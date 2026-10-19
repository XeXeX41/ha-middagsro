/* Middagsro – madplan og indkøb til REMA 1000 i Home Assistant. Ingen build-trin, ingen afhængigheder. */

const WEEKDAYS = ["Mandag", "Tirsdag", "Onsdag", "Torsdag", "Fredag", "Lørdag", "Søndag"];
const AVOID_LABELS = {
  meat: "Kød",
  pork: "Svinekød",
  beef: "Oksekød",
  fish: "Fisk",
  shellfish: "Skaldyr",
  animal_products: "Animalske produkter (vegansk)",
  spicy: "Stærk mad",
};
const ALLERGY_LABELS = {
  gluten: "Gluten",
  lactose: "Laktose",
  milk: "Mælkeprotein",
  egg: "Æg",
  nuts: "Nødder",
  peanuts: "Jordnødder",
  soy: "Soja",
  sesame: "Sesam",
  celery: "Selleri",
  mustard: "Sennep",
  fish: "Fisk",
  shellfish: "Krebsdyr",
  molluscs: "Bløddyr",
  lupin: "Lupin",
  sulphites: "Sulfitter",
};
const FREQ_LABELS = {
  weekly: "Hver uge",
  biweekly: "Hver 2. uge",
  monthly: "Hver måned",
  on_offer: "Kun når på tilbud",
  inspiration: "Til inspiration",
};
const TYPE_LABELS = { normal: "", vegetar: "Vegetar", rester: "Rester", fast: "Fast dag", tom: "Ingen ret" };
const EGG_LABELS = {
  caged: "Skrabeæg (alle æg)",
  free_range: "Mindst frilandsæg",
  organic: "Kun økologiske æg",
};
const GENERATING_MESSAGE = "Madplanen er ved at blive lavet – det tager typisk 1-2 minutter.";
const onOffer = (p) =>
  Boolean(p.is_advertised || p.is_campaign || (p.normal_price && p.price && p.price < p.normal_price - 0.01));
const validTo = (iso) => (iso && !iso.startsWith("2099") ? shortDate(iso.slice(0, 10)) : "");
const STATUS_LABELS = { draft: "Klar", sent: "Sendt", generating: "Laves", error: "Fejl" };
// Line icons for the tab bar (shown when it sits at the bottom on a phone).
const TAB_ICONS = {
  plan: '<svg viewBox="0 0 24 24" aria-hidden="true"><rect x="3.5" y="5" width="17" height="15" rx="2"/><path d="M3.5 10h17M8 3v4M16 3v4M7.5 14h3M13.5 14h3M7.5 17h3"/></svg>',
  recipes: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 7.5c-1.6-1.6-4.3-2.3-8-2.2v12.5c3.7-.1 6.4.6 8 2.2 1.6-1.6 4.3-2.3 8-2.2V5.3c-3.7-.1-6.4.6-8 2.2zM12 7.5V20"/></svg>',
  shopping: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M3 4h2.2l2.3 10.3a1 1 0 0 0 1 .7h8.9a1 1 0 0 0 1-.8L20 8H6.3"/><circle cx="9.5" cy="19" r="1.4"/><circle cx="17" cy="19" r="1.4"/></svg>',
  favorites: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 20s-7.5-4.6-7.5-10.2A4.3 4.3 0 0 1 12 7a4.3 4.3 0 0 1 7.5 2.8C19.5 15.4 12 20 12 20z"/></svg>',
  health: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M3 12h4l2-5 4 10 2-5h6"/></svg>',
  history: '<svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="12" cy="12" r="8.5"/><path d="M12 7.5V12l3 2"/></svg>',
  settings: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 7h9M17 7h3M4 17h3M11 17h9"/><circle cx="15" cy="7" r="2"/><circle cx="9" cy="17" r="2"/></svg>',
};
// On a phone the bottom bar shows the first tabs; the rest sit behind "Mere".
const EXTRA_TABS = new Set(["health", "history", "settings"]);
const MORE_ICON = '<svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="5" cy="12" r="1.4"/><circle cx="12" cy="12" r="1.4"/><circle cx="19" cy="12" r="1.4"/></svg>';
const CLOSE_ICON = '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M6 6l12 12M18 6L6 18"/></svg>';
// Shown on every button that asks the AI for something.
const AI_ICON = '<svg class="ai" viewBox="0 0 24 24" aria-hidden="true"><path d="M10 3.5l1.6 4.6 4.6 1.6-4.6 1.6L10 15.9l-1.6-4.6L3.8 9.7l4.6-1.6z"/><path d="M17.5 13.5l.9 2.4 2.4.9-2.4.9-.9 2.4-.9-2.4-2.4-.9 2.4-.9z"/></svg>';
const aiLabel = (label) => `${AI_ICON}${label}`;
const RATE_ICONS = {
  like: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M7 10.5V20H4.2a.7.7 0 0 1-.7-.7v-8.1a.7.7 0 0 1 .7-.7H7zm0 0 3.6-6.2c.4-.7 1.3-.9 2-.5.6.4.9 1.1.7 1.8L12.6 9h5.6a2 2 0 0 1 2 2.4l-1.3 6.9a2 2 0 0 1-2 1.7H7"/></svg>',
  dislike: '<svg viewBox="0 0 24 24" aria-hidden="true" style="transform:rotate(180deg)"><path d="M7 10.5V20H4.2a.7.7 0 0 1-.7-.7v-8.1a.7.7 0 0 1 .7-.7H7zm0 0 3.6-6.2c.4-.7 1.3-.9 2-.5.6.4.9 1.1.7 1.8L12.6 9h5.6a2 2 0 0 1 2 2.4l-1.3 6.9a2 2 0 0 1-2 1.7H7"/></svg>',
  favorite: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 20s-7.5-4.6-7.5-10.2A4.3 4.3 0 0 1 12 7a4.3 4.3 0 0 1 7.5 2.8C19.5 15.4 12 20 12 20z"/></svg>',
};
const REMA_ID = "11deC"; // REMA 1000 on Tjek: its avis is shown first among the shops
const RATE_LABELS = { like: "Synes om", dislike: "Synes ikke om", favorite: "Favorit" };
const SURPRISE_ICON = '<svg class="ai" viewBox="0 0 24 24" aria-hidden="true"><path d="M4 11h16v9H4zM12 11v9M3 7.5h18V11H3zM12 7.5C10 3 6 4 7.5 6.5 8.4 8 12 7.5 12 7.5zm0 0c2-4.5 6-3.5 4.5-1C15.6 8 12 7.5 12 7.5z"/></svg>';
const RECIPE_SORTS = { name: "Navn", newest: "Senest tilføjet", most_used: "Mest brugt", quickest: "Hurtigst" };
const RECIPE_FILTERS = { all: "Alle", favorite: "Favoritter", like: "Synes om", dislike: "Synes ikke om" };
// 👍, 👎 and ❤️: pressing the same again takes it back, the other one replaces it (as the server does).
const applyRating = (recipe, action) => {
  const r = { ...recipe };
  if (action === "like") Object.assign(r, r.rating === "like" ? { rating: null, favorite: false } : { rating: "like" });
  if (action === "dislike") Object.assign(r, r.rating === "dislike" ? { rating: null } : { rating: "dislike", favorite: false });
  if (action === "favorite") Object.assign(r, r.favorite ? { favorite: false } : { favorite: true, rating: "like" });
  return r;
};
const rateToast = (recipe) =>
  recipe.favorite
    ? `${recipe.name} er en favorit – gemt i opskriftsamlingen.`
    : recipe.rating === "like"
      ? `I synes om ${recipe.name} – gemt i opskriftsamlingen.`
      : recipe.rating === "dislike"
        ? `${recipe.name} kommer ikke på madplanen igen.`
        : `Bedømmelsen af ${recipe.name} er fjernet.`;
const normName = (name) => String(name || "").toLowerCase().split(/\s+/).filter(Boolean).join(" ");
const CREDIT = `<p class="credit">Udviklet af Christian Dinnsen <a class="gh-link" href="https://github.com/Dinnsen" target="_blank" rel="noopener noreferrer" aria-label="Christian Dinnsen på GitHub" title="Christian Dinnsen på GitHub"><svg class="gh" viewBox="0 0 16 16" aria-hidden="true"><path fill="currentColor" d="M8 0C3.58 0 0 3.58 0 8c0 3.54 2.29 6.53 5.47 7.59.4.07.55-.17.55-.38 0-.19-.01-.82-.01-1.49-2.01.37-2.53-.49-2.69-.94-.09-.23-.48-.94-.82-1.13-.28-.15-.68-.52-.01-.53.63-.01 1.08.58 1.23.82.72 1.21 1.87.87 2.33.66.07-.52.28-.87.51-1.07-1.78-.2-3.64-.89-3.64-3.95 0-.87.31-1.59.82-2.15-.08-.2-.36-1.02.08-2.12 0 0 .67-.21 2.2.82.64-.18 1.32-.27 2-.27.68 0 1.36.09 2 .27 1.53-1.04 2.2-.82 2.2-.82.44 1.1.16 1.92.08 2.12.51.56.82 1.27.82 2.15 0 3.07-1.87 3.75-3.65 3.95.29.25.54.73.54 1.48 0 1.07-.01 1.93-.01 2.2 0 .21.15.46.55.38A8.01 8.01 0 0 0 16 8c0-4.42-3.58-8-8-8z"/></svg></a></p>`;
const TABS = [
  ["plan", "Madplan"],
  ["recipes", "Opskrifter"],
  ["shopping", "Indkøb"],
  ["favorites", "Favoritter"],
  ["health", "Sundhed"],
  ["history", "Historik"],
  ["settings", "Indstillinger"],
];

const SETTING_ICONS = {
  plan: TAB_ICONS.plan,
  family: '<svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="8.5" cy="8" r="2.8"/><circle cx="16.5" cy="9.5" r="2.2"/><path d="M3.5 19c.4-3.3 2.4-5.3 5-5.3s4.6 2 5 5.3M13.8 15.2c.8-.9 1.7-1.3 2.7-1.3 2 0 3.5 1.6 3.9 4.6"/></svg>',
  dishes: '<svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="12" cy="13" r="6.5"/><circle cx="12" cy="13" r="3"/><path d="M4 4v5M2.8 4v3M5.2 4v3M4 9v11M20 4c-1.6 1.3-2 3.5-2 6h2v10"/></svg>',
  shopping: TAB_ICONS.shopping,
  rules: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M9 18h6M10 21h4M12 3a6 6 0 0 0-3.5 10.9c.6.5 1 1.2 1 2.1h5c0-.9.4-1.6 1-2.1A6 6 0 0 0 12 3z"/></svg>',
  nutrition: TAB_ICONS.health,
  mealie: TAB_ICONS.recipes,
  chains: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 9.5 5.5 4h13L20 9.5M4 9.5h16M4 9.5c0 1.7 1.3 2.5 2.7 2.5S9.3 11.2 9.3 9.5c0 1.7 1.3 2.5 2.7 2.5s2.7-.8 2.7-2.5c0 1.7 1.3 2.5 2.7 2.5S20 11.2 20 9.5M5.5 12v8h13v-8M10 20v-4.5h4V20"/></svg>',
  app: '<svg viewBox="0 0 24 24" aria-hidden="true"><rect x="7" y="2.5" width="10" height="19" rx="2.5"/><path d="M11 18.5h2"/></svg>',
};

// The settings' sub-pages, with a one-line summary of what is chosen.
const SETTINGS_SECTIONS = (panel) => {
  const f = panel._form;
  const state = panel._state;
  const organic = { only: "Kun økologi", prefer: "Foretræk økologi", none: "Billigst" }[f.organic] || "";
  const allergies = f.allergies.length + (f.allergies_other.trim() ? 1 : 0);
  const dislikes = (state.settings.disliked_dishes || []).length;
  return [
    { key: "plan", title: "Madplan og uge", form: true,
      summary: `${f.days} dage fra ${WEEKDAYS[f.start_weekday].toLowerCase()} · budget ${f.budget} kr.${f.auto_generate ? " · laves automatisk" : ""}` },
    { key: "family", title: "Familien, allergier og undgå", form: true,
      summary: `${f.household.length} personer${allergies ? ` · ${allergies} allergi${allergies === 1 ? "" : "er"}` : ""}${f.avoid.length ? ` · undgår ${f.avoid.length}` : ""}` },
    { key: "dishes", title: "Retter, favoritter og ønsker", form: true,
      summary: `${state.favorites.length} favoritretter · ${dislikes} kan ikke lide · ${f.leftover_days} restedage` },
    { key: "shopping", title: "Indkøb og varer", form: true,
      summary: `${organic}${f.must_haves.length ? ` · ${f.must_haves.length} faste varer` : ""}` },
    { key: "rules", title: "Det skal AI'en huske", form: false,
      summary: `${(state.settings.rules || []).length} punkter` },
    { key: "nutrition", title: "Næring", form: true,
      summary: f.nutrition_enabled ? `${f.kcal_min}–${f.kcal_max} kcal · ${f.protein_pct}/${f.carb_pct}/${f.fat_pct} %` : "Slået fra" },
    { key: "chains", title: "Andre butikker", form: true,
      summary: `Madplan: ${(f.plan_chains?.length ? f.plan_chains : [REMA_ID]).map((id) => panel._chainName(id)).join(", ")}` },
    { key: "mealie", title: "Mealie", form: true,
      summary: state.mealie?.available ? (f.mealie_recipes || f.mealie_calendar ? "Slået til" : "Slået fra") : "Ikke sat op" },
    { key: "app", title: "App på hjemmeskærmen", form: false, summary: "Åbn Middagsro som en app på telefonen" },
  ].map((sec) => ({ ...sec, icon: SETTING_ICONS[sec.key] }));
};

/** Today's date as YYYY-MM-DD in the phone's own time zone. */
function localToday() {
  const now = new Date();
  const pad = (n) => String(n).padStart(2, "0");
  return `${now.getFullYear()}-${pad(now.getMonth() + 1)}-${pad(now.getDate())}`;
}

const esc = (value) =>
  String(value ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);
const kr = (value) =>
  value == null || Number.isNaN(Number(value))
    ? "–"
    : `${Number(value).toLocaleString("da-DK", { minimumFractionDigits: 2, maximumFractionDigits: 2 })} kr.`;
const dateLabel = (iso) => {
  if (!iso) return "";
  const d = new Date(`${iso}T12:00:00`);
  return `${WEEKDAYS[(d.getDay() + 6) % 7]} ${d.getDate()}/${d.getMonth() + 1}`;
};
// "torsdag" for a date.
const dayName = (iso) => {
  const d = new Date(`${localDay(iso)}T12:00:00`);
  return WEEKDAYS[(d.getDay() + 6) % 7].toLowerCase();
};
// "tor 15/10": short weekday and date, for offers that start later in the week.
const dayShort = (iso) => {
  if (!iso) return "";
  const day = localDay(iso);
  const d = new Date(`${day}T12:00:00`);
  return `${WEEKDAYS[(d.getDay() + 6) % 7].slice(0, 3).toLowerCase()} ${shortDate(day)}`;
};
const shortDate = (iso) => {
  if (!iso) return "";
  const d = new Date(`${iso}T12:00:00`);
  return `${d.getDate()}/${d.getMonth() + 1}`;
};
// A timestamp from the avis (often UTC, e.g. 22:00 the day before) as a local day.
const localDay = (iso) => {
  if (!iso) return "";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso.slice(0, 10);
  const pad = (n) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
};
const clone = (obj) => JSON.parse(JSON.stringify(obj));

