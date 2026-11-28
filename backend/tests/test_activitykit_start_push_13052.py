"""Tests for kickoff Live Activity push-to-start (#13052 / 254-A / 178-B)."""

from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
import json
from unittest.mock import AsyncMock, patch
from uuid import UUID, uuid4

import pytest

from app.services.activitykit_apns import APNsResult
from app.services.activitykit_start_dispatch import (
    DEDUP_TTL_SECONDS,
    build_kickoff_event_ids_query,
    dispatch_kickoff_starts,
)
from app.services.push_audience import KickoffPlan, StartTarget
from app.tasks import celery_app
from app.tasks.activitykit_start import run_activitykit_start_dispatch
from app.utils.activitykit_payload import ActivityKitPayloadError, GameActivitySnapshot
from app.utils.activitykit_start_payload import (
    GAME_ACTIVITY_ATTRIBUTES_TYPE,
    START_STALE_WINDOW,
    build_activitykit_start,
    build_activitykit_start_alert,
)

# Fixed historical clock (well outside wall-clock fixture checks).
_T0 = datetime(2001, 10, 15, 23, 0, 0, tzinfo=timezone.utc)


def _live_snapshot(
    *,
    home_pct: int | None = 62,
    prob_age_seconds: int | None = 30,
    score_age_seconds: int | None = 20,
    lifecycle: str = "live",
) -> GameActivitySnapshot:
    return GameActivitySnapshot(
        event_id=4201,
        home_team="Boston Celtics",
        away_team="New York Knicks",
        lifecycle=lifecycle,
        home_score=2 if lifecycle == "live" else 110,
        away_score=0 if lifecycle == "live" else 104,
        home_rendered_percent=home_pct if lifecycle in {"scheduled", "live"} else None,
        score_observed_at=(
            _T0 - timedelta(seconds=score_age_seconds)
            if score_age_seconds is not None
            else None
        ),
        probability_observed_at=(
            _T0 - timedelta(seconds=prob_age_seconds)
            if prob_age_seconds is not None and home_pct is not None and lifecycle in {"scheduled", "live"}
            else None
        ),
    )


class _MemoryDedup:
    def __init__(self) -> None:
        self.claimed: set[tuple[int, UUID]] = set()
        self.released: list[tuple[int, UUID]] = []

    async def claim(self, event_id: int, device_id: UUID, ttl_seconds: int) -> bool:
        assert ttl_seconds == DEDUP_TTL_SECONDS
        key = (event_id, device_id)
        if key in self.claimed:
            return False
        self.claimed.add(key)
        return True

    async def release(self, event_id: int, device_id: UUID) -> None:
        key = (event_id, device_id)
        self.claimed.discard(key)
        self.released.append(key)


class _FakeTransport:
    def __init__(self, env: str, outcomes: list[APNsResult]) -> None:
        self.env = env
        self.outcomes = list(outcomes)
        self.calls: list[dict] = []

    async def send(self, command, *, activity_token: str, provider_token: str) -> APNsResult:
        self.calls.append(
            {
                "env": self.env,
                "command_id": command.command_id,
                "body": json.loads(command.push.body.decode("utf-8")),
                "headers": dict(command.push.headers),
                "token": activity_token,
                "jwt": provider_token,
            }
        )
        return self.outcomes.pop(0) if self.outcomes else APNsResult("accepted", "apns_accepted")


class _FakeTransportPool:
    def __init__(self, outcomes_by_env: dict[str, list[APNsResult]] | None = None) -> None:
        outcomes_by_env = outcomes_by_env or {}
        self.by_env = {
            "production": _FakeTransport("production", outcomes_by_env.get("production", [])),
            "sandbox": _FakeTransport("sandbox", outcomes_by_env.get("sandbox", [])),
        }

    def for_env(self, apns_env: str):
        return self.by_env["sandbox" if apns_env == "sandbox" else "production"]

    async def aclose(self) -> None:
        pass


class _DummyDB:
    def __init__(self) -> None:
        self.committed = 0

    async def commit(self) -> None:
        self.committed += 1


def _dummy_sessions(db: _DummyDB):
    @asynccontextmanager
    async def _ctx():
        yield db

    return _ctx


# --- Payload contract tests ---


def test_start_payload_shape_ios18_with_input_push_token():
    snap = _live_snapshot(home_pct=62, prob_age_seconds=30)
    push = build_activitykit_start(snap, sent_at=_T0, input_push_token=True)

    assert push.priority == "10"
    assert push.headers == {
        "apns-push-type": "liveactivity",
        "apns-priority": "10",
        "apns-expiration": "0",
    }
    parsed = json.loads(push.body.decode("utf-8"))
    aps = parsed["aps"]
    assert aps["event"] == "start"
    assert aps["attributes-type"] == GAME_ACTIVITY_ATTRIBUTES_TYPE
    assert aps["attributes"] == {"eventID": 4201}
    assert aps["input-push-token"] == 1
    assert aps["timestamp"] == int(_T0.timestamp())
    assert aps["stale-date"] == int((_T0 + START_STALE_WINDOW).timestamp())
    assert aps["content-state"] == snap.content_state()
    assert aps["alert"] == {
        "title": "New York Knicks at Boston Celtics",
        "body": "Starting now · Boston Celtics 62%",
    }


