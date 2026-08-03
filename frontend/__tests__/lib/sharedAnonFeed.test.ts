// L2-242 / C133 — the client side of anonymous cold-work sharing. jest env is
// 'node', so the decision lives as pure functions (sharedAnonFeed.ts) exercised
// directly, with a fake window.localStorage injected for the impure reads.
//
// These cases mirror the queue's required fixture matrix: fresh install,
// returning clean, interacted, dismissed/seen, private storage failure,
// concurrent tabs, late anon after interaction/login, logout, page two, and the
// authenticated principal. They map onto the backend C133 refusal semantics:
// a fresh no-session anon may reuse the warm build; fresh_session_zero_
// interactions is never cross-session; unknown authority fails closed.

import {
  decideFeedPrincipal,
  readClientPrincipalState,
  resolveSharedAnonSuppression,
  type FeedPrincipalInput,
} from "@/lib/discover/sharedAnonFeed";

const SESSION_KEY = "bainluck_session_id";
const PROFILE_KEY = "discover_interaction_profile_v1";
const DISMISSED_KEY = "discover_dismissed";
const SWIPED_KEY = "discover_has_swiped";

function makeStore(seed: Record<string, string> = {}) {
  const map = new Map(Object.entries(seed));
  return {
    getItem: (k: string) => (map.has(k) ? (map.get(k) as string) : null),
    setItem: (k: string, v: string) => void map.set(k, v),
    removeItem: (k: string) => void map.delete(k),
  };
}

function withStorage(seed: Record<string, string> | "throws" = {}) {
  const localStorage =
    seed === "throws"
      ? {
          getItem: () => {
            throw new Error("storage blocked");
          },
          setItem: () => {
            throw new Error("storage blocked");
          },
          removeItem: () => {},
        }
      : makeStore(seed);
  (globalThis as unknown as { window?: unknown }).window = { localStorage };
}

afterEach(() => {
  delete (globalThis as unknown as { window?: unknown }).window;
});

const base: FeedPrincipalInput = {
  authenticated: false,
  hasDurableSession: false,
  interactionAuthority: "known_zero",
  hasInMemoryInteraction: false,
};

describe("decideFeedPrincipal — pure decision", () => {
  it("fresh signed-out zero-interaction visitor reuses the shared warm feed", () => {
    expect(decideFeedPrincipal(base)).toEqual({
      mode: "shared_anon",
      suppressSessionId: true,
    });
  });

  it("authenticated identity always wins (never shared), even at known_zero", () => {
    expect(decideFeedPrincipal({ ...base, authenticated: true })).toEqual({
      mode: "authenticated",
      suppressSessionId: false,
    });
  });

  it("a durable session (returning visitor) stays session-scoped", () => {
    expect(decideFeedPrincipal({ ...base, hasDurableSession: true })).toEqual({
      mode: "session",
      suppressSessionId: false,
    });
  });

  it("an in-memory interaction this mount stays session-scoped", () => {
    expect(decideFeedPrincipal({ ...base, hasInMemoryInteraction: true })).toEqual({
      mode: "session",
      suppressSessionId: false,
    });
  });

  it("known_present interaction authority stays session-scoped", () => {
    expect(
      decideFeedPrincipal({ ...base, interactionAuthority: "known_present" })
    ).toEqual({ mode: "session", suppressSessionId: false });
  });

  it("unknown authority FAILS CLOSED to session-scoped (private mode / SSR)", () => {
    expect(
      decideFeedPrincipal({ ...base, interactionAuthority: "unknown" })
    ).toEqual({ mode: "session", suppressSessionId: false });
  });
});

