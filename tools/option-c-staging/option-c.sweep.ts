/**
 * UX-P122 item C — STAGE the ruled Option-C wording, generated from the live payload.
 *
 * ## What was ruled
 *
 * UX-P120 put three pooled-category display options in front of Alex as rendered
 * mocks (`tools/pooled-label-options/one-pager-2026-08-23.md`). **Alex ruled
 * OPTION C**, with five amendments, and every one of them is a correction to how
 * the fold is DESCRIBED rather than to the number:
 *
 *   1. the pooled number is KEPT — axis D, exactly what the page computes today
 *   2. the fold is NAMED
 *   3. member wording splits published from unpublished:
 *      "pools 1 published category (soccer) and 54 unpublished (…)"
 *   4. the member list is FULL and expandable — **a capped list is not checkable**
 *   5. an anchor sentence quotes the API's own `by_category` figure
 *   6. the section sentence's numerator is 6 — RENDERED pooled rows, never the 7
 *      normalized keys
 *
 * ## Why this is generated and not typed
 *
 * #2108 exists because a hand-written census — "exactly 2 of 128 rows pool" —
 * was quoted as fact in a source comment for a full cycle. The census then moved
 * **twice in two days with zero code change**: tennis went 3 → 4 published
 * members overnight because the payload gained a `by_category` row, and the
 * one-pager regenerated 108 diff lines seven hours after it was committed.
 *
 * A hand-typed staging doc for a DERIVED sentence is the same mistake at one
 * remove: the sentence in the doc and the sentence the code emits become two
 * objects that can disagree, and only one of them ships. So every count, every
 * member list and every figure below is computed here, at generation time, from
 * the live payload, by calling the page's own `normalizeCat` / `aggregateBuckets`
 * / `cohortFilterFor` / `ece`.
 *
 * ## What this file IS, for whoever implements it
 *
 * `describeCategoryPopulationOptionC` below is the deliverable — a drop-in
 * replacement for `describeCategoryPopulation`'s pooling clause, written against
 * the same signature. UX-P122 could not apply it: `frontend/lib/calibrationPopulation.ts`
 * sits in the unmerged stack's barred set and the write gate ("origin/master
 * contains ux-107") was CLOSED at both ends of the cycle. So it is staged here,
 * executed against production, and its output committed — a tested patch rather
 * than a proposal, the same posture UX-P120 took with `2108-disclosure-fix.patch`.
 *
 * **The emitted numbers are evidence, not a contract.** They are stamped with the
 * payload's `generated_at` precisely because they expire. The implementation must
 * derive its own; a test that asserts "soccer folds 55" is a test that fails on a
 * Tuesday.
 *
 * ## The one judgment call, stated rather than buried
 *
 * "Fold NAMED" and "FULL expandable member list" pull in different directions for
 * soccer, whose fold is 55 identifiers. Rendering all 55 inline is the wall of
 * text the ruling's own tradeoff line warned about; capping is explicitly
 * forbidden. This generator resolves it as:
 *
 *   - the SENTENCE names the counts and the PUBLISHED members inline — those are
 *     the few a reader can actually go and look up, and there are at most 7 today
 *   - the EXPANDER carries the full list of both sets, uncapped
 *
 * Nothing is capped anywhere, and the inline text stays a sentence. The
 * alternative — counts inline, both sets behind the expander — is emitted
 * alongside as `sentenceCountsOnly` so the choice is one line, not a rewrite.
 *
 * Run: `tools/option-c-staging/run.sh`
 */

import * as fs from "fs";
import * as path from "path";
import { normalizeCat, categoryLabel } from "@/lib/calibrationCategories";
import { aggregateBuckets, cohortFilterFor } from "@/lib/calibrationParity";
import { ece } from "@/lib/calibrationMath";
import { cohortPhrase } from "@/lib/calibrationPopulation";
import type { CohortKey } from "@/lib/calibrationCohort";

interface RawBucket {
  bucket_idx: number;
  source: string;
  category: string;
  price_moved: boolean | null;
  n: number;
  winners: number;
  sum_prob: number;
  sum_sq_err: number;
}

interface PublishedCategory {
  category: string;
  ece: number | null;
  n: number;
}

const PAYLOAD = process.env.OPTIONC_PAYLOAD || "/tmp/option-c-staging/cal.json";
const OUT_MD = process.env.OPTIONC_OUT_MD || "/tmp/option-c-staging/wording.md";
const OUT_JSON = process.env.OPTIONC_OUT_JSON || "/tmp/option-c-staging/wording.json";

const n0 = (v: number): string => v.toLocaleString("en-US");
/** The rendered precision — `page.tsx` prints `.toFixed(1)`. */
const shown = (v: number | null): string => (v === null ? "—" : `${v.toFixed(1)}pp`);

