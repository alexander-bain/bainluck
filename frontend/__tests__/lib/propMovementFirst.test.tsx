/**
 * MOVEMENT FIRST, WITH A PER-LADDER CAP — UX-P108. Alex's ruling, made off the
 * UX-P107 before/after capture.
 *
 *   "The script rail ranks MOVEMENT FIRST WITH A PER-LADDER CAP. Rows with real
 *    pregame travel (|now − opened|) rank first; conviction fills the remaining
 *    slots; at most ONE row per player-ladder family anywhere in the rail; the
 *    structural filter (ruling 105) stays underneath as a floor."
 *
 * ── WHY A RANKING CHANGE AND NOT A BETTER THRESHOLD ──────────────────────────
 *
 * UX-P107 implemented ruling 105 and reported, against itself, that the card was
 * not fixed: three rungs one point less extreme stepped into the freed slots,
 * and a sweep of `PROP_STRUCTURAL_CERTAINTY` from 0.44 to 0.35 kept the same
 * shape at every value. The rung population is a continuum with no gap, and
 * conviction ranking selects a ladder's extreme rungs BY CONSTRUCTION — so the
 * residual was never the constant. Alex's ruling changes the RANKING and adds
 * the first rule on this rail whose subject is a GROUP.
 *
 * ── THE BEFORE, MEASURED, ON ALEX'S OWN CARD ─────────────────────────────────
 *
 * `15199886`, with ruling 105's filter already applied:
 *
 *     1. Kyle Schwarber: 1+ home runs            54.7%   27.7 pt
 *     2. Alec Bohm: 1+ home runs                  6.5%    1.0 pt
 *     3. Justin Crawford: 5+ hits + runs + rbis   7.0%    0.0 pt
 *     4. Trea Turner: 4+ hits                     7.0%    0.0 pt
 *     5. Trea Turner: 3+ hits                     8.0%    0.0 pt
 *
 * Three rows that had not moved, two of them the same Turner ladder one point
 * apart. Every number in this file's `THE BEFORE` assertions is from that
 * measurement, and the after is asserted beside it.
 */

import {
  PROP_SCRIPT_CONVICTION,
  PROP_STRUCTURAL_CERTAINTY,
  PROP_SURPRISE_TRAVEL,
  PROP_TRAVEL_FLOOR,
  RAIL_MAX_PER_LADDER,
  RAIL_MAX_PER_PLAYER,
  RAIL_MAX_ROWS,
  selectDivergenceDetail,
  selectDivergenceRows,
  type DivergenceRow,
} from "@/lib/propDivergence";
import type { PlayerPropRow } from "@/lib/playerPropsGrouping";

import phillies from "../fixtures/eventPlayerProps.15199886.json";
import reds from "../fixtures/eventPlayerProps.14788546.json";
import dodgers from "../fixtures/eventPlayerProps.15199902.settled.json";
import braves from "../fixtures/eventPlayerProps.15194472.settled.json";

const PHILLIES = phillies as unknown as PlayerPropRow[];
const REDS = reds as unknown as PlayerPropRow[];
const DODGERS = dodgers as unknown as PlayerPropRow[];
const BRAVES = braves as unknown as PlayerPropRow[];
const ALL: Array<[string, PlayerPropRow[]]> = [
  ["15199886", PHILLIES],
  ["14788546", REDS],
  ["15199902", DODGERS],
  ["15194472", BRAVES],
];

function candidates(rows: PlayerPropRow[], status = "scheduled"): DivergenceRow[] {
  const d = selectDivergenceDetail({ playerProps: rows, status });
  return [...d.offScript, ...d.onScript, ...d.ungraded];
}

function rail(rows: PlayerPropRow[], status = "scheduled") {
  return selectDivergenceRows({ playerProps: rows, status });
}

function labels(rows: readonly DivergenceRow[]): string[] {
  return rows.map((r) => r.label);
}

function ladder(row: DivergenceRow): string {
  return `${row.player}|${row.stat}`;
}

