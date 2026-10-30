#!/usr/bin/env node
'use strict';
// #10090: BROWSER-FREE LIFECYCLE control of the receipt brackets and the DARK
// clock challenge, through the real recorder (subprocess, --scope local) with
// the scripted in-process page in lifecycle-fake-playwright/. It proves record
// semantics end to end (collector receipt, ack carry, teardown sweep, holes,
// challenge wiring and gating). It is NOT a browser qualification: no paint,
// no real CDP timing; qualify.cjs remains the browser control.
//
//   node lifecycle_control.cjs --out NEW_DIR --pg-module DIR --pg-url postgresql://user@127.0.0.1:PORT/db
//        --old-recorder DIR   (a checkout of the predecessor passive-recorder, for the record-count twin)
//
// Cases (run in parallel, one T0):
//   A  prompt callbacks + challenge over real local PG to two stand-in producers
//   B  late callbacks, a 600 ms collector stall at the chart change, stop-tail acks never resolve
//   C  document replaced at T0+90 s + a challenge connection that refuses
//   D  the predecessor recorder on A's page, no challenge (record-count twin)
// Exit 0 only if every check passes; CONTROLS.json lists each.
const {spawn} = require('child_process');
const crypto = require('crypto');
const fs = require('fs');
const path = require('path');
const {receiptBounds} = require('./receipt_bounds_reference.cjs');
const {CEILINGS, SCHEMA} = require('./challenge.cjs');

const args = {};
for (let i = 2; i < process.argv.length; i += 2) args[process.argv[i].slice(2)] = process.argv[i + 1];
for (const k of ['out', 'pg-module', 'pg-url', 'old-recorder']) if (!args[k]) { console.error(`--${k} required`); process.exit(2); }
const OUT = path.resolve(args.out);
if (fs.existsSync(OUT)) { console.error(`--out exists: ${OUT}`); process.exit(3); }
if (!['127.0.0.1', 'localhost'].includes(new URL(args['pg-url']).hostname)) { console.error('--pg-url must be loopback'); process.exit(3); }
fs.mkdirSync(OUT);
const HERE = __dirname;
const FAKE = path.join(HERE, 'lifecycle-fake-playwright');
const sha = b => crypto.createHash('sha256').update(b).digest('hex');
const iso = ms => new Date(ms).toISOString();
const pg = require(path.resolve(args['pg-module']));

const ORIGIN = 'http://127.0.0.1:4999', EVENT = 77, MEMBERS = [77, 78];
const AUTH = {incarnation: '3', namespace: '3b4f1a52-8d7e-4c1a-9f0e-2a6b5c4d3e21'};
const LEAD_MS = 30000;
const T0 = Math.ceil((Date.now() + LEAD_MS) / 1000) * 1000;
const INPUT = 60000; // the scripted input, ms after T0
const BROWSER_VERSION = '0.0.0-lifecycle-fake';
const LIMITS = {max_request_attempts: 400, max_eventsource_constructions: 4, max_stream_attempts: 6, max_active_streams: 1,
  max_response_bytes: 50_000_000, max_request_bytes: 2_000_000, max_record_bytes: 262_144, max_saved_bytes: 200_000_000,
  reserved_stop_bytes: 4_000_000, max_queue_records: 512, max_detail_requests: 0, received_overshoot_bytes: 65_536};

function pinned(dir, name, v) { const f = path.join(dir, name); fs.writeFileSync(f, JSON.stringify(v)); return {path: f, sha256: sha(fs.readFileSync(f))}; }

