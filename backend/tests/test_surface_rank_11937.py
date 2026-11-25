"""Stage 2 Step 1 (#11937): Sports tab & My Stuff on the shared surface ranking code."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.routes.feed import PersonalizationContext, _rank_key, apply_discover_display_chain
from app.utils.surface_rank import (
    DISCOVER_SURFACE_PROFILE,
    MY_STUFF_SURFACE_PROFILE,
    RankingSurfaceProfile,
    SPORTS_SURFACE_PROFILE,
    get_surface_profile,
    order_my_stuff_team_buckets,
    rank_candidates_for_surface,
    resolve_surface_profile,
    score_candidate_for_surface,
)

FROZEN_NOW = datetime(2026, 11, 25, 15, 0, 0, tzinfo=timezone.utc)


def _event(
    eid: int,
    *,
    score: float,
    status: str = "scheduled",
    hours_from_now: float = 2.0,
    home_team_id: int = 1,
    away_team_id: int = 2,
) -> dict:
    commence = (FROZEN_NOW + timedelta(hours=hours_from_now)).isoformat()
    return {
        "type": "event",
        "score": min(98, int(score)),
        "_rank_score": float(score),
        "_sort_time": (FROZEN_NOW + timedelta(hours=hours_from_now)).timestamp(),
        "headline": f"Team {away_team_id} @ Team {home_team_id}",
        "data": {
            "id": eid,
            "status": status,
            "commence_time": commence,
            "home_team_id": home_team_id,
            "away_team_id": away_team_id,
            "sport": "basketball_nba",
        },
    }


def _futures(
    fid: int,
    *,
    score: float,
    team_id: int | None = None,
    movement: float = 0.0,
) -> dict:
    return {
        "type": "futures",
        "score": min(98, int(score)),
        "_rank_score": float(score),
        "_sort_time": FROZEN_NOW.timestamp(),
        "movement_magnitude": movement,
        "headline": f"Futures {fid}",
        "data": {
            "id": fid,
            "name": f"Futures Market {fid}",
            "llm_sport_category": "basketball",
            **({"matched_team": {"id": team_id}} if team_id is not None else {}),
            "outcomes": [{"name": "Yes", "probability": 0.45}],
        },
    }


def test_resolve_surface_profile_honors_cert_2190_precedence():
    assert resolve_surface_profile() is DISCOVER_SURFACE_PROFILE
    assert resolve_surface_profile(mode="discover") is DISCOVER_SURFACE_PROFILE
    assert resolve_surface_profile(mode="sports") is SPORTS_SURFACE_PROFILE
    assert resolve_surface_profile(sports_mode=True) is SPORTS_SURFACE_PROFILE
    # CERT-2190: my_teams_only=True ALWAYS wins over sports_mode / mode='sports'.
    assert resolve_surface_profile(my_teams_only=True) is MY_STUFF_SURFACE_PROFILE
    assert resolve_surface_profile(mode="sports", my_teams_only=True) is MY_STUFF_SURFACE_PROFILE
    assert resolve_surface_profile(sports_mode=True, my_teams_only=True) is MY_STUFF_SURFACE_PROFILE
    assert get_surface_profile("sports").futures_first_page_cap is None


def test_sports_and_my_stuff_shipping_profiles_match_legacy_rank_key():
    """Pin 'nothing moved' for Step 1: Sports and My Stuff profiles match legacy `_rank_key`."""
    pool = [
        _event(10, score=72.0, status="live", hours_from_now=-0.5),
        _event(11, score=85.0, status="scheduled", hours_from_now=4.0),
        # Same score as eid 11, earlier kickoff/sort_time -> _rank_key breaks ties by _sort_time
        _event(12, score=85.0, status="scheduled", hours_from_now=1.0),
        _futures(20, score=90.0, team_id=9, movement=0.20),
        _futures(21, score=72.0, team_id=12, movement=0.05),
        _event(13, score=64.0, status="completed", hours_from_now=-3.0),
    ]
    # Give _futures(21) a newer _sort_time than _event(10) so tie on 72.0 breaks by recency.
    pool[4]["_sort_time"] = FROZEN_NOW.timestamp() + 1800
    expected = [(c["type"], c["data"]["id"]) for c in sorted(pool, key=_rank_key, reverse=True)]
    for profile in (SPORTS_SURFACE_PROFILE, MY_STUFF_SURFACE_PROFILE):
        ranked = rank_candidates_for_surface(
            pool,
            profile,
            followed_team_ids={9, 12},
            now=FROZEN_NOW,
        )
        assert [(c["type"], c["data"]["id"]) for c in ranked] == expected


def test_order_my_stuff_team_buckets_matches_legacy_loop_and_documents_tie_break():
    def _legacy_order(per_team: dict[int, list[dict]], limit: int) -> list[dict]:
        ranked_buckets = sorted(
            per_team.values(),
            key=lambda bucket: bucket[0]["probability"],
            reverse=True,
        )
        out: list[dict] = []
        depth = 0
        while len(out) < limit:
            progressed = False
            for bucket in ranked_buckets:
                if depth < len(bucket):
                    out.append(bucket[depth])
                    progressed = True
                    if len(out) >= limit:
                        break
            if not progressed:
                break
            depth += 1
        return out

    distinct = {
        1: [{"id": 101, "probability": 0.40}, {"id": 102, "probability": 0.25}],
        2: [{"id": 201, "probability": 0.72}, {"id": 202, "probability": 0.30}],
        3: [{"id": 301, "probability": 0.55}, {"id": 302, "probability": 0.20}],
    }
    assert order_my_stuff_team_buckets(
        distinct, limit=5, profile=MY_STUFF_SURFACE_PROFILE
    ) == _legacy_order(distinct, 5)

    # Known Step 1 tie difference: exact lead-probability ties sort lower team_id first.
    tied = {
        20: [{"id": 2001, "probability": 0.55}, {"id": 2002, "probability": 0.15}],
        5: [{"id": 501, "probability": 0.55}, {"id": 502, "probability": 0.10}],
        12: [{"id": 1201, "probability": 0.80}],
    }
    ordered_tied = order_my_stuff_team_buckets(tied, limit=5, profile=MY_STUFF_SURFACE_PROFILE)
    assert [it["id"] for it in ordered_tied] == [1201, 501, 2001, 502, 2002]


def test_discover_profile_never_drifts_base_rank_scores():
    items = [
        _event(10, score=72.5, status="live", hours_from_now=-1.0),
        _futures(20, score=84.0, team_id=9, movement=0.18),
    ]
    for item in items:
        scored, breakdown = score_candidate_for_surface(
            item,
            DISCOVER_SURFACE_PROFILE,
            followed_team_ids={9},
            now=FROZEN_NOW,
        )
        assert scored == pytest.approx(item["_rank_score"])
        assert breakdown["weighted"] == pytest.approx(item["_rank_score"])

    ranked = rank_candidates_for_surface(items, DISCOVER_SURFACE_PROFILE, now=FROZEN_NOW)
    assert [it["data"]["id"] for it in ranked] == [20, 10]


def test_sports_and_my_stuff_profiles_rank_with_shared_signals():
    custom_sports = RankingSurfaceProfile(
        surface="sports",
        live_game_bonus=25.0,
        imminent_kickoff_bonus=10.0,
    )
    far_sched = _event(1, score=68.0, status="scheduled", hours_from_now=48.0)
    imminent = _event(2, score=65.0, status="scheduled", hours_from_now=1.5)
    live_game = _event(3, score=60.0, status="live", hours_from_now=-0.5)

    ranked_sports = rank_candidates_for_surface(
        [far_sched, imminent, live_game],
        custom_sports,
        now=FROZEN_NOW,
    )
    assert [it["data"]["id"] for it in ranked_sports] == [3, 2, 1]

    custom_my_stuff = RankingSurfaceProfile(
        surface="my_stuff",
        followed_team_bonus=30.0,
        movement_weight=5.0,
        apply_diversity_caps=False,
    )
    unfollowed = _futures(10, score=80.0, team_id=100, movement=0.01)
    followed = _futures(11, score=62.0, team_id=42, movement=0.10)
    ranked_my_stuff = rank_candidates_for_surface(
        [unfollowed, followed],
        custom_my_stuff,
        followed_team_ids={42},
        now=FROZEN_NOW,
    )
    assert [it["data"]["id"] for it in ranked_my_stuff] == [11, 10]


def test_order_my_stuff_team_buckets_interleaves_by_leading_score():
    per_team = {
        1: [{"id": 101, "probability": 0.40}, {"id": 102, "probability": 0.25}],
        2: [{"id": 201, "probability": 0.72}, {"id": 202, "probability": 0.30}],
        3: [{"id": 301, "probability": 0.55}],
    }
    ordered = order_my_stuff_team_buckets(per_team, limit=4, profile=MY_STUFF_SURFACE_PROFILE)
    assert [it["id"] for it in ordered] == [201, 301, 101, 202]
    assert order_my_stuff_team_buckets(per_team, limit=0) == []


def test_apply_discover_display_chain_reports_and_enforces_resolved_surfaces(monkeypatch):
    monkeypatch.setenv("DISCOVER_GAME_NEEDS_REASON", "false")
    pool = [
        _event(1, score=75.0, status="live", hours_from_now=-0.5),
        _event(2, score=74.0, status="scheduled", hours_from_now=2.0),
        _futures(3, score=90.0),
    ]

    _, meta_discover = apply_discover_display_chain(
        [dict(p) for p in pool],
        limit=20,
        ctx=PersonalizationContext(),
        event_pct=0.15,
        now=FROZEN_NOW,
    )
    assert meta_discover["surface"] == "discover"

    _, meta_sports = apply_discover_display_chain(
        [dict(p) for p in pool],
        limit=20,
        ctx=PersonalizationContext(),
        event_pct=0.6,
        sports_mode=True,
        now=FROZEN_NOW,
    )
    assert meta_sports["surface"] == "sports"
    assert meta_sports["futures_first_page_cap"] is not None

    _, meta_my_stuff = apply_discover_display_chain(
        [dict(p) for p in pool],
        limit=20,
        ctx=PersonalizationContext(),
        event_pct=0.6,
        sports_mode=True,
        my_teams_only=True,
        now=FROZEN_NOW,
    )
    assert meta_my_stuff["surface"] == "my_stuff"
    assert meta_my_stuff["futures_first_page_cap"] is None
