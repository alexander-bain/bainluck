/**
 * #7411 — By Source stops publishing the ECE that Source Comparison refuses.
 *
 * Shopped on production at 390px, 2026-09-20, in the all-markets cohort. One
 * page, one population of 36 outcomes, two answers:
 *
 *   Source Comparison (y≈1,180)
 *     DataGolf | 36 | All 36 won — no losses to measure against.
 *
 *   By Source panel (y≈4,945)
 *     DataGolf · 36.5pp ECE · 36 outcomes · 0.0% of the curve
 *     …over a curve pinned flat at 100% actual across the 40-85% predicted range.
 *
 * #6211 settled what that number is worth: *"a reader could read 36.5pp as
 * 'DataGolf is badly calibrated', which is a claim we cannot support about a
 * named third party."* Observed frequency is 1.0 in every bucket while the
 * price says 0.44-0.83, so the ~36pp gap is there by construction — it measures
 * our own read-side censoring.
 *
 * `censoringVerdict` shipped with that fix and had exactly two call sites, both
 * inside `calibrationSourceRows.ts`. The panel builders never consulted it:
 * their only refusal rule is `n > 0`, which is right and does not reach 36.
 *
 * ═══ WHAT THIS FILE GUARDS, AND WHY IN THIS SHAPE ═══
 *
 *   1. BEHAVIOUR — a censored provider publishes no ECE and states the fact,
 *      AND the page is proven to be still drawing its curve in the same breath.
 *      Without that second half the whole suite passes against a version that
 *      simply dropped the panel — which is #6211 item 3's named wrong answer:
 *      *"suppressing it … would delete the alarm and keep the defect."* The
 *      flat line at 100% IS the alarm. This is the load-bearing arm.
 *   2. PAIRING — the panel's sentence and the table row's sentence are read out
 *      of the rendered page at their two testids and compared byte-for-byte.
 *      Fixing this defect gave the page a SECOND place to word one fact, and
 *      two places wording it differently is the same disease one layer up. A
 *      ban would be satisfied by deleting a word; a pairing is not (UX-P075).
 *   3. NO-CHANGE — the measured providers still publish their ECEs and carry no
 *      censored note. `censored: true` for everyone passes arms 1 and 2 and
 *      blanks the page.
 *   4. BOTH DIRECTIONS, EXACTLY — all-losers censors too, with its own wording,
 *      and ONE loser among 36 does not censor at all. The verdict is exact
 *      rather than a threshold, and a 99%-one-sided population is a real
 *      measurement of a skewed population, not a censored one.
 */

import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import type { CalibrationData } from "@/lib/api";
import { buildSourcePanels } from "@/lib/calibrationMath";
import { censoredPopulationText, censoringVerdict } from "@/lib/calibrationSourceRows";

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

/**
 * The chart PUBLISHES the series it was handed rather than rendering nothing.
 *
 * `null` is the usual stub on this page and it would make arm 1 vacuous: with
 * no chart there is no evidence the censored provider's curve ever reached a
 * reader, and "the panel withholds its ECE" would pass against a page that
 * deleted the panel. Recharts internals are not the subject; what the page
 * HANDED the chart is the same question a reader answers by looking at it.
 */
