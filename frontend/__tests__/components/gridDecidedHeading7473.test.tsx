/**
 * #7473 — A FINISHED DRAW'S GRID WAS STILL HEADED "CHANCE OF REACHING".
 *
 * Alex, /tournaments/us-open at 390px on 2026-09-20, seven days after the
 * final. The page does settled well everywhere else — "This draw is done",
 * "Settled. Alexander Zverev won the title.", Won/Out on the board — and then
 * the grid two-thirds down reads:
 *
 *     CHANCE OF REACHING · Men's Singles
 *
 * over a table in which every cell on the first screen is a grey ✓ or a `—`.
 * `GRID_SECTION_LABEL` was a bare constant interpolated with no condition, so
 * the heading read identically on ceremony day and a week after the trophy.
 *
 * ═══ WHY THE NEGATIVE CONTROL IS THE LOAD-BEARING TEST HERE ═══
 *
 * The cheapest wrong fix is to re-word the constant, which would make every
 * "the heading says the past tense" assertion pass while breaking the live
 * tournament this page exists for. So the two payloads are asserted TOGETHER
 * and both are real production captures of the same slug:
 *
 *   payload-2026-08-27.json          mid-tournament, nobody has won  ⇒ forecast
 *   payload-decided-2026-09-20.json  a week past the final           ⇒ result
 *
 * Neither is hand-built. A fabricated grid is exactly the specimen that makes
 * a state-reading predicate return its "I could not tell" branch and look
 * principled doing it.
 *
 * ═══ AND THE OVER-CLAIM CONTROL ═══
 *
 * The grid is NOT 100% settled on a decided draw — on the day this was filed
 * the men's table still carried 31 numbers (`stale`/`dark`, first at row 29).
 * "The table has no probabilities in it" would be the same defect pointing the
 * other way, so `still prints the numbers it still has` pins that the change
 * is four words above the table and nothing inside it.
 */

import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import fs from "node:fs";
import path from "node:path";

import PlayoffGrid from "@/components/tournament/PlayoffGrid";
import {
  GRID_SECTION_LABEL,
  GRID_SECTION_LABEL_DECIDED,
  gridIsDecided,
  readPlayoffGrid,
  type GridCell,
  type PlayoffGrid as GridModel,
  type PlayoffGridPayload,
} from "@/lib/playoffGrid";

const MOCKS = path.join(__dirname, "..", "..", "..", "docs", "mocks", "us-open");

function loadGrid(file: string, draw: string): GridModel {
  const payload = JSON.parse(fs.readFileSync(path.join(MOCKS, file), "utf8")) as {
    grids?: Record<string, PlayoffGridPayload>;
  };
  const grid = readPlayoffGrid(payload.grids?.[draw]);
  if (!grid) throw new Error(`${file} has no ${draw} grid — the fixture moved`);
  return grid;
}

const LIVE = "payload-2026-08-27.json";
const DECIDED = "payload-decided-2026-09-20.json";
const DRAWS = ["mens-singles", "womens-singles"] as const;

/** Deep-enough copy that a test mutating one cell cannot leak into the next. */
function clone(grid: GridModel): GridModel {
  return JSON.parse(JSON.stringify(grid)) as GridModel;
}

/** The cell that decides the draw, by `kind` — the row with the trophy. */
function titleKey(grid: GridModel): string {
  const column = grid.columns.find((c) => c.kind === "title");
  if (!column) throw new Error("fixture has no title column");
  return column.key;
}

function winningCell(grid: GridModel): GridCell {
  const key = titleKey(grid);
  const row = grid.rows.find((r) => r.cells?.[key]?.note === "won");
  if (!row) throw new Error("fixture has no winning title cell");
  return row.cells[key];
}

