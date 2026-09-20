/**
 * #7417 — a Back out of a Discover card returns the reader to their place.
 *
 * THE DEFECT, MEASURED. Local production build, phone width, 3 runs of 3: the
 * reader left at scrollY 4558 and settled at 14931 / 15099 / 14931 — ~10,400px,
 * twelve screens, in the page footer. At every sample `scrollY` was exactly
 * `docHeight - 844`: pinned to the maximum, not scattered. The card count went
 * 20 → 40 while they sat there.
 *
 * That shape names a four-rung loop (see the header of `lib/discover/feedRestore`):
 * the loaded pages are discarded, the browser CLAMPS the restore into the
 * collapsed document, the clamp parks the reader on the pagination sentinel,
 * and the page that fetches grows the document under an anchored footer so the
 * sentinel is in view again.
 *
 * These tests are aimed at the rungs, not at the symptom. Each one fails if a
 * rung is uncut, and several assert the REFUSALS — a restore that fires on a
 * reload, or a scroll mark recorded mid-restore, reintroduces the bug wearing
 * the fix's clothes.
 */
import {
  FEED_SNAPSHOT_MAX_ITEMS,
  FEED_SNAPSHOT_TTL_MS,
  FEED_SNAPSHOT_VERSION,
  capSnapshotItems,
  landingTarget,
  markAndDetectClientTransition,
  parseFeedSnapshot,
  parseScrollMark,
  serializeFeedSnapshot,
  serializeScrollMark,
  shouldRestoreOnMount,
} from "@/lib/discover/feedRestore";

const item = (id: string) => ({ type: "futures", data: { id } });

describe("#7417 landingTarget — the clamp is the defect, so the height check is the fix", () => {
  it("refuses to land while the document cannot hold the offset", () => {
    // Rung 2, exactly: the reader left at 4558 and the rebuilt document is
    // 8661 tall with an 844 viewport, so the furthest the browser can go is
    // 7817. Any earlier frame is shorter still.
    const { y, reached } = landingTarget(4558, 2000, 844);
    expect(reached).toBe(false);
    // The best-available offset is the clamp — which is why `reached` has to
    // gate the scroll rather than the caller just using `y`.
    expect(y).toBe(1156);
  });

  it("lands exactly on the offset once the document is tall enough", () => {
    expect(landingTarget(4558, 8712, 844)).toEqual({ y: 4558, reached: true });
  });

  it("treats an exactly-fitting document as reached, not as one pixel short", () => {
    // docHeight - viewport === targetY. An off-by-one here spins the landing
    // loop to its timeout on every feed whose restore is at the very bottom.
    expect(landingTarget(4558, 5402, 844)).toEqual({ y: 4558, reached: true });
  });

  it("never returns a negative offset for a document shorter than the viewport", () => {
    expect(landingTarget(4558, 300, 844)).toEqual({ y: 0, reached: false });
  });
});

describe("#7417 shouldRestoreOnMount — the navigation type cannot answer this alone", () => {
  it("restores on a client-side transition even though the entry says 'navigate'", () => {
    // 🔴 THE CASE THE WHOLE FIX IS FOR. A Back out of a card creates no new
    // navigation entry, so `performance` still reports how the TAB was opened.
    // Gating on "back_forward" would refuse the one navigation that matters.
    expect(shouldRestoreOnMount({ clientTransition: true, navigationType: "navigate" })).toBe(true);
  });

  it("restores on a full-document back/forward traversal", () => {
    expect(shouldRestoreOnMount({ clientTransition: false, navigationType: "back_forward" })).toBe(
      true,
    );
  });

  it("refuses on a reload — the reader asked for a fresh feed", () => {
    expect(shouldRestoreOnMount({ clientTransition: false, navigationType: "reload" })).toBe(false);
  });

  it("refuses on a fresh arrival, and on an unreadable navigation type", () => {
    expect(shouldRestoreOnMount({ clientTransition: false, navigationType: "navigate" })).toBe(false);
    expect(shouldRestoreOnMount({ clientTransition: false, navigationType: null })).toBe(false);
  });
});

describe("#7417 markAndDetectClientTransition — the window is the only witness", () => {
  it("reads the first mount of a document as a document load, and the next as a transition", () => {
    const win = {} as Window;
    expect(markAndDetectClientTransition(win)).toBe(false);
    expect(markAndDetectClientTransition(win)).toBe(true);
    expect(markAndDetectClientTransition(win)).toBe(true);
  });

  it("forgets across documents, so a reload is not mistaken for a transition", () => {
    const first = {} as Window;
    markAndDetectClientTransition(first);
    // A document load hands the page a brand new `window`. That is the whole
    // signal — if this ever returned true, a reload would restore.
    expect(markAndDetectClientTransition({} as Window)).toBe(false);
  });
});

