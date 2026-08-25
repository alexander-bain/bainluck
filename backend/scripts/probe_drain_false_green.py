#!/usr/bin/env python3
"""Would lowering the retention horizon have flipped the capture wall's gate green?

The red-first receipt for the C-KALSHI-RETENTION-1 fold-in, and it exists because the
defect it proves is **latent** rather than present at either commit:

* at ``e3a41dd0`` (pre-fold) the horizon is 66, so the 59-66 day production cohort
  lands in the ``0-7`` bucket and the drain gate reads it correctly;
* at ``1e4c690d`` (post-fold) the gate sums over ``TERMINAL_BUCKETS`` and is correct;
* the failure only exists in the state "horizon lowered, drain gate not yet widened" —
  which is exactly the state that applying the retention report's constants-audit
  table WITHOUT the ordering half would have shipped, and which was therefore never
  committed.

So a plain two-tree diff cannot show it. This script constructs the state instead: it
takes whatever tree it is pointed at, forces the horizon to the post-report value, and
asks the runner's own drain expression what it would have said.

    # red, against the pre-fold planner
    PYTHONPATH=/path/to/e3a41dd0/backend python3 backend/scripts/probe_drain_false_green.py
    # green, against the fold-in
    PYTHONPATH=/path/to/1e4c690d/backend python3 backend/scripts/probe_drain_false_green.py

Exit code is the verdict, read as a value (gotcha #54): ``1`` the gate reports DRAINED
over uncaptured rows — a false green; ``0`` it does not.

WHY THIS IS THE MOST IMPORTANT OF THE THREE PROBES
--------------------------------------------------
``terminal_bucket_drained`` is the number the capture deadline is judged by. A livelock
wastes a sweep and is visible in the next report. A false green ENDS the program: it
says the work is done, over ~1,096 rows nobody ever asked a source about, and the
evidence that would contradict it expires. Gotcha #53 one level up — an empty bucket is
not an absence of work.
"""
from __future__ import annotations

import sys

from app.utils import kalshi_retention

#: The horizon the retention report's own arithmetic yields (47d confirmed purge minus
#: the same two-day margin the old 66 used). Forced in rather than imported, so this
#: script constructs the dangerous state on a tree that predates it.
POST_REPORT_HORIZON = 45

#: Age of the capture-wall cohort on the measurement date. The report puts the
#: 1,096-terminal program at roughly 59-66 days old.
COHORT_AGE_DAYS = 60

#: Rows in that cohort no sweep has ever captured. Any non-zero count must keep the
#: gate red; the exact value is not what is being tested.
UNCAPTURED = 40


def main() -> int:
    kalshi_retention.CAPTURE_PLANNING_AGE_DAYS = POST_REPORT_HORIZON

    # Imported AFTER the patch: the planner reads the constant at call time, but a
    # module that had already bound it would otherwise keep the old value.
    from app.utils import settlement_sweep_plan as plan

    plan.CAPTURE_PLANNING_AGE_DAYS = POST_REPORT_HORIZON

    remaining = POST_REPORT_HORIZON - COHORT_AGE_DAYS
    label = plan.bucket_for(remaining)
    uncaptured_by_bucket = {label: UNCAPTURED}

    # The runner's own drain expression, both shapes.
    single = uncaptured_by_bucket.get(plan.TERMINAL_BUCKET, 0)
    buckets = getattr(plan, "TERMINAL_BUCKETS", frozenset({plan.TERMINAL_BUCKET}))
    summed = sum(uncaptured_by_bucket.get(name, 0) for name in buckets)

    build = "POST-FOLD (urgency set)" if hasattr(plan, "TERMINAL_BUCKETS") else "PRE-FOLD (single label)"
    print(f"planner build: {build}")
    print(f"horizon forced to {POST_REPORT_HORIZON}d; cohort age {COHORT_AGE_DAYS}d")
    print(f"cohort bucket: {label!r}   uncaptured in it: {UNCAPTURED}")
    print(f"drain over TERMINAL_BUCKET only -> {single}")
    print(f"drain over TERMINAL_BUCKETS     -> {summed}")

    # The gate as the runner computes it on this tree.
    gate = summed if hasattr(plan, "TERMINAL_BUCKETS") else single
    drained = gate == 0
    print(f"terminal_bucket_drained would report: {drained}")

    false_green = drained and UNCAPTURED > 0
    print("VERDICT:", "FALSE GREEN (red)" if false_green else "GATE HOLDS (green)")
    return 1 if false_green else 0


if __name__ == "__main__":
    sys.exit(main())
