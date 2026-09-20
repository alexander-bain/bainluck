/**
 * #7422 — the By Source panel's ECE is measured over the population it prints.
 *
 * Shopped on production at 390px, 2026-09-20 07:50Z, in the DEFAULT (traded)
 * cohort. One page, one provider, one outcome count, two answers:
 *
 *   Source Comparison (y≈1,180)
 *     Polymarket | 79,278 | 2.7pp | 2.6pp | 0.1539
 *
 *   By Source panel (y≈2,800)
 *     Polymarket · 1.6pp ECE · 79,278 outcomes · 17.7% of the curve
 *
 * `1.57` is `by_source[].ece` verbatim — the WHOLE-population figure, measured
 * over 264,956 outcomes. The panel printed it beside a population of 79,278.
 * Recomputed from the served `buckets[]`, n-weighted: polymarket traded is
 * 2.70pp and polymarket all-markets is 1.57pp, so the table was right.
 *
 * The tell is that the panel's ECE did not move when its own population did:
 *
 *   cohort            panel n    panel share   panel ECE
 *   traded (default)   79,278    17.7%         1.6pp
 *   all markets       264,956    35.5%         1.6pp
 *
 * Everything else in the frame — n, share, and the plotted curve — is
 * cohort-filtered. Only the headline number was not.
 *
 * ═══ WHAT THIS FILE GUARDS, AND WHY IN THIS SHAPE ═══
 *
 *   1. PAIRING, FOR EVERY PROVIDER — each panel's `data-panel-ece` equals its
 *      own Source Comparison row's `data-row-ece`. `calibrationProviderPanels.ts`
 *      already argued that a pairing assertion is what makes disagreement
 *      unrepresentable, and shipped one — for the Sportsbooks panel only, the
 *      arm that already took the cohort-aware road. Scoping the guard to the
 *      arm that behaves is precisely how the other arm got to be wrong for as
 *      long as the cohort toggle has existed. This is the load-bearing arm.
 *   2. NOT VACUOUS — the fixture is adversarial by assertion: polymarket's
 *      published `by_source` figure and its traded-cohort figure are checked to
 *      DIFFER by more than the display precision before the pairing is read. A
 *      fixture where the two agree satisfies arm 1 against the broken code.
 *   3. NO-CHANGE — kalshi and the sportsbook family are unchanged to the
 *      reader. Kalshi carried the identical defect on production and hid inside
 *      its own rounding (0.92 traded against 0.89 published, both printing
 *      "0.9pp"); a fix that moved it would be a visible regression.
 *   4. #7411 STILL WINS — a censored provider publishes no ECE and no basis
 *      other than `censored`, in the cohort where it has outcomes. The pairing
 *      in arm 1 must not have reintroduced a number on that panel.
 *
 * The OTHER cohort cannot be reached here: the toggle is `useState` and this
 * page is rendered statically. That half is `eceInputsForPanel`'s unit block in
 * `__tests__/lib/calibrationProviderPanels.test.ts`, which is why that rule was
 * extracted out of the page in the first place — an inline ternary had a half
 * no test could reach, and that is the half that shipped wrong.
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

jest.mock("@/components/CalibrationChart", () => {
  const ReactLib = require("react");
  return {
    __esModule: true,
    default: () => ReactLib.createElement("div", { "data-testid": "chart" }),
  };
});

jest.mock("next/link", () => {
  const ReactLib = require("react");
  return {
    __esModule: true,
    default: ({ href, children, ...props }: { href: string; children: React.ReactNode }) =>
      ReactLib.createElement("a", { href, ...props }, children),
  };
});

import CalibrationPage from "@/app/calibration/page";

/* ───────────────────────────── the fixture ───────────────────────────── */

function bucket(
  source: string,
  idx: number,
  n: number,
  avgProb: number,
  winners: number,
  priceMoved: boolean,
) {
  return {
    bucket_idx: idx,
    source,
    category: "baseball",
    price_moved: priceMoved,
    n,
    winners,
    avg_prob: avgProb,
    sum_prob: avgProb * n,
    sum_sq_err: n * 0.1,
    ci_lower: 0.01,
    ci_upper: 0.99,
  };
}

/**
 * Polymarket, in production's shape: a traded slice that is materially worse
 * calibrated than the untraded bulk it is pooled with.
 *
 *   traded   80,000 @ 0.55 predicted, 0.52 actual  →  3.0pp
 *   untraded 180,000 @ 0.55 predicted, 0.55 actual →  0.0pp
 *   pooled   260,000 @ 0.55 predicted, 0.5408      →  ~0.9pp
 *
 * So the whole-population number the server publishes is about a THIRD of the
 * traded one, exactly the direction production showed (1.57 against 2.70).
 */
