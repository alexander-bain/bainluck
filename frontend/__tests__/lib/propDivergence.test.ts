/**
 * THE DIVERGENCE rail — selection, escalation, and the disappearance taxonomy.
 *
 * UX-P098 (UX-AMBITION-1 slice 1). The fixture is a REAL production payload
 * (`GET /api/events/15199886/game-markets`, Marlins @ Phillies, captured live
 * 2026-08-18), and it is load-bearing rather than decorative: it carries BOTH
 * provider shapes at once —
 *
 *   Polymarket  "Alec Bohm: Home Runs O/U 0.5"   / outcome "Over" | "Under"
 *   Kalshi      "Philadelphia vs Miami: Hits"    / outcome "Edmundo Sosa: 2+"
 *
 * — which is precisely the both-directions guard gotcha #43 requires: the rail
 * must populate on the Polymarket shape (the #1976 §5 class, fixed in UX-P097)
 * WITHOUT collapsing the Kalshi shape, where one market name covers many
 * distinct players and only the outcome tells them apart (#1639).
 */

import {
  PROP_SURPRISE_TRAVEL,
  RAIL_MAX_ROWS,
  RAIL_MAX_PER_PLAYER,
  selectDivergenceRows,
  selectDivergenceDetail,
  divergenceSentence,
  isBenignDrop,
  isSettledStatus,
} from "@/lib/propDivergence";
import type { PlayerPropRow } from "@/lib/playerPropsGrouping";

import realPayload from "../fixtures/eventPlayerProps.15199886.json";

const REAL_ROWS = realPayload as unknown as PlayerPropRow[];

/** Minimal Polymarket-shaped row (player in the market name, bare Over/Under). */
function polyRow(
  player: string,
  stat: string,
  line: number,
  pregame: number,
  current: number,
  outcome: "Over" | "Under" = "Over",
): PlayerPropRow {
  return {
    market_name: `${player}: ${stat} O/U ${line}`,
    outcome_name: outcome,
    threshold: line,
    over_probability: current,
    pregame_mark: pregame,
    source: "polymarket",
  } as PlayerPropRow;
}

/** Minimal Kalshi-shaped row (player in the OUTCOME, matchup in the market). */
function kalshiRow(
  player: string,
  stat: string,
  line: number,
  pregame: number,
  current: number,
): PlayerPropRow {
  return {
    market_name: `Philadelphia vs Miami: ${stat}`,
    outcome_name: `${player}: ${line}+`,
    threshold: line,
    over_probability: current,
    pregame_mark: pregame,
    source: "kalshi",
  } as PlayerPropRow;
}

describe("the measured surprise threshold", () => {
  it("is p90 of the measured travel distribution, not a round preference", () => {
    // Recorded so a future edit has to confront the measurement. p90 = 21.0 pts
    // over 143 production props; 0.20 admits 11% of them.
    expect(PROP_SURPRISE_TRAVEL).toBe(0.2);
  });

  it("escalates at the threshold and not below it", () => {
    const res = selectDivergenceRows({
      playerProps: [
        polyRow("Big Mover", "Hits", 1.5, 0.1, 0.1 + PROP_SURPRISE_TRAVEL),
        polyRow("Small Mover", "Hits", 1.5, 0.1, 0.1 + PROP_SURPRISE_TRAVEL - 0.01),
      ],
      status: "scheduled",
    });
    const big = res.rows.find((r) => r.player === "Big Mover")!;
    const small = res.rows.find((r) => r.player === "Small Mover")!;

    // V2: the sentence is an ESCALATION. Every row is a bar; only the
    // surprising one additionally gets prose.
    expect(big.surprising).toBe(true);
    expect(big.sentence).toBeTruthy();
    expect(small.surprising).toBe(false);
    expect(small.sentence).toBeNull();
  });
});

