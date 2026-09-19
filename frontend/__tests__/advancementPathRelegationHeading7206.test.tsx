/**
 * A BLOCK HEADED "CHAMPIONSHIP PATH" NEVER LEADS WITH RELEGATION (#7206).
 *
 * ═══ WHAT WAS ON PRODUCTION ═══
 *
 * `/events/15305209` (Nottingham Forest v Coventry City), 390px, 2026-09-19
 * 16:5xZ. Both team cards in "Bigger Picture → Season context":
 *
 *     CHAMPIONSHIP PATH                 CHAMPIONSHIP PATH
 *     Relegated   ↑1.3%   11%           Relegated          78%
 *     Top 4       ↓1.3%    4%           Top 4               4%
 *     Champion             1%           Champion            1%
 *
 * Coventry's block is headed *championship path* over a **78.5% chance of
 * going down**. The first and largest rung of a path to a title is relegation.
 * Every figure is true; the heading is what is wrong. (#7206 was filed off the
 * Tottenham–Aston Villa page at 12%; the live one was five times worse.)
 *
 * ═══ THE MECHANISM ═══
 *
 * `RelatedFutures` builds these rows from `league_context`, whose columns
 * arrive from `league_configs.py` as `{key, label}` pairs. The builder kept
 * `col.label` and threw `col.key` away, so `Relegated` reached
 * `AdvancementPath` in exactly the shape of `Top 4` — a rung down the table
 * indistinguishable from a rung up it. With nothing to contradict it, the
 * component printed its default heading.
 *
 * ═══ WHY THE ASSERTIONS ARE WHERE THEY ARE ═══
 *
 * The repair is a rule about what a heading may claim given its rungs, and it
 * lives inside `AdvancementPath` so that no caller can reintroduce the defect.
 * So it is pinned twice and deliberately:
 *
 *   - through `RelatedFutures` with the production payload, because that is
 *     the surface that broke and a unit test of the helper would not notice
 *     the builder dropping the key again on the way in; and
 *   - on `AdvancementPath` directly, because the invariant is the component's
 *     and the second caller (tennis) must be shown to be untouched.
 *
 * ═══ BOTH DIRECTIONS (gotcha #43) ═══
 *
 * A test that only proves "the heading is not CHAMPIONSHIP PATH" is passed
 * perfectly by deleting that heading from the app. Every case below is paired
 * with a control that changes ONE thing — the column key — and asserts the
 * championship heading comes back. And because the issue explicitly forbids
 * the lazy repair ("it should not simply be reordered to hide the biggest
 * number"), the rung itself is asserted present, first, and at its full value
 * in the very case where the heading changes.
 */

import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import RelatedFutures from "@/components/RelatedFutures";
import AdvancementPath, {
  advancementHeading,
  CHAMPIONSHIP_PATH_HEADING,
  NON_ADVANCEMENT_STAGE_KEYS,
  SEASON_OUTCOMES_HEADING,
  type AdvancementStage,
} from "@/components/event/AdvancementPath";
import type { RelatedFuturesResponse, LeagueContextData } from "@/lib/types";

const EVENT_ID = 15305209;
const HOME = "Nottingham Forest";
const AWAY = "Coventry City";

/** The EPL config's columns, verbatim from `league_configs.py`. */
const EPL_COLUMNS: LeagueContextData["columns"] = [
  { key: "relegation", label: "Relegated" },
  { key: "top_4", label: "Top 4" },
  { key: "championship", label: "Champion" },
];

/**
 * The NFL config's columns — a league with no downward rung — as the control
 * shape. Its labels differ from EPL's too, which is the point: the rule must
 * key on `relegation`, not on any property of the words.
 */
const NFL_COLUMNS: LeagueContextData["columns"] = [
  { key: "make_playoffs", label: "Make Playoffs" },
  { key: "division", label: "Division" },
  { key: "conference", label: "Conference" },
  { key: "championship", label: "Super Bowl" },
];

let swrPayload: RelatedFuturesResponse;

