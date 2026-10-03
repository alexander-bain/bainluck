/**
 * #10263 — A GAME-PROP CARD IN SEARCH SAYS WHICH GAME IT IS ABOUT.
 *
 * Production, `/search?q=dodgers` at 390px, 2026-10-02 18:5x PT. The Games list
 * held three Dodgers–Braves games (Oct 3 20:00Z, Oct 4, Oct 6) and the Markets
 * grid printed `Spread: Los Angeles Dodgers (-2.5)` with `Atlanta Braves 63%`
 * leading, `1st 5 Innings Spread: Los Angeles Dodgers (-1.5)` and
 * `Los Angeles Dodgers Team Total: O/U 4.5` — no opponent, no date, and a bare
 * `2` (the outcome count) in the corner.
 *
 * The specimens below are the served rows from `GET /api/events/search?q=dodgers`
 * at 2026-10-03 03:18Z (ids, names, outcome order and kickoff verbatim). The games
 * are that payload's `results` rows (15323083 is the Oct 3 game). Jest pins TZ=UTC
 * and every helper call passes `NOW`, so no assertion branches on the clock.
 */

import fs from "fs";
import path from "path";
import { renderToStaticMarkup } from "react-dom/server";
import FuturesCard from "../../components/FuturesCard";
import SearchFamilyCard from "../../components/SearchFamilyCard";
import type { FuturesMarket, FuturesOutcome } from "../../lib/types";
import {
  gamePropContextLine,
  gamePropMatchup,
  spreadSideLabels,
  type GamePropGameRef,
} from "../../lib/gamePropCardContext";

const NOW = Date.parse("2026-10-03T03:18:00Z");
const OCT3 = "2026-10-03T20:00:00+00:00";

const GAMES: GamePropGameRef[] = [
  { home_team: "Los Angeles Dodgers", away_team: "Atlanta Braves", commence_time: OCT3, sport: "baseball_mlb" },
  { home_team: "Los Angeles Dodgers", away_team: "Atlanta Braves", commence_time: "2026-10-04T20:00:00+00:00", sport: "baseball_mlb" },
  { home_team: "Atlanta Braves", away_team: "Los Angeles Dodgers", commence_time: "2026-10-06T23:00:00+00:00", sport: "baseball_mlb" },
];

function outcome(id: number, name: string, probability: number): FuturesOutcome {
  return {
    id, name, probability,
    american_odds: null, rank: null, rank_change_24h: null, probability_change_24h: null,
    movement: null, opening_probability: null, opening_american_odds: null,
    is_winner: false, last_updated: null,
  } as FuturesOutcome;
}

function market(id: number, name: string, outs: [string, number][], over: Partial<FuturesMarket> = {}): FuturesMarket {
  return {
    id, name, description: null, source: "polymarket", category: "game_prop",
    sport: "baseball_mlb", sport_name: "MLB", llm_sport_category: "baseball",
    market_tier: 5, external_id: null, mutually_exclusive: true, commence_time: null,
    resolution_date: OCT3, outcome_count: outs.length, created_at: null, updated_at: null,
    status: "open", event_commence_time: OCT3,
    top_outcomes: outs.map(([n, p], i) => outcome(id * 10 + i, n, p)),
    ...over,
  } as unknown as FuturesMarket;
}

const SPREAD = market(63803243, "Spread: Los Angeles Dodgers (-2.5)", [["Atlanta Braves", 0.625], ["Los Angeles Dodgers", 0.375]]);
const F5_SPREAD = market(63812908, "1st 5 Innings Spread: Los Angeles Dodgers (-1.5)", [["Atlanta Braves", 0.56], ["Los Angeles Dodgers", 0.44]]);
const TEAM_TOTAL = market(63803242, "Los Angeles Dodgers Team Total: O/U 4.5", [["Over", 0.52], ["Under", 0.48]]);
const TITLED = market(63798072, "Atlanta Braves vs. Los Angeles Dodgers: O/U 8.5", [["Under", 0.515], ["Over", 0.485]]);
const CHAMPION = market(114584, "MLB World Series Champion 2026",
  [["Los Angeles Dodgers", 0.305], ["Milwaukee Brewers", 0.1715], ["New York Yankees", 0.155]],
  { category: "championship", market_tier: 1, event_commence_time: undefined, outcome_count: 31 } as Partial<FuturesMarket>);

