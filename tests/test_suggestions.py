"""Daily suggestions: three dinners a day, fish once a week, about 500 kcal, no 👎 dishes."""

from __future__ import annotations

import asyncio
from datetime import date, datetime
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry
from pytest_homeassistant_custom_component.typing import WebSocketGenerator

from custom_components.middagsro import chains as ch, suggestions as sg
from custom_components.middagsro.const import DOMAIN
from custom_components.middagsro.mealplan import plan_dates
from custom_components.middagsro.storage import clean_settings
from homeassistant.const import ATTR_ENTITY_ID
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ServiceValidationError

from .conftest import make_plan

MONDAY = date(2026, 10, 19)  # the monday after NOW (wednesday 14 october)
DATES = plan_dates(MONDAY, 7)
LIDL = "71c90"
RECIPE = {"ingredients": [{"name": "laks", "amount": "600 g"}], "steps": ["Bag laksen."]}
SENSOR = "sensor.middagsro_daily_suggestions"
SELECT_MONDAY = "select.middagsro_dinner_mandag"


def option(dish: str, kcal: Any = 500, fish: bool = False, **extra: Any) -> dict[str, Any]:
    """One of the AI's dinners."""
    return {
        "dish": dish,
        "type": "normal",
        "fish": fish,
        "kcal": kcal,
        "servings": 4,
        "active_minutes": 20,
        "total_minutes": 30,
        "shopping": extra.pop(
            "shopping",
            [{"name": "Løg", "amount": 2, "unit": "stk", "search": "løg"}],
        ),
        **extra,
    }


def week_answer(fish_on_sunday: bool = True) -> dict[str, Any]:
    """Three good dinners a day, plus some that break the rules."""
    days = []
    for idx, day in enumerate(DATES):
        options = [option(f"Ret {idx}-{n}") for n in range(3)]
        days.append({"date": day.isoformat(), "options": options})
    monday = days[0]["options"]
    monday.insert(0, option("Kraftig gryde", kcal=820))  # too many kcal
    monday.insert(0, option("Lasagne"))  # thumbs down
    monday.insert(0, option("Uden kcal", kcal=None))
    tuesday = days[1]["options"]
    tuesday.insert(0, option("Ovnbagt laks", fish=True, shopping=[
        {"name": "Laks", "amount": 400, "unit": "g", "search": "laks", "offer": "lidl0"}
    ]))  # fmt: skip
    tuesday.insert(1, option("Rejer i karry"))  # fish by its name; a second fish that day
    days[2]["options"].insert(0, option("Ret 1-0"))  # the same dish as on tuesday
    if fish_on_sunday:
        days[6]["options"].append(option("Torsk med kartofler", fish=True))
    days.append("ikke en dag")
    return {"days": days}


class FakeAI:
    """Answers the suggestions and recipe tasks."""

    def __init__(self, *answers: Any) -> None:
        self.answers = list(answers)
        self.prompts: list[str] = []

    async def __call__(self, hass: HomeAssistant, **kwargs: Any) -> SimpleNamespace:
        await asyncio.sleep(0)
        if kwargs["task_name"] == sg.TASK_NAME:
            self.prompts.append(kwargs["instructions"])
            return SimpleNamespace(data=self.answers.pop(0))
        return SimpleNamespace(data=RECIPE)


@pytest.fixture
def ai() -> Any:
    """The AI for the whole test (recipes are written in the background after a pick)."""
    fake = FakeAI()
    with patch("homeassistant.components.ai_task.async_generate_data", new=fake):
        yield fake


@pytest.fixture
def storage_contents() -> dict[str, Any]:
    """The family gave lasagne a thumbs down; favourites to rotate."""
    return {
        "settings": {"ai_task_entity": "ai_task.assistant", "must_haves": []},
        "recipes": [
            {
                "id": "r1",
                "name": "Lasagne",
                "rating": "dislike",
                "favorite": False,
                "ingredients": [],
                "steps": [],
            }
        ],
        "favorites": [
            {"id": "fav1", "text": "Frikadeller", "frequency": "weekly", "last_used": None},
            {"id": "fav2", "text": "Tacos", "frequency": "on_offer", "last_used": None},
        ],
    }


async def _generate(hass: HomeAssistant, entry: MockConfigEntry) -> dict[str, Any]:
    planner = entry.runtime_data.planner
    offers = {"lidl0": ch.plan_offers({LIDL: [{
        "id": "l-1", "heading": "Laksefilet", "description": None, "price": 49.0,
        "pre_price": None, "quantity": "400 g",
        "valid_from": "2026-10-16T22:00:00+0000", "valid_to": "2026-10-23T21:59:59+0000",
    }]}, MONDAY)["lidl0"]}  # fmt: skip
    with patch.object(planner, "_async_chain_offers", new=AsyncMock(return_value=offers)):
        sg.async_start(planner)
        assert planner.generating
        await planner._task
    assert planner.status["state"] == "idle"
    suggestions = entry.runtime_data.store.suggestions
    assert suggestions is not None
    return suggestions


