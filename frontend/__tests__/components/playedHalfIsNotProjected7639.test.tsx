/**
 * #7639 — THE HALF MARGIN CARD ASKS ITS LADDER'S SHAPE WHILE THE GAME IS LIVE.
 *
 * Seen on production at 390px on 2026-09-20 at 5:58 PM PDT, `/events/15312237`
 * — Inter Miami CF 1-1 San Diego FC, MLS, live in the 2nd half at `56'`:
 *
 *   1st half margin
 *     PROJECTION  MIA by 1.5+          <- the first half was over, and level
 *   2nd half margin
 *     PROJECTION  MIA by 1.5+          <- the identical tile, identically placed
 *
 * The venue's own `First Half Winner` in the same payload read `Tie 0.99 /
 * Miami 0.01 / San Diego 0.01`. The half had finished a draw.
 *
 * ## The rungs, and why the tile is an artefact twice over
 *
 * The four `half_spread` 1H rows `/api/events/15312237/game-markets` served at
 * 00:47Z are reproduced verbatim below. Rendered through the real component
 * they reduce to a two-rung ladder — `SD by 1.5+ 1%`, `MIA by 1.5+ 1%` — which
 * is the half correctly settled and a dead book. ZERO rungs inside the
 * 0.15-0.85 interior band.
 *
 * So `closest50` is choosing between two rungs 49 points from a coin flip and
 * equal to each other: not only is the NUMBER not a line anybody quoted, the
 * TEAM on the tile falls out of rung order. `MIA` rather than `SD` is a
 * `reduce` tie-break, not a reading.
 *
 * ## Why it survived three fixes aimed straight at it
 *
 * `probabilitiesQuoteALine` (#5488) refuses exactly this population, and
 * refuses it correctly the moment the game goes final — the last case here
 * proves that arm was already working. It was written behind `!isDone ||`,
 * which makes the GAME's status the gate on whether the ladder is asked about
 * its shape at all. A half finishes long before its game does, so on a live
 * game the question was never put.
 *
 * The half TOTALS card one section down has always asked on both arms
 * (`isDone ? settledLadderQuotesALine : quotesALine`). The margin card was the
 * only half card with an arm that tested nothing, which is the drift #5488's
 * own comment says the shared predicate exists to prevent.
 *
 * ## What makes this suite non-vacuous
 *
 * A missing tile proves nothing by itself: it is also what a payload with no
 * 1H rows looks like, and what a guard that deleted the feature looks like. So
 * every case renders the REAL `MarketMapSection`, and the arms differ ONLY in
 * the four 1H probabilities:
 *
 *   - the production ladder (all settled)  -> the 1st half tile is gone;
 *   - the same rungs while the book quotes -> the tile is BACK, on the same card.
 *
 * The second arm is the strawman check, and the 2nd half card — untouched in
 * both arms, quoting throughout — is the control that the suppression is
 * per-ladder and not per-page.
 */

import React from "react";
import { renderToStaticMarkup } from "react-dom/server";

import MarketMapSection from "@/components/MarketMapSection";

