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

/** Domains that have a registered event-concept adapter today. Tennis winner
 *  markets map by name-slug; golf routes via tournament data (see
 *  tournamentEventKey). Extend as adapters land (F1/UFC = later slice). */
const MARKET_EVENT_DOMAINS = new Set(["tennis"]);

/**
 * Event key for a futures MARKET (Discover futures card / futures-detail), or
 * null when the market isn't part of an event concept. Only winner-field markets
 * in an adapter domain resolve — a single match/prop can't derive its parent
 * event key client-side (that needs the backend matcher; tracked as a follow-up).
 */
export function marketEventKey(m: {
  name?: string | null;
  llm_sport_category?: string | null;
}): string | null {
  const cat = (m.llm_sport_category || "").toLowerCase();
  if (!MARKET_EVENT_DOMAINS.has(cat)) return null;
  if (!isWinnerMarketName(m.name)) return null;
  const slug = cleanSlug(m.name);
  return slug ? `event:${cat}:${slug}` : null;
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

/** Build the app path for an event key (single-encode the colons for the route). */
export function eventPath(key: string): string {
  return `/event/${encodeURIComponent(key)}`;
}
