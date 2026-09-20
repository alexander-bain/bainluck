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

## what is deliberately not asserted here

The ladder's *content* — which string each rung composes — is unit-graded in
`tests/test_team_slug_ladder_7501.py`, including the migration-token trap. This
file only asks which rung a row lands on when the index pushes it there.
"""

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

    # Only the two tables this ship touches, rather than `Base.metadata` whole.
    # Not an optimisation: the full schema carries DDL that needs PostgreSQL 15
    # (`NULLS NOT DISTINCT`), and a fixture that only stands up on the CI image
    # is a fixture nobody runs before pushing. `teams` and `sports` are the real
    # ones, from `models.py`, with the real UNIQUE index on `teams.slug` — which
    # is the entire reason this file wants a server.
    tables = [Sport.__table__, Team.__table__]

    engine = create_async_engine(DB_URL)
    async with engine.begin() as conn:
        await conn.execute(text(f"DROP TABLE IF EXISTS {BANK_TABLE}"))
        await conn.run_sync(Base.metadata.drop_all, tables=tables)
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
    """
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


class TestTheBank:
    async def test_the_fill_runs_and_says_so_when_there_is_no_bank(
        self, pg_session, world
    ):
        """The ship is not held hostage to a side table. A beat firing before
        anyone has run `--backup` must still give clubs their pages."""
        stats = await fill_missing_team_slugs(pg_session)
        assert stats["banked"] is False
        assert stats["written"] == 4

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
        writes `ON CONFLICT DO NOTHING`. Neither may duplicate a club's row —
        a second row for one club would make the restore's join ambiguous."""
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
