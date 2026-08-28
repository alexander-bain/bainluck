"""`/api/futures/movers` stops sorting the whole outcome table. LAT-P108.

WHY THIS FILE EXISTS.

`GET /api/futures/movers` — the "Biggest Movers" strip on the iOS Futures tab
(`Views/FuturesListView.swift:51` -> `FuturesListViewModel.loadMovers`) — cost
**11,129 ms of execution time** on production on 2026-08-28 to return ten rows.
`x-timing-split` on the live cold request read `wall=13090.5; db=13041.5; q=1`:
one statement, thirteen seconds, and nothing else in the request worth naming.

The statement was:

    SELECT ... FROM futures_outcomes fo
    JOIN futures_markets fm ON fo.market_id = fm.id
    WHERE fo.probability_change_24h IS NOT NULL
      AND fm.status IN ('open','active')
    ORDER BY abs(fo.probability_change_24h) DESC
    LIMIT 10

`abs()` is not indexed, so `EXPLAIN (ANALYZE)` on production showed a **parallel
Seq Scan reading 977,240 rows per worker (9,799 ms of the 11,129)**, a hash join
down to 124,272 survivors, and a full Sort of all of them to emit ten.

THE FIX, AND WHY IT IS A BOUND AND NOT A SAMPLE.

`futures_markets.max_movement_24h` is defined by the task that writes it
(`app.tasks.update_max_movement`, every 10 minutes) as
`MAX(ABS(outcome.probability_change_24h))` over that market's outcomes. So for
every outcome, `its market's max_movement >= |its own change|`. Take the top-N
markets by `max_movement_24h`; let `v` be the smallest max_movement in that
pool. Every outcome whose |change| exceeds `v` lives in a market whose
max_movement exceeds `v`, and therefore in a market already inside the pool.
The pool is a **provable superset** of the answer.

Measured on production 2026-08-28, one atomic statement per probe so both arms
read the same snapshot (a two-statement comparison of this endpoint is churn,
not evidence — prices move between them):

    limit  10 / pool  400   value vector IDENTICAL   id list IDENTICAL
    limit  20 / pool  800   value vector IDENTICAL   id list IDENTICAL
    limit 100 / pool 1500   value vector IDENTICAL   id list differs inside a
                            tie group — see `test_ties_are_not_a_regression`

Row-path timings on the same afternoon: 11,129 ms -> 627 ms (pool 400),
1,138 ms (pool 1000), 2,833 ms (pool 2500).

WHAT THIS FILE ASSERTS, AND WHY EACH ONE IS HERE.

1. The fixture is CERTIFIED FIRST. If the pool were wide enough to hold every
   market, every equality below would be vacuously true. `test_fixture_is_not_vacuous`
   fails unless the bound genuinely excludes markets.
2. The two arms agree, row for row, across limits and across corpora — with the
   legacy full-scan arm (`FUTURES_MOVERS_POOLED=0`) as the ORACLE. It is kept in
   the module as the rollback path, so the oracle is not a test-only fiction.
3. The soundness CONTRACT is executable. The bound holds only while
   `max_movement_24h` tracks its own outcomes;
   `test_the_bound_depends_on_max_movement_being_maintained` constructs a market
   where it does not and shows the pooled arm dropping a real mover. That is not
   a bug being enshrined — it is the precondition being written down where a
   future edit to `update_max_movement` will trip over it.
4. `limit` is clamped, and clamped BEFORE the cache key.
5. The route still calls the builder. A guard that only exercises the helper
   stays green when the caller stops calling it.

WHAT THIS FILE DELIBERATELY DOES NOT ASSERT.

Freshness. Three of the ten rows production served on 2026-08-28 were last
written on **2026-07-24** — thirty-five days of "24-hour change". A read-side
`last_updated >= now() - 24h` filter is the obvious fix and it is **incompatible
with this bound**: `max_movement_24h` is computed over all of a market's
outcomes including the stale ones, so ranking the pool by it while filtering the
answer by freshness breaks the superset guarantee. Measured, not feared — at
limit 20 the pooled and unbounded arms disagreed on the VALUE vector, not merely
on ties. The staleness is an upstream data bug and is parked as one.
"""

from __future__ import annotations

import inspect
import os

import pytest
from sqlalchemy import create_engine
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.dialects import postgresql
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import Session


# SQLite cannot render Postgres-native column types. These shims affect DDL
# rendering for the sqlite dialect ONLY — production is Postgres and never
# reaches them.
@compiles(JSONB, "sqlite")
def _jsonb_on_sqlite(type_, compiler, **kw):  # pragma: no cover - DDL shim
    return "JSON"


