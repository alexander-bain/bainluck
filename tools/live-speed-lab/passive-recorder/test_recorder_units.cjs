'use strict';
// node --test tools/live-speed-lab/passive-recorder/test_recorder_units.cjs
// Browser-free units for the passive recorder. The browser controls live in qualify.cjs.
const test = require('node:test');
const assert = require('node:assert');
const crypto = require('crypto');
const fs = require('fs');
const http = require('http');
const net = require('net');
const os = require('os');
const path = require('path');
const contract = require('./contract.cjs');
const {createJournal, minimalForms} = require('./journal.cjs');
const {createTransport} = require('./transport.cjs');
const {createClock} = require('./clock.cjs');

const sha = b => crypto.createHash('sha256').update(b).digest('hex');
const iso = ms => new Date(ms).toISOString();
const tmp = () => fs.mkdtempSync(path.join(os.tmpdir(), 'passive-recorder-test-'));

function bundle(dir, {mm, mg, origin = 'http://127.0.0.1:4633', t0 = Date.now() + 60000} = {}) {
  const pin = (name, v) => { const f = path.join(dir, name); fs.writeFileSync(f, JSON.stringify(v)); return {path: f, sha256: sha(fs.readFileSync(f))}; };
  const receipt = {source_sha: 'a'.repeat(40), release_receipt: pin('r.json', {r: 1})};
  const m = {schema: contract.MANIFEST_SCHEMA, case_id: 'c1', policy: pin('policy.json', {p: 1}),
    selection: {selected_at: iso(Date.now() - 1000), max_age_s: 3600, selected_by: 'test', inventory: {evidence: pin('inv.json', {i: 1}), order: [5], rejections: [], replacement_rule: 'none'}},
    event: {canonical_event_id: 5, members: [5, 9], contributing_sources: [{source: 'kalshi', contract: 'k', orientation: 'home'}]},
    owner_receipts: {backend: receipt, worker: receipt, frontend: receipt, authority: {incarnation: '3', namespace: '3b4f1a52-8d7e-4c1a-9f0e-2a6b5c4d3e21'}, preview_activation: pin('pa.json', {a: 1})},
    entry: {page_url: `${origin}/events/5`, api_origin: origin, readout_activation: 'none', expected_stream_url: `${origin}/api/events/5/stream?preview_protocol=authority-v3`, expected_stream_events: ['preview_open_v3']},
    trace: null,
    clock: {t0_utc: iso(Math.floor(t0 / 1000) * 1000), scoring: {start_offset_ms: 0, end_offset_ms: 180000}, acquisition: {start_offset_ms: -5000, end_offset_ms: 185000}, setup: {earliest_offset_ms: -120000, cutoff_offset_ms: -5000}},
    page: {viewport: {width: 390, height: 844}, held_pages: 1, require_document_visible: true, require_in_viewport: false},
    cleanup: {custody: 'test'}};
  if (mm) mm(m);
  const mPath = path.join(dir, 'm.json');
  fs.writeFileSync(mPath, JSON.stringify(m));
  const mSha = sha(fs.readFileSync(mPath));
  const g = {schema: contract.GRANT_SCHEMA, grant_id: 'g1', issued_by: 'test', issued_at: iso(Date.now() - 1000), expires_at: iso(t0 + 600000), case_id: 'c1', manifest_sha256: mSha,
    allowed_origins: [origin], allowed_routes: [{origin, methods: ['GET'], path_prefix: '/', resource_types: ['*']}],
    limits: {max_request_attempts: 10, max_eventsource_constructions: 2, max_stream_attempts: 3, max_active_streams: 1, max_response_bytes: 1000000,
      max_request_bytes: 100000, max_record_bytes: 10000, max_saved_bytes: 1000000, reserved_stop_bytes: 100000, max_queue_records: 64, max_detail_requests: 0, received_overshoot_bytes: 65536},
    detail_requests: [], browser: {browser_channel: 'chromium', browser_mode: 'single-process', playwright_package_sha256: 'c'.repeat(64), browser_version: '140.0.7339.186'}};
  if (mg) mg(g);
  const gPath = path.join(dir, 'g.json');
  fs.writeFileSync(gPath, JSON.stringify(g));
  return {manifest: mPath, manifestSha256: mSha, grant: gPath, grantSha256: sha(fs.readFileSync(gPath)), scope: 'local', now: Date.now()};
}

