/**
 * L2-219 Item 1 (#1453) — non-overlapping engagement accounting (C90 P2).
 *
 * BEFORE: `useEngagementTime` emitted the FULL cumulative duration on every
 * trigger — visibility→hidden, `beforeunload`, effect cleanup, and route change.
 * One hide/show/unload cycle produced several overlapping cumulative
 * observations for a single page, inflating both event counts and every
 * duration-derived aggregate.
 *
 * The contract asserted here: emitted values are DELTAS that never overlap, and
 * they sum to the true time on page exactly once.
 */

import {
  nextEngagementObservation,
  EMPTY_ENGAGEMENT_LEDGER,
  type EngagementLedger,
} from '@/lib/analytics/engagement';

const MIN_FIRST = 10; // GA_CONFIG.ENGAGEMENT.MIN_ENGAGED_TIME

function observe(
  totalMs: number,
  activeMs: number,
  ledger: EngagementLedger = EMPTY_ENGAGEMENT_LEDGER,
) {
  return nextEngagementObservation({
    elapsedTotalMs: totalMs,
    elapsedActiveMs: activeMs,
    ledger,
    minFirstSeconds: MIN_FIRST,
  });
}

describe('engagement floor', () => {
  it('a bounce under the floor reports nothing at all', () => {
    expect(observe(3_000, 3_000)).toBeNull();
    expect(observe(9_999, 9_000)).toBeNull();
  });

  it('the first observation at the floor reports the full elapsed time', () => {
    const result = observe(12_000, 11_000);
    expect(result).not.toBeNull();
    expect(result!.seconds).toBe(12);
    expect(result!.activeSeconds).toBe(11);
  });
});

describe('non-overlapping deltas', () => {
  it('a hide → unload → cleanup burst emits ONCE, not three times', () => {
    // The exact C90 P2 scenario: three triggers, no new time between them.
    const first = observe(30_000, 25_000);
    expect(first).not.toBeNull();
    expect(first!.seconds).toBe(30);

    const second = observe(30_000, 25_000, first!.ledger);
    const third = observe(30_000, 25_000, first!.ledger);
    expect(second).toBeNull();
    expect(third).toBeNull();
  });

  it('emitted deltas sum to the true time on page exactly once', () => {
    const emitted: number[] = [];
    let ledger = EMPTY_ENGAGEMENT_LEDGER;

    for (const elapsed of [15_000, 40_000, 90_000]) {
      const result = observe(elapsed, elapsed, ledger);
      if (result) {
        emitted.push(result.seconds);
        ledger = result.ledger;
      }
    }

    expect(emitted).toEqual([15, 25, 50]);
    expect(emitted.reduce((a, b) => a + b, 0)).toBe(90); // true time, counted once
  });

  it('active time is accounted separately and also never overlaps', () => {
    const first = observe(20_000, 20_000);
    // Tab hidden for 30s: total advances, active does not.
    const second = observe(50_000, 20_000, first!.ledger);
    expect(second!.seconds).toBe(30);
    expect(second!.activeSeconds).toBe(0);
  });

  it('a sub-second follow-up delta is suppressed rather than sprayed', () => {
    const first = observe(30_000, 30_000);
    const second = observe(30_400, 30_400, first!.ledger);
    expect(second).toBeNull();
  });

  it('a follow-up past the floor does NOT re-apply the first-observation floor', () => {
    // Once a page has reported, a 2s delta is worth sending even though 2 < 10.
    const first = observe(30_000, 30_000);
    const second = observe(32_000, 32_000, first!.ledger);
    expect(second).not.toBeNull();
    expect(second!.seconds).toBe(2);
  });
});

describe('robustness', () => {
  it('a backwards clock can never rewind the ledger or emit a negative delta', () => {
    const first = observe(60_000, 60_000);
    const second = observe(10_000, 10_000, first!.ledger);
    expect(second).toBeNull();
    // The ledger is unchanged, so a later real advance still measures correctly.
    const third = observe(75_000, 75_000, first!.ledger);
    expect(third!.seconds).toBe(15);
  });

  it('a fresh page starts from zero and re-honors the floor', () => {
    const prior = observe(300_000, 300_000);
    expect(prior!.ledger.reportedTotalMs).toBe(300_000);
    // New page → EMPTY ledger, so a 3s visit reports nothing.
    expect(observe(3_000, 3_000, EMPTY_ENGAGEMENT_LEDGER)).toBeNull();
  });

  it('the shared empty ledger is never mutated', () => {
    observe(45_000, 45_000, EMPTY_ENGAGEMENT_LEDGER);
    expect(EMPTY_ENGAGEMENT_LEDGER).toEqual({
      reportedTotalMs: 0,
      reportedActiveMs: 0,
    });
  });
});
