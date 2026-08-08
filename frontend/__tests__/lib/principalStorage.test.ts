// UX-P017 / #1496 — principal-partitioned buckets and the anonymous-migration
// policy.
//
// The write half of #1496 is the damaging half: account B did not merely SEE
// account A's pins, it merged them into B's server account. Every test here
// exists to make that specific sentence false, and to keep the anonymous
// experience working while it does.

import {
  legacyKey,
  anonymousKey,
  principalBucketKey,
  migrationDoneKey,
  bucketKeyFor,
  reconcileLegacyBucket,
  pendingAnonymousMigration,
  completeAnonymousMigration,
  type BucketPolicy,
  type KeyValueStore,
} from "@/lib/principalStorage";
import { resolveScope } from "@/lib/clientPrincipal";

const POLICY: BucketPolicy = { base: "bainluck_pinnedEvents" };
const INTERESTS: BucketPolicy = {
  base: "bainluck_categoryInterests",
  legacyDoneKey: "bainluck_interestsSyncedToServer",
};

class FakeStore implements KeyValueStore {
  private map = new Map<string, string>();
  constructor(seed: Record<string, string> = {}) {
    for (const [k, v] of Object.entries(seed)) this.map.set(k, v);
  }
  getItem(key: string) {
    return this.map.has(key) ? (this.map.get(key) as string) : null;
  }
  setItem(key: string, value: string) {
    this.map.set(key, value);
  }
  removeItem(key: string) {
    this.map.delete(key);
  }
  snapshot(): Record<string, string> {
    return Object.fromEntries(this.map);
  }
}

const SCOPE_A = resolveScope({ isLoading: false, isAuthenticated: true, uid: "acct-a" });
const SCOPE_B = resolveScope({ isLoading: false, isAuthenticated: true, uid: "acct-b" });
const SCOPE_ANON = resolveScope({ isLoading: false, isAuthenticated: false, uid: null });
const SCOPE_PENDING = resolveScope({ isLoading: true, isAuthenticated: false, uid: null });

describe("bucketKeyFor — one bucket per owner", () => {
  it("touches nothing while identity is unresolved", () => {
    expect(bucketKeyFor(POLICY, SCOPE_PENDING)).toBeNull();
  });

  it("gives the anonymous visitor a bucket of their own, distinct from the legacy key", () => {
    const key = bucketKeyFor(POLICY, SCOPE_ANON);
    expect(key).toBe(anonymousKey(POLICY));
    expect(key).not.toBe(legacyKey(POLICY));
  });

  it("gives each account a distinct bucket", () => {
    expect(bucketKeyFor(POLICY, SCOPE_A)).toBe("bainluck_pinnedEvents:user:acct-a");
    expect(bucketKeyFor(POLICY, SCOPE_A)).not.toBe(bucketKeyFor(POLICY, SCOPE_B));
  });

  it("never returns the pre-partition device-global key to anyone", () => {
    for (const scope of [SCOPE_PENDING, SCOPE_ANON, SCOPE_A, SCOPE_B]) {
      expect(bucketKeyFor(POLICY, scope)).not.toBe(legacyKey(POLICY));
    }
  });
});

describe("reconcileLegacyBucket — the legacy bucket is adopted only where provenance is provable", () => {
  it("under an ANONYMOUS scope, adopts it: the visitor keeps their own pins", () => {
    // Both-direction guard (gotcha #43). Deleting it unconditionally would be
    // "safe" and would also silently wipe every anonymous visitor's pins.
    const store = new FakeStore({ [legacyKey(POLICY)]: "[1,2,3]" });
    reconcileLegacyBucket(POLICY, SCOPE_ANON, store);

    expect(store.getItem(anonymousKey(POLICY))).toBe("[1,2,3]");
    expect(store.getItem(legacyKey(POLICY))).toBeNull();
  });

  it("under a SIGNED-IN scope, DELETES it unread — this is the line that closes the leak", () => {
    const store = new FakeStore({ [legacyKey(POLICY)]: "[1,2,3]" });
    reconcileLegacyBucket(POLICY, SCOPE_B, store);

    expect(store.getItem(legacyKey(POLICY))).toBeNull();
    // Never copied anywhere B could later use as migration input.
    expect(store.getItem(anonymousKey(POLICY))).toBeNull();
    expect(store.getItem(principalBucketKey(POLICY, "user:acct-b"))).toBeNull();
  });

  it("decides nothing while identity is unresolved", () => {
    const store = new FakeStore({ [legacyKey(POLICY)]: "[1,2,3]" });
    reconcileLegacyBucket(POLICY, SCOPE_PENDING, store);
    expect(store.getItem(legacyKey(POLICY))).toBe("[1,2,3]");
  });

  it("never overwrites a real anonymous bucket with legacy leftovers", () => {
    const store = new FakeStore({
      [legacyKey(POLICY)]: "[1,2,3]",
      [anonymousKey(POLICY)]: "[9]",
    });
    reconcileLegacyBucket(POLICY, SCOPE_ANON, store);

    expect(store.getItem(anonymousKey(POLICY))).toBe("[9]");
    expect(store.getItem(legacyKey(POLICY))).toBeNull();
  });

  it("is a no-op when there is no legacy bucket (the steady state)", () => {
    const store = new FakeStore({ [anonymousKey(POLICY)]: "[5]" });
    reconcileLegacyBucket(POLICY, SCOPE_ANON, store);
    expect(store.snapshot()).toEqual({ [anonymousKey(POLICY)]: "[5]" });
  });
});

