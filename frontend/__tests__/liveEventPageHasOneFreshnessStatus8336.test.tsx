// #8336 — a live event page answers "how fresh is this" ONCE.
//
// LOOKED at production `/events/15317520`'s sibling `/events/15317522`
// (Athletics v Angels, live, Top 5th) at 390px on 2026-09-24 03:10 UTC. The
// page was stream-fed — the header's pulsing `live · 35s ago` badge, which reads
// the event's own observation stamp — and the same first screen ALSO said:
//
//     Top 5th   MLB.TV, NBC Sports CA, Angels.TV      ⟳ 20s     <- hero row
//     Win Probability  ◔ 20s                                    <- chart title
//
// Three freshness indicators for one question. The two tickers count a 20s
// `setInterval` that runs whether or not anything arrives, so on a pushed page
// they advertise a poll the reader is not waiting on. The web twin of #8320
// (native owns the phone half): the header badge is the one status.
//
// What this does NOT touch: the header's polled-page "Next update:" ring, which
// #5039/#4861/#5459/#6381 each guard. The polled arm below asserts it survives,
// so a fix that deleted every countdown would fail here too.

import React from "react";
import { readFileSync } from "fs";
import { join } from "path";
import { renderToStaticMarkup } from "react-dom/server";

const MINUTE = 60 * 1000;

/** Offset FIRST, then serialise (gotcha #44). */
function agoIso(ms: number): string {
  return new Date(Date.now() - ms).toISOString();
}

/** A live MLB game 40 minutes in, with a fresh blend and a score. */
function event() {
  return {
    id: 15317522,
    sport_key: "baseball_mlb",
    sport_title: "MLB",
    home_team: "Athletics",
    away_team: "Los Angeles Angels",
    home_score: 5,
    away_score: 2,
    status: "live",
    commence_time: agoIso(40 * MINUTE),
    hero_probability: 0.84,
    hero_probability_away: 0.16,
    hero_probability_source: "blend",
    win_probability_sources: {
      kalshi: {
        value: 0.84,
        display_name: "Kalshi",
        type: "market",
        color: "#22c55e",
        updated_at: agoIso(20 * 1000),
      },
    },
  };
}

/** The markup both removed tickers shared: `<span class="… tabular-nums font-mono">20s</span>`. */
const TICKER = /tabular-nums font-mono">\d+s</;
/** The refresh glyph that sat in front of the hero ticker. */
const REFRESH_GLYPH = "M4 4v5h.582";
/** The age badge's visible text. The blend caption is "Live ·" — capital L, not this. */
const BADGE = "live · ";
/** The header's polled-page ring — untouched by this ship. */
const PROMISE = "Next update:";

let eventPayload: unknown;
let streamConnected = false;

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
  useLiveEventStream: () => ({ frame: null, connected: streamConnected }),
}));

jest.mock("next/navigation", () => ({
  __esModule: true,
  useRouter: () => ({ push: () => {}, replace: () => {}, prefetch: () => {} }),
  usePathname: () => "/events/15317522",
  useSearchParams: () => new URLSearchParams(),
  useParams: () => ({ id: "15317522" }),
}));

// eslint-disable-next-line @typescript-eslint/no-var-requires
const EventDetailPage = require("@/app/events/[id]/page").default;
// eslint-disable-next-line @typescript-eslint/no-var-requires
const { AnalyticsProvider } = require("@/components/Analytics");

function draw(connected: boolean): string {
  streamConnected = connected;
  eventPayload = event();
  return renderToStaticMarkup(
    React.createElement(
      AnalyticsProvider,
      null,
      React.createElement(EventDetailPage, { params: { id: "15317522" } }),
    ),
  );
}

const count = (haystack: string, needle: string): number => haystack.split(needle).length - 1;

describe("#8336 a live event page shows one freshness status", () => {
  it("a stream-fed page: the age badge, once, and no poll ticker anywhere", () => {
    const html = draw(true);

    expect(count(html, BADGE)).toBe(1);
    expect(html).not.toMatch(TICKER);
    expect(html).not.toContain(REFRESH_GLYPH);
    expect(html).not.toContain(PROMISE);
  });

  it("a polled page: the age badge once, the header ring kept, no second or third ticker", () => {
    const html = draw(false);

    expect(count(html, BADGE)).toBe(1);
    expect(html).not.toMatch(TICKER);
    expect(html).not.toContain(REFRESH_GLYPH);
    // CONTROL — the header's ring is #5039's and stays. Without this arm a
    // deletion of every countdown on the page would pass the assertions above.
    expect(count(html, PROMISE)).toBe(1);
  });

  it("draws the live page rather than failing to render it", () => {
    // A thrown or empty render satisfies every `not` above for the wrong reason.
    const html = draw(true);

    expect(html).toContain("Athletics");
    expect(html).toContain('data-testid="win-probability-card"');
  });

  it("the fullscreen chart carries the age badge, not a ticker of its own", () => {
    // The modal only mounts on a tap, which a static render cannot make, so
    // this arm reads the source: no `{countdown}s` ticker survives anywhere in
    // the page, and the modal header places the header's own `ageBadge`.
    const source = readFileSync(join(process.cwd(), "app/events/[id]/page.tsx"), "utf8");
    expect(source).not.toContain("{countdown}s<");

    const modal = source.slice(source.indexOf("{/* Fullscreen Chart Modal */}"));
    const modalHeader = modal.slice(0, modal.indexOf("{isFinished && ("));
    expect(modalHeader).toContain("{ageBadge}");
  });
});
