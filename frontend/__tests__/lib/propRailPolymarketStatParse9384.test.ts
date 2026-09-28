/**
 * #9384 — a settled NFL page's props rail printed one question twice.
 *
 * `eventPlayerProps.14781702.polymarketStatParse9384.json` is the REAL production
 * `player_props` array of `GET /api/events/14781702/game-markets` (Commanders
 * 33–31 Seahawks, completed), captured 2026-09-28 ~13:55Z, untrimmed (418 rows —
 * the rail ranks across all of them, so a trim would change what it selects).
 *
 * Rail before the fix (390px, production ~13:30Z):
 *   "Darnold's 4+ passing touchdowns was marked 5% — and it hit."
 *   "Passing Touchdowns O/U 3.5's 4+ was marked 5% — and it hit."
 *
 *   Kalshi      "Seattle vs Washington: Passing Touchdowns" / "Sam Darnold: 4+"
 *   Polymarket  "Sam Darnold: Passing Touchdowns O/U 3.5"   / "Over"
 *
 * `parsePlayerName`'s Polymarket branch only fired for a stat in STAT_TYPES, and
 * "Passing Touchdowns" is not in it, so the stat-and-line became the "player"
 * and #9178's collapse (keyed player|stat|rung) could not pair the two legs.
 */

import { parsePlayerName, groupPlayerProps } from "@/lib/playerPropsGrouping";
import type { PlayerPropRow } from "@/lib/playerPropsGrouping";
import { selectDivergenceDetail, selectDivergenceRows } from "@/lib/propDivergence";

import payload from "../fixtures/eventPlayerProps.14781702.polymarketStatParse9384.json";

const ROWS = payload as unknown as PlayerPropRow[];

describe("#9384 — parsePlayerName keeps the player before the colon", () => {
  it("the specimen: a stat outside STAT_TYPES keeps Darnold and the whole phrase", () => {
    expect(parsePlayerName("Sam Darnold: Passing Touchdowns O/U 3.5", "Over")).toMatchObject({
      player: "Sam Darnold",
      stat: "Passing Touchdowns",
    });
  });

  it("keys exactly like the Kalshi leg of the same question", () => {
    const poly = parsePlayerName("Sam Darnold: Passing Touchdowns O/U 3.5", "Over");
    const kalshi = parsePlayerName("Seattle vs Washington: Passing Touchdowns", "Sam Darnold: 4+");
    expect([poly?.player, poly?.stat]).toEqual([kalshi?.player, kalshi?.stat]);
  });

  it.each([
    ["Tarik Skubal: Outs Recorded O/U 17.5", "Tarik Skubal", "Outs Recorded"],
    ["Tarik Skubal: Earned Runs Allowed O/U 1.5", "Tarik Skubal", "Earned Runs Allowed"],
    ["Jaxon Smith-Njigba: Longest Reception O/U 24.5", "Jaxon Smith-Njigba", "Longest Reception"],
  ])("the measured population: %s", (market, player, stat) => {
    expect(parsePlayerName(market, "Over")).toMatchObject({ player, stat });
  });

  it("control: a known stat keeps its canonical STAT_TYPES spelling", () => {
    expect(parsePlayerName("Manny Machado: home runs O/U 0.5", "Over")).toMatchObject({
      player: "Manny Machado",
      stat: "Home Runs",
    });
  });

  it.each([
    "Norway vs. Denmark: 1st Half O/U 1.5",
    "Army vs. Temple: 1Q O/U 10.5",
    "Radisic vs. Morvayova: Match O/U 22.5",
    "Chicago Cubs vs. Boston Red Sox: 1st 5 Innings O/U 4.5",
    "Seahawks @ Commanders: Team Total O/U 24.5",
  ])("control: a matchup before the colon is never a player — %s", (market) => {
    const parsed = parsePlayerName(market, "Over");
    expect(parsed?.player ?? "").not.toMatch(/ vs\.? | @ /);
    expect(parsed?.player ?? "").not.toBe(market.slice(0, market.indexOf(":")));
  });
});

describe("#9384 — the production specimen", () => {
  it("serves the two legs of Darnold's 4+ passing touchdowns", () => {
    const legs = ROWS.filter(
      (r) =>
        (r.market_name === "Sam Darnold: Passing Touchdowns O/U 3.5" && r.outcome_name === "Over") ||
        (r.market_name === "Seattle vs Washington: Passing Touchdowns" && r.outcome_name === "Sam Darnold: 4+"),
    );
    expect(legs.map((l) => l.source).sort()).toEqual(["kalshi", "polymarket"]);
  });

  it("the settled rail asks the question once, and no row is named after a stat line", () => {
    const labels = selectDivergenceRows({ playerProps: ROWS, status: "completed" }).rows.map((r) => r.label);
    expect(labels.filter((l) => l === "Sam Darnold: 4+ passing touchdowns")).toHaveLength(1);
    expect(labels.filter((l) => /O\/U/.test(l))).toEqual([]);
  });

  it("the detail lists no nameless O/U twin (252 rows became 250)", () => {
    const d = selectDivergenceDetail({ playerProps: ROWS, status: "completed" });
    const all = [...d.offScript, ...d.onScript, ...d.ungraded];
    expect(all.filter((r) => /O\/U/.test(r.label))).toEqual([]);
    expect(all).toHaveLength(250);
  });

  it("the props section builds no player called 'Passing Touchdowns O/U …'", () => {
    const { players } = groupPlayerProps({ playerProps: ROWS, homeTeam: "Washington Commanders", awayTeam: "Seattle Seahawks" });
    expect(players.map((p) => p.name).filter((n) => /O\/U/.test(n))).toEqual([]);
  });
});
