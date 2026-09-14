// CAL-P1217 — the accuracy page's coverage accounting, read from the census the
// serve path already attaches.
//
// WHAT THIS IS FOR
//
// Milestone 4 asks that the page explain which outcomes are included and which
// are excluded. The page already names individual filters (liquidity, the
// writer bar, esports bundles, voids), but those are a handful of sentences
// about a handful of rules, not an accounting: a reader cannot add them up and
// arrive anywhere, and the biggest exclusions were never among them.
//
// `calibration_coverage_census.coverage_bridge` IS the accounting. It is an
// ordered, first-match-wins PARTITION of the covered population — every
// resolved futures outcome that carried a usable price lands on exactly one
// rung, so the rungs sum back to the population by construction. The producer
// (`app.tasks.census_coverage_rungs`) counts it out of band; the serve path
// (`app.utils.calibration_coverage_consumer`) attaches it only after proving it
// describes the build being served. This module is the reader's half.
//
// THREE THINGS IT REFUSES TO DO
//
// 1. It never prints the payload's own `rule` strings. Those are written for an
//    auditor — "DataGolf recovery residual", "virtual question", "normalization
//    field" — and notice 34 bans exactly that prose from a reader's screen.
//    Every rung gets a short label here, in the client, or it is not shown.
//
// 2. It never renders a partial accounting. A rung the client cannot name, a
//    bridge that does not reconcile, an arithmetic that does not add up: each
//    returns `null` and the page shows nothing at all. Half an accounting is
//    worse than none, because a reader sums what they are given.
//
// 3. It never widens the scope of what it is counting. The bridge is over
//    FUTURES outcomes (Kalshi, Polymarket). The page's headline total also
//    contains sportsbook curve observations, which are a different unit and are
//    not on these rungs. The caller states that scope; this module keeps the
//    two numbers apart by never deriving one from the other.

export const COVERAGE_BRIDGE_SCHEMA = "calibration-coverage-bridge/v1";

/** The terminal rung: the covered outcomes that DO reach the curve. */
export const PLOTTED_RUNG = "plotted_on_curve";

/**
 * A short reader label for every rung the server can emit.
 *
 * Deliberately a CLOSED map, and deliberately the reason this module can refuse
 * to render. The server's rung set is a contract (`BRIDGE_RUNGS` in
 * `app/utils/calibration_coverage_bridge.py`, first-match-wins and documented
 * as "reordering is a contract change"). If it ever grows a rung, the honest
 * behaviour here is to stop showing the accounting until someone writes the
 * sentence a reader should see — not to print a raw key, and not to quietly
 * drop a bucket out of a total the reader is invited to add up.
 */
export const RUNG_LABELS: Readonly<Record<string, string>> = {
  [PLOTTED_RUNG]: "Counted on the curve above",
  market_result_unavailable: "Result could not be established, so the whole market was set aside",
  truth_source_missing: "Nothing independent recorded what happened",
  truth_ineligible_source: "The only record of what happened came from the price itself",
  question_ungraded: "No outcome in the question was ever marked the winner",
  malformed_or_unknown_truth: "The recorded result does not add up to a scoreable answer",
  phantom_liquidity: "Nobody ever bid or traded, so the price is not a forecast",
  opening_below_writer_bar: "The opening price was never discovered in real trading",
  structural_artifact: "The price is a known artifact of how the market was listed",
  field_incomplete: "Another outcome in the same group was excluded, so the group cannot sum to 100%",
  representative_not_selected: "A different row already represents this question",
};

export interface CoverageRungRow {
  key: string;
  label: string;
  outcomes: number;
}

export interface CoverageAccounting {
  /** Resolved futures outcomes carrying a usable price — the denominator. */
  covered: number;
  /** Of those, the ones plotted on the published curve. */
  plotted: number;
  /** `covered - plotted`, recomputed here rather than taken on trust. */
  excluded: number;
  /** Every exclusion rung that excluded at least one outcome, largest first. */
  rows: CoverageRungRow[];
  /**
   * Exclusion rungs measured at exactly zero.
   *
   * Kept as a count rather than dropped: a rule that fired zero times is a
   * checked zero, and the distinction between "measured none" and "not
   * measured" is the whole reason the census carries a `checked` flag.
   */
  emptyRules: number;
}

function isCount(value: unknown): value is number {
  return typeof value === "number" && Number.isInteger(value) && value >= 0;
}

function asRecord(value: unknown): Record<string, unknown> | null {
  return typeof value === "object" && value !== null && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : null;
}

/**
 * The accounting to show, or `null` to show nothing.
 *
 * `null` is the normal answer and the safe one. The census is walked out of
 * band, so for most of its life it is absent, behind the build, or explicitly
 * unavailable, and every one of those cases must leave the page exactly as it
 * was rather than print a zero.
 */
export function readCoverageAccounting(census: unknown): CoverageAccounting | null {
  const block = asRecord(census);
  if (!block || block.schema_version !== COVERAGE_BRIDGE_SCHEMA) return null;
  if (block.status === "unavailable") return null;

  // A diverging hinge means the bridge's own terminal rung and the population
  // query disagree about how many rows reached the curve. The census still
  // publishes both, on purpose — but a reader must never be handed a number two
  // independent counts cannot agree on.
  const invariants = asRecord(block.invariants);
  const violations = invariants?.violations;
  if (Array.isArray(violations) && violations.includes("PLOTTED_HINGE_DIVERGES")) return null;

  const bridge = asRecord(block.coverage_bridge);
  if (!bridge || bridge.reconciles !== true) return null;
  const rungs = bridge.rungs;
  if (!Array.isArray(rungs) || rungs.length === 0) return null;

  let plotted: number | null = null;
  const rows: CoverageRungRow[] = [];
  let emptyRules = 0;
  const seen = new Set<string>();

  for (const entry of rungs) {
    const rung = asRecord(entry);
    if (!rung) return null;
    const key = rung.key;
    if (typeof key !== "string" || seen.has(key)) return null;
    seen.add(key);

    const label = RUNG_LABELS[key];
    if (label === undefined) return null; // refusal 1: an unnamed rung
    if (rung.checked !== true || !isCount(rung.outcomes)) return null; // refusal 2: unmeasured

    if (key === PLOTTED_RUNG) {
      plotted = rung.outcomes;
      continue;
    }
    if (rung.outcomes === 0) {
      emptyRules += 1;
      continue;
    }
    rows.push({ key, label, outcomes: rung.outcomes });
  }

  if (plotted === null) return null;
  if (rows.length + emptyRules + 1 !== Object.keys(RUNG_LABELS).length) return null;

  const units = asRecord(asRecord(block.units)?.outcomes_with_calibration_coverage);
  const covered = units?.value;
  if (!isCount(covered)) return null;

  // The arithmetic the reader is invited to do, done here first. The rungs are
  // a partition, so this can only fail if the two sides came from different
  // walks — which is precisely the case a residual of 0 would be lying about.
  const excluded = rows.reduce((sum, row) => sum + row.outcomes, 0);
  if (plotted + excluded !== covered) return null;

  rows.sort((a, b) => b.outcomes - a.outcomes || a.key.localeCompare(b.key));

  return { covered, plotted, excluded, rows, emptyRules };
}
