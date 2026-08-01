// L2-227: rendered truth for the five championship grids.
//
// Queue 295 put an explicit register behind the grid serving path, so a cell
// now arrives with a typed state instead of always arriving as a number. This
// suite is the guard that the *rendered* page honours that state: a settled
// cell shows its result, a missing cell shows an honest empty, and neither
// can show a live-looking percentage. It also pins the blast-radius rule —
// one poison cell cannot blank its row, its siblings, or the page.
//
// States and vocabulary come from the C108 contract corpus
// (backend/tests/evals/fixtures/grid_register_contract.json). The five states
// are not organic in production yet (the 2026-08-01 census returned `live` for
// 120/120 NBA, 120/120 MLB and 735/735 golf cells with no register published),
// so every non-live state here is proved with a fixed fixture.

import { renderToStaticMarkup } from "react-dom/server";
import React from "react";

jest.mock("@/hooks/useAnalytics", () => ({
  useAnalytics: () => ({ track: () => {} }),
}));

import TournamentProgressionTable from "../../components/TournamentProgressionTable";
import { gridCellsToProgression } from "../../lib/gridCellState";
import type {
  ChampionshipGridTeam,
  ProgressionResponse,
  ProgressionStage,
} from "../../lib/types";

// The five leagues the register targets, with their real column keys.
const LEAGUE_COLUMNS: Record<string, string[]> = {
  nba: ["make_playoffs", "division", "conference", "championship"],
  nhl: ["make_playoffs", "division", "conference", "championship"],
  mlb: ["make_playoffs", "division", "pennant", "championship"],
  nfl: ["make_playoffs", "division", "conference", "championship"],
  golf: ["make_cut", "top_20", "top_10", "top_5", "win"],
};

function stagesFor(league: string): ProgressionStage[] {
  return LEAGUE_COLUMNS[league].map((key, i) => ({
    key,
    label: key.replace(/_/g, " ").toUpperCase(),
    order: i,
    market_id: null,
    market_name: null,
    resolved: false,
  }));
}

/** Build a ProgressionResponse from raw payload teams, exactly as the pages do. */
function build(league: string, teams: { name: string; cells: unknown }[]): ProgressionResponse {
  return {
    sport: league,
    tournament_name: league.toUpperCase(),
    stages: stagesFor(league),
    participants: teams.map((t) => {
      const { probabilities, changes_24h, status, sources_data } = gridCellsToProgression(t.cells);
      return {
        name: t.name,
        team_id: null,
        logo_url: null,
        primary_color: null,
        conference: null,
        region: null,
        seed: null,
        record: null,
        probabilities,
        changes_24h,
        status,
        sources_data,
      };
    }),
  };
}

const live = (p: number) => ({ merged_probability: p, sources: [], trend_24h: null, state: "live" });
const settled = (result: "won" | "eliminated") => ({
  merged_probability: null,
  sources: [],
  trend_24h: null,
  state: result,
});
const missing = () => ({ merged_probability: null, sources: [], trend_24h: null, state: "missing" });
const unavailable = () => ({
  merged_probability: null,
  sources: [],
  trend_24h: null,
  state: "unavailable",
});

function render(data: ProgressionResponse): string {
  return renderToStaticMarkup(<TournamentProgressionTable data={data} pageType="playoff_grid" />);
}

// ---------------------------------------------------------------------------

