/** @jest-environment jsdom */
import React, { act } from "react";
import { createRoot } from "react-dom/client";
import EventCard183A, {
  alignPregameReasonTeamNames,
  buildUnifiedCardFromEvent,
  extractPregameProjectedPair,
  formatGameCardProjection,
  formatLivePregameSummary,
  formatLiveTenthsPair,
  formatSingleLiveTenths,
  resolveDiscoverChartDomain,
  sharedGameCardTeamFontClass,
  type UnifiedGameCardData,
} from "@/components/EventCard183A";
import { PIN_PATH } from "@/components/PinButton";
import { cleanDiscoverGameReason, isWebGameCard183AEnabled } from "@/lib/gameCard183AFlag";
import type { Event } from "@/lib/types";

(
  globalThis as typeof globalThis & { IS_REACT_ACT_ENVIRONMENT: boolean }
).IS_REACT_ACT_ENVIRONMENT = true;

const BASE_CARD: UnifiedGameCardData = {
  id: 14639206,
  sport: "americanfootball_nfl",
  sport_name: "NFL",
  home_team: "Detroit Lions",
  away_team: "New England Patriots",
  commence_time: "2026-11-15T14:30:00Z",
  status: "scheduled",
  home_score: null,
  away_score: null,
  home_color: "#0076b6",
  away_color: "#c60c30",
  home_prob: 0.575,
  away_prob: 0.425,
  pregame_home_pct: 58,
  pregame_away_pct: 42,
  pregame_projected_home: "27",
  pregame_projected_away: "24",
  projected_home: 25,
  projected_away: 20,
  live_clock_label: null,
  reason_line: "A win locks Detroit into the NFC #1 seed entering Thanksgiving.",
};

