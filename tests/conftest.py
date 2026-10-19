"""Fixtures for the REMA 1000 tests."""

from __future__ import annotations

from collections.abc import AsyncGenerator, Generator
from datetime import UTC, datetime
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.middagsro.api import (
    Catalog,
    Offer,
    Product,
    RemaClient,
    ShoppingList,
    ShoppingListItem,
)
from custom_components.middagsro.const import DOMAIN
from homeassistant.const import CONF_EMAIL, CONF_PASSWORD
from homeassistant.core import HomeAssistant

pytest_plugins = "pytest_homeassistant_custom_component"

USER_ID = 4242
EMAIL = "family@example.com"
PASSWORD = "correct-horse"
NOW = datetime(2026, 10, 14, 10, 0, tzinfo=UTC)  # a Wednesday


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations: None) -> None:
    """Load integrations from custom_components."""


@pytest.fixture(autouse=True)
def no_chain_offers_for_plans() -> Generator[None]:
    """Plans are made with REMA's avis only, unless a test gives other chains' offers."""
    with patch(
        "custom_components.middagsro.mealplan.MealPlanner._async_chain_offers",
        new=AsyncMock(return_value={}),
    ):
        yield


@pytest.fixture(autouse=True)
def skip_panel_dependencies(hass: HomeAssistant) -> None:
    """The sidebar panel needs the real frontend; mark it as loaded instead."""
    hass.config.components.update({"frontend", "panel_custom"})


def make_product(
    product_id: int,
    name: str,
    price: float | None,
    *,
    underline: str | None = None,
    department: str = "Kolonial",
    category: str | None = None,
    normal_price: float | None = None,
    is_advertised: bool = False,
    is_campaign: bool = False,
    is_organic: bool = False,
    compare_unit: str | None = None,
    compare_unit_price: float | None = None,
) -> Product:
    """A product as the client returns it."""
    return Product(
        id=product_id,
        name=name,
        underline=underline,
        department=department,
        category=category,
        price=price,
        normal_price=normal_price if normal_price is not None else price,
        compare_unit=compare_unit,
        compare_unit_price=compare_unit_price,
        is_advertised=is_advertised,
        is_campaign=is_campaign,
        price_valid_to=None,
        upcoming_price=None,
        upcoming_from=None,
        upcoming_is_advertised=False,
        is_organic=is_organic,
        labels=["Økologisk"] if is_organic else [],
        image=f"https://images.example/{product_id}.webp",
    )


CATALOGUE = [
    make_product(
        20494,
        "LETMÆLK 1,5% FEDT",
        10.95,
        underline="1 LTR. / REMA 1000",
        department="Mejeri",
        compare_unit="ltr",
        compare_unit_price=10.95,
    ),
    make_product(
        20495,
        "LETMÆLK 1,5% FEDT",
        4.5,
        underline="250 ML / REMA 1000",
        department="Mejeri",
        compare_unit="ltr",
        compare_unit_price=18.0,
    ),
    make_product(
        20496,
        "ØKO. LETMÆLK",
        13.95,
        underline="1 LTR. / ARLA, ØKOLOGISK",
        department="Mejeri",
        is_organic=True,
        compare_unit="ltr",
        compare_unit_price=13.95,
    ),
    make_product(
        30001,
        "HK. OKSEKØD 8-12%",
        40.0,
        underline="500 GR. / DANSK",
        department="Kød",
        normal_price=50.0,
        is_advertised=True,
        is_campaign=True,
    ),
    make_product(30002, "KYLLINGEBRYST", 45.0, underline="600 GR. / DANSK", department="Kød"),
    make_product(30003, "HK. KYLLING", 30.0, underline="400 GR. / DANSK", department="Kød"),
    make_product(40001, "SKRABEÆG", 25.0, underline="10 STK. / M/L", department="Mejeri"),
    make_product(40002, "FRILANDSÆG", 32.0, underline="10 STK. / M/L", department="Mejeri"),
    make_product(
        40003,
        "ØKOLOGISKE ÆG",
        38.0,
        underline="10 STK. / M/L, ØKOLOGISK",
        department="Mejeri",
        is_organic=True,
    ),
    make_product(50001, "BROCCOLI", 12.0, underline="1 STK.", department="Frugt & grønt"),
    make_product(
        50002,
        "ØKO. BROCCOLI",
        14.0,
        underline="1 STK. / ØKOLOGISK",
        department="Frugt & grønt",
        is_organic=True,
    ),
    make_product(50003, "LØG", 8.0, underline="1 KG / SPANIEN", department="Frugt & grønt"),
    make_product(50004, "HVIDLØG", 6.0, underline="3 STK.", department="Frugt & grønt"),
    make_product(
        60001, "HAKKEDE TOMATER", 5.0, underline="400 GR. / REMA 1000", department="Kolonial"
    ),
    make_product(60002, "SPAGHETTI", 9.0, underline="1 KG / REMA 1000", department="Kolonial"),
    make_product(
        60003, "GLUTENFRI SPAGHETTI", 22.0, underline="400 GR. / SCHÄR", department="Kolonial"
    ),
    make_product(70001, "RUGBRØD", 18.0, underline="1 KG / KOHBERG", department="Brød"),
    make_product(99999, "CIGARETTER", 65.0, underline="20 STK.", department="Tobak"),
]


