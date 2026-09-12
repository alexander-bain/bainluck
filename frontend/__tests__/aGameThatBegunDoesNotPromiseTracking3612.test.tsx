// #3612 — A GAME THAT HAS BEGUN MUST NOT PROMISE THAT TRACKING WILL BEGIN.
//
// ── WHAT THE READER SAW ──────────────────────────────────────────────────────
//
// `/events/15308573` — Paris Saint-Germain 6–1 Slovan Bratislava, Champions
// League, `completed`, badged Final with a WON chip. Win Probability card:
// "Tracking will begin when odds are available".
// `/events/15291006` — Giants 7–2 Diamondbacks, `closed`, Final, two weeks old.
// Same sentence. `/events/15310723` — a live tennis match, same sentence.
// (ux/1210 re-read the first and the last on 2026-09-12: both serve history 0,
// win_prob_history 0, bookmaker_history 0, espn_history 0 — nothing has ever
// priced them.)
//
// ── THE MECHANISM ────────────────────────────────────────────────────────────
//
// The page held its OWN copy of the empty state, and it fired before OddsChart
// mounted:
//
//     historyData?.history?.length === 0 && !hasAnyWinProbData(historyData)
//       ? "Tracking will begin when odds are available"
//       : <OddsChart … />
//
// `OddsChart`'s own empty state IS status-aware and was cleaned under ruling 142
// ("Chart available at game time" for `scheduled`, "No history data available"
// otherwise) — but it was unreachable for exactly the population that needed it,
// because the page returned first. Two copies of one sentence, and the page's
// copy could not tell a finished game from an upcoming one.
//
// ── POPULATION (ux/1205, production db-query, last 30 days) ──────────────────
//
// Events past their commence_time with ZERO odds_snapshots and ZERO
// win_prob_snapshots: `closed` 52,006 · `suspended` 10,083 · `voided` 452 ·
// `completed` 112 · `live` 5. `scheduled` 81, for which the sentence is fine.
//
// ── WHY A RENDER TEST ────────────────────────────────────────────────────────
//
// The fix is "this card is not on the page", which no unit on a predicate can
// witness — a passing test on `suppressWinProbabilityCard` alone would survive
// the wrapper being deleted. Harness copied from
// `refreshFailureKeepsThePage5016.test.tsx`, which established this seam.
//
// 🔴 EVERY CASE ASSERTS THE PAGE ITSELF RENDERED (#4286's lesson). A blank
// document satisfies every `not.toContain` here for the wrong reason.

import React from "react";
import { renderToStaticMarkup } from "react-dom/server";

const PROMISE = "Tracking will begin when odds are available";
const PREGAME_LINE = "Chart available at game time";
const CARD = 'data-testid="win-probability-card"';

const BASE = {
  id: 15308573,
  sport_key: "soccer_uefa_champs_league",
  sport_title: "Champions League",
  home_team: "Paris Saint-Germain",
  away_team: "Slovan Bratislava",
  home_score: 6,
  away_score: 1,
  win_probability_sources: {},
};

/** Nothing has ever priced this event — the shape all five specimens serve. */
const NO_HISTORY = { history: [], win_prob_history: [], espn_history: [], bookmaker_history: {} };

/** A real curve, so the card must survive. */
const WITH_HISTORY = {
  history: [
    { timestamp: "2026-09-11T20:00:00Z", home_win_probability: 0.6, away_win_probability: 0.4 },
    { timestamp: "2026-09-11T20:05:00Z", home_win_probability: 0.65, away_win_probability: 0.35 },
  ],
  win_prob_history: [],
  espn_history: [],
  bookmaker_history: {},
};

const HOUR = 3600 * 1000;
const past = () => new Date(Date.now() - 3 * HOUR).toISOString();
const future = () => new Date(Date.now() + 3 * HOUR).toISOString();

let eventPayload: unknown;
let historyPayload: unknown;
let historyLoading = false;
let historyFailure: unknown;

jest.mock("swr", () => ({
  __esModule: true,
  default: (key: unknown) => {
    const name = Array.isArray(key) ? key[0] : undefined;
    if (name === "event") {
      return { data: eventPayload, error: undefined, isLoading: false, mutate: () => undefined };
    }
    if (name === "history") {
      return {
        data: historyPayload,
        error: historyFailure,
        isLoading: historyLoading,
        mutate: () => undefined,
      };
    }
    return { data: undefined, error: undefined, isLoading: false, mutate: () => undefined };
  },
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
  useLiveEventStream: () => ({ frame: null, connected: false }),
}));

jest.mock("next/navigation", () => ({
  __esModule: true,
  useRouter: () => ({ push: () => {}, replace: () => {}, prefetch: () => {} }),
  usePathname: () => "/events/15308573",
  useSearchParams: () => new URLSearchParams(),
  useParams: () => ({ id: "15308573" }),
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
      React.createElement(EventDetailPage, { params: { id: "15308573" } }),
    ),
  );
}

beforeEach(() => {
  historyLoading = false;
  historyFailure = undefined;
  historyPayload = NO_HISTORY;
});

