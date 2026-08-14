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
//
// So every label here names its predicate and nothing else. Where the predicate
// really does measure trading movement — a payload with no not-applicable rows,
// where the cohort IS exactly `price_moved === true` — the plain claim is
// allowed to stand, because then it is measured rather than assumed.
//
// Native's `cohortHeadline` still reads "Showing well-traded markets (N)" and
// is now the residual divergence, owed a one-line native follow-up. It is out of
// this queue's gate: reported, not edited.
//
// ---------------------------------------------------------------------------
// UX-P075 — L2-236's SECOND objection is OVERTURNED, in the open (ruling 055)
// ---------------------------------------------------------------------------
//
// This header used to carry a second bullet, deleted above and quoted here so
// the reversal is legible at the point where the argument lived:
//
//   > "thin / untraded" for the excluded side is false twice over. Those rows
//   > are `price_moved === false` — they traded, they just never moved — and
//   > the published population already excludes zero-bid, zero-volume outcomes
//   > upstream. Nothing in the excluded set is untraded.
//
// **That is factually correct and it is overruled anyway** — by Alex, 2026-08-13
// eyeball session, staged as UX-P075 item (a): *rename the excluded cohort
// "untraded" everywhere; keep the proxy footnote — the rename must not quietly
// upgrade a proxy into a fact.* Later, and specific to this exact page and this
// exact word, so it governs (ruling 055's citation test).
//
// The reasoning behind the override, recorded so it is not re-litigated: L2-236
// solved a truth problem by making every label a predicate description, and
// bought truth with unreadability. "Showing markets whose price moved, plus
// sportsbook lines" is unimpeachable and nobody parses it. `/calibration`'s
// entire job is credibility with a non-technical reader (PRD §2; ruling 044 was
// banked against this page by name), and a sentence that is accurate and unread
// communicates nothing — which is the failure ruling 044 exists to name.
//
// So the resolution is NOT to drop L2-236's point but to relocate it: the short
// word goes in the label, and the predicate goes in a footnote that travels with
// it, ALWAYS. `proxyFootnote` below is that footnote, it is non-optional
// whenever the word appears, and `calibrationCohort.test.ts` asserts the pairing
// rather than banning the word. A short word with its proxy stated is honest; a
// short word alone is the thing L2-236 was right about.

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
   * The proxy footnote — UX-P075 / Alex 2026-08-14 item (a).
   *
   * NON-OPTIONAL wherever the short words appear. "Traded"/"untraded" are the
   * reader's words for a PRICE test, and this sentence is what stops the rename
   * from upgrading a proxy into a fact. It states the asymmetry precisely:
   * movement proves trading, stillness does not prove its absence.
   *
   * Derived by TESTING the emitted labels for the word, never by a separate
   * condition that implies them — so it is null exactly when no label says
   * "untraded", and the two cannot drift. A footnote about a cohort the page is
   * not showing is boilerplate, and boilerplate is how a caveat stops being read.
   */
  proxyFootnote: string | null;
  /**
   * `moved + unchanged + notApplicable === fullN`. False means the payload
   * carries a `price_moved` value outside the tri-state, and any cohort count
   * derived from it is describing fewer rows than it claims.
   */
  reconciles: boolean;
}

/**
 * The proxy footnote's text. One constant, because the page renders it and the
 * test asserts it, and a footnote that exists in two spellings is a footnote
 * one of whose spellings is unguarded.
 */