describe("gamePropContextLine — the three specimens name the Oct 3 game", () => {
  it.each([
    ["spread", SPREAD],
    ["1st-5 spread", F5_SPREAD],
    ["team total", TEAM_TOTAL],
  ])("%s → matchup from the same-instant game + its kickoff", (_, m) => {
    expect(gamePropContextLine(m, GAMES, NOW)).toBe("Braves @ Dodgers · Today 8:00 PM");
  });

  it("a title that already names both sides gets the date only", () => {
    expect(gamePropContextLine(TITLED, GAMES, NOW)).toBe("Today 8:00 PM");
  });

  it("without the page's games: a spread names its sides from its rows, a team total is dated only", () => {
    expect(gamePropContextLine(SPREAD, [], NOW)).toBe("Braves vs Dodgers · Today 8:00 PM");
    expect(gamePropContextLine(TEAM_TOTAL, [], NOW)).toBe("Today 8:00 PM");
  });

  it("an unlinked market (no kickoff served) gets no line at all", () => {
    expect(gamePropContextLine(CHAMPION, GAMES, NOW)).toBeNull();
  });

  it("a game already under way prints the matchup and no clock (same rule as the Games list)", () => {
    expect(gamePropContextLine(TEAM_TOTAL, GAMES, Date.parse("2026-10-03T21:00:00Z"))).toBe("Braves @ Dodgers");
  });
});

describe("gamePropMatchup — the join is by exact instant, never by day or name alone", () => {
  it("the Oct 6 prop takes the Oct 6 game (home/away swapped) — never the Oct 3 one", () => {
    const oct6 = { ...TEAM_TOTAL, event_commence_time: "2026-10-06T23:00:00+00:00" };
    expect(gamePropMatchup(oct6, GAMES)).toBe("Dodgers @ Braves");
  });

  it("a kickoff matching no game on the page borrows nothing", () => {
    const orphan = { ...TEAM_TOTAL, event_commence_time: "2026-10-05T20:00:00+00:00" };
    expect(gamePropMatchup(orphan, GAMES)).toBeNull();
  });

  it("a same-instant game that names neither of the prop's teams is not joined", () => {
    const other: GamePropGameRef[] = [{ home_team: "New York Yankees", away_team: "Boston Red Sox", commence_time: OCT3 }];
    expect(gamePropMatchup(TEAM_TOTAL, other)).toBeNull();
  });

  it("two same-instant games both naming the team is a guess, so it falls back to the rows", () => {
    const twice: GamePropGameRef[] = [GAMES[0], { ...GAMES[0], away_team: "San Diego Padres" }];
    expect(gamePropMatchup(TEAM_TOTAL, twice)).toBeNull();
    expect(gamePropMatchup(SPREAD, twice)).toBe("Braves vs Dodgers");
  });

  it("Yes/No and Over/Under rows are answers, not sides", () => {
    const yesNo = market(1, "Will the Dodgers score first?", [["Yes", 0.5], ["No", 0.5]]);
    expect(gamePropMatchup(yesNo, [])).toBeNull();
    expect(gamePropMatchup(TEAM_TOTAL, [])).toBeNull();
  });
});

