// L2-162: division-race projection from the league championship grid.
import { buildDivisionRace, sortDivisionRows } from "../../lib/teamDivisionRace";
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

  test("returns null on missing/errored grid", () => {
    expect(buildDivisionRace(null, 1, "A")).toBeNull();
    expect(
      buildDivisionRace({ error: "timeout" } as unknown as ChampionshipGridResponse, 1, "A"),
    ).toBeNull();
  });
});

describe("sortDivisionRows", () => {
  const rows = [
    { teamId: 1, name: "A", shortName: "A", color: null, logoUrl: null, isTeam: false, division: 0.1, playoffs: 0.5, championship: 0.02 },
    { teamId: 2, name: "B", shortName: "B", color: null, logoUrl: null, isTeam: false, division: 0.4, playoffs: null, championship: 0.2 },
  ];

  test("sorts by the chosen column descending, nulls last", () => {
    expect(sortDivisionRows(rows, "division").map((r) => r.name)).toEqual(["B", "A"]);
    expect(sortDivisionRows(rows, "playoffs").map((r) => r.name)).toEqual(["A", "B"]);
  });
});
