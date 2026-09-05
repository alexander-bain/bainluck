"""`_create_settled_market`'s outcome INSERT, executed against a REAL PostgreSQL.

CAL-P1004R (#1852, repairs CERT-948). This is the round trip CERT-948 named:
drive the real gap-create path with `status=active, result=""` and read the
stored row back out of the server, asserting `is_winner IS NULL` and
`resolution_source IS NULL`, with finalized yes/no controls beside it.

## the defect

`futures_outcomes.is_winner` carries BOTH `default=False` (SQLAlchemy, applied
at execute time) and `server_default=text("false")` (`models.py`). CAL-P1004
made grading three-state via `graded_columns()`: when the venue has not
answered, it returns an EMPTY mapping so that neither column is written. That is
exactly right on an UPDATE and exactly wrong on an INSERT — `**{}` contributes
no column, the default fires, and the row being born is recorded as a **declared
loss on a market the venue is still trading**. `ON CONFLICT DO NOTHING` protects
every row that already existed and does nothing at all for that one.

## why nothing cheaper catches it

An omitted column and an explicit `None` **compile to the same SQL** as far as
the caller can see, and the divergence is produced by the defaulting machinery
at execute time. So the question "what is actually stored?" is not answerable by
reading the statement, by asserting on source text, or by a mock session — a
mock records the values the caller passed and therefore agrees with the caller
by construction. Only a server that owns the column default can be asked.

This column has already caused one total, silent production failure by this
exact mechanism: #2199's futures price writer resolved outcomes with
`is_winner IS NULL` against the same non-nullable defaulting column and matched
0 of 10,804 rows — permanently, with 19,906 tests green. Its gate is the
"Futures price writer contract" step in this same CI job. This file is that
lesson applied to the write side rather than the read side.

There is no local Postgres in the agent sandbox (`initdb` fails on `shmget`), so
**CI is the environment that runs this**, and the job's step carries the same
skip-detection as every gate around it — pytest exits 0 when everything skips,
and a gate that silently did not run reads exactly like one that passed.

## the negative control

`test_the_unrepaired_insert_stores_a_false_the_venue_never_declared` executes
the ORIGINAL statement shape (the `**graded_cols` splat) against the same server
and requires it to store `False`. A green run therefore means the repair was
proved NECESSARY, not merely that nothing objected.
"""

from __future__ import annotations

import os
from datetime import timedelta
from unittest.mock import MagicMock

import pytest
from sqlalchemy import text
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.models.models import FuturesMarket, FuturesOutcome
from app.services.kalshi_api import KalshiEvent, KalshiMarket
from app.tasks.kalshi import _create_settled_market, _GAP_CREATE_START
from app.utils.market_label_normalization import compute_market_tier

DB_URL = os.environ.get("SEARCH_TEST_DATABASE_URL")

VENUE_SOURCE = "api_settlement"

pytestmark = [
    pytest.mark.asyncio,
    pytest.mark.skipif(
        not DB_URL,
        reason=(
            "set SEARCH_TEST_DATABASE_URL to run the real-Postgres gap-create "
            "grade round trip (CI job `search-recall` provides one)"
        ),
    ),
]


@pytest.fixture
async def pg_session():
    """Real Postgres with the real schema.

    Function-scoped, following `test_tag_counts_real_postgres.py`: `pytest.ini`
    leaves `asyncio_default_fixture_loop_scope` unset, so a module-scoped async
    fixture would outlive the loop that created its engine.
    """
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    import app.models.models  # noqa: F401 — registers every table on Base
    from app.services.database import Base

    engine = create_async_engine(DB_URL)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)

    Session = async_sessionmaker(engine, expire_on_commit=False)
    async with Session() as session:
        yield session

    await engine.dispose()


def _event(status, result, ticker):
    """One Kalshi event inside the gap window, carrying a single market."""
    return KalshiEvent(
        event_ticker=ticker,
        title="Some tennis match",
        category="Tennis",
        mutually_exclusive=True,
        markets=[
            KalshiMarket(
                ticker=f"{ticker}-A",
                event_ticker=ticker,
                title="A",
                yes_sub_title="Alcaraz",
                status=status,
                close_time=_GAP_CREATE_START + timedelta(days=10),
                last_price=0.62,
                result=result,
                volume=1500,
            )
        ],
    )


