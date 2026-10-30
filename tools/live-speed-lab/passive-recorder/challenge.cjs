'use strict';
// #10090: causal clock challenge driver, DARK. Inactive unless the grant names
// a `challenge`; production scope refuses one (contract.cjs) until a transport
// is admitted.
//
// Runs inside the existing recorder: its clock (collector C), journal, timers
// and teardown. Every 250 ms slot it sends one nonce to each rostered producer
// incarnation over one injected connection and stamps
//   S = C immediately before the send,
//   R = C at the first line of the reply callback, before size check, parse or journal.
// The reply repeats the binding and carries the producer's marker [lo, hi] in
// its own monotonic domain. Nothing here converts between clocks: a genuine
// reply only proves S < marker < R in real time. One outstanding request per
// incarnation, no retry, no catch-up: a slot that cannot be sent is a gap.
const crypto = require('crypto');
const SCHEMA = require('./challenge_schema.json');
const {parseStrictJson} = require('./contract.cjs');

// Protocol ceilings from the 20261030T0615Z contract (proposed code limits, not
// grants): a grant may name less, never more.
const MAX_DOMAINS = 16;
const MAX_SLOTS = 760;
const MIN_SLOT_MS = 250;
const CEILINGS = {connect_timeout_ms: 2000, max_wire_bytes_per_incarnation: 2 * 1048576, max_wire_bytes_session: 1048576,
  max_read_overshoot_bytes: 65536, max_journal_bytes_per_incarnation: 2 * 1048576};
const GAP_RANGES_KEPT = 64;
const REQUEST_RE = new RegExp(SCHEMA.request.channel_pattern);
const REPLY_RE = new RegExp(SCHEMA.reply.channel_pattern);
const HEX16 = /^[0-9a-f]{16}$/;
const RUN_RE = /^[0-9a-z_-]{1,32}$/;

const isSafeNonNeg = v => Number.isSafeInteger(v) && v >= 0;

function inactiveSummary() { return {status: 'INACTIVE'}; }

