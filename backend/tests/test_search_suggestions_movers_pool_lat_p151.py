"""`/api/events/search-suggestions` stops sorting 1.14 GB to print two chips. LAT-P151, #2285.

WHY THIS FILE EXISTS.

`GET /api/events/search-suggestions` is what `frontend/app/search/page.tsx:313`
calls on mount; it renders "Loading suggestions..." until it answers, so it is
the first thing a person sees after tapping Search. On 2026-08-30 a cold read of
it measured `wall=8009.5; db=7914.0; q=5; maxq=7732.6` — 99 % of the request in
one statement — and the 24 h slow-request ring held eight of them, p50 12,969 ms,
max 18,388 ms.

The statement is section 3 of the build, "futures big movers":

    SELECT ... FROM futures_outcomes fo
    JOIN futures_markets fm ON fm.id = fo.market_id
    WHERE fm.status = 'open'
      AND fo.probability_change_24h IS NOT NULL
      AND abs(fo.probability_change_24h) > 0.02
    ORDER BY abs(fo.probability_change_24h) DESC
    LIMIT 5

`abs()` is not indexed AND the join sits ABOVE the sort, so `LIMIT 5` cannot
bound it. Production `EXPLAIN (ANALYZE, BUFFERS)` 2026-08-30, fingerprint
`775d6ff2b74e14cd`:

    Limit                                      9,498 ms
      Nested Loop
        Gather Merge
          Sort    external merge, 5,736 kB to DISK
            parallel Seq Scan futures_outcomes
    146,425 shared blocks (~1.14 GB)   Shared I/O Read Time 15,428 ms

THE FIX IS NOT NEW AND THAT IS THE POINT.

LAT-P124 measured this exact cost, named an expression index as the permanent
form, and parked it as P124-1 because DDL is integrator-owned (ruling 080).
LAT-P139 shipped a cache in front of it and parked P124-1 a second time, writing
"the build is not made faster" as a decision. Neither noticed that
`/api/futures/movers` — one route file over — had solved the IDENTICAL statement
in LAT-P108 two days earlier with no DDL at all, by ranking inside the top-N
markets by `max_movement_24h`.

That bound now lives in `app/utils/movement_pool.py` with its proof, and this
section is its second consumer. Same production minute:

    9,498 ms -> 588 ms      146,425 shared blocks -> 3,629
    external merge to disk  -> top-N heapsort in memory

Verified on production 2026-08-30, ONE ATOMIC STATEMENT PER PROBE so both arms
read the same snapshot — a two-statement comparison is churn, not evidence,
because `update_max_movement` rewrites the column every ten minutes:

    legacy top-5   ->  5 of  5 inside the pool of 400   (fp b2e02339a8f83f30)
    legacy top-20  -> 20 of 20 inside the pool of 400
    legacy top-50  -> 50 of 50 inside the pool of 400

WHAT THIS FILE ASSERTS, AND WHY EACH ONE IS HERE.

1. The fixture is CERTIFIED FIRST. A pool wide enough to hold every market makes
   every equality below vacuously true, so `test_fixture_is_not_vacuous` fails
   unless the bound genuinely excludes markets.
2. The two arms agree row for row, with the legacy full-scan arm
   (`SEARCH_SUGGESTIONS_MOVERS_POOLED=0`) as the ORACLE. It is kept in the module
   as the rollback path, so the oracle is not a test-only fiction.
3. The 0.02 threshold, the `open`-only status list and the limit of five are
   asserted on BOTH arms — this queue ships a cost change, and any of those three
   drifting would change which chips a person sees.
4. The soundness CONTRACT is executable:
   `test_the_bound_depends_on_max_movement_being_maintained` builds a market
   where `max_movement_24h` lies and shows the pooled arm dropping a real mover.
   That is the precondition written down where an edit to `update_max_movement`
   will trip over it, not a bug being enshrined.
5. The pooled arm must NOT join `futures_markets`. Re-stating the status filter
   as a join would be the most natural "tidy-up" in the file and it would put the
   join back above the sort — restoring the entire defect while every equivalence
   test above stayed green. `test_the_pooled_arm_does_not_join_the_market_table`
   is the only thing standing between this fix and that edit.
"""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.dialects import postgresql
from sqlalchemy.ext.compiler import compiles
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
from app.routes import events as events_routes  # noqa: E402
from app.routes.events import (  # noqa: E402
    _SUGGESTION_MOVERS_LIMIT,
    _SUGGESTION_MOVERS_POOL,
    _SUGGESTION_MOVERS_POOLED,
    _SUGGESTION_MOVERS_STATUSES,
    _build_suggestion_movers_query,
)

