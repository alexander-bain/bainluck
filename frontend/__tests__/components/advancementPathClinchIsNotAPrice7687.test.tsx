/**
 * #7687 — A PLAYOFF RUNG STOPS SAYING A CLUB HAS CLINCHED BECAUSE THE PRICE IS HIGH.
 *
 * ═══ WHAT WAS ON PRODUCTION ═══
 *
 * `/events/15314300` (Red Sox vs Guardians), the CHAMPIONSHIP PATH block in
 * Boston's card, measured 2026-09-21 against `/api/events/{id}/related-futures`
 * and `/api/playoffs/mlb` read in the same minutes:
 *
 *     Make Playoffs     ✓ clinched      <- served 0.9972. NOT clinched.
 *     AL / NL Champ     12%
 *     World Series      5%
 *
 * Boston had not clinched anything. The site's OWN playoffs grid served that
 * exact cell as `state: "live"` in the same minute, so two Bain Luck surfaces
 * one click apart disagreed about whether a club was in, and the one that was
 * wrong was the one making the stronger claim.
 *
 * ═══ THE THRESHOLD COULD ONLY EVER FIRE WHERE IT MUST NOT ═══
 *
 * `RelatedFutures.buildPathEntries` set `resolved = probability >= 0.995`, and
 * `AdvancementPath` prints that flag as `✓ clinched`. The assumption was
 * written down — in `TournamentExtensions`, the sibling caller that refused to
 * copy it: *"the league path calls a stage clinched at >= 0.995 because a
 * season's playoff market really does settle to 1.0 once the maths is done."*
 *
 * Production falsifies that sentence. A settled rung does not settle to 1.0,
 * it is DROPPED:
 *
 *   The Dodgers HAVE clinched — the grid serves make_playoffs AND division as
 *   `state: "won"` — and their `league_context.cells` omits both keys
 *   entirely (`{pennant, championship}` is the whole object). Their page
 *   printed no ✓ clinched at all.
 *
 *   Boston have NOT clinched, so their cell was present, at 0.9972, and the
 *   threshold fired.
 *
 * The flag was therefore inverted by construction, not merely mistuned: the
 * payload's convention makes a PRESENT rung an UNRESOLVED one, so the only
 * rows `>= 0.995` can reach are the rows it must never fire on. Raising the
 * cutoff would only have made the false claim rarer.
 *
 * ═══ AND THE NUMBER BESIDE IT ═══
 *
 * The rung's percentage went through a bare `renderedPercent`, so UX-P046's
 * boundary rule — rounding may never move a probability across a boundary it
 * is not on — had never been applied on this block. Both ends are live on it:
 * the same Red Sox page served 0.9972 in a list with rungs at 0.001, which
 * printed `0%` over markets actively pricing them.
 *
 * ═══ WHY THESE ASSERTIONS ARE ON RENDERED MARKUP ═══
 *
 * The defect spans a join: one file decides `resolved`, a different file
 * decides what `resolved` draws. A unit test of either alone passes while the
 * page lies — which is how this survived, given the component's own prop
 * documented a clinch it had no way to verify. So the payload-shaped arm below
 * drives the real `AdvancementPath` with the real production numbers.
 *
 * ═══ BOTH DIRECTIONS (gotcha #43) ═══
 *
 * "Never prints ✓ clinched" is passed perfectly by a component that draws
 * nothing, and "prints >99%" by one that has stopped drawing clinches it
 * SHOULD draw. So the suppression arms are paired with controls: the rungs
 * must still be present with their labels and numbers, a genuinely `resolved`
 * stage must still render the tick, and an ordinary mid-range rung must still
 * print its plain integer rather than a marker.
 *
 * The marker assertions read the RAW MARKUP. React escapes `>` to `&gt;`, and
 * a text-stripping helper that rewrites entities cannot tell `>99%` from
 * `99%` — the single character carrying the meaning is the one such helpers
 * delete (this bit the sibling suite; see its note).
 *
 *   npx jest --testPathPatterns=advancementPathClinchIsNotAPrice7687
 */

import React from "react";
import { renderToStaticMarkup } from "react-dom/server";

import AdvancementPath, {
  type AdvancementStage,
} from "../../components/event/AdvancementPath";
import RelatedFutures from "../../components/RelatedFutures";
import type { RelatedFuturesResponse } from "../../lib/types";

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

/** Boston's served rungs, verbatim from `league_context.cells` on 2026-09-21. */
const BOSTON_MAKE_PLAYOFFS = 0.9972;
const BOSTON_PENNANT = 0.1207;
const BOSTON_WORLD_SERIES = 0.0545;
/** The low end, from the same page's related-futures rows. */
const BARELY_POSSIBLE = 0.001;

function stage(over: Partial<AdvancementStage>): AdvancementStage {
  return {
    label: "Make Playoffs",
    prob: BOSTON_MAKE_PLAYOFFS,
    change: null,
    resolved: false,
    ...over,
  };
}

function draw(stages: AdvancementStage[]): string {
  return renderToStaticMarkup(React.createElement(AdvancementPath, { stages }));
}

