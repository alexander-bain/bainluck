// #999 L2-65 — the ONE shared helper that resolves a market/tournament to its
// event-concept key (`event:<domain>:<slug>`), so Discover cards, futures-detail,
// search, and sport pages all route into /event/[key] the SAME way — no
// per-tournament hardcoding. Mirrors the backend derivation
// (utils/name_normalization.clean_slug + utils/event_tennis.is_winner_market);
// the backend /api/event/{key} resolver is tolerant (exact clean_slug OR
// token-subset, then richest-market canonicalization), so a name-derived slug
// resolves to the canonical event page.

/** Mirror of backend `clean_slug`: lowercase, non-alphanumeric runs → "-", trim. */
export function cleanSlug(name: string | null | undefined): string {
  return (name || "")
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "");
}

const WINNER_RE = /\b(winner|champion|champ|to win)\b/i;
const MATCHUP_RE = /\b(vs\.?|v\.?|def\.?|beats?)\b/i;

/** Mirror of backend `is_winner_market`: a tournament-winner FIELD (the parent),
 *  not a single "X vs Y" match. */
export function isWinnerMarketName(name: string | null | undefined): boolean {
  const n = name || "";
  return WINNER_RE.test(n) && !MATCHUP_RE.test(n);
}

/** Winner-FIELD event-concept domains, keyed by `llm_sport_category`. A winner
 *  market's name-slug resolves server-side to the canonical event page (the tennis
 *  and F1 adapters match token-tolerantly). Golf is NOT here: golf slug matching is
 *  EXACT, so a client-derived slug can dead-link — golf links come from the
 *  backend-attached `event_concept_key` (see FuturesMarket) or tournamentEventKey.
 *  Mirrors backend `utils/concept_links.derive_market_concept_key`. */
const WINNER_FIELD_DOMAINS: Record<string, string> = {
  tennis: "tennis",
  motorsports: "f1",
};

// F1 sub-markets (sprint/quali/pole/…) are children, not the GP winner field.
// Mirrors backend `event_f1._F1_SUBMARKET_RE`.
const F1_SUBMARKET_RE =
  /\b(sprint|qualifying|pole|podium|constructor|fastest|top\s*\d|q[123])\b/i;

// L2-91: UFC + boxing card FIGHT ticker prefixes -> event domain. A fight ticker is
// `<PREFIX>-<YYMONDD><FIGHTERS>`; the date-token groups a card. Prop tickers
// (KXUFCMOV… / KXBOXINGMOV…) don't match the `<PREFIX>-<date>` shape, so only real
// fights derive a card concept. Mirrors backend `event_combat.card_token`.
const COMBAT_FIGHT_PREFIXES: [string, string][] = [
  ["KXUFCFIGHT", "ufc"],
  ["KXBOXING", "boxing"],
];

/** Card event key for a combat FIGHT market (UFC/boxing), from its fight ticker's
 *  date-token, or null. e.g. "kalshi:KXUFCFIGHT-26JUL11MCGHOL" -> "event:ufc:26jul11". */
export function combatCardKey(m: { external_id?: string | null }): string | null {
  const eid = (m.external_id || "").toUpperCase();
  for (const [prefix, domain] of COMBAT_FIGHT_PREFIXES) {
    const mt = eid.match(new RegExp(`${prefix}-(\\d{2}[A-Z]{3}\\d{2})`));
    if (mt) return `event:${domain}:${mt[1].toLowerCase()}`;
  }
  return null;
}

// L2-88: awards ceremony detection, mirroring backend `derive_awards_concept`
// (event_awards.py CEREMONIES). Ticker stem (unambiguous) first, then a name
// keyword — award category markets carry the ceremony word ("Oscar winner: …").
// The BARE ceremony slug resolves server-side to the latest rich edition, so the
// breadcrumb is never a dead link even for an older-edition market.
const AWARDS_TICKER_STEMS: [string, string][] = [
  ["KXOSCAR", "oscars"],
  ["KXEMMY", "emmys"],
  ["KXTONYAWARDS", "tonys"],
  ["KXGRAM", "grammys"],
];
const AWARDS_NAME_STEMS: [string, string][] = [
  ["academy award", "oscars"],
  ["oscar", "oscars"],
  ["emmy", "emmys"],
  ["grammy", "grammys"],
  ["tony award", "tonys"],
];

const AWARDS_SLUG_DISPLAY: Record<string, string> = {
  oscars: "The Oscars",
  emmys: "The Emmys",
  grammys: "The Grammys",
  tonys: "The Tony Awards",
};

/** Human ceremony name for an `event:awards:<slug>` key ("The Oscars"), or null. */
export function awardsCeremonyName(key: string | null | undefined): string | null {
  if (!key || !key.startsWith("event:awards:")) return null;
  const slug = key.slice("event:awards:".length).replace(/-\d{2,4}$/, "");
  return AWARDS_SLUG_DISPLAY[slug] || null;
}

/** Ceremony event key for an awards MARKET (Oscar/Emmy/Tony/Grammy), or null. */
export function awardsEventKey(m: {
  name?: string | null;
  external_id?: string | null;
}): string | null {
  const eid = (m.external_id || "").toUpperCase();
  for (const [stem, slug] of AWARDS_TICKER_STEMS) {
    if (eid.includes(stem)) return `event:awards:${slug}`;
  }
  const n = (m.name || "").toLowerCase();
  for (const [stem, slug] of AWARDS_NAME_STEMS) {
    if (n.includes(stem)) return `event:awards:${slug}`;
  }
  return null;
}

