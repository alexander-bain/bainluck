/**
 * STRUCTURAL RUNGS — UX-P107. Alex's ruling, off the UX-P106 capture.
 *
 * "SUPPRESS STRUCTURAL RUNGS. Near-certain ladder rungs whose probability is
 * arithmetic (a rung's position in its own ladder, not a market view) are
 * filtered out of the 5-row script rail; conviction ranking stays among what
 * remains; they stay reachable in 'See all 40'."
 *
 * And the bar the implementation had to clear:
 *
 *   "'Structural' needs a real predicate — rung position within its own ladder
 *    family plus threshold — never a bare probability cutoff; a genuine
 *    standalone 94% market view must survive the filter."
 *
 * ── THE SPECIMEN THE POPULATION HANDED US ────────────────────────────────────
 *
 * The bar is not tested by paraphrasing it. Production event `15199902` carries
 * three questions reading "3+ hits", all priced at exactly **6.0%**, and the
 * only thing that differs between them is whether the market also asked a
 * lower rung:
 *
 *   Jordan Beck: 3+ hits       family [3]     SURVIVES
 *   Kyle Tucker: 3+ hits       family [2,3]   suppressed
 *   Braxton Fulford: 3+ hits   family [2,3]   suppressed
 *
 * A bare probability cutoff deletes all three. That triple is the load-bearing
 * test in this file: it reds the moment anyone reduces the predicate to a price
 * comparison, and it cannot be satisfied by one.
 *
 * ── WHAT THIS FILE DELIBERATELY DOES NOT CLAIM ───────────────────────────────
 *
 * That the filter makes every card read like a script. It does not, and the
 * measurement below records why: the rung population is a CONTINUUM with no gap
 * (5.0, 6.0, 7.0, 7.2, 8.5, 8.8, 9.0 …), so on a card with almost no questions
 * near a coin flip, the rows promoted into the freed slots are rungs one point
 * less extreme. Swept from 0.44 down to 0.35, the Phillies rail keeps the same
 * shape at every value. That is a finding about the CONVICTION KEY, not a knob
 * left un-turned, and it is recorded here rather than papered over.
 */

import { renderToStaticMarkup } from "react-dom/server";
import React from "react";

import {
  PROP_SCRIPT_CONVICTION,
  PROP_STRUCTURAL_CERTAINTY,
  selectDivergenceDetail,
  selectDivergenceRows,
  type DivergenceRow,
} from "@/lib/propDivergence";
import type { PlayerPropRow } from "@/lib/playerPropsGrouping";
import PropDivergenceRail from "@/components/PropDivergenceRail";

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

/** Every eligible question on a payload, read as pregame. */
function candidates(rows: PlayerPropRow[]): DivergenceRow[] {
  const d = selectDivergenceDetail({ playerProps: rows, status: "scheduled" });
  return [...d.offScript, ...d.onScript, ...d.ungraded];
}

function pooled(): DivergenceRow[] {
  return ALL.flatMap(([, rows]) => candidates(rows));
}

function labels(rows: readonly DivergenceRow[]): string[] {
  return rows.map((r) => r.label);
}

/**
 * A Kalshi-shaped rung. The provider puts the player in the OUTCOME and the
 * stat in the MARKET, which is the shape that makes a ladder: one market name,
 * many players, many thresholds.
 */
function rung(
  player: string,
  stat: string,
  line: number,
  price: number,
  mark = price,
): PlayerPropRow {
  return {
    market_name: `Philadelphia vs Miami: ${stat}`,
    outcome_name: `${player}: ${line}+`,
    threshold: line,
    over_probability: price,
    pregame_mark: mark,
    source: "kalshi",
  } as unknown as PlayerPropRow;
}

// ---------------------------------------------------------------------------
// The constant is a measurement
// ---------------------------------------------------------------------------

