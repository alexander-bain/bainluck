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
//
// #11384 changed the product contract this file first pinned: a cell the
// register still serves LIVE no longer earns a ✓ at >=0.5. A checkmark is a
// confirmed achievement; Tampa Bay's 0.995 pennant cell prints its number and
// says its result is unconfirmed. The register-won fix above is unchanged.
//
// #11385 (Design, 2026-10-21): "unconfirmed" in the title and accessible name
// is invisible on a phone, so every live decided cell also PRINTS
// "Unconfirmed" under its number. `visible` below is the cell's text with every
// tag — and so every title/aria-label attribute — stripped, so it cannot pass
// on the tooltip's wording.

import { renderToStaticMarkup } from "react-dom/server";
import React from "react";

jest.mock("@/hooks/useAnalytics", () => ({
  useAnalytics: () => ({ track: () => {} }),
}));

import TournamentProgressionTable, { decidedCellDisplay } from "../../components/TournamentProgressionTable";
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

function build(teams: { name: string; cells: Record<string, unknown> }[] = TEAMS): ProgressionResponse {
  return {
    sport: "mlb",
    tournament_name: "MLB Playoffs 2026",
    stages: STAGES,
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

interface DecidedCell {
  /** The decided span's own first text: the glyph or the number. */
  text: string;
  /** Everything a sighted reader sees in the cell: tags and attributes stripped. */
  visible: string;
  title: string | undefined;
  spoken: string | undefined;
  state: string | undefined;
}

/** Tags stripped by a character scan, not a regex replace (CodeQL's
 * incomplete-sanitization rule — same helper as futuresVerifiedTitleDetail10224.test). */
function stripTags(html: string): string {
  let out = "";
  let inTag = false;
  for (const ch of html) {
    if (ch === "<") inTag = true;
    else if (ch === ">") inTag = false;
    else if (!inTag) out += ch;
  }
  return out;
}

/** The decided-column cells of one team's row, in column order. */
function decidedCellsFor(html: string, team: string): DecidedCell[] {
  const body = html.split("<tbody>")[1] ?? "";
  const row = body.split("<tr").find((r) => r.includes(team));
  if (!row) throw new Error(`no row for ${team}`);
  const attr = (tag: string, name: string) => tag.match(new RegExp(`${name}="([^"]*)"`))?.[1];
  return Array.from(row.matchAll(/<td([^>]*)>((?:(?!<\/td>)[\s\S])*)<\/td>/g)).flatMap((m) => {
    const span = m[2].match(/<span([^>]*data-decided-cell="[^"]*"[^>]*)>([^<]*)/);
    if (!span) return [];
    return [
      {
        text: span[2],
        visible: stripTags(m[2]),
        title: attr(m[1], "title")?.replace(/&#x27;/g, "'"),
        spoken: attr(span[1], "aria-label"),
        state: attr(span[1], "data-decided-cell"),
      },
    ];
  });
}

const decidedGlyphsFor = (html: string, team: string) => decidedCellsFor(html, team).map((c) => c.text);

describe("#11369 decided columns print the result the register served", () => {
  const html = renderToStaticMarkup(<TournamentProgressionTable data={build()} pageType="playoff_grid" />);

  test("the NL champion reads ✓ in every decided column, titled and spoken as clinched", () => {
    expect(decidedGlyphsFor(html, "Milwaukee Brewers")).toEqual(["✓", "✓", "✓"]);
    for (const cell of decidedCellsFor(html, "Milwaukee Brewers")) {
      expect(cell).toEqual({ text: "✓", visible: "✓", title: "Clinched", spoken: "Clinched", state: "clinched" });
    }
  });

  // #11384: this was "keeps its number-based glyph" and pinned ✓ ✓ ✓. The
  // product contract changed: 0.995 is a strong chance, not a pennant.
  test("a cell still served live is not a ✓ — Tampa Bay 0.995 prints its number, result unconfirmed", () => {
    expect(decidedGlyphsFor(html, "Tampa Bay Rays")).toEqual(["✓", "✓", "99.5%"]);
    const pennant = decidedCellsFor(html, "Tampa Bay Rays")[2];
    expect(pennant).toEqual({
      text: "99.5%",
      visible: "99.5%Unconfirmed",
      title: "Result unconfirmed · Live probability 99.5%",
      spoken: "Result unconfirmed · Live probability 99.5%",
      state: "live",
    });
  });

  test("one ✓ in the pennant column — the club that won it", () => {
    const pennantGlyphs = TEAMS.map((t) => decidedGlyphsFor(html, t.name)[2]);
    expect(pennantGlyphs.filter((g) => g === "✓")).toEqual(["✓"]);
  });

  test("a clinched-then-eliminated club reads in, in, out", () => {
    expect(decidedGlyphsFor(html, "Los Angeles Dodgers")).toEqual(["✓", "✓", "—"]);
    expect(decidedGlyphsFor(html, "New York Yankees")).toEqual(["✓", "—", "—"]);
    expect(decidedCellsFor(html, "New York Yankees")[1]).toEqual({
      text: "—",
      visible: "—",
      title: "Eliminated",
      spoken: "Eliminated",
      state: "eliminated",
    });
  });

  test("an eliminated club reads — everywhere", () => {
    expect(decidedGlyphsFor(html, "Colorado Rockies")).toEqual(["—", "—", "—"]);
  });

  test("the undecided World Series column is untouched — no decided cell, live numbers", () => {
    const body = html.split("<tbody>")[1] ?? "";
    expect((body.match(/data-decided-cell=/g) ?? []).length).toBe(TEAMS.length * 3);
    expect(body).toContain("63%");
  });

  test("the column being decided settles no cell — no cell is titled \"Decided\"", () => {
    const body = html.split("<tbody>")[1] ?? "";
    expect(body).not.toContain('title="Decided"');
  });
});

describe("#11384 a decided column marks only confirmed results", () => {
  const missing = { merged_probability: null, sources: [], trend_24h: null, state: "missing" };
  const unavailable = { merged_probability: null, sources: [], trend_24h: null, state: "unavailable" };
  const SPECIMENS: { name: string; cells: Record<string, unknown> }[] = [
    { name: "Live Low Club", cells: { make_playoffs: live(0.01), division: live(0.5), pennant: live(1), championship: live(0.2) } },
    { name: "Unknown Club", cells: { make_playoffs: missing, division: unavailable, pennant: {}, championship: live(0.2) } },
  ];
  const html = renderToStaticMarkup(<TournamentProgressionTable data={build(SPECIMENS)} pageType="playoff_grid" />);

  test("a live low chance is not an elimination, and a live 1 is not a clinch", () => {
    const cells = decidedCellsFor(html, "Live Low Club");
    expect(cells.map((c) => c.text)).toEqual(["1.0%", "50%", "100%"]);
    for (const cell of cells) {
      expect(cell.state).toBe("live");
      expect(cell.title).toBe(`Result unconfirmed · Live probability ${cell.text}`);
      expect(cell.spoken).toBe(cell.title);
    }
  });

  test("missing, unavailable or absent evidence reads as awaiting, never — (out)", () => {
    const cells = decidedCellsFor(html, "Unknown Club");
    expect(cells).toHaveLength(3);
    for (const cell of cells) {
      expect(cell).toEqual({
        text: "Awaiting",
        visible: "Awaiting",
        title: "Awaiting result",
        spoken: "Awaiting result",
        state: "awaiting",
      });
    }
  });

  // #11385: the deciding check. `visible` has no attributes in it, so a title or
  // aria-label saying "unconfirmed" cannot satisfy this; only printed text can.
  test("every live decided cell PRINTS Unconfirmed under its number — 100% included", () => {
    const cells = decidedCellsFor(html, "Live Low Club");
    expect(cells.map((c) => c.visible)).toEqual(["1.0%Unconfirmed", "50%Unconfirmed", "100%Unconfirmed"]);
    for (const cell of cells) expect(cell.visible).not.toContain("Result unconfirmed");
  });

  test("only live cells carry the qualifier — confirmed, eliminated and awaiting cells print none", () => {
    const all = [build(), build(SPECIMENS)].flatMap((data) => {
      const page = renderToStaticMarkup(<TournamentProgressionTable data={data} pageType="playoff_grid" />);
      return data.participants.flatMap((p) => decidedCellsFor(page, p.name));
    });
    const live = all.filter((c) => c.state === "live");
    expect(live).toHaveLength(4);
    for (const cell of live) expect(cell.visible).toBe(`${cell.text}Unconfirmed`);
    for (const cell of all.filter((c) => c.state !== "live")) {
      expect(cell.visible).toBe(cell.text);
      expect(cell.visible.toLowerCase()).not.toContain("unconfirmed");
    }
  });

  test("neither specimen prints a ✓ or a — in a decided column", () => {
    const glyphs = SPECIMENS.flatMap((t) => decidedGlyphsFor(html, t.name));
    expect(glyphs).not.toContain("✓");
    expect(glyphs).not.toContain("—");
  });
});

describe("decidedCellDisplay", () => {
  test("status is the result; the number never settles a cell", () => {
    expect(decidedCellDisplay(null, "clinched")).toEqual({ text: "✓", label: "Clinched", state: "clinched" });
    expect(decidedCellDisplay(0.1, "clinched").text).toBe("✓");
    expect(decidedCellDisplay(0.9, "eliminated")).toEqual({ text: "—", label: "Eliminated", state: "eliminated" });
    expect(decidedCellDisplay(null, "eliminated").text).toBe("—");
    expect(decidedCellDisplay(0.9, "missing")).toEqual({ text: "Awaiting", label: "Awaiting result", state: "awaiting" });
    expect(decidedCellDisplay(0.9, "unavailable").state).toBe("awaiting");
    expect(decidedCellDisplay(null, null).state).toBe("awaiting");
    expect(decidedCellDisplay(Number.NaN, null).state).toBe("awaiting");
    for (const s of ["clinched", "eliminated", "missing"] as const) {
      expect(decidedCellDisplay(0.9, s).qualifier).toBeUndefined();
    }
  });

  // #11384: the old contract pinned decidedGlyph(0.5, null) = ✓ and
  // decidedGlyph(0.49, null) = —. Neither number is a result.
  test("a live number at any level stays a live number with an unconfirmed result", () => {
    for (const [p, text] of [
      [0.5, "50%"],
      [0.49, "49%"],
      [0.995, "99.5%"],
      [0.9995, ">99.9%"],
      [1, "100%"],
      [0.01, "1.0%"],
      [0, "0%"],
    ] as const) {
      expect(decidedCellDisplay(p, null)).toEqual({
        text,
        label: `Result unconfirmed · Live probability ${text}`,
        state: "live",
        qualifier: "Unconfirmed",
      });
    }
  });
});

// Design (2026-10-21, confirmed-grid-reader-disposition): the qualifier was
// 9px uppercase muted grey (~2.5:1 on white). A live decided cell's number and
// its "Unconfirmed" now read in the secondary grey (~4.8:1) at 12px/16px
// medium, title case, normal tracking, no opacity; every other decided cell
// keeps the muted grey.
describe("Design 2026-10-21: an unconfirmed decided cell is readable", () => {
  /** Class lists of each decided cell's span and its qualifier, in column order. */
  function decidedClassesFor(html: string, team: string) {
    const body = html.split("<tbody>")[1] ?? "";
    const row = body.split("<tr").find((r) => r.includes(team));
    if (!row) throw new Error(`no row for ${team}`);
    const cls = (tag: string) => (tag.match(/class="([^"]*)"/)?.[1] ?? "").split(/\s+/).filter(Boolean);
    return Array.from(row.matchAll(/<span([^>]*data-decided-cell="([^"]*)"[^>]*)>([^<]*)(<span([^>]*data-decided-qualifier[^>]*)>([^<]*))?/g)).map(
      (m) => ({ state: m[2], cell: cls(m[1]), qualifier: m[5] === undefined ? undefined : cls(m[5]), qualifierText: m[6] }),
    );
  }

  const html = renderToStaticMarkup(<TournamentProgressionTable data={build()} pageType="playoff_grid" />);
  const all = TEAMS.flatMap((t) => decidedClassesFor(html, t.name));

  test("Tampa Bay's unconfirmed pennant: number and qualifier in the secondary grey, qualifier 12px medium title case", () => {
    const [tampa] = decidedClassesFor(html, "Tampa Bay Rays").filter((c) => c.state === "live");
    expect(tampa.cell).toContain("text-text-secondary");
    expect(tampa.cell).not.toContain("text-text-muted");
    expect(tampa.qualifierText).toBe("Unconfirmed");
    expect(tampa.qualifier).toEqual(expect.arrayContaining(["text-xs", "font-medium"]));
    // The qualifier inherits the number's colour: no colour, size, leading,
    // case, tracking, opacity or clamp of its own to drift from it.
    for (const c of tampa.qualifier ?? []) {
      expect(c).not.toMatch(/^(text-text-|text-\[|leading-|uppercase$|tracking-|opacity-|truncate$|line-clamp-)/);
    }
  });

  test("confirmed, eliminated and awaiting cells keep the muted grey and carry no qualifier", () => {
    const unknown = renderToStaticMarkup(
      <TournamentProgressionTable
        data={build([{ name: "Unknown Club", cells: { make_playoffs: {}, division: {}, pennant: {}, championship: {} } }])}
        pageType="playoff_grid"
      />,
    );
    const others = [...all, ...decidedClassesFor(unknown, "Unknown Club")].filter((c) => c.state !== "live");
    expect(new Set(others.map((c) => c.state))).toEqual(new Set(["clinched", "eliminated", "awaiting"]));
    for (const c of others) {
      expect(c.cell).toContain("text-text-muted");
      expect(c.cell).not.toContain("text-text-secondary");
      expect(c.qualifier).toBeUndefined();
    }
  });
});
