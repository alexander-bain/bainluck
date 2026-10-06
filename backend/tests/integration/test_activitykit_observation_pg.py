"""Actual PostgreSQL serializer gates, with an explicitly synthetic reader."""

import asyncio
from datetime import timedelta
import os
import pytest
from sqlalchemy import event, insert, select, text
from app.services.activitykit_observation import (
    ActivityKitObservationAdapter,
    LOCK_NAMESPACE,
    OBS,
    REG,
)
from app.services.activitykit_state_codec import decode_state
from tests.integration.test_activitykit_worker_pg import record, worker, mutate
from tests.test_activitykit_delivery_state import NOW

pytestmark = pytest.mark.skipif(
    not os.environ.get("SEARCH_TEST_DATABASE_URL"),
    reason="Disposable PostgreSQL URL required",
)


@pytest.fixture
async def pg():
    from tests.integration.test_activitykit_worker_pg import pg as original

    async for sessions in original.__wrapped__():
        async with sessions.kw["bind"].begin() as conn:
            await conn.run_sync(OBS.create)
            await conn.execute(
                text("ALTER TABLE events ADD COLUMN home_score INTEGER DEFAULT 0")
            )
        yield sessions


async def reader(db, id):
    score = (
        await db.execute(text("SELECT home_score FROM events WHERE id=:id"), {"id": id})
    ).scalar_one()
    return {
        "id": id,
        "home_team": "Home",
        "away_team": "Away",
        "status": "live",
        "sport": "basketball_nba",
        "home_score": score,
        "away_score": 0,
        "score_source": "provider",
        "score_observed_at": NOW,
        "hero_probability": 0.6,
        "hero_probability_away": 0.4,
        "hero_probability_observed_at": NOW - timedelta(seconds=15),
    }


def adapter(pg, read=reader, **kwargs):
    return ActivityKitObservationAdapter(pg.kw["bind"], reader=read, **kwargs)


async def test_writer_committed_during_lock_wait_is_visible(pg):
    engine = pg.kw["bind"]
    waiting = asyncio.Event()
    sqls = []

    def statement(conn, cursor, sql, params, context, many):
        sqls.append(sql)
        if "pg_advisory_lock(" in sql:
            waiting.set()

    async with engine.connect() as blocker:
        await blocker.execute(
            text("SELECT pg_advisory_lock(:n,42)"), {"n": LOCK_NAMESPACE}
        )
        event.listen(engine.sync_engine, "before_cursor_execute", statement)
        try:
            task = asyncio.create_task(adapter(pg).capture(42))
            await asyncio.wait_for(waiting.wait(), 3)
            async with engine.begin() as writer:
                await writer.execute(text("UPDATE events SET home_score=7 WHERE id=42"))
            assert not task.done()
            await blocker.execute(
                text("SELECT pg_advisory_unlock(:n,42)"), {"n": LOCK_NAMESPACE}
            )
            observation = await asyncio.wait_for(task, 5)
            assert observation.snapshot.home_score == 7
            assert observation.sequence == 1
            lock = next(i for i, s in enumerate(sqls) if "pg_advisory_lock(" in s)
            # Different connections may interleave; capture's first post-lock read
            # must be the reader, never a sequence read or transaction-level lock.
            reads = [
                s
                for s in sqls[lock + 1 :]
                if s.startswith("SELECT home_score") or "activitykit_observations" in s
            ]
            assert reads[0].startswith("SELECT home_score")
        finally:
            event.remove(engine.sync_engine, "before_cursor_execute", statement)


async def test_delayed_reader_and_concurrent_writer_order(pg):
    entered, release = asyncio.Event(), asyncio.Event()

    async def delayed(db, id):
        result = await reader(db, id)
        entered.set()
        await release.wait()
        return result

    a = asyncio.create_task(adapter(pg, delayed).capture(42))
    await asyncio.wait_for(entered.wait(), 3)
    b = asyncio.create_task(adapter(pg).capture(42))
    async with pg() as db, db.begin():
        await db.execute(text("UPDATE events SET home_score=8 WHERE id=42"))
    release.set()
    first, second = await asyncio.wait_for(asyncio.gather(a, b), 5)
    assert (
        first.sequence,
        first.snapshot.home_score,
        second.sequence,
        second.snapshot.home_score,
    ) == (1, 0, 2, 8)
    assert await adapter(pg).replay(42, 1) == first
    assert first.snapshot.score_observed_at == NOW
    assert first.snapshot.probability_observed_at == NOW - timedelta(seconds=15)