describe("#7473 — the grid heading follows the draw", () => {
  describe("a decided draw is headed as a result", () => {
    it.each(DRAWS)("%s says so in the h2", (draw) => {
      const html = renderToStaticMarkup(<PlayoffGrid grid={loadGrid(DECIDED, draw)} />);

      expect(html).toContain(GRID_SECTION_LABEL_DECIDED);
      expect(html).not.toContain(GRID_SECTION_LABEL);
    });

    it.each(DRAWS)("%s carries data-decided for probes", (draw) => {
      const html = renderToStaticMarkup(<PlayoffGrid grid={loadGrid(DECIDED, draw)} />);

      expect(html).toContain('data-decided="true"');
    });

    it("keeps the draw label beside the new heading", () => {
      const html = renderToStaticMarkup(
        <PlayoffGrid grid={loadGrid(DECIDED, "mens-singles")} drawLabel="Men's Singles" />
      );

      expect(html).toContain(GRID_SECTION_LABEL_DECIDED);
      expect(html).toContain("Men&#x27;s Singles");
    });

    it("still prints the numbers it still has", () => {
      // The over-claim control. 31 men's cells were `stale`/`dark` a week after
      // the final and every one still shows its own quote; the heading moved,
      // the table did not.
      const grid = loadGrid(DECIDED, "mens-singles");
      const numeric = grid.rows.flatMap((row) =>
        Object.values(row.cells ?? {}).filter(
          (cell) => typeof cell.probability === "number" && Number.isFinite(cell.probability)
        )
      );
      expect(numeric.length).toBeGreaterThan(0);

      const html = renderToStaticMarkup(<PlayoffGrid grid={grid} initialExpanded />);
      expect(html).toMatch(/>\d+%</);
    });
  });

  describe("a live draw is still headed as a forecast", () => {
    it.each(DRAWS)("%s keeps the forecast heading", (draw) => {
      const html = renderToStaticMarkup(<PlayoffGrid grid={loadGrid(LIVE, draw)} />);

      expect(html).toContain(GRID_SECTION_LABEL);
      expect(html).not.toContain(GRID_SECTION_LABEL_DECIDED);
      expect(html).toContain('data-decided="false"');
    });

    it("the two fixtures actually disagree", () => {
      // Without this the pair above could both be describing the same state and
      // the suite would pass on a constant rename.
      expect(gridIsDecided(loadGrid(LIVE, "mens-singles"))).toBe(false);
      expect(gridIsDecided(loadGrid(DECIDED, "mens-singles"))).toBe(true);
    });
  });

  describe("gridIsDecided reads the winning title cell and nothing else", () => {
    it("a settled title column with no winner is not decided", () => {
      const grid = clone(loadGrid(DECIDED, "mens-singles"));
      const key = titleKey(grid);
      for (const row of grid.rows) {
        const cell = row.cells?.[key];
        if (cell?.note === "won") cell.note = "out";
      }

      expect(gridIsDecided(grid)).toBe(false);
      expect(renderToStaticMarkup(<PlayoffGrid grid={grid} />)).toContain(GRID_SECTION_LABEL);
    });

    it("a winner noted on an unsettled cell is not decided", () => {
      // A title cell still quoting a live number has not finished, whatever
      // note rides along with it — the two halves are read together.
      const grid = clone(loadGrid(DECIDED, "mens-singles"));
      winningCell(grid).state = "live";

      expect(gridIsDecided(grid)).toBe(false);
    });

    it("a reach column's ✓ never decides the draw", () => {
      // Every finalist's F cell is `settled` and the champion's is noted `won`
      // only in the TITLE column. A predicate that swept all columns would call
      // the draw decided the moment the first player reached a round.
      const grid = clone(loadGrid(DECIDED, "mens-singles"));
      const key = titleKey(grid);
      // Nobody has lifted the trophy in this table — but every R16/QF/SF/F ✓ in
      // it now claims the strongest note a cell can carry. The title column is
      // still declared, so this is not the no-title-column arm.
      for (const row of grid.rows) delete row.cells[key];
      for (const row of grid.rows) {
        for (const cell of Object.values(row.cells ?? {})) {
          if (cell.state === "settled") cell.note = "won";
        }
      }
      expect(grid.columns.some((c) => c.kind === "title")).toBe(true);

      expect(gridIsDecided(grid)).toBe(false);
      expect(renderToStaticMarkup(<PlayoffGrid grid={grid} />)).toContain(GRID_SECTION_LABEL);
    });

    it("finds the title column by kind, not by the key 'title'", () => {
      const grid = clone(loadGrid(DECIDED, "mens-singles"));
      const key = titleKey(grid);
      grid.columns = grid.columns.map((c) => (c.kind === "title" ? { ...c, key: "champion" } : c));
      for (const row of grid.rows) {
        if (row.cells?.[key]) {
          row.cells.champion = row.cells[key];
          delete row.cells[key];
        }
      }

      expect(gridIsDecided(grid)).toBe(true);
    });

    it("a grid with no title column is never decided", () => {
      const grid = clone(loadGrid(DECIDED, "mens-singles"));
      grid.columns = grid.columns.filter((c) => c.kind !== "title");

      expect(gridIsDecided(grid)).toBe(false);
      expect(renderToStaticMarkup(<PlayoffGrid grid={grid} />)).toContain(GRID_SECTION_LABEL);
    });
  });

  describe("the two headings are different sentences", () => {
    it("neither is the other, and neither speaks in our words", () => {
      expect(GRID_SECTION_LABEL_DECIDED).not.toBe(GRID_SECTION_LABEL);
      for (const label of [GRID_SECTION_LABEL, GRID_SECTION_LABEL_DECIDED]) {
        expect(label).not.toMatch(/price|settle|market|cell|state/i);
      }
    });
  });
});
