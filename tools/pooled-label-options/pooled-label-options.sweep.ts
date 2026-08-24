/**
 * UX-P120 item 2 — RENDER the three live options for the pooled-category rows.
 *
 * ## This is a mock generator, not a fix
 *
 * Fable's directive: "Pooled-category display is a TASTE call — Alex's, not
 * ours. Produce a one-pager with rendered examples ... No code beyond mocks,
 * ruling next cycle." So this script writes a one-pager and changes nothing the
 * page reads. It is the mock, and it exists so the one-pager quotes text that
 * was actually produced rather than text somebody typed into a document.
 *
 * ## Why generate the copy instead of writing it
 *
 * Three of the four harness proofs UX-P119 shipped were wrong in ways that only
 * execution exposed, and #2108 exists because a hand-written census ("exactly 2
 * of 128 rows pool") was quoted as fact in a comment for a whole cycle. A
 * hand-typed mock of a sentence that is DERIVED from data is the same mistake at
 * one remove: the sentence in the doc and the sentence the code would emit are
 * two things that can disagree, and only one of them ships.
 *
 * So every quoted string below is produced by calling the real
 * `describeCategoryPopulation` / `describeCategoryTablePopulation` (option C) or
 * by composing over real payload numbers (options A and B), against the live
 * payload the sweep already downloads.
 *
 * ## The three options, and which AXIS each one puts on screen
 *
 * From `tools/calibration-divergence/report-*.md`, four ECEs are reachable for
 * a pooled row and the page renders the one that is on none of them:
 *
 *   A) server key only, ALL rows       <- what `by_category` PUBLISHES
 *   B) server key only, cohort filter
 *   C) pooled keys,     ALL rows
 *   D) pooled keys,     cohort filter  <- what the PAGE RENDERS TODAY
 *
 * The directive's three options map onto these:
 *
 *   Option A  "cohort value with a pooled label"  -> render axis B
 *   Option B  "published value with a label"      -> render axis A
 *   Option C  "keep the pooled computation but
 *              name the fold on-screen"           -> render axis D (status quo)
 *
 * Naming the axis is what makes the choice unambiguous: the option labels are
 * prose and could be read two ways, the axis letters cannot.
 *
 * Run: `tools/pooled-label-options/run.sh`
 */

