'use strict';
// #10090 / #11674: collector <-> document clock mapping as intervals.
//
// The comparison clock is the collector's monotonic clock relative to the
// predeclared T0. A document performance.now() value `d` read inside a
// collector bracket [c0, c1] maps to collector time with offset in
// [c0 - d, c1 - d]. Repeated exchanges must keep a common offset; when they do
// not, the drift is a loud fault, never averaged away. Worker, Redis and DB
// clocks are NOT mapped here — the page cannot measure them.
const {performance} = require('perf_hooks');

// Chrome's performance.now() resolution without cross-origin isolation is
// 100 us; 2 ms absorbs that plus timer coarsening. A fixed recorder constant,
// stated in every summary, not a grant number.
const DRIFT_TOLERANCE_MS = 2;
const WALL_JUMP_TOLERANCE_MS = 50;
const READ_UNCERTAINTY_FAULT_MS = 250;

function createClock({t0WallMs, wallSkewMs = () => 0}) {
  // One anchor maps the predeclared T0 (wall) onto the collector monotonic clock.
  const a0 = performance.now(), w0 = Date.now() + wallSkewMs(), a1 = performance.now();
  const anchor = {mono_before: a0, mono_after: a1, wall: w0, t0_mono: [t0WallMs - w0 + a0, t0WallMs - w0 + a1]};
  const exchanges = [];
  const faults = [];
  let offset = null; // running intersection [lo, hi] of collector_mono - doc_mono
  let timeOrigin = null;
  let lastWallMinusMono = w0 - a0;

  const mono = () => performance.now();
  const wall = () => Date.now() + wallSkewMs();
  // Collector monotonic relative to T0, as an interval (the anchor's bracket width).
  const sinceT0 = m => [m - anchor.t0_mono[1], m - anchor.t0_mono[0]];
  const fault = (kind, detail) => { faults.push({...detail, kind}); };

  async function exchange(page, label) {
    const c0m = mono(), c0w = wall();
    let doc;
    try {
      doc = await page.evaluate(() => ({now: performance.now(), timeOrigin: performance.timeOrigin, wall: Date.now(),
        visibility: document.visibilityState}));
    } catch (error) {
      const c1m = mono();
      exchanges.push({label, ok: false, error: String(error), collector: {mono: [c0m, c1m], wall_before: c0w}});
      fault('clock-exchange-failed', {label, error: String(error)});
      return null;
    }
    const c1m = mono(), c1w = wall();
    const width = c1m - c0m;
    const off = [c0m - doc.now, c1m - doc.now];
    const row = {label, ok: true, collector: {mono: [c0m, c1m], wall: [c0w, c1w], since_t0_ms: sinceT0(c0m)},
      document: doc, offset_interval_ms: off, read_uncertainty_ms: width, faults: []};
    if (width > READ_UNCERTAINTY_FAULT_MS) { row.faults.push('read-uncertainty'); fault('clock-read-uncertainty', {label, width_ms: width}); }
    if (timeOrigin === null) timeOrigin = doc.timeOrigin;
    else if (doc.timeOrigin !== timeOrigin) {
      row.faults.push('document-replaced');
      fault('document-replaced', {label, previous_time_origin: timeOrigin, time_origin: doc.timeOrigin});
      timeOrigin = doc.timeOrigin;
      offset = null; // a new document is a new clock; the old mapping no longer applies
    }
    const wmm = c0w - c0m;
    if (Math.abs(wmm - lastWallMinusMono) > WALL_JUMP_TOLERANCE_MS) {
      row.faults.push('collector-wall-jump-or-suspend');
      fault('collector-wall-jump-or-suspend', {label, delta_ms: wmm - lastWallMinusMono});
    }
    lastWallMinusMono = wmm;
    // Document wall vs its own monotonic: a jump there is a document-side discontinuity.
    const docSkew = doc.wall - (doc.timeOrigin + doc.now);
    row.document_wall_minus_origin_ms = docSkew;
    if (Math.abs(docSkew) > WALL_JUMP_TOLERANCE_MS) { row.faults.push('document-wall-discontinuity'); fault('document-wall-discontinuity', {label, skew_ms: docSkew}); }
    if (offset === null) offset = [...off];
    else {
      const lo = Math.max(offset[0], off[0]), hi = Math.min(offset[1], off[1]);
      if (lo > hi + DRIFT_TOLERANCE_MS) {
        row.faults.push('offset-drift');
        fault('offset-drift', {label, running: offset, this: off, gap_ms: lo - hi});
        offset = [Math.min(offset[0], off[0]), Math.max(offset[1], off[1])];
      } else if (lo <= hi) offset = [lo, hi];
      // Within tolerance but disjoint: keep the brackets' intersection widened
      // by the tolerance, never the narrower gap between them.
      else offset = [lo - DRIFT_TOLERANCE_MS, hi + DRIFT_TOLERANCE_MS];
    }
    row.running_offset_ms = [...offset];
    exchanges.push(row);
    return row;
  }

  // Map a document monotonic stamp to collector-ms-since-T0 as a conservative interval.
  function docToT0(docMono) {
    if (!offset) return null;
    return [docMono + offset[0] - anchor.t0_mono[1], docMono + offset[1] - anchor.t0_mono[0]];
  }

  return {anchor, exchanges, faults, mono, wall, sinceT0, exchange, docToT0,
    get offset() { return offset && [...offset]; },
    constants: {DRIFT_TOLERANCE_MS, WALL_JUMP_TOLERANCE_MS, READ_UNCERTAINTY_FAULT_MS}};
}

module.exports = {createClock, DRIFT_TOLERANCE_MS, WALL_JUMP_TOLERANCE_MS, READ_UNCERTAINTY_FAULT_MS};