jest.mock("swr", () => ({
  __esModule: true,
  default: () => ({
    data: swrPayload,
    error: undefined,
    isLoading: false,
    mutate: () => undefined,
  }),
}));

/** The served payload, as production returned it for this event. */
function render(opts: {
  columns: LeagueContextData["columns"];
  homeCells: Record<string, number>;
  awayCells?: Record<string, number>;
}): string {
  swrPayload = {
    event_id: EVENT_ID,
    home_team: HOME,
    away_team: AWAY,
    home_team_futures: [],
    away_team_futures: [],
    series_markets: [],
    total_count: 0,
    summary: null,
    event_status: "live",
    box_score: null,
    league_context: {
      league_slug: "epl",
      league_name: "Premier League 2026-27",
      league_page_url: "/playoffs/epl",
      columns: opts.columns,
      home_team: {
        cells: opts.homeCells,
        changes_24h: {},
        sources_available: ["kalshi", "polymarket"],
      },
      ...(opts.awayCells
        ? {
            away_team: {
              cells: opts.awayCells,
              changes_24h: {},
              sources_available: ["kalshi", "polymarket"],
            },
          }
        : {}),
    },
  } as RelatedFuturesResponse;

  return renderToStaticMarkup(
    React.createElement(RelatedFutures, {
      eventId: EVENT_ID,
      homeTeam: HOME,
      awayTeam: AWAY,
      homeTeamColor: "#DD0000",
      awayTeamColor: "#6CADDF",
    }),
  );
}

/** The heading `AdvancementPath` renders for one card, read off the markup. */
function headingOf(html: string, side: "home" | "away"): string | null {
  const m = new RegExp(
    `data-testid="${side}-championship-path-heading"[^>]*>([^<]*)<`,
  ).exec(html);
  return m ? m[1].trim() : null;
}

/** The production cells, to four places, for the two cards above. */
const FOREST = { relegation: 0.113, top_4: 0.038, championship: 0.009 };
const COVENTRY = { relegation: 0.785, top_4: 0.04, championship: 0.009 };

describe("#7206 — the rungs get the last word on what the block calls itself", () => {
  it("THE REPORTED PAGE: neither card claims a championship path over a relegation rung", () => {
    const html = render({
      columns: EPL_COLUMNS,
      homeCells: FOREST,
      awayCells: COVENTRY,
    });

    expect(headingOf(html, "home")).toBe(SEASON_OUTCOMES_HEADING);
    expect(headingOf(html, "away")).toBe(SEASON_OUTCOMES_HEADING);
    expect(html).not.toContain(CHAMPIONSHIP_PATH_HEADING);
  });

  it("THE NUMBER IS TRUE AND IT STAYS: Coventry's 78.5% is still first, still whole", () => {
    // The issue's own words: "It should not simply be reordered to hide the
    // biggest number — the number is true; the heading is what is wrong." So a
    // repair that suppressed, demoted or rounded the rung away would pass the
    // case above and fail this one.
    const html = render({ columns: EPL_COLUMNS, homeCells: COVENTRY });

    const stages = [
      ...html.matchAll(/data-stage="([^"]*)" data-probability="([^"]*)"/g),
    ].map((m) => [m[1], Number(m[2])] as const);

    expect(stages).toEqual([
      ["Relegated", 0.785],
      ["Top 4", 0.04],
      ["Champion", 0.009],
    ]);
    expect(html).toContain("79%");
  });

  it("CONTROL: the same three cells under a league with no downward rung keep CHAMPIONSHIP PATH", () => {
    // One thing differs from the first case — the column KEYS. Same component,
    // same builder, same number of rungs. Without this the suite would pass on
    // an app that had simply deleted the championship heading.
    const html = render({
      columns: NFL_COLUMNS,
      homeCells: { make_playoffs: 0.62, division: 0.31, championship: 0.05 },
    });

    expect(headingOf(html, "home")).toBe(CHAMPIONSHIP_PATH_HEADING);
    expect(html).not.toContain(SEASON_OUTCOMES_HEADING);
  });

  it("PER CARD, NOT PER PAGE: a side with no relegation cell keeps its own heading", () => {
    // `ctxToFutures` filters on `cells[key] != null`, so one team can have a
    // relegation price and the other not. The heading is derived from the rungs
    // that side actually draws, so the two cards are allowed to differ.
    const html = render({
      columns: EPL_COLUMNS,
      homeCells: FOREST,
      awayCells: { top_4: 0.62, championship: 0.28 },
    });

    expect(headingOf(html, "home")).toBe(SEASON_OUTCOMES_HEADING);
    expect(headingOf(html, "away")).toBe(CHAMPIONSHIP_PATH_HEADING);
  });
});

