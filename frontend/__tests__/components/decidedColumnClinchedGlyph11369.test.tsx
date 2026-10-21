// #11369: a DECIDED playoff-grid column must say who actually got in.
//
// Since Q295 a register-won cell carries `state: "won"` and NO number, but the
// decided-column glyph read the number alone (`prob >= 0.5 ? "✓" : "—"`). On
// production /playoffs/mlb (2026-10-21 08:09Z) that printed "—" for the NL
// champion Brewers in "AL / NL Champ" and for all twelve playoff teams in
// "Make Playoffs" — identical to the eliminated clubs — while Tampa Bay, still
// served live at 0.995, kept its ✓.
//
// The cells below are copied verbatim from that served payload
// (artifacts/shopper/pass-0541/journey/api.json, sha256 e5fa1574…a7d4), and are
// pushed through the same adapter the page uses.

import { renderToStaticMarkup } from "react-dom/server";
import React from "react";

jest.mock("@/hooks/useAnalytics", () => ({
  useAnalytics: () => ({ track: () => {} }),
}));

import TournamentProgressionTable, { decidedGlyph } from "../../components/TournamentProgressionTable";
import { gridCellsToProgression } from "../../lib/gridCellState";
import type { ProgressionResponse, ProgressionStage } from "../../lib/types";

const won = { merged_probability: null, sources: [], trend_24h: null, state: "won" };
const out = { merged_probability: null, sources: [], trend_24h: null, state: "eliminated" };
const live = (p: number) => ({ merged_probability: p, sources: [], trend_24h: null, state: "live" });

// Served column flags: the first three are decided, the World Series is not.
const STAGES: ProgressionStage[] = [
  ["make_playoffs", "Make Playoffs", true],
  ["division", "Division", true],
  ["pennant", "AL / NL Champ", true],
  ["championship", "World Series", false],
].map(([key, label, resolved], i) => ({
  key: key as string,
  label: label as string,
  order: i + 1,
  market_id: null,
  market_name: null,
  resolved: resolved as boolean,
}));

const TEAMS: { name: string; cells: Record<string, unknown> }[] = [
  { name: "Milwaukee Brewers", cells: { make_playoffs: won, division: won, pennant: won, championship: live(0.627) } },
  { name: "Tampa Bay Rays", cells: { make_playoffs: won, division: won, pennant: live(0.995), championship: live(0.373) } },
  { name: "Los Angeles Dodgers", cells: { make_playoffs: won, division: won, pennant: out, championship: out } },
  { name: "New York Yankees", cells: { make_playoffs: won, division: out, pennant: out, championship: out } },
  { name: "Colorado Rockies", cells: { make_playoffs: out, division: out, pennant: out, championship: out } },
];

function build(): ProgressionResponse {
  return {
    sport: "mlb",
    tournament_name: "MLB Playoffs 2026",
    stages: STAGES,
    participants: TEAMS.map((t) => {
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

/** The decided-column glyphs of one team's row, in column order. */
function decidedGlyphsFor(html: string, team: string): string[] {
  const body = html.split("<tbody>")[1] ?? "";
  const row = body.split("<tr").find((r) => r.includes(team));
  if (!row) throw new Error(`no row for ${team}`);
  return Array.from(row.matchAll(/<td[^>]*title="Decided"[^>]*>[\s\S]*?<span[^>]*>([^<]*)<\/span>/g)).map(
    (m) => m[1],
  );
}

describe("#11369 decided columns print the result the register served", () => {
  const html = renderToStaticMarkup(<TournamentProgressionTable data={build()} pageType="playoff_grid" />);

  test("the NL champion reads ✓ in every decided column", () => {
    expect(decidedGlyphsFor(html, "Milwaukee Brewers")).toEqual(["✓", "✓", "✓"]);
  });

  test("a cell still served live keeps its number-based glyph (Tampa Bay 0.995)", () => {
    expect(decidedGlyphsFor(html, "Tampa Bay Rays")).toEqual(["✓", "✓", "✓"]);
  });

  test("a clinched-then-eliminated club reads in, in, out", () => {
    expect(decidedGlyphsFor(html, "Los Angeles Dodgers")).toEqual(["✓", "✓", "—"]);
    expect(decidedGlyphsFor(html, "New York Yankees")).toEqual(["✓", "—", "—"]);
  });

  test("an eliminated club reads — everywhere", () => {
    expect(decidedGlyphsFor(html, "Colorado Rockies")).toEqual(["—", "—", "—"]);
  });

  test("the undecided World Series column is untouched — no decided glyph, live numbers", () => {
    const body = html.split("<tbody>")[1] ?? "";
    expect((body.match(/title="Decided"/g) ?? []).length).toBe(TEAMS.length * 3);
    expect(body).toContain("63%");
  });
});

describe("decidedGlyph", () => {
  test("status is the result; the number is consulted only for a live cell", () => {
    expect(decidedGlyph(null, "clinched")).toBe("✓");
    expect(decidedGlyph(0.1, "clinched")).toBe("✓");
    expect(decidedGlyph(0.9, "eliminated")).toBe("—");
    expect(decidedGlyph(null, "eliminated")).toBe("—");
    expect(decidedGlyph(0.9, "missing")).toBe("—");
    expect(decidedGlyph(0.9, "unavailable")).toBe("—");
    expect(decidedGlyph(0.5, null)).toBe("✓");
    expect(decidedGlyph(0.49, null)).toBe("—");
    expect(decidedGlyph(null, null)).toBe("—");
  });
});
