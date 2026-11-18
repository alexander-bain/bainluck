/**
 * Item 6 (Mon Nov 16) — Website Wording Guard in CI (Tests Only)
 *
 * Fails CI if any website card face regresses to printing:
 *   1. `"opening"` or `"opened"` for pregame (`Opened 58%`, `58% opening`, `Opening odds`)
 *   2. `"stale"` (`Stale`, `stale price`, `stale odds`)
 *   3. `"checked"` for an age (`Checked 14m ago`, `Last checked`)
 *   4. A venue name on a card's face — either a market venue badge (`Kalshi`,
 *      `Polymarket`, `DraftKings`, `FanDuel`, `BetMGM`, `Caesars`, `DataGolf`)
 *      or a stadium/arena venue (`Ford Field`, `Madison Square Garden`,
 *      `Emirates Stadium`).
 */

import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import EventCard from "@/components/EventCard";
import EventCard183A, { buildUnifiedCardFromEvent } from "@/components/EventCard183A";
import FeedCard from "@/components/FeedCard";
import FuturesCard from "@/components/FuturesCard";
import LeagueBinaryBoard from "@/components/LeagueBinaryBoard";
import { RecentGameCard, UpcomingGameCard } from "@/components/TeamGameCards";
import { EventCard as DiscoverEventCard } from "@/components/discover/EventCard";
import { FuturesCard as DiscoverFuturesCard } from "@/components/discover/FuturesCard";
import { MarketRow as EconMarketRow } from "@/components/economics/atoms";
import { SideMarketCard } from "@/components/politics/SideMarketCard";
import { CrossSourceBadge, SourceBadge as WeatherSourceBadge } from "@/components/weather/SourceBadge";
import { formatAsOfStamp } from "@/lib/asOfStamp";
import { rangeMovementCaption } from "@/lib/futuresDetailDisplay";
import type { PoliticsMarketRow, TeamGameBrief } from "@/lib/api";
import type { LeagueBinary } from "@/lib/leagueCards";
import type { Event, FeedEventData, FeedFuturesData, FeedItem, FuturesMarket } from "@/lib/types";

jest.mock("@/components/Analytics", () => ({
  __esModule: true,
  useAnalyticsContext: () => ({ track: jest.fn() }),
}));

jest.mock("next/navigation", () => ({
  __esModule: true,
  useRouter: () => ({ push: jest.fn(), replace: jest.fn(), prefetch: jest.fn() }),
  usePathname: () => "/",
  useSearchParams: () => new URLSearchParams(),
}));

/** Extract visible text plus accessible label/title text from rendered HTML without regex tag filters. */
export function extractCardFaceReadableText(html: string): string {
  const attrs: string[] = [];
  const attrRe = /\b(?:aria-label|title)="([^"]*)"/gi;
  let match: RegExpExecArray | null;
  while ((match = attrRe.exec(html)) !== null) {
    if (match[1]) attrs.push(match[1]);
  }
  let out = "";
  let insideTag = false;
  for (let i = 0; i < html.length; i += 1) {
    const ch = html[i];
    if (ch === "<") {
      insideTag = true;
      out += " ";
    } else if (ch === ">") {
      insideTag = false;
      out += " ";
    } else if (!insideTag) {
      out += ch;
    }
  }
  const visible = out
    .replaceAll("&nbsp;", " ")
    .replaceAll("&middot;", "·")
    .replaceAll("&amp;", "&")
    .replace(/\s+/g, " ")
    .trim();
  return [visible, ...attrs].join(" | ");
}

const PREGAME_OPENING_RE = /\bopen(?:ed|ing)\b/i;
const STALE_WORD_RE = /\bstale\b/i;
const CHECKED_AGE_RE = /\bchecked\b/i;
const PTS_ABBREV_RE = /[+-]?\d+(?:\.\d+)?\s*pts?\b|\bpts\b/;
const MARKET_VENUE_FACE_RE =
  /\b(?:Kalshi|Polymarket|DraftKings|FanDuel|BetMGM|Caesars|PointsBet|BetRivers|DataGolf|Cross-source)\b/i;
