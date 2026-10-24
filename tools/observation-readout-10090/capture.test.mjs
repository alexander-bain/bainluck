import test from 'node:test';
import assert from 'node:assert/strict';
import { analyzeObservation, captureObservation } from './capture.mjs';

const iso = ms => new Date(Date.UTC(2026, 9, 21) + ms).toISOString();
const component = (ms = 0, count = 1, extra = {}) => ({ eventId: '42', observedAt: iso(ms),
  count: String(count), delivery: 'committed', visible: true, disclosureOpen: true,
  disclosureVisible: true, ...extra });
const read = (t, value = component(), end = t) => ({ beginMs: t, endMs: end, components: [value] });
const capture = (samples, endMs = samples.at(-1)?.endMs ?? 0) => ({ eventId: '42', samples, endMs });

test('5-second completed left interval plus 49-second trailing interval reports 49-second lower bound', () => {
  const samples = Array.from({ length: 541 }, (_, i) => read(i * 100, component(i < 50 ? 0 : 1_000, i < 50 ? 1 : 2)));
  const result = analyzeObservation(capture(samples));
  assert.equal(result.qualification, 'QUALIFIED');
  assert.equal(result.longest.lowerMs, 49_000);
  assert.equal(result.longest.upperMs, 49_100);
  assert.equal(result.longest.kind, 'right-censored');
  assert.equal(result.intervals[0].upperMs, 5_000);
});

test('a no-advancement recording includes both edges; initial observation is not an arrival', () => {
  const result = analyzeObservation(capture([read(0, component(), 10), read(100), read(200)], 250));
  assert.equal(result.qualification, 'QUALIFIED');
  assert.equal(result.advances.length, 0);
  assert.deepEqual(result.longest, { kind: 'both-censored', lowerMs: 190, upperMs: 250, isWholeSampleQualified: true });
});

test('subsecond updates in the same printed second are distinct; precision stays exact', () => {
  const values = [100, 200, 300].map((ms, i) => read(i * 100, component(ms, i + 1, { delivery: 'dnpl' })));
  const result = analyzeObservation(capture(values));
  assert.equal(result.qualification, 'QUALIFIED');
  assert.equal(result.advances.length, 2);
  assert.equal(result.selected[1].observedAt, '2026-10-21T00:00:00.200Z');
  assert.equal(result.advances[0].delivery, 'dnpl');
  assert.deepEqual([result.advances[0].lowerMs, result.advances[0].upperMs], [0, 100]);
});

test('raw submillisecond timestamps are retained but comparison matches millisecond UI counter', () => {
  const result = analyzeObservation(capture([
    read(0, component(0, 1, { observedAt: '2026-10-21T00:00:00.000001Z' })),
    read(100, component(0, 1, { observedAt: '2026-10-21T00:00:00.000002Z' })),
  ]));
  assert.equal(result.qualification, 'QUALIFIED');
  assert.equal(result.advances.length, 0);
  assert.equal(result.selected[1].observedAt, '2026-10-21T00:00:00.000002Z');
});

test('rollback and restoration at old highwater are not forward advancement', () => {
  const result = analyzeObservation(capture([
    read(0, component(300, 5)), read(100, component(200, 5)),
    read(200, component(300, 5)), read(300, component(400, 6)), read(400, component(400, 6)),
  ]));
  assert.equal(result.qualification, 'QUALIFIED');
  assert.equal(result.advances.length, 1);
  assert.equal(result.rollbacks.length, 1);
  assert.equal(result.advances[0].observedAt, iso(400));
  assert.equal(result.intervals[0].upperMs, 300);
});

test('count leap marks missed intermediate forward updates; it cannot qualify the whole maximum', () => {
  const result = analyzeObservation(capture([read(0), read(100, component(300, 4)), read(200, component(300, 4))]));
  assert.equal(result.qualification, 'UNQUALIFIED');
  assert.equal(result.issues.find(i => i.kind === 'missed-forward-updates').detail, 2);
  assert.equal(result.longest.isWholeSampleQualified, false);
});

test('counter proves an unseen forward update even when displayed value has rolled back', () => {
  const result = analyzeObservation(capture([read(0, component(300, 3)), read(100, component(200, 4))]));
  assert.equal(result.qualification, 'UNQUALIFIED');
  assert.ok(result.issues.some(i => i.kind === 'unseen-forward-update'));
  assert.equal(result.advances.length, 0);
});

test('failed/invalid reads and slow gaps remain in evidence and disqualify the whole maximum', () => {
  for (const bad of [
    { beginMs: 100, endMs: 150, error: 'read timeout' },
    read(100, component(0, 1, { observedAt: '2026-02-30T00:00:00Z' })),
    read(100, component(0, 1, { delivery: 'enabled' })),
    read(100, component(0, 1, { visible: false })),
  ]) {
    const result = analyzeObservation(capture([read(0), bad, read(200)]));
    assert.equal(result.qualification, 'UNQUALIFIED');
    assert.equal(result.samplesRead, 3);
    assert.ok(result.issues.length);
  }
  const gap = analyzeObservation(capture([read(0), read(1_000)]));
  assert.equal(gap.qualification, 'UNQUALIFIED');
  assert.ok(gap.issues.some(i => i.kind === 'recorder-gap'));
});

