"""Meal plans: prompt, AI generation, product matching and sending to REMA."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from datetime import UTC, date, datetime, time as clock_time, timedelta
import json
import logging
import math
import re
from typing import Any
import uuid

from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers import issue_registry as ir
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.helpers.event import async_track_point_in_utc_time
from homeassistant.util import dt as dt_util

from .api import DANISH_TIME, Catalog, Offer, Product, RemaClient, RemaError, parse_time
from .chains import (
    MIN_SAVING,
    REMA_ID,
    ChainError,
    ChainOffers,
    as_offer,
    chain_name,
    plan_offer_lines,
    plan_offers,
)
from .const import DOMAIN
from .mealie import MealieError, MealieLink
from .recipes import (
    disliked_names,
    find_recipe,
    ingredient_texts,
    mark_planned,
    prompt_recipes,
    recipe_to_day,
)
from .storage import RemaPlanStore

_LOGGER = logging.getLogger(__name__)

WEEKDAYS_DA = ("mandag", "tirsdag", "onsdag", "torsdag", "fredag", "lørdag", "søndag")
AVOID_DA = {
    "meat": "kød",
    "pork": "svinekød",
    "beef": "oksekød",
    "fish": "fisk",
    "shellfish": "skaldyr",
    "animal_products": "alle animalske produkter (maden skal være vegansk)",
    "spicy": "stærk mad",
}
ALLERGY_DA = {
    "gluten": "gluten",
    "lactose": "laktose",
    "milk": "mælkeprotein",
    "egg": "æg",
    "nuts": "nødder",
    "peanuts": "jordnødder",
    "soy": "soja",
    "sesame": "sesam",
    "celery": "selleri",
    "mustard": "sennep",
    "fish": "fisk",
    "shellfish": "krebsdyr",
    "molluscs": "bløddyr",
    "lupin": "lupin",
    "sulphites": "sulfitter",
}
# Products REMA sells as "free from" an allergen.
FREE_FROM = {"gluten": "GLUTENFRI", "lactose": "LAKTOSEFRI", "milk": "LAKTOSEFRI"}

ISSUE_NO_AI_TASK = "no_ai_task"
AI_TASK_DOCS_URL = "https://www.home-assistant.io/integrations/ai_task/"

MAX_AI_ROUNDS = 2  # first try + one retry if the list is over budget
RECIPE_CONCURRENCY = 3
SEARCH_CONCURRENCY = 4

_SIZE_MULTI = re.compile(
    r"(\d+)\s*[xX]\s*(\d+(?:[.,]\d+)?)\s*(KG|GR|G|LTR|LITER|L|ML|CL|DL)\b", re.IGNORECASE
)
_SIZE = re.compile(r"(\d+(?:[.,]\d+)?)\s*(KG|GR|G|LTR|LITER|L|ML|CL|DL|STK)\b", re.IGNORECASE)
_UNIT_BASE = {
    "kg": ("g", 1000),
    "gr": ("g", 1),
    "g": ("g", 1),
    "ltr": ("ml", 1000),
    "liter": ("ml", 1000),
    "l": ("ml", 1000),
    "dl": ("ml", 100),
    "cl": ("ml", 10),
    "ml": ("ml", 1),
    "stk": ("stk", 1),
    "stk.": ("stk", 1),
    "pcs": ("stk", 1),
    "pk": ("pack", 1),
    "pakke": ("pack", 1),
    "pakker": ("pack", 1),
    "dåse": ("pack", 1),
    "dåser": ("pack", 1),
    "pose": ("pack", 1),
    "poser": ("pack", 1),
    "bakke": ("pack", 1),
    "bakker": ("pack", 1),
    "flaske": ("pack", 1),
    "flasker": ("pack", 1),
    "glas": ("pack", 1),
}
# REMA abbreviates some words in product names.
_ABBREVIATIONS = {"hk": "hakket", "øko": "økologisk", "økologiske": "økologisk"}
# Extra words that make a product something else than what was asked for.
_DIFFERENT_WORDS = {
    "løse",
    "søde",
    "grønt",
    "grøntsager",
    "blanding",
    "mix",
    "pålæg",
    "marineret",
    "krydret",
    "kryddret",
    "paneret",
    "panerede",
    "røget",
    "gravad",
    "gravet",
    "gravede",
    "citronpeber",
    "chili",
    "sauce",
    "dressing",
    "salat",
    "suppe",
    "juice",
    "snack",
    "chips",
}
# First parts of compound words that make it another product (hvidløg is not løg).
_DIFFERENT_PREFIXES = {
    "hvid", "perle", "hvidløgs", "rød", "forårs", "sukker",
    # kakaomælk, havremælk, kærnemælk … are not mælk
    "kakao", "chokolade", "kokos", "mandel", "havre", "soja", "kærne",
}  # fmt: skip
# Words in product names that say nothing about what the product is.
_NEUTRAL_WORDS = {
    "rema",
    "og",
    "med",
    "i",
    "af",
    "til",
    "en",
    "et",
    "dansk",
    "danske",
    "økologisk",
    "kl",
    "stk",
    "gr",
    "g",
    "kg",
    "ltr",
    "ml",
    "fedt",
    "frisk",
    "friske",
}


def _invalid(key: str, **placeholders: str) -> ServiceValidationError:
    """An error caused by what was asked for, with a translated message."""
    return ServiceValidationError(
        translation_domain=DOMAIN,
        translation_key=key,
        translation_placeholders=placeholders or None,
    )


def _failed(key: str, **placeholders: str) -> HomeAssistantError:
    """An error while doing what was asked, with a translated message."""
    return HomeAssistantError(
        translation_domain=DOMAIN,
        translation_key=key,
        translation_placeholders=placeholders or None,
    )


def signal_plans_updated(entry_id: str) -> str:
    """Dispatcher signal sent when plans or generation status change."""
    return f"{DOMAIN}_{entry_id}_plans_updated"


def next_start(today: date, weekday: int) -> date:
    """The next day (today included) that is the given weekday."""
    return today + timedelta(days=(weekday - today.weekday()) % 7)


def plan_week(dates: list[date]) -> int:
    """The week a plan is named after: the week of its first monday.

    A plan from sunday to saturday follows REMA's avis, which is named after
    the week the monday is in.
    """
    monday = next((d for d in dates if d.weekday() == 0), dates[0])
    return monday.isocalendar().week


def plan_title(dates: list[date]) -> str:
    """The name of a plan, e.g. 'Madplan uge 43'."""
    return f"Madplan uge {plan_week(dates)}"


def late_offers(offers: list[Offer], first_day: date) -> dict[int, date]:
    """Offers that only start after the plan's first day (e.g. thursday): index -> day."""
    late: dict[int, date] = {}
    for idx, offer in enumerate(offers):
        start = parse_time(offer.valid_from)
        if start is None:
            continue
        day = start.astimezone(DANISH_TIME).date()
        if day > first_day:
            late[idx] = day
    return late


def prices_from(day: date) -> datetime:
    """When REMA has a day's products and prices: 00:00 UTC (02:00 danish), plus a margin."""
    return datetime.combine(day, clock_time(0, 5), UTC)


def noon(day: date) -> datetime | None:
    """Noon (danish time) on a day, in UTC, or None if that has passed: then prices are now."""
    moment = dt_util.start_of_local_day(day) + timedelta(hours=12)
    return dt_util.as_utc(moment) if moment > dt_util.now() else None


def to_base(amount: float, unit: str | None) -> tuple[str, float] | None:
    """Convert an amount to grams, millilitres or pieces."""
    if not unit:
        return None
    base = _UNIT_BASE.get(unit.strip().lower())
    if not base:
        return None
    return base[0], amount * base[1]


def package_size(underline: str | None) -> tuple[str, float] | None:
    """Read the package size from REMA's underline, e.g. '500 GR. / REMA 1000'."""
    if not underline:
        return None
    text = underline.split("/")[0]
    if match := _SIZE_MULTI.search(text):
        count = int(match.group(1))
        size = to_base(float(match.group(2).replace(",", ".")), match.group(3))
        return (size[0], size[1] * count) if size else None
    if match := _SIZE.search(text):
        return to_base(float(match.group(1).replace(",", ".")), match.group(2))
    return None


def packages_needed(amount: float | None, unit: str | None, product: Product) -> int:
    """How many packages of a product cover an amount."""
    if not amount or amount <= 0:
        return 1
    need = to_base(amount, unit)
    if need is None:
        return 1
    if need[0] == "pack":  # cans, packs, bags: one package each
        return max(1, min(20, math.ceil(need[1])))
    size = package_size(product.underline)
    if size and need[0] == size[0] and size[1] > 0:
        return max(1, min(20, math.ceil(need[1] / size[1] - 0.05)))
    if need[0] == "stk" and size is None:
        return max(1, min(20, math.ceil(need[1])))  # loose items sold per piece
    return 1  # e.g. 8 pitabrød from one 375 g bag


def avis_packages(amount: float | None, unit: str | None, offer: Offer) -> int:
    """How many of an avis offer's items cover an amount (by the avis's size)."""
    if not amount or amount <= 0:
        return 1
    need = to_base(amount, unit)
    if need is None:
        return 1
    if need[0] == "pack":
        return max(1, min(20, math.ceil(need[1])))
    size = avis_size(offer, need[0])
    if size and size[0] > 0:
        return max(1, min(20, math.ceil(need[1] / size[0] - 0.05)))
    if need[0] == "stk":
        return max(1, min(20, math.ceil(need[1])))
    return 1


_ACCENTS = str.maketrans("éèêëáàâíìîïóòôúùûüç", "eeeeaaaiiiiooouuuuc")


def _tokens(text: str) -> list[str]:
    """Lower-case words of a product name, with REMA's abbreviations expanded."""
    words = re.findall(r"[a-zæøå]+", text.lower().translate(_ACCENTS))
    return [_ABBREVIATIONS.get(w, w) for w in words]


# Words in REMA's underline that say where a product is from, not its brand.
_ORIGINS = {
    "danmark", "dansk", "danske", "land", "kl", "egypten", "spanien", "holland", "italien",
    "norge", "norsk", "tyskland", "frankrig", "sverige", "polen", "marokko", "peru", "chile",
    "portugal", "grækenland", "tyrkiet", "brasilien", "colombia", "ecuador", "costa", "israel",
    "sydafrika", "kenya", "new", "argentina", "mexico", "irland", "belgien", "udenlandsk",
}  # fmt: skip
# Words in an avis heading that describe rather than name a product or brand.
_AVIS_WORDS = _NEUTRAL_WORDS | {
    "eller", "pr", "partivare", "max", "frost", "dybfrost", "ca", "stk", "pak", "nyhed",
    "konventionelle", "økologiske", "udenlandske", "udenlandsk", "fersk", "ferske",
}  # fmt: skip
_PERCENT = re.compile(r"(\d+(?:[.,]\d+)?(?:\s*-\s*\d+(?:[.,]\d+)?)?)\s*%")
_RANGE = re.compile(
    r"(\d+(?:[.,]\d+)?)\s*(?:-\s*(\d+(?:[.,]\d+)?))?\s*(KG|GR|G|LTR|LITER|L|ML|CL|DL|STK)\b",
    re.IGNORECASE,
)


def _stem(word: str) -> str:
    """A word without its Danish plural/definite ending, to compare names."""
    for ending in ("erne", "ene", "er", "e", "r"):
        if word.endswith(ending) and len(word) - len(ending) >= 4:
            return word[: -len(ending)]
    return word


def _name_words(text: str) -> set[str]:
    return {_stem(w) for w in _tokens(text) if len(w) > 1 and w not in _NEUTRAL_WORDS}


def _brand(underline: str | None) -> str | None:
    """The brand in REMA's underline ('500 GR. / KAROLINES KØKKEN' -> karolines)."""
    if not underline or "/" not in underline:
        return None
    words = _tokens(underline.split("/", 1)[1])
    if not words or words[0] in _ORIGINS or words[0] == "økologisk":
        return None
    return words[0]


