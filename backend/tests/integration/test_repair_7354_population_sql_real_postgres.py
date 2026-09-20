"""#7354 — the repair rail's own census, PREPARED BY A REAL SERVER.

## what happened, and why 54 green tests could not see it

`test_a_settled_swapped_row_is_repaired_only_when_the_slot_copy_is_proven_7354.py`
carries 54 guards. Every one of them drives a fake session: the corpus is a list
of `SimpleNamespace` rows and the "database" answers whatever the test handed it.
They are the right tool for *which rows does this rail decide to touch*, and they
proved the slot-copy proof, the per-store judgement and the undo's column parity.

**Not one of them lets PostgreSQL see the statement.** So the rail shipped with

    AND (:sport_key IS NULL OR s.key = :sport_key)

in `_SETTLED_PREDICATE` — the predicate BOTH `_POPULATION_SQL` and
`_CANDIDATE_SQL` are built from — and a bind whose only typing context is
`IS NULL` has no type PostgreSQL can infer. asyncpg PREPAREs before it binds, so
the statement dies in type resolution, before the values are ever considered:

    asyncpg.exceptions.AmbiguousParameterError:
        could not determine data type of parameter $2

Measured on production the morning after the forward fix merged — `run.8889` at
07:23:49Z with no `--sport`, and `run.3415` at 07:25:48Z with
`--sport americanfootball_ncaaf`. **Both exit 1 on the first statement.** Passing
a value does not help: the failure is in the text, not the parameters, so there
is no invocation of this rail that ever worked. The repair half of #7354 was
inert from the moment it merged, and nothing in the suite, in CI, or in the cert
could say so, because the only reader that can is a server.

That is the gap this file closes: **the rail's SQL is executed, by asyncpg,
against a real PostgreSQL, through the shipped `run()` entry point** — the same
function the operator invokes on the dyno.

## why the whole `run()` and not just the two statements

A gate that re-typed `_POPULATION_SQL` here would prove the typist agreed with
themselves. `run()` is what the Heroku one-off calls; it resolves
`get_task_session`, executes the census, executes the candidate fetch with its
own `LIMIT`/`OFFSET` binds, walks the rows and prints the operator's ledger. Its
exit code and its `population=` line are exactly what a person reads after
`heroku run:detached`, so that is what is asserted.

Dry-run only. `--apply` is D51(b) work with its own backup, CAS and app gate, and
`test_drain_6919_apply_restore_real_postgres.py` is the precedent for gating
*that* half; this file is about whether the rail can open its own census at all.

## the corpus separates "typeable" from "still filtering"

A cast is not the only edit that makes the error go away — deleting the clause
does too, and so does any `OR TRUE`. Two of the five rows exist to fail such a
repair:

* `NCAAF_A`, `NCAAF_B`, `NFL` — settled, scored, `espn_id` set, inside the floor.
  All three are the population when no sport is named; only the first two are
  when `americanfootball_ncaaf` is. **A cast that stopped filtering passes the
  first arm and fails the second.**
* `NO_ESPN` — settled and scored with a NULL `espn_id`. ESPN cannot adjudicate a
  row it cannot be asked about.
* `ANCIENT` — settled, scored, `espn_id` set, and 400 days old: outside
  `--since-days`, which is `make_interval(days => :since_days)`, the OTHER bind
  in the same predicate and the one that IS typed (by the function's signature).

ESPN itself is stubbed to answer unreadably (see `_UnreadableEspnEvent`). What
the rail then decides about a row is the 54 guards' subject and is deliberately
not restated here; this gate ends at "the right rows arrived, on a real server".
"""

from __future__ import annotations

import contextlib
import os
from datetime import datetime, timedelta, timezone

import pytest

DB_URL = os.environ.get("SEARCH_TEST_DATABASE_URL")

needs_postgres = pytest.mark.skipif(
    not DB_URL,
    reason=(
        "set SEARCH_TEST_DATABASE_URL to run the real-Postgres #7354 census "
        "gate (CI job `search-recall` provides one)"
    ),
)

NCAAF_A, NCAAF_B, NFL, NO_ESPN, ANCIENT = (
    73541001,
    73541002,
    73541003,
    73541004,
    73541005,
)

NCAAF_KEY = "americanfootball_ncaaf"
NFL_KEY = "americanfootball_nfl"

#: Every row that satisfies the predicate when no sport is named, and the subset
#: that satisfies it when one is. Named once so no arm can drift from the
#: docstring.
ALL_SPORTS_POPULATION = 3
NCAAF_POPULATION = 2


def _asyncpg_url(url: str) -> str:
    if url.startswith("postgresql+asyncpg://"):
        return url
    return url.replace("postgres://", "postgresql://", 1).replace(
        "postgresql://", "postgresql+asyncpg://", 1
    )


