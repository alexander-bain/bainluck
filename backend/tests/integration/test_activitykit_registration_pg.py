"""#10542 credential ownership against isolated real PostgreSQL transactions.

SHIP: the selected game's background activity keeps its account-owned delivery
credential through replacement/stop. Explicit test URL only; random test schema.
"""

import asyncio
import json
import os
from types import SimpleNamespace
from uuid import uuid4

from fastapi import HTTPException
import pytest
from sqlalchemy import select, text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from starlette.requests import Request

from app.models.activitykit import ActivityKitRegistration
from app.routes import activitykit

DB_URL = os.environ.get("SEARCH_TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(
    not DB_URL,
    reason="SEARCH_TEST_DATABASE_URL required for isolated PostgreSQL ownership gate",
)
TABLE = ActivityKitRegistration.__table__


@pytest.fixture
async def pg():
    url = make_url(DB_URL)
    assert url.get_backend_name() == "postgresql", "PostgreSQL gate requires PostgreSQL"
    assert (
        url.database == "bl_searchtest"
    ), "Only the hosted disposable test database is permitted"
    schema = "activitykit_test_" + uuid4().hex
    admin = create_async_engine(url)
    async with admin.begin() as conn:
        await conn.execute(text(f'CREATE SCHEMA "{schema}"'))
    engine = create_async_engine(
        url, connect_args={"server_settings": {"search_path": schema}}
    )
    async with engine.begin() as conn:
        await conn.execute(text("CREATE TABLE users(id INTEGER PRIMARY KEY)"))
        await conn.execute(text("CREATE TABLE events(id INTEGER PRIMARY KEY)"))
        await conn.execute(text("INSERT INTO users VALUES (1), (2)"))
        await conn.execute(text("INSERT INTO events VALUES (42), (43)"))
        await conn.run_sync(TABLE.create)
    yield async_sessionmaker(engine, expire_on_commit=False)
    await engine.dispose()
    async with admin.begin() as conn:
        await conn.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
    await admin.dispose()


def body(version=0, token="ab" * 32, event_id=42):
    return {
        "event_id": event_id,
        "expected_version": version,
        "mutation_id": str(uuid4()),
        "push_token": token,
    }


async def invoke(sessions, value, *, identity="activity-a", user=1, revoke=False):
    payload = {k: v for k, v in value.items() if not revoke or k != "push_token"}

    async def receive():
        return {
            "type": "http.request",
            "body": json.dumps(payload).encode(),
            "more_body": False,
        }

    request = Request(
        {
            "type": "http",
            "method": "DELETE" if revoke else "PUT",
            "path": "/",
            "headers": [],
        },
        receive,
    )
    async with sessions() as db:
        try:
            result = await activitykit._mutate(
                request, identity, SimpleNamespace(id=user), db, revoke=revoke
            )
            return 200, result
        except HTTPException as error:
            return error.status_code, error.detail


async def row(sessions, identity="activity-a"):
    async with sessions() as db:
        return (
            (await db.execute(select(TABLE).where(TABLE.c.activity_id == identity)))
            .mappings()
            .one_or_none()
        )


def synchronize_owned_reads(monkeypatch):
    original = activitykit._owned
    barrier = asyncio.Barrier(2)

    async def owned(*args):
        value = await original(*args)
        await barrier.wait()
        return value

    monkeypatch.setattr(activitykit, "_owned", owned)
    return original


async def test_two_session_replacements_only_one_cas_wins(pg, monkeypatch):
    assert (await invoke(pg, body()))[0] == 200
    synchronize_owned_reads(monkeypatch)
    outcomes = await asyncio.wait_for(
        asyncio.gather(invoke(pg, body(1, "cd" * 32)), invoke(pg, body(1, "ef" * 32))),
        timeout=15,
    )
    assert sorted(status for status, _ in outcomes) == [200, 409]
    actual = await row(pg)
    assert actual["version"] == 2
    assert actual["push_token"] in {"cd" * 32, "ef" * 32}


async def test_concurrent_creates_preserve_one_owner_and_event(pg, monkeypatch):
    synchronize_owned_reads(monkeypatch)
    outcomes = await asyncio.wait_for(
        asyncio.gather(
            invoke(pg, body(), user=1),
            invoke(pg, body(token="cd" * 32, event_id=43), user=2),
        ),
        timeout=15,
    )
    assert sorted(status for status, _ in outcomes) == [200, 409]
    actual = await row(pg)
    assert (actual["user_id"], actual["event_id"]) in {(1, 42), (2, 43)}
    winner = next(result for status, result in outcomes if status == 200)
    assert winner["event_id"] == actual["event_id"]


async def test_concurrent_token_unique_collision_is_generic(pg, monkeypatch, caplog):
    synchronize_owned_reads(monkeypatch)
    outcomes = await asyncio.wait_for(
        asyncio.gather(
            invoke(pg, body(), identity="activity-a"),
            invoke(pg, body(), identity="activity-b", user=2),
        ),
        timeout=15,
    )
    assert sorted(status for status, _ in outcomes) == [200, 409]
    assert (
        next(value for status, value in outcomes if status == 409)
        == "Registration conflict"
    )
    assert "ab" * 32 not in caplog.text
    async with pg() as db:
        assert len((await db.execute(select(TABLE))).all()) == 1


async def test_create_revoke_race_and_stop_first_tombstone_cannot_reactivate(
    pg, monkeypatch
):
    assert (await invoke(pg, body(), identity="stopped-first", revoke=True))[0] == 200
    assert (await invoke(pg, body(), identity="stopped-first"))[0] == 409
    original = synchronize_owned_reads(monkeypatch)
    outcomes = await asyncio.wait_for(
        asyncio.gather(invoke(pg, body()), invoke(pg, body(), revoke=True)), timeout=15
    )
    assert sorted(status for status, _ in outcomes) == [200, 409]
    monkeypatch.setattr(activitykit, "_owned", original)
    actual = await row(pg)
    if actual["is_active"]:
        assert (await invoke(pg, body(actual["version"]), revoke=True))[0] == 200
    actual = await row(pg)
    assert not actual["is_active"]
    assert actual["push_token"] is None and actual["token_hash"] is None
    assert (await invoke(pg, body(actual["version"])))[0] == 409


async def test_user_delete_cascades_deliverable_token_in_postgresql(pg):
    assert (await invoke(pg, body()))[0] == 200
    async with pg() as db:
        await db.execute(text("DELETE FROM users WHERE id=1"))
        await db.commit()
    assert await row(pg) is None
