"""Other chains' offers (Netto, Lidl, føtex …) from Tjek, the same source as REMA's avis.

The app stays a REMA 1000 app: other chains' offers are shown on their own
pages, and the shopping list says where an item is cheaper this week. An item
can be moved to that shop's own list (``line["buy_at"]`` = the chain's Tjek
dealer id); it is then not sent to the REMA list.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
import logging
import time
from typing import TYPE_CHECKING, Any
import uuid

import aiohttp

from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import Offer, parse_time
from .const import DOMAIN

if TYPE_CHECKING:
    from .mealplan import MealPlanner

_LOGGER = logging.getLogger(__name__)

TJEK = "https://squid-api.tjek.com"
TIMEOUT = aiohttp.ClientTimeout(total=30)
OFFER_CACHE = 3600
DEALER_CACHE = 86400
MAX_OFFERS = 800
MIN_SAVING = 1.0  # kr. per item; less is not worth a trip
# REMA 1000 on Tjek: its avis is shown with the other chains' on the front page.
REMA_ID = "11deC"
# Grocery chains on Tjek (eTilbudsavis): their dealer ids.
CHAINS: dict[str, str] = {
    "9ba51": "Netto",
    "71c90": "Lidl",
    "bdf5A": "føtex",
    "93f13": "Bilka",
    "DWZE1w": "365discount",
    "267e1m": "MENY",
    "0b1e8": "SuperBrugsen",
    "c1edq": "Kvickly",
    "d311fg": "Brugsen",
    "88ddE": "SPAR",
    "65caN": "Løvbjerg",
    "603dfL": "Min Købmand",
    "70d42L": "ABC Lavpris",
}
# The chains the meal plan is made with, the family's favourite shop first:
# items that are not on offer anywhere go to the first one.
PLAN_CHAINS_DEFAULT = ["9ba51", "71c90", REMA_ID]  # Netto, Lidl, REMA 1000
# Aviser that are not about food.
_NONFOOD = (
    "nonfood", "non-food", "legetøj", "elektronik", "bolig", "have", "tekstil", "jul",
    "skønhed", "velvære", "ud af huset", "katalog", "magasin", "prosonic", "halloween",
)  # fmt: skip


class ChainError(HomeAssistantError):
    """Tjek could not be reached for another chain's offers."""


def _invalid(key: str) -> ServiceValidationError:
    return ServiceValidationError(translation_domain=DOMAIN, translation_key=key)


def is_food_catalog(label: str | None) -> bool:
    """A weekly food avis, not a toy or electronics catalogue."""
    text = str(label or "").lower()
    return not any(word in text for word in _NONFOOD)


def offer_dict(data: dict[str, Any], dealer_id: str) -> dict[str, Any]:
    """A Tjek offer for the panel."""
    offer = Offer.from_api(data)
    images = data.get("images") or {}
    return {
        **offer.as_dict(),
        "dealer_id": dealer_id,
        "image": images.get("thumb") or images.get("view"),
    }


def as_offer(entry: dict[str, Any]) -> Offer:
    """A stored offer dict as an Offer again (to match it)."""
    return Offer(
        id=entry["id"],
        heading=entry["heading"],
        description=entry.get("description"),
        price=entry.get("price"),
        pre_price=entry.get("pre_price"),
        quantity=entry.get("quantity"),
        valid_from=entry.get("valid_from"),
        valid_to=entry.get("valid_to"),
    )


def runs_on(entry: dict[str, Any], day: date) -> bool:
    """The offer can be bought on a day."""
    start = parse_time(entry.get("valid_from"))
    end = parse_time(entry.get("valid_to"))
    moment = datetime.combine(day, datetime.min.time(), tzinfo=UTC) + timedelta(hours=12)
    return (start is None or start <= moment) and (end is None or moment <= end)


def chain_name(dealer_id: str) -> str:
    """A chain's name ("REMA 1000", "Netto" …)."""
    return "REMA 1000" if dealer_id == REMA_ID else CHAINS.get(dealer_id, dealer_id)


