"""Changes to a meal plan after it is made.

- Swap one dish for another (the AI suggests three), with its shopping items
  and recipe.
- The basic items (pantry) the recipes use, which are not on the shopping
  list, and putting one on it after all.
- Adding a REMA product found by searching, and removing an added item.
"""

from __future__ import annotations

from datetime import date, datetime
import json
import logging
import re
from typing import Any
import uuid

from homeassistant.exceptions import HomeAssistantError

from .api import Offer, RemaError
from .chains import plan_offer_lines
from .mealie import MealieError
from .mealplan import (
    ALLERGY_DA,
    AVOID_DA,
    WEEKDAYS_DA,
    MealPlanner,
    _failed,
    _household_lines,
    _invalid,
    _tokens,
    late_offers,
    noon,
    nutrition_target,
    packages_needed,
    rule_lines,
    to_base,
)
from .recipes import disliked_names, find_recipe, ingredient_texts, prompt_recipes

_LOGGER = logging.getLogger(__name__)

PANTRY_CATEGORY = "Basisvarer"
EMPTY_TYPE = "tom"  # a day whose dish was deleted; a new one can be chosen
ADDED_CATEGORY = "Tilføjet"
_AMOUNT = re.compile(r"(\d+(?:[.,]\d+)?)\s*(kg|g|gr|ml|dl|cl|l|liter)\b", re.IGNORECASE)


# ------------------------------------------------------------------ helpers


def _plan_and_day(
    planner: MealPlanner, plan_id: str, day_date: str
) -> tuple[dict[str, Any], dict[str, Any]]:
    plan = planner.store.get_plan(plan_id)
    if plan is None:
        raise _invalid("plan_not_found")
    day = next((d for d in plan["days"] if d["date"] == day_date), None)
    if day is None:
        raise _invalid("day_not_found")
    return plan, day


def cooked_day(plan: dict[str, Any], day: dict[str, Any]) -> dict[str, Any]:
    """The day a dish is cooked: for a leftovers day, the day it is from."""
    source = day.get("uses_leftovers_from")
    if not source and day.get("type") != "rester":
        return day
    found = next((d for d in plan["days"] if d["date"] == source), None)
    if found is None:
        found = next(
            (
                d
                for d in reversed(plan["days"])
                if d["date"] < day["date"]
                and not d.get("uses_leftovers_from")
                and d.get("type") != "rester"
            ),
            None,
        )
    return found or day


def update_total(plan: dict[str, Any]) -> None:
    """The plan's price after a change, and whether it is over budget."""
    plan["total"] = round(sum(line.get("cost") or 0 for line in plan["shopping"]), 2)
    budget = plan.get("budget")
    plan["over_budget"] = bool(budget) and plan["total"] > budget


async def _async_offers(planner: MealPlanner, plan: dict[str, Any]) -> list[Offer]:
    """The offers of the avis the plan is built on (none if it can't be read)."""
    catalog = plan.get("catalog") or {}
    if not catalog.get("id"):
        return []
    try:
        return await planner.client.async_get_offers(catalog["id"])
    except RemaError as err:
        _LOGGER.debug("Could not load the offers for the plan: %s", err)
        return []


def _rules(settings: dict[str, Any], weekday: bool) -> list[str]:
    """The family's rules that a dish must follow."""
    out: list[str] = []
    allergies = [ALLERGY_DA[a] for a in settings["allergies"]]
    if settings["allergies_other"].strip():
        allergies.append(settings["allergies_other"].strip())
    if allergies:
        out.append(f"- Allergier – må ALDRIG indgå: {', '.join(allergies)}.")
    avoid = [AVOID_DA[a] for a in settings["avoid"]]
    if settings["avoid_other"].strip():
        avoid.append(settings["avoid_other"].strip())
    if avoid:
        out.append(f"- Undgå helt: {', '.join(avoid)}.")
    if settings["disliked_dishes"]:
        out.append("- Familien kan ikke lide: " + "; ".join(settings["disliked_dishes"]) + ".")
    if weekday:
        out.append(f"- Højst {settings['max_cook_minutes_weekday']} minutters aktiv tilberedning.")
    if settings["wishes"].strip():
        out.append(f"- Ønsker: {settings['wishes'].strip()}")
    out += rule_lines(settings)
    if target := nutrition_target(settings):
        out.append(f"- Næring: {target}.")
    return out


