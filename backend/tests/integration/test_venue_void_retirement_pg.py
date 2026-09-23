"""The void fact RETIRES the row, run against a REAL Postgres — #7035.

WHY THIS FILE EXISTS — CERT-3326 (BLOCK, 2026-09-23 05:35Z)
------------------------------------------------------------

    "The declared TRUTH ship remains false because the SHA has no runtime
    consumer of that fact outside the capture task ... event 15312871 therefore
    remains suspended/served and its card still says 'No result reported'."

The sibling file ``test_kalshi_resolved_void_selection_pg.py`` proves the
CAPTURE reaches the named families. This one proves the other half: that the
fact it writes MOVES A ROW. It seeds the specimen's shape, runs the real
consumer — :func:`_retire_venue_voided_suspended_rows`, the function the beat
calls — and reads ``events.status`` back.

🔴 THE STAMP IS WRITTEN BY THE CAPTURE'S OWN STATEMENT, NOT BY A FIXTURE.
Every arm that needs a voided row gets there by executing
:data:`VOID_UPDATE_SQL` — the exact SQL the sweep runs in production. A
hand-built ``{"venue_voided": True}`` literal would test the consumer against
the test author's belief about what the capture writes, which is the seam that
was missing in the first place: the capture stores a JSON *boolean*, and a
consumer comparing against the string ``'true'`` would pass such a fixture and
select nothing in production. Here the two halves meet on a real ``jsonb``
column and the contract is falsifiable in both directions.

It must be a real server: the fact lives in ``jsonb``, and the arm's write goes
through a backup table that only exists on Postgres.

THE CONTROL THAT MATTERS MOST
------------------------------

``test_the_arm_is_inert_before_the_capture_stamps`` runs the arm over the
specimen with everything true EXCEPT the stamp, and requires 0 retirements. It
is the negative half of the ship: without it, an arm that retired every
suspended Kalshi row would pass every other arm in this file.
"""

import os
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import text

from app.tasks.espn_sync import (
    UNREACHABLE_SUSPENDED_BACKUP_DDL,
    UNREACHABLE_SUSPENDED_BACKUP_TABLE,
    VENUE_VOIDED_SUSPENDED_MAX_PER_PASS,
    _retire_venue_voided_suspended_rows,
    unreachable_suspended_floor,
)
from app.tasks.kalshi_resolution_sweep import VOID_UPDATE_SQL
from app.utils.event_completion import UNREACHABLE_SUSPENDED_TERMINAL

DB_URL = os.environ.get("SEARCH_TEST_DATABASE_URL")

pytestmark = [
    pytest.mark.skipif(
        not DB_URL,
        reason=(
            "set SEARCH_TEST_DATABASE_URL to run the real-Postgres venue-void "
            "retirement contract (CI job `search-recall` provides one)"
        ),
    ),
    pytest.mark.asyncio,
]

#: Fixed, and every row OFFSETS from it — gotcha #44. No arm below contains an
#: `if` on the clock.
NOW = datetime(2026, 9, 23, 6, 0, tzinfo=timezone.utc)

FLOOR = unreachable_suspended_floor()

#: Past the floor by an hour: retirable on the clock, so any refusal an arm sees
#: is the screen it is actually testing.
PAST_FLOOR = NOW - FLOOR - timedelta(hours=1)

#: Inside the floor by an hour — the one control for the floor itself.
INSIDE_FLOOR = NOW - FLOOR + timedelta(hours=1)

#: 🔴 WHY EVERY CONTROL ASSERTS `screened == 0` AS WELL AS `retired == 0`.
#:
#: The arm is two layers — a SQL screen and a Python verdict — and the verdict
#: deliberately re-asks what the screen already asked (#6927's lesson: two copies
#: of one rule are not belt and braces if they hang from the same hook). The cost
#: of that design is that `retired == 0` alone cannot tell the two layers apart:
#: delete a conjunct from the screen and the verdict still refuses the row, so
#: every arm stays green while the arm silently loads and re-reads rows it should
#: never have touched. MEASURED: a mutation sweep of this file's first cut
#: reported 6 such survivors — one per screen conjunct.
#:
#: `screened` is the counter that separates them, so a control states BOTH: the
#: screen excluded this row, AND nothing retired it.
_SCREEN_NOTE = (
    "the SCREEN must exclude this row, not merely the verdict — otherwise a "
    "deleted WHERE clause is invisible to this file"
)


