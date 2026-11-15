/** @jest-environment jsdom */
import React, { act } from "react";
import { createRoot } from "react-dom/client";
import EventCard183A, {
  formatLiveTenthsPair,
  formatSingleLiveTenths,
  sharedGameCardTeamFontClass,
  type UnifiedGameCardData,
} from "@/components/EventCard183A";
import { PIN_PATH } from "@/components/PinButton";
import { cleanDiscoverGameReason, isWebGameCard183AEnabled } from "@/lib/gameCard183AFlag";

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
  away_color: "#002244",
  home_prob: 0.575,
  away_prob: 0.425,
  pregame_home_pct: 58,
  pregame_away_pct: 42,
  projected_home: 25,
  projected_away: 20,
  live_clock_label: null,
  reason_line: "A win locks Detroit into the NFC #1 seed entering Thanksgiving.",
};

describe("EventCard183A unified web game card (#12616, switched off by default)", () => {
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

  it("renders pregame compact card with Proj. + Chance columns, shared bookmark PIN_PATH, EKG pulse, segmented bar, and NO Pregame column", () => {
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
    expect(byTestId("discover-191a-chart-panel")).toBeNull();
    expect(byTestId("compact-probability-bar")).not.toBeNull();
    const pinWrap = byTestId("bookmark-pin-icon");
    expect(pinWrap).not.toBeNull();
    expect(pinWrap?.querySelector("path")?.getAttribute("d")).toBe(PIN_PATH);
    expect(byTestId("ekg-feed-pulse")).toBeNull();
    expect(byTestId("discover-game-reason-line")?.textContent).toContain(
      "A win locks Detroit into the NFC #1 seed entering Thanksgiving.",
    );

    const saveBtn = host.querySelector('button[aria-label="Save game"]') as HTMLButtonElement | null;
    expect(saveBtn).not.toBeNull();
    act(() => saveBtn!.click());
    expect(onPin).toHaveBeenCalledTimes(1);
  });

  it("renders live Discover card with Score · Pregame · Now live tenths, single live projection, and 191-A chart panel", () => {
    render(
      <EventCard183A
        card={{
          ...BASE_CARD,
          status: "live",
          away_score: 21,
          home_score: 24,
          away_prob: 0.342,
          home_prob: 0.658,
          projected_away: 27,
          projected_home: 31,
          live_clock_label: "Q4 · 4:12",
          reason_line: "Detroit jumped 24 points in 3 minutes.",
          chart_points: [
            { t: 0, p: 0.58 },
            { t: 0.6, p: 0.42 },
            { t: 1, p: 0.658 },
          ],
        }}
        surface="discover"
      />,
    );

    expect(byTestId("col-header-score")?.textContent).toBe("Score");
    expect(byTestId("col-header-pregame")?.textContent).toBe("Pregame");
    expect(byTestId("col-header-now")?.textContent).toBe("Now");
    expect(byTestId("ekg-feed-pulse")).not.toBeNull();
    expect(host.textContent).toContain("34.2%");
    expect(host.textContent).toContain("65.8%");
    expect(byTestId("live-projected-once")?.textContent).toContain(
      "Proj. final: Patriots 27 – Lions 31",
    );
    expect(byTestId("discover-191a-chart-panel")).not.toBeNull();
    expect(host.textContent).not.toMatch(/Opened/i);
    expect(host.textContent).not.toMatch(/venues/i);
  });

  it("renders settled game matching the app: Pregame and Final columns (no separate Score column), Final shows the score, winner is ticked, and never 'Settled'", () => {
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
    expect(byTestId("col-header-pregame")?.textContent).toBe("Pregame");
    expect(byTestId("col-header-now")?.textContent).toBe("Final");
    expect(byTestId("ekg-feed-pulse")).toBeNull();
    expect(byTestId("winner-tick-home")?.textContent).toBe("✓");
    expect(byTestId("winner-tick-away")).toBeNull();
    expect(host.textContent).toContain("20");
    expect(host.textContent).toContain("28");
    expect(host.textContent).not.toContain("Won ✓");
    expect(byTestId("discover-191a-chart-panel")).not.toBeNull();
    expect(host.textContent).not.toMatch(/Settled/i);
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

    // Finished level 1–1: Draw row gets winner-tick-draw ✓ while clubs show 1 and 1 under Final
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
    expect(byTestId("live-projected-once")).toBeNull();
    expect(host.textContent).toContain("28.4%");
    expect(host.textContent).toContain("71.6%");
  });
});
