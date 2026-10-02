/**
 * #10200 (child of #9655) — the chart status's words, as a pure decision.
 *
 * Every receipt here is keyed on the ACCEPTED price clock advancing, never on a
 * frame arriving: the page refuses frames (p = null, an older revision, a wrong
 * phase, a raw row on a folded hero), and a status that said "Updated" on
 * arrival would claim a change the hero never printed. The mounted page fixture
 * (`liveConnectionStatusHeldPage9655.test.tsx`) proves the page feeds this the
 * adopted value; this file proves what it does with it.
 *
 * Time is a parameter (gotcha #44): one fixed epoch, offsets added to it.
 */

import {
  CONNECTION_FEEDBACK_MS,
  EMPTY_CONNECTION_TRACKER,
  formatObservationClock,
  presentConnectionStatus,
  stepConnectionTracker,
  type ConnectionObservation,
  type ConnectionPresentationInput,
  type ConnectionTracker,
} from '@/lib/event/liveConnectionStatus';

const T0 = Date.UTC(2026, 9, 2, 20, 0, 0);
const at = (s: number) => new Date(T0 + s * 1000).toISOString();

function obs(over: Partial<ConnectionObservation> = {}): ConnectionObservation {
  return {
    eventId: 1,
    status: 'open',
    priceObservedAt: at(0),
    valueKey: '60/40',
    terminal: false,
    ...over,
  };
}

const QUIET: Omit<ConnectionPresentationInput, 'status'> = {
  terminalLabel: null,
  priceMayBeOld: false,
  scoreMayBeOld: false,
};

/** Feed a run of observations at the given clock offsets; return the tracker. */
function run(steps: Array<[number, Partial<ConnectionObservation>]>): ConnectionTracker {
  return steps.reduce(
    (tracker, [s, over]) => stepConnectionTracker(tracker, obs(over), T0 + s * 1000),
    EMPTY_CONNECTION_TRACKER,
  );
}

function label(tracker: ConnectionTracker, nowS: number, over: Partial<ConnectionPresentationInput> = {}) {
  return presentConnectionStatus(tracker, { ...QUIET, status: 'open', ...over }, T0 + nowS * 1000).label;
}

describe('#10200 the tracker: receipts come from the adopted clock only', () => {
  it('the first observation of a mount is a baseline, never a change', () => {
    const t = run([[0, {}]]);
    expect(t.feedback).toBeNull();
    expect(label(t, 0)).toBe('Connected · waiting');
  });

  it('a newer adopted observation with a new printed value is Updated — briefly', () => {
    const t = run([[0, {}], [5, { priceObservedAt: at(5), valueKey: '62/38' }]]);
    expect(label(t, 5)).toBe('Updated');
    expect(label(t, 5 + CONNECTION_FEEDBACK_MS / 1000 - 0.001)).toBe('Updated');
    // ...then back to quiet.
    expect(label(t, 5 + CONNECTION_FEEDBACK_MS / 1000)).toBe('Connected · waiting');
  });

  it('a newer adopted observation with the same printed value is "no change"', () => {
    const t = run([[0, {}], [5, { priceObservedAt: at(5) }]]);
    expect(label(t, 5)).toBe('Connected · no change');
    // "Connected" is a socket claim: without an open socket it is just "No change".
    expect(label(t, 5, { status: 'idle' })).toBe('No change');
  });

  it('the SAME clock again — a duplicate, a re-render, a heartbeat, a mount — earns nothing', () => {
    const once = run([[0, {}], [5, { priceObservedAt: at(5), valueKey: '62/38' }]]);
    const again = stepConnectionTracker(once, obs({ priceObservedAt: at(5), valueKey: '62/38' }), T0 + 9_000);
    expect(again.feedback).toEqual(once.feedback);
    expect(label(again, 9)).toBe('Connected · waiting');
  });

  it('an OLDER clock (a refused stale frame the page did not adopt) earns nothing', () => {
    const t = run([[0, { priceObservedAt: at(10) }], [12, { priceObservedAt: at(4), valueKey: '61/39' }]]);
    expect(t.feedback).toBeNull();
    expect(t.lastObservedAt).toBe(T0 + 10_000);
  });

  it('an absent or unparseable clock never counts as newer', () => {
    const t = run([[0, {}], [3, { priceObservedAt: null }], [4, { priceObservedAt: 'not a time' }]]);
    expect(t.feedback).toBeNull();
  });

  it('a changed printed value with NO newer clock is tracked but not claimed', () => {
    const t = run([[0, {}], [3, { valueKey: '55/45' }]]);
    expect(t.feedback).toBeNull();
    // The next real receipt compares against what was on screen, so an
    // unchanged newer observation of 55/45 reads "no change", not "Updated".
    const next = stepConnectionTracker(t, obs({ priceObservedAt: at(6), valueKey: '55/45' }), T0 + 6_000);
    expect(next.feedback?.kind).toBe('unchanged');
  });
});

