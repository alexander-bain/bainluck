"""#10663 — the Polymarket slate's link read keeps one row per linked market.

The read selected five columns per OUTCOME and built ``condition_to_ids`` from
three of them; nothing read that map. It now selects ``(market_id,
linked_event_id)`` with DISTINCT. Equivalence needs three things, held here
without a database (the real-Postgres arm is
``tests/integration/test_ws_slate_age_floor_pg_837.py``):

* the outcome join and every filter are byte-for-byte the parent's, on both the
  full read and the stored live/suspended read;
* the two columns are the market id and its event id, and nothing else — an
  event id belongs to its market row, so DISTINCT removes only outcome repeats;
* the slate fixtures, written as the parent's outcome-level rows, are answered
  in the shipped read's shape (``answer_slate_link_read``), so every consumer
  test that feeds them still exercises the shipped loop.
"""

import pytest
from sqlalchemy.dialects import postgresql

from tests._pm_slate_link_read_10663 import (
    answer_slate_link_read,
    is_slate_link_read,
    parent_slate_link_stmt,
    shipped_slate_link_stmt,
)


def _from_onward(stmt):
    sql = str(stmt.compile(dialect=postgresql.dialect()))
    head, sep, tail = sql.partition("\nFROM ")
    assert sep, sql
    return head, tail


def _columns(stmt):
    return [
        (getattr(getattr(getattr(c, "element", c), "table", None), "name", None), c.name)
        for c in stmt.selected_columns
    ]


@pytest.mark.parametrize("stored_live_only", [False, True])
async def test_the_link_read_keeps_the_parent_join_and_filters(stored_live_only):
    shipped = await shipped_slate_link_stmt(stored_live_only=stored_live_only)
    parent = parent_slate_link_stmt(stored_live_only=stored_live_only)

    head, tail = _from_onward(shipped)
    _parent_head, parent_tail = _from_onward(parent)
    # FROM futures_outcomes JOIN futures_markets ... JOIN events ... WHERE ...
    assert tail == parent_tail
    assert tail.startswith("futures_outcomes JOIN futures_markets ON ")
    assert head.startswith("SELECT DISTINCT ")
    assert shipped._distinct is True
    assert _columns(shipped) == [
        ("futures_outcomes", "market_id"),
        ("futures_markets", "linked_event_id"),
    ]


def test_parent_fixtures_answer_the_parent_read_unchanged():
    stored = [
        (10, 1, "0xa", "0xa", 100),
        (11, 1, "0xa_side1", "0xa", 100),
        (12, 1, "", "0xa", 100),
        (20, 2, "0xb", "0xb", 200),
    ]
    parent = parent_slate_link_stmt()
    assert is_slate_link_read(parent)
    assert answer_slate_link_read(parent, stored) == stored  # parent: untouched


async def test_parent_fixtures_answer_the_shipped_read_distinct():
    stored = [
        (10, 1, "0xa", "0xa", 100),
        (11, 1, "0xa_side1", "0xa", 100),
        (12, 1, "", "0xa", 100),
        (20, 2, "0xb", "0xb", 200),
    ]
    shipped = await shipped_slate_link_stmt()
    assert answer_slate_link_read(shipped, stored) == [(1, 100), (2, 200)]
