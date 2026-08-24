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
 *   4. the member list is FULL and expandable. Refined by Alex 2026-08-24 to
 *      **cap-collapsed + FULL expansion**: the collapsed sentence may cap the
 *      inline names, and that is legal only because the expansion is complete
 *   5. an anchor sentence quotes the API's own `by_category` figure
 *   6. the section sentence's numerator is the RENDERED pooled rows, never the
 *      normalized keys — two different populations in one fraction
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
 * ## What this file IS — AS OF UX-P125, A DIVERGENCE SWEEP, NOT A STAGING DOC
 *
 * It used to carry its own copy of the deliverable, because UX-P122's write gate
 * ("origin/master contains ux-107") was CLOSED at both ends of the cycle and
 * `frontend/lib/calibrationPopulation.ts` sat in the unmerged stack's barred set.
 * The gate is now OPEN and the functions have LANDED in that module. So this file
 * no longer defines them — **it imports the shipped ones** and runs them against
 * the live payload.
 *
 * That is the whole point of the change. Two copies of a derived sentence are two
 * objects that can disagree, and only one of them ships; a staging doc for a
 * sentence the page computes is the #2108 mistake at one remove. Importing means
 * a divergence between the swept wording and the rendered wording is not possible
 * rather than merely unlikely.
 *
 * **The emitted numbers are evidence, not a contract.** They are stamped with the
 * payload's `generated_at` precisely because they expire. Nothing may assert
 * them; a test that asserts "soccer folds 55" is a test that fails on a Tuesday.
 *
 * ## The one judgment call, stated rather than buried
 *
 * "Fold NAMED" and "FULL expandable member list" pull in different directions for
 * soccer, whose fold is 55 identifiers. Rendering all 55 inline is the wall of
 * text the ruling's own tradeoff line warned about. Alex ruled it
 * **cap-collapsed with a FULL expansion**:
 *
 *   - the SENTENCE names the counts, and the published members inline up to
 *     `MEMBER_NAME_CAP`, collapsing the tail to "and N more"
 *   - the EXPANDER carries every member of both sets, uncapped
 *
 * So the assertion below is NOT "never cap" — that was the pre-ruling reading,
 * and it is now backwards. It is: **a cap marker is legal iff the expanded form
 * carries the complete list.** A cap with nowhere to finish reading it is #2108;
 * a cap in front of a complete expansion is a sentence that stayed a sentence.
 *
 * Run: `tools/option-c-staging/run.sh`
 */

import * as fs from "fs";
import * as path from "path";
import { normalizeCat, categoryLabel } from "@/lib/calibrationCategories";
import { aggregateBuckets, cohortFilterFor } from "@/lib/calibrationParity";
import { ece } from "@/lib/calibrationMath";
// THE SHIPPED FUNCTIONS. Imported, never re-implemented — see the header.
import {
  MEMBER_NAME_CAP,
  describeCategoryPopulation,
  describeCategoryTablePopulation,
  nameAll,
} from "@/lib/calibrationPopulation";

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

    const sectionSentence = describeCategoryTablePopulation(
      "excluding_never_moved",
      pooledRendered.length,
      renderedKeys.length
    );

    const rows = pooledRendered.map(({ cat, members }) => {
      const d = describeCategoryPopulation(
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
    L.push("UX-P125 (was UX-P122 item C). **APPLIED.** This is no longer a staging doc:");
    L.push("the functions below are imported from the shipped");
    L.push("`frontend/lib/calibrationPopulation.ts`, so what is printed here is what the");
    L.push("page renders — a divergence sweep, not a proposal.");
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
    L.push("**Amendment 6 is exactly this pair of numbers.** The pre-UX-P125 page passed");
    L.push(
      `\`${allPooledKeys.length}\` (every normalized key) over \`${renderedKeys.length}\` (rendered rows) — a fraction whose`
    );
    L.push(
      `halves came from two different populations. The numerator is now **${pooledRendered.length}**,` +
        " taken from the rendered rows, and this sweep asserts the section sentence agrees."
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
      "Each row shows the collapsed sentence as ruled (published members inline,"
    );
    L.push(
      `capped at ${MEMBER_NAME_CAP}), the counts-only tooltip, and the FULL member list the`
    );
    L.push("expander carries. THE EXPANSION IS NEVER CAPPED — that is what makes the");
    L.push("collapsed form's \"and N more\" legal rather than a #2108 reprise.");
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
      L.push("tooltip (counts only — never the member wall):");
      L.push("");
      L.push("```");
      L.push(r.title);
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

      // ---- amendment 4, RE-POINTED (Alex, 2026-08-24) ----------------------
      //
      // This assertion used to read `expect(r.sentence).not.toMatch(/and \d+
      // more/)` — "no cap anywhere". That reading is now BACKWARDS: the ruling
      // was refined to cap-collapsed + FULL expansion, so a cap marker in the
      // collapsed sentence is legal. What it is legal *because of* is the thing
      // to assert.
      //
      // So: a cap marker is legal IFF the expanded form carries the complete
      // list. Concretely — the two member arrays partition the fold (above),
      // the expansion enumerates every one of them, the expansion itself never
      // caps, and `capApplied` agrees with what the sentence actually did. A
      // cap that hides members from the expansion too is #2108 with extra
      // steps; a cap the flag denies is a disclosure lying about its own shape.
      const expansion = [
        nameAll(r.publishedMembers),
        nameAll(r.unpublishedMembers),
      ].join(" ");
      for (const m of r.pooledFrom) expect(expansion).toContain(m);
      expect(expansion).not.toMatch(/and \d+ more/);

      const capped = /and \d+ more/.test(r.sentence);
      expect(capped).toBe(r.capApplied);
      if (capped) {
        // A cap only ever collapses the PUBLISHED inline list, and only past
        // the cap. Anything else is a different defect wearing this one's
        // clothes.
        expect(r.publishedMembers.length).toBeGreaterThan(MEMBER_NAME_CAP);
        for (const m of r.publishedMembers.slice(0, MEMBER_NAME_CAP)) {
          expect(r.sentence).toContain(m);
        }
        expect(r.sentence).toContain(
          `and ${r.publishedMembers.length - MEMBER_NAME_CAP} more`
        );
      } else {
        for (const m of r.publishedMembers) expect(r.sentence).toContain(m);
      }
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
