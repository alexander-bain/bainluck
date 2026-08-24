/**
 * Which population a rendered calibration number describes (UX-P118 item 5;
 * #2108; Option C as ruled, UX-P125).
 *
 * ── TWO TRUTHS, NOT ONE DEFECT ──────────────────────────────────────────────
 *
 * `GET /api/calibration` publishes a per-category ECE in `by_category`, and this
 * page renders its own. They disagree, and both are correct about their own
 * population. Measured on the live payload, 2026-08-21, for hockey:
 *
 *   A) server key only, ALL rows       n=35416  ece=0.95   <- by_category PUBLISHES
 *   B) server key only, cohort filter  n=15383  ece=1.94
 *   C) pooled keys,     ALL rows       n=47091  ece=1.38
 *   D) pooled keys,     cohort filter  n=27058  ece=2.25   <- the PAGE RENDERS
 *
 * Unlabelled, a skeptical reader who curls the API and compares to the screen
 * finds 0.95 against 2.25 and concludes the page is lying. It is not. But the
 * page never said which of the four it was showing, and "trust us" is not
 * available to a surface whose entire job is credibility.
 *
 * ── THE DISCLOSURE MUST NAME BOTH AXES OR IT IS ITSELF FALSE ────────────────
 *
 * The tempting fix is one sentence about the cohort. That is the difference
 * between A and B, and it is NOT the difference between A and what is on the
 * screen: `normalizeCat` also folds several payload categories into one row.
 *
 * So a cohort-only note would attach the words "this is the traded cohort" to a
 * number that is the traded cohort **of a different set of categories** — a
 * label that reads as a full account and is not one. UX-P115's rule: a refusal
 * (or a disclosure) that is itself a false claim is worse than the bug it
 * replaces.
 *
 * ── #2108: THE CENSUS IN THIS COMMENT WAS FALSE, AND STAYED FALSE ───────────
 *
 * This block used to assert "exactly **2 of 128** rows pool — football and
 * hockey". Every part of that was wrong and none of it was checkable from here:
 * the table renders at most 15 rows (not 128), and on the payload measured at
 * apply time (`generated_at 2026-08-24T05:36:13Z`, 1,952 buckets, 34
 * `by_category` rows) **6 of the 15 rendered rows pool** — baseball, basketball,
 * soccer, tennis, hockey and football — while 7 normalized keys pool in total
 * (`mma` pools but never reaches the screen).
 *
 * That census is a reading of one payload and it EXPIRES. It moved twice in two
 * days with zero code change: tennis went 3 → 4 published members overnight
 * because the payload gained a `by_category` row. Nothing below reads it. It is
 * here stamped so the next person can tell a stale sentence from a current one,
 * which is the property the old comment lacked.
 *
 * ── DERIVED, NOT WRITTEN ────────────────────────────────────────────────────
 *
 * Every sentence here is computed from the SAME inputs the number is computed
 * from — the pooled key set, the published set, and the active cohort — so a
 * label cannot drift from the predicate it describes. That is the standing
 * lesson of `describeCohort`, whose comment records the two times a hand-guessed
 * condition disagreed with the copy beside it.
 *
 * ── OPTION C, AS RULED (five amendments) ────────────────────────────────────
 *
 *   1. the pooled number is KEPT — axis D, exactly what the page computes today
 *   2. the fold is NAMED
 *   3. members split published from unpublished — "published" invites a reader
 *      to go and verify, so it must be earned per member
 *   4. the member list is FULL and expandable. The COLLAPSED sentence may cap
 *      the inline names (soccer folds 55 identifiers; inlining them is the wall
 *      of text the ruling's own tradeoff line warned about) — **a cap marker is
 *      legal only because the expansion carries the complete list.** Take the
 *      expander away and the cap becomes the #2108 defect again.
 *   5. an anchor sentence quotes the API's own `by_category` figure
 *   6. the section numerator is RENDERED pooled rows, never the normalized keys
 */

import type { CohortKey } from "./calibrationCohort";

