"""W3.2 wire/authority guards; no Apple services or device state required."""

from dataclasses import replace
from datetime import datetime, timedelta, timezone
import json

import pytest

from app.utils.activitykit_payload import (
    ActivityKitPayloadError,
    GameActivitySnapshot,
    MAX_PAYLOAD_BYTES,
    build_activitykit_end,
    build_activitykit_update,
)

SENT = datetime(2026, 10, 5, 12, 0, tzinfo=timezone.utc)


def snapshot(**changes):
    fields = {
        "event_id": 101,
        "home_team": "Giants",
        "away_team": "Dodgers",
        "lifecycle": "live",
        "home_score": 3,
        "away_score": 2,
        "home_rendered_percent": 46,
        "score_observed_at": SENT - timedelta(seconds=30),
        "probability_observed_at": SENT - timedelta(seconds=10),
    }
    fields.update(changes)
    return GameActivitySnapshot(**fields)


def aps(push):
    body = json.loads(push.body)
    assert set(body) == {"aps"}
    return body["aps"]


def test_update_matches_swift_content_state_default_date_wire_contract():
    # Independent golden values: Date Codable defaults to seconds since 2001,
    # while APNs timestamp/stale-date use Unix seconds. No ISO8601 strategy.
    push = build_activitykit_update(snapshot(), sent_at=SENT)
    assert aps(push) == {
        "timestamp": 1791201600,
        "event": "update",
        "content-state": {
            "snapshot": {
                "eventID": 101,
                "homeTeam": "Giants",
                "awayTeam": "Dodgers",
                "lifecycle": "live",
                "homeScore": 3,
                "awayScore": 2,
                "homeRenderedPercent": 46,
                "scoreObservedAt": 812894370,
                "probabilityObservedAt": 812894390,
            }
        },
        "stale-date": 1791201690,
    }
    assert push.headers == {
        "apns-push-type": "liveactivity",
        "apns-priority": "5",
        "apns-expiration": "0",
    }


def test_fractional_producer_clock_and_timezone_survive_without_redating():
    observed = datetime(
        2026, 10, 5, 14, 59, 50, 125000, tzinfo=timezone(timedelta(hours=3))
    )
    reading = snapshot(probability_observed_at=observed)
    state = aps(build_activitykit_update(reading, sent_at=SENT))["content-state"][
        "snapshot"
    ]
    assert state["probabilityObservedAt"] == 812894390.125
    assert state["scoreObservedAt"] == 812894370


@pytest.mark.parametrize("missing", ["score_observed_at", "probability_observed_at"])
def test_unknown_displayed_clock_is_omitted_and_marks_stale_now(missing):
    reading = snapshot(**{missing: None})
    result = aps(build_activitykit_update(reading, sent_at=SENT))
    clock_key = (
        "scoreObservedAt" if missing == "score_observed_at" else "probabilityObservedAt"
    )
    assert clock_key not in result["content-state"]["snapshot"]
    assert result["stale-date"] == result["timestamp"]


def test_old_reading_does_not_get_fresh_expiry_from_send_time():
    reading = snapshot(score_observed_at=SENT - timedelta(minutes=5))
    first = aps(build_activitykit_update(reading, sent_at=SENT))
    later = aps(build_activitykit_update(reading, sent_at=SENT + timedelta(minutes=1)))
    assert first["stale-date"] == 1791201420 < first["timestamp"]
    assert later["stale-date"] == first["stale-date"]
    assert later["content-state"] == first["content-state"]
    assert later["timestamp"] > first["timestamp"]


def test_probability_only_reading_uses_its_clock_not_an_absent_score_clock():
    reading = snapshot(home_score=None, away_score=None, score_observed_at=None)
    result = aps(build_activitykit_update(reading, sent_at=SENT))
    assert result["stale-date"] == 1791201710
    assert "homeScore" not in result["content-state"]["snapshot"]
    assert "scoreObservedAt" not in result["content-state"]["snapshot"]


def test_score_only_reading_uses_its_clock_and_never_invents_probability():
    reading = snapshot(home_rendered_percent=None, probability_observed_at=None)
    result = aps(build_activitykit_update(reading, sent_at=SENT))
    assert result["stale-date"] == 1791201690
    assert "homeRenderedPercent" not in result["content-state"]["snapshot"]
    assert "probabilityObservedAt" not in result["content-state"]["snapshot"]


@pytest.mark.parametrize("lifecycle", ["suspended", "unknown"])
def test_unavailable_lifecycle_is_not_reclassified_as_final(lifecycle):
    reading = snapshot(
        lifecycle=lifecycle,
        home_score=None,
        away_score=None,
        home_rendered_percent=None,
        score_observed_at=None,
        probability_observed_at=None,
    )
    result = aps(build_activitykit_update(reading, sent_at=SENT))
    assert result["event"] == "update"
    assert result["content-state"]["snapshot"]["lifecycle"] == lifecycle
    assert result["stale-date"] == result["timestamp"]
    with pytest.raises(ActivityKitPayloadError):
        build_activitykit_end(reading, sent_at=SENT)


@pytest.mark.parametrize("percent", [0, 100])
def test_extreme_probability_is_still_an_update_and_cannot_end(percent):
    reading = snapshot(home_rendered_percent=percent)
    result = aps(build_activitykit_update(reading, sent_at=SENT))
    assert result["event"] == "update"
    assert result["content-state"]["snapshot"]["homeRenderedPercent"] == percent
    with pytest.raises(ActivityKitPayloadError):
        build_activitykit_end(reading, sent_at=SENT)


