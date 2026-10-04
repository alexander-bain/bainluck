/**
 * #10397 — the props rail led with "Rice's 4+ hits + runs + rbis was marked 99%
 * — and it missed" on a 1–0 Yankees loss.
 *
 * `eventPlayerProps.15322539.invertedLadder.json` is the REAL production
 * `player_props` array of `GET /api/events/15322539/game-markets` (Rays 1 –
 * Yankees 0, Final), captured 2026-10-04 ~01:48Z. Polymarket's Ben Rice
 * "Hits + Runs + RBIs" ladder:
 *
 *   O/U 1.5  pregame_mark 0.01 on both legs
 *   O/U 3.5  pregame_mark 0.99 on both legs
 *
 * Both legs of each question agree, so #8313's leg check cannot see it. The
 * ladder can: "2+" can never be less likely than "4+". The data half (where the
 * mark is captured) is a separate fix; this file guards the rail half.
 */

import {
  PROP_STRUCTURAL_CERTAINTY,
  selectDivergenceDetail,
  selectDivergenceRows,
} from "@/lib/propDivergence";
import type { PlayerPropRow } from "@/lib/playerPropsGrouping";

import payload from "../fixtures/eventPlayerProps.15322539.invertedLadder.json";

type Row = PlayerPropRow & { pregame_mark: number };

const ROWS = payload as unknown as Row[];
const RICE_LOW = "Ben Rice: Hits + Runs + RBIs O/U 1.5";
const RICE_HIGH = "Ben Rice: Hits + Runs + RBIs O/U 3.5";
const isRiceLadder = (r: Row) => r.market_name === RICE_LOW || r.market_name === RICE_HIGH;

const settled = (rows: readonly Row[]) =>
  selectDivergenceRows({ playerProps: rows, status: "completed" });
const conflicting = (res: { dropped: { reason: string; count: number; examples: string[] }[] }) =>
  res.dropped.find((d) => d.reason === "conflicting_legs");

describe("#10397 — the production specimen", () => {
  it("is a ladder whose legs agree per rung and whose rungs contradict each other", () => {
    expect(ROWS.filter((r) => r.market_name === RICE_LOW).map((r) => r.pregame_mark)).toEqual([0.01, 0.01]);
    expect(ROWS.filter((r) => r.market_name === RICE_HIGH).map((r) => r.pregame_mark)).toEqual([0.99, 0.99]);
  });

  it("no longer puts either Rice H+R+RBI rung on the rail, and says two were held back", () => {
    const res = settled(ROWS);
    expect(res.rows.some((r) => r.player === "Ben Rice" && r.stat === "Hits + Runs + RBIs")).toBe(false);
    expect(res.rows.some((r) => /99%/.test(r.sentence ?? ""))).toBe(false);
    const drop = conflicting(res);
    expect(drop?.count).toBe(2);
    expect([...(drop?.examples ?? [])].sort()).toEqual([RICE_LOW, RICE_HIGH]);
  });

  it("keeps Rice's own healthy ladder and the rest of the game (gotcha #43, the other direction)", () => {
    const detail = selectDivergenceDetail({ playerProps: ROWS, status: "completed" });
    const all = [...detail.offScript, ...detail.onScript, ...detail.ungraded];
    expect(all.some((r) => r.label === "Ben Rice: 1+ home runs")).toBe(true);
    // Spencer Jones' 2+ and 3+ rungs sit level at 0.01: monotone, kept.
    expect(all.filter((r) => r.player === "Spencer Jones" && r.stat === "Hits + Runs + RBIs")).toHaveLength(2);
    expect(settled(ROWS).rows.length).toBeGreaterThan(0);
  });

  it("gives the same answer whatever order the rungs arrive in", () => {
    const flipped = [...ROWS.filter((r) => !isRiceLadder(r)), ...ROWS.filter(isRiceLadder).reverse()];
    for (const rows of [ROWS, flipped]) {
      expect(conflicting(settled(rows))?.count).toBe(2);
    }
  });

  it("is withheld by the detail view too — one admission rule", () => {
    const detail = selectDivergenceDetail({ playerProps: ROWS, status: "completed" });
    const all = [...detail.offScript, ...detail.onScript, ...detail.ungraded];
    expect(all.some((r) => r.player === "Ben Rice" && r.stat === "Hits + Runs + RBIs")).toBe(false);
    expect(conflicting(detail)?.count).toBe(2);
  });
});

