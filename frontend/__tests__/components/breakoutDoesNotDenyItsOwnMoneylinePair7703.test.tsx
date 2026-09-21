/**
 * #7703 — the shape breakout stops telling a reader its two moneyline curves
 * are different questions.
 *
 * WHAT A READER SAW. Inside By Source → Sportsbooks (Odds API):
 *
 *     ▶ Break out the shapes (4)
 *       Each shape is a different question, so these curves are not comparable
 *       to each other — only to the same shape elsewhere.
 *
 * Four curves; three shapes. `odds_api_bookmaker` (Per-sportsbook, 106,030) and
 * `odds_api` (Moneylines, 18,440) are BOTH the h2h moneyline — the producer's
 * docstring says so (`backfill_winners.py`, "the per-bookmaker moneyline
 * curve"), `calibrationProviders.ts`'s own module header says so ("the
 * forbidden blend: … are both moneyline"), and the draw-authority exclusion is
 * scoped to the two of them together for that reason. So 121,470 of the
 * family's 155,127 outcomes sat inside a sentence forbidding the one comparison
 * in that panel a reader would actually make: does a single sportsbook beat the
 * consensus line on the same question?
 *
 * Two register errors, one cause. The control counted source KEYS and called
 * them SHAPES, and Source Comparison's note 900px above it said "three shapes
 * (moneylines, spreads, totals)" — the same hand-written enumeration #7456
 * deleted from the hero, naming three of the family's four keys and omitting
 * the largest, surviving only because this copy is inside a fold.
 *
 * ═══ WHY THIS FILE HAS ITS OWN FIXTURE ═══
 *
 * `__tests__/lib/calibrationProviderPanels.test.ts` pins the 2026-08-13 corpus,
 * which has FIVE keys and no `odds_api_bookmaker`. On that payload the family
 * is three keys over three shapes, `repeated` is empty, and every assertion
 * below would pass while the defect rendered on production. The fixture IS the
 * specimen, so this file carries the seven keys production serves — asserted to
 * contain the gap before anything is judged against it.
 *
 * ═══ BOTH DIRECTIONS (gotcha #43) ═══
 *
 * The not-comparable warning is TRUE between shapes and must survive: a spread
 * curve and a totals curve really are different questions. So the negative
 * tests pin that a family whose keys are all distinct shapes still gets the
 * warning and names no pair — a "just delete the sentence" fix fails here.
 */
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import type { CalibrationData } from "@/lib/api";
import { groupSourcesByProvider, shapeName, shapeOf } from "@/lib/calibrationProviders";
import {
  buildProviderPanels,
  shapeBreakoutCaption,
  shapeCensus,
} from "@/lib/calibrationProviderPanels";

jest.mock("swr", () => ({
  __esModule: true,
  default: () => ({
    data: (global as unknown as { __calPayload: CalibrationData }).__calPayload,
  }),
}));

jest.mock("@/hooks", () => ({
  usePageTracking: () => {},
  useScrollDepth: () => {},
  useEngagementTime: () => {},
}));

jest.mock("@/components/CalibrationChart", () => ({ __esModule: true, default: () => null }));

jest.mock("next/link", () => {
  const ReactLib = require("react");
  return {
    __esModule: true,
    default: ({ href, children, ...props }: { href: string; children: React.ReactNode }) =>
      ReactLib.createElement("a", { href, ...props }, children),
  };
});

import CalibrationPage from "@/app/calibration/page";

/**
 * The seven keys `/api/calibration` served at 06:14Z 2026-09-21, in payload
 * order, with the outcome counts measured off that payload
 * (`population_version q271`). The two moneyline keys are the point of the
 * file, so they are real numbers rather than round ones: a reader's sense that
 * the pair matters comes from 106,030 + 18,440 being 78% of the family.
 */
const REAL_SOURCE_KEYS = [
  "kalshi",
  "polymarket",
  "odds_api_bookmaker",
  "odds_api",
  "odds_api_totals",
  "odds_api_spreads",
  "datagolf",
];
const REAL_N: Record<string, number> = {
  kalshi: 326_909,
  polymarket: 264_956,
  odds_api_bookmaker: 106_030,
  odds_api: 18_440,
  odds_api_totals: 15_537,
  odds_api_spreads: 15_120,
  datagolf: 36,
};

const SPORTSBOOK_KEYS = REAL_SOURCE_KEYS.filter(k => k.startsWith("odds_api"));

function bucket(source: string, idx: number) {
  return {
    bucket_idx: idx,
    source,
    category: "baseball",
    price_moved: true,
    n: 400,
    winners: 200,
    avg_prob: 0.05 + idx * 0.1,
    sum_prob: 400 * (0.05 + idx * 0.1),
    sum_sq_err: 40,
    ci_lower: 0.01,
    ci_upper: 0.99,
  };
}