# ----------------------------------------------------------------- functions


def test_fish_words() -> None:
    """Fish by the AI's word or the dish's name; whole words for short names."""
    assert sg.is_fish("Ovnbagt laks med broccoli")
    assert sg.is_fish("Fiskefrikadeller med remoulade")
    assert sg.is_fish("Rejer i karry")
    assert sg.is_fish("Stegt sej med persillesovs")
    assert not sg.is_fish("Kylling i sejt sovs")
    assert not sg.is_fish("Lasagne")
    assert sg.is_fish("Bouillabaisse", flagged=True)


def test_kcal_filter() -> None:
    """About 500 kcal, or the family's own target; dinners outside it are left out."""
    assert sg.kcal_range(clean_settings({})) == (450, 550)
    own = clean_settings({"nutrition_enabled": True, "kcal_min": 600, "kcal_max": 700})
    assert sg.kcal_range(own) == (600, 700)
    rules: dict[str, Any] = {"low": 450, "high": 550, "disliked": set(), "fish_allowed": True}
    assert sg.clean_option(option("Pasta", kcal=500), **rules)["kcal"] == 500
    assert sg.clean_option(option("Pasta", kcal="530"), **rules)["kcal"] == 530
    assert sg.clean_option(option("Gryde", kcal=820), **rules) is None
    assert sg.clean_option(option("Salat", kcal=300), **rules) is None
    assert sg.clean_option(option("Ukendt", kcal=None), **rules) is None
    assert sg.clean_option("ikke en ret", **rules) is None
    assert sg.clean_option({"dish": " "}, **rules) is None


def test_thumbs_down_left_out() -> None:
    """A dish the family gave 👎 is never a suggestion."""
    rules: dict[str, Any] = {"low": 450, "high": 550, "fish_allowed": True}
    assert sg.clean_option(option("Lasagne"), disliked={"lasagne"}, **rules) is None
    assert sg.clean_option(option("  Lasagne "), disliked={"lasagne"}, **rules) is None
    assert sg.clean_option(option("Lasagne al forno"), disliked={"lasagne"}, **rules)


def test_fish_rule() -> None:
    """One fish a day at most, the last day has fish when the week needs it, never two."""
    rules: dict[str, Any] = {"low": 450, "high": 550, "disliked": set()}
    salmon = option("Laks i ovn", fish=True)
    assert sg.clean_option(salmon, fish_allowed=True, **rules)["fish"] is True
    assert sg.clean_option(salmon, fish_allowed=False, **rules) is None  # the week has fish

    def opt(name: str, fish: bool = False) -> dict[str, Any]:
        cleaned = sg.clean_option(option(name, fish=fish), fish_allowed=True, **rules)
        assert cleaned is not None
        return cleaned

    found = {
        DATES[0].isoformat(): [opt("Laks", True), opt("Torsk", True), opt("A"), opt("B")],
        DATES[6].isoformat(): [opt("C"), opt("D"), opt("E"), opt("Sej med kartofler")],
    }
    picked = sg.pick_options(found, DATES, fish_needed=True)
    monday = [o["dish"] for o in picked[DATES[0].isoformat()]]
    assert monday == ["Laks", "A", "B"]  # not two fish the same day
    sunday = picked[DATES[6].isoformat()]
    assert sunday[0]["dish"] == "Sej med kartofler"  # the last chance: fish first
    assert sg._missing(picked, DATES, True) == DATES[1:6]

    # Sunday without fish while the week needs it: sunday is missing too.
    found[DATES[6].isoformat()] = [opt("C"), opt("D"), opt("E")]
    picked = sg.pick_options(found, [DATES[0], DATES[6]], fish_needed=True)
    assert sg._missing(picked, [DATES[0], DATES[6]], True) == [DATES[6]]
    assert sg._missing(picked, [DATES[0], DATES[6]], False) == []


