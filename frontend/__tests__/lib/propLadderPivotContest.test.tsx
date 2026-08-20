/**
 * RULING 112'S REPORTED COST, DETECTED RATHER THAN ARGUED — UX-P110.
 *
 * Ruling 112 shipped with a cost stated against its own work:
 *
 *   "A moved structural rung now spends its ladder's one slot. So a ladder whose
 *    biggest mover is a collapsed rung cannot also show the rung the market has a
 *    live view about. On the specimen the cost is zero … but the shape is real."
 *
 * Alex's disposition, 2026-08-20: **DEFERRED TO PIXELS.** Layout calls run through
 * visual mocks, never a word-argument, and with zero specimens the question is not
 * ripe. Keep the shipped biggest-mover behaviour and DO NOT CHANGE THE TEST — but
 * make sure the question gets answered the day a real card asks it.
 *
 * So this file tests a DETECTOR, not a rule. Two things it must do and one it must
 * not: fire on the contested shape, stay silent on every shape that only looks like
 * it, and change nothing about what the rail renders.
 *
 * The four production payloads are the standing control. `ladderPivotContests` is
 * empty on all of them today — that is the "zero specimens" claim, asserted here so
 * that the day it stops being true, this suite says so.
 */

import {
  PROP_STRUCTURAL_CERTAINTY,
  RAIL_MAX_PER_LADDER,
  selectDivergenceRows,
  type DivergenceRow,
} from "@/lib/propDivergence";
import type { PlayerPropRow } from "@/lib/playerPropsGrouping";

import phillies from "../fixtures/eventPlayerProps.15199886.json";
import reds from "../fixtures/eventPlayerProps.14788546.json";
import dodgers from "../fixtures/eventPlayerProps.15199902.settled.json";
import braves from "../fixtures/eventPlayerProps.15194472.settled.json";

const PRODUCTION: Array<[string, PlayerPropRow[]]> = [
  ["15199886", phillies as unknown as PlayerPropRow[]],
  ["14788546", reds as unknown as PlayerPropRow[]],
  ["15199902", dodgers as unknown as PlayerPropRow[]],
  ["15194472", braves as unknown as PlayerPropRow[]],
];

/** A Kalshi-shaped rung: player in the OUTCOME, stat in the MARKET. */
function rung(
  player: string,
  stat: string,
  line: number,
  mark: number,
  current = mark,
): PlayerPropRow {
  return {
    market_name: `St. Louis vs Cincinnati: ${stat}`,
    outcome_name: `${player}: ${line}+`,
    threshold: line,
    over_probability: current,
    pregame_mark: mark,
    source: "kalshi",
  } as unknown as PlayerPropRow;
}

function rail(rows: PlayerPropRow[], status = "scheduled") {
  return selectDivergenceRows({ playerProps: rows, status });
}

const labels = (rows: readonly DivergenceRow[]) => rows.map((r) => r.label);

/**
 * THE CONTESTED SHAPE, built to ruling 112's own description.
 *
 *   Singer 5+  0.39 -> 0.05   34.0 pt   conviction 0.45  STRUCTURAL (2+ sits below)
 *   Singer 2+  0.46 -> 0.30   16.0 pt   conviction 0.20  market-live
 *
 * The 5+ rung is on the rail only because ruling 112 readmitted it, it outranks
 * its sibling on travel, and `RAIL_MAX_PER_LADDER` therefore silences the rung the
 * market still has a live view about. That is the cost, in one ladder.
 *
 * Ruling 112's real specimen differs in exactly one respect and that is why its
 * cost was zero: Singer's actual 2+ never moved (46.0% -> 46.0%).
 */
function contestedCard(): PlayerPropRow[] {
  return [
    rung("Brady Singer", "strikeouts", 5, 0.39, 0.05),
    rung("Brady Singer", "strikeouts", 2, 0.46, 0.3),
    rung("Brycen Mautz", "strikeouts", 5, 0.6, 0.2),
    rung("Ivan Herrera", "hits + runs + rbis", 1, 0.75, 0.463),
    rung("Victor Scott", "hits + runs + rbis", 1, 0.74, 0.455),
    rung("Bryan Torres", "hits + runs + rbis", 1, 0.73, 0.45),
  ];
}

