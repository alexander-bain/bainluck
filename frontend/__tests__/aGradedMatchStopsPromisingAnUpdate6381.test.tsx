// #6381's SECOND HALF — THE POLL RING STOPS PROMISING AN UPDATE OVER A MATCH
// THE VENUE HAS ALREADY GRADED.
//
// ── WHAT THE READER SAW ──────────────────────────────────────────────────────
//
// `/events/15313807` at 390px, production 2026-09-17 18:13Z, hours after #6739
// taught the hero to print the winner's name (live/354's LOOK,
// `artifacts/live-354/AFTER-6739-15313807-390-top.png`):
//
//     Next update: 108                 <- the header
//     Settled · Crawley wins           <- the hero, two lines below
//
// One page, two answers. **777 of the 1,121** graded `suspended` rows now carry
// a winner sentence, and every one of them inside countdown reach draws this
// ring.
//
// ── WHY NEITHER EXISTING GUARD CAN SEE IT ────────────────────────────────────
//
// `shouldShowRefreshCountdown` took `isFinished, streamConnected, isLive,
// isSuspended, commenceTime, liveClaimUnbacked` — and no `venueSettled`, while
// `venue_settled` reached only the hero sentence and the pill. So:
//
//   * `isFinished` is FALSE — the row is `suspended`, not `completed`;
//   * `liveClaimUnbacked` (#5459) measures how old OUR NUMBER is, and these rows
//     have a fresh blend because their markets are still being polled;
//   * #6381's own clock bound (`REFRESH_COUNTDOWN_MAX_AGE_MS`, 12h) is about
//     rows too OLD to update, and this one is three hours past kickoff.
//
// The row therefore reached `if (isSuspended) return startedWithinCountdownReach(...)`
// and answered true. It is a STATE the guards were missing, not a clock they
// were mistuning, which is why the new arm sits beside the `isFinished` early
// return rather than inside the `isSuspended` branch.
//
// ── WHY A RENDER TEST AND NOT ONLY THE SEAM ──────────────────────────────────
//
// The seam table below would have passed throughout this bug: the function was
// correct for the arguments it was given, and the defect was that the PAGE never
// gave it the one that mattered. Only a render can see that wiring — and only a
// render can check the thing that must NOT change with it, which is that the
// hero keeps saying who won. Harness copied from
// `livePageStopsPromisingAnUpdate5459.test.tsx`, whose split (`onVisiblePoll`
// keeps the admission, `showRefreshCountdown` loses the promise) this rides.
//
// Anchors are OFFSET FIRST from the clock (gotcha #44), so no assertion here
// branches on the hour it runs at.

import React from "react";
import { renderToStaticMarkup } from "react-dom/server";

import { shouldShowRefreshCountdown } from "@/lib/eventKeyStats";

const MINUTE = 60 * 1000;
const HOUR = 60 * MINUTE;

/** Offset FIRST, then serialise. */
function agoIso(ms: number): string {
  return new Date(Date.now() - ms).toISOString();
}

/* ═══ ARM 1 — the seam, both directions ═════════════════════════════════════ */

describe("shouldShowRefreshCountdown: a venue-graded match has nothing to promise", () => {
  const started3hAgo = agoIso(3 * HOUR);
  const base = {
    isFinished: false,
    streamConnected: false,
    isLive: false,
    isSuspended: true,
    commenceTime: started3hAgo,
  };

  it("withholds the ring once the venue has graded the match", () => {
    expect(shouldShowRefreshCountdown({ ...base, venueSettled: true })).toBe(false);
  });

  it("CONTROL — the identical row WITHOUT a grade still earns its ring", () => {
    // This is the arm that keeps the one above honest: the specimen is a ring
    // case in every respect except the grade.
    expect(shouldShowRefreshCountdown(base)).toBe(true);
    expect(shouldShowRefreshCountdown({ ...base, venueSettled: false })).toBe(true);
  });

  it("CONTROL — an absent argument means 'not graded', so every old caller is unchanged", () => {
    expect(shouldShowRefreshCountdown({ ...base, venueSettled: undefined })).toBe(true);
  });

  it("outranks a LIVE claim, because a graded match is not live whatever the status says", () => {
    expect(
      shouldShowRefreshCountdown({ ...base, isLive: true, venueSettled: true }),
    ).toBe(false);
    expect(shouldShowRefreshCountdown({ ...base, isLive: true })).toBe(true);
  });

  it("CONTROL — a pregame match inside the start window is untouched", () => {
    const startsSoon = new Date(Date.now() + 30 * MINUTE).toISOString();
    expect(
      shouldShowRefreshCountdown({
        isFinished: false,
        streamConnected: false,
        isLive: false,
        isSuspended: false,
        commenceTime: startsSoon,
      }),
    ).toBe(true);
  });
});

