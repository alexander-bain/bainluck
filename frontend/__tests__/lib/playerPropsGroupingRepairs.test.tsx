// UX-P058 — the C277 repairs to UX-P056's guard, and the controls that prove
// each one is doing something.
//
// Three defects, three shapes of proof:
//
//   1. ATOMIC ROW COMMIT — a row that throws LATE must contribute nothing at all.
//      The original guard bounded the blast radius of a throw but not its PARTIAL
//      WRITES: the player and stat entries were committed near the top and a
//      dozen reads followed, so a late throw left a stat with ZERO RUNGS. That is
//      #1722's own precondition, manufactured by the guard written to contain it.
//
//   2. POISON IS NOT ABSENCE — a section whose every row was dropped must SAY so,
//      not render as a game with no props (gotcha #53, client side).
//
//   3. IDENTITY IS NAME + AUTHORITATIVE SIDE — same-name opponents must not merge
//      into one card, and one real player must NOT fragment into two.
//
// The throwing rows below use getters rather than odd values, because that is the
// only way to make a read fail at a chosen POINT in the sequence — which is the
// whole question for atomicity.

import { renderToStaticMarkup } from "react-dom/server";
import React from "react";
import { groupPlayerProps, type PlayerPropRow } from "../../lib/playerPropsGrouping";
import PlayerPropsDashboard from "../../components/PlayerPropsDashboard";

/** A healthy row for "Ana Diaz", 2+ Hits. */
function healthyRow(over: Partial<PlayerPropRow> = {}): PlayerPropRow {
  return {
    market_name: "Reds vs Cubs: Hits",
    outcome_name: "Ana Diaz: 2+",
    threshold: 2,
    over_probability: 0.55,
    movement: 0.01,
    source: "kalshi",
    actual: null,
    hit: null,
    is_winner: null,
    resolution_source: null,
    ...over,
  };
}

/** The same row, but a chosen field throws when read. */
function rowThrowingOn(field: keyof PlayerPropRow): PlayerPropRow {
  const row = healthyRow();
  Object.defineProperty(row, field, {
    get() {
      throw new Error(`hostile ${String(field)}`);
    },
    enumerable: true,
    configurable: true,
  });
  return row;
}

