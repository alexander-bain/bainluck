"""#7594 — the take-back cannot empty a fixture, proved with two real sessions.

CERT-3204's required repair, `7594-CANONICAL-ROW-MUST-BE-OWNED-THROUGH-TAKEBACK`.

## the interleaving, and why nothing cheaper can see it

CERT-3199's repair put the screen's verdict inside the write:

    UPDATE events SET status = :after
     WHERE id = :i AND status = :before
       AND EXISTS (a row the screen accepted, still in the status it accepted)

That closes a canonical retirement **committed before the statement starts**. It
cannot close one committed *during* it: under READ COMMITTED the subquery is
evaluated against the statement's snapshot, MVCC readers never block, and the
row being updated is the SUBJECT, not the canonical — so a writer that retires
the canonical a microsecond after the snapshot is invisible, the swap matches,
both rows commit retired, and the fixture has ZERO reader-visible cards.

`FOR UPDATE` on the counterparts is the one read that DOES block, which is why
the repair takes row ownership before it writes and holds it to commit. There is
no interleaving left: the competing writer either committed before the locking
read (it is seen), or is mid-transaction (the read waits for it and then sees
it), or arrives afterwards (it waits for the take-back's transaction and
re-evaluates against a database in which the subject is already retired).

## why this file exists next to the sqlite race tests

**sqlite serialises writers and ignores `FOR UPDATE` entirely**, so the whole
hazard is unreachable on that rail — the existing race tests pass with the lock,
without the lock, and would pass with a lock that did nothing. Only real
Postgres, and only two real sessions, can tell those three apart. That is the
same lesson as the `MAX(x.captured_at)` string assertions in
`test_staleness_does_not_end_a_match.py`: a guard that cannot execute the
mechanism it is guarding is not a guard.

## the strawman

`test_without_ownership_the_same_interleaving_really_does_empty_the_fixture`
runs the identical sequence with the ownership step stubbed out and REQUIRES the
defect to appear (zero cards). Without it, a rig whose second session silently
did nothing — a wrong id, a rolled-back transaction, a connection on the wrong
database — would report the repair working and prove nothing at all.
"""

from __future__ import annotations

import asyncio
import importlib
import os
from datetime import datetime, timedelta, timezone

import pytest

#: A DATABASE OF ITS OWN, provisioned by the step before this one in
#: `search-recall` and thrown away with the runner. Never `bl_searchtest`: this
#: file builds and drops the handful of tables the repair touches, and the
#: shared recall database is populated by ~90 earlier steps whose inbound
#: foreign keys make the drop fail outright.
DB_URL = os.environ.get("CANONICAL_OWNERSHIP_DATABASE_URL")

pytestmark = [pytest.mark.asyncio]

needs_postgres = pytest.mark.skipif(
    not DB_URL,
    reason=(
        "set CANONICAL_OWNERSHIP_DATABASE_URL to run the two-session ownership "
        "contract (CI job `search-recall` provisions a disposable one)"
    ),
)

#: How long the test waits before asserting the take-back is still blocked. Long
#: enough that a pass which was NOT blocked would certainly have finished (the
#: whole pass is three statements against a six-row database, microseconds on
#: this hardware), short enough to cost nothing. It is an assertion about
#: BLOCKING, so it is checked with `task.done()` and never with a wall-clock
#: comparison — a slow runner makes this test slower, never wrong.
BLOCKED_FOR = 0.4


def _repair():
    return importlib.import_module(
        "scripts.repair_7594_revoid_published_reversed_twins"
    )


def _args(apply=True, backup=True):
    from types import SimpleNamespace

    return SimpleNamespace(apply=apply, backup=backup)


async def _seed(session):
    """The production shape: one game, two cards, sides reversed."""
    from app.models.models import Event, Sport

    nhl = Sport(key="icehockey_nhl", name="NHL")
    catchall = Sport(key="icehockey_other", name="Ice Hockey")
    session.add_all([nhl, catchall])
    await session.flush()

    start = datetime.now(timezone.utc) + timedelta(hours=3)
    revived = Event(
        sport_id=catchall.id,
        home_team_name="Hurricanes",
        away_team_name="Panthers",
        commence_time=start,
        status="scheduled",
    )
    canonical = Event(
        sport_id=nhl.id,
        home_team_name="Florida Panthers",
        away_team_name="Carolina Hurricanes",
        commence_time=start,
        status="scheduled",
    )
    session.add_all([revived, canonical])
    await session.commit()
    return revived.id, canonical.id


@pytest.fixture
async def world():
    """Real Postgres, the repair's two tables, and the seeded pair.

    Function-scoped for the reason `test_search_recall_contract.py` gives:
    `pytest.ini` leaves `asyncio_default_fixture_loop_scope` unset, so a
    module-scoped async fixture outlives the loop that created its engine.
    """
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    import app.models.models  # noqa: F401 — registers every table on Base
    from app.services.database import Base

    repair = _repair()
    wanted = [
        Base.metadata.tables[name]
        for name in ("sports", "teams", "venues", "events")
    ]

    engine = create_async_engine(DB_URL)
    async with engine.begin() as conn:
        await conn.execute(
            text(f"DROP TABLE IF EXISTS {repair.BANK_TABLE}")
        )
        await conn.execute(
            text(f"DROP TABLE IF EXISTS {repair.UNREACHABLE_SUSPENDED_BACKUP_TABLE}")
        )
        await conn.run_sync(Base.metadata.drop_all, tables=wanted, checkfirst=True)
        await conn.run_sync(Base.metadata.create_all, tables=wanted)

    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as session:
        revived_id, canonical_id = await _seed(session)
        # The #7260 arm's ledger IS the repair's scope, so the pass selects
        # nothing without it.
        await session.execute(
            text(
                f"CREATE TABLE {repair.UNREACHABLE_SUSPENDED_BACKUP_TABLE} "
                "(event_id INTEGER)"
            )
        )
        await session.execute(
            text(
                f"INSERT INTO {repair.UNREACHABLE_SUSPENDED_BACKUP_TABLE} "
                "(event_id) VALUES (:i)"
            ),
            {"i": revived_id},
        )
        await session.commit()

    yield engine, maker, revived_id, canonical_id

    await engine.dispose()