test('a complete local bundle validates with no network', () => {
  const v = contract.validateBundle(bundle(tmp()));
  assert.deepStrictEqual(v.refusals, []);
  assert.strictEqual(v.window.acquisition_end_wall_ms - v.window.t0_wall_ms, 185000);
});

test('scope has no default', () => {
  const b = bundle(tmp());
  assert.match(contract.validateBundle({...b, scope: undefined}).refusals.join(), /--scope: local or production required/);
});

for (const [name, mut, re] of [
  ['acquisition edge moved', {mm: m => { m.clock.acquisition.start_offset_ms = 0; }}, /predeclared -5000..185000/],
  ['scoring edge moved', {mm: m => { m.clock.scoring.end_offset_ms = 120000; }}, /predeclared 0..180000/],
  ['setup cutoff after acquisition start', {mm: m => { m.clock.setup.cutoff_offset_ms = 0; }}, /earliest < cutoff <= -5000/],
  ['stream URL rewritten', {mm: m => { m.entry.expected_stream_url += '&x=1'; }}, /expected_stream_url: must equal/],
  ['page route is not the event', {mm: m => { m.entry.page_url = 'http://127.0.0.1:4633/events/6'; }}, /product event route/],
  ['members omit the event', {mm: m => { m.event.members = [9]; }}, /must include canonical_event_id/],
  ['members unsorted', {mm: m => { m.event.members = [9, 5]; }}, /strictly increasing/],
  ['two held pages', {mm: m => { m.page.held_pages = 2; }}, /exactly 1/],
  ['stale selection', {mm: m => { m.selection.max_age_s = 1; }}, /not current through the acquisition end/],
  ['unknown limit', {mg: g => { g.limits.max_extra = 1; }}, /unknown max_extra/],
  ['zero limit', {mg: g => { g.limits.max_request_attempts = 0; }}, /finite positive integer/],
  ['fractional limit', {mg: g => { g.limits.max_saved_bytes = 1.5; }}, /finite positive integer/],
  ['reserve not below total', {mg: g => { g.limits.reserved_stop_bytes = 1000000; }}, /must be below max_saved_bytes/],
  ['detail count mismatch', {mg: g => { g.limits.max_detail_requests = 1; }}, /count must equal/],
  ['detail outside window', {mg: g => { g.limits.max_detail_requests = 1; g.detail_requests = [{method: 'GET', url: 'http://127.0.0.1:4633/api/x', at_offset_ms: 200000}]; }}, /inside the acquisition window/],
  ['grant does not cover entry', {mg: g => { g.allowed_origins = ['http://127.0.0.1:9']; g.allowed_routes[0].origin = 'http://127.0.0.1:9'; }}, /does not cover manifest.entry.page_url/],
  ['production host under local scope', {origin: 'https://api.bainluck.com'}, /local scope: non-loopback origin refused \(api.bainluck.com\)/],
  // N1: the per-stream number could only be read from lagging CDP, so it is not a limit.
  ['a per-stream byte limit', {mg: g => { g.limits.max_stream_bytes = 1; }}, /grant.limits: unknown max_stream_bytes/],
  // N2: a reserve below the floor could leave a run with no STOP or SUMMARY.
  ['reserve below the STOP floor', {mg: g => { g.limits.reserved_stop_bytes = 16; }}, /reserved_stop_bytes: must be at least 65536/],
  ['reserve one byte below the floor', {mg: g => { g.limits.reserved_stop_bytes = contract.MIN_RESERVED_STOP_BYTES - 1; }}, /must be at least 65536/],
  // N3: the grant names the qualified browser.
  ['grant without a browser', {mg: g => { delete g.browser; }}, /grant: missing browser/],
  ['grant browser mode unknown', {mg: g => { g.browser.browser_mode = 'toString'; }}, /grant.browser.browser_mode: one of/],
  ['grant browser channel unknown', {mg: g => { g.browser.browser_channel = 'firefox'; }}, /grant.browser.browser_channel: one of/],
  ['grant browser package not a sha', {mg: g => { g.browser.playwright_package_sha256 = '1.55.0'; }}, /playwright_package_sha256: lowercase sha256/],
  ['grant browser version empty', {mg: g => { g.browser.browser_version = ''; }}, /browser_version: the exact browser.version\(\) string required/],
  ['grant browser extra field', {mg: g => { g.browser.headless = true; }}, /grant.browser: unknown headless/],
]) {
  test(`refuses: ${name}`, () => {
    const v = contract.validateBundle(bundle(tmp(), mut));
    assert.strictEqual(v.ok, false);
    assert.match(v.refusals.join('\n'), re);
  });
}

