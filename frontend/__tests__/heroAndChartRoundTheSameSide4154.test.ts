// #4154 — the hero and its own Win Probability chart print the same number.
//
// ═══ THE DEFECT, READ ON PRODUCTION ═══
//
// `/events/15307331` (Zheng v Rybakina, a US Open women's quarter-final) at
// 390×844 on 2026-09-08 ~8:20pm PT, one screen, no scrolling between the two:
//
//     hero, directly under the players' faces      27%
//     Win Probability chart, current-point callout 28%
//
// The payload carries ONE number — `hero_probability: 0.275`,
// `hero_probability_away: 0.725`, `hero_probability_source: "blend"`. Both
// elements were rendering it. They disagreed on how to round it, which is the
// thing *the blend is the product* exists to prevent.
//
// ═══ WHY IT IS NOT A ROUNDING BUG IN EITHER ARM ═══
//
// Both arms were individually obeying a contract, and the contracts differed on
// WHICH END THEY ANCHOR:
//
//   hero   `renderedDuelPercents(0.725, 0.275)` — the pair is a complement, so
//          it rounds the LARGER side once and DERIVES the smaller:
//          Rybakina 73 (rounded), Zheng 100 − 73 = 27 (derived).
//   chart  `chartAxisPercents(27.5)` — rounded `home` on its own:
//          Zheng `renderedPercent(0.275)` = 28.
//
// So `0.275` is 28 when rounded and 27 when derived from its complement, and
// neither arm is wrong about its own rule. #3892 fixed the mirror image of this
// (`0.575`: hero 58, callout 57) by changing HOW the chart rounds, and could not
// see this case, because there the charted side was the side the hero ROUNDS.
// The fix makes the chart ask the hero's own function which end to anchor.
//
// ═══ 🔴 WHY THE OBVIOUS GUARD IS THE WRONG GUARD ═══
//
// "The two sides sum to 100" PASSES ON THE BROKEN RENDER. The hero printed
// 27/73 and the chart printed 28/72 — both internally consistent, both summing
// to 100, disagreeing with each other. A sum predicate cannot see this defect
// no matter how many pairs it is pointed at, and neither can a suite that
// compares each arm to `renderedPercent` (which is the hero's answer only when
// home is the larger side — see the note in
// `chartCalloutRoundsLikeTheHero3892.test.ts`).
//
// The assertion that catches it is HERO vs CHART, FROM ONE PAYLOAD, through
// both real shipped functions. That is what this file does, and the positive
// control below fails if the old rule ever comes back.

import {
  chartAxisPercents,
  homeProbToChartAxis,
  resolveProbability,
} from "../lib/eventKeyStats";
import { renderedPercent } from "../lib/renderedPercent";
import type {
  EventDetailResponse,
  EventHistoryResponse,
} from "../lib/types";

/** The production specimen: a live blend whose HOME side is the smaller one. */
function liveBlendEvent(
  homeProbability: number,
  awayProbability: number,
): EventDetailResponse {
  return {
    id: 15307331,
    home_team: "Qinwen Zheng",
    away_team: "Elena Rybakina",
    status: "live",
    commence_time: "2026-09-08T23:00:00Z",
    hero_probability: homeProbability,
    hero_probability_away: awayProbability,
    hero_probability_source: "blend",
  } as unknown as EventDetailResponse;
}

const NO_HISTORY = {
  event_id: 15307331,
  history: [],
} as unknown as EventHistoryResponse;

/**
 * What the hero prints, through the real resolver: `homePct`/`awayPct`, the
 * fields whose own comment says "these are the numbers to PRINT". Reading
 * `homeProb` instead — the number to REASON with — is how a guard ends up
 * modelling the rule rather than calling it.
 */
function heroPrints(event: EventDetailResponse) {
  const resolved = resolveProbability(event, NO_HISTORY, null, true, false);
  return { home: resolved.homePct, away: resolved.awayPct };
}

/**
 * What the chart prints for the same payload. The live edge of `aggregate_line`
 * is pinned to `hero_probability` on the backend (`_pin_live_blend_edge`), so
 * the callout is drawing this very number a second time — which is exactly why
 * the two are comparable at all.
 */
