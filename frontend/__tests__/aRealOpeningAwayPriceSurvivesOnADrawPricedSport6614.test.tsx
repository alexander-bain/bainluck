/**
 * #6614 — the event hero stops deleting a REAL opening away price on soccer.
 *
 * ═══ WHAT A READER SAW ═══
 *
 * `/events/15298749` — Torreense @ Lillestrom, Europa League, final 1–2 —
 * photographed at 390×844 on 2026-09-18
 * (`artifacts/ux-1330/BEFORE-6614-15298749-390.png`). Torreense WON AS A 21%
 * UNDERDOG and the settled hero printed no pregame mark at all: "Torreense /
 * Won / 1 – 2" and nothing else. The one fact that made the result worth
 * reading was the fact the page deleted.
 *
 * ═══ WHY IT WAS DELETED, AND WHY THE SPORT IS THE WRONG QUESTION ═══
 *
 * #6238 taught this page to withhold the away figure wherever the sport prices
 * a draw, because `current_odds.away_probability` is derived as `1 - home` and
 * so means "the home team does not win" — away win OR draw. That is right for
 * that pair and it was applied to BOTH pairs on the page.
 *
 * `opening_odds` is not that pair. Since #1011 it is de-vigged across the whole
 * quoted board, so `home + away ≈ 0.76` and the missing ~0.24 IS the draw. Both
 * legs are real, independently sourced prices. Re-taken on production
 * 2026-09-18, `/api/feed?mode=sports`, 25 soccer cards:
 *
 *   | pair           | sums to 1.0000 | sums to 0.72 – 0.84 |
 *   |----------------|----------------|---------------------|
 *   | `current_odds` | **25 / 25**    | 0                   |
 *   | `opening_odds` | 16 / 25        | **9 / 25**          |
 *
 * BOTH arms are live traffic, which is why this suite asserts both on ONE
 * sport: 16 of 25 opening pairs really are complements and must STILL be
 * withheld. A blanket flip in either direction is wrong, so the guard that
 * matters is the one that fails for a blanket flip in either direction.
 *
 * ═══ THE PAYLOADS ARE WHAT PRODUCTION SERVED ═══
 *
 * `SETTLED_AWAY_WINNER` is `GET /api/events/15298749` verbatim, read
 * 2026-09-18. `LIVE_NON_COMPLEMENT` carries the issue's own filed specimen —
 * Lyon @ Anderlecht, `/api/events/15298544`, opening `0.3246 / 0.4044` summing
 * to 0.729 — which is the pair the issue was written about.
 *
 * 🪤 The COMPLEMENT arm is built by overriding this specimen's own away leg to
 * the exact complement of its own home leg (`1 - 0.5476`). That is deliberate:
 * it holds sport, page, component and every other field fixed, so the only
 * thing the two arms disagree about is the one thing the rule reads. A second
 * live row would have varied a dozen fields at once.
 */

import React from "react";
import { renderToStaticMarkup } from "react-dom/server";

/** `GET /api/events/15298749`, production, 2026-09-18. Away side won 2–1 off an
 *  opening pair summing to 0.7579 — not a complement, both legs real. */
const SETTLED_AWAY_WINNER = {
  id: 15298749,
  sport: "soccer_uefa_europa_league",
  sport_name: "UEFA Europa League",
  home_team: "Lillestrom",
  away_team: "Torreense",
  home_score: 1,
  away_score: 2,
  status: "completed",
  commence_time: "2026-09-17T19:00:00+00:00",
  completed_at: "2026-09-17T20:58:07.882953+00:00",
  hero_settled_result: "away",
  win_probability_sources: {},
  current_odds: {
    captured_at: "2026-09-17T20:55:09.603194+00:00",
    home_probability: 0.0078,
    away_probability: null,
    away_rendered_percent: null,
    home_rendered_percent: 1,
    bookmaker_count: 9,
  },
  opening_odds: {
    home_probability: 0.5476,
    away_probability: 0.2103,
    favorite: "home",
  },
};

