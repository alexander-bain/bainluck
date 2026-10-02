"""#1619 — `?debug_timing=1` says which futures statement spent the futures stage.

Production 2026-10-02 00:2xZ, `f1 champion` uncached: the futures stage read
4,464 ms with `futures_outcome_arm: budget_exceeded` (bounded at 1,000 ms) and
2,082 ms with it `merged`. One number could not say whether the name arm, the
outcome arm, or the event formatting billed to the same stage spent the rest.

Two changes, both pinned here:
* `_fetch_futures_window(..., arm_ms=)` records each statement's wall time under
  `tier1` / `split` / `outcome`, ONLY for statements that ran — an absent key is
  a statement that never started, not one that cost 0 ms (gotcha #53);
* the route marks `event_format` after the event fold + settlement reads, so
  `futures` no longer carries them.

The FakeDB sleeps a known time per statement, so attribution is checked by
which key carries the long sleep, not by an exact number.
"""

from __future__ import annotations

import asyncio
import inspect
import re

import pytest

from app.routes import events as ev
from app.routes.events import _SEARCH_FUTURES_WINDOW, _fetch_futures_window

WINDOW = _SEARCH_FUTURES_WINDOW
SLOW_S = 0.2
FAST_S = 0.01


class _Result:
    def __init__(self, rows):
        self._rows = rows

    def scalars(self):
        return self

    def unique(self):
        return self

    def all(self):
        return list(self._rows)


class _Savepoint:
    async def commit(self):
        pass

    async def rollback(self):
        pass


class QueryCanceledError(Exception):
    """Named like asyncpg's, which `_is_query_timeout` recognises by name."""


class _Row:
    def __init__(self, id: int):
        self.id = id


class FakeDB:
    """Each statement sleeps by the arm it reads; `slow` names the slow one."""

    def __init__(self, *, tier1_rows: int, slow: str, cancel: str | None = None):
        self.tier1_rows = tier1_rows
        self.slow = slow
        self.cancel = cancel

    async def execute(self, marker):
        _tag, arms = marker
        which = "outcome" if "outcome" in arms else "split" if "split" in arms else "tier1"
        await asyncio.sleep(SLOW_S if which == self.slow else FAST_S)
        if which == self.cancel:
            raise QueryCanceledError("canceling statement due to statement timeout")
        if which == "outcome":
            return _Result([_Row(1000 + i) for i in range(WINDOW)])
        return _Result([_Row(i) for i in range(self.tier1_rows)])

    async def begin_nested(self):
        return _Savepoint()


def _candidates_in(arms):
    return frozenset(arms)


def _window_query(candidate_filter):
    return ("Q", candidate_filter)


@pytest.fixture(autouse=True)
def _no_timeouts(monkeypatch):
    async def _fake(db, deadline=None, bound_ms=None):
        return None

    monkeypatch.setattr(ev, "_apply_search_statement_timeout", _fake)


async def _run(db, *, split=(), arm_ms=None):
    return await _fetch_futures_window(
        db, _window_query, _candidates_in, ["name"], "outcome", None,
        split_arms=list(split), split_report={}, arm_ms=arm_ms,
    )


async def test_a_slow_outcome_arm_is_billed_to_outcome_not_tier1():
    arm_ms: dict = {}
    _rows, state = await _run(FakeDB(tier1_rows=3, slow="outcome"), arm_ms=arm_ms)
    assert state == "merged"
    assert set(arm_ms) == {"tier1", "outcome"}
    assert arm_ms["outcome"] >= SLOW_S * 1000 * 0.9
    assert arm_ms["tier1"] < SLOW_S * 1000 * 0.75


async def test_a_slow_name_arm_is_billed_to_tier1_not_outcome():
    arm_ms: dict = {}
    await _run(FakeDB(tier1_rows=3, slow="tier1"), arm_ms=arm_ms)
    assert arm_ms["tier1"] >= SLOW_S * 1000 * 0.9
    assert arm_ms["outcome"] < SLOW_S * 1000 * 0.75


async def test_an_outcome_arm_that_blows_its_bound_still_reports_its_time():
    """The `budget_exceeded` read is the one #1619 needs explained."""
    arm_ms: dict = {}
    _rows, state = await _run(
        FakeDB(tier1_rows=3, slow="outcome", cancel="outcome"), arm_ms=arm_ms
    )
    assert state == "budget_exceeded"
    assert arm_ms["outcome"] >= SLOW_S * 1000 * 0.9


async def test_a_skipped_outcome_arm_has_no_key():
    arm_ms: dict = {}
    _rows, state = await _run(FakeDB(tier1_rows=WINDOW, slow="tier1"), arm_ms=arm_ms)
    assert state == "skipped"
    assert set(arm_ms) == {"tier1"}


async def test_the_split_statement_is_billed_to_split():
    arm_ms: dict = {}
    await _run(FakeDB(tier1_rows=3, slow="split"), split=("split",), arm_ms=arm_ms)
    assert set(arm_ms) == {"tier1", "split", "outcome"}
    assert arm_ms["split"] >= SLOW_S * 1000 * 0.9
    assert arm_ms["tier1"] < SLOW_S * 1000 * 0.75
    assert arm_ms["outcome"] < SLOW_S * 1000 * 0.75


async def test_no_arm_ms_dict_is_still_the_old_call():
    rows, state = await _run(FakeDB(tier1_rows=3, slow="outcome"))
    assert state == "merged" and len(rows) == WINDOW


_ROUTE = inspect.getsource(ev.search_events)


def test_the_route_passes_its_dict_and_serves_it_beside_the_stage_sum():
    assert "arm_ms=_futures_arm_ms" in _ROUTE
    block = _ROUTE[_ROUTE.index('"debug_timing": {**_stage_ms'):]
    block = block[: block.index("if debug_timing else {}")]
    assert '"futures_arm_ms": _futures_arm_ms' in block
    # Inside `_stage_ms` it would be summed into `total_ms` a second time.
    assert "_stage_ms[" not in block


def test_event_formatting_is_its_own_stage_before_futures():
    settle = _ROUTE.index("await attach_venue_settlement(db, events, formatted_results, now)")
    mark = _ROUTE.index('_mark("event_format")')
    futures = _ROUTE.index('_mark("futures")')
    assert settle < mark < futures
    between = _ROUTE[settle:mark]
    assert not re.search(r"\bawait\b", between.split("\n", 1)[1])


async def test_a_slow_name_arm_is_not_billed_to_split():
    arm_ms: dict = {}
    await _run(FakeDB(tier1_rows=3, slow="tier1"), split=("split",), arm_ms=arm_ms)
    assert arm_ms["tier1"] >= SLOW_S * 1000 * 0.9
    assert arm_ms["split"] < SLOW_S * 1000 * 0.75
