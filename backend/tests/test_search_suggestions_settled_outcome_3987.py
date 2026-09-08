"""#3987 — the "Right now" row stops selling a FINISHED match as the day's biggest riser.

WHAT A USER SAW (production `635faf8c`, phone-width LOOK of `/search`, 2026-09-08
15:37Z). The third chip of the "Right now" row:

    Completed Match    Surging +99.0% — M25 Plaisir + H: Toby Marti...

`futures_outcomes` 225453717, market 60384159:

    name                    'Completed Match'
    current_probability      1.000000      <-- resolved
    probability_change_24h   0.990000      <-- and therefore the biggest "mover"

THE BIAS, WHICH IS THE ACTUAL DEFECT. Section 3 ranks by
`abs(probability_change_24h)`. That quantity is LARGEST EXACTLY WHEN A THING
RESOLVES — a market going to certainty is the biggest move it will ever make. So
the ranking was not merely admitting settled outcomes, it was *sorting them to
the front*. On the read above the specimen was **rank 1 of the whole pool**: the
single loudest thing on a discovery surface was a tennis match that was over.

That is the standing *settled means settled* ruling (heroes show winners, cards
show results) broken on the one surface whose whole job is "what is happening
now".

WHY THE GATE IS IN THE QUERY AND NOT IN `_mover_chips`.

`_mover_chips` is where section 3's DISPLAY rules live (#3675's prop refusal, its
one-chip-per-market cap). This one is not a display rule. The `LIMIT 5` is in the
statement, so a settled row rejected at display time has ALREADY SPENT A SLOT —
and since the specimen was rank 1, the row would have served four chips instead
of five. Eligibility belongs where the ranking happens.

It sits in the shared `conditions` list rather than on one arm, so the pooled and
legacy arms carry it identically and `test_pooled_arm_equals_the_full_scan_oracle`
in `test_search_suggestions_movers_pool_lat_p151.py` goes on grading it.

THE NULLABLE-COLUMN TRAP, WHICH IS WHY THE PREDICATE IS LONG.

`futures_outcomes.current_probability` is `Numeric(7, 6)` and **nullable**. The
terse spelling of this gate —

    FuturesOutcome.current_probability < 1.0

— is WRONG, and wrong in the silent direction: `NULL < 1.0` is NULL, not true, so
a `WHERE` carrying it drops every outcome whose probability is unknown. Measured
on production the day this shipped, inside the live pool of 400 markets:

    eligible rows in pool            2047
    current_probability IS NULL         4      <-- the terse spelling loses these
    current_probability >= 1.0          8      <-- the defect
    current_probability <= 0.0          0
    strictly between                 2035

So the terse version would have fixed 8 rows and quietly broken 4 others. UNKNOWN
IS NOT RESOLVED. `test_an_unknown_probability_is_not_a_settled_one` is the
executable form of that sentence and it fails on the one-line rewrite.

`<= 0.0` measured zero live rows and is still asserted: an outcome resolving to NO
is exactly as settled as one resolving to YES, and "zero today" is not a property
of the schema.
"""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.dialects import postgresql
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import Session


# SQLite cannot render Postgres-native column types. DDL rendering for the sqlite
# dialect ONLY — production is Postgres and never reaches them.
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
    _build_suggestion_movers_query,
)

#: The production row, by number, so a reader can go and look at it.
_SPECIMEN_OUTCOME_ID = 225453717
_SPECIMEN_MARKET_ID = 60384159

#: Big enough to hold every market these fixtures seed. The pool BOUND is not
#: what this file is testing — `..._movers_pool_lat_p151.py` owns that — and a
#: pool that also excluded rows would make an absence here ambiguous.
TEST_POOL = 50

#: Both arms, every time. The gate lives in the shared `conditions` list; a fix
#: applied to only one of them is the exact regression this parametrisation
#: catches, and the legacy arm is the live rollback path (`..._POOLED=0`).
BOTH_ARMS = pytest.mark.parametrize("pooled", [True, False], ids=["pooled", "legacy"])


@pytest.fixture(autouse=True)
def _wide_pool(monkeypatch):
    monkeypatch.setattr(events_routes, "_SUGGESTION_MOVERS_POOL", TEST_POOL)


@pytest.fixture()
def engine():
    eng = create_engine("sqlite://")
    Base.metadata.create_all(
        eng, tables=[FuturesMarket.__table__, FuturesOutcome.__table__]
    )
    return eng


def _add(session, oid, *, change, prob, mid=None):
    """One outcome in its own market, so market-level dedup can never explain a miss.

    `max_movement_24h` is DERIVED from the outcome's own change — a fixture that
    states it independently can be wrong in the same direction as the code.
    """
    mid = mid if mid is not None else oid
    session.add(
        FuturesMarket(
            id=mid,
            source="kalshi",
            external_id=f"MKT-{mid}",
            name=f"market {mid}",
            status="open",
            max_movement_24h=abs(change),
        )
    )
    session.add(
        FuturesOutcome(
            id=oid,
            market_id=mid,
            external_id=f"OUT-{oid}",
            name=f"outcome {oid}",
            current_probability=prob,
            probability_change_24h=change,
        )
    )
    return oid


def _run(engine, *, pooled):
    with Session(engine) as s:
        stmt = _build_suggestion_movers_query(pooled=pooled)
        return [r.id for r in s.execute(stmt).unique().scalars().all()]