def test_start_payload_omits_input_push_token_on_ios17():
    snap = _live_snapshot(home_pct=35, prob_age_seconds=10)
    push = build_activitykit_start(snap, sent_at=_T0, input_push_token=False)
    aps = json.loads(push.body.decode("utf-8"))["aps"]
    assert "input-push-token" not in aps
    assert aps["alert"]["body"] == "Starting now · New York Knicks 65%"


def test_start_alert_omits_number_when_probability_is_old_or_missing():
    old_snap = _live_snapshot(home_pct=62, prob_age_seconds=600)
    assert build_activitykit_start_alert(old_snap, sent_at=_T0) == {
        "title": "New York Knicks at Boston Celtics",
        "body": "Starting now",
    }
    no_prob_snap = _live_snapshot(home_pct=None, prob_age_seconds=None)
    assert build_activitykit_start_alert(no_prob_snap, sent_at=_T0) == {
        "title": "New York Knicks at Boston Celtics",
        "body": "Starting now",
    }


def test_start_alert_never_prints_zero_or_hundred_percent():
    snap_zero = _live_snapshot(home_pct=0, prob_age_seconds=10)
    assert build_activitykit_start_alert(snap_zero, sent_at=_T0)["body"] == (
        "Starting now · New York Knicks >99%"
    )
    snap_hundred = _live_snapshot(home_pct=100, prob_age_seconds=10)
    assert build_activitykit_start_alert(snap_hundred, sent_at=_T0)["body"] == (
        "Starting now · Boston Celtics >99%"
    )
    snap_sub_one = GameActivitySnapshot(
        event_id=4201,
        home_team="Boston Celtics",
        away_team="New York Knicks",
        lifecycle="live",
        home_score=2,
        away_score=0,
        home_rendered_percent=1,
        away_rendered_percent=99,
        home_sub_one=True,
        away_above_ninety_nine=True,
        score_observed_at=_T0 - timedelta(seconds=10),
        probability_observed_at=_T0 - timedelta(seconds=10),
    )
    assert build_activitykit_start_alert(snap_sub_one, sent_at=_T0)["body"] == (
        "Starting now · New York Knicks >99%"
    )
    snap_above_99 = GameActivitySnapshot(
        event_id=4201,
        home_team="Boston Celtics",
        away_team="New York Knicks",
        lifecycle="live",
        home_score=2,
        away_score=0,
        home_rendered_percent=99,
        away_rendered_percent=1,
        home_above_ninety_nine=True,
        away_sub_one=True,
        score_observed_at=_T0 - timedelta(seconds=10),
        probability_observed_at=_T0 - timedelta(seconds=10),
    )
    assert build_activitykit_start_alert(snap_above_99, sent_at=_T0)["body"] == (
        "Starting now · Boston Celtics >99%"
    )


def test_start_payload_rejects_non_live_lifecycles():
    for lifecycle in ("scheduled", "final", "closed", "suspended", "unknown"):
        snap = _live_snapshot(lifecycle=lifecycle)
        with pytest.raises(ActivityKitPayloadError):
            build_activitykit_start(snap, sent_at=_T0)


# --- Dispatcher orchestration tests ---


