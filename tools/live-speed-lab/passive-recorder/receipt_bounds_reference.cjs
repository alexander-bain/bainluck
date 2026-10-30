'use strict';
// #10090: REFERENCE reading of the page receipt brackets, for the recorder's
// own controls. Measurement's adapter is the scorer; this file only states the
// inequalities the recorder's records support, so a control can check them.
//
// For page record i (same document, i.e. same time_origin):
//   upper: the page observed before it sent, and the collector stamped recv
//          after the send, so observation_i < recv_i on C.  D_hi = recv_i.
//   lower: for an earlier record j whose page ack (document time) is strictly
//          before this sample's read start r0_i, recv_j < ack_j < r0_i in real
//          time, so D_lo = max such recv_j on C. No such j: no lower bound.
// Nothing converts document time to C by an offset. A record with no ack
// gives no lower bound to later samples; it keeps its own upper bound.

// records: [{page_seq, time_origin, recv (C ms), read_start (document ms), acks: [[seq, ackDoc], ...]}]
// extraAcks: acks from the stop return / drain, [[seq, ackDoc], ...] with their time_origin.
function receiptBounds(records, extraAcks = [], extraTimeOrigin = null) {
  const ackDoc = new Map(); // `${time_origin}:${seq}` -> document ms
  const put = (to, a) => { if (Array.isArray(a) && a.length === 2) ackDoc.set(`${to}:${a[0]}`, a[1]); };
  for (const r of records) for (const a of r.acks || []) put(r.time_origin, a);
  for (const a of extraAcks) put(extraTimeOrigin, a);
  // Acked records of each document, ordered by ack time, with a running max of recv.
  const byDoc = new Map();
  for (const r of records) {
    const ack = ackDoc.get(`${r.time_origin}:${r.page_seq}`);
    if (ack === undefined) continue;
    if (!byDoc.has(r.time_origin)) byDoc.set(r.time_origin, []);
    byDoc.get(r.time_origin).push({ack, recv: r.recv});
  }
  for (const list of byDoc.values()) {
    list.sort((a, b) => a.ack - b.ack);
    let best = -Infinity;
    for (const x of list) { best = Math.max(best, x.recv); x.best = best; }
  }
  return records.map(r => {
    const list = byDoc.get(r.time_origin) || [];
    let lo = null;
    // Largest ack strictly before the read start (binary search on ack).
    let a = 0, b = list.length - 1, hit = -1;
    while (a <= b) { const m = (a + b) >> 1; if (list[m].ack < r.read_start) { hit = m; a = m + 1; } else b = m - 1; }
    if (hit >= 0) lo = list[hit].best;
    return {page_seq: r.page_seq, d_lo: lo, d_hi: r.recv};
  });
}

module.exports = {receiptBounds};
