/**
 * #9178 — a settled MLB page asked one prop twice.
 *
 * `eventPlayerProps.15318905.crossVenueRung.json` is the REAL production
 * `player_props` array of `GET /api/events/15318905/game-markets` (Padres 10–7
 * Diamondbacks, completed), captured 2026-09-27 ~18:19Z, trimmed to the 58 rows
 * that carry a threshold, a price and a pregame mark (the only rows the rail can
 * admit; every other row drops as benign `no_line` / `no_real_price`).
 *
 * Four questions are priced by both venues, all home runs 1+:
 *
 *   Polymarket  "Manny Machado: Home Runs O/U 0.5" Over   threshold 0.5  mark 0.095
 *   Kalshi      "Arizona vs San Diego: Home Runs" / "Manny Machado: 1+"
 *                                                         threshold 1.0  mark 0.17
 *
 * The dedupe key read the RAW threshold, so 0.5 ≠ 1.0 kept two rows, and the
 * rail printed "Machado's 1+ home runs was marked 10%" and "... 17%".
 */

import {
  selectDivergenceDetail,
  selectDivergenceRows,
} from "@/lib/propDivergence";
import type { PlayerPropRow } from "@/lib/playerPropsGrouping";

import payload from "../fixtures/eventPlayerProps.15318905.crossVenueRung.json";

type Row = PlayerPropRow & { pregame_mark: number; _inverted?: boolean };

const ROWS = payload as unknown as Row[];
const TWINS = ["Manny Machado", "Corbin Carroll", "Ketel Marte", "Nolan Arenado"];
const KALSHI_MARKS: Record<string, number> = {
  "Manny Machado": 0.17,
  "Corbin Carroll": 0.2,
  "Ketel Marte": 0.16,
  "Nolan Arenado": 0.14,
};

const settled = (rows: readonly Row[]) =>
  selectDivergenceRows({ playerProps: rows, status: "completed" });
const detailRows = (rows: readonly Row[], status = "completed") => {
  const d = selectDivergenceDetail({ playerProps: rows, status });
  return [...d.offScript, ...d.onScript, ...d.ungraded];
};
const labelOf = (player: string) => `${player}: 1+ home runs`;

describe("#9178 — the production specimen", () => {
  it("is each question priced once by Polymarket O/U 0.5 and once by Kalshi 1+", () => {
    for (const player of TWINS) {
      const legs = ROWS.filter(
        (r) =>
          r.market_name === `${player}: Home Runs O/U 0.5` ||
          r.outcome_name === `${player}: 1+`,
      );
      expect(legs.map((l) => [l.source, l.threshold, l._inverted]).sort()).toEqual([
        ["kalshi", 1, false],
        ["polymarket", 0.5, false],
        ["polymarket", 0.5, true],
      ]);
    }
  });

  it("asks each question once — in the detail view, which holds every admitted row", () => {
    const rows = detailRows(ROWS);
    for (const player of TWINS) {
      expect(rows.filter((r) => r.label === labelOf(player))).toHaveLength(1);
    }
    // No label anywhere on the page's rail or detail appears twice.
    const labels = rows.map((r) => r.label);
    expect(labels.length).toBe(new Set(labels).size);
  });

  it("Machado's sentence is printed once on the rail, at the Kalshi mark", () => {
    const res = settled(ROWS);
    const machado = res.rows.filter((r) => r.label === labelOf("Manny Machado"));
    expect(machado).toHaveLength(1);
    expect(machado[0].pregameMark).toBe(0.17);
    expect(machado[0].sentence).toContain("17%");
    expect(res.rows.map((r) => r.sentence).join(" ")).not.toContain("marked 10%");
  });

  it("the row reads the leg whose own line IS the printed question, whichever venue arrives first", () => {
    const reversed = [...ROWS].reverse();
    for (const rows of [ROWS, reversed]) {
      const byLabel = new Map(detailRows(rows).map((r) => [r.label, r]));
      for (const player of TWINS) {
        expect(byLabel.get(labelOf(player))?.pregameMark).toBe(KALSHI_MARKS[player]);
        expect(byLabel.get(labelOf(player))?.threshold).toBe(1);
      }
    }
  });

  it("both venues' verdicts still grade the merged row (they agree here)", () => {
    const byLabel = new Map(detailRows(ROWS).map((r) => [r.label, r]));
    expect(byLabel.get(labelOf("Manny Machado"))?.resolution).toBe(1);
    expect(byLabel.get(labelOf("Nolan Arenado"))?.resolution).toBe(0);
  });

  it("a cross-venue gap below or above #8313's bar never withholds the question", () => {
    // Widen Carroll's venue gap past PROP_LEG_DISAGREEMENT (0.2): Kalshi's mark
    // 0.2 → 0.45 against Polymarket's 0.095. The Polymarket O/U pair still agrees
    // with itself, so this is not #8313's mis-stored leg.
    const widened = ROWS.map((r) =>
      r.outcome_name === "Corbin Carroll: 1+" ? { ...r, pregame_mark: 0.45 } : r,
    );
    const d = selectDivergenceDetail({ playerProps: widened, status: "completed" });
    const rows = [...d.offScript, ...d.onScript, ...d.ungraded];
    expect(rows.filter((r) => r.label === labelOf("Corbin Carroll"))).toHaveLength(1);
    expect(d.dropped.find((x) => x.reason === "conflicting_legs")).toBeUndefined();
  });
});

describe("#9178 — what it must not collapse (gotcha #43, the other direction)", () => {
  it("keeps distinct rungs apart: O/U 1.5 (2+) is not O/U 0.5 (1+)", () => {
    const labels = detailRows(ROWS).map((r) => r.label);
    expect(labels).toContain("Corbin Carroll: 1+ home runs");
    expect(labels).toContain("Corbin Carroll: 2+ home runs");
  });

  it("a lone Polymarket O/U still pairs its own legs (#9003) and still withholds a mis-stored leg (#8313)", () => {
    const polyOnly = ROWS.filter((r) => r.source === "polymarket");
    const carroll = detailRows(polyOnly).find((r) => r.label === labelOf("Corbin Carroll"));
    expect(carroll?.pregameMark).toBe(0.095);
    expect(carroll?.threshold).toBe(0.5);

    // #8313's shape: the Under leg stored with the Over's opening price.
    const misStored = polyOnly.map((r) =>
      r.market_name === "Corbin Carroll: Home Runs O/U 0.5" && r._inverted
        ? { ...r, pregame_mark: 0.905 }
        : r,
    );
    const d = selectDivergenceDetail({ playerProps: misStored, status: "completed" });
    const rows = [...d.offScript, ...d.onScript, ...d.ungraded];
    expect(rows.find((r) => r.label === labelOf("Corbin Carroll"))).toBeUndefined();
    expect(d.dropped.find((x) => x.reason === "conflicting_legs")?.count).toBe(1);
  });

  it("a Kalshi-built row does not borrow the Polymarket Under to print a pair", () => {
    // Live, so #9003's pair gate is the path a row prints through.
    const byLabel = new Map(detailRows(ROWS, "live").map((r) => [r.label, r]));
    const machado = byLabel.get(labelOf("Manny Machado"));
    expect(machado?.pregameMark).toBe(0.17);
    expect(machado?.printedMark).toBeUndefined();
  });
});
