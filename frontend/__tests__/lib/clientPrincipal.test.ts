// UX-P017 / #1496 — the general client account boundary.
//
// The rule under test is the one every defect in #1496 broke: authenticated
// client state is bound to WHICH ACCOUNT, never to an `isAuthenticated`
// boolean. Each scenario below is run twice where it matters — once through a
// boolean-derived key (to prove it leaks) and once through the production
// principal key (to prove it cannot) — so this file fails loudly if the
// principal is ever dropped from a key again.

import {
  resolvePrincipal,
  resolveScope,
  sameScope,
  principalKey,
  bindToPrincipal,
  dataForPrincipal,
  type ClientScope,
  type PrincipalBound,
} from "@/lib/clientPrincipal";
import { myStuffKey } from "@/lib/myStuffIdentity";

const A = { isLoading: false, isAuthenticated: true, uid: "acct-a" };
const B = { isLoading: false, isAuthenticated: true, uid: "acct-b" };
const SIGNED_OUT = { isLoading: false, isAuthenticated: false, uid: null };
const RESTORING = { isLoading: true, isAuthenticated: false, uid: null };

describe("resolvePrincipal — fail closed unless the identity is stable", () => {
  it("is null while auth is still restoring, even if a uid is already present", () => {
    expect(resolvePrincipal(RESTORING)).toBeNull();
    expect(resolvePrincipal({ isLoading: true, isAuthenticated: true, uid: "acct-a" })).toBeNull();
  });

  it("is null when signed out", () => {
    expect(resolvePrincipal(SIGNED_OUT)).toBeNull();
    expect(resolvePrincipal({ isLoading: false, isAuthenticated: false })).toBeNull();
  });

  it("is null in the supersession window — authenticated but no usable uid", () => {
    expect(resolvePrincipal({ isLoading: false, isAuthenticated: true, uid: "" })).toBeNull();
    expect(resolvePrincipal({ isLoading: false, isAuthenticated: true, uid: "   " })).toBeNull();
    expect(resolvePrincipal({ isLoading: false, isAuthenticated: true, uid: null })).toBeNull();
  });

  it("resolves distinct, namespaced principals for distinct accounts", () => {
    expect(resolvePrincipal(A)).toBe("user:acct-a");
    expect(resolvePrincipal(B)).toBe("user:acct-b");
    expect(resolvePrincipal(A)).not.toBe(resolvePrincipal(B));
  });

  it("is stable across re-renders for the same account (no cache-busting)", () => {
    expect(resolvePrincipal(A)).toBe(resolvePrincipal({ ...A }));
  });
});

describe("resolveScope — three states, because anonymous state is real state", () => {
  it("distinguishes 'we do not know yet' from 'nobody is signed in'", () => {
    // Collapsing these two was what let a pin hook write into a bucket before
    // it knew whose bucket it was.
    expect(resolveScope(RESTORING)).toEqual({ kind: "pending" });
    expect(resolveScope(SIGNED_OUT)).toEqual({ kind: "anonymous" });
  });

  it("gives an account its own scope", () => {
    expect(resolveScope(A)).toEqual({ kind: "principal", principal: "user:acct-a" });
  });

  it("refuses the anonymous bucket to an authenticated user with no usable uid", () => {
    // Falling back to `anonymous` here would hand one account the device
    // bucket — the exact provenance confusion the migration rule forbids.
    expect(resolveScope({ isLoading: false, isAuthenticated: true, uid: "" })).toEqual({
      kind: "pending",
    });
  });

  it("sameScope tracks owner identity, not object identity", () => {
    expect(sameScope(resolveScope(A), resolveScope({ ...A }))).toBe(true);
    expect(sameScope(resolveScope(A), resolveScope(B))).toBe(false);
    expect(sameScope(resolveScope(SIGNED_OUT), resolveScope(A))).toBe(false);
    expect(sameScope(resolveScope(RESTORING), resolveScope(SIGNED_OUT))).toBe(false);
  });
});