describe("1. atomic row commit — a late throw contributes NOTHING", () => {
  // Each of these fields is read AFTER the point where the pre-repair code had
  // already written the player and the stat into the map.
  for (const field of ["source", "resolution_source", "hit"] as const) {
    it(`a row throwing on \`${field}\` drops exactly one row and creates no player`, () => {
      const { players, dropped } = groupPlayerProps({
        playerProps: [rowThrowingOn(field)],
        other: [],
      });

      // NO CONTRIBUTION. Before the repair this produced a player carrying a
      // stat with zero rungs — a phantom card asserting data we never read.
      expect(players).toEqual([]);
      // ...and ONE drop, so the failure is recorded rather than swallowed.
      expect(dropped).toHaveLength(1);
      expect(dropped[0].kind).toBe("player_prop_row");
      expect(dropped[0].at).toBe("0");
      expect(dropped[0].message).toContain(field);
    });
  }

  it("a hostile row costs only itself — healthy siblings still render (gotcha #42)", () => {
    const { players, dropped } = groupPlayerProps({
      playerProps: [
        healthyRow(),
        rowThrowingOn("source"),
        healthyRow({ outcome_name: "Bo Vance: 1+", threshold: 1 }),
      ],
      other: [],
    });
    expect(dropped).toHaveLength(1);
    expect(players.map((p) => p.name).sort()).toEqual(["Ana Diaz", "Bo Vance"]);
  });

  it("a late throw does not corrupt a stat an EARLIER healthy row already built", () => {
    // The existing-rung path: row 0 builds the 2+ rung, row 1 is the same
    // player/stat/threshold and throws while being merged into it.
    const { players, dropped } = groupPlayerProps({
      playerProps: [healthyRow(), rowThrowingOn("hit")],
      other: [],
    });
    expect(dropped).toHaveLength(1);
    expect(players).toHaveLength(1);
    const stat = players[0].stats[0];
    // Exactly the healthy row's contribution, unchanged and un-doubled.
    expect(stat.shape).toBe("line");
    expect(stat.threshold).toBe(2);
    expect(stat.overProb).toBe(0.55);
    expect(stat.sources).toBe(1);
  });

  it("a rejected row leaves NO PRICE behind on a healthy rung", () => {
    // THE SHARPEST ATOMICITY CASE, and the reason the others are not enough.
    //
    // `players).toEqual([])` alone is a weak assertion here: the downstream
    // zero-rung `continue` and `stats.length === 0` skip already sweep away a
    // phantom player, so a partial write can be invisible in the player list.
    // What is NOT swept away is a partial write onto a rung a HEALTHY row
    // already built.
    //
    // Pre-repair order: the rung merge (`over_probability`) ran BEFORE the
    // `source` read, so this hostile row's 0.9 was written onto the existing
    // rung and only then did the row fail — leaving the card showing a price
    // from a row the guard rejected. That is worse than a dropped row: it is a
    // number on screen that no accepted row ever supplied.
    const hostile = healthyRow({ over_probability: 0.9 });
    Object.defineProperty(hostile, "source", {
      get() {
        throw new Error("hostile source");
      },
      enumerable: true,
      configurable: true,
    });

    const { players, dropped } = groupPlayerProps({
      playerProps: [healthyRow(), hostile],
      other: [],
    });
    expect(dropped).toHaveLength(1);
    expect(players).toHaveLength(1);
    expect(players[0].stats[0].overProb).toBe(0.55);
  });

  it("NO stat is ever created with zero rungs — #1722's precondition", () => {
    const { players } = groupPlayerProps({
      playerProps: [rowThrowingOn("source"), healthyRow()],
      other: [],
    });
    for (const p of players) {
      for (const s of p.stats) {
        const rungCount = s.shape === "ladder" ? (s.rungs?.length ?? 0) : 1;
        expect(rungCount).toBeGreaterThan(0);
      }
    }
  });
});

