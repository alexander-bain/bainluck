/**
 * #7456 — THE SENTENCES THAT STATE A TOTAL NAME EVERY SOURCE BEHIND IT.
 *
 * ── WHAT A READER SAW, MEASURED ON PRODUCTION ───────────────────────────────
 *
 * `https://bainluck.com/calibration` at 390px, all-markets cohort, 2026-09-20
 * (live at `13a23384a`). The hero, the page's first sentence:
 *
 *   "We analyzed 747,028 resolved predictions across Kalshi, Polymarket, and
 *    sportsbook odds (moneylines, spreads, and totals)."
 *
 * 500px below it, on the same phone screen, the Sources stat card:
 *
 *   SOURCES  4
 *   Kalshi · Polymarket · Sportsbooks (Odds API: …) · DataGolf
 *
 * Per provider, from the live payload, grouped by the page's own `providerOf`:
 *
 *   kalshi            326,909 full    214,622 default cohort
 *   polymarket        264,956 full     79,278 default cohort
 *   odds_api_family   155,127 full    155,127 default cohort
 *   datagolf               36 full          0 default cohort
 *   ── total          747,028 full    449,027 default cohort
 *
 * 747,028 is `total_outcomes` exactly, so DataGolf's 36 are INSIDE the number
 * the sentence attributes to three providers.
 *
 * ── TWO SITES, TWO SCOPES, AND ONLY ONE OF THEM WAS EVER TRUE ───────────────
 *
 *   hero, default cohort          449,027  3 providers behind it, 3 named  ✅
 *   hero, all-markets cohort      747,028  4 providers behind it, 3 named  ❌
 *   "What's included?" bullet     `total_outcomes`, ALWAYS the full
 *                                 population — so 4 behind it, 3 named,
 *                                 on every load, in either cohort        ❌
 *
 * This is #6265's ruling — "the page answers 'how many sources' ONCE, from
 * `providerGroups`" — with the NAMES half never converted. That issue fixed
 * every site printing a COUNT and stopped there; these two print a LIST, and
 * have been static strings since before `providerGroups` existed.
 *
 * ── WHAT THIS FILE PINS ─────────────────────────────────────────────────────
 *
 * The PAIRING, both directions, read off the rendered DOM rather than
 * recomputed here: the hero names exactly the providers with outcomes in the
 * cohort, and the bullet names exactly the providers with outcomes in the
 * population. A provider that enters the cohort enters the sentence; one that
 * leaves it leaves the sentence. Wording stays free to change.
 *
 * Three things make it non-vacuous:
 *
 *   1. the production-shaped fixture REPRODUCES the defect — four providers in
 *      the population against a pre-fix literal that named three;
 *   2. the two lists DISAGREE on one render, which is the defect's signature
 *      and the thing a single shared constant could never express;
 *   3. the all-DataGolf-traded fixture proves the hero list is live rather
 *      than a longer hard-coded string.
 *
 * ── WHY THERE IS NO CLICK ───────────────────────────────────────────────────
 *
 * `testEnvironment: 'node'` and `renderToStaticMarkup`, so the cohort toggle
 * cannot be pressed (the same constraint `pinAffordance.test.tsx` records).
 * The all-markets arithmetic is reached the honest way instead — a payload
 * with no `price_moved: false` row, where the default cohort IS the whole
 * population — and the string it produces is pinned at the lib level too.
 */

import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import type { CalibrationData } from "@/lib/api";
import {
  listProviderNames,
  providerLabel,
  providerOf,
  providerProseName,
  PROVIDER_PROSE_NAMES,
} from "@/lib/calibrationProviders";

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

/** The sentence both sites carried before this ship, verbatim. */
const PRE_FIX_LIST = "Kalshi, Polymarket, and sportsbook odds";

/**
 * The production source keys and their outcome counts, 2026-09-20.
 *
 * Per SOURCE key, because that is what the payload carries and what
 * `groupSourcesByProvider` folds — writing the four provider totals instead
 * would hand the code under test its own answer.
 */
