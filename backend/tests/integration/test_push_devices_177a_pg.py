"""177-A / 178-B: a phone registers its pins and push tokens without an account,
on real PostgreSQL.

SHIP: a reader who pins a game gets its kickoff, big-swing and final alerts, and
the Live Activity that starts by push, without signing in.

Explicit test URL only (the hosted disposable ``bl_searchtest``), random test
schema dropped afterwards. The database-integration job names this file and
fails on any skip.
"""

import importlib.util
import os
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import httpx
import pytest
from fastapi import FastAPI, HTTPException, Request
from sqlalchemy import create_engine, select, text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.dependencies.auth import get_current_user, get_optional_user
from app.models.activitykit import ActivityKitRegistration
from app.models.activitykit_delivery import ActivityKitDelivery
from app.models.models import UserPin
from app.models.push_device import PushDevice
from app.routes import activitykit, devices
from app.services.database import get_db_rw

DB_URL = os.environ.get("SEARCH_TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(
    not DB_URL,
    reason="SEARCH_TEST_DATABASE_URL required for the #177-A push-devices gate",
)
DEVICES = PushDevice.__table__
REGS = ActivityKitRegistration.__table__
SECRET = "s" * 43
OTHER_SECRET = "t" * 43
TOKEN = "ab" * 32
START = "cd" * 32
VERSIONS = Path(__file__).resolve().parents[2] / "alembic" / "versions"


def _url():
    url = make_url(DB_URL)
    assert url.get_backend_name() == "postgresql", "PostgreSQL gate requires PostgreSQL"
    assert url.database == "bl_searchtest", "Only the hosted disposable test database is permitted"
    return url


@pytest.fixture
async def pg():
    url = _url()
    schema = "push_devices_test_" + uuid4().hex
    admin = create_async_engine(url)
    async with admin.begin() as conn:
        await conn.execute(text(f'CREATE SCHEMA "{schema}"'))
    engine = create_async_engine(url, connect_args={"server_settings": {"search_path": schema}})
    async with engine.begin() as conn:
        await conn.execute(text("CREATE TABLE users(id INTEGER PRIMARY KEY)"))
        await conn.execute(text("CREATE TABLE events(id INTEGER PRIMARY KEY)"))
        await conn.execute(text("INSERT INTO users VALUES (1), (2)"))
        await conn.execute(text("INSERT INTO events VALUES (42), (43)"))
        await conn.run_sync(DEVICES.create)
        await conn.run_sync(REGS.create)
        await conn.run_sync(ActivityKitDelivery.__table__.create)
        await conn.run_sync(UserPin.__table__.create)
    yield async_sessionmaker(engine, expire_on_commit=False)
    await engine.dispose()
    async with admin.begin() as conn:
        await conn.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
    await admin.dispose()


@pytest.fixture
async def client(pg):
    app = FastAPI()
    app.include_router(devices.router)
    app.include_router(activitykit.router)

    async def database():
        async with pg() as session:
            yield session

    def _user(request: Request):
        uid = request.headers.get("x-test-user")
        return SimpleNamespace(id=int(uid)) if uid else None

    async def current(request: Request):
        user = _user(request)
        if user is None:
            raise HTTPException(401, "Authentication required")
        return user

    async def optional(request: Request):
        return _user(request)

    app.dependency_overrides[get_db_rw] = database
    app.dependency_overrides[get_current_user] = current
    app.dependency_overrides[get_optional_user] = optional
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t") as c:
        yield c


def state(**changes):
    return {
        "platform": "ios",
        "apns_env": "production",
        "notification_token": TOKEN,
        "la_start_token": START,
        "os_major": 18,
        "app_version": "1.0.8",
        "pinned_event_ids": [42, 43, 42],
        "pinned_market_ids": [7],
        **changes,
    }


async def put(client, device, body, secret=SECRET):
    return await client.put(f"/api/devices/{device}", json=body, headers={"X-Device-Secret": secret})


async def stored(pg, device):
    async with pg() as db:
        return (await db.execute(select(DEVICES).where(DEVICES.c.device_id == device))).mappings().one_or_none()


async def test_a_phone_registers_without_an_account_and_no_response_carries_a_token(client, pg):
    device = uuid4()
    first = await put(client, device, state())
    assert first.status_code == 200
    body = first.json()
    assert body["pinned_event_ids"] == [42, 43] and body["pinned_market_ids"] == [7]
    assert body["notification_token_on_file"] is True and body["la_start_token_on_file"] is True
    assert body["signed_in"] is False
    got = await client.get(f"/api/devices/{device}", headers={"X-Device-Secret": SECRET})
    for response in (first, got):
        assert TOKEN not in response.text and START not in response.text and SECRET not in response.text
    row = await stored(pg, device)
    assert row["notification_token"] == TOKEN and row["la_start_token"] == START
    assert row["secret_hash"] != SECRET and len(row["secret_hash"]) == 64
    assert row["la_start_token_at"] is not None and row["user_id"] is None