describe("2. poison is not absence", () => {
  it("no rows at all reports `none`", () => {
    expect(groupPlayerProps({ playerProps: [], other: [] }).emptyReason).toBe("none");
  });

  it("rows that group to nothing WITHOUT a drop reports `clean`", () => {
    // Benign: a row with no threshold is skipped, not dropped.
    const { players, dropped, emptyReason } = groupPlayerProps({
      playerProps: [healthyRow({ threshold: null })],
      other: [],
    });
    expect(players).toEqual([]);
    expect(dropped).toEqual([]);
    expect(emptyReason).toBe("clean");
  });

  it("rows that ALL drop reports `unreadable`", () => {
    const { players, dropped, emptyReason } = groupPlayerProps({
      playerProps: [rowThrowingOn("source")],
      other: [],
    });
    expect(players).toEqual([]);
    expect(dropped).toHaveLength(1);
    expect(emptyReason).toBe("unreadable");
  });

  it("a surviving player reports no empty reason at all", () => {
    expect(groupPlayerProps({ playerProps: [healthyRow()], other: [] }).emptyReason).toBeNull();
  });

  // --- The SSR half: the state must actually REACH the screen. ---
  //
  // The pre-repair caller returned `null` for every empty, so the poisoned case
  // drew nothing and UX-P056's "N props couldn't be read" line — written for
  // exactly this case — sat after that return and was unreachable.

  const dash = (rows: PlayerPropRow[]) =>
    renderToStaticMarkup(
      <PlayerPropsDashboard
        data={{ player_props: rows, other: [] } as never}
        homeTeam="Cubs"
        awayTeam="Reds"
      />
    );

  it("SSR: a fully poisoned section RENDERS and says it could not be read", () => {
    const html = dash([rowThrowingOn("source")]);
    expect(html).toContain("Player Props");
    expect(html).toContain("couldn&#x27;t be read");
  });

  it("SSR: a genuinely propless game still renders NOTHING", () => {
    // The other direction (gotcha #43). The notice must not become the new
    // always-on empty state, which would put a worry on every propless game.
    expect(dash([])).toBe("");
  });

  it("SSR: the poisoned state is BOUNDED — no row list, no error text", () => {
    const html = dash([rowThrowingOn("source"), rowThrowingOn("hit")]);
    // The guard's internal message must never reach the user.
    expect(html).not.toContain("hostile");
    expect(html).not.toContain("Error");
    // One notice, not one per dropped row.
    expect(html.match(/couldn&#x27;t be read/g)).toHaveLength(1);
  });
});

describe("3. identity is name + AUTHORITATIVE side", () => {
  it("same name, different authoritative sides → TWO players", () => {
    const { players } = groupPlayerProps({
      playerProps: [
        healthyRow({ player_team: "home" }),
        healthyRow({ player_team: "away", outcome_name: "Ana Diaz: 3+", threshold: 3 }),
      ],
      other: [],
    });
    expect(players).toHaveLength(2);
    expect(players.map((p) => p.team).sort()).toEqual(["away", "home"]);
    // And neither borrowed the other's line.
    for (const p of players) expect(p.stats).toHaveLength(1);
  });

  it("same player across several stats stays ONE card", () => {
    const { players } = groupPlayerProps({
      playerProps: [
        healthyRow({ player_team: "home" }),
        healthyRow({
          player_team: "home",
          market_name: "Reds vs Cubs: Runs",
          outcome_name: "Ana Diaz: 1+",
          threshold: 1,
        }),
      ],
      other: [],
    });
    expect(players).toHaveLength(1);
    expect(players[0].stats).toHaveLength(2);
  });

  it("a DETECTED side never splits a player — only an authoritative one does", () => {
    // THE REGRESSION THIS EXISTS FOR. Keying on the resolved side (which falls
    // back to `detectTeam`) fragmented Mike Trout and Zach Neto into a home card
    // and an away card on production event 15187845, taking it 23 -> 26 players.
    // `detectTeam` reads a market name that NAMES BOTH TEAMS, so two rows about
    // one person can disagree. It is a display heuristic, never an identity.
    const { players } = groupPlayerProps({
      playerProps: [
        healthyRow({ market_name: "Reds vs Cubs: Hits", player_team: null }),
        healthyRow({
          market_name: "Cubs vs Reds: Runs",
          outcome_name: "Ana Diaz: 1+",
          threshold: 1,
          player_team: null,
        }),
      ],
      other: [],
    });
    expect(players).toHaveLength(1);
    expect(players[0].stats).toHaveLength(2);
  });

  it("an unknown-side row joins the single known player of that name", () => {
    const { players } = groupPlayerProps({
      playerProps: [
        healthyRow({ player_team: "home" }),
        healthyRow({
          player_team: null,
          market_name: "Reds vs Cubs: Runs",
          outcome_name: "Ana Diaz: 1+",
          threshold: 1,
        }),
      ],
      other: [],
    });
    expect(players).toHaveLength(1);
    expect(players[0].stats).toHaveLength(2);
  });

  it("with TWO known sides, an unknown-side row is not assigned by a coin flip", () => {
    const { players } = groupPlayerProps({
      playerProps: [
        healthyRow({ player_team: "home" }),
        healthyRow({ player_team: "away", outcome_name: "Ana Diaz: 3+", threshold: 3 }),
        healthyRow({
          player_team: null,
          market_name: "Reds vs Cubs: Runs",
          outcome_name: "Ana Diaz: 1+",
          threshold: 1,
        }),
      ],
      other: [],
    });
    // Three buckets: home, away, and the unattributable row standing alone.
    // Guessing a side here would attach one player's Runs line to the other.
    expect(players).toHaveLength(3);
  });
});
