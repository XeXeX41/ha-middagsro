"""Tests for the REMA 1000 entities."""

from __future__ import annotations

from datetime import timedelta
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry, async_fire_time_changed

from custom_components.middagsro.api import RemaError
from custom_components.middagsro.const import DOMAIN
from homeassistant.components.todo import TodoItem, TodoItemStatus
from homeassistant.const import ATTR_ENTITY_ID
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import device_registry as dr, entity_registry as er

from .conftest import NOW, make_plan

LIST_TOTAL = "sensor.middagsro_shopping_list_total"
CURRENT = "sensor.middagsro_current_offer_catalogue"
UPCOMING = "sensor.middagsro_next_offer_catalogue"
MEAL_PLAN = "sensor.middagsro_meal_plan"
DINNER = "sensor.middagsro_dinner_today"
CALENDAR = "calendar.middagsro_meal_plan"
TODO = "todo.middagsro_shopping_list"
QUICK_ADD = "text.middagsro_add_to_shopping_list"
GENERATE = "button.middagsro_make_meal_plan"
SEND = "button.middagsro_send_meal_plan_to_shopping_list"


@pytest.fixture
def storage_contents() -> dict[str, Any]:
    """An older plan and the current one (Tuesday to Thursday)."""
    older = make_plan("plan-0", start="2026-10-12", status="sent")
    older["days"][2]["dish"] = "Fiskefrikadeller"
    return {"plans": [make_plan("plan-1", start="2026-10-13"), older]}


async def test_entities_and_device(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    entity_registry: er.EntityRegistry,
    device_registry: dr.DeviceRegistry,
) -> None:
    """All entities belong to one service device named REMA 1000."""
    entries = er.async_entries_for_config_entry(entity_registry, init_integration.entry_id)
    assert sorted(e.entity_id for e in entries) == sorted(
        [
            LIST_TOTAL,
            CURRENT,
            UPCOMING,
            MEAL_PLAN,
            DINNER,
            CALENDAR,
            TODO,
            QUICK_ADD,
            GENERATE,
            SEND,
            "sensor.middagsro_daily_suggestions",
            "button.middagsro_make_daily_suggestions",
            *(
                f"select.middagsro_dinner_{day}"
                for day in ("mandag", "tirsdag", "onsdag", "torsdag", "fredag", "lordag", "sondag")
            ),
        ]
    )
    device = device_registry.async_get(entries[0].device_id)
    assert device is not None
    assert (DOMAIN, "4242") in device.identifiers
    assert device.name == "Middagsro"
    assert device.entry_type is dr.DeviceEntryType.SERVICE
    assert {e.device_id for e in entries} == {device.id}


async def test_sensors(hass: HomeAssistant, init_integration: MockConfigEntry) -> None:
    """Totals, catalogues and the meal plan."""
    total = hass.states.get(LIST_TOTAL)
    assert float(total.state) == 21.9
    assert total.attributes["unit_of_measurement"] == "DKK"
    assert total.attributes["items"] == 2
    assert total.attributes["items_without_price"] == 1

    current = hass.states.get(CURRENT)
    assert current.state == "2026-10-10T22:00:00+00:00"
    assert current.attributes["catalog_id"] == "cat-42"
    assert current.attributes["offer_count"] == 120
    assert current.attributes["first_seen"] == NOW.isoformat()
    assert hass.states.get(UPCOMING).attributes["label"] == "Uge 43"

    plan = hass.states.get(MEAL_PLAN)
    assert plan.state == "draft"
    assert plan.attributes["title"] == "Madplan uge 42"
    assert plan.attributes["dinners"]["2026-10-15"] == "Kyllingewok med broccoli"
    assert plan.attributes["over_budget"] is False


async def test_meal_plan_sensor_follows_generation(
    hass: HomeAssistant, init_integration: MockConfigEntry
) -> None:
    """While a plan is made, the sensor says so."""
    planner = init_integration.runtime_data.planner
    planner._set_status("generating", "Laver madplan …")
    await hass.async_block_till_done()
    state = hass.states.get(MEAL_PLAN)
    assert state.state == "generating"
    assert state.attributes["message"] == "Laver madplan …"

    planner._set_status("idle")
    await hass.async_block_till_done()
    assert hass.states.get(MEAL_PLAN).state == "draft"


async def test_dinner_today(
    hass: HomeAssistant, init_integration: MockConfigEntry, freezer: Any
) -> None:
    """Today's dish from the newest plan, and the next day at midnight."""
    state = hass.states.get(DINNER)
    assert state.state == "Rester af spaghetti bolognese"
    assert state.attributes["leftovers"] is True
    assert state.attributes["tomorrow"] == "Kyllingewok med broccoli"
    assert state.attributes["ingredients"] == ["500 g hakket oksekød"]
    assert state.attributes["plan"] == "Madplan uge 42"

    freezer.move_to(NOW + timedelta(days=1))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    assert hass.states.get(DINNER).state == "Kyllingewok med broccoli"

    freezer.move_to(NOW + timedelta(days=3))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    state = hass.states.get(DINNER)
    assert state.state == "unknown"
    assert state.attributes["tomorrow"] is None


