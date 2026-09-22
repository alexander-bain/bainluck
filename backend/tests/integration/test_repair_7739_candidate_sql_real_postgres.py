"""#7739 — the orientation repair's candidate query, PREPARED BY A REAL SERVER.

## what happened, and why every green test missed it

`tests/test_polymarket_host_orientation_7739.py` guards the verdict logic: which
rows the two-signal rule decides are reversed, that a wrong-leg ESPN match yields
DISAGREE, that `unhandled_reasons` refuses a half-swap. Those are the right tool
for *what does this script decide*, and they were all green when CERT-3291 granted
its token.

**Not one of them lets PostgreSQL see `CANDIDATE_SQL`.** So the script shipped with

    AND now() + interval :horizon_days * interval '1 day'

`INTERVAL` is a type constructor, not a function: its operand must be a literal, so
`interval $1` dies in the PARSER — before binding, before type resolution, before a
single row is considered.

    asyncpg.exceptions.PostgresSyntaxError: syntax error at or near "$1"

Measured on production the moment the script reached the slug — `run.3888` at
12:03Z on 2026-09-22, a plain dry run with no arguments. **Exit 1 on the first
statement.** Passing a different `--horizon-days` does not help and neither does
`--apply`: the failure is in the text, so there is no invocation of this script
that has ever selected a row. The repair was inert from the moment it merged, and
nothing in the suite, in CI, or in the cert could say so, because the only reader
that can is a server.

That is the gap this file closes: **`CANDIDATE_SQL` and its two sibling statements
are executed, by asyncpg, against a real PostgreSQL**, with the binds the script
actually passes.

Exactly the class #7354 shipped through (`AmbiguousParameterError` on an `IS NULL`
bind); `test_repair_7354_population_sql_real_postgres.py` is the precedent and this
file is deliberately its shape.

## the corpus separates "parses" from "still filters"

A cast is not the only edit that makes the syntax error go away — deleting the
BETWEEN clause does too, and so does any `OR TRUE`. Most of this corpus exists to
fail such a repair, so the gate cannot be satisfied by a statement that runs and
selects everything:

* `IN_WINDOW`   — polymarket-only anchor, no `espn_id`, scheduled, 5 days out.
  The one row a correct query returns.
* `FAR_FUTURE`  — identical but 60 days out. **In the population if the horizon
  stopped bounding**, which is what a deleted clause looks like.
* `HAS_ESPN_ID` — identical but carries an `espn_id`. ESPN already adjudicates it.
* `COMPLETED`   — identical but completed. A finished game's orientation is
  load-bearing for the score stored against it.
* `TWO_ANCHORS` — polymarket AND statpal. The `other.event_id IS NULL` arm exists
  because a second provider is a better authority than Polymarket's listing order.

`test_the_shipped_form_still_cannot_be_prepared` is the strawman: it rebuilds the
text as it merged and asserts the server still rejects it. Without it, a harness
that silently stopped reaching Postgres would pass every other arm in this file.
"""
from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone

import pytest

DB_URL = os.environ.get("SEARCH_TEST_DATABASE_URL")

needs_postgres = pytest.mark.skipif(
    not DB_URL,
    reason=(
        "set SEARCH_TEST_DATABASE_URL to run the real-Postgres #7739 candidate "
        "query gate"
    ),
)

PM_LEAGUE = "basketball_wnba"
SPORT_ID = 7739_01
OTHER_SPORT_ID = 7739_02

IN_WINDOW = 7739_0001
FAR_FUTURE = 7739_0002
HAS_ESPN_ID = 7739_0003
COMPLETED = 7739_0004
TWO_ANCHORS = 7739_0005

#: Only `IN_WINDOW` satisfies every arm at the script's default horizon.
EXPECTED_AT_30_DAYS = {IN_WINDOW}