def plan_offers(
    chain_offers: dict[str, list[dict[str, Any]]], day: date
) -> dict[str, dict[str, Any]]:
    """Other chains' offers that can be bought on the shopping day, by their id for the AI.

    REMA's offers keep their "o<i>" ids; another chain's are its name and a
    number ("netto3", "lidl12").
    """
    out: dict[str, dict[str, Any]] = {}
    for dealer_id, entries in chain_offers.items():
        slug = "".join(ch for ch in chain_name(dealer_id).lower() if "a" <= ch <= "z") or "c"
        running = [entry for entry in entries if runs_on(entry, day)]
        for idx, entry in enumerate(running):
            out[f"{slug}{idx}"] = {**entry, "dealer_id": dealer_id}
    return out


def plan_offer_lines(offers: dict[str, dict[str, Any]]) -> list[str]:
    """Other chains' offers for the AI, as "netto3 | Netto: vare | pris | mængde" lines."""
    lines = []
    for key, entry in offers.items():
        price = f"{entry['price']:g} kr." if entry.get("price") is not None else "?"
        if entry.get("pre_price"):
            price += f" (før {entry['pre_price']:g})"
        qty = entry.get("quantity") or ""
        name = f"{chain_name(entry['dealer_id'])}: {entry['heading']}"
        lines.append(f"{key} | {name} | {price} | {qty}".rstrip(" |"))
    return lines


class ChainOffers:
    """Reads other chains' offers from Tjek's public API."""

    def __init__(self, hass: HomeAssistant) -> None:
        """Initialize."""
        self.hass = hass
        self._dealers: tuple[float, dict[str, dict[str, Any]]] | None = None
        self._offers: dict[str, tuple[float, list[dict[str, Any]]]] = {}

    async def _get(self, path: str, params: dict[str, Any]) -> Any:
        session = async_get_clientsession(self.hass)
        try:
            async with session.get(
                f"{TJEK}{path}",
                params=params,
                headers={"Accept": "application/json"},
                timeout=TIMEOUT,
            ) as resp:
                if resp.status >= 400:
                    raise ChainError(f"Tjek {path} svarede {resp.status}")
                return await resp.json(content_type=None)
        except (aiohttp.ClientError, TimeoutError) as err:
            raise ChainError(f"Kunne ikke nå Tjek: {err}") from err

    def _near(self) -> dict[str, Any]:
        """Home's location, so a chain's local aviser are found too."""
        lat, lng = self.hass.config.latitude, self.hass.config.longitude
        if not lat and not lng:
            return {}
        return {"r_lat": lat, "r_lng": lng, "r_radius": 30000}

    async def async_dealers(self) -> dict[str, dict[str, Any]]:
        """The chains with their name, colour and logo (cached for a day)."""
        if self._dealers and time.monotonic() - self._dealers[0] < DEALER_CACHE:
            return self._dealers[1]
        dealers = {
            dealer_id: {"id": dealer_id, "name": name, "color": None, "logo": None}
            for dealer_id, name in {REMA_ID: "REMA 1000", **CHAINS}.items()
        }
        try:
            data = await self._get(
                "/v2/dealers", {"dealer_ids": ",".join(dealers), "limit": len(dealers)}
            )
        except ChainError as err:
            _LOGGER.debug("Chain logos not read: %s", err)
            return dealers  # names only; try again next time
        for entry in data or []:
            if isinstance(entry, dict) and entry.get("id") in dealers:
                color = str(entry.get("color") or "").strip("#")
                dealers[entry["id"]].update(
                    color=f"#{color}" if color else None, logo=entry.get("logo")
                )
        self._dealers = (time.monotonic(), dealers)
        return dealers

    async def async_offers(self, dealer_id: str, force: bool = False) -> list[dict[str, Any]]:
        """A chain's food offers now and in its next avis (cached for an hour)."""
        if dealer_id not in CHAINS and dealer_id != REMA_ID:
            raise _invalid("chain_not_found")
        cached = self._offers.get(dealer_id)
        if cached and not force and time.monotonic() - cached[0] < OFFER_CACHE:
            return cached[1]
        catalogs = await self._get(
            "/v2/catalogs", {"dealer_ids": dealer_id, "limit": 24, **self._near()}
        )
        now = datetime.now(UTC)
        chosen = [
            c
            for c in catalogs or []
            if isinstance(c, dict)
            and is_food_catalog(c.get("label"))
            and (parse_time(c.get("run_till")) or now) >= now
        ]
        offers: list[dict[str, Any]] = []
        seen: set[str] = set()
        for catalog in chosen:
            offset = 0
            while len(offers) < MAX_OFFERS:
                page = await self._get(
                    "/v2/offers",
                    {"catalog_ids": catalog["id"], "limit": 100, "offset": offset},
                )
                entries = [e for e in page or [] if isinstance(e, dict)]
                for entry in entries:
                    if str(entry.get("id")) not in seen and entry.get("heading"):
                        seen.add(str(entry.get("id")))
                        offers.append(
                            offer_dict(entry, dealer_id) | {"catalog": catalog.get("label")}
                        )
                if len(entries) < 100:
                    break
                offset += 100
        self._offers[dealer_id] = (time.monotonic(), offers)
        return offers


