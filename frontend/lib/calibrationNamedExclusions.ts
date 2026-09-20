// #7353 — the exclusion rules the accuracy page publishes but never named.
//
// WHAT THIS IS FOR
//
// The methodology section names six exclusions in full sentences: the two
// Kalshi bars, esports bundles, soccer 2-way, voids, and non-partition bundles.
// The payload carries nine more named `*_filter` blocks, eight of them with a
// non-zero count, and before this module not one of those nine field names
// appeared anywhere in `frontend/`. Four of the eight are LARGER than the void
// filter the page does list, and the largest is bigger than the liquidity
// filter it also lists — so the silence was not a rounding-off of trivia, it
// was the same class of rule disclosed for six and withheld for eight.
//
// The sentence under the hero made that a false claim rather than a gap: it
// told a reader the methodology covered "every exclusion".
//
// WHAT IT IS NOT
//
// This is a LIST, not an accounting. `calibrationCoverage.ts` is the
// accounting — a first-match-wins partition whose rungs sum back to the covered
// population, which is why that module refuses to render at all when the
// arithmetic does not reproduce. These rows are independent rules over
// overlapping cohorts on different denominators, so they sum to nothing and the
// page says so beside them. Two consequences, both deliberate:
//
//   1. No total is exported. A caller cannot add these up, because adding them
//      up is wrong: the Kalshi bars already nest, and a prop row can be dropped
//      by more than one rule.
//   2. It does not make the page complete. `truth_evidence`'s price-derived
//      rung and `mex_normalization`'s field-incomplete rung are exclusions too,
//      measured over a different population (all captured outcomes, not the
//      resolved-and-priced set these counts are drawn from), so appending them
//      to this list would put two denominators under one column. They stay out,
//      and the page therefore stops promising completeness instead of claiming
//      it. Disclosing them honestly needs the coverage census, which reads
//      `status: "unavailable"` in production today.
//
// THE LABELS ARE THIS MODULE'S OWN WORDS, AND THE MAP IS CLOSED
//
// Same rule as `RUNG_LABELS`, for the same reason (#4067 / CERT-2295): every
// payload block carries a `rule` string written for an auditor — raw column
// names, series tickers, supplier words, issue numbers — and notice 34 bans
// exactly that prose from a reader's screen. A filter this map cannot name is
// counted in `unlistedRules` and rendered as nothing at all, so a rule the
// backend adds tomorrow shows up as a number a probe can see rather than as a
// raw key on the page or a silent omission.
//
// AND THE UNIVERSE IT CLOSES OVER IS THE BACKEND, NOT THE SERVED PAYLOAD (#7627)
//
// This map was first written from `api.bainluck.com/api/calibration`, which is
// the obvious place to read "what blocks exist" and is the wrong one. That
// payload is published by `precompute_calibration_main`, a HEAVY_TASK, and
// `bainluck-heavy` runs behind master (notice 48): the response the map was
// built from was stamped 2026-09-15 and carried fifteen blocks, while master had
// emitted sixteen since 2026-09-14. So `identity_quarantine_filter` was missing
// from the map, from the fixture, and therefore from the fixture-derived test
// that was supposed to keep the map closed — one omission, invisible three
// times, because all three read the same stale artifact.
//
// The cost was not a reader's: that rule must be skipped anyway. It was
// `unlistedRules`, which would have read 1 forever for a rule the page names in
// full, so the one signal built to catch the NEXT omission was pre-spent on a
// known one. The suite now derives the universe from
// `backend/app/tasks/precompute_calibration.py` itself.

/**
 * The exclusions that already have their own bullet, with their own sentence.
 *
 * Listed here so a count can never be printed twice under two different names.
 * `nonexclusive_bundle_filter` carries Alex's ruled disclosure (CAL-P114/P117),
 * the two Kalshi bars carry the overlap sentence they were ruled to carry, and
 * none of that belongs in a folded tail.
 */
export const EXCLUSIONS_WITH_THEIR_OWN_BULLET: ReadonlySet<string> = new Set([
  "liquidity_filter",
  "writer_bar_filter",
  "esports_multi_bundle_filter",
  "soccer_2way_filter",
  "void_filter",
  "nonexclusive_bundle_filter",
  // #7627. Not a folded row, and not for want of a label: these rows are the
  // page's "Held out, under review" section (CAL-P067, Alex's #6275/#1902
  // ruling), which prints the count in full. Listing them here too would be the
  // double-naming this set exists to stop.
  //
  // The skip is safe to make unconditional because the section and this block
  // are gated on the SAME backend variable — `identity_disputed_excluded` is
  // both `identity_quarantine_filter.excluded` and the `> 0` test that decides
  // whether `quarantine` is a row or an empty list — so there is no payload in
  // which the fold stays silent and the section does too. That coupling is what
  // makes this an own-bullet rule rather than a silent drop, so it is pinned
  // against the backend source in the suite rather than trusted.
  "identity_quarantine_filter",
]);