/**
 * Enumerate UNCAPPED. There is no `cap` parameter and that is the point of the
 * ruling: `MEMBER_NAME_CAP = 4` in the held `2108-disclosure-fix.patch` produced
 * "and 50 more", and a disclosure a reader cannot finish checking is a
 * disclosure that only technically said something.
 */
function nameAll(cats: string[]): string {
  if (cats.length === 0) return "";
  if (cats.length === 1) return cats[0];
  return `${cats.slice(0, -1).join(", ")} and ${cats[cats.length - 1]}`;
}

const plural = (n: number, one: string, many: string) => (n === 1 ? one : many);

export interface OptionCDisclosure {
  displayed: string;
  pooledFrom: string[];
  pools: boolean;
  /** Members the API publishes under their own name — a reader can verify these. */
  publishedMembers: string[];
  /** Members with no `by_category` row — naming them "published" is #2108 defect 3. */
  unpublishedMembers: string[];
  publishedEce: number | null;
  publishedN: number | null;
  /** Ruled wording: published members named inline, counts for both. */
  sentence: string;
  /** The alternative resolution — counts inline, every member behind the expander. */
  sentenceCountsOnly: string;
  /** The anchor: the API's own figure for this name, quoted (amendment 5). */
  anchorSentence: string | null;
  /** Tooltip form. Never the full 55-member wall. */
  title: string;
}

/**
 * The ruled Option-C disclosure for one rendered category row.
 *
 * Signature-compatible with `describeCategoryPopulation` so this lifts into
 * `frontend/lib/calibrationPopulation.ts` without a caller change.
 *
 * ** "published" is the load-bearing word and it must be earned. ** It is what
 * tells a reader they can go and verify a member. For soccer it was true of 1
 * member in 55, and the shipped sentence called all 55 published. That is the
 * same class of error as UX-P115's `SETTLED_NO_GRADE_LABEL`: a disclosure that
 * is itself a false claim is worse than the bug it replaces.
 */