_LIMIT = re.compile(r"(?:max\.?|flere end)\s*\d+\s*(?:stk|pk|ks)\.?", re.IGNORECASE)


def avis_size(offer: Offer, kind: str) -> tuple[float, float] | None:
    """The size range of one kind (g, ml or stk) an avis offer is for.

    "Max 6 stk." and "ved køb af flere end 6 stk." are limits, not sizes.
    """
    text = _LIMIT.sub(" ", f"{offer.description or ''} {offer.quantity or ''}")
    found: list[tuple[float, float]] = []
    for low, high, unit in _RANGE.findall(text):
        a = to_base(float(low.replace(",", ".")), unit)
        b = to_base(float((high or low).replace(",", ".")), unit)
        if a and b and a[0] == kind:
            found.append((a[1], b[1]))
    if not found:
        return None
    return min(f[0] for f in found), max(f[1] for f in found)


def _percents(text: str) -> set[str]:
    return {re.sub(r"\s+", "", p).replace(",", ".") for p in _PERCENT.findall(text)}


def avis_match(name: str, underline: str | None, organic: bool, offer: Offer) -> bool:
    """Is a REMA product the very product an avis offer is for?

    Strict, because a wrong match puts a wrong price on the list:
    - every word of the product's name is in the offer's heading (a compound
      like "rugbrød" for "brød" only when the offer names the product's brand;
      any variety when the heading is just the product's name, "Kærgården"),
    - unless the heading names the product's brand, the product's part of it
      ("X, Y eller Z") names nothing the product isn't (another brand, another
      variety),
    - the size is within the offer's size or range,
    - fat percentages (8-12%) are the same,
    - organic matches organic.
    """
    return _avis_name_fits(name, underline, offer) and _avis_details_fit(
        name, underline, organic, offer
    )


def _avis_name_fits(name: str, underline: str | None, offer: Offer) -> bool:
    heading = _tokens(offer.heading)
    heading_words = {_stem(w) for w in heading if len(w) > 1}
    brand = _brand(underline)
    # REMA's underline has the brand after the size, but often a variety
    # instead ("200 GR. / LET"): only a brand the heading names counts.
    branded = bool(brand and brand != "rema" and brand in heading)
    words = _name_words(name)
    if not words:
        return False
    named = [w for w in heading if len(w) > 2 and w not in _AVIS_WORDS]
    first = _name_words(_tokens(name)[0]) if _tokens(name) else set()
    if len(named) == 1 and {_stem(named[0])} == first and _same_size(underline, offer):
        # "Kærgården" (200 g): the whole line of the product, any variety.
        # Only with the same kind of size: "Æbler" (1 stk.) is no apple juice.
        words = first
    for word in words:
        # "rugbrød" in "Schulstad Det Gode brød": the offer is for the brand's range.
        if word not in heading_words and not (
            branded and any(len(h) > 3 and word.endswith(h) for h in heading_words)
        ):
            return False
    if branded:
        return True
    parts = re.split(r",|\beller\b", offer.heading, flags=re.IGNORECASE)
    own = max(parts, key=lambda part: len(words & _name_words(part)))
    if heading and heading[0] != "rema":
        # "Lotus Premium Toiletpapir eller køkkenruller": the brand in front
        # is for every part, so not REMA's own køkkenruller.
        own = f"{' '.join(_tokens(parts[0])[:-1])} {own}"
    return not any(
        len(w) > 2 and w not in _AVIS_WORDS and _stem(w) not in words for w in _tokens(own)
    )


def _same_size(underline: str | None, offer: Offer) -> bool:
    """The product and the offer both have a size, of the same kind (g, ml, stk)."""
    size = package_size(underline)
    return bool(size and avis_size(offer, size[0]))


def _avis_details_fit(name: str, underline: str | None, organic: bool, offer: Offer) -> bool:
    text = f"{offer.heading}\n{offer.description or ''}"
    size = package_size(underline)
    sizes = avis_size(offer, size[0]) if size else None
    if size and sizes and not sizes[0] * 0.9 <= size[1] <= sizes[1] * 1.1:
        return False
    offer_percents = _percents(text)
    product_percents = _percents(name)
    if offer_percents and product_percents and not product_percents & offer_percents:
        return False
    words = _tokens(text)
    if "økologisk" in words:
        return organic or any(w.startswith("konventionel") for w in words)
    return not organic


def offer_covers(
    offer: Offer, product_id: int | None, name: str, underline: str | None, organic: bool
) -> bool:
    """Is the offer for this product? By REMA's product ids when Tjek has them.

    When Tjek also lists products without a REMA id ("Arla Skyr Airy"), or none
    at all, a product the ids don't cover can still be the offer by name.
    """
    if offer.product_ids is not None:
        if product_id in offer.product_ids:
            return True
        if not offer.unlinked:
            return False
        if unlinked_match(name, underline, organic, offer):
            return True
    return avis_match(name, underline, organic, offer)


def unlinked_match(name: str, underline: str | None, organic: bool, offer: Offer) -> bool:
    """Is a REMA product one Tjek lists for the offer without REMA's id?

    Every word of REMA's name is in Tjek's ("SKYR AIRY JORDBÆR" in "Arla Skyr
    Airy Jordbær"), and size, fat percentage and organic fit the offer.
    """
    words = _name_words(name)
    return bool(words) and any(
        words <= _name_words(tjek) and _avis_details_fit(name, underline, organic, offer)
        for tjek in offer.unlinked_names
    )


def offer_query(offer: Offer, name: str = "") -> str:
    """REMA search words for the part of an avis offer a line is about.

    'REMA 1000 salami, leverpostej eller Taga serrano' for 'leverpostej' ->
    'leverpostej'; 'REMA 1000 Laksefilet' -> 'Laksefilet'.
    """
    heading = re.sub(r"^REMA 1000\s+", "", offer.heading.strip(), flags=re.IGNORECASE)
    parts = [p.strip() for p in re.split(r",|\beller\b", heading, flags=re.IGNORECASE)]
    wanted = _name_words(name)
    best = max(parts, key=lambda part: len(wanted & _name_words(part)))
    return best or heading or offer.heading


def search_queries(line: dict[str, Any]) -> list[str]:
    """What to search REMA for, best guess first.

    REMA names minced meat "HK. ...KØD", so "kyllingefars" is also tried as
    "hakket kylling", and the line's own name is tried last.
    """
    queries = [line["search"]]
    for word in _tokens(line["search"]):
        if word.endswith("fars") and len(word) > 4:
            meat = word[:-4].rstrip("e")
            queries.append(f"hakket {meat}")
    queries.append(line["name"])
    unique: list[str] = []
    for query in queries:
        if query and query.lower() not in (q.lower() for q in unique):
            unique.append(query)
    return unique


def name_fit(search_words: list[str], product_name: str) -> tuple[int, float]:
    """How well a product name fits the searched words.

    Returns (number of searched words found, price penalty factor). Danish
    compound words count as a match ("skrabeæg" is æg, "laksefileter" is laks),
    but cost a little more than the plain word. Words that make it a different
    product ("søde kartofler", "oksekød 35% grønt", "broccoliblanding",
    "hvidløg" for løg) cost a lot, so they are only chosen if nothing else fits.
    """
    name = [t for t in _tokens(product_name) if len(t) > 1]
    matched = 0
    penalty = 1.0
    for word in search_words:
        if word in name:
            matched += 1
            continue
        compound = next(
            (
                t
                for t in name
                # A short word only at the end: skrabeæg is æg, æggestand isn't.
                if t.endswith(word) or (t.startswith(word) and len(word) > 3)
            ),
            None,
        )
        if compound is None:
            continue
        matched += 1
        rest = compound[len(word) :] if compound.startswith(word) else compound[: -len(word)]
        # Danish joins compounds with -e- or -s- (laks-e-pålæg, hvidløg-s-...).
        parts = {rest, rest.strip("es")}
        different = parts & (_DIFFERENT_WORDS | _DIFFERENT_PREFIXES)
        penalty += 5.0 if different else 0.15
    for token in name:
        if token in _NEUTRAL_WORDS or any(word in token or token in word for word in search_words):
            continue
        is_other = token in _DIFFERENT_WORDS or any(
            token.endswith(d) for d in _DIFFERENT_WORDS if len(d) > 4
        )  # "varmrøget" is røget
        penalty += 5.0 if is_other else 0.15
    return matched, penalty


def extract_json(data: Any) -> dict[str, Any]:
    """Get the JSON object out of an AI answer."""
    if isinstance(data, dict):
        return data
    text = str(data or "").strip()
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end <= start:
        raise ValueError("The AI answer contained no JSON object")
    result = json.loads(text[start : end + 1])
    if not isinstance(result, dict):
        raise ValueError("The AI answer was not a JSON object")
    return result


def _num(value: Any, default: float | None = None) -> float | None:
    try:
        return float(str(value).replace(",", "."))
    except (TypeError, ValueError):
        return default


# ------------------------------------------------------------------ prompt


_EGG_LEVEL = {"caged": 0, "free_range": 1, "organic": 2}
_NOT_EGGS = {"pålæg", "indlæg", "tillæg", "oplæg", "pålægs"}
_NOT_DAIRY_MILK = ("kokos", "mandel", "havre", "soja", "ris", "kakao", "kærne")


def egg_level(product: Product) -> int:
    """0 = skrabeæg (or unknown), 1 = frilandsæg, 2 = økologiske æg."""
    text = f"{product.name} {product.underline or ''}".upper()
    if product.is_organic or re.search(r"(^|[^A-ZÆØÅ])ØKO", text):
        return 2
    if "FRILAND" in text:
        return 1
    return 0


def line_kind(line: dict[str, Any]) -> str | None:
    """Is a shopping line eggs, (dairy) milk or fruit & vegetables?"""
    tokens = _tokens(f"{line.get('search') or ''} {line.get('name') or ''}")
    if any(t == "æg" or (t.endswith("æg") and t not in _NOT_EGGS) for t in tokens):
        return "egg"
    if any(
        "mælk" in t and "chokolade" not in t and not t.startswith(_NOT_DAIRY_MILK) for t in tokens
    ):
        return "milk"
    category = str(line.get("category") or "").lower()
    if "frugt" in category or "grønt" in category:
        return "produce"
    return None


def rule_lines(settings: dict[str, Any]) -> list[str]:
    """The family's standing rules ("altid frisk broccoli til laks"), for every prompt."""
    return [f"- {rule}" for rule in settings.get("rules") or []]


def nutrition_target(settings: dict[str, Any]) -> str | None:
    """The nutrition the family aims for per adult's dinner, as a prompt line."""
    if not settings.get("nutrition_enabled"):
        return None
    return (
        f"{settings['kcal_min']}-{settings['kcal_max']} kcal pr. voksenportion, og energien "
        f"fordelt så tæt som muligt på {settings['protein_pct']} % protein, "
        f"{settings['carb_pct']} % kulhydrat og {settings['fat_pct']} % fedt"
    )


NUTRITION_KEYS = ("kcal", "protein_g", "carbs_g", "fat_g", "fiber_g")


def clean_nutrition(raw: Any) -> dict[str, float] | None:
    """The AI's estimate of a dish's nutrition per adult portion."""
    if not isinstance(raw, dict):
        return None
    out: dict[str, float] = {}
    for key in NUTRITION_KEYS:
        value = _num(raw.get(key))
        if value is not None and 0 <= value < 10000:
            out[key] = round(value, 1)
    return out if "kcal" in out else None


def _household_lines(settings: dict[str, Any]) -> list[str]:
    lines = []
    for member in settings["household"]:
        role = "Voksen" if member["role"] == "adult" else "Barn"
        sex = {"male": "dreng/mand", "female": "pige/kvinde"}.get(member["sex"], "")
        lines.append(f"- {role}, {member['age']} år{', ' + sex if sex else ''}")
    return lines or ["- 2 voksne"]


