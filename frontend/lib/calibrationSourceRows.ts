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
 *
 * ── THE THIRD STATE: A POPULATION WITH ONLY ONE OUTCOME CLASS (#6211) ───────
 *
 * The same row came back, in the other direction. With the cohort toggle on,
 * `datagolf` published **36 outcomes and a 36.5pp ECE**, beside Kalshi's
 * 318,956 at 0.9pp, in the same table and the same columns, with no caveat.
 *
 * **Every one of those 36 outcomes is a winner.** All five published buckets,
 * no exceptions, confirmed by two independent payload fields (the `winners`
 * count, and `sum_sq_err`, which matches the all-won prediction to within 0.6%
 * in every bucket and is nowhere near the all-lost one). The losers exist —
 * 14,581 resolved rows survive every eligibility predicate at a plausible 16.7%
 * win rate — and are dropped on the read side, in a `deduped` CTE frozen under
 * ruling 009 / D45. Fixing that population is issue #6211 item 2 and is not
 * this module's to touch.
 *
 * What this module can decide is whether the resulting number is publishable as
 * a peer measurement, and it is not — **as a theorem rather than a judgement
 * about sample size.** When every outcome falls on one side, observed frequency
 * is 1 in every bucket (or 0 in every bucket), so
 *
 *     ECE = Σ nᵢ·|1 − p̄ᵢ| / N        (all won)
 *     ECE = Σ nᵢ·|0 − p̄ᵢ| / N        (all lost)
 *
 * is a function of the PRICES ALONE. Nothing about how the questions resolved
 * can move it, because they all resolved the same way. DataGolf's 36.5pp is the
 * average distance from a 0.44–0.83 price to certainty; it measures the
 * censoring and would read the same if the source were perfect or worthless.
 * That is why the gate is exact — `winners === n` or `winners === 0` — and not
 * a threshold: at 99% winners the figure is a real measurement with a skew, and
 * a tunable constant here would be a dial someone later turns until the row
 * goes away.
 *
 * This generalises `TestLoneClaimSymmetryGate` (D112,
 * `app/utils/resolution_authority.py`), which already states the doctrine —
 * *"THE PAIR IS ADMITTED TOGETHER OR NOT AT ALL … Admitting the loser-only
 * channel by itself does not widen the population, it BIASES it"* — but is
 * scoped to one ingest arm. DataGolf is the same defect in the winner
 * direction, at the curve's OUTPUT, where no gate was watching.
 *
 * ── WHY THE ROW IS STATED, NOT DROPPED (#6211 item 3) ───────────────────────
 *
 * Item 3 of the issue is explicit: *"Do not simply hide the row. The 36.5pp is
 * currently the only visible alarm for a censored population; suppressing it
 * behind a min-sample floor and calling it done would delete the alarm and keep
 * the defect."*
 *
 * So the row stays, the outcome COUNT stays — 36 is a real count, honestly
 * arrived at — and the three metric columns are replaced by the fact that
 * produced them. That is a louder alarm than 36.5pp was, not a quieter one: a
 * reader could read 36.5pp as "DataGolf is badly calibrated", which is a claim
 * we cannot support about a named third party. "All 36 outcomes won" is a claim
 * about our own population, which is the true one.
 *
 * Same grammar as the `no-cohort-data` cell above it: the fact, and nothing
 * written to satisfy a reviewer (notice 34 / D102).
 */

/**
 * Whether a row carries a real measurement, an explicit absence, or a
 * population that cannot produce a measurement (#6211).
 */
export type SourceRowState = "measured" | "no-cohort-data" | "censored";

/**
 * The part of a pooled bucket the censoring verdict reads.
 *
 * Structurally typed on the two fields it needs rather than importing
 * `AggBucket`, so the page hands over exactly what `aggregateBuckets` already
 * returns and a test can state a two-field literal without inventing a
 * midpoint, a CI or an error term it is not asserting anything about.
 */
export interface SourceRowBucket {
  n: number;
  winners: number;
}

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
  /**
   * The provider's pooled buckets for the active cohort — the same
   * `aggregateBuckets(...)` array the metrics above were computed from.
   *
   * REQUIRED, deliberately. The censoring verdict is not computable without
   * it, and an optional field would mean a caller that forgot the wiring kept
   * publishing censored rows as measurements with every test still green —
   * the exact failure mode #6211 is. Required makes the compiler the guard: a
   * call site that omits it cannot build.
   */
  buckets: readonly SourceRowBucket[];
}

/** What the pooled buckets say about whether this row can be a measurement. */
export interface CensoringVerdict {
  /** Outcomes pooled across the buckets. */
  n: number;
  /** Of those, the ones that won. */
  winners: number;
  /**
   * True when every pooled outcome fell on the same side, so the metrics over
   * them are a function of the prices alone. See the module header.
   */
  censored: boolean;
}

/**
 * Pool the buckets and decide whether the population has two sides in it.
 *
 * Exact, not a threshold, and the module header says why: one-sidedness makes
 * the metric price-determined as a matter of arithmetic, whereas 99%-one-sided
 * is a real measurement of a skewed population.
 *
 * Non-finite and negative bucket fields are floored to 0, and `winners` is
 * clamped to its own bucket's `n`. A bucket claiming more winners than
 * outcomes is corrupt, and the clamp makes it read as all-winners — censored,
 * withheld from the ranking. That is the fail-closed direction: the cost of
 * being wrong is a row that states its population instead of publishing a
 * number, which is recoverable; the other direction publishes the lie.
 */
export function censoringVerdict(
  buckets: readonly SourceRowBucket[] | null | undefined
): CensoringVerdict {
  let n = 0;
  let winners = 0;
  for (const b of buckets ?? []) {
    if (!b) continue;
    const bn = Number.isFinite(b.n) && b.n > 0 ? b.n : 0;
    const bw = Number.isFinite(b.winners) && b.winners > 0 ? Math.min(b.winners, bn) : 0;
    n += bn;
    winners += bw;
  }
  // `n > 0` first: an empty bucket list is not a censored population, it is no
  // population, and that case is already `no-cohort-data`.
  return { n, winners, censored: n > 0 && (winners === n || winners === 0) };
}

/**
 * The one sentence a censored population is stated in, wherever it is stated.
 *
 * #7411. The verdict above shipped with #6211 wired to the Source Comparison
 * table alone, and By Source went on publishing DataGolf's 36.5pp three
 * thousand pixels below the row that refuses it. Fixing that gives the page a
 * SECOND place to word this, and two places wording one fact differently is
 * how a page starts disagreeing with itself again — the defect one layer up.
 *
 * So the sentence is a function, not a string literal copied to the second
 * call site. `SourceComparisonRow` and the By Source panels both render THIS,
 * and `panelCensoringMatchesTheRow7411` asserts they are byte-identical for
 * the same population, which makes disagreement unrepresentable rather than
 * merely discouraged (the module's own pairing-assertion discipline, UX-P075:
 * a ban is satisfied by deleting the word, a pairing is not).
 *
 * Both directions are named because both are censored by the same arithmetic —
 * an all-losers population's error is as price-determined as an all-winners
 * one's — and `censoringVerdict` already returns `censored` for each.
 */
export function censoredPopulationText(n: number, winners: number | null): string {
  return winners === 0
    ? `All ${n.toLocaleString()} lost — no wins to measure against.`
    : `All ${n.toLocaleString()} won — no losses to measure against.`;
}

/** A row as the page should render it. */
export interface SourceRow {
  provider: string;
  label: string;
  sources: string[];
  n: number;
  state: SourceRowState;
  /**
   * Winners pooled across the cohort's buckets, so the censored cell can say
   * WHICH side the population fell on without recomputing it. `null` when
   * there are no buckets to pool.
   */
  winners: number | null;
  /**
   * `null` on any row that is not `measured` — the empty reduction's `0`, and
   * the censored population's price-determined figure, never reach a
   * formatter. A caller that renders these without a null check gets
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
function stateOf(n: number, buckets: readonly SourceRowBucket[] | undefined): SourceRowState {
  if (!(Number.isFinite(n) && n > 0)) return "no-cohort-data";
  // Absence beats censoring: a row with no outcomes in the cohort is withheld,
  // not one-sided, and `withheldSourcesNote`'s remedy is the true one for it.
  return censoringVerdict(buckets).censored ? "censored" : "measured";
}

/**
 * Judge each row, then order them: measured rows by ECE ascending, then every
 * unmeasured row, alphabetically by label so the tail is stable.
 *
 * Stable tail ordering matters because a `no-cohort-data` row has no metric to
 * break ties with, and an unstable tail would make the table's row order depend
 * on the payload's source ordering — a difference a reader would read as a
 * change in the data.
 *
 * A `censored` row joins that same tail, for the same reason and one more.
 * "Sorted by ECE, lower is better" makes POSITION a published claim, so ranking
 * a price-determined figure publishes a verdict on a named third party that our
 * population cannot support — and DataGolf's 36.5pp would have taken LAST
 * place, which reads as "the worst source we carry" just as surely as the old
 * fabricated 0.0 read as the best. Both directions are the same error: a number
 * that is not a measurement occupying a rank.
 */
export function orderSourceRows(
  rows: readonly SourceRowInput[] | null | undefined
): SourceRow[] {
  if (!rows || !rows.length) return [];

  const judged: SourceRow[] = rows
    .filter(r => r && Array.isArray(r.sources))
    .map(r => {
      const verdict = censoringVerdict(r.buckets);
      const state = stateOf(r.n, r.buckets);
      const measured = state === "measured";
      const keep = (v: number) =>
        measured && typeof v === "number" && Number.isFinite(v) ? v : null;
      return {
        provider: r.provider,
        label: r.label,
        sources: [...r.sources],
        n: Number.isFinite(r.n) && r.n > 0 ? r.n : 0,
        state,
        winners: verdict.n > 0 ? verdict.winners : null,
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
 * The rows withheld from the ranking because their population has one side
 * (#6211). Deliberately NOT folded into `sourceRowsExcludedFromRollup`.
 *
 * Both sets leave the ordering, so folding them looks like a tidy-up. It would
 * make `withheldSourcesNote` say of DataGolf that it "has no outcomes in this
 * cohort … use the toggle to measure it" — and with the toggle already ON, that
 * sentence is false twice over: there are 36 outcomes, and the named remedy is
 * the control the reader just used. The two absences are different absences,
 * which is the distinction this whole module exists to keep (see the header on
 * why the `n === 0` row is stated rather than dropped). Same names, same
 * derivation, different sentence.
 */
export function censoredSourceRows(rows: readonly SourceRow[]): SourceRow[] {
  return rows.filter(r => r.state === "censored");
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

/**
 * By Source's caption — the one sentence that stays in the page body.
 *
 * WHY IT IS DERIVED RATHER THAN WRITTEN (#7446)
 *
 * It used to be the constant "One panel per data provider, all on the same
 * 0–100% axis." #4340 moved every other sentence in that section one click away
 * into the `How these panels are drawn` fold — correctly, under notice 34 — and
 * `withheldSourcesNote` went with them. What survived in plain view was a
 * UNIVERSAL whose only exception now sat behind a summary the reader has to
 * open. Measured on production 2026-09-20: the default cohort drew THREE panels
 * under a sentence promising one per provider, DataGolf having been emptied by
 * the cohort, and the sentence naming it was folded.
 *
 * Neither half of that was the defect. `buildProviderPanels` is right to drop a
 * 0-outcome provider (there is no curve to draw) and the note is right to be
 * folded. The caption is the piece that was never updated to match, which is
 * the failure mode this module's header already describes in the other
 * direction: an absence and a claim have to move together.
 *
 * Read off `sourceRowsExcludedFromRollup` — the SAME derivation the note and
 * the section's `data-withheld-sources` attribute use — so the caption is
 * structurally incapable of promising a panel the section does not draw. The
 * censored rows are deliberately NOT consulted: a censored provider still gets
 * a panel (#7411), so its caption promise is kept.
 *
 * It states no count, names no provider and adds no caveat. Notice 34 keeps
 * coverage and limitation out of the page body, and the fold below already
 * carries who and why; this sentence only has to stop being false.
 */
export function bySourceCaption(rows: readonly SourceRow[]): string {
  const subject = sourceRowsExcludedFromRollup(rows).length
    ? "One panel per data provider with outcomes in this cohort"
    : "One panel per data provider";
  return (
    `${subject}, all on the same 0–100% axis. Tap any point for example ` +
    `outcomes, or a provider tab for the full-width view.`
  );
}
