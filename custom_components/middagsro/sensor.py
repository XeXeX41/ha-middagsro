"""Sensors for REMA 1000."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity, SensorStateClass
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.event import async_track_time_change
from homeassistant.util import dt as dt_util

from .api import Catalog
from .coordinator import RemaConfigEntry, RemaOffersCoordinator, RemaShoppingListCoordinator
from .entity import RemaEntity, device_info
from .mealplan import signal_plans_updated
from .suggestions import summary

PARALLEL_UPDATES = 0


async def async_setup_entry(
    hass: HomeAssistant,
    entry: RemaConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the sensors."""
    data = entry.runtime_data
    async_add_entities(
        [
            RemaListTotalSensor(data.shopping_list, entry),
            RemaCatalogSensor(data.offers, entry, "current_catalog"),
            RemaCatalogSensor(data.offers, entry, "upcoming_catalog"),
            RemaMealPlanSensor(data.shopping_list, entry),
            RemaDinnerTodaySensor(entry),
            RemaSuggestionsSensor(entry),
        ]
    )


class RemaDinnerTodaySensor(SensorEntity):
    """Today's dinner from the meal plan (the newest plan wins)."""

    _attr_has_entity_name = True
    _attr_translation_key = "dinner_today"

    def __init__(self, entry: RemaConfigEntry) -> None:
        """Initialize the sensor."""
        self._entry = entry
        self._attr_unique_id = f"{entry.unique_id}_dinner_today"
        self._attr_device_info = device_info(entry)

    def _day(self, offset: int = 0) -> tuple[dict[str, Any], dict[str, Any]] | None:
        """(day, plan) for today + offset days."""
        plan, day = self._entry.runtime_data.store.dinner(
            dt_util.now().date() + timedelta(days=offset)
        )
        return (day, plan) if plan is not None and day is not None else None

    @property
    def native_value(self) -> str | None:
        """The dish, or nothing if today is not planned."""
        found = self._day()
        return str(found[0]["dish"])[:255] if found else None

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Details for dashboards and voice."""
        found = self._day()
        tomorrow = self._day(1)
        attrs: dict[str, Any] = {"tomorrow": tomorrow[0]["dish"] if tomorrow else None}
        if found:
            day, plan = found
            attrs |= {
                "date": day["date"],
                "type": day.get("type"),
                "leftovers": bool(day.get("uses_leftovers_from")),
                "makes_leftovers": bool(day.get("makes_leftovers")),
                "servings": day.get("servings"),
                "active_minutes": day.get("active_minutes"),
                "total_minutes": day.get("total_minutes"),
                "ingredients": [
                    f"{i['amount']} {i['name']}".strip() for i in day.get("ingredients", [])
                ],
                "steps": len(day.get("steps", [])),
                "tip": day.get("tip") or None,
                "plan": plan.get("title"),
            }
        return attrs

    async def async_added_to_hass(self) -> None:
        """Update when plans change and at midnight."""
        await super().async_added_to_hass()
        self.async_on_remove(
            async_dispatcher_connect(
                self.hass, signal_plans_updated(self._entry.entry_id), self._refresh
            )
        )
        self.async_on_remove(
            async_track_time_change(self.hass, self._refresh, hour=0, minute=0, second=5)
        )

    @callback
    def _refresh(self, *_: Any) -> None:
        self.async_write_ha_state()


class RemaMealPlanSensor(RemaEntity[RemaShoppingListCoordinator], SensorEntity):
    """Status of the newest meal plan."""

    _attr_device_class = SensorDeviceClass.ENUM
    _attr_options = ["none", "generating", "error", "draft", "sent"]

    def __init__(self, coordinator: RemaShoppingListCoordinator, entry: RemaConfigEntry) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, entry, "meal_plan")
        self._entry = entry

    @property
    def available(self) -> bool:
        """The plan is stored locally, so it is always available."""
        return True

    @property
    def native_value(self) -> str:
        """Generating/error while working, else the newest plan's status."""
        data = self._entry.runtime_data
        state = str(data.planner.status["state"])
        if state in ("generating", "error"):
            return state
        plan = data.store.latest_plan
        return str(plan["status"]) if plan else "none"

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Describe the newest plan."""
        data = self._entry.runtime_data
        plan = data.store.latest_plan
        attrs: dict[str, Any] = {"message": data.planner.status.get("message")}
        if plan:
            attrs |= {
                "title": plan["title"],
                "start_date": plan["start_date"],
                "end_date": plan["end_date"],
                "total": plan["total"],
                "budget": plan["budget"],
                "over_budget": plan.get("over_budget", False),
                "dinners": {day["date"]: day["dish"] for day in plan["days"]},
            }
        return attrs

    async def async_added_to_hass(self) -> None:
        """Update when plans change."""
        await super().async_added_to_hass()
        self.async_on_remove(
            async_dispatcher_connect(
                self.hass, signal_plans_updated(self._entry.entry_id), self._plans_updated
            )
        )

    @callback
    def _plans_updated(self) -> None:
        self.async_write_ha_state()


class RemaListTotalSensor(RemaEntity[RemaShoppingListCoordinator], SensorEntity):
    """Estimated price of what is left on the list."""

    _attr_device_class = SensorDeviceClass.MONETARY
    _attr_state_class = SensorStateClass.TOTAL
    _attr_native_unit_of_measurement = "DKK"
    _attr_suggested_display_precision = 2

    def __init__(self, coordinator: RemaShoppingListCoordinator, entry: RemaConfigEntry) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, entry, "list_total")

    @property
    def native_value(self) -> float | None:
        """Return the estimated total."""
        return self.coordinator.data.unbought_total if self.coordinator.data else None

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Show how many lines the estimate covers."""
        data = self.coordinator.data
        if not data:
            return None
        open_items = [item for item in data.items if not item.bought]
        return {
            "items": len(open_items),
            "items_without_price": sum(1 for item in open_items if item.price is None),
        }


