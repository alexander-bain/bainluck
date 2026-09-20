"""#7501's fill against a REAL PostgreSQL, because the ladder is a UNIQUE index.

## what a reader saw, on production

`/sport/football/ncaaf/team/georgia-bulldogs` (read 2026-09-20) renders

    We don't have a football page for Georgia Bulldogs.

while `GET /api/teams/15263` serves that club's 3-0 record, its crest, five
recent games, five upcoming and 23 futures. The route resolves a team page
through `Team.slug == identifier` and the row's slug is NULL. 4,004 of 9,917
team rows (40.4%) are in that shape; 855 of them cannot take their clean
name-slug because a club in another sport already holds it.

## why a real server and not a session double

Every interesting thing the filler does is a claim about Postgres:

* **the collision itself.** `teams.slug` is UNIQUE. The 855-row cohort exists
  *because* of that index, and a double that records an UPDATE has no index to
  refuse it — every row would take rung 1 and the test would pass while the
  production run aborted on its first batch.
* **the SAVEPOINT.** A rejected candidate has to cost its own row and nothing
  else. Whether `begin_nested()` actually isolates an `IntegrityError` from the
  other 499 rows in the batch is a property of the driver and the server, not of
  our `for` loop; a fake raises or does not raise on command.
* **`WHERE slug IS NULL` as the idempotency key.** Two passes racing is a
  transaction-visibility question.
* **the bank's column types.** #6215's class: the CTAS derives `slug_after` from
  `teams.slug`, and `text` vs `varchar(200)` is the same characters to a double
  (#3672, CERT-2880).
* **the bank as the PRECONDITION of the write** (CERT-3171). "Writes nothing
  when the bank is absent" is a claim about what reached the column, and
  `to_regclass`, the `ON CONFLICT` arbiter and the savepoint that keeps the slug
  and its undo record atomic are all server behaviour. A double asked whether a
  table exists answers whatever it was told to.

## what is deliberately not asserted here

The ladder's *content* — which string each rung composes — is unit-graded in
`tests/test_team_slug_ladder_7501.py`, including the migration-token trap. This
file only asks which rung a row lands on when the index pushes it there.
"""

import argparse
import os

import pytest
from sqlalchemy import text

from app.tasks.team_slug_backfill import BANK_TABLE, fill_missing_team_slugs
from scripts.repair_7501_clubs_without_a_slug_have_no_page import ensure_bank
from scripts.restore_7501_clubs_without_a_slug_have_no_page import (
    _RESTORABLE_SQL,
    _RESTORE_SQL,
)

DB_URL = os.environ.get("SEARCH_TEST_DATABASE_URL")

pytestmark = pytest.mark.skipif(
    not DB_URL,
    reason=(
        "set SEARCH_TEST_DATABASE_URL to run the real-Postgres #7501 slug fill "
        "(CI job `search-recall` provides one)"
    ),
)


@pytest.fixture
async def pg_session():
    """Real Postgres with the real schema.

    Function-scoped for the reason `test_backup_round_trip_jsonb_6215_pg` gives:
    `pytest.ini` leaves `asyncio_default_fixture_loop_scope` unset, so a
    module-scoped async fixture would outlive the loop that made its engine.
    """
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    from app.models.models import Sport, Team
    from app.services.database import Base

    # DROP the whole schema, CREATE only the two tables this ship touches.
    #
    # The asymmetry is deliberate and both halves were measured. `search-recall`
    # shares ONE database across ~55 gates, so a subset `drop_all` raises
    # `DependentObjectsStillExistError: constraint events_home_team_id_fkey on
    # table events depends on table teams` against whatever the previous gate
    # left behind — only the full graph knows the drop order. And a subset
    # `create_all` skips the DDL that needs PostgreSQL 15 (`NULLS NOT DISTINCT`,
    # on `container_provider_anchors`), so this file also stands up on a
    # PostgreSQL 14 to hand — which is how the filler's `remaining` KeyError was
    # found before a runner reported it as a red deploy gate.
    #
    # Dropping everything also resets the `sports` sequence, which is why the
    # seeds below can let the serial fire instead of naming explicit ids the way
    # #6221 and #7147 had to.
    tables = [Sport.__table__, Team.__table__]

    engine = create_async_engine(DB_URL)
    async with engine.begin() as conn:
        await conn.execute(text(f"DROP TABLE IF EXISTS {BANK_TABLE}"))
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all, tables=tables)

    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as session:
        yield session

    async with engine.begin() as conn:
        await conn.execute(text(f"DROP TABLE IF EXISTS {BANK_TABLE}"))
    await engine.dispose()


