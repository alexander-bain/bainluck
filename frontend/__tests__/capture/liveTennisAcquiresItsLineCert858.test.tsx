/**
 * CERT-858 — A CONNECTED LIVE TENNIS PAGE ACQUIRES ITS LINE, ON A RENDER.
 *
 * ═══ WHAT THE CERT FOUND, AND WHY A PURE TEST DID NOT ═══
 *
 * CERT-854's repair made the poll rule callable and asserted it hard. Every
 * one of those assertions handed the rule a payload that ALREADY carried a
 * linescore, so the one input that mattered was never asked:
 *
 *     connected stream + status live + tennis + NO line yet  ->  0
 *
 * `0` is not a frozen score. It is a page that can never acquire one. A reader
 * who opens a live match in the seconds before `poll_live_tennis_scores` has
 * written its first line — or on a match whose first game is still being
 * played, which is every match once — gets a probability that ticks and a
 * scoreline that never appears at all, for as long as they watch.
 *
 * ═══ WHY THIS FILE IS A RENDER AND NOT A SEVENTH PURE ASSERTION ═══
 *
 * `__tests__/lib/liveDetailRefresh.test.ts` now covers that input directly, and
 * it should. But a pure test proves the RULE; it cannot prove the page hands
 * the rule the right facts, and the CERT-858 defect was exactly that — the
 * call site passed `hasLinescore: Boolean(data?.linescore)` and nothing else,
 * so no rule written behind it could have recovered the sport. A source scan
 * for `sport: data?.sport` is defeated by passing the wrong field under the
 * right name.
 *
 * So this drives `app/events/[id]/page.tsx` ITSELF: the real component, its
 * real SWR config, its real stream hook reporting connected. `refreshInterval`
 * is a function of the served data, so the captured config can be invoked with
 * the first-acquisition payload and the answer read. Then the second render
 * proves the acquired line reaches the HTML — a poll that fetches a score the
 * page does not draw is the same blank to the reader.
 *
 * There is no jsdom in this harness ([[no jsdom, `testEnvironment: node`]]) and
 * therefore no effects and no timers: this file does not claim SWR fires the
 * interval, only that the page ASKS for a non-zero one in the state where it
 * used to ask for none. The interval mechanism is SWR's and is not ours to
 * re-test.
 *
 *   TZ=UTC npx jest --testPathPatterns=liveTennisAcquiresItsLine
 */

import React from "react";

/** The three GA4 hooks every page calls before any conditional return. */
const ANALYTICS_HOOKS = {
  usePageTracking: () => {},
  useScrollDepth: () => {},
  useEngagementTime: () => {},
  useAnalytics: () => ({
    track: () => {},
    trackNavigationClick: () => {},
    recordEvent: () => {},
  }),
  usePinnedEvents: () => ({
    isPinned: () => false,
    togglePin: () => {},
    isMaxReached: false,
  }),
};

/** ESPN competition 182709, live 2026-09-03: Popyrin 6-2 6-7(4) 6-5 Tabilo. */
const POPYRIN_LINE = {
  source: "espn",
  unit: "games",
  state: "in_progress",
  completion: "unknown",
  status_detail: "3rd Set",
  was_suspended: false,
  sets: [
    { home: 6, away: 2, home_tiebreak: null, away_tiebreak: null, won_by: "home" },
    // BOTH sides' tiebreak points, which is what ESPN publishes; the component
    // prints only the LOSER's. Popyrin lost this one 6-7, so the visible 4 is
    // his and Tabilo's 7 must not appear.
    { home: 6, away: 7, home_tiebreak: 4, away_tiebreak: 7, won_by: "away" },
    { home: 6, away: 5, home_tiebreak: null, away_tiebreak: null, won_by: null },
  ],
  current_set: 3,
  sets_won: { home: 1, away: 1 },
  games: { home: 18, away: 14 },
  line: "6-2, 6-7(4), 6-5",
  observed_at: "2026-09-03T21:52:00+00:00",
};

/**
 * The event payload `GET /api/events/{id}` serves for a live match.
 *
 * `linescore` is passed separately rather than baked in because the ABSENCE of
 * the key is the state under test — the backend omits it, it does not send
 * `null`, and a fixture that always carried the key could not express the
 * first-acquisition moment at all.
 */