def plan_shops(
    settings: dict[str, Any], chain_offers: dict[str, dict[str, Any]] | None
) -> list[str]:
    """The plan's shops, favourite first: REMA 1000 and the chosen chains with offers read.

    A chain whose avis could not be read is left out, so its items go to REMA
    as before.
    """
    read = {entry["dealer_id"] for entry in (chain_offers or {}).values()}
    order = settings.get("plan_chains") or [REMA_ID]
    return [c for c in order if c == REMA_ID or c in read]


def build_prompt(
    *,
    settings: dict[str, Any],
    dates: list[date],
    catalog: Catalog | None,
    offers: list[Offer],
    favorites_due: list[dict[str, Any]],
    favorites_optional: list[dict[str, Any]],
    recent_dishes: list[str],
    feedback: str | None = None,
    skipped: list[date] | None = None,
    note: str | None = None,
    late: dict[int, date] | None = None,
    mealie: list[dict[str, Any]] | None = None,
    own: list[dict[str, Any]] | None = None,
    disliked: list[str] | None = None,
    surprise: bool = False,
    chain_offers: dict[str, dict[str, Any]] | None = None,
) -> str:
    """Build the instructions for the AI."""
    s = settings
    day_list = ", ".join(f"{WEEKDAYS_DA[d.weekday()]} {d.isoformat()}" for d in dates)
    shops = plan_shops(s, chain_offers)
    out: list[str] = [
        "Du er en erfaren dansk madplanlægger. Familien handler i REMA 1000 i Danmark."
        if len(shops) < 2
        else "Du er en erfaren dansk madplanlægger. Familien handler i "
        + ", ".join(chain_name(c) for c in shops)
        + " i Danmark – helst i den rækkefølge.",
        f"Lav en madplan med aftensmad for {len(dates)} dage: {day_list}.",
        "",
        "HUSSTAND (beregn mængder til hele husstanden; børn spiser mindre end voksne):",
        *_household_lines(s),
        "",
        "KRAV – SKAL OVERHOLDES:",
    ]
    if skipped:
        out.append(
            "- Disse dage springes over (ingen aftensmad og intet på indkøbslisten): "
            + ", ".join(f"{WEEKDAYS_DA[d.weekday()]} {d.isoformat()}" for d in skipped)
            + ". Rester spises dagen efter den ret, de kommer fra, i listen ovenfor."
        )
    allergies = [ALLERGY_DA[a] for a in s["allergies"]]
    if s["allergies_other"].strip():
        allergies.append(s["allergies_other"].strip())
    if allergies:
        out.append(f"- Allergier – må ALDRIG indgå, heller ikke som spor: {', '.join(allergies)}.")
    avoid = [AVOID_DA[a] for a in s["avoid"]]
    if s["avoid_other"].strip():
        avoid.append(s["avoid_other"].strip())
    if avoid:
        out.append(f"- Undgå helt: {', '.join(avoid)}.")
    out.append(
        f"- Vegetarretter: mindst {s['min_vegetarian']} og højst {s['max_vegetarian']} i perioden."
    )
    if s["leftover_days"]:
        out.append(
            f"- Præcis {s['leftover_days']} dage er restedage: retten dagen før laves i dobbelt "
            'portion, og dagen efter spises resten (type "rester", angiv uses_leftovers_from, '
            "ingen nye ingredienser). Rester må ikke ligge på første dag."
        )
    else:
        out.append("- Ingen restedage; hver dag er en ny ret.")
    for fixed in s["fixed_days"]:
        matching = [d for d in dates if d.weekday() == fixed["weekday"]]
        for day in matching:
            out.append(
                f"- {WEEKDAYS_DA[day.weekday()]} {day.isoformat()}: {fixed['text']} "
                '(fast dag – tæller ikke som restedag, type "fast")'
            )
    out.append(
        f"- Mandag til fredag højst {s['max_cook_minutes_weekday']} minutters aktiv tilberedning."
    )
    if dislikes := [*s["disliked_dishes"], *(disliked or [])]:
        out.append(
            "- Familien kan ikke lide disse retter – brug dem ALDRIG, heller ikke varianter af dem: "
            + "; ".join(dislikes)
            + "."
        )
    if recent_dishes:
        out.append(
            "- Disse retter fra de seneste uger må IKKE gentages: " + "; ".join(recent_dishes) + "."
        )
    if s.get("rules"):
        out.append("- Familiens faste regler – følg dem altid:")
        out += [f"  {line}" for line in rule_lines(s)]
    if target := nutrition_target(s):
        out.append(f"- Næring: {target}.")
    if s["budget"] and len(shops) < 2:
        out.append(f"- Hele indkøbslisten skal koste under {s['budget']} kr. med REMA 1000-priser.")
    elif s["budget"]:
        out.append(
            f"- Hele indkøbslisten skal koste under {s['budget']} kr. i alt på tværs af alle "
            "butikkerne (tilbudspriserne; varer uden tilbud regnes med REMA 1000's pris)."
        )
    organic = {
        "only": "Brug udelukkende økologiske varer, hvor REMA 1000 har dem.",
        "prefer": f"Foretræk økologiske varer, når de højst er {s['organic_max_extra_pct']} % dyrere.",
        "none": "Vælg de billigste varer; økologi er ikke et krav.",
    }[s["organic"]]
    out.append(f"- Økologi: {organic}")
    if s["egg_min"] != "caged":
        eggs = "mindst frilandsæg" if s["egg_min"] == "free_range" else "økologiske æg"
        out.append(f"- Æg skal være {eggs}.")
    if s["milk_organic"]:
        out.append("- Mælk skal være økologisk.")
    if s["produce_organic"]:
        out.append("- Frugt og grønt skal være økologisk.")
    if note:
        out.append(
            "- Familiens ønsker til netop denne madplan – SKAL følges (fx varer de allerede har, "
            "der skal bruges før en bestemt dato, eller en bestemt ret på en bestemt dag). Varer, "
            f"familien allerede har, skal IKKE på indkøbslisten: {note}"
        )
    if feedback:
        out.append(f"- VIGTIGT fra sidste forsøg: {feedback}")

    out += ["", "ØNSKER:"]
    if surprise:
        out.append(
            "- OVERRASK FAMILIEN: lav en uge med retter, de aldrig har fået – fra andre køkkener "
            "(fx koreansk, peruviansk, etiopisk, georgisk, libanesisk, vietnamesisk), med "
            "spændende smage, teknikker og overraskende kombinationer. Hver dag skal være "
            "forskellig og føles som en lille opdagelse, men stadig til at lave på en hverdag, "
            "børnevenlig og inden for alle krav ovenfor. Brug ikke familiens kendte retter."
        )
    if s["wishes"].strip():
        out.append(f"- {s['wishes'].strip()}")
    out.append(
        "- Byg retterne op omkring ugens tilbud nedenfor, og marker tilbudsvarer på "
        "indkøbslisten med tilbuddets id."
    )
    if favorites_due and not surprise:
        out.append("- Disse familiefavoritter SKAL med i perioden (angiv favorite_id på dagen):")
        out += [f"  [{f['id']}] {f['text']}" for f in favorites_due]
    if favorites_optional and not surprise:
        out.append(
            '- Familiefavoritter til inspiration (ikke krav). Dem markeret "kun på tilbud" '
            "bruges kun, hvis hovedingrediensen er på tilbud. Angiv favorite_id, hvis du bruger én:"
        )
        for fav in favorites_optional:
            note = " (kun på tilbud)" if fav.get("frequency") == "on_offer" else ""
            out.append(f"  [{fav['id']}] {fav['text']}{note}")
    if s["pantry"].strip():
        out.append(
            f"- Basisvarer familien altid har, som IKKE skal på indkøbslisten: {s['pantry'].strip()}."
        )
    if s["must_haves"]:
        names = ", ".join(item["name"] for item in s["must_haves"])
        out.append(
            f"- Faste ugevarer købes separat og skal IKKE på indkøbslisten: {names}. "
            "Du må gerne bruge dem i retterne."
        )

    if mealie:
        out += [
            "",
            "FAMILIENS OPSKRIFTER I MEALIE – tag udgangspunkt i dem: brug en af dem, når den "
            "passer til ugens tilbud og kravene (skriv dens id i mealie på dagen, og brug "
            "opskriftens navn som dish; indkøbslisten følger opskriftens ingredienser). Er "
            "der ikke en passende, så find selv på en ret (mealie: null). "
            "id | ret | ingredienser:",
        ]
        out += [f"{r['slug']} | {r['name']} | {', '.join(r['ingredients'])[:300]}" for r in mealie]
    if own and not surprise:
        out += [
            "",
            "FAMILIENS OPSKRIFTSSAMLING – retter de synes om (❤️ = favorit, brug dem gerne "
            "ofte). Brug en af dem, når den passer til ugens tilbud og kravene: skriv dens id i "
            "recipe_id på dagen og opskriftens navn som dish; indkøbslisten følger opskriftens "
            "ingredienser. Ellers recipe_id: null. id | ret | ingredienser:",
        ]
        out += [
            f"{r['id']} | {'❤️ ' if r['favorite'] else ''}{r['name']} | "
            f"{', '.join(ingredient_texts(r))[:300]}"
            for r in own
        ]
    if offers:
        label = catalog.label if catalog and catalog.label else "Ugens tilbud"
        late = late or {}
        out += ["", f"UGENS TILBUD I REMA 1000 ({label}) – id | vare | pris | mængde:"]
        if late and s["shop_late_week"]:
            out.append(
                'Tilbud markeret "gælder først fra" må KUN bruges i retter på eller efter den dag '
                "(familien køber dem den dag)."
            )
        for idx, offer in enumerate(offers):
            starts = late.get(idx)
            if starts and not s["shop_late_week"]:
                continue  # the family shops once, before this offer starts
            price = f"{offer.price:g} kr." if offer.price is not None else "?"
            if offer.pre_price:
                price += f" (før {offer.pre_price:g})"
            desc = (offer.description or "").split("\n")[0][:60]
            qty = offer.quantity or ""
            line = f"o{idx} | {offer.heading} | {price} | {qty} {desc}".rstrip()
            if starts:
                line += f" | gælder først fra {WEEKDAYS_DA[starts.weekday()]} {starts.isoformat()}"
            out.append(line)
    if chain_offers:
        favourite = chain_name(shops[0])
        out += [
            "",
            "UGENS TILBUD I DE ANDRE BUTIKKER – id | butik: vare | pris | mængde:",
            *plan_offer_lines(chain_offers),
            "",
            "BUTIKKER: Hver tilbudsvare købes i den butik, tilbuddets id hører til. Er samme "
            "vare på tilbud flere steder, så vælg det billigste tilbud; koster de næsten det "
            f"samme (under {MIN_SAVING:g} kr. forskel), så vælg efter rækkefølgen "
            + ", ".join(chain_name(c) for c in shops)
            + f". Varer, der ikke er på tilbud, købes i {favourite} (giv dem intet tilbuds-id).",
        ]

    out += [
        "",
        "Lav KUN overblikket nu – opskrifterne skrives bagefter. Hold svaret kort og præcist; "
        "summary højst én sætning.",
        "Retternes navne skal passe til ingredienserne (kyllingefrikadeller kræver hakket "
        "kylling). Indkøbslisten skal indeholde ALLE ingredienser til alle retter, og mængderne "
        "skal dække dobbelte portioner på dage, der laver rester.",
        "Brug de varer, en dansk familie normalt bruger til retten, og som er nemmest: hakkede "
        "tomater på dåse til kødsovs, lasagne og bolognese (ikke friske tomater, der skal "
        "hakkes), frossen spinat, revet ost. Samme slags vare til forskellige formål står hver "
        "for sig (friske tomater til gnavegrønt OG hakkede tomater på dåse til sovsen).",
        "Angiv for hver dag i uses navnene på de varer fra indkøbslisten, retten bruger "
        "(præcis som de står på listen; ikke basisvarer). Restedage har en tom liste.",
        "",
        "INDKØBSLISTE: Saml alle ingredienser på tværs af dagene. Angiv for hver vare: navn, "
        "mængde som tal, enhed (g, kg, ml eller l når muligt; pk for pakker, dåser og poser, fx "
        "3 pk hakkede tomater; stk kun for løse enkeltvarer, fx 10 stk æg eller 2 stk "
        "peberfrugt), et søgeord til REMA 1000's varesøgning "
        '(1-3 ord, fx "hakket oksekød", "laks", "broccoli"), kategori (Frugt & grønt, Kød, '
        "Fisk, Mejeri, Brød, Kolonial, Frost eller Andet) og evt. tilbuddets id. Udelad basisvarer.",
        "",
        "Kontrollér til sidst ALLE krav og udfyld checklist ærligt. Skriv afvigelser i deviations.",
        "",
        "SVARFORMAT: Svar KUN med gyldig JSON uden markdown og uden forklaring, præcis sådan:",
        json.dumps(
            {
                "title": plan_title(dates),
                "summary": "Kort beskrivelse af ugen",
                "days": [
                    {
                        "date": dates[0].isoformat(),
                        "dish": "Ovnbagt laks med spinatpasta, pesto og broccoli",
                        "type": "normal | vegetar | rester | fast",
                        "favorite_id": None,
                        "uses_leftovers_from": None,
                        "makes_leftovers": False,
                        "servings": 4,
                        "active_minutes": 20,
                        "total_minutes": 35,
                        "uses": ["Laksefilet", "Spinatpasta", "Pesto", "Broccoli"],
                        "mealie": None,
                        "recipe_id": None,
                    }
                ],
                "shopping": [
                    {
                        "name": "Laksefilet",
                        "amount": 600,
                        "unit": "g",
                        "search": "laks",
                        "category": "Fisk",
                        "offer": "o12",
                    }
                ],
                "checklist": [{"requirement": "Højst 1 vegetarret", "ok": True}],
                "deviations": "",
            },
            ensure_ascii=False,
        ),
        f"days skal have præcis {len(dates)} elementer i datoorden.",
    ]
    return "\n".join(out)


