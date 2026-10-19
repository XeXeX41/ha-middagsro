"""Websocket commands used by the Middagsro panel."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
import functools
from typing import Any

from homeassistant.components import websocket_api
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.util import dt as dt_util

from .api import Catalog, RemaError
from .chains import (
    CHAINS,
    REMA_ID,
    ChainError,
    async_add_offer,
    async_add_rema_offer,
    async_chain_line,
    async_clear_chain,
    async_compare,
    async_compare_products,
    async_move_line,
    async_search_everywhere,
)
from .const import DOMAIN
from .coordinator import RemaConfigEntry
from .health import plan_health
from .mealplan import parse_date, plan_summary
from .planedit import (
    async_add_pantry_item,
    async_add_product,
    async_clear_day,
    async_edit_line,
    async_remove_line,
    async_swap_dish,
    async_swap_options,
    cooked_day,
    pantry_needs,
)
from .recipes import (
    ACTIONS,
    async_delete_recipe,
    async_import,
    async_rate,
    async_rate_day,
    async_save_recipe,
    find_recipe,
)
from .schema import vol
from .storage import ALLERGY_OPTIONS, AVOID_OPTIONS, FAVORITE_FREQUENCIES
from .suggestions import (
    async_choose as async_choose_suggestion,
    async_dislike as async_dislike_suggestion,
    async_start as async_start_suggestions,
)

ENTRY = vol.Optional("entry_id")

type _Handler = Callable[
    [HomeAssistant, websocket_api.ActiveConnection, dict[str, Any]], Awaitable[None]
]


def _entry(hass: HomeAssistant, msg: dict[str, Any]) -> RemaConfigEntry:
    entries: list[RemaConfigEntry] = hass.config_entries.async_loaded_entries(DOMAIN)
    if entry_id := msg.get("entry_id"):
        entries = [e for e in entries if e.entry_id == entry_id]
    if not entries:
        raise ServiceValidationError(translation_domain=DOMAIN, translation_key="entry_not_found")
    return entries[0]


def _catalog(cat: Catalog | None) -> dict[str, Any] | None:
    if not cat:
        return None
    return {
        "id": cat.id,
        "label": cat.label,
        "valid_from": cat.valid_from.isoformat() if cat.valid_from else None,
        "valid_to": cat.valid_to.isoformat() if cat.valid_to else None,
    }


def _recipe_summary(recipe: dict[str, Any]) -> dict[str, Any]:
    """A recipe in the collection without its ingredients and steps (those come on request)."""
    return {
        key: recipe.get(key)
        for key in (
            "id",
            "name",
            "type",
            "servings",
            "total_minutes",
            "active_minutes",
            "rating",
            "favorite",
            "source",
            "created",
            "times_planned",
            "last_planned",
        )
    } | {"ingredient_names": [i["name"] for i in recipe.get("ingredients") or []][:30]}


def _state(hass: HomeAssistant, entry: RemaConfigEntry) -> dict[str, Any]:
    data = entry.runtime_data
    store = data.store
    offers = data.offers.data
    shopping = data.shopping_list.data

    latest = store.latest_plan
    today = dt_util.now().date()
    current = store.plan_covering(today)
    timeline = store.timeline(today, store.settings["start_weekday"])
    shown = {entry["plan_id"] for entry in timeline}
    return {
        "entry_id": entry.entry_id,
        "title": entry.title,
        "settings": store.settings,
        "favorites": store.favorites,
        "plans": [plan_summary(plan) for plan in store.plans],
        "latest_plan": latest,
        # The plan with tonight's dinner, when it is not the newest one.
        "current_plan": current if current is not latest else None,
        # This week and the coming days as one plan: which plan each date comes from.
        "timeline": timeline,
        "timeline_plans": [
            p for p in store.plans if p["id"] in shown and p is not latest and p is not current
        ],
        "note": store.note,
        "recipes": [_recipe_summary(r) for r in store.recipes],
        "suggestions": store.suggestions,
        "status": data.planner.status,
        "default_start": data.planner.default_start().isoformat(),
        "ai_entities": [
            {"entity_id": state.entity_id, "name": state.name}
            for state in hass.states.async_all("ai_task")
        ],
        "catalogs": {
            "current": _catalog(offers.current) if offers else None,
            "upcoming": _catalog(offers.upcoming) if offers else None,
        },
        "rema_list": {
            "name": shopping.name,
            "items": [
                {"id": i.id, "name": i.name, "amount": i.amount, "bought": i.bought}
                for i in shopping.items
            ],
            "total": shopping.unbought_total,
        }
        if shopping
        else None,
        "mealie": {
            "available": data.planner.mealie.available,
            "url": data.planner.mealie.url,
            "recipes": data.planner.mealie.recipe_url(""),
        },
        "options": {
            "avoid": list(AVOID_OPTIONS),
            "allergies": list(ALLERGY_OPTIONS),
            "frequencies": list(FAVORITE_FREQUENCIES),
        },
    }


def _wrap(handler: _Handler) -> _Handler:
    """Turn errors into websocket error messages."""

    @functools.wraps(handler)
    async def wrapper(
        hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]
    ) -> None:
        try:
            await handler(hass, connection, msg)
        except (HomeAssistantError, RemaError, ValueError) as err:
            connection.send_error(msg["id"], "middagsro_error", str(err))

    return wrapper


@websocket_api.websocket_command(
    {vol.Required("type"): "middagsro/state", ENTRY: str, vol.Optional("refresh"): bool}
)
@websocket_api.async_response
@_wrap
async def ws_state(
    hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]
) -> None:
    """Everything the panel shows; refresh=True fetches the REMA list first."""
    entry = _entry(hass, msg)
    if msg.get("refresh"):
        await entry.runtime_data.shopping_list.async_refresh()
    connection.send_result(msg["id"], _state(hass, entry))


@websocket_api.websocket_command(
    {vol.Required("type"): "middagsro/plan", ENTRY: str, vol.Required("plan_id"): str}
)
@websocket_api.async_response
@_wrap
async def ws_plan(
    hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]
) -> None:
    """One full plan."""
    plan = _entry(hass, msg).runtime_data.store.get_plan(msg["plan_id"])
    if plan is None:
        raise ServiceValidationError(translation_domain=DOMAIN, translation_key="plan_not_found")
    connection.send_result(msg["id"], plan)


@websocket_api.websocket_command(
    {vol.Required("type"): "middagsro/settings", ENTRY: str, vol.Required("settings"): dict}
)
@websocket_api.async_response
@_wrap
async def ws_settings(
    hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]
) -> None:
    """Save settings."""
    entry = _entry(hass, msg)
    settings = await entry.runtime_data.store.async_set_settings(msg["settings"])
    connection.send_result(msg["id"], settings)


@websocket_api.websocket_command(
    {vol.Required("type"): "middagsro/note", ENTRY: str, vol.Required("text"): str}
)
@websocket_api.async_response
@_wrap
async def ws_note(
    hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]
) -> None:
    """Save the family's wishes for the next plan (empty removes them)."""
    store = _entry(hass, msg).runtime_data.store
    connection.send_result(msg["id"], {"note": await store.async_set_note(msg["text"])})


