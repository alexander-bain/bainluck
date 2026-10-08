// #1469 — a returning reader sees last visit's first page while the fresh one
// loads. The decisions are pure (`feedWarmStart.ts`); the page wiring is pinned
// by source so a refactor cannot quietly fold warm cards into the edition or
// let them send impressions.

import fs from "fs";
import path from "path";
import {
  WARM_FEED_MAX_AGE_MS,
  WARM_FEED_VERSION,
  decodeWarmFeed,
  encodeWarmFeed,
  warmFeedIdentity,
  warmItemIsTruthful,
  type StorageLike,
} from "@/lib/discover/feedWarmStart";
import type { FeedItem } from "@/lib/types";

const NOW = Date.parse("2026-10-08T14:00:00Z");
const HOUR = 60 * 60 * 1000;

function event(id: number, status: string, commence: string): FeedItem {
  return {
    type: "event",
    score: 50,
    reason: "",
    headline: null,
    data: { id, status, commence_time: commence } as unknown as FeedItem["data"],
  };
}
function futures(id: number): FeedItem {
  return { type: "futures", score: 50, reason: "", headline: null, data: { id } as unknown as FeedItem["data"] };
}
function other(type: FeedItem["type"], id: number): FeedItem {
  return { type, score: 50, reason: "", headline: null, data: { id } as unknown as FeedItem["data"] };
}

function storage(entries: Record<string, string>): StorageLike {
  const keys = Object.keys(entries);
  return {
    get length() {
      return keys.length;
    },
    key: (i) => keys[i] ?? null,
    getItem: (k) => (k in entries ? entries[k] : null),
  };
}

describe("warmItemIsTruthful — only cards whose state cannot have moved", () => {
  it("keeps futures and finished games", () => {
    expect(warmItemIsTruthful(futures(1), NOW)).toBe(true);
    expect(warmItemIsTruthful(event(1, "completed", "2026-10-08T01:00:00Z"), NOW)).toBe(true);
    expect(warmItemIsTruthful(event(2, "closed", "2026-10-08T01:00:00Z"), NOW)).toBe(true);
  });

  it("keeps a scheduled game only while its start is still ahead", () => {
    expect(warmItemIsTruthful(event(1, "scheduled", "2026-10-08T18:00:00Z"), NOW)).toBe(true);
    expect(warmItemIsTruthful(event(2, "scheduled", "2026-10-08T13:59:00Z"), NOW)).toBe(false);
    expect(warmItemIsTruthful(event(3, "scheduled", "not a date"), NOW)).toBe(false);
  });

  it("drops a game stored live or suspended — it may be final now", () => {
    expect(warmItemIsTruthful(event(1, "live", "2026-10-08T13:00:00Z"), NOW)).toBe(false);
    expect(warmItemIsTruthful(event(2, "suspended", "2026-10-08T13:00:00Z"), NOW)).toBe(false);
  });

  it("leaves nested-state cards to the fresh page", () => {
    for (const t of ["tournament", "bundle", "concept", "collection"] as const) {
      expect(warmItemIsTruthful(other(t, 1), NOW)).toBe(false);
    }
  });
});

describe("warmFeedIdentity — whose page it is", () => {
  it("is anon with no persisted Firebase user", () => {
    expect(warmFeedIdentity(storage({ bainluck_session_id: "s1" }))).toBe("anon");
  });
  it("is the Firebase uid when one is persisted", () => {
    expect(
      warmFeedIdentity(storage({ "firebase:authUser:KEY:[DEFAULT]": JSON.stringify({ uid: "u42" }) }))
    ).toBe("fb:u42");
  });
  it("fails closed on an unreadable auth record", () => {
    expect(warmFeedIdentity(storage({ "firebase:authUser:KEY:[DEFAULT]": "{nope" }))).toBeNull();
    expect(warmFeedIdentity(storage({ "firebase:authUser:KEY:[DEFAULT]": JSON.stringify({}) }))).toBeNull();
  });
});

describe("decodeWarmFeed — refuses anything it cannot vouch for", () => {
  const items = [
    futures(1),
    event(2, "scheduled", "2026-10-08T20:00:00Z"),
    event(3, "live", "2026-10-08T13:00:00Z"),
    other("bundle", 4),
  ];
  const stored = encodeWarmFeed(items, "fb:u42", NOW - HOUR);

  it("returns the truthful cards, in served order, for the same identity", () => {
    expect(decodeWarmFeed(stored, "fb:u42", NOW).map((i) => (i.data as { id: number }).id)).toEqual([1, 2]);
  });
  it("never paints one account's page for another, or for signed-out mode", () => {
    expect(decodeWarmFeed(stored, "fb:other", NOW)).toEqual([]);
    expect(decodeWarmFeed(stored, "anon", NOW)).toEqual([]);
    expect(decodeWarmFeed(stored, null, NOW)).toEqual([]);
  });
  it("refuses an over-age, future-stamped, other-version or corrupt entry", () => {
    const old = encodeWarmFeed(items, "anon", NOW - WARM_FEED_MAX_AGE_MS - 1);
    expect(decodeWarmFeed(old, "anon", NOW)).toEqual([]);
    const ahead = encodeWarmFeed(items, "anon", NOW + 1000);
    expect(decodeWarmFeed(ahead, "anon", NOW)).toEqual([]);
    const other = JSON.stringify({ v: WARM_FEED_VERSION + 1, savedAt: NOW, identity: "anon", items });
    expect(decodeWarmFeed(other, "anon", NOW)).toEqual([]);
    expect(decodeWarmFeed("{broken", "anon", NOW)).toEqual([]);
    expect(decodeWarmFeed(null, "anon", NOW)).toEqual([]);
  });
});

describe("Discover page wiring", () => {
  const src = fs.readFileSync(path.join(__dirname, "../../app/discover/page.tsx"), "utf8");

  it("shows warm cards only while the first request is in flight, with a restored edition winning", () => {
    expect(src).toMatch(
      /const warmActive =\s*isLoading && !data && warmItems\.length > 0 && page1Items\.length === 0 && allItems\.length === 0;/
    );
    expect(src).toContain("const raw = warmActive ? warmItems : [...page1Items, ...allItems];");
    expect(src).toContain("{isLoading && !warmActive && <DiscoverSkeletonGrid />}");
  });

  it("never folds warm cards into the edition the served page reconciles against", () => {
    expect(src).not.toMatch(/setPage1Items\([^)]*warmItems/);
    expect(src).toContain("if (!warmActive) recordEditionScores(");
  });

  it("holds impressions on warm cards", () => {
    expect(src).toContain("impressionsHeld={warmActive}");
    expect(src).toContain("if (tracked.current || impressionsHeld) return;");
  });

  it("stores each accepted served page and reads it after mount", () => {
    expect(src).toContain("if (!decision.showUnavailable) writeWarmFeed(incoming);");
    expect(src).toMatch(/useEffect\(\(\) => \{\s*setWarmItems\(readWarmFeed\(\)\);\s*\}, \[\]\);/);
  });
});
