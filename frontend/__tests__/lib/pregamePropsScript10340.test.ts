/**
 * #10340 — before kickoff, a prop question is told once.
 *
 * Production, 390px, 2026-10-03 14:18Z: /events/15318030 (Alabama @ Mississippi
 * State, `scheduled`). Six Team Receiving Touchdowns questions drew three times:
 * the rail ("The script · 2 of 6"), the "All 6 props" fold, and THE SCRIPT
 * below Additional Markets, at different thresholds under two "script" headings.
 *
 * The repair removes from THE SCRIPT only the rows the fold actually DRAWS, only
 * on a known pregame page. These guards run the real grouping, not a stub of it,
 * because "the key is in `player_props`" is not coverage: a rejected row, a
 * line's hidden second threshold and an ambiguous identity all have keys and are
 * not on any card.
 */
import { readFileSync } from "fs";
import { join } from "path";
import {
  groupPlayerProps,
  groupPlayerPropsWithCoverage,
  type OtherMarketRow,
  type PlayerPropRow,
} from "../../lib/playerPropsGrouping";
import {
  dropScriptRowsTheFoldDraws,
  isKnownPregameForScript,
  type PregameScriptRow,
} from "../../lib/pregamePropsScript10340";
import fixture from "../fixtures/playerPropsProduction.json";

// The specimen's market, verbatim from the served payload.
const MARKET = "Alabama vs Mississippi St.: Team Receiving Touchdowns";

function prop(over: Partial<PlayerPropRow>): PlayerPropRow {
  return {
    market_name: MARKET,
    outcome_name: "Alabama: 2+",
    threshold: 2,
    over_probability: 0.5,
    movement: null,
    source: "kalshi",
    player_team: null,
    actual: null,
    hit: null,
    is_winner: false,
    resolution_source: null,
    ...over,
  };
}

interface ScriptRow extends PregameScriptRow {
  key: string;
  label: string;
  pregame_mark: number | null;
  current: number | null;
}

/** The server's `_build_props_script` key and an ungraded, unsettled mark. */
function scriptOf(rows: readonly PlayerPropRow[]): ScriptRow[] {
  return rows.map((r) => ({
    key: `${r.market_name}|${r.outcome_name}`,
    label: r.outcome_name ?? "",
    pregame_mark: r.over_probability ?? null,
    current: r.over_probability ?? null,
    graded_result: null,
    settled: false,
  }));
}

function coverage(rows: readonly PlayerPropRow[], other: readonly OtherMarketRow[] = []) {
  return groupPlayerPropsWithCoverage({
    playerProps: rows,
    other,
    homeTeam: "Mississippi State Bulldogs",
    awayTeam: "Alabama Crimson Tide",
  }).representedScriptKeys;
}

const PREGAME = { knownPregame: true };

// The pregame shape of the specimen: three rungs a side.
const SIX: PlayerPropRow[] = [
  prop({ outcome_name: "Mississippi St.: 2+", threshold: 2, over_probability: 0.595 }),
  prop({ outcome_name: "Mississippi St.: 3+", threshold: 3, over_probability: 0.325 }),
  prop({ outcome_name: "Mississippi St.: 4+", threshold: 4, over_probability: 0.145 }),
  prop({ outcome_name: "Alabama: 2+", threshold: 2, over_probability: 0.58 }),
  prop({ outcome_name: "Alabama: 3+", threshold: 3, over_probability: 0.28 }),
  prop({ outcome_name: "Alabama: 4+", threshold: 4, over_probability: 0.105 }),
];

describe("#10340 the specimen: six rows, two ladders", () => {
  it("the fold draws every one of the six, so THE SCRIPT has nothing left to repeat", () => {
    const { players } = groupPlayerProps({ playerProps: SIX });
    expect(players.map((p) => `${p.name}:${p.stats.map((s) => `${s.shape}${s.rungs?.length}`)}`).sort())
      .toEqual(["Alabama:ladder3", "Mississippi St.:ladder3"]);

    const script = scriptOf(SIX);
    const keys = coverage(SIX);
    expect([...keys].sort()).toEqual(script.map((s) => s.key).sort());
    expect(dropScriptRowsTheFoldDraws(script, { ...PREGAME, representedKeys: keys })).toEqual([]);
  });

  it("without the filter the section carries all six — the defect this guard must see", () => {
    const script = scriptOf(SIX);
    expect(dropScriptRowsTheFoldDraws(script, { knownPregame: false, representedKeys: coverage(SIX) }))
      .toHaveLength(6);
  });
});

