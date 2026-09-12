/**
 * #5686 — the futures outcome row called POINTS a PERCENT.
 *
 * `formatMovementPoints` returns the magnitude of a move in POINTS: a market
 * that went 37.8% -> 47.8% moved TEN POINTS, and "↑ 10.0%" reads as a tenth
 * more than it had — about 4.8 points. The literal beside the formatter said
 * percent on `components/futures/OutcomeRow.tsx:435`.
 *
 * Ninth surface of the points-vs-percent family, found by discover/044's class
 * scan (#5685) and routed here rather than fixed there, because standing notice
 * 41 names `OutcomeRow` for UX by name. The family so far: #4066 (Discover
 * pill), #5619 (eight backend sentences), #5608 (search chip), #5623 (tournament
 * card), #5652 (the coloured zero on the same row), #5666 (golf movers),
 * #5669 (team page, two sites), #5685 (FeedCard + CombinedFeedCard), this.
 *
 * TWO HALVES, because #5669 learned the hard way that a source scan alone
 * cannot tell a fixed page from a blank one: the scan below proves the `%` is
 * gone from the render path, and the behavioural test proves the row still
 * PRINTS its move, through the real page and the real fixture.
 */

import fs from "fs";
import path from "path";

import React from "react";
import { renderToStaticMarkup } from "react-dom/server";

import market109441 from "../fixtures/uxp230_futures_109441.json";

jest.mock("next/navigation", () => ({
  useSearchParams: () => new URLSearchParams(""),
  useRouter: () => ({ replace: () => {}, push: () => {} }),
}));

let ACTIVE_MARKET: unknown = market109441;

// KEYED, not blanket: the page issues several SWR calls and only one of them
// wants this fixture. Handing the market payload back for every key makes the
// history reader iterate a market object and throw — the render dies before the
// row exists, which is the shape `futuresBaselineRender` already solved.
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

// The whole module is REPLACED, not spread over `requireActual` — the real
// `@/hooks` reaches a hook that needs an `AuthProvider` above it, and an SSR
// render with no provider throws before this row is ever drawn. Same shape as
// `futuresBaselineRender.test.tsx`, which renders the same page.
jest.mock("@/hooks", () => ({
  usePageTracking: () => {},
  useScrollDepth: () => {},
  useEngagementTime: () => {},
  usePinnedFutures: () => ({
    isPinned: () => false,
    togglePin: () => {},
    isMaxReached: false,
  }),
}));

jest.mock("@/components/Analytics", () => ({
  useAnalyticsContext: () => ({ track: () => {} }),
}));

// eslint-disable-next-line @typescript-eslint/no-var-requires
const FuturesDetailPage = require("../../app/futures/[id]/page").default;

const ROW = path.join(process.cwd(), "components/futures/OutcomeRow.tsx");
const src = fs.readFileSync(ROW, "utf8");

/** Text of the element carrying a `data-testid`, tags removed by scan. */
function testIdText(html: string, id: string): string | null {
  const m = new RegExp(`data-testid="${id}"[^>]*>([\\s\\S]*?)</`).exec(html);
  if (!m) return null;
  let out = "";
  let inTag = false;
  for (const ch of m[1]) {
    if (ch === "<") inTag = true;
    else if (ch === ">") inTag = false;
    else if (!inTag) out += ch;
  }
  return out.trim();
}

function draw(): string {
  return renderToStaticMarkup(
    React.createElement(FuturesDetailPage, { params: { id: "109441" } }),
  );
}

describe("#5686 the outcome row prints its move in points", () => {
  it("the scan read the real component, so the assertions below are about something", () => {
    // Without this a moved or renamed file makes the rule vacuous — #5669's
    // reachability check, kept because this is the same class of guard.
    expect(src.length).toBeGreaterThan(2000);
    expect(src).toContain("formatMovementPoints");
    expect(src).toContain('data-testid="outcome-change"');
  });

  it("no movement site in this file puts a '%' against the points formatter", () => {
    // Structural, matching the RENDER rather than prose: the file's own comment
    // names the defect it fixed, and a guard that reddens on its incident notes
    // is a guard someone deletes. #5669's regex, on this file.
    const PCT_AGAINST_POINTS = /\{formatMovementPoints\([^)]*\)\}\s*%/g;
    expect(src.match(PCT_AGAINST_POINTS)).toBeNull();
  });

  it("…and it prints ' pts', so the rule above cannot pass by deleting the badge", () => {
    const printed = src.match(/\{formatMovementPoints\([^)]*\)\}\s*pts/g) ?? [];
    expect(printed).toHaveLength(1);
  });

  it("BEHAVIOURAL: the real page renders the move as points, sign intact", () => {
    // The half a source scan cannot do. `-71.5` is byte-identical to what this
    // row printed before — only the unit moved — which is what makes this a
    // relabel and not a change of arithmetic.
    const html = draw();
    const change = testIdText(html, "outcome-change");
    expect(change).toBe("-71.5 pts");
    expect(change).not.toContain("%");
  });

  it("the #5652 gate is still in front of it — no coloured zero comes back", () => {
    // This ship and #5652's repair touch the same three lines, and a coloured
    // zero would now read `+0.0 pts` — a NEW spelling that every absence arm
    // written against "0.0%" passes straight over (#5685 widened its own arms
    // for exactly this reason).
    //
    // 🔴 MEASURED VACUITY, and the reason this arm renders instead of reading
    // the source. Mutating `{printsMove ? (` to `{true ? (` in this file is
    // caught by NOTHING in the tree today: not by `colouredZeroMovement5652`,
    // which is the guard named for this gate, and not by the other 332 tests
    // matching /futures/. A `src.toContain("printsMove")` assertion does not
    // catch it either — the identifier is still declared above, so the scan
    // passes on the mutant. The behaviour has to be rendered.
    //
    // The specimen is hand-built on purpose: every change in the banked fixture
    // is a real move, so the fixture cannot express "nonzero yet rounds to
    // nothing". 0.00003 is 0.003 points — the open interval #5652 is about.
    //
    // And it zeroes exactly ONE row, not all of them, because the table has a
    // SECOND gate above this one: `showLastMove` in the page hides the whole
    // column when no row prints. An all-zero market therefore proves nothing
    // about the row-level gate — the column is already gone — and the test
    // would pass on the mutant. Zeroing one row of a table that still has
    // movers is the only shape that isolates it.
    const market = market109441 as {
      outcomes: { probability_change_24h: number | null }[];
    };
    const badges = (html: string) =>
      (html.match(/data-testid="outcome-change"/g) ?? []).length;

    // Positive control: the real fixture DOES draw badges, so a smaller count
    // below means the gate held, not that the table failed to render.
    const before = badges(draw());
    expect(before).toBeGreaterThan(0);

    ACTIVE_MARKET = {
      ...market,
      outcomes: market.outcomes.map((o, i) =>
        i === 0 ? { ...o, probability_change_24h: 0.00003 } : o,
      ),
    };
    try {
      const html = draw();
      expect(badges(html)).toBe(before - 1);
      expect(html).not.toContain("0.0 pts");
      expect(html).not.toContain("0.0%");
    } finally {
      ACTIVE_MARKET = market109441;
    }
  });
});
