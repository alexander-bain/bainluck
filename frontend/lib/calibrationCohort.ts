// L2-236 — the calibration page's cohort language, derived from the cohort's
// own predicate instead of asserted beside it.
//
// THE DEFECT THIS REPLACES
//
// `/calibration` defaults to `price_moved !== false` and described that set as
// "well-traded markets — where real trading moved the price". `price_moved` is
// a TRI-state, not a boolean:
//
//   true   the price moved after opening
//   false  it never did
//   null   sportsbook moneylines / spreads / totals, where "did trading move
//          the price" is not a question the source can answer — NOT APPLICABLE
//
// So the default cohort is `true` PLUS `null`, and on the frozen 2026-08-02
// production payload that is 349,310 + 40,075 = 389,385 rows. The sentence
// "where real trading moved the price" was false for 40,075 of them, 10.3% of
// the cohort it described, and those rows were named nowhere on the page: the
// activity section's two cards summed to 612,332 against a stated population of
// 652,407 and the shortfall had no label.
//
// L2-231 fixed exactly this on native and reported the identical defect here.
// This module is web's half, and it is the same grammar.
//
// WHY THE COHORT IS ALSO RENAMED
//
// Native kept the NAME "well-traded" deliberately — the name was web's, and
// renaming it there while web was out of gate would have manufactured a second
// divergence. Web is where that call belongs, and the name does not survive it:
//
//   - "well-traded" is a LIQUIDITY claim. The predicate measures MOVEMENT. A
//     market can trade heavily and close where it opened.
//   - "thin / untraded" for the excluded side is false twice over. Those rows
//     are `price_moved === false` — they traded, they just never moved — and
//     the published population already excludes zero-bid, zero-volume outcomes
//     upstream (see the page's methodology section). Nothing in the excluded
//     set is untraded.
//
// So every label here names its predicate and nothing else. Where the predicate
// really does measure trading movement — a payload with no not-applicable rows,
// where the cohort IS exactly `price_moved === true` — the plain claim is
// allowed to stand, because then it is measured rather than assumed.
//
// Native's `cohortHeadline` still reads "Showing well-traded markets (N)" and
// is now the residual divergence, owed a one-line native follow-up. It is out of
// this queue's gate: reported, not edited.

/** en-US thousands separators, fixed so tests do not depend on host locale. */
function fmt(n: number): string {
  return n.toLocaleString("en-US");
}

/** The three states of `price_moved`, counted in outcomes. */
export interface ActivityPartition {
  /** `price_moved === true` — the price moved after opening. */
  movedN: number;
  /** `price_moved === false` — it never did. */
  unchangedN: number;
  /** `price_moved` null/absent — sportsbook lines; the test does not apply. */
  notApplicableN: number;
}

/** Which predicate the page is currently rendering. */
export type CohortKey = "all" | "excluding_never_moved";

export interface CohortCopy {
  /** Machine-readable name of the active predicate. Published as a hook. */
  key: CohortKey;
  /** Outcomes the active cohort contains. */
  cohortN: number;
  /** Outcomes in the whole population — the comparison denominator. */
  fullN: number;
  /** Short noun phrase for the cohort, for chart labels and headings. */
  shortLabel: string;
  /** The toggle banner's bolded headline. */
  headline: string;
  /** The sentence under it, naming every part of the cohort with its count. */
  detail: string;
  /** The toggle button's label. */
  toggleLabel: string;
  /** The population stat card's detail line. */
  statDetail: string;
  /** The hero's population clause. */
  heroClause: string;
  /**
   * Reconciles the activity section's two cards to the page population. Null
   * when there are no not-applicable rows, so the note never appears as
   * boilerplate on a payload it does not describe.
   */
  partitionNote: string | null;
  /**
   * `moved + unchanged + notApplicable === fullN`. False means the payload
   * carries a `price_moved` value outside the tri-state, and any cohort count
   * derived from it is describing fewer rows than it claims.
   */
  reconciles: boolean;
}

/**
 * Count the three `price_moved` states over anything bucket-shaped.
 *
 * Written against a structural minimum rather than `CalibrationBucket` so the
 * tests can freeze the production payload without importing the API surface.
 */
