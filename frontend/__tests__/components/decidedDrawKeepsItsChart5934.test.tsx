/**
 * ═══ #5934: A DECIDED DRAW KEEPS ITS CHART ═══
 *
 * The ship, in one sentence: when every row of a draw has settled, the
 * title-race card draws the completed journey instead of unmounting.
 *
 * WHAT HAPPENED. #5917's payload half landed at 14:46Z on the last day of the
 * US Open and correctly settled every women's row to `probability: null`. The
 * board became right and the picture disappeared: `chartableRows` filtered
 * `probability !== null`, `defaultSelection` emptied, and `ContenderChart` took
 * its `series.length === 0 → return null`. `docHeight` 3437 → 3102. The men's
 * draw was two hours from the same fate. Alex's standing ruling names this case
 * in as many words — *settled means settled: charts show the completed
 * journey*.
 *
 * ⚠️ **THE TRAP THIS FILE EXISTS TO HOLD SHUT IS THE FIX, NOT THE BUG.** The
 * cheap way to make a chart reappear is to let the legend read the last point
 * of the line — and that prints "E. RYBAKINA 99%" sixteen hours after she won
 * the title, which is the exact lie #5917 removed from the board two inches
 * above. So every arm that asserts the card is BACK also asserts no percent
 * came back with it, and ARM 2 is the one that fails if someone reaches into
 * `points` for a number.
 *
 * ARM 5 pins the other direction. Today the backend's settled-row shape emits
 * `trend: []` / `trend_hourly: []` (`tournament_board.py:538`), so this change
 * is measurably INERT until live's producer half lands — a settled row with no
 * history is still not chartable and the card still unmounts rather than
 * drawing an empty frame. That is deliberate: an empty plot is not a completed
 * journey, and notice 34 says leave the space empty rather than explain it.
 */

import React from "react";
import { renderToStaticMarkup } from "react-dom/server";

import ContenderChart from "@/components/tournament/ContenderChart";
import {
  chartableRows,
  defaultSelection,
  legendValue,
} from "@/lib/contenderChart";
import type { TournamentFinePoint, TournamentRow, TournamentTrendPoint } from "@/lib/tournament";

/** Daily keys, as the coarse series carries them. */
function days(start: string, count: number, from = 0.2): TournamentTrendPoint[] {
  const base = Date.parse(`${start}T00:00:00Z`);
  return Array.from({ length: count }, (_, i) => ({
    date: new Date(base + i * 86_400_000).toISOString().slice(0, 10),
    probability: from + i * 0.002,
  }));
}

/** Hourly instants, as the fine series carries them. */
function hours(
  startIso: string,
  count: number,
  from = 0.3,
  step = 0.01,
): TournamentFinePoint[] {
  const base = Date.parse(startIso);
  return Array.from({ length: count }, (_, i) => ({
    at: `${new Date(base + i * 3_600_000).toISOString().slice(0, 13)}:00:00Z`,
    probability: from + i * step,
  }));
}

function row(overrides: Partial<TournamentRow> = {}): TournamentRow {
  return {
    entity_key: "rybakina",
    display_name: "Elena Rybakina",
    seed: 1,
    country: "KAZ",
    rank: 1,
    state: "live",
    probability: 0.42,
    probability_is_live: true,
    observed_at: "2026-09-12T12:00:00+00:00",
    age_hours: 0.5,
    price_state: "live",
    freshest_observed_at: "2026-09-12T12:00:00+00:00",
    freshest_age_hours: 0.5,
    stale_sources: [],
    mixed_freshness: false,
    source_count: 2,
    sources: [],
    blend_rule: "mean",
    divergent: false,
    trend: days("2026-08-30", 14),
    trend_delta: 0.04,
    ...overrides,
  };
}

/**
 * The women's board as it will serve once live's producer half keeps the
 * history on a settled row: champion first, then the field, nothing priced.
 *
 * The ORDER is the board's own — rank 1 is the winner — because that is what
 * makes the decided default the same three lines the chart was drawing the
 * minute before the final was graded.
 */
const DECIDED: TournamentRow[] = [
  row({
    entity_key: "rybakina",
    display_name: "Elena Rybakina",
    rank: 1,
    state: "won",
    probability: null,
    probability_is_live: false,
    trend_hourly: hours("2026-09-06T00:00:00Z", 80, 0.6, 0.004),
  }),
  row({
    entity_key: "sabalenka",
    display_name: "Aryna Sabalenka",
    rank: 2,
    state: "eliminated",
    probability: null,
    probability_is_live: false,
    trend_hourly: hours("2026-09-06T00:00:00Z", 80, 0.3, -0.003),
  }),
  row({
    entity_key: "potapova",
    display_name: "Anastasia Potapova",
    rank: 3,
    state: "eliminated",
    probability: null,
    probability_is_live: false,
    trend_hourly: hours("2026-09-06T00:00:00Z", 80, 0.1, -0.001),
  }),
];

