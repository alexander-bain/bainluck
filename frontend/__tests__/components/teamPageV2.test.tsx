// L2-162: SSR render guards for the team-page v2 sections. Both directions:
//  - championship-path progression renders its steps in easy→hard order,
//  - division-race grid renders every rival row and highlights the team,
//  - both generalize across MLB / NBA / NFL shapes,
//  - and neither crashes on the empty/degenerate inputs the page can pass.
import { renderToStaticMarkup } from "react-dom/server";
import React from "react";

jest.mock("next/link", () => ({
  __esModule: true,
  default: ({ href, children }: { href: string; children: React.ReactNode }) => (
    <a href={href}>{children}</a>
  ),
}));

import { TeamChampionshipPath } from "../../components/TeamChampionshipPath";
import { TeamDivisionRace } from "../../components/TeamDivisionRace";
import { buildDivisionRace } from "../../lib/teamDivisionRace";
import type { ChampionshipPathEntry } from "../../lib/api";
import type { ChampionshipGridResponse, ChampionshipGridTeam } from "../../lib/types";

function pathEntry(overrides: Partial<ChampionshipPathEntry>): ChampionshipPathEntry {
  return {
    tier: 1,
    label: "Championship",
    market_name: "World Series",
    market_id: 1,
    probability: 0.04,
    rank: null,
    movement: null,
    ...overrides,
  };
}

function cell(p: number) {
  return { merged_probability: p, sources: [], trend_24h: null };
}
function gTeam(o: Partial<ChampionshipGridTeam>): ChampionshipGridTeam {
  return {
    name: "T", short_name: "T", team_id: null, logo_url: null,
    primary_color: null, secondary_color: null, record: null,
    conference: null, division: null, region: null, seed: null, cells: {}, ...o,
  };
}
function gridOf(teams: ChampionshipGridTeam[]): ChampionshipGridResponse {
  return {
    league: "x", name: "X", season: null, columns: [], teams,
    grouped_teams: null, movers: [],
    trend_chart: { column: "championship", top: 5, timeline: [] },
    team_count: teams.length, last_updated: "", sources_available: [],
  } as unknown as ChampionshipGridResponse;
}

describe("TeamChampionshipPath", () => {
  test("renders steps in Division → Conference → Championship order", () => {
    const html = renderToStaticMarkup(
      <TeamChampionshipPath
        color="#BD3039"
        entries={[
          pathEntry({ tier: 1, label: "Championship", probability: 0.04 }),
          pathEntry({ tier: 2, label: "Conference", probability: 0.08, market_id: 2 }),
          pathEntry({ tier: 4, label: "Division", probability: 0.14, market_id: 3 }),
        ]}
      />,
    );
    expect(html).toContain("Championship path");
    expect(html).toContain("Win Division");
    expect(html).toContain("Win Conference");
    expect(html).toContain("Win Championship");
    // Division (easiest) precedes Championship (hardest) in the markup.
    expect(html.indexOf("Win Division")).toBeLessThan(html.indexOf("Win Championship"));
    expect(html).toContain("14%");
    expect(html).toContain("4%");
  });

  test("does not crash on a single-step path or null probability", () => {
    const html = renderToStaticMarkup(
      <TeamChampionshipPath
        color={null}
        entries={[pathEntry({ tier: 4, label: "Division", probability: null })]}
      />,
    );
    expect(html).toContain("Win Division");
    expect(html).toContain("—");
  });
});

describe("TeamDivisionRace across leagues", () => {
  function raceFor(division: string, teamId: number, name: string) {
    const teams = [
      gTeam({ name, short_name: name.slice(0, 3), team_id: teamId, division, primary_color: "#111",
        cells: { division: cell(0.2), make_playoffs: cell(0.4), championship: cell(0.05) } }),
      gTeam({ name: "Rival A", short_name: "RVA", team_id: teamId + 1, division,
        cells: { division: cell(0.5), make_playoffs: cell(0.8), championship: cell(0.2) } }),
      gTeam({ name: "Rival B", short_name: "RVB", team_id: teamId + 2, division,
        cells: { division: cell(0.3), make_playoffs: cell(0.6), championship: cell(0.1) } }),
    ];
    return buildDivisionRace(gridOf(teams), teamId, name)!;
  }

  test.each([
    ["MLB", "AL East", 111, "Boston Red Sox"],
    ["NBA", "Atlantic", 200, "Boston Celtics"],
    ["NFL", "AFC East", 300, "Buffalo Bills"],
  ])("%s division race renders all rivals + header", (_league, div, id, name) => {
    const race = raceFor(div, id as number, name as string);
    const html = renderToStaticMarkup(
      <TeamDivisionRace race={race} teamColor="#0A0A0A" />,
    );
    expect(html).toContain(name as string);
    expect(html).toContain("Rival A");
    expect(html).toContain("Rival B");
    expect(html).toContain(div as string); // header carries the division label
    expect(html).toContain("Playoffs");
    expect(html).toContain("Champion");
  });

  test("omits a column entirely when no team has that stage's data", () => {
    const teams = [
      gTeam({ name: "A", team_id: 1, division: "D",
        cells: { make_playoffs: cell(0.4), championship: cell(0.1) } }),
      gTeam({ name: "B", team_id: 2, division: "D",
        cells: { make_playoffs: cell(0.6), championship: cell(0.2) } }),
    ];
    const race = buildDivisionRace(gridOf(teams), 1, "A")!;
    const html = renderToStaticMarkup(<TeamDivisionRace race={race} teamColor={null} />);
    expect(html).not.toContain("Division ↓");
    expect(html).toContain("Playoffs");
  });
});