class Rema1000Panel extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._tab = "plan";
    this._state = null;
    this._plan = null; // the plan being viewed (latest unless chosen in history)
    this._viewingLatest = true;
    this._day = 0;
    this._dayKey = null; // plan + date the recipe day was chosen for
    this._form = null;
    this._dirty = false;
    this._busy = false;
    this._toast = null;
    this._error = null;
    this._search = { query: "", results: [], loading: false };
    this._editFav = null;
    this._settingsSection = null; // the open sub-page of the settings
    this._recipesSub = "week"; // "week" (the plan's recipes) or "collection"
    this._rc = { query: "", sort: "newest", filter: "all", link: "", importing: false };
    this._chains = null; // the chains that can be chosen, with logos
    this._chain = null; // the chain whose offers page is open
    this._chainOffers = {}; // dealer id -> {offers, loading, error}
    this._chainQuery = "";
    this._compare = null; // {key, lines, chains, loading}: plan items cheaper elsewhere
    this._favCompare = {}; // week -> {product id: cheaper offer}
    this._everywhere = { query: "", loading: false, data: null, error: null }; // one search, every shop
    this._newFav = { text: "", frequency: "weekly" };
    this._newDislike = "";
    this._startDate = null;
    this._skip = new Set(); // ISO dates in the next plan that get no dinner
    this._noteOpen = false; // the "wishes for the plan" popup
    this._noteDraft = "";
    // Other popups: a day of the plan (recipe or swap the dish), the basic items.
    this._modal = null;
    this._newRule = "";
    this._editRule = null; // {index, text}
    this._dictating = null; // the field being dictated into
    this._health = null; // {planId, data, loading, error}
    this._shopSearch = { main: { query: "", results: [], loading: false }, late: { query: "", results: [], loading: false } };
    this._moreOpen = false; // the "Mere" sheet on a phone
    this._checked = {}; // ingredient/step ticks per plan+day
    this._timers = {};
    this._favWeek = "current"; // favourites on offer this week or next week
    this._favCache = {}; // week -> {products, on_offer, catalog, fallback}
    this._favsLoading = false;
    this._favsError = null;
    this._favFilter = "";
    this._wake = null;
    this._wakeWanted = false;
    this._onVisibility = () => {
      if (document.visibilityState === "visible" && this._wakeWanted && !this._wake) this._requestWake();
    };
    this.shadowRoot.addEventListener("click", (ev) => this._onClick(ev));
    this.shadowRoot.addEventListener("keydown", (ev) => {
      if (ev.key === "Escape" && (this._noteOpen || this._modal)) {
        this._noteOpen = false;
        if (!this._modal?.busy) this._modal = null;
        this._renderModal();
      }
    });
    this.shadowRoot.addEventListener("input", (ev) => this._onInput(ev));
    this.shadowRoot.addEventListener("change", (ev) => this._onInput(ev));
    this.shadowRoot.addEventListener("touchstart", (ev) => this._onTouchStart(ev), { passive: true });
    this.shadowRoot.addEventListener("touchend", (ev) => this._onTouchEnd(ev), { passive: true });
  }

  set hass(hass) {
    const first = !this._hass;
    this._hass = hass;
    const menu = this.shadowRoot.querySelector("ha-menu-button");
    if (menu) menu.hass = hass;
    if (first) this._load();
  }

  set narrow(narrow) {
    this._narrow = narrow;
    const menu = this.shadowRoot.querySelector("ha-menu-button");
    if (menu) menu.narrow = narrow;
  }

  set panel(panel) {
    this._panel = panel;
  }

  get _static() {
    return this._panel?.config?.static_url || "/middagsro_static";
  }

  /* Images are cached for a long time: the version in the address makes a new version load new images */
  _img(name) {
    const v = this._panel?.config?.version;
    return `${this._static}/${name}${v ? `?v=${encodeURIComponent(v)}` : ""}`;
  }

  connectedCallback() {
    document.addEventListener("visibilitychange", this._onVisibility);
    // No zooming: pinch (Safari's gesture events) and two-finger touches.
    this._noZoom = (ev) => ev.preventDefault();
    this._noPinch = (ev) => {
      if (ev.touches?.length > 1) ev.preventDefault();
    };
    document.addEventListener("gesturestart", this._noZoom, { passive: false });
    document.addEventListener("touchmove", this._noPinch, { passive: false });
    this._tick = setInterval(() => this._tickTimers(), 1000);
    if (this._hass && !this._state) this._load();
  }

  disconnectedCallback() {
    document.removeEventListener("visibilitychange", this._onVisibility);
    document.removeEventListener("gesturestart", this._noZoom);
    document.removeEventListener("touchmove", this._noPinch);
    this._stopDictation?.();
    clearInterval(this._tick);
    clearTimeout(this._poll);
    this._releaseWake();
  }

  // ------------------------------------------------------------------ data

  async _ws(type, data = {}) {
    const entry = this._state?.entry_id ? { entry_id: this._state.entry_id } : {};
    return this._hass.callWS({ type, ...entry, ...data });
  }

  async _load(silent = false, refresh = false) {
    try {
      const state = await this._ws("middagsro/state", refresh ? { refresh: true } : {});
      this._state = state;
      this._error = null;
      if (!this._startDate) this._startDate = state.default_start;
      if (this._viewingLatest) this._plan = state.latest_plan;
      if (!this._form || !this._dirty) this._form = clone(state.settings);
      if (!this._chains) this._loadChains();
    } catch (err) {
      this._error = err?.message || String(err);
    }
    clearTimeout(this._poll);
    if (this._state?.status?.state === "generating") {
      this._poll = setTimeout(() => this._load(true), 3000);
    }
    // Don't redraw the settings form under the user's fingers while polling.
    if (silent && this._tab === "settings") {
      this._renderStatus();
      return;
    }
    this._render();
  }

  _say(message) {
    this._toast = message;
    this._render();
    clearTimeout(this._toastTimer);
    this._toastTimer = setTimeout(() => {
      this._toast = null;
      this._render();
    }, 3500);
  }

  async _run(fn, okMessage) {
    if (this._busy) return;
    this._busy = true;
    this._render();
    try {
      await fn();
      if (okMessage) this._toast = okMessage;
    } catch (err) {
      this._toast = `Fejl: ${err?.message || err}`;
    } finally {
      this._busy = false;
      await this._load();
      clearTimeout(this._toastTimer);
      this._toastTimer = setTimeout(() => {
        this._toast = null;
        this._render();
      }, 3500);
    }
  }

  // ------------------------------------------------------------------ events

  // Saved right away like the favourites, without saving other unsaved settings.
  _saveDislikes(list, okMessage) {
    this._run(async () => {
      const saved = await this._ws("middagsro/settings", {
        settings: { ...this._state.settings, disliked_dishes: list },
      });
      if (this._form) this._form.disliked_dishes = saved.disliked_dishes;
    }, okMessage);
  }

  // To the top of the page. Scrolling <main> into view would tuck its start under the sticky toolbar.
  _toTop() {
    const top = this.shadowRoot.querySelector("#top");
    if (top?.scrollIntoView) top.scrollIntoView({ block: "start" });
    else this.scrollTo?.(0, 0);
  }

  _goTab(key, direction = 0) {
    if (!key || key === this._tab) return;
    this._moreOpen = false;
    this._everywhere = { query: "", loading: false, data: null, error: null };
    this._tab = key;
    if (key !== "recipes") this._releaseWake();
    if (key === "favorites" && !this._favCache[this._favWeek] && !this._favsLoading) this._loadFavs();
    if (key === "health") this._loadHealth(true);
    this._render();
    const content = this.shadowRoot.querySelector("#content");
    if (content && direction) {
      content.classList.remove("from-left", "from-right");
      void content.offsetWidth; // restart the animation
      content.classList.add(direction > 0 ? "from-right" : "from-left");
    }
  }

  // Swipe left/right on the page to go to the next/previous tab.
  _onTouchStart(ev) {
    this._swipe = null;
    if (ev.touches.length !== 1) return;
    const t = ev.touches[0];
    // Leave the screen edges to the system (back gesture, HA's menu).
    if (t.clientX < 24 || t.clientX > innerWidth - 24) return;
    for (const el of ev.composedPath()) {
      if (el === this) break;
      if (!(el instanceof HTMLElement)) continue;
      if (el.matches("input, textarea, select, .tabs, .chips")) return;
      const overflow = getComputedStyle(el).overflowX;
      if ((overflow === "auto" || overflow === "scroll") && el.scrollWidth > el.clientWidth) return;
    }
    this._swipe = { x: t.clientX, y: t.clientY, time: Date.now() };
  }

  _onTouchEnd(ev) {
    const start = this._swipe;
    this._swipe = null;
    if (!start || !ev.changedTouches.length) return;
    const t = ev.changedTouches[0];
    const dx = t.clientX - start.x;
    const dy = t.clientY - start.y;
    if (Math.abs(dx) < 70 || Math.abs(dx) < Math.abs(dy) * 2 || Date.now() - start.time > 700) return;
    if (getSelection()?.toString()) return;
    const keys = TABS.map(([key]) => key);
    const next = keys[keys.indexOf(this._tab) + (dx < 0 ? 1 : -1)];
    this._goTab(next, dx < 0 ? 1 : -1);
  }

  _onClick(ev) {
    const el = ev.target.closest("[data-action]");
    if (!el) return;
    const { action, arg } = el.dataset;
    const actions = {
      tab: () => {
        this._moreOpen = false;
        this._chain = null;
        if (arg === "settings") this._settingsSection = null;
        if (arg === this._tab) {
          this._everywhere = { query: "", loading: false, data: null, error: null };
          this._render();
        }
        else this._goTab(arg);
      },
      more: () => {
        this._moreOpen = !this._moreOpen;
        this._render();
      },
      "fav-refresh": () => this._loadFavs(true),
      "fav-week": () => {
        if (arg === this._favWeek) return;
        this._favWeek = arg;
        if (this._favCache[arg]) this._render();
        else this._loadFavs();
      },
      "note-open": () => {
        this._noteDraft = this._state?.note || "";
        this._noteOpen = true;
        this._renderModal();
        this.shadowRoot.querySelector("#note-text")?.focus();
      },
      "note-close": () => {
        this._noteOpen = false;
        this._renderModal();
      },
      "note-clear": () => {
        this._noteDraft = "";
        this._saveNote();
      },
      "note-save": () => this._saveNote(),
      "note-generate": () => this._saveNote(true),
      "fav-add": () =>
        this._run(
          () => this._ws("middagsro/list/add", { product_id: Number(arg), amount: 1 }),
          "Tilføjet til REMA-listen."
        ),
      "clear-list": () => {
        const count = this._state?.rema_list?.items?.length || 0;
        if (!count) return this._say("REMA-listen er allerede tom.");
        if (!confirm(`Fjern alle ${count} varer fra REMA-listen? Listen er delt, så den bliver også tom i appen.`)) return;
        this._run(() => this._ws("middagsro/list/clear"), "REMA-listen er tømt.");
      },
      generate: () => this._run(() => this._generate(), GENERATING_MESSAGE),
      send: () =>
        this._run(
          () => this._ws("middagsro/send", { plan_id: this._plan?.id, part: arg === "late" ? "late" : "main" }),
          arg === "late" ? "Torsdagsvarerne er sendt til REMA 1000-appen." : "Indkøbslisten er sendt til REMA 1000-appen."
        ),
      "open-day": () => {
        this._day = this._recipeIndex(arg);
        this._dayKey = this._recipeKey();
        this._tab = "recipes";
        this._recipesSub = "week";
        this._render();
      },
      day: () => {
        this._day = Number(arg);
        this._dayKey = this._recipeKey();
        this._render();
      },
      tick: () => {
        this._checked[arg] = !this._checked[arg];
        this._render();
      },
      timer: () => {
        const sep = arg.lastIndexOf("|"); // the key itself contains "|"
        const key = arg.slice(0, sep);
        const minutes = arg.slice(sep + 1);
        if (this._timers[key]) delete this._timers[key];
        else this._timers[key] = Date.now() + Number(minutes) * 60000;
        this._render();
      },
      wake: () => (this._wakeWanted ? this._releaseWake(true) : this._requestWake()),
      "view-plan": () =>
        this._run(async () => {
          this._plan = await this._ws("middagsro/plan", { plan_id: arg });
          this._viewingLatest = this._plan?.id === this._state?.latest_plan?.id;
          this._tab = "plan";
        }),
      "view-latest": () => {
        this._viewingLatest = true;
        this._plan = this._state?.latest_plan;
        this._render();
      },
      "delete-plan": () => {
        if (!confirm("Slet denne madplan fra historikken?")) return;
        this._run(async () => {
          await this._ws("middagsro/plan/delete", { plan_id: arg });
          if (this._plan?.id === arg) {
            this._viewingLatest = true;
          }
        }, "Madplanen er slettet.");
      },
      "rate-day": () => {
        const [planId, date, rate] = String(arg).split("|");
        this._run(async () => {
          this._toast = rateToast(await this._ws("middagsro/recipes/rate_day", { plan_id: planId, date, action: rate }));
        });
      },
      "rate-recipe": () => {
        const [id, rate] = String(arg).split("|");
        const m = this._modal;
        if (m?.kind === "recipe" && !m.recipe.id) {
          // Not saved yet: the rating is saved with it.
          m.recipe = applyRating(m.recipe, rate);
          return this._renderModal();
        }
        this._run(async () => {
          const recipe = await this._ws("middagsro/recipes/rate", { recipe_id: id, action: rate });
          this._toast = rateToast(recipe);
          if (m?.kind === "recipe" && m.recipe.id === id) {
            m.recipe = { ...m.recipe, rating: recipe.rating, favorite: recipe.favorite };
            this._renderModal();
          }
        });
      },
      "recipes-sub": () => {
        this._recipesSub = arg;
        this._render();
      },
      "rc-filter": () => {
        this._rc.filter = arg;
        this._render();
      },
      "rc-import": () => this._recipeImport(),
      "rc-new": () => {
        this._modal = { kind: "recipe", recipe: { id: null, name: "", type: "normal", servings: 4, active_minutes: 0, total_minutes: 0,
          ingredients: [{ amount: "", name: "" }], steps: [{ text: "", minutes: 0 }], tip: "", rating: null, favorite: false, source: "manual" } };
        this._renderModal();
      },
      "rc-open": () => this._recipeOpen(arg),
      "rc-row": () => {
        const m = this._modal;
        if (m?.kind !== "recipe") return;
        const [list, op, idx] = String(arg).split("|");
        const rows = m.recipe[list];
        if (op === "add") rows.push(list === "ingredients" ? { amount: "", name: "" } : { text: "", minutes: 0 });
        else rows.splice(Number(idx), 1);
        this._renderModal();
      },
      "rc-save": () => this._recipeSave(),
      "rc-delete": () => {
        const m = this._modal;
        if (!m?.recipe?.id || !confirm(`Slet "${m.recipe.name}" fra opskriftsamlingen?`)) return;
        this._modal = null;
        this._renderModal();
        this._run(() => this._ws("middagsro/recipes/delete", { recipe_id: m.recipe.id }), "Opskriften er slettet.");
      },
      "rc-plan": () => {
        const m = this._modal;
        if (!m) return;
        m.picking = !m.picking;
        this._renderModal();
      },
      "rc-plan-day": () => this._recipeToPlan(arg),
      surprise: () => this._run(() => this._generate(true), "Madplanen med nye, overraskende retter er ved at blive lavet – det tager typisk 1-2 minutter."),
      everywhere: () => this._everywhereRun(),
      "everywhere-clear": () => {
        this._everywhere = { query: "", loading: false, data: null, error: null };
        if (this._modal?.kind === "where") {
          this._modal = null;
          this._renderModal();
        }
        this._render();
      },
      "ev-rema": () => {
        const product = this._everywhere.data?.products.find((p) => String(p.id) === arg);
        if (!product) return;
        const plan = this._state?.latest_plan;
        this._editPlan(
          () => (plan
            ? this._ws("middagsro/plan/add", { plan_id: plan.id, product_id: product.id, part: "main" })
            : this._ws("middagsro/list/add", { product_id: product.id, amount: 1 })),
          plan ? `${product.name} er sat på indkøbslisten.` : `${product.name} er sat på REMA-listen.`
        );
      },
      "ev-chain": () => {
        const offer = this._everywhere.data?.offers.find((o) => o.id === arg);
        const plan = this._state?.latest_plan;
        if (!offer || !plan) return;
        this._editPlan(
          () => this._ws("middagsro/chains/add", { plan_id: plan.id, offer }),
          `${offer.heading} er sat på ${this._chainName(offer.dealer_id)}-listen under Indkøb.`
        );
      },
      "fav-where": () => {
        const p = (this._favCache[this._favWeek]?.products || []).find((x) => String(x.id) === arg)
          || (this._favCache[this._favWeek]?.on_offer || []).find((x) => String(x.id) === arg);
        if (!p) return;
        this._modal = { kind: "where", title: p.name };
        this._renderModal();
        this._everywhereRun(p.name);
      },
      "plan-help": () => {
        this._planHelp = !this._planHelp;
        this._render();
      },
      "chain-open": () => {
        this._chain = arg;
        this._chainQuery = "";
        this._render();
        this._toTop();
        if (!this._chainOffers[arg]?.offers) this._loadChainOffers(arg);
      },
      "chain-close": () => {
        this._chain = null;
        this._render();
      },
      "chain-refresh": () => this._loadChainOffers(this._chain, true),
      "chain-add": () => {
        const offer = (this._chainOffers[this._chain]?.offers || []).find((o) => o.id === arg);
        const plan = this._state?.latest_plan;
        if (offer && offer.dealer_id === REMA_ID) {
          return this._editPlan(async () => {
            const res = await this._ws("middagsro/chains/rema_add", { offer, plan_id: plan?.id || null });
            this._toast = res.added_to === "plan" ? `${res.name} er sat på indkøbslisten.` : `${res.name} er sat på REMA-listen.`;
          });
        }
        if (!offer || !plan) return this._say("Lav en madplan først – så kan tilbuddet komme på indkøbslisten.");
        this._editPlan(
          () => this._ws("middagsro/chains/add", { plan_id: plan.id, offer }),
          `${offer.heading} er sat på ${this._chainName(offer.dealer_id)}-listen under Indkøb.`
        );
      },
      "chain-move": () => {
        const [lineId, dealer] = String(arg).split("|");
        const found = this._compare?.lines?.[lineId];
        this._compare = null;
        this._editPlan(
          () => this._ws("middagsro/chains/move", { plan_id: this._plan.id, line_id: lineId, dealer_id: dealer || null,
            price: dealer && found ? found.per_package : null, heading: dealer && found ? found.heading : null }),
          dealer ? `Flyttet til ${this._chainName(dealer)}-listen.` : "Flyttet tilbage til REMA-listen."
        );
      },
      "chain-move-all": () => {
        const lines = Object.entries(this._compare?.lines || {}).filter(([, f]) => f.dealer_id === arg);
        this._compare = null;
        this._editPlan(async () => {
          for (const [lineId, f] of lines) {
            await this._ws("middagsro/chains/move", { plan_id: this._plan.id, line_id: lineId, dealer_id: arg, price: f.per_package, heading: f.heading });
          }
        }, `${lines.length} varer er flyttet til ${this._chainName(arg)}-listen.`);
      },
      "chain-tick": () => {
        const line = this._plan?.shopping.find((l) => l.id === arg);
        if (!line) return;
        this._editPlan(() => this._ws("middagsro/chains/line", { plan_id: this._plan.id, line_id: arg, bought: !line.bought }));
      },
      "chain-count": () => {
        const [lineId, delta] = String(arg).split("|");
        const line = this._plan?.shopping.find((l) => l.id === lineId);
        if (!line) return;
        const packages = Math.max(1, Math.min(99, (line.packages || 1) + Number(delta)));
        this._editPlan(() => this._ws("middagsro/chains/line", { plan_id: this._plan.id, line_id: lineId, packages }));
      },
      "chain-delete": () =>
        this._editPlan(() => this._ws("middagsro/chains/line", { plan_id: this._plan.id, line_id: arg, delete: true }), "Varen er slettet."),
      "chain-clear": () => {
        const bought = this._plan.shopping.filter((l) => l.buy_at === arg && l.bought).length;
        if (!bought) return this._say("Sæt flueben ved det, I har købt – så ryddes det fra listen.");
        this._editPlan(() => this._ws("middagsro/chains/clear", { plan_id: this._plan.id, dealer_id: arg }), `Kurven er ryddet – ${bought} varer er købt.`);
      },
      "settings-section": () => {
        if (arg === "chains" && !this._chains) this._loadChains();
        this._settingsSection = arg || null;
        this._render();
        this._toTop();
      },
      "plan-chain-add": () => {
        this._form.plan_chains = [...(this._form.plan_chains || [REMA_ID]), arg];
        this._dirty = true;
        this._render();
      },
      "plan-chain-remove": () => {
        this._form.plan_chains.splice(Number(arg), 1);
        this._dirty = true;
        this._render();
      },
      "plan-chain-move": () => {
        const [idx, step] = arg.split("|").map(Number);
        const list = this._form.plan_chains;
        if (idx + step < 0 || idx + step >= list.length) return;
        [list[idx], list[idx + step]] = [list[idx + step], list[idx]];
        this._dirty = true;
        this._render();
      },
      "save-settings": () =>
        this._run(async () => {
          await this._ws("middagsro/settings", { settings: this._form });
          this._dirty = false;
        }, "Indstillingerne er gemt."),
      "add-dislike": () => {
        const text = this._newDislike.trim();
        if (!text) return this._say("Skriv en ret først.");
        this._saveDislikes([...(this._state.settings.disliked_dishes || []), text], "Retten er tilføjet.");
        this._newDislike = "";
      },
      "delete-dislike": () => {
        const list = [...(this._state.settings.disliked_dishes || [])];
        list.splice(Number(arg), 1);
        this._saveDislikes(list, "Retten er fjernet.");
      },
      "reset-settings": () => {
        this._form = clone(this._state.settings);
        this._dirty = false;
        this._render();
      },
      "add-row": () => {
        const rows = {
          household: { role: "adult", age: 40, sex: "female" },
          fixed_days: { weekday: 3, text: "" },
          must_haves: { name: "", amount: 1, product_id: null },
        };
        this._form[arg].push(clone(rows[arg]));
        this._dirty = true;
        this._render();
      },
      "remove-row": () => {
        const [list, idx] = arg.split("|");
        this._form[list].splice(Number(idx), 1);
        this._dirty = true;
        this._render();
      },
      search: () => this._doSearch(),
      "pick-product": () => {
        const product = this._search.results[Number(arg)];
        if (!product) return;
        const name = `${product.name}${product.underline ? ` (${product.underline.split("/")[0].trim()})` : ""}`;
        this._form.must_haves.push({ name, product_id: product.id, amount: 1 });
        this._search = { query: "", results: [], loading: false };
        this._dirty = true;
        this._render();
      },
      "add-fav": () => {
        if (!this._newFav.text.trim()) return this._say("Skriv en ret først.");
        this._run(async () => {
          await this._ws("middagsro/favorite/save", { favorite: this._newFav });
          this._newFav = { text: "", frequency: "weekly" };
        }, "Favoritten er tilføjet.");
      },
      "edit-fav": () => {
        const fav = this._state.favorites.find((f) => f.id === arg);
        this._editFav = fav ? clone(fav) : null;
        this._render();
      },
      "save-fav": () =>
        this._run(async () => {
          await this._ws("middagsro/favorite/save", { favorite: this._editFav });
          this._editFav = null;
        }, "Favoritten er gemt."),
      "cancel-fav": () => {
        this._editFav = null;
        this._render();
      },
      "delete-fav": () => {
        if (!confirm("Slet denne favorit?")) return;
        this._run(() => this._ws("middagsro/favorite/delete", { favorite_id: arg }), "Favoritten er slettet.");
      },
      recipe: () =>
        this._run(async () => {
          const item = this._recipeDays()[this._day];
          if (!item) return;
          // The plans are read again afterwards, so the new recipe shows up.
          await this._ws("middagsro/recipe", { plan_id: item.plan.id, date: item.day.date });
          if (!this._viewingLatest) this._plan = await this._ws("middagsro/plan", { plan_id: this._plan.id });
        }, "Opskriften er lavet igen."),
      refresh: () => this._load(),
      // A day of the plan: see the recipe, or swap the dish for another.
      "day-menu": () => {
        const [planId, date] = String(arg).split("|");
        const plan = this._planOf(planId);
        const day = plan?.days.find((d) => d.date === date);
        if (!day) return;
        this._modal = { kind: "day", planId, date, dish: day.dish, leftovers: !!day.uses_leftovers_from || day.type === "rester" };
        this._renderModal();
      },
      "modal-close": () => {
        if (this._modal?.busy) return;
        if (this._modal?.kind === "where") this._everywhere = { query: "", loading: false, data: null, error: null };
        this._modal = null;
        this._renderModal();
      },
      "day-recipe": () => {
        const m = this._modal;
        this._modal = null;
        this._renderModal();
        this._day = this._recipeIndex(`${m.planId}|${m.date}`);
        this._dayKey = this._recipeKey();
        this._tab = "recipes";
        this._recipesSub = "week";
        this._render();
      },
      "swap-options": () => this._swapOptions(),
      "day-clear": () => {
        const m = this._modal;
        if (!m || m.busy) return;
        const skip = arg === "skip";
        const what = skip ? "Spring dagen over? Der laves ingen aftensmad den dag." : "Slet retten? Du kan vælge en ny bagefter.";
        if (!confirm(`${what} Rettens egne varer fjernes fra indkøbslisten.`)) return;
        this._modal = null;
        this._renderModal();
        this._editPlan(
          () => this._ws("middagsro/day/clear", { plan_id: m.planId, date: m.date, skip }),
          skip ? "Dagen springes over." : "Retten er slettet."
        );
      },
      "line-menu": () => this._openLine(arg),
      "line-count": () => {
        const m = this._modal;
        if (!m) return;
        m.packages = Math.max(1, Math.min(99, m.packages + Number(arg)));
        this._renderModal();
      },
      "line-save-count": () => this._lineAction({ packages: this._modal.packages }, "Antallet er rettet."),
      "line-delete": () => this._lineAction({ delete: true }, "Varen er slettet fra indkøbslisten."),
      "line-search": () => this._lineSearch(),
      "line-pick": () => {
        const product = this._modal?.results[Number(arg)];
        if (product) this._lineAction({ product_id: product.id }, `${product.name} er sat på listen i stedet.`);
      },
      "add-rule": () => {
        const text = this._newRule.trim();
        if (!text) return this._say("Skriv noget først – eller diktér det.");
        this._newRule = "";
        this._saveRules([...(this._state.settings.rules || []), text], "Gemt – AI'en husker det fra næste madplan.");
      },
      "edit-rule": () => {
        this._editRule = { index: Number(arg), text: (this._state.settings.rules || [])[Number(arg)] || "" };
        this._render();
      },
      "cancel-rule": () => {
        this._editRule = null;
        this._render();
      },
      "save-rule": () => {
        const list = [...(this._state.settings.rules || [])];
        const text = this._editRule?.text.trim();
        if (text) list[this._editRule.index] = text;
        else list.splice(this._editRule.index, 1);
        this._editRule = null;
        this._saveRules(list, "Rettet.");
      },
      "delete-rule": () => {
        const list = [...(this._state.settings.rules || [])];
        list.splice(Number(arg), 1);
        this._saveRules(list, "Slettet.");
      },
      dictate: () => this._dictate(arg),
      "health-refresh": () => this._loadHealth(true),
      "mealie-save": () => {
        const [planId, date] = String(arg).split("|");
        if (this._modal) {
          this._modal = null;
          this._renderModal();
        }
        this._editPlan(() => this._ws("middagsro/mealie/save", { plan_id: planId, date }), "Opskriften er gemt i Mealie.");
      },
      "mealie-sync": () =>
        this._run(() => this._ws("middagsro/mealie/sync", { plan_id: this._plan.id }), "Ugen er sat i Mealie-kalenderen."),
      "swap-pick": () => this._swapPick(Number(arg)),
      "pantry-open": () => this._pantryOpen(),
      "plan-refresh": () =>
        this._editPlan(
          () => this._ws("middagsro/plan/refresh", { plan_id: this._plan.id }),
          "Tilbudsvarerne er fundet igen med REMA's varer og priser lige nu."
        ),
      "pantry-add": () => this._pantryAdd(arg),
      "shop-search": () => this._shopSearchRun(arg),
      "shop-add": () => {
        const [part, idx] = String(arg).split("|");
        const product = this._shopSearch[part]?.results[Number(idx)];
        if (!product || !this._plan) return;
        this._shopSearch[part] = { query: "", results: [], loading: false };
        this._editPlan(
          () => this._ws("middagsro/plan/add", { plan_id: this._plan.id, product_id: product.id, part }),
          `${product.name} er tilføjet til indkøbslisten.`
        );
      },
      "line-remove": () =>
        this._editPlan(() => this._ws("middagsro/plan/remove", { plan_id: this._plan.id, line_id: arg }), "Varen er fjernet."),
    };
    actions[action]?.();
  }

  _onInput(ev) {
    const el = ev.target;
    const ds = el.dataset;
    if (ds.bind === "start") {
      this._startDate = el.value;
      if (ev.type === "change") this._render(); // the skip boxes follow the dates
      return;
    }
    if (ds.bind === "skip") {
      if (el.checked) this._skip.add(el.value);
      else this._skip.delete(el.value);
      return;
    }
    if (ds.bind === "note") {
      this._noteDraft = el.value;
      return;
    }
    if (ds.bind === "favfilter") {
      this._favFilter = el.value;
      const list = this.shadowRoot.querySelector("#fav-all");
      if (list) list.innerHTML = this._favRows();
      return;
    }
    if (ds.bind === "everywhere") {
      this._everywhere.query = el.value;
      if (!el.value.trim()) {
        // Emptied (also with the field's own ✕): the results go away.
        this._everywhere = { query: "", loading: false, data: null, error: null };
        this.shadowRoot.querySelectorAll(".ev-out").forEach((n) => (n.innerHTML = ""));
        return;
      }
      if (ev.type === "change") this._everywhereRun();
      return;
    }
    if (ds.bind === "chainquery") {
      this._chainQuery = el.value;
      const list = this.shadowRoot.querySelector("#chain-offers");
      if (list) list.innerHTML = this._chainOfferRows();
      return;
    }
    if (ds.bind === "rc") {
      this._rc[ds.field] = el.value;
      if (ds.field === "link") return;
      if (ds.field === "sort" || ev.type === "input") {
        const list = this.shadowRoot.querySelector("#rc-list");
        if (list && ds.field === "query") list.innerHTML = this._collectionRows();
        else this._render();
      }
      return;
    }
    if (ds.bind === "rcp") {
      const m = this._modal;
      if (m?.kind !== "recipe") return;
      const number = ["servings", "active_minutes", "total_minutes", "minutes"].includes(ds.field);
      const value = number ? Number(el.value) || 0 : el.value;
      if (ds.list) m.recipe[ds.list][Number(ds.idx)][ds.field] = value;
      else m.recipe[ds.field] = value;
      return;
    }
    if (ds.bind === "newrule") {
      this._newRule = el.value;
      return;
    }
    if (ds.bind === "editrule") {
      if (this._editRule) this._editRule.text = el.value;
      return;
    }
    if (ds.bind === "linesearch") {
      if (this._modal) this._modal.query = el.value;
      if (ev.type === "change") this._lineSearch();
      return;
    }
    if (ds.bind === "shopsearch") {
      this._shopSearch[ds.part].query = el.value;
      if (ev.type === "change") this._shopSearchRun(ds.part);
      return;
    }
    if (ds.bind === "search") {
      this._search.query = el.value;
      if (ev.type === "change") this._doSearch();
      return;
    }
    if (ds.bind === "newdislike") {
      this._newDislike = el.value;
      return;
    }
    if (ds.bind === "newfav") {
      this._newFav[ds.field] = el.value;
      return;
    }
    if (ds.bind === "editfav") {
      this._editFav[ds.field] = el.value;
      return;
    }
    if (ds.list && this._form) {
      const list = this._form[ds.list];
      const idx = list.indexOf(el.value);
      if (el.checked && idx < 0) list.push(el.value);
      if (!el.checked && idx >= 0) list.splice(idx, 1);
      this._dirty = true;
      return;
    }
    if (ds.path && this._form) {
      let value = el.type === "checkbox" ? el.checked : el.value;
      if (ds.type === "number") value = value === "" ? 0 : Number(value);
      if (ds.type === "nullable") value = value || null;
      const keys = ds.path.split(".");
      let target = this._form;
      while (keys.length > 1) target = target[keys.shift()];
      target[keys[0]] = value;
      this._dirty = true;
      if (ev.type === "change" && (el.type === "radio" || el.tagName === "SELECT" || /_pct$/.test(ds.path))) this._render();
    }
  }

  async _loadFavs(force = false) {
    const week = this._favWeek;
    if (force) this._favCache = {};
    this._favsLoading = true;
    this._favsError = null;
    this._render();
    try {
      this._favCache[week] = await this._ws("middagsro/favorites", { force, week });
      this._loadFavCompare(week);
    } catch (err) {
      this._favsError = err?.message || String(err);
    }
    this._favsLoading = false;
    this._render();
  }

  // Favourites that are cheaper in one of the chosen chains that week.
  async _loadFavCompare(week) {
    const data = this._favCache[week];
    if (!data || !(this._state?.settings?.chains || []).length) return;
    const date = week === "next" && !data.fallback && data.catalog?.valid_from ? localDay(data.catalog.valid_from) : null;
    const products = (data.products || []).map((p) => ({ id: p.id, name: p.name, underline: p.underline, price: p.price, is_organic: p.is_organic }));
    try {
      this._favCompare[week] = (await this._ws("middagsro/chains/products", { products, date })).products;
      if (this._tab === "favorites") this._render();
    } catch (err) {
      this._favCompare[week] = {};
    }
  }

  _favCheaper(p) {
    const found = this._favCompare[this._favWeek]?.[String(p.id)];
    return found
      ? `<button class="cheaper" data-action="fav-where" data-arg="${esc(p.id)}" title="Se priserne i butikkerne">${this._chainLogo(found.dealer_id, "tiny")}<span>${kr(found.per_package)} i ${esc(this._chainName(found.dealer_id))}</span></button>`
      : `<button class="cheaper plain" data-action="fav-where" data-arg="${esc(p.id)}">Sammenlign priser</button>`;
  }

  async _generate(surprise = false) {
    const days = new Set(this._planDates());
    await this._ws("middagsro/generate", {
      start_date: this._startDate || null,
      skip_dates: [...this._skip].filter((d) => days.has(d)),
      surprise,
    });
    this._skip.clear();
    this._viewingLatest = true;
    this._tab = "plan";
  }

  // Save the wishes for the next plan, and make the plan right away if asked.
  _saveNote(generate = false) {
    const text = this._noteDraft.trim();
    this._noteOpen = false;
    this._renderModal();
    this._run(
      async () => {
        await this._ws("middagsro/note", { text });
        if (generate) await this._generate();
      },
      generate ? GENERATING_MESSAGE : text ? "Ønskerne bruges i næste madplan." : "Ønskerne er fjernet."
    );
  }

  // Every plan the panel has in full: the viewed one, the newest and those this week's days come from.
  _planOf(id) {
    const s = this._state || {};
    return [this._plan, s.latest_plan, s.current_plan, ...(s.timeline_plans || [])].find((p) => p && p.id === id) || null;
  }

  // This week and the coming days as one plan: each date from the newest plan that covers it.
  // Null when looking at an older plan, or when nothing is planned from today on.
  _timeline() {
    if (!this._viewingLatest) return null;
    const today = localToday();
    const list = (this._state?.timeline || [])
      .map((e) => {
        const plan = this._planOf(e.plan_id);
        return plan ? { ...e, plan, day: e.skipped ? null : plan.days.find((d) => d.date === e.date) || null } : null;
      })
      .filter(Boolean);
    return list.some((e) => e.date >= today) ? list : null;
  }

  // The dinners of the week (or of the plan being viewed), in order.
  _recipeDays() {
    const plan = this._plan;
    if (!plan) return [];
    const timeline = this._timeline();
    if (timeline) return timeline.filter((e) => e.day).map((e) => ({ plan: e.plan, day: e.day }));
    return plan.days.map((day) => ({ plan, day }));
  }

  // "planId|date" -> position in _recipeDays(); otherwise today, else the first day.
  _recipeIndex(arg) {
    const list = this._recipeDays();
    const [planId, date] = String(arg || "").split("|");
    let idx = list.findIndex((x) => x.plan.id === planId && x.day.date === date);
    if (idx < 0) idx = list.findIndex((x) => x.day.date === localToday());
    return Math.max(0, idx);
  }

  async _doSearch() {
    const query = this._search.query.trim();
    if (!query) return;
    this._search.loading = true;
    this._render();
    try {
      this._search.results = await this._ws("middagsro/search", { query });
    } catch (err) {
      this._say(`Søgningen fejlede: ${err?.message || err}`);
    }
    this._search.loading = false;
    this._render();
  }

  // A change to the plan being viewed: run it, then show the plan as it is now.
  _editPlan(fn, okMessage) {
    return this._run(async () => {
      await fn();
      if (!this._viewingLatest && this._plan) this._plan = await this._ws("middagsro/plan", { plan_id: this._plan.id });
    }, okMessage);
  }

  async _shopSearchRun(part) {
    const search = this._shopSearch[part];
    const query = search?.query.trim();
    if (!query) return;
    search.loading = true;
    this._render();
    try {
      search.results = await this._ws("middagsro/search", { query });
      if (!search.results.length) this._say(`Ingen varer fundet for "${query}".`);
    } catch (err) {
      this._say(`Søgningen fejlede: ${err?.message || err}`);
    }
    search.loading = false;
    this._render();
  }

  async _swapOptions() {
    const m = this._modal;
    if (!m || m.busy) return;
    m.busy = "options";
    m.error = null;
    this._renderModal();
    try {
      const result = await this._ws("middagsro/swap/options", { plan_id: m.planId, date: m.date });
      Object.assign(m, { date: result.date, dish: result.dish, options: result.options });
    } catch (err) {
      m.error = err?.message || String(err);
    }
    m.busy = null;
    this._renderModal();
  }

  async _swapPick(idx) {
    const m = this._modal;
    const option = m?.options?.[idx];
    if (!option || m.busy) return;
    m.busy = "swap";
    m.picked = idx;
    m.error = null;
    this._renderModal();
    try {
      const plan = await this._ws("middagsro/swap", { plan_id: m.planId, date: m.date, option });
      if (!this._viewingLatest && this._plan?.id === plan.id) this._plan = plan;
      this._modal = null;
      this._renderModal();
      await this._load();
      this._say(`${option.dish} er sat på madplanen – indkøbslisten og opskriften er lavet om.`);
    } catch (err) {
      m.busy = null;
      m.error = err?.message || String(err);
      this._renderModal();
    }
  }

  async _pantryOpen() {
    if (!this._plan) return;
    this._modal = { kind: "pantry", busy: "load", items: [] };
    this._renderModal();
    await this._pantryLoad();
  }

  async _pantryLoad() {
    const m = this._modal;
    if (!m) return;
    try {
      m.items = await this._ws("middagsro/pantry", { plan_id: this._plan.id });
      m.error = null;
    } catch (err) {
      m.error = err?.message || String(err);
    }
    m.busy = null;
    this._renderModal();
  }

  async _pantryAdd(name) {
    const m = this._modal;
    if (!m || m.busy) return;
    m.busy = name;
    this._renderModal();
    try {
      const line = await this._ws("middagsro/plan/add", { plan_id: this._plan.id, pantry: name });
      if (!this._viewingLatest) this._plan = await this._ws("middagsro/plan", { plan_id: this._plan.id });
      await this._load();
      this._say(line.product ? `${line.product.name} er tilføjet til indkøbslisten.` : `${line.name} er tilføjet som fritekst.`);
    } catch (err) {
      m.error = err?.message || String(err);
    }
    await this._pantryLoad();
  }

  // ------------------------------------------------------------------ rules ("Det skal AI'en huske")

  _saveRules(list, okMessage) {
    this._run(async () => {
      const saved = await this._ws("middagsro/settings", { settings: { ...this._state.settings, rules: list } });
      if (this._form) this._form.rules = saved.rules;
    }, okMessage);
  }

  _rulesHtml() {
    const rules = this._state.settings.rules || [];
    const items = rules
      .map((text, i) =>
        this._editRule?.index === i
          ? `<li class="fav edit"><textarea data-bind="editrule" rows="2">${esc(this._editRule.text)}</textarea>
              <div class="row wrap">
                <button class="btn primary small" data-action="save-rule" ${this._busy ? "disabled" : ""}>Gem</button>
                ${this._micButton("editrule")}
                <button class="btn small" data-action="cancel-rule">Annullér</button>
              </div></li>`
          : `<li class="fav"><div class="what" data-action="edit-rule" data-arg="${i}"><span>${esc(text)}</span></div>
              <button class="btn small" data-action="edit-rule" data-arg="${i}">Ret</button>
              <button class="btn small danger" data-action="delete-rule" data-arg="${i}">Slet</button></li>`
      )
      .join("");
    return `<textarea data-bind="newrule" rows="2" placeholder="Fx: Vi vil altid have frisk broccoli og fettuccine med spinat til laksefilet">${esc(this._newRule)}</textarea>
      <div class="row wrap">
        <button class="btn primary small" data-action="add-rule" ${this._busy ? "disabled" : ""}>Tilføj</button>
        ${this._micButton("newrule")}
      </div>
      <ul class="favs">${items || "<li class='muted'>Ingen endnu.</li>"}</ul>`;
  }

  // ------------------------------------------------------------------ dictation

  _micButton(target) {
    if (!this._canDictate()) return "";
    const on = this._dictating === target;
    return `<button class="btn small mic ${on ? "on" : ""}" data-action="dictate" data-arg="${target}">${on ? "■ Stop" : "🎤 Diktér"}</button>`;
  }

  _canDictate() {
    return Boolean(
      window.SpeechRecognition || window.webkitSpeechRecognition || (navigator.mediaDevices?.getUserMedia && this._hass?.connection)
    );
  }

  // Put dictated text into a field (and its state) without redrawing the page.
  _dictated(target, text) {
    text = String(text || "").trim();
    if (!text) return;
    const join = (old) => (old && !/\s$/.test(old) ? `${old} ${text}` : `${old || ""}${text}`);
    if (target === "newrule") this._newRule = join(this._newRule);
    else if (target === "editrule" && this._editRule) this._editRule.text = join(this._editRule.text);
    else if (target === "note") this._noteDraft = join(this._noteDraft);
    const field = this.shadowRoot.querySelector(`[data-bind="${target}"]`);
    if (field) field.value = target === "note" ? this._noteDraft : target === "newrule" ? this._newRule : this._editRule?.text || "";
  }

  _dictate(target) {
    if (this._dictating) {
      this._stopDictation?.();
      return;
    }
    const Recognition = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (Recognition) {
      const rec = new Recognition();
      rec.lang = "da-DK";
      rec.interimResults = false;
      rec.continuous = false;
      rec.onresult = (ev) => {
        for (let i = ev.resultIndex; i < ev.results.length; i++) {
          if (ev.results[i].isFinal) this._dictated(target, ev.results[i][0].transcript);
        }
      };
      rec.onerror = (ev) => {
        if (ev.error === "not-allowed") this._say("Giv adgang til mikrofonen for at diktere.");
        else if (ev.error !== "no-speech" && ev.error !== "aborted") this._dictateHA(target);
      };
      rec.onend = () => {
        if (this._dictating === target && this._stopDictation === stop) this._dictationDone();
      };
      const stop = () => rec.stop();
      this._stopDictation = stop;
      this._dictating = target;
      this._render();
      this._renderModal();
      try {
        rec.start();
      } catch (err) {
        this._dictateHA(target);
      }
      return;
    }
    this._dictateHA(target);
  }

  _dictationDone() {
    this._dictating = null;
    this._stopDictation = null;
    this._render();
    this._renderModal();
  }

  // Without the browser's own speech recognition (e.g. the Home Assistant app):
  // Home Assistant's own speech-to-text (Assist), as its voice dialog does.
  async _dictateHA(target) {
    const conn = this._hass?.connection;
    if (!navigator.mediaDevices?.getUserMedia || !conn) {
      this._say("Diktat virker ikke i denne browser.");
      return this._dictationDone();
    }
    let stream;
    try {
      stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    } catch (err) {
      this._say("Giv adgang til mikrofonen for at diktere.");
      return this._dictationDone();
    }
    const ctx = new (window.AudioContext || window.webkitAudioContext)();
    const source = ctx.createMediaStreamSource(stream);
    const proc = ctx.createScriptProcessor(4096, 1, 1);
    let handler = null;
    let stopped = false;
    let unsub = null;
    const waiting = [];
    const send = (pcm) => {
      const msg = new Uint8Array(1 + pcm.byteLength);
      msg[0] = handler;
      msg.set(new Uint8Array(pcm.buffer), 1);
      conn.socket.send(msg);
    };
    const finish = () => {
      if (stopped) return;
      stopped = true;
      proc.disconnect();
      source.disconnect();
      stream.getTracks().forEach((t) => t.stop());
      ctx.close();
      if (handler !== null) conn.socket.send(new Uint8Array([handler])); // end of audio
    };
    this._stopDictation = finish;
    this._dictating = target;
    this._render();
    this._renderModal();
    proc.onaudioprocess = (ev) => {
      if (stopped) return;
      const input = ev.inputBuffer.getChannelData(0);
      const pcm = new Int16Array(input.length);
      for (let i = 0; i < input.length; i++) pcm[i] = Math.max(-1, Math.min(1, input[i])) * 0x7fff;
      if (handler === null) waiting.push(pcm);
      else send(pcm);
    };
    source.connect(proc);
    proc.connect(ctx.destination);
    try {
      unsub = await conn.subscribeMessage(
        (ev) => {
          if (ev.type === "run-start") {
            handler = ev.data.runner_data.stt_binary_handler_id;
            waiting.splice(0).forEach(send);
          } else if (ev.type === "stt-vad-end") {
            finish();
          } else if (ev.type === "stt-end") {
            this._dictated(target, ev.data?.stt_output?.text);
          } else if (ev.type === "error") {
            finish();
            this._say(`Diktat fejlede: ${ev.data?.message || ev.data?.code || "ukendt fejl"}`);
          }
          if (ev.type === "run-end" || ev.type === "error") {
            unsub?.();
            this._dictationDone();
          }
        },
        { type: "assist_pipeline/run", start_stage: "stt", end_stage: "stt", input: { sample_rate: ctx.sampleRate } }
      );
    } catch (err) {
      finish();
      this._say(`Diktat virker ikke: ${err?.message || err}. Sæt tale-til-tekst op under Indstillinger › Stemmeassistenter.`);
      this._dictationDone();
    }
  }

  // ------------------------------------------------------------------ shopping line popup

  _openLine(lineId) {
    const plan = this._plan;
    const line = plan?.shopping.find((l) => l.id === lineId);
    if (!line) return;
    const m = { kind: "line", planId: plan.id, lineId, packages: line.packages || 1, query: "", results: [], loading: false };
    this._modal = m;
    this._renderModal();
    // REMA's nutrition per 100 g, as the app shows it.
    if (line.product?.id) {
      this._ws("middagsro/nutrition", { product_id: line.product.id })
        .then((n) => {
          m.nutrition = n;
          if (this._modal === m) this._renderModal();
        })
        .catch(() => {});
    }
  }

  async _lineAction(data, okMessage) {
    const m = this._modal;
    if (!m || m.busy) return;
    m.busy = true;
    m.error = null;
    this._renderModal();
    try {
      const plan = await this._ws("middagsro/plan/line", { plan_id: m.planId, line_id: m.lineId, ...data });
      if (!this._viewingLatest && this._plan?.id === plan.id) this._plan = plan;
      this._modal = null;
      this._renderModal();
      await this._load();
      this._say(okMessage);
    } catch (err) {
      m.busy = false;
      m.error = err?.message || String(err);
      this._renderModal();
    }
  }

  async _lineSearch() {
    const m = this._modal;
    const query = m?.query.trim();
    if (!query) return;
    m.loading = true;
    this._renderModal();
    try {
      m.results = await this._ws("middagsro/search", { query });
      if (!m.results.length) m.error = `Ingen varer fundet for "${query}".`;
    } catch (err) {
      m.error = err?.message || String(err);
    }
    m.loading = false;
    this._renderModal();
    this.shadowRoot.querySelector('[data-bind="linesearch"]')?.focus();
  }

  _lineModal(m) {
    const line = this._plan?.shopping.find((l) => l.id === m.lineId);
    if (!line) return "";
    const p = line.product || line.avis_item;
    const busy = !!m.busy;
    const results = m.loading
      ? '<p class="muted"><span class="spinner small"></span> Søger …</p>'
      : m.results
          .map(
            (r, i) => `<button class="result" data-action="line-pick" data-arg="${i}" ${busy ? "disabled" : ""}>
              ${r.image ? `<img src="${esc(r.image)}" alt="">` : ""}
              <span><b>${esc(r.name)}</b><span class="muted">${esc(r.underline || "")} · ${kr(r.price)}</span></span>
              ${r.is_organic ? '<span class="badge eco">Øko</span>' : ""}<span class="add">Vælg</span></button>`
          )
          .join("");
    const price = p?.price != null ? p.price : null;
    return `
      <div class="scrim" data-action="modal-close"></div>
      <div class="dialog" role="dialog" aria-modal="true" aria-labelledby="line-title">
        <div class="line-head">
          ${p?.image ? `<img src="${esc(p.image)}" alt="">` : '<span class="noimg">?</span>'}
          <div><h2 id="line-title">${esc(p ? p.name : line.name)}</h2>
          <p class="muted small">${esc(p?.underline || "Fritekst")}${line.amount && line.unit && line.unit !== "pk" ? ` · behov ${esc(`${line.amount} ${line.unit}`)}` : ""}</p></div>
        </div>
        ${m.error ? `<div class="banner error">${esc(m.error)}</div>` : ""}
        <div class="row wrap stepper">
          <span>Antal</span>
          <button class="btn small" data-action="line-count" data-arg="-1" ${busy || m.packages <= 1 ? "disabled" : ""}>−</button>
          <b class="count">${m.packages}</b>
          <button class="btn small" data-action="line-count" data-arg="1" ${busy || m.packages >= 99 ? "disabled" : ""}>+</button>
          ${price != null ? `<span class="muted">${kr(price * m.packages)}</span>` : ""}
          <span class="spacer"></span>
          <button class="btn small primary" data-action="line-save-count" ${busy || m.packages === (line.packages || 1) ? "disabled" : ""}>Gem antal</button>
        </div>
        ${m.nutrition && m.nutrition.kcal != null
          ? `<details class="nutrition"><summary>Næringsindhold pr. 100 g</summary><table>
              ${[["kcal", "Energi", " kcal"], ["fat_g", "Fedt", " g"], ["carbs_g", "Kulhydrat", " g"], ["fiber_g", "Kostfibre", " g"], ["protein_g", "Protein", " g"], ["salt_g", "Salt", " g"]]
                .filter(([k]) => m.nutrition[k] != null)
                .map(([k, label, unit]) => `<tr><td>${label}</td><td>${String(m.nutrition[k]).replace(".", ",")}${unit}</td></tr>`)
                .join("")}</table></details>`
          : ""}
        <h2 class="small-h">Skift til en anden vare</h2>
        <div class="row wrap">
          <input class="grow" type="search" data-bind="linesearch" value="${esc(m.query)}" placeholder="Søg i REMA 1000">
          <button class="btn small" data-action="line-search" ${busy ? "disabled" : ""}>Søg</button>
        </div>
        <div class="results">${results}</div>
        <div class="row wrap dialog-actions">
          <button class="btn danger" data-action="line-delete" ${busy ? "disabled" : ""}>Slet varen</button>
          <span class="spacer"></span>
          <button class="btn" data-action="modal-close" ${busy ? "disabled" : ""}>Luk</button>
        </div>
      </div>`;
  }

  // ------------------------------------------------------------------ health

  async _loadHealth(force = false) {
    const planId = this._plan?.id;
    if (!planId) return;
    if (!force && this._health?.planId === planId && (this._health.data || this._health.loading)) return;
    this._health = { planId, loading: true, data: null, error: null };
    this._render();
    try {
      this._health.data = await this._ws("middagsro/health", { plan_id: planId });
    } catch (err) {
      this._health.error = err?.message || String(err);
    }
    this._health.loading = false;
    if (this._tab === "health") this._render();
  }

  _healthView() {
    if (!this._plan) return `<div class="card">Der er ingen madplan endnu.</div>`;
    const h = this._health;
    if (!h || h.planId !== this._plan.id) {
      setTimeout(() => this._loadHealth(), 0);
      return `<div class="card center"><span class="spinner"></span> Regner på madplanen …</div>`;
    }
    if (h.loading) return `<div class="card center"><span class="spinner"></span> Regner på madplanen …</div>`;
    if (h.error) return `<div class="card"><div class="banner error">${esc(h.error)}</div></div>`;
    const d = h.data;
    const t = d.targets;
    const bar = (value, goal, kind) => {
      const pct = goal ? Math.min(100, Math.round((value / goal) * 100)) : 0;
      const ok = kind === "max" ? value <= goal : value >= goal;
      return `<div class="meter ${ok ? "ok" : kind === "max" ? "over" : "low"}"><span style="width:${pct}%"></span></div>`;
    };
    const macro = (pct) =>
      pct ? `${pct.protein} % protein · ${pct.carbs} % kulhydrat · ${pct.fat} % fedt` : "";
    const avg = d.average || d.rema_average;
    const fromRema = !d.average && !!d.rema_average;
    const rema = d.rema_average;
    const kcalOk = avg && t ? avg.kcal >= t.kcal_min && avg.kcal <= t.kcal_max : null;
    const dinners = d.dinners
      .map(
        (x) => `<li class="hrow"><div class="what"><b>${esc(dateLabel(x.date))}</b><span>${esc(x.dish)}${x.leftovers ? ' <span class="badge">Rester</span>' : ""}</span>
          <span class="muted small">${x.percent ? macro(x.percent) : ""}</span></div>
          <div class="cost">${x.nutrition || x.rema
            ? `<b>${Math.round((x.nutrition || x.rema).kcal)} kcal</b>${Math.round((x.nutrition || x.rema).protein_g || 0)} g protein${x.nutrition && x.rema ? `<br><span class="small">REMA: ${Math.round(x.rema.kcal)} kcal</span>` : ""}`
            : "–"}</div></li>`
      )
      .join("");
    const nutritionCard = avg
      ? `<div class="card">
          <h1>Næring pr. aftensmad</h1>
          <p class="muted small">Pr. voksenportion${fromRema ? ", regnet ud fra REMA's næringsindhold for varerne" : ", som AI'en vurderer det ud fra opskriften"}. Børnenes portioner er mindre.</p>
          <div class="kpis">
            <div class="kpi"><span class="big ${kcalOk === false ? "warn" : ""}">${Math.round(avg.kcal)}</span><span class="muted">kcal i snit${t ? ` · mål ${t.kcal_min}–${t.kcal_max}` : ""}</span></div>
            <div class="kpi"><span class="big">${Math.round(avg.protein_g || 0)} g</span><span class="muted">protein</span></div>
            <div class="kpi"><span class="big">${Math.round(avg.carbs_g || 0)} g</span><span class="muted">kulhydrat</span></div>
            <div class="kpi"><span class="big">${Math.round(avg.fat_g || 0)} g</span><span class="muted">fedt</span></div>
            ${avg.fiber_g ? `<div class="kpi"><span class="big">${Math.round(avg.fiber_g)} g</span><span class="muted">kostfibre</span></div>` : ""}
          </div>
          ${(d.average_percent || d.rema_average_percent) ? `<p>Fordeling: <b>${macro(d.average_percent || d.rema_average_percent)}</b>${t ? ` <span class="muted">· mål ${t.protein} / ${t.carbs} / ${t.fat} %</span>` : ""}</p>` : ""}
          ${rema && !fromRema
            ? `<p class="nutri">Efter REMA's varedata: <b>${Math.round(rema.kcal)} kcal</b> · ${Math.round(rema.protein_g)} g protein · ${Math.round(rema.carbs_g)} g kulhydrat · ${Math.round(rema.fat_g)} g fedt
                <br><span class="muted small">Regnet ud fra næringsindholdet pr. 100 g på de varer, retten bruger (som i REMA-appen). Frugt, grønt og basisvarer har ofte ingen næringsdata, så tallet er typisk lidt lavt.</span></p>`
            : ""}
          ${t ? "" : '<p class="muted small">Sæt mål for kalorier og fordeling under Indstillinger › Næring.</p>'}
          <ul class="lines">${dinners}</ul>
        </div>`
      : `<div class="card"><h1>Næring pr. aftensmad</h1>
          <p class="muted">Næringen regnes ud, når opskrifterne skrives. Madplaner lavet før version 0.9 har den ikke – lav en ny madplan, eller tryk "Lav opskriften igen" på en ret.</p></div>`;
    const advice = d.advice
      .map(
        (a) => `<li class="hrow"><div class="what"><b>${esc(a.label)}</b><span class="muted small">${esc(a.note)}</span>
            ${bar(a.value, a.goal, a.kind)}</div>
          <div class="cost"><b>${a.value} g</b>${a.kind === "max" ? "højst" : "mål"} ${a.goal} g<br><span class="small">${esc(a.unit)}</span></div></li>`
      )
      .join("");
    const l = d.labels;
    const share = (v) => (v == null ? "–" : `${v} %`);
    return `
      ${nutritionCard}
      <div class="card">
        <h1>Kostrådene</h1>
        <p class="muted small">Ud fra indkøbslisten til ${d.days} dage og ${String(d.people).replace(".", ",")} portioner (børn tæller mindre). Kun aftensmaden er med – morgenmad, frokost og frugt kommer oveni.</p>
        <ul class="lines">${advice}</ul>
        ${d.unknown.length ? `<p class="muted small">Uden mængde: ${d.unknown.map(esc).join(", ")}.</p>` : ""}
        <p class="muted small">Kilde: <a href="https://www.sundhed.dk/borger/sygdomme-a-aa/hormoner-og-stofskifte/sygdomme/kost/sund-kost/" target="_blank" rel="noopener">De officielle kostråd (sundhed.dk)</a>.</p>
      </div>
      <div class="card">
        <h1>Mærker i kurven</h1>
        <p class="muted small">Andel af indkøbslistens pris.</p>
        ${l.known
          ? `<div class="kpis">
              <div class="kpi"><span class="big">${share(l.keyhole)}</span><span class="muted">Nøglehulsmærket</span></div>
              <div class="kpi"><span class="big">${share(l.organic)}</span><span class="muted">Økologisk</span></div>
              <div class="kpi"><span class="big">${share(l.asc_msc)}</span><span class="muted">ASC/MSC (fisk)</span></div>
            </div>`
          : `<p class="muted">Mærkerne gemmes på varerne fra version 0.9. Tryk "Opdatér tilbudsvarer" i Indkøb eller lav en ny madplan.</p>
            <div class="kpis"><div class="kpi"><span class="big">${share(l.organic)}</span><span class="muted">Økologisk</span></div></div>`}
      </div>
      <div class="row wrap"><button class="btn" data-action="health-refresh">Regn igen</button></div>`;
  }

  // ------------------------------------------------------------------ wake lock

  async _requestWake() {
    this._wakeWanted = true;
    if (!("wakeLock" in navigator)) {
      this._wakeWanted = false;
      this._say("Denne browser kan ikke holde skærmen tændt.");
      return;
    }
    try {
      this._wake = await navigator.wakeLock.request("screen");
      this._wake.addEventListener("release", () => {
        this._wake = null;
        this._render();
      });
    } catch (err) {
      this._wakeWanted = false;
      this._say(`Skærmen kan ikke holdes tændt: ${err?.message || err}`);
    }
    this._render();
  }

  async _releaseWake(render = false) {
    this._wakeWanted = false;
    if (this._wake) {
      try {
        await this._wake.release();
      } catch (err) {
        /* already released */
      }
      this._wake = null;
    }
    if (render) this._render();
  }

  // ------------------------------------------------------------------ timers

  _tickTimers() {
    const nodes = this.shadowRoot.querySelectorAll("[data-timer]");
    nodes.forEach((node) => {
      const end = this._timers[node.dataset.timer];
      if (!end) return;
      const left = Math.max(0, Math.round((end - Date.now()) / 1000));
      node.textContent = left > 0 ? `${Math.floor(left / 60)}:${String(left % 60).padStart(2, "0")}` : "Færdig!";
      if (left === 0 && !node.dataset.done) {
        node.dataset.done = "1";
        node.closest(".step")?.classList.add("alarm");
        if (navigator.vibrate) navigator.vibrate([300, 150, 300]);
        this._beep();
      }
    });
  }

  _beep() {
    try {
      const ctx = new (window.AudioContext || window.webkitAudioContext)();
      const osc = ctx.createOscillator();
      osc.frequency.value = 880;
      osc.connect(ctx.destination);
      osc.start();
      osc.stop(ctx.currentTime + 0.6);
    } catch (err) {
      /* no audio */
    }
  }

  // ------------------------------------------------------------------ render

  // ------------------------------------------------------------------ other chains

  async _loadChains() {
    if (this._chainsLoading) return;
    this._chainsLoading = true;
    try {
      this._chains = (await this._ws("middagsro/chains")).chains;
    } catch (err) {
      this._chains = [];
    }
    this._chainsLoading = false;
    this._render();
  }

  _chainInfo(id) {
    const fallback = { id, name: id === REMA_ID ? "REMA 1000" : id, color: id === REMA_ID ? "#0B2D8B" : null, logo: null };
    return (this._chains || []).find((c) => c.id === id) || fallback;
  }

  _chainName(id) {
    return this._chainInfo(id).name;
  }

  // A chain's logo in a circle, so they stand out from REMA's own things.
  _chainLogo(id, cls = "") {
    const c = this._chainInfo(id);
    return `<span class="chain-logo ${cls}" style="--c:${esc(c.color || "#888")}">${c.logo
      ? `<img class="cl" src="${esc(c.logo)}" alt="${esc(c.name)}">`
      : `<span>${esc(c.name.slice(0, 2))}</span>`}</span>`;
  }

  async _loadChainOffers(id, force = false) {
    this._chainOffers[id] = { ...(this._chainOffers[id] || {}), loading: true, error: null };
    this._render();
    try {
      const data = await this._ws("middagsro/chains/offers", { dealer_id: id, force });
      this._chainOffers[id] = { offers: data.offers, loading: false };
    } catch (err) {
      this._chainOffers[id] = { offers: null, loading: false, error: err?.message || String(err) };
    }
    this._render();
  }

  _chainOfferRows() {
    const data = this._chainOffers[this._chain] || {};
    const words = normName(this._chainQuery).split(" ").filter(Boolean);
    const offers = (data.offers || []).filter((o) => {
      const text = normName(`${o.heading} ${o.description || ""}`);
      return words.every((w) => text.includes(w));
    });
    if (!offers.length) return `<p class="muted">${data.offers?.length ? "Ingen tilbud passer til søgningen." : "Ingen madtilbud lige nu."}</p>`;
    const plan = this._state?.latest_plan;
    return offers
      .slice(0, 300)
      .map(
        (o) => `<div class="prod">
          ${o.image ? `<img src="${esc(o.image)}" alt="" loading="lazy">` : '<span class="noimg">?</span>'}
          <div class="prod-body">
            <b>${esc(o.heading)}</b>
            ${o.description ? `<span class="muted small clamp">${esc(o.description)}</span>` : ""}
            <span class="prod-price"><b class="sale">${o.price != null ? kr(o.price) : ""}</b>${o.pre_price ? ` <s class="muted">${kr(o.pre_price)}</s>` : ""}</span>
            <span class="muted small">${o.quantity ? `${esc(o.quantity)} · ` : ""}${o.valid_to ? `til ${esc(shortDate(localDay(o.valid_to)))}` : ""}</span>
          </div>
          ${plan ? `<button class="btn small" data-action="chain-add" data-arg="${esc(o.id)}" ${this._busy ? "disabled" : ""}>+ Indkøb</button>` : ""}
        </div>`
      )
      .join("");
  }

  _chainView() {
    const id = this._chain;
    const c = this._chainInfo(id);
    const data = this._chainOffers[id] || {};
    const count = data.offers?.length;
    return `
      <div class="settings-head">
        <button class="btn back" data-action="chain-close">‹ Madplan</button>
        ${this._chainLogo(id, "big")}
        <h1>Tilbud i ${esc(c.name)}</h1>
      </div>
      <div class="card">
        <div class="row wrap">
          <input class="grow" type="search" data-bind="chainquery" value="${esc(this._chainQuery)}" placeholder="Søg i tilbuddene, fx kaffe">
          <button class="btn small" data-action="chain-refresh" ${data.loading ? "disabled" : ""}>${data.loading ? '<span class="spinner small"></span>' : "Opdatér"}</button>
        </div>
        <p class="muted small">${count != null ? `${count} madtilbud fra ${esc(c.name)}${c.name.endsWith("s") ? "'" : "s"} aviser. ` : ""}${id === REMA_ID ? 'Med "+ Indkøb" kommer tilbuddet på indkøbslisten og sendes til REMA-appen med resten.' : `Med "+ Indkøb" kommer et tilbud på ${esc(c.name)}-listen under Indkøb – REMA-listen er uændret.`}</p>
        ${data.error ? `<div class="banner error">${esc(data.error)}</div>` : ""}
        ${data.loading && !data.offers ? '<p class="muted"><span class="spinner small"></span> Henter tilbud …</p>' : `<div class="prod-grid" id="chain-offers">${this._chainOfferRows()}</div>`}
      </div>`;
  }

  // The chosen chains on the front page.
  _chainsCard() {
    const ids = [REMA_ID, ...(this._state.settings.chains || [])];
    const e = this._everywhere;
    return `<div class="card chains-card">
      <h2 class="flush">Tilbud og priser</h2>
      <div class="chain-row">${ids
        .map((id) => `<button class="chain-btn" data-action="chain-open" data-arg="${esc(id)}">${this._chainLogo(id)}<span>${esc(this._chainName(id))}</span></button>`)
        .join("")}</div>
      <div class="row wrap everywhere">
        <input class="grow" type="search" data-bind="everywhere" value="${esc(e.query)}" placeholder="Søg på en vare – fx kaffe, smør eller laks" enterkeyhint="search">
        <button class="btn" data-action="everywhere" ${e.loading ? "disabled" : ""}>${e.loading ? '<span class="spinner small"></span>' : "Søg"}</button>
        ${e.data || e.error ? '<button class="btn" data-action="everywhere-clear">Ryd</button>' : ""}
      </div>
      <div class="ev-out">${e.error ? `<div class="banner error">${esc(e.error)}</div>` : ""}${e.data ? this._everywhereHtml(e.data) : ""}</div>
    </div>`;
  }

  async _everywhereRun(query) {
    const q = String(query ?? this._everywhere.query).trim();
    if (!q) return this._say("Skriv en vare først.");
    this._everywhere = { query: q, loading: true, data: this._everywhere.data, error: null };
    this._render();
    try {
      this._everywhere = { query: q, loading: false, data: await this._ws("middagsro/search/everywhere", { query: q }), error: null };
    } catch (err) {
      this._everywhere = { query: q, loading: false, data: null, error: err?.message || String(err) };
    }
    this._render();
    this._renderModal();
  }

  // REMA's products and the other shops' offers for a search, cheapest marked.
  _everywhereHtml(data) {
    const unit = (u) => (u ? `${kr(u.price)}/${u.unit}` : "");
    const best = data.best;
    const isBest = (source, id) => best && best.source === source && String(best.id) === String(id);
    const plan = this._state?.latest_plan;
    const products = data.products
      .map(
        (p) => `<li class="ev ${isBest("rema", p.id) ? "best" : ""}">
          ${this._chainLogo(REMA_ID, "tiny")}
          ${p.image ? `<img src="${esc(p.image)}" alt="" loading="lazy">` : '<span class="noimg">?</span>'}
          <div class="what"><b>${esc(p.name)}</b><span class="muted small">${esc(p.underline || "")}${p.unit_price ? ` · ${unit(p.unit_price)}` : ""}</span>
            ${isBest("rema", p.id) ? '<span class="badge eco">Billigst</span>' : ""}</div>
          <span class="ev-price ${onOffer(p) ? "sale" : ""}">${kr(p.price)}</span>
          <button class="btn small" data-action="ev-rema" data-arg="${esc(p.id)}" ${this._busy ? "disabled" : ""}>+ ${plan ? "Indkøb" : "REMA-listen"}</button>
        </li>`
      )
      .join("");
    const offers = data.offers
      .map(
        (o) => `<li class="ev ${isBest("chain", o.id) ? "best" : ""}">
          ${this._chainLogo(o.dealer_id, "tiny")}
          ${o.image ? `<img src="${esc(o.image)}" alt="" loading="lazy">` : '<span class="noimg">?</span>'}
          <div class="what"><b>${esc(o.heading)}</b><span class="muted small">${esc(this._chainName(o.dealer_id))}${o.description ? ` · ${esc(o.description)}` : ""}${o.unit_price ? ` · ${unit(o.unit_price)}` : ""}</span>
            ${isBest("chain", o.id) ? '<span class="badge eco">Billigst</span>' : ""}</div>
          <span class="ev-price sale">${o.price != null ? kr(o.price) : ""}</span>
          <button class="btn small" data-action="ev-chain" data-arg="${esc(o.id)}" ${this._busy || !plan ? "disabled" : ""} title="${plan ? "" : "Lav en madplan først"}">+ ${esc(this._chainName(o.dealer_id))}</button>
        </li>`
      )
      .join("");
    const chains = (this._state.settings.chains || []).length;
    return `<div class="everywhere-results">
      ${best
        ? `<p class="best-line">Billigst: <b>${unit(best.unit_price)}</b> hos ${esc(best.source === "rema" ? "REMA 1000" : this._chainName((data.offers.find((o) => o.id === best.id) || {}).dealer_id))}</p>`
        : ""}
      <h3>REMA 1000</h3>
      <ul class="evs">${products || '<li class="muted">Ingen varer fundet hos REMA.</li>'}</ul>
      ${chains
        ? `<h3>Tilbud i andre butikker</h3><ul class="evs">${offers || '<li class="muted">Ingen af de andre butikker har den på tilbud lige nu.</li>'}</ul>`
        : '<p class="muted small">Vælg andre butikker under Indstillinger › Andre butikker for at sammenligne med deres tilbud.</p>'}
    </div>`;
  }

  // Which of the plan's items are cheaper in the chosen chains (read once per change of the list).
  _ensureCompare() {
    const plan = this._plan;
    if (!plan || !(this._state.settings.chains || []).length) return null;
    const key = `${plan.id}|${plan.total}|${plan.shopping.length}|${(this._state.settings.chains || []).join(",")}`;
    if (this._compare?.key === key) return this._compare;
    this._compare = { key, loading: true, lines: {}, chains: {} };
    this._ws("middagsro/chains/compare", { plan_id: plan.id })
      .then((data) => {
        if (this._compare?.key === key) this._compare = { key, loading: false, ...data };
      })
      .catch(() => {
        if (this._compare?.key === key) this._compare = { key, loading: false, lines: {}, chains: {} };
      })
      .finally(() => this._tab === "shopping" && this._render());
    return this._compare;
  }

  _chainListsHtml(plan) {
    const byChain = {};
    plan.shopping.filter((l) => l.buy_at).forEach((l) => (byChain[l.buy_at] ||= []).push(l));
    return Object.entries(byChain)
      .map(([id, lines]) => {
        const total = lines.filter((l) => !l.bought).reduce((sum, l) => sum + (l.cost || 0), 0);
        const bought = lines.filter((l) => l.bought).length;
        const rows = lines
          .map(
            (l) => `<li class="cline ${l.bought ? "bought" : ""}">
              <button class="box" data-action="chain-tick" data-arg="${esc(l.id)}" aria-label="Købt" aria-pressed="${!!l.bought}">${l.bought ? "✓" : ""}</button>
              <div class="what"><b>${esc(l.chain_heading || l.product?.name || l.name)}</b>
                <span class="muted small">${l.chain_only ? esc(l.note || "") : l.price_estimated ? "Ikke på tilbud – anslået pris ud fra REMA 1000" : `I stedet for ${esc(l.product?.name || l.name)} hos REMA`}</span></div>
              <span class="cost"><b>${kr(l.cost)}</b></span>
              <span class="ctrl">
                <span class="stepper">
                  <button class="icon-btn" data-action="chain-count" data-arg="${esc(l.id)}|-1" aria-label="Færre">−</button>
                  <b>${l.packages || 1}</b>
                  <button class="icon-btn" data-action="chain-count" data-arg="${esc(l.id)}|1" aria-label="Flere">+</button>
                </span>
                ${l.chain_only ? "" : `<button class="icon-btn" data-action="chain-move" data-arg="${esc(l.id)}|" title="Tilbage på REMA-listen" aria-label="Tilbage på REMA-listen">↩</button>`}
                <button class="icon-btn" data-action="chain-delete" data-arg="${esc(l.id)}" aria-label="Slet">${CLOSE_ICON}</button>
              </span>
            </li>`
          )
          .join("");
        return `<div class="card chain-list" style="--c:${esc(this._chainInfo(id).color || "#888")}">
          <div class="row between wrap">
            <div class="row">${this._chainLogo(id)}<h1 class="flush">Indkøb i ${esc(this._chainName(id))}</h1></div>
            <div class="price"><span class="big">${kr(total)}</span><span class="muted">${lines.length - bought} mangler</span></div>
          </div>
          <ul class="clines">${rows}</ul>
          <div class="row wrap actions">
            <button class="btn" data-action="chain-clear" data-arg="${esc(id)}" ${this._busy ? "disabled" : ""}>Ryd kurven${bought ? ` (${bought} købt)` : ""}</button>
            <button class="btn" data-action="chain-open" data-arg="${esc(id)}" ${this._busy ? "disabled" : ""}>Se tilbud i ${esc(this._chainName(id))}</button>
          </div>
        </div>`;
      })
      .join("");
  }

  // ------------------------------------------------------------------ recipe collection

  // The collection's recipe for a plan's dinner (leftovers: the dish they are from).
  _recipeForDay(plan, day) {
    let cooked = day;
    if (day.uses_leftovers_from) cooked = plan.days.find((d) => d.date === day.uses_leftovers_from) || day;
    const recipes = this._state?.recipes || [];
    return {
      cooked,
      recipe: recipes.find((r) => r.id === cooked.recipe_id) || recipes.find((r) => normName(r.name) === normName(cooked.dish)),
    };
  }

  _rateButtons(plan, day) {
    const { cooked, recipe } = this._recipeForDay(plan, day);
    if (!cooked?.dish || cooked.type === "tom") return '<span class="rate"></span>';
    const on = { like: recipe?.rating === "like", dislike: recipe?.rating === "dislike", favorite: !!recipe?.favorite };
    return `<span class="rate">${["like", "dislike", "favorite"]
      .map(
        (a) => `<button class="rate-btn ${a} ${on[a] ? "on" : ""}" data-action="rate-day" data-arg="${esc(plan.id)}|${esc(day.date)}|${a}"
          title="${RATE_LABELS[a]}" aria-label="${RATE_LABELS[a]}: ${esc(cooked.dish)}" aria-pressed="${on[a]}" ${this._busy ? "disabled" : ""}>${RATE_ICONS[a]}</button>`
      )
      .join("")}</span>`;
  }

  _recipeRateButtons(recipe) {
    return `<span class="rate">${["like", "dislike", "favorite"]
      .map((a) => {
        const on = a === "favorite" ? !!recipe.favorite : recipe.rating === a;
        return `<button class="rate-btn ${a} ${on ? "on" : ""}" data-action="rate-recipe" data-arg="${esc(recipe.id || "")}|${a}"
          title="${RATE_LABELS[a]}" aria-label="${RATE_LABELS[a]}" aria-pressed="${on}" ${this._busy ? "disabled" : ""}>${RATE_ICONS[a]}</button>`;
      })
      .join("")}</span>`;
  }

  _filteredRecipes() {
    const words = normName(this._rc.query).split(" ").filter(Boolean);
    const list = (this._state.recipes || []).filter((r) => {
      if (this._rc.filter === "favorite" && !r.favorite) return false;
      if (["like", "dislike"].includes(this._rc.filter) && r.rating !== this._rc.filter) return false;
      const text = normName(`${r.name} ${(r.ingredient_names || []).join(" ")}`);
      return words.every((w) => text.includes(w));
    });
    const by = {
      name: (a, b) => a.name.localeCompare(b.name, "da"),
      newest: (a, b) => String(b.created || "").localeCompare(String(a.created || "")),
      most_used: (a, b) => (b.times_planned || 0) - (a.times_planned || 0) || a.name.localeCompare(b.name, "da"),
      quickest: (a, b) => (a.total_minutes || 999) - (b.total_minutes || 999),
    }[this._rc.sort];
    return list.sort(by);
  }

  _collectionRows() {
    const list = this._filteredRecipes();
    if (!list.length) {
      return (this._state.recipes || []).length
        ? '<p class="muted">Ingen opskrifter passer til søgningen.</p>'
        : '<p class="muted">Opskriftsamlingen er tom. Giv en ret 👍 eller ♥ på madplanen, indsæt et link til en opskrift, eller skriv en ny.</p>';
    }
    return list
      .map(
        (r) => `<div class="rc-item">
          <button class="rc-open" data-action="rc-open" data-arg="${esc(r.id)}">
            <b>${esc(r.name)}</b>
            <span class="muted small">${[
              r.total_minutes ? `${r.total_minutes} min` : "",
              r.type === "vegetar" ? "Vegetar" : "",
              r.times_planned ? `brugt ${r.times_planned} ${r.times_planned === 1 ? "gang" : "gange"}` : "",
              r.source === "link" ? "fra link" : r.source === "manual" ? "egen opskrift" : "",
            ]
              .filter(Boolean)
              .join(" · ")}</span>
          </button>
          ${this._recipeRateButtons(r)}
        </div>`
      )
      .join("");
  }

  _collectionView() {
    const filters = Object.entries(RECIPE_FILTERS)
      .map(([k, l]) => `<button class="chip ${this._rc.filter === k ? "active" : ""}" data-action="rc-filter" data-arg="${k}">${l}</button>`)
      .join("");
    return `
      <div class="card">
        <h2 class="flush">Tilføj en opskrift</h2>
        <div class="row wrap">
          <input class="grow" type="url" inputmode="url" data-bind="rc" data-field="link" value="${esc(this._rc.link)}" placeholder="Indsæt et link til en opskrift">
          <button class="btn primary" data-action="rc-import" ${this._rc.importing ? "disabled" : ""}>${this._rc.importing ? '<span class="spinner small"></span> Henter …' : "Hent opskrift"}</button>
          <button class="btn" data-action="rc-new">Skriv selv</button>
        </div>
        <p class="muted small">Opskriften hentes fra siden, og du kan rette den, før den gemmes. Linket gemmes ikke.</p>
      </div>
      <div class="card">
        <div class="row wrap">
          <input class="grow" type="search" data-bind="rc" data-field="query" value="${esc(this._rc.query)}" placeholder="Søg i opskrifter og ingredienser">
          <label class="field inline">Sortér
            <select data-bind="rc" data-field="sort">${Object.entries(RECIPE_SORTS)
              .map(([k, l]) => `<option value="${k}" ${this._rc.sort === k ? "selected" : ""}>${l}</option>`)
              .join("")}</select></label>
        </div>
        <div class="chips">${filters}</div>
        <div id="rc-list" class="rc-list">${this._collectionRows()}</div>
      </div>`;
  }

  async _recipeImport() {
    const url = this._rc.link.trim();
    if (!url) return this._say("Indsæt et link først.");
    this._rc.importing = true;
    this._render();
    try {
      const recipe = await this._ws("middagsro/recipes/import", { url });
      this._rc.link = "";
      this._modal = { kind: "recipe", recipe: { ...recipe, id: null }, imported: true };
      this._renderModal();
    } catch (err) {
      this._say(`Fejl: ${err?.message || err}`);
    }
    this._rc.importing = false;
    this._render();
  }

  async _recipeOpen(id) {
    this._modal = { kind: "recipe", loading: true, recipe: { id, name: "" } };
    this._renderModal();
    try {
      const recipe = await this._ws("middagsro/recipes/get", { recipe_id: id });
      if (this._modal?.kind === "recipe" && this._modal.recipe.id === id) {
        this._modal = { kind: "recipe", recipe: clone(recipe) };
        this._renderModal();
      }
    } catch (err) {
      this._modal = null;
      this._renderModal();
      this._say(`Fejl: ${err?.message || err}`);
    }
  }

  async _recipeSave() {
    const m = this._modal;
    if (m?.kind !== "recipe" || m.busy) return;
    const r = m.recipe;
    if (!String(r.name || "").trim()) return this._say("Giv opskriften et navn.");
    const recipe = {
      ...r,
      ingredients: r.ingredients.filter((i) => String(i.name || "").trim()),
      steps: r.steps.filter((st) => String(st.text || "").trim()),
    };
    if (!recipe.id) delete recipe.id;
    m.busy = true;
    this._renderModal();
    try {
      const saved = await this._ws("middagsro/recipes/save", { recipe });
      this._modal = null;
      this._renderModal();
      this._recipesSub = "collection";
      this._say(r.id ? "Opskriften er gemt." : `${saved.name} er gemt i opskriftsamlingen.`);
      await this._load(true);
    } catch (err) {
      m.busy = false;
      m.error = err?.message || String(err);
      this._renderModal();
    }
  }

  // The days a recipe can be put on: the newest plan's, from today.
  _planTargets() {
    const today = localToday();
    const timeline = this._timeline();
    if (timeline) return timeline.filter((e) => e.day && e.date >= today).map((e) => ({ plan: e.plan, day: e.day }));
    const plan = this._state?.latest_plan;
    return plan ? plan.days.filter((d) => d.date >= today).map((day) => ({ plan, day })) : [];
  }

  async _recipeToPlan(arg) {
    const m = this._modal;
    const [planId, date] = String(arg).split("|");
    if (m?.kind !== "recipe" || !m.recipe.id || m.busy) return;
    m.busy = "plan";
    m.error = null;
    this._renderModal();
    try {
      await this._ws("middagsro/recipes/plan", { recipe_id: m.recipe.id, plan_id: planId, date });
      this._modal = null;
      this._renderModal();
      await this._load();
      this._say(`${m.recipe.name} er sat på madplanen ${dateLabel(date).toLowerCase()} – indkøbslisten er lavet om.`);
    } catch (err) {
      m.busy = false;
      m.error = err?.message || String(err);
      this._renderModal();
    }
  }

  _recipeModal(m) {
    if (m.loading) {
      return `<div class="scrim" data-action="modal-close"></div>
        <div class="dialog wide" role="dialog" aria-modal="true"><p><span class="spinner small"></span> Henter opskriften …</p></div>`;
    }
    const r = m.recipe;
    const busy = !!m.busy;
    const field = (name, value, attrs = "") =>
      `<input data-bind="rcp" data-field="${name}" value="${esc(value ?? "")}" ${attrs}>`;
    const ingredients = r.ingredients
      .map(
        (ing, i) => `<div class="rc-ing">
          <input type="text" class="amount" data-bind="rcp" data-list="ingredients" data-idx="${i}" data-field="amount" value="${esc(ing.amount)}" placeholder="Mængde">
          <input type="text" class="grow" data-bind="rcp" data-list="ingredients" data-idx="${i}" data-field="name" value="${esc(ing.name)}" placeholder="Ingrediens">
          <button class="icon-btn" data-action="rc-row" data-arg="ingredients|del|${i}" aria-label="Fjern ingrediens">${CLOSE_ICON}</button>
        </div>`
      )
      .join("");
    const steps = r.steps
      .map(
        (st, i) => `<div class="rc-step">
          <span class="num">${i + 1}</span>
          <textarea class="grow" rows="2" data-bind="rcp" data-list="steps" data-idx="${i}" data-field="text" placeholder="Trin">${esc(st.text)}</textarea>
          <button class="icon-btn" data-action="rc-row" data-arg="steps|del|${i}" aria-label="Fjern trin">${CLOSE_ICON}</button>
        </div>`
      )
      .join("");
    const targets = m.picking
      ? `<div class="rc-targets">${this._planTargets()
          .map(
            ({ plan, day }) => `<button class="option" data-action="rc-plan-day" data-arg="${esc(plan.id)}|${esc(day.date)}" ${busy ? "disabled" : ""}>
              <b>${esc(dateLabel(day.date))}</b><span class="muted small">${esc(day.dish || "Ingen ret")}</span></button>`
          )
          .join("") || '<p class="muted">Der er ingen dage at sætte den på – lav en madplan først.</p>'}
          ${m.busy === "plan" ? '<p class="muted small"><span class="spinner small"></span> Finder varer og sætter retten på …</p>' : ""}</div>`
      : "";
    return `
      <div class="scrim" data-action="modal-close"></div>
      <div class="dialog wide" role="dialog" aria-modal="true" aria-label="Opskrift">
        <div class="rc-head">
          <input type="text" class="rc-name" data-bind="rcp" data-field="name" value="${esc(r.name)}" placeholder="Rettens navn">
          ${this._recipeRateButtons(r)}
        </div>
        ${m.imported ? '<p class="muted small">Hentet fra linket. Ret det, der skal rettes, og gem den i opskriftsamlingen.</p>' : ""}
        ${m.error ? `<div class="banner error">${esc(m.error)}</div>` : ""}
        <div class="grid rc-meta">
          <label class="field">Personer ${field("servings", r.servings, 'type="number" min="1" max="50"')}</label>
          <label class="field">Min. aktiv ${field("active_minutes", r.active_minutes, 'type="number" min="0" max="600"')}</label>
          <label class="field">Min. i alt ${field("total_minutes", r.total_minutes, 'type="number" min="0" max="1440"')}</label>
          <label class="field">Type
            <select data-bind="rcp" data-field="type">
              <option value="normal" ${r.type !== "vegetar" ? "selected" : ""}>Med kød/fisk</option>
              <option value="vegetar" ${r.type === "vegetar" ? "selected" : ""}>Vegetar</option>
            </select></label>
        </div>
        <h3>Ingredienser</h3>
        ${ingredients}
        <button class="btn small" data-action="rc-row" data-arg="ingredients|add">+ Ingrediens</button>
        <h3>Sådan gør du</h3>
        ${steps}
        <button class="btn small" data-action="rc-row" data-arg="steps|add">+ Trin</button>
        <label class="field">Tip <textarea rows="2" data-bind="rcp" data-field="tip">${esc(r.tip || "")}</textarea></label>
        ${targets}
        <div class="row wrap dialog-actions">
          <button class="btn primary" data-action="rc-save" ${busy ? "disabled" : ""}>${r.id ? "Gem" : "Gem i opskriftsamlingen"}</button>
          ${r.id ? `<button class="btn" data-action="rc-plan" ${busy ? "disabled" : ""}>${aiLabel("Tilføj til madplan")}</button>` : ""}
          ${r.id ? `<button class="btn danger" data-action="rc-delete" ${busy ? "disabled" : ""}>Slet</button>` : ""}
          <span class="spacer"></span>
          <button class="btn" data-action="modal-close" ${busy ? "disabled" : ""}>Luk</button>
        </div>
      </div>`;
  }

  _renderStatus() {
    const node = this.shadowRoot.querySelector("#status");
    if (node) node.innerHTML = this._statusHtml();
  }

  _statusHtml() {
    const status = this._state?.status;
    if (!status) return "";
    if (status.state === "generating") {
      return `<div class="banner info"><span class="spinner"></span>${esc(status.message || "Laver madplan …")}</div>`;
    }
    if (status.state === "error") {
      return `<div class="banner error"><b>Madplanen kunne ikke laves:</b> ${esc(status.message)}</div>`;
    }
    return "";
  }

  _render() {
    const state = this._state;
    let body;
    if (this._error && !state) {
      body = `<div class="card"><h2>Middagsro kunne ikke indlæses</h2><p>${esc(this._error)}</p>
        <button class="btn" data-action="refresh">Prøv igen</button></div>`;
    } else if (!state) {
      body = `<div class="card center"><span class="spinner"></span> Indlæser …</div>`;
    } else {
      body = {
        plan: () => this._planView(),
        recipes: () => this._recipesView(),
        shopping: () => this._shoppingView(),
        favorites: () => this._favoritesView(),
        health: () => this._healthView(),
        history: () => this._historyView(),
        settings: () => this._settingsView(),
      }[this._tab]();
      if (this._tab === "plan" && this._chain) body = this._chainView();
      if (this._tab === "plan") body += CREDIT;
    }
    const root = this.shadowRoot;
    // The toolbar and tabs are built once, so their horizontal scroll survives.
    if (!root.querySelector("#content")) {
      const tabs = TABS.map(
        ([key, label]) =>
          `<button class="tab${EXTRA_TABS.has(key) ? " extra" : ""}" data-action="tab" data-arg="${key}">${TAB_ICONS[key] || ""}<span>${label}</span></button>`
      ).join("");
      const extra = TABS.filter(([key]) => EXTRA_TABS.has(key))
        .map(([key, label]) => `<button class="more-item" data-action="tab" data-arg="${key}">${TAB_ICONS[key] || ""}<span>${label}</span></button>`)
        .join("");
      root.innerHTML = `
        <style>${STYLE}</style>
        <div id="top"></div>
        <div class="toolbar">
          <ha-menu-button></ha-menu-button>
          <span class="brand"><img class="logo" src="${this._img("icon.svg")}" alt=""><span class="wordmark">Middagsro</span></span>
          <span class="spacer"></span>
          <span id="busy"></span>
        </div>
        <nav class="tabs">${tabs}<button class="tab more" data-action="more" aria-expanded="false"></button></nav>
        <div class="more-scrim" data-action="more" hidden></div>
        <div class="more-sheet" hidden>${extra}</div>
        <main id="content"></main>
        <div id="modal"></div>
        <div id="toast"></div>`;
    }
    const menu = root.querySelector("ha-menu-button");
    if (menu) {
      menu.hass = this._hass;
      menu.narrow = this._narrow;
    }
    root.querySelectorAll(".tab, .more-item").forEach((tab) => tab.classList.toggle("active", tab.dataset.arg === this._tab));
    const more = root.querySelector(".tab.more");
    if (more) {
      more.classList.toggle("active", this._moreOpen || EXTRA_TABS.has(this._tab));
      more.setAttribute("aria-expanded", String(!!this._moreOpen));
      more.innerHTML = this._moreOpen ? `${CLOSE_ICON}<span>Luk</span>` : `${MORE_ICON}<span>Mere</span>`;
    }
    for (const sel of [".more-sheet", ".more-scrim"]) {
      const el = root.querySelector(sel);
      if (el) el.hidden = !this._moreOpen;
    }
    root.querySelector("#busy").innerHTML = this._busy ? '<span class="spinner small"></span>' : "";
    const oldChips = root.querySelector(".chips");
    const chipsLeft = oldChips ? oldChips.scrollLeft : 0;
    root.querySelector("#content").innerHTML = `<div id="status">${this._statusHtml()}</div>${body}`;
    root.querySelector("#toast").innerHTML = this._toast ? `<div class="toast">${esc(this._toast)}</div>` : "";
    const chips = root.querySelector(".chips");
    if (chips) chips.scrollLeft = chipsLeft;
    this._keepVisible(root.querySelector(".tabs"), root.querySelector(".tab.active"));
    this._keepVisible(chips, chips?.querySelector(".chip.active"));
    this._tickTimers();
  }

  // The popup lives outside #content, so polling while a plan is made doesn't
  // redraw it under the user's fingers.
  _renderModal() {
    const node = this.shadowRoot.querySelector("#modal");
    if (!node) return;
    if (this._modal?.kind === "day") {
      node.innerHTML = this._dayModal(this._modal);
      return;
    }
    if (this._modal?.kind === "pantry") {
      node.innerHTML = this._pantryModal(this._modal);
      return;
    }
    if (this._modal?.kind === "where") {
      const e = this._everywhere;
      node.innerHTML = `<div class="scrim" data-action="modal-close"></div>
        <div class="dialog wide where" role="dialog" aria-modal="true" aria-label="Priser">
          <div class="dialog-top"><h2>${esc(this._modal.title)}</h2>
            <button class="icon-btn close" data-action="modal-close" aria-label="Luk">${CLOSE_ICON}</button></div>
          <div class="row wrap everywhere">
            <input class="grow" type="search" data-bind="everywhere" value="${esc(e.query)}" placeholder="Søg på en vare">
            <button class="btn" data-action="everywhere" ${e.loading ? "disabled" : ""}>${e.loading ? '<span class="spinner small"></span>' : "Søg"}</button>
          </div>
          <div class="ev-out">${e.error ? `<div class="banner error">${esc(e.error)}</div>` : ""}
          ${e.loading && !e.data ? '<p class="muted"><span class="spinner small"></span> Finder priserne …</p>' : e.data ? this._everywhereHtml(e.data) : ""}</div>
          <div class="dialog-bottom"><button class="btn" data-action="modal-close">Luk</button></div>
        </div>`;
      return;
    }
    if (this._modal?.kind === "recipe") {
      // Keep the scroll position when rows are added or removed.
      const top = node.querySelector(".dialog")?.scrollTop || 0;
      node.innerHTML = this._recipeModal(this._modal);
      const dialog = node.querySelector(".dialog");
      if (dialog) dialog.scrollTop = top;
      return;
    }
    if (this._modal?.kind === "line") {
      node.innerHTML = this._lineModal(this._modal);
      return;
    }
    if (!this._noteOpen) {
      node.innerHTML = "";
      return;
    }
    const busy = this._busy || this._state?.status?.state === "generating";
    node.innerHTML = `
      <div class="scrim" data-action="note-close"></div>
      <div class="dialog" role="dialog" aria-modal="true" aria-labelledby="note-title">
        <h2 id="note-title">Ønsker til madplanen</h2>
        <p class="muted small">Bruges kun i den næste madplan og fjernes derefter. Fx varer i køleskabet, der skal bruges inden en dato, eller en bestemt ret på en bestemt dag.</p>
        <textarea id="note-text" data-bind="note" rows="5" maxlength="1000"
          placeholder="Fx: Fløde og 500 g hakket kylling skal bruges inden tirsdag. Pizza fredag.">${esc(this._noteDraft)}</textarea>
        <div class="row wrap dialog-actions">
          <button class="btn primary" data-action="note-generate" ${busy ? "disabled" : ""}>${aiLabel("Gem og lav madplan")}</button>
          <button class="btn" data-action="note-save">Gem</button>
          ${this._micButton("note")}
          ${this._state?.note ? '<button class="btn danger" data-action="note-clear">Fjern</button>' : ""}
          <span class="spacer"></span>
          <button class="btn" data-action="note-close">Annullér</button>
        </div>
      </div>`;
  }

  // "Gem i Mealie" for the plan's own recipes, "Åbn i Mealie" for the family's.
  _mealieButton(planId, date) {
    const mealie = this._state?.mealie;
    if (!mealie?.available) return "";
    const plan = this._planOf(planId);
    let day = plan?.days.find((d) => d.date === date);
    if (day?.uses_leftovers_from) day = plan.days.find((d) => d.date === day.uses_leftovers_from) || day;
    if (!day?.dish) return "";
    if (day.mealie) {
      return mealie.url
        ? `<a class="btn" href="${esc(`${mealie.recipes || `${mealie.url}/g/home/r/`}${encodeURIComponent(day.mealie)}`)}" target="_blank" rel="noopener">Åbn i Mealie</a>`
        : "";
    }
    if (!day.steps?.length) return "";
    return `<button class="btn" data-action="mealie-save" data-arg="${esc(planId)}|${esc(day.date)}" ${this._busy ? "disabled" : ""}>Gem i Mealie</button>`;
  }

  _dayModal(m) {
    const busy = !!m.busy;
    const options = (m.options || [])
      .map(
        (o, i) => `<button class="option" data-action="swap-pick" data-arg="${i}" ${busy ? "disabled" : ""}>
          <span class="option-dish"><b>${esc(o.dish)}</b>${o.type === "vegetar" ? ' <span class="badge eco">Vegetar</span>' : ""}${o.mealie ? ' <span class="badge mealie">Mealie</span>' : ""}</span>
          ${o.why ? `<span class="muted small">${esc(o.why)}</span>` : ""}
          <span class="muted small">${o.active_minutes ? `${o.active_minutes} min aktiv` : ""}${o.total_minutes ? ` · ${o.total_minutes} min i alt` : ""}</span>
          ${m.busy === "swap" && m.picked === i ? '<span class="muted small"><span class="spinner small"></span> Finder varer og skriver opskriften …</span>' : ""}
        </button>`
      )
      .join("");
    const body = m.options
      ? `<p class="muted small">Vælg en ret. Indkøbslisten og opskriften bliver lavet om${m.leftovers ? ", også for resterne" : ""}.</p>
         <div class="options">${options}</div>
         <div class="row wrap dialog-actions">
           <button class="btn" data-action="swap-options" ${busy ? "disabled" : ""}>
             ${m.busy === "options" ? '<span class="spinner small"></span> Finder andre retter …' : aiLabel("Tre nye forslag")}</button>
           <span class="spacer"></span>
           <button class="btn" data-action="modal-close" ${busy ? "disabled" : ""}>Annullér</button>
         </div>`
      : `${m.leftovers ? '<p class="muted small">Det er rester – skifter du, skiftes retten, de er rester af.</p>' : ""}
         <div class="row wrap dialog-actions">
           ${m.dish ? `<button class="btn" data-action="day-recipe" ${busy ? "disabled" : ""}>Se opskriften</button>` : ""}
           ${this._mealieButton(m.planId, m.date)}
           <button class="btn primary" data-action="swap-options" ${busy ? "disabled" : ""}>
             ${m.busy === "options" ? '<span class="spinner small"></span> Finder retter …' : aiLabel(m.dish ? "Skift retten – tre forslag" : "Find en ret – tre forslag")}</button>
         </div>
         <div class="row wrap dialog-actions">
           ${m.dish ? `<button class="btn danger" data-action="day-clear" data-arg="delete" ${busy ? "disabled" : ""}>Slet retten</button>` : ""}
           <button class="btn danger" data-action="day-clear" data-arg="skip" ${busy ? "disabled" : ""}>Spring dagen over</button>
           <span class="spacer"></span>
           <button class="btn" data-action="modal-close" ${busy ? "disabled" : ""}>Luk</button>
         </div>`;
    return `
      <div class="scrim" data-action="modal-close"></div>
      <div class="dialog" role="dialog" aria-modal="true" aria-labelledby="day-title">
        <h2 id="day-title">${esc(m.dish || "Ingen ret")}</h2>
        <p class="muted">${esc(dateLabel(m.date))}</p>
        ${m.error ? `<div class="banner error">${esc(m.error)}</div>` : ""}
        ${body}
      </div>`;
  }

  _pantryModal(m) {
    const items = (m.items || [])
      .map((item) => {
        const uses = item.uses.map((u) => `${esc(u.dish)}${u.amount ? `: ${esc(u.amount)}` : ""}`).join(" · ");
        const need = item.amount ? ` · i alt ${item.amount} ${esc(item.unit)}` : "";
        const action = item.on_list
          ? '<span class="badge eco">På listen ✓</span>'
          : `<button class="btn small primary" data-action="pantry-add" data-arg="${esc(item.name)}" ${m.busy ? "disabled" : ""}>
               ${m.busy === item.name ? '<span class="spinner small"></span>' : "+ Tilføj til indkøb"}</button>`;
        return `<li class="pantry-item"><div class="what"><b>${esc(item.name.charAt(0).toUpperCase() + item.name.slice(1))}</b>
            <span class="muted small">${uses}${need}</span></div>${action}</li>`;
      })
      .join("");
    const empty =
      m.busy === "load"
        ? '<p class="muted"><span class="spinner small"></span> Kigger i opskrifterne …</p>'
        : '<p class="muted">Opskrifterne bruger ingen af jeres basisvarer – eller de er ikke skrevet endnu.</p>';
    return `
      <div class="scrim" data-action="modal-close"></div>
      <div class="dialog" role="dialog" aria-modal="true" aria-labelledby="pantry-title">
        <h2 id="pantry-title">Basisvarer i madplanen</h2>
        <p class="muted small">Varer fra opskrifterne, som I har som basisvarer (Indstillinger) og derfor ikke står på indkøbslisten. Mangler I en, så tilføj den – varen vælges efter jeres indstillinger.</p>
        ${m.error ? `<div class="banner error">${esc(m.error)}</div>` : ""}
        ${items ? `<ul class="lines">${items}</ul>` : empty}
        <div class="row wrap dialog-actions"><span class="spacer"></span>
          <button class="btn" data-action="modal-close" ${m.busy && m.busy !== "load" ? "disabled" : ""}>Luk</button></div>
      </div>`;
  }

  // Search REMA and add a product to the main list or the later one.
  _shopSearchHtml(part) {
    const search = this._shopSearch[part];
    const results = search.loading
      ? '<p class="muted"><span class="spinner small"></span> Søger …</p>'
      : search.results
          .map(
            (p, i) => `<button class="result" data-action="shop-add" data-arg="${part}|${i}" ${this._busy ? "disabled" : ""}>
              ${p.image ? `<img src="${esc(p.image)}" alt="">` : ""}
              <span><b>${esc(p.name)}</b><span class="muted">${esc(p.underline || "")} · ${kr(p.price)}</span></span>
              ${p.is_organic ? '<span class="badge eco">Øko</span>' : ""}<span class="add">+ Tilføj</span></button>`
          )
          .join("");
    return `<div class="shop-search">
        <div class="row wrap">
          <input class="grow" type="search" data-bind="shopsearch" data-part="${part}" value="${esc(search.query)}"
            placeholder="Tilføj en vare – søg i REMA 1000, fx kaffe">
          <button class="btn small" data-action="shop-search" data-arg="${part}">Søg</button>
        </div>
        <div class="results">${results}</div>
      </div>`;
  }

  _keepVisible(container, item) {
    // Scroll a horizontal strip just enough to show the active item.
    if (!container || !item) return;
    const left = item.offsetLeft - container.offsetLeft;
    const right = left + item.offsetWidth;
    if (left < container.scrollLeft) container.scrollLeft = left - 12;
    else if (right > container.scrollLeft + container.clientWidth) {
      container.scrollLeft = right - container.clientWidth + 12;
    }
  }

  // The dates the next plan covers, from the chosen first day.
  _planDates() {
    const start = this._startDate || this._state?.default_start;
    const count = this._state?.settings?.days || 7;
    if (!start) return [];
    const pad = (n) => String(n).padStart(2, "0");
    const last = this._lastAvisDay();
    return Array.from({ length: count }, (_, i) => {
      const d = new Date(`${start}T12:00:00`);
      d.setDate(d.getDate() + i);
      return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
    }).filter((iso) => !last || iso <= last || start > last);
  }

  // The last day of the newest avis that is out: a plan can't be priced after it.
  _lastAvisDay() {
    const cat = this._state?.catalogs || {};
    return localDay(cat.upcoming?.valid_to || cat.current?.valid_to || "");
  }

  _generateControls(label = "Lav ny madplan") {
    const generating = this._state?.status?.state === "generating";
    const skip = this._planDates()
      .map(
        (iso) => `<label class="check skipday"><input type="checkbox" data-bind="skip" value="${iso}" ${this._skip.has(iso) ? "checked" : ""}> ${esc(dateLabel(iso))}</label>`
      )
      .join("");
    const note = this._state?.note;
    const cat = this._state?.catalogs || {};
    const last = this._lastAvisDay();
    return `<div class="row wrap">
      <label class="field inline">Første dag
        <input type="date" data-bind="start" value="${esc(this._startDate || "")}" ${last ? `max="${esc(last)}"` : ""}>
      </label>
    </div>
    ${cat.current && !cat.upcoming && last
      ? `<p class="muted small">Næste uges avis er ikke ude endnu, så madplanen kan højst gå til og med ${esc(dateLabel(last))}.</p>`
      : ""}
    <div class="wishes">
      <button class="btn" data-action="note-open">${note ? "Ret ønsker til madplanen" : "Ønsker til madplanen"}</button>
      ${note ? `<p class="muted small note-preview">Bruges i næste madplan: ${esc(note)}</p>` : ""}
    </div>
    ${skip ? `<p class="muted small skiphead">Spring over (ingen aftensmad de dage):</p><div class="skipdays">${skip}</div>` : ""}
    <div class="row wrap skipgo">
      <button class="btn primary" data-action="generate" ${generating || this._busy ? "disabled" : ""}>
        ${generating ? "Laves …" : aiLabel(label)}
      </button>
      <button class="btn surprise" data-action="surprise" ${generating || this._busy ? "disabled" : ""}
        title="Retter I aldrig har fået – fra andre køkkener og med overraskende smage">${SURPRISE_ICON}Overrask os</button>
    </div>`;
  }

  _planView() {
    const plan = this._plan;
    const cat = this._state.catalogs;
    const catLine = [
      cat.current ? `Aktuel avis: ${esc(cat.current.label || "")} (til ${shortDate(localDay(cat.current.valid_to))})` : "",
      cat.upcoming
        ? `Næste avis: ${esc(cat.upcoming.label || "")} fra ${shortDate(localDay(cat.upcoming.valid_from))}`
        : "Næste uges avis er ikke udkommet endnu",
    ]
      .filter(Boolean)
      .join(" · ");
    if (!plan) {
      return `<div class="card hero">
        <img src="${this._img("icon.png")}" class="hero-icon" alt="">
        <h1>Ingen madplan endnu</h1>
        <p>Madplanen laves med AI ud fra ugens tilbud og jeres indstillinger. Tjek indstillingerne først, og tryk så på knappen.</p>
        ${this._generateControls("Lav madplan")}
        <p class="muted">${catLine}</p>
      </div>${this._chainsCard()}`;
    }
    const over = plan.budget && plan.total > plan.budget;
    const today = localToday();
    const dayRow = (owner, day) => {
      const type = TYPE_LABELS[day.type] ?? day.type;
      const past = day.date < today;
      return `<div class="day-row ${past ? "past" : ""}"><button class="day ${day.date === today ? "today" : ""}" data-action="day-menu" data-arg="${esc(owner.id)}|${day.date}">
          <span class="date">${day.date === today ? `I aften · ${esc(dateLabel(day.date))}` : esc(dateLabel(day.date))}</span>
          <span class="dish ${day.dish ? "" : "muted"}">${esc(day.dish || "Ingen ret – tryk for at vælge en")}</span>
          <span class="meta">${day.total_minutes ? `${day.total_minutes} min` : ""}${type ? ` <span class="badge">${esc(type)}</span>` : ""}${day.mealie ? ' <span class="badge mealie">Mealie</span>' : ""}${owner.surprise ? ' <span class="badge surprise">Overraskelse</span>' : ""}</span>
        </button>${this._rateButtons(owner, day)}</div>`;
    };
    // The newest plan decides each date; this week and the coming days show as one plan.
    const timeline = this._timeline();
    let title = plan.title;
    let period = `${dateLabel(plan.start_date)} – ${dateLabel(plan.end_date)}`;
    let skipped = plan.skipped || [];
    let avis = plan.catalog ? ` · ${plan.catalog.label || ""}` : "";
    let shopFrom = "";
    let days;
    if (timeline) {
      const weeks = [...new Set(timeline.map((e) => e.week))];
      title = weeks.length > 1 ? `Madplan uge ${weeks[0]}–${weeks[weeks.length - 1]}` : `Madplan uge ${weeks[0]}`;
      const shown = timeline.filter((e) => e.day);
      period = shown.length ? `${dateLabel(shown[0].date)} – ${dateLabel(shown[shown.length - 1].date)}` : period;
      skipped = timeline.filter((e) => e.skipped && e.date >= today).map((e) => e.date);
      avis = "";
      // Days from older plans: the price and the list are the newest plan's.
      if (timeline.some((e) => e.plan.id !== plan.id)) shopFrom = `indkøb fra ${dateLabel(plan.start_date)}`;
      let week = null;
      days = shown
        .map((e) => {
          const head = weeks.length > 1 && e.week !== week ? `<h3 class="week-head">Uge ${esc(e.week)}</h3>` : "";
          week = e.week;
          return head + dayRow(e.plan, e.day);
        })
        .join("");
    } else {
      days = plan.days.map((day) => dayRow(plan, day)).join("");
    }
    const checklist = (plan.checklist || [])
      .map((c) => `<li class="${c.ok ? "ok" : "bad"}">${c.ok ? "✓" : "✗"} ${esc(c.requirement)}</li>`)
      .join("");
    return `
      ${this._viewingLatest ? "" : `<div class="banner info">Du ser en ældre madplan. <button class="link" data-action="view-latest">Vis nyeste</button></div>`}
      ${this._chainsCard()}
      <div class="card">
        <div class="row between wrap">
          <div>
            <h1>${esc(title)}</h1>
            <p class="muted">${esc(period)}${esc(avis)}${skipped.length ? `<br>Springes over: ${skipped.map((d) => esc(dateLabel(d))).join(", ")}` : ""}</p>
          </div>
          <div class="price ${over ? "over" : ""}">
            <span class="big">${kr(plan.total)}</span>
            <span class="muted">${[shopFrom, plan.budget ? `budget ${kr(plan.budget)}` : ""].filter(Boolean).map(esc).join(" · ")}</span>
          </div>
        </div>
        ${plan.summary ? `<p>${esc(plan.summary)}</p>` : ""}
        ${over ? `<div class="banner warn">Planen er over budget. Prøv at lave en ny, eller ret budgettet i indstillingerne.</div>` : ""}
        <div class="days">${days}</div>
        <div class="help-row">
          ${this._planHelp ? '<p class="muted small help-text">Tryk på en ret for at se opskriften eller skifte den ud. 👍, 👎 og ♥ gemmer retten i opskriftsamlingen – tryk igen for at fortryde.</p>' : ""}
          <button class="help-q" data-action="plan-help" aria-expanded="${this._planHelp ? "true" : "false"}" aria-label="Hjælp" title="Hjælp">?</button>
        </div>
        <div class="row wrap actions">
          <button class="btn primary" data-action="send" ${this._busy ? "disabled" : ""}>
            ${plan.status === "sent" ? "Sendt ✓ – send igen" : "Send til REMA-listen"}
          </button>
          ${plan.shopping.some((line) => line.buy_from)
            ? `<span class="muted small">+ ${plan.shopping.filter((line) => line.buy_from).length} varer købes senere – se Indkøb</span>`
            : ""}
          <button class="btn" data-action="tab" data-arg="shopping">Se indkøbsliste</button>
          <button class="btn" data-action="open-day" data-arg="">Start madlavning</button>
          ${this._state.mealie?.available ? `<button class="btn" data-action="mealie-sync" ${this._busy ? "disabled" : ""}>Sæt ugen i Mealie-kalenderen</button>` : ""}
        </div>
        ${checklist || plan.deviations ? `<details><summary>Krav-tjekliste</summary><ul class="checklist">${checklist}</ul>${plan.deviations ? `<p class="muted">${esc(plan.deviations)}</p>` : ""}</details>` : ""}
      </div>
      <div class="card">
        <h2>Det skal AI'en huske</h2>
        <p class="muted small">Faste ønsker til alle madplaner – skriv eller diktér. De kan også rettes under Indstillinger.</p>
        ${this._rulesHtml()}
      </div>
      <div class="card">
        <h2>Ny madplan</h2>
        ${this._generateControls()}
        <p class="muted">${catLine}</p>
      </div>`;
  }

  // Which plan and date the chosen recipe day belongs to; a new plan or a new
  // day starts again on today's dish.
  _recipeKey() {
    return `${this._plan?.id}|${localToday()}`;
  }

  _recipesView() {
    const seg = `<div class="seg subnav">
        <button class="${this._recipesSub === "week" ? "active" : ""}" data-action="recipes-sub" data-arg="week">Ugens opskrifter</button>
        <button class="${this._recipesSub === "collection" ? "active" : ""}" data-action="recipes-sub" data-arg="collection">Opskriftsamling${this._state.recipes?.length ? ` (${this._state.recipes.length})` : ""}</button>
      </div>`;
    return seg + (this._recipesSub === "collection" ? this._collectionView() : this._weekRecipesView());
  }

  _weekRecipesView() {
    const list = this._recipeDays();
    if (!list.length) return `<div class="card">Der er ingen madplan endnu.</div>`;
    if (this._dayKey !== this._recipeKey()) {
      // Today, or the first day if no plan has a dinner today.
      this._day = this._recipeIndex("");
      this._dayKey = this._recipeKey();
    }
    const idx = Math.min(this._day, list.length - 1);
    const { plan, day } = list[idx];
    const key = `${plan.id}|${day.date}`;
    const today = localToday();
    const chips = list
      .map(
        ({ day: d }, i) =>
          `<button class="chip ${i === idx ? "active" : ""}" data-action="day" data-arg="${i}">${d.date === today ? "I aften" : esc(dateLabel(d.date))}</button>`
      )
      .join("");
    const ingredients = day.ingredients
      .map((ing, i) => {
        const id = `${key}|i${i}`;
        return `<li class="${this._checked[id] ? "done" : ""}" data-action="tick" data-arg="${esc(id)}">
          <span class="box">${this._checked[id] ? "✓" : ""}</span>
          <span class="amount">${esc(ing.amount)}</span> ${esc(ing.name)}</li>`;
      })
      .join("");
    const steps = day.steps
      .map((step, i) => {
        const id = `${key}|s${i}`;
        const timer = step.minutes
          ? this._timers[id]
            ? `<button class="timer running" data-action="timer" data-arg="${esc(id)}|${step.minutes}"><span data-timer="${esc(id)}">${step.minutes}:00</span> ✕</button>`
            : `<button class="timer" data-action="timer" data-arg="${esc(id)}|${step.minutes}">⏱ ${step.minutes} min</button>`
          : "";
        return `<li class="step ${this._checked[id] ? "done" : ""}">
          <div class="step-text" data-action="tick" data-arg="${esc(id)}"><span class="num">${i + 1}</span>${esc(step.text)}</div>
          ${timer}</li>`;
      })
      .join("");
    const type = TYPE_LABELS[day.type] ?? day.type;
    const leftovers = day.uses_leftovers_from
      ? `<div class="banner info">Rester fra ${esc(dateLabel(day.uses_leftovers_from))} – varm op og server.</div>`
      : day.makes_leftovers
        ? `<div class="banner info">Lav dobbelt portion – resten bruges i morgen.</div>`
        : "";
    return `
      <div class="chips">${chips}</div>
      <div class="card recipe">
        <div class="row between wrap">
          <h1>${esc(day.dish || "Ingen ret")}</h1>
          ${this._rateButtons(plan, day)}
          <button class="btn ${this._wake ? "primary" : ""}" data-action="wake">
            ${this._wake ? "☀ Skærmen holdes tændt" : "☀ Hold skærmen tændt"}
          </button>
        </div>
        <p class="muted">${esc(dateLabel(day.date))}${day.servings ? ` · ${day.servings} personer` : ""}${day.active_minutes ? ` · ${day.active_minutes} min aktiv` : ""}${day.total_minutes ? ` · ${day.total_minutes} min i alt` : ""}${type ? ` · ${esc(type)}` : ""}</p>
        ${leftovers}
        ${day.nutrition
          ? `<p class="nutri">Pr. voksenportion: <b>${Math.round(day.nutrition.kcal)} kcal</b>${["protein_g", "carbs_g", "fat_g"]
              .filter((k) => day.nutrition[k] != null)
              .map((k) => ` · ${Math.round(day.nutrition[k])} g ${{ protein_g: "protein", carbs_g: "kulhydrat", fat_g: "fedt" }[k]}`)
              .join("")}</p>`
          : ""}
        ${day.recipe_error || (!day.steps.length && !day.uses_leftovers_from && day.type !== "rester" && day.type !== "tom")
          ? `<div class="banner warn">Opskriften kunne ikke laves${day.recipe_error ? `: ${esc(day.recipe_error)}` : ""}
             <button class="btn small" data-action="recipe" ${this._busy ? "disabled" : ""}>${aiLabel("Prøv igen")}</button></div>`
          : ""}
        <div class="recipe-grid">
          <section>
            <h2>Ingredienser</h2>
            <ul class="ingredients">${ingredients || "<li>Ingen</li>"}</ul>
          </section>
          <section>
            <h2>Sådan gør du</h2>
            <ol class="steps">${steps || "<li>Ingen trin</li>"}</ol>
            ${day.tip ? `<p class="tip">💡 ${esc(day.tip)}</p>` : ""}
            <p class="row wrap">${day.mealie ? "" : `<button class="btn small" data-action="recipe" ${this._busy ? "disabled" : ""}>${aiLabel("Lav opskriften igen")}</button>`}
              ${this._mealieButton(plan.id, day.date)}</p>
            ${day.mealie ? '<p class="muted small">Opskriften er jeres egen fra Mealie.</p>' : ""}
          </section>
        </div>
      </div>`;
  }

  _shoppingView() {
    const plan = this._plan;
    const rema = this._state.rema_list;
    let planHtml = `<div class="card">Der er ingen madplan endnu.</div>`;
    if (plan) {
      const groups = {};
      const compare = this._ensureCompare();
      const lateLines = plan.shopping.filter((line) => line.buy_from && !line.buy_at);
      plan.shopping
        .filter((line) => !line.buy_from && !line.buy_at)
        .forEach((line) => (groups[line.category || "Andet"] ||= []).push(line));
      const row = (line) => {
              // An offer only sold in the shops (partivare) has the avis's name and price.
              const p = line.product || line.avis_item;
              const badges = [
                p?.is_advertised || p?.is_campaign ? '<span class="badge offer">Tilbud</span>' : "",
                p?.is_organic ? '<span class="badge eco">Øko</span>' : "",
                line.must_have ? '<span class="badge">Fast vare</span>' : "",
                line.buy_from ? `<span class="badge from">Købes ${esc(dayShort(line.buy_from))}</span>` : "",
                line.price_source === "avis" ? '<span class="badge">Avispris</span>' : "",
              ].join("");
              const need = line.amount && line.unit && line.unit !== "pk" ? `${line.amount} ${line.unit}` : "";
              return `<li class="line tappable" data-action="line-menu" data-arg="${esc(line.id || "")}">
                ${p?.image ? `<img src="${esc(p.image)}" alt="" loading="lazy">` : '<span class="noimg">?</span>'}
                <div class="what">
                  <span class="title"><b>${esc(p ? p.name : line.name)}</b> ${badges}</span>
                  <span class="muted">${esc(p?.underline || "Tilføjes som fritekst")}${need ? ` · behov ${esc(need)}` : ""}</span>
                  ${line.offer_name ? `<span class="muted">Avisvare: ${esc(line.offer_name)}</span>` : ""}
                  ${line.note ? `<span class="note">${esc(line.note)}</span>` : ""}
                  ${compare?.lines?.[line.id]
                    ? `<button class="cheaper" data-action="chain-move" data-arg="${esc(line.id)}|${esc(compare.lines[line.id].dealer_id)}"
                        title="Flyt til ${esc(this._chainName(compare.lines[line.id].dealer_id))}-listen">${this._chainLogo(compare.lines[line.id].dealer_id, "tiny")}
                        <span>${esc(compare.lines[line.id].heading)}: spar ${kr(compare.lines[line.id].saving)}</span></button>`
                    : ""}
                </div>
                <div class="cost">${p && p.price != null ? `${line.packages} × ${kr(p.price)}<b>${kr(line.cost)}</b>` : line.packages > 1 ? `${line.packages} stk.` : "–"}</div>
              </li>`;
      };
      const sections = Object.entries(groups)
        .map(([category, lines]) => `<h2>${esc(category)}</h2><ul class="lines">${lines.map(row).join("")}</ul>`)
        .join("");
      const lateDay = lateLines[0]?.buy_from;
      const lateTotal = lateLines.reduce((sum, line) => sum + (line.cost || 0), 0);
      const lateHtml = lateLines.length
        ? `<div class="card">
            <div class="row between wrap">
              <div><h1>Indkøb ${esc(lateDay ? dayShort(lateDay) : "senere")}</h1>
              <p class="muted">Tilbud, der først gælder fra ${esc(lateDay ? dayShort(lateDay) : "senere på ugen")}. Send dem til REMA-listen, når I skal handle.</p></div>
              <div class="price"><span class="big">${kr(lateTotal)}</span></div>
            </div>
            <ul class="lines">${lateLines.map(row).join("")}</ul>
            ${this._shopSearchHtml("late")}
            <div class="row wrap actions">
              <button class="btn primary" data-action="send" data-arg="late" ${this._busy ? "disabled" : ""}>
                ${plan.late_sent_at ? "Sendt ✓ – send igen" : `Send ${esc(lateDay ? dayName(lateDay) : "")}svarer til REMA-listen`}</button>
            </div>
          </div>`
        : "";
      planHtml = `<div class="card">
        <div class="row between wrap">
          <div><h1>${lateLines.length ? "Indkøb på indkøbsdagen" : "Indkøbsliste"}</h1><p class="muted">${esc(plan.title)}${lateLines.length ? ` · plus ${lateLines.length} varer ${esc(dayShort(lateDay))}` : ""}</p></div>
          <div class="price ${plan.budget && plan.total > plan.budget ? "over" : ""}"><span class="big">${kr(plan.total)}</span>
          <span class="muted">${plan.budget ? `budget ${kr(plan.budget)}` : ""}</span></div>
        </div>
        <p class="muted small">Tryk på en vare for at rette antal, skifte den ud eller slette den.</p>
        ${Object.entries(compare?.chains || {})
          .map(
            ([id, t]) => `<div class="banner info chain-save">${this._chainLogo(id)}
              <span><b>${t.count} ${t.count === 1 ? "vare er" : "varer er"} billigere i ${esc(this._chainName(id))}</b> – spar ${kr(t.saving)} Tryk på logoet ved en vare for at købe den der.</span>
              <button class="btn small" data-action="chain-move-all" data-arg="${esc(id)}" ${this._busy ? "disabled" : ""}>Lav ${esc(this._chainName(id))}-liste</button></div>`
          )
          .join("")}
        ${compare?.loading ? '<p class="muted small"><span class="spinner small"></span> Sammenligner med de andre butikkers tilbud …</p>' : ""}
        ${sections}
        ${this._shopSearchHtml("main")}
        <div class="row wrap actions">
          <button class="btn primary" data-action="send" ${this._busy ? "disabled" : ""}>
            ${plan.status === "sent" ? "Sendt ✓ – send igen" : "Send til REMA-listen"}</button>
          <button class="btn" data-action="pantry-open">Basisvarer i madplanen</button>
          <button class="btn" data-action="plan-refresh" ${this._busy ? "disabled" : ""}>Opdatér tilbudsvarer</button>
        </div>
      </div>${lateHtml}${this._chainListsHtml(plan)}`;
    }
    const remaItems = rema?.items?.length
      ? rema.items
          .map((i) => `<li class="${i.bought ? "bought" : ""}">${i.amount > 1 ? `${i.amount} × ` : ""}${esc(i.name)}</li>`)
          .join("")
      : "<li class='muted'>Listen er tom.</li>";
    return `${planHtml}
      <div class="card">
        <div class="row between wrap">
          <h2>På REMA-listen lige nu${rema ? ` (${esc(rema.name)})` : ""}</h2>
          <button class="btn small danger" data-action="clear-list" ${this._busy || !rema?.items?.length ? "disabled" : ""}>Tøm kurv</button>
        </div>
        <ul class="rema">${remaItems}</ul>
        ${rema ? `<p class="muted">Anslået pris for det, der mangler: ${kr(rema.total)}</p>` : ""}
      </div>`;
  }

  _productCard(p) {
    const sale = onOffer(p);
    const until = validTo(p.price_valid_to);
    return `<div class="prod">
      ${p.image ? `<img src="${esc(p.image)}" alt="" loading="lazy">` : '<span class="noimg">?</span>'}
      <div class="prod-body">
        <b>${esc(p.name)}</b>
        <span class="muted small">${esc(p.underline || "")}</span>
        <span class="prod-price">
          <b class="${sale ? "sale" : ""}">${kr(p.price)}</b>
          ${sale && p.normal_price && p.normal_price > p.price ? `<s class="muted">${kr(p.normal_price)}</s>` : ""}
        </span>
        <span>${p.is_advertised ? '<span class="badge offer">Avisvare</span>' : sale ? '<span class="badge offer">Tilbud</span>' : ""}
          ${p.is_organic ? '<span class="badge eco">Øko</span>' : ""}
          ${p.offer_from
            ? `<span class="badge from">fra ${esc(dayShort(p.offer_from))}</span>`
            : sale && until ? `<span class="muted small">til ${esc(until)}</span>` : ""}</span>
        ${p.avis ? `<span class="muted small avis">Avis: ${esc(p.avis)}${p.avis_quantity ? ` · ${esc(p.avis_quantity)}` : ""}</span>` : ""}
        ${this._favCheaper(p)}
      </div>
      <button class="btn small primary" data-action="fav-add" data-arg="${esc(p.id)}" ${this._busy ? "disabled" : ""}>+ Tilføj</button>
    </div>`;
  }

  _favRows() {
    const filter = this._favFilter.trim().toLowerCase();
    const rows = (this._favCache[this._favWeek]?.products || [])
      .filter((p) => !filter || `${p.name} ${p.underline || ""}`.toLowerCase().includes(filter))
      .map(
        (p) => `<li class="fav-row">
          <div class="what"><b>${esc(p.name)}</b><span class="muted small">${esc(p.underline || "")}</span>${this._favCheaper(p)}</div>
          <span class="${onOffer(p) ? "sale" : ""}">${kr(p.price)}</span>
          <button class="btn small" data-action="fav-add" data-arg="${esc(p.id)}">+ Tilføj</button>
        </li>`
      )
      .join("");
    return rows || "<li class='muted'>Ingen favoritter matcher.</li>";
  }

  _favoritesView() {
    const week = this._favWeek;
    const data = this._favCache[week];
    const seg = `<div class="seg" role="tablist">${[["current", "Denne uge"], ["next", "Næste uge"]]
      .map(([key, label]) => `<button role="tab" aria-selected="${key === week}" class="${key === week ? "active" : ""}" data-action="fav-week" data-arg="${key}">${label}</button>`)
      .join("")}</div>`;
    let body;
    if (this._favsLoading && !data) {
      body = `<p class="center muted"><span class="spinner"></span> Tjekker dine favoritter mod tilbudsavisen …</p>`;
    } else if (this._favsError && !data) {
      body = `<h2>Favoritterne kunne ikke hentes</h2><p>${esc(this._favsError)}</p>
        <button class="btn" data-action="fav-refresh">Prøv igen</button>`;
    } else {
      const offers = data?.on_offer || [];
      const cat = data?.catalog;
      const next = week === "next" && !data?.fallback;
      const from = next && cat?.valid_from ? ` fra ${esc(shortDate(localDay(cat.valid_from)))}` : "";
      body = `
        ${data?.fallback ? '<div class="banner info">Næste uges avis er ikke udkommet endnu – her er denne uges tilbud indtil da.</div>' : ""}
        <h2>${next ? `På tilbud${from}` : "På tilbud nu"} (${offers.length})</h2>
        ${offers.length
          ? `<div class="prod-grid">${offers.map((p) => this._productCard(p)).join("")}</div>`
          : `<p class="muted">Ingen af dine favoritter er på tilbud ${next ? "i næste uge" : "lige nu"}.</p>`}`;
    }
    const count = data?.products?.length;
    return `
      <div class="card">
        <div class="row between wrap">
          <div><h1>Dine favoritter</h1>
          <p class="muted">Varer du har markeret med hjerte i REMA 1000-appen${count != null ? ` – ${count} i alt` : ""}.</p></div>
          <button class="btn small" data-action="fav-refresh" ${this._favsLoading ? "disabled" : ""}>
            ${this._favsLoading ? '<span class="spinner small"></span>' : "Opdatér"}</button>
        </div>
        ${seg}
        ${body}
      </div>
      <div class="card">
        <details>
          <summary>Alle favoritter (${count ?? 0})</summary>
          <input class="grow filter" type="search" data-bind="favfilter" value="${esc(this._favFilter)}" placeholder="Filtrér, fx mælk">
          <ul class="favlist" id="fav-all">${this._favRows()}</ul>
        </details>
      </div>`;
  }

  _historyView() {
    const plans = this._state.plans;
    if (!plans.length) return `<div class="card">Der er ingen tidligere madplaner.</div>`;
    const rows = plans
      .map(
        (p) => `<li class="hist">
          <div class="what" data-action="view-plan" data-arg="${esc(p.id)}">
            <b>${esc(p.title)}</b>
            <span class="muted">${esc(dateLabel(p.start_date))} – ${esc(dateLabel(p.end_date))} · ${kr(p.total)}</span>
            <span class="muted small">${esc(p.dishes.join(" · "))}</span>
          </div>
          <span class="badge ${p.status}">${esc(STATUS_LABELS[p.status] || p.status)}</span>
          <button class="btn small" data-action="view-plan" data-arg="${esc(p.id)}">Vis</button>
          <button class="btn small danger" data-action="delete-plan" data-arg="${esc(p.id)}">Slet</button>
        </li>`
      )
      .join("");
    return `<div class="card"><h1>Historik</h1><ul class="history">${rows}</ul></div>`;
  }

  _settingsView() {
    const f = this._form;
    const opts = this._state.options;
    const check = (list, key, labels) =>
      `<label class="check"><input type="checkbox" data-list="${list}" value="${key}" ${f[list].includes(key) ? "checked" : ""}> ${esc(labels[key] || key)}</label>`;
    const weekdaySelect = (path, value) =>
      `<select data-path="${path}" data-type="number">${WEEKDAYS.map((d, i) => `<option value="${i}" ${Number(value) === i ? "selected" : ""}>${d}</option>`).join("")}</select>`;
    const num = (path, value, min = 0, max = 999) =>
      `<input type="number" data-path="${path}" data-type="number" min="${min}" max="${max}" value="${esc(value)}">`;
    const ai = this._state.ai_entities
      .map((e) => `<option value="${esc(e.entity_id)}" ${f.ai_task_entity === e.entity_id ? "selected" : ""}>${esc(e.name)}</option>`)
      .join("");
    const household = f.household
      .map(
        (m, i) => `<div class="row wrap rowitem">
          <select data-path="household.${i}.role">
            <option value="adult" ${m.role === "adult" ? "selected" : ""}>Voksen</option>
            <option value="child" ${m.role === "child" ? "selected" : ""}>Barn</option>
          </select>
          <label class="field inline">Alder ${num(`household.${i}.age`, m.age, 0, 120)}</label>
          <select data-path="household.${i}.sex">
            <option value="female" ${m.sex === "female" ? "selected" : ""}>Pige/kvinde</option>
            <option value="male" ${m.sex === "male" ? "selected" : ""}>Dreng/mand</option>
            <option value="other" ${m.sex === "other" ? "selected" : ""}>Andet</option>
          </select>
          <button class="btn small danger" data-action="remove-row" data-arg="household|${i}">Fjern</button>
        </div>`
      )
      .join("");
    const fixed = f.fixed_days
      .map(
        (d, i) => `<div class="row wrap rowitem">
          ${weekdaySelect(`fixed_days.${i}.weekday`, d.weekday)}
          <input class="grow" type="text" data-path="fixed_days.${i}.text" value="${esc(d.text)}" placeholder="Fx Rugbrødsdag">
          <button class="btn small danger" data-action="remove-row" data-arg="fixed_days|${i}">Fjern</button>
        </div>`
      )
      .join("");
    const musts = f.must_haves
      .map(
        (m, i) => `<div class="row wrap rowitem">
          <input class="grow" type="text" data-path="must_haves.${i}.name" value="${esc(m.name)}" placeholder="Vare">
          <label class="field inline">Antal pr. uge ${num(`must_haves.${i}.amount`, m.amount, 1, 99)}</label>
          ${m.product_id ? '<span class="badge">REMA-vare</span>' : ""}
          <button class="btn small danger" data-action="remove-row" data-arg="must_haves|${i}">Fjern</button>
        </div>`
      )
      .join("");
    const results = this._search.loading
      ? '<p class="muted"><span class="spinner small"></span> Søger …</p>'
      : this._search.results
          .map(
            (p, i) => `<button class="result" data-action="pick-product" data-arg="${i}">
              ${p.image ? `<img src="${esc(p.image)}" alt="">` : ""}
              <span><b>${esc(p.name)}</b><span class="muted">${esc(p.underline || "")} · ${kr(p.price)}</span></span>
              ${p.is_organic ? '<span class="badge eco">Øko</span>' : ""}</button>`
          )
          .join("");
    const dislikes = (this._state.settings.disliked_dishes || [])
      .map(
        (text, i) => `<li class="fav"><div class="what"><span>${esc(text)}</span></div>
          <button class="btn small danger" data-action="delete-dislike" data-arg="${i}">Slet</button></li>`
      )
      .join("");
    const favs = this._state.favorites
      .map((fav) =>
        this._editFav?.id === fav.id
          ? `<li class="fav edit">
              <textarea data-bind="editfav" data-field="text" rows="2">${esc(this._editFav.text)}</textarea>
              <div class="row wrap">
                <select data-bind="editfav" data-field="frequency">${opts.frequencies.map((q) => `<option value="${q}" ${this._editFav.frequency === q ? "selected" : ""}>${FREQ_LABELS[q]}</option>`).join("")}</select>
                <button class="btn small primary" data-action="save-fav">Gem</button>
                <button class="btn small" data-action="cancel-fav">Annullér</button>
              </div></li>`
          : `<li class="fav"><div class="what"><span>${esc(fav.text)}</span>
              <span class="muted small">${esc(FREQ_LABELS[fav.frequency] || fav.frequency)}${fav.last_used ? ` · sidst ${esc(shortDate(fav.last_used))}` : ""}</span></div>
              <button class="btn small" data-action="edit-fav" data-arg="${esc(fav.id)}">Ret</button>
              <button class="btn small danger" data-action="delete-fav" data-arg="${esc(fav.id)}">Slet</button></li>`
      )
      .join("");

    const card = (html) => `<div class="card">${html}</div>`;
    const sections = SETTINGS_SECTIONS(this);
    const open = sections.find((sec) => sec.key === this._settingsSection);
    const savebar = `<div class="savebar">
        <button class="btn primary" data-action="save-settings" ${this._busy ? "disabled" : ""}>Gem indstillinger</button>
        <button class="btn" data-action="reset-settings">Fortryd ændringer</button>
        ${this._dirty ? '<span class="muted">Ikke gemt</span>' : ""}
      </div>`;
    const html = {
      plan: () => card(`        <h2 class="flush">AI</h2>
        <label class="field">AI-opgave-entitet
          <select data-path="ai_task_entity" data-type="nullable">
            <option value="">Home Assistants standard</option>${ai}
          </select></label>
        `) + card(`        <h2 class="flush">Uge og budget</h2>
        <div class="grid">
          <label class="field">Madplanen starter / der handles ind ${weekdaySelect("start_weekday", f.start_weekday)}</label>
          <label class="field">Antal dage ${num("days", f.days, 1, 14)}</label>
          <label class="field">Budget for hele listen (kr.) ${num("budget", f.budget, 0, 100000)}</label>
        </div>
        <label class="check"><input type="checkbox" data-path="shop_late_week" ${f.shop_late_week ? "checked" : ""}> Vi handler også sidst på ugen</label>
        <p class="muted small">Så må madplanen bruge tilbud, der først gælder fra torsdag, i retterne fra den dag. Varerne mærkes med, hvornår de skal købes. Ellers bruges kun tilbud, der gælder på indkøbsdagen.</p>
        `) + card(`        <h2 class="flush">Automatik</h2>
        <label class="check"><input type="checkbox" data-path="auto_generate" ${f.auto_generate ? "checked" : ""}> Lav næste uges madplan automatisk, når den nye tilbudsavis udkommer</label>
        <label class="check"><input type="checkbox" data-path="auto_send" ${f.auto_send ? "checked" : ""}> Send den automatisk til REMA-listen</label>
        `),
      family: () => card(`        <h2 class="flush">Familien</h2>
        ${household}
        <button class="btn small" data-action="add-row" data-arg="household">+ Tilføj person</button>
        `) + card(`        <h2 class="flush">Undgå</h2>
        <div class="checks">${opts.avoid.map((k) => check("avoid", k, AVOID_LABELS)).join("")}</div>
        <label class="field">Andet at undgå <input type="text" data-path="avoid_other" value="${esc(f.avoid_other)}" placeholder="Fx svampe, oliven"></label>
        `) + card(`        <h2 class="flush">Allergier</h2>
        <div class="checks">${opts.allergies.map((k) => check("allergies", k, ALLERGY_LABELS)).join("")}</div>
        <label class="field">Andre allergier <input type="text" data-path="allergies_other" value="${esc(f.allergies_other)}"></label>
        `),
      dishes: () => card(`        <h2 class="flush">Retter</h2>
        <div class="grid">
          <label class="field">Mindst vegetarretter ${num("min_vegetarian", f.min_vegetarian, 0, 14)}</label>
          <label class="field">Højst vegetarretter ${num("max_vegetarian", f.max_vegetarian, 0, 14)}</label>
          <label class="field">Restedage (laves dagen før) ${num("leftover_days", f.leftover_days, 0, 7)}</label>
          <label class="field">Maks. minutter på hverdage ${num("max_cook_minutes_weekday", f.max_cook_minutes_weekday, 5, 300)}</label>
          <label class="field">Ingen gentagelse i antal uger ${num("no_repeat_weeks", f.no_repeat_weeks, 0, 52)}</label>
        </div>
        <h3>Faste dage</h3>
        ${fixed}
        <button class="btn small" data-action="add-row" data-arg="fixed_days">+ Tilføj fast dag</button>
        <label class="field">Ønsker til maden <textarea data-path="wishes" rows="2">${esc(f.wishes)}</textarea></label>
        <label class="field">Basisvarer I altid har (købes ikke) <textarea data-path="pantry" rows="2">${esc(f.pantry)}</textarea></label>
        `) + card(`        <h2 class="flush">Familiens favoritter</h2>
        <p class="muted">Beskriv retten, fx “Ovnbagt laks med citronskiver, frisk spinatpasta med pesto og broccoli”.</p>
        <textarea data-bind="newfav" data-field="text" rows="2" placeholder="Ret">${esc(this._newFav.text)}</textarea>
        <div class="row wrap">
          <select data-bind="newfav" data-field="frequency">${opts.frequencies.map((q) => `<option value="${q}" ${this._newFav.frequency === q ? "selected" : ""}>${FREQ_LABELS[q]}</option>`).join("")}</select>
          <button class="btn primary small" data-action="add-fav">Tilføj</button>
        </div>
        <ul class="favs">${favs || "<li class='muted'>Ingen favoritter endnu.</li>"}</ul>
        `) + card(`        <h2 class="flush">Retter familien ikke kan lide</h2>
        <p class="muted">Retter, der aldrig skal på madplanen, fx “Fiskefrikadeller” eller “Gryderetter med kål”.</p>
        <textarea data-bind="newdislike" rows="2" placeholder="Ret">${esc(this._newDislike)}</textarea>
        <div class="row wrap">
          <button class="btn primary small" data-action="add-dislike" ${this._busy ? "disabled" : ""}>Tilføj</button>
        </div>
        <ul class="favs">${dislikes || "<li class='muted'>Ingen endnu.</li>"}</ul>
        `),
      shopping: () => card(`        <h2 class="flush">Økologi</h2>
        <div class="row wrap">
          ${[["only", "Udelukkende økologi"], ["prefer", "Foretræk økologi"], ["none", "Ligeglad (prisbevidst)"]]
            .map(([v, l]) => `<label class="check"><input type="radio" name="organic" data-path="organic" value="${v}" ${f.organic === v ? "checked" : ""}> ${l}</label>`)
            .join("")}
        </div>
        ${f.organic === "prefer" ? `<label class="field inline">Højst så mange % dyrere end den billigste ${num("organic_max_extra_pct", f.organic_max_extra_pct, 0, 500)}</label>` : ""}

        <h2>Krav til varer</h2>
        <p class="muted small">Gælder uanset pris. Findes der ingen vare, der opfylder kravet, vælges den billigste med en note.</p>
        <div class="grid">
          <label class="field">Æg
            <select data-path="egg_min">${Object.entries(EGG_LABELS)
              .map(([v, l]) => `<option value="${v}" ${f.egg_min === v ? "selected" : ""}>${l}</option>`)
              .join("")}</select></label>
        </div>
        <label class="check"><input type="checkbox" data-path="milk_organic" ${f.milk_organic ? "checked" : ""}> Mælk skal være økologisk</label>
        <label class="check"><input type="checkbox" data-path="produce_organic" ${f.produce_organic ? "checked" : ""}> Frugt og grønt skal være økologisk</label>
        `) + card(`        <h2 class="flush">Faste varer hver uge</h2>
        ${musts}
        <div class="row wrap">
          <input class="grow" type="search" data-bind="search" value="${esc(this._search.query)}" placeholder="Søg i REMA 1000, fx letmælk">
          <button class="btn small" data-action="search">Søg</button>
          <button class="btn small" data-action="add-row" data-arg="must_haves">+ Fritekst</button>
        </div>
        <div class="results">${results}</div>
        `),
      rules: () => card(`        <h2 class="flush">Det skal AI'en huske</h2>
        <p class="muted">Faste ønsker, der bruges i alle madplaner, opskrifter og forslag – fx “Vi vil altid have frisk broccoli og fettuccine med spinat til laksefilet”. Skriv eller diktér; hvert punkt kan rettes og slettes.</p>
        ${this._rulesHtml()}
        `),
      nutrition: () => card(`        <h2 class="flush">Næring pr. aftensmad</h2>
        <p class="muted">Mål for en voksens portion. AI'en rammer det så tæt som muligt, og under Sundhed kan du se, hvordan madplanen ligger.</p>
        <label class="check"><input type="checkbox" data-path="nutrition_enabled" ${f.nutrition_enabled ? "checked" : ""}> Brug målene, når madplanen laves</label>
        <div class="grid">
          <label class="field inline">Protein ${num("protein_pct", f.protein_pct, 0, 100)} %</label>
          <label class="field inline">Kulhydrat ${num("carb_pct", f.carb_pct, 0, 100)} %</label>
          <label class="field inline">Fedt ${num("fat_pct", f.fat_pct, 0, 100)} %</label>
        </div>
        ${Number(f.protein_pct) + Number(f.carb_pct) + Number(f.fat_pct) !== 100
          ? `<p class="note">Procenterne giver ${Number(f.protein_pct) + Number(f.carb_pct) + Number(f.fat_pct)} % – de bør give 100 %.</p>`
          : ""}
        <div class="grid">
          <label class="field inline">Fra ${num("kcal_min", f.kcal_min, 100, 3000)} kcal</label>
          <label class="field inline">til ${num("kcal_max", f.kcal_max, 100, 3000)} kcal</label>
        </div>
        <p class="muted small">Fx 40 % protein, 35 % kulhydrat og 25 % fedt og 800–900 kcal. De officielle anbefalinger for voksne er ca. 10–20 % protein, 45–60 % kulhydrat og 25–40 % fedt af energien.</p>
        `),
      chains: () => card(`<h2 class="flush">Andre butikker</h2>
        <h3>Madplanen</h3>
        <p class="muted">AI'en laver madplanen ud fra tilbuddene i disse butikker, og hver vare kommer på listen til den butik, den købes i. Rækkefølgen er jeres foretrukne butikker: er en vare på tilbud flere steder til næsten samme pris, vælges den øverste, og varer, der ikke er på tilbud, kommer på listen til den øverste (med REMA 1000's pris som anslået pris). REMA 1000 er altid med.</p>
        <ol class="plan-chains">${(f.plan_chains || [REMA_ID])
          .map((id, i, all) => `<li>${this._chainLogo(id)}<span class="grow">${esc(this._chainName(id))}</span>
            <button class="icon-btn" data-action="plan-chain-move" data-arg="${i}|-1" ${i === 0 ? "disabled" : ""} aria-label="Op">▲</button>
            <button class="icon-btn" data-action="plan-chain-move" data-arg="${i}|1" ${i === all.length - 1 ? "disabled" : ""} aria-label="Ned">▼</button>
            ${id === REMA_ID ? '<span class="icon-btn" aria-hidden="true"></span>' : `<button class="icon-btn" data-action="plan-chain-remove" data-arg="${i}" aria-label="Fjern">${CLOSE_ICON}</button>`}</li>`)
          .join("")}</ol>
        ${this._chains
          ? `<div class="row wrap">${this._chains
              .filter((c) => c.id !== REMA_ID && !(f.plan_chains || []).includes(c.id))
              .map((c) => `<button class="btn" data-action="plan-chain-add" data-arg="${esc(c.id)}">+ ${esc(c.name)}</button>`)
              .join("")}</div>`
          : ""}
        <h3>Sammenlign priser</h3>
        <p class="muted">Vælg de kæder, I også handler i. Deres madtilbud vises på forsiden, og i indkøbslisten og favoritterne står der, når en vare er billigere hos dem denne uge.</p>
        ${this._chains
          ? `<div class="chain-pick">${this._chains
              .map((c) => `<label class="chain-choice"><input type="checkbox" data-list="chains" value="${esc(c.id)}" ${f.chains.includes(c.id) ? "checked" : ""}>${this._chainLogo(c.id)}<span>${esc(c.name)}</span></label>`)
              .join("")}</div>`
          : '<p class="muted"><span class="spinner small"></span> Henter kæderne …</p>'}
        <p class="muted small">Tilbuddene kommer fra kædernes tilbudsaviser (Tjek/eTilbudsavis). En vare tæller kun som billigere, når det er den samme slags vare i samme størrelse.</p>`),
      mealie: () => card(`        <h2 class="flush">Mealie</h2>
        ${this._state.mealie?.available
          ? `<p class="muted">Bruger Mealie-integrationen i Home Assistant${this._state.mealie.url ? ` (${esc(this._state.mealie.url)})` : ""}.</p>
            <label class="check"><input type="checkbox" data-path="mealie_recipes" ${f.mealie_recipes ? "checked" : ""}> Tag udgangspunkt i vores opskrifter i Mealie – AI'en finder selv på, når ingen passer</label>
            <label class="check"><input type="checkbox" data-path="mealie_calendar" ${f.mealie_calendar ? "checked" : ""}> Sæt madplanen i Mealie-kalenderen (og ret den, når madplanen ændres)</label>
            <p class="muted small">Madplanens egne opskrifter kan gemmes i Mealie med "Gem i Mealie" på retten.</p>`
          : `<p class="muted">Har I jeres opskrifter i <a href="https://mealie.io" target="_blank" rel="noopener">Mealie</a>, så sæt Mealie-integrationen op i Home Assistant (Indstillinger › Enheder og tjenester). Så kan madplanen tage udgangspunkt i jeres opskrifter, gemme sine egne i Mealie og fylde Mealie-kalenderen.</p>`}
        `),
      app: () => card(`        <h2 class="flush">App på hjemmeskærmen</h2>
        <p class="muted">Åbn linket i Safari (eller Chrome), log ind og vælg Del › Føj til hjemmeskærm. Så åbner Middagsro i fuld skærm i dit tema.</p>
        <p><a href="${esc(`${location.origin}/middagsro_app/app.html`)}" target="_blank" rel="noopener">${esc(`${location.origin}/middagsro_app/app.html`)}</a></p>
        `),
    };
    if (open) {
      return `
        <div class="settings-head">
          <button class="btn back" data-action="settings-section" data-arg="">‹ Indstillinger</button>
          <h1>${esc(open.title)}</h1>
        </div>
        ${html[open.key]()}
        ${open.form ? savebar : ""}`;
    }
    const rows = sections
      .map(
        (sec) => `<button class="setting-row" data-action="settings-section" data-arg="${sec.key}">
          <span class="setting-icon">${sec.icon}</span>
          <span class="setting-text"><b>${esc(sec.title)}</b><span class="muted small">${esc(sec.summary)}</span></span>
          <span class="chev" aria-hidden="true">›</span>
        </button>`
      )
      .join("");
    return `
      <div class="card">
        <h1>Indstillinger</h1>
        <p class="muted">Bruges hver gang en madplan laves.</p>
        <div class="setting-rows">${rows}</div>
      </div>
      ${this._dirty ? savebar : ""}`;
  }
}

