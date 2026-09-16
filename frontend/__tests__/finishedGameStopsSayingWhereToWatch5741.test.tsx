// #5741 — A FINISHED GAME STOPS TELLING THE READER WHERE TO WATCH IT.
//
// ── WHAT THE READER SAW ──────────────────────────────────────────────────────
//
// `/events/15312659` (Arizona Diamondbacks 2, Miami Marlins 4, **Final**),
// production, 390px, 2026-09-16. The hero's top meta row:
//
//     🏆  Final  [MLB.TV, DBACKS.TV, Marlins.TV]   Sep 15, 2026 · 6:40 PM PDT
//
// Everything else in that frame is a model of settled-means-settled — `Final`,
// a `WON` chip on the Marlins, `41% pregame`, the score at full size — and then
// the most prominent chip in the row invites the reader to tune in. The issue's
// own first specimen (`/events/15310364`, Yankees 2 Mets 12, Final, wearing
// `MLB.TV, MLB Net, YES`) is four days older, so the class is not one bad row:
// where a broadcast exists it survives the final whistle, measured at 42 of 183
// finished pages in one day.
//
// ── WHY THIS IS A GATE AND NOT A DELETION ────────────────────────────────────
//
// 🔴 The pregame and live arms below are the point of this file. The chip's
// whole job is "where to watch" BEFORE the first pitch — the hero's own comment
// (L2-157) calls its real estate "pregame start time + broadcast" — so a fix
// gated on `effectivelyLive` (which the issue recommended) would silence the
// defect by costing every pregame reader the thing the chip is for. An
// absence-only guard passes on that fix. These two arms fail on it.
//
// ── THE RULE IS ADOPTED, NOT DESIGNED ────────────────────────────────────────
//
// This page was the last of three surfaces to carry it:
//   * `components/EventCard.tsx` — footer gated `!isFinished && !isSuspended`
//     (CERT-792), with the same reasoning written out: a pregame promise on a
//     match that is stopped, not upcoming.
//   * `ios/.../EventDetailView.swift` — `showsBroadcast` (#4002), after the
//     same chip offered "MLB.TV, Padres.TV, YES" two days after a game was
//     abandoned.
// The suspended arm exists because both of those carry it; dropping it here
// would have made the web page disagree with its own card about the same match.

import React from "react";
import { renderToStaticMarkup } from "react-dom/server";

/** The production specimen, verbatim. */
const BROADCAST = "MLB.TV, DBACKS.TV, Marlins.TV";
const CHIP = 'data-testid="event-hero-broadcast"';

const HOUR = 60 * 60 * 1000;

/** Offset FIRST, never a literal date: an anchor that branches on the clock is
 *  not an anchor (gotcha #44). "Future" and "started" are relative facts and a
 *  hard-coded 2026 timestamp stops being either. */
const startedHoursAgo = (h: number) => new Date(Date.now() - h * HOUR).toISOString();
const startsInHours = (h: number) => new Date(Date.now() + h * HOUR).toISOString();

function event(overrides: Record<string, unknown> = {}) {
  return {
    id: 15312659,
    sport_key: "baseball_mlb",
    sport: "baseball_mlb",
    sport_title: "MLB",
    home_team: "Arizona Diamondbacks",
    away_team: "Miami Marlins",
    home_score: 2,
    away_score: 4,
    status: "completed",
    commence_time: startedHoursAgo(7),
    espn: { broadcast: BROADCAST },
    win_probability_sources: {},
    ...overrides,
  };
}

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
  usePathname: () => "/events/15312659",
  useSearchParams: () => new URLSearchParams(),
  useParams: () => ({ id: "15312659" }),
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
      React.createElement(EventDetailPage, { params: { id: "15312659" } }),
    ),
  );
}

beforeEach(() => {
  historyPayload = { aggregate_line: [] };
});

describe("#5741 the broadcast chip answers a question somebody still has", () => {
  it("is gone on the issue's own finished specimen", () => {
    eventPayload = event();

    const html = draw();

    expect(html).not.toContain(BROADCAST);
    expect(html).not.toContain(CHIP);
  });

  it("is gone on a `closed` row too, which is the other half of Final", () => {
    // `isFinishedStatus` is `completed || closed`. A gate written against the
    // one status the specimen happened to carry ships to half its own class.
    eventPayload = event({ status: "closed" });

    expect(draw()).not.toContain(BROADCAST);
  });

  it("is gone on a suspended match — nobody can report it, so nobody can watch it", () => {
    eventPayload = event({
      status: "suspended",
      home_score: null,
      away_score: null,
      commence_time: startedHoursAgo(5),
    });

    expect(draw()).not.toContain(BROADCAST);
  });

  it("is gone on a `scheduled` row hours past its own kickoff", () => {
    // #3211's widening: the row still calls itself scheduled and nothing ever
    // reported anything. The page renders that as "No result reported", so the
    // chip must follow the badge and not the raw status.
    eventPayload = event({
      status: "scheduled",
      home_score: null,
      away_score: null,
      commence_time: startedHoursAgo(6),
    });

    expect(draw()).not.toContain(BROADCAST);
  });

  // ── the two arms that make this a gate and not a deletion ──────────────────

  it("🔴 STILL SHOWS on a pregame game, which is the chip's whole job", () => {
    eventPayload = event({
      status: "scheduled",
      home_score: null,
      away_score: null,
      commence_time: startsInHours(3),
    });

    // Asserted on the STRING the reader sees, not on this ship's new testid:
    // these two arms are controls, and a control that can only pass after the
    // change is not a control. They pass before it and must keep passing.
    expect(draw()).toContain(BROADCAST);
  });

  it("🔴 STILL SHOWS on a live game", () => {
    eventPayload = event({
      status: "live",
      home_score: 1,
      away_score: 0,
      commence_time: startedHoursAgo(1),
    });

    expect(draw()).toContain(BROADCAST);
  });

  it("is addressable, so a DOM probe can tell this chip from any other text", () => {
    // New with this ship, and the one assertion here that is expected to be red
    // before it. The absence arms above are deliberately written against the
    // broadcast STRING so they cannot be satisfied by a missing attribute.
    eventPayload = event({
      status: "live",
      home_score: 1,
      away_score: 0,
      commence_time: startedHoursAgo(1),
    });

    expect(draw()).toContain(CHIP);
  });

  // ── controls ───────────────────────────────────────────────────────────────

  it("takes the chip and nothing else out of the meta row", () => {
    // The failure mode of a JSX gate is a condition that swallows its siblings.
    // The date label lives in the same flex row and is what the reader is left
    // with, so it is asserted by its own testid rather than by eye.
    eventPayload = event();

    const html = draw();

    expect(html).toContain('data-testid="event-hero-start"');
    expect(html).toContain("Final");
  });

  it("draws the page rather than failing to render it", () => {
    // A thrown render satisfies every `not.toContain` above for the wrong
    // reason, so the positive assertions are the ones that make them mean
    // anything.
    eventPayload = event();

    const html = draw();

    expect(html).toContain("Diamondbacks");
    expect(html).toContain("Marlins");
    expect(html.length).toBeGreaterThan(2000);
  });
});
