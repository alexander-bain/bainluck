import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { fetchEvents, setAuthTokenGetter } from "@/lib/api";

let mockFetchers: Array<() => Promise<unknown>> = [];
let mockEvents: unknown[] = [];
jest.mock("swr", () => ({
  __esModule: true,
  default: (key: unknown, fetcher: () => Promise<unknown>) => {
    if (!key) return {};
    if (key === "sports") return { data: { sports: [] } };
    mockFetchers.push(fetcher);
    return { data: { events: mockEvents }, isLoading: false, mutate: () => {} };
  },
}));
jest.mock("@/hooks", () => ({
  usePageTracking: () => undefined,
  useScrollDepth: () => undefined,
  useEngagementTime: () => undefined,
  useAnalytics: () => ({ trackEventCardClick: () => undefined }),
}));
import SportPage from "@/app/sports/[key]/page";
import specimen from "../fixtures/leagueNflResults20260922.json";

const originalFetch = global.fetch;
const now = Date.parse("2026-09-22T12:00:00Z");
beforeEach(() => {
  jest.useFakeTimers({ now, doNotFake: ["nextTick"] });
  mockFetchers = [];
  mockEvents = [];
  setAuthTokenGetter(null);
  global.fetch = jest.fn().mockResolvedValue({
    ok: true, json: async () => ({ events: [] }),
  });
});
afterEach(() => {
  global.fetch = originalFetch;
  jest.useRealTimers();
});
function requests(): URL[] {
  return (global.fetch as jest.Mock).mock.calls.map(([url]) => new URL(url));
}

test("both league requests retain a week of results without expanding the normal upcoming window", async () => {
  // Empty near-term schedule activates the existing off-season request too.
  renderToStaticMarkup(<SportPage params={{ key: "americanfootball_nfl" }} />);
  expect(mockFetchers).toHaveLength(2);
  await Promise.all(mockFetchers.map(fetcher => fetcher()));
  expect(requests().map(url => url.searchParams.get("days"))).toEqual(["14", "90"]);
  expect(requests().map(url => url.searchParams.get("past_days"))).toEqual(["7", "7"]);
  expect(requests().map(url => url.searchParams.get("sport"))).toEqual([
    "americanfootball_nfl", "americanfootball_nfl",
  ]);
});

test("an active league keeps one request and the 14-day upcoming window", async () => {
  mockEvents = [{ id: 1, sport: "americanfootball_nfl", home_team: "Home", away_team: "Away",
    status: "scheduled", commence_time: new Date(now + 86400000).toISOString() }];
  renderToStaticMarkup(<SportPage params={{ key: "americanfootball_nfl" }} />);
  expect(mockFetchers).toHaveLength(1);
  await mockFetchers[0]();
  expect(requests()[0].searchParams.get("days")).toBe("14");
  expect(requests()[0].searchParams.get("past_days")).toBe("7");
});

test("fetchEvents preserves an explicit zero-day results window", async () => {
  const params = { sport: "tennis_atp", days: 14, past_days: 0 };
  await fetchEvents(params);
  expect(requests()[0].searchParams.get("past_days")).toBe("0");
});

test("callers that omit past_days retain the backend default", async () => {
  await fetchEvents({ sport: "tennis_atp", days: 14 });
  expect(requests()[0].searchParams.has("past_days")).toBe(false);
});

// Production payload replay: request the actual page fetcher, then render its result.
// Keeps the request-to-render boundary in the regression, not just the chosen constant.
test("the NFL page renders all 17 available week results rather than only the two night games", async () => {
  global.fetch = jest.fn().mockImplementation(async (url: string) => ({
    ok: true,
    json: async () => ({ events: new URL(url).searchParams.get("past_days") === "7"
      ? specimen.events.week : specimen.events.default }),
  }));
  mockEvents = specimen.events.default;
  renderToStaticMarkup(<SportPage params={{ key: "americanfootball_nfl" }} />);
  const response = await mockFetchers[0]() as { events: unknown[] };
  mockEvents = response.events;
  const html = renderToStaticMarkup(<SportPage params={{ key: "americanfootball_nfl" }} />);
  const renderedIds = new Set([...html.matchAll(/href="\/events\/(\d+)"/g)].map(match => Number(match[1])));
  const finals = specimen.events.week.filter(event => event.status === "completed");
  expect(finals).toHaveLength(17);
  expect(finals.every(event => renderedIds.has(event.id))).toBe(true);
  const upcomingBefore = specimen.events.default.filter(event => event.status === "scheduled").map(event => event.id);
  const upcomingAfter = specimen.events.week.filter(event => event.status === "scheduled").map(event => event.id);
  expect([...upcomingAfter].sort()).toEqual([...upcomingBefore].sort());
  expect(upcomingBefore.every(id => renderedIds.has(id))).toBe(true);
});

test.each(["baseball_mlb", "tennis_atp"])("%s retains its existing results window and request count", async sport => {
  renderToStaticMarkup(<SportPage params={{ key: sport }} />);
  expect(mockFetchers).toHaveLength(2);
  await Promise.all(mockFetchers.map(fetcher => fetcher()));
  expect(requests().map(url => url.searchParams.get("past_days"))).toEqual(["1", "1"]);
});

test("college football retains Saturday results through the week", async () => {
  renderToStaticMarkup(<SportPage params={{ key: "americanfootball_ncaaf" }} />);
  await Promise.all(mockFetchers.map(fetcher => fetcher()));
  expect(requests().map(url => url.searchParams.get("past_days"))).toEqual(["7", "7"]);
});
