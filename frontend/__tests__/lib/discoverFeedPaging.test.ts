import fs from "fs";
import path from "path";
import {
  FEED_PAGE_LIMIT,
  initialFeedRequest,
  nextFeedRequest,
  dedupeById,
} from "@/lib/discover/feedPaging";

// L2-214 Item 0/1 — drive the PRODUCTION request-plan helpers the Discover page
// uses (not a cloned copy) against the canonical C79 speed fixture, so the
// bounded-initial / monotonic-pagination / stable-id-dedup contract is pinned.
const SPEED_FIXTURE = JSON.parse(
  fs.readFileSync(
    path.join(__dirname, "../../../backend/scripts/evals/feed_speed_fixtures.json"),
    "utf8"
  )
);

/** Build the offset sequence the page issues: one initial (0), then N pages via
 *  nextFeedRequest, each advancing by the page size already held. */
function requestPlan(pages: number): { limit: number; offset: number }[] {
  const plan = [initialFeedRequest()];
  let loaded = FEED_PAGE_LIMIT; // initial page returned a full page
  for (let i = 0; i < pages; i++) {
    plan.push(nextFeedRequest(loaded));
    loaded += FEED_PAGE_LIMIT;
  }
  return plan;
}

describe("discover feed paging — production helpers", () => {
  it("initial request is bounded to the fixture max and starts at offset 0", () => {
    const initial = initialFeedRequest();
    expect(initial.offset).toBe(0);
    expect(initial.limit).toBeLessThanOrEqual(SPEED_FIXTURE.initial_page_limit_max);
    // bounded_initial_only fixture: exactly one initial request of <= 20 at offset 0
    expect(FEED_PAGE_LIMIT).toBeLessThanOrEqual(SPEED_FIXTURE.initial_page_limit_max);
  });

  it("pagination offsets are strictly increasing, > 0, and never re-request offset 0", () => {
    const plan = requestPlan(3);
    const pagination = plan.slice(1); // drop the initial
    const offsets = pagination.map((r) => r.offset);

    // matches fixture bounded_initial_and_pages: 20, 40, 60
    expect(offsets).toEqual([20, 40, 60]);
    // reject_offset_zero_pagination / reject_overlapping_offsets can never occur
    expect(offsets).toEqual([...offsets].sort((a, b) => a - b));
    expect(new Set(offsets).size).toBe(offsets.length);
    expect(offsets.every((o) => o > 0)).toBe(true);
    // reject_two_initial_200 / initial_page_unbounded can never occur
    expect(pagination.every((r) => r.limit <= SPEED_FIXTURE.initial_page_limit_max)).toBe(true);
  });

  it("nextFeedRequest never masquerades as a second offset-zero fetch", () => {
    // Even at a degenerate loadedCount of 0, pagination cannot re-fetch offset 0.
    expect(nextFeedRequest(0).offset).toBeGreaterThan(0);
    expect(nextFeedRequest(20).offset).toBe(20);
  });

  it("dedupeById renders each stable id once across overlapping pages", () => {
    // overlap_deduped_by_stable_id: pages [f1,f2] + [f2,f3] render f1,f2,f3 once.
    const overlap = SPEED_FIXTURE.scenarios.find(
      (s: { id: string }) => s.id === "overlap_deduped_by_stable_id"
    );
    const pageIds: string[][] = overlap.page_ids;
    const merged = pageIds.flat().map((id) => ({ id }));
    const deduped = dedupeById(merged, (x) => x.id);
    expect(deduped.map((x) => x.id)).toEqual(overlap.rendered_ids);
  });

  it("dedupeById drops an accidental duplicate render id (reject_duplicate_render_id)", () => {
    const withDup = [{ id: "futures-1" }, { id: "event-2" }, { id: "futures-1" }];
    expect(dedupeById(withDup, (x) => x.id).map((x) => x.id)).toEqual([
      "futures-1",
      "event-2",
    ]);
  });
});
