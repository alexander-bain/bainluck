import { isStale } from "@/lib/discover/feedFreshness";
import type { FeedItem } from "@/lib/types";

// L2-214 Item 0/2 — the PRODUCTION client freshness gate the Discover page uses.
// Mirrors backend/scripts/evals/feed_credibility_fixtures.json: only AUTHORITATIVE
// lifecycle/date evidence settles a card; probability ALONE never does.

const PAST = "2000-01-01T00:00:00Z";
const FUTURE = "2999-01-01T00:00:00Z";

function futures(opts: {
  status?: string;
  resolution_date?: string | null;
  leader?: number;
  movement?: number;
}): FeedItem {
  return {
    type: "futures",
    data: {
      id: 1,
      name: "Who wins?",
      status: opts.status ?? "open",
      resolution_date: opts.resolution_date ?? null,
      top_outcomes:
        opts.leader != null
          ? [{ name: "A", probability: opts.leader, movement: opts.movement ?? 0 }]
          : [],
    },
  } as unknown as FeedItem;
}

function event(opts: { status?: string; commence_time: string }): FeedItem {
  return {
    type: "event",
    data: {
      id: 100,
      home_team: "Home",
      away_team: "Away",
      status: opts.status ?? "scheduled",
      commence_time: opts.commence_time,
    },
  } as unknown as FeedItem;
}

describe("discover client freshness — authoritative only (L2-214)", () => {
  it("active_known_future: open + future resolution surfaces", () => {
    expect(isStale(futures({ resolution_date: FUTURE, leader: 0.62 }))).toBe(false);
  });

  it("date_past_taylor_equivalent: past resolution date is stale", () => {
    expect(isStale(futures({ resolution_date: PAST, leader: 0.54 }))).toBe(true);
  });

  it("authoritative_resolved: resolved status is stale", () => {
    expect(isStale(futures({ status: "resolved", leader: 1.0 }))).toBe(true);
  });

  it("closed status is stale", () => {
    expect(isStale(futures({ status: "closed", leader: 0.5 }))).toBe(true);
  });

  it("unknown_date_otherwise_clean: open + no date surfaces (unknown stays unknown)", () => {
    expect(isStale(futures({ resolution_date: null, leader: 0.58 }))).toBe(false);
  });

  // THE core L2-214 assertion: price alone never settles a card.
  it("near_certain_but_open: 0.99 open with future date still surfaces", () => {
    expect(isStale(futures({ resolution_date: FUTURE, leader: 0.99 }))).toBe(false);
  });

  it("reject_price_only_settlement: a 0.99 open market is NOT hidden by price", () => {
    // The fixture flags hiding this as the violation; our gate keeps it surfaced.
    expect(isStale(futures({ status: "open", resolution_date: FUTURE, leader: 0.99 }))).toBe(false);
  });

  it("near-extreme low probability, open, still surfaces", () => {
    expect(isStale(futures({ resolution_date: FUTURE, leader: 0.01 }))).toBe(false);
  });

  it("near-decided with no movement, open, still surfaces (no price inference)", () => {
    expect(isStale(futures({ leader: 0.92, movement: 0 }))).toBe(false);
  });

  it("event completed and commenced > 8h ago is stale", () => {
    expect(isStale(event({ status: "completed", commence_time: PAST }))).toBe(true);
  });

  it("event completed but recent stays within the result window", () => {
    const twoHoursAgo = new Date(Date.now() - 2 * 3600 * 1000).toISOString();
    expect(isStale(event({ status: "completed", commence_time: twoHoursAgo }))).toBe(false);
  });

  it("scheduled future event surfaces", () => {
    expect(isStale(event({ status: "scheduled", commence_time: FUTURE }))).toBe(false);
  });
});