const PROD_SOURCES = [
  { source: "kalshi", n: 326_909 },
  { source: "polymarket", n: 264_956 },
  { source: "odds_api_bookmaker", n: 106_030 },
  { source: "odds_api", n: 18_440 },
  { source: "odds_api_totals", n: 15_537 },
  { source: "odds_api_spreads", n: 15_120 },
  { source: "datagolf", n: 36 },
];

/** The share of each source that is `price_moved: false`, as production has it. */
const UNTRADED_SHARE: Record<string, number> = {
  // 326,909 − 214,622
  kalshi: 112_287 / 326_909,
  // 264,956 − 79,278: the source #7202 measured as 70% excluded by default
  polymarket: 185_678 / 264_956,
  // Sportsbook lines carry no flag at all; they are traded by construction (D101)
  odds_api_bookmaker: 0,
  odds_api: 0,
  odds_api_totals: 0,
  odds_api_spreads: 0,
  // The whole content of #2176: every DataGolf row is `price_moved: false`
  datagolf: 1,
};

function bucket(source: string, idx: number, priceMoved: boolean | null, n: number) {
  const p = 0.05 + idx * 0.1;
  return {
    bucket_idx: idx,
    source,
    category: "golf",
    price_moved: priceMoved,
    n,
    winners: Math.round(n * p),
    avg_prob: p,
    sum_prob: n * p,
    sum_sq_err: n * 0.1,
    ci_lower: 0.01,
    ci_upper: 0.99,
  };
}

/**
 * @param datagolfTraded when true, DataGolf's rows carry `price_moved: true`,
 *   so it is in the default cohort as well as the population. That is the
 *   all-markets arithmetic, reachable without a click.
 */
function makePayload(datagolfTraded = false): CalibrationData {
  const buckets = PROD_SOURCES.flatMap(s => {
    const untradedShare = datagolfTraded && s.source === "datagolf" ? 0 : UNTRADED_SHARE[s.source];
    const untraded = Math.round(s.n * untradedShare);
    const traded = s.n - untraded;
    const flag = s.source.startsWith("odds_api") ? null : true;
    const rows = [];
    // Spread over five bins so the page has a curve to aggregate, and so no
    // arm of this file depends on a provider having exactly one bucket.
    for (let i = 0; i < 5; i++) {
      if (traded > 0) rows.push(bucket(s.source, i, flag, Math.round(traded / 5)));
      if (untraded > 0) rows.push(bucket(s.source, i, false, Math.round(untraded / 5)));
    }
    return rows;
  });
  return {
    buckets,
    total_markets: 400_000,
    total_outcomes: buckets.reduce((t, b) => t + b.n, 0),
    total_winners: 300_000,
    mce_ci_lower: 0.01,
    mce_ci_upper: 0.05,
    mce_closing_line: 0.03,
    mce_opening_price: 0.04,
    generated_at: "2026-09-20T09:00:00Z",
    date_range: { start: "2021-09-01", end: "2026-09-20" },
    by_source: PROD_SOURCES.map(s => ({ source: s.source, ece: 0.01, mce: 0.02, n: s.n })),
    by_category: [{ category: "golf", ece: 0.01, n: 400_000 }],
  } as unknown as CalibrationData;
}

function render(datagolfTraded = false): string {
  (global as unknown as { __calPayload: CalibrationData }).__calPayload =
    makePayload(datagolfTraded);
  return renderToStaticMarkup(<CalibrationPage />);
}