async def test_identity_change_refused_without_sequence_or_reparent(pg):
    async def changed(db, id):
        return {**await reader(db, id), "id": 43}

    with pytest.raises(ValueError, match="identity changed"):
        await adapter(pg, changed).capture(42)
    async with pg() as db:
        assert (await db.execute(select(OBS))).all() == []
        assert (await db.execute(select(REG.c.event_id))).scalar_one() == 42
    assert (await adapter(pg).capture(42)).sequence == 1


@pytest.mark.parametrize("cancel", [True, False])
async def test_failed_or_cancelled_capture_releases_lock(pg, cancel):
    entered = asyncio.Event()

    async def failed(db, id):
        await reader(db, id)
        entered.set()
        if cancel:
            await asyncio.Event().wait()
        raise RuntimeError("reader failed")

    task = asyncio.create_task(adapter(pg, failed).capture(42))
    await asyncio.wait_for(entered.wait(), 3)
    if cancel:
        task.cancel()
    with pytest.raises(asyncio.CancelledError if cancel else RuntimeError):
        await task
    assert (await asyncio.wait_for(adapter(pg).capture(42), 5)).sequence == 1


async def test_timeout_releases_connection_without_partial_row(pg):
    async with pg.kw["bind"].connect() as blocker:
        await blocker.execute(
            text("SELECT pg_advisory_lock(:n,42)"), {"n": LOCK_NAMESPACE}
        )
        with pytest.raises(Exception, match="lock timeout"):
            await adapter(pg, lock_timeout_ms=50).capture(42)
        await blocker.execute(
            text("SELECT pg_advisory_unlock(:n,42)"), {"n": LOCK_NAMESPACE}
        )
    assert (await adapter(pg).capture(42)).sequence == 1


async def test_terminal_replay_and_stop_fences(pg):
    first = await adapter(pg).capture(42)

    async def final(db, id):
        return {**await reader(db, id), "status": "completed"}

    second = await adapter(pg, final).capture(42)
    w = worker(pg)
    await adapter(pg).fanout(42, second.sequence, w, now=NOW)
    await adapter(pg).fanout(42, first.sequence, w, now=NOW)
    state = decode_state((await record(pg))["state"])
    assert state.terminal_latched and state.snapshot.is_terminal
    await w.observe("a", second.snapshot, revision=second.sequence, stop=True)
    await adapter(pg).fanout(42, second.sequence, w, now=NOW)
    assert decode_state((await record(pg))["state"]).stopped


async def test_bounded_fanout_and_authorization_filters(pg):
    await adapter(pg).capture(42)
    async with pg() as db, db.begin():
        reg = dict((await db.execute(select(REG))).mappings().one())
        await db.execute(text("INSERT INTO events(id) VALUES(43)"))
        for id in ["b", "c", "d", "e"]:
            await db.execute(
                insert(REG).values(
                    **{
                        **reg,
                        "activity_id": id,
                        "token_hash": id * 64,
                        "event_id": 43 if id == "d" else 42,
                        "expires_at": NOW if id == "e" else reg["expires_at"],
                    }
                )
            )
    page = await adapter(pg).fanout(42, 1, worker(pg), now=NOW, limit=2)
    assert (page.attempted, page.accepted, page.next_cursor) == (2, 2, "b")
    page = await adapter(pg).fanout(42, 1, worker(pg), now=NOW, after="b", limit=2)
    assert (page.attempted, page.accepted, page.next_cursor) == (1, 1, None)


async def test_worker_rechecks_expiry_after_fanout_selection(pg):
    await adapter(pg).capture(42)

    class Expired:
        async def observe(self, *args, **kwargs):
            await mutate(pg, expires_at=NOW)
            return await worker(pg).observe(*args, **kwargs)

    assert (await adapter(pg).fanout(42, 1, Expired(), now=NOW)).accepted == 0


async def test_serializer_released_before_worker_fanout(pg):
    await adapter(pg).capture(42)

    class Check:
        async def observe(self, *args, **kwargs):
            assert (await asyncio.wait_for(adapter(pg).capture(42), 5)).sequence == 2
            return True

    assert (await adapter(pg).fanout(42, 1, Check(), now=NOW)).accepted == 1


async def test_observation_merge_refusal_preserves_parent(pg, monkeypatch):
    from app.utils import event_child_repoint as rail

    await adapter(pg).capture(42)
    async with pg() as db, db.begin():
        await db.execute(text("INSERT INTO events(id) VALUES(43)"))
    monkeypatch.setattr(rail, "event_fk_tables", lambda: ("activitykit_observations",))
    async with pg() as db, db.begin():
        with pytest.raises(rail.ImmutableActivityBindingRefused):
            await rail.repoint_event_children(db, keep_id=43, orphan_id=42)
    assert (await adapter(pg).replay(42, 1)).snapshot.event_id == 42


