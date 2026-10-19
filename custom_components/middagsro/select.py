"""Pick the dinner for each day of the week among the daily suggestions."""

from __future__ import annotations

from typing import Any

from homeassistant.components.select import SelectEntity
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import RemaConfigEntry
from .entity import device_info
from .mealplan import WEEKDAYS_DA, signal_plans_updated
from .suggestions import NOTHING, async_choose, option_label

PARALLEL_UPDATES = 1


async def async_setup_entry(
    hass: HomeAssistant,
    entry: RemaConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """One select per weekday (monday to sunday)."""
    async_add_entities(RemaSuggestionSelect(entry, weekday) for weekday in range(7))


class RemaSuggestionSelect(SelectEntity):
    """The dinner picked for a weekday: one of its three suggestions, or none."""

    _attr_has_entity_name = True
    _attr_translation_key = "suggestion_day"

    def __init__(self, entry: RemaConfigEntry, weekday: int) -> None:
        """Initialize the select."""
        self._entry = entry
        self._weekday = weekday
        self._attr_unique_id = f"{entry.unique_id}_suggestion_{weekday}"
        self._attr_translation_placeholders = {"weekday": WEEKDAYS_DA[weekday]}
        self._attr_device_info = device_info(entry)

    def _day(self) -> dict[str, Any] | None:
        suggestions = self._entry.runtime_data.store.suggestions
        if not suggestions:
            return None
        return next(
            (d for d in suggestions["days"] if WEEKDAYS_DA.index(d["weekday"]) == self._weekday),
            None,
        )

    def _labels(self) -> dict[str, str]:
        """The day's options as select labels (unique) -> their ids."""
        day = self._day()
        labels: dict[str, str] = {}
        for option in day["options"] if day else []:
            label = option_label(option)
            while label in labels:
                label += " ·"
            labels[label] = option["id"]
        return labels

    @property
    def available(self) -> bool:
        """Only while there are suggestions for the day."""
        return self._day() is not None

    @property
    def options(self) -> list[str]:
        """No dinner, or one of the day's suggestions."""
        return [NOTHING, *self._labels()]

    @property
    def current_option(self) -> str | None:
        """The picked dinner."""
        day = self._day()
        chosen = day.get("chosen") if day else None
        return next((label for label, oid in self._labels().items() if oid == chosen), NOTHING)

    async def async_select_option(self, option: str) -> None:
        """Pick the dinner: it goes on the week's plan and its items on the shops' lists."""
        day = self._day()
        if day is None:
            return
        await async_choose(
            self._entry.runtime_data.planner, day["date"], self._labels().get(option)
        )

    async def async_added_to_hass(self) -> None:
        """Update when the suggestions change."""
        await super().async_added_to_hass()
        self.async_on_remove(
            async_dispatcher_connect(
                self.hass, signal_plans_updated(self._entry.entry_id), self._refresh
            )
        )

    @callback
    def _refresh(self, *_: Any) -> None:
        self.async_write_ha_state()
