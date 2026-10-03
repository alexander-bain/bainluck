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
//
// #10200 (web half of #9655) MOVED the one status, deliberately: on a page with
// a chart it is the connection status beside "Win Probability" — semantic words,
// exact clocks on tap — and the header's age badge and sparkline give way to it.
// The fullscreen view prints the same model. A page with NO chart card keeps the
// header badge, because there is nowhere else for the admission to go; the last
// arms here pin that, the truth warnings, and that an open socket never turns a
// scheduled match "Live".

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
function event(over: Record<string, unknown> = {}) {
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
    ...over,
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
/** #10200: the chart's one status. */
const STATUS = 'data-testid="live-connection-status"';

let eventPayload: unknown;
let historyPayload: unknown;
let streamConnected = false;
let streamStatus: string | undefined;

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
  useLiveEventStream: () => ({ frame: null, connected: streamConnected, chartPoints: [], status: streamStatus }),
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

function draw(
  connected: boolean,
  opts: { status?: string; event?: Record<string, unknown>; history?: unknown } = {},
): string {
  streamConnected = connected;
  streamStatus = opts.status ?? (connected ? "open" : undefined);
  eventPayload = event(opts.event);
  historyPayload = opts.history;
  return renderToStaticMarkup(
    React.createElement(
      AnalyticsProvider,
      null,
      React.createElement(EventDetailPage, { params: { id: "15317522" } }),
    ),
  );
}

const count = (haystack: string, needle: string): number => haystack.split(needle).length - 1;

/** The status's visible words. */
const statusWords = (html: string): string | null =>
  html.match(/data-testid="live-connection-status" data-status="([^"]*)"/)?.[1] ?? null;