const STADIUM_VENUE_SPECIMENS = [
  "Ford Field",
  "Madison Square Garden",
  "Emirates Stadium",
  "Arrowhead Stadium",
];

export interface CardWordingViolation {
  rule:
    | "opening_for_pregame"
    | "stale"
    | "checked_for_age"
    | "venue_on_card_face"
    | "pts_abbreviation";
  detail: string;
}

export function detectCardFaceWordingViolations(html: string): CardWordingViolation[] {
  const readable = extractCardFaceReadableText(html);
  const violations: CardWordingViolation[] = [];

  const openingMatch = readable.match(PREGAME_OPENING_RE);
  if (openingMatch) {
    violations.push({
      rule: "opening_for_pregame",
      detail: `matched "${openingMatch[0]}" in "${readable}"`,
    });
  }

  const staleMatch = readable.match(STALE_WORD_RE);
  if (staleMatch) {
    violations.push({
      rule: "stale",
      detail: `matched "${staleMatch[0]}" in "${readable}"`,
    });
  }

  const checkedMatch = readable.match(CHECKED_AGE_RE);
  if (checkedMatch) {
    violations.push({
      rule: "checked_for_age",
      detail: `matched "${checkedMatch[0]}" in "${readable}"`,
    });
  }

  const ptsMatch = readable.match(PTS_ABBREV_RE);
  if (ptsMatch) {
    violations.push({
      rule: "pts_abbreviation",
      detail: `matched "${ptsMatch[0]}" in "${readable}"`,
    });
  }

  const marketVenueMatch = readable.match(MARKET_VENUE_FACE_RE);
  if (marketVenueMatch) {
    violations.push({
      rule: "venue_on_card_face",
      detail: `matched market venue "${marketVenueMatch[0]}" in "${readable}"`,
    });
  }

  for (const stadium of STADIUM_VENUE_SPECIMENS) {
    if (readable.toLowerCase().includes(stadium.toLowerCase())) {
      violations.push({
        rule: "venue_on_card_face",
        detail: `matched stadium venue "${stadium}" in "${readable}"`,
      });
    }
  }

  return violations;
}

function assertCleanCardFace(surface: string, html: string): void {
  const violations = detectCardFaceWordingViolations(html);
  if (violations.length > 0) {
    throw new Error(
      `[${surface}] Card-face wording guard failed:\n` +
        violations.map((v) => `  - (${v.rule}) ${v.detail}`).join("\n"),
    );
  }
}

const FUTURE_START = "2026-11-20T20:00:00Z";
const LIVE_START = "2026-11-16T16:00:00Z";
const PAST_START = "2026-11-15T20:00:00Z";
const AGED_STAMP = "2026-11-02T12:00:00Z"; // 14 days old -> must render "As of Nov 2", never "stale", "checked", or "14d ago"

function makeEventSpecimen(overrides: Record<string, unknown> = {}): Event {
  return {
    id: 50101,
    external_id: "guard-50101",
    sport: "americanfootball_nfl",
    sport_key: "americanfootball_nfl",
    sport_name: "NFL",
    home_team: "Detroit Lions",
    away_team: "Green Bay Packers",
    commence_time: FUTURE_START,
    status: "scheduled",
    home_score: null,
    away_score: null,
    venue: "Ford Field",
    espn_data: {
      venue: "Ford Field",
      period: 3,
      game_clock: "6:12",
    },
    current_odds: {
      home_probability: 0.58,
      away_probability: 0.42,
      home_rendered_percent: 58,
      away_rendered_percent: 42,
      projected_home_score: 27.1,
      projected_away_score: 23.4,
      updated_at: AGED_STAMP,
    },
    // Both `opening_odds` and `prematch_odds` present to catch any regression to "Opened" / "opening"
    opening_odds: {
      home_probability: 0.52,
      away_probability: 0.48,
    },
    prematch_odds: {
      home_probability: 0.58,
      away_probability: 0.42,
      home_rendered_percent: 58,
      away_rendered_percent: 42,
      source: "kalshi",
    },
    win_probability_sources: {
      kalshi: { value: 0.58, display_name: "Kalshi", type: "market", updated_at: AGED_STAMP },
      polymarket: { value: 0.57, display_name: "Polymarket", type: "market", updated_at: AGED_STAMP },
    },
    ...overrides,
  } as unknown as Event;
}