@websocket_api.websocket_command(
    {vol.Required("type"): "middagsro/favorite/save", ENTRY: str, vol.Required("favorite"): dict}
)
@websocket_api.async_response
@_wrap
async def ws_favorite_save(
    hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]
) -> None:
    """Add or change a favourite dish."""
    store = _entry(hass, msg).runtime_data.store
    connection.send_result(msg["id"], await store.async_save_favorite(msg["favorite"]))


@websocket_api.websocket_command(
    {
        vol.Required("type"): "middagsro/favorite/delete",
        ENTRY: str,
        vol.Required("favorite_id"): str,
    }
)
@websocket_api.async_response
@_wrap
async def ws_favorite_delete(
    hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]
) -> None:
    """Delete a favourite dish."""
    await _entry(hass, msg).runtime_data.store.async_delete_favorite(msg["favorite_id"])
    connection.send_result(msg["id"], True)


@websocket_api.websocket_command(
    {
        vol.Required("type"): "middagsro/generate",
        ENTRY: str,
        vol.Optional("start_date"): vol.Any(str, None),
        vol.Optional("skip_dates"): [str],
        vol.Optional("surprise", default=False): bool,
    }
)
@websocket_api.async_response
@_wrap
async def ws_generate(
    hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]
) -> None:
    """Start making a meal plan; skip_dates get no dinner."""
    planner = _entry(hass, msg).runtime_data.planner
    skip = {d for d in (parse_date(v) for v in msg.get("skip_dates") or []) if d}
    planner.async_start_generation(
        parse_date(msg.get("start_date")), skip=skip, surprise=msg["surprise"]
    )
    connection.send_result(msg["id"], planner.status)