/**
 * The cohort as a noun phrase that reads inside a sentence.
 *
 * Keyed on `CohortKey` — the existing machine-readable discriminant — and NOT
 * on `shortLabel`, which is a heading ("Traded", "All markets") and produces
 * "measured over traded" when dropped into prose. A `Record<CohortKey, …>` is
 * exhaustive, so adding a third cohort is a type error here rather than a
 * silently unlabelled number on the page.
 *
 * This is the one place this module says anything about the cohort; the
 * vocabulary itself still belongs to `describeCohort`.
 */
const COHORT_PHRASE: Record<CohortKey, string> = {
  all: "all resolved outcomes",
  excluding_never_moved: "traded outcomes only",
};

export function cohortPhrase(key: CohortKey): string {
  return COHORT_PHRASE[key];
}

/** A payload category, as published, with the figure published for it. */
export interface PublishedCategory {
  category: string;
  ece: number | null;
  n: number;
}

/**
 * How many published member names the COLLAPSED sentence spells out before it
 * collapses the tail to "and N more".
 *
 * This is legal only in the collapsed form, and only because
 * `publishedMembers` / `unpublishedMembers` below are complete and the row's
 * expander renders both in full. `capApplied` is published alongside so a
 * caller (or a test) can assert that pairing rather than assume it.
 */
export const MEMBER_NAME_CAP = 4;

export interface PopulationDisclosure {
  /** The row's displayed key, as passed in. */
  displayed: string;
  /** The payload categories this displayed row is measured over, sorted. */
  pooledFrom: string[];
  /** True when the row pools more than one payload category. */
  pools: boolean;
  /**
   * Members the API publishes under their own name. COMPLETE and uncapped —
   * this is what the expander renders, and what makes the collapsed sentence's
   * cap marker honest.
   */
  publishedMembers: string[];
  /**
   * Members with no `by_category` row. COMPLETE and uncapped. Calling these
   * "published categories" was #2108's third defect: it told a reader to go and
   * look up 54 identifiers the API does not publish.
   */
  unpublishedMembers: string[];
  /** True when `sentence` collapsed part of the published list to "and N more". */
  capApplied: boolean;
  /**
   * The figure `by_category` publishes under this row's own name, when the
   * server publishes one. `null` when the displayed name is not a payload key
   * (so there is no published twin to reconcile against, and claiming one would
   * be inventing a disagreement).
   */
  publishedEce: number | null;
  publishedN: number | null;
  /**
   * One sentence: names the fold, splits published from unpublished, names the
   * cohort, and ends with the anchor. The inline published list is capped at
   * `MEMBER_NAME_CAP`; the full list lives in the two member arrays above.
   */
  sentence: string;
  /** The anchor on its own (amendment 5), for rendering it as its own line. */
  anchorSentence: string | null;
  /** Compact tooltip form — counts only, never a 55-member wall. */
  title: string;
}

/** Enumerate every member, uncapped. What the expander renders. */
export function nameAll(cats: string[]): string {
  if (cats.length === 0) return "";
  if (cats.length === 1) return cats[0];
  return `${cats.slice(0, -1).join(", ")} and ${cats[cats.length - 1]}`;
}

/** Enumerate at most `cap` members, collapsing the tail to "and N more". */
function nameCapped(cats: string[], cap: number): string {
  if (cats.length <= cap) return nameAll(cats);
  return `${cats.slice(0, cap).join(", ")} and ${cats.length - cap} more`;
}

const plural = (n: number, one: string, many: string) => (n === 1 ? one : many);

/**
 * Describe the population behind one rendered category row.
 *
 * The cohort arrives as its KEY, not as a rendered label: a label is a heading
 * and reads badly mid-sentence, and keying on the discriminant keeps this
 * exhaustive against a future third cohort.
 *
 * ** "published" is the load-bearing word and it must be earned. ** It is what
 * tells a reader they can go and verify a member. For soccer it was true of 1
 * member in 55, and the shipped sentence called all 55 published. That is the
 * same class of error as UX-P115's `SETTLED_NO_GRADE_LABEL`: a disclosure that
 * is itself a false claim is worse than the bug it replaces.
 */
