'use strict';
// node --test tools/live-speed-lab/passive-recorder/test_challenge_units.cjs
// Browser-free, network-free units for the DARK clock challenge driver:
// injected clock (virtual collector C), injected connection, real journal.
const test = require('node:test');
const assert = require('node:assert');
const fs = require('fs');
const os = require('os');
const path = require('path');
const crypto = require('crypto');
const {createChallengeDriver, validateChallenge, CEILINGS, SCHEMA, SCHEMA_SHA256, compact} = require('./challenge.cjs');
const {createJournal} = require('./journal.cjs');

const T0_MONO = 100000; // collector mono at T0 in the virtual clock
const tmp = () => fs.mkdtempSync(path.join(os.tmpdir(), 'challenge-test-'));
const tok = i => i.toString(16).padStart(16, '0');
const CASE = 'case20261030a';
const REPLY = `cmr_${CASE}`;

function cfgFor(n, {count = 760, first = -5000, slot = 250, deadline = 150, limits = {}} = {}) {
  return {case: CASE, reply_channel: REPLY,
    roster: Array.from({length: n}, (_, i) => ({token: tok(i + 1), channel: `cm_${CASE}_${tok(i + 1)}`, run: `run${i}`, pid: 100 + i, role: i ? 'polymarket' : 'kalshi'})),
    slots: {first_offset_ms: first, slot_ms: slot, count}, deadline_ms: deadline,
    limits: {connect_timeout_ms: 2000, max_wire_bytes_per_incarnation: CEILINGS.max_wire_bytes_per_incarnation, max_wire_bytes_session: CEILINGS.max_wire_bytes_session,
      max_read_overshoot_bytes: 65536, max_journal_bytes_per_incarnation: CEILINGS.max_journal_bytes_per_incarnation, ...limits}};
}

// Virtual collector clock + timer queue. Microtasks are flushed between timers.
function harness() {
  const st = {t: T0_MONO - 30000, q: []};
  const clock = {mono: () => st.t, wall: () => 1.7e12 + st.t, sinceT0: m => [m - T0_MONO, m - T0_MONO]};
  const setTimer = (fn, ms) => { const h = {at: st.t + Math.max(0, ms), fn, seq: st.q.length}; st.q.push(h); return h; };
  const flush = async () => { for (let i = 0; i < 5; i++) await new Promise(r => setImmediate(r)); };
  async function runUntil(target, hook) {
    for (;;) {
      await flush();
      st.q.sort((a, b) => a.at - b.at || a.seq - b.seq);
      const h = st.q[0];
      if (!h || h.at > target) { st.t = Math.max(st.t, target); await flush(); return; }
      st.q.shift();
      st.t = Math.max(st.t, h.at);
      if (hook) hook(st.t);
      h.fn();
    }
  }
  return {st, clock, setTimer, runUntil, flush};
}

// A fake producer behind an injected connection. `behave(req)` returns
// {delay, mutate(replyObj)->obj|string|null, extra: [..]} per request.
function fakeConnection(h, {behave = () => ({delay: 5}), connectDelay = 10, fail = null, neverResolveNotify = false} = {}) {
  const log = {notifies: [], listened: [], closed: 0, connectArgs: null};
  let api = null;
  const connect = async args => {
    log.connectArgs = args;
    await new Promise((resolve, reject) => h.setTimer(() => (fail ? reject(new Error(fail)) : resolve()), connectDelay));
    api = args;
    return {
      listen: async ch => { log.listened.push(ch); },
      notify: (ch, payload) => {
        log.notifies.push({ch, payload, at: h.st.t});
        const req = JSON.parse(payload);
        const b = behave({...req, k: req.slot}) || {};
        const send = (delay, obj) => h.setTimer(() => api.onNotification(REPLY, typeof obj === 'string' ? obj : compact(obj)), delay);
        const rosterPid = 100 + parseInt(req.tok, 16) - 1;
        // A clock_marker/1 reply, as the producer writes it (sorted compact JSON).
        const reply = {v: 1, k: 'm', case: req.case, tok: req.tok, run: req.run, pid: rosterPid, slot: req.slot, nonce: req.nonce,
          i: req.slot + 1, rx: req.slot + 1, lo: 86400.123456 + req.slot, hi: 86400.123519 + req.slot, q: 1e-06, f: {big: 0, bad: 0, foreign: 0, dup: 0, ord: 0, q: 0, drop: 0}};
        if (b.delay !== null && b.delay !== undefined) {
          const out = b.mutate ? b.mutate({...reply}) : reply;
          if (out !== null) send(b.delay, out);
        }
        for (const [delay, obj] of b.extra || []) send(delay, typeof obj === 'function' ? obj({...reply}) : obj);
        return neverResolveNotify ? new Promise(() => {}) : Promise.resolve();
      },
      wire: () => ({sent_bytes: 0, received_bytes: 0}),
      close: async () => { log.closed++; },
    };
  };
  return {connect, log, closeFromServer: (reason, e) => api && api.onClose(reason, e)};
}

