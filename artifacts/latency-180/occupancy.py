#!/usr/bin/env python3
"""latency/180 — is the background queue's dead time an AVERAGE problem or a
CONTIGUITY problem?

The demand model says `background` runs at 0.80x of its 7,200 worker-seconds an
hour. At 80% utilisation a 2-slot queue should not strand a 10-second beat for
four minutes at a time, and yet the warmer's period p95 is 206-300s. Averages
and waits are different questions, so this measures the second one directly.

`recent_durations_at` + `recent_durations_ms` give each task's last 50 runs as
real intervals [end - duration, end]. Unioning every background task's intervals
across the collected snapshots reconstructs the queue's actual occupancy
timeline, from which the two facts that matter fall out:

  * how much of the wall clock has 0, 1, or 2 slots busy — the average, checked
    against the demand model rather than assumed to agree with it; and
  * the DISTRIBUTION of contiguous BOTH-BUSY intervals, which is what a beat
    actually waits behind. A queue that is 80% busy in 5-second pieces starves
    nobody; the same 80% in fifteen-minute pieces starves everything.

⚠️ THE WINDOW IS BOUNDED BY THE SHORTEST RING, and that bound is load-bearing.
50 samples is 23 minutes for `warm_typeahead` at 131/hr and 24 hours for a daily
beat, so any window longer than the shortest contributing ring silently drops
the fast tasks' runs and under-reports occupancy exactly where it is densest.
The window is therefore clipped to the newest interval start of the task whose
ring is shortest among those that actually contribute, and the clip is printed.
"""
import json
import statistics as st
import sys
from collections import defaultdict

SLOTS = 2
occ_path = sys.argv[1] if len(sys.argv) > 1 else ".lat180-occ.jsonl"
beat = json.load(open("/tmp/lat180-beatmap.json"))
lm = json.load(open("/tmp/lat180-labelmap.json"))
label_of = {k: v for k, v in lm.items() if k.startswith("app.tasks.")}
bg_labels = {label_of[t] for t, b in beat.items()
             if b["queue"] == "background" and t in label_of}

# Union every snapshot's runs, deduped on (label, end-stamp) so overlapping
# snapshots cost nothing and a run seen five times is still one run.
runs = defaultdict(dict)
for line in open(occ_path):
    d = json.loads(line)
    for t in d.get("tasks") or []:
        lab = t["task"]
        if lab not in bg_labels:
            continue
        ats, mss = t.get("at") or [], t.get("ms") or []
        if len(ats) != len(mss):
            continue
        for a, m in zip(ats, mss):
            if a is None or m is None:
                continue
            runs[lab][round(a, 3)] = m / 1000.0

if not runs:
    raise SystemExit("no background runs collected yet")

# Clip to a window every contributing ring genuinely covers.
#
# 🔴 THE SATURATION TEST BELONGS TO THE OLDEST SNAPSHOT, NOT TO THE UNION, and
# getting that wrong is what a first pass of this script did. Unioning three
# snapshots of `warm_typeahead` yields ~70 distinct runs, so a `len(runs) >= 50`
# test on the UNION finds it unsaturated and lets the window stretch to 182
# minutes — eight times what that ring can see. The consequence was not subtle:
# `warm_typeahead` scored 8.7% of a window in which it truly runs ~54% of a
# slot, and `tournament_price_refresh` scored 23.1% entirely on pre-fix runs
# 179 had already eliminated. Coverage is a property of one ring at one read.
snaps = [json.loads(l) for l in open(occ_path)]
snaps.sort(key=lambda d: d["ts"])
oldest = next((s for s in snaps if s.get("tasks")), None)
cover_starts = []
for t in (oldest.get("tasks") or []) if oldest else []:
    if t["task"] in bg_labels and len(t.get("at") or []) >= 50:
        cover_starts.append(min(a for a in t["at"] if a is not None))
ends = {lab: max(v) for lab, v in runs.items()}
window_end = max(ends.values())
window_start = max(cover_starts) if cover_starts else min(min(v) for v in runs.values())
span = window_end - window_start
limiter = "saturated ring in the oldest snapshot" if cover_starts else "(none saturated)"

ivals = []
for lab, d in runs.items():
    for end, dur in d.items():
        s, e = max(end - dur, window_start), min(end, window_end)
        if e > s:
            ivals.append((s, e, lab))

# Sweep line over interval endpoints -> concurrency over time.
pts = sorted({window_start, window_end} | {x for s, e, _ in ivals for x in (s, e)})
busy_time = defaultdict(float)
both_runs, cur = [], None
for i in range(len(pts) - 1):
    a, b = pts[i], pts[i + 1]
    n = sum(1 for s, e, _ in ivals if s <= a and e >= b)
    busy_time[min(n, SLOTS)] += b - a
    if n >= SLOTS:
        cur = (a, b) if cur is None else (cur[0], b)
    elif cur is not None:
        both_runs.append(cur[1] - cur[0])
        cur = None
if cur is not None:
    both_runs.append(cur[1] - cur[0])

print(f"window {span:.0f}s ({span/60:.1f} min), clipped by the shortest saturated "
      f"ring: {limiter}")
print(f"{len(ivals)} runs across {len(runs)} background tasks\n")
print("=== SLOT OCCUPANCY (share of wall clock) ===")
for n in range(SLOTS + 1):
    print(f"  {n} slot(s) busy: {busy_time[n]:8.0f}s  {busy_time[n]/span*100:5.1f}%")
util = sum(n * t for n, t in busy_time.items()) / (SLOTS * span)
print(f"  measured utilisation: {util*100:.1f}% of {SLOTS} slots "
      f"({util*SLOTS*3600:,.0f} wsec/hr)")

print("\n=== CONTIGUOUS 'BOTH SLOTS BUSY' INTERVALS — what a beat waits behind ===")
if both_runs:
    both_runs.sort()
    over = [x for x in both_runs if x > 65]
    print(f"  n={len(both_runs)}  p50={st.median(both_runs):.1f}s  "
          f"p95={both_runs[min(len(both_runs)-1, int(0.95*(len(both_runs)-1)))]:.1f}s  "
          f"max={both_runs[-1]:.1f}s")
    print(f"  total blocked: {sum(both_runs):.0f}s = {sum(both_runs)/span*100:.1f}% of the window")
    print(f"  intervals LONGER than the 65s response TTL: {len(over)} "
          f"({sum(over):.0f}s = {sum(over)/span*100:.1f}% of the window)")
    print(f"  longest 8: {', '.join(f'{x:.0f}s' for x in both_runs[-8:])}")
else:
    print("  none observed")

print("\n=== WHO IS IN THE BLOCKED INTERVALS (slot-seconds inside both-busy time) ===")
share = defaultdict(float)
for s, e, lab in ivals:
    share[lab] += e - s
for lab, sec in sorted(share.items(), key=lambda kv: -kv[1])[:14]:
    print(f"  {sec:8.0f}s  {sec/span*100:5.1f}% of window  {lab}")