/**
 * Read a list out of THE SENTENCE A READER SEES, and prove the element's data
 * hook agrees with it.
 *
 * Both halves are load-bearing and this file shipped without the first one.
 * Mutation-tested on the committed fix: reverting the visible prose to the
 * hard-coded three while leaving `data-population-sources` derived SURVIVED
 * every assertion here, because every reader in this file was pointed at the
 * attribute. The hook is for probes; the prose is the ship.
 *
 * The clause is matched on the element's markup AS IT IS, with no tag-stripping
 * pass. A `.replace(/<[^>]+>/g, "")` stood here for one commit and CodeQL is
 * right to call it `js/incomplete-multi-character-sanitization` (high) — a
 * hand-rolled HTML-to-text helper in a test is still a hand-rolled HTML-to-text
 * helper. It is also unnecessary: neither sentence's "across …" clause contains
 * markup, and if one ever did, the match would carry the tag and fail this
 * function's own agreement check against the hook. Fail-closed, and no stripper.
 */
function listIn(html: string, hook: string, tail: string): string {
  const el = new RegExp(`<(p|li)[^>]*${hook}="([^"]*)"[^>]*>([\\s\\S]*?)</\\1>`).exec(html);
  expect(el).not.toBeNull();
  const m = new RegExp(` across ([^.]*)\\. ${tail}`).exec(el![3]);
  // A null match means the sentence lost its "across …" clause, or the clause
  // moved — either way nothing below can be measuring the right words.
  expect(m).not.toBeNull();
  const prose = m![1];
  // The hook is published for probes; if it and the prose ever disagreed, one
  // of the two would be lying about the same render.
  expect(prose).toBe(el![2]);
  return prose;
}

const heroList = (html: string) => listIn(html, "data-hero-sources", "The answer");
const populationList = (html: string) =>
  listIn(html, "data-population-sources", "That published total");

/** Which providers a rendered list actually names, by the page's own names. */
function namedProviders(list: string, nameOf: (p: string) => string): string[] {
  const all = [...new Set(PROD_SOURCES.map(s => providerOf(s.source)))];
  return all.filter(p => list.includes(nameOf(p)));
}

/* ════════════ the harness proves itself, and the fixture proves the bug ════════════ */

describe("the harness renders the real calibration page on production's shape", () => {
  test("positive control: the page is built, not a loading shell", () => {
    const html = render();
    expect(html).toContain("calibration-hero-sources");
    expect(html).toContain("calibration-stat-sources");
  });

  test("the fixture carries FOUR providers, which is what made three a lie", () => {
    // Without this the pairing tests below would pass on a payload that never
    // had the problem — three providers named, three providers present.
    const providers = new Set(PROD_SOURCES.map(s => providerOf(s.source)));
    expect(providers.size).toBe(4);
    expect(providers.has("datagolf")).toBe(true);
    // And the pre-fix literal named three of them. This is the reproduction:
    // the sentence that shipped could not have named the fourth.
    expect(namedProviders(PRE_FIX_LIST, providerProseName)).toHaveLength(3);
    expect(PRE_FIX_LIST).not.toContain("DataGolf");
  });

  test("the fixture reproduces the cohort gap DataGolf sits in", () => {
    // DataGolf has outcomes in the population and none in the default cohort;
    // every other provider has both. That asymmetry is the whole specimen.
    const html = render();
    expect(populationList(html)).toContain(providerLabel("datagolf"));
    expect(heroList(html)).not.toContain(providerProseName("datagolf"));
  });
});

/* ═════════════ SHIP — a stated total names every source behind it ═════════════ */

