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
//
// ---------------------------------------------------------------------------
// D101 — AND THE FOOTNOTE IS NOW DELETED (Alex, Wed 2026-09-09 10:05am PT)
// ---------------------------------------------------------------------------
//
// The paragraph above describes a footnote that no longer exists. It is kept
// because the reversal has to be legible where the argument lived (ruling 055),
// and because the next reader of this file will otherwise re-derive it.
//
// Two of Alex's own instructions had come to point opposite ways for this one
// sentence: 2026-08-14 said the proxy footnote rides with the word wherever the
// word appears, and standing notice 34 (2026-09-08) says no diagnostic prose on
// a reader's screen. calibration/1063 put the conflict to him rather than
// picking a side, with three options — A leave it, B fold it behind the same
// tap as the other six blocks, C delete it. **He ruled C.**
//
// The GROUND for counting sportsbook lines as traded (UX-P080 item 3, Alex
// round 2) rode in the same paragraph's last clause and does NOT go with it:
// `partitionNote` states it, and #4340 renders that note inside the closed
// "The overall split" fold — one tap down, where the other six blocks of this
// class now live. `calibrationCohort.test.ts` re-points that assertion rather
// than deleting it.
//
// So the pairing invariant is gone, not weakened, and what replaces it is the
// only thing left that can go wrong: the cohort labels must not start making a
// CLAIM the deleted sentence used to qualify. "Traded"/"untraded" as the name of
// a cohort survives — that is the rename Alex ordered in August and did not
// revisit. "Well-traded", "thinly traded", "actively traded", a trade COUNT, or
// any word that asserts activity rather than naming a cohort is what the
// footnote was holding back, and `calibrationCohort.test.ts` bans exactly those,
// on the emitted strings. The word-ban L2-236 wanted, narrowed to the claims
// that were actually at issue.

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
  /**
   * Outcomes in the measured population — the comparison denominator.
   *
   * #7496: NOT "the whole population", and no string here may call it that.
   * `total_outcomes` is what survives the exclusion rules, and the page's own
   * "What's included?" bullet says so — "that published total is lower than the
   * raw resolved-outcome count because we exclude markets that can't form an
   * honest prediction". The eight folded rules alone set aside 147,721
   * outcomes, four of the six bulleted ones more. So a sentence that calls this
   * number the total, or names the untraded rows as the only thing left out,
   * is contradicted nine screens below by the same page.
   */
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
   * The plain headline's scope phrase — the subject of the one sentence a
   * casual reader actually reads, which prints the cohort's ECE.
   *
   * #7202: that sentence was the hard-coded "Across every market we track",
   * one line under a `heroClause` that had just disclosed setting aside
   * 298,001 of 747,028 outcomes. It was not loose wording: the figure beside
   * it is the cohort's (0.91pp → "0.9"), while the population it named reads
   * 0.68pp → "0.7". It also said "every" over a set excluding 70% of
   * Polymarket and all of DataGolf.
   *
   * So the scope travels with the predicate, like every other string here. It
   * says "every market" only where that is TRUE — the reader has toggled the
   * untraded rows back in, or the payload excluded none — and never asks the
   * call site to decide which case it is in.
   */
  plainHeadlineScope: string;
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
  // UX-P080 item 3. The arithmetic is unchanged; the SENTENCE had to change with
  // it. This note used to say sportsbook lines "sit in neither cohort" — true of
  // the old framing, and now a contradiction of the copy directly above it,
  // where they are counted as traded. A reconciliation note that disagrees with
  // the sentence it reconciles is worse than none: it is the page arguing with
  // itself in small print, on the surface whose only job is credibility.
  const partitionNote = hasNotApplicable
    ? `Sportsbook lines (${fmt(notApplicableN)} outcomes) carry no price-moved flag and ` +
      // #4067 repair (CERT-2290): "a book" was the last reader-facing singular
      // on this page. Notice 33 bans the word whatever its number, and the
      // sentence loses nothing — it is already about sportsbook lines, named
      // in its own first clause.
      `need none — a sportsbook moves its line with money — so they count as traded: ` +
      `${fmt(movedN)} price-moved + ${fmt(notApplicableN)} sportsbook = ` +
      `${fmt(defaultCohortN)} traded, plus ${fmt(unchangedN)} untraded ` +
      `= ${fmt(fullN)} resolved outcomes.`
    : null;

  // D101 (Alex, Wed 2026-09-09): `withFootnote` stood here. It derived the
  // proxy footnote FROM the emitted strings — the pairing that made "untraded"
  // on screen without its definition unrepresentable — and it is deleted with
  // the footnote it produced. The lesson it was written for survives as a
  // TEST over the emitted strings (never a second condition beside them), which
  // is where it belonged anyway: see the claim ban in calibrationCohort.test.ts.

  if (includeNeverMoved) {
    return {
      key: "all",
      cohortN,
      fullN,
      // #7750 — `shortLabel` is the ADJECTIVE SLOT, not a noun phrase. Two of
      // its three consumers supply their own noun over their own number
      // (page.tsx: "{shortLabel} ({cohortN} outcomes)" and the chart series
      // "{shortLabel} ({cohortN})"), which is why the sibling cohort below is
      // the bare word "Traded". "All markets" was the odd one out and it
      // printed "All markets (747,028 outcomes)" — a noun and its counter-noun
      // over one number. Keeping the slot adjectival fixes every consumer at
      // once and makes the next one correct by construction; spelling it "All
      // outcomes" would instead have produced "All outcomes (747,028
      // outcomes)". The chip reads "ALL" beside its sibling's "TRADED".
      shortLabel: "All",
      headline: `Showing all outcomes (${fmt(fullN)})`,
      // Two cohorts, not three. "Not applicable" named a category the ruling
      // dissolved; the sportsbook count survives as a parenthetical inside the
      // cohort it actually belongs to.
      detail: hasNotApplicable
        ? `${fmt(defaultCohortN)} traded (including ${fmt(notApplicableN)} ` +
          `sportsbook lines) · ${fmt(unchangedN)} untraded.`
        : `${fmt(movedN)} traded · ${fmt(unchangedN)} untraded.`,
      toggleLabel: unchangedN > 0 ? "Exclude untraded" : "Show every outcome",
      // #7496 — "all outcomes · 747,028 total" over the RESOLVED OUTCOMES card.
      // Both halves claimed the exclusion rules away. The toggle's own scope is
      // real and stays (this view holds every row the curve has); what it may
      // not say is that the curve holds every row.
      statDetail: `all measured outcomes · ${fmt(fullN)} measured`,
      heroClause: `${fmt(fullN)} resolved predictions`,
      // The cohort IS the population here, so the unqualified claim is true.
      plainHeadlineScope: "Across every market we track",
      partitionNote,
      reconciles,
    };
  }

  // UX-P080 item 3 — Alex round 2. The default cohort is THE TRADED OUTCOMES,
  // full stop, and sportsbook lines are part of it rather than an appendix to
  // it.
  //
  // The ruling that collapses the two: **sportsbook lines are traded BY
  // CONSTRUCTION — a sportsbook moves its line with money.** So the absent
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
  // The definition did not vanish at the time; it moved to `PROXY_FOOTNOTE`,
  // which travelled with the word wherever the word appeared. **D101 has since
  // deleted that footnote** (Alex, 2026-09-09). The GROUND it carried — a
  // sportsbook moves its line with money, so those rows are traded — is not
  // lost with it: `partitionNote` below states it, and #4340 put that note
  // inside the closed "The overall split" fold, which is where the other six
  // blocks of this class now live. The rows are named and counted in `detail`
  // either way.
  const shortLabel = "Traded";
  // #7750 — the unit is the OUTCOME. Four things on this one screen count the
  // same population and the headline was the only one out of step with the
  // other three: its own `excluded` clause below ("Excluded: N untraded
  // OUTCOMES", same sentence), the source table's OUTCOMES column, and the
  // RESOLVED OUTCOMES hero card. A market resolves into many outcomes, so
  // "markets (449,027)" is not a loose synonym here — it is a different and
  // much smaller quantity, printed on the page whose only job is credibility.
  const headline = `Showing traded outcomes (${fmt(defaultCohortN)})`;
  // An empty excluded side excludes NOTHING, so it gets no clause — "Excluded:
  // 0 untraded outcomes" states a non-fact. It was caught by the proxy-footnote
  // pairing test on that test's first run (the pairing is gone with D101, the
  // clause it caught is not), which is the whole argument for writing an
  // assertion over the emitted strings rather than over the branch.
  const excluded = unchangedN > 0
    ? ` Excluded: ${fmt(unchangedN)} untraded outcomes, whose price never moved off its opening line.`
    : "";
  // #7330 — `headline` and `detail` are rendered as ONE sentence flow
  // (`{cohort.headline} {cohort.detail}`, page.tsx), so this clause is read
  // immediately after the count the headline just printed. It used to open by
  // restating that count, and production said:
  //
  //   Showing traded markets (449,027) 449,027 traded outcomes (including
  //   155,127 sportsbook lines). Excluded: 298,001 untraded outcomes…
  //
  // Neither half is wrong alone, which is why every per-field assertion over
  // `detail` passed; the defect exists only in the concatenation. A number
  // repeated adjacent to itself reads as double-counting, on the one page whose
  // whole job is to be trusted with numbers.
  //
  // "Of those" keeps what the restatement was carrying — that the sportsbook
  // rows are a SUBSET of the traded cohort, not a third thing beside it, which
  // is UX-P080 item 3's ruling and the e2e claim `sportsbook_named_as_a_subset`
  // — and lets the headline be the only place the traded count is printed.
  const detail = hasNotApplicable
    ? `Of those, ${fmt(notApplicableN)} are sportsbook lines.${excluded}`
    : // No sportsbook rows in this payload: the cohort is the price-moved set
      // and there is no second construction to name.
      `Every traded outcome.${excluded}`;

  return {
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
      ? `excludes ${fmt(unchangedN)} untraded · ${fmt(fullN)} measured`
      : `all measured outcomes · ${fmt(fullN)} measured`,
    // #7496 — the hero read "every outcome except the 298,001 untraded ones …
    // (747,028 in total)", which names untraded as the only cut and 747,028 as
    // everything. Neither is true (see `fullN` above), and both stand in the
    // largest type on the page, ahead of every qualification that walks them
    // back.
    //
    // The exclusions do NOT move up here. Notice 34 / D102 keep the method off
    // the reader's screen, and it is already carried twice below — the
    // "What's included?" bullet and the exclusion list, folded. What the hero
    // owes is a scope its own page does not contradict, and "we measured" is
    // the page's own verb for it ("How We Measure This").
    //
    // The parenthetical says "measured in all" rather than "in all" because a
    // reader skims it ALONE: "(747,028 in all)" read on its own is the same
    // completeness claim with the qualifier out of sight. A scoping word that
    // only works when the whole sentence is read is not a scoping word.
    heroClause: unchangedN > 0
      ? `${fmt(defaultCohortN)} resolved predictions — every outcome we measured except ` +
        `the ${fmt(unchangedN)} untraded ones, whose price never moved off its ` +
        `opening line (${fmt(fullN)} measured in all)`
      : `${fmt(defaultCohortN)} resolved predictions`,
    // "traded" is this module's ratified word for the default cohort, and it
    // covers the sportsbook rows correctly under D101 rather than apologising
    // for them. An empty excluded side excludes nothing, so it earns no
    // qualifier — the same rule `excluded` above follows.
    plainHeadlineScope: unchangedN > 0
      ? "Across every traded market we track"
      : "Across every market we track",
    partitionNote,
    reconciles,
  };
}

