/**
 * #12822 Website Guard — Whole percents before kickoff & zero headline/card cell truncation
 *
 * Per Fable's 4:50 PM PT rule on #12779:
 * 1. Before kickoff, `Chance` prints whole percents on every surface (`24%` / `76%`),
 *    even 1 minute before tip when `tenthsOptIn` is `true` and streaming readings arrive.
 *    During play, `Now` keeps tenths (`23.5%` / `76.5%`).
 * 2. No headline or card numeric cell ever truncates (`"…"` / `&hellip;` / `truncate` /
 *    `text-ellipsis`), and every column's `minWidth` fits the longest value it can print
 *    at its rendered font size, shrinking font size on dense multi-set columns rather than
 *    clipping.
 */

import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import EventPageHeadline199, {
  columnMinWidthCss199,
  columnMinWidthPx199,
  liveSummaryFontPx199,
  primaryHeadlineCellFontPx199,
  pxToRem199,
  secondaryHeadlineCellFontPx199,
  sharedCompetitorNameFontPx199,
} from "@/components/event/EventPageHeadline199";
import EventCard183A, { buildUnifiedCardFromEvent } from "@/components/EventCard183A";
import { resolveEventPageHeadline199 } from "@/lib/eventPageHeadline199";
import type { Event, EventDetailResponse } from "@/lib/types";

const ONE_MIN_BEFORE_TIP_NOW = Date.parse("2026-11-16T23:59:00Z");
const TIP_TIME = "2026-11-17T00:00:00Z";

function makeCelticsEvent(overrides: Partial<EventDetailResponse> = {}): EventDetailResponse {
  return {
    id: 1282201,
    external_id: "magic-celtics-12822",
    sport: "basketball_nba",
    sport_key: "basketball_nba",
    sport_name: "NBA",
    away_team: "Orlando Magic",
    home_team: "Boston Celtics",
    commence_time: TIP_TIME,
    status: "scheduled",
    away_score: null,
    home_score: null,
    hero_probability_source: "blend",
    away_team_data: {
      name: "Orlando Magic",
      abbreviation: "ORL",
      primary_color: "#0077C0",
      record: "6-7",
    },
    home_team_data: {
      name: "Boston Celtics",
      abbreviation: "BOS",
      primary_color: "#007A33",
      record: "10-3",
    },
    current_odds: {
      away_probability: 0.235,
      home_probability: 0.765,
      away_rendered_percent: 24,
      home_rendered_percent: 76,
      projected_away_score: 105.4,
      projected_home_score: 114.6,
      bookmaker_count: 10,
    },
    prematch_odds: {
      away_probability: 0.235,
      home_probability: 0.765,
      away_rendered_percent: 24,
      home_rendered_percent: 76,
    },
    ...overrides,
  } as EventDetailResponse;
}

function visibleTextOnly(html: string): string {
  let out = "";
  let inTag = false;
  for (let i = 0; i < html.length; i += 1) {
    const ch = html[i];
    if (ch === "<") {
      inTag = true;
      out += " ";
    } else if (ch === ">") {
      inTag = false;
      out += " ";
    } else if (!inTag) {
      out += ch;
    }
  }
  return out.replace(/\s+/g, " ").trim();
}

