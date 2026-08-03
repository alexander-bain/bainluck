// L2-240 Item 1 — the Sports feed SWR key contract, as pure logic.
//
// These fixtures pin the behavior that removes the auth-before-fetch blocker:
// the key never gates on `authLoading` (it is not even an input), the anonymous
// request starts immediately, and anon vs signed-in reads stay under distinct
// keys so a late identity can never let a stale response overwrite a newer one.

import {
  sportsFeedKey,
  groupedFeedKey,
  sportsFeedIdentity,
  SPORTS_FEED_ANON_KEY,
} from "@/lib/sports/feedKey";

describe("sportsFeedKey — anonymous request starts before auth resolves", () => {
  it("never returns null (the fetch must not wait on Firebase)", () => {
    // While auth is still loading there is no user id yet — the key must be the
    // anonymous key, NOT null, so SWR issues the request immediately.
    expect(sportsFeedKey(null)).not.toBeNull();
    expect(sportsFeedKey(undefined)).not.toBeNull();
    expect(sportsFeedKey(null)).toEqual(SPORTS_FEED_ANON_KEY);
  });

  it("a signed-out visitor stays on the anon key with no wasteful re-key", () => {
    // Loading (null) and resolved-signed-out (null) yield the SAME key, so auth
    // resolving to "no user" does not trigger a second request.
    expect(sportsFeedKey(null)).toEqual(sportsFeedKey(null));
    expect(sportsFeedKey(undefined)).toEqual(SPORTS_FEED_ANON_KEY);
  });

  it("a late identity re-keys onto a distinct personalized key", () => {
    const anon = sportsFeedKey(null);
    const signedIn = sportsFeedKey("uid-123");
    expect(signedIn).toEqual(["feed-sports", "uid-123"]);
    // Distinct keys → SWR caches and races per key: a slow anonymous response
    // lands under the anon key, never overwriting the personalized generation.
    expect(signedIn).not.toEqual(anon);
  });

  it("different identities never share a cache key", () => {
    expect(sportsFeedKey("uid-A")).not.toEqual(sportsFeedKey("uid-B"));
  });

  it("the anon key is referentially stable so SWR issues exactly one request", () => {
    // SWR compares keys structurally, but a stable reference makes the single
    // in-flight request guarantee obvious across renders that keep the same id.
    expect(sportsFeedKey(null)).toBe(SPORTS_FEED_ANON_KEY);
    expect(sportsFeedKey(undefined)).toBe(SPORTS_FEED_ANON_KEY);
  });
});

describe("groupedFeedKey — same decoupling for player props/progressions", () => {
  it("never null and distinct per identity", () => {
    expect(groupedFeedKey(null)).toEqual(["grouped-feed-anon"]);
    expect(groupedFeedKey("uid-123")).toEqual(["grouped-feed", "uid-123"]);
    expect(groupedFeedKey("uid-123")).not.toEqual(groupedFeedKey(null));
  });
});

describe("sportsFeedIdentity — paginated tail reset trigger", () => {
  it("collapses no-user states to a single 'anon' token", () => {
    expect(sportsFeedIdentity(null)).toBe("anon");
    expect(sportsFeedIdentity(undefined)).toBe("anon");
  });

  it("changes on every genuine identity transition", () => {
    // anon → user, user → other user, and user → logout must each be observable
    // as a token change so the page drops the previous identity's tail pages.
    expect(sportsFeedIdentity("uid-A")).not.toBe(sportsFeedIdentity(null));
    expect(sportsFeedIdentity("uid-A")).not.toBe(sportsFeedIdentity("uid-B"));
    expect(sportsFeedIdentity(null)).not.toBe(sportsFeedIdentity("uid-A"));
  });
});