def _asyncpg_url(url: str) -> str:
    if url.startswith("postgresql+asyncpg://"):
        return url
    return url.replace("postgres://", "postgresql://", 1).replace(
        "postgresql://", "postgresql+asyncpg://", 1
    )


@pytest.fixture
async def session():
    """Real Postgres with the real schema, dropped and rebuilt.

    The script's runtime DDL (`backup_event_orientation_7739`) is dropped on the
    way in and the way out. Nothing here applies, so nothing should create it —
    dropping it anyway keeps a future `--apply` arm from leaving a table behind
    that `Base.metadata.drop_all` cannot see, which is how #6919's gate broke a
    search test several hundred lines away in the same job.
    """
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    import app.models.models  # noqa: F401 — registers every table on Base
    from app.services.database import Base

    from scripts.repair_polymarket_event_orientation import BACKUP_TABLE

    engine = create_async_engine(_asyncpg_url(DB_URL))
    async with engine.begin() as conn:
        await conn.execute(text(f"DROP TABLE IF EXISTS {BACKUP_TABLE}"))
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with maker() as s:
            await _seed(s)
            yield s
    finally:
        async with engine.begin() as conn:
            await conn.execute(text(f"DROP TABLE IF EXISTS {BACKUP_TABLE}"))
        await engine.dispose()


async def _seed(session) -> None:
    from app.models import Event, Sport
    from app.models.models import EventProviderAnchor

    now = datetime.now(timezone.utc)
    session.add(Sport(id=SPORT_ID, key=PM_LEAGUE, name="WNBA"))
    session.add(Sport(id=OTHER_SPORT_ID, key="icehockey_nhl", name="NHL"))
    await session.flush()

    # (id, days_out, espn_id, status)
    corpus = (
        (IN_WINDOW, 5, None, "scheduled"),
        (FAR_FUTURE, 60, None, "scheduled"),
        (HAS_ESPN_ID, 5, "401857215", "scheduled"),
        (COMPLETED, -5, None, "completed"),
        (TWO_ANCHORS, 5, None, "scheduled"),
    )
    for eid, days_out, espn_id, status in corpus:
        session.add(
            Event(
                id=eid,
                sport_id=SPORT_ID,
                home_team_name=f"Toronto Tempo {eid}",
                away_team_name=f"Connecticut Sun {eid}",
                commence_time=now + timedelta(days=days_out),
                status=status,
                espn_id=espn_id,
            )
        )
    await session.flush()

    for eid, *_ in corpus:
        session.add(
            EventProviderAnchor(
                event_id=eid,
                source="polymarket",
                source_id=f"pm-{eid}",
                id_kind="game",
            )
        )
    # The one row with a second provider — a better authority than listing order.
    session.add(
        EventProviderAnchor(
            event_id=TWO_ANCHORS,
            source="statpal",
            source_id="sp-7739",
            id_kind="game",
        )
    )
    await session.commit()


async def _candidates(session, horizon_days: int) -> set[int]:
    """Run the SHIPPED constant with the SHIPPED bind. No re-typed copy."""
    from sqlalchemy import text

    from scripts.repair_polymarket_event_orientation import CANDIDATE_SQL

    rows = (
        await session.execute(text(CANDIDATE_SQL), {"horizon_days": horizon_days})
    ).mappings().all()
    return {r["id"] for r in rows}


