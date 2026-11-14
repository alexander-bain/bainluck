"""Tests for gated ``team_active_streaks`` ("The streak") candidate (#12288 Wave 2)."""

from __future__ import annotations

import re
from datetime import datetime

import pytest

from app.utils.roundup_containers import (
    CONTAINERS_DATA_DIR,
    ROUNDUP_PRODUCERS,
    RoundupMembers,
    RoundupRefusal,
)
from app.utils.team_active_streaks import (
    CANDIDATE_TEAM_ACTIVE_STREAKS_PATH,
    CANDIDATE_TEAM_ACTIVE_STREAKS_ROWS_PATH,
    PRODUCER_KIND_TEAM_ACTIVE_STREAKS,
    build_team_active_streaks_CandidatePack,
    build_team_active_streaks_producer,
    compose_team_streaks_card_and_container,
    load_candidate_definition,
    load_candidate_eval_rows,
    produce_team_active_streaks,
    select_team_active_streaks,
)

FORBIDDEN_COPY_RE = re.compile(
    r"\b(?:questions?|stale|venues?|kalshi|polymarket|opened)\b",
    re.IGNORECASE,
)


def test_candidate_is_switched_off_and_validates() -> None:
    assert CANDIDATE_TEAM_ACTIVE_STREAKS_PATH.exists()
    assert CANDIDATE_TEAM_ACTIVE_STREAKS_ROWS_PATH.exists()
    assert not (CONTAINERS_DATA_DIR / CANDIDATE_TEAM_ACTIVE_STREAKS_PATH.name).exists()
    assert "roundup-team-active-streaks" not in ROUNDUP_PRODUCERS
    defn = load_candidate_definition()
    assert defn["rule"]["producer"] == PRODUCER_KIND_TEAM_ACTIVE_STREAKS


@pytest.mark.asyncio
async def test_eval_rows_seat_priced_streaks_and_refuse_unpriced_games() -> None:
    pack = load_candidate_eval_rows()
    now = datetime.fromisoformat(pack["captured_at"])
    producer = build_team_active_streaks_producer()
    res = await produce_team_active_streaks(pack["input_payload"], rule=producer.rule, now=now)
    assert isinstance(res, RoundupMembers)

    seated_ids = [r["event_id"] for r in res.rows]
    assert seated_ids == pack["expected_event_ids"]
    assert 990001 not in seated_ids

    assert res.rows[0]["label"] == "San Antonio Spurs (W11) · at Utah Jazz"
    assert res.rows[0]["rendered_percent"] == 89
    assert res.rows[0]["destination"]["web"] == "/events/15344692"

    feed_item, container = compose_team_streaks_card_and_container(producer, res)
    ctx = feed_item["context_summary"]
    assert "San Antonio Spurs (W11, 89% to reach W12 at Utah Jazz)" in ctx
    assert not FORBIDDEN_COPY_RE.search(ctx)
    assert container["context_line"] == ctx
    assert container["sections"][0]["members"][0]["type"] == "event"
    assert container["sections"][0]["members"][0]["destination"]["web"] == "/events/15344692"

    cand = build_team_active_streaks_CandidatePack(producer, res)
    assert cand["reader_reachable"] is False
    # Detroit Lions (57.5%) is closest to 50%
    assert cand["best_single"]["event_id"] == 14639206


def test_derives_streaks_from_completed_events_and_dedups_same_next_game() -> None:
    completed = [
        {"sport": "basketball_nba", "home_team": "Celtics", "away_team": "Knicks", "home_score": 110, "away_score": 102, "commence_time": f"2026-11-0{i}T00:00:00+00:00"}
        for i in range(1, 6)
    ] + [
        {"sport": "basketball_nba", "home_team": "Cavaliers", "away_team": "Nets", "home_score": 115, "away_score": 99, "commence_time": f"2026-11-0{i}T00:00:00+00:00"}
        for i in range(1, 5)
    ]
    # Celtics (W5) and Cavaliers (W4) play EACH OTHER in event #500 -> must dedup to 1 row -> insufficient (<3)
    upcoming = [
        {
            "id": 500,
            "sport": "basketball_nba",
            "status": "scheduled",
            "home_team": "Celtics",
            "away_team": "Cavaliers",
            "hero_probability": 0.58,
            "hero_probability_away": 0.42,
            "commence_time": "2026-11-15T00:00:00+00:00",
        }
    ]
    res = select_team_active_streaks({"completed_events": completed, "upcoming_events": upcoming})
    assert isinstance(res, RoundupRefusal)
    assert list(res.reasons) == [("insufficient_priced_streaks", 1, 3)]
