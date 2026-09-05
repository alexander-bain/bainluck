"""The fabricated-loss drain's bind contract, against a REAL asyncpg connection.

Why this file exists, and why 19,000 green unit tests were not enough
---------------------------------------------------------------------
`repair_kalshi_fabricated_loss` is the drain for #1852/#2528 — 63,733 Kalshi legs
carrying a fabricated ``is_winner = false``, which is why those cards sum to
~1,500% instead of 100%. It was built 2026-08-14, certified twice (C-CERT-1852
and R2), and carries a large unit suite.

**Its endpoint had never completed a single work selection.** Measured against
production 2026-09-05, both unsharded and with ``?sport=``::

    POST /api/admin/repairs/kalshi-fabricated-loss?apply=false&limit=1
    -> "work selection did not complete: ProgrammingError:
        asyncpg.exceptions.AmbiguousParameterError:
        could not determine data type of parameter $1"   (0.1 s)

The line was::

    AND (:sport IS NULL OR fm.llm_sport_category = :sport)

asyncpg prepares a statement with **no parameter types**, so Postgres infers them
from the query text alone, and the FIRST occurrence of a parameter fixes its
type. ``$1 IS NULL`` fixes ``$1`` as ``unknown``; the later ``= $1`` cannot
re-resolve it; the prepare dies before a row is read — whatever value is bound.
That is why the keyset predicate two lines below it casts both halves, and why
every sibling rail writes ``:sport::text`` on BOTH sides
(``repair_polymarket_leg_label.py`` :457-458, :758). This one line did not.

Nothing in the unit suite could see it: the session doubles never prepare a
statement, so the WHERE clause never meets a type system. This file is the
boundary that can reject it — it executes the rail's real statements through the
real driver, so any future parameter this rail cannot type fails HERE rather than
on the first attended production run.

Opt-in on ``SEARCH_TEST_DATABASE_URL``, following the other real-Postgres
contracts; CI's ``search-recall`` job provides a Postgres 15 service and asserts
the gate did not silently skip.
"""

import os
from datetime import datetime, timedelta, timezone

import pytest

from app.tasks import repair_kalshi_fabricated_loss as rail
from app.utils.kalshi_fabricated_loss import REPAIRABLE_SOURCE
from app.utils.kalshi_retention import PROVABLY_PURGED_AGE_DAYS

DB_URL = os.environ.get("SEARCH_TEST_DATABASE_URL")

pytestmark = [
    pytest.mark.skipif(
        not DB_URL,
        reason=(
            "set SEARCH_TEST_DATABASE_URL to run the real-Postgres "
            "fabricated-loss bind contract (CI job `search-recall` provides one)"
        ),
    ),
    pytest.mark.asyncio,
]