export function describeCategoryPopulationOptionC(
  displayed: string,
  pooledFrom: string[],
  published: PublishedCategory[],
  cohort: CohortKey
): OptionCDisclosure {
  const pooled = [...new Set(pooledFrom)].sort();
  const pools = pooled.length > 1;
  const publishedNames = new Set(published.map(p => p.category));
  const pub = pooled.filter(c => publishedNames.has(c));
  const unpub = pooled.filter(c => !publishedNames.has(c));
  const twin = published.find(p => p.category === displayed) ?? null;

  const cohortClause = `measured over ${cohortPhrase(cohort)}`;

  // The pooling clause leads when it applies: a reader can imagine a cohort
  // filter, but cannot imagine that "Soccer" silently means 55 payload keys.
  let poolingClause: string | null = null;
  let poolingClauseCountsOnly: string | null = null;
  if (pools) {
    if (pub.length === 0) {
      poolingClause =
        `pools ${pooled.length} payload categories, none of them published in ` +
        `\`by_category\``;
      poolingClauseCountsOnly = poolingClause;
    } else if (unpub.length === 0) {
      poolingClause =
        `pools ${pub.length} published ${plural(pub.length, "category", "categories")} ` +
        `(${nameAll(pub)})`;
      poolingClauseCountsOnly =
        `pools ${pub.length} published ${plural(pub.length, "category", "categories")}`;
    } else {
      // Alex's ruled shape, verbatim in structure:
      //   "pools 1 published category (soccer) and 54 unpublished (…)"
      poolingClause =
        `pools ${pub.length} published ${plural(pub.length, "category", "categories")} ` +
        `(${nameAll(pub)}) and ${unpub.length} unpublished`;
      poolingClauseCountsOnly =
        `pools ${pub.length} published ${plural(pub.length, "category", "categories")} ` +
        `and ${unpub.length} unpublished`;
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
          : ` — that figure covers the whole population, not this cohort.`)
      : null;

  const sentence = [build(poolingClause), anchorSentence].filter(Boolean).join(" ");
  const sentenceCountsOnly = [build(poolingClauseCountsOnly), anchorSentence]
    .filter(Boolean)
    .join(" ");

  return {
    displayed,
    pooledFrom: pooled,
    pools,
    publishedMembers: pub,
    unpublishedMembers: unpub,
    publishedEce: twin?.ece ?? null,
    publishedN: twin?.n ?? null,
    sentence,
    sentenceCountsOnly,
    anchorSentence,
    title: sentenceCountsOnly,
  };
}

/**
 * The section sentence (amendment 6).
 *
 * ** Both arguments must come from the SAME population. ** The shipped page
 * passes 7 — every normalized key, including the unrendered `mma` — over 15,
 * the RENDERED rows. A reader who hovered all fifteen found six. A disclosure
 * whose own count does not survive being checked is worse than no disclosure.
 */
export function describeCategoryTablePopulationOptionC(
  cohort: CohortKey,
  pooledRenderedRows: number,
  renderedRows: number
): string {
  const base =
    `Every figure in this table is measured over ${cohortPhrase(cohort)}, so it will not ` +
    `match the whole-population number the API publishes in \`by_category\` for ` +
    `the same name.`;
  if (pooledRenderedRows <= 0) return base;
  return (
    base +
    ` ${pooledRenderedRows} of ${renderedRows} rows also pool several payload ` +
    `categories under one label — expand a row to see every one of them.`
  );
}

describe("option C — the ruled pooled-category wording", () => {
  it("stages the wording from the live payload", () => {
    const data = JSON.parse(fs.readFileSync(PAYLOAD, "utf8"));
    const buckets: RawBucket[] = data.buckets ?? [];
    const published: PublishedCategory[] = data.by_category ?? [];
    expect(buckets.length).toBeGreaterThan(0);

    // ---- the page's pipeline, transcribed ---------------------------------
    const normalized = buckets.map(b => ({ ...b, category: normalizeCat(b.category) }));
    const minCategoryOutcomes: number = data.min_category_outcomes ?? 1000;
    const cohortFilter = cohortFilterFor(false); // page default: exclude never-moved
    const catMap: Record<string, number> = {};
    for (const b of normalized) catMap[b.category] = (catMap[b.category] || 0) + b.n;
    const renderedKeys = Object.entries(catMap)
      .filter(([, n]) => n >= minCategoryOutcomes)
      .sort(([, a], [, b]) => b - a)
      .map(([cat]) => cat)
      .slice(0, 15);

    const pooledByCategory = new Map<string, string[]>();
    for (const b of buckets) {
      const key = normalizeCat(b.category);
      const seen = pooledByCategory.get(key);
      if (seen) {
        if (!seen.includes(b.category)) seen.push(b.category);
      } else {
        pooledByCategory.set(key, [b.category]);
      }
    }

    const read = (keys: string[], cohort: boolean) => {
      const rows = buckets.filter(
        b => keys.includes(b.category) && (!cohort || cohortFilter(b))
      );
      if (!rows.length) return { ece: null as number | null, n: 0 };
      const agg = aggregateBuckets(rows);
      return { ece: ece(agg), n: agg.reduce((s, a) => s + a.n, 0) };
    };

    // ---- the two populations amendment 6 is about --------------------------
    const pooledRendered = renderedKeys
      .map(cat => ({ cat, members: [...(pooledByCategory.get(cat) ?? [])].sort() }))
      .filter(r => r.members.length > 1);
    const allPooledKeys = [...pooledByCategory.entries()].filter(([, m]) => m.length > 1);
    const unrenderedPooled = allPooledKeys
      .map(([k]) => k)
      .filter(k => !renderedKeys.includes(k))
      .sort();

    const sectionSentence = describeCategoryTablePopulationOptionC(
      "excluding_never_moved",
      pooledRendered.length,
      renderedKeys.length
    );

    const rows = pooledRendered.map(({ cat, members }) => {
      const d = describeCategoryPopulationOptionC(
        cat,
        members,
        published,
        "excluding_never_moved"
      );
      const axisD = read(members, true);
      return { ...d, label: categoryLabel(cat), renderedEce: axisD.ece, renderedN: axisD.n };
    });

    // ---- machine-readable, for whoever implements this ---------------------
    const spec = {
      note:
        "VALUES EXPIRE — they are stamped with the payload they came from. The " +
        "implementation must derive its own; asserting these numbers in a test is " +
        "the #2108 defect reintroduced as a fixture.",
      generated_from_payload_at: data.generated_at,
      population_version: data.population_version ?? null,
      cohort: "excluding_never_moved",
      rendered_rows: renderedKeys.length,
      pooled_rendered_rows: pooledRendered.length,
      pooled_normalized_keys: allPooledKeys.length,
      unrendered_pooled_keys: unrenderedPooled,
      by_category_rows: published.length,
      section_sentence: sectionSentence,
      rows,
    };
    fs.mkdirSync(path.dirname(OUT_JSON), { recursive: true });
    fs.writeFileSync(OUT_JSON, JSON.stringify(spec, null, 2) + "\n");

    // ---- the human staging doc ---------------------------------------------
    const L: string[] = [];
    L.push("# Option C, as ruled — the wording, generated from the live payload");
    L.push("");
    L.push("UX-P122 item C. **Staging only.** `frontend/lib/calibrationPopulation.ts` is in");
    L.push("the unmerged stack's barred set and UX-P122's write gate was CLOSED, so this is");
    L.push("the tested content for `program/ux-108`, not an applied change.");
    L.push("");
    L.push(`- payload \`generated_at\`: \`${data.generated_at}\``);
    L.push(`- \`by_category\` rows published: **${published.length}**`);
    L.push(`- rendered rows: **${renderedKeys.length}** · of which POOL: **${pooledRendered.length}**`);
    L.push(
      `- normalized keys that pool: **${allPooledKeys.length}**` +
        (unrenderedPooled.length
          ? ` — ${unrenderedPooled.length} of them never reach the screen (${unrenderedPooled.join(", ")})`
          : "")
    );
    L.push("");
    L.push("**Amendment 6 is exactly this pair of numbers.** The shipped page passes");
    L.push(
      `\`${allPooledKeys.length}\` (every normalized key) over \`${renderedKeys.length}\` (rendered rows) — a fraction whose`
    );
    L.push(
      `halves come from two different populations. The numerator must be **${pooledRendered.length}**.`
    );
    L.push("");
    L.push("## The section sentence");
    L.push("");
    L.push("```");
    L.push(sectionSentence);
    L.push("```");
    L.push("");
    L.push("## The rows");
    L.push("");
    L.push(
      "Each row shows the sentence as ruled (published members named inline), the"
    );
    L.push(
      "counts-only alternative, and the FULL member list the expander must carry."
    );
    L.push("Nothing below is capped.");
    L.push("");

    for (const r of rows) {
      L.push(`### ${r.label} (\`${r.displayed}\`)`);
      L.push("");
      L.push(
        `Renders **${shown(r.renderedEce)}** over n=${n0(r.renderedN)} (axis D, unchanged). ` +
          `Folds **${r.pooledFrom.length}** payload categories: **${r.publishedMembers.length}** published, ` +
          `**${r.unpublishedMembers.length}** not.`
      );
      L.push("");
      L.push("```");
      L.push(r.sentence);
      L.push("```");
      L.push("");
      L.push("counts-only alternative:");
      L.push("");
      L.push("```");
      L.push(r.sentenceCountsOnly);
      L.push("```");
      L.push("");
      L.push(`<details><summary>full member list (${r.pooledFrom.length})</summary>`);
      L.push("");
      L.push(
        `- published in \`by_category\` (${r.publishedMembers.length}): ` +
          (r.publishedMembers.length ? r.publishedMembers.join(", ") : "_none_")
      );
      L.push(
        `- not published (${r.unpublishedMembers.length}): ` +
          (r.unpublishedMembers.length ? r.unpublishedMembers.join(", ") : "_none_")
      );
      L.push("");
      L.push("</details>");
      L.push("");
    }

    L.push("## What an implementation must NOT copy from this file");
    L.push("");
    L.push("Every number above is a reading of one payload. The census moved twice in two");
    L.push("days with no code change — tennis 3 → 4 published members overnight, and the");
    L.push("prior one-pager regenerated 108 diff lines seven hours after it was committed.");
    L.push("Copy the FUNCTIONS; derive the counts.");
    L.push("");

    fs.mkdirSync(path.dirname(OUT_MD), { recursive: true });
    fs.writeFileSync(OUT_MD, L.join("\n") + "\n");

    // ---- assertions: the generator must not emit a false disclosure ---------
    //
    // These are properties, not values, so they survive the census moving.
    for (const r of rows) {
      expect(r.publishedMembers.length + r.unpublishedMembers.length).toBe(
        r.pooledFrom.length
      );
      // No cap anywhere — the ruling's fourth amendment, asserted rather than
      // trusted. "and N more" is what a cap produces.
      expect(r.sentence).not.toMatch(/and \d+ more/);
      for (const m of r.publishedMembers) expect(r.sentence).toContain(m);
      // Amendment 3: no member may be swept under the word that invites a
      // reader to go and verify it unless the API actually publishes it.
      if (r.unpublishedMembers.length > 0) {
        expect(r.sentence).toContain(`${r.unpublishedMembers.length} unpublished`);
      }
      if (r.publishedEce !== null) {
        expect(r.anchorSentence).toContain("The API publishes");
      }
    }
    // Amendment 6, asserted as a relation between the two populations.
    expect(spec.pooled_rendered_rows).toBeLessThanOrEqual(spec.pooled_normalized_keys);
    expect(sectionSentence).toContain(
      `${pooledRendered.length} of ${renderedKeys.length} rows`
    );

    // eslint-disable-next-line no-console
    console.log(`wrote ${OUT_MD} and ${OUT_JSON}`);
  });
});
