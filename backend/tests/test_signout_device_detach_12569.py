"""Tests for #12569 server half: signed-in sign-out detach + legacy unsigned path."""

from __future__ import annotations

import inspect
from types import SimpleNamespace
from unittest.mock import AsyncMock

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.dialects.postgresql import dialect as postgresql_dialect
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.dependencies.auth import get_current_user, get_optional_user
from app.models.models import DeviceToken
from app.routes import notifications
from app.services.database import get_db_rw

VICTIM_ID, STRANGER_ID = 42, 7


class _CaptureDB:
    def __init__(self, rowcount: int = 1) -> None:
        self.execute = AsyncMock(return_value=SimpleNamespace(rowcount=rowcount))
        self.commit = AsyncMock()


def _client(db, *, current_user=None, optional_user=None) -> TestClient:
    app = FastAPI()
    app.include_router(notifications.router)

    async def _db():
        return db

    app.dependency_overrides[get_db_rw] = _db
    if current_user is not None:
        async def _curr():
            return current_user

        app.dependency_overrides[get_current_user] = _curr
    if optional_user is not None or current_user is None:
        async def _opt():
            return optional_user

        app.dependency_overrides[get_optional_user] = _opt
    return TestClient(app)


def test_unregister_requires_get_current_user_and_returns_401_unsigned():
    sig = inspect.signature(notifications.unregister_device_token)
    deps = [p.default.dependency for p in sig.parameters.values() if hasattr(p.default, "dependency")]
    assert get_current_user in deps

    db = _CaptureDB()
    client = _client(db, current_user=None, optional_user=None)
    resp = client.post(
        "/api/notifications/unregister",
        json={
            "device_token": "a" * 32,
            "platform": "ios",
            "session_id": "sess-1",
            "token_kind": "apns",
        },
    )
    assert resp.status_code == 401
    db.execute.assert_not_awaited()
    db.commit.assert_not_awaited()


@pytest.mark.parametrize(
    ("platform", "token_kind", "expected_kind"),
    [
        ("ios", "apns", "apns"),
        ("macos", "fcm", "fcm"),
        ("ios", None, "apns"),
    ],
)
def test_unregister_accepts_app_shape_and_filters_by_user_id(
    platform: str, token_kind: str | None, expected_kind: str
):
    db = _CaptureDB(rowcount=1)
    client = _client(db, current_user=SimpleNamespace(id=VICTIM_ID))

    body: dict[str, object] = {
        "device_token": "b" * 32,
        "platform": platform,
        "session_id": "sess-signout-99",
    }
    if token_kind is not None:
        body["token_kind"] = token_kind

    resp = client.post(
        "/api/notifications/unregister",
        json=body,
        headers={
            "Authorization": "Bearer " + "x" * 16,
            "X-Session-Id": "sess-signout-99",
        },
    )
    assert resp.status_code == 200, resp.text
    assert resp.json() == {"status": "ok", "detached": True, "token_kind": expected_kind}
    db.execute.assert_awaited_once()
    db.commit.assert_awaited_once()

    compiled = db.execute.await_args.args[0].compile(dialect=postgresql_dialect())
    sql_text = str(compiled)
    assert "UPDATE device_tokens" in sql_text
    assert "device_tokens.device_token" in sql_text
    assert "device_tokens.user_id" in sql_text
    assert VICTIM_ID in compiled.params.values()
    assert ("b" * 32) in compiled.params.values()


class _SyncBackedAsyncSession:
    """Delegate ANSI SQLAlchemy Core updates/selects to a real in-memory SQLite Session."""

    def __init__(self, session: Session) -> None:
        self._session = session

    async def execute(self, stmt):
        return self._session.execute(stmt)

    async def commit(self) -> None:
        self._session.commit()