async def _create(session, ticker, status, result):
    """Drive the REAL gap-create path and commit what it wrote."""
    svc = MagicMock()
    svc._parse_event = MagicMock(return_value=_event(status, result, ticker))
    stats = {"markets_created": 0, "outcomes_created": 0}

    outcome = await _create_settled_market(
        session, svc, {}, pg_insert,
        FuturesMarket, FuturesOutcome, compute_market_tier, stats,
    )
    assert outcome == "created", f"{ticker}: gap-create returned {outcome!r}"
    assert stats["outcomes_created"] == 1
    await session.commit()


async def _stored_grade(session, ticker):
    """Read the pair back out of the SERVER, not out of the ORM identity map."""
    return (
        await session.execute(
            text(
                "SELECT is_winner, resolution_source FROM futures_outcomes "
                "WHERE external_id = :t"
            ),
            {"t": f"{ticker}-A"},
        )
    ).one()


# --------------------------------------------------------------------------
# The round trip CERT-948 named, and its two controls.
# --------------------------------------------------------------------------


async def test_still_trading_market_stores_null_not_a_loss(pg_session):
    """`status=active, result=""` — the venue has not answered.

    This is the assertion CERT-948 asked for by name. Before the repair the row
    came back `False`: a loss declared by our own column default on a market
    Kalshi was still trading.
    """
    await _create(pg_session, "KXP1004R-ACTIVE", "active", "")
    is_winner, source = await _stored_grade(pg_session, "KXP1004R-ACTIVE")

    assert is_winner is None, (
        f"stored is_winner is {is_winner!r}, expected None — an ungraded leg was "
        "recorded as a declared loss the venue never made (CERT-948)"
    )
    assert source is None, f"stored resolution_source is {source!r}, expected None"


async def test_finalized_yes_stores_the_win(pg_session):
    await _create(pg_session, "KXP1004R-YES", "finalized", "yes")
    is_winner, source = await _stored_grade(pg_session, "KXP1004R-YES")

    assert is_winner is True
    assert source == VENUE_SOURCE


async def test_finalized_no_stores_the_real_loss(pg_session):
    """The control that keeps the repair from becoming "never grade anything"."""
    await _create(pg_session, "KXP1004R-NO", "finalized", "no")
    is_winner, source = await _stored_grade(pg_session, "KXP1004R-NO")

    assert is_winner is False
    assert source == VENUE_SOURCE


async def test_scalar_result_is_not_a_loss(pg_session):
    """`result="scalar"` settles on a number, not a side.

    Production measures 47,795 `api_settlement`-sourced losing legs on OPEN
    markets; this state is how they acquired a source while never being graded.
    """
    await _create(pg_session, "KXP1004R-SCALAR", "finalized", "scalar")
    is_winner, source = await _stored_grade(pg_session, "KXP1004R-SCALAR")

    assert is_winner is None
    assert source is None


# --------------------------------------------------------------------------
# The negative control: the unrepaired shape, on the same server.
# --------------------------------------------------------------------------


async def test_the_unrepaired_insert_stores_a_false_the_venue_never_declared(
    pg_session,
):
    """Execute the ORIGINAL statement shape and require it to store the defect.

    Without this arm a green file would be consistent with "the default was
    never `false` in the first place", and the repair would be unfalsifiable.
    The splat below is verbatim what the code did before CAL-P1004R: an empty
    `graded_cols` contributes no column at all.
    """
    from app.utils.kalshi_market_status import graded_columns

    graded_cols = graded_columns("active", "")
    assert graded_cols == {}, (
        "this control assumes an ungraded venue answer yields an EMPTY mapping; "
        f"graded_columns() returned {graded_cols!r} and the control is stale"
    )

    market_id = (
        await pg_session.execute(
            pg_insert(FuturesMarket)
            .values(
                source="kalshi",
                external_id="KXP1004R-CONTROL",
                name="control market",
                status="resolved",
            )
            .returning(FuturesMarket.id)
        )
    ).scalar_one()

    await pg_session.execute(
        pg_insert(FuturesOutcome).values(
            market_id=market_id,
            external_id="KXP1004R-CONTROL-A",
            name="Alcaraz",
            current_probability=0.62,
            **graded_cols,
        )
    )
    await pg_session.commit()

    is_winner, source = await _stored_grade(pg_session, "KXP1004R-CONTROL")

    assert is_winner is False, (
        f"the unrepaired INSERT stored {is_winner!r}, not False — the column "
        "default this whole gate guards has changed, so re-read the file rather "
        "than deleting it"
    )
    assert source is None
