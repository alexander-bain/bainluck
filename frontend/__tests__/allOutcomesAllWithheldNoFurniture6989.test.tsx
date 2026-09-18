/**
 * #6989 — "ALL OUTCOMES" DREW A SORT TOOLBAR AND AN "as of Feb 27" OVER ZERO ROWS.
 *
 * Production specimen, re-read live 2026-09-18 18:54Z from
 * `api.bainluck.com/api/futures/109681` — "CPI year-over-year in Oct 2026?",
 * `status: open`, `source: kalshi`, `outcome_count: 16`, `prices_withheld: 16`,
 * `openings_withheld: true`, and all 16 legs `probability: null` carrying
 * `last_updated: 2026-02-27T21:45:16.485704+00:00`. Reader frame at 390px:
 * `artifacts/ux-1341/before-6989-109681-390.png` —
 *
 *     📊 All Outcomes   as of Feb 27
 *     [ Probability ↓ ] [ Last move ] [ Name ]
 *     ▶ More outcomes (16)
 *
 * …and nothing else. Three chips that reorder an empty list, and a seven-month-old
 * date attached to prices that are not on screen. Not a blank card — a working
 * control panel with nothing behind it, which is the worse failure, and exactly
 * the diagnostic furniture notice 34 / D102 forbid.
 *
 * ═══ WHAT IS **NOT** THE BUG, and the whole reason this file exists ═══
 *
 * 🔴 The WITHHOLDING is correct and this ship does not touch it. All 16 legs sit
 * on empty books (`bid 0.0000 / ask 0.9800`); their stored `0.49`/`0.50`
 * midpoints are the artifact #6757/#6727 exist to remove, and the standing rule
 * is withhold-never-rewrite. lane1b, which owns that rail, filed this and said
 * so. A "fix" that made numbers reappear would be the real regression, so the
 * test below asserts the folded rows keep their `-` and nothing prints a percent.
 *
 * ═══ THE CASE THAT SEPARATES THE RIGHT PREDICATE FROM THE PLAUSIBLE ONE ═══
 *
 * 🪤 The obvious predicate is "this market has withheld rows" —
 * `unpricedOutcomes.length > 0`. It is green on the specimen and WRONG: #4568's
 * own UFC ladder (14 priced + 5 numberless, `/futures/114175`) has withheld rows
 * too, and under that predicate it would lose the sort chips that order its
 * fourteen real prices. The predicate is the LISTED count, and `ufcPartial()`
 * below is the control that can tell the two apart. A suite without it cannot.
 *
 * ═══ THE ONE WAY THIS SHIP COULD DO HARM ═══
 *
 * 🔴 Suppressing furniture one gate too far takes the SECTION with it. The
 * heading and the disclosure are asserted present on the all-withheld specimen
 * for that reason — "the card vanished" would satisfy every "the chips are
 * gone" assertion in this file if they were written as bare absences.
 *
 * Assertions are POSITIONAL, split at the `<details>` boundary, for #4568's
 * reason: `<details>` renders its contents into the markup and the browser
 * collapses them, so a bare `toContain` cannot tell folded from visible, and a
 * bare `not.toContain` demands a deletion gotcha #43 forbids.
 */
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";

jest.mock("next/navigation", () => ({
  useSearchParams: () => new URLSearchParams(""),
  useRouter: () => ({ replace: () => {}, push: () => {} }),
}));

let ACTIVE_MARKET: unknown = null;

jest.mock("swr", () => ({
  __esModule: true,
  default: (key: unknown) => {
    if (key == null) return { data: undefined, error: null, isLoading: false };
    const tag = Array.isArray(key) ? key[0] : key;
    if (tag === "futures-market") {
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      return { data: ACTIVE_MARKET as any, error: null, isLoading: false, mutate: () => {} };
    }
    return { data: undefined, error: null, isLoading: false, mutate: () => {} };
  },
}));

jest.mock("@/hooks", () => ({
  usePageTracking: () => {},
  useScrollDepth: () => {},
  useEngagementTime: () => {},
  usePinnedFutures: () => ({ isPinned: () => false, togglePin: () => {}, isMaxReached: false }),
}));

jest.mock("@/components/Analytics", () => ({
  useAnalyticsContext: () => ({ track: () => {} }),
}));

import FuturesDetailPage from "../app/futures/[id]/page";
import {
  NO_PRICED_OUTCOMES_NOTE,
  noPricedOutcomesNote,
} from "@/lib/futuresDetailDisplay";

