/**
 * ux/1034 A1 — THE CONTENDER CHART OPENS ON THE TOURNAMENT.
 *
 * Alex, on the live US Open hub at 3:30pm on day four:
 *
 *   > I'm a LOT more interested in how the Contender chart has looked …
 *   > since the tournament started than since August 5th.
 *
 * He was reading `ALL`, which is what the chart had always opened on. On the
 * men's board `ALL` is the 30 days from 4 August: twenty-six days of
 * pre-tournament drift, then the four days of actual play squeezed into the
 * right-hand sixth of the plot.
 *
 * ## Why the four buttons could not already do this
 *
 * `1W` is seven days back **from the latest reading**, which today lands two
 * days before the main draw and next Tuesday will land two days after it. It is
 * a rolling window; what Alex asked for is a window with a MEANING. So the
 * range selector gains two chips that are dates rather than durations — `Draw`
 * (the main draw) and `Quals` (five days earlier) — and `Draw` is the default.
 *
 * ## What each test here is holding shut
 *
 * - `opens on the main draw` is the ship, stated on the live payload.
 * - `does not draw the month before the tournament` is the same claim from the
 *   other side, and it is the one a well-meaning "just add a chip" change would
 *   break: adding the option without moving the default leaves Alex exactly
 *   where he was.
 * - `reads the start off the payload` is the NEVER-A-CONSTANT guard. `30
 *   August` is a fact about one tournament in one year, and a literal would be
 *   wrong for the Australian Open and silently wrong next September — the
 *   chart would still draw, just from the wrong day. The test moves the
 *   payload's date and requires the window to follow.
 * - `falls back` is the control: a payload that cannot date either window
 *   renders the four buttons it always had, opening on `ALL`. Without this the
 *   suite could not tell "the default moved" from "the default is now DRAW
 *   unconditionally", and the second would blank the chart on the morning of
 *   day one, before there are two readings to join.
 */

import React from "react";
import { renderToStaticMarkup } from "react-dom/server";

import ContenderChart from "@/components/tournament/ContenderChart";
import {
  chartRanges,
  chartSeriesFor,
  defaultChartRange,
  rangeIsDrawable,
  seriesForRange,
  type WindowStarts,
} from "@/lib/contenderChart";
import { tournamentWindowStarts } from "@/lib/tournamentWindows";
import type { TournamentPayload, TournamentRow } from "@/lib/tournament";

import hub from "../fixtures/tournamentHubUsOpen.20260903.json";

/** The banked production payload — see its own `_provenance` field. */
const PAYLOAD = hub as unknown as TournamentPayload;

const MENS = PAYLOAD.boards.find((board) => board.draw === "mens-singles")!;
const WOMENS = PAYLOAD.boards.find((board) => board.draw === "womens-singles")!;

/** The chart's own default selection is the board's top three, which is all the
 *  fixture carries — so the series list is the whole board. */
function seriesFor(rows: TournamentRow[]) {
  return chartSeriesFor(
    rows,
    rows.map((row) => row.entity_key)
  );
}

function render(rows: TournamentRow[], windowStarts: WindowStarts) {
  return renderToStaticMarkup(
    <ContenderChart
      rows={rows}
      draw="mens-singles"
      selection={rows.map((row) => row.entity_key)}
      onToggle={() => {}}
      windowStarts={windowStarts}
    />
  );
}

/** Every date the plot's axis is built from, in order. */
function drawnDates(rows: TournamentRow[], windowStarts: WindowStarts): string[] {
  const range = defaultChartRange(seriesFor(rows), windowStarts);
  const drawn = seriesForRange(seriesFor(rows), range, windowStarts);
  return Array.from(new Set(drawn.flatMap((entry) => entry.points.map((p) => p.date)))).sort();
}