def _offer_lines(offers: list[Offer], when: date, late: dict[int, date]) -> list[str]:
    """The avis's offers that can be bought for a dish on a day, as "o<i> | ..." lines."""
    lines = []
    for idx, offer in enumerate(offers):
        starts = late.get(idx)
        if starts and starts > when:
            continue
        price = f"{offer.price:g} kr." if offer.price is not None else "?"
        lines.append(f"o{idx} | {offer.heading} | {price} | {offer.quantity or ''}".rstrip(" |"))
    return lines


def _describe(line: dict[str, Any]) -> str:
    text = str(line["name"])
    if line.get("amount") and line.get("unit") and line["unit"] != "pk":
        text += f" ({line['amount']:g} {line['unit']})"
    return text


# ------------------------------------------------------------------ swapping


def build_swap_prompt(
    *,
    settings: dict[str, Any],
    plan: dict[str, Any],
    day: dict[str, Any],
    offer_lines: list[str],
    mealie: list[dict[str, Any]] | None = None,
    own: list[dict[str, Any]] | None = None,
    chain_lines: list[str] | None = None,
) -> str:
    """Ask the AI for three other dishes for a day."""
    when = date.fromisoformat(day["date"])
    others = [
        d["dish"]
        for d in plan["days"]
        if d["date"] != day["date"] and d.get("uses_leftovers_from") != day["date"]
    ]
    out = [
        "Du er en erfaren dansk madplanlægger. Familien handler i REMA 1000.",
        (
            f"Familien mangler aftensmad {WEEKDAYS_DA[when.weekday()]} {day['date']}. "
            "Foreslå TRE retter, der er forskellige fra hinanden."
        )
        if day.get("type") == EMPTY_TYPE
        else (
            f"Familien vil skifte aftensmaden {WEEKDAYS_DA[when.weekday()]} {day['date']}: "
            f"{day['dish']}. Foreslå TRE andre retter, der er forskellige fra hinanden."
        ),
        "",
        "HUSSTAND:",
        *_household_lines(settings),
        "",
        "KRAV:",
        *_rules(settings, when.weekday() < 5),
        "- Ikke de andre retter i ugen: " + "; ".join(others) + ".",
    ]
    if day.get("makes_leftovers"):
        out.append("- Retten laves i dobbelt portion; resten spises dagen efter.")
    if day.get("type") == "vegetar":
        out.append("- Gerne en vegetarret, da den gamle var det.")
    if offer_lines:
        out += [
            "",
            "Brug gerne ugens tilbud i REMA 1000 (id | vare | pris | mængde):",
            *offer_lines,
        ]
    if chain_lines:
        out += [
            "",
            "Og ugens tilbud i de andre butikker (id | butik: vare | pris | mængde):",
            *chain_lines,
        ]
    if mealie:
        out += [
            "",
            "Familiens egne opskrifter i Mealie – foreslå gerne dem, der passer (skriv deres id "
            "i mealie, og brug opskriftens navn som dish):",
            *(f"{r['slug']} | {r['name']}" for r in mealie),
        ]
    if own:
        out += [
            "",
            "Fra familiens opskriftssamling (retter de synes om, ❤️ = favorit) – foreslå gerne "
            "en, der passer (skriv dens id i recipe_id, og brug opskriftens navn som dish):",
            *(f"{r['id']} | {'❤️ ' if r['favorite'] else ''}{r['name']}" for r in own),
        ]
    out += [
        "",
        "SVARFORMAT: Svar KUN med gyldig JSON uden markdown, præcis sådan:",
        json.dumps(
            {
                "options": [
                    {
                        "dish": "Kyllingewok med nudler og broccoli",
                        "type": "normal | vegetar",
                        "active_minutes": 20,
                        "total_minutes": 25,
                        "why": "Én kort sætning, fx hvilket tilbud den bruger",
                        "mealie": None,
                        "recipe_id": None,
                    }
                ]
            },
            ensure_ascii=False,
        ),
    ]
    return "\n".join(out)


