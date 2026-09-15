// #6399 / #6390 — THE FOLDED SPORTSBOOKS HAVE TO BE REACHABLE, NOT MERELY SERVED.
//
// ── WHAT THE READER SAW ──────────────────────────────────────────────────────
//
// `/events/15311919` — Brest 0-1 Paris Saint-Germain, Ligue 1, `completed` —
// rendered a final score and nothing else. Its hidden duplicate `15297786` held
// all ten sportsbooks.
//
// #6390 folded `odds_snapshots` onto the canonical's DETAIL payload, and
// CERT-2925 blocked it for a reason no backend test could have caught: the
// price table it fills is nested inside the Win Probability card, and
// `suppressWinProbabilityCard` removes that whole card when every series the
// chart can draw is empty and the game has begun. Ten sportsbooks arrived in
// the payload and no reader could see one of them.
//
// ── WHY THIS FILE IS A RENDER TEST ───────────────────────────────────────────
//
// "The rows are reachable" is a statement about the PAGE, and the false-green
// boundary CERT-2925 named is exactly an API assertion that passes while the
// page shows nothing. A unit on the predicate would not have caught the
// nesting either — it is the wrapper, not the condition, that hides the table.
// Harness copied from `aGameThatBegunDoesNotPromiseTracking3612.test.tsx`,
// which established this seam for the same card.
//
// ── WHAT "REACHABLE" MEANS HERE, EXACTLY ─────────────────────────────────────
//
// The ten rows sit behind a collapsed toggle (notice 37 / D102: untraded and
// secondary detail goes behind a disclosure, present and openable). A static
// render cannot click, so reachability is proved in two halves that compose:
// this file asserts the "Sportsbooks" disclosure is ON THE PAGE, and
// `BookmakerTable`'s own tests assert it draws a row per book once opened.
// Asserting the rows in the static markup would be asserting the toggle is
// broken.
//
// 🔴 EVERY CASE ASSERTS THE PAGE ITSELF RENDERED. A blank document satisfies
// every `not.toContain` here for the wrong reason (#4286).

import React from "react";
import { renderToStaticMarkup } from "react-dom/server";

const DISCLOSURE = "Sportsbooks";
const CARD = 'data-testid="win-probability-card"';

const HOUR = 3600 * 1000;
const past = () => new Date(Date.now() - 3 * HOUR).toISOString();

/** The ten books production holds on ghost `15297786`. */
const GHOST_BOOKS = [
  "betmgm",
  "betrivers",
  "bovada",
  "caesars",
  "draftkings",
  "fanduel",
  "lowvig",
  "mybookieag",
  "pinnacle",
  "williamhill_us",
];

/** What #6390's detail fold puts on the canonical: ten books, none its own. */
const FOLDED_ODDS = GHOST_BOOKS.map((bookmaker) => ({
  bookmaker,
  home_moneyline: -150,
  away_moneyline: 130,
  home_win_probability: 0.6,
  away_win_probability: 0.4,
  last_update: past(),
}));

const BASE = {
  id: 15311919,
  sport_key: "soccer_france_ligue_one",
  sport_title: "Ligue 1",
  home_team: "Brest",
  away_team: "Paris Saint-Germain",
  home_score: 0,
  away_score: 1,
  status: "completed",
  win_probability_sources: {},
  bookmaker_odds: FOLDED_ODDS,
};

/** Before #6399: the canonical's own rows, i.e. none of them. */
const NO_HISTORY = {
  history: [],
  win_prob_history: [],
  espn_history: [],
  bookmaker_history: {},
  aggregate_line: null,
};

/**
 * After #6399: the ghost's series arrive with its prices.
 *
 * Shaped from what production serves on `15297786` — ten non-empty
 * `bookmaker_history` keys — rather than from an invented minimum, because the
 * guard is an AND over five inputs and a fixture that happened to fill a
 * DIFFERENT one would prove the wrong thing.
 */
const FOLDED_HISTORY = {
  history: [
    { timestamp: "2026-09-13T17:00:00Z", home_win_probability: 0.58, away_win_probability: 0.42 },
    { timestamp: "2026-09-13T18:00:00Z", home_win_probability: 0.6, away_win_probability: 0.4 },
  ],
  win_prob_history: [],
  espn_history: [],
  aggregate_line: null,
  bookmaker_history: Object.fromEntries(
    GHOST_BOOKS.map((book) => [
      book,
      [
        { timestamp: "2026-09-13T17:00:00Z", home_probability: 0.58, away_probability: 0.42 },
        { timestamp: "2026-09-13T18:00:00Z", home_probability: 0.6, away_probability: 0.4 },
      ],
    ]),
  ),
};