describe("readClientPrincipalState — evidence reads", () => {
  it("SSR / no window → unknown, no durable session (fail closed)", () => {
    expect(readClientPrincipalState()).toEqual({
      hasDurableSession: false,
      interactionAuthority: "unknown",
    });
  });

  it("fresh install (empty storage) → known_zero, no session", () => {
    withStorage({});
    expect(readClientPrincipalState()).toEqual({
      hasDurableSession: false,
      interactionAuthority: "known_zero",
    });
  });

  it("returning clean visitor (session id only) → durable session, known_zero interactions", () => {
    withStorage({ [SESSION_KEY]: "sess_abc" });
    expect(readClientPrincipalState()).toEqual({
      hasDurableSession: true,
      interactionAuthority: "known_zero",
    });
  });

  it("interaction profile with categories → known_present", () => {
    withStorage({
      [PROFILE_KEY]: JSON.stringify({ categories: { mlb: { score: 3 } } }),
    });
    expect(readClientPrincipalState().interactionAuthority).toBe("known_present");
  });

  it("empty profile object (no categories) is NOT evidence → known_zero", () => {
    withStorage({ [PROFILE_KEY]: JSON.stringify({ categories: {} }) });
    expect(readClientPrincipalState().interactionAuthority).toBe("known_zero");
  });

  it("dismissed set with items → known_present", () => {
    withStorage({
      [DISMISSED_KEY]: JSON.stringify({ items: [{ id: "futures-1" }] }),
    });
    expect(readClientPrincipalState().interactionAuthority).toBe("known_present");
  });

  it("legacy dismissed array format with items → known_present", () => {
    withStorage({ [DISMISSED_KEY]: JSON.stringify(["futures-1"]) });
    expect(readClientPrincipalState().interactionAuthority).toBe("known_present");
  });

  it("empty dismissed set is NOT evidence → known_zero", () => {
    withStorage({ [DISMISSED_KEY]: JSON.stringify({ items: [] }) });
    expect(readClientPrincipalState().interactionAuthority).toBe("known_zero");
  });

  it("swipe-hint-dismissed flag → known_present", () => {
    withStorage({ [SWIPED_KEY]: "1" });
    expect(readClientPrincipalState().interactionAuthority).toBe("known_present");
  });

  it("malformed profile blob fails closed → known_present", () => {
    withStorage({ [PROFILE_KEY]: "{not json" });
    expect(readClientPrincipalState().interactionAuthority).toBe("known_present");
  });

  it("storage that throws (private mode) → unknown, no session", () => {
    withStorage("throws");
    expect(readClientPrincipalState()).toEqual({
      hasDurableSession: false,
      interactionAuthority: "unknown",
    });
  });
});

describe("resolveSharedAnonSuppression — the fetch-layer gate", () => {
  it("ineligible request (pagination / non-first) never suppresses", () => {
    withStorage({}); // fresh, but not eligible
    expect(
      resolveSharedAnonSuppression({ eligible: false, authenticated: false })
    ).toBe(false);
  });

  it("eligible fresh signed-out visitor suppresses x-session-id", () => {
    withStorage({});
    expect(
      resolveSharedAnonSuppression({ eligible: true, authenticated: false })
    ).toBe(true);
  });

  it("eligible but authenticated does NOT suppress (bearer identity wins)", () => {
    withStorage({});
    expect(
      resolveSharedAnonSuppression({ eligible: true, authenticated: true })
    ).toBe(false);
  });

  it("returning visitor with a durable session does NOT suppress", () => {
    // Concurrent tabs / a prior visit already minted a session id.
    withStorage({ [SESSION_KEY]: "sess_abc" });
    expect(
      resolveSharedAnonSuppression({ eligible: true, authenticated: false })
    ).toBe(false);
  });

  it("in-memory interaction this mount does NOT suppress on the next request", () => {
    // Late-anon-after-interaction: the reader dismissed a card before the durable
    // session propagated; the following request must be per-session.
    withStorage({});
    expect(
      resolveSharedAnonSuppression({
        eligible: true,
        authenticated: false,
        hasInMemoryInteraction: true,
      })
    ).toBe(false);
  });

  it("interacted/dismissed durable state does NOT suppress (no resurrection)", () => {
    withStorage({
      [DISMISSED_KEY]: JSON.stringify({ items: [{ id: "futures-1" }] }),
    });
    expect(
      resolveSharedAnonSuppression({ eligible: true, authenticated: false })
    ).toBe(false);
  });

  it("private-mode storage failure fails closed (no suppression)", () => {
    withStorage("throws");
    expect(
      resolveSharedAnonSuppression({ eligible: true, authenticated: false })
    ).toBe(false);
  });
});