function buildCase(name, {challenge = null, connection = null}) {
  const dir = path.join(OUT, `case-${name}`);
  fs.mkdirSync(dir);
  const label = 'LOCAL LIFECYCLE CONTROL ONLY — not a production receipt';
  const r = n => pinned(dir, `${n}.json`, {label, n});
  const m = {schema: 'bainluck.passive-case-manifest/1', case_id: `lifecycle-${name}`, policy: pinned(dir, 'policy.json', {label}),
    selection: {selected_at: iso(Date.now() - 1000), max_age_s: 3600, selected_by: 'calibration lifecycle control',
      inventory: {evidence: pinned(dir, 'inventory.json', {label}), order: [EVENT], rejections: [], replacement_rule: 'none'}},
    event: {canonical_event_id: EVENT, members: MEMBERS, contributing_sources: [{source: 'fixture', contract: 'lifecycle', orientation: 'home'}]},
    owner_receipts: {backend: {source_sha: '0'.repeat(40), release_receipt: r('backend')}, worker: {source_sha: '0'.repeat(40), release_receipt: r('worker')},
      frontend: {source_sha: '0'.repeat(40), release_receipt: r('frontend')}, authority: AUTH, preview_activation: r('preview-activation')},
    entry: {page_url: `${ORIGIN}/events/${EVENT}`, api_origin: ORIGIN, readout_activation: 'none',
      expected_stream_url: `${ORIGIN}/api/events/${EVENT}/stream?preview_protocol=authority-v3`, expected_stream_events: ['preview_open_v3']},
    trace: null,
    clock: {t0_utc: iso(T0), scoring: {start_offset_ms: 0, end_offset_ms: 180000}, acquisition: {start_offset_ms: -5000, end_offset_ms: 185000},
      setup: {earliest_offset_ms: -(LEAD_MS + 10000), cutoff_offset_ms: -5000}},
    page: {viewport: {width: 390, height: 844}, held_pages: 1, require_document_visible: true, require_in_viewport: false},
    cleanup: {custody: 'calibration lifecycle control harness'}};
  const mPath = path.join(dir, 'manifest.json');
  fs.writeFileSync(mPath, JSON.stringify(m, null, 1));
  const g = {schema: 'bainluck.passive-case-grant/1', grant_id: `lifecycle-${name}`, issued_by: 'calibration lifecycle control', issued_at: iso(Date.now() - 1000),
    expires_at: iso(T0 + 600000), case_id: m.case_id, manifest_sha256: sha(fs.readFileSync(mPath)), allowed_origins: [ORIGIN],
    allowed_routes: [{origin: ORIGIN, methods: ['GET'], path_prefix: '/', resource_types: ['*']}], limits: LIMITS, detail_requests: [],
    browser: {browser_channel: 'chromium', browser_mode: 'single-process', playwright_package_sha256: sha(fs.readFileSync(path.join(FAKE, 'package.json'))), browser_version: BROWSER_VERSION}};
  if (challenge) g.challenge = challenge;
  const gPath = path.join(dir, 'grant.json');
  fs.writeFileSync(gPath, JSON.stringify(g, null, 1));
  let connPath = null;
  if (connection) { connPath = path.join(dir, 'connection.cjs'); fs.writeFileSync(connPath, connection); }
  return {name, dir, mPath, gPath, mSha: sha(fs.readFileSync(mPath)), gSha: sha(fs.readFileSync(gPath)), connPath};
}

function scenario(extra) {
  return {t0_wall_ms: T0, doc_offset_ms: 98765.4321, page_url: `${ORIGIN}/events/${EVENT}`, stream_url: `${ORIGIN}/api/events/${EVENT}/stream?preview_protocol=authority-v3`,
    authority: AUTH, members: MEMBERS, event_id: EVENT, browser_version: BROWSER_VERSION,
    input_since_t0_ms: INPUT, headline_after_ms: 100, chart_after_ms: 1200, d1_ms: 1, d2_ms: 1, ...extra};
}

function runRecorder(recorderDir, c, scen0) {
  const out = path.join(c.dir, 'out');
  const scen = {...scen0, offsets_file: path.join(c.dir, 'doc_offsets.json')};
  const argv = [path.join(recorderDir, 'passive_case_recorder.cjs'), 'record', '--scope', 'local', '--manifest', c.mPath, '--manifest-sha256', c.mSha,
    '--grant', c.gPath, '--grant-sha256', c.gSha, '--out', out, '--playwright-module', FAKE, '--browser-channel', 'chromium', '--browser-mode', 'single-process',
    ...(c.connPath ? ['--challenge-connection', c.connPath] : [])];
  return new Promise(resolve => {
    const p = spawn(process.execPath, argv, {env: {...process.env, LIFECYCLE_FAKE_SCENARIO: JSON.stringify(scen)}, stdio: ['ignore', 'pipe', 'pipe']});
    let stdout = '', stderr = '';
    p.stdout.on('data', d => { stdout += d; });
    p.stderr.on('data', d => { stderr += d; });
    // A recorder must exit on its own after its STOP; one that does not is a failure.
    const watchdog = setTimeout(() => { p.kill('SIGKILL'); fs.writeFileSync(path.join(c.dir, 'recorder.KILLED'), 'did not exit within T0+185 s + 60 s\n'); }, Math.max(0, T0 + 245000 - Date.now()));
    p.on('close', code => { clearTimeout(watchdog); fs.writeFileSync(path.join(c.dir, 'recorder.stdout'), stdout); fs.writeFileSync(path.join(c.dir, 'recorder.stderr'), stderr); resolve({code, out}); });
  });
}

