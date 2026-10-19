"""Actions (services) for REMA 1000."""

from __future__ import annotations

from typing import Any

from homeassistant.core import (
    HomeAssistant,
    ServiceCall,
    ServiceResponse,
    SupportsResponse,
    callback,
)
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers import config_validation as cv

from .api import RemaError
from .const import (
    ATTR_AMOUNT,
    ATTR_CATALOG,
    ATTR_CONFIG_ENTRY_ID,
    ATTR_ITEMS,
    ATTR_LIMIT,
    ATTR_NAME,
    ATTR_PRODUCT_ID,
    ATTR_QUERY,
    DOMAIN,
    SERVICE_ADD_ITEMS,
    SERVICE_GENERATE_DAILY_SUGGESTIONS,
    SERVICE_GENERATE_MEAL_PLAN,
    SERVICE_GET_OFFERS,
    SERVICE_SEARCH_PRODUCTS,
    SERVICE_SEND_MEAL_PLAN,
)
from .coordinator import RemaConfigEntry
from .mealplan import parse_date
from .schema import vol
from .suggestions import async_start as async_start_suggestions


def _ensure_list(value: Any) -> list[Any]:
    """Accept a single item as a list of one."""
    if value is None:
        return []
    return value if isinstance(value, list) else [value]


def _product_or_name(value: dict[str, Any]) -> dict[str, Any]:
    """Each item needs a product_id or a name."""
    if not value.get(ATTR_PRODUCT_ID) and not value.get(ATTR_NAME):
        raise vol.Invalid("Each item needs product_id or name")
    return value


_ITEM_SCHEMA = vol.All(
    vol.Schema(
        {
            vol.Optional(ATTR_PRODUCT_ID): vol.Coerce(int),
            vol.Optional(ATTR_NAME): cv.string,
            vol.Optional(ATTR_AMOUNT, default=1): vol.All(
                vol.Coerce(int), vol.Range(min=1, max=99)
            ),
        }
    ),
    _product_or_name,
)

SEARCH_SCHEMA = vol.Schema(
    {
        vol.Optional(ATTR_CONFIG_ENTRY_ID): cv.string,
        vol.Required(ATTR_QUERY): cv.string,
        vol.Optional(ATTR_LIMIT, default=10): vol.All(vol.Coerce(int), vol.Range(min=1, max=100)),
    }
)
ADD_SCHEMA = vol.Schema(
    {
        vol.Optional(ATTR_CONFIG_ENTRY_ID): cv.string,
        vol.Required(ATTR_ITEMS): vol.All(_ensure_list, [_ITEM_SCHEMA]),
    }
)
GENERATE_SCHEMA = vol.Schema(
    {
        vol.Optional(ATTR_CONFIG_ENTRY_ID): cv.string,
        vol.Optional("start_date"): cv.string,
        vol.Optional("send", default=False): cv.boolean,
    }
)
SUGGESTIONS_SCHEMA = vol.Schema(
    {
        vol.Optional(ATTR_CONFIG_ENTRY_ID): cv.string,
        vol.Optional("start_date"): cv.string,
    }
)
SEND_SCHEMA = vol.Schema(
    {
        vol.Optional(ATTR_CONFIG_ENTRY_ID): cv.string,
        vol.Optional("plan_id"): cv.string,
        vol.Optional("part", default="main"): vol.In(["main", "late", "all"]),
    }
)
OFFERS_SCHEMA = vol.Schema(
    {
        vol.Optional(ATTR_CONFIG_ENTRY_ID): cv.string,
        vol.Optional(ATTR_CATALOG, default="current"): vol.In(["current", "upcoming"]),
    }
)


