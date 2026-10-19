"""Daily suggestions: every sunday, three dinners for each day of the coming week.

The family picks one dinner a day. The picks become the week's meal plan, so
Dinner today, the calendar, the shops' own lists and the budget work as for
any plan. Built on the offers of all the chosen chains (REMA 1000, Netto,
Lidl …); an offer that starts later in the week is only used from that day.

Rules: about 500 kcal a portion (the family's nutrition target when it is on),
none of the dishes they gave a thumbs down, their favourites in rotation, and
fish exactly once a week (monday to sunday).
"""

from __future__ import annotations

import copy
from datetime import date, datetime, timedelta
import json
import logging
import re
from typing import TYPE_CHECKING, Any
import uuid

from homeassistant.core import callback
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.util import dt as dt_util

from .chains import REMA_ID, chain_name, plan_offer_lines
from .const import DOMAIN
from .mealie import MealieError
from .mealplan import (
    WEEKDAYS_DA,
    _household_lines,
    _num,
    late_offers,
    plan_dates,
    plan_title,
    plan_week,
)
from .planedit import EMPTY_TYPE, _rules, update_total
from .recipes import (
    MAX_RECIPES,
    apply_rating,
    clean_recipe,
    disliked_names,
    find_by_name,
    prompt_recipes,
)

if TYPE_CHECKING:
    from .api import Offer
    from .mealplan import MealPlanner

_LOGGER = logging.getLogger(__name__)

DAYS = 7  # monday to sunday
OPTIONS = 3  # dinners to choose between each day
DEFAULT_KCAL = 500
KCAL_SLACK = 50  # 450-550 kcal when the family has no nutrition target of their own
MAX_ROUNDS = 2  # first try + one more for the days that are missing dinners
TASK_NAME = "REMA 1000 dagsforslag"
NOTHING = "Intet valgt"

# Words that make a dish a fish dish (fish and shellfish count alike).
_FISH = (
    "fisk", "laks", "torsk", "rødspætte", "makrel", "sild", "ørred", "kuller", "hellefisk",
    "kulmule", "pangasius", "rødfisk", "stenbider", "rejer", "reje", "krabbe", "hummer",
    "muslinger", "skaldyr", "tilapia", "skrubbe", "ising", "pighvar", "havkat", "rogn",
    "tunfisk", "ansjos", "sardin", "scampi", "blæksprutte", "sej",
)  # fmt: skip
_WORD = re.compile(r"[a-zæøåé]+")


def _invalid(key: str, **placeholders: str) -> ServiceValidationError:
    return ServiceValidationError(
        translation_domain=DOMAIN, translation_key=key, translation_placeholders=placeholders
    )


def is_fish(dish: str, flagged: bool = False) -> bool:
    """A fish (or shellfish) dinner: the AI says so, or its name does."""
    if flagged:
        return True
    for word in _WORD.findall(dish.lower()):
        for fish in _FISH:
            # Short names only as whole words ("sej", not "sejt").
            if word == fish or (len(fish) > 3 and fish in word):
                return True
    return False


def kcal_range(settings: dict[str, Any]) -> tuple[int, int]:
    """The kcal a portion may have: the family's target, else about 500."""
    if settings.get("nutrition_enabled"):
        return int(settings["kcal_min"]), int(settings["kcal_max"])
    return DEFAULT_KCAL - KCAL_SLACK, DEFAULT_KCAL + KCAL_SLACK


def next_monday(today: date) -> date:
    """The monday the suggestions are for: tomorrow on a sunday."""
    return today + timedelta(days=7 - today.weekday())


def week_fish(planner: MealPlanner, start: date, skip_plan: str | None = None) -> bool:
    """True if another plan already has fish in the week (monday to sunday)."""
    end = (start + timedelta(days=DAYS - 1)).isoformat()
    seen: set[str] = set()
    for plan in planner.store.plans:  # newest first: a newer plan's day wins
        if plan.get("id") == skip_plan:
            continue
        for day in plan.get("days") or []:
            when = day.get("date") or ""
            if not start.isoformat() <= when <= end or when in seen:
                continue
            seen.add(when)
            if day.get("type") != EMPTY_TYPE and is_fish(
                str(day.get("dish") or ""), bool(day.get("fish"))
            ):
                return True
    return False


