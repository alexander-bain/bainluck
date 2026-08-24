/**
 * UX-P119 item 1 — the `normalizeCat` divergence sweep. MEASUREMENT ONLY.
 *
 * ## The question this answers
 *
 * UX-P118 measured, for hockey, that four different ECEs are reachable from one
 * payload and the page renders the fourth:
 *
 *   A) server key only, ALL rows       <- what `by_category` PUBLISHES
 *   B) server key only, cohort filter
 *   C) pooled keys,     ALL rows
 *   D) pooled keys,     cohort filter  <- what the PAGE RENDERS
 *
 * Hockey's D (2.25) matched neither the published 0.95 nor the directive's
 * cohort-only 1.94, because `normalizeCat` folds `icehockey_nhl` and two Swedish
 * leagues into one "Hockey" row. This sweep does that same read for EVERY
 * rendered category and reports which of them render a number that appears on
 * NO axis a reader could reconstruct.
 *
 * ## Why it executes the page's own functions
 *
 * `normalizeCat`, `aggregateBuckets`, `cohortFilterFor` and `ece` are imported,
 * not reimplemented. A reimplementation measures a copy — the exact failure mode
 * that caused `calibrationCategories.ts` to be extracted from the page in the
 * first place ("a guard that cannot call the function asserts against a copy of
 * it"). The selection pipeline below is transcribed from
 * `frontend/app/calibration/page.tsx` and each step cites its line.
 *
 * ## The comparison precision is the RENDERED precision, deliberately
 *
 * The table prints `cm.ece.toFixed(1)` (page.tsx:1587). A reader's complaint is
 * "the API says 0.95 and the screen says 2.3", so the divergence test is run at
 * one decimal place — what is actually on the screen — with full precision
 * carried alongside for diagnosis. Comparing at full float precision would
 * manufacture divergences no reader can see.
 *
 * ## This is not a gate
 *
 * It reads production and prints a table; it asserts only that the payload was
 * usable. A measurement whose numbers move when upstream data moves must never
 * be able to turn a deploy red. See the config's comment on the `.sweep.ts`
 * suffix.
 *
 * Run: `tools/calibration-divergence/run.sh`
 */

import * as fs from "fs";
import { normalizeCat, categoryLabel } from "@/lib/calibrationCategories";
import { aggregateBuckets, cohortFilterFor } from "@/lib/calibrationParity";
import { ece } from "@/lib/calibrationMath";

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

const PAYLOAD = process.env.CAL_PAYLOAD || "/tmp/calibration-divergence/cal.json";
const OUT = process.env.SWEEP_OUT || "/tmp/normalizeCat-divergence.md";

/** The rendered precision — `page.tsx:1587` prints `.toFixed(1)`. */
const shown = (v: number | null): string => (v === null ? "—" : v.toFixed(1));
/** Two numbers are "the same number" iff they print the same on the screen. */
const sameOnScreen = (a: number, b: number | null): boolean =>
  b !== null && a.toFixed(1) === b.toFixed(1);