describe("PROP_STRUCTURAL_CERTAINTY is measured, and measured to be TIGHTER", () => {
  it("is p95 of the same conviction distribution PROP_SCRIPT_CONVICTION took p90 of", () => {
    const conv = pooled()
      .map((r) => r.conviction)
      .sort((a, b) => a - b);
    expect(conv.length).toBe(183);
    const at = (p: number) => conv[Math.min(conv.length - 1, Math.floor(p * conv.length))];
    expect(at(0.9)).toBeCloseTo(PROP_SCRIPT_CONVICTION, 4);
    expect(at(0.95)).toBeCloseTo(PROP_STRUCTURAL_CERTAINTY, 4);
  });

  it("SUPPRESSION SITS TIGHTER THAN ESCALATION — the costs are not symmetric", () => {
    // A wrongly escalated row is a loud row on a page already being read. A
    // wrongly suppressed row is a market that is not on the rail at all. If
    // anyone ever loosens this below the escalation line, that asymmetry has
    // been inverted and this test is the one that says so.
    expect(PROP_STRUCTURAL_CERTAINTY).toBeGreaterThan(PROP_SCRIPT_CONVICTION);
  });

  it("selects 13 of 183 rows (7.1%) across the four production payloads", () => {
    const structural = pooled().filter((r) => r.structural);
    expect(structural.length).toBe(13);
    expect(structural.length / 183).toBeCloseTo(0.071, 3);
  });

  it("every one of the 13 is a DOWNWARD rung — the upward arm has no specimen", () => {
    // Recorded, not asserted as a property of the rule: the highest ladder rung
    // in this population carrying a higher sibling is 92.5%, below the line. The
    // upward arm is exercised synthetically further down and is labelled there.
    const structural = pooled().filter((r) => r.structural);
    expect(structural.every((r) => r.current < 0.5)).toBe(true);
  });
});

// ---------------------------------------------------------------------------
// Alex's bar
// ---------------------------------------------------------------------------

describe("the bar: position + threshold, never a bare probability cutoff", () => {
  it("THE 6.0% TRIPLE — same card, same stat, same threshold, same price, opposite fates", () => {
    const byLabel = new Map(candidates(DODGERS).map((r) => [r.label, r]));
    const beck = byLabel.get("Jordan Beck: 3+ hits")!;
    const tucker = byLabel.get("Kyle Tucker: 3+ hits")!;
    const fulford = byLabel.get("Braxton Fulford: 3+ hits")!;

    // The premise of the specimen — if the payload ever stops carrying three
    // 6.0% "3+ hits" rows, this test is measuring something else and must say so
    // rather than quietly passing on a weaker case.
    for (const row of [beck, tucker, fulford]) {
      expect(row.current).toBeCloseTo(0.06, 6);
      expect(row.threshold).toBe(3);
      expect(row.stat.toLowerCase()).toBe("hits");
    }

    expect(beck.structural).toBe(false);
    expect(tucker.structural).toBe(true);
    expect(fulford.structural).toBe(true);
  });

  it("a genuine standalone near-certain market view SURVIVES", () => {
    // Alex's clause, at its own number and on both sides of the flip.
    for (const price of [0.94, 0.06, 0.99, 0.01]) {
      const only = selectDivergenceRows({
        playerProps: [rung("Solo Player", "Hits", 2, price)],
        status: "scheduled",
      });
      expect(only.rows).toHaveLength(1);
      expect(only.rows[0].structural).toBe(false);
      expect(only.structuralSuppressed).toBe(0);
    }
  });

  it("the SAME price becomes structural the moment a lower rung joins it", () => {
    const lone = candidates([rung("Solo Player", "Hits", 5, 0.05)]);
    expect(lone[0].structural).toBe(false);

    const withLadder = candidates([
      rung("Solo Player", "Hits", 5, 0.05),
      rung("Solo Player", "Hits", 3, 0.3),
    ]);
    const top = withLadder.find((r) => r.threshold === 5)!;
    const base = withLadder.find((r) => r.threshold === 3)!;
    expect(top.structural).toBe(true);
    // The rung the market actually has a view about is untouched.
    expect(base.structural).toBe(false);
  });

  it("a near-certain rung at the BASE of its own ladder survives — position, not price", () => {
    // Both rungs priced identically at the floor. Only the upper one is
    // explained by its position; the lower one is where the ladder starts.
    const rows = candidates([
      rung("Floor Player", "Hits", 4, 0.05),
      rung("Floor Player", "Hits", 5, 0.05),
    ]);
    expect(rows.find((r) => r.threshold === 4)!.structural).toBe(false);
    expect(rows.find((r) => r.threshold === 5)!.structural).toBe(true);
  });

  it("across the whole population, no family is emptied — every ladder keeps a rung", () => {
    // The strong form of the clause above. If a family could be wholly
    // suppressed, "reachable in the expand" would be doing all the work.
    const families = new Map<string, DivergenceRow[]>();
    for (const r of pooled()) {
      const k = `${r.player}|${r.stat}`;
      families.set(k, [...(families.get(k) ?? []), r]);
    }
    for (const [key, family] of families) {
      expect(`${key}: ${family.filter((r) => !r.structural).length}`).not.toBe(
        `${key}: 0`,
      );
    }
  });

  it("THE UPWARD ARM (synthetic — zero specimens in production)", () => {
    const rows = candidates([
      rung("Ceiling Player", "Hits", 1, 0.96),
      rung("Ceiling Player", "Hits", 3, 0.2),
    ]);
    // 96% at the ladder's floor, with a rung still asked above it: arithmetic.
    expect(rows.find((r) => r.threshold === 1)!.structural).toBe(true);
    expect(rows.find((r) => r.threshold === 3)!.structural).toBe(false);

    // The same 96%, as the family's TOP rung, is not — nothing above it explains
    // it, so it is the market's own claim.
    const inverted = candidates([
      rung("Ceiling Player", "Hits", 3, 0.96),
      rung("Ceiling Player", "Hits", 1, 0.99),
    ]);
    expect(inverted.find((r) => r.threshold === 3)!.structural).toBe(false);
  });

  it("the certainty line is INCLUSIVE at its exact boundary", () => {
    // `0.06 - 0.5` is -0.44000000000000006, so a naive `>=` on conviction reads
    // the boundary row as below the line. Same class as TRAVEL_EPSILON, and the
    // real Tucker/Fulford rows sit on exactly this value.
    const onLine = candidates([
      rung("Edge Player", "Hits", 5, 0.06),
      rung("Edge Player", "Hits", 3, 0.4),
    ]);
    expect(onLine.find((r) => r.threshold === 5)!.structural).toBe(true);

    // And a genuine near-miss still misses.
    const nearMiss = candidates([
      rung("Edge Player", "Hits", 5, 0.065),
      rung("Edge Player", "Hits", 3, 0.4),
    ]);
    expect(nearMiss.find((r) => r.threshold === 5)!.structural).toBe(false);
  });
});

