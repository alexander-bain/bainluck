"""#13000 (Decision 250-A): carry scoreSourceUnavailable in Live Activity APNs pushes.

Matches Swift ``GameActivitySnapshot`` (#13059): present-only ``true`` when a live
game has no scores and ``score_source_unavailable`` is ``true`` on the served
event detail; omitted on covered live games, scheduled games, and finals so
1.0.6 payloads stay byte-identical.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json

import pytest

from app.utils.activitykit_delivery_state import (
    DeliveryState,
    RetryPolicy,
    reader_view,
)
from app.utils.activitykit_payload import (
    ActivityKitPayloadError,
    GameActivitySnapshot,
    build_activitykit_update,
)
from app.utils.activitykit_projection import project_activitykit_snapshot

T0 = datetime(2026, 6, 15, 19, 0, tzinfo=timezone.utc)


def _live_tennis_detail(
    *,
    score_source_unavailable: bool | None = True,
    home_score: int | None = None,
    away_score: int | None = None,
    status: str = "live",
) -> dict:
    detail: dict = {
        "id": 15350957,
        "home_team": "Hsu",
        "away_team": "Zhou",
        "status": status,
        "sport": "tennis_atp",
        "home_score": home_score,
        "away_score": away_score,
        "score_source": "statpal" if home_score is not None else None,
        "score_observed_at": T0.isoformat() if home_score is not None else None,
        "hero_probability": {
            "home": 0.624,
            "away": 0.376,
            "observed_at": T0.isoformat(),
        },
    }
    if score_source_unavailable is not None:
        detail["score_source_unavailable"] = score_source_unavailable
    return detail


def test_scoreless_live_match_projects_and_encodes_score_source_unavailable():
    snap = project_activitykit_snapshot(_live_tennis_detail(score_source_unavailable=True))
    assert snap.score_source_unavailable is True

    push = build_activitykit_update(snap, sent_at=T0 + timedelta(seconds=10))
    wire = json.loads(push.body.decode("utf-8"))
    content = wire["aps"]["content-state"]["snapshot"]
    assert content["scoreSourceUnavailable"] is True
    assert "homeScore" not in content
    assert "awayScore" not in content


def test_covered_scheduled_and_final_matches_omit_score_source_unavailable():
    covered = project_activitykit_snapshot(
        _live_tennis_detail(score_source_unavailable=False)
    )
    assert covered.score_source_unavailable is None
    assert "scoreSourceUnavailable" not in covered.content_state()["snapshot"]

    # Even if a caller passes score_source_unavailable=True alongside real scores,
    # the projection strips it so the score renders.
    scored = project_activitykit_snapshot(
        _live_tennis_detail(
            score_source_unavailable=True, home_score=1, away_score=0
        )
    )
    assert scored.score_source_unavailable is None
    assert "scoreSourceUnavailable" not in scored.content_state()["snapshot"]

    scheduled = project_activitykit_snapshot(
        _live_tennis_detail(score_source_unavailable=True, status="scheduled")
    )
    assert scheduled.score_source_unavailable is None
    assert "scoreSourceUnavailable" not in scheduled.content_state()["snapshot"]

    final = project_activitykit_snapshot(
        _live_tennis_detail(score_source_unavailable=True, status="completed")
    )
    assert final.score_source_unavailable is None
    assert "scoreSourceUnavailable" not in final.content_state()["snapshot"]


@pytest.mark.parametrize(
    "kwargs",
    [
        {"lifecycle": "live", "score_source_unavailable": False},
        {"lifecycle": "live", "home_score": 1, "away_score": 0, "score_source_unavailable": True},
        {"lifecycle": "scheduled", "score_source_unavailable": True},
        {"lifecycle": "final", "score_source_unavailable": True},
    ],
)
def test_snapshot_rejects_invalid_score_source_unavailable(kwargs):
    with pytest.raises(ActivityKitPayloadError):
        GameActivitySnapshot(
            event_id=15350957,
            home_team="Hsu",
            away_team="Zhou",
            **kwargs,
        )


def test_flipping_score_source_unavailable_changes_reader_view_and_sends_priority_10():
    base = GameActivitySnapshot(
        event_id=15350957,
        home_team="Hsu",
        away_team="Zhou",
        lifecycle="live",
        home_rendered_percent=62,
        away_rendered_percent=38,
        probability_observed_at=T0,
    )
    flagged = GameActivitySnapshot(
        event_id=15350957,
        home_team="Hsu",
        away_team="Zhou",
        lifecycle="live",
        home_rendered_percent=62,
        away_rendered_percent=38,
        probability_observed_at=T0 + timedelta(seconds=15),
        score_source_unavailable=True,
    )
    assert reader_view(base) != reader_view(flagged)

    state = DeliveryState(
        activity_id="act-250a",
        event_id=15350957,
        retry_policy=RetryPolicy((timedelta(seconds=30),)),
    )
    state = state.observe(base, revision=1)
    state, first = state.dispatch(now=T0 + timedelta(seconds=5))
    assert first is not None and first.push.priority == "10"

    # Simulate accepted first send, then flag turns on 15s later (well inside
    # QUIET_REFRESH_SECONDS=120) -> must still dispatch immediately at priority 10.
    state = state.complete(first.attempt_id, now=T0 + timedelta(seconds=6))
    state = state.observe(flagged, revision=2)
    state, second = state.dispatch(now=T0 + timedelta(seconds=20))
    assert second is not None
    assert second.push.priority == "10"
    wire = json.loads(second.push.body.decode("utf-8"))
    assert wire["aps"]["content-state"]["snapshot"]["scoreSourceUnavailable"] is True
