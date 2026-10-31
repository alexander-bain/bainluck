/**
 * #10090 Alex 67, part 2 — THE CHART'S STATUS SPEAKS ONLY WHEN SOMETHING IS WRONG.
 *
 * While the EKG is showing, a healthy socket (open, quiet) draws no status;
 * reconnecting, an old price, or no EKG (`?ekg=0`) keep today's words. The live
 * region stays mounted, so trouble is still announced. The real page, rendered
 * statically with the reader's EKG choice forced on or off. Part 1 (the tap) and
 * the healthy rule are `components/ekgTapForTimesAlex67.test.tsx`.
 *
 * No `minimalDom` here: with a `window` the page's committed layout effects
 * would run their client branch under the server renderer.
 */
import React from "react";
import { readFileSync } from "fs";
import { join } from "path";
import { renderToStaticMarkup } from "react-dom/server";

// ── the real page, statically, with the reader's EKG choice forced ───────────
const MINUTE = 60_000;
const agoIso = (ms: number) => new Date(Date.now() - ms).toISOString();

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
      kalshi: { value: 0.84, display_name: "Kalshi", type: "market", color: "#22c55e", updated_at: agoIso(20 * 1000) },
    },
    ...over,
  };
}

let eventPayload: unknown;
let streamStatus: string | undefined;
let ekgOn = true;

jest.mock("swr", () => ({
  __esModule: true,
  default: (key: unknown) => ({
    data: Array.isArray(key) && key[0] === "event" ? eventPayload : undefined,
    error: undefined,
    isLoading: false,
    mutate: () => undefined,
  }),
}));
jest.mock("@/hooks", () => ({
  ...jest.requireActual("@/hooks"),
  __esModule: true,
  usePageTracking: () => undefined,
  useScrollDepth: () => undefined,
  useEngagementTime: () => undefined,
  usePinnedEvents: () => ({ isPinned: () => false, togglePin: () => undefined, isMaxReached: false }),
}));
jest.mock("@/hooks/useLiveEventStream", () => ({
  __esModule: true,
  useLiveEventStream: () => ({ frame: null, connected: true, chartPoints: [], status: streamStatus }),
}));
jest.mock("@/lib/ekgOptIn", () => ({
  ...jest.requireActual("@/lib/ekgOptIn"),
  __esModule: true,
  useEkgOptIn: () => ekgOn,
}));
jest.mock("next/navigation", () => ({
  __esModule: true,
  useRouter: () => ({ push: () => {}, replace: () => {}, prefetch: () => {} }),
  usePathname: () => "/events/15317522",
  useSearchParams: () => new URLSearchParams(),
  useParams: () => ({ id: "15317522" }),
}));

const EventDetailPage = require("@/app/events/[id]/page").default;
const { AnalyticsProvider } = require("@/components/Analytics");

function page(opts: { status?: string; ekg?: boolean; event?: Record<string, unknown> } = {}): string {
  streamStatus = opts.status ?? "open";
  ekgOn = opts.ekg ?? true;
  eventPayload = event(opts.event);
  return renderToStaticMarkup(
    React.createElement(AnalyticsProvider, null, React.createElement(EventDetailPage, { params: { id: "15317522" } })),
  );
}

/** The chart status's own markup: from its wrapper up to the card's fullscreen opener. */
function chartStatus(html: string): string {
  const card = html.slice(html.indexOf('data-testid="win-probability-card"'));
  const start = card.indexOf('data-testid="live-connection-status"');
  expect(start).toBeGreaterThan(-1);
  const opener = card.lastIndexOf("<button", card.indexOf('title="Open fullscreen chart"'));
  expect(opener).toBeGreaterThan(start);
  return card.slice(start, opener);
}

describe("Alex 67 — on the page: the status speaks only when something is wrong", () => {
  it("healthy with the EKG on: the EKG is a tap-for-times button and the chart has no status line", () => {
    const html = page();
    expect(html).toContain('data-testid="ekg-row"');
    expect(html).toMatch(/data-testid="ekg-times"><button type="button" aria-expanded="false"/);
    const status = chartStatus(html);
    expect(status).toContain('data-quiet="true"');
    expect(status).not.toContain("<button");
    // `data-status` keeps the model's words for probes; nothing is drawn.
    expect(status).not.toContain("leading-4");
    // The live region stays, empty, ready for trouble.
    expect(status).toContain('<span class="sr-only" role="status" aria-live="polite"></span>');
  });

  it("quiet socket with the EKG on: no status line either", () => {
    const status = chartStatus(page({ status: "quiet" }));
    expect(status).toContain('data-quiet="true"');
    expect(status).not.toContain("<button");
  });

  it("retrying: the status line is present, and announced", () => {
    const status = chartStatus(page({ status: "retrying" }));
    expect(status).not.toContain("data-quiet");
    expect(status).toContain('<span class="min-w-0 leading-4">Updates interrupted · reconnecting</span>');
    expect(status).toContain('aria-live="polite">Updates interrupted · reconnecting</span>');
  });

  it("an old price keeps its words while the EKG shows", () => {
    const status = chartStatus(page({
      event: {
        win_probability_sources: {
          kalshi: { value: 0.84, display_name: "Kalshi", type: "market", color: "#22c55e", updated_at: agoIso(5 * MINUTE) },
        },
      },
    }));
    expect(status).not.toContain("data-quiet");
    expect(status).toContain(">Price may be old</span>");
  });

  it("?ekg=0: no EKG, and the status line exactly as today", () => {
    const html = page({ ekg: false });
    expect(html).not.toContain('data-testid="ekg-row"');
    const status = chartStatus(html);
    expect(status).not.toContain("data-quiet");
    expect(status).toContain('<span class="min-w-0 leading-4">Connected · waiting</span>');
  });

  it("the fullscreen copy is never quiet: the dialog covers the EKG", () => {
    const source = readFileSync(join(process.cwd(), "app/events/[id]/page.tsx"), "utf8");
    const modal = source.slice(source.indexOf("{/* Fullscreen Chart Modal"));
    expect(modal.slice(0, modal.indexOf("<OddsChart"))).toContain("connectionStatus(false)}");
    expect(source).toContain("const connectionStatusQuiet = ekgShowing && connectionStatusIsHealthy({");
  });
});