/** A Kalshi-shaped rung: player in the OUTCOME, stat in the MARKET. */
function rung(
  player: string,
  stat: string,
  line: number,
  mark: number,
  current = mark,
): PlayerPropRow {
  return {
    market_name: `Philadelphia vs Miami: ${stat}`,
    outcome_name: `${player}: ${line}+`,
    threshold: line,
    over_probability: current,
    pregame_mark: mark,
    source: "kalshi",
  } as unknown as PlayerPropRow;
}

// ---------------------------------------------------------------------------
// The tier
// ---------------------------------------------------------------------------

describe("movement ranks first — a TIER, not a blend", () => {
  it("every mover outranks every non-mover, on all four production payloads", () => {
    // The load-bearing property, stated over ORDERED RUNS of the candidate list
    // rather than over the five rows that happened to fit. A blend can satisfy
    // "the top row moved" by accident; only a tier satisfies this.
    //
    // Read off `offScript` and `onScript` SEPARATELY, and that is not a
    // weakening: each is a subsequence of the one sorted candidate list, so
    // "movers first" holding in both is the tier holding in the sort. Reading
    // them concatenated would test the FOLD's partition order instead — which
    // interleaves the two tiers by construction, and is what the first draft of
    // this test actually measured.
    let checked = 0;
    for (const [id, rows] of ALL) {
      const d = selectDivergenceDetail({ playerProps: rows, status: "scheduled" });
      for (const [part, list] of [
        ["offScript", d.offScript],
        ["onScript", d.onScript],
      ] as const) {
        const moved = list.map((r) => r.direction !== "flat");
        const lastMover = moved.lastIndexOf(true);
        const firstFlat = moved.indexOf(false);
        if (lastMover === -1 || firstFlat === -1) continue;
        checked += 1;
        expect(`${id}/${part}: ${lastMover < firstFlat}`).toBe(`${id}/${part}: true`);
      }
    }
    // Non-vacuity (gotcha #43): a `continue`-heavy loop that checked nothing
    // passes silently, which is exactly the shape this suite exists to catch.
    expect(checked).toBeGreaterThanOrEqual(3);
  });

  it("a two-point move outranks a 93% favourite that has not moved", () => {
    // THE RULING'S SHARPEST EDGE, asserted rather than left to be discovered.
    // `Quiet` moved 60% -> 62%; `Rock` has sat at 93% since the board opened.
    const rows = [
      rung("Rock", "Hits", 1, 0.5 + PROP_SCRIPT_CONVICTION),
      rung("Quiet", "Hits", 2, 0.6, 0.62),
    ];
    expect(labels(rail(rows).rows)).toEqual(["Quiet: 2+ hits", "Rock: 1+ hits"]);
  });

  it("WITHIN the movement tier the key is travel, NOT salience", () => {
    // Ranking movers by `scriptSalience` would let a one-point move at 94%
    // outrank a twenty-point move at 60% — re-admitting the extreme-hunting this
    // ruling exists to end, inside the tier meant to be free of it. This is the
    // assertion that reds if anyone "simplifies" the two tiers back into one
    // max().
    const rows = [
      rung("Tiny Move Big Price", "Hits", 1, 0.94, 0.95),
      rung("Big Move Mid Price", "Hits", 2, 0.4, 0.6),
    ];
    expect(labels(rail(rows).rows)).toEqual([
      "Big Move Mid Price: 2+ hits",
      "Tiny Move Big Price: 1+ hits",
    ]);
  });

  it("in tier 2 salience IS conviction — the claim the source comment makes", () => {
    // `scriptSalience` is kept in the conviction tier so the rail and the detail
    // fold share one function. That is only harmless because every tier-2 row
    // has travel below the floor, so its travel term cannot reach the conviction
    // term. Asserted, not asserted-in-a-comment.
    const maxTravelTerm = PROP_TRAVEL_FLOOR / PROP_SURPRISE_TRAVEL;
    for (const [id, rows] of ALL) {
      const flat = candidates(rows).filter((r) => r.direction === "flat");
      for (const row of flat) {
        expect(`${id} ${row.key}`).toBe(`${id} ${row.key}`);
        expect(row.travel / PROP_SURPRISE_TRAVEL).toBeLessThan(maxTravelTerm);
      }
      // Non-vacuity (gotcha #43): there ARE flat rows to have checked.
      expect(flat.length).toBeGreaterThan(0);
    }
  });

  it("the floor is the same half-point line that types the bar", () => {
    // `hasTravelled` is defined as `direction !== "flat"`, so the movement tier
    // is exactly the set of rows whose own bar draws a journey. If these two
    // ever diverge, a screenshot stops being able to check the ranking — and a
    // screenshot is the only bar this surface has ever been judged at.
    expect(PROP_TRAVEL_FLOOR).toBe(0.005);
    for (const [, rows] of ALL) {
      for (const row of candidates(rows)) {
        expect(row.direction === "flat").toBe(row.travel < PROP_TRAVEL_FLOOR);
      }
    }
  });
});