@websocket_api.websocket_command(
    {
        vol.Required("type"): "middagsro/send",
        ENTRY: str,
        vol.Optional("plan_id"): vol.Any(str, None),
        vol.Optional("part", default="main"): vol.In(["main", "late", "all"]),
    }
)
@websocket_api.async_response
@_wrap
async def ws_send(
    hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]
) -> None:
    """Send a plan's shopping list to the REMA list."""
    plan = await _entry(hass, msg).runtime_data.planner.async_send(msg.get("plan_id"), msg["part"])
    connection.send_result(msg["id"], {"plan_id": plan["id"], "status": plan["status"]})


@websocket_api.websocket_command(
    {
        vol.Required("type"): "middagsro/recipe",
        ENTRY: str,
        vol.Required("plan_id"): str,
        vol.Required("date"): str,
    }
)
@websocket_api.async_response
@_wrap
async def ws_recipe(
    hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]
) -> None:
    """Write one day's recipe again."""
    planner = _entry(hass, msg).runtime_data.planner
    day = await planner.async_regenerate_recipe(msg["plan_id"], msg["date"])
    connection.send_result(msg["id"], day)


@websocket_api.websocket_command(
    {vol.Required("type"): "middagsro/plan/delete", ENTRY: str, vol.Required("plan_id"): str}
)
@websocket_api.async_response
@_wrap
async def ws_plan_delete(
    hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]
) -> None:
    """Delete a plan from the history."""
    data = _entry(hass, msg).runtime_data
    await data.store.async_delete_plan(msg["plan_id"])
    data.planner._notify()  # the sensors and calendar show the plan before it
    connection.send_result(msg["id"], True)


@websocket_api.websocket_command(
    {vol.Required("type"): "middagsro/search", ENTRY: str, vol.Required("query"): str}
)
@websocket_api.async_response
@_wrap
async def ws_search(
    hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]
) -> None:
    """Search products (used for weekly must-haves)."""
    client = _entry(hass, msg).runtime_data.client
    products = await client.async_search_products(msg["query"], 10)
    connection.send_result(msg["id"], [p.as_dict() for p in products])


@websocket_api.websocket_command(
    {
        vol.Required("type"): "middagsro/favorites",
        ENTRY: str,
        vol.Optional("force"): bool,
        vol.Optional("week", default="current"): vol.In(["current", "next"]),
    }
)
@websocket_api.async_response
@_wrap
async def ws_favorites(
    hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]
) -> None:
    """The account's favourite products, and those on offer this or next week.

    Until next week's avis is out, next week shows this week's offers
    (fallback=True).
    """
    data = _entry(hass, msg).runtime_data
    force = bool(msg.get("force"))
    products = await data.client.async_get_favorites(force=force)
    catalogs = data.offers.data
    current = catalogs.current if catalogs else None
    upcoming = catalogs.upcoming if catalogs else None
    catalog = upcoming if msg["week"] == "next" else current
    fallback = msg["week"] == "next" and upcoming is None
    if fallback:
        catalog = current
    offers = await data.favorite_offers.async_on_offer(products, catalog, force=force)
    connection.send_result(
        msg["id"],
        {
            "week": msg["week"],
            "fallback": fallback,
            "catalog": _catalog(catalog),
            "products": [p.as_dict() for p in products],
            "on_offer": offers,
        },
    )


@websocket_api.websocket_command(
    {
        vol.Required("type"): "middagsro/list/add",
        ENTRY: str,
        vol.Required("product_id"): int,
        vol.Optional("amount", default=1): int,
    }
)
@websocket_api.async_response
@_wrap
async def ws_list_add(
    hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]
) -> None:
    """Add one product to the primary REMA list."""
    coordinator = _entry(hass, msg).runtime_data.shopping_list
    await coordinator.async_add_items(
        [{"product_id": msg["product_id"], "amount": max(1, min(99, msg["amount"]))}]
    )
    connection.send_result(msg["id"], True)


@websocket_api.websocket_command({vol.Required("type"): "middagsro/list/clear", ENTRY: str})
@websocket_api.async_response
@_wrap
async def ws_list_clear(
    hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]
) -> None:
    """Remove everything from the primary REMA list."""
    removed = await _entry(hass, msg).runtime_data.shopping_list.async_clear()
    connection.send_result(msg["id"], {"removed": removed})


