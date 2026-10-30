'use strict';
// CHALLENGE_PG_MODULE=<dir of pinned pg> CHALLENGE_PG_URL=postgresql://user@127.0.0.1:PORT/db \
//   node --test tools/live-speed-lab/passive-recorder/test_challenge_pg.cjs
// LOOPBACK-ONLY controls of the proposed transport (pg_transport.cjs) and the
// driver over a real local PostgreSQL, with a stand-in producer that answers
// on its own ordinary pg connection. Disposable local state only: LISTEN /
// pg_notify on throwaway channels; nothing is created or written. Without both
// variables every test is skipped and says why.
const test = require('node:test');
const assert = require('node:assert');
const {execFileSync} = require('child_process');
const crypto = require('crypto');
const fs = require('fs');
const net = require('net');
const os = require('os');
const path = require('path');
const tls = require('tls');
const {createPgConnectionFactory} = require('./pg_transport.cjs');
const {createChallengeDriver, CEILINGS, SCHEMA} = require('./challenge.cjs');
const {createJournal} = require('./journal.cjs');

const PG_MODULE = process.env.CHALLENGE_PG_MODULE, PG_URL = process.env.CHALLENGE_PG_URL;
const skip = !PG_MODULE || !PG_URL ? 'CHALLENGE_PG_MODULE and CHALLENGE_PG_URL (loopback) are required' : false;
const pg = skip ? null : require(path.resolve(PG_MODULE));
const OP = crypto.randomBytes(8).toString('hex');
const REPLY = `bl_cr_${OP}`;
const tmp = () => fs.mkdtempSync(path.join(os.tmpdir(), 'challenge-pg-'));
const LIMITS = {connect_timeout_ms: 2000, max_wire_bytes_per_incarnation: CEILINGS.max_wire_bytes_per_incarnation,
  max_wire_bytes_session: CEILINGS.max_wire_bytes_session, max_read_overshoot_bytes: 65536, max_journal_bytes_per_incarnation: CEILINGS.max_journal_bytes_per_incarnation};
const connArgs = (over = {}) => ({onNotification: () => {}, onClose: () => {}, wire_cap_bytes: 1 << 20, max_pending: 4, statement_timeout_ms: 150,
  connect_timeout_ms: 2000, read_overshoot_bytes: 65536, ...over});

// A stand-in producer incarnation: LISTENs on its request channel and replies
// per the schema, stamping its marker with its own monotonic clock.
async function producer({url = PG_URL, token, run, pid, delayFor = () => 0}) {
  const c = new pg.Client({connectionString: url});
  await c.connect();
  let q = 0;
  c.on('notification', m => {
    const lo = process.hrtime.bigint();
    const r = JSON.parse(m.payload);
    if (r.t !== token || r.r !== run) return;
    const hi = process.hrtime.bigint();
    const reply = JSON.stringify({p: SCHEMA.protocol, o: r.o, t: token, r: run, pid, k: r.k, n: r.n, q: ++q,
      m: [Number(lo / 1000n), Number((hi + 999n) / 1000n)]});
    setTimeout(() => c.query('SELECT pg_notify($1, $2)', [`bl_cr_${r.o}`, reply]).catch(() => {}), delayFor(r.k));
  });
  await c.query(`LISTEN bl_cc_${token}`);
  return c;
}

function realClock() {
  const {performance} = require('perf_hooks');
  const t0 = performance.now() + 1500; // T0 1.5 s from now
  return {mono: () => performance.now(), wall: () => Date.now(), sinceT0: m => [m - t0, m - t0]};
}

test('pg transport: refuses a non-loopback host before any connection', {skip}, () => {
  assert.throws(() => createPgConnectionFactory({pgModuleDir: PG_MODULE, connectionString: 'postgresql://u@db.example.com:5432/x'}), /loopback-only/);
});

