/**
 * SHIP 6 (#4460) — THE MAP COLUMN STOPS PRINTING ITS ONE CARD'S TITLE TWICE.
 *
 * Read on production, 2026-09-10 ~02:30 PT, `/events/15308439` at 390px — the
 * US Open men's semi-final. Two labels, stacked, twenty pixels apart:
 *
 *   > GAME MARGIN MAP                     <- the column eyebrow, small grey caps
 *   > ┌───────────────────────────────┐
 *   > │ Game margin map      SHE 73%  │   <- the card's own title
 *   > │ Expected margin distribution  │
 *
 *   > GAMES MAP
 *   > ┌───────────────────────────────┐
 *   > │ Games map        Projected 41 │
 *
 * The eyebrow exists to name a column that GROUPS several cards — a full-game
 * margin map plus a first-half one, where "Point margin maps" is genuinely
 * telling you what the stack below is. `mapColumnHeading(title, 1)` returns the
 * title unchanged, so with a single card it printed that card's own heading
 * verbatim, immediately above it.
 *
 * Tennis is the guaranteed case: a match has no halves, so `halfMarginMaps` and
 * `halfTotalMaps` are always empty and the count is always exactly 1. Every
 * tennis match page carried both duplicates, on both columns.
 *
 * D102 allows small grey type "where it makes sense and offers the reader
 * value". A label that repeats the heading below it offers none.
 *
 * ── WHY THE RENDER SITE AND NOT THE HELPER ───────────────────────────────────
 *
 * `mapColumnHeading` is doing its job: it pluralises from the declared title
 * and `settledMapTense.test.tsx` pins that over every declared vocabulary
 * (#2442, #2441, #3136). The redundancy is not in what the string says, it is
 * in showing a one-card column a heading at all. So the count decides whether
 * the eyebrow renders, and the helper is untouched.
 *
 * The positive control at the foot of this file is the half that makes the fix
 * a fix rather than a deletion: give the column a second card and the eyebrow
 * must come back, pluralised.
 */
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";

import MarketMapSection from "@/components/MarketMapSection";
import { sportVocab } from "@/lib/marketMapUtils";