@compiles(ARRAY, "sqlite")
def _array_on_sqlite(type_, compiler, **kw):  # pragma: no cover - DDL shim
    return "JSON"


from app.models.models import Base, FuturesMarket, FuturesOutcome  # noqa: E402
from app.routes import futures as futures_routes  # noqa: E402
from app.routes.futures import (  # noqa: E402
    _MOVERS_POOL_MAX,
    _MOVERS_POOL_MIN,
    _MOVERS_POOL_PER_ITEM,
    _build_movers_query,
    _clamp_movers_limit,
    _movers_market_pool_size,
)

#: Small enough that the pool bound BINDS on a fixture we can hold in memory.
#: The production constants are asserted separately, in
#: `test_production_pool_constants_are_what_the_measurement_used`.
TEST_POOL_MIN = 5
TEST_POOL_MAX = 8
TEST_POOL_PER_ITEM = 2


@pytest.fixture(autouse=True)
def small_pool(monkeypatch):
    monkeypatch.setattr(futures_routes, "_MOVERS_POOL_MIN", TEST_POOL_MIN)
    monkeypatch.setattr(futures_routes, "_MOVERS_POOL_MAX", TEST_POOL_MAX)
    monkeypatch.setattr(futures_routes, "_MOVERS_POOL_PER_ITEM", TEST_POOL_PER_ITEM)


def _market(mid: int, *, status: str = "open", max_movement=None) -> FuturesMarket:
    return FuturesMarket(
        id=mid,
        source="kalshi",
        external_id=f"MKT-{mid}",
        name=f"market {mid}",
        status=status,
        max_movement_24h=max_movement,
    )


def _outcome(oid: int, mid: int, change) -> FuturesOutcome:
    return FuturesOutcome(
        id=oid,
        market_id=mid,
        external_id=f"OUT-{oid}",
        name=f"outcome {oid}",
        current_probability=0.5,
        probability_change_24h=change,
    )


def _seed(session, markets):
    """`markets` is {market_id: [change, ...]}; max_movement_24h is DERIVED.

    Derived rather than hand-written on purpose: a fixture that states
    `max_movement_24h` independently of the outcomes is a fixture that can be
    wrong in the same direction as the code, and the whole bound rests on the
    two agreeing.
    """
    for mid, changes in markets.items():
        present = [c for c in changes if c is not None]
        session.add(
            _market(mid, max_movement=max(abs(c) for c in present) if present else None)
        )
        for i, change in enumerate(changes):
            session.add(_outcome(mid * 1000 + i, mid, change))
    session.commit()


@pytest.fixture()
def engine():
    eng = create_engine("sqlite://")
    Base.metadata.create_all(
        eng, tables=[FuturesMarket.__table__, FuturesOutcome.__table__]
    )
    return eng


#: A market per distinct movement level, so the pool boundary lands somewhere
#: real. Levels descend; the pool of 5-8 markets cannot hold all 14.
_SPREAD = {mid: [round(0.90 - 0.05 * mid, 4)] for mid in range(1, 15)}

#: The top movers CONCENTRATED in two markets — the case where the answer spans
#: fewer markets than `limit`, which a naive "top-`limit` markets" bound would
#: also survive and a wrong one would not.
_CONCENTRATED = {
    1: [0.95, -0.94, 0.93, -0.92, 0.91],
    2: [0.90, -0.89, 0.88],
    **{mid: [round(0.50 - 0.01 * mid, 4)] for mid in range(3, 16)},
}

#: Ties everywhere at the top — the shape production is actually in (hundreds of
#: outcomes sitting on -0.98).
_TIED = {mid: [-0.98, 0.10] for mid in range(1, 12)}


def _run(session, limit, *, pooled):
    stmt = _build_movers_query(limit, pooled=pooled)
    return session.execute(stmt).unique().scalars().all()


def _ids(rows):
    return [r.id for r in rows]


def _vals(rows):
    return [abs(float(r.probability_change_24h)) for r in rows]


# --------------------------------------------------------------------------
# 0 — certify the fixture BEFORE trusting anything it proves
# --------------------------------------------------------------------------


@pytest.mark.parametrize("corpus", [_SPREAD, _CONCENTRATED, _TIED], ids=list("SCT"))
@pytest.mark.parametrize("limit", [1, 3])
def test_fixture_is_not_vacuous(engine, corpus, limit):
    """The pool must genuinely exclude markets, or every equality below is free."""
    pool = _movers_market_pool_size(limit)
    assert pool < len(corpus), (
        f"pool {pool} holds every one of the {len(corpus)} markets in this corpus — "
        "the bound is not exercised and the equivalence tests prove nothing"
    )