async def test_calendar(hass: HomeAssistant, init_integration: MockConfigEntry) -> None:
    """One all-day event per dinner; the newest plan wins on the same day."""
    state = hass.states.get(CALENDAR)
    assert state.state == "on"
    assert state.attributes["message"] == "Rester af spaghetti bolognese"

    result = await hass.services.async_call(
        "calendar",
        "get_events",
        {ATTR_ENTITY_ID: CALENDAR, "start_date_time": "2026-10-12 00:00", "duration": {"days": 7}},
        blocking=True,
        return_response=True,
    )
    events = result[CALENDAR]["events"]
    assert [(e["start"], e["summary"]) for e in events] == [
        ("2026-10-12", "Spaghetti bolognese"),
        ("2026-10-13", "Spaghetti bolognese"),
        ("2026-10-14", "Rester af spaghetti bolognese"),
        ("2026-10-15", "Kyllingewok med broccoli"),
    ]
    assert events[0]["description"].startswith("40 min.")
    assert "rester" in events[2]["description"]

    # A day the newest plan skips has no dinner, also not the older plan's.
    newest = init_integration.runtime_data.store.get_plan("plan-1")
    assert newest is not None
    newest["days"] = [d for d in newest["days"] if d["date"] != "2026-10-14"]
    result = await hass.services.async_call(
        "calendar",
        "get_events",
        {ATTR_ENTITY_ID: CALENDAR, "start_date_time": "2026-10-12 00:00", "duration": {"days": 7}},
        blocking=True,
        return_response=True,
    )
    assert [e["start"] for e in result[CALENDAR]["events"]] == [
        "2026-10-12",
        "2026-10-13",
        "2026-10-15",
    ]


async def test_buttons(hass: HomeAssistant, init_integration: MockConfigEntry) -> None:
    """The buttons start a plan and send the newest plan."""
    planner = init_integration.runtime_data.planner
    with patch.object(planner, "async_start_generation") as start:
        await hass.services.async_call("button", "press", {ATTR_ENTITY_ID: GENERATE}, blocking=True)
    start.assert_called_once_with()

    with patch.object(planner, "async_send") as send:
        await hass.services.async_call("button", "press", {ATTR_ENTITY_ID: SEND}, blocking=True)
    send.assert_awaited_once_with()

    with (
        patch.object(planner, "async_send", side_effect=RemaError("HTTP 500")),
        pytest.raises(HomeAssistantError) as err,
    ):
        await hass.services.async_call("button", "press", {ATTR_ENTITY_ID: SEND}, blocking=True)
    assert err.value.translation_key == "update_failed"


async def test_quick_add_text(
    hass: HomeAssistant, init_integration: MockConfigEntry, mock_client: MagicMock
) -> None:
    """Typed text becomes the best product, else a free-text line."""
    await hass.services.async_call(
        "text", "set_value", {ATTR_ENTITY_ID: QUICK_ADD, "value": "tre letmælk"}, blocking=True
    )
    call = mock_client.async_add_to_list.call_args
    assert call.kwargs == {"amount": 3, "product_id": 20494, "name": None}
    state = hass.states.get(QUICK_ADD)
    assert state.state == ""
    assert state.attributes["last_added"] == "3 × LETMÆLK 1,5% FEDT (1 LTR.)"
    assert state.attributes["free_text"] is False

    await hass.services.async_call(
        "text", "set_value", {ATTR_ENTITY_ID: QUICK_ADD, "value": "Kage til Bo"}, blocking=True
    )
    assert mock_client.async_add_to_list.call_args.kwargs == {
        "amount": 1,
        "product_id": None,
        "name": "Kage til Bo",
    }
    assert hass.states.get(QUICK_ADD).attributes["free_text"] is True

    calls = mock_client.async_add_to_list.call_count
    await hass.services.async_call(
        "text", "set_value", {ATTR_ENTITY_ID: QUICK_ADD, "value": "   "}, blocking=True
    )
    assert mock_client.async_add_to_list.call_count == calls

    mock_client.async_add_to_list.side_effect = RemaError("HTTP 500")
    with pytest.raises(HomeAssistantError) as err:
        await hass.services.async_call(
            "text", "set_value", {ATTR_ENTITY_ID: QUICK_ADD, "value": "æg"}, blocking=True
        )
    assert err.value.translation_key == "update_failed"


