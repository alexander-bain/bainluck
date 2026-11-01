/**
 * #10090 (Alex 2026-11-01) — the EKG panel's scrolling list of every venue
 * update: source and receipt time to the hundredth, newest first, duplicates
 * kept, a reconnect's repeat dropped, bounded.
 */
import {
  addUpdates,
  EMPTY_PLAYBACK,
  EMPTY_UPDATE_LIST,
  heartbeatUpdates,
  PLAYBACK_SPREAD_MS,
  advanceScreen,
  openScreen,
  revealUpdates,
  scheduleUpdates,
  SHOWN_CAPACITY,
  updateProbabilityText,
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
    expect(heartbeatUpdates(raw)).toEqual([{ source: 'kalshi', at: T0, p: null }]);
    expect(heartbeatUpdates(JSON.stringify({ t: 'x' }))).toEqual([]);
    expect(heartbeatUpdates('not json')).toEqual([]);
  });
});

describe('#10090 the update list', () => {
  test('newest first, same-time duplicates kept, a repeated batch dropped, bounded', () => {
    const a = { source: 'kalshi', at: T0, p: 0.36 };
    const b = { source: 'polymarket', at: T0 + 100, p: null };
    let list = addUpdates(EMPTY_UPDATE_LIST, [a, a, b]);
    expect(list.updates.map((u) => u.source)).toEqual(['polymarket', 'kalshi', 'kalshi']);
    expect(new Set(list.updates.map((u) => u.seq)).size).toBe(3);
    expect(addUpdates(list, [a, b])).toBe(list);
    list = addUpdates(list, Array.from({ length: 150 }, (_, i) => ({ source: 'kalshi', at: T0 + 1000 + i, p: null })));
    expect(list.updates.length).toBe(Math.min(UPDATE_LIST_CAPACITY, 153));
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
  expect(got).toEqual([[{ source: 'kalshi', at: T0, p: null }]]);
  expect(frames).toEqual([]);
  controller.stop();
});

// Alex 2026-11-01: "just shows the source and timestamp, but not a probability.
// that was kinda the whole point. it's also not a scrolling stream. it just
// arrives in batches".
describe('#10090 each update carries its probability', () => {
  test('update_p sits beside the two-item rows, same order; a bad or misaligned one is unknown', () => {
    const iso = new Date(T0).toISOString();
    expect(heartbeatUpdates(JSON.stringify({ updates: [['kalshi', iso], ['polymarket', iso]], update_p: [0.36, 1.7] })))
      .toEqual([{ source: 'kalshi', at: T0, p: 0.36 }, { source: 'polymarket', at: T0, p: null }]);
    expect(heartbeatUpdates(JSON.stringify({ updates: [['kalshi', iso]], update_p: [0.36, 0.4] })))
      .toEqual([{ source: 'kalshi', at: T0, p: null }]);
  });

  test('the row prints it to a tenth, or a dash when unknown', () => {
    expect(updateProbabilityText(0.8125)).toBe('81.3%');
    expect(updateProbabilityText(0.36)).toBe('36.0%');
    expect(updateProbabilityText(null)).toBe('—');
  });
});

describe('#10090 the list streams at the venues pace, not in batches', () => {
  const batch = (list: typeof EMPTY_UPDATE_LIST, offsets: number[]) =>
    addUpdates(list, offsets.map(ms => ({ source: 'kalshi', at: T0 + ms, p: 0.5 })));

  test('a batch is replayed by its own receipt gaps from its arrival', () => {
    const list = batch(EMPTY_UPDATE_LIST, [0, 300, 700]);
    let play = scheduleUpdates(EMPTY_PLAYBACK, list.updates, 1000);
    expect(play.queue.map(([, at]) => at)).toEqual([1000, 1300, 1700]);
    play = revealUpdates(play, 1000);
    expect(play.shown).toBe(0);
    play = revealUpdates(play, 1299);
    expect(play.shown).toBe(0);
    play = revealUpdates(play, 1300);
    expect(play.shown).toBe(1);
    expect(revealUpdates(play, 1301)).toBe(play);
  });

  test('a long batch is squeezed into one spread; the next batch first shows what is left', () => {
    let list = batch(EMPTY_UPDATE_LIST, [0, 5000]);
    let play = scheduleUpdates(EMPTY_PLAYBACK, list.updates, 0);
    expect(play.queue[1][1]).toBe(PLAYBACK_SPREAD_MS);
    list = batch(list, [6000]);
    play = scheduleUpdates(play, list.updates, 10);
    expect(play.shown).toBe(1);
    expect(play.queue).toEqual([[2, 10]]);
  });

  test('nothing new schedules nothing', () => {
    const list = batch(EMPTY_UPDATE_LIST, [0]);
    const play = scheduleUpdates(EMPTY_PLAYBACK, list.updates, 0);
    expect(scheduleUpdates(play, list.updates, 50)).toBe(play);
  });
});

describe('#10090 the panel keeps the rows it showed', () => {
  test('a new batch never shrinks the list, and rows sort by receipt across venues', () => {
    let list = addUpdates(EMPTY_UPDATE_LIST, Array.from({ length: 120 }, (_, i) => ({ source: 'kalshi', at: T0 + i, p: 0.5 })));
    let screen = openScreen(list.updates);
    expect(screen.rows).toHaveLength(SHOWN_CAPACITY);
    list = addUpdates(list, [{ source: 'kalshi', at: T0 + 500, p: 0.5 }, { source: 'polymarket', at: T0 + 100, p: 0.4 }]);
    screen = advanceScreen(screen, list.updates, 0);
    expect(screen.rows).toHaveLength(SHOWN_CAPACITY);       // nothing taken away while the batch waits
    screen = advanceScreen(screen, list.updates, PLAYBACK_SPREAD_MS);
    expect(screen.rows[0].at).toBe(T0 + 500);
    expect(screen.rows.find(row => row.source === 'polymarket')?.p).toBe(0.4);
    expect(screen.rows).toHaveLength(SHOWN_CAPACITY);
    expect(advanceScreen(screen, list.updates, PLAYBACK_SPREAD_MS + 50)).toBe(screen);
  });
});
