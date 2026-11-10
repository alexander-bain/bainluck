import type { FeedResponse } from "@/lib/types";
import { probabilityValue } from "@/lib/probabilityDisplay";

// #12361: decode the real-valued fields before hero selection, eligibility and
// formatting see them. Labels, IDs, counts, dates and settlement evidence keep
// their wire values. Recursing also reaches members inside theme bundles.
const NUMERIC_FIELDS = new Set([
  "probability", "current_probability", "opening_probability",
  "home_probability", "away_probability", "draw_probability",
  "home_win_probability", "away_win_probability", "merged_probability",
  "secondary_probability", "winner_opening_probability",
  "yes_probability", "no_probability", "basis_price",
  "movement", "movement_24h", "probability_change_24h", "trend_24h",
  "stored_movement_claim", "supported_move", "supported_move_points",
]);

function decode(value: unknown): unknown {
  if (Array.isArray(value)) {
    const decoded = value.map(decode);
    return decoded.some((entry, i) => entry !== value[i]) ? decoded : value;
  }
  if (value === null || typeof value !== "object") return value;

  const record = value as Record<string, unknown>;
  let decoded: Record<string, unknown> | undefined;
  for (const [key, entry] of Object.entries(record)) {
    let next: unknown;
    if (NUMERIC_FIELDS.has(key) && typeof entry === "string") {
      const number = probabilityValue(entry);
      next = Number.isFinite(number) ? number : null;
    } else {
      next = decode(entry);
    }
    if (next !== entry) {
      decoded ??= { ...record };
      decoded[key] = next;
    }
  }
  return decoded ?? value;
}

/** A valid numeric feed keeps its objects; decimal text is decoded once. */
export function normalizeFeedNumbers(page: FeedResponse): FeedResponse {
  return decode(page) as FeedResponse;
}