# ------------------------------------------------------------------ comparing


def _equivalent_price(product: dict[str, Any], offer: Offer) -> float | None:
    """The offer's price for as much as one of REMA's packages (None if they can't be compared).

    With a size range ("400-500 g") the smallest size is used, so a saving is never overstated.
    """
    from .mealplan import avis_size, package_size  # noqa: PLC0415

    if offer.price is None:
        return None
    size = package_size(product.get("underline"))
    if size is None or size[0] == "pack":
        return offer.price
    sizes = avis_size(offer, size[0])
    if not sizes or sizes[0] <= 0:
        return None
    return offer.price * size[1] / sizes[0]


def _same_kind(product: dict[str, Any], offer: Offer) -> bool:
    """Every word of REMA's name is in the offer (also inside a compound word, "mælk" in
    "letmælk"), nothing in it makes it another product, and fat % and organic are the same."""
    from .mealplan import _NEUTRAL_WORDS, _percents, _tokens, name_fit  # noqa: PLC0415

    name = str(product.get("name") or "")
    words = [w for w in _tokens(name) if len(w) > 1 and w not in _NEUTRAL_WORDS]
    if not words:
        return False
    matched, penalty = name_fit(words, f"{offer.heading} {offer.description or ''}")
    if matched < len(words) or penalty >= 5:
        return False
    text = f"{offer.heading}\n{offer.description or ''}"
    theirs, ours = _percents(text), _percents(name)
    if theirs and ours and not theirs & ours:
        return False
    return ("økologisk" in _tokens(text)) == bool(product.get("is_organic"))


def cheaper_offer(
    line: dict[str, Any], offers: list[dict[str, Any]], day: date
) -> dict[str, Any] | None:
    """The other chain's offer that is the same item as a line, and the cheapest; None if REMA wins."""
    product = line.get("product") or {}
    price = product.get("price")
    if not price or line.get("buy_at"):
        return None
    best: dict[str, Any] | None = None
    for entry in offers:
        if not runs_on(entry, day):
            continue
        offer = as_offer(entry)
        if not _same_kind(product, offer):
            continue
        equivalent = _equivalent_price(product, offer)
        if equivalent is None or equivalent > price * 0.95 or price - equivalent < MIN_SAVING:
            continue
        saving = round((price - equivalent) * (line.get("packages") or 1), 2)
        if best is None or saving > best["saving"]:
            best = {
                "dealer_id": entry["dealer_id"],
                "offer_id": entry["id"],
                "heading": entry["heading"],
                "description": entry.get("description"),
                "price": entry["price"],
                "per_package": round(equivalent, 2),
                "saving": saving,
                "valid_to": entry.get("valid_to"),
            }
    return best


async def async_compare(planner: MealPlanner, plan_id: str) -> dict[str, Any]:
    """Where the plan's items are cheaper in the family's other chains this week."""
    plan = planner.store.get_plan(plan_id)
    if plan is None:
        raise _invalid("plan_not_found")
    chosen = [d for d in planner.store.settings["chains"] if d in CHAINS]
    offers: list[dict[str, Any]] = []
    for dealer_id in chosen:
        try:
            offers += await planner.chains.async_offers(dealer_id)
        except ChainError as err:
            _LOGGER.debug("Offers of %s not read: %s", dealer_id, err)
    first = date.fromisoformat(plan["start_date"])
    lines: dict[str, dict[str, Any]] = {}
    totals: dict[str, dict[str, Any]] = {}
    for line in plan["shopping"]:
        day = date.fromisoformat(line["buy_from"]) if line.get("buy_from") else first
        if found := cheaper_offer(line, offers, day):
            lines[line["id"]] = found
            total = totals.setdefault(found["dealer_id"], {"count": 0, "saving": 0.0})
            total["count"] += 1
            total["saving"] = round(total["saving"] + found["saving"], 2)
    return {"plan_id": plan["id"], "lines": lines, "chains": totals}