function setup(n, opts = {}, connOpts = {}) {
  const h = harness();
  const dir = tmp();
  const journal = createJournal({dir, limits: {max_record_bytes: 262144, max_saved_bytes: 200_000_000, reserved_stop_bytes: 4_000_000}, onExhausted: () => {}});
  const fc = fakeConnection(h, connOpts);
  const driver = createChallengeDriver({cfg: cfgFor(n, opts), connect: fc.connect, clock: h.clock, journal, setTimer: h.setTimer});
  const lines = () => { journal.close(); return fs.readFileSync(path.join(dir, 'records.jsonl'), 'utf8').trim().split('\n').filter(Boolean).map(l => JSON.parse(l)); };
  return {h, journal, fc, driver, lines};
}

const exchanges = ls => ls.filter(l => l.kind === 'challenge-exchange');

test('validate: a full 16-incarnation, 760-slot challenge is accepted', () => {
  const r = [];
  validateChallenge(cfgFor(16), m => r.push(m));
  assert.deepStrictEqual(r, []);
});

for (const [name, mut, re] of [
  ['17 incarnations', c => { for (let i = 0; i < 16; i++) c.roster.push({...c.roster[0], token: tok(200 + i), channel: `cm_${CASE}_${tok(200 + i)}`}); }, /1\.\.16 incarnations/],
  ['761 slots', c => { c.slots.count = 761; }, /at most 760/],
  ['slot faster than 250 ms', c => { c.slots.slot_ms = 100; }, /at least 250/],
  ['deadline not below the slot', c => { c.deadline_ms = 250; }, /below slot_ms/],
  ['a slot after the acquisition end', c => { c.slots.first_offset_ms = 0; }, /inside the acquisition window/],
  ['a slot before the acquisition start', c => { c.slots.first_offset_ms = -5250; }, /inside the acquisition window/],
  ['wire per incarnation above the ceiling', c => { c.limits.max_wire_bytes_per_incarnation = CEILINGS.max_wire_bytes_per_incarnation + 1; }, /at most 2097152/],
  ['connect bound above 2 s', c => { c.limits.connect_timeout_ms = 2001; }, /at most 2000/],
  ['channel not derived from case and token', c => { c.roster[0].channel = `cm_${CASE}_${tok(7)}`; }, /must be cm_<case>_<token>/],
  ['reply channel not derived from the case', c => { c.reply_channel = 'cmr_othercase1'; }, /must be cmr_<case>/],
  ['case outside the producer pattern', c => { c.case = 'Bad-Case'; c.reply_channel = 'cmr_Bad-Case'; }, /grant.challenge.case/],
  ['duplicate token', c => { c.roster[1] = {...c.roster[0]}; }, /duplicate/],
  ['unknown key', c => { c.retry = 1; }, /unknown retry/],
  ['missing limit', c => { delete c.limits.max_read_overshoot_bytes; }, /missing max_read_overshoot_bytes/],
  ['zero pid', c => { c.roster[0].pid = 0; }, /pid: positive integer/],
]) {
  test(`validate refuses: ${name}`, () => {
    const c = cfgFor(2);
    mut(c);
    const r = [];
    validateChallenge(c, m => r.push(m));
    assert.match(r.join('\n'), re);
  });
}

