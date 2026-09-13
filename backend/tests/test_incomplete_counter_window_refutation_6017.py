"""A zero incomplete count beside a stamp that refutes it (#6017, check 2).

The launch scoreboard's check 2 asks whether a release preserves incoming
prices. The instrument that answers it is the per-run terminal rail, and the
rail contradicted itself on the only release anyone has measured it against.

**Production, 2026-09-13T22:50Z. Main-app release v4506 at 21:46:19Z:**

* ``poll_odds`` — ``last_incomplete_at 2026-09-13T21:46:36.070Z`` (17 s after
  the release) with ``incompletes_24h: 0``, ``incompletes_window_s: null``,
  ``incomplete_share_basis: "no incompletes in window"``.
* ``prediction_market_live`` — ``last_incomplete_at 2026-09-13T21:46:36.873Z``,
  the same second on a different worker, with ``incompletes_24h: 10`` over a
  29,065 s window.

Two rails, one process-level event, opposite readings — decided entirely by
which counter's ``SET NX EX 86400`` window happened to still be alive. A reader
grading check 2 off ``incompletes_24h`` reads "no torn-down run in 24 h" on the
task that WAS torn down.

The fix publishes the sentence and leaves the count alone: 0 is true for the
window the counter still owns, and no derivation exists to retract (which is
what separates this from :func:`_terminal_evidence_refutes_hard_kill`, whose
kill count IS derived and IS decremented). Health is untouched.
"""

from __future__ import annotations

import time

import pytest