def build_swap_items_prompt(
    *,
    settings: dict[str, Any],
    plan: dict[str, Any],
    day: dict[str, Any],
    dish: str,
    offer_lines: list[str],
    known_uses: bool,
    ingredients: list[str] | None = None,
    chain_lines: list[str] | None = None,
) -> str:
    """Ask the AI for the shopping items of the new dish."""
    others = [
        d["dish"]
        for d in plan["days"]
        if d["date"] != day["date"]
        and not d.get("uses_leftovers_from")
        and d.get("type") != "rester"
    ]
    servings = int(day.get("servings") or 4)
    out = [
        "Du er en erfaren dansk madplanlægger. Familien handler i REMA 1000.",
        f'Aftensmaden {day["date"]} bliver "{dish}".'
        if day.get("type") == EMPTY_TYPE
        else f'Retten "{day["dish"]}" {day["date"]} skiftes ud med "{dish}".',
        f"Den skal laves til {servings} personer"
        + (" i dobbelt portion (rester dagen efter)." if day.get("makes_leftovers") else "."),
        "",
        "HUSSTAND:",
        *_household_lines(settings),
        "",
        "Indkøbslisten har nu: " + ", ".join(_describe(line) for line in plan["shopping"]) + ".",
        f"Ugens andre retter: {'; '.join(others)}.",
        f"Basisvarer familien har (skal IKKE på listen): {settings['pantry'].strip() or 'salt og peber'}.",
        "",
        "Svar med:",
        "- add: de varer, der skal købes til den nye ret (navn, mængde som tal, enhed g/kg/ml/l "
        "eller pk/stk, søgeord til REMA's varesøgning, kategori og evt. tilbuddets id). Står en "
        "vare allerede på listen, og skal der mere til, så skriv kun den ekstra mængde.",
        "- uses: navnene på ALLE de varer fra listen og fra add, som den nye ret bruger.",
        "Brug de nemmeste hverdagsvarer (hakkede tomater på dåse til kødsovs, ikke friske tomater).",
        *([f"Familiens egen opskrift bruger: {', '.join(ingredients)}."] if ingredients else []),
    ]
    if not known_uses:
        out.append(
            "- remove: navnene på de varer på listen, som KUN blev købt til den gamle ret "
            "(ikke varer, som ugens andre retter også bruger)."
        )
    if offer_lines:
        out += ["", "Ugens tilbud (id | vare | pris | mængde):", *offer_lines]
    if chain_lines:
        out += [
            "",
            "Ugens tilbud i de andre butikker (id | butik: vare | pris | mængde). En vare på "
            "et af dem købes i den butik; varer uden tilbud købes som de andre på listen:",
            *chain_lines,
        ]
    out += [
        "",
        "SVARFORMAT: Svar KUN med gyldig JSON uden markdown, præcis sådan:",
        json.dumps(
            {
                "add": [
                    {
                        "name": "Kyllingebryst",
                        "amount": 600,
                        "unit": "g",
                        "search": "kyllingebryst",
                        "category": "Kød",
                        "offer": "o4",
                    }
                ],
                "uses": ["Kyllingebryst", "Broccoli"],
                "remove": ["Lasagneplader"],
            },
            ensure_ascii=False,
        ),
    ]
    return "\n".join(out)


def _clean_option(raw: Any) -> dict[str, Any] | None:
    if not isinstance(raw, dict) or not str(raw.get("dish") or "").strip():
        return None

    def minutes(value: Any) -> int:
        try:
            return max(0, min(600, int(float(value))))
        except (TypeError, ValueError):
            return 0

    kind = str(raw.get("type") or "normal").strip().lower()
    return {
        "dish": str(raw["dish"]).strip()[:300],
        "type": "vegetar" if kind == "vegetar" else "normal",
        "active_minutes": minutes(raw.get("active_minutes")),
        "total_minutes": minutes(raw.get("total_minutes")),
        "why": str(raw.get("why") or "").strip()[:300],
        "mealie": str(raw["mealie"])[:200] if raw.get("mealie") else None,
        "recipe_id": str(raw["recipe_id"])[:40] if raw.get("recipe_id") else None,
    }


async def _async_mealie_list(planner: MealPlanner) -> list[dict[str, Any]]:
    """The family's recipes in Mealie (names), when the plan should start from them."""
    if not (planner.store.settings["mealie_recipes"] and planner.mealie.available):
        return []
    try:
        return [
            {"slug": r["slug"], "name": r.get("name") or r["slug"]}
            for r in await planner.mealie.async_summaries()
        ][:150]
    except MealieError as err:
        _LOGGER.debug("Could not read the recipes in Mealie: %s", err)
        return []


