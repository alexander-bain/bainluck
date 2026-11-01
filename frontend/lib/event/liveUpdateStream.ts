/**
 * #10090 (Alex 2026-11-01) — THE EKG'S SCROLLING LIST OF VENUE UPDATES.
 *
 * "A super-fluid scrolling stream of the updates we're getting, with the
 * source and the timestamp to the hundredth of a second, even if they're
 * duplicates." The stream's heartbeat carries `updates` (`[[venue, ISO
 * receipt]]`, every venue input since the last heartbeat) and, beside it,
 * `update_p`: each input's venue home-team probability after it, or null
 * ("not a probability. that was kinda the whole point", Alex). The page keeps
 * the newest `UPDATE_LIST_CAPACITY`. Not trades, and never a price's age.
 * Mirrors the app's `LiveUpdateStream`.
 */

export interface LiveUpdate {
  source: string;
  /** Receipt time, ms. */
  at: number;
  /** The venue's home-team probability after this input, or null when unknown. */
  p: number | null;
  /** Arrival order on this page: same-millisecond rows are each their own. */
  seq: number;
}

export interface LiveUpdateList {
  /** Newest first. */
  updates: LiveUpdate[];
  nextSeq: number;
  /** Newest receipt held per venue: a reconnect's repeat is not new. */
  newest: Record<string, number>;
}

export const UPDATE_LIST_CAPACITY = 100;

export const EMPTY_UPDATE_LIST: LiveUpdateList = { updates: [], nextSeq: 0, newest: {} };

export type IncomingUpdate = { source: string; at: number; p: number | null };

/** The heartbeat's `updates` with their `update_p`, skipping rows that are not a venue and a parseable time. */
export function heartbeatUpdates(raw: unknown): IncomingUpdate[] {
  let body: unknown = raw;
  if (typeof raw === 'string') {
    try {
      body = JSON.parse(raw);
    } catch {
      return [];
    }
  }
  const beat = body && typeof body === 'object' ? (body as { updates?: unknown; update_p?: unknown }) : undefined;
  const rows = beat?.updates;
  if (!Array.isArray(rows)) return [];
  const probs = Array.isArray(beat?.update_p) && beat.update_p.length === rows.length ? beat.update_p : null;
  const out: IncomingUpdate[] = [];
  rows.forEach((row, index) => {
    if (!Array.isArray(row) || row.length !== 2) return;
    const [source, iso] = row;
    const at = typeof iso === 'string' ? Date.parse(iso) : NaN;
    const raw = probs?.[index];
    const p = typeof raw === 'number' && Number.isFinite(raw) && raw >= 0 && raw <= 1 ? raw : null;
    if (typeof source === 'string' && source && Number.isFinite(at)) out.push({ source, at, p });
  });
  return out;
}

/** Adds rows newer than what is held for their venue (same-time duplicates kept), newest first, bounded. */
export function addUpdates(list: LiveUpdateList, incoming: IncomingUpdate[]): LiveUpdateList {
  if (incoming.length === 0) return list;
  const floor = list.newest;
  const newest = { ...list.newest };
  let seq = list.nextSeq;
  const fresh: LiveUpdate[] = [];
  for (const row of [...incoming].sort((a, b) => a.at - b.at)) {
    const held = floor[row.source];
    if (held !== undefined && row.at <= held) continue;
    fresh.push({ source: row.source, at: row.at, p: row.p ?? null, seq: seq++ });
    newest[row.source] = Math.max(newest[row.source] ?? row.at, row.at);
  }
  if (fresh.length === 0) return list;
  return {
    updates: [...fresh.reverse(), ...list.updates].slice(0, UPDATE_LIST_CAPACITY),
    nextSeq: seq,
    newest,
  };
}

export function venueName(source: string): string {
  if (source === 'kalshi') return 'Kalshi';
  if (source === 'polymarket') return 'Polymarket';
  return source.charAt(0).toUpperCase() + source.slice(1);
}

/** The receipt time to the hundredth of a second, in the reader's time zone: 2:57:03.42 PM. */
export function updateTimeText(at: number, timeZone?: string): string {
  const parts = new Intl.DateTimeFormat('en-US', {
    hour: 'numeric', minute: '2-digit', second: '2-digit', hour12: true, timeZone,
  }).formatToParts(new Date(at));
  const get = (type: string) => parts.find((p) => p.type === type)?.value ?? '';
  const hundredths = String(Math.floor((((at % 1000) + 1000) % 1000) / 10)).padStart(2, '0');
  return `${get('hour')}:${get('minute')}:${get('second')}.${hundredths} ${get('dayPeriod')}`;
}

/** A venue's home-team probability as the row prints it: 81.0%. */
export function updateProbabilityText(p: number | null): string {
  return p === null ? '—' : `${(Math.round(p * 1000) / 10).toFixed(1)}%`;
}

/**
 * When each row is revealed, so the list streams at the venues' own pace
 * instead of landing a heartbeat's worth at once ("it just arrives in
 * batches", Alex). A batch is replayed from its arrival: each row after the
 * batch's oldest by its own receipt gap, capped at `PLAYBACK_SPREAD_MS` so a
 * batch always finishes before the next one is due. A new batch first reveals
 * whatever the last one has not.
 */
export const PLAYBACK_SPREAD_MS = 1000;

export interface UpdatePlayback {
  /** Highest seq scheduled. */
  scheduled: number;
  /** Highest seq on screen. */
  shown: number;
  /** [seq, reveal time (ms, the page's monotonic clock)], ascending. */
  queue: [number, number][];
}

export const EMPTY_PLAYBACK: UpdatePlayback = { scheduled: -1, shown: -1, queue: [] };

/** Schedules the rows newer than what is scheduled. `updates` is newest first. */
export function scheduleUpdates(playback: UpdatePlayback, updates: LiveUpdate[], now: number): UpdatePlayback {
  const fresh = updates.filter(update => update.seq > playback.scheduled).sort((a, b) => a.seq - b.seq);
  if (fresh.length === 0) return playback;
  const base = Math.min(...fresh.map(update => update.at));
  const flushed = playback.queue.length > 0 ? playback.queue[playback.queue.length - 1][0] : playback.shown;
  const queue: [number, number][] = [];
  let last = now;
  for (const update of fresh) {
    last = Math.max(last, now + Math.min(PLAYBACK_SPREAD_MS, Math.max(0, update.at - base)));
    queue.push([update.seq, last]);
  }
  return { scheduled: fresh[fresh.length - 1].seq, shown: Math.max(playback.shown, flushed), queue };
}

/** Reveals every row whose time has come. Same object when nothing changes. */
export function revealUpdates(playback: UpdatePlayback, now: number): UpdatePlayback {
  let count = 0;
  while (count < playback.queue.length && playback.queue[count][1] <= now) count++;
  if (count === 0) return playback;
  return { ...playback, shown: playback.queue[count - 1][0], queue: playback.queue.slice(count) };
}
