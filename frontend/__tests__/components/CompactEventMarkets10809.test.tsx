/** @jest-environment jsdom */
import React, { act } from "react";
import { createRoot } from "react-dom/client";
import MarketBrowser from "@/components/event/MarketBrowser";
import CompactPlayerProps from "@/components/event/CompactPlayerProps";
import MarketMapSection from "@/components/MarketMapSection";
import CompactMarketMap from "@/components/event/CompactMarketMap";
import SeasonComparison from "@/components/event/SeasonComparison";
import SpecialEventMarkets from "@/components/SpecialEventMarkets";
import PlayerPropsDashboard from "@/components/PlayerPropsDashboard";
import type { GameMarketsResponse } from "@/lib/api";
import type { PlayerData } from "@/lib/playerPropsGrouping";

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
function click(text: string) {
  const button = Array.from(host.querySelectorAll("button")).find(
    (b) => b.textContent === text,
  );
  expect(button).toBeDefined();
  act(() => button!.click());
}
function search(value: string) {
  const input = host.querySelector("input")!;
  act(() => {
    Object.getOwnPropertyDescriptor(
      HTMLInputElement.prototype,
      "value",
    )!.set!.call(input, value);
    input.dispatchEvent(new Event("input", { bubbles: true }));
  });
}

test("a thousand questions remain reachable without a thousand-row first paint", () => {
  const items = Array.from({ length: 1120 }, (_, i) => ({
    key: String(i),
    group: i < 1000 ? "Season totals" : "Awards",
    search: `Question ${i}`,
    content: <span>Question {i}</span>,
  }));
  render(<MarketBrowser items={items} label="Season markets" />);
  expect(host.textContent).toContain("12 of 1000");
  expect(host.textContent).not.toContain("Question 999");
  click("Show more");
  expect(host.textContent).toContain("24 of 1000");
  search("Question 1119");
  expect(host.textContent).toContain("Question 1119");
  click("Awards");
  expect(host.textContent).toContain("12 of 120");
  // A refreshed payload removing the selected family falls back to a real one.
  render(<MarketBrowser items={items.slice(0, 40)} label="Season markets" />);
  expect(host.textContent).toContain("Question 0");
  expect(host.textContent).toContain("12 of 40");
});

test.each([
  "Passing Yards",
  "Rebounds",
  "Strikeouts",
  "Shots",
  "Aces",
  "Takedowns",
])("%s uses served targets and no fabricated live progress", (type) => {
  const players: PlayerData[] = [
    {
      name: "Example Player",
      initials: "EP",
      team: "home",
      color: "red",
      stats: [
        {
          type,
          shape: "ladder",
          sources: 1,
          movement: null,
          rungs: [
            { threshold: 10, overProb: 0.7, sources: 1, movement: null },
            { threshold: 20, overProb: 0.4, sources: 1, movement: null },
          ],
        },
      ],
    },
  ];
  render(
    <CompactPlayerProps
      players={players}
      live
      settled={false}
      renderSettled={() => null}
    />,
  );
  expect(host.textContent).toContain("40%");
  expect(host.textContent).not.toContain("so far");
  click("10+");
  expect(host.textContent).toContain("70%");
});

test("finished props still withhold missing grades, including when a box score exists", () => {
  const data = {
    player_props: [
      {
        market_name: "Seattle Mariners vs Tampa Bay Rays - Player Props",
        outcome_name: "Cole Young: Home Runs O/U 0.5",
        threshold: 0.5,
        over_probability: 0.01,
        source: "polymarket",
        movement: null,
        actual: null,
        hit: null,
        is_winner: false,
        resolution_source: null,
      },
    ],
    other: [],
  } as unknown as GameMarketsResponse;
  render(
    <PlayerPropsDashboard
      compact
      data={data}
      eventStatus="completed"
      boxScore={{
        players: [
          { name: "Cole Young", team: "home", stats: { "Home Runs": 0 } },
        ],
      }}
    />,
  );
  expect(host.textContent).toContain("grading unavailable");
  expect(host.textContent).not.toMatch(/MISS|1%/);
});

test("game completion does not settle the season; unavailable prices remain blank", () => {
  render(
    <SeasonComparison
      homeName="Home"
      awayName="Away"
      home={[
        {
          label: "Win title",
          columnKey: "championship",
          prob: 0.32,
          change: null,
          resolved: false,
        },
      ]}
      away={[
        {
          label: "Win title",
          columnKey: "championship",
          prob: null,
          change: null,
          resolved: false,
        },
      ]}
    />,
  );
  expect(host.textContent).toContain("32%");
  expect(host.textContent).not.toMatch(/0%|clinched/);
});

test.each(["pre", "live", "done"] as const)(
  "%s map keeps all quoted lines reachable and labels final quotes honestly",
  (status) => {
    render(
      <CompactMarketMap
        variant="total"
        title="Points"
        subtitle="Quoted lines"
        headline=""
        rangeMin={0}
        rangeMax={60}
        density={[1, 2, 1]}
        accentRgb="0,0,0"
        axisLabels={{ left: "0", mid: "30", right: "60" }}
        markers={[]}
        status={status}
        bandDrawsShape
        ladder={Array.from({ length: 40 }, (_, i) => ({
          label: `Over ${i}`,
          probability: 80 - i,
          side: "mid" as const,
        }))}
      />,
    );
    expect(host.textContent).not.toContain("Over 0");
    click("All 40 lines");
    expect(host.textContent).toContain("Over 0");
    expect(host.textContent).toContain(
      status === "done" ? "Last quote" : "Chance",
    );
    if (status === "done") expect(host.querySelector("svg")).toBeNull();
  },
);

test("categorical questions keep the existing void refusal", () => {
  const data = {
    other: [
      {
        market_name: "Who wins Set 1?",
        outcome_name: "Player A",
        probability: 0.5,
        source: "polymarket",
        is_winner: false,
        resolution_source: "polymarket_api",
      },
      {
        market_name: "Who wins Set 1?",
        outcome_name: "Player B",
        probability: 0.5,
        source: "polymarket",
        is_winner: false,
        resolution_source: "polymarket_api",
      },
    ],
  } as unknown as GameMarketsResponse;
  render(
    <SpecialEventMarkets compact data={data} voided eventStatus="completed" />,
  );
  expect(host.textContent).toContain("Void");
  expect(host.textContent).not.toMatch(/50%|Lost|Won/);
});

test.each([
  ["americanfootball_nfl", "Points"],
  ["basketball_nba", "Points"],
  ["baseball_mlb", "Runs"],
  ["soccer_epl", "Goals"],
  ["tennis_atp", "Games"],
])("%s keeps sport vocabulary and phase-safe map inputs", (sportKey, unit) => {
  const data = {
    totals: [
      {
        threshold: 12.5,
        over_probability: 0.55,
        source: "kalshi",
        market_type: "game_total",
        market_name: `Total ${unit}`,
        outcome_name: "Over 12.5",
        movement: null,
      },
    ],
    spreads: [],
    period_markets: [],
    team_totals: [],
    player_props: [],
    other: [],
    home_score: 7,
    away_score: 6,
  } as unknown as GameMarketsResponse;
  for (const status of ["scheduled", "live", "completed"]) {
    render(
      <MarketMapSection
        compact
        gameMarkets={data}
        eventStatus={status}
        homeTeam="Home"
        awayTeam="Away"
        sportKey={sportKey}
      />,
    );
    expect(host.textContent?.toLowerCase()).toContain(unit.toLowerCase());
    expect(host.textContent).not.toContain("NaN");
    if (status === "completed")
      expect(host.textContent).not.toContain("Projection");
  }
});