let eventPayload: unknown;
let historyPayload: unknown;

jest.mock("swr", () => ({
  __esModule: true,
  default: (key: unknown) => {
    const name = Array.isArray(key) ? key[0] : undefined;
    if (name === "event") {
      return { data: eventPayload, error: undefined, isLoading: false, mutate: () => undefined };
    }
    if (name === "history") {
      return { data: historyPayload, error: undefined, isLoading: false, mutate: () => undefined };
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
  usePathname: () => "/events/15311919",
  useSearchParams: () => new URLSearchParams(),
  useParams: () => ({ id: "15311919" }),
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
      React.createElement(EventDetailPage, { params: { id: "15311919" } }),
    ),
  );
}

/**
 * The page is really on screen, so a `not` below means something.
 *
 * Both competitors, matched on the SHORT names the hero actually renders
 * through `teamShortNames` — "Paris Saint-Germain" never appears in the markup
 * (#4627: this club takes "PSG"). Not the score: "0" and "1" are in almost any
 * document, so asserting them would be a survival check that cannot fail, which
 * is the same defect as having none.
 */
function expectPageRendered(html: string) {
  expect(html).toContain("Brest");
  expect(html).toContain("PSG");
}

beforeEach(() => {
  eventPayload = { ...BASE, commence_time: past() };
  historyPayload = FOLDED_HISTORY;
});

describe("#6399 — the folded price table reaches the finished page", () => {
  it("renders the Sportsbooks disclosure once the folded series arrive", () => {
    const html = draw();
    expectPageRendered(html);
    expect(html).toContain(CARD);
    expect(html).toContain(DISCLOSURE);
  });

  it("is the HISTORY fold that unlocks it, not the prices alone", () => {
    // The CERT-2925 state exactly: #6390 has landed, so ten books are in the
    // detail payload, and the history route is still unfolded. This is the
    // BEFORE, and it must be able to fail — a fixture that reached the
    // disclosure here would mean the two arms are not testing the fold.
    historyPayload = NO_HISTORY;
    const html = draw();
    expectPageRendered(html);
    expect(html).not.toContain(CARD);
    expect(html).not.toContain(DISCLOSURE);
  });

  it("still needs prices: a folded chart with no book rows shows no disclosure", () => {
    // The other half of the conjunction at page.tsx:2062. Without this, the
    // first case passes for an event that has a chart and no prices, and the
    // file would be testing the card rather than the table inside it.
    eventPayload = { ...BASE, commence_time: past(), bookmaker_odds: [] };
    const html = draw();
    expectPageRendered(html);
    expect(html).toContain(CARD);
    expect(html).not.toContain(DISCLOSURE);
  });
});

// 🔴 THE RESIDUAL, HELD HERE SO THE ux SHIP HAS SOMETHING TO INVERT — #6421.
//
// CERT-2925's REQUIRED TEST named this shape:
//
//     test_completed_empty_history_with_folded_bookmakers_renders_sportsbook_
//     disclosure_6390 — detail has ten folded bookmaker_odds; history has every
//     series empty; assert the disclosure and ten rows are reachable.
//
// The repair it required named two routes, and #6399 takes the history one,
// which is the route that works for the named specimen (ghost `15297786` holds
// 1,236 points). That route does NOT deliver this shape, and saying so is the
// point of the assertion below rather than quietly shipping a differently-named
// test.
//
// The shape stays reachable after #6399: for a finished event the history query
// caps at `_finished_event_end_cap` while the detail route's current-odds read
// applies no cap, so a book whose only reading was captured after the cap lands
// in `bookmaker_odds` and in no series. Closing it means rendering the table
// OUTSIDE the card — ux's layout file, notice 41.
describe("#6421 — the residual CERT-2925 named, not closed by the history fold", () => {
  it("BOUNDARY: ten prices and no series are still hidden — invert this in #6421", () => {
    historyPayload = NO_HISTORY;
    const html = draw();
    expectPageRendered(html);
    // When #6421 lands, these two become `toContain` and this block's name
    // loses the word BOUNDARY. Nothing else in the file changes.
    expect(html).not.toContain(DISCLOSURE);
    expect(html).not.toContain(CARD);
  });
});
