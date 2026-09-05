// ux/1081 (#3230) — the rain card's heading counts its own tiles.
//
// 🔴 WHAT WAS SHIPPED. `RainForecast` printed the literal string
// `NYC · 7-day rain probability` and laid its tiles into the literal grid
// `repeat(7, minmax(70px, 1fr))`. Neither number came from the payload. On
// production on Sat 2026-09-05 the card drew TWO tiles under that heading and
// into those seven tracks: at 1280px, two ~90px tiles and ~600px of trailing
// white space beneath a promise of seven days.
//
// 🔴 THE TWO WAS RIGHT. Measured at the venue, not in our tables: Kalshi's
// `KXRAIN` series had 44 open markets under exactly two event tickers
// (`KXRAIN-26SEP05`, `KXRAIN-26SEP06`). The card was not dropping five days.
//
// 🔴 WHY THE ASSERTIONS COUNT RATHER THAN MATCH. A guard that pins the string
// "NYC · 2-day rain probability" passes on today's population and says nothing
// about the class — it would go green on a card hard-coded to say 2, and red
// on the day the venue lists seven, which is the correct behaviour. So every
// arm here derives the number out of the heading the component rendered and
// compares it with the tiles the component rendered, at four populations:
//
//   N = 0  → no horizon in the heading at all (there is nothing to count).
//   N = 1  → heading says 1, one tile.
//   N = 2  → the production specimen.
//   N = 7  → the old literal is still reachable, and the full-width layout
//            it shipped with is unchanged.
//
// Arm 7 matters as much as arm 2: a "fix" that deleted the number, or that
// pinned the grid to the row count with no cap, would pass 0/1/2 and quietly
// change the layout the card has always had at full width.

import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import RainForecast from "@/components/weather/RainForecast";
import { RAIN_HEADING_NO_COUNT } from "@/lib/rainCardHeading";

let swrPayload: unknown = undefined;
jest.mock("swr", () => ({
  __esModule: true,
  default: () => ({ data: swrPayload, error: undefined }),
}));

jest.mock("@/lib/weatherApi", () => ({
  fetchRain: () => Promise.resolve({ daily: [], monthly: [] }),
}));

type Row = { day: string; date: string; iso: string; prob: number; icon: string };

/** `n` consecutive dated days, none of them today, so no tile says "Today". */
function days(n: number): Row[] {
  return Array.from({ length: n }, (_, i) => {
    const dayOfMonth = 11 + i; // 2026-01-11 onwards: fixed, never today.
    return {
      day: ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"][i % 7],
      date: `Jan ${dayOfMonth}`,
      iso: `2026-01-${dayOfMonth}`,
      prob: 10 + i,
      icon: "☀️",
    };
  });
}

function render(daily: Row[]): string {
  swrPayload = { daily, monthly: [] };
  return renderToStaticMarkup(React.createElement(RainForecast));
}

/** How many day tiles the card actually drew. */
function tileCount(markup: string): number {
  return markup.split('data-testid="rain-day-tile"').length - 1;
}

/** The horizon the heading claims, or `null` if it claims none. */
function headingDays(markup: string): number | null {
  const m = markup.match(/NYC · (\d+)-day rain probability/);
  return m ? Number(m[1]) : null;
}

/** The `grid-template-columns` the tiles were laid into. */
function gridTracks(markup: string): number | null {
  const m = markup.match(/grid-template-columns:repeat\((\d+),/);
  return m ? Number(m[1]) : null;
}

afterEach(() => {
  swrPayload = undefined;
});

describe("the heading never promises more days than the card draws", () => {
  test.each([1, 2, 7])("%i day(s) held → heading says %i, and %i tiles exist", (n) => {
    const markup = render(days(n));
    expect(tileCount(markup)).toBe(n);
    expect(headingDays(markup)).toBe(n);
  });

  test("two days — the production specimen — never says seven", () => {
    const markup = render(days(2));
    expect(markup).not.toContain("7-day rain probability");
    expect(headingDays(markup)).toBe(2);
    expect(tileCount(markup)).toBe(2);
  });

  test("no days held → the heading carries no horizon at all", () => {
    const markup = render([]);
    expect(tileCount(markup)).toBe(0);
    expect(headingDays(markup)).toBeNull();
    expect(markup).toContain(RAIN_HEADING_NO_COUNT);
    // The empty state is the one ux/1069 shipped and it must survive: an
    // honest sentence, not a skeleton that pulses forever.
    expect(markup).toContain("No live rain markets right now");
  });

  test("still loading → no horizon is claimed before a payload arrives", () => {
    swrPayload = undefined;
    const markup = renderToStaticMarkup(React.createElement(RainForecast));
    expect(headingDays(markup)).toBeNull();
    expect(markup).toContain(RAIN_HEADING_NO_COUNT);
  });
});

describe("the layout makes the same claim the heading does", () => {
  test.each([1, 2])("%i day(s) → %i tracks, capped and centred", (n) => {
    const markup = render(days(n));
    expect(gridTracks(markup)).toBe(n);
    // Capped so two days cannot stretch into two half-card slabs, and centred
    // so the space left over reads as deliberate rather than as a failed load.
    expect(markup).toContain("margin-left:auto");
    expect(markup).toContain("max-width:");
  });

  test("seven days → the full-width layout that shipped, unchanged", () => {
    const markup = render(days(7));
    expect(gridTracks(markup)).toBe(7);
    expect(markup).toContain("grid-template-columns:repeat(7, minmax(70px, 1fr))");
    // No cap and no centring at full width: the grid fills the card as before.
    const gridStart = markup.indexOf("grid-template-columns:repeat(7");
    const styleAttr = markup.slice(gridStart, gridStart + 120);
    expect(styleAttr).not.toContain("max-width");
  });

  test("a payload longer than the card's width still lays down seven tracks", () => {
    // Defensive: if Kalshi ever lists more than a week, the extra tiles wrap
    // onto a second row of the same seven tracks rather than squeezing every
    // tile below the 70px floor — the behaviour the card already had. The
    // heading counts all of them, not just the ones on the first row.
    const markup = render(days(9));
    expect(gridTracks(markup)).toBe(7);
    expect(tileCount(markup)).toBe(9);
    expect(headingDays(markup)).toBe(9);
  });
});