# ----------------------------------------------------------------- the AI


def build_suggestions_prompt(
    *,
    settings: dict[str, Any],
    dates: list[date],
    offers: list[Offer],
    late: dict[int, date],
    chain_lines: list[str],
    favorites: list[dict[str, Any]],
    inspiration: list[dict[str, Any]],
    recipes: list[dict[str, Any]],
    mealie: list[dict[str, Any]],
    recent: list[str],
    disliked: list[str],
    fish_needed: bool,
    missing: list[date] | None = None,
) -> str:
    """Ask for three dinners for each day."""
    low, high = kcal_range(settings)
    wanted = missing or dates
    out = [
        "Du er en erfaren dansk madplanlægger. Familien handler i "
        + ", ".join(chain_name(c) for c in settings.get("plan_chains") or [REMA_ID])
        + ".",
        f"Foreslå {OPTIONS} forskellige aftensmåltider til HVER af disse dage: "
        + ", ".join(f"{WEEKDAYS_DA[d.weekday()]} {d.isoformat()}" for d in wanted)
        + ". Familien vælger selv én ret pr. dag.",
        "",
        "HUSSTAND:",
        *_household_lines(settings),
        "",
        "KRAV – SKAL OVERHOLDES:",
        *_rules(settings, True),
        f"- Hver ret skal give {low}-{high} kcal pr. voksenportion; angiv dit skøn i kcal.",
        "- Alle retter i hele ugen skal være forskellige.",
        "- Marker fish: true på retter med fisk eller skaldyr. Højst ét fiskeforslag pr. dag.",
    ]
    if fish_needed:
        last = dates[-1]
        out.append(
            f"- Ugen skal have fisk præcis én gang: {WEEKDAYS_DA[last.weekday()]} "
            f"{last.isoformat()} er sidste chance, så mindst ét af den dags forslag SKAL være "
            "en fiskeret. Andre dage må også have ét fiskeforslag."
        )
    else:
        out.append("- Ugen har allerede fisk: INGEN af forslagene må være med fisk eller skaldyr.")
    if disliked:
        out.append(
            "- Familien kan ikke lide disse retter – brug dem ALDRIG: " + "; ".join(disliked)
        )
    if recent:
        out.append("- Retter fra de seneste uger, som ikke skal gentages: " + "; ".join(recent))
    if settings["pantry"].strip():
        out.append(
            f"- Basisvarer familien altid har (skal IKKE på listen): {settings['pantry'].strip()}."
        )
    out += [
        "",
        "ØNSKER:",
        "- Byg retterne op omkring tilbuddene nedenfor, og marker tilbudsvarer med tilbuddets "
        "id. Et tilbud, der først gælder fra en bestemt dag, må kun bruges den dag eller senere.",
    ]
    if favorites:
        out.append(
            "- Det er disse favoritters tur – hver af dem SKAL være et af forslagene i ugen "
            "(angiv favorite_id):"
        )
        out += [f"  [{f['id']}] {f['text']}" for f in favorites]
    if inspiration:
        out.append(
            '- Flere familiefavoritter – brug dem gerne som forslag (dem markeret "kun på tilbud" '
            "kun, når hovedingrediensen er på tilbud). Angiv favorite_id:"
        )
        out += [
            f"  [{f['id']}] {f['text']}"
            + (" (kun på tilbud)" if f.get("frequency") == "on_offer" else "")
            for f in inspiration
        ]
    if recipes:
        out.append(
            "- Retter fra familiens opskriftssamling, de synes om (angiv recipe_id, hvis du "
            "bruger én):"
        )
        out += [f"  {r['id']} | {r['name']}" for r in recipes]
    if mealie:
        out.append("- Familiens opskrifter i Mealie (angiv mealie, hvis du bruger én):")
        out += [f"  {r['slug']} | {r['name']}" for r in mealie]
    if offers:
        out += ["", "TILBUD I REMA 1000 – id | vare | pris | mængde:"]
        for idx, offer in enumerate(offers):
            price = f"{offer.price:g} kr." if offer.price is not None else "?"
            line = f"o{idx} | {offer.heading} | {price} | {offer.quantity or ''}".rstrip(" |")
            if starts := late.get(idx):
                line += f" | gælder først fra {WEEKDAYS_DA[starts.weekday()]} {starts.isoformat()}"
            out.append(line)
    if chain_lines:
        out += ["", "TILBUD I DE ANDRE BUTIKKER – id | butik: vare | pris | mængde:", *chain_lines]
    out += [
        "",
        "Hvert forslag har sin egen indkøbsliste til netop den ret (navn, mængde som tal, enhed "
        "g/kg/ml/l eller pk/stk, søgeord til REMA 1000's varesøgning, kategori og evt. "
        "tilbuddets id). Udelad basisvarer. Varer, der ikke er på tilbud, får intet id.",
        "",
        "SVARFORMAT: Svar KUN med gyldig JSON uden markdown, præcis sådan:",
        json.dumps(
            {
                "days": [
                    {
                        "date": wanted[0].isoformat(),
                        "options": [
                            {
                                "dish": "Ovnbagt laks med kartofler og broccoli",
                                "type": "normal | vegetar",
                                "fish": True,
                                "kcal": DEFAULT_KCAL,
                                "servings": 4,
                                "active_minutes": 20,
                                "total_minutes": 35,
                                "why": "Laks på tilbud i Lidl",
                                "favorite_id": None,
                                "recipe_id": None,
                                "mealie": None,
                                "shopping": [
                                    {
                                        "name": "Laksefilet",
                                        "amount": 600,
                                        "unit": "g",
                                        "search": "laks",
                                        "category": "Fisk",
                                        "offer": "lidl0",
                                    }
                                ],
                            }
                        ],
                    }
                ]
            },
            ensure_ascii=False,
        ),
        f"days skal have præcis {len(wanted)} elementer i datoorden med {OPTIONS} options hver.",
    ]
    return "\n".join(out)


