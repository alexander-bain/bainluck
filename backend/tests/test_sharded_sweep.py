"""CAL-P991 — the sharded sweep must tell a throttled CALLER from an oversized RANGE.

The defect these guard: ``POST /api/admin/db-query`` refuses with
``Rate limit exceeded: 300/minute``, which ``dbq_probe`` records as
``status: refused``. Every fold's private copy of the sweep treated any not-ok
answer as "this range is too big" and bisected. Bisecting a throttled range
DOUBLES the request rate against the limit that just refused, so one throttled
range walks to the bisect floor and stamps clean ranges IRREDUCIBLE — and an
IRREDUCIBLE range taints the run (gotcha #53) while the fold still prints a
table. The failure is therefore silent-by-construction: the output looks like a
census, and it is a census of a population the sweep never read.

The ORDERING test is the load-bearing one. A throttle handled after the split
arm still produces rows, so a test that only asserts "the fold finished" passes
under both arms and proves nothing (the both-arms-green trap). These assert the
request LOG — which ranges were asked for, in which order — because that is the
only observable that differs.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from sharded_sweep import (  # noqa: E402
    THROTTLE_BACKOFF_S,
    SweepRefused,
    is_sql_refusal,
    is_throttle,
    sweep,
)

TMPL = "SELECT {lo} AS lo, {hi} AS hi"


class Recorder:
    """A fake db-query rail that records every range it was asked for."""

    def __init__(self, script):
        self.script = script          # (lo, hi) -> list of responses to serve
        self.asked: list[tuple[int, int]] = []
        self.slept: list[float] = []

    def __call__(self, sql: str, timeout_ms: int) -> dict:
        lo = int(sql.split()[1])
        hi = int(sql.split()[4])
        self.asked.append((lo, hi))
        queue = self.script.get((lo, hi))
        if queue is None:
            return {"status": "ok", "rows": [[lo]], "duration_ms": 1}
        return queue.pop(0) if len(queue) > 1 else queue[0]

    def sleep(self, seconds: float) -> None:
        self.slept.append(seconds)


def _sweep(rec, lo=0, hi=100, chunk=100, floor=10):
    rows: list = []
    irreducible: list = []
    sweep(TMPL, lo, hi, chunk, 10_000, rows, irreducible,
          runner=rec, floor=floor, sleep=rec.sleep, log=lambda _m: None)
    return rows, irreducible


THROTTLE = {"status": "refused", "reason": "Rate limit exceeded: 300/minute"}
TIMEOUT = {"status": "failed", "reason": "statement_timeout"}
OK = {"status": "ok", "rows": [["x"]], "duration_ms": 5}


def test_is_throttle_recognises_the_endpoints_own_wording():
    assert is_throttle("Rate limit exceeded: 300/minute")
    assert is_throttle("429 Too Many Requests")
    assert not is_throttle("statement_timeout")
    assert not is_throttle(None)


def test_throttled_range_is_re_asked_unchanged_and_never_split():
    """THE ORDERING CONTRACT. A throttle must not reach the split arm."""
    rec = Recorder({(0, 100): [THROTTLE, OK]})
    rows, irreducible = _sweep(rec)

    assert rec.asked == [(0, 100), (0, 100)], (
        "a throttled range must be re-asked at its ORIGINAL bounds; any other "
        "range in this log means the throttle fell through to the split arm"
    )
    assert irreducible == []
    assert rows == [["x"]]
    assert rec.slept == [THROTTLE_BACKOFF_S[0]]


def test_oversized_range_is_still_split():
    """The control: the arm the throttle branch must not have disabled."""
    rec = Recorder({(0, 100): [TIMEOUT]})
    rows, irreducible = _sweep(rec)

    assert (0, 50) in rec.asked and (50, 100) in rec.asked
    assert irreducible == []
    assert len(rows) == 2


def test_throttle_that_survives_every_backoff_is_recorded_not_dropped():
    rec = Recorder({(0, 100): [THROTTLE]})
    rows, irreducible = _sweep(rec)

    assert rows == []
    assert irreducible == [[0, 100, "throttled"]]
    assert rec.slept == list(THROTTLE_BACKOFF_S), (
        "every backoff step must be spent before a range is written off"
    )
    # Asked once up front plus once per backoff — and never at other bounds.
    assert rec.asked == [(0, 100)] * (1 + len(THROTTLE_BACKOFF_S))


def test_timeout_at_the_floor_is_irreducible_and_taints_the_run():
    rec = Recorder({(0, 10): [TIMEOUT]})
    rows, irreducible = _sweep(rec, lo=0, hi=10, chunk=10, floor=10)

    assert rows == []
    assert irreducible == [[0, 10, "statement_timeout"]]


def test_truncated_answer_is_treated_as_oversized_not_as_data():
    """A truncated aggregate is a WRONG answer, not a short one (1000-row cap)."""
    truncated = {"status": "ok", "rows": [["x"]], "truncated": True}
    rec = Recorder({(0, 100): [truncated]})
    rows, irreducible = _sweep(rec)

    assert (0, 50) in rec.asked and (50, 100) in rec.asked
    assert ["x"] not in rows, "the truncated page must not be banked as rows"
    assert len(rows) == 2


def test_a_throttle_after_a_split_is_still_re_asked_at_the_split_bounds():
    """Composition: the two repairs must not cancel each other out."""
    rec = Recorder({(0, 100): [TIMEOUT], (0, 50): [THROTTLE, OK]})
    rows, irreducible = _sweep(rec)

    assert rec.asked.count((0, 50)) == 2
    assert (0, 25) not in rec.asked, "the throttled HALF must not be split again"
    assert irreducible == []


REFUSED = {"status": "refused", "reason": "Only SELECT queries are allowed"}


def test_a_read_guard_refusal_stops_the_sweep_instead_of_bisecting():
    """The statement is wrong at every width, so no split can repair it.

    Measured 2026-09-03: one apostrophe in a ``--`` comment produced 100+
    IRREDUCIBLE ranges and a printed table. Aborting is the only honest answer.
    """
    rec = Recorder({(0, 100): [REFUSED]})
    with pytest.raises(SweepRefused, match="Only SELECT"):
        _sweep(rec)
    assert rec.asked == [(0, 100)], "it must not have split even once"


def test_a_throttle_is_not_mistaken_for_a_guard_refusal():
    """Ordering control: the recorder labels a 429 ``refused`` too."""
    assert is_sql_refusal("Only SELECT queries are allowed")
    assert not is_sql_refusal("Rate limit exceeded: 300/minute")
    assert not is_sql_refusal("statement_timeout")

    rec = Recorder({(0, 100): [THROTTLE, OK]})
    rows, irreducible = _sweep(rec)
    assert rows == [["x"]] and irreducible == []


def test_a_statement_timeout_is_not_a_refusal_and_still_splits():
    rec = Recorder({(0, 100): [TIMEOUT]})
    rows, _ = _sweep(rec)
    assert len(rows) == 2


@pytest.mark.parametrize("wait", THROTTLE_BACKOFF_S)
def test_backoff_schedule_is_monotone_and_clears_the_window(wait):
    assert wait > 0
    assert THROTTLE_BACKOFF_S == tuple(sorted(THROTTLE_BACKOFF_S))
    assert max(THROTTLE_BACKOFF_S) > 60, (
        "the endpoint's window is a minute; a schedule that never clears one "
        "cannot outlast a sustained throttle"
    )
