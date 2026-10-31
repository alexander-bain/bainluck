"""#10090 — adjacent observed preview-cohort transactions share one.

`_pm_lock_isolated_chunks` gives each observed live game its own transaction;
at 67 live games (2026-10-31 12:45Z) a game flush walked ~30 of them, ~8 round
trips each. `_pm_pack_preview_cohort_chunks` joins neighbours whole, never
splits a unit, and leaves lock-retried and open legs alone.
"""

import inspect

import pytest

from app.tasks import polymarket_ws as pm
from app.tasks.polymarket_ws import (
    _pm_lock_isolated_chunks,
    _pm_pack_preview_cohort_chunks,
)


@pytest.fixture(autouse=True)
def _pack_on(monkeypatch):
    monkeypatch.setattr(pm, "PM_PACK_PREVIEW_COHORTS", True)


# Events 1-4, two legs each (one binary question per event).
EVENT = {11: 1, 12: 1, 21: 2, 22: 2, 31: 3, 32: 3, 41: 4, 42: 4, 91: 9, 92: 9}
MARKET = {11: 101, 12: 101, 21: 102, 22: 102, 31: 103, 32: 103,
          41: 104, 42: 104, 91: 109, 92: 109}
COMPLEMENT = {11: 12, 12: 11, 21: 22, 22: 21, 31: 32, 32: 31,
              41: 42, 42: 41, 91: 92, 92: 91}


def pack(chunks, events, retry=None, open_ids=(), rows=500):
    return _pm_pack_preview_cohort_chunks(
        chunks, set(events), EVENT, retry or {}, set(open_ids), rows,
    )


def test_adjacent_cohorts_share_one_transaction_in_row_order():
    chunks = [[11, 12], [21, 22], [31, 32]]
    assert pack(chunks, {1, 2, 3}) == [[11, 12, 21, 22, 31, 32]]


def test_a_pack_never_passes_the_row_cap_and_never_splits_a_chunk():
    chunks = [[11, 12], [21, 22], [31, 32], [41, 42]]
    assert pack(chunks, {1, 2, 3, 4}, rows=5) == [
        [11, 12, 21, 22], [31, 32, 41, 42],
    ]
    # A chunk already past the cap stays whole, alone.
    assert pack([[11, 12], [21, 22, 31, 32]], {1, 2, 3}, rows=3) == [
        [11, 12], [21, 22, 31, 32],
    ]


def test_a_lock_retried_leg_keeps_its_chunk_alone_and_breaks_adjacency():
    chunks = [[11, 12], [21, 22], [31, 32]]
    # A cooldown entry (any value, even 0) makes the chunk probe NOWAIT or
    # skip outright, which would refuse every event joined to it.
    assert pack(chunks, {1, 2, 3}, retry={21: 0}) == [[11, 12], [21, 22], [31, 32]]


def test_unselected_events_and_open_legs_are_never_joined():
    chunks = [[11, 12], [91, 92], [21, 22], [31, 32]]
    assert pack(chunks, {1, 2, 3}) == [[11, 12], [91, 92], [21, 22, 31, 32]]
    assert pack(chunks, {1, 2, 3, 9}, open_ids={91}) == [
        [11, 12], [91, 92], [21, 22, 31, 32],
    ]


def test_switch_off_is_the_isolated_chunks_exactly(monkeypatch):
    monkeypatch.setattr(pm, "PM_PACK_PREVIEW_COHORTS", False)
    chunks = [[11, 12], [21, 22], [31, 32]]
    assert pack(chunks, {1, 2, 3}) is chunks
    monkeypatch.setattr(pm, "PM_PACK_PREVIEW_COHORTS", True)
    assert pack(chunks, set()) is chunks


@pytest.mark.parametrize("raw, expected", [
    (None, True), ("", True), ("1", True), ("0", False), ("off", False),
    (" FALSE ", False), ("no", False),
])
def test_env_switch(monkeypatch, raw, expected):
    if raw is None:
        monkeypatch.delenv("PM_PACK_PREVIEW_COHORTS", raising=False)
    else:
        monkeypatch.setenv("PM_PACK_PREVIEW_COHORTS", raw)
    assert pm._pack_preview_cohorts_env() is expected


def test_after_isolation_the_observed_games_collapse_but_the_remainder_and_retry_stay():
    # One planned chunk holding every event; 2 and 3 observed-unchanged,
    # 4 changed (goes first), 1 a lock retry, 9 an ordinary remainder.
    planned = [[11, 12, 21, 22, 31, 32, 41, 42, 91, 92]]
    retry_events = {1}
    isolated = {1, 2, 3}
    changed = {4}
    isolated_chunks = _pm_lock_isolated_chunks(
        planned, isolated, EVENT, MARKET, COMPLEMENT, 500, first_events=changed,
    )
    assert len(isolated_chunks) == 5  # remainder + four single-event chunks
    packed = pack(
        isolated_chunks, (isolated | changed) - retry_events, retry={11: 0, 12: 0},
    )
    flat = [oid for chunk in packed for oid in chunk]
    assert flat == [oid for chunk in isolated_chunks for oid in chunk]
    assert [11, 12] in packed  # the retry is still alone
    assert [91, 92] in packed  # the remainder keeps its own transaction
    assert len(packed) < len(isolated_chunks)
    for chunk in packed:
        events = {EVENT[oid] for oid in chunk}
        assert not (events & retry_events) or events == retry_events


def test_the_game_flush_packs_after_isolating():
    source = inspect.getsource(pm.polymarket_ws_consumer) if hasattr(
        pm, "polymarket_ws_consumer") else inspect.getsource(pm)
    isolate = source.index("first_events=changed_events,")
    packed = source.index("_pm_pack_preview_cohort_chunks(\n", isolate)
    assert source.index("stats[\"open_contract_flush_deferred\"]", isolate) > packed
    assert "(isolated_events | changed_events) - lock_retry_events" in source[packed:packed + 300]
