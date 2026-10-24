/**
 * #2311 — the team page's Prop Races say when they did not search the whole roster.
 *
 * Served 2026-10-24, `/api/teams/seattle-seahawks/prop-families` (build 12:08:56Z,
 * quality full, availability live): 4 races, and
 * `roster_search: {searched: 40, total: 82, truncated: true}`. The page dropped
 * that field, so a race whose only members sit among the 42 unsearched names
 * was simply absent and the section read as complete. The fixture is that
 * payload, verbatim (shopper's 12:22Z re-look, artifacts/shopper/2311-relook-1222Z).
 *
 * A capped team with NO races is declared too (Root, 12:47Z, on #2311's Outcome:
 * "derived from the team's WHOLE roster, or must declare that they were not"):
 * zero races is the case whose missing races could ALL sit among the unsearched
 * names. a70bd36aa2 hid it; its "stays hidden" test pinned that incomplete rule
 * and is replaced below by the positive and negative controls.
 *
 * Mutation map:
 *   - drop the caption from TeamPropFamilies          → part 2 "counted" fails
 *   - quote counts without the `quality: "full"` gate → part 1 partial/absent-cache fail
 *   - accept `searched >= total` / non-integers       → part 1 malformed rows fail
 *   - treat a missing `truncated` as capped           → part 1 legacy rows fail
 *   - hide a capped EMPTY result (a70bd36aa2's rule)   → part 2 capped-empty tests fail
 *   - show an uncapped or legacy empty result          → part 2 uncapped-empty test fails
 *   - draw the empty card grid under a capped-empty caption → part 2 capped-empty tests fail
 *   - drop the slug tag from useTeamPropRaces         → part 3 switch test fails
 *   - drop the `cancelled` guard                      → part 3 "resolving AFTER" test fails
 *   - gate counts on `!== "partial"` instead of `=== "full"` → part 1 degraded/no-quality rows fail
 *   - drop `rosterCoverage=` from the team page        → part 4 fails
 *   - feed the hook `teamSlug` instead of `resolvedSlug` → part 4 fails
 */