describe("#7417 the stored edition round-trips, and refuses what it cannot vouch for", () => {
  it("restores the pages, the window and the exhaustion flag", () => {
    const raw = serializeFeedSnapshot({
      page1: [item("a"), item("b")],
      rest: [item("c")],
      visibleCount: 60,
      hasMore: true,
    });
    expect(parseFeedSnapshot(raw)).toEqual({
      page1: [item("a"), item("b")],
      rest: [item("c")],
      visibleCount: 60,
      hasMore: true,
    });
  });

  it("declines to store a cold feed", () => {
    // Rung 1 only bites when there was an edition to lose. Writing an empty one
    // over a good one is how a restore destroys what it is restoring.
    expect(serializeFeedSnapshot({ page1: [], rest: [], visibleCount: 20, hasMore: true })).toBeNull();
  });

  it.each([
    ["not json", "{nope"],
    ["a non-object", "42"],
    ["a null body", "null"],
    ["an older version", JSON.stringify({ v: FEED_SNAPSHOT_VERSION - 1, page1: [item("a")], rest: [], visibleCount: 20, hasMore: true })],
    ["an empty page one", JSON.stringify({ v: FEED_SNAPSHOT_VERSION, page1: [], rest: [], visibleCount: 20, hasMore: true })],
    ["a missing tail", JSON.stringify({ v: FEED_SNAPSHOT_VERSION, page1: [item("a")], visibleCount: 20, hasMore: true })],
    ["a zero window", JSON.stringify({ v: FEED_SNAPSHOT_VERSION, page1: [item("a")], rest: [], visibleCount: 0, hasMore: true })],
    ["a fractional window", JSON.stringify({ v: FEED_SNAPSHOT_VERSION, page1: [item("a")], rest: [], visibleCount: 20.5, hasMore: true })],
    ["a non-boolean hasMore", JSON.stringify({ v: FEED_SNAPSHOT_VERSION, page1: [item("a")], rest: [], visibleCount: 20, hasMore: "yes" })],
  ])("refuses %s", (_label, raw) => {
    expect(parseFeedSnapshot(raw)).toBeNull();
  });

  it("refuses an absent snapshot", () => {
    expect(parseFeedSnapshot(null)).toBeNull();
  });
});

describe("#7417 the edition is capped, and page one is never the part sacrificed", () => {
  it("keeps every page-one card and truncates the paginated tail", () => {
    const page1 = Array.from({ length: 20 }, (_, i) => item(`p${i}`));
    const rest = Array.from({ length: 400 }, (_, i) => item(`r${i}`));
    const capped = capSnapshotItems(page1, rest);
    expect(capped.page1).toHaveLength(20);
    expect(capped.rest).toHaveLength(FEED_SNAPSHOT_MAX_ITEMS - 20);
    // Order is the reader's: the tail is truncated from the END, so what is
    // kept is the part nearest their first screen.
    expect(capped.rest[0]).toEqual(item("r0"));
  });

  it("drops the tail entirely rather than trim page one when page one fills the cap", () => {
    const page1 = Array.from({ length: FEED_SNAPSHOT_MAX_ITEMS + 30 }, (_, i) => item(`p${i}`));
    const capped = capSnapshotItems(page1, [item("r0")]);
    expect(capped.page1).toHaveLength(FEED_SNAPSHOT_MAX_ITEMS);
    expect(capped.rest).toEqual([]);
  });

  it("keeps a capped edition inside the sessionStorage budget", () => {
    // ~2.8KB per item measured against /api/feed?limit=20 (56,299 bytes / 20).
    // The point of the cap is that a restore can never be the thing that blows
    // an origin's ~5MB quota, so assert the ceiling, not the typical case.
    const bulky = Array.from({ length: 500 }, (_, i) => ({
      type: "futures",
      data: { id: `x${i}`, blob: "y".repeat(2800) },
    }));
    const raw = serializeFeedSnapshot({ page1: bulky, rest: bulky, visibleCount: 20, hasMore: true });
    expect(raw!.length).toBeLessThan(1_000_000);
  });
});

describe("#7417 the scroll mark expires, and a clock that ran backwards is not fresh", () => {
  const now = 1_700_000_000_000;

  it("round-trips a live mark", () => {
    const raw = serializeScrollMark({ scrollY: 4558, savedAt: now - 1000 });
    expect(parseScrollMark(raw, now)).toEqual({ scrollY: 4558, savedAt: now - 1000 });
  });

  it("refuses a mark older than the TTL", () => {
    const raw = serializeScrollMark({ scrollY: 4558, savedAt: now - FEED_SNAPSHOT_TTL_MS - 1 });
    expect(parseScrollMark(raw, now)).toBeNull();
  });

  it("refuses a mark written in the future", () => {
    // 🔴 BOTH SIDES OF THE AGE ARE CHECKED. "Not older than the TTL" is true of
    // every future-dated mark, however wrong — a one-sided check restores them
    // forever. Reachable via a system clock change mid-session.
    const raw = serializeScrollMark({ scrollY: 4558, savedAt: now + 60_000 });
    expect(parseScrollMark(raw, now)).toBeNull();
  });

  it("accepts a mark exactly at the TTL boundary and refuses one past it", () => {
    expect(parseScrollMark(serializeScrollMark({ scrollY: 10, savedAt: now - FEED_SNAPSHOT_TTL_MS }), now))
      .not.toBeNull();
    expect(parseScrollMark(serializeScrollMark({ scrollY: 10, savedAt: now - FEED_SNAPSHOT_TTL_MS - 1 }), now))
      .toBeNull();
  });

  it.each([
    ["a negative offset", JSON.stringify({ v: FEED_SNAPSHOT_VERSION, scrollY: -5, savedAt: now })],
    ["a non-finite offset", JSON.stringify({ v: FEED_SNAPSHOT_VERSION, scrollY: null, savedAt: now })],
    ["a missing timestamp", JSON.stringify({ v: FEED_SNAPSHOT_VERSION, scrollY: 10 })],
    ["an older version", JSON.stringify({ v: FEED_SNAPSHOT_VERSION - 1, scrollY: 10, savedAt: now })],
    ["not json", "{nope"],
  ])("refuses %s", (_label, raw) => {
    expect(parseScrollMark(raw, now)).toBeNull();
  });
});