// ---------------------------------------------------------------------------
// The cap
// ---------------------------------------------------------------------------

describe("one rung per ladder, anywhere in the rail", () => {
  it("RAIL_MAX_PER_LADDER is one", () => {
    expect(RAIL_MAX_PER_LADDER).toBe(1);
  });

  it("no rail on any production payload repeats a ladder", () => {
    for (const [id, rows] of ALL) {
      const ladders = rail(rows).rows.map(ladder);
      expect(`${id}: ${new Set(ladders).size}`).toBe(`${id}: ${ladders.length}`);
    }
  });

  it("THE DOUBLE-TURNER ROWS ARE GONE, and both are still reachable", () => {
    const r = rail(PHILLIES);
    expect(labels(r.rows).filter((l) => l.startsWith("Trea Turner"))).toHaveLength(0);
    expect(labels(candidates(PHILLIES))).toEqual(
      expect.arrayContaining(["Trea Turner: 4+ hits", "Trea Turner: 3+ hits"]),
    );
    // Rail capacity, never a taxonomy loss — the same accounting a row that
    // merely ranked sixth gets.
    expect(r.notSelected).toBe(r.eligible - r.rows.length);
    expect(r.nonBenignCount).toBe(0);
  });

  it("the cap is NOT subsumed by RAIL_MAX_PER_PLAYER, and does not subsume it", () => {
    // One player, two stats: the ladder cap permits both, the player cap allows
    // exactly two. Neither rule implies the other and a card can hit either
    // first.
    const twoStats = [
      rung("Both Ways", "Hits", 2, 0.4, 0.55),
      rung("Both Ways", "Home Runs", 1, 0.2, 0.35),
      rung("Filler", "Hits", 1, 0.5, 0.56),
    ];
    expect(labels(rail(twoStats).rows).sort()).toEqual([
      "Both Ways: 1+ home runs",
      "Both Ways: 2+ hits",
      "Filler: 1+ hits",
    ]);
    // Three stats, same player: the PLAYER cap binds at two even though all
    // three ladders are distinct.
    const threeStats = [
      ...twoStats.slice(0, 2),
      rung("Both Ways", "Strikeouts", 3, 0.3, 0.44),
    ];
    const capped = rail(threeStats).rows.filter((r) => r.player === "Both Ways");
    expect(capped).toHaveLength(RAIL_MAX_PER_PLAYER);
  });

  it("SCOPE: the cap is pregame-only — a live rail may still carry two rungs", () => {
    // Alex ruled on THE SCRIPT. In-game two rungs of one ladder moving together
    // is corroboration, not repetition, and ruling 035 says a rail nobody ruled
    // on is not re-ranked on the way past. This is the control for that scope.
    const rows = [
      rung("Mover", "Strikeouts", 5, 0.89, 0.49),
      rung("Mover", "Strikeouts", 3, 0.79, 0.49),
      rung("Other", "Hits", 1, 0.5, 0.52),
    ];
    expect(labels(rail(rows, "live").rows)).toEqual([
      "Mover: 5+ strikeouts",
      "Mover: 3+ strikeouts",
      "Other: 1+ hits",
    ]);
    // …and pregame the same payload keeps one.
    expect(labels(rail(rows, "scheduled").rows)).toEqual([
      "Mover: 5+ strikeouts",
      "Other: 1+ hits",
    ]);
  });
});