function liveEvent(
  sport: string,
  linescore: Record<string, unknown> | undefined,
): Record<string, unknown> {
  return {
    id: 15293999,
    external_id: "espn:182709",
    sport,
    home_team: "Alexei Popyrin",
    away_team: "Alejandro Tabilo",
    // Well in the past: the page's `hasStarted` gate reads this, and a live
    // status with a future commence_time is deliberately NOT treated as live.
    commence_time: "2026-09-03T19:00:00+00:00",
    status: "live",
    home_score: 1,
    away_score: 1,
    ...(linescore === undefined ? {} : { linescore }),
    win_probability_sources: {},
  };
}

/** A settled SWR result. */
const settled = (data: unknown) => ({
  data,
  error: undefined,
  isLoading: false,
  mutate: () => {},
});

/**
 * The two sibling responses the page fetches beside the event.
 *
 * Transcribed from the routes that produce them rather than fitted to whatever
 * stops the render crashing — CERT-569's finding on the sibling capture file
 * was a fixture reached by the ABSENCE of a field, which put the page in a
 * state no real reader can occupy. Both of these are the genuine empty shape
 * for a live tennis match, which has neither odds history nor game markets.
 */
/** `backend/app/routes/events.py`, the `if not markets` early return. */
const NO_GAME_MARKETS = {
  event_id: 15293999,
  totals: [],
  player_props: [],
  spreads: [],
  matchups: [],
  other: [],
  pace: null,
  props_script: [],
};
/** `GET /api/events/{id}/history` with no snapshots yet. */
const NO_HISTORY = {
  event_id: 15293999,
  home_team: "Alexei Popyrin",
  away_team: "Alejandro Tabilo",
  history: [],
  aggregate_line: [],
  points: 0,
};

type RefreshRule = (data: unknown) => number;

interface Rendered {
  markup: string;
  /** The page's OWN `refreshInterval`, captured off the `["event", id]` call. */
  eventRefreshInterval: RefreshRule;
}

/**
 * Render the real event page with a CONNECTED stream and one served payload.
 *
 * `jest.doMock`, not `jest.mock`: the latter is hoisted to file scope and every
 * render in this file needs its own graph. `react-dom/server` is required
 * INSIDE the isolated registry because `isolateModules` hands the page a fresh
 * `react`, and a renderer bound to the outer copy reads a null hook dispatcher.
 */
function renderEventPage(event: Record<string, unknown>): Rendered {
  let markup = "";
  let captured: RefreshRule | null = null;

  jest.isolateModules(() => {
    jest.doMock("@/hooks", () => ANALYTICS_HOOKS);
    jest.doMock("next/navigation", () => ({
      useRouter: () => ({ push: () => {}, replace: () => {}, prefetch: () => {} }),
      useSearchParams: () => new URLSearchParams(""),
      useParams: () => ({ id: String(event.id) }),
    }));
    // THE STREAM IS UP. This is the state live/034 S2 silences the poll in, and
    // therefore the only state in which the CERT-858 defect exists at all.
    jest.doMock("@/hooks/useLiveEventStream", () => ({
      useLiveEventStream: () => ({ frame: null, connected: true }),
    }));
    jest.doMock("@/lib/api", () => ({
      API_URL: "https://api.example.test",
      fetchEvent: () => Promise.resolve(event),
      fetchEventHistory: () => Promise.resolve(NO_HISTORY),
      fetchGameMarkets: () => Promise.resolve(NO_GAME_MARKETS),
      fetchTeamProgression: () => Promise.resolve({}),
      fetchEventTournament: () => Promise.resolve({}),
      formatProbability: (p: number) => `${Math.round(p * 100)}%`,
    }));
    jest.doMock("swr", () => ({
      __esModule: true,
      default: (key: unknown, _fetcher: unknown, config: Record<string, unknown>) => {
        const resource = Array.isArray(key) ? key[0] : key;
        if (resource === "event") {
          // THE CAPTURE. This is the page's own config object, not a copy of
          // the rule — if the page stops calling `liveDetailRefreshInterval`,
          // or calls it with the wrong fields, this function's ANSWER changes
          // and the assertions below fail. That is the whole point of taking
          // it from here instead of importing the rule.
          captured = config?.refreshInterval as RefreshRule;
          return settled(event);
        }
        if (resource === "history") return settled(NO_HISTORY);
        if (resource === "game-markets") return settled(NO_GAME_MARKETS);
        return settled(undefined);
      },
    }));

    /* eslint-disable @typescript-eslint/no-var-requires */
    const render = require("react-dom/server").renderToStaticMarkup;
    const Page = require("@/app/events/[id]/page").default;
    /* eslint-enable @typescript-eslint/no-var-requires */
    markup = render(React.createElement(Page, { params: { id: String(event.id) } }));
  });

  if (typeof captured !== "function") {
    throw new Error(
      "the event page's SWR config carried no refreshInterval function — " +
        "the capture, not the ship, is broken",
    );
  }
  return { markup, eventRefreshInterval: captured };
}

