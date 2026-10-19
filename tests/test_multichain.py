"""Meal plans made with REMA 1000, Netto and Lidl's offers, and the shops' own lists."""

from __future__ import annotations

from datetime import date
import json
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.middagsro import chains as ch, mealplan as mp, planedit as pe
from custom_components.middagsro.storage import clean_settings
from homeassistant.core import HomeAssistant

from .test_mealplan import SETTINGS, START, FakeAI, _generate, ai_answer
from .test_planedit import FakeAI as SwapAI, plan_with_uses

NETTO, LIDL, REMA = "9ba51", "71c90", ch.REMA_ID
# The real fetch: conftest replaces it for every test, so it is kept from before.
REAL_CHAIN_OFFERS = mp.MealPlanner._async_chain_offers
WEEK = {"valid_from": "2026-10-16T22:00:00+0000", "valid_to": "2026-10-23T21:59:59+0000"}


def chain_offer(
    offer_id: str, heading: str, price: float, quantity: str | None = None, **times: Any
) -> dict[str, Any]:
    """Another chain's offer as ChainOffers gives it."""
    return {
        "id": offer_id,
        "heading": heading,
        "description": f"{heading}\nFra Danmark",
        "price": price,
        "pre_price": None,
        "quantity": quantity,
        **WEEK,
        **times,
    }


CHAIN_OFFERS = {
    NETTO: [
        chain_offer(
            "n-old",
            "Gammelt tilbud",
            5,
            valid_from="2026-10-03T22:00:00+0000",
            valid_to="2026-10-10T21:59:59+0000",
        ),
        chain_offer("n-1", "Kyllingebryst", 35.0, "450 g"),
    ],
    LIDL: [chain_offer("l-1", "Laksefilet", 49.0, "400 g")],
}


# ----------------------------------------------------------------- functions


def test_settings_plan_chains() -> None:
    """Netto, Lidl and REMA by default; the family's order kept; REMA always there."""
    assert clean_settings({})["plan_chains"] == [NETTO, LIDL, REMA]
    assert clean_settings({"plan_chains": [LIDL, REMA, NETTO]})["plan_chains"] == [
        LIDL,
        REMA,
        NETTO,
    ]
    assert clean_settings({"plan_chains": [NETTO, "ukendt", NETTO, 7]})["plan_chains"] == [
        NETTO,
        REMA,  # REMA prices what isn't on offer
    ]
    assert clean_settings({"plan_chains": "Netto"})["plan_chains"] == [REMA]


def test_offers_for_the_ai() -> None:
    """Each chain's running offers get an id with its name; REMA keeps "o<i>"."""
    offers = ch.plan_offers(CHAIN_OFFERS, START)
    assert list(offers) == ["netto0", "lidl0"]  # the old Netto offer has ended
    assert offers["netto0"]["dealer_id"] == NETTO
    assert ch.plan_offer_lines(offers) == [
        "netto0 | Netto: Kyllingebryst | 35 kr. | 450 g",
        "lidl0 | Lidl: Laksefilet | 49 kr. | 400 g",
    ]
    cheap = {"x0": {**offers["lidl0"], "price": None, "pre_price": 60.0, "quantity": None}}
    assert ch.plan_offer_lines(cheap) == ["x0 | Lidl: Laksefilet | ? (før 60)"]
    assert ch.chain_name(REMA) == "REMA 1000"


def test_shops_and_prompt() -> None:
    """The AI gets every chain's offers, the family's order and a budget across shops."""
    offers = ch.plan_offers(CHAIN_OFFERS, START)
    settings = clean_settings({"budget": 600})
    assert mp.plan_shops(settings, offers) == [NETTO, LIDL, REMA]
    # A chain whose avis could not be read is left out: its items go elsewhere.
    assert mp.plan_shops(settings, {"lidl0": offers["lidl0"]}) == [LIDL, REMA]
    assert mp.plan_shops(settings, None) == [REMA]

    args: dict[str, Any] = {
        "settings": settings,
        "dates": mp.plan_dates(START, 7),
        "catalog": None,
        "offers": [],
        "favorites_due": [],
        "favorites_optional": [],
        "recent_dishes": [],
    }
    prompt = mp.build_prompt(**args, chain_offers=offers)
    assert "Familien handler i Netto, Lidl, REMA 1000 i Danmark" in prompt
    assert "under 600 kr. i alt på tværs af alle butikkerne" in prompt
    assert "UGENS TILBUD I DE ANDRE BUTIKKER" in prompt
    assert "netto0 | Netto: Kyllingebryst | 35 kr. | 450 g" in prompt
    assert "lidl0 | Lidl: Laksefilet | 49 kr. | 400 g" in prompt
    assert "Varer, der ikke er på tilbud, købes i Netto" in prompt
    assert "vælg efter rækkefølgen Netto, Lidl, REMA 1000" in prompt

    # Without other chains' offers: REMA only, as before.
    prompt = mp.build_prompt(**args)
    assert "Familien handler i REMA 1000 i Danmark." in prompt
    assert "under 600 kr. med REMA 1000-priser" in prompt
    assert "ANDRE BUTIKKER" not in prompt


