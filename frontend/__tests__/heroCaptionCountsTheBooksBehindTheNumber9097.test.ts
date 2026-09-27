/**
 * #9097 (consumer half of #9081) — a scheduled event's hero caption counts the
 * sportsbooks standing behind the hero NUMBER, not every served book row.
 *
 * Specimen: /events/14870012 (Clemson v Miami, Oct 3, scheduled), read on
 * production 2026-09-27 11:50Z. `current_odds.bookmaker_count` is 4 — betmgm,
 * draftkings, fanduel and a mybookieag quote 53 days old — while the producer
 * (live/650, `hero_sportsbook_count`) serves 3: the books the blend admitted.
 * On 9/26 the same page served a Kalshi-only 13% captioned "4 sportsbooks"
 * because ruling 051 had dropped the 2-book consensus; the server now says 0.
 */

import { resolveProbability } from "@/lib/eventKeyStats";

function specimen(overrides: Record<string, unknown> = {}) {
  return {
    status: "scheduled",
    hero_probability: 0.12,
    hero_probability_away: 0.88,
    hero_probability_source: "blend",
    hero_sportsbook_count: 3,
    current_odds: {
      captured_at: "2026-09-27T07:35:17.626933+00:00",
      home_probability: 0.12,
      away_probability: 0.88,
      home_rendered_percent: 12,
      away_rendered_percent: 88,
      bookmaker_count: 4,
    },
    ...overrides,
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
  } as any;
}

const scheduled = (event: ReturnType<typeof specimen>) =>
  resolveProbability(event, undefined, null, false, false);

describe("#9097 scheduled hero caption", () => {
  it("counts the 3 books behind the blend, not the 4 served rows", () => {
    const r = scheduled(specimen());
    expect(r.homeProb).toBeCloseTo(0.12, 6);
    expect(r.probSourceLabel).toBe("3 sportsbooks");
  });

  it("claims no sportsbook when none stands behind the number (9/26 Kalshi-only 13%)", () => {
    const r = scheduled(specimen({ hero_probability: 0.13, hero_sportsbook_count: 0 }));
    // No caption at all: nothing about sportsbooks is true of this number.
    expect(r.probSourceLabel).toBeNull();
  });

  it("singular when one book stands behind it", () => {
    expect(scheduled(specimen({ hero_sportsbook_count: 1 })).probSourceLabel).toBe("1 sportsbook");
  });

  it("CONTROL: an absent or null count keeps the older row count", () => {
    const { hero_sportsbook_count: _drop, ...absent } = specimen();
    void _drop;
    expect(scheduled(absent).probSourceLabel).toBe("4 sportsbooks");
    expect(scheduled(specimen({ hero_sportsbook_count: null })).probSourceLabel).toBe(
      "4 sportsbooks",
    );
  });

  it("CONTROL: a count beside a non-blend hero is not trusted", () => {
    const r = scheduled(specimen({ hero_probability_source: "opening", hero_sportsbook_count: 0 }));
    expect(r.probSourceLabel).toBe("4 sportsbooks");
  });
});
