"""177-A / 178-B wiring that needs no database. The routes, phone-owned
activities and the migration run on real Postgres in
``tests/integration/test_push_devices_177a_pg.py``."""

import importlib.util
from pathlib import Path

import pytest
from fastapi import HTTPException

from app.dependencies import device_auth
from app.models.activitykit import ActivityKitRegistration
from app.models.push_device import PushDevice
from app.routes import devices

BACKEND = Path(__file__).resolve().parents[1]
MIGRATION = BACKEND / "alembic" / "versions" / "push_devices_177a.py"


def _migration():
    spec = importlib.util.spec_from_file_location("push_devices_177a", MIGRATION)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_the_router_is_mounted_in_both_places():
    main = (BACKEND / "app" / "main.py").read_text()
    package = (BACKEND / "app" / "routes" / "__init__.py").read_text()
    assert "app.include_router(devices.router)" in main
    assert '"devices"' in package


def test_the_migration_is_migration_class_and_its_id_fits():
    module = _migration()
    assert module.revision == "push_devices_177a" and len(module.revision) <= 32
    assert "MIGRATION-CLASS" in module.__doc__


def test_the_model_and_the_migration_create_the_same_columns():
    source = MIGRATION.read_text()
    for column in PushDevice.__table__.columns:
        assert f'"{column.name}"' in source, column.name
    names = {"ck_push_devices_platform", "ck_push_devices_apns_env", "ck_push_devices_appclip_no_la"}
    for name in names:
        assert name in source
    assert {c.name for c in PushDevice.__table__.constraints if c.name} >= names


def test_an_activity_may_belong_to_a_phone_but_never_to_nobody():
    table = ActivityKitRegistration.__table__
    assert table.c.user_id.nullable and table.c.device_id.nullable
    checks = {c.name: str(c.sqltext) for c in table.constraints if c.name}
    assert checks["ck_activitykit_registrations_owner"] == "user_id IS NOT NULL OR device_id IS NOT NULL"


@pytest.mark.parametrize("secret", [None, "", "short", "x" * 31, "x" * 257, "has space" + "x" * 30])
def test_a_missing_or_malformed_secret_is_refused(secret):
    with pytest.raises(HTTPException) as refused:
        device_auth.checked_secret(secret)
    assert refused.value.status_code == 401


def test_only_the_hash_is_stored_and_the_comparison_is_by_hash():
    secret = "k" * 43
    stored = device_auth.secret_hash(secret)
    assert stored != secret and len(stored) == 64
    assert device_auth.secret_matches(stored, secret)
    assert not device_auth.secret_matches(stored, "j" * 43)


def test_the_public_shape_says_whether_a_token_is_on_file_and_never_names_it():
    row = {
        "device_id": "7c9e6679-7425-40de-944b-e07fc1f90ae7",
        "platform": "ios",
        "pinned_event_ids": [42],
        "pinned_market_ids": [],
        "notification_token": "ab" * 32,
        "la_start_token": None,
        "user_id": None,
        "secret_hash": "a" * 64,
    }
    public = devices._public(row)
    assert public["notification_token_on_file"] is True
    assert public["la_start_token_on_file"] is False
    assert "ab" * 32 not in repr(public) and "a" * 64 not in repr(public)
