/**
 * Ruling 204-C — Website Game Card (`EventCard183A`) Drops Live Grey Line &
 * Wires `/sports` (`FeedCard`) and Team Page (`UpcomingGameCard`, `RecentGameCard`)
 * Behind `NEXT_PUBLIC_GAME_CARD_183A` (default `false`).
 */

import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import EventCard183A, {
  buildUnifiedCardFromTeamGame,
  formatLivePregameSummary,
  type UnifiedGameCardData,
} from "@/components/EventCard183A";
import FeedCard from "@/components/FeedCard";
import { RecentGameCard, UpcomingGameCard } from "@/components/TeamGameCards";
import type { TeamGameBrief } from "@/lib/api";
import type { FeedEventData, FeedItem } from "@/lib/types";

jest.mock("@/components/Analytics", () => ({
  __esModule: true,
  useAnalyticsContext: () => ({ track: jest.fn() }),
}));

const FUTURE_ISO = "2026-11-20T20:00:00Z";
const LIVE_ISO = "2026-11-16T14:00:00Z";
const PAST_ISO = "2026-11-15T20:00:00Z";

function makeTeamGame(overrides: Partial<TeamGameBrief> = {}): TeamGameBrief {
  return {
    id: 4401,
    home_team: "Detroit Lions",
    away_team: "Green Bay Packers",
    opponent: "Green Bay Packers",
    is_home: true,
    commence_time: FUTURE_ISO,
    status: "scheduled",
    home_score: null,
    away_score: null,
    win_probability: 0.58,
    pregame_win_probability: 0.56,
    sport_key: "americanfootball_nfl",
    ...overrides,
  };
}