@pytest.mark.parametrize("lifecycle", ["final", "closed"])
def test_authoritative_terminal_push_retains_real_score_clock_and_no_forecast(
    lifecycle,
):
    reading = snapshot(
        lifecycle=lifecycle,
        home_rendered_percent=None,
        probability_observed_at=None,
        score_observed_at=SENT - timedelta(minutes=5),
    )
    result = aps(build_activitykit_end(reading, sent_at=SENT))
    assert set(result) == {"timestamp", "event", "content-state"}
    assert result["event"] == "end"
    state = result["content-state"]["snapshot"]
    assert state["lifecycle"] == lifecycle
    assert state["scoreObservedAt"] == 812894100
    assert "homeRenderedPercent" not in state
    assert "probabilityObservedAt" not in state
    assert "winner" not in state and "isDraw" not in state
    with pytest.raises(ActivityKitPayloadError):
        build_activitykit_update(reading, sent_at=SENT)


def test_final_missing_scores_stays_missing_not_zero_or_winner():
    reading = snapshot(
        lifecycle="final",
        home_score=None,
        away_score=None,
        home_rendered_percent=None,
        score_observed_at=None,
        probability_observed_at=None,
    )
    state = aps(build_activitykit_end(reading, sent_at=SENT))["content-state"][
        "snapshot"
    ]
    assert set(state) == {"eventID", "homeTeam", "awayTeam", "lifecycle"}


def test_explicit_stop_dismisses_without_inventing_final_lifecycle():
    result = aps(build_activitykit_end(snapshot(), sent_at=SENT, reason="stop"))
    assert result["event"] == "end"
    assert result["dismissal-date"] == 1791201599 < result["timestamp"]
    assert result["content-state"]["snapshot"]["lifecycle"] == "live"
    assert "alert" not in result and "sound" not in result


def test_no_offline_storage_or_routine_alerts_for_update_or_end():
    pushes = [
        build_activitykit_update(snapshot(), sent_at=SENT),
        build_activitykit_end(snapshot(), sent_at=SENT, reason="stop"),
    ]
    for push in pushes:
        assert push.headers["apns-expiration"] == "0"
        assert push.headers["apns-priority"] == "5"
        assert (
            not {"alert", "sound", "badge", "attributes", "attributes-type"}
            & aps(push).keys()
        )


@pytest.mark.parametrize(
    "fields",
    [
        {"event_id": 0},
        {"event_id": True},
        {"event_id": 1 << 63},
        {"home_team": " "},
        {"away_team": None},
        {"home_score": -1},
        {"home_score": True},
        {"away_score": 2.5},
        {"home_rendered_percent": -1},
        {"home_rendered_percent": 101},
        {"home_rendered_percent": True},
        {"home_rendered_percent": 46.0},
        {"home_rendered_percent": float("nan")},
        {"lifecycle": "completed"},
        {"lifecycle": "final"},
        {"lifecycle": "closed"},
        {"lifecycle": "suspended"},
        {"home_rendered_percent": None},
        {"score_observed_at": SENT.replace(tzinfo=None)},
        {"probability_observed_at": "2026-10-05T12:00:00Z"},
    ],
)
def test_invalid_snapshot_fields_fail_closed(fields):
    with pytest.raises(ActivityKitPayloadError):
        snapshot(**fields)


@pytest.mark.parametrize("field", ["score_observed_at", "probability_observed_at"])
def test_future_producer_clock_is_rejected_not_replaced_by_send_time(field):
    reading = snapshot(**{field: SENT + timedelta(microseconds=1)})
    with pytest.raises(ActivityKitPayloadError):
        build_activitykit_update(reading, sent_at=SENT)


def test_send_time_is_explicit_aware_and_end_reason_is_explicit():
    with pytest.raises(TypeError):
        build_activitykit_update(snapshot())
    with pytest.raises(ActivityKitPayloadError):
        build_activitykit_update(snapshot(), sent_at=SENT.replace(tzinfo=None))
    with pytest.raises(ActivityKitPayloadError):
        build_activitykit_update(
            snapshot(), sent_at=datetime(1960, 1, 1, tzinfo=timezone.utc)
        )
    with pytest.raises(ActivityKitPayloadError):
        build_activitykit_end(snapshot(), sent_at=SENT, reason="probability_extreme")
    with pytest.raises(ActivityKitPayloadError):
        build_activitykit_update({}, sent_at=SENT)


def test_utf8_payload_size_is_bounded_in_bytes_and_boundary_is_inclusive():
    base = snapshot(home_team="A")
    baseline = len(build_activitykit_update(base, sent_at=SENT).body)
    exact = replace(base, home_team="A" * (1 + MAX_PAYLOAD_BYTES - baseline))
    assert len(build_activitykit_update(exact, sent_at=SENT).body) == MAX_PAYLOAD_BYTES
    with pytest.raises(ActivityKitPayloadError):
        build_activitykit_update(
            replace(exact, home_team=exact.home_team + "A"), sent_at=SENT
        )
    # Character count alone would accept this; UTF-8 byte accounting must not.
    with pytest.raises(ActivityKitPayloadError):
        build_activitykit_update(replace(base, home_team="é" * 2200), sent_at=SENT)


def test_invalid_unicode_never_escapes_as_an_undeliverable_body():
    with pytest.raises(ActivityKitPayloadError):
        build_activitykit_update(snapshot(home_team="\ud800"), sent_at=SENT)