describe("#10340 coverage is what the fold EMITS, never input membership", () => {
  it("a two-rung line draws only its lowest rung, so the hidden second threshold stays", () => {
    const rows = [
      prop({ outcome_name: "Alabama: 2+", threshold: 2 }),
      prop({ outcome_name: "Alabama: 3+", threshold: 3 }),
    ];
    const { players } = groupPlayerProps({ playerProps: rows });
    expect(players[0].stats[0]).toMatchObject({ shape: "line", threshold: 2 });

    const kept = dropScriptRowsTheFoldDraws(scriptOf(rows), { ...PREGAME, representedKeys: coverage(rows) });
    expect(kept.map((r) => r.key)).toEqual([`${MARKET}|Alabama: 3+`]);
  });

  it("a three-rung ladder covers every rung", () => {
    const rows = SIX.slice(0, 3);
    expect([...coverage(rows)].sort()).toEqual(scriptOf(rows).map((s) => s.key).sort());
  });

  it("a row with no threshold is rejected by the grouping and its script row stays", () => {
    const rows = [...SIX, prop({ outcome_name: "Alabama: 6+", threshold: null })];
    const kept = dropScriptRowsTheFoldDraws(scriptOf(rows), { ...PREGAME, representedKeys: coverage(rows) });
    expect(kept.map((r) => r.key)).toEqual([`${MARKET}|Alabama: 6+`]);
  });

  it("an unparseable row (no subject at all) contributes no key and stays", () => {
    const bad = prop({ market_name: "Points", outcome_name: "Yes", threshold: 0.5 });
    expect(groupPlayerProps({ playerProps: [bad] }).players).toEqual([]);
    const rows = [...SIX, bad];
    const kept = dropScriptRowsTheFoldDraws(scriptOf(rows), { ...PREGAME, representedKeys: coverage(rows) });
    expect(kept.map((r) => r.key)).toEqual(["Points|Yes"]);
  });

  it("an unidentified stat (matchup, not a person — #1642 P1b) is drawn but claims nothing", () => {
    const matchup = prop({
      market_name: "Tampa Bay Rays vs. Seattle Mariners - Player Props",
      outcome_name: "Something",
      threshold: 1,
    });
    expect(groupPlayerProps({ playerProps: [matchup] }).players).toHaveLength(1);
    expect(coverage([matchup]).size).toBe(0);
  });

  it("two same-named opponents: the untagged row is ambiguous and stays; the tagged rows are covered", () => {
    const m = "Dodgers vs Braves: Hits";
    const rows = [
      prop({ market_name: m, outcome_name: "Will Smith: 1+", threshold: 1, player_team: "home" }),
      prop({ market_name: m, outcome_name: "Will Smith: 1+ ", threshold: 1, player_team: "away" }),
      prop({ market_name: m, outcome_name: "Will Smith: 2+", threshold: 2, player_team: null }),
    ];
    const keys = coverage(rows);
    expect(keys.has(`${m}|Will Smith: 1+`)).toBe(true);
    expect(keys.has(`${m}|Will Smith: 1+ `)).toBe(true);
    expect(keys.has(`${m}|Will Smith: 2+`)).toBe(false);
  });

  it("a row missing either name has no key the server and page spell alike, so it claims nothing", () => {
    const rows = [prop({ market_name: null, outcome_name: "Alabama: 2+" })];
    expect(coverage(rows).size).toBe(0);
  });

  it("an `other[]` row can shape a card but never claims a script key", () => {
    const other: OtherMarketRow[] = [
      { market_name: "Alabama vs Mississippi St.: Receptions", outcome_name: "Ryan Williams: 5+", probability: 0.4, source: "kalshi" },
    ];
    expect(groupPlayerProps({ playerProps: [], other }).players.length).toBeGreaterThan(0);
    expect(coverage([], other).size).toBe(0);
  });

  it("partial coverage: a script key the fold never saw stays, in place", () => {
    const script = [
      ...scriptOf(SIX.slice(0, 3)),
      { key: `${MARKET}|Alabama: 9+`, label: "Alabama: 9+", pregame_mark: 0.01, current: 0.01, graded_result: null, settled: false },
    ];
    const kept = dropScriptRowsTheFoldDraws(script, { ...PREGAME, representedKeys: coverage(SIX.slice(0, 3)) });
    expect(kept.map((r) => r.key)).toEqual([`${MARKET}|Alabama: 9+`]);
  });

  it("a mark with no string key is never removed", () => {
    const keys = coverage(SIX);
    const rows = [
      { key: null, graded_result: null, settled: false },
      { key: 7, graded_result: null, settled: false },
    ];
    expect(dropScriptRowsTheFoldDraws(rows, { ...PREGAME, representedKeys: keys })).toEqual(rows);
  });
});

describe("#10340 a result is never removed", () => {
  it("a settled or graded closed-window row stays even before kickoff, even when its key is covered", () => {
    const script = scriptOf(SIX);
    script[1] = { ...script[1], settled: true };
    script[4] = { ...script[4], graded_result: "hit" };
    const kept = dropScriptRowsTheFoldDraws(script, { ...PREGAME, representedKeys: coverage(SIX) });
    expect(kept).toEqual([script[1], script[4]]);
  });
});