def test_prompt() -> None:
    """The prompt asks for three a day, the kcal, the week's fish and leaves out 👎."""
    args: dict[str, Any] = {
        "settings": clean_settings({}),
        "dates": DATES,
        "offers": [],
        "late": {},
        "chain_lines": ["lidl0 | Lidl: Laksefilet | 49 kr. | 400 g"],
        "favorites": [{"id": "fav1", "text": "Frikadeller"}],
        "inspiration": [{"id": "fav2", "text": "Tacos", "frequency": "on_offer"}],
        "recipes": [{"id": "r2", "name": "Kyllingesuppe"}],
        "mealie": [{"slug": "boller", "name": "Boller i karry"}],
        "recent": ["Chili"],
        "disliked": ["Lasagne"],
    }
    prompt = sg.build_suggestions_prompt(**args, fish_needed=True)
    assert "3 forskellige aftensmåltider til HVER af disse dage: mandag 2026-10-19" in prompt
    assert "450-550 kcal pr. voksenportion" in prompt
    assert "søndag 2026-10-25 er sidste chance" in prompt
    assert "brug dem ALDRIG: Lasagne" in prompt
    assert "[fav1] Frikadeller" in prompt
    assert "[fav2] Tacos (kun på tilbud)" in prompt
    assert "lidl0 | Lidl: Laksefilet" in prompt
    assert "boller | Boller i karry" in prompt
    prompt = sg.build_suggestions_prompt(**args, fish_needed=False, missing=[DATES[3]])
    assert "INGEN af forslagene må være med fisk" in prompt
    assert "HVER af disse dage: torsdag 2026-10-22." in prompt


# ----------------------------------------------------------------- the week


async def test_generate_choose_and_dislike(
    hass: HomeAssistant, init_integration: MockConfigEntry, ai_task: str, ai: FakeAI
) -> None:
    """Three dinners a day, picks become the week's plan, fish once, 👎 removes a dish."""
    ai.answers.append(week_answer())
    suggestions = await _generate(hass, init_integration)
    assert len(ai.prompts) == 1
    assert "[fav1] Frikadeller" in ai.prompts[0]
    assert suggestions["start_date"] == "2026-10-19"
    assert suggestions["fish_needed"] is True
    assert suggestions["missing"] == []
    days = {d["date"]: d for d in suggestions["days"]}
    names = {d: [o["dish"] for o in day["options"]] for d, day in days.items()}
    # Over 550 kcal, without kcal and 👎 are left out.
    assert names["2026-10-19"] == ["Ret 0-0", "Ret 0-1", "Ret 0-2"]
    # One fish a day: the shrimp curry is a second fish on tuesday.
    assert names["2026-10-20"] == ["Ovnbagt laks", "Ret 1-0", "Ret 1-1"]
    # The same dish only once in the week.
    assert "Ret 1-0" not in names["2026-10-21"]
    # Sunday is the last chance for fish: its fish dinner comes first.
    assert names["2026-10-25"][0] == "Torsk med kartofler"
    salmon = days["2026-10-20"]["options"][0]
    assert (salmon["chain"], salmon["cost"]) == (LIDL, 49.0)  # on Lidl's offer
    # Not on offer: in the first shop with offers (Lidl here), priced as at REMA.
    monday_first = days["2026-10-19"]["options"][0]
    assert monday_first["chain"] == LIDL
    assert monday_first["shopping"][0]["price_estimated"] is True

    planner = init_integration.runtime_data.planner
    store = init_integration.runtime_data.store
    # Pick the salmon on tuesday: the week's plan, the salmon on Lidl's list.
    plan = await sg.async_choose(planner, "2026-10-20", salmon["id"])
    assert plan["kind"] == "suggestions"
    assert [d["dish"] for d in plan["days"]][:2] == ["", "Ovnbagt laks"]
    assert plan["days"][1]["fish"] is True
    laks = next(line for line in plan["shopping"] if line["name"] == "Laks")
    assert laks["buy_at"] == LIDL
    assert store.latest_plan is plan
    await hass.async_block_till_done()
    assert plan["days"][1]["ingredients"] == [{"name": "laks", "amount": "600 g"}]

    # A second fish in the week is not allowed.
    cod = days["2026-10-25"]["options"][0]
    with pytest.raises(ServiceValidationError) as err:
        await sg.async_choose(planner, "2026-10-25", cod["id"])
    assert err.value.translation_key == "one_fish_a_week"

    # Two dinners with onions: one line for the week.
    monday = days["2026-10-19"]["options"][0]
    plan = await sg.async_choose(planner, "2026-10-19", monday["id"])
    onions = [line for line in plan["shopping"] if line["name"] == "Løg"]
    assert len(onions) == 1
    assert onions[0]["amount"] == 2
    await sg.async_choose(planner, "2026-10-21", days["2026-10-21"]["options"][0]["id"])
    onions = [line for line in plan["shopping"] if line["name"] == "Løg"]
    assert (len(onions), onions[0]["amount"]) == (1, 4)
    assert plan["total"] == pytest.approx(sum(line.get("cost") or 0 for line in plan["shopping"]))
    # The same pick again keeps the dinner (and its recipe).
    plan = await sg.async_choose(planner, "2026-10-20", salmon["id"])
    assert plan["days"][1]["ingredients"]

    # 👎 on the chosen salmon: gone from the suggestions and the plan, never again.
    await sg.async_dislike(planner, "2026-10-20", salmon["id"])
    assert days["2026-10-20"]["chosen"] is None
    assert "Ovnbagt laks" not in [o["dish"] for o in days["2026-10-20"]["options"]]
    assert plan["days"][1]["dish"] == ""
    assert not [line for line in plan["shopping"] if line["name"] == "Laks"]
    disliked = next(r for r in store.recipes if r["name"] == "Ovnbagt laks")
    assert disliked["rating"] == "dislike"
    # Now the week's fish can be on sunday.
    await sg.async_choose(planner, "2026-10-25", cod["id"])
    # Unpick a day.
    plan = await sg.async_choose(planner, "2026-10-25", None)
    assert plan["days"][6]["dish"] == ""

    # The next suggestions leave the 👎 dish out.
    ai.answers.append(week_answer())
    await _generate(hass, init_integration)
    assert "Ovnbagt laks" in ai.prompts[-1].split("brug dem ALDRIG:")[1].split("\n")[0]
    tuesday = store.suggestions["days"][1]  # type: ignore[index]
    assert "Ovnbagt laks" not in [o["dish"] for o in tuesday["options"]]

    for call in (
        sg.async_choose(planner, "2026-11-01", None),
        sg.async_choose(planner, "2026-10-19", "ukendt"),
        sg.async_dislike(planner, "2026-10-19", "ukendt"),
    ):
        with pytest.raises(ServiceValidationError) as err:
            await call
        assert err.value.translation_key == "suggestion_not_found"