describe("pendingAnonymousMigration — anonymous-sourced, at most once", () => {
  it("offers the anonymous bucket for migration", () => {
    const store = new FakeStore({ [anonymousKey(POLICY)]: "[1,2]" });
    expect(pendingAnonymousMigration(POLICY, store)).toBe("[1,2]");
  });

  it("NEVER offers another account's bucket — the whole point of #1496", () => {
    const store = new FakeStore({
      [principalBucketKey(POLICY, "user:acct-a")]: "[1,2,3]",
    });
    // B signs in on A's device. There is nothing to migrate.
    expect(pendingAnonymousMigration(POLICY, store)).toBeNull();
  });

  it("offers nothing once the device has already migrated", () => {
    const store = new FakeStore({
      [anonymousKey(POLICY)]: "[1,2]",
      [migrationDoneKey(POLICY)]: "1",
    });
    expect(pendingAnonymousMigration(POLICY, store)).toBeNull();
  });

  it("honours a PRE-EXISTING legacy done flag, so devices do not re-migrate", () => {
    const store = new FakeStore({
      [anonymousKey(INTERESTS)]: '{"nba":1}',
      "bainluck_interestsSyncedToServer": "true",
    });
    expect(pendingAnonymousMigration(INTERESTS, store)).toBeNull();
  });

  it("treats an absent or empty bucket as nothing to do", () => {
    expect(pendingAnonymousMigration(POLICY, new FakeStore())).toBeNull();
    expect(pendingAnonymousMigration(POLICY, new FakeStore({ [anonymousKey(POLICY)]: "" }))).toBeNull();
  });
});

describe("completeAnonymousMigration — flag AND clear", () => {
  it("marks the device done and empties the bucket", () => {
    const store = new FakeStore({ [anonymousKey(POLICY)]: "[1,2]" });
    completeAnonymousMigration(POLICY, store);

    expect(store.getItem(migrationDoneKey(POLICY))).toBe("1");
    expect(store.getItem(anonymousKey(POLICY))).toBeNull();
  });

  it("an emptied bucket cannot leak to a second account even if the flag were lost", () => {
    const store = new FakeStore({ [anonymousKey(POLICY)]: "[1,2]" });
    completeAnonymousMigration(POLICY, store);
    store.removeItem(migrationDoneKey(POLICY)); // simulate the flag going missing

    expect(pendingAnonymousMigration(POLICY, store)).toBeNull();
  });
});

describe("end-to-end: the exact sequence #1496 reported", () => {
  it("A signs in, signs out, B signs in — B adopts NOTHING of A's", () => {
    const store = new FakeStore();

    // 1. Anonymous visitor pins three things.
    reconcileLegacyBucket(POLICY, SCOPE_ANON, store);
    store.setItem(bucketKeyFor(POLICY, SCOPE_ANON)!, "[1,2,3]");

    // 2. A signs in and consumes the device's anonymous pins.
    reconcileLegacyBucket(POLICY, SCOPE_A, store);
    expect(pendingAnonymousMigration(POLICY, store)).toBe("[1,2,3]");
    completeAnonymousMigration(POLICY, store);
    store.setItem(bucketKeyFor(POLICY, SCOPE_A)!, "[1,2,3,4]");

    // 3. A signs out; B signs in on the same device.
    reconcileLegacyBucket(POLICY, SCOPE_B, store);

    // B is offered nothing to migrate, and B's own bucket is empty.
    expect(pendingAnonymousMigration(POLICY, store)).toBeNull();
    expect(store.getItem(bucketKeyFor(POLICY, SCOPE_B)!)).toBeNull();

    // A's bucket is untouched and still A's — B cannot address it.
    expect(store.getItem(principalBucketKey(POLICY, "user:acct-a"))).toBe("[1,2,3,4]");
    expect(bucketKeyFor(POLICY, SCOPE_B)).not.toBe(principalBucketKey(POLICY, "user:acct-a"));
  });

  it("upgrade path: B signs in first on a device holding A's legacy pins", () => {
    // The ambiguous upgrade case. The legacy bucket may be A's; nothing says so.
    const store = new FakeStore({ [legacyKey(POLICY)]: "[1,2,3]" });

    reconcileLegacyBucket(POLICY, SCOPE_B, store);

    expect(pendingAnonymousMigration(POLICY, store)).toBeNull();
    expect(store.getItem(legacyKey(POLICY))).toBeNull();
    expect(store.snapshot()).toEqual({});
  });

  it("the anonymous path still works end to end (both-direction guard)", () => {
    const store = new FakeStore({ [legacyKey(POLICY)]: "[7,8]" });

    // Anonymous visit after the upgrade: pins survive.
    reconcileLegacyBucket(POLICY, SCOPE_ANON, store);
    expect(store.getItem(bucketKeyFor(POLICY, SCOPE_ANON)!)).toBe("[7,8]");

    // They then sign in as A and the pins follow them into the account, once.
    reconcileLegacyBucket(POLICY, SCOPE_A, store);
    expect(pendingAnonymousMigration(POLICY, store)).toBe("[7,8]");
    completeAnonymousMigration(POLICY, store);
    expect(pendingAnonymousMigration(POLICY, store)).toBeNull();
  });
});