jest.mock("@/components/CalibrationChart", () => {
  const ReactLib = require("react");
  return {
    __esModule: true,
    default: ({ series }: { series: { label?: string; data: { bucket: string; error: number }[] }[] }) =>
      ReactLib.createElement("div", {
        "data-testid": "chart-points",
        "data-points": (series ?? [])
          .flatMap(s => (s.data ?? []).map(d => `${s.label ?? "?"}|${d.bucket}|${d.error}`))
          .join(";"),
      }),
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

function bucket(source: string, idx: number, n: number, avgProb: number, winners: number) {
  return {
    bucket_idx: idx,
    source,
    category: "golf",
    price_moved: true,
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
 * DataGolf's five published buckets, as #6211 measured them on production —
 * the real n and avg_prob, and every outcome a winner.
 *
 * `winnersOf` is what the arms below vary, so one fixture covers all-won,
 * all-lost, and the one-loser boundary without three payload builders drifting
 * apart. The default is the live shape.
 */
const DG = [
  { idx: 4, n: 3, avgProb: 0.4367 },
  { idx: 5, n: 9, avgProb: 0.5552 },
  { idx: 6, n: 14, avgProb: 0.6504 },
  { idx: 7, n: 9, avgProb: 0.7355 },
  { idx: 8, n: 1, avgProb: 0.8326 },
];
const DG_N = DG.reduce((s, b) => s + b.n, 0);

/** The two providers that carry the page, both with mixed outcomes. */
const CARRIERS = [
  bucket("kalshi", 1, 50_000, 0.15, 7_500),
  bucket("kalshi", 5, 100_000, 0.55, 55_000),
  bucket("polymarket", 5, 20_000, 0.55, 11_000),
];

type Side = "all-won" | "all-lost" | "one-loser";

function datagolfBuckets(side: Side) {
  return DG.map((b, i) => {
    if (side === "all-lost") return bucket("datagolf", b.idx, b.n, b.avgProb, 0);
    // One loser lives in the largest bucket, so 35 of 36 won: as one-sided as a
    // population can get without being censored.
    const winners = side === "one-loser" && i === 2 ? b.n - 1 : b.n;
    return bucket("datagolf", b.idx, b.n, b.avgProb, winners);
  });
}

function payload(side: Side): CalibrationData {
  const buckets = [...CARRIERS, ...datagolfBuckets(side)];
  const total = buckets.reduce((s, b) => s + b.n, 0);
  return {
    buckets,
    total_markets: 12_000,
    total_outcomes: total,
    total_winners: buckets.reduce((s, b) => s + b.winners, 0),
    mce_ci_lower: 0.33,
    mce_ci_upper: 1.19,
    mce_closing_line: 0.03,
    mce_opening_price: 0.04,
    generated_at: "2026-09-20T07:00:00Z",
    date_range: { start: "2026-01-01", end: "2026-09-20" },
    // The server DOES publish a figure for datagolf. That is the point: the
    // page has a number to render and declines to, rather than having none.
    by_source: [
      { source: "kalshi", ece: 0.9, mce: 1.3, n: 150_000 },
      { source: "polymarket", ece: 1.6, mce: 1.8, n: 20_000 },
      { source: "datagolf", ece: 36.5, mce: 35.8, n: DG_N },
    ],
    by_category: [{ category: "golf", ece: 0.9, n: total }],
  } as unknown as CalibrationData;
}

function render(side: Side = "all-won"): string {
  (global as unknown as { __calPayload: CalibrationData }).__calPayload = payload(side);
  return renderToStaticMarkup(<CalibrationPage />);
}

/* ─────────────────────────────── readers ─────────────────────────────── */

/** The whole of one element, from its testid to the end of its open tag's block. */
function blockAt(html: string, testid: string, extra = ""): string | null {
  const key = `data-testid="${testid}"${extra}`;
  const start = html.indexOf(key);
  if (start === -1) return null;
  // Walk back to the element's own `<`, then take a generous slice: the
  // sentences these arms read are plain text inside a leaf element.
  const open = html.lastIndexOf("<", start);
  const close = html.indexOf(">", start);
  const end = html.indexOf("<", close);
  return html.slice(open, end === -1 ? close : end);
}

/**
 * The ECE a named provider's By Source panel published, as a number, or `null`
 * when it published none.
 *
 * #7422 changed WHICH figure that is — in a cohort-filtered view the panel
 * renders the cohort's own figure rather than `by_source`'s whole-population
 * one — so two arms below that substring-matched this fixture's payload
 * literals ("0.9pp ECE", "36.5pp ECE") were asserting a basis neither of them
 * is about. Reading the attribute per provider says what they actually mean:
 * this panel published a figure, and it is not censored.
 */
function panelEce(html: string, provider: string): number | null {
  const tag = (html.match(
    new RegExp(`<[a-z]+[^>]*data-testid="calibration-provider-panel"[^>]*>`, "g")
  ) ?? []).find(t => t.includes(`data-provider="${provider}"`));
  const m = tag?.match(/data-panel-ece="([^"]*)"/);
  return m && m[1] !== "" ? Number(m[1]) : null;
}

/** The text a testid renders, tags stripped, entities the page emits decoded. */
function textAt(html: string, testid: string): string | null {
  const block = blockAt(html, testid);
  if (block === null) return null;
  const gt = block.indexOf(">");
  return block
    .slice(gt + 1)
    .replace(/&#x27;|&apos;/g, "'")
    .replace(/&quot;/g, '"')
    .replace(/&mdash;/g, "—")
    .replace(/&amp;/g, "&")
    .trim();
}

/**
 * The `<div>` the DataGolf PANEL is.
 *
 * Anchored on the panel's own testid, not on `data-provider="datagolf"` alone:
 * the Source Comparison ROW carries that same attribute and comes first in the
 * document, so the bare marker reads the table and these arms would be grading
 * the surface that was already correct.
 */
function datagolfPanel(html: string): string | null {
  const key = 'data-testid="calibration-provider-panel" data-provider="datagolf"';
  const at = html.indexOf(key);
  if (at === -1) return null;
  const open = html.lastIndexOf("<div", at);
  // Enough to cover the header, the count line and the chart stub beneath it.
  return html.slice(open, open + 2_000);
}

/** Every `label|bucket|error` the page handed a chart. */
function chartPoints(html: string): string[] {
  const out: string[] = [];
  const key = 'data-points="';
  let at = html.indexOf(key);
  while (at > -1) {
    const from = at + key.length;
    const to = html.indexOf('"', from);
    if (to > from) out.push(...html.slice(from, to).split(";").filter(Boolean));
    at = html.indexOf(key, to);
  }
  return out;
}

/* ═══════════════ 1. BEHAVIOUR — withheld, and still drawn ═══════════════ */

describe("a censored provider publishes no ECE, and is still on the page", () => {
  const html = render("all-won");

  test("the verdict the fixture encodes is the one #6211 measured", () => {
    // Guards the fixture itself: if this ever stops being a censored 36, every
    // arm below is asserting about a population that is not the specimen.
    const v = censoringVerdict(datagolfBuckets("all-won"));
    expect(v.n).toBe(36);
    expect(v.winners).toBe(36);
    expect(v.censored).toBe(true);
  });

  test("the 36.5pp the payload published does NOT reach the panel", () => {
    const panel = datagolfPanel(html);
    expect(panel).not.toBeNull();
    expect(panel).not.toContain("36.5pp");
    // Not merely absent from the panel — absent from the page. The figure has
    // one other rendering, the table row, and #6211 already withholds it there.
    expect(html).not.toContain("36.5pp");
  });

  test("the panel says which way the population fell, where the number was", () => {
    expect(textAt(html, "calibration-panel-censored")).toBe(
      "All 36 won — no losses to measure against."
    );
  });

  test("and the page is STILL DRAWING the curve — this is #6211 item 3", () => {
    // The arm that refuses the easy wrong answer. Dropping the panel satisfies
    // every assertion above and deletes the only visible alarm for a censored
    // population. All five buckets must still be handed to a chart.
    const drawn = chartPoints(html).filter(p => p.startsWith("DataGolf|"));
    expect(drawn).toHaveLength(DG.length);
    // And the count the panel states is the real one, not rounded away.
    expect(datagolfPanel(html)).toContain("36 outcomes");
  });

  test("the withholding is machine-readable as a REFUSAL, not an absence", () => {
    // `"none"` means the server published nothing; `"censored"` means it did
    // and we declined. A rail that cannot tell them apart cannot alarm on the
    // second, which is the one that means something is wrong upstream.
    expect(datagolfPanel(html)).toContain('data-ece-basis="censored"');
  });
});

/* ═════════════════ 2. PAIRING — one fact, one sentence ═════════════════ */

describe("the panel and the table row state one population in one sentence", () => {
  test("byte-for-byte identical, read from the two rendered testids", () => {
    const html = render("all-won");
    const row = textAt(html, "calibration-provider-censored");
    const panel = textAt(html, "calibration-panel-censored");
    expect(row).toBe("All 36 won — no losses to measure against.");
    expect(panel).toBe(row);
  });

  test("both come from `censoredPopulationText`, so they cannot drift apart", () => {
    // The pairing above proves they agree TODAY. This proves they agree
    // because they are one expression, not because someone kept two literals
    // in step — which is the thing that fails silently six months from now.
    expect(censoredPopulationText(36, 36)).toBe("All 36 won — no losses to measure against.");
    expect(censoredPopulationText(36, 0)).toBe("All 36 lost — no wins to measure against.");
    // Thousands separators, because the row has always had them and a panel
    // that dropped them would be a second wording by another name.
    expect(censoredPopulationText(12_345, 12_345)).toContain("12,345");
  });
});

/* ══════════════ 3. NO-CHANGE — the measured page is untouched ══════════════ */

describe("providers with two-sided populations are completely unaffected", () => {
  const html = render("all-won");

  test("Kalshi and Polymarket still publish an ECE each", () => {
    // If this reddens, the gate is censoring the page rather than the censored
    // population — the mutation that passes every arm above.
    //
    // Read per provider rather than as a substring of the payload's literals:
    // since #7422 a cohort-filtered panel renders the COHORT's figure, not
    // `by_source`'s, and this fixture's payload numbers disagree with its own
    // buckets. Which figure it is belongs to #7422's pairing guard; what THIS
    // arm is about is that a two-sided provider still publishes one at all.
    expect(panelEce(html, "kalshi")).not.toBeNull();
    expect(panelEce(html, "polymarket")).not.toBeNull();
    expect(html).not.toContain("NaNpp ECE");
  });

  test("exactly ONE panel on the page is censored", () => {
    const hits = html.split('data-testid="calibration-panel-censored"').length - 1;
    expect(hits).toBe(1);
  });

  test("their curves are drawn, as they always were", () => {
    const labels = new Set(chartPoints(html).map(p => p.split("|")[0]));
    expect(labels.has("Kalshi")).toBe(true);
    expect(labels.has("Polymarket")).toBe(true);
  });
});

/* ══════════ 4. BOTH DIRECTIONS, AND the boundary is EXACT ══════════ */

describe("all-losers is censored too, and 35-of-36 is not censored at all", () => {
  test("an all-losers population is withheld, in its own words", () => {
    // Same arithmetic: an observed frequency of 0 in every bucket makes the
    // error as price-determined as an observed 1 does.
    const html = render("all-lost");
    expect(html).not.toContain("36.5pp");
    expect(textAt(html, "calibration-panel-censored")).toBe(
      "All 36 lost — no wins to measure against."
    );
  });

  test("ONE loser among 36 publishes the figure — the verdict is exact", () => {
    // A threshold (`>= 99% one-sided`) passes every other arm in this file and
    // withholds measurements of genuinely skewed populations. 35/36 is 97.2%
    // one-sided and is a real measurement.
    const v = censoringVerdict(datagolfBuckets("one-loser"));
    expect(v.winners).toBe(35);
    expect(v.censored).toBe(false);

    const html = render("one-loser");
    // A figure IS published for this population — the point of the arm. Which
    // figure is #7422's question: in the default cohort the panel renders the
    // cohort's own number, so the payload literal "36.5pp ECE" no longer names
    // it and would make this arm assert a basis it is not about.
    expect(panelEce(html, "datagolf")).not.toBeNull();
    expect(blockAt(html, "calibration-panel-censored")).toBeNull();
  });
});

/* ═══════════ 5. THE SHAPE PANELS GET THE SAME GATE ═══════════ */

describe("buildSourcePanels applies the gate one level down", () => {
  // No shape is censored on today's payload — the one that is, DataGolf, is a
  // single-source provider. That is exactly why this arm exists: the gate
  // #6211 built was meant to catch the NEXT one-sided source without anyone
  // walking the page, and a gate wired only to the surfaces that happen to be
  // failing today is not that gate.
  const shapes = (winners: number) => [
    { source: "odds_api_totals", buckets: [{ n: 800, error: 40, winners }], publishedEce: 12.3 },
    { source: "odds_api_spreads", buckets: [{ n: 900, error: 2, winners: 450 }], publishedEce: 0.4 },
  ];

  test("a one-sided shape withholds its published ECE and says which side", () => {
    const [totals] = buildSourcePanels(shapes(800)).filter(p => p.source === "odds_api_totals");
    expect(totals.censored).toBe(true);
    expect(totals.ece).toBeNull();
    expect(totals.winners).toBe(800);
    expect(censoredPopulationText(totals.n, totals.winners)).toBe(
      "All 800 won — no losses to measure against."
    );
  });

  test("its two-sided sibling in the same call is untouched", () => {
    const [spreads] = buildSourcePanels(shapes(800)).filter(p => p.source === "odds_api_spreads");
    expect(spreads.censored).toBe(false);
    expect(spreads.ece).toBe(0.4);
    expect(spreads.winners).toBeNull();
  });

  test("a two-sided shape keeps its number", () => {
    const [totals] = buildSourcePanels(shapes(400)).filter(p => p.source === "odds_api_totals");
    expect(totals.censored).toBe(false);
    expect(totals.ece).toBe(12.3);
  });

  test("an empty population is DROPPED, never censored", () => {
    // `censoringVerdict`'s `n > 0` guard. Zero winners of zero outcomes is not
    // an all-losers population, it is no population, and the existing drop rule
    // already owns it — the gate must not steal that case and relabel it.
    expect(buildSourcePanels([{ source: "ghost", buckets: [{ n: 0, error: 0, winners: 0 }] }])).toEqual([]);
  });
});
