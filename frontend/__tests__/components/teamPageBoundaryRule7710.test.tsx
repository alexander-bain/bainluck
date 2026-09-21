/**
 * #7710 — THE TEAM PAGE STOPS PRINTING AN ABSOLUTE IT DOES NOT HAVE.
 *
 * ═══ WHAT WAS ON PRODUCTION ═══
 *
 * Photographed at 390px on 2026-09-21, after #7687 went live (`4e3e7674e`) and
 * fixed exactly one of the page's five percentage renderers.
 *
 *   Chicago White Sox, four consecutive Season Futures cards:
 *     Munetaka Murakami · AL Rookie of the Year · 0.004   -> "0%"  (#3 of 46)
 *     Munetaka Murakami · 2026 AL MVP           · 0.0035  -> "0%"  (#3 of 18,
 *                                                                  −0.1 pts)
 *     Chicago White Sox · Team to win 100+ games· 0.001   -> "0%"  (#17 of 30)
 *     Sean Burke        · 2026 AL Cy Young      · 0.0005  -> "0%"  (#6 of 65)
 *
 *   Milwaukee Brewers, the third card under two settled ones:
 *     Team to advance to NLDS · 0.9955, is_winner false   -> "100%" (−0.3 pts)
 *
 *   Baltimore Orioles, the page headline, 3xl in team orange:
 *     Championship · 0.004                                -> "0%"  (↓0.1 pts)
 *
 *   Baltimore Orioles, Division Race · East:
 *     Toronto Blue Jays CHAMPION · 0.0035                 -> "0%"
 *     Baltimore Orioles CHAMPION · 0.0005                 -> "0%"
 *
 *   Baltimore Orioles, "Al Rookie Of The Year" prop card:
 *     Dylan Beavers · 0.0005                              -> "0%"
 *
 * A row that says a player is third of forty-six, and that his price moved
 * today, printed `0%` beside both. `0%` reads as *cannot happen*; `100%` on an
 * unplayed series reads as *decided* — in the same column, the same card shape
 * and the same weight as the two rows above it that genuinely settled.
 *
 * ═══ THE RULE, AND THE TWO VOCABULARIES ═══
 *
 * `lib/probabilityDisplay` (UX-P046) states it once: rounding may never move a
 * probability across a boundary it is not on. Two helpers implement it, and
 * which one a surface speaks is not a free choice:
 *
 *   `formatProbabilityPercent`  `<1%` / `>99%`   outcome ROWS and headline
 *                                                numbers — what the rest of
 *                                                this page and every feed and
 *                                                futures row already print.
 *   `probabilityCellText`       `<0.1%` / `0.4%` GRID CELLS — what the playoffs
 *                                                page prints (#7670, #7692).
 *
 * `TeamDivisionRace` takes the `probabilityCellText` route because its cells
 * ARE the playoffs grid's cells: `buildDivisionRace` slices them out of the
 * same `GET /api/playoffs/{league}` payload, so the two surfaces have to agree
 * cell-for-cell or a reader moving between them reads two answers for one
 * number. The last test in this file pins that agreement directly.
 *
 * ═══ BOTH DIRECTIONS (gotcha #43) ═══
 *
 * "Nothing prints 0%" is passed perfectly by a component that prints nothing.
 * So every suppression arm has a control beside it: ordinary values keep their
 * plain integers, a null still prints the dash, and the absolutes the payload
 * is ENTITLED to state — a served 0, a served 1, a settled `✓ Won` row — still
 * print plainly. Those controls are not hypothetical: all 15 settled-won rows
 * and all 156 settled prop rows measured on production carry exactly 1.0 or
 * exactly 0.0.
 *
 * Markers are read from DECODED text, because React escapes `<` and `>` and
 * that one character is the entire difference between "unlikely" and
 * "impossible" (#7320's suite records the same reasoning).
 *
 *   npx jest --testPathPatterns=teamPageBoundaryRule7710
 */

import { readFileSync } from "fs";
import { join } from "path";

