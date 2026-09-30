"""A replaced-player write that fails costs its own row, not the tennis pass.
#9797 follow-up (CERT-3856 `9797-RELEASE-FLUSH-SAVEPOINT`), real Postgres.

#9797 made a withdrawn row give its ESPN id back and FLUSH the clear, so the
lucky loser's real match can be stamped in the same pass. That flush is a real
UPDATE inside ``_sync_tennis_from_espn``'s ONE transaction. Before this file's
fix it ran with no savepoint: a lock timeout or a deadlock there was caught by
the row's handler and logged, the transaction stayed aborted, every later row
raised ``InFailedSQLTransactionError``, and the pass's one ``COMMIT`` became a
ROLLBACK — the writes of every OTHER tennis row were lost with it (#8796's
class, on the tennis pass).

Only Postgres aborts a transaction, so this file uses a real failure of the
real statement: a second connection holds the withdrawn row ``FOR UPDATE`` and
the pass runs under a short ``lock_timeout``. The claim tested is the pass's:
the row read AFTER the failed release still gets its ESPN id, on disk.
"""

from __future__ import annotations

import os
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select, text

#: The #7617 step's disposable database, as the #8796 file uses. This file
#: drops and creates only the tables it names.
DB_URL = os.environ.get("DELAY_CONTRACT_DATABASE_URL")

pytestmark = [pytest.mark.asyncio]

needs_postgres = pytest.mark.skipif(
    not DB_URL,
    reason=(
        "set DELAY_CONTRACT_DATABASE_URL to run the real-Postgres tennis "
        "release-savepoint contract (CI job `search-recall` provisions one)"
    ),
)

BUCKET, GENERIC = "tennis_wta_china_open", "tennis_wta"
RELEASED_ID, SIBLING_ID = "184289", "184290"


def _clock():
    """ESPN's start for the released competition. Offset FIRST, then
    truncated, so the anchor never branches on the clock (gotcha #44)."""
    return (datetime.now(timezone.utc) + timedelta(hours=6)).replace(
        second=0, microsecond=0
    )


def _iso(at: datetime) -> str:
    return at.strftime("%Y-%m-%dT%H:%MZ")


@pytest.fixture
async def db():
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    import app.models.models  # noqa: F401 — registers every table on Base
    from app.models.models import Event, Sport
    from app.services.database import Base

    # Same closure as the #8796 file, so either can run after the other.
    wanted = [
        Base.metadata.tables[name]
        for name in (
            "sports",
            "teams",
            "venues",
            "events",
            "win_prob_snapshots",
            "futures_markets",
            "futures_outcomes",
        )
    ]
    engine = create_async_engine(DB_URL)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all, tables=wanted, checkfirst=True)
        await conn.run_sync(Base.metadata.create_all, tables=wanted)

    maker = async_sessionmaker(engine, expire_on_commit=False)
    t = _clock()
    async with maker() as session:
        bucket = Sport(key=BUCKET, name=BUCKET)
        session.add_all([bucket, Sport(key=GENERIC, name=GENERIC)])
        await session.flush()
        rows = {
            # #8288 already suspended it; ESPN has since handed 184289 to the
            # lucky loser. Read FIRST (the pass orders by start, newest first).
            "withdrawn": Event(
                sport_id=bucket.id, home_team_name="Marcinko",
                away_team_name="Frech", status="suspended",
                commence_time=t - timedelta(hours=9), espn_id=RELEASED_ID,
                event_tags=["provenance:source:kalshi"],
            ),
            # Another match of the same board, read AFTER the withdrawn row:
            # its stamp is the write a poisoned transaction would lose.
            "sibling": Event(
                sport_id=bucket.id, home_team_name="Elvina Kalieva",
                away_team_name="Viktorija Golubic", status="scheduled",
                commence_time=t - timedelta(hours=10),
                event_tags=["provenance:source:odds_api"],
            ),
            # The match ESPN now lists under 184289, 12 h off ESPN's start.
            "replacement": Event(
                sport_id=bucket.id, home_team_name="Magdalena Frech",
                away_team_name="Elsa Jacquemot", status="scheduled",
                commence_time=t - timedelta(hours=12),
                commence_time_source="odds_api",
                event_tags=["provenance:source:odds_api"],
            ),
        }
        session.add_all(list(rows.values()))
        await session.commit()
        ids = {name: row.id for name, row in rows.items()}

    yield engine, maker, ids

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all, tables=wanted, checkfirst=True)
    await engine.dispose()


