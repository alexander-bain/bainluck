"""#7035's already-resolved void SELECTION, against a REAL Postgres server.

WHY THIS FILE EXISTS — CERT-3324 (BLOCK, 2026-09-23 04:04Z)
-----------------------------------------------------------

The first presentation of #7035 shipped a correct classifier, a correct write,
and a guard that handed the specimen to :func:`run_backfill` directly. The cert
refused it, and the finding was right:

    "both sweep selection arms require ``futures_markets.status='open'``, while
    the four named Levante–Athletic families are already resolved ... Its
    composed guard injects the specimen after selection, so classifier/write
    correctness cannot make the existing postponed-game card acquire
    ``market_metadata.venue_voided``."

A guard that supplies its own rows can only ever prove that the code downstream
of the selection works. It cannot see that the selection reaches nothing. So the
subject of this file is :data:`RESOLVED_VOID_SELECT_SQL` ITSELF, executed by
Postgres against seeded rows — the one seam the blocked presentation had no test
for.

It must be a real server: the predicate screens on ``market_metadata->>'…'``
against a ``jsonb`` column, which SQLite cannot answer at all, so the unit suite
is structurally unable to host this check.

THE POPULATION, MEASURED BEFORE THE PREDICATE WAS WRITTEN
---------------------------------------------------------

Production, 2026-09-23 04:2xZ, the exact statement below:

* **489** candidate rows over **324** events in the 14-day band, 0 legless;
* the four ids CERT-3324 named — 60481773, 60636796, 60636798, 60636800
  (``KX{LALIGAGAME,LALIGATOTAL,LALIGASPREAD,LALIGABTTS}-26SEP16LEVATH``,
  Levante v Bilbao, event 15312871 ``suspended``) — are all four inside it;
* the venue agrees the fixture voided: all three legs of the moneyline read
  ``status='finalized'``, ``result='scalar'``.

Every arm below is one screen of that statement, and each control is a row that
differs from the specimen in exactly one column.
"""

import os
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import text

from app.tasks.kalshi_resolution_sweep import (
    RESOLVED_VOID_SELECT_SQL,
    SUSPENDED_EVENT_WINDOW_HOURS,
)

DB_URL = os.environ.get("SEARCH_TEST_DATABASE_URL")

pytestmark = [
    pytest.mark.skipif(
        not DB_URL,
        reason=(
            "set SEARCH_TEST_DATABASE_URL to run the real-Postgres resolved-void "
            "selection contract (CI job `search-recall` provides one)"
        ),
    ),
    pytest.mark.asyncio,
]

#: Fixed, and offset from it rather than truncated — gotcha #44. No arm below
#: may contain an `if` on the clock.
NOW = datetime(2026, 9, 23, 4, 0, tzinfo=timezone.utc)

#: Inside the band by a week; the floor is 14 days.
RECENT = NOW - timedelta(days=7)

#: Outside it by a week, on the same side of no other screen.
STALE = NOW - timedelta(hours=SUSPENDED_EVENT_WINDOW_HOURS + 168)

SUSPENDED_FLOOR = NOW - timedelta(hours=SUSPENDED_EVENT_WINDOW_HOURS)


