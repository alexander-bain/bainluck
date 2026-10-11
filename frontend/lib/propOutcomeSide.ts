/**
 * propOutcomeSide — which side of a line an outcome label names.
 *
 * A pure label parser, split out of `propResolution.ts` (#10809) so a surface
 * that reads the side but never states a verdict (the All questions catalog)
 * does not import the grading module. `propResolution` re-exports it; the
 * rule and its tests are unchanged.
 *
 * PURE — no imports, no I/O.
 */

/** Which side of the line an outcome label names, in over-probability space. */
export type PropOutcomeSide = "over" | "under" | "unreadable";

/** Kalshi's inclusive ladder rung: "Freddie Freeman: 3+", "Willi Castro: 2+". */
const RUNG_RE = /\d+\s*\+/;

/**
 * Place an outcome label on the over axis.
 *
 * Three shapes cover 586 of 587 production rows:
 *   - Polymarket O/U legs: "Over" / "Under"
 *   - Polymarket binary legs: "Yes" / "No"
 *   - Kalshi rungs: "<Player>: N+" — inclusive, and therefore the over side
 */
export function propOutcomeSide(outcomeName?: string | null): PropOutcomeSide {
  const o = (outcomeName || "").trim().toLowerCase();
  if (!o) return "unreadable";
  if (o === "over" || o === "yes") return "over";
  if (o === "under" || o === "no") return "under";
  if (RUNG_RE.test(o)) return "over";
  return "unreadable";
}