async def async_compare_products(
    planner: MealPlanner, products: list[dict[str, Any]], day: date
) -> dict[str, dict[str, Any]]:
    """REMA products (the family's favourites) that are cheaper in another chain on a day."""
    offers: list[dict[str, Any]] = []
    for dealer_id in [d for d in planner.store.settings["chains"] if d in CHAINS]:
        try:
            offers += await planner.chains.async_offers(dealer_id)
        except ChainError as err:
            _LOGGER.debug("Offers of %s not read: %s", dealer_id, err)
    out: dict[str, dict[str, Any]] = {}
    for product in products[:500]:
        if isinstance(product, dict) and product.get("id") is not None:
            found = cheaper_offer({"product": product, "packages": 1}, offers, day)
            if found:
                out[str(product["id"])] = found
    return out


# ------------------------------------------------------------------ one search, every shop


def _unit(kind: str, amount: float, price: float) -> dict[str, Any]:
    if kind == "g":
        return {"unit": "kg", "price": round(price / amount * 1000, 2)}
    if kind == "ml":
        return {"unit": "l", "price": round(price / amount * 1000, 2)}
    return {"unit": "stk", "price": round(price / amount, 2)}


def product_unit_price(product: dict[str, Any]) -> dict[str, Any] | None:
    """A REMA product's price per kg, litre or piece (from its underline)."""
    from .mealplan import package_size  # noqa: PLC0415

    size = package_size(product.get("underline"))
    price = product.get("price")
    if not size or not price or size[0] == "pack" or size[1] <= 0:
        return None
    return _unit(size[0], size[1], float(price))


def offer_unit_price(entry: dict[str, Any]) -> dict[str, Any] | None:
    """An offer's price per kg, litre or piece (its smallest size, so never too low)."""
    from .mealplan import avis_size  # noqa: PLC0415

    offer = as_offer(entry)
    if offer.price is None:
        return None
    for kind in ("g", "ml", "stk"):
        if (sizes := avis_size(offer, kind)) and sizes[0] > 0:
            return _unit(kind, sizes[0], offer.price)
    return None


def query_words(query: str) -> list[str]:
    """The words of a search ("let mælk" -> ["let", "mælk"])."""
    from .mealplan import _tokens  # noqa: PLC0415

    return [w for w in _tokens(query) if len(w) > 1]


def text_has(words: list[str], text: str) -> bool:
    """Every word is in the text, also inside a longer word ("mælk" in "letmælk")."""
    from .mealplan import _tokens  # noqa: PLC0415

    tokens = _tokens(text)
    return bool(words) and all(any(w in t for t in tokens) for w in words)


def query_fit(query: str, name: str) -> tuple[bool, bool]:
    """Does a name fit a search: (every word is in it, and it is the very kind asked for).

    The kind is wrong if a word makes it another product ("oksekød 35% grønt") or the
    fat % differs ("oksekød 4-7%" for "oksekød 8-12%").
    """
    from .mealplan import _NEUTRAL_WORDS, _percents, name_fit  # noqa: PLC0415

    words = query_words(query)
    words = [w for w in words if w not in _NEUTRAL_WORDS] or words
    if not words:
        return False, False
    matched, penalty = name_fit(words, name)
    if matched < len(words):
        return False, False
    asked, theirs = _percents(query), _percents(name)
    return True, penalty < 5 and not (asked and theirs and not asked & theirs)