async def _sport(session, key: str) -> int:
    return (
        await session.execute(
            text(
                "INSERT INTO sports (key, name, active) "
                "VALUES (:k, :k, true) RETURNING id"
            ),
            {"k": key},
        )
    ).scalar_one()


async def _team(session, name: str, sport_id: int, slug: str | None = None) -> int:
    return (
        await session.execute(
            text(
                "INSERT INTO teams (name, sport_id, slug) "
                "VALUES (:n, :s, :g) RETURNING id"
            ),
            {"n": name, "s": sport_id, "g": slug},
        )
    ).scalar_one()


async def _slug_of(session, team_id: int) -> str | None:
    return (
        await session.execute(
            text("SELECT slug FROM teams WHERE id = :i"), {"i": team_id}
        )
    ).scalar_one()


@pytest.fixture
async def world(pg_session):
    """Four clubs across four leagues, arranged to force each rung.

    `Manchester City` three times is production's actual shape: a club appears
    once per competition it plays in, one row takes the clean slug, and the
    others are the cohort this ship is about.

    THE BANK IS PART OF THE WORLD because it is the precondition of every write:
    after CERT-3171 the fill refuses outright without it, so a ladder test that
    omitted it would be asserting the refusal path four different ways and
    reading as four green rung tests. `TestTheBank` is where its absence is the
    subject; everywhere else its presence is the premise.
    """
    await ensure_bank(pg_session)
    epl = await _sport(pg_session, "soccer_epl")
    ucl = await _sport(pg_session, "soccer_uefa_champs_league")
    ncaaf = await _sport(pg_session, "americanfootball_ncaaf")
    champ = await _sport(pg_session, "soccer_efl_champ")

    ids = {
        # Rung 1: nothing holds `georgia-bulldogs`. The reader's own specimen.
        "georgia": await _team(pg_session, "Georgia Bulldogs", ncaaf),
        # Already slugged by the May migration — must not move.
        "city_epl": await _team(
            pg_session, "Manchester City", epl, "manchester-city"
        ),
        # Rung 2: rung 1 is taken by the row above.
        "city_ucl": await _team(pg_session, "Manchester City", ucl),
        # Rung 2 again, on an UNMAPPED three-part key, where the migration's
        # token (`champ`) and the URL's segment (`efl_champ`) disagree.
        "city_champ": await _team(pg_session, "Manchester City", champ),
        # Rung 3: both name rungs taken.
        "hull": await _team(pg_session, "Hull City", epl),
    }
    await _team(pg_session, "Hull City", ncaaf, "hull-city")
    await _team(pg_session, "Hull City Reserves", ncaaf, "hull-city-epl")
    await pg_session.commit()
    return ids


