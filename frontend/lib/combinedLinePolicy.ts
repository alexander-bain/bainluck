import type { FuturesOutcomeHistory } from "./types";

/**
 * #8158 — WHETHER ADDING A BOARD'S OUTCOMES UP PRODUCES A PROBABILITY AT ALL,
 * and the "Combined" line that may only be drawn when it does.
 *
 * ═══ THE DEFECT THIS EXISTS FOR ═══
 *
 * `FuturesChart` built the combined line as `Math.min(1, sum)` over the rows the
 * reader had on screen. On production market **56775596** — *"Las Vegas: Team
 * Specials"*, ten independent Kalshi props — the served field measured
 * 2026-09-22 reads:
 *
 *   | outcome | p |
 *   |---|---|
 *   | Brock Bowers 3+ touchdowns in a single game | 0.940 |
 *   | Fernando Mendoza 300+ passing yards in a single game | 0.640 |
 *   | Mike Washington Jr. 500+ rushing yards | 0.520 |
 *   | …seven more | … |
 *   | **served field total** | **3.72** |
 *
 * The chart's default top-three selection alone sums to **2.10**, and native
 * measured the same board's phone payload at **584 of 584 points clamped to
 * exactly 100**, with **20 distinct values collapsed to 1**. Ticking "Combined"
 * therefore drew a dead-flat dashed line pinned to the top of the plot.
 *
 * That is the worst of the available failures. The sum of independent binaries is
 * meaningless (gotcha #23), and the clamp does not report the meaninglessness — it
 * **launders it into a confident certainty**. An unclamped 210% line at least reads
 * as broken; a flat 100% reads as *"these three together are a lock"*, a statement
 * the market never made.
 *
 * ═══ WHY THE FIELD'S OWN ARITHMETIC, AND NOT `mutually_exclusive` ═══
 *
 * The database has an exclusivity flag and it is fully populated, so the obvious
 * fix looks like "serve the flag". Native censused it 2026-09-22 over EVERY open
 * market with ≥3 priced outcomes — 11,095 of them, complete keyset walk, raw rows at
 * `artifacts/native-303/8158-ceiling-census.json` — and **the flag is informative but
 * nowhere near sufficient**:
 *
 *   | `mutually_exclusive` | markets | median sum | p95 | worst | above 1.3 |
 *   |---|---|---|---|---|---|
 *   | `true`  | 4,764 | 1.014 | 2.500 | 21.64 | 646 (13.6%) |
 *   | `false` | 6,331 | 3.610 | 12.310 | 179.87 | 5,576 (88.1%) |
 *
 * 646 flagged-exclusive markets still cannot be summed, in two populations: cumulative
 * threshold ladders whose rungs contain one another, and large fields whose per-outcome
 * YES prices never normalise ("Maxwell Award Winner", 63 outcomes, 20.39). So the
 * arithmetic is not a stand-in for the flag pending a producer change — it is right
 * where the flag is wrong, and a later ship gating on a served flag would reintroduce
 * the lie on all 646. The timeline payload does not serve the flag, and it should not
 * start.
 *
 * ═══ WHAT THIS DELIBERATELY DOES NOT CATCH, AND WHAT IT COSTS ═══
 *
 * 755 non-exclusive markets sum UNDER the ceiling and keep their line. Two independent
 * props at 0.40 and 0.45 add to 0.85 — still not a probability, and arithmetically
 * indistinguishable from an exclusive field truncated to its top rows. Arithmetic
 * cannot separate those two, so the boundary is drawn where the sum stops being able
 * to be one at all.
 *
 * 🪤 The cost is not zero. Across native's census 6,222 markets (56.1%) lose the
 * control; for 5,877 of them (94.5%) the line was already a flat clamped 100%, so the
 * refusal is purely the repair, but 345 were drawing a moving line under 100% on
 * prices inflated several-fold. A plausible wrong number is the worse failure of the
 * two, which is why those are refused too — a judgement, not a free win.
 */