def clean_option(
    raw: Any, *, low: int, high: int, disliked: set[str], fish_allowed: bool
) -> dict[str, Any] | None:
    """One of the AI's dinners, or None if it breaks a rule (kcal, 👎 or fish)."""
    if not isinstance(raw, dict) or not str(raw.get("dish") or "").strip():
        return None
    dish = " ".join(str(raw["dish"]).split())[:300]
    if dish.lower() in disliked:
        return None  # the family gave it a thumbs down
    kcal = _num(raw.get("kcal"))
    if kcal is None or not low <= kcal <= high:
        return None
    fish = is_fish(dish, raw.get("fish") is True)
    if fish and not fish_allowed:
        return None
    kind = str(raw.get("type") or "normal").strip().lower()
    return {
        "id": uuid.uuid4().hex[:8],
        "dish": dish,
        "type": "vegetar" if kind == "vegetar" else "normal",
        "fish": fish,
        "kcal": round(kcal),
        "servings": int(_num(raw.get("servings"), 4) or 4),
        "active_minutes": int(_num(raw.get("active_minutes"), 0) or 0),
        "total_minutes": int(_num(raw.get("total_minutes"), 0) or 0),
        "why": str(raw.get("why") or "").strip()[:300],
        "favorite_id": str(raw["favorite_id"])[:40] if raw.get("favorite_id") else None,
        "recipe_id": str(raw["recipe_id"])[:40] if raw.get("recipe_id") else None,
        "mealie": str(raw["mealie"])[:200] if raw.get("mealie") else None,
        "shopping": raw.get("shopping") if isinstance(raw.get("shopping"), list) else [],
    }


def pick_options(
    found: dict[str, list[dict[str, Any]]], dates: list[date], fish_needed: bool
) -> dict[str, list[dict[str, Any]]]:
    """Up to three dinners a day: different dishes, one fish a day at most, fish on the last."""
    used: set[str] = set()
    out: dict[str, list[dict[str, Any]]] = {}
    for day in dates:
        key = day.isoformat()
        chosen: list[dict[str, Any]] = []
        candidates = found.get(key) or []
        if fish_needed and day == dates[-1]:
            # The last chance for this week's fish: a fish dinner first.
            candidates = sorted(candidates, key=lambda o: not o["fish"])
        for option in candidates:
            name = option["dish"].lower()
            if name in used or (option["fish"] and any(o["fish"] for o in chosen)):
                continue
            chosen.append(option)
            used.add(name)
            if len(chosen) == OPTIONS:
                break
        out[key] = chosen
    return out


