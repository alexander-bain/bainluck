// #4342: a reader on a phone must be told WHICH tournament each row of the golf
// "Upcoming Tournaments" list is.
//
// The row is one flex line whose right block (tour chip + date range) is
// `shrink-0`, so the name absorbs every pixel of squeeze. Measured on production
// at 390px (2026-09-09, `.lat285-schedule-probe.mjs`, `scrollWidth > clientWidth`
// on the title node): the row is 308px wide inside its padding, the right block
// takes 116.8-158.3px of it, and SEVEN of the ten live tournaments truncate
// mid-word on the 138-179px that is left:
//
//     Open de Espana presented by Madrid   243.1px into 149px   short 94.1
//     Alfred Dunhill Links Championship    220.3px into 155px   short 65.3
//     DP World India Championship          191.3px into 142px   short 49.3
//     Biltmore Championship Asheville      211.1px into 164px   short 47.1
//     BMW PGA CHAMPIONSHIP                 176.3px into 139px   short 37.3
//     FedEx Open de France                 146.3px into 138px   short  8.3
//     Bank of Utah Championship            179.6px into 179px   short  0.6
//
// Letting the name take a second line renders all ten complete. Measured by
// cloning the live row and re-laying it out (`.lat285-candidate-probe.mjs`):
// 10/10 complete, never more than two lines, +140px across the whole list —
// against +250px for moving the chip and dates onto their own line, which also
// costs the right-aligned date column that makes the list scannable.
//
// ═══ WHAT THIS SUITE ASSERTS, AND WHAT IT DELIBERATELY DOES NOT ═══
//
// It asserts NO PIXEL WIDTH. jsdom has no font metrics, so every "it fits" number
// above is production geometry's claim, not this file's, and a char budget cannot
// separate fit from non-fit in a proportional font — #4309 proved that on this very
// page (`J. Skov Olesen` and `Matthew Jordan` are both 14 characters; one fits the
// cap and the other does not).
//
// What it CAN pin is the mechanism, and the mechanism is a single class. The
// load-bearing case is the third one: `truncate` and `line-clamp-2` cannot be
// combined, because `truncate` sets `white-space: nowrap`, which silently defeats
// the clamp. The tempting one-line "fix" — ADD `line-clamp-2` and leave `truncate`
// alone — renders the exact bug it claims to fix, and it looks correct in review.
//
// It also pins that the fix was not bought from the neighbours: the name must still
// travel whole (no #4309-style abbreviation, which is wrong here — a tournament has
// no surname), and the meta block must keep `shrink-0` so the chip and the dates are
// never themselves clipped.
//
// The VENUE line is deliberately left truncating. It is the secondary line, only one
// of the ten clips it, and clamping it too would double the worst-case row height for
// the least identifying half of the row. That is a choice, not an oversight.

import React from "react";
import { renderToStaticMarkup } from "react-dom/server";

import UpcomingTournaments from "@/components/golf/UpcomingTournaments";
import type { GolfUpcomingEvent } from "@/lib/types";

// The live specimens, verbatim from the production probe above.
const TRUNCATING_NAMES = [
  "Open de Espana presented by Madrid",
  "Alfred Dunhill Links Championship",
  "DP World India Championship",
  "Biltmore Championship Asheville",
  "BMW PGA CHAMPIONSHIP",
  "FedEx Open de France",
  "Bank of Utah Championship",
];

function event(name: string, i: number): GolfUpcomingEvent {
  return {
    key: `t-${i}`,
    name,
    start_date: "2026-10-08T00:00:00+00:00",
    end_date: "2026-10-11T00:00:00+00:00",
    venue: null,
    location: "Madrid, Spain",
    tour: "dpworld",
    tour_label: "DP World Tour",
  };
}

function html(names: string[]): string {
  return renderToStaticMarkup(
    <UpcomingTournaments events={names.map(event)} />,
  );
}

/**
 * The class attribute of every tournament-NAME node, in render order.
 *
 * Anchored on the row testid and taking the FIRST inner `<div>` of the row's
 * left block, because the venue line beside it is also a bare `<div>` and a
 * class-only match would conflate the two — the venue legitimately still
 * truncates, so conflating them would make this suite pass on the wrong node.
 */
function nameClasses(markup: string): string[] {
  return Array.from(
    markup.matchAll(
      /data-testid="golf-upcoming-row"[^>]*>\s*<div class="min-w-0">\s*<div class="([^"]*)"/g,
    ),
  ).map((m) => m[1]);
}

describe("#4342 — a phone reader can tell which tournament a schedule row is", () => {
  it("clamps the tournament name to two lines instead of cutting it mid-word", () => {
    const classes = nameClasses(html(TRUNCATING_NAMES));

    // Positive control: the specimens reached a name node at all. Without this an
    // empty match set satisfies every assertion below vacuously — and this regex
    // is exactly the kind that goes quiet when the markup is restructured.
    expect(classes).toHaveLength(TRUNCATING_NAMES.length);

    for (const cls of classes) {
      expect(cls).toContain("line-clamp-2");
    }
  });

  it("does not leave the name on `truncate`, which is what cuts it mid-word", () => {
    for (const cls of nameClasses(html(TRUNCATING_NAMES))) {
      expect(cls.split(/\s+/)).not.toContain("truncate");
    }
  });

  it("never carries BOTH classes — `truncate`'s nowrap silently defeats the clamp", () => {
    // The regression that looks like the fix. If someone adds the clamp without
    // removing the truncate, every name renders exactly as it does today and this
    // is the only case that says so.
    for (const cls of nameClasses(html(TRUNCATING_NAMES))) {
      const tokens = cls.split(/\s+/);
      expect(tokens.includes("truncate") && tokens.includes("line-clamp-2")).toBe(
        false,
      );
    }
  });

  it("still renders every tournament's name in full, unabbreviated", () => {
    // Not bought by shortening the name. #4309 abbreviates a GOLFER, which works
    // because a person has a surname that carries the identity; a tournament does
    // not, and "A. Dunhill Links Championship" would be a different bug.
    const markup = html(TRUNCATING_NAMES);
    for (const name of TRUNCATING_NAMES) {
      expect(markup).toContain(name);
    }
  });

  it("keeps the tour chip and dates on `shrink-0` so they are never clipped instead", () => {
    // Not bought from the neighbours either: the meta block must keep refusing to
    // shrink, or this fix just moves the clipping onto the date range.
    const markup = html(["Alfred Dunhill Links Championship"]);
    expect(markup).toContain("shrink-0");
    expect(markup).toContain("DP World Tour");
    expect(markup).toContain("Oct 8 – 11");
  });
});