@websocket_api.websocket_command(
    {
        vol.Required("type"): "middagsro/swap/options",
        ENTRY: str,
        vol.Required("plan_id"): str,
        vol.Required("date"): str,
    }
)
@websocket_api.async_response
@_wrap
async def ws_swap_options(
    hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]
) -> None:
    """Three other dishes the AI suggests for a day."""
    planner = _entry(hass, msg).runtime_data.planner
    result = await async_swap_options(planner, msg["plan_id"], msg["date"])
    connection.send_result(msg["id"], result)


@websocket_api.websocket_command(
    {
        vol.Required("type"): "middagsro/swap",
        ENTRY: str,
        vol.Required("plan_id"): str,
        vol.Required("date"): str,
        vol.Required("option"): dict,
    }
)
@websocket_api.async_response
@_wrap
async def ws_swap(
    hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]
) -> None:
    """Put the chosen dish on the day, with its shopping and recipe."""
    planner = _entry(hass, msg).runtime_data.planner
    plan = await async_swap_dish(planner, msg["plan_id"], msg["date"], msg["option"])
    connection.send_result(msg["id"], plan)


@websocket_api.websocket_command(
    {vol.Required("type"): "middagsro/pantry", ENTRY: str, vol.Required("plan_id"): str}
)
@websocket_api.async_response
@_wrap
async def ws_pantry(
    hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]
) -> None:
    """The basic items the plan's recipes use, which are not on the shopping list."""
    data = _entry(hass, msg).runtime_data
    plan = data.store.get_plan(msg["plan_id"])
    if plan is None:
        raise ServiceValidationError(translation_domain=DOMAIN, translation_key="plan_not_found")
    connection.send_result(msg["id"], pantry_needs(plan, data.store.settings["pantry"]))


@websocket_api.websocket_command(
    {
        vol.Required("type"): "middagsro/plan/add",
        ENTRY: str,
        vol.Required("plan_id"): str,
        vol.Exclusive("product_id", "what"): int,
        vol.Exclusive("pantry", "what"): str,
        vol.Optional("amount", default=1): int,
        vol.Optional("part", default="main"): vol.In(["main", "late"]),
    }
)
@websocket_api.async_response
@_wrap
async def ws_plan_add(
    hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]
) -> None:
    """Put a searched product, or a basic item the recipes use, on the plan's list."""
    planner = _entry(hass, msg).runtime_data.planner
    if "pantry" in msg:
        line = await async_add_pantry_item(planner, msg["plan_id"], msg["pantry"])
    elif "product_id" in msg:
        line = await async_add_product(
            planner, msg["plan_id"], msg["product_id"], msg["amount"], msg["part"]
        )
    else:
        raise ValueError("product_id or pantry is required")
    connection.send_result(msg["id"], line)


@websocket_api.websocket_command(
    {vol.Required("type"): "middagsro/plan/refresh", ENTRY: str, vol.Required("plan_id"): str}
)
@websocket_api.async_response
@_wrap
async def ws_plan_refresh(
    hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]
) -> None:
    """Match the plan's offer items again with REMA's products and prices now."""
    planner = _entry(hass, msg).runtime_data.planner
    connection.send_result(msg["id"], await planner.async_refresh_offers(msg["plan_id"]))


@websocket_api.websocket_command(
    {
        vol.Required("type"): "middagsro/plan/remove",
        ENTRY: str,
        vol.Required("plan_id"): str,
        vol.Required("line_id"): str,
    }
)
@websocket_api.async_response
@_wrap
async def ws_plan_remove(
    hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]
) -> None:
    """Take an added item off the plan's list."""
    planner = _entry(hass, msg).runtime_data.planner
    await async_remove_line(planner, msg["plan_id"], msg["line_id"])
    connection.send_result(msg["id"], True)


@websocket_api.websocket_command(
    {
        vol.Required("type"): "middagsro/day/clear",
        ENTRY: str,
        vol.Required("plan_id"): str,
        vol.Required("date"): str,
        vol.Optional("skip", default=False): bool,
    }
)
@websocket_api.async_response
@_wrap
async def ws_day_clear(
    hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]
) -> None:
    """Delete a day's dish, or skip the day (no dinner at home)."""
    planner = _entry(hass, msg).runtime_data.planner
    plan = await async_clear_day(planner, msg["plan_id"], msg["date"], skip=msg["skip"])
    connection.send_result(msg["id"], plan)