def _missing(
    picked: dict[str, list[dict[str, Any]]], dates: list[date], fish_needed: bool
) -> list[date]:
    """The days that still need dinners (or the last day its fish)."""
    out = [d for d in dates if len(picked.get(d.isoformat()) or []) < OPTIONS]
    last = dates[-1]
    if (
        fish_needed
        and last not in out
        and not any(o["fish"] for o in picked.get(last.isoformat()) or [])
    ):
        out.append(last)
    return out


# ----------------------------------------------------------------- making them


@callback
def async_start(planner: MealPlanner, start: date | None = None) -> None:
    """Make the week's suggestions in the background."""
    if planner.generating:
        raise _invalid("already_generating")
    if not planner.ai_available():
        planner._async_create_ai_issue()
        raise _invalid("no_ai_task")
    start = start or next_monday(dt_util.now().date())
    planner._set_status("generating", "Laver ugens dagsforslag …")
    planner._task = planner.hass.async_create_background_task(
        _async_run(planner, start), name=f"{DOMAIN} daily suggestions"
    )


@callback
def async_sunday(planner: MealPlanner, now: datetime) -> None:
    """Sunday morning: make the coming week's suggestions, unless they are made already."""
    settings = planner.store.settings
    local = dt_util.as_local(now).date()
    if local.weekday() != 6 or not settings["suggestions_auto"]:
        return
    start = next_monday(local)
    current = planner.store.suggestions
    if current and current.get("start_date") == start.isoformat():
        return
    try:
        async_start(planner, start)
    except HomeAssistantError as err:
        _LOGGER.warning("Could not make the daily suggestions for %s: %s", start, err)


async def _async_run(planner: MealPlanner, start: date) -> None:
    try:
        await async_generate(planner, start)
    except Exception as err:
        _LOGGER.exception("Could not make the daily suggestions")
        planner._set_status("error", str(err) or err.__class__.__name__)
    else:
        planner._set_status("idle")


async def async_generate(planner: MealPlanner, start: date) -> dict[str, Any]:
    """Three dinners for each day from monday, priced and stored."""
    store = planner.store
    settings = store.settings
    dates = plan_dates(start, DAYS)
    planner._set_status("generating", "Henter ugens tilbud …")
    catalog, offers = await planner._async_offers(start)
    late = late_offers(offers, start)
    chain_offers = await planner._async_chain_offers(start)
    fish_needed = not week_fish(planner, start)
    low, high = kcal_range(settings)
    disliked = disliked_names(store)
    no = {" ".join(name.lower().split()) for name in [*disliked, *settings["disliked_dishes"]]}
    recent = store.recent_dishes(start, settings["no_repeat_weeks"])
    due, optional = store.favorites_due(start)
    mealie: list[dict[str, Any]] = []
    if settings["mealie_recipes"] and planner.mealie.available:
        try:
            mealie = await planner.mealie.async_prompt_recipes(recent)
        except MealieError as err:
            _LOGGER.warning("Could not read the recipes in Mealie: %s", err)

    found: dict[str, list[dict[str, Any]]] = {}
    picked: dict[str, list[dict[str, Any]]] = {}
    missing: list[date] = dates
    for attempt in range(MAX_ROUNDS):
        planner._set_status(
            "generating", "AI'en finder på retter …" if attempt == 0 else "Finder flere retter …"
        )
        prompt = build_suggestions_prompt(
            settings=settings,
            dates=dates,
            offers=offers,
            late=late,
            chain_lines=plan_offer_lines(chain_offers),
            favorites=due,
            inspiration=optional,
            recipes=prompt_recipes(store, recent),
            mealie=mealie,
            recent=recent,
            disliked=[*settings["disliked_dishes"], *disliked],
            fish_needed=fish_needed,
            missing=missing if attempt else None,
        )
        raw = await planner._async_ask_ai(prompt, TASK_NAME)
        for idx, entry in enumerate(raw.get("days") or []):
            if not isinstance(entry, dict):
                continue
            key = str(entry.get("date") or (missing[idx].isoformat() if idx < len(missing) else ""))
            for item in entry.get("options") or []:
                option = clean_option(
                    item, low=low, high=high, disliked=no, fish_allowed=fish_needed
                )
                if option is not None:
                    found.setdefault(key, []).append(option)
        picked = pick_options(found, dates, fish_needed)
        missing = _missing(picked, dates, fish_needed)
        if not missing:
            break

    planner._set_status("generating", "Finder varer og priser …")
    await _async_price(planner, picked, dates, offers, late, chain_offers)
    extras = await _async_must_haves(planner, offers, start)
    suggestions = {
        "id": uuid.uuid4().hex[:12],
        "created": dt_util.now().isoformat(),
        "start_date": dates[0].isoformat(),
        "end_date": dates[-1].isoformat(),
        "title": plan_title(dates),
        "fish_needed": fish_needed,
        "kcal": [low, high],
        "catalog": {"id": catalog.id, "label": catalog.label} if catalog else None,
        "extras": extras,
        "plan_id": None,
        "days": [
            {
                "date": d.isoformat(),
                "weekday": WEEKDAYS_DA[d.weekday()],
                "options": picked.get(d.isoformat()) or [],
                "chosen": None,
            }
            for d in dates
        ],
        "missing": [d.isoformat() for d in missing],
    }
    store.suggestions = suggestions
    await store.async_save()
    planner._notify()
    return suggestions