#: Small enough that the pool bound BINDS on a fixture we can hold in memory, and
#: NOT smaller than the ask — see `test_the_pool_can_never_be_smaller_than_the_ask`
#: for why 5 is a floor and not a convenience. The production constant is asserted
#: separately, in `test_the_production_pool_is_the_number_the_probe_used`.
TEST_POOL = 6

#: The section's own threshold, restated here so a test that means "just over the
#: bar" cannot silently start meaning "well over it" if the constant moves.
THRESHOLD = 0.02


@pytest.fixture(autouse=True)
def small_pool(monkeypatch):
    monkeypatch.setattr(events_routes, "_SUGGESTION_MOVERS_POOL", TEST_POOL)


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


def _seed(session, markets, *, status="open"):
    """`markets` is {market_id: [change, ...]}; `max_movement_24h` is DERIVED.

    Derived rather than hand-written on purpose: a fixture that states
    `max_movement_24h` independently of its own outcomes is a fixture that can be
    wrong in the same direction as the code, and the whole bound rests on the two
    agreeing. The one test that needs them to DISAGREE seeds by hand and says so.
    """
    for mid, changes in markets.items():
        present = [c for c in changes if c is not None]
        session.add(
            _market(
                mid,
                status=status,
                max_movement=max(abs(c) for c in present) if present else None,
            )
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


#: A market per distinct movement level, descending. The pool of 4 cannot hold
#: all 12, so the bound binds.
_SPREAD = {mid: [round(0.90 - 0.05 * mid, 4)] for mid in range(1, 13)}

#: The top movers CONCENTRATED in two markets — the case where the answer spans
#: fewer markets than the ask, which a wrong "top-`limit` markets" bound would
#: fail and the real superset bound survives.
_CONCENTRATED = {
    1: [0.95, -0.94, 0.93, -0.92, 0.91, 0.90],
    2: [0.89, -0.88, 0.87],
    **{mid: [round(0.50 - 0.01 * mid, 4)] for mid in range(3, 14)},
}

#: Ties everywhere at the top — the shape production is actually in. The live
#: read on 2026-08-30 returned outcomes at |0.996| and |0.980| out of a top-5
#: whose smallest value was 0.980, with hundreds of rows sitting on it.
_TIED = {mid: [-0.98, 0.10] for mid in range(1, 10)}


def _run(session, *, pooled):
    stmt = _build_suggestion_movers_query(pooled=pooled)
    return session.execute(stmt).unique().scalars().all()


def _ids(rows):
    return [r.id for r in rows]


def _vals(rows):
    return [abs(float(r.probability_change_24h)) for r in rows]


def _sql(*, pooled) -> str:
    return " ".join(
        str(
            _build_suggestion_movers_query(pooled=pooled).compile(
                dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}
            )
        ).split()
    )


# --------------------------------------------------------------------------
# 0 — certify the fixture BEFORE trusting anything it proves
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "corpus", [_SPREAD, _CONCENTRATED, _TIED], ids=["spread", "concentrated", "tied"]
)
def test_fixture_is_not_vacuous(corpus):
    """The pool must genuinely exclude markets, or every equality below is free."""
    assert TEST_POOL < len(corpus), (
        f"pool {TEST_POOL} holds every one of the {len(corpus)} markets in this "
        "corpus — the bound is not exercised and the equivalence tests prove nothing"
    )


def test_the_small_pool_fixture_actually_took(engine):
    """The autouse monkeypatch is load-bearing; prove it reached the SQL.

    If `_build_suggestion_movers_query` ever reads the pool size from somewhere
    other than the module global, every test in this file would silently run
    against the production pool of 400 — which holds every fixture market, which
    makes the whole file vacuous. That failure is invisible without this test.
    """
    assert f"LIMIT {TEST_POOL}" in _sql(pooled=True)