function makePayload(): CalibrationData {
  const buckets = REAL_SOURCE_KEYS.flatMap(s => [0, 1, 2, 3, 4].map(i => bucket(s, i)));
  return {
    buckets,
    total_markets: 12_000,
    total_outcomes: 747_028,
    total_winners: 441_443,
    mce_ci_lower: 0.01,
    mce_ci_upper: 0.05,
    mce_closing_line: 0.03,
    mce_opening_price: 0.04,
    generated_at: "2026-09-15T11:16:10Z",
    date_range: { start: "2021-09-01", end: "2026-09-15" },
    by_source: REAL_SOURCE_KEYS.map(source => ({ source, ece: 0.02, mce: 0.05, n: REAL_N[source] })),
    by_category: [
      { category: "baseball", ece: 0.02, n: 4_000 },
      { category: "football", ece: 0.03, n: 3_000 },
    ],
  } as unknown as CalibrationData;
}

function render(): string {
  (global as unknown as { __calPayload: CalibrationData }).__calPayload = makePayload();
  return renderToStaticMarkup(<CalibrationPage />);
}

/** Visible text only — the source keys live in attributes, and those are not copy. */
function visibleText(html: string): string {
  return html
    .replace(/<!--[\s\S]*?-->/g, " ")
    .replace(/<[^>]*>/g, " ")
    .replace(/\s+/g, " ")
    .trim();
}

/* ═══════════ the fixture proves it holds the defect before judging it ═══════════ */

describe("the specimen is the production family, not a convenient one", () => {
  test("the sportsbook family really does draw two curves of one shape", () => {
    expect(SPORTSBOOK_KEYS).toHaveLength(4);
    const census = shapeCensus(SPORTSBOOK_KEYS);
    expect(census.curves).toBe(4);
    expect(census.shapes).toBe(3);
    expect(census.curves).toBeGreaterThan(census.shapes);
  });

  test("and the pair is the large half of the family, which is why it matters", () => {
    const moneyline = SPORTSBOOK_KEYS.filter(k => shapeOf(k) === "moneyline");
    expect(moneyline).toEqual(["odds_api_bookmaker", "odds_api"]);
    const family = SPORTSBOOK_KEYS.reduce((s, k) => s + REAL_N[k], 0);
    const pair = moneyline.reduce((s, k) => s + REAL_N[k], 0);
    expect(family).toBe(155_127);
    expect(pair / family).toBeGreaterThan(0.75);
  });
});

/* ═══════════════════════ shapeOf — the pairing itself ═══════════════════════ */

describe("shapeOf pairs only what has been declared, and is total", () => {
  test("the two moneyline keys share a shape; the other two do not", () => {
    expect(shapeOf("odds_api")).toBe(shapeOf("odds_api_bookmaker"));
    expect(shapeOf("odds_api_spreads")).not.toBe(shapeOf("odds_api"));
    expect(shapeOf("odds_api_totals")).not.toBe(shapeOf("odds_api_spreads"));
  });

  test("🔴 an unknown key is its OWN shape — a new key can never join a pair", () => {
    // The fail-safe direction. `shapeOf` falling back to a family or a prefix
    // would let the next `odds_api_*` key silently enter the moneyline pair and
    // make the caption assert a pairing nobody measured. Total, like
    // `providerOf`, is what forbids that.
    expect(shapeOf("odds_api_first_half")).toBe("odds_api_first_half");
    expect(shapeOf("odds_api_first_half")).not.toBe("moneyline");
    expect(shapeCensus(["odds_api", "odds_api_first_half"]).shapes).toBe(2);
  });

  test("a shape always has a name a reader can read", () => {
    // CAL-P1024's floor, stated on the tell rather than on inequality with the
    // key: `shapeName("kalshi")` IS "kalshi" and that is correct — the brand
    // lowercased. What may never reach a sentence is an un-prettified payload
    // identifier, and the underscore is what makes one recognisable.
    for (const key of [...REAL_SOURCE_KEYS, "odds_api_first_half"]) {
      const name = shapeName(shapeOf(key));
      expect(name).toBeTruthy();
      expect(name).not.toContain("_");
    }
    expect(shapeName(shapeOf("odds_api_bookmaker"))).toBe("moneyline");
  });
});

/* ═══════════════ the caption — the sentence that was false ═══════════════ */

