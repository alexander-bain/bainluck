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