import React from "react";
import { renderToStaticMarkup } from "react-dom/server";

import { TeamFutureRow } from "../../components/TeamFutureRow";
import { TeamPropFamilies } from "../../components/TeamPropFamilies";
import { TeamDivisionRace } from "../../components/TeamDivisionRace";
import { buildDivisionRace } from "../../lib/teamDivisionRace";
import { probabilityCellText } from "../../lib/probabilityCellText";
import type { PropFamily, TeamFutureItem } from "../../lib/api";
import type { ChampionshipGridResponse, ChampionshipGridTeam } from "../../lib/types";

jest.mock("next/link", () => ({
  __esModule: true,
  default: ({ href, children }: { href: string; children: React.ReactNode }) => (
    <a href={href}>{children}</a>
  ),
}));

/** Tags out first, then entities in, so the decode cannot manufacture a tag. */
function readable(html: string): string {
  return html
    .replace(/<[^>]*>/g, " ")
    .replace(/&lt;/g, "<")
    .replace(/&gt;/g, ">")
    .replace(/&#x27;/g, "'")
    .replace(/\s+/g, " ");
}

// ---------------------------------------------------------------------------
// 1. The Season Futures row (`TeamFutureRow`, lifted from the page)
// ---------------------------------------------------------------------------

function future(over: Partial<TeamFutureItem>): TeamFutureItem {
  return {
    market_id: 214,
    outcome_id: 1549,
    market_name: "MLB: AL Rookie of the Year",
    outcome_name: "Munetaka Murakami",
    probability: 0.004,
    market_tier: 3,
    rank: 3,
    total_outcomes: 46,
    probability_change_24h: null,
    is_winner: false,
    ...over,
  } as TeamFutureItem;
}

const rowText = (over: Partial<TeamFutureItem>): string =>
  readable(renderToStaticMarkup(<TeamFutureRow item={future(over)} />));

describe("#7710 a season-futures row never rounds a live price into an absolute", () => {
  test("Murakami's 0.004 for Rookie of the Year stops reading as impossible", () => {
    const text = rowText({ probability: 0.004 });
    // Control first: the row has to be on the page for the rest to mean
    // anything, and it has to still carry the rank that contradicted the 0%.
    expect(text).toContain("Munetaka Murakami");
    expect(text).toContain("#3 of 46");
    expect(text).toContain("<1%");
    expect(text).not.toContain(" 0% ");
  });

  test("the whole Chicago cohort — 0.0035, 0.001, 0.0005 — is covered", () => {
    for (const probability of [0.0035, 0.001, 0.0005]) {
      expect(rowText({ probability })).toContain("<1%");
    }
  });

  test("the Brewers' unplayed NLDS series stops reading as decided", () => {
    const text = rowText({
      market_name: "MLB Playoffs: Team to advance to NLDS",
      outcome_name: "Milwaukee Brewers",
      probability: 0.9955,
      market_tier: 5,
      rank: 1,
      total_outcomes: 10,
      probability_change_24h: -0.003,
      is_winner: false,
    });
    expect(text).toContain(">99%");
    expect(text).not.toContain("100%");
    // The row is still the live one it always was: an unsettled row keeps its
    // tier eyebrow and its move, and must NOT have acquired the settled
    // grammar just because its price is high.
    expect(text).toContain("Prop");
    expect(text).not.toContain("What hit");
    expect(text).toContain("-0.3 pts");
  });

  test("CONTROL: a settled winner still prints a plain 100% under ✓ Won", () => {
    // Measured: all 15 settled-won rows on production carry exactly 1.0. If
    // this ever prints `>99%` the boundary rule has eaten a real result.
    const text = rowText({
      probability: 1,
      is_winner: true,
      market_name: "MLB: Team to make postseason",
      outcome_name: "Milwaukee Brewers",
    });
    expect(text).toContain("What hit");
    expect(text).toContain("✓ Won");
    expect(text).toContain("100%");
    expect(text).not.toContain(">99%");
  });

  test("CONTROL: ordinary prices keep their plain integers", () => {
    expect(rowText({ probability: 0.0505 })).toContain("5%");
    expect(rowText({ probability: 0.9948 })).toContain("99%");
    expect(rowText({ probability: 0.5 })).toContain("50%");
  });

  test("CONTROL: a served 0 and a null are two different prints", () => {
    // A payload zero is a boundary the payload states, so it prints as one; a
    // null is "we have no number" and keeps the dash it always had.
    expect(rowText({ probability: 0 })).toContain("0%");
    const nulled = rowText({ probability: null });
    expect(nulled).toContain("—");
    expect(nulled).not.toContain("0%");
  });
});

// ---------------------------------------------------------------------------
// 2. The prop-family cohort card (`TeamPropFamilies`)
// ---------------------------------------------------------------------------

function familyWith(rows: Array<Partial<PropFamily["rows"][number]>>): PropFamily {
  return {
    family_key: "al rookie of the year",
    label: "Al Rookie Of The Year",
    sport: "baseball",
    entity_count: rows.length,
    sources: ["kalshi", "polymarket"],
    rows: rows.map((r, i) => ({
      entity: `Entity ${i}`,
      market_id: 7448386 + i,
      outcome_id: 39431906 + i,
      probability: 0.5,
      source: "polymarket",
      sources: ["polymarket"],
      cross_source: {},
      group_id: null,
      status: "open",
      settled: false,
      result: null,
      top_outcome: null,
      ...r,
    })),
  } as unknown as PropFamily;
}

const familyText = (rows: Array<Partial<PropFamily["rows"][number]>>): string =>
  readable(
    renderToStaticMarkup(
      <TeamPropFamilies families={[familyWith(rows)]} teamColor="#df4601" />,
    ),
  );

describe("#7710 a prop-family row never rounds a live price into an absolute", () => {
  test("Dylan Beavers' served 0.0005 stops reading as impossible", () => {
    const text = familyText([
      { entity: "Samuel Basallo", probability: 0.01 },
      { entity: "Dylan Beavers", probability: 0.0005 },
    ]);
    expect(text).toContain("Dylan Beavers");
    expect(text).toContain("<1%");
    // The leader is the control: the card still prints its ordinary integer,
    // so this is a repaired floor and not a card that stopped printing numbers.
    expect(text).toContain("1%");
  });

  test("the other end is guarded too", () => {
    const text = familyText([
      { entity: "Runaway Favourite", probability: 0.9955 },
      { entity: "Field", probability: 0.004 },
    ]);
    expect(text).toContain(">99%");
    expect(text).not.toContain("100%");
  });

  test("CONTROL: a settled winner at exactly 1.0 still prints 100% beside ✓ Won", () => {
    // Adley Rutschman's real row: settled, result won, probability exactly 1.0.
    const text = familyText([
      { entity: "Adley Rutschman", probability: 1, settled: true, result: "won" },
      { entity: "Ketel Marte", probability: 0.05, settled: true, result: null },
    ]);
    expect(text).toContain("✓ Won");
    expect(text).toContain("100%");
    expect(text).not.toContain(">99%");
  });

  test("CONTROL: a settled loser at exactly 0.0 still prints 0%", () => {
    // 122 of the 156 settled rows measured sit at exactly 0.0. They must keep
    // printing `0%` — the payload is stating the boundary, not rounding to it.
    const text = familyText([
      { entity: "Mike Trout", probability: 0, settled: true, result: "lost" },
      { entity: "Byron Buxton", probability: 0, settled: true, result: "lost" },
    ]);
    expect(text).toContain("0%");
    expect(text).not.toContain("<1%");
  });

  test("CONTROL: a null probability keeps the dash", () => {
    const text = familyText([
      { entity: "No Price", probability: null },
      { entity: "Priced", probability: 0.2 },
    ]);
    expect(text).toContain("—");
    expect(text).toContain("20%");
  });
});

// ---------------------------------------------------------------------------
// 3. The division-race grid (`TeamDivisionRace`) — and its agreement with the
//    playoffs page it is a slice of
// ---------------------------------------------------------------------------

function cell(p: number | null) {
  return { merged_probability: p, sources: [], trend_24h: null, state: "live" };
}

function gridTeam(o: Partial<ChampionshipGridTeam>): ChampionshipGridTeam {
  return {
    name: "Team",
    short_name: "TM",
    team_id: null,
    logo_url: null,
    primary_color: null,
    secondary_color: null,
    record: null,
    conference: "American League",
    division: "East",
    region: null,
    seed: null,
    cells: {},
    ...o,
  } as ChampionshipGridTeam;
}

/** The AL East as production served it on 2026-09-21, championship column. */
const AL_EAST: ChampionshipGridTeam[] = [
  gridTeam({
    name: "Toronto Blue Jays",
    short_name: "TOR",
    team_id: 1,
    cells: { championship: cell(0.0035), make_playoffs: cell(0.045) },
  }),
  gridTeam({
    name: "Baltimore Orioles",
    short_name: "BAL",
    team_id: 2,
    cells: { championship: cell(0.0005), make_playoffs: cell(0.0085) },
  }),
  gridTeam({
    name: "New York Yankees",
    short_name: "NYY",
    team_id: 3,
    cells: { championship: cell(0.1), make_playoffs: cell(0.99) },
  }),
];

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

function raceText(teams: ChampionshipGridTeam[], teamName: string): string {
  const me = teams.find((t) => t.name === teamName);
  if (!me) throw new Error(`fixture has no ${teamName} — the guard would be vacuous`);
  const race = buildDivisionRace(grid(teams), me.team_id as number, teamName);
  if (!race) throw new Error("fixture built no race — the guard would be vacuous");
  return readable(
    renderToStaticMarkup(<TeamDivisionRace race={race} teamColor="#df4601" />),
  );
}

describe("#7710 a division-race cell prints what the playoffs grid prints", () => {
  test("Baltimore's and Toronto's championship cells stop reading as impossible", () => {
    const text = raceText(AL_EAST, "Baltimore Orioles");
    // Controls first: the table is there, with every rival on it.
    expect(text).toContain("Baltimore Orioles");
    expect(text).toContain("Toronto Blue Jays");
    expect(text).toContain("New York Yankees");
    // 0.0005 and 0.0035 in the grid's own vocabulary.
    expect(text).toContain("<0.1%");
    expect(text).toContain("0.4%");
    expect(text).not.toContain(" 0% ");
  });

  test("EVERY cell agrees with the playoffs page, cell for cell", () => {
    // The point of routing this renderer rather than giving it a rule of its
    // own. If a later edit sends one of these two surfaces somewhere else,
    // this fails and names the cell.
    const text = raceText(AL_EAST, "Baltimore Orioles");
    for (const team of AL_EAST) {
      for (const c of Object.values(team.cells ?? {})) {
        const p = (c as { merged_probability: number | null }).merged_probability;
        if (p === null) continue;
        expect(text).toContain(probabilityCellText(p));
      }
    }
  });

  test("the other end is guarded too", () => {
    const text = raceText(
      [
        gridTeam({
          name: "Near Certain",
          short_name: "NC",
          team_id: 9,
          cells: { championship: cell(0.9996) },
        }),
        gridTeam({
          name: "Rival",
          short_name: "RV",
          team_id: 8,
          cells: { championship: cell(0.2) },
        }),
      ],
      "Near Certain",
    );
    expect(text).toContain(">99.9%");
    expect(text).not.toContain("100%");
  });

  test("CONTROL: ordinary cells keep their integers and a null keeps the dash", () => {
    const text = raceText(
      [
        gridTeam({
          name: "Priced",
          short_name: "PR",
          team_id: 7,
          cells: { championship: cell(0.1), make_playoffs: cell(0.65) },
        }),
        gridTeam({
          name: "Unpriced",
          short_name: "UN",
          team_id: 6,
          cells: { championship: cell(null), make_playoffs: cell(0.42) },
        }),
      ],
      "Priced",
    );
    expect(text).toContain("10%");
    expect(text).toContain("65%");
    expect(text).toContain("42%");
    expect(text).toContain("—");
  });
});

// ---------------------------------------------------------------------------
// 4. The two renderers a render test cannot reach — the page headline and the
//    Season Journey's current number
// ---------------------------------------------------------------------------

/**
 * WHY THIS HALF IS A SOURCE SCAN, STATED SO IT IS NOT COPIED CARELESSLY.
 *
 * The headline lives in an `app/**` client page that fills itself from three
 * `useEffect` fetches, and `TeamSeasonJourney` returns `null` until its own
 * fetch resolves (`if (!pick || !loaded || !outcome …)`). This repo renders
 * guards with `renderToStaticMarkup`, which never runs an effect, and has no
 * `@testing-library/react` — so neither number can be rendered here at all.
 * #5669's suite reached the same page the same way and records the same reason.
 *
 * A scan that only proved the bare round was GONE would also pass on a page
 * that stopped printing the number entirely (gotcha #43), so each arm asserts
 * the replacement is PRESENT first and the defect absent second.
 */
describe("#7710 the two renderers an effect-free render cannot reach", () => {
  /**
   * The file's CODE, with comments removed.
   *
   * Not tidying — load-bearing. Each fix below is documented in a docstring
   * that QUOTES the expression it replaced, so a scan over the raw file finds
   * the defect it is checking for, in prose, and fails on a correct tree. (It
   * did: that is how this helper came to exist.)
   */
  const src = (rel: string): string =>
    readFileSync(join(__dirname, "..", "..", rel), "utf8")
      .replace(/\/\*[\s\S]*?\*\//g, " ")
      .replace(/^\s*\/\/.*$/gm, " ");

  const TEAM_PAGE = "app/sport/[sport]/[league]/team/[team]/page.tsx";
  const JOURNEY = "components/TeamSeasonJourney.tsx";

  test("the page headline routes its probability through the boundary rule", () => {
    const text = src(TEAM_PAGE);
    expect(text).toContain("formatProbabilityPercent(headline.probability)");
    expect(text).not.toContain("Math.round(headline.probability * 100)");
  });

  test("the Season Journey's current number does too, and grew no second %", () => {
    const text = src(JOURNEY);
    expect(text).toContain("formatProbabilityPercent(pick.probability)");
    expect(text).not.toContain("Math.round(pick.probability * 100)");
    // `formatProbabilityPercent` returns a `%`-suffixed string, so the JSX that
    // used to read `{currentPct}%` must not still carry the sign.
    expect(text).toContain("{currentPct}\n");
    expect(text).not.toContain("{currentPct}%");
  });

  test("CONTROL: no renderer on this page has kept a bare round of a probability", () => {
    // The sweep that found this ship, frozen. `Math.round(x * 100)` is still
    // legitimate for BAR WIDTHS and for the game cards' complementary pair
    // (`oppPct = 100 - teamPct`, which needs the duel rule and not this one),
    // so the assertion names the printed expressions rather than the idiom.
    for (const [rel, forbidden] of [
      [TEAM_PAGE, "Math.round(headline.probability * 100)"],
      [TEAM_PAGE, "Math.round(item.probability * 100)"],
      [JOURNEY, "Math.round(pick.probability * 100)"],
      ["components/TeamPropFamilies.tsx", "return v === null ? \"—\" : `${Math.round(v * 100)}%`;"],
      ["components/TeamDivisionRace.tsx", "return v === null ? \"—\" : `${Math.round(v * 100)}%`;"],
      ["components/TeamFutureRow.tsx", "Math.round(item.probability * 100)"],
    ] as const) {
      expect(src(rel)).not.toContain(forbidden);
    }
  });
});