// ---------------------------------------------------------------------------
// What it does to the rail Alex was looking at
// ---------------------------------------------------------------------------

describe("the rail Alex ruled on", () => {
  it("removes the three rows he named from 15199886", () => {
    const before = candidates(PHILLIES).filter((r) => r.structural);
    expect(labels(before).sort()).toEqual([
      "Edmundo Sosa: 5+ hits + runs + rbis",
      "Javier Sanoja: 5+ hits + runs + rbis",
      "Kyle Stowers: 5+ hits + runs + rbis",
    ]);
    const rail = selectDivergenceRows({ playerProps: PHILLIES, status: "scheduled" });
    for (const gone of labels(before)) expect(labels(rail.rows)).not.toContain(gone);
    expect(rail.structuralSuppressed).toBe(3);
  });

  it("SUPERSEDED BY UX-P108, AND THE COST IS RECORDED: the two 92.5% rows lose their slots to movers", () => {
    // UX-P107 counted promoting `Braxton Fulford: 1+` and `Max Muncy (LAD): 1+`
    // — both marked 92.5%, both travelled 0.0 points — among its wins. Alex's
    // movement-first ruling takes both slots back, and this test is rewritten to
    // say so rather than deleted (ruling 049: a claim already committed is
    // corrected IN the record).
    const rail = selectDivergenceRows({ playerProps: DODGERS, status: "scheduled" });
    expect(labels(rail.rows)).not.toContain("Braxton Fulford: 1+ hits + runs + rbis");
    expect(labels(rail.rows)).not.toContain("Max Muncy (LAD): 1+ hits + runs + rbis");
    // …because five questions on this card actually moved, and they are the five.
    expect(rail.rows.every((r) => r.direction !== "flat")).toBe(true);

    // ── THE COHERENCE PROPERTY WEAKENS, MEASURED AND NOT GLOSSED ──────────────
    //
    // UX-P106 established that the script's five rows and the settled rail's
    // five biggest surprises overlap, and P107 measured that overlap at 2. Under
    // movement-first it is 1, and the direction is structural rather than
    // incidental: the settled key is |resolution − mark|, which is maximised by
    // exactly the near-certain marks this ruling stops leading with.
    //
    // Recorded at its NEW value, with the old one named. What survives is worth
    // saying: the single row that appears on both rails is Freddie Freeman's 3+,
    // the biggest surprise of the game (93.0 points) — kept because it also
    // travelled 35.5 points before first pitch, i.e. the movement tier caught the
    // game's best story on its own terms rather than by predicting it.
    const settled = selectDivergenceRows({ playerProps: DODGERS, status: "completed" });
    const scriptKeys = new Set(rail.rows.map((r) => r.key));
    const overlap = settled.rows.filter((r) => scriptKeys.has(r.key));
    expect(overlap).toHaveLength(1);
    expect(overlap[0].label).toBe("Freddie Freeman: 3+ hits + runs + rbis");
    expect(settled.rows[0].label).toBe("Freddie Freeman: 3+ hits + runs + rbis");
  });

  it("NOTHING IT SUPPRESSED TURNED OUT TO MATTER — the safety check, on a finished game", () => {
    // The cost of this rule is a market the user does not see on the rail. On
    // the one payload where the answers are known, every suppressed rung is
    // absent from the settled rail's top five surprises — the filter did not
    // hide a question the game later made interesting.
    const suppressed = new Set(
      candidates(DODGERS).filter((r) => r.structural).map((r) => r.key),
    );
    expect(suppressed.size).toBe(2);
    const settled = selectDivergenceRows({ playerProps: DODGERS, status: "completed" });
    expect(settled.rows.filter((r) => suppressed.has(r.key))).toHaveLength(0);
  });

  it("a card with no ladders at all is untouched", () => {
    const rail = selectDivergenceRows({ playerProps: BRAVES, status: "scheduled" });
    expect(rail.structuralSuppressed).toBe(0);
    expect(rail.rows).toHaveLength(2);
  });

  it("THE RESIDUAL IS GONE — and the test that recorded it is the one that says so", () => {
    // ** THIS ASSERTION USED TO RUN THE OTHER WAY. ** UX-P107 shipped it as
    // "THE RESIDUAL, RECORDED: the freed slots refill with rungs one point less
    // extreme", asserting >= 3 rows at conviction >= 0.4, and wrote in its own
    // body: "If a later change makes the Phillies rail lead with questions near
    // a coin flip, this test reds and the finding has been superseded, which is
    // the point."
    //
    // Alex's movement-first ruling is that change, and this test did red. It is
    // inverted rather than deleted, so the residual's whole life — found,
    // recorded, closed — stays legible in one place.
    const rail = selectDivergenceRows({ playerProps: PHILLIES, status: "scheduled" });
    expect(rail.rows.filter((r) => r.conviction >= 0.4)).toHaveLength(0);
    // The population itself did not change — the ranking did. Same 8 near-flip
    // questions, same continuum of rungs; they are simply no longer what the
    // rail leads with.
    expect(candidates(PHILLIES).filter((r) => r.conviction < 0.25)).toHaveLength(8);
    expect(candidates(PHILLIES).filter((r) => r.conviction >= 0.4).length).toBeGreaterThan(3);
  });
});