@websocket_api.websocket_command(
    {
        vol.Required("type"): "middagsro/plan/line",
        ENTRY: str,
        vol.Required("plan_id"): str,
        vol.Required("line_id"): str,
        vol.Optional("delete", default=False): bool,
        vol.Optional("packages"): vol.Any(int, None),
        vol.Optional("product_id"): vol.Any(int, None),
    }
)
@websocket_api.async_response
@_wrap
async def ws_plan_line(
    hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]
) -> None:
    """Delete a shopping item, change how many, or put another product on it."""
    planner = _entry(hass, msg).runtime_data.planner
    plan = await async_edit_line(
        planner,
        msg["plan_id"],
        msg["line_id"],
        delete=msg["delete"],
        packages=msg.get("packages"),
        product_id=msg.get("product_id"),
    )
    connection.send_result(msg["id"], plan)


@websocket_api.websocket_command(
    {
        vol.Required("type"): "middagsro/health",
        ENTRY: str,
        vol.Optional("plan_id"): vol.Any(str, None),
    }
)
@websocket_api.async_response
@_wrap
async def ws_health(
    hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]
) -> None:
    """Nutrition, dietary advice and labels for a plan (the newest by default)."""
    data = _entry(hass, msg).runtime_data
    store = data.store
    plan = store.get_plan(msg["plan_id"]) if msg.get("plan_id") else store.latest_plan
    if plan is None:
        raise ServiceValidationError(translation_domain=DOMAIN, translation_key="no_plan")
    ids = [
        int(line["product"]["id"])
        for line in plan.get("shopping") or []
        if isinstance(line.get("product"), dict) and line["product"].get("id")
    ]
    try:
        table = await data.client.async_get_nutrition(ids)
    except RemaError:
        table = {}
    connection.send_result(msg["id"], plan_health(plan, store.settings, table))


@websocket_api.websocket_command(
    {vol.Required("type"): "middagsro/nutrition", ENTRY: str, vol.Required("product_id"): int}
)
@websocket_api.async_response
@_wrap
async def ws_nutrition(
    hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]
) -> None:
    """REMA's nutrition per 100 g for one product (empty if REMA has none)."""
    client = _entry(hass, msg).runtime_data.client
    table = await client.async_get_nutrition([msg["product_id"]])
    connection.send_result(msg["id"], table.get(msg["product_id"]) or {})


@websocket_api.websocket_command(
    {
        vol.Required("type"): "middagsro/mealie/save",
        ENTRY: str,
        vol.Required("plan_id"): str,
        vol.Required("date"): str,
    }
)
@websocket_api.async_response
@_wrap
async def ws_mealie_save(
    hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]
) -> None:
    """Save a day's recipe in Mealie (and put it in Mealie's calendar, if switched on)."""
    planner = _entry(hass, msg).runtime_data.planner
    plan = planner.store.get_plan(msg["plan_id"])
    day = next((d for d in plan["days"] if d["date"] == msg["date"]), None) if plan else None
    if plan is None or day is None:
        raise ServiceValidationError(translation_domain=DOMAIN, translation_key="day_not_found")
    day = cooked_day(plan, day)
    saved = await planner.mealie.async_save_recipe(day)
    day["mealie"] = saved["slug"]
    await planner.store.async_save()
    await planner.async_mealie_sync(plan)
    connection.send_result(msg["id"], saved)


@websocket_api.websocket_command(
    {vol.Required("type"): "middagsro/mealie/sync", ENTRY: str, vol.Required("plan_id"): str}
)
@websocket_api.async_response
@_wrap
async def ws_mealie_sync(
    hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]
) -> None:
    """Put a plan's dinners in Mealie's calendar now."""
    planner = _entry(hass, msg).runtime_data.planner
    plan = planner.store.get_plan(msg["plan_id"])
    if plan is None:
        raise ServiceValidationError(translation_domain=DOMAIN, translation_key="plan_not_found")
    count = await planner.async_mealie_sync(plan, force=True)
    connection.send_result(msg["id"], {"count": count})


# ------------------------------------------------------------------ recipe collection


@websocket_api.websocket_command(
    {vol.Required("type"): "middagsro/recipes/get", ENTRY: str, vol.Required("recipe_id"): str}
)
@websocket_api.async_response
@_wrap
async def ws_recipe_get(
    hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]
) -> None:
    """One recipe in the collection, with ingredients and steps."""
    store = _entry(hass, msg).runtime_data.store
    recipe = find_recipe(store, msg["recipe_id"])
    if recipe is None:
        raise ServiceValidationError(translation_domain=DOMAIN, translation_key="recipe_not_found")
    connection.send_result(msg["id"], recipe)


