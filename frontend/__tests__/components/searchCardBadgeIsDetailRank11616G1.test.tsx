/**
 * #11616 G1 + N1 — the search card's RENDERED badge is detail's rank for the
 * same row, and a priceless row prints none.
 *
 * Root's ROOT-6430-REVIEW-DISPOSITION (G1): the badge was asserted at field level
 * only (backend `matched_rank`). These are lane1b's rendered-card inputs
 * (DELTA-REVIEW-6430a461 §1, `gamma-epsilon-cards.json`, the actual producer's
 * cards for Argon's empty-book board) through `FuturesCard`, with the expected
 * digits written out from detail's ranks rather than read back from the fixture.
 *
 * Two disclosed edits, as in lane1b's probe: the producer test helper stamps
 * `outcome_count: 2` whatever its legs, so the card counts its legs; and its
 * "politics" category swaps rank badges for avatars (#4416), so a sports
 * category shows the badge.
 */

import { renderToStaticMarkup } from "react-dom/server";
import FuturesCard from "../../components/FuturesCard";
import type { FuturesMarket } from "../../lib/types";
import cards from "../fixtures/gamma_epsilon_cards_lane1b_6430a461.json";

type Board = keyof typeof cards;

function card(board: Board, edit: (m: FuturesMarket) => FuturesMarket = (m) => m): FuturesMarket {
  const served = cards[board].card as unknown as FuturesMarket;
  return edit({
    ...served,
    outcome_count: Object.keys(cards[board].detail_rank).length,
    llm_sport_category: "basketball",
  });
}

/** [label, badge digit] per rendered row, in card order. */
function badges(market: FuturesMarket): [string, string][] {
  const html = renderToStaticMarkup(
    <FuturesCard market={market} readsOpenFieldOuts keepsServedOrder />,
  );
  const found = [...html.matchAll(
    /<span class="([^"]*w-5 h-5 flex items-center justify-center text-\[10px\][^"]*)">(\d*)<\/span>[\s\S]*?data-outcome-label[^>]*>([^<]*)</g,
  )].map(([, , badge, label]) => [label, badge] as [string, string]);
  if (found.length === 0) throw new Error("extractor blind");
  return found;
}

describe("G1: the rendered badge is detail's rank; a priceless row prints none", () => {
  it("Gamma, the priced pin, prints detail's 3 (00791f95 printed 1)", () => {
    expect(Object.fromEntries(badges(card("gamma")))).toEqual({
      "Gamma Example": "3",
      "Delta Example": "4",
      "Alpha Example": "",
      "Beta Example": "",
    });
  });

  it("Epsilon, Argon's priced control, prints detail's 3", () => {
    expect(Object.fromEntries(badges(card("epsilon")))).toEqual({
      "Epsilon Example": "3",
      "Gamma Example": "2",
      "Alpha Example": "",
    });
  });

  it("beta, a priceless pinned supported result, prints no number", () => {
    expect(Object.fromEntries(badges(card("beta")))).toEqual({
      "Beta Example": "",
      "Alpha Example": "",
      "Gamma Example": "3",
      "Delta Example": "4",
    });
  });

  it("the expected digits are detail's own ranks for every priced row", () => {
    for (const board of Object.keys(cards) as Board[]) {
      const ranks = cards[board].detail_rank as Record<string, number>;
      for (const [label, badge] of badges(card(board))) {
        const row = (card(board).top_outcomes ?? []).find((o) => o.name === label)!;
        expect(badge).toBe(row.probability == null ? "" : String(ranks[label]));
      }
    }
  });
});

describe("N1: a ranked row whose matched_rank differs still prints its rank", () => {
  // Defensive only: no deployed producer serves this pair (master serves no
  // `rank`). An earlier build of this PR served the strictly-above count here.
  it("Gamma with a stale matched_rank 1 prints detail's 3", () => {
    const stale = card("gamma", (m) => ({
      ...m,
      top_outcomes: (m.top_outcomes ?? []).map((o) =>
        o.name === "Gamma Example" ? { ...o, matched_rank: 1 } : o,
      ),
    }));
    expect(Object.fromEntries(badges(stale))["Gamma Example"]).toBe("3");
  });
});
