// #5459 / #5077 — A PAGE WHOSE NUMBER STOPPED MOVING MUST STOP PROMISING ONE.
//
// ── WHAT THE READER SAW ──────────────────────────────────────────────────────
//
// Jeanjean v Liu (`tennis_wta`), production, 2026-09-12 03:26Z, 390px:
// `artifacts/ux-1204/BEFORE-15310172-390-top.png`.
//
//     ● 146m ago
//     LIVE                                    ⟳ 20s
//     1% – 99%     Bain Luck blend
//     Win Probability  ◔ 20s
//     [chart: dead flat at 1% from 5:30 PM to 8:26 PM]
//
// No score anywhere. The match was long over and Liu had won — `1%`/`99%` is the
// settled-market signature (bid 0.00 / ask 1.00 on every rung), not a forecast.
// Racing Louisville v Gotham was byte-for-byte the same page at the same minute
// (`BEFORE-15307904-390-top.png`, `144m ago`).
//
// THE PAGE ALREADY CONTAINED ITS OWN REFUTATION. `LiveAgeStamp` had worked out
// that the number was two and a half hours old, greyed itself and dropped the
// word "live" accordingly — two centimetres above a chip that said LIVE and a
// ring that promised a fresh number in twenty seconds. That is #4469/#5069's
// lesson (*a second copy of the comparison is how a dot and its caption come to
// disagree*) reaching one element further out.
//
// ── WHY THIS IS NOT ALREADY COVERED BY #4861 ─────────────────────────────────
//
// #4861 is the same sentence about a different subject: it drops the promise
// when OUR FETCHES stop landing. Here they land perfectly — on schedule, every
// two minutes — and write the same value back each time. `eventFeedIsStalled` is
// false throughout, which is why its guard passes on this page while a reader
// looks at three separate claims of liveness.
//
// #4861 also fixed only the header's countdown GROUP, leaving the two
// `{countdown}s` tickers and the pulsing phase badge on `effectivelyLive` alone.
// That is why the specimen above says LIVE in three places. One predicate now,
// not three JSX conditions.
//
// ── WHY A RENDER TEST AND NOT ONLY A SEAM ────────────────────────────────────
//
// `liveClaimIsUnbacked` is pure and has its own table below, but a test that
// only called it would have passed throughout this bug: the defect is that the
// HEADER prints a promise, and only a render can see the header. Same reason
// #4861 renders, and the same reason #5016's `loadFailure2783` did not catch it.
//
// The page is mocked down to the seam under test: every SWR key but the event
// resolves to `undefined`, so the rails below the hero draw their own empty
// states. The assertions are about the header.

import React from "react";
import { renderToStaticMarkup } from "react-dom/server";

import {
  LIVE_CLAIM_MAX_BLEND_AGE_MS,
  liveClaimIsUnbacked,
} from "@/lib/eventLivePush";

const MINUTE = 60 * 1000;

/** Offset FIRST, then serialise (gotcha #44 — an anchor that branches is not fixed). */
function agoIso(ms: number): string {
  return new Date(Date.now() - ms).toISOString();
}

/**
 * A live WTA match past its own kickoff, which is what makes the header draw the
 * countdown ring at all (`shouldShowRefreshCountdown`), with ONE blend source.
 *
 * `updated_at` is a parameter rather than a constant because the whole argument
 * of the second disqualifier is about that stamp's age, and both sides of the
 * boundary have to be reachable from the same fixture.
 */
function event(opts: { stampAgeMs: number; pinned?: unknown }) {
  return {
    id: 15310172,
    sport_key: "tennis_wta",
    sport_title: "WTA",
    home_team: "Jeanjean",
    away_team: "Liu",
    home_score: null,
    away_score: null,
    status: "live",
    // Fixed relative to the stamp, not to the clock: this only ever needs to be
    // "well past kickoff", and the ring's 3h window is not what is under test.
    commence_time: agoIso(opts.stampAgeMs + 30 * MINUTE),
    hero_probability: 0.01,
    hero_probability_away: 0.99,
    hero_probability_source: "blend",
    win_probability_sources: {
      polymarket: {
        value: 0.01,
        display_name: "Polymarket",
        type: "market",
        color: "#22c55e",
        updated_at: agoIso(opts.stampAgeMs),
      },
    },
    ...(opts.pinned === undefined ? {} : { live_probability_pinned: opts.pinned }),
  };
}

/** The payload the server sends when it has withdrawn the claim itself. */
const PINNED = {
  pinned: true,
  probability: 0.01,
  observations: 11,
  span_seconds: 6430,
  since: "2026-09-12T01:25:16.492979+00:00",
};

/** The promise the header must not make over a number that stopped moving. */
const PROMISE = "Next update:";
/** The word the phase badge must not say, and the ticker beside it. */
const CLAIM = "LIVE";
/** Where the badge lands instead — existing vocabulary, no new prose (notice 34). */
const ADMISSION = "No result reported";

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