# --------------------------------------------------------------------------
# 1 — the two arms agree
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "corpus", [_SPREAD, _CONCENTRATED], ids=["spread", "concentrated"]
)
@pytest.mark.parametrize("limit", [1, 2, 3, 4])
def test_pooled_arm_equals_the_full_scan_oracle(engine, corpus, limit):
    with Session(engine) as s:
        _seed(s, corpus)
        oracle = _run(s, limit, pooled=False)
        pooled = _run(s, limit, pooled=True)
        assert len(oracle) == limit
        assert _vals(pooled) == _vals(oracle)
        assert _ids(pooled) == _ids(oracle)


def test_ties_are_not_a_regression(engine):
    """On a tied corpus the VALUES must match; the ids may not, and never could.

    The legacy query's `ORDER BY abs(...) DESC` carries no tie-break, so which
    of hundreds of equal-valued rows it returned was already the planner's
    choice. Asserting id equality here would be asserting a property production
    never had.
    """
    with Session(engine) as s:
        _seed(s, _TIED)
        oracle = _run(s, 4, pooled=False)
        pooled = _run(s, 4, pooled=True)
        assert _vals(pooled) == _vals(oracle) == [0.98, 0.98, 0.98, 0.98]


def test_closed_markets_stay_out_of_both_arms(engine):
    with Session(engine) as s:
        _seed(s, _SPREAD)
        s.add(_market(900, status="closed", max_movement=0.99))
        s.add(_outcome(900_001, 900, -0.99))
        s.commit()
        for pooled in (True, False):
            assert 900_001 not in _ids(_run(s, 3, pooled=pooled))


def test_null_change_outcomes_stay_out_of_both_arms(engine):
    with Session(engine) as s:
        _seed(s, {**_SPREAD, 20: [None, 0.99]})
        for pooled in (True, False):
            ids = _ids(_run(s, 3, pooled=pooled))
            assert 20_001 in ids, "the market's real mover must still be reachable"
            assert 20_000 not in ids, "the NULL-change sibling must not be"


# --------------------------------------------------------------------------
# 2 — the soundness contract, written down as a test rather than as a hope
# --------------------------------------------------------------------------


def test_the_bound_depends_on_max_movement_being_maintained(engine):
    """A market whose `max_movement_24h` understates its outcomes is invisible.

    This is the precondition, not a defect being blessed:
    `app.tasks.update_max_movement` recomputes the column every 10 minutes as
    `MAX(ABS(probability_change_24h))`, and the pool is sound exactly while that
    is true. If that task is ever retimed, narrowed, or made conditional, this
    test is the thing that says what breaks.
    """
    with Session(engine) as s:
        _seed(s, _SPREAD)
        # A genuine top mover in a market that CLAIMS to have barely moved.
        s.add(_market(500, max_movement=0.001))
        s.add(_outcome(500_001, 500, -0.99))
        s.commit()

        assert 500_001 in _ids(_run(s, 3, pooled=False)), "the oracle must see it"
        assert 500_001 not in _ids(_run(s, 3, pooled=True)), (
            "if this starts passing, the pool no longer depends on max_movement_24h "
            "and this file's soundness argument has moved — re-derive it"
        )


def test_a_market_with_null_max_movement_is_out_of_the_pool(engine):
    """`max_movement_24h IS NULL` means the writer has never seen a mover there.

    `update_max_movement` only touches markets that appear in its aggregate, so
    NULL means "no non-null change on any outcome" — which is also exactly the
    set the outcome-level predicate rejects. The two agree, and this pins it.
    """
    with Session(engine) as s:
        _seed(s, _SPREAD)
        s.add(_market(600, max_movement=None))
        s.add(_outcome(600_001, 600, None))
        s.commit()
        assert 600_001 not in _ids(_run(s, 3, pooled=True))
        assert 600_001 not in _ids(_run(s, 3, pooled=False))


# --------------------------------------------------------------------------
# 3 — the bounds themselves
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "asked,expected",
    [(-5, 1), (0, 1), (1, 1), (10, 10), (20, 20), (100, 100), (101, 100), (99999, 100)],
)
def test_limit_is_clamped(asked, expected):
    assert _clamp_movers_limit(asked) == expected


