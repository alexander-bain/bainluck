#!/usr/bin/env python3
"""Under a binding budget, does the sweep spend anything at all on its oldest rows?

The second half of the C-KALSHI-RETENTION-1 fold-in red-first receipt. Same latency
problem as :mod:`probe_drain_false_green`: the defect is only reachable once the
retention horizon drops to the measured value, so it is present at neither commit and
a two-tree test-file diff cannot show it (it shows ``ImportError`` — exit 2, a story
about the harness rather than a result, gotcha #54). This constructs the state.

    # red, against the pre-fold planner
    PYTHONPATH=/path/to/e3a41dd0/backend python3 backend/scripts/probe_overdue_ordering.py
    # green, against the fold-in
    PYTHONPATH=/path/to/1e4c690d/backend python3 backend/scripts/probe_overdue_ordering.py

Exit ``1`` the planner spends nothing on the overdue cohort; ``0`` it spends first.

THE DEFECT
----------
Pre-fold, ``order_candidates`` ranked ``expired`` at ``len(BUCKETS) + 1`` — dead last,
tied with ``unknown`` — on the stated grounds that such rows "cannot be saved". That
reasoning was sound while the horizon was 66 and ``expired`` meant "past the observed
retention floor". It stops being sound the moment the horizon becomes a PLANNING number
derived from the youngest confirmed purge: at 45 days, ``overdue`` no longer means
"gone", it means "past the age where we wanted to have asked". Kalshi retention is
non-monotonic (``RETENTION_IS_MONOTONIC = False``), so a 60-day row may well still
answer — and it is the row with the least time left.

So lowering the constant without re-ranking makes the sweep monotonically WORSE as its
constants get more accurate: every row the better measurement reclassifies as urgent
gets sorted to the back of the queue and starved by any binding budget. The constant
change and the ordering change are not separable; either alone is a regression. That is
the single claim this probe exists to make executable.
"""
from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone

from app.utils import kalshi_retention

POST_REPORT_HORIZON = 45

#: Frozen, and every specimen is an OFFSET from it — never a literal date and never a
#: branch on the wall clock (gotcha #44).
NOW = datetime(2026, 8, 24, 12, 0, tzinfo=timezone.utc)

#: The capture-wall cohort: old enough to be overdue at a 45-day horizon, young enough
#: that the 86-day skip-work bound says a probe is still worth spending.
OVERDUE_AGE_DAYS = 60

#: A comfortable mid-horizon cohort to compete against. Deliberately NOT the 0-7
#: terminal bucket, so the comparison is about rank and not about the terminal
#: bucket's take-to-exhaustion rule.
COMFORTABLE_AGE_DAYS = 25

COHORT = 5
#: Binding: exactly half the demand, so rank decides who is served.
BUDGET = 5


def main() -> int:
    kalshi_retention.CAPTURE_PLANNING_AGE_DAYS = POST_REPORT_HORIZON
    from app.utils import settlement_sweep_plan as plan

    plan.CAPTURE_PLANNING_AGE_DAYS = POST_REPORT_HORIZON

    def rows(age: float, first_id: int, reason: str) -> list:
        return [
            plan.Candidate(
                market_id=first_id + i,
                source="kalshi",
                external_id=f"KX-{reason}-{i}",
                resolution_date=NOW - timedelta(days=age),
                candidate_reason=reason,
            )
            for i in range(COHORT)
        ]

    overdue = rows(OVERDUE_AGE_DAYS, 1000, "overdue")
    comfortable = rows(COMFORTABLE_AGE_DAYS, 2000, "comfortable")
    overdue_ids = {c.market_id for c in overdue}

    # Interleaved on input so the result cannot be an artifact of list order.
    cands = [c for pair in zip(comfortable, overdue) for c in pair]

    selected, skipped = plan.plan_sweep(cands, budget=BUDGET, now=NOW)
    served = sum(1 for c in selected if c.market_id in overdue_ids)

    label = plan.bucket_for(overdue[0].days_remaining(NOW))
    print(f"horizon forced to {POST_REPORT_HORIZON}d")
    print(f"{COHORT} rows at {OVERDUE_AGE_DAYS}d -> bucket {label!r}")
    print(f"{COHORT} rows at {COMFORTABLE_AGE_DAYS}d -> bucket "
          f"{plan.bucket_for(comfortable[0].days_remaining(NOW))!r}")
    print(f"budget {BUDGET} against demand {len(cands)}")
    print(f"selected {len(selected)}; of those, from the overdue cohort: {served}")
    print(f"skipped_by_bucket: {dict(sorted(skipped.items()))}")

    # Conservation, independently of who won: a capped sweep must still account for
    # every candidate it did not take.
    accounted = len(selected) + sum(skipped.values())
    print(f"accounted {accounted} of {len(cands)}")
    if accounted != len(cands):
        print("VERDICT: ROWS VANISHED FROM THE REPORT (red)")
        return 1

    starved = served == 0
    print("VERDICT:", "OVERDUE COHORT STARVED (red)" if starved else "OVERDUE SERVED FIRST (green)")
    return 1 if starved else 0


if __name__ == "__main__":
    sys.exit(main())