describe("principalKey — a null key suppresses, a resolved key partitions", () => {
  it("suppresses the request entirely when the principal is unresolved", () => {
    expect(principalKey("prefs", null, "user-preferences")).toBeNull();
    expect(principalKey("prefs", resolvePrincipal(RESTORING), "user-preferences")).toBeNull();
  });

  it("puts the principal in the key so two accounts cannot collide", () => {
    const keyA = principalKey("prefs", resolvePrincipal(A), "user-preferences");
    const keyB = principalKey("prefs", resolvePrincipal(B), "user-preferences");
    expect(keyA).not.toEqual(keyB);
  });

  it("appends extra params AFTER the principal so they can never shadow it", () => {
    expect(principalKey("prefs", "user:acct-a", "pinned-events", [7, 9])).toEqual([
      "prefs",
      "pinned-events",
      "user:acct-a",
      7,
      9,
    ]);
  });

  it("is byte-identical for the same principal across re-mounts", () => {
    expect(principalKey("prefs", "user:acct-a", "pinned-events", [7])).toEqual(
      principalKey("prefs", "user:acct-a", "pinned-events", [7])
    );
  });

  it("keeps myStuffKey's shape frozen — it is a LIVE cache key", () => {
    // Changing this array would not be a refactor: it would be a cache miss for
    // every signed-in user, silently re-running L2-217's fix as a regression.
    expect(myStuffKey("user:acct-a", "feed")).toEqual(["my-stuff", "feed", "user:acct-a"]);
    expect(myStuffKey("user:acct-a", "pinned-events", [3, 4])).toEqual([
      "my-stuff",
      "pinned-events",
      "user:acct-a",
      3,
      4,
    ]);
    expect(myStuffKey(null, "feed")).toBeNull();
  });
});

