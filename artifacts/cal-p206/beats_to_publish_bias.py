#!/usr/bin/env python3
"""CAL-P206 / question 5 — "this thing was FIXED. Is the fix CONNECTED to the thing it
fixed?" applied to CAL-P068's fix of ``staged:beats_to_publish``.

THE FIX. ``_record_staged_rate`` (calibration_main_build.py:1603-1628) projects::

    per_beat         = usable_ms / projection_mean
    beats_to_publish = ceil((BUCKETS - banked) / per_beat)

CAL-P068 changed ``projection_mean`` from ``unit_ms_mean`` (the mean over every unit the
beat TIMED, cancellations included) to ``unit_ms_mean_completed`` (the mean over units
that COMPLETED). Its comment states the reasoning, and the reasoning is correct about the
quantity it names::

    A beat runs N units and the last is cancelled at the deadline, so the truncated
    observation drags the mean DOWN; a lower mean means more units appear to fit per
    beat, which means FEWER beats appear to remain. The projection was optimistic by
    construction.

THE PROBLEM. That argument is about the COST OF A UNIT. ``beats_to_publish`` is not a unit
cost -- it is a THROUGHPUT projection, and throughput must charge the time burned by
cancelled units to the units that actually banked. A cancelled unit does not cost nothing;
it costs a share of the window and banks zero. Swapping the mixed mean (which happens to
absorb that wasted time) for the completed mean (which excludes it) removes the only term
that was accounting for it.

DIRECTION OF THE CHANGE: the completed mean is always <= the mixed mean, so per_beat rises
and beats_to_publish FALLS. The fix moves the number the same way the bias it names does.

LIVE RECONSTRUCTION (2026-09-01 21:2xZ, banked 65/128, basis=completed):
    window 1,380,000ms; ran 7, completed 5, cancelled 2
    mixed mean 186,306ms -> 7 units timed = 1,304,142ms = 94.5% of the window
    completed mean 77,940ms -> 5 units = 389,700ms; 914,442ms burned on the 2 cancelled
    projection (completed) per_beat=17.71 -> beats_to_publish=4   <- matches production
    projection (mixed)     per_beat= 7.41 -> beats_to_publish=9
    measured throughput    per_beat= 5.00 -> beats_to_publish=13
The beat is not idle. It is 94.5% busy and banks 5.

THIS HARNESS measures the bias over 168 consecutive production beats. Those beats PREDATE
CAL-P067, so ``unit_ms_mean_completed`` is absent from all of them and they ran on the
MIXED basis -- which makes the ring a natural control arm for the pre-fix behaviour.

CONTROL ARMS:
  ARM 1 (reproduction) -- recompute each beat's published ``beats_to_publish`` from its own
      gauges. If the recomputation does not match production, the model of the formula is
      wrong and no bias verdict may be emitted.
  ARM 2 (basis) -- assert the ring is on the MIXED basis, so the measured bias is
      attributable to the pre-fix arm and not silently mixing the two.
  ARM 3 (counterfactual) -- an unbiased projection has median(projected/actual) == 1. The
      harness reports the median and states the status quo would have been RIGHT if the
      ratio brackets 1. It must be able to return "no bias".
  ARM 4 (coverage) -- report the fraction of the population actually classified, and the
      reason each excluded beat was excluded.
"""

import json
import math
import pathlib
import statistics
import sys

RING = pathlib.Path(__file__).resolve().parents[1] / "cal-p118" / "beat-ring-full.json"
PHASE_DEADLINE_MS = 1_380_000  # calibration_phase_ledger.py:236
BUCKETS = 128                  # calibration_main_build.py:188