/**
 * The largest served-field total that can still be one question's alternatives.
 *
 * **Principled, not fitted.** One question's alternatives sum to 1 by construction;
 * the only legitimate excess is overround, and #2582 photographed every two-way
 * market on one UFC card summing to 101–102%. 1.3 allows thirty points of vig and
 * pricing noise on a well-formed field — clear of the flagged-exclusive median of
 * 1.014, far below the non-exclusive median of 3.610. Three exclusive production
 * controls measured 2026-09-22 all keep their line: *"Democratic nomination odds
 * leader on October 31?"* 1.000, *"Lowest Mississippi level at St. Louis by November
 * 30?"* 1.077, *"B.C. Conservative Party Leadership Election Winner"* 1.275.
 *
 * 🪤 **It is NOT a natural boundary, and the census says so** — sweeping the ceiling
 * over all 11,095 markets produces no cliff, so "nothing measured lands near it"
 * would be false:
 *
 *   | ceiling | refused | already flat | working lines lost |
 *   |---|---|---|---|
 *   | 1.0 | 8,638 | 6,914 | 1,724 |
 *   | 1.2 | 6,500 | 6,013 | 487 |
 *   | **1.3** | **6,222** | **5,877** | **345** |
 *   | 1.5 | 5,903 | 5,670 | 233 |
 *   | 3.0 | 3,988 | 3,941 | 47 |
 *
 * Raising it buys a better ratio and leaves more flat lines unfixed; lowering it
 * fixes more and costs more working ones. The table is here so the next person to
 * change it argues with the trade rather than rediscovering it. It matches the
 * native half (`EvolutionCombinedLinePolicy.singleQuestionSumCeiling`) on purpose —
 * the same board must not answer differently on web and phone.
 */
export const SINGLE_QUESTION_SUM_CEILING = 1.3;

/**
 * A series' current value: its last point that carries a price.
 *
 * Deliberately NOT `history[history.length - 1]?.probability ?? 0`, the idiom
 * `EvolutionView.lastProbOf` uses for sort order. A trailing null is a reading we
 * do not have, and reading it as zero would pull a field's total down — for a sort
 * that only reorders rows; here it would silently talk a non-exclusive field under
 * the ceiling and hand back the line this module exists to refuse.
 */
export function lastServedProbability(outcome: FuturesOutcomeHistory): number | null {
  for (let i = outcome.history.length - 1; i >= 0; i -= 1) {
    const p = outcome.history[i]?.probability;
    if (p !== null && p !== undefined) return p;
  }
  return null;
}

/**
 * Whether `servedOutcomes` are alternatives to ONE question.
 *
 * Measured over the WHOLE SERVED FIELD — not over the rows a reader's selection or
 * Top-N chip left on screen. This is the web half's own defect: the old line summed
 * `displayedOutcomes`, so narrowing the table changed what the "sum" claimed to be.
 * A card-level truth must not move because a reader narrowed the table.
 *
 * Truncation is safe in one direction only, and that is the direction every caller
 * truncates in: dropping rows or windowing by time can only REMOVE probability mass,
 * so it can lower a field under the ceiling but never lift one over it. A false "one
 * question" is today's behaviour; a false "not one question" would silently remove a
 * working line, and this cannot produce one.
 *
 * An unpriced field answers `true` — today's behaviour — because a chart with no
 * served probabilities has said nothing this can contradict. Two priced outcomes are
 * required before it will judge: one outcome cannot exceed the ceiling on its own, so
 * a single row could only ever return `true`, and reading that as a verdict would
 * dress a non-answer up as a measurement (gotcha #53).
 *
 * ═══ 🔴 WHO MAY CALL THIS: ONE MARKET'S FIELD, NEVER A UNION ═══
 *
 * Its whole premise is that the rows it is handed are one market's outcome list. On
 * `/api/futures/multi-history` — the cross-source union EvolutionView uses whenever a
 * Stage has more than one `market_ids` entry — they are not, and the sum is inflated
 * by rows that are the same contender priced twice. Measured 2026-09-22 on the NFL
 * league page's default Stage (`market_ids=40533,86832,129037`, "2027 Pro Football
 * Champion"), the union serves **44 rows for 32 teams** and totals **1.502**:
 *
 *     0.1176  Buffalo Bills        0.115  Buffalo
 *     0.0871  Seattle Seahawks     0.075  Seattle
 *     0.0462  Detroit Lions        0.035  Detroit
 *     …eleven teams doubled, one per naming convention per source…
 *
 * That field IS one question. Judged here it would read 1.502 and lose its line, and
 * the same is true of the NBA, MLB, NHL, NCAAF and MLS championship Stages. The
 * duplication is not detectable from the payload: dedupe by name fails ("Buffalo" is
 * not "Buffalo Bills" — a name is not an id), and `/api/futures/multi-history` serves
 * no per-outcome market id to group on. Scaling the ceiling by the number of
 * constituent markets was measured and rejected too — it forgives the NFL "Division"
 * Stage (16 markets, 8 genuinely different questions), which is exactly as unsummable
 * as a props board.
 *
 * So this function is called ONLY on the single-market path, and the union path keeps
 * today's behaviour until the payload can say which market a row came from (the
 * follow-up issue named in #8158). Refusing a line is cheap; refusing the right line
 * for the wrong reason on a marquee page is not.
 */
