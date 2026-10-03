"""#9238: repair/restore roundtrip and real PostgreSQL backup-lock regression.

Use a disposable database on the local CI service, never production. The old
EXISTS-only guard failed both concurrent-backup cases while waiting on a market
lock. SQLite cannot model that READ COMMITTED statement-snapshot race.
"""

import asyncio
from contextlib import asynccontextmanager
from types import SimpleNamespace
import os
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

from scripts import repair_4962_market_image_repick as repair
from scripts import restore_4962_market_images as restore

URL = os.environ.get("SEARCH_TEST_DATABASE_URL")
pytestmark = [
    pytest.mark.asyncio,
    pytest.mark.skipif(
        not URL,
        reason="SEARCH_TEST_DATABASE_URL required for real-PG image repair gate",
    ),
]


@pytest.fixture(scope="session")
def isolated_database():
    url = make_url(URL)
    assert url.host in ("localhost", "127.0.0.1"), "gate may only use local PostgreSQL"
    database = "image_guard_9238_" + uuid4().hex
    admin = create_engine(
        url.set(drivername="postgresql+psycopg2"), isolation_level="AUTOCOMMIT"
    )
    with admin.connect() as connection:
        connection.execute(text(f'CREATE DATABASE "{database}"'))
    try:
        yield url.set(database=database)
    finally:
        with admin.connect() as connection:
            connection.execute(text(f'DROP DATABASE "{database}"'))
        admin.dispose()


@pytest.fixture
async def gate(monkeypatch, isolated_database):
    engine = create_async_engine(isolated_database)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as session:
        await session.execute(text("DROP TABLE IF EXISTS backup_4962_market_images"))
        await session.execute(text("DROP TABLE IF EXISTS futures_markets"))
        await session.execute(
            text(
                "CREATE TABLE futures_markets (id BIGINT PRIMARY KEY, name TEXT, llm_sport_category TEXT, status TEXT, image_url TEXT, image_width INTEGER, image_height INTEGER)"
            )
        )
        for mid, (name, category, photo) in repair.PINNED_SPECIMENS.items():
            await session.execute(
                text(
                    "INSERT INTO futures_markets VALUES (:id,:name,:category,:status,:image,940,NULL)"
                ),
                dict(
                    id=mid,
                    name=name,
                    category=category,
                    status="resolved" if mid == 16757297 else "open",
                    image=f"https://images.pexels.com/photos/{photo}/pexels-photo-{photo}.jpeg?auto=compress",
                ),
            )
        await session.execute(
            text(
                "INSERT INTO futures_markets VALUES (1,'Untouched','golf','open','control.jpg',12,34)"
            )
        )
        await session.commit()

        @asynccontextmanager
        async def factory():
            yield session

        monkeypatch.setattr(repair, "get_task_session", factory)
        monkeypatch.setattr(restore, "get_task_session", factory)
        monkeypatch.setenv("HEROKU_APP_NAME", "bainluck")
        yield session, maker
    await engine.dispose()


def args(**kwargs):
    return SimpleNamespace(ids="16757297,109295", backup=False, apply=False, **kwargs)


async def image(session, mid):
    return (
        await session.execute(
            text(
                "SELECT image_url,image_width,image_height FROM futures_markets WHERE id=:id"
            ),
            dict(id=mid),
        )
    ).one()


async def snapshots(session, restoring=False):
    if restoring:
        q = "SELECT f.id,f.name,f.llm_sport_category,f.status,b.image_url,b.image_width,b.image_height,f.image_url AS current_image,f.image_width AS current_width,f.image_height AS current_height FROM futures_markets f JOIN backup_4962_market_images b ON b.id=f.id WHERE f.id IN (16757297,109295) ORDER BY f.id"
    else:
        q = "SELECT * FROM futures_markets WHERE id IN (16757297,109295) ORDER BY id"
    return [
        SimpleNamespace(**dict(r._mapping))
        for r in (await session.execute(text(q))).all()
    ]


async def backed(session):
    assert (
        await repair.run(
            SimpleNamespace(ids="16757297,109295", backup=True, apply=False)
        )
        == 0
    )


async def cleared(session):
    await backed(session)
    assert (
        await repair.run(
            SimpleNamespace(ids="16757297,109295", backup=False, apply=True)
        )
        == 0
    )


async def test_run_backup_apply_restore_roundtrip_and_control(gate):
    s, _ = gate
    before = {mid: await image(s, mid) for mid in (*repair.FILED_MARKET_IDS, 1)}
    assert await repair.run(args()) == 0
    assert not (
        await s.execute(
            text("SELECT to_regclass('public.backup_4962_market_images') IS NOT NULL")
        )
    ).scalar()
    await cleared(s)
    for mid in (16757297, 109295):
        assert await image(s, mid) == (None, None, None)
    assert await image(s, 1) == before[1]
    # A pinned row outside the requested --ids is not touched (#10326's row).
    assert await image(s, 61040985) == before[61040985]
    assert await restore.run(args()) == 0
    assert await image(s, 109295) == (None, None, None)
    assert await restore.run(SimpleNamespace(ids="16757297,109295", apply=True)) == 0
    assert {mid: await image(s, mid) for mid in before} == before