@websocket_api.websocket_command(
    {vol.Required("type"): "middagsro/recipes/save", ENTRY: str, vol.Required("recipe"): dict}
)
@websocket_api.async_response
@_wrap
async def ws_recipe_save(
    hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]
) -> None:
    """Add a recipe to the collection, or save changes to one."""
    data = _entry(hass, msg).runtime_data
    recipe = await async_save_recipe(data.store, msg["recipe"])
    data.planner._notify()
    connection.send_result(msg["id"], recipe)


@websocket_api.websocket_command(
    {vol.Required("type"): "middagsro/recipes/delete", ENTRY: str, vol.Required("recipe_id"): str}
)
@websocket_api.async_response
@_wrap
async def ws_recipe_delete(
    hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]
) -> None:
    """Delete a recipe from the collection."""
    data = _entry(hass, msg).runtime_data
    await async_delete_recipe(data.store, msg["recipe_id"])
    data.planner._notify()
    connection.send_result(msg["id"])


@websocket_api.websocket_command(
    {
        vol.Required("type"): "middagsro/recipes/rate",
        ENTRY: str,
        vol.Required("recipe_id"): str,
        vol.Required("action"): vol.In(ACTIONS),
    }
)
@websocket_api.async_response
@_wrap
async def ws_recipe_rate(
    hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]
) -> None:
    """👍, 👎 or ❤️ a recipe (pressing again takes it back)."""
    data = _entry(hass, msg).runtime_data
    recipe = await async_rate(data.store, msg["recipe_id"], msg["action"])
    data.planner._notify()
    connection.send_result(msg["id"], recipe)


@websocket_api.websocket_command(
    {
        vol.Required("type"): "middagsro/recipes/rate_day",
        ENTRY: str,
        vol.Required("plan_id"): str,
        vol.Required("date"): str,
        vol.Required("action"): vol.In(ACTIONS),
    }
)
@websocket_api.async_response
@_wrap
async def ws_recipe_rate_day(
    hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]
) -> None:
    """👍, 👎 or ❤️ a dinner in a plan: it goes in the recipe collection."""
    planner = _entry(hass, msg).runtime_data.planner
    recipe = await async_rate_day(planner, msg["plan_id"], msg["date"], msg["action"])
    connection.send_result(msg["id"], recipe)


@websocket_api.websocket_command(
    {vol.Required("type"): "middagsro/recipes/import", ENTRY: str, vol.Required("url"): str}
)
@websocket_api.async_response
@_wrap
async def ws_recipe_import(
    hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]
) -> None:
    """Read the recipe behind a link; it is saved when the family has looked it over."""
    planner = _entry(hass, msg).runtime_data.planner
    connection.send_result(msg["id"], await async_import(planner, msg["url"]))


@websocket_api.websocket_command(
    {
        vol.Required("type"): "middagsro/recipes/plan",
        ENTRY: str,
        vol.Required("recipe_id"): str,
        vol.Required("plan_id"): str,
        vol.Required("date"): str,
    }
)
@websocket_api.async_response
@_wrap
async def ws_recipe_plan(
    hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]
) -> None:
    """Put a recipe from the collection on a day of a plan (its items go on the list)."""
    planner = _entry(hass, msg).runtime_data.planner
    recipe = find_recipe(planner.store, msg["recipe_id"])
    if recipe is None:
        raise ServiceValidationError(translation_domain=DOMAIN, translation_key="recipe_not_found")
    option = {
        "dish": recipe["name"],
        "type": recipe["type"],
        "active_minutes": recipe["active_minutes"],
        "total_minutes": recipe["total_minutes"],
        "recipe_id": recipe["id"],
    }
    plan = await async_swap_dish(planner, msg["plan_id"], msg["date"], option)
    connection.send_result(msg["id"], plan)


# ------------------------------------------------------------------ other chains


@websocket_api.websocket_command({vol.Required("type"): "middagsro/chains", ENTRY: str})
@websocket_api.async_response
@_wrap
async def ws_chains(
    hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]
) -> None:
    """The chains that can be chosen, with their logos."""
    planner = _entry(hass, msg).runtime_data.planner
    dealers = await planner.chains.async_dealers()
    connection.send_result(msg["id"], {"chains": list(dealers.values())})