describe("#7687 a rung's certainty comes from the payload, never from its price", () => {
  test("the census is not vacuous: this component really does draw a clinch", () => {
    // If `✓ clinched` had been deleted outright, every suppression assertion
    // below would pass against a component incapable of the claim, and the
    // guard would be describing nothing. The tick must remain REACHABLE — what
    // changed is who is allowed to ask for it.
    expect(draw([stage({ resolved: true })])).toContain("clinched");
  });

  test("Boston's 0.9972 does not print ✓ clinched", () => {
    const html = draw([stage({ prob: BOSTON_MAKE_PLAYOFFS })]);
    expect(html).not.toContain("clinched");
  });

  test("Boston's 0.9972 does not print 100% either", () => {
    // The second spelling of the same false claim. A fix that only deleted the
    // word would leave the page asserting the berth in digits.
    const html = draw([stage({ prob: BOSTON_MAKE_PLAYOFFS })]);
    expect(html).not.toContain("100%");
    expect(html).toContain("&gt;99%");
  });

  test("a rung a market still prices does not print 0%", () => {
    const html = draw([stage({ label: "World Series", prob: BARELY_POSSIBLE })]);
    expect(html).not.toContain(">0%<");
    expect(html).toContain("&lt;1%");
  });

  test("the absolutes still print plainly when the payload states them", () => {
    // The boundary rule guards ROUNDING, it does not forbid a real 0 or 1.
    expect(draw([stage({ prob: 1 })])).toContain("100%");
    expect(draw([stage({ label: "World Series", prob: 0 })])).toContain("0%");
  });

  test("CONTROL: an ordinary rung is untouched — plain integer, no marker", () => {
    const html = draw([
      stage({ label: "AL / NL Champ", prob: BOSTON_PENNANT }),
      stage({ label: "World Series", prob: BOSTON_WORLD_SERIES }),
    ]);
    expect(html).toContain("12%");
    expect(html).toContain("5%");
    expect(html).not.toContain("&gt;");
    expect(html).not.toContain("&lt;");
  });

  test("CONTROL: Boston's whole block still renders every rung it was given", () => {
    // The suppression must cost the reader nothing. Three rungs in, three
    // labels and three numbers out.
    const html = draw([
      stage({ label: "Make Playoffs", prob: BOSTON_MAKE_PLAYOFFS }),
      stage({ label: "AL / NL Champ", prob: BOSTON_PENNANT }),
      stage({ label: "World Series", prob: BOSTON_WORLD_SERIES }),
    ]);
    expect(html).toContain("Make Playoffs");
    expect(html).toContain("AL / NL Champ");
    expect(html).toContain("World Series");
    expect((html.match(/data-testid="advancement-stage"/g) ?? []).length).toBe(3);
    expect(html).toContain("&gt;99%");
    expect(html).toContain("12%");
    expect(html).toContain("5%");
  });
});

/**
 * THE OTHER HALF OF THE JOIN.
 *
 * Everything above proves what `AdvancementPath` draws when it is HANDED a
 * flag. It says nothing about who sets it, and the defect was in the setting:
 * a component that draws `resolved` faithfully is exactly what made a
 * price-derived flag reach a reader. So this arm drives the real
 * `RelatedFutures` with Boston's verbatim `league_context` and reads the page.
 *
 * `cells` being `Record<string, number>` is itself the finding — the type has
 * nowhere to put a settlement, which is why the old code had to invent one.
 */
const BOSTON_CELLS = {
  make_playoffs: BOSTON_MAKE_PLAYOFFS,
  pennant: BOSTON_PENNANT,
  championship: BOSTON_WORLD_SERIES,
};
const COLUMNS = [
  { key: "make_playoffs", label: "Make Playoffs" },
  { key: "division", label: "Division" },
  { key: "pennant", label: "AL / NL Champ" },
  { key: "championship", label: "World Series" },
];

function renderEventPage(homeCells: Record<string, number>): string {
  swrPayload = {
    event_id: 15314300,
    home_team: "Boston Red Sox",
    away_team: "Cleveland Guardians",
    home_team_futures: [],
    away_team_futures: [],
    series_markets: [],
    total_count: 0,
    summary: null,
    event_status: "scheduled",
    box_score: null,
    league_context: {
      league_slug: "mlb",
      league_name: "MLB",
      columns: COLUMNS,
      league_page_url: "/leagues/mlb",
      home_team: {
        cells: homeCells,
        changes_24h: {},
        record: "88-68",
        conference: "American League",
        sources_available: ["kalshi", "polymarket"],
      },
    },
  } as unknown as RelatedFuturesResponse;

  return renderToStaticMarkup(
    React.createElement(RelatedFutures, {
      eventId: 15314300,
      homeTeam: "Boston Red Sox",
      awayTeam: "Cleveland Guardians",
      homeTeamColor: "#bd3039",
      awayTeamColor: "#00385d",
    }),
  );
}

describe("#7687 the event page stops minting a clinch out of league_context", () => {
  test("Boston's served 0.9972 reaches the page as a number, not a verdict", () => {
    const html = renderEventPage(BOSTON_CELLS);
    // The control first: the block must actually be on the page, or the
    // assertion under it is about an empty string.
    expect(html).toContain("Make Playoffs");
    expect(html).not.toContain("clinched");
    expect(html).not.toContain("100%");
    expect(html).toContain("&gt;99%");
  });

  test("CONTROL: the rest of Boston's path is unchanged", () => {
    const html = renderEventPage(BOSTON_CELLS);
    expect(html).toContain("AL / NL Champ");
    expect(html).toContain("12%");
    expect(html).toContain("World Series");
    expect(html).toContain("5%");
  });

  test("no rung at all can mint one — 0.995 exactly, the old cutoff", () => {
    // The threshold was `>= 0.995`, so its own boundary value is the sharpest
    // probe: a re-tuned cutoff would still fire here, a removed claim cannot.
    const html = renderEventPage({ ...BOSTON_CELLS, make_playoffs: 0.995 });
    expect(html).toContain("Make Playoffs");
    expect(html).not.toContain("clinched");
  });
});
