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
 * still draws as drama. A short ladder of fixed steps does not: the axis holds still
 * for weeks and changes only when the shape of the race genuinely changes, and the
 * labels state the top so the reader can always see which rung they are on. P4's
 * target is the amplification, and the ladder is the answer to it, not an exception
 * to it.
 *
 * ### #4374: the ladder's own widest gap was a cliff, for the third time
 *
 * A ladder fixes #2451 only where its rungs are close enough together that the rung
 * below is a real option. Where two rungs are far apart, the leader lands near the
 * BOTTOM of the taller one and the field draws small again — #2451's defect, arrived
 * at by the ladder rather than in spite of it. #3032 found this at `0.5 → 1` (a 2×
 * gap: Alcaraz at 44.5% wanted 51.2%, got the full axis, drew in the bottom half)
 * and closed it by adding `0.75`.
 *
 * `0.1 → 0.25` was a **2.5× gap, the widest in the ladder**, and it sat exactly where
 * multi-runner fields live. A leader at 8.69% used 86.9% of the plot; at 8.70% it
 * used 34.8% — a 0.01pp move halving every line on the chart with nothing changing
 * in the race. The live golf field (leader 12.22%) sat in that hole and drew at 48.9%.
 * (#4374's table puts that edge one hundredth higher; the measured boundary is
 * 8.69/8.70, and the defect is the one the issue describes.)
 *
 * `0.15` closes it, by the same reasoning and to the same shape as #3032: the step
 * ratio drops from 2.5× to 1.5×, matching the ladder's tightest existing step, and
 * the golf field draws at 81.5%. Nothing outside a leader of 8.70–13.04% moves — the
 * change is monotone and can only make a field taller, never shorter.
 *
 * The next-widest gap is now `0.25 → 0.5` at 2×. That is the same shape again and is
 * NOT fixed here — it has no filed specimen, and widening this ship to chase it would
 * move the men's-board case that #2451 and #3032 both tuned deliberately.
 */

/** The only rungs an axis top may land on. `0.15` is #4374's; `0.75` is #3032's. */
export const CEILING_STEPS = [0.1, 0.15, 0.25, 0.5, 0.75, 1] as const;

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