// Not connected, so the page is on the POLL branch — which is the branch that
// draws the ring. A pushed page shows its age stamp instead (live/034 S2).
jest.mock("@/hooks/useLiveEventStream", () => ({
  __esModule: true,
  useLiveEventStream: () => ({ frame: null, connected: false }),
}));

jest.mock("next/navigation", () => ({
  __esModule: true,
  useRouter: () => ({ push: () => {}, replace: () => {}, prefetch: () => {} }),
  usePathname: () => "/events/15310172",
  useSearchParams: () => new URLSearchParams(),
  useParams: () => ({ id: "15310172" }),
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
      React.createElement(EventDetailPage, { params: { id: "15310172" } }),
    ),
  );
}

describe("#5459 the event page stops promising liveness it cannot back", () => {
  it("CONTROL: a live page with a fresh number keeps its LIVE pill and its ticker", () => {
    // The test CERT-2669 named. Everything this ship removes must still be here
    // on an ordinary live page, or the fix is a deletion rather than a rule.
    eventPayload = event({ stampAgeMs: 20 * 1000 });

    const html = draw();

    expect(html).toContain(PROMISE);
    expect(html).toContain(CLAIM);
    expect(html).not.toContain(ADMISSION);
  });

  it("drops the promise and the claim when the SERVER says the number is pinned", () => {
    // Fresh stamp on purpose: this is the shape no age rule can see, and the
    // reason the backend half exists at all. If this passed on the age arm the
    // test would be proving the wrong disqualifier.
    eventPayload = event({ stampAgeMs: 20 * 1000, pinned: PINNED });

    const html = draw();

    expect(html).not.toContain(PROMISE);
    expect(html).not.toContain(CLAIM);
    // The page is kept and so is the number — it is the promise of liveness
    // that was unbacked, not the price.
    expect(html).toContain("Jeanjean");
    expect(html).toContain("Liu");
    expect(html).toContain(ADMISSION);
  });

  it("drops them on the page's OWN reading when the blend is an hour old", () => {
    // The 24 rows of #5469 the backend rule cannot reach — Alex's MiLB specimen
    // 15310413 read `234m ago` under a 20s ticker and carried no payload field.
    eventPayload = event({ stampAgeMs: LIVE_CLAIM_MAX_BLEND_AGE_MS + MINUTE });

    const html = draw();

    expect(html).not.toContain(PROMISE);
    expect(html).not.toContain(CLAIM);
    expect(html).toContain(ADMISSION);
  });

  it("does NOT drop them a minute inside the boundary", () => {
    // The other side of the same constant. Without this pair the bound could be
    // tuned to zero and every live page in the app would go quiet, green.
    eventPayload = event({ stampAgeMs: LIVE_CLAIM_MAX_BLEND_AGE_MS - MINUTE });

    const html = draw();

    expect(html).toContain(PROMISE);
    expect(html).toContain(CLAIM);
  });
});

describe("#5459 liveClaimIsUnbacked", () => {
  it("believes the server over any age, because that is the case only it can see", () => {
    expect(liveClaimIsUnbacked({ pinned: PINNED, blendAgeMs: 20 * 1000 })).toBe(true);
  });

  it("says nothing about an ordinary live page", () => {
    expect(liveClaimIsUnbacked({ pinned: undefined, blendAgeMs: 20 * 1000 })).toBe(false);
  });

  it("fires on age alone, for the rows the server rule cannot reach", () => {
    expect(
      liveClaimIsUnbacked({
        pinned: undefined,
        blendAgeMs: LIVE_CLAIM_MAX_BLEND_AGE_MS + 1,
      }),
    ).toBe(true);
  });

  it("holds ON the boundary — an hour old is not yet past an hour", () => {
    expect(
      liveClaimIsUnbacked({
        pinned: undefined,
        blendAgeMs: LIVE_CLAIM_MAX_BLEND_AGE_MS,
      }),
    ).toBe(false);
  });

  it("stays far clear of a healthy poll, which is why the bound is not the badge's", () => {
    // `LiveAgeStamp` greys at 120s. Withdrawing a word there would flicker the
    // pill off and on every poll cycle on every healthy game in the app.
    expect(liveClaimIsUnbacked({ pinned: undefined, blendAgeMs: 130 * 1000 })).toBe(false);
  });

  it("treats an unstamped page as unknown, not as old", () => {
    // "We cannot say how old this is" and "this is old" are different claims,
    // and only the second earns the removal of a word.
    expect(liveClaimIsUnbacked({ pinned: undefined, blendAgeMs: null })).toBe(false);
    expect(liveClaimIsUnbacked({ pinned: undefined, blendAgeMs: NaN })).toBe(false);
  });

  it("reuses the server's own floor rather than a number chosen here", () => {
    // `_pinned_live_probability` requires the value to have held for >=60
    // minutes from kickoff. Two halves of one pair may not disagree about how
    // long is too long.
    expect(LIVE_CLAIM_MAX_BLEND_AGE_MS).toBe(60 * 60 * 1000);
  });
});
