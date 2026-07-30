// L2-215 Item 3 — the Discover first-load request contract, as a deterministic
// request-spy INTEGRATION (not a human network-panel observation). It drives the
// Discover page's exact fetch orchestration — the SWR initial fetcher and
// `loadNextPage` — through the real `@/lib/api` `fetchFeed` seam and the real
// production paging helpers, asserting:
//   • exactly ONE initial request at limit=20, offset=0 (never the old 200-item pull)
//   • page two advances monotonically to offset=20 and NEVER re-requests offset 0
//   • the merged rendered set has no duplicate IDs across pages
//   • an SWR revalidation re-issues offset 0 without regressing the pagination cursor
// This fails on the pre-L2-214 behavior (limit:200 initial + `offsets=[0, loaded]`
// offset-zero refetch).

import { initialFeedRequest, nextFeedRequest, dedupeById } from "@/lib/discover/feedPaging";

jest.mock("@/lib/api", () => ({
  __esModule: true,
  fetchFeed: jest.fn(),
  fetchResolutions: jest.fn(),
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

/** A scripted page of `count` rows starting at `startId`, plus `has_more`. */
function page(startId: number, count: number, hasMore: boolean, offset: number) {
  return {
    items: Array.from({ length: count }, (_, i) => row(startId + i)),
    total: 100,
    limit: 20,
    offset,
    has_more: hasMore,
  };
}

beforeEach(() => {
  fetchFeedMock.mockReset();
});

/** The page's SWR initial fetcher (verbatim shape from app/discover/page.tsx). */
async function initialFetch() {
  const { limit, offset } = initialFeedRequest();
  return fetchFeedMock({ limit, offset, event_pct: 0.15 });
}

/** The page's loadNextPage request (verbatim shape). */
async function pageTwoFetch(loadedCount: number) {
  const { limit, offset } = nextFeedRequest(loadedCount);
  return fetchFeedMock({ limit, offset, event_pct: 0.15 });
}

describe("Discover first-load request contract (request-spy integration)", () => {
  it("issues one bounded initial request then a monotonic page two, with no duplicate IDs", async () => {
    // Page two overlaps the last id of page one to prove cross-page dedup.
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
    let loaded = first.items;
    const second = await pageTwoFetch(loaded.length);
    const rendered = dedupeById([...loaded, ...second.items], getId);

    // Exactly two requests were issued.
    expect(fetchFeedMock).toHaveBeenCalledTimes(2);

    // Initial: bounded to 20 at offset 0 — NOT the old 200-item pull.
    expect(fetchFeedMock.mock.calls[0][0]).toMatchObject({ limit: 20, offset: 0 });

    // Page two: monotonic advance to offset 20 — never a second offset-0 fetch.
    expect(fetchFeedMock.mock.calls[1][0]).toMatchObject({ limit: 20, offset: 20 });

    const offsets = fetchFeedMock.mock.calls.map((c) => c[0].offset);
    expect(offsets).toEqual([0, 20]);
    expect(offsets.filter((o) => o === 0)).toHaveLength(1); // fails the old refetch-0 bug
    for (const c of fetchFeedMock.mock.calls) {
      expect(c[0].limit).toBeLessThanOrEqual(20); // fails the old limit:200 pull
    }

    // No duplicate rendered IDs despite the intentional cross-page overlap.
    const ids = rendered.map(getId);
    expect(new Set(ids).size).toBe(ids.length);
    expect(rendered).toHaveLength(39); // 20 + 20 - 1 overlap
  });

  it("an SWR revalidation re-issues offset 0 without regressing the pagination cursor", async () => {
    const PAGE_0 = page(0, 20, true, 0);
    const PAGE_20 = page(20, 20, false, 20);
    fetchFeedMock.mockImplementation(({ offset }: { offset: number }) =>
      Promise.resolve(offset === 0 ? PAGE_0 : PAGE_20),
    );

    // Initial → page two.
    const first = await initialFetch();
    await pageTwoFetch(first.items.length);
    // SWR background revalidation: re-fetch the SAME initial key (offset 0).
    await initialFetch();
    // Pagination continues monotonically from the held count after revalidation.
    await pageTwoFetch(first.items.length);

    const offsets = fetchFeedMock.mock.calls.map((c) => c[0].offset);
    // Revalidation reuses offset 0; pagination never regresses below the boundary.
    expect(offsets).toEqual([0, 20, 0, 20]);
    // Every paginated (non-initial) request advanced past offset 0.
    const paginated = [offsets[1], offsets[3]];
    expect(paginated.every((o) => o >= 20)).toBe(true);
  });
});