import "./helpers/minimalDom";
import React, { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { renderToStaticMarkup } from "react-dom/server";

import seahawks from "./fixtures/2311SeahawksPropFamilies.20261024.json";
import type { TeamPropFamiliesResponse } from "@/lib/api";
import { propRosterCoverage, propRosterCoverageNote } from "@/lib/propRosterCoverage";
import { TeamPropFamilies } from "@/components/TeamPropFamilies";

const mockFetch = jest.fn();
jest.mock("@/lib/api", () => ({
  ...jest.requireActual("@/lib/api"),
  fetchTeamPropFamilies: (slug: string) => mockFetch(slug),
}));

import { useTeamPropRaces, type TeamPropRaces } from "@/hooks/useTeamPropRaces";

import fs from "node:fs";
import path from "node:path";

const SEAHAWKS = seahawks as unknown as TeamPropFamiliesResponse;
const COUNTED_NOTE = "We checked 40 of the 82 players on this roster, so some races may be missing.";
const UNCOUNTED_NOTE = "We did not check every player on this roster, so some races may be missing.";

function withSearch(search: unknown, cache: unknown = SEAHAWKS.cache) {
  return { ...SEAHAWKS, roster_search: search, cache } as unknown as TeamPropFamiliesResponse;
}

// ---------------------------------------------------------------------------
// Part 1 — the one reading of `roster_search`
// ---------------------------------------------------------------------------

describe("#2311 part 1 — propRosterCoverage", () => {
  test("the fixture is the served capped build", () => {
    expect(SEAHAWKS.roster_search).toEqual({ searched: 40, total: 82, truncated: true });
    expect(SEAHAWKS.cache?.quality).toBe("full");
    expect(SEAHAWKS.families.map((f) => f.label)).toEqual([
      "Next Team",
      "Defensive Player Of The Year",
      "MVP",
      "Season Receiving Yards",
    ]);
  });

  test("a full capped build quotes its own counts", () => {
    expect(propRosterCoverage(SEAHAWKS)).toEqual({ kind: "counted", searched: 40, total: 82 });
    expect(propRosterCoverageNote(propRosterCoverage(SEAHAWKS))).toBe(COUNTED_NOTE);
  });

  test("the counts are PLAYERS checked, never rows: 40 names is not 40 players with markets", () => {
    const rows = SEAHAWKS.families.reduce((n, f) => n + f.rows.length, 0);
    expect(rows).not.toBe(40);
    expect(COUNTED_NOTE).not.toMatch(/have (props|markets|races)/i);
  });

  test("a whole-roster search says nothing", () => {
    expect(propRosterCoverage(withSearch({ searched: 31, total: 31, truncated: false }))).toBeNull();
  });

  test.each([
    ["absent (rosterless team / legacy payload)", undefined],
    ["null", null],
    ["truncated missing", { searched: 40, total: 82 }],
    ["truncated as a string", { searched: 40, total: 82, truncated: "true" }],
    ["an array", [40, 82, true]],
  ])("no claim either way when roster_search is %s", (_label, search) => {
    expect(propRosterCoverage(withSearch(search))).toBeNull();
    expect(propRosterCoverageNote(propRosterCoverage(withSearch(search)))).toBeNull();
  });

  test.each([
    ["searched >= total", { searched: 82, total: 82, truncated: true }],
    ["searched > total", { searched: 90, total: 82, truncated: true }],
    ["zero searched", { searched: 0, total: 82, truncated: true }],
    ["fractional", { searched: 40.5, total: 82, truncated: true }],
    ["string counts", { searched: "40", total: "82", truncated: true }],
    ["counts missing", { truncated: true }],
    ["negative", { searched: -1, total: 82, truncated: true }],
  ])("a capped search with %s keeps the warning but invents no counts", (_label, search) => {
    expect(propRosterCoverage(withSearch(search))).toEqual({ kind: "uncounted" });
    const note = propRosterCoverageNote(propRosterCoverage(withSearch(search)));
    expect(note).toBe(UNCOUNTED_NOTE);
    expect(note).not.toMatch(/\d/);
  });

  test("a partial build does not quote counts: the roster branch may not have finished", () => {
    const partial = {
      ...SEAHAWKS.cache,
      quality: "partial",
      quality_reasons: ["branch_timeout:outcome_roster", "branch_timeout:market_roster"],
    };
    expect(propRosterCoverage(withSearch(SEAHAWKS.roster_search, partial))).toEqual({
      kind: "uncounted",
    });
  });

  test.each([
    ["degraded", { ...SEAHAWKS.cache, quality: "degraded" }],
    ["missing its quality", (({ quality: _q, ...rest }) => rest)(SEAHAWKS.cache ?? {})],
  ])("a %s build does not quote counts: only `full` is trusted", (_label, cache) => {
    expect(propRosterCoverage(withSearch(SEAHAWKS.roster_search, cache))).toEqual({
      kind: "uncounted",
    });
  });

  test("absent cache (the build that lost every branch) does not quote counts", () => {
    const { cache: _drop, ...noCache } = SEAHAWKS;
    expect(propRosterCoverage(noCache)).toEqual({ kind: "uncounted" });
  });

  test("neither sentence speaks build or timeout jargon", () => {
    for (const note of [COUNTED_NOTE, UNCOUNTED_NOTE]) {
      expect(note).not.toMatch(/timeout|timed out|partial|cache|build|branch|cap\b|truncat|quality/i);
    }
  });
});

// ---------------------------------------------------------------------------
// Part 2 — the caption on the Prop Races section
// ---------------------------------------------------------------------------

describe("#2311 part 2 — TeamPropFamilies renders the caption", () => {
  const render = (coverage: ReturnType<typeof propRosterCoverage>, families = SEAHAWKS.families) =>
    renderToStaticMarkup(
      <TeamPropFamilies
        families={families}
        teamColor="#002244"
        teamName="Seattle Seahawks"
        rosterCoverage={coverage}
      />,
    );

  test("counted: the sentence, the counts as data attributes, and every race still shown", () => {
    const html = render(propRosterCoverage(SEAHAWKS));
    expect(html).toContain(COUNTED_NOTE);
    expect(html).toContain('data-roster-searched="40"');
    expect(html).toContain('data-roster-total="82"');
    for (const f of SEAHAWKS.families) expect(html).toContain(f.label);
    // Real row navigation is untouched.
    expect(html).toContain('href="/futures/3452980"');
    // The caption sits under the heading, before the first card.
    expect(html.indexOf("Prop Races")).toBeLessThan(html.indexOf(COUNTED_NOTE));
    expect(html.indexOf(COUNTED_NOTE)).toBeLessThan(html.indexOf("Next Team"));
  });

  test("uncounted: the sentence without numbers or count attributes", () => {
    const html = render({ kind: "uncounted" });
    expect(html).toContain(UNCOUNTED_NOTE);
    expect(html).not.toContain("data-roster-searched");
    expect(html).not.toContain("data-roster-total");
  });

  test("no coverage: no caption, and the same bytes as the old call site that passed no coverage", () => {
    const withNull = render(null);
    expect(withNull).not.toContain("prop-roster-coverage");
    expect(withNull).toContain("mb-4");
    // Omitting the prop entirely (the old call site) renders the same bytes.
    const omitted = renderToStaticMarkup(
      <TeamPropFamilies families={SEAHAWKS.families} teamColor="#002244" teamName="Seattle Seahawks" />,
    );
    expect(omitted).toBe(withNull);
  });

  // A one-entity family is filtered out before render, so a payload holding only
  // those is an empty result too.
  const ONE_ENTITY_ONLY = [{ ...SEAHAWKS.families[0], rows: SEAHAWKS.families[0].rows.slice(0, 1) }];

  test.each([
    ["no families", []],
    ["only one-entity families", ONE_ENTITY_ONLY],
  ])("a capped EMPTY result (%s) is declared: heading and counted sentence, nothing else", (_l, families) => {
    const html = render(propRosterCoverage(SEAHAWKS), families);
    expect(html).toContain("Prop Races");
    expect(html).toContain(COUNTED_NOTE);
    expect(html).toContain('data-roster-searched="40"');
    expect(html).toContain('data-roster-total="82"');
    // No card scaffold, no race, no row, no market count.
    expect(html).not.toContain("grid-cols-1");
    expect(html).not.toContain("rounded-card");
    expect(html).not.toContain("in the mix");
    expect(html).not.toContain("/futures/");
    for (const f of SEAHAWKS.families) expect(html).not.toContain(f.label);
    // Heading and the one sentence are the whole section.
    expect(html.replace(/<[^>]+>/g, "")).toBe(`Prop Races${COUNTED_NOTE}`);
  });

  test("a capped EMPTY result with untrusted counts is declared without numbers", () => {
    const html = render({ kind: "uncounted" }, []);
    expect(html.replace(/<[^>]+>/g, "")).toBe(`Prop Races${UNCOUNTED_NOTE}`);
    expect(html).not.toContain("data-roster-searched");
    expect(html).not.toContain("data-roster-total");
  });

  test("the empty declaration claims neither absence nor completeness", () => {
    const html = render(propRosterCoverage(SEAHAWKS), []);
    expect(html).not.toMatch(/\b(no|none|zero)\b[^.]*\b(races|props|markets)\b/i);
    expect(html).not.toMatch(/\b(all|every|complete)\b/i);
  });

  test.each([
    ["coverage null (whole-roster search)", null],
    ["coverage omitted (legacy call site / payload)", undefined],
  ])("an UNcapped or legacy EMPTY result stays hidden: %s", (_l, coverage) => {
    for (const families of [[], ONE_ENTITY_ONLY]) {
      const html =
        coverage === undefined
          ? renderToStaticMarkup(
              <TeamPropFamilies families={families} teamColor="#002244" teamName="Seattle Seahawks" />,
            )
          : render(coverage, families);
      expect(html).toBe("");
    }
  });
});

// ---------------------------------------------------------------------------
// Part 3 — team switch: races and caption travel together, keyed by slug
// ---------------------------------------------------------------------------

type Deferred = { resolve: (v: unknown) => void; reject: (e: unknown) => void };

describe("#2311 part 3 — useTeamPropRaces", () => {
  let root: Root;
  let latest: TeamPropRaces | null;
  let pending: Record<string, Deferred>;

  function Probe({ slug }: { slug: string }) {
    latest = useTeamPropRaces(slug);
    return null;
  }

  const flush = () => act(async () => { for (let i = 0; i < 10; i++) await Promise.resolve(); });

  beforeEach(() => {
    latest = null;
    pending = {};
    mockFetch.mockReset();
    mockFetch.mockImplementation(
      (slug: string) =>
        new Promise((resolve, reject) => {
          pending[slug] = { resolve, reject };
        }),
    );
    const doc = document as unknown as {
      createElement: (t: string) => unknown;
      body: { appendChild: (n: unknown) => void };
    };
    const host = doc.createElement("div");
    doc.body.appendChild(host);
    root = createRoot(host as unknown as Element);
  });

  afterEach(() => {
    act(() => root.unmount());
  });

  test("the served payload arrives with its coverage", async () => {
    act(() => root.render(<Probe slug="seattle-seahawks" />));
    expect(latest).toEqual({ families: [], coverage: null });
    pending["seattle-seahawks"].resolve(SEAHAWKS);
    await flush();
    expect(latest?.families).toHaveLength(4);
    expect(latest?.coverage).toEqual({ kind: "counted", searched: 40, total: 82 });
  });

  test("switching teams drops the old races AND caption on the same render", async () => {
    act(() => root.render(<Probe slug="seattle-seahawks" />));
    pending["seattle-seahawks"].resolve(SEAHAWKS);
    await flush();
    expect(latest?.coverage).not.toBeNull();

    act(() => root.render(<Probe slug="kansas-city-chiefs" />));
    expect(latest).toEqual({ families: [], coverage: null });

    // The next team's whole-roster answer carries no caption.
    pending["kansas-city-chiefs"].resolve({
      ...SEAHAWKS,
      roster_search: { searched: 31, total: 31, truncated: false },
    });
    await flush();
    expect(latest?.families).toHaveLength(4);
    expect(latest?.coverage).toBeNull();
  });

  test("a late answer for the previous team never shows, nor wipes the current team's", async () => {
    act(() => root.render(<Probe slug="seattle-seahawks" />));
    act(() => root.render(<Probe slug="kansas-city-chiefs" />));
    pending["seattle-seahawks"].resolve(SEAHAWKS);
    await flush();
    expect(latest).toEqual({ families: [], coverage: null });

    const chiefs = { ...SEAHAWKS, roster_search: { searched: 40, total: 65, truncated: true } };
    pending["kansas-city-chiefs"].resolve(chiefs);
    await flush();
    expect(latest?.coverage).toEqual({ kind: "counted", searched: 40, total: 65 });
  });

  test("Seahawks resolving AFTER Chiefs leaves the Chiefs' races up", async () => {
    act(() => root.render(<Probe slug="seattle-seahawks" />));
    act(() => root.render(<Probe slug="kansas-city-chiefs" />));
    const chiefs = { ...SEAHAWKS, roster_search: { searched: 40, total: 65, truncated: true } };
    pending["kansas-city-chiefs"].resolve(chiefs);
    await flush();
    pending["seattle-seahawks"].resolve(SEAHAWKS);
    await flush();
    expect(latest?.families).toHaveLength(4);
    expect(latest?.coverage).toEqual({ kind: "counted", searched: 40, total: 65 });
  });

  test("a capped payload with no races still hands back its coverage", async () => {
    act(() => root.render(<Probe slug="seattle-seahawks" />));
    pending["seattle-seahawks"].resolve({ ...SEAHAWKS, families: [], total_families: 0 });
    await flush();
    expect(latest).toEqual({
      families: [],
      coverage: { kind: "counted", searched: 40, total: 82 },
    });
  });

  test("a failed fetch hides the section and claims nothing", async () => {
    act(() => root.render(<Probe slug="seattle-seahawks" />));
    pending["seattle-seahawks"].reject(new Error("503"));
    await flush();
    expect(latest).toEqual({ families: [], coverage: null });
  });

  test("a legacy payload without roster_search shows its races with no caption", async () => {
    const { roster_search: _drop, ...legacy } = SEAHAWKS;
    act(() => root.render(<Probe slug="seattle-seahawks" />));
    pending["seattle-seahawks"].resolve(legacy);
    await flush();
    expect(latest?.families).toHaveLength(4);
    expect(latest?.coverage).toBeNull();
  });
});

// ---------------------------------------------------------------------------
// Part 4 — the team page delivers the coverage to the section
// ---------------------------------------------------------------------------
//
// Parts 2 and 3 render the component and the hook directly, so neither sees the
// page. The prop is optional, so typecheck does not either: deleting
// `rosterCoverage={propRaces.coverage}` from the page left every suite green
// (lane1's M1 on a70bd36aa2) — and "the web page dropped the field" was #2311's
// defect in the first place. The page fills itself from effects, which
// `renderToStaticMarkup` never runs, so this reads the source, as
// `teamPageMovementPoints5669` / `teamPageLeagueLabel5847` do.

describe("#2311 part 4 — the team page passes the hook's coverage to Prop Races", () => {
  const TEAM_PAGE = "app/sport/[sport]/[league]/team/[team]/page.tsx";
  const src = fs.readFileSync(path.join(__dirname, "..", TEAM_PAGE), "utf8");
  const hookCalls = [...src.matchAll(/const\s+(\w+)\s*=\s*useTeamPropRaces\(([^)]*)\)/g)];
  const elements = src.match(/<TeamPropFamilies\b[^>]*\/>/g) ?? [];

  test("the scan read the real page, so every assertion below is about something", () => {
    expect(src.length).toBeGreaterThan(5000);
    expect(hookCalls).toHaveLength(1);
    expect(elements).toHaveLength(1);
  });

  test("the hook is asked for the RESOLVED slug, not the URL's", () => {
    // A redirected or aliased URL slug fetches the wrong team's races.
    expect(hookCalls[0]?.[2].trim()).toBe("resolvedSlug");
  });

  test("the one <TeamPropFamilies> gets that hook's families AND its coverage", () => {
    const binding = hookCalls[0]?.[1];
    const element = elements[0] ?? "";
    expect(element).toMatch(new RegExp(`\\bfamilies=\\{${binding}\\.families\\}`));
    expect(element).toMatch(new RegExp(`\\brosterCoverage=\\{${binding}\\.coverage\\}`));
  });
});
