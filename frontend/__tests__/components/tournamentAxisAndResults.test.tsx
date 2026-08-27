/**
 * ITEM 6 (the chart's x-axis) and ITEM 9 (decided-match scores) — UX-P139.
 *
 * Both are "the page was missing an orientation the reader needs", and both are
 * asserted against the RENDER rather than against the pure layer, because a
 * library test stays green the day the component stops printing the feature
 * (`reference_plant_must_hit_the_render`).
 */

import React from "react";
import { renderToStaticMarkup } from "react-dom/server";

import ContenderChart from "@/components/tournament/ContenderChart";
import TournamentResults from "@/components/tournament/TournamentResults";
import {
  axisSpanDays,
  axisTicks,
  chartGeometry,
  chartSeriesFor,
  seriesPoints,
  shortDateLabel,
} from "@/lib/contenderChart";
import {
  DRAW_ORDER,
  drawIsPriced,
  formatPrematch,
  prematchCoverage,
  resultSentence,
  resultsEmptyReason,
  resultsForDraw,
  roundHeading,
  sortedResults,
  type TournamentResult,
  type TournamentResults as ResultsModel,
} from "@/lib/tournamentResults";
import type { TournamentRow } from "@/lib/tournament";

// ---------------------------------------------------------------------------
// ITEM 6 — "The chart needs x-axis orientation — dates/ticks"
// ---------------------------------------------------------------------------

function row(overrides: Partial<TournamentRow> = {}): TournamentRow {
  return {
    entity_key: "carlos-alcaraz",
    display_name: "Carlos Alcaraz",
    seed: 1,
    country: null,
    rank: 1,
    state: "live",
    probability: 0.26,
    probability_is_live: true,
    observed_at: "2026-08-27T00:00:00+00:00",
    age_hours: 0.2,
    price_state: "live",
    freshest_observed_at: "2026-08-27T00:00:00+00:00",
    freshest_age_hours: 0.2,
    stale_sources: [],
    mixed_freshness: false,
    source_count: 2,
    sources: [],
    blend_rule: "equal_weight_midpoint",
    divergent: false,
    trend: [
      { date: "2026-07-28", probability: 0.19 },
      { date: "2026-08-11", probability: 0.22 },
      { date: "2026-08-20", probability: 0.24 },
      { date: "2026-08-26", probability: 0.26 },
    ],
    trend_delta: 0.07,
    ...overrides,
  };
}

