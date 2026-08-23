/**
 * Which population a rendered calibration number describes (UX-P118, item 5).
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
 * The page's "Hockey" pools `hockey` with `icehockey_nhl` (3.48, n=10,616),
 * `icehockey_sweden_allsvenskan` (8.14, n=329) and
 * `icehockey_sweden_hockey_league` (4.24, n=730); the server's `hockey` is the
 * LLM category by itself.
 *
 * So a cohort-only note would attach the words "this is the traded cohort" to a
 * number that is the traded cohort **of a different set of categories** — a
 * label that reads as a full account and is not one. UX-P115's rule: a refusal
 * (or a disclosure) that is itself a false claim is worse than the bug it
 * replaces.
 *
 * Pooling is not everywhere and not nowhere: exactly **2 of 128** rows pool —
 * football and hockey — and hockey is the specimen the class was filed on. A
 * rule that fired on every row would be noise; one that fired on none would
 * have missed the case that prompted it.
 *
 * ── DERIVED, NOT WRITTEN ────────────────────────────────────────────────────
 *
 * Every sentence here is computed from the SAME inputs the number is computed
 * from — the pooled key set and the active cohort — so a label cannot drift
 * from the predicate it describes. That is the standing lesson of
 * `describeCohort`, whose comment records the two times a hand-guessed
 * condition disagreed with the copy beside it.
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

export interface PopulationDisclosure {
  /** The payload categories this displayed row is measured over, sorted. */
  pooledFrom: string[];
  /** True when the row pools more than one payload category. */
  pools: boolean;
  /**
   * The figure `by_category` publishes under this row's own name, when the
   * server publishes one. `null` when the displayed name is not a payload key
   * (so there is no published twin to reconcile against, and claiming one would
   * be inventing a disagreement).
   */
  publishedEce: number | null;
  publishedN: number | null;
  /** One sentence. Always names the cohort; names the pooling when it applies. */
  sentence: string;
  /** Compact tooltip form for the row cell. */
  title: string;
}

function label(cats: string[]): string {
  if (cats.length <= 1) return cats[0] ?? "";
  return `${cats.slice(0, -1).join(", ")} and ${cats[cats.length - 1]}`;
}

/**
 * Describe the population behind one rendered category row.
 *
 * The cohort arrives as its KEY, not as a rendered label: a label is a heading
 * and reads badly mid-sentence, and keying on the discriminant keeps this
 * exhaustive against a future third cohort.
 */
export function describeCategoryPopulation(
  displayed: string,
  pooledFrom: string[],
  published: PublishedCategory[],
  cohort: CohortKey
): PopulationDisclosure {
  const pooled = [...new Set(pooledFrom)].sort();
  const pools = pooled.length > 1;
  const twin = published.find(p => p.category === displayed) ?? null;

  const cohortClause = `measured over ${cohortPhrase(cohort)}`;

  // The pooling clause leads when it applies, because it is the larger and the
  // less guessable of the two differences: a reader can imagine a cohort filter,
  // but cannot imagine that "Hockey" silently means four payload categories.
  const poolingClause = pools
    ? `pools the published categories ${label(pooled)}`
    : null;

  const clauses = [poolingClause, cohortClause].filter(Boolean) as string[];

  let sentence = `This row ${clauses.join(", and is ")}.`;
  if (twin && twin.ece !== null) {
    sentence +=
      ` The API publishes ${twin.ece.toFixed(2)}pp for “${displayed}”` +
      ` over ${twin.n.toLocaleString()} outcomes` +
      (pools
        ? ` — that figure covers only the “${displayed}” category, and the whole population.`
        : ` — that figure covers the whole population, not this cohort.`);
  }

  return {
    pooledFrom: pooled,
    pools,
    publishedEce: twin?.ece ?? null,
    publishedN: twin?.n ?? null,
    sentence,
    title: sentence,
  };
}

/**
 * The section-level sentence: what the ECE column as a whole describes.
 *
 * Stated once at the top rather than repeated per row, because the cohort is a
 * property of the table and repeating it 128 times is how a disclosure becomes
 * furniture nobody reads.
 */
export function describeCategoryTablePopulation(
  cohort: CohortKey,
  pooledRowCount: number,
  totalRowCount: number
): string {
  const base =
    `Every figure in this table is measured over ${cohortPhrase(cohort)}, so it will not ` +
    `match the whole-population number the API publishes in \`by_category\` for ` +
    `the same name.`;
  if (pooledRowCount <= 0) return base;
  return (
    base +
    ` ${pooledRowCount} of ${totalRowCount} rows also pool several published ` +
    `categories under one label — hover a row to see exactly which.`
  );
}