describe("V1 — five live questions", () => {
  it("caps the rail at five rows, ranked by travel", () => {
    const rows = Array.from({ length: 9 }, (_, i) =>
      polyRow(`Player ${i}`, "Hits", 1.5, 0.5, 0.5 + i * 0.03),
    );
    const res = selectDivergenceRows({ playerProps: rows, status: "scheduled" });

    expect(res.rows).toHaveLength(RAIL_MAX_ROWS);
    const travels = res.rows.map((r) => r.travel);
    expect([...travels].sort((a, b) => b - a)).toEqual(travels); // descending
    expect(res.rows[0].player).toBe("Player 8"); // the biggest mover leads
    // Capacity is NOT a taxonomy loss — those props are reachable via the expand.
    expect(res.notSelected).toBe(4);
    expect(res.nonBenignCount).toBe(0);
  });

  it("caps a single player at two rows so one player cannot own the rail", () => {
    const rows = [
      polyRow("Hot Hitter", "Hits", 1.5, 0.1, 0.9),
      polyRow("Hot Hitter", "Home Runs", 0.5, 0.1, 0.85),
      polyRow("Hot Hitter", "Strikeouts", 3.5, 0.1, 0.8),
      polyRow("Someone Else", "Hits", 1.5, 0.1, 0.4),
    ];
    const res = selectDivergenceRows({ playerProps: rows, status: "scheduled" });

    const hot = res.rows.filter((r) => r.player === "Hot Hitter");
    expect(hot).toHaveLength(RAIL_MAX_PER_PLAYER);
    // The cap must yield the slot to another player, not shrink the rail.
    expect(res.rows.map((r) => r.player)).toContain("Someone Else");
  });

  it("renders fewer than five cleanly — a short rail is a normal state", () => {
    const res = selectDivergenceRows({
      playerProps: [polyRow("Only One", "Hits", 1.5, 0.2, 0.5)],
      status: "scheduled",
    });
    expect(res.rows).toHaveLength(1);
    expect(res.emptyReason).toBeNull();
    expect(res.notSelected).toBe(0);
  });
});

describe("the Over/Under pair is ONE question", () => {
  it("collapses the two legs of a Polymarket prop into a single row", () => {
    const res = selectDivergenceRows({
      playerProps: [
        polyRow("Alec Bohm", "Home Runs", 0.5, 0.05, 0.4, "Over"),
        polyRow("Alec Bohm", "Home Runs", 0.5, 0.05, 0.4, "Under"),
      ],
      status: "scheduled",
    });
    expect(res.rows).toHaveLength(1);
    expect(res.eligible).toBe(1);
  });

  it("does NOT collapse distinct players who share a market name and line (#1639)", () => {
    // The Kalshi shape: one market name, one threshold, two DIFFERENT people.
    // A dedupe keyed on market_name+threshold deletes one of them silently.
    const res = selectDivergenceRows({
      playerProps: [
        kalshiRow("Edmundo Sosa", "Hits", 2, 0.36, 0.7),
        kalshiRow("Bryce Harper", "Hits", 2, 0.4, 0.75),
      ],
      status: "scheduled",
    });
    expect(res.rows).toHaveLength(2);
    expect(res.rows.map((r) => r.player).sort()).toEqual([
      "Bryce Harper",
      "Edmundo Sosa",
    ]);
  });
});

