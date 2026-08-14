// #999 L2-75: pure calibration math extracted from the /calibration page so it's
// unit-testable without SWR/data mocking. ECE is the n-weighted headline metric
// (reflects the outcomes users actually see); MCE is the equal-weighted
// worst-bucket-sensitivity number (a tiny bucket counts as much as a huge one).

export interface CalibrationErrorBucket {
  n: number;
  /** actual - predicted, in percentage points. */
  error: number;
}

/** Equal-weighted mean |error| (pp). Worst-bucket sensitive. */
export function mce(cal: CalibrationErrorBucket[]): number {
  if (!cal.length) return 0;
  return cal.reduce((s, b) => s + Math.abs(b.error), 0) / cal.length;
}

/** n-weighted mean |error| (pp). The headline calibration metric. */
export function ece(cal: CalibrationErrorBucket[]): number {
  const totalN = cal.reduce((s, b) => s + b.n, 0);
  if (!totalN) return 0;
  return cal.reduce((s, b) => s + (b.n / totalN) * Math.abs(b.error), 0);
}

// ---------------------------------------------------------------------------
// L2-230 / C111 [P1]: the trading-activity comparison.
//
// The page used to render an UNCONDITIONAL claim — "outcomes where the price
// moved are dramatically better calibrated" — plus `(unchangedECE / movedECE)`
// followed by the words "more accurately calibrated". Both are wrong whenever
// the observed ordering reverses, and on 2026-08-02 it had: price moved 1.7pp,
// price unchanged 1.0pp, rendering the literal sentence "Markets with active
// trading are 0.6x more accurately calibrated". A ratio below 1 printed as
// "more accurately" is not a wording nit — it inverts the number beside it.
//
// So the comparison is derived here, from the SAME values the page prints, and
// it states only the observed ordering. Two rules make that safe:
//
//   1. Compare at DISPLAY precision. If the page shows two cohorts as "1.0pp"
//      and "1.0pp", prose that ranks one above the other contradicts the pixels
//      next to it. Rounding first makes the tie state fall out for free, and
//      makes 0.05pp the tolerance rather than an invented threshold.
//   2. Never infer cause. C111 [P2] showed this aggregate is composition
//      sensitive: a synthetic mix where moved was better within BOTH strata
//      still inverted in aggregate. An ordering is an ordering. When it can't
//      be computed honestly, we say nothing — nothing > unhelpful.
// ---------------------------------------------------------------------------

/** Decimal places every ECE on the calibration page is rendered with. */
const ECE_DISPLAY_DP = 1;

/** One side of the activity split, as the page has it. */
export interface ActivityCohort {
  /** n-weighted ECE in percentage points. */
  ece: number | null | undefined;
  /** Outcomes behind it. Absent or <= 0 means there is nothing to compare. */
  n: number | null | undefined;
}

export interface ActivityComparison {
  /** Which cohort carries the HIGHER error, judged at display precision. */
  direction: "moved_higher" | "unchanged_higher" | "tied" | "unknown";
  /** Moved cohort ECE exactly as printed, e.g. "1.7". null when unusable. */
  movedText: string | null;
  /** Unchanged cohort ECE exactly as printed. null when unusable. */
  unchangedText: string | null;
  /** higher ÷ lower at display precision, e.g. "1.7". null when unstateable. */
  ratioText: string | null;
  /** The sentence to render. null means render no comparison at all. */
  sentence: string | null;
}

const UNRENDERABLE: ActivityComparison = {
  direction: "unknown",
  movedText: null,
  unchangedText: null,
  ratioText: null,
  sentence: null,
};

/** A cohort is usable only if it has outcomes AND a finite, non-negative ECE. */
function cohortValue(c: ActivityCohort | null | undefined): number | null {
  if (!c) return null;
  const { ece: e, n } = c;
  if (typeof n !== "number" || !Number.isFinite(n) || n <= 0) return null;
  if (typeof e !== "number" || !Number.isFinite(e) || e < 0) return null;
  // Round to what the reader actually sees before anything is compared.
  return Number(e.toFixed(ECE_DISPLAY_DP));
}

