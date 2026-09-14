// ux/1251 (#2800) — THE PAGE ITSELF MUST STOP CAPTIONING A FROZEN PRICE "Live".
//
// ── WHY A RENDER TEST AND NOT ONLY THE SEAM ──────────────────────────────────
//
// This is #4861's lesson applied again, and it is the reason this file exists
// beside `__tests__/lib/pinnedBlendIsNotCaptionedLive2800.test.ts` rather than
// inside it. That file proves `blendCaptionIsStale` composes the two signals
// correctly, and it would have passed throughout this entire bug: the defect
// was never in a helper, it was that `app/events/[id]/page.tsx` handed
// `resolveProbability` an age and nothing else. A seam test cannot see a wiring
// decision. Only a render can.
//
// Concretely, the mutant this file is here to kill: revert the call site to
// `heroStampIsStale(freshestSourceStamp, "price")` alone. Every assertion in
// the seam file still passes. The one below goes red.
//
// ── THE SPECIMEN ─────────────────────────────────────────────────────────────
//
// `/events/15312054` (Peliwo v Ziegann, ATP), production 2026-09-14 07:26Z:
// `live_probability_pinned` at 84 observations over 5,247 seconds, all 0.99,
// under a `1m ago` badge and a "No result reported" phase badge.
//
// ── THE STAMP IS AN OFFSET, NOT A LITERAL (gotcha #44) ───────────────────────
//
// The whole difficulty of #2800 is that the price is FRESH, so this test needs
// a stamp inside the 120s price boundary on every clock the suite runs on. A
// fixed ISO string would age past that boundary and silently convert this into
// a second copy of #5069 — passing for the wrong reason forever after. So the
// stamp is computed as an offset from now, and `commence_time` is fixed in the
// past because "already started" only becomes more true.

import React from "react";
import { renderToStaticMarkup } from "react-dom/server";

/** The caption under test, exactly as the hero prints it. */
const LIVE_CAPTION = "Live · Bain Luck blend";
/** What it must degrade to: the same number, without the claim of currency. */
const WITHDRAWN_CAPTION = "Bain Luck blend";

/** Inside the 120s price-staleness boundary on any clock (gotcha #44). */
function freshStamp(): string {
  return new Date(Date.now() - 30_000).toISOString();
}

function baseEvent(pinned: unknown) {
  return {
    id: 15312054,
    sport_key: "tennis_atp",
    sport_title: "ATP",
    home_team: "Peliwo",
    away_team: "Ziegann",
    home_score: null,
    away_score: null,
    status: "live",
    // Fixed and in the past: `hasStarted` only becomes more true with time.
    commence_time: "2026-09-14T06:00:00+00:00",
    hero_probability: 0.99,
    hero_probability_away: 0.01,
    hero_probability_source: "blend",
    live_probability_pinned: pinned,
    win_probability_sources: {
      kalshi: {
        value: 0.99,
        display_name: "Kalshi",
        type: "market",
        color: "#22c55e",
        updated_at: freshStamp(),
      },
    },
  };
}

/** The production shape: frozen for 87 minutes, still being rewritten. */
const PINNED = {
  pinned: true,
  probability: 0.99,
  observations: 84,
  span_seconds: 5247,
  since: "2026-09-14T06:00:00+00:00",
};

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

jest.mock("@/hooks/useLiveEventStream", () => ({
  __esModule: true,
  useLiveEventStream: () => ({ frame: null, connected: false }),
}));

jest.mock("next/navigation", () => ({
  __esModule: true,
  useRouter: () => ({ push: () => {}, replace: () => {}, prefetch: () => {} }),
  usePathname: () => "/events/15312054",
  useSearchParams: () => new URLSearchParams(),
  useParams: () => ({ id: "15312054" }),
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
      React.createElement(EventDetailPage, { params: { id: "15312054" } }),
    ),
  );
}

describe("#2800 the event page does not caption a pinned blend as live", () => {
  test("THE BUG: a pinned price is not captioned 'Live' on the rendered page", () => {
    eventPayload = baseEvent(PINNED);
    const html = draw();
    expect(html).not.toContain(LIVE_CAPTION);
    expect(html).toContain(WITHDRAWN_CAPTION);
  });

  test("the number survives the withdrawal — the reader keeps 99%", () => {
    // Notice 34: the repair removes a word. A blank hero would be worse than a
    // frozen one, and this asserts the fix did not reach the number.
    eventPayload = baseEvent(PINNED);
    expect(draw()).toContain("99");
  });

  test("A BACKED, FRESH BLEND STILL SAYS 'Live' — the control (gotcha #43)", () => {
    // If this arm ever goes red the change has eaten the ordinary live case,
    // which is every live event on the site. It is also what proves the arm
    // above is not passing merely because the caption never renders at all.
    //
    // ── WHY THE CONTROL IS AN ABSENT FIELD AND NOT `{pinned: false}` ──
    //
    // `liveClaimIsUnbacked` reads this field by TRUTHINESS (`if (pinned) return
    // true`, `lib/eventLivePush.ts:214`) on the documented contract that the
    // server sends it "ONLY when the server says so". A `{pinned: false}`
    // fixture is therefore a shape that does not exist, and asserting against
    // it would encode a fiction and read as a false red.
    //
    // MEASURED rather than taken from the docstring — 20 live events on
    // production, 2026-09-14 07:45Z: 16 absent/null, 4 with `pinned: true`,
    // ZERO present-but-false. The truthiness is load-bearing and currently safe.
    // If a server change ever starts emitting the false shape, this file's first
    // test would begin passing for the wrong reason and this comment is the
    // pointer to why.
    eventPayload = baseEvent(undefined);
    const html = draw();
    expect(html).toContain(LIVE_CAPTION);
  });
});