@pytest.fixture
async def canonical_pg():
    from uuid import uuid4
    from sqlalchemy.engine import make_url
    from sqlalchemy.ext.asyncio import create_async_engine
    from app.services.database import Base
    import app.models  # noqa: F401 — registers complete FK metadata

    url = make_url(os.environ["SEARCH_TEST_DATABASE_URL"])
    assert url.get_backend_name() == "postgresql" and url.database == "bl_searchtest"
    schema = "activitykit_canonical_" + uuid4().hex
    admin = create_async_engine(url)
    async with admin.begin() as conn:
        await conn.execute(text(f'CREATE SCHEMA "{schema}"'))
    engine = create_async_engine(
        url, connect_args={"server_settings": {"search_path": schema}}
    )
    try:
        async with engine.begin() as conn:
            # Tables only: canonical correctness does not depend on indexes; the
            # full metadata has unrelated PostgreSQL-15-only index clauses.
            from sqlalchemy.schema import CreateTable

            from sqlalchemy import Enum

            enum_types = {
                column.type.name: column.type
                for table in Base.metadata.tables.values()
                for column in table.columns
                if isinstance(column.type, Enum)
            }
            for enum_type in enum_types.values():
                await conn.run_sync(
                    lambda sync, typ=enum_type: typ.create(sync, checkfirst=True)
                )
            for table in Base.metadata.sorted_tables:
                await conn.execute(CreateTable(table))
        yield engine
    finally:
        await engine.dispose()
        async with admin.begin() as conn:
            await conn.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        await admin.dispose()


@pytest.mark.parametrize(
    "sport,status",
    [
        ("basketball_nba", "live"),
        ("soccer_epl", "live"),
        ("basketball_nba", "completed"),
    ],
)
async def test_actual_canonical_route_matches_persisted_projection(
    canonical_pg, sport, status
):
    from app.models import Event, Sport
    from app.routes.events import build_event_detail_uncoalesced
    from app.utils.activitykit_projection import project_activitykit_snapshot
    from sqlalchemy.ext.asyncio import AsyncSession

    engine = canonical_pg
    async with engine.begin() as conn:
        await conn.execute(
            insert(Sport.__table__).values(id=1, key=sport, name="Fixture sport")
        )
        await conn.execute(
            insert(Event.__table__).values(
                id=42,
                sport_id=1,
                external_id="fixture42",
                home_team_name="Home",
                away_team_name="Away",
                commence_time=NOW,
                status=status,
                home_score=2,
                away_score=1,
                score_source="espn",
                score_observed_at=NOW,
                win_probability_sources={
                    "espn": {
                        "value": 0.63,
                        "home_probability": 0.63,
                        "away_probability": 0.27,
                        "updated_at": NOW.isoformat(),
                    }
                },
            )
        )
    waiting = asyncio.Event()
    capture_statements = []
    capture_connection = None

    def statement(conn, cursor, sql, params, context, many):
        nonlocal capture_connection
        if "pg_advisory_lock(" in sql:
            capture_connection = conn
            waiting.set()
        elif conn is capture_connection:
            capture_statements.append(sql)

    async with engine.connect() as blocker:
        await blocker.execute(
            text("SELECT pg_advisory_lock(:n,42)"), {"n": LOCK_NAMESPACE}
        )
        event.listen(engine.sync_engine, "before_cursor_execute", statement)
        try:
            task = asyncio.create_task(
                ActivityKitObservationAdapter(engine).capture(42)
            )
            await asyncio.wait_for(waiting.wait(), 3)
            async with engine.begin() as writer:
                await writer.execute(text("UPDATE events SET home_score=3 WHERE id=42"))
            assert not task.done()
            await blocker.execute(
                text("SELECT pg_advisory_unlock(:n,42)"), {"n": LOCK_NAMESPACE}
            )
            observed = await asyncio.wait_for(task, 5)
        finally:
            event.remove(engine.sync_engine, "before_cursor_execute", statement)
    assert observed.snapshot.home_score == 3
    assert capture_statements[0].startswith("SELECT events.")
    async with AsyncSession(engine, autoflush=False) as db:
        detail = await build_event_detail_uncoalesced(db, 42)
    assert observed.snapshot == project_activitykit_snapshot(detail)
    assert observed.snapshot.score_observed_at == NOW
    assert observed.snapshot.is_terminal == (status == "completed")
    if status == "live":
        assert observed.snapshot.home_rendered_percent == 63
        assert observed.snapshot.probability_observed_at == NOW
    else:
        assert observed.snapshot.home_rendered_percent is None
        assert observed.snapshot.probability_observed_at is None
    assert await ActivityKitObservationAdapter(engine).replay(42, 1) == observed
