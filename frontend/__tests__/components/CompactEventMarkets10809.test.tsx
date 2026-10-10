/** @jest-environment jsdom */
import React, { act } from "react";
import { createRoot } from "react-dom/client";
import GameLineBrowser from "@/components/event/GameLineBrowser";
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
  "Saves",
  "Birdies",
  "Wickets",
  "Laps Led",
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
  ["icehockey_nhl", "Goals"],
  ["basketball_wnba", "Points"],
  ["americanfootball_ncaaf", "Points"],
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

// #10823: the server now prices each team-total line on its own. Rows below are
// the f7e7cf8b served shape (Eagles @ Jaguars 14639175, Florida live, 10/10):
// each question prints its own quote, an Under row never borrows the Over
// price (beside its Over twin it is not listed at all), and during play a
// pregame-stamped price prints nothing.
test("team totals print each line's own quote; Under borrows nothing; live drops stale prices", () => {
  const NOW = Date.parse("2026-10-10T19:50:00Z");
  const now = jest.spyOn(Date, "now").mockReturnValue(NOW);
  const total = (
    market_name: string,
    outcome_name: string,
    threshold: number,
    over_probability: number,
    source: string,
    observed_at: string,
  ) => ({
    market_name,
    outcome_name,
    threshold,
    over_probability,
    source,
    observed_at,
    market_type: "team_total",
    movement: null,
    period: null,
  });
  const data = {
    team_totals: [
      total("Eagles 1H Team Total: O/U 6.5", "Over", 6.5, 0.555, "polymarket", "2026-10-10T19:44:00Z"),
      total("Eagles 1H Team Total: O/U 6.5", "Under", 6.5, 0.555, "polymarket", "2026-10-10T19:44:00Z"),
      total("Eagles Team Total: O/U 10.5", "Over", 10.5, 0.73, "polymarket", "2026-10-10T19:44:00Z"),
      total("PHI Eagles vs JAC Jaguars: Team Total", "PHI Eagles over 7.5 points", 7.5, 0.865, "kalshi", "2026-10-10T19:40:00Z"),
      total("PHI Eagles vs JAC Jaguars: Team Total", "JAC Jaguars over 7.5 points", 7.5, 0.975, "kalshi", "2026-10-10T19:40:00Z"),
      // Pregame-stamped (16:39Z) — 3h old once the game is under way.
      total("Florida Team Total: O/U 26.5", "Over", 26.5, 0.82, "polymarket", "2026-10-10T16:39:00Z"),
      // An Under with no Over twin stays reachable, without a number.
      total("Jaguars Team Total: O/U 20.5", "Under", 20.5, 0.4, "polymarket", "2026-10-10T19:44:00Z"),
    ],
    period_markets: [],
  } as unknown as GameMarketsResponse;
  try {
    const quotes = () => Array.from(host.querySelectorAll("strong")).map((s) => s.textContent);
    const lines = () =>
      Array.from(host.querySelectorAll("div.py-3")).map(
        (r) => `${r.children[0].textContent} · ${r.children[1].textContent}`,
      );
    render(<GameLineBrowser data={data} status="scheduled" />);
    expect(host.textContent).not.toContain("Unavailable");
    expect(lines()).toEqual([
      "Eagles 1H Team Total: O/U 6.5 · Over56%",
      "Eagles Team Total: O/U 10.5 · Over73%",
      "PHI Eagles vs JAC Jaguars: Team Total · PHI Eagles over 7.5 points87%",
      "PHI Eagles vs JAC Jaguars: Team Total · JAC Jaguars over 7.5 points98%",
      "Florida Team Total: O/U 26.5 · Over82%",
      "Jaguars Team Total: O/U 20.5 · Under",
    ]);
    expect(host.querySelectorAll('[data-quote="stale"]')).toHaveLength(0);

    render(<GameLineBrowser data={data} status="in_progress" />);
    expect(quotes()).toEqual(["56%", "73%", "87%", "98%"]);
    const stale = host.querySelectorAll('[data-quote="stale"]');
    expect(stale).toHaveLength(1);
    expect(stale[0].textContent).toContain("Florida Team Total: O/U 26.5");
    expect(stale[0].querySelector("strong")).toBeNull();

    render(<GameLineBrowser data={data} status="completed" />);
    expect(quotes()).toEqual([
      "Last quote 56%", "Last quote 73%", "Last quote 87%", "Last quote 98%", "Last quote 82%",
    ]);
  } finally {
    now.mockRestore();
  }
});

// Categorical markets do not need a points model or an NFL-specific family.
// Exercise the actual question renderer with large fields and settled legs.
test.each([
  ["Golf", "Top 20 finish"],
  ["Motorsport", "Podium finish"],
  ["MMA", "Method of victory"],
  ["Boxing", "Winning round"],
  ["Cricket", "Top wicket taker"],
  ["Rugby", "First try scorer"],
  ["Hockey", "First goal scorer"],
  ["Volleyball", "Exact set score"],
])("%s categorical fields keep every outcome reachable in every phase", (sport, market) => {
  const rows = Array.from({ length: 30 }, (_, i) => ({
    market_name: `${sport}: ${market}`,
    outcome_name: `Competitor ${String(i).padStart(2, "0")}`,
    probability: 0.03,
    source: "polymarket",
  }));
  for (const status of ["scheduled", "live", "completed"]) {
    const data = { other: rows.map((row, i) => ({ ...row,
      ...(status === "completed" ? { is_winner: i === 29, resolution_source: "polymarket_api" } : {}),
    })) } as unknown as GameMarketsResponse;
    render(<SpecialEventMarkets compact data={data} eventStatus={status} />);
    search("Competitor 29");
    expect(host.textContent).toContain("Competitor 29");
    const disclosure = host.querySelector("details");
    expect(disclosure).not.toBeNull();
    act(() => disclosure!.querySelector("summary")!.click());
    expect(disclosure!.open).toBe(true);
    if (status === "completed") {
      expect(host.textContent).toContain("Won");
      expect(host.textContent).not.toContain("3%");
    }
    // Clear the disclosure and browser state before testing the next phase.
    render(<div />);
  }
});