async def test_apply_missing_backup_refuses_and_subset_does_not_widen(gate):
    s, _ = gate
    assert (
        await repair.run(
            SimpleNamespace(ids="16757297,109295", backup=False, apply=True)
        )
        == 2
    )
    assert await repair.run(SimpleNamespace(ids="1", backup=False, apply=True)) == 2
    await backed(s)
    assert (
        await repair.run(SimpleNamespace(ids="109295", backup=False, apply=True)) == 0
    )
    assert (await image(s, 16757297))[0] is not None
    assert await image(s, 109295) == (None, None, None)


@pytest.mark.parametrize("mode", ["clear", "restore"])
@pytest.mark.parametrize(
    "table,column,value",
    [
        ("futures_markets", "name", "Changed question"),
        ("futures_markets", "llm_sport_category", "politics"),
        ("futures_markets", "status", "live"),
        ("futures_markets", "image_url", "new-good.jpg"),
        ("futures_markets", "image_width", 123),
        ("futures_markets", "image_height", 456),
        ("backup_4962_market_images", "image_url", "new-backup.jpg"),
        ("backup_4962_market_images", "image_width", 123),
        ("backup_4962_market_images", "image_height", 456),
    ],
)
async def test_committed_drift_refuses_whole_batch(gate, mode, table, column, value):
    s, maker = gate
    if mode == "restore":
        await cleared(s)
    else:
        await backed(s)
    rows = await snapshots(s, mode == "restore")
    first_before = await image(s, rows[0].id)
    async with maker() as writer:
        await writer.execute(
            text(f"UPDATE {table} SET {column}=:value WHERE id=:id"),
            dict(value=value, id=rows[1].id),
        )
        await writer.commit()
    fn = (
        restore.restore_captured_rows
        if mode == "restore"
        else repair.clear_captured_rows
    )
    assert not await fn(s, rows)
    assert await image(s, rows[0].id) == first_before
    assert (
        await s.execute(
            text(f"SELECT {column} FROM {table} WHERE id=:id"), dict(id=rows[1].id)
        )
    ).scalar() == value


@pytest.mark.parametrize("mode", ["clear", "restore"])
async def test_lock_wait_rechecks_concurrent_replacement(gate, mode):
    s, maker = gate
    if mode == "restore":
        await cleared(s)
    else:
        await backed(s)
    rows = await snapshots(s, mode == "restore")
    first_before = await image(s, rows[0].id)
    async with maker() as writer:
        await writer.execute(
            text("SELECT id FROM futures_markets WHERE id=:id FOR UPDATE"),
            dict(id=rows[1].id),
        )
        fn = (
            restore.restore_captured_rows
            if mode == "restore"
            else repair.clear_captured_rows
        )
        task = asyncio.create_task(fn(s, rows))
        # Wait for a genuine PostgreSQL lock wait, not guessed timing.
        for _ in range(100):
            await writer.execute(text("SELECT pg_stat_clear_snapshot()"))
            waits = (
                await writer.execute(
                    text(
                        "SELECT count(*) FROM pg_stat_activity WHERE datname=current_database() AND wait_event_type='Lock'"
                    )
                )
            ).scalar()
            if waits:
                break
            await asyncio.sleep(0.02)
        assert waits, "repair never reached the contested row"
        await writer.execute(
            text("UPDATE futures_markets SET image_url='new-good.jpg' WHERE id=:id"),
            dict(id=rows[1].id),
        )
        await writer.commit()
        assert not await asyncio.wait_for(task, 5)
    assert await image(s, rows[0].id) == first_before
    assert (await image(s, rows[1].id))[0] == "new-good.jpg"


@pytest.mark.parametrize("mode", ["clear", "restore"])
async def test_lock_wait_rechecks_concurrent_backup_change(gate, mode):
    s, maker = gate
    if mode == "restore":
        await cleared(s)
    else:
        await backed(s)
    rows = await snapshots(s, mode == "restore")
    first_before = await image(s, rows[0].id)
    async with maker() as writer:
        await writer.execute(
            text("SELECT id FROM futures_markets WHERE id=:id FOR UPDATE"),
            dict(id=rows[1].id),
        )
        fn = (
            restore.restore_captured_rows
            if mode == "restore"
            else repair.clear_captured_rows
        )
        task = asyncio.create_task(fn(s, rows))
        for _ in range(100):
            await writer.execute(text("SELECT pg_stat_clear_snapshot()"))
            waits = (
                await writer.execute(
                    text(
                        "SELECT count(*) FROM pg_stat_activity WHERE datname=current_database() AND wait_event_type='Lock'"
                    )
                )
            ).scalar()
            if waits:
                break
            await asyncio.sleep(0.02)
        assert waits, "repair never reached the contested row"
        await writer.execute(
            text(
                "UPDATE backup_4962_market_images SET image_url='new-backup.jpg' WHERE id=:id"
            ),
            dict(id=rows[1].id),
        )
        await writer.commit()
        assert not await asyncio.wait_for(
            task, 5
        ), "backup changed while UPDATE waited; stale MVCC predicate must not allow write"
    assert await image(s, rows[0].id) == first_before
