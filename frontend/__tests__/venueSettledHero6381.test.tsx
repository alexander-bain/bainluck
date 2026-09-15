// #6381 — THE HERO STOPS DENYING A RESULT THE VENUE ALREADY GAVE US.
//
// ── WHAT THE READER SAW ──────────────────────────────────────────────────────
//
// `/events/15310639` (Liverpool FC v Fulham FC, `tier: 1`, `status='scheduled'`,
// both scores null), production, 2026-09-15. The hero, top of the page:
//
//     No result reported            Sep 12, 2026 · 7:30 AM PDT
//
// One screen below, on the SAME payload, its own markets:
//
//     Liverpool FC vs Fulham FC: Correct Score        Draw 0-0     Won
//     Liverpool FC vs Fulham FC: First Team to Score  No Goal      Won
//
// graded `is_winner=true, resolution_source='api_settlement'` three days
// earlier. The page denied having a result while drawing the result.
//
// ── THE PAIR ─────────────────────────────────────────────────────────────────
//
// Producer half (live lane, PR #6410): `/api/events/{id}` gains `venue_settled`
// and `venue_settled_result` on exactly the rows about to print the sentence.
// This is the consumer half: the words on the page.
//
// ── WHAT MUST NOT MOVE, AND IS ASSERTED BELOW ────────────────────────────────
//
// `isSuspended` is the page's ONE `hasNoReportedResult` answer (#4015) and four
// other things read it: the suppressed countdown (#3211), the suppressed
// projected final (#5257), the map's past-tense marks (#5206) and the withdrawn
// age stamp (#5459). Every one of them is still RIGHT about a venue-settled
// match — there is nothing left to forecast and no update to promise — so the
// flag does not move and the projection control below proves it did not.
//
// The other failure mode is a fix that fires on rows it was never served for.
// Until PR #6410 is live EVERY payload on production carries neither key, so
// "absent leaves the sentence alone" is not a tail case here: it is the whole
// site, and it has its own test.

import React from "react";
import { renderToStaticMarkup } from "react-dom/server";

import {
  VENUE_SETTLED_DESCRIPTION,
  VENUE_SETTLED_LABEL,
  SUSPENDED_DESCRIPTION,
  SUSPENDED_LABEL,
  venueSettledSummary,
} from "@/lib/eventState";

const DENIAL = SUSPENDED_LABEL; // "No result reported"
const PROJECTION = "Projected final";

/** The Liverpool–Fulham specimen. Soccer declares `hasDerivedSpread`, which is
 *  what makes the projection control below reachable at all — on a tennis
 *  fixture that branch is gated off by the sport and could prove nothing. */
function event(overrides: Record<string, unknown> = {}) {
  return {
    id: 15310639,
    sport_key: "soccer_epl",
    sport: "soccer_epl",
    sport_title: "Premier League",
    home_team: "Liverpool FC",
    away_team: "Fulham FC",
    home_score: null,
    away_score: null,
    status: "scheduled",
    // Well past its own kickoff, which is what `startedWithoutResult` reads.
    commence_time: "2026-09-12T14:30:00+00:00",
    win_probability_sources: {},
    ...overrides,
  };
}

const HISTORY = {
  aggregate_line: [],
  pm_spread_data: {
    projected_final: { home_score: 2.4, away_score: 1.1 },
  },
};

let eventPayload: unknown;
let historyPayload: unknown;