import * as fs from "fs";
import { normalizeCat, categoryLabel } from "@/lib/calibrationCategories";
import { aggregateBuckets, cohortFilterFor } from "@/lib/calibrationParity";
import { ece } from "@/lib/calibrationMath";
import {
  describeCategoryPopulation,
  describeCategoryTablePopulation,
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

const PAYLOAD = process.env.CAL_PAYLOAD || "/tmp/pooled-label-options/cal.json";
const OUT = process.env.OPTIONS_OUT || "/tmp/pooled-label-options.md";

/** The rendered precision — `page.tsx:1587` prints `.toFixed(1)`. */
const shown = (v: number | null): string => (v === null ? "—" : `${v.toFixed(1)}pp`);
const n0 = (v: number): string => v.toLocaleString("en-US");

/**
 * Enumerate a list without producing a wall of text.
 *
 * Soccer folds 55 payload categories. #2108 defect 3 is that the current
 * tooltip would print all of them, so the cap is not cosmetic — it is the
 * difference between a disclosure and an unreadable paragraph. The COUNT is
 * always stated, so capping never hides the size.
 */
function capped(cats: string[], cap = 4): string {
  if (cats.length <= cap) {
    if (cats.length <= 1) return cats[0] ?? "";
    return `${cats.slice(0, -1).join(", ")} and ${cats[cats.length - 1]}`;
  }
  return `${cats.slice(0, cap).join(", ")} and ${cats.length - cap} more`;
}

describe("pooled-category label options", () => {
  it("renders every live option for every pooled row", () => {
    const data = JSON.parse(fs.readFileSync(PAYLOAD, "utf8"));
    const buckets: RawBucket[] = data.buckets ?? [];
    const published: PublishedCategory[] = data.by_category ?? [];
    expect(buckets.length).toBeGreaterThan(0);

    // ---- the page's pipeline, transcribed (same as the divergence sweep) ---
    const normalized = buckets.map(b => ({ ...b, category: normalizeCat(b.category) }));
    const minCategoryOutcomes: number = data.min_category_outcomes ?? 1000;
    const cohortFilter = cohortFilterFor(false); // page default: exclude never-moved
    const catMap: Record<string, number> = {};
    for (const b of normalized) catMap[b.category] = (catMap[b.category] || 0) + b.n;
    const categories = Object.entries(catMap)
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

    const publishedFor = (name: string): PublishedCategory | null =>
      published.find(p => p.category === name) ?? null;

    /** ECE + n over a chosen key set, with or without the cohort filter. */
    const read = (keys: string[], cohort: boolean) => {
      const rows = buckets.filter(
        b => keys.includes(b.category) && (!cohort || cohortFilter(b))
      );
      if (!rows.length) return { ece: null as number | null, n: 0 };
      const agg = aggregateBuckets(rows);
      return { ece: ece(agg), n: agg.reduce((s, a) => s + a.n, 0) };
    };

    const pooledRows = categories
      .map(cat => ({ cat, members: [...(pooledByCategory.get(cat) ?? [])].sort() }))
      .filter(r => r.members.length > 1);

    const L: string[] = [];
    L.push("# Pooled-category display — the three live options, rendered");
    L.push("");
    L.push("UX-P120 item 2. **Mocks only. No code beyond this generator — the ruling is Alex's.**");
    L.push("");
    L.push(`- payload \`generated_at\`: \`${data.generated_at}\``);
    L.push(`- rendered rows: ${categories.length} · of which POOL more than one payload category: **${pooledRows.length}**`);
    L.push(`- cohort: page default (\`includeNeverMoved = false\`)`);
    L.push("");
    L.push("Every string below was produced by running this file against the live payload.");
    L.push("Options A and B are composed over real numbers; option C calls the page's own");
    L.push("`describeCategoryPopulation` unchanged, so it is literally today's text.");
    L.push("");
    L.push("## The axis each option puts on screen");
    L.push("");
    L.push("| | option | renders | can a reader reconstruct it from the payload? |");
    L.push("|---|---|---|---|");
    L.push("| **A** | cohort value with a pooled label | axis B — this row's OWN key, cohort-filtered | Yes — filter `price_moved != false`, one key |");
    L.push("| **B** | published value with a label | axis A — exactly `by_category` | Yes — it IS the published number |");
    L.push("| **C** | keep pooling, name the fold | axis D — pooled keys, cohort-filtered | Only if the fold is listed, which is the change |");
    L.push("");
    L.push("Today the page renders axis D with no fold named, which is why all");
    L.push(`**${pooledRows.length}** of these rows print a number that appears nowhere.`);
    L.push("");

    // ---- tradeoffs, with the cost of each MEASURED -------------------------
    //
    // Two lines each, per the directive. The first line of each pair is the
    // argument for it; the second is what it costs, and the cost is a number
    // read off this payload rather than an adjective.
    const totD = pooledRows.reduce((s, r) => s + read(r.members, true).n, 0);
    const totB = pooledRows.reduce((s, r) => s + read([r.cat], true).n, 0);
    const noTwin = pooledRows.filter(r => publishedFor(r.cat) === null);
    const worstFold = pooledRows.reduce((a, b) => (b.members.length > a.members.length ? b : a));
    L.push("## Tradeoffs");
    L.push("");
    L.push("**Option A — render axis B (own key, cohort).**");
    L.push(
      `Puts every row back on an axis a reader can rebuild, and the whole table stays one cohort.`
    );
    L.push(
      `Costs ${n0(totD - totB)} of ${n0(totD)} outcomes across these ${pooledRows.length} rows ` +
        `(${(((totD - totB) / totD) * 100).toFixed(0)}%) — the leagues stop counting toward their own sport.`
    );
    L.push("");
    L.push("**Option B — render axis A (exactly what the API publishes).**");
    L.push(
      `The number matches \`by_category\` byte for byte, so the "I curled it and it disagrees" complaint cannot arise.`
    );
    L.push(
      `Costs the cohort: this table alone would be all-resolved while every other figure on the page is traded-only` +
        (noTwin.length
          ? `, and ${noTwin.length} row(s) have no published twin at all and could not render.`
          : `, and it silently reintroduces never-moved outcomes the page excludes everywhere else.`)
    );
    L.push("");
    L.push("**Option C — keep axis D, name the fold.**");
    L.push(
      `Nothing recomputes, the biggest sample stays, and the number is derivable once the fold is stated.`
    );
    L.push(
      `Costs screen space and it does not scale: \`${worstFold.cat}\` folds ${worstFold.members.length} ` +
        `categories, and a capped list ("and N more") means the disclosure is once again not fully checkable.`
    );
    L.push("");

    // ---- the section-level sentence, all three ways ------------------------
    const renderedPooled = pooledRows.length;
    L.push("## The section sentence");
    L.push("");
    L.push("```");
    L.push("A: " + describeCategoryTablePopulation("excluding_never_moved", 0, categories.length));
    L.push("```");
    L.push("");
    L.push("```");
    L.push(
      "B: Every figure in this table is the whole-population number the API publishes in " +
        "`by_category`, so it will not reflect the traded-only cohort shown elsewhere on this page."
    );
    L.push("```");
    L.push("");
    L.push("```");
    L.push("C: " + describeCategoryTablePopulation("excluding_never_moved", renderedPooled, categories.length));
    L.push("```");
    L.push("");
    L.push(
      "Note C's numerator is **" +
        renderedPooled +
        "**, the RENDERED pooled rows — #2108 defect 2 is that the page passes 7 (all normalized keys, including the unrendered `mma`) against a denominator of 15 (rendered rows)."
    );
    L.push("");

    // ---- per row ------------------------------------------------------------
    L.push("## The rows");
    L.push("");
    for (const { cat, members } of pooledRows) {
      const twin = publishedFor(cat);
      const axisB = read([cat], true);
      const axisD = read(members, true);
      const pubMembers = members.filter(m => publishedFor(m) !== null);
      const unpubMembers = members.filter(m => publishedFor(m) === null);

      L.push(`### ${categoryLabel(cat)} (\`${cat}\`)`);
      L.push("");
      L.push(
        `Folds **${members.length}** payload categories, of which **${pubMembers.length}** ` +
          `${pubMembers.length === 1 ? "appears" : "appear"} in \`by_category\`. ` +
          `Axis A ${shown(twin?.ece ?? null)} · ` +
          `axis B ${shown(axisB.ece)} · axis D **${shown(axisD.ece)}** (on screen today).`
      );
      L.push("");
      L.push("```");
      L.push(`A  ${categoryLabel(cat)}   ${shown(axisB.ece)}   n=${n0(axisB.n)}`);
      L.push(
        `   This row is the “${cat}” category alone, measured over traded outcomes only. ` +
          `${members.length - 1} related payload categories (${capped(members.filter(m => m !== cat))}) ` +
          `are charted separately and are NOT in this figure.`
      );
      L.push("```");
      L.push("");
      L.push("```");
      L.push(
        `B  ${categoryLabel(cat)}   ${shown(twin?.ece ?? null)}   n=${twin ? n0(twin.n) : "—"}`
      );
      L.push(
        twin
          ? `   As published by the API for “${cat}”, over all resolved outcomes. ` +
              `Every other figure on this page is traded-only, so this column alone is not.`
          : `   NOT AVAILABLE — the API publishes no “${cat}” row, so this option cannot ` +
              `render this category at all.`
      );
      L.push("```");
      L.push("");
      const disclosure = describeCategoryPopulation(cat, members, published, "excluding_never_moved");
      L.push("```");
      L.push(`C  ${categoryLabel(cat)}   ${shown(axisD.ece)}   n=${n0(axisD.n)}`);
      L.push(`   ${disclosure.sentence}`);
      L.push("```");
      L.push("");
      if (unpubMembers.length) {
        L.push(
          `> C as written today calls all **${members.length}** members “published”. ` +
            `**${unpubMembers.length}** of them ${unpubMembers.length === 1 ? "is" : "are"} not in ` +
            `\`by_category\` and cannot be looked ` +
            `up (#2108 defect 3). A corrected C would read: pools ${pubMembers.length} published ` +
            `categor${pubMembers.length === 1 ? "y" : "ies"} (${capped(pubMembers)}) and ` +
            `${unpubMembers.length} unpublished (${capped(unpubMembers)}).`
        );
        L.push("");
      }
    }

    fs.writeFileSync(OUT, L.join("\n") + "\n");
    // eslint-disable-next-line no-console
    console.log(`wrote ${OUT}`);
  });
});
