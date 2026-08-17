"""The cliff drain's bind contract, against a REAL asyncpg connection (#1884).

Why this file exists, and why the unit suite was not enough
-----------------------------------------------------------
The drain shipped (#1875, master ``f6649764``, Heroku v3818) with 39 green unit
tests and threw ``asyncpg.exceptions.DataError`` on the first statement of every
single run. It bound its cold-start watermark as an ISO **string** into

    (fm.resolution_date, fo.id) > (:cursor_date, :cursor_id)

and ``fm.resolution_date`` is ``DateTime(timezone=True)``. Postgres infers that
parameter as ``timestamptz``; asyncpg refuses a ``str`` there rather than casting
it, which psycopg2 would have done silently. Production recorded 166 ms runs,
``outcomes_seen: 0``, ``fetch_errors: 0`` (it never reached a fetch), a ``failed``
terminal, and a watermark that never left ``None`` — permanently self-blocking,
because the cold path is the only path a never-advancing watermark can take.

Nothing in the unit suite could see it. The session double discarded ``params``
entirely, and the one watermark test that looked at the bind compared
``_cursor_params()["cursor_date"]`` against ``_EPOCH`` — the same constant the
production line binds. It restated the assignment, so it could not fail whatever
the type was.

The unit suite is now type-strict about this bind, which closes the specimen.
This file closes the CLASS: it executes the real SQL through the real driver, so
any future parameter whose Python type stops matching its column type fails here
regardless of what the doubles believe. A type contract is only worth what the
type system that enforces it is, and the enforcing type system is asyncpg's.

Opt-in on ``SEARCH_TEST_DATABASE_URL``, following the search contracts — CI's
``search-recall`` job provides a Postgres 15 service.
"""

import os
from datetime import datetime, timedelta, timezone

import pytest

from app.tasks import kalshi_cliff as drain
from app.utils.kalshi_retention import PROVABLY_PURGED_AGE_DAYS

DB_URL = os.environ.get("SEARCH_TEST_DATABASE_URL")

pytestmark = [
    pytest.mark.skipif(
        not DB_URL,
        reason=(
            "set SEARCH_TEST_DATABASE_URL to run the real-Postgres cliff-drain "
            "bind contract (CI job `search-recall` provides one)"
        ),
    ),
    pytest.mark.asyncio,
]


@pytest.fixture
async def pg_session():
    """Real Postgres, real schema, real asyncpg type coercion.

    Function-scoped: ``pytest.ini`` leaves ``asyncio_default_fixture_loop_scope``
    unset, so a module-scoped async fixture would outlive the event loop that
    created its engine.
    """
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    import app.models.models  # noqa: F401 — registers every table on Base
    from app.services.database import Base

    engine = create_async_engine(DB_URL)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)

    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as session:
        yield session

    await engine.dispose()


async def _seed_one_recoverable_outcome(
    session, *, age_days=None, ext="KXBINDCONTRACT-26"
):
    """One resolved Kalshi outcome inside the retention window, no snapshots.

    Inside the window and ahead of the epoch, so a working cold watermark
    selects it and a broken one cannot reach the question at all. ``age_days``
    places it precisely, which the at-risk band contracts below need in order
    to land on one side or the other of the grace edge.
    """
    from sqlalchemy import text

    if age_days is None:
        age_days = PROVABLY_PURGED_AGE_DAYS - 5
    settled = datetime.now(timezone.utc) - timedelta(days=age_days)
    # Raw `text()` INSERTs deliberately — this gate exists to exercise the
    # driver's own type coercion, and going through the ORM would let SQLAlchemy
    # adapt values on the way in, which is exactly the layer whose absence is
    # the defect.
    #
    # The cost of that choice: Python-side column defaults do NOT apply to a raw
    # INSERT, so every NOT NULL column with only a `default=` must be supplied
    # explicitly. `category` ('championship'), `mutually_exclusive` (True) and
    # `status` ('open') on futures_markets, and `is_winner` (False) on
    # futures_outcomes, are all in that class. CI found this on the first run.
    market_id = (
        await session.execute(
            text(
                """
                INSERT INTO futures_markets
                    (name, source, category, mutually_exclusive,
                     status, resolution_date, external_id)
                VALUES
                    (:name, 'kalshi', 'championship', TRUE,
                     'resolved', :settled, :ext)
                RETURNING id
                """
            ),
            {
                "name": "Cliff drain bind contract market",
                "settled": settled,
                "ext": ext,
            },
        )
    ).scalar()

    outcome_id = (
        await session.execute(
            text(
                """
                INSERT INTO futures_outcomes
                    (market_id, name, external_id, is_winner)
                VALUES (:mid, 'Yes', :ext, FALSE)
                RETURNING id
                """
            ),
            {"mid": market_id, "ext": f"{ext}-YES"},
        )
    ).scalar()

    await session.commit()
    return outcome_id, settled