describe("#10397 — the line", () => {
  const rung = (threshold: number, mark: number, player = "Test Player"): Row[] =>
    ["Over", "Under"].map(
      (outcome) =>
        ({
          market_name: `${player}: Hits O/U ${threshold}`,
          outcome_name: outcome,
          threshold,
          over_probability: 0.3,
          pregame_mark: mark,
          ...(outcome === "Under" ? { _inverted: true } : {}),
        }) as unknown as Row,
    );
  // The detail view, not the rail: the rail shows one rung per ladder (UX-P108),
  // so only the detail can show which rungs were admitted.
  const live = (rows: Row[]) => {
    const detail = selectDivergenceDetail({ playerProps: rows, status: "live" });
    const admitted = [...detail.offScript, ...detail.onScript, ...detail.ungraded];
    return { ...detail, thresholds: admitted.map((r) => r.threshold).sort() };
  };

  it("sits on the structural pass's own near-certainty", () => {
    expect(PROP_STRUCTURAL_CERTAINTY).toBe(0.44);
  });

  it("withholds both rungs at the line (6% under 94% — floats either side of 0.44)", () => {
    const res = live([...rung(0.5, 0.06), ...rung(1.5, 0.94)]);
    expect(res.thresholds).toEqual([]);
    expect(conflicting(res)?.count).toBe(2);
  });

  it("keeps the pair when either end is just short of near-certain", () => {
    for (const [lo, hi] of [
      [0.07, 0.94],
      [0.06, 0.93],
    ]) {
      const res = live([...rung(0.5, lo), ...rung(1.5, hi)]);
      expect(conflicting(res)).toBeUndefined();
      expect(res.thresholds).toEqual([0.5, 1.5]);
    }
  });

  it("withholds only the rungs in the contradiction, not the whole ladder", () => {
    const res = live([...rung(0.5, 0.97), ...rung(1.5, 0.03), ...rung(2.5, 0.96)]);
    // 2+ near-certain NO under 3+ near-certain YES; 1+ at 97% sits below both.
    expect(conflicting(res)?.count).toBe(2);
    expect(res.thresholds).toEqual([0.5]);
  });

  it("keeps ruling 112's Singer ladder: rungs open at different times, so an inversion alone is no defect", () => {
    // 14788546, Brady Singer strikeouts 2+..5+ as opened: 46%, 5%, 6%, 39%.
    const res = live([...rung(1.5, 0.46), ...rung(2.5, 0.05), ...rung(3.5, 0.06), ...rung(4.5, 0.39)]);
    expect(conflicting(res)).toBeUndefined();
    expect(res.thresholds).toEqual([1.5, 2.5, 3.5, 4.5]);
  });

  it("keeps a monotone ladder and a level one", () => {
    for (const marks of [
      [0.97, 0.5, 0.03],
      [0.01, 0.01, 0.01],
    ]) {
      const res = live([...rung(0.5, marks[0]), ...rung(1.5, marks[1]), ...rung(2.5, marks[2])]);
      expect(conflicting(res)).toBeUndefined();
      expect(res.thresholds).toEqual([0.5, 1.5, 2.5]);
    }
  });

  it("never compares two players' ladders", () => {
    const res = live([...rung(0.5, 0.03, "Player One"), ...rung(1.5, 0.97, "Player Two")]);
    expect(conflicting(res)).toBeUndefined();
    expect(res.thresholds).toEqual([0.5, 1.5]);
  });
});