describe("item 6 — the chart's x-axis", () => {
  const rows = [
    row(),
    row({ entity_key: "alexander-zverev", display_name: "Alexander Zverev", rank: 2,
      probability: 0.21 }),
  ];
  const selection = rows.map((r) => r.entity_key);
  const geometry = chartGeometry(chartSeriesFor(rows, selection), "ALL", 320, 96);

  it("puts three ticks on a multi-reading domain — first, median, last", () => {
    // Three because the axis is 320 units inside a 358px box and a `26 Aug`
    // label is ~34px: four collide at the ends, two leave the middle
    // unanchored.
    const ticks = axisTicks(geometry);
    expect(ticks).toHaveLength(3);
    expect(ticks[0].date).toBe(geometry.dates[0]);
    expect(ticks[2].date).toBe(geometry.dates[geometry.dates.length - 1]);
    expect(ticks[0].x).toBe(0);
    expect(ticks[2].x).toBe(320);
  });

  /* ═══ UX-P146: THE AXIS IS A CALENDAR NOW, NOT A LIST ═══
   *
   * Alex, on the UX-P145 desktop artifact: the headline chart's x-axis has
   * weird spacing. It did. UX-P139 spaced every point by its INDEX in the list
   * of observed dates, so a day and a fortnight were the same step, and the
   * interior tick was the median OBSERVATION rather than the middle of the
   * window. The tests below are the replacement contract; the one they replace
   * asserted the ordinal placement directly.
   */

  it("places ticks by the CALENDAR, not by position in the list", () => {
    const ticks = axisTicks(geometry);
    const day = (iso: string) => Date.parse(`${iso}T00:00:00Z`) / 86_400_000;
    const first = day(geometry.dates[0]);
    const last = day(geometry.dates[geometry.dates.length - 1]);
    for (const tick of ticks) {
      // Still a real observed date — an axis must not label a day nothing was
      // read. Only its POSITION changed.
      expect(geometry.dates).toContain(tick.date);
      expect(tick.x).toBeCloseTo(((day(tick.date) - first) * 320) / (last - first), 5);
    }
  });

  it("the interior tick is the middle of the WINDOW, not the middle of the list", () => {
    // The fixture domain is 28 Jul, 11 Aug, 20 Aug, 26 Aug — deliberately
    // uneven. The list's median is 20 Aug (index 2 of 4). The window's
    // midpoint is 11.5 Aug, so the tick snaps to 11 Aug.
    const ticks = axisTicks(geometry);
    expect(ticks.map((t) => t.date)).toEqual(["2026-07-28", "2026-08-11", "2026-08-26"]);
    // …and it sits near the middle of the plot, where a middle label belongs.
    expect(ticks[1].x / 320).toBeGreaterThan(0.45);
    expect(ticks[1].x / 320).toBeLessThan(0.55);
    // The old behaviour, stated so the regression is unmistakable: the median
    // observation would have been drawn two thirds of the way across and
    // labelled as the midpoint.
    expect((2 * 320) / 3).toBeGreaterThan(ticks[1].x + 50);
  });

  it("PROOF ON REAL DATA: the gap the old axis deleted", () => {
    // The production men's board carries 23 observed dates: 2026-07-28 through
    // 08-17 daily, then an EIGHT-DAY HOLE, then 08-26 and 08-27.
    const dates = [
      ...Array.from({ length: 21 }, (_unused, i) =>
        new Date(Date.UTC(2026, 6, 28 + i)).toISOString().slice(0, 10)
      ),
      "2026-08-26",
      "2026-08-27",
    ];
    expect(dates).toHaveLength(23);
    expect(dates[20]).toBe("2026-08-17");

    const real = { dates, width: 320, height: 96 };
    const ticks = axisTicks(real);

    // BEFORE: index-spaced. The interior tick was `dates[11]` = 08-08, drawn at
    // exactly 50% and read by a user as the midpoint of a 30-day window whose
    // true midpoint is 12 Aug.
    expect(dates[11]).toBe("2026-08-08");
    // AFTER: the tick is 12 Aug and it is not at 50%, because 12 Aug is not.
    expect(ticks[1].date).toBe("2026-08-12");

    // And the squash. The last nine calendar days used to occupy 2 of 22 steps
    // — 9% of the axis — while the first eleven days took 50% of it. Now every
    // day is worth the same width, so the two stretches are drawn in
    // proportion to the time they cover.
    const width = (fromIso: string, toIso: string) => {
      const day = (iso: string) => Date.parse(`${iso}T00:00:00Z`) / 86_400_000;
      return ((day(toIso) - day(fromIso)) * 320) / (day(dates[22]) - day(dates[0]));
    };
    const tail = width("2026-08-18", "2026-08-27"); // 9 days
    const head = width("2026-07-28", "2026-08-08"); // 11 days
    // Comparable stretches, comparable widths — the old axis drew these at
    // 28.8 and 160.0, a 5.6x distortion.
    expect(tail / head).toBeGreaterThan(0.7);
    expect(tail / head).toBeLessThan(1.0);
    const oldTail = (2 * 320) / 22;
    const oldHead = (11 * 320) / 22;
    expect(oldHead / oldTail).toBeGreaterThan(5);
  });

  it("drops the interior tick rather than nudge it into an edge", () => {
    // One old reading and a recent clump: the calendar midpoint has no nearby
    // observation, so the nearest one sits hard against the right-hand label.
    // Two accurate ticks beat three with one in the wrong place.
    const lopsided = {
      dates: ["2026-01-01", "2026-08-25", "2026-08-26", "2026-08-27"],
      width: 320,
      height: 96,
    };
    const ticks = axisTicks(lopsided);
    expect(ticks).toHaveLength(2);
    expect(ticks.map((t) => t.date)).toEqual(["2026-01-01", "2026-08-27"]);
  });

  it("the LINE uses the same scale as the ticks — they cannot disagree", () => {
    // The failure this exists to stop is the one the old design accepted
    // knowingly: a tick placed by one rule and a point placed by another, so
    // the label sits where the line is not.
    const series = chartSeriesFor(rows, selection);
    const drawn = seriesPoints(series[0], geometry, "ALL");
    const xs = drawn.split(" ").map((pair) => Number(pair.split(",")[0]));
    const ticks = axisTicks(geometry);
    // Every tick's x is one of the drawn x's, because every tick is an observed
    // date and this series carries all four of them.
    for (const tick of ticks) {
      expect(xs.some((value) => Math.abs(value - tick.x) < 0.15)).toBe(true);
    }
    // And the spacing is uneven in exactly the way the data is: 14 days, then
    // 9, then 6.
    expect(xs[1] - xs[0]).toBeCloseTo((14 * 320) / 29, 1);
    expect(xs[2] - xs[1]).toBeCloseTo((9 * 320) / 29, 1);
    expect(xs[3] - xs[2]).toBeCloseTo((6 * 320) / 29, 1);
  });

  it("offers no ticks for a domain that cannot be drawn", () => {
    expect(axisTicks({ dates: [], width: 320, height: 96 })).toEqual([]);
    expect(axisTicks({ dates: ["2026-08-26"], width: 320, height: 96 })).toEqual([]);
  });

  it("labels a date day-first, because the month repeats and the day does not", () => {
    expect(shortDateLabel("2026-08-26")).toBe("26 Aug");
    expect(shortDateLabel("2026-01-02")).toBe("2 Jan");
    expect(shortDateLabel("nonsense")).toBe("nonsense");
  });

  it("states how long the drawn window IS, which the buttons cannot", () => {
    // `ALL` on a field with four readings is four days, and the timeframe
    // button says `ALL` either way.
    expect(axisSpanDays(geometry)).toBe(29);
    expect(axisSpanDays({ dates: ["2026-08-26"], width: 320, height: 96 })).toBeNull();
  });

  it("RENDERS the ticks and their labels", () => {
    const html = renderToStaticMarkup(
      <ContenderChart rows={rows} draw="mens-singles" selection={selection} onToggle={() => {}} />
    );
    expect(html).toContain('data-testid="chart-axis"');
    expect((html.match(/data-testid="chart-axis-tick"/g) ?? []).length).toBe(3);
    expect((html.match(/data-testid="chart-axis-label"/g) ?? []).length).toBe(3);
    expect(html).toContain("28 Jul");
    expect(html).toContain("26 Aug");
    expect(html).toContain('data-testid="chart-span"');
    expect(html).toContain("29d shown");
  });

  it("labels live OUTSIDE the svg, which is non-uniformly scaled", () => {
    // `preserveAspectRatio="none"` stretches x and y independently, so SVG
    // text would be distorted. The labels are HTML positioned by the same
    // fraction of the width the tick uses.
    const html = renderToStaticMarkup(
      <ContenderChart rows={rows} draw="mens-singles" selection={selection} onToggle={() => {}} />
    );
    const svg = html.slice(html.indexOf("<svg"), html.indexOf("</svg>"));
    expect(svg).not.toContain("<text");
    expect(svg).toContain('data-testid="chart-axis-tick"');
    expect(html.indexOf('data-testid="chart-axis"')).toBeGreaterThan(html.indexOf("</svg>"));
  });

  it("says the date range in the accessible label too", () => {
    const html = renderToStaticMarkup(
      <ContenderChart rows={rows} draw="mens-singles" selection={selection} onToggle={() => {}} />
    );
    expect(html).toContain("over 29 days, 28 Jul to 26 Aug");
  });
});

