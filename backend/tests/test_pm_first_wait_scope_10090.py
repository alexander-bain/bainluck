"""#10090 (Root attempt71): the 1 ms first price wait belongs only to whole game
chunks on a <=25 ms game cadence, and a hold outlasting it is counted, not logged.

A global 1 ms budget was REJECTED (attempt70): on the 250 ms side loops a 20 ms
hold became a ~270 ms prop/standalone wait. Every other chunk keeps 50 ms.
"""

import inspect

import pytest

from app.tasks import polymarket_ws
from app.tasks.polymarket_ws import (
    FAST_GAME_PRICE_STATEMENT_LOCK_TIMEOUT_MS, PRICE_STATEMENT_LOCK_TIMEOUT_MS,
    _PMCatalogFlushBoundary,
)
from tests.test_pm_quote_lock_bound_10090 import LockHeld, writer_rig
from tests.test_ws_flush_cadence_10090 import _FakeTime


class RecordingLogger:
    def __init__(self):
        self.levels = []

    def __getattr__(self, level):
        return lambda *args, **kwargs: self.levels.append(level)


@pytest.mark.asyncio
@pytest.mark.parametrize("period,kind,budget", [
    (None, "game", 50), (0.25, "game", 50), (0.05, "game", 50),
    (0.025, "game", 1), (0.01, "game", 1),
    (0.025, "prop", 50), (0.025, "open", 50), (0.025, "unknown", 50),
    (0.025, "mixed", 50),
])
async def test_first_wait_matches_the_owning_loop(monkeypatch, period, kind, budget):
    clock = _FakeTime(monkeypatch, t=1000)
    r, state = writer_rig(clock)
    r.ns["catalog_boundary"] = _PMCatalogFlushBoundary(game_period=period)
    if kind == "prop":
        r.ns["non_blend_outcome_ids"].add(1)
    if kind == "open":
        r.ns["open_outcome_ids"].add(1)
    if kind == "unknown":
        r.ns["event_id_by_outcome"].pop(1)
    if kind == "mixed":
        r.ns["non_blend_outcome_ids"].add(2)
    wrote = await r.ns["write_chunk"]({1: 0.7, 2: 0.3})
    assert state.budgets[0] == f"{budget}ms"
    assert len(state.attempts) == 1
    if kind in {"prop", "unknown", "mixed"}:
        # #10090: two units (an event and a question): the held row keeps back
        # only its own unit, and the other commits in the same attempt.
        assert state.skip == [True]
        assert wrote.written_ids == (2,) and wrote.skipped_ids == {1}
        assert state.commits == [2]
        assert r.ns["price_buffer"][1] == 0.9  # still buffered, never dropped
    else:
        assert wrote is None and not state.commits
        assert r.ns["price_buffer"]


def test_the_budgets_are_the_named_constants():
    assert FAST_GAME_PRICE_STATEMENT_LOCK_TIMEOUT_MS == 1
    assert PRICE_STATEMENT_LOCK_TIMEOUT_MS == 50
    assert _PMCatalogFlushBoundary().game_price_lock_timeout_ms == 50


def test_the_consumer_builds_its_boundary_from_the_game_cadence():
    # Unwired, every run would keep 50 ms and the unit cases above still pass.
    source = "".join(inspect.getsource(polymarket_ws._run_polymarket_ws_consumer).split())
    assert "_PMCatalogFlushBoundary(game_period=game_period)" in source


@pytest.mark.asyncio
@pytest.mark.parametrize("period,logged,errors,counted", [
    (0.025, [], 0, 1),            # fast game: an ordinary hold, counted
    (0.25, ["exception"], 1, 0),  # 50 ms control: the episode's logged error
])
async def test_a_hold_outlasting_the_fast_first_wait_is_counted_not_logged(
    monkeypatch, period, logged, errors, counted,
):
    clock = _FakeTime(monkeypatch, t=1000)
    r, state = writer_rig(clock)
    r.ns["catalog_boundary"] = _PMCatalogFlushBoundary(game_period=period)
    log = r.ns["logger"] = RecordingLogger()
    assert await r.ns["write_chunk"]({1: 0.7, 2: 0.3}) is None
    assert state.nowait == [False]
    assert log.levels == logged
    assert r.ns["stats"].get("errors", 0) == errors
    assert r.ns["stats"].get("price_lock_timeouts", 0) == counted
    # Either way the rows are known-held and due: the next try is a NOWAIT probe.
    assert set(r.ns["lock_retry_until"]) == {1, 2}
    assert max(r.ns["lock_retry_until"].values()) <= clock.t
    assert {1, 2} <= set(r.ns["price_buffer"]), "a refused chunk stays buffered"
    state.held = False
    assert (await r.ns["write_chunk"]({1: 0.9, 2: 0.3})).written_ids == (1, 2)
    assert state.nowait == [False, True]
    assert not r.ns["lock_retry_until"]


@pytest.mark.asyncio
async def test_a_rerank_lock_timeout_on_a_fast_game_chunk_is_still_logged(monkeypatch):
    # Only the price statement's own timeout is the ordinary short-try case.
    clock = _FakeTime(monkeypatch, t=1000)
    r, state = writer_rig(clock)
    r.ns["catalog_boundary"] = _PMCatalogFlushBoundary(game_period=0.025)
    log = r.ns["logger"] = RecordingLogger()
    state.held = False
    state.rank_error = LockHeld()
    assert await r.ns["write_chunk"]({1: 0.7, 2: 0.3}) is None
    assert state.budgets == ["1ms", "500ms"]
    assert log.levels == ["exception"]
    assert r.ns["stats"]["errors"] == 1
    assert not r.ns["stats"].get("price_lock_timeouts")

