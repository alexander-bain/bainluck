/**
 * #6217 — a scoring race is a team market, never a player card.
 *
 * Seen on production 2026-10-01 at 390px, `/events/14780550` (Steelers @
 * Browns, live Q4): the props tray's PIT filter ended with five cards titled
 * "Race to 10 / 14 / 21 / 28 / 35", avatar "RT", stat "Points". They came from
 * the fifteen `other[]` rows below, verbatim from that event's game-markets
 * payload: the `other[]` pass stripped "Points" off "Race to 21 Points", kept
 * "Race to 21" as the person, and "Points" passed the STAT_TYPES check.
 *
 * On that payload the fix takes the page from 28 cards (5 races) to 23 (0) and
 * leaves the other 23 alone. The races keep their real home, the Additional
 * Markets race ladder (#1627), which reads them with the same predicate.
 */
import { groupPlayerProps, type OtherMarketRow } from "../../lib/playerPropsGrouping";
import { isScoringRaceMarket } from "../../lib/otherMarketGroups";

const HOME = "Cleveland Browns";
const AWAY = "Pittsburgh Steelers";

// Verbatim from GET /api/events/14780550/game-markets, 02:5xZ 2026-10-02.
const RACE_ROWS: OtherMarketRow[] = [
  ["35", "Neither team", 0.935],
  ["35", "Cleveland", 0.04],
  ["35", "Pittsburgh", 0.01],
  ["14", "Cleveland", 0.9802],
  ["14", "Neither team", 0.0099],
  ["14", "Pittsburgh", 0.0099],
  ["28", "Neither team", 0.645],
  ["28", "Cleveland", 0.31],
  ["28", "Pittsburgh", 0.035],
  ["10", "Cleveland", 0.9612],
  ["10", "Neither team", 0.0291],
  ["10", "Pittsburgh", 0.0097],
  ["21", "Cleveland", 0.9802],
  ["21", "Pittsburgh", 0.0099],
  ["21", "Neither team", 0.0099],
].map(([n, outcome, p]) => ({
  market_name: `Pittsburgh vs Cleveland: Race to ${n} Points`,
  outcome_name: outcome as string,
  probability: p as number,
  source: "kalshi",
}));

// A player row that reaches the card list ONLY through the `other[]` pass —
// the control. Same matchup prefix, same "Points" stat as the races, so a
// refusal widened past scoring races (to every "Points" stat, or to every
// "<A> vs <B>:" market) would delete this card too.
const PLAYER_OTHER_ROW: OtherMarketRow = {
  market_name: "Pittsburgh vs Cleveland: Points",
  outcome_name: "Quinshon Judkins: 6+",
  probability: 0.42,
  source: "kalshi",
};

function cardNames(other: OtherMarketRow[]): string[] {
  return groupPlayerProps({ playerProps: [], other, homeTeam: HOME, awayTeam: AWAY }).players.map(
    (p) => p.name,
  );
}

describe("#6217 a scoring race never becomes a player card", () => {
  it("the five races from the live payload draw no card", () => {
    expect(cardNames(RACE_ROWS)).toEqual([]);
  });

  it("a real player row in the same other[] still draws its card (control)", () => {
    expect(cardNames([...RACE_ROWS, PLAYER_OTHER_ROW])).toEqual(["Quinshon Judkins"]);
  });

  it("refuses by the same predicate Additional Markets groups races with", () => {
    // Every race row is one the race ladder claims, so refusing here moves the
    // market to one home rather than deleting it from the page.
    for (const row of RACE_ROWS) expect(isScoringRaceMarket(row.market_name)).toBe(true);
    expect(isScoringRaceMarket(PLAYER_OTHER_ROW.market_name)).toBe(false);
  });
});
