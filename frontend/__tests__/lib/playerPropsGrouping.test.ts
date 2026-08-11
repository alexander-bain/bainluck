/**
 * UX-P056 — the props grouping, held to two production payloads and one guard.
 *
 * WHY THE FIXTURE IS REAL AND NOT SYNTHETIC. The whole point of the extraction
 * is that this code could not previously be executed by a test at all: it lived
 * inline in a `useMemo`, jest here is `testEnvironment: "node"`, and neither
 * jsdom nor react-test-renderer is installed (the npm registry is unreachable
 * from this environment). So the only description of its behaviour was "render
 * the component against whatever game exists tonight" — and a slate is exactly
 * what defeated the last rail this lane tried to test that way (#1650).
 *
 * `fixtures/playerPropsProduction.json` is two captures of
 * `GET /api/events/{id}/game-markets`, taken 2026-08-11:
 *
 *   15191146  Cleveland Guardians @ Chicago White Sox, completed, 39 props / 121 other
 *   15187845  Texas Rangers @ Los Angeles Angels,      completed, 41 props /  71 other
 *
 * These are the two events on the whole feed that carry player props, which is
 * the honest exposure statement: the dashboard renders on a minority of games,
 * and on those it renders 23–24 player cards at once. That ratio is the reason
 * one bad row costing all of them mattered.
 *
 * The counts are not transcribed by hand — see the oracle describe() below for
 * why that was tried, failed, and was replaced.
 */

import {
  groupPlayerProps,
  parsePlayerName,
  type PlayerPropRow,
  type OtherMarketRow,
} from "@/lib/playerPropsGrouping";
import { groupPlayerPropsLegacy } from "../fixtures/playerPropsGroupingLegacy";
import fixture from "../fixtures/playerPropsProduction.json";

type Capture = {
  status: string;
  home_team: string;
  away_team: string;
  player_props: PlayerPropRow[];
  other: OtherMarketRow[];
};

const CAPTURES = fixture as unknown as Record<string, Capture>;

function group(id: string, overrides: Partial<Parameters<typeof groupPlayerProps>[0]> = {}) {
  const c = CAPTURES[id];
  return groupPlayerProps({
    playerProps: c.player_props,
    other: c.other,
    homeTeam: c.home_team,
    awayTeam: c.away_team,
    homeColor: "#111111",
    awayColor: "#222222",
    ...overrides,
  });
}

/**
 * THE BOTH-DIRECTION PROOF (gotcha #43), and the reason it is an oracle and not
 * a list of numbers.
 *
 * The first draft of this suite transcribed player counts from a hand-written
 * census — and got them wrong (17, when the real figure is 24), because the
 * census only walked `player_props[]` and forgot that the `other[]` pass adds
 * players of its own. Numbers copied by hand describe the transcriber, not the
 * code. So the extraction is held against a MECHANICAL COPY of the pre-change
 * memo (`fixtures/playerPropsGroupingLegacy.ts`, lifted verbatim from f46716ed):
 * if the two disagree about anything on a real payload, this fails.
 */
describe("the extraction changed nothing — new module vs pre-change memo", () => {
  for (const id of Object.keys(CAPTURES)) {
    it(`produces byte-identical players on ${id}`, () => {
      const c = CAPTURES[id];
      const legacy = groupPlayerPropsLegacy(
        { player_props: c.player_props, other: c.other },
        c.home_team,
        c.away_team,
        "#111111",
        "#222222",
        null,
      );
      const { players, dropped } = group(id);
      expect(players).toEqual(legacy);
      expect(dropped).toEqual([]);
    });
  }
});

describe("groupPlayerProps over the two production payloads", () => {
  /**
   * The exposure statement, measured rather than assumed: these are the only
   * two events on the whole feed carrying player props, and each renders more
   * than a dozen cards at once. That ratio is why one bad row costing all of
   * them mattered.
   */
  it("15191146 renders 24 players", () => {
    expect(group("15191146").players).toHaveLength(24);
  });

  it("15187845 renders 23 players", () => {
    expect(group("15187845").players).toHaveLength(23);
  });

  it("sorts by stat count, most props first", () => {
    const counts = group("15191146").players.map((p) => p.stats.length);
    expect(counts).toEqual([...counts].sort((a, b) => b - a));
  });

  /**
   * The shape rule, pinned because #1722 lived inside it: 3+ rungs is a ladder,
   * fewer is a line, and ZERO never reaches the decision at all.
   */
  it("assigns ladder only at three or more rungs, and never emits a rungless stat", () => {
    for (const id of Object.keys(CAPTURES)) {
      for (const p of group(id).players) {
        expect(p.stats.length).toBeGreaterThan(0);
        for (const s of p.stats) {
          if (s.shape === "ladder") {
            expect(s.rungs!.length).toBeGreaterThanOrEqual(3);
          } else {
            expect(s.threshold).not.toBeUndefined();
          }
        }
      }
    }
  });

  /** Ruling 003: every verdict comes from a `hit` the backend typed. */
  it("states a verdict only where the backend typed one", () => {
    const states = group("15191146").players.flatMap((p) =>
      p.stats.map((s) => s.grade!.state),
    );
    expect(states.filter((s) => s === "HIT")).toHaveLength(0);
    expect(states.filter((s) => s === "MISS").length).toBeGreaterThan(0);
    expect(states.filter((s) => s === "WITHHOLD").length).toBeGreaterThan(0);
  });

  /**
   * #1728, recorded here so the number is not mistaken for a client bug.
   *
   * This MISS is WRONG — Steven Kwan reached 3 on a 2+ line, and the payload
   * publishes `actual: 0.0, hit: false` because the backend resolves
   * `Hits + Runs + RBIs` as if it were a simple statistic. The client must still
   * print what it was given (ruling 003), and this asserts exactly that: the
   * wrong verdict travels through unchanged rather than being repaired here.
   */
  it("passes #1728's wrong verdict through rather than repairing it", () => {
    const kwan = group("15191146").players.find((p) => p.name === "Steven Kwan")!;
    const hrr = kwan.stats.find((s) => s.type === "Hits + Runs + Rbis")!;
    expect(hrr.grade).toMatchObject({ state: "MISS", hit: false, actual: 0 });
  });

  /** The box-score path stays off — dict-shaped `players` must not switch it on. */
  it("never derives an actual from a box score", () => {
    const { players } = group("15191146", { boxScorePlayers: null });
    expect(players.every((p) => p.stats.every((s) => s.actual == null))).toBe(true);
  });
});