async def async_search_everywhere(planner: MealPlanner, query: str) -> dict[str, Any]:
    """REMA's products and the chosen chains' offers for a search, cheapest first."""
    words = query_words(query)
    if not words:
        return {"query": query, "products": [], "offers": [], "best": None}
    products = [p.as_dict() for p in await planner.client.async_search_products(query, 8)]
    fits: dict[int, tuple[bool, bool]] = {}
    for product in products:
        product["unit_price"] = product_unit_price(product)
        fits[id(product)] = query_fit(query, str(product.get("name") or ""))
    # REMA's search also finds near misses (grisekød for oksekød): leave them out
    # when something fits, and put the very kind first.
    if any(fit[0] for fit in fits.values()):
        products = [p for p in products if fits[id(p)][0]]
    products.sort(key=lambda p: not fits[id(p)][1])
    now = datetime.now(UTC)
    offers: list[dict[str, Any]] = []
    for dealer_id in [d for d in planner.store.settings["chains"] if d in CHAINS]:
        try:
            found = await planner.chains.async_offers(dealer_id)
        except ChainError as err:
            _LOGGER.debug("Offers of %s not read: %s", dealer_id, err)
            continue
        for entry in found:
            end = parse_time(entry.get("valid_to"))
            if (end is None or end >= now) and text_has(
                words, f"{entry['heading']} {entry.get('description') or ''}"
            ):
                offers.append({**entry, "unit_price": offer_unit_price(entry)})

    def order(item: dict[str, Any]) -> tuple[int, float]:
        unit = item.get("unit_price")
        return (0, unit["price"]) if unit else (1, float(item.get("price") or 1e9))

    offers.sort(key=order)
    offers = offers[:30]
    # The cheapest of the very kind asked for, compared per kg, litre or piece in
    # the unit most of them have.
    candidates = [("rema", p) for p in products if p.get("unit_price") and fits[id(p)][1]] + [
        ("chain", o)
        for o in offers
        if o.get("unit_price") and query_fit(query, str(o.get("heading") or ""))[1]
    ]
    best: dict[str, Any] | None = None
    if candidates:
        units = [c[1]["unit_price"]["unit"] for c in candidates]
        unit = max(set(units), key=units.count)
        source, item = min(
            (c for c in candidates if c[1]["unit_price"]["unit"] == unit),
            key=lambda c: c[1]["unit_price"]["price"],
        )
        best = {"source": source, "id": item["id"], "unit_price": item["unit_price"]}
    return {"query": query, "products": products, "offers": offers, "best": best}


async def async_add_rema_offer(
    planner: MealPlanner, offer: dict[str, Any], plan_id: str | None
) -> dict[str, Any]:
    """An offer from REMA's avis on the plan's shopping list (else the REMA list)."""
    from .planedit import ADDED_CATEGORY, _new_line, async_add_product, update_total  # noqa: PLC0415

    heading = str(offer.get("heading") or "").strip()[:200]
    if not heading or not offer.get("id"):
        raise _invalid("chain_not_found")
    found = await planner.client.async_get_offer_products([as_offer({**offer, "heading": heading})])
    ids = list(found[0].product_ids or ()) if found else []
    plan = planner.store.get_plan(plan_id) if plan_id else None
    if plan is None:
        await planner._add_items(
            [{"product_id": ids[0], "amount": 1}] if ids else [{"name": heading, "amount": 1}]
        )
        return {"added_to": "rema_list", "name": heading}
    if ids:
        line = await async_add_product(planner, plan["id"], ids[0])
        return {"added_to": "plan", "name": line["name"]}
    line = _new_line(heading, heading, ADDED_CATEGORY, buy_from=None)
    price = offer.get("price")
    line.update(
        amount=1,
        packages=1,
        cost=round(float(price), 2) if price else 0,
        note=offer.get("description"),
    )
    plan["shopping"].append(line)
    update_total(plan)
    await planner.store.async_save()
    planner._notify()
    return {"added_to": "plan", "name": heading}


# ------------------------------------------------------------------ the shops' own lists


def _line(plan: dict[str, Any], line_id: str) -> dict[str, Any]:
    line: dict[str, Any] | None = next(
        (x for x in plan["shopping"] if x.get("id") == line_id), None
    )
    if line is None:
        raise _invalid("line_not_found")
    return line


