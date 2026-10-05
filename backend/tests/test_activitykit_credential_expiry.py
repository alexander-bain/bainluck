"""#10564 server authorization horizon and same-owner inactive acknowledgment."""

from datetime import timedelta
import pytest
from sqlalchemy import update
from app.routes import activitykit
from app.services.activitykit_registration_lifecycle import (
    AUTHORIZATION_LIFETIME,
    horizon_open,
)
from tests.test_activitykit_delivery_state import NOW
from tests.test_activitykit_registration import (
    client,
    body,
    put,
    revoke,
    TABLE,
    TOKEN,
    NEW_TOKEN,
)


@pytest.fixture
def db():
    from tests.test_activitykit_registration import db as original

    yield from original.__wrapped__()


@pytest.fixture(autouse=True)
def clock(monkeypatch):
    value = [NOW]
    monkeypatch.setattr(activitykit, "utc_now", lambda: value[0])
    return value


def test_first_registration_sets_nonrenewable_eight_hour_horizon(db, clock):
    c = client(db)
    initial = body()
    assert put(c, initial).status_code == 200
    created, expires = db.row()["created_at"], db.row()["expires_at"]
    assert expires - created == AUTHORIZATION_LIFETIME
    clock[0] += timedelta(hours=3)
    assert put(c, initial).status_code == 200
    assert put(c, body(1, NEW_TOKEN)).status_code == 200
    assert (db.row()["created_at"], db.row()["expires_at"]) == (created, expires)


@pytest.mark.parametrize("version", [0, 1])
def test_expired_put_sanitizes_before_mutation_replay_or_cas(db, clock, version):
    c = client(db)
    initial = body()
    assert put(c, initial).status_code == 200
    clock[0] += AUTHORIZATION_LIFETIME
    retry = initial if version == 0 else body(1, NEW_TOKEN)
    assert put(c, retry).status_code == 409
    row = db.row()
    assert not row["is_active"] and row["version"] == 2
    assert row["push_token"] is None and row["token_hash"] is None
    assert put(c, body(2)).status_code == 409
    assert db.row()["version"] == 2


@pytest.mark.parametrize("operation", ["get", "delete"])
def test_same_owner_inactive_ack_erases_expired_secret_and_is_idempotent(
    db, clock, operation
):
    c = client(db)
    assert put(c, body()).status_code == 200
    clock[0] += AUTHORIZATION_LIFETIME

    def call():
        return (
            c.get("/api/activitykit/registrations/activity-a")
            if operation == "get"
            else revoke(c, body(0))
        )

    response = call()
    assert response.status_code == 200 and not response.json()["is_active"]
    assert response.json()["version"] == 2
    assert call().json() == response.json()
    assert db.row()["push_token"] is None


def test_inactive_ack_never_cleans_other_owner_or_event(db, clock):
    c = client(db)
    assert put(c, body()).status_code == 200
    clock[0] += AUTHORIZATION_LIFETIME
    assert revoke(client(db, 2), body(1)).status_code == 404
    assert revoke(c, body(1, event_id=43)).status_code == 409
    assert db.row()["is_active"] and db.row()["push_token"] == TOKEN
    assert (
        c.get("/api/activitykit/registrations/activity-a").json()["is_active"] is False
    )


@pytest.mark.parametrize("missing", ["created_at", "expires_at"])
def test_legacy_missing_horizon_fails_closed_without_updated_at_renewal(db, missing):
    c = client(db)
    initial = body()
    assert put(c, initial).status_code == 200
    db.connection.execute(update(TABLE).values(**{missing: None}))
    db.connection.commit()
    assert put(c, initial).status_code == 409
    assert not db.row()["is_active"] and db.row()["push_token"] is None


def test_absent_delete_has_no_credentials_and_cannot_later_activate(db):
    c = client(db)
    assert revoke(c, body()).status_code == 200
    row = db.row()
    assert row["expires_at"] == row["created_at"]
    assert row["push_token"] is None and not row["is_active"]
    assert put(c, body()).status_code == 409


def test_client_cannot_provide_authorization_clock(db):
    assert (
        put(
            client(db), body(expires_at=(NOW + timedelta(days=365)).isoformat())
        ).status_code
        == 422
    )
    assert db.row() is None


@pytest.mark.parametrize(
    "offset", [timedelta(), AUTHORIZATION_LIFETIME, timedelta(hours=9)]
)
def test_horizon_boundary_uses_operational_clock_and_refuses_overlong_policy(
    db, offset
):
    assert put(client(db), body()).status_code == 200
    row = dict(db.row())
    assert horizon_open(row, NOW + offset) == (offset < AUTHORIZATION_LIFETIME)
    row["expires_at"] += timedelta(seconds=1)
    assert not horizon_open(row, NOW)
