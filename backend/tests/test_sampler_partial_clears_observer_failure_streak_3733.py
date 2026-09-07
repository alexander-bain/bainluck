"""CAL-P1042 (#3733) — the named repair `SAMPLER-PARTIAL-CLEARS-OBSERVER-FAILURE-STREAK-3733`.

Why this file exists: a fix that changed the word and not the number
---------------------------------------------------------------------
CAL-P1042's first presentation (CERT-2153) moved the beat gauge sampler's
producer-fault verdict from ``failed`` to ``partial``, on the correct reasoning
that a producer's condition is not the observer's failure. The cert BLOCKED it,
and was right: the ship was *"health stops reading critical"*, and the terminal
alone does not deliver it.

Two facts, both already in the tree, compose into that:

* ``record_task_incomplete`` **freezes** ``consecutive_failures`` rather than
  clearing it. Deliberate, and correct for a resumable sweep that keeps
  stopping — the streak is real and a partial must not wipe it.
* ``get_task_metrics`` reads the streak band (``consecutive >= 5 -> critical``)
  **before** the last-verdict band.

So the 78 already banked would have held ``health: critical`` for as long as the
producer's fault lasted, and a task in this state never reaches
``record_task_success`` — the only writer that zeroes the streak — so nothing
could ever retract it. Worse, ``record_task_incomplete`` refreshes the hash TTL
on every call, so the stale streak could not even age out.

The repair is :data:`~app.utils.task_verdict.SELF_OK_FIELD`: an opt-in field by
which a task states its OWN machinery finished. It is the only thing that clears
a streak from the incomplete path, and no other task sets it.

The property this file defends, in one line:

    **a false streak clears; a real streak survives.**

Both directions, because a repair that only proved the first would have replaced
a permanently-red instrument with a permanently-green one.
"""

from __future__ import annotations

import pytest

from app.tasks import redis_state
from app.tasks.redis_state import TASK_METRICS_PREFIX
from app.utils.task_verdict import SELF_OK_FIELD, clears_failure_streak


class _FakePipe:
    """Records writes; `execute` applies them to the parent double."""

    def __init__(self, parent):
        self.parent = parent

    def hset(self, key, mapping=None, **_kw):
        self.parent.hashes.setdefault(key, {}).update(
            {str(k): str(v) for k, v in (mapping or {}).items()}
        )
        return self

    def set(self, key, value, ex=None, nx=False):
        if nx and key in self.parent.counters:
            return self
        self.parent.counters[key] = str(value)
        return self

    def incr(self, key):
        self.parent.counters[key] = str(int(self.parent.counters.get(key, 0)) + 1)
        return self

    def expire(self, *_a, **_k):
        return self

    def lpush(self, *_a, **_k):
        return self

    def ltrim(self, *_a, **_k):
        return self

    def execute(self):
        return []


class _FakeRedis:
    """Enough of redis for the WRITE path and the READ path in one object.

    Both halves matter: this suite's whole point is the round trip. Asserting on
    the mapping handed to `hset` would re-state the implementation; asserting on
    what `get_task_metrics` then *publishes* is the fact an operator meets.
    """

    def __init__(self, hashes=None, counters=None):
        self.hashes = hashes or {}
        self.counters = counters or {}

    def pipeline(self):
        return _FakePipe(self)

    def hgetall(self, key):
        return dict(self.hashes.get(key, {}))

    def hget(self, key, field):
        return self.hashes.get(key, {}).get(field)

    def get(self, key):
        return self.counters.get(key)

    def ttl(self, key):
        return -1 if key in self.counters else -2

    def lrange(self, *_a, **_k):
        return []

    def keys(self, _pattern):
        return [k.encode() for k in self.hashes]


SAMPLER = "calibration_beat_gauge_sampler"
_KEY = f"{TASK_METRICS_PREFIX}:{SAMPLER}"

#: The production state on 2026-09-06, in the fields that decide health.
_SEEDED_78 = {"consecutive_failures": "78", "last_verdict": "failed"}

#: The artifact the sampler returns on a producer fault, in the fields the
#: health surface reads. `self_ok` is the assertion under test.
_PRODUCER_FAULT_SUMMARY = {
    "terminal": "partial",
    SELF_OK_FIELD: True,
    "producer_condition": {
        "measured": True,
        "conditions": ["gauges_absent"],
        "gauges_absent": ["staged:served_at"],
        "beat_terminal": "cancelled",
    },
    "history_write": "unchanged",
    "generation": 1788734295931,
}


def _fake(monkeypatch, hashes=None, counters=None):
    fake = _FakeRedis(hashes=hashes, counters=counters)
    monkeypatch.setattr(redis_state, "get_redis_client", lambda *a, **k: fake)
    return fake


# ---------------------------------------------------------------------------
# The pure predicate
# ---------------------------------------------------------------------------