// ---------------------------------------------------------------------------
// ITEM 9 — decided matches, with the score
// ---------------------------------------------------------------------------

function result(overrides: Partial<TournamentResult> = {}): TournamentResult {
  return {
    matchup_key: "espn:184607",
    draw: "mens-singles",
    draw_label: "Men's Singles",
    round: "Qualifying 1st Round",
    players: [
      { entity_key: "jacob-fearnley", display_name: "Jacob Fearnley", seed: null,
        is_winner: true, prematch_probability: null },
      { entity_key: "roberto-carballes-baena", display_name: "Roberto Carballes Baena",
        seed: null, is_winner: false, prematch_probability: null },
    ],
    winner_entity_key: "jacob-fearnley",
    score: "7-6, 6-3",
    completed_at: "2026-08-24T15:05Z",
    source_round: "Qualifying 1st Round",
    source: "espn",
    ...overrides,
  };
}

function results(overrides: Partial<ResultsModel> = {}): ResultsModel {
  return {
    matches: [result()],
    count: 1,
    unregistered_pairs: 0,
    winner_not_registered: 0,
    source_competitions: 199,
    source_scored: 181,
    source_errors: [],
    ...overrides,
  };
}

describe("item 9 — decided matches carry their score", () => {
  it("prints the score beside the outcome, winner first", () => {
    const html = renderToStaticMarkup(
      <TournamentResults results={results()} draw="mens-singles" />
    );
    expect(html).toContain('data-testid="result-score"');
    expect(html).toContain("7-6, 6-3");
    // Winner's row comes first and is the one marked `won`.
    const winnerIndex = html.indexOf("Jacob Fearnley");
    const loserIndex = html.indexOf("Roberto Carballes Baena");
    expect(winnerIndex).toBeLessThan(loserIndex);
    expect(html).toContain('data-outcome="won"');
    expect(html).toContain('data-outcome="lost"');
  });

  it("says WHERE the score came from", () => {
    const html = renderToStaticMarkup(
      <TournamentResults results={results()} draw="mens-singles" />
    );
    expect(html).toContain('data-testid="results-provenance"');
    expect(html).toContain("Scores from ESPN");
  });

  it("shows a retirement as a result with no score, never as half a score", () => {
    const html = renderToStaticMarkup(
      <TournamentResults results={results({ matches: [result({ score: null })] })} draw="mens-singles" />
    );
    expect(html).toContain('data-has-score="false"');
    expect(html).toContain('data-testid="result-no-score"');
    // The outcome is still there — knowing who won is most of the value.
    expect(html).toContain("Jacob Fearnley");
    expect(html).toContain("retirement or walkover");
  });

  it("uses ESPN's finer round wording where the register has one bucket", () => {
    expect(roundHeading(result())).toBe("Qualifying 1st Round");
    expect(roundHeading(result({ source_round: null, round: "qualifying" }))).toBe("Qualifying");
  });

  it("orders newest first — a results list is read for what just happened", () => {
    const older = result({ matchup_key: "a", completed_at: "2026-08-24T12:00Z" });
    const newer = result({ matchup_key: "b", completed_at: "2026-08-24T18:00Z" });
    expect(sortedResults([older, newer]).map((r) => r.matchup_key)).toEqual(["b", "a"]);
  });

  it("writes the sentence a result IS, winner first, surnames only", () => {
    expect(resultSentence(result())).toBe("Fearnley beat Carballes Baena 7-6, 6-3");
    expect(resultSentence(result({ score: null }))).toBe("Fearnley beat Carballes Baena");
  });

  it("distinguishes the three empties, because they need different people", () => {
    expect(resultsEmptyReason(undefined)).toBe("Results are not loaded.");
    expect(resultsEmptyReason(results({ matches: [], source_errors: ["timeout"] })))
      .toContain("could not reach the results feed");
    expect(resultsEmptyReason(results({ matches: [], source_competitions: 199 })))
      .toContain("199 matches have finished");
    expect(resultsEmptyReason(results({ matches: [], source_competitions: 0 })))
      .toBe("No match has finished yet.");
    expect(resultsEmptyReason(results())).toBeNull();
  });

  it("counts the coverage gap rather than letting a short list speak for it", () => {
    const html = renderToStaticMarkup(
      <TournamentResults results={results({ unregistered_pairs: 117 })} draw="mens-singles" />
    );
    expect(html).toContain("117 other finished matches");
  });
});

