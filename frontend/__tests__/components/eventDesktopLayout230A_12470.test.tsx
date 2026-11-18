/**
 * Ruling 230: A (#12470) — Website Event Page Two-Column Layout from 1024 px (`lg:`)
 *
 * - Two columns start at `lg:` (1024 px, landscape iPad & desktop); portrait iPad
 *   (834 px) and phones stay one column (`no min-[820px]:` classes).
 * - Featured column (`event-featured-column`): Headline + Win Probability chart +
 *   Projected final points chart (or Score Differential fallback).
 * - Side column (`event-side-column`): Game stories, Margin/Points maps, Team scoring &
 *   period lines, The script / Player props, Special markets, and Related sections.
 * - Headline numbers (`Score`, `Proj.`, `Chance`/`Now`) sit beside team names (`lg:justify-start`)
 *   with large team-colour `Chance`/`Now` (`lg:!text-[34px] xl:!text-[38px]`) for `colCount <= 4`,
 *   while 5+-column tennis scoreboards stay right-justified.
 * - Nothing cuts off from 1024 px up: `MarketBrowser` wraps category pills when `searchable={false}`,
 *   `CompactMarketMap` stacks rail above ladder (`lg:grid-cols-1`) inside the side column, and
 *   `NFLEventCardDeck` sizes Card 1 inside the `>= 404 px` side column (`lg:w-[356px]`).
 */

import fs from "fs";
import path from "path";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import EventPageHeadline199 from "@/components/event/EventPageHeadline199";
import MarketBrowser from "@/components/event/MarketBrowser";
import CompactMarketMap from "@/components/event/CompactMarketMap";
import { resolveEventPageHeadline199 } from "@/lib/eventPageHeadline199";
import type { EventDetailResponse } from "@/lib/types";

jest.mock("next/navigation", () => ({
  __esModule: true,
  useRouter: () => ({ push: () => {}, replace: () => {}, prefetch: () => {} }),
  usePathname: () => "/events/15350164",
  useSearchParams: () => new URLSearchParams(),
}));

const FIXED_NOW_MS = Date.parse("2026-11-17T23:00:00Z");

function makeEvent(overrides: Partial<EventDetailResponse> = {}): EventDetailResponse {
  return {
    id: 15350164,
    external_id: "nba-15350164",
    sport: "basketball_nba",
    sport_key: "basketball_nba",
    sport_name: "NBA",
    away_team: "Portland Trail Blazers",
    home_team: "Minnesota Timberwolves",
    commence_time: "2026-11-18T01:00:00Z",
    status: "scheduled",
    away_score: null,
    home_score: null,
    away_team_data: {
      name: "Portland Trail Blazers",
      abbreviation: "POR",
      primary_color: "#E03A3E",
      record: "9-4",
    },
    home_team_data: {
      name: "Minnesota Timberwolves",
      abbreviation: "MIN",
      primary_color: "#0C2340",
      record: "10-4",
    },
    current_odds: {
      away_probability: 0.45,
      home_probability: 0.55,
      away_rendered_percent: 45,
      home_rendered_percent: 55,
      projected_away_score: 112.1,
      projected_home_score: 115.0,
    },
    bookmaker_odds: [],
    win_probability_sources: {},
    ...overrides,
  } as EventDetailResponse;
}

