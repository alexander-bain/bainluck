/**
 * #10090 — the event page's heartbeat ("EKG"), as a pure decision.
 *
 * A beat is the markets reporting in: the stream's `confirmed_at` advancing, or
 * the accepted price clock advancing. Never a timer, never a keep-alive that
 * repeats its `confirmed_at`, never a reconnect or a re-read of the held value,
 * never while the transport is down. Bursts coalesce; silence goes flat.
 *
 * Time is a parameter (gotcha #44): one fixed epoch, offsets added to it.
 */

import {
  EKG_FLAT_AFTER_MS,
  EKG_MIN_BEAT_GAP_MS,
  EMPTY_EKG_TRACKER,
  presentEkg,
  stepEkgTracker,
  type EkgObservation,
  type EkgTracker,
} from '@/lib/event/ekgHeartbeat';

const T0 = Date.UTC(2026, 9, 30, 21, 0, 0);
const at = (s: number) => new Date(T0 + s * 1000).toISOString();
const ms = (s: number) => T0 + s * 1000;
const E = 15320001;

function obs(over: Partial<EkgObservation> = {}): EkgObservation {
  return { eventId: E, status: 'open', confirmedAt: null, priceObservedAt: at(0), ...over };
}

/** Mount on a held price observed at 0 s, open socket, no confirmation yet. */
function mounted(now = ms(0)): EkgTracker {
  return stepEkgTracker(EMPTY_EKG_TRACKER, obs(), now);
}

describe('#10090 EKG — what earns a beat', () => {
  test('the mount is a baseline, never a beat: flat until the first report', () => {
    const t = mounted();
    expect(t.beats).toBe(0);
    const p = presentEkg(t, 'open', ms(1));
    expect(p.mode).toBe('flat');
    expect(p.label).toBe('Markets reporting: no update yet');
    // The clock it mounted with is not news when it arrives again.
    expect(stepEkgTracker(t, obs({ priceObservedAt: at(0) }), ms(2)).beats).toBe(0);
  });

  test('one second reads singular', () => {
    const t = stepEkgTracker(mounted(), obs({ confirmedAt: at(6) }), ms(6));
    expect(presentEkg(t, 'open', ms(7)).label).toBe('Markets reporting: last update 1 second ago');
  });

  test('an advancing confirmed_at beats; the same confirmed_at again does not', () => {
    let t = mounted();
    t = stepEkgTracker(t, obs({ confirmedAt: at(6) }), ms(6));
    expect(t.beats).toBe(1);
    // The 20 s keep-alive repeats the newest value it has sent: no advance.
    t = stepEkgTracker(t, obs({ confirmedAt: at(6) }), ms(20));
    t = stepEkgTracker(t, obs({ confirmedAt: at(6) }), ms(20));
    expect(t.beats).toBe(1);
    t = stepEkgTracker(t, obs({ confirmedAt: at(12) }), ms(12.5));
    expect(t.beats).toBe(2);
  });

  test('a C1-withheld (null) confirmed_at neither beats nor erases what was seen', () => {
    let t = mounted();
    t = stepEkgTracker(t, obs({ confirmedAt: at(6) }), ms(6));
    t = stepEkgTracker(t, obs({ confirmedAt: null }), ms(8));
    expect(t.beats).toBe(1);
    // Released again at the same value: not a second report.
    t = stepEkgTracker(t, obs({ confirmedAt: at(6) }), ms(9));
    expect(t.beats).toBe(1);
  });

  test('a newly adopted headline price beats; a re-read of the held one does not', () => {
    let t = mounted();
    t = stepEkgTracker(t, obs({ priceObservedAt: at(0) }), ms(4));
    expect(t.beats).toBe(0);
    t = stepEkgTracker(t, obs({ priceObservedAt: at(4) }), ms(4.2));
    expect(t.beats).toBe(1);
    // A preview expiring back to an older committed clock is not newer.
    t = stepEkgTracker(t, obs({ priceObservedAt: at(2) }), ms(7));
    expect(t.beats).toBe(1);
  });

  test('an advance to a clock already older than the flat threshold is not a beat', () => {
    // First heartbeat after connect on a market that went quiet a minute ago.
    let t = mounted(ms(60));
    t = stepEkgTracker(t, obs({ confirmedAt: at(30) }), ms(61));
    expect(t.beats).toBe(0);
    expect(presentEkg(t, 'open', ms(61)).mode).toBe('flat');
  });

  test('a clock slightly ahead of ours still counts as now', () => {
    let t = mounted();
    t = stepEkgTracker(t, obs({ confirmedAt: at(7) }), ms(6));
    expect(t.beats).toBe(1);
  });
});