test('the reserve floor is exactly accepted', () => {
  const v = contract.validateBundle(bundle(tmp(), {mg: g => { g.limits.reserved_stop_bytes = contract.MIN_RESERVED_STOP_BYTES; }}));
  assert.deepStrictEqual(v.refusals, []);
});

test('journal: at the floor, worst-case minimal STOP and SUMMARY both fit; a 16-byte reserve writes neither', () => {
  // Every string escapes to 6 bytes per UTF-16 unit and every list is overfull: the largest the minimal forms can be.
  const worst = '\u0000'.repeat(500);
  const forms = minimalForms({status: worst, reason: worst, holes: Array(200).fill(worst), fault_kinds: Array(200).fill(worst)});
  assert.strictEqual(forms.summary.holes.length, contract.MINIMAL_LIST_ITEMS);
  assert.ok(forms.summary.holes.every(h => h.length === contract.MINIMAL_STRING_CHARS));
  const big = {pad: 'p'.repeat(contract.MIN_RESERVED_STOP_BYTES * 2)};
  const dir = tmp();
  const j = createJournal({dir, limits: {max_record_bytes: 1000, max_saved_bytes: contract.MIN_RESERVED_STOP_BYTES + 1000, reserved_stop_bytes: contract.MIN_RESERVED_STOP_BYTES}, onExhausted: () => {}});
  const stop = j.writeReserved('STOP.json', big, forms.stop);
  const summary = j.writeReserved('SUMMARY.json', big, forms.summary);
  j.close();
  assert.deepStrictEqual([stop.written, stop.truncated, summary.written, summary.truncated], [true, true, true, true]);
  assert.ok(j.stats.reserved_used_bytes <= 40000, `minimal forms used ${j.stats.reserved_used_bytes} bytes`);
  assert.strictEqual(JSON.parse(fs.readFileSync(path.join(dir, 'SUMMARY.json'), 'utf8')).reserve_truncated, true);

  const dir2 = tmp();
  const j2 = createJournal({dir: dir2, limits: {max_record_bytes: 1000, max_saved_bytes: 2000, reserved_stop_bytes: 16}, onExhausted: () => {}});
  const typical = minimalForms({status: 'STOPPED', reason: 'cancelled', holes: [], fault_kinds: []});
  assert.strictEqual(j2.writeReserved('STOP.json', big, typical.stop).written, false);
  assert.strictEqual(j2.writeReserved('SUMMARY.json', big, typical.summary).written, false);
  j2.close();
  assert.deepStrictEqual(fs.readdirSync(dir2).sort(), ['records.jsonl']);
});

test('a pinned file that drifts after hashing refuses', () => {
  const dir = tmp();
  const b = bundle(dir);
  fs.appendFileSync(path.join(dir, 'policy.json'), ' ');
  assert.match(contract.validateBundle(b).refusals.join(), /manifest.policy: sha256 drift/);
});

test('production scope accepts a production origin the grant names', () => {
  const v = contract.validateBundle({...bundle(tmp(), {origin: 'https://api.example.test'}), scope: 'production'});
  assert.deepStrictEqual(v.refusals.filter(r => /origin/.test(r)), []);
});

test('strict JSON reports duplicate keys that JSON.parse would hide', () => {
  const r = contract.parseStrictJson('{"protocol":3,"a":{"b":1,"b":2},"protocol":3}');
  assert.deepStrictEqual(r.duplicates.sort(), ['$.a.b', '$.protocol']);
  assert.throws(() => contract.parseStrictJson('{"protocol":3,'), SyntaxError);
  assert.deepStrictEqual(contract.parseStrictJson('[1,"x\\"y",{"k":null}]').value, [1, 'x"y', {k: null}]);
});