const POLY_TRADED_N = 80_000;
const POLY_UNTRADED_N = 180_000;
const POLYMARKET = [
  bucket("polymarket", 5, POLY_TRADED_N, 0.55, 41_600, true),
  bucket("polymarket", 5, POLY_UNTRADED_N, 0.55, 99_000, false),
];
/** What the server publishes for polymarket: the POOLED figure, whole population. */
const POLY_PUBLISHED_ECE = 0.9;

/**
 * Kalshi, the no-change control: every outcome traded, so its two cohorts are
 * the same population and its published figure is its cohort figure. It must
 * read the same before and after this fix.
 */
const KALSHI = [
  bucket("kalshi", 1, 50_000, 0.15, 7_000, true),
  bucket("kalshi", 5, 100_000, 0.55, 56_000, true),
];

/** The sportsbook family — multi-shape, already cohort-aware, must not move. */
const SPORTSBOOKS = [
  bucket("odds_api", 5, 18_000, 0.52, 9_200, true),
  bucket("odds_api_totals", 5, 15_000, 0.5, 7_600, true),
];

/** DataGolf: 36 outcomes, every one a winner — #7411's censored population. */
const DATAGOLF = [
  bucket("datagolf", 4, 3, 0.4367, 3, true),
  bucket("datagolf", 5, 9, 0.5552, 9, true),
  bucket("datagolf", 6, 14, 0.6504, 14, true),
  bucket("datagolf", 7, 9, 0.7355, 9, true),
  bucket("datagolf", 8, 1, 0.8326, 1, true),
];

function payload(): CalibrationData {
  const buckets = [...KALSHI, ...POLYMARKET, ...SPORTSBOOKS, ...DATAGOLF];
  const total = buckets.reduce((s, b) => s + b.n, 0);
  return {
    buckets,
    total_markets: 400_000,
    total_outcomes: total,
    total_winners: buckets.reduce((s, b) => s + b.winners, 0),
    mce_ci_lower: 0.33,
    mce_ci_upper: 1.19,
    mce_closing_line: 0.03,
    mce_opening_price: 0.04,
    generated_at: "2026-09-20T07:00:00Z",
    date_range: { start: "2026-01-01", end: "2026-09-20" },
    // Every one of these is WHOLE-POPULATION, which is the whole point: the
    // payload has no cohort dimension to offer.
    by_source: [
      { source: "kalshi", ece: 1.0, mce: 1.3, n: 150_000 },
      { source: "polymarket", ece: POLY_PUBLISHED_ECE, mce: 1.1, n: 260_000 },
      { source: "odds_api", ece: 1.5, mce: 1.6, n: 18_000 },
      { source: "odds_api_totals", ece: 2.5, mce: 2.6, n: 15_000 },
      { source: "datagolf", ece: 36.5, mce: 35.8, n: 36 },
    ],
    by_category: [{ category: "baseball", ece: 0.9, n: total }],
  } as unknown as CalibrationData;
}

function render(): string {
  (global as unknown as { __calPayload: CalibrationData }).__calPayload = payload();
  return renderToStaticMarkup(<CalibrationPage />);
}

/* ─────────────────────────────── readers ─────────────────────────────── */

/** Every open tag carrying `testid`, as raw attribute text. */
function tagsFor(html: string, testid: string): string[] {
  return html.match(new RegExp(`<[a-z]+[^>]*data-testid="${testid}"[^>]*>`, "g")) ?? [];
}

function attr(tag: string, name: string): string | null {
  const m = tag.match(new RegExp(`${name}="([^"]*)"`));
  return m ? m[1] : null;
}

/** `{ provider: { ece, basis } }` for the By Source panels. */
function panels(html: string): Record<string, { ece: string | null; basis: string | null }> {
  const out: Record<string, { ece: string | null; basis: string | null }> = {};
  for (const tag of tagsFor(html, "calibration-provider-panel")) {
    const provider = attr(tag, "data-provider");
    if (provider) out[provider] = { ece: attr(tag, "data-panel-ece"), basis: attr(tag, "data-ece-basis") };
  }
  return out;
}

/** `{ provider: { ece, state } }` for the Source Comparison rows. */
function rows(html: string): Record<string, { ece: string | null; state: string | null }> {
  const out: Record<string, { ece: string | null; state: string | null }> = {};
  for (const tag of tagsFor(html, "calibration-provider-row")) {
    const provider = attr(tag, "data-provider");
    if (provider) out[provider] = { ece: attr(tag, "data-row-ece"), state: attr(tag, "data-row-state") };
  }
  return out;
}

