/**
 * #10090 decision J under a preview — WEB HALF of native #11816's rule 2.
 *
 * `confirmed_at` vouches for the COMMITTED pair. While a preview is displayed,
 * the page may say "Probability confirmed" (and the status may read
 * "Connected") only if the preview PRINTS the committed pair: same digits, both
 * sides, at the precision the reader sees. A preview printing another number is
 * provisional and keeps its own clock. Before this, master claimed the
 * confirmation over any preview whose observation was older than
 * `confirmed_at`, whatever number it printed.
 *
 * Real EventPage and its real connection status; only transport/data reads are
 * mocked (the shape of `previewObservedReadoutPage10090.test.tsx`).
 */
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { previewAfter, type BlendPreviewState } from "@/lib/blendPreview";

const ID = 14632820;
/** Fixed anchor — never `Date.now()` (gotcha #44). */
const NOW = Date.UTC(2026, 9, 30, 21, 0, 0);
const COMMITTED = new Date(NOW - 120_000).toISOString();
const OBSERVED = new Date(NOW - 8_000).toISOString(); // the preview's observation
const CONFIRMED = new Date(NOW - 2_000).toISOString(); // newer than the preview
let eventPayload: ReturnType<typeof event>;
let blendPreview: BlendPreviewState | null;
let blendPreviewNow: number;
let confirmedAt: string | null;
let tenthsOn: boolean;
function event() {
  return {
    id: ID, sport: "americanfootball_nfl", sport_key: "americanfootball_nfl",
    home_team: "Los Angeles Rams", away_team: "San Francisco 49ers",
    home_score: 7, away_score: 10, status: "live",
    commence_time: new Date(NOW - 3_600_000).toISOString(),
    score_observed_at: new Date(NOW - 60_000).toISOString(),
    hero_probability: .6, hero_probability_away: .4,
    hero_probability_source: "blend", hero_probability_observed_at: COMMITTED,
    blend_fold_revision: { [ID]: 10 } as Record<string, number>,
    win_probability_sources: {
      kalshi: { value: .6, display_name: "Kalshi", type: "market", color: "#22c55e", updated_at: COMMITTED },
    },
  };
}
function preview(p: number) {
  return previewAfter(null, {
    event_id: ID, p, status: "live", observed_at: new Date(NOW).toISOString(),
    display_observed_at: OBSERVED,
    preview: { kind: "blend", epoch: 1, seq: 1, base_rev: 10, ttl_ms: 1000 },
  }, ID, NOW);
}

jest.mock("swr", () => ({
  __esModule: true,
  default: (key: unknown) => ({
    data: Array.isArray(key) && key[0] === "event" ? eventPayload : undefined,
    error: undefined, isLoading: false, mutate: () => undefined,
  }),
}));
jest.mock("@/hooks", () => ({
  ...jest.requireActual("@/hooks"),
  usePageTracking: () => undefined, useScrollDepth: () => undefined, useEngagementTime: () => undefined,
  usePinnedEvents: () => ({ isPinned: () => false, togglePin: () => undefined, isMaxReached: false }),
}));
jest.mock("@/hooks/useLiveEventStream", () => ({
  useLiveEventStream: () => ({
    frame: null, connected: true, status: "open", blendPreview, blendPreviewNow, chartPoints: [], confirmedAt,
  }),
}));
jest.mock("next/dynamic", () => ({ __esModule: true, default: () => () => null }));
jest.mock("next/navigation", () => ({
  useRouter: () => ({ push: () => {}, replace: () => {}, prefetch: () => {} }),
  usePathname: () => "/events/14632820", useSearchParams: () => new URLSearchParams(),
  useParams: () => ({ id: "14632820" }),
}));
jest.mock("@/lib/tenthsOptIn", () => ({
  __esModule: true,
  ...jest.requireActual("@/lib/tenthsOptIn"),
  useTenthsOptIn: () => tenthsOn,
}));