describe('#10200 interruption and recovery', () => {
  it('a real retry reads interrupted, and that outranks a fresh receipt', () => {
    const t = run([[0, {}], [5, { status: 'retrying' }]]);
    expect(t.interrupted).toBe(true);
    const p = presentConnectionStatus(t, { ...QUIET, status: 'retrying' }, T0 + 5_000);
    expect(p.label).toBe('Updates interrupted · reconnecting');
    expect(p.tone).toBe('attention');
    expect(p.announcement).toBe('Updates interrupted · reconnecting');
  });

  it('the socket reopening alone is "Connected", NOT "Updates resumed"', () => {
    const t = run([[0, {}], [5, { status: 'retrying' }], [9, { status: 'open' }]]);
    expect(t.interrupted).toBe(true);
    expect(label(t, 9)).toBe('Connected · waiting');
  });

  it('"Updates resumed" is earned by an observation ADOPTED after the interruption — unchanged value included', () => {
    const t = run([
      [0, {}],
      [5, { status: 'retrying' }],
      [9, { status: 'open' }],
      [11, { status: 'open', priceObservedAt: at(11) }],
    ]);
    expect(t.interrupted).toBe(false);
    const p = presentConnectionStatus(t, { ...QUIET, status: 'open' }, T0 + 11_000);
    expect(p.label).toBe('Updates resumed');
    expect(p.announcement).toBe('Updates resumed');
  });

  it('a value polled in WHILE still retrying does not clear the interruption', () => {
    const t = run([
      [0, {}],
      [5, { status: 'retrying' }],
      [8, { status: 'retrying', priceObservedAt: at(8), valueKey: '63/37' }],
    ]);
    expect(t.interrupted).toBe(true);
    expect(label(t, 8, { status: 'retrying' })).toBe('Updates interrupted · reconnecting');
    // ...so the first adoption after the socket recovers is the one that resumes.
    const after = stepConnectionTracker(t, obs({ status: 'open', priceObservedAt: at(12), valueKey: '63/37' }), T0 + 12_000);
    expect(after.feedback?.kind).toBe('resumed');
  });

  it('a rollover is never an interruption — and never a connection claim, because its socket is closed', () => {
    const t = run([[0, {}], [5, { status: 'rollover' }], [6, { status: 'connecting' }], [7, { status: 'open' }]]);
    expect(t.interrupted).toBe(false);
    const p = presentConnectionStatus(t, { ...QUIET, status: 'rollover' }, T0 + 5_000);
    expect(p).toEqual({ label: 'Connecting', tone: 'neutral', breathes: false, announcement: '' });
    expect(label(t, 7, { status: 'open' })).toBe('Connected · waiting');
  });

  it('a receipt landing mid-rollover is "No change", not "Connected · no change"', () => {
    const t = run([[0, {}], [5, { status: 'rollover', priceObservedAt: at(5) }]]);
    expect(label(t, 5, { status: 'rollover' })).toBe('No change');
  });
});