export const PROXY_FOOTNOTE =
  '"Traded" and "untraded" are shorthand for a price test, not a trade count. ' +
  "A price that moved off its opening line proves trading happened; a price " +
  "that never moved does not prove that it didn't. Outcomes with no bid and no " +
  "volume are already excluded upstream, so nothing in the untraded set is " +
  "untraded in the literal sense — it is the set whose price never moved off " +
  "its opening line. " +
  // UX-P080 item 3 (Alex round 2). This is the definition the headline sentence
  // stopped carrying. It belongs here and not up there for the reason the whole
  // footnote exists: the short word leads, the precision rides with it. Note it
  // states the GROUND ("a book moves its line with money"), not just the
  // conclusion — a reader who is told sportsbook lines count as traded and not
  // told why has been asked to take our word for it, on the one page whose
  // entire job is not needing to be taken at our word.
  "Sportsbook lines carry no price-moved flag and do not need one: a book " +
  "moves its line with money, so those outcomes are traded by construction " +
  "and are counted as traded here.";

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
  // UX-P080 item 3. The arithmetic is unchanged; the SENTENCE had to change with
  // it. This note used to say sportsbook lines "sit in neither cohort" — true of
  // the old framing, and now a contradiction of the copy directly above it,
  // where they are counted as traded. A reconciliation note that disagrees with
  // the sentence it reconciles is worse than none: it is the page arguing with
  // itself in small print, on the surface whose only job is credibility.
  const partitionNote = hasNotApplicable
    ? `Sportsbook lines (${fmt(notApplicableN)} outcomes) carry no price-moved flag and ` +
      `need none — a book moves its line with money — so they count as traded: ` +
      `${fmt(movedN)} price-moved + ${fmt(notApplicableN)} sportsbook = ` +
      `${fmt(defaultCohortN)} traded, plus ${fmt(unchangedN)} untraded ` +
      `= ${fmt(fullN)} resolved outcomes.`
    : null;

  // The footnote rides with the WORD — and that is implemented by TESTING the
  // emitted labels, not by guessing a condition that implies them.
  //
  // The first draft guessed (`unchangedN > 0`) and was wrong twice in a row: the
  // zero-untraded branch still said "Excluded: 0 untraded outcomes", and after
  // that was fixed the toggle still said "Include untraded". Both were caught by
  // the pairing test, both were the same mistake — a second expression that has
  // to stay in agreement with the strings, i.e. #1620's disease in miniature.
  // Deriving the footnote FROM the strings makes disagreement unrepresentable.
  const withFootnote = (copy: Omit<CohortCopy, "proxyFootnote">): CohortCopy => ({
    ...copy,
    proxyFootnote: [
      copy.headline, copy.detail, copy.toggleLabel,
      copy.statDetail, copy.heroClause, copy.shortLabel,
    ].some(l => /untraded/i.test(l))
      ? PROXY_FOOTNOTE
      : null,
  });

  if (includeNeverMoved) {
    return withFootnote({
      key: "all",
      cohortN,
      fullN,
      shortLabel: "All markets",
      headline: `Showing all markets (${fmt(fullN)})`,
      // Two cohorts, not three. "Not applicable" named a category the ruling
      // dissolved; the sportsbook count survives as a parenthetical inside the
      // cohort it actually belongs to.
      detail: hasNotApplicable
        ? `${fmt(defaultCohortN)} traded (including ${fmt(notApplicableN)} ` +
          `sportsbook lines) · ${fmt(unchangedN)} untraded.`
        : `${fmt(movedN)} traded · ${fmt(unchangedN)} untraded.`,
      toggleLabel: unchangedN > 0 ? "Exclude untraded" : "Show every outcome",
      statDetail: `all outcomes · ${fmt(fullN)} total`,
      heroClause: `${fmt(fullN)} resolved predictions`,
      partitionNote,
      reconciles,
    });
  }

  // UX-P080 item 3 — Alex round 2. The default cohort is THE TRADED OUTCOMES,
  // full stop, and sportsbook lines are part of it rather than an appendix to
  // it.
  //
  // The ruling that collapses the two: **sportsbook lines are traded BY
  // CONSTRUCTION — a book moves its line with money.** So the absent
  // `price_moved` flag on those rows was never evidence that the price test
  // failed on them; it is evidence that the test is unnecessary for them. The
  // old copy inherited the flag's shape instead of the fact's, and every
  // sentence it produced had to apologise for a third category that does not
  // exist: "plus sportsbook lines where that test doesn't apply."
  //
  // What that cost the reader is the point. "413,406 traded outcomes" is one
  // number they can hold; "372,615 traded outcomes, plus 40,791 sportsbook
  // lines where that test doesn't apply" is two numbers, a caveat, and a
  // subtraction — and the reader who does the subtraction still does not learn
  // anything, because the answer is that all of them are traded.
  //
  // The definition does not vanish; it moves to `PROXY_FOOTNOTE`, which already
  // travels with the word wherever the word appears. Same move UX-P075 made for
  // "untraded" and UX-P078 made for the shape annex: the short true thing leads,
  // the precision rides underneath it, and neither is dropped.
  const shortLabel = "Traded";
  const headline = `Showing traded markets (${fmt(defaultCohortN)})`;
  // An empty excluded side excludes NOTHING, so it gets no clause — "Excluded:
  // 0 untraded outcomes" both states a non-fact and puts the word "untraded" on
  // screen in the one state where `proxyFootnote` is (correctly) null, breaking
  // the pairing invariant. Caught by that invariant's own test on its first run,
  // which is the whole argument for writing the assertion as a pairing rather
  // than as a word-ban.
  const excluded = unchangedN > 0
    ? ` Excluded: ${fmt(unchangedN)} untraded outcomes, whose price never moved off its opening line.`
    : "";
  const detail = hasNotApplicable
    ? `${fmt(defaultCohortN)} traded outcomes ` +
      `(including ${fmt(notApplicableN)} sportsbook lines).${excluded}`
    : // No sportsbook rows in this payload: the cohort is the price-moved set
      // and there is no second construction to name.
      `Every traded outcome.${excluded}`;

  return withFootnote({
    key: "excluding_never_moved",
    cohortN,
    fullN,
    shortLabel,
    headline,
    detail,
    toggleLabel: unchangedN > 0
      ? `Include untraded (+${fmt(unchangedN)})`
      : "Show every outcome",
    statDetail: unchangedN > 0
      ? `excludes ${fmt(unchangedN)} untraded · ${fmt(fullN)} total`
      : `all outcomes · ${fmt(fullN)} total`,
    heroClause: unchangedN > 0
      ? `${fmt(defaultCohortN)} resolved predictions — every outcome except the ` +
        `${fmt(unchangedN)} untraded ones, whose price never moved off its ` +
        `opening line (${fmt(fullN)} in total)`
      : `${fmt(defaultCohortN)} resolved predictions`,
    partitionNote,
    reconciles,
  });
}
