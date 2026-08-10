// Queue 309 Items 1-3 — the first-run orientation cohort and the game gate.
//
// Every assertion runs in BOTH directions (gotcha #43): a first-run anonymous
// reader gets the orientation UI and no games, and a returning or signed-in
// reader gets today's Discover exactly. The one-directional version of this
// test is what let a diversity cap empty the Sports tab while "fixing" a golf
// flood — a guard that only proves the new behaviour happens cannot notice that
// it happened to everyone.

import {
  areGamesUnlocked,
  isFirstRunAnonymous,
  markFirstRunEngaged,
  markGamesUnlocked,
  readFirstRunStorage,
  GAMES_UNLOCK_CARDS_SEEN,
  GAMES_UNLOCKED_STORAGE_KEY,
  ORIENTATION_STORAGE_KEY,
  SWIPE_HINT_STORAGE_KEY,
  DISCOVER_PROFILE_STORAGE_KEY,
  type FirstRunStorage,
} from "@/lib/discoverFirstRun";

const FRESH: FirstRunStorage = {
  oriented: false,
  swiped: false,
  gamesUnlocked: false,
  hasInteractionProfile: false,
};

function installStorage(entries: Record<string, string>, opts?: { throwOnRead?: boolean }) {
  const store = new Map(Object.entries(entries));
  (global as { window?: unknown }).window = {
    localStorage: {
      getItem: (k: string) => {
        if (opts?.throwOnRead) throw new Error("SecurityError: storage blocked");
        return store.get(k) ?? null;
      },
      setItem: (k: string, v: string) => {
        if (opts?.throwOnRead) throw new Error("SecurityError: storage blocked");
        store.set(k, v);
      },
    },
  };
  return store;
}

describe("isFirstRunAnonymous", () => {
  const realWindow = (global as { window?: unknown }).window;
  afterEach(() => {
    (global as { window?: unknown }).window = realWindow;
    if (realWindow === undefined) delete (global as { window?: unknown }).window;
  });

  it("is TRUE for a signed-out reader with no durable history", () => {
    expect(
      isFirstRunAnonymous({ authenticated: false, storage: FRESH, engagedThisSession: false }),
    ).toBe(true);
  });

  it("is FALSE for a signed-in reader — returning users see zero change", () => {
    expect(
      isFirstRunAnonymous({ authenticated: true, storage: FRESH, engagedThisSession: false }),
    ).toBe(false);
  });

  it.each([
    ["already oriented", { ...FRESH, oriented: true }],
    ["has swiped before", { ...FRESH, swiped: true }],
    ["has an interaction profile", { ...FRESH, hasInteractionProfile: true }],
  ])("is FALSE when the reader %s", (_label, storage) => {
    expect(
      isFirstRunAnonymous({ authenticated: false, storage, engagedThisSession: false }),
    ).toBe(false);
  });

  it("is FALSE before storage resolves, so no first-run UI can reach SSR markup", () => {
    expect(
      isFirstRunAnonymous({ authenticated: false, storage: null, engagedThisSession: false }),
    ).toBe(false);
  });

  it("is FALSE the moment the reader engages this session", () => {
    expect(
      isFirstRunAnonymous({ authenticated: false, storage: FRESH, engagedThisSession: true }),
    ).toBe(false);
  });

  it("ignores the games-unlocked flag — scrolling is not engagement", () => {
    expect(
      isFirstRunAnonymous({
        authenticated: false,
        storage: { ...FRESH, gamesUnlocked: true },
        engagedThisSession: false,
      }),
    ).toBe(true);
  });
});

describe("the orientation line cannot expire on a timer (the P3 trap)", () => {
  // The swipe hint this cohort copies its PERSISTENCE from also auto-dismisses
  // after 5s. An orientation line that vanishes while the reader is still
  // reading it is worse than not shipping one, so the decision is structurally
  // time-free: no argument carries elapsed time, and no amount of waiting can
  // be expressed as an input. This test states that as a property.
  it("returns the same answer no matter how many times time 'passes'", () => {
    const input = { authenticated: false, storage: FRESH, engagedThisSession: false };
    for (let tick = 0; tick < 1000; tick++) {
      expect(isFirstRunAnonymous(input)).toBe(true);
    }
  });

  it("takes no time-shaped parameter at all", () => {
    // One object argument; the function is arity-1 and its input type has no
    // clock, timestamp, or elapsed field. A future edit that adds one has to
    // break this test on the way past.
    expect(isFirstRunAnonymous.length).toBe(1);
    expect(Object.keys(FRESH)).toEqual([
      "oriented",
      "swiped",
      "gamesUnlocked",
      "hasInteractionProfile",
    ]);
  });
});

