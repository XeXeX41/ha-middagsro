"""Middagsro: meal plans, recipes and REMA 1000 shopping in Home Assistant."""

from __future__ import annotations

from datetime import datetime

from homeassistant.const import CONF_EMAIL, CONF_PASSWORD, Platform
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryNotReady
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.aiohttp_client import async_create_clientsession
from homeassistant.helpers.event import async_track_time_change
from homeassistant.helpers.typing import ConfigType

from .api import Catalog, RemaAuthError, RemaClient, RemaError
from .const import DOMAIN
from .coordinator import (
    RemaConfigEntry,
    RemaOffersCoordinator,
    RemaRuntimeData,
    RemaShoppingListCoordinator,
)
from .favorites import FavoriteOffers
from .mealplan import MealPlanner
from .migrate import async_migrate
from .panel import async_register_panel, async_unregister_panel
from .services import async_setup_services
from .storage import RemaPlanStore
from .suggestions import async_sunday
from .websocket import async_register_websocket

PLATFORMS: list[Platform] = [
    Platform.BUTTON,
    Platform.CALENDAR,
    Platform.SELECT,
    Platform.SENSOR,
    Platform.TEXT,
    Platform.TODO,
]

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Set up the actions and the panel's websocket commands."""
    async_setup_services(hass)
    async_register_websocket(hass)
    return True


async def async_setup_entry(hass: HomeAssistant, entry: RemaConfigEntry) -> bool:
    """Set up Middagsro for a REMA 1000 account."""
    await async_migrate(hass, entry)
    # Own session so the login cookies of this account are kept apart.
    session = async_create_clientsession(hass)
    client = RemaClient(session, entry.data[CONF_EMAIL], entry.data[CONF_PASSWORD])
    try:
        await client.async_login()
    except RemaAuthError as err:
        raise ConfigEntryAuthFailed(
            translation_domain=DOMAIN,
            translation_key="auth_failed",
            translation_placeholders={"email": entry.data[CONF_EMAIL]},
        ) from err
    except RemaError as err:
        raise ConfigEntryNotReady(
            translation_domain=DOMAIN,
            translation_key="cannot_connect",
            translation_placeholders={"error": str(err)},
        ) from err

    store = RemaPlanStore(hass, entry.entry_id)
    await store.async_load()

    shopping_list = RemaShoppingListCoordinator(hass, entry, client)
    offers = RemaOffersCoordinator(hass, entry, client)
    await shopping_list.async_config_entry_first_refresh()
    # Offers come from a third party (Tjek); don't block setup if it fails.
    await offers.async_refresh()

    def catalogs() -> tuple[Catalog | None, Catalog | None]:
        data = offers.data
        return (data.current, data.upcoming) if data else (None, None)

    planner = MealPlanner(
        hass, entry.entry_id, client, store, catalogs, shopping_list.async_add_items
    )
    entry.runtime_data = RemaRuntimeData(
        client=client,
        shopping_list=shopping_list,
        offers=offers,
        store=store,
        planner=planner,
        favorite_offers=FavoriteOffers(client),
    )

    @callback
    def _offers_updated() -> None:
        if offers.data:
            planner.async_check_auto_generate(offers.data.upcoming)

    entry.async_on_unload(offers.async_add_listener(_offers_updated))
    entry.async_on_unload(planner.async_cancel)

    # Every sunday morning: the coming week's daily suggestions (if switched on).
    @callback
    def _sunday(now: datetime) -> None:
        async_sunday(planner, now)

    entry.async_on_unload(async_track_time_change(hass, _sunday, hour=7, minute=0, second=0))
    planner.async_restore_sends()

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    await async_register_panel(hass)
    _offers_updated()
    return True


async def async_unload_entry(hass: HomeAssistant, entry: RemaConfigEntry) -> bool:
    """Unload a config entry."""
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded and not [
        e for e in hass.config_entries.async_loaded_entries(DOMAIN) if e.entry_id != entry.entry_id
    ]:
        async_unregister_panel(hass)
    return unloaded
