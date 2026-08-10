/**
 * UX-P046 — the single home for "what percentage does this probability print".
 *
 * THE DEFECT. Every percentage on the site was `Math.round(p * 100)`, which
 * turns a small-but-real probability into a flat `0%`. `0%` does not mean
 * "unlikely"; to a reader it means **impossible** — and we print it over an
 * outcome a market is actively pricing as possible.
 *
 * Measured on production 2026-08-10 (`GET /api/feed`, 100 unique cards, 345
 * rendered outcome rows): 17 rows were nonzero yet printed `0%`, and one card —
 * "Who will Taylor Swift's bridesmaids be?", 12 outcomes priced 0.05%-0.35% —
 * printed `0%` on every single row while its own headline named a 64% favourite.
 * Eight ranked rows, every one reading `0%`. That card tells a reader nothing,
 * and what little it does say is false.
 *
 * THE RULE, stated once so it cannot drift: **rounding may never move a
 * probability across a boundary it is not on.** A value strictly inside (0, 1)
 * is neither impossible nor certain, so it must never print as `0%` or `100%`.
 * The bands are derived from the rounding RESULT rather than from hand-picked
 * thresholds, so the two ends cannot disagree and there is no constant to keep
 * in sync with the rounding it guards.
 *
 * This is a formatting decision over a number the backend published — the client
 * is not deriving or adjudicating anything (ruling 003).
 *
 * PURE: no I/O, no clock, no ambient state.
 */

/** Printed when a value is possible but rounds to nothing. */
export const BELOW_ONE_PERCENT = "<1%";
/** Printed when a value is uncertain but rounds to certainty. */
export const ABOVE_NINETY_NINE_PERCENT = ">99%";

/**
 * The percentage string for a probability in [0, 1].
 *
 * Exact `0` and exact `1` are printed plainly — those ARE the boundaries, and a
 * caller that wants to distinguish "no data" from "genuinely zero" does so
 * before calling (several already render an em dash for `0`, which is preserved).
 */
export function formatProbabilityPercent(prob: number): string {
  if (!Number.isFinite(prob)) return "—";

  const rounded = Math.round(prob * 100);

  // Strictly inside the interval, but rounding would claim a boundary.
  if (rounded <= 0 && prob > 0) return BELOW_ONE_PERCENT;
  if (rounded >= 100 && prob < 1) return ABOVE_NINETY_NINE_PERCENT;

  return `${rounded}%`;
}