/* ────────────────────────────── the harness ────────────────────────────── */

function render(market: unknown, id: string): string {
  ACTIVE_MARKET = market;
  return renderToStaticMarkup(<FuturesDetailPage params={{ id }} />);
}

const FOLD_MARKER = 'data-testid="futures-more-outcomes"';
const SORT_CONTROLS = 'data-testid="futures-sort-controls"';
const AS_OF = 'data-testid="market-as-of"';
const NOTE = 'data-testid="futures-no-priced-outcomes"';

/** What a reader sees without opening anything, and what the toggle reveals. */
function splitAtFold(html: string): { beforeFold: string; insideFold: string } {
  const at = html.indexOf(FOLD_MARKER);
  if (at === -1) return { beforeFold: html, insideFold: "" };
  return { beforeFold: html.slice(0, at), insideFold: html.slice(at) };
}

function outcome(
  id: number,
  name: string,
  probability: number | null,
  rank: number,
  lastUpdated: string,
) {
  return {
    id,
    name,
    probability,
    rank,
    opening_probability: null,
    probability_change_24h: null,
    american_odds: null,
    opening_american_odds: null,
    is_winner: false,
    resolution_source: null,
    last_updated: lastUpdated,
  };
}

/** 16 CPI buckets, every one withheld. The served order and names of 109681. */
const CPI_STAMP = "2026-02-27T21:45:16.485704+00:00";
const CPI_NAMES = [
  "Exactly 3.0%", "Exactly 2.9%", "Exactly 2.8%", "Exactly 2.7%",
  "Exactly 3.1%", "Exactly 3.2%", "Exactly 2.5%", "Exactly 2.6%",
  "Exactly 3.5%", "Exactly 3.4%", "Exactly 2.4%", "Exactly 2.0%",
  "Exactly 2.1%", "Exactly 2.2%", "Exactly 2.3%", "Exactly 3.3%",
];

function cpiAllWithheld() {
  return {
    id: 109681,
    name: "CPI year-over-year in Oct 2026?",
    status: "open",
    source: "kalshi",
    category: "economics",
    llm_sport_category: "economics",
    market_type: "threshold",
    mutually_exclusive: true,
    outcome_count: 16,
    prices_withheld: 16,
    openings_withheld: true,
    hook_withheld: true,
    bookmakers: ["kalshi"],
    resolution_date: "2026-11-10T00:00:00+00:00",
    updated_at: CPI_STAMP,
    outcomes: CPI_NAMES.map((name, i) => outcome(700 + i, name, null, i + 1, CPI_STAMP)),
  };
}

/**
 * #4568's UFC ladder: fourteen real prices and five numberless rows. The control
 * that separates "no row has a price" from "some row is withheld".
 */
function ufcPartial() {
  const priced: Array<[string, number]> = [
    ["Ciryl Gane", 0.655], ["Josh Hokit", 0.2], ["Alexander Volkov", 0.0415],
    ["Tom Aspinall", 0.0145], ["Sergei Pavlovich", 0.0095], ["Curtis Blaydes", 0.0005],
    ["Jailton Almeida", 0.0005], ["Tyrell Fortune", 0.0005], ["Waldo Cortes Acosta", 0.0005],
    ["Serghei Spivac", 0.0005], ["Derrick Lewis", 0.0005], ["Ante Delija", 0.0005],
    ["Marcin Tybura", 0.0005], ["Rizvan Kuniev", 0.0005],
  ];
  const numberless = ["Fighter E", "Fighter D", "Other", "Fighter F", "Fighter G"];
  return {
    id: 114175,
    name: "Who will be UFC Heavyweight champion at the end of 2026?",
    status: "open",
    source: "polymarket",
    category: "championship",
    llm_sport_category: "mma",
    market_type: "field",
    mutually_exclusive: true,
    outcome_count: 19,
    bookmakers: ["polymarket"],
    resolution_date: "2026-12-31T00:00:00+00:00",
    updated_at: CPI_STAMP,
    outcomes: [
      ...priced.map(([name, p], i) => outcome(900 + i, name, p, i + 1, CPI_STAMP)),
      ...numberless.map((name, i) => outcome(950 + i, name, null, 15 + i, CPI_STAMP)),
    ],
  };
}

/* ───────────────────────────────── the rule ───────────────────────────────── */