describe("V3 — the disappearance taxonomy", () => {
  it("hides a no-price row silently and counts it as benign", () => {
    const noPrice = {
      market_name: "Ghost Player: Hits O/U 1.5",
      outcome_name: "Over",
      threshold: 1.5,
      over_probability: null,
      pregame_mark: null,
      source: "polymarket",
    } as unknown as PlayerPropRow;

    const res = selectDivergenceRows({
      playerProps: [polyRow("Real Player", "Hits", 1.5, 0.2, 0.5), noPrice],
      status: "scheduled",
    });

    const drop = res.dropped.find((d) => d.reason === "no_real_price")!;
    expect(drop.count).toBe(1);
    expect(drop.benign).toBe(true);
    // Benign losses must not inflate the number that demands an explanation.
    expect(res.nonBenignCount).toBe(0);
  });

  it("surfaces an unreadable row as UNKNOWN rather than claiming it never traded", () => {
    // Fable's amendment: a reason that reads UNKNOWN renders AS unknown, not as
    // silence, and never as a confident "no trading".
    const unnamed = {
      market_name: "",
      outcome_name: "",
      threshold: null,
      over_probability: 0.5,
      pregame_mark: 0.3,
    } as unknown as PlayerPropRow;

    const res = selectDivergenceRows({ playerProps: [unnamed], status: "scheduled" });

    const drop = res.dropped.find((d) => d.reason === "unknown")!;
    expect(drop.count).toBe(1);
    expect(drop.benign).toBe(false);
    expect(res.nonBenignCount).toBe(1);
    // Nothing survived AND a guard caught something -> unreadable, not clean.
    expect(res.emptyReason).toBe("unreadable");
  });

  it("distinguishes a genuine absence from a poisoned one", () => {
    expect(selectDivergenceRows({ playerProps: [] }).emptyReason).toBe("none");
    expect(selectDivergenceRows({ playerProps: null }).emptyReason).toBe("none");

    // Priced rows that simply carry no marks: benign, nothing survived.
    const clean = selectDivergenceRows({
      playerProps: [
        {
          market_name: "Someone: Hits O/U 1.5",
          outcome_name: "Over",
          threshold: 1.5,
          over_probability: null,
          pregame_mark: null,
        } as unknown as PlayerPropRow,
      ],
    });
    expect(clean.emptyReason).toBe("clean");
    expect(clean.nonBenignCount).toBe(0);
  });

  it("classifies only reasons 1 and 2 as benign", () => {
    expect(isBenignDrop("no_real_price")).toBe(true);
    expect(isBenignDrop("outside_band")).toBe(true);
    expect(isBenignDrop("misclassified")).toBe(false);
    expect(isBenignDrop("wrong_game")).toBe(false);
    expect(isBenignDrop("ungraded")).toBe(false);
    expect(isBenignDrop("unknown")).toBe(false);
  });
});

describe("the label and the sentence", () => {
  it("asks the question and never shows the provider string", () => {
    const res = selectDivergenceRows({
      playerProps: [polyRow("Janson Junk", "Strikeouts", 3.5, 0.2, 0.6)],
      status: "scheduled",
    });
    const row = res.rows[0];
    // "3.5" reads as "4+": Over on a half-point line means the next whole unit.
    expect(row.label).toBe("Janson Junk: 4+ strikeouts");
    expect(row.label).not.toContain("O/U");
    expect(row.label).not.toContain("vs");
  });

  it("is deterministic arithmetic over two numbers already on the row", () => {
    expect(
      divergenceSentence("Juan Soto", "Juan Soto: 2+ hits", 0.1, 0.32, false),
    ).toBe("Soto's 2+ hits opened at 10% — it's 32% now.");
  });

  it("states the OUTCOME on a settled game, never the last traded price", () => {
    // UX-P105 (#2011). This test used to assert `finished at 60%` — a PRICE
    // read out with the grammar of a result. Alex's verdict on the expand
    // captures was that post-game it "doesn't make any sense", and the
    // measurement behind it is worse than cosmetic: the price is also what the
    // rail RANKED by, so a question that resolved against a heavy favourite
    // without ever trading sorted to the bottom.
    const graded = polyRow("Juan Soto", "Hits", 1.5, 0.1, 0.6) as PlayerPropRow & {
      hit?: boolean;
    };
    graded.hit = true; // the "Over" leg hit: the over resolved YES

    const live = selectDivergenceRows({
      playerProps: [graded],
      status: "scheduled",
    }).rows[0];
    const done = selectDivergenceRows({
      playerProps: [graded],
      status: "completed",
    }).rows[0];

    expect(live.settled).toBe(false);
    expect(live.sentence).toContain("now.");
    expect(live.resolution).toBeNull();

    expect(done.settled).toBe(true);
    expect(done.resolution).toBe(1);
    expect(done.surprise).toBeCloseTo(0.9, 6); // |1 - 0.10|, not |0.60 - 0.10|
    expect(done.sentence).toBe("Soto's 2+ hits was marked 10% — and it hit.");
    expect(done.sentence).not.toContain("finished at");
    // Travel is still computed — it is simply no longer what settles the rank.
    expect(done.travel).toBeCloseTo(0.5, 6);
  });

  it("withholds the outcome when the settled row carries no typed verdict", () => {
    const done = selectDivergenceRows({
      playerProps: [polyRow("Juan Soto", "Hits", 1.5, 0.1, 0.6)],
      status: "completed",
    });
    // The rail will not spend a slot on a question with nothing to say; it
    // reports the honest-empty instead, and the expand still lists the row.
    expect(done.rows).toHaveLength(0);
    expect(done.emptyReason).toBe("ungraded");
    expect(done.ungraded).toBe(1);
    expect(done.eligible).toBe(1);

    const detail = selectDivergenceDetail({
      playerProps: [polyRow("Juan Soto", "Hits", 1.5, 0.1, 0.6)],
      status: "completed",
    });
    expect(detail.ungraded).toHaveLength(1);
    const row = detail.ungraded[0];
    expect(row.settled).toBe(true);
    expect(row.resolution).toBeNull();
    expect(row.surprise).toBeNull();
    expect(row.sentence).toBeNull();
    expect(row.grade?.state).toBe("WITHHOLD");
  });

  it("reads settledness from the standing status vocabulary", () => {
    expect(isSettledStatus("completed")).toBe(true);
    expect(isSettledStatus("CLOSED")).toBe(true);
    expect(isSettledStatus("live")).toBe(false);
    expect(isSettledStatus(null)).toBe(false);
  });
});

