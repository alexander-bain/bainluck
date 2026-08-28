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
  shortDateLabel,
} from "@/lib/contenderChart";
import {
  DRAW_ORDER,
  drawIsPriced,
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

  it("places ticks by DOMAIN INDEX, so they agree with the line", () => {
    // `seriesPoints` spaces points by their index in the shared date list, so a
    // domain with a gap draws its two sides adjacent. A tick placed by calendar
    // arithmetic would sit where the line is not.
    const ticks = axisTicks(geometry);
    for (const tick of ticks) {
      expect(geometry.dates).toContain(tick.date);
      const index = geometry.dates.indexOf(tick.date);
      expect(tick.x).toBeCloseTo((index * 320) / (geometry.dates.length - 1), 5);
    }
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
      { entity_key: "jacob-fearnley", display_name: "Jacob Fearnley", seed: null, is_winner: true },
      { entity_key: "roberto-carballes-baena", display_name: "Roberto Carballes Baena",
        seed: null, is_winner: false },
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
            { entity_key: "a-b", display_name: "Hunter / Krawczyk", seed: 2, is_winner: true },
            { entity_key: "c-d", display_name: "Siniakova / Zhang", seed: null, is_winner: false },
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