test('journal: oversize is a marker, saved cap stops before the reserve, late writes are counted not written', () => {
  const dir = tmp();
  const hits = [];
  const j = createJournal({dir, limits: {max_record_bytes: 200, max_saved_bytes: 1000, reserved_stop_bytes: 400}, onExhausted: d => hits.push(d)});
  assert.ok(j.append('a', {x: 'y'}));
  j.append('big', {x: 'z'.repeat(500)});
  assert.strictEqual(j.stats.oversize, 1);
  while (j.append('fill', {x: 'q'.repeat(100)})) { /* until the ordinary cap */ }
  assert.ok(j.stats.saved_bytes <= 600);
  assert.strictEqual(hits.length, 1);
  assert.ok(j.writeReserved('STOP.json', {status: 'STOPPED', pad: 'p'.repeat(1000)}, {status: 'STOPPED'}).truncated);
  j.close();
  assert.strictEqual(j.append('late', {}), null);
  assert.strictEqual(j.stats.late_records, 1);
  const lines = fs.readFileSync(path.join(dir, 'records.jsonl'), 'utf8').trim().split('\n').map(l => JSON.parse(l));
  assert.deepStrictEqual(lines.map(l => l.id), lines.map((_, i) => i + 1));
  assert.strictEqual(lines[1].kind, 'oversize');
});

function listen(server) { return new Promise(r => server.listen(0, '127.0.0.1', () => r(server.address().port))); }

test('transport: an endless chunked stream is cut before the chunk that would cross the cap (HTTP)', async () => {
  const origin = http.createServer((req, res) => {
    res.writeHead(200, {'content-type': 'text/event-stream'});
    const blob = Buffer.alloc(1000, 0x61);
    const t = setInterval(() => res.write(blob), 1);
    res.on('close', () => clearInterval(t));
  });
  const port = await listen(origin);
  let tripped = null;
  const t = createTransport({allowOrigin: o => o === `http://127.0.0.1:${port}`, limits: {max_response_bytes: 50000, max_request_bytes: 10000}, onTrip: x => { tripped = x; }, onEvent: () => {}});
  const pport = await t.listen();
  let received = 0;
  await new Promise(resolve => {
    const req = http.request({host: '127.0.0.1', port: pport, path: `http://127.0.0.1:${port}/s`, agent: false}, res => { res.on('data', c => { received += c.length; }); res.on('close', resolve); res.on('error', resolve); });
    req.on('error', resolve);
    req.end();
  });
  await t.close();
  origin.close();
  assert.strictEqual(tripped.kind, 'max_response_bytes');
  assert.ok(t.counters.response_bytes <= 50000, `forwarded ${t.counters.response_bytes}`);
  assert.ok(received <= t.counters.response_bytes, 'the client never sees more than was counted');
  assert.strictEqual(t.counters.refused_chunks, 1);
});

test('transport: a refused origin is never contacted', async () => {
  let contacted = false;
  const origin = http.createServer((req, res) => { contacted = true; res.end('x'); });
  const port = await listen(origin);
  const t = createTransport({allowOrigin: () => false, limits: {max_response_bytes: 1000, max_request_bytes: 1000}, onTrip: () => {}, onEvent: () => {}});
  const pport = await t.listen();
  await new Promise(resolve => { const req = http.request({host: '127.0.0.1', port: pport, path: `http://127.0.0.1:${port}/`, agent: false}, () => resolve()); req.on('error', resolve); req.end(); });
  await t.close();
  origin.close();
  assert.strictEqual(contacted, false);
  assert.strictEqual(t.counters.refused_origins, 1);
});

test('transport: CONNECT tunnels count raw bytes and cut at the cap', async () => {
  const origin = net.createServer(s => { const t = setInterval(() => s.write(Buffer.alloc(4096, 0x62)), 1); s.on('close', () => clearInterval(t)); s.on('error', () => {}); });
  const port = await listen(origin);
  let tripped = null;
  const t = createTransport({allowOrigin: o => o === `https://127.0.0.1:${port}`, limits: {max_response_bytes: 40000, max_request_bytes: 10000}, onTrip: x => { tripped = x; }, onEvent: () => {}});
  const pport = await t.listen();
  let received = 0;
  await new Promise(resolve => {
    const s = net.connect(pport, '127.0.0.1', () => s.write(`CONNECT 127.0.0.1:${port} HTTP/1.1\r\nHost: 127.0.0.1:${port}\r\n\r\n`));
    s.on('data', c => { received += c.length; });
    s.on('close', resolve);
    s.on('error', resolve);
  });
  await t.close();
  origin.close();
  assert.strictEqual(tripped.kind, 'max_response_bytes');
  assert.ok(t.counters.response_bytes <= 40000);
  assert.strictEqual(received, t.counters.response_bytes);
  assert.strictEqual(t.counters.tunnels, 1);
});