// cfg is a validated grant.challenge. connect({onNotification, onClose,
// connect_timeout_ms, wire_cap_bytes, max_pending, statement_timeout_ms,
// read_overshoot_bytes}) resolves to {listen(channel), notify(channel, payload),
// wire(), close()}. onNotification(channel, payload) must be called
// synchronously as each notification is delivered.
function createChallengeDriver({cfg, connect, clock, journal, setTimer}) {
  const {operation, reply_channel: replyChannel, roster, slots, deadline_ms: deadlineMs, limits} = cfg;
  const domains = roster.map((r, i) => ({i, token: r.token, channel: r.channel, run: r.run, pid: r.pid, role: r.role,
    ex: new Array(slots.count).fill(null), outstanding: null, stopped: null,
    sent: 0, timely: 0, late: 0, no_reply: 0, notify_failed: 0, skipped: 0, journal_bytes: 0, attributed_bytes: 0, gaps: [], gap_ranges_dropped: 0}));
  const byToken = new Map(domains.map(d => [d.token, d]));
  const drops = {};
  const counters = {notifications: 0, after_stop: 0, pending_notifies: 0, max_pending_notifies: 0, slots_fired: 0, slots_missed: 0};
  const holes = new Set();
  let status = 'CONNECTING';
  let conn = null, closeReason = null, accepting = false, lastSlot = -1, connectMs = null;

  const drop = (reason, detail) => { drops[reason] = (drops[reason] || 0) + 1; if (detail && drops[reason] <= 3) journal.append('challenge-drop', {reason, ...detail}); };
  const since = m => clock.sinceT0(m);
  const gap = (d, k, reason) => {
    d.skipped++;
    const last = d.gaps[d.gaps.length - 1];
    if (last && last[2] === reason && last[1] === k - 1) last[1] = k;
    else if (d.gaps.length < GAP_RANGES_KEPT) d.gaps.push([k, k, reason]);
    else d.gap_ranges_dropped++;
  };
  // A domain's journal spend is measured on the journal itself, not estimated.
  const write = (d, kind, body) => {
    const before = journal.stats.saved_bytes;
    const id = journal.append(kind, body);
    d.journal_bytes += journal.stats.saved_bytes - before;
    if (d.journal_bytes > limits.max_journal_bytes_per_incarnation && !d.stopped) stopDomain(d, 'journal-cap');
    return id;
  };
  function stopDomain(d, reason) { d.stopped = {reason, since_t0_ms: since(clock.mono())}; holes.add(`challenge-domain-stopped:${reason}`); }

  function expire(d, atStop) {
    const ex = d.outstanding;
    d.outstanding = null;
    if (!ex || ex.replied) return;
    ex.expired = true;
    d.no_reply++;
    write(d, 'challenge-exchange', {domain: d.i, token: d.token, k: ex.k, n: ex.n, S: ex.S, A: ex.A ?? null, R: null,
      s_since_t0_ms: since(ex.S), outcome: atStop ? 'no-reply-at-stop' : 'no-reply', notify_error: ex.notify_error ?? null});
  }

  function fire(k) {
    counters.slots_fired++;
    for (const d of domains) {
      if (d.stopped) { gap(d, k, `stopped:${d.stopped.reason}`); continue; }
      if (status !== 'RUNNING') { gap(d, k, status === 'CONNECTING' ? 'not-connected' : 'transport-down'); continue; }
      if (d.outstanding) {
        if (clock.mono() - d.outstanding.S >= deadlineMs) expire(d, false);
        else { gap(d, k, 'outstanding'); continue; }
      }
      if (counters.pending_notifies >= domains.length) { gap(d, k, 'transport-queue-full'); continue; }
      const n = crypto.randomBytes(16).toString('hex');
      const payload = JSON.stringify({p: SCHEMA.protocol, o: operation, t: d.token, r: d.run, k, n});
      const bytes = Buffer.byteLength(payload);
      if (bytes > SCHEMA.request.max_bytes) { gap(d, k, 'request-oversize'); drop('request-oversize', {domain: d.i, bytes}); continue; }
      const attributed = bytes + Buffer.byteLength(d.channel);
      if (d.attributed_bytes + attributed > limits.max_wire_bytes_per_incarnation) { stopDomain(d, 'attributed-wire-cap'); gap(d, k, 'stopped:attributed-wire-cap'); continue; }
      d.attributed_bytes += attributed;
      const ex = {k, n, S: null, A: null, replied: false};
      d.ex[k] = ex;
      d.outstanding = ex;
      d.sent++;
      counters.pending_notifies++;
      counters.max_pending_notifies = Math.max(counters.max_pending_notifies, counters.pending_notifies);
      ex.S = clock.mono();
      let p;
      try { p = Promise.resolve(conn.notify(d.channel, payload)); } catch (e) { p = Promise.reject(e); }
      p.then(() => { ex.A = clock.mono(); counters.pending_notifies--; }, e => {
        counters.pending_notifies--;
        ex.notify_error = String(e && (e.code || e.message) || e).slice(0, 200);
        d.notify_failed++;
        holes.add('challenge-notify-failed');
      });
    }
  }

  // One timer chain on C. A late tick never sends the slots it missed.
  function tick() {
    const now = since(clock.mono())[0];
    const k = Math.floor((now - slots.first_offset_ms) / slots.slot_ms);
    if (!accepting && status !== 'CONNECTING' && status !== 'RUNNING') return;
    if (k >= slots.count) return;
    if (k >= 0 && k > lastSlot) {
      for (let j = lastSlot + 1; j < k; j++) { counters.slots_missed++; for (const d of domains) gap(d, j, 'timer-late'); }
      fire(k);
      lastSlot = k;
    }
    const next = slots.first_offset_ms + (Math.max(k, lastSlot) + 1) * slots.slot_ms;
    if (Math.max(k, lastSlot) + 1 < slots.count) setTimer(tick, Math.max(0, next - now));
  }

  function onNotification(channel, payload) {
    const R = clock.mono(); // collector receipt: first line, before any check
    if (!accepting) { counters.after_stop++; return; }
    counters.notifications++;
    if (channel !== replyChannel) return drop('foreign-channel', {channel: String(channel).slice(0, 64)});
    if (typeof payload !== 'string') return drop('reply-not-text');
    const bytes = Buffer.byteLength(payload);
    if (bytes > SCHEMA.reply.max_bytes) return drop('reply-oversize', {bytes});
    let parsed;
    try { parsed = parseStrictJson(payload); } catch { return drop('reply-malformed', {raw: payload.slice(0, 128)}); }
    const v = parsed.value;
    if (parsed.duplicates.length || !v || typeof v !== 'object' || Array.isArray(v)) return drop('reply-malformed', {raw: payload.slice(0, 128)});
    const keys = Object.keys(v);
    if (keys.length !== SCHEMA.reply.keys.length || keys.some((key, i) => key !== SCHEMA.reply.keys[i])) return drop('reply-wrong-keys', {keys: keys.slice(0, 12)});
    if (v.p !== SCHEMA.protocol || v.o !== operation) return drop('reply-wrong-operation', {raw: payload.slice(0, 128)});
    const d = byToken.get(v.t);
    if (!d) return drop('reply-unknown-token', {t: String(v.t).slice(0, 32)});
    if (v.r !== d.run || v.pid !== d.pid) return drop('reply-wrong-binding', {domain: d.i, r: v.r, pid: v.pid});
    if (!Number.isSafeInteger(v.k) || v.k < 0 || v.k >= slots.count) return drop('reply-unmatched', {domain: d.i, k: v.k});
    const ex = d.ex[v.k];
    if (!ex || ex.n !== v.n) return drop('reply-unmatched', {domain: d.i, k: v.k});
    if (ex.replied) return drop('reply-duplicate', {domain: d.i, k: v.k});
    const m = v.m;
    if (!Array.isArray(m) || m.length !== 2 || !isSafeNonNeg(m[0]) || !isSafeNonNeg(m[1]) || m[0] > m[1] || !Number.isSafeInteger(v.q) || v.q < 1) {
      return drop('reply-bad-marker', {domain: d.i, k: v.k});
    }
    ex.replied = true;
    const timely = !ex.expired && R - ex.S <= deadlineMs;
    if (d.outstanding === ex) d.outstanding = null;
    if (timely) d.timely++; else d.late++;
    d.attributed_bytes += bytes + Buffer.byteLength(channel);
    write(d, 'challenge-exchange', {domain: d.i, token: d.token, k: v.k, n: v.n, S: ex.S, A: ex.A, R,
      s_since_t0_ms: since(ex.S), r_since_t0_ms: since(R), outcome: timely ? 'reply' : 'late-reply', reply_bytes: bytes, raw: payload});
    if (d.attributed_bytes > limits.max_wire_bytes_per_incarnation && !d.stopped) stopDomain(d, 'attributed-wire-cap');
  }

  function onClose(reason, error) {
    if (closeReason) return;
    closeReason = {reason: String(reason), error: error ? String(error.code || error.message || error).slice(0, 200) : null, since_t0_ms: since(clock.mono())};
    if (status === 'RUNNING' || status === 'CONNECTING') { status = 'TRANSPORT-DOWN'; holes.add(`challenge-transport-${closeReason.reason}`); }
  }

  // Starts the slot chain at once (slots before the connection is listening are
  // gaps) and makes exactly one bounded connect attempt.
  async function start() {
    tick();
    const c0 = clock.mono();
    const timeout = new Promise(resolve => { setTimer(() => resolve('timeout'), limits.connect_timeout_ms); });
    const attempt = (async () => {
      const c = await connect({onNotification, onClose, connect_timeout_ms: limits.connect_timeout_ms,
        wire_cap_bytes: limits.max_wire_bytes_per_incarnation * domains.length + limits.max_wire_bytes_session,
        max_pending: domains.length, statement_timeout_ms: deadlineMs, read_overshoot_bytes: limits.max_read_overshoot_bytes});
      conn = c;
      await c.listen(replyChannel);
      return 'ok';
    })().catch(e => { closeReason = closeReason || {reason: 'connect-failed', error: String(e && (e.code || e.message) || e).slice(0, 200)}; return 'failed'; });
    const outcome = await Promise.race([attempt, timeout]);
    connectMs = clock.mono() - c0;
    if (outcome === 'ok' && status === 'CONNECTING') { status = 'RUNNING'; accepting = true; }
    else {
      if (status === 'CONNECTING') status = 'UNAVAILABLE';
      holes.add(outcome === 'timeout' ? 'challenge-connect-timeout' : 'challenge-connect-failed');
      // A connection that arrives after the bound is closed, never used.
      attempt.then(() => { if (conn) Promise.resolve(conn.close()).catch(() => {}); });
    }
    journal.append('challenge-start', {status, connect_ms: connectMs, close: closeReason, since_t0_ms: since(clock.mono())});
    return status;
  }

  async function stop(reason) {
    accepting = false;
    for (const d of domains) expire(d, true);
    const wasRunning = status === 'RUNNING';
    if (status === 'RUNNING' || status === 'CONNECTING') status = 'STOPPED';
    if (conn) await conn.close();
    return {reason, was_running: wasRunning};
  }

  function summary() {
    const perDomain = domains.map(d => ({i: d.i, token: d.token, role: d.role, run: d.run, pid: d.pid, sent: d.sent, timely: d.timely, late: d.late,
      no_reply: d.no_reply, notify_failed: d.notify_failed, skipped: d.skipped, journal_bytes: d.journal_bytes, attributed_bytes: d.attributed_bytes,
      stopped: d.stopped, gaps: d.gaps, gap_ranges_dropped: d.gap_ranges_dropped}));
    const complete = closeReason === null && perDomain.every(d => d.timely === slots.count && !d.stopped) && Object.keys(drops).length === 0;
    return {schema_sha256: crypto.createHash('sha256').update(JSON.stringify(SCHEMA)).digest('hex'), protocol: SCHEMA.protocol,
      status: status === 'UNAVAILABLE' ? 'UNAVAILABLE' : complete ? 'COMPLETE' : 'INCOMPLETE', driver_state: status,
      operation, reply_channel: replyChannel, slots, deadline_ms: deadlineMs, limits, connect_ms: connectMs, close: closeReason,
      counters, drops, holes: [...holes].sort(), wire: conn && conn.wire ? conn.wire() : null, domains: perDomain,
      semantics: 'Causal order only: a genuine reply proves S < producer marker < R. Collector-time bounds; no clock conversion, no physical-duration claim. Late replies are retained as late.'};
  }

  return {start, stop, summary, onNotification, onClose, get status() { return status; }, domains};
}