describe("#8336 a live event page shows one freshness status", () => {
  it("a stream-fed page: one chart status, no header badge, no poll ticker anywhere", () => {
    const html = draw(true);

    expect(count(html, STATUS)).toBe(1);
    expect(statusWords(html)).toBe("Connected · waiting");
    // #10200: no headline seconds — the header badge gave way to the status.
    expect(count(html, BADGE)).toBe(0);
    expect(html).not.toMatch(TICKER);
    expect(html).not.toContain(REFRESH_GLYPH);
    expect(html).not.toContain(PROMISE);
  });

  it("a polled page: one chart status, the header ring kept, no second or third ticker", () => {
    const html = draw(false);

    expect(count(html, STATUS)).toBe(1);
    expect(statusWords(html)).toBe("Checking for updates");
    expect(count(html, BADGE)).toBe(0);
    expect(html).not.toMatch(TICKER);
    expect(html).not.toContain(REFRESH_GLYPH);
    // CONTROL — the header's ring is #5039's and stays. Without this arm a
    // deletion of every countdown on the page would pass the assertions above.
    expect(count(html, PROMISE)).toBe(1);
  });

  it("the status sits in the chart card's header, beside Win Probability", () => {
    const html = draw(true);
    const card = html.slice(html.indexOf('data-testid="win-probability-card"'));
    const cardHeader = card.slice(0, card.indexOf('title="Open fullscreen chart"'));
    expect(cardHeader).toContain("Win Probability");
    expect(cardHeader).toContain(STATUS);
  });

  it("draws the live page rather than failing to render it", () => {
    // A thrown or empty render satisfies every `not` above for the wrong reason.
    const html = draw(true);

    expect(html).toContain("Athletics");
    expect(html).toContain('data-testid="win-probability-card"');
  });

  it("the fullscreen chart carries the SAME status model, not a ticker or a badge of its own", () => {
    // The modal only mounts on a tap, which a static render cannot make, so
    // this arm reads the source: no `{countdown}s` ticker survives anywhere in
    // the page, and the modal header places the one status builder — the same
    // closure over the same `connectionPresentation` the card uses.
    const source = readFileSync(join(process.cwd(), "app/events/[id]/page.tsx"), "utf8");
    expect(source).not.toContain("{countdown}s<");
    expect(count(source, "<LiveConnectionStatus")).toBe(1);
    expect(source).toContain("presentation={connectionPresentation}");

    // #10250 moved the modal's shell into `ChartFullscreenDialog`; the page
    // hands it the status through `status=`, which ends where the chart begins.
    const modal = source.slice(source.indexOf("{/* Fullscreen Chart Modal"));
    const modalHeader = modal.slice(0, modal.indexOf("<OddsChart"));
    expect(modalHeader).toContain("<ChartFullscreenDialog");
    expect(modalHeader).toContain("status={");
    expect(modalHeader).toContain("connectionStatus(false)");
    expect(modalHeader).not.toContain("{ageBadge}");
    const cardHeader = source.slice(source.indexOf("{/* Chart Header — v2: title + freshness."));
    expect(cardHeader.slice(0, cardHeader.indexOf('title="Open fullscreen chart"'))).toContain("connectionStatus(true)");
  });

  it("both header rows are positioned, so the tap details hang from the row and fit a phone", () => {
    // The status is deliberately unpositioned (its panel ran off the card at
    // 390px when it hung from the button); the row it sits in must be.
    const source = readFileSync(join(process.cwd(), "app/events/[id]/page.tsx"), "utf8");
    const card = source.slice(source.indexOf("{/* Chart Header — v2: title + freshness."));
    expect(card).toMatch(/^[\s\S]{0,200}<div className="relative px-4 sm:px-5 py-3 flex items-center justify-between">/);
    // #10250 — the fullscreen header row now lives in the dialog component.
    const dialog = readFileSync(join(process.cwd(), "components/event/ChartFullscreenDialog.tsx"), "utf8");
    const modal = dialog.slice(dialog.indexOf('data-testid="chart-fullscreen-dialog"'));
    expect(modal).toMatch(/^[\s\S]{0,200}<div className="relative flex items-center justify-between px-4 py-3 border-b border-surface-border">/);
  });

  it("a page with NO chart card keeps the header's age admission", () => {
    // A begun game whose history holds no series: the chart card is suppressed
    // (#3612), so the header badge is still the page's one answer.
    const html = draw(true, {
      history: { history: [], bookmaker_history: {}, aggregate_line: [] },
    });

    expect(html).not.toContain('data-testid="win-probability-card"');
    expect(count(html, STATUS)).toBe(0);
    expect(count(html, BADGE)).toBe(1);
  });
});

describe("#10200 the status never lets a healthy socket hide old evidence", () => {
  it("an old price is named while the socket is open — no breathing, no connection claim", () => {
    const html = draw(true, {
      event: {
        win_probability_sources: {
          kalshi: { value: 0.84, display_name: "Kalshi", type: "market", color: "#22c55e", updated_at: agoIso(5 * MINUTE) },
        },
      },
    });
    expect(statusWords(html)).toBe("Price may be old");
    const status = html.slice(html.indexOf(STATUS));
    expect(status.slice(0, status.indexOf("</button>"))).not.toContain("animate-");
  });

  it("an old score is named while the price is fresh, and the tap facts give its clock", () => {
    const html = draw(true, { event: { score_observed_at: agoIso(10 * MINUTE) } });
    expect(statusWords(html)).toBe("Score may be old");
    const status = html.slice(html.indexOf(STATUS));
    expect(status).toContain("Score confirmed");
    expect(status).toContain("10m ago");
    expect(status).toContain("Oldest on screen</dt><dd>The score");
  });

  it("an open socket never turns a scheduled match Live", () => {
    const html = draw(true, {
      status: "open",
      event: { status: "scheduled", commence_time: new Date(Date.now() + 3 * 60 * MINUTE).toISOString(), home_score: null, away_score: null },
    });
    expect(statusWords(html)).toBe("Connected · waiting");
    expect(statusWords(html)).not.toMatch(/live/i);
    expect(html).not.toContain(">LIVE<");
  });
});
