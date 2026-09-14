import { renderedPercent } from "./renderedPercent";

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

/** Printed when there is no usable number. NOT a hyphen — see `formatProbability`. */
export const NO_READING = "—";

/**
 * A percentage split into the marker and the integer, for callers that cannot
 * take a finished string.
 *
 * #6064 — THE EVENT HERO COULD NOT CALL `formatProbabilityPercent`, SO IT DID
 * NOT CALL ANYTHING. Its two giant percents print the integer and the `%` as
 * SEPARATE spans (48px numeral, 18px sign) for layout, so `">99%"` is not a
 * drop-in: handed that string the hero would have rendered `>99%` at 48px with
 * a second `%` glued after it. The component therefore printed the bare
 * `renderedPercent` and the clamp never ran on the biggest element of the page
 * — a live underdog at 0.004 read `0%`, the exact "impossible" render UX-P046
 * exists to refuse, and 0.999 read `100%` over a game nobody had won.
 *
 * Splitting the value is the fix, NOT re-implementing the bands in the
 * component: `probabilityParts` is the one place the boundary rule lives and
 * `formatProbabilityPercent` is now composed from it, so a string caller and a
 * span caller cannot drift. The alternative — the hero stripping the `%` off
 * this module's output — would have made the marker rule depend on parsing a
 * sentence, which is the class of defect UX-P275 two functions below exists to
 * delete ("ask the string, not the number" is right for a PREDICATE and wrong
 * for a decomposition).
 */
export interface ProbabilityParts {
  /** `<` or `>` when rounding would claim a boundary the value is not on. */
  marker: "<" | ">" | null;
  /** The integer to print, or `NO_READING` when there is none. */
  digits: string;
}

const BELOW_ONE_PARTS: ProbabilityParts = { marker: "<", digits: "1" };
const ABOVE_NINETY_NINE_PARTS: ProbabilityParts = { marker: ">", digits: "99" };

/** The one place parts become a string, so the two forms cannot disagree. */
function joinParts({ marker, digits }: ProbabilityParts): string {
  if (digits === NO_READING) return NO_READING;
  return `${marker ?? ""}${digits}%`;
}

/**
 * Printed when a value is possible but rounds to nothing.
 *
 * DERIVED from the parts rather than written twice: these constants are what
 * several suites assert against, so a literal here could go on agreeing with a
 * test while disagreeing with what the hero draws.
 */
export const BELOW_ONE_PERCENT = joinParts(BELOW_ONE_PARTS);
/** Printed when a value is uncertain but rounds to certainty. */
export const ABOVE_NINETY_NINE_PERCENT = joinParts(ABOVE_NINETY_NINE_PARTS);

/**
 * The percentage string for a probability in [0, 1].
 *
 * Exact `0` and exact `1` are printed plainly — those ARE the boundaries, and a
 * caller that wants to distinguish "no data" from "genuinely zero" does so
 * before calling (several already render an em dash for `0`, which is preserved).
 */
/**
 * `rendered` overrides the INTEGER, not the rule.
 *
 * UX-P114: a card that prints two sides of one question decides both percents
 * together, or the two independently-correct numbers sum to 101 (see
 * `renderedDuelPercents` and `contracts/rendered_percent.json`). That decision is
 * made on the server and arrives on the payload, so callers that have it pass it
 * here rather than rounding a second time.
 *
 * The boundary rule above still runs on the PROBABILITY. A served 100 over a
 * probability of 0.996 is still `>99%`, because "rounding may never move a
 * probability across a boundary it is not on" is a claim about the value, not
 * about which arithmetic produced the integer. The two rules compose; neither
 * outranks the other by accident.
 *
 * ** IT IS AN OPTIONS OBJECT, AND THAT IS DELIBERATE. ** The first draft took a
 * bare second `number`, and `wire.map(formatProbabilityPercent)` — a real call in
 * this module's own test — silently handed it the ARRAY INDEX. Eight outcomes
 * that must print `<1%` printed `<1%, 1%, 2%, 3%…`, and only an existing
 * production-specimen assertion caught it. With an object, the point-free form is
 * a TYPE error instead of a wrong number, because `number` is not assignable to
 * it. The shape of the parameter is the guard.
 */
export interface ProbabilityFormatOptions {
  /** The card-level integer this surface has already decided to print. */
  rendered?: number | null;
}

export function probabilityParts(
  prob: number,
  options?: ProbabilityFormatOptions,
): ProbabilityParts {
  if (!Number.isFinite(prob)) return { marker: null, digits: NO_READING };

  const override = options?.rendered;
  // #3867: the rounding rule is `renderedPercent`'s, not a second copy of it.
  // This read `Math.round(prob * 100)` inline, which was the same rule until the
  // contract moved to scaling by 1000 — at which point an inline copy would have
  // printed 56 under a hero printing 57 for one probability. The non-null
  // assertion is safe behind the `Number.isFinite` guard directly above.
  const rounded =
    override != null && Number.isFinite(override)
      ? override
      : (renderedPercent(prob) as number);

  // Strictly inside the interval, but rounding would claim a boundary.
  if (rounded <= 0 && prob > 0) return BELOW_ONE_PARTS;
  if (rounded >= 100 && prob < 1) return ABOVE_NINETY_NINE_PARTS;

  return { marker: null, digits: `${rounded}` };
}