/**
 * Direction-aware, causation-free description of the trading-activity split.
 *
 * Returns `sentence: null` for every state where a comparison cannot be made
 * honestly — a missing cohort, an empty cohort, NaN/Infinity, a negative ECE.
 * The caller renders nothing in that case rather than guessing.
 */
export function describeActivityComparison(
  moved: ActivityCohort | null | undefined,
  unchanged: ActivityCohort | null | undefined
): ActivityComparison {
  const m = cohortValue(moved);
  const u = cohortValue(unchanged);
  if (m === null || u === null) return UNRENDERABLE;

  const movedText = m.toFixed(ECE_DISPLAY_DP);
  const unchangedText = u.toFixed(ECE_DISPLAY_DP);
  // UX-P075 item (c), Alex 2026-08-13: one vocabulary on this page. The cohorts
  // were "price moved"/"price unchanged" here, "Active Trading"/"Opening Price
  // Only" on the stat cards, and something else again in the toggle banner —
  // five namings of two cohorts. The PREDICATE is unchanged; only the noun is.
  // (`lib/calibrationCohort.ts` carries the reversal of L2-236's contrary
  // decision, in the open, per ruling 055 — and the proxy footnote that Alex
  // required to travel with the short word.)
  const lead = `Traded sits at ${movedText}pp and untraded at ${unchangedText}pp`;

  if (m === u) {
    return {
      direction: "tied",
      movedText,
      unchangedText,
      ratioText: null,
      sentence: `${lead} — effectively the same calibration error in this sample.`,
    };
  }

  const movedHigher = m > u;
  const higher = movedHigher ? m : u;
  const lower = movedHigher ? u : m;
  const higherLabel = movedHigher ? "traded" : "untraded";
  const lowerLabel = movedHigher ? "untraded" : "traded";

  // The ratio is suppressed when the smaller side rounds to 0.0pp (division by
  // zero) and when it would print as "1.0x", which reads as "the same" beside
  // prose that just said one is higher.
  let ratioText: string | null = null;
  if (lower > 0) {
    const r = (higher / lower).toFixed(ECE_DISPLAY_DP);
    if (r !== "1.0") ratioText = r;
  }

  const tail = ratioText
    ? `, ${ratioText}x the ${lowerLabel} cohort's`
    : "";
  return {
    direction: movedHigher ? "moved_higher" : "unchanged_higher",
    movedText,
    unchangedText,
    ratioText,
    sentence:
      `${lead} — in this sample the ${higherLabel} cohort carries the ` +
      `higher calibration error${tail}.`,
  };
}

/** "Jul 2026" from an ISO date; echoes the raw string if unparseable. */
export function monthYear(iso: string): string {
  const d = new Date(iso);
  return Number.isNaN(d.getTime())
    ? iso
    : d.toLocaleDateString("en-US", { month: "short", year: "numeric" });
}

// ---------------------------------------------------------------------------
// CAL-P025 / exit-exam item 2: the MATCHED-BUCKET trading comparison.
//
// `describeActivityComparison` above is honest about what it can say, and its
// comment already names the reason it cannot say much: "C111 [P2] showed this
// aggregate is composition sensitive: a synthetic mix where moved was better
// within BOTH strata still inverted in aggregate."
//
// That is a diagnosis, and this is the treatment. Two cohorts compared as
// aggregates differ in their predicted-probability MIX, so the difference
// between their headline ECEs is part composition and part whatever trading
// does. Compared bucket for bucket, the mix is held fixed and only the second
// part is left. On the frozen 2026-08-02 production payload the two readings
// disagree about the story: in aggregate the cohorts look separable, while
// bucket for bucket they sit within ~1-2pp of each other in eight of ten
// buckets and diverge in exactly one place — the 35-50% mid-band, where the
// price-moved side over-predicts by several points more.
//
// That mid-band divergence is a specific, publishable finding. The aggregate
// tiles bury it. So the section leads with this, and the tiles become the
// supporting detail they always were.
//
// Two rules carry over from `describeActivityComparison`, for the same reasons:
//   1. Compare at DISPLAY precision, so prose can never rank two numbers the
//      pixels render identically.
//   2. Never infer cause. A gap within a bucket is still an observed gap; it
//      is narrower than the aggregate one, not more causal.
//
// And one rule that is new here, because this function is the first in the
// module that can be asked about a bucket that does not exist on both sides:
//   3. An ABSENT side is `null`, never zero. A bucket that only one cohort
//      reaches has no gap to report, and rendering "0.0pp" for it would invent
//      an agreement out of missing data — gotcha #53's shape, in a table cell.
// ---------------------------------------------------------------------------