from app.tasks import redis_state
from app.tasks.redis_state import (
    TASK_METRICS_PREFIX,
    WINDOW_COUNTER_TTL,
    _stamp_refutes_empty_incomplete_counter,
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


def _iso(epoch: float) -> str:
    from datetime import datetime, timezone

    return datetime.fromtimestamp(epoch, tz=timezone.utc).isoformat()


def _metrics(monkeypatch, task, hash_fields, counters):
    monkeypatch.setattr(
        redis_state, "get_redis_client", lambda *a, **k: _Fake({task: hash_fields}, counters)
    )
    return redis_state.get_task_metrics(task)


def _poll_odds_hash(now: float, incomplete_age_s: float = 3600.0) -> dict:
    """`poll_odds` as production served it at 22:50Z, dated relative to ``now``."""
    return {
        "last_started_at": _iso(now - 7.0),
        "last_success_at": _iso(now - 0.5),
        "last_incomplete_at": _iso(now - incomplete_age_s),
        "last_duration_ms": "7168",
        "consecutive_failures": "0",
    }


# ---------------------------------------------------------------- the helper


def test_zero_count_with_a_stamp_from_inside_the_window_is_named():
    now = 1_789_339_800.0
    note = _stamp_refutes_empty_incomplete_counter(
        {"last_incomplete_at": _iso(now - 3600.0)}, 0, now=now
    )
    assert note is not None
    # The reader must be able to tell which question the 0 answered, and how
    # old the contradicting stamp is, without a second request.
    assert "3600s old" in note
    assert "incompletes_24h=0" in note
    assert "counter's own window" in note


def test_a_nonzero_count_is_not_a_contradiction():
    now = 1_789_339_800.0
    assert (
        _stamp_refutes_empty_incomplete_counter(
            {"last_incomplete_at": _iso(now - 3600.0)}, 10, now=now
        )
        is None
    )


def test_a_stamp_older_than_the_window_the_count_names_is_not_a_contradiction():
    """24h + 1s: the count and the stamp now describe different days."""
    now = 1_789_339_800.0
    assert (
        _stamp_refutes_empty_incomplete_counter(
            {"last_incomplete_at": _iso(now - WINDOW_COUNTER_TTL - 1)}, 0, now=now
        )
        is None
    )


def test_a_stamp_exactly_at_the_window_edge_still_counts():
    """The boundary belongs to the window the counter is named for."""
    now = 1_789_339_800.0
    assert (
        _stamp_refutes_empty_incomplete_counter(
            {"last_incomplete_at": _iso(now - WINDOW_COUNTER_TTL)}, 0, now=now
        )
        is not None
    )


def test_a_task_that_has_never_recorded_an_incomplete_says_nothing():
    assert _stamp_refutes_empty_incomplete_counter({}, 0, now=1_789_339_800.0) is None
    assert (
        _stamp_refutes_empty_incomplete_counter({"last_incomplete_at": ""}, 0, now=1.0)
        is None
    )
    assert (
        _stamp_refutes_empty_incomplete_counter(
            {"last_incomplete_at": "not-a-date"}, 0, now=1.0
        )
        is None
    )


def test_a_stamp_from_the_future_beyond_clock_noise_says_nothing():
    """Sub-second ordering noise is absorbed; a stamp an hour ahead is not."""
    now = 1_789_339_800.0
    assert (
        _stamp_refutes_empty_incomplete_counter(
            {"last_incomplete_at": _iso(now + 0.4)}, 0, now=now
        )
        is not None
    )
    assert (
        _stamp_refutes_empty_incomplete_counter(
            {"last_incomplete_at": _iso(now + 3600.0)}, 0, now=now
        )
        is None
    )


def test_the_default_clock_is_wall_time_not_a_frozen_constant():
    """No `now=` argument: the caller in `get_task_metrics` passes none."""
    assert (
        _stamp_refutes_empty_incomplete_counter(
            {"last_incomplete_at": _iso(time.time() - 60)}, 0
        )
        is not None
    )
    assert (
        _stamp_refutes_empty_incomplete_counter(
            {"last_incomplete_at": _iso(time.time() - WINDOW_COUNTER_TTL - 600)}, 0
        )
        is None
    )


# ------------------------------------------------------- the served payload


def test_poll_odds_shape_publishes_the_note(monkeypatch):
    """The production specimen: prices torn down by a release, counter empty."""
    now = time.time()
    m = _metrics(
        monkeypatch,
        "poll_odds",
        _poll_odds_hash(now),
        {
            f"{TASK_METRICS_PREFIX}:poll_odds:successes": "2091",
            f"{TASK_METRICS_PREFIX}:poll_odds:failures": "33",
            f"{TASK_METRICS_PREFIX}:poll_odds:starts": "2426",
            # No `:incompletes` key at all — the window rolled after the bump.
        },
    )
    assert m["incompletes_24h"] == 0
    assert "incompletes_understated" in m
    assert "last_incomplete_at" in m["incompletes_understated"]


def test_the_count_itself_is_never_adjusted(monkeypatch):
    """Unlike the hard-kill refutation, nothing here invents a unit."""
    now = time.time()
    m = _metrics(
        monkeypatch,
        "poll_odds",
        _poll_odds_hash(now),
        {
            f"{TASK_METRICS_PREFIX}:poll_odds:successes": "2091",
            f"{TASK_METRICS_PREFIX}:poll_odds:starts": "2426",
        },
    )
    assert m["incompletes_24h"] == 0
    assert m["incomplete_share"] == 0.0


def test_prediction_market_live_shape_is_silent(monkeypatch):
    """Same event, same second, live window: nothing to explain."""
    now = time.time()
    m = _metrics(
        monkeypatch,
        "prediction_market_live",
        _poll_odds_hash(now),
        {
            f"{TASK_METRICS_PREFIX}:prediction_market_live:successes": "378",
            f"{TASK_METRICS_PREFIX}:prediction_market_live:starts": "160",
            f"{TASK_METRICS_PREFIX}:prediction_market_live:incompletes": "10",
        },
    )
    assert m["incompletes_24h"] == 10
    assert "incompletes_understated" not in m


def test_health_is_identical_whether_or_not_the_note_is_published(monkeypatch):
    """The note is a sentence, not an input. Two payloads differing ONLY in the
    stamp's age must agree on health and on every counter field."""
    now = time.time()
    counters = {
        f"{TASK_METRICS_PREFIX}:poll_odds:successes": "2091",
        f"{TASK_METRICS_PREFIX}:poll_odds:failures": "33",
        f"{TASK_METRICS_PREFIX}:poll_odds:starts": "2426",
    }
    inside = _metrics(monkeypatch, "poll_odds", _poll_odds_hash(now, 3600.0), counters)
    outside = _metrics(
        monkeypatch,
        "poll_odds",
        _poll_odds_hash(now, WINDOW_COUNTER_TTL + 600.0),
        counters,
    )
    assert "incompletes_understated" in inside
    assert "incompletes_understated" not in outside
    for field in (
        "health",
        "incompletes_24h",
        "successes_24h",
        "failures_24h",
        "starts_24h",
        "hard_kills_24h",
        "hard_kills_raw_diff",
        "incomplete_share",
    ):
        assert inside.get(field) == outside.get(field), field


@pytest.mark.parametrize("incompletes", ["0", None])
def test_an_explicit_zero_counter_reads_the_same_as_a_missing_one(
    monkeypatch, incompletes
):
    """A key holding "0" and a key that has expired are the same claim."""
    now = time.time()
    counters = {
        f"{TASK_METRICS_PREFIX}:poll_odds:successes": "2091",
        f"{TASK_METRICS_PREFIX}:poll_odds:starts": "2426",
    }
    if incompletes is not None:
        counters[f"{TASK_METRICS_PREFIX}:poll_odds:incompletes"] = incompletes
    m = _metrics(monkeypatch, "poll_odds", _poll_odds_hash(now), counters)
    assert "incompletes_understated" in m
