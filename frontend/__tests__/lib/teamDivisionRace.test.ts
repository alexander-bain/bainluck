// L2-162: division-race projection from the league championship grid.
import { buildDivisionRace, sortDivisionRows } from "../../lib/teamDivisionRace";
import type { DivisionRaceRow } from "../../lib/teamDivisionRace";
import type { ChampionshipGridResponse, ChampionshipGridTeam } from "../../lib/types";

function cell(p: number) {
  return { merged_probability: p, sources: [], trend_24h: null };
}

function team(overrides: Partial<ChampionshipGridTeam>): ChampionshipGridTeam {
  return {
    name: "Team",
    short_name: "TM",
    team_id: null,
    logo_url: null,
    primary_color: null,
    secondary_color: null,
    record: null,
    conference: null,
    division: null,
    region: null,
    seed: null,
    cells: {},
    ...overrides,
  };
}

function grid(teams: ChampionshipGridTeam[]): ChampionshipGridResponse {
  return {
    league: "mlb",
    name: "MLB",
    season: "2026",
    columns: [],
    teams,
    grouped_teams: null,
    movers: [],
    trend_chart: { column: "championship", top: 5, timeline: [] },
    team_count: teams.length,
    last_updated: "",
    sources_available: [],
  } as unknown as ChampionshipGridResponse;
}

const AL_EAST = [
  team({
    name: "Boston Red Sox", short_name: "BOS", team_id: 111, division: "AL East",
    primary_color: "#BD3039",
    cells: { division: cell(0.14), make_playoffs: cell(0.31), championship: cell(0.04) },
  }),
  team({
    name: "New York Yankees", short_name: "NYY", team_id: 147, division: "AL East",
    cells: { division: cell(0.48), make_playoffs: cell(0.86), championship: cell(0.12) },
  }),
  team({
    name: "Tampa Bay Rays", short_name: "TB", team_id: 139, division: "AL East",
    cells: { division: cell(0.22), make_playoffs: cell(0.61), championship: cell(0.05) },
  }),
  // A different-division team that must be excluded.
  team({
    name: "Houston Astros", short_name: "HOU", team_id: 117, division: "AL West",
    cells: { division: cell(0.55), make_playoffs: cell(0.9), championship: cell(0.15) },
  }),
];

describe("buildDivisionRace", () => {
  test("filters to the team's division and highlights the team (by id)", () => {
    const race = buildDivisionRace(grid(AL_EAST), 111, "Boston Red Sox");
    expect(race).not.toBeNull();
    expect(race!.divisionLabel).toBe("AL East");
    expect(race!.rows).toHaveLength(3); // Astros excluded
    expect(race!.rows.every((r) => r.name !== "Houston Astros")).toBe(true);
    const me = race!.rows.find((r) => r.isTeam);
    expect(me?.name).toBe("Boston Red Sox");
    // Others are not flagged as the team.
    expect(race!.rows.filter((r) => r.isTeam)).toHaveLength(1);
  });

  test("defaults to championship-descending order", () => {
    const race = buildDivisionRace(grid(AL_EAST), 111, "Boston Red Sox");
    expect(race!.rows.map((r) => r.name)).toEqual([
      "New York Yankees", // 12%
      "Tampa Bay Rays", // 5%
      "Boston Red Sox", // 4%
    ]);
  });

  test("threads the season label through for the header chip when present", () => {
    const race = buildDivisionRace(grid(AL_EAST), 111, "Boston Red Sox");
    expect(race!.season).toBe("2026");
  });

  test("season is null when the grid provides none (chip stays hidden, never guessed)", () => {
    const g = grid(AL_EAST);
    (g as { season: string | null }).season = null;
    expect(buildDivisionRace(g, 111, "Boston Red Sox")!.season).toBeNull();
    const blank = grid(AL_EAST);
    (blank as { season: string | null }).season = "   ";
    expect(buildDivisionRace(blank, 111, "Boston Red Sox")!.season).toBeNull();
  });

  test("matches by normalized name when the grid has no team_id", () => {
    const teams = AL_EAST.map((t) => team({ ...t, team_id: null }));
    const race = buildDivisionRace(grid(teams), 999, "boston red sox");
    expect(race!.rows.find((r) => r.isTeam)?.name).toBe("Boston Red Sox");
  });

  test("returns null when the team is not in the grid", () => {
    expect(buildDivisionRace(grid(AL_EAST), 555, "Nonexistent FC")).toBeNull();
  });

  test("returns null when the team has no division metadata or no peers", () => {
    const solo = [team({ name: "Solo", team_id: 1, division: "Only", cells: {} })];
    expect(buildDivisionRace(grid(solo), 1, "Solo")).toBeNull();
    const noDiv = [
      team({ name: "A", team_id: 1, division: null }),
      team({ name: "B", team_id: 2, division: null }),
    ];
    expect(buildDivisionRace(grid(noDiv), 1, "A")).toBeNull();
  });

  test("L2-174: championshipResolved reflects the grid's championship column resolved flag", () => {
    // Settled-means-settled: a resolved championship column marks the whole race
    // graded so the component crowns the champion instead of framing a live race.
    const g = grid(AL_EAST);
    (g as { columns: unknown[] }).columns = [
      { key: "championship", label: "Champion", order: 3, sequential: false, resolved: true },
    ];
    expect(buildDivisionRace(g, 111, "Boston Red Sox")!.championshipResolved).toBe(true);
    // Absent/false flag → a live race (the default fixture has columns: []).
    expect(
      buildDivisionRace(grid(AL_EAST), 111, "Boston Red Sox")!.championshipResolved,
    ).toBe(false);
  });

  test("returns null on missing/errored grid", () => {
    expect(buildDivisionRace(null, 1, "A")).toBeNull();
    expect(
      buildDivisionRace({ error: "timeout" } as unknown as ChampionshipGridResponse, 1, "A"),
    ).toBeNull();
  });
});