describe("direction", () => {
  it("names which way the question travelled, and calls a flat prop flat", () => {
    const res = selectDivergenceRows({
      playerProps: [
        polyRow("Up Guy", "Hits", 1.5, 0.2, 0.6),
        polyRow("Down Guy", "Hits", 1.5, 0.6, 0.2),
        polyRow("Flat Guy", "Hits", 1.5, 0.205, 0.205),
      ],
      status: "scheduled",
    });
    const by = (n: string) => res.rows.find((r) => r.player === n)!;
    expect(by("Up Guy").direction).toBe("over");
    expect(by("Down Guy").direction).toBe("under");
    expect(by("Flat Guy").direction).toBe("flat");
  });
});

describe("the real production payload (gotcha #43, both directions)", () => {
  const res = selectDivergenceRows({ playerProps: REAL_ROWS, status: "live" });

  it("populates the rail on a game carrying the Polymarket shape", () => {
    // The #1976 §5 class. Before UX-P097 these rows never reached the client
    // at all; a rail that renders nothing here would be that bug returning.
    expect(res.rows.length).toBeGreaterThan(0);
    expect(res.rows.length).toBeLessThanOrEqual(RAIL_MAX_ROWS);
    expect(res.emptyReason).toBeNull();
  });

  it("keeps the Kalshi-shaped players distinct instead of collapsing them", () => {
    // 42 raw rows -> 40 real questions: exactly two Polymarket Over/Under PAIRS
    // collapse (Bohm's home runs, Junk's strikeouts) and nothing else does.
    //
    // This number is the whole point of the test. Keying the dedupe on
    // `market_name + threshold` instead of the parsed identity yields ELEVEN —
    // because the many "Philadelphia vs Miami: Hits" rows are different PEOPLE
    // sharing one market name — and eleven is what a first pass at this fixture
    // produced. Twenty-nine distinct player questions would have vanished with
    // no guard firing: #1639's "17 distinct players collapsed into ONE card",
    // re-entered from the client side.
    expect(res.eligible).toBe(40);
    expect(res.nonBenignCount).toBe(0);
  });

  it("finds the one real mover and escalates only that row", () => {
    // Schwarber's 1+ HR travelled 27.7 pts (0.27 -> 0.5467); every other prop
    // on this payload moved 1.0 pt or less. Exactly the bimodality the
    // threshold was measured against.
    const top = res.rows[0];
    expect(top.player).toBe("Kyle Schwarber");
    expect(top.travel).toBeCloseTo(0.2767, 3);
    expect(top.surprising).toBe(true);
    expect(top.sentence).toBe(
      "Schwarber's 1+ home runs opened at 27% — it's 55% now.",
    );

    // One sentence, four bare bars — the shape V2 describes.
    expect(res.rows.filter((r) => r.surprising)).toHaveLength(1);
  });
});
