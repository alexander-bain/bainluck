/**
 * #9470 — a scheduled event whose hero the server labels `opening` is captioned
 * as the opening line, not as a current sportsbook price.
 *
 * Specimen: /events/14780556 (Packers v Bears, Oct 11), served on production
 * 2026-09-28 ~23:00Z: `hero_probability` 0.5996 / 0.4004, source `opening`,
 * `current_odds` the same pair with `bookmaker_count` 2, captured 2026-09-13
 * 15:10Z — both books pulled the line at Week 1's kickoff and nothing has quoted
 * it since. The page read "60% – 40% · 2 sportsbooks".
 */

import { resolveProbability } from "@/lib/eventKeyStats";

function specimen(overrides: Record<string, unknown> = {}) {
  return {
    status: "scheduled",
    hero_probability: 0.5996,
    hero_probability_away: 0.4004,
    hero_probability_source: "opening",
    hero_sportsbook_count: null,
    current_odds: {
      captured_at: "2026-09-13T15:10:39.053494+00:00",
      home_probability: 0.5996,
      away_probability: 0.4004,
      bookmaker_count: 2,
      source: null,
    },
    opening_odds: { home_probability: null, away_probability: null },
    win_probability_sources: { betting_book_count: 1 },
    ...overrides,
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
  } as any;
}

const scheduled = (event: ReturnType<typeof specimen>) =>
  resolveProbability(event, undefined, null, false, false);

describe("#9470 opening hero caption", () => {
  it("the specimen reads 60–40 captioned as the opening line, not '2 sportsbooks'", () => {
    const r = scheduled(specimen());
    expect(r.probSourceLabel).toBe("Opening line");
    expect(r.homePct).toBe(60);
    expect(r.awayPct).toBe(40);
  });

  it("the number is the hero's, so a still-quoting 2-book row cannot sit under the caption", () => {
    // Ruling 051 drops a consensus under 3, so a game whose two books ARE
    // quoting is also served `opening`. The caption must describe what prints.
    const r = scheduled(
      specimen({
        current_odds: {
          captured_at: "2026-09-28T21:00:00+00:00",
          home_probability: 0.7,
          away_probability: 0.3,
          home_rendered_percent: 70,
          away_rendered_percent: 30,
          bookmaker_count: 2,
        },
      }),
    );
    expect(r.probSourceLabel).toBe("Opening line");
    expect(r.homeProb).toBeCloseTo(0.5996, 6);
    expect(r.homePct).toBe(60);
    expect(r.awayPct).toBe(40);
  });

  it("an absent away side is the complement", () => {
    const { hero_probability_away: _drop, ...noAway } = specimen();
    void _drop;
    const r = scheduled(noAway);
    expect(r.awayProb).toBeCloseTo(0.4004, 6);
    expect(r.homePct! + r.awayPct!).toBe(100);
  });

  it("CONTROL: a blend hero keeps its sportsbook caption", () => {
    const r = scheduled(specimen({ hero_probability_source: "blend", hero_sportsbook_count: 2 }));
    expect(r.probSourceLabel).toBe("2 sportsbooks");
  });

  it("CONTROL: `opening` with no served number falls through to the old path", () => {
    const r = scheduled(specimen({ hero_probability: null }));
    expect(r.probSourceLabel).toBe("2 sportsbooks");
  });

  it("CONTROL: a live `opening` event is not this branch", () => {
    const r = resolveProbability(specimen({ status: "live" }), undefined, null, true, false);
    expect(r.probSourceLabel).not.toBe("Opening line");
  });
});