/** The `/api/calibration` bucket fields the matched comparison reads. */
export interface MatchedBucketInput {
  bucket_idx: number;
  /**
   * Tri-state, and OPTIONAL because `CalibrationBucket` declares it so. Absent
   * and `null` mean the same thing here — the test does not apply (sportsbook
   * lines) — and both are counted into `notApplicableN` rather than guessed at.
   */
  price_moved?: boolean | null;
  n: number;
  winners: number;
  sum_prob: number;
}

/** One cohort's numbers inside one bucket. */
export interface MatchedBucketSide {
  n: number;
  /** n-weighted mean predicted probability, in percentage points. */
  predictedPct: number;
  /** Realised win rate, in percentage points. */
  actualPct: number;
  /** actual - predicted, in percentage points. Negative = over-predicted. */
  errorPp: number;
}

export interface MatchedBucketRow {
  bucketIdx: number;
  /** "40-50%" */
  label: string;
  moved: MatchedBucketSide | null;
  unchanged: MatchedBucketSide | null;
  /**
   * `moved.errorPp - unchanged.errorPp`, at display precision.
   * `null` whenever either side is absent — see rule 3 above.
   */
  gapPp: number | null;
  /** Both sides present AND both above the thin-sample floor. */
  comparable: boolean;
}

export interface MatchedBucketComparison {
  /** Every bucket either cohort reaches, ascending. */
  rows: MatchedBucketRow[];
  /** The comparable row with the largest |gapPp|. `null` if none qualify. */
  widest: MatchedBucketRow | null;
  /** Outcomes behind the comparable rows — what the finding actually rests on. */
  comparedN: number;
  /** `price_moved === null` outcomes, excluded by definition and never silently. */
  notApplicableN: number;
  /** How many comparable buckets sit within `CLOSE_BAND_PP` of each other. */
  closeCount: number;
  /** The sentence to render. `null` means render no claim at all. */
  sentence: string | null;
}

/**
 * Sides thinner than this are shown but never carry the finding. Matches the
 * page's `MIN_CHART_BUCKET_N`, deliberately — a bucket the curve draws as a
 * faded thin-sample dot must not become the headline of the section below it.
 */
export const MATCHED_BUCKET_MIN_SIDE_N = 1000;

/** Gap at or under this reads as "these two track each other" (pp). */
export const MATCHED_BUCKET_CLOSE_BAND_PP = 2;

/** pp, at the one decimal place this page renders everything with. */
function pp(x: number): number {
  return Math.round(x * 1000) / 10;
}

/** "+2.3" / "-5.7" / "0.0" — sign carried, because direction is the content. */
function signedPp(x: number): string {
  if (x === 0) return "0.0";
  return `${x > 0 ? "+" : "−"}${Math.abs(x).toFixed(1)}`;
}

function side(acc: { n: number; winners: number; sumProb: number } | undefined): MatchedBucketSide | null {
  // Rule 3: absent and empty are both "no side", never a zero-error side.
  if (!acc || acc.n <= 0) return null;
  const predictedPct = pp(acc.sumProb / acc.n);
  const actualPct = pp(acc.winners / acc.n);
  return {
    n: acc.n,
    predictedPct,
    actualPct,
    // Rounded from the raw ratio, not from the two rounded values, so the
    // error never disagrees with itself by a rounding step.
    errorPp: pp(acc.winners / acc.n - acc.sumProb / acc.n),
  };
}

