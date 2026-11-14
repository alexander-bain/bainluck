/** @jest-environment jsdom */
import React, { act } from "react";
import { createRoot } from "react-dom/client";
import EventCard183A, { type UnifiedGameCardData } from "@/components/EventCard183A";
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

  it("renders pregame compact card with Proj. + Chance columns, bookmark pin, EKG pulse, and NO Pregame column", () => {
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
    expect(byTestId("bookmark-pin-icon")).not.toBeNull();
    expect(byTestId("ekg-feed-pulse")).not.toBeNull();
    expect(byTestId("discover-game-reason-line")?.textContent).toContain(
      "A win locks Detroit into the NFC #1 seed entering Thanksgiving.",
    );

    const saveBtn = host.querySelector('button[aria-label="Save game"]') as HTMLButtonElement | null;
    expect(saveBtn).not.toBeNull();
    act(() => saveBtn!.click());
    expect(onPin).toHaveBeenCalledTimes(1);
  });

  it("renders live Discover card with Score · Pregame · Now columns, single live projection, and 191-A chart panel", () => {
    render(
      <EventCard183A
        card={{
          ...BASE_CARD,
          status: "live",
          away_score: 21,
          home_score: 24,
          away_prob: 0.34,
          home_prob: 0.66,
          projected_away: 27,
          projected_home: 31,
          live_clock_label: "Q4 · 4:12",
          reason_line: "Detroit swung 24 points in 3 minutes after a fourth-down red-zone takeaway.",
          chart_points: [
            { t: 0, p: 0.58 },
            { t: 0.6, p: 0.42 },
            { t: 1, p: 0.66 },
          ],
        }}
        surface="discover"
      />,
    );

    expect(byTestId("col-header-score")?.textContent).toBe("Score");
    expect(byTestId("col-header-pregame")?.textContent).toBe("Pregame");
    expect(byTestId("col-header-now")?.textContent).toBe("Now");
    expect(byTestId("live-projected-once")?.textContent).toContain(
      "Proj. final: Patriots 27 – Lions 31",
    );
    expect(byTestId("discover-191a-chart-panel")).not.toBeNull();
    expect(host.textContent).not.toMatch(/Opened/i);
    expect(host.textContent).not.toMatch(/venues/i);
  });

  it("renders settled game with two rows, Score · Pregame · Final columns, and never 'Settled'", () => {
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

    expect(byTestId("col-header-score")?.textContent).toBe("Score");
    expect(byTestId("col-header-pregame")?.textContent).toBe("Pregame");
    expect(byTestId("col-header-now")?.textContent).toBe("Final");
    expect(host.textContent).toContain("Won");
    expect(byTestId("discover-191a-chart-panel")).not.toBeNull();
    expect(host.textContent).not.toMatch(/Settled/i);
  });

  it("renders 187-A centered Draw strip on 3-way soccer and leaves off filler reason lines", () => {
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
          projected_away: null,
          projected_home: null,
          reason_line: "Trending matchup",
        }}
        surface="discover"
      />,
    );

    expect(byTestId("soccer-187a-centered-draw")?.textContent).toContain("Draw");
    expect(byTestId("soccer-187a-centered-draw")?.textContent).toContain("27%");
    expect(byTestId("discover-game-reason-line")).toBeNull();
  });
});