const STYLE = `
  /* No double-tap zoom; 16 px inputs so a phone doesn't zoom in on them. */
  :host, button, input, select, textarea, .day, .line { touch-action: manipulation; }
  :host { display: block; min-height: 100vh; overflow-x: clip; background: var(--primary-background-color); color: var(--primary-text-color);
    font-family: var(--ha-font-family-body, Roboto, sans-serif);
    /* Everything follows the Home Assistant theme; only the logo keeps REMA's colours. */
    --rema-accent: var(--primary-color);
    --rema-on-accent: var(--text-primary-color, #fff);
    --rema-sale: var(--error-color, #db4437);
    --rema-on-sale: var(--text-primary-color, #fff);
    --rema-ok: var(--success-color, #43a047);
    --rema-warn: var(--warning-color, #ffa600);
    --rema-card: var(--ha-card-background, var(--card-background-color));
    --rema-subtle: var(--secondary-background-color);
    --rema-tint: color-mix(in srgb, var(--rema-accent) 12%, transparent);
    /* Bars that stay on screen while content scrolls under them: the card colour on the
       page background, so see-through (glass) themes don't show text behind them. */
    --rema-solid-card: linear-gradient(var(--card-background-color), var(--card-background-color)) var(--primary-background-color); }
  * { box-sizing: border-box; }
  a { color: var(--rema-accent); overflow-wrap: anywhere; }
  .skiphead { margin: 14px 0 6px; }
  .skipdays { display: grid; grid-template-columns: repeat(auto-fill, minmax(130px, 1fr)); gap: 2px 12px; }
  .skipgo { margin-top: 12px; }
  #content.from-right { animation: rema-from-right .2s ease-out; }
  #content.from-left { animation: rema-from-left .2s ease-out; }
  @keyframes rema-from-right { from { transform: translateX(32px); opacity: .4; } }
  @keyframes rema-from-left { from { transform: translateX(-32px); opacity: .4; } }
  @media (prefers-reduced-motion: reduce) { #content.from-right, #content.from-left { animation: none; } }
  /* --rema-safe-top/-bottom are only set by the home-screen app (behind the status bar and home bar). */
  .toolbar { display: flex; align-items: center; gap: 8px; height: calc(var(--header-height, 56px) + var(--rema-safe-top, 0px));
    padding: var(--rema-safe-top, 0px) 12px 0;
    background: var(--app-header-background-color, var(--card-background-color)); color: var(--app-header-text-color, inherit);
    border-bottom: 1px solid var(--divider-color); position: sticky; top: 0; z-index: 3; }
  .brand { display: inline-flex; align-items: center; gap: 10px; }
  .logo { height: min(36px, calc(var(--header-height, 56px) - 16px)); border-radius: 9px; }
  .wordmark { font-family: "Inter Display", Inter, var(--ha-font-family-body, system-ui), sans-serif; font-weight: 650; font-size: 22px;
    letter-spacing: -.025em; color: var(--app-header-text-color, var(--primary-text-color)); }
  .spacer { flex: 1; }
  .tabs { display: flex; gap: 4px; overflow-x: auto; padding: 8px 12px 0; background: var(--rema-solid-card);
    border-bottom: 1px solid var(--divider-color); position: sticky; top: calc(var(--header-height, 56px) + var(--rema-safe-top, 0px)); z-index: 2; }
  .tab { border: none; background: none; color: var(--secondary-text-color); padding: 10px 14px; font-size: 15px; cursor: pointer;
    border-bottom: 3px solid transparent; white-space: nowrap; font-weight: 500; }
  .tab.active { color: var(--rema-accent); border-color: var(--rema-accent); }
  .tab.more { display: none; }
  .more-scrim, .more-sheet { display: none; }
  .credit { margin: 24px 0 0; text-align: center; font-size: 13px; color: var(--secondary-text-color); }
  .credit .gh-link { display: inline-flex; vertical-align: -3px; margin-left: 4px; padding: 2px; color: inherit; border-radius: 999px; }
  .credit .gh { width: 16px; height: 16px; display: block; }
  .tab svg { display: none; width: 22px; height: 22px; fill: none; stroke: currentColor; stroke-width: 1.8;
    stroke-linecap: round; stroke-linejoin: round; }
  main { max-width: 1100px; margin: 0 auto; padding: 16px 12px calc(96px + var(--rema-safe-bottom, env(safe-area-inset-bottom, 0px))); }
  .card { background: var(--rema-card); border-radius: var(--ha-card-border-radius, 12px);
    box-shadow: var(--ha-card-box-shadow, 0 1px 3px rgba(0,0,0,.12)); border: 1px solid var(--divider-color);
    padding: 16px 18px; margin-bottom: 16px; }
  .center { text-align: center; }
  h1 { font-size: 22px; margin: 0 0 4px; } h2 { font-size: 17px; margin: 22px 0 8px; } h3 { font-size: 15px; margin: 14px 0 6px; }
  p { line-height: 1.5; }
  .muted { color: var(--secondary-text-color); } .small { font-size: 13px; }
  .row { display: flex; align-items: center; gap: 10px; } .wrap { flex-wrap: wrap; } .between { justify-content: space-between; }
  .grow { flex: 1; min-width: 160px; }
  .actions { margin-top: 16px; }
  .btn { border: 1px solid var(--divider-color); background: var(--rema-card); color: var(--primary-text-color);
    border-radius: 999px; padding: 9px 16px; font-size: 14px; font-weight: 500; cursor: pointer; }
  .btn.primary { background: var(--rema-accent); color: var(--rema-on-accent); border-color: var(--rema-accent); }
  .btn.danger { color: var(--rema-sale); }
  .btn.small { padding: 5px 12px; font-size: 13px; }
  .btn:disabled { opacity: .5; cursor: default; }
  .ai { width: 1.1em; height: 1.1em; fill: currentColor; vertical-align: -.2em; margin-right: 6px; }
  .day-row { display: grid; grid-template-columns: minmax(0, 1fr) auto; gap: 6px; align-items: center; }
  .rate { display: inline-flex; gap: 2px; }
  .rate-btn { width: 34px; height: 34px; border-radius: 50%; border: none; background: none; cursor: pointer; display: grid; place-items: center;
    color: var(--secondary-text-color); padding: 0; }
  .rate-btn:hover { background: var(--rema-tint); }
  .rate-btn svg { width: 20px; height: 20px; fill: none; stroke: currentColor; stroke-width: 1.7; stroke-linejoin: round; stroke-linecap: round; }
  .rate-btn.on svg { fill: currentColor; }
  .rate-btn.like.on { color: var(--rema-accent); }
  .rate-btn.dislike.on { color: var(--secondary-text-color); }
  .rate-btn.favorite.on { color: #e5484d; }
  .rate-btn:focus-visible, .setting-row:focus-visible, .rc-open:focus-visible { outline: 2px solid var(--rema-accent); outline-offset: 2px; }
  .subnav { margin: 0 0 12px; }
  .btn.surprise { border-style: dashed; }
  .badge.surprise { background: color-mix(in srgb, #e5484d 15%, transparent); color: var(--primary-text-color); }
  .rc-list { display: grid; margin-top: 4px; }
  .rc-item { display: grid; grid-template-columns: minmax(0, 1fr) auto; gap: 8px; align-items: center; border-top: 1px solid var(--divider-color); }
  .rc-item:first-child { border-top: none; }
  .rc-open { display: grid; gap: 2px; text-align: left; background: none; border: none; color: var(--primary-text-color); font-size: 15px;
    padding: 12px 4px; cursor: pointer; min-width: 0; }
  .rc-open b { overflow-wrap: anywhere; }
  .dialog.wide { width: min(680px, calc(100vw - 24px)); }
  .rc-head { display: flex; gap: 8px; align-items: center; }
  .rc-name { flex: 1; min-width: 0; font-size: 20px !important; font-weight: 600; }
  .rc-meta { grid-template-columns: repeat(auto-fit, minmax(120px, 1fr)); }
  .rc-meta input[type=number] { width: 100%; }
  .rc-step textarea { min-height: 44px; }
  .rc-ing, .rc-step { display: flex; gap: 6px; align-items: center; margin-bottom: 6px; }
  .rc-ing .amount { width: 110px; flex: none; }
  .rc-step .num { flex: none; width: 24px; height: 24px; border-radius: 50%; display: grid; place-items: center; font-size: 13px;
    background: var(--rema-tint); color: var(--rema-accent); font-weight: 600; }
  .icon-btn { flex: none; width: 32px; height: 32px; border-radius: 50%; border: none; background: none; cursor: pointer;
    color: var(--secondary-text-color); display: grid; place-items: center; }
  .icon-btn svg { width: 16px; height: 16px; stroke: currentColor; stroke-width: 2; fill: none; }
  .rc-targets { display: grid; gap: 6px; margin-top: 12px; }
  .chain-logo { --c: #888; flex: none; width: 52px; height: 52px; border-radius: 50%; background: #fff; display: grid; place-items: center;
    overflow: hidden; box-shadow: 0 0 0 3px var(--c), 0 2px 8px rgba(0, 0, 0, .12); }
  /* Beats the product-photo rules (.ev img, .prod img, .line img) the logo sits inside. */
  .chain-logo > img.cl { width: 78%; height: 78%; max-width: none; margin: 0; padding: 0; border: 0; border-radius: 0;
    background: none; object-fit: contain; display: block; }
  .chain-logo span { font-weight: 700; color: var(--c); text-transform: uppercase; }
  .chain-logo.big { width: 44px; height: 44px; }
  .chain-logo.tiny { width: 28px; height: 28px; box-shadow: 0 0 0 2px var(--c); }
  .chain-list .chain-logo, .chain-save .chain-logo { width: 36px; height: 36px; box-shadow: 0 0 0 2px var(--c); }
  .chain-row { display: flex; gap: 14px; overflow-x: auto; padding: 8px 4px 4px; }
  .chain-btn { display: grid; justify-items: center; gap: 8px; background: none; border: none; cursor: pointer; color: var(--primary-text-color);
    font-size: 13px; min-width: 64px; padding: 4px; }
  .chain-btn:focus-visible, .cheaper:focus-visible { outline: 2px solid var(--rema-accent); outline-offset: 2px; border-radius: 12px; }
  .cheaper { display: inline-flex; align-items: center; gap: 6px; margin-top: 4px; border: 1px solid var(--divider-color); background: var(--rema-card);
    color: var(--primary-text-color); border-radius: 999px; padding: 3px 10px 3px 4px; font-size: 12px; cursor: pointer; max-width: 100%; }
  .cheaper.static { cursor: default; }
  .cheaper.plain { padding: 3px 10px; color: var(--secondary-text-color); }
  .everywhere { margin-top: 12px; }
  .everywhere-results h3 { margin: 14px 0 4px; }
  .best-line { margin: 12px 0 0; padding: 8px 12px; border-radius: 10px; background: color-mix(in srgb, var(--rema-ok) 14%, transparent); }
  .evs { list-style: none; padding: 0; margin: 0; }
  .ev { display: grid; grid-template-columns: auto 44px minmax(0, 1fr) auto auto; gap: 10px; align-items: center; padding: 8px 4px;
    border-top: 1px solid var(--divider-color); }
  .ev:first-child { border-top: none; }
  .ev.best { background: color-mix(in srgb, var(--rema-ok) 9%, transparent); border-radius: 10px; }
  .ev img, .ev .noimg { width: 44px; height: 44px; object-fit: contain; border-radius: 8px; background: #fff; }
  .ev .what { display: grid; min-width: 0; } .ev .what b { overflow-wrap: anywhere; }
  .ev .badge { justify-self: start; margin-top: 2px; }
  .ev-price { font-weight: 700; white-space: nowrap; } .ev-price.sale { color: var(--rema-sale); }
  .ev .what .muted { display: -webkit-box; -webkit-box-orient: vertical; -webkit-line-clamp: 2; overflow: hidden; }
  /* On a phone the button sits under the price, so a row is two lines, not four. */
  @media (max-width: 600px) {
    .ev { grid-template-columns: auto 40px minmax(0, 1fr) auto; row-gap: 4px; padding: 8px 2px; }
    .ev > .chain-logo, .ev > img, .ev > .noimg, .ev > .what { grid-row: 1 / 3; }
    .ev > .ev-price { grid-column: 4; grid-row: 1; justify-self: end; align-self: end; }
    .ev > .btn { grid-column: 4; grid-row: 2; justify-self: end; align-self: start; padding: 4px 10px; min-height: 0; font-size: .85rem; }
    .ev img, .ev .noimg { width: 40px; height: 40px; }
  }
  .day-row.past { opacity: .55; }
  .week-head { margin: 14px 0 4px; font-size: .95rem; color: var(--secondary-text-color); }
  .help-row { display: flex; align-items: flex-start; justify-content: flex-end; gap: 8px; margin: 6px 0; }
  .help-row .help-text { flex: 1; margin: 2px 0; }
  .help-q { flex: none; width: 24px; height: 24px; border-radius: 50%; border: 1px solid var(--divider-color); background: none; cursor: pointer;
    color: var(--secondary-text-color); font-weight: 700; font-size: .8rem; line-height: 1; display: grid; place-items: center; padding: 0; }
  .help-q[aria-expanded="true"] { background: var(--secondary-background-color); color: var(--primary-text-color); }
  .dialog.where { padding-top: 0; padding-bottom: 0; max-height: min(80vh, 720px); max-height: min(80dvh, 720px); }
  .dialog-top, .dialog-bottom { position: sticky; z-index: 1; background: var(--rema-solid-card); display: flex; align-items: center; gap: 8px; }
  .dialog-top { top: 0; padding: 14px 0 8px; margin-bottom: 4px; }
  .dialog-top h2 { margin: 0; flex: 1; font-size: 1.15rem; overflow-wrap: anywhere; }
  .dialog-top .close { width: 36px; height: 36px; background: var(--secondary-background-color); }
  .dialog-bottom { bottom: 0; justify-content: flex-end; padding: 10px 0 14px; margin-top: 8px; border-top: 1px solid var(--divider-color); }
  .cheaper { justify-self: start; width: fit-content; }
  .cheaper > span:not(.chain-logo) { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .chain-save { align-items: center; }
  .chain-save > span:not(.chain-logo) { flex: 1; min-width: 200px; }
  .chain-list { border-top: 4px solid var(--c); }
  .chain-list .row { gap: 12px; align-items: center; }
  .clines { list-style: none; padding: 0; margin: 8px 0 0; }
  .cline { display: grid; grid-template-columns: auto minmax(0, 1fr) auto auto; grid-template-areas: "box what cost ctrl"; gap: 8px;
    align-items: center; padding: 10px 0; border-top: 1px solid var(--divider-color); }
  .cline .box { grid-area: box; } .cline .what { grid-area: what; } .cline .cost { grid-area: cost; }
  .cline .ctrl { grid-area: ctrl; display: inline-flex; align-items: center; gap: 4px; }
  .cline .what { display: grid; min-width: 0; } .cline .what b { overflow-wrap: anywhere; }
  .cline.bought .what b { text-decoration: line-through; opacity: .6; }
  .cline .box { width: 28px; height: 28px; border-radius: 8px; border: 2px solid var(--c, var(--rema-accent)); background: none; cursor: pointer;
    color: var(--rema-on-accent); font-weight: 700; }
  .cline.bought .box { background: var(--c, var(--rema-accent)); color: #fff; }
  .stepper { display: inline-flex; align-items: center; gap: 2px; }
  .stepper .icon-btn { font-size: 18px; }
  .plan-chains { list-style: none; padding: 0; margin: 12px 0; display: grid; gap: 8px; }
  .plan-chains li { display: flex; align-items: center; gap: 8px; }
  .chain-pick { display: grid; grid-template-columns: repeat(auto-fill, minmax(150px, 1fr)); gap: 10px; margin: 12px 0; }
  .chain-choice { display: flex; align-items: center; gap: 10px; padding: 8px; border-radius: 12px; border: 1px solid var(--divider-color); cursor: pointer; }
  .chain-choice .chain-logo { width: 36px; height: 36px; box-shadow: 0 0 0 2px var(--c); }
  .clamp { display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden; }
  @media (max-width: 600px) { .cline { grid-template-columns: auto minmax(0, 1fr) auto; grid-template-areas: "box what cost" ". ctrl ctrl"; row-gap: 2px; } }
  .setting-rows { display: grid; margin-top: 8px; }
  .setting-row { display: grid; grid-template-columns: 40px 1fr auto; gap: 12px; align-items: center; width: 100%; text-align: left;
    background: none; border: none; border-top: 1px solid var(--divider-color); padding: 14px 4px; color: var(--primary-text-color);
    font-size: 15px; cursor: pointer; }
  .setting-row:first-child { border-top: none; }
  .setting-row:hover { background: var(--rema-tint); }
  .setting-icon { width: 40px; height: 40px; border-radius: 12px; display: grid; place-items: center;
    background: var(--rema-tint); color: var(--rema-accent); }
  .setting-icon svg { width: 22px; height: 22px; fill: none; stroke: currentColor; stroke-width: 1.7; stroke-linecap: round; stroke-linejoin: round; }
  .setting-text { display: grid; gap: 2px; min-width: 0; }
  .setting-text .small { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .chev { font-size: 22px; color: var(--secondary-text-color); }
  .settings-head { display: flex; align-items: center; gap: 12px; flex-wrap: wrap; margin-bottom: 12px; }
  .settings-head h1 { margin: 0; }
  .btn.back { padding: 6px 12px; }
  .wishes { margin-top: 12px; } .hero .wishes { text-align: center; }
  .note-preview { margin: 6px 0 0; white-space: pre-line; overflow-wrap: anywhere; }
  h2.flush { margin-top: 0; }
  .day.today { box-shadow: inset 3px 0 0 var(--rema-accent); }
  .seg { display: inline-flex; gap: 2px; padding: 3px; margin-top: 12px; border-radius: 999px; background: var(--rema-subtle); }
  .seg button { border: none; background: none; color: var(--secondary-text-color); padding: 7px 16px; border-radius: 999px;
    font-size: 14px; font-weight: 500; cursor: pointer; }
  .seg button.active { background: var(--rema-accent); color: var(--rema-on-accent); }
  .scrim { position: fixed; inset: 0; z-index: 20; background: rgba(0, 0, 0, .45); }
  .dialog { position: fixed; z-index: 21; left: 50%; top: 50%; transform: translate(-50%, -50%); width: min(520px, calc(100vw - 32px));
    max-height: calc(100vh - 32px); overflow: auto; padding: 18px; border-radius: var(--ha-card-border-radius, 16px);
    background: var(--rema-solid-card); border: 1px solid var(--divider-color); box-shadow: 0 12px 40px rgba(0, 0, 0, .3); }
  .dialog h2 { margin-top: 0; } .dialog-actions { margin-top: 12px; }
  .link { background: none; border: none; color: var(--primary-color); cursor: pointer; text-decoration: underline; font-size: inherit; }
  .banner { border-radius: 10px; padding: 10px 14px; margin-bottom: 12px; display: flex; align-items: center; gap: 10px; flex-wrap: wrap; }
  .banner.info { background: var(--rema-tint); }
  .banner.warn { background: color-mix(in srgb, var(--rema-warn) 18%, transparent); }
  .banner.error { background: color-mix(in srgb, var(--rema-sale) 15%, transparent); }
  .spinner { width: 18px; height: 18px; border: 3px solid var(--rema-tint); border-top-color: var(--rema-accent); border-radius: 50%;
    display: inline-block; animation: spin 1s linear infinite; vertical-align: middle; }
  .spinner.small { width: 14px; height: 14px; border-width: 2px; }
  @keyframes spin { to { transform: rotate(360deg); } }
  .hero { text-align: center; padding: 32px 18px; } .hero .row { justify-content: center; }
  .hero-icon { width: 72px; height: 72px; margin-bottom: 8px; }
  .price { text-align: right; display: flex; flex-direction: column; } .price .big { font-size: 22px; font-weight: 700; color: var(--rema-accent); }
  .price.over .big { color: var(--rema-sale); }
  .days { display: grid; gap: 8px; margin-top: 12px; }
  .day { display: grid; grid-template-columns: 130px 1fr auto; gap: 12px; align-items: center; text-align: left; width: 100%;
    background: var(--rema-subtle); border: none; border-radius: 10px; padding: 12px 14px;
    color: var(--primary-text-color); font-size: 15px; cursor: pointer; }
  .day .date { font-weight: 600; color: var(--rema-accent); } .day .meta { color: var(--secondary-text-color); font-size: 13px; white-space: nowrap; }
  .badge { display: inline-block; font-size: 11px; font-weight: 600; padding: 2px 8px; border-radius: 999px;
    background: var(--rema-subtle); color: var(--secondary-text-color); vertical-align: middle; }
  .badge.offer { background: var(--rema-sale); color: var(--rema-on-sale); }
  .badge.eco, .badge.sent { background: var(--rema-ok); color: var(--rema-on-accent); }
  .badge.from { background: var(--info-color, #039be5); color: #fff; }
  .prod .avis { display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden; }
  .badge.draft { background: var(--rema-accent); color: var(--rema-on-accent); }
  details { margin-top: 14px; } summary { cursor: pointer; color: var(--secondary-text-color); }
  .checklist { list-style: none; padding: 0; } .checklist li { padding: 3px 0; } .checklist .bad { color: var(--rema-sale); }
  .chips { display: flex; gap: 8px; overflow-x: auto; padding-bottom: 8px; margin-bottom: 8px; }
  .chip { border: 1px solid var(--divider-color); background: var(--card-background-color); color: var(--primary-text-color);
    border-radius: 999px; padding: 8px 14px; white-space: nowrap; cursor: pointer; font-size: 14px; }
  .chip.active { background: var(--rema-accent); color: var(--rema-on-accent); border-color: var(--rema-accent); }
  .recipe h1 { font-size: 26px; }
  .recipe-grid { display: grid; grid-template-columns: minmax(0, 1fr) minmax(0, 2fr); gap: 24px; }
  .recipe-grid section { min-width: 0; overflow-wrap: anywhere; }
  .ingredients { list-style: none; padding: 0; margin: 0; }
  .ingredients li { display: flex; gap: 10px; align-items: center; padding: 9px 0; border-bottom: 1px solid var(--divider-color);
    font-size: 17px; cursor: pointer; }
  .ingredients .amount { font-weight: 600; min-width: 70px; }
  .box { width: 22px; height: 22px; border: 2px solid var(--rema-accent); border-radius: 6px; display: inline-flex;
    align-items: center; justify-content: center; color: var(--rema-on-accent); flex: none; font-size: 14px; }
  li.done .box { background: var(--rema-accent); } li.done { opacity: .5; text-decoration: line-through; }
  .steps { list-style: none; padding: 0; margin: 0; }
  .step { padding: 12px 0; border-bottom: 1px solid var(--divider-color); display: flex; gap: 10px; align-items: flex-start;
    justify-content: space-between; flex-wrap: wrap; }
  .step-text { font-size: 19px; line-height: 1.5; cursor: pointer; flex: 1; min-width: 200px; display: flex; gap: 12px; }
  .num { flex: none; width: 30px; height: 30px; border-radius: 50%; background: var(--rema-accent); color: var(--rema-on-accent); font-weight: 700;
    display: inline-flex; align-items: center; justify-content: center; font-size: 15px; }
  .step.done .step-text { opacity: .45; text-decoration: line-through; } .step.done .num { background: var(--rema-ok); }
  .step.alarm { background: color-mix(in srgb, var(--rema-sale) 15%, transparent); border-radius: 10px; }
  .timer { border: 1px solid var(--rema-accent); color: var(--rema-accent); background: none; border-radius: 999px; padding: 6px 12px;
    font-size: 14px; cursor: pointer; font-variant-numeric: tabular-nums; }
  .timer.running { background: var(--rema-accent); color: var(--rema-on-accent); }
  .tip { background: var(--rema-subtle); padding: 10px 14px; border-radius: 10px; }
  .lines, .history, .favs, .rema { list-style: none; padding: 0; margin: 0; }
  .line { display: grid; grid-template-columns: 48px 1fr auto; gap: 12px; align-items: center; padding: 10px 0;
    border-bottom: 1px solid var(--divider-color); }
  .line img, .noimg { width: 48px; height: 48px; object-fit: contain; border-radius: 8px; background: #fff; }
  .noimg { display: flex; align-items: center; justify-content: center; color: var(--secondary-text-color); background: var(--secondary-background-color); }
  .what { display: flex; flex-direction: column; gap: 2px; min-width: 0; }
  .what .title { display: flex; flex-wrap: wrap; align-items: center; gap: 4px 6px; }
  .note { color: var(--rema-warn); font-size: 13px; }
  .cost { text-align: right; display: flex; flex-direction: column; font-size: 13px; color: var(--secondary-text-color); white-space: nowrap; }
  .cost b { color: var(--primary-text-color); font-size: 15px; }
  .rema li { padding: 6px 0; border-bottom: 1px solid var(--divider-color); } .rema .bought { opacity: .45; text-decoration: line-through; }
  .hist, .fav { display: flex; gap: 10px; align-items: center; padding: 12px 0; border-bottom: 1px solid var(--divider-color); }
  .hist .what, .fav .what { flex: 1; cursor: pointer; } .fav.edit { flex-direction: column; align-items: stretch; }
  .field { display: flex; flex-direction: column; gap: 6px; font-size: 14px; color: var(--secondary-text-color); margin: 8px 0; }
  .field.inline { flex-direction: row; align-items: center; }
  .grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(220px, 1fr)); gap: 4px 16px; }
  input[type=text], input[type=number], input[type=date], input[type=search], input[type=url], input:not([type]), select, textarea {
    font: inherit; font-size: 16px; color: var(--primary-text-color); background: var(--secondary-background-color, transparent);
    border: 1px solid var(--divider-color); border-radius: 8px; padding: 8px 10px; }
  input[type=number] { width: 90px; } textarea { width: 100%; resize: vertical; }
  .checks { display: flex; flex-wrap: wrap; gap: 6px 18px; }
  .check { display: flex; align-items: center; gap: 6px; font-size: 15px; padding: 4px 0; }
  .rowitem { padding: 6px 0; border-bottom: 1px dashed var(--divider-color); }
  .results { display: grid; gap: 6px; margin-top: 8px; }
  .shop-search { margin-top: 14px; }
  .line.tappable { cursor: pointer; } .line.tappable:hover { background: var(--rema-subtle); }
  .line-head { display: flex; gap: 12px; align-items: center; margin-bottom: 8px; }
  .line-head img, .line-head .noimg { width: 56px; height: 56px; object-fit: contain; border-radius: 8px; background: #fff; flex: 0 0 auto; }
  .line-head h2 { margin: 0; }
  .stepper { align-items: center; gap: 8px; margin: 10px 0; } .stepper .count { min-width: 28px; text-align: center; font-size: 18px; }
  .small-h { font-size: 16px; margin: 14px 0 6px; }
  .badge.mealie { background: #e58325; color: #fff; }
  a.btn { text-decoration: none; display: inline-flex; align-items: center; }
  .mic.on { background: var(--rema-sale); color: var(--rema-on-sale); border-color: transparent; }
  details.nutrition table { width: 100%; border-collapse: collapse; margin-top: 6px; }
  details.nutrition td { padding: 6px 4px; border-bottom: 1px solid var(--divider-color); } details.nutrition td:last-child { text-align: right; font-weight: 600; }
  .nutri { background: var(--rema-subtle); padding: 8px 12px; border-radius: 10px; }
  .kpis { display: grid; grid-template-columns: repeat(auto-fill, minmax(120px, 1fr)); gap: 10px; margin: 10px 0; }
  .kpi { display: flex; flex-direction: column; background: var(--rema-subtle); border-radius: 12px; padding: 10px 12px; }
  .kpi .big { font-size: 22px; font-weight: 700; color: var(--rema-accent); } .kpi .big.warn { color: var(--rema-warn); }
  .hrow { display: flex; gap: 12px; align-items: center; padding: 10px 0; border-bottom: 1px solid var(--divider-color); }
  .hrow .what { flex: 1; }
  .meter { height: 8px; border-radius: 999px; background: var(--rema-subtle); overflow: hidden; margin-top: 6px; }
  .meter span { display: block; height: 100%; border-radius: 999px; background: var(--rema-accent); }
  .meter.low span { background: var(--rema-warn); } .meter.over span { background: var(--rema-sale); }
  .result .add { color: var(--rema-accent); font-weight: 600; white-space: nowrap; }
  .result .badge, .result .add { display: inline-block; flex: 0 0 auto; }
  .options { display: grid; gap: 8px; }
  .option { display: flex; flex-direction: column; gap: 3px; text-align: left; width: 100%; background: var(--rema-subtle);
    border: 1px solid transparent; border-radius: 10px; padding: 12px 14px; color: var(--primary-text-color); font-size: 15px; cursor: pointer; }
  .option:hover:not([disabled]) { border-color: var(--rema-accent); }
  .option[disabled] { cursor: default; opacity: .75; }
  .pantry-item { display: flex; gap: 10px; align-items: center; justify-content: space-between; padding: 10px 0;
    border-bottom: 1px solid var(--divider-color); }
  .pantry-item .what { flex: 1; } .pantry-item .btn, .pantry-item .badge { white-space: nowrap; flex: 0 0 auto; }
  .link.small { font-size: 12px; padding: 2px 0; }
  .result { display: flex; gap: 10px; align-items: center; text-align: left; background: var(--rema-subtle);
    border: none; border-radius: 10px; padding: 8px 10px; cursor: pointer; color: var(--primary-text-color); }
  .result img { width: 40px; height: 40px; object-fit: contain; background: #fff; border-radius: 6px; }
  .result span { display: flex; flex-direction: column; flex: 1; }
  .prod-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(140px, 1fr)); gap: 10px; }
  .prod { display: flex; flex-direction: column; gap: 6px; padding: 8px; border: 1px solid var(--divider-color);
    border-radius: 12px; background: var(--rema-subtle); min-width: 0; font-size: 14px; }
  .prod img, .prod .noimg { width: 100%; height: 90px; object-fit: contain; border-radius: 8px; }
  .prod img { background: #fff; } /* product photos are shot on white */
  .prod-body { display: flex; flex-direction: column; gap: 3px; flex: 1; min-width: 0; overflow-wrap: break-word; hyphens: auto; }
  .prod-body > b { display: -webkit-box; -webkit-line-clamp: 3; -webkit-box-orient: vertical; overflow: hidden; }
  .prod-price { display: flex; flex-wrap: wrap; gap: 0 6px; align-items: baseline; font-size: 16px; }
  .prod .btn { width: 100%; }
  .sale { color: var(--rema-sale); font-weight: 700; }
  .favlist { list-style: none; padding: 0; margin: 8px 0 0; }
  .fav-row { display: flex; gap: 10px; align-items: center; padding: 8px 0; border-bottom: 1px solid var(--divider-color); }
  .fav-row .what { flex: 1; }
  .filter { width: 100%; margin-top: 10px; }
  .sticky { position: sticky; bottom: 0; background: var(--rema-solid-card); padding: 12px 0 calc(12px + var(--rema-safe-bottom, env(safe-area-inset-bottom, 0px)));
    border-top: 1px solid var(--divider-color); }
  /* Last in the settings view, so it stays at the bottom of the screen all the way down. */
  .savebar { position: sticky; bottom: calc(8px + var(--rema-safe-bottom, env(safe-area-inset-bottom, 0px))); z-index: 2; display: flex; flex-wrap: wrap; gap: 8px; align-items: center;
    margin-top: 16px; padding: 12px 16px; background: var(--rema-solid-card); border: 1px solid var(--divider-color);
    border-radius: var(--ha-card-border-radius, 12px); box-shadow: 0 -2px 12px rgba(0, 0, 0, .12); }
  .toast { position: fixed; left: 50%; bottom: calc(24px + var(--rema-safe-bottom, env(safe-area-inset-bottom, 0px))); transform: translateX(-50%); background: var(--primary-text-color); color: var(--primary-background-color);
    padding: 12px 20px; border-radius: 10px; z-index: 10; max-width: 90vw; box-shadow: 0 4px 12px rgba(0,0,0,.3); }
  @media (max-width: 700px) {
    .recipe-grid { grid-template-columns: 1fr; }
    .day { grid-template-columns: 1fr; gap: 4px; }
    .price { text-align: left; }
    .step-text { font-size: 18px; }
    .line { grid-template-columns: 40px 1fr; } .line .cost { grid-column: 2; text-align: left; flex-direction: row; gap: 8px; }
    .prod-grid { grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 6px; }
    .prod { padding: 6px; gap: 4px; font-size: 12px; border-radius: 10px; }
    .prod img, .prod .noimg { height: 64px; }
    .prod-price { font-size: 14px; }
    .prod .badge { font-size: 10px; padding: 1px 5px; }
    .prod .btn { padding: 6px 4px; font-size: 12px; }
    /* Phone: the tabs become a low bar at the very bottom, see-through like the CRM's menu. */
    :host { --rema-tabbar: calc(56px + max(2px, var(--rema-safe-bottom, env(safe-area-inset-bottom, 0px)) - 16px)); }
    .tabs { position: fixed; top: auto; bottom: 0; left: 0; right: 0; z-index: 5; display: grid;
      grid-template-columns: repeat(6, minmax(0, 1fr)); gap: 0; overflow: visible;
      /* side padding keeps the outer icons clear of the screen's rounded corners */
      padding: 5px 22px max(2px, calc(var(--rema-safe-bottom, env(safe-area-inset-bottom, 0px)) - 16px));
      border-bottom: none; border-top: 1px solid var(--divider-color);
      background: color-mix(in srgb, var(--primary-background-color) 60%, transparent);
      -webkit-backdrop-filter: blur(2px) saturate(1.4); backdrop-filter: blur(2px) saturate(1.4); }
    .tab { display: flex; flex-direction: column; align-items: center; gap: 2px; padding: 6px 0 4px; min-width: 0;
      font-size: 10.5px; font-weight: 600; border-bottom: none; }
    .tab span { max-width: 100%; overflow: hidden; text-overflow: ellipsis; }
    .tabs { grid-template-columns: repeat(5, minmax(0, 1fr)); }
    .tab.extra { display: none; }
    .tab.more { display: flex; }
    .more-scrim:not([hidden]) { display: block; position: fixed; inset: 0; z-index: 4; }
    .more-sheet:not([hidden]) { display: flex; flex-direction: column; position: fixed; right: 8px; z-index: 6;
      bottom: calc(var(--rema-tabbar) + 8px); min-width: 200px; padding: 6px; border-radius: 16px;
      background: var(--rema-solid-card); border: 1px solid var(--divider-color); box-shadow: 0 8px 28px rgba(0, 0, 0, .22); }
    .more-item { display: flex; align-items: center; gap: 12px; padding: 12px 14px; border: none; border-radius: 10px;
      background: none; color: var(--primary-text-color); font-size: 16px; font-weight: 500; text-align: left; cursor: pointer; }
    .more-item svg { width: 22px; height: 22px; fill: none; stroke: currentColor; stroke-width: 1.8; stroke-linecap: round; stroke-linejoin: round; }
    .more-item.active { color: var(--rema-accent); background: var(--rema-tint); }
    .tab svg { display: block; }
    main { padding-bottom: calc(96px + var(--rema-tabbar)); }
    .savebar { bottom: calc(8px + var(--rema-tabbar)); }
    .sticky { bottom: var(--rema-tabbar); padding-bottom: 12px; }
    .toast { bottom: calc(16px + var(--rema-tabbar)); }
  }
`;

if (!customElements.get("middagsro-panel")) customElements.define("middagsro-panel", Rema1000Panel);
