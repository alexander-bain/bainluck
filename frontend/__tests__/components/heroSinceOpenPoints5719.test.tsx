/**
 * #5719 — the event hero's "since open" caption, in POINTS and derived from the
 * numbers printed beside it.
 *
 * ═══ WHAT A READER SAW, PRODUCTION, 390px, 2026-09-12 ═══
 *
 * `/events/1175875` — Michigan 17, Oklahoma 10, 5:57 4th Quarter:
 *
 *       75% – 25%
 *   ↑ +41% Wolverines since open
 *     Opened 34% – 66%
 *
 * Two defects on that one line.
 *
 * DEFECT 1, THE UNIT. 34 -> 75 is +41 percentage POINTS. As a percentage it is
 * +121. The caption sits directly above the opening pair, which invites the
 * reader to do the subtraction, and then answers in the wrong unit. Tenth
 * surface of the points-vs-percent family (#5623, #5669, #5686, #5659, #3042,
 * #5709, #3051) and the largest.
 *
 * DEFECT 2, THE SECOND ROUNDING. The caption was the raw difference of two
 * probabilities; every number around it is an integer `resolveProbability`
 * already decided. Two roundings of one relationship disagree whenever the
 * fractional parts straddle a boundary — #2951's finding, which #3051 caught on
 * a tennis hero captioning `+3` between a printed 91 and a printed 95.
 *
 * ═══ WHY THIS FILE RENDERS THE PAGE ═══
 *
 * A source scan cannot tell a fixed caption from a deleted one — #5669 learned
 * that and #5686 was built on it. Every arm below draws the real
 * `app/events/[id]/page.tsx` through the real `resolveProbability` and reads the
 * sentence out of the HTML.
 *
 * ═══ THE SPECIMENS ARE CHOSEN SO THE TWO RULES DISAGREE ═══
 *
 * The production frames cannot prove defect 2: 75 − 34 = 41 and 60 − 14 = 46, so
 * both arithmetics agree on them by luck. That is exactly why sampling would
 * never have caught this. Each pair below was picked by replaying the shipped
 * `renderedDuelPercents` and keeping the ones where the two answers differ:
 *
 *   DISAGREE   home .755 / open .344   ->  printed 76 and 34, difference 42
 *                                          raw difference rounds to 41
 *   SUB-POINT  home .7551 / open .7549 ->  printed 76 and 75, difference 1
 *                                          raw difference rounds to 0
 *   NO MOVE    home .755 / open .758   ->  printed 76 and 76, difference 0
 *
 * The SUB-POINT pair is the converse case and it is deliberate: the levels the
 * hero prints differ by a point on screen, so the caption that explains them
 * must exist, even though the raw move is two ten-thousandths. Under the old
 * gate it printed nothing.
 */

import React from "react";
import { renderToStaticMarkup } from "react-dom/server";

/** The home team's compact name, which is what the caption names. */
const HOME_SHORT = "Wolverines";
const CAPTION_TAIL = `${HOME_SHORT} since open`;

let eventPayload: unknown;

