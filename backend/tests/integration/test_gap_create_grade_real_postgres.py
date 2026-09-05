"""Kalshi's two outcome-INSERT sites, executed against a REAL PostgreSQL.

CAL-P1004R (#1852, repairs CERT-948) and CAL-P1004R-BULK-INSERT-ROUND-TRIP (the
follow-up CERT-950 named). Both halves of the file do the same thing to a
different site: drive the real path with `status=active, result=""` and read the
stored row back out of the server, asserting `is_winner IS NULL` and
`resolution_source IS NULL`, with finalized yes/no controls beside it.

    site                                       driven by
    ---------------------------------------------------------------------
    `_create_settled_market` (gap-create)      the first half of this file
    `_poll_kalshi_markets`   (the bulk poll)   the second half

The poll's site is the file's HIGHEST-VOLUME creator of outcome rows and carried
the identical defect; it had only the AST census and the statement-shape tests
until the second half below, and — see "why nothing cheaper catches it" — those
read the statement, which is exactly the thing that cannot tell the two
behaviours apart. The filename predates the second half and is left alone: it is
the name the `search-recall` CI step's path argument uses.

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
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy import text
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.models.models import FuturesMarket, FuturesOutcome
from app.services.kalshi_api import KalshiEvent, KalshiMarket
from app.tasks.kalshi import (
    _create_settled_market,
    _GAP_CREATE_START,
    _poll_kalshi_markets,
)
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


# --------------------------------------------------------------------------
# CAL-P1004R-BULK-INSERT-ROUND-TRIP (the follow-up CERT-950 named by name).
#
# Everything above drives `_create_settled_market` — the GAP-CREATE site. The
# poll's own upsert (`_poll_kalshi_markets`, the `outcome_stmt` in the
# probability-ranked second pass) is the file's HIGHEST-VOLUME creator of
# outcome rows and carried the identical defect, and it had only the AST census
# and the statement-shape tests: both read the statement, and an omitted column
# and an explicit `None` compile to the same statement. So the bigger site was
# the one with no proof of what a real server actually stores.
#
# These arms drive the REAL poll — no re-stated statement, no hand-built value
# dict — with the venue's answer as the only input that varies. Everything
# between the fetch and the insert is production code: category classification,
# the crypto skip, `derive_resolution_window`, the market upsert, the price
# guard, the rank sort, `graded_columns`, and `on_conflict_do_update`.
# --------------------------------------------------------------------------


def _poll_market(event_ticker, suffix, status, result, name, price):
    return KalshiMarket(
        ticker=f"{event_ticker}-{suffix}",
        event_ticker=event_ticker,
        title=name,
        yes_sub_title=name,
        status=status,
        close_time=datetime.now(timezone.utc) + timedelta(days=10),
        # A tight two-sided book, so `_kalshi_yes_probability` takes the
        # midpoint and `has_real_trading` is True — the widest value set the
        # site ever builds, which is the one worth round-tripping.
        yes_bid=price - 0.01,
        yes_ask=price + 0.01,
        last_price=price,
        result=result,
        volume=1500,
    )


def _poll_event(event_ticker, legs):
    """One multi-market tennis event; `legs` are `(suffix, status, result, name)`."""
    return KalshiEvent(
        event_ticker=event_ticker,
        title="Some tennis match",
        category="Tennis",
        mutually_exclusive=True,
        markets=[
            _poll_market(event_ticker, suffix, status, result, name, price)
            for (suffix, status, result, name), price in zip(
                legs, (0.62, 0.51, 0.40, 0.30, 0.20)
            )
        ],
    )


async def _run_poll(session, events):
    """Run the REAL `_poll_kalshi_markets` against this Postgres session.

    Three seams, all of them the task's own boundaries rather than anything
    inside the write path:

    * `KalshiAPIService` — the network. `get_all_events` returns `events`.
    * `get_task_session` — the connection. Yields OUR session and does not
      close it, so the assertions can read the same server afterwards. The poll
      re-enters this CM in its post-loop fixups; re-yielding one session is
      correct for that.
    * `get_redis_client` — raised, so the poll's `_phase_rc` is `None` and every
      phase marker/cursor/discovery-cache call takes its own no-op branch. That
      makes the run deterministic in CI instead of dependent on whether a Redis
      happens to be reachable.
    """
    service = MagicMock()
    service.get_all_events = AsyncMock(return_value=events)
    service.close = AsyncMock()

    @asynccontextmanager
    async def _session_cm():
        yield session

    with patch(
        "app.services.kalshi_api.KalshiAPIService", return_value=service
    ), patch(
        "app.tasks.kalshi.get_task_session", _session_cm
    ), patch(
        "app.tasks.redis_state.get_redis_client",
        side_effect=RuntimeError("no Redis in this gate — take the None branch"),
    ), patch.dict(
        os.environ, {"KALSHI_API_KEY": "test-key"}
    ):
        stats = await _poll_kalshi_markets()

    # The poll swallows per-event and top-level failures into `stats["errors"]`
    # (it must: one bad event may not wipe a whole ingest). Unasserted, a gate
    # driving it would read a silently-skipped event as a passing round trip.
    assert stats["errors"] == [], f"the poll reported errors: {stats['errors']}"
    assert stats["events_processed"] == len(events), (
        f"the poll processed {stats['events_processed']}/{len(events)} events — "
        "the fixture never reached the upsert loop, so nothing below is a "
        f"round trip. stats: {stats}"
    )
    await session.commit()
    return stats


async def _stored_grade_by_id(session, external_id):
    return (
        await session.execute(
            text(
                "SELECT is_winner, resolution_source FROM futures_outcomes "
                "WHERE external_id = :t"
            ),
            {"t": external_id},
        )
    ).one()


async def test_poll_bulk_insert_stores_each_venue_answer_as_given(pg_session):
    """One real poll, three legs, three different venue answers.

    The three states share a single INSERT statement and differ only in what
    Kalshi said, so running them in one event is what proves the site is
    three-state rather than proving three separate code paths.
    """
    await _run_poll(
        pg_session,
        [
            _poll_event(
                "KXP1004RPOLL",
                [
                    ("ACTIVE", "active", "", "Alcaraz"),
                    ("YES", "finalized", "yes", "Sinner"),
                    ("NO", "finalized", "no", "Djokovic"),
                ],
            )
        ],
    )

    ungraded = await _stored_grade_by_id(pg_session, "KXP1004RPOLL-ACTIVE")
    assert ungraded == (None, None), (
        f"the poll's bulk INSERT stored {ungraded!r} for a leg Kalshi is still "
        "trading, expected (None, None) — this is the 47,795-row production "
        "shape being reproduced, not a test failure about naming"
    )

    assert await _stored_grade_by_id(pg_session, "KXP1004RPOLL-YES") == (
        True,
        VENUE_SOURCE,
    )
    # The control that keeps the repair from degenerating into "never grade":
    # a real venue-declared loss must still be stored as a loss.
    assert await _stored_grade_by_id(pg_session, "KXP1004RPOLL-NO") == (
        False,
        VENUE_SOURCE,
    )


async def test_poll_re_poll_of_an_ungraded_leg_never_invents_a_grade(pg_session):
    """The second beat is where the UPDATE arm runs; it must stay a no-op too.

    The INSERT arm is only half the site — `on_conflict_do_update` fires on
    every subsequent beat, which for a still-trading market is most of them.
    """
    event = _poll_event("KXP1004RREPOLL", [("ACTIVE", "active", "", "Alcaraz")])
    await _run_poll(pg_session, [event])
    assert await _stored_grade_by_id(pg_session, "KXP1004RREPOLL-ACTIVE") == (
        None,
        None,
    )

    await _run_poll(pg_session, [event])
    after = await _stored_grade_by_id(pg_session, "KXP1004RREPOLL-ACTIVE")
    assert after == (None, None), (
        f"re-polling an ungraded leg stored {after!r} — the conflict arm "
        "declared a grade the venue never gave"
    )


async def test_poll_grade_survives_a_later_ungraded_repoll(pg_session):
    """A settled grade must not be erased when a later beat sees no answer.

    Kalshi markets age out of the venue's market endpoint (gotcha #35), so a
    re-poll CAN return an ungraded shape for something already graded. Writing
    NULL over that would be the mirror-image defect of the one being fixed:
    three-state has to mean "don't write", not "write nothing-ness".
    """
    await _run_poll(
        pg_session,
        [_poll_event("KXP1004RKEEP", [("LEG", "finalized", "yes", "Sinner")])],
    )
    assert await _stored_grade_by_id(pg_session, "KXP1004RKEEP-LEG") == (
        True,
        VENUE_SOURCE,
    )

    await _run_poll(
        pg_session,
        [_poll_event("KXP1004RKEEP", [("LEG", "active", "", "Sinner")])],
    )
    after = await _stored_grade_by_id(pg_session, "KXP1004RKEEP-LEG")
    assert after == (True, VENUE_SOURCE), (
        f"an ungraded re-poll overwrote a settled grade with {after!r} — the "
        "empty mapping stopped meaning 'write nothing'"
    )


async def test_the_unrepaired_bulk_insert_stores_a_false_at_this_site_too(
    pg_session,
):
    """The negative control for the BULK site, on the same server.

    Without an arm that executes the unrepaired shape and sees the defect, the
    three arms above are consistent with "the column default was never `false`"
    and the gate is unfalsifiable.

    This mirrors the site exactly, including `on_conflict_do_update` — which is
    the point. CAL-P1004 had already fixed the conflict arm (`update_set` gets
    `**graded_cols`), and that repair does nothing here: the row does not exist
    yet, so the INSERT arm runs, the splat contributes no column, and the server
    default decides. A fixed UPDATE arm beside a defaulting INSERT arm is the
    whole shape of #1852's forward half.
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
                external_id="KXP1004RBULK-CONTROL",
                name="control market",
                status="open",
            )
            .returning(FuturesMarket.id)
        )
    ).scalar_one()

    await pg_session.execute(
        pg_insert(FuturesOutcome)
        .values(
            market_id=market_id,
            external_id="KXP1004RBULK-CONTROL-A",
            name="Alcaraz",
            current_probability=0.62,
            current_yes_bid=0.61,
            current_yes_ask=0.63,
            rank=1,
            **graded_cols,
        )
        .on_conflict_do_update(
            index_elements=["market_id", "external_id"],
            set_={"name": "Alcaraz", **graded_cols},
        )
    )
    await pg_session.commit()

    is_winner, source = await _stored_grade_by_id(
        pg_session, "KXP1004RBULK-CONTROL-A"
    )
    assert is_winner is False, (
        f"the unrepaired bulk INSERT stored {is_winner!r}, not False — the "
        "column default this gate guards has changed, so re-read the file "
        "rather than deleting it"
    )
    assert source is None