/** Strip tags so an assertion reads what a PERSON reads. */
function visibleText(markup: string): string {
  return markup
    .replace(/<[^>]*>/g, " ")
    .replace(/&#x27;|&apos;/g, "'")
    .replace(/&amp;/g, "&")
    .replace(/\s+/g, " ")
    .trim();
}

describe("a live tennis page with a connected stream and no line yet", () => {
  it("asks for a poll — the request that goes and gets the first line", () => {
    /** THE REGRESSION. Against the shipped rule this is `0`, and a `0` here is
        a live tennis page that never shows a score at all. */
    const { eventRefreshInterval } = renderEventPage(
      liveEvent("tennis_atp_us_open", undefined),
    );
    expect(
      eventRefreshInterval(liveEvent("tennis_atp_us_open", undefined)),
    ).toBeGreaterThan(0);
  });

  it("keeps polling once the line exists and is still moving", () => {
    const { eventRefreshInterval } = renderEventPage(
      liveEvent("tennis_atp_us_open", POPYRIN_LINE),
    );
    expect(
      eventRefreshInterval(liveEvent("tennis_atp_us_open", POPYRIN_LINE)),
    ).toBeGreaterThan(0);
  });

  it("stops when the LINE says decided, even under a still-live status", () => {
    /** THE SECOND CONTROL, and it is what proves the page passes the line
        itself and not merely its existence. `decided` lands on the 20 s score
        grid and `completed` on the 60 s status grid, so this minute is
        ordinary; a page that dropped `linescore` from the call would read this
        as a first acquisition and poll through it. */
    const decided = liveEvent("tennis_atp_us_open", {
      ...POPYRIN_LINE,
      state: "decided",
      completion: "final",
      status_detail: "Final",
      current_set: null,
    });
    const { eventRefreshInterval } = renderEventPage(decided);
    expect(eventRefreshInterval(decided)).toBe(0);
  });

  it("STILL silences the poll for a live sport that has no line to fetch", () => {
    /** THE CONTROL, rendered rather than reasoned about. live/034 S2's ship is
        that a streaming page stops polling; an NFL page must keep it exactly.
        A repair that simply always polled would pass both tests above and fail
        this one. */
    const { eventRefreshInterval } = renderEventPage(
      liveEvent("americanfootball_nfl", undefined),
    );
    expect(
      eventRefreshInterval(liveEvent("americanfootball_nfl", undefined)),
    ).toBe(0);
  });
});

describe("the acquired line reaches the reader", () => {
  /**
   * A poll that fetches a score the page does not draw is the same blank. The
   * two renders below are the same page in the two states either side of the
   * poll this ship exists to keep alive — before the first line, and after it.
   */
  it("draws nothing where the line is, before the first one arrives", () => {
    const text = visibleText(
      renderEventPage(liveEvent("tennis_atp_us_open", undefined)).markup,
    );
    expect(text).not.toContain("6-2");
    expect(text).not.toContain("3rd Set");
    /** Not a blank PAGE — the hero is up, which is why the missing score is
        the kind of absence a reader does not notice as an error. */
    expect(text).toContain("Popyrin");
  });

  it("draws the set-by-set score once the poll has fetched it", () => {
    const text = visibleText(
      renderEventPage(liveEvent("tennis_atp_us_open", POPYRIN_LINE)).markup,
    );
    /** Both rows, whole, in publication order: the trailing `6` and `5` are
        the set IN PLAY — the game-level movement the card was blind to and the
        reason the poll above has to stay alive. */
    expect(text).toContain("Popyrin 6 6 4 6");
    expect(text).toContain("Tabilo 2 7 5");
    /** ESPN's own caption for the moment, beside the grid. */
    expect(text).toContain("3rd Set");
  });
});