export function describeCategoryPopulation(
  displayed: string,
  pooledFrom: string[],
  published: PublishedCategory[],
  cohort: CohortKey
): PopulationDisclosure {
  const pooled = [...new Set(pooledFrom)].sort();
  const pools = pooled.length > 1;
  const publishedNames = new Set(published.map(p => p.category));
  const pub = pooled.filter(c => publishedNames.has(c));
  const unpub = pooled.filter(c => !publishedNames.has(c));
  const twin = published.find(p => p.category === displayed) ?? null;

  const cohortClause = `measured over ${cohortPhrase(cohort)}`;

  // The pooling clause leads when it applies, because it is the larger and the
  // less guessable of the two differences: a reader can imagine a cohort filter,
  // but cannot imagine that "Soccer" silently means 55 payload keys.
  let poolingClause: string | null = null;
  let poolingClauseCountsOnly: string | null = null;
  let capApplied = false;
  if (pools) {
    const noun = plural(pub.length, "category", "categories");
    if (pub.length === 0) {
      poolingClause =
        `pools ${pooled.length} payload categories, none of them published in ` +
        "`by_category`";
      poolingClauseCountsOnly = poolingClause;
    } else if (unpub.length === 0) {
      capApplied = pub.length > MEMBER_NAME_CAP;
      poolingClause = `pools ${pub.length} published ${noun} (${nameCapped(pub, MEMBER_NAME_CAP)})`;
      poolingClauseCountsOnly = `pools ${pub.length} published ${noun}`;
    } else {
      // Alex's ruled shape, verbatim in structure:
      //   "pools 1 published category (soccer) and 54 unpublished"
      capApplied = pub.length > MEMBER_NAME_CAP;
      poolingClause =
        `pools ${pub.length} published ${noun} ` +
        `(${nameCapped(pub, MEMBER_NAME_CAP)}) and ${unpub.length} unpublished`;
      poolingClauseCountsOnly =
        `pools ${pub.length} published ${noun} and ${unpub.length} unpublished`;
    }
  }

  const build = (clause: string | null) => {
    const clauses = [clause, cohortClause].filter(Boolean) as string[];
    return `This row ${clauses.join(", and is ")}.`;
  };

  // Amendment 5 — the anchor. Quoting the API's own figure is what lets a
  // skeptical reader reconcile the two numbers instead of picking one. Omitted
  // when the displayed name is not a payload key at all: there is no published
  // twin, and inventing a disagreement is worse than naming none.
  const anchorSentence =
    twin && twin.ece !== null
      ? `The API publishes ${twin.ece.toFixed(2)}pp for “${displayed}” over ` +
        `${twin.n.toLocaleString()} outcomes` +
        (pools
          ? ` — that figure covers the “${displayed}” category alone, over the whole population.`
          : " — that figure covers the whole population, not this cohort.")
      : null;

  return {
    displayed,
    pooledFrom: pooled,
    pools,
    publishedMembers: pub,
    unpublishedMembers: unpub,
    capApplied,
    publishedEce: twin?.ece ?? null,
    publishedN: twin?.n ?? null,
    sentence: [build(poolingClause), anchorSentence].filter(Boolean).join(" "),
    anchorSentence,
    title: [build(poolingClauseCountsOnly), anchorSentence].filter(Boolean).join(" "),
  };
}

/**
 * The section-level sentence: what the ECE column as a whole describes.
 *
 * Stated once at the top rather than repeated per row, because the cohort is a
 * property of the table and repeating it fifteen times is how a disclosure
 * becomes furniture nobody reads.
 *
 * ** Both counts must come from the SAME population (amendment 6). ** The
 * shipped page passed every normalized key that pools — including keys that
 * never reach the screen — over the RENDERED row count. A reader who hovered
 * every row found fewer than the numerator promised. A disclosure whose own
 * count does not survive being checked is worse than no disclosure.
 */
export function describeCategoryTablePopulation(
  cohort: CohortKey,
  pooledRenderedRows: number,
  renderedRows: number
): string {
  const base =
    `Every figure in this table is measured over ${cohortPhrase(cohort)}, so it will not ` +
    "match the whole-population number the API publishes in `by_category` for " +
    "the same name.";
  if (pooledRenderedRows <= 0) return base;
  return (
    base +
    ` ${pooledRenderedRows} of ${renderedRows} rows also pool several payload ` +
    "categories under one label — expand a row to see every one of them."
  );
}
