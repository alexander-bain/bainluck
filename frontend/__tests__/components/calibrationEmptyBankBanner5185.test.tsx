/**
 * #5185 — the accuracy page tells an emptied input bank apart from one that
 * lost its date, and publishes which one it is showing.
 *
 * `/api/calibration` has said `staged.reason: "served_bank_empty"` since #5043
 * (PR #5124). The page threw that away twice: every unreadable reason rendered
 * one sentence ("We couldn't read when the market data behind it was last
 * staged"), and `staged.reason` was on no attribute, so a probe could not tell
 * which state the page was in either.
 *
 * The two envelopes are production's MAIN-tier answer (no `cache`) and differ
 * in `staged.reason` alone, so the reason is the only candidate cause of any
 * difference below. Harness borrowed verbatim from
 * `calibrationMethodologyRefreshPromiseIsGated7612.test.tsx`.
 */

import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import type { CalibrationData } from "@/lib/api";

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

/** The wire's bucket shape — `bucket_idx`/`avg_prob`/`winners`, not a guess. */
function bucket(category: string, idx: number, priceMoved: boolean, n: number) {
  return {
    bucket_idx: idx,
    source: "kalshi",
    category,
    price_moved: priceMoved,
    n,
    winners: Math.round(n * (0.05 + idx * 0.1)),
    avg_prob: 0.05 + idx * 0.1,
    sum_prob: n * (0.05 + idx * 0.1),
    sum_sq_err: n * 0.1,
    ci_lower: 0.01,
    ci_upper: 0.99,
  };
}

const CATEGORIES = [
  { category: "baseball", traded: 80_000, untraded: 60_000 },
  { category: "basketball", traded: 58_000, untraded: 11_000 },
];

function makePayload(envelope: Record<string, unknown>): CalibrationData {
  const buckets = CATEGORIES.flatMap(c =>
    [0, 1, 2, 3, 4].flatMap(i => [
      bucket(c.category, i, true, c.traded / 5),
      bucket(c.category, i, false, c.untraded / 5),
    ]),
  );
  return {
    buckets,
    total_markets: 12_000,
    total_outcomes: CATEGORIES.reduce((t, c) => t + c.traded + c.untraded, 0),
    total_winners: 100_000,
    mce_ci_lower: 0.01,
    mce_ci_upper: 0.05,
    mce_closing_line: 0.03,
    mce_opening_price: 0.04,
    generated_at: "2026-09-15T11:16:10.215051+00:00",
    date_range: { start: "2021-09-01", end: "2026-09-15" },
    min_category_outcomes: 1000,
    by_source: [{ source: "kalshi", ece: 0.02, mce: 0.05, n: 2_000 }],
    by_category: CATEGORIES.map(c => ({
      category: c.category,
      ece: 0.02,
      n: c.traded + c.untraded,
    })),
    small_sample_categories: [],
    ...envelope,
  } as unknown as CalibrationData;
}

function render(envelope: Record<string, unknown>): string {
  (global as unknown as { __calPayload: CalibrationData }).__calPayload = makePayload(envelope);
  return renderToStaticMarkup(<CalibrationPage />);
}


const MAIN_TIER = {
  availability: "stale",
  producer: {
    task: "precompute_calibration_main",
    interval_s: 3600,
    stall_after_s: 14400,
    age_s: 497_636,
    beats_missed: 138,
    stalled: true,
  },
};
const EMPTY_BANK = { ...MAIN_TIER, staged: { measured: false, reason: "served_bank_empty" } };
const UNDATED_BANK = { ...MAIN_TIER, staged: { measured: false, reason: "served_at_absent" } };

/** The banner element, from its opening tag to its closing `</div>`. */
function banner(html: string): string {
  const hook = html.indexOf('data-testid="calibration-stale-banner"');
  expect(hook).toBeGreaterThan(-1);
  const open = html.lastIndexOf("<div", hook);
  const end = html.indexOf("</div>", hook);
  return html.slice(open, end);
}

function attr(el: string, name: string): string | null {
  const m = el.match(new RegExp(`${name}="([^"]*)"`));
  return m ? m[1] : null;
}

describe("#5185 the page's empty-bank state", () => {
  test("positive control: both envelopes render the same undisclosed banner kind", () => {
    for (const env of [EMPTY_BANK, UNDATED_BANK]) {
      const el = banner(render(env));
      expect(attr(el, "data-staleness-kind")).toBe("undisclosed");
      expect(el).toContain("138 hourly rebuilds have come and gone without a new snapshot.");
    }
  });

  test("staged.reason is probeable on the banner", () => {
    expect(attr(banner(render(EMPTY_BANK)), "data-staged-reason")).toBe("served_bank_empty");
    expect(attr(banner(render(UNDATED_BANK)), "data-staged-reason")).toBe("served_at_absent");
  });

  test("an emptied bank reads as emptied, not as a failed read", () => {
    const el = banner(render(EMPTY_BANK));
    expect(el).toContain("The market data behind it is being gathered again from scratch, so it has no date to show.");
    expect(el).not.toMatch(/couldn.t read when the market data/);
  });

  test("control: a bank that lost its date keeps the failed-read sentence", () => {
    const el = banner(render(UNDATED_BANK));
    expect(el).toContain("couldn\u2019t read when the market data behind it was last staged.");
    expect(el).not.toContain("gathered again from scratch");
  });

  test("no staging date is invented for the empty bank (#2007)", () => {
    expect(attr(banner(render(EMPTY_BANK)), "data-staged-at")).toBe("");
  });

  test("the last-good banner publishes the staged reason too", () => {
    const el = banner(
      render({
        ...EMPTY_BANK,
        cache: { status: "stale", reason: "main_key_absent_durable", age_s: 497_636, generated_at: "2026-09-15T11:16:10.215051+00:00" },
      }),
    );
    expect(attr(el, "data-staleness-kind")).toBe("last-good");
    expect(attr(el, "data-cache-reason")).toBe("main_key_absent_durable");
    expect(attr(el, "data-staged-reason")).toBe("served_bank_empty");
  });
});
