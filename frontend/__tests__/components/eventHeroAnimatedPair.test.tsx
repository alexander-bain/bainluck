/**
 * live/034 S2 — guards for the ANIMATED hero pair.
 *
 * The ruling asks for an animated number on a live event. The risk it creates
 * is precise: #2085 exists because two complementary probabilities rounded
 * INDEPENDENTLY print 101, and an animation that tweens the two sides
 * separately reintroduces exactly that defect — one frame at a time, where no
 * static test would ever see it.
 *
 * So the property under test is not "does it animate". It is "can the pair ever
 * disagree, on ANY frame", plus the ways the feature could quietly change what
 * every non-pushed event renders.
 *
 * The mid-flight frames are tested through `shownPair`, the pure function that
 * makes the decision, because this harness renders with `renderToStaticMarkup`
 * — effects never run, so no tween is ever observable through the DOM. A test
 * that rendered and asserted would only ever re-check the settled state and
 * would pass no matter how badly the animation misbehaved.
 */

import React from "react";
import { renderToStaticMarkup } from "react-dom/server";

import EventHeroProbabilityPair, {
  shownPair,
} from "@/components/EventHeroProbabilityPair";

function printed(html: string): number[] {
  return (html.match(/>(\d+)</g) ?? []).map((m) => Number(m.slice(1, -1)));
}

function renderPair(props: Partial<React.ComponentProps<typeof EventHeroProbabilityPair>>) {
  return renderToStaticMarkup(
    <EventHeroProbabilityPair
      homeProb={0.09}
      awayProb={0.91}
      homePct={9}
      awayPct={91}
      homeColor="#111827"
      awayColor="#94A3B8"
      {...props}
    />,
  );
}

describe("shownPair — the pair can never disagree, on any frame", () => {
  test("mid-count, the away side is DERIVED from the counted home side", () => {
    // The counted value has not reached the target yet: this is a tween frame.
    expect(shownPair(42, 58, 21, true)).toEqual({ home: 21, away: 79 });
  });

  test("every frame of a full count sums to 100", () => {
    // THE invariant, swept across every intermediate value the count can take
    // between two served pairs — including the asymmetric 32/68 case that naive
    // independent rounding prints as 33/68.
    for (const [fromPct, toPct, awayServed] of [
      [9, 42, 58],
      [50, 50, 50],
      [68, 32, 68],
      [1, 99, 1],
      [99, 1, 99],
    ] as const) {
      for (let counted = 0; counted <= 100; counted++) {
        const { home, away } = shownPair(toPct, awayServed, counted, true);
        expect(home! + away!).toBe(100);
      }
      expect(fromPct).toBeGreaterThanOrEqual(0); // the sweep is the assertion
    }
  });

  test("settled, the SERVED pair is printed verbatim, not a derived one", () => {
    // Once the count lands, the served asymmetric pair must come back exactly —
    // 32/68, never the 32/68-derived-from-32 that happens to agree, and never
    // a re-rounded 33.
    expect(shownPair(32, 68, 32, true)).toEqual({ home: 32, away: 68 });
  });

  test("with animation off, the served pair passes straight through", () => {
    // Even if a stale counted value is lying around from a previous live run.
    expect(shownPair(32, 68, 99, false)).toEqual({ home: 32, away: 68 });
  });

  test("before the first count, the served pair passes straight through", () => {
    expect(shownPair(32, 68, null, true)).toEqual({ home: 32, away: 68 });
  });

  test("a null served pair stays null rather than becoming a number", () => {
    // Must print an em-dash, not silently invent a percent.
    expect(shownPair(null, null, 40, true)).toEqual({ home: null, away: null });
  });
});

describe("EventHeroProbabilityPair — non-pushed rendering is unchanged", () => {
  test("an un-animated pair prints exactly the served percents", () => {
    expect(printed(renderPair({}))).toEqual([9, 91]);
  });

  test("the default is unchanged for every existing caller", () => {
    // `animate` omitted entirely — the state every non-pushed surface renders
    // in. If this ever needs `animate={false}` to pass, the default flipped.
    expect(printed(renderPair({ homePct: 50, awayPct: 50, homeProb: 0.5, awayProb: 0.5 })))
      .toEqual([50, 50]);
  });

  test("first paint lands immediately even with animation on", () => {
    // Counting up from nothing on load would animate a number that never moved.
    expect(printed(renderPair({ animate: true }))).toEqual([9, 91]);
  });

  test("a missing percent prints an em-dash rather than a number", () => {
    const html = renderPair({ homePct: null, awayPct: null, animate: true });
    expect(printed(html)).toEqual([]);
    expect(html).toContain("—");
  });

  test("data-probability stays the PROBABILITY, not the animated percent", () => {
    // UX-P003: the card == hero == chart rail reads this attribute. An
    // animation that wrote the tweened percent here would break that contract
    // on every frame.
    expect(renderPair({ animate: true })).toContain('data-probability="0.09"');
  });
});
