/**
 * #6991 — the top two of a LONGER field are not two sides of one question.
 *
 * ═══ WHAT A READER SAW ═══
 *
 * `https://bainluck.com/event/awards/tonys-2026` at 390px, production 2026-09-18:
 *
 *     Schmigadoon!                                    >99%
 *     Two Strangers (Carry a Cake Across New York)      0%
 *
 * `Schmigadoon!` is quoted at exactly `0.99`. `>99%` is a strict inequality the
 * market never published, and **Best Musical has five nominees, not two**.
 *
 * ═══ WHY IT PRINTED THAT ═══
 *
 * `TwoSidedTimeline` takes `fieldOrder(competitors).slice(0, 2)` and hands the
 * pair to `renderedDuelPercents`, which normalizes ANY two probabilities summing
 * inside `[0.99, 1.01]`. Here the top two sum to `0.99 + 0.0 = 0.99` — inside the
 * band BY COINCIDENCE, because the other three nominees are all `0.0`:
 *
 *   1. `isComplementPair([0.99, 0])` -> true (0.99 IS `COMPLEMENT_MIN`)
 *   2. `renderedCardPercents` divides by the true total: `renderedPercent(0.99/0.99)`
 *      = `renderedPercent(1.0)` = 100
 *   3. `probabilityParts(0.99, { rendered: 100 })` hits `rounded >= 100 && prob < 1`
 *      -> the `>99%` branch
 *
 * The one missing point of probability belongs to the FIELD, not to the leader.
 * Normalizing hands it to `Schmigadoon!` and prints a certainty out of it — the
 * same failure `eventConceptShareMeta` documents on the unfurl ("it can
 * manufacture a certainty") and fences there.
 *
 * ═══ THE RULE, WHICH THIS FILE'S TWO SIBLINGS ALREADY APPLY ═══
 *
 * Pairing is an arithmetic claim about the contest's SHAPE, so it may run only
 * when the served field IS the pair. `servedBoutPercents` (#6816) is already
 * fenced on `competitors.length === 2` one line below the seam this fixes, and
 * `eventConceptShareMeta` reached the same predicate from its own `US_OPEN`
 * counter-example. The local pairing (#6844) was the sole holdout.
 *
 * 🪤 REACHABILITY WAS THE WHOLE ARGUMENT, AND THE PREMISE WAS FALSE.
 * discover/169 routed this as unreachable — "`TwoSidedTimeline` renders only for
 * a two-sided `co_equal_list` hero". `co_equal_list` is emitted by THREE
 * adapters: `event_combat` (genuinely two-sided), `event_awards` ("a bout only
 * when the category came down to two nominees") and `event_election` (races).
 * `app/event/[domain]/[slug]/page.tsx` renders the hero on `isCoEqual` ALONE —
 * the only arity gate is `pair.length < 2`, which stops a field of one and never
 * a field of twenty-five.
 *
 * ═══ WHAT THIS DELIBERATELY DOES NOT CHANGE ═══
 *
 * Every genuine bout — the entire UFC/boxing population, and both arms of #6816 —
 * has `competitors.length === 2` and is untouched. That direction is asserted
 * here as explicitly as the fixed one, because a fence that also silences the
 * two-sided case would trade this defect for #6844's.
 */
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";

jest.mock("swr", () => ({ __esModule: true, default: () => ({ data: undefined }) }));
jest.mock("@/components/FuturesChart", () => ({ __esModule: true, FuturesChart: () => null }));
jest.mock("../../components/event/FighterAvatar", () => ({
  __esModule: true,
  default: () => null,
}));

import TwoSidedTimeline from "../../components/event/TwoSidedTimeline";
import type { EventConceptCompetitor } from "../../lib/types";

/** Every printed percentage in the hero, in DOM order. Boundary markers are
    escaped by static markup, so they are matched escaped and restored. */
function printed(html: string): string[] {
  return Array.from(html.matchAll(/>\s*((?:&lt;|&gt;)?\d{1,3}%)\s*</g)).map((m) =>
    m[1].replace("&lt;", "<").replace("&gt;", ">"),
  );
}

