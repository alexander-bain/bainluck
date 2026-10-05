"""Real SQL CAS/uniqueness and signed-in route behavior; no device or APNs."""

from types import SimpleNamespace
from uuid import uuid4

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest
from sqlalchemy import create_engine, event, insert, select, update
from sqlalchemy.pool import StaticPool

from app.dependencies.auth import get_current_user
from app.models.activitykit import ActivityKitRegistration
from app.routes import activitykit
from app.services.database import Base, get_db_rw

TABLE = ActivityKitRegistration.__table__
TOKEN, NEW_TOKEN = "ab" * 32, "cd" * 32


class Database:
    def __init__(self):
        self.engine = create_engine(
            "sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False}
        )

        @event.listens_for(self.engine, "connect")
        def foreign_keys(connection, _):
            connection.execute("PRAGMA foreign_keys=ON")

        self.connection = self.engine.connect()
        for sql in [
            "CREATE TABLE users(id INTEGER PRIMARY KEY)",
            "CREATE TABLE events(id INTEGER PRIMARY KEY)",
            "INSERT INTO users VALUES (1), (2)",
            "INSERT INTO events VALUES (42), (43)",
        ]:
            self.connection.exec_driver_sql(sql)
        TABLE.create(self.connection)
        self.connection.commit()
        self.before_write = None

    async def execute(self, statement):
        if self.before_write and (
            getattr(statement, "is_insert", False)
            or getattr(statement, "is_update", False)
        ):
            hook, self.before_write = self.before_write, None
            hook(self.connection)
        return self.connection.execute(statement)

    async def commit(self):
        self.connection.commit()

    async def rollback(self):
        self.connection.rollback()

    def row(self, identity="activity-a"):
        return (
            self.connection.execute(
                select(TABLE).where(TABLE.c.activity_id == identity)
            )
            .mappings()
            .one_or_none()
        )


@pytest.fixture
def db():
    value = Database()
    yield value
    value.connection.close()
    value.engine.dispose()


def client(db, user=1):
    app = FastAPI()
    app.include_router(activitykit.router)

    async def database():
        return db

    app.dependency_overrides[get_db_rw] = database
    if user is not None:
        app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(id=user)
    return TestClient(app)


def body(version=0, token=TOKEN, **changes):
    return {
        "event_id": 42,
        "expected_version": version,
        "mutation_id": str(uuid4()),
        "push_token": token,
        **changes,
    }


def put(c, value, identity="activity-a"):
    return c.put(f"/api/activitykit/registrations/{identity}", json=value)


def revoke(c, value):
    return c.request(
        "DELETE",
        "/api/activitykit/registrations/activity-a",
        json={k: v for k, v in value.items() if k != "push_token"},
    )


def test_missing_auth_rejected_before_invalid_large_secret_body(db):
    c = client(db, None)
    for raw in ['{"push_token":"' + TOKEN, TOKEN * 200]:
        response = c.put("/api/activitykit/registrations/activity-a", content=raw)
        assert response.status_code == 401
        assert TOKEN not in response.text
    assert db.row() is None


def test_create_replay_replace_and_get_expose_server_version_only(db):
    c, initial = client(db), body()
    first = put(c, initial)
    assert first.status_code == 200
    assert first.json() == {
        "activity_id": "activity-a",
        "event_id": 42,
        "version": 1,
        "is_active": True,
    }
    assert put(c, initial).json() == first.json()
    replacement = body(1, NEW_TOKEN)
    second = put(c, replacement)
    assert second.json()["version"] == 2
    assert db.row()["push_token"] == NEW_TOKEN
    assert put(c, replacement).json() == second.json()
    assert c.get("/api/activitykit/registrations/activity-a").json() == second.json()
    assert put(c, initial).status_code == 409
    assert db.row()["push_token"] == NEW_TOKEN


def test_replay_with_changed_token_or_action_conflicts(db):
    c, initial = client(db), body()
    assert put(c, initial).status_code == 200
    assert put(c, {**initial, "push_token": NEW_TOKEN}).status_code == 409
    assert revoke(c, initial).status_code == 409
    assert db.row()["push_token"] == TOKEN


def test_owner_and_canonical_event_immutable(db):
    c, other = client(db), client(db, 2)
    assert put(c, body()).status_code == 200
    assert other.get("/api/activitykit/registrations/activity-a").status_code == 404
    assert put(other, body()).status_code == 409
    assert revoke(other, body(1)).status_code == 404
    assert put(c, body(1, event_id=43)).status_code == 409
    assert (db.row()["user_id"], db.row()["event_id"]) == (1, 42)


def test_tombstone_erases_token_and_blocks_delayed_or_new_registration(db):
    c, initial = client(db), body()
    assert put(c, initial).status_code == 200
    deletion = body(1)
    result = revoke(c, deletion)
    assert result.json()["version"] == 2 and not result.json()["is_active"]
    assert revoke(c, deletion).json() == result.json()
    assert db.row()["push_token"] is None and db.row()["token_hash"] is None
    assert put(c, initial).status_code == 409
    assert put(c, body(2)).status_code == 409
    assert not db.row()["is_active"]


