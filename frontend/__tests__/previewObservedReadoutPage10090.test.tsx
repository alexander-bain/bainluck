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
let historyPayload: { aggregate_line: { timestamp: string; home_probability: number }[] } & Record<string, unknown> | undefined;
let chartPoints: { timestamp: string; home_probability: number; rev?: Record<string, number> }[];
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
  useLiveEventStream: () => ({ frame: null, connected: true, status: "open", blendPreview, blendPreviewNow, chartPoints }),
}));
// #10090: the real chart, so its own endpoint attributes are observable; every
// other client-only module stays unmounted exactly as in a server render.
jest.mock("next/dynamic", () => ({
  __esModule: true,
  default: (loader: () => unknown) => {
    if (!/["/]OddsChart"/.test(loader.toString())) return () => null;
    // eslint-disable-next-line @typescript-eslint/no-var-requires
    return require("@/components/OddsChart").default;
  },
}));
jest.mock("next/navigation", () => ({
  useRouter: () => ({ push: () => {}, replace: () => {}, prefetch: () => {} }),
  usePathname: () => "/events/14632820", useSearchParams: () => new URLSearchParams(),
  useParams: () => ({ id: "14632820" }),
}));
// #10090 — tenths are on by default on the event page. This file pins preview reporting when the printed percent is unchanged,
// which reads the whole-number hero, so it renders as a reader who opened
// `?tenths=off` (the tenths markup is `tenthsOptInOn10090`'s to pin).
jest.mock("@/lib/tenthsOptIn", () => ({
  __esModule: true,
  ...jest.requireActual("@/lib/tenthsOptIn"),
  useTenthsOptIn: () => false,
}));

// eslint-disable-next-line @typescript-eslint/no-var-requires
const EventDetailPage = require("@/app/events/[id]/page").default;
// eslint-disable-next-line @typescript-eslint/no-var-requires
const { AnalyticsProvider } = require("@/components/Analytics");
function draw() {
  return renderToStaticMarkup(<AnalyticsProvider><EventDetailPage params={{id: String(ID)}} /></AnalyticsProvider>);
}
// Alex 2026-10-31: the pop-up has two rows, "Latest source update" and "Score".
// The delivery state and visit count stay on the data attributes only.
function priceDetails(html: string) {
  return html.match(/Latest source update<\/dt><dd>(.*?)<\/dd>/)![1];
}
function scoreDetails(html: string) {
  return html.match(/Score<\/dt><dd>(.*?)<\/dd>/)?.[1];
}
beforeEach(() => {
  jest.spyOn(Date, "now").mockReturnValue(NOW);
  eventPayload = event(); blendPreview = null; blendPreviewNow = NOW; historyPayload = undefined; chartPoints = [];
});
afterEach(() => jest.restoreAllMocks());
// The real chart's layout hooks warn in a server render; nothing else is muted.
const realConsoleError = console.error;
beforeAll(() => {
  console.error = (...args: unknown[]) => {
    if (typeof args[0] === "string" && args[0].includes("useLayoutEffect does nothing on the server")) return;
    realConsoleError(...args);
  };
});
afterAll(() => { console.error = realConsoleError; });

test("the real page reports the displayed preview observation before any commit, even when rounded percent is unchanged", () => {
  const before = draw();
  expect(priceDetails(before)).toContain(`dateTime="${COMMITTED}"`);
  blendPreview = preview();
  const after = draw();
  expect(before).toContain('data-probability="0.6"');
  expect(before).toContain('data-observation-delivery="committed"');
  expect(before).toContain('data-observation-count="1"');
  expect(after).toContain('data-probability="0.601"');
  expect(after).toContain('data-observation-delivery="dnpl"');
  expect(after).toContain(`data-observation-at="${OBSERVED}"`);
  expect(after).toContain(`data-observation-event-id="${ID}"`);
  expect(before.match(/data-hero-digits="">([^<]+)/g)).toEqual(after.match(/data-hero-digits="">([^<]+)/g));
  expect(after).toContain('data-hero-digits="">60</span>');
  expect(priceDetails(after)).toContain(`dateTime="${OBSERVED}"`);
  expect(priceDetails(after)).toContain("8s ago");
  expect(priceDetails(after)).not.toContain(COMMITTED);
  expect(scoreDetails(before)).toContain(`dateTime="${SCORE}"`);
  expect(scoreDetails(after)).toBe(scoreDetails(before));
  for (const html of [before, after]) expect(html).not.toContain("Oldest on screen");
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
  if (reason === "terminal") expect(html).not.toContain("Latest source update");
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

// Alex 2026-10-31: the pop-up no longer prints the delivery state or the visit
// count. Both stay on the data attributes the capture tool reads, unchanged.
test("the delivery state and visit count stay on the data attributes, not in the pop-up", () => {
  const committed = draw();
  blendPreview = preview();
  const dnpl = draw();
  blendPreview = preview(null, .7);
  const unknownClock = draw();
  eventPayload.hero_probability_source = "opening"; blendPreview = null;
  const unknown = draw();
  expect(committed).toContain('data-observation-delivery="committed"');
  expect(committed).toContain('data-observation-count="1"');
  expect(dnpl).toContain('data-observation-delivery="dnpl"');
  expect(unknownClock).toContain('data-observation-count="0"');
  expect(unknown).toContain('data-observation-delivery="unknown"');
  for (const html of [committed, dnpl, unknownClock, unknown]) {
    expect(html).not.toMatch(/Current probability delivery|Published update|Live preview|Delivery unknown|DNPL|Committed delivery/);
    expect(html).not.toMatch(/Readings shown this visit|first reading plus newer updates|Observations shown/);
  }
});

// ── #10090: which state each surface ADOPTED, headline and chart separately ──
const attr = (html: string, name: string) => html.match(new RegExp(`${name}="([^"]*)"`))?.[1];
const hero = (html: string) => html.match(/<div[^>]*data-testid="event-hero-probability"[^>]*>/)![0];
const chartRoot = (html: string) => html.match(/<div[^>]*data-callout-at="[^"]*"[^>]*>/)?.[0] ?? "";
const AUTH = { incarnation: "7", namespace: "0b6c3d8e-4b5f-4a51-9b55-2b1e8f6b0c11" };
const SESSION = "5d1f9b52-6a4e-4f0e-8c33-9c2a1b7e4d10";
const T1 = new Date(NOW - 100_000).toISOString();
const T2 = new Date(NOW - 50_000).toISOString();
function blendHistory() {
  const sourcePoints = (p: number) => [{ timestamp: new Date(NOW - 300_000).toISOString(), home_probability: p },
    { timestamp: COMMITTED, home_probability: p }];
  return {
    event_id: ID, aggregate_line: [{ timestamp: COMMITTED, home_probability: .6 }],
    history_fold_revision: { [ID]: 10 }, blend_edge_fold_revision: { [ID]: 10 },
    win_prob_history: { kalshi: sourcePoints(.6), polymarket: sourcePoints(.6) },
    win_prob_sources: ["kalshi", "polymarket"],
  };
}
function v3Preview(seq: number, p: number) {
  const held = preview(OBSERVED, p)!;
  return { ...held, seq, receivedAt: 1234.5, authority: { ...AUTH, session: SESSION, fold: false } };
}

test("repeated equal values: the headline names each committed revision while data-probability cannot", () => {
  const first = draw();
  eventPayload.blend_fold_revision = { [ID]: 11 };
  const second = draw();
  expect(attr(hero(first), "data-probability")).toBe(attr(hero(second), "data-probability"));
  expect(attr(hero(first), "data-display-basis")).toBe("committed");
  expect(attr(hero(first), "data-display-state")).toBe(`fold:${ID}=10`);
  expect(attr(hero(second), "data-display-state")).toBe(`fold:${ID}=11`);
  expect(attr(hero(second), "data-display-observed-at")).toBe(COMMITTED);
  expect(attr(hero(second), "data-display-received")).toBe("");
});

test("an admitted equal-valued v3 preview is named by its authority, session and sequence; refused or expired previews are not", () => {
  const committed = draw();
  blendPreview = v3Preview(1, .6);
  const shown = draw();
  expect(attr(hero(shown), "data-probability")).toBe(attr(hero(committed), "data-probability"));
  expect(attr(hero(shown), "data-display-basis")).toBe("preview");
  expect(attr(hero(shown), "data-display-state")).toBe(`v3:7:${AUTH.namespace}:${SESSION}:e1.s1:fold:${ID}=10`);
  expect(attr(hero(shown), "data-display-received")).toBe("1234.5");
  expect(attr(hero(shown), "data-display-observed-at")).toBe(OBSERVED);
  blendPreview = v3Preview(2, .6);
  expect(attr(hero(draw()), "data-display-state")).toBe(`v3:7:${AUTH.namespace}:${SESSION}:e1.s2:fold:${ID}=10`);
  // Expired, superseded by a newer commit, wrong status: committed truth with
  // ITS revision, never the preview's borrowed identity.
  for (const refuse of ["expired", "newer commit", "wrong status"]) {
    eventPayload = event(); blendPreview = v3Preview(2, .6); blendPreviewNow = NOW;
    if (refuse === "expired") blendPreviewNow = NOW + 1000;
    if (refuse === "newer commit") eventPayload.blend_fold_revision = { [ID]: 11 };
    if (refuse === "wrong status") blendPreview.status = "scheduled";
    const html = hero(draw());
    expect([refuse, attr(html, "data-display-basis")]).toEqual([refuse, "committed"]);
    expect(attr(html, "data-display-state")).toBe(`fold:${ID}=${refuse === "newer commit" ? 11 : 10}`);
    expect(attr(html, "data-display-received")).toBe("");
  }
});

test("a fallback headline has no adopted blend identity", () => {
  eventPayload.hero_probability_source = "opening";
  historyPayload = { aggregate_line: [{ timestamp: COMMITTED, home_probability: .6 }] };
  const html = hero(draw());
  expect(attr(html, "data-display-basis")).toBe("unavailable");
  expect(attr(html, "data-display-state")).toBe("");
});

test("the chart names its own endpoint: repeated equal pushes by revision, separately from the headline", () => {
  historyPayload = blendHistory();
  eventPayload.blend_fold_revision = { [ID]: 11 };
  eventPayload.hero_probability_observed_at = T1;
  chartPoints = [{ timestamp: T1, home_probability: .6, rev: { [ID]: 11 } }];
  const first = draw();
  eventPayload.blend_fold_revision = { [ID]: 12 };
  eventPayload.hero_probability_observed_at = T2;
  chartPoints = [...chartPoints, { timestamp: T2, home_probability: .6, rev: { [ID]: 12 } }];
  const second = draw();
  expect(attr(chartRoot(first), "data-callout-label")).toBe(attr(chartRoot(second), "data-callout-label"));
  expect(attr(chartRoot(first), "data-chart-endpoint-at")).toBe(T1);
  expect(attr(chartRoot(first), "data-chart-endpoint-basis")).toBe("push");
  expect(attr(chartRoot(first), "data-chart-endpoint-state")).toBe(`fold:${ID}=11`);
  expect(attr(chartRoot(second), "data-chart-endpoint-at")).toBe(T2);
  expect(attr(chartRoot(second), "data-chart-endpoint-state")).toBe(`fold:${ID}=12`);
  expect(attr(chartRoot(second), "data-chart-history")).toBe(`rev=fold:${ID}=10;through=${COMMITTED}`);
  expect(attr(hero(second), "data-display-state")).toBe(`fold:${ID}=12`);
});

test("a preview on the chart is the preview; once it expires the chart reports the committed point it actually draws", () => {
  historyPayload = blendHistory();
  blendPreview = v3Preview(3, .6);
  const shown = draw();
  expect(attr(chartRoot(shown), "data-chart-endpoint-at")).toBe(OBSERVED);
  expect(attr(chartRoot(shown), "data-chart-endpoint-basis")).toBe("preview");
  expect(attr(chartRoot(shown), "data-chart-endpoint-state")).toBe(attr(hero(shown), "data-display-state"));
  blendPreviewNow = NOW + 1000;
  const expired = draw();
  expect(attr(chartRoot(expired), "data-chart-endpoint-at")).toBe(COMMITTED);
  expect(attr(chartRoot(expired), "data-chart-endpoint-basis")).toBe("history");
  expect(attr(chartRoot(expired), "data-chart-endpoint-state")).toBe(`fold:${ID}=10`);
  expect(attr(hero(expired), "data-display-basis")).toBe("committed");
});

test("a pushed point the chart refuses is not its endpoint; the chart reports what it still draws", () => {
  historyPayload = blendHistory();
  // A different row's revision is incomparable with the held one-row fold.
  chartPoints = [{ timestamp: T2, home_probability: .7, rev: { [ID + 1]: 99 } }];
  const html = chartRoot(draw());
  expect(attr(html, "data-chart-endpoint-at")).toBe(COMMITTED);
  expect(attr(html, "data-chart-endpoint-basis")).toBe("history");
  expect(attr(html, "data-chart-endpoint-state")).toBe(`fold:${ID}=10`);
});
