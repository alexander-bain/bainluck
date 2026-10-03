// #4889 — a live event page shows ONE game clock.
//
// Production, Auburn at Tennessee `/events/15318034`, 2026-10-03 20:12:56–
// 20:13:21Z (shopper, 390px): the header badge read `0:42 - 1st Quarter` while
// the newest-play strip under the chart read `0:38 - 1st Quarter`. The header
// read the detail payload, the strip reads `/history`; PR #10361 put both reads
// on the same 32s cadence, which shrank the gap but could not close it — the two
// reads share a cadence, not a phase.
//
// The rule (the issue's): one clock, from the authority, everywhere on the page;
// where a surface cannot have the authority's clock it shows no clock rather
// than a second one. The history row carries the time it was observed and the
// detail clock carries none, so the header prints the strip's clock.
//
// Every arm below feeds the two sources DIFFERENT clocks. A fixture where they
// agree is green on the bug.
//
// The strip is the REAL mounted `GamePlayCard`, resting on the page's own
// `lastChartPoint` (`next/dynamic` is mocked to render it inline — it is
// `ssr: false`, so a static render would otherwise omit it). PR #10380's guard
// compared the header with a re-implementation of the chart's carry instead, and
// the independent review found the arm that broke: with no ESPN rows the header
// read win-prob Q2 5:10 while the real readout printed the detail's 5:31.

import React from "react";
import { renderToStaticMarkup } from "react-dom/server";

const MINUTE = 60 * 1000;

/** Offset FIRST, then serialise (gotcha #44). */
function agoIso(ms: number): string {
  return new Date(Date.now() - ms).toISOString();
}

type EspnRow = {
  timestamp: string;
  home_probability: number | null;
  away_probability: number | null;
  home_score: number | null;
  away_score: number | null;
  game_clock: string | null;
  period: string | null;
};

function espnRow(agoMs: number, period: string | null, clock: string | null): EspnRow {
  return {
    timestamp: agoIso(agoMs),
    home_probability: 0.65,
    away_probability: 0.35,
    home_score: 0,
    away_score: 0,
    game_clock: clock,
    period,
  };
}

/** A live NCAAF game in its first quarter, as the detail payload serves it. */
function event(espn: Record<string, unknown> | undefined, sport = "americanfootball_ncaaf") {
  return {
    id: 15318034,
    sport,
    sport_key: sport,
    sport_title: "NCAAF",
    home_team: "Tennessee Volunteers",
    away_team: "Auburn Tigers",
    home_score: 0,
    away_score: 0,
    status: "live",
    commence_time: agoIso(20 * MINUTE),
    hero_probability: 0.65,
    hero_probability_away: 0.35,
    hero_probability_source: "blend",
    espn,
  };
}

function history(espn_history: EspnRow[], win_prob_history?: Record<string, unknown[]>) {
  return { history: [], bookmaker_history: {}, aggregate_line: [], espn_history, win_prob_history };
}

jest.mock("next/dynamic", () => ({
  __esModule: true,
  default: (loader: () => unknown) => {
    if (!loader.toString().includes("GamePlayCard")) return () => null;
    // eslint-disable-next-line @typescript-eslint/no-var-requires
    return require("@/components/GamePlayCard").default;
  },
}));

let eventPayload: unknown;
let historyPayload: unknown;

jest.mock("swr", () => ({
  __esModule: true,
  default: (key: unknown) => {
    const isEvent = Array.isArray(key) && key[0] === "event";
    const isHistory = Array.isArray(key) && key[0] === "history";
    return {
      data: isEvent ? eventPayload : isHistory ? historyPayload : undefined,
      error: undefined,
      isLoading: false,
      mutate: () => undefined,
    };
  },
}));

jest.mock("@/hooks", () => ({
  ...jest.requireActual("@/hooks"),
  __esModule: true,
  usePageTracking: () => undefined,
  useScrollDepth: () => undefined,
  useEngagementTime: () => undefined,
  usePinnedEvents: () => ({
    isPinned: () => false,
    togglePin: () => undefined,
    isMaxReached: false,
  }),
}));