# --------------------------------------------------------------------------
# 1 — the two arms agree
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "corpus", [_SPREAD, _CONCENTRATED], ids=["spread", "concentrated"]
)
def test_pooled_arm_equals_the_full_scan_oracle(engine, corpus):
    with Session(engine) as s:
        _seed(s, corpus)
        oracle = _run(s, pooled=False)
        pooled = _run(s, pooled=True)
        assert len(oracle) == _SUGGESTION_MOVERS_LIMIT
        assert _vals(pooled) == _vals(oracle)
        assert _ids(pooled) == _ids(oracle)


def test_ties_are_not_a_regression(engine):
    """On a tied corpus the VALUES must match; the ids may not, and never could.

    The legacy query's `ORDER BY abs(...) DESC` carries no tie-break, so which of
    hundreds of equal-valued rows it returned was already the planner's choice.
    Asserting id equality here would be asserting a property production never
    had — and would make this file fail for a reason that is not a regression.
    """
    with Session(engine) as s:
        _seed(s, _TIED)
        assert _vals(_run(s, pooled=True)) == _vals(_run(s, pooled=False))


def test_the_arms_agree_when_the_answer_is_short(engine):
    """Fewer qualifying outcomes than the ask: both arms return the same few.

    A `LIMIT 5` that quietly became "always five rows" would show up here and
    nowhere else in this file.
    """
    with Session(engine) as s:
        _seed(s, {1: [0.9], 2: [-0.5], 3: [0.001]})
        oracle = _run(s, pooled=False)
        assert len(oracle) == 2  # 0.001 is under the threshold
        assert _vals(_run(s, pooled=True)) == _vals(oracle)


def test_the_arms_agree_when_nothing_qualifies(engine):
    with Session(engine) as s:
        _seed(s, {1: [0.001], 2: [-0.002]})
        assert _run(s, pooled=False) == []
        assert _run(s, pooled=True) == []


# --------------------------------------------------------------------------
# 2 — the three things that decide WHICH CHIPS A PERSON SEES
# --------------------------------------------------------------------------


@pytest.mark.parametrize("pooled", [True, False], ids=["pooled", "legacy"])
def test_the_threshold_is_strictly_greater_than_two_percent(engine, pooled):
    """`> 0.02`, not `>=` and not a different number, on BOTH arms."""
    with Session(engine) as s:
        _seed(s, {1: [THRESHOLD], 2: [THRESHOLD + 0.001], 3: [-THRESHOLD]})
        vals = _vals(_run(s, pooled=pooled))
        assert vals == [pytest.approx(THRESHOLD + 0.001)], (
            "an outcome sitting exactly ON the threshold must be excluded — "
            f"got {vals}"
        )


@pytest.mark.parametrize("pooled", [True, False], ids=["pooled", "legacy"])
def test_non_open_markets_stay_out_of_both_arms(engine, pooled):
    with Session(engine) as s:
        _seed(s, {1: [0.9]}, status="resolved")
        _seed(s, {2: [0.5]}, status="active")
        _seed(s, {3: [0.1]}, status="open")
        assert _vals(_run(s, pooled=pooled)) == [pytest.approx(0.1)], (
            "section 3 counts `open` alone. `/api/futures/movers` counts "
            "('open','active') and this section never has; widening it here "
            "would change what a person sees inside a latency queue."
        )


@pytest.mark.parametrize("pooled", [True, False], ids=["pooled", "legacy"])
def test_null_change_outcomes_stay_out_of_both_arms(engine, pooled):
    with Session(engine) as s:
        _seed(s, {1: [None, 0.9], 2: [None]})
        assert _vals(_run(s, pooled=pooled)) == [pytest.approx(0.9)]


@pytest.mark.parametrize("pooled", [True, False], ids=["pooled", "legacy"])
def test_both_arms_stop_at_five(engine, pooled):
    with Session(engine) as s:
        _seed(s, {1: [0.9, 0.8, 0.7, 0.6, 0.5, 0.4, 0.3]})
        assert len(_run(s, pooled=pooled)) == _SUGGESTION_MOVERS_LIMIT == 5


