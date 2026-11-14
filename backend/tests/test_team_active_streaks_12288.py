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


def test_unpriced_earliest_game_excludes_team_instead_of_skipping_to_second_game() -> None:
    payload = {
        "team_streaks": [
            {"sport": "basketball_nba", "team": "Rockets", "streak_kind": "W", "streak_length": 6},
            {"sport": "basketball_nba", "team": "Spurs", "streak_kind": "W", "streak_length": 8},
            {"sport": "icehockey_nhl", "team": "Predators", "streak_kind": "W", "streak_length": 5},
            {"sport": "americanfootball_nfl", "team": "Lions", "streak_kind": "W", "streak_length": 4},
        ],
        "upcoming_events": [
            # Rockets' REAL next game (#701) has no odds; game #2 (#702) IS priced.
            # Rockets MUST be excluded rather than paired with #702!
            {
                "id": 701,
                "sport": "basketball_nba",
                "status": "scheduled",
                "home_team": "Rockets",
                "away_team": "Grizzlies",
                "hero_probability": None,
                "commence_time": "2026-11-15T01:00:00+00:00",
            },
            {
                "id": 702,
                "sport": "basketball_nba",
                "status": "scheduled",
                "home_team": "Rockets",
                "away_team": "Mavericks",
                "hero_probability": 0.64,
                "hero_probability_away": 0.36,
                "commence_time": "2026-11-17T01:00:00+00:00",
            },
            {
                "id": 703,
                "sport": "basketball_nba",
                "status": "scheduled",
                "home_team": "Spurs",
                "away_team": "Jazz",
                "hero_probability": 0.85,
                "hero_probability_away": 0.15,
                "commence_time": "2026-11-15T02:00:00+00:00",
            },
            {
                "id": 704,
                "sport": "icehockey_nhl",
                "status": "scheduled",
                "home_team": "Predators",
                "away_team": "Sharks",
                "hero_probability": 0.61,
                "hero_probability_away": 0.39,
                "commence_time": "2026-11-15T03:00:00+00:00",
            },
            {
                "id": 705,
                "sport": "americanfootball_nfl",
                "status": "scheduled",
                "home_team": "Lions",
                "away_team": "Patriots",
                "hero_probability": 0.58,
                "hero_probability_away": 0.42,
                "commence_time": "2026-11-15T18:00:00+00:00",
            },
        ],
    }
    res = select_team_active_streaks(payload)
    assert isinstance(res, RoundupMembers)
    seated_teams = [r["team"] for r in res.rows]
    seated_ids = [r["event_id"] for r in res.rows]
    assert "Rockets" not in seated_teams
    assert 701 not in seated_ids
    assert 702 not in seated_ids
    assert seated_teams == ["Spurs", "Predators", "Lions"]


def test_old_quotes_withheld_prices_malformed_inputs_and_precedence() -> None:
    now = datetime.fromisoformat("2026-11-14T08:00:00+00:00")
    completed = [
        # Completed events give Thunder W4, but explicit team_streaks overrides Thunder to W6
        {
            "sport": "basketball_nba",
            "home_team": "Thunder",
            "away_team": "Suns",
            "home_score": 112,
            "away_score": 100,
            "commence_time": f"2026-11-0{i}T00:00:00+00:00",
        }
        for i in range(1, 5)
    ]
    payload = {
        "completed_events": completed,
        "team_streaks": [
            {"sport": "basketball_nba", "team": "Thunder", "streak_kind": "W", "streak_length": 6},
            {"sport": "basketball_nba", "team": "BadLen", "streak_kind": "W", "streak_length": "not-an-int"},
            {"sport": "basketball_nba", "team": "WithheldTeam", "streak_kind": "W", "streak_length": 7},
            {"sport": "basketball_nba", "team": "OldQuoteTeam", "streak_kind": "W", "streak_length": 7},
            {"sport": "basketball_nba", "team": "Kalshi Kings", "streak_kind": "W", "streak_length": 9},
            {"sport": "icehockey_nhl", "team": "Stars", "streak_kind": "W", "streak_length": 5},
        ],
        "upcoming_events": [
            {
                "id": 801,
                "sport": "basketball_nba",
                "status": "scheduled",
                "home_team": "Thunder",
                "away_team": "Clippers",
                "home_streak": "W2",  # inline token must NOT override explicit W6
                "hero_probability": 0.72,
                "hero_probability_away": 0.28,
                "odds_updated_at": "2026-11-14T07:30:00+00:00",
                "commence_time": "2026-11-15T01:00:00+00:00",
            },
            {
                "id": 802,
                "sport": "basketball_nba",
                "status": "scheduled",
                "home_team": "WithheldTeam",
                "away_team": "Hawks",
                "prices_withheld": True,
                "hero_probability": 0.66,
                "hero_probability_away": 0.34,
                "odds_updated_at": "2026-11-14T07:30:00+00:00",
                "commence_time": "2026-11-15T01:30:00+00:00",
            },
            {
                "id": 803,
                "sport": "basketball_nba",
                "status": "scheduled",
                "home_team": "OldQuoteTeam",
                "away_team": "Magic",
                "hero_probability": 0.63,
                "hero_probability_away": 0.37,
                "odds_updated_at": "2026-11-12T00:00:00+00:00",  # > 24h old
                "commence_time": "2026-11-15T02:00:00+00:00",
            },
            {
                "id": 804,
                "sport": "basketball_nba",
                "status": "scheduled",
                "home_team": "Kalshi Kings",
                "away_team": "Bulls",
                "hero_probability": 0.68,
                "hero_probability_away": 0.32,
                "odds_updated_at": "2026-11-14T07:30:00+00:00",
                "commence_time": "2026-11-15T02:30:00+00:00",
            },
            {
                "id": 805,
                "sport": "icehockey_nhl",
                "status": "scheduled",
                "home_team": "Stars",
                "away_team": "Wild",
                "hero_probability": 0.56,
                "hero_probability_away": 0.44,
                "odds_updated_at": "2026-11-14T07:45:00+00:00",
                "commence_time": "2026-11-15T03:00:00+00:00",
            },
            {
                "id": 806,
                "sport": "americanfootball_nfl",
                "status": "scheduled",
                "home_team": "Bills",
                "away_team": "Jets",
                "home_streak": "W4",  # inline fallback works when no explicit/completed entry exists
                "hero_probability": 0.70,
                "hero_probability_away": 0.30,
                "odds_updated_at": "2026-11-14T07:50:00+00:00",
                "commence_time": "2026-11-15T18:00:00+00:00",
            },
        ],
    }
    res = select_team_active_streaks(payload, now=now, max_quote_age_hours=24.0)
    assert isinstance(res, RoundupMembers)
    rows_by_team = {r["team"]: r for r in res.rows}
    assert set(rows_by_team) == {"Thunder", "Stars", "Bills"}
    assert rows_by_team["Thunder"]["streak"] == "W6"
    assert rows_by_team["Bills"]["streak"] == "W4"
