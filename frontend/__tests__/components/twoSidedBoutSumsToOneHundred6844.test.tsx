/**
 * #6844 — A TWO-SIDED BOUT'S HERO PRINTED 68% AND 33%.
 *
 * ═══ THE SPECIMEN ═══
 *
 * Production, 2026-09-18 02:35Z, `/event/ufc/power-slap-23-26sep18powerslap23`
 * read at 390px (`artifacts/ux-1324/5603b-BEFORE-eventpage-ufc-chip-390.png`):
 *
 *     Main event
 *     BW  Brandon Wilson              Brian Ellis  BE
 *         68%                                 33%
 *     [————————— one split bar —————————]
 *
 * `GET /api/event/event:ufc:26sep18powerslap23`, read at 02:44Z — nine minutes
 * after the frame, and stamped to the clock rather than to the frame, because
 * "the same minute" is the kind of convenience that later gets navigated by:
 *
 *     primary.kind = "co_equal_list"
 *     Brandon Wilson  probability 0.675
 *     Brian Ellis     probability 0.325     → 1.000 exactly
 *
 * ═══ WHY THE 101 IS OURS ═══
 *
 * The pair arrives summing to one. Each side then went through
 * `formatProbability` ALONE, and JS rounds a half away from zero on both:
 * `67.5 → 68`, `32.5 → 33`. So this is not a bad price or a bad minute — it is
 * every `.5/.5` split on this surface, which is the shape a complement pair
 * takes whenever the venue quotes on a half-percent grid.
 *
 * ═══ WHY THIS IS AN ADOPTION AND NOT A NEW RULE ═══
 *
 * `renderedDuelPercents` (#2060 / UX-P114, `contracts/rendered_percent.json`) is
 * the product's standing answer and already runs on `GamePlayCard`, `/politics`
 * (#6778), `/entertainment` (#6233) and `discover/EventCard`. The event concept
 * page's hero is the surface that never adopted it. Unlike those, an event
 * competitor carries no served `*_rendered_percent`, so here the local pairing
 * is the answer rather than a fallback for an old payload.
 *
 * ═══ WHAT EACH TEST IS FOR ═══
 *
 * Only the first is the ship clause; it is satisfied on its own by normalizing
 * everything, by hard-coding a complement, or by moving one number. Hence:
 *
 *   - `an independent pair is left alone` is the control that matters most. A
 *     pair summing to 0.90 is two questions, and forcing it to 100 would INVENT
 *     ten points of probability — the exact harm `isComplementPair`'s band
 *     exists to prevent.
 *   - `the favourite survives the rounding` pins WHICH side absorbs the
 *     derivation. `42/58` also sums to 100 and is still wrong.
 *   - `a price we do not have still prints "-"` keeps #6761's arm: the pairing
 *     runs through `formatProbability`'s `rendered` option precisely so the
 *     absent-price and boundary rules are not re-derived from an integer.
 *   - `the boundary rules still run on the probability` is the reason the fix is
 *     an option and not a printed number: a served 100 over `0.996` must stay
 *     `>99%`, and its complement `<1%`, even though those two do not sum to 100.
 *     A card that prints `>99% / <1%` is honest; one that prints `100% / 0%` is
 *     not, and this arm is what stops the pairing "fixing" it into a lie.
 *   - `the split bar is untouched` proves the change moved the WORDS, not the
 *     pixels — #6778's lesson, where the bar draws the split and does not print
 *     it.
 */
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";

jest.mock("swr", () => ({ __esModule: true, default: () => ({ data: undefined }) }));
jest.mock("@/components/FuturesChart", () => ({
  __esModule: true,
  FuturesChart: () => null,
}));
jest.mock("../../components/event/FighterAvatar", () => ({
  __esModule: true,
  default: () => null,
}));

import TwoSidedTimeline from "../../components/event/TwoSidedTimeline";

type Competitor = { name: string; probability: number | null };

function render(a: Competitor, b: Competitor): string {
  return renderToStaticMarkup(
    <TwoSidedTimeline
      competitors={[a, b] as never}
      label="Main event"
      evolutionMarketId={null}
    />,
  );
}

