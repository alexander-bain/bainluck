/**
 * #10090 (Alex 2026-11-01) — the EKG panel's scrolling list of every venue
 * update: source and receipt time to the hundredth, newest first, duplicates
 * kept, a reconnect's repeat dropped, bounded.
 */
import {
  addUpdates,
  EMPTY_UPDATE_LIST,
  heartbeatUpdates,
  UPDATE_LIST_CAPACITY,
  updateTimeText,
  venueName,
} from '@/lib/event/liveUpdateStream';
import { createLiveStreamController } from '@/lib/liveStreamController';

const T0 = Date.UTC(2026, 10, 1, 22, 57, 3, 420);

describe('#10090 heartbeat updates', () => {
  test('reads venue rows with parseable times and skips the rest', () => {
    const raw = JSON.stringify({
      t: 'x',
      updates: [['kalshi', new Date(T0).toISOString()], ['polymarket', 'soon'], ['', new Date(T0).toISOString()], 'junk'],
    });
    expect(heartbeatUpdates(raw)).toEqual([{ source: 'kalshi', at: T0 }]);
    expect(heartbeatUpdates(JSON.stringify({ t: 'x' }))).toEqual([]);
    expect(heartbeatUpdates('not json')).toEqual([]);
  });
});

describe('#10090 the update list', () => {
  test('newest first, same-time duplicates kept, a repeated batch dropped, bounded', () => {
    const a = { source: 'kalshi', at: T0 };
    const b = { source: 'polymarket', at: T0 + 100 };
    let list = addUpdates(EMPTY_UPDATE_LIST, [a, a, b]);
    expect(list.updates.map((u) => u.source)).toEqual(['polymarket', 'kalshi', 'kalshi']);
    expect(new Set(list.updates.map((u) => u.seq)).size).toBe(3);
    expect(addUpdates(list, [a, b])).toBe(list);
    list = addUpdates(list, Array.from({ length: 150 }, (_, i) => ({ source: 'kalshi', at: T0 + 1000 + i })));
    expect(list.updates).toHaveLength(UPDATE_LIST_CAPACITY);
    expect(list.updates[0].at).toBe(T0 + 1149);
  });

  test('each row names its venue and its time to the hundredth', () => {
    expect(updateTimeText(T0, 'UTC')).toBe('10:57:03.42 PM');
    expect(updateTimeText(Date.UTC(2026, 10, 1, 0, 0, 0, 59), 'UTC')).toBe('12:00:00.05 AM');
    expect(venueName('kalshi')).toBe('Kalshi');
    expect(venueName('polymarket')).toBe('Polymarket');
  });
});

class FakeSource {
  readyState = 1;
  private listeners: Record<string, ((e: { data?: unknown }) => void)[]> = {};
  addEventListener(type: string, fn: (e: { data?: unknown }) => void) {
    (this.listeners[type] ??= []).push(fn);
  }
  close() { this.readyState = 2; }
  emit(type: string, data?: unknown) {
    for (const fn of this.listeners[type] ?? []) fn({ data });
  }
}

test('#10090 the controller hands the heartbeat updates on, and nothing else', () => {
  const source = new FakeSource();
  const got: unknown[] = [];
  const frames: unknown[] = [];
  const controller = createLiveStreamController({
    open: () => source as never,
    now: () => 0,
    onFrame: (f) => frames.push(f),
    onDeliveringChange: () => undefined,
    onUpdates: (u) => got.push(u),
  });
  controller.start();
  source.emit('open');
  source.emit('heartbeat', JSON.stringify({ t: 1, updates: [['kalshi', new Date(T0).toISOString()]] }));
  source.emit('heartbeat', JSON.stringify({ t: 2 }));
  expect(got).toEqual([[{ source: 'kalshi', at: T0 }]]);
  expect(frames).toEqual([]);
  controller.stop();
});