/* ──────────────────────────────── the arms ───────────────────────────── */

describe("#7422 — the fixture is adversarial (arm 2, read first)", () => {
  it("polymarket's published figure and its traded figure really do differ", () => {
    // Without this the pairing below passes against the broken code, because a
    // panel rendering the wrong number still matches a row that happens to
    // carry the same one. The whole guard rests on this being true.
    const r = rows(render()).polymarket;
    expect(r).toBeDefined();
    const traded = Number(r.ece);
    expect(Number.isFinite(traded)).toBe(true);
    expect(Math.abs(traded - POLY_PUBLISHED_ECE)).toBeGreaterThan(0.5);
  });

  it("the page renders a panel AND a row for every measured provider", () => {
    // A pairing over an empty intersection is the other way to be vacuous.
    const html = render();
    const measured = Object.entries(rows(html))
      .filter(([, r]) => r.state !== "no-cohort-data")
      .map(([p]) => p);
    expect(measured.length).toBeGreaterThanOrEqual(3);
    for (const provider of measured) expect(panels(html)[provider]).toBeDefined();
  });
});

describe("#7422 — a panel's ECE is its own row's ECE, for EVERY provider (arm 1)", () => {
  it("panel and row agree, provider by provider", () => {
    const html = render();
    const p = panels(html);
    const r = rows(html);
    for (const [provider, row] of Object.entries(r)) {
      if (row.state === "no-cohort-data") continue;
      // A censored provider publishes no figure on either surface — arm 4.
      // `data-panel-ece={null}` is OMITTED by React rather than emitted empty,
      // so absence is the encoding and `attr()` reads it back as null.
      if (row.state === "censored") {
        expect(p[provider].ece).toBeNull();
        continue;
      }
      expect({ provider, ece: p[provider].ece }).toEqual({ provider, ece: row.ece });
    }
  });

  it("polymarket specifically: the traded figure, NOT the published one", () => {
    // The defect, named. Pre-#7422 this panel read 0.9 (the server's whole
    // population) beside a row reading ~3.0 about the same 80,000 outcomes.
    const html = render();
    expect(Number(panels(html).polymarket.ece)).toBeCloseTo(3.0, 1);
    expect(Number(panels(html).polymarket.ece)).not.toBeCloseTo(POLY_PUBLISHED_ECE, 1);
    expect(panels(html).polymarket.basis).toBe("pooled");
  });

  it("a filtered panel never claims a 'published' basis", () => {
    // In the default cohort the server has measured no panel's population, so
    // no panel may claim its number came from the payload. The `published`
    // basis is still reachable — in the other cohort, covered by the unit test
    // for `eceInputsForPanel`.
    for (const [provider, panel] of Object.entries(panels(render()))) {
      expect({ provider, basis: panel.basis }).not.toEqual({ provider, basis: "published" });
    }
  });
});

describe("#7422 — no-change arms (arm 3)", () => {
  it("kalshi is unchanged: its cohorts are one population and it reads that figure", () => {
    // 7,000/50,000 = 14% against 15% predicted, and 56,000/100,000 = 56%
    // against 55%: n-weighted 1.0pp, which is also what `by_source` publishes.
    // A fix that moved this number would be the regression, not the repair.
    const html = render();
    expect(Number(panels(html).kalshi.ece)).toBeCloseTo(1.0, 1);
    expect(panels(html).kalshi.ece).toBe(rows(html).kalshi.ece);
  });

  it("the multi-shape sportsbook panel is pooled, exactly as before", () => {
    const html = render();
    const family = Object.keys(panels(html)).find(k => k.includes("odds_api"))!;
    expect(panels(html)[family].basis).toBe("pooled");
    expect(panels(html)[family].ece).toBe(rows(html)[family].ece);
  });
});

describe("#7422 — #7411's censoring still wins over both bases (arm 4)", () => {
  it("datagolf publishes no ECE and says 'censored', not 'pooled'", () => {
    const html = render();
    const dg = panels(html).datagolf;
    expect(dg).toBeDefined();
    expect(dg.basis).toBe("censored");
    // Omitted, not empty: React drops a null-valued attribute entirely.
    expect(dg.ece).toBeNull();
    // And the row it is paired with agrees about the population.
    expect(rows(html).datagolf.state).toBe("censored");
  });
});