describe("the account-switch matrix, through a faithful SWR stand-in", () => {
  /** Minimal SWR model: a key→body map with SWR's serialization semantics. */
  class FakeSWRCache {
    private store = new Map<string, unknown>();
    private fetches = 0;

    read<T>(key: unknown): T | undefined {
      if (key === null || key === undefined) return undefined;
      return this.store.get(JSON.stringify(key)) as T | undefined;
    }

    write(key: unknown, body: unknown): void {
      if (key === null || key === undefined) {
        throw new Error("a null key must suppress the request, not issue one");
      }
      this.fetches += 1;
      this.store.set(JSON.stringify(key), body);
    }

    get requestCount(): number {
      return this.fetches;
    }
  }

  interface Prefs {
    owner: string;
    teams: string[];
  }
  const prefsFor = (owner: string): Prefs => ({ owner, teams: [`${owner}-team`] });

  /** The legacy key this queue removed: constant, principal-blind. */
  const legacyKey = (isAuthenticated: boolean) => (isAuthenticated ? "user-preferences" : null);

  const rendered = (cache: FakeSWRCache, principal: string | null, key: unknown) =>
    dataForPrincipal(cache.read<PrincipalBound<Prefs>>(key), principal);

  it("A→B: the legacy constant key LEAKS, the principal key cannot", () => {
    // Legacy: B reads the body A cached, because the key never changed.
    const legacy = new FakeSWRCache();
    legacy.write(legacyKey(true), prefsFor("acct-a"));
    expect(legacy.read<Prefs>(legacyKey(true))).toEqual(prefsFor("acct-a"));

    // Production: B's key is different, so there is nothing of A's to read.
    const cache = new FakeSWRCache();
    const pA = resolvePrincipal(A);
    const pB = resolvePrincipal(B);
    cache.write(principalKey("prefs", pA, "user-preferences"), bindToPrincipal(pA!, prefsFor("acct-a")));

    expect(rendered(cache, pB, principalKey("prefs", pB, "user-preferences"))).toBeUndefined();
    expect(rendered(cache, pA, principalKey("prefs", pA, "user-preferences"))).toEqual(
      prefsFor("acct-a")
    );
  });

  it("late-A-response: a fetch dispatched as A cannot paint after the switch to B", () => {
    const cache = new FakeSWRCache();
    const pA = resolvePrincipal(A);
    const pB = resolvePrincipal(B);

    // A's in-flight request resolves AFTER the viewer became B.
    cache.write(principalKey("prefs", pA, "user-preferences"), bindToPrincipal(pA!, prefsFor("acct-a")));

    // Even reading A's own key as B renders nothing — the binding is the second,
    // independent guard behind the key.
    expect(rendered(cache, pB, principalKey("prefs", pA, "user-preferences"))).toBeUndefined();
  });

  it("logout→B: signing out then in as B never reuses A's body", () => {
    const cache = new FakeSWRCache();
    const pA = resolvePrincipal(A);
    cache.write(principalKey("prefs", pA, "user-preferences"), bindToPrincipal(pA!, prefsFor("acct-a")));

    const signedOut = resolvePrincipal(SIGNED_OUT);
    expect(principalKey("prefs", signedOut, "user-preferences")).toBeNull();
    expect(rendered(cache, signedOut, principalKey("prefs", signedOut, "user-preferences"))).toBeUndefined();

    const pB = resolvePrincipal(B);
    expect(rendered(cache, pB, principalKey("prefs", pB, "user-preferences"))).toBeUndefined();
  });

  it("slow B / restoring auth: issues no personalized request at all", () => {
    const cache = new FakeSWRCache();
    const restoring = resolvePrincipal(RESTORING);
    expect(principalKey("prefs", restoring, "user-preferences")).toBeNull();
    expect(cache.requestCount).toBe(0);
  });

  it("rejected auth lands on the signed-out branch, not on a guessed principal", () => {
    const rejected = { isLoading: false, isAuthenticated: false, uid: null };
    expect(principalKey("prefs", resolvePrincipal(rejected), "user-preferences")).toBeNull();
  });

  it("same-user remount REUSES the cached body — no cache-busting regression", () => {
    const cache = new FakeSWRCache();
    const pA = resolvePrincipal(A);
    cache.write(principalKey("prefs", pA, "user-preferences"), bindToPrincipal(pA!, prefsFor("acct-a")));

    const afterRemount = resolvePrincipal({ ...A });
    expect(
      rendered(cache, afterRemount, principalKey("prefs", afterRemount, "user-preferences"))
    ).toEqual(prefsFor("acct-a"));
    // One write, and the remount served from cache rather than refetching.
    expect(cache.requestCount).toBe(1);
  });

  it("dataForPrincipal renders nothing rather than guessing, in every ambiguous case", () => {
    const bound = bindToPrincipal("user:acct-a", prefsFor("acct-a"));
    expect(dataForPrincipal(bound, "user:acct-b")).toBeUndefined();
    expect(dataForPrincipal(bound, null)).toBeUndefined();
    expect(dataForPrincipal(undefined, "user:acct-a")).toBeUndefined();
    expect(dataForPrincipal(null, "user:acct-a")).toBeUndefined();
    expect(dataForPrincipal(bound, "user:acct-a")).toEqual(prefsFor("acct-a"));
  });
});

describe("both directions — the fix must not blank a legitimate signed-in surface", () => {
  // Gotcha #43: a suppression rule ships a guard in BOTH directions. It is not
  // enough that B sees nothing of A's; A must still see A's.
  it("a settled, signed-in viewer gets a real key and its own data", () => {
    const scope: ClientScope = resolveScope(A);
    expect(scope.kind).toBe("principal");

    const p = resolvePrincipal(A);
    const key = principalKey("prefs", p, "user-preferences");
    expect(key).not.toBeNull();
    expect(dataForPrincipal(bindToPrincipal(p!, { owner: "acct-a", teams: [] }), p)).toEqual({
      owner: "acct-a",
      teams: [],
    });
  });
});