async def test_second_round_and_fish_in_the_week(
    hass: HomeAssistant, init_integration: MockConfigEntry, ai_task: str, ai: FakeAI
) -> None:
    """Days without enough dinners are asked for again; a week with fish gets no more."""
    store = init_integration.runtime_data.store
    first = week_answer(fish_on_sunday=False)
    first["days"] = first["days"][:5]  # saturday and sunday missing
    sunday = {"date": "2026-10-25", "options": [
        option("Sej med kartofler", fish=True), option("X1"), option("X2")
    ]}  # fmt: skip
    saturday = {"options": [option("Y1"), option("Y2"), option("Y3")]}  # by its place
    ai.answers += [first, {"days": [saturday, sunday]}]
    suggestions = await _generate(hass, init_integration)
    assert len(ai.prompts) == 2
    assert "lørdag 2026-10-24, søndag 2026-10-25." in ai.prompts[1]
    assert [o["dish"] for o in suggestions["days"][5]["options"]] == ["Y1", "Y2", "Y3"]
    assert suggestions["days"][6]["options"][0]["dish"] == "Sej med kartofler"

    # Another plan already has fish this week: no fish at all.
    other = make_plan("other", start="2026-10-18")
    other["days"][2]["dish"] = "Fiskefrikadeller"  # tuesday 20 october
    await store.async_add_plan(other)
    ai.answers.append(week_answer())
    suggestions = await _generate(hass, init_integration)
    assert "INGEN af forslagene må være med fisk" in ai.prompts[-1]
    assert suggestions["fish_needed"] is False
    assert not [o for d in suggestions["days"] for o in d["options"] if o["fish"]]
    assert suggestions["missing"] == []