describe("the guard — one bad row does not cost the other players", () => {
  /**
   * A row whose `market_name` throws when read. This is the #1722 SHAPE at the
   * seam where it actually occurred: inside the grouping loop, before any card
   * exists. It is planted rather than found because the payload that used to
   * throw no longer does — #1722 fixed the cause, which is why this needs a
   * seam to plant at rather than a specimen to capture.
   */
  function poisonRow(): PlayerPropRow {
    return {
      get market_name(): string {
        throw new Error("planted: unreadable market_name");
      },
      outcome_name: "Poison Row: 1+",
      threshold: 1,
      over_probability: 0.5,
      source: "kalshi",
    } as unknown as PlayerPropRow;
  }

  it("drops exactly the bad row and keeps every one of the 24 players", () => {
    const c = CAPTURES["15191146"];
    const { players, dropped } = groupPlayerProps({
      playerProps: [...c.player_props, poisonRow()],
      other: c.other,
      homeTeam: c.home_team,
      awayTeam: c.away_team,
    });

    expect(players).toHaveLength(24);
    expect(dropped).toHaveLength(1);
    expect(dropped[0]).toMatchObject({ kind: "player_prop_row", at: "39" });
    expect(dropped[0].message).toContain("unreadable market_name");
  });

  it("survives a poison row in the FIRST position too", () => {
    const c = CAPTURES["15191146"];
    const { players, dropped } = groupPlayerProps({
      playerProps: [poisonRow(), ...c.player_props],
      other: c.other,
      homeTeam: c.home_team,
      awayTeam: c.away_team,
    });
    expect(players).toHaveLength(24);
    expect(dropped).toHaveLength(1);
  });

  it("drops a bad `other` row without touching the player_props players", () => {
    const c = CAPTURES["15191146"];
    const poison = {
      get market_name(): string {
        throw new Error("planted: unreadable other row");
      },
      outcome_name: "x",
      probability: 0.4,
      source: "kalshi",
    } as unknown as OtherMarketRow;

    const { players, dropped } = groupPlayerProps({
      playerProps: c.player_props,
      other: [...c.other, poison],
      homeTeam: c.home_team,
      awayTeam: c.away_team,
    });
    expect(players).toHaveLength(24);
    expect(dropped).toHaveLength(1);
    expect(dropped[0].kind).toBe("other_row");
  });

  it("reports every bad row, not just the first", () => {
    const c = CAPTURES["15191146"];
    const { players, dropped } = groupPlayerProps({
      playerProps: [poisonRow(), ...c.player_props, poisonRow()],
      other: c.other,
      homeTeam: c.home_team,
      awayTeam: c.away_team,
    });
    expect(players).toHaveLength(24);
    expect(dropped).toHaveLength(2);
  });

  /**
   * The other direction (gotcha #43): the guard must not become a shrug that
   * hides a real failure. A clean payload reports nothing dropped, so the
   * "couldn't be read" line the dashboard renders off this array stays absent.
   */
  it("reports nothing dropped on a clean payload", () => {
    for (const id of Object.keys(CAPTURES)) {
      expect(group(id).dropped).toEqual([]);
    }
  });

  it("returns no players and no drops for an empty payload", () => {
    expect(groupPlayerProps({ playerProps: [], other: [] })).toEqual({
      players: [],
      dropped: [],
    });
  });
});

describe("parsePlayerName, moved unchanged", () => {
  it("reads the player from the outcome when the market names the stat", () => {
    expect(parsePlayerName("Chicago WS vs Cleveland: Hits", "Steven Kwan: 2+")).toEqual({
      player: "Steven Kwan",
      stat: "Hits",
      team: "Chicago WS vs Cleveland",
      identified: true,
    });
  });

  it("marks a matchup-shaped market as unidentified (#1642 P1b)", () => {
    const parsed = parsePlayerName("Tampa Bay Rays vs. Seattle Mariners", "Yes");
    expect(parsed?.identified).toBe(false);
  });

  it("withholds the group verdict for an unidentified bucket", () => {
    const rows: PlayerPropRow[] = [
      {
        market_name: "Tampa Bay Rays vs. Seattle Mariners",
        outcome_name: "Yes",
        threshold: 1,
        over_probability: 0.5,
        source: "polymarket",
        actual: 3,
        hit: true,
        is_winner: true,
        resolution_source: "api_settlement",
      },
    ];
    const { players } = groupPlayerProps({ playerProps: rows, other: [] });
    expect(players[0].stats[0].grade).toMatchObject({
      state: "WITHHOLD",
      reason: "mixed_entity_group",
    });
  });
});
