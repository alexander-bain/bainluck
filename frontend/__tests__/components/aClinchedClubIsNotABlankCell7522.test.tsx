// #7522 — the team page's Division Race must render a SETTLED cell as a result.
//
// The producer half (#7387, live 2026-09-20 v4821) stopped the championship grid
// deleting graded legs, so `/api/playoffs/{league}` now publishes terminal cells:
// `{"merged_probability": null, "state": "won"}`. On the first read after that
// release the MLB grid carried 5 `won` and 11 `eliminated` make_playoffs cells.
//
// The Division Race read `merged_probability` and nothing else, so the strongest
// answer we have — this club has CLINCHED — rendered as the same "—" that means
// "we have no market". A row could read "Division 96% · Playoffs —", which is
// not merely unhelpful: division is a subset of playoffs, so the row contradicts
// itself and the natural reading of the dash is the exact opposite of the truth.
//
// These are SSR assertions on rendered HTML, not on the projection — the
// projection has its own arms in `__tests__/lib/teamDivisionRace.test.ts`. Both
// layers are needed: a correct status that the component drops on the floor is
// still a blank cell to a reader.
import { renderToStaticMarkup } from "react-dom/server";
import React from "react";

import { TeamDivisionRace } from "../../components/TeamDivisionRace";
import { buildDivisionRace } from "../../lib/teamDivisionRace";
import type { ChampionshipGridResponse, ChampionshipGridTeam } from "../../lib/types";

const WON = { merged_probability: null, state: "won", sources: [], trend_24h: null };
const OUT = { merged_probability: null, state: "eliminated", sources: [], trend_24h: null };
const live = (p: number) => ({ merged_probability: p, sources: [], trend_24h: null });

function gTeam(o: Partial<ChampionshipGridTeam>): ChampionshipGridTeam {
  return {
    name: "T", short_name: "T", team_id: null, logo_url: null,
    primary_color: null, secondary_color: null, record: null,
    conference: null, division: null, region: null, seed: null, cells: {}, ...o,
  };
}

function gridOf(
  teams: ChampionshipGridTeam[],
  columns: unknown[] = [],
): ChampionshipGridResponse {
  return {
    league: "mlb", name: "MLB", season: "2026", columns, teams,
    grouped_teams: null, movers: [],
    trend_chart: { column: "championship", top: 5, timeline: [] },
    team_count: teams.length, last_updated: "", sources_available: [],
  } as unknown as ChampionshipGridResponse;
}

// The AL East as the payload actually carried it on 2026-09-20: Tampa Bay had
// clinched a berth while leading the division at 96%, Toronto was out, Boston
// was 99% to reach the playoffs through a wild card with the division gone.
const AL_EAST_LATE_SEASON = [
  gTeam({
    name: "Tampa Bay Rays", short_name: "TB", team_id: 139, division: "AL East",
    cells: { division: live(0.96), make_playoffs: WON, championship: live(0.093) },
  }),
  gTeam({
    name: "Boston Red Sox", short_name: "BOS", team_id: 111, division: "AL East",
    primary_color: "#BD3039",
    cells: { division: OUT, make_playoffs: live(0.99), championship: live(0.055) },
  }),
  gTeam({
    name: "Toronto Blue Jays", short_name: "TOR", team_id: 141, division: "AL East",
    cells: { division: OUT, make_playoffs: OUT, championship: OUT },
  }),
];

function renderAlEast(): string {
  const race = buildDivisionRace(gridOf(AL_EAST_LATE_SEASON), 111, "Boston Red Sox")!;
  return renderToStaticMarkup(<TeamDivisionRace race={race} teamColor="#BD3039" />);
}