// ---------------------------------------------------------------------------
// ITEM 12 — the doubles section is built and waiting
// ---------------------------------------------------------------------------

describe("item 12 — doubles and mixed doubles are accepted, not special-cased", () => {
  it("knows all five draws, singles first", () => {
    expect([...DRAW_ORDER]).toEqual([
      "mens-singles", "womens-singles", "mens-doubles", "womens-doubles", "mixed-doubles",
    ]);
  });

  it("marks the doubles draws as not-yet-priced without hiding them", () => {
    // Censused 2026-08-26: zero US Open doubles markets at either source. The
    // section is ready; the markets are not.
    expect(drawIsPriced("mens-singles")).toBe(true);
    expect(drawIsPriced("mixed-doubles")).toBe(false);
  });

  it("renders a doubles result with no code change the day one arrives", () => {
    const doubles = results({
      matches: [
        result({
          matchup_key: "espn:190001",
          draw: "mixed-doubles",
          draw_label: "Mixed Doubles",
          round: "Round of 16",
          source_round: "Round of 16",
          players: [
            { entity_key: "a-b", display_name: "Hunter / Krawczyk", seed: 2,
              is_winner: true, prematch_probability: null },
            { entity_key: "c-d", display_name: "Siniakova / Zhang", seed: null,
              is_winner: false, prematch_probability: null },
          ],
          winner_entity_key: "a-b",
          score: "6-4, 7-5",
        }),
      ],
    });
    const html = renderToStaticMarkup(
      <TournamentResults results={doubles} draw="mixed-doubles" />
    );
    expect(html).toContain('data-draw="mixed-doubles"');
    expect(html).toContain("Mixed Doubles");
    expect(html).toContain("Hunter / Krawczyk");
    expect(html).toContain("6-4, 7-5");
  });

  it("stays out of the way for an unpriced draw with nothing played", () => {
    const html = renderToStaticMarkup(
      <TournamentResults
        results={results({ matches: [], source_competitions: 0 })}
        draw="womens-doubles"
      />
    );
    expect(html).toBe("");
  });

  it("filters strictly by draw — a men's result never leaks into the women's tab", () => {
    const both = results({
      matches: [result(), result({ matchup_key: "w", draw: "womens-singles" })],
      count: 2,
    });
    expect(resultsForDraw(both, "mens-singles")).toHaveLength(1);
    expect(resultsForDraw(both, "womens-singles")).toHaveLength(1);
    const html = renderToStaticMarkup(<TournamentResults results={both} draw="womens-singles" />);
    expect(html).toContain('data-count="1"');
  });
});