test('driver: 2 incarnations x 760 slots, timely replies -> COMPLETE, S < R on C, one line per exchange', async () => {
  const {h, driver, lines, fc} = setup(2);
  const started = driver.start();
  await h.runUntil(T0_MONO + 185000);
  await started;
  await driver.stop('deadline');
  const s = driver.summary();
  const ls = lines();
  assert.strictEqual(s.status, 'COMPLETE', JSON.stringify(s.holes));
  assert.deepStrictEqual(s.domains.map(d => [d.sent, d.timely, d.late, d.no_reply, d.skipped]), [[760, 760, 0, 0, 0], [760, 760, 0, 0, 0]]);
  const ex = exchanges(ls);
  assert.strictEqual(ex.length, 1520);
  assert.ok(ex.every(e => e.outcome === 'reply' && e.S < e.R && e.R - e.S <= 150));
  // Slots sit on the predeclared grid, T0-5 s .. T0+184.75 s, never after +185 s.
  assert.strictEqual(Math.min(...ex.map(e => e.s_since_t0_ms[0])), -5000);
  assert.strictEqual(Math.max(...ex.map(e => e.s_since_t0_ms[0])), 184750);
  assert.ok(fc.log.notifies.every(x => Buffer.byteLength(x.payload) <= SCHEMA.request.max_bytes));
  // Each request is exactly the producer's request shape.
  assert.ok(fc.log.notifies.every(x => JSON.stringify(Object.keys(JSON.parse(x.payload))) === JSON.stringify(SCHEMA.request.keys)));
  assert.deepStrictEqual(fc.log.listened, [REPLY]);
  assert.strictEqual(fc.log.connectArgs.max_pending, 2);
  assert.strictEqual(fc.log.connectArgs.wire_cap_bytes, 2 * 2097152 + 1048576);
  // Raw reply retained verbatim, with the producer marker untouched.
  assert.deepStrictEqual([JSON.parse(ex[0].raw).lo, JSON.parse(ex[0].raw).hi], [86400.123456, 86400.123519]);
});

test('driver: a reply after the 150 ms deadline is retained as late, never as timely coverage', async () => {
  const {h, driver, lines} = setup(1, {count: 8, first: 0}, {behave: req => ({delay: req.k === 3 ? 300 : 5})});
  const started = driver.start();
  await h.runUntil(T0_MONO + 3000);
  await started;
  await driver.stop('deadline');
  const ex = exchanges(lines()).filter(e => e.k === 3);
  // The next slot expires it (no-reply), then the late reply lands as its own line.
  assert.deepStrictEqual(ex.map(e => e.outcome), ['no-reply', 'late-reply']);
  assert.strictEqual(ex[1].R - ex[1].S, 300);
  const s = driver.summary();
  assert.strictEqual(s.status, 'INCOMPLETE');
  assert.deepStrictEqual([s.domains[0].timely, s.domains[0].late, s.domains[0].no_reply], [7, 1, 1]);
});

test('driver: a reply late but before expiry is still late, not timely', async () => {
  const {h, driver, lines} = setup(1, {count: 4, first: 0, deadline: 150}, {behave: req => ({delay: req.k === 1 ? 160 : 5})});
  const started = driver.start();
  await h.runUntil(T0_MONO + 2000);
  await started;
  await driver.stop('deadline');
  const ex = exchanges(lines()).filter(e => e.k === 1);
  assert.deepStrictEqual(ex.map(e => e.outcome), ['late-reply']);
});

test('driver: spoofed, replayed, wrong-binding, malformed and oversize replies are counted drops, never exchanges', async () => {
  const bad = [
    [1, r => ({...r, nonce: 'f'.repeat(32)})], // wrong nonce
    [1, r => ({...r, pid: 999})], // wrong pid
    [1, r => ({...r, run: 'other'})], // stale run
    [1, r => ({...r, tok: tok(42)})], // unrostered token
    [1, r => ({...r, case: 'othercase1'})], // other case
    [1, r => ({...r, lo: 9, hi: 3})], // inverted marker
    [1, r => ({...r, q: 1e-3})], // wrong quantum
    [1, r => ({...r, i: 0})], // bad ordinal
    [1, r => ({...r, f: {...r.f, nope: 1}})], // unknown fault counter
    [1, r => ({...r, slot: 5})], // a slot never sent
    [1, r => { const x = {...r}; delete x.rx; return x; }], // wrong keys
    [1, r => ({...r, k: 'zz'})], // unknown kind
    [1, () => '{"v":1,"v":1}'], // duplicate key
    [1, () => '{not json'],
    [1, r => compact({...r, nonce: r.nonce + 'x'.repeat(600)})], // oversize
  ];

  const {h, driver, lines} = setup(1, {count: 3, first: 0}, {behave: req => (req.k === 0 ? {delay: 20, extra: [...bad, [30, r => r] /* replay after accept */]} : {delay: 5})});
  const started = driver.start();
  await h.runUntil(T0_MONO + 1500);
  await started;
  await driver.stop('deadline');
  const s = driver.summary();
  const ex = exchanges(lines());
  assert.deepStrictEqual(ex.map(e => [e.k, e.outcome]), [[0, 'reply'], [1, 'reply'], [2, 'reply']]);
  // The accepted slot-0 exchange is the genuine reply (20 ms), not any earlier bad one (1 ms).
  assert.strictEqual(ex[0].R - ex[0].S, 20);
  const totalDrops = Object.values(s.drops).reduce((a, b) => a + b, 0);
  assert.strictEqual(totalDrops, bad.length + 1);
  for (const k of ['reply-unmatched', 'reply-wrong-binding', 'reply-unrostered', 'reply-wrong-case', 'reply-bad-marker', 'reply-wrong-keys', 'reply-unknown-kind', 'reply-malformed', 'reply-oversize', 'reply-duplicate']) assert.ok(s.drops[k] >= 1, k);
  assert.strictEqual(s.status, 'INCOMPLETE', 'any drop keeps the challenge from COMPLETE');
});