def test_unregister_owner_vs_stranger_on_real_sqlite_and_legacy_register_kept():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    with engine.begin() as conn:
        conn.exec_driver_sql("CREATE TABLE users (id INTEGER PRIMARY KEY)")
    DeviceToken.__table__.create(engine)
    SessionLocal = sessionmaker(engine, expire_on_commit=False)

    apns_tok = "c" * 32
    fcm_tok = "d" * 32
    legacy_tok = "e" * 32
    with SessionLocal() as seed_db:
        seed_db.add(
            DeviceToken(
                device_token=apns_tok,
                platform="ios",
                token_kind="apns",
                user_id=VICTIM_ID,
                session_id="sess-old",
                is_active=True,
            )
        )
        seed_db.add(
            DeviceToken(
                device_token=fcm_tok,
                platform="ios",
                token_kind="fcm",
                user_id=VICTIM_ID,
                session_id="sess-old",
                is_active=True,
            )
        )
        seed_db.commit()

    active_user_holder: dict[str, object] = {"user": SimpleNamespace(id=STRANGER_ID)}
    app = FastAPI()
    app.include_router(notifications.router)

    async def _db_override():
        with SessionLocal() as sync_sess:
            yield _SyncBackedAsyncSession(sync_sess)

    async def _current_override():
        return active_user_holder["user"]

    app.dependency_overrides[get_db_rw] = _db_override
    app.dependency_overrides[get_current_user] = _current_override

    client = TestClient(app)

    # Stranger cannot detach victim's token via /unregister
    resp_stranger = client.post(
        "/api/notifications/unregister",
        json={
            "device_token": apns_tok,
            "platform": "ios",
            "session_id": "sess-evil",
            "token_kind": "apns",
        },
    )
    assert resp_stranger.status_code == 200
    assert resp_stranger.json()["detached"] is False

    with SessionLocal() as check_db:
        row = check_db.execute(
            select(DeviceToken).where(DeviceToken.device_token == apns_tok)
        ).scalar_one()
        assert row.user_id == VICTIM_ID
        assert row.is_active is True

    # Owner signs out and detaches both apns and fcm tokens
    active_user_holder["user"] = SimpleNamespace(id=VICTIM_ID)
    for tok, kind in (
        (apns_tok, "apns"),
        (fcm_tok, "fcm"),
    ):
        resp_owner = client.post(
            "/api/notifications/unregister",
            json={
                "device_token": tok,
                "platform": "ios",
                "session_id": "sess-signout",
                "token_kind": kind,
            },
            headers={"X-Session-Id": "sess-signout"},
        )
        assert resp_owner.status_code == 200
        assert resp_owner.json() == {"status": "ok", "detached": True, "token_kind": kind}

    with SessionLocal() as check_db:
        rows = check_db.execute(
            select(DeviceToken).order_by(DeviceToken.id.asc())
        ).scalars().all()
        assert len(rows) == 2
        assert all(r.user_id is None and r.is_active is True for r in rows)

    engine.dispose()

    # Legacy pre-1.0.8 unsigned POST /api/notifications/register still clears user_id to None
    legacy_db = _CaptureDB()
    legacy_client = _client(legacy_db, current_user=None, optional_user=None)
    res_legacy = legacy_client.post(
        "/api/notifications/register",
        json={
            "device_token": legacy_tok,
            "platform": "ios",
            "session_id": "sess-anon",
            "token_kind": "apns",
        },
    )
    assert res_legacy.status_code == 200
    assert res_legacy.json() == {"status": "ok", "token_kind": "apns"}
    params = legacy_db.execute.await_args.args[0].compile(dialect=postgresql_dialect()).params
    assert params["user_id"] is None
    assert params["param_3"] is None


def test_app_signout_ordering_sequence_leaves_device_anonymous_and_active():
    """Verify signed-in register -> signed-in unregister -> anonymous register sequence (#12569 / #13684)."""
    # 1) Signed-in registration attaches VICTIM_ID
    seq_tok = "f" * 32
    db_reg = _CaptureDB()
    c_signed = _client(db_reg, current_user=SimpleNamespace(id=VICTIM_ID), optional_user=SimpleNamespace(id=VICTIM_ID))
    r1 = c_signed.post(
        "/api/notifications/register",
        json={"device_token": seq_tok, "platform": "ios", "session_id": "s1", "token_kind": "fcm"},
    )
    assert r1.status_code == 200
    p1 = db_reg.execute.await_args.args[0].compile(dialect=postgresql_dialect()).params
    assert p1["user_id"] == VICTIM_ID and p1["param_3"] == VICTIM_ID

    # 2) Signed-in sign-out /unregister detaches VICTIM_ID while still holding Bearer
    db_unreg = _CaptureDB(rowcount=1)
    c_unreg = _client(db_unreg, current_user=SimpleNamespace(id=VICTIM_ID))
    r2 = c_unreg.post(
        "/api/notifications/unregister",
        json={"device_token": seq_tok, "platform": "ios", "session_id": "s1", "token_kind": "fcm"},
        headers={"Authorization": "Bearer " + "x" * 16, "X-Session-Id": "s1"},
    )
    assert r2.status_code == 200 and r2.json()["detached"] is True

    # 3) Subsequent anonymous /register keeps token active and anonymous
    db_anon = _CaptureDB()
    c_anon = _client(db_anon, current_user=None, optional_user=None)
    r3 = c_anon.post(
        "/api/notifications/register",
        json={"device_token": seq_tok, "platform": "ios", "session_id": "s2", "token_kind": "fcm"},
        headers={"X-Session-Id": "s2"},
    )
    assert r3.status_code == 200
    p3 = db_anon.execute.await_args.args[0].compile(dialect=postgresql_dialect()).params
    assert p3["user_id"] is None and p3["param_3"] is None and p3["param_5"] is True