def build_recipe_prompt(
    *, settings: dict[str, Any], day: dict[str, Any], plan: dict[str, Any]
) -> str:
    """Instructions for the recipe of one dinner."""
    s = settings
    current = date.fromisoformat(day["date"])
    out = [
        "Du er en erfaren dansk kok, der skriver opskrifter til en børnefamilie.",
        f"Skriv opskriften på aftensmaden {WEEKDAYS_DA[current.weekday()]} {day['date']}: "
        f"{day['dish']}.",
        "",
        "HUSSTAND (mængderne skal passe til alle; børn spiser mindre):",
        *_household_lines(s),
    ]
    if day.get("makes_leftovers"):
        out.append(
            "Lav dobbelt portion – halvdelen spises som rester dagen efter. Mængderne skal "
            "dække begge dage."
        )
    allergies = [ALLERGY_DA[a] for a in s["allergies"]]
    if s["allergies_other"].strip():
        allergies.append(s["allergies_other"].strip())
    if allergies:
        out.append(f"Allergier – må ALDRIG indgå: {', '.join(allergies)}.")
    avoid = [AVOID_DA[a] for a in s["avoid"]]
    if s["avoid_other"].strip():
        avoid.append(s["avoid_other"].strip())
    if avoid:
        out.append(f"Undgå helt: {', '.join(avoid)}.")
    if current.weekday() < 5:
        out.append(f"Højst {s['max_cook_minutes_weekday']} minutters aktiv tilberedning.")
    if s.get("rules"):
        out += ["Familiens faste regler – følg dem altid:", *rule_lines(s)]
    if target := nutrition_target(s):
        out.append(f"Næring: {target}. Juster mængderne, så retten rammer det.")
    if plan.get("note"):
        out.append(
            f"Familiens ønsker til ugen (brug varer, de allerede har, hvor det passer): {plan['note']}"
        )

    def describe(line: dict[str, Any]) -> str:
        bought = (line.get("product") or line.get("avis_item") or {}).get("name")
        text = str(line["name"])
        if line.get("amount") and line.get("unit") and line["unit"] != "pk":
            text += f" ({line['amount']:g} {line['unit']})"
        if bought and bought.lower() != line["name"].lower():
            text += f" [købes som {bought}]"
        return text

    lines = plan.get("shopping", [])
    uses = {name.lower() for name in day.get("uses") or []}
    mine = [line for line in lines if line["name"].lower() in uses]
    if mine:
        # Only this dish's items: the fresh tomatoes for snacks on another day
        # are not the lasagne's tomatoes.
        out.append(
            "Rettens varer fra indkøbslisten (brug dem, som de købes – fx hakkede tomater på "
            "dåse hældes i, de skal ikke hakkes; tilføj ikke nye dyre varer): "
            + ", ".join(describe(line) for line in mine)
            + "."
        )
    else:
        out.append(
            "Ugens indkøb (brug disse varer og basisvarerne; tilføj ikke nye dyre varer): "
            + ", ".join(describe(line) for line in lines)
            + "."
        )
    out += [
        f"Basisvarer: {s['pantry'].strip() or 'salt og peber'}.",
        "",
        "Lav retten, som en dansk familie normalt laver den, med de nemmeste varer: hakkede "
        "tomater på dåse i kødsovs og lasagne, ikke friske tomater, der skal hakkes.",
        "Skriv til en uerfaren kok: præcise mængder, højst 10 korte trin med minutter, og ét "
        "kort tip, der gør det nemt for børnefamilien.",
        "",
        "SVARFORMAT: Svar KUN med gyldig JSON uden markdown og uden forklaring, præcis sådan:",
        json.dumps(
            {
                "ingredients": [{"name": "laksefilet", "amount": "600 g"}],
                "steps": [{"text": "Tænd ovnen på 200 grader.", "minutes": 1}],
                "tip": "Kort tip",
                "active_minutes": 20,
                "total_minutes": 35,
                "nutrition": {
                    "kcal": 750,
                    "protein_g": 50,
                    "carbs_g": 80,
                    "fat_g": 22,
                    "fiber_g": 9,
                },
            },
            ensure_ascii=False,
        ),
        "nutrition er dit bedste skøn over næringen i én voksenportion.",
    ]
    return "\n".join(out)


# ------------------------------------------------------------------ planner