async function producer(token, run, pid) {
  const c = new pg.Client({connectionString: args['pg-url']});
  await c.connect();
  let q = 0;
  c.on('notification', msg => {
    const lo = process.hrtime.bigint();
    const r = JSON.parse(msg.payload);
    if (r.t !== token || r.r !== run) return;
    const hi = process.hrtime.bigint();
    c.query('SELECT pg_notify($1, $2)', [`bl_cr_${r.o}`, JSON.stringify({p: SCHEMA.protocol, o: r.o, t: token, r: run, pid, k: r.k, n: r.n, q: ++q, m: [Number(lo / 1000n), Number((hi + 999n) / 1000n)]})]).catch(() => {});
  });
  await c.query(`LISTEN bl_cc_${token}`);
  return c;
}

function load(out) {
  const read = f => JSON.parse(fs.readFileSync(path.join(out, f), 'utf8'));
  const lines = fs.readFileSync(path.join(out, 'records.jsonl'), 'utf8').trim().split('\n').map(l => JSON.parse(l));
  return {stop: read('STOP.json'), summary: read('SUMMARY.json'), bindings: read('BINDINGS.json'), lines,
    offsets: JSON.parse(fs.readFileSync(path.join(path.dirname(out), 'doc_offsets.json'), 'utf8'))};
}

// The reference brackets on the recorder's own journal, with ground truth from
// the scenario's document offset (true read on C = document read + offset).
function brackets(run, scen) {
  const recs = run.lines.filter(l => (l.kind === 'sample' || l.kind === 'page') && l.recv && l.rec && Number.isSafeInteger(l.rec.page_seq)).map(l => ({
    page_seq: l.rec.page_seq, time_origin: l.rec.time_origin, recv: l.recv.mono, read_start: l.rec.read_bracket ? l.rec.read_bracket[0] : l.rec.mono,
    acks: l.rec.acks || [], kind: l.rec.kind, di: l.rec.display_identity, since: l.recv.since_t0_ms,
    true_read: (l.rec.read_bracket ? l.rec.read_bracket[0] : l.rec.mono) + run.offsets[String(l.rec.time_origin)]}));
  const q = run.stop.counters.page_queue || {}, dr = run.stop.counters.page_acks_drained || {};
  const extraTo = q.time_origin ?? dr.time_origin ?? null;
  const b = receiptBounds(recs, [...(q.acks || []), ...(dr.acks || [])], extraTo);
  return recs.map((r, i) => ({...r, ...b[i]}));
}

const checks = [];
const check = (caseName, name, ok, detail = null) => { checks.push({case: caseName, check: name, ok: !!ok, detail}); };

function checkBrackets(caseName, run, scen, {expectHeadlineProvable}) {
  const bs = brackets(run, scen);
  const anchor = run.bindings.clock_anchor; // since_t0(m) = [m - t0_mono[1], m - t0_mono[0]]
  const since = m => [m - anchor.t0_mono[1], m - anchor.t0_mono[0]];
  const bad = bs.filter(r => r.d_hi < r.true_read || (r.d_lo !== null && r.d_lo > r.true_read));
  check(caseName, 'every record: true read on C lies inside [d_lo, d_hi]', bad.length === 0 && bs.length > 1000, {records: bs.length, violations: bad.slice(0, 5).map(r => r.page_seq)});
  const samples = bs.filter(r => r.kind === 'sample' && r.di);
  const firstNew = k => samples.find(r => r.di[k].attributes[k === 'headline' ? 'data-display-state' : 'data-chart-endpoint-state'] === 'new');
  const head = firstNew('headline'), chart = firstNew('chart');
  const lastOldChart = samples.filter(r => samples.indexOf(r) < samples.indexOf(chart)).pop();
  const chartHi = since(chart.d_hi)[1] - INPUT, headHi = since(head.d_hi)[1] - INPUT;
  check(caseName, 'a chart 1.2 s late is never definitely under 1 s (upper bound of its display > 1000 ms)', chartHi > 1000, {chart_display_upper_ms: chartHi});
  if (expectHeadlineProvable) {
    check(caseName, 'the fast headline is provably under 1 s', headHi < 1000, {headline_display_upper_ms: headHi});
    const lo = lastOldChart.d_lo === null ? null : since(lastOldChart.d_lo)[0] - INPUT;
    check(caseName, 'the slow chart is definitely over 1 s (lower bound of its display > 1000 ms)', lo !== null && lo > 1000, {chart_display_lower_ms: lo});
  } else {
    check(caseName, 'late callbacks leave the headline upper bound at or above the prompt case', headHi > 100, {headline_display_upper_ms: headHi});
  }
  return bs;
}

