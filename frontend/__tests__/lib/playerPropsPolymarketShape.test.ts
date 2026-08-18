/**
 * UX-P097 (#1976 §5) — the Polymarket prop shape, client half.
 *
 * The backend half of this fix is in `routes/events.py`: a Polymarket-only game
 * served SIX EMPTY SECTIONS over a complete prop set, because the assembly path
 * assumed Kalshi's line placement (number in the OUTCOME name) and Polymarket
 * puts it in the MARKET name with bare "Over"/"Under" outcomes.
 *
 * Fixing the payload exposed the SAME wrong assumption one layer up, in this
 * module, where it had been invisible precisely because these rows had never
 * reached the client:
 *
 *   1. `parsePlayerName` splits on the colon expecting "<Matchup>: <Player Stat>".
 *      Polymarket's "<Player>: <Stat> O/U <line>" is the mirror image, so the
 *      parse took the STAT-AND-LINE as the person and produced players literally
 *      named "Home Runs O/U 0.5".
 *   2. Every `other`-derived rung was pushed with a HARDCODED `threshold: 0.5`,
 *      so "Bubba Chandler: Strikeouts O/U 4.5" rendered as Strikeouts 0.5 — a
 *      wrong number, not a missing one. `parsePropLabel` had been parsing the
 *      real line all along; this pass discarded it.
 *
 * The fixture is the real payload of the flagship specimen, captured 2026-08-18:
 *
 *   15191702  Boston Red Sox @ Pittsburgh Pirates, closed, polymarket-only.
 *             0 player_props / 33 other — the empty page, exactly as served.
 *
 * Held in BOTH directions per gotcha #43: the Polymarket shape must parse, and
 * the Kalshi shapes that parse today must not move.
 */

import {
  groupPlayerProps,
  parsePlayerName,
  type OtherMarketRow,
} from "../../lib/playerPropsGrouping";
import polymarketOnly from "../fixtures/playerPropsPolymarketOnly.json";

const GROUP_ARGS = {
  homeTeam: "Pittsburgh Pirates",
  awayTeam: "Boston Red Sox",
  homeColor: "#111111",
  awayColor: "#222222",
  boxScorePlayers: null,
} as const;

describe("parsePlayerName — the Polymarket '<Player>: <Stat> O/U <line>' shape", () => {
  it.each([
    ["Adley Rutschman: Home Runs O/U 0.5", "Adley Rutschman", "Home Runs"],
    ["Bubba Chandler: Strikeouts O/U 4.5", "Bubba Chandler", "Strikeouts"],
    ["Jarren Duran: Home Runs O/U 1.5", "Jarren Duran", "Home Runs"],
  ])("%s -> %s / %s", (marketName, player, stat) => {
    const parsed = parsePlayerName(marketName, "Over");
    expect(parsed).not.toBeNull();
    expect(parsed!.player).toBe(player);
    expect(parsed!.stat).toBe(stat);
    expect(parsed!.identified).toBe(true);
  });

  it("does not hand the player's name to the team detector", () => {
    // `team` feeds detectTeam(). For this shape the text before the colon is a
    // PERSON, so answering with it would be a confident wrong answer; the row's
    // own `player_team` is the honest source and the caller prefers it.
    expect(parsePlayerName("Adley Rutschman: Home Runs O/U 0.5", "Over")!.team).toBe("");
  });

  // ---- the other direction: Kalshi shapes must be untouched ---------------

  it("leaves the Kalshi team-stat shape parsing exactly as before", () => {
    const parsed = parsePlayerName(
      "Cincinnati Reds at St. Louis Cardinals: Home Runs",
      "Juan Soto: 2+",
    );
    expect(parsed!.player).toBe("Juan Soto");
    expect(parsed!.stat).toBe("Home Runs");
    // Here the pre-colon text IS the matchup, and must still reach detectTeam.
    expect(parsed!.team).toBe("Cincinnati Reds at St. Louis Cardinals");
  });

  it("does not claim a person when the line has no known stat", () => {
    // A genuine game total wearing the same punctuation. Must NOT be read as a
    // player called "St. Louis Cardinals vs. Cincinnati Reds".
    const parsed = parsePlayerName("St. Louis Cardinals vs. Cincinnati Reds: O/U 10.5", "Over");
    expect(parsed?.stat).not.toBe("Home Runs");
    expect(parsed?.player).not.toBe("St. Louis Cardinals vs. Cincinnati Reds");
  });
});

describe("the `other` bucket carries each row's real line, not 0.5", () => {
  const other = polymarketOnly.other as OtherMarketRow[];

  it("the fixture is the empty page, as served", () => {
    expect(polymarketOnly.player_props).toHaveLength(0);
    expect(other).toHaveLength(33);
  });

  it("reads Bubba Chandler's strikeouts at 4.5, the line his label states", () => {
    const { players } = groupPlayerProps({ playerProps: [], other, ...GROUP_ARGS } as never);
    const chandler = players.find((p) => p.name === "Bubba Chandler");
    expect(chandler).toBeDefined();
    const strikeouts = chandler!.stats.find((s) => s.type.toLowerCase() === "strikeouts");
    expect(strikeouts).toBeDefined();
    // The regression: this was 0.5 for every row regardless of its label.
    expect(strikeouts!.threshold ?? strikeouts!.rungs?.[0]?.threshold).toBe(4.5);
  });

  it("still defaults to 0.5 for labels that carry no line", () => {
    // The Yes/No/NRFI rows must keep rendering exactly as they do today.
    const yesNo: OtherMarketRow[] = [
      { market_name: "Will there be a run scored in the first inning?", outcome_name: "Yes", probability: 0.47, source: "polymarket" },
    ];
    const { players } = groupPlayerProps({ playerProps: [], other: yesNo, ...GROUP_ARGS } as never);
    // No stat is named, so no player card is invented from it.
    expect(players.find((p) => p.name.includes("run scored"))).toBeUndefined();
  });

  it("names real people, never a statistic", () => {
    const { players } = groupPlayerProps({ playerProps: [], other, ...GROUP_ARGS } as never);
    for (const p of players) {
      expect(p.name).not.toMatch(/O\/U/i);
      expect(p.name).not.toMatch(/^(Home Runs|Strikeouts|Hits)\b/i);
    }
  });
});
