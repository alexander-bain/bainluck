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
 *
 * ═══ #5995 CHANGED THE WORDING AND KEPT EVERY RULE ABOVE ═══
 *
 * #5719's answer to defect 1 was the word `pts`. On a SCORING sport that word
 * is the score's unit: `+49 pts Giants since open` printed directly above a
 * 21–14 scoreline, and 49 is larger than either team's points, so the wrong
 * reading is the likelier one. `pp` is jargon (D102) and a hero-only unit word
 * would break the family `pts` belongs to, so the caption stopped naming a unit
 * and now prints the JOURNEY between the two levels:
 *
 *       Wolverines 34% → 76% since open
 *
 * This is #5719's invariant with the arithmetic removed. "Difference of the
 * printed levels" existed so that `shown − caption = opened` held on screen;
 * printing the levels themselves makes that true by construction, so the
 * second-rounding class (#2951, #3051) cannot recur on this line at all. Every
 * specimen below is therefore kept, including the DISAGREE pair whose whole
 * purpose was to separate the two arithmetics — under the new wording it proves
 * the caption quotes the printed integers (34 and 76) and invents neither the
 * raw-derived 41 nor the integer-derived 42.
 *
 * The `pts`/`%` assertions are inverted rather than deleted: the caption must
 * now print NO delta in any unit. A `%` DOES appear, attached to each level,
 * which is the correct use of the sign and the thing #5719 was never objecting
 * to — so the old blanket "no percent sign before this sentence" guard is
 * replaced by a narrower one that still catches the defect it was aimed at.
 */

import React from "react";
import { renderToStaticMarkup } from "react-dom/server";

/** The home team's compact name, which is what the caption names. */
const HOME_SHORT = "Wolverines";
/** The caption's invariant tail — the only part of it no wording has changed. */
const SINCE_OPEN = "since open";

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

/**
 * 🔴 THE CAPTION IS READ OUT, NOT MATCHED AGAINST A TAIL.
 *
 * #5995 moved the team name from the END of this sentence to the FRONT, which
 * quietly turns every `not.toContain("… Wolverines since open")` guard vacuous:
 * the string it forbids can no longer occur under ANY wording, right or wrong,
 * so the assertion passes without examining anything. The negative guards here
 * are the ones that catch the defect, so they are pointed at the caption's own
 * text instead of at a substring of the document.
 *
 * Returns the caption span's contents, and THROWS if the page drew no caption —
 * an extractor that returns "" on a missing element turns the same guards
 * vacuous a second way.
 */
function captionText(html: string): string {
  const span = html.match(
    /<span class="text-xs font-semibold[^"]*">([\s\S]*?)<\/span>/,
  );
  if (!span) throw new Error("no since-open caption in the rendered page");
  // React separates adjacent text children with empty comments; they are not
  // part of what the reader sees.
  const text = span[1].replace(/<!---->/g, "");
  expect(text).toContain(SINCE_OPEN);
  return text;
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

describe("#5719/#5995 the hero's since-open caption prints the journey", () => {
  it("names no unit at all on the filed specimen's shape", () => {
    const html = draw(0.755, 0.344);

    expect(html).toContain(`Wolverines 34% → 76% ${SINCE_OPEN}`);

    const text = captionText(html);
    // #5995: the score's own word, which is what a reader on a scoring sport
    // reads it as. `\bpts?\b` catches both spellings, because "+1 pt" was a
    // real branch of the line this replaces.
    expect(text).not.toMatch(/\bpts?\b/);
    // #5719's defect, still refused: a DELTA, in any unit or none. Each level
    // may carry a `%`; a difference may not appear at all.
    expect(text).not.toMatch(/[+−-]\s*\d/);
  });

  it("quotes the two INTEGERS the hero shows, and invents neither arithmetic's delta", () => {
    const html = draw(0.755, 0.344);

    // The levels this page printed. Asserted first: without them the caption
    // assertion below could be satisfied by a page showing some other pair.
    expect(html).toContain(heroPrints(76));
    expect(html).toContain("Opened 34%");

    // The caption is those same two integers, in order.
    expect(html).toContain(`Wolverines 34% → 76% ${SINCE_OPEN}`);

    // Under #5719 this pair was chosen because the two arithmetics disagree:
    // 76 − 34 = 42, while the raw difference rounds to 41. The caption now
    // performs neither subtraction, so NEITHER number may appear in it.
    const text = captionText(html);
    expect(text).not.toContain("42");
    expect(text).not.toContain("41");
  });

  it("shows a one-point journey the printed levels show even when the raw move rounds to nothing", () => {
    // .7551 prints 76, .7549 prints 75 — a point apart on screen, two
    // ten-thousandths apart on the wire. The old gate (raw < 0.01) printed
    // nothing here and left the reader two visibly different numbers with no
    // sentence between them.
    const html = draw(0.7551, 0.7549);

    expect(html).toContain(heroPrints(76));
    expect(html).toContain("Opened 75%");
    expect(html).toContain(`Wolverines 75% → 76% ${SINCE_OPEN}`);
  });

  it("says nothing at all when the two printed levels are the same number", () => {
    // .755 and .758 both print 76. A caption over two identical numbers can
    // only contradict them — and as a journey it would read "76% → 76%",
    // which is the same objection in the new wording.
    const html = draw(0.755, 0.758);

    expect(html).toContain(heroPrints(76));
    expect(html).toContain("Opened 76%");
    expect(html).not.toContain(SINCE_OPEN);
  });

  it("reads the journey backwards on a fall, with no sign to get wrong", () => {
    // Opening 76, current 34 — the Yankees' direction on the second production
    // frame. A journey carries its direction in the order of its two numbers,
    // so the whole family of sign defects ("--42") cannot arise.
    const html = draw(0.344, 0.755);

    expect(html).toContain(`Wolverines 76% → 34% ${SINCE_OPEN}`);
    expect(html).not.toContain("-42");
  });
});

/**
 * #5995 — THE BOUNDARY, WHICH IS WHERE THIS CAPTION IS ACTUALLY LOOKED AT.
 *
 * The two levels are rendered by two different things. The current one comes
 * from `EventHeroProbabilityPair`, which prints the bare integer; the opening
 * one comes from `formatProbability`, which clamps the ends to `<1%` / `>99%`.
 * They disagree above 99.5%, so a caption that used ONE formatter for both ends
 * would contradict one of its two neighbours on exactly the blowout frames the
 * issue says the fix has to survive ("any fix has to read correctly at +49").
 *
 * Each arm below pins the caption to the neighbour that end belongs to.
 */
describe("#5995 each end of the caption matches the line that prints it", () => {
  it("says 100% when the hero says 100%, not the >99% of the line below", () => {
    // .996 renders 100. The hero prints a bare `100`; `formatProbability`
    // would print `>99%` for the same value.
    const html = draw(0.996, 0.344);

    expect(html).toContain(heroPrints(100));
    expect(html).toContain(`Wolverines 34% → 100% ${SINCE_OPEN}`);
  });

  it("spells the OPENING end exactly as the Opened line spells it", () => {
    // An opening above the clamp: the line below prints `>99%`, so the caption
    // must too. Printing a bare `100%` here would contradict the sentence
    // directly beneath it.
    const html = draw(0.344, 0.996);

    expect(html).toContain("Opened &gt;99%");
    expect(html).toContain(`Wolverines &gt;99% → 34% ${SINCE_OPEN}`);
  });

  it("carries the low clamp the same way", () => {
    // .004 renders 0, which `formatProbability` prints as `<1%` rather than a
    // `0%` that reads as impossible (UX-P046).
    const html = draw(0.344, 0.004);

    expect(html).toContain("Opened &lt;1%");
    expect(html).toContain(`Wolverines &lt;1% → 34% ${SINCE_OPEN}`);
  });
});