@needs_postgres
class TestTheCandidateQueryReachesTheServer:
    async def test_the_candidate_sql_prepares_and_runs(self, session):
        """The whole point: asyncpg accepts the text and returns rows.

        This arm alone fails on the merged script with PostgresSyntaxError.
        """
        assert await _candidates(session, 30) == EXPECTED_AT_30_DAYS

    async def test_the_horizon_still_bounds_the_pass(self, session):
        """A cast that stopped filtering would pass the arm above and fail here."""
        assert FAR_FUTURE not in await _candidates(session, 30)
        assert FAR_FUTURE in await _candidates(session, 90)

    async def test_a_tighter_horizon_excludes_the_in_window_row(self, session):
        """The bind is READ, not merely accepted — a hardcoded 30 fails here."""
        assert await _candidates(session, 1) == set()

    async def test_a_row_espn_already_adjudicates_is_not_a_candidate(self, session):
        assert HAS_ESPN_ID not in await _candidates(session, 90)

    async def test_a_completed_game_is_not_a_candidate(self, session):
        """Swapping a finished game silently reverses the score stored on it."""
        assert COMPLETED not in await _candidates(session, 90)

    async def test_a_row_with_a_second_provider_is_not_a_candidate(self, session):
        assert TWO_ANCHORS not in await _candidates(session, 90)

    async def test_the_sibling_statements_also_prepare(self, session):
        """`CANDIDATE_SQL` is not the only text this script hands the server."""
        from sqlalchemy import text

        from scripts.repair_polymarket_event_orientation import (
            CLUBS_SQL,
            POLYMARKET_AWAY_FIRST_LEAGUES,
            UNHANDLED_SQL,
        )

        await session.execute(
            text(CLUBS_SQL), {"leagues": list(POLYMARKET_AWAY_FIRST_LEAGUES)}
        )
        unhandled = (
            await session.execute(text(UNHANDLED_SQL), {"ids": [IN_WINDOW]})
        ).mappings().all()
        assert [r["id"] for r in unhandled] == [IN_WINDOW]

    async def test_the_shipped_form_still_cannot_be_prepared(self, session):
        """THE STRAWMAN. Without this, a harness that stopped reaching Postgres
        would pass every arm above and report a gate that examined nothing."""
        from sqlalchemy import text
        from sqlalchemy.exc import ProgrammingError

        from scripts.repair_polymarket_event_orientation import CANDIDATE_SQL

        as_merged = CANDIDATE_SQL.replace(
            "now() + (cast(:horizon_days AS int) * interval '1 day')",
            "now() + interval :horizon_days * interval '1 day'",
        )
        assert as_merged != CANDIDATE_SQL, (
            "the shipped-form reconstruction no longer matches the current text — "
            "update this strawman or it silently stops proving anything"
        )
        with pytest.raises(ProgrammingError) as caught:
            await session.execute(text(as_merged), {"horizon_days": 30})
        # Keyed on the server's own sentence, not on a class: SQLAlchemy wraps the
        # asyncpg error in the dialect's DBAPI shim, so `.orig` is that shim and
        # `PostgresSyntaxError` survives only inside the message — which is also
        # the line `run.3888` printed on the dyno. (Same finding as #7354's gate.)
        assert 'syntax error at or near "$1"' in str(caught.value)

    async def test_the_double_colon_cast_is_not_a_bind_and_is_also_rejected(
        self, session
    ):
        """The SECOND trap, guarded because it is the fix a reader reaches for.

        `:horizon_days::int` looks like the obvious repair and compiles happily —
        with an EMPTY bind list, because SQLAlchemy's bind regex refuses a colon
        preceded by a colon. The literal `:horizon_days::int` then reaches the
        server. Anyone "simplifying" the cast back to `::` gets a red here instead
        of a second inert production run.
        """
        from sqlalchemy import text
        from sqlalchemy.exc import ProgrammingError

        from scripts.repair_polymarket_event_orientation import CANDIDATE_SQL

        double_colon = CANDIDATE_SQL.replace(
            "cast(:horizon_days AS int)", ":horizon_days::int"
        )
        assert double_colon != CANDIDATE_SQL
        assert text(double_colon).compile().params == {}, (
            "SQLAlchemy now treats `::` as a bind — this trap has changed shape"
        )
        with pytest.raises(ProgrammingError) as caught:
            await session.execute(text(double_colon), {"horizon_days": 30})
        # A DIFFERENT sentence from the arm above, and that is the point: the two
        # wrong spellings fail in two distinguishable ways, so neither arm can be
        # satisfied by the other's defect.
        assert 'syntax error at or near ":"' in str(caught.value)