describe("#10340 only a KNOWN pregame page filters", () => {
  it.each([
    ["scheduled", false, true],
    ["Scheduled", false, true],
    ["scheduled", true, false], // start passed, status not caught up: uncertain
    ["live", false, false],
    ["suspended", false, false],
    ["completed", false, false],
    ["closed", false, false],
    ["final", false, false],
    ["", false, false],
    [null, false, false],
    [undefined, false, false],
    ["postponed", false, false],
  ])("status %p, start passed %p -> known pregame %p", (status, passed, expected) => {
    expect(isKnownPregameForScript(status as string | null | undefined, passed)).toBe(expected);
  });

  it("live, final and unknown pass the original array through untouched", () => {
    const script = scriptOf(SIX);
    const keys = coverage(SIX);
    for (const status of ["live", "completed", "closed", "suspended", "", "wat"]) {
      const out = dropScriptRowsTheFoldDraws(script, {
        knownPregame: isKnownPregameForScript(status, false),
        representedKeys: keys,
      });
      expect(out).toBe(script);
    }
  });

  it("no coverage at all passes the original array through", () => {
    const script = scriptOf(SIX);
    expect(dropScriptRowsTheFoldDraws(script, { ...PREGAME, representedKeys: new Set() })).toBe(script);
    expect(dropScriptRowsTheFoldDraws(script, { ...PREGAME, representedKeys: null })).toBe(script);
  });
});

describe("#10340 survivors keep their order and identity", () => {
  it("the rows that stay are the same objects, in the served order", () => {
    const rows = [
      prop({ outcome_name: "Alabama: 2+", threshold: 2 }),
      prop({ outcome_name: "Alabama: 3+", threshold: 3 }), // line's hidden rung
      prop({ outcome_name: "Alabama: 7+", threshold: null }), // rejected
      prop({ outcome_name: "Mississippi St.: 2+", threshold: 2 }),
    ];
    const script = scriptOf(rows);
    const kept = dropScriptRowsTheFoldDraws(script, { ...PREGAME, representedKeys: coverage(rows) });
    expect(kept).toHaveLength(2);
    expect(kept[0]).toBe(script[1]);
    expect(kept[1]).toBe(script[2]);
  });
});

describe("#10340 the trace leaves the grouping exactly as it was", () => {
  type Capture = { home_team: string; away_team: string; player_props: PlayerPropRow[]; other: OtherMarketRow[] };
  const CAPTURES = fixture as unknown as Record<string, Capture>;

  it.each(Object.keys(CAPTURES))("production capture %s: same players, drops and empty reason", (id) => {
    const c = CAPTURES[id];
    const input = { playerProps: c.player_props, other: c.other, homeTeam: c.home_team, awayTeam: c.away_team };
    const plain = groupPlayerProps(input);
    const traced = groupPlayerPropsWithCoverage(input);
    expect(traced.players).toEqual(plain.players);
    expect(traced.dropped).toEqual(plain.dropped);
    expect(traced.emptyReason).toBe(plain.emptyReason);

    // Every claimed key belongs to a served player_props row, and a line's
    // second threshold is never claimed through its rung.
    const served = new Set(c.player_props.map((r) => `${r.market_name}|${r.outcome_name}`));
    for (const k of traced.representedScriptKeys) expect(served.has(k)).toBe(true);
    expect(traced.representedScriptKeys.size).toBeGreaterThan(0);
  });
});

describe("#10340 page wiring", () => {
  const page = readFileSync(join(process.cwd(), "app/events/[id]/page.tsx"), "utf8");
  const dashboard = readFileSync(join(process.cwd(), "components/PlayerPropsDashboard.tsx"), "utf8");

  it("THE SCRIPT's input is filtered before the grade mapping, on the page's pregame read", () => {
    const start = page.indexOf("const servedScript = gameMarkets?.props_script;");
    const end = page.indexOf("<PropsSection", start);
    expect(start).toBeGreaterThan(0);
    expect(end).toBeGreaterThan(start);
    const block = page.slice(start, end);
    expect(block).toContain("isKnownPregameForScript(event.status, hasStarted)");
    expect(block).toContain("dropScriptRowsTheFoldDraws(servedScript");
    expect(block).toContain(".representedScriptKeys");
    expect(block).toContain("if (propsScript.length === 0) return null;");
    // The grade mapping still reads the (filtered) array it always did.
    expect(page.slice(end, end + 1500)).toContain("items={propsScript");
  });

  it("coverage is grouped over the same inputs the fold's dashboard passes", () => {
    for (const field of ["playerProps: data.player_props", "other: data.other", "homeTeam,", "awayTeam,"]) {
      expect(dashboard).toContain(field);
    }
    const start = page.indexOf("groupPlayerPropsWithCoverage({");
    const call = page.slice(start, page.indexOf("}).representedScriptKeys", start));
    for (const field of [
      "playerProps: gameMarkets?.player_props",
      "other: gameMarkets?.other",
      "homeTeam: event.home_team",
      "awayTeam: event.away_team",
    ]) {
      expect(call).toContain(field);
    }
  });

  it("the rail, the All-N fold and its dashboard are unchanged", () => {
    expect(page).toContain("<PropDivergenceRail\n              playerProps={gameMarkets.player_props}\n              status={event.status}");
    expect(page).toContain('All {countOf(gameMarkets.player_props.length, "prop", "props")}');
    expect(page).toContain("<PlayerPropsDashboard\n                data={gameMarkets}");
  });
});