async def _cards_a_reader_can_reach(maker):
    from sqlalchemy import text

    from app.utils.event_completion import is_retired_event_status

    async with maker() as session:
        rows = (
            await session.execute(text("SELECT id, status FROM events ORDER BY id"))
        ).all()
    return [(i, s) for i, s in rows if not is_retired_event_status(s)]


async def _run_with_a_writer_between_the_screen_and_the_write(
    engine, maker, monkeypatch, canonical_id, *, own=True
):
    """Drive the real `run()` while a SECOND session retires the canonical.

    The second session's UPDATE is issued from inside the screen's own return
    path, which is the exact instant CERT-3204 names: after the take-back has
    decided the canonical is alive, before it writes. It is left UNCOMMITTED, so
    the repair's locking read has something real to wait for; the caller commits
    it once it has established that the repair is blocked.
    """
    from sqlalchemy import text

    import app.tasks.base as base

    repair = _repair()
    monkeypatch.setenv("HEROKU_APP_NAME", repair.PRODUCER_APP)

    session_a = maker()
    monkeypatch.setattr(base, "get_task_session", lambda **_kw: _Ctx(session_a))

    if not own:
        # THE STRAWMAN ARM. Ownership removed and nothing else changed, so the
        # interleaving below has to produce the defect.
        async def _no_ownership(_s, ids):
            return [(i, "scheduled") for i in ids]

        monkeypatch.setattr(repair, "own_the_canonical", _no_ownership)

    conn_b = await engine.connect()
    trans_b = await conn_b.begin()
    real_screen = repair._surviving_counterpart_rows
    fired = {"b": False}

    async def screen_then_a_competing_writer(s, event):
        rows = await real_screen(s, event)
        if not fired["b"]:
            fired["b"] = True
            await conn_b.execute(
                text("UPDATE events SET status = :s WHERE id = :i"),
                {"s": repair.UNREACHABLE_SUSPENDED_TERMINAL, "i": canonical_id},
            )
        return rows

    monkeypatch.setattr(
        repair, "_surviving_counterpart_rows", screen_then_a_competing_writer
    )

    task = asyncio.create_task(repair.run(_args()))
    await asyncio.sleep(BLOCKED_FOR)
    blocked = not task.done()
    await trans_b.commit()
    await conn_b.close()
    code = await asyncio.wait_for(task, timeout=20)
    await session_a.close()
    return code, blocked


class _Ctx:  # pragma: no cover - test rail
    """`get_task_session`'s surface over a session this test keeps a handle on.

    It commits on a clean exit exactly as the real one does — which is what
    holds the row lock for the whole take-back rather than for one statement.
    """

    def __init__(self, session):
        self._s = session

    async def __aenter__(self):
        return self._s

    async def __aexit__(self, exc_type, *_exc):
        if exc_type is None:
            await self._s.commit()
        return False


@needs_postgres
class TestTheCanonicalIsOwnedThroughTheTakeBack:
    async def test_concurrent_canonical_retirement_after_exists_snapshot_cannot_empty_fixture(
        self, world, monkeypatch
    ):
        """THE SHIP. Two sessions, the interleaving CERT-3204 named, one card left.

        The competing writer lands after the screen and after any snapshot the
        UPDATE's `EXISTS` could take, and it is still uncommitted when the
        take-back reaches its locking read. So the read WAITS — asserted, because
        a lock that does not block is not a lock — and when it returns, the
        canonical is retired and the pass keeps its own row rather than voiding
        the last card for the game.
        """
        engine, maker, revived_id, canonical_id = world

        code, blocked = await _run_with_a_writer_between_the_screen_and_the_write(
            engine, maker, monkeypatch, canonical_id
        )

        assert blocked, (
            "the take-back did not wait for the competing writer — "
            "`FOR UPDATE` is not being taken, and the window is open again"
        )
        assert await _cards_a_reader_can_reach(maker) == [(revived_id, "scheduled")]
        assert code == 0

    async def test_without_ownership_the_same_interleaving_really_does_empty_the_fixture(
        self, world, monkeypatch
    ):
        """THE STRAWMAN. Ownership stubbed out, nothing else changed.

        This must FAIL to protect the fixture, or the test above is proving
        something about the rig rather than about the repair — a second session
        on the wrong database, a rolled-back transaction or a mistyped id would
        all otherwise read as a pass.
        """
        engine, maker, _revived_id, canonical_id = world

        _code, blocked = await _run_with_a_writer_between_the_screen_and_the_write(
            engine, maker, monkeypatch, canonical_id, own=False
        )

        assert not blocked, "without the lock there is nothing to wait for"
        assert await _cards_a_reader_can_reach(maker) == [], (
            "the interleaving is supposed to empty the fixture without the "
            "ownership step — if it does not, this rig is not reproducing "
            "CERT-3204's hazard and the test above proves nothing"
        )
