'use strict';
// node --test tools/live-speed-lab/passive-recorder/test_receipt_units.cjs
// Browser-free units for the page receipt brackets: the in-page send/ack carry
// (page_hooks.cjs run in a vm with a scripted document clock), the journal's
// oversize marker keeping the receipt, the grant's challenge gate, and the
// reference reading of the brackets on a fast-headline / slow-chart case.
const test = require('node:test');
const assert = require('node:assert');
const crypto = require('crypto');
const fs = require('fs');
const os = require('os');
const path = require('path');
const vm = require('vm');
const hooks = require('./page_hooks.cjs');
const contract = require('./contract.cjs');
const {createJournal} = require('./journal.cjs');
const {receiptBounds} = require('./receipt_bounds_reference.cjs');
const {CEILINGS} = require('./challenge.cjs');

const tmp = () => fs.mkdtempSync(path.join(os.tmpdir(), 'receipt-test-'));
const sha = b => crypto.createHash('sha256').update(b).digest('hex');

// A page with a scripted performance.now(); each binding call is a deferred
// promise whose argument is serialized at call time, as CDP does.
function page({maxQueue = 8, maxAcks = 512, timeOrigin = 1.7e12, auto = 0} = {}) {
  const st = {now: 1000, auto};
  class FakeES {
    constructor(url) { this.url = url; this.withCredentials = false; this.readyState = 1; this.l = {}; }
    addEventListener(t, f) { (this.l[t] = this.l[t] || []).push(f); }
    close() {}
  }
  FakeES.CLOSED = 2;
  const calls = [];
  const window = {EventSource: FakeES, addEventListener() {},
    __passiveRecord: rec => new Promise((resolve, reject) => calls.push({rec: JSON.parse(JSON.stringify(rec)), resolve, reject}))};
  const document = {addEventListener() {}, visibilityState: 'visible', querySelector: () => null, querySelectorAll: () => []};
  const performance = {now: () => { const v = st.now; st.now += st.auto; return v; }, timeOrigin};
  const ctx = vm.createContext({window, document, performance, Date, Promise, Math, Map, Set, String, Object, Error, JSON,
    setInterval: () => 1, clearInterval() {}, innerWidth: 390, innerHeight: 844, scrollY: 0});
  vm.runInContext(`(${hooks.installPassiveEventSourceHook})(${JSON.stringify({binding: '__passiveRecord', maxQueue, maxAcks, maxDataChars: 1000, streamEvents: ['message']})})`, ctx);
  // Results cross the page boundary serialized, as page.evaluate returns them.
  const run = (fn, arg) => JSON.parse(JSON.stringify(vm.runInContext(`(${fn})(${arg === undefined ? '' : JSON.stringify(arg)})`, ctx)));
  const emit = rec => window.__passiveRecorderEmit(rec);
  const settle = () => new Promise(r => setImmediate(r));
  return {st, calls, window, run, emit, settle};
}

test('page: each record carries send_mono and time_origin; an ack rides the next record, never its own', async () => {
  const p = page();
  p.emit({kind: 'x', mono: 1000});
  p.st.now = 1005;
  p.calls[0].resolve();
  await p.settle();
  p.st.now = 1010;
  p.emit({kind: 'y', mono: 1010});
  assert.strictEqual(p.calls.length, 2, 'acks add no binding call');
  const [a, b] = p.calls.map(c => c.rec);
  assert.strictEqual(a.send_mono, 1000);
  assert.strictEqual(a.time_origin, 1.7e12);
  assert.strictEqual(a.acks, undefined);
  assert.deepStrictEqual(b.acks, [[1, 1005]]);
  assert.ok(b.acks[0][1] >= a.send_mono, 'ack after send in document time');
});