async def async_swap_options(planner: MealPlanner, plan_id: str, day_date: str) -> dict[str, Any]:
    """Three other dishes for a day (a leftovers day: for the day it is from)."""
    plan, picked = _plan_and_day(planner, plan_id, day_date)
    day = cooked_day(plan, picked)
    if not planner.ai_available():
        raise _invalid("no_ai_task")
    offers = await _async_offers(planner, plan)
    when = date.fromisoformat(day["date"])
    late = late_offers(offers, date.fromisoformat(plan["start_date"]))
    chain_offers = await planner._async_chain_offers(when)
    mealie = await _async_mealie_list(planner)
    recent = [d["dish"] for d in plan["days"]]
    own = prompt_recipes(planner.store, recent)
    prompt = build_swap_prompt(
        settings=_with_dislikes(planner),
        plan=plan,
        day=day,
        offer_lines=_offer_lines(offers, when, late),
        mealie=mealie,
        own=own,
        chain_lines=plan_offer_lines(chain_offers),
    )
    raw = await planner._async_ask_ai(prompt, "REMA 1000 andre retter")
    options = [o for o in (_clean_option(item) for item in raw.get("options") or []) if o][:3]
    known = {r["slug"] for r in mealie}
    ours = {r["id"] for r in own}
    for option in options:
        if option["mealie"] not in known:
            option["mealie"] = None
        if option["recipe_id"] not in ours:
            option["recipe_id"] = None
    if not options:
        raise _failed("swap_failed", error="AI'en kom ikke med nogen forslag")
    return {"plan_id": plan["id"], "date": day["date"], "dish": day["dish"], "options": options}


def _with_dislikes(planner: MealPlanner) -> dict[str, Any]:
    """The settings, with the collection's thumbs-down dishes among the dishes they don't like."""
    settings = planner.store.settings
    return {
        **settings,
        "disliked_dishes": [*settings["disliked_dishes"], *disliked_names(planner.store)],
    }


def _names(items: Any) -> list[str]:
    if not isinstance(items, list):
        return []
    return [str(n).strip()[:200] for n in items if isinstance(n, str) and n.strip()]