@pytest.fixture
async def pg_session():
    """Real Postgres, real schema, real asyncpg parameter-type inference.

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


async def _seed_one_fabricated_loss_market(session, *, sport="baseball", ext="KXBIND-26"):
    """One market in the drain's population: 2 legs, no winner, all api_settlement.

    Raw ``text()`` INSERTs deliberately — this gate exists to exercise the
    driver's own type handling, and the ORM would adapt values on the way in.
    Python-side column defaults therefore do NOT apply, so every NOT NULL column
    with only a ``default=`` is supplied explicitly.
    """
    from sqlalchemy import text

    resolved = datetime.now(timezone.utc) - timedelta(days=PROVABLY_PURGED_AGE_DAYS - 5)
    market_id = (
        await session.execute(
            text(
                """
                INSERT INTO futures_markets
                    (name, source, category, mutually_exclusive, status,
                     resolution_date, external_id, llm_sport_category)
                VALUES
                    (:name, 'kalshi', 'championship', TRUE, 'resolved',
                     :resolved, :ext, :sport)
                RETURNING id
                """
            ),
            {
                "name": "Fabricated-loss bind contract market",
                "resolved": resolved,
                "ext": ext,
                "sport": sport,
            },
        )
    ).scalar()

    for leg in ("YES", "NO"):
        await session.execute(
            text(
                """
                INSERT INTO futures_outcomes
                    (market_id, name, external_id, is_winner, resolution_source)
                VALUES (:mid, :name, :ext, FALSE, :source)
                """
            ),
            {
                "mid": market_id,
                "name": leg.title(),
                "ext": f"{ext}-{leg}",
                "source": REPAIRABLE_SOURCE,
            },
        )

    await session.commit()
    return market_id, resolved


async def _work(session, **params):
    from sqlalchemy import text

    args = {"lim": 10, "sport": None, "after_date": None, "after_id": None}
    args.update(params)
    return (await session.execute(text(rail._WORK_SQL), args)).all()


async def test_the_unsharded_work_selection_executes_against_real_postgres(pg_session):
    """THE SPECIMEN. This is the call the runbook makes first.

    Pre-fix this raises ``AmbiguousParameterError`` on ``$1`` before a row is
    read, which is what the production endpoint did on 2026-09-05.
    """
    market_id, _ = await _seed_one_fabricated_loss_market(pg_session)

    rows = await _work(pg_session)

    assert [r.market_id for r in rows] == [market_id], (
        "the unsharded drain must select the fabricated-loss market. An "
        "exception here means a parameter this rail binds cannot be typed by "
        "Postgres; zero rows with no exception means the population predicate "
        "moved."
    )


async def test_the_sharded_work_selection_still_filters(pg_session):
    """The over-reach control: the cast must not turn the filter into a no-op.

    A cast that made ``:sport`` always match would be the cheapest way to pass
    the test above while quietly widening every attended run's scope.
    """
    baseball, _ = await _seed_one_fabricated_loss_market(
        pg_session, sport="baseball", ext="KXBIND-BASE"
    )
    await _seed_one_fabricated_loss_market(
        pg_session, sport="hockey", ext="KXBIND-HOCK"
    )

    assert [r.market_id for r in await _work(pg_session, sport="baseball")] == [baseball]
    assert await _work(pg_session, sport="chess") == []
    assert len(await _work(pg_session)) == 2, "no shard means no filter"


async def test_the_keyset_resume_executes_and_advances(pg_session):
    """Both halves of the cursor are bound together, and they are typed too.

    The keyset was already cast (`62e84233`); this holds that, and proves the
    resume walks forward rather than re-reading page one — the failure mode
    `?offset=` was retired for.
    """
    first, resolved = await _seed_one_fabricated_loss_market(
        pg_session, ext="KXBIND-P1"
    )
    second, _ = await _seed_one_fabricated_loss_market(pg_session, ext="KXBIND-P2")

    page_one = await _work(pg_session, lim=1)
    assert [r.market_id for r in page_one] == [first]

    page_two = await _work(
        pg_session, lim=1, after_date=resolved.isoformat(), after_id=first
    )
    assert [r.market_id for r in page_two] == [second], (
        "the resume must advance past the row page one returned"
    )


async def test_the_census_executes_against_real_postgres(pg_session):
    """The other statement the runbook opens with, on the same rail.

    It carries no parameters today, which is exactly why it belongs here: this
    file is the rail's bind surface, so a parameter added to the census later
    meets Postgres in CI rather than in an attended window.
    """
    from sqlalchemy import text

    await _seed_one_fabricated_loss_market(pg_session)

    rows = (await pg_session.execute(text(rail._CENSUS_SQL))).all()

    assert [r.source for r in rows] == ["kalshi"]
    assert rows[0].markets == 1 and int(rows[0].outcomes) == 2


async def test_the_per_market_leg_read_executes(pg_session):
    """`_legs` is what the plan is built from; its bind is typed by its column."""
    market_id, _ = await _seed_one_fabricated_loss_market(pg_session)

    legs = await rail._legs(pg_session, market_id)

    assert len(legs) == 2
    assert {leg.resolution_source for leg in legs} == {REPAIRABLE_SOURCE}
    assert not any(leg.is_winner for leg in legs)
