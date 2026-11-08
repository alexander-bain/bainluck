"""Only a completed worker read can replace ceremony evidence."""

import asyncio
import json
from contextlib import contextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from app.services import awards_occasion_snapshot as snapshot
from app.services.awards_occasion_source import AwardsOccasionSourceError
from app.tasks import awards_occasions as worker, redis_state
from app.utils.awards_occasion_finder import find_awards_occasions


def discovered():
    return find_awards_occasions(
        [
            {
                "provider": "kalshi",
                "event_ticker": "KXNEW-PIC27",
                "title": "Best Picture",
                "markets": [{"rules_primary": "At the 99th Academy Awards."}],
            }
        ]
    )


async def test_complete_pass_publishes_reproducible_proposals_without_licensing_them(
    monkeypatch,
):
    client = SimpleNamespace(setex=Mock(return_value=True))
    monkeypatch.setattr(redis_state, "get_redis_client", lambda: client)
    reader = AsyncMock(return_value=discovered())
    monkeypatch.setattr(worker, "read_live", reader)
    result = await worker.refresh_awards_occasions()
    reader.assert_awaited_once_with("all")
    assert result["terminal"] == "complete"
    assert result["occasions"] == result["provider_events"] == 1
    assert result["model_cost_usd"] == 0
    key, ttl, raw = client.setex.call_args.args
    assert key == snapshot.AWARDS_OCCASION_CACHE_KEY
    assert ttl == snapshot.AWARDS_OCCASION_CACHE_SECONDS
    payload = json.loads(raw)
    assert (
        snapshot.discovery_from_snapshot(payload, now=payload["observed_at"])
        == discovered()
    )
    assert payload["state"] == "proposed"


async def test_failed_source_withdraws_the_previous_snapshot_and_preserves_the_error(
    monkeypatch,
):
    client = SimpleNamespace(setex=Mock(return_value=True))
    monkeypatch.setattr(redis_state, "get_redis_client", lambda: client)
    monkeypatch.setattr(
        worker, "read_live", AsyncMock(side_effect=TimeoutError("source deadline"))
    )
    with pytest.raises(TimeoutError, match="source deadline"):
        await worker.refresh_awards_occasions()
    failed = json.loads(client.setex.call_args.args[2])
    with pytest.raises(
        AwardsOccasionSourceError, match="source_unavailable:TimeoutError"
    ):
        snapshot.discovery_from_snapshot(failed, now=failed["observed_at"])


async def test_a_failed_cache_write_is_never_a_completed_refresh(monkeypatch):
    client = SimpleNamespace(setex=Mock(return_value=False))
    monkeypatch.setattr(redis_state, "get_redis_client", lambda: client)
    monkeypatch.setattr(worker, "read_live", AsyncMock(return_value=discovered()))
    with pytest.raises(AwardsOccasionSourceError, match="source_snapshot_not_written"):
        await worker.refresh_awards_occasions()


async def test_missing_redis_stops_before_the_source_read(monkeypatch):
    monkeypatch.setattr(redis_state, "get_redis_client", lambda: None)
    reader = AsyncMock()
    monkeypatch.setattr(worker, "read_live", reader)
    with pytest.raises(AwardsOccasionSourceError, match="source_unavailable:redis"):
        await worker.refresh_awards_occasions()
    reader.assert_not_awaited()


def test_registered_refresh_is_hourly_on_background_with_its_own_runtime_limits():
    from app import tasks

    entry = tasks.celery_app.conf.beat_schedule["refresh-awards-occasions-hourly"]
    assert entry["task"] == "app.tasks.refresh_awards_occasions"
    assert entry["schedule"].minute == {47}
    assert entry["options"]["queue"] == "background"
    assert entry["options"]["expires"] == 3600
    assert tasks.celery_app.conf.task_routes[entry["task"]] == {"queue": "background"}
    registered = tasks.celery_app.tasks[entry["task"]]
    assert registered.soft_time_limit == 120
    assert registered.time_limit == 150


def test_disabled_definitions_return_before_the_lease_or_source(monkeypatch):
    from app import tasks
    from app.utils import roundup_containers, single_flight

    monkeypatch.setattr(roundup_containers, "ROUNDUP_PRODUCERS", {})
    lease = Mock(side_effect=AssertionError("unexpected lease"))
    refresh = AsyncMock(side_effect=AssertionError("unexpected source read"))
    monkeypatch.setattr(single_flight, "single_flight", lease)
    monkeypatch.setattr(worker, "refresh_awards_occasions", refresh)
    result = tasks.refresh_awards_occasions.run()
    assert result == {
        "terminal": "skipped",
        "reason": "ceremony_definitions_disabled",
        "model_cost_usd": 0,
    }
    lease.assert_not_called()
    refresh.assert_not_awaited()


@pytest.mark.parametrize("reason", ["already_running", "redis_unavailable"])
def test_an_unavailable_lease_cannot_launch_a_publisher(monkeypatch, reason):
    from app import tasks
    from app.utils import roundup_containers, single_flight

    producer = SimpleNamespace(
        rule={"producer": "awards_ceremony"}, enabled=lambda: True
    )
    monkeypatch.setattr(roundup_containers, "ROUNDUP_PRODUCERS", {"fixture": producer})

    @contextmanager
    def lease(task_name, ttl_seconds):
        assert task_name == "app.tasks.refresh_awards_occasions" and ttl_seconds == 180
        yield SimpleNamespace(
            acquired=reason != "already_running",
            reason=reason,
            skipped_result=lambda: {"skipped": True, "reason": reason},
        )

    refresh = AsyncMock(side_effect=AssertionError("unexpected source read"))
    monkeypatch.setattr(single_flight, "single_flight", lease)
    monkeypatch.setattr(worker, "refresh_awards_occasions", refresh)
    if reason == "redis_unavailable":
        with pytest.raises(RuntimeError, match="evidence lease unavailable"):
            tasks.refresh_awards_occasions.run()
    else:
        assert tasks.refresh_awards_occasions.run() == {
            "skipped": True,
            "reason": reason,
        }
    refresh.assert_not_awaited()


def test_enabled_definition_dispatches_the_owned_refresh_under_the_lease(monkeypatch):
    from app import tasks
    from app.utils import roundup_containers, single_flight

    producer = SimpleNamespace(
        rule={"producer": "awards_ceremony"}, enabled=lambda: True
    )
    monkeypatch.setattr(roundup_containers, "ROUNDUP_PRODUCERS", {"fixture": producer})

    @contextmanager
    def lease(task_name, ttl_seconds):
        assert task_name == "app.tasks.refresh_awards_occasions" and ttl_seconds == 180
        yield SimpleNamespace(acquired=True, reason="acquired")

    expected = {"terminal": "complete", "occasions": 1, "model_cost_usd": 0}
    refresh = AsyncMock(return_value=expected)

    def tracked(task_name, awaitable):
        assert task_name == "awards_occasions"
        return asyncio.run(awaitable)

    monkeypatch.setattr(single_flight, "single_flight", lease)
    monkeypatch.setattr(worker, "refresh_awards_occasions", refresh)
    monkeypatch.setattr(tasks, "_tracked_run", tracked)
    assert tasks.refresh_awards_occasions.run() == expected
    refresh.assert_awaited_once()
