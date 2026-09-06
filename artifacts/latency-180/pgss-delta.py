#!/usr/bin/env python3
"""Difference two `pg_stat_statements` snapshots into a LIVE rate per statement.

Cumulative totals rank history. `pg_stat_statements` here was last reset 5 days
11 hours ago, so a statement 179 fixed an hour ago still sits near the top of
`total_exec_time` with the full signature of the bug — 278 ms and 15,084 buffers
for a single-row `UPDATE ... WHERE external_id = $3`. True row, dead statement.
The delta is what says which is which: a fixed statement's `calls` stops moving.
"""
import json
import sys

A = json.load(open(sys.argv[1]))
B = json.load(open(sys.argv[2]))
dt = B["at"] - A["at"]
print(f"window {dt:.0f}s ({dt/60:.1f} min)\n")

out = []
for qid, b in B["rows"].items():
    a = A["rows"].get(qid)
    dc = b["calls"] - (a["calls"] if a else 0)
    dms = b["ms"] - (a["ms"] if a else 0)
    dhit = b["hit"] - (a["hit"] if a else 0)
    drd = b["read"] - (a["read"] if a else 0)
    if dc <= 0:
        continue
    out.append({
        "calls_hr": dc / dt * 3600, "s_hr": dms / 1000 / dt * 3600,
        "mean_ms": dms / dc, "buf_call": (dhit + drd) / dc, "rd_call": drd / dc,
        "dc": dc, "q": " ".join(b["q"].split()),
    })

out.sort(key=lambda r: -r["s_hr"])
print(f"{'calls/hr':>9} {'DBs/hr':>8} {'mean_ms':>9} {'buf/call':>9} {'rd/call':>8} {'n':>6}  query")
for r in out[:30]:
    print(f"{r['calls_hr']:9.0f} {r['s_hr']:8.1f} {r['mean_ms']:9.1f} {r['buf_call']:9.0f} "
          f"{r['rd_call']:8.0f} {r['dc']:6d}  {r['q'][:95]}")

print(f"\n{len(out)} statements moved; "
      f"{len(B['rows']) - len(out)} of the top-200 by lifetime total did NOT move at all.")
print(f"total live DB time: {sum(r['s_hr'] for r in out):,.0f} s/hr across all consumers")
