/**
 * #8917 — a category listed on its all-outcome total but thin in the view on
 * screen keeps its numbers and loses the quality colour.
 *
 * Shopped on production, phone width, default (traded) view, 2026-09-26 20:25Z:
 * the Category Breakdown table's last row was "Table Tennis · 26 · 21.6pp" in
 * the warning colour. It is listed because the bar counts all 4,772 of its
 * outcomes (#7195 / #7302 — the bar stays all-cohort); only 26 are traded. The
 * table's own fold calls anything under the bar "statistical noise, not a
 * calibration signal".
 *
 * The fixture reproduces that straddle and pairs it with a CONTROL: a category
 * well above the bar in this view whose error is just as bad, so a fix that
 * simply muted every warning colour would fail the control.
 */

import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import type { CalibrationData } from "@/lib/api";

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

const BAR = 1_000;

/** `bad`: every traded outcome loses, so the row's error lands far above 5pp. */
const SPLIT = [
  { category: "baseball", traded: 50_000, untraded: 20_000, bad: false },
  { category: "basketball", traded: 40_000, untraded: 10_000, bad: false },
  // CONTROL — above the bar in this view AND badly calibrated: keeps its colour.
  { category: "cricket", traded: 1_450, untraded: 4_650, bad: true },
  // SPECIMEN — production's straddle: 26 traded of 4,772.
  { category: "table_tennis", traded: 26, untraded: 4_746, bad: true },
];

const allTotal = (s: (typeof SPLIT)[number]) => s.traded + s.untraded;

function bucket(category: string, idx: number, priceMoved: boolean, n: number, bad: boolean) {
  const p = 0.05 + idx * 0.1;
  return {
    bucket_idx: idx,
    source: "kalshi",
    category,
    price_moved: priceMoved,
    n,
    winners: bad && priceMoved ? 0 : Math.round(n * p),
    avg_prob: p,
    sum_prob: n * p,
    sum_sq_err: n * 0.1,
    ci_lower: 0.01,
    ci_upper: 0.99,
  };
}

function makePayload(): CalibrationData {
  const buckets = SPLIT.flatMap(s =>
    // Two buckets at 55% and 65%, so a losing traded cohort errs ~60pp.
    [5, 6].flatMap(i => [
      bucket(s.category, i, true, s.traded / 2, s.bad),
      bucket(s.category, i, false, s.untraded / 2, s.bad),
    ]),
  );
  return {
    buckets,
    min_category_outcomes: BAR,
    total_markets: 5_000,
    total_outcomes: SPLIT.reduce((t, s) => t + allTotal(s), 0),
    total_winners: 60_000,
    mce_ci_lower: 0.01,
    mce_ci_upper: 0.05,
    mce_closing_line: 0.03,
    mce_opening_price: 0.04,
    generated_at: "2026-09-26T20:20:00Z",
    date_range: { start: "2026-01-01", end: "2026-09-26" },
    by_source: [{ source: "kalshi", ece: 0.02, mce: 0.05, n: 2_000 }],
    by_category: SPLIT.map(s => ({ category: s.category, ece: 0.02, n: allTotal(s) })),
    small_sample_categories: [],
  } as unknown as CalibrationData;
}

function render(): string {
  (global as unknown as { __calPayload: CalibrationData }).__calPayload = makePayload();
  return renderToStaticMarkup(<CalibrationPage />);
}

/** The whole `<tr>` the Category Breakdown table rendered for one category. */
function row(html: string, category: string): string {
  const re = new RegExp(
    `<tr[^>]*data-testid="calibration-category-row"[^>]*data-category="${category}"[^>]*>([\\s\\S]*?)</tr>`,
  );
  const m = re.exec(html);
  expect(m).not.toBeNull();
  return m![0];
}

/** The ECE cell: the third `<td>` of the row. */
function eceCell(rowHtml: string): string {
  const cells = rowHtml.match(/<td[^>]*>[\s\S]*?<\/td>/g) ?? [];
  expect(cells.length).toBeGreaterThanOrEqual(3);
  return cells[2];
}

describe("the fixture has the straddle and a control", () => {
  test("specimen clears the bar on its total and not in the traded view; control clears both", () => {
    const tt = SPLIT.find(s => s.category === "table_tennis")!;
    const cr = SPLIT.find(s => s.category === "cricket")!;
    expect(allTotal(tt)).toBeGreaterThanOrEqual(BAR);
    expect(tt.traded).toBeLessThan(BAR);
    expect(cr.traded).toBeGreaterThanOrEqual(BAR);
  });

  test("both rows render, with the bad error figure", () => {
    const html = render();
    for (const c of ["table_tennis", "cricket"]) {
      const m = />(\d+\.\d)pp</.exec(eceCell(row(html, c)));
      expect(m).not.toBeNull();
      expect(parseFloat(m![1])).toBeGreaterThan(5);
    }
  });
});

describe("#8917 — a thin row keeps its numbers and loses the quality colour", () => {
  test("🔴 the specimen is marked thin and its error is not painted as a grade", () => {
    const r = row(render(), "table_tennis");
    expect(r).toContain('data-thin="true"');
    expect(r).toContain('data-testid="calibration-thin-row-badge"');
    expect(eceCell(r)).not.toMatch(/text-(orange|blue|green)-600/);
    expect(eceCell(r)).toContain("text-text-muted");
  });

  test("the specimen is still listed, with its count — nothing is hidden", () => {
    const r = row(render(), "table_tennis");
    expect(r).toContain('data-n="26"');
    expect(r).toMatch(/>26</);
  });

  test("control: an above-bar row with the same bad error keeps its warning colour", () => {
    const r = row(render(), "cricket");
    expect(r).toContain('data-thin="false"');
    expect(r).not.toContain("calibration-thin-row-badge");
    expect(eceCell(r)).toContain("text-orange-600");
  });

  test("the marked rows are exactly the rows the fold's 'fewer than' clause is about", () => {
    const html = render();
    const thinCount = (html.match(/data-thin="true"/g) ?? []).length;
    const m = /data-testid="calibration-category-bar-note"[^>]*data-rows-below-bar="(\d+)"/.exec(html);
    expect(m).not.toBeNull();
    expect(thinCount).toBe(Number(m![1]));
    expect(thinCount).toBe(1);
  });

  test("the mark's tooltip names both counts' populations", () => {
    const r = row(render(), "table_tennis");
    const m = /data-testid="calibration-thin-row-badge"[^>]*title="([^"]+)"/.exec(r)
      ?? /title="([^"]+)"[^>]*data-testid="calibration-thin-row-badge"/.exec(r);
    expect(m).not.toBeNull();
    expect(m![1]).toContain("Only 26 outcomes in this view");
    expect(m![1]).toContain("1,000");
  });
});
