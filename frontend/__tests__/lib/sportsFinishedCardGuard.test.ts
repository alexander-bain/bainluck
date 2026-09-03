import { applyFinishedCardGuard } from "@/lib/sports/finishedCardGuard";
import { groupFeedIntoSections } from "@/lib/feedSections";
import { isStale } from "@/lib/discover/feedFreshness";
import type { FeedItem, FeedEventData } from "@/lib/types";
import productionPageOne from "../fixtures/sportsFeedPageOne.20260903T0315Z.json";

// UX-1034f — the /sports finished-card guard, replayed over the LIVE payload it
// was measured on: `GET /api/feed?limit=40&mode=sports`, production,
// 2026-09-03T03:15:41Z. The clock is pinned to that instant because the fixture
// carries absolute `commence_time`s — the anchor is a constant, never a branch
// (gotcha #44).
const MEASURED_AT = new Date("2026-09-03T03:15:41.913Z");

const PAGE_ONE = (productionPageOne as { items: FeedItem[] }).items;

function events(items: FeedItem[]): FeedEventData[] {
  return items
    .filter((i) => i.type === "event")
    .map((i) => i.data as unknown as FeedEventData);
}

function completedIds(items: FeedItem[]): number[] {
  return events(items)
    .filter((d) => d.status === "completed" || d.status === "closed")
    .map((d) => d.id);
}

function event(opts: {
  id: number;
  status: string;
  hoursAgo: number;
}): FeedItem {
  return {
    type: "event",
    data: {
      id: opts.id,
      home_team: `Home ${opts.id}`,
      away_team: `Away ${opts.id}`,
      status: opts.status,
      commence_time: new Date(
        MEASURED_AT.getTime() - opts.hoursAgo * 3600 * 1000,
      ).toISOString(),
      current_odds: { home_probability: 0.5, away_probability: 0.5 },
    },
  } as unknown as FeedItem;
}

function futures(opts: { id: number; status?: string }): FeedItem {
  return {
    type: "futures",
    data: {
      id: opts.id,
      name: "Who wins it?",
      status: opts.status ?? "open",
      resolution_date: null,
      top_outcomes: [{ name: "A", probability: 0.6 }],
    },
  } as unknown as FeedItem;
}

beforeAll(() => {
  jest.useFakeTimers();
  jest.setSystemTime(MEASURED_AT);
});

afterAll(() => {
  jest.useRealTimers();
});

describe("the production payload this guard was measured on", () => {
  // The control: without the guard, /sports page one really was a results wall.
  // If this ever stops holding, the fixture no longer reproduces the defect and
  // every assertion below is vacuous.
  it("carries 20 completed game cards out of 24 events", () => {
    expect(PAGE_ONE).toHaveLength(40);
    expect(events(PAGE_ONE)).toHaveLength(24);
    expect(completedIds(PAGE_ONE)).toHaveLength(20);
  });

  it("is what Discover's gate would already have filtered — /sports just never asked", () => {
    // The gate is not new code; it is the same predicate Discover runs. Seven of
    // the twenty completed cards fail it on this payload.
    expect(PAGE_ONE.filter(isStale)).toHaveLength(7);
  });
});

