/**
 * #8313 — the props rail led with "Riley Greene's 1+ home runs was marked 94% —
 * and it missed".
 *
 * `eventPlayerProps.15317535.conflictingLegs.json` is the REAL production
 * `player_props` array of `GET /api/events/15317535/game-markets` (Nationals 4 –
 * Tigers 2, Final), captured 2026-09-24 ~00:30Z. Polymarket's
 * "Riley Greene: Home Runs O/U 0.5" has two legs, and they disagree about where
 * the question opened:
 *
 *   Under  pregame_mark 0.935  (_inverted: the Under leg was stored with the
 *                               Over's 0.065 opening price, and the route
 *                               correctly inverted what it was given)
 *   Over   pregame_mark 0.065
 *
 * The rail built its one row from whichever leg came first in the payload — the
 * Under — so it graded a 6.5% longshot as a 94% miss and, because that reads as
 * an 84-point surprise, put it at the top.
 *
 * The data half (the Polymarket ingest) is a separate fix. This file guards the
 * rail half: a question whose legs contradict each other on the mark is
 * withheld, whatever order they arrive in.
 */

import {
  selectDivergenceDetail,
  selectDivergenceRows,
  isBenignDrop,
  PROP_DROP_REASON_LABEL,
  PROP_LEG_DISAGREEMENT,
} from "@/lib/propDivergence";
import type { PlayerPropRow } from "@/lib/playerPropsGrouping";

import payload from "../fixtures/eventPlayerProps.15317535.conflictingLegs.json";

type Row = PlayerPropRow & { pregame_mark: number };

const ROWS = payload as unknown as Row[];
const GREENE = "Riley Greene: Home Runs O/U 0.5";
const isGreene = (r: Row) => r.market_name === GREENE;

const settled = (rows: readonly Row[]) =>
  selectDivergenceRows({ playerProps: rows, status: "completed" });

describe("#8313 — the production specimen", () => {
  it("is two legs of one question that disagree by 0.87, Under first", () => {
    const legs = ROWS.filter(isGreene);
    expect(legs.map((l) => l.outcome_name)).toEqual(["Under", "Over"]);
    expect(legs.map((l) => l.pregame_mark)).toEqual([0.935, 0.065]);
  });

  it("no longer puts Greene on the rail, and says one row was held back", () => {
    const res = settled(ROWS);
    expect(res.rows.some((r) => r.player === "Riley Greene")).toBe(false);

    const drop = res.dropped.find((d) => d.reason === "conflicting_legs");
    expect(drop?.count).toBe(1);
    expect(drop?.examples).toEqual([GREENE]);
    expect(drop?.benign).toBe(false);
    expect(res.nonBenignCount).toBeGreaterThanOrEqual(1);
  });

  it("still ranks the rest of the game (gotcha #43, the other direction)", () => {
    const res = settled(ROWS);
    expect(res.rows.length).toBeGreaterThan(0);
    // Torkelson's legs sit 0.07 apart on the same page: under the line, kept.
    const before = ROWS.filter((r) => r.market_name?.startsWith("Spencer Torkelson: Home Runs O/U 0.5"));
    expect(Math.abs(before[0].pregame_mark - before[1].pregame_mark)).toBeCloseTo(0.07, 5);
    const detail = selectDivergenceDetail({ playerProps: ROWS, status: "completed" });
    const all = [...detail.offScript, ...detail.onScript, ...detail.ungraded];
    expect(all.some((r) => r.label === "Spencer Torkelson: 1+ home runs")).toBe(true);
  });

  it("gives the same answer whichever leg arrives first — the coin flip is gone", () => {
    const flipped = [...ROWS.filter((r) => !isGreene(r)), ...ROWS.filter(isGreene).reverse()];
    for (const rows of [ROWS, flipped]) {
      const res = settled(rows);
      expect(res.rows.some((r) => r.player === "Riley Greene")).toBe(false);
      expect(res.dropped.find((d) => d.reason === "conflicting_legs")?.count).toBe(1);
    }
  });

  it("is withheld by the detail view too — one admission rule", () => {
    const detail = selectDivergenceDetail({ playerProps: ROWS, status: "completed" });
    const all = [...detail.offScript, ...detail.onScript, ...detail.ungraded];
    expect(all.some((r) => r.player === "Riley Greene")).toBe(false);
    expect(detail.dropped.find((d) => d.reason === "conflicting_legs")?.count).toBe(1);
  });
});

describe("#8313 — the line", () => {
  const pair = (overMark: number, underMark: number): Row[] => [
    {
      market_name: "Test Player: Home Runs O/U 0.5",
      outcome_name: "Under",
      threshold: 0.5,
      over_probability: 0.3,
      pregame_mark: underMark,
    } as unknown as Row,
    {
      market_name: "Test Player: Home Runs O/U 0.5",
      outcome_name: "Over",
      threshold: 0.5,
      over_probability: 0.3,
      pregame_mark: overMark,
    } as unknown as Row,
  ];
  const live = (rows: Row[]) => selectDivergenceRows({ playerProps: rows, status: "live" });

  it("sits at 0.2", () => {
    expect(PROP_LEG_DISAGREEMENT).toBe(0.2);
  });

  it("withholds at the line (0.3 vs 0.1 is a float 0.19999…)", () => {
    const res = live(pair(0.1, 0.3));
    expect(res.rows).toHaveLength(0);
    expect(res.dropped.find((d) => d.reason === "conflicting_legs")?.count).toBe(1);
  });

  it("keeps a pair just under it, and keeps legs that agree", () => {
    for (const [o, u] of [
      [0.1, 0.29],
      [0.22, 0.1], // the widest healthy pair measured (Tatis, 15316961): 0.12
      [0.065, 0.065],
    ]) {
      const res = live(pair(o, u));
      expect(res.dropped.find((d) => d.reason === "conflicting_legs")).toBeUndefined();
      expect(res.rows).toHaveLength(1);
    }
  });

  it("tells the reader in words, not an enum key", () => {
    expect(isBenignDrop("conflicting_legs")).toBe(false);
    expect(PROP_DROP_REASON_LABEL.conflicting_legs).toBe("with conflicting prices");
  });
});