// ---------------------------------------------------------------------------
// #6992 — the peer pool is the (conference, division) PAIR.
//
// 🔴 THE FIXTURE ABOVE IS WHY THIS SUITE WAS GREEN OVER A LIVE DEFECT. `AL_EAST`
// uses `division: "AL East"` with `conference: null` — a pre-qualified string that
// `/api/playoffs/mlb` has never served. Production serves the division UNQUALIFIED
// ("East") with the league in `conference` ("American League"), and under that real
// shape the division name alone matched ten teams. A fixture that pre-qualifies the
// key encodes the answer, so the guard could not see the question.
//
// These cases use the shape measured off the four live grids on 2026-09-18:
//   mlb  East/Central/West        shared by both leagues   -> 10 per name  (trips)
//   nfl  AFC East … NFC West      pre-qualified            -> 4 per name
//   nba  Atlantic/Pacific/…       unique across conferences-> 5 per name
//   nhl  Atlantic Division/…      unique across conferences-> 8 per name
// `conference` was populated on 100% of rows in all four.
// ---------------------------------------------------------------------------
describe("buildDivisionRace — the pool is (conference, division) [#6992]", () => {
  /** Production's real MLB shape: unqualified division, league in `conference`. */
  const MLB_EAST_BOTH_LEAGUES = [
    team({
      name: "Tampa Bay Rays", short_name: "TB", team_id: 139,
      conference: "American League", division: "East",
      cells: { division: cell(0.943), make_playoffs: cell(1), championship: cell(0.11) },
    }),
    team({
      name: "Atlanta Braves", short_name: "ATL", team_id: 144,
      conference: "National League", division: "East",
      cells: { division: cell(0.984), make_playoffs: cell(1), championship: cell(0.07) },
    }),
    team({
      name: "New York Yankees", short_name: "NYY", team_id: 147,
      conference: "American League", division: "East",
      cells: { division: cell(0.058), make_playoffs: cell(1), championship: cell(0.06) },
    }),
    team({
      name: "Boston Red Sox", short_name: "BOS", team_id: 111,
      conference: "American League", division: "East",
      cells: { division: cell(0.007), make_playoffs: cell(0.99), championship: cell(0.01) },
    }),
    team({
      name: "New York Mets", short_name: "NYM", team_id: 121,
      conference: "National League", division: "East",
      cells: { division: cell(0.005), make_playoffs: cell(0.01), championship: cell(0.004) },
    }),
    // A same-league, different-division club: still excluded, as before.
    team({
      name: "Houston Astros", short_name: "HOU", team_id: 117,
      conference: "American League", division: "West",
      cells: { division: cell(0.72), make_playoffs: cell(0.79), championship: cell(0.04) },
    }),
  ];

  test("an MLB team's race lists only its OWN league's division rivals", () => {
    const race = buildDivisionRace(grid(MLB_EAST_BOTH_LEAGUES), 111, "Boston Red Sox")!;
    expect(race).not.toBeNull();
    expect(race.rows.map((r) => r.name).sort()).toEqual([
      "Boston Red Sox",
      "New York Yankees",
      "Tampa Bay Rays",
    ]);
    // The National League East clubs the Red Sox cannot finish above are gone...
    expect(race.rows.some((r) => r.name === "Atlanta Braves")).toBe(false);
    expect(race.rows.some((r) => r.name === "New York Mets")).toBe(false);
    // ...and so is the same-league club from another division.
    expect(race.rows.some((r) => r.name === "Houston Astros")).toBe(false);
    // The team's own row always survives the narrowing — it is the highlighted one.
    expect(race.rows.find((r) => r.isTeam)?.name).toBe("Boston Red Sox");
  });

  test("the DIVISION column describes one race: a single leader, summing near 100%", () => {
    const race = buildDivisionRace(grid(MLB_EAST_BOTH_LEAGUES), 111, "Boston Red Sox")!;
    const divs = race.rows.map((r) => r.division ?? 0);
    const sum = divs.reduce((a, b) => a + b, 0);
    // Before the fix this column held Rays 0.943 AND Braves 0.984 and summed to
    // ~2.0 — two teams each ~certain to win the same division.
    expect(divs.filter((v) => v > 0.5)).toHaveLength(1);
    expect(sum).toBeLessThan(1.3);
    expect(sum).toBeGreaterThan(0.9);
  });

  test("the other league's page gets the other race, not a mirror of the same rows", () => {
    const race = buildDivisionRace(grid(MLB_EAST_BOTH_LEAGUES), 144, "Atlanta Braves")!;
    expect(race.rows.map((r) => r.name).sort()).toEqual(["Atlanta Braves", "New York Mets"]);
    expect(race.rows.filter((r) => (r.division ?? 0) > 0.5)).toHaveLength(1);
  });

  test("leagues whose division names are already unique are untouched", () => {
    // NFL pre-qualifies the name; the conference clause must narrow nothing.
    const nfl = [
      team({ name: "Buffalo Bills", team_id: 1, conference: "American Football Conference", division: "AFC East", cells: { division: cell(0.68) } }),
      team({ name: "New England Patriots", team_id: 2, conference: "American Football Conference", division: "AFC East", cells: { division: cell(0.23) } }),
      team({ name: "Miami Dolphins", team_id: 3, conference: "American Football Conference", division: "AFC East", cells: { division: cell(0.02) } }),
      team({ name: "New York Jets", team_id: 4, conference: "American Football Conference", division: "AFC East", cells: { division: cell(0.06) } }),
      team({ name: "Dallas Cowboys", team_id: 5, conference: "National Football Conference", division: "NFC East", cells: { division: cell(0.4) } }),
    ];
    expect(buildDivisionRace(grid(nfl), 1, "Buffalo Bills")!.rows).toHaveLength(4);
    // NBA: names unique across conferences, so "Atlantic" is one pool already.
    const nba = [
      team({ name: "Boston Celtics", team_id: 10, conference: "Eastern Conference", division: "Atlantic", cells: { division: cell(0.25) } }),
      team({ name: "New York Knicks", team_id: 11, conference: "Eastern Conference", division: "Atlantic", cells: { division: cell(0.35) } }),
      team({ name: "Denver Nuggets", team_id: 12, conference: "Western Conference", division: "Northwest", cells: { division: cell(0.5) } }),
    ];
    expect(buildDivisionRace(grid(nba), 10, "Boston Celtics")!.rows).toHaveLength(2);
  });

  test("FAILS OPEN: our conference unknown but our peers' known — section survives", () => {
    // 🔴 THE CASE HAS TO BE *PARTIAL*. Nulling every row's conference does NOT test
    // this: `null === null` is true, so the strict form `t.conference ===
    // me.conference` keeps all five rows too and the mutant walks. The only shape
    // that separates them is OUR row unlabelled while the peers carry a league —
    // there the strict form matches nobody but us, `peers.length < 2` fires, and the
    // whole Division Race section disappears from the page with no trace for a
    // reader or a probe. We cannot narrow honestly without our own conference, so we
    // keep the wider pool instead of emptying the surface.
    const meUnlabelled = MLB_EAST_BOTH_LEAGUES.map((t) =>
      t.team_id === 111 ? team({ ...t, conference: null }) : t,
    );
    const race = buildDivisionRace(grid(meUnlabelled), 111, "Boston Red Sox");
    expect(race).not.toBeNull();
    expect(race!.rows).toHaveLength(5); // every "East" row, Astros still excluded
    expect(race!.rows.some((r) => r.name === "Houston Astros")).toBe(false);
    expect(race!.rows.find((r) => r.isTeam)?.name).toBe("Boston Red Sox");
  });

  test("a peer with no conference is excluded when ours is known", () => {
    // Deliberate, not an oversight: an unlabelled row cannot be shown to be in our
    // league, and admitting it is how the 206% column came back. Pinned so the
    // trade is a decision on the record rather than an accident.
    const mixed = [
      ...MLB_EAST_BOTH_LEAGUES,
      team({ name: "Mystery Club", team_id: 900, conference: null, division: "East", cells: { division: cell(0.9) } }),
    ];
    const race = buildDivisionRace(grid(mixed), 111, "Boston Red Sox")!;
    expect(race.rows.some((r) => r.name === "Mystery Club")).toBe(false);
  });
});