# ----------------------------------------------------------------- planning


@pytest.fixture
def storage_contents() -> dict[str, Any]:
    """The family shops in Netto first, then Lidl, then REMA 1000."""
    return {"settings": {**SETTINGS, "plan_chains": [NETTO, LIDL, REMA]}}


async def test_chain_offers_are_read(
    hass: HomeAssistant, init_integration: MockConfigEntry
) -> None:
    """The chosen chains' offers are read; one that can't be read is left out."""
    planner = init_integration.runtime_data.planner

    async def offers(dealer_id: str, force: bool = False) -> list[dict[str, Any]]:
        if dealer_id == LIDL:
            raise ch.ChainError("Tjek svarede 500")
        return [{**entry, "dealer_id": dealer_id} for entry in CHAIN_OFFERS[dealer_id]]

    with patch.object(planner.chains, "async_offers", new=AsyncMock(side_effect=offers)) as get:
        found = await REAL_CHAIN_OFFERS(planner, START)
    assert list(found) == ["netto0"]
    assert [c.args[0] for c in get.call_args_list] == [NETTO, LIDL]  # not REMA: its own avis


async def test_plan_across_chains(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    mock_client: MagicMock,
    ai_task: str,
) -> None:
    """Every item gets a shop: offers where they are, the rest in Netto; one budget."""
    planner = init_integration.runtime_data.planner
    offers = ch.plan_offers(CHAIN_OFFERS, START)
    shopping = [
        {"name": "Hakket oksekød", "amount": 1000, "unit": "g", "search": "hakket oksekød",
         "category": "Kød", "offer": "o0"},
        {"name": "Kyllingebryst", "amount": 800, "unit": "g", "search": "kyllingebryst",
         "category": "Kød", "offer": "netto0"},
        {"name": "Laks", "amount": 400, "unit": "g", "search": "laks", "category": "Fisk",
         "offer": "lidl0"},
        {"name": "Spaghetti", "amount": 500, "unit": "g", "search": "spaghetti",
         "category": "Kolonial"},
    ]  # fmt: skip
    dates = mp.plan_dates(START, 7)
    ai = FakeAI(json.dumps(ai_answer(dates, shopping)))  # type: ignore[arg-type]
    with patch.object(planner, "_async_chain_offers", new=AsyncMock(return_value=offers)):
        await _generate(planner, ai)

    prompt = ai.prompts[0]
    assert "netto0 | Netto: Kyllingebryst" in prompt
    assert "lidl0 | Lidl: Laksefilet" in prompt
    assert "o0 | Hakket oksekød 8-12%" in prompt  # REMA's avis, as before

    plan = init_integration.runtime_data.store.latest_plan
    assert plan is not None
    lines = {line["name"]: line for line in plan["shopping"]}
    # REMA's offer: a REMA product on the REMA list, as before.
    assert lines["Hakket oksekød"]["product"]["id"] == 30001
    assert "buy_at" not in lines["Hakket oksekød"]
    # Netto's and Lidl's offers: on those shops' lists, at the offer's price.
    chicken = lines["Kyllingebryst"]
    assert (chicken["buy_at"], chicken["chain_heading"], chicken["chain_price"]) == (
        NETTO,
        "Kyllingebryst",
        35.0,
    )
    assert (chicken["packages"], chicken["cost"]) == (2, 70.0)  # 800 g from 450 g packs
    assert chicken["product"] is None
    assert chicken["chain_only"] is True
    salmon = lines["Laks"]
    assert (salmon["buy_at"], salmon["packages"], salmon["cost"]) == (LIDL, 1, 49.0)
    # Not on offer: in Netto, the family's favourite, priced as at REMA.
    pasta = lines["Spaghetti"]
    assert pasta["buy_at"] == NETTO
    assert pasta["price_estimated"] is True
    assert pasta["chain_price"] is None
    assert pasta["product"]["id"] == 60003  # still gluten-free
    assert pasta["cost"] == pytest.approx(pasta["packages"] * pasta["product"]["price"])
    # The weekly REMA items stay at REMA.
    assert "buy_at" not in lines["Rugbrød"]
    # One budget across the shops.
    assert plan["total"] == pytest.approx(sum(line["cost"] or 0 for line in plan["shopping"]))
    assert plan["total"] == pytest.approx(80 + 70 + 49 + pasta["cost"] + 36)

    # Only REMA's items go to the REMA app.
    await planner.async_send(plan["id"], "all")
    sent = [
        c.kwargs.get("product_id") or c.kwargs.get("name")
        for c in mock_client.async_add_to_list.call_args_list
    ]
    assert sorted(sent) == [30001, 70001]

    # Back to REMA: no longer an estimate.
    moved = await ch.async_move_line(planner, plan["id"], pasta["id"], None)
    back = next(line for line in moved["shopping"] if line["id"] == pasta["id"])
    assert "buy_at" not in back
    assert "price_estimated" not in back


