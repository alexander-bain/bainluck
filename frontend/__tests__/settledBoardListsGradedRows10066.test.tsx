/**
 * #10066 — A SETTLED BOARD'S "FINAL RESULTS" HID ITS WINNER BEHIND A TOGGLE.
 *
 * Production specimen, read 2026-10-01 12:58Z from `api.bainluck.com/api/futures/60544002`
 * (Zbigniew Nocun vs Adam Staniczek, Kalshi): `status: resolved`, both legs
 * `probability: null`, 226341650 `is_winner: true` and 226341651 `is_winner: false`,
 * both `resolution_source: api_settlement`. At 390px the header read "Zbigniew Nocun ·
 * WON" while the table under it read
 *
 *     📊 Final Results
 *     No current prices for this market.
 *     ▸ More outcomes (2)
 *
 * — the graded rows (`Won · 100% · Settled`, `Lost · 0% · Settled`) existed, folded.
 * The fold's predicate was `probability == null`; the row prints its verdict without
 * reading `probability`, so the two rules disagreed exactly on a priceless graded leg.
 *
 * Two controls keep the predicate honest: an UNGRADED priceless leg on a resolved
 * board (no `resolution_source`) still folds — the fix keys on the verdict, not on
 * `status` — and an OPEN market's `is_winner: false` leg, which the row refuses to
 * call `Lost`, still folds.
 *
 * Assertions are positional around the `<details>` marker, #4568's reason: folded
 * markup is still in the HTML, so a bare `toContain` cannot tell folded from visible.
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
  partitionOutcomesByPrice,
} from "@/lib/futuresDetailDisplay";

function render(market: unknown, id: string): string {
  ACTIVE_MARKET = market;
  return renderToStaticMarkup(<FuturesDetailPage params={{ id }} />);
}

const FOLD_MARKER = 'data-testid="futures-more-outcomes"';
const VERDICT = 'data-testid="outcome-verdict"';

/** The table section a reader sees, from its heading to the fold (or the end). */
function visibleTable(html: string, heading: string): string {
  const from = html.indexOf(heading);
  expect(from).toBeGreaterThan(-1);
  const rest = html.slice(from);
  const at = rest.indexOf(FOLD_MARKER);
  return at === -1 ? rest : rest.slice(0, at);
}

function leg(
  id: number,
  name: string,
  isWinner: boolean | null,
  resolutionSource: string | null,
  rank: number,
) {
  return {
    id,
    name,
    probability: null,
    rank,
    opening_probability: null,
    probability_change_24h: null,
    american_odds: null,
    opening_american_odds: null,
    is_winner: isWinner,
    resolution_source: resolutionSource,
    last_updated: "2026-10-01T12:18:13+00:00",
  };
}

function board(status: string, legs: ReturnType<typeof leg>[]) {
  return {
    id: 60544002,
    name: "Zbigniew Nocun vs Adam Staniczek",
    status,
    source: "kalshi",
    category: "mma",
    llm_sport_category: "mma",
    market_type: null,
    mutually_exclusive: true,
    outcome_count: legs.length,
    prices_withheld: 0,
    bookmakers: ["kalshi"],
    resolution_date: "2026-09-27T00:00:00+00:00",
    updated_at: "2026-10-01T12:18:13+00:00",
    outcomes: legs,
  };
}

/** 60544002 as served. */
const specimen = () =>
  board("resolved", [
    leg(226341650, "Zbigniew Nocun", true, "api_settlement", 1),
    leg(226341651, "Adam Staniczek", false, "api_settlement", 2),
  ]);

describe("#10066 settled board lists its graded rows", () => {
  it("Final Results shows Won and Lost without opening anything", () => {
    const html = render(specimen(), "60544002");
    const table = visibleTable(html, "Final Results");
    expect(table).toContain("Zbigniew Nocun");
    expect(table).toContain("Adam Staniczek");
    expect(table.split(VERDICT).length - 1).toBe(2);
    expect(table).toContain(">Won<");
    expect(table).toContain(">Lost<");
    expect(table).toContain("100%");
  });

  it("prints no 'No current prices' and no fold on the specimen", () => {
    const html = render(specimen(), "60544002");
    expect(html).not.toContain(NO_PRICED_OUTCOMES_NOTE);
    expect(html).not.toContain(FOLD_MARKER);
  });

  it("the winner leads the table", () => {
    const table = visibleTable(render(specimen(), "60544002"), "Final Results");
    expect(table.indexOf("Zbigniew Nocun")).toBeLessThan(table.indexOf("Adam Staniczek"));
  });

  it("CONTROL: an ungraded priceless leg on a resolved board still folds", () => {
    const html = render(
      board("resolved", [
        leg(226341650, "Zbigniew Nocun", true, "api_settlement", 1),
        leg(226341651, "Adam Staniczek", false, null, 2),
      ]),
      "60544002",
    );
    const table = visibleTable(html, "Final Results");
    expect(table).toContain("Zbigniew Nocun");
    expect(table).not.toContain("Adam Staniczek");
    expect(html).toContain(FOLD_MARKER);
    expect(html.slice(html.indexOf(FOLD_MARKER))).toContain("Adam Staniczek");
  });

  it("CONTROL: an open market's is_winner=false leg is not called Lost and still folds", () => {
    const html = render(
      board("open", [
        leg(226341650, "Zbigniew Nocun", false, "api_settlement", 1),
        leg(226341651, "Adam Staniczek", false, "api_settlement", 2),
      ]),
      "60544002",
    );
    expect(html).toContain(NO_PRICED_OUTCOMES_NOTE);
    expect(html).toContain(FOLD_MARKER);
    expect(html).not.toContain(VERDICT);
  });
});

describe("partitionOutcomesByPrice isGraded", () => {
  const rows = [
    { id: 1, probability: null as number | null, graded: true },
    { id: 2, probability: null as number | null, graded: false },
    { id: 3, probability: 0.4 as number | null, graded: false },
  ];

  it("lists a priceless row the caller grades, folds the rest", () => {
    const { listed, folded } = partitionOutcomesByPrice(rows, (r) => r.graded);
    expect(listed.map((r) => r.id)).toEqual([1, 3]);
    expect(folded.map((r) => r.id)).toEqual([2]);
  });

  it("without the predicate behaves exactly as before", () => {
    const { listed, folded } = partitionOutcomesByPrice(rows);
    expect(listed.map((r) => r.id)).toEqual([3]);
    expect(folded.map((r) => r.id)).toEqual([1, 2]);
  });
});