def _seed_specimen_plus_movers(session, *, specimen_prob):
    """The production shape: the settled row is the BIGGEST mover, plus five real ones.

    The specimen's |change| is 0.99 and every honest row is below it, so the
    specimen is rank 1 by the section's own sort. That is what makes its absence
    from the result meaningful rather than incidental.
    """
    _add(
        session,
        _SPECIMEN_OUTCOME_ID,
        mid=_SPECIMEN_MARKET_ID,
        change=0.99,
        prob=specimen_prob,
    )
    honest = [_add(session, 900 + i, change=0.90 - 0.01 * i, prob=0.5) for i in range(5)]
    session.commit()
    return honest


# --------------------------------------------------------------------------
# 0 — certify the fixture BEFORE trusting any absence it proves
# --------------------------------------------------------------------------


@BOTH_ARMS
def test_the_specimen_is_rank_one_when_it_is_not_settled(engine, pooled):
    """POSITIVE CONTROL: with probability 0.5 the identical row IS returned, first.

    Without this, every assertion below could pass because the fixture never
    reached the query at all — the failure mode that makes a guard a decoration.
    It also pins the claim in the issue: the defect is not that a settled row
    sneaks in somewhere down the list, it is that it SORTS TO THE FRONT.
    """
    with Session(engine) as s:
        _seed_specimen_plus_movers(s, specimen_prob=0.5)

    ids = _run(engine, pooled=pooled)
    assert ids[0] == _SPECIMEN_OUTCOME_ID
    assert len(ids) == _SUGGESTION_MOVERS_LIMIT


# --------------------------------------------------------------------------
# 1 — the defect itself
# --------------------------------------------------------------------------


@BOTH_ARMS
def test_a_resolved_outcome_is_never_a_mover(engine, pooled):
    """`current_probability = 1.0` — the production specimen, exactly as filed."""
    with Session(engine) as s:
        _seed_specimen_plus_movers(s, specimen_prob=1.0)

    assert _SPECIMEN_OUTCOME_ID not in _run(engine, pooled=pooled)


@BOTH_ARMS
def test_an_outcome_resolved_to_no_is_equally_settled(engine, pooled):
    """`current_probability = 0.0`. Zero live rows when this shipped; still barred."""
    with Session(engine) as s:
        _seed_specimen_plus_movers(s, specimen_prob=0.0)

    assert _SPECIMEN_OUTCOME_ID not in _run(engine, pooled=pooled)


@BOTH_ARMS
def test_the_settled_row_does_not_spend_a_limit_slot(engine, pooled):
    """WHY THE GATE IS IN THE QUERY: the row still serves FIVE chips, not four.

    This is the assertion that fails if someone "simplifies" the fix by moving it
    into `_mover_chips`. A display-time refusal leaves the statement's `LIMIT 5`
    already spent on the settled row, and the user loses a chip to a bug fix.
    """
    with Session(engine) as s:
        honest = _seed_specimen_plus_movers(s, specimen_prob=1.0)

    ids = _run(engine, pooled=pooled)
    assert len(ids) == _SUGGESTION_MOVERS_LIMIT
    assert ids == honest


# --------------------------------------------------------------------------
# 2 — the nullable-column trap
# --------------------------------------------------------------------------


@BOTH_ARMS
def test_an_unknown_probability_is_not_a_settled_one(engine, pooled):
    """`current_probability IS NULL` SURVIVES. Four live rows depended on this.

    🔴 THIS IS THE TEST THAT FAILS ON THE TERSE REWRITE. Replace the predicate
    with `current_probability < 1.0` and SQL three-valued logic drops this row:
    `NULL < 1.0` is NULL, which is not true, which does not pass a `WHERE`.
    Unknown is not resolved.
    """
    with Session(engine) as s:
        _seed_specimen_plus_movers(s, specimen_prob=None)

    assert _SPECIMEN_OUTCOME_ID in _run(engine, pooled=pooled)


# --------------------------------------------------------------------------
# 3 — the boundary is AT certainty, not near it
# --------------------------------------------------------------------------


@BOTH_ARMS
@pytest.mark.parametrize("prob", [0.999999, 0.000001, 0.98, 0.02])
def test_a_nearly_certain_outcome_is_still_a_mover(engine, pooled, prob):
    """Only certainty is barred — "nearly resolved" is a real, tradeable move.

    Pinned because the tempting widening ("anything above 0.95 is basically
    over") is a PRODUCT judgement nobody has made, and it would have removed the
    live `Cut more than 25bps` row at 0.98 — a Bank of Korea market that is
    genuinely moving and genuinely unresolved.
    """
    with Session(engine) as s:
        _seed_specimen_plus_movers(s, specimen_prob=prob)

    assert _SPECIMEN_OUTCOME_ID in _run(engine, pooled=pooled)


# --------------------------------------------------------------------------
# 4 — the predicate's SHAPE, so the fix cannot be silently un-written
# --------------------------------------------------------------------------


def test_the_gate_is_null_safe_in_the_compiled_sql():
    """The rendered statement names the column three times: IS NULL, > 0, < 1.

    A structural assertion rather than a behavioural one, because the behavioural
    proof above runs on SQLite while production is Postgres — and the two engines
    agree on three-valued logic, but nothing in this file would notice if the
    predicate stopped being rendered at all.
    """
    for pooled in (True, False):
        sql = " ".join(
            str(
                _build_suggestion_movers_query(pooled=pooled).compile(
                    dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}
                )
            ).split()
        )
        assert "current_probability IS NULL" in sql
        assert "current_probability > 0.0" in sql
        assert "current_probability < 1.0" in sql