// ---------------------------------------------------------------------------
// UX-P146 — a finished match shows what the market said BEFORE it
//
// Alex, on the UX-P145 desktop artifact: "finished outcomes on the right must
// show their PRE-MATCH probabilities alongside the result — a result without
// the prior probability is half the story on a probability product."
// ---------------------------------------------------------------------------

/** The same fixture with a real prior on both sides. */
function withPrior(winner: number, loser: number, overrides: Partial<TournamentResult> = {}) {
  const base = result(overrides);
  return {
    ...base,
    players: base.players.map((player) => ({
      ...player,
      prematch_probability: player.is_winner ? winner : loser,
    })),
  };
}

describe("UX-P146 — the prior beside the result", () => {
  it("prints each player's pre-match number on their own line", () => {
    const html = renderToStaticMarkup(
      <TournamentResults results={results({ matches: [withPrior(0.62, 0.38)] })} draw="mens-singles" />
    );
    expect((html.match(/data-testid="result-prematch"/g) ?? []).length).toBe(2);
    expect(html).toContain("62%");
    expect(html).toContain("38%");
    // The machine-readable half, for the sentinels and the cert.
    expect(html).toContain('data-prematch="0.62"');
    expect(html).toContain('data-prematch="0.38"');
  });

  it("the upset is legible, which is the whole reason for the column", () => {
    // Production, men's qualifying second round 2026-08-26: Colton Smith went
    // in at 39.5% and won. Without the prior that row says "somebody beat
    // somebody"; with it, it is the most interesting row on the page.
    const html = renderToStaticMarkup(
      <TournamentResults results={results({ matches: [withPrior(0.395, 0.605)] })} draw="mens-singles" />
    );
    const winnerRow = html.slice(html.indexOf('data-outcome="won"'), html.indexOf('data-outcome="lost"'));
    expect(winnerRow).toContain("40%");
    expect(winnerRow).toContain("won");
  });

  it("shows NOTHING where we held no market — never a zero, never a dash", () => {
    // 64 of 76 production results are this case. A `0%` here would say the
    // market called the winner impossible, and an em dash in a probability
    // column reads as a number we lost.
    const html = renderToStaticMarkup(
      <TournamentResults results={results()} draw="mens-singles" />
    );
    expect(html).not.toContain('data-testid="result-prematch"');
    expect(html).not.toContain('data-testid="results-prematch-note"');
    // …and the result itself is untouched by the absence.
    expect(html).toContain("7-6, 6-3");
    expect(html).toContain("Jacob Fearnley");
  });

  it("states the coverage when only some rows have a prior", () => {
    const mixed = results({
      matches: [withPrior(0.62, 0.38), result({ matchup_key: "espn:2" })],
      count: 2,
    });
    const html = renderToStaticMarkup(<TournamentResults results={mixed} draw="mens-singles" />);
    expect(html).toContain('data-with-prematch="1"');
    expect(html).toContain('data-total="2"');
    expect(html).toContain("1 of 2");
  });

  it("does not state a coverage ratio when every row has one", () => {
    // "2 of 2" is noise. The note still explains WHAT the number is, because
    // that part is owed whether or not anything is missing.
    const all = results({
      matches: [withPrior(0.62, 0.38), withPrior(0.7, 0.3, { matchup_key: "espn:2" })],
      count: 2,
    });
    const html = renderToStaticMarkup(<TournamentResults results={all} draw="mens-singles" />);
    expect(html).toContain('data-testid="results-prematch-note"');
    expect(html).toContain("before the match started");
    expect(html).not.toContain("2 of 2");
  });

  it("the coverage is counted over THIS draw, not the payload's all-draws total", () => {
    // A footnote reading "12 of 76" under a list of 24 is a footnote about a
    // different list — which is what reading the payload's counter would give.
    const both = results({
      matches: [
        withPrior(0.62, 0.38),
        result({ matchup_key: "w1", draw: "womens-singles" }),
        result({ matchup_key: "w2", draw: "womens-singles" }),
      ],
      count: 3,
      with_prematch: 1,
    });
    const html = renderToStaticMarkup(<TournamentResults results={both} draw="mens-singles" />);
    expect(html).toContain('data-total="1"');
    expect(html).not.toContain('data-total="3"');
  });

  it("never rounds a real prior to 0% or 100%", () => {
    // Through `formatProbabilityPercent` (UX-P046), not a local Math.round: a
    // 0.4% prior printed as `0%` says the market called it impossible.
    expect(formatPrematch(0.004)).toBe("<1%");
    expect(formatPrematch(0.996)).toBe(">99%");
    expect(formatPrematch(0.62)).toBe("62%");
    expect(formatPrematch(null)).toBeNull();
    expect(formatPrematch(undefined)).toBeNull();
    expect(formatPrematch(Number.NaN)).toBeNull();
  });

  it("prematchCoverage counts MATCHES, not players", () => {
    const two = [withPrior(0.62, 0.38), result({ matchup_key: "espn:2" })];
    expect(prematchCoverage(two)).toEqual({ withPrior: 1, total: 2 });
    expect(prematchCoverage([])).toEqual({ withPrior: 0, total: 0 });
  });
});
