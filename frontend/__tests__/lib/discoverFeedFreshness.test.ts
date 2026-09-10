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

function event(opts: {
  status?: string;
  commence_time: string;
  ended_at?: string | null;
}): FeedItem {
  return {
    type: "event",
    data: {
      id: 100,
      home_team: "Home",
      away_team: "Away",
      status: opts.status ?? "scheduled",
      commence_time: opts.commence_time,
      ...(opts.ended_at !== undefined ? { ended_at: opts.ended_at } : {}),
    },
  } as unknown as FeedItem;
}

const hoursAgo = (h: number) => new Date(Date.now() - h * 3600 * 1000).toISOString();

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

// #4776 — the eight hours are counted from the WHISTLE, not the kickoff.
//
// This is the client half of the rule; `backend/tests/test_client_deletion_
// mirror_3836.py` pins the server's copy and reads this file to check the two
// have not drifted. Both halves are needed: the backend spends a first-page
// slot on the prediction that the browser will paint the card, and it is THIS
// function that decides whether it does.
describe("discover client freshness — a finished game ages from its end (#4776)", () => {
  it("keeps the NFL opener at the hour the kickoff clock deleted it", () => {
    // Real production row: event 14780138, SEA 13-10 NE. 3.11h long. Read at
    // 8.67h past kickoff / 5.56h past the whistle — the state in which the old
    // rule dropped it, which on the night was 1:20AM Pacific.
    expect(
      isStale(
        event({
          status: "completed",
          commence_time: hoursAgo(8.67),
          ended_at: hoursAgo(5.56),
        }),
      ),
    ).toBe(false);
  });

  it("still deletes it once eight hours have passed since the end", () => {
    expect(
      isStale(
        event({
          status: "completed",
          commence_time: hoursAgo(11.2),
          ended_at: hoursAgo(8.1),
        }),
      ),
    ).toBe(true);
  });

  it("falls back to commence_time when ended_at is absent", () => {
    // D109/#4676 requires the stamp stay OPTIONAL: it is absent on unsettled
    // rows and on any payload cached before the backend that added it. An
    // unstamped row must give exactly today's answer, both ways.
    expect(isStale(event({ status: "completed", commence_time: PAST }))).toBe(true);
    expect(
      isStale(event({ status: "completed", commence_time: hoursAgo(2) })),
    ).toBe(false);
  });

  it("falls back when ended_at is null or empty rather than reading it", () => {
    for (const blank of [null, ""] as (string | null)[]) {
      expect(
        isStale(event({ status: "completed", commence_time: PAST, ended_at: blank })),
      ).toBe(true);
    }
  });

  it("keeps a card whose ended_at is unreadable instead of ageing it out", () => {
    // `new Date("not a date")` is NaN and `NaN > 8` is false. Unknown age has
    // always meant "render it" here — inferring "old" from an unparseable stamp
    // would delete a card the reader was about to see.
    expect(
      isStale(
        event({
          status: "completed",
          commence_time: PAST,
          ended_at: "not a date",
        }),
      ),
    ).toBe(false);
  });

  it("does not touch a live game however long ago it started", () => {
    expect(
      isStale(event({ status: "live", commence_time: PAST, ended_at: PAST })),
    ).toBe(false);
  });
});