describe("Website CI Wording Guard — card faces never print opening/opened, stale, checked, or venue names", () => {
  it("self-tests: detector fires on every forbidden class (opening/opened, stale, checked, market venue, stadium venue)", () => {
    expect(detectCardFaceWordingViolations("<div>Opened 58%</div>").map((v) => v.rule)).toContain(
      "opening_for_pregame",
    );
    expect(
      detectCardFaceWordingViolations("<div>Lions 58% opening</div>").map((v) => v.rule),
    ).toContain("opening_for_pregame");
    expect(detectCardFaceWordingViolations("<div>Stale price</div>").map((v) => v.rule)).toContain(
      "stale",
    );
    expect(
      detectCardFaceWordingViolations('<span title="Checked 14m ago">58%</span>').map(
        (v) => v.rule,
      ),
    ).toContain("checked_for_age");
    expect(
      detectCardFaceWordingViolations("<div><span>Kalshi</span> 58%</div>").map((v) => v.rule),
    ).toContain("venue_on_card_face");
    expect(
      detectCardFaceWordingViolations("<div><span>Polymarket</span> 42%</div>").map((v) => v.rule),
    ).toContain("venue_on_card_face");
    expect(
      detectCardFaceWordingViolations("<div>Packers at Lions · Ford Field</div>").map(
        (v) => v.rule,
      ),
    ).toContain("venue_on_card_face");
    expect(
      detectCardFaceWordingViolations("<div>San Antonio Spurs up 2 pts since Nov 9.</div>").map(
        (v) => v.rule,
      ),
    ).toContain("pts_abbreviation");

    // Legitimate copy ("Pregame", "As of Nov 2", "US Open", "up 2 points") passes cleanly
    expect(
      detectCardFaceWordingViolations(
        "<div>US Open · Pregame Lions 58% · up 2 points · As of Nov 2</div>",
      ),
    ).toEqual([]);
  });

  it("EventCard183A (before, during, after, Discover & standard) passes all four wording guards", () => {
    for (const surface of ["discover", "standard"] as const) {
      const pre = buildUnifiedCardFromEvent(makeEventSpecimen({ status: "scheduled" }));
      const live = buildUnifiedCardFromEvent(
        makeEventSpecimen({
          status: "live",
          commence_time: LIVE_START,
          home_score: 17,
          away_score: 14,
        }),
      );
      const final = buildUnifiedCardFromEvent(
        makeEventSpecimen({
          status: "completed",
          commence_time: PAST_START,
          ended_at: PAST_START,
          home_score: 27,
          away_score: 20,
        }),
      );

      assertCleanCardFace(
        `EventCard183A/${surface}/before`,
        renderToStaticMarkup(<EventCard183A card={pre} surface={surface} />),
      );
      assertCleanCardFace(
        `EventCard183A/${surface}/during`,
        renderToStaticMarkup(<EventCard183A card={live} surface={surface} />),
      );
      assertCleanCardFace(
        `EventCard183A/${surface}/after`,
        renderToStaticMarkup(<EventCard183A card={final} surface={surface} />),
      );
    }
  });

  it("EventCard & DiscoverEventCard (with 183-A enabled) and FeedCard game/futures items pass all four wording guards", () => {
    const prevFlag = process.env.NEXT_PUBLIC_GAME_CARD_183A;
    process.env.NEXT_PUBLIC_GAME_CARD_183A = "true";
    try {
      const pre = makeEventSpecimen({ status: "scheduled" });
      const live = makeEventSpecimen({
        status: "live",
        commence_time: LIVE_START,
        home_score: 17,
        away_score: 14,
      });
      const final = makeEventSpecimen({
        status: "completed",
        commence_time: PAST_START,
        ended_at: PAST_START,
        home_score: 27,
        away_score: 20,
      });

      for (const [label, ev] of [
        ["before", pre],
        ["during", live],
        ["after", final],
      ] as const) {
        assertCleanCardFace(`EventCard/${label}`, renderToStaticMarkup(<EventCard event={ev} />));
      }

      const feedPre: FeedItem = {
        type: "event",
        id: "ev-pre",
        score: 90,
        reason: null,
        data: pre as unknown as FeedEventData,
      } as unknown as FeedItem;
      const feedLive: FeedItem = {
        type: "event",
        id: "ev-live",
        score: 95,
        reason: null,
        data: live as unknown as FeedEventData,
      } as unknown as FeedItem;
      const feedFinal: FeedItem = {
        type: "event",
        id: "ev-final",
        score: 88,
        reason: null,
        data: final as unknown as FeedEventData,
      } as unknown as FeedItem;

      const noop = () => undefined;
      assertCleanCardFace(
        "DiscoverEventCard/before",
        renderToStaticMarkup(
          <DiscoverEventCard
            item={feedPre}
            data={feedPre.data as FeedEventData}
            liked={false}
            setLiked={noop}
            onDismiss={noop}
            trending={false}
          />,
        ),
      );
      assertCleanCardFace(
        "DiscoverEventCard/during",
        renderToStaticMarkup(
          <DiscoverEventCard
            item={feedLive}
            data={feedLive.data as FeedEventData}
            liked={false}
            setLiked={noop}
            onDismiss={noop}
            trending={false}
          />,
        ),
      );
      assertCleanCardFace(
        "DiscoverEventCard/after",
        renderToStaticMarkup(
          <DiscoverEventCard
            item={feedFinal}
            data={feedFinal.data as FeedEventData}
            liked={false}
            setLiked={noop}
            onDismiss={noop}
            trending={false}
          />,
        ),
      );
    } finally {
      if (prevFlag === undefined) {
        delete process.env.NEXT_PUBLIC_GAME_CARD_183A;
      } else {
        process.env.NEXT_PUBLIC_GAME_CARD_183A = prevFlag;
      }
    }
  });

  it("FuturesCard, DiscoverFuturesCard, and FeedCard futures items pass all four wording guards (including aged timestamps & Kalshi/Polymarket sources)", () => {
    const futuresMarket = {
      id: 88001,
      name: "NBA Championship Winner 2027",
      sport: "basketball_nba",
      llm_sport_category: "basketball",
      market_type: "championship",
      source: "kalshi",
      sources: ["kalshi", "polymarket"],
      status: "open",
      updated_at: AGED_STAMP,
      resolution_date: "2027-06-20T00:00:00Z",
      outcomes: [
        {
          id: 1,
          name: "Boston Celtics",
          outcome_name: "Boston Celtics",
          probability: 0.24,
          current_probability: 0.24,
          opening_probability: 0.2,
          probability_change_24h: 0.02,
          updated_at: AGED_STAMP,
        },
        {
          id: 2,
          name: "Oklahoma City Thunder",
          outcome_name: "Oklahoma City Thunder",
          probability: 0.21,
          current_probability: 0.21,
          opening_probability: 0.19,
          probability_change_24h: -0.01,
          updated_at: AGED_STAMP,
        },
      ],
    } as unknown as FuturesMarket;

    assertCleanCardFace(
      "FuturesCard",
      renderToStaticMarkup(<FuturesCard market={futuresMarket} />),
    );

    const feedFuturesData = {
      id: 88001,
      name: "NBA Championship Winner 2027",
      sport: "basketball_nba",
      llm_sport_category: "basketball",
      market_type: "championship",
      source: "polymarket",
      sources: ["kalshi", "polymarket"],
      updated_at: AGED_STAMP,
      resolution_date: "2027-06-20T00:00:00Z",
      outcome_count: 2,
      top_outcomes: [
        { id: 1, name: "Boston Celtics", probability: 0.24, movement: 0.02 },
        { id: 2, name: "Oklahoma City Thunder", probability: 0.21, movement: -0.01 },
      ],
    } as unknown as FeedFuturesData;

    const feedFuturesItem = {
      type: "futures",
      id: "futures-88001",
      score: 85,
      reason: null,
      data: feedFuturesData,
    } as unknown as FeedItem;

    assertCleanCardFace(
      "FeedCard/futures",
      renderToStaticMarkup(<FeedCard item={feedFuturesItem} />),
    );
    const noop = () => undefined;
    assertCleanCardFace(
      "DiscoverFuturesCard",
      renderToStaticMarkup(
        <DiscoverFuturesCard
          item={feedFuturesItem}
          data={feedFuturesData}
          liked={false}
          setLiked={noop}
          onDismiss={noop}
          trending={false}
        />,
      ),
    );
  });

  it("TeamGameCards, LeagueBinaryBoard, Economics MarketRow, Politics SideMarketCard, Weather SourceBadge, and formatAsOfStamp pass all four wording guards", () => {
    const upcomingGame: TeamGameBrief = {
      id: 6601,
      home_team: "New York Knicks",
      away_team: "Boston Celtics",
      opponent: "Boston Celtics",
      is_home: true,
      commence_time: FUTURE_START,
      status: "scheduled",
      home_score: null,
      away_score: null,
      win_probability: 0.54,
      pregame_win_probability: 0.52,
      sport_key: "basketball_nba",
    };
    const recentGame: TeamGameBrief = {
      ...upcomingGame,
      id: 6602,
      commence_time: PAST_START,
      completed_at: PAST_START,
      status: "completed",
      home_score: 112,
      away_score: 108,
      win_probability: 1,
    };

    assertCleanCardFace(
      "UpcomingGameCard",
      renderToStaticMarkup(
        <UpcomingGameCard game={upcomingGame} teamName="New York Knicks" teamColor="#006BB6" />,
      ),
    );
    assertCleanCardFace(
      "RecentGameCard",
      renderToStaticMarkup(<RecentGameCard game={recentGame} />),
    );

    const binaryRows: LeagueBinary[] = [
      {
        market: {
          id: 77001,
          name: "Will Detroit Lions make the playoffs?",
          market_type: "yes_no",
          source: "kalshi",
          outcome_count: 2,
          top_outcomes: [
            { name: "Yes", probability: 0.78, movement_24h: 0.03 },
            { name: "No", probability: 0.22, movement_24h: -0.03 },
          ],
        },
        answer: {
          outcome: "Yes",
          probability: 0.78,
          movement24h: 0.03,
        },
      } as unknown as LeagueBinary,
    ];
    assertCleanCardFace(
      "LeagueBinaryBoard",
      renderToStaticMarkup(<LeagueBinaryBoard binaries={binaryRows} />),
    );

    assertCleanCardFace(
      "EconMarketRow",
      renderToStaticMarkup(
        <EconMarketRow
          q="US recession before 2027?"
          prob={28}
          src="kalshi"
          delta={-2}
          leader="Yes"
          marketId={99001}
        />,
      ),
    );

    const politicsMarket = {
      market_id: 99002,
      q: "Next UK general election year?",
      prob: 64,
      src: "polymarket",
      outcome_count: 3,
      top_outcomes: [{ name: "2029", prob: 64 }],
    } as unknown as PoliticsMarketRow;
    assertCleanCardFace(
      "PoliticsSideMarketCard",
      renderToStaticMarkup(<SideMarketCard market={politicsMarket} />),
    );

    assertCleanCardFace(
      "WeatherSourceBadge",
      renderToStaticMarkup(
        <div>
          <WeatherSourceBadge src="kalshi" />
          <WeatherSourceBadge src="polymarket" />
          <CrossSourceBadge />
        </div>,
      ),
    );

    const ageStamp = formatAsOfStamp(AGED_STAMP, new Date("2026-11-16T17:00:00Z"));
    expect(ageStamp).toBe("As of Nov 2");
    assertCleanCardFace("formatAsOfStamp", `<span>${ageStamp}</span>`);

    const trendCaption = rangeMovementCaption(
      { id: 1, name: "San Antonio Spurs", probability: 0.24 },
      [
        {
          outcome_id: 1,
          history: [
            { timestamp: "2026-11-09T00:00:00Z", probability: 0.22 },
            { timestamp: "2026-11-16T00:00:00Z", probability: 0.24 },
          ],
        },
      ],
      null,
      "UTC",
    );
    expect(trendCaption).toBe("San Antonio Spurs up 2 points since Nov 9.");
    assertCleanCardFace("rangeMovementCaption", `<p>${trendCaption}</p>`);
  });
});