class RemaCatalogSensor(RemaEntity[RemaOffersCoordinator], SensorEntity):
    """The current or next tilbudsavis. The state is when it starts."""

    _attr_device_class = SensorDeviceClass.TIMESTAMP

    def __init__(
        self, coordinator: RemaOffersCoordinator, entry: RemaConfigEntry, key: str
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, entry, key)
        self._key = key

    @property
    def _catalog(self) -> Catalog | None:
        data = self.coordinator.data
        if not data:
            return None
        return data.current if self._key == "current_catalog" else data.upcoming

    @property
    def native_value(self) -> datetime | None:
        """Return when the avis starts."""
        catalog = self._catalog
        return catalog.valid_from if catalog else None

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Describe the avis."""
        catalog = self._catalog
        if not catalog:
            return None
        return {
            "catalog_id": catalog.id,
            "label": catalog.label,
            "valid_to": catalog.valid_to.isoformat() if catalog.valid_to else None,
            "offer_count": catalog.offer_count,
            "first_seen": self.coordinator.data.first_seen.get(catalog.id),
        }


class RemaSuggestionsSensor(SensorEntity):
    """The week's daily suggestions: how many days still need a dinner picked."""

    _attr_has_entity_name = True
    _attr_translation_key = "daily_suggestions"

    def __init__(self, entry: RemaConfigEntry) -> None:
        """Initialize the sensor."""
        self._entry = entry
        self._attr_unique_id = f"{entry.unique_id}_daily_suggestions"
        self._attr_device_info = device_info(entry)

    @property
    def native_value(self) -> int | None:
        """Days without a picked dinner (None before the first suggestions)."""
        suggestions = self._entry.runtime_data.store.suggestions
        if not suggestions:
            return None
        return sum(1 for day in suggestions["days"] if not day.get("chosen"))

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Each day's three dinners: name, kcal, shop, price and whether it is fish."""
        suggestions = self._entry.runtime_data.store.suggestions
        if not suggestions:
            return None
        return {
            "start_date": suggestions["start_date"],
            "end_date": suggestions["end_date"],
            "plan_id": suggestions.get("plan_id"),
            "days": summary(suggestions),
        }

    async def async_added_to_hass(self) -> None:
        """Update when the suggestions or plans change."""
        await super().async_added_to_hass()
        self.async_on_remove(
            async_dispatcher_connect(
                self.hass, signal_plans_updated(self._entry.entry_id), self._refresh
            )
        )

    @callback
    def _refresh(self, *_: Any) -> None:
        self.async_write_ha_state()