// ---------------------------------------------------------------------------
// Where they went
// ---------------------------------------------------------------------------

describe("suppressed rungs stay reachable — this is rail capacity, not a loss", () => {
  it.each(ALL)("%s: eligible and the detail view still carry every one", (_id, rows) => {
    const rail = selectDivergenceRows({ playerProps: rows, status: "scheduled" });
    const all = candidates(rows);
    expect(rail.eligible).toBe(all.length);
    // notSelected is the rail's own accounting of what it could not fit, and a
    // suppressed rung is inside it exactly like a row that ranked sixth.
    expect(rail.notSelected).toBe(all.length - rail.rows.length);
    for (const r of all.filter((x) => x.structural)) {
      expect(all.map((x) => x.key)).toContain(r.key);
    }
  });

  it("no suppressed rung is reported as a taxonomy loss", () => {
    for (const [, rows] of ALL) {
      const rail = selectDivergenceRows({ playerProps: rows, status: "scheduled" });
      const all = candidates(rows);
      expect(rail.nonBenignCount + rail.rows.length + rail.notSelected).toBe(
        all.length + rail.nonBenignCount,
      );
      expect(rail.dropped.some((d) => (d.reason as string) === "structural")).toBe(false);
    }
  });

  it("the expand still offers all 40 on Alex's card", () => {
    const html = renderToStaticMarkup(
      React.createElement(PropDivergenceRail, {
        playerProps: PHILLIES,
        status: "scheduled",
      }),
    );
    expect(html).toContain("See all 40 questions");
    expect(html).toContain("5 of 40");
  });
});