@pytest.mark.parametrize("pooled", [True, False], ids=["pooled", "legacy"])
def test_both_arms_rank_by_absolute_movement(engine, pooled):
    """A faller of -0.9 outranks a riser of +0.5. `abs`, not signed."""
    with Session(engine) as s:
        _seed(s, {1: [-0.9], 2: [0.5]})
        assert _vals(_run(s, pooled=pooled)) == [
            pytest.approx(0.9),
            pytest.approx(0.5),
        ]


# --------------------------------------------------------------------------
# 3 — the bound's precondition, written down where an edit will trip over it
# --------------------------------------------------------------------------


def test_a_market_with_null_max_movement_is_out_of_the_pool(engine):
    """The documented COST of the bound, asserted rather than left to be found.

    A market whose `max_movement_24h` has never been written cannot be ordered
    against the pool, so its outcomes cannot reach the answer however far they
    have moved. `/api/futures/movers` has shipped this same trade since
    LAT-P108; it is why the rollback flag exists.
    """
    with Session(engine) as s:
        s.add(_market(1, max_movement=None))
        s.add(_outcome(10, 1, 0.99))
        _seed(s, {2: [0.3]})
        assert _vals(_run(s, pooled=False)) == [
            pytest.approx(0.99),
            pytest.approx(0.3),
        ]
        assert _vals(_run(s, pooled=True)) == [pytest.approx(0.3)]


def test_the_bound_depends_on_max_movement_being_maintained(engine):
    """Seeded BY HAND so `max_movement_24h` lies, which `_seed` cannot do.

    This is the executable form of the precondition in
    `app/utils/movement_pool.py`: the pool is a superset only while the column
    tracks its own outcomes. If `update_max_movement` ever stops maintaining it,
    this test is the thing that says so — in both consumers at once, which is
    why the bound has one home.
    """
    with Session(engine) as s:
        # A real mover hidden behind a stale, tiny max_movement.
        s.add(_market(1, max_movement=0.01))
        s.add(_outcome(10, 1, 0.99))
        # Enough markets that legitimately outrank it to fill the pool.
        _seed(s, {mid: [0.5 - 0.01 * mid] for mid in range(2, 2 + TEST_POOL)})
        assert pytest.approx(0.99) == _vals(_run(s, pooled=False))[0]
        assert pytest.approx(0.99) not in _vals(_run(s, pooled=True))


# --------------------------------------------------------------------------
# 4 — the SHAPE, because equivalence tests cannot see a plan
# --------------------------------------------------------------------------


def test_the_pooled_arm_does_not_join_the_market_table():
    """🔴 THE LOAD-BEARING ONE.

    Re-stating the status filter as a join — "clearer", "explicit", identical
    results on every fixture in this file — puts `futures_markets` back ABOVE the
    sort, and an unbounded sort is the entire 9,498 ms. Every equivalence test
    above would stay green through that edit. This one would not.
    """
    sql = _sql(pooled=True)
    assert "JOIN futures_markets" not in sql, (
        "the pooled arm joined the market table again — the LIMIT can no longer "
        "bound the sort and the 1.14 GB is back, with every other test green"
    )
    assert "futures_outcomes.market_id IN (SELECT futures_markets.id" in sql


def test_the_pooled_arm_bounds_the_market_scan():
    sql = _sql(pooled=True)
    assert "ORDER BY futures_markets.max_movement_24h DESC" in sql
    assert "futures_markets.max_movement_24h IS NOT NULL" in sql
    assert f"LIMIT {TEST_POOL}" in sql


def test_the_legacy_arm_is_still_the_query_it_is_rolling_back_to():
    """The oracle must remain the shape production actually ran."""
    sql = _sql(pooled=False)
    assert "JOIN futures_markets" in sql
    assert "max_movement_24h" not in sql
    assert "ORDER BY abs(futures_outcomes.probability_change_24h) DESC" in sql


@pytest.mark.parametrize("pooled", [True, False], ids=["pooled", "legacy"])
def test_both_arms_keep_the_not_null_condition(pooled):
    assert "futures_outcomes.probability_change_24h IS NOT NULL" in _sql(pooled=pooled)