/**
 * Compare the two trading cohorts bucket for bucket.
 *
 * Holds the predicted-probability mix fixed, which is the one thing the
 * aggregate comparison cannot do. Rows with a missing side are still returned —
 * a reader should see that a bucket is one-sided — but they are not comparable
 * and can never become `widest` or feed the sentence.
 */
export function compareMatchedBuckets(
  buckets: MatchedBucketInput[] | null | undefined,
  minSideN: number = MATCHED_BUCKET_MIN_SIDE_N
): MatchedBucketComparison {
  const empty: MatchedBucketComparison = {
    rows: [],
    widest: null,
    comparedN: 0,
    notApplicableN: 0,
    closeCount: 0,
    sentence: null,
  };
  if (!buckets || !buckets.length) return empty;

  type Acc = { n: number; winners: number; sumProb: number };
  const moved: Record<number, Acc> = {};
  const unchanged: Record<number, Acc> = {};
  let notApplicableN = 0;

  for (const b of buckets) {
    if (!b || typeof b.bucket_idx !== "number" || !Number.isFinite(b.n) || b.n <= 0) continue;
    if (b.price_moved === null || b.price_moved === undefined) {
      // Named, not dropped. L2-236's finding was that these 40,075 outcomes
      // were excluded by both cards and mentioned by neither.
      notApplicableN += b.n;
      continue;
    }
    const into = b.price_moved ? moved : unchanged;
    const acc = (into[b.bucket_idx] ||= { n: 0, winners: 0, sumProb: 0 });
    acc.n += b.n;
    acc.winners += b.winners;
    acc.sumProb += b.sum_prob;
  }

  const idxs = Array.from(
    new Set([...Object.keys(moved), ...Object.keys(unchanged)].map(Number))
  ).sort((a, b) => a - b);

  const rows: MatchedBucketRow[] = idxs.map(i => {
    const m = side(moved[i]);
    const u = side(unchanged[i]);
    const bothPresent = m !== null && u !== null;
    return {
      bucketIdx: i,
      label: `${i * 10}-${i * 10 + 10}%`,
      moved: m,
      unchanged: u,
      gapPp: bothPresent ? Math.round((m.errorPp - u.errorPp) * 10) / 10 : null,
      comparable: bothPresent && m.n >= minSideN && u.n >= minSideN,
    };
  });

  const comparable = rows.filter(r => r.comparable);
  if (!comparable.length) {
    return { ...empty, rows, notApplicableN };
  }

  const widest = comparable.reduce((best, r) =>
    Math.abs(r.gapPp as number) > Math.abs(best.gapPp as number) ? r : best
  );
  const comparedN = comparable.reduce(
    (s, r) => s + (r.moved as MatchedBucketSide).n + (r.unchanged as MatchedBucketSide).n, 0
  );
  const closeCount = comparable.filter(
    r => Math.abs(r.gapPp as number) <= MATCHED_BUCKET_CLOSE_BAND_PP
  ).length;

  const wm = widest.moved as MatchedBucketSide;
  const wu = widest.unchanged as MatchedBucketSide;
  const sentence =
    `In ${closeCount} of ${comparable.length} matched buckets the two cohorts land within ` +
    `${MATCHED_BUCKET_CLOSE_BAND_PP}pp of each other. The widest matched gap is the ` +
    `${widest.label} band, where price-moved outcomes run ${signedPp(wm.errorPp)}pp against ` +
    `${signedPp(wu.errorPp)}pp for price-unchanged — a ` +
    `${Math.abs(widest.gapPp as number).toFixed(1)}pp difference on ` +
    `${(wm.n + wu.n).toLocaleString()} outcomes. Comparing inside a bucket holds the ` +
    `predicted-probability mix fixed, which the two headline figures above cannot do.`;

  return { rows, widest, comparedN, notApplicableN, closeCount, sentence };
}