def test_pool_size_scales_with_limit_and_stays_inside_its_bounds(monkeypatch):
    monkeypatch.setattr(futures_routes, "_MOVERS_POOL_MIN", _MOVERS_POOL_MIN)
    monkeypatch.setattr(futures_routes, "_MOVERS_POOL_MAX", _MOVERS_POOL_MAX)
    monkeypatch.setattr(futures_routes, "_MOVERS_POOL_PER_ITEM", _MOVERS_POOL_PER_ITEM)
    sizes = [_movers_market_pool_size(n) for n in (1, 10, 20, 50, 100)]
    assert sizes == [400, 400, 800, 1500, 1500]
    assert all(_MOVERS_POOL_MIN <= s <= _MOVERS_POOL_MAX for s in sizes)


def test_production_pool_constants_are_what_the_measurement_used():
    """The numbers in the module docstring were measured at these values."""
    assert (_MOVERS_POOL_MIN, _MOVERS_POOL_MAX, _MOVERS_POOL_PER_ITEM) == (
        400,
        1500,
        40,
    )


def test_the_fast_path_is_the_default():
    """A flag that ships OFF ships nothing, and nothing about it looks red."""
    if os.getenv("FUTURES_MOVERS_POOLED") is not None:
        pytest.skip("FUTURES_MOVERS_POOLED is set in this environment")
    assert futures_routes._MOVERS_POOLED is True


# --------------------------------------------------------------------------
# 4 — shape, and the caller
# --------------------------------------------------------------------------


def _sql(limit, *, pooled):
    return " ".join(
        str(
            _build_movers_query(limit, pooled=pooled).compile(
                dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}
            )
        ).split()
    )


def test_pooled_sql_bounds_the_market_scan(monkeypatch):
    monkeypatch.setattr(futures_routes, "_MOVERS_POOL_MIN", _MOVERS_POOL_MIN)
    monkeypatch.setattr(futures_routes, "_MOVERS_POOL_MAX", _MOVERS_POOL_MAX)
    monkeypatch.setattr(futures_routes, "_MOVERS_POOL_PER_ITEM", _MOVERS_POOL_PER_ITEM)
    sql = _sql(10, pooled=True)
    assert "max_movement_24h DESC LIMIT 400" in sql
    assert "futures_outcomes.market_id IN (SELECT futures_markets.id" in sql
    assert sql.endswith(
        "ORDER BY abs(futures_outcomes.probability_change_24h) DESC LIMIT 10"
    )


@pytest.mark.parametrize("pooled", [True, False])
def test_both_arms_keep_the_not_null_condition(pooled):
    """🔴 SHAPE, not behaviour, and the reason is a dialect difference.

    SQLite sorts NULLs LAST under `ORDER BY ... DESC`; **Postgres sorts them
    FIRST**. So dropping `probability_change_24h IS NOT NULL` is invisible to
    every in-memory test in this file and would put NULL-change rows at the TOP
    of Movers in production. Found by mutating the source, not by reasoning
    about it: the behavioural test stayed green.
    """
    assert "futures_outcomes.probability_change_24h IS NOT NULL" in _sql(
        10, pooled=pooled
    )


def test_the_pool_excludes_markets_with_no_recorded_movement():
    """🔴 SHAPE, same dialect trap, and this one is load-bearing.

    `ORDER BY max_movement_24h DESC` on Postgres is NULLS FIRST. Without
    `max_movement_24h IS NOT NULL` the pool fills with the ~20,200 open markets
    that have never recorded a mover, the real movers never enter it, and
    "Biggest Movers" goes empty — fast, and wrong. SQLite orders the other way,
    so the seeded corpora cannot see this.
    """
    sql = _sql(10, pooled=True)
    assert "futures_markets.max_movement_24h IS NOT NULL" in sql


def test_legacy_arm_is_still_the_query_it_is_rolling_back_to():
    sql = _sql(10, pooled=False)
    assert (
        "JOIN futures_markets ON futures_outcomes.market_id = futures_markets.id" in sql
    )
    assert "futures_markets.status IN ('open', 'active')" in sql
    assert "max_movement_24h DESC LIMIT" not in sql


def test_the_route_actually_uses_the_builder_and_the_clamp():
    """A helper-only guard stays green when the caller stops calling it."""
    src = inspect.getsource(futures_routes.get_futures_movers)
    assert "_build_movers_query(" in src
    assert "pooled=_MOVERS_POOLED" in src
    # Clamped BEFORE the cache key, or `limit=99999` mints its own Redis entry.
    assert src.index("_clamp_movers_limit(") < src.index("cache_key = ")
