/**
 * #3729 — A QUARTERFINAL FILLED FROM ITS OWN EVENT SAYS SO, IN THE PAGE'S WORD.
 *
 * Found by LOOK, on production, on the middle Sunday of the US Open: the only
 * two blank rows on `/tournaments/us-open` were the two quarterfinals, while
 * each one's own match page printed a number from seven sportsbooks. The
 * backend now fills those rows from the event's own blend
 * (`apply_event_blend_slate`), and where the sportsbook consensus fed it alone
 * the row carries `price_source: "books"`.
 *
 * This is the render half, and it pins the two halves of one rule:
 *
 *   1. A books-filled row prints the marker — the SAME word the finished list
 *      one section down already prints beside its sportsbook priors. One page
 *      may not caveat the same claim in two vocabularies.
 *   2. An ordinary row prints nothing. `price_source` is absent on every row
 *      served before this shipped and on every row a prediction market
 *      priced, and absence has always meant "the product's own reading, which
 *      reads as itself". A cached payload must pick up no caveat it did not
 *      earn — which is also why this asserts against a fixture with the field
 *      MISSING rather than set to null.
 */

import React from "react";
import { renderToStaticMarkup } from "react-dom/server";

import TournamentMatches from "@/components/tournament/TournamentMatches";
import { matchListFromSlate, priceMarkerFor } from "@/lib/matchList";
import { BOOKS_MARKER } from "@/lib/tournamentResults";
import type { SlateMatch, SlateSide } from "@/lib/slate";

function side(overrides: Partial<SlateSide> = {}): SlateSide {
  return {
    entity_key: "espn:athlete:1000001",
    display_name: "Aryna Sabalenka",
    seed: null,
    country: "BLR",
    role: "contender",
    probability: 0.6992,
    opening_probability: 0.6992,
    move: 0,
    raw_probability: 0.6992,
    raw_opening_probability: 0.6992,
    age_hours: 0.04,
    price_state: "live",
    ...overrides,
  };
}

/** The women's quarterfinal, as the backend now serves it. */
function quarterfinal(overrides: Partial<SlateMatch> = {}): SlateMatch {
  return {
    matchup_key: "espn:182533",
    priced: true,
    event_id: 15306160,
    draw: "womens-singles",
    draw_label: "Women's Singles",
    round: "QF",
    scheduled_date: "2026-09-08T15:30:00+00:00",
    sides: [
      side(),
      side({
        entity_key: "espn:athlete:1000002",
        display_name: "Linda Noskova",
        country: "CZ",
        probability: 0.3008,
        opening_probability: 0.3008,
        raw_probability: 0.3008,
        raw_opening_probability: 0.3008,
      }),
    ],
    coherent: true,
    raw_sum: 1,
    opening_raw_sum: 1,
    probability_is_live: true,
    price_state: "live",
    observed_at: "2026-09-07T00:33:38+00:00",
    age_hours: 0.04,
    freshest_observed_at: "2026-09-07T00:33:38+00:00",
    freshest_age_hours: 0.04,
    stale_sides: [],
    mixed_freshness: false,
    favourite: "espn:athlete:1000001",
    has_moved: false,
    source_count: 1,
    ...overrides,
  };
}

describe("#3729 — the filled quarterfinal names its own source", () => {
  it("prints the number AND the page's own books marker", () => {
    const html = renderToStaticMarkup(
      <TournamentMatches
        entries={matchListFromSlate([quarterfinal({ price_source: "books" })])}
      />
    );

    expect(html).toContain("70%");
    expect(html).toContain('data-testid="match-price-marker"');
    expect(html).toContain(BOOKS_MARKER);
    // And the row is a real row, not the collapsed no-number treatment.
    expect(html).toContain("Aryna Sabalenka");
    expect(html).not.toContain("no probability against it");
  });

  it("says nothing at all on a row the field never reached", () => {
    const html = renderToStaticMarkup(
      <TournamentMatches entries={matchListFromSlate([quarterfinal()])} />
    );

    expect(html).toContain("70%");
    expect(html).not.toContain('data-testid="match-price-marker"');
  });

  it("a prediction market's number wears no caveat", () => {
    expect(priceMarkerFor("kalshi")).toBeNull();
    expect(priceMarkerFor("polymarket")).toBeNull();
    expect(priceMarkerFor(undefined)).toBeNull();
    expect(priceMarkerFor(null)).toBeNull();
    expect(priceMarkerFor("books")).toBe(BOOKS_MARKER);
  });
});
