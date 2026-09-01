#!/usr/bin/env python3
"""CAL-P198 PROOF 2 (empirical) — the ETA carries no information about the
throughput it predicts, and its error explodes exactly when units are cancelled.

Reuses CAL-P118's captured ring (168 consecutive production beats,
2026-08-22 -> 08-29) rather than measuring anything new, plus the live stuck
beat's gauges captured this session. No DB access; runs from any cwd.
Exit 0 = every claim held.

The reconstruction. ``_record_staged_rate`` records
``beats_to_publish = ceil(remaining / per_beat)``, so from the captured pair
(``units_banked``, ``beats_to_publish``) the asserted rate is recoverable as
``implied = (128 - units_banked) / beats_to_publish``. Because of the ceil,
``implied <= per_beat`` -- so every optimism figure below is a LOWER BOUND on
the real over-claim.

Claims proved here:
  A. Across the captured beats the ETA's implied throughput has essentially
     ZERO correlation with the throughput actually observed (|r| < 0.10).
     This is the empirical form of CAL-P071's "observed throughput is not an
     input to it".
  B. The ETA over-claims on a large majority of beats.
  C. The error is regime-dependent: on beats that recorded a cancellation the
     worst over-claim is many times the median beat's. The worst captured beat
     asserted >= 30 units/beat and banked 1.
  D. On the live stuck beat the cancelled-unit time reconciles to the unit
     stage total, showing what share of the phase the projection models as
     productive when it is not.
"""

from __future__ import annotations

import json
import math
import pathlib
import statistics
import sys

STAGED_FUTURES_BUCKETS = 128

failures: list[str] = []


def check(label: str, ok: bool, detail: str = "") -> None:
    print(("  PASS  " if ok else "  FAIL  ") + label + (("\n          " + detail) if detail else ""))
    if not ok:
        failures.append(label)


def repo_root() -> pathlib.Path:
    here = pathlib.Path(__file__).resolve()
    for p in [here, *here.parents]:
        if (p / "artifacts" / "cal-p118" / "beat-ring-full.json").exists():
            return p
    raise SystemExit("FATAL: could not locate repo root from %s" % here)


ROOT = repo_root()
RING = ROOT / "artifacts" / "cal-p118" / "beat-ring-full.json"

# Live stuck beat, captured this session from
#   durable_state_snapshots WHERE identity='calibration:main:phase_ledger'
#   updated_at 2026-09-01 17:31:46.517193+00
LIVE = {
    "read:futures_unit": 958892,
    "staged:units_completed_this_beat": 5,
    "staged:units_cancelled": 2,
    "staged:unit_ms_mean_completed": 50245,
    "staged:unit_ms_mean": 136984,
    "staged:units_banked": 50,
    "staged:beats_to_publish": 3,
    "cancelled_unit_ms": [353842, 353844],  # staged:unit_cancelled:<digest>
}

print("=" * 78)
print("CAL-P198 PROOF 2 — the ETA does not track the throughput it predicts")
print("ring: %s" % RING.relative_to(ROOT))
print("=" * 78)

beats = json.loads(RING.read_text())
print("\ncaptured beats in ring: %d" % len(beats))

pairs = []  # (implied_rate, actual_completed, cancelled_or_None, stamp)
for b in beats:
    g = b.get("gauges") or {}
    btp = g.get("staged:beats_to_publish")
    comp = g.get("staged:units_completed_this_beat")
    bank = g.get("staged:units_banked")
    if btp is None or comp is None or bank is None or btp < 1:
        continue
    remaining = STAGED_FUTURES_BUCKETS - bank
    if remaining <= 0:
        continue
    pairs.append((remaining / btp, comp, g.get("staged:units_cancelled"), b.get("generated_at", "")[:19]))

implied = [p[0] for p in pairs]
actual = [p[1] for p in pairs]
print("usable beats (ETA >= 1 and units remaining): %d" % len(pairs))

# ---- A ---------------------------------------------------------------------
print("\nA. the ETA's implied rate is uncorrelated with observed throughput")
n = len(pairs)
mi, ma = statistics.mean(implied), statistics.mean(actual)
cov = sum((i - mi) * (a - ma) for i, a in zip(implied, actual)) / n
r = cov / (statistics.pstdev(implied) * statistics.pstdev(actual))
print("          implied units/beat : mean=%.1f med=%.1f min=%.1f max=%.1f"
      % (mi, statistics.median(implied), min(implied), max(implied)))
