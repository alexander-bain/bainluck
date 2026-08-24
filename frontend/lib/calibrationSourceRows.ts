/**
 * Source Comparison row ordering, and the n=0 state that used to be a 0.
 *
 * WHY THIS EXISTS (UX-P128, routed from Alex).
 *
 * `/calibration` rendered a `datagolf` row reading **0 outcomes · 0.0pp ECE ·
 * 0.0pp MCE · 0.0000 Brier**, in green, **sorted to the top of a table whose
 * own subhead says "sorted by ECE … Lower is better."** The page therefore
 * presented its worst-calibrated source as its best, with a number nobody
 * measured.
 *
 * Every one of those zeroes is an empty reduction's identity element, not a
 * measurement:
 *
 *   - `ece([])`   → `0`  (`totalN` is 0, the guard returns 0)
 *   - `mce([])`   → `0`  (`cal.length` is 0, the guard returns 0)
 *   - `brierScore` → `0`  (`n > 0 ? sq / n : 0`)
 *
 * Each guard is individually correct — a metric over nothing has no value, and
 * `0` is the conventional neutral return. They only become a lie at the point
 * of RENDER, where `(0).toFixed(1)` is indistinguishable from a source that was
 * measured and found perfect. This module is that point of render, moved into
 * one tested place.
 *
 * ── WHY THE ROW EXISTS AT ALL, RATHER THAN BEING DROPPED ────────────────────
 *
 * `buildSourcePanels` and `buildProviderPanels` already solve their half of
 * this by DROPPING `n === 0`, and both say why: *"an empty panel asserts 'we
 * measured this provider and found nothing', which is not what it means."*
 * That is right for a curve — there is no shape to draw.
 *
 * It is the wrong answer for the table, because the two absences are not the
 * same absence:
 *
 *   - A provider the payload never published is absent because we have no
 *     data. Dropping it is honest.
 *   - `datagolf` published **171 outcomes across 9 buckets with a server ECE of
 *     11.88pp**. It is empty here only because the DEFAULT COHORT excludes it —
 *     all 171 rows carry `price_moved: false`, and the default cohort is
 *     `price_moved !== false`. The data exists and the toggle above the table
 *     brings it back.
 *
 * Dropping the second case silently would leave the Sources KPI saying 4 while
 * the table showed 3, and would hide a source the reader can see with one
 * click. So the row stays and states its own emptiness. **Nothing is better
 * than a number we made up; a stated absence is better than either.**
 *
 * ── EXCLUDED FROM THE ORDERING, WHICH IS THE ROLLUP THAT GETS FLATTERED ─────
 *
 * The Combined row is n-weighted off pooled buckets, so a 0-outcome source
 * already contributes exactly nothing to it — that one was never flattered, and
 * `sourceRowsExcludedFromRollup` exists so a test can keep saying so.
 *
 * The rollup that WAS flattered is the ordering. "Sorted by ECE, lower is
 * better" makes a row's POSITION a published claim, and a fabricated 0.0
 * collected first place. Rows with no cohort data are therefore ordered after
 * every measured row rather than by a metric they do not have. They are not
 * ranked, because they were not measured.
 *
 * Ruling 003 is untouched: nothing here derives a calibration number. It
 * decides which numbers are real and where the unreal ones stop being printed.
 */

/** Whether a row carries a real measurement or an explicit absence. */
export type SourceRowState = "measured" | "no-cohort-data";

/** A row as the page computes it, before this module judges it. */
export interface SourceRowInput {
  provider: string;
  label: string;
  sources: string[];
  /** Outcomes behind this provider IN THE ACTIVE COHORT. */
  n: number;
  /** Metrics over the cohort's buckets. Meaningless when `n` is 0. */
  ece: number;
  mce: number;
  brier: number;
}

/** A row as the page should render it. */
export interface SourceRow {
  provider: string;
  label: string;
  sources: string[];
  n: number;
  state: SourceRowState;
  /**
   * `null` on a `no-cohort-data` row — the empty reduction's `0` never reaches
   * a formatter. A caller that renders these without a null check gets
   * `Cannot read properties of null`, which is the point: the failure is loud
   * at the call site rather than silent on the page.
   */
  ece: number | null;
  mce: number | null;
  brier: number | null;
}