describe("#12822 — Whole percents before kickoff & zero numeric cell truncation on website", () => {
  it("prints whole percents (24% / 76%, never 23.5% / 76.5%) 1 minute before tip on both EventPageHeadline199 and EventCard183A, even with tenthsOptIn=true", () => {
    const event = makeCelticsEvent();
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
      liveClockLabel: null,
      bestHomeScore: null,
      bestAwayScore: null,
      heroScorePairPresent: false,
      heroScoreIsStoppageFiller: false,
      projectedPairRaw: { away_score: 105.4, home_score: 114.6 },
      projectedPairAdmitted: true,
      homeProb: 0.765,
      servedAwayProb: 0.235,
      homePct: 76,
      servedAwayPct: 24,
      probSourceLabel: "Bain Luck Blend",
      tenthsOptIn: true,
      settledWinnerSide: null,
      nowMs: ONE_MIN_BEFORE_TIP_NOW,
    });

    expect(model.phase).toBe("before");
    expect(model.rows.map((r) => r.cells)).toEqual([
      ["105", "24%"],
      ["115", "76%"],
    ]);

    const headlineHtml = renderToStaticMarkup(
      <EventPageHeadline199
        event={event}
        model={model}
        isPinned={false}
        pinDisabled={false}
        onPinToggle={() => {}}
      />,
    );
    const headlineVisible = visibleTextOnly(headlineHtml);
    expect(headlineVisible).toContain("24%");
    expect(headlineVisible).toContain("76%");
    expect(headlineVisible).not.toContain("23.5%");
    expect(headlineVisible).not.toContain("76.5%");
    expect(headlineVisible).not.toContain("…");
    expect(headlineHtml).not.toContain("&hellip;");

    const card = buildUnifiedCardFromEvent(event as unknown as Event);
    const cardHtml = renderToStaticMarkup(<EventCard183A card={card} surface="standard" />);
    const cardVisible = visibleTextOnly(cardHtml);
    expect(cardVisible).toContain("24%");
    expect(cardVisible).toContain("76%");
    expect(cardVisible).not.toContain("23.5%");
    expect(cardVisible).not.toContain("76.5%");
    expect(cardVisible).not.toContain("…");
  });

  it("prints tenths (23.5% / 76.5%) during play with zero ellipsis or truncation classes on any headline or card cell", () => {
    const liveEvent = makeCelticsEvent({
      status: "live",
      away_score: 138,
      home_score: 142,
      espn: { period: "OT", game_clock: "1:12" } as never,
    });
    const liveModel = resolveEventPageHeadline199({
      event: liveEvent,
      effectivelyLive: true,
      isLive: true,
      isFinished: false,
      isSuspended: false,
      venueVoided: false,
      venueSettledSentence: null,
      stoppageLabel: null,
      startClock: "clock",
      liveClockLabel: "OT 1:12",
      bestHomeScore: 142,
      bestAwayScore: 138,
      heroScorePairPresent: true,
      heroScoreIsStoppageFiller: false,
      projectedPairRaw: { away_score: 144, home_score: 148 },
      projectedPairAdmitted: true,
      homeProb: 0.765,
      servedAwayProb: 0.235,
      homePct: 76,
      servedAwayPct: 24,
      probSourceLabel: "Bain Luck Blend",
      tenthsOptIn: true,
      settledWinnerSide: null,
      nowMs: ONE_MIN_BEFORE_TIP_NOW + 7200_000,
    });

    const headlineHtml = renderToStaticMarkup(
      <EventPageHeadline199
        event={liveEvent}
        model={liveModel}
        isPinned={false}
        pinDisabled={false}
        onPinToggle={() => {}}
      />,
    );
    expect(headlineHtml).toContain("23.5%");
    expect(headlineHtml).toContain("76.5%");
    expect(headlineHtml).toContain("138");
    expect(headlineHtml).toContain("142");
    expect(headlineHtml).not.toContain("…");
    expect(headlineHtml).not.toContain("text-ellipsis");

    // Guard every numeric cell span: never carries `truncate` or `text-ellipsis`
    const cellSpans = headlineHtml.match(/<span[^>]*data-headline-cell="[^"]*"[^>]*>[\s\S]*?<\/span>/g) ?? [];
    expect(cellSpans.length).toBeGreaterThanOrEqual(6);
    for (const span of cellSpans) {
      expect(span).not.toContain("truncate");
      expect(span).not.toContain("text-ellipsis");
      expect(span).not.toContain("…");
    }

    const liveCard = buildUnifiedCardFromEvent(liveEvent as unknown as Event);
    const cardHtml = renderToStaticMarkup(<EventCard183A card={liveCard} surface="standard" />);
    expect(cardHtml).toContain("23.5%");
    expect(cardHtml).toContain("76.5%");
    expect(cardHtml).not.toContain("…");
    expect(cardHtml).not.toContain("text-ellipsis");
  });

  it("steps font size down and preserves positive horizontal clearance on worst-case 6-column live 5-set tennis and long pregame summaries", () => {
    for (const colCount of [2, 3, 4, 5, 6]) {
      const nowMinW = columnMinWidthPx199("now", "during", colCount);
      const nowFont = primaryHeadlineCellFontPx199(colCount);
      // Longest live cell is 5 glyphs ("98.5%" or ">99%"); tabular glyph advance ~0.58em
      expect(nowMinW).toBeGreaterThanOrEqual(5 * nowFont * 0.58);

      const scoreMinW = columnMinWidthPx199("score", "during", colCount);
      const secFont = secondaryHeadlineCellFontPx199(colCount);
      // Longest 3-digit NBA score ("148") is 3 tabular digits
      expect(scoreMinW).toBeGreaterThanOrEqual(3 * secFont * 0.6);
    }

    expect(liveSummaryFontPx199(32)).toBe(12);
    expect(liveSummaryFontPx199(44)).toBe(11);
    expect(liveSummaryFontPx199(52)).toBe(10);
  });

  it("renders Alex's 6:23 PM Magic 106 @ Celtics 99 Q4 3:16 (Now 90.3% / 9.7%) and NBA 3OT Timberwolves (148–145) with rem-scaled aligned columns that fit inside 320 px × 135% largest text", () => {
    const magicCelticsQ4 = makeCelticsEvent({
      status: "live",
      away_score: 106,
      home_score: 99,
      espn: { period: "4th Quarter", game_clock: "3:16" } as never,
    });
    const q4Model = resolveEventPageHeadline199({
      event: magicCelticsQ4,
      effectivelyLive: true,
      isLive: true,
      isFinished: false,
      isSuspended: false,
      venueVoided: false,
      venueSettledSentence: null,
      stoppageLabel: null,
      startClock: "clock",
      liveClockLabel: "Q4 3:16",
      bestHomeScore: 99,
      bestAwayScore: 106,
      heroScorePairPresent: true,
      heroScoreIsStoppageFiller: false,
      projectedPairRaw: { away_score: 112, home_score: 108 },
      projectedPairAdmitted: true,
      homeProb: 0.097,
      servedAwayProb: 0.903,
      homePct: 10,
      servedAwayPct: 90,
      probSourceLabel: "Bain Luck Blend",
      tenthsOptIn: true,
      settledWinnerSide: null,
      nowMs: ONE_MIN_BEFORE_TIP_NOW + 6000_000,
    });

    const html = renderToStaticMarkup(
      <EventPageHeadline199
        event={magicCelticsQ4}
        model={q4Model}
        isPinned={false}
        pinDisabled={false}
        onPinToggle={() => {}}
      />,
    );
    const visible = visibleTextOnly(html);
    expect(visible).toContain("Score");
    expect(visible).toContain("Proj.");
    expect(visible).toContain("Now");
    expect(visible).toContain("106");
    expect(visible).toContain("99");
    expect(visible).toContain("112");
    expect(visible).toContain("108");
    expect(visible).toContain("90.3%");
    expect(visible).toContain("9.7%");
    expect(visible).not.toContain("Sco…");
    expect(visible).not.toContain("1…");
    expect(visible).not.toContain("…");

    // Header and data cells share identical rem-aware minWidth CSS so columns stay aligned under Larger Text
    expect(pxToRem199(16)).toBe("1rem");
    expect(columnMinWidthCss199("now", "during", 3)).toBe("max(90px, 5.6063rem)");
    expect(columnMinWidthCss199("score", "during", 3)).toBe("max(38px, 2.3906rem)");

    // At 320 px narrowest phone width (248 px inner width) × 135% Largest Text (1rem = 21.6 px):
    const remAt135 = 21.6;
    const evalMaxCss = (css: string): number => {
      const m = css.match(/^max\((\d+(?:\.\d+)?)px,\s*(\d+(?:\.\d+)?)rem\)$/);
      if (m) return Math.max(parseFloat(m[1]), parseFloat(m[2]) * remAt135);
      return parseFloat(css);
    };
    const nba3ColWidthAt135 =
      evalMaxCss(columnMinWidthCss199("score", "during", 3)) +
      8 +
      evalMaxCss(columnMinWidthCss199("projected", "during", 3)) +
      8 +
      evalMaxCss(columnMinWidthCss199("now", "during", 3));
    expect(nba3ColWidthAt135).toBeLessThanOrEqual(248);

    const tennis7ColWidthAt135 =
      5 * evalMaxCss(columnMinWidthCss199("setScore", "during", 7)) +
      evalMaxCss(columnMinWidthCss199("gamePoints", "during", 7)) +
      6 * 4 +
      evalMaxCss(columnMinWidthCss199("now", "during", 7));
    expect(tennis7ColWidthAt135).toBeLessThanOrEqual(248);

    // Timberwolves (12 chars) steps down to 14 px on 3-column live NBA so full name fits at 390 px
    expect(
      sharedCompetitorNameFontPx199(
        [
          { shortName: "Timberwolves" } as never,
          { shortName: "Thunder" } as never,
        ],
        3,
      ),
    ).toBe(14);
  });
});
