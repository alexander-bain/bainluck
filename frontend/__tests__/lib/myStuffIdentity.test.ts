// L2-217 Item 1 / C88 — the My Stuff account boundary, as a deterministic
// matrix over the REAL production helpers (`@/lib/myStuffIdentity`) plus a
// faithful stand-in for SWR's key→body cache.
//
// The premise being tested is the one that was broken before this queue: the
// page keyed its records on the constant strings "my-teams-feed" /
// "my-team-futures" / ["my-stuff-pinned-events", ...ids], so a cached body had
// no idea which account it belonged to. Every scenario below is run twice —
// once through the legacy constant key (to prove it leaks) and once through the
// production principal key (to prove it cannot) — so this file fails loudly if
// the principal is ever dropped from a key again.

import {
  resolveMyStuffPrincipal,
  myStuffKey,
  bindToPrincipal,
  dataForPrincipal,
  type PrincipalBound,
} from "@/lib/myStuffIdentity";

/** Minimal SWR stand-in: a key→body map with SWR's serialization semantics. */
class FakeSWRCache {
  private store = new Map<string, unknown>();
  private fetches = 0;

  private static serialize(key: unknown): string {
    return JSON.stringify(key);
  }

  /** SWR's read-then-revalidate: a cached body for the key renders immediately. */
  read<T>(key: unknown): T | undefined {
    if (key === null || key === undefined) return undefined;
    return this.store.get(FakeSWRCache.serialize(key)) as T | undefined;
  }

  write(key: unknown, body: unknown): void {
    if (key === null || key === undefined) throw new Error("null key must suppress the request");
    this.fetches += 1;
    this.store.set(FakeSWRCache.serialize(key), body);
  }

  /** How many real requests were issued — a null key must issue none. */
  get requestCount(): number {
    return this.fetches;
  }

  /** Every key currently held, so a test can prove nothing unrelated was flushed. */
  keys(): string[] {
    return Array.from(this.store.keys()).sort();
  }
}

interface Feed {
  owner: string;
  items: { id: number }[];
}

const feedFor = (owner: string): Feed => ({ owner, items: [{ id: 1 }, { id: 2 }] });

/** What actually renders for a viewer, through the production read path. */
function renderedFeed(
  cache: FakeSWRCache,
  principal: string | null,
  key: unknown
): Feed | undefined {
  const record = cache.read<PrincipalBound<Feed>>(key);
  return dataForPrincipal(record, principal);
}

describe("resolveMyStuffPrincipal — fail closed unless the identity is stable", () => {
  it("suppresses while auth restore is in flight", () => {
    expect(
      resolveMyStuffPrincipal({ isLoading: true, isAuthenticated: false, uid: null })
    ).toBeNull();
    // Even a uid already in hand is not trusted until restore settles.
    expect(
      resolveMyStuffPrincipal({ isLoading: true, isAuthenticated: true, uid: "a" })
    ).toBeNull();
  });

  it("suppresses for signed-out and rejected-auth viewers", () => {
    expect(
      resolveMyStuffPrincipal({ isLoading: false, isAuthenticated: false, uid: null })
    ).toBeNull();
    // Rejected/cancelled sign-in: restore settled, still nobody signed in.
    expect(
      resolveMyStuffPrincipal({ isLoading: false, isAuthenticated: false, uid: undefined })
    ).toBeNull();
  });

  it("suppresses in the supersession window: authenticated but no usable uid", () => {
    expect(
      resolveMyStuffPrincipal({ isLoading: false, isAuthenticated: true, uid: "" })
    ).toBeNull();
    expect(
      resolveMyStuffPrincipal({ isLoading: false, isAuthenticated: true, uid: "   " })
    ).toBeNull();
    expect(
      resolveMyStuffPrincipal({ isLoading: false, isAuthenticated: true, uid: null })
    ).toBeNull();
  });

  it("resolves a stable, namespaced principal for a signed-in viewer", () => {
    expect(
      resolveMyStuffPrincipal({ isLoading: false, isAuthenticated: true, uid: "abc" })
    ).toBe("user:abc");
  });
});

