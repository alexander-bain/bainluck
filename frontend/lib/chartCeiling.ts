/**
 * ═══ THE #2451 CEILING LADDER, IN ONE PLACE ═══
 *
 * Alex, on the TO WIN THE TITLE chart: *"renders three contender lines inside
 * roughly the bottom 15% of the plot area, with **no y-axis labels at all**.
 * Alcaraz 34.5%, Zverev 23.5%, Shelton 9.3% — all visually flat and
 * indistinguishable."* And the instruction: **"Fix the scale, do not smooth the
 * line."**
 *
 * That ruling shipped in `contenderChart.ts` for the tournament ContenderChart and
 * nowhere else, so the OTHER field chart — `FuturesChart`, which draws the golf hub,
 * the futures detail page and the event-concept winner field — kept the pre-#2451
 * axis and reproduced the identical defect four months later (#4259: the whole
 * 8-golfer contender field inside 9.57% of the plot height, leader at 12.22%, the
 * 25/50/75/100% gridlines labelling empty space).
 *
 * The ladder now lives here so there is ONE of it. `chartCeiling` (series-aware,
 * timeframe-aware) and `FuturesChart` (which has already reduced its series to a
 * single max) both step through `ceilingForMax`, so the two charts can never drift
 * onto different ladders again.
 *
 * ### Zero stays. The top moves.
 *
 * The classic chart lie is a truncated baseline — cropping the bottom to magnify a
 * wiggle. That is not what this does: the axis is ALWAYS anchored at 0, so a line's
 * height stays proportional to the probability and a player at 9% is drawn at 9% of
 * the ceiling, not floated up off a fake floor.
 *
 * ### Coarse on purpose — this is what keeps it inside P4
 *
 * `docs/chart-design-spec.md` P4 forbids "drama-zoom": *auto-zooming the Y-axis to
 * amplify small moves*, a D1 enticement pattern. A CONTINUOUS fit-to-max would be
 * exactly that — it rescales every time the leader moves a point, so a flat week
 * still draws as drama. Five fixed steps do not: the axis holds still for weeks and
 * changes only when the shape of the race genuinely changes, and the labels state
 * the top so the reader can always see which rung they are on. P4's target is the
 * amplification, and the ladder is the answer to it, not an exception to it.
 */

/** The only rungs an axis top may land on. */
export const CEILING_STEPS = [0.1, 0.25, 0.5, 0.75, 1] as const;

/** Room above the leader, so the top line is not welded to the frame. */
export const CEILING_HEADROOM = 1.15;

/**
 * The axis top for a field whose highest drawn probability is `max` (0–1).
 *
 * Always one of `CEILING_STEPS`, always ≥ the leader plus headroom, and 1 when
 * nothing smaller fits — so a two-sided market, or any field with a line above 87%,
 * keeps the plain 0–100% axis it has today.
 */
export function ceilingForMax(max: number): number {
  if (!Number.isFinite(max) || max <= 0) return 1;
  const wanted = max * CEILING_HEADROOM;
  return CEILING_STEPS.find((step) => step >= wanted) ?? 1;
}