class TestTheRungTheIndexPushesARowTo:
    async def test_a_pageless_club_takes_the_clean_slug(self, pg_session, world):
        await fill_missing_team_slugs(pg_session)
        assert await _slug_of(pg_session, world["georgia"]) == "georgia-bulldogs"

    async def test_a_taken_name_falls_to_the_url_league_segment(
        self, pg_session, world
    ):
        """And NOT to `manchester-city-league`, which is what the migration
        wrote for this exact row and what `/sport/soccer/ucl/team/...` cannot
        reach. Both arms, because the positive one alone would pass on any
        non-colliding suffix."""
        await fill_missing_team_slugs(pg_session)
        got = await _slug_of(pg_session, world["city_ucl"])
        assert got == "manchester-city-ucl"
        assert got != "manchester-city-league"

    async def test_the_unmapped_three_part_key_uses_the_whole_tail(
        self, pg_session, world
    ):
        await fill_missing_team_slugs(pg_session)
        got = await _slug_of(pg_session, world["city_champ"])
        assert got == "manchester-city-efl_champ"
        assert got != "manchester-city-champ"

    async def test_both_name_rungs_taken_falls_to_the_id(self, pg_session, world):
        await fill_missing_team_slugs(pg_session)
        assert await _slug_of(pg_session, world["hull"]) == f"hull-city-{world['hull']}"

    async def test_an_already_slugged_row_never_moves(self, pg_session, world):
        """The fill is additive. A live URL changing as a side effect of a
        backfill is the one regression this ship could cause, and `WHERE slug IS
        NULL` is what forecloses it."""
        await fill_missing_team_slugs(pg_session)
        assert await _slug_of(pg_session, world["city_epl"]) == "manchester-city"

    async def test_one_collision_does_not_cost_the_batch(self, pg_session, world):
        """The SAVEPOINT's whole job. Four rows are slugged in one pass, and
        three of them only get there by surviving a rejected candidate."""
        stats = await fill_missing_team_slugs(pg_session)
        assert stats["written"] == 4
        assert stats["errors"] == 0
        assert stats["unresolved"] == 0


class TestTheRowTheLadderCannotPlace:
    async def test_it_stays_null_and_is_counted_not_guessed(self, pg_session):
        """Every rung taken, including the two carrying the row's own id — only
        reachable by squatting on the id after the insert, which is what makes
        `unresolved` a report rather than a normal outcome."""
        await ensure_bank(pg_session)
        sport = await _sport(pg_session, "soccer_epl")
        other = await _sport(pg_session, "americanfootball_ncaaf")
        stuck = await _team(pg_session, "Squatted FC", sport)
        for taken in (
            "squatted-fc",
            "squatted-fc-epl",
            f"squatted-fc-{stuck}",
            f"team-{stuck}",
        ):
            await _team(pg_session, f"decoy {taken}", other, taken)
        await pg_session.commit()

        stats = await fill_missing_team_slugs(pg_session)
        assert stats["unresolved"] == 1
        assert stats["written"] == 0
        assert await _slug_of(pg_session, stuck) is None


class TestRunningItTwice:
    async def test_the_second_pass_writes_nothing(self, pg_session, world):
        first = await fill_missing_team_slugs(pg_session)
        second = await fill_missing_team_slugs(pg_session)
        assert first["written"] == 4
        assert second["written"] == 0
        assert second["examined"] == 0
        assert second["remaining"] == 0

    async def test_the_dry_run_reports_the_plan_and_writes_nothing(
        self, pg_session, world
    ):
        planned = await fill_missing_team_slugs(pg_session, dry_run=True)
        assert dict(planned["pairs"])[world["city_ucl"]] == "manchester-city-ucl"
        assert await _slug_of(pg_session, world["city_ucl"]) is None

        applied = await fill_missing_team_slugs(pg_session)
        assert planned["pairs"] == applied["pairs"]