async def test_the_cold_watermark_executes_against_real_postgres(pg_session):
    """The regression, at the only boundary that can actually reject it.

    On the shipped code this raises ``DataError: invalid input for query
    argument`` before returning a single row — the production failure, reproduced
    end to end rather than described.
    """
    from sqlalchemy import text

    outcome_id, _ = await _seed_one_recoverable_outcome(pg_session)

    rows = (
        await pg_session.execute(
            text(drain._COHORT_SQL),
            {
                "purge_days": PROVABLY_PURGED_AGE_DAYS,
                "limit": 10,
                **drain._cursor_params(drain._default_state()),
            },
        )
    ).fetchall()

    assert [r.outcome_id for r in rows] == [outcome_id], (
        "a cold-start drain must select the recoverable outcome. Zero rows "
        "here with no exception would mean the watermark is ahead of the "
        "cohort; an exception means the bind type is wrong again."
    )


async def test_a_warm_watermark_executes_and_pages_past_what_it_has_seen(
    pg_session,
):
    """The resumed path, which re-enters through a JSON string from Redis.

    Fixing only the epoch would have moved the failure from run 1 to run 2, so
    the warm bind gets its own real-driver execution rather than sharing the
    cold one's verdict.
    """
    from sqlalchemy import text

    outcome_id, settled = await _seed_one_recoverable_outcome(pg_session)

    # Exactly the shape run_cliff_drain persists: `resolution_date.isoformat()`.
    warm = drain._default_state()
    warm["cursor_date"] = settled.isoformat()
    warm["cursor_id"] = outcome_id

    rows = (
        await pg_session.execute(
            text(drain._COHORT_SQL),
            {
                "purge_days": PROVABLY_PURGED_AGE_DAYS,
                "limit": 10,
                **drain._cursor_params(warm),
            },
        )
    ).fetchall()

    assert rows == [], (
        "the watermark sits ON the only seeded row, so a correct strict-greater "
        "comparison returns nothing. Rows here would mean the drain re-serves "
        "what it has already examined — a rescan, not a drain."
    )


async def test_the_remaining_count_shares_the_bind_and_therefore_the_fix(
    pg_session,
):
    """`_count_remaining` binds the same cursor into the same comparison.

    It is the query whose ``DataError`` was visible in the admin endpoint's
    ``remaining`` block BEFORE the first beat ever fired — the reported symptom
    that named the root cause. It must be proven fixed on its own, not inferred
    from the cohort query passing.
    """
    from sqlalchemy import text

    await _seed_one_recoverable_outcome(pg_session)

    count = (
        await pg_session.execute(
            text(drain._REMAINING_SQL),
            {
                "purge_days": PROVABLY_PURGED_AGE_DAYS,
                "cap": drain._REMAINING_CAP,
                **drain._cursor_params(drain._default_state()),
            },
        )
    ).scalar()

    assert count == 1, (
        f"expected the one seeded recoverable outcome, got {count}. A null or "
        "an exception here is the `remaining: {'count': null, 'error': "
        "'...DataError...'}' the endpoint was reporting."
    )


