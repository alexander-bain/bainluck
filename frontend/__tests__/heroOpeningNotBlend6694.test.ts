/**
 * #6694 — what the backend relabel actually does to the reader.
 *
 * The backend half of this fix (live/419, `resolve_hero` + `compute_aggregate_
 * probability_tiered`) stops serving an opening-only hero as
 * `hero_probability_source: "blend"` and serves `"opening"` instead. The NUMBER
 * on the wire does not move; only the claim about it does.
 *
 * This file is the proof that the relabel is not inert. `resolveProbability`
 * already carries the guard it needs —
 *
 *     // Gate on the source: `hero_probability` degrades to the OPENING line
 *     // when no blend exists, and an opening line is not a live blend —
 *     // labelling it "Bain Luck blend" would be a lie
 *
 * — written against a `hero_probability_source` that, until this fix, could
 * never be anything but `"blend"` on an event with an opening. The guard was
 * therefore unfalsifiable. These tests drive the REAL builder on BOTH payloads,
 * so the before column is what production served and the after column is what
 * the backend change makes it serve.
 *
 * Specimen: event 15314578 (Uganda–Kenya, live) read at 2026-09-19 12:06:44Z.
 * Hero 0.6414 captioned "Live · Bain Luck blend"; the chart's own last point
 * 0.7534, from the single sportsbook (`betting_book_count: 1`) whose consensus
 * ruling 051 refuses to publish as a blend.
 *
 * NOTE ON OWNERSHIP (notice 41): this is a new test file and reads
 * `lib/eventKeyStats.ts` without modifying it. No layout file is touched.
 */

import { resolveProbability } from "@/lib/eventKeyStats";

const OPENING = 0.6414;
const SINGLE_BOOK = 0.7534;

function specimen(source: "blend" | "opening") {
  return {
    hero_probability: OPENING,
    hero_probability_away: 1 - OPENING,
    hero_probability_source: source,
    current_odds: {
      home_probability: OPENING,
      away_probability: 1 - OPENING,
      bookmaker_count: 1,
      captured_at: "2026-09-19T12:06:44",
      source: "aggregate",
    },
    opening_odds: {
      home_probability: OPENING,
      away_probability: 1 - OPENING,
    },
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
  } as any;
}

/** The chart's own series: one sportsbook, currently 0.7534. */
const HISTORY = {
  history: [
    { timestamp: "2026-09-19T11:40:00", home_probability: 0.71, bookmaker_count: 1 },
    { timestamp: "2026-09-19T12:06:44", home_probability: SINGLE_BOOK, bookmaker_count: 1 },
  ],
  // No blend line exists — a single source produces no aggregate.
  aggregate_line: null,
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
} as any;

describe("#6694 opening-only hero", () => {
  it("BEFORE: an opening served as `blend` is captioned as a live Bain Luck blend", () => {
    const before = resolveProbability(specimen("blend"), HISTORY, null, true, false);

    expect(before.homeProb).toBeCloseTo(OPENING, 6);
    expect(before.probSourceLabel).toBe("Live · Bain Luck blend");
  });

  it("AFTER: the same payload labelled `opening` is no longer called a blend", () => {
    const after = resolveProbability(specimen("opening"), HISTORY, null, true, false);

    expect(after.probSourceLabel).not.toBe("Live · Bain Luck blend");
    expect(after.probSourceLabel).not.toMatch(/blend/i);
  });

  it("AFTER: the hero stops contradicting the chart drawn beneath it", () => {
    const after = resolveProbability(specimen("opening"), HISTORY, null, true, false);

    // The reader's complaint on #6694 was two numbers for one question on one
    // screen. The fall-through cross-checks `current_odds` against the chart's
    // own last point and adopts it when they differ by more than 5 points.
    expect(after.homeProb).toBeCloseTo(SINGLE_BOOK, 6);
  });

  it("AFTER: the single book is attributed as one sportsbook, never as our blend", () => {
    const after = resolveProbability(specimen("opening"), HISTORY, null, true, false);

    // Ruling 051 forbids publishing a one-book consensus AS THE BLEND. Printing
    // it under its own name, with the count visible, is a different claim and is
    // the behaviour this surface already shipped for the no-blend case.
    expect(after.probSourceLabel).toBe("Live · 1 sportsbook");
  });

  it("a REAL blend is untouched by the relabel", () => {
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const real = specimen("blend") as any;
    real.hero_probability = 0.74;
    real.hero_probability_away = 0.26;

    const out = resolveProbability(real, HISTORY, null, true, false);

    expect(out.homeProb).toBeCloseTo(0.74, 6);
    expect(out.probSourceLabel).toBe("Live · Bain Luck blend");
  });
});