function heroNumbers(competitors: EventConceptCompetitor[]): string[] {
  return printed(
    renderToStaticMarkup(
      <TwoSidedTimeline competitors={competitors} label="Main event" evolutionMarketId={null} />,
    ),
  );
}

const row = (name: string, probability: number | null) =>
  ({ name, probability }) as EventConceptCompetitor;

/* The five nominees of Best Musical, and the 25-candidate California Governor
   field, exactly as `/api/event/…` served them on 2026-09-18. Real quotes: the
   defect is a coincidence of THESE numbers, so inventing them would prove
   nothing. */
const TONYS_BEST_MUSICAL: EventConceptCompetitor[] = [
  row("Schmigadoon!", 0.99),
  row("Two Strangers (Carry a Cake Across New York)", 0.0),
  row("The Lost Boys", 0.0),
  row("Titaníque", 0.0),
  row("Tie", 0.0),
];

const CA_GOVERNOR: EventConceptCompetitor[] = [
  row("Xavier Becerra", 0.9575),
  row("Steve Hilton", 0.042),
  ...Array.from({ length: 23 }, (_, i) => row(`also-ran ${i}`, 0.0)),
];

describe("#6991 — a longer field's top two are not a duel", () => {
  test("the Tonys specimen: a nominee quoted at exactly 0.99 prints 99%, not >99%", () => {
    expect(TONYS_BEST_MUSICAL).toHaveLength(5);
    // The coincidence that reaches the band in the first place.
    expect(TONYS_BEST_MUSICAL[0].probability! + TONYS_BEST_MUSICAL[1].probability!).toBe(0.99);

    expect(heroNumbers(TONYS_BEST_MUSICAL)).toEqual(["99%", "0%"]);
  });

  test("the certainty is what was manufactured: >99% appears nowhere", () => {
    // Keyed on the MARKER rather than on the pair, so a future rounding change
    // that reintroduces the certainty by another route still fails here.
    expect(heroNumbers(TONYS_BEST_MUSICAL).join(" ")).not.toContain(">99%");
  });

  test("California Governor: 25 candidates, top two in band, prints its own values", () => {
    expect(CA_GOVERNOR).toHaveLength(25);
    const sum = CA_GOVERNOR[0].probability! + CA_GOVERNOR[1].probability!;
    expect(sum).toBeGreaterThanOrEqual(0.99);
    expect(sum).toBeLessThanOrEqual(1.01);

    // 0.9575 -> 96, 0.042 -> 4 on their own. Unchanged from what production
    // prints today, which is the point: the fence costs this page nothing.
    expect(heroNumbers(CA_GOVERNOR)).toEqual(["96%", "4%"]);
  });

  test("a field of exactly two is STILL paired — #6844 is not undone", () => {
    // The Power Slap specimen #6844 shipped for: exact complements on a
    // half-cent grid, which round to 68/33 = 101 separately and 68/32 paired.
    expect(heroNumbers([row("Brandon Wilson", 0.675), row("Brian Ellis", 0.325)])).toEqual([
      "68%",
      "32%",
    ]);
  });

  test("a two-row field whose quotes sum to 1.01 is still paired — #6816's bout", () => {
    // Tsarukyan / Ruffy: 74 + 28 = 102 unpaired, 73 / 27 paired.
    expect(heroNumbers([row("Arman Tsarukyan", 0.735), row("Mauricio Ruffy", 0.275)])).toEqual([
      "73%",
      "27%",
    ]);
  });

  test("a THREE-row field with the same two leaders is no longer paired", () => {
    // discover/169's probe shape. The third row is what makes the pairing a
    // false claim, and it is the only difference from the test above.
    expect(
      heroNumbers([
        row("Arman Tsarukyan", 0.735),
        row("Mauricio Ruffy", 0.275),
        row("a third competitor", 0.01),
      ]),
    ).toEqual(["74%", "28%"]);
  });
});