async def _async_price(
    planner: MealPlanner,
    picked: dict[str, list[dict[str, Any]]],
    dates: list[date],
    offers: list[Offer],
    late: dict[int, date],
    chain_offers: dict[str, dict[str, Any]],
) -> None:
    """Every dinner's items priced in the shops, and the dinner's price and main shop."""
    lines: list[dict[str, Any]] = []
    for options in picked.values():
        for option in options:
            option["shopping"] = [
                line for line in (planner._clean_line(item) for item in option["shopping"]) if line
            ]
            lines += option["shopping"]
    await planner._async_price_lines(
        lines, offers, planner.price_time(dates[0]), late, chain_offers
    )
    for options in picked.values():
        for option in options:
            option["cost"] = round(sum(line.get("cost") or 0 for line in option["shopping"]), 2)
            by_shop: dict[str, float] = {}
            for line in option["shopping"]:
                shop = line.get("buy_at") or REMA_ID
                by_shop[shop] = by_shop.get(shop, 0) + (line.get("cost") or 0)
            option["chains"] = sorted(by_shop, key=lambda s: -by_shop[s])
            option["chain"] = option["chains"][0] if option["chains"] else REMA_ID


async def _async_must_haves(
    planner: MealPlanner, offers: list[Offer], start: date
) -> list[dict[str, Any]]:
    """The family's weekly REMA items, priced, for the week's list."""
    lines = [
        {
            "name": item["name"],
            "amount": item["amount"],
            "unit": "pk",
            "search": item["name"],
            "category": "Faste varer",
            "offer": None,
            "must_have": True,
            "product_id": item.get("product_id"),
        }
        for item in planner.store.settings["must_haves"]
    ]
    if lines:
        await planner._async_price_lines(lines, offers, planner.price_time(start))
    return lines


# ----------------------------------------------------------------- choosing


def _find(planner: MealPlanner, day_date: str) -> tuple[dict[str, Any], dict[str, Any]]:
    suggestions = planner.store.suggestions
    day = next((d for d in (suggestions or {}).get("days") or [] if d["date"] == day_date), None)
    if suggestions is None or day is None:
        raise _invalid("suggestion_not_found")
    return suggestions, day