/**
 * Event key for a futures MARKET (Discover futures card / futures-detail), or
 * null when the market isn't part of an event concept. Winner-field markets in an
 * adapter domain (tennis) resolve by name-slug; awards category/nomination markets
 * resolve to their ceremony page. A single sports match/prop can't derive its parent
 * event key client-side (that needs the backend matcher; tracked as a follow-up).
 */
export function marketEventKey(m: {
  name?: string | null;
  llm_sport_category?: string | null;
  external_id?: string | null;
}): string | null {
  // L2-88: awards ceremonies (config-driven, engine-link pattern) link up first.
  const awards = awardsEventKey(m);
  if (awards) return awards;
  // L2-91: a combat fight ticker is authoritative regardless of category.
  const combat = combatCardKey(m);
  if (combat) return combat;
  const cat = (m.llm_sport_category || "").toLowerCase();
  const domain = WINNER_FIELD_DOMAINS[cat];
  if (!domain) return null;
  if (!isWinnerMarketName(m.name)) return null;
  // F1: only true Grand Prix winner fields (not sprint/quali/pole, and require
  // "grand prix" so a motorsports-miscategorized market can't leak a bad concept).
  if (domain === "f1") {
    const n = (m.name || "").toLowerCase();
    if (!n.includes("grand prix") || F1_SUBMARKET_RE.test(m.name || "")) return null;
  }
  const slug = cleanSlug(m.name);
  return slug ? `event:${domain}:${slug}` : null;
}

/**
 * Event key for a golf TOURNAMENT (Discover tournament card, sport/league
 * tournament cards). Prefers an already-formed event key, then the payload slug,
 * then a slug derived from the name/key. Golf is the only tournament-card domain
 * today, so the domain defaults to golf.
 */
export function tournamentEventKey(t: {
  key?: string | null;
  slug?: string | null;
  name?: string | null;
}): string | null {
  if (t.key && t.key.startsWith("event:")) return t.key;
  const slug =
    (t.slug && cleanSlug(t.slug)) ||
    (t.name && cleanSlug(t.name)) ||
    (t.key && cleanSlug(t.key.replace(/_/g, " "))) ||
    "";
  return slug ? `event:golf:${slug}` : null;
}

/** Split an event key into (domain, slug), mirroring backend `parse_event_key`.
 *  Canonical form `event:<domain>:<slug>`; also tolerates `<domain>:<slug>` and a
 *  bare slug (treated as golf, the slice-1 parity domain). */
export function parseEventKey(key: string): { domain: string; slug: string } {
  const parts = (key || "").split(":");
  if (parts.length >= 3 && parts[0] === "event") {
    return { domain: parts[1], slug: parts.slice(2).join(":") };
  }
  if (parts.length === 2) return { domain: parts[0], slug: parts[1] };
  return { domain: "golf", slug: key };
}

/** Build the app path for an event key (L2-113: colon-free `/event/<domain>/<slug>`,
 *  so a shared URL reads `/event/ufc/26jul11` instead of `/event/event%3Aufc%3A…`).
 *  The API still keys on `event:<domain>:<slug>`; only the browser URL changes. */
export function eventPath(key: string): string {
  const { domain, slug } = parseEventKey(key);
  return `/event/${encodeURIComponent(domain)}/${encodeURIComponent(slug)}`;
}

// L2-91: competition hub display labels (mirrors routes/hub.py HUB_CONFIGS). Used
// for the fallback up-link when a market has no specific event concept but its
// competition has a /hub/<slug> page (e.g. a UFC futures market -> /hub/mma).
const HUB_LABELS: Record<string, string> = {
  mma: "MMA",
  boxing: "Boxing",
  golf: "Golf",
  tennis: "Tennis",
  esports: "Esports",
};

/** Display label for a competition hub slug ("MMA"), or null if unknown. */
export function hubLabel(slug: string | null | undefined): string | null {
  return slug ? HUB_LABELS[slug] || null : null;
}

/** Build the app path for a competition hub slug. */
export function hubPath(slug: string): string {
  return `/hub/${slug}`;
}

// L2-94: themed section-page labels (mirrors backend concept_links._CATEGORY_PAGE).
// The mesh fallback below the hub: a politics/economics/weather/entertainment market
// with no specific concept and no competition hub up-links to its /<slug> page.
const CATEGORY_PAGE_LABELS: Record<string, string> = {
  politics: "Politics",
  economics: "Economics",
  weather: "Weather",
  entertainment: "Entertainment",
};

/** Display label for a themed section-page slug ("Politics"), or null if unknown. */
export function categoryPageLabel(slug: string | null | undefined): string | null {
  return slug ? CATEGORY_PAGE_LABELS[slug] || null : null;
}

/** Build the app path for a themed section-page slug ("/politics"). */
export function categoryPagePath(slug: string): string {
  return `/${slug}`;
}

/** Build the app path for a hub-less sport's sport page ("/sports/soccer_epl"). */
export function sportPagePath(key: string): string {
  return `/sports/${key}`;
}

/** Human breadcrumb label for an event-concept key + its market name. Awards read
 *  as the ceremony ("The Oscars"); combat cards read as the card; winner fields drop
 *  the "Winner/Champion" suffix ("… British Grand Prix"). */
export function conceptDisplayLabel(
  key: string | null | undefined,
  marketName: string | null | undefined,
): string | null {
  if (!key) return null;
  const ceremony = awardsCeremonyName(key);
  if (ceremony) return ceremony;
  if (key.startsWith("event:ufc:") || key.startsWith("event:boxing:")) {
    return "the full fight card";
  }
  const name = marketName || "";
  return (
    name.replace(/\s*(winner|champion|champ|to win)\s*$/i, "").trim() || name || null
  );
}
