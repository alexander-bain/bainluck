"""Tests for #12288 Wave 1 (Idea #3): dynamic ``window_events_upsets`` producer."""

from __future__ import annotations

import re

import pytest

from app.utils.roundup_containers import (
    CONTAINERS_DATA_DIR,
    ROUNDUP_PRODUCERS,
    RoundupMembers,
    RoundupRefusal,
)
from app.utils.window_events_upsets import (
    CANDIDATE_UPSETS_BREWING_PATH,
    PRODUCER_KIND_WINDOW_EVENTS_UPSETS,
    build_upsets_brewing_grading_candidate,
    build_window_events_upsets_producer,
    compose_upsets_brewing_card_and_container,
    load_candidate_definition,
    produce_window_events_upsets,
    select_window_events_upsets,
)

FORBIDDEN_COPY_RE = re.compile(
    r"\b(?:questions?|stale|venues?|kalshi|polymarket|opened)\b",
    re.IGNORECASE,
)


def _live_upset_events_fixture() -> list[dict]:
    return [
        # 1. Pregame 28% underdog leading 78-71 in Q3, now 61% (+33 pts)
        {
            "id": 15390001,
            "status": "live",
            "status_detail": "Q3 4:12",
            "sport": "basketball_nba",
            "home_team": "Charlotte Hornets",
            "away_team": "Boston Celtics",
            "home_team_data": {"short_name": "Hornets"},
            "away_team_data": {"short_name": "Celtics"},
            "home_score": 78,
            "away_score": 71,
            "pregame_home_win_probability": 0.28,
            "home_win_probability": 0.61,
        },
        # 2. Pregame 34% road underdog leading 17-10 in 3rd quarter, now 58% (+24 pts)
        {
            "id": 15390002,
            "status": "live",
            "status_detail": "3rd 8:45",
            "sport": "americanfootball_nfl",
            "home_team": "Kansas City Chiefs",
            "away_team": "Las Vegas Raiders",
            "home_team_data": {"short_name": "Chiefs"},
            "away_team_data": {"short_name": "Raiders"},
            "home_score": 10,
            "away_score": 17,
            "pregame_home_win_probability": 0.66,
            "home_win_probability": 0.42,
        },
        # 3. Pregame 38% underdog tied 2-2 in 3rd period with 52% live win chance (+14 pts)
        {
            "id": 15390003,
            "status": "live",
            "status_detail": "3rd 11:02",
            "sport": "icehockey_nhl",
            "home_team": "Montreal Canadiens",
            "away_team": "Toronto Maple Leafs",
            "home_team_data": {"short_name": "Canadiens"},
            "away_team_data": {"short_name": "Maple Leafs"},
            "home_score": 2,
            "away_score": 2,
            "pregame_home_win_probability": 0.38,
            "home_win_probability": 0.52,
        },
        # Excluded: pregame favorite leading (not an upset)
        {
            "id": 15390004,
            "status": "live",
            "sport": "basketball_nba",
            "home_team": "Los Angeles Lakers",
            "away_team": "Utah Jazz",
            "home_score": 88,
            "away_score": 70,
            "pregame_home_win_probability": 0.74,
            "home_win_probability": 0.91,
        },
        # Excluded: finished game (belongs to settled cards, not live upset watch)
        {
            "id": 15390005,
            "status": "completed",
            "sport": "basketball_nba",
            "home_team": "Brooklyn Nets",
            "away_team": "New York Knicks",
            "home_score": 112,
            "away_score": 108,
            "pregame_home_win_probability": 0.30,
            "home_win_probability": 0.99,
        },
    ]


def test_candidate_is_gated_and_validates() -> None:
    assert CANDIDATE_UPSETS_BREWING_PATH.exists()
    assert not (CONTAINERS_DATA_DIR / CANDIDATE_UPSETS_BREWING_PATH.name).exists()
    assert "roundup-upsets-brewing" not in ROUNDUP_PRODUCERS
    defn = load_candidate_definition()
    assert defn["rule"]["producer"] == PRODUCER_KIND_WINDOW_EVENTS_UPSETS


@pytest.mark.asyncio
async def test_upsets_brewing_orders_by_point_swing_uses_pregame_never_opened() -> None:
    producer = build_window_events_upsets_producer()
    res = await produce_window_events_upsets(_live_upset_events_fixture(), rule=producer.rule)
    assert isinstance(res, RoundupMembers)
    assert [r["event_id"] for r in res.rows] == [15390001, 15390002, 15390003]
    assert res.rows[0]["swing_label"] == "+33 pts · 28% pregame"
    assert res.rows[1]["swing_label"] == "+24 pts · 34% pregame"
    assert "%" not in res.rows[0]["swing_label"].split("·")[0]

    feed_item, container = compose_upsets_brewing_card_and_container(producer, res)
    ctx = feed_item["context_summary"]
    assert "40% or lower pregame" in ctx
    assert "+33 pts from pregame" in ctx
    assert container["context_line"] == ctx
    assert not FORBIDDEN_COPY_RE.search(ctx)
    assert not FORBIDDEN_COPY_RE.search(feed_item["data"]["roundup"]["footer"])
    for r in res.rows:
        assert not FORBIDDEN_COPY_RE.search(r["label"])
        assert not FORBIDDEN_COPY_RE.search(r["swing_label"])

    grading = build_upsets_brewing_grading_candidate(producer, res)
    assert grading["reader_reachable"] is False
    assert grading["best_single"]["id"] == 15390003


def test_auto_withholds_when_fewer_than_three_live_upsets() -> None:
    res = select_window_events_upsets(_live_upset_events_fixture()[:2], min_members=3)
    assert isinstance(res, RoundupRefusal)
    assert res.reasons[0][0] == "insufficient_live_upsets"