@websocket_api.websocket_command(
    {
        vol.Required("type"): "middagsro/chains/offers",
        ENTRY: str,
        vol.Required("dealer_id"): vol.In([REMA_ID, *CHAINS]),
        vol.Optional("force", default=False): bool,
    }
)
@websocket_api.async_response
@_wrap
async def ws_chain_offers(
    hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]
) -> None:
    """A chain's food offers."""
    planner = _entry(hass, msg).runtime_data.planner
    try:
        offers = await planner.chains.async_offers(msg["dealer_id"], msg["force"])
    except ChainError as err:
        raise HomeAssistantError(str(err)) from err
    connection.send_result(msg["id"], {"dealer_id": msg["dealer_id"], "offers": offers})


@websocket_api.websocket_command(
    {vol.Required("type"): "middagsro/chains/compare", ENTRY: str, vol.Required("plan_id"): str}
)
@websocket_api.async_response
@_wrap
async def ws_chain_compare(
    hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]
) -> None:
    """Where the plan's items are cheaper than at REMA this week."""
    planner = _entry(hass, msg).runtime_data.planner
    connection.send_result(msg["id"], await async_compare(planner, msg["plan_id"]))


@websocket_api.websocket_command(
    {
        vol.Required("type"): "middagsro/chains/products",
        ENTRY: str,
        vol.Required("products"): [dict],
        vol.Optional("date"): vol.Any(None, str),
    }
)
@websocket_api.async_response
@_wrap
async def ws_chain_products(
    hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]
) -> None:
    """Which of some REMA products are cheaper in another chain on a day (default today)."""
    planner = _entry(hass, msg).runtime_data.planner
    day = parse_date(msg.get("date")) or dt_util.now().date()
    found = await async_compare_products(planner, msg["products"], day)
    connection.send_result(msg["id"], {"products": found})


@websocket_api.websocket_command(
    {
        vol.Required("type"): "middagsro/chains/move",
        ENTRY: str,
        vol.Required("plan_id"): str,
        vol.Required("line_id"): str,
        vol.Required("dealer_id"): vol.Any(None, vol.In(list(CHAINS))),
        vol.Optional("price"): vol.Any(None, vol.Coerce(float)),
        vol.Optional("heading"): vol.Any(None, str),
    }
)
@websocket_api.async_response
@_wrap
async def ws_chain_move(
    hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]
) -> None:
    """Buy an item in another shop instead (or back at REMA)."""
    planner = _entry(hass, msg).runtime_data.planner
    plan = await async_move_line(
        planner,
        msg["plan_id"],
        msg["line_id"],
        msg["dealer_id"],
        msg.get("price"),
        msg.get("heading"),
    )
    connection.send_result(msg["id"], plan)


@websocket_api.websocket_command(
    {
        vol.Required("type"): "middagsro/chains/add",
        ENTRY: str,
        vol.Required("plan_id"): str,
        vol.Required("offer"): dict,
    }
)
@websocket_api.async_response
@_wrap
async def ws_chain_add(
    hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]
) -> None:
    """Put another chain's offer on that shop's list."""
    planner = _entry(hass, msg).runtime_data.planner
    connection.send_result(msg["id"], await async_add_offer(planner, msg["plan_id"], msg["offer"]))


@websocket_api.websocket_command(
    {
        vol.Required("type"): "middagsro/chains/line",
        ENTRY: str,
        vol.Required("plan_id"): str,
        vol.Required("line_id"): str,
        vol.Optional("bought"): bool,
        vol.Optional("packages"): vol.All(int, vol.Range(min=1, max=99)),
        vol.Optional("delete", default=False): bool,
    }
)
@websocket_api.async_response
@_wrap
async def ws_chain_line(
    hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]
) -> None:
    """Tick off, change how many or delete an item on a shop's list."""
    planner = _entry(hass, msg).runtime_data.planner
    plan = await async_chain_line(
        planner,
        msg["plan_id"],
        msg["line_id"],
        bought=msg.get("bought"),
        packages=msg.get("packages"),
        delete=msg["delete"],
    )
    connection.send_result(msg["id"], plan)


@websocket_api.websocket_command(
    {
        vol.Required("type"): "middagsro/chains/clear",
        ENTRY: str,
        vol.Required("plan_id"): str,
        vol.Required("dealer_id"): vol.In(list(CHAINS)),
    }
)
@websocket_api.async_response
@_wrap
async def ws_chain_clear(
    hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]
) -> None:
    """Empty a shop's basket: the ticked-off items are bought."""
    planner = _entry(hass, msg).runtime_data.planner
    plan = await async_clear_chain(planner, msg["plan_id"], msg["dealer_id"])
    connection.send_result(msg["id"], plan)


