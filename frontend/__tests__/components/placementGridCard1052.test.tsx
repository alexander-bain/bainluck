/**
 * UX-1052 item 3 — the five golf cards become one grid, on screen.
 *
 * Alex, shopping /sports on 2026-09-03: "Five near-identical golf cards for one
 * tournament (Omega European Masters: Top 5 / Top 10 / Top 20 / Make the Cut /
 * Winner) … group them into a beautiful grid. One card per tournament: players
 * down, markets across."
 *
 * The grouping is proved in `backend/tests/test_placement_grid_1052.py`. This
 * file proves the strip DRAWS it — a payload change with no renderer arm would
 * have made every one of those five markets vanish instead of merge, because
 * the backend now consumes them out of the ungrouped list.
 *
 * It also pins the two things that make the grid honest rather than merely
 * compact: an unpriced cell prints "—" (never a borrowed neighbour), and a card
 * showing a slice of a deep field says how deep the field is.
 */

import React from "react";
import { renderToStaticMarkup } from "react-dom/server";

jest.mock("next/link", () => {
  const ReactLib = require("react");
  return {
    __esModule: true,
    default: ({ href, children, ...props }: { href: string; children: React.ReactNode }) =>
      ReactLib.createElement("a", { href, ...props }, children),
  };
});

import GroupedFeedRenderer from "@/components/GroupedFeedRenderer";
import { admittedPropStripRows } from "@/lib/sports/propStripAdmission";
import type { GroupedFeedItem, PlacementGridFeedItem } from "@/lib/types";

const OMEGA: PlacementGridFeedItem = {
  type: "placement_grid",
  group_key: "placement:omega european masters",
  title: "Omega European Masters",
  market_count: 5,
  sources: ["datagolf"],
  row_total: 132,
  columns: [
    { key: "winner", label: "Winner" },
    { key: "top_5", label: "Top 5" },
    { key: "top_10", label: "Top 10" },
    { key: "top_20", label: "Top 20" },
    { key: "make_cut", label: "Make cut" },
  ],
  rows: [
    { name: "Angel Ayora", values: { winner: 0.12, top_5: 0.38, top_10: 0.55, top_20: 0.74, make_cut: 0.91 } },
    { name: "Eugenio Chacarra", values: { winner: 0.09, top_5: 0.31, top_10: 0.48, top_20: 0.7, make_cut: 0.88 } },
    // A golfer with no outright book — the "—" case.
    { name: "Marco Penge", values: { winner: null, top_5: 0.24, top_10: 0.4, top_20: 0.62, make_cut: 0.83 } },
  ],
};

function render(items: GroupedFeedItem[]) {
  return renderToStaticMarkup(<GroupedFeedRenderer items={items} compact />);
}

describe("UX-1052 item 3 — the placement grid renders", () => {
  it("names the tournament once, not five times", () => {
    const html = render([OMEGA]);
    expect(html.split("Omega European Masters").length - 1).toBe(1);
  });

  it("puts the markets across the top", () => {
    const html = render([OMEGA]);
    for (const label of ["Winner", "Top 5", "Top 10", "Top 20", "Make cut"]) {
      expect(html).toContain(label);
    }
    // In reading order, left to right.
    expect(html.indexOf("Top 5")).toBeLessThan(html.indexOf("Top 10"));
    expect(html.indexOf("Top 10")).toBeLessThan(html.indexOf("Top 20"));
  });

  it("puts the players down the side with their numbers", () => {
    const html = render([OMEGA]);
    expect(html).toContain("Angel Ayora");
    expect(html).toContain("Eugenio Chacarra");
    expect(html).toContain("12%");
    expect(html).toContain("91%");
  });

  it("prints an em dash for an unpriced cell rather than borrowing a number", () => {
    const html = render([OMEGA]);
    expect(html).toContain("—");
    // Penge has no outright price; 24% (his Top 5) must not stand in for it.
    // Assert on the row, not the document, so an unrelated 24% cannot pass it.
    const row = html.slice(html.indexOf("Marco Penge"));
    const firstCell = row.slice(0, row.indexOf("24%"));
    expect(firstCell).toContain("—");
  });

  it("says how deep the real field is when it shows a slice", () => {
    expect(render([OMEGA])).toContain("3 of 132 players");
  });

  it("says nothing about depth when the card shows the whole field", () => {
    const whole = { ...OMEGA, row_total: 3 };
    expect(render([whole])).not.toContain("of 3 players");
  });
});

describe("UX-1052 item 3 — admission", () => {
  it("admits a grid that carries a number", () => {
    expect(admittedPropStripRows([OMEGA])).toHaveLength(1);
  });

  it("refuses a grid whose every cell is empty", () => {
    const blank: PlacementGridFeedItem = {
      ...OMEGA,
      rows: OMEGA.rows.map((r) => ({
        name: r.name,
        values: Object.fromEntries(Object.keys(r.values).map((k) => [k, null])),
      })),
    };
    expect(admittedPropStripRows([blank])).toEqual([]);
    expect(render([blank])).not.toContain("Omega European Masters");
  });

  it("refuses a grid with no columns", () => {
    expect(admittedPropStripRows([{ ...OMEGA, columns: [] }])).toEqual([]);
  });
});