async def async_move_line(
    planner: MealPlanner,
    plan_id: str,
    line_id: str,
    dealer_id: str | None,
    price: float | None = None,
    heading: str | None = None,
) -> dict[str, Any]:
    """Buy an item in another shop (its price there), or back at REMA."""
    from .planedit import update_total  # noqa: PLC0415

    plan = planner.store.get_plan(plan_id)
    if plan is None:
        raise _invalid("plan_not_found")
    line = _line(plan, line_id)
    if dealer_id is not None and dealer_id not in CHAINS:
        raise _invalid("chain_not_found")
    packages = int(line.get("packages") or 1)
    if dealer_id:
        line["buy_at"] = dealer_id
        line["chain_price"] = price
        line["chain_heading"] = heading
        line["bought"] = False
        if price is not None:
            line["cost"] = round(price * packages, 2)
            line.pop("price_estimated", None)  # the shop's own price now
    elif line.get("chain_only"):
        plan["shopping"].remove(line)
    else:
        for key in ("buy_at", "chain_price", "chain_heading", "bought", "price_estimated"):
            line.pop(key, None)
        product = line.get("product") or {}
        line["cost"] = round((product.get("price") or 0) * packages, 2)
    update_total(plan)
    await planner.store.async_save()
    planner._notify()
    return plan


async def async_add_offer(
    planner: MealPlanner, plan_id: str, offer: dict[str, Any]
) -> dict[str, Any]:
    """Put another chain's offer on its shop's list."""
    from .planedit import update_total  # noqa: PLC0415

    plan = planner.store.get_plan(plan_id)
    if plan is None:
        raise _invalid("plan_not_found")
    dealer_id = str(offer.get("dealer_id") or "")
    heading = str(offer.get("heading") or "").strip()[:200]
    if dealer_id not in CHAINS or not heading:
        raise _invalid("chain_not_found")
    try:
        price = float(offer["price"]) if offer.get("price") is not None else None
    except (TypeError, ValueError):
        price = None
    plan["shopping"].append(
        {
            "id": uuid.uuid4().hex[:8],
            "name": heading,
            "amount": 1,
            "unit": "pk",
            "search": heading.lower(),
            "category": CHAINS[dealer_id],
            "must_have": False,
            "added": True,
            "chain_only": True,  # not a REMA item: deleting it from the shop's list removes it
            "product": None,
            "product_id": None,
            "packages": 1,
            "cost": round(price or 0, 2),
            "buy_at": dealer_id,
            "chain_price": price,
            "chain_heading": heading,
            "bought": False,
            "note": str(offer.get("description") or "")[:200] or None,
        }
    )
    update_total(plan)
    await planner.store.async_save()
    planner._notify()
    return plan


async def async_chain_line(
    planner: MealPlanner,
    plan_id: str,
    line_id: str,
    *,
    bought: bool | None = None,
    packages: int | None = None,
    delete: bool = False,
) -> dict[str, Any]:
    """Tick off, change how many or delete an item on a shop's list."""
    from .planedit import update_total  # noqa: PLC0415

    plan = planner.store.get_plan(plan_id)
    if plan is None:
        raise _invalid("plan_not_found")
    line = _line(plan, line_id)
    if not line.get("buy_at"):
        raise _invalid("line_not_found")
    if delete:
        plan["shopping"].remove(line)
    else:
        if bought is not None:
            line["bought"] = bool(bought)
        if packages is not None:
            line["packages"] = max(1, min(99, int(packages)))
            unit = line.get("chain_price")
            if unit is None and line.get("product"):
                unit = line["product"].get("price")
            line["cost"] = round((unit or 0) * line["packages"], 2)
    update_total(plan)
    await planner.store.async_save()
    planner._notify()
    return plan


async def async_clear_chain(planner: MealPlanner, plan_id: str, dealer_id: str) -> dict[str, Any]:
    """Empty the basket: the shop's ticked-off items are bought and leave the plan."""
    from .planedit import update_total  # noqa: PLC0415

    plan = planner.store.get_plan(plan_id)
    if plan is None:
        raise _invalid("plan_not_found")
    plan["shopping"] = [
        line
        for line in plan["shopping"]
        if not (line.get("buy_at") == dealer_id and line.get("bought"))
    ]
    update_total(plan)
    await planner.store.async_save()
    planner._notify()
    return plan