// ---------------------------------------------------------------------------
// Scope: the SCRIPT rail only
// ---------------------------------------------------------------------------

describe("the filter runs pregame and nowhere else", () => {
  it.each(["live", "in_progress", "completed", "closed"])(
    "%s: nothing is suppressed",
    (status) => {
      for (const [, rows] of ALL) {
        const rail = selectDivergenceRows({ playerProps: rows, status });
        expect(rail.structuralSuppressed).toBe(0);
      }
    },
  );

  it("SETTLED: a near-certain mark that was WRONG is the best row on the rail, not a hidden one", () => {
    // ── THIS TEST EXISTS BECAUSE A MUTATION SURVIVED ────────────────────────
    //
    // Deleting `pregame &&` from the selection filter passed the entire suite.
    // Two reasons, and the second is the dangerous one:
    //
    //   1. `structuralSuppressed` is ITSELF pregame-gated, so the state tests
    //      above read 0 whether or not the filter ran. A counter cannot witness
    //      the thing it is gated on.
    //   2. No row on any of the four settled payloads happens to be structural
    //      by the post-game basis, so no real fixture could catch it either.
    //
    // And the leak would be severe rather than cosmetic. Post-game the basis is
    // `pregameMark`, and #2011's whole finding is that THE BIGGEST SURPRISES ARE
    // THE NEAR-CERTAIN MARKS THAT WERE WRONG — Fulford 92.5% and Castro 17%. A
    // structural filter running post-game would delete precisely the rows the
    // settled rail exists to show.
    const rows: PlayerPropRow[] = [
      // marked 4% with a 2+ rung below it — structural by position and price
      rung("Shock", "Hits", 4, 0.04),
      rung("Shock", "Hits", 2, 0.4),
      rung("Ordinary", "Hits", 2, 0.5),
    ];
    const pre = candidates(rows);
    expect(pre.find((r) => r.threshold === 4)!.structural).toBe(true);

    // The same rung, post-game, with the flag computed off `pregameMark`.
    const settledRows = rows.map((r) =>
      r.threshold === 4
        ? ({ ...r, outcome_name: "Shock: 4+", hit: true } as unknown as PlayerPropRow)
        : r,
    );
    const settled = selectDivergenceRows({
      playerProps: settledRows,
      status: "completed",
    });
    const shock = settled.rows.find((r) => r.label === "Shock: 4+ hits");
    expect(shock).toBeDefined();
    // 96 points of surprise: it was marked 4% and it happened. This is the row.
    expect(shock!.surprise).toBeCloseTo(0.96, 6);
    expect(settled.rows[0].label).toBe("Shock: 4+ hits");
  });

  it("LIVE: a rung structural by its pregame mark still leads once the price moves", () => {
    // The in-game half of the same hole. `basis` is `pregameMark` here too, so a
    // leaked filter hides the row with the biggest line move on the card.
    const rows: PlayerPropRow[] = [
      rung("Mover", "Hits", 5, 0.04, 0.62),
      rung("Mover", "Hits", 3, 0.4),
    ];
    expect(candidates(rows).find((r) => r.threshold === 5)!.structural).toBe(true);
    const live = selectDivergenceRows({ playerProps: rows, status: "live" });
    expect(labels(live.rows)).toContain("Mover: 5+ hits");
    expect(live.rows[0].label).toBe("Mover: 5+ hits");
    expect(live.rows[0].travel).toBeCloseTo(0.58, 6);
  });

  it("a rung suppressed pregame still leads the in-game rail once it moves", () => {
    // Same question, same ladder. Pregame it is arithmetic; in-game a 30-point
    // move is the entire story and the rail must not still be hiding it.
    const ladder = [
      rung("Mover", "Hits", 3, 0.35),
      rung("Mover", "Hits", 5, 0.05, 0.35),
    ];
    const script = selectDivergenceRows({ playerProps: ladder, status: "scheduled" });
    expect(labels(script.rows)).not.toContain("Mover: 5+ hits");

    const live = selectDivergenceRows({ playerProps: ladder, status: "live" });
    expect(labels(live.rows)).toContain("Mover: 5+ hits");
    expect(live.structuralSuppressed).toBe(0);
  });

  it("the detail view lists structural rungs in EVERY state", () => {
    const detail = selectDivergenceDetail({ playerProps: PHILLIES, status: "scheduled" });
    const all = [...detail.offScript, ...detail.onScript, ...detail.ungraded];
    expect(all.filter((r) => r.structural)).toHaveLength(3);
    expect(all).toHaveLength(40);
  });
});