describe.each(Object.keys(LEAGUE_COLUMNS))("%s grid — every C108 state renders honestly", (league) => {
  const cols = LEAGUE_COLUMNS[league];
  const last = cols[cols.length - 1];

  test("a live cell shows its number", () => {
    const html = render(build(league, [{ name: "Alpha", cells: { [last]: live(0.34) } }]));
    expect(html).toContain("34%");
    expect(html).toContain('data-cell-state="live"');
  });

  test("a won cell shows ✓ and no percentage", () => {
    const html = render(build(league, [{ name: "Alpha", cells: { [last]: settled("won") } }]));
    expect(html).toContain("✓");
    expect(html).toContain('data-cell-state="clinched"');
    expect(html).toContain('aria-label="Clinched"');
    expect(html).not.toMatch(/\d+(\.\d+)?%/);
  });

  test("an eliminated cell shows ✕ and no percentage", () => {
    const html = render(build(league, [{ name: "Alpha", cells: { [last]: settled("eliminated") } }]));
    expect(html).toContain("✕");
    expect(html).toContain('data-cell-state="eliminated"');
    expect(html).toContain('aria-label="Eliminated"');
    expect(html).not.toMatch(/\d+(\.\d+)?%/);
  });

  test("a missing cell shows an em-dash, never 50%", () => {
    const html = render(build(league, [{ name: "Alpha", cells: { [last]: missing() } }]));
    expect(html).toContain('data-cell-state="missing"');
    expect(html).toContain('aria-label="No market"');
    expect(html).toContain("—");
    expect(html).not.toContain("50%");
    expect(html).not.toMatch(/\d+(\.\d+)?%/);
  });

  test("an unavailable cell renders as unavailable, never as a number", () => {
    const html = render(build(league, [{ name: "Alpha", cells: { [last]: unavailable() } }]));
    expect(html).toContain('data-cell-state="unavailable"');
    expect(html).toContain('aria-label="Unavailable"');
    expect(html).not.toMatch(/\d+(\.\d+)?%/);
  });

  test("a settled cell whose payload still carries a stale number drops it", () => {
    const stale = { merged_probability: 0.91, sources: [], trend_24h: 0.2, state: "won" };
    const html = render(build(league, [{ name: "Alpha", cells: { [last]: stale } }]));
    expect(html).toContain("✓");
    expect(html).not.toContain("91%");
    // The 24h trend of a settled cell is not a live move either.
    expect(html).not.toContain("▲");
  });

  test("a full row of mixed states renders every cell and keeps the row intact", () => {
    const cells: Record<string, unknown> = {};
    const pattern = [live(0.62), settled("won"), missing(), settled("eliminated"), unavailable()];
    cols.forEach((c, i) => {
      cells[c] = pattern[i % pattern.length];
    });
    const html = render(build(league, [{ name: "Alpha", cells }]));
    expect(html).toContain("Alpha");
    // One <td> per stage, plus rank + name columns, in the single body row.
    const bodyRow = html.split("<tbody>")[1] ?? "";
    expect((bodyRow.match(/<td/g) || []).length).toBe(cols.length + 2);
  });
});

// ---------------------------------------------------------------------------

describe("blast radius — one bad cell cannot blank a row or the page", () => {
  const cols = LEAGUE_COLUMNS.nba;

  const POISON: { name: string; value: unknown }[] = [
    { name: "null", value: null },
    { name: "string", value: "0.5" },
    { name: "array", value: [0.5] },
    { name: "number", value: 0.5 },
    { name: "unknown state", value: { state: "banana", merged_probability: 0.5 } },
    { name: "NaN probability", value: { state: "live", merged_probability: NaN } },
  ];

  describe.each(["first", "middle", "last"] as const)("poison in the %s cell", (position) => {
    test.each(POISON)("$name poison still renders the whole row", ({ value }) => {
      const idx = position === "first" ? 0 : position === "last" ? cols.length - 1 : 1;
      const cells: Record<string, unknown> = {};
      cols.forEach((c, i) => {
        cells[c] = i === idx ? value : live(0.2 + i / 100);
      });

      const html = render(build("nba", [{ name: "Poisoned", cells }]));
      expect(html).toContain("Poisoned");
      const bodyRow = html.split("<tbody>")[1] ?? "";
      expect((bodyRow.match(/<td/g) || []).length).toBe(cols.length + 2);
      // The healthy siblings survive.
      for (let i = 0; i < cols.length; i++) {
        if (i === idx) continue;
        expect(html).toContain(`${Math.round((0.2 + i / 100) * 100)}%`);
      }
    });
  });

  test("a healthy team still renders when a sibling team's cells are poison", () => {
    const data = build("nba", [
      { name: "Healthy", cells: { championship: live(0.41) } },
      { name: "Broken", cells: "not-an-object" },
      { name: "AlsoHealthy", cells: { championship: live(0.29) } },
    ]);
    const html = render(data);
    expect(html).toContain("Healthy");
    expect(html).toContain("AlsoHealthy");
    expect(html).toContain("41%");
    expect(html).toContain("29%");
    // The broken team still gets a row — empty cells, not a missing row.
    expect(html).toContain("Broken");
  });

  test("a poison participant row is dropped rather than throwing", () => {
    const data = build("nba", [{ name: "Healthy", cells: { championship: live(0.41) } }]);
    // Simulate a payload that survived typing but not reality.
    (data.participants as unknown[]).push(null, "nope", { probabilities: {} });
    expect(() => render(data)).not.toThrow();
    const html = render(data);
    expect(html).toContain("Healthy");
    expect(html).toContain("41%");
  });

  test("poison stages are dropped rather than throwing", () => {
    const data = build("nba", [{ name: "Healthy", cells: { championship: live(0.41) } }]);
    (data.stages as unknown[]).push(null, { label: "no key" });
    expect(() => render(data)).not.toThrow();
    expect(render(data)).toContain("41%");
  });
});

// ---------------------------------------------------------------------------

