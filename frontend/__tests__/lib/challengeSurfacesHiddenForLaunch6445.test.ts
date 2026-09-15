// #6445 — Today's Challenge, the resolved-predictions banner and the standalone
// Daily Challenge page are hidden for the initial release.
//
// ALEX, 2026-09-15, from the phone build: hide Today's Challenge altogether
// until it is good, including Discover's resolved-predictions banner and My
// Stuff's Predictions summary. What he met was a promotion with nothing behind
// it — "Play" led to "No challenge cards right now".
//
// WEB SCOPE, MEASURED, NOT ASSUMED. Of the three surfaces Alex named on the
// phone, web carries two: the Discover tracker (with the inline quiz slots it
// counts) and the resolved banner. Web `/my-stuff` is "My Teams" — followed
// teams, pinned events, futures, awards — and holds no predictions summary at
// all; that one is native's, and `ios/**` is native's file set (notice 41).
//
// ── WHY THE FIRST DESCRIBE IS THE TEST AND NOT A TAUTOLOGY ──────────────────
//
// `areGamesUnlocked` had two unconditional `true` shortcuts before any cohort
// arithmetic: a returning reader, and an engaged session. Gating only the
// first-run arm would have hidden the games from first-time anonymous readers
// and from nobody else — which is to say, from almost nobody, since the flag's
// whole population is people who have been here before. So the arms below walk
// the WHOLE input space rather than one specimen: every combination of the four
// booleans, at card counts either side of the unlock threshold. The regression
// this catches is a gate re-inserted below one of those shortcuts.
//
// ── AND WHY THE SECOND DESCRIBE MATTERS MORE THAN IT LOOKS ──────────────────
//
// Alex said "until good", and the issue says restore under a later product
// decision. That promise is only real if the feature is intact behind the flag.
// Re-requiring the module with the flag forced ON proves two things at once:
// the cohort logic still works, and this constant is the ONLY thing hiding it.
// A hide implemented by deleting the arms would pass every other test here.

import {
  GAMES_UNLOCK_CARDS_SEEN,
  GAMES_UNLOCKED_STORAGE_KEY,
  ORIENTATION_STORAGE_KEY,
  areGamesUnlocked,
  type FirstRunStorage,
} from "@/lib/discoverFirstRun";
import { CHALLENGE_SURFACES_ENABLED } from "@/lib/launchSurfaces";

function storage(over: Partial<FirstRunStorage> = {}): FirstRunStorage {
  return {
    oriented: false,
    swiped: false,
    gamesUnlocked: false,
    hasInteractionProfile: false,
    ...over,
  };
}

const BOOLS = [false, true];

describe("#6445 — no reader unlocks the challenge surfaces", () => {
  it("is off for the initial release", () => {
    expect(CHALLENGE_SURFACES_ENABLED).toBe(false);
  });

  it("refuses every combination of reader state, on both sides of the card threshold", () => {
    const cardCounts = [0, GAMES_UNLOCK_CARDS_SEEN - 1, GAMES_UNLOCK_CARDS_SEEN, 99];
    let combinations = 0;

    for (const firstRun of BOOLS) {
      for (const hasScrolled of BOOLS) {
        for (const engagedThisSession of BOOLS) {
          for (const storedUnlock of BOOLS) {
            for (const cardsSeen of cardCounts) {
              combinations += 1;
              expect(
                areGamesUnlocked({
                  firstRun,
                  storage: storage({ gamesUnlocked: storedUnlock }),
                  cardsSeen,
                  hasScrolled,
                  engagedThisSession,
                }),
              ).toBe(false);
            }
          }
        }
      }
    }

    // The loop must actually have run — a mistyped array would pass vacuously.
    expect(combinations).toBe(BOOLS.length ** 4 * cardCounts.length);
  });

  it("refuses the null-storage case, which used to fall through to `true`", () => {
    // `storage: null` means "not yet resolved"; with `firstRun` false it took
    // the returning-reader shortcut on the very first paint, before any effect
    // had read localStorage. That is the paint Alex would see.
    expect(
      areGamesUnlocked({
        firstRun: false,
        storage: null,
        cardsSeen: 0,
        hasScrolled: false,
        engagedThisSession: false,
      }),
    ).toBe(false);
  });

  it("names the three readers who most obviously used to see games", () => {
    const signedInReturning = {
      firstRun: false,
      storage: storage({ oriented: true, swiped: true }),
      cardsSeen: 40,
      hasScrolled: true,
      engagedThisSession: false,
    };
    const engagedNow = {
      firstRun: true,
      storage: storage(),
      cardsSeen: 0,
      hasScrolled: false,
      engagedThisSession: true,
    };
    const earnedItEarlier = {
      firstRun: true,
      storage: storage({ gamesUnlocked: true }),
      cardsSeen: 0,
      hasScrolled: false,
      engagedThisSession: false,
    };

    expect(areGamesUnlocked(signedInReturning)).toBe(false);
    expect(areGamesUnlocked(engagedNow)).toBe(false);
    expect(areGamesUnlocked(earnedItEarlier)).toBe(false);
  });
});