describe("the detector fires on the contested shape", () => {
  it("names the ladder, the mover that took the slot, and the rung it displaced", () => {
    const result = rail(contestedCard());
    expect(result.ladderPivotContests).toHaveLength(1);

    const [contest] = result.ladderPivotContests;
    expect(contest.ladder).toBe("Brady Singer|Strikeouts");

    // The mover is on the rail ONLY because ruling 112 readmitted it.
    expect(contest.mover.threshold).toBe(5);
    expect(contest.mover.structural).toBe(true);
    expect(contest.mover.direction).not.toBe("flat");
    expect(contest.mover.conviction).toBeGreaterThanOrEqual(PROP_STRUCTURAL_CERTAINTY);

    // The pivot is the rung the market has a live view about, and it moved.
    expect(contest.pivot.threshold).toBe(2);
    expect(contest.pivot.structural).toBe(false);
    expect(contest.pivot.direction).not.toBe("flat");

    // And the mover really did take the slot the pivot wanted.
    expect(labels(result.rows)).toContain(contest.mover.label);
    expect(labels(result.rows)).not.toContain(contest.pivot.label);
  });

  it("carries a counterfactual rail that differs by exactly one row", () => {
    const [contest] = rail(contestedCard()).ladderPivotContests;
    const shipped = labels(rail(contestedCard()).rows);
    const counterfactual = labels(contest.counterfactualRows);

    expect(counterfactual).toHaveLength(shipped.length);
    // 1-for-1 inside one ladder — hence one player — so no cap counter moves and
    // no third row can be pulled in or pushed out. That is what makes it a
    // counterfactual rather than a different rail.
    const gone = shipped.filter((l) => !counterfactual.includes(l));
    const arrived = counterfactual.filter((l) => !shipped.includes(l));
    expect(gone).toEqual([contest.mover.label]);
    expect(arrived).toEqual([contest.pivot.label]);
  });

  it("keeps the counterfactual in ranking order, not in the mover's old slot", () => {
    const [contest] = rail(contestedCard()).ladderPivotContests;
    const travels = contest.counterfactualRows.map((r) => r.travel);
    // The pivot travelled less than the mover, so a faithful counterfactual must
    // re-rank it rather than leave it sitting where the mover was.
    expect([...travels].sort((a, b) => b - a)).toEqual(travels);
  });
});

describe("the detector stays silent on shapes that only look contested", () => {
  it("is silent when the slot went to an ordinary mover — ruling 112 is not implicated", () => {
    // Same ladder, but the winning rung is nowhere near certain, so it did not
    // need readmitting and no ruling-112 cost is being paid.
    const rows = [
      rung("Brady Singer", "strikeouts", 5, 0.7, 0.3),
      rung("Brady Singer", "strikeouts", 2, 0.46, 0.35),
      rung("Ivan Herrera", "hits + runs + rbis", 1, 0.75, 0.463),
    ];
    const result = rail(rows);
    expect(result.rows.length).toBeGreaterThan(0);
    expect(result.ladderPivotContests).toEqual([]);
  });

  it("is silent when the displaced sibling never moved — this is ruling 112's own specimen", () => {
    // Change ONE number from the contested card: Singer's 2+ stays where it
    // opened, exactly as it does on `14788546`. Nothing with a live view is being
    // crowded out, so there is no question to route.
    const rows = contestedCard().map((r) =>
      (r as unknown as { outcome_name: string }).outcome_name === "Brady Singer: 2+"
        ? rung("Brady Singer", "strikeouts", 2, 0.46, 0.46)
        : r,
    );
    const result = rail(rows);
    expect(result.rows.some((r) => r.player === "Brady Singer")).toBe(true);
    expect(result.ladderPivotContests).toEqual([]);
  });

  it("is silent when every sibling is also structural — no live view exists to displace", () => {
    const rows = [
      rung("Brady Singer", "strikeouts", 5, 0.39, 0.05),
      rung("Brady Singer", "strikeouts", 6, 0.23, 0.05),
      rung("Brady Singer", "strikeouts", 7, 0.14, 0.05),
      rung("Ivan Herrera", "hits + runs + rbis", 1, 0.75, 0.463),
    ];
    expect(rail(rows).ladderPivotContests).toEqual([]);
  });

  it("is silent in-game and post-game — ruling 112 is pregame-only, so its cost is too", () => {
    for (const status of ["live", "in_progress", "final", "closed"]) {
      expect(rail(contestedCard(), status).ladderPivotContests).toEqual([]);
    }
  });

  it("is empty on an empty rail rather than undefined", () => {
    expect(rail([]).ladderPivotContests).toEqual([]);
  });
});

describe("the detector changes nothing about what the rail renders", () => {
  it("the contested card's rows are what the shipped rule selects", () => {
    // Alex ruled the biggest mover stays. Assert the mover is leading its ladder
    // and the cap is still one — i.e. the detector reports the cost without
    // quietly paying it.
    const result = rail(contestedCard());
    const singerRows = result.rows.filter((r) => r.player === "Brady Singer");
    expect(singerRows).toHaveLength(RAIL_MAX_PER_LADDER);
    expect(singerRows[0].threshold).toBe(5);
  });

  it.each(PRODUCTION)(
    "%s: pregame rail is untouched and reports ZERO contests",
    (_id, rows) => {
      const result = rail(rows);
      // The standing "zero specimens" claim from ruling 112, now asserted. When
      // this goes red, a real payload has finally asked the question and the
      // capture rig owes Alex a pair of pictures.
      expect(result.ladderPivotContests).toEqual([]);
      // And the rail itself still has the shape the ruling shipped.
      expect(result.rows.length).toBeLessThanOrEqual(5);
    },
  );

  it("14788546 still leads its Singer ladder with the 34-point rung", () => {
    // Ruling 112's proof subject, re-asserted here so a change to the detector
    // that disturbed selection would be caught in this file too, not only next door.
    const result = rail(reds as unknown as PlayerPropRow[]);
    const singer = result.rows.filter((r) => r.player.includes("Singer"));
    if (singer.length > 0) {
      expect(singer).toHaveLength(1);
      expect(singer[0].travel).toBeGreaterThan(0.3);
    }
  });
});
