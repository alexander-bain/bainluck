"""Admission policy boundaries, using the existing league importance authority."""
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from app.utils.highlights import get_league_tier
from app.utils.preview_reservations import (
    RESERVATIONS_ENV,
    ReservationPolicy,
    reservation_context,
)


AT = datetime(2026, 10, 23, 20, tzinfo=timezone.utc)


def event(**changes):
    values = dict(
        sport_key="basketball_nba", status="live", completed_at=None,
        commence_time=AT - timedelta(minutes=30), preview_context_at=AT,
    )
    values.update(changes)
    return SimpleNamespace(**values)


@pytest.mark.parametrize("sport_key,tier,active_bucket", [
    ("basketball_nba", 1, 0),
    ("icehockey_nhl", 1, 0),
    ("soccer_germany_bundesliga", 2, 2),
    ("soccer_usa_mls", 2, 2),
    ("tennis_atp_us_open", 2, 2),
    ("tennis_wta_wimbledon", 2, 2),
    ("tennis_atp", 4, 4),
    ("tennis_atp_dubai", 4, 4),
    ("soccer_fa_cup", 3, 4),
    ("unrecognized_league", 4, 4),
    (None, 4, 4),
])
def test_existing_tier_authority_and_tennis_fallback(sport_key, tier, active_bucket):
    assert get_league_tier(sport_key) == tier
    active = reservation_context(event(sport_key=sport_key), 7)
    upcoming = reservation_context(event(
        sport_key=sport_key, status="scheduled", commence_time=AT + timedelta(hours=1)
    ), 7)
    assert active.bucket == active_bucket
    assert upcoming.bucket == active_bucket + 1


@pytest.mark.parametrize("offset,bucket", [
    (timedelta(microseconds=-1), 0),
    (timedelta(0), 0),
    (timedelta(microseconds=1), 1),
    (timedelta(hours=6), 1),
    (timedelta(hours=6, microseconds=1), 6),
    (timedelta(days=7), 6),
])
def test_scheduled_window_has_exact_edges(offset, bucket):
    result = reservation_context(event(status="scheduled", commence_time=AT + offset), 7)
    assert result.bucket == bucket


def test_undated_scheduled_game_cannot_hoard_in_play_reservation():
    assert reservation_context(event(status="scheduled", commence_time=None), 7).bucket == 6


@pytest.mark.parametrize("status", ["live", "suspended"])
def test_authoritative_in_play_status_survives_missing_start(status):
    assert reservation_context(event(status=status, commence_time=None), 7).bucket == 0


@pytest.mark.parametrize("changes", [
    {"status": "completed"}, {"status": "cancelled"},
    {"status": "live", "completed_at": AT},
])
def test_terminal_or_completed_context_cannot_get_reservation(changes):
    assert reservation_context(event(**changes), 7).bucket == 6


def test_unknown_league_is_distinct_from_missing_authoritative_context():
    candidate = event()
    del candidate.sport_key
    assert reservation_context(candidate, 7) is None
    assert reservation_context(event(sport_key=None), 7).bucket == 4


@pytest.mark.parametrize("changes,revision", [
    ({"preview_context_at": None}, 7),
    ({"preview_context_at": AT.replace(tzinfo=None)}, 7),
    ({"status": "scheduled", "commence_time": AT.replace(tzinfo=None)}, 7),
    ({}, -1), ({}, True), ({}, 9007199254740992),
])
def test_unusable_context_refuses_instead_of_inventing_priority(changes, revision):
    assert reservation_context(event(**changes), revision) is None


def test_default_budget_preserves_total_and_protected_capacity(monkeypatch):
    monkeypatch.delenv(RESERVATIONS_ENV, raising=False)
    policy = ReservationPolicy.configured()
    assert policy.limits == (192, 64, 128, 64, 48, 16)
    assert policy.total == 512


def test_bounded_custom_policy_changes_identity(monkeypatch):
    default = ReservationPolicy()
    monkeypatch.setenv(RESERVATIONS_ENV, "3,1,2,1,1,1")
    custom = ReservationPolicy.configured()
    assert custom.total == 9
    assert custom.fingerprint != default.fingerprint


@pytest.mark.parametrize("raw", [
    "", "1,2", "1024,1,0,0,0,0", "0,0,0,0,0,0",
    "-1,1,1,1,1,1", "1.5,1,1,1,1,1", "١,1,1,1,1,1",
])
def test_invalid_configuration_fails_closed(monkeypatch, raw):
    monkeypatch.setenv(RESERVATIONS_ENV, raw)
    with pytest.raises(ValueError):
        ReservationPolicy.configured()