export function formatProbabilityPercent(
  prob: number,
  options?: ProbabilityFormatOptions,
): string {
  return joinParts(probabilityParts(prob, options));
}

/**
 * UX-P048 — the single home for "what UNIT is a movement value in".
 *
 * THE DEFECT. `movement` / `movement_24h` / `probability_change_24h` are all
 * FRACTIONS on the wire, exactly like `probability`. The backend's own prose
 * proves it in the same payload: an outcome carrying `movement: -0.07` ships
 * `reason: "The Odyssey moved down 7.0 points today"`.
 *
 * Seven of the eight renderers agreed and multiplied by 100. The Discover hero
 * did not — it printed `Math.abs(m).toFixed(1)` under a label reading "points".
 * Measured on production 2026-08-10 (`GET /api/feed?limit=60`, backend
 * `a4275e07`): of 21 futures cards carrying a leader movement, ALL 21 route to
 * that hero, 20 rendered nothing at all, and the single card that did render was
 * the feed's most dramatic mover — a 64.0-point swing to a new favourite — which
 * printed `↑ 0.6` above a tooltip asserting "Up 0.6 points in the last 24h".
 *
 * The same card contradicted itself on screen: the backend-written caption "The
 * Odyssey down 7.0 points today" sat directly above an empty `24h` delta slot,
 * because 0.07 failed a gate that was written as points and read as a fraction.
 *
 * THE RULE, stated once so it cannot drift: **a movement crosses into "points"
 * exactly once, here.** Callers pass the wire fraction and receive points; no
 * call site multiplies by 100 itself. Thresholds stay with the caller, because
 * "how big must a move be before this surface shows it" is a per-surface design
 * choice — but they are now expressed in POINTS, the unit their names claim.
 *
 * This is a formatting decision over a number the backend published — the client
 * is not deriving or adjudicating anything (ruling 003).
 *
 * PURE: no I/O, no clock, no ambient state.
 */

/** Wire fraction -> points. `null` for anything that is not a usable number. */
export function movementPoints(movement: number | null | undefined): number | null {
  if (movement == null || !Number.isFinite(movement)) return null;
  return movement * 100;
}

/**
 * The absolute size of a move, in points, rounded for display to `decimals`.
 *
 * Returns `null` when there is no usable movement, so a caller's `&&` chain
 * cannot leak a bare `0` into the DOM (see `RelatedFutures`, UX-P048 Item 2).
 */
export function formatMovementPoints(
  movement: number | null | undefined,
  decimals = 1,
): string | null {
  const pts = movementPoints(movement);
  if (pts == null) return null;
  return Math.abs(pts).toFixed(decimals);
}

/**
 * UX-P275 — does this movement PRINT as a move at `decimals`?
 *
 * THE DEFECT this exists to make unrepresentable. Seven renderers decided
 * "did it move?" by testing the WIRE FRACTION for exact zero (`m !== 0`) and
 * then printed the result rounded to one decimal. Those are two different
 * questions, so they disagree on everything in the open interval that is
 * nonzero yet rounds to nothing: a market that moved 0.0029 points passed the
 * gate and printed `-0.0%` inside a red "went down" pill. A no-change read as
 * an alarm, and which alarm depended only on the sign of a rounding residue.
 *
 * Measured on production 2026-09-02 (`GET /api/futures/1`, the "Last move"
 * column): of 22 outcomes carrying a change, **16 printed a coloured zero** —
 * 13 green `+0.0%` and 3 red `-0.0%`. Six rows in that column said something
 * true. `GET /api/feed?limit=50` carries 81 `movement` values, of which 41
 * render as a zero and 27 are EXACTLY zero.
 *
 * THE RULE: **ask the string, not the number.** The predicate is derived from
 * `formatMovementPoints` — the very function that produces the printed
 * magnitude — so the gate and the rendering cannot drift apart, whatever
 * `decimals` a surface chooses. This is the same construction UX-P046 uses two
 * functions above, where the bands come from the rounding RESULT rather than
 * from hand-picked thresholds "so the two ends cannot disagree".
 *
 * It is deliberately NOT a threshold constant. A constant would have to be
 * kept in sync with each caller's `decimals` by hand, which is the drift this
 * module exists to prevent.
 */
export function isRenderedMove(
  movement: number | null | undefined,
  decimals = 1,
): boolean {
  const printed = formatMovementPoints(movement, decimals);
  if (printed === null) return false;
  return Number.parseFloat(printed) !== 0;
}