@pytest.fixture
async def pg_session():
    """Real Postgres, real schema. Function-scoped for the sibling's reason.

    ``pytest.ini`` leaves ``asyncio_default_fixture_loop_scope`` unset, so a
    module-scoped async fixture would outlive the loop that created its engine.
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


async def _sport(session):
    """🔴 `events.sport_id` is an INTEGER FK to `sports.id`, NOT a sport key.

    The first cut of this file passed `'soccer_spain_la_liga'` — the string the
    rest of the codebase calls a sport_id everywhere else — and every one of the
    14 arms died in CI with `TypeError: 'str' object cannot be interpreted as an
    integer`, raised from asyncpg's `int4_encode` four frames below anything
    under test. Neither local instrument could see it: the PG gate skips on a
    PG14 server, and the reduced-table proof beside it has no `sports` table to
    join, so it never carried the column at all.

    `active` is named explicitly for the reason this file's enrolment in
    `test_pg_gate_seed_completeness.py` exists: it is NOT NULL with a
    PYTHON-side default, which a raw INSERT bypasses. The completeness check
    reads `server_default`, so a column defaulted in the ORM alone does not
    appear in its required list — it is a hazard that survives the guard.
    """
    return (await session.execute(text("""
                INSERT INTO sports (key, name, active)
                VALUES ('soccer_spain_la_liga', 'La Liga', TRUE)
                ON CONFLICT (key) DO UPDATE SET name = EXCLUDED.name
                RETURNING id
                """))).scalar()


async def _event(session, *, status, commence=RECENT):
    sport_id = await _sport(session)
    return (
        await session.execute(
            text("""
                INSERT INTO events
                    (sport_id, home_team_name, away_team_name, commence_time, status)
                VALUES (:sport, 'Levante', 'Bilbao', :commence, :status)
                RETURNING id
                """),
            {"sport": sport_id, "commence": commence, "status": status},
        )
    ).scalar()


async def _market(
    session,
    *,
    event_id,
    ext,
    status="resolved",
    metadata=None,
    source="kalshi",
):
    """One Kalshi row. ``market_metadata`` is CAST because an untyped NULL into a
    ``jsonb`` column is an inference failure before any row is read — the same
    hazard the sibling bind contract is about, one layer down."""
    return (
        await session.execute(
            text("""
                INSERT INTO futures_markets
                    (name, source, category, mutually_exclusive, status,
                     external_id, event_id, market_metadata)
                VALUES
                    (:name, :source, 'game_prop', TRUE, :status,
                     :ext, :event_id, CAST(:metadata AS jsonb))
                RETURNING id
                """),
            {
                "name": f"Resolved void selection {ext}",
                "source": source,
                "status": status,
                "ext": ext,
                "event_id": event_id,
                "metadata": metadata,
            },
        )
    ).scalar()


async def _leg(session, *, market_id, ext, is_winner=None):
    await session.execute(
        text("""
            INSERT INTO futures_outcomes (market_id, external_id, name, is_winner)
            VALUES (:market_id, :ext, :ext, :is_winner)
            """),
        {"market_id": market_id, "ext": ext, "is_winner": is_winner},
    )


async def _selected(session, *, limit=60):
    rows = (
        await session.execute(
            text(RESOLVED_VOID_SELECT_SQL),
            {"suspended_floor": SUSPENDED_FLOOR, "limit": limit},
        )
    ).all()
    return [r[0] for r in rows]


async def _specimen(session, ext="KXLALIGAGAME-26SEP16LEVATH", **market_kwargs):
    """The shape CERT-3324 named: resolved row, suspended event, ungraded leg."""
    event_id = await _event(session, status="suspended")
    market_id = await _market(session, event_id=event_id, ext=ext, **market_kwargs)
    await _leg(session, market_id=market_id, ext=f"{ext}-LEV")
    return market_id


class TestTheSelectionReachesTheNamedShape:
    async def test_the_postponed_fixture_is_selected(self, pg_session):
        """🔴 THE ARM CERT-3324 SAID DID NOT EXIST.

        A resolved Kalshi row on a suspended event, no leg graded, never
        checked. Under the shipped selections this row is unreachable — both
        open with ``fm.status = 'open'`` — and the capture could never run on
        it however correct the classifier was.
        """
        market_id = await _specimen(pg_session)

        assert await _selected(pg_session) == [market_id]

    async def test_all_four_legs_of_one_postponed_family_are_selected(self, pg_session):
        """The named specimen is a FAMILY, and the arm is per-market.

        CERT-3324 named four market ids on one event. A predicate that reached
        the moneyline and missed its siblings would leave the same page half
        explained, so the event is seeded once and carries all four.
        """
        event_id = await _event(pg_session, status="suspended")
        expected = []
        for series in ("GAME", "TOTAL", "SPREAD", "BTTS"):
            ext = f"KXLALIGA{series}-26SEP16LEVATH"
            market_id = await _market(pg_session, event_id=event_id, ext=ext)
            await _leg(pg_session, market_id=market_id, ext=f"{ext}-LEV")
            expected.append(market_id)

        assert sorted(await _selected(pg_session)) == sorted(expected)


class TestTheControlsItMustRefuse:
    async def test_a_played_game_we_have_not_graded_yet_is_refused(self, pg_session):
        """🔴 THE CONTROL THE CERT ASKED FOR, AND THE ONE THAT MATTERS MOST.

        Identical to the specimen on every axis the predicate reads except
        ``events.status``: resolved Kalshi row, no leg graded, inside the band.
        Production holds **2,843** such rows over 712 completed events — "played,
        not yet graded".

        Stamping one ``venue_voided`` would tell a reader no result was ever
        reported about a game that was played and won. The event status is the
        only thing that separates the two populations before the venue is asked,
        which is why it is a SCREEN and not an ordering.
        """
        event_id = await _event(pg_session, status="completed")
        market_id = await _market(
            pg_session, event_id=event_id, ext="KXLALIGAGAME-26SEP16PLAYED"
        )
        await _leg(pg_session, market_id=market_id, ext="PLAYED-LEV")

        assert await _selected(pg_session) == []

    async def test_a_row_we_have_already_graded_is_refused(self, pg_session):
        """A reported result is the opposite of the fact this arm captures."""
        event_id = await _event(pg_session, status="suspended")
        market_id = await _market(
            pg_session, event_id=event_id, ext="KXLALIGAGAME-26SEP16GRADED"
        )
        await _leg(pg_session, market_id=market_id, ext="GRADED-LEV", is_winner=True)

        assert await _selected(pg_session) == []

    async def test_a_row_with_no_legs_at_all_is_refused(self, pg_session):
        """ "We never priced this" is not "nobody reported a result".

        Without the ``EXISTS`` screen the ungraded test passes VACUOUSLY here.
        Measured 0 such rows in production today; the arm is written against the
        shape, not against today's count.
        """
        event_id = await _event(pg_session, status="suspended")
        await _market(pg_session, event_id=event_id, ext="KXLALIGAGAME-26SEP16LEGLESS")

        assert await _selected(pg_session) == []

    async def test_an_open_row_is_left_to_the_arm_that_owns_it(self, pg_session):
        """This arm is the complement of the other three, not a widening.

        A ``status='open'`` row on a suspended event is exactly what
        ``RECENT_FINAL_SELECT_SQL``'s suspended arm selects. Both arms taking it
        would double the venue reads and race two write policies onto one row.
        """
        event_id = await _event(pg_session, status="suspended")
        market_id = await _market(
            pg_session, event_id=event_id, ext="KXLALIGAGAME-26SEP16OPEN", status="open"
        )
        await _leg(pg_session, market_id=market_id, ext="OPEN-LEV")

        assert await _selected(pg_session) == []

    async def test_a_fixture_older_than_the_band_is_refused(self, pg_session):
        """The leash. Nothing else would ever retire a stuck event from this
        selection, and the venue purges the markets behind it anyway."""
        event_id = await _event(pg_session, status="suspended", commence=STALE)
        market_id = await _market(
            pg_session, event_id=event_id, ext="KXLALIGAGAME-25SEP16STALE"
        )
        await _leg(pg_session, market_id=market_id, ext="STALE-LEV")

        assert await _selected(pg_session) == []

    async def test_a_non_kalshi_row_is_refused(self, pg_session):
        """The classifier reads a Kalshi payload shape; the screen says so.

        🔴 THE TICKER IS `KX`-PREFIXED ON PURPOSE, and the first draft of this
        arm was vacuous for want of that. Written with a realistic Polymarket
        id (`0xdeadbeef`) the row is refused by the `LIKE 'KX%'` screen as well,
        so the arm passed with `fm.source = 'kalshi'` DELETED — a mutation sweep
        of the predicate reported that screen SURVIVED. A control must differ
        from the specimen in exactly the one screen it is aiming at, even when
        the resulting row could not occur in production.
        """
        event_id = await _event(pg_session, status="suspended")
        market_id = await _market(
            pg_session,
            event_id=event_id,
            ext="KXLALIGAGAME-26SEP16NOTKALSHI",
            source="polymarket",
        )
        await _leg(pg_session, market_id=market_id, ext="POLY-LEV")

        assert await _selected(pg_session) == []

    async def test_a_legacy_non_kx_ticker_is_refused(self, pg_session):
        """The other half of the pair above, isolating the prefix screen."""
        event_id = await _event(pg_session, status="suspended")
        market_id = await _market(
            pg_session, event_id=event_id, ext="LALIGA-LEGACY-26SEP16"
        )
        await _leg(pg_session, market_id=market_id, ext="LEGACY-LEV")

        assert await _selected(pg_session) == []


class TestItAsksEachRowOnce:
    """The idempotency screen, and it is what makes the arm affordable.

    A 14-ticker venue sample of this exact population answered 4 voided / 10
    graded. With no durable record of the refusal, ~71% of a 489-row band would
    be re-read every 10 minutes for 14 days — the jam CAL-P998 measured, where a
    row that gets no write never rotates.
    """

    async def test_a_row_already_stamped_voided_is_not_asked_again(self, pg_session):
        await _specimen(pg_session, metadata='{"venue_voided": true}')

        assert await _selected(pg_session) == []

    async def test_a_row_already_stamped_checked_is_not_asked_again(self, pg_session):
        await _specimen(
            pg_session,
            metadata='{"venue_void_checked_at": "2026-09-23T04:00:00+00:00"}',
        )

        assert await _selected(pg_session) == []

    async def test_other_metadata_does_not_retire_a_row(self, pg_session):
        """🔴 THE STRAWMAN THIS PAIR NEEDS.

        Both screens above are ``IS NULL`` tests on ONE key of a jsonb blob. A
        predicate that read "has any metadata" instead would pass both arms
        above and silently refuse every row carrying a ``shape`` — which is most
        of them. This is the arm that fails if either screen is widened to the
        column.
        """
        market_id = await _specimen(
            pg_session, metadata='{"shape": {"side_kind": "team"}}'
        )

        assert await _selected(pg_session) == [market_id]


class TestTheBatchIsBounded:
    async def test_the_limit_is_honoured(self, pg_session):
        """It rides #4655's 10-minute beat and must never be why that beat is
        late. The bound is the statement's, not the caller's good manners."""
        event_id = await _event(pg_session, status="suspended")
        for n in range(5):
            ext = f"KXLALIGAGAME-26SEP16BOUND{n}"
            market_id = await _market(pg_session, event_id=event_id, ext=ext)
            await _leg(pg_session, market_id=market_id, ext=f"{ext}-LEV")

        assert len(await _selected(pg_session, limit=3)) == 3

    async def test_the_oldest_unexplained_fixture_is_served_first(self, pg_session):
        """Ordered by kick-off ASC: the postponement a reader has been staring
        at the longest is the one still unexplained the longest."""
        ids = []
        for days in (2, 9, 5):
            event_id = await _event(
                pg_session, status="suspended", commence=NOW - timedelta(days=days)
            )
            ext = f"KXLALIGAGAME-26SEP16AGE{days}"
            market_id = await _market(pg_session, event_id=event_id, ext=ext)
            await _leg(pg_session, market_id=market_id, ext=f"{ext}-LEV")
            ids.append((days, market_id))

        selected = await _selected(pg_session)
        by_age = [market_id for days, market_id in sorted(ids, reverse=True)]
        assert selected == by_age