describe("areGamesUnlocked", () => {
  it("is TRUE immediately for anyone who is not a first-run reader", () => {
    expect(
      areGamesUnlocked({ firstRun: false, storage: FRESH, cardsSeen: 0, engagedThisSession: false }),
    ).toBe(true);
  });

  it("is FALSE for a first-run reader who has met nothing yet", () => {
    expect(
      areGamesUnlocked({ firstRun: true, storage: FRESH, cardsSeen: 0, engagedThisSession: false }),
    ).toBe(false);
  });

  it(`stays FALSE right up to ${GAMES_UNLOCK_CARDS_SEEN} cards, then unlocks`, () => {
    const base = { firstRun: true, storage: FRESH, engagedThisSession: false };
    expect(areGamesUnlocked({ ...base, cardsSeen: GAMES_UNLOCK_CARDS_SEEN - 1 })).toBe(false);
    expect(areGamesUnlocked({ ...base, cardsSeen: GAMES_UNLOCK_CARDS_SEEN })).toBe(true);
    expect(areGamesUnlocked({ ...base, cardsSeen: GAMES_UNLOCK_CARDS_SEEN + 40 })).toBe(true);
  });

  it("unlocks on a tap (engagement) long before the card threshold", () => {
    expect(
      areGamesUnlocked({ firstRun: true, storage: FRESH, cardsSeen: 1, engagedThisSession: true }),
    ).toBe(true);
  });

  it("does not re-lock on remount once the unlock is persisted", () => {
    expect(
      areGamesUnlocked({
        firstRun: true,
        storage: { ...FRESH, gamesUnlocked: true },
        cardsSeen: 0,
        engagedThisSession: false,
      }),
    ).toBe(true);
  });
});

describe("readFirstRunStorage", () => {
  const realWindow = (global as { window?: unknown }).window;
  afterEach(() => {
    (global as { window?: unknown }).window = realWindow;
    if (realWindow === undefined) delete (global as { window?: unknown }).window;
  });

  it("reads every durable signal off its real key", () => {
    installStorage({
      [ORIENTATION_STORAGE_KEY]: "1",
      [SWIPE_HINT_STORAGE_KEY]: "1",
      [GAMES_UNLOCKED_STORAGE_KEY]: "1",
      [DISCOVER_PROFILE_STORAGE_KEY]: JSON.stringify({ categories: {} }),
    });
    expect(readFirstRunStorage()).toEqual({
      oriented: true,
      swiped: true,
      gamesUnlocked: true,
      hasInteractionProfile: true,
    });
  });

  it("reads a genuinely fresh browser as first-run", () => {
    installStorage({});
    expect(readFirstRunStorage()).toEqual(FRESH);
  });

  it("fails CLOSED when storage is blocked — no first-run UI on every visit forever", () => {
    installStorage({}, { throwOnRead: true });
    const storage = readFirstRunStorage();
    expect(storage.oriented).toBe(true);
    expect(
      isFirstRunAnonymous({ authenticated: false, storage, engagedThisSession: false }),
    ).toBe(false);
  });

  it("treats server-side rendering as not-first-run", () => {
    delete (global as { window?: unknown }).window;
    expect(readFirstRunStorage()).toEqual({
      oriented: true,
      swiped: true,
      gamesUnlocked: true,
      hasInteractionProfile: true,
    });
  });
});

describe("persistence", () => {
  const realWindow = (global as { window?: unknown }).window;
  afterEach(() => {
    (global as { window?: unknown }).window = realWindow;
    if (realWindow === undefined) delete (global as { window?: unknown }).window;
  });

  it("engagement spends the orientation UI AND unlocks games, permanently", () => {
    const store = installStorage({});
    markFirstRunEngaged();
    expect(store.get(ORIENTATION_STORAGE_KEY)).toBe("1");
    expect(store.get(GAMES_UNLOCKED_STORAGE_KEY)).toBe("1");
    // Next visit: the reader is no longer first-run.
    expect(
      isFirstRunAnonymous({
        authenticated: false,
        storage: readFirstRunStorage(),
        engagedThisSession: false,
      }),
    ).toBe(false);
  });

  it("seeing enough cards unlocks games but leaves the orientation line intact", () => {
    const store = installStorage({});
    markGamesUnlocked();
    expect(store.get(GAMES_UNLOCKED_STORAGE_KEY)).toBe("1");
    expect(store.has(ORIENTATION_STORAGE_KEY)).toBe(false);
    expect(
      isFirstRunAnonymous({
        authenticated: false,
        storage: readFirstRunStorage(),
        engagedThisSession: false,
      }),
    ).toBe(true);
  });

  it("a blocked write never throws into the feed", () => {
    installStorage({}, { throwOnRead: true });
    expect(() => markFirstRunEngaged()).not.toThrow();
    expect(() => markGamesUnlocked()).not.toThrow();
  });
});
