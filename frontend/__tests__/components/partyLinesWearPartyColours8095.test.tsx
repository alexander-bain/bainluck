/**
 * #8095 — A PARTY LINE WEARS ITS PARTY'S COLOUR.
 *
 * Production, 390px, 2026-09-22 21:5xZ, `/futures/108621` "Which party will win
 * the U.S. House?": the served outcomes sort Republican Party first, the index
 * palette deals blue then red, and the legend read
 *
 *   🔵 Republican Party  🔴 Democratic Party
 *
 * under a red line pinned at 91% — a glance reads Republicans winning, the
 * opposite of the answer. These tests render the chart the page renders and read
 * the colour each legend swatch and each series stroke actually carries.
 */
import { renderToStaticMarkup } from "react-dom/server";
import React from "react";
import { FuturesChart } from "../../components/FuturesChart";
import {
  SERIES_COLORS,
  assignSeriesColors,
  conventionalSeriesColor,
} from "../../lib/seriesColors";
import type { FuturesOutcomeHistory } from "../../lib/types";

const BLUE = SERIES_COLORS[0];
const RED = SERIES_COLORS[1];

function history(field: { name: string; p: number }[]): FuturesOutcomeHistory[] {
  return field.map((o, i) => ({
    outcome_id: i + 1,
    name: o.name,
    history: [
      { timestamp: "2026-09-01T00:00:00Z", probability: o.p },
      { timestamp: "2026-09-22T00:00:00Z", probability: o.p },
    ],
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
  })) as any;
}

/** legend label -> the swatch colour printed beside it. */
function legendColors(html: string): Record<string, string> {
  const out: Record<string, string> = {};
  for (const m of html.matchAll(
    /background-color:(#[0-9a-fA-F]{6})[^>]*><\/span><span[^>]*>([^<]+)<\/span>/g,
  )) {
    out[m[2]] = m[1].toLowerCase();
  }
  return out;
}

function render(field: { name: string; p: number }[]): string {
  const data = history(field);
  return renderToStaticMarkup(
    <FuturesChart
      historyData={data}
      selectedOutcomes={new Set(data.map((o) => o.outcome_id))}
      onToggleOutcome={() => {}}
      fixedYAxis
      fieldCeiling
      marketName="Which party will win the U.S. House?"
    />,
  );
}

/** The specimen, in the order production served it. */
const HOUSE = [
  { name: "Republican Party", p: 0.09 },
  { name: "Democratic Party", p: 0.91 },
];

describe("#8095 the House chart", () => {
  it("draws Democrats blue and Republicans red whatever order they arrive in", () => {
    const colors = legendColors(render(HOUSE));
    expect(colors["Democratic Party"]).toBe(BLUE);
    expect(colors["Republican Party"]).toBe(RED);

    const reversed = legendColors(render([...HOUSE].reverse()));
    expect(reversed["Democratic Party"]).toBe(BLUE);
    expect(reversed["Republican Party"]).toBe(RED);
  });

  it("paints the lines in the same colours as their legend swatches", () => {
    const html = render(HOUSE);
    const strokes = [...html.matchAll(/stroke="(#[0-9a-fA-F]{6})"/g)].map((m) =>
      m[1].toLowerCase(),
    );
    expect(strokes).toContain(BLUE);
    expect(strokes).toContain(RED);
    // The pre-fix order: the FIRST series stroke is Republican's, and it was blue.
    expect(strokes.find((s) => s === BLUE || s === RED)).toBe(RED);
  });

  it("leaves a field with no party line exactly on the index palette", () => {
    const field = [
      { name: "Denny Hamlin", p: 0.3 },
      { name: "Kyle Larson", p: 0.25 },
      { name: "William Byron", p: 0.2 },
    ];
    const colors = legendColors(render(field));
    field.forEach((o, i) => expect(colors[o.name]).toBe(SERIES_COLORS[i]));
  });
});

describe("#8095 conventionalSeriesColor matches the whole party label only", () => {
  it.each([
    ["Democratic Party", BLUE],
    ["Democrats", BLUE],
    ["democratic", BLUE],
    ["The Democratic Party", BLUE],
    ["Republican Party", RED],
    ["Republicans", RED],
    ["GOP", RED],
  ])("%s -> party colour", (name, color) => {
    expect(conventionalSeriesColor(name)).toBe(color);
  });

  it.each([
    "Democrats, 5+ pts",
    "Republicans, 2+ pts",
    "Liberal Democratic Party",
    "Social Democratic Party",
    "Democratic Republic of the Congo",
    "Kamala Harris",
  ])("%s -> no convention", (name) => {
    expect(conventionalSeriesColor(name)).toBeNull();
  });
});

describe("#8095 assignSeriesColors", () => {
  it("never gives a third line the blue or red a party already holds", () => {
    const colors = assignSeriesColors(
      ["Independent", "Republican Party", "Democratic Party", "Libertarian"],
      SERIES_COLORS,
    );
    expect(colors[1]).toBe(RED);
    expect(colors[2]).toBe(BLUE);
    expect(colors[0]).not.toBe(BLUE);
    expect(colors[0]).not.toBe(RED);
    expect(colors[3]).not.toBe(BLUE);
    expect(colors[3]).not.toBe(RED);
    expect(new Set(colors).size).toBe(4);
  });

  it("is the plain index palette when no label carries a convention", () => {
    const names = Array.from({ length: 12 }, (_, i) => `Golfer ${i}`);
    expect(assignSeriesColors(names, SERIES_COLORS)).toEqual(
      names.map((_, i) => SERIES_COLORS[i % SERIES_COLORS.length]),
    );
  });
});
