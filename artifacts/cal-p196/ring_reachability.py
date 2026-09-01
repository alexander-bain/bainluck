#!/usr/bin/env python3
"""CAL-P196 — how often did `availability: fresh` survive the drift gate?

Reads the 168-beat production ring captured by CAL-P118
(``artifacts/cal-p118/beat-ring-full.json``) — a REUSED artifact, not a
re-collection. Every entry carries both the raw ``gauges`` and the
``disclosure`` block that ``build_disclosure`` produced from them, so the gate's
verdict is recorded rather than re-derived.

Runs from anywhere. Read-only. Exit 0 = the tabulation completed.
"""

from __future__ import annotations

import collections
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
RING = os.path.abspath(os.path.join(HERE, "..", "cal-p118", "beat-ring-full.json"))

rows = sorted(json.load(open(RING)), key=lambda r: r["generated_at"])
print(f"ring: {len(rows)} beats  {rows[0]['generated_at'][:19]} .. {rows[-1]['generated_at'][:19]}")

# -- 1. the gate's verdict, as recorded ---------------------------------------
verdict = collections.Counter(
    (r.get("disclosure") or {}).get("frozen_over_drift") for r in rows
)
measured = verdict[True] + verdict[False]
print("\n1. frozen_over_drift, as recorded by build_disclosure")
print(f"   True  (availability floored to STALE): {verdict[True]}")
print(f"   False (fresh permitted)              : {verdict[False]}")
print(f"   absent (disclosure unmeasured)       : {verdict[None]}")
print(f"   => fresh permitted on {verdict[False]}/{measured} measured beats "
      f"({100 * verdict[False] / measured:.1f}%)")

# -- 2. served drift saturates ------------------------------------------------
print("\n2. served bank: (served_units, served_drifted) distribution")
sd = collections.Counter(
    (g.get("staged:served_units"), g.get("staged:served_drifted"))
    for r in rows
    if (g := r.get("gauges") or {})
)
for k, v in sd.most_common(8):
    print(f"   {k}: {v} beats")

# -- 3. why the zero-drift beats still failed the gate ------------------------
print("\n3. beats with served_units=128 AND served_drifted=0 "
      "(i.e. drift itself was clean)")
for r in rows:
    g = r.get("gauges") or {}
    if g.get("staged:served_units") == 128 and g.get("staged:served_drifted") == 0:
        d = r.get("disclosure") or {}
        blocker = (
            "-" if d.get("frozen_over_drift") is False
            else f"served_drift_uncheckable={g.get('staged:served_drift_uncheckable')}"
        )
        print(f"   {r['generated_at'][:19]}  frozen={d.get('frozen_over_drift')!s:<5} "
              f"blocked_by: {blocker}")

# -- 4. the identity that proves the per-beat reading -------------------------
# Units banked by `advance` carry no digest (advance is handed a key, never a
# chunk), so the NEXT top-of-beat drift measurement cannot see them. If
# roster_drift's baseline were "when the unit ran" this identity would not hold.
print("\n4. units_drift_uncheckable == units_completed_this_beat ?")
ok = bad = 0
for r in rows:
    g = r.get("gauges") or {}
    u, c = g.get("staged:units_drift_uncheckable"), g.get("staged:units_completed_this_beat")
    if u is None or c is None:
        continue
    ok, bad = (ok + 1, bad) if u == c else (ok, bad + 1)
print(f"   holds on {ok} beats, fails on {bad} "
      f"({100 * ok / (ok + bad):.0f}%)")

# -- 5. the building bank's per-beat drift RATE -------------------------------
print("\n5. building-bank drift per beat (units_drifted / units_drift_checkable)")
pcts = sorted(
    100 * g["staged:units_drifted"] / g["staged:units_drift_checkable"]
    for r in rows
    if (g := r.get("gauges") or {}) and g.get("staged:units_drift_checkable")
)
n = len(pcts)
print(f"   n={n}  min={pcts[0]:.0f}%  p25={pcts[n // 4]:.0f}%  "
      f"median={pcts[n // 2]:.0f}%  p75={pcts[3 * n // 4]:.0f}%  max={pcts[-1]:.0f}%")
print("   => a slot's membership changes within ONE beat, most beats. That is a")
print("      RATE. It is not 'how stale the bank is since it was banked'.")

sys.exit(0)
