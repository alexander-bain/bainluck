/**
 * #7325 — the "niche & long-shot" card stops parking categories the page publishes.
 *
 * Seen on production https://bainluck.com/calibration at 390px, 2026-09-19. The
 * card said "109 categories don't have enough resolved outcomes yet for a curve
 * we'd stand behind" and showed eight chips under CLOSEST TO THE BAR:
 *
 *     CFL 847 · NCAA Lacrosse 829 · Chess 809 · SHL 730
 *     NFL Preseason 707 · NCAAF FCS 682 · USA MLS 613 · UFL 593
 *
 * SIX OF THE EIGHT WERE ALREADY PUBLISHED on the same page. CFL, NFL Preseason,
 * NCAAF FCS and UFL are inside Football (34,205); SHL is inside Hockey (27,316);
 * USA MLS is inside Soccer (132,357) — each with its own row in the Category
 * Breakdown table. In one screenshot that table published Geopolitics at 732
 * while the card below parked CFL at 847: a bigger number described as too small
 * to grade than one that got a curve. `americanfootball_nfl` was in the list at
 * 393 — the NFL, listed as a long-shot market we cannot stand behind.
 *
 * ═══ THE CAUSE IS A MISSING JOIN, NOT A BAD COUNT ═══
 *
 * The two lists are kept in two vocabularies and nothing reconciled them:
 *
 *   published  — computed page-side over `normalizeCat(b.category)`, so
 *                `americanfootball_{nfl,cfl,ufl}` all fold into `football`
 *   parked     — `small_sample_categories`, emitted by the backend over RAW
 *                payload keys, all `disposition: parked_below_publish_bar`
 *
 * So a sub-league is below the bar as a raw key while its normalized parent is
 * far above it. Measured on the live payload: 67 of the 109 entries — 19,655 of
 * the 23,873 outcomes the card called "still accumulating", 82% — were already
 * graded and on the page.
 *
 * It also made the fold's promise unkeepable. "The moment one crosses the bar it
 * appears above automatically" cannot come true for `americanfootball_cfl`: it
 * can never be its own row, because it is already inside Football.
 *
 * ═══ WHY THE FIXTURE IS SHAPED LIKE THIS ═══
 *
 *   bucket key                n      normalizes to   published?
 *   americanfootball_nfl   30,000    football        yes (30,847 total)
 *   americanfootball_cfl      847    football        yes — INSIDE the row above
 *   soccer_epl             20,000    soccer          yes (20,613 total)
 *   soccer_usa_mls            613    soccer          yes — INSIDE the row above
 *   chess                     800    chess           no  — below the 1,000 bar
 *   lacrosse_ncaa             900    lacrosse_ncaa   no  — below the 1,000 bar
 *
 * `small_sample_categories` carries all four sub-bar RAW keys, exactly as the
 * backend emits them: cfl 847, usa_mls 613, chess 800, lacrosse_ncaa 900.
 *
 * The CFL and MLS rows are the specimen: both are genuinely below the bar on
 * their own raw key, and both are genuinely inside a published parent. That is
 * the production case, reproduced — not a category invented to fail.
 *
 * A fixture without them would pass on the broken code, and a fixture whose
 * parked entries were ALL published would let a fix that deletes the card
 * outright pass too; `chess` and `lacrosse_ncaa` are here so the card must
 * survive with the right two chips rather than vanish.
 *
 * ═══ WHAT THESE TESTS PIN ═══
 *
 * Both lists are read FROM THE RENDERED DOM, never recomputed here — a guard
 * that rebuilds the page's arithmetic checks this file's opinion, not the page.
 */

import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import type { CalibrationData } from "@/lib/api";
import { normalizeCat } from "@/lib/calibrationCategories";

// The page is a `"use client"` component behind SWR. Mock the hook, not the
// fetcher: `renderToStaticMarkup` never runs an effect, so a real SWR hands the
// page `undefined` and the suite photographs the loading state instead. (#6265)
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

jest.mock("@/components/CalibrationChart", () => ({
  __esModule: true,
  default: () => null,
}));

jest.mock("next/link", () => {
  const ReactLib = require("react");
  return {
    __esModule: true,
    default: ({ href, children, ...props }: { href: string; children: React.ReactNode }) =>
      ReactLib.createElement("a", { href, ...props }, children),
  };
});

import CalibrationPage from "@/app/calibration/page";

/** Raw payload key -> outcomes. Sub-league keys fold into a published parent. */
const BUCKET_KEYS: { category: string; n: number }[] = [
  { category: "americanfootball_nfl", n: 30_000 },
  { category: "americanfootball_cfl", n: 847 },
  { category: "soccer_epl", n: 20_000 },
  { category: "soccer_usa_mls", n: 613 },
  { category: "chess", n: 800 },
  { category: "lacrosse_ncaa", n: 900 },
];

/** Exactly what the backend emits: the RAW keys that are under the bar. */
const PARKED_RAW = [
  { category: "lacrosse_ncaa", outcomes: 900, ece: 5.1, disposition: "parked_below_publish_bar", publish_bar: 1000 },
  { category: "americanfootball_cfl", outcomes: 847, ece: 6.62, disposition: "parked_below_publish_bar", publish_bar: 1000 },
  { category: "chess", outcomes: 800, ece: 4.4, disposition: "parked_below_publish_bar", publish_bar: 1000 },
  { category: "soccer_usa_mls", outcomes: 613, ece: 7.0, disposition: "parked_below_publish_bar", publish_bar: 1000 },
];

/** The two whose normalized parent has a published row: the defect's specimen. */
const ALREADY_PUBLISHED_RAW = ["americanfootball_cfl", "soccer_usa_mls"];
/** The two that are genuinely absent from the page. */
const GENUINELY_PARKED_RAW = ["lacrosse_ncaa", "chess"];