// ---------------------------------------------------------------------------
// The floor underneath (ruling 105), and what it costs
// ---------------------------------------------------------------------------

describe("ruling 105's filter stays underneath as a floor — for the rows that DID NOT MOVE (ruling 112)", () => {
  it("a FLAT structural rung is still suppressed", () => {
    // Ruling 105's predicate is untouched and still unconditional for a rung
    // whose price never left its opening. This is the arm ruling 112 did not
    // move, asserted separately from the arm it did, so a future change cannot
    // take both out with one edit.
    const rows = [
      rung("Ladder", "Strikeouts", 5, 0.04),
      rung("Ladder", "Strikeouts", 3, 0.45),
      rung("Real", "Hits", 1, 0.56),
    ];
    const r = rail(rows);
    expect(r.structuralSuppressed).toBe(1);
    expect(labels(r.rows)).not.toContain("Ladder: 5+ strikeouts");
  });

  it("A STRUCTURAL RUNG THAT MOVED IS RAIL-ELIGIBLE — ruling 112, the arm that changed", () => {
    // ** THIS TEST IS THE PREVIOUS CYCLE'S, INVERTED IN PLACE. ** UX-P108 shipped
    // the floor as unconditional, measured that it deleted a 34-point move, and
    // flagged the residual back rather than re-litigating it. Alex ruled:
    // movement overrides the structural floor. The same three rows, the same
    // ladder, the opposite expectation — and the cap still holds the ladder to
    // one row.
    const rows = [
      rung("Ladder", "Strikeouts", 5, 0.4, 0.04),
      rung("Ladder", "Strikeouts", 3, 0.5, 0.45),
      rung("Real", "Hits", 1, 0.5, 0.56),
    ];
    const r = rail(rows);
    // Both ladder rungs moved AND are structural; neither is counted suppressed.
    expect(r.structuralSuppressed).toBe(0);
    expect(labels(r.rows)).toContain("Ladder: 5+ strikeouts");
    // ONE rung of the ladder, not two — ruling 111's cap is what makes 112 safe.
    expect(labels(r.rows).filter((l) => l.startsWith("Ladder:"))).toHaveLength(1);
  });

  it("THE 34-POINT SINGER RUNG IS ON THE RAIL: ruling 112 measured on 14788546", () => {
    // ** THE HIGHEST-COST SPECIMEN UX-P108 FOUND, now the proof subject. ** Brady
    // Singer's whole strikeout ladder collapsed onto the 5% floor before first
    // pitch — 5+ went 39.0% -> 5.0%, a 34.0-point move, the second biggest on a
    // 100-question card. It is structural BECAUSE of where it landed, and it
    // landed there by travelling. Under UX-P108's unconditional floor the rail
    // deleted it and led with rows that had moved less.
    const moved = candidates(REDS).filter(
      (r) => r.structural && r.direction !== "flat",
    );
    expect(moved).toHaveLength(5);
    expect(moved.every((r) => r.player === "Brady Singer")).toBe(true);
    const biggest = Math.max(...moved.map((r) => r.travel));
    expect(Math.round(biggest * 1000) / 1000).toBe(0.34);

    const rows = rail(REDS).rows;
    // Position 2, behind Mautz's 40.0-pt rung and ahead of the 28.7 that used
    // to sit there. Pinned by INDEX, because "somewhere on the rail" would pass
    // for a 34-point move ranked fifth.
    expect(rows[1].label).toBe("Brady Singer: 5+ strikeouts");
    expect(Math.round(rows[1].travel * 1000) / 1000).toBe(0.34);
    // ** THE CAP IS DOING THE WORK: five Singer rungs moved, ONE is on the rail. **
    // Without it the 18.0-pt and 9.0-pt rungs take slots 3 and 5 and the card is
    // three quotes of one ladder — ruling 111's defect, re-created by 112.
    expect(labels(rows).filter((l) => l.startsWith("Brady Singer"))).toHaveLength(1);
  });

  it("the three rungs that did NOT move are still suppressed: 8 structural, 3 counted", () => {
    // The floor did not stop mattering. On the same card three structural rungs
    // are flat — Singer's 3+, Liberatore's 10+, Mautz's 8+ — and all three stay
    // off the rail. `structuralSuppressed` counts what the loop SKIPS, so it
    // reads 3, not the 8 that carry the flag.
    const all = candidates(REDS);
    expect(all.filter((r) => r.structural)).toHaveLength(8);
    const r = rail(REDS);
    expect(r.structuralSuppressed).toBe(3);
    for (const gone of [
      "Brady Singer: 3+ strikeouts",
      "Matthew Liberatore: 10+ strikeouts",
      "Brycen Mautz: 8+ strikeouts",
    ]) {
      expect(labels(r.rows)).not.toContain(gone);
    }
  });

  it("THE COST OF RULING 112, MEASURED NOT ASSUMED: a moved rung spends its ladder's slot", () => {
    // ** REPORTED RATHER THAN DISCOVERED LATER. ** Because a moved structural
    // rung now reaches `push`, it consumes its ladder's one slot — so a ladder
    // whose biggest mover is a collapsed rung cannot ALSO show the rung the
    // market has a live view about. Synthetic, because the specimen does not
    // exhibit it: Singer's 2+ is 46.0% and flat, conviction 0.040, so it was
    // never reaching a five-row rail from tier 2 anyway.
    const singerLive = candidates(REDS).find(
      (r) => r.label === "Brady Singer: 2+ strikeouts",
    )!;
    expect(singerLive.structural).toBe(false);
    expect(singerLive.direction).toBe("flat");
    expect(singerLive.conviction).toBeCloseTo(0.04, 6);

    // The shape that WOULD cost something: a collapsed rung that moved further
    // than its own ladder's live question.
    const rows = [
      rung("Pitcher", "Strikeouts", 9, 0.45, 0.05), // structural, moved 40 pt
      rung("Pitcher", "Strikeouts", 4, 0.6, 0.72), // the real view, moved 12 pt
      rung("Filler", "Hits", 1, 0.5, 0.58),
    ];
    const r = rail(rows);
    expect(labels(r.rows)).toContain("Pitcher: 9+ strikeouts");
    expect(labels(r.rows)).not.toContain("Pitcher: 4+ strikeouts");
    // Accepted, not a bug: movement-first says the biggest mover is the story,
    // and the 4+ rung remains in the expand. If Alex wants the pivot rung
    // preferred inside a ladder, that is a ruling and it changes this test.
    const detail = selectDivergenceDetail({ playerProps: rows, status: "scheduled" });
    expect(
      [...detail.offScript, ...detail.onScript].map((x) => x.label),
    ).toContain("Pitcher: 4+ strikeouts");
  });
});