export function fieldIsOneQuestion(servedOutcomes: FuturesOutcomeHistory[]): boolean {
  const priced = servedOutcomes
    .map(lastServedProbability)
    .filter((p): p is number => p !== null);
  if (priced.length < 2) return true;
  return priced.reduce((a, b) => a + b, 0) <= SINGLE_QUESTION_SUM_CEILING;
}

/** One instant of the combined line: the forward-filled total at time `t`. */
export interface CombinedLinePoint {
  t: number;
  sum: number;
}

/**
 * The combined line's points for a selection, or `null` if there is nothing to draw.
 *
 * ⚠️ THIS DOES NOT JUDGE, AND THAT IS DELIBERATE — see `fieldIsOneQuestion`'s
 * "who may call this" note. It sums what it is given. The caller decides whether a
 * combined line means anything at all, because the caller is the only layer that
 * knows whether its outcome list is one market's field or several markets' union.
 *
 * The clamp lives HERE rather than at the call site because the clamp is the defect:
 * `Math.min(1, …)` is what converted a meaningless 2.10 into a confident 1.00, and a
 * number that can mislead a reader belongs somewhere a test can reach it. It is kept
 * for the case it was written for — on alternatives to one question a selection
 * genuinely cannot exceed certainty, so it only ever absorbs rounding and overround
 * there, a percent or two of vig rather than a factor of two.
 */
export function combinedLinePoints(
  displayedOutcomes: FuturesOutcomeHistory[],
): CombinedLinePoint[] | null {
  if (displayedOutcomes.length < 2) return null;

  const stamps = new Set<number>();
  for (const o of displayedOutcomes) {
    for (const p of o.history) {
      if (p.probability !== null) stamps.add(new Date(p.timestamp).getTime());
    }
  }
  const sortedStamps = Array.from(stamps).sort((a, b) => a - b);
  if (sortedStamps.length < 2) return null;

  // Pre-sort each outcome's real points once for a linear forward-fill walk.
  const series = displayedOutcomes.map((o) =>
    o.history
      .filter((p) => p.probability !== null)
      .map((p) => ({ t: new Date(p.timestamp).getTime(), v: p.probability as number }))
      .sort((a, b) => a.t - b.t),
  );
  const cursors = series.map(() => 0);
  const last = series.map(() => null as number | null);
  const pts: CombinedLinePoint[] = [];
  for (const t of sortedStamps) {
    let sum = 0;
    let anyKnown = false;
    series.forEach((pointsList, i) => {
      while (cursors[i] < pointsList.length && pointsList[cursors[i]].t <= t) {
        last[i] = pointsList[cursors[i]].v;
        cursors[i] += 1;
      }
      if (last[i] !== null) {
        sum += last[i] as number;
        anyKnown = true;
      }
    });
    if (anyKnown) pts.push({ t, sum: Math.min(1, sum) });
  }
  return pts.length >= 2 ? pts : null;
}