test('page: a delayed callback delays its ack; acks accumulate in order and are capped with a carried drop count', async () => {
  const p = page({maxAcks: 2});
  for (let i = 0; i < 4; i++) { p.st.now = 1000 + i; p.emit({kind: 'x', mono: p.st.now}); }
  // Resolve out of order and late: the ack time is when each resolved.
  p.st.now = 1500; p.calls[2].resolve(); await p.settle();
  p.st.now = 1600; p.calls[0].resolve(); await p.settle();
  p.st.now = 1700; p.calls[1].resolve(); await p.settle();
  p.st.now = 1800; p.emit({kind: 'z', mono: 1800});
  const z = p.calls[4].rec;
  assert.deepStrictEqual(z.acks, [[3, 1500], [1, 1600]]);
  assert.strictEqual(z.acks_dropped, 1, 'the third ack did not fit and is counted');
});

test('page: a rejected binding call gives no ack and counts an emit failure; a full queue drops before sending', async () => {
  const p = page({maxQueue: 1});
  p.emit({kind: 'a', mono: 1});
  p.emit({kind: 'b', mono: 2}); // queue full: dropped, no call
  assert.strictEqual(p.calls.length, 1);
  p.calls[0].reject(new Error('x'));
  await p.settle();
  p.emit({kind: 'c', mono: 3});
  const q = p.window.__passiveRecorderQueue;
  assert.strictEqual(q.emit_failures, 1);
  assert.strictEqual(q.dropped, 1);
  assert.strictEqual(p.calls[1].rec.acks, undefined);
  assert.strictEqual(p.calls[1].rec.page_seq, 3);
});

test('page: the stop return carries the acks still pending; one drain sweep carries those that resolve after it', async () => {
  const p = page();
  p.emit({kind: 'a', mono: 1});
  p.emit({kind: 'b', mono: 2});
  p.st.now = 10; p.calls[0].resolve(); await p.settle();
  const stop = p.run(hooks.stopDisplaySampler);
  assert.deepStrictEqual(stop.queue.acks, [[1, 10]]);
  p.st.now = 20; p.calls[1].resolve(); await p.settle();
  const drain = p.run(hooks.drainRecorderAcks);
  assert.deepStrictEqual(drain.acks, [[2, 20]]);
  assert.deepStrictEqual(p.run(hooks.drainRecorderAcks).acks, [], 'each ack is carried once');
});

test('page: a sample keeps its start (mono) and the bracket around the pinned read()', () => {
  const p = page({auto: 1});
  // The fake read stamps the document clock itself, so the bracket must enclose it.
  p.window.__readDisplayIdentity10090 = () => ({headline: {status: 'present'}, at: p.window.__now()});
  p.window.__now = () => { const v = p.st.now; p.st.now += p.st.auto; return v; };
  p.run(hooks.startDisplaySampler, {intervalMs: 100});
  const s = p.calls.map(c => c.rec).find(r => r.kind === 'sample');
  assert.ok(s, 'one sample emitted at start');
  assert.ok(s.mono < s.read_bracket[0] && s.read_bracket[0] < s.read_bracket[1] && s.read_bracket[1] < s.send_mono,
    JSON.stringify({mono: s.mono, read: s.read_bracket, send: s.send_mono}));
  assert.ok(s.read_bracket[0] < s.display_identity.at && s.display_identity.at < s.read_bracket[1], 'the bracket encloses the read itself');
  assert.deepStrictEqual(s.display_identity.headline, {status: 'present'});
});

test('journal: an oversize record keeps its collector receipt and acks in the marker; an oversize keep is dropped and counted', () => {
  const dir = tmp();
  const j = createJournal({dir, limits: {max_record_bytes: 400, max_saved_bytes: 100000, reserved_stop_bytes: 65536}, onExhausted: () => {}});
  j.append('page', {big: 'x'.repeat(1000)}, {recv: {mono: 12.5}, page_seq: 7, acks: [[6, 11.1]]});
  j.append('page', {big: 'x'.repeat(1000)}, {recv: {mono: 13}, acks: Array(200).fill([1, 1])});
  j.close();
  const lines = fs.readFileSync(path.join(dir, 'records.jsonl'), 'utf8').trim().split('\n').map(l => JSON.parse(l));
  assert.strictEqual(lines[0].kind, 'oversize');
  assert.deepStrictEqual(lines[0].kept, {recv: {mono: 12.5}, page_seq: 7, acks: [[6, 11.1]]});
  assert.strictEqual(lines[1].kept_dropped, true);
  assert.strictEqual(j.stats.oversize_kept_dropped, 1);
  assert.ok(lines.every(l => Buffer.byteLength(JSON.stringify(l)) + 1 <= 400));
});

