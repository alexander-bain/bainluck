/**
 * #10090 (Alex 2026-11-01) — THE EKG'S SCROLLING LIST OF VENUE UPDATES.
 *
 * "A super-fluid scrolling stream of the updates we're getting, with the
 * source and the timestamp to the hundredth of a second, even if they're
 * duplicates." The stream's heartbeat carries `updates` (`[[venue, ISO
 * receipt]]`, every venue input since the last heartbeat); the page keeps the
 * newest `UPDATE_LIST_CAPACITY`. Not trades, and never a price's age: each row
 * says only that a venue reported in. Mirrors the app's `LiveUpdateStream`.
 */

export interface LiveUpdate {
  source: string;
  /** Receipt time, ms. */
  at: number;
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

/** The heartbeat's `updates`, skipping rows that are not a venue and a parseable time. */
export function heartbeatUpdates(raw: unknown): { source: string; at: number }[] {
  let body: unknown = raw;
  if (typeof raw === 'string') {
    try {
      body = JSON.parse(raw);
    } catch {
      return [];
    }
  }
  const rows = body && typeof body === 'object' ? (body as { updates?: unknown }).updates : undefined;
  if (!Array.isArray(rows)) return [];
  const out: { source: string; at: number }[] = [];
  for (const row of rows) {
    if (!Array.isArray(row) || row.length !== 2) continue;
    const [source, iso] = row;
    const at = typeof iso === 'string' ? Date.parse(iso) : NaN;
    if (typeof source === 'string' && source && Number.isFinite(at)) out.push({ source, at });
  }
  return out;
}

/** Adds rows newer than what is held for their venue (same-time duplicates kept), newest first, bounded. */
export function addUpdates(list: LiveUpdateList, incoming: { source: string; at: number }[]): LiveUpdateList {
  if (incoming.length === 0) return list;
  const floor = list.newest;
  const newest = { ...list.newest };
  let seq = list.nextSeq;
  const fresh: LiveUpdate[] = [];
  for (const row of [...incoming].sort((a, b) => a.at - b.at)) {
    const held = floor[row.source];
    if (held !== undefined && row.at <= held) continue;
    fresh.push({ source: row.source, at: row.at, seq: seq++ });
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
