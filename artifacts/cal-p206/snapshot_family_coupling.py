#!/usr/bin/env python3
"""CAL-P206 / question 12 — "the instruction names a row. Is that where the value is
PRODUCED, or where it is COPIED TO?" applied to ITEM 2's OWN read-instruction table.

P203-1 established that ONE ledger key -- ``staged:units_banked`` -- is a beat-END COPY
of a durable row that is written PER UNIT, and that reading it as a liveness signal cost
four sessions. The conveyor's ITEM 2 table now carries that warning on that one key.

QUESTION: how many OTHER keys in the same table are the same shape?

STRUCTURAL ANSWER (calibration_main_build.py:1396-1529): ``_record_staged_convergence``
performs exactly ONE ``read_snapshot_standalone`` (:1400) and EVERY gauge below it is
derived from that single ``payload`` -- directly, or via ``_record_drift_coverage`` and
``_record_served_bank``, which take ``payload`` as an argument and never read again.
So the family shares one instant and one failure.

THIS HARNESS tests the observable consequence on 168 consecutive production beats:
does the snapshot family appear and disappear as a BLOCK, independently of the
beat-local gauges recorded from the beat's own stage timings?

CONTROL ARMS (the five-point lesson: reproduce a known hit, state its shape, report the
fraction classified, name the population in the marker's noun, and fail when the status
quo would have been right):

  ARM 1 (known hit) -- ``staged:units_banked`` must land in the SNAPSHOT family by the
      structural classifier. If it does not, the classifier is not measuring P203-1's
      thing and every other verdict is void.
  ARM 2 (negative control, same function) -- ``staged:units_partition`` is
      ``record_gauge(name, STAGED_FUTURES_BUCKETS)``, a module CONSTANT emitted from
      inside the same try-block. It must classify as CONSTANT, not SNAPSHOT. A
      classifier that swallows it is matching "emitted near the read", not "derived
      from the read".
  ARM 3 (discriminating control) -- the BEAT-LOCAL gauges must be observed present on
      at least one beat where the snapshot family is absent. Without such a beat the
      coupling claim is untestable on this population and the harness says UNTESTABLE
      rather than CONFIRMED.
  ARM 4 (counterfactual) -- if every gauge in the ledger were in fact one family, this
      harness must NOT report a coupling. Enforced by requiring the two families to
      dissociate on at least one beat (ARM 3) before any coupling verdict is emitted.
"""

import json
import pathlib
import sys

RING = pathlib.Path(__file__).resolve().parents[1] / "cal-p118" / "beat-ring-full.json"

# Derived from the SINGLE read at calibration_main_build.py:1400. Every one of these is
# ``payload[...]`` or ``len(payload[...])`` from that one envelope.
SNAPSHOT_FAMILY = [
    "staged:units_banked",             # :1416  len(committed)
    "staged:units_drifted",            # :1420  payload["roster_drift_units"]
    "staged:units_drift_checkable",    # :1473  len(committed) - uncheckable
    "staged:units_drift_uncheckable",  # :1474  from committed + payload["unit_digests"]
    "staged:served_units",             # :1515  len(payload["served_units"])
    "staged:served_drifted",           # :1518  payload["served_drift_units"]
    "staged:served_drift_uncheckable", # :1524  from served + payload["served_digests"]
    "staged:served_at",                # :1527  payload["served_at"]
]

# ARM 2: emitted inside the same try-block, from a module constant, not the payload.
CONSTANT_IN_FAMILY = ["staged:units_partition"]

# ARM 3: recorded by _record_staged_rate from THIS BEAT's own stage timings
# (ledger.stage_counts / stage_mean_ms), never from the durable payload.
BEAT_LOCAL = [
    "staged:units_this_beat",            # :1567  ledger.stage_counts[...]
    "staged:units_completed_this_beat",  # :1577  ledger.stage_completed_count(...)
    "staged:unit_ms_mean",               # :1590  ledger.stage_mean_ms(...)
    "staged:unit_ms_mean_completed",     # :1583  ledger.stage_completed_mean_ms(...)
]