function bundle(dir, {scope = 'local', challenge = undefined} = {}) {
  const origin = 'http://127.0.0.1:4633', t0 = Date.now() + 60000;
  const iso = ms => new Date(ms).toISOString();
  const pin = (name, v) => { const f = path.join(dir, name); fs.writeFileSync(f, JSON.stringify(v)); return {path: f, sha256: sha(fs.readFileSync(f))}; };
  const receipt = {source_sha: 'a'.repeat(40), release_receipt: pin('r.json', {r: 1})};
  const m = {schema: contract.MANIFEST_SCHEMA, case_id: 'c1', policy: pin('policy.json', {p: 1}),
    selection: {selected_at: iso(Date.now() - 1000), max_age_s: 3600, selected_by: 'test', inventory: {evidence: pin('inv.json', {i: 1}), order: [5], rejections: [], replacement_rule: 'none'}},
    event: {canonical_event_id: 5, members: [5, 9], contributing_sources: [{source: 'kalshi', contract: 'k', orientation: 'home'}]},
    owner_receipts: {backend: receipt, worker: receipt, frontend: receipt, authority: {incarnation: '3', namespace: '3b4f1a52-8d7e-4c1a-9f0e-2a6b5c4d3e21'}, preview_activation: pin('pa.json', {a: 1})},
    entry: {page_url: `${origin}/events/5`, api_origin: origin, readout_activation: 'none', expected_stream_url: `${origin}/api/events/5/stream?preview_protocol=authority-v3`, expected_stream_events: ['preview_open_v3']},
    trace: null,
    clock: {t0_utc: iso(Math.floor(t0 / 1000) * 1000), scoring: {start_offset_ms: 0, end_offset_ms: 180000}, acquisition: {start_offset_ms: -5000, end_offset_ms: 185000}, setup: {earliest_offset_ms: -120000, cutoff_offset_ms: -5000}},
    page: {viewport: {width: 390, height: 844}, held_pages: 1, require_document_visible: true, require_in_viewport: false}, cleanup: {custody: 'test'}};
  const mPath = path.join(dir, 'm.json');
  fs.writeFileSync(mPath, JSON.stringify(m));
  const mSha = sha(fs.readFileSync(mPath));
  const g = {schema: contract.GRANT_SCHEMA, grant_id: 'g1', issued_by: 'test', issued_at: iso(Date.now() - 1000), expires_at: iso(t0 + 600000), case_id: 'c1', manifest_sha256: mSha,
    allowed_origins: [origin], allowed_routes: [{origin, methods: ['GET'], path_prefix: '/', resource_types: ['*']}],
    limits: {max_request_attempts: 10, max_eventsource_constructions: 2, max_stream_attempts: 3, max_active_streams: 1, max_response_bytes: 1000000,
      max_request_bytes: 100000, max_record_bytes: 10000, max_saved_bytes: 1000000, reserved_stop_bytes: 100000, max_queue_records: 64, max_detail_requests: 0, received_overshoot_bytes: 65536},
    detail_requests: [], browser: {browser_channel: 'chromium', browser_mode: 'single-process', playwright_package_sha256: 'c'.repeat(64), browser_version: '140.0.7339.186'}};
  if (challenge !== undefined) g.challenge = challenge;
  const gPath = path.join(dir, 'g.json');
  fs.writeFileSync(gPath, JSON.stringify(g));
  return {manifest: mPath, manifestSha256: mSha, grant: gPath, grantSha256: sha(fs.readFileSync(gPath)), scope, now: Date.now()};
}
const goodChallenge = () => ({case: 'case20261030a', reply_channel: 'cmr_case20261030a',
  roster: [{token: '0123456789abcdef', channel: 'cm_case20261030a_0123456789abcdef', run: 'a1b2c3d4', pid: 11, role: 'kalshi'}],
  slots: {first_offset_ms: -5000, slot_ms: 250, count: 760}, deadline_ms: 150,
  limits: {connect_timeout_ms: 2000, max_wire_bytes_per_incarnation: CEILINGS.max_wire_bytes_per_incarnation, max_wire_bytes_session: CEILINGS.max_wire_bytes_session,
    max_read_overshoot_bytes: 65536, max_journal_bytes_per_incarnation: CEILINGS.max_journal_bytes_per_incarnation}});