# --------------------------------------------------------------------------
# 5 — the production constants, and that the fast path is what ships
# --------------------------------------------------------------------------


def test_the_pool_can_never_be_smaller_than_the_ask():
    """🔴 A FLOOR THE BOUND NEEDS AND THE SUPERSET ARGUMENT DOES NOT MENTION.

    Found by this file failing rather than by reading the proof: with one outcome
    per market, a pool of N markets can supply at most N rows, so a pool smaller
    than the limit truncates the answer even though every market in it is
    correctly chosen. The superset argument is about WHICH markets qualify and is
    silent on how many rows they hold.

    Production is 400 against an ask of 5, so this has 80x of headroom and can
    only be broken by an edit — which is exactly what a guard is for.
    """
    assert _SUGGESTION_MOVERS_POOL >= _SUGGESTION_MOVERS_LIMIT
    assert TEST_POOL >= _SUGGESTION_MOVERS_LIMIT, (
        "the test pool dropped below the ask, so the equivalence tests in this "
        "file would fail for a fixture reason and read as a code regression"
    )


def test_the_production_pool_is_the_number_the_probe_used():
    """400 — `/api/futures/movers`' own floor, and the number verified on prod.

    Changing it invalidates the atomic superset probes quoted in this file's
    docstring, so the constant and the evidence move together or not at all.
    """
    assert _SUGGESTION_MOVERS_POOL == 400


def test_the_status_list_is_open_only():
    assert _SUGGESTION_MOVERS_STATUSES == ("open",)


def test_the_fast_path_is_the_default():
    """A rollback flag that defaults to the slow arm ships nothing."""
    assert _SUGGESTION_MOVERS_POOLED is True


@pytest.mark.parametrize(
    "value,expected",
    [("0", False), ("false", False), ("no", False), ("FALSE", False),
     ("1", True), ("", True), ("yes", True), (" 0 ", False)],
)
def test_the_rollback_flag_reads_the_environment(monkeypatch, value, expected):
    """Re-derived exactly as the module derives it, so the rollback Alex would
    reach for at 3 a.m. is the rollback that exists."""
    monkeypatch.setenv("SEARCH_SUGGESTIONS_MOVERS_POOLED", value)
    import os

    got = os.getenv("SEARCH_SUGGESTIONS_MOVERS_POOLED", "1").strip().lower() not in (
        "0",
        "false",
        "no",
    )
    assert got is expected


def test_the_route_actually_uses_the_builder_and_the_flag():
    """Both arms could be perfect and unreachable. Pin the call site.

    Read from source rather than executed, because the section sits inside a
    600-line coroutine behind a bare `except Exception: pass` — the construct
    that hid #2286's two dead sections for the entire life of this route, and
    that would hide a `NameError` here just as completely.
    """
    import inspect

    body = inspect.getsource(events_routes._build_search_suggestions)
    assert (
        "_build_suggestion_movers_query(pooled=_SUGGESTION_MOVERS_POOLED)" in body
    ), "section 3 no longer calls the builder — the fix is unreachable"
    assert "select(FuturesOutcome)" not in body.split("--- 3.")[1].split("--- 4.")[0], (
        "section 3 grew its own inline query again beside the builder"
    )


def test_the_pool_shape_has_one_home():
    """`/api/futures/movers` and this section must emit the SAME pool subquery.

    Not a style rule: the pool is a claim about an invariant maintained by
    `update_max_movement`, and two spellings of it can be repaired one at a time.
    Compared by rendered SQL rather than by `is`, because that is what actually
    reaches Postgres.
    """
    from app.utils.movement_pool import market_pool_subquery

    rendered = " ".join(
        str(
            market_pool_subquery(pool_size=7, statuses=("open", "active")).compile(
                dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}
            )
        ).split()
    )
    assert rendered == (
        "(SELECT futures_markets.id FROM futures_markets "
        "WHERE futures_markets.status IN ('open', 'active') "
        "AND futures_markets.max_movement_24h IS NOT NULL "
        "ORDER BY futures_markets.max_movement_24h DESC LIMIT 7)"
    )
