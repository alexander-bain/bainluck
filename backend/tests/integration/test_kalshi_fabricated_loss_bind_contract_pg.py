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


async def _seed_one_fabricated_loss_market(
    session, *, sport="baseball", ext="KXBIND-26"
):
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
            text("""
                INSERT INTO futures_markets
                    (name, source, category, mutually_exclusive, status,
                     resolution_date, external_id, llm_sport_category)
                VALUES
                    (:name, 'kalshi', 'championship', TRUE, 'resolved',
                     :resolved, :ext, :sport)
                RETURNING id
                """),
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
            text("""
                INSERT INTO futures_outcomes
                    (market_id, name, external_id, is_winner, resolution_source)
                VALUES (:mid, :name, :ext, FALSE, :source)
                """),
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

    assert [r.market_id for r in await _work(pg_session, sport="baseball")] == [
        baseball
    ]
    assert await _work(pg_session, sport="chess") == []
    assert len(await _work(pg_session)) == 2, "no shard means no filter"


async def test_the_cursor_this_rail_hands_back_is_one_it_accepts(pg_session):
    """The round trip, closed: `next_cursor` out, `?after_date=` in, and page two.

    The population is 63,733 legs at ``APPLY_MARKET_CAP`` markets a call, so the
    drain is nothing BUT paging — and this loop was open. ``keyset_after``
    emits ``after_date`` as ``date.isoformat()``, the route declares
    ``after_date: str``, and asyncpg refuses a ``str`` for a ``timestamptz``
    parameter rather than casting it (psycopg2 would have). Page one worked;
    page two died on ``DataError: invalid input for query argument``.

    So the assertion is the whole loop rather than a bind type: the cursor is
    taken FROM `keyset_after`, put through the REAL query-string decoder, then
    through `parse_cursor_date`, then executed. Nothing here restates a value
    the rail computed.

    CERT-1892 blocked the version of this test that skipped the decoder. A
    params dictionary is not a query string, and the character that was being
    eaten — `isoformat()`'s `+` — is eaten only by the transport. The test was
    green over a user path that could not work. `QueryParams` is the same class
    Starlette hands the route, so it is in the loop now; the route itself, with
    the cursor appended to a URL as text, is pinned in
    `tests/test_kalshi_fabricated_loss_cursor_transport_p1010.py`.
    """
    from starlette.datastructures import QueryParams

    from app.utils.repair_apply_plan import keyset_after

    def _through_the_query_string(value: str) -> str:
        return QueryParams(f"after_date={value}")["after_date"]

    first, _ = await _seed_one_fabricated_loss_market(pg_session, ext="KXBIND-P1")
    second, _ = await _seed_one_fabricated_loss_market(pg_session, ext="KXBIND-P2")

    page_one = await _work(pg_session, lim=1)
    assert [r.market_id for r in page_one] == [first]

    cursor = keyset_after(page_one, examined=1)
    assert cursor["after_id"] == first
    assert isinstance(
        cursor["after_date"], str
    ), "the emitted cursor is a STRING — that is the fact the parse exists for"
    assert (
        _through_the_query_string(cursor["after_date"]) == cursor["after_date"]
    ), "the cursor changed in transit, which is CERT-1892's defect"

    page_two = await _work(
        pg_session,
        lim=1,
        after_date=rail.parse_cursor_date(
            _through_the_query_string(cursor["after_date"])
        ),
        after_id=cursor["after_id"],
    )
    assert [r.market_id for r in page_two] == [
        second
    ], "the resume must advance past the row page one returned"

    exhausted = keyset_after(page_two, examined=1)
    assert (
        await _work(
            pg_session,
            lim=1,
            after_date=rail.parse_cursor_date(
                _through_the_query_string(exhausted["after_date"])
            ),
            after_id=exhausted["after_id"],
        )
        == []
    ), "the walk must end, not wrap"


async def test_a_hand_typed_date_is_accepted_and_a_broken_one_is_refused(pg_session):
    """The two shapes an operator actually types, and neither may be ignored.

    A naive date is what somebody pastes from the plan by hand; it is read as
    UTC. Anything unreadable is REFUSED by name — a cursor half silently
    dropped to ``None`` re-reads page one and reports it as a resume, which is
    the `?offset=` bug rebuilt one level down.
    """
    first, _ = await _seed_one_fabricated_loss_market(pg_session, ext="KXBIND-H1")
    await _seed_one_fabricated_loss_market(pg_session, ext="KXBIND-H2")

    naive = rail.parse_cursor_date("2000-01-01T00:00:00")
    assert naive.tzinfo is not None, "asyncpg wants the tzinfo explicit"
    rows = await _work(pg_session, after_date=naive, after_id=0)
    assert len(rows) == 2, "a floor before both rows must return both"

    with pytest.raises(ValueError):
        rail.parse_cursor_date("page two please")

    out = await rail.repair(
        pg_session, apply=False, after_date="page two please", after_id=first
    )
    assert out["refused"] == "CURSOR_DATE_UNPARSEABLE"
    assert out["measured"] is False


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
