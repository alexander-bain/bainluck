import fs from "fs";
import path from "path";

import { priceCadenceNote } from "@/lib/priceCadenceCopy";

/**
 * UX-P068 (#1803) leg 3 — the sparse-history footnote must not promise updates
 * that can never come, and only ONE file may build it.
 *
 * THE DEFECT. `/event/golf/the-masters` showed "Round 3 Leader: McIlroy 80%,
 * Young 11%" under a SETTLED banner on a tournament that finished 2026-04-12,
 * and directly beneath the chart it promised "Prices update every 1–2 hours for
 * this market". The backend legs of #1803 fix the ladder; this leg fixes the
 * promise, which travelled an entirely independent path and was gated on
 * `totalPoints < 2` alone — with no settled-awareness anywhere on it.
 *
 * WHY THAT GATE COULD NEVER HAVE BEEN RIGHT. Sparseness and settledness are
 * different facts. "Few points" answers *how much history exists*; it says
 * nothing about *whether the question is still open*. And the two correlate
 * backwards: a market that stopped trading in April has almost no recent points,
 * so the sparse branch is the branch a settled market is MOST likely to take.
 * The copy promising motion appeared precisely where motion is impossible.
 *
 * ── THE #1620 HALF ──
 *
 * Three sites printed this string and they had ALREADY drifted before anyone
 * touched them: `FuturesChart.tsx` and `app/futures/[id]/page.tsx:659` spelled
 * it with an EN DASH (`1{"–"}2`), while `page.tsx:678` used a HYPHEN
 * (`1{"-"}2`). Nobody chose that; it is just what three copies do. Fourteenth
 * instance of this shape on this lane.
 *
 * So, exactly as `resolvesLabelAuthority.test.ts` does for "Resolves <date>",
 * the guard below READS THE TREE and fails on a new construction of the string.
 * A unit test proves today's three callers agree; it does nothing about the
 * fourth copy someone writes next month.
 */

const FRONTEND = path.resolve(__dirname, "..", "..");

/** Comments out, code in — a MENTION in a docstring is not a CONSTRUCTION. */
function stripComments(src: string): string {
  return src.replace(/\/\*[\s\S]*?\*\//g, "").replace(/(^|[^:])\/\/.*$/gm, "$1");
}

/**
 * What a construction of this string looks like. Deliberately tolerant of the
 * dash the drift was made of: en dash, em dash, hyphen, or a JSX-escaped
 * `1{"–"}2`, all match. A guard that only caught the spelling we happen to use
 * today would miss the next copy for exactly the reason the last one drifted.
 */
const CONSTRUCTION = /Prices update every 1\s*(?:\{["'`][-–—]["'`]\}|[-–—])\s*2 hours/;

function cadenceConstructionSites(): string[] {
  const hits: string[] = [];
  const walk = (dir: string) => {
    for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
      if (entry.name === "node_modules" || entry.name.startsWith(".")) continue;
      const full = path.join(dir, entry.name);
      if (entry.isDirectory()) {
        walk(full);
        continue;
      }
      if (!/\.(ts|tsx)$/.test(entry.name)) continue;
      if (CONSTRUCTION.test(stripComments(fs.readFileSync(full, "utf8")))) {
        hits.push(path.relative(FRONTEND, full));
      }
    }
  };
  for (const root of ["components", "lib", "app"]) walk(path.join(FRONTEND, root));
  return [...new Set(hits)].sort();
}

const AUTHORITY = "lib/priceCadenceCopy.ts";

describe("price-cadence copy: one authority", () => {
  it("is built in EXACTLY one file", () => {
    // Equality, not a subset check against a list that could quietly grow.
    expect(cadenceConstructionSites()).toEqual([AUTHORITY]);
  });

  it("is non-vacuous — the scan can actually see a violation", () => {
    // Proves the regex + walker would catch a new copy. If this ever fails, the
    // guard above is passing because it finds NOTHING, not because the tree is
    // clean (the false-green shape a plant exists to detect).
    const planted = `const x = "Prices update every 1-2 hours";`;
    expect(CONSTRUCTION.test(stripComments(planted))).toBe(true);
    expect(CONSTRUCTION.test(stripComments(`const x = "Prices update every 1{"–"}2 hours";`))).toBe(true);
    // ...and does not fire on a comment merely naming the string.
    expect(CONSTRUCTION.test(stripComments(`// renders "Prices update every 1–2 hours"`))).toBe(false);
  });
});

describe("priceCadenceNote", () => {
  it("never promises an update on a settled market", () => {
    const settled = priceCadenceNote(true);
    // The property is the absence of a CADENCE — a promise that the number will
    // move again on some schedule. Not the absence of the word "update": the
    // settled copy says "no longer update", which is that promise's negation.
    // (The first draft of this assertion banned the word and went red against
    // correct copy — the guard was wrong, not the string.)
    expect(settled).not.toMatch(/every\s+\d/i);
    expect(settled).not.toMatch(/hours?\b/i);
    expect(settled).toMatch(/final/i);
    // The long form must not smuggle the promise back in.
    expect(priceCadenceNote(true, { long: true })).toBe(settled);
  });

  it("still tells a live market how often it moves", () => {
    expect(priceCadenceNote(false)).toMatch(/Prices update every 1–2 hours/);
    expect(priceCadenceNote(false, { long: true })).toMatch(/for this market$/);
  });

  it("uses ONE dash spelling across both lengths (the drift that was there)", () => {
    const dashes = [priceCadenceNote(false), priceCadenceNote(false, { long: true })]
      .map((s) => s.match(/1(.)2/)?.[1]);
    expect(new Set(dashes).size).toBe(1);
    expect(dashes[0]).toBe("–");
  });

  it("defaults to the short form", () => {
    expect(priceCadenceNote(false)).toBe(priceCadenceNote(false, {}));
    expect(priceCadenceNote(false)).not.toMatch(/for this market/);
  });
});

describe("the callers that know they are settled, pass it", () => {
  const read = (rel: string) => fs.readFileSync(path.join(FRONTEND, rel), "utf8");

  it("SettledPathChart is settled BY CONSTRUCTION", () => {
    // It only ever renders a concluded event's path to resolution, so this is a
    // constant prop rather than a runtime check that could be wrong.
    expect(read("components/event/SettledPathChart.tsx")).toMatch(/\n\s*settled\n/);
  });

  it("the futures page drives it from the market's own resolved state", () => {
    const src = read("app/futures/[id]/page.tsx");
    expect(src).toContain("settled={isResolved}");
    expect(src).toContain("priceCadenceNote(isResolved");
  });

  it("FuturesChart defaults to NOT settled, so every other caller is unaffected", () => {
    expect(read("components/FuturesChart.tsx")).toContain("settled = false,");
  });
});