async def async_choose(
    planner: MealPlanner, day_date: str, option_id: str | None
) -> dict[str, Any]:
    """Pick a day's dinner (None: no dinner picked). The picks are the week's plan."""
    suggestions, day = _find(planner, day_date)
    option = None
    if option_id:
        option = next((o for o in day["options"] if o["id"] == option_id), None)
        if option is None:
            raise _invalid("suggestion_not_found")
        if option["fish"]:
            other = [
                d["date"]
                for d in suggestions["days"]
                if d is not day and _chosen(d) and _chosen(d)["fish"]  # type: ignore[index]
            ]
            if other or week_fish(planner, date.fromisoformat(suggestions["start_date"]),
                                  suggestions.get("plan_id")):  # fmt: skip
                raise _invalid("one_fish_a_week")
    day["chosen"] = option["id"] if option else None
    plan = await _async_update_plan(planner, suggestions)
    planner._notify()
    if option is not None:
        planner.hass.async_create_background_task(
            _async_recipe(planner, plan["id"], day_date), name=f"{DOMAIN} recipe {day_date}"
        )
    return plan


def _chosen(day: dict[str, Any]) -> dict[str, Any] | None:
    return next((o for o in day["options"] if o["id"] == day.get("chosen")), None)


async def _async_update_plan(planner: MealPlanner, suggestions: dict[str, Any]) -> dict[str, Any]:
    """The week's plan from the picks: their dinners and items (on each shop's list)."""
    store = planner.store
    plan = store.get_plan(suggestions["plan_id"]) if suggestions.get("plan_id") else None
    old_days = {d["date"]: d for d in plan["days"]} if plan else {}
    dates = [date.fromisoformat(d["date"]) for d in suggestions["days"]]
    days: list[dict[str, Any]] = []
    shopping: list[dict[str, Any]] = []
    for entry in suggestions["days"]:
        option = _chosen(entry)
        old = old_days.get(entry["date"])
        if option is None:
            days.append(_empty_day(entry))
            continue
        if old and old.get("suggestion_id") == option["id"]:
            days.append(old)  # same dinner: keep its recipe
        else:
            days.append(_day(entry, option))
        for line in option["shopping"]:
            shopping.append({**copy.deepcopy(line), "id": uuid.uuid4().hex[:8]})
    shopping = _merge(shopping) + [
        {**copy.deepcopy(line), "id": uuid.uuid4().hex[:8]} for line in suggestions["extras"]
    ]
    if plan is None:
        plan = {
            "id": uuid.uuid4().hex[:12],
            "created": dt_util.now().isoformat(),
            "kind": "suggestions",
            "status": "draft",
            "sent_at": None,
            "summary": "Ugens retter, valgt blandt dagsforslagene.",
            "checklist": [],
            "deviations": "",
            "catalog": suggestions.get("catalog"),
            "ai_entity": planner._ai_entity(),
            "note": "",
            "skipped": [],
            "surprise": False,
        }
        suggestions["plan_id"] = plan["id"]
        plan.update(_plan_fields(dates, days, shopping, store.settings["budget"]))
        update_total(plan)
        await store.async_add_plan(plan)
        return plan
    plan.update(_plan_fields(dates, days, shopping, store.settings["budget"]))
    update_total(plan)
    used = {d.get("favorite_id") for d in days if d.get("favorite_id")}
    for fav in store.favorites:
        if fav["id"] in used:
            fav["last_used"] = plan["start_date"]
    await store.async_save()
    return plan


def _plan_fields(
    dates: list[date], days: list[dict[str, Any]], shopping: list[dict[str, Any]], budget: int
) -> dict[str, Any]:
    return {
        "start_date": dates[0].isoformat(),
        "end_date": dates[-1].isoformat(),
        "week": plan_week(dates),
        "title": plan_title(dates),
        "days": days,
        "shopping": shopping,
        "budget": budget,
    }


def _empty_day(entry: dict[str, Any]) -> dict[str, Any]:
    return {
        "date": entry["date"],
        "weekday": entry["weekday"],
        "dish": "",
        "type": EMPTY_TYPE,
        "favorite_id": None,
        "uses_leftovers_from": None,
        "makes_leftovers": False,
        "servings": 0,
        "active_minutes": 0,
        "total_minutes": 0,
        "ingredients": [],
        "steps": [],
        "tip": "",
        "mealie": None,
        "recipe_id": None,
        "uses": [],
    }


