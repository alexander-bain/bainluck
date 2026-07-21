"""Guard tests for the time-horizon calibration chunk + resumable cursor.

Item 1 (Queue #220/221): `_compute_time_horizon_calibration` ran all four
horizons in one process and blew the 600s soft limit (0/27 successes over 3 days,
12 consecutive SoftTimeLimitExceeded at 600.9s). Each horizon is a LATERAL
last-snapshot probe over ~539K eligible resolved non-event outcomes.

The fix bounds each horizon with a per-query statement_timeout, persists
completed horizons to a WIP accumulator keyed by label, and stops the run at an
internal deadline (resuming next beat). These tests assert the mechanism is in
place and sanely sized without needing a DB — the SQL/timings are runtime, but
the constants and control-flow are inspectable.
"""

import importlib
import inspect

pc = importlib.import_module("app.tasks.precompute_calibration")


class TestTimeHorizonBudget:
    def test_deadline_leaves_room_for_a_full_horizon_under_soft_limit(self):
        # A horizon is only started if it can run its full statement_timeout and
        # still finish before the deadline — and the deadline itself sits under
        # the 600s Celery soft_time_limit so the run always returns cleanly.
        assert pc._HORIZON_DEADLINE_S < 600
        assert pc._HORIZON_STMT_TIMEOUT_S > 0
        # Worst case: a horizon started right at the guard boundary ends by
        # deadline; leave margin under the soft limit for the Redis write.
        assert pc._HORIZON_DEADLINE_S + 5 <= 600

    def test_wip_key_is_distinct_from_published_key(self):
        # The WIP accumulator must not clobber the published payload — the public
        # key is only written once every horizon is present.
        assert pc._TIME_HORIZON_WIP_KEY != "bainluck:calibration:time_horizon"
        assert "wip" in pc._TIME_HORIZON_WIP_KEY

    def test_function_is_resumable_and_bounded(self):
        src = inspect.getsource(pc._compute_time_horizon_calibration)
        # Resumable cursor: skip already-computed horizons, persist WIP as we go.
        assert "if label in horizons_result:" in src
        assert "continue" in src
        assert pc._TIME_HORIZON_WIP_KEY in src or "_TIME_HORIZON_WIP_KEY" in src
        # Bounded: per-horizon statement_timeout is armed.
        assert "statement_timeout" in src
        # Deadline guard bounds the longest single op (start of a horizon), not
        # just the loop boundary.
        assert "_HORIZON_STMT_TIMEOUT_S" in src and "_HORIZON_DEADLINE_S" in src
        # Publishes the full payload only after the loop, and clears the cursor.
        assert "rc.delete(_TIME_HORIZON_WIP_KEY)" in src

    def test_all_horizons_covered_by_labels(self):
        # The cursor keys on label; labels must be unique so resume can't collide.
        labels = [label for label, _ in pc._HORIZONS]
        assert len(labels) == len(set(labels))
