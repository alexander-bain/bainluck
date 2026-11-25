/**
 * #13102 (Decision 385: A) — Types and URL helpers for /grade/scout morning blind deck.
 * Kept separate from app/grade/scout/page.tsx so Next.js App Router page exports stay valid.
 */

export interface ScoutBlindMember {
  title: string;
  leading_outcome: string;
  probability: number | null;
  change_24h: number | null;
  image_url: string | null;
}

export interface ScoutBlindCard {
  item_id: string;
  title: string;
  kicker: string;
  category: string;
  summary: string;
  look: "bars" | "map" | "faces";
  member_count: number;
  members: ScoutBlindMember[];
}

export interface ScoutMorningDeckResponse {
  status: "ready" | "empty";
  deck_date: string;
  staged_count: number;
  decoy_count: number;
  total_count: number;
  sealed_key_sha256: string | null;
  items: ScoutBlindCard[];
  message: string | null;
}

export const SCOUT_DECK_DEFAULT_SURFACE = "grade_scout_morning_deck";
export const SCOUT_DECK_ITEM_TYPE = "scout_morning_deck";
const SMOKE_SURFACE_RE = /^grade_scout_smoke_[a-z0-9_]{1,25}$/;
const DATE_RE = /^\d{4}-\d{2}-\d{2}$/;

export function parseScoutDeckSearchParams(search: string): {
  deckDate: string | null;
  activeSurface: string;
} {
  const params = new URLSearchParams(search);
  const rawDate = (params.get("date") || "").trim();
  const deckDate = DATE_RE.test(rawDate) ? rawDate : null;
  const rawSmoke = (params.get("smoke_surface") || "").trim();
  const activeSurface = SMOKE_SURFACE_RE.test(rawSmoke)
    ? rawSmoke
    : SCOUT_DECK_DEFAULT_SURFACE;
  return { deckDate, activeSurface };
}
