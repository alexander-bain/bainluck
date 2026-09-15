/**
 * #6253 — AN O/U PAIR NEVER PRINTS ONE WORD TWICE.
 *
 * ═══ WHAT ALEX SAW ═══
 *
 * `/events/15312629` (Club Necaxa v CF América, Liga MX), Bigger Picture, at
 * 390px. The group headed `O/U 8.5 TOTAL CORNERS (2)` drew two tiles:
 *
 *     Team   51%
 *     Team   50%
 *
 * Two tiles, the same word, one percentage point apart. A reader cannot tell
 * which one is Over. The label was not clipped — it was a CONSTANT, so the pair
 * carried zero information, and "Team" is not even the right KIND of subject:
 * a total-corners line has no team.
 *
 * ═══ THE MECHANISM — THE ANSWER WAS DELETED AT PARSE ═══
 *
 * The payload knew: `outcome_name` was `Over` and `Under`. `parseStatOutcome`
 * matched `/^(over|under)/`, used the match only as a boolean (`isTeamTotal`),
 * and threw the matched WORD away. The two rows left the parser byte-identical,
 * so nothing downstream could recover the distinction — `disambiguateLabels`
 * (#2788) was handed two identical strings and correctly changed nothing, and
 * the render site then supplied the invented constant `"Team"`.
 *
 * The repair is to carry the word: `parseStatOutcome` returns `direction`, and
 * the tile's subject is READ from the outcome rather than invented — the same
 * principle #6210 applied to THE SCRIPT (`lib/playerPropsGrouping.ts`) and the
 * divergence rows (`lib/propDivergence.ts`). This is the third component on the
 * same page carrying that constant, not a regression of that fix.
 *
 * ═══ WHY THE ASSERTIONS ARE ON MARKUP ═══
 *
 * `parseStatOutcome` is not exported, and the defect is a property of the
 * rendered GROUP — "these two tiles print the same string" — not of any one
 * call. So this file renders the real component and reads the tile labels out
 * of its HTML, which is the only artifact that can tell a fixed label from a
 * fixed parser feeding a broken render site.
 *
 * ═══ BOTH DIRECTIONS (gotcha #43) ═══
 *
 * A test that only asserted "the word Team is gone" would be passed perfectly
 * by rendering no label at all, or by labelling every tile "—". Every case
 * below therefore asserts what the tile DOES say, and the player-prop control
 * asserts the far commoner path — a named player — is untouched.
 */

import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import RelatedFutures from "@/components/RelatedFutures";
import type { RelatedFuture, RelatedFuturesResponse } from "@/lib/types";

const EVENT_ID = 15312629;
const HOME = "Club Necaxa";
const AWAY = "CF América";
const CORNERS = "Club Necaxa vs. CF América: O/U 8.5 Total Corners";

/** A stat-prop row, defaulted to the reported page's shape. */
function row(over: Partial<RelatedFuture> = {}): RelatedFuture {
  return {
    market_id: 8801,
    market_name: CORNERS,
    display_category: "game_prop",
    market_tier: 5,
    category: "game",
    source: "kalshi",
    outcome_id: 9001,
    outcome_name: "Over",
    probability: 0.505,
    american_odds: null,
    probability_change_24h: null,
    opening_probability: null,
    rank: null,
    relevance_score: 1,
    relevance_reason: "same match",
    last_updated: null,
    next_update_expected: "",
    resolution_date: null,
    ...over,
  };
}

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

function render(home: RelatedFuture[]): string {
  swrPayload = {
    event_id: EVENT_ID,
    home_team: HOME,
    away_team: AWAY,
    home_team_futures: home,
    away_team_futures: [],
    series_markets: [],
    total_count: home.length,
    summary: null,
    event_status: "scheduled",
    box_score: null,
    league_context: null,
  } as RelatedFuturesResponse;

  return renderToStaticMarkup(
    React.createElement(RelatedFutures, {
      eventId: EVENT_ID,
      homeTeam: HOME,
      awayTeam: AWAY,
    }),
  );
}

/**
 * The tile labels, in draw order.
 *
 * Anchored on the label element's own class list rather than on any text, so
 * the extraction cannot be satisfied by a label that says the right thing
 * somewhere else on the page (the `title` attribute, the group header, a
 * tooltip). It reads exactly the string the reader sees inside the tile.
 */
function tileLabels(html: string): string[] {
  const re =
    /<div class="text-\[11px\] font-semibold text-text-primary truncate leading-tight"[^>]*>(.*?)<\/div>/g;
  const out: string[] = [];
  let m: RegExpExecArray | null;
  while ((m = re.exec(html)) !== null) out.push(m[1]);
  return out;
}