@pytest.fixture
async def session():
    """Real Postgres with the real schema, dropped and rebuilt.

    The rail's runtime DDL (`bak_7354_settled_orientation_swap`) is dropped on
    the way in and the way out. Nothing here applies, so nothing should create
    it — dropping it anyway keeps a future `--apply` arm from leaving a table
    behind that `Base.metadata.drop_all` cannot see, which is how #6919's gate
    broke a search test several hundred lines away in the same job.
    """
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    import app.models.models  # noqa: F401 — registers every table on Base
    from app.services.database import Base
    from scripts.repair_7354_settled_orientation_swap import BAK_TABLE

    engine = create_async_engine(_asyncpg_url(DB_URL))
    async with engine.begin() as conn:
        await conn.execute(text(f"DROP TABLE IF EXISTS {BAK_TABLE}"))
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with maker() as s:
            await _seed(s)
            yield s
    finally:
        async with engine.begin() as conn:
            await conn.execute(text(f"DROP TABLE IF EXISTS {BAK_TABLE}"))
        await engine.dispose()


async def _seed(session) -> None:
    """Insert the corpus through the ORM."""
    from app.models import Event, Sport

    now = datetime.now(timezone.utc)
    session.add(Sport(id=7354_01, key=NCAAF_KEY, name="NCAAF"))
    session.add(Sport(id=7354_02, key=NFL_KEY, name="NFL"))
    await session.flush()

    # (id, sport, espn_id, days_ago)
    corpus = (
        (NCAAF_A, 7354_01, "401856802", 1),
        (NCAAF_B, 7354_01, "401856803", 2),
        (NFL, 7354_02, "401856804", 3),
        (NO_ESPN, 7354_01, None, 1),
        (ANCIENT, 7354_01, "401856805", 400),
    )
    for eid, sport_id, espn_id, days_ago in corpus:
        session.add(
            Event(
                id=eid,
                sport_id=sport_id,
                home_team_name=f"Home {eid}",
                away_team_name=f"Away {eid}",
                commence_time=now - timedelta(days=days_ago),
                completed_at=now - timedelta(days=days_ago) + timedelta(hours=3),
                status="completed",
                home_score=27,
                away_score=38,
                espn_id=espn_id,
            )
        )
    await session.commit()


@contextlib.asynccontextmanager
async def _yield(session):
    yield session


class _UnreadableEspnEvent:
    """ESPN answering, for every row, in a way the judge cannot read.

    A final with scores and NO competitor objects is `UNRESOLVED` by
    `espn_orientation_verdict`'s first guard — "a row we cannot read at all is
    not evidence of a swap". Two reasons this and not `None`:

    * it is the only skip the rail puts a LEDGER LINE on (an `espn_not_found`
      row is counted and never printed), and the ledger line carrying `ev<id>`
      is how these arms see WHICH rows the two statements returned;
    * it reaches further into the pass — both `_LAST_*_SNAPSHOT_SQL` statements
      execute before the plan, so they are prepared by the server here too.

    What the rail then DECIDES belongs to the 54 unit guards. Nothing here
    touches the network.
    """

    async def get_event(self, sport_key, espn_id):  # noqa: D102
        from types import SimpleNamespace

        return SimpleNamespace(
            status="post", home_score=38, away_score=27,
            home_team=None, away_team=None,
        )


async def _run(session, monkeypatch, capsys, **kwargs) -> tuple[int, str]:
    """Execute the SHIPPED `run()` against this database. Returns (exit, stdout)."""
    import app.services.espn_api as espn_mod
    import app.tasks.base as base
    from scripts import repair_7354_settled_orientation_swap as rail

    monkeypatch.setattr(base, "get_task_session", lambda: _yield(session))
    monkeypatch.setattr(espn_mod, "ESPNAPIService", _UnreadableEspnEvent)

    params = {"apply": False, "limit": 50, "sport": None, "offset": 0,
              "since_days": 60}
    params.update(kwargs)
    code = await rail.run(**params)
    return code, capsys.readouterr().out