/** What the matched-bucket section says about which rows it holds. */
export interface ActivityScopeCopy {
  /**
   * One sentence in the section body, under the caption that makes the table
   * legible. Says which rows are NOT in either column, because the column
   * heading alone cannot.
   */
  caption: string;
  /**
   * The arithmetic, one tap down inside the section's own "What 'traded' means
   * here" note. Reconciles the two columns to the page's traded total.
   */
  reconciliation: string;
}

/**
 * The scope disclosure for the matched-bucket comparison (#7519).
 *
 * This section is the ONE place on the page where `price_moved` is the subject
 * rather than a filter, and that is what makes it the one place the page's own
 * vocabulary misdescribes. Its two columns are `true` vs `false`; the flagless
 * sportsbook rows are in NEITHER, because there is no price-move test to put
 * them on a side of.
 *
 * Everywhere else, "traded" means the default cohort — `true` PLUS `null` —
 * under UX-P080 item 3 (Alex, round 2): sportsbook lines are traded BY
 * CONSTRUCTION, a sportsbook moves its line with money. That ruling is right
 * and nothing here touches it. What it left behind is this: the page publishes
 * 449,027 traded outcomes and heads a column "Traded" over 293,900 of them.
 *
 * #7335 is the proximate cause and is also not the thing to undo. It renamed
 * these columns from "Price moved"/"Price unchanged" to the cohort nouns so the
 * page would stop naming two cohorts three ways (UX-P075 item (c), Alex
 * 2026-08-13). That rename is correct at every other site; it is only here that
 * the shared noun names a population the columns do not hold. So the fix is to
 * state the population, the way #7515 did for the category bar — never to
 * re-split the vocabulary the rename deliberately joined.
 *
 * `lib/calibrationCohort.ts` recorded the moment this opened up, in the comment
 * on `partitionNote`: that note "used to say sportsbook lines 'sit in neither
 * cohort' — true of the old framing, and now a contradiction of the copy
 * directly above it". True of the framing; still true of THESE TWO COLUMNS. It
 * was retired as page-wide copy for a good reason and the one section that
 * still needed it lost it. This puts it back, scoped to the section it is true
 * of.
 *
 * Returns null when there are no flagless rows — then the two columns ARE the
 * whole traded population, there is nothing outside them, and a note saying so
 * would be boilerplate on a payload it does not describe (same rule
 * `partitionNote` follows).
 */