class TestClearsFailureStreak:
    def test_a_partial_asserting_self_ok_clears(self):
        assert clears_failure_streak("partial", _PRODUCER_FAULT_SUMMARY) is True

    def test_an_ordinary_partial_does_not(self):
        """The resumable-sweep case. This is the behaviour that must NOT move."""
        assert clears_failure_streak("partial", {"terminal": "partial"}) is False

    @pytest.mark.parametrize("verdict", ["failed", "unknown", "complete", None, ""])
    def test_only_a_partial_may_clear_however_loudly_it_asserts(self, verdict):
        assert clears_failure_streak(verdict, {SELF_OK_FIELD: True}) is False

    @pytest.mark.parametrize("truthy", [1, "yes", "true", [1], {"a": 1}, 1.0])
    def test_a_merely_TRUTHY_value_does_not_clear(self, truthy):
        """Overriding a safety counter takes a literal True, nothing else."""
        assert clears_failure_streak("partial", {SELF_OK_FIELD: truthy}) is False

    @pytest.mark.parametrize("falsey", [False, 0, None])
    def test_an_explicit_negative_does_not_clear(self, falsey):
        assert clears_failure_streak("partial", {SELF_OK_FIELD: falsey}) is False

    @pytest.mark.parametrize("poison", [None, "partial", 7, ["self_ok"]])
    def test_a_non_dict_summary_fails_closed(self, poison):
        assert clears_failure_streak("partial", poison) is False


# ---------------------------------------------------------------------------
# The round trip — seeded at 78, which is the number that shipped
# ---------------------------------------------------------------------------

class TestTheSeventyEightDeepFalseStreak:
    def _record(self, monkeypatch, summary, *, hashes=None, counters=None):
        fake = _fake(monkeypatch, hashes=hashes or {_KEY: dict(_SEEDED_78)},
                     counters=counters or {})
        redis_state.record_task_incomplete(
            SAMPLER, 470.0, verdict="partial",
            verdict_reason="terminal:partial", result_summary=summary,
        )
        return fake

    def test_the_streak_is_cleared(self, monkeypatch):
        fake = self._record(monkeypatch, _PRODUCER_FAULT_SUMMARY)
        assert fake.hashes[_KEY]["consecutive_failures"] == "0"

    def test_health_stops_reading_critical(self, monkeypatch):
        """The ship, stated as the operator meets it."""
        self._record(monkeypatch, _PRODUCER_FAULT_SUMMARY)
        out = redis_state.get_task_metrics(SAMPLER)
        assert out["health"] != "critical"
        assert out["health"] == "degraded", (
            "a producer fault is not healthy either — it must land between the two"
        )

    def test_the_clearing_is_stamped_not_silent(self, monkeypatch):
        """A counter a task may reset says when, and on whose word."""
        fake = self._record(monkeypatch, _PRODUCER_FAULT_SUMMARY)
        assert fake.hashes[_KEY]["failure_streak_cleared_at"]
        assert fake.hashes[_KEY]["failure_streak_cleared_by"] == "terminal:partial"

    def test_no_success_is_counted(self, monkeypatch):
        """Clearing the streak is not a success. The two must never merge."""
        fake = self._record(monkeypatch, _PRODUCER_FAULT_SUMMARY)
        assert f"{TASK_METRICS_PREFIX}:{SAMPLER}:successes" not in fake.counters
        assert fake.counters.get(f"{TASK_METRICS_PREFIX}:{SAMPLER}:incompletes") == "1"
        assert "last_success_at" not in fake.hashes[_KEY]
        assert fake.hashes[_KEY]["last_verdict"] == "partial"

    def test_the_producer_detail_survives_into_the_record(self, monkeypatch):
        """Clearing our own red must not cost the producer's finding."""
        import json

        fake = self._record(monkeypatch, _PRODUCER_FAULT_SUMMARY)
        banked = json.loads(fake.hashes[_KEY]["last_result_summary"])
        assert banked["producer_condition"]["gauges_absent"] == ["staged:served_at"]
        assert banked["producer_condition"]["beat_terminal"] == "cancelled"
        assert banked[SELF_OK_FIELD] is True

    def test_a_sampler_run_that_did_NOT_do_its_job_leaves_the_streak_alone(
        self, monkeypatch
    ):
        """`self_ok: False` is the sampler's own fault — the streak is real."""
        fake = self._record(
            monkeypatch, dict(_PRODUCER_FAULT_SUMMARY, **{SELF_OK_FIELD: False})
        )
        assert fake.hashes[_KEY]["consecutive_failures"] == "78"