class MealPlanner:
    """Create meal plans with AI and send them to the REMA shopping list."""

    def __init__(
        self,
        hass: HomeAssistant,
        entry_id: str,
        client: RemaClient,
        store: RemaPlanStore,
        get_catalogs: Callable[[], tuple[Catalog | None, Catalog | None]],
        add_items: Callable[[list[dict[str, Any]]], Awaitable[None]],
    ) -> None:
        """Initialize the planner."""
        self.hass = hass
        self.entry_id = entry_id
        self.client = client
        self.store = store
        self._get_catalogs = get_catalogs
        self._add_items = add_items
        self.status: dict[str, Any] = {"state": "idle", "message": None, "started": None}
        self._task: asyncio.Task[None] | None = None
        self._auto_attempted: set[str] = set()
        self.mealie = MealieLink(hass)
        self.chains = ChainOffers(hass)
        # Automatic sends waiting for REMA's prices: (plan id, key) -> cancel.
        self._sends: dict[tuple[str, str], Callable[[], None]] = {}

    # ------------------------------------------------------------- status

    @callback
    def _notify(self) -> None:
        async_dispatcher_send(self.hass, signal_plans_updated(self.entry_id))

    @callback
    def _set_status(self, state: str, message: str | None = None) -> None:
        started = self.status.get("started") if state != "generating" else dt_util.now().isoformat()
        self.status = {"state": state, "message": message, "started": started}
        self._notify()

    @property
    def generating(self) -> bool:
        """True while a plan is being made."""
        return self._task is not None and not self._task.done()

    # ------------------------------------------------------------- generation

    def default_start(self) -> date:
        """The start date of the next plan.

        The family's first weekday, but today while next week's avis isn't out:
        a plan for next week can't be priced yet, the rest of this week can.
        """
        today = dt_util.now().date()
        start = next_start(today, self.store.settings["start_weekday"])
        try:
            self.avis_end(start)
        except ServiceValidationError:
            return today
        return start

    def avis_end(self, start: date) -> date | None:
        """The last day a plan from start can be priced, or None for no limit.

        Raises if start is after every avis that is out: the prices aren't known yet.
        Without any avis known (REMA can't be reached), anything goes, as before.
        """
        known = [
            (c, _local_day(c.valid_from), _local_day(c.valid_to))
            for c in self._get_catalogs()
            if c and c.valid_from and c.valid_to
        ]
        if not known:
            return None
        covering = next((k for k in known if k[1] <= start <= k[2]), None)
        if covering is None:
            last = max(k[2] for k in known)
            if start > last:
                raise _invalid(
                    "avis_not_out",
                    date=f"{start.day}/{start.month}",
                    last=f"{last.day}/{last.month}",
                )
            return None
        end = covering[2]
        # A later avis takes over the day after: the plan can go on into it.
        if any(k[1] <= end + timedelta(days=1) <= k[2] for k in known if k is not covering):
            return None
        return end

    @callback
    def async_start_generation(
        self,
        start: date | None = None,
        send: bool = False,
        skip: set[date] | None = None,
        surprise: bool = False,
    ) -> None:
        """Start making a plan in the background. Days in skip get no dinner.

        surprise: dishes the family has never had (Overrask os).
        """
        if self.generating:
            raise _invalid("already_generating")
        start = start or self.default_start()
        self.avis_end(start)
        if skip and not plan_dates(start, self.store.settings["days"], skip):
            raise _invalid("all_days_skipped")
        if not self.ai_available():
            self._async_create_ai_issue()
            raise _invalid("no_ai_task")
        self._set_status("generating", "Laver madplan …")
        self._task = self.hass.async_create_background_task(
            self._async_run(start, send, skip or set(), surprise),
            name=f"{DOMAIN} meal plan",
        )

    async def _async_run(
        self, start: date, send: bool, skip: set[date], surprise: bool = False
    ) -> None:
        try:
            plan = await self.async_generate(start, skip, surprise=surprise)
            if send:
                await self._async_send_when_ready(plan)
        except Exception as err:
            _LOGGER.exception("Could not make a meal plan")
            self._set_status("error", str(err) or err.__class__.__name__)
        else:
            self._set_status("idle")

    def _ai_entity(self) -> str | None:
        """The AI Task entity to use; None means Home Assistant's preferred one."""
        entity: str | None = self.store.settings.get("ai_task_entity")
        if entity and self.hass.states.get(entity) is not None:
            return entity
        # None lets Home Assistant use its preferred AI task entity; fall back to
        # the first one if no preference is set.
        prefs = self.hass.data.get("ai_task_preferences")
        if prefs is not None and getattr(prefs, "gen_data_entity_id", None):
            return None
        ids = self.hass.states.async_entity_ids("ai_task")
        return ids[0] if ids else entity

    def ai_available(self) -> bool:
        """True if there is an AI Task entity to make plans with."""
        prefs = self.hass.data.get("ai_task_preferences")
        if prefs is not None and getattr(prefs, "gen_data_entity_id", None):
            return True
        return bool(self.hass.states.async_entity_ids("ai_task"))

    @callback
    def _async_create_ai_issue(self) -> None:
        """Tell the user in Repairs that an AI Task is needed."""
        ir.async_create_issue(
            self.hass,
            DOMAIN,
            ISSUE_NO_AI_TASK,
            is_fixable=False,
            severity=ir.IssueSeverity.WARNING,
            translation_key=ISSUE_NO_AI_TASK,
            learn_more_url=AI_TASK_DOCS_URL,
        )

    async def _async_offers(self, start: date) -> tuple[Catalog | None, list[Offer]]:
        current, upcoming = self._get_catalogs()
        catalog = current
        for candidate in (upcoming, current):
            if (
                candidate
                and candidate.valid_from
                and candidate.valid_to
                and candidate.valid_from.date() <= start <= candidate.valid_to.date()
            ):
                catalog = candidate
                break
        if catalog is None:
            return None, []
        try:
            return catalog, await self.client.async_get_offers(catalog.id)
        except RemaError as err:
            _LOGGER.warning("Could not load offers for the meal plan: %s", err)
            return catalog, []

    async def _async_chain_offers(self, day: date) -> dict[str, dict[str, Any]]:
        """The chosen chains' offers on the shopping day, by their id for the AI."""
        chosen: dict[str, list[dict[str, Any]]] = {}
        for dealer_id in self.store.settings.get("plan_chains") or []:
            if dealer_id == REMA_ID:
                continue  # REMA's avis comes from REMA (with its products)
            try:
                chosen[dealer_id] = await self.chains.async_offers(dealer_id)
            except (ChainError, ServiceValidationError) as err:
                _LOGGER.warning("Could not load %s's offers for the meal plan: %s", dealer_id, err)
        return plan_offers(chosen, day)

    async def _async_ask_ai(self, prompt: str, task_name: str) -> dict[str, Any]:
        from homeassistant.components.ai_task import async_generate_data  # noqa: PLC0415

        entity_id = self._ai_entity()

        async def ask(instructions: str) -> Any:
            try:
                result = await async_generate_data(
                    self.hass, task_name=task_name, entity_id=entity_id, instructions=instructions
                )
            except HomeAssistantError as err:
                if "MAX_TOKENS" in str(err).upper():
                    raise _failed("ai_answer_too_long", error=str(err)) from err
                raise
            return result.data

        try:
            return extract_json(await ask(prompt))
        except ValueError:
            _LOGGER.debug("AI answer was not valid JSON, asking again")
        try:
            return extract_json(
                await ask(
                    prompt + "\n\nDit forrige svar var ikke gyldig JSON. Svar nu KUN med selve "
                    "JSON-objektet."
                )
            )
        except ValueError as err:
            raise _failed("ai_invalid_json", error=str(err)) from err

    # ------------------------------------------------------------- recipes

    @staticmethod
    def _is_leftovers(day: dict[str, Any]) -> bool:
        return bool(day.get("uses_leftovers_from")) or day.get("type") == "rester"

    async def _async_recipe(self, day: dict[str, Any], plan: dict[str, Any]) -> None:
        """Fill in ingredients and steps for one day."""
        day.pop("recipe_error", None)
        if self._is_leftovers(day):
            source = day.get("uses_leftovers_from")
            previous = next(
                (d for d in plan["days"] if d["date"] == source),
                None,
            ) or next(
                (
                    d
                    for d in reversed(plan["days"])
                    if d["date"] < day["date"] and not self._is_leftovers(d)
                ),
                None,
            )
            dish = previous["dish"] if previous else "gårsdagens ret"
            day["steps"] = [{"text": f"Varm resten af {dish} op, og server den.", "minutes": 10}]
            day["ingredients"] = []
            day["total_minutes"] = day["total_minutes"] or 15
            day["active_minutes"] = day["active_minutes"] or 5
            return
        if day.get("mealie") and await self._async_mealie_recipe(day):
            return
        own = find_recipe(self.store, day.get("recipe_id"))
        if own and (own["ingredients"] or own["steps"]):
            recipe_to_day(own, day)
            return
        prompt = build_recipe_prompt(settings=self.store.settings, day=day, plan=plan)
        try:
            raw = await self._async_ask_ai(prompt, f"REMA 1000 opskrift {day['date']}")
        except HomeAssistantError as err:
            _LOGGER.warning("Could not write the recipe for %s: %s", day["date"], err)
            day["recipe_error"] = str(err)
            return
        cleaned = self._clean_days(
            [{**raw, "date": day["date"]}], [date.fromisoformat(day["date"])]
        )[0]
        day["ingredients"] = cleaned["ingredients"]
        day["steps"] = cleaned["steps"]
        day["tip"] = cleaned["tip"]
        day["nutrition"] = clean_nutrition(raw.get("nutrition"))
        if cleaned["active_minutes"]:
            day["active_minutes"] = cleaned["active_minutes"]
        if cleaned["total_minutes"]:
            day["total_minutes"] = cleaned["total_minutes"]

    async def _async_mealie_recipe(self, day: dict[str, Any]) -> bool:
        """The family's own recipe from Mealie for a day built on it."""
        try:
            recipe = await self.mealie.async_recipe(str(day["mealie"]))
        except MealieError as err:
            _LOGGER.warning("Could not read %s from Mealie: %s", day["mealie"], err)
            return False
        if not recipe["ingredients"] and not recipe["steps"]:
            return False
        day["ingredients"] = [{"name": text, "amount": ""} for text in recipe["ingredients"]]
        day["steps"] = [{"text": text, "minutes": 0} for text in recipe["steps"]]
        day["tip"] = recipe["description"]
        day["nutrition"] = None
        day["active_minutes"] = recipe["active_minutes"] or day.get("active_minutes", 0)
        day["total_minutes"] = recipe["total_minutes"] or day.get("total_minutes", 0)
        return True

    async def async_mealie_sync(self, plan: dict[str, Any], force: bool = False) -> int:
        """Put a plan's dinners in Mealie's calendar (when switched on, or asked)."""
        if not force and not (self.store.settings["mealie_calendar"] and self.mealie.available):
            return 0
        try:
            count = await self.mealie.async_sync_calendar(plan)
        except MealieError as err:
            if force:
                raise
            _LOGGER.warning("Could not fill Mealie's calendar: %s", err)
            return 0
        finally:
            await self.store.async_save()
        return count

    async def _async_add_recipes(self, plan: dict[str, Any]) -> None:
        """Write all recipes, a few at a time."""
        semaphore = asyncio.Semaphore(RECIPE_CONCURRENCY)
        cooking = [d for d in plan["days"] if not self._is_leftovers(d)]
        done = 0

        async def one(day: dict[str, Any]) -> None:
            nonlocal done
            async with semaphore:
                await self._async_recipe(day, plan)
            done += 1 if day in cooking else 0
            self._set_status("generating", f"Skriver opskrifter ({done}/{len(cooking)}) …")

        self._set_status("generating", f"Skriver opskrifter (0/{len(cooking)}) …")
        await asyncio.gather(*(one(day) for day in plan["days"]))

    async def async_regenerate_recipe(self, plan_id: str, day_date: str) -> dict[str, Any]:
        """Write one day's recipe again."""
        plan = self.store.get_plan(plan_id)
        day: dict[str, Any] | None = (
            next((d for d in plan["days"] if d["date"] == day_date), None) if plan else None
        )
        if plan is None or day is None:
            raise _invalid("day_not_found")
        await self._async_recipe(day, plan)
        await self.store.async_save()
        self._notify()
        if day.get("recipe_error"):
            raise _failed("recipe_failed", error=str(day["recipe_error"]))
        return day

    @staticmethod
    def price_time(start: date) -> datetime | None:
        """When to read prices for a plan: noon on its first day, or now (None).

        A plan for next week is bought next week, so it gets next week's
        prices and offers, matching the avis it is built on.
        """
        return noon(start)

    async def async_generate(
        self, start: date, skip: set[date] | None = None, *, surprise: bool = False
    ) -> dict[str, Any]:
        """Make, price and store a plan. Returns the plan."""
        settings = self.store.settings
        dates = plan_dates(start, settings["days"], skip)
        # Not past the last avis that is out: those days' prices aren't known yet.
        end = self.avis_end(start)
        if end is not None:
            dates = [d for d in dates if d <= end]
        if not dates:
            raise _invalid("all_days_skipped")
        skipped = sorted(
            d for d in (skip or set()) if start <= d < start + timedelta(settings["days"])
        )
        # Fewer days to cook: no more leftover or vegetarian days than there is room for.
        settings = {
            **settings,
            "leftover_days": min(settings["leftover_days"], (len(dates) - 1) // 2),
            "min_vegetarian": min(settings["min_vegetarian"], len(dates)),
            "max_vegetarian": min(settings["max_vegetarian"], len(dates)),
        }
        self._set_status("generating", "Henter ugens tilbud …")
        catalog, offers = await self._async_offers(start)
        late = late_offers(offers, dates[0])
        chain_offers = await self._async_chain_offers(dates[0])
        due, optional = self.store.favorites_due(start)
        recent = self.store.recent_dishes(start, settings["no_repeat_weeks"])
        note = self.store.note.strip()
        own = [] if surprise else prompt_recipes(self.store, recent)
        mealie: list[dict[str, Any]] = []
        if settings["mealie_recipes"] and self.mealie.available and not surprise:
            self._set_status("generating", "Henter jeres opskrifter fra Mealie …")
            try:
                mealie = await self.mealie.async_prompt_recipes(recent)
            except MealieError as err:
                _LOGGER.warning("Could not read the recipes in Mealie: %s", err)

        best: dict[str, Any] | None = None
        feedback: str | None = None
        for attempt in range(MAX_AI_ROUNDS):
            self._set_status(
                "generating",
                "AI'en laver madplanen …"
                if attempt == 0
                else "Planen var over budget – prøver igen …",
            )
            prompt = build_prompt(
                settings=settings,
                dates=dates,
                catalog=catalog,
                offers=offers,
                favorites_due=due,
                favorites_optional=optional,
                recent_dishes=recent,
                feedback=feedback,
                skipped=skipped,
                note=note or None,
                late=late,
                mealie=mealie,
                own=own,
                disliked=disliked_names(self.store),
                surprise=surprise,
                chain_offers=chain_offers,
            )
            raw = await self._async_ask_ai(prompt, "REMA 1000 madplan")
            self._set_status("generating", "Finder varer og priser i REMA 1000 …")
            plan = await self._async_build_plan(
                raw, dates, catalog, offers, self.price_time(start), late, chain_offers
            )
            known = {r["slug"] for r in mealie}
            ours = {r["id"] for r in own}
            for day in plan["days"]:
                if day.get("mealie") not in known:
                    day["mealie"] = None  # not one of the family's recipes
                if day.get("recipe_id") not in ours:
                    day["recipe_id"] = None
            if best is None or plan["total"] < best["total"]:
                best = plan
            if not settings["budget"] or plan["total"] <= settings["budget"]:
                break
            expensive = sorted(
                (line for line in plan["shopping"] if line.get("cost")),
                key=lambda line: line["cost"],
                reverse=True,
            )[:6]
            feedback = (
                f"Indkøbslisten kostede {plan['total']:.0f} kr., men budgettet er "
                f"{settings['budget']} kr. Dyreste varer: "
                + ", ".join(f"{line['name']} ({line['cost']:.0f} kr.)" for line in expensive)
                + ". Vælg billigere retter og flere tilbudsvarer."
            )

        assert best is not None
        ir.async_delete_issue(self.hass, DOMAIN, ISSUE_NO_AI_TASK)
        best["over_budget"] = bool(settings["budget"]) and best["total"] > settings["budget"]
        best["skipped"] = [d.isoformat() for d in skipped]
        best["note"] = note
        best["surprise"] = surprise
        await self._async_add_recipes(best)
        mark_planned(self.store, best)
        await self.store.async_add_plan(best)
        self._schedule_refreshes(best)
        await self.async_mealie_sync(best)
        if note and self.store.note.strip() == note:
            # The wishes are for this plan only (unless changed meanwhile).
            await self.store.async_set_note("")
        self._notify()
        return best

    async def _async_build_plan(
        self,
        raw: dict[str, Any],
        dates: list[date],
        catalog: Catalog | None,
        offers: list[Offer],
        at: datetime | None = None,
        late: dict[int, date] | None = None,
        chain_offers: dict[str, dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        settings = self.store.settings
        days = self._clean_days(raw.get("days") or [], dates)
        shopping = [
            line for line in (self._clean_line(item) for item in raw.get("shopping") or []) if line
        ]
        for item in settings["must_haves"]:
            shopping.append(
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
            )
        await self._async_price_lines(shopping, offers, at, late, chain_offers)
        total = round(sum(line.get("cost") or 0 for line in shopping), 2)
        return {
            "id": uuid.uuid4().hex[:12],
            "created": dt_util.now().isoformat(),
            "start_date": dates[0].isoformat(),
            "end_date": dates[-1].isoformat(),
            "week": plan_week(dates),
            "status": "draft",
            "sent_at": None,
            "title": plan_title(dates),
            "summary": str(raw.get("summary") or "")[:2000],
            "days": days,
            "shopping": shopping,
            "checklist": [
                {"requirement": str(c.get("requirement") or "")[:300], "ok": bool(c.get("ok"))}
                for c in raw.get("checklist") or []
                if isinstance(c, dict)
            ],
            "deviations": str(raw.get("deviations") or "")[:2000],
            "total": total,
            "budget": settings["budget"],
            "catalog": {"id": catalog.id, "label": catalog.label} if catalog else None,
            "ai_entity": self._ai_entity(),
        }

    async def _async_price_lines(
        self,
        shopping: list[dict[str, Any]],
        offers: list[Offer],
        at: datetime | None = None,
        late: dict[int, date] | None = None,
        chain_offers: dict[str, dict[str, Any]] | None = None,
    ) -> None:
        """Find and price REMA products for shopping lines (offers as "o<index>").

        A line on another chain's offer ("netto3") goes on that shop's list at
        the offer's price. A line on no offer goes to the family's favourite
        shop, priced with REMA's product as an estimate.
        """
        settings = self.store.settings
        chain_offers = chain_offers or {}
        favourite = plan_shops(settings, chain_offers)[0]
        rema_lines = []
        for line in shopping:
            entry = chain_offers.get(str(line.get("offer") or ""))
            if entry is None:
                rema_lines.append(line)
            else:
                self._chain_offer_line(line, entry)
        shopping = rema_lines
        offer_names = {f"o{i}": offer.heading for i, offer in enumerate(offers)}
        by_id = {f"o{i}": offer for i, offer in enumerate(offers)}
        late_days = {f"o{i}": day for i, day in (late or {}).items()}
        for line in shopping:
            offer_id = str(line.get("offer") or "")
            line["offer_name"] = offer_names.get(offer_id)
            # A thursday offer is bought (and priced) on its first day.
            day = late_days.get(offer_id) if settings["shop_late_week"] else None
            line["buy_from"] = day.isoformat() if day else None

        # Which of REMA's products the offers the dishes are built on are for.
        used = {str(line.get("offer") or "") for line in shopping} & by_id.keys()
        try:
            looked_up = await self.client.async_get_offer_products([by_id[o] for o in used])
        except RemaError as err:
            _LOGGER.debug("Could not look up the offers' products: %s", err)
        else:
            by_id |= {
                key: offer for key in used for offer in looked_up if offer.id == by_id[key].id
            }

        semaphore = asyncio.Semaphore(SEARCH_CONCURRENCY)

        async def match(line: dict[str, Any]) -> None:
            day = line["buy_from"]
            offer = by_id.get(str(line.get("offer") or ""))
            async with semaphore:
                await self._async_match(line, noon(date.fromisoformat(day)) if day else at, offer)
            self._avis_price(line, offer)

        await asyncio.gather(*(match(line) for line in shopping))
        if favourite != REMA_ID:
            for line in shopping:
                if not line.get("offer_name") and not line.get("must_have"):
                    # Not on offer: bought in the favourite shop, REMA's price as an estimate.
                    line.update(
                        buy_at=favourite,
                        chain_price=None,
                        chain_heading=line["name"],
                        bought=False,
                        price_estimated=True,
                    )

    @staticmethod
    def _chain_offer_line(line: dict[str, Any], entry: dict[str, Any]) -> None:
        """A line built on another chain's offer: on that shop's list, at the offer's price."""
        price = entry.get("price")
        packages = avis_packages(line.get("amount"), line.get("unit"), as_offer(entry))
        line.update(
            offer_name=entry["heading"],
            buy_from=None,
            product=None,
            avis_item=None,
            packages=packages,
            cost=round((price or 0) * packages, 2),
            note=str(entry.get("description") or "").split("\n")[0][:200] or None,
            buy_at=entry["dealer_id"],
            chain_price=price,
            chain_heading=entry["heading"],
            chain_only=True,  # not a REMA item
            bought=False,
        )

    @staticmethod
    def _clean_days(raw_days: list[Any], dates: list[date]) -> list[dict[str, Any]]:
        by_date = {
            str(day.get("date")): day
            for day in raw_days
            if isinstance(day, dict) and day.get("date")
        }
        ordered = [d for d in raw_days if isinstance(d, dict)]
        days = []
        for idx, current in enumerate(dates):
            day = by_date.get(current.isoformat()) or (ordered[idx] if idx < len(ordered) else {})
            days.append(
                {
                    "date": current.isoformat(),
                    "weekday": WEEKDAYS_DA[current.weekday()],
                    "dish": str(day.get("dish") or "Fri aften")[:300],
                    "type": str(day.get("type") or "normal")[:20],
                    "favorite_id": day.get("favorite_id") or None,
                    "uses_leftovers_from": day.get("uses_leftovers_from") or None,
                    "makes_leftovers": bool(day.get("makes_leftovers")),
                    "servings": int(_num(day.get("servings"), 4) or 4),
                    "active_minutes": int(_num(day.get("active_minutes"), 0) or 0),
                    "total_minutes": int(_num(day.get("total_minutes"), 0) or 0),
                    "ingredients": [
                        {
                            "name": str(i.get("name") or "")[:200],
                            "amount": str(i.get("amount") or "")[:60],
                        }
                        for i in day.get("ingredients") or []
                        if isinstance(i, dict) and i.get("name")
                    ],
                    "steps": [
                        {
                            "text": str(st.get("text") if isinstance(st, dict) else st)[:1000],
                            "minutes": int(_num(st.get("minutes"), 0) or 0)
                            if isinstance(st, dict)
                            else 0,
                        }
                        for st in day.get("steps") or []
                        if st
                    ],
                    "tip": str(day.get("tip") or "")[:500],
                    "mealie": str(day["mealie"])[:200] if day.get("mealie") else None,
                    "recipe_id": str(day["recipe_id"])[:40] if day.get("recipe_id") else None,
                    # The shopping list's items for this dish (from the overview).
                    "uses": [
                        str(name).strip()[:200]
                        for name in (day.get("uses") or [])[:30]
                        if isinstance(name, str) and name.strip()
                    ]
                    if isinstance(day.get("uses"), list)
                    else [],
                }
            )
        return days

    @staticmethod
    def _clean_line(item: Any) -> dict[str, Any] | None:
        if not isinstance(item, dict) or not item.get("name"):
            return None
        name = str(item["name"]).strip()[:200]
        return {
            "name": name,
            "amount": _num(item.get("amount")),
            "unit": str(item.get("unit") or "").strip().lower()[:10] or None,
            "search": str(item.get("search") or name).strip()[:80],
            "category": str(item.get("category") or "Andet")[:40],
            "offer": item.get("offer") or None,
            "must_have": False,
            "product_id": None,
        }

    async def _async_search(self, query: str, at: datetime | None) -> list[Product]:
        """Search REMA, priced now or (at) when the plan is bought."""
        if at is None:
            return await self.client.async_search_products(query, 15)
        return await self.client.async_search_products(query, 15, at=at)

    async def _async_match(
        self, line: dict[str, Any], at: datetime | None = None, offer: Offer | None = None
    ) -> None:
        """Pick a REMA product for a shopping line and price it (now, or at a time)."""
        line.update(product=None, avis_item=None, packages=1, cost=None, note=None)
        line.pop("price_source", None)
        try:
            products = await self._async_search(line["search"], at)
            if not line.get("product_id") and not line.get("must_have"):
                await self._async_match_by_name(line, products, at, offer)
                return
            if not products and line["search"] != line["name"]:
                products = await self._async_search(line["name"], at)
        except RemaError as err:
            line["note"] = f"Søgning fejlede: {err}"
            return

        if line.get("product_id"):
            chosen = next((p for p in products if p.id == line["product_id"]), None)
            if chosen:
                self._apply(line, chosen, int(line["amount"] or 1))
                return
        if line.get("must_have"):
            priced = [p for p in products if p.price]
            if priced:
                self._apply(line, priced[0], int(line["amount"] or 1))
            else:
                line["note"] = "Ingen vare fundet – tilføjes som fritekst"
            return

    def _requirement(
        self, line: dict[str, Any]
    ) -> tuple[Callable[[Product], bool], str, list[str]] | None:
        """The family's rule for this kind of item: (test, label, extra searches)."""
        settings = self.store.settings
        kind = line_kind(line)
        if kind == "egg" and settings["egg_min"] != "caged":
            level = _EGG_LEVEL[settings["egg_min"]]
            if level == 1:
                return (
                    lambda p: egg_level(p) >= 1,
                    "frilandsæg eller økologiske æg",
                    ["frilandsæg", "økologiske æg"],
                )
            return lambda p: egg_level(p) >= 2, "økologiske æg", ["økologiske æg", "øko æg"]
        if (kind == "milk" and settings["milk_organic"]) or (
            kind == "produce" and settings["produce_organic"]
        ):
            label = "økologisk mælk" if kind == "milk" else "økologisk frugt og grønt"
            search = line["search"]
            return lambda p: p.is_organic, label, [f"økologisk {search}", f"øko {search}"]
        return None

    async def _async_search_candidates(
        self,
        line: dict[str, Any],
        first: list[Product],
        require: Callable[[Product], bool] | None,
        at: datetime | None = None,
        offer: Offer | None = None,
        offered: list[Product] | None = None,
    ) -> tuple[list[Product], dict[int, float]]:
        """Try the search terms in turn until a product matches by name.

        With an avis offer, first look for the product the offer is for
        (``offered``: those products as REMA has them, then searching for the
        offer's own name); only then for anything that fits.
        """
        queries = search_queries(line)
        found: dict[str, list[Product]] = {queries[0]: first}
        if offer is not None and offered:
            candidates, penalty = self._candidates(
                line, offered, line["search"], require, offer, limit=len(offered)
            )
            if candidates:
                return candidates, penalty
        passes: list[tuple[Offer | None, list[str]]] = []
        if offer is not None:
            passes.append((offer, [*queries, offer_query(offer, line["name"])]))
        passes.append((None, queries))
        poor: tuple[list[Product], dict[int, float]] | None = None
        for this_offer, terms in passes:
            for query in terms:
                if query not in found:
                    try:
                        found[query] = await self._async_search(query, at)
                    except RemaError:
                        found[query] = []
                candidates, penalty = self._candidates(
                    # With an offer, the products must still be what the line asks
                    # for, also when found by the offer's own name.
                    line,
                    found[query],
                    query if this_offer is None else line["search"],
                    require,
                    this_offer,
                )
                if not candidates:
                    continue
                if this_offer is not None or min(penalty.get(p.id, 1.0) for p in candidates) < 5:
                    return candidates, penalty
                # Only something else by that name ("laks": smoked salmon);
                # the line's own name ("Laksefilet") may find the real thing.
                poor = poor or (candidates, penalty)
        return poor or ([], {})

    async def _async_match_by_name(
        self,
        line: dict[str, Any],
        first: list[Product],
        at: datetime | None = None,
        offer: Offer | None = None,
    ) -> None:
        """Choose the best product by name, the family's rules and price."""
        offered = await self._async_offered(offer, at)
        if (
            offer is not None
            and offered == []
            and not offer.unlinked
            and self._store_only(line, offer)
        ):
            return
        requirement = self._requirement(line)
        require = requirement[0] if requirement else None
        note: str | None = None
        candidates, penalty = await self._async_search_candidates(
            line, first, require, at, offer, offered
        )
        if not candidates and requirement:
            # None of the usual results meet the rule: search for it directly.
            for query in requirement[2]:
                try:
                    products = await self._async_search(query, at)
                except RemaError:
                    continue
                for words in (line["search"], line["name"]):
                    candidates, penalty = self._candidates(line, products, words, require)
                    if candidates:
                        break
                if candidates:
                    break
            if not candidates:
                candidates, penalty = await self._async_search_candidates(line, first, None, at)
                note = f"Ingen vare opfylder kravet om {requirement[1]} – billigste valgt"
        if not candidates:
            # Better a free-text line than a wrong product.
            line["note"] = "Ingen sikker vare fundet – tilføjes som fritekst"
            return
        need = to_base(line["amount"], line["unit"]) if line.get("amount") else None
        if need and need[0] in ("g", "ml"):
            # 3 kg potatoes: only products whose size can be counted in kg,
            # not one sweet potato sold per piece.
            comparable = [
                p for p in candidates if (size := package_size(p.underline)) and size[0] == need[0]
            ]
            candidates = comparable or candidates

        def package_cost(product: Product) -> float:
            return packages_needed(line["amount"], line["unit"], product) * (product.price or 0)

        cost = package_cost

        def fit(product: Product) -> tuple[float, bool, float]:
            # Same cost: an offer beats the normal price, and more beats less.
            size = package_size(product.underline)
            return (
                cost(product) * penalty.get(product.id, 1.0),
                not product.is_advertised,
                -(size[1] if size else 0),
            )

        settings = self.store.settings
        if line.get("prefer") == "relevance":
            # Typed by a person ("letmælk"): only products named close to it,
            # then the lowest price per litre/kilo, so 1 L beats a 250 ml carton.
            best_fit = min(penalty.get(p.id, 1.0) for p in candidates)
            candidates = [p for p in candidates if penalty.get(p.id, 1.0) <= best_fit + 0.5]
            unit = next((p.compare_unit for p in candidates if p.compare_unit_price), None)

            def unit_cost(product: Product) -> float:
                if unit is None:
                    return product.price or 0
                if product.compare_unit == unit and product.compare_unit_price:
                    return product.compare_unit_price
                return math.inf  # cannot be compared per litre/kilo

            cost = unit_cost
            # min() keeps REMA's own order on ties.
            cheapest = min(candidates, key=lambda p: (cost(p), not p.is_advertised))
        else:
            cheapest = min(candidates, key=fit)
        # An organic alternative must be the same kind of product, not just organic.
        organic = [
            p
            for p in candidates
            if p.is_organic and penalty.get(p.id, 1.0) <= penalty.get(cheapest.id, 1.0) + 0.5
        ]
        best_organic = min(organic, key=fit) if organic else None
        chosen = cheapest
        if settings["organic"] == "only":
            if best_organic:
                chosen = best_organic
            else:
                line["note"] = "Ingen økologisk variant fundet"
        elif settings["organic"] == "prefer" and best_organic:
            limit = cost(cheapest) * (1 + settings["organic_max_extra_pct"] / 100)
            if cost(best_organic) <= limit + 0.001:
                chosen = best_organic
        self._apply(line, chosen, packages_needed(line["amount"], line["unit"], chosen))
        if note:
            line["note"] = note

    async def _async_offered(
        self, offer: Offer | None, at: datetime | None
    ) -> list[Product] | None:
        """The very products an offer is for, as REMA has them (None: unknown).

        An empty list means REMA's webshop has none of them: a *partivare*,
        sold only in the shops.
        """
        if offer is None or not offer.product_ids:
            return None
        try:
            return await self.client.async_get_products(list(offer.product_ids), at)
        except RemaError:
            return None

    @staticmethod
    def _store_only(line: dict[str, Any], offer: Offer) -> bool:
        """Put an offer REMA's webshop doesn't have on the list as the avis has it.

        Tjek's name for it ("REMA 1000 laksefilet 600g") at the avis's price.
        Before the offer starts, its product is often not in REMA yet: it is
        looked up again when the list is sent (from 02:00 on the shopping day
        it is there, if REMA sells it online). If REMA still doesn't have it,
        it goes on the list as free text, like the webshop does with a
        *partivare*. Only when it is what the line asks for (no meatballs for
        kebab when the AI picked the wrong offer).
        """
        label = (
            offer.product_names[0]
            if len(offer.product_names) == 1
            else f"{offer_query(offer, line['name'])} (tilbud)"
        )
        fits = False
        for text in (line["search"], line["name"]):
            words = [w for w in _tokens(text) if len(w) > 1 and w not in _NEUTRAL_WORDS]
            if words:
                matched, cost = name_fit(words, f"{label} {offer.heading}")
                fits = fits or (matched == len(words) and cost < 5)
        if not fits:
            return False
        packages = avis_packages(line.get("amount"), line.get("unit"), offer)
        start = parse_time(offer.valid_from)
        started = (
            start is None or prices_from(start.astimezone(DANISH_TIME).date()) <= dt_util.utcnow()
        )
        line["avis_item"] = {
            "name": label,
            "underline": offer.quantity,
            "price": offer.price,
            "is_advertised": True,
            "product_ids": list(offer.product_ids or ()),
        }
        line["packages"] = packages
        line["cost"] = round(packages * offer.price, 2) if offer.price else None
        line["price_source"] = "avis"
        line["note"] = (
            "Partivare – kun i butikken, tilføjes som fritekst"
            if started
            else "Avisvare – REMA har den først, når tilbuddet starter; vælges, når listen sendes"
        )
        return True

    def _candidates(
        self,
        line: dict[str, Any],
        products: list[Product],
        query: str,
        require: Callable[[Product], bool] | None = None,
        offer: Offer | None = None,
        limit: int = 12,
    ) -> tuple[list[Product], dict[int, float]]:
        """Products that really are what the line asks for, and a price penalty
        for each (extra words in the name make a product a worse fit).

        With an avis offer, only the products that offer is for.
        """
        priced = [p for p in products[:limit] if p.price and (require is None or require(p))]
        if not priced:
            return [], {}
        words = [w for w in _tokens(query) if len(w) > 1 and w not in _NEUTRAL_WORDS]
        if not words:
            return [], {}
        fits = {p.id: name_fit(words, p.name) for p in priced}
        penalty = {pid: fit[1] for pid, fit in fits.items()}

        if offer is not None:
            # The AI built the dish on this avis offer: only the product it is
            # for, and only if that is also what the line asks for.
            fitting = [
                p
                for p in priced
                if fits[p.id][0] and offer_covers(offer, p.id, p.name, p.underline, p.is_organic)
            ]
            return (self._free_from(fitting), penalty) if fitting else ([], penalty)

        best = max(fit[0] for fit in fits.values())
        if best == 0:
            return [], penalty  # nothing is called what we searched for
        if line.get("prefer") == "relevance" and best < len(words):
            # Typed by a person: every word must fit, or "kage til Anna" could
            # become anything with "ana" in it. Free text is the safe answer.
            return [], penalty
        relevant = [p for p in priced if fits[p.id][0] == best]
        # "Laksefilet" searched as "laks": products that are what the line is
        # called beat the rest (salmon fillet, not salmon in pastry).
        named = [
            w for w in _tokens(line.get("name") or "") if len(w) > 1 and w not in _NEUTRAL_WORDS
        ]
        if named and named != words:
            full = {p.id for p in relevant if name_fit(named, p.name)[0] == len(named)}
            if full:
                for p in relevant:
                    if p.id not in full:
                        penalty[p.id] = penalty.get(p.id, 1.0) + 5.0
        # Stay in the department of the best-fitting product (fish, not cold cuts).
        anchor = min(relevant, key=lambda p: penalty.get(p.id, 1.0)).department
        relevant = [p for p in relevant if p.department == anchor] or relevant
        return self._free_from(relevant), penalty

    def _free_from(self, relevant: list[Product]) -> list[Product]:
        """Prefer gluten-free / lactose-free products when the family needs them."""
        for allergy in self.store.settings["allergies"]:
            marker = FREE_FROM.get(allergy)
            if marker:
                free = [p for p in relevant if marker in f"{p.name} {p.underline or ''}".upper()]
                if free:
                    relevant = free
        return relevant

    @staticmethod
    def _avis_price(line: dict[str, Any], offer: Offer | None) -> None:
        """Use the avis's price for a line built on an offer REMA doesn't show yet.

        REMA only has an offer's price once it takes effect (02:00 on its first
        day), so a plan made before that would otherwise get the normal price.
        """
        product = line.get("product")
        if not offer or not offer.price or not product:
            return
        if product.get("price") and product["price"] <= offer.price:
            return  # REMA already has the offer, or its own price is lower anyway
        if not offer_covers(
            offer,
            product.get("id"),
            product.get("name") or "",
            product.get("underline"),
            bool(product.get("is_organic")),
        ):
            return  # another product than the one on offer
        product["normal_price"] = product.get("price")
        product["price"] = offer.price
        product["is_advertised"] = True
        line["cost"] = round(line["packages"] * offer.price, 2)
        line["price_source"] = "avis"

    @staticmethod
    def _apply(line: dict[str, Any], product: Product, packages: int) -> None:
        line["packages"] = packages
        line["cost"] = round(packages * (product.price or 0), 2)
        line["product"] = {
            "id": product.id,
            "name": product.name,
            "underline": product.underline,
            "price": product.price,
            "normal_price": product.normal_price,
            "is_advertised": product.is_advertised,
            "is_campaign": product.is_campaign,
            "is_organic": product.is_organic,
            "image": product.image,
            "department": product.department,
            "category": product.category,
            "labels": product.labels,
        }

    # ------------------------------------------------------------- sending

    async def async_quick_add(self, text: str) -> dict[str, Any]:
        """Add something typed by a person: a matching REMA product, else free text."""
        amount, name = parse_quick_add(text)
        if not name:
            raise _invalid("empty_quick_add")
        line: dict[str, Any] = {
            "name": name,
            "search": name,
            "amount": amount,
            "unit": "pk",
            "category": None,
            "offer": None,
            "must_have": False,
            "product_id": None,
            "prefer": "relevance",
        }
        await self._async_match(line)
        product = line.get("product")
        if product:
            await self._add_items([{"product_id": product["id"], "amount": line["packages"]}])
            added = (
                f"{line['packages']} × {product['name']}"
                if line["packages"] > 1
                else product["name"]
            )
            if product.get("underline"):
                added += f" ({product['underline'].split('/')[0].strip()})"
        else:
            await self._add_items([{"name": name, "amount": amount}])
            added = f"{amount} × {name}" if amount > 1 else name
        return {
            "text": text,
            "added": added,
            "product_id": product["id"] if product else None,
            "free_text": product is None,
            "note": line.get("note"),
        }

    async def async_send(self, plan_id: str | None = None, part: str = "main") -> dict[str, Any]:
        """Put a plan's shopping list on the primary REMA list.

        part: "main" (bought on the shopping day), "late" (the items for later
        in the week, e.g. thursday offers) or "all".
        """
        plan = self.store.get_plan(plan_id) if plan_id else self.store.latest_plan
        if plan is None:
            raise _invalid("no_plan" if not plan_id else "plan_not_found")
        items: list[dict[str, Any]] = []
        lines = [
            line
            for line in plan["shopping"]
            if (part == "all" or bool(line.get("buy_from")) == (part == "late"))
            and not line.get("buy_at")  # bought in another shop
        ]
        # The offers' products and prices as REMA has them now (once they run).
        try:
            await self._async_refresh_lines(plan, lines)
        except RemaError as err:
            _LOGGER.debug("Could not look at the offers again before sending: %s", err)
        await asyncio.gather(*(self._async_resolve_avis_item(line) for line in lines))
        plan["total"] = round(sum(line.get("cost") or 0 for line in plan["shopping"]), 2)
        for line in lines:
            if line.get("product"):
                items.append({"product_id": line["product"]["id"], "amount": line["packages"]})
            elif line.get("avis_item"):
                # Only in the shops: the avis's name, as the webshop puts it on.
                items.append({"name": line["avis_item"]["name"], "amount": line["packages"]})
            else:
                amount = line.get("amount")
                label = line["name"]
                if amount and line.get("unit") and line["unit"] != "pk":
                    label += f" ({amount:g} {line['unit']})"
                items.append({"name": label, "amount": int(line.get("packages") or 1)})
        if items:
            await self._add_items(items)
        for key in {"main": ("send_at",), "late": ("late_send_at",)}.get(
            part, ("send_at", "late_send_at")
        ):
            plan.pop(key, None)  # sent: nothing left to send automatically
            self._cancel_send(plan["id"], key)
        await self.store.async_mark_sent(plan["id"], part)
        self._notify()
        return plan

    async def _async_resolve_avis_item(self, line: dict[str, Any]) -> None:
        """An avis item REMA didn't have when the plan was made: REMA's product now.

        From 02:00 on an offer's first day REMA has its products (unless it is
        a partivare, only sold in the shops); then the line gets the real
        product, at REMA's price. Otherwise it stays free text.
        """
        item = line.get("avis_item")
        if line.get("product") or not item or not item.get("product_ids"):
            return
        try:
            products = await self.client.async_get_products(list(item["product_ids"]))
        except RemaError as err:
            _LOGGER.debug("Could not look up %s: %s", item["name"], err)
            return
        candidates: list[Product] = []
        for text in (line["search"], line["name"], item["name"]):
            candidates, _penalty = self._candidates(line, products, text, limit=len(products))
            if candidates:
                break
        if not candidates:
            return

        def cost(product: Product) -> float:
            return packages_needed(line.get("amount"), line.get("unit"), product) * (
                product.price or 0
            )

        chosen = min(candidates, key=cost)
        self._apply(line, chosen, packages_needed(line.get("amount"), line.get("unit"), chosen))
        line["note"] = None
        line.pop("price_source", None)  # REMA's own price now

    async def async_refresh_offers(self, plan_id: str, part: str = "all") -> dict[str, Any]:
        """Match a plan's offer items again, now REMA has the offers' products and prices.

        A plan is made from the avis days before it starts; REMA gets the
        offers' products and prices at 02:00 on their first day (a new product
        like the 600 g salmon fillet only appears then). Items whose offer has
        not started yet are left as they are.
        """
        plan = self.store.get_plan(plan_id)
        if plan is None:
            raise _invalid("plan_not_found")
        lines = [
            line
            for line in plan["shopping"]
            if part == "all" or bool(line.get("buy_from")) == (part == "late")
        ]
        await self._async_refresh_lines(plan, lines)
        await self.store.async_save()
        self._notify()
        return plan

    async def _async_refresh_lines(self, plan: dict[str, Any], lines: list[dict[str, Any]]) -> None:
        now = dt_util.utcnow()
        due = [
            line
            for line in lines
            if line.get("offer_name")
            and not line.get("must_have")
            and not line.get("added")
            and not line.get("product_id")
            and not line.get("buy_at")
            and prices_from(date.fromisoformat(line.get("buy_from") or plan["start_date"])) <= now
        ]
        catalog_id = (plan.get("catalog") or {}).get("id")
        if not due or not catalog_id:
            return
        offers = await self.client.async_get_offers(catalog_id)
        by_heading = {
            offer.heading: offer
            for offer in await self.client.async_get_offer_products(
                [o for o in offers if o.heading in {line["offer_name"] for line in due}]
            )
        }
        semaphore = asyncio.Semaphore(SEARCH_CONCURRENCY)

        async def refresh(line: dict[str, Any]) -> None:
            offer = by_heading.get(line["offer_name"])
            if offer is None:
                return  # not in the avis any more: leave it
            async with semaphore:
                await self._async_match(line, None, offer)
            self._avis_price(line, offer)

        await asyncio.gather(*(refresh(line) for line in due))
        plan["total"] = round(sum(line.get("cost") or 0 for line in plan["shopping"]), 2)
        plan["refreshed_at"] = now.isoformat()

    @callback
    def _schedule_refreshes(self, plan: dict[str, Any]) -> None:
        """Look at the plan's offers again at 02:00 on the shopping day (and thursday)."""
        now = dt_util.utcnow()
        main_at = prices_from(date.fromisoformat(plan["start_date"]))
        if main_at > now:
            plan["refresh_at"] = main_at.isoformat()
            self._schedule_send(plan, "refresh_at")
        late = sorted(line["buy_from"] for line in plan["shopping"] if line.get("buy_from"))
        if late and prices_from(date.fromisoformat(late[0])) > now:
            plan["late_refresh_at"] = prices_from(date.fromisoformat(late[0])).isoformat()
            self._schedule_send(plan, "late_refresh_at")

    @callback
    def async_restore_sends(self) -> None:
        """Schedule the automatic sends and refreshes that were waiting (after a restart)."""
        for plan in self.store.plans:
            if plan.get("send_at") and plan.get("status") != "sent":
                self._schedule_send(plan, "send_at")
            if plan.get("late_send_at") and not plan.get("late_sent_at"):
                self._schedule_send(plan, "late_send_at")
            for key in ("refresh_at", "late_refresh_at"):
                if plan.get(key):
                    self._schedule_send(plan, key)

    async def _async_send_when_ready(self, plan: dict[str, Any]) -> None:
        """Send a plan automatically once REMA has its products and prices.

        The avis is out days before it starts, but REMA's products and prices
        for it (and new products on offer) come at 02:00 on the shopping day;
        thursday's offers at 02:00 that thursday.
        """
        now = dt_util.utcnow()
        main_at = prices_from(date.fromisoformat(plan["start_date"]))
        if main_at <= now:
            await self.async_send(plan["id"], "main")
        else:
            plan["send_at"] = main_at.isoformat()
            self._schedule_send(plan, "send_at")
        late = sorted(line["buy_from"] for line in plan["shopping"] if line.get("buy_from"))
        if late:
            plan["late_send_at"] = prices_from(date.fromisoformat(late[0])).isoformat()
            self._schedule_send(plan, "late_send_at")
        await self.store.async_save()
        self._notify()

    @callback
    def _schedule_send(self, plan: dict[str, Any], key: str) -> None:
        when = parse_time(plan.get(key))
        if when is None:
            return
        self._cancel_send(plan["id"], key)
        if date.fromisoformat(plan["end_date"]) < dt_util.now().date():
            plan.pop(key, None)  # the week is over; nothing to buy any more
            return
        part = "late" if key.startswith("late_") else "main"
        plan_id = plan["id"]
        work = self._async_refresh_due if key.endswith("refresh_at") else self._async_send_due

        @callback
        def _due(_now: datetime) -> None:
            self._sends.pop((plan_id, key), None)
            self.hass.async_create_task(work(plan_id, part), name=f"{DOMAIN} {key}")

        # A time that has passed (HA was off at 02:00) fires right away.
        self._sends[(plan_id, key)] = async_track_point_in_utc_time(
            self.hass, _due, max(when, dt_util.utcnow())
        )

    @callback
    def _cancel_send(self, plan_id: str, key: str) -> None:
        if unsub := self._sends.pop((plan_id, key), None):
            unsub()

    async def _async_refresh_due(self, plan_id: str, part: str) -> None:
        plan = self.store.get_plan(plan_id)
        if plan is None:
            return
        plan.pop("late_refresh_at" if part == "late" else "refresh_at", None)
        if plan.get("late_send_at" if part == "late" else "send_at"):
            await self.store.async_save()
            return  # sent automatically now, which looks at the offers again first
        try:
            await self.async_refresh_offers(plan_id, part)
        except (HomeAssistantError, RemaError) as err:
            _LOGGER.warning("Could not look at the meal plan's offers again: %s", err)
            await self.store.async_save()

    async def _async_send_due(self, plan_id: str, part: str) -> None:
        if self.store.get_plan(plan_id) is None:
            return
        try:
            await self.async_send(plan_id, part)
        except (HomeAssistantError, RemaError) as err:
            _LOGGER.warning("Could not send the meal plan to REMA automatically: %s", err)

    # ------------------------------------------------------------- automatic

    @callback
    def async_check_auto_generate(self, upcoming: Catalog | None) -> None:
        """Make next week's plan when the new avis is out (if switched on)."""
        settings = self.store.settings
        if not settings["auto_generate"] or upcoming is None or self.generating:
            return
        start = self.default_start()
        if start == dt_util.now().date():
            start += timedelta(days=7)
        if not (
            upcoming.valid_from
            and upcoming.valid_to
            and upcoming.valid_from.date() <= start <= upcoming.valid_to.date()
        ):
            return
        key = start.isoformat()
        if self.store.plan_for_start(start) or key in self._auto_attempted:
            return
        self._auto_attempted.add(key)
        _LOGGER.info("New tilbudsavis found, making the meal plan for %s", key)
        try:
            self.async_start_generation(start, send=settings["auto_send"])
        except HomeAssistantError as err:
            _LOGGER.warning("Could not make the meal plan for %s automatically: %s", key, err)

    @callback
    def async_cancel(self) -> None:
        """Stop a running generation and the waiting sends (on unload)."""
        if self._task and not self._task.done():
            self._task.cancel()
        for unsub in self._sends.values():
            unsub()
        self._sends.clear()


_QUICK_COUNT = re.compile(
    r"^\s*(\d{1,2})\s*"
    r"(?:x|×|\*|stk\.?|styk(?:ker)?|pk\.?|pakk(?:e|er)|pos(?:e|er)|dås(?:e|er)|flask(?:e|er)|bakk(?:e|er))?"
    r"\s+(?!(?:g|gr|kg|gram|l|ml|dl|cl|liter)\b)(.+?)\s*$",
    re.IGNORECASE,
)
# Siri and Assist often write small numbers as words.
_NUMBER_WORDS = {
    "en": 1, "et": 1, "to": 2, "tre": 3, "fire": 4, "fem": 5, "seks": 6,
    "syv": 7, "otte": 8, "ni": 9, "ti": 10, "elleve": 11, "tolv": 12,
}  # fmt: skip
_NUMBER_WORD = re.compile(rf"^\s*({'|'.join(_NUMBER_WORDS)})(?=\s)", re.IGNORECASE)


def parse_quick_add(text: str) -> tuple[int, str]:
    """'3 x æg', '3x æg', '3 stk æg', '3 æg' and 'tre æg' -> (3, 'æg').

    '500 g mel' stays as text.
    """
    # Shortcuts can wrap the text in quotes or <...>.
    text = (text or "").strip().strip("<>\"'“”„«»").strip()
    text = _NUMBER_WORD.sub(lambda m: str(_NUMBER_WORDS[m.group(1).lower()]), text)
    if match := _QUICK_COUNT.match(text):
        return max(1, int(match.group(1))), match.group(2)
    if glued := re.match(r"^\s*(\d+)\s*[x×*](\S.*)$", text):  # '3xæg'
        return max(1, int(glued.group(1))), glued.group(2).strip()
    return 1, text


def plan_summary(plan: dict[str, Any]) -> dict[str, Any]:
    """The fields of a plan needed for lists."""
    return {
        key: plan.get(key)
        for key in ("id", "title", "start_date", "end_date", "week", "status", "total", "budget")
    } | {"dishes": [day["dish"] for day in plan.get("days", [])]}


def _local_day(moment: datetime) -> date:
    """The local day of a moment (an avis from 22:00 UTC starts the next day here)."""
    return dt_util.as_local(moment).date()


def plan_dates(start: date, days: int, skip: set[date] | None = None) -> list[date]:
    """The days of a plan that get a dinner."""
    return [d for d in (start + timedelta(days=i) for i in range(days)) if d not in (skip or set())]


def parse_date(value: str | None) -> date | None:
    """Parse an ISO date from the panel."""
    if not value:
        return None
    try:
        return datetime.fromisoformat(value).date()
    except ValueError as err:
        raise _invalid("invalid_date", value=value) from err
