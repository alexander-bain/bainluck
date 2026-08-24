#!/usr/bin/env python3
"""Does the sweep planner put a row it cannot answer at the head of the queue?

The red-first receipt for #2175, written so that the red run and the green run are
the SAME FILE against two trees. It imports only symbols that exist on both sides of
the fix and asks ``Candidate.__dataclass_fields__`` which planner it is talking to,
so there is no version of this script that can only produce one answer.

    # red, against the unfixed planner
    PYTHONPATH=/path/to/master/backend python3 backend/scripts/probe_sweep_ordering.py
    # green, against the fix
    PYTHONPATH=/path/to/fix/backend python3 backend/scripts/probe_sweep_ordering.py

Exit code is the verdict and is meant to be read as a value (gotcha #54):
``1`` the unanswerable row is at the head — livelocked; ``0`` it is not.

WHY A SCRIPT AND NOT ONLY A TEST
--------------------------------
The pytest guards in ``test_settlement_sweep_plan.py`` are the durable green, but
they cannot produce a functional red: against the unfixed planner they fail to
import ``TIER_NEVER_PROBED`` and pytest exits ``2``, which is a story about the
harness rather than a result. This script is the part of the receipt that can
actually run red.

THE SPECIMEN
------------
Two candidates, both in the terminal bucket, so bucket rank cannot decide between
them:

    id=1  1.0 days to purge, ALREADY answered ``ambiguous_empty`` three times
    id=2  6.0 days to purge, NEVER probed

The pre-fix key is ``(bucket rank, days remaining, market_id)``. It has no field in
which a probe history could even be expressed, so id=1 wins by construction on
every pass forever — and a budget of one is spent re-asking the row that has
already told us three times that it cannot answer. That is the livelock, and it is
why the fix is an ordering change rather than a change to what ``ambiguous_empty``
means.
"""
from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone

from app.utils.kalshi_retention import CAPTURE_PLANNING_AGE_DAYS
from app.utils.settlement_sweep_plan import Candidate, order_candidates, plan_sweep

# Frozen, and the ages below are offsets from it. A wall-clock read here would make
# the specimen's bucket membership drift with the hour (gotcha #44).
NOW = datetime(2026, 8, 21, 12, 0, tzinfo=timezone.utc)


def mk(market_id: int, days_remaining: float, **history) -> Candidate:
    age = CAPTURE_PLANNING_AGE_DAYS - days_remaining
    kwargs = dict(
        market_id=market_id,
        source="kalshi",
        external_id=f"KXTEST-{market_id}",
        resolution_date=NOW - timedelta(days=age),
        candidate_reason="missing_winner",
    )
    # The pre-fix Candidate has no history fields at all — that absence IS the
    # defect, so the keywords are filtered rather than passed blind.
    fields = Candidate.__dataclass_fields__
    kwargs.update({k: v for k, v in history.items() if k in fields})
    return Candidate(**kwargs)


def main() -> int:
    fields = Candidate.__dataclass_fields__
    build = "POST-FIX (history-aware)" if "attempts" in fields else "PRE-FIX (deadline-only)"
    print(f"planner build: {build}")
    print(f"Candidate fields: {sorted(fields)}")

    answered = mk(1, 1.0, attempts=3, stable_nonanswers=3)
    unasked = mk(2, 6.0)

    order = [c.market_id for c in order_candidates([answered, unasked], NOW)]
    selected, _skipped = plan_sweep([answered, unasked], budget=1, now=NOW)

    print(f"order_candidates -> {order}")
    print(f"plan_sweep(budget=1) selects -> {[c.market_id for c in selected]}")

    livelocked = order[0] == 1
    print(f"HEAD OF QUEUE IS THE UNANSWERABLE ROW: {livelocked}")
    print("VERDICT:", "LIVELOCKED (red)" if livelocked else "FIXED (green)")
    return 1 if livelocked else 0


if __name__ == "__main__":
    sys.exit(main())