describe("shapeBreakoutCaption states the pair instead of denying it", () => {
  const caption = () => shapeBreakoutCaption(SPORTSBOOK_KEYS);

  test("🔴 it names both curves of the repeated shape, and the shape", () => {
    const text = caption();
    expect(text).toContain("Per-sportsbook (Odds API)");
    expect(text).toContain("Moneylines (Odds API)");
    expect(text).toContain("moneyline");
    expect(text).toContain("measured two ways");
  });

  test("🔴 it no longer asserts that EVERY pair here is incomparable", () => {
    // The exact string production served, and the claim that was false of 78%
    // of this family. Byte-level, because the defect was the sentence.
    expect(caption()).not.toContain("Each shape is a different question");
    // The blanket subject is the defect. "Curves of different shapes" is the
    // qualified form and must be what stands in its place.
    expect(caption()).toContain("Curves of different shapes answer different questions");
  });

  test("the between-shape warning SURVIVES — deleting it is not the fix", () => {
    // Both directions. A spread curve and a totals curve are different
    // questions; the reader still has to be told not to rank them against each
    // other. A "just remove the sentence" repair fails right here.
    expect(caption()).toContain("not comparable to each other");
    expect(caption()).toContain("The panel above is all of them pooled");
  });

  test("a family with no repeated shape gets the plain sentence and names no pair", () => {
    // The 2026-08-13 corpus, which is what every other suite pins. On it the
    // new clause must not appear at all — a caption that announced a pairing
    // here would be inventing one.
    const distinct = shapeBreakoutCaption(["odds_api", "odds_api_totals", "odds_api_spreads"]);
    expect(shapeCensus(["odds_api", "odds_api_totals", "odds_api_spreads"]).repeated).toHaveLength(0);
    expect(distinct).toContain("Each curve here is a different question");
    expect(distinct).not.toContain("measured two ways");
    expect(distinct).toContain("The panel above is all of them pooled");
  });
});

/* ══════════════════ the rendered page, which is what ships ══════════════════ */

describe("the page renders the honest control and the honest caption", () => {
  test("positive control: the real page is built, not a loading shell", () => {
    const text = visibleText(render());
    expect(text).toContain("Source Comparison");
    expect(text).toContain("By Source");
  });

  test("🔴 the control is named for what it lists, and its count is the curves", () => {
    const text = visibleText(render());
    const m = /Break out the curves \((\d+)\)/.exec(text);
    expect(m).not.toBeNull();
    expect(Number(m![1])).toBe(SPORTSBOOK_KEYS.length);
    // The old name is gone from the reader's page entirely — it was the half of
    // the defect that contradicted the "three shapes" sentence above it.
    expect(text).not.toContain("Break out the shapes");
  });

  test("🔴 the rendered caption names the pair — asserted on the RENDER, not the helper", () => {
    // #4214's note: only the composed output shows this class, because each
    // half is individually valid. A unit test on `shapeBreakoutCaption` cannot
    // tell whether the page calls it.
    const text = visibleText(render());
    expect(text).toContain("Per-sportsbook (Odds API) and Moneylines (Odds API) are the same question");
    expect(text).not.toContain("Each shape is a different question");
  });

  test("🔴 the hand-written 'three shapes (moneylines, spreads, totals)' is gone", () => {
    // #7456 deleted this enumeration from the hero and recorded the rule ("one
    // place owns the shapes"). This is the copy it could not reach. The
    // assertion is on the ENUMERATION, not on the digit: re-deriving the same
    // list by hand in a different order would still be the defect.
    const text = visibleText(render());
    expect(text).not.toContain("three shapes");
    expect(text).not.toContain("(moneylines, spreads, totals)");
  });

  test("🔴 the pointer sentence and the control it names still agree — #7308 holds", () => {
    // The contract that file established, restated through the new wording so a
    // rename cannot quietly break the agreement it guards.
    const text = visibleText(render());
    const promised = /see all (\d+) curves separately/.exec(text);
    const control = /Break out the curves \((\d+)\)/.exec(text);
    expect(promised).not.toBeNull();
    expect(control).not.toBeNull();
    expect(promised![1]).toBe(control![1]);
  });

  test("the caption count and the panels drawn under it are the same number", () => {
    // The gap that made "(4)" survive: nobody asserted the control's number
    // against the panels it opens onto. Read both out of one render.
    const html = render();
    const panels = html.match(/data-testid="calibration-source-panel"/g) ?? [];
    const control = /Break out the curves \((\d+)\)/.exec(visibleText(html));
    expect(Number(control![1])).toBe(panels.length);
  });
});

/* ═════════ the derivation is one object, so the counts cannot drift ═════════ */

describe("one census feeds the panel, so the page cannot disagree with itself", () => {
  test("the breakout panel's own sources are what the census is taken over", () => {
    const groups = groupSourcesByProvider(REAL_SOURCE_KEYS);
    const panels = buildProviderPanels(
      groups.map(g => ({
        provider: g.provider,
        label: g.label,
        sources: g.sources,
        buckets: g.sources.map(s => ({ n: REAL_N[s], error: 2, winners: Math.round(REAL_N[s] / 2) })),
        publishedEce: g.sources.length === 1 ? 3.1 : null,
        pooledEce: g.sources.length > 1 ? 4.2 : null,
      }))
    );
    const breakout = panels.filter(p => p.hasShapeBreakdown);
    expect(breakout).toHaveLength(1);
    expect(shapeCensus(breakout[0].sources)).toEqual(shapeCensus(SPORTSBOOK_KEYS));
  });
});
