import type { ApiError } from './api';
import type { FuturesMarketDetailResponse, FuturesHistoryResponse } from './types';

// PostgreSQL observation clocks retain microseconds. Date.parse alone truncates
// distinct observations within the same millisecond into an apparent tie.
const instant = (value: string | null | undefined): number | null => {
  const match = value?.match(/^(\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d)(?:\.(\d+))?(Z|[+-]\d\d:\d\d)$/);
  if (!match) return null;
  const seconds = Date.parse(match[1] + match[3]);
  const micros = Number((match[2] ?? '').padEnd(6, '0').slice(0, 6));
  return Number.isFinite(seconds) ? seconds * 1000 + micros : null;
};

export function futuresDetailSettled(market: FuturesMarketDetailResponse): boolean {
  return market.status === 'resolved' || market.status === 'closed' || market.outcomes.some(row => row.is_winner === true);
}

/** Private absence watermarks never become a fabricated wire observation clock. */
export function createFuturesDetailReconciler(initial: FuturesMarketDetailResponse) {
  let held = initial;
  let withdrawals = new Map(initial.outcomes.filter(row => row.probability === null)
    .map(row => [row.id, instant(row.last_updated)]));
  return {
    current: () => held,
    adopt(incoming: FuturesMarketDetailResponse): FuturesMarketDetailResponse {
      if (incoming.id !== held.id || new Set(incoming.outcomes.map(row => row.id)).size !== incoming.outcomes.length) return held;
      if (futuresDetailSettled(held)) {
        if (!futuresDetailSettled(incoming)) return held;
        const winners = held.outcomes.filter(row => row.is_winner).map(row => row.id).sort().join(',');
        if (winners && incoming.outcomes.filter(row => row.is_winner).map(row => row.id).sort().join(',') !== winners) return held;
      }
      const before = new Map(held.outcomes.map(row => [row.id, row]));
      // Mutually exclusive fields are normalized against the WHOLE raw vector:
      // a sibling's new quote or withdrawal can change this row's displayed %
      // without changing this row's observation clock. Never mix two divisors.
      const normalizedChange = incoming.mutually_exclusive && (
        held.outcomes.length !== incoming.outcomes.length || incoming.outcomes.some(row => {
          const prior = before.get(row.id);
          return !prior || (prior.probability !== null && row.probability === null) ||
            (instant(row.last_updated) !== null && (instant(row.last_updated)! > (instant(prior.last_updated) ?? -Infinity)));
        })
      );
      const nextWithdrawals = new Map(withdrawals);
      let preserved = false;
      const outcomes = incoming.outcomes.map(row => {
        const prior = before.get(row.id);
        const after = instant(row.last_updated);
        const retain = () => { preserved = true; return prior!; };
        if (!prior) {
          if (row.probability === null) nextWithdrawals.set(row.id, after);
          return row;
        }
        if ((prior.is_winner === true && row.is_winner !== true) || (prior.is_winner != null && row.is_winner == null)) return retain();
        if (!futuresDetailSettled(held) && futuresDetailSettled(incoming) && row.is_winner !== null) {
          nextWithdrawals.delete(row.id);
          return row;
        }
        const oldClock = instant(prior.last_updated);
        if (row.probability === null) {
          const clocks = [oldClock, nextWithdrawals.get(row.id), after].filter((n): n is number => typeof n === 'number');
          const watermark = Math.max(oldClock ?? -Infinity, nextWithdrawals.get(row.id) ?? -Infinity);
          if (after !== null && after < watermark) return retain();
          nextWithdrawals.set(row.id, clocks.length ? Math.max(...clocks) : null);
          return row;
        }
        if (nextWithdrawals.has(row.id)) {
          const watermark = nextWithdrawals.get(row.id);
          if (after === null || (watermark != null && after <= watermark)) return retain();
          nextWithdrawals.delete(row.id);
        }
        if (oldClock !== null && (after === null || after < oldClock || (after === oldClock && row.probability !== prior.probability && !normalizedChange))) return retain();
        return row;
      });
      if (preserved && incoming.mutually_exclusive) return held;
      // A stale retained price cannot acquire the incoming body's new provider.
      if (preserved && (incoming.source !== held.source || incoming.external_id !== held.external_id || incoming.group_id !== held.group_id ||
        JSON.stringify(incoming.bookmakers) !== JSON.stringify(held.bookmakers))) return held;
      withdrawals = nextWithdrawals;
      held = preserved ? { ...incoming, outcomes, updated_at: held.updated_at } : incoming;
      return held;
    },
  };
}