test('contract: a grant without challenge validates exactly as before (driver inactive)', () => {
  assert.deepStrictEqual(contract.validateBundle(bundle(tmp())).refusals, []);
});
test('contract: a local grant naming a valid challenge validates', () => {
  assert.deepStrictEqual(contract.validateBundle(bundle(tmp(), {challenge: goodChallenge()})).refusals, []);
});
test('contract: production scope refuses any challenge (no transport admitted)', () => {
  const b = bundle(tmp(), {challenge: goodChallenge()});
  const r = contract.validateBundle({...b, scope: 'production'}).refusals.join('\n');
  assert.match(r, /grant.challenge: no challenge transport is admitted for production scope/);
});
test('contract: a malformed challenge refuses with every clause', () => {
  const c = goodChallenge();
  c.slots.count = 900; c.deadline_ms = 300;
  const r = contract.validateBundle(bundle(tmp(), {challenge: c})).refusals.join('\n');
  assert.match(r, /at most 760/);
  assert.match(r, /below slot_ms/);
});

// ---- fast headline, slow chart: the brackets on C contain every true read,
// and a chart >1 s late can never be read as under 1 s, however late the
// callbacks are. Document clock = C - OFF; OFF is unknown to the reader.
function simulate({d1 = () => 1, d2 = () => 1, stall = null} = {}) {
  const OFF = 12345.678, X = 50000, HEAD = X + 100, CHART = X + 1200;
  const toDoc = c => c - OFF;
  const recs = [];
  let lastRecv = -Infinity;
  const pendingAcks = [];
  for (let c = X - 2000; c < X + 4000; c += 100) {
    const r0 = c + 0.3, send = c + 0.8;
    let recv = Math.max(lastRecv, send + d1(c));
    if (stall && recv >= stall[0] && recv < stall[1]) recv = stall[1];
    lastRecv = recv;
    const ackC = recv + d2(c);
    const rec = {page_seq: recs.length + 1, time_origin: 1, recv, read_start: toDoc(r0), true_read: r0,
      headline_new: r0 >= HEAD, chart_new: r0 >= CHART, acks: pendingAcks.filter(a => toDoc(send) > a[1]).map(a => [a[0], a[1]])};
    for (const a of rec.acks) pendingAcks.splice(pendingAcks.findIndex(x => x[0] === a[0]), 1);
    pendingAcks.push([rec.page_seq, toDoc(ackC)]);
    recs.push(rec);
  }
  const b = receiptBounds(recs, pendingAcks, 1);
  return {X, recs: recs.map((r, i) => ({...r, ...b[i]}))};
}
const firstNew = (recs, k) => recs.find(r => r[k]);
const lastOld = (recs, k) => [...recs].reverse().find(r => !r[k] && recs.indexOf(r) < recs.indexOf(firstNew(recs, k)));

for (const [name, opts] of [
  ['prompt callbacks', {}],
  ['callbacks 400 ms late, acks 300 ms late', {d1: () => 400, d2: () => 300}],
  ['collector stalled 550 ms across the chart change (slow journal)', {stall: [50000 + 1150, 50000 + 1700]}],
  ['callbacks 950 ms late', {d1: () => 950}],
]) {
  test(`fast headline / slow chart, ${name}: brackets contain the truth; the chart can never pass 1 s`, () => {
    const {X, recs} = simulate(opts);
    for (const r of recs) {
      assert.ok(r.d_hi >= r.true_read, `upper bound below truth at seq ${r.page_seq}`);
      if (r.d_lo !== null) assert.ok(r.d_lo <= r.true_read, `lower bound above truth at seq ${r.page_seq}`);
    }
    const chart = firstNew(recs, 'chart_new');
    // Display happened in (last old read, first new read]; its upper bound is the first new sample's d_hi.
    assert.ok(chart.d_hi - X > 1000, 'a chart 1.2 s late is never definitely under 1 s');
    if (name === 'prompt callbacks') {
      const head = firstNew(recs, 'headline_new');
      assert.ok(head.d_hi - X < 1000, 'the fast headline is provably under 1 s with prompt callbacks');
      assert.ok(lastOld(recs, 'chart_new').d_lo - X > 1000, 'and the slow chart is definitely over 1 s');
    }
  });
}

