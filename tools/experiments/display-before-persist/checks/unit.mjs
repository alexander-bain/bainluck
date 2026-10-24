import test from 'node:test';
import assert from 'node:assert/strict';
import { Pipeline, hash } from '../src/pipeline.mjs';
import { createModel } from '../src/client.mjs';

// Fully synthetic. These values are not a recorded market or production replay.
const frame = (seq, p = 0.5) => ({
  status: 'live', event_id: 1, seq, p, sources: { kalshi: { value: p } },
});

await test('display-first publishes before an unresolved persistence promise', async () => {
  let resolveCommit;
  const commit = new Promise(resolve => { resolveCommit = resolve; });
  const messages = [];
  const pipeline = new Pipeline({
    run: 'synthetic-unit', arm: 'display-first',
    store: { persist: () => commit }, publish: message => messages.push(message),
  });
  const payload = frame(1);
  pipeline.offer(payload);
  payload.p = 0.9;
  payload.sources.kalshi.value = 0.9;
  assert.equal(messages.length, 1);
  assert.equal(messages[0].state, 'pending');
  assert.equal(messages[0].payload.p, 0.5);
  assert.equal(messages[0].payload.sources.kalshi.value, 0.5);
  resolveCommit({ hash: messages[0].hash });
  const result = await pipeline.finish();
  assert.equal(result.durable, 1);
  assert.equal(messages[1].state, 'durable');
});

await test('commit-first publishes nothing until persistence resolves', async () => {
  let resolveCommit;
  const commit = new Promise(resolve => { resolveCommit = resolve; });
  const messages = [];
  const pipeline = new Pipeline({
    run: 'synthetic-unit', arm: 'commit-first',
    store: { persist: () => commit }, publish: message => messages.push(message),
  });
  pipeline.offer(frame(1));
  assert.equal(messages.length, 0);
  resolveCommit({ hash: hash(frame(1)) });
  await pipeline.finish();
  assert.equal(messages.length, 1);
  assert.equal(messages[0].state, 'durable');
});

await test('a current durability ACK is status-only, never a new chart point', () => {
  const model = createModel();
  model.reset('epoch', 'run');
  const payload = frame(1);
  const identity = { run: 'run', epoch: 'epoch', event: 1, seq: 1, hash: hash(payload) };
  model.accept({ ...identity, kind: 'publication', state: 'pending', payload });
  const result = model.accept({ ...identity, kind: 'persistence', state: 'durable' });
  assert.equal(result.statusOnly, true);
  assert.equal(model.state().points.length, 1);
  assert.equal(model.state().current.p, 0.5);
  assert.equal(model.state().current.state, 'durable');
});
