/**
 * gradedPropPair — WHAT HIT prints ONE row per two-sided question (#8230).
 *
 * `/events/15316869` (Red Sox 2 – 3 Guardians, Final) at 390px, 2026-09-24: the
 * WHAT HIT board printed all 25 Over/Under questions twice — `Under 0.0 — hit`
 * over `Over 0.0 — miss` — 23 green chips and 24 red. A graded row prints the
 * actual value and a verdict and no probability, so the two legs of one question
 * carried one fact printed twice, and the board was half red by construction
 * whatever the script had said.
 *
 * THE SCRIPT needs both legs: `Under 94% / Over 6%` is two numbers. WHAT HIT is
 * "the pregame script, graded", and the script's claim about a two-sided question
 * is the side it favoured. So the row that survives is the leg with the HIGHER
 * pregame mark, and it prints that mark beside its verdict — `Under 94% · 0.0 —
 * hit`, and an upset reads `Over 60% · … — miss`. That is a result per question
 * ("62% → won"), not an accuracy score (notice 45).
 *
 * When the marks cannot name a favourite (either leg unmarked, or a dead 50/50),
 * the survivor is the leg that happened, printed with no number — the one fact
 * the pair had. When neither leg was graded, one leg stands alone with no number,
 * so the "grading unavailable" chip is said once rather than twice and no
 * pregame percent sits beside a verdict that does not exist.
 *
 * NARROW, both directions (gotcha #43):
 *   - only a two-leg family whose legs are exactly Over/Under or Yes/No;
 *   - only when the verdicts are consistent with one question — one hit and one
 *     miss, both push, or both ungraded. Two hits (or two misses) on one
 *     question is a data defect, and collapsing it would hide it, so both rows
 *     stay on screen;
 *   - a ladder family (`1+`, `2+`, …) and a three-way winner are different
 *     questions per row and are never touched.
 *
 * PURE — no I/O, no React.
 */

export interface GradedPairLeg<K> {
  key: K;
  label: string;
  pregame_mark: number | null;
  graded_result?: "hit" | "miss" | "push" | null;
}

export interface GradedPairDecision<K> {
  /** The leg that is printed. */
  keep: K;
  /** The leg that is not. */
  drop: K;
  /** Whether the survivor prints its pregame mark — true only when the mark is
   *  the reason it was chosen AND there is a verdict for it to sit beside. */
  showMark: boolean;
}

const SIDE_PAIRS: ReadonlyArray<readonly [string, string]> = [
  ["over", "under"],
  ["yes", "no"],
];

function isTwoSided(a: string, b: string): boolean {
  const x = a.trim().toLowerCase();
  const y = b.trim().toLowerCase();
  return SIDE_PAIRS.some(([p, q]) => (x === p && y === q) || (x === q && y === p));
}

function consistentVerdicts(a: GradedPairLeg<unknown>, b: GradedPairLeg<unknown>): boolean {
  const ra = a.graded_result ?? null;
  const rb = b.graded_result ?? null;
  if (ra === null && rb === null) return true;
  if (ra === "push" && rb === "push") return true;
  return (ra === "hit" && rb === "miss") || (ra === "miss" && rb === "hit");
}

function finite(p: number | null | undefined): p is number {
  return typeof p === "number" && Number.isFinite(p);
}

export function gradedPairDecision<K>(
  legs: ReadonlyArray<GradedPairLeg<K>>,
): GradedPairDecision<K> | null {
  if (legs.length !== 2) return null;
  const [a, b] = legs;
  if (!isTwoSided(a.label, b.label)) return null;
  if (!consistentVerdicts(a, b)) return null;

  if (finite(a.pregame_mark) && finite(b.pregame_mark) && a.pregame_mark !== b.pregame_mark) {
    const [keep, drop] = a.pregame_mark > b.pregame_mark ? [a, b] : [b, a];
    return { keep: keep.key, drop: drop.key, showMark: keep.graded_result != null };
  }
  if (b.graded_result === "hit") return { keep: b.key, drop: a.key, showMark: false };
  return { keep: a.key, drop: b.key, showMark: false };
}