const EventDetailPage = require("@/app/events/[id]/page").default;
const { AnalyticsProvider } = require("@/components/Analytics");
function draw() {
  return renderToStaticMarkup(<AnalyticsProvider><EventDetailPage params={{ id: String(ID) }} /></AnalyticsProvider>);
}
const confirmedRow = (html: string) => html.match(/Probability confirmed<\/dt><dd>(.*?)<\/dd>/)?.[1] ?? null;
const observedRow = (html: string) => html.match(/Probability observed<\/dt><dd>(.*?)<\/dd>/)![1];
const status = (html: string) => html.match(/data-testid="live-connection-status" data-status="([^"]*)"/)![1];
const heroDigits = (html: string) => (html.match(/data-hero-digits="">([^<]+)/g) ?? []).map(m => m.replace(/.*>/, ""));
const delivery = (html: string) => html.match(/data-observation-delivery="([^"]*)"/)![1];

beforeEach(() => {
  jest.spyOn(Date, "now").mockReturnValue(NOW);
  eventPayload = event(); blendPreview = null; blendPreviewNow = NOW; confirmedAt = CONFIRMED; tenthsOn = true;
});
afterEach(() => jest.restoreAllMocks());

test("control: no preview, the committed number is confirmed exactly as today", () => {
  const html = draw();
  expect(delivery(html)).toBe("committed");
  expect(confirmedRow(html)).toContain(`dateTime="${CONFIRMED}"`);
  expect(status(html)).toBe("Connected");
});

test("a preview printing the committed pair keeps the confirmation, aged from the later clock", () => {
  blendPreview = preview(.6002); // prints 60.0 / 40.0, the committed pair
  const html = draw();
  expect(delivery(html)).toBe("dnpl");
  expect(observedRow(html)).toContain(`dateTime="${OBSERVED}"`);
  expect(confirmedRow(html)).toContain(`dateTime="${CONFIRMED}"`);
  expect(status(html)).toBe("Connected");
});

test("a preview printing another number is never called confirmed and keeps its own clock", () => {
  blendPreview = preview(.64); // prints 64.0 / 36.0 over a committed 60.0 / 40.0
  const html = draw();
  expect(delivery(html)).toBe("dnpl");
  expect(heroDigits(html)).toEqual(["64", "36"]);
  expect(confirmedRow(html)).toBeNull();
  expect(observedRow(html)).toContain(`dateTime="${OBSERVED}"`);
  expect(status(html)).toBe("Connected · waiting");
});

test("'the same number' is the printed number, at the precision this reader sees", () => {
  blendPreview = preview(.603);
  // Tenths on (the default): 60.3 is not the committed 60.0.
  const tenths = draw();
  expect(confirmedRow(tenths)).toBeNull();
  expect(status(tenths)).toBe("Connected · waiting");
  // Opted out (`?tenths=off`): both print 60 / 40, so it is the confirmed number.
  tenthsOn = false;
  const whole = draw();
  expect(heroDigits(whole)).toEqual(["60", "40"]);
  expect(confirmedRow(whole)).toContain(`dateTime="${CONFIRMED}"`);
  expect(status(whole)).toBe("Connected");
});

test("once a different-number preview expires, the committed number is confirmed again", () => {
  blendPreview = preview(.64);
  expect(confirmedRow(draw())).toBeNull();
  blendPreviewNow = NOW + 1000;
  const html = draw();
  expect(delivery(html)).toBe("committed");
  expect(confirmedRow(html)).toContain(`dateTime="${CONFIRMED}"`);
  expect(status(html)).toBe("Connected");
});

test("no confirmed_at (an old server) is today's page with or without a preview", () => {
  confirmedAt = null;
  expect(confirmedRow(draw())).toBeNull();
  blendPreview = preview(.6002);
  const html = draw();
  expect(confirmedRow(html)).toBeNull();
  expect(status(html)).toBe("Connected · waiting");
});