test('pg driver: two incarnations over one real connection, every slot answered, S < R, wire counted at the socket', {skip}, async () => {
  const tokens = [crypto.randomBytes(8).toString('hex'), crypto.randomBytes(8).toString('hex')];
  const prods = await Promise.all(tokens.map((t, i) => producer({token: t, run: `run${i}`, pid: 4000 + i})));
  const dir = tmp();
  const journal = createJournal({dir, limits: {max_record_bytes: 262144, max_saved_bytes: 50_000_000, reserved_stop_bytes: 65536}, onExhausted: () => {}});
  const cfg = {operation: OP, reply_channel: REPLY, roster: tokens.map((t, i) => ({token: t, channel: `bl_cc_${t}`, run: `run${i}`, pid: 4000 + i, role: 'standin'})),
    slots: {first_offset_ms: 0, slot_ms: 250, count: 12}, deadline_ms: 150, limits: LIMITS};
  const driver = createChallengeDriver({cfg, connect: createPgConnectionFactory({pgModuleDir: PG_MODULE, connectionString: PG_URL}), clock: realClock(), journal, setTimer: setTimeout});
  assert.strictEqual(await driver.start(), 'RUNNING');
  await new Promise(r => setTimeout(r, 1500 + 12 * 250 + 300));
  await driver.stop('deadline');
  const s = driver.summary();
  journal.close();
  await Promise.all(prods.map(p => p.end()));
  const ex = fs.readFileSync(path.join(dir, 'records.jsonl'), 'utf8').trim().split('\n').map(l => JSON.parse(l)).filter(l => l.kind === 'challenge-exchange');
  assert.strictEqual(s.status, 'COMPLETE', JSON.stringify({holes: s.holes, drops: s.drops, d: s.domains.map(d => [d.sent, d.timely, d.late, d.no_reply, d.gaps])}));
  assert.strictEqual(ex.length, 24);
  assert.ok(ex.every(e => e.S < e.R && e.outcome === 'reply'));
  assert.strictEqual(s.wire.pg_package.version, require(path.join(path.resolve(PG_MODULE), 'package.json')).version);
  assert.ok(s.wire.sent_bytes > 0 && s.wire.received_bytes > 0 && s.wire.sent_bytes + s.wire.received_bytes <= s.wire.cap_bytes);
  assert.strictEqual(s.wire.cap_bytes, 2 * CEILINGS.max_wire_bytes_per_incarnation + CEILINGS.max_wire_bytes_session);
  console.log(`# wire after 24 exchanges (plaintext loopback): sent ${s.wire.sent_bytes} B, received ${s.wire.received_bytes} B; R-S max ${Math.max(...ex.map(e => e.R - e.S)).toFixed(2)} ms`);
});

test('pg driver: a producer reply later than the deadline is retained as late', {skip}, async () => {
  const token = crypto.randomBytes(8).toString('hex');
  const prod = await producer({token, run: 'late', pid: 4100, delayFor: k => (k === 2 ? 320 : 0)});
  const dir = tmp();
  const journal = createJournal({dir, limits: {max_record_bytes: 262144, max_saved_bytes: 50_000_000, reserved_stop_bytes: 65536}, onExhausted: () => {}});
  const cfg = {operation: OP, reply_channel: REPLY, roster: [{token, channel: `bl_cc_${token}`, run: 'late', pid: 4100, role: 'standin'}],
    slots: {first_offset_ms: 0, slot_ms: 250, count: 6}, deadline_ms: 150, limits: LIMITS};
  const driver = createChallengeDriver({cfg, connect: createPgConnectionFactory({pgModuleDir: PG_MODULE, connectionString: PG_URL}), clock: realClock(), journal, setTimer: setTimeout});
  await driver.start();
  await new Promise(r => setTimeout(r, 1500 + 6 * 250 + 500));
  await driver.stop('deadline');
  journal.close();
  await prod.end();
  const ex = fs.readFileSync(path.join(dir, 'records.jsonl'), 'utf8').trim().split('\n').map(l => JSON.parse(l)).filter(l => l.kind === 'challenge-exchange' && l.k === 2);
  assert.deepStrictEqual(ex.map(e => e.outcome), ['no-reply', 'late-reply']);
  assert.ok(ex[1].R - ex[1].S > 300);
});

test('pg transport: a write that would cross the cap is refused before it is sent, and the connection closes', {skip}, async () => {
  let closed = null;
  const connect = createPgConnectionFactory({pgModuleDir: PG_MODULE, connectionString: PG_URL});
  const conn = await connect(connArgs({wire_cap_bytes: 2500, onClose: (r, e) => { closed = r; }}));
  const w0 = conn.wire();
  let refused = null;
  for (let i = 0; i < 50 && !refused; i++) {
    try { await conn.notify(`bl_cc_${'0'.repeat(16)}`, 'x'.repeat(200)); } catch (e) { refused = e; }
  }
  const w = conn.wire();
  await conn.close();
  assert.ok(refused, 'a notify was refused');
  assert.strictEqual(closed, 'wire-cap');
  assert.ok(w.refused_writes >= 1);
  assert.ok(w.sent_bytes + w.received_bytes <= 2500, `counted ${w.sent_bytes}+${w.received_bytes}`);
  assert.ok(w0.sent_bytes > 0 && w0.received_bytes > 0, 'startup and auth bytes are counted too');
});