@pytest.mark.asyncio
async def test_dispatch_routes_prod_and_sandbox_dedups_and_handles_410_and_retry():
    dev_prod = uuid4()
    dev_sandbox = uuid4()
    dev_active = uuid4()
    dev_410 = uuid4()
    dev_retry = uuid4()

    targets = [
        StartTarget(dev_prod, "production", True, "1.0.8", "aa" * 32),
        StartTarget(dev_sandbox, "sandbox", False, "1.0.8", "bb" * 32),
        StartTarget(dev_active, "production", True, "1.0.8", "cc" * 32),
        StartTarget(dev_410, "production", True, "1.0.8", "dd" * 32),
        StartTarget(dev_retry, "sandbox", True, "1.0.8", "ee" * 32),
    ]

    pool = _FakeTransportPool(
        outcomes_by_env={
            "production": [
                APNsResult("accepted", "apns_accepted"),
                APNsResult("unavailable", "token_unregistered"),
            ],
            "sandbox": [
                APNsResult("accepted", "apns_accepted"),
                APNsResult("retry", "apns_transient"),
            ],
        }
    )
    dedup = _MemoryDedup()
    db = _DummyDB()

    live_detail = {
        "id": 4201,
        "home_team": "Boston Celtics",
        "away_team": "New York Knicks",
        "status": "live",
        "home_score": 4,
        "away_score": 2,
        "score_observed_at": (_T0 - timedelta(seconds=10)).isoformat(),
        "hero_probability": 0.62,
        "hero_probability_observed_at": (_T0 - timedelta(seconds=15)).isoformat(),
    }

    async def _fake_finder(_db, _ts):
        return [4201]

    async def _fake_reader(_db, event_id: int):
        assert event_id == 4201
        return live_detail

    async def _fake_jwt():
        return "hdr.pay.sig"

    with (
        patch(
            "app.services.activitykit_start_dispatch.kickoff_plan",
            new=AsyncMock(return_value=KickoffPlan(start=targets, alert=[], next_after=None)),
        ),
        patch(
            "app.services.activitykit_start_dispatch._active_device_ids_for_event",
            new=AsyncMock(return_value={dev_active}),
        ),
        patch(
            "app.services.activitykit_start_dispatch.forget_token",
            new=AsyncMock(return_value=1),
        ) as mock_forget,
    ):
        summary = await dispatch_kickoff_starts(
            _dummy_sessions(db),
            pool,
            _fake_jwt,
            dedup,
            now=_T0,
            detail_reader=_fake_reader,
            candidate_finder=_fake_finder,
        )

    assert summary.events_scanned == 1
    assert summary.attempted == 4
    assert summary.accepted == 2
    assert summary.skipped_active == 1
    assert summary.skipped_dedup == 0
    assert summary.token_forgotten == 1
    assert summary.retryable == 1
    assert summary.rejected == 0

    # Production received dev_prod (iOS 18 -> input-push-token) and dev_410.
    assert len(pool.by_env["production"].calls) == 2
    assert pool.by_env["production"].calls[0]["body"]["aps"]["input-push-token"] == 1
    # Sandbox received dev_sandbox (iOS 17 -> no input-push-token) and dev_retry.
    assert len(pool.by_env["sandbox"].calls) == 2
    assert "input-push-token" not in pool.by_env["sandbox"].calls[0]["body"]["aps"]

    # APNs 410 forgot the dead token and committed.
    mock_forget.assert_awaited_once_with(db, "la_start_token", "dd" * 32)
    assert db.committed == 1

    # Transient retry released its dedup key; accepted/410 keys stayed claimed.
    assert (4201, dev_retry) in dedup.released
    assert (4201, dev_retry) not in dedup.claimed
    assert (4201, dev_prod) in dedup.claimed
    assert (4201, dev_sandbox) in dedup.claimed

    # Second beat immediately after skips already-claimed phones and retries only dev_retry.
    pool2 = _FakeTransportPool(
        outcomes_by_env={"sandbox": [APNsResult("accepted", "apns_accepted")]}
    )
    with (
        patch(
            "app.services.activitykit_start_dispatch.kickoff_plan",
            new=AsyncMock(return_value=KickoffPlan(start=targets, alert=[], next_after=None)),
        ),
        patch(
            "app.services.activitykit_start_dispatch._active_device_ids_for_event",
            new=AsyncMock(return_value={dev_active}),
        ),
    ):
        summary2 = await dispatch_kickoff_starts(
            _dummy_sessions(db),
            pool2,
            _fake_jwt,
            dedup,
            now=_T0 + timedelta(seconds=30),
            detail_reader=_fake_reader,
            candidate_finder=_fake_finder,
        )

    assert summary2.attempted == 1
    assert summary2.accepted == 1
    assert summary2.skipped_dedup == 3
    assert summary2.skipped_active == 1


@pytest.mark.asyncio
async def test_task_is_default_off_and_scheduled():
    with patch.dict("os.environ", {}, clear=True):
        result = await run_activitykit_start_dispatch()
    assert result == {"status": "disabled", "terminal": "skipped"}

    assert "app.tasks.deliver_activitykit_starts" in celery_app.tasks
    schedule = celery_app.conf.beat_schedule["activitykit-start-push"]
    assert schedule["task"] == "app.tasks.deliver_activitykit_starts"
    assert schedule["schedule"] == 30.0
    assert schedule["options"]["queue"] == "realtime"


def test_kickoff_query_compiles_pg_array_contains_for_gin_index():
    from sqlalchemy.dialects import postgresql

    sql = str(
        build_kickoff_event_ids_query(now=_T0).compile(dialect=postgresql.dialect())
    )
    assert "push_devices.pinned_event_ids @> ARRAY[events.id]" in sql
    assert "push_devices.la_start_token IS NOT NULL" in sql
    assert "push_devices.platform !=" in sql

