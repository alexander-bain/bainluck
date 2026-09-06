"""#3672's repair, executed through a REAL asyncpg connection — #1884's class.

WHY THIS FILE EXISTS
────────────────────
`repair_3672_bare_namespace_event_names.py` shipped with 42 green unit tests,
passed CERT-2139, merged at `343eea23` and deployed as Heroku v4240 — and threw
on the first statement of every run:

    asyncpg.exceptions.DataError: invalid input for query argument $1:
    '2026-06-01' (expected a datetime.date or datetime.datetime instance,
    got 'str')

`SINCE` was an ISO string bound into `CAST(:since AS timestamptz)`. Postgres
infers that parameter as `timestamptz`; asyncpg refuses a `str` there rather
than casting it, which psycopg2 would have done silently. So the script planned
nothing, wrote no backup, and exited 1 on a detached dyno whose stdout the
sandbox cannot read — the "it returned is not it worked" shape of gotcha #53,
except it did not even return.

Nothing in the unit suite could see it. Every case there drives the planner
through a fake session that accepts any params object, so the bind's TYPE was
never in contact with a type system. A cert graded the diff, which is the right
thing for a cert to do and is not where this belonged.

WHY IT IS A SECOND FILE AND NOT A CASE IN THE CLIFF DRAIN'S
────────────────────────────────────────────────────────────
`tests/integration/test_kalshi_cliff_bind_contract.py` was written for exactly
this class (#1884) and its docstring says it "closes the CLASS". It closed the
class *for the SQL it executes* — the drain's own. The class recurred four
months later in a different module because no other module's statements were
ever put in front of the driver. So the unit of protection is a statement, not a
codebase, and a script that runs unattended against production earns its own.

WHAT IS ASSERTED: the script's two real statements, with the script's own binds,
against real PostgreSQL. Not a paraphrase — the candidate query is imported
behaviour via `build_plan`, so a future edit to that SQL is covered without
this file being touched.

CI: named explicitly in the `search-recall` job. The assertion that it IS named
lives in the always-run unit file, not here, because a wiring check inside a
skip-gated file is circular.
"""

import os
import sys
from datetime import datetime, timedelta, timezone

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

DB_URL = os.environ.get("SEARCH_TEST_DATABASE_URL")

pytestmark = [
    pytest.mark.skipif(
        not DB_URL,
        reason=(
            "set SEARCH_TEST_DATABASE_URL to run the real-asyncpg #3672 repair "
            "bind contract (CI job `search-recall` provides one)"
        ),
    ),
    pytest.mark.asyncio,
]


@pytest.fixture
async def pg_session():
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


class TestTheRepairsOwnStatementsSurviveTheDriver:
    async def test_the_candidate_query_executes_with_the_shipped_binds(
        self, pg_session
    ):
        """THE SPECIMEN. On an EMPTY database this must return no rows — and
        crucially must not raise. The shipped version raised here."""
        from scripts.repair_3672_bare_namespace_event_names import build_plan

        plan, skipped = await build_plan(pg_session)
        assert plan == [] and skipped == []

    async def test_the_since_watermark_actually_filters_rather_than_erroring(
        self, pg_session
    ):
        """A bind that raises and a bind that filters nothing are both 'no rows'.

        Seeds one row on each side of `SINCE` and asserts the watermark cuts
        between them, so the parameter is proved to reach the comparison with
        its meaning intact — not merely to be accepted.
        """
        from sqlalchemy import text

        from scripts.repair_3672_bare_namespace_event_names import SINCE, build_plan

        assert isinstance(SINCE, datetime)
        await pg_session.execute(
            text(
                # `active` is NOT NULL with a PYTHON-side default only, and a
                # raw INSERT bypasses it — see test_pg_gate_seed_completeness.
                "INSERT INTO sports (id, key, name, active) "
                "VALUES (1, 'tennis_wta', 'WTA', true)"
            )
        )
        rows = {
            "before": SINCE.replace(tzinfo=timezone.utc) - timedelta(days=30),
            "after": SINCE.replace(tzinfo=timezone.utc) + timedelta(days=30),
        }
        for i, (label, when) in enumerate(rows.items(), start=1):
            await pg_session.execute(
                text(
                    "INSERT INTO events (id, sport_id, home_team_name, away_team_name, "
                    "commence_time, status) VALUES "
                    "(:i, 1, 'Timberwolves', 'Hornets', :w, 'scheduled')"
                ),
                {"i": i, "w": when},
            )
            await pg_session.execute(
                text(
                    # category / mutually_exclusive / status are NOT NULL with
                    # PYTHON-side defaults only; a raw INSERT bypasses those.
                    "INSERT INTO futures_markets "
                    "  (id, source, external_id, name, event_id, "
                    "   category, mutually_exclusive, status) "
                    "VALUES (:i, 'kalshi', :ext, 'Minnen vs Charaeva', :i, "
                    "        'championship', true, 'open')"
                ),
                {"i": i, "ext": f"KXWTACHALLENGERMATCH-26JUN0{i}MINCHA"},
            )
        await pg_session.commit()

        plan, skipped = await build_plan(pg_session)
        touched = {r["id"] for r in plan} | {r[0]["id"] for r in skipped}
        assert 1 not in touched, "the pre-SINCE row was not excluded by the watermark"
        assert 2 in touched, (
            "the post-SINCE row was not reached — the watermark accepted the bind "
            "but filtered everything, which reads exactly like the DataError did"
        )

    async def test_the_collision_probes_timestamptz_cast_also_survives(
        self, pg_session
    ):
        """The file's SECOND `CAST(:c AS timestamptz)`, in `drop_collisions`.

        It lives in a different function, is bound from a row rather than a
        constant, and `build_plan` never reaches it — so the specimen test above
        would stay green if this one broke. Both casts belong in front of the
        driver, because "the other one is fine" is what was true this morning.

        Its bind is `row["commence"]`, which comes off the database and is
        therefore a datetime by construction today. That is a property of the
        current query, not a guarantee: project it as text and this fails here
        rather than on a dyno.
        """
        from sqlalchemy import text

        from scripts.repair_3672_bare_namespace_event_names import (
            SINCE,
            build_plan,
            drop_collisions,
        )

        await pg_session.execute(
            text(
                # `active` is NOT NULL with a PYTHON-side default only, and a
                # raw INSERT bypasses it — see test_pg_gate_seed_completeness.
                "INSERT INTO sports (id, key, name, active) "
                "VALUES (1, 'tennis_wta', 'WTA', true)"
            )
        )
        when = SINCE.replace(tzinfo=timezone.utc) + timedelta(days=30)
        await pg_session.execute(
            text(
                "INSERT INTO events (id, sport_id, home_team_name, away_team_name, "
                "commence_time, status) VALUES "
                "(1, 1, 'Timberwolves', 'Hornets', :w, 'scheduled')"
            ),
            {"w": when},
        )
        await pg_session.execute(
            text(
                "INSERT INTO futures_markets "
                "  (id, source, external_id, name, event_id, "
                "   category, mutually_exclusive, status) "
                "VALUES (1, 'kalshi', 'KXWTACHALLENGERMATCH-26JUN02MINCHA', "
                "        'Minnen vs Charaeva', 1, 'championship', true, 'open')"
            )
        )
        await pg_session.commit()

        plan, _ = await build_plan(pg_session)
        assert plan, "nothing planned, so the collision probe would not be exercised"
        kept, dropped = await drop_collisions(pg_session, plan)
        assert len(kept) + len(dropped) == len(plan)