class TestUnrelatedTasksAreUntouched:
    """The other direction, and the one that makes the repair safe to land."""

    def test_an_ordinary_partial_preserves_a_real_streak(self, monkeypatch):
        key = f"{TASK_METRICS_PREFIX}:some_resumable_sweep"
        fake = _fake(monkeypatch, hashes={key: {"consecutive_failures": "6"}})
        redis_state.record_task_incomplete(
            "some_resumable_sweep", 100.0, verdict="partial",
            verdict_reason="terminal:partial",
            result_summary={"terminal": "partial", "stopped_at": "unit-40"},
        )
        assert fake.hashes[key]["consecutive_failures"] == "6"

    def test_that_task_still_reads_critical(self, monkeypatch):
        key = f"{TASK_METRICS_PREFIX}:some_resumable_sweep"
        _fake(monkeypatch, hashes={key: {
            "consecutive_failures": "6", "last_verdict": "partial",
        }}, counters={f"{TASK_METRICS_PREFIX}:some_resumable_sweep:failures": "6"})
        assert redis_state.get_task_metrics("some_resumable_sweep")["health"] == "critical"

    def test_the_interrupted_worker_path_still_preserves_its_streak(self, monkeypatch):
        """`describe_worker_shutdown` sets no `self_ok`, and must not start."""
        from app.utils.task_verdict import describe_worker_shutdown

        summary = describe_worker_shutdown(SystemExit(-241))
        assert SELF_OK_FIELD not in summary
        assert clears_failure_streak("partial", summary) is False


class TestTheSeamHoldsOnTheREALArtifact:
    """End to end on the sampler's own output, with nothing hand-written.

    Every test above feeds a summary this file composed. That proves the
    recorder and the predicate, and it would still pass if the SAMPLER stopped
    emitting `self_ok` — which is the one way this repair could silently stop
    working. So this class builds the artifact by actually running the task, and
    routes it through `verdict_for` exactly as `_tracked_run` does.
    """

    @staticmethod
    def _real_artifact(monkeypatch):
        import asyncio
        import datetime

        import app.tasks.calibration_beat_gauge_sampler as mod

        # Every required gauge except the one production is actually missing.
        stages = {
            g: 0 for g in mod.REQUIRED_DISCLOSURE_GAUGES if g != "staged:served_at"
        }
        ledger = {
            "generation": 1788734295931,
            "generated_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "complete": True,
            "payload": {"terminal": "cancelled", "stages": stages},
            "status": "ok",
        }

        async def _rl():
            return ledger, "ok"

        async def _rh():
            return {}, "ok"

        async def _pub(_envelope):
            return {"status": "stored"}

        monkeypatch.setattr(mod, "_read_ledger", _rl)
        monkeypatch.setattr(mod, "_read_history", _rh)
        monkeypatch.setattr(
            "app.services.durable_snapshots.publish_snapshot_standalone", _pub
        )
        return asyncio.run(mod.run_beat_gauge_sample())

    def test_the_real_artifact_classifies_partial_and_asserts_self_ok(self, monkeypatch):
        from app.utils.task_verdict import verdict_for

        art = self._real_artifact(monkeypatch)
        assert art["terminal"] == "partial"
        assert art[SELF_OK_FIELD] is True

        verdict = verdict_for(SAMPLER, art)
        assert verdict.verdict == "partial"
        assert verdict.authoritative is True
        assert verdict.is_green is False
        # The seam: the recorder's decision, taken on the real pair.
        assert clears_failure_streak(verdict.verdict, art) is True

    def test_the_real_artifact_takes_a_78_streak_out_of_critical(self, monkeypatch):
        """The whole ship, from `run_beat_gauge_sample` to `health`."""
        from app.utils.task_verdict import verdict_for

        art = self._real_artifact(monkeypatch)
        verdict = verdict_for(SAMPLER, art)

        _fake(monkeypatch, hashes={_KEY: dict(_SEEDED_78)})
        redis_state.record_task_incomplete(
            SAMPLER, 470.0, verdict=verdict.verdict,
            verdict_reason=verdict.reason, result_summary=art,
        )
        out = redis_state.get_task_metrics(SAMPLER)
        assert out["health"] == "degraded"
        assert out["consecutive_failures"] == "0"

    def test_a_real_SAMPLER_fault_still_reads_failed_and_never_clears(self, monkeypatch):
        """The other direction on the real object: an unreadable ledger."""
        import asyncio

        import app.tasks.calibration_beat_gauge_sampler as mod
        from app.utils.task_verdict import verdict_for

        async def _rl():
            return None, "unavailable"

        monkeypatch.setattr(mod, "_read_ledger", _rl)
        art = asyncio.run(mod.run_beat_gauge_sample())

        assert art["terminal"] == "failed"
        assert art[SELF_OK_FIELD] is False
        assert verdict_for(SAMPLER, art).verdict == "failed"
        assert clears_failure_streak("failed", art) is False


class TestNoOtherTaskOptsIn:
    def test_the_sampler_is_the_only_setter_in_the_tree(self):
        """Blast radius, asserted rather than assumed.

        The field is opt-in, so the repair is only as safe as the set of tasks
        that set it. If a second task ever does, that is a deliberate act and
        this test is where it gets reviewed.
        """
        import pathlib

        root = pathlib.Path(redis_state.__file__).resolve().parents[1]
        setters = sorted(
            p.relative_to(root).as_posix()
            for p in root.rglob("*.py")
            if f'"{SELF_OK_FIELD}"' in p.read_text() or f"'{SELF_OK_FIELD}'" in p.read_text()
        )
        assert setters == [
            "tasks/calibration_beat_gauge_sampler.py",
            "utils/task_verdict.py",
        ], f"a new opt-in appeared: {setters}"
