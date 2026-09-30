/**
 * #8991 — a live MLB page answered one prop twice.
 *
 * `eventPlayerProps.15318878.overLegCurrent.json` is the REAL production
 * `player_props` array of `GET /api/events/15318878/game-markets` (Cardinals @
 * Brewers, live, End 4th), captured 2026-09-27 00:30Z. Polymarket's
 * "William Contreras: Home Runs O/U 0.5" has two legs that agree on the opening
 * mark (0.075) but not on the price now:
 *
 *   Under  over_probability 0.08  (_inverted: 1 − 0.92)   ← listed FIRST
 *   Over   over_probability 0.16
 *
 * The rail built its row from the first leg and printed "1+ home runs · now 8%"
 * while THE DIVERGENCE on the same page (backend `props_script`, each leg on its
 * own axis) printed "Over 8% → 16%". Jackson Chourio is the same shape (Under
 * 0.09, Over 0.18). #8313 did not fire: it compares the legs' MARKS only.
 *
 * The row now reads the Over leg's own price whenever the payload has one.
 */

import {
  selectDivergenceDetail,
  selectDivergenceRows,
} from "@/lib/propDivergence";
import type { PlayerPropRow } from "@/lib/playerPropsGrouping";

import payload from "../fixtures/eventPlayerProps.15318878.overLegCurrent.json";

type Row = PlayerPropRow & { pregame_mark: number; _inverted?: boolean };

const ROWS = payload as unknown as Row[];
const CONTRERAS = "William Contreras: Home Runs O/U 0.5";
const CHOURIO = "Jackson Chourio: Home Runs O/U 0.5";

const live = (rows: readonly Row[]) => selectDivergenceRows({ playerProps: rows, status: "live" });
const detailRows = (rows: readonly Row[]) => {
  const d = selectDivergenceDetail({ playerProps: rows, status: "live" });
  return [...d.offScript, ...d.onScript, ...d.ungraded];
};
const byLabel = <T extends { label: string }>(rows: T[], label: string) =>
  rows.find((r) => r.label === label);

describe("#8991 — the production specimen", () => {
  it("is two legs that agree on the mark and disagree now, the inverted Under first", () => {
    const legs = ROWS.filter((r) => r.market_name === CONTRERAS);
    expect(legs.map((l) => [l.outcome_name, l._inverted, l.over_probability, l.pregame_mark])).toEqual([
      ["Under", true, 0.08, 0.075],
      ["Over", false, 0.16, 0.075],
    ]);
  });

  it("prints the Over leg's own price on the rail — the number THE DIVERGENCE prints", () => {
    const res = live(ROWS);
    const contreras = byLabel(res.rows, "William Contreras: 1+ home runs");
    expect(contreras?.current).toBe(0.16);
    expect(contreras?.pregameMark).toBe(0.075);
    expect(contreras?.direction).toBe("over");
    const chourio = byLabel(res.rows, "Jackson Chourio: 1+ home runs");
    expect(chourio?.current).toBe(0.18);
  });

  it("gives the same row whichever leg arrives first", () => {
    const pairs = new Set([CONTRERAS, CHOURIO]);
    const flipped = [
      ...ROWS.filter((r) => !pairs.has(r.market_name ?? "")),
      ...ROWS.filter((r) => r.market_name === CONTRERAS).reverse(),
      ...ROWS.filter((r) => r.market_name === CHOURIO).reverse(),
    ];
    for (const rows of [ROWS, flipped]) {
      expect(byLabel(live(rows).rows, "William Contreras: 1+ home runs")?.current).toBe(0.16);
      expect(byLabel(detailRows(rows), "Jackson Chourio: 1+ home runs")?.current).toBe(0.18);
    }
  });

  it("the detail view reads the same leg — one admission rule, one number", () => {
    expect(byLabel(detailRows(ROWS), "William Contreras: 1+ home runs")?.current).toBe(0.16);
  });

  it("changes no question whose legs already agree (gotcha #43, the other direction)", () => {
    const res = live(ROWS);
    expect(byLabel(res.rows, "Jordan Walker: 1+ home runs")?.current).toBe(0.095);
    expect(res.rows.length).toBe(5);
    expect(res.dropped.find((d) => d.reason === "conflicting_legs")).toBeUndefined();
  });
});

describe("#8991 — a lone Under leg", () => {
  it("still reads its inverted price: it is the best number the page has", () => {
    const under = ROWS.filter((r) => r.market_name === CONTRERAS && r.outcome_name === "Under");
    // #1626 slice 2: 0.075 → 0.08 prints 8% → 8%, so the lone leg is no longer
    // on "What's moving" — the READ is this test's subject, and the detail view
    // uses the same admission rule, so it is asserted there. It is not lost.
    const res = live(under);
    expect(res.rows).toHaveLength(0);
    expect(res.eligible).toBe(1);
    const rows = detailRows(under);
    expect(rows).toHaveLength(1);
    expect(rows[0].current).toBe(0.08);
    expect(rows[0].direction).toBe("flat");
  });
});
