/**
 * Queue L2-204 Item 2 — `preferred_sport` GA4 user-property derivation.
 *
 * Proves the pure derivation that feeds the already-defined `preferred_sport`
 * dimension (dimension3, `lib/analytics/core.ts`) from the established affinity
 * source (`useCategoryInterests` → `sport_affinities`):
 *  - the highest positive-affinity key wins (a "preference change" changes it),
 *  - empty / all-zero / negative / non-numeric interest leaves it UNSET (no
 *    guessed default),
 *  - ties resolve deterministically so a user dimension never flickers.
 *
 * The hook wrapper (`usePreferredSportProperty`) additionally gates on consent
 * and dedupes set-per-value; those are effect/consent behaviors that require a
 * jsdom + React Testing Library setup this repo intentionally does not run
 * (`jest.config.js` → `testEnvironment: 'node'`). They are covered by the
 * consent gate already proven in `analyticsConsent.test.ts` (denied/unknown →
 * events dropped) and are documented in the queue's DebugView verification debt.
 */

import { derivePreferredSport } from "@/hooks/usePreferredSportProperty";

describe("derivePreferredSport — top positive-affinity key", () => {
  it("returns the single highest-affinity key", () => {
    expect(
      derivePreferredSport({
        basketball_nba: 1.0,
        soccer: 0.3,
        baseball_mlb: 0.1,
      }),
    ).toBe("basketball_nba");
  });

  it("reflects a preference change (new max wins)", () => {
    const before = derivePreferredSport({ soccer: 0.3, baseball_mlb: 0.1 });
    const after = derivePreferredSport({
      soccer: 0.3,
      baseball_mlb: 1.0, // user just bumped MLB to "Love it"
    });
    expect(before).toBe("soccer");
    expect(after).toBe("baseball_mlb");
  });

  it("considers a lone positive interest", () => {
    expect(derivePreferredSport({ golf: 0.1 })).toBe("golf");
  });
});

describe("derivePreferredSport — no guessed default", () => {
  it("returns undefined for an empty map", () => {
    expect(derivePreferredSport({})).toBeUndefined();
  });

  it("returns undefined when every affinity is zero", () => {
    expect(
      derivePreferredSport({ soccer: 0, baseball_mlb: 0 }),
    ).toBeUndefined();
  });

  it("ignores negative affinities (treated as no interest)", () => {
    expect(
      derivePreferredSport({ soccer: -1, baseball_mlb: -0.5 }),
    ).toBeUndefined();
  });

  it("ignores non-numeric / non-finite values", () => {
    // Cast guards against dirty stored/localStorage data reaching the deriver.
    const dirty = {
      soccer: "1.0",
      baseball_mlb: NaN,
      golf: null,
    } as unknown as Record<string, number>;
    expect(derivePreferredSport(dirty)).toBeUndefined();
  });

  it("returns undefined for null / undefined input", () => {
    expect(derivePreferredSport(null)).toBeUndefined();
    expect(derivePreferredSport(undefined)).toBeUndefined();
  });

  it("skips zero/negative entries but still picks the positive one", () => {
    expect(
      derivePreferredSport({ soccer: 0, hockey_nhl: -1, tennis: 0.3 }),
    ).toBe("tennis");
  });
});

describe("derivePreferredSport — deterministic tie-break", () => {
  it("breaks ties on the lexicographically-smallest key", () => {
    // basketball_nba < football_nfl alphabetically → stable choice
    expect(
      derivePreferredSport({ football_nfl: 1.0, basketball_nba: 1.0 }),
    ).toBe("basketball_nba");
  });

  it("is insertion-order independent (same result either way)", () => {
    const a = derivePreferredSport({ football_nfl: 1.0, basketball_nba: 1.0 });
    const b = derivePreferredSport({ basketball_nba: 1.0, football_nfl: 1.0 });
    expect(a).toBe(b);
    expect(a).toBe("basketball_nba");
  });
});
