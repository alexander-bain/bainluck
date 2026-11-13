"""Tests for #12288 Wave 1 (Idea #4): dynamic ``league_award_ladders`` producer."""

from __future__ import annotations

import re

import pytest

from app.utils.league_award_ladders import (
    CANDIDATE_NBA_AWARD_LADDERS_PATH,
    PRODUCER_KIND_LEAGUE_AWARD_LADDERS,
    build_award_ladders_grading_candidate,
    build_league_award_ladders_producer,
    compose_award_ladders_card_and_container,
    load_candidate_definition,
    produce_league_award_ladders,
    select_league_award_ladders,
)
from app.utils.roundup_containers import (
    CONTAINERS_DATA_DIR,
    ROUNDUP_PRODUCERS,
    RoundupMembers,
    RoundupRefusal,
)

FORBIDDEN_COPY_RE = re.compile(
    r"\b(?:questions?|stale|venues?|kalshi|polymarket|opened)\b",
    re.IGNORECASE,
)


def _live_nba_awards_fixture() -> list[dict]:
    """Real Nov 13, 2026 NBA award markets + combo/finalist noise that must be excluded."""
    return [
        {
            "id": 66031970,
            "source": "polymarket",
            "status": "open",
            "sport": "basketball_nba",
            "name": "NBA: 2026-27 MVP",
            "outcomes": [
                {"name": "Victor Wembanyama", "probability": 0.360},
                {"name": "Luka Doncic", "probability": 0.342},
                {"name": "Shai Gilgeous-Alexander", "probability": 0.086},
            ],
        },
        {
            "id": 52755648,
            "source": "kalshi",
            "status": "open",
            "sport": "basketball_nba",
            "name": "Pro Basketball Defensive Player of the Year Winner",
            "outcomes": [
                {"name": "Victor Wembanyama", "probability": 0.695},
                {"name": "Rudy Gobert", "probability": 0.045},
            ],
        },
        {
            "id": 52755649,
            "source": "kalshi",
            "status": "open",
            "sport": "basketball_nba",
            "name": "Pro Basketball Rookie of the Year Winner",
            "outcomes": [
                {"name": "Yaxel Lendeborg", "probability": 0.420},
                {"name": "Cameron Boozer", "probability": 0.215},
            ],
        },
        {
            "id": 60629715,
            "source": "kalshi",
            "status": "open",
            "sport": "basketball_nba",
            "name": "Pro Basketball Coach of the Year Winner",
            "outcomes": [
                {"name": "Micah Nori", "probability": 0.152},
                {"name": "Ime Udoka", "probability": 0.097},
            ],
        },
        # Excluded noise: NBA Cup MVP, Finalists, MVP+DPOY combo
        {
            "id": 68948379,
            "source": "polymarket",
            "status": "open",
            "sport": "basketball_nba",
            "name": "NBA: 2026 NBA Cup MVP",
            "outcomes": [{"name": "Shai Gilgeous-Alexander", "probability": 0.22}],
        },
        {
            "id": 65521793,
            "source": "kalshi",
            "status": "open",
            "sport": "basketball_nba",
            "name": "NBA MVP Finalists",
            "outcomes": [{"name": "Victor Wembanyama", "probability": 0.78}],
        },
    ]


def test_candidate_is_gated_and_validates() -> None:
    assert CANDIDATE_NBA_AWARD_LADDERS_PATH.exists()
    assert not (CONTAINERS_DATA_DIR / CANDIDATE_NBA_AWARD_LADDERS_PATH.name).exists()
    assert "roundup-nba-award-ladders" not in ROUNDUP_PRODUCERS
    defn = load_candidate_definition()
    assert defn["rule"]["producer"] == PRODUCER_KIND_LEAGUE_AWARD_LADDERS


@pytest.mark.asyncio
async def test_nba_award_ladders_orders_closest_race_first_and_explains_context() -> None:
    producer = build_league_award_ladders_producer()
    res = await produce_league_award_ladders(_live_nba_awards_fixture(), rule=producer.rule)
    assert isinstance(res, RoundupMembers)
    assert len(res.rows) == 4
    # MVP (36.0 vs 34.2 = 1.8 pt gap) leads ahead of Coach (5.5 pt), ROY (20.5 pt), DPOY (65.0 pt)
    assert [r["award"] for r in res.rows] == [
        "MVP",
        "Coach of the Year",
        "Rookie of the Year",
        "Defensive Player",
    ]

    feed_item, container = compose_award_ladders_card_and_container(producer, res)
    ctx = feed_item["context_summary"]
    assert "MVP: Victor Wembanyama 36%" in ctx
    assert "Defensive Player: Victor Wembanyama 70%" in ctx
    assert container["context_line"] == ctx
    assert not FORBIDDEN_COPY_RE.search(ctx)
    assert not FORBIDDEN_COPY_RE.search(feed_item["data"]["roundup"]["footer"])

    grading = build_award_ladders_grading_candidate(producer, res)
    assert grading["reader_reachable"] is False
    assert grading["best_single"]["id"] == 52755649


def test_nfl_awards_blend_cross_source_dpoy_twin() -> None:
    nfl_markets = [
        {
            "id": 40532,
            "source": "kalshi",
            "status": "open",
            "sport": "americanfootball_nfl",
            "name": "NFL MVP Winner?",
            "outcomes": [{"name": "Joe Burrow", "probability": 0.319}, {"name": "Josh Allen", "probability": 0.211}],
        },
        {
            "id": 53663,
            "source": "kalshi",
            "status": "open",
            "sport": "americanfootball_nfl",
            "name": "NFL Defensive Player of the Year Winner?",
            "outcomes": [{"name": "Will Anderson Jr.", "probability": 0.395}, {"name": "Fred Warner", "probability": 0.155}],
        },
        {
            "id": 56947548,
            "source": "polymarket",
            "status": "open",
            "sport": "americanfootball_nfl",
            "name": "Pro Football: 2026-27 AP Defensive Player of the Year Winner",
            "outcomes": [{"name": "Will Anderson Jr.", "probability": 0.328}, {"name": "Fred Warner", "probability": 0.137}],
        },
        {
            "id": 8122712,
            "source": "kalshi",
            "status": "open",
            "sport": "americanfootball_nfl",
            "name": "NFL Coach of the Year Winner?",
            "outcomes": [{"name": "Kyle Shanahan", "probability": 0.250}, {"name": "John Harbaugh", "probability": 0.225}],
        },
    ]
    res = select_league_award_ladders(nfl_markets, sport="americanfootball_nfl", min_awards=3)
    assert isinstance(res, RoundupMembers)
    dpoy = [r for r in res.rows if r["award"] == "Defensive Player"][0]
    assert dpoy["probability"] == pytest.approx((0.395 + 0.328) / 2.0, abs=1e-4)


def test_withholds_when_below_min_awards() -> None:
    res = select_league_award_ladders(_live_nba_awards_fixture()[:2], min_awards=3)
    assert isinstance(res, RoundupRefusal)
