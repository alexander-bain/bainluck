"""#4437: the /search futures window proves "open now" for an ordered slice, not every candidate.

THE SHIP. A two-letter search ("we") made the futures window run the correlated
`_futures_game_already_played()` anti-joins on every candidate before its LIMIT:
1,024 candidates proven open to keep 60 (Nov 7, production `EXPLAIN ANALYZE`:
1.6 s of sibling probes plus the outer copy, under load). The window now takes
the top `_SEARCH_OPEN_NOW_SLICE` ids in its own order with the two cheap filters,
applies the full predicate to those alone, and falls back to the unsliced
statement when too few survive — so the page is the same page.
"""

import inspect

import pytest

from app.routes import events as events_mod
from app.routes.events import _SEARCH_OPEN_NOW_SLICE, _search_sliced_window_rows


class _Result:
    def __init__(self, rows):
        self._rows = rows

    def scalars(self):
        return self

    def unique(self):
        return self

    def all(self):
        return list(self._rows)


class _DB:
    """Answers by statement identity: the slice, the sliced window, the full one."""

    def __init__(self, slice_ids, sliced_rows, full_rows):
        self.answers = {}
        self.slice_ids, self.sliced_rows, self.full_rows = slice_ids, sliced_rows, full_rows
        self.ran = []

    async def execute(self, stmt):
        self.ran.append(stmt)
        if stmt == "SLICE":
            return _Result(self.slice_ids)
        if stmt == "SLICED":
            return _Result(self.sliced_rows)
        if stmt == "FULL":
            return _Result(self.full_rows)
        raise AssertionError(stmt)


def _over(ids_seen):
    def over_ids(ids):
        ids_seen.append(list(ids))
        return "SLICED"

    return over_ids


@pytest.mark.asyncio
async def test_a_short_slice_is_the_whole_candidate_set_so_no_fallback():
    seen = []
    db = _DB(list(range(37)), ["r"] * 12, ["full"] * 60)
    rows = await _search_sliced_window_rows(db, "FULL", "SLICE", _over(seen), 60)
    assert rows == ["r"] * 12
    assert db.ran == ["SLICE", "SLICED"]
    assert seen == [list(range(37))]


@pytest.mark.asyncio
async def test_a_full_slice_with_enough_survivors_is_the_page():
    db = _DB(list(range(_SEARCH_OPEN_NOW_SLICE)), ["r"] * 60, ["full"] * 60)
    rows = await _search_sliced_window_rows(db, "FULL", "SLICE", _over([]), 60)
    assert rows == ["r"] * 60
    assert "FULL" not in db.ran


@pytest.mark.asyncio
async def test_a_full_slice_with_too_few_survivors_falls_back_to_the_full_statement():
    db = _DB(list(range(_SEARCH_OPEN_NOW_SLICE)), ["r"] * 59, ["full"] * 60)
    rows = await _search_sliced_window_rows(db, "FULL", "SLICE", _over([]), 60)
    assert rows == ["full"] * 60
    assert db.ran == ["SLICE", "SLICED", "FULL"]


@pytest.mark.asyncio
async def test_no_slice_is_the_old_single_statement():
    db = _DB([], [], ["full"] * 3)
    rows = await _search_sliced_window_rows(db, "FULL", None, _over([]), 60)
    assert rows == ["full"] * 3
    assert db.ran == ["FULL"]


def test_the_slice_is_well_above_the_widest_window_it_feeds():
    assert _SEARCH_OPEN_NOW_SLICE > events_mod._SEARCH_FUTURES_WINDOW + events_mod._SEARCH_FUTURES_REFILL


def test_the_route_builds_the_slice_from_the_window_builder_with_the_cheap_filters():
    src = inspect.getsource(events_mod.search_events)
    body = src[src.index("def _futures_slice_query(arms):"):]
    body = body[: body.index("futures_query = _futures_window_query(")]
    assert "_futures_candidates_in(arms, open_now=_futures_cheap_open_now)" in body
    assert "open_now=_futures_cheap_open_now," in body
    assert ".with_only_columns(FuturesMarket.id)" in body
    assert ".limit(_SEARCH_OPEN_NOW_SLICE)" in body
    assert "_futures_cheap_open_now = _futures_open_now[:2]" in src
    assert "slice_query=_futures_slice_query," in src


def test_the_tier1_window_replaces_its_candidate_filter_with_the_slice_ids():
    """ANDing the candidate filter back would re-prove every candidate: its arms
    carry the full predicate too (measured: 2,181 ms ANDed vs 2,292 unsliced)."""
    src = inspect.getsource(events_mod._fetch_futures_window)
    assert "await _search_sliced_window_rows(" in src
    assert "lambda ids: window_query(" in src
    assert "FuturesMarket.id == any_(literal(ids, ARRAY(Integer)))" in src