/** The issue's own filed specimen — Lyon @ Anderlecht, `/api/events/15298544`,
 *  opening `0.3246 / 0.4044` = 0.729. Held LIVE here because the `Opened X – Y`
 *  line renders on the `!isFinished` branch only. */
const LIVE_NON_COMPLEMENT = {
  id: 15298544,
  sport: "soccer_uefa_europa_league",
  sport_name: "UEFA Europa League",
  home_team: "Anderlecht",
  away_team: "Lyon",
  home_score: null,
  away_score: null,
  status: "live",
  commence_time: new Date(Date.now() - 30 * 60 * 1000).toISOString(),
  win_probability_sources: {},
  current_odds: {
    home_probability: 0.3246,
    away_probability: null,
    home_rendered_percent: 32,
    away_rendered_percent: null,
  },
  opening_odds: { home_probability: 0.3246, away_probability: 0.4044 },
};

/** CONTROL sport: `sportVocab` does not declare a draw for NFL, so nothing on
 *  this page may change for it in either pair. */
const LIVE_TWO_WAY = {
  ...LIVE_NON_COMPLEMENT,
  id: 15310565,
  sport: "americanfootball_nfl",
  sport_name: "NFL",
  home_team: "Kansas City Chiefs",
  away_team: "Denver Broncos",
  opening_odds: { home_probability: 0.62, away_probability: 0.38 },
};

let eventPayload: unknown;
let historyPayload: unknown;