test('fast headline / slow chart: late callbacks only widen the upper bound, never narrow it', () => {
  const a = simulate().recs, b = simulate({d1: () => 400, d2: () => 300}).recs;
  for (let i = 0; i < a.length; i++) assert.ok(b[i].d_hi >= a[i].d_hi);
  const headA = firstNew(a, 'headline_new'), headB = firstNew(b, 'headline_new');
  assert.ok(headB.d_hi > headA.d_hi);
});

test('reference: a record with no ack gives no lower bound to later samples; acks from another document never bound this one', () => {
  const recs = [
    {page_seq: 1, time_origin: 1, recv: 10, read_start: 5, acks: []},
    {page_seq: 2, time_origin: 1, recv: 20, read_start: 15, acks: []}, // seq 1's ack missing
    {page_seq: 3, time_origin: 2, recv: 30, read_start: 1, acks: [[2, 100]]}, // a new document
  ];
  const b = receiptBounds(recs);
  assert.deepStrictEqual(b.map(x => x.d_lo), [null, null, null]);
  assert.deepStrictEqual(b.map(x => x.d_hi), [10, 20, 30]);
});

// The recorder's receipt summary runs inside record(); this executes its OWN
// source text (receipts state, noteAcks, the onPageRecord receipt lines, the
// stop-return line and receiptBrackets) on a replaced document.
test('recorder: a replaced document restarts page_seq; its lost ack is a hole, never paid by the new document', () => {
  const src = fs.readFileSync(path.join(__dirname, 'passive_case_recorder.cjs'), 'utf8');
  const cut = (a, b) => { const i = src.indexOf(a), j = src.indexOf(b, i); assert.ok(i >= 0 && j > i, `anchor ${a}`); return src.slice(i, j); };
  const lines = src.split('\n');
  const L1 = lines.find(l => l.includes('receipts.recvByKey.set('));
  const L2 = lines.find(l => /^\s*noteAcks\(rec\.acks, rec\.acks_dropped/.test(l));
  const STOP = (src.match(/receipts\.final_from_stop = noteAcks\([^;]*\);/) || [])[0];
  assert.ok(L1 && L2 && STOP, 'receipt lines present');
  const r = new Function(`${cut('  const receipts = {', '  const challenge = challengeCfg')}
${cut('  function receiptBrackets() {', '  async function detail(')}
let mono = 0;
return {onRec(rec) { const recvMono = ++mono; ${L1.trim()} ${L2.trim()} }, stop(queue) { receipts.stop_sent_mono = ++mono; ${STOP} }, receiptBrackets};`)();
  const OLD = 1793344000000.1, NEW = 1793344090000.2;
  for (let s = 1; s <= 5; s++) r.onRec({page_seq: s, time_origin: OLD, acks: s > 1 ? [[s - 1, s * 100]] : undefined});
  for (let s = 1; s <= 8; s++) r.onRec({page_seq: s, time_origin: NEW, acks: s > 1 ? [[s - 1, s * 100]] : undefined});
  r.stop({acks: [[8, 900]], acks_dropped: 0, time_origin: NEW});
  const b = r.receiptBrackets();
  assert.strictEqual(b.records_received, 13);
  assert.strictEqual(b.missing_before_stop, 1, 'old document seq 5 was never acked');
  assert.deepStrictEqual(b.missing_first, [5]);
  assert.strictEqual(b.acks_unknown, 0);
});