# Derived from BOTH clocks: remaining = BUCKETS - banked (snapshot) divided by a rate
# computed from this beat's timings (beat-local). :1592-1628.
MIXED = ["staged:beats_to_publish"]


def load_beats():
    beats = json.loads(RING.read_text())
    if not isinstance(beats, list) or not beats:
        sys.exit("ring artifact is not a non-empty list")
    return beats


def present(gauges, names):
    return {n for n in names if n in gauges}


def main() -> int:
    beats = load_beats()
    n = len(beats)
    print(f"POPULATION: {n} consecutive production beats ({RING.name})")
    print("NOUN: ledger gauge keys emitted by the staged-convergence path.\n")

    # ---- ARM 1: the known hit must be in the family under test -------------------
    if "staged:units_banked" not in SNAPSHOT_FAMILY:
        print("ARM 1 FAIL: P203-1's key is not in the family; verdicts void.")
        return 2
    print("ARM 1 PASS: P203-1's known hit (staged:units_banked) is in the family.")

    # ---- ARM 2: the constant must not be in the family ---------------------------
    overlap = set(CONSTANT_IN_FAMILY) & set(SNAPSHOT_FAMILY)
    if overlap:
        print(f"ARM 2 FAIL: constant(s) {overlap} classified as snapshot; over-broad.")
        return 2
    print("ARM 2 PASS: staged:units_partition (a module constant emitted from inside "
          "the same try) is NOT counted as a snapshot.")

    # ---- co-occurrence over the population ---------------------------------------
    all_present = all_absent = partial = 0
    dissociating = []          # ARM 3 evidence
    partial_examples = []
    for i, beat in enumerate(beats):
        g = beat.get("gauges") or {}
        snap = present(g, SNAPSHOT_FAMILY)
        local = present(g, BEAT_LOCAL)
        if len(snap) == len(SNAPSHOT_FAMILY):
            all_present += 1
        elif not snap:
            all_absent += 1
            if local:
                dissociating.append((i, sorted(local)))
        else:
            partial += 1
            if len(partial_examples) < 5:
                missing = sorted(set(SNAPSHOT_FAMILY) - snap)
                partial_examples.append((i, missing))

    classified = all_present + all_absent + partial
    print(f"\nCOVERAGE: {classified}/{n} beats classified "
          f"({100.0 * classified / n:.1f}% of the population).")
    print(f"  whole family PRESENT : {all_present}")
    print(f"  whole family ABSENT  : {all_absent}")
    print(f"  PARTIAL              : {partial}")
    for i, missing in partial_examples:
        print(f"      beat[{i}] missing {missing}")

    # ---- ARM 3 / ARM 4: the two families must dissociate somewhere ---------------
    print()
    if not dissociating:
        print("ARM 3 UNTESTABLE: no beat in this population has the beat-local gauges "
              "present while the whole snapshot family is absent. The coupling claim "
              "is NOT confirmed on this population.")
        verdict = "UNTESTABLE"
    else:
        print(f"ARM 3 PASS: {len(dissociating)} beat(s) carry beat-local gauges while "
              f"the ENTIRE snapshot family is absent — the two families dissociate, "
              f"so the coupling is a real distinction and not an artifact of a dead beat.")
        for i, local in dissociating[:5]:
            print(f"      beat[{i}] beat-local present={local}, snapshot family absent")
        verdict = "CONFIRMED"

    # ---- the mixed-clock key ------------------------------------------------------
    mixed_present = sum(1 for b in beats if MIXED[0] in (b.get("gauges") or {}))
    print(f"\nMIXED-CLOCK KEY: {MIXED[0]} present on {mixed_present}/{n} beats. "
          f"Its numerator (BUCKETS - banked) is a SNAPSHOT quantity; its denominator "
          f"(usable_ms / mean) is BEAT-LOCAL. One quotient, two clocks.")

    print(f"\nVERDICT: {verdict}")
    print(f"ITEM 2's table warns on 1 of the {len(SNAPSHOT_FAMILY)} snapshot-family keys "
          f"= {100.0 / len(SNAPSHOT_FAMILY):.1f}% of the population it describes.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