describe("ux/1034 A1 — the window the contender chart opens on", () => {
  it("reads both starts off the live payload", () => {
    const starts = tournamentWindowStarts(PAYLOAD);

    // The main draw is PUBLISHED — `main_draw_starts_at`, the same value the
    // empty-slate hint prints as "Sunday 30 August".
    expect(starts.DRAW).toBe("2026-08-30");
    // Qualifying is OBSERVED — the earliest day a qualifying match finished.
    // Nothing in the payload names it, and "five days before the draw" would be
    // a fact about this tournament wearing the shape of a rule.
    expect(starts.QUAL).toBe("2026-08-25");
  });

  /**
   * THE NEVER-A-CONSTANT GUARD. A literal `2026-08-30` would pass every other
   * test in this file and be wrong in January.
   */
  it("reads the start off the payload rather than from a constant", () => {
    const moved = {
      ...PAYLOAD,
      main_draw_starts_at: "2027-01-12T11:00:00+11:00",
    } as TournamentPayload;

    expect(tournamentWindowStarts(moved).DRAW).toBe("2027-01-12");

    // And with no published start there is no chip to press — an option that
    // cannot be honoured is worse than an absent one.
    const undated = { ...PAYLOAD, main_draw_starts_at: undefined } as TournamentPayload;
    expect(tournamentWindowStarts(undated).DRAW).toBeNull();
    expect(chartRanges(tournamentWindowStarts(undated))).not.toContain("DRAW");
  });

  it("opens on the main draw on both boards", () => {
    const starts = tournamentWindowStarts(PAYLOAD);

    expect(defaultChartRange(seriesFor(MENS.rows), starts)).toBe("DRAW");
    expect(defaultChartRange(seriesFor(WOMENS.rows), starts)).toBe("DRAW");

    const html = render(MENS.rows, starts);
    expect(html).toContain('data-range="DRAW"');
    // The chip is pressed, and it says what it is for a reader who cannot
    // decode `Draw` from four characters.
    expect(html).toContain('data-option="DRAW" data-active="true"');
    expect(html).toContain("Since the main draw began, 30 August");
    expect(html).toContain("Since qualifying began, 25 August");
  });

  /**
   * THE SAME CLAIM FROM THE OTHER SIDE. Adding the chips without moving the
   * default would leave Alex looking at 4 August, and every assertion above
   * would still pass on a `ranges.includes` reading.
   */
  it("does not draw the month before the tournament", () => {
    const starts = tournamentWindowStarts(PAYLOAD);
    const dates = drawnDates(MENS.rows, starts);

    expect(dates.length).toBeGreaterThanOrEqual(2);
    expect(dates[0]).toBe("2026-08-30");
    // 4 August is on this board and is what he was shown. It is not drawn now.
    expect(seriesFor(MENS.rows)[0].points[0].date).toBe("2026-08-04");
    expect(dates).not.toContain("2026-08-04");

    // Quals is the wider of the two windows and still narrower than ALL.
    const qual = seriesForRange(seriesFor(MENS.rows), "QUAL", starts);
    const qualDates = Array.from(
      new Set(qual.flatMap((entry) => entry.points.map((p) => p.date)))
    ).sort();
    expect(qualDates[0]).toBe("2026-08-26");
    expect(qualDates.length).toBeGreaterThan(dates.length);
    expect(qualDates.length).toBeLessThan(seriesFor(MENS.rows)[0].points.length);
  });

  /**
   * THE CONTROL, and the reason `DRAW` has to EARN the default. On the morning
   * of day one the window holds one reading, which is not a line — the chart
   * must fall back rather than open blank.
   */
  it("falls back to ALL when the tournament window cannot be drawn", () => {
    const noStarts: WindowStarts = { DRAW: null, QUAL: null };
    expect(chartRanges(noStarts)).toEqual(["1D", "1W", "1M", "ALL"]);
    expect(defaultChartRange(seriesFor(MENS.rows), noStarts)).toBe("ALL");
    expect(render(MENS.rows, noStarts)).toContain('data-range="ALL"');

    // A dated window with a single reading in it: offered, disabled, not the
    // default. `2026-09-03` is the last day the fixture carries.
    const dayOne: WindowStarts = { DRAW: "2026-09-03", QUAL: null };
    expect(rangeIsDrawable(seriesFor(MENS.rows), "DRAW", dayOne)).toBe(false);
    expect(defaultChartRange(seriesFor(MENS.rows), dayOne)).toBe("ALL");
  });

  /**
   * Two chips that draw the same window are one chip and a puzzle. This also
   * catches a payload whose qualifying rows were misdated into the main draw,
   * which is the case where offering `Quals` would quietly redraw the window
   * the reader thinks they chose.
   */
  it("does not offer Quals when it is not earlier than the draw", () => {
    const noQualifying = {
      ...PAYLOAD,
      results: { ...PAYLOAD.results, matches: [] },
    } as unknown as TournamentPayload;
    expect(tournamentWindowStarts(noQualifying).QUAL).toBeNull();
    expect(chartRanges(tournamentWindowStarts(noQualifying))).not.toContain("QUAL");

    const misdated = {
      ...PAYLOAD,
      main_draw_starts_at: "2026-08-20T11:00:00-04:00",
    } as TournamentPayload;
    expect(tournamentWindowStarts(misdated).DRAW).toBe("2026-08-20");
    expect(tournamentWindowStarts(misdated).QUAL).toBeNull();
  });

  /** The four durations are untouched — the instruction was to add, not replace. */
  it("keeps 1D/1W/1M/ALL", () => {
    const starts = tournamentWindowStarts(PAYLOAD);
    expect(chartRanges(starts)).toEqual(["DRAW", "QUAL", "1D", "1W", "1M", "ALL"]);

    const html = render(MENS.rows, starts);
    for (const option of ["1D", "1W", "1M", "ALL"]) {
      expect(html).toContain(`data-option="${option}"`);
    }
  });
});
