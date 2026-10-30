'use strict';
// #10090: the PROPOSED challenge transport, DARK and loopback-only.
//
// One standard pinned node-postgres Client: LISTEN on the reply channel and
// autocommit parameterized `SELECT pg_notify($1, $2)` on the same connection.
// The Client is handed a metered socket, so every encoded byte it exchanges
// (startup, auth, TLS records, framing, notifications) passes one boundary:
//   writes: refused BEFORE they cross the cap (the connection is destroyed);
//   reads:  the chunk that would cross the cap is discarded and counted as
//           overshoot (at most one socket read), then the connection is destroyed.
// Sent + received together are capped (one bidirectional ceiling).
//
// It refuses any non-loopback host: no production connection is admitted.
// The pg module directory is passed in by the caller and its package.json is
// hashed into wire() so a run names the library it used.
const crypto = require('crypto');
const fs = require('fs');
const net = require('net');
const path = require('path');
const {Duplex} = require('stream');
const {LOOPBACK} = require('./contract.cjs');

const REPLY_CHANNEL_RE = /^bl_cr_[0-9a-f]{16}$/;
const REQUEST_CHANNEL_RE = /^bl_cc_[0-9a-f]{16}$/;
const NOTIFY_STATEMENT = 'SELECT pg_notify($1, $2)';

class MeteredSocket extends Duplex {
  constructor(meter) {
    super();
    this.meter = meter;
    this.raw = null;
    this.noDelay = null;
  }

  connect(port, host) {
    const raw = net.connect(port, host);
    this.raw = raw;
    if (this.noDelay !== null) raw.setNoDelay(this.noDelay);
    raw.on('connect', () => this.emit('connect'));
    raw.on('data', chunk => {
      const m = this.meter;
      if (m.sent_bytes + m.received_bytes + chunk.length > m.cap_bytes) {
        m.read_overshoot_bytes += chunk.length;
        m.read_overshoot_chunks++;
        if (chunk.length > m.overshoot_bound_bytes) m.overshoot_over_bound = true;
        this.destroy(Object.assign(new Error('challenge wire cap (read)'), {code: 'EWIRECAP'}));
        return;
      }
      m.received_bytes += chunk.length;
      if (!this.push(chunk)) raw.pause();
    });
    raw.on('end', () => this.push(null));
    raw.on('error', e => this.destroy(e));
    raw.on('close', () => { if (!this.destroyed) this.destroy(); });
    return this;
  }

  _read() { if (this.raw) this.raw.resume(); }

  _write(chunk, encoding, callback) {
    const m = this.meter;
    if (!this.raw || m.sent_bytes + m.received_bytes + chunk.length > m.cap_bytes) {
      m.refused_writes++;
      m.refused_write_bytes += chunk.length;
      const error = Object.assign(new Error('challenge wire cap (write refused)'), {code: 'EWIRECAP'});
      this.destroy(error);
      callback(error);
      return;
    }
    m.sent_bytes += chunk.length;
    this.raw.write(chunk, callback);
  }

  _final(callback) { if (this.raw) this.raw.end(); callback(); }

  _destroy(error, callback) { if (this.raw) this.raw.destroy(); callback(error); }

  setNoDelay(v = true) { this.noDelay = v; if (this.raw) this.raw.setNoDelay(v); return this; }
  setKeepAlive() { return this; } // no keepalive probes: the session lives one case
  ref() { if (this.raw) this.raw.ref(); return this; }
  unref() { if (this.raw) this.raw.unref(); return this; }
}

// Returns connect({onNotification, onClose, wire_cap_bytes, max_pending, statement_timeout_ms, connect_timeout_ms})
// in the shape challenge.cjs injects.
function createPgConnectionFactory({pgModuleDir, connectionString, ssl = false}) {
  const pkgPath = path.join(path.resolve(pgModuleDir), 'package.json');
  const pgPackage = {path: pkgPath, sha256: crypto.createHash('sha256').update(fs.readFileSync(pkgPath)).digest('hex'),
    version: JSON.parse(fs.readFileSync(pkgPath, 'utf8')).version};
  let host;
  try { host = new URL(connectionString).hostname; } catch { throw new Error('connectionString: postgresql:// URL required'); }
  if (!LOOPBACK.has(host)) throw new Error(`pg transport is loopback-only (DARK): ${host} refused`);
  const pg = require(path.resolve(pgModuleDir));

  return async function connect({onNotification, onClose, wire_cap_bytes: capBytes, max_pending: maxPending, statement_timeout_ms: statementMs,
    connect_timeout_ms: connectMs, read_overshoot_bytes: overshootBound}) {
    for (const [k, v] of Object.entries({wire_cap_bytes: capBytes, max_pending: maxPending, statement_timeout_ms: statementMs, connect_timeout_ms: connectMs,
      read_overshoot_bytes: overshootBound})) {
      if (!Number.isSafeInteger(v) || v <= 0) throw new Error(`${k}: positive integer required`);
    }
    const meter = {cap_bytes: capBytes, overshoot_bound_bytes: overshootBound, overshoot_over_bound: false, sent_bytes: 0, received_bytes: 0, read_overshoot_bytes: 0, read_overshoot_chunks: 0,
      refused_writes: 0, refused_write_bytes: 0, notifies: 0, notify_refused_queue: 0, notifications: 0, pending: 0, max_pending: 0};
    let socket = null;
    const client = new pg.Client({connectionString, ssl, keepAlive: false, connectionTimeoutMillis: connectMs,
      application_name: 'bl_clock_challenge', statement_timeout: statementMs,
      stream: () => { socket = new MeteredSocket(meter); return socket; }});
    let closed = false;
    const closeOnce = (reason, error) => { if (closed) return; closed = true; onClose(reason, error); };
    client.on('notification', msg => { meter.notifications++; onNotification(msg.channel, msg.payload); });
    client.on('error', e => closeOnce(e && e.code === 'EWIRECAP' ? 'wire-cap' : 'error', e));
    client.on('end', () => closeOnce('end'));
    await client.connect();
    return {
      async listen(channel) {
        if (!REPLY_CHANNEL_RE.test(channel)) throw new Error(`listen: ${channel} is not a reply channel`);
        await client.query(`LISTEN ${channel}`); // identifier validated above; LISTEN takes no parameter
      },
      notify(channel, payload) {
        if (!REQUEST_CHANNEL_RE.test(channel)) return Promise.reject(new Error(`notify: ${channel} is not a request channel`));
        if (meter.pending >= maxPending) { meter.notify_refused_queue++; return Promise.reject(Object.assign(new Error('notify queue full'), {code: 'EQUEUE'})); }
        meter.pending++;
        meter.max_pending = Math.max(meter.max_pending, meter.pending);
        meter.notifies++;
        return client.query({name: 'bl_cc_notify', text: NOTIFY_STATEMENT, values: [channel, payload]})
          .finally(() => { meter.pending--; });
      },
      wire() { return {...meter, pg_package: pgPackage, counted_at: 'MeteredSocket: every byte between the pg Client (incl. TLS) and the TCP socket'}; },
      async close() {
        closed = true;
        let timer;
        try { await Promise.race([client.end(), new Promise((_, rej) => { timer = setTimeout(() => rej(new Error('pg end timeout')), 1000); })]); }
        catch { if (socket) socket.destroy(); }
        finally { clearTimeout(timer); }
      },
    };
  };
}

module.exports = {createPgConnectionFactory, MeteredSocket, NOTIFY_STATEMENT};