// ---------------------------------------------------------------------------
// The two loop decisions, made mutation-visible
// ---------------------------------------------------------------------------

describe("selection-loop mechanics", () => {
  it("CONTINUE, NOT BREAK — a structural row at the top does not truncate the rail", () => {
    // Structural rungs are the MOST convinced rows on a card, so they cluster at
    // the top of a conviction order. A `break` here empties the rail on exactly
    // the cards the rule was written for.
    const rows = [
      rung("Ladder Guy", "Hits", 5, 0.04),
      rung("Ladder Guy", "Hits", 3, 0.3),
      rung("Other Guy", "Hits", 2, 0.62),
    ];
    const rail = selectDivergenceRows({ playerProps: rows, status: "scheduled" });
    expect(rail.structuralSuppressed).toBe(1);
    expect(labels(rail.rows).sort()).toEqual(["Ladder Guy: 3+ hits", "Other Guy: 2+ hits"]);
  });

  it("A SUPPRESSED RUNG DOES NOT SPEND ITS PLAYER'S CAP", () => {
    // Three structural rungs ahead of two real questions from the same player.
    // Charged against RAIL_MAX_PER_PLAYER, the two real ones never render — the
    // rule would have silenced the player in whose name it fired.
    //
    // ** THE TWO REAL QUESTIONS ARE NOW TWO DIFFERENT STATS, AND THAT IS THE
    // POINT OF THE EDIT. ** UX-P107 wrote this fixture with both survivors on
    // the Hits ladder, which UX-P108's one-per-ladder cap correctly reduces to
    // one — so the original fixture could no longer distinguish "the player cap
    // was spent by a suppressed rung" (the defect under test) from "the ladder
    // cap fired" (working as ruled). Two stats separate them again: the player
    // cap is the only thing that could stop the second row, so if a suppressed
    // rung ever charges against it, this reds.
    const rows = [
      rung("Deep Ladder", "Hits", 6, 0.03),
      rung("Deep Ladder", "Hits", 5, 0.04),
      rung("Deep Ladder", "Hits", 4, 0.05),
      rung("Deep Ladder", "Hits", 3, 0.22),
      rung("Deep Ladder", "Home Runs", 2, 0.7),
    ];
    const rail = selectDivergenceRows({ playerProps: rows, status: "scheduled" });
    expect(rail.structuralSuppressed).toBe(3);
    expect(labels(rail.rows).sort()).toEqual([
      "Deep Ladder: 2+ home runs",
      "Deep Ladder: 3+ hits",
    ]);
  });

  it("ONE RUNG PER LADDER — and the suppressed rungs ahead of it do not take the slot either", () => {
    // Alex's cap, on the same fixture shape the test above uses, with both
    // survivors back on ONE ladder. Exactly one of them reaches the rail, and it
    // is the higher-ranked one — not the first rung the loop happened to walk
    // past, which is what a cap charged before the structural floor would give.
    const rows = [
      rung("Deep Ladder", "Hits", 6, 0.03),
      rung("Deep Ladder", "Hits", 5, 0.04),
      rung("Deep Ladder", "Hits", 4, 0.05),
      rung("Deep Ladder", "Hits", 3, 0.22),
      rung("Deep Ladder", "Hits", 2, 0.7),
    ];
    const rail = selectDivergenceRows({ playerProps: rows, status: "scheduled" });
    expect(rail.structuralSuppressed).toBe(3);
    // The 3+ rung, not the 2+ one. Neither has moved, so both sit in the
    // conviction tier, where 3+ (priced 22%, conviction 0.28) outranks 2+
    // (priced 70%, conviction 0.20) — the cap takes the rail's OWN top-ranked
    // survivor rather than whichever rung the loop reached first.
    expect(labels(rail.rows)).toEqual(["Deep Ladder: 3+ hits"]);
    // Non-vacuity in the other direction (gotcha #43): the rung it did NOT show
    // is still eligible and still reachable through the expand.
    expect(rail.eligible).toBe(5);
    expect(labels(candidates(rows))).toContain("Deep Ladder: 2+ hits");
  });

  it("THE DOUBLE-TURNER ROWS ALEX NAMED ARE GONE FROM HIS OWN CARD", () => {
    // The shape the cap was ruled for, on the real payload. UX-P107's rail
    // carried `Trea Turner: 4+ hits` at row 4 and `Trea Turner: 3+ hits` at row
    // 5 — one ladder, one point apart, neither having moved.
    const rail = selectDivergenceRows({ playerProps: PHILLIES, status: "scheduled" });
    const ladders = rail.rows.map((r) => `${r.player}|${r.stat}`);
    expect(new Set(ladders).size).toBe(ladders.length);
    expect(labels(rail.rows).filter((l) => l.startsWith("Trea Turner"))).toHaveLength(0);
    // Both Turner rungs are still eligible; this is rail capacity, not a loss.
    expect(labels(candidates(PHILLIES))).toEqual(
      expect.arrayContaining(["Trea Turner: 4+ hits", "Trea Turner: 3+ hits"]),
    );
  });

  it("EVERY CARD: one rung per ladder, on all four production payloads", () => {
    for (const [id, rows] of ALL) {
      const rail = selectDivergenceRows({ playerProps: rows, status: "scheduled" });
      const ladders = rail.rows.map((r) => `${r.player}|${r.stat}`);
      expect(`${id}: ${new Set(ladders).size}`).toBe(`${id}: ${ladders.length}`);
    }
  });
});