describe("noPricedOutcomesNote", () => {
  it("speaks only when the listed half is empty", () => {
    expect(noPricedOutcomesNote(0)).toBe(NO_PRICED_OUTCOMES_NOTE);
    expect(noPricedOutcomesNote(1)).toBeNull();
    expect(noPricedOutcomesNote(14)).toBeNull();
  });

  it("is keyed on the LISTED count, so a withheld-row count cannot drive it", () => {
    // 109681 lists 0 of 16; 114175 lists 14 of 19. Both have withheld rows, and
    // only one of them is this defect. The rule must disagree about them.
    expect(noPricedOutcomesNote(0)).not.toBeNull();
    expect(noPricedOutcomesNote(14)).toBeNull();
  });

  it("says the honest thing once and claims nothing about why", () => {
    // Not "no outcomes" — the rows exist, one tap below. Notice 34: no method
    // note, no count, no explanation of the emptiness.
    expect(NO_PRICED_OUTCOMES_NOTE).toBe("No current prices for this market.");
    expect(NO_PRICED_OUTCOMES_NOTE).not.toMatch(/withheld|book|stale|untraded/i);
  });
});

/* ──────────────────────── the page, on the specimen ──────────────────────── */

describe("/futures/109681 — all 16 legs withheld", () => {
  const html = () => render(cpiAllWithheld(), "109681");

  it("prints the honest line above the fold", () => {
    const { beforeFold } = splitAtFold(html());
    expect(beforeFold).toContain(NOTE);
    expect(beforeFold).toContain(NO_PRICED_OUTCOMES_NOTE);
  });

  it("draws no sort toolbar — there is nothing to order", () => {
    // 🪤 The testid is part of THIS ship, so `not.toContain(SORT_CONTROLS)` is
    // also satisfied by a tree that never had the testid — it was green on the
    // unfixed render for that reason, and on its own it proves nothing. The
    // chip LABEL predates the fix and is the assertion that can fail, and
    // "keeps its sort toolbar" below is what stops both from being vacuous.
    const { beforeFold } = splitAtFold(html());
    expect(beforeFold).not.toContain("Last move");
    expect(html()).not.toContain(SORT_CONTROLS);
  });

  it("draws no as-of — the date belonged to prices nobody can see", () => {
    // `marketAsOf` reads the leader's `last_updated`, and with every leg
    // withheld the leader IS a withheld leg. Feb 27 is ~7 months stale, so the
    // label is well past `asOfLabel`'s threshold and would print but for the gate.
    expect(html()).not.toContain(AS_OF);
    expect(html()).not.toContain("as of Feb 27");
  });

  it("KEEPS THE SECTION — the heading and the disclosure both still render", () => {
    // 🔴 The one way this ship could do harm. Every absence asserted above is
    // also satisfied by the card disappearing, so the presences are the check.
    const out = html();
    expect(out).toContain("All Outcomes");
    expect(out).toContain(FOLD_MARKER);
    expect(out).toContain("More outcomes (16)");
  });

  it("keeps all 16 rows, folded, and invents no price for any of them", () => {
    const { beforeFold, insideFold } = splitAtFold(html());
    for (const name of CPI_NAMES) {
      expect(insideFold).toContain(name);
      expect(beforeFold).not.toContain(name);
    }
    // withhold-never-rewrite: no `0.49`/`49%` midpoint may surface anywhere.
    expect(html()).not.toContain("49%");
    expect(html()).not.toContain("50%");
  });
});

/* ────────────────────────── the controls, unmoved ────────────────────────── */

describe("a market that lists prices is untouched", () => {
  const html = () => render(ufcPartial(), "114175");

  it("keeps its sort toolbar though five of its rows are numberless", () => {
    // The case the plausible-but-wrong predicate gets wrong.
    expect(html()).toContain(SORT_CONTROLS);
  });

  it("keeps its as-of", () => {
    expect(html()).toContain(AS_OF);
  });

  it("says nothing about prices being absent", () => {
    expect(html()).not.toContain(NOTE);
    expect(html()).not.toContain(NO_PRICED_OUTCOMES_NOTE);
  });

  it("still folds its five numberless rows behind the disclosure (#4568 intact)", () => {
    const { beforeFold, insideFold } = splitAtFold(html());
    expect(beforeFold).toContain("Ciryl Gane");
    for (const name of ["Fighter E", "Fighter D", "Other", "Fighter F", "Fighter G"]) {
      expect(insideFold).toContain(name);
      expect(beforeFold).not.toContain(name);
    }
  });
});
