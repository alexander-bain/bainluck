"""#13610 — Replace disjunctive ``event_id IN (SELECT events.id ...)`` with PK-keyed LEFT JOIN.

WHY THIS FILE EXISTS.

On PostgreSQL, `_suggestion_movers_market_conditions()` emitted:

    (futures_markets.event_id IS NULL
     OR futures_markets.event_id IN (SELECT events.id FROM events JOIN sports ...))

When all historical tier-1/2 rows in `events` exceed Postgres's hash-table
budget (`hash_mem_multiplier * work_mem`), Postgres falls back to an unhashed
`SubPlan 1`, scanning `events` and spilling temp blocks (`15-42 s` H12 timeouts
on production `/api/events/search-suggestions`). Replacing correlated `IN` with
correlated `EXISTS` still inflated the subquery cost estimate and flipped the
outer query to a `Parallel Seq Scan on futures_outcomes`.

A PK-keyed 1-to-0..1 `LEFT OUTER JOIN events` -> `LEFT OUTER JOIN sports` inside
`market_pool_subquery` (and in the legacy rollback arm) avoids both cliffs while
preserving identical eligibility and `LIMIT` pool cardinality.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.dialects import postgresql
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import Session


@compiles(JSONB, "sqlite")
def _jsonb_on_sqlite(type_, compiler, **kw):  # pragma: no cover - DDL shim
    return "JSON"


@compiles(ARRAY, "sqlite")
def _array_on_sqlite(type_, compiler, **kw):  # pragma: no cover - DDL shim
    return "JSON"


from app.models.models import (  # noqa: E402
    Base,
    Event,
    FuturesMarket,
    FuturesOutcome,
    Sport,
)
from app.routes import events as events_routes  # noqa: E402
from app.routes.events import _build_suggestion_movers_query  # noqa: E402
from app.utils.movement_pool import market_pool_subquery  # noqa: E402

BOTH_ARMS = pytest.mark.parametrize("pooled", [True, False], ids=["pooled", "legacy"])
TEST_POOL = 6


def _compile_pg(stmt) -> str:
    return " ".join(
        str(
            stmt.compile(
                dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}
            )
        ).split()
    )


@pytest.fixture()
def engine():
    eng = create_engine("sqlite://")
    Base.metadata.create_all(
        eng,
        tables=[
            FuturesMarket.__table__,
            FuturesOutcome.__table__,
            Event.__table__,
            Sport.__table__,
        ],
    )
    return eng


def _sport(session: Session, sid: int, key: str) -> int:
    session.add(Sport(id=sid, key=key, name=key))
    return sid


def _event(session: Session, eid: int, *, sport_id: int) -> int:
    session.add(
        Event(
            id=eid,
            sport_id=sport_id,
            home_team_name=f"Home {eid}",
            away_team_name=f"Away {eid}",
            commence_time=datetime.now(timezone.utc) - timedelta(hours=1),
        )
    )
    return eid


def _add_market_outcome(
    session: Session,
    oid: int,
    *,
    change: float,
    event_id: int | None = None,
    shape: str | None = "field",
) -> int:
    session.add(
        FuturesMarket(
            id=oid,
            source="kalshi",
            external_id=f"MKT-{oid}",
            name=f"market {oid}",
            status="open",
            market_type=shape,
            event_id=event_id,
            max_movement_24h=abs(change),
        )
    )
    session.add(
        FuturesOutcome(
            id=oid,
            market_id=oid,
            external_id=f"OUT-{oid}",
            name=f"Entity {oid}",
            current_probability=0.5,
            probability_change_24h=change,
        )
    )
    return oid


def _run(session: Session, *, pooled: bool):
    return (
        session.execute(_build_suggestion_movers_query(pooled=pooled))
        .unique()
        .scalars()
        .all()
    )


# ---------------------------------------------------------------------------
# 1 — SQL shape guarantees (fail before the fix)
# ---------------------------------------------------------------------------


@BOTH_ARMS
def test_compiled_sql_uses_left_outer_join_instead_of_event_id_subquery(pooled: bool):
    sql = _compile_pg(_build_suggestion_movers_query(pooled=pooled))
    assert "event_id IN (SELECT events.id" not in sql
    assert "LEFT OUTER JOIN events ON events.id = futures_markets.event_id" in sql
    assert "LEFT OUTER JOIN sports ON sports.id = events.sport_id" in sql
    assert "futures_markets.event_id IS NULL OR sports.key IN" in sql


def test_market_pool_subquery_without_outerjoins_emits_zero_joins():
    sql = _compile_pg(market_pool_subquery(pool_size=7, statuses=("open", "active")))
    assert "JOIN" not in sql


# ---------------------------------------------------------------------------
# 2 — behavioral & oracle-equivalence contracts on both arms
# ---------------------------------------------------------------------------


@BOTH_ARMS
def test_eventless_market_stays_eligible_with_none_event(engine, pooled: bool):
    with Session(engine) as s:
        oid = _add_market_outcome(s, 1, change=0.80, event_id=None)
        s.commit()

        rows = _run(s, pooled=pooled)
        assert [r.id for r in rows] == [oid]
        assert rows[0].market.event is None


@pytest.mark.parametrize("sport_key", ["americanfootball_nfl", "tennis_atp_us_open"])
@BOTH_ARMS
def test_tier_12_event_market_eligible_and_loads_event(engine, sport_key: str, pooled: bool):
    with Session(engine) as s:
        sid = _sport(s, 1, sport_key)
        eid = _event(s, 10, sport_id=sid)
        oid = _add_market_outcome(s, 1, change=0.75, event_id=eid)
        s.commit()

        rows = _run(s, pooled=pooled)
        assert [r.id for r in rows] == [oid]
        assert rows[0].market.event is not None
        assert rows[0].market.event.id == eid


@BOTH_ARMS
def test_below_tier_2_event_excluded_and_does_not_consume_pool_slot(
    engine, monkeypatch, pooled: bool
):
    monkeypatch.setattr(events_routes, "_SUGGESTION_MOVERS_POOL", 1)
    with Session(engine) as s:
        low_sid = _sport(s, 1, "tennis_other")
        nfl_sid = _sport(s, 2, "americanfootball_nfl")
        low_eid = _event(s, 10, sport_id=low_sid)
        nfl_eid = _event(s, 11, sport_id=nfl_sid)
        low_oid = _add_market_outcome(s, 1, change=0.95, event_id=low_eid)
        nfl_oid = _add_market_outcome(s, 2, change=0.25, event_id=nfl_eid)
        s.commit()

        rows = _run(s, pooled=pooled)
        assert [r.id for r in rows] == [nfl_oid]
        assert low_oid not in [r.id for r in rows]


def test_mixed_corpus_pooled_matches_legacy_oracle_row_for_row(engine, monkeypatch):
    """Mixed corpus (event-less + tier-1/2 + below-tier-2) with binding pool."""
    monkeypatch.setattr(events_routes, "_SUGGESTION_MOVERS_POOL", TEST_POOL)
    with Session(engine) as s:
        nfl_sid = _sport(s, 1, "americanfootball_nfl")
        slam_sid = _sport(s, 2, "tennis_atp_us_open")
        low_sid = _sport(s, 3, "tennis_other")

        nfl_eid = _event(s, 10, sport_id=nfl_sid)
        slam_eid = _event(s, 11, sport_id=slam_sid)
        low_eid = _event(s, 12, sport_id=low_sid)

        # Below-tier-2 rows with huge movement must not fill the pool.
        for idx in range(1, 5):
            _add_market_outcome(s, idx, change=0.99 - 0.01 * idx, event_id=low_eid)

        # Mix of eligible event-less and tier-1/2 game markets (8 total > TEST_POOL=6).
        _add_market_outcome(s, 101, change=0.88, event_id=None)
        _add_market_outcome(s, 102, change=-0.82, event_id=nfl_eid)
        _add_market_outcome(s, 103, change=0.77, event_id=slam_eid)
        _add_market_outcome(s, 104, change=-0.71, event_id=None)
        _add_market_outcome(s, 105, change=0.65, event_id=nfl_eid)
        _add_market_outcome(s, 106, change=-0.50, event_id=slam_eid)
        _add_market_outcome(s, 107, change=0.40, event_id=None)
        _add_market_outcome(s, 108, change=0.30, event_id=nfl_eid)
        s.commit()

        oracle = _run(s, pooled=False)
        pooled_rows = _run(s, pooled=True)
        assert [r.id for r in pooled_rows] == [r.id for r in oracle] == [101, 102, 103, 104, 105]