@pytest.fixture
async def pg_session():
    """Real Postgres, real schema, plus the arm's backup table.

    Function-scoped for the sibling's reason: ``pytest.ini`` leaves
    ``asyncio_default_fixture_loop_scope`` unset, so a module-scoped async
    fixture would outlive the loop that created its engine.

    The backup table is created from
    :data:`UNREACHABLE_SUSPENDED_BACKUP_DDL` — the same string the attended
    enable script executes — so this gate cannot pass against a table
    production does not get.
    """
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    import app.models.models  # noqa: F401 — registers every table on Base
    from app.services.database import Base

    engine = create_async_engine(DB_URL)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
        await conn.execute(
            text(f"DROP TABLE IF EXISTS {UNREACHABLE_SUSPENDED_BACKUP_TABLE}")
        )
        await conn.execute(text(UNREACHABLE_SUSPENDED_BACKUP_DDL))

    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as session:
        yield session

    await engine.dispose()


async def _sport(session, key="soccer_spain_la_liga"):
    """🔴 `events.sport_id` is an INTEGER FK to `sports.id`, not a sport key, and
    `sports.active` is NOT NULL with a PYTHON-side default a raw INSERT bypasses
    — both learned the hard way in CI (see the sibling gate's note)."""
    return (
        await session.execute(
            text("""
                INSERT INTO sports (key, name, active)
                VALUES (:key, 'La Liga', TRUE)
                ON CONFLICT (key) DO UPDATE SET name = EXCLUDED.name
                RETURNING id
                """),
            {"key": key},
        )
    ).scalar()


async def _event(
    session,
    *,
    status="suspended",
    commence=PAST_FLOOR,
    home_score=None,
    away_score=None,
    completed_at=None,
    sport_key="soccer_spain_la_liga",
):
    sport_id = await _sport(session, sport_key)
    return (
        await session.execute(
            text("""
                INSERT INTO events
                    (sport_id, home_team_name, away_team_name, commence_time,
                     status, home_score, away_score, completed_at)
                VALUES
                    (:sport, 'Levante', 'Bilbao', :commence, :status,
                     :home_score, :away_score, :completed_at)
                RETURNING id
                """),
            {
                "sport": sport_id,
                "commence": commence,
                "status": status,
                "home_score": home_score,
                "away_score": away_score,
                "completed_at": completed_at,
            },
        )
    ).scalar()