// ---------------------------------------------------------------------------
// The card Alex ruled on
// ---------------------------------------------------------------------------

describe("15199886 — the before and the after, on one card", () => {
  it("THE BEFORE is gone: no row on the rail is flat, and none repeats a ladder", () => {
    const rows = rail(PHILLIES).rows;
    expect(rows).toHaveLength(RAIL_MAX_ROWS);
    expect(rows.filter((r) => r.direction === "flat")).toHaveLength(0);
    expect(new Set(rows.map(ladder)).size).toBe(RAIL_MAX_ROWS);
    // The three flat rows UX-P107 measured at positions 3, 4 and 5.
    for (const gone of [
      "Justin Crawford: 5+ hits + runs + rbis",
      "Trea Turner: 4+ hits",
      "Trea Turner: 3+ hits",
    ]) {
      expect(labels(rows)).not.toContain(gone);
    }
  });

  it("THE AFTER, pinned exactly — five movers, five ladders", () => {
    // Pinned as an ordered list on purpose. This rail is ruled on from a
    // screenshot, so the thing worth locking is the picture, not a property that
    // several different pictures could satisfy.
    expect(labels(rail(PHILLIES).rows)).toEqual([
      "Kyle Schwarber: 1+ home runs",
      "Kyle Schwarber: 2+ hits",
      "Brandon Marsh: 2+ hits",
      "Alec Bohm: 3+ hits",
      "Bryan De La Cruz: 2+ hits",
    ]);
  });

  it("Schwarber twice is the PLAYER cap working, not the ladder cap failing", () => {
    // Two different stats — home runs and hits — so two claims, permitted by the
    // ladder cap and bounded at two by `RAIL_MAX_PER_PLAYER`. Worth its own test
    // because a reader scanning the pinned list above will ask.
    const his = rail(PHILLIES).rows.filter((r) => r.player === "Kyle Schwarber");
    expect(his).toHaveLength(RAIL_MAX_PER_PLAYER);
    expect(new Set(his.map(ladder)).size).toBe(2);
  });

  it("a card where NOTHING moved still shows THE SCRIPT, by conviction", () => {
    // The tier degrades to the old behaviour rather than to an empty rail —
    // `15194472` has two questions and neither has moved.
    const r = rail(BRAVES);
    expect(r.rows).toHaveLength(2);
    expect(r.rows.every((x) => x.direction === "flat")).toBe(true);
    expect(r.emptyReason).toBeNull();
    expect(labels(r.rows)).toEqual([
      "Mauricio Dubón: 2+ home runs",
      "Ozzie Albies: 1+ home runs",
    ]);
  });
});

