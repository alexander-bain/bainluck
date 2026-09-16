// #4882 — the chip over the win-probability chart names WHAT IT COUNTS.
//
// It counted crossings of the 50% line by the primary series and called them
// "Lead changes". Alex saw it first on the NFL opener — `Lead changes (9)` on a
// 13–10 game with about three — and the specimen that settles the argument is
// `/events/15296797`, Banfield v Central, **FINAL 1–1**, printing
//
//     ◆ Lead changes (138)
//
// three lines under a hero reading `FINAL - TIED`. All 138 are crossings of a
// fifteen-day PRE-KICKOFF odds line: that page carries zero post-kickoff points
// (measured in #6349). At nine-on-three a reader can believe the number is
// merely wrong; at 138 on a draw it is impossible as a fact about the score, so
// the chip was reading market churn to the reader in in-game vocabulary.
//
// ═══ THE FIX IS THE NOUN, WHICH IS WHY THIS GUARD IS ABOUT THE LABEL ═══
//
// No tightening of the crossing count makes "lead changes" true of a pre-game
// price series, so nothing here asserts a threshold. Two nouns that look right
// and are not, both rejected on the issue before building:
//
//   · "Momentum swings" — half the specimens are pages whose own hero reads
//     "Starts in 3h". A match that has not started has no momentum either.
//   · "Favorite flips" — the house's own gloss for this quantity
//     (`EIBadge.tsx`, "Times the favorite flipped"), and true for NFL and
//     tennis. An overclaim on a THREE-WAY sport: this axis is home-win%
//     against everything else, so home crossing 50 means more-likely-than-not
//     became less, while the favourite may be the draw. The 138 is soccer.
//
// The word it landed on is NOT this branch's invention. `highlights.py:1312`
// ruled the same class under #5439 — the card that said "Lead change" was fed
// by the same 50%-crossing count — and it prints **"Odds flipped"**, which iOS
// already classifies (`EventCardView.swift:531`). One quantity, one name, on
// the card, the chart and the app. This branch's own first answer was "Crossed
// 50%": correct English, and a second vocabulary for a thing already named.
//
// So the assertions are: the count is printed under a label that makes no claim
// about the score, and THE NUMBER ITSELF DID NOT MOVE — a rename that also
// changed the arithmetic would be a different ship wearing this one's name.

import React from "react";
import { readFileSync } from "fs";
import { join } from "path";
import { renderToStaticMarkup } from "react-dom/server";

jest.mock("@/components/Analytics/AnalyticsProvider", () => ({
  __esModule: true,
  useAnalyticsContext: () => ({ track: () => {} }),
  AnalyticsProvider: ({ children }: { children: React.ReactNode }) => children,
}));

jest.mock("recharts", () => {
  const actual = jest.requireActual("recharts");
  return {
    __esModule: true,
    ...actual,
    ResponsiveContainer: ({ children }: { children: React.ReactElement }) =>
      React.cloneElement(children, { width: 390, height: 300 }),
  };
});

import OddsChart from "@/components/OddsChart";

/** Fixed anchor — never Date.now() (gotcha #44). */
const FIRST_POINT = Date.UTC(2026, 8, 6, 19, 0, 0);

const series = (probs: number[]) =>
  probs.map((p, i) => ({
    timestamp: new Date(FIRST_POINT + i * 3_600_000).toISOString(),
    home_probability: p,
    away_probability: 1 - p,
  }));

/** Four crossings and not one lead change: the match below finished 1–1, and
 *  every point here is a pre-kickoff price. None sits exactly ON 50, so the
 *  asymmetric `>= 50` / `<= 50` boundary (its own open question on the issue)
 *  is deliberately not in play — this file is about the noun. */
const CROSSES_FOUR_TIMES = series([0.6, 0.4, 0.6, 0.4, 0.6]);

/** Negative control: a market that never approaches 50. */
const NEVER_CROSSES = series([0.65, 0.66, 0.64, 0.65, 0.66]);

function render(kalshi: ReturnType<typeof series>) {
  return renderToStaticMarkup(
    <OddsChart
      history={[]}
      winProbHistory={{ kalshi }}
      winProbSources={{
        kalshi: { display_name: "Kalshi", color: "#22c55e", type: "market", snapshot_count: 5 },
      }}
      homeTeam="Banfield"
      awayTeam="Central"
      commenceTime="2026-09-14T19:00:00+00:00"
      isLive={false}
      eventStatus="closed"
      // `all`, not `live`: these points PREDATE kickoff, which is the whole
      // specimen. On the `Since Start` window the real page shows no chip at
      // all — measured on `/events/15308357` (#4882, comment 4).
      externalTimeRange="all"
    />,
  );
}