async def _market(
    session, *, event_id, ext, status="resolved", source="kalshi"
):
    return (
        await session.execute(
            text("""
                INSERT INTO futures_markets
                    (name, source, category, mutually_exclusive, status,
                     external_id, event_id, market_metadata)
                VALUES
                    (:name, :source, 'game_prop', TRUE, :status,
                     :ext, :event_id, NULL)
                RETURNING id
                """),
            {
                "name": f"Venue void retirement {ext}",
                "source": source,
                "status": status,
                "ext": ext,
                "event_id": event_id,
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


async def _capture_stamps_void(session, market_id):
    """Write the void fact THE WAY THE CAPTURE WRITES IT. See the module note.

    🔴 `updated_at` IS BOUND AS A STRING, because the capture binds
    `now.isoformat()` (`kalshi_resolution_sweep:1345`) into a
    `CAST(:updated_at AS text)`. Passing a `datetime` here raises
    `invalid input for query argument $1 ... (expected str, got datetime)` from
    asyncpg — which is the contract working: the cast fixes `$1`'s type, so the
    binding this gate uses has to be the binding production uses, and a fixture
    that guessed would be testing a statement the sweep never runs.
    """
    await session.execute(
        text(VOID_UPDATE_SQL), {"id": market_id, "updated_at": NOW.isoformat()}
    )


async def _specimen(session, *, legs=4, stamped=True, tag=None, **event_kwargs):
    """The production shape: one suspended event, four resolved Kalshi families,
    every leg ungraded, every family stamped by the capture.

    `tag` disambiguates the external ids when an arm seeds more than one
    specimen. `futures_markets` carries `uq_futures_source_external`, so two
    events built from the default ticker collide on the INSERT — which reads as
    an arm failing for its own reason rather than the rule's.
    """
    event_id = await _event(session, **event_kwargs)
    stem = f"KXLALIGAGAME-26SEP16LEVATH{'' if tag is None else f'-{tag}'}"
    for n in range(legs):
        market_id = await _market(session, event_id=event_id, ext=f"{stem}-{n}")
        await _leg(session, market_id=market_id, ext=f"{stem}-LEV-{n}")
        if stamped:
            await _capture_stamps_void(session, market_id)
    return event_id


async def _run(session):
    stats = await _retire_venue_voided_suspended_rows(session, NOW, FLOOR)
    await session.commit()
    return stats


async def _status(session, event_id):
    return (
        await session.execute(
            text("SELECT status FROM events WHERE id = :id"), {"id": event_id}
        )
    ).scalar()


async def _backup_rows(session):
    return (
        await session.execute(
            text(
                "SELECT event_id, previous_status FROM "
                f"{UNREACHABLE_SUSPENDED_BACKUP_TABLE} ORDER BY event_id"
            )
        )
    ).all()


# =============================================================================
# The ship: the fact moves the row.
# =============================================================================


class TestTheVoidFactRetiresTheRow:
    async def test_the_postponed_fixture_is_retired(self, pg_session):
        """CERT-3326's sentence, inverted: the row does NOT remain suspended."""
        event_id = await _specimen(pg_session)

        stats = await _run(pg_session)

        assert stats["venue_voided_suspended_retired"] == 1
        assert await _status(pg_session, event_id) == UNREACHABLE_SUSPENDED_TERMINAL

    async def test_the_retirement_is_backed_up_in_the_same_transaction(
        self, pg_session
    ):
        """D51: the arm cannot retire a row it would be unable to give back."""
        event_id = await _specimen(pg_session)

        await _run(pg_session)

        assert await _backup_rows(pg_session) == [(event_id, "suspended")]

    async def test_the_arm_is_inert_before_the_capture_stamps(self, pg_session):
        """🔴 THE CONTROL THAT CARRIES THE FILE.

        Everything about this row is the specimen except that the capture has
        not answered yet. An arm that retired every suspended Kalshi row would
        pass every other arm here and fail this one.
        """
        event_id = await _specimen(pg_session, stamped=False)

        stats = await _run(pg_session)

        assert stats["venue_voided_suspended_screened"] == 1, (
            "the screen must REACH the row — a refusal that happens because the "
            "screen missed it proves nothing about the verdict"
        )
        assert stats["venue_voided_suspended_retired"] == 0
        assert await _status(pg_session, event_id) == "suspended"

    async def test_one_unstamped_family_holds_the_whole_event(self, pg_session):
        """EVERY market, not any. At the venue, 10 of 14 sampled rows in this
        population were graded, so "any leg voided" would retire played games."""
        event_id = await _event(pg_session)
        for n, stamp in enumerate((True, True, True, False)):
            market_id = await _market(
                pg_session, event_id=event_id, ext=f"KXLALIGAGAME-MIXED-{n}"
            )
            await _leg(pg_session, market_id=market_id, ext=f"MIX-{n}")
            if stamp:
                await _capture_stamps_void(pg_session, market_id)

        stats = await _run(pg_session)

        assert stats["venue_voided_suspended_screened"] == 1, (
            "every market IS kalshi+resolved, so the screen selects this row — "
            "it is the VERDICT's `every_market_venue_voided` that must refuse it"
        )
        assert stats["venue_voided_suspended_retired"] == 0
        assert await _status(pg_session, event_id) == "suspended"


# =============================================================================
# The controls. Each differs from the specimen in exactly one thing.
# =============================================================================


class TestTheControlsItMustRefuse:
    async def test_a_played_game_is_refused(self, pg_session):
        """THE PLAYED RESOLVED CONTROL the cert asked for, kept whole: a
        `completed` event whose Kalshi families are resolved and stamped. On
        production 2,843 completed events hold resolved rows with no graded leg
        — identical to the specimen on every other axis — and retiring one would
        put "never played" on a game that was."""
        event_id = await _specimen(pg_session, status="completed")

        stats = await _run(pg_session)

        assert stats["venue_voided_suspended_screened"] == 0, _SCREEN_NOTE
        assert stats["venue_voided_suspended_retired"] == 0
        assert await _status(pg_session, event_id) == "completed"

    async def test_a_graded_outcome_of_ours_is_refused(self, pg_session):
        """The contradiction test: a winner says a result WAS reported."""
        event_id = await _event(pg_session)
        market_id = await _market(
            pg_session, event_id=event_id, ext="KXLALIGAGAME-GRADED"
        )
        await _leg(pg_session, market_id=market_id, ext="GRADED", is_winner=True)
        await _capture_stamps_void(pg_session, market_id)

        stats = await _run(pg_session)

        assert stats["venue_voided_suspended_screened"] == 0, _SCREEN_NOTE
        assert stats["venue_voided_suspended_retired"] == 0
        assert await _status(pg_session, event_id) == "suspended"

    async def test_an_open_market_of_another_source_holds_the_row(self, pg_session):
        """A Polymarket row still open is a door still standing, whatever Kalshi
        said. This is why the screen asks "no market that ISN'T kalshi+resolved"
        rather than "some kalshi resolved market exists"."""
        event_id = await _event(pg_session)
        kalshi = await _market(
            pg_session, event_id=event_id, ext="KXLALIGAGAME-WITHPOLY"
        )
        await _leg(pg_session, market_id=kalshi, ext="POLYSIB")
        await _capture_stamps_void(pg_session, kalshi)
        await _market(
            pg_session,
            event_id=event_id,
            ext="0xdeadbeef",
            status="open",
            source="polymarket",
        )

        stats = await _run(pg_session)

        assert stats["venue_voided_suspended_screened"] == 0, _SCREEN_NOTE
        assert stats["venue_voided_suspended_retired"] == 0
        assert await _status(pg_session, event_id) == "suspended"

    async def test_a_kalshi_market_still_open_holds_the_row(self, pg_session):
        """🔴 THE `resolved` HALF OF THE SCREEN, AND IT HAD NO CONTROL.

        A surviving mutant found this: replacing
        `~and_(source == 'kalshi', status == 'resolved')` with the shorter
        `source != 'kalshi'` passed every arm in this file. The polymarket
        control above exercises the SOURCE half only — under that mutant a
        foreign row is still excluded — so nothing was left holding the STATUS
        half, and an event with an open Kalshi market would have been selected.

        The row is stamped on purpose, so the verdict cannot save the screen: if
        the screen admits it, `every_market_venue_voided` is True and the arm
        RETIRES a fixture whose market the venue has not finished. That is the
        one case the capture's own docstring says must stay re-askable — "a
        NON-terminal answer is stamped with neither, so a market the venue has
        not finished is re-asked".
        """
        event_id = await _event(pg_session)
        market_id = await _market(
            pg_session,
            event_id=event_id,
            ext="KXLALIGAGAME-STILLOPEN",
            status="open",
        )
        await _leg(pg_session, market_id=market_id, ext="STILLOPEN")
        await _capture_stamps_void(pg_session, market_id)

        stats = await _run(pg_session)

        assert stats["venue_voided_suspended_screened"] == 0, _SCREEN_NOTE
        assert stats["venue_voided_suspended_retired"] == 0
        assert await _status(pg_session, event_id) == "suspended"

    async def test_an_event_with_no_markets_is_refused(self, pg_session):
        """The vacuous case. `all()` over an empty list is True, and a legless
        row would otherwise read as "every market voided" — a row the venue was
        never asked about. The sibling arm owns that population, not this one."""
        event_id = await _event(pg_session)

        stats = await _run(pg_session)

        assert stats["venue_voided_suspended_screened"] == 0
        assert stats["venue_voided_suspended_retired"] == 0
        assert await _status(pg_session, event_id) == "suspended"

    async def test_a_row_inside_the_floor_is_refused(self, pg_session):
        """Inside `SUSPENDED_RESUME_WINDOW` the resume arm can still re-select
        this row, and retiring one it is about to resume is a race this rule
        would lose."""
        event_id = await _specimen(pg_session, commence=INSIDE_FLOOR)

        stats = await _run(pg_session)

        assert stats["venue_voided_suspended_screened"] == 0, _SCREEN_NOTE
        assert stats["venue_voided_suspended_retired"] == 0
        assert await _status(pg_session, event_id) == "suspended"

    async def test_a_row_carrying_a_score_is_refused(self, pg_session):
        """Measured 0 across the whole candidate population, and this is what
        keeps that true: a row that acquired a result between the census and the
        write refutes the premise directly."""
        event_id = await _specimen(pg_session, home_score=0, away_score=0)

        stats = await _run(pg_session)

        assert stats["venue_voided_suspended_screened"] == 0, _SCREEN_NOTE
        assert stats["venue_voided_suspended_retired"] == 0
        assert await _status(pg_session, event_id) == "suspended"

    async def test_a_row_carrying_a_completed_at_is_refused(self, pg_session):
        event_id = await _specimen(
            pg_session, completed_at=NOW - timedelta(hours=3)
        )

        stats = await _run(pg_session)

        assert stats["venue_voided_suspended_screened"] == 0, _SCREEN_NOTE
        assert stats["venue_voided_suspended_retired"] == 0
        assert await _status(pg_session, event_id) == "suspended"

    async def test_the_negative_stamp_does_not_retire(self, pg_session):
        """"We asked and the venue named a result" is the OPPOSITE fact, and it
        is truthy. A consumer testing `if md.get(...)` instead of `is True`
        would retire on it."""
        from app.tasks.kalshi_resolution_sweep import VOID_CHECKED_UPDATE_SQL

        event_id = await _event(pg_session)
        market_id = await _market(
            pg_session, event_id=event_id, ext="KXLALIGAGAME-CHECKED"
        )
        await _leg(pg_session, market_id=market_id, ext="CHECKED")
        await pg_session.execute(
            text(VOID_CHECKED_UPDATE_SQL), {"id": market_id, "updated_at": NOW.isoformat()}
        )

        stats = await _run(pg_session)

        assert stats["venue_voided_suspended_screened"] == 1
        assert stats["venue_voided_suspended_retired"] == 0
        assert await _status(pg_session, event_id) == "suspended"


class TestTheVoidReadItself:
    """`_row_markets_all_venue_voided` direct, because the arm's screen hides
    two of its rules from every test that goes through the arm.

    Both arms here were SURVIVING MUTANTS of the first cut. The screen's
    `any_market` clause means a legless event never reaches the read, so
    deleting the read's own emptiness test changed nothing observable; and no
    control carried a `venue_voided` that was present-but-not-boolean, so
    swapping `is True` for a truth test changed nothing either. A rule the arm
    cannot exercise still has to be right — the screen is allowed to change.
    """

    async def test_an_event_with_no_markets_is_not_vacuously_voided(
        self, pg_session
    ):
        """`all()` over an empty list is True. Without the emptiness test, "we
        never priced this" would read as "the venue declined to grade it"."""
        from app.tasks.espn_sync import _row_markets_all_venue_voided

        event_id = await _event(pg_session)

        assert await _row_markets_all_venue_voided(pg_session, event_id) is False

    async def test_a_string_valued_stamp_is_not_the_fact(self, pg_session):
        """🔴 PRESENT BUT NOT BOOLEAN. The capture writes a JSON boolean today,
        so no production row looks like this — which is exactly why the identity
        test needs a control that is not a production row. If another writer
        ever merges `{"venue_voided": "true"}` into this column, a truthy read
        would retire the event on a value nothing in this codebase promises.
        """
        from app.tasks.espn_sync import _row_markets_all_venue_voided

        event_id = await _event(pg_session)
        market_id = await _market(
            pg_session, event_id=event_id, ext="KXLALIGAGAME-STRINGY"
        )
        await _leg(pg_session, market_id=market_id, ext="STRINGY")
        await pg_session.execute(
            text(
                "UPDATE futures_markets SET market_metadata = "
                "CAST(:md AS jsonb) WHERE id = :id"
            ),
            {"md": '{"venue_voided": "true"}', "id": market_id},
        )

        assert await _row_markets_all_venue_voided(pg_session, event_id) is False

        stats = await _run(pg_session)
        assert stats["venue_voided_suspended_retired"] == 0
        assert await _status(pg_session, event_id) == "suspended"

    async def test_the_real_stamp_reads_true(self, pg_session):
        """The positive control for the two arms above: the same helper, on the
        same shape, answers True once the capture's own statement has run. A
        refusal that is really a helper always returning False would pass both
        arms above and fail this one."""
        from app.tasks.espn_sync import _row_markets_all_venue_voided

        event_id = await _event(pg_session)
        market_id = await _market(
            pg_session, event_id=event_id, ext="KXLALIGAGAME-REALSTAMP"
        )
        await _leg(pg_session, market_id=market_id, ext="REALSTAMP")
        await _capture_stamps_void(pg_session, market_id)

        assert await _row_markets_all_venue_voided(pg_session, event_id) is True


# =============================================================================
# The rails: the restore gate and the bound.
# =============================================================================


class TestTheRailsHold:
    async def test_no_backup_table_means_no_retirement(self, pg_session):
        """The gate is a gate, not a log. Behavioural because a source scan
        cannot tell a `to_regclass` that fires from one that is never reached."""
        event_id = await _specimen(pg_session)
        await pg_session.execute(
            text(f"DROP TABLE {UNREACHABLE_SUSPENDED_BACKUP_TABLE}")
        )

        stats = await _run(pg_session)

        assert stats["venue_voided_suspended_retired"] == 0
        assert stats["venue_voided_suspended_screened"] == 0
        assert await _status(pg_session, event_id) == "suspended"

    async def test_the_pass_is_bounded(self, pg_session):
        """One more event than the cap, all retirable. The bound is the only
        blast-radius limit this arm has, so it must be a real one."""
        for n in range(VENUE_VOIDED_SUSPENDED_MAX_PER_PASS + 1):
            event_id = await _event(
                pg_session, commence=PAST_FLOOR - timedelta(minutes=n)
            )
            market_id = await _market(
                pg_session, event_id=event_id, ext=f"KXLALIGAGAME-BULK-{n}"
            )
            await _leg(pg_session, market_id=market_id, ext=f"BULK-{n}")
            await _capture_stamps_void(pg_session, market_id)

        stats = await _run(pg_session)

        assert (
            stats["venue_voided_suspended_retired"]
            == VENUE_VOIDED_SUSPENDED_MAX_PER_PASS
        )

    async def test_the_drain_is_oldest_first(self, pg_session):
        """Oldest first: the fixture a reader has been staring at longest is the
        one to fix first, and newest-first starves the tail (gotcha #41).

        🔴 THE CLOCK ORDER IS THE REVERSE OF THE INSERT ORDER, DELIBERATELY. The
        whole pass shares one transaction, so every `retired_at` is the same
        instant and any ordering assertion over the ledger tie-breaks on
        `event_id` — which, seeded naively, agrees with `commence_time` and the
        arm passes whichever way it sorts. Here the NEWEST fixtures get the
        LOWEST ids, so a `.desc()` mutation (or no ordering at all) retires the
        wrong set and this fails. `cap + 1` rows make the bound do the choosing.
        """
        cap = VENUE_VOIDED_SUSPENDED_MAX_PER_PASS
        by_age = {}
        for n in range(cap + 1):
            # n = 0 is the NEWEST and is inserted first, so it holds the lowest
            # event_id. The oldest row is inserted last and has the highest.
            event_id = await _specimen(
                pg_session, tag=f"AGE{n}", commence=PAST_FLOOR - timedelta(days=n)
            )
            by_age[n] = event_id

        await _run(pg_session)

        retired = {row[0] for row in await _backup_rows(pg_session)}

        # The oldest `cap` of them, which is every row except the newest.
        assert retired == {by_age[n] for n in range(1, cap + 1)}
        assert by_age[0] not in retired

    async def test_a_second_pass_is_idempotent(self, pg_session):
        """The row leaves the screen permanently once retired — it is no longer
        `suspended` — so the arm does not re-read or re-write it."""
        await _specimen(pg_session)

        first = await _run(pg_session)
        second = await _run(pg_session)

        assert first["venue_voided_suspended_retired"] == 1
        assert second["venue_voided_suspended_screened"] == 0
        assert second["venue_voided_suspended_retired"] == 0