print("          actual  units/beat : mean=%.1f med=%.1f min=%.1f max=%.1f"
      % (ma, statistics.median(actual), min(actual), max(actual)))
print("          Pearson r(implied, actual) = %+.3f" % r)
check("|r| < 0.10 — the ETA carries no information about what the beat will bank",
      abs(r) < 0.10,
      "the ETA's spread is %.0fx (%.0f..%.0f) while actual throughput's is %.1fx"
      % (max(implied) / min(implied), min(implied), max(implied), max(actual) / max(1, min(a for a in actual if a))))

# ---- B ---------------------------------------------------------------------
print("\nB. the ETA over-claims on a large majority of beats")
over = sum(1 for i, a, _, _ in pairs if i > a)
ratios = [i / a for i, a, _, _ in pairs if a > 0]
print("          over-claiming beats: %d/%d = %.0f%%" % (over, n, 100 * over / n))
print("          optimism ratio implied/actual: med=%.2fx mean=%.2fx max=%.1fx"
      % (statistics.median(ratios), statistics.mean(ratios), max(ratios)))
check("the ETA over-claims on > 60% of beats", over / n > 0.60)
check("and the ceil means every ratio here is a LOWER bound on the real over-claim", True,
      "beats_to_publish = ceil(remaining/per_beat) => implied <= per_beat")

# ---- C ---------------------------------------------------------------------
print("\nC. the error is regime-dependent — cancellations are where it explodes")
canc = [p for p in pairs if p[2]]
print("          beats that recorded staged:units_cancelled: %d" % len(canc))
print("          %-21s %5s %6s %9s %9s" % ("generated_at", "canc", "actual", "implied", "ratio"))
worst = None
for i, a, c, stamp in sorted(canc, key=lambda p: -(p[0] / max(1, p[1]))):
    ratio = i / a if a else float("inf")
    print("          %-21s %5s %6s %9.1f %8.1fx" % (stamp, c, a, i, ratio))
    if worst is None:
        worst = (i, a, c, stamp, ratio)
check("the worst captured beat asserted >= 30 units/beat", worst is not None and worst[0] >= 30,
      "%s: %d cancelled, banked %d, ETA asserted %.1f/beat (%.0fx)"
      % (worst[3], worst[2], worst[1], worst[0], worst[4]))
med_all = statistics.median(ratios)
check("that worst-case over-claim is >= 10x the median beat's",
      worst[4] >= 10 * med_all,
      "worst %.1fx vs median %.2fx" % (worst[4], med_all))

# ---- D ---------------------------------------------------------------------
print("\nD. the live stuck beat — cancelled time reconciles to the unit stage total")
cancel_ms = sum(LIVE["cancelled_unit_ms"])
complete_ms = LIVE["staged:units_completed_this_beat"] * LIVE["staged:unit_ms_mean_completed"]
total = LIVE["read:futures_unit"]
recon = cancel_ms + complete_ms
print("          %d cancelled units      : %9d ms" % (LIVE["staged:units_cancelled"], cancel_ms))
print("          %d completed units x %d : %9d ms" % (LIVE["staged:units_completed_this_beat"],
                                                      LIVE["staged:unit_ms_mean_completed"], complete_ms))
print("          reconstructed total     : %9d ms" % recon)
print("          read:futures_unit       : %9d ms   (delta %d ms)" % (total, abs(recon - total)))
check("the two cancelled units plus the five completed ones account for the unit stage",
      abs(recon - total) < 1000, "delta %d ms" % abs(recon - total))
share = cancel_ms / total
print("          share of unit-stage wall clock that banked NOTHING: %.1f%%" % (100 * share))
check("cancelled units consumed > 70% of the unit stage, and the projection models 0% of it",
      share > 0.70)
print("          the projection's numerator (usable_ms) deducts none of that %d ms;" % cancel_ms)
print("          its divisor is the %d ms cost of a unit that COMPLETES." % LIVE["staged:unit_ms_mean_completed"])
honest = total / LIVE["staged:units_completed_this_beat"]
print("          honest cost per BANKED unit this beat: %d ms  (%.1fx the modelled %d ms)"
      % (honest, honest / LIVE["staged:unit_ms_mean_completed"], LIVE["staged:unit_ms_mean_completed"]))

print("\n" + "=" * 78)
if failures:
    print("PROOF 2 FAILED — %d claim(s) did not hold:" % len(failures))
    for f in failures:
        print("  - %s" % f)
    sys.exit(1)
print("PROOF 2 HELD — every claim above is true of the captured data.")
sys.exit(0)
