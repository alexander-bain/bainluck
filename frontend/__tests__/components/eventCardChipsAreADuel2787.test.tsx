// THE SHARED CARD'S TWO CHIPS ARE ONE QUESTION — #2787 (4th arm of #2084).
//
// `renderedCardPercents`/`renderedDuelPercents` exist because a surface prints a
// CARD and a card has a SUM. The shared `components/EventCard.tsx` already
// imported the fix and applied it to ONE branch: the live footer's
// "Opened 62/38". Its HEADLINE CHIPS — home above, away below, two fixed slots
// holding both sides of one question — did not go through it. Each side went
// through a component-local `AnimatedProbability` that ran its own
// `Math.round(v)` inside `useTransform`, so an exact complement pair landing on
// `.5` on both sides rounded UP twice.
//
// Measured on production 2026-09-03 (`842e6167` / v4020),
// `/sports/tennis_atp_us_open`: 82/19, 20/81 and 18/83 on three of ~16 upcoming
// cards. That is the surface behind the league rails, the category grids, search
// results, pinned rows and My Stuff.
//
// WHY THE ASSERTION IS A SUM. Each side is individually CORRECT here — 0.815
// really does render 82 and 0.185 really does render 19 under half-up rounding.
// A test that checked one chip could not see this bug at all. Only the pair can.
//
// WHY THE SPRING MATTERS. The rounding happened on the spring's OUTPUT, so
// passing a pre-rounded `renderedPercent` per side would have been discarded on
// the next frame. The contract is applied to the spring's TARGET instead, which
// is why `AnimatedProbability` now takes a whole percent rather than a
// probability.
//
// RENDERED, NOT GREPPED, and BOTH DIRECTIONS PER GOTCHA #43: every "sums to 100"
// case has a sibling asserting that an ordinary pair and a NON-complement pair
// are printed exactly as before. Without them, a card that printed no chips at
// all, or one that normalized two independent prices into a fake 100, would pass
// the headline assertion.

import React from "react";
import { renderToStaticMarkup } from "react-dom/server";

jest.mock("next/link", () => {
  const ReactLib = require("react");
  return {
    __esModule: true,
    default: ({ href, children, ...props }: { href: string; children: React.ReactNode }) =>
      ReactLib.createElement("a", { href, ...props }, children),
  };
});

jest.mock("@/components/Analytics", () => ({
  useAnalyticsContext: () => ({ track: () => {} }),
}));
jest.mock("@/hooks", () => ({
  useAnalytics: () => ({ trackEventCardClick: () => {}, track: () => {} }),
}));

import EventCard from "@/components/EventCard";
import type { Event } from "@/lib/types";

const IN_THE_FUTURE = new Date(Date.now() + 3 * 3600_000).toISOString();
const IN_THE_PAST = new Date(Date.now() - 1 * 3600_000).toISOString();

/**
 * The production specimen, exactly: Shelton/Shapovalov printed 82% / 19%.
 *
 * 0.815 and 0.185 are an EXACT complement, and both land on a half-percent, so
 * both sides round up. This is not a contrived pair — the feed derives the away
 * side as `1 - home`, which is precisely what makes the case reachable.
 */
function makeEvent(over: Partial<Event> = {}): Event {
  return {
    id: 15301400,
    external_id: "evt-15301400",
    sport: "tennis_atp_us_open",
    sport_name: "US Open",
    home_team: "Ben Shelton",
    away_team: "Denis Shapovalov",
    commence_time: IN_THE_FUTURE,
    status: "scheduled",
    home_score: null,
    away_score: null,
    home_team_data: { primary_color: "#2563eb", logo_small: "h.png" },
    away_team_data: { primary_color: "#64748b", logo_small: "a.png" },
    current_odds: {
      captured_at: IN_THE_PAST,
      home_probability: 0.815,
      away_probability: 0.185,
      spread: null,
      over_under: null,
      projected_home_score: null,
      projected_away_score: null,
    },
    ...over,
  } as unknown as Event;
}

function render(event: Event): string {
  return renderToStaticMarkup(<EventCard event={event} />);
}

/** Every whole percent this card actually prints, in document order. */
function printedPercents(html: string): number[] {
  return Array.from(html.replace(/<[^>]*>/g, " ").matchAll(/(\d+)%/g)).map((m) =>
    Number(m[1]),
  );
}

describe("the shared EventCard's headline chips print one question", () => {
  it("prints both chips at all (the control every sum below depends on)", () => {
    // If the chips were not reaching the DOM, a "they sum to 100" assertion over
    // an empty list would pass for the wrong reason.
    expect(printedPercents(render(makeEvent()))).toHaveLength(2);
  });

  it("does not print 101 on a scheduled card", () => {
    // THE BUG. Before the fix this markup carried 82% and 19%.
    const percents = printedPercents(render(makeEvent()));
    expect(percents.reduce((a, b) => a + b, 0)).toBe(100);
  });

  it("keeps the favourite's number and derives the other side", () => {
    // The contract's own rule: the leader is the number that survives untouched,
    // so the point is taken off the side that is not the headline. 82 stays; 19
    // becomes 18. Asserting only the SUM would also pass for 81/19, which is a
    // different (and wrong) answer.
    const percents = printedPercents(render(makeEvent()));
    expect(percents).toContain(82);
    expect(percents).toContain(18);
    expect(percents).not.toContain(19);
  });

  it("does not print 101 on a LIVE card either", () => {
    // The live chips are a second, smaller pair of the same two slots and were
    // the same defect. `commence_time` must be in the past for `isLive`.
    const percents = printedPercents(
      render(
        makeEvent({ status: "live", commence_time: IN_THE_PAST } as Partial<Event>),
      ),
    );
    expect(percents.reduce((a, b) => a + b, 0)).toBe(100);
  });

  it("leaves an ordinary pair exactly as it was", () => {
    // The regression direction that matters most: a pair that never had the
    // problem must print the same two numbers it always did.
    const percents = printedPercents(
      render(
        makeEvent({
          current_odds: {
            captured_at: IN_THE_PAST,
            home_probability: 0.62,
            away_probability: 0.38,
            spread: null,
            over_under: null,
            projected_home_score: null,
            projected_away_score: null,
          },
        } as unknown as Partial<Event>),
      ),
    );
    expect(percents).toEqual(expect.arrayContaining([62, 38]));
  });

  it("does NOT normalize two independent prices into a fake 100", () => {
    // #2088's boundary, asserted as explicitly as the fixed direction. A pair
    // summing to 0.97 is two questions, not one; forcing it to 100 would invent
    // three points of probability. 57 and 40 must both survive.
    const percents = printedPercents(
      render(
        makeEvent({
          current_odds: {
            captured_at: IN_THE_PAST,
            home_probability: 0.57,
            away_probability: 0.4,
            spread: null,
            over_under: null,
            projected_home_score: null,
            projected_away_score: null,
          },
        } as unknown as Partial<Event>),
      ),
    );
    expect(percents).toEqual(expect.arrayContaining([57, 40]));
  });

  it("still prints a dash when there is no price to print", () => {
    // `AnimatedProbability` changed shape (probability -> whole percent), and
    // `null` had to keep meaning "no number", not "0%".
    const html = render(
      makeEvent({ current_odds: null } as unknown as Partial<Event>),
    );
    expect(printedPercents(html)).toHaveLength(0);
    expect(html.replace(/<[^>]*>/g, " ")).toContain("-");
  });
});
