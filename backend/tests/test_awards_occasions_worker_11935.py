"""Only a completed worker read can replace ceremony evidence."""

import json
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