# ==========================================================================
# Queue 359 (#1892): the at-risk pass, at the same real boundary
# ==========================================================================
#
# The at-risk pass is a SECOND watermark binding into the SAME timestamptz
# comparison, so it is a second chance to make #1884's bind. The unit suite is
# type-strict about it, but only asyncpg can reject the real thing — and only a
# real Postgres can reject a typo in the band predicate. Both queries are
# executed here for the same reason the cohort and remaining queries are: a
# type contract is worth what the type system enforcing it is.


async def test_the_at_risk_band_query_executes_against_real_postgres(pg_session):
    """A cold at-risk watermark selects an outcome inside the 74-86d band."""
    from sqlalchemy import text
    from app.utils.kalshi_retention import AT_RISK_AGE_DAYS

    outcome_id, _ = await _seed_one_recoverable_outcome(
        pg_session, age_days=PROVABLY_PURGED_AGE_DAYS - 5   # 81d — in the band
    )

    rows = (
        await pg_session.execute(
            text(drain._AT_RISK_SQL),
            {
                "purge_days": PROVABLY_PURGED_AGE_DAYS,
                "at_risk_days": AT_RISK_AGE_DAYS,
                "limit": 10,
                **drain._at_risk_cursor_params(drain._default_state()),
            },
        )
    ).fetchall()

    assert [r.outcome_id for r in rows] == [outcome_id], (
        "the at-risk pass must reach an outcome in the band. An exception here "
        "is #1884's bind made a second time; zero rows is a band predicate that "
        "excludes the population it names."
    )


async def test_the_at_risk_band_excludes_what_is_not_yet_at_risk(pg_session):
    """The ceiling is load-bearing: without it the 'at-risk' pass is just a
    second full sweep of the window competing with the main drain."""
    from sqlalchemy import text
    from app.utils.kalshi_retention import AT_RISK_AGE_DAYS

    await _seed_one_recoverable_outcome(
        pg_session, age_days=10, ext="KXBINDYOUNG-26"   # nowhere near the band
    )

    rows = (
        await pg_session.execute(
            text(drain._AT_RISK_SQL),
            {
                "purge_days": PROVABLY_PURGED_AGE_DAYS,
                "at_risk_days": AT_RISK_AGE_DAYS,
                "limit": 10,
                **drain._at_risk_cursor_params(drain._default_state()),
            },
        )
    ).fetchall()

    assert rows == []


async def test_the_at_risk_count_separates_a_backlog_from_a_loss(pg_session):
    """`ahead` is recoverable; `expiring_soon` has a deadline. One number for
    both would make the alarm fire on work that is merely queued."""
    from sqlalchemy import text
    from app.utils.kalshi_retention import AT_RISK_AGE_DAYS

    # 76d: in the band, comfortably clear of the grace edge (86 - 2 = 84d).
    await _seed_one_recoverable_outcome(
        pg_session, age_days=76, ext="KXBINDQUEUED-26"
    )
    # 85d: in the band AND past the grace edge — out of time.
    await _seed_one_recoverable_outcome(
        pg_session, age_days=85, ext="KXBINDDYING-26"
    )

    row = (
        await pg_session.execute(
            text(drain._AT_RISK_COUNT_SQL),
            {
                "purge_days": PROVABLY_PURGED_AGE_DAYS,
                "at_risk_days": AT_RISK_AGE_DAYS,
                "expiry_edge_days": (
                    PROVABLY_PURGED_AGE_DAYS - drain.AT_RISK_GRACE_DAYS
                ),
                **drain._at_risk_cursor_params(drain._default_state()),
            },
        )
    ).one()

    assert row.ahead == 2
    assert row.expiring_soon == 1
