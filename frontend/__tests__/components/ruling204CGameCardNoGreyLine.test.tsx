/**
 * Ruling 204-C — Website Game Card (`EventCard183A`) Drops Live Grey Line &
 * Wires `/sports` (`FeedCard`) and Team Page (`UpcomingGameCard`, `RecentGameCard`)
 * Behind `NEXT_PUBLIC_GAME_CARD_183A` (default `false`).
 */

import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import EventPageHeadline199 from "@/components/event/EventPageHeadline199";
import { resolveEventPageHeadline199 } from "@/lib/eventPageHeadline199";
import EventCard183A, {
  buildUnifiedCardFromEvent,
  buildUnifiedCardFromTeamGame,
  extractDiscoverChartPointsFromHistory,
  formatLivePregameSummary,
  formatPregameKickoff,
  resolveLiveSummarySideInk,
  type UnifiedGameCardData,
} from "@/components/EventCard183A";
import FeedCard from "@/components/FeedCard";
import { RecentGameCard, UpcomingGameCard } from "@/components/TeamGameCards";
import type { TeamGameBrief } from "@/lib/api";
import type { Event, EventHistoryResponse, FeedEventData, FeedItem } from "@/lib/types";

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
      // Rulings 213-A & 214-A1: live card prints single grey pregame line ("Pregame  Arsenal 59%")
      expect(liveHtml).toContain('data-testid="live-pregame-summary-line"');
      expect(liveHtml).toContain("Arsenal 59%");
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

      process.env.NEXT_PUBLIC_GAME_CARD_183A = "false";
      const offHtml = renderToStaticMarkup(<FeedCard item={feedItem} />);
      expect(offHtml).not.toContain('data-testid="event-card-183a-standard"');

      delete process.env.NEXT_PUBLIC_GAME_CARD_183A;
      const onHtml = renderToStaticMarkup(<FeedCard item={feedItem} />);
      expect(onHtml).toContain('data-testid="event-card-183a-standard"');
      expect(onHtml).toContain(">Score<");
      expect(onHtml).toContain(">Proj.<");
      expect(onHtml).toContain(">Now<");
      // Decision 207 live clock fix: prints period + clock ("Q3 6:12") without "LIVE · " prefix
      expect(onHtml).toContain("Q3 6:12");
      expect(onHtml).not.toContain("LIVE ·");
      expect(onHtml).toContain('data-testid="pregame-bar-tick"');
      expect(onHtml).toContain('data-testid="live-pregame-summary-line"');
      expect(onHtml).toContain("Lions 58%");

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

      process.env.NEXT_PUBLIC_GAME_CARD_183A = "false";
      const upcomingOff = renderToStaticMarkup(
        <UpcomingGameCard game={upcoming} teamName="Detroit Lions" teamColor="#0076B6" />,
      );
      const recentOff = renderToStaticMarkup(<RecentGameCard game={recent} />);
      expect(upcomingOff).not.toContain('data-testid="event-card-183a-standard"');
      expect(recentOff).not.toContain('data-testid="event-card-183a-standard"');

      delete process.env.NEXT_PUBLIC_GAME_CARD_183A;
      const upcomingOn = renderToStaticMarkup(
        <UpcomingGameCard game={upcoming} teamName="Detroit Lions" teamColor="#0076B6" />,
      );
      const recentOn = renderToStaticMarkup(<RecentGameCard game={recent} />);

      expect(upcomingOn).toContain('data-testid="event-card-183a-standard"');
      expect(upcomingOn).toContain('data-testid="pregame-bar-tick"');
      expect(upcomingOn).toContain('data-testid="live-pregame-summary-line"');

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

  describe("Decision 207 turn-on fixes (#12616)", () => {
    it("1. Dates: prints Today on the same day, weekday alone within 6 days, and weekday + month day beyond 6 days", () => {
      // Jest pins TZ=UTC
      const nowMs = Date.parse("2026-11-16T15:00:00Z"); // Mon Nov 16
      expect(formatPregameKickoff("2026-11-16T22:15:00Z", false, nowMs)).toBe("Today 10:15 PM");
      expect(formatPregameKickoff("2026-11-22T18:00:00Z", false, nowMs)).toBe("Sun 6:00 PM"); // +6d
      expect(formatPregameKickoff("2026-11-26T18:00:00Z", false, nowMs)).toBe(
        "Thu Nov 26, 6:00 PM",
      ); // +10d
      expect(formatPregameKickoff("2026-12-06T18:00:00Z", false, nowMs)).toBe(
        "Sun Dec 6, 6:00 PM",
      ); // +20d
      expect(formatPregameKickoff("2026-12-13T18:00:00Z", false, nowMs)).toBe(
        "Sun Dec 13, 6:00 PM",
      ); // +27d
    });

    it("2. Finished search cards never fall back to opening_odds (print Final alone when prematch_odds is absent) and clamp <1% / >99% when prematch_odds is sent", () => {
      const lmuAtHawaiiNoPrematch = {
        id: 15349582,
        sport: "basketball_wncaab",
        sport_name: "WNCAAB",
        home_team: "Hawai'i Rainbow Warriors",
        away_team: "Loyola Marymount Lions",
        commence_time: "2026-11-16T00:45:00Z",
        status: "completed",
        home_score: 49,
        away_score: 59,
        opening_odds: {
          home_probability: 0.2665,
          away_probability: 0.7335,
        },
      } as unknown as Event;

      const cardWithoutPrematch = buildUnifiedCardFromEvent(lmuAtHawaiiNoPrematch);
      expect(cardWithoutPrematch.pregame_away_pct).toBeNull();
      expect(cardWithoutPrematch.pregame_home_pct).toBeNull();
      const htmlWithoutPrematch = renderToStaticMarkup(
        <EventCard183A card={cardWithoutPrematch} surface="standard" />,
      );
      expect(htmlWithoutPrematch).not.toContain(">Pregame<");
      expect(htmlWithoutPrematch).toContain(">Final<");
      expect(htmlWithoutPrematch).not.toContain(">73%<");
      expect(htmlWithoutPrematch).not.toContain(">27%<");

      // When prematch_odds IS sent (including extreme 0.9975 / 0.0025), prints Pregame · Final and clamps >99% / <1%
      const uapbAtUsc = {
        id: 15348906,
        sport: "basketball_ncaab",
        sport_name: "NCAAB",
        home_team: "USC Trojans",
        away_team: "Arkansas-Pine Bluff Golden Lions",
        commence_time: "2026-11-16T00:00:00Z",
        status: "completed",
        home_score: 122,
        away_score: 46,
        prematch_odds: {
          home_probability: 0.9975,
          away_probability: 0.0025,
          source: "odds_snapshot",
          captured_at: "2026-11-15T23:55:00Z",
        },
      } as unknown as Event;
      const uscHtml = renderToStaticMarkup(
        <EventCard183A card={buildUnifiedCardFromEvent(uapbAtUsc)} surface="standard" />,
      );
      expect(uscHtml).toContain(">Pregame<");
      expect(uscHtml).toContain(">Final<");
      expect(uscHtml).toContain("&gt;99%");
      expect(uscHtml).toContain("&lt;1%");
      expect(uscHtml).not.toContain(">100%<");
      expect(uscHtml).not.toContain(">0%<");
    });

    it("3. Row order stays strictly [away, home] across before, during, and after regardless of who leads or wins", () => {
      const states: Array<Partial<Event>> = [
        { status: "scheduled", home_score: null, away_score: null },
        { status: "live", home_score: 31, away_score: 24 },
        { status: "completed", home_score: 49, away_score: 59 }, // away wins
        { status: "completed", home_score: 122, away_score: 46 }, // home wins
      ];
      for (const st of states) {
        const ev = {
          id: 15349582,
          sport: "basketball_wncaab",
          sport_name: "WNCAAB",
          home_team: "Hawai'i Rainbow Warriors",
          away_team: "Loyola Marymount Lions",
          commence_time: "2026-11-16T00:45:00Z",
          current_odds: { home_probability: 0.27, away_probability: 0.73 },
          opening_odds: { home_probability: 0.27, away_probability: 0.73 },
          ...st,
        } as unknown as Event;
        const html = renderToStaticMarkup(
          <EventCard183A card={buildUnifiedCardFromEvent(ev)} surface="standard" />,
        );
        const awayIdx = html.indexOf("Loyola Marymount");
        const homeIdx = html.indexOf("Hawai");
        expect(awayIdx).toBeGreaterThan(-1);
        expect(homeIdx).toBeGreaterThan(awayIdx);
      }
    });

    it("4. Team-page cards resolve both teams' colours and apply Ruling 197 collision switching", () => {
      // Titans (#0C2340 navy blue, secondary #C8102E red) at Lions (#0076B6 Honolulu blue) — both blue family!
      const titansAtLions = buildUnifiedCardFromTeamGame(
        makeTeamGame({
          home_team: "Detroit Lions",
          away_team: "Tennessee Titans",
          opponent: "Tennessee Titans",
          is_home: true,
        }),
        { teamColor: "#0076B6", teamSecondaryColor: "#B0B7BC" },
      );
      expect(titansAtLions.home_color.toLowerCase()).toBe("#0076b6");
      // Ruling 197 switches away Titans from blue #0C2340 to red #C8102E (never grey #475569!)
      expect(titansAtLions.away_color.toLowerCase()).toBe("#c8102e");

      // Buccaneers (#D50A0A red) at Lions (#0076B6 blue) — distinct families keep both main colours
      const bucsAtLions = buildUnifiedCardFromTeamGame(
        makeTeamGame({
          home_team: "Detroit Lions",
          away_team: "Tampa Bay Buccaneers",
          opponent: "Tampa Bay Buccaneers",
          is_home: true,
        }),
        { teamColor: "#0076B6" },
      );
      expect(bucsAtLions.home_color.toLowerCase()).toBe("#0076b6");
      expect(bucsAtLions.away_color.toLowerCase()).toBe("#d50a0a");
    });

    it("5. extractDiscoverChartPointsFromHistory requires >= 3 readings and returns undefined for <= 2 readings", () => {
      const twoPoints = {
        event_id: 1,
        home_team: "A",
        away_team: "B",
        history: [
          { timestamp: "2026-11-16T01:00:00Z", home_probability: 0.79 },
          { timestamp: "2026-11-16T03:30:00Z", home_probability: 0.0 },
        ],
      } as unknown as EventHistoryResponse;
      expect(extractDiscoverChartPointsFromHistory(twoPoints)).toBeUndefined();

      const fourPoints = {
        event_id: 1,
        home_team: "A",
        away_team: "B",
        history: [
          { timestamp: "2026-11-16T01:00:00Z", home_probability: 0.79 },
          { timestamp: "2026-11-16T01:45:00Z", home_probability: 0.62 },
          { timestamp: "2026-11-16T02:30:00Z", home_probability: 0.34 },
          { timestamp: "2026-11-16T03:30:00Z", home_probability: 0.0 },
        ],
      } as unknown as EventHistoryResponse;
      const extracted = extractDiscoverChartPointsFromHistory(fourPoints);
      expect(extracted).toHaveLength(4);
      expect(extracted?.[0]).toEqual({ t: 0, p: 0.79 });
      expect(extracted?.[3]).toEqual({ t: 1, p: 0 });
    });

    it("6. resolveLiveClock handles numeric raw espn_data.period safely without throwing", () => {
      const liveWithNumericEspnData = {
        id: 15349999,
        sport: "americanfootball_nfl",
        sport_name: "NFL",
        home_team: "Detroit Lions",
        away_team: "Green Bay Packers",
        commence_time: LIVE_ISO,
        status: "live",
        home_score: 17,
        away_score: 14,
        espn_data: { period: 3, game_clock: "8:14" },
      } as unknown as Event;
      const card = buildUnifiedCardFromEvent(liveWithNumericEspnData);
      expect(card.live_clock_label).toBe("8:14");
    });

    it("7. Rulings 213-A & 214-A1: colours named team + first projected number in named team's colour and second in opponent's across same-colour-family (Kansas–Duke) and grey-fallback (Gonzaga–Duke) pairs on both page and card", () => {
      // A) Same-colour-family pair: Kansas (#0051BA blue, secondary #E8000D crimson) @ Duke (#003087 blue)
      // Suppose Kansas was pregame 54% favourite, projected Kansas 79 – Duke 76 -> named Kansas first!
      const kansasAtDukeEvent = {
        id: 21401,
        sport: "basketball_ncaab",
        sport_name: "NCAAB",
        home_team: "Duke Blue Devils",
        away_team: "Kansas Jayhawks",
        commence_time: LIVE_ISO,
        status: "live",
        home_score: 41,
        away_score: 44,
        espn: { period: "2nd Half", game_clock: "11:20" },
        current_odds: {
          home_probability: 0.462,
          away_probability: 0.538,
          projected_home_score: 77.0,
          projected_away_score: 80.0,
          live_projection: {
            kind: "in_play",
            boundary: "commence_time",
            boundary_at: LIVE_ISO,
            earliest_confirmed_at: "2026-11-16T14:05:00Z",
            latest_captured_at: "2026-11-16T14:50:00Z",
            source: "sportsbooks",
            basis: "consensus_spread_total",
            bookmaker_count: 10,
            unit: "points",
            period: "full_game",
            projected_home_score: 77.0,
            projected_away_score: 80.0,
          },
        },
        prematch_odds: {
          home_probability: 0.46,
          away_probability: 0.54,
          source: "odds_snapshot",
          captured_at: "2026-11-16T13:55:00Z",
        },
        pregame_projection: {
          kind: "last_before_scheduled_start",
          boundary: "scheduled_start",
          boundary_at: LIVE_ISO,
          source: "sportsbooks",
          basis: "consensus_spread_total",
          unit: "points",
          period: "full_game",
          projected_home_score: 76.1,
          projected_away_score: 79.2,
          bookmaker_count: 10,
          earliest_captured_at: "2026-11-16T13:30:00Z",
          latest_captured_at: "2026-11-16T13:58:00Z",
        },
      } as unknown as Event;

      const kuCard = buildUnifiedCardFromEvent(kansasAtDukeEvent);
      const kuCardHtml = renderToStaticMarkup(<EventCard183A card={kuCard} surface="standard" />);
      expect(kuCardHtml).toContain('data-testid="live-pregame-named"');
      // Kansas switched to crimson #E8000D; Duke stays #00539B; named Kansas (79) comes first, Duke (76) second
      expect(kuCardHtml.toLowerCase()).toContain('style="color:#e8000d" data-testid="live-pregame-named">kansas 54%<');
      expect(kuCardHtml.toLowerCase()).toContain('style="color:#e8000d" data-testid="live-pregame-proj-first">79<');
      expect(kuCardHtml.toLowerCase()).toContain('style="color:#00539b" data-testid="live-pregame-proj-second">76<');

      const kuPageModel = resolveEventPageHeadline199({
        event: kansasAtDukeEvent as never,
        isLive: true,
        effectivelyLive: true,
        isFinished: false,
        isSuspended: false,
        stoppageLabel: null,
        venueVoided: false,
        venueSettledSentence: null,
        homeProb: 0.462,
        servedAwayProb: 0.538,
        homePct: 46,
        servedAwayPct: 54,
        probSourceLabel: "Blend",
        tenthsOptIn: true,
        settledWinnerSide: null,
        bestHomeScore: 41,
        bestAwayScore: 44,
        heroScorePairPresent: true,
        heroScoreIsStoppageFiller: false,
        projectedPairAdmitted: true,
        projectedPairRaw: { home_score: 77, away_score: 80 },
        liveClockLabel: "2H 11:20",
        startClock: "clock",
        pregameStateLabel: null,
      });
      const kuPageHtml = renderToStaticMarkup(
        <EventPageHeadline199
          model={kuPageModel}
          event={kansasAtDukeEvent as never}
          isPinned={false}
          pinDisabled={false}
          onPinToggle={jest.fn()}
        />,
      );
      expect(kuPageHtml.toLowerCase()).toContain('style="color:#e8000d" data-testid="headline-pregame-named">kansas 54%<');
      expect(kuPageHtml.toLowerCase()).toContain('style="color:#e8000d" data-testid="headline-pregame-proj-first">79<');
      expect(kuPageHtml.toLowerCase()).toContain('style="color:#00539b" data-testid="headline-pregame-proj-second">76<');

      // B) Grey-fallback pair: Kentucky (#0033A0 blue, #FFFFFF white secondary -> Ruling 197 slate fallback) @ Duke (#00539B blue)
      const kentuckyAtDukeEvent = {
        ...kansasAtDukeEvent,
        id: 21402,
        away_team: "Kentucky Wildcats",
        away_team_data: {
          name: "Kentucky Wildcats",
          primary_color: "#0033A0",
          secondary_color: "#FFFFFF",
        },
      } as unknown as Event;
      expect(resolveLiveSummarySideInk("#64748B")).toBe("#475569");
      const ukCardHtml = renderToStaticMarkup(
        <EventCard183A card={buildUnifiedCardFromEvent(kentuckyAtDukeEvent)} surface="standard" />,
      );
      expect(ukCardHtml.toLowerCase()).toContain('style="color:#475569" data-testid="live-pregame-named">kentucky 54%<');
      expect(ukCardHtml.toLowerCase()).toContain('style="color:#475569" data-testid="live-pregame-proj-first">79<');
      expect(ukCardHtml.toLowerCase()).toContain('style="color:#00539b" data-testid="live-pregame-proj-second">76<');

      const ukPageModel = resolveEventPageHeadline199({
        event: kentuckyAtDukeEvent as never,
        isLive: true,
        effectivelyLive: true,
        isFinished: false,
        isSuspended: false,
        stoppageLabel: null,
        venueVoided: false,
        venueSettledSentence: null,
        homeProb: 0.462,
        servedAwayProb: 0.538,
        homePct: 46,
        servedAwayPct: 54,
        probSourceLabel: "Blend",
        tenthsOptIn: true,
        settledWinnerSide: null,
        bestHomeScore: 41,
        bestAwayScore: 44,
        heroScorePairPresent: true,
        heroScoreIsStoppageFiller: false,
        projectedPairAdmitted: true,
        projectedPairRaw: { home_score: 77, away_score: 80 },
        liveClockLabel: "2H 11:20",
        startClock: "clock",
        pregameStateLabel: null,
      });
      const ukPageHtml = renderToStaticMarkup(
        <EventPageHeadline199
          model={ukPageModel}
          event={kentuckyAtDukeEvent as never}
          isPinned={false}
          pinDisabled={false}
          onPinToggle={jest.fn()}
        />,
      );
      expect(ukPageHtml.toLowerCase()).toContain('style="color:#475569" data-testid="headline-pregame-named">kentucky 54%<');
      expect(ukPageHtml.toLowerCase()).toContain('style="color:#475569" data-testid="headline-pregame-proj-first">79<');
      expect(ukPageHtml.toLowerCase()).toContain('style="color:#00539b" data-testid="headline-pregame-proj-second">76<');
    });
  });
});