export function partitionByActivity(
  buckets: ReadonlyArray<{ price_moved?: boolean | null; n: number }>
): ActivityPartition {
  let movedN = 0;
  let unchangedN = 0;
  let notApplicableN = 0;
  for (const b of buckets) {
    // Non-finite `n` contributes nothing rather than poisoning the whole
    // partition — one unreadable row must not wipe the pass (gotcha #42).
    const n = typeof b.n === "number" && Number.isFinite(b.n) ? b.n : 0;
    if (b.price_moved === true) movedN += n;
    else if (b.price_moved === false) unchangedN += n;
    else notApplicableN += n;
  }
  return { movedN, unchangedN, notApplicableN };
}

/**
 * Every cohort-facing string on the page, from the partition and the toggle.
 *
 * `fullN` is passed in rather than summed here because the page computes it
 * from the same aggregation the curve uses; passing it lets `reconciles`
 * actually check the two against each other instead of restating one of them.
 */
export function describeCohort(
  partition: ActivityPartition,
  fullN: number,
  includeNeverMoved: boolean
): CohortCopy {
  const { movedN, unchangedN, notApplicableN } = partition;
  const hasNotApplicable = notApplicableN > 0;
  const defaultCohortN = movedN + notApplicableN;
  const cohortN = includeNeverMoved ? fullN : defaultCohortN;
  const reconciles = movedN + unchangedN + notApplicableN === fullN;

  // The activity split's own reconciliation. Identical in shape to native's
  // `activityPartitionNote` so the two surfaces state one arithmetic fact.
  const partitionNote = hasNotApplicable
    ? `Sportsbook lines (${fmt(notApplicableN)} outcomes) carry no price-moved flag, so they ` +
      `sit in neither cohort: ${fmt(movedN)} + ${fmt(unchangedN)} + ${fmt(notApplicableN)} ` +
      `= ${fmt(fullN)} resolved outcomes.`
    : null;

  if (includeNeverMoved) {
    return {
      key: "all",
      cohortN,
      fullN,
      shortLabel: "All markets",
      headline: `Showing all markets (${fmt(fullN)})`,
      detail: hasNotApplicable
        ? `${fmt(movedN)} price moved · ${fmt(unchangedN)} price unchanged · ` +
          `${fmt(notApplicableN)} not applicable (sportsbook lines).`
        : `${fmt(movedN)} price moved · ${fmt(unchangedN)} price unchanged.`,
      toggleLabel: "Exclude never-moved",
      statDetail: `all outcomes · ${fmt(fullN)} total`,
      heroClause: `${fmt(fullN)} resolved predictions`,
      partitionNote,
      reconciles,
    };
  }

  // The default cohort. Its name is what it selects: outcomes whose price
  // moved, plus the rows where that test does not apply.
  const shortLabel = hasNotApplicable
    ? "Price moved + sportsbook lines"
    : "Price moved";
  const headline = hasNotApplicable
    ? `Showing markets whose price moved, plus sportsbook lines (${fmt(defaultCohortN)})`
    : `Showing markets whose price moved (${fmt(defaultCohortN)})`;
  const excluded = `Excluded: ${fmt(unchangedN)} outcomes whose price never moved off its opening line.`;
  const detail = hasNotApplicable
    ? `${fmt(movedN)} outcomes whose price real trading moved, plus ${fmt(notApplicableN)} ` +
      `sportsbook lines where that test doesn't apply. ${excluded}`
    : // No not-applicable rows: the cohort really is "where real trading moved
      // the price", so the plain claim is measured and may stand.
      `Every outcome whose price real trading moved. ${excluded}`;

  return {
    key: "excluding_never_moved",
    cohortN,
    fullN,
    shortLabel,
    headline,
    detail,
    toggleLabel: `Include never-moved (+${fmt(unchangedN)})`,
    statDetail: `excludes ${fmt(unchangedN)} never-moved · ${fmt(fullN)} total`,
    heroClause:
      `${fmt(defaultCohortN)} resolved predictions — every outcome except the ` +
      `${fmt(unchangedN)} whose price never moved off its opening line ` +
      `(${fmt(fullN)} in total)`,
    partitionNote,
    reconciles,
  };
}