async def async_swap_dish(
    planner: MealPlanner, plan_id: str, day_date: str, option: dict[str, Any]
) -> dict[str, Any]:
    """Put another dish on a day: its shopping items, prices and recipe."""
    plan, picked = _plan_and_day(planner, plan_id, day_date)
    day = cooked_day(plan, picked)
    choice = _clean_option(option)
    if choice is None:
        raise _invalid("swap_failed", error="ingen ret valgt")
    if not planner.ai_available():
        raise _invalid("no_ai_task")
    settings = _with_dislikes(planner)
    offers = await _async_offers(planner, plan)
    first = date.fromisoformat(plan["start_date"])
    late = late_offers(offers, first)
    chain_offers = await planner._async_chain_offers(date.fromisoformat(day["date"]))
    cooked = [
        d for d in plan["days"] if not d.get("uses_leftovers_from") and d.get("type") != "rester"
    ]
    # Plans from 0.7.0 know every dish's items: the old dish's own are found here.
    known_uses = day.get("type") == EMPTY_TYPE or (
        bool(day.get("uses")) and all("uses" in d for d in cooked)
    )
    recipe: dict[str, Any] | None = None
    if choice["mealie"]:
        try:
            recipe = await planner.mealie.async_recipe(choice["mealie"])
        except MealieError as err:
            _LOGGER.debug("Could not read %s from Mealie: %s", choice["mealie"], err)
    own = find_recipe(planner.store, choice["recipe_id"])
    if own is None:
        choice["recipe_id"] = None
    elif own["ingredients"]:
        recipe = {"ingredients": ingredient_texts(own)}
    prompt = build_swap_items_prompt(
        settings=settings,
        plan=plan,
        day=day,
        dish=choice["dish"],
        offer_lines=_offer_lines(offers, date.fromisoformat(day["date"]), late),
        known_uses=known_uses,
        ingredients=recipe["ingredients"] if recipe else None,
        chain_lines=plan_offer_lines(chain_offers),
    )
    raw = await planner._async_ask_ai(prompt, "REMA 1000 ny ret")

    # The old dish's own items leave the list (a deleted dish has none left).
    if day.get("type") == EMPTY_TYPE:
        remove: set[str] = set()
    elif known_uses:
        others = {name.lower() for d in cooked if d is not day for name in d.get("uses") or []}
        remove = {n.lower() for n in day.get("uses") or []} - others
    else:
        remove = {n.lower() for n in _names(raw.get("remove"))}
    plan["shopping"] = [
        line
        for line in plan["shopping"]
        if line.get("must_have") or line.get("added") or line["name"].lower() not in remove
    ]

    # The new dish's items: more of one already on the list, or a new line.
    new_lines: list[dict[str, Any]] = []
    for item in raw.get("add") or []:
        line = planner._clean_line(item)
        if line is None:
            continue
        same = next(
            (
                existing
                for existing in plan["shopping"]
                if existing["name"].lower() == line["name"].lower()
                and existing.get("unit") == line["unit"]
                and not existing.get("must_have")
            ),
            None,
        )
        if same is not None and line["amount"]:
            same["amount"] = (same.get("amount") or 0) + line["amount"]
            new_lines.append(same)
            continue
        plan["shopping"].append(line)
        new_lines.append(line)
    await planner._async_price_lines(
        new_lines, offers, planner.price_time(first), late, chain_offers
    )

    day.update(
        dish=choice["dish"],
        type=choice["type"],
        favorite_id=None,
        active_minutes=choice["active_minutes"] or day.get("active_minutes", 0),
        total_minutes=choice["total_minutes"] or day.get("total_minutes", 0),
        uses=_names(raw.get("uses")),
        mealie=choice["mealie"],
        recipe_id=choice["recipe_id"],
    )
    if own is not None:
        own["times_planned"] = own.get("times_planned", 0) + 1
        own["last_planned"] = day["date"]
    update_total(plan)
    await planner._async_recipe(day, plan)
    for leftover in plan["days"]:
        if leftover.get("uses_leftovers_from") == day["date"]:
            leftover["dish"] = f"Rester af {choice['dish'][:1].lower()}{choice['dish'][1:]}"
            await planner._async_recipe(leftover, plan)
    await planner.store.async_save()
    await planner.async_mealie_sync(plan)
    planner._notify()
    if day.get("recipe_error"):
        _LOGGER.warning(
            "The recipe for %s could not be written: %s", day["dish"], day["recipe_error"]
        )
    return plan


# ------------------------------------------------------------------ pantry


def pantry_words(text: str) -> list[str]:
    """The family's basic items: 'salt, peber, olie og smør' -> salt, peber, olie, smør."""
    parts = re.split(r",|;|\n|\bog\b", text, flags=re.IGNORECASE)
    seen: list[str] = []
    for part in parts:
        word = part.strip().lower()
        if word and word not in seen:
            seen.append(word)
    return seen


def _uses_item(item: str, ingredient: str) -> bool:
    """Is a recipe ingredient this basic item? 'rapsolie' is olie; 'mælk' isn't mel."""
    wanted = _tokens(item)
    if not wanted:
        return False
    words = _tokens(ingredient)
    return all(
        any(
            w == want or (len(want) > 2 and w.endswith(want) and len(w) > len(want) + 2)
            for w in words
        )
        for want in wanted
    )


def _sum_amounts(amounts: list[str]) -> tuple[float, str] | None:
    """'25 g' and '50 g' -> 75 g; None if they can't all be added up."""
    total = 0.0
    kind: str | None = None
    for text in amounts:
        match = _AMOUNT.search(text or "")
        if not match:
            return None
        base = to_base(float(match.group(1).replace(",", ".")), match.group(2))
        if base is None or (kind and base[0] != kind):
            return None
        kind = base[0]
        total += base[1]
    if kind is None or total <= 0:
        return None
    return total, kind


def pantry_needs(plan: dict[str, Any], pantry: str) -> list[dict[str, Any]]:
    """The basic items the plan's recipes use (not on the shopping list)."""
    on_list = {
        str(line.get("pantry") or "").lower() for line in plan["shopping"] if line.get("pantry")
    }
    needs = []
    for item in pantry_words(pantry):
        uses = [
            {"date": day["date"], "dish": day["dish"], "name": ing["name"], "amount": ing["amount"]}
            for day in plan["days"]
            for ing in day.get("ingredients") or []
            if _uses_item(item, ing.get("name") or "")
        ]
        if not uses:
            continue
        total = _sum_amounts([u["amount"] for u in uses])
        needs.append(
            {
                "name": item,
                "uses": uses,
                "amount": round(total[0]) if total else None,
                "unit": total[1] if total else None,
                "on_list": item.lower() in on_list,
            }
        )
    return needs


