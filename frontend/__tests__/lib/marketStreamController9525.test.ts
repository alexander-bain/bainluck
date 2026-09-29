import { createMarketStreamController } from '../../lib/marketStreamController';

class Wire {
  readyState = 1;
  listeners = new Map<string, (event: unknown) => void>();
  addEventListener(name: string, callback: (event: unknown) => void) { this.listeners.set(name, callback); }
  close() { this.readyState = 2; }
  emit(name: string, value: unknown = {}) { this.listeners.get(name)?.({ data: JSON.stringify(value) }); }
}

function rig(ids = [1, 2]) {
  let at = 0;
  const wires: Wire[] = [];
  const admitted: number[][] = [];
  const onInvalidate = jest.fn();
  const controller = createMarketStreamController({
    marketIds: ids, now: () => at, onInvalidate,
    open: batch => { admitted.push(batch); const wire = new Wire(); wires.push(wire); return wire; },
  });
  controller.start();
  return { controller, wires, admitted, onInvalidate, tick: (time: number) => { at = time; controller.tick(); } };
}

test('open reconciles the whole requested set; heartbeat never invalidates a quote', () => {
  const r = rig();
  r.wires[0].emit('open', { market_ids: [1], unavailable_market_ids: [2] });
  expect(r.onInvalidate).toHaveBeenLastCalledWith([1, 2]);
  r.wires[0].emit('heartbeat');
  expect(r.onInvalidate).toHaveBeenCalledTimes(1);
});

test('only valid requested market invalidations land, including a final invalidation', () => {
  const r = rig();
  r.wires[0].emit('market', { market_id: 3, invalidation: true, terminal: false });
  r.wires[0].emit('market', { market_id: 1, invalidation: true });
  expect(r.onInvalidate).not.toHaveBeenCalled();
  r.wires[0].emit('market', { market_id: 1, invalidation: true, terminal: true });
  expect(r.onInvalidate).toHaveBeenLastCalledWith([1]);
  r.wires[0].emit('reconnect');
  r.tick(5000);
  expect(r.admitted).toEqual([[1, 2], [2]]);
});

test('a closed/refused wire waits sixty seconds; rollover waits five', () => {
  const r = rig();
  r.wires[0].readyState = 2;
  r.wires[0].emit('error');
  r.tick(59_999);
  expect(r.wires).toHaveLength(1);
  r.tick(60_000);
  expect(r.wires).toHaveLength(2);
  r.wires[1].emit('reconnect');
  r.tick(64_999);
  expect(r.wires).toHaveLength(2);
  r.tick(65_000);
  expect(r.wires).toHaveLength(3);
});

test('quiet wires recover; old handles and stopped timers have no authority', () => {
  const r = rig();
  r.tick(65_001);
  expect(r.wires[0].readyState).toBe(2);
  r.tick(70_001);
  r.wires[0].emit('market', { market_id: 1, invalidation: true, terminal: false });
  expect(r.onInvalidate).not.toHaveBeenCalled();
  r.controller.stop();
  r.tick(200_000);
  r.wires[1].emit('open');
  expect(r.wires).toHaveLength(2);
  expect(r.onInvalidate).not.toHaveBeenCalled();
});

test('terminal closure delivers final reconciliation and never resubscribes ended contracts', () => {
  const r = rig();
  r.wires[0].emit('closed', { reason: 'settled', market_ids: [1, 2] });
  expect(r.onInvalidate).toHaveBeenLastCalledWith([1, 2]);
  r.tick(60_000);
  r.tick(120_000);
  expect(r.wires).toHaveLength(1);
});

test.each([[], [0], [-1], [1.5], Array.from({ length: 51 }, (_, i) => i + 1)].map(ids => ({ ids })))('rejects an invalid request set $ids', ({ ids }) => {
  expect(rig(ids).wires).toHaveLength(0);
});

test('transport construction failure gets a bounded retry', () => {
  let at = 0;
  const open = jest.fn(() => { throw new Error('no transport'); });
  const controller = createMarketStreamController({ marketIds: [1], now: () => at, open, onInvalidate: jest.fn() });
  controller.start();
  at = 59999; controller.tick();
  expect(open).toHaveBeenCalledTimes(1);
  at = 60000; controller.tick();
  expect(open).toHaveBeenCalledTimes(2);
});