describe("normalizeCat divergence sweep", () => {
  it("reads every rendered category against the live payload", () => {
    const data = JSON.parse(fs.readFileSync(PAYLOAD, "utf8"));
    const buckets: RawBucket[] = data.buckets ?? [];
    const published: PublishedCategory[] = data.by_category ?? [];
    expect(buckets.length).toBeGreaterThan(0);

    // ---- the page's pipeline, transcribed ---------------------------------
    // page.tsx:214-217
    const normalized = buckets.map(b => ({ ...b, category: normalizeCat(b.category) }));
    // page.tsx:300
    const minCategoryOutcomes: number = data.min_category_outcomes ?? 1000;
    // page.tsx:260 — the page defaults to EXCLUDING never-moved outcomes.
    const cohortFilter = cohortFilterFor(false);
    // page.tsx:302-313 — note the floor is applied to the FULL n, not the cohort n.
    const catMap: Record<string, number> = {};
    for (const b of normalized) catMap[b.category] = (catMap[b.category] || 0) + b.n;
    const categories = Object.entries(catMap)
      .filter(([, n]) => n >= minCategoryOutcomes)
      .sort(([, a], [, b]) => b - a)
      .map(([cat]) => cat)
      .slice(0, 15);

    // page.tsx:356-368 — the pre-image of each displayed row, from the RAW keys.
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

    const rows = categories.map(cat => {
      const pooledFrom = [...(pooledByCategory.get(cat) ?? [])].sort();
      const pools = pooledFrom.length > 1;

      // D — what the page renders. page.tsx:373-376.
      const dBuckets = aggregateBuckets(
        normalized,
        b => b.category === cat && (!cohortFilter || cohortFilter(b))
      );
      const D = ece(dBuckets);
      const dN = normalized
        .filter(b => b.category === cat && (!cohortFilter || cohortFilter(b)))
        .reduce((s, b) => s + b.n, 0);

      // C — pooled keys, ALL rows (cohort toggle flipped on).
      const C = ece(aggregateBuckets(normalized, b => b.category === cat));
      const cN = normalized
        .filter(b => b.category === cat)
        .reduce((s, b) => s + b.n, 0);

      // B — the SERVER's key alone, cohort filtered. Only defined when the
      // displayed name is itself a payload key; otherwise there is no server-key
      // reading to take and claiming one would invent a disagreement.
      const serverKeyExists = buckets.some(b => b.category === cat);
      const B = serverKeyExists
        ? ece(
            aggregateBuckets(
              buckets,
              b => b.category === cat && (!cohortFilter || cohortFilter(b))
            )
          )
        : null;

      // A — what the API publishes under this name.
      const twin = publishedFor(cat);
      const A = twin?.ece ?? null;

      // Per-member readings, so a reader can see what got folded in.
      const members = pooledFrom.map(raw => {
        const mAll = ece(aggregateBuckets(buckets, b => b.category === raw));
        const mN = buckets.filter(b => b.category === raw).reduce((s, b) => s + b.n, 0);
        const mPub = publishedFor(raw);
        return { raw, ece: mAll, n: mN, publishedEce: mPub?.ece ?? null };
      });

      // Which axis, if any, does the RENDERED number sit on?
      const onA = sameOnScreen(D, A);
      const onB = sameOnScreen(D, B);
      const onC = sameOnScreen(D, C);
      const onMember = members.some(m => sameOnScreen(D, m.publishedEce));
      const axes: string[] = [];
      if (onA) axes.push("A (published)");
      if (onB) axes.push("B (server key + cohort)");
      if (onC) axes.push("C (pooled + all)");
      if (onMember) axes.push("member published");

      return {
        cat,
        label: categoryLabel(cat),
        pooledFrom,
        pools,
        A,
        aN: twin?.n ?? null,
        B,
        C,
        cN,
        D,
        dN,
        axes,
        appearsNowhere: axes.length === 0,
        hasPublishedTwin: A !== null,
      };
    });

    // ---- report ------------------------------------------------------------
    const L: string[] = [];
    L.push("# `normalizeCat` divergence sweep — every rendered category");
    L.push("");
    L.push("UX-P119 item 1. **Measurement only — no fix in this queue.**");
    L.push("");
    L.push(`- payload \`generated_at\`: \`${data.generated_at}\``);
    L.push(`- buckets: ${buckets.length} · published \`by_category\` rows: ${published.length}`);
    L.push(`- \`min_category_outcomes\`: ${minCategoryOutcomes}`);
    const rawKeys = new Set(buckets.map(b => b.category));
    const poolingKeysAll = [...pooledByCategory.entries()].filter(([, v]) => v.length > 1);
    L.push(`- distinct RAW payload categories in \`buckets\`: ${rawKeys.size}`);
    L.push(`- distinct keys after \`normalizeCat\`: ${pooledByCategory.size}`);
    L.push(
      `- keys that pool, across ALL normalized keys (not only rendered): ` +
        `${poolingKeysAll.length} of ${pooledByCategory.size} — ` +
        poolingKeysAll.map(([k, v]) => `\`${k}\`(${v.length})`).join(", ")
    );
    L.push(`- rendered rows (top 15 over the floor): ${categories.length}`);
    L.push(
      `- rendered rows that POOL more than one payload category: ${rows.filter(r => r.pools).length}`
    );
    // How many members of each pooling row are actually PUBLISHED. The shipped
    // disclosure sentence says "pools the published categories …", so a member
    // that is not in `by_category` makes that sentence false about itself.
    const publishedNames = new Set(published.map(p => p.category));
    for (const r of rows.filter(x => x.pools)) {
      const pub = r.pooledFrom.filter(c => publishedNames.has(c)).length;
      L.push(
        `  - \`${r.cat}\`: ${r.pooledFrom.length} members, ${pub} of them published in \`by_category\``
      );
    }
    L.push("");
    L.push(
      "Cohort is the page default (`includeNeverMoved = false`), i.e. `price_moved !== false`."
    );
    L.push("Values are shown at the RENDERED precision (`toFixed(1)`), which is the");
    L.push("precision at which a reader can call two numbers different.");
    L.push("");
    L.push("## The table");
    L.push("");
    L.push(
      "| # | rendered row | cohorts folded in | A published | B key+cohort | C pooled+all | **D RENDERED** | D appears on |"
    );
    L.push("|---|---|---|---|---|---|---|---|");
    rows.forEach((r, i) => {
      const folded = r.pools
        ? r.pooledFrom.map(c => `\`${c}\``).join(" + ")
        : `\`${r.pooledFrom[0] ?? r.cat}\` (none)`;
      L.push(
        `| ${i + 1} | ${r.label} (\`${r.cat}\`) | ${folded} | ${shown(r.A)} | ${shown(
          r.B
        )} | ${shown(r.C)} | **${shown(r.D)}** | ${
          r.axes.length ? r.axes.join(", ") : "**NOWHERE**"
        } |`
      );
    });
    L.push("");
    L.push("## The answer — rows rendering a number that appears nowhere");
    L.push("");
    const nowhere = rows.filter(r => r.appearsNowhere);
    if (!nowhere.length) {
      L.push("_None._");
    } else {
      L.push(
        `**${nowhere.length} of ${rows.length}** rendered rows print an ECE that is on no`
      );
      L.push("axis a reader can reconstruct from the published payload.");
      L.push("");
      for (const r of nowhere) {
        L.push(
          `### ${r.label} (\`${r.cat}\`) — renders **${shown(r.D)}pp** over ${r.dN.toLocaleString()} outcomes`
        );
        L.push("");
        L.push(
          `- published for this name: ${
            r.hasPublishedTwin ? `**${shown(r.A)}pp** over ${r.aN?.toLocaleString()}` : "_not a payload key_"
          }`
        );
        L.push(`- pools ${r.pooledFrom.length} payload categor${r.pooledFrom.length === 1 ? "y" : "ies"}: ${r.pooledFrom.map(c => `\`${c}\``).join(", ")}`);
        L.push(
          `- other readings: B ${shown(r.B)} · C ${shown(r.C)} (n=${r.cN.toLocaleString()})`
        );
        L.push("");
      }
    }
    L.push("## Every pooling row, member by member");
    L.push("");
    for (const r of rows.filter(x => x.pools)) {
      L.push(`**${r.label}** renders ${shown(r.D)}pp and folds:`);
      for (const raw of r.pooledFrom) {
        const mAll = ece(aggregateBuckets(buckets, b => b.category === raw));
        const mN = buckets.filter(b => b.category === raw).reduce((s, b) => s + b.n, 0);
        const mPub = publishedFor(raw);
        L.push(
          `- \`${raw}\` — all-rows ECE ${shown(mAll)}pp, n=${mN.toLocaleString()}` +
            (mPub?.ece != null ? `, published ${shown(mPub.ece)}pp` : ", not published")
        );
      }
      L.push("");
    }
    L.push("## Published categories that no rendered row is measured over");
    L.push("");
    const renderedKeys = new Set(categories);
    const orphans = published.filter(p => {
      const folded = normalizeCat(p.category);
      return !renderedKeys.has(folded);
    });
    if (!orphans.length) L.push("_None._");
    else {
      L.push("These are published by the API but below the floor or outside the top 15,");
      L.push("so a reader who curls the API sees a category the page never shows.");
      L.push("");
      for (const p of orphans.sort((a, b) => b.n - a.n)) {
        L.push(
          `- \`${p.category}\` — published ${shown(p.ece)}pp over ${p.n.toLocaleString()} (folds to \`${normalizeCat(p.category)}\`)`
        );
      }
    }
    L.push("");

    fs.writeFileSync(OUT, L.join("\n"));
    // eslint-disable-next-line no-console
    console.log(L.join("\n"));
    // eslint-disable-next-line no-console
    console.log(`\n[sweep] wrote ${OUT}`);
  });
});