// ---------------------------------------------------------------------------
// CAL-P025 / exit-exam item 4: per-source PANELS, not five overlaid lines.
//
// The legibility problem is measurable from the payload rather than a matter
// of taste. On 2026-08-02 the five sources spanned 28x in n (kalshi 420,594 to
// odds_api_spreads 12,410) and 3.3x in ECE (0.82pp to 2.72pp). Drawn on one
// axis the two large sources own every pixel that matters and the three
// sportsbook curves are unreadable — and the comparison a reader most wants,
// kalshi against polymarket, is the one the overlay hides.
//
// Small multiples fix it, but only if two things hold, and both are the
// point of doing this in a tested function instead of inline in the JSX:
//
//   1. The axis is SHARED. `CalibrationChart` fixes both axes at 0-100%
//      structurally, so this is free — but it is free only as long as every
//      panel goes through that component, which is asserted here by ordering
//      panels rather than by each caller choosing its own scale.
//   2. The SIZE difference survives. Small multiples equalise panel area, so a
//      12K-outcome curve and a 420K-outcome curve look equally authoritative
//      unless each panel states its own n. Every panel therefore carries n,
//      its share of the population, and its ECE — the three numbers the
//      overlay conveyed by line thickness and accident.
//
// RULING 003 ("clients format, never adjudicate", 2026-08-09) governs the third
// of those. Its named failure is *"dual ECE derivations — the same calibration
// number computed twice, in two languages, which guarantees they drift"*, so
// this function does NOT compute ECE. It takes the server's published
// `by_source[].ece` and renders it. A source the server published no ECE for
// gets `null` and the panel prints nothing there, which is the honest state:
// "the backend did not publish a number for this", not a number we invented to
// fill the gap.
//
// Counts are a different matter and are still summed here. `n` and `share` are
// sums of published per-bucket rows — formatting the evidence, not adjudicating
// a metric — and the ruling's list is metrics and decisions, not arithmetic on
// rows the server already sent.
// ---------------------------------------------------------------------------

export interface SourcePanelInput {
  source: string;
  /** The source's aggregated buckets, as the curve draws them. */
  buckets: CalibrationErrorBucket[];
  /**
   * The server's published ECE for this source, in pp. `null`/absent when the
   * payload published none — never backfilled by a client-side derivation.
   */
  publishedEce?: number | null;
}

export interface SourcePanel {
  source: string;
  /** Outcomes behind this source. */
  n: number;
  /** The server's ECE, pp, or `null` when the payload published none. */
  ece: number | null;
  /** This source's share of the panelled population, 0-1. */
  share: number;
}

/**
 * Order the per-source panels and give each one the numbers a shared-area
 * layout would otherwise erase.
 *
 * Largest first: the reader meets the source carrying most of the headline
 * number before the ones that barely move it. Sources with no buckets are
 * dropped rather than rendered as an empty frame — an empty panel asserts "we
 * measured this source and found nothing", which is not what it means.
 */
export function buildSourcePanels(inputs: SourcePanelInput[] | null | undefined): SourcePanel[] {
  if (!inputs || !inputs.length) return [];
  const withN = inputs
    .filter(i => i && Array.isArray(i.buckets))
    .map(i => ({
      source: i.source,
      n: i.buckets.reduce((s, b) => s + b.n, 0),
      // Rendered, not derived — ruling 003. Rounding a published number to the
      // page's display precision is formatting; recomputing it is not.
      ece: typeof i.publishedEce === "number" && Number.isFinite(i.publishedEce)
        ? Math.round(i.publishedEce * 10) / 10
        : null,
    }))
    // The one drop rule, and it is `n`, not `buckets.length`: a source present
    // with all-empty buckets is as absent as one with no buckets at all, and
    // both must fall out here rather than one falling out somewhere earlier.
    .filter(p => p.n > 0);

  const total = withN.reduce((s, p) => s + p.n, 0);
  return withN
    .map(p => ({ ...p, share: total > 0 ? p.n / total : 0 }))
    .sort((a, b) => b.n - a.n || a.source.localeCompare(b.source));
}
