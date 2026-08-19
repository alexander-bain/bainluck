"""The phantom hard kill: a derived count refuted by its own payload (#1609, #1501).

`hard_kills_24h` is DERIVED — ``starts − (successes + failures + incompletes)``
— and the four counters do **not** share a window. Each is stamped
``SET NX EX 86400`` at its own first increment, so each expires on its own
schedule. On a task whose cadence is *exactly* 24 h, every key's expiry lands
within milliseconds of the next increment, and whether that increment lands on a
live key or a dead one is a race that can resolve DIFFERENTLY for ``starts`` and
``successes`` — they are written a fraction of a second apart.

**Measured on production, 2026-08-18T22:45Z. One morning, two tasks, the same
race resolving in opposite directions:**

* ``mlb_schedule_coverage`` — ``starts_24h: 1``, ``successes_24h: 0``,
  ``successes_window_s: null`` ⇒ derived ``hard_kills_24h: 1``, ``health:
  critical``, *"1 runs started, none reached an end handler — hard-killed
  (memory / hard time limit)"*. The **same payload** carried
  ``last_started_at 07:05:00.095``, ``last_success_at 07:05:00.851``,
  ``last_duration_ms 734``, and a fully populated ``last_result_summary`` for
  2026-08-18. Those three fields ARE the end handler's writes.
* ``grid_sentinel`` — ``starts_24h: 0``, ``successes_24h: 1``. The inverse, and
  invisible only because of the ``max(0, …)`` clamp.

Why it matters beyond tidiness: LAT-P069 reported this task as "1 attempt /
0 terminals" and the T5 read scheduled for 2026-08-19 07:50–17:01Z grades
exactly this task. A phantom red graded against #1609's routing would have
blamed the wrong cause — which is the failure mode the fenced read exists to
avoid.
"""

from __future__ import annotations

import pytest

from app.tasks import redis_state
from app.tasks.redis_state import (
    TASK_METRICS_PREFIX,
    _terminal_evidence_refutes_hard_kill,
)


class _Fake:
    """Minimal redis double: one hash per task, plus counter keys."""

    def __init__(self, hashes, counters=None):
        self.hashes = hashes
        self.counters = counters or {}

    def hgetall(self, key):
        return self.hashes.get(key.rsplit(":", 1)[-1], {})

    def get(self, key):
        return self.counters.get(key)

    def ttl(self, key):
        return -1 if key in self.counters else -2

    def lrange(self, *_a, **_k):
        return []

    def keys(self, _pattern):
        return [f"{TASK_METRICS_PREFIX}:{t}".encode() for t in self.hashes]


def _metrics(monkeypatch, task, hash_fields, counters):
    monkeypatch.setattr(
        redis_state, "get_redis_client", lambda *a, **k: _Fake({task: hash_fields}, counters)
    )
    return redis_state.get_task_metrics(task)


#: The production payload that exposed this, verbatim in the fields that matter.
_MLB_HASH = {
    b"consecutive_failures": b"0",
    b"last_started_at": b"2026-08-18T07:05:00.095435+00:00",
    b"last_success_at": b"2026-08-18T07:05:00.851187+00:00",
    b"last_duration_ms": b"734",
}
_MLB_COUNTERS = {f"{TASK_METRICS_PREFIX}:mlb_schedule_coverage:starts": b"1"}


class TestTheHelperInIsolation:
    def test_a_success_after_the_start_refutes_the_kill(self):
        reason = _terminal_evidence_refutes_hard_kill(
            {
                "last_started_at": "2026-08-18T07:05:00.095435+00:00",
                "last_success_at": "2026-08-18T07:05:00.851187+00:00",
            }
        )
        assert reason is not None
        assert "counter-window artifact" in reason

    @pytest.mark.parametrize(
        "field", ["last_success_at", "last_failure_at", "last_incomplete_at"]
    )
    def test_any_terminal_stamp_counts_as_reaching_a_handler(self, field):
        # A failure is still a run that reached an end handler. Only a kill
        # reaches none — that is the whole distinction being drawn.
        reason = _terminal_evidence_refutes_hard_kill(
            {"last_started_at": "2026-08-18T07:05:00+00:00", field: "2026-08-18T07:06:00+00:00"}
        )
        assert reason is not None

    def test_a_terminal_from_BEFORE_the_start_does_not_refute(self):
        # Yesterday's success says nothing about today's run. If this returned a
        # refutation, a genuinely killed task would be silenced by a stale stamp
        # — turning a real alarm off, which is far worse than the phantom.
        assert (
            _terminal_evidence_refutes_hard_kill(
                {
                    "last_started_at": "2026-08-18T07:05:00+00:00",
                    "last_success_at": "2026-08-17T07:05:00+00:00",
                }
            )
            is None
        )

    def test_no_start_stamp_means_no_evidence_either_way(self):
        assert (
            _terminal_evidence_refutes_hard_kill(
                {"last_success_at": "2026-08-18T07:05:00+00:00"}
            )
            is None
        )

    def test_no_terminal_stamp_at_all_is_a_real_kill(self):
        assert (
            _terminal_evidence_refutes_hard_kill(
                {"last_started_at": "2026-08-18T07:05:00+00:00"}
            )
            is None
        )

    @pytest.mark.parametrize("bad", ["", None, "not-a-date", "2026-13-45T99:99", 12345, []])
    def test_unparseable_stamps_never_refute(self, bad):
        assert (
            _terminal_evidence_refutes_hard_kill(
                {"last_started_at": bad, "last_success_at": bad}
            )
            is None
        )

    def test_sub_second_ordering_noise_is_absorbed(self):
        # Both stamps are written by the same process from the same clock, so
        # the tolerance only covers ordering noise. It is not a window: a
        # terminal a full minute early must NOT refute.
        assert (
            _terminal_evidence_refutes_hard_kill(
                {
                    "last_started_at": "2026-08-18T07:05:00.900000+00:00",
                    "last_success_at": "2026-08-18T07:05:00.100000+00:00",
                }
            )
            is not None
        )
        assert (
            _terminal_evidence_refutes_hard_kill(
                {
                    "last_started_at": "2026-08-18T07:05:00+00:00",
                    "last_success_at": "2026-08-18T07:04:00+00:00",
                }
            )
            is None
        )