@needs_postgres
class TestTheRailCanOpenItsOwnCensus:
    """The statements REACH a server and come back — the production failure."""

    async def test_the_census_runs_when_no_sport_is_named(
        self, session, monkeypatch, capsys
    ):
        """`run.8889`'s exact invocation. Red before the cast, on this message:

            AmbiguousParameterError: could not determine data type of parameter $2
        """
        code, out = await _run(session, monkeypatch, capsys)

        assert code == 0, out
        assert f"population={ALL_SPORTS_POPULATION} " in out, out

    async def test_the_census_runs_when_a_sport_is_named(
        self, session, monkeypatch, capsys
    ):
        """`run.3415`'s exact invocation — a VALUE for the bind does not save it.

        PREPARE resolves types before it sees a parameter, so the non-null case
        failed identically in production. Both arms exist because "it only breaks
        without `--sport`" is the reading the error message invites.
        """
        code, out = await _run(session, monkeypatch, capsys, sport=NCAAF_KEY)

        assert code == 0, out
        assert f"population={NCAAF_POPULATION} " in out, out

    async def test_the_candidate_fetch_and_its_cursor_binds_also_prepare(
        self, session, monkeypatch, capsys
    ):
        """`LIMIT :limit OFFSET :offset` is a second statement with more binds.

        A census that runs proves nothing about the fetch beneath it: the two are
        separate PREPAREs and only the fetch carries the cursor. Scanning one row
        at offset 1 exercises both bounds and the resumable cursor the operator
        is told to advance.
        """
        code, out = await _run(session, monkeypatch, capsys, limit=1, offset=1)

        assert code == 0, out
        assert f"COVERAGE: scanned 1 of {ALL_SPORTS_POPULATION} at offset 1" in out
        assert "next_offset 2" in out, out


@needs_postgres
class TestTheSportFilterStillFilters:
    """A cast is not the only edit that silences the error — these fail the others."""

    async def test_naming_a_sport_excludes_the_other_sports_rows(
        self, session, monkeypatch, capsys
    ):
        """Deleting the clause, or `OR TRUE`, passes every arm above and this one
        is what it fails: the NFL row must not be in an NCAAF pass."""
        _, out = await _run(session, monkeypatch, capsys, sport=NCAAF_KEY)

        assert f"ev{NFL}" not in out, out
        assert f"ev{NCAAF_A}" in out and f"ev{NCAAF_B}" in out, out

    async def test_naming_no_sport_includes_every_sport(
        self, session, monkeypatch, capsys
    ):
        """The other direction: NULL means "all sports", not "no sports". A cast
        placed so that the IS NULL arm never matches turns the default invocation
        — the one the operator runs first — into a silent empty pass."""
        _, out = await _run(session, monkeypatch, capsys)

        for eid in (NCAAF_A, NCAAF_B, NFL):
            assert f"ev{eid}" in out, out


@needs_postgres
class TestTheRestOfThePredicateSurvivedTheRepair:
    """The cast sits inside a predicate with four other clauses."""

    async def test_a_row_espn_cannot_be_asked_about_is_not_in_the_population(
        self, session, monkeypatch, capsys
    ):
        _, out = await _run(session, monkeypatch, capsys)

        assert f"ev{NO_ESPN}" not in out, out

    async def test_the_since_days_floor_still_bounds_the_pass(
        self, session, monkeypatch, capsys
    ):
        """`make_interval(days => :since_days)` is the typed bind in the same
        predicate, and a floor that stopped binding would quietly widen every
        pass onto rows ESPN no longer serves (gotcha #41)."""
        _, out = await _run(session, monkeypatch, capsys)
        assert f"ev{ANCIENT}" not in out, out

        _, wide = await _run(session, monkeypatch, capsys, since_days=500)
        assert f"ev{ANCIENT}" in wide, wide


@needs_postgres
class TestTheDefectIsReproducibleFromTheShippedText:
    """Red-first, executed rather than remembered."""

    async def test_the_uncast_bind_still_cannot_be_prepared(self, session):
        """Textual surgery on the SHIPPED constant reverts the one-token fix and
        the server refuses it again.

        This is the arm that keeps the CAST from being read as decoration. It
        reverts `CAST(:sport_key AS text)` to the bare bind in the real
        `_SETTLED_PREDICATE` — so if the cast is ever removed, the surgery is a
        no-op and the census arms above go red instead.
        """
        import sqlalchemy.exc
        from sqlalchemy import text

        from scripts.repair_7354_settled_orientation_swap import _POPULATION_SQL

        reverted = _POPULATION_SQL.replace("CAST(:sport_key AS text)", ":sport_key")
        assert ":sport_key IS NULL" in reverted, (
            "the surgery did not find the cast — _POPULATION_SQL no longer "
            "builds on the predicate this gate is about"
        )

        with pytest.raises(sqlalchemy.exc.ProgrammingError) as caught:
            await session.execute(
                text(reverted), {"sport_key": None, "since_days": 60}
            )

        # Keyed on the server's own sentence, not on a class: SQLAlchemy wraps
        # the asyncpg error in the dialect's DBAPI shim, so `.orig` is that shim
        # and `AmbiguousParameterError` survives only inside the message — which
        # is also the line the production dyno printed.
        assert "could not determine data type of parameter" in str(caught.value)