@needs_postgres
class TestTheSettleStatementsReachTheServer:
    """The settle stage hands the server three MORE statements.

    Same gap, same cost. The unit guards prove SQLAlchemy binds the parameters;
    only a server proves the SQL parses and does what the sentence says. The
    repair's first apply was reverted inside 22 seconds by a writer it could not
    see, and the stage that answers that must not itself be inert.
    """

    async def test_the_stored_read_prepares_and_reads_the_source(self, session):
        from sqlalchemy import text

        from scripts.repair_polymarket_event_orientation import STORED_SQL

        await session.execute(
            text("UPDATE events SET win_probability_sources = "
                 "'{\"polymarket\": {\"value\": 0.455}}'::jsonb WHERE id = :i"),
            {"i": IN_WINDOW},
        )
        await session.commit()
        rows = (await session.execute(
            text(STORED_SQL), {"ids": [IN_WINDOW, FAR_FUTURE]}
        )).mappings().all()
        by_id = {r["id"]: r["value"] for r in rows}
        assert by_id[IN_WINDOW] == pytest.approx(0.455)
        # The row with no polymarket leg reads None, not 0.0 — the difference
        # between "we hold nothing" and "we hold zero" is a whole verdict.
        assert by_id[FAR_FUTURE] is None

    async def test_the_restamp_writes_only_the_polymarket_value(self, session):
        """It must move `polymarket.value` and leave every sibling source alone.

        A `jsonb_set` on the wrong path, or one that replaces the object, would
        take out the blend's other legs — a repair for one source quietly
        deleting the others.
        """
        from sqlalchemy import text

        from scripts.repair_polymarket_event_orientation import (
            RESTAMP_SQL,
            STORED_SQL,
        )

        await session.execute(
            text("UPDATE events SET win_probability_sources = '{"
                 "\"polymarket\": {\"value\": 0.455, \"scope\": \"keep-me\"}, "
                 "\"kalshi\": {\"value\": 0.61}}'::jsonb WHERE id = :i"),
            {"i": IN_WINDOW},
        )
        await session.commit()

        await session.execute(
            text(RESTAMP_SQL), {"event_id": IN_WINDOW, "value": 0.545}
        )
        await session.commit()

        after = (await session.execute(
            text("SELECT win_probability_sources AS s FROM events WHERE id = :i"),
            {"i": IN_WINDOW},
        )).mappings().one()["s"]
        assert after["polymarket"]["value"] == pytest.approx(0.545)
        assert after["polymarket"]["scope"] == "keep-me", (
            "the re-stamp replaced the source object instead of its value"
        )
        assert after["kalshi"]["value"] == pytest.approx(0.61), (
            "the re-stamp reached a source this repair does not transpose"
        )
        stored = (await session.execute(
            text(STORED_SQL), {"ids": [IN_WINDOW]}
        )).mappings().one()["value"]
        assert stored == pytest.approx(0.545)

    async def test_a_row_with_no_polymarket_leg_is_not_given_one(self, session):
        """The `WHERE` is load-bearing: `jsonb_set` on an absent parent is a
        no-op, but on a NULL column it would null the whole thing, and on a row
        with other sources it would MINT a polymarket leg that no market backs —
        the #1163 phantom, created by the repair itself."""
        from sqlalchemy import text

        from scripts.repair_polymarket_event_orientation import RESTAMP_SQL

        await session.execute(
            text("UPDATE events SET win_probability_sources = "
                 "'{\"kalshi\": {\"value\": 0.61}}'::jsonb WHERE id = :i"),
            {"i": FAR_FUTURE},
        )
        await session.commit()
        result = await session.execute(
            text(RESTAMP_SQL), {"event_id": FAR_FUTURE, "value": 0.545}
        )
        await session.commit()
        assert result.rowcount == 0
        after = (await session.execute(
            text("SELECT win_probability_sources AS s FROM events WHERE id = :i"),
            {"i": FAR_FUTURE},
        )).mappings().one()["s"]
        assert "polymarket" not in after
        assert after["kalshi"]["value"] == pytest.approx(0.61)

    async def test_the_snapshot_restamp_is_bounded_by_captured_at(self, session):
        """Only the snapshots laid down AFTER the swap may be transposed.

        The ones the swap itself already fixed must be left alone; re-swapping
        them undoes the first half of the repair. This arm seeds one snapshot on
        each side of the boundary and asserts exactly one moves.
        """
        from sqlalchemy import text

        from app.models.models import WinProbSnapshot
        from scripts.repair_polymarket_event_orientation import (
            RESTAMP_SNAPSHOTS_SQL,
        )

        swapped_at = datetime.now(timezone.utc)
        session.add(WinProbSnapshot(
            event_id=IN_WINDOW, source="polymarket",
            captured_at=swapped_at - timedelta(minutes=5),
            home_win_probability=0.2, away_win_probability=0.8,
        ))
        session.add(WinProbSnapshot(
            event_id=IN_WINDOW, source="polymarket",
            captured_at=swapped_at + timedelta(seconds=10),
            home_win_probability=0.3, away_win_probability=0.7,
        ))
        await session.commit()

        moved = (await session.execute(
            text(RESTAMP_SNAPSHOTS_SQL),
            {"ids": [IN_WINDOW], "since": swapped_at},
        )).rowcount
        await session.commit()
        assert moved == 1, "the bound is not filtering — an unbounded re-swap"

        rows = (await session.execute(
            text("SELECT captured_at, home_win_probability AS h"
                 " FROM win_prob_snapshots WHERE event_id = :i"
                 " ORDER BY captured_at"),
            {"i": IN_WINDOW},
        )).mappings().all()
        assert [float(r["h"]) for r in rows] == [
            pytest.approx(0.2), pytest.approx(0.7),
        ], "the pre-swap snapshot was transposed a second time"

    async def test_the_backup_table_takes_a_run_id_and_scopes_the_undo(
        self, session
    ):
        """Two applies must leave two recoverable runs, not one ambiguous pile.

        The shipped table has no `run_id`, so this also exercises the
        `ADD COLUMN IF NOT EXISTS` upgrade against a server: the fixture creates
        nothing, the first statement creates the old shape, the second carries
        it forward.
        """
        from sqlalchemy import text

        from scripts.repair_polymarket_event_orientation import BACKUP_TABLE

        await session.execute(text(
            f"CREATE TABLE IF NOT EXISTS {BACKUP_TABLE} ("
            " event_id bigint, home_team_name text, away_team_name text,"
            " home_team_id bigint, away_team_id bigint,"
            " win_probability_sources jsonb,"
            " backed_up_at timestamptz DEFAULT now())"
        ))
        await session.execute(text(
            f"ALTER TABLE {BACKUP_TABLE} ADD COLUMN IF NOT EXISTS run_id text"
        ))
        for run, home in (("run-a", "A"), ("run-b", "B")):
            await session.execute(text(
                f"INSERT INTO {BACKUP_TABLE} (event_id, home_team_name, run_id)"
                " VALUES (:e, :h, :r)"
            ), {"e": IN_WINDOW, "h": home, "r": run})
        await session.commit()

        # The unscoped restore is ambiguous — two rows for one event.
        both = (await session.execute(text(
            f"SELECT count(*) FROM {BACKUP_TABLE} WHERE event_id = :e"
        ), {"e": IN_WINDOW})).scalar_one()
        assert both == 2

        scoped = (await session.execute(text(
            f"SELECT home_team_name FROM {BACKUP_TABLE}"
            " WHERE event_id = :e AND run_id = :r"
        ), {"e": IN_WINDOW, "r": "run-a"})).scalars().all()
        assert scoped == ["A"], "the run scope does not disambiguate the undo"