/**
 * SURVIVAL FIRST — the page is really on screen, so a `not` means something.
 *
 * Matched on the SHORT name: the hero renders through `teamShortNames`, so the
 * full "Paris Saint-Germain" never appears in the markup. The score is asserted
 * too, because it is the thing the reader keeps when the chart card goes away —
 * if suppression ever took the hero with it, this is what would catch it.
 *
 * #4627 (ux/1219, 2026-09-12): the home side's short name is now "PSG", by
 * Alex's ruling that this club takes its crest letters as a hand-picked label.
 * This is the anchor moving with the label it reads, not the subject of this
 * file changing — nothing about tracking, suppression or the chart card is
 * touched, and the away side is left exactly as it was so the pair still proves
 * the hero drew BOTH competitors.
 */
function expectPageRendered(html: string) {
  expect(html).toContain("PSG");
  expect(html).toContain("Bratislava");
}

describe("#3612 — a begun event with no price ever recorded", () => {
  it("does not promise tracking on a FINISHED game, and drops the card entirely", () => {
    eventPayload = { ...BASE, status: "completed", commence_time: past() };
    const html = draw();
    expectPageRendered(html);
    expect(html).not.toContain(PROMISE);
    expect(html).not.toContain(CARD);
  });

  it("does not promise tracking on a LIVE game", () => {
    eventPayload = { ...BASE, status: "live", commence_time: past() };
    const html = draw();
    expectPageRendered(html);
    expect(html).not.toContain(PROMISE);
    expect(html).not.toContain(CARD);
  });

  it("does not promise tracking on a SUSPENDED game — the tennis specimen", () => {
    eventPayload = { ...BASE, status: "suspended", commence_time: past() };
    const html = draw();
    expectPageRendered(html);
    expect(html).not.toContain(PROMISE);
    expect(html).not.toContain(CARD);
  });

  it("does not promise tracking when the STATUS says finished but the start time is wrong", () => {
    // The status half of `eventHasBegun`, and the mutation guard for dropping
    // it: a settled event whose `commence_time` we hold in the future is a data
    // error, and the clock alone would hand it the pregame card. Rare, but the
    // clause is otherwise untested and would read as dead weight to the next
    // reader — which is how a load-bearing clause gets deleted.
    eventPayload = { ...BASE, status: "completed", commence_time: future() };
    const html = draw();
    expectPageRendered(html);
    expect(html).not.toContain(PROMISE);
    expect(html).not.toContain(CARD);
  });

  it("does not promise tracking when the STATUS still says scheduled but start time has passed", () => {
    // The clock half of `eventHasBegun`, and the mutation guard for dropping it:
    // status alone leaves this row promising a chart "at game time" three hours
    // after game time. #3211 / #5158's shape.
    eventPayload = { ...BASE, status: "scheduled", commence_time: past() };
    const html = draw();
    expectPageRendered(html);
    expect(html).not.toContain(PROMISE);
    expect(html).not.toContain(CARD);
  });
});