/**
 * A row is a measurement only when outcomes stand behind it.
 *
 * `n`, not `Number.isFinite(ece)`, for the same reason `buildSourcePanels`
 * drops on `n` rather than `buckets.length`: the metric guards return a finite
 * `0` on empty input, so the metric can never report its own absence. Only the
 * count can.
 */
function stateOf(n: number): SourceRowState {
  return Number.isFinite(n) && n > 0 ? "measured" : "no-cohort-data";
}

/**
 * Judge each row, then order them: measured rows by ECE ascending, then every
 * unmeasured row, alphabetically by label so the tail is stable.
 *
 * Stable tail ordering matters because a `no-cohort-data` row has no metric to
 * break ties with, and an unstable tail would make the table's row order depend
 * on the payload's source ordering — a difference a reader would read as a
 * change in the data.
 */
export function orderSourceRows(
  rows: readonly SourceRowInput[] | null | undefined
): SourceRow[] {
  if (!rows || !rows.length) return [];

  const judged: SourceRow[] = rows
    .filter(r => r && Array.isArray(r.sources))
    .map(r => {
      const state = stateOf(r.n);
      const measured = state === "measured";
      const keep = (v: number) =>
        measured && typeof v === "number" && Number.isFinite(v) ? v : null;
      return {
        provider: r.provider,
        label: r.label,
        sources: [...r.sources],
        n: Number.isFinite(r.n) && r.n > 0 ? r.n : 0,
        state,
        ece: keep(r.ece),
        mce: keep(r.mce),
        brier: keep(r.brier),
      };
    });

  return judged.sort((a, b) => {
    const aMeasured = a.state === "measured";
    const bMeasured = b.state === "measured";
    // Unmeasured rows leave the ranking entirely rather than winning it.
    if (aMeasured !== bMeasured) return aMeasured ? -1 : 1;
    if (!aMeasured) return a.label.localeCompare(b.label);
    return (a.ece as number) - (b.ece as number) || a.label.localeCompare(b.label);
  });
}

/**
 * The providers withheld from the cohort, for the sentence that names them.
 *
 * Derived from the SAME rows the table renders, never from a second condition
 * that has to be kept in step with them — the pairing discipline this page
 * keeps re-learning (`shapeBreakdownNote`'s header carries the incident).
 */
export function sourceRowsExcludedFromRollup(
  rows: readonly SourceRow[]
): SourceRow[] {
  return rows.filter(r => r.state === "no-cohort-data");
}

/**
 * The sentence By Source owes when the cohort empties a provider the payload
 * did publish.
 *
 * By Source drops those panels — correctly, there is no curve to draw — but a
 * panel that vanishes with no explanation reads as "this source does not
 * exist", which is the same deception as the 0.0pp row in the other direction.
 * Returns `null` when nothing was withheld, so the page renders no sentence
 * rather than a sentence about an empty set.
 *
 * The remedy is NAMED (the toggle) because an absence a reader cannot act on is
 * just a smaller mystery.
 */
export function withheldSourcesNote(
  rows: readonly SourceRow[],
  toggleLabel: string
): string | null {
  const withheld = sourceRowsExcludedFromRollup(rows);
  if (!withheld.length) return null;
  const names = withheld.map(r => r.label).join(", ");
  const isAre = withheld.length === 1 ? "has" : "have";
  const itThey = withheld.length === 1 ? "its" : "their";
  return (
    `${names} ${isAre} no outcomes in this cohort, so ${itThey} ` +
    `${withheld.length === 1 ? "panel is" : "panels are"} not drawn here and ` +
    `${withheld.length === 1 ? "it is" : "they are"} not ranked in Source ` +
    `Comparison above. Use “${toggleLabel}” to measure ${withheld.length === 1 ? "it" : "them"}.`
  );
}