jest.mock("swr", () => ({
  __esModule: true,
  default: (key: unknown) => {
    const k = Array.isArray(key) ? key[0] : null;
    const data =
      k === "event" ? eventPayload : k === "history" ? historyPayload : undefined;
    return { data, error: undefined, isLoading: false, mutate: () => undefined };
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
  useLiveEventStream: () => ({ frame: null, connected: false }),
}));

jest.mock("next/navigation", () => ({
  __esModule: true,
  useRouter: () => ({ push: () => {}, replace: () => {}, prefetch: () => {} }),
  usePathname: () => "/events/15310639",
  useSearchParams: () => new URLSearchParams(),
  useParams: () => ({ id: "15310639" }),
}));

// eslint-disable-next-line @typescript-eslint/no-var-requires
const EventDetailPage = require("@/app/events/[id]/page").default;
// eslint-disable-next-line @typescript-eslint/no-var-requires
const { AnalyticsProvider } = require("@/components/Analytics");

function draw(): string {
  return renderToStaticMarkup(
    React.createElement(
      AnalyticsProvider,
      null,
      React.createElement(EventDetailPage, { params: { id: "15310639" } }),
    ),
  );
}

beforeEach(() => {
  historyPayload = HISTORY;
});

describe("#6381 the hero prints the venue's grade instead of denying it", () => {
  it("names the graded score on the issue's own specimen", () => {
    eventPayload = event({
      venue_settled: true,
      venue_settled_result: "Draw 0-0",
    });

    const html = draw();

    expect(html).toContain("Settled · Draw 0-0");
    expect(html).not.toContain(DENIAL);
  });

  it("does the same on a suspended row, which is the LARGER half of the class", () => {
    // Measured on production 2026-09-15: suspended 889, scheduled 426 (the
    // issue's own sample), live 8. A fix that landed only on the arm the issue
    // happened to name would ship to a third of its own defect.
    eventPayload = event({
      status: "suspended",
      venue_settled: true,
      venue_settled_result: "Brighton & Hove Albion wins 5-0",
    });

    const html = draw();

    // `renderToStaticMarkup` escapes the ampersand; the string the READER sees
    // is "Settled · Brighton & Hove Albion wins 5-0".
    expect(html).toContain("Settled · Brighton &amp; Hove Albion wins 5-0");
    expect(html).not.toContain(DENIAL);
  });

  it("says Settled and invents no score when only props graded", () => {
    // The tennis shape: 15304840 (Sabalenka–Townsend) holds 16 prop grades and
    // no score market, so the venue settled the event without ever quoting a
    // scoreline.
    eventPayload = event({
      sport_key: "tennis_wta",
      sport: "tennis_wta",
      home_team: "Aryna Sabalenka",
      away_team: "Taylor Townsend",
      venue_settled: true,
      venue_settled_result: null,
    });

    const html = draw();

    expect(html).toContain(VENUE_SETTLED_LABEL);
    expect(html).not.toContain(DENIAL);
    // 🔴 The whole point of the null arm: nothing may stand in for the score we
    // do not have. "no score" would read as 0-0 beside sibling states that
    // print real scorelines, and a dash would read as one.
    expect(html).not.toContain("Settled ·");
    expect(html).not.toMatch(/Settled[^<]*\d/);
  });

  it("swaps the tooltip too, so the sentence behind the badge is not the old one", () => {
    eventPayload = event({ venue_settled: true, venue_settled_result: "Draw 0-0" });
    expect(draw()).toContain(VENUE_SETTLED_DESCRIPTION);

    eventPayload = event({ venue_settled: false, venue_settled_result: null });
    expect(draw()).toContain(SUSPENDED_DESCRIPTION);
  });

  // ── controls: every row that is NOT venue-settled keeps what it had ────────

  it("leaves the sentence alone when the venue graded nothing", () => {
    eventPayload = event({ venue_settled: false, venue_settled_result: null });

    const html = draw();

    expect(html).toContain(DENIAL);
    expect(html).not.toContain(VENUE_SETTLED_LABEL);
  });

  it("leaves the sentence alone when the keys are absent — which is every row today", () => {
    // Out of scope, and the state the entire site is in until PR #6410 ships.
    // A consumer that read `undefined` as anything but "we never asked" would
    // have gone live as a regression on 1,471 pages.
    eventPayload = event();

    const html = draw();

    expect(html).toContain(DENIAL);
    expect(html).not.toContain(VENUE_SETTLED_LABEL);
  });

  it("still suppresses the projected final on a venue-settled match", () => {
    // #5257's suppression reads `isSuspended`, which this ship deliberately
    // does NOT move. If the fix had flipped the flag to change the words, this
    // page would have started forecasting a match the badge says is settled.
    eventPayload = event({
      venue_settled: true,
      venue_settled_result: "Draw 0-0",
    });

    expect(draw()).not.toContain(PROJECTION);
  });

  it("draws the page rather than failing to render it", () => {
    // The failure mode of a string swap is a thrown render, which would satisfy
    // every `not.toContain` above for the wrong reason.
    eventPayload = event({ venue_settled: true, venue_settled_result: "Draw 0-0" });

    const html = draw();

    expect(html).toContain("Liverpool");
    expect(html).toContain("Fulham");
    expect(html.length).toBeGreaterThan(2000);
  });
});

describe("#6381 venueSettledSummary", () => {
  it("returns null for every row the venue has not settled", () => {
    expect(venueSettledSummary(false, null)).toBeNull();
    expect(venueSettledSummary(undefined, undefined)).toBeNull();
    // 🔴 A graded score with `venue_settled` false is not a result: the boolean
    // is the claim and the string is its detail, never the other way round.
    expect(venueSettledSummary(false, "Draw 0-0")).toBeNull();
    expect(venueSettledSummary(null, "Draw 0-0")).toBeNull();
  });

  it("prints the badge alone when no score graded", () => {
    expect(venueSettledSummary(true, null)).toBe("Settled");
    expect(venueSettledSummary(true, undefined)).toBe("Settled");
    // An empty or whitespace-only name is the same absence wearing a string.
    expect(venueSettledSummary(true, "")).toBe("Settled");
    expect(venueSettledSummary(true, "   ")).toBe("Settled");
  });

  it("prints the outcome name VERBATIM, whatever shape the sport gives it", () => {
    // Soccer, tennis (sets), and a name carrying its own punctuation. The
    // producer refuses `1st Half Correct Score` by segment-exact market name;
    // nothing here parses, matches or reformats, so there is no second place
    // that judgement can drift.
    expect(venueSettledSummary(true, "Draw 0-0")).toBe("Settled · Draw 0-0");
    expect(venueSettledSummary(true, "Aryna Sabalenka wins 2-0")).toBe(
      "Settled · Aryna Sabalenka wins 2-0",
    );
    expect(venueSettledSummary(true, "Brighton & Hove Albion wins 5-0")).toBe(
      "Settled · Brighton & Hove Albion wins 5-0",
    );
  });

  it("never says Final", () => {
    // `completed`/`closed` mean something with standing said the match ended.
    // These rows still say otherwise, so the ladder's terminal word would be a
    // claim we cannot make — the same lie #3211 refuses, told in the direction
    // that sounds like good news.
    expect(venueSettledSummary(true, "Draw 0-0")).not.toMatch(/final/i);
    expect(venueSettledSummary(true, null)).not.toMatch(/final/i);
  });
});