def _day(entry: dict[str, Any], option: dict[str, Any]) -> dict[str, Any]:
    return {
        **_empty_day(entry),
        "dish": option["dish"],
        "type": option["type"],
        "fish": option["fish"],
        "favorite_id": option["favorite_id"],
        "servings": option["servings"],
        "active_minutes": option["active_minutes"],
        "total_minutes": option["total_minutes"],
        "mealie": option["mealie"],
        "recipe_id": option["recipe_id"],
        "uses": [line["name"] for line in option["shopping"]],
        "suggestion_id": option["id"],
        "kcal": option["kcal"],
    }


def _merge(lines: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """The same item for several dinners as one line (in the same shop)."""
    out: list[dict[str, Any]] = []
    by_key: dict[tuple[str, str, str], dict[str, Any]] = {}
    for line in lines:
        key = (line["name"].lower(), str(line.get("unit") or ""), str(line.get("buy_at") or ""))
        same = by_key.get(key)
        if same is None:
            by_key[key] = line
            out.append(line)
            continue
        if same.get("amount") is not None and line.get("amount") is not None:
            same["amount"] = same["amount"] + line["amount"]
        same["packages"] = int(same.get("packages") or 1) + int(line.get("packages") or 1)
        same["cost"] = round((same.get("cost") or 0) + (line.get("cost") or 0), 2)
    return out


async def _async_recipe(planner: MealPlanner, plan_id: str, day_date: str) -> None:
    """Write the recipe for a picked dinner (in the background)."""
    plan = planner.store.get_plan(plan_id)
    day = next((d for d in plan["days"] if d["date"] == day_date), None) if plan else None
    if plan is None or day is None or day.get("ingredients") or day.get("type") == EMPTY_TYPE:
        return
    try:
        await planner._async_recipe(day, plan)
    except HomeAssistantError as err:  # pragma: no cover - _async_recipe keeps its errors
        _LOGGER.warning("Could not write the recipe for %s: %s", day_date, err)
    await planner.store.async_save()
    await planner.async_mealie_sync(plan)
    planner._notify()


async def async_dislike(planner: MealPlanner, day_date: str, option_id: str) -> dict[str, Any]:
    """👎 on a suggestion: in the collection as disliked (it never comes back), and gone."""
    suggestions, day = _find(planner, day_date)
    option = next((o for o in day["options"] if o["id"] == option_id), None)
    if option is None:
        raise _invalid("suggestion_not_found")
    store = planner.store
    recipe = find_by_name(store, option["dish"])
    if recipe is None:
        recipe = clean_recipe(
            {
                "name": option["dish"],
                "source": "plan",
                "active_minutes": option["active_minutes"],
                "total_minutes": option["total_minutes"],
            }
        )
        store.recipes.insert(0, recipe)
        del store.recipes[MAX_RECIPES:]
    if recipe["rating"] != "dislike":  # pressing 👎 again would take it back
        apply_rating(recipe, "dislike")
    name = option["dish"].lower()
    for entry in suggestions["days"]:
        entry["options"] = [o for o in entry["options"] if o["dish"].lower() != name]
        if entry.get("chosen") and _chosen(entry) is None:
            entry["chosen"] = None
    if suggestions.get("plan_id"):
        await _async_update_plan(planner, suggestions)
    else:
        await store.async_save()
    planner._notify()
    return suggestions


def option_label(option: dict[str, Any]) -> str:
    """A suggestion as one line for the select: dish, kcal, shop and price."""
    return (
        f"{option['dish']} · {option['kcal']} kcal · {chain_name(option.get('chain') or REMA_ID)}"
        f" · {option.get('cost') or 0:.0f} kr."
    )[:255]


def summary(suggestions: dict[str, Any] | None) -> list[dict[str, Any]]:
    """The suggestions for the sensor: per day, the dinners with kcal, shop, price and fish."""
    if not suggestions:
        return []
    return [
        {
            "date": day["date"],
            "weekday": day["weekday"],
            "chosen": (_chosen(day) or {}).get("dish"),
            "options": [
                {
                    "name": o["dish"],
                    "kcal": o["kcal"],
                    "chain": chain_name(o.get("chain") or REMA_ID),
                    "price": o.get("cost"),
                    "fish": o["fish"],
                }
                for o in day["options"]
            ],
        }
        for day in suggestions["days"]
    ]