describe('#10090 EKG — disconnected never beats', () => {
  test('advances while retrying are recorded silently and the line reads interrupted', () => {
    let t = mounted();
    t = stepEkgTracker(t, obs({ status: 'retrying', confirmedAt: at(6), priceObservedAt: at(6) }), ms(6));
    expect(t.beats).toBe(0);
    const p = presentEkg(t, 'retrying', ms(6));
    expect(p.mode).toBe('interrupted');
    expect(p.label).toBe('Markets reporting: updates interrupted');
  });

  test('a reconnect alone is not a beat: the caught-up clock was already seen', () => {
    let t = mounted();
    t = stepEkgTracker(t, obs({ status: 'retrying', confirmedAt: at(6) }), ms(6));
    t = stepEkgTracker(t, obs({ status: 'connecting', confirmedAt: at(6) }), ms(8));
    t = stepEkgTracker(t, obs({ status: 'open', confirmedAt: at(6) }), ms(9));
    expect(t.beats).toBe(0);
    // A report made after the reconnect does beat.
    t = stepEkgTracker(t, obs({ status: 'open', confirmedAt: at(10) }), ms(10));
    expect(t.beats).toBe(1);
  });

  test.each(['connecting', 'rollover', 'unavailable', 'closed', 'idle'] as const)(
    '%s draws no beat and a flat line, even right after a report',
    (status) => {
      let t = mounted();
      t = stepEkgTracker(t, obs({ confirmedAt: at(6) }), ms(6));
      t = stepEkgTracker(t, obs({ status, confirmedAt: at(7) }), ms(7));
      expect(t.beats).toBe(1);
      expect(presentEkg(t, status, ms(7)).mode).toBe('flat');
    },
  );

});

describe('#10090 EKG — flat after silence', () => {
  test(`flat once ${EKG_FLAT_AFTER_MS / 1000} s pass with no report, alive just before`, () => {
    let t = mounted();
    t = stepEkgTracker(t, obs({ confirmedAt: at(6) }), ms(6));
    expect(presentEkg(t, 'open', ms(6) + EKG_FLAT_AFTER_MS - 1).mode).toBe('beating');
    const flat = presentEkg(t, 'open', ms(6) + EKG_FLAT_AFTER_MS);
    expect(flat.mode).toBe('flat');
    expect(flat.label).toBe('Markets reporting: last update 15 seconds ago');
  });

  test('the flat threshold sits between J cadence (~6 s) and the 20 s keep-alive', () => {
    expect(EKG_FLAT_AFTER_MS).toBeGreaterThanOrEqual(2 * 6_000);
    expect(EKG_FLAT_AFTER_MS).toBeLessThan(20_000);
  });

  test('the new event of a client navigation starts from its own baseline', () => {
    let t = mounted();
    t = stepEkgTracker(t, obs({ confirmedAt: at(6) }), ms(6));
    t = stepEkgTracker(t, obs({ eventId: E + 1, confirmedAt: at(7), priceObservedAt: at(7) }), ms(7));
    expect(t.eventId).toBe(E + 1);
    expect(t.beats).toBe(0);
  });
});

describe('#10090 EKG — bursts coalesce', () => {
  test(`at most one beat per ${EKG_MIN_BEAT_GAP_MS} ms; the burst still keeps the line alive`, () => {
    let t = mounted();
    t = stepEkgTracker(t, obs({ confirmedAt: at(6) }), ms(6));
    t = stepEkgTracker(t, obs({ confirmedAt: at(6), priceObservedAt: at(6.2) }), ms(6.2));
    t = stepEkgTracker(t, obs({ confirmedAt: at(7), priceObservedAt: at(6.2) }), ms(7));
    expect(t.beats).toBe(1);
    expect(t.lastSignalAt).toBe(ms(7));
    t = stepEkgTracker(t, obs({ confirmedAt: at(7.5), priceObservedAt: at(6.2) }), ms(7.5));
    expect(t.beats).toBe(2);
  });

  test('a steady 1 s cadence draws a beat every 2 s, never every frame', () => {
    let t = mounted();
    for (let s = 1; s <= 10; s += 1) t = stepEkgTracker(t, obs({ confirmedAt: at(s) }), ms(s));
    expect(t.beats).toBe(5);
  });

  test('a repeated render with the same input cannot draw a second beat', () => {
    let t = mounted();
    const o = obs({ confirmedAt: at(6) });
    t = stepEkgTracker(t, o, ms(6));
    t = stepEkgTracker(t, o, ms(9));
    expect(t.beats).toBe(1);
    expect(t.lastSignalAt).toBe(ms(6));
  });
});
