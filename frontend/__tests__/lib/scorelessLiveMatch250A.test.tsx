import fs from "fs";
import path from "path";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import EventCard183A, {
  buildUnifiedCardFromEvent,
  buildUnifiedCardFromFeed,
  buildUnifiedCardFromTeamGame,
} from "@/components/EventCard183A";
import EventPageHeadline199 from "@/components/event/EventPageHeadline199";
import { leagueGameToEvent } from "@/lib/leagueCards";
import {
  NO_LIVE_SCORE_GAME_LINE_250A,
  NO_LIVE_SCORE_TOURNAMENT_LINE_250A,
  resolveEventPageHeadline199,
  resolveScoreUnavailableNotice250A,
} from "@/lib/eventPageHeadline199";
import type { Event, EventDetailResponse, FeedEventData, FeedItem } from "@/lib/types";
import type { LeagueGameBrief, TeamGameBrief } from "@/lib/api";

describe("#13000 (250: A) — live match with no score source on website", () => {
  const baseLiveTennis: EventDetailResponse = {
    id: 15350873,
    external_id: "boyer-olivieri-challenger",
    sport: "tennis_atp",
    sport_name: "ATP",
    home_team: "Genaro Alberto Olivieri",
    away_team: "Tristan Boyer",
    commence_time: "2026-11-18T22:00:00Z",
    status: "live",
    home_score: 0,
    away_score: 0,
    score_source_unavailable: true,
    espn: {
      period: "In Progress",
      tennis_sets: [{ away: 0, home: 0, current: true }] as unknown as never,
    } as EventDetailResponse["espn"],
    current_odds: {
      home_probability: 0.376,
      away_probability: 0.624,
      home_rendered_percent: 38,
      away_rendered_percent: 62,
      spread: null,
      over_under: null,
      projected_home_score: null,
      projected_away_score: null,
      captured_at: "2026-11-18T23:05:00Z",
    },
    prematch_odds: {
      home_probability: 0.42,
      away_probability: 0.58,
      home_rendered_percent: 42,
      away_rendered_percent: 58,
      source: "sportsbook",
    },
  };

  it("omits Score, Sets, and S1/Pts columns on EventCard183A with no blank and no dash across event, feed, league, and team adapters", () => {
    const fromEvent = buildUnifiedCardFromEvent(baseLiveTennis as Event);
    expect(fromEvent.score_source_unavailable).toBe(true);

    const html = renderToStaticMarkup(<EventCard183A card={fromEvent} surface="standard" />);
    expect(html).not.toContain('data-testid="col-header-score"');
    expect(html).not.toContain('data-testid="tennis-score-strip"');
    expect(html).not.toContain("In Progress");
    expect(html).toContain("LIVE");
    expect(html).toContain('data-testid="col-header-now"');
    expect(html).toContain("62.4%");
    expect(html).toContain("37.6%");

    const feedItem = { id: "event:15350873", type: "event", reason: null } as unknown as FeedItem;
    const fromFeed = buildUnifiedCardFromFeed(feedItem, baseLiveTennis as unknown as FeedEventData);
    expect(fromFeed.score_source_unavailable).toBe(true);

    const leagueBrief: LeagueGameBrief = {
      id: 15350873,
      sport: "tennis_atp",
      home_team: "Genaro Alberto Olivieri",
      away_team: "Tristan Boyer",
      commence_time: "2026-11-18T22:00:00Z",
      status: "live",
      home_score: null,
      away_score: null,
      score_source_unavailable: true,
      home_win_probability: 0.376,
    };
    const leagueMapped = buildUnifiedCardFromEvent(leagueGameToEvent(leagueBrief));
    expect(leagueMapped.score_source_unavailable).toBe(true);

    const teamBrief: TeamGameBrief = {
      id: 15350873,
      sport_key: "tennis_atp",
      home_team: "Genaro Alberto Olivieri",
      away_team: "Tristan Boyer",
      home_score: null,
      away_score: null,
      score_source_unavailable: true,
      status: "live",
      commence_time: "2026-11-18T22:00:00Z",
      is_home: false,
      opponent: "Genaro Alberto Olivieri",
      win_probability: 0.624,
    };
    const fromTeam = buildUnifiedCardFromTeamGame(teamBrief);
    expect(fromTeam.score_source_unavailable).toBe(true);
  });

  it("prints 'No live score for this tournament.' once on a live tennis match page and drops Score/Sets columns", () => {
    const model = resolveEventPageHeadline199({
      event: baseLiveTennis,
      effectivelyLive: true,
      isLive: true,
      isFinished: false,
      isSuspended: false,
      venueVoided: false,
      venueSettledSentence: null,
      stoppageLabel: null,
      startClock: "pending",
      pregameStateLabel: null,
      liveClockLabel: "Live",
      bestHomeScore: 0,
      bestAwayScore: 0,
      heroScorePairPresent: false,
      heroScoreIsStoppageFiller: false,
      projectedPairRaw: null,
      projectedPairAdmitted: false,
      homeProb: 0.376,
      servedAwayProb: 0.624,
      homePct: 38,
      servedAwayPct: 62,
      probSourceLabel: "Bain Luck blend",
      tenthsOptIn: true,
      settledWinnerSide: null,
      gameMarkets: null,
    });

    expect(model.liveBadgeText).toBe("LIVE");
    expect(model.columns.map((c) => c.role)).toEqual(["now"]);
    expect(model.rows.map((r) => r.cells)).toEqual([["62.4%"], ["37.6%"]]);
    expect(model.scoreUnavailableNotice).toBe(NO_LIVE_SCORE_TOURNAMENT_LINE_250A);

    const html = renderToStaticMarkup(
      <EventPageHeadline199
        event={baseLiveTennis}
        model={model}
        isPinned={false}
        pinDisabled={false}
        onPinToggle={() => {}}
      />,
    );
    const matches = html.match(/No live score for this tournament\./g) ?? [];
    expect(matches).toHaveLength(1);
    expect(html).toContain('data-testid="headline-12472-no-live-score-notice"');
    expect(html).not.toContain(">Score<");
    expect(html).not.toContain(">Sets<");
  });

  it("prints 'No live score for this game.' on a scoreless live team-league match and keeps covered live matches unchanged", () => {
    const teamLeagueLive: EventDetailResponse = {
      ...baseLiveTennis,
      id: 99801,
      sport: "basketball_ncaab",
      sport_name: "NCAAB",
      away_team: "Furman Paladins",
      home_team: "Radford Highlanders",
      score_source_unavailable: true,
    };
    expect(resolveScoreUnavailableNotice250A(teamLeagueLive, true)).toBe(
      NO_LIVE_SCORE_GAME_LINE_250A,
    );

    const teamModel = resolveEventPageHeadline199({
      event: teamLeagueLive,
      effectivelyLive: true,
      isLive: true,
      isFinished: false,
      isSuspended: false,
      venueVoided: false,
      venueSettledSentence: null,
      stoppageLabel: null,
      startClock: "pending",
      pregameStateLabel: null,
      liveClockLabel: "Live",
      bestHomeScore: null,
      bestAwayScore: null,
      heroScorePairPresent: false,
      heroScoreIsStoppageFiller: false,
      projectedPairRaw: { home_score: 79.0, away_score: 80.4 },
      projectedPairAdmitted: true,
      homeProb: 0.511,
      servedAwayProb: 0.489,
      homePct: 51,
      servedAwayPct: 49,
      probSourceLabel: "Bain Luck blend",
      tenthsOptIn: true,
      settledWinnerSide: null,
      gameMarkets: null,
    });
    expect(teamModel.liveBadgeText).toBe("LIVE");
    expect(teamModel.columns.map((c) => c.role)).toEqual(["now"]);
    expect(teamModel.scoreUnavailableNotice).toBe("No live score for this game.");

    const coveredTennis: EventDetailResponse = {
      ...baseLiveTennis,
      score_source_unavailable: undefined,
    };
    expect(resolveScoreUnavailableNotice250A(coveredTennis, true)).toBeNull();
  });

  it("exports static 390px web look HTML when RENDER_WEB_13000_HTML_DIR is set", () => {
    const outDir = process.env.RENDER_WEB_13000_HTML_DIR;
    if (!outDir) return;
    fs.mkdirSync(outDir, { recursive: true });

    const cssDir = path.join(process.cwd(), ".next/static/css");
    const cssFiles = fs.existsSync(cssDir)
      ? fs.readdirSync(cssDir).filter((f) => f.endsWith(".css"))
      : [];
    const cssText = cssFiles
      .map((f) => fs.readFileSync(path.join(cssDir, f), "utf8"))
      .join("\n");

    const tennisCard = buildUnifiedCardFromEvent(baseLiveTennis as Event);
    const tennisModel = resolveEventPageHeadline199({
      event: baseLiveTennis,
      effectivelyLive: true,
      isLive: true,
      isFinished: false,
      isSuspended: false,
      venueVoided: false,
      venueSettledSentence: null,
      stoppageLabel: null,
      startClock: "pending",
      pregameStateLabel: null,
      liveClockLabel: "Live",
      bestHomeScore: 0,
      bestAwayScore: 0,
      heroScorePairPresent: false,
      heroScoreIsStoppageFiller: false,
      projectedPairRaw: null,
      projectedPairAdmitted: false,
      homeProb: 0.376,
      servedAwayProb: 0.624,
      homePct: 38,
      servedAwayPct: 62,
      probSourceLabel: "Bain Luck blend",
      tenthsOptIn: true,
      settledWinnerSide: null,
      gameMarkets: null,
    });

    const teamLeagueLive: EventDetailResponse = {
      ...baseLiveTennis,
      id: 99801,
      sport: "basketball_ncaab",
      sport_name: "NCAAB",
      away_team: "Furman Paladins",
      home_team: "Radford Highlanders",
      score_source_unavailable: true,
    };
    const teamModel = resolveEventPageHeadline199({
      event: teamLeagueLive,
      effectivelyLive: true,
      isLive: true,
      isFinished: false,
      isSuspended: false,
      venueVoided: false,
      venueSettledSentence: null,
      stoppageLabel: null,
      startClock: "pending",
      pregameStateLabel: null,
      liveClockLabel: "Live",
      bestHomeScore: null,
      bestAwayScore: null,
      heroScorePairPresent: false,
      heroScoreIsStoppageFiller: false,
      projectedPairRaw: { home_score: 79.0, away_score: 80.4 },
      projectedPairAdmitted: true,
      homeProb: 0.511,
      servedAwayProb: 0.489,
      homePct: 51,
      servedAwayPct: 49,
      probSourceLabel: "Bain Luck blend",
      tenthsOptIn: true,
      settledWinnerSide: null,
      gameMarkets: null,
    });

    const sheetBody = renderToStaticMarkup(
      <div className="min-h-fit w-[390px] bg-surface-primary p-4 space-y-3.5 font-sans">
        <div className="text-xs font-semibold text-text-secondary">
          250: A · Web match card (no Score/Sets column, LIVE + Now only)
        </div>
        <EventCard183A card={tennisCard} surface="standard" />

        <div className="pt-1 text-xs font-semibold text-text-secondary">
          250: A · Web match page (LIVE + Now + tournament line)
        </div>
        <EventPageHeadline199
          event={baseLiveTennis}
          model={tennisModel}
          isPinned={false}
          pinDisabled={false}
          onPinToggle={() => {}}
        />

        <div className="pt-1 text-xs font-semibold text-text-secondary">
          250: A · Web team-league page (LIVE + Now + game line)
        </div>
        <EventPageHeadline199
          event={teamLeagueLive}
          model={teamModel}
          isPinned={false}
          pinDisabled={false}
          onPinToggle={() => {}}
        />
      </div>,
    );

    const wrapHTML = (body: string, rootPx: number) => `<!doctype html>
<html lang="en" style="font-size:${rootPx}px">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=390, initial-scale=1" />
<style>${cssText}</style>
<style>body{margin:0;background:#f8fafc;font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif;}</style>
</head>
<body>${body}</body>
</html>`;

    fs.writeFileSync(path.join(outDir, "web-13000-default.html"), wrapHTML(sheetBody, 16));
    fs.writeFileSync(path.join(outDir, "web-13000-largest.html"), wrapHTML(sheetBody, 24));
  });
});
