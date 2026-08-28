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
  prematchPercents,
  resultScoreLine,
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

  /* ═══ UX-P147: THE COUNT IS A TIER NOW, NOT A NUMBER ═══
   *
   * Alex, on the UX-P146 re-mock: the axis is "still oddly sparse" — increase
   * the density until it reads well. It was sparse because THREE was measured
   * once on a 358px phone and then inherited by a plot that is 817px at `2xl`.
   * `axisTicks` now emits every candidate with a `tier` naming the narrowest
   * plot its label fits in, and the component spends the tiers with `lg:` and
   * `2xl:`. The test that stood here asserted `toHaveLength(3)` and is
   * replaced, not deleted — the properties it protected (ends are the real
   * ends, at 0 and the full width) are asserted below and everywhere else.
   */

  it("always bounds the window with its two real ends", () => {
    const ticks = axisTicks(geometry);
    expect(ticks[0].date).toBe(geometry.dates[0]);
    expect(ticks[ticks.length - 1].date).toBe(geometry.dates[geometry.dates.length - 1]);
    expect(ticks[0].x).toBe(0);
    expect(ticks[ticks.length - 1].x).toBe(320);
    expect(ticks[0].tier).toBe("end");
    expect(ticks[ticks.length - 1].tier).toBe("end");
  });

  it("gets denser as the window widens, and a narrow axis is a SUBSET of a wide one", () => {
    // The property that makes widening the window feel like zooming in rather
    // than like a different chart: every label a phone shows is still there, at
    // the same position, when the desktop adds more between them.
    const dates = [
      ...Array.from({ length: 21 }, (_unused, i) =>
        new Date(Date.UTC(2026, 6, 28 + i)).toISOString().slice(0, 10)
      ),
      "2026-08-26",
      "2026-08-27",
    ];
    const ticks = axisTicks({ dates, width: 320, height: 96 });
    const upTo = (tiers: string[]) => ticks.filter((t) => tiers.includes(t.tier));

    const phone = upTo(["end", "major"]);
    const desktop = upTo(["end", "major", "wide"]);
    const wide = ticks;

    // Four, six, ten on the real men's board — against three before.
    expect(phone.map((t) => t.label)).toEqual(["28 Jul", "7 Aug", "17 Aug", "27 Aug"]);
    expect(desktop).toHaveLength(6);
    expect(wide).toHaveLength(10);

    // Subset, positions included.
    for (const tick of phone) {
      expect(desktop).toContainEqual(tick);
      expect(wide).toContainEqual(tick);
    }
    for (const tick of desktop) expect(wide).toContainEqual(tick);
  });

  it("never draws two labels closer than they can be read at their own width", () => {
    const dates = [
      ...Array.from({ length: 21 }, (_unused, i) =>
        new Date(Date.UTC(2026, 6, 28 + i)).toISOString().slice(0, 10)
      ),
      "2026-08-26",
      "2026-08-27",
    ];
    const ticks = axisTicks({ dates, width: 320, height: 96 });
    // A `26 Aug` label is ~30px; 38px is the claim each one makes. The plot is
    // 358px on a phone, ~486px at `lg`, ~817px at `2xl`.
    const plotAt: Record<string, number> = { end: 358, major: 358, wide: 486, fine: 817 };
    for (let i = 0; i < ticks.length; i += 1) {
      for (let j = i + 1; j < ticks.length; j += 1) {
        // The two share a screen only from the FINER tier's width up — which
        // is the WIDER plot of the pair, because a finer tier appears later.
        const px = Math.max(plotAt[ticks[i].tier], plotAt[ticks[j].tier]);
        const apart = (Math.abs(ticks[i].x - ticks[j].x) / 320) * px;
        expect(apart).toBeGreaterThanOrEqual(38);
      }
    }
  });

  it("thins out rather than repeating a date, when there are fewer days than slots", () => {
    // A week-long window has six interior days for eleven interior slots. It
    // must not label the same day twice, and it must not invent a day.
    const week = {
      dates: Array.from({ length: 7 }, (_unused, i) =>
        new Date(Date.UTC(2026, 7, 20 + i)).toISOString().slice(0, 10)
      ),
      width: 320,
      height: 96,
    };
    const ticks = axisTicks(week);
    expect(new Set(ticks.map((t) => t.date)).size).toBe(ticks.length);
    for (const tick of ticks) expect(week.dates).toContain(tick.date);
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

  it("the interior ticks are calendar positions, not positions in the list", () => {
    // The fixture domain is 28 Jul, 11 Aug, 20 Aug, 26 Aug — deliberately
    // uneven, with only two interior days for eleven interior slots, so both
    // survive at the coarsest tier and the axis is four labels at every width.
    const ticks = axisTicks(geometry);
    expect(ticks.map((t) => t.date)).toEqual([
      "2026-07-28", "2026-08-11", "2026-08-20", "2026-08-26",
    ]);
    // 11 Aug is 14 of 29 days in — just under half — and it is drawn there.
    // The ORDINAL axis this replaced put it one third of the way across, at
    // index 1 of 3, and labelled the two-thirds mark "20 Aug".
    expect(ticks[1].x / 320).toBeCloseTo(14 / 29, 3);
    expect(ticks[2].x / 320).toBeCloseTo(23 / 29, 3);
    expect(Math.abs(ticks[1].x - 320 / 3)).toBeGreaterThan(40);
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
    // AFTER: 12 Aug is on the axis, and it is not at 50%, because 12 Aug is
    // not the middle of 28 Jul → 27 Aug once the eight-day hole is drawn at
    // its true width.
    const midpoint = ticks.find((tick) => tick.date === "2026-08-12");
    expect(midpoint).toBeDefined();
    expect((midpoint as { x: number }).x).toBe(160);
    // ...and the hole itself is now legible as a hole: 17 Aug to 27 Aug is a
    // third of the axis with nothing in it, because that is a third of the
    // window with nothing in it.
    const seventeenth = ticks.find((tick) => tick.date === "2026-08-17");
    expect((seventeenth as { x: number }).x).toBeCloseTo((20 * 320) / 30, 1);
    expect(ticks.filter((tick) => tick.date > "2026-08-17" && tick.date < "2026-08-27"))
      .toEqual([]);

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
    expect((html.match(/data-testid="chart-axis-tick"/g) ?? []).length).toBe(4);
    expect((html.match(/data-testid="chart-axis-label"/g) ?? []).length).toBe(4);
    expect(html).toContain("28 Jul");
    expect(html).toContain("26 Aug");
    expect(html).toContain('data-testid="chart-span"');
    expect(html).toContain("29d shown");
  });

  it("spends the tier at the breakpoint — one render, three densities", () => {
    // UX-P147. The rule that must not regress is that a `wide` or `fine` tick
    // is HIDDEN below its breakpoint rather than absent from the markup: the
    // chart is server-rendered once, and the density has to come from CSS or
    // it cannot come at all.
    const dates = [
      ...Array.from({ length: 21 }, (_unused, i) =>
        new Date(Date.UTC(2026, 6, 28 + i)).toISOString().slice(0, 10)
      ),
      "2026-08-26",
      "2026-08-27",
    ];
    const dense = [
      row({ trend: dates.map((date) => ({ date, probability: 0.4 })) }),
    ];
    const html = renderToStaticMarkup(
      <ContenderChart
        rows={dense}
        draw="mens-singles"
        selection={dense.map((r) => r.entity_key)}
        onToggle={() => {}}
      />
    );
    // Every tier is present in the DOM…
    expect(html).toContain('data-tier="major"');
    expect(html).toContain('data-tier="wide"');
    expect(html).toContain('data-tier="fine"');
    // …and only the coarse ones are visible without a breakpoint.
    const ticks = [...html.matchAll(/data-testid="chart-axis-label"[^>]*/g)].map(String);
    expect(ticks).toHaveLength(10);
    for (const tick of [...html.matchAll(/<span class="([^"]*)"[^>]*data-tier="(\w+)"/g)]) {
      const [, className, tier] = tick;
      if (tier === "wide") expect(className).toContain("hidden lg:block");
      if (tier === "fine") expect(className).toContain("hidden 2xl:block");
      if (tier === "end" || tier === "major") expect(className).not.toContain("hidden");
    }
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

  /* ═══ UX-P147, ALEX'S ITEM 5: THE ROW THAT SAID "no score" ═══
   *
   * He pointed at the Dimitrov qualifying final and asked for the root cause.
   * Measured against the live ESPN scoreboard 2026-08-28T00:4xZ: competition
   * 184769 is `STATUS_WALKOVER`, note "Grigor Dimitrov (BUL) bt Otto Virtanen
   * (FIN) w/o", no `linescores` on either competitor. Not an ingest gap and
   * not a render fallback — a walkover, which we were told about and threw
   * away. The same census found the mirror defect: all 8 retirements DO carry
   * equal-length line scores, so they printed as ordinary final results.
   */

  it("names a WALKOVER, instead of shrugging at its own missing data", () => {
    const html = renderToStaticMarkup(
      <TournamentResults
        results={results({
          matches: [result({ score: null, completion: "walkover" })],
        })}
        draw="mens-singles"
      />
    );
    expect(html).toContain('data-has-score="false"');
    expect(html).toContain('data-completion="walkover"');
    expect(html).toContain("walkover");
    // NOT the old wording, and not the old guess.
    expect(html).not.toContain("no score");
    expect(html).not.toContain("usually a retirement");
    // The outcome is still there — knowing who won is most of the value.
    expect(html).toContain("Jacob Fearnley");
    // And the section says it once more, counted, at the bottom.
    expect(html).toContain("1 was a walkover, with no set played");
  });

  it("MARKS a retirement's score instead of passing it off as a finished one", () => {
    // `4-6, 7-5, 3-1` is not a scoreline a completed tennis match can have. It
    // is true, it is most of what happened, and before UX-P147 it printed with
    // nothing at all to say the match was abandoned.
    const html = renderToStaticMarkup(
      <TournamentResults
        results={results({
          matches: [result({ score: "4-6, 7-5, 3-1", completion: "retired" })],
        })}
        draw="mens-singles"
      />
    );
    expect(html).toContain("4-6, 7-5, 3-1 ret.");
    expect(html).toContain('data-score-kind="retired"');
    expect(html).toContain("1 ended in a retirement");
  });

  it("still refuses to guess when the source gives neither a score nor a reason", () => {
    const html = renderToStaticMarkup(
      <TournamentResults results={results({ matches: [result({ score: null })] })} draw="mens-singles" />
    );
    expect(html).toContain('data-testid="result-no-score"');
    expect(html).toContain("no score");
    // The old tooltip asserted "usually a retirement". A guess is worse than a
    // gap, because it reads more authoritative than one.
    expect(html).toContain("did not say why");
    expect(html).not.toContain("usually a retirement");
  });

  it("says nothing about completions when every match ran its course", () => {
    const html = renderToStaticMarkup(
      <TournamentResults
        results={results({ matches: [result({ completion: "final" })] })}
        draw="mens-singles"
      />
    );
    expect(html).not.toContain("results-completion-note");
    expect(html).not.toContain("walkover");
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

  /* ═══ UX-P147, ALEX'S ITEM 3: "raggedly aligned" ═══
   *
   * The two priors and the score have to be COLUMNS. They were not, and the
   * reason looked correct in the source: a `flex justify-between` row sizes its
   * items per line, so the prior column's right edge — and with it the score
   * column's left edge — moved with the width of each row's own score string.
   * `6-3, 6-4` is 56px and `7-6 (7-4), 3-6, 6-4` is 128px, so no two rows put
   * their numbers in the same place.
   *
   * Columns that line up ACROSS rows need one grid whose tracks every row
   * shares. That is a structural property, so this asserts the structure: one
   * grid on the list, `display: contents` rows, three tracks, and a score that
   * spans both player lines. A screenshot could not prove this and a pixel
   * assertion in jsdom would prove nothing at all — jsdom does not lay out.
   */

  it("draws the priors and the score as real columns, shared by every row", () => {
    const varied = results({
      matches: [
        withPrior(0.735, 0.265, { matchup_key: "a", score: "6-3, 6-4" }),
        withPrior(0.51, 0.49, {
          matchup_key: "b",
          score: "7-6 (7-4), 3-6, 6-4",
          completed_at: "2026-08-24T11:00Z",
        }),
      ],
      count: 2,
    });
    const html = renderToStaticMarkup(<TournamentResults results={varied} draw="mens-singles" />);

    // ONE grid, on the list, with the three tracks — not a grid per row.
    expect(html).toContain(
      'class="grid grid-cols-[minmax(0,1fr)_max-content_max-content] items-center gap-x-3 lg:gap-x-4"'
    );
    // Rows are transparent to it, so their cells land in the parent's tracks.
    expect((html.match(/class="contents" data-testid="result-row"/g) ?? []).length).toBe(2);
    // The round headings are bands INSIDE the same grid. A heading outside it
    // would reset the tracks and move the next round's score column.
    expect(html).toContain('class="col-span-3 border-t');
    // The score is drawn once per match and spans both player lines, because a
    // score describes the match and not the player it sits beside.
    expect((html.match(/data-testid="result-score"/g) ?? []).length).toBe(2);
    expect((html.match(/row-span-2/g) ?? []).length).toBe(2);
    // …and the two scores that used to set two different column edges are now
    // both in the same track.
    expect(html).toContain("6-3, 6-4");
    expect(html).toContain("7-6 (7-4), 3-6, 6-4");
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
    // 39, not 40 — see the item-4 block below. This is the exact row Alex read
    // off the UX-P146 artifact as "40/61".
    expect(winnerRow).toContain("39%");
    expect(winnerRow).toContain("won");
  });

  /* ═══ UX-P147, ALEX'S ITEM 4: A PAIR ALWAYS SUMS TO 100 ═══
   *
   * "probabilities sum to 101% on most rows (74/27, 40/61, 60/41, 67/34).
   * Round complementarily so a pair always sums to 100 — and check whether the
   * underlying pair is normalized at all."
   *
   * It is: all twelve priors on `payload-2026-08-27.json` arrive summing to
   * exactly 1.000. The 101 was made at the last step, by rounding both halves
   * of a `.5` boundary up.
   */

  it("rounds the pair ONCE, so the two priors on a row cannot sum to 101", () => {
    // The four rows Alex read off the artifact, all of which summed to 101.
    const cases: Array<[number, number, string, string]> = [
      [0.735, 0.265, "74%", "26%"],
      [0.395, 0.605, "39%", "61%"],
      [0.595, 0.405, "60%", "40%"],
      [0.665, 0.335, "67%", "33%"],
    ];
    for (const [winner, loser, winnerPct, loserPct] of cases) {
      const percents = prematchPercents(withPrior(winner, loser));
      const values = Object.values(percents) as number[];
      expect(values[0] + values[1]).toBe(100);
      const html = renderToStaticMarkup(
        <TournamentResults
          results={results({ matches: [withPrior(winner, loser)] })}
          draw="mens-singles"
        />
      );
      expect(html).toContain(`>${winnerPct}<`);
      expect(html).toContain(`>${loserPct}<`);
    }
  });

  it("keeps the FAVOURITE's number and derives the underdog's from it", () => {
    // Both sides sit on `.5` here, so half-up rounding took both to 51 and 50.
    // Only one number may be rounded; the favourite is the one that survives,
    // because it is the one a reader is looking at.
    expect(prematchPercents(withPrior(0.495, 0.505))).toEqual({
      "jacob-fearnley": 49,
      "roberto-carballes-baena": 51,
    });
  });

  it("does not invent a complement when only one side has a prior", () => {
    // There is nothing to derive from, and `100 − 62` would be a number no
    // market ever quoted, printed under a real player's name.
    const oneSided = result({
      players: [
        { entity_key: "a", display_name: "A", seed: null, is_winner: true,
          prematch_probability: 0.62 },
        { entity_key: "b", display_name: "B", seed: null, is_winner: false,
          prematch_probability: null },
      ],
      winner_entity_key: "a",
    });
    expect(prematchPercents(oneSided)).toEqual({ a: 62, b: null });
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