async def test_entities_action_and_sunday(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    ai_task: str,
    ai: FakeAI,
    hass_ws_client: WebSocketGenerator,
    freezer: Any,
) -> None:
    """The sensor, the selects, the button, the action, the panel and the sunday run."""
    planner = init_integration.runtime_data.planner
    assert hass.states.get(SENSOR).state == "unknown"
    assert hass.states.get(SELECT_MONDAY).state == "unavailable"

    ai.answers.append(week_answer())
    with patch.object(planner, "_async_chain_offers", new=AsyncMock(return_value={})):
        await hass.services.async_call(DOMAIN, "generate_daily_suggestions", {}, blocking=True)
        await planner._task
    await hass.async_block_till_done()
    state = hass.states.get(SENSOR)
    assert state.state == "7"  # seven days to pick
    first = state.attributes["days"][0]
    assert first["weekday"] == "mandag"
    assert first["options"][0] == {
        "name": "Ret 0-0", "kcal": 500, "chain": "REMA 1000", "price": 8.0, "fish": False
    }  # fmt: skip
    select = hass.states.get(SELECT_MONDAY)
    assert select.state == sg.NOTHING
    pick = select.attributes["options"][1]
    assert pick == "Ret 0-0 · 500 kcal · REMA 1000 · 8 kr."
    await hass.services.async_call(
        "select", "select_option", {ATTR_ENTITY_ID: SELECT_MONDAY, "option": pick}, blocking=True
    )
    await hass.async_block_till_done()
    assert hass.states.get(SELECT_MONDAY).state == pick
    assert hass.states.get(SENSOR).state == "6"
    plan = init_integration.runtime_data.store.latest_plan
    assert plan is not None
    assert plan["days"][0]["dish"] == "Ret 0-0"
    # On the day it is Dinner today.
    freezer.move_to("2026-10-19T12:00:00+02:00")
    planner._notify()
    await hass.async_block_till_done()
    assert hass.states.get("sensor.middagsro_dinner_today").state == "Ret 0-0"
    freezer.move_to("2026-10-14T12:00:00+02:00")

    # The button starts them too.
    with patch("custom_components.middagsro.button.async_start_suggestions") as start:
        await hass.services.async_call(
            "button",
            "press",
            {ATTR_ENTITY_ID: "button.middagsro_make_daily_suggestions"},
            blocking=True,
        )
    start.assert_called_once_with(planner)

    # The panel.
    client = await hass_ws_client(hass)
    await client.send_json({"id": 1, "type": "middagsro/state"})
    state_msg = await client.receive_json()
    assert state_msg["result"]["suggestions"]["start_date"] == "2026-10-19"
    tuesday = init_integration.runtime_data.store.suggestions["days"][1]  # type: ignore[index]
    await client.send_json(
        {"id": 2, "type": "middagsro/suggestions/choose", "date": tuesday["date"],
         "option_id": tuesday["options"][1]["id"]}
    )  # fmt: skip
    assert (await client.receive_json())["success"]
    await client.send_json(
        {"id": 3, "type": "middagsro/suggestions/dislike", "date": tuesday["date"],
         "option_id": tuesday["options"][2]["id"]}
    )  # fmt: skip
    assert len((await client.receive_json())["result"]["days"][1]["options"]) == 2
    with patch("custom_components.middagsro.websocket.async_start_suggestions") as start:
        await client.send_json({"id": 4, "type": "middagsro/suggestions/generate"})
        assert (await client.receive_json())["success"]
    start.assert_called_once()
    await hass.async_block_till_done()

    # Sunday morning: next week's suggestions, once, and only when switched on.
    sunday = datetime(2026, 10, 25, 7, 0).astimezone()
    with patch.object(sg, "async_start") as start:
        sg.async_sunday(planner, datetime(2026, 10, 24, 7, 0).astimezone())  # saturday
        sg.async_sunday(planner, datetime(2026, 10, 18, 7, 0).astimezone())  # already made
        start.assert_not_called()
        sg.async_sunday(planner, sunday)
        start.assert_called_once_with(planner, date(2026, 10, 26))
        await init_integration.runtime_data.store.async_set_settings(
            {**init_integration.runtime_data.store.settings, "suggestions_auto": False}
        )
        sg.async_sunday(planner, sunday)
        start.assert_called_once()
    await init_integration.runtime_data.store.async_set_settings(
        {**init_integration.runtime_data.store.settings, "suggestions_auto": True}
    )
    with patch.object(sg, "async_start", side_effect=ServiceValidationError("ingen AI")):
        sg.async_sunday(planner, sunday)  # logged, not raised


async def test_needs_ai_and_one_at_a_time(
    hass: HomeAssistant, init_integration: MockConfigEntry
) -> None:
    """Without an AI Task nothing starts; and not while a plan is being made."""
    planner = init_integration.runtime_data.planner
    with pytest.raises(ServiceValidationError) as err:
        sg.async_start(planner)
    assert err.value.translation_key == "no_ai_task"
    with patch.object(type(planner), "generating", new=True), pytest.raises(ServiceValidationError):
        sg.async_start(planner)


async def test_failed_run(
    hass: HomeAssistant, init_integration: MockConfigEntry, ai_task: str
) -> None:
    """An AI that fails: the status says so."""
    planner = init_integration.runtime_data.planner

    async def broken(hass: HomeAssistant, **kwargs: Any) -> SimpleNamespace:
        raise ServiceValidationError("AI'en er nede")

    with patch("homeassistant.components.ai_task.async_generate_data", new=broken):
        sg.async_start(planner, MONDAY)
        await planner._task
    assert planner.status["state"] == "error"
    assert sg.summary(None) == []