class TestTheBankIsThePreconditionOfEveryWrite:
    """CERT-3171. The bank is not bookkeeping beside the write — it is what
    makes an unattended production write permissible at all (D51(b)), so its
    absence has to stop the write rather than downgrade it."""

    async def _unbanked_world(self, pg_session):
        """`world` establishes the bank, which is exactly what these tests must
        not have. Seeded here instead of dropping the table afterwards: a test
        whose premise is arranged by undoing a fixture passes if the undo
        silently fails."""
        ncaaf = await _sport(pg_session, "americanfootball_ncaaf")
        georgia = await _team(pg_session, "Georgia Bulldogs", ncaaf)
        await pg_session.commit()
        assert (
            await pg_session.execute(text(f"SELECT to_regclass('{BANK_TABLE}')"))
        ).scalar_one() is None
        return georgia

    async def test_the_fill_refuses_and_writes_nothing_with_no_bank(self, pg_session):
        """The defect CERT-3171 named. The beat fires at :05/:25/:45 and would
        have slugged 500 clubs a pass before anyone created the bank — rows that
        are, by construction, the ones the restore can never reach.

        Asserted on the COLUMN, not on the returned counter: a stats dict saying
        `written: 0` is the claim under test, so trusting it would be circular."""
        georgia = await self._unbanked_world(pg_session)

        stats = await fill_missing_team_slugs(pg_session)

        assert stats["refused"], "the pass proceeded with no bank behind it"
        assert BANK_TABLE in stats["refused"]
        assert await _slug_of(pg_session, georgia) is None
        assert stats["written"] == 0
        assert stats["banked"] is False
        # Still reported honestly, so the beat's WARNING names the backlog it is
        # sitting on rather than reading as a drained queue.
        assert stats["remaining"] == 1

    async def test_the_refusal_creates_no_table_of_its_own(self, pg_session):
        """A beat that fixed its own precondition would be running DDL as a
        consequence of a release, which is migration-class (notice 47(c)) and
        the reason the refusal exists rather than a `CREATE TABLE` here."""
        await self._unbanked_world(pg_session)
        await fill_missing_team_slugs(pg_session)
        assert (
            await pg_session.execute(text(f"SELECT to_regclass('{BANK_TABLE}')"))
        ).scalar_one() is None

    async def test_a_dry_run_needs_no_bank(self, pg_session):
        """It writes nothing, so it has nothing to undo. Without this arm the
        refusal could be implemented as a blanket early return and the operator
        would lose the plan that tells them what the apply will do."""
        georgia = await self._unbanked_world(pg_session)
        planned = await fill_missing_team_slugs(pg_session, dry_run=True)
        assert planned["refused"] is None
        assert dict(planned["pairs"])[georgia] == "georgia-bulldogs"
        assert await _slug_of(pg_session, georgia) is None

    async def test_the_bank_covers_every_single_successful_write(
        self, pg_session, world
    ):
        """EXACT coverage, both directions — not a count. A bank holding four
        rows for four writes can still be four wrong rows, and the restore joins
        on `t.slug = b.slug_after`, so a bank row naming a slug its club does not
        wear is an undo that silently declines."""
        stats = await fill_missing_team_slugs(pg_session)
        assert stats["written"] == 4

        banked = dict(
            (
                await pg_session.execute(
                    text(f"SELECT team_id, slug_after FROM {BANK_TABLE}")
                )
            ).all()
        )
        assert banked == dict(stats["pairs"])
        # And every banked pair is the value the club actually carries.
        for team_id, slug_after in banked.items():
            assert await _slug_of(pg_session, team_id) == slug_after

    async def test_a_refill_after_a_restore_rebanks_the_new_slug(
        self, pg_session, world
    ):
        """`ON CONFLICT DO NOTHING` leaves the FIRST fill's value in the bank
        here, and the restore joins on `t.slug = b.slug_after` — so the bank
        reads full, the undo reports nothing to do, and the club is stranded
        with a slug no one can take back.

        The sequence is production's, not a contrivance: the restore does NOT
        delete what it restores (by design — it is the record of what was
        written), the beat fires three times an hour, and a refill can land on a
        different rung than the one that was banked because the restore freed
        the rung above it. Here `manchester-city` falls free, and the fill takes
        rows newest-id first, so the EFL Championship row reaches it before the
        UCL row does and moves off the `manchester-city-efl_champ` it banked.
        """
        await fill_missing_team_slugs(pg_session)
        banked_first = (
            await pg_session.execute(
                text(f"SELECT slug_after FROM {BANK_TABLE} WHERE team_id = :i"),
                {"i": world["city_champ"]},
            )
        ).scalar_one()
        assert banked_first == "manchester-city-efl_champ"

        # The real undo, then the clean name falls free.
        await pg_session.execute(text(_RESTORE_SQL))
        await pg_session.execute(
            text("UPDATE teams SET slug = NULL WHERE id = :i"),
            {"i": world["city_epl"]},
        )
        await pg_session.commit()

        await fill_missing_team_slugs(pg_session)

        # The premise, asserted rather than assumed: the refill really did move
        # a banked club onto a different rung, so ON CONFLICT was reached.
        assert await _slug_of(pg_session, world["city_champ"]) == "manchester-city"

        rows = (
            await pg_session.execute(
                text(f"SELECT team_id, slug_after FROM {BANK_TABLE}")
            )
        ).all()
        for team_id, slug_after in rows:
            assert await _slug_of(pg_session, team_id) == slug_after

        # And the consequence that matters: the undo can still reach every one
        # of them. Five now — the four the first fill wrote plus the EPL row
        # that fell free and was slugged by the refill.
        assert len(rows) == 5
        assert (await pg_session.execute(text(_RESTORABLE_SQL))).scalar_one() == 5

    async def test_the_bank_row_and_the_slug_land_together_or_not_at_all(
        self, pg_session, world
    ):
        """Atomicity, proven by breaking the bank rather than by reading the
        code: a bank whose `slug_after` cannot hold the value makes the INSERT
        raise INSIDE the savepoint, and the club must come back out NULL rather
        than slugged-but-unrecorded."""
        await pg_session.execute(
            text(f"ALTER TABLE {BANK_TABLE} ADD COLUMN must_be_set integer NOT NULL")
        )
        await pg_session.commit()

        stats = await fill_missing_team_slugs(pg_session)

        assert stats["written"] == 0
        assert await _slug_of(pg_session, world["georgia"]) is None
        assert (
            await pg_session.execute(text(f"SELECT count(*) FROM {BANK_TABLE}"))
        ).scalar_one() == 0