/**
 * A short reader sentence for every other `*_filter` the server can emit.
 *
 * Each one says what was set aside and why, in the page's voice. Deliberately a
 * CLOSED map: see the header.
 */
export const NAMED_EXCLUSION_LABELS: Readonly<Record<string, string>> = {
  heuristic_filter: "Results an old process guessed at instead of settling",
  kalshi_prop_threshold_filter: "Player-prop prices the market never really made (Kalshi)",
  poly_placeholder_filter: "Filler prices near 50% that nobody bid on or traded (Polymarket)",
  no_winner_filter: "Markets where nothing was ever marked the winner",
  draw_authority_filter: "Two-way prices on a match that could have ended in a draw",
  golf_placeholder_filter: "Two golfers both priced above 80% to win the same event",
  malformed_binary_filter: "Two-sided markets that marked nobody the winner, or marked both",
  weather_wide_spread_filter: "Weather prices quoted with a gap too wide to trade (Kalshi)",
  orphan_partition_filter: "One runner kept from a field whose rivals were never recorded",
};

export interface NamedExclusionRow {
  /** The payload field, so a probe can bind a row to its source. */
  key: string;
  label: string;
  outcomes: number;
}

export interface NamedExclusions {
  /** Rules that set aside at least one outcome, largest first. */
  rows: NamedExclusionRow[];
  /**
   * Rules measured at exactly zero.
   *
   * A rule that fired zero times is a checked zero and is worth a line, the way
   * the coverage accounting says so: "measured none" and "not measured" are
   * different answers and the page should not collapse them.
   */
  emptyRules: number;
  /**
   * `*_filter` blocks this module could not turn into a row — no label in the
   * closed map, or no count it could read.
   *
   * Never rendered as prose; published as a data attribute so a guard or a
   * probe can see the day the backend grows a rule this list does not name.
   */
  unlistedRules: number;
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
 * How many outcomes a filter block set aside, or `null` if it does not say.
 *
 * Two shapes are in the payload today. Most blocks publish a flat `excluded`;
 * `heuristic_filter` publishes only `excluded_by_source`, and reading the flat
 * field alone would have printed that rule — the largest of the nine — as an
 * unreadable block. A per-source breakdown IS the count, summed.
 */
function excludedOutcomes(block: Record<string, unknown>): number | null {
  if (isCount(block.excluded)) return block.excluded;

  const bySource = asRecord(block.excluded_by_source);
  if (!bySource) return null;
  const parts = Object.values(bySource);
  if (parts.length === 0 || !parts.every(isCount)) return null;
  return (parts as number[]).reduce((sum, n) => sum + n, 0);
}

/**
 * The exclusion rules to list, or `null` to list nothing.
 *
 * `null` when there is no row to show — an older cached payload, or a build in
 * which every remaining rule fired zero times. A fold with nothing in it is
 * worse than no fold, so the page renders neither.
 */
export function readNamedExclusions(payload: unknown): NamedExclusions | null {
  const block = asRecord(payload);
  if (!block) return null;

  const rows: NamedExclusionRow[] = [];
  let emptyRules = 0;
  let unlistedRules = 0;

  for (const key of Object.keys(block)) {
    if (!key.endsWith("_filter")) continue;
    if (EXCLUSIONS_WITH_THEIR_OWN_BULLET.has(key)) continue;

    const filter = asRecord(block[key]);
    if (!filter) continue; // absent or null: the payload predates the rule.

    const label = NAMED_EXCLUSION_LABELS[key];
    const outcomes = excludedOutcomes(filter);
    if (label === undefined || outcomes === null) {
      unlistedRules += 1;
      continue;
    }

    if (outcomes === 0) {
      emptyRules += 1;
      continue;
    }
    rows.push({ key, label, outcomes });
  }

  if (rows.length === 0) return null;

  rows.sort((a, b) => b.outcomes - a.outcomes || a.key.localeCompare(b.key));
  return { rows, emptyRules, unlistedRules };
}