describe("Ruling 204-C — buildUnifiedCardFromTeamGame & EventCard183A flag-gated surfaces", () => {
  const originalFlag = process.env.NEXT_PUBLIC_GAME_CARD_183A;

  afterEach(() => {
    if (originalFlag === undefined) {
      delete process.env.NEXT_PUBLIC_GAME_CARD_183A;
    } else {
      process.env.NEXT_PUBLIC_GAME_CARD_183A = originalFlag;
    }
  });

  describe("buildUnifiedCardFromTeamGame", () => {
    it("maps a home team's win probability and pregame probability to home and 1-wp complement to away", () => {
      const card = buildUnifiedCardFromTeamGame(
        makeTeamGame({
          is_home: true,
          win_probability: 0.62,
          pregame_win_probability: 0.584,
        }),
        "#0076B6",
      );
      expect(card.home_prob).toBeCloseTo(0.62, 5);
      expect(card.away_prob).toBeCloseTo(0.38, 5);
      expect(card.pregame_home_pct).toBe(58);
      expect(card.pregame_away_pct).toBe(42);
      expect(card.home_color.toLowerCase()).toBe("#0076b6");
    });

    it("maps an away team's win probability to away and 1-wp complement to home on 2-way sports", () => {
      const card = buildUnifiedCardFromTeamGame(
        makeTeamGame({
          is_home: false,
          opponent: "Detroit Lions",
          win_probability: 0.41,
          pregame_win_probability: 0.442,
        }),
        "#203731",
      );
      expect(card.away_prob).toBeCloseTo(0.41, 5);
      expect(card.home_prob).toBeCloseTo(0.59, 5);
      expect(card.pregame_away_pct).toBe(44);
      expect(card.pregame_home_pct).toBe(56);
      expect(card.away_color.toLowerCase()).toBe("#203731");
    });

    it("withholds the unserved opponent complement on draw-priced sports (soccer)", () => {
      const awaySoccer = buildUnifiedCardFromTeamGame(
        makeTeamGame({
          sport_key: "soccer_epl",
          home_team: "Chelsea",
          away_team: "Arsenal",
          opponent: "Chelsea",
          is_home: false,
          win_probability: 0.64,
          pregame_win_probability: 0.59,
        }),
        "#EF0107",
      );
      expect(awaySoccer.away_prob).toBeCloseTo(0.64, 5);
      expect(awaySoccer.home_prob).toBeNull();
      expect(awaySoccer.pregame_away_pct).toBe(59);
      expect(awaySoccer.pregame_home_pct).toBeNull();

      const homeSoccer = buildUnifiedCardFromTeamGame(
        makeTeamGame({
          sport_key: "soccer_epl",
          home_team: "Arsenal",
          away_team: "Chelsea",
          opponent: "Chelsea",
          is_home: true,
          win_probability: 0.64,
          pregame_win_probability: 0.59,
        }),
        "#EF0107",
      );
      expect(homeSoccer.home_prob).toBeCloseTo(0.64, 5);
      expect(homeSoccer.away_prob).toBeNull();
      expect(homeSoccer.pregame_home_pct).toBe(59);
      expect(homeSoccer.pregame_away_pct).toBeNull();
    });

    it("clears live/current probabilities on finished games while preserving pregame percentages", () => {
      const done = buildUnifiedCardFromTeamGame(
        makeTeamGame({
          status: "completed",
          commence_time: PAST_ISO,
          completed_at: PAST_ISO,
          home_score: 27,
          away_score: 20,
          win_probability: 1.0,
          pregame_win_probability: 0.58,
        }),
        "#0076B6",
      );
      expect(done.home_prob).toBeNull();
      expect(done.away_prob).toBeNull();
      expect(done.pregame_home_pct).toBe(58);
      expect(done.pregame_away_pct).toBe(42);
    });

    it("handles null and non-finite pregame_win_probability cleanly without NaN%", () => {
      const nullPre = buildUnifiedCardFromTeamGame(
        makeTeamGame({ pregame_win_probability: null }),
        null,
      );
      expect(nullPre.pregame_home_pct).toBeNull();
      expect(nullPre.pregame_away_pct).toBeNull();

      const nanPre = buildUnifiedCardFromTeamGame(
        makeTeamGame({ pregame_win_probability: Number.NaN }),
        null,
      );
      expect(nanPre.pregame_home_pct).toBeNull();
      expect(nanPre.pregame_away_pct).toBeNull();
    });
  });

  describe("homeOnlyWithheld / singleAwayPct bar & chance rendering on away soccer team cards", () => {
    it("renders single away whole percent before play and single away tenths during play with left-anchored bar and no home segment", () => {
      const baseCard = buildUnifiedCardFromTeamGame(
        makeTeamGame({
          sport_key: "soccer_epl",
          home_team: "Chelsea",
          away_team: "Arsenal",
          opponent: "Chelsea",
          is_home: false,
          win_probability: 0.624,
          pregame_win_probability: 0.59,
        }),
        "#EF0107",
      );

      const preHtml = renderToStaticMarkup(<EventCard183A card={baseCard} surface="standard" />);
      expect(preHtml).toContain('data-testid="primary-chance-away">62%<');
      expect(preHtml).toContain('data-testid="primary-chance-home">—<');
      expect(preHtml).toContain("justify-start bg-surface-border/40");
      expect(preHtml).toContain("width:62.4%");
      expect(preHtml).not.toContain("rounded-r-full");

      const liveCard: UnifiedGameCardData = {
        ...baseCard,
        status: "live",
        commence_time: LIVE_ISO,
        away_score: 1,
        home_score: 0,
      };
      const liveHtml = renderToStaticMarkup(<EventCard183A card={liveCard} surface="standard" />);
      expect(liveHtml).toContain('data-testid="primary-chance-away">62.4%<');
      expect(liveHtml).toContain('data-testid="primary-chance-home">—<');
      expect(liveHtml).not.toContain('data-testid="pregame-bar-tick"');
      expect(liveHtml).not.toContain('data-testid="live-pregame-summary-line"');
    });
  });

  describe("Flag-on delegation in FeedCard, UpcomingGameCard, and RecentGameCard", () => {
    it("delegates FeedCard event items to EventCard183A only when NEXT_PUBLIC_GAME_CARD_183A=true, with Score · Proj. · Now and no live grey line", () => {
      const eventData: FeedEventData = {
        id: 7701,
        sport: "americanfootball_nfl",
        sport_name: "NFL",
        home_team: "Detroit Lions",
        away_team: "Green Bay Packers",
        commence_time: LIVE_ISO,
        status: "live",
        home_score: 17,
        away_score: 14,
        live_clock: "Q3 6:12",
        current_odds: {
          home_probability: 0.664,
          away_probability: 0.336,
          projected_home_score: 27.4,
          projected_away_score: 23.1,
          live_projection: {
            kind: "in_play",
            boundary: "commence_time",
            boundary_at: LIVE_ISO,
            earliest_confirmed_at: "2026-11-16T14:05:00Z",
            latest_captured_at: "2026-11-16T14:50:00Z",
            source: "sportsbooks",
            basis: "consensus_spread_total",
            bookmaker_count: 12,
            unit: "points",
            period: "full_game",
            projected_home_score: 27.4,
            projected_away_score: 23.1,
          },
        },
        prematch_odds: {
          home_probability: 0.58,
          away_probability: 0.42,
          home_rendered_percent: 58,
          away_rendered_percent: 42,
        },
      } as unknown as FeedEventData;

      const feedItem: FeedItem = {
        type: "event",
        id: "event-7701",
        score: 90,
        reason: null,
        data: eventData,
      } as unknown as FeedItem;

      delete process.env.NEXT_PUBLIC_GAME_CARD_183A;
      const offHtml = renderToStaticMarkup(<FeedCard item={feedItem} />);
      expect(offHtml).not.toContain('data-testid="event-card-183a-standard"');

      process.env.NEXT_PUBLIC_GAME_CARD_183A = "true";
      const onHtml = renderToStaticMarkup(<FeedCard item={feedItem} />);
      expect(onHtml).toContain('data-testid="event-card-183a-standard"');
      expect(onHtml).toContain(">Score<");
      expect(onHtml).toContain(">Proj.<");
      expect(onHtml).toContain(">Now<");
      expect(onHtml).toContain('data-testid="pregame-bar-tick"');
      expect(onHtml).not.toContain('data-testid="live-pregame-summary-line"');
      expect(onHtml).not.toContain("Pregame");

      // When live_projection is unheld, "Proj." is omitted so no header floats over an empty column
      const unheldFeedItem: FeedItem = {
        ...feedItem,
        data: {
          ...eventData,
          current_odds: {
            home_probability: 0.664,
            away_probability: 0.336,
          },
        },
      } as unknown as FeedItem;
      const unheldHtml = renderToStaticMarkup(<FeedCard item={unheldFeedItem} />);
      expect(unheldHtml).toContain(">Score<");
      expect(unheldHtml).toContain(">Now<");
      expect(unheldHtml).not.toContain(">Proj.<");

      // On college games without logos, CrestBadge honours served school abbreviations (Ruling 194-A)
      const customAbbrevItem: FeedItem = {
        ...feedItem,
        data: {
          ...eventData,
          sport: "americanfootball_ncaaf",
          home_team: "Bainport State Wolfpack",
          away_team: "Harbor Tech Engineers",
          home_team_data: { name: "Bainport State Wolfpack", abbreviation: "BPST" },
          away_team_data: { name: "Harbor Tech Engineers", abbreviation: "HTU" },
        },
      } as unknown as FeedItem;
      const abbrevHtml = renderToStaticMarkup(<FeedCard item={customAbbrevItem} />);
      expect(abbrevHtml).toContain(">BPST<");
      expect(abbrevHtml).toContain(">HTU<");
    });

    it("delegates UpcomingGameCard and RecentGameCard to EventCard183A only when NEXT_PUBLIC_GAME_CARD_183A=true", () => {
      const upcoming = makeTeamGame({
        status: "live",
        commence_time: LIVE_ISO,
        home_score: 14,
        away_score: 10,
        win_probability: 0.642,
        pregame_win_probability: 0.58,
      });
      const recent = makeTeamGame({
        id: 4402,
        status: "completed",
        commence_time: PAST_ISO,
        completed_at: PAST_ISO,
        home_score: 27,
        away_score: 20,
        win_probability: 1.0,
        pregame_win_probability: 0.58,
      });

      delete process.env.NEXT_PUBLIC_GAME_CARD_183A;
      const upcomingOff = renderToStaticMarkup(
        <UpcomingGameCard game={upcoming} teamName="Detroit Lions" teamColor="#0076B6" />,
      );
      const recentOff = renderToStaticMarkup(<RecentGameCard game={recent} />);
      expect(upcomingOff).not.toContain('data-testid="event-card-183a-standard"');
      expect(recentOff).not.toContain('data-testid="event-card-183a-standard"');

      process.env.NEXT_PUBLIC_GAME_CARD_183A = "true";
      const upcomingOn = renderToStaticMarkup(
        <UpcomingGameCard game={upcoming} teamName="Detroit Lions" teamColor="#0076B6" />,
      );
      const recentOn = renderToStaticMarkup(<RecentGameCard game={recent} />);

      expect(upcomingOn).toContain('data-testid="event-card-183a-standard"');
      expect(upcomingOn).toContain('data-testid="pregame-bar-tick"');
      expect(upcomingOn).not.toContain('data-testid="live-pregame-summary-line"');

      expect(recentOn).toContain('data-testid="event-card-183a-standard"');
      expect(recentOn).toContain('data-testid="winner-tick-home"');
      expect(recentOn).not.toContain('data-testid="compact-probability-bar"');
    });
  });

  it("keeps formatLivePregameSummary intact for the game-page headline (Ruling 200-B)", () => {
    const line = formatLivePregameSummary(
      {
        sport: "americanfootball_nfl",
        pregame_home_pct: 58,
        pregame_away_pct: 42,
        pregame_projected_home: "27",
        pregame_projected_away: "23",
      },
      "Packers",
      "Lions",
    );
    expect(line?.fullText).toBe("Pregame  Lions 58% · projected 27–23");
  });
});