describe("a clinched club is not a blank cell [#7522]", () => {
  test("the clinched and eliminated marks reach the page", () => {
    const html = renderAlEast();
    expect(html).toContain("✓");
    expect(html).toContain("✕");
  });

  test("every terminal cell is NAMED, so the mark is not a mystery glyph", () => {
    const html = renderAlEast();
    // One `won` cell in this fixture, four `eliminated` ones. Each carries both
    // an accessible name and a hover title — a bare ✓ tells a screen reader
    // nothing, and D102 keeps the word off the visible row.
    expect(html.split('aria-label="Clinched"').length - 1).toBe(1);
    expect(html.split('aria-label="Eliminated"').length - 1).toBe(4);
    expect(html).toContain('title="Clinched"');
  });

  test("the marks land on the RIGHT clubs, not merely somewhere on the page", () => {
    const html = renderAlEast();
    // A count alone would pass if every glyph landed on one row. Anchor each
    // mark to the row it belongs to by slicing the HTML between team names.
    const rowOf = (name: string) => {
      const start = html.indexOf(name);
      expect(start).toBeGreaterThan(-1);
      const rest = html.slice(start);
      const next = ["Tampa Bay Rays", "Boston Red Sox", "Toronto Blue Jays"]
        .map((n) => rest.indexOf(n, 1))
        .filter((i) => i > 0);
      return next.length ? rest.slice(0, Math.min(...next)) : rest;
    };
    // Tampa Bay: clinched the berth, still a live 96% for the division.
    expect(rowOf("Tampa Bay Rays")).toContain('aria-label="Clinched"');
    expect(rowOf("Tampa Bay Rays")).toContain("96%");
    // Boston: out of the division, but 99% live for a wild card — a result and
    // a probability on the same row, each rendered as what it is.
    expect(rowOf("Boston Red Sox")).toContain('aria-label="Eliminated"');
    expect(rowOf("Boston Red Sox")).toContain("99%");
    // Toronto: out of everything, and no number anywhere on the row.
    expect(rowOf("Toronto Blue Jays")).not.toMatch(/\d+%/);
  });

  test("🔴 the defect itself: a clinched cell no longer renders as the em-dash", () => {
    const html = renderAlEast();
    // The dash is reserved for "no market". This fixture has no such cell, so a
    // single "—" anywhere in the table body is the bug coming back.
    const body = html.slice(html.indexOf("Tampa Bay Rays"));
    expect(body).not.toContain("—");
  });

  test("a club with genuinely no market still gets the em-dash, not a verdict", () => {
    // The opposite failure — dressing an absence up as a result — would be worse
    // than the bug being fixed. Playoffs is present for one club and absent for
    // the other, so the column renders and one cell has nothing to say.
    const teams = [
      gTeam({ name: "Has Market", short_name: "HAS", team_id: 1, division: "D",
        cells: { division: live(0.5), make_playoffs: live(0.7) } }),
      gTeam({ name: "No Market", short_name: "NON", team_id: 2, division: "D",
        cells: { division: live(0.5) } }),
    ];
    const race = buildDivisionRace(gridOf(teams), 2, "No Market")!;
    const html = renderToStaticMarkup(<TeamDivisionRace race={race} teamColor={null} />);
    expect(html).toContain("—");
    expect(html).toContain('aria-label="No market"');
    expect(html).not.toContain("✓");
    expect(html).not.toContain("✕");
  });

  test("the champion is still crowned when the win carries no number", () => {
    // `championship >= 0.999` found the champion while a settled cell still
    // carried 1.0. A `won` cell publishes no number, so the crown would have
    // vanished from exactly the grids that had a champion to crown.
    const teams = [
      gTeam({ name: "Boston Celtics", short_name: "BOS", team_id: 200, division: "Atlantic",
        cells: { division: WON, make_playoffs: WON, championship: WON } }),
      gTeam({ name: "New York Knicks", short_name: "NYK", team_id: 201, division: "Atlantic",
        cells: { division: OUT, make_playoffs: WON, championship: OUT } }),
    ];
    const race = buildDivisionRace(
      gridOf(teams, [
        { key: "championship", label: "Champion", order: 3, sequential: false, resolved: true },
      ]),
      200,
      "Boston Celtics",
    )!;
    // The column is all-result, so it must still be on the page at all.
    expect(race.hasChampionship).toBe(true);
    const html = renderToStaticMarkup(<TeamDivisionRace race={race} teamColor="#007A33" />);
    expect(html).toContain("FINAL");
    expect(html).toContain("Champion");
    expect(html.split("🏆").length - 1).toBe(1);
    // …and on the winner, not the runner-up.
    const knicks = html.indexOf("New York Knicks");
    expect(html.indexOf("🏆")).toBeLessThan(knicks);
  });
});