class TestTheProductionPayload:
    """The exact reading that would have mis-graded T5."""

    def test_the_phantom_kill_is_refuted(self, monkeypatch):
        result = _metrics(monkeypatch, "mlb_schedule_coverage", _MLB_HASH, _MLB_COUNTERS)
        assert result["starts_24h"] == 1
        assert result["successes_24h"] == 0  # the counter is genuinely gone
        assert result["hard_kills_24h"] == 0  # ...but it was not a kill
        assert "counter-window artifact" in result["hard_kills_refuted"]

    def test_health_no_longer_asserts_a_mechanism_its_own_payload_refutes(self, monkeypatch):
        result = _metrics(monkeypatch, "mlb_schedule_coverage", _MLB_HASH, _MLB_COUNTERS)
        assert result["health"] == "healthy"
        assert "hard-killed" not in result.get("health_reason", "")

    def test_without_the_terminal_stamps_the_same_counters_still_read_critical(
        self, monkeypatch
    ):
        # Non-vacuity. The reversal must be driven by the EVIDENCE, not by the
        # task name or by the counters — strip the stamps and the alarm returns.
        result = _metrics(
            monkeypatch,
            "mlb_schedule_coverage",
            {b"consecutive_failures": b"0"},
            _MLB_COUNTERS,
        )
        assert result["hard_kills_24h"] == 1
        assert result["health"] == "critical"
        assert "hard-killed" in result["health_reason"]


class TestOnlyTheLastRunIsSpokenFor:
    def test_a_real_kill_among_earlier_runs_survives(self, monkeypatch):
        # 5 starts, 2 successes -> 3 derived kills. The stamps are evidence about
        # exactly ONE run (the last), so exactly one is refuted. Refuting all
        # three would use one run's evidence to clear four.
        result = _metrics(
            monkeypatch,
            "some_task",
            {
                b"consecutive_failures": b"0",
                b"last_started_at": b"2026-08-18T07:05:00+00:00",
                b"last_success_at": b"2026-08-18T07:06:00+00:00",
            },
            {
                f"{TASK_METRICS_PREFIX}:some_task:starts": b"5",
                f"{TASK_METRICS_PREFIX}:some_task:successes": b"2",
            },
        )
        assert result["hard_kills_24h"] == 2
        assert "hard_kills_refuted" in result

    def test_a_healthy_task_is_untouched_and_carries_no_refutation_key(self, monkeypatch):
        result = _metrics(
            monkeypatch,
            "some_task",
            {b"consecutive_failures": b"0"},
            {
                f"{TASK_METRICS_PREFIX}:some_task:starts": b"10",
                f"{TASK_METRICS_PREFIX}:some_task:successes": b"10",
            },
        )
        assert result["hard_kills_24h"] == 0
        # The key appears only when something was actually refuted; an always-on
        # key would make "refuted" the normal state and stop meaning anything.
        assert "hard_kills_refuted" not in result
        assert result["health"] == "healthy"


class TestTheCadenceTrapIsDocumented:
    """Guards on the reads the T5 window depends on, so the trap is not re-sprung."""

    def test_the_counter_ttl_equals_a_daily_cadence(self):
        # This is the whole mechanism in one assertion: the counter window and
        # the cadence of a daily beat are the SAME 86400 s, so every daily task
        # races its own expiry once a day. If this ever stops being true the
        # phantom changes shape and the reconciliation should be re-measured.
        assert redis_state.WINDOW_COUNTER_TTL == 86400

    def test_calibration_sentinel_is_weekly_and_cannot_fill_a_24h_counter(self):
        # Not a bug — a cadence fact with a grading consequence. A weekly beat's
        # `successes_24h` is 0 on six days in seven, by construction. Grading it
        # as "no run recorded in 24h" scores a healthy task red.
        import inspect

        from app.tasks import __init__ as tasks_init  # noqa: F401
        import app.tasks as tasks_mod

        source = inspect.getsource(tasks_mod)
        idx = source.index('"task": "app.tasks.calibration_sentinel"')
        window = source[idx : idx + 300]
        assert "day_of_week=1" in window, (
            "calibration_sentinel is weekly (Monday 06:20 UTC); if that changed, "
            "the T5 grading protocol's cadence table must change with it"
        )