async def test_the_secret_guards_every_later_request(client, pg):
    device = uuid4()
    assert (await put(client, device, state())).status_code == 200
    changed = await put(client, device, state(pinned_event_ids=[]), secret=OTHER_SECRET)
    assert changed.status_code == 403
    assert (await stored(pg, device))["pinned_event_ids"] == [42, 43]
    assert (await client.get(f"/api/devices/{device}", headers={"X-Device-Secret": OTHER_SECRET})).status_code == 403
    assert (await client.get(f"/api/devices/{device}")).status_code == 401
    assert (await client.get(f"/api/devices/{uuid4()}", headers={"X-Device-Secret": SECRET})).status_code == 404
    assert (await client.delete(f"/api/devices/{device}", headers={"X-Device-Secret": OTHER_SECRET})).status_code == 403
    assert await stored(pg, device) is not None


async def test_a_token_that_reappears_under_a_new_id_moves_to_it(client, pg):
    old, new = uuid4(), uuid4()
    assert (await put(client, old, state())).status_code == 200
    assert (await put(client, new, state(), secret=OTHER_SECRET)).status_code == 200
    was = await stored(pg, old)
    now = await stored(pg, new)
    assert was["notification_token"] is None and was["la_start_token"] is None
    assert now["notification_token"] == TOKEN and now["la_start_token"] == START


async def test_the_kickoff_sender_finds_every_phone_that_pinned_the_game(client, pg):
    a, b, c = uuid4(), uuid4(), uuid4()
    await put(client, a, state(notification_token=None, la_start_token=None, pinned_event_ids=[42]))
    await put(client, b, state(notification_token=None, la_start_token=None, pinned_event_ids=[43, 42]))
    await put(client, c, state(notification_token=None, la_start_token=None, pinned_event_ids=[43]))
    async with pg() as db:
        found = set(
            (await db.execute(select(DEVICES.c.device_id).where(DEVICES.c.pinned_event_ids.contains([42])))).scalars()
        )
    assert found == {a, b}


async def test_the_start_token_time_is_stamped_kept_and_cleared(client, pg):
    device = uuid4()
    await put(client, device, state())
    first = (await stored(pg, device))["la_start_token_at"]
    await put(client, device, state())
    assert (await stored(pg, device))["la_start_token_at"] == first
    await put(client, device, state(la_start_token=None))
    row = await stored(pg, device)
    assert row["la_start_token"] is None and row["la_start_token_at"] is None


async def test_an_app_clip_row_never_holds_a_start_token_and_a_bad_body_echoes_nothing(client):
    clip = uuid4()
    refused = await put(client, clip, state(platform="appclip"))
    assert refused.status_code == 422 and START not in refused.text
    assert (await put(client, clip, state(platform="appclip", la_start_token=None))).status_code == 200
    too_many = await put(client, uuid4(), state(pinned_event_ids=list(range(1, 202))))
    assert too_many.status_code == 422
    bad = await put(client, uuid4(), state(notification_token="zz" + TOKEN))
    assert bad.status_code == 422 and TOKEN not in bad.text


async def test_a_phone_owns_its_live_activity_and_forgetting_the_phone_ends_it(client, pg):
    device = uuid4()
    await put(client, device, state())
    headers = {"X-Device-Id": str(device), "X-Device-Secret": SECRET}
    registration = {"event_id": 42, "expected_version": 0, "mutation_id": str(uuid4()), "push_token": "ef" * 32}
    made = await client.put("/api/activitykit/registrations/activity-a", json=registration, headers=headers)
    assert made.status_code == 200, made.text
    async with pg() as db:
        row = (await db.execute(select(REGS).where(REGS.c.activity_id == "activity-a"))).mappings().one()
    assert row["device_id"] == device and row["user_id"] is None
    assert (await client.get("/api/activitykit/registrations/activity-a", headers=headers)).status_code == 200
    other = uuid4()
    await put(client, other, state(notification_token=None, la_start_token=None), secret=OTHER_SECRET)
    stranger = {"X-Device-Id": str(other), "X-Device-Secret": OTHER_SECRET}
    assert (await client.get("/api/activitykit/registrations/activity-a", headers=stranger)).status_code == 404
    wrong = {"X-Device-Id": str(device), "X-Device-Secret": OTHER_SECRET}
    assert (await client.get("/api/activitykit/registrations/activity-a", headers=wrong)).status_code == 403
    assert (await client.get("/api/activitykit/registrations/activity-a")).status_code == 401
    gone = await client.delete(f"/api/devices/{device}", headers={"X-Device-Secret": SECRET})
    assert gone.status_code == 204
    assert await stored(pg, device) is None
    async with pg() as db:
        assert (await db.execute(select(REGS).where(REGS.c.activity_id == "activity-a"))).first() is None


