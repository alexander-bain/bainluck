/** Real EventPage and its real clock control; only transport/data reads are mocked. */
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { previewAfter, type BlendPreviewState } from "@/lib/blendPreview";

const ID = 14632820;
const NOW = Date.UTC(2026, 9, 20, 20);
const COMMITTED = new Date(NOW - 120_000).toISOString();
const OBSERVED = new Date(NOW - 8_000).toISOString();
const SCORE = new Date(NOW - 60_000).toISOString();
let eventPayload: ReturnType<typeof event>;
let blendPreview: BlendPreviewState | null;
let blendPreviewNow: number;
let historyPayload: { aggregate_line: { timestamp: string; home_probability: number }[] } | undefined;
function event() {
  return {
    id: ID, sport: "americanfootball_nfl", sport_key: "americanfootball_nfl",
    home_team: "Los Angeles Rams", away_team: "San Francisco 49ers",
    home_score: 7, away_score: 10, status: "live",
    commence_time: new Date(NOW - 3_600_000).toISOString(),
    score_observed_at: SCORE,
    hero_probability: .6, hero_probability_away: .4,
    hero_probability_source: "blend", hero_probability_observed_at: COMMITTED,
    blend_fold_revision: { [ID]: 10 } as Record<string, number>,
    win_probability_sources: {
      kalshi: { value: .6, display_name: "Kalshi", type: "market", color: "#22c55e", updated_at: COMMITTED },
    },
  };
}
function preview(clock: unknown = OBSERVED, p = .601) {
  return previewAfter(null, {
    event_id: ID, p, status: "live", observed_at: new Date(NOW).toISOString(),
    display_observed_at: clock as string,
    preview: { kind: "blend", epoch: 1, seq: 1, base_rev: 10, ttl_ms: 1000 },
  }, ID, NOW);
}

jest.mock("swr", () => ({
  __esModule: true,
  default: (key: unknown) => ({
    data: Array.isArray(key) ? key[0] === "event" ? eventPayload : key[0] === "history" ? historyPayload : undefined : undefined,
    error: undefined, isLoading: false, mutate: () => undefined,
  }),
}));
jest.mock("@/hooks", () => ({
  ...jest.requireActual("@/hooks"),
  usePageTracking: () => undefined, useScrollDepth: () => undefined, useEngagementTime: () => undefined,
  usePinnedEvents: () => ({ isPinned: () => false, togglePin: () => undefined, isMaxReached: false }),
}));
jest.mock("@/hooks/useLiveEventStream", () => ({
  useLiveEventStream: () => ({ frame: null, connected: true, status: "open", blendPreview, blendPreviewNow }),
}));
jest.mock("next/navigation", () => ({
  useRouter: () => ({ push: () => {}, replace: () => {}, prefetch: () => {} }),
  usePathname: () => "/events/14632820", useSearchParams: () => new URLSearchParams(),
  useParams: () => ({ id: "14632820" }),
}));
// eslint-disable-next-line @typescript-eslint/no-var-requires
const EventDetailPage = require("@/app/events/[id]/page").default;
// eslint-disable-next-line @typescript-eslint/no-var-requires
const { AnalyticsProvider } = require("@/components/Analytics");
function draw() {
  return renderToStaticMarkup(<AnalyticsProvider><EventDetailPage params={{id: String(ID)}} /></AnalyticsProvider>);
}
function priceDetails(html: string) {
  return html.match(/Probability observed<\/dt><dd>(.*?)<\/dd>/)![1];
}
function deliveryWords(html: string) {
  return html.match(/Current probability delivery<\/dt><dd>(.*?)<\/dd>/)?.[1];
}
function scoreDetails(html: string) {
  return html.match(/Score confirmed<\/dt><dd>(.*?)<\/dd>/)?.[1];
}
beforeEach(() => {
  jest.spyOn(Date, "now").mockReturnValue(NOW);
  eventPayload = event(); blendPreview = null; blendPreviewNow = NOW; historyPayload = undefined;
});
afterEach(() => jest.restoreAllMocks());

test("the real page reports the displayed preview observation before any commit, even when rounded percent is unchanged", () => {
  const before = draw();
  expect(priceDetails(before)).toContain(`dateTime="${COMMITTED}"`);
  blendPreview = preview();
  const after = draw();
  expect(before).toContain('data-probability="0.6"');
  expect(before).toContain('data-observation-delivery="committed"');
  expect(before).toContain('data-observation-count="1"');
  expect(deliveryWords(before)).toBe("Published update");
  expect(after).toContain('data-probability="0.601"');
  expect(after).toContain('data-observation-delivery="dnpl"');
  expect(after).toContain(`data-observation-at="${OBSERVED}"`);
  expect(deliveryWords(after)).toBe("Live preview");
  expect(after).toContain(`data-observation-event-id="${ID}"`);
  expect(before.match(/data-hero-digits="">([^<]+)/g)).toEqual(after.match(/data-hero-digits="">([^<]+)/g));
  expect(after).toContain('data-hero-digits="">60</span>');
  expect(priceDetails(after)).toContain(`dateTime="${OBSERVED}"`);
  expect(priceDetails(after)).toContain("8s ago");
  expect(priceDetails(after)).not.toContain(COMMITTED);
  expect(scoreDetails(before)).toContain(`dateTime="${SCORE}"`);
  expect(scoreDetails(after)).toBe(scoreDetails(before));
  expect(before).toContain("Oldest on screen</dt><dd>The probability</dd>");
  expect(after).toContain("Oldest on screen</dt><dd>The score</dd>");
  expect(eventPayload.hero_probability).toBe(.6);
  expect(eventPayload.hero_probability_observed_at).toBe(COMMITTED);
});