describe("spreadSideLabels — each row carries its own line", () => {
  it("the issue's specimen: the leader reads as the +2.5 side, not a contradiction", () => {
    expect(spreadSideLabels(SPREAD.name, ["Atlanta Braves", "Los Angeles Dodgers"])).toEqual([
      "Atlanta Braves +2.5",
      "Los Angeles Dodgers -2.5",
    ]);
  });

  it("follows the served order (63798071 serves the named side first) and the period prefix", () => {
    expect(spreadSideLabels("Spread: Los Angeles Dodgers (-1.5)", ["Los Angeles Dodgers", "Atlanta Braves"])).toEqual([
      "Los Angeles Dodgers -1.5",
      "Atlanta Braves +1.5",
    ]);
    expect(spreadSideLabels(F5_SPREAD.name, ["Atlanta Braves", "Los Angeles Dodgers"])).toEqual([
      "Atlanta Braves +1.5",
      "Los Angeles Dodgers -1.5",
    ]);
  });

  it("mirrors a plus line", () => {
    expect(spreadSideLabels("1H Spread: Lakers (+3.5)", ["Lakers", "Celtics"])).toEqual(["Lakers +3.5", "Celtics -3.5"]);
  });

  it("leaves every other shape to the caller", () => {
    expect(spreadSideLabels(TEAM_TOTAL.name, ["Over", "Under"])).toBeNull();
    expect(spreadSideLabels(SPREAD.name, ["Yes", "No"])).toBeNull();
    expect(spreadSideLabels(SPREAD.name, ["Atlanta Braves", "San Diego Padres"])).toBeNull();
    expect(spreadSideLabels(SPREAD.name, ["Atlanta Braves", "Los Angeles Dodgers", "Draw"])).toBeNull();
    expect(spreadSideLabels("Spread -1.5", ["Kings", "Blue Jackets"])).toBeNull();
  });
});

describe("FuturesCard renders it", () => {
  // The card reads the real clock, so its specimen kicks off 17h from now.
  const soon = new Date(Date.now() + 17 * 3_600_000).toISOString();
  const games = GAMES.map((g, i) => (i === 0 ? { ...g, commence_time: soon } : g));
  const render = (m: FuturesMarket) => renderToStaticMarkup(<FuturesCard market={m} games={games} />);
  const contextOf = (html: string) => /data-game-prop-context="true">([^<]*)</.exec(html)?.[1] ?? null;
  const labels = (html: string) => [...html.matchAll(/data-outcome-label[^>]*>([^<]*)</g)].map((x) => x[1]);
  const cornerCount = (html: string) => /<span class="text-micro text-text-muted">(\d+)<\/span>/.exec(html)?.[1] ?? null;

  it("the spread card names the game, labels both sides, and drops the bare '2'", () => {
    const html = render({ ...SPREAD, event_commence_time: soon });
    expect(contextOf(html)).toMatch(/^Braves @ Dodgers · (Today|Tomorrow) \d{1,2}:\d{2}\s?[AP]M$/);
    expect(labels(html)).toEqual(["Atlanta Braves +2.5", "Los Angeles Dodgers -2.5"]);
    expect(cornerCount(html)).toBeNull();
  });

  it("the team-total card names the opponent it never carried", () => {
    expect(contextOf(render({ ...TEAM_TOTAL, event_commence_time: soon }))).toMatch(/^Braves @ Dodgers · /);
  });

  it("a championship card is unchanged: no context line, its count stays", () => {
    const html = render(CHAMPION);
    expect(contextOf(html)).toBeNull();
    expect(cornerCount(html)).toBe("31");
    expect(labels(html)).toEqual(["Los Angeles Dodgers", "Milwaukee Brewers", "New York Yankees"]);
  });

  it("Search hands the card its Games list (the join is inert without it)", () => {
    const page = fs.readFileSync(path.join(__dirname, "../../app/search/page.tsx"), "utf8");
    const card = /<FuturesCard[\s\S]*?\/>/.exec(page)?.[0] ?? "";
    expect(card).toContain("games={results.results}");
  });
});

describe("SearchFamilyCard — a spread row's leader carries its line too", () => {
  const family = (headline: FuturesMarket) => ({
    family_key: "entity:dodgers", label: "Dodgers", headline, members: [TITLED, TEAM_TOTAL], more_count: 0, member_count: 3,
  });
  const html = (headline: FuturesMarket) => renderToStaticMarkup(<SearchFamilyCard family={family(headline)} />);

  it("the -2.5 headline reads `Atlanta Braves +2.5`, never a bare `Atlanta Braves`", () => {
    const out = html(SPREAD);
    expect(out).toContain(">Atlanta Braves +2.5<");
    expect(out).not.toContain(">Atlanta Braves<");
  });

  it("a non-spread row keeps its plain leader", () => {
    expect(html(TITLED)).toContain(">Under<");
  });
});