@websocket_api.websocket_command(
    {vol.Required("type"): "middagsro/search/everywhere", ENTRY: str, vol.Required("query"): str}
)
@websocket_api.async_response
@_wrap
async def ws_search_everywhere(
    hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]
) -> None:
    """A product at REMA and in the chosen chains' offers, cheapest marked."""
    planner = _entry(hass, msg).runtime_data.planner
    connection.send_result(msg["id"], await async_search_everywhere(planner, msg["query"]))


@websocket_api.websocket_command(
    {
        vol.Required("type"): "middagsro/chains/rema_add",
        ENTRY: str,
        vol.Required("offer"): dict,
        vol.Optional("plan_id"): vol.Any(None, str),
    }
)
@websocket_api.async_response
@_wrap
async def ws_rema_offer_add(
    hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]
) -> None:
    """Put an offer from REMA's avis on the plan's list (or the REMA list)."""
    planner = _entry(hass, msg).runtime_data.planner
    result = await async_add_rema_offer(planner, msg["offer"], msg.get("plan_id"))
    connection.send_result(msg["id"], result)


# ------------------------------------------------------------------ daily suggestions


@websocket_api.websocket_command(
    {
        vol.Required("type"): "middagsro/suggestions/generate",
        ENTRY: str,
        vol.Optional("start_date"): str,
    }
)
@websocket_api.async_response
@_wrap
async def ws_suggestions_generate(
    hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]
) -> None:
    """Start making the week's daily suggestions."""
    planner = _entry(hass, msg).runtime_data.planner
    async_start_suggestions(planner, parse_date(msg.get("start_date")))
    connection.send_result(msg["id"], planner.status)


@websocket_api.websocket_command(
    {
        vol.Required("type"): "middagsro/suggestions/choose",
        ENTRY: str,
        vol.Required("date"): str,
        vol.Optional("option_id"): vol.Any(str, None),
    }
)
@websocket_api.async_response
@_wrap
async def ws_suggestions_choose(
    hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]
) -> None:
    """Pick a day's dinner among its suggestions (or none)."""
    planner = _entry(hass, msg).runtime_data.planner
    plan = await async_choose_suggestion(planner, msg["date"], msg.get("option_id"))
    connection.send_result(msg["id"], plan)


@websocket_api.websocket_command(
    {
        vol.Required("type"): "middagsro/suggestions/dislike",
        ENTRY: str,
        vol.Required("date"): str,
        vol.Required("option_id"): str,
    }
)
@websocket_api.async_response
@_wrap
async def ws_suggestions_dislike(
    hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]
) -> None:
    """👎 on a suggestion: it is removed and never suggested again."""
    planner = _entry(hass, msg).runtime_data.planner
    result = await async_dislike_suggestion(planner, msg["date"], msg["option_id"])
    connection.send_result(msg["id"], result)


@callback
def async_register_websocket(hass: HomeAssistant) -> None:
    """Register the panel's commands."""
    for command in (
        ws_state,
        ws_plan,
        ws_settings,
        ws_note,
        ws_favorite_save,
        ws_favorite_delete,
        ws_generate,
        ws_send,
        ws_recipe,
        ws_plan_delete,
        ws_search,
        ws_favorites,
        ws_list_add,
        ws_list_clear,
        ws_swap_options,
        ws_swap,
        ws_pantry,
        ws_plan_add,
        ws_plan_remove,
        ws_plan_refresh,
        ws_day_clear,
        ws_plan_line,
        ws_health,
        ws_nutrition,
        ws_mealie_save,
        ws_mealie_sync,
        ws_recipe_get,
        ws_recipe_save,
        ws_recipe_delete,
        ws_recipe_rate,
        ws_recipe_rate_day,
        ws_recipe_import,
        ws_recipe_plan,
        ws_chains,
        ws_chain_offers,
        ws_chain_compare,
        ws_chain_products,
        ws_chain_move,
        ws_chain_add,
        ws_chain_line,
        ws_chain_clear,
        ws_search_everywhere,
        ws_rema_offer_add,
        ws_suggestions_generate,
        ws_suggestions_choose,
        ws_suggestions_dislike,
    ):
        websocket_api.async_register_command(hass, command)