describe("EventCard183A unified web game card (#12616, Rulings 199, 200-B, 201)", () => {
  const origEnv = process.env.NEXT_PUBLIC_GAME_CARD_183A;
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
    process.env.NEXT_PUBLIC_GAME_CARD_183A = origEnv;
  });

  function render(node: React.ReactNode) {
    act(() => root.render(node));
  }

  function byTestId(id: string): Element | null {
    return host.querySelector(`[data-testid="${id}"]`);
  }

  it("stays strictly switched off by default unless NEXT_PUBLIC_GAME_CARD_183A === 'true'", () => {
    delete process.env.NEXT_PUBLIC_GAME_CARD_183A;
    expect(isWebGameCard183AEnabled()).toBe(false);
    process.env.NEXT_PUBLIC_GAME_CARD_183A = "false";
    expect(isWebGameCard183AEnabled()).toBe(false);
    process.env.NEXT_PUBLIC_GAME_CARD_183A = "true";
    expect(isWebGameCard183AEnabled()).toBe(true);
  });

  it("formats live streaming tenths identically to iOS CompactGameCard12616", () => {
    expect(formatSingleLiveTenths(0.004)).toBe("<1%");
    expect(formatSingleLiveTenths(0.996)).toBe(">99%");
    expect(formatLiveTenthsPair(0.3424, 0.6576, false)).toEqual({
      away: "34.2%",
      home: "65.8%",
    });
    expect(formatLiveTenthsPair(0.412, 0.489, false)).toEqual({
      away: "41.2%",
      home: "48.9%",
    });
    expect(formatLiveTenthsPair(0.4, 0.6, true)).toEqual({
      away: null,
      home: "60.0%",
    });
  });

  it("formats Ruling 200-B single-line pregame summary with favourite first and omits missing halves or full line", () => {
    // Home favourite: Lions 58% · projected 27–24
    expect(
      formatLivePregameSummary(
        {
          sport: "americanfootball_nfl",
          pregame_home_pct: 58,
          pregame_away_pct: 42,
          pregame_projected_home: "27",
          pregame_projected_away: "24",
        },
        "Patriots",
        "Lions",
      ),
    ).toEqual({
      body: "Lions 58% · projected 27–24",
      fullText: "Pregame  Lions 58% · projected 27–24",
    });

    // Away favourite: Chiefs 63% · projected 28–21
    expect(
      formatLivePregameSummary(
        {
          sport: "americanfootball_nfl",
          pregame_home_pct: 37,
          pregame_away_pct: 63,
          pregame_projected_home: "21",
          pregame_projected_away: "28",
        },
        "Chiefs",
        "Raiders",
      ),
    ).toEqual({
      body: "Chiefs 63% · projected 28–21",
      fullText: "Pregame  Chiefs 63% · projected 28–21",
    });

    // Missing pregame projected score: leaves out that half
    expect(
      formatLivePregameSummary(
        {
          sport: "americanfootball_nfl",
          pregame_home_pct: 58,
          pregame_away_pct: 42,
          pregame_projected_home: null,
          pregame_projected_away: null,
        },
        "Patriots",
        "Lions",
      ),
    ).toEqual({
      body: "Lions 58%",
      fullText: "Pregame  Lions 58%",
    });

    // Missing pregame win chance: leaves out that half
    expect(
      formatLivePregameSummary(
        {
          sport: "americanfootball_nfl",
          pregame_home_pct: null,
          pregame_away_pct: null,
          pregame_projected_home: "27",
          pregame_projected_away: "24",
        },
        "Patriots",
        "Lions",
      ),
    ).toEqual({
      body: "projected 27–24",
      fullText: "Pregame  projected 27–24",
    });

    // Both missing: returns null so line is omitted completely
    expect(
      formatLivePregameSummary(
        {
          sport: "americanfootball_nfl",
          pregame_home_pct: null,
          pregame_away_pct: null,
          pregame_projected_home: null,
          pregame_projected_away: null,
        },
        "Patriots",
        "Lions",
      ),
    ).toBeNull();
  });

  it("never passes opening_odds off as Pregame when prematch_odds is absent, and extracts validated pregame_projection", () => {
    const fakeEvent = {
      id: 99,
      sport: "americanfootball_nfl",
      sport_name: "NFL",
      home_team: "Detroit Lions",
      away_team: "New England Patriots",
      commence_time: "2026-11-15T18:00:00Z",
      status: "live",
      home_score: 21,
      away_score: 17,
      opening_odds: {
        home_probability: 0.42,
        away_probability: 0.58,
      },
      prematch_odds: null,
      pregame_projection: {
        kind: "last_before_scheduled_start",
        boundary: "scheduled_start",
        boundary_at: "2026-11-15T18:00:00Z",
        source: "sportsbooks",
        basis: "consensus_spread_total",
        unit: "points",
        projected_home_score: 27.1,
        projected_away_score: 23.8,
        bookmaker_count: 14,
        earliest_captured_at: "2026-11-15T17:40:00Z",
        latest_captured_at: "2026-11-15T17:58:00Z",
      },
    } as unknown as Event;

    const unified = buildUnifiedCardFromEvent(fakeEvent);
    expect(unified.pregame_home_pct).toBeNull();
    expect(unified.pregame_away_pct).toBeNull();
    expect(unified.pregame_projected_home).toBe("27");
    expect(unified.pregame_projected_away).toBe("24");

    expect(
      extractPregameProjectedPair(
        {
          ...fakeEvent.pregame_projection!,
          latest_captured_at: "2026-11-15T18:02:00Z", // captured after kickoff — must reject
        },
        "americanfootball_nfl",
      ),
    ).toBeNull();
  });

  it("renders pregame compact card with Proj. + Chance columns, shared bookmark PIN_PATH, segmented bar, and NO Pregame column or line", () => {
    const onPin = jest.fn();
    render(
      <EventCard183A
        card={BASE_CARD}
        surface="discover"
        isPinned={false}
        onPinToggle={onPin}
      />,
    );

    expect(byTestId("col-header-proj")?.textContent).toBe("Proj.");
    expect(byTestId("col-header-now")?.textContent).toBe("Chance");
    expect(byTestId("col-header-pregame")).toBeNull();
    expect(byTestId("live-pregame-summary-line")).toBeNull();
    expect(byTestId("discover-191a-chart-panel")).toBeNull();
    expect(byTestId("compact-probability-bar")).not.toBeNull();
    // Before the game: no pregame tick on the bar
    expect(byTestId("pregame-bar-tick")).toBeNull();
    const pinWrap = byTestId("bookmark-pin-icon");
    expect(pinWrap).not.toBeNull();
    expect(pinWrap?.querySelector("path")?.getAttribute("d")).toBe(PIN_PATH);
    expect(byTestId("ekg-feed-pulse")).toBeNull();
    // Before the game: sentence stays and names the team as its row does ("Lions", not "Detroit")
    expect(byTestId("discover-game-reason-line")?.textContent).toContain(
      "A win locks Lions into the NFC #1 seed entering Thanksgiving.",
    );

    const saveBtn = host.querySelector('button[aria-label="Save game"]') as HTMLButtonElement | null;
    expect(saveBtn).not.toBeNull();
    act(() => saveBtn!.click());
    expect(onPin).toHaveBeenCalledTimes(1);
  });

  it("renders live Discover card per Rulings 199, 200-B & 201: Score · Proj. · Now, no Pregame column, Now largest in team colour, single grey pregame line, and fitted chart scale", () => {
    render(
      <EventCard183A
        card={{
          ...BASE_CARD,
          status: "live",
          away_score: 17,
          home_score: 21,
          away_prob: 0.338,
          home_prob: 0.662,
          projected_away: 23.5,
          projected_home: 28.0,
          live_clock_label: "Q3 · 8:14",
          reason_line: "Detroit jumped 18 points in 4 minutes.",
          chart_points: [
            { t: 0, p: 0.58 },
            { t: 0.5, p: 0.48 },
            { t: 1, p: 0.662 },
          ],
        }}
        surface="discover"
      />,
    );

    expect(byTestId("col-header-score")?.textContent).toBe("Score");
    expect(byTestId("col-header-proj")?.textContent).toBe("Proj.");
    expect(byTestId("col-header-now")?.textContent).toBe("Now");
    expect(byTestId("col-header-pregame")).toBeNull();
    expect(byTestId("live-projected-once")).toBeNull();
    expect(byTestId("ekg-feed-pulse")).not.toBeNull();
    expect(byTestId("compact-probability-bar")).not.toBeNull();
    // Tick marks away team's pregame chance (42% for Patriots), not 50%
    const barTick = byTestId("pregame-bar-tick") as HTMLElement | null;
    expect(barTick).not.toBeNull();
    expect(barTick?.style.left).toBe("42%");
    // Whole-number football projections: 24 and 28, never 23.5 or 28.0
    expect(byTestId("proj-score-away")?.textContent).toBe("24");
    expect(byTestId("proj-score-home")?.textContent).toBe("28");
    // Direction 199: during a game, print no sentence repeating the card
    expect(byTestId("discover-game-reason-line")).toBeNull();

    const awayNow = byTestId("primary-chance-away") as HTMLElement | null;
    const homeNow = byTestId("primary-chance-home") as HTMLElement | null;
    expect(awayNow?.textContent).toBe("33.8%");
    expect(homeNow?.textContent).toBe("66.2%");
    expect(awayNow?.className).toContain("text-[22px]");
    expect(awayNow?.className).toContain("font-extrabold");
    expect(awayNow?.style.color).not.toBe("");
    expect(homeNow?.style.color).not.toBe("");

    // Ruling 204-C: cards print Score · Proj. · Now with NO grey pregame line; the bar tick carries the pregame chance
    expect(byTestId("live-pregame-summary-line")).toBeNull();
    expect(host.textContent).not.toContain("Pregame");

    const chartPanel = byTestId("discover-191a-chart-panel");
    expect(chartPanel).not.toBeNull();
    // Ruling 201: 2-team NFL game fits movement (48%..66.2% -> 40-80), NOT 0-100
    expect(chartPanel?.getAttribute("data-chart-domain")).toBe("40-80");

    expect(host.textContent).not.toMatch(/opening/i);
    expect(host.textContent).not.toMatch(/venues/i);
  });

  it("renders settled game per Ruling 200-B: Pregame · Final columns, NO bar, winner ticked, and never 'Settled'", () => {
    render(
      <EventCard183A
        card={{
          ...BASE_CARD,
          status: "completed",
          completed_at: "2026-11-15T18:05:00Z",
          away_score: 20,
          home_score: 28,
          away_prob: 0,
          home_prob: 1,
          projected_away: null,
          projected_home: null,
          reason_line: "Detroit moves a full game clear atop the NFC North.",
        }}
        surface="discover"
      />,
    );

    expect(byTestId("col-header-score")).toBeNull();
    expect(byTestId("col-header-proj")).toBeNull();
    expect(byTestId("col-header-pregame")?.textContent).toBe("Pregame");
    expect(byTestId("col-header-now")?.textContent).toBe("Final");
    expect(byTestId("compact-probability-bar")).toBeNull();
    expect(byTestId("live-pregame-summary-line")).toBeNull();
    expect(byTestId("ekg-feed-pulse")).toBeNull();
    expect(byTestId("winner-tick-home")?.textContent).toBe("✓");
    expect(byTestId("winner-tick-away")).toBeNull();
    expect(host.textContent).toContain("20");
    expect(host.textContent).toContain("28");
    expect(host.textContent).not.toContain("Won ✓");
    expect(byTestId("discover-191a-chart-panel")).not.toBeNull();
    // Direction 199: after a game, print no sentence repeating the card
    expect(byTestId("discover-game-reason-line")).toBeNull();
    expect(host.textContent).not.toContain("65%");
    expect(host.textContent).not.toMatch(/Settled/i);
  });

  it("formats football/basketball projections as whole numbers and soccer/baseball/hockey to one decimal, omits live bar tick when unheld, and aligns pregame team names", () => {
    expect(formatGameCardProjection(23.5, "americanfootball_nfl")).toBe("24");
    expect(formatGameCardProjection("28.0", "americanfootball_ncaaf")).toBe("28");
    expect(formatGameCardProjection(114.7, "basketball_nba")).toBe("115");
    expect(formatGameCardProjection(1.6, "soccer_epl")).toBe("1.6");
    expect(formatGameCardProjection(4.5, "baseball_mlb")).toBe("4.5");
    expect(formatGameCardProjection(3.0, "icehockey_nhl")).toBe("3.0");

    expect(
      alignPregameReasonTeamNames(
        "Detroit is up 6 points from 52% earlier this week.",
        "Detroit Lions",
        "Lions",
        "New England Patriots",
        "Patriots",
      ),
    ).toBe("Lions are up 6 points from 52% earlier this week.");

    render(
      <EventCard183A
        card={{
          ...BASE_CARD,
          status: "live",
          away_score: 10,
          home_score: 14,
          pregame_away_pct: null,
          pregame_home_pct: null,
        }}
        surface="standard"
      />,
    );
    expect(byTestId("pregame-bar-tick")).toBeNull();
  });

  it("keeps 0-100 chart scale on soccer (Ruling 201) while fitting 2-way games with exact [top, 50%, bottom] labels", () => {
    expect(
      resolveDiscoverChartDomain(
        [
          { t: 0, p: 0.58 },
          { t: 1, p: 0.66 },
        ],
        true,
      ),
    ).toEqual({
      min: 0.4,
      max: 0.8,
      ticks: [0.8, 0.5, 0.4],
    });
    expect(
      resolveDiscoverChartDomain(
        [
          { t: 0, p: 0.44 },
          { t: 1, p: 1.0 },
        ],
        true,
      ),
    ).toEqual({
      min: 0.3,
      max: 1.0,
      ticks: [1.0, 0.5, 0.3],
    });
    expect(
      resolveDiscoverChartDomain(
        [
          { t: 0, p: 0.49 },
          { t: 1, p: 0.55 },
        ],
        false,
      ),
    ).toEqual({
      min: 0,
      max: 1,
      ticks: [1, 0.75, 0.5, 0.25, 0],
    });
  });

  it("shrinks both team names together on long college school names before cutting", () => {
    expect(sharedGameCardTeamFontClass("Lions", "Patriots", true)).toBe("text-[15px]");
    expect(sharedGameCardTeamFontClass("Washington", "Michigan State", true)).toBe(
      "text-[13.5px]",
    );
    expect(sharedGameCardTeamFontClass("Alabama", "Mississippi State", true)).toBe(
      "text-[12.5px]",
    );
  });

  it("renders 187-A middle Draw row aligned across before, during, and level final on 3-way soccer", () => {
    expect(cleanDiscoverGameReason("Trending matchup", "Arsenal", "Chelsea")).toBeNull();
    expect(cleanDiscoverGameReason("Chelsea at Arsenal", "Arsenal", "Chelsea")).toBeNull();

    render(
      <EventCard183A
        card={{
          ...BASE_CARD,
          sport: "soccer_epl",
          sport_name: "Premier League",
          away_team: "Chelsea",
          home_team: "Arsenal",
          away_prob: 0.24,
          draw_prob: 0.27,
          home_prob: 0.49,
          pregame_away_pct: 24,
          pregame_draw_pct: 27,
          pregame_home_pct: 49,
          projected_away: null,
          projected_home: null,
          reason_line: "Trending matchup",
        }}
        surface="standard"
      />,
    );

    const drawRow = byTestId("soccer-187a-centered-draw");
    expect(drawRow?.textContent).toContain("Draw");
    expect(drawRow?.textContent).toContain("27%");
    expect(byTestId("discover-game-reason-line")).toBeNull();

    // Live soccer on Discover uses 0-100 chart scale per Ruling 201
    render(
      <EventCard183A
        card={{
          ...BASE_CARD,
          sport: "soccer_epl",
          sport_name: "Premier League",
          status: "live",
          away_team: "Chelsea",
          home_team: "Arsenal",
          away_score: 0,
          home_score: 1,
          away_prob: 0.14,
          draw_prob: 0.22,
          home_prob: 0.64,
          pregame_away_pct: 24,
          pregame_draw_pct: 27,
          pregame_home_pct: 49,
          pregame_projected_away: null,
          pregame_projected_home: null,
          projected_away: 0.6,
          projected_home: 1.9,
          chart_points: [
            { t: 0, p: 0.49 },
            { t: 1, p: 0.64 },
          ],
        }}
        surface="discover"
      />,
    );
    expect(byTestId("discover-191a-chart-panel")?.getAttribute("data-chart-domain")).toBe("0-100");

    // Finished level 1–1: Draw row gets winner-tick-draw ✓ while clubs show 1 and 1 under Final, with NO bar
    render(
      <EventCard183A
        card={{
          ...BASE_CARD,
          sport: "soccer_epl",
          sport_name: "Premier League",
          status: "completed",
          away_team: "Chelsea",
          home_team: "Arsenal",
          away_score: 1,
          home_score: 1,
          away_prob: null,
          draw_prob: null,
          home_prob: null,
          pregame_away_pct: 24,
          pregame_draw_pct: 27,
          pregame_home_pct: 49,
          projected_away: null,
          projected_home: null,
        }}
        surface="standard"
      />,
    );
    expect(byTestId("winner-tick-draw")?.textContent).toBe("✓");
    expect(byTestId("col-header-score")).toBeNull();
    expect(byTestId("col-header-now")?.textContent).toBe("Final");
    expect(byTestId("compact-probability-bar")).toBeNull();
  });

  it("renders score-first set-by-set tennis columns with serving indicator and no Proj. column", () => {
    render(
      <EventCard183A
        card={{
          ...BASE_CARD,
          sport: "tennis_atp_finals",
          sport_name: "ATP Finals",
          away_team: "Taylor Fritz",
          home_team: "Jannik Sinner",
          status: "live",
          away_score: 1,
          home_score: 1,
          away_prob: 0.284,
          home_prob: 0.716,
          pregame_away_pct: 22,
          pregame_home_pct: 78,
          pregame_projected_away: null,
          pregame_projected_home: null,
          projected_away: 12,
          projected_home: 14,
          live_clock_label: "Set 3",
          serving: "home",
          tennis_sets: [
            { away: 4, home: 6 },
            { away: 7, home: 6, tiebreak_away: 7, tiebreak_home: 5 },
            { away: 2, home: 4, current: true },
          ],
          tennis_game_points: { away: "15", home: "40" },
        }}
        surface="standard"
      />,
    );

    expect(byTestId("tennis-score-strip")?.textContent).toContain("S1");
    expect(byTestId("tennis-score-strip")?.textContent).toContain("S2");
    expect(byTestId("tennis-score-strip")?.textContent).toContain("S3");
    expect(byTestId("tennis-score-strip")?.textContent).toContain("Pts");
    expect(byTestId("tennis-serving-home")).not.toBeNull();
    expect(byTestId("col-header-proj")).toBeNull();
    // Ruling 204-C: live tennis card also drops the grey pregame line
    expect(byTestId("live-pregame-summary-line")).toBeNull();
    expect(host.textContent).toContain("28.4%");
    expect(host.textContent).toContain("71.6%");
  });
});