def _wire(monkeypatch, maker, *, lock_timeout: str | None):
    """The real task, with only its I/O replaced: ESPN's board, and a real
    session committed once at the end, as ``get_task_session`` does."""
    import app.services.espn_tennis as svc
    import app.tasks.espn_sync as espn_sync
    from tests.test_espn_tennis_anchor import _competition
    from tests.test_tennis_replaced_player_suspends_8288 import _board

    t = _clock()
    payloads = _board(
        _competition(RELEASED_ID, ["Magdalena Frech", "Elsa Jacquemot"], date=_iso(t)),
        _competition(
            SIBLING_ID, ["Elvina Kalieva", "Viktorija Golubic"],
            date=_iso(t - timedelta(hours=10)),
        ),
    )

    @asynccontextmanager
    async def _session(**_kwargs):
        async with maker() as session:
            try:
                if lock_timeout:
                    await session.execute(
                        text(f"SET LOCAL lock_timeout = '{lock_timeout}'")
                    )
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    monkeypatch.setattr(svc, "fetch_scoreboards", lambda dates=None: (payloads, []))
    monkeypatch.setattr(espn_sync, "get_task_session", _session)


async def _row(maker, event_id):
    from app.models.models import Event

    async with maker() as session:
        return (
            await session.execute(
                select(Event.espn_id, Event.status, Event.event_tags).where(
                    Event.id == event_id
                )
            )
        ).one()


@needs_postgres
class TestTheReleaseLosesALock:
    async def test_the_rows_after_it_still_commit(self, db, monkeypatch):
        """THE SHIP. RED before the fix: the release's flush timed out, the
        handler logged it, the sibling's stamp raised on the aborted
        transaction, and the COMMIT discarded it."""
        from app.tasks.espn_sync import _sync_tennis_from_espn

        engine, maker, ids = db
        _wire(monkeypatch, maker, lock_timeout="300ms")

        # Another writer holds the withdrawn row, as a live-state write can.
        holder = await engine.connect()
        holder_tx = await holder.begin()
        await holder.execute(
            text("SELECT id FROM events WHERE id = :id FOR UPDATE"),
            {"id": ids["withdrawn"]},
        )
        try:
            stats = await _sync_tennis_from_espn()
        finally:
            await holder_tx.rollback()
            await holder.close()

        sibling_id, _, _ = await _row(maker, ids["sibling"])
        assert sibling_id == SIBLING_ID, (
            "a failed release discarded another row's ESPN anchor", stats
        )
        assert stats["replaced_player_write_errors"] == 1, stats
        assert stats["replaced_player_id_releases"] == 0, stats
        assert stats["row_errors"] == 0, stats
        # The failed release is rolled back whole: the row still holds its id
        # and carries no release tag, so the next pass retries it cleanly.
        espn_id, status, tags = await _row(maker, ids["withdrawn"])
        assert (espn_id, status, tags) == (
            RELEASED_ID, "suspended", ["provenance:source:kalshi"]
        )
        # Its holder still stands, so the replacement waits for that retry.
        assert (await _row(maker, ids["replacement"]))[0] is None

    async def test_an_uncontended_release_lands_and_the_real_match_anchors(
        self, db, monkeypatch
    ):
        """THE KILL CONTROL. A savepoint that swallowed every release would pass
        the ship (the sibling still anchors) and fail here."""
        from app.tasks.espn_sync import _sync_tennis_from_espn
        from app.utils.espn_tennis_anchor import ESPN_ID_RELEASED_TAG_PREFIX

        _, maker, ids = db
        _wire(monkeypatch, maker, lock_timeout=None)

        stats = await _sync_tennis_from_espn()

        assert stats["replaced_player_write_errors"] == 0, stats
        assert stats["replaced_player_id_releases"] == 1, stats
        espn_id, status, tags = await _row(maker, ids["withdrawn"])
        assert (espn_id, status) == (None, "suspended")
        assert tags == [
            "provenance:source:kalshi", f"{ESPN_ID_RELEASED_TAG_PREFIX}{RELEASED_ID}"
        ]
        assert (await _row(maker, ids["replacement"]))[0] == RELEASED_ID
        assert (await _row(maker, ids["sibling"]))[0] == SIBLING_ID
