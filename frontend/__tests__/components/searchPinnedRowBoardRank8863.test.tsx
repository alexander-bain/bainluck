/**
 * #8863 — a search card's pinned row prints its place on the board, not "5".
 *
 * `/api/events/search` (#8842, live 2026-09-26 17:07Z) pins the outcome that
 * answered the reader's query into the LAST row of a card recalled through that
 * outcome, and stamps it `query_match: true` + `matched_rank` (its place on the
 * whole board by price). `FuturesCard` badged every row `index + 1`, so on
 * `?q=ohtani` (390px, 2026-09-26 17:58Z) `MLB: Home Runs Leader` drew Ohtani
 * with a "5" while he is 8th — the badge read as "fifth on the board".
 *
 * The specimen below is that card's `top_outcomes` as served at 17:58Z, trimmed
 * to the fields the card reads. Badges are read off the rank span's class
 * signature (the one #4416's suite pins, so an avatar's initials cannot pass as
 * a rank) and bound to their row's `data-outcome-label`, so "right digits on
 * the wrong rows" cannot pass.
 */

import { renderToStaticMarkup } from "react-dom/server";
import FuturesCard from "../../components/FuturesCard";
import type { FuturesMarket, FuturesOutcome } from "../../lib/types";

function outcome(
  id: number,
  name: string,
  probability: number,
  over: Partial<FuturesOutcome> = {},
): FuturesOutcome {
  return {
    id,
    name,
    probability,
    american_odds: null,
    rank: null,
    rank_change_24h: null,
    probability_change_24h: null,
    movement: null,
    opening_probability: null,
    opening_american_odds: null,
    is_winner: false,
    last_updated: null,
    ...over,
  } as FuturesOutcome;
}

function market(top_outcomes: FuturesOutcome[]): FuturesMarket {
  return {
    id: 12516244,
    name: "MLB: Home Runs Leader",
    description: null,
    source: "kalshi",
    category: null,
    sport: "baseball_mlb",
    sport_name: null,
    llm_sport_category: "baseball",
    external_id: null,
    mutually_exclusive: true,
    commence_time: null,
    resolution_date: null,
    outcome_count: 28,
    created_at: null,
    updated_at: null,
    status: "open",
    top_outcomes,
  } as unknown as FuturesMarket;
}

/** [label, badge] per rendered row, in screen order. */
function rows(html: string): [string, string][] {
  const found = [
    ...html.matchAll(/<span class="[^"]*w-5 h-5 flex items-center justify-center text-\[10px\][^"]*">(\d+)<\/span>[\s\S]*?data-outcome-label[^>]*>([^<]*)</g),
  ].map(([, badge, label]) => [label, badge] as [string, string]);
  if (found.length === 0) {
    throw new Error("no badge/label rows rendered — the extractor is blind, not the card empty");
  }
  return found;
}

const render = (m: FuturesMarket) => renderToStaticMarkup(<FuturesCard market={m} />);

const SERVED = [
  outcome(1, "Kyle Schwarber", 0.62),
  outcome(2, "Pete Crow-Armstrong", 0.325),
  outcome(3, "Pete Alonso", 0.009),
  outcome(4, "Junior Caminero", 0.0055),
  outcome(5, "Shohei Ohtani", 0.0005, { query_match: true, matched_rank: 8 }),
];

describe("#8863 the pinned search row prints its board rank", () => {
  it("the production specimen: Ohtani stays last and reads 8, the rest read 1…4", () => {
    expect(rows(render(market(SERVED)))).toEqual([
      ["Kyle Schwarber", "1"],
      ["Pete Crow-Armstrong", "2"],
      ["Pete Alonso", "3"],
      ["Junior Caminero", "4"],
      ["Shohei Ohtani", "8"],
    ]);
  });

  it("the issue's shape: last row query_match + matched_rank 9 renders 9", () => {
    const served = [...SERVED.slice(0, 4), outcome(5, "Shohei Ohtani", 0.0005, { query_match: true, matched_rank: 9 })];
    expect(rows(render(market(served))).at(-1)).toEqual(["Shohei Ohtani", "9"]);
  });

  it("control: the same five without the key still read 1…5", () => {
    const plain = SERVED.map(({ query_match: _q, matched_rank: _r, ...o }) => o as FuturesOutcome);
    expect(rows(render(market(plain))).map(([, badge]) => badge)).toEqual(["1", "2", "3", "4", "5"]);
  });

  it("matched_rank alone, without query_match, does not move a badge", () => {
    const stray = [...SERVED.slice(0, 4), outcome(5, "Shohei Ohtani", 0.0005, { matched_rank: 8 })];
    expect(rows(render(market(stray))).at(-1)).toEqual(["Shohei Ohtani", "5"]);
  });
});
