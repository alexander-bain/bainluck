#!/usr/bin/env node
'use strict';
// #10090 INTEROP control, LOCAL ONLY: this recorder's challenge driver and pg
// transport against the producer half's REAL code (Authority's clock_bridge
// markers, PR #11775), run as one Python producer incarnation on a local
// disposable Postgres (LISTEN/NOTIFY only).
//
//   node interop_authority_producer.cjs --producer-source PATH/clock_bridge.py --pg-module DIR
//        --pg-url postgresql://user@127.0.0.1:PORT/db --out NEW_DIR
//
// A binder listens on cmr_<case> before the producer arms and takes the roster
// from its one `bind`; the driver then challenges 48 slots. Collector and
// producer clocks are NOT compared (different processes; on macOS Node counts
// sleep and Python does not). Exit 0 only if the challenge is COMPLETE.
const args = {};
for (let i = 2; i < process.argv.length; i += 2) args[process.argv[i].slice(2)] = process.argv[i + 1];
for (const k of ['producer-source', 'pg-module', 'pg-url', 'out']) if (!args[k]) { console.error(`--${k} required`); process.exit(2); }
if (!['127.0.0.1', 'localhost'].includes(new URL(args['pg-url']).hostname)) { console.error('--pg-url must be loopback'); process.exit(3); }
const PR = __dirname;
const PG = require('path').resolve(args['pg-module']);
const URL_ = args['pg-url'];
const OUT = require('path').resolve(args.out);
if (require('fs').existsSync(OUT)) { console.error(`--out exists: ${OUT}`); process.exit(3); }
require('fs').mkdirSync(OUT);
const {spawn} = require('child_process');
const fs = require('fs'), os = require('os'), path = require('path'), crypto = require('crypto');
const pg = require(PG);
const {createChallengeDriver, validateChallenge, CEILINGS} = require(PR + '/challenge.cjs');
const {createPgConnectionFactory} = require(PR + '/pg_transport.cjs');
const {createJournal} = require(PR + '/journal.cjs');
const {performance} = require('perf_hooks');
(async () => {
  const CASE = `interop${crypto.randomBytes(4).toString('hex')}`;
  // 1. Roster binder: listen for the producer's one bind before it arms.
  const binder = new pg.Client({connectionString: URL_}); await binder.connect();
  const binds = [];
  binder.on('notification', m => binds.push(JSON.parse(m.payload)));
  await binder.query(`LISTEN cmr_${CASE}`);
  const prod = spawn('python3', [path.join(__dirname, 'interop_producer.py'), URL_, CASE, '25', path.resolve(args['producer-source'])], {stdio: ['ignore', 'pipe', 'pipe']});
  let plog = ''; prod.stdout.on('data', d => { plog += d; }); prod.stderr.on('data', d => { plog += d; });
  const t0w = Date.now();
  while (!binds.some(b => b.k === 'bind') && Date.now() - t0w < 10000) await new Promise(r => setTimeout(r, 20));
  const bind = binds.find(b => b.k === 'bind');
  if (!bind) { console.log('NO BIND', plog); process.exit(1); }
  await binder.end();
  console.log('bind', JSON.stringify(bind));
  // 2. Grant roster from the bind; T0 2 s from now; 48 slots (12 s).
  const cfg = {case: CASE, reply_channel: `cmr_${CASE}`, roster: [{token: bind.tok, channel: bind.ch, run: bind.run, pid: bind.pid, role: 'kalshi-real-producer'}],
    slots: {first_offset_ms: 0, slot_ms: 250, count: 48}, deadline_ms: 150,
    limits: {connect_timeout_ms: 2000, max_wire_bytes_per_incarnation: CEILINGS.max_wire_bytes_per_incarnation, max_wire_bytes_session: CEILINGS.max_wire_bytes_session, max_read_overshoot_bytes: 65536, max_journal_bytes_per_incarnation: CEILINGS.max_journal_bytes_per_incarnation}};
  const refusals = []; validateChallenge(cfg, m => refusals.push(m));
  if (refusals.length) { console.log('REFUSED', refusals); process.exit(1); }
  const T0 = performance.now() + 2000;
  const clock = {mono: () => performance.now(), wall: () => Date.now(), sinceT0: m => [m - T0, m - T0]};
  const dir = path.join(OUT, 'journal'); fs.mkdirSync(dir);
  const journal = createJournal({dir, limits: {max_record_bytes: 262144, max_saved_bytes: 50_000_000, reserved_stop_bytes: 65536}, onExhausted: () => {}});
  const driver = createChallengeDriver({cfg, connect: createPgConnectionFactory({pgModuleDir: PG, connectionString: URL_}), clock, journal, setTimer: setTimeout});
  console.log('driver', await driver.start());
  await new Promise(r => setTimeout(r, 2000 + 48 * 250 + 400));
  await driver.stop('deadline');
  const s = driver.summary();
  journal.close();
  const lines = fs.readFileSync(path.join(dir, 'records.jsonl'), 'utf8').trim().split('\n').map(l => JSON.parse(l));
  const ex = lines.filter(l => l.kind === 'challenge-exchange');
  const replies = ex.filter(e => e.raw).map(e => JSON.parse(e.raw));
  const out = {case: CASE, status: s.status, holes: s.holes, drops: s.drops, domain: s.domains.map(d => ({sent: d.sent, timely: d.timely, late: d.late, no_reply: d.no_reply, skipped: d.skipped, producer_faults: d.producer_faults})),
    exchanges: ex.length, all_S_lt_R: ex.every(e => e.S < e.R), producer_lo_le_hi: replies.every(r => r.lo <= r.hi), producer_i_seq: replies.map(r => r.i).join(',') === replies.map((_, j) => j + 1).join(','),
    rtt_ms: (() => { const v = ex.map(e => e.R - e.S).sort((a, b) => a - b); return {p50: v[v.length >> 1], max: v[v.length - 1]}; })(),
    producer_hold_ms: (() => { const v = replies.map(r => (r.hi - r.lo) * 1000).sort((a, b) => a - b); return {p50: v[v.length >> 1], max: v[v.length - 1]}; })(),
    wire: {sent: s.wire.sent_bytes, received: s.wire.received_bytes, per_exchange: (s.wire.sent_bytes + s.wire.received_bytes) / Math.max(1, ex.length)}, sample_reply: ex[0] && ex[0].raw, journal_dir: dir};
  out.producer_source = {path: path.resolve(args['producer-source']), sha256: crypto.createHash('sha256').update(fs.readFileSync(args['producer-source'])).digest('hex')};
  fs.writeFileSync(path.join(OUT, 'INTEROP.json'), JSON.stringify(out, null, 1));
  console.log(JSON.stringify(out, null, 1));
  await new Promise(r => prod.on('close', r));
  fs.writeFileSync(path.join(OUT, 'producer.log'), plog);
  console.log('producer lines', plog.split('\n').filter(Boolean).map(l => l.split(' ')[0]).reduce((m, k) => (m[k] = (m[k] || 0) + 1, m), {}));
  process.exitCode = s.status === 'COMPLETE' ? 0 : 1;
})().catch(e => { console.error(e); process.exitCode = 2; });
