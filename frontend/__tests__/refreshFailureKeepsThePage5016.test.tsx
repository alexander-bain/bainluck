// #5016 — A FAILED REFRESH MUST NOT TAKE THE PAGE AWAY.
//
// ── WHAT THE READER SAW ──────────────────────────────────────────────────────
//
// SF@LAR, the season opener, production, 2026-09-10. A tab opened at 5:39pm PT
// and never touched again:
//
//     5:39pm  61% – 39%, score 0–0, `live · 8s ago`, chart, projected final
//     5:56pm  "Couldn't reach the server / Failed to fetch / Tap to retry"
//     6:36pm  the same error card, 57 minutes on
//
// The document went from 24259px to 1197px and stayed there. The server was
// fine the whole time — at 6:31pm the API served `7 – 3, live`, and a fresh
// load of the same url rendered a complete page.
//
// ── THE MECHANISM ────────────────────────────────────────────────────────────
//
// The gate read `if (eventError || !event)`. SWR KEEPS `data` WHEN A
// REVALIDATION FAILS — that is what stale-while-revalidate is — so `eventError`
// says nothing about whether there is a page to draw. `event` was populated and
// one line away from being rendered when the `||` discarded it.
//
// A failed refresh is a FRESHNESS event, not an EXISTENCE event. The page
// already discloses freshness (`live · Ns ago`, counted from the event's own
// observation stamp), so a page left up goes visibly stale by itself and
// recovers invisibly on the next good poll. A page that threw its content away
// needs a success AND a rerender before the reader gets anything back.
//
// ── WHY A RENDER TEST AND NOT A SEAM ─────────────────────────────────────────
//
// The defect is not in a computed string, it is in what is on the screen, and
// the two cases differ only in whether one early return fires. Only a render
// can tell them apart. `__tests__/lib/loadFailure2783.test.ts` already covers
// which HEADING a failure earns and passed throughout this bug — it never
// renders the page with data and an error at once, which is the entire case.
//
// The page is mocked down to the seam under test: every SWR key but the event
// resolves to `undefined`, so the sections below the hero render their own
// empty states. That is fine and deliberate — the assertion is about the early
// return at the top of the component, not about what the rails draw.

import React from "react";
import { renderToStaticMarkup } from "react-dom/server";

const EVENT = {
  id: 14632820,
  sport_key: "americanfootball_nfl",
  sport_title: "NFL",
  home_team: "Los Angeles Rams",
  away_team: "San Francisco 49ers",
  home_score: 7,
  away_score: 3,
  status: "live",
  commence_time: "2026-09-11T00:35:00+00:00",
  win_probability_sources: {},
};

/**
 * The words the reader must not be given while we are holding a page. Matched
 * without the apostrophe on purpose: the renderer escapes it to `&#x27;`, and a
 * guard that pinned the entity would be a guard about HTML escaping.
 */
const ERROR_CARD = "reach the server";

let eventPayload: unknown;
let eventFailure: unknown;

jest.mock("swr", () => ({
  __esModule: true,
  default: (key: unknown) => {
    // The page holds many SWR calls — history, game markets, tournament, team
    // progression. Only the event one is under test; the rest resolve empty.
    const isEvent = Array.isArray(key) && key[0] === "event";
    return {
      data: isEvent ? eventPayload : undefined,
      error: isEvent ? eventFailure : undefined,
      isLoading: false,
      mutate: () => undefined,
    };
  },
}));

// Only the three GA4 hooks stand down — `useAnalytics` comes from the real
// module, because the page destructures it and a blanket mock of `@/hooks`
// takes it away. `usePinnedEvents` reaches for the auth context, which is a
// whole provider away from anything this test is asking about.
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
  usePathname: () => "/events/14632820",
  useSearchParams: () => new URLSearchParams(),
  useParams: () => ({ id: "14632820" }),
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
      React.createElement(EventDetailPage, { params: { id: "14632820" } }),
    ),
  );
}

describe("#5016 a failed refresh keeps the page it already has", () => {
  it("keeps the score on screen when a refresh fails and SWR still holds the event", () => {
    eventPayload = EVENT;
    eventFailure = new TypeError("Failed to fetch");

    const html = draw();

    // The bug: this is what stood on the screen for 57 minutes instead.
    expect(html).not.toContain(ERROR_CARD);
    // And the page is really there, not merely not-an-error.
    expect(html).toContain("Rams");
    expect(html).toContain("49ers");
  });

  it("still shows the error card when the FIRST load fails and there is nothing to draw", () => {
    eventPayload = undefined;
    eventFailure = new TypeError("Failed to fetch");

    expect(draw()).toContain(ERROR_CARD);
  });

  it("renders the page normally when there is no error at all", () => {
    eventPayload = EVENT;
    eventFailure = undefined;

    const html = draw();

    expect(html).not.toContain(ERROR_CARD);
    expect(html).toContain("Rams");
  });
});