class TestTheOperatorPath:
    """The repair script's own gate, driven end to end against the real server.

    Graded here rather than as a unit on `missing_backup_refusal` because the
    claim is "zero writes", and a pure-argument test cannot tell a refusal that
    returns early from one that returns after the loop.
    """

    @staticmethod
    def _driving(monkeypatch, pg_session):
        """Point the script's session factory at this test's database, and stand
        it on the producer app so the app gate (which fires first on an unset
        `HEROKU_APP_NAME`) cannot be what refuses."""
        import contextlib

        import app.tasks.base as task_base

        monkeypatch.setenv("HEROKU_APP_NAME", "bainluck")

        @contextlib.asynccontextmanager
        async def _session():
            yield pg_session

        monkeypatch.setattr(task_base, "get_task_session", _session)

    async def test_apply_without_backup_refuses_and_writes_nothing(
        self, pg_session, monkeypatch
    ):
        from scripts.repair_7501_clubs_without_a_slug_have_no_page import run

        ncaaf = await _sport(pg_session, "americanfootball_ncaaf")
        georgia = await _team(pg_session, "Georgia Bulldogs", ncaaf)
        await pg_session.commit()
        self._driving(monkeypatch, pg_session)

        code = await run(argparse.Namespace(apply=True, backup=False))

        assert code == 2
        assert await _slug_of(pg_session, georgia) is None
        assert (
            await pg_session.execute(text(f"SELECT to_regclass('{BANK_TABLE}')"))
        ).scalar_one() is None

    async def test_backup_then_apply_banks_and_fills(
        self, pg_session, monkeypatch, world
    ):
        """The positive control. Without it the test above passes on a script
        that refuses everything."""
        from scripts.repair_7501_clubs_without_a_slug_have_no_page import run

        self._driving(monkeypatch, pg_session)

        code = await run(argparse.Namespace(apply=True, backup=True))

        assert code == 0
        assert await _slug_of(pg_session, world["georgia"]) == "georgia-bulldogs"
        assert (
            await pg_session.execute(text(f"SELECT count(*) FROM {BANK_TABLE}"))
        ).scalar_one() == 4

    async def test_backup_creates_the_bank_even_with_nothing_left_to_fill(
        self, pg_session, monkeypatch
    ):
        """`--backup` is what unblocks the beat, and the beat's job outlives
        today's backlog — every club `upsert_team` mints is born slug-less. A
        `--backup` that returned early on an empty backlog would leave the beat
        refusing forever on tomorrow's rows."""
        from scripts.repair_7501_clubs_without_a_slug_have_no_page import run

        ncaaf = await _sport(pg_session, "americanfootball_ncaaf")
        await _team(pg_session, "Georgia Bulldogs", ncaaf, "georgia-bulldogs")
        await pg_session.commit()
        self._driving(monkeypatch, pg_session)

        code = await run(argparse.Namespace(apply=False, backup=True))

        assert code == 0
        assert (
            await pg_session.execute(text(f"SELECT to_regclass('{BANK_TABLE}')"))
        ).scalar_one() is not None