// ---------------------------------------------------------------------------
// Honest-empty (ruling 027) — the pregame twin of `ungraded`
// ---------------------------------------------------------------------------

describe("when the rule empties the rail, the page says so", () => {
  const allStructural: PlayerPropRow[] = [
    rung("A Player", "Hits", 4, 0.02),
    rung("A Player", "Hits", 2, 0.05),
  ];

  it("a floor-priced ladder does NOT empty — its base rung always survives", () => {
    // The near-miss of the case below, and the reason the empty case is rare:
    // on the downward arm the family's lowest rung has nothing beneath it to be
    // explained by, so it is never suppressed however cheap it is.
    const rail = selectDivergenceRows({
      playerProps: [
        rung("A Player", "Hits", 4, 0.02),
        rung("A Player", "Hits", 2, 0.04),
      ],
      status: "scheduled",
    });
    expect(labels(rail.rows)).toEqual(["A Player: 2+ hits"]);
    expect(rail.emptyReason).toBeNull();
    expect(rail.structuralSuppressed).toBe(1);
  });

  it("A CARD THE RULE CAN EMPTY: a two-rung ladder straddling the flip", () => {
    // The one shape that suppresses both ends of a family — near-certain YES at
    // the base with a rung above it, near-certain NO at the top with a rung
    // below it. No specimen in production; constructed here because a filter
    // with no escape hatch must be shown behaving at its own limit.
    const rows = [
      rung("Straddle", "Hits", 1, 0.97),
      rung("Straddle", "Hits", 6, 0.02),
    ];
    const rail = selectDivergenceRows({ playerProps: rows, status: "scheduled" });
    expect(rail.rows).toHaveLength(0);
    expect(rail.emptyReason).toBe("structural");
    expect(rail.eligible).toBe(2);
    expect(rail.notSelected).toBe(2);
    expect(rail.structuralSuppressed).toBe(2);

    const html = renderToStaticMarkup(
      React.createElement(PropDivergenceRail, { playerProps: rows, status: "scheduled" }),
    );
    // It renders, rather than vanishing — a silent gap is indistinguishable from
    // missing data, which is the complaint V3 exists to answer.
    expect(html).toContain("rungs of a bigger ladder");
    expect(html).toContain("See all 2 questions");
    expect(html).toContain("The script");
  });

  it("an empty-for-another-reason pregame card is still `clean`, not `structural`", () => {
    const rail = selectDivergenceRows({ playerProps: [], status: "scheduled" });
    expect(rail.emptyReason).toBe("none");
    expect(rail.structuralSuppressed).toBe(0);

    const unreadable = selectDivergenceRows({
      playerProps: [
        { market_name: "", outcome_name: "", threshold: 1, over_probability: 0.5 } as unknown as PlayerPropRow,
      ],
      status: "scheduled",
    });
    expect(unreadable.emptyReason).toBe("unreadable");
  });

  it("the same all-structural card renders normally once the game starts", () => {
    const html = renderToStaticMarkup(
      React.createElement(PropDivergenceRail, {
        playerProps: allStructural,
        status: "live",
      }),
    );
    expect(html).not.toContain("rungs of a bigger ladder");
  });
});