async def test_shopping_list_items(hass: HomeAssistant, init_integration: MockConfigEntry) -> None:
    """The REMA list as to-do items."""
    assert hass.states.get(TODO).state == "2"
    result = await hass.services.async_call(
        "todo", "get_items", {ATTR_ENTITY_ID: TODO}, blocking=True, return_response=True
    )
    items = result[TODO]["items"]
    assert items[0]["uid"] == "1"
    assert items[0]["summary"] == "2 × LETMÆLK 1,5% FEDT"
    assert items[0]["status"] == TodoItemStatus.NEEDS_ACTION
    assert items[0]["description"] == "1 LTR. / REMA 1000 · 21,90 kr. · Tilbud"
    assert items[1]["summary"] == "Kage til Anna"
    assert "description" not in items[1] or items[1]["description"] is None
    assert items[2]["status"] == TodoItemStatus.COMPLETED
    assert hass.states.get(TODO).attributes["list_name"] == "Indkøb"


async def test_shopping_list_changes(
    hass: HomeAssistant, init_integration: MockConfigEntry, mock_client: MagicMock
) -> None:
    """Add, tick off, change amount, rename and delete lines."""
    await hass.services.async_call(
        "todo", "add_item", {ATTR_ENTITY_ID: TODO, "item": "2 x letmælk"}, blocking=True
    )
    assert mock_client.async_add_to_list.call_args.kwargs["amount"] == 2

    await hass.services.async_call(
        "todo",
        "update_item",
        {ATTR_ENTITY_ID: TODO, "item": "Kage til Anna", "status": "completed"},
        blocking=True,
    )
    mock_client.async_update_item.assert_awaited_with(777, 2, bought=True)

    await hass.services.async_call(
        "todo",
        "update_item",
        {ATTR_ENTITY_ID: TODO, "item": "Kage til Anna", "rename": "3 x Kage til Bo"},
        blocking=True,
    )
    mock_client.async_update_item.assert_awaited_with(777, 2, amount=3, name="Kage til Bo")

    await hass.services.async_call(
        "todo",
        "update_item",
        {ATTR_ENTITY_ID: TODO, "item": "1", "rename": "4 × LETMÆLK 1,5% FEDT"},
        blocking=True,
    )
    mock_client.async_update_item.assert_awaited_with(777, 1, amount=4)

    calls = mock_client.async_update_item.await_count
    await hass.services.async_call(
        "todo",
        "update_item",
        {ATTR_ENTITY_ID: TODO, "item": "1", "status": "needs_action"},
        blocking=True,
    )
    assert mock_client.async_update_item.await_count == calls  # nothing changed

    await hass.services.async_call(
        "todo", "remove_item", {ATTR_ENTITY_ID: TODO, "item": ["Kage til Anna"]}, blocking=True
    )
    mock_client.async_delete_items.assert_awaited_with(777, [2])


async def test_shopping_list_errors(
    hass: HomeAssistant, init_integration: MockConfigEntry, mock_client: MagicMock
) -> None:
    """Errors from REMA are shown to the user."""
    entity = hass.data["todo"].get_entity(TODO)
    with pytest.raises(HomeAssistantError) as err:
        entity._item("999")
    assert err.value.translation_key == "item_not_found"

    mock_client.async_update_item.side_effect = RemaError("HTTP 500")
    with pytest.raises(HomeAssistantError) as err:
        await hass.services.async_call(
            "todo",
            "update_item",
            {ATTR_ENTITY_ID: TODO, "item": "Kage til Anna", "status": "completed"},
            blocking=True,
        )
    assert err.value.translation_key == "update_failed"

    mock_client.async_delete_items.side_effect = RemaError("HTTP 500")
    with pytest.raises(HomeAssistantError):
        await hass.services.async_call(
            "todo", "remove_item", {ATTR_ENTITY_ID: TODO, "item": ["Kage til Anna"]}, blocking=True
        )

    mock_client.async_add_to_list.side_effect = RemaError("HTTP 500")
    with pytest.raises(HomeAssistantError):
        await hass.services.async_call(
            "todo", "add_item", {ATTR_ENTITY_ID: TODO, "item": "æg"}, blocking=True
        )

    entity = hass.data["todo"].get_entity(TODO)
    calls = mock_client.async_add_to_list.call_count
    await entity.async_create_todo_item(TodoItem(summary="  "))
    assert mock_client.async_add_to_list.call_count == calls


async def test_list_becomes_unavailable(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    mock_client: MagicMock,
    freezer: Any,
) -> None:
    """When REMA can't be reached, list entities become unavailable."""
    mock_client.async_get_primary_list.side_effect = RemaError("HTTP 503")
    freezer.tick(timedelta(minutes=3))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    assert hass.states.get(TODO).state == "unavailable"
    assert hass.states.get(LIST_TOTAL).state == "unavailable"
    # Local entities keep working.
    assert hass.states.get(GENERATE).state != "unavailable"
    assert hass.states.get(QUICK_ADD).state != "unavailable"
    assert hass.states.get(MEAL_PLAN).state == "draft"