test.each([null, "", "bad-time", 42])("an admitted preview with unknown clock %p says unavailable, never committed or attempt time", clock => {
  blendPreview = preview(clock, .7);
  const html = draw();
  expect(priceDetails(html)).toBe("<span>Time unavailable</span>");
  expect(html).not.toContain("Oldest on screen");
  expect(html).toContain('data-observation-at=""');
  expect(html).toContain('data-observation-count="0"');
  expect(html).toContain('data-observation-delivery="dnpl"');
});

test.each(["expiry", "reset", "newer commit", "terminal", "wrong event", "wrong status", "folded hero", "non-blend"])("%s restores the committed observation clock with committed truth", reason => {
  blendPreview = preview();
  if (reason === "expiry") blendPreviewNow = NOW + 1000;
  if (reason === "reset") blendPreview = null;
  if (reason === "newer commit") eventPayload.blend_fold_revision = { [ID]: 11 };
  if (reason === "terminal") eventPayload.status = "completed";
  if (reason === "wrong event") blendPreview!.eventId = ID + 1;
  if (reason === "wrong status") blendPreview!.status = "scheduled";
  if (reason === "folded hero") eventPayload.blend_fold_revision = { [ID]: 10, 2: 4 };
  if (reason === "non-blend") eventPayload.hero_probability_source = "opening";
  const html = draw();
  // A cold final page has no connection control; its final hero is the answer.
  // The mounted live -> final transition is covered by the real stream test.
  if (reason === "terminal") expect(html).not.toContain("Probability observed");
  else if (reason === "non-blend") {
    expect(priceDetails(html)).toBe("<span>Time unavailable</span>");
    expect(html).toContain('data-observation-delivery="unknown"');
    expect(html).toContain('data-observation-at=""');
    expect(html).toContain('data-observation-count="0"');
    expect(html).not.toContain("Oldest on screen");
  } else {
    expect(priceDetails(html)).toContain(`dateTime="${COMMITTED}"`);
    expect(html).toContain('data-observation-delivery="committed"');
  }
});


test("a folded redirect counts the displayed canonical observation under the URL page session", () => {
  eventPayload.id = ID + 1;
  const html = draw();
  expect(html).toContain('data-observation-count="1"');
  expect(html).toContain(`data-observation-event-id="${ID}"`);
  expect(html).toContain(`data-observation-at="${COMMITTED}"`);
});

test("a missing event renders no observation counter", () => {
  eventPayload = undefined as unknown as ReturnType<typeof event>;
  expect(draw()).not.toContain('data-observation-count');
});


test("unchanged history selection never borrows advancing source clocks or counts them as observations", () => {
  eventPayload.hero_probability_source = "opening";
  historyPayload = { aggregate_line: [{ timestamp: COMMITTED, home_probability: .6 }] };
  for (const clock of [COMMITTED, OBSERVED, new Date(NOW).toISOString()]) {
    eventPayload.hero_probability_observed_at = clock;
    eventPayload.win_probability_sources.kalshi.updated_at = clock;
    const html = draw();
    expect(html).toContain('data-probability="0.6"');
    expect(priceDetails(html)).toBe("<span>Time unavailable</span>");
    expect(html).toContain('data-observation-at=""');
    expect(html).toContain('data-observation-count="0"');
    expect(html).toContain('data-observation-delivery="unknown"');
    expect(html).not.toContain("Oldest on screen");
  }
});

// Reader words only; the typed state, its data attribute and the capture tool
// that reads it are unchanged. Receipts recorded before the wording change
// printed "DNPL active" / "Committed delivery" for these same two states.
test("the delivery row names each unchanged state in reader words", () => {
  const committed = draw();
  blendPreview = preview();
  const dnpl = draw();
  eventPayload.hero_probability_source = "opening"; blendPreview = null;
  const unknown = draw();
  expect(committed).toContain('data-observation-delivery="committed"');
  expect(deliveryWords(committed)).toBe("Published update");
  expect(dnpl).toContain('data-observation-delivery="dnpl"');
  expect(deliveryWords(dnpl)).toBe("Live preview");
  expect(unknown).toContain('data-observation-delivery="unknown"');
  expect(deliveryWords(unknown)).toBe("Delivery unknown");
  for (const html of [committed, dnpl, unknown]) {
    expect(html).not.toMatch(/DNPL|Committed delivery/);
  }
});