describe("#6445 — hidden, not deleted: one flip restores the whole feature", () => {
  function unlockedWithFlagOn(input: Parameters<typeof areGamesUnlocked>[0]): boolean {
    let result: boolean | undefined;
    jest.isolateModules(() => {
      jest.doMock("@/lib/launchSurfaces", () => ({ CHALLENGE_SURFACES_ENABLED: true }));
      // eslint-disable-next-line @typescript-eslint/no-var-requires
      const mod = require("@/lib/discoverFirstRun") as typeof import("@/lib/discoverFirstRun");
      result = mod.areGamesUnlocked(input);
    });
    jest.dontMock("@/lib/launchSurfaces");
    return result as boolean;
  }

  it("still unlocks a returning reader when the flag is on", () => {
    expect(
      unlockedWithFlagOn({
        firstRun: false,
        storage: storage({ oriented: true }),
        cardsSeen: 0,
        hasScrolled: false,
        engagedThisSession: false,
      }),
    ).toBe(true);
  });

  it("still holds a first-run reader back until they have met cards AND scrolled", () => {
    const base = { firstRun: true, storage: storage(), engagedThisSession: false };

    // Both halves of the Queue 309 gate survive the flag: the card count alone
    // does not unlock (the desktop-masonry trap), and scrolling alone does not.
    expect(
      unlockedWithFlagOn({ ...base, cardsSeen: GAMES_UNLOCK_CARDS_SEEN, hasScrolled: false }),
    ).toBe(false);
    expect(unlockedWithFlagOn({ ...base, cardsSeen: 0, hasScrolled: true })).toBe(false);
    expect(
      unlockedWithFlagOn({ ...base, cardsSeen: GAMES_UNLOCK_CARDS_SEEN, hasScrolled: true }),
    ).toBe(true);
  });

  it("leaves the durable storage keys exactly as they were", () => {
    // Nothing here deletes a reader's history. The keys a restored feature
    // would read are the keys it wrote before this ship.
    expect(GAMES_UNLOCKED_STORAGE_KEY).toBe("discover_games_unlocked");
    expect(ORIENTATION_STORAGE_KEY).toBe("discover_oriented");
  });
});

describe("#6445 — `/daily` stops being the way search promotes a hidden game", () => {
  it("asks not to be indexed, and still states its own identity", () => {
    // eslint-disable-next-line @typescript-eslint/no-var-requires
    const { metadata } = require("@/app/daily/layout") as { metadata: Record<string, unknown> };

    expect(metadata.robots).toEqual({ index: false, follow: false });
    // #4193's fix must survive the addition: without the canonical the route
    // tells crawlers it is a duplicate of the home page, which is a different
    // and worse claim than "do not index me".
    expect(metadata.alternates).toEqual({ canonical: "/daily" });
  });
});

describe("#6445 — the Discover page's three render sites are gated", () => {
  // A SOURCE SCAN, DELIBERATELY, and on the same reasoning
  // `guessNeverAsksAFinishedGame5763.test.ts` set out for this exact file:
  // `app/discover/page.tsx` is a client page whose surfaces depend on SWR data,
  // an auth context, localStorage cohorts and an IntersectionObserver, so a
  // rendered arm would prove the composition of all of those rather than the
  // rule. The behaviour is proved above, on the predicate. What this adds is
  // that the page actually ASKS the predicate at each of the three places a
  // reader could otherwise meet the feature.
  const source = require("fs").readFileSync(
    require("path").join(__dirname, "..", "..", "app", "discover", "page.tsx"),
    "utf8",
  ) as string;

  it("gates the resolved-predictions banner on the launch flag", () => {
    const line = source
      .split("\n")
      .find((l) => l.includes("resolutionsData && resolutionsData.resolutions.length > 0"));
    expect(line).toBeDefined();
    expect(line).toContain("CHALLENGE_SURFACES_ENABLED &&");
  });

  it("stops fetching the resolutions it will not show", () => {
    const block = source.slice(
      source.indexOf("const { data: resolutionsData }"),
      source.indexOf("const hasMoreRef"),
    );
    expect(block).toContain('CHALLENGE_SURFACES_ENABLED ? "discover-resolutions" : null');
  });

  it("gates the Today's Challenge tracker on the unlock predicate", () => {
    const line = source.split("\n").find((l) => l.includes("<DailyChallengeCard"));
    expect(line).toBeDefined();
    const block = source.slice(
      source.indexOf("{!isLoading && gamesUnlocked && processedItems.length > 0 && ("),
      source.indexOf("<DailyChallengeCard"),
    );
    expect(block).not.toBe("");
  });

  it("gates the inline quiz slot on the same predicate", () => {
    const line = source.split("\n").find((l) => l.includes("const isGuessSlot"));
    expect(line).toBeDefined();
    expect(line).toContain("gamesUnlocked &&");
  });
});