(async () => {
  const opA = crypto.randomBytes(8).toString('hex');
  const tokens = [crypto.randomBytes(8).toString('hex'), crypto.randomBytes(8).toString('hex')];
  const challengeA = {operation: opA, reply_channel: `bl_cr_${opA}`, roster: tokens.map((t, i) => ({token: t, channel: `bl_cc_${t}`, run: `run${i}`, pid: 5001 + i, role: i ? 'polymarket-standin' : 'kalshi-standin'})),
    slots: {first_offset_ms: -5000, slot_ms: 250, count: 760}, deadline_ms: 150,
    limits: {connect_timeout_ms: 2000, max_wire_bytes_per_incarnation: CEILINGS.max_wire_bytes_per_incarnation, max_wire_bytes_session: CEILINGS.max_wire_bytes_session,
      max_read_overshoot_bytes: 65536, max_journal_bytes_per_incarnation: CEILINGS.max_journal_bytes_per_incarnation}};
  const opC = crypto.randomBytes(8).toString('hex');
  const challengeC = {...challengeA, operation: opC, reply_channel: `bl_cr_${opC}`};
  const A = buildCase('A', {challenge: challengeA, connection: `module.exports.connect = require(${JSON.stringify(path.join(HERE, 'pg_transport.cjs'))}).createPgConnectionFactory({pgModuleDir: ${JSON.stringify(path.resolve(args['pg-module']))}, connectionString: ${JSON.stringify(args['pg-url'])}});\n`});
  const B = buildCase('B', {});
  const C = buildCase('C', {challenge: challengeC, connection: "module.exports.connect = async () => { throw Object.assign(new Error('refused by the lifecycle control'), {code: 'ECONNREFUSED'}); };\n"});
  const D = buildCase('D', {});
  const scen = {A: scenario({}), B: scenario({d1_ms: [50, 400], d2_ms: [50, 300], stall: {at_ms: INPUT + 1150, ms: 600}, never_resolve_after_ms: 183500}),
    C: scenario({replace_document_at_ms: 90000}), D: scenario({})};
  const prods = await Promise.all(tokens.map((t, i) => producer(t, `run${i}`, 5001 + i)));
  console.log(`T0 ${iso(T0)}; four recorders start now; done about ${iso(T0 + 200000)}`);
  const [rA, rB, rC, rD] = await Promise.all([runRecorder(HERE, A, scen.A), runRecorder(HERE, B, scen.B), runRecorder(HERE, C, scen.C), runRecorder(path.resolve(args['old-recorder']), D, scen.D)]);
  await Promise.all(prods.map(p => p.end()));

  for (const [n, r] of [['A', rA], ['B', rB], ['C', rC], ['D', rD]]) check(n, 'recorder exited on its own', !fs.existsSync(path.join(path.dirname(r.out), 'recorder.KILLED')), {code: r.code});
  // A
  const a = load(rA.out);
  check('A', 'exit 0, page case COMPLETE with no holes', rA.code === 0 && a.summary.status === 'COMPLETE' && a.summary.holes.length === 0, {code: rA.code, status: a.summary.status, holes: a.summary.holes, faults: a.summary.fault_kinds});
  check('A', 'every page record journaled with its collector receipt', a.lines.filter(l => l.kind === 'sample' || l.kind === 'page').every(l => l.recv && Number.isFinite(l.recv.mono) && Array.isArray(l.recv.since_t0_ms)));
  const rbA = a.summary.receipt_brackets;
  check('A', 'every record received before the stop request was acked', rbA.missing_before_stop === 0 && rbA.acks_dropped === 0 && rbA.acked >= rbA.records_received - rbA.unacked_after_stop_request, rbA);
  checkBrackets('A', a, scen.A, {expectHeadlineProvable: true});
  const ch = a.summary.challenge;
  check('A', 'challenge COMPLETE: 760 timely exchanges per stand-in incarnation over one real PG connection', ch.status === 'COMPLETE' && ch.domains.every(d => d.timely === 760 && d.sent === 760), {status: ch.status, holes: ch.holes, drops: ch.drops, domains: ch.domains.map(d => [d.sent, d.timely, d.late, d.no_reply, d.skipped])});
  const exA = a.lines.filter(l => l.kind === 'challenge-exchange');
  check('A', 'challenge journal: one line per exchange, S < R on C, raw reply kept', exA.length === 1520 && exA.every(e => e.S < e.R && typeof e.raw === 'string'), {lines: exA.length});
  check('A', 'challenge wire counted at the socket and inside the cap', ch.wire && ch.wire.sent_bytes + ch.wire.received_bytes <= ch.wire.cap_bytes && ch.wire.refused_writes === 0 && ch.wire.read_overshoot_bytes === 0,
    ch.wire && {sent: ch.wire.sent_bytes, received: ch.wire.received_bytes, cap: ch.wire.cap_bytes, per_exchange: (ch.wire.sent_bytes + ch.wire.received_bytes) / 1520, max_pending: ch.wire.max_pending});
  const rs = exA.map(e => e.R - e.S).sort((x, y) => x - y);
  check('A', 'challenge round trip on C (diagnostic)', true, {p50_ms: rs[Math.floor(rs.length / 2)], p99_ms: rs[Math.floor(rs.length * 0.99)], max_ms: rs[rs.length - 1]});

  // B
  const b = load(rB.out);
  check('B', 'stop-tail acks that never resolve are an explicit hole (UNRESOLVED)', b.summary.status === 'UNRESOLVED' && b.summary.holes.includes('page-ack-missing'), {status: b.summary.status, holes: b.summary.holes, rb: b.summary.receipt_brackets});
  check('B', 'challenge inactive and recorded so', b.summary.challenge_status === 'INACTIVE' && b.bindings.challenge === 'inactive');
  checkBrackets('B', b, scen.B, {expectHeadlineProvable: false});

  // C
  const c = load(rC.out);
  check('C', 'a replaced document is a loud fault on the record path', c.summary.fault_kinds.includes('document-replaced-record'), c.summary.fault_kinds);
  check('C', 'acks still pending in the replaced document are a hole, not silently dropped', c.summary.holes.includes('page-ack-missing') || c.summary.receipt_brackets.missing_before_stop === 0, {holes: c.summary.holes, rb: c.summary.receipt_brackets});
  check('C', 'a refused challenge connection is UNAVAILABLE with a hole, and the page case still records', c.summary.challenge_status === 'UNAVAILABLE' && c.summary.challenge.holes.includes('challenge-connect-failed') &&
    c.lines.filter(l => l.kind === 'sample' && l.recv && l.recv.since_t0_ms[0] > 100000).length > 500, {challenge: c.summary.challenge.status, holes: c.summary.challenge.holes});
  const bsC = brackets(c, scen.C);
  const origins = [...new Set(bsC.map(r => r.time_origin))];
  const firstOfNew = bsC.find(r => r.time_origin === origins[1]);
  check('C', 'no lower bound crosses documents: the new document\'s first record has none', origins.length === 2 && firstOfNew.d_lo === null, {origins});
  const badC = bsC.filter(r => r.d_hi < r.true_read || (r.d_lo !== null && r.d_lo > r.true_read));
  check('C', 'brackets still contain the truth across the replacement', badC.length === 0);

  // D: the predecessor recorder on the same page; record counts are preserved.
  const d = load(rD.out);
  const kinds = run => [...new Set(run.lines.map(l => l.kind))].filter(k => !k.startsWith('challenge')).sort();
  check('D', 'predecessor recorder COMPLETE on the same scripted page', rD.code === 0 && d.summary.status === 'COMPLETE', {code: rD.code, holes: d.summary.holes});
  check('A/D', 'same record kinds as the predecessor (challenge lines aside); one journal line per page callback in both',
    JSON.stringify(kinds(a)) === JSON.stringify(kinds(d)) &&
    a.lines.filter(l => l.kind === 'sample' || l.kind === 'page').length === rbA.records_received,
    {kinds_new: kinds(a), kinds_old: kinds(d), new_page_lines: a.lines.filter(l => l.kind === 'sample' || l.kind === 'page').length, new_records_received: rbA.records_received});
  const perLine = run => { const ls = run.lines.filter(l => l.kind === 'sample'); return ls.reduce((n, l) => n + Buffer.byteLength(JSON.stringify(l)) + 1, 0) / ls.length; };
  check('A/D', 'bytes per sample line, new vs predecessor (diagnostic)', true, {new: Math.round(perLine(a)), old: Math.round(perLine(d))});

  const pass = checks.every(x => x.ok);
  fs.writeFileSync(path.join(OUT, 'CONTROLS.json'), JSON.stringify({schema: 'calibration-10090-lifecycle-control/1', t0: iso(T0), pass, checks}, null, 1) + '\n');
  for (const x of checks) console.log(`${x.ok ? 'PASS' : 'FAIL'}  ${x.case}  ${x.check}${x.detail ? '  ' + JSON.stringify(x.detail) : ''}`);
  console.log(pass ? `ALL ${checks.length} CHECKS PASS` : `${checks.filter(x => !x.ok).length} of ${checks.length} CHECKS FAIL`);
  process.exitCode = pass ? 0 : 1;
})().catch(e => { console.error(e); process.exitCode = 2; });
