/**
 * Pinned events/futures storage.
 *
 * Rewritten in UX-P017 (#1496). The previous version of this file defined its
 * own `loadPinnedIds`/`savePinnedIds` and then asserted on inline array
 * operations (`ids.push(4)` → `[1,2,3,4]`), so it never imported a single line
 * of production code and would have passed unchanged if the pin hooks had been
 * deleted outright. It was green throughout the entire life of the P1
 * cross-account write it nominally covered.
 *
 * It now exercises the real modules, and carries the dimension the old file was
 * missing: pins belong to an OWNER, not to a device.
 */

import { parseIds, serializeIds, mergeForMigration } from "@/lib/pinnedIds";
import {
  bucketKeyFor,
  legacyKey,
  type BucketPolicy,
  type KeyValueStore,
} from "@/lib/principalStorage";
import { resolveScope } from "@/lib/clientPrincipal";

const EVENTS_POLICY: BucketPolicy = { base: "bainluck_pinnedEvents" };
const FUTURES_POLICY: BucketPolicy = { base: "bainluck_pinnedFutures" };
const MAX_PINNED = 6;

const SCOPE_A = resolveScope({ isLoading: false, isAuthenticated: true, uid: "acct-a" });
const SCOPE_B = resolveScope({ isLoading: false, isAuthenticated: true, uid: "acct-b" });
const SCOPE_ANON = resolveScope({ isLoading: false, isAuthenticated: false, uid: null });
const SCOPE_PENDING = resolveScope({ isLoading: true, isAuthenticated: false, uid: null });

class FakeStore implements KeyValueStore {
  private map = new Map<string, string>();
  getItem(key: string) {
    return this.map.has(key) ? (this.map.get(key) as string) : null;
  }
  setItem(key: string, value: string) {
    this.map.set(key, value);
  }
  removeItem(key: string) {
    this.map.delete(key);
  }
}

/** Store ids into the bucket the given scope owns. */
function savePins(policy: BucketPolicy, scope: ReturnType<typeof resolveScope>, store: FakeStore, ids: number[]) {
  const key = bucketKeyFor(policy, scope);
  if (!key) throw new Error("no bucket for an unresolved scope — the hook must not write");
  store.setItem(key, serializeIds(ids));
}

/** Read ids from the bucket the given scope owns. */
function loadPins(policy: BucketPolicy, scope: ReturnType<typeof resolveScope>, store: FakeStore): number[] {
  const key = bucketKeyFor(policy, scope);
  if (!key) return [];
  return parseIds(store.getItem(key));
}

describe("parsing stored pins", () => {
  it("returns empty when nothing is stored", () => {
    expect(parseIds(null)).toEqual([]);
  });

  it("loads a valid array", () => {
    expect(parseIds(JSON.stringify([1, 2, 3]))).toEqual([1, 2, 3]);
  });

  it("returns empty for invalid JSON", () => {
    expect(parseIds("not valid json")).toEqual([]);
  });

  it("returns empty for non-array JSON", () => {
    expect(parseIds(JSON.stringify({ id: 1 }))).toEqual([]);
  });

  it("returns empty for an array with non-numbers", () => {
    expect(parseIds(JSON.stringify([1, "two", 3]))).toEqual([]);
  });

  it("returns empty for a null value", () => {
    expect(parseIds("null")).toEqual([]);
  });

  it("handles an empty array", () => {
    expect(parseIds(JSON.stringify([]))).toEqual([]);
  });
});

describe("round-trip through an owner's bucket", () => {
  it("save then load preserves data", () => {
    const store = new FakeStore();
    savePins(EVENTS_POLICY, SCOPE_A, store, [10, 20, 30]);
    expect(loadPins(EVENTS_POLICY, SCOPE_A, store)).toEqual([10, 20, 30]);
  });

  it("events and futures stay independent", () => {
    const store = new FakeStore();
    savePins(EVENTS_POLICY, SCOPE_A, store, [1, 2, 3]);
    savePins(FUTURES_POLICY, SCOPE_A, store, [10, 20]);

    expect(loadPins(EVENTS_POLICY, SCOPE_A, store)).toEqual([1, 2, 3]);
    expect(loadPins(FUTURES_POLICY, SCOPE_A, store)).toEqual([10, 20]);
  });

  it("clearing stores an empty array", () => {
    const store = new FakeStore();
    savePins(EVENTS_POLICY, SCOPE_A, store, [1, 2, 3]);
    savePins(EVENTS_POLICY, SCOPE_A, store, []);
    expect(loadPins(EVENTS_POLICY, SCOPE_A, store)).toEqual([]);
  });

  it("an anonymous visitor keeps their own pins across loads", () => {
    const store = new FakeStore();
    savePins(EVENTS_POLICY, SCOPE_ANON, store, [4, 5]);
    expect(loadPins(EVENTS_POLICY, SCOPE_ANON, store)).toEqual([4, 5]);
  });
});

describe("pins belong to an owner, not to a device (#1496)", () => {
  it("account B does not read account A's pins", () => {
    const store = new FakeStore();
    savePins(EVENTS_POLICY, SCOPE_A, store, [1, 2, 3]);

    expect(loadPins(EVENTS_POLICY, SCOPE_B, store)).toEqual([]);
    expect(loadPins(EVENTS_POLICY, SCOPE_A, store)).toEqual([1, 2, 3]);
  });

  it("an account does not read the anonymous bucket as its own", () => {
    const store = new FakeStore();
    savePins(EVENTS_POLICY, SCOPE_ANON, store, [7, 8]);
    expect(loadPins(EVENTS_POLICY, SCOPE_A, store)).toEqual([]);
  });

  it("nothing is readable or writable while identity is unresolved", () => {
    const store = new FakeStore();
    expect(bucketKeyFor(EVENTS_POLICY, SCOPE_PENDING)).toBeNull();
    expect(loadPins(EVENTS_POLICY, SCOPE_PENDING, store)).toEqual([]);
    expect(() => savePins(EVENTS_POLICY, SCOPE_PENDING, store, [1])).toThrow();
  });

  it("no owner writes to the pre-partition device-global key", () => {
    const store = new FakeStore();
    savePins(EVENTS_POLICY, SCOPE_A, store, [1]);
    savePins(EVENTS_POLICY, SCOPE_B, store, [2]);
    savePins(EVENTS_POLICY, SCOPE_ANON, store, [3]);

    expect(store.getItem(legacyKey(EVENTS_POLICY))).toBeNull();
  });
});

describe("pin / unpin / toggle, against the merge cap", () => {
  it("respects the max when adopting migrated pins", () => {
    const { merged, toPush } = mergeForMigration([1, 2, 3, 4, 5], [6, 7], MAX_PINNED);
    expect(merged).toHaveLength(MAX_PINNED);
    expect(toPush).toEqual([6]);
  });

  it("ignores a duplicate", () => {
    const { merged, toPush } = mergeForMigration([1, 2, 3], [2], MAX_PINNED);
    expect(merged).toEqual([1, 2, 3]);
    expect(toPush).toEqual([]);
  });

  it("adopts nothing when the account is already at the max", () => {
    const { merged, toPush } = mergeForMigration([1, 2, 3, 4, 5, 6], [7], MAX_PINNED);
    expect(merged).toEqual([1, 2, 3, 4, 5, 6]);
    expect(toPush).toEqual([]);
  });
});