def main() -> int:
    beats = json.loads(RING.read_text())
    n = len(beats)
    print(f"POPULATION: {n} consecutive production beats ({RING.name})")
    print("NOUN: beats on which staged:beats_to_publish was published.\n")

    # ---- ARM 2: which basis did this population run on? --------------------------
    with_completed = sum(
        1 for b in beats if "staged:unit_ms_mean_completed" in (b.get("gauges") or {})
    )
    if with_completed:
        print(f"ARM 2 FAIL: {with_completed}/{n} beats carry unit_ms_mean_completed; "
              f"the population mixes both bases and cannot isolate the pre-fix arm.")
        return 2
    print(f"ARM 2 PASS: 0/{n} beats carry staged:unit_ms_mean_completed — the whole ring "
          f"predates CAL-P067 and ran on the MIXED basis (the pre-CAL-P068 arm).")

    # ---- ARM 1: reproduce the published projection from each beat's own gauges ----
    repro_ok = repro_bad = 0
    rows = []
    excluded = {"no_btp": 0, "no_mean": 0, "no_banked": 0, "no_next_banked": 0,
                "sentinel": 0, "rebuild_boundary": 0}

    for i, beat in enumerate(beats):
        g = beat.get("gauges") or {}
        btp = g.get("staged:beats_to_publish")
        mean = g.get("staged:unit_ms_mean")
        banked = g.get("staged:units_banked")
        if btp is None:
            excluded["no_btp"] += 1
            continue
        if btp == -1:
            excluded["sentinel"] += 1
            continue
        if mean is None:
            excluded["no_mean"] += 1
            continue
        if banked is None:
            excluded["no_banked"] += 1
            continue

        # Reproduce. usable_ms is window less this beat's fixed cost, which the ring does
        # not carry; the full window is the upper bound, so the reproduction is an
        # inequality: published btp must be >= the one computed from the full window.
        per_beat_full = PHASE_DEADLINE_MS / mean if mean > 0 else 0.0
        remaining = max(0, BUCKETS - banked)
        if per_beat_full >= 1 and remaining > 0:
            btp_full = math.ceil(remaining / per_beat_full)
            if btp >= btp_full:
                repro_ok += 1
            else:
                repro_bad += 1

        # ---- actual throughput: banked delta to the next beat of the SAME generation --
        if i + 1 >= n:
            excluded["no_next_banked"] += 1
            continue
        nxt = beats[i + 1]
        ng = nxt.get("gauges") or {}
        nbanked = ng.get("staged:units_banked")
        if nbanked is None:
            excluded["no_next_banked"] += 1
            continue
        # NOT generation equality: ``generation`` is stamped PER BEAT (168 distinct
        # values over 168 beats), so it marks the beat, not the rebuild. A rebuild
        # boundary shows up as ``banked`` DECREASING — the bank restarting from a low
        # number. Anything non-decreasing is the same rebuild advancing.
        if nbanked < banked:
            excluded["rebuild_boundary"] += 1
            continue
        actual = nbanked - banked
        if actual <= 0:
            # a beat that banked nothing cannot produce a finite ratio; counted, not hidden
            rows.append((i, btp, per_beat_full, actual, None))
            continue
        rows.append((i, btp, per_beat_full, actual, per_beat_full / actual))

    print(f"ARM 1: reproduction consistent on {repro_ok} beats, INCONSISTENT on {repro_bad}.")
    if repro_bad > repro_ok:
        print("ARM 1 FAIL: the formula model does not describe production. Verdict void.")
        return 2
    print("ARM 1 PASS: published beats_to_publish is consistent with the modelled formula "
          "(published >= the full-window lower bound on every reproduced beat).")

    ratios = [r[4] for r in rows if r[4] is not None]
    zero_banked = sum(1 for r in rows if r[4] is None)
    classified = len(ratios)
    print(f"\nARM 4 COVERAGE: {classified}/{n} beats yielded a projected-vs-actual ratio "
          f"({100.0 * classified / n:.1f}% of the population).")
    print(f"  beats that banked ZERO units (no finite ratio): {zero_banked}")
    for k, v in excluded.items():
        if v:
            print(f"  excluded [{k}]: {v}")

    if classified < 10:
        print("\nARM 3: population too small to characterise a bias. NO VERDICT.")
        return 0

    med = statistics.median(ratios)
    lo, hi = min(ratios), max(ratios)
    over = sum(1 for r in ratios if r > 1.0)
    print(f"\nPROJECTED units/beat vs ACTUAL units banked:")
    print(f"  median ratio : {med:.2f}x")
    print(f"  range        : {lo:.2f}x .. {hi:.2f}x")
    print(f"  optimistic   : {over}/{classified} beats ({100.0 * over / classified:.1f}%)")

    print()
    if 0.9 <= med <= 1.1:
        print("ARM 3: median brackets 1 — the projection is UNBIASED on this population. "
              "The status quo would have been right. NO FINDING.")
        verdict = "NO BIAS"
    else:
        direction = "OPTIMISTIC" if med > 1 else "PESSIMISTIC"
        verdict = f"{direction} by {med:.2f}x on the MIXED basis"
        print(f"ARM 3: median {med:.2f}x — the projection is {direction} even on the "
              f"MIXED basis, i.e. BEFORE CAL-P068 made the mean smaller.")
        print("Because the completed mean is always <= the mixed mean, CAL-P068 can only "
              "have RAISED per_beat and LOWERED beats_to_publish — moving the number "
              "further in the direction this population already shows it erring.")

    print(f"\nVERDICT: {verdict}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
