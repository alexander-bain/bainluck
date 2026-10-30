'use strict';
// #10090 / #11674: bounded, immediately persisted JSONL.
//
// Every record is written with writeSync the moment it arrives, under one
// sequential id across all record kinds. Each line is capped at
// max_record_bytes (an oversized record is replaced by a marker carrying its
// size and hash, never dropped silently). The aggregate is capped at
// max_saved_bytes, of which reserved_stop_bytes is kept back for the STOP and
// the summary: ordinary records stop before they can touch that reserve.
const crypto = require('crypto');
const fs = require('fs');
const path = require('path');
const {MINIMAL_STRING_CHARS, MINIMAL_LIST_ITEMS} = require('./contract.cjs');

// The fallback STOP and SUMMARY, clipped so their size has a fixed bound that
// the contract's MIN_RESERVED_STOP_BYTES floor covers.
function minimalForms({status, reason, holes, fault_kinds: kinds}) {
  const clip = v => String(v).slice(0, MINIMAL_STRING_CHARS);
  const list = xs => (Array.isArray(xs) ? xs : []).slice(0, MINIMAL_LIST_ITEMS).map(clip);
  return {stop: {status: clip(status), reason: clip(reason)},
    summary: {status: clip(status), reason: clip(reason), holes: list(holes), fault_kinds: list(kinds)}};
}

function createJournal({dir, limits, onExhausted, fault = null}) {
  const file = path.join(dir, 'records.jsonl');
  const fd = fs.openSync(file, 'wx');
  const stats = {records: 0, saved_bytes: 0, oversize: 0, refused: 0, refused_bytes: 0, write_failures: 0,
    reserved_used_bytes: 0};
  let seq = 0;
  let exhausted = false;
  let closed = false;
  const ordinaryCap = limits.max_saved_bytes - limits.reserved_stop_bytes;

  function write(line) {
    if (fault && fault.beforeWrite) fault.beforeWrite(stats);
    fs.writeSync(fd, line);
  }

  // `keep` (optional): small receipt fields an oversize marker retains, so a
  // replaced record still carries its collector receipt and the acks it held.
  // Dropped from the marker (and counted) only if the marker would not fit.
  function append(kind, body, keep = null) {
    // A page callback that lands after close is counted, never written: the fd
    // number may already belong to another file.
    if (closed) { stats.late_records = (stats.late_records || 0) + 1; return null; }
    const id = ++seq;
    let line = JSON.stringify({id, kind, ...body}) + '\n';
    let size = Buffer.byteLength(line);
    if (size > limits.max_record_bytes) {
      stats.oversize++;
      const marker = {id, kind: 'oversize', original_kind: kind, bytes: size,
        sha256: crypto.createHash('sha256').update(line).digest('hex')};
      line = JSON.stringify(keep ? {...marker, kept: keep} : marker) + '\n';
      if (keep && Buffer.byteLength(line) > limits.max_record_bytes) {
        stats.oversize_kept_dropped = (stats.oversize_kept_dropped || 0) + 1;
        line = JSON.stringify({...marker, kept_dropped: true}) + '\n';
      }
      size = Buffer.byteLength(line);
    }
    if (exhausted || stats.saved_bytes + size > ordinaryCap) {
      stats.refused++;
      stats.refused_bytes += size;
      if (!exhausted) { exhausted = true; onExhausted({id, kind, size, saved_bytes: stats.saved_bytes, cap: ordinaryCap}); }
      return null;
    }
    try {
      write(line);
    } catch (error) {
      stats.write_failures++;
      onExhausted({id, kind, export_failure: String(error.code || error.message)});
      exhausted = true;
      return null;
    }
    stats.records++;
    stats.saved_bytes += size;
    return id;
  }

  // Setup bindings: counted in the ordinary budget, exempt from the per-record
  // cap (they are not a receipt), written once before any network.
  function writeSidecar(name, value) {
    const text = JSON.stringify(value, null, 1) + '\n';
    const size = Buffer.byteLength(text);
    if (stats.saved_bytes + size > ordinaryCap) return false;
    fs.writeFileSync(path.join(dir, name), text, {flag: 'wx'});
    stats.saved_bytes += size;
    return true;
  }

  // STOP and summary spend only the reserve. If a full form would not fit, the
  // minimal one is written instead; the contract's reserve floor holds both
  // minimal forms. {written:false} is still returned, never thrown away: the
  // caller treats it as a recorder failure.
  function writeReserved(name, value, minimal) {
    const target = path.join(dir, name);
    let text = JSON.stringify(value, null, 1) + '\n';
    const left = limits.reserved_stop_bytes - stats.reserved_used_bytes;
    let truncated = false;
    if (Buffer.byteLength(text) > left) { text = JSON.stringify({...minimal, reserve_truncated: true}) + '\n'; truncated = true; }
    if (Buffer.byteLength(text) > left) return {written: false, truncated: true, bytes: 0};
    fs.writeFileSync(target, text, {flag: 'wx'});
    stats.reserved_used_bytes += Buffer.byteLength(text);
    return {written: true, truncated, bytes: Buffer.byteLength(text)};
  }

  return {
    file, stats, append, writeReserved, writeSidecar,
    get exhausted() { return exhausted; },
    close() { if (closed) return; closed = true; try { fs.fsyncSync(fd); } catch { /* reported by write_failures */ } fs.closeSync(fd); },
  };
}

module.exports = {createJournal, minimalForms};
