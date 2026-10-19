"""Buttons to make and send meal plans."""

from __future__ import annotations

from homeassistant.components.button import ButtonEntity
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .api import RemaError
from .const import DOMAIN
from .coordinator import RemaConfigEntry, RemaShoppingListCoordinator
from .entity import RemaEntity
from .suggestions import async_start as async_start_suggestions

PARALLEL_UPDATES = 1


async def async_setup_entry(
    hass: HomeAssistant,
    entry: RemaConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the buttons."""
    coordinator = entry.runtime_data.shopping_list
    async_add_entities(
        [
            RemaMealPlanButton(coordinator, entry, "generate_meal_plan"),
            RemaMealPlanButton(coordinator, entry, "send_meal_plan"),
            RemaMealPlanButton(coordinator, entry, "generate_daily_suggestions"),
        ]
    )


class RemaMealPlanButton(RemaEntity[RemaShoppingListCoordinator], ButtonEntity):
    """Make a new meal plan, or send the newest one to the REMA list."""

    def __init__(
        self, coordinator: RemaShoppingListCoordinator, entry: RemaConfigEntry, key: str
    ) -> None:
        """Initialize the button."""
        super().__init__(coordinator, entry, key)
        self._entry = entry
        self._key = key

    @property
    def available(self) -> bool:
        """Buttons work as long as the integration is loaded."""
        return True

    async def async_press(self) -> None:
        """Handle the press."""
        planner = self._entry.runtime_data.planner
        if self._key == "generate_meal_plan":
            planner.async_start_generation()
            return
        if self._key == "generate_daily_suggestions":
            async_start_suggestions(planner)
            return
        try:
            await planner.async_send()
        except RemaError as err:
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="update_failed",
                translation_placeholders={"error": str(err)},
            ) from err