describe("register version transitions", () => {
  // The payload does not expose a register version (confirmed against the
  // deployed a303db18 on 2026-08-01), so the renderer must be version-blind:
  // the same cell states must render identically whether they came from an old
  // register, a new one, or no register at all.
  test("old register, new register, and no register render the same states", () => {
    const cells = {
      make_playoffs: settled("won"),
      division: live(0.44),
      conference: missing(),
      championship: live(0.12),
    };
    const withOldVersion = { ...cells };
    const withNewVersion = { ...cells };
    const preRegister = {
      make_playoffs: settled("won"),
      division: { merged_probability: 0.44, sources: [], trend_24h: null }, // no state field
      conference: { merged_probability: null, sources: [], trend_24h: null },
      championship: { merged_probability: 0.12, sources: [], trend_24h: null },
    };

    const a = render(build("nba", [{ name: "Alpha", cells: withOldVersion }]));
    const b = render(build("nba", [{ name: "Alpha", cells: withNewVersion }]));
    const c = render(build("nba", [{ name: "Alpha", cells: preRegister }]));

    expect(a).toBe(b);
    // A pre-register payload has no state, so the "conference" cell reads as
    // missing rather than unavailable — both render the same honest empty.
    expect(c).toContain("44%");
    expect(c).toContain("12%");
    expect(c).toContain('data-cell-state="missing"');
  });

  test("terminal season → next season: a fully settled grid carries no live numbers", () => {
    const champion = {
      make_playoffs: settled("won"),
      division: settled("won"),
      conference: settled("won"),
      championship: settled("won"),
    };
    const knockedOut = {
      make_playoffs: settled("won"),
      division: settled("eliminated"),
      conference: settled("eliminated"),
      championship: settled("eliminated"),
    };
    const html = render(
      build("nba", [
        { name: "Champion", cells: champion },
        { name: "Runner", cells: knockedOut },
      ]),
    );
    expect(html).not.toMatch(/\d+(\.\d+)?%/);
    expect(html).toContain("✓");
    expect(html).toContain("✕");
  });

  test("next season opens with all-missing cells, not with last season's numbers", () => {
    const rollover = Object.fromEntries(LEAGUE_COLUMNS.nba.map((c) => [c, missing()]));
    const html = render(build("nba", [{ name: "Alpha", cells: rollover }]));
    expect(html).not.toMatch(/\d+(\.\d+)?%/);
    expect(html).not.toContain("50%");
    expect((html.match(/data-cell-state="missing"/g) || []).length).toBe(
      LEAGUE_COLUMNS.nba.length,
    );
  });
});

// ---------------------------------------------------------------------------

describe("ordering and layout stability", () => {
  test("a clinched champion sorts above the highest live probability", () => {
    const html = render(
      build("nba", [
        { name: "Longshot", cells: { championship: live(0.01) } },
        { name: "Favorite", cells: { championship: live(0.44) } },
        { name: "Champion", cells: { championship: settled("won") } },
      ]),
    );
    const order = ["Champion", "Favorite", "Longshot"].map((n) => html.indexOf(n));
    expect(order[0]).toBeGreaterThan(-1);
    expect(order[0]).toBeLessThan(order[1]);
    expect(order[1]).toBeLessThan(order[2]);
  });

  test("missing and eliminated cells sort below every live cell", () => {
    const html = render(
      build("nba", [
        { name: "Gone", cells: { championship: settled("eliminated") } },
        { name: "NoMarket", cells: { championship: missing() } },
        { name: "Tiny", cells: { championship: live(0.001) } },
      ]),
    );
    expect(html.indexOf("Tiny")).toBeLessThan(html.indexOf("Gone"));
    expect(html.indexOf("Tiny")).toBeLessThan(html.indexOf("NoMarket"));
  });

  test("every non-live cell still renders visible content, so cells cannot collapse", () => {
    for (const cell of [settled("won"), settled("eliminated"), missing(), unavailable()]) {
      const html = render(build("nba", [{ name: "Alpha", cells: { championship: cell } }]));
      const body = html.split("<tbody>")[1] ?? "";
      // Each stage cell carries a glyph — ✓, ✕ or an em-dash — never an empty td.
      expect(body).toMatch(/✓|✕|—/);
      expect(body).not.toContain("<td></td>");
    }
  });

  test("no non-live cell ever emits an inline probability bar", () => {
    for (const cell of [settled("won"), settled("eliminated"), missing(), unavailable()]) {
      const html = render(build("nba", [{ name: "Alpha", cells: { championship: cell } }]));
      expect(html).not.toContain("bg-blue-500/[0.08]");
    }
  });

  test("a live cell still emits its bar — the guard did not disable live rendering", () => {
    const html = render(build("nba", [{ name: "Alpha", cells: { championship: live(0.4) } }]));
    expect(html).toContain("bg-blue-500/[0.08]");
  });
});