def _get_entry(hass: HomeAssistant, call: ServiceCall) -> RemaConfigEntry:
    """Find the loaded config entry a call is meant for."""
    entries: list[RemaConfigEntry] = hass.config_entries.async_loaded_entries(DOMAIN)
    if entry_id := call.data.get(ATTR_CONFIG_ENTRY_ID):
        for entry in entries:
            if entry.entry_id == entry_id:
                return entry
        raise ServiceValidationError(translation_domain=DOMAIN, translation_key="entry_not_found")
    if len(entries) == 1:
        return entries[0]
    raise ServiceValidationError(
        translation_domain=DOMAIN,
        translation_key="entry_required" if entries else "entry_not_found",
    )


def _error(err: RemaError) -> HomeAssistantError:
    return HomeAssistantError(
        translation_domain=DOMAIN,
        translation_key="update_failed",
        translation_placeholders={"error": str(err)},
    )


@callback
def async_setup_services(hass: HomeAssistant) -> None:
    """Register the REMA 1000 actions."""

    async def search_products(call: ServiceCall) -> ServiceResponse:
        entry = _get_entry(hass, call)
        try:
            products = await entry.runtime_data.client.async_search_products(
                call.data[ATTR_QUERY], call.data[ATTR_LIMIT]
            )
        except RemaError as err:
            raise _error(err) from err
        return {"products": [product.as_dict() for product in products]}

    async def add_items(call: ServiceCall) -> None:
        entry = _get_entry(hass, call)
        items: list[dict[str, Any]] = call.data[ATTR_ITEMS]
        try:
            await entry.runtime_data.shopping_list.async_add_items(items)
        except RemaError as err:
            raise _error(err) from err

    async def get_offers(call: ServiceCall) -> ServiceResponse:
        entry = _get_entry(hass, call)
        data = entry.runtime_data.offers.data
        catalog = None
        if data:
            catalog = data.current if call.data[ATTR_CATALOG] == "current" else data.upcoming
        if catalog is None:
            return {"catalog": None, "offers": []}
        try:
            offers = await entry.runtime_data.client.async_get_offers(catalog.id)
        except RemaError as err:
            raise _error(err) from err
        return {
            "catalog": {
                "id": catalog.id,
                "label": catalog.label,
                "valid_from": catalog.valid_from.isoformat() if catalog.valid_from else None,
                "valid_to": catalog.valid_to.isoformat() if catalog.valid_to else None,
            },
            "offers": [offer.as_dict() for offer in offers],
        }

    hass.services.async_register(
        DOMAIN,
        SERVICE_SEARCH_PRODUCTS,
        search_products,
        schema=SEARCH_SCHEMA,
        supports_response=SupportsResponse.ONLY,
    )
    hass.services.async_register(DOMAIN, SERVICE_ADD_ITEMS, add_items, schema=ADD_SCHEMA)

    async def generate_meal_plan(call: ServiceCall) -> None:
        entry = _get_entry(hass, call)
        entry.runtime_data.planner.async_start_generation(
            parse_date(call.data.get("start_date")), send=call.data["send"]
        )

    async def generate_daily_suggestions(call: ServiceCall) -> None:
        entry = _get_entry(hass, call)
        async_start_suggestions(entry.runtime_data.planner, parse_date(call.data.get("start_date")))

    async def send_meal_plan(call: ServiceCall) -> None:
        entry = _get_entry(hass, call)
        try:
            await entry.runtime_data.planner.async_send(call.data.get("plan_id"), call.data["part"])
        except RemaError as err:
            raise _error(err) from err

    hass.services.async_register(
        DOMAIN, SERVICE_GENERATE_MEAL_PLAN, generate_meal_plan, schema=GENERATE_SCHEMA
    )
    hass.services.async_register(DOMAIN, SERVICE_SEND_MEAL_PLAN, send_meal_plan, schema=SEND_SCHEMA)
    hass.services.async_register(
        DOMAIN,
        SERVICE_GENERATE_DAILY_SUGGESTIONS,
        generate_daily_suggestions,
        schema=SUGGESTIONS_SCHEMA,
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_GET_OFFERS,
        get_offers,
        schema=OFFERS_SCHEMA,
        supports_response=SupportsResponse.ONLY,
    )
