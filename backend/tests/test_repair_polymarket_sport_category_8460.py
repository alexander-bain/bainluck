"""#8460 — the resolved drain reaches rows that carry their event id only in ``group_id``.

PILLAR: TRUTH / FORMATTING. SHIP: a settled ITF match stops reading TABLE
TENNIS while its sibling in the same Polymarket event reads TENNIS
(``/futures/59524708`` vs ``/futures/59522756``, 2026-09-24).

The #2526 drain finished cleanly and could not see these rows: its population
required ``market_metadata->>'polymarket_event_id' IS NOT NULL``, and 75,004
resolved ``table_tennis`` rows have no such key. Each carries the event in its
``group_id`` (``polymarket:905447``). So the ``not_open`` scope keys the event on
``COALESCE(metadata id, group_id's numeric tail)`` in EVERY statement that names
the population, and the ``open`` scope — the path the Q495–Q497 certs graded,
with zero such rows — renders byte-for-byte as before.

Production proof of the expression itself (2026-09-24 ~21:25Z, db-query): both
specimen rows key to ``905447``; ``polymarket:abc``, ``kalshi:123`` and
``polymarket:123:x`` key to NULL. These tests guard the SQL the rail renders.
"""

from __future__ import annotations

import pytest

from app.tasks import repair_polymarket_sport_category as rail
from tests.test_repair_polymarket_sport_category_q496 import (
    _Row,
    _Session,
    _SETKA,
    _TENNIS,
    _Ts,
    _venue,
)

_GROUP_KEY = (
    "COALESCE(fm.market_metadata->>'polymarket_event_id', "
    "substring(fm.group_id from '^polymarket:([0-9]+)$'))"
)
_BARE_KEY = "fm.market_metadata->>'polymarket_event_id'"


@pytest.fixture
def fast(monkeypatch):
    monkeypatch.setattr(rail, "VENUE_PAUSE", 0)


def _population(s: _Session) -> list[str]:
    """Every statement that names the population: SELECTs and the UPDATE."""
    return [
        sql
        for sql, _p in s.statements
        if "FROM futures_markets fm" in sql or sql.startswith("UPDATE futures_markets fm")
    ]


def _specimen_session() -> _Session:
    # /futures/59524708: resolved, no metadata id, group_id polymarket:905447.
    return _Session(
        targets=[
            _Row("905447", _Ts("2026-08-10T12:00:00+00:00"), 59524708, markets=1,
                 market_ids=[59524708]),
        ],
        remaining=11764,
        update_rowcount=1,
    )


def test_each_scope_has_an_event_key_and_only_not_open_reads_group_id():
    assert set(rail.EVENT_ID_SQL) == set(rail.STATUS_SCOPE_SQL)
    assert rail.EVENT_ID_SQL["open"] == _BARE_KEY
    assert rail.EVENT_ID_SQL["not_open"] == _GROUP_KEY


async def test_not_open_keys_every_population_statement_on_the_group_fallback(
    fast, monkeypatch
):
    s = _specimen_session()
    _venue(monkeypatch, {"905447": _TENNIS})

    out = await rail.repair(s, apply=True, status_scope="not_open")

    assert len(s.writes) == 1, "the write never ran — the assertions below are vacuous"
    statements = _population(s)
    # page SELECT, UPDATE, remaining count
    assert len(statements) == 3, statements
    for sql in statements:
        assert _GROUP_KEY in sql, sql
    assert f"{_GROUP_KEY} AS event_id" in s.target_sql
    assert f"{_GROUP_KEY} IS NOT NULL" in s.target_sql
    # The write's compare-and-set matches on the SAME key the page grouped on —
    # on the bare key it would match no row of this specimen and write nothing.
    sql, params = s.writes[0]
    assert f"{_GROUP_KEY} = :eid" in sql, sql
    assert params["eid"] == "905447"
    assert params["ids"] == [59524708]
    assert out["counts"]["changed"] == 1
    assert out["counts"]["markets_written"] == 1


async def test_the_specimen_banks_an_undo_receipt_for_the_row(fast, monkeypatch):
    s = _specimen_session()
    _venue(monkeypatch, {"905447": _TENNIS})
    out = await rail.repair(s, apply=True, status_scope="not_open")
    assert len(s.receipts) == 1, "no receipt staged — the write would be irreversible"
    assert len(out["receipts"]) == 1
    receipt = out["receipts"][0]
    assert receipt["event_id"] == "905447"
    assert receipt["restore_command"]


async def test_a_table_tennis_verdict_still_writes_nothing(fast, monkeypatch):
    """The control: a group-keyed Setka event is re-asked like any other and the
    venue keeps it where it is. The fallback widens who is ASKED, never what
    the answer is."""
    s = _Session(
        targets=[_Row("945534", _Ts("2026-08-11T12:00:00+00:00"), 70, markets=6,
                      market_ids=[70, 71, 72, 73, 74, 75])],
        remaining=11764,
    )
    _venue(monkeypatch, {"945534": _SETKA})
    out = await rail.repair(s, apply=True, status_scope="not_open")
    assert out["counts"]["unchanged"] == 1
    assert s.writes == []


async def test_the_not_open_census_counts_the_same_population(monkeypatch):
    s = _Session(remaining=0)
    out = await rail.census(s, status_scope="not_open")
    assert out["measured"] is True
    statements = _population(s)
    assert len(statements) == 2, statements
    for sql in statements:
        assert f"count(DISTINCT {_GROUP_KEY})" in sql, sql
        assert f"{_GROUP_KEY} IS NOT NULL" in sql, sql


async def test_the_open_scope_never_reads_group_id(fast, monkeypatch):
    """The graded path is untouched: no open-scope statement names group_id."""
    s = _Session(
        targets=[_Row("924377", _Ts("2026-08-30T18:00:00+00:00"), 11, markets=3,
                      market_ids=[11, 12, 13])],
        remaining=40,
        update_rowcount=3,
    )
    _venue(monkeypatch, {"924377": _TENNIS})
    await rail.repair(s, apply=True)
    c = _Session(remaining=0)
    await rail.census(c)

    statements = _population(s) + _population(c)
    assert len(s.writes) == 1 and len(statements) == 5, statements
    for sql in statements:
        assert "group_id" not in sql, sql
        assert "COALESCE" not in sql, sql
