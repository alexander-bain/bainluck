/**
 * #925 — forward-fill of game state along a chart's minute-keyed points, with
 * the DATE of what was carried.
 *
 * `OddsChart` builds one row per minute (real snapshots plus gap-filled
 * minutes) and attaches score / period / clock from the rows that observed
 * them. Between observations the last state is carried forward so a scrub
 * always has something to say. The carry itself is right — a score does not
 * stop being true when it stops changing (#7211) — but presenting a 7:41 game
 * clock as if it had been seen at the 7:44 price is not, and that is what the
 * readout did: the `~` on the clock (the original #925 ship, `8bf2bf8d`) said
 * "approximate" without ever saying how old.
 *
 * ── WHY THREE CLOCKS AND NOT ONE ─────────────────────────────────────────────
 *
 * The three things the readout can print are observed by DIFFERENT rows, and a
 * row that observed one of them says nothing about the age of the other two:
 *
 *   - MLB serves `period: "Top 8th"` with no game clock at all, and ESPN emits
 *     score-only rows between half-innings.
 *   - A clock-only row is common mid-period: the clock ticks, the period and
 *     the score do not change, and the wire sends only what moved.
 *
 * So a single shared observation timestamp is wrong in both directions. A
 * period-only observation at 8:03 would refresh a clock last seen at 8:00 and
 * the card would stop dating it; a clock-only observation at 8:03 would
 * present a period last seen at 8:00 as freshly observed. Each field therefore
 * carries its own `_*ObservedAt` and its own `_*Approx`, and the card — which
 * is the only thing that knows what it actually rendered — decides what to
 * disclose. (Codex's independent review of the candidate reproduced exactly
 * these two failures; `codexIndependentStateClocks925.test.tsx` is its
 * reproducer and is pinned in `independentStateClocks925.test.tsx`.)
 *
 * Extracted from the component so the rule can be tested on the exact shape it
 * runs on, rather than through a recharts mouse event in jsdom. Mutates the
 * rows it is handed in place — that is the contract the component's `useMemo`
 * already had.
 */

export interface CarriedGameStateRow {
  timestamp: string;
  _homeScore?: number | null;
  _awayScore?: number | null;
  _period?: string | null;
  _clock?: string | null;
  /**
   * Set by the enrich step to the timestamp of the SNAPSHOT that supplied this
   * row's period / clock / score. Optional: when a row brings its own value
   * with no stamp, the row's own `timestamp` is used, so the helper is correct
   * for any caller that forgets to stamp rather than silently mis-dating.
   */
  _periodObservedAt?: string | null;
  _clockObservedAt?: string | null;
  _scoreObservedAt?: string | null;
  /** True when the field shown on this row was carried, not observed here. */
  _periodApprox?: boolean;
  _clockApprox?: boolean;
  _scoreApprox?: boolean;
}

/**
 * Mutates `sorted` (timestamp-ascending) in place and returns it.
 *
 * For each of period, clock and score independently: a row that brings its own
 * value is exact and dates itself; a row that does not inherits the last value
 * AND the timestamp of the row that observed it, and is flagged approximate.
 *
 * Rows before the first observation of a field carry nothing for it and are
 * NOT approximate — there is no state to be stale about (late first
 * observation); `_*ObservedAt` stays null so the card has nothing to date.
 *
 * `_clockApprox` keeps the exact meaning it has had since `8bf2bf8d` — "this
 * row's clock is inherited" — so the existing badge rendering is unchanged by
 * this file.
 */
export function carryGameStateForward<T extends CarriedGameStateRow>(sorted: T[]): T[] {
  let lastPeriod: string | null = null;
  let lastClock: string | null = null;
  let lastHomeScore: number | null = null;
  let lastAwayScore: number | null = null;
  let lastPeriodAt: string | null = null;
  let lastClockAt: string | null = null;
  let lastScoreAt: string | null = null;

  for (const pt of sorted) {
    // "Own" is decided from the value the row ARRIVED with, before any
    // forward-fill below writes to it — after that step every row looks
    // observed. Reading the value rather than the stamp is deliberate: it is
    // the same test the pre-#925 forward-fill used, so a row the enrich step
    // did not stamp is still classified the way it always was.
    const ownPeriod = pt._period != null && pt._period !== "";
    const ownClock = pt._clock != null && pt._clock !== "";
    const ownScore = pt._homeScore != null || pt._awayScore != null;

    if (ownPeriod) {
      lastPeriod = pt._period as string;
      lastPeriodAt = pt._periodObservedAt ?? pt.timestamp;
      pt._periodObservedAt = lastPeriodAt;
      pt._periodApprox = false;
    } else {
      pt._period = lastPeriod;
      pt._periodObservedAt = lastPeriod != null ? lastPeriodAt : null;
      pt._periodApprox = lastPeriod != null;
    }

    if (ownClock) {
      lastClock = pt._clock as string;
      lastClockAt = pt._clockObservedAt ?? pt.timestamp;
      pt._clockObservedAt = lastClockAt;
      pt._clockApprox = false;
    } else {
      pt._clock = lastClock;
      pt._clockObservedAt = lastClock != null ? lastClockAt : null;
      pt._clockApprox = lastClock != null;
    }

    if (ownScore) {
      // A row can observe one side's score and not the other's; the side it
      // did not bring is carried, but the row still counts as a score
      // observation and dates the pair. Splitting the two halves would date a
      // "101 - 98" readout by two different minutes with no way to show it.
      if (pt._homeScore != null) lastHomeScore = pt._homeScore;
      else pt._homeScore = lastHomeScore;
      if (pt._awayScore != null) lastAwayScore = pt._awayScore;
      else pt._awayScore = lastAwayScore;
      lastScoreAt = pt._scoreObservedAt ?? pt.timestamp;
      pt._scoreObservedAt = lastScoreAt;
      pt._scoreApprox = false;
    } else {
      pt._homeScore = lastHomeScore;
      pt._awayScore = lastAwayScore;
      const hadScore = lastHomeScore != null || lastAwayScore != null;
      pt._scoreObservedAt = hadScore ? lastScoreAt : null;
      pt._scoreApprox = hadScore;
    }
  }

  return sorted;
}