export function describeActivityScope(
  partition: ActivityPartition
): ActivityScopeCopy | null {
  const { movedN, unchangedN, notApplicableN } = partition;
  if (notApplicableN <= 0) return null;

  return {
    // Notice 34 / D102: what the reader is handed WITHOUT a tap is the one fact
    // the column heading gets wrong — which rows are missing, and that they are
    // missing for a reason that is not "we don't count them". The arithmetic is
    // a method note and folds.
    caption:
      `Both columns are the price-moved test, so the ${fmt(notApplicableN)} ` +
      `sportsbook lines — traded, but never put to that test — are in neither.`,
    // The reconciliation states the page's OWN traded total beside the column's,
    // because the reader's question is not "how many are missing" but "is this
    // the Traded I was reading about two screens up". It is not, and saying the
    // two numbers next to each other is the only answer that settles it.
    reconciliation:
      `Here that makes two columns: ${fmt(movedN)} outcomes whose price moved ` +
      `and ${fmt(unchangedN)} whose price never did. The ` +
      `${fmt(notApplicableN)} sportsbook lines are counted as traded ` +
      `everywhere else on this page — a sportsbook moves its line with money — ` +
      `but there is no price move to test on them, so they sit outside this ` +
      `comparison rather than on one side of it. The page's traded total of ` +
      `${fmt(movedN + notApplicableN)} includes them; the Traded column here ` +
      `does not.`,
  };
}