test('pg transport: a read that would cross the cap is discarded, counted as one bounded overshoot, and closes the connection', {skip}, async () => {
  let closed = null;
  const connect = createPgConnectionFactory({pgModuleDir: PG_MODULE, connectionString: PG_URL});
  const conn = await connect(connArgs({wire_cap_bytes: 40000, onClose: r => { closed = r; }}));
  await conn.listen(REPLY);
  const flood = new pg.Client({connectionString: PG_URL});
  await flood.connect();
  for (let i = 0; i < 12 && !closed; i++) await flood.query('SELECT pg_notify($1, $2)', [REPLY, 'y'.repeat(7900)]);
  await new Promise(r => setTimeout(r, 200));
  await flood.end();
  const w = conn.wire();
  await conn.close();
  assert.strictEqual(closed, 'wire-cap');
  assert.ok(w.sent_bytes + w.received_bytes <= 40000);
  assert.strictEqual(w.read_overshoot_chunks, 1);
  assert.ok(w.read_overshoot_bytes > 0 && w.read_overshoot_bytes <= 65536);
  assert.strictEqual(w.overshoot_over_bound, false);
});

// TLS: a local shim answers SSLRequest, terminates TLS with a throwaway
// self-signed certificate and pipes plaintext to the same local server.
test('pg transport over TLS: handshake, records and framing are counted at the socket', {skip: skip || (() => { try { execFileSync('openssl', ['version']); return false; } catch { return 'openssl unavailable'; } })()}, async () => {
  const dir = tmp();
  execFileSync('openssl', ['req', '-x509', '-newkey', 'rsa:2048', '-nodes', '-keyout', path.join(dir, 'k.pem'), '-out', path.join(dir, 'c.pem'), '-days', '1', '-subj', '/CN=127.0.0.1'], {stdio: 'ignore'});
  const key = fs.readFileSync(path.join(dir, 'k.pem')), cert = fs.readFileSync(path.join(dir, 'c.pem'));
  const up = new URL(PG_URL);
  const shim = net.createServer(sock => sock.once('data', b => {
    if (b.length !== 8 || b.readUInt32BE(4) !== 80877103) return sock.destroy();
    sock.write('S');
    const t = new tls.TLSSocket(sock, {isServer: true, key, cert});
    const u = net.connect(Number(up.port || 5432), up.hostname);
    t.pipe(u); u.pipe(t);
    t.on('error', () => u.destroy()); u.on('error', () => t.destroy());
  }));
  await new Promise(r => shim.listen(0, '127.0.0.1', r));
  const shimUrl = new URL(PG_URL); shimUrl.port = String(shim.address().port);
  const token = crypto.randomBytes(8).toString('hex');
  const prod = await producer({token, run: 'tls', pid: 4200});
  const notes = [];
  const connect = createPgConnectionFactory({pgModuleDir: PG_MODULE, connectionString: shimUrl.toString(), ssl: {rejectUnauthorized: false}});
  const conn = await connect(connArgs({onNotification: (c, p) => notes.push(p)}));
  const hs = conn.wire();
  await conn.listen(REPLY);
  const payload = k => JSON.stringify({p: SCHEMA.protocol, o: OP, t: token, r: 'tls', k, n: crypto.randomBytes(16).toString('hex')});
  await conn.notify(`bl_cc_${token}`, payload(0));
  await new Promise(r => setTimeout(r, 100));
  const w0 = conn.wire();
  for (let k = 1; k <= 40; k++) { await conn.notify(`bl_cc_${token}`, payload(k)); await new Promise(r => setTimeout(r, 10)); }
  await new Promise(r => setTimeout(r, 200));
  const w1 = conn.wire();
  await conn.close();
  await prod.end();
  shim.close();
  assert.strictEqual(notes.length, 41);
  const per = {sent: (w1.sent_bytes - w0.sent_bytes) / 40, received: (w1.received_bytes - w0.received_bytes) / 40};
  console.log(`# TLS (local shim, self-signed RSA-2048): handshake+auth sent ${hs.sent_bytes} B received ${hs.received_bytes} B; steady per exchange sent ${per.sent} B received ${per.received} B`);
  // A TLS record adds framing, so the steady exchange is larger than its payloads; 760 slots stay far below the 2 MiB proposal.
  assert.ok(per.sent > 120 && per.received > 170);
  assert.ok(760 * (per.sent + per.received) < CEILINGS.max_wire_bytes_per_incarnation);
});