/* ═══ ARM 2 — the page, where the wiring lives ══════════════════════════════ */

/** The promise the header must not make over a graded match. */
const PROMISE = "Next update:";
/** What the hero says instead, and must keep saying (#6739). */
const VERDICT = "Crawley wins";

interface Fixture {
  venueSettled: boolean;
}

let eventPayload: unknown;

jest.mock("swr", () => ({
  __esModule: true,
  default: (key: unknown) => {
    const isEvent = Array.isArray(key) && key[0] === "event";
    return {
      data: isEvent ? eventPayload : undefined,
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

// Not connected, so the page is on the POLL branch — the branch that draws the
// ring. A pushed page shows its age stamp instead (live/034 S2).
jest.mock("@/hooks/useLiveEventStream", () => ({
  __esModule: true,
  useLiveEventStream: () => ({ frame: null, connected: false }),
}));

jest.mock("next/navigation", () => ({
  __esModule: true,
  useRouter: () => ({ push: () => {}, replace: () => {}, prefetch: () => {} }),
  usePathname: () => "/events/15313807",
  useSearchParams: () => new URLSearchParams(),
  useParams: () => ({ id: "15313807" }),
}));

// eslint-disable-next-line @typescript-eslint/no-var-requires
const EventDetailPage = require("@/app/events/[id]/page").default;
// eslint-disable-next-line @typescript-eslint/no-var-requires
const { AnalyticsProvider } = require("@/components/Analytics");

/**
 * live/354's specimen: a `suspended` row three hours past kickoff, no score
 * reported, markets still priced — and the venue's own grade beside it.
 */
function draw({ venueSettled }: Fixture): string {
  eventPayload = {
    id: 15313807,
    sport_key: "soccer_efl_cup",
    sport_title: "EFL Cup",
    home_team: "Crawley Town",
    away_team: "Brighton",
    home_score: null,
    away_score: null,
    status: "suspended",
    commence_time: agoIso(3 * HOUR),
    hero_probability: 0.89,
    hero_probability_away: 0.11,
    hero_probability_source: "blend",
    win_probability_sources: {
      polymarket: {
        value: 0.89,
        display_name: "Polymarket",
        type: "market",
        color: "#22c55e",
        // FRESH, which is the whole reason #5459's guard cannot reach this row.
        updated_at: agoIso(2 * MINUTE),
      },
    },
    venue_settled: venueSettled,
    venue_settled_result: venueSettled ? "Crawley wins" : null,
  };
  return renderToStaticMarkup(
    React.createElement(
      AnalyticsProvider,
      null,
      React.createElement(EventDetailPage, { params: { id: "15313807" } }),
    ),
  );
}

describe("/events/[id] over a venue-graded match", () => {
  it("CONTROL — the ungraded row draws the ring, so the page IS the defect's page", () => {
    expect(draw({ venueSettled: false })).toContain(PROMISE);
  });

  it("stops promising an update once the venue has graded it", () => {
    expect(draw({ venueSettled: true })).not.toContain(PROMISE);
  });

  it("and still names the winner — the remedy is not deleted with the promise", () => {
    expect(draw({ venueSettled: true })).toContain(VERDICT);
  });

  it("KEEPS the age stamp, which is the admission that replaces the promise", () => {
    // #5459's split, and the reason `venueSettled` is passed to the RING call
    // and not to `onVisiblePoll`: the header answers "how old is this number?"
    // whether or not it promises a new one, and folding the two together is the
    // mistake #4861's guard caught the last time someone made it. Rendered, this
    // row reads `live · 2m ago  Settled · Crawley wins`.
    expect(draw({ venueSettled: true })).toMatch(/\bago\b/);
  });
});