jest.mock("@/hooks/useLiveEventStream", () => ({
  __esModule: true,
  useLiveEventStream: () => ({ frame: null, connected: true, chartPoints: [], status: "open" }),
}));

jest.mock("next/navigation", () => ({
  __esModule: true,
  useRouter: () => ({ push: () => {}, replace: () => {}, prefetch: () => {} }),
  usePathname: () => "/events/15318034",
  useSearchParams: () => new URLSearchParams(),
  useParams: () => ({ id: "15318034" }),
}));

// eslint-disable-next-line @typescript-eslint/no-var-requires
const EventDetailPage = require("@/app/events/[id]/page").default;
// eslint-disable-next-line @typescript-eslint/no-var-requires
const { AnalyticsProvider } = require("@/components/Analytics");

function draw(espn: Record<string, unknown> | undefined, hist: unknown, sport?: string): string {
  eventPayload = event(espn, sport);
  historyPayload = hist;
  return renderToStaticMarkup(
    React.createElement(
      AnalyticsProvider,
      null,
      React.createElement(EventDetailPage, { params: { id: "15318034" } }),
    ),
  );
}

/** The header phase badge: the pulsing dot, then the label. */
const BADGE_RE = /bg-emerald-500 animate-pulse"><\/span>([^<]*)</g;

function headerClock(html: string): string {
  const all = Array.from(html.matchAll(BADGE_RE));
  // One live badge on the page — otherwise "the header" is ambiguous and every
  // assertion below could be reading the wrong span.
  expect(all).toHaveLength(1);
  return all[0][1];
}

/** The resting readout's badge — the real `GamePlayCard`'s period/clock span. */
const STRIP_RE = /bg-surface-secondary px-2 py-1 rounded">([^<]*)</g;

function stripBadge(html: string): string {
  const all = Array.from(html.matchAll(STRIP_RE));
  // The card is mounted, exactly once — a missing strip would make every
  // "header == strip" comparison below vacuous.
  expect(all).toHaveLength(1);
  return all[0][1];
}

/**
 * The header joins with " · ", the card with a space, and only the card marks a
 * carried field with `~` (the header has no age vocabulary). The period and
 * clock VALUES are what must match.
 */
function sameClock(header: string, strip: string): void {
  expect(header.split(" · ").join(" ")).toBe(strip.split("~").join(""));
}