test('driver: a foreign channel is dropped; the collector receipt R is the clock at callback entry', async () => {
  const {h, driver, lines, fc} = setup(1, {count: 2, first: 0});
  const started = driver.start();
  await h.runUntil(T0_MONO + 100);
  await started;
  driver.onNotification('cmr_othercase1', '{}');
  await h.runUntil(T0_MONO + 1000);
  await driver.stop('deadline');
  assert.strictEqual(driver.summary().drops['foreign-channel'], 1);
  const ex = exchanges(lines());
  for (const e of ex) assert.strictEqual(e.R, e.S + 5, 'R is the virtual clock when the reply callback was entered');
  assert.ok(fc.log.notifies.length === 2);
});

test('driver: a late timer never sends the slots it missed (no catch-up burst)', async () => {
  const {h, driver, lines, fc} = setup(1, {count: 40, first: 0});
  const started = driver.start();
  await h.runUntil(T0_MONO + 1000);
  await started;
  // Freeze the collector's loop for 2.6 s: timers fire late, once.
  const pending = h.st.q.filter(x => x.at <= T0_MONO + 3600);
  for (const p of pending) p.at = Math.max(p.at, T0_MONO + 3600);
  h.st.t = T0_MONO + 3600;
  await h.runUntil(T0_MONO + 10500);
  await driver.stop('deadline');
  const s = driver.summary();
  const sentKs = fc.log.notifies.map(x => JSON.parse(x.payload).slot);
  assert.deepStrictEqual(sentKs, [...new Set(sentKs)].sort((a, b) => a - b), 'each slot at most once, in order');
  assert.ok(s.domains[0].gaps.some(g => g[2] === 'timer-late'));
  assert.strictEqual(s.domains[0].sent + s.domains[0].skipped, 40);
  // No more than one request leaves per tick: the catch-up tick sends one slot.
  const at3600 = fc.log.notifies.filter(x => x.at === T0_MONO + 3600);
  assert.strictEqual(at3600.length, 1);
  // Only the exchange whose reply was frozen with the loop can be late.
  assert.ok(exchanges(lines()).filter(e => e.outcome !== 'reply').length <= 2);
});

test('driver: a connect that misses its 2 s bound is UNAVAILABLE; the late connection is closed, never used', async () => {
  const {h, driver, fc} = setup(1, {count: 10, first: 0}, {connectDelay: 2500});
  const st = driver.start();
  await h.runUntil(T0_MONO - 30000 + 2100);
  assert.strictEqual(await st, 'UNAVAILABLE');
  await h.runUntil(T0_MONO + 3000);
  await driver.stop('deadline');
  const s = driver.summary();
  assert.strictEqual(s.status, 'UNAVAILABLE');
  assert.ok(s.holes.includes('challenge-connect-timeout'));
  assert.strictEqual(fc.log.notifies.length, 0);
  assert.ok(fc.log.closed >= 1, 'the connection that arrived late was closed');
});

test('driver: a failed connect is a hole, no retry', async () => {
  const {h, driver, fc} = setup(1, {count: 4, first: 0}, {fail: 'ECONNREFUSED'});
  const started = driver.start();
  await h.runUntil(T0_MONO + 2000);
  await started;
  await driver.stop('deadline');
  const s = driver.summary();
  assert.strictEqual(s.status, 'UNAVAILABLE');
  assert.ok(s.holes.includes('challenge-connect-failed'));
  assert.strictEqual(fc.log.notifies.length, 0);
});

test('driver: a transport that drops mid-run leaves gaps from then on, never a reconnect', async () => {
  const {h, driver, fc} = setup(1, {count: 20, first: 0});
  const started = driver.start();
  await h.runUntil(T0_MONO + 2000);
  await started;
  fc.closeFromServer('error', Object.assign(new Error('x'), {code: 'ECONNRESET'}));
  await h.runUntil(T0_MONO + 6000);
  await driver.stop('deadline');
  const s = driver.summary();
  assert.strictEqual(s.driver_state, 'TRANSPORT-DOWN');
  assert.strictEqual(s.status, 'INCOMPLETE');
  assert.ok(s.holes.includes('challenge-transport-error'));
  assert.ok(s.domains[0].gaps.some(g => g[2] === 'transport-down'));
  assert.strictEqual(fc.log.notifies.filter(x => x.at > T0_MONO + 2000).length, 0);
});