/** The wire's bucket shape — `bucket_idx`/`avg_prob`/`winners`, not a guess. */
function bucket(category: string, idx: number, n: number) {
  return {
    bucket_idx: idx,
    source: "kalshi",
    category,
    price_moved: true,
    n,
    winners: Math.round(n * (0.05 + idx * 0.1)),
    avg_prob: 0.05 + idx * 0.1,
    sum_prob: n * (0.05 + idx * 0.1),
    sum_sq_err: n * 0.1,
    ci_lower: 0.01,
    ci_upper: 0.99,
  };
}

function makePayload(): CalibrationData {
  const buckets = BUCKET_KEYS.flatMap(k =>
    [0, 1, 2, 3, 4].map(i => bucket(k.category, i, k.n / 5)),
  );
  return {
    buckets,
    min_category_outcomes: 1000,
    small_sample_categories: PARKED_RAW,
    total_markets: 5_000,
    total_outcomes: BUCKET_KEYS.reduce((t, k) => t + k.n, 0),
    total_winners: 20_000,
    mce_ci_lower: 0.01,
    mce_ci_upper: 0.05,
    mce_closing_line: 0.03,
    mce_opening_price: 0.04,
    generated_at: "2026-09-19T10:00:00Z",
    date_range: { start: "2026-01-01", end: "2026-09-19" },
    by_source: [{ source: "kalshi", ece: 0.02, mce: 0.05, n: 2_000 }],
    by_category: [],
  } as unknown as CalibrationData;
}

function render(): string {
  (global as unknown as { __calPayload: CalibrationData }).__calPayload = makePayload();
  return renderToStaticMarkup(<CalibrationPage />);
}

/** Every `data-category` carried by a given testid, in render order. */
function categoriesFor(html: string, testid: string): string[] {
  const re = new RegExp(`data-testid="${testid}"[^>]*?data-category="([^"]*)"`, "g");
  const out: string[] = [];
  let m: RegExpExecArray | null;
  while ((m = re.exec(html)) !== null) out.push(m[1]);
  return out;
}

/** The published rows of the Category Breakdown table — what the reader sees. */
const publishedRows = (html: string) => categoriesFor(html, "calibration-category-row");
/** The chips under CLOSEST TO THE BAR. */
const parkedChips = (html: string) => categoriesFor(html, "calibration-parked-category");

function parkedCount(html: string): number {
  const m = /data-testid="calibration-niche-section"[^>]*?data-parked-count="(\d+)"/.exec(html);
  expect(m).not.toBeNull();
  return Number(m![1]);
}

describe("#7325 the niche card and the breakdown table are one vocabulary", () => {
  test("the fixture reproduces the defect's shape, or nothing below proves anything", () => {
    const html = render();
    // The sub-leagues really are published, via their normalized parent.
    const published = new Set(publishedRows(html));
    expect(published).toEqual(new Set(["football", "soccer"]));
    for (const raw of ALREADY_PUBLISHED_RAW) {
      expect(published.has(normalizeCat(raw))).toBe(true);
    }
    // ...and the other two really are absent from it.
    for (const raw of GENUINELY_PARKED_RAW) {
      expect(published.has(normalizeCat(raw))).toBe(false);
    }
  });

  test("no chip names a category the page publishes", () => {
    const html = render();
    const published = new Set(publishedRows(html));
    const offenders = parkedChips(html).filter(c => published.has(normalizeCat(c)));
    expect(offenders).toEqual([]);
  });

  test("CFL and USA MLS are gone; lacrosse and chess stay", () => {
    const html = render();
    // Named explicitly as well as by rule: the rule above would also be
    // satisfied by a fix that renders no chips at all.
    expect(parkedChips(html)).toEqual(GENUINELY_PARKED_RAW);
  });

  test("the count describes what is held back, not what is already shown", () => {
    const html = render();
    expect(parkedCount(html)).toBe(2);
    // The sentence the reader reads, and the outcome total in the fold. 900 +
    // 800 — NOT 3,160, which would be counting CFL's 847 and MLS's 613 twice,
    // once here and once inside Football and Soccer.
    expect(html).toContain("<strong class=\"text-text-primary\">2</strong>");
    expect(html).toContain("1,700 outcomes and counting");
    expect(html).not.toContain("3,160 outcomes and counting");
  });

  test("published and parked are an exact disjoint partition of the page's categories", () => {
    const html = render();
    const published = publishedRows(html);
    const parked = parkedChips(html).map(normalizeCat);
    // Every category the payload carries, in the page's own vocabulary.
    const inPayload = new Set(BUCKET_KEYS.map(k => normalizeCat(k.category)));

    expect(new Set([...published, ...parked])).toEqual(inPayload);
    expect(published.filter(c => parked.includes(c))).toEqual([]);
    expect(published.length + parked.length).toBe(inPayload.size);
  });

  test("a payload holding nothing back renders no card at all", () => {
    // Every parked entry is already published, so there is no honest sentence
    // left to write — "0 categories don't have enough outcomes" is furniture.
    const payload = makePayload() as unknown as {
      small_sample_categories: typeof PARKED_RAW;
    };
    payload.small_sample_categories = PARKED_RAW.filter(p =>
      ALREADY_PUBLISHED_RAW.includes(p.category),
    );
    (global as unknown as { __calPayload: unknown }).__calPayload = payload;
    const html = renderToStaticMarkup(<CalibrationPage />);
    expect(html).not.toContain('data-testid="calibration-niche-section"');
    expect(html).not.toContain("What About Niche");
  });
});