jest.mock("swr", () => ({
  __esModule: true,
  default: (key: unknown) => {
    const k = Array.isArray(key) ? key[0] : null;
    return {
      data: k === "event" ? eventPayload : undefined,
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
  useLiveEventStream: () => ({ frame: null, connected: false }),
}));

jest.mock("next/navigation", () => ({
  __esModule: true,
  useRouter: () => ({ push: () => {}, replace: () => {}, prefetch: () => {} }),
  usePathname: () => "/events/1175875",
  useSearchParams: () => new URLSearchParams(),
  useParams: () => ({ id: "1175875" }),
}));

// eslint-disable-next-line @typescript-eslint/no-var-requires
const EventDetailPage = require("@/app/events/[id]/page").default;
// eslint-disable-next-line @typescript-eslint/no-var-requires
const { AnalyticsProvider } = require("@/components/Analytics");

/**
 * A live game whose hero is the BLEND.
 *
 * `hero_probability_source: "blend"` is the branch that returns the pair
 * unserved, so `withRenderedPercents` decides both integers locally — the same
 * path Michigan–Oklahoma took. `win_probability_sources` is empty so
 * `liveClaimIsUnbacked` reads no stamp and the page stays LIVE rather than
 * falling into `isSuspended`, which resolves from the chart instead.
 *
 * The kickoff is an OFFSET from `Date.now()`, computed at call time and never
 * truncated to a wall-clock literal (gotcha #44): `isLive` requires
 * `commence_time` in the past, and an anchor that branches on the clock is not
 * an anchor.
 */
function liveEvent(homeProb: number, openingHomeProb: number) {
  return {
    id: 1175875,
    sport_key: "americanfootball_ncaaf",
    sport: "americanfootball_ncaaf",
    sport_title: "NCAAF",
    home_team: "Michigan Wolverines",
    away_team: "Oklahoma Sooners",
    home_score: 17,
    away_score: 10,
    status: "live",
    commence_time: new Date(Date.now() - 150 * 60 * 1000).toISOString(),
    win_probability_sources: {},
    hero_probability_source: "blend",
    hero_probability: homeProb,
    hero_probability_away: 1 - homeProb,
    opening_odds: {
      home_probability: openingHomeProb,
      away_probability: 1 - openingHomeProb,
    },
  };
}

/**
 * 🔴 THE HERO'S INTEGER AND ITS `%` ARE TWO SIBLING SPANS.
 *
 * So `toContain("76%")` fails against a page printing exactly `76%`, and the
 * first draft of this file reported a defect that was not there. The caption
 * and the opening line are each a SINGLE text run, so they are asserted
 * verbatim; only the hero pair needs this.
 *
 * Stripping the tags first is the obvious alternative and it is the one to
 * avoid: `replace(/<[^>]*>/g, "")` is CodeQL's `js/incomplete-multi-character-
 * sanitization`, a HIGH severity finding, and it failed the check-run on this
 * branch's first sha. The rule is right even in a test — the expression is an
 * HTML filter whatever it is used for — and matching the element is both safer
 * and more precise than flattening the document to find a number in it.
 */
function heroPrints(percent: number): string {
  return `>${percent}</span>`;
}

function draw(homeProb: number, openingHomeProb: number): string {
  eventPayload = liveEvent(homeProb, openingHomeProb);
  const html = renderToStaticMarkup(
    React.createElement(
      AnalyticsProvider,
      null,
      React.createElement(EventDetailPage, { params: { id: "1175875" } }),
    ),
  );
  // An assertion against a page that did not draw is a pass that proves
  // nothing. Both teams render on every branch this file exercises.
  expect(html).toContain(HOME_SHORT);
  return html;
}

describe("#5719 the hero's since-open caption is in points", () => {
  it("says pts, and never a percent sign, on the filed specimen's shape", () => {
    const html = draw(0.755, 0.344);

    expect(html).toContain(`pts ${CAPTION_TAIL}`);
    // The defect's exact spelling, and the general one beside it: any percent
    // sign immediately before this sentence is this bug whatever its value.
    expect(html).not.toContain(`% ${CAPTION_TAIL}`);
  });

  it("prints the difference of the two INTEGERS the hero shows, not of the two probabilities", () => {
    const html = draw(0.755, 0.344);

    // The levels this page printed. Asserted first: without them the caption
    // assertion below could be satisfied by a page showing some other pair.
    expect(html).toContain(heroPrints(76));
    expect(html).toContain("Opened 34%");

    // 76 − 34. The raw difference rounds to 41, which is what shipped.
    expect(html).toContain(`+42 pts ${CAPTION_TAIL}`);
    expect(html).not.toContain("+41");
  });

  it("claims a one-point move the printed levels show even when the raw move rounds to nothing", () => {
    // .7551 prints 76, .7549 prints 75 — a point apart on screen, two
    // ten-thousandths apart on the wire. The old gate (raw < 0.01) printed
    // nothing here and left the reader two visibly different numbers with no
    // sentence between them.
    const html = draw(0.7551, 0.7549);

    expect(html).toContain(heroPrints(76));
    expect(html).toContain("Opened 75%");
    expect(html).toContain(`+1 pt ${CAPTION_TAIL}`);
    // Singular, because this caption prints a whole number. "1 pts" is the
    // tell that nobody read the sentence.
    expect(html).not.toContain("+1 pts");
  });

  it("says nothing at all when the two printed levels are the same number", () => {
    // .755 and .758 both print 76. A caption over two identical numbers can
    // only contradict them.
    const html = draw(0.755, 0.758);

    expect(html).toContain(heroPrints(76));
    expect(html).toContain("Opened 76%");
    expect(html).not.toContain(CAPTION_TAIL);
  });

  it("prints one minus sign on a fall, and still in points", () => {
    // Opening 76, current 34 — the Yankees' direction on the second production
    // frame. The sign travels on the number; a `-` prefix would print `--42`.
    const html = draw(0.344, 0.755);

    expect(html).toContain(`-42 pts ${CAPTION_TAIL}`);
    expect(html).not.toContain("--42");
  });
});