async def fake_search(query: str, limit: int = 24, at: datetime | None = None) -> list[Product]:
    """A small product search over CATALOGUE, like REMA's (word match)."""
    words = [w for w in query.lower().replace(".", " ").split() if len(w) > 1]
    names = {"oksekød": "okse", "kylling": "kylling", "mælk": "mælk"}
    found = []
    for product in CATALOGUE:
        name = product.name.lower()
        if any(w in name or names.get(w, "\0") in name for w in words):
            found.append(product)
    return found[:limit]


def make_list(*items: ShoppingListItem) -> ShoppingList:
    """The primary shopping list."""
    return ShoppingList(id=777, name="Indkøb", items=list(items))


def list_item(
    item_id: int,
    name: str,
    *,
    amount: int = 1,
    bought: bool = False,
    product_id: int | None = None,
    price: float | None = None,
    underline: str | None = None,
    discount: bool = False,
) -> ShoppingListItem:
    """A line on the shopping list."""
    return ShoppingListItem(
        id=item_id,
        name=name,
        bought=bought,
        amount=amount,
        product_id=product_id,
        underline=underline,
        price=price,
        is_on_discount=discount,
    )


CURRENT = Catalog(
    id="cat-42",
    label="Uge 42",
    valid_from=datetime(2026, 10, 10, 22, 0, tzinfo=UTC),
    valid_to=datetime(2026, 10, 17, 21, 59, tzinfo=UTC),
    offer_count=120,
)
UPCOMING = Catalog(
    id="cat-43",
    label="Uge 43",
    valid_from=datetime(2026, 10, 17, 22, 0, tzinfo=UTC),
    valid_to=datetime(2026, 10, 24, 21, 59, tzinfo=UTC),
    offer_count=118,
)
OFFERS = [
    Offer(
        id="o-1",
        heading="Hakket oksekød 8-12%",
        description="500 g\nDansk",
        price=40.0,
        pre_price=50.0,
        quantity="500 g",
        valid_from=None,
        valid_to=None,
    ),
    Offer(
        id="o-2",
        heading="Broccoli",
        description=None,
        price=10.0,
        pre_price=None,
        quantity=None,
        valid_from=None,
        valid_to=None,
    ),
]


@pytest.fixture
def mock_client() -> Generator[MagicMock]:
    """A REMA client that answers like REMA 1000 does."""
    client = MagicMock(spec=RemaClient)
    client.user_id = USER_ID
    client.async_login = AsyncMock(return_value=USER_ID)
    client.async_get_primary_list = AsyncMock(
        return_value=make_list(
            list_item(1, "LETMÆLK 1,5% FEDT", amount=2, product_id=20494, price=10.95,
                      underline="1 LTR. / REMA 1000", discount=True),
            list_item(2, "Kage til Anna"),
            list_item(3, "RUGBRØD", bought=True, product_id=70001, price=18.0),
        )
    )  # fmt: skip
    client.async_add_to_list = AsyncMock()
    client.async_update_item = AsyncMock(return_value={})
    client.async_delete_items = AsyncMock()
    client.async_search_products = AsyncMock(side_effect=fake_search)

    async def search_at(query: str, limit: int, times: list[datetime]) -> list[list[Product]]:
        return [await fake_search(query, limit) for _ in times]

    client.async_search_products_at = AsyncMock(side_effect=search_at)
    client.async_get_favorites = AsyncMock(return_value=CATALOGUE[:3])
    client.async_get_catalogs = AsyncMock(return_value=[CURRENT, UPCOMING])
    client.async_get_offers = AsyncMock(return_value=OFFERS)
    client.async_get_offer_products = AsyncMock(side_effect=lambda offers: offers)
    client.async_get_products = AsyncMock(return_value=[])
    client.async_get_nutrition = AsyncMock(return_value={})
    with (
        patch("custom_components.middagsro.RemaClient", return_value=client),
        patch("custom_components.middagsro.config_flow.RemaClient", return_value=client),
    ):
        yield client


@pytest.fixture
def mock_panel() -> Generator[tuple[AsyncMock, MagicMock]]:
    """Don't serve the panel files in tests (that needs the real frontend)."""
    with (
        patch("custom_components.middagsro.async_register_panel") as register,
        patch("custom_components.middagsro.async_unregister_panel") as unregister,
    ):
        yield register, unregister