/** The same decided board as PRODUCTION serves it today: no history at all. */
const DECIDED_WITHOUT_HISTORY: TournamentRow[] = DECIDED.map((entry) => ({
  ...entry,
  trend: [],
  trend_hourly: [],
}));

function html(rows: TournamentRow[], selection?: string[]): string {
  return renderToStaticMarkup(
    <ContenderChart
      rows={rows}
      draw="womens-singles"
      selection={selection ?? defaultSelection(rows)}
      onToggle={() => {}}
    />,
  );
}

/** Occurrences of a substring — a count, so an arm can ban as well as require. */
function count(haystack: string, needle: string): number {
  return haystack.split(needle).length - 1;
}

describe("#5934 — a decided draw keeps its chart", () => {
  it("ARM 1: the card renders, with a line per contender, when every row is settled", () => {
    const markup = html(DECIDED);

    // The card itself. Its absence IS the bug: before this ship the component
    // returned null and the reader got 335px of nothing.
    expect(markup).toContain('data-testid="contender-chart"');
    expect(count(markup, 'data-testid="chart-legend-item"')).toBe(3);

    // And the PICTURE, not just the frame: three drawn series with real
    // geometry. A card that mounted with an empty plot would pass the line
    // above and is not the ship.
    expect(count(markup, 'data-testid="chart-series"')).toBe(3);
    expect(count(markup, "<polyline")).toBe(3);
    expect(markup).not.toContain('data-testid="chart-empty"');
  });

  it("ARM 2: the legend prints the RESULT, and never the last reading as a percent", () => {
    const markup = html(DECIDED);

    expect(markup).toContain(">Won<");
    expect(count(markup, ">Out<")).toBe(2);

    // THE BAN. Rybakina's line ends near 92% and Sabalenka's near 6%; if the
    // legend ever reads its number off the series, a percent appears here. The
    // chart's y-axis labels are percents too, so the ban is scoped to the
    // legend's own cells rather than to the whole card.
    const legendCells = markup.match(
      /data-testid="chart-legend-probability"[^>]*>[^<]*/g,
    );
    expect(legendCells).toHaveLength(3);
    for (const cell of legendCells ?? []) {
      expect(cell).not.toMatch(/\d/);
      expect(cell).not.toContain("%");
    }
  });

  it("ARM 3: a live board's default is still the priced three, not a dead man's line", () => {
    // A settled-but-drawable row sitting ABOVE two live ones — the shape a
    // board takes mid-tournament, and the one that would let an eliminated
    // player open the chart if the default simply took the top three of
    // everything chartable.
    const midTournament: TournamentRow[] = [
      row({
        entity_key: "out-early",
        display_name: "Ashlyn Krueger",
        rank: 1,
        state: "eliminated",
        probability: null,
        probability_is_live: false,
        trend_hourly: hours("2026-09-06T00:00:00Z", 40, 0.2, -0.004),
      }),
      row({ entity_key: "a", display_name: "A Player", rank: 2, probability: 0.5 }),
      row({ entity_key: "b", display_name: "B Player", rank: 3, probability: 0.3 }),
      row({ entity_key: "c", display_name: "C Player", rank: 4, probability: 0.2 }),
    ];

    expect(defaultSelection(midTournament)).toEqual(["a", "b", "c"]);
    // It is still ADDABLE — the reader can ask for the completed line.
    expect(chartableRows(midTournament).map((r) => r.entity_key)).toContain("out-early");
  });

  it("ARM 4: the picker labels a settled candidate with the same word as the legend", () => {
    // One line drawn, so the other two sit in the picker.
    const markup = html(DECIDED, ["rybakina"]);

    expect(markup).toContain('data-testid="chart-picker"');
    expect(legendValue(DECIDED[1])).toBe("Out");
    // The picker is collapsed by default, so assert the shared rule directly
    // rather than on a DOM the reader has not opened yet.
    expect(legendValue(DECIDED[0])).toBe("Won");
    expect(legendValue({ probability: 0.42, state: "live" })).toBe("42%");
    // An unknown state falls through to the dash rather than inventing a word.
    expect(legendValue({ probability: null, state: "withdrawn" })).toBe("—");
  });

  it("ARM 5: a settled row with NO history is still not chartable — no empty frame", () => {
    expect(chartableRows(DECIDED_WITHOUT_HISTORY)).toEqual([]);
    expect(defaultSelection(DECIDED_WITHOUT_HISTORY)).toEqual([]);
    expect(html(DECIDED_WITHOUT_HISTORY)).toBe("");
  });
});
