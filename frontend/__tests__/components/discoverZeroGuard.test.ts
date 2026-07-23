// L2-164 Item 3: belt-and-suspenders 0% card guard. A default futures card whose
// leader is sub-1% renders a bare live-looking "0%" (the stale post-Open golf
// class) and must be suppressed — unless it carries settled context. Both
// directions covered.
import { suppressBareZeroFuturesCard } from "../../components/discover/utils";
import type { FeedItem, FeedFuturesData } from "../../lib/types";

function futures(data: Partial<FeedFuturesData>): FeedItem {
  return {
    type: "futures",
    data: {
      id: 1,
      name: "Tournament winner",
      sport: null,
      sport_name: null,
      llm_sport_category: null,
      source: "kalshi",
      source_count: 1,
      market_tier: 1,
      status: "open",
      resolution_date: null,
      top_outcomes: [{ id: 1, name: "Leader", probability: 0.0, rank: 1, movement: null }],
      outcome_count: 10,
      canonical_market_key: null,
      ...data,
    } as FeedFuturesData,
  } as unknown as FeedItem;
}

const NOW = new Date("2026-07-22T00:00:00Z").getTime();

describe("suppressBareZeroFuturesCard", () => {
  test("suppresses a bare sub-1% leader with no settled context", () => {
    expect(suppressBareZeroFuturesCard(futures({}), NOW)).toBe(true);
    expect(
      suppressBareZeroFuturesCard(
        futures({ top_outcomes: [{ id: 1, name: "L", probability: 0.004, rank: 1, movement: null }] }),
        NOW,
      ),
    ).toBe(true);
  });

  test("keeps a card whose leader is at/above 1%", () => {
    expect(
      suppressBareZeroFuturesCard(
        futures({ top_outcomes: [{ id: 1, name: "L", probability: 0.02, rank: 1, movement: null }] }),
        NOW,
      ),
    ).toBe(false);
  });

  test("keeps a settled sub-1% card (resolved flag / winner / status)", () => {
    expect(suppressBareZeroFuturesCard(futures({ resolved: true }), NOW)).toBe(false);
    expect(suppressBareZeroFuturesCard(futures({ winner: "Someone" }), NOW)).toBe(false);
    expect(suppressBareZeroFuturesCard(futures({ status: "resolved" }), NOW)).toBe(false);
  });

  test("keeps a card whose resolution_date is already past (shows a Resolved label)", () => {
    expect(
      suppressBareZeroFuturesCard(futures({ resolution_date: "2026-07-01T00:00:00Z" }), NOW),
    ).toBe(false);
  });

  test("leaves ladder formats (distribution / heatmap) alone", () => {
    expect(
      suppressBareZeroFuturesCard(
        futures({ discover_card: { suggested_format: "outcome_distribution" } } as Partial<FeedFuturesData>),
        NOW,
      ),
    ).toBe(false);
    expect(
      suppressBareZeroFuturesCard(
        futures({ discover_card: { suggested_format: "threshold_heatmap" } } as Partial<FeedFuturesData>),
        NOW,
      ),
    ).toBe(false);
  });

  test("null leader renders name-only (not a bare hero) — never suppressed", () => {
    expect(
      suppressBareZeroFuturesCard(
        futures({ top_outcomes: [{ id: 1, name: "L", probability: null, rank: 1, movement: null }] }),
        NOW,
      ),
    ).toBe(false);
  });

  test("non-futures items are never affected", () => {
    expect(suppressBareZeroFuturesCard({ type: "event", data: {} } as unknown as FeedItem, NOW)).toBe(false);
  });
});