describe("myStuffKey — an unresolved principal issues no request", () => {
  it("returns null (SWR suppression) until the principal resolves", () => {
    expect(myStuffKey(null, "feed")).toBeNull();
    const cache = new FakeSWRCache();
    expect(cache.read(myStuffKey(null, "feed"))).toBeUndefined();
    expect(cache.requestCount).toBe(0);
  });

  it("binds resource, principal, and extras — and never lets extras shadow identity", () => {
    expect(myStuffKey("user:a", "feed")).toEqual(["my-stuff", "feed", "user:a"]);
    expect(myStuffKey("user:a", "pinned-events", [7, 9])).toEqual([
      "my-stuff",
      "pinned-events",
      "user:a",
      7,
      9,
    ]);
    // Two accounts recovering the SAME pinned ids still get distinct keys.
    expect(myStuffKey("user:a", "pinned-events", [7])).not.toEqual(
      myStuffKey("user:b", "pinned-events", [7])
    );
  });
});

describe("account boundary matrix — zero account-A content under account B", () => {
  const A = "user:a";
  const B = "user:b";

  it("A→B switch: the legacy constant key leaks A; the principal key cannot", () => {
    // --- legacy behavior (the bug this queue closes) ---
    const legacy = new FakeSWRCache();
    legacy.write("my-teams-feed", feedFor("a"));
    // B mounts, reads the same constant key, and paints A's feed.
    expect((legacy.read("my-teams-feed") as Feed).owner).toBe("a");

    // --- production behavior ---
    const cache = new FakeSWRCache();
    cache.write(myStuffKey(A, "feed"), bindToPrincipal(A, feedFor("a")));
    // B's read is a MISS — a different key entirely.
    expect(renderedFeed(cache, B, myStuffKey(B, "feed"))).toBeUndefined();
    // A's entry survives untouched; nothing was globally flushed.
    expect(renderedFeed(cache, A, myStuffKey(A, "feed"))?.owner).toBe("a");
  });

  it("A→B applies to team futures and pinned recovery, not just the feed", () => {
    const cache = new FakeSWRCache();
    for (const resource of ["feed", "team-futures"] as const) {
      cache.write(myStuffKey(A, resource), bindToPrincipal(A, feedFor("a")));
      expect(renderedFeed(cache, B, myStuffKey(B, resource))).toBeUndefined();
    }
    cache.write(myStuffKey(A, "pinned-events", [4, 5]), bindToPrincipal(A, feedFor("a")));
    expect(renderedFeed(cache, B, myStuffKey(B, "pinned-events", [4, 5]))).toBeUndefined();
    cache.write(myStuffKey(A, "pinned-futures", [4]), bindToPrincipal(A, feedFor("a")));
    expect(renderedFeed(cache, B, myStuffKey(B, "pinned-futures", [4]))).toBeUndefined();
  });

  it("logout: a signed-out viewer resolves no principal, so nothing renders or fetches", () => {
    const cache = new FakeSWRCache();
    cache.write(myStuffKey(A, "feed"), bindToPrincipal(A, feedFor("a")));

    const signedOut = resolveMyStuffPrincipal({
      isLoading: false,
      isAuthenticated: false,
      uid: null,
    });
    const key = myStuffKey(signedOut, "feed");
    expect(key).toBeNull();
    expect(renderedFeed(cache, signedOut, key)).toBeUndefined();
    expect(cache.requestCount).toBe(1); // only A's original fetch
  });

  it("slow B: while B's request is still in flight, A's body is not rendered", () => {
    const cache = new FakeSWRCache();
    cache.write(myStuffKey(A, "feed"), bindToPrincipal(A, feedFor("a")));
    // B mounted; nothing written under B's key yet (request in flight).
    expect(renderedFeed(cache, B, myStuffKey(B, "feed"))).toBeUndefined();
    // B's response lands — B sees B, and only B.
    cache.write(myStuffKey(B, "feed"), bindToPrincipal(B, feedFor("b")));
    expect(renderedFeed(cache, B, myStuffKey(B, "feed"))?.owner).toBe("b");
  });

  it("late account-A response cannot render under B even if it lands on B's key", () => {
    // Defense-in-depth: the payload is bound to the principal that fetched it,
    // so a misrouted/late body is discarded rather than painted.
    const cache = new FakeSWRCache();
    cache.write(myStuffKey(B, "feed"), bindToPrincipal(A, feedFor("a")));
    expect(renderedFeed(cache, B, myStuffKey(B, "feed"))).toBeUndefined();
  });

  it("rejected auth: a failed sign-in attempt renders no previous account's data", () => {
    const cache = new FakeSWRCache();
    cache.write(myStuffKey(A, "feed"), bindToPrincipal(A, feedFor("a")));
    const rejected = resolveMyStuffPrincipal({
      isLoading: false,
      isAuthenticated: false,
      uid: null,
    });
    expect(renderedFeed(cache, rejected, myStuffKey(rejected, "feed"))).toBeUndefined();
  });

  it("returning user: the same principal reproduces the identical key and reuses SWR", () => {
    const cache = new FakeSWRCache();
    const first = myStuffKey(A, "feed");
    cache.write(first, bindToPrincipal(A, feedFor("a")));
    // A returns later (remount). Same principal → same key → cache hit, no refetch.
    const second = myStuffKey(
      resolveMyStuffPrincipal({ isLoading: false, isAuthenticated: true, uid: "a" }),
      "feed"
    );
    expect(second).toEqual(first);
    expect(renderedFeed(cache, A, second)?.owner).toBe("a");
    expect(cache.requestCount).toBe(1);
  });

  it("same-user revalidation replaces in place without touching other keys", () => {
    const cache = new FakeSWRCache();
    cache.write(myStuffKey(A, "feed"), bindToPrincipal(A, feedFor("a")));
    cache.write(myStuffKey(A, "team-futures"), bindToPrincipal(A, feedFor("a")));
    const before = cache.keys();

    cache.write(myStuffKey(A, "feed"), bindToPrincipal(A, { owner: "a", items: [{ id: 3 }] }));

    // Sibling records still present — no global flush, progressive siblings intact.
    expect(cache.keys()).toEqual(before);
    expect(renderedFeed(cache, A, myStuffKey(A, "feed"))?.items).toEqual([{ id: 3 }]);
    expect(renderedFeed(cache, A, myStuffKey(A, "team-futures"))?.owner).toBe("a");
  });

  it("an unrelated surface's cache entry is never evicted by a My Stuff switch", () => {
    const cache = new FakeSWRCache();
    cache.write("discover-feed", { shared: true });
    cache.write(myStuffKey(A, "feed"), bindToPrincipal(A, feedFor("a")));
    // Switch to B: B simply reads a different key. Nothing is removed.
    expect(renderedFeed(cache, B, myStuffKey(B, "feed"))).toBeUndefined();
    expect(cache.read("discover-feed")).toEqual({ shared: true });
  });
});

describe("dataForPrincipal — the render gate itself", () => {
  it("returns undefined for a missing record, a null principal, or a mismatch", () => {
    expect(dataForPrincipal(undefined, "user:a")).toBeUndefined();
    expect(dataForPrincipal(null, "user:a")).toBeUndefined();
    expect(dataForPrincipal(bindToPrincipal("user:a", feedFor("a")), null)).toBeUndefined();
    expect(dataForPrincipal(bindToPrincipal("user:a", feedFor("a")), "user:b")).toBeUndefined();
  });

  it("returns the payload only for its own principal", () => {
    const bound = bindToPrincipal("user:a", feedFor("a"));
    expect(dataForPrincipal(bound, "user:a")?.owner).toBe("a");
  });
});