/** Keep an already observed history tail when a delayed read regresses it.
 * All points remain actual served observations; invalidations add no points. */
export function reconcileFuturesHistory(held: FuturesHistoryResponse | undefined, incoming: FuturesHistoryResponse, market?: FuturesMarketDetailResponse): FuturesHistoryResponse {
  if (!held || held.market_id !== incoming.market_id || held.hours !== incoming.hours) return incoming;
  const old = new Map(held.outcomes.map(row => [row.outcome_id, row]));
  return { ...incoming, outcomes: incoming.outcomes.map(row => {
    const prior = old.get(row.outcome_id);
    if (!prior) return row;
    const tail = (history: typeof row.history) => history.reduce<typeof row.history[number] | undefined>((latest, point) =>
      (instant(point.timestamp) ?? -Infinity) >= (instant(latest?.timestamp) ?? -Infinity) ? point : latest, undefined);
    const a = tail(prior.history), b = tail(row.history);
    const verdict = market && futuresDetailSettled(market) ? market.outcomes.find(outcome => outcome.id === row.outcome_id)?.is_winner : null;
    const finalTail = verdict != null && b?.probability === (verdict ? 1 : 0);
    if (a && (!b || (instant(b.timestamp) ?? -Infinity) < (instant(a.timestamp) ?? -Infinity) ||
      (instant(b.timestamp) === instant(a.timestamp) && b.bookmaker === a.bookmaker && b.probability !== a.probability && !finalTail))) return prior;
    return row;
  }) };
}

export const FUTURES_REFRESH_INTERVAL_MS = 2_000;

/** One inflight authoritative read plus one trailing read, paced on dispatch.
 * Failed final reads remain owed even if the wire keeps sending heartbeats. */
export function createFuturesReadScheduler(options: {
  now: () => number;
  read: (signal: AbortSignal, current: () => boolean) => Promise<void>;
}) {
  let stopped = false, visible = true, pending = false, running = false;
  let eligibleAt = 0, fallbackAt = options.now() + 60_000;
  let abort: AbortController | undefined;
  const pump = () => {
    if (stopped || !visible || running || !pending || options.now() < eligibleAt) return;
    pending = false; running = true;
    eligibleAt = options.now() + FUTURES_REFRESH_INTERVAL_MS;
    fallbackAt = options.now() + 60_000;
    const request = new AbortController(); abort = request;
    const current = () => !stopped && visible && abort === request && !request.signal.aborted;
    void options.read(request.signal, current).catch((error: ApiError) => {
      if (!current()) return;
      const retry = error.status === 429 && Number.isFinite(error.retryAfterMs) && error.retryAfterMs! > 0 ? error.retryAfterMs! : 60_000;
      eligibleAt = Math.max(eligibleAt, options.now() + retry);
      pending = true;
    }).finally(() => {
      if (abort !== request) return;
      running = false;
      if (current()) pump();
    });
  };
  return {
    request() { pending = true; pump(); },
    tick() { if (options.now() >= fallbackAt) pending = true; pump(); },
    setVisible(next: boolean) {
      if (visible === next) return;
      visible = next;
      if (!next) { abort?.abort(); abort = undefined; running = false; }
      else { pending = true; pump(); }
    },
    stop() { stopped = true; abort?.abort(); abort = undefined; },
  };
}