@pytest.mark.parametrize("revoked", [False, True])
def test_atomic_cas_rejects_intervening_mutation_after_lookup(db, revoked):
    c = client(db)
    assert put(c, body()).status_code == 200

    def concurrent(connection):
        connection.execute(
            update(TABLE).values(
                version=2,
                is_active=not revoked,
                push_token=None if revoked else NEW_TOKEN,
                token_hash=None,
            )
        )
        connection.commit()

    db.before_write = concurrent
    assert put(c, body(1, "ef" * 32)).status_code == 409
    assert db.row()["version"] == 2
    assert db.row()["push_token"] == (None if revoked else NEW_TOKEN)


def test_concurrent_create_preserves_first_owner_and_event(db):
    def concurrent(connection):
        connection.execute(
            insert(TABLE).values(
                activity_id="activity-a",
                user_id=2,
                event_id=43,
                version=1,
                is_active=True,
                push_token=NEW_TOKEN,
                token_hash="f" * 64,
                mutation_id=str(uuid4()),
                request_hash="e" * 64,
            )
        )
        connection.commit()

    db.before_write = concurrent
    assert put(client(db), body()).status_code == 409
    assert (db.row()["user_id"], db.row()["event_id"]) == (2, 43)


def test_unique_token_error_never_leaks_or_mutates(db, caplog):
    assert put(client(db), body()).status_code == 200
    response = put(client(db, 2), body(), "activity-b")
    assert response.status_code == 409
    assert TOKEN not in response.text and TOKEN[:8] not in caplog.text
    assert db.row("activity-b") is None


@pytest.mark.parametrize("token", [None, 1, "secret-token", TOKEN + "Z"])
def test_invalid_secret_error_is_generic(db, caplog, token):
    response = put(client(db), body(token=token))
    assert response.status_code == 422
    assert response.json() == {"detail": "Invalid registration request"}
    assert str(token) not in caplog.text


def test_unknown_event_stale_version_and_body_bound_do_not_create(db):
    c = client(db)
    assert put(c, body(event_id=999)).status_code == 404
    assert put(c, body(3)).status_code == 404
    assert (
        c.put(
            "/api/activitykit/registrations/activity-a", content=TOKEN * 100
        ).status_code
        == 413
    )
    assert db.row() is None


def test_account_deletion_cascades_registration_credential_and_metadata_registered(db):
    assert put(client(db), body()).status_code == 200
    db.connection.exec_driver_sql("DELETE FROM users WHERE id=1")
    db.connection.commit()
    assert db.row() is None
    assert "activitykit_registrations" in Base.metadata.tables
    assert next(iter(TABLE.c.user_id.foreign_keys)).ondelete == "CASCADE"


def test_revoke_before_first_register_tombstones_delayed_create(db):
    c = client(db)
    deletion = body()
    result = revoke(c, deletion)
    assert result.status_code == 200 and not result.json()["is_active"]
    assert revoke(c, deletion).json() == result.json()
    assert put(c, body()).status_code == 409
    assert db.row()["push_token"] is None and db.row()["token_hash"] is None


def test_concurrent_revoke_wins_delayed_initial_create(db):
    def concurrent(connection):
        connection.execute(
            insert(TABLE).values(
                activity_id="activity-a",
                user_id=1,
                event_id=42,
                version=1,
                is_active=False,
                push_token=None,
                token_hash=None,
                mutation_id=str(uuid4()),
                request_hash="e" * 64,
            )
        )
        connection.commit()

    db.before_write = concurrent
    assert put(client(db), body()).status_code == 409
    assert not db.row()["is_active"]
    assert db.row()["push_token"] is None


def test_create_winning_revoke_race_requires_fresh_version_then_tombstones(db):
    def concurrent(connection):
        connection.execute(
            insert(TABLE).values(
                activity_id="activity-a",
                user_id=1,
                event_id=42,
                version=1,
                is_active=True,
                push_token=TOKEN,
                token_hash="f" * 64,
                mutation_id=str(uuid4()),
                request_hash="e" * 64,
            )
        )
        connection.commit()

    c = client(db)
    db.before_write = concurrent
    assert revoke(c, body()).status_code == 409
    version = c.get("/api/activitykit/registrations/activity-a").json()["version"]
    assert revoke(c, body(version)).status_code == 200
    assert db.row()["push_token"] is None


def test_operational_database_failure_does_not_expose_bound_token(db, caplog):
    from sqlalchemy.exc import OperationalError

    def failure(_):
        raise OperationalError(
            "SQL WITH SECRET", {"push_token": TOKEN}, Exception(TOKEN)
        )

    db.before_write = failure
    response = put(client(db), body())
    assert response.status_code == 503
    assert TOKEN not in response.text and TOKEN not in caplog.text
    assert db.row() is None