test('clock: intervals intersect, a replaced document and a wall jump are loud faults', async () => {
  const {performance} = require('perf_hooks');
  const base = performance.now() - 1000;
  let docNow = 0, origin = 5e12, skew = 0;
  // A document clock that runs at the collector's rate, as a real one does.
  const page = {evaluate: async () => { docNow = performance.now() - base; return {now: docNow, timeOrigin: origin, wall: origin + docNow, visibility: 'visible'}; }};
  const c = createClock({t0WallMs: Date.now() + 1000, wallSkewMs: () => skew});
  await c.exchange(page, 'a');
  await c.exchange(page, 'b');
  assert.ok(c.offset[0] <= c.offset[1]);
  assert.deepStrictEqual(c.faults, []);
  skew = 5000;
  await c.exchange(page, 'jump');
  assert.ok(c.faults.some(f => f.kind === 'collector-wall-jump-or-suspend'));
  origin += 1;
  await c.exchange(page, 'replaced');
  assert.ok(c.faults.some(f => f.kind === 'document-replaced'));
  const at = c.docToT0(docNow);
  assert.ok(at[0] <= at[1]);
});

test('clock: a document clock that drifts outside the running interval is a fault', async () => {
  let docNow = 1000;
  const page = {evaluate: async () => ({now: docNow, timeOrigin: 1, wall: 1 + docNow, visibility: 'visible'})};
  const c = createClock({t0WallMs: Date.now()});
  await c.exchange(page, 'a');
  docNow -= 50; // the document clock went backwards relative to the collector
  await c.exchange(page, 'b');
  assert.ok(c.faults.some(f => f.kind === 'offset-drift'));
});

test('clock: brackets disjoint within tolerance keep their intersection widened by the tolerance', async () => {
  const {performance} = require('perf_hooks');
  const realNow = performance.now;
  // Scripted collector monotonic reads: anchor (0, 0), exchange a (100, 104), exchange b (200, 204).
  const reads = [0, 0, 100, 104, 200, 204];
  let mono = 0;
  performance.now = () => { mono = reads.shift(); return mono; };
  try {
    const docNow = [50, 145]; // offsets [50, 54] then [55, 59]: 1 ms apart, inside the 2 ms tolerance
    const page = {evaluate: async () => { const now = docNow.shift(); return {now, timeOrigin: 1000, wall: 1000 + now, visibility: 'visible'}; }};
    const base = Date.now();
    const c = createClock({t0WallMs: base, wallSkewMs: () => mono - (Date.now() - base)});
    await c.exchange(page, 'a');
    const b = await c.exchange(page, 'b');
    assert.deepStrictEqual(c.offset, [53, 56], 'the intersection of both brackets widened by 2 ms, not the 54..55 gap');
    assert.deepStrictEqual(b.running_offset_ms, [53, 56]);
    assert.deepStrictEqual(c.faults, []);
  } finally { performance.now = realNow; }
});

test('primary recorder is the staged observer span, byte for byte', () => {
  const text = fs.readFileSync(path.join(__dirname, 'primary_recorder.cjs'), 'utf8').split('\n');
  const start = text.findIndex(l => l.startsWith('// Browser-local primary record.'));
  const span = text.slice(start, start + 94).join('\n') + '\n';
  assert.strictEqual(sha(span), '3f34bcfb2670b4a0830f760ce495ef2d44d1fbed474a164464886bfcdda28a37');
});

test('the 100 ms sampler file is the pinned display_sample.cjs', () => {
  const {DISPLAY_SAMPLE_SHA256} = require('./passive_case_recorder.cjs');
  assert.strictEqual(sha(fs.readFileSync(path.join(__dirname, '../compare/display_sample.cjs'))), DISPLAY_SAMPLE_SHA256);
});
