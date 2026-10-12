/** @jest-environment jsdom */
import React, { act } from "react";
import { createRoot } from "react-dom/client";
import GameLineBrowser from "@/components/event/GameLineBrowser";
import type { GameMarketsResponse } from "@/lib/api";

// #10590 — Root's reader FAIL, 2026-10-12 22:18Z. On /events/15323985 (Brewers
// 4, Padres 3) "San Diego Padres Team Total: O/U 4.5" read "Over — Last quote
// 0%" with no result, while /futures/64157612 correctly read "Under WON". The
// event payload already carried the answer: the row is on the OVER axis
// (#6239), over_probability 0.0, is_winner false, resolution_source
// clob_authoritative = "Over lost". The rows below are that served shape.

(
  globalThis as typeof globalThis & { IS_REACT_ACT_ENVIRONMENT: boolean }
).IS_REACT_ACT_ENVIRONMENT = true;

let host: HTMLDivElement;
let root: ReturnType<typeof createRoot>;
beforeEach(() => {
  host = document.createElement("div");
  document.body.append(host);
  root = createRoot(host);
});
afterEach(() => {
  act(() => root.unmount());
  host.remove();
});
function render(node: React.ReactNode) {
  act(() => root.render(node));
}

const total = (
  market_name: string,
  outcome_name: string,
  threshold: number,
  over_probability: number,
  is_winner: boolean | null,
  resolution_source: string | null,
  source = "polymarket",
) => ({
  market_name,
  outcome_name,
  threshold,
  over_probability,
  is_winner,
  resolution_source,
  source,
  market_type: "team_total",
  movement: null,
  period: null,
  observed_at: "2026-10-04T19:09:06Z",
});

const data = {
  team_totals: [
    // THE SPECIMEN (market 64157612): Padres scored 3, so Under 4.5 won.
    total("San Diego Padres Team Total: O/U 4.5", "Under", 4.5, 0.0, false, "clob_authoritative"),
    total("San Diego Padres Team Total: O/U 4.5", "Over", 4.5, 0.0, false, "clob_authoritative"),
    // Brewers scored 4: Over 2.5 won (both legs carry the Over's verdict).
    total("Milwaukee Brewers Team Total: O/U 2.5", "Over", 2.5, 1.0, true, "clob_authoritative"),
    total("Milwaukee Brewers Team Total: O/U 2.5", "Under", 2.5, 1.0, true, "clob_authoritative"),
    // A Kalshi rung named for its side.
    total("San Diego vs Milwaukee: Team Total", "San Diego over 1.5 runs scored", 1.5, 1.0, true, "api_settlement", "kalshi"),
    // An Under with no Over twin: the served verdict is the OVER's, so the
    // Under leg reads the opposite.
    total("Milwaukee Brewers Team Total: O/U 5.5", "Under", 5.5, 0.0, false, "clob_authoritative"),
    // No grader: the leftover quote stays a quote.
    total("Milwaukee Brewers Team Total: O/U 6.5", "Over", 6.5, 0.02, null, null),
    // A retraction is never a verdict (#1852).
    total("Milwaukee Brewers Team Total: O/U 7.5", "Over", 7.5, 0.0, false, "ungradeable_result"),
  ],
  period_markets: [
    // A row with its own probability is graded on its own leg.
    {
      market_name: "1st 5 Innings Spread: San Diego Padres (-1.5)",
      outcome_name: "Milwaukee Brewers",
      threshold: -1.5,
      probability: 1.0,
      source: "polymarket",
      market_type: "half_spread",
      is_winner: true,
      resolution_source: "api_settlement",
    },
    {
      market_name: "1st 5 Innings Spread: San Diego Padres (-1.5)",
      outcome_name: "San Diego Padres",
      threshold: -1.5,
      probability: null,
      source: "polymarket",
      market_type: "half_spread",
      is_winner: false,
      resolution_source: "api_settlement",
    },
  ],
} as unknown as GameMarketsResponse;

const lines = () =>
  Array.from(host.querySelectorAll("div.py-3")).map(
    (r) => `${r.children[0].textContent} · ${r.children[1].textContent}`,
  );

test("a finished game's team total prints its result, not 'Last quote 0%'", () => {
  render(<GameLineBrowser data={data} status="completed" />);
  expect(lines()).toEqual([
    "San Diego Padres Team Total: O/U 4.5 · OverLost",
    "Milwaukee Brewers Team Total: O/U 2.5 · OverWon",
    "San Diego vs Milwaukee: Team Total · San Diego over 1.5 runs scoredWon",
    "Milwaukee Brewers Team Total: O/U 5.5 · UnderWon",
    "Milwaukee Brewers Team Total: O/U 6.5 · OverLast quote 2%",
    "Milwaukee Brewers Team Total: O/U 7.5 · OverLast quote 0%",
  ]);
  // A result replaces the quote; it never sits beside it.
  const padres = host.querySelectorAll("div.py-3")[0];
  expect(padres.querySelector("strong")).toBeNull();
  expect(padres.querySelector('[data-testid="outcome-verdict"]')?.textContent).toBe("Lost");
});

test("a period row with its own probability is graded on its own leg", () => {
  // Periods is the second group; render it alone so it is the one shown.
  const periods = { ...data, team_totals: [] } as unknown as GameMarketsResponse;
  render(<GameLineBrowser data={periods} status="completed" />);
  expect(lines()).toEqual([
    "1st 5 Innings Spread: San Diego Padres (-1.5) · Milwaukee BrewersWon",
    "1st 5 Innings Spread: San Diego Padres (-1.5) · San Diego PadresLost",
  ]);
});

test("during play only an authoritative win is printed; a loss waits for the final", () => {
  render(<GameLineBrowser data={data} status="in_progress" />);
  const verdicts = Array.from(
    host.querySelectorAll('[data-testid="outcome-verdict"]'),
  ).map((v) => v.closest("div.py-3")?.children[0].textContent + " " + v.textContent);
  expect(verdicts).toEqual([
    "Milwaukee Brewers Team Total: O/U 2.5 Won",
    "San Diego vs Milwaukee: Team Total Won",
  ]);
  expect(host.textContent).not.toContain("Lost");
});

test("a payload without the grade fields keeps today's quotes", () => {
  const legacy = {
    team_totals: data.team_totals.map((row) => {
      const { is_winner: _w, resolution_source: _s, ...rest } = row as typeof row & {
        is_winner?: boolean | null;
        resolution_source?: string | null;
      };
      return rest;
    }),
    period_markets: [],
  } as unknown as GameMarketsResponse;
  render(<GameLineBrowser data={legacy} status="completed" />);
  expect(host.querySelectorAll('[data-testid="outcome-verdict"]')).toHaveLength(0);
  expect(lines()[0]).toBe("San Diego Padres Team Total: O/U 4.5 · OverLast quote 0%");
});
