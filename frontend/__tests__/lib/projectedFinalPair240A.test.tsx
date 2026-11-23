import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import EventCard183A, {
  buildUnifiedCardFromEvent,
  buildUnifiedCardFromFeed,
} from "@/components/EventCard183A";
import { resolveEventPageHeadline199 } from "@/lib/eventPageHeadline199";
import {
  cardProjectedFinal,
  liveCardProjectedFinal,
  projectedPairConflictsWithChance,
} from "@/lib/projectedFinalPair";
import type { Event, EventDetailResponse, FeedEventData, FeedItem } from "@/lib/types";

describe("Ruling 240: A (#12992) — projected final level pairs & winner coherence", () => {
  const futureISO = new Date(Date.now() + 4 * 3600 * 1000).toISOString();

  it("Rule 1: prints a level rounded pair on non-tie sports (76ers @ Magic 111–111, LSU @ Tennessee 23–23)", () => {
    // 76ers @ Magic (#15350555): 111.1 / 110.6 -> 111–111 beside 49% / 51%
    expect(
      cardProjectedFinal(
        { projected_home_score: 110.6, projected_away_score: 111.1 },
        "basketball_nba",
        { home: 0.505, away: 0.495 },
      ),
    ).toEqual({ home: 111, away: 111 });

    // LSU @ Tennessee (#15175997): 23.4 / 22.5 -> 23–23 beside 51% / 49%
    expect(
      cardProjectedFinal(
        { projected_home_score: 22.5, projected_away_score: 23.4 },
        "americanfootball_ncaaf",
        { home: 0.4929, away: 0.5071 },
      ),
    ).toEqual({ home: 23, away: 23 });
  });

  it("Rule 2: hides the projected pair when rounded score and chance name different winners", () => {
    // South Florida @ Florida Atlantic (#15349440): 32.5 / 31.9 -> 33–32 (away ahead) vs 51% home
    expect(
      cardProjectedFinal(
        { projected_home_score: 31.9, projected_away_score: 32.5 },
        "americanfootball_ncaaf",
        { home: 0.505, away: 0.495 },
      ),
    ).toBeNull();

    // Exact 50% (0.5 / 0.5) never conflicts
    expect(
      cardProjectedFinal(
        { projected_home_score: 31.9, projected_away_score: 32.5 },
        "americanfootball_ncaaf",
        { home: 0.5, away: 0.5 },
      ),
    ).toEqual({ home: 32, away: 33 });

    // Level pair never conflicts regardless of chance
    expect(
      projectedPairConflictsWithChance(
        { home: 111, away: 111 },
        { home: 0.72, away: 0.28 },
        "basketball_nba",
      ),
    ).toBe(false);

    // Furman @ Radford (#15350596) live: 80.4 / 79.0 -> 80–79 away ahead vs 51.1% home
    const startISO = new Date(Date.now() - 1800 * 1000).toISOString();
    const confirmISO = new Date(Date.now() - 60 * 1000).toISOString();
    expect(
      liveCardProjectedFinal(
        {
          live_projection: {
            projected_home_score: 79.0,
            projected_away_score: 80.4,
            kind: "in_play",
            boundary: "commence_time",
            boundary_at: startISO,
            earliest_confirmed_at: confirmISO,
            latest_captured_at: confirmISO,
            source: "sportsbooks",
            basis: "consensus_spread_total",
            bookmaker_count: 6,
            unit: "points",
            period: "full_game",
          },
        },
        "basketball_ncaab",
        startISO,
        { home: 52, away: 54 },
        { home: 0.51136, away: 0.48864 },
      ),
    ).toBeNull();
  });

  it("EventCard183A renders Proj. 111/111 on toss-up and Chance-only on Rule-2 conflict", () => {
    const tossUpEvent = {
      id: 15350555,
      sport: "basketball_nba",
      sport_name: "NBA",
      home_team: "Orlando Magic",
      away_team: "Philadelphia 76ers",
      commence_time: futureISO,
      status: "scheduled",
      home_score: null,
      away_score: null,
      hero_probability: 0.505,
      hero_probability_away: 0.495,
      hero_probability_source: "blend",
      current_odds: {
        home_probability: 0.505,
        away_probability: 0.495,
        projected_home_score: 110.6,
        projected_away_score: 111.1,
      },
    } as unknown as Event;

    const tossUpCard = buildUnifiedCardFromEvent(tossUpEvent);
    expect(String(tossUpCard.projected_away)).toBe("111");
    expect(String(tossUpCard.projected_home)).toBe("111");
    const tossUpMarkup = renderToStaticMarkup(
      <EventCard183A card={tossUpCard} surface="standard" />,
    );
    expect(tossUpMarkup).toContain("Proj.");
    expect(tossUpMarkup).toContain("111");

    const conflictData = {
      id: 15349440,
      sport: "americanfootball_ncaaf",
      sport_name: "NCAAF",
      home_team: "Florida Atlantic Owls",
      away_team: "South Florida Bulls",
      commence_time: futureISO,
      status: "scheduled",
      home_score: null,
      away_score: null,
      current_odds: {
        home_probability: 0.505,
        away_probability: 0.495,
        projected_home_score: 31.9,
        projected_away_score: 32.5,
      },
    } as unknown as FeedEventData;
    const feedItem = { type: "event", score: 40, data: conflictData } as unknown as FeedItem;
    const conflictCard = buildUnifiedCardFromFeed(feedItem, conflictData);
    expect(conflictCard.projected_away).toBeNull();
    expect(conflictCard.projected_home).toBeNull();
    const conflictMarkup = renderToStaticMarkup(
      <EventCard183A card={conflictCard} surface="standard" />,
    );
    expect(conflictMarkup).not.toContain("Proj.");
    expect(conflictMarkup).toContain("Chance");
  });

  it("EventPageHeadline199 suppresses Proj. column on Rule-2 conflict and prints level pair", () => {
    const baseEvent = {
      id: 15349440,
      sport: "americanfootball_ncaaf",
      sport_name: "NCAAF",
      home_team: "Florida Atlantic Owls",
      away_team: "South Florida Bulls",
      commence_time: futureISO,
      status: "scheduled",
      home_score: null,
      away_score: null,
      hero_probability: 0.505,
      hero_probability_away: 0.495,
      hero_probability_source: "blend",
      current_odds: {
        home_probability: 0.505,
        away_probability: 0.495,
        projected_home_score: 31.9,
        projected_away_score: 32.5,
      },
    } as unknown as EventDetailResponse;

    const conflictHeadline = resolveEventPageHeadline199({
      event: baseEvent,
      effectivelyLive: false,
      isLive: false,
      isFinished: false,
      isSuspended: false,
      venueVoided: false,
      venueSettledSentence: null,
      stoppageLabel: null,
      startClock: "clock",
      liveClockLabel: null,
      bestHomeScore: null,
      bestAwayScore: null,
      heroScorePairPresent: false,
      heroScoreIsStoppageFiller: false,
      projectedPairRaw: { home_score: 31.9, away_score: 32.5 },
      projectedPairAdmitted: true,
      homeProb: 0.505,
      servedAwayProb: 0.495,
      homePct: 51,
      servedAwayPct: 49,
      probSourceLabel: "Blend",
      tenthsOptIn: false,
      settledWinnerSide: null,
    });
    expect(conflictHeadline.columns.find((c) => c.role === "projected")?.header).toBe("");

    const tossUpHeadline = resolveEventPageHeadline199({
      event: { ...baseEvent, sport: "basketball_nba" },
      effectivelyLive: false,
      isLive: false,
      isFinished: false,
      isSuspended: false,
      venueVoided: false,
      venueSettledSentence: null,
      stoppageLabel: null,
      startClock: "clock",
      liveClockLabel: null,
      bestHomeScore: null,
      bestAwayScore: null,
      heroScorePairPresent: false,
      heroScoreIsStoppageFiller: false,
      projectedPairRaw: { home_score: 110.6, away_score: 111.1 },
      projectedPairAdmitted: true,
      homeProb: 0.505,
      servedAwayProb: 0.495,
      homePct: 51,
      servedAwayPct: 49,
      probSourceLabel: "Blend",
      tenthsOptIn: false,
      settledWinnerSide: null,
    });
    expect(tossUpHeadline.columns.find((c) => c.role === "projected")?.header).toBe("Proj.");
    expect(tossUpHeadline.rows[0]?.cells[0]).toBe("111");
    expect(tossUpHeadline.rows[1]?.cells[0]).toBe("111");
  });

  it("exports static 390px web look HTML when RENDER_WEB_12992_HTML_DIR is set", () => {
    const outDir = process.env.RENDER_WEB_12992_HTML_DIR;
    if (!outDir) return;
    // eslint-disable-next-line @typescript-eslint/no-var-requires
    const fs = require("fs") as typeof import("fs");
    // eslint-disable-next-line @typescript-eslint/no-var-requires
    const path = require("path") as typeof import("path");
    fs.mkdirSync(outDir, { recursive: true });

    const cssDir = path.join(process.cwd(), ".next/static/css");
    const cssFiles = fs.existsSync(cssDir)
      ? fs.readdirSync(cssDir).filter((f) => f.endsWith(".css"))
      : [];
    const cssText = cssFiles
      .map((f) => fs.readFileSync(path.join(cssDir, f), "utf8"))
      .join("\n");

    const sixersEvent = {
      id: 15350555,
      sport: "basketball_nba",
      sport_name: "NBA",
      home_team: "Orlando Magic",
      away_team: "Philadelphia 76ers",
      commence_time: "2026-11-20T00:00:00Z",
      status: "scheduled",
      home_score: null,
      away_score: null,
      home_team_data: {
        team_id: 19,
        slug: "orlando-magic-nba",
        primary_color: "#0077c0",
        secondary_color: "#c4ced4",
        record: "8-6",
        abbreviation: "ORL",
      },
      away_team_data: {
        team_id: 20,
        slug: "philadelphia-76ers-nba",
        primary_color: "#006bb6",
        secondary_color: "#ed174c",
        record: "7-6",
        abbreviation: "PHI",
      },
      hero_probability: 0.505,
      hero_probability_away: 0.495,
      hero_probability_source: "blend",
      current_odds: {
        home_probability: 0.505,
        away_probability: 0.495,
        away_rendered_percent: 49,
        home_rendered_percent: 51,
        projected_home_score: 110.6,
        projected_away_score: 111.1,
        bookmaker_count: 12,
      },
    } as unknown as Event;

    const lsuEvent = {
      id: 15175997,
      sport: "americanfootball_ncaaf",
      sport_name: "NCAAF",
      home_team: "Tennessee Volunteers",
      away_team: "LSU Tigers",
      commence_time: "2026-11-21T20:30:00Z",
      status: "scheduled",
      home_score: null,
      away_score: null,
      home_team_data: {
        team_id: 15937,
        slug: "tennessee-volunteers-ncaaf",
        primary_color: "#ff8200",
        secondary_color: "#ffffff",
        record: "8-2",
        abbreviation: "TENN",
      },
      away_team_data: {
        team_id: 9,
        slug: "lsu-tigers-ncaaf",
        primary_color: "#461d76",
        secondary_color: "#fdd023",
        record: "6-4",
        abbreviation: "LSU",
      },
      hero_probability: 0.4929,
      hero_probability_away: 0.5071,
      hero_probability_source: "blend",
      current_odds: {
        home_probability: 0.4929,
        away_probability: 0.5071,
        away_rendered_percent: 51,
        home_rendered_percent: 49,
        projected_home_score: 22.5,
        projected_away_score: 23.4,
        bookmaker_count: 10,
      },
    } as unknown as Event;

    const usfEvent = {
      id: 15349440,
      sport: "americanfootball_ncaaf",
      sport_name: "NCAAF",
      home_team: "Florida Atlantic Owls",
      away_team: "South Florida Bulls",
      commence_time: "2026-11-21T19:30:00Z",
      status: "scheduled",
      home_score: null,
      away_score: null,
      home_team_data: {
        team_id: 15300,
        slug: "florida-atlantic-owls-ncaaf",
        primary_color: "#003366",
        secondary_color: "#cc0000",
        record: "6-4",
        abbreviation: "FAU",
      },
      away_team_data: {
        team_id: 15294,
        slug: "south-florida-bulls-ncaaf",
        primary_color: "#006747",
        secondary_color: "#cfc493",
        record: "6-4",
        abbreviation: "USF",
      },
      hero_probability: 0.505,
      hero_probability_away: 0.495,
      hero_probability_source: "blend",
      current_odds: {
        home_probability: 0.505,
        away_probability: 0.495,
        away_rendered_percent: 49,
        home_rendered_percent: 51,
        projected_home_score: 31.9,
        projected_away_score: 32.5,
        bookmaker_count: 8,
      },
    } as unknown as Event;

    const tossUpBody = renderToStaticMarkup(
      <div className="min-h-fit w-[390px] bg-surface-primary p-4 space-y-3.5 font-sans">
        <div className="text-xs font-semibold text-text-secondary">
          240: A · Web toss-up level projected final (390 px)
        </div>
        <EventCard183A card={buildUnifiedCardFromEvent(sixersEvent)} surface="standard" />
        <EventCard183A card={buildUnifiedCardFromEvent(lsuEvent)} surface="standard" />
      </div>,
    );

    const rule2Body = renderToStaticMarkup(
      <div className="min-h-fit w-[390px] bg-surface-primary p-4 space-y-3.5 font-sans">
        <div className="text-xs font-semibold text-text-secondary">
          240: A · Web Rule 2 hides conflicting pair (390 px)
        </div>
        <EventCard183A card={buildUnifiedCardFromEvent(usfEvent)} surface="standard" />
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

    fs.writeFileSync(path.join(outDir, "web-tossup-default.html"), wrapHTML(tossUpBody, 16));
    fs.writeFileSync(path.join(outDir, "web-tossup-larger.html"), wrapHTML(tossUpBody, 20));
    fs.writeFileSync(path.join(outDir, "web-rule2-default.html"), wrapHTML(rule2Body, 16));
    fs.writeFileSync(path.join(outDir, "web-rule2-larger.html"), wrapHTML(rule2Body, 20));
  });
});
