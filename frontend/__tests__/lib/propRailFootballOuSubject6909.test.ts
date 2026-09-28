/**
 * #6909 follow-up — a settled NFL rail named a prop after its own line.
 *
 * `eventPlayerProps.14782707.footballOuSubject.json` is the REAL production
 * `player_props` array of `GET /api/events/14782707/game-markets` (Saints 27 –
 * Raiders 35, completed), captured 2026-09-28 13:11Z right after #6909's
 * Polymarket arm went live, trimmed to the 264 rows that carry a threshold, a
 * price and a pregame mark (the only rows the rail can admit).
 *
 * Once those Polymarket O/U rows carried a typed `hit`, "How the props landed"
 * printed, directly under Kalshi's "Shough's 4+ passing touchdowns was marked
 * 5%":
 *
 *     Passing Touchdowns O/U 3.5's 4+ was marked 5% — and it hit.
 *
 * `parsePlayerName` only reads Polymarket's "<Player>: <Stat> O/U <line>" shape
 * for a stat in STAT_TYPES, and "Passing Touchdowns" was not one — so the
 * stat-and-line became the player, and #9178's cross-venue dedupe could not
 * see that it was Shough's 4+ question again.
 */

import { selectDivergenceDetail, selectDivergenceRows } from "@/lib/propDivergence";
import { parsePlayerName, type PlayerPropRow } from "@/lib/playerPropsGrouping";

import payload from "../fixtures/eventPlayerProps.14782707.footballOuSubject.json";

type Row = PlayerPropRow & { pregame_mark: number; _inverted?: boolean };

const ROWS = payload as unknown as Row[];

const detailRows = (rows: readonly Row[]) => {
  const d = selectDivergenceDetail({ playerProps: rows, status: "completed" });
  return [...d.offScript, ...d.onScript, ...d.ungraded];
};

describe("#6909 follow-up — the production specimen", () => {
  it("carries both venues' passing-touchdown lines for Shough", () => {
    const legs = ROWS.filter(
      (r) =>
        r.market_name === "Tyler Shough: Passing Touchdowns O/U 3.5" ||
        (r.market_name === "Las Vegas vs New Orleans: Passing Touchdowns" &&
          r.outcome_name === "Tyler Shough: 4+"),
    );
    expect(legs.map((l) => [l.source, l.threshold]).sort()).toEqual([
      ["kalshi", 4],
      ["polymarket", 3.5],
      ["polymarket", 3.5],
    ]);
  });

  it("no row on the rail or in the detail is named after a line", () => {
    const labels = detailRows(ROWS).map((r) => r.label);
    expect(labels.length).toBeGreaterThan(0);
    expect(labels.filter((l) => /O\/U/.test(l))).toEqual([]);
    // "Juwan Johnson: 2+ Touchdowns" printed as "2+: 2+ touchdowns".
    expect(labels.filter((l) => /^\d+\+:/.test(l))).toEqual([]);
    const sentences = selectDivergenceRows({ playerProps: ROWS, status: "completed" }).rows.map(
      (r) => r.sentence,
    );
    expect(sentences.join(" ")).not.toContain("O/U");
  });

  it("asks Shough's 4+ passing touchdowns once, at the Kalshi rung's own mark", () => {
    const rows = detailRows(ROWS).filter(
      (r) => r.label === "Tyler Shough: 4+ passing touchdowns",
    );
    expect(rows).toHaveLength(1);
    expect(rows[0].pregameMark).toBe(0.045);
    const labels = detailRows(ROWS).map((r) => r.label);
    expect(labels.length).toBe(new Set(labels).size);
  });
});

describe("#6909 follow-up — the parse", () => {
  it.each([
    ["Passing Touchdowns"],
    ["Passing Completions"],
    ["Passing Attempts"],
    ["Longest Reception"],
    ["Rushing + Receiving Yards"],
  ])("reads Polymarket's '<Player>: %s O/U <line>' as that player", (stat) => {
    expect(parsePlayerName(`Pat Passer: ${stat} O/U 2.5`, "Over")).toEqual({
      player: "Pat Passer",
      stat,
      team: "",
      identified: true,
    });
  });

  it("reads Polymarket's '<Player>: <n>+ <Stat>' Yes/No market as that player", () => {
    expect(parsePlayerName("Juwan Johnson: 2+ Touchdowns", "Yes")).toEqual({
      player: "Juwan Johnson",
      stat: "Touchdowns",
      team: "",
      identified: true,
    });
    // An unknown stat after the rung keeps today's parse.
    expect(parsePlayerName("Juwan Johnson: 2+ Fantasy Hats", "Yes")?.player).not.toBe(
      "Juwan Johnson",
    );
  });

  it("leaves Kalshi's matchup shape reading the subject from the outcome", () => {
    expect(
      parsePlayerName("Las Vegas vs New Orleans: Passing Touchdowns", "Tyler Shough: 4+"),
    ).toMatchObject({ player: "Tyler Shough", stat: "Passing Touchdowns" });
  });
});