describe("Ruling 230: A (#12470) — Desktop Event Page 2-Column Layout from 1024 px", () => {
  test("EventPage shell uses lg: (1024 px) two-column grid (no 820 px portrait-iPad split) with Headline + 2 charts in featured column and maps/stories/props in side column", () => {
    const pageSrc = fs.readFileSync(
      path.join(process.cwd(), "app/events/[id]/page.tsx"),
      "utf8",
    );

    expect(pageSrc).not.toContain("min-[820px]");
    expect(pageSrc).toContain('data-testid="event-desktop-two-col-shell"');
    expect(pageSrc).toContain(
      "flex flex-col gap-3 lg:grid lg:grid-cols-[minmax(0,1.36fr)_minmax(404px,1fr)] xl:grid-cols-[minmax(0,1.52fr)_minmax(448px,1fr)]",
    );
    // Preserves exact < 1024 px single-column order (order-1 headline/odds -> order-2 game stories -> order-3 projected final -> order-4 maps/props)
    expect(pageSrc).toContain('className="max-lg:contents lg:flex lg:flex-col lg:gap-3 lg:min-w-0" data-testid="event-featured-column"');
    expect(pageSrc).toContain('className="max-lg:contents lg:flex lg:flex-col lg:gap-3 lg:min-w-0" data-testid="event-side-column"');
    expect(pageSrc).toContain('max-lg:order-1');
    expect(pageSrc).toContain('max-lg:order-2');
    expect(pageSrc).toContain('max-lg:order-3');
    expect(pageSrc).toContain('max-lg:order-4');

    const featuredIdx = pageSrc.indexOf('data-testid="event-featured-column"');
    const sideIdx = pageSrc.indexOf('data-testid="event-side-column"');
    const headlineIdx = pageSrc.indexOf("<EventPageHeadline199");
    const oddsChartIdx = pageSrc.indexOf("<OddsChart");
    const projFinalIdx = pageSrc.indexOf("{projectedFinalPointsModule}");
    const gameStoriesIdx = pageSrc.indexOf("<NFLEventCardDeck");
    const marketMapIdx = pageSrc.indexOf("<MarketMapSection");
    const scriptIdx = pageSrc.indexOf("<PropDivergenceRail");

    expect(featuredIdx).toBeGreaterThan(0);
    expect(sideIdx).toBeGreaterThan(featuredIdx);

    // Featured column holds Headline + Win Probability + Projected final points
    expect(headlineIdx).toBeGreaterThan(featuredIdx);
    expect(headlineIdx).toBeLessThan(sideIdx);
    expect(oddsChartIdx).toBeGreaterThan(featuredIdx);
    expect(oddsChartIdx).toBeLessThan(sideIdx);
    expect(projFinalIdx).toBeGreaterThan(featuredIdx);
    expect(projFinalIdx).toBeLessThan(sideIdx);

    // Side column holds Game stories + Margin/Points maps + Script/props
    expect(gameStoriesIdx).toBeGreaterThan(sideIdx);
    expect(marketMapIdx).toBeGreaterThan(sideIdx);
    expect(scriptIdx).toBeGreaterThan(sideIdx);
  });

  test("EventPageHeadline199 places Chance/Proj. beside team names at lg: (1024 px+) with large team-colour Chance and zero 820 px classes", () => {
    const event = makeEvent();
    const model = resolveEventPageHeadline199({
      event,
      effectivelyLive: false,
      isLive: false,
      isFinished: false,
      isSuspended: false,
      venueVoided: false,
      venueSettledSentence: null,
      stoppageLabel: null,
      startClock: "clock",
      pregameStateLabel: "In 2h",
      liveClockLabel: null,
      heroScorePairPresent: false,
      bestHomeScore: null,
      bestAwayScore: null,
      heroScoreIsStoppageFiller: false,
      projectedPairRaw: { home_score: 115, away_score: 112 },
      projectedPairAdmitted: true,
      homeProb: 0.55,
      servedAwayProb: 0.45,
      homePct: 55,
      servedAwayPct: 45,
      probSourceLabel: "Bain Luck blend",
      tenthsOptIn: false,
      settledWinnerSide: null,
      gameMarkets: null,
      nowMs: FIXED_NOW_MS,
    });

    const html = renderToStaticMarkup(
      <EventPageHeadline199
        event={event}
        model={model}
        displayIdentity={null}
        homeProbForDataAttr={0.55}
        isPinned={false}
        pinDisabled={false}
        onPinToggle={() => {}}
      />,
    );

    expect(html).not.toContain("min-[820px]");
    expect(html).toContain("lg:justify-start");
    expect(html).toContain(
      "lg:[&amp;_[data-headline-identity]]:w-[232px] xl:[&amp;_[data-headline-identity]]:w-[288px]",
    );
    expect(html).toContain("lg:!text-[34px] xl:!text-[38px]");
  });

  test("tennis set scoreboards keep right-justified layout without fixed team-block width", () => {
    const tennis = makeEvent({
      sport: "tennis_atp_french_open",
      sport_key: "tennis_atp_french_open",
      sport_name: "ATP",
      away_team: "Carlos Alcaraz",
      home_team: "Jannik Sinner",
      status: "live",
      commence_time: "2026-11-17T21:00:00Z",
      away_score: 2,
      home_score: 1,
      linescore: {
        sets: [
          [6, 4],
          [4, 6],
          [6, 3],
          [3, 4],
        ],
      } as EventDetailResponse["linescore"],
    });
    const model = resolveEventPageHeadline199({
      event: tennis,
      effectivelyLive: true,
      isLive: true,
      isFinished: false,
      isSuspended: false,
      venueVoided: false,
      venueSettledSentence: null,
      stoppageLabel: null,
      startClock: "clock",
      pregameStateLabel: null,
      liveClockLabel: "Set 4",
      heroScorePairPresent: true,
      bestHomeScore: 1,
      bestAwayScore: 2,
      heroScoreIsStoppageFiller: false,
      projectedPairRaw: null,
      projectedPairAdmitted: false,
      homeProb: 0.55,
      servedAwayProb: 0.45,
      homePct: 55,
      servedAwayPct: 45,
      probSourceLabel: "Bain Luck blend",
      tenthsOptIn: true,
      settledWinnerSide: null,
      gameMarkets: null,
      nowMs: FIXED_NOW_MS,
    });
    expect(model.columns.length).toBeGreaterThanOrEqual(5);

    const html = renderToStaticMarkup(
      <EventPageHeadline199
        event={tennis}
        model={model}
        displayIdentity={null}
        homeProbForDataAttr={0.55}
        isPinned={false}
        pinDisabled={false}
        onPinToggle={() => {}}
      />,
    );
    expect(html).not.toContain("lg:justify-start");
  });

  test("side-column surfaces prevent cut-off text and word-by-word wrapping from 1024 px up", () => {
    const browserHtml = renderToStaticMarkup(
      <MarketBrowser
        label="Game maps"
        searchable={false}
        items={[
          { key: "m1", group: "Margin map", search: "Margin map", content: <div>M1</div> },
          { key: "m2", group: "Points map", search: "Points map", content: <div>M2</div> },
          { key: "m3", group: "1st half margin", search: "1st half margin", content: <div>M3</div> },
          { key: "m4", group: "2nd half margin", search: "2nd half margin", content: <div>M4</div> },
        ]}
      />,
    );
    expect(browserHtml).toContain("overflow-x-auto pb-1 lg:basis-full lg:flex-wrap lg:gap-1.5 lg:overflow-visible lg:pb-0");

    const mapHtml = renderToStaticMarkup(
      <CompactMarketMap
        variant="margin"
        title="Margin map"
        subtitle="Expected margin distribution"
        headline="MIN 55%"
        rangeMin={-18}
        rangeMax={18}
        zeroPosition={0}
        density={[1, 2, 4, 8, 10, 8, 4, 2]}
        bandDrawsShape
        accentRgb="37,99,235"
        axisLabels={{ left: "POR by 18+", mid: "0", right: "MIN by 18+" }}
        markers={[{ key: "proj", label: "Projection", displayValue: "MIN by 2.5+", value: 2.5, type: "proj" }]}
        ladder={[
          { label: "POR by 1.5+", probability: 42, side: "left" },
          { label: "MIN by 1.5+", probability: 53, side: "right" },
          { label: "MIN by 2.5+", probability: 49, side: "right" },
        ]}
        status="pre"
      />,
    );
    expect(mapHtml).toContain("sm:grid-cols-2 lg:grid-cols-1");

    const deckSrc = fs.readFileSync(
      path.join(process.cwd(), "components/event/NFLEventCards.tsx"),
      "utf8",
    );
    expect(deckSrc).toContain(
      'cards.length > 1 ? "w-[86%] sm:w-[360px] lg:w-[356px] xl:w-[368px]" : "w-full sm:w-[420px] lg:w-full lg:max-w-[420px]"',
    );
  });
});