describe("applyFinishedCardGuard on the live payload", () => {
  it("ages out the four cards the freshness bucket named, and only stale ones", () => {
    const { items, agedOut, keptToAvoidEmptyGames } = applyFinishedCardGuard(PAGE_ONE);

    // The three the 19:39Z bucket recorded as PERSISTING, plus the one it filed
    // as new. These are the needle.
    const namedDead = [15299603, 15299604, 15300190, 15300436];
    for (const id of namedDead) {
      expect(completedIds(PAGE_ONE)).toContain(id);
      expect(completedIds(items)).not.toContain(id);
    }

    expect(agedOut).toHaveLength(7);
    expect(items).toHaveLength(33);
    expect(keptToAvoidEmptyGames).toBe(false);
    // Everything removed is genuinely stale by the shared authority.
    expect(agedOut.every(isStale)).toBe(true);
  });

  it("keeps the same-day results the 'Just Happened' section exists to carry", () => {
    const { items } = applyFinishedCardGuard(PAGE_ONE);
    // 13 finals that started 2.8–7.7h before the measurement survive; the
    // guard is an age-out, not a ban on results content.
    expect(completedIds(items)).toHaveLength(13);
    // A concrete one: Brewers–Cubs, 3.7h old at the measurement.
    expect(completedIds(items)).toContain(15300468);
  });

  it("touches nothing but the stale cards — live games, futures and concepts all survive", () => {
    const { items } = applyFinishedCardGuard(PAGE_ONE);
    const liveBefore = events(PAGE_ONE).filter((d) => d.status === "live").length;
    const liveAfter = events(items).filter((d) => d.status === "live").length;
    expect(liveBefore).toBe(4);
    expect(liveAfter).toBe(4);

    const countType = (list: FeedItem[], type: string) =>
      list.filter((i) => i.type === type).length;
    expect(countType(items, "futures")).toBe(countType(PAGE_ONE, "futures"));
    expect(countType(items, "concept")).toBe(countType(PAGE_ONE, "concept"));
    expect(countType(items, "tournament")).toBe(countType(PAGE_ONE, "tournament"));
  });

  it("preserves the backend's ordering", () => {
    const { items } = applyFinishedCardGuard(PAGE_ONE);
    const survivorOrder = PAGE_ONE.filter((i) => items.includes(i));
    expect(items).toEqual(survivorOrder);
  });

  it("shortens the wall the reader hits before Upcoming and Top Markets", () => {
    // Gotcha #43 — assert BOTH directions: the flood is capped AND the sections
    // it was burying are still populated.
    const before = groupFeedIntoSections(PAGE_ONE);
    const after = groupFeedIntoSections(applyFinishedCardGuard(PAGE_ONE).items);
    const count = (sections: typeof before, key: string) =>
      sections.find((s) => s.key === key)?.items.length ?? 0;

    expect(count(before, "finished")).toBe(20);
    expect(count(after, "finished")).toBe(13);
    expect(count(after, "live")).toBe(count(before, "live"));
    expect(count(after, "markets")).toBe(count(before, "markets"));
    expect(count(after, "markets")).toBeGreaterThan(0);
  });
});

describe("#1091 — the guard never filters the sports feed into having no games", () => {
  it("declines its own age-out when every game in the payload is stale", () => {
    const payload = [
      event({ id: 1, status: "completed", hoursAgo: 20 }),
      event({ id: 2, status: "completed", hoursAgo: 30 }),
      futures({ id: 900 }),
    ];
    const { items, agedOut, keptToAvoidEmptyGames } = applyFinishedCardGuard(payload);

    expect(keptToAvoidEmptyGames).toBe(true);
    expect(items).toHaveLength(3);
    expect(agedOut).toHaveLength(0);
    expect(groupFeedIntoSections(items).find((s) => s.key === "finished")?.items).toHaveLength(2);
  });

  it("still ages out stale futures in that same reprieve — only games are spared", () => {
    const payload = [
      event({ id: 1, status: "completed", hoursAgo: 20 }),
      futures({ id: 900, status: "resolved" }),
      futures({ id: 901 }),
    ];
    const { items, agedOut, keptToAvoidEmptyGames } = applyFinishedCardGuard(payload);

    expect(keptToAvoidEmptyGames).toBe(true);
    expect(agedOut.map((i) => (i.data as { id: number }).id)).toEqual([900]);
    expect(items).toHaveLength(2);
  });

  it("does NOT reprieve when one live game survives — the wall still goes", () => {
    const payload = [
      event({ id: 1, status: "completed", hoursAgo: 20 }),
      event({ id: 2, status: "completed", hoursAgo: 30 }),
      event({ id: 3, status: "live", hoursAgo: 1 }),
    ];
    const { items, agedOut, keptToAvoidEmptyGames } = applyFinishedCardGuard(payload);

    expect(keptToAvoidEmptyGames).toBe(false);
    expect(agedOut).toHaveLength(2);
    expect(items.map((i) => (i.data as { id: number }).id)).toEqual([3]);
  });

  it("is a no-op on a payload with nothing stale in it", () => {
    const payload = [
      event({ id: 1, status: "live", hoursAgo: 1 }),
      event({ id: 2, status: "completed", hoursAgo: 2 }),
      futures({ id: 900 }),
    ];
    const result = applyFinishedCardGuard(payload);

    expect(result.items).toBe(payload);
    expect(result.agedOut).toHaveLength(0);
    expect(result.keptToAvoidEmptyGames).toBe(false);
  });

  it("has no games to protect when the payload is markets-only", () => {
    const payload = [futures({ id: 900, status: "resolved" }), futures({ id: 901 })];
    const { items, agedOut, keptToAvoidEmptyGames } = applyFinishedCardGuard(payload);

    expect(keptToAvoidEmptyGames).toBe(false);
    expect(agedOut).toHaveLength(1);
    expect(items).toHaveLength(1);
  });
});