function row(overrides: Partial<DivisionRaceRow>): DivisionRaceRow {
  return {
    teamId: null,
    name: "Row",
    shortName: "R",
    color: null,
    logoUrl: null,
    isTeam: false,
    division: null,
    playoffs: null,
    championship: null,
    divisionStatus: null,
    playoffsStatus: null,
    championshipStatus: null,
    ...overrides,
  };
}

describe("sortDivisionRows", () => {
  const rows = [
    row({ teamId: 1, name: "A", shortName: "A", division: 0.1, playoffs: 0.5, championship: 0.02 }),
    row({ teamId: 2, name: "B", shortName: "B", division: 0.4, playoffs: null, championship: 0.2 }),
  ];

  test("sorts by the chosen column descending, nulls last", () => {
    expect(sortDivisionRows(rows, "division").map((r) => r.name)).toEqual(["B", "A"]);
    expect(sortDivisionRows(rows, "playoffs").map((r) => r.name)).toEqual(["A", "B"]);
  });
});

// ---------------------------------------------------------------------------
// #7522 — a settled cell is a RESULT, not a missing number.
//
// #7387 stopped the grid deleting graded legs, so `/api/playoffs/{league}` now
// publishes `{"merged_probability": null, "state": "won"|"eliminated"}`. Every
// assertion below was RED against the pre-#7522 projection, which read
// `merged_probability` alone and could not tell "we are certain" from "we have
// nothing". The shapes are the live payload's, not invented: on 2026-09-20 the
// MLB grid carried 5 `won` and 11 `eliminated` make_playoffs cells.
// ---------------------------------------------------------------------------
describe("terminal cells on the Division Race [#7522]", () => {
  const wonCell = { merged_probability: null, state: "won", sources: [], trend_24h: null };
  const outCell = { merged_probability: null, state: "eliminated", sources: [], trend_24h: null };

  /** Rays clinched; Jays are out; Sox and Yanks still trading. */
  const SETTLING_AL_EAST = [
    team({
      name: "Tampa Bay Rays", short_name: "TB", team_id: 139, division: "AL East",
      cells: { division: cell(0.96), make_playoffs: wonCell, championship: cell(0.09) },
    }),
    team({
      name: "Toronto Blue Jays", short_name: "TOR", team_id: 141, division: "AL East",
      cells: { division: outCell, make_playoffs: outCell, championship: outCell },
    }),
    team({
      name: "Boston Red Sox", short_name: "BOS", team_id: 111, division: "AL East",
      cells: { division: cell(0.003), make_playoffs: cell(0.99), championship: cell(0.055) },
    }),
    team({
      name: "New York Yankees", short_name: "NYY", team_id: 147, division: "AL East",
      cells: { division: cell(0.038), make_playoffs: wonCell, championship: cell(0.1) },
    }),
  ];

  test("a clinched club carries the result, not a null that reads as no data", () => {
    const race = buildDivisionRace(grid(SETTLING_AL_EAST), 111, "Boston Red Sox")!;
    const rays = race.rows.find((r) => r.name === "Tampa Bay Rays")!;
    expect(rays.playoffsStatus).toBe("clinched");
    // The number is absent BY CONTRACT — the point is that the status says why.
    expect(rays.playoffs).toBeNull();
  });

  test("an eliminated club is told apart from a club with no market", () => {
    const race = buildDivisionRace(grid(SETTLING_AL_EAST), 111, "Boston Red Sox")!;
    const jays = race.rows.find((r) => r.name === "Toronto Blue Jays")!;
    expect(jays.playoffsStatus).toBe("eliminated");
    // 🔴 The whole defect in one line: before #7522 both of these were `null`
    // and the page printed the same "—" for each.
    const noMarket = buildDivisionRace(
      grid([
        team({ name: "X", team_id: 1, division: "D", cells: { division: cell(0.5) } }),
        team({ name: "Y", team_id: 2, division: "D", cells: { division: cell(0.5) } }),
      ]),
      1,
      "X",
    )!.rows[0];
    expect(noMarket.playoffsStatus).toBeNull();
    expect(noMarket.playoffs).toBeNull();
    expect(jays.playoffsStatus).not.toBe(noMarket.playoffsStatus);
  });

  test("a live cell is untouched — number kept, no status invented", () => {
    const race = buildDivisionRace(grid(SETTLING_AL_EAST), 111, "Boston Red Sox")!;
    const sox = race.rows.find((r) => r.name === "Boston Red Sox")!;
    expect(sox.playoffs).toBeCloseTo(0.99);
    expect(sox.playoffsStatus).toBeNull();
    expect(sox.division).toBeCloseTo(0.003);
  });

  test("a clinched club sorts as certainty, not below every longshot", () => {
    const race = buildDivisionRace(grid(SETTLING_AL_EAST), 111, "Boston Red Sox")!;
    const order = sortDivisionRows(race.rows, "playoffs").map((r) => r.name);
    // Both clinched clubs above the 99% live cell; the eliminated club last.
    expect(order.slice(0, 2).sort()).toEqual(["New York Yankees", "Tampa Bay Rays"]);
    expect(order[2]).toBe("Boston Red Sox");
    expect(order[3]).toBe("Toronto Blue Jays");
  });

  test("a column that is ALL result keeps its place on the page", () => {
    // 🔴 The trap the number-only test walked into: a race that is over carries
    // a probability nowhere, so `rows.some(r => r.division !== null)` went false
    // and the column disappeared at the exact moment it became certain.
    const decided = [
      team({ name: "Champ", team_id: 1, division: "D", cells: { division: wonCell } }),
      team({ name: "Rest", team_id: 2, division: "D", cells: { division: outCell } }),
    ];
    const race = buildDivisionRace(grid(decided), 1, "Champ")!;
    expect(race.hasDivision).toBe(true);
    expect(race.rows.every((r) => r.division === null)).toBe(true);
  });

  test("an absent column still hides, and an unreadable cell is never a result", () => {
    // Fail-closed, both directions: no column at all must not become a verdict,
    // and a cell the register cannot vouch for must not be dressed up as one.
    const junk = [
      team({ name: "P", team_id: 1, division: "D", cells: { division: cell(0.5), make_playoffs: { merged_probability: null, state: "nonsense", sources: [], trend_24h: null } } }),
      team({ name: "Q", team_id: 2, division: "D", cells: { division: cell(0.5) } }),
    ];
    const race = buildDivisionRace(grid(junk), 1, "P")!;
    expect(race.hasChampionship).toBe(false); // absent everywhere
    expect(race.hasPlayoffs).toBe(false); // present but unreadable — not a result
    const p = race.rows.find((r) => r.name === "P")!;
    expect(p.playoffsStatus).toBe("unavailable");
    expect(p.playoffs).toBeNull();
  });
});
