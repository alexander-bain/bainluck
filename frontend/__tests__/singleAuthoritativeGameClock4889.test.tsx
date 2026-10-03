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

import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { parseISO } from "date-fns";
import { carryGameStateForward, stampObservedGameState, type CarriedGameStateRow } from "@/lib/chartGameState";
import { toMinuteKey } from "@/lib/chartTimeline";
import { trustedLiveClock } from "@/lib/gameTimeLabel";

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
function event(espn: Record<string, unknown> | undefined) {
  return {
    id: 15318034,
    sport: "americanfootball_ncaaf",
    sport_key: "americanfootball_ncaaf",
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

function draw(espn: Record<string, unknown> | undefined, hist: unknown): string {
  eventPayload = event(espn);
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

/**
 * What the strip under the chart prints at its live edge, computed by the
 * chart's own steps (`OddsChart` runs exactly these two over the same rows;
 * `GamePlayCard` paints the result through `trustedLiveClock`). Independent of
 * the page's code, so "header == strip" is a comparison, not a tautology.
 */
function stripLabel(espnHistory: EspnRow[]): string {
  const rows = new Map<string, CarriedGameStateRow>();
  for (const r of espnHistory) rows.set(toMinuteKey(r.timestamp), { timestamp: toMinuteKey(r.timestamp) });
  stampObservedGameState(rows, espnHistory, null);
  const sorted = Array.from(rows.values()).sort(
    (a, b) => parseISO(a.timestamp).getTime() - parseISO(b.timestamp).getTime(),
  );
  const edge = carryGameStateForward(sorted).slice(-1)[0];
  const t = trustedLiveClock(edge._period, edge._clock, "americanfootball_ncaaf");
  return [t.period, t.gameClock].filter(Boolean).join(" · ");
}

describe("#4889 a live event page shows one game clock", () => {
  it("the production specimen: detail says 0:42, history says 0:38 — the header prints the strip's 0:38", () => {
    const rows = [espnRow(3 * MINUTE, "0:52 - 1st Quarter", "0:52"), espnRow(1 * MINUTE, "0:38 - 1st Quarter", "0:38")];
    const html = draw({ period: "0:42 - 1st Quarter", game_clock: "0:42" }, history(rows));

    expect(headerClock(html)).toBe("0:38 - 1st Quarter");
    expect(headerClock(html)).toBe(stripLabel(rows));
    // The detail payload's clock is printed nowhere on the page.
    expect(html).not.toContain("0:42");
  });

  it("the other phase: detail already moved to 0:38, history still says 0:42 — still one clock, the strip's", () => {
    // Which read is fresher cannot be known: the detail clock carries no
    // observation time. What can be guaranteed is that the page never shows two.
    const rows = [espnRow(1 * MINUTE, "0:42 - 1st Quarter", "0:42")];
    const html = draw({ period: "0:38 - 1st Quarter", game_clock: "0:38" }, history(rows));

    expect(headerClock(html)).toBe("0:42 - 1st Quarter");
    expect(headerClock(html)).toBe(stripLabel(rows));
    expect(html).not.toContain("0:38");
  });

  it("a period boundary: history has reached Halftime while detail still reads the last clock of the half", () => {
    const rows = [espnRow(4 * MINUTE, "0:03 - 2nd Quarter", "0:03"), espnRow(1 * MINUTE, "Halftime", null)];
    const html = draw({ period: "0:03 - 2nd Quarter", game_clock: "0:03" }, history(rows));

    expect(headerClock(html)).toBe("Halftime");
    expect(headerClock(html)).toBe(stripLabel(rows));
  });

  it("a clock carried from a row older than the period is not printed as the current clock", () => {
    // The new quarter's row brought a period and no clock. The strip marks the
    // inherited 0:05 approximate (`~`); the header has no `~`, so it drops it
    // rather than show the old quarter's clock under the new quarter's name.
    const rows = [espnRow(4 * MINUTE, "2nd Quarter", "0:05"), espnRow(1 * MINUTE, "3rd Quarter", null)];
    const html = draw({ period: "2nd Quarter", game_clock: "0:05" }, history(rows));

    expect(headerClock(html)).toBe("3rd Quarter");
  });

  it("history holds no clock yet (quiet): the detail clock is the only clock on the page, so the header keeps it", () => {
    const rows = [espnRow(1 * MINUTE, null, null)];
    expect(headerClock(draw({ period: "0:42 - 1st Quarter", game_clock: "0:42" }, history(rows)))).toBe(
      "0:42 - 1st Quarter",
    );
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
    expect(html).not.toContain("5:31");
  });
});