// Offline validation of grant.challenge (shape and ceilings). Values are the
// grant's; the only constants here are protocol ceilings, never defaults.
function validateChallenge(c, refuse) {
  const isObj = v => v && typeof v === 'object' && !Array.isArray(v);
  const posInt = v => Number.isSafeInteger(v) && v > 0;
  const exact = (o, keys, where) => {
    if (!isObj(o)) { refuse(`${where}: object required`); return false; }
    for (const k of keys) if (!(k in o)) refuse(`${where}: missing ${k}`);
    for (const k of Object.keys(o)) if (!keys.includes(k)) refuse(`${where}: unknown ${k}`);
    return keys.every(k => k in o);
  };
  if (!exact(c, ['operation', 'reply_channel', 'roster', 'slots', 'deadline_ms', 'limits'], 'grant.challenge')) return;
  if (!HEX16.test(c.operation)) refuse('grant.challenge.operation: 16 lowercase hex');
  if (c.reply_channel !== `bl_cr_${c.operation}` || !REPLY_RE.test(c.reply_channel)) refuse('grant.challenge.reply_channel: must be bl_cr_<operation>');
  if (!Array.isArray(c.roster) || c.roster.length < 1 || c.roster.length > MAX_DOMAINS) refuse(`grant.challenge.roster: 1..${MAX_DOMAINS} incarnations`);
  else {
    const tokens = new Set();
    c.roster.forEach((r, i) => {
      if (!exact(r, ['token', 'channel', 'run', 'pid', 'role'], `grant.challenge.roster[${i}]`)) return;
      if (!HEX16.test(r.token)) refuse(`grant.challenge.roster[${i}].token: 16 lowercase hex`);
      if (r.channel !== `bl_cc_${r.token}` || !REQUEST_RE.test(r.channel)) refuse(`grant.challenge.roster[${i}].channel: must be bl_cc_<token>`);
      if (typeof r.run !== 'string' || !RUN_RE.test(r.run)) refuse(`grant.challenge.roster[${i}].run: 1..32 of [0-9a-z_-]`);
      if (!posInt(r.pid)) refuse(`grant.challenge.roster[${i}].pid: positive integer`);
      if (typeof r.role !== 'string' || !r.role) refuse(`grant.challenge.roster[${i}].role: required`);
      if (tokens.has(r.token)) refuse(`grant.challenge.roster[${i}].token: duplicate`);
      tokens.add(r.token);
    });
  }
  if (exact(c.slots, ['first_offset_ms', 'slot_ms', 'count'], 'grant.challenge.slots')) {
    const {first_offset_ms: f, slot_ms: s, count: n} = c.slots;
    if (!Number.isSafeInteger(f) || !posInt(s) || !posInt(n)) refuse('grant.challenge.slots: integers required');
    else {
      if (n > MAX_SLOTS) refuse(`grant.challenge.slots.count: at most ${MAX_SLOTS}`);
      if (s < MIN_SLOT_MS) refuse(`grant.challenge.slots.slot_ms: at least ${MIN_SLOT_MS}`);
      if (f < -5000 || f + (n - 1) * s >= 185000) refuse('grant.challenge.slots: every slot inside the acquisition window -5000..185000');
    }
  }
  if (!posInt(c.deadline_ms) || (isObj(c.slots) && posInt(c.slots.slot_ms) && c.deadline_ms >= c.slots.slot_ms)) refuse('grant.challenge.deadline_ms: positive and below slot_ms');
  if (exact(c.limits, ['connect_timeout_ms', 'max_wire_bytes_per_incarnation', 'max_wire_bytes_session', 'max_read_overshoot_bytes', 'max_journal_bytes_per_incarnation'], 'grant.challenge.limits')) {
    for (const k of Object.keys(c.limits)) {
      if (!posInt(c.limits[k])) refuse(`grant.challenge.limits.${k}: finite positive integer required`);
      else if (c.limits[k] > CEILINGS[k]) refuse(`grant.challenge.limits.${k}: at most ${CEILINGS[k]}`);
    }
  }
}

module.exports = {createChallengeDriver, validateChallenge, inactiveSummary, MAX_DOMAINS, MAX_SLOTS, MIN_SLOT_MS, CEILINGS, SCHEMA};
