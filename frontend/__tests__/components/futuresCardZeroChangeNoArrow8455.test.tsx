/**
 * #8455 — a futures card drew a red "↓ 0.0%" for a change that rounds to zero.
 *
 * Found by latency/1099 at 390px on production, `/search?q=superbowl`
 * (NFL Super Bowl Winner, market 86832), 2026-09-24: the search payload served
 * `movement: -5.3e-05` on the Rams row, the other rows the same size, and
 * `FuturesCard`'s `MovementIndicator` hid itself only at exactly 0 — so every
 * row printed a falling arrow beside "0.0%".
 *
 * Both directions (gotcha #43): a sub-display drift draws nothing; a real move
 * still draws its arrow and number.
 */
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";

import FuturesCard from "@/components/FuturesCard";
import type { FuturesMarket, FuturesOutcome } from "@/lib/types";

jest.mock("next/link", () => ({
  __esModule: true,
  default: ({ children, href }: { children: React.ReactNode; href: string }) => (
    <a href={href}>{children}</a>
  ),
}));

function outcome(id: number, name: string, probability: number, movement: number | null): FuturesOutcome {
  return {
    id,
    name,
    probability,
    american_odds: null,
    rank: null,
    rank_change_24h: null,
    probability_change_24h: null,
    movement,
    opening_probability: null,
    opening_american_odds: null,
    is_winner: null,
    last_updated: null,
  } as unknown as FuturesOutcome;
}

function card(movement: number | null): string {
  const market = {
    id: 86832,
    name: "NFL Super Bowl Winner",
    description: null,
    source: "kalshi",
    category: "championship",
    sport: "americanfootball_nfl",
    sport_name: "NFL",
    llm_sport_category: "football",
    external_id: null,
    mutually_exclusive: true,
    commence_time: null,
    resolution_date: null,
    outcome_count: 1,
    created_at: null,
    updated_at: null,
    status: "open",
    outcomes: [outcome(1, "Los Angeles Rams", 0.11, movement)],
  } as unknown as FuturesMarket;
  return renderToStaticMarkup(<FuturesCard market={market} />);
}

describe("#8455 FuturesCard draws no arrow for a change that prints as 0.0", () => {
  test("the production specimen: -5.3e-05 draws no falling arrow", () => {
    const html = card(-5.3e-5);
    expect(html).not.toContain("↓");
    expect(html).not.toContain("0.0%");
  });

  test("the same size upward draws no rising arrow", () => {
    expect(card(4.9e-4)).not.toContain("↑");
  });

  test("control: a real fall still draws ↓ 2.1%", () => {
    const html = card(-0.021);
    expect(html).toContain("↓");
    expect(html).toContain("2.1%");
  });

  test("control: the smallest change that prints non-zero still draws", () => {
    // 0.0006 → 0.06pp → "0.1".
    expect(card(0.0006)).toContain("↑");
  });

  test("control: no movement at all draws nothing, as before", () => {
    const html = card(null);
    expect(html).not.toContain("↓");
    expect(html).not.toContain("↑");
  });
});