describe('#10200 the words for each transport state', () => {
  const t = run([[0, {}]]);
  it.each([
    ['connecting', 'Connecting', false],
    ['open', 'Connected · waiting', true],
    ['rollover', 'Connecting', false],
    ['quiet', 'Connected · checking', false],
    ['unavailable', 'Checking for updates', false],
    ['closed', 'Checking for updates', false],
    ['idle', 'Checking for updates', false],
  ] as const)('%s → %s', (status, words, breathes) => {
    const p = presentConnectionStatus(t, { ...QUIET, status }, T0);
    expect(p.label).toBe(words);
    // Only a healthy open connection earns motion; nothing else claims to be live.
    expect(p.breathes).toBe(breathes);
    expect(p.announcement).toBe('');
  });

  it('no state ever prints a ticking age or the word "Live"', () => {
    for (const status of ['connecting', 'open', 'quiet', 'retrying', 'rollover', 'unavailable', 'closed', 'idle'] as const) {
      const words = presentConnectionStatus(t, { ...QUIET, status }, T0).label;
      expect(words).not.toMatch(/\d+\s*s\b|ago|live/i);
    }
  });
});

describe('#10200 truth outranks a healthy socket; the finish outranks everything', () => {
  const fresh = run([[0, {}], [5, { priceObservedAt: at(5), valueKey: '62/38' }]]);

  it('an old price is named even while the socket is open and a receipt is fresh', () => {
    const p = presentConnectionStatus(fresh, { ...QUIET, status: 'open', priceMayBeOld: true }, T0 + 5_000);
    expect(p.label).toBe('Price may be old');
    expect(p.tone).toBe('neutral');
    expect(p.breathes).toBe(false);
  });

  it('an old score is named the same way', () => {
    expect(
      presentConnectionStatus(fresh, { ...QUIET, status: 'open', scoreMayBeOld: true }, T0 + 5_000).label,
    ).toBe('Score may be old');
  });

  it('the finish replaces every connection word and is announced', () => {
    const finished = stepConnectionTracker(fresh, obs({ terminal: true, priceObservedAt: at(5) }), T0 + 6_000);
    const p = presentConnectionStatus(
      finished,
      { ...QUIET, status: 'open', terminalLabel: 'Finished', priceMayBeOld: true },
      T0 + 6_000,
    );
    expect(p).toEqual({ label: 'Finished', tone: 'neutral', breathes: false, announcement: 'Finished' });
    expect(finished.feedback).toBeNull();
  });

  it('a late frame after the finish mints no receipt', () => {
    const finished = stepConnectionTracker(fresh, obs({ terminal: true }), T0 + 6_000);
    const late = stepConnectionTracker(finished, obs({ terminal: true, priceObservedAt: at(9), valueKey: '70/30' }), T0 + 9_000);
    expect(late.feedback).toBeNull();
    expect(late.sawUnfinished).toBe(true);
  });

  it('a mount that opens on a finished page never saw it unfinished', () => {
    expect(run([[0, { terminal: true }]]).sawUnfinished).toBe(false);
  });
});

describe('#10200 navigation resets the memory', () => {
  it('a different event starts from nothing — no carried interruption, no carried receipt', () => {
    const a = run([[0, {}], [5, { status: 'retrying' }], [6, { status: 'retrying', priceObservedAt: at(6), valueKey: '1/99' }]]);
    expect(a.interrupted).toBe(true);
    const b = stepConnectionTracker(a, obs({ eventId: 2, status: 'connecting', priceObservedAt: at(1) }), T0 + 7_000);
    expect(b).toEqual({
      eventId: 2,
      lastObservedAt: T0 + 1_000,
      lastValueKey: '60/40',
      interrupted: false,
      feedback: null,
      sawUnfinished: true,
    });
    expect(label(b, 7, { status: 'connecting' })).toBe('Connecting');
  });
});

describe('#10200 the tap-detail clock', () => {
  it('prints the wall time with its zone', () => {
    // The suite runs in UTC (jest.config.js pins it).
    expect(formatObservationClock('2026-10-02T20:04:11Z')).toBe('Oct 2, 8:04:11 PM UTC');
  });

  it('returns null for an absent or unreadable clock — the caller says "Time unavailable"', () => {
    expect(formatObservationClock(null)).toBeNull();
    expect(formatObservationClock(undefined)).toBeNull();
    expect(formatObservationClock('yesterday-ish')).toBeNull();
  });
});