@pytest.fixture
def config_entry() -> MockConfigEntry:
    """A REMA 1000 account."""
    return MockConfigEntry(
        domain=DOMAIN,
        title=EMAIL,
        unique_id=str(USER_ID),
        data={CONF_EMAIL: EMAIL, CONF_PASSWORD: PASSWORD},
    )


@pytest.fixture
def ai_task(hass: HomeAssistant) -> str:
    """An AI Task entity the planner can use."""
    hass.states.async_set("ai_task.assistant", "unknown", {"friendly_name": "Assistant"})
    return "ai_task.assistant"


@pytest.fixture
def storage_contents() -> dict[str, Any]:
    """Settings, favourites and plans stored before setup (override per module)."""
    return {}


@pytest.fixture
async def init_integration(
    hass: HomeAssistant,
    hass_storage: dict[str, Any],
    config_entry: MockConfigEntry,
    mock_client: MagicMock,
    mock_panel: tuple[AsyncMock, MagicMock],
    storage_contents: dict[str, Any],
    freezer: Any,
) -> AsyncGenerator[MockConfigEntry]:
    """Set up the integration with one account."""
    freezer.move_to(NOW)
    await hass.config.async_set_time_zone("Europe/Copenhagen")
    config_entry.add_to_hass(hass)
    if storage_contents:
        store_data(hass_storage, config_entry.entry_id, **storage_contents)
    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()
    yield config_entry


def make_plan(
    plan_id: str = "plan-1", start: str = "2026-10-11", status: str = "draft"
) -> dict[str, Any]:
    """A stored meal plan of three days (Sunday to Tuesday after start)."""
    first = datetime.fromisoformat(start).date()
    days = []
    dishes = [
        ("Spaghetti bolognese", "normal", True, None),
        ("Rester af spaghetti bolognese", "rester", False, first.isoformat()),
        ("Kyllingewok med broccoli", "normal", False, None),
    ]
    for offset, (dish, kind, makes, uses) in enumerate(dishes):
        day = first.fromordinal(first.toordinal() + offset)
        days.append(
            {
                "date": day.isoformat(),
                "weekday": "søndag",
                "dish": dish,
                "type": kind,
                "favorite_id": None,
                "uses_leftovers_from": uses,
                "makes_leftovers": makes,
                "servings": 4,
                "active_minutes": 20,
                "total_minutes": 40,
                "ingredients": [{"name": "hakket oksekød", "amount": "500 g"}],
                "steps": [{"text": "Brun kødet.", "minutes": 5}],
                "tip": "Lav dobbelt portion.",
            }
        )
    last = first.fromordinal(first.toordinal() + 2)
    return {
        "id": plan_id,
        "created": "2026-10-10T12:00:00+02:00",
        "start_date": first.isoformat(),
        "end_date": last.isoformat(),
        "week": first.isocalendar().week,
        "status": status,
        "sent_at": None,
        "title": "Madplan uge 42",
        "summary": "Hurtige retter",
        "days": days,
        "shopping": [
            {
                "name": "Hakket oksekød",
                "amount": 500.0,
                "unit": "g",
                "search": "hakket oksekød",
                "category": "Kød",
                "offer": "o0",
                "must_have": False,
                "product_id": None,
                "product": {"id": 30001, "name": "HK. OKSEKØD 8-12%", "underline": "500 GR."},
                "packages": 1,
                "cost": 40.0,
                "note": None,
            },
            {
                "name": "Persille",
                "amount": 1.0,
                "unit": "bundt",
                "search": "persille",
                "category": "Frugt & grønt",
                "offer": None,
                "must_have": False,
                "product_id": None,
                "product": None,
                "packages": 1,
                "cost": None,
                "note": "Ingen sikker vare fundet – tilføjes som fritekst",
            },
            {
                "name": "Spaghetti",
                "amount": 1.0,
                "unit": "pk",
                "search": "spaghetti",
                "category": "Kolonial",
                "offer": None,
                "must_have": False,
                "product_id": None,
                "product": None,
                "packages": 1,
                "cost": None,
                "note": None,
            },
        ],
        "checklist": [{"requirement": "Højst 1 vegetarret", "ok": True}],
        "deviations": "",
        "total": 40.0,
        "budget": 500,
        "catalog": {"id": "cat-42", "label": "Uge 42"},
        "ai_entity": "ai_task.assistant",
    }


def store_data(hass_storage: dict[str, Any], entry_id: str, **data: Any) -> None:
    """Put settings, favourites and plans in the REMA store before setup."""
    key = f"{DOMAIN}.{entry_id}.mealplans"
    hass_storage[key] = {"version": 1, "minor_version": 1, "key": key, "data": data}
