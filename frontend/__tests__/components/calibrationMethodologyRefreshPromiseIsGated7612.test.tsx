/**
 * #7612 — the methodology card stops promising an hourly refresh the payload
 * refutes.
 *
 * Shopped on production, 1280px, default view, 2026-09-20 21:45Z. Two sentences
 * on ONE page load, neither behind a tap:
 *
 *     Showing the last complete snapshot. These numbers were built Sep 15,
 *     4:16 AM (5 days ago) and are not being refreshed right now. 130 hourly
 *     rebuilds have come and gone without a new snapshot.
 *       …
 *     What's included? 747,028 resolved outcomes … Data refreshes hourly.
 *
 * The payload underneath carried `producer: {stalled: true, beats_missed: 130}`.
 *
 * ═══ WHY THE BANNER'S FIX DID NOT REACH THIS ═══
 *
 * #2649 removed exactly this promise from the BANNER, and #4113 tightened it;
 * `stalenessScheduleClause` is the result and its docstring carries the rule
 * ("THE BANNER MAY DESCRIBE, IT MAY NOT PREDICT"). The methodology card's copy
 * of the same sentence was a string literal in the JSX, so it read nothing and
 * no guard compared it to anything: `calibrationBannerCopy.test.tsx` scopes its
 * forward-looking ban to the banner element, and `calibrationStaleness.test.ts`
 * covers a function this literal never called.
 *
 * So the assertion here is deliberately the RELATION, not the string: whenever
 * the page renders a staleness banner, the methodology card does not print the
 * promise. A future sentence that says the same thing in different words fails
 * this the same way, which is the failure mode #7341 and #7353 were both.
 *
 * ═══ WHY THE FIXTURE IS BUILT THE WAY IT IS ═══
 *
 * Both renders use the SAME payload object except its staleness envelope —
 * `availability`, `producer`, `cache`. Nothing else moves. Without that, "the
 * sentence disappeared" could be any of a dozen differences between two
 * hand-built payloads; with it, the envelope is the only candidate cause.
 *
 * The stale envelope is production's, verbatim, including `age_s: 469772` and
 * the `served_bank_empty` staged reason.
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

/** The envelope production served at 21:45Z, 130 beats after the last publish. */
const STALE_ENVELOPE = {
  availability: "stale",
  staged: { measured: false, reason: "served_bank_empty" },
  producer: {
    task: "precompute_calibration_main",
    interval_s: 3600,
    stall_after_s: 14400,
    age_s: 469_772,
    beats_missed: 130,
    stalled: true,
  },
  cache: {
    status: "stale",
    reason: "main_key_absent_durable",
    age_s: 469_772,
    generated_at: "2026-09-15T11:16:10.215051+00:00",
  },
};

/** The curve is current and the server says so. No banner renders. */
const FRESH_ENVELOPE = {
  availability: "fresh",
  staged: { measured: true, frozen_over_drift: false, units_drifted: 0, units_banked: 128 },
  producer: { task: "precompute_calibration_main", interval_s: 3600, beats_missed: 0, stalled: false },
  cache: null,
};

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

/** The "What's included?" bullet, from its own attribute to its closing tag. */
function whatsIncluded(html: string): string {
  const start = html.indexOf("data-population-sources=");
  expect(start).toBeGreaterThan(-1);
  const open = html.lastIndexOf("<li", start);
  const end = html.indexOf("</li>", start);
  expect(open).toBeGreaterThan(-1);
  expect(end).toBeGreaterThan(open);
  return html.slice(open, end);
}

/** Does the page render a staleness banner at all? */
function hasBanner(html: string): boolean {
  return html.includes("data-staleness-kind=");
}

/* ═══════ the harness proves itself before it proves an absence ═══════ */

describe("the harness renders the real calibration page", () => {
  test("positive control: both renders build the methodology card", () => {
    // Every assertion below the fold is an ABSENCE, and a loading shell or a
    // crashed render satisfies every absence ever written.
    for (const envelope of [STALE_ENVELOPE, FRESH_ENVELOPE]) {
      const bulletText = whatsIncluded(render(envelope));
      expect(bulletText).toContain("resolved outcomes");
      expect(bulletText).toContain("never-traded outcomes are excluded");
    }
  });

  test("positive control: the envelope is the only thing that moves", () => {
    // If the fixture differed elsewhere, the sentence's disappearance would not
    // be attributable to the staleness state.
    const stale = makePayload(STALE_ENVELOPE) as unknown as Record<string, unknown>;
    const fresh = makePayload(FRESH_ENVELOPE) as unknown as Record<string, unknown>;
    const envelopeKeys = new Set(["availability", "staged", "producer", "cache"]);
    const differing = Object.keys(stale).filter(
      k => JSON.stringify(stale[k]) !== JSON.stringify(fresh[k]),
    );
    expect(differing.sort()).toEqual([...envelopeKeys].sort());
  });
});

describe("#7612 — the page does not promise a refresh it is not delivering", () => {
  test("stale: the banner describes 130 missed rebuilds and the card makes no promise", () => {
    const html = render(STALE_ENVELOPE);

    // The banner the reader actually saw, so the contradiction's other half is
    // pinned rather than assumed.
    expect(hasBanner(html)).toBe(true);
    expect(html).toContain("130 hourly rebuilds have come and gone without a new snapshot.");

    expect(whatsIncluded(html)).not.toContain("Data refreshes hourly");
  });

  test("fresh: the sentence is a gate, not a deletion", () => {
    const html = render(FRESH_ENVELOPE);
    expect(hasBanner(html)).toBe(false);
    expect(whatsIncluded(html)).toContain("Data refreshes hourly.");
  });

  test("the relation, not the string: a banner and a refresh promise never co-render", () => {
    // Keyed on the claim's SHAPE, so the next sentence that says it in other
    // words is caught too. Deliberately scoped to the methodology bullet: the
    // banner's own `stalenessScheduleClause` sentence is allowed to name the
    // cadence while describing its failure ("130 hourly rebuilds …"), and a
    // page-wide ban would red on that correct copy.
    const PROMISES_A_REFRESH = /refreshe?s?\s+(?:hourly|every hour)|rebuild(?:s|ed)?\s+hourly|updated?\s+(?:hourly|every hour)/i;

    for (const envelope of [STALE_ENVELOPE, FRESH_ENVELOPE]) {
      const html = render(envelope);
      const promises = PROMISES_A_REFRESH.test(whatsIncluded(html));
      expect(promises).toBe(!hasBanner(html));
    }
  });
});