describe("#6253 — a team total's tile is labelled by its own outcome", () => {
  it("THE REPORTED PAIR: bare Over/Under draw two DIFFERENT labels, and neither is 'Team'", () => {
    // The exact rows the API served: one market, two outcomes, the direction
    // word the only thing telling them apart — and no number anywhere in the
    // outcome, which is what made the old fallback produce an empty line too.
    const html = render([
      row({ outcome_id: 9001, outcome_name: "Over", probability: 0.505 }),
      row({ outcome_id: 9002, outcome_name: "Under", probability: 0.495 }),
    ]);

    const labels = tileLabels(html);
    expect(labels).toEqual(["Over", "Under"]);

    // The defect stated as the reader met it: two tiles, one string.
    expect(new Set(labels).size).toBe(labels.length);
    expect(labels).not.toContain("Team");

    // Both numbers are still on the page, so the pair is readable, not merely
    // distinct — 51% / 50%, as Alex saw them.
    expect(html).toContain("51%");
    expect(html).toContain("50%");
  });

  it("A LINE IN THE OUTCOME survives: 'Over 2.5' still shows its number, labelled Over", () => {
    // The commoner team-total shape. The direction becomes the label and the
    // line keeps its own row — the fix must not swallow the number into the
    // label or drop it.
    //
    // Every market name here names THIS event: `isRelevantGameProp` drops a
    // `game_prop` whose "A vs B" prefix matches neither side, so a borrowed
    // name from another fixture renders nothing and the case proves nothing.
    const html = render([
      row({
        market_name: "Club Necaxa vs. CF América: O/U 2.5 Total Goals",
        market_id: 8802,
        outcome_id: 9101,
        outcome_name: "Over 2.5",
        probability: 0.52,
      }),
      row({
        market_name: "Club Necaxa vs. CF América: O/U 2.5 Total Goals",
        market_id: 8802,
        outcome_id: 9102,
        outcome_name: "Under 2.5",
        probability: 0.48,
      }),
    ]);

    expect(tileLabels(html)).toEqual(["Over", "Under"]);
    expect(html).toContain("2.5");
  });

  it("A LADDER of Overs keeps its LINES: same direction, different questions, distinguishable tiles", () => {
    // The commonest live shape for this branch — measured 2026-09-15 across 96
    // upcoming events: `Alaves vs Valencia: Total Goals` serves SIX rows, all
    // "Over N.5 goals scored". Their labels are all "Over" and that is correct:
    // the direction is the subject, exactly as a player's name is, and the line
    // is what differs — so the line is what the tile must keep showing.
    //
    // This is the case that stops a future "no two labels may repeat" rule from
    // being enforced by deleting the line number and inventing a subject again.
    const lines = ["0.5", "1.5", "2.5", "3.5"];
    const html = render(
      lines.map((l, i) =>
        row({
          market_name: "Club Necaxa vs. CF América: Total Goals",
          market_id: 8804,
          outcome_id: 9500 + i,
          outcome_name: `Over ${l} goals scored`,
          probability: 0.9 - i * 0.2,
        }),
      ),
    );

    expect(tileLabels(html)).toEqual(["Over", "Over", "Over", "Over"]);
    // …and each tile still carries the line that tells it from its neighbours.
    for (const l of lines) expect(html).toContain(l);
  });

  it("CONTROL — PLAYER PROPS ARE UNTOUCHED: a named player still labels its own tile", () => {
    // The path that was never broken, and by far the commoner one. If this
    // fails, the repair has relabelled every prop tile in the app.
    const html = render([
      row({
        market_name: "Club Necaxa vs. CF América: Shots on Target",
        market_id: 8803,
        outcome_id: 9201,
        outcome_name: "Alejandro Zendejas: 2+",
        probability: 0.61,
      }),
      row({
        market_name: "Club Necaxa vs. CF América: Shots on Target",
        market_id: 8803,
        outcome_id: 9202,
        outcome_name: "Diber Cambindo: 1+",
        probability: 0.55,
      }),
    ]);

    expect(tileLabels(html)).toEqual(["Alejandro Zendejas", "Diber Cambindo"]);
  });

  it("CONTROL — THE LABEL IS STILL DRAWN: the fix removes a wrong word, not the element", () => {
    // A test asserting only the absence of "Team" would be passed by deleting
    // the label element. Assert a tile exists and its label is non-empty.
    const html = render([
      row({ outcome_id: 9301, outcome_name: "Over", probability: 0.505 }),
    ]);

    const labels = tileLabels(html);
    expect(labels).toHaveLength(1);
    expect(labels[0].trim().length).toBeGreaterThan(0);
    expect(labels[0]).toBe("Over");
  });

  it("the tooltip carries the outcome the payload served, never an invented subject", () => {
    // `title` was the second site holding the constant. It is what a reader
    // gets on hover when the tile truncates, so it must name the real row.
    const html = render([
      row({ outcome_id: 9401, outcome_name: "Over 8.5", probability: 0.52 }),
    ]);

    expect(html).toContain('title="Over 8.5"');
    expect(html).not.toContain('title="Team"');
  });
});