describe("#4889 a live event page shows one game clock", () => {
  it("#6684 a live MLB page: history carries ESPN's constant 0:00, the header prints the inning and no clock", () => {
    // Production, ALDS Game 1 `/events/15322539`, 2026-10-03 22:59Z, v5455: the
    // header read `End 1st · 0:00`. The detail payload serves `game_clock: null`
    // for MLB, but every `/history` row carries `0:00`; PR #10380 moved the header
    // onto the history clock without the sport, so #6684's rule never ran there.
    const rows = [espnRow(2 * MINUTE, "End 1st", "0:00"), espnRow(1 * MINUTE, "End 1st", "0:00")];
    const html = draw({ period: "End 1st", game_clock: null }, history(rows), "baseball_mlb");

    expect(headerClock(html)).toBe("End 1st");
    sameClock(headerClock(html), stripBadge(html));
    expect(html).not.toContain("0:00");
  });

  it("the production specimen: detail says 0:42, history says 0:38 — the header prints the strip's 0:38", () => {
    const rows = [espnRow(3 * MINUTE, "0:52 - 1st Quarter", "0:52"), espnRow(1 * MINUTE, "0:38 - 1st Quarter", "0:38")];
    const html = draw({ period: "0:42 - 1st Quarter", game_clock: "0:42" }, history(rows));

    expect(headerClock(html)).toBe("0:38 - 1st Quarter");
    sameClock(headerClock(html), stripBadge(html));
    // The detail payload's clock is printed nowhere on the page.
    expect(html).not.toContain("0:42");
  });

  it("the other phase: detail already moved to 0:38, history still says 0:42 — still one clock, the strip's", () => {
    // Which read is fresher cannot be known: the detail clock carries no
    // observation time. What can be guaranteed is that the page never shows two.
    const rows = [espnRow(1 * MINUTE, "0:42 - 1st Quarter", "0:42")];
    const html = draw({ period: "0:38 - 1st Quarter", game_clock: "0:38" }, history(rows));

    expect(headerClock(html)).toBe("0:42 - 1st Quarter");
    sameClock(headerClock(html), stripBadge(html));
    expect(html).not.toContain("0:38");
  });

  it("a period boundary: history has reached Halftime while detail still reads the last clock of the half", () => {
    const rows = [espnRow(4 * MINUTE, "0:03 - 2nd Quarter", "0:03"), espnRow(1 * MINUTE, "Halftime", null)];
    const html = draw({ period: "0:03 - 2nd Quarter", game_clock: "0:03" }, history(rows));

    expect(headerClock(html)).toBe("Halftime");
    sameClock(headerClock(html), stripBadge(html));
  });

  it("a clock carried from a row older than the period is not printed as the current clock", () => {
    // The new quarter's row brought a period and no clock. The strip marks the
    // inherited 0:05 approximate (`~`); the header has no `~`, so it drops it
    // rather than show the old quarter's clock under the new quarter's name.
    const rows = [espnRow(4 * MINUTE, "2nd Quarter", "0:05"), espnRow(1 * MINUTE, "3rd Quarter", null)];
    const html = draw({ period: "2nd Quarter", game_clock: "0:05" }, history(rows));

    expect(headerClock(html)).toBe("3rd Quarter");
    // The real strip says the same period and marks its inherited clock as old.
    expect(stripBadge(html)).toBe("3rd Quarter ~0:05");
  });

  it("history holds no clock yet (quiet): the detail clock is the only clock on the page, so the header keeps it", () => {
    const rows = [espnRow(1 * MINUTE, null, null)];
    const quiet = draw({ period: "0:42 - 1st Quarter", game_clock: "0:42" }, history(rows));
    expect(headerClock(quiet)).toBe("0:42 - 1st Quarter");
    // The real strip falls back to the same event-row clock (#925), marked carried.
    expect(stripBadge(quiet)).toBe("~0:42 - 1st Quarter");
    sameClock(headerClock(quiet), stripBadge(quiet));
    // CONTROL: no history read at all — the pre-#4889 behaviour, unchanged.
    expect(headerClock(draw({ period: "0:42 - 1st Quarter", game_clock: "0:42" }, undefined))).toBe(
      "0:42 - 1st Quarter",
    );
  });

  it("the strip's clock fails the trust rules: the header says LIVE, never the detail's second clock", () => {
    // ESPN's pregame sentence shipped with "0.0" — the strip paints nothing
    // honest from it, and substituting the detail clock would be the second clock.
    const rows = [espnRow(1 * MINUTE, "Sat, October 3rd at 3:30 PM EDT", "0.0")];
    const html = draw({ period: "14:51 - 1st Quarter", game_clock: "14:51" }, history(rows));

    expect(headerClock(html)).toBe("LIVE");
    expect(stripBadge(html)).toBe("\u2014");
    expect(html).not.toContain("14:51");
  });

  it("with no ESPN rows, the win-prob game_state the strip falls back to is the header's clock too", () => {
    const winProb = {
      espn: [
        { timestamp: agoIso(1 * MINUTE), home_probability: 0.65, away_probability: 0.35, game_state: { period: "Q2", clock: "5:10" } },
      ],
    };
    const html = draw({ period: "5:31 - 2nd Quarter", game_clock: "5:31" }, history([], winProb));

    expect(headerClock(html)).toBe("Q2 · 5:10");
    // The independent review's counterexample: the REAL resting readout printed
    // the detail payload's 5:31 here while the header printed 5:10.
    expect(stripBadge(html)).toBe("Q2 5:10");
    sameClock(headerClock(html), stripBadge(html));
    expect(html).not.toContain("5:31");
  });
});
