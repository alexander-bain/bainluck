#!/usr/bin/env python3
"""latency/180 — what is actually happening during the warmer's HOLES?

Two hypotheses are already dead. The queue is not oversubscribed on average
(0.80x priced demand against 2 slots), and it is not blocked in long contiguous
stretches (longest both-slots-busy interval in 34.5 minutes: 73.5s, against a
period p95 of 206-300s). So the hole is not a slot the warmer could not get.

This overlays the warmer's own ring on the occupancy timeline hole by hole and
prints, for each, both slot occupancy AND the pass records either side — so the
answer can be "nothing held a slot", which is a finding and not a null result.
"""
import json
import statistics as st
from collections import defaultdict

TTL = 65.0
beat = json.load(open("/tmp/lat180-beatmap.json"))
lm = json.load(open("/tmp/lat180-labelmap.json"))
label_of = {k: v for k, v in lm.items() if k.startswith("app.tasks.")}
bg_labels = {label_of[t] for t, b in beat.items()
             if b["queue"] == "background" and t in label_of}

# The ring, unioned by each record's own `at` across every sampler tick.
recs = {}
for line in open(".lat180-samples.jsonl"):
    d = json.loads(line)
    for r in d.get("ring_records") or []:
        if r.get("at") is not None:
            recs[round(r["at"], 3)] = r
records = [recs[k] for k in sorted(recs)]

# Occupancy intervals, same union.
runs = defaultdict(dict)
for line in open(".lat180-occ.jsonl"):
    d = json.loads(line)
    for t in d.get("tasks") or []:
        if t["task"] not in bg_labels:
            continue
        ats, mss = t.get("at") or [], t.get("ms") or []
        if len(ats) == len(mss):
            for a, m in zip(ats, mss):
                if a is not None and m is not None:
                    runs[t["task"]][round(a, 3)] = m / 1000.0
ivals = [(e - dur, e, lab) for lab, d in runs.items() for e, dur in d.items()]

span = records[-1]["at"] - records[0]["at"]
periods = [r["period_s"] for r in records if r.get("period_s")]
walls = [r["seconds_wall"] for r in records if r.get("seconds_wall")]
holes = []
for r in records:
    p, w = r.get("period_s"), r.get("seconds_wall") or 0
    if not p or p <= TTL:
        continue
    start = r["at"] - w                       # this pass's start
    holes.append({"from": start - (p - TTL), "to": start, "period": p, "excess": p - TTL})

dead = sum(h["excess"] for h in holes)
print(f"ring: {len(records)} passes over {span:.0f}s ({span/60:.1f} min)")
print(f"  period p50={st.median(periods):.1f}s "
      f"p95={sorted(periods)[min(len(periods)-1,int(0.95*(len(periods)-1)))]:.1f}s "
      f"max={max(periods):.1f}s")
print(f"  wall   p50={st.median(walls):.1f}s max={max(walls):.1f}s")
print(f"  DEAD (period beyond the {TTL:.0f}s TTL): {dead:.0f}s of {span:.0f}s = "
      f"{dead/span*100:.1f}%   in {len(holes)} of {len(records)} passes\n")

print("=== EACH HOLE: was a slot even busy? ===")
for h in holes:
    who = defaultdict(float)
    for s, e, lab in ivals:
        ov = min(e, h["to"]) - max(s, h["from"])
        if ov > 0:
            who[lab] += ov
    # Slot-seconds available in the hole vs consumed.
    consumed = sum(who.values())
    capacity = 2 * h["excess"]
    top = sorted(who.items(), key=lambda kv: -kv[1])[:3]
    desc = ", ".join(f"{k}={v:.0f}s" for k, v in top) or "NOTHING HELD A SLOT"
    print(f"  excess {h['excess']:6.0f}s (period {h['period']:6.0f}s)  "
          f"slot-use {consumed:.0f}/{capacity:.0f}s = {consumed/capacity*100 if capacity else 0:4.0f}%"
          f"  <- {desc}")

print("\n=== SKIP REASONS ON THE PASSES THEMSELVES ===")
print(dict(sorted(
    ((str(r.get("skip_reason")), sum(1 for x in records if x.get("skip_reason") == r.get("skip_reason")))
     for r in records), key=lambda kv: -kv[1])))
print("terminals:", dict(sorted(
    ((str(r.get("terminal")), sum(1 for x in records if x.get("terminal") == r.get("terminal")))
     for r in records), key=lambda kv: -kv[1])))