def _new_line(name: str, search: str, category: str, **extra: Any) -> dict[str, Any]:
    return {
        "id": uuid.uuid4().hex[:8],
        "name": name,
        "amount": 1,
        "unit": "pk",
        "search": search,
        "category": category,
        "offer": None,
        "offer_name": None,
        "must_have": False,
        "product_id": None,
        "buy_from": None,
        "added": True,
        **extra,
    }


async def async_add_pantry_item(planner: MealPlanner, plan_id: str, item: str) -> dict[str, Any]:
    """Put a basic item the recipes use on the shopping list, by the family's rules."""
    plan = planner.store.get_plan(plan_id)
    if plan is None:
        raise _invalid("plan_not_found")
    need = next(
        (
            n
            for n in pantry_needs(plan, planner.store.settings["pantry"])
            if n["name"] == item.lower()
        ),
        None,
    )
    if need is None:
        raise _invalid("line_not_found")
    # One recipe calling it something more precise ("hvedemel"): search for that.
    names = {u["name"].strip().lower() for u in need["uses"]}
    search = next(iter(names)) if len(names) == 1 and len(_tokens(next(iter(names)))) == 1 else item
    line = _new_line(item.capitalize(), search, PANTRY_CATEGORY, pantry=item.lower())
    if need["amount"] and need["unit"] in ("g", "ml"):
        line.update(amount=need["amount"], unit=need["unit"])
    await planner._async_match(line, planner.price_time(date.fromisoformat(plan["start_date"])))
    plan["shopping"].append(line)
    update_total(plan)
    await planner.store.async_save()
    planner._notify()
    return line


# ------------------------------------------------------------------ search


async def async_add_product(
    planner: MealPlanner, plan_id: str, product_id: int, amount: int = 1, part: str = "main"
) -> dict[str, Any]:
    """Put a REMA product found by searching on the plan's list (or the late list)."""
    plan = planner.store.get_plan(plan_id)
    if plan is None:
        raise _invalid("plan_not_found")
    buy_from: str | None = None
    if part == "late":
        later = sorted(line["buy_from"] for line in plan["shopping"] if line.get("buy_from"))
        if not later:
            raise _invalid("no_late_list")
        buy_from = later[0]
    first = date.fromisoformat(buy_from or plan["start_date"])
    at: datetime | None = noon(first) if buy_from else planner.price_time(first)
    try:
        products = await planner.client.async_get_products([product_id], at)
    except RemaError as err:
        raise HomeAssistantError(str(err)) from err
    if not products:
        raise _invalid("product_not_found")
    product = products[0]
    packages = max(1, min(99, amount))
    line = _new_line(product.name, product.name, ADDED_CATEGORY, buy_from=buy_from)
    line.update(amount=packages, product_id=product.id)
    planner._apply(line, product, packages)
    plan["shopping"].append(line)
    update_total(plan)
    await planner.store.async_save()
    planner._notify()
    return line


async def async_remove_line(planner: MealPlanner, plan_id: str, line_id: str) -> None:
    """Take an item that was added by hand (or a basic item) off the plan's list."""
    plan = planner.store.get_plan(plan_id)
    if plan is None:
        raise _invalid("plan_not_found")
    kept = [
        line for line in plan["shopping"] if not (line.get("added") and line.get("id") == line_id)
    ]
    if len(kept) == len(plan["shopping"]):
        raise _invalid("line_not_found")
    plan["shopping"] = kept
    update_total(plan)
    await planner.store.async_save()
    planner._notify()


# ------------------------------------------------------------------ days


def _is_cooked(day: dict[str, Any]) -> bool:
    return (
        not day.get("uses_leftovers_from")
        and day.get("type") not in ("rester", EMPTY_TYPE)
        and bool(day.get("dish"))
    )