describe("#7456 — the hero names the providers in the cohort it counted", () => {
  test("default cohort: the list is byte-identical to the sentence that shipped", () => {
    // The repair must not move a sentence that was already true. Three
    // providers have cohort outcomes, and these are their words.
    expect(heroList(render())).toBe(PRE_FIX_LIST);
  });

  test("a provider that enters the cohort enters the sentence", () => {
    // The other direction, and the one that fails on a longer hard-coded
    // string: same providers, same order, DataGolf's rows merely traded.
    const html = render(true);
    expect(heroList(html)).toBe("Kalshi, Polymarket, sportsbook odds, and DataGolf");
    expect(heroList(html)).not.toBe(heroList(render()));
  });

  test("the hero names EXACTLY the providers with cohort outcomes, both ways", () => {
    for (const datagolfTraded of [false, true]) {
      const html = render(datagolfTraded);
      const expected = datagolfTraded
        ? ["kalshi", "polymarket", "odds_api_family", "datagolf"]
        : ["kalshi", "polymarket", "odds_api_family"];
      expect(namedProviders(heroList(html), providerProseName)).toEqual(expected);
    }
  });

  test("the sentence reaches the reader, not just the data attribute", () => {
    // A hook nobody renders into prose would let the visible sentence keep
    // saying anything at all.
    const html = render(true);
    expect(html).toContain(`across ${heroList(html)}`);
  });
});

describe("#7456 — the methodology bullet names the population it counted", () => {
  test("it names all four providers in the default cohort, where the hero names three", () => {
    // The disagreement IS the ship: one sentence counts the cohort, the other
    // counts `total_outcomes`, and a single shared list could not be right for
    // both. This is the assertion a fix that wires one constant into both
    // sites fails.
    const html = render();
    expect(namedProviders(populationList(html), providerLabel)).toEqual([
      "kalshi", "polymarket", "odds_api_family", "datagolf",
    ]);
    expect(namedProviders(heroList(html), providerProseName)).toHaveLength(3);
  });

  test("it is unmoved by the cohort, because its subject is", () => {
    expect(populationList(render(true))).toBe(populationList(render()));
  });

  test("it keeps the supplier attribution the hand-written '(via The Odds API)' carried", () => {
    // The parenthetical was deleted, not lost: the bullet names the Source
    // Comparison rows the way those rows are labelled.
    expect(populationList(render())).toContain("Odds API");
  });
});

/* ══════════════════════ the naming rule itself ══════════════════════ */

describe("#7456 — listProviderNames", () => {
  test("the all-markets list is the sentence production should have printed", () => {
    expect(
      listProviderNames(["kalshi", "polymarket", "odds_api_family", "datagolf"])
    ).toBe("Kalshi, Polymarket, sportsbook odds, and DataGolf");
  });

  test("two names take no serial comma, one takes no conjunction, none takes nothing", () => {
    expect(listProviderNames(["kalshi", "polymarket"])).toBe("Kalshi and Polymarket");
    expect(listProviderNames(["kalshi"])).toBe("Kalshi");
    // Empty means the caller renders no "across …" clause at all, rather than
    // a sentence trailing into a full stop.
    expect(listProviderNames([])).toBe("");
  });

  test("a duplicated provider key cannot name a provider twice", () => {
    expect(listProviderNames(["kalshi", "kalshi", "polymarket"])).toBe("Kalshi and Polymarket");
  });

  test("an unmapped provider still reaches the sentence, by its table name", () => {
    // The failure this exists to prevent is a provider counted in a total and
    // missing from the list explaining it. A stiff phrase beats an omission.
    expect(listProviderNames(["kalshi", "pinnacle_model"]))
      .toBe("Kalshi and Pinnacle Model");
  });

  test("the prose register and the label register genuinely differ", () => {
    // If these ever collapsed, one of the two sentences would be wrong and no
    // other test here would notice — both would still be internally consistent.
    expect(providerProseName("odds_api_family")).toBe("sportsbook odds");
    expect(providerLabel("odds_api_family")).toBe("Sportsbooks (Odds API)");
  });

  test("the prose map is CLOSED over the providers the payload publishes", () => {
    // So the fallback is never the thing a reader sees. Fails loudly when the
    // payload grows a fifth provider, which is exactly when someone should be
    // choosing its words rather than inheriting a table label.
    for (const p of new Set(PROD_SOURCES.map(s => providerOf(s.source)))) {
      expect(Object.keys(PROVIDER_PROSE_NAMES)).toContain(p);
    }
  });
});
