"""A source outage or expired proposal cannot become a current ceremony set."""

from copy import deepcopy
import json
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from app.services import awards_occasion_snapshot as snapshot
from app.services.awards_occasion_source import AwardsOccasionSourceError
from app.utils.awards_occasion_finder import OccasionDiscovery, find_awards_occasions

NOW = 1794175200.0


def discovery():
    return find_awards_occasions(
        [
            {
                "provider": "kalshi",
                "event_ticker": "KXNEW-PIC27",
                "title": "Best Picture",
                "markets": [
                    {"rules_primary": "If Film A wins at the 99th Academy Awards."}
                ],
            },
            {
                "provider": "polymarket",
                "id": "123456",
                "title": "Best Screenplay",
                "markets": [
                    {"rules_primary": "If Film B wins at the 99th Academy Awards."}
                ],
            },
        ]
    )


def test_source_evidence_round_trips_without_inferred_dates_or_permission():
    expected = discovery()
    expected = OccasionDiscovery(
        expected.occasions, (("kalshi", "KXMISSING-27", "provider_event_missing"),)
    )
    encoded = snapshot.occasion_snapshot(expected, observed_at=NOW)
    actual = snapshot.discovery_from_snapshot(encoded, now=NOW)
    assert actual == expected
    assert actual.occasions[0].level == "member"
    assert actual.occasions[0].state == "proposed"
    assert actual.occasions[0].ceremony_date is None


@pytest.mark.parametrize(
    "change,reason",
    [
        (lambda p: p.update(version=2), "source_snapshot_malformed"),
        (lambda p: p.update(state="licensed"), "source_snapshot_malformed"),
        (lambda p: p.update(observed_at=True), "source_snapshot_malformed"),
        (lambda p: p.update(observed_at=float("nan")), "source_snapshot_malformed"),
        (lambda p: p.update(observed_at=NOW + 1), "source_snapshot_malformed"),
        (lambda p: p.update(events={}), "source_snapshot_malformed"),
        (
            lambda p: p.update(refused=[["missing", "reason"]]),
            "source_snapshot_malformed",
        ),
        (
            lambda p: p["events"][0].update(provider="unknown"),
            "source_snapshot_malformed",
        ),
        (
            lambda p: p.update(
                observed_at=NOW - snapshot.AWARDS_OCCASION_CACHE_SECONDS
            ),
            "source_snapshot_stale",
        ),
        (
            lambda p: p.update(state="unavailable", reason="HTTPStatusError"),
            "source_unavailable:HTTPStatusError",
        ),
    ],
)
def test_an_invalid_or_failed_snapshot_retains_its_refusal(change, reason):
    payload = deepcopy(snapshot.occasion_snapshot(discovery(), observed_at=NOW))
    change(payload)
    with pytest.raises(AwardsOccasionSourceError, match=reason):
        snapshot.discovery_from_snapshot(payload, now=NOW)


async def test_missing_cache_is_explicit_and_performs_no_source_or_database_read(
    monkeypatch,
):
    from app.tasks import redis_state

    client = SimpleNamespace(get=Mock(return_value=None))
    monkeypatch.setattr(redis_state, "get_redis_client", lambda: client)
    db = SimpleNamespace(
        execute=Mock(side_effect=AssertionError("unexpected database read"))
    )
    with pytest.raises(AwardsOccasionSourceError, match="source_snapshot_missing"):
        await snapshot.read_cached_awards_occasions(db)
    client.get.assert_called_once_with(snapshot.AWARDS_OCCASION_CACHE_KEY)
    db.execute.assert_not_called()


@pytest.mark.parametrize("raw", ["{", "null"])
async def test_bad_cache_json_is_a_failure(monkeypatch, raw):
    from app.tasks import redis_state

    monkeypatch.setattr(
        redis_state,
        "get_redis_client",
        lambda: SimpleNamespace(get=Mock(return_value=raw)),
    )
    with pytest.raises(AwardsOccasionSourceError, match="source_snapshot_malformed"):
        await snapshot.read_cached_awards_occasions(object())


def test_expired_evidence_can_only_supply_worker_fetch_seeds():
    payload = snapshot.occasion_snapshot(discovery(), observed_at=NOW)
    later = NOW + snapshot.AWARDS_OCCASION_CACHE_SECONDS + 1
    with pytest.raises(AwardsOccasionSourceError, match="source_snapshot_stale"):
        snapshot.discovery_from_snapshot(payload, now=later)
    assert (
        snapshot.discovery_from_snapshot(payload, now=later, allow_expired=True)
        == discovery()
    )
    with pytest.raises(AwardsOccasionSourceError, match="source_snapshot_malformed"):
        snapshot.discovery_from_snapshot(payload, now=NOW - 1, allow_expired=True)


async def test_oversized_cache_is_refused_before_decoding(monkeypatch):
    from app.tasks import redis_state

    raw = json.dumps(snapshot.occasion_snapshot(discovery(), observed_at=NOW))
    raw += " " * snapshot.AWARDS_OCCASION_MAX_BYTES
    monkeypatch.setattr(
        redis_state,
        "get_redis_client",
        lambda: SimpleNamespace(get=Mock(return_value=raw)),
    )
    with pytest.raises(AwardsOccasionSourceError, match="source_snapshot_too_large"):
        await snapshot.read_cached_awards_occasions(object())