async def test_netto_avis_missing(
    hass: HomeAssistant, init_integration: MockConfigEntry, mock_client: MagicMock, ai_task: str
) -> None:
    """Netto's avis could not be read: what isn't on offer goes to Lidl, the next shop."""
    planner = init_integration.runtime_data.planner
    offers = {"lidl0": ch.plan_offers(CHAIN_OFFERS, START)["lidl0"]}
    shopping = [{"name": "Spaghetti", "amount": 500, "unit": "g", "search": "spaghetti"}]
    ai = FakeAI(json.dumps(ai_answer(mp.plan_dates(START, 7), shopping)))  # type: ignore[arg-type]
    with patch.object(planner, "_async_chain_offers", new=AsyncMock(return_value=offers)):
        await _generate(planner, ai)
    plan = init_integration.runtime_data.store.latest_plan
    assert plan is not None
    pasta = next(line for line in plan["shopping"] if line["name"] == "Spaghetti")
    assert pasta["buy_at"] == LIDL
    assert "Familien handler i Lidl, REMA 1000" in ai.prompts[0]


async def test_swap_with_other_chains(
    hass: HomeAssistant,
    hass_storage: dict[str, Any],
    init_integration: MockConfigEntry,
    mock_client: MagicMock,
    ai_task: str,
) -> None:
    """Swapping a dish offers the other chains' offers too, and puts them on their lists."""
    store = init_integration.runtime_data.store
    planner = init_integration.runtime_data.planner
    # REMA first this time: what isn't on offer stays on the REMA list.
    await store.async_set_settings({**store.settings, "plan_chains": [REMA, LIDL]})
    await store.async_add_plan(plan_with_uses())
    offers = {"lidl0": ch.plan_offers(CHAIN_OFFERS, START)["lidl0"]}
    items = {
        "add": [
            {"name": "Laks", "amount": 400, "unit": "g", "search": "laks", "category": "Fisk",
             "offer": "lidl0"},
            {"name": "Persille", "amount": 1, "unit": "bundt", "search": "persille"},
        ],
        "uses": ["Laks", "Persille"],
    }  # fmt: skip
    ai = SwapAI(items=items, options={"options": [{"dish": "Laks i ovn", "type": "normal"}]})
    with (
        patch("homeassistant.components.ai_task.async_generate_data", new=ai),
        patch.object(planner, "_async_chain_offers", new=AsyncMock(return_value=offers)),
    ):
        options = await pe.async_swap_options(planner, "p", "2026-10-18")
        plan = await pe.async_swap_dish(planner, "p", "2026-10-18", {"dish": "Laks i ovn"})

    assert options["options"][0]["dish"] == "Laks i ovn"
    assert "lidl0 | Lidl: Laksefilet | 49 kr." in ai.prompts["REMA 1000 andre retter"][0]
    assert "lidl0 | Lidl: Laksefilet" in ai.prompts["REMA 1000 ny ret"][0]
    lines = {line["name"]: line for line in plan["shopping"]}
    assert (lines["Laks"]["buy_at"], lines["Laks"]["cost"]) == (LIDL, 49.0)
    assert "buy_at" not in lines["Persille"]
    assert plan["total"] == pytest.approx(sum(line.get("cost") or 0 for line in plan["shopping"]))


def test_dates_used() -> None:
    """The shopping day decides which offers run."""
    assert ch.plan_offers(CHAIN_OFFERS, date(2026, 10, 9)) == {"netto0": {
        **CHAIN_OFFERS[NETTO][0], "dealer_id": NETTO
    }}  # fmt: skip