describe("#3612 — BOTH DIRECTIONS: what must keep rendering", () => {
  it("an UPCOMING game keeps the card, and it is not the old promise", () => {
    // The mutation guard for suppressing on `hasNoPriceHistoryAtAll` alone.
    //
    // 🔴 THIS CASE DOES NOT ASSERT THE PREGAME SENTENCE, AND THE REASON IS THE
    // RIG, NOT THE PRODUCT: `OddsChart` is a dynamic import, so server-side it
    // renders its loading skeleton (`animate-pulse h-48`) and nothing it owns
    // reaches this markup. Asserting its wording from here would either fail
    // honestly or, worse, pass on some unrelated copy of the string. The
    // sentence the page now delegates to is pinned by rendering `OddsChart`
    // directly, in the block below.
    eventPayload = { ...BASE, status: "scheduled", commence_time: future() };
    const html = draw();
    expectPageRendered(html);
    expect(html).toContain(CARD);
    expect(html).not.toContain(PROMISE);
  });

  it("a finished game WITH a curve keeps its card", () => {
    // The mutation guard for suppressing on `eventHasBegun` alone.
    eventPayload = { ...BASE, status: "completed", commence_time: past() };
    historyPayload = WITH_HISTORY;
    const html = draw();
    expectPageRendered(html);
    expect(html).toContain(CARD);
  });

  it("a slow history fetch keeps the card rather than blinking it off the page", () => {
    eventPayload = { ...BASE, status: "completed", commence_time: past() };
    historyPayload = undefined;
    historyLoading = true;
    const html = draw();
    expectPageRendered(html);
    expect(html).toContain(CARD);
  });

  it("a FAILED history fetch keeps the card, so its Retry button is reachable", () => {
    // #5016's lesson one section down: an error is a freshness event, and the
    // recovery control lives inside the card this ship can remove.
    eventPayload = { ...BASE, status: "completed", commence_time: past() };
    historyPayload = undefined;
    historyFailure = new TypeError("Failed to fetch");
    const html = draw();
    expectPageRendered(html);
    expect(html).toContain(CARD);
  });

  /* ── THE TWO CASES BELOW EXIST BECAUSE MUTATION TESTING FOUND THEM MISSING ──
     Dropping `!historyLoading` from the predicate, and dropping `!historyError`,
     BOTH left all twelve other tests green. Neither clause is redundant — they
     only bite when SWR is holding data AND reporting loading/error at the same
     time, which is exactly what stale-while-revalidate does on every refresh
     (#5016 is the issue that taught this page the difference). The tests above
     set `data: undefined` alongside the flag, so `!!historyData` short-circuited
     first and the clauses were never reached.

     The behaviour they pin is #5016's ruling applied one section down: a refresh
     that is slow or failing must not make a section vanish from under a reader
     who is looking at it. */

  /* ── THE CHART DRAWS FROM FIVE SERIES, SO "NOTHING" MUST MEAN ALL FIVE ──────
     The condition this ship replaced asked only about `history`, `espn_history`
     and `win_prob_history`. `OddsChart` also builds from `bookmaker_history` and
     `aggregate_line`, both passed by this page — so an event carrying only one
     of those was already being told "tracking will begin" over a chart that
     would have drawn, and suppressing on the same test would have hidden the
     chart outright. These two cases are the mutation guards for the clauses
     that close it; each fails if its clause is dropped. */

  it("a bookmaker series alone keeps the card — the chart can draw it", () => {
    eventPayload = { ...BASE, status: "completed", commence_time: past() };
    historyPayload = {
      ...NO_HISTORY,
      bookmaker_history: {
        draftkings: [{ timestamp: "2026-09-11T20:00:00Z", home_win_probability: 0.55 }],
      },
    };
    const html = draw();
    expectPageRendered(html);
    expect(html).toContain(CARD);
  });

  it("an aggregate line alone keeps the card — the chart can draw it", () => {
    eventPayload = { ...BASE, status: "completed", commence_time: past() };
    historyPayload = {
      ...NO_HISTORY,
      aggregate_line: [{ timestamp: "2026-09-11T20:00:00Z", home_probability: 0.55 }],
    };
    const html = draw();
    expectPageRendered(html);
    expect(html).toContain(CARD);
  });

  it("a refresh IN FLIGHT over an empty history keeps the card", () => {
    eventPayload = { ...BASE, status: "completed", commence_time: past() };
    historyPayload = NO_HISTORY;
    historyLoading = true;
    const html = draw();
    expectPageRendered(html);
    expect(html).toContain(CARD);
  });

  it("a refresh that FAILED over an empty history keeps the card", () => {
    eventPayload = { ...BASE, status: "completed", commence_time: past() };
    historyPayload = NO_HISTORY;
    historyFailure = new TypeError("Failed to fetch");
    const html = draw();
    expectPageRendered(html);
    expect(html).toContain(CARD);
  });
});

/**
 * THE SENTENCE THE PAGE NOW DELEGATES TO — and it had NO test until this ship.
 *
 * Ruling 142 cleaned this wording inside `OddsChart` ("will update … once the
 * game starts" promised a future state), and a grep for either string across
 * `__tests__/` before this file found nothing. So the page deleted its own copy
 * in favour of a definition that nothing was holding in place. Pinned here, both
 * arms, because "there is one definition" is only an improvement if the one
 * definition is guarded.
 *
 * Rendered directly rather than through the page: the page loads this component
 * dynamically and never shows its output server-side (see the note above).
 */
describe("#3612 — OddsChart owns the empty state, and it is status-aware", () => {
  // eslint-disable-next-line @typescript-eslint/no-var-requires
  const OddsChart = require("@/components/OddsChart").default;

  // Wrapped in the provider for the same reason the page is: the chart reports
  // its own interactions, and `useAnalyticsContext` throws without one.
  const drawChart = (eventStatus: string) =>
    renderToStaticMarkup(
      React.createElement(
        AnalyticsProvider,
        null,
        React.createElement(OddsChart, {
          history: [],
          homeTeam: "Paris Saint-Germain",
          awayTeam: "Slovan Bratislava",
          eventStatus,
        }),
      ),
    );

  it("an upcoming game is told what the chart plots, in the present tense", () => {
    const html = drawChart("scheduled");
    expect(html).toContain(PREGAME_LINE);
    expect(html).toContain("This chart plots win probability minute by minute");
    // Ruling 142's own point: no promise about a future state.
    expect(html).not.toContain(PROMISE);
    expect(html).not.toContain("will update");
  });

  it("a finished game is NOT told a chart is available at game time", () => {
    const html = drawChart("completed");
    expect(html).not.toContain(PREGAME_LINE);
    expect(html).not.toContain(PROMISE);
    expect(html).toContain("No history data available");
  });

  it("an UNKNOWN status does not get the pregame promise either", () => {
    // `isPreGame` is `=== "scheduled"` exactly, which is the safe end: the page
    // keeps the card for an unrecognised status (isPregameStatus is permissive
    // there), and this is what stops that combination promising anything.
    const html = drawChart("some_provider_word");
    expect(html).not.toContain(PREGAME_LINE);
    expect(html).toContain("No history data available");
  });
});
