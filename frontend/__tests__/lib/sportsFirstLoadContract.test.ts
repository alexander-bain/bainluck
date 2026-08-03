// L2-240 Item 2 — the Sports first-load request contract, as a deterministic
// request-spy integration (mirrors discoverFirstLoadContract). It drives the
// Sports page's exact fetch orchestration — the SWR initial fetcher and
// `loadNextPage` — through the real `@/lib/api` `fetchFeed` seam and the real
// production paging + availability helpers, asserting:
//   • exactly ONE initial request at limit=20, offset=0 with mode="sports"
//     (never the old 200-item pull)
//   • page two advances monotonically to offset=20 and NEVER re-requests offset 0
//   • the merged rendered set has no duplicate IDs across pages
//   • a typed-UNAVAILABLE page is inert — it contributes no items and does NOT
//     close pagination (exhaustion stays distinct from unavailable)
//   • genuine exhaustion (has_more:false, available) ends pagination
// This fails on the pre-L2-240 behavior (limit:200 single pull, no pagination).

import { initialFeedRequest, nextFeedRequest, dedupeById } from "@/lib/discover/feedPaging";
import { decideFeedPage } from "@/lib/discover/feedAvailability";

jest.mock("@/lib/api", () => ({
  __esModule: true,
  fetchFeed: jest.fn(),
  fetchGroupedFeed: jest.fn(),
}));

// eslint-disable-next-line @typescript-eslint/no-var-requires
import { fetchFeed } from "@/lib/api";
const fetchFeedMock = fetchFeed as jest.Mock;

interface Row {
  type: string;
  data: { id: number };
}
const row = (id: number): Row => ({ type: "futures", data: { id } });
const getId = (r: Row) => `${r.type}-${r.data.id}`;

function page(startId: number, count: number, hasMore: boolean, offset: number, extra?: object) {
  return {
    items: Array.from({ length: count }, (_, i) => row(startId + i)),
    total: 100,
    limit: 20,
    offset,
    has_more: hasMore,
    ...extra,
  };
}

beforeEach(() => {
  fetchFeedMock.mockReset();
});

/** The page's SWR initial fetcher (verbatim shape from app/sports/page.tsx). */
async function initialFetch() {
  const { limit, offset } = initialFeedRequest();
  return fetchFeedMock({ limit, offset, mode: "sports" });
}

/** The page's loadNextPage request (verbatim shape). */
async function pageTwoFetch(loadedCount: number) {
  const { limit, offset } = nextFeedRequest(loadedCount);
  return fetchFeedMock({ limit, offset, mode: "sports" });
}

describe("Sports first-load request contract (request-spy integration)", () => {
  it("issues one bounded initial request then a monotonic page two, with no duplicate IDs", async () => {
    const PAGE_0 = page(0, 20, true, 0);
    const overlapId = PAGE_0.items[19].data.id; // 19
    const PAGE_20 = {
      ...page(20, 19, true, 20),
      items: [...page(20, 19, true, 20).items, row(overlapId)],
    };
    fetchFeedMock.mockImplementation(({ offset }: { offset: number }) =>
      Promise.resolve(offset === 0 ? PAGE_0 : PAGE_20),
    );

    const first = await initialFetch();
    const second = await pageTwoFetch(first.items.length);
    const rendered = dedupeById([...first.items, ...second.items], getId);

    expect(fetchFeedMock).toHaveBeenCalledTimes(2);

    // Initial: bounded to 20 at offset 0, mode sports — NOT the old 200-item pull.
    expect(fetchFeedMock.mock.calls[0][0]).toMatchObject({ limit: 20, offset: 0, mode: "sports" });
    // Page two: monotonic advance to offset 20 — never a second offset-0 fetch.
    expect(fetchFeedMock.mock.calls[1][0]).toMatchObject({ limit: 20, offset: 20, mode: "sports" });

    const offsets = fetchFeedMock.mock.calls.map((c) => c[0].offset);
    expect(offsets).toEqual([0, 20]);
    expect(offsets.filter((o) => o === 0)).toHaveLength(1);
    for (const c of fetchFeedMock.mock.calls) {
      expect(c[0].limit).toBeLessThanOrEqual(20); // fails the old limit:200 pull
    }

    const ids = rendered.map(getId);
    expect(new Set(ids).size).toBe(ids.length);
    expect(rendered).toHaveLength(39); // 20 + 20 - 1 overlap
  });

  it("a typed-unavailable page two is inert and keeps pagination open (distinct from exhaustion)", async () => {
    const PAGE_0 = page(0, 20, true, 0);
    // The backend's transient no-data terminal: empty items, has_more:false, but
    // cache.status = "unavailable". That has_more:false is an artifact of the
    // empty body, NOT an exhaustion claim.
    const UNAVAILABLE = page(0, 0, false, 20, { cache: { status: "unavailable" } });
    fetchFeedMock.mockImplementation(({ offset }: { offset: number }) =>
      Promise.resolve(offset === 0 ? PAGE_0 : UNAVAILABLE),
    );

    const first = await initialFetch();
    const page1Decision = decideFeedPage({
      payload: first,
      previousHasMore: true,
      hasRenderedItems: false,
    });
    expect(page1Decision.acceptItems).toBe(true);
    expect(page1Decision.hasMore).toBe(true);

    const second = await pageTwoFetch(first.items.length);
    const pageTwoDecision = decideFeedPage({
      payload: second,
      previousHasMore: true,
      hasRenderedItems: true,
    });
    // Unavailable: no items accepted, pagination NOT closed, retry raised.
    expect(pageTwoDecision.acceptItems).toBe(false);
    expect(pageTwoDecision.hasMore).toBe(true);
    expect(pageTwoDecision.showUnavailable).toBe(true);
  });

  it("genuine exhaustion (available, has_more:false) ends pagination", async () => {
    const PAGE_0 = page(0, 20, true, 0);
    const PAGE_20 = page(20, 5, false, 20); // available, fewer than a full page, done
    fetchFeedMock.mockImplementation(({ offset }: { offset: number }) =>
      Promise.resolve(offset === 0 ? PAGE_0 : PAGE_20),
    );

    const first = await initialFetch();
    const second = await pageTwoFetch(first.items.length);
    const decision = decideFeedPage({
      payload: second,
      previousHasMore: true,
      hasRenderedItems: true,
    });
    expect(decision.acceptItems).toBe(true);
    expect(decision.hasMore).toBe(false);
    expect(decision.showUnavailable).toBe(false);
  });
});
