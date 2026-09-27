/**
 * #9003 — one prop, two roundings.
 *
 * `eventGameMarkets.15318878.halfCentPairs.json` is the REAL production
 * `player_props` + `props_script` of `GET /api/events/15318878/game-markets`
 * (Cardinals @ Brewers, live), captured 2026-09-27 01:30Z. Polymarket quotes on
 * a half-cent grid, so Jordan Walker's 1+ HR sits on `.5` at both ends:
 *
 *   Over  0.085 → 0.095      Under (own axis) 0.915 → 0.905
 *
 * THE DIVERGENCE rounds that pair once (`divergencePairPercents` →
 * `renderedOutcomeRowPercents`): "Over 8% → 9%". The rail rounded the Over number
 * alone: "opened 9% · now 10%". The rail now prints the pair the page prints.
 */

import React from "react";
import { renderToStaticMarkup } from "react-dom/server";

import {
  selectDivergenceDetail,
  selectDivergenceRows,
  printedCurrentPoints,
  printedMarkPoints,
  type DivergenceRow,
} from "@/lib/propDivergence";
import type { PlayerPropRow } from "@/lib/playerPropsGrouping";
import {
  isComplementPair,
  renderedOutcomeRowPercents,
  renderedPercent,
} from "@/lib/renderedPercent";
import PropDivergenceRail from "@/components/PropDivergenceRail";

import payload from "../fixtures/eventGameMarkets.15318878.halfCentPairs.json";

type Row = PlayerPropRow & { pregame_mark: number | null; _inverted?: boolean };
type ScriptLeg = { key: string; pregame_mark: number | null; current: number | null };

const ROWS = payload.player_props as unknown as Row[];
const SCRIPT = payload.props_script as unknown as ScriptLeg[];
const WALKER = "Jordan Walker: 1+ home runs";
const BAUERS = "Jake Bauers: 1+ home runs";
const CONTRERAS = "William Contreras: 1+ home runs";

const allRows = (rows: readonly Row[]): DivergenceRow[] => {
  const d = selectDivergenceDetail({ playerProps: rows, status: "live" });
  return [...d.offScript, ...d.onScript, ...d.ungraded];
};
const byLabel = (rows: DivergenceRow[], label: string) => rows.find((r) => r.label === label);
const printed = (row: DivergenceRow | undefined) =>
  row ? [printedMarkPoints(row), printedCurrentPoints(row)] : null;

/**
 * What THE DIVERGENCE prints for a question's Over row, from `props_script`,
 * with `divergencePairPercents`'s own gate: both ends complement ⇒ the pair is
 * rounded once; otherwise the row's own `renderedPercent`.
 */
function divergenceOverPoints(row: DivergenceRow): [number, number] | null {
  const family = SCRIPT.filter(
    (s) =>
      s.key.startsWith(`${row.player}: `) &&
      s.key.toLowerCase().includes(`${row.stat.toLowerCase()} o/u ${row.threshold}|`),
  );
  const over = family.find((s) => s.key.endsWith("|Over"));
  const under = family.find((s) => s.key.endsWith("|Under"));
  if (!over || over.pregame_mark == null || over.current == null) return null;
  if (
    under &&
    under.pregame_mark != null &&
    under.current != null &&
    isComplementPair([over.current, under.current]) &&
    isComplementPair([over.pregame_mark, under.pregame_mark])
  ) {
    const [mark] = renderedOutcomeRowPercents([over.pregame_mark, under.pregame_mark]);
    const [current] = renderedOutcomeRowPercents([over.current, under.current]);
    return [mark as number, current as number];
  }
  return [renderedPercent(over.pregame_mark) as number, renderedPercent(over.current) as number];
}