function visibleText(html: string): string {
  return html
    .replace(/<[^>]+>/g, " ")
    .replace(/&#x27;/g, "'")
    .replace(/&amp;/g, "&")
    .replace(/&[a-z]+;/g, " ")
    .replace(/\s+/g, " ")
    .trim();
}

function occurrences(haystack: string, needle: string): number {
  return haystack.split(needle).length - 1;
}

/**
 * Event 15308439 as production served it, trimmed to the fields these maps
 * read. One full-game margin ladder and one full-game totals ladder, which is
 * every tennis match: one card per column.
 */
function tiafoeShelton(overrides: Record<string, unknown> = {}) {
  const spread = (outcome: string, probability: number) => ({
    market_name: "Frances Tiafoe vs Ben Shelton: Game Spread",
    outcome_name: outcome,
    threshold: null,
    probability,
    source: "kalshi",
    is_winner: null,
    resolution_source: null,
  });
  return {
    event_id: 15308439,
    home_team: "Frances Tiafoe",
    away_team: "Ben Shelton",
    home_score: null,
    away_score: null,
    status: "scheduled",
    player_props: [],
    team_totals: [],
    period_markets: [],
    matchups: [],
    other: [],
    pace: null,
    props_script: [],
    spreads: [
      spread("Ben Shelton -1.5 games", 0.62),
      spread("Ben Shelton -4.5 games", 0.41),
      spread("Ben Shelton -7.5 games", 0.24),
    ],
    totals: [
      {
        threshold: 34.5,
        over_probability: 0.695,
        source: "kalshi",
        market_type: "game_total",
        market_name: "Frances Tiafoe vs Ben Shelton: Total Games",
        outcome_name: "Over 34.5 games",
        is_winner: null,
        resolution_source: null,
        movement: 0,
        period: null,
      },
      {
        threshold: 38.5,
        over_probability: 0.42,
        source: "kalshi",
        market_type: "game_total",
        market_name: "Frances Tiafoe vs Ben Shelton: Total Games",
        outcome_name: "Over 38.5 games",
        is_winner: null,
        resolution_source: null,
        movement: 0,
        period: null,
      },
    ],
    ...overrides,
  };
}

function renderSF(overrides: Record<string, unknown> = {}) {
  return visibleText(
    renderToStaticMarkup(
      <MarketMapSection
        gameMarkets={tiafoeShelton(overrides) as never}
        eventStatus="scheduled"
        homeTeam="Frances Tiafoe"
        awayTeam="Ben Shelton"
        homeAbbr="TIA"
        awayAbbr="SHE"
        homeWinProb={0.275}
        awayWinProb={0.725}
        homeSpread={4.5}
        overUnder={39.9}
        sportKey="tennis_atp_us_open"
      />
    )
  );
}

describe("#4460 — a one-card map column does not repeat the card's title", () => {
  const vocab = sportVocab("tennis_atp_us_open");

  it("THE DEFECT: 'Game margin map' was printed twice, one above the other", () => {
    const text = renderSF();
    // The card really rendered. Without this the count below would be
    // satisfied by a column that was never drawn at all — a fix that empties
    // the section would pass a bare "not twice" assertion.
    expect(text).toContain(vocab.marginTitle);
    expect(occurrences(text, vocab.marginTitle)).toBe(1);
  });

  it("the totals column has the same shape and the same rule", () => {
    const text = renderSF();
    expect(text).toContain(vocab.totalTitle);
    expect(occurrences(text, vocab.totalTitle)).toBe(1);
  });

  it("the card keeps its own title and subtitle — the EYEBROW is what went", () => {
    // Which of the two duplicates disappeared matters. Dropping the card's
    // heading instead would leave a 10px grey all-caps label as the only name
    // for a chart, which is the same defect wearing the other hat.
    const text = renderSF();
    expect(text).toContain("Expected margin distribution");
    expect(text).toContain("SHE 73%");
  });
});

/**
 * THE POSITIVE CONTROL.
 *
 * A column that really does group two cards still gets its eyebrow, and the
 * eyebrow is the plural. Without this, "delete the heading entirely" passes
 * every assertion above.
 */
describe("#4460 — a column with more than one card keeps its eyebrow", () => {
  function nflWithHalfSpreads() {
    const full = (outcome: string, probability: number) => ({
      market_name: "Chiefs vs Bills: Spread",
      outcome_name: outcome,
      threshold: null,
      probability,
      source: "kalshi",
      is_winner: null,
      resolution_source: null,
    });
    const half = (outcome: string, probability: number) => ({
      market_type: "half_spread",
      market_name: "Chiefs vs Bills: 1st Half Spread",
      outcome_name: outcome,
      period: "1H",
      threshold: null,
      probability,
      source: "kalshi",
      is_winner: null,
      resolution_source: null,
    });
    return {
      event_id: 1,
      home_team: "Kansas City Chiefs",
      away_team: "Buffalo Bills",
      home_score: null,
      away_score: null,
      status: "scheduled",
      player_props: [],
      team_totals: [],
      matchups: [],
      other: [],
      pace: null,
      props_script: [],
      totals: [],
      spreads: [
        full("Kansas City Chiefs -2.5", 0.58),
        full("Kansas City Chiefs -6.5", 0.38),
        full("Kansas City Chiefs -10.5", 0.19),
      ],
      period_markets: [
        half("Kansas City Chiefs -1.5", 0.57),
        half("Kansas City Chiefs -3.5", 0.44),
        half("Kansas City Chiefs -6.5", 0.26),
      ],
    };
  }

  it("two margin cards ⇒ the plural eyebrow is back", () => {
    const vocab = sportVocab("americanfootball_nfl");
    const text = visibleText(
      renderToStaticMarkup(
        <MarketMapSection
          gameMarkets={nflWithHalfSpreads() as never}
          eventStatus="scheduled"
          homeTeam="Kansas City Chiefs"
          awayTeam="Buffalo Bills"
          homeAbbr="KC"
          awayAbbr="BUF"
          homeWinProb={0.62}
          awayWinProb={0.38}
          homeSpread={-2.5}
          overUnder={47.5}
          sportKey="americanfootball_nfl"
        />
      )
    );
    const plural = `${vocab.marginTitle.replace(/ map$/i, "")} maps`;
    // Both cards drew, so there really are two to group.
    expect(text).toContain(vocab.marginTitle);
    expect(text).toContain(plural);
  });
});