jest.mock("swr", () => ({
  __esModule: true,
  default: (key: unknown) => {
    const k = Array.isArray(key) ? key[0] : null;
    const data =
      k === "event" ? eventPayload : k === "history" ? historyPayload : undefined;
    return { data, error: undefined, isLoading: false, mutate: () => undefined };
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
  useLiveEventStream: () => ({ frame: null, connected: false }),
}));

jest.mock("next/navigation", () => ({
  __esModule: true,
  useRouter: () => ({ push: () => {}, replace: () => {}, prefetch: () => {} }),
  usePathname: () => "/events/15298749",
  useSearchParams: () => new URLSearchParams(),
  useParams: () => ({ id: "15298749" }),
}));

// eslint-disable-next-line @typescript-eslint/no-var-requires
const EventDetailPage = require("@/app/events/[id]/page").default;
// eslint-disable-next-line @typescript-eslint/no-var-requires
const { AnalyticsProvider } = require("@/components/Analytics");

function draw(payload: unknown): string {
  eventPayload = payload;
  return renderToStaticMarkup(
    React.createElement(
      AnalyticsProvider,
      null,
      React.createElement(EventDetailPage, { params: { id: "15298749" } }),
    ),
  );
}

/**
 * The text of the `Opened …` line alone.
 *
 * 🪤 Asserting `html).toContain("40%")` would pass off any 40% anywhere on a
 * page that carries dozens of percentages — the chart, the markets, the props.
 * This pulls the one line the ship is about and asserts against THAT.
 */
function openedLine(html: string): string {
  const at = html.indexOf("Opened");
  if (at === -1) return "";
  // 🪤 Stop at the next TAG, not at a fixed width and not by stripping tags.
  //
  // Two traps, both paid for on this file. A fixed-width slice runs into the
  // next element and yields `Opened 32%LLyon</a`, failing an end-anchored
  // assertion for a reason that has nothing to do with the ship. And the
  // obvious repair — `.replace(/<[^>]*>/g, "")` — is a CodeQL HIGH:
  // `js/incomplete-multi-character-sanitization`, "this string may still
  // contain [<script". It is right in general: a single-pass tag strip is not
  // a sanitizer, and notice 32 makes that a merge stop.
  //
  // Neither is needed. The `Opened` span's content is plain text with no
  // nested elements, so the line simply ends at the next `<`.
  const end = html.indexOf("<", at);
  return html.slice(at, end === -1 ? html.length : end).trim();
}

beforeEach(() => {
  historyPayload = { aggregate_line: [] };
});

describe("#6614 a non-complement opening pair keeps BOTH legs", () => {
  it("prints the away leg of `Opened` on the issue's own filed specimen", () => {
    const line = openedLine(draw(LIVE_NON_COMPLEMENT));

    // THE SHIP. `0.3246 / 0.4044` — two real prices, both printed.
    expect(line).toMatch(/Opened\s*32%\s*–\s*40%/);
  });

  it("restores the settled pregame mark for an away winner, and calls it an upset", () => {
    const html = draw(SETTLED_AWAY_WINNER);

    // THE SHIP, and the whole reader payoff: 21% is under `UPSET_THRESHOLD`.
    expect(html).toContain("21% pregame");
    expect(html).toContain("Upset");

    // NON-VACUITY. A page that failed to draw would satisfy nothing above but
    // would also satisfy a `not.toContain`, so the opposite arm below needs
    // this same anchor to mean anything.
    expect(html).toContain("Torreense");
    expect(html).toContain("Lillestrom");
    expect(html.length).toBeGreaterThan(2000);
  });
});

describe("#6614 a complement opening pair is STILL withheld — 16 of 25 live cards", () => {
  /** This specimen's own home leg, completed to 1. Only the away value differs
   *  from the arm above. */
  const asComplement = {
    ...SETTLED_AWAY_WINNER,
    opening_odds: {
      ...SETTLED_AWAY_WINNER.opening_odds,
      away_probability: 1 - 0.5476,
    },
  };

  it("withholds the pregame mark when the away leg IS the complement", () => {
    const html = draw(asComplement);

    // #6238's rule, unchanged: the number it would print is "Lillestrom does
    // not win", which is not Torreense's price.
    expect(html).not.toContain("45% pregame");
    expect(html).not.toContain("pregame");

    // NON-VACUITY: the same page, same hero, still drawn.
    expect(html).toContain("Torreense");
    expect(html).toContain("Lillestrom");
    expect(html.length).toBeGreaterThan(2000);
  });

  it("withholds the away leg of `Opened` when the pair completes to 1", () => {
    const line = openedLine(
      draw({
        ...LIVE_NON_COMPLEMENT,
        opening_odds: { home_probability: 0.3246, away_probability: 1 - 0.3246 },
      }),
    );

    // The separator goes with the figure (#6238): `Opened 32% – -` reads as a
    // number that failed to draw.
    expect(line).toMatch(/Opened\s*32%\s*$/);
    expect(line).not.toContain("–");
  });
});

describe("#6614 the CURRENT pair on the same page is untouched", () => {
  /**
   * 🪤 THERE IS DELIBERATELY NO "the current away figure is still withheld"
   * TEST HERE, AND IT IS NOT AN OVERSIGHT.
   *
   * One was written and then removed, because it could not fail. Three mutants
   * were run against it: `awaySlotWithheld = false`, `awayProb =
   * servedAwayProb`, and both together. All three SURVIVED a green suite. The
   * cause is upstream — `resolveProbability` hands this page a null
   * `servedAwayProb` on these specimens, so no mutation downstream of it can
   * put a current away figure on the page, and `not.toContain(…)` was passing
   * on a number that was never going to render either way.
   *
   * The two-way control below is kept because it DOES fail: forcing
   * `sportPricesADraw` true reddens it.
   *
   * A control that cannot fail is worse than no control — it advertises a
   * protection that is not there. #6238's own behaviour is guarded on the
   * surfaces where it is observable (`drawPricedCardFamily6238.test.tsx`).
   */
  it("CONTROL: a two-way sport prints both opening legs, as it always did", () => {
    const line = openedLine(draw(LIVE_TWO_WAY));

    expect(line).toMatch(/Opened\s*62%\s*–\s*38%/);
  });
});