test('stalled recorder yields NO_RESULT, not a fabricated user pause', () => {
  for (const sample of [capture([], 180_000), capture([read(0, component(), 180_000)], 180_000), capture([read(0), read(0)], 0)]) {
    const result = analyzeObservation(sample);
    assert.equal(result.qualification, 'NO_RESULT');
    assert.equal(result.longest, null);
  }
});

test('full-screen read selects exact event, never merges duplicates or another event', () => {
  const unrelated = { ...component(), eventId: '99' };
  const one = read(100); one.components.push(unrelated);
  assert.equal(analyzeObservation(capture([read(0), one])).qualification, 'QUALIFIED');
  const fullscreen = read(100); fullscreen.components.push(component(0, 1, { visible: false }));
  assert.equal(analyzeObservation(capture([read(0), fullscreen])).qualification, 'QUALIFIED');
  const duplicates = read(100); duplicates.components.push(component());
  const duplicateResult = analyzeObservation(capture([read(0), duplicates, read(200)]));
  assert.ok(duplicateResult.issues.some(i => i.kind === 'duplicate-visible-target'));
  assert.equal(duplicateResult.qualification, 'UNQUALIFIED');
  const swapped = analyzeObservation(capture([read(0), read(100, unrelated), read(200)]));
  assert.ok(swapped.issues.some(i => i.kind === 'no-visible-target'));
});

test('read envelopes bound arrivals and trailing silence; delayed reads are not delivery latency', () => {
  const result = analyzeObservation(capture([read(0, component(), 20),
    read(100, component(100, 2), 140), read(200, component(100, 2), 220)], 250));
  assert.deepEqual(result.advances.map(({ lowerMs, upperMs }) => [lowerMs, upperMs]), [[0, 140]]);
  assert.equal(result.intervals.at(-1).lowerMs, 60);
  assert.equal(result.intervals.at(-1).upperMs, 250);
  assert.equal('deliveryLatencyMs' in result, false);
});

test('bounded capture uses only awaited CUA DOM reads with a remaining-duration timeout and 100ms pacing', async () => {
  let clock = 0, active = 0, peak = 0;
  const timeouts = [];
  const tab = { playwright: { getByTestId(id) {
    assert.equal(id, 'live-connection-status');
    return { async evaluateAll(fn, arg, options) {
      assert.equal(typeof fn, 'function'); assert.equal(arg, undefined); timeouts.push(options.timeoutMs);
      active++; peak = Math.max(peak, active); clock += 10;
      active--; return [component()];
    } };
  } } };
  const result = await captureObservation(tab, { eventId: 42, durationMs: 350,
    now: () => clock, wait: async ms => { clock += ms; } });
  assert.deepEqual(result.samples.map(s => s.beginMs), [0, 100, 200, 300]);
  assert.deepEqual(timeouts, [350, 250, 150, 50]);
  assert.equal(result.endMs, 350);
  assert.equal(result.overrunMs, 0);
  assert.equal(peak, 1); assert.equal(active, 0);
  assert.equal(result.analysis.qualification, 'QUALIFIED');
});

test('an awaited timeout or overrun is recorded and no request is abandoned', async () => {
  let clock = 0, pending = false;
  const tab = { playwright: { getByTestId() { return { async evaluateAll() {
    pending = true; clock = 70; pending = false; throw new Error('CUA timeout');
  } }; } } };
  const result = await captureObservation(tab, { eventId: 42, durationMs: 50, now: () => clock, wait: async () => {} });
  assert.equal(pending, false);
  assert.equal(result.overrunMs, 20);
  assert.equal(result.samples[0].error, 'CUA timeout');
  assert.equal(result.analysis.qualification, 'NO_RESULT');
});


test('closed or hidden disclosure is metadata-only and never qualifies the visible timestamp metric', () => {
  for (const visibility of [
    { disclosureOpen: false, disclosureVisible: false },
    { disclosureOpen: true, disclosureVisible: false },
    { disclosureOpen: false, disclosureVisible: true },
    { disclosureOpen: true, disclosureVisible: null },
  ]) {
    const result = analyzeObservation(capture([
      read(0, component(0, 1, visibility)), read(100, component(100, 2, visibility)),
    ]));
    assert.equal(result.qualification, 'UNQUALIFIED');
    assert.equal(result.longest.isWholeSampleQualified, false);
    assert.equal(result.validSamples, 2, 'metadata remains available');
    assert.equal(result.issues.filter(i => i.kind === 'timestamp-disclosure-not-visible').length, 2);
  }
  const missing = component(); delete missing.disclosureOpen; delete missing.disclosureVisible;
  assert.equal(analyzeObservation(capture([read(0, missing), read(100, missing)])).qualification, 'UNQUALIFIED');
});
