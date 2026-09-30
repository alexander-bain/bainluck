import type { FeedItem } from '../types';
import type { DiscoverPriceCards } from './priceRefresh';
import { priceKey } from './priceRefresh';

type Timer = ReturnType<typeof setTimeout>;
export interface PriceDeliveryDependencies {
  visible: () => FeedItem[];
  fetch: (items: FeedItem[], signal: AbortSignal) => Promise<DiscoverPriceCards>;
  accept: (response: DiscoverPriceCards, requested: Set<string>) => void;
  now: () => number;
  setTimer: (callback: () => void, ms: number) => Timer;
  clearTimer: (timer: Timer) => void;
}

/** One foreground dispatcher, including every 50-ID batch and recovery read. */
export function createPriceDelivery(deps: PriceDeliveryDependencies) {
  let active = false;
  let epoch = 0;
  let notBefore = -Infinity;
  let pending = new Set<string>();
  let timer: Timer | null = null;
  let fallback: Timer | null = null;
  let flight: AbortController | null = null;

  const schedule = () => {
    if (!active || flight || timer !== null || pending.size === 0) return;
    timer = deps.setTimer(() => { timer = null; void dispatch(); }, Math.max(0, notBefore - deps.now()));
  };
  const invalidate = () => {
    if (!active) return;
    deps.visible().forEach(item => { const key = priceKey(item); if (key) pending.add(key); });
    schedule();
  };
  const armFallback = () => {
    fallback = deps.setTimer(() => {
      fallback = null;
      if (!active) return;
      // Pubsub is lossy. Heartbeats never disable this recovery read.
      invalidate();
      armFallback();
    }, 60_000);
  };
  const dispatch = async () => {
    if (!active || flight) return;
    if (deps.now() < notBefore) { schedule(); return; }
    const visible = new Map(deps.visible().map(item => [priceKey(item), item]));
    for (const key of pending) if (!visible.has(key)) pending.delete(key);
    const keys = [...pending].slice(0, 50);
    if (!keys.length) return;
    keys.forEach(key => pending.delete(key));
    const selected = keys.map(key => visible.get(key)!);
    const generation = epoch;
    const controller = new AbortController();
    flight = controller;
    notBefore = Math.max(notBefore, deps.now() + 2_000);
    try {
      const response = await deps.fetch(selected, controller.signal);
      if (!active || epoch !== generation || controller.signal.aborted) return;
      const stillVisible = new Set(deps.visible().map(priceKey));
      deps.accept(response, new Set(keys.filter(key => stillVisible.has(key))));
    } catch (error) {
      if (!active || epoch !== generation || controller.signal.aborted) return;
      const failure = error as { status?: number; retryAfterMs?: number };
      const supplied = failure.status === 429 && Number.isFinite(failure.retryAfterMs) && failure.retryAfterMs! > 0
        ? failure.retryAfterMs! : 60_000;
      notBefore = Math.max(notBefore, deps.now() + supplied);
      // Queue failed members behind untouched batches, so one refused read
      // cannot permanently starve the later half of a visible group.
      keys.forEach(key => pending.add(key));
    } finally {
      if (flight === controller) flight = null;
      if (active && epoch === generation) schedule();
    }
  };
  return {
    start() { if (active) return; active = true; epoch++; invalidate(); armFallback(); },
    invalidate,
    stop() {
      active = false; epoch++; pending = new Set();
      if (timer !== null) deps.clearTimer(timer);
      if (fallback !== null) deps.clearTimer(fallback);
      timer = null; fallback = null;
      flight?.abort(); flight = null;
      // A known cooldown survives hide/show.
    },
  };
}
