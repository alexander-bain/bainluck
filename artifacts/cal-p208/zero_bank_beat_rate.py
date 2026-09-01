#!/usr/bin/env python3
"""How often does a beat bank ZERO units? — CAL-P208, arm for PC-1 prediction #4.

WHY THIS NUMBER MATTERS TO PC-1
-------------------------------
``save_staged_cursor`` is called ONLY inside the per-unit loop, immediately
after a unit commits (``precompute_calibration.py:4739`` @ ``c1397139``). There
is no unconditional save at beat end. So a beat that banks zero units never
re-stamps the cursor, and ``legacy_fingerprint_accepted`` — which is a READ-time
classification of the value on disk — fires AGAIN on the following beat.

The conveyor's PC-1 rubric says the token must appear "exactly once, then
resumable". That wording is only correct when the cutover beat banks >= 1 unit.
This measures how often that assumption fails.

POPULATION (named in the same noun the finding will use)
--------------------------------------------------------
The 168 consecutive production beats in ``artifacts/cal-p118/beat-ring-full.json``.
Each ring entry is ONE BEAT. The quantity is ``staged:units_completed_this_beat``
— per the conveyor's ITEM 2 vocabulary table, "units banked this beat", and
explicitly NOT ``units_this_beat`` (which is ATTEMPTS).

CONTROL ARMS
------------
1. KNOWN-HIT reproduction: the harness must find at least one beat whose banked
   count is 0 AND whose attempted count is > 0 — a beat that tried and banked
   nothing. If the population contains no such beat the harness reports
   NOT-OBSERVED rather than "0%", because those are different claims (gotcha #53).
2. SHAPE of the hit is printed for the first few hits, so the reader can see
   what one looks like rather than trusting a count.
3. CLASSIFIED FRACTION is reported: beats missing the gauge are UNCLASSIFIABLE
   and are excluded from the denominator, and the exclusion is printed.
4. COUNTERFACTUAL: the harness also computes the rate under the WRONG gauge
   (``units_this_beat``, attempts). If the two rates are equal the ring cannot
   dissociate the arms and the result is reported as NOT-DISSOCIABLE, because a
   number that is the same whichever gauge you pick is not evidence about which
   gauge is right.
5. It exits non-zero if the ring's shape moves (missing/!=168 entries), so a
   stale artifact voids the finding instead of silently re-scaling it.
"""
import json
import os
import sys

RING = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                    "..", "cal-p118", "beat-ring-full.json")
BANKED = "staged:units_completed_this_beat"
ATTEMPTED = "staged:units_this_beat"


def main():
    with open(RING) as fh:
        beats = json.load(fh)

    if not isinstance(beats, list) or len(beats) != 168:
        print(f"ARM 5 FAILED: ring shape moved (type={type(beats).__name__} "
              f"n={len(beats) if hasattr(beats, '__len__') else '?'}); finding VOID")
        return 2

    total = len(beats)
    classified, unclassifiable = [], 0
    for b in beats:
        g = b.get("gauges") or {}
        if BANKED not in g or ATTEMPTED not in g:
            unclassifiable += 1
            continue
        try:
            classified.append((int(g[BANKED]), int(g[ATTEMPTED]), b))
        except (TypeError, ValueError):
            unclassifiable += 1

    n = len(classified)
    if n == 0:
        print("UNCLASSIFIABLE: no beat carries both gauges; finding VOID")
        return 2

    zero_banked = [(bk, at, b) for bk, at, b in classified if bk == 0]
    tried_and_banked_nothing = [t for t in zero_banked if t[1] > 0]
    zero_attempted = [(bk, at, b) for bk, at, b in classified if at == 0]

    print("=" * 74)
    print("ZERO-BANK BEAT RATE — population: 168 consecutive production beats")
    print("=" * 74)
    print(f"ring entries                    : {total}")
    print(f"classified (both gauges present): {n}  ({100.0*n/total:.1f}%)")
    print(f"unclassifiable                  : {unclassifiable}")
    print()
    print(f"beats banking ZERO units        : {len(zero_banked)}  "
          f"({100.0*len(zero_banked)/n:.1f}% of classified)")
    print(f"  ...of which ATTEMPTED > 0     : {len(tried_and_banked_nothing)}  "
          f"({100.0*len(tried_and_banked_nothing)/n:.1f}% of classified)")
    print(f"  ...of which ATTEMPTED == 0    : {len(zero_banked) - len(tried_and_banked_nothing)}")
    print()

    # -- ARM 1: known-hit reproduction -------------------------------------
    if not tried_and_banked_nothing:
        print("ARM 1 (known hit): NOT-OBSERVED — no beat in this population "
              "attempted units and banked none.")
        print("  => the rate is reported as an OBSERVED CEILING on this ring, "
              "NOT as a proven 0%.")
    else:
        print(f"ARM 1 (known hit): REPRODUCED — {len(tried_and_banked_nothing)} hit(s).")
        print("ARM 2 (shape of a hit):")
        for bk, at, b in tried_and_banked_nothing[:4]:
            g = b.get("gauges") or {}
            print(f"    attempted={at:>3} banked={bk:>3} "
                  f"cancelled={g.get('staged:units_cancelled','<absent>'):>4} "
                  f"units_banked_cum={g.get('staged:units_banked')} "
                  f"at={b.get('recorded_at') or b.get('updated_at') or '<no ts>'}")
    print()

    # -- ARM 4: counterfactual on the WRONG gauge --------------------------
    r_right = len(zero_banked) / n
    r_wrong = len(zero_attempted) / n
    print("ARM 4 (counterfactual — same question asked of the WRONG gauge):")
    print(f"    rate using {BANKED:>36} = {100*r_right:.1f}%")
    print(f"    rate using {ATTEMPTED:>36} = {100*r_wrong:.1f}%")
    dissociable = r_right != r_wrong
    print(f"    arms_dissociable: {dissociable}")
    if not dissociable:
        print("    => the ring cannot tell the two gauges apart on this question; "
              "the number is NOT evidence about which gauge is right.")
    print()

    print("VERDICT:")
    if tried_and_banked_nothing:
        pct = 100.0 * len(tried_and_banked_nothing) / n
        print(f"  A beat CAN attempt units and bank none: {pct:.1f}% of {n} classified beats.")
        print("  => PC-1 prediction #4 ('exactly once, then resumable') is CONDITIONAL on the")
        print("     cutover beat banking >= 1 unit. A second consecutive")
        print("     legacy_fingerprint_accepted is NOT a failure; it means the prior beat")
        print("     banked nothing, so save_staged_cursor never ran and the cursor was")
        print("     never re-stamped. Grade the token on the first beat that BANKS.")
    else:
        print("  NOT-OBSERVED on this ring. The mechanism is proven from source")
        print("  (save is per-unit only, :4739) but its rate is unmeasured here.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