describe("#7206 — the invariant belongs to the component", () => {
  const stage = (over: Partial<AdvancementStage>): AdvancementStage => ({
    label: "Champion",
    prob: 0.1,
    change: null,
    resolved: false,
    ...over,
  });

  it("an explicit caller heading is overridden too — the rule is not 'fix the default'", () => {
    // A block holding a season outcome IS a season-outcomes block whatever its
    // caller wanted to call it. If this only guarded the default, the next
    // caller to pass its own championship wording would print the defect again.
    const html = renderToStaticMarkup(
      React.createElement(AdvancementPath, {
        heading: "ROAD TO THE TITLE",
        stages: [
          stage({ label: "Relegated", prob: 0.785, columnKey: "relegation" }),
          stage({ columnKey: "championship" }),
        ],
      }),
    );
    expect(html).toContain(SEASON_OUTCOMES_HEADING);
    expect(html).not.toContain("ROAD TO THE TITLE");
  });

  it("THE SECOND CALLER IS UNTOUCHED: keyless stages keep the heading they were given", () => {
    // `TournamentExtensions` passes tennis reach cells, which have no grid
    // column at all. A rule that fired on absence would rename every tennis
    // draw on the site.
    const html = renderToStaticMarkup(
      React.createElement(AdvancementPath, {
        heading: "CHANCE OF REACHING",
        stages: [
          stage({ label: "Quarter-finals", prob: 0.48 }),
          stage({ label: "Final", prob: 0.12 }),
        ],
      }),
    );
    expect(html).toContain("CHANCE OF REACHING");
    expect(html).not.toContain(SEASON_OUTCOMES_HEADING);
  });

  it("the label is not the predicate: a rung CALLED Relegated with no key does not trip it", () => {
    // This is the classifier this fix exists to avoid. It also pins the
    // fallback branch's documented behaviour: raw ILIKE rows carry no key and
    // are deliberately left alone rather than pattern-matched.
    expect(
      advancementHeading(
        [stage({ label: "Relegated", prob: 0.785 })],
        CHAMPIONSHIP_PATH_HEADING,
      ),
    ).toBe(CHAMPIONSHIP_PATH_HEADING);
  });

  it("NON-VACUITY: every key in the set downgrades, and a key outside it does not", () => {
    // If `NON_ADVANCEMENT_STAGE_KEYS` were ever emptied, every case above that
    // asserts a downgrade would go green by never downgrading anything — the
    // controls would still pass. This is the test that reds instead.
    expect(NON_ADVANCEMENT_STAGE_KEYS.size).toBeGreaterThan(0);
    for (const key of NON_ADVANCEMENT_STAGE_KEYS) {
      expect(
        advancementHeading([stage({ columnKey: key })], CHAMPIONSHIP_PATH_HEADING),
      ).toBe(SEASON_OUTCOMES_HEADING);
    }
    // Every other column key in `league_configs.py` is a rung toward something
    // good, so none of them may downgrade.
    for (const key of [
      "championship",
      "conference",
      "division",
      "make_playoffs",
      "top_4",
      "top_5",
      "top_10",
      "top_20",
      "final",
      "final_four",
      "elite_eight",
      "sweet_16",
      "round_of_32",
      "quarterfinal",
      "semifinal",
      "title_game",
      "pennant",
      "make_cut",
      "win",
    ]) {
      expect(
        advancementHeading([stage({ columnKey: key })], CHAMPIONSHIP_PATH_HEADING),
      ).toBe(CHAMPIONSHIP_PATH_HEADING);
    }
  });
});