/**
 * THE TWO NUMBERS, IN THE ORDER A READER READS THEM — left is the `accent-brand`
 * span, right is the `text-secondary` one. Read from the spans the component
 * prints into rather than from the whole card: the bar's `width: 68%` is also the
 * characters `68%` in the markup, and a guard that scans raw HTML for a percent
 * would pass on the pixels while the words stayed wrong.
 */
function printedPair(html: string): [string, string] {
  const left = html.match(/<span class="text-accent-brand">([^<]*)<\/span>/);
  const right = html.match(/<span class="text-text-secondary">([^<]*)<\/span>/);
  return [decode(left?.[1] ?? ""), decode(right?.[1] ?? "")];
}

/**
 * 🪤 The boundary markers arrive ESCAPED. `renderToStaticMarkup` writes `&gt;99%`
 * and `&lt;1%`, so a raw-markup assertion for `">99%"` fails on a component that
 * is behaving perfectly — and, worse, an assertion written the other way round
 * (`not.toContain(">99%")`) would PASS on a component that had lost the rule.
 */
function decode(s: string): string {
  return s
    .replace(/&gt;/g, ">")
    .replace(/&lt;/g, "<")
    .replace(/&amp;/g, "&")
    .trim();
}

/** Every `width:N%` in the markup, in order — the split, not the words. */
function widths(html: string): string[] {
  return Array.from(html.matchAll(/width:\s*([\d.]+)%/g)).map((m) => m[1]);
}

const asInts = (pair: [string, string]) => pair.map((s) => parseInt(s, 10));

describe("#6844 — a two-sided bout's two numbers are rounded once, together", () => {
  test("🔴 SHIP: the Power Slap 23 specimen prints 68 and 32, not 68 and 33", () => {
    const html = render(
      { name: "Brandon Wilson", probability: 0.675 },
      { name: "Brian Ellis", probability: 0.325 },
    );

    expect(printedPair(html)).toEqual(["68%", "32%"]);
    expect(asInts(printedPair(html)).reduce((x, y) => x + y, 0)).toBe(100);
  });

  test("CONTROL: the favourite survives the rounding", () => {
    // 42/58 also sums to 100 and is still the wrong card: the side the reader is
    // shown as leading must be the one that kept its own number.
    const html = render(
      { name: "Favourite", probability: 0.675 },
      { name: "Underdog", probability: 0.325 },
    );
    expect(printedPair(html)[0]).toBe("68%");
  });

  test("CONTROL: an independent pair is left alone", () => {
    // Sums to 0.90 — two questions, not two sides of one. Normalizing would
    // invent ten points of probability, which is worse than an honest 90.
    const html = render(
      { name: "Alpha", probability: 0.6 },
      { name: "Beta", probability: 0.3 },
    );
    expect(printedPair(html)).toEqual(["60%", "30%"]);
  });

  test('CONTROL: a price we do not have still prints "-"', () => {
    const one = render(
      { name: "Priced", probability: 0.675 },
      { name: "Unpriced", probability: null },
    );
    // `fieldOrder` sorts nulls last, so the priced side is always `a` (#6761).
    expect(printedPair(one)).toEqual(["68%", "-"]);

    const neither = render(
      { name: "Alpha", probability: null },
      { name: "Beta", probability: null },
    );
    expect(printedPair(neither)).toEqual(["-", "-"]);
  });

  test("CONTROL: the boundary rules still run on the probability", () => {
    // A complement pair whose rounding would claim certainty. `>99%` / `<1%` do
    // not sum to 100 and must not be "fixed" into `100% / 0%`.
    const html = render(
      { name: "Nearly certain", probability: 0.996 },
      { name: "Nearly impossible", probability: 0.004 },
    );
    expect(printedPair(html)).toEqual([">99%", "<1%"]);
  });

  test("CONTROL: the split bar is untouched", () => {
    // The bar draws the split; it does not print it. Pairing its width would
    // move a pixel to fix a word.
    const html = render(
      { name: "Brandon Wilson", probability: 0.675 },
      { name: "Brian Ellis", probability: 0.325 },
    );
    expect(widths(html)).toEqual(["68", "32"]);
  });
});