function visibleText(html: string): string {
  return html
    .replace(/<[^>]+>/g, " ")
    .replace(/&#x27;|&#39;|&apos;/g, "'")
    .replace(/&amp;/g, "&")
    .replace(/&[a-z]+;/g, " ")
    .replace(/\s+/g, " ")
    .trim();
}

const HOME = "Inter Miami CF";
const AWAY = "San Diego FC";

const HEADINGS = ["1st half margin", "2nd half margin"] as const;

/**
 * ONE card's text, bounded by its SIBLING's heading.
 *
 * Both half cards draw the same words, so a fixed-width window off a heading
 * reads the neighbour's tile and passes a suppression assertion that ought to
 * fail. The bound is the sibling heading and not any `half margin`, because
 * the card's own subtitle is "1st half margin distribution" — a loose bound
 * cuts there and reduces every assertion below to a test of twenty characters.
 * That the bound really holds is asserted, not trusted.
 */
function cardBody(text: string, heading: (typeof HEADINGS)[number]): string {
  const at = text.indexOf(heading);
  if (at === -1) return "";
  const rest = text.slice(at + heading.length);
  const sibling = HEADINGS.find((h) => h !== heading)!;
  const next = rest.indexOf(sibling);
  return heading + (next === -1 ? rest : rest.slice(0, next));
}

function spread(
  period: "1H" | "2H",
  market_name: string,
  outcome_name: string,
  probability: number,
  threshold: number | null
) {
  return {
    market_name,
    outcome_name,
    probability,
    threshold,
    point: null,
    market_type: "half_spread",
    period,
    source: "kalshi",
    over_probability: null,
    is_winner: null,
    resolution_source: null,
    movement: 0,
  };
}

/** The 2nd half as served — genuinely live, and the same in every arm. */
const SECOND_HALF = [
  spread("2H", "Miami vs San Diego FC: Second Half Spread", "Miami wins the 2H by more than 1.5 goals", 0.52, 2.0),
  spread("2H", "Miami vs San Diego FC: Second Half Spread", "San Diego FC wins the 2H by more than 1.5 goals", 0.26, 2.0),
];

/**
 * The four 1H rows as served at 00:47Z — the half settled under a sportsbook
 * that had not stopped quoting it.
 */
function firstHalf(miami: number, sandiego: number) {
  return [
    spread("1H", "1st Half Spread: Inter Miami CF (-1.5)", AWAY, 0.725, null),
    spread("1H", "1st Half Spread: Inter Miami CF (-1.5)", HOME, 0.27, null),
    spread("1H", "Miami vs San Diego FC: First Half Spread", "Miami wins the 1H by more than 1.5 goals", miami, 1.0),
    spread("1H", "Miami vs San Diego FC: First Half Spread", "San Diego FC wins the 1H by more than 1.5 goals", sandiego, 1.0),
  ];
}

/** Production, verbatim: both rungs settled to a penny. */
const SETTLED_1H = firstHalf(0.01, 0.01);
/** The same two rungs while the book is still making a price on them. */
const QUOTING_1H = firstHalf(0.44, 0.38);

function render(first: ReturnType<typeof firstHalf>, eventStatus = "live"): string {
  return visibleText(
    renderToStaticMarkup(
      <MarketMapSection
        gameMarkets={
          {
            event_id: 15312237,
            home_team: HOME,
            away_team: AWAY,
            home_score: 1,
            away_score: 1,
            status: eventStatus,
            player_props: [],
            team_totals: [],
            period_markets: [...first, ...SECOND_HALF],
            matchups: [],
            other: [],
            pace: null,
            props_script: [],
            spreads: [],
            totals: [],
          } as never
        }
        eventStatus={eventStatus}
        homeTeam={HOME}
        awayTeam={AWAY}
        homeAbbr="MIA"
        awayAbbr="SD"
        sportKey="soccer_usa_mls"
      />
    )
  );
}

describe("#7639 a live game's half card whose ladder has stopped quoting", () => {
  it("the extractor is bounded — or every suppression below is vacuous", () => {
    const first = cardBody(render(SETTLED_1H), "1st half margin");

    expect(first).toContain("1st half margin");
    expect(first).not.toContain("2nd half margin");
  });

  it("no longer prints the projection the reader saw", () => {
    const text = render(SETTLED_1H);

    expect(text).toContain("1st half margin");
    expect(cardBody(text, "1st half margin")).not.toContain("Projection");
  });

  it("and specifically not MIA by 1.5+, the tile that was on screen", () => {
    // Asserted as the PAIR. `MIA by 1.5+` alone is also a ladder rung on this
    // card — one that correctly reads 1% — so banning the bare string would
    // demand the settled rungs vanish too, which is a different and wrong ship.
    expect(cardBody(render(SETTLED_1H), "1st half margin")).not.toContain(
      "Projection MIA by 1.5+"
    );
  });

  it("strawman: the same card, same rungs, book quoting — the tile is back", () => {
    const body = cardBody(render(QUOTING_1H), "1st half margin");

    expect(body).toContain("Projection");
    expect(body).toContain("MIA by 1.5+");
  });

  it("control: the half that IS quoting keeps its projection in both arms", () => {
    expect(cardBody(render(SETTLED_1H), "2nd half margin")).toContain("Projection");
    expect(cardBody(render(QUOTING_1H), "2nd half margin")).toContain("Projection");
  });

  it("the settled rungs themselves stay on the card", () => {
    // The ladder is the honest half of this card and is not what was wrong.
    const body = cardBody(render(SETTLED_1H), "1st half margin");

    expect(body).toContain("MIA by 1.5+");
    expect(body).toContain("SD by 1.5+");
  });

  it("#5488's pre-game control is NOT this ship's to move", () => {
    // Before kickoff a dead half ladder is a book that has not opened yet, and
    // #5488 declined to remove the tile for it in as many words. Same rungs,
    // same card, `scheduled` — the tile stays. A fix written as `quotesALine`
    // alone passes every other case in this file and fails here, which is
    // precisely what #5488's own control already said it would.
    expect(cardBody(render(SETTLED_1H, "scheduled"), "1st half margin")).toContain(
      "Projection"
    );
  });

  it("the finished-game arm was already right, and has not moved", () => {
    // #5488's predicate refuses this exact ladder once the whistle goes; that
    // arm is the reason the defect was only ever visible while live. If this
    // ever fails, the fix has reached a case that was not broken.
    expect(cardBody(render(SETTLED_1H, "completed"), "1st half margin")).not.toContain(
      "Pre-game"
    );
    expect(cardBody(render(QUOTING_1H, "completed"), "1st half margin")).toContain(
      "Pre-game"
    );
  });
});