test('driver: a notify that never completes bounds pending requests at the roster size', async () => {
  const {h, driver, fc} = setup(3, {count: 12, first: 0}, {neverResolveNotify: true, behave: () => ({delay: null})});
  const started = driver.start();
  await h.runUntil(T0_MONO + 3500);
  await started;
  await driver.stop('deadline');
  const s = driver.summary();
  assert.strictEqual(s.counters.max_pending_notifies, 3);
  assert.strictEqual(fc.log.notifies.length, 3);
  assert.ok(s.domains.every(d => d.gaps.some(g => g[2] === 'transport-queue-full')));
});

test('driver: the journal cap per incarnation stops challenges to that incarnation only', async () => {
  const {h, driver} = setup(2, {count: 40, first: 0, limits: {max_journal_bytes_per_incarnation: 4000}}, {behave: req => ({delay: 5, mutate: r => (req.t === tok(1) ? r : r)})});
  const started = driver.start();
  await h.runUntil(T0_MONO + 10500);
  await started;
  await driver.stop('deadline');
  const s = driver.summary();
  assert.ok(s.domains.every(d => d.stopped && d.stopped.reason === 'journal-cap'));
  assert.ok(s.domains.every(d => d.journal_bytes <= 4000 + 1000), 'at most one line past the cap');
  assert.ok(s.holes.includes('challenge-domain-stopped:journal-cap'));
});

test('driver: stop expires outstanding requests, sends nothing after, and does not journal replies after the stop', async () => {
  const {h, driver, lines, fc} = setup(1, {count: 20, first: 0}, {behave: () => ({delay: 100})});
  const started = driver.start();
  await h.runUntil(T0_MONO + 1050);
  await started;
  await driver.stop('cancelled');
  const n = fc.log.notifies.length;
  await h.runUntil(T0_MONO + 5000);
  const s = driver.summary();
  assert.strictEqual(fc.log.notifies.length, n);
  assert.ok(s.counters.after_stop >= 1);
  const ex = exchanges(lines());
  assert.strictEqual(ex[ex.length - 1].outcome, 'no-reply-at-stop');
});

test('schema: the vendored clock_marker/1 fixture is byte-identical to Authority\'s pinned one', () => {
  const bytes = fs.readFileSync(path.join(__dirname, 'clock_marker_10090_schema.json'));
  assert.strictEqual(crypto.createHash('sha256').update(bytes).digest('hex'), SCHEMA_SHA256);
  assert.strictEqual(SCHEMA.schema, 'clock_marker/1');
});

test('driver: a rostered bind is journaled; an unrostered bind is a coverage hole; a producer end stops that incarnation', async () => {
  const bind = r => ({v: 1, k: 'bind', case: CASE, tok: r.tok, run: r.run, pid: r.pid, ch: `cm_${CASE}_${r.tok}`, listen: 1, clock: 'time.monotonic', mono: 86400.5,
    exp: 1.8e9, slots: 760, dyno: 'worker-ws.1', rel: 'v1', commit: 'c'.repeat(40), boot: 'b'});
  const end = r => ({v: 1, k: 'end', case: CASE, tok: r.tok, run: r.run, pid: r.pid, why: 'MARKER_CAP', i: 3, rx: 3, f: {big: 0}, pb: 1, wb: 2});
  const {h, driver, lines, fc} = setup(1, {count: 12, first: 0}, {behave: req => (req.slot === 0 ? {delay: 5, extra: [[1, r => bind(r)], [2, r => bind({...r, tok: tok(77)})]]} : req.slot === 3 ? {delay: 5, extra: [[20, r => end(r)]]} : {delay: 5})});
  const started = driver.start();
  await h.runUntil(T0_MONO + 3500);
  await started;
  await driver.stop('deadline');
  const s = driver.summary();
  const ls = lines();
  assert.strictEqual(ls.filter(l => l.kind === 'challenge-bind').length, 1);
  assert.strictEqual(ls.filter(l => l.kind === 'challenge-end').length, 1);
  assert.strictEqual(s.drops['bind-unrostered'], 1);
  assert.ok(s.holes.includes('challenge-unrostered-incarnation'));
  assert.deepStrictEqual(s.domains[0].stopped.reason, 'producer-end:MARKER_CAP');
  assert.strictEqual(s.domains[0].sent, 4, 'no request after the producer said it ended');
  assert.strictEqual(fc.log.notifies.length, 4);
});