describe("#9003 — the production specimen", () => {
  it("is an exact complement pair sitting on .5 at both ends", () => {
    const legs = ROWS.filter((r) => r.market_name === "Jordan Walker: Home Runs O/U 0.5");
    expect(legs.map((l) => [l.outcome_name, l._inverted, l.over_probability, l.pregame_mark])).toEqual([
      ["Under", true, 0.095, 0.085],
      ["Over", false, 0.095, 0.085],
    ]);
  });

  it("the rail prints Walker 8% → 9% and Bauers 8% → 9%, as THE DIVERGENCE does", () => {
    const rows = allRows(ROWS);
    expect(printed(byLabel(rows, WALKER))).toEqual([8, 9]);
    expect(printed(byLabel(rows, BAUERS))).toEqual([8, 9]);
  });

  it("EVERY row the rail can show prints THE DIVERGENCE's Over numbers", () => {
    const rows = allRows(ROWS);
    expect(rows.length).toBeGreaterThanOrEqual(5);
    for (const row of rows) {
      expect([row.label, printed(row)]).toEqual([row.label, divergenceOverPoints(row)]);
    }
  });

  it("a question whose legs are NOT a pair keeps its own rounding (Contreras 0.075 → 0.16)", () => {
    // Over 0.16 + Under 0.92 = 1.08: two independent prices, never re-derived.
    expect(printed(byLabel(allRows(ROWS), CONTRERAS))).toEqual([8, 16]);
  });

  it("renders on the rail as 'opened 8%' / 'now 9%', never 'now 10%'", () => {
    const text = renderToStaticMarkup(<PropDivergenceRail playerProps={ROWS} status="live" />)
      .replace(/<[^>]+>/g, " ")
      .replace(/\s+/g, " ");
    const at = text.indexOf(WALKER);
    expect(at).toBeGreaterThanOrEqual(0);
    // Walker's own row: its label up to the next question's label.
    const row = text.slice(at, text.indexOf("Dustin May", at));
    expect(row).toContain("opened 8%");
    expect(row).toContain("now 9%");
    expect(row).not.toContain("now 10%");
  });
});

describe("#9003 — direction follows the printed ends (#8754)", () => {
  const leg = (outcome: "Over" | "Under", over: number, mark: number): Row =>
    ({
      market_name: "Test Player: Home Runs O/U 0.5",
      outcome_name: outcome,
      threshold: 0.5,
      over_probability: over,
      pregame_mark: mark,
      _inverted: outcome === "Under",
      source: "polymarket",
    }) as unknown as Row;

  it("a paired 0.085 → 0.08 prints 8% → 8% and reads flat", () => {
    const row = allRows([leg("Over", 0.08, 0.085), leg("Under", 0.08, 0.085)])[0];
    expect(printed(row)).toEqual([8, 8]);
    expect(row.direction).toBe("flat");
  });

  it("the same Over leg ALONE keeps the contract's own rounding: 9% → 8%, under", () => {
    const row = allRows([leg("Over", 0.08, 0.085)])[0];
    expect(printed(row)).toEqual([9, 8]);
    expect(row.direction).toBe("under");
  });

  it("marks that are not a pair keep BOTH ends unpaired, as THE DIVERGENCE does", () => {
    // Currents complement (0.085 / own 0.915) but marks do not (0.10 / own 0.94),
    // so `divergencePairPercents` pairs neither end: now prints 9, not 8.
    const row = allRows([leg("Over", 0.085, 0.1), leg("Under", 0.085, 0.06)])[0];
    expect(printed(row)).toEqual([10, 9]);
  });

  it("an unpaired row rounds with the contract, not Math.round: 0.565 prints 57", () => {
    // `0.565 * 100` is 56.49999…, so Math.round printed 56 where THE DIVERGENCE's
    // `renderedPercent` prints 57.
    const row = allRows([leg("Over", 0.6, 0.565)])[0];
    expect(printed(row)).toEqual([57, 60]);
  });

  it("a surprising paired row's sentence quotes the bar's own printed ends", () => {
    // Paired: Under 0.715 is the favourite (72), so the Over mark prints 28 —
    // alone it would print 29. Travel 0.28 makes the row surprising.
    const row = allRows([leg("Over", 0.565, 0.285), leg("Under", 0.565, 0.285)])[0];
    expect(printed(row)).toEqual([28, 57]);
    expect(row.sentence).toContain("opened at 28%");
    expect(row.sentence).toContain("57% now");
  });
});

describe("#9003 — the rail's rows are unchanged in membership", () => {
  it("still leads with the same three questions", () => {
    const res = selectDivergenceRows({ playerProps: ROWS, status: "live" });
    expect(res.rows.map((r) => r.label).slice(0, 3)).toEqual([
      "Jackson Chourio: 1+ home runs",
      CONTRERAS,
      WALKER,
    ]);
  });
});
