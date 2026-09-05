/**
 * #3163 — A ROUND BAND GROUPS A RUN, NOT A ROW.
 *
 * Found in a phone-width LOOK of `/tournaments/us-open` on 2026-09-05
 * (live/072, under D48). The FINISHED list read:
 *
 *     ROUND OF 32
 *       Ben Shelton      78% BOOKS   7-6, 6-7, 6-3, 6-4
 *     ROUND OF 32
 *       Frances Tiafoe   64% BOOKS   6-4, 6-2, 6-4
 *     ROUND OF 32
 *       Alex Michelsen   63% BOOKS   7-6, 6-4, 6-3
 *     ROUND OF 32
 *       Tomas Martin …   55% BOOKS   6-4, 6-4, 6-3
 *
 * The band was emitted once per ROW. A heading that appears above every member
 * of a group is not a heading — it groups nothing, it is read as noise, and on
 * a phone it costs a whole band of vertical space per match on a list that is
 * 138 matches long.
 *
 * ── THE GUARD IS OVER REAL BYTES, AND IT IS A RELATION ───────────────────────
 *
 * `tournamentHubUsOpen.20260901.json` is production's own payload (see
 * `tournamentResultsLiveProof.test.tsx` for its provenance — it is unedited in
 * the two keys under test). The assertions below are written as RELATIONS over
 * whatever that fixture holds, not as hard counts, so a refreshed capture with
 * a different round distribution keeps them meaningful:
 *
 *   - no two ADJACENT bands ever carry the same text;
 *   - there is exactly one band per RUN of equal headings;
 *   - every rendered row still sits under a band (none was orphaned).
 *
 * The last of those is the one that matters most and is easiest to lose: a
 * "dedupe" that compared against the wrong neighbour, or that suppressed the
 * band at index 0, would satisfy the first two and leave the top of the list
 * headless.
 *
 * ── WHY IT CANNOT PASS ON A NO-OP ────────────────────────────────────────────
 *
 * The fixture's men's draw contains real runs — the shipped defect emitted one
 * band per row, so `bands.length === rows.length` and adjacent duplicates were
 * everywhere. `bands.length < rows.length` is asserted directly, which the
 * pre-fix component cannot satisfy on this payload.
 */

import React from "react";
import { renderToStaticMarkup } from "react-dom/server";

import TournamentResults from "@/components/tournament/TournamentResults";
import {
  resultsForDraw,
  roundHeading,
  sortedResults,
  type TournamentResults as ResultsModel,
} from "@/lib/tournamentResults";

import LIVE from "../fixtures/tournamentHubUsOpen.20260901.json";

const RESULTS = LIVE.results as unknown as ResultsModel;

function render(draw: string): string {
  return renderToStaticMarkup(
    <TournamentResults results={RESULTS} draw={draw} initialExpanded />
  );
}

/** The band texts, in document order. */
function bands(html: string): string[] {
  return Array.from(
    html.matchAll(/data-testid="result-round"[^>]*>([^<]*)</g)
  ).map((m) => m[1].trim());
}

function rowCount(html: string): number {
  return html.split('data-testid="result-row"').length - 1;
}

/** One band per run of equal headings — what the list SHOULD contain. */
function expectedBands(draw: string): string[] {
  const ordered = sortedResults(resultsForDraw(RESULTS, draw));
  const out: string[] = [];
  for (const result of ordered) {
    const heading = roundHeading(result);
    if (out.length === 0 || out[out.length - 1] !== heading) out.push(heading);
  }
  return out;
}

describe("#3163 — the FINISHED list's round band", () => {
  /** The control for everything below: a trimmed fixture would make the
   *  defect and the fix agree, because a one-row draw has no run to collapse. */
  it("the fixture actually contains runs to collapse", () => {
    const ordered = sortedResults(resultsForDraw(RESULTS, "mens-singles"));
    expect(ordered.length).toBeGreaterThan(50);
    expect(expectedBands("mens-singles").length).toBeLessThan(ordered.length);
  });

  it("draws one band per run, not one per row", () => {
    const html = render("mens-singles");
    const drawn = bands(html);

    // The shipped defect: one band per row. This is the assertion it fails.
    expect(drawn.length).toBeLessThan(rowCount(html));
    expect(drawn).toEqual(expectedBands("mens-singles"));
  });

  it("never repeats a band back to back", () => {
    for (const draw of ["mens-singles", "womens-singles"]) {
      const drawn = bands(render(draw));
      for (let i = 1; i < drawn.length; i += 1) {
        expect(drawn[i]).not.toBe(drawn[i - 1]);
      }
    }
  });

  /**
   * THE ORPHAN ARM. A dedupe that compared against the wrong neighbour, or that
   * dropped the band at index 0, passes both assertions above and leaves the
   * top of the list with no heading at all.
   */
  it("still opens with a band, and never leaves a row unheaded", () => {
    for (const draw of ["mens-singles", "womens-singles"]) {
      const html = render(draw);
      if (rowCount(html) === 0) continue;

      // The first thing inside the list is a band, not a row.
      const firstBand = html.indexOf('data-testid="result-round"');
      const firstRow = html.indexOf('data-testid="result-row"');
      expect(firstBand).toBeGreaterThan(-1);
      expect(firstBand).toBeLessThan(firstRow);

      // And the bands, in order, are exactly the runs the data has.
      expect(bands(html)).toEqual(expectedBands(draw));
      expect(bands(html).length).toBeGreaterThan(0);
    }
  });

  /**
   * THE COLLAPSED LIST. The page ships collapsed to five rows, and the slice is
   * where an off-by-one hides: its first row starts a run whatever preceded it
   * in the full array, so it must carry a band even though the row before it in
   * the DATA had the same heading.
   */
  it("opens the COLLAPSED list with a band too", () => {
    const html = renderToStaticMarkup(
      <TournamentResults results={RESULTS} draw="mens-singles" />
    );
    const drawn = bands(html);
    expect(drawn.length).toBeGreaterThan(0);
    expect(drawn.length).toBeLessThanOrEqual(rowCount(html));
    const firstBand = html.indexOf('data-testid="result-round"');
    const firstRow = html.indexOf('data-testid="result-row"');
    expect(firstBand).toBeLessThan(firstRow);
  });
});
