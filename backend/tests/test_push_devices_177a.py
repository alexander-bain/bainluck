"""177-A / 178-B wiring that needs no database. The routes, phone-owned
activities and the migration run on real Postgres in
``tests/integration/test_push_devices_177a_pg.py``."""

import importlib.util
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy.dialects import postgresql

from app.dependencies import device_auth
from app.models.activitykit import ActivityKitRegistration
from app.models.push_device import PushDevice
from app.routes import devices
from app.services import push_audience as audience

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


# --- 212-A: who hears about a pinned game (app/services/push_audience.py) -----
# The queries run on real Postgres in tests/integration/test_push_devices_177a_pg.py.


NOW = datetime(2026, 1, 5, 18, 0, tzinfo=timezone.utc)


def test_the_app_clip_has_its_own_alert_topic():
    assert audience.alert_topic("ios") == "com.bainluck.Bain-Luck"
    assert audience.alert_topic("macos") == "com.bainluck.Bain-Luck"
    assert audience.alert_topic("appclip") == "com.bainluck.Bain-Luck.Clip"
    assert audience.LIVE_ACTIVITY_TOPIC == "com.bainluck.Bain-Luck.push-type.liveactivity"


@pytest.mark.parametrize(
    "have,need,ok",
    [
        ("1.0.8", None, True),
        (None, None, True),
        ("1.0.8", "1.0.8", True),
        ("1.0.10", "1.0.8", True),
        ("1.1", "1.0.8", True),
        ("1.0.7", "1.0.8", False),
        ("1.0", "1.0.0", True),
        (None, "1.0.8", False),
        ("1.0.8-beta", "1.0.8", False),
    ],
)
def test_a_start_push_goes_only_to_a_build_that_can_decode_it(have, need, ok):
    assert audience.can_take_start_push(have, need) is ok


def test_targets_keep_their_tokens_out_of_repr():
    alert = audience.AlertTarget(uuid4(), "ios", "production", audience.APP_TOPIC, token="ab" * 32)
    start = audience.StartTarget(uuid4(), "production", True, "1.0.8", token="cd" * 32)
    assert "abab" not in repr(alert) and "cdcd" not in repr(start)


def test_the_pin_match_is_the_gin_indexed_containment():
    sql = str(
        audience._pinned("event", 42).compile(dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True})
    )
    assert "pinned_event_ids @> ARRAY[42]" in sql
    assert "user_pins.pin_type = 'event'" in sql
    market = str(
        audience._pinned("market", 7).compile(dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True})
    )
    assert "pinned_market_ids @> ARRAY[7]" in market and "'future'" in market


@pytest.mark.parametrize(
    "kind,target,limit,now",
    [
        ("game", 1, 10, NOW),
        ("event", 0, 10, NOW),
        ("event", True, 10, NOW),
        ("event", 2**31, 10, NOW),
        ("event", 1, 0, NOW),
        ("event", 1, audience.MAX_PAGE + 1, NOW),
        ("event", 1, 10, NOW.replace(tzinfo=None)),
    ],
)
async def test_bad_arguments_are_refused_before_any_query(kind, target, limit, now):
    class Boom:
        async def execute(self, *_a, **_k):
            raise AssertionError("queried")

    with pytest.raises(ValueError):
        await audience.alert_targets(Boom(), kind, target, now=now, limit=limit)


async def test_kickoff_gives_each_phone_exactly_one_push(monkeypatch):
    ids = [uuid4() for _ in range(5)]
    rows = [
        # start token, iOS 18: the start push, with input-push-token
        dict(device_id=ids[0], platform="ios", apns_env="production", notification_token="aa", la_start_token="s0", os_major=18, app_version="1.0.8"),
        # start token, iOS 17: the start push, no input-push-token
        dict(device_id=ids[1], platform="ipados", apns_env="sandbox", notification_token=None, la_start_token="s1", os_major=17, app_version="1.0.8"),
        # no start token: the plain alert
        dict(device_id=ids[2], platform="ios", apns_env="production", notification_token="cc", la_start_token=None, os_major=17, app_version="1.0.7"),
        # start token on a build too old to decode it: the plain alert
        dict(device_id=ids[3], platform="ios", apns_env="production", notification_token="dd", la_start_token="s3", os_major=18, app_version="1.0.7"),
        # start token on an old build and no notification token: nothing
        dict(device_id=ids[4], platform="ios", apns_env="production", notification_token=None, la_start_token="s4", os_major=18, app_version="1.0.6"),
    ]

    async def fake_rows(*_a, **_k):
        return rows

    # An App Clip row never gets a start push, even if one ever held a start
    # token (the table's CHECK forbids it; this rule does not lean on that).
    clip = uuid4()
    rows.append(dict(device_id=clip, platform="appclip", apns_env="production", notification_token="ee", la_start_token="s5", os_major=18, app_version="1.0.8"))
    monkeypatch.setattr(audience, "_rows", fake_rows)
    plan = await audience.kickoff_plan(object(), 42, now=NOW, min_app_version="1.0.8", limit=10)
    assert plan.alert[-1].device_id == clip and plan.alert[-1].topic == audience.CLIP_TOPIC
    rows.pop()
    assert [t.device_id for t in plan.start] == ids[:2]
    assert [t.input_push_token for t in plan.start] == [True, False]
    assert [t.apns_env for t in plan.start] == ["production", "sandbox"]
    assert [t.device_id for t in plan.alert][:2] == [ids[2], ids[3]]
    assert {t.topic for t in plan.alert[:2]} == {audience.APP_TOPIC}
    assert plan.next_after is None
    full = await audience.kickoff_plan(object(), 42, now=NOW, limit=5)
    assert full.next_after == ids[4]