function chartPrints(homeProbability: number) {
  return chartAxisPercents(homeProbToChartAxis(homeProbability));
}

/** The rule this ship deletes: round `home` on its own, derive `away`. */
function theOldChartRule(homeProbability: number) {
  const home = renderedPercent(homeProbability);
  return home === null
    ? { home: null, away: null }
    : { home, away: 100 - home };
}

describe("#4154 — one card, one number, one answer", () => {
  test("the exemplar: hero and callout both say 27% for Zheng, not 27 and 28", () => {
    const event = liveBlendEvent(0.275, 0.725);
    const hero = heroPrints(event);
    const chart = chartPrints(0.275);

    // What the hero has always printed, and what the reader compares against.
    expect(hero).toEqual({ home: 27, away: 73 });
    expect(chart).toEqual({ home: 27, away: 73 });
    expect(chart.home).toBe(hero.home);
    expect(chart.away).toBe(hero.away);
  });

  test("POSITIVE CONTROL: the old chart rule really did print 28 here", () => {
    // Without this the suite could be green because both arms are broken in the
    // same direction, which is precisely how #3892's suite stayed green through
    // #3892. The control pins the defect, not just the fix.
    const old = theOldChartRule(0.275);
    expect(old).toEqual({ home: 28, away: 72 });
    expect(old.home).not.toBe(heroPrints(liveBlendEvent(0.275, 0.725)).home);
  });

  test("🔴 a sum-to-100 predicate CANNOT see this defect", () => {
    // The reason this file asserts hero-vs-chart and not the sum. Both the
    // broken pair and the fixed pair total 100; only one of them agrees with
    // the hero. A guard asserting the sum passes on the broken render.
    const broken = theOldChartRule(0.275);
    expect(broken.home! + broken.away!).toBe(100);

    const fixed = chartPrints(0.275);
    expect(fixed.home! + fixed.away!).toBe(100);

    expect(broken.home).not.toBe(fixed.home);
  });

  test("#3892's exemplar still holds — this is a widening, not a replacement", () => {
    // `/events/15307463` (Khachanov, 0.575): the charted side is the one the
    // hero ROUNDS, so the answer must not move.
    const event = liveBlendEvent(0.575, 0.425);
    expect(heroPrints(event)).toEqual({ home: 58, away: 42 });
    expect(chartPrints(0.575)).toEqual({ home: 58, away: 42 });
    expect(theOldChartRule(0.575)).toEqual({ home: 58, away: 42 });
  });
});

// ═══ THE WHOLE GRID, NOT THE TWO VALUES THAT HAPPENED TO BE ON SCREEN ═══
//
// #4154's own scope note: "Not a one-off. Any complement pair on the
// half-percent grid whose two sides straddle the boundary hits it — venues
// quote on that grid, so `.xx5` is the common case." So the agreement is
// asserted across the grid rather than at the specimen, and the count of
// values the fix MOVES is asserted too — a sweep that silently stopped moving
// anything would otherwise read as a pass.
describe("#4154 — hero and chart agree across the half-percent grid", () => {
  const GRID: number[] = [];
  for (let tenth = 0; tenth <= 1000; tenth += 5) GRID.push(tenth / 1000);

  test.each(GRID)("home %p: the callout prints the hero's number", (p) => {
    const hero = heroPrints(liveBlendEvent(p, 1 - p));
    const chart = chartPrints(p);
    expect(chart.home).toBe(hero.home);
    expect(chart.away).toBe(hero.away);
  });

  test("the fix actually moves values — and only on the smaller side", () => {
    const moved = GRID.filter(
      (p) => theOldChartRule(p).home !== chartPrints(p).home,
    );

    // Every value the old rule got wrong is one where HOME is the smaller side
    // — the side the hero derives. That is the defect's shape, stated as an
    // assertion rather than as prose.
    expect(moved.length).toBeGreaterThan(0);
    for (const p of moved) expect(p).toBeLessThan(0.5);

    // And nothing on the larger side moved, so #3892's population is untouched.
    for (const p of GRID.filter((q) => q > 0.5)) {
      expect(chartPrints(p).home).toBe(theOldChartRule(p).home);
    }
  });
});
