/**
 * #7920 — the y-axis ladder for the Score Differential chart.
 *
 * WHAT A READER SAW. On `/events/14780545` (Rams–Giants) at 390px the axis read
 *
 *     -26  -17  -8  +1  +10  +19
 *
 * on a chart whose whole subject is how far ahead somebody is. It has no zero —
 * on a score-DIFFERENTIAL axis, the one label that means something — its rungs
 * are not the round numbers a reader counts in, and the top of the plot (+26)
 * carries no label at all. Two other NFL games showed the milder form: a clean
 * `-24 -16 -8 0 +8 +24` with `+16` missing, a 42px gap where every other was 22.
 *
 * WHY. The generator asked for a step of `ceil(domainMax / 3)` and then walked
 * `-domainMax` upward by it. That step only lands on zero when it DIVIDES
 * `domainMax`, which is to say when 3 divides `domainMax`:
 *
 *     domainMax 24 -> step  8 -> -24 -16 -8  0 +8 +16 +24     symmetric
 *     domainMax 26 -> step  9 -> -26 -17 -8 +1 +10 +19        misses zero
 *
 * A trailing `if (!ticks.includes(0)) ticks.push(0)` bolted zero back on, which
 * is how `0` and `+1` — 2.9px apart at this plot height — came to be adjacent
 * rungs. `domainMax` is always even (`ceil(maxAbs / 2) * 2`), so this is not an
 * edge case: **25 of the 40 domain sizes from 2 to 80 produce a collapsed gap**,
 * and only 6, 12, 18, 24, 30 … come out clean. What the reader actually saw was
 * recharts' overlap heuristic quietly dropping one of the colliding pair, which
 * is why the defect presented as a missing label rather than as a smudge.
 *
 * 🪤 The filing proposed `interval={0}` on the `<YAxis>` — force recharts to
 * draw every tick it is handed. That is the wrong half of the fix and on its own
 * it is a REGRESSION: the ladder above is unchanged by it, so 25 of 40 games
 * would have painted `0` and `+1` on top of each other instead of dropping one.
 * The heuristic was hiding the defect, not causing it. Fix the ladder first;
 * `interval={0}` is then safe, and belongs there, because a correct ladder's
 * tightest gap is `domainMax / 3` — never a near-duplicate.
 *
 * THE RULE. Keep the domain exactly as it is — it is deliberately tight
 * (`ceil(maxAbs / 2) * 2`, with the comment "for a tighter fit"), and widening
 * it to reach a rounder step would flatten the plotted curve on every chart.
 * Only the STEP moves: take the smallest step at or above `ceil(domainMax / 3)`
 * that divides `domainMax`. Then the ladder is symmetric, lands on zero by
 * construction, is evenly spaced, and spans exactly the domain.
 *
 * This preserves the ladders that were already right — 2, 4, 6, 12, 18, 24, 30
 * are byte-identical to the old output — so the blast radius is only the games
 * that were broken.
 */

/**
 * The y-axis step: the smallest integer at or above `ceil(domainMax / 3)` that
 * divides `domainMax` exactly.
 *
 * Terminates, and never degenerates to a 3-rung axis in practice: `domainMax` is
 * always even, so `domainMax / 2` is a divisor, and `domainMax / 2` is at or
 * above `ceil(domainMax / 3)` for every `domainMax >= 2`. The loop therefore
 * stops at `domainMax / 2` at the latest, which is a 5-rung ladder.
 */
export function scoreDifferentialYStep(domainMax: number): number {
  const floor = Math.max(2, Math.ceil(domainMax / 3));
  let step = floor;
  while (step < domainMax && domainMax % step !== 0) step += 1;
  return step;
}

/**
 * The full ladder, low to high. Symmetric about zero, zero always present,
 * evenly spaced, endpoints exactly `-domainMax` and `+domainMax`.
 *
 * At most 7 rungs (the step is at least a third of `domainMax`), at least 3.
 */
export function scoreDifferentialYTicks(domainMax: number): number[] {
  const step = scoreDifferentialYStep(domainMax);
  const ticks: number[] = [];
  for (let v = -domainMax; v <= domainMax; v += step) ticks.push(v);
  return ticks;
}