async def test_signing_in_claims_the_phone_and_its_pins_follow_the_reader(client, pg):
    device = uuid4()
    await put(client, device, state())
    async with pg() as db:
        await db.execute(UserPin.__table__.insert().values(user_id=1, pin_type="event", target_id=42))
        await db.commit()
    unsigned = await client.post(f"/api/devices/{device}/claim", headers={"X-Device-Secret": SECRET})
    assert unsigned.status_code == 401
    claimed = await client.post(
        f"/api/devices/{device}/claim", headers={"X-Device-Secret": SECRET, "X-Test-User": "1"}
    )
    assert claimed.status_code == 200 and claimed.json()["signed_in"] is True
    assert (await stored(pg, device))["user_id"] == 1
    async with pg() as db:
        pins = set((await db.execute(select(UserPin.pin_type, UserPin.target_id).where(UserPin.user_id == 1))).all())
    assert pins == {("event", 42), ("event", 43), ("future", 7)}


def _migration(name):
    spec = importlib.util.spec_from_file_location(name, VERSIONS / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_the_migration_upgrades_refuses_an_ownerless_activity_and_downgrades():
    from alembic.migration import MigrationContext
    from alembic.operations import Operations
    from sqlalchemy.exc import IntegrityError

    url = _url().set(drivername="postgresql+psycopg2")
    schema = "push_devices_mig_" + uuid4().hex
    engine = create_engine(url)
    try:
        with engine.begin() as conn:
            conn.exec_driver_sql(f'CREATE SCHEMA "{schema}"')
            conn.exec_driver_sql(f'SET LOCAL search_path TO "{schema}"')
            conn.exec_driver_sql("CREATE TABLE users(id int PRIMARY KEY); CREATE TABLE events(id int PRIMARY KEY)")
            conn.exec_driver_sql("INSERT INTO users VALUES (1); INSERT INTO events VALUES (42)")
            with Operations.context(MigrationContext.configure(conn)):
                _migration("activitykit_registration").upgrade()
                _migration("activitykit_credential_expiry").upgrade()
                conn.exec_driver_sql(
                    "INSERT INTO activitykit_registrations(activity_id,user_id,event_id,version,is_active,"
                    "mutation_id,request_hash) VALUES ('signed-in',1,42,1,true,'m','h')"
                )
                migration = _migration("push_devices_177a")
                migration.upgrade()
                conn.exec_driver_sql(
                    "INSERT INTO push_devices(device_id,secret_hash,platform,apns_env) VALUES "
                    "('7c9e6679-7425-40de-944b-e07fc1f90ae7', repeat('a',64), 'ios', 'production')"
                )
                conn.exec_driver_sql(
                    "INSERT INTO activitykit_registrations(activity_id,device_id,event_id,version,is_active,"
                    "mutation_id,request_hash) VALUES ('phone','7c9e6679-7425-40de-944b-e07fc1f90ae7',42,1,true,'m','h')"
                )
                with pytest.raises(IntegrityError):
                    with conn.begin_nested():
                        conn.exec_driver_sql(
                            "INSERT INTO activitykit_registrations(activity_id,event_id,version,is_active,"
                            "mutation_id,request_hash) VALUES ('nobody',42,1,true,'m','h')"
                        )
                with pytest.raises(IntegrityError):
                    with conn.begin_nested():
                        conn.exec_driver_sql(
                            "INSERT INTO push_devices(device_id,secret_hash,platform,apns_env,la_start_token) VALUES "
                            "('8c9e6679-7425-40de-944b-e07fc1f90ae7', repeat('a',64), 'appclip', 'production', 'ab')"
                        )
                migration.downgrade()
                kept = [r[0] for r in conn.exec_driver_sql("SELECT activity_id FROM activitykit_registrations")]
                assert kept == ["signed-in"]
                assert conn.exec_driver_sql("SELECT to_regclass('push_devices')").scalar() is None
    finally:
        with engine.begin() as conn:
            conn.exec_driver_sql(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE')
        engine.dispose()