def _ingredient_lines(plan: dict[str, Any], day: dict[str, Any]) -> set[str]:
    """Shopping lines (ids) a day's recipe uses, by its items or its ingredients' names."""
    lines = [
        line
        for line in plan["shopping"]
        if not line.get("must_have") and not line.get("added") and line.get("id")
    ]
    if "uses" in day:
        wanted = {name.lower() for name in day.get("uses") or []}
        return {line["id"] for line in lines if line["name"].lower() in wanted}
    found: set[str] = set()
    for ing in day.get("ingredients") or []:
        words = set(_tokens(str(ing.get("name") or "")))
        for line in lines:
            name = set(_tokens(line["name"]))
            if name and (name <= words or (words and words <= name)):
                found.add(line["id"])
    return found


def own_lines(plan: dict[str, Any], day: dict[str, Any]) -> set[str]:
    """The shopping lines only this dish uses (not shared with another dish)."""
    others: set[str] = set()
    for other in plan["days"]:
        if other is not day and _is_cooked(other):
            others |= _ingredient_lines(plan, other)
    return _ingredient_lines(plan, day) - others


def _empty(day: dict[str, Any]) -> None:
    day.update(
        dish="",
        type=EMPTY_TYPE,
        favorite_id=None,
        uses_leftovers_from=None,
        makes_leftovers=False,
        active_minutes=0,
        total_minutes=0,
        ingredients=[],
        steps=[],
        tip="",
        uses=[],
        nutrition=None,
        recipe_id=None,
    )
    day.pop("recipe_error", None)


async def async_clear_day(
    planner: MealPlanner, plan_id: str, day_date: str, skip: bool = False
) -> dict[str, Any]:
    """Delete a day's dish (a new one can be chosen later), or skip the day.

    The dish's own items leave the shopping list; its leftovers go with it.
    """
    plan, day = _plan_and_day(planner, plan_id, day_date)
    removed = own_lines(plan, day) if _is_cooked(day) else set()
    plan["shopping"] = [line for line in plan["shopping"] if line.get("id") not in removed]
    for other in plan["days"]:
        if other is not day and other.get("uses_leftovers_from") == day["date"]:
            _empty(other)
    if skip:
        if day.get("mealie_entry"):
            plan.setdefault("skipped_entries", []).append(day["mealie_entry"])
        plan["days"] = [d for d in plan["days"] if d is not day]
        plan["skipped"] = sorted({*(plan.get("skipped") or []), day["date"]})
    else:
        _empty(day)
        day["mealie"] = None
    update_total(plan)
    await planner.store.async_save()
    await planner.async_mealie_sync(plan)
    planner._notify()
    return plan


# ------------------------------------------------------------------ lines


async def async_edit_line(
    planner: MealPlanner,
    plan_id: str,
    line_id: str,
    *,
    delete: bool = False,
    packages: int | None = None,
    product_id: int | None = None,
) -> dict[str, Any]:
    """Delete a shopping line, change how many, or put another REMA product on it.

    A line changed by hand keeps its product: it is not matched again at 02:00.
    """
    plan = planner.store.get_plan(plan_id)
    if plan is None:
        raise _invalid("plan_not_found")
    line = next((item for item in plan["shopping"] if item.get("id") == line_id), None)
    if line is None:
        raise _invalid("line_not_found")
    if delete:
        plan["shopping"] = [item for item in plan["shopping"] if item is not line]
    elif product_id is not None:
        day = line.get("buy_from")
        at = (
            noon(date.fromisoformat(day))
            if day
            else planner.price_time(date.fromisoformat(plan["start_date"]))
        )
        try:
            products = await planner.client.async_get_products([product_id], at)
        except RemaError as err:
            raise HomeAssistantError(str(err)) from err
        if not products:
            raise _invalid("product_not_found")
        product = products[0]
        count = packages or (
            packages_needed(line.get("amount"), line.get("unit"), product)
            if not line.get("added")
            else int(line.get("packages") or 1)
        )
        planner._apply(line, product, max(1, min(99, count)))
        line.update(product_id=product.id, avis_item=None, note=None)
        line.pop("price_source", None)
    elif packages is not None:
        count = max(1, min(99, packages))
        line["packages"] = count
        item = line.get("product") or line.get("avis_item") or {}
        price = item.get("price")
        line["cost"] = round(count * price, 2) if price else None
        if line.get("product"):
            line["product_id"] = line["product"]["id"]  # keep it as chosen
    update_total(plan)
    await planner.store.async_save()
    planner._notify()
    return plan
