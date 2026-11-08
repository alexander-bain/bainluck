"""#4437: the dropdown proves "open now" for a bounded ordered slice, not every candidate.

Measured on "we" (Nov 7, production `EXPLAIN ANALYZE`): the futures candidate statement ran
the open-now anti-joins (game already played, twins, group siblings) on all 1,627 candidates
before its `LIMIT 20`: 280 of 724 ms. The candidates are now ordered under the two cheap
filters, the first 200 go through the full statement, and the original statement runs only
when that slice was full and fewer than 20 survived. Same rows, by construction.
"""

from __future__ import annotations

import inspect

import pytest
from sqlalchemy.dialects import postgresql

from app.routes import events


class _Res:
    def __init__(self, rows):
        self.rows = rows

    def scalars(self):
        return self

    def unique(self):
        return self

    def all(self):
        return list(self.rows)


class _DB:
    def __init__(self, slice_ids, sliced_rows, full_rows):
        self.answers = [slice_ids, sliced_rows, full_rows]
        self.statements = []

    async def execute(self, stmt):
        self.statements.append(stmt)
        return _Res(self.answers[len(self.statements) - 1])


def _sql(stmt):
    return str(stmt.compile(dialect=postgresql.dialect()))


SLICE = events._TYPEAHEAD_OPEN_NOW_SLICE
POOL = events._TYPEAHEAD_FUTURES_POOL


def _queries():
    from sqlalchemy import select

    from app.models import FuturesMarket

    full = select(FuturesMarket).where(FuturesMarket.status == "open").limit(POOL)
    sl = select(FuturesMarket.id).where(FuturesMarket.status == "open").limit(SLICE)
    return sl, full


@pytest.mark.asyncio
async def test_a_short_candidate_list_is_answered_by_the_slice_alone():
    sl, full = _queries()
    db = _DB(list(range(1, 51)), ["r"] * 7, None)
    res = await events._typeahead_sliced_futures(db, sl, full)
    assert res.scalars().unique().all() == ["r"] * 7
    assert len(db.statements) == 2  # slice + sliced full: the original never runs
    assert "ANY" in _sql(db.statements[1]).upper()  # the full statement is held to the slice


@pytest.mark.asyncio
async def test_a_full_slice_that_fills_the_pool_is_the_same_top_rows():
    sl, full = _queries()
    db = _DB(list(range(SLICE)), [f"m{i}" for i in range(POOL)], None)
    res = await events._typeahead_sliced_futures(db, sl, full)
    assert res.scalars().unique().all() == [f"m{i}" for i in range(POOL)]
    assert len(db.statements) == 2


@pytest.mark.asyncio
async def test_a_full_slice_that_cannot_fill_the_pool_asks_the_original_question():
    sl, full = _queries()
    db = _DB(list(range(SLICE)), ["m"] * (POOL - 1), ["orig"] * POOL)
    res = await events._typeahead_sliced_futures(db, sl, full)
    assert res.scalars().unique().all() == ["orig"] * POOL
    assert len(db.statements) == 3 and db.statements[2] is full


def test_the_slice_carries_the_cheap_filters_and_the_full_statement_keeps_all_three():
    src = inspect.getsource(events.typeahead_search)
    assert "_ta_cheap_open_now = _ta_open_now[:2]" in src
    assert ".where(_ta_candidate_filter, *_ta_cheap_open_now)" in src
    assert ".limit(_TYPEAHEAD_OPEN_NOW_SLICE)" in src
    # the statement whose rows are served still applies every open-now filter
    assert "_ta_candidate_filter,\n            *_ta_open_now,\n        )\n        .order_by(*_ta_futures_order)" in src
    assert SLICE >= 10 * POOL
