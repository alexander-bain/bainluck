import type { StreamHandle } from './liveStreamController';

export interface MarketStreamDependencies {
  marketIds: number[];
  open: (ids: number[]) => StreamHandle;
  now: () => number;
  onInvalidate: (ids: number[]) => void;
}

function payload(event: unknown): Record<string, unknown> | null {
  try {
    const raw = (event as { data?: unknown })?.data;
    if (typeof raw !== 'string') return null;
    const value: unknown = JSON.parse(raw);
    return value && typeof value === 'object' && !Array.isArray(value)
      ? value as Record<string, unknown> : null;
  } catch { return null; }
}

/** One bounded market channel. Frames invalidate REST; a heartbeat is no quote. */
export function createMarketStreamController(deps: MarketStreamDependencies) {
  const ids = [...new Set(deps.marketIds)].sort((a, b) => a - b);
  const valid = ids.length > 0 && ids.length <= 50 && ids.every(id => Number.isSafeInteger(id) && id > 0);
  const terminal = new Set<number>();
  let handle: StreamHandle | null = null;
  let stopped = true;
  let generation = 0;
  let lastWire = 0;
  let retryAt: number | null = null;

  const retire = () => { generation++; handle?.close(); handle = null; };
  const recycle = (delay: number) => {
    retire();
    retryAt = deps.now() + delay;
  };
  const connect = () => {
    const active = ids.filter(id => !terminal.has(id));
    if (stopped || active.length === 0) return;
    retire();
    retryAt = null;
    const epoch = generation;
    let next: StreamHandle;
    try { next = deps.open(active); }
    catch { recycle(60_000); return; }
    handle = next;
    lastWire = deps.now();
    const current = () => !stopped && epoch === generation && handle === next;
    next.addEventListener('open', () => {
      if (!current()) return;
      lastWire = deps.now();
      // Includes unavailable IDs: connecting does not close a pub/sub gap.
      deps.onInvalidate(active);
    });
    next.addEventListener('heartbeat', () => {
      if (current()) lastWire = deps.now();
    });
    next.addEventListener('market', event => {
      if (!current()) return;
      const frame = payload(event);
      if (!frame || frame.invalidation !== true || typeof frame.terminal !== 'boolean' ||
          typeof frame.market_id !== 'number' || !active.includes(frame.market_id)) return;
      lastWire = deps.now();
      deps.onInvalidate([frame.market_id]);
      if (frame.terminal) terminal.add(frame.market_id);
    });
    next.addEventListener('reconnect', () => {
      if (!current()) return;
      deps.onInvalidate(active);
      recycle(5_000);
    });
    next.addEventListener('closed', event => {
      if (!current()) return;
      const frame = payload(event);
      const ended = frame?.reason === 'settled' && Array.isArray(frame.market_ids)
        ? frame.market_ids.filter((id): id is number => typeof id === 'number' && active.includes(id)) : [];
      deps.onInvalidate(active);
      ended.forEach(id => terminal.add(id));
      recycle(60_000);
    });
    next.addEventListener('error', () => {
      if (!current()) return;
      // EventSource does not reveal the HTTP status and can retry while still
      // CONNECTING. Own every error retry so refusals cannot spin invisibly.
      recycle(60_000);
    });
  };

  return {
    start() { if (!stopped || !valid) return; stopped = false; connect(); },
    stop() { stopped = true; retryAt = null; retire(); },
    tick() {
      if (stopped) return;
      if (retryAt !== null && deps.now() >= retryAt) connect();
      else if (handle && deps.now() - lastWire > 65_000) recycle(5_000);
    },
  };
}