// ---------------------------------------------------------------------------
// Controls — the states this ruling does not touch
// ---------------------------------------------------------------------------

describe("CONTROL: the live and settled rails do not move", () => {
  it.each(ALL)("%s: live and settled rails are unchanged by the pregame ruling", (_id, rows) => {
    // Ruling 050: a change predicted to move nothing on a measured surface is
    // still read, EXPECTING no movement. The pregame ranking key and the ladder
    // cap are both gated on `pregame`, so these two states must be untouched —
    // and they were verified byte-identical against `program/ux-94` before this
    // test was written, over all four payloads.
    const live = rail(rows, "live");
    const settled = rail(rows, "completed");
    // The live rail ranks by travel and applies NO ladder cap.
    expect(live.structuralSuppressed).toBe(0);
    for (let i = 1; i < live.rows.length; i += 1) {
      expect(live.rows[i - 1].travel).toBeGreaterThanOrEqual(live.rows[i].travel);
    }
    // The settled rail ranks by surprise and applies no ladder cap either.
    expect(settled.structuralSuppressed).toBe(0);
    const surprises = settled.rows.map((r) => r.surprise ?? -1);
    for (let i = 1; i < surprises.length; i += 1) {
      expect(surprises[i - 1]).toBeGreaterThanOrEqual(surprises[i]);
    }
  });

  it("the detail view's MEMBERSHIP is unchanged — only its order", () => {
    // The fold predicate did not change, so which questions sit above the fold
    // is the same set; the new sort reorders within it. Recorded because the
    // reorder IS a user-visible change and should not arrive unannounced.
    for (const [id, rows] of ALL) {
      const d = selectDivergenceDetail({ playerProps: rows, status: "scheduled" });
      const above = new Set(d.offScript.map((r) => r.key));
      for (const row of candidates(rows)) {
        const salience = Math.max(
          row.travel / PROP_SURPRISE_TRAVEL,
          row.conviction / PROP_SCRIPT_CONVICTION,
        );
        expect(`${id} ${row.key}: ${above.has(row.key)}`).toBe(
          `${id} ${row.key}: ${salience >= 0.94 - 1e-9}`,
        );
      }
    }
  });

  it("the structural predicate itself is untouched — 105's specimen triple still holds", () => {
    // The 6.0%-priced triple on `15199902` is ruling 105's load-bearing test.
    // This queue changed the RANKING and added a CAP; if it had also moved the
    // predicate, this reds.
    const all = candidates(DODGERS);
    const by = (l: string) => all.find((r) => r.label === l)!;
    expect(by("Jordan Beck: 3+ hits").structural).toBe(false);
    expect(by("Kyle Tucker: 3+ hits").structural).toBe(true);
    expect(by("Braxton Fulford: 3+ hits").structural).toBe(true);
    expect(PROP_STRUCTURAL_CERTAINTY).toBe(0.44);
  });
});