class TestTheBank:
    """Its shape, and the undo it exists to serve. `ensure_bank` is idempotent,
    so the calls below are redundant with `world` and kept because each test
    should read as the sequence an operator actually runs."""

    async def test_the_banks_columns_are_the_teams_columns(self, pg_session, world):
        """#6215's class (CERT-2880): a hand-declared backup column that
        disagrees with what it backs up makes `--backup` raise, `--apply` refuse
        for want of a backup, and the repair dead on arrival while reading
        perfectly well. The CTAS is what prevents it; this is what holds it."""
        await ensure_bank(pg_session)
        types = dict(
            (
                await pg_session.execute(
                    text(
                        "SELECT column_name, data_type FROM information_schema.columns "
                        "WHERE table_name = :t"
                    ),
                    {"t": BANK_TABLE},
                )
            ).all()
        )
        team_slug_type = (
            await pg_session.execute(
                text(
                    "SELECT data_type FROM information_schema.columns "
                    "WHERE table_name = 'teams' AND column_name = 'slug'"
                )
            )
        ).scalar_one()
        assert types["slug_after"] == team_slug_type
        assert set(types) == {"team_id", "slug_after", "taken_at"}

    async def test_a_banked_fill_undoes_completely(self, pg_session, world):
        await ensure_bank(pg_session)
        stats = await fill_missing_team_slugs(pg_session)
        assert stats["banked"] is True
        banked = (
            await pg_session.execute(text(f"SELECT count(*) FROM {BANK_TABLE}"))
        ).scalar_one()
        assert banked == stats["written"] == 4

        await pg_session.execute(text(_RESTORE_SQL))
        await pg_session.commit()
        assert (
            await pg_session.execute(text(_RESTORABLE_SQL))
        ).scalar_one() == 0
        assert await _slug_of(pg_session, world["city_ucl"]) is None
        # The row the fill never touched keeps the slug it always had.
        assert await _slug_of(pg_session, world["city_epl"]) == "manchester-city"

    async def test_the_undo_leaves_a_re_slugged_club_alone(self, pg_session, world):
        """An undo that overwrites work it did not do is not an undo. The
        predicate is `t.slug = b.slug_after`, so a club re-slugged between the
        fill and the restore keeps the newer value."""
        await ensure_bank(pg_session)
        await fill_missing_team_slugs(pg_session)
        await pg_session.execute(
            text("UPDATE teams SET slug = 'man-city-ucl-renamed' WHERE id = :i"),
            {"i": world["city_ucl"]},
        )
        await pg_session.commit()

        await pg_session.execute(text(_RESTORE_SQL))
        await pg_session.commit()
        assert await _slug_of(pg_session, world["city_ucl"]) == "man-city-ucl-renamed"
        assert await _slug_of(pg_session, world["georgia"]) is None

    async def test_banking_is_idempotent_across_two_passes(self, pg_session, world):
        """`ensure_bank` runs on every invocation of the script, and the beat
        writes `ON CONFLICT (team_id) DO UPDATE`. Neither may duplicate a club's
        row — a second row for one club would make the restore's join
        ambiguous."""
        await ensure_bank(pg_session)
        await fill_missing_team_slugs(pg_session)
        await ensure_bank(pg_session)
        await fill_missing_team_slugs(pg_session)
        distinct, total = (
            await pg_session.execute(
                text(f"SELECT count(DISTINCT team_id), count(*) FROM {BANK_TABLE}")
            )
        ).one()
        assert distinct == total == 4
