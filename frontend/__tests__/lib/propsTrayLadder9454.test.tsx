/**
 * #9454 — a finished game's props tray said "grading unavailable" on 60 of 102
 * player cards of /events/14780548 (Rams 30 @ Broncos 26), while WHAT HIT on
 * the same page graded the same props. Two causes, one guard each:
 *
 *   1. the Under leg of an O/U market (`_inverted: true`) carried the UNDER's
 *      typed `hit` into an Over ladder, so every O/U line served with both legs
 *      "conflicted", and `rung.hit` was whichever leg arrived first;
 *   2. a genuine split (HIT at 2+, MISS at 2.5+) withheld the whole card,
 *      including the count every row agreed on.
 *
 * The fixture is the production payload's rows for four players, unedited.
 */
import { renderToStaticMarkup } from "react-dom/server";
import React from "react";
import PlayerPropsDashboard from "../../components/PlayerPropsDashboard";
import type { GameMarketsResponse } from "../../lib/api";
import { groupPlayerProps, type PlayerPropRow, type PlayerStat } from "../../lib/playerPropsGrouping";
import { readSettledLadder } from "../../lib/propGrade";
import fixture from "../fixtures/propsTrayLadder9454.json";

const ROWS = fixture.player_props as PlayerPropRow[];

function statOf(player: string, type: string, rows: readonly PlayerPropRow[] = ROWS): PlayerStat {
  const { players } = groupPlayerProps({ playerProps: rows, homeTeam: "Denver Broncos", awayTeam: "Los Angeles Rams" });
  const p = players.find((x) => x.name === player);
  const s = p?.stats.find((x) => x.type === type);
  if (!s) throw new Error(`no ${player} / ${type}`);
  return s;
}

describe("readSettledLadder — only the backend's typed rung verdicts", () => {
  const rows = (actual: number | null) => [{ actual, hit: true }, { actual, hit: false }];

  it("names the highest HIT rung, the lowest MISS rung and the agreed count", () => {
    const rungs = [{ threshold: 1, hit: true }, { threshold: 2, hit: true }, { threshold: 2.5, hit: false }, { threshold: 3, hit: false }];
    expect(readSettledLadder(rungs, rows(2))).toEqual({ actual: 2, cleared: 2, missed: 2.5 });
  });

  it("is not a split when every rung agrees — readPropGrade already badges that", () => {
    expect(readSettledLadder([{ threshold: 1, hit: true }, { threshold: 2, hit: true }], rows(3))).toBeNull();
    expect(readSettledLadder([{ threshold: 1, hit: false }, { threshold: 2, hit: false }], rows(0))).toBeNull();
  });

  it("refuses verdicts that contradict each other (a HIT above a MISS)", () => {
    expect(readSettledLadder([{ threshold: 1, hit: false }, { threshold: 2, hit: true }], rows(2))).toBeNull();
  });

  it("drops a count the rows disagree on, or one outside the two rungs", () => {
    const rungs = [{ threshold: 1, hit: true }, { threshold: 2, hit: false }];
    expect(readSettledLadder(rungs, [{ actual: 1, hit: true }, { actual: 3, hit: false }])?.actual).toBeNull();
    expect(readSettledLadder(rungs, rows(5))?.actual).toBeNull();
    expect(readSettledLadder(rungs, rows(null))).toEqual({ actual: null, cleared: 1, missed: 2 });
  });
});

describe("the production payload, grouped", () => {
  it("Stafford's 2 passing TDs split at HIT 2+ / MISS 2.5+ (was: grading unavailable)", () => {
    const s = statOf("Matthew Stafford", "Passing Touchdowns");
    expect(s.grade?.reason).toBe("conflicting_rung_verdicts");
    expect(s.settledLadder).toEqual({ actual: 2, cleared: 2, missed: 2.5 });
  });

  it("an Under leg no longer sets a rung's verdict: Ferguson caught 1, so 1.5+ is a MISS", () => {
    const s = statOf("Terrance Ferguson", "Receptions");
    expect(s.rungs?.find((r) => r.threshold === 1.5)?.hit).toBe(false);
    expect(s.rungs?.find((r) => r.threshold === 0.5)?.hit).toBe(true);
    expect(s.settledLadder).toEqual({ actual: 1, cleared: 1, missed: 1.5 });
  });

  it("an O/U line served with both legs grades instead of conflicting", () => {
    const s = statOf("Courtland Sutton", "Longest Reception");
    expect(s.grade).toMatchObject({ state: "HIT", actual: 27 });
  });

  it("a two-rung stat drawn as a line splits too (Nix TDs: HIT 1+, MISS 2+)", () => {
    const s = statOf("Bo Nix", "Touchdowns");
    expect(s.shape).toBe("line");
    expect(s.settledLadder).toEqual({ actual: null, cleared: 1, missed: 2 });
  });

  it("no conflicting card is left without a split", () => {
    const { players } = groupPlayerProps({ playerProps: ROWS, homeTeam: "Denver Broncos", awayTeam: "Los Angeles Rams" });
    const stranded = players.flatMap((p) =>
      p.stats.filter((s) => s.grade?.reason === "conflicting_rung_verdicts" && !s.settledLadder).map((s) => `${p.name} ${s.type}`),
    );
    expect(stranded).toEqual([]);
  });
});

describe("the settled tray card", () => {
  const html = renderToStaticMarkup(
    <PlayerPropsDashboard
      data={{ player_props: ROWS, other: [] } as unknown as GameMarketsResponse}
      eventStatus="completed"
      homeTeam="Denver Broncos"
      awayTeam="Los Angeles Rams"
    />,
  );

  it("prints Stafford's split instead of 'grading unavailable'", () => {
    const card = html.split("Matthew Stafford")[1]?.split('data-settled-ladder="split"')[1] ?? "";
    expect(html).toContain('data-settled-ladder="split"');
    expect(card).toMatch(/>2<\/div>/);
    expect(card).toMatch(/HIT<\/span><span[^>]*>2\+/);
    expect(card).toMatch(/MISS<\/span><span[^>]*>2\.5\+/);
    expect(html.split("Matthew Stafford")[1]?.split("Bo Nix")[0]).not.toContain("grading unavailable");
  });
});