describe("#4882 — the count is labelled with the thing it counts", () => {
  it("prints the crossings under a label that claims nothing about the score", () => {
    const html = render(CROSSES_FOUR_TIMES);

    // Not vacuous: the rig has to have drawn the chart, or every absence
    // assertion below passes over an empty state (#3425's lesson, next door).
    expect(html).toContain("recharts-line-curve");

    // What a reader on a 1–1 final must NOT be told happened four times.
    expect(html).not.toMatch(/lead change/i);

    // And the number is still offered, under the name the rest of the product
    // already uses for it — the subject moved from the field to the market,
    // which is where the observation was taken.
    expect(html).toContain("Odds flipped (4)");
  });

  it("control: the arithmetic did not move with the noun", () => {
    // Four crossings is a fact about the fixture, counted by hand: 60→40,
    // 40→60, 60→40, 40→60. If this reads 3 or 5 the rename changed the
    // counter, and the chip is now honest about a different quantity.
    const printed = /Odds flipped \((\d+)\)/.exec(render(CROSSES_FOUR_TIMES));
    expect(printed).not.toBeNull();
    expect(Number(printed![1])).toBe(4);
  });

  it("negative control: a market that never crosses 50 offers no chip at all", () => {
    // The toggle is gated on `crossingCount > 0`, and that gate is the reason
    // a rename cannot be proved by string-absence alone: a build that rendered
    // NOTHING would pass the first assertion above. This arm is what stops it.
    const html = render(NEVER_CROSSES);
    expect(html).toContain("recharts-line-curve");
    expect(html).not.toMatch(/lead change/i);
    expect(html).not.toContain("Odds flipped");
  });
});

describe("#4882 — the two other places the same words were printed", () => {
  const read = (rel: string) =>
    readFileSync(join(__dirname, "../../", rel), "utf8");

  /** The legend sits behind the toggle's own state, so it cannot be reached by
   *  `renderToStaticMarkup` (this repo has no interaction harness). It is read
   *  from source, bounded to its own block — the idiom this chart's other
   *  guards use — because the issue requires it to move WITH the chip: it
   *  prints the same words for the same number. */
  it("the legend under the chart says exactly what the chip says", () => {
    const SOURCE = read("components/OddsChart.tsx");
    const start = SOURCE.indexOf("{/* Odds-flip legend");
    if (start < 0) {
      throw new Error(
        "the odds-flip legend block was not found in OddsChart — this guard " +
          "cannot check what it cannot locate; find the block and re-anchor it.",
      );
    }
    // Bounded by the block's own closing, and taken from the first <span> so
    // the window is the RENDERED text rather than the comment above it — a
    // scan over the whole block would read this file's history lesson and
    // report the old words as the defect.
    const block = SOURCE.slice(start, SOURCE.indexOf("</div>", start));
    const rendered = block.slice(block.indexOf("<span"));
    expect(rendered).toContain("Odds flipped");
    expect(rendered).not.toMatch(/lead change/i);
  });

  /** `EIBadge`'s row is a different number — the backend Excitement Index —
   *  but the backend counts the same thing and says so: `excitement_index.py`
   *  and `pulse.py` both annotate `lead_changes` as "50% crossings". Fixing
   *  the chart chip and leaving this row would leave a sibling wearing the
   *  bug. It lives inside a hover tooltip, so it is read from source too. */
  it("the excitement tooltip's row moved with it", () => {
    const SOURCE = read("components/EIBadge.tsx");
    const start = SOURCE.indexOf("ei.metadata.lead_changes > 0");
    expect(start).toBeGreaterThan(-1);
    // From the row's first rendered element to the sibling metric below it.
    const block = SOURCE.slice(
      SOURCE.indexOf("<div", start),
      SOURCE.indexOf("comeback_factor", start),
    );
    expect(block).toContain("<span");           // the window caught the row
    // Case-insensitive on purpose: this tooltip Title-Cases every metric name
    // ("Probability Travel", "Comeback Factor"), so pinning the chart chip's
    // exact casing here would be pinning the wrong house style. What must hold
    // is that it is the same WORD as the chip and the card.
    expect(block).toMatch(/odds flipped/i);
    expect(block).not.toMatch(/lead change(s)?</i);
  });
});
