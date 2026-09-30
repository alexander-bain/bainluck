/**
 * #9608 — a settled soccer rail printed a prop with no player in it.
 *
 * `eventPlayerProps.15316808.yesNoRung.json` is the REAL production
 * `player_props` array of `GET /api/events/15316808/game-markets` (Northern
 * Ireland 0 – Hungary 0, completed), captured 2026-09-29 12:10Z: 14 Polymarket
 * Yes/No rows in the "<Player>: <n>+ <stat>" shape.
 *
 * "How the props landed" read:
 *
 *     1+ goals +: 1+ assists
 *
 * `parsePlayerName`'s rung arm only kept the name for a stat in STAT_TYPES, and
 * "goals + assists" is not one — so the suffix strip made "1+ goals +" the
 * player. #9384 already ruled the O/U shape: the player is before the colon
 * whatever the stat is called. This is the same rule for the rung shape.
 */

import { selectDivergenceDetail } from "@/lib/propDivergence";
import { parsePlayerName, type PlayerPropRow } from "@/lib/playerPropsGrouping";

import payload from "../fixtures/eventPlayerProps.15316808.yesNoRung.json";

type Row = PlayerPropRow & { pregame_mark: number | null; _inverted?: boolean };

const ROWS = payload as unknown as Row[];

const detailRows = (rows: readonly Row[]) => {
  const d = selectDivergenceDetail({ playerProps: rows, status: "completed" });
  return [...d.offScript, ...d.onScript, ...d.ungraded];
};

describe("#9608 — the production specimen", () => {
  it("carries Shea Charles's graded 1+ goals + assists question", () => {
    const legs = ROWS.filter((r) => r.market_name === "Shea Charles: 1+ goals + assists");
    expect(legs).toHaveLength(2);
    expect(legs.every((r) => r.pregame_mark === 0.11)).toBe(true);
  });

  it("names Shea Charles on the settled rail, never the rung", () => {
    const labels = detailRows(ROWS).map((r) => r.label);
    expect(labels).toContain("Shea Charles: 1+ goals + assists");
    expect(labels.join(" | ")).not.toMatch(/(^|\| )\d+\+[^:|]*:/);
  });
});

describe("#9608 — the parse", () => {
  it.each([
    ["Shea Charles: 1+ goals + assists", "Shea Charles", "goals + assists"],
    ["Balázs Tóth: 1+ saves", "Balázs Tóth", "Saves"],
    ["Pierce Charles: 3+ shots on target", "Pierce Charles", "shots on target"],
  ])("reads %s as that player", (market, player, stat) => {
    expect(parsePlayerName(market, "Yes")).toEqual({
      player,
      stat,
      team: "",
      identified: true,
    });
  });

  it("keeps a matchup subject off the player slot", () => {
    for (const subject of ["Norway vs. Denmark", "Army @ Temple", "Spain v Italy"]) {
      expect(parsePlayerName(`${subject}: 2+ goals + assists`, "Yes")?.player).not.toBe(
        subject,
      );
    }
  });

  it("leaves a known stat on its STAT_TYPES spelling", () => {
    expect(parsePlayerName("Juwan Johnson: 2+ Touchdowns", "Yes")?.stat).toBe("Touchdowns");
  });
});
