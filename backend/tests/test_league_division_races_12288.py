"""Tests for #12288 Wave 1 (Idea #1): dynamic ``league_division_races`` producer."""

from __future__ import annotations

import re

import pytest

from app.utils.league_division_races import (
    CANDIDATE_NBA_DIVISION_RACES_PATH,
    PRODUCER_KIND_LEAGUE_DIVISION_RACES,
    build_division_races_grading_candidate,
    build_league_division_races_producer,
    compose_division_races_card_and_container,
    load_candidate_definition,
    produce_league_division_races,
    select_league_division_races,
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


def _live_nba_division_fixture() -> list[dict]:
    """Real Nov 13, 2026 NBA division markets plus noise markets that must be excluded."""
    return [
        {
            "id": 52755689,
            "source": "kalshi",
            "status": "open",
            "sport": "basketball_nba",
            "name": "Pro Basketball Atlantic Division Winner",
            "outcomes": [
                {"name": "Boston", "probability": 0.478},
                {"name": "Philadelphia", "probability": 0.284},
                {"name": "New York", "probability": 0.164},
            ],
        },
        {
            "id": 52755688,
            "source": "kalshi",
            "status": "open",
            "sport": "basketball_nba",
            "name": "Pro Basketball Central Division Winner",
            "outcomes": [
                {"name": "Detroit", "probability": 0.615},
                {"name": "Cleveland", "probability": 0.240},
                {"name": "Indiana", "probability": 0.100},
            ],
        },
        {
            "id": 52755684,
            "source": "kalshi",
            "status": "open",
            "sport": "basketball_nba",
            "name": "Pro Basketball Southeast Division Winner",
            "outcomes": [
                {"name": "Atlanta", "probability": 0.421},
                {"name": "Miami", "probability": 0.335},
                {"name": "Orlando", "probability": 0.127},
            ],
        },
        {
            "id": 52755686,
            "source": "kalshi",
            "status": "open",
            "sport": "basketball_nba",
            "name": "Pro Basketball Northwest Division Winner",
            "outcomes": [
                {"name": "Oklahoma City", "probability": 0.458},
                {"name": "Minnesota", "probability": 0.251},
                {"name": "Portland", "probability": 0.187},
            ],
        },
        {
            "id": 52755685,
            "source": "kalshi",
            "status": "open",
            "sport": "basketball_nba",
            "name": "Pro Basketball Pacific Division Winner",
            "outcomes": [
                {"name": "Los Angeles Lakers", "probability": 0.782},
                {"name": "Golden State", "probability": 0.188},
                {"name": "Phoenix", "probability": 0.030},
            ],
        },
        {
            "id": 52755683,
            "source": "kalshi",
            "status": "open",
            "sport": "basketball_nba",
            "name": "Pro Basketball Southwest Division Winner",
            "outcomes": [
                {"name": "San Antonio", "probability": 0.656},
                {"name": "Houston", "probability": 0.269},
                {"name": "Dallas", "probability": 0.057},
            ],
        },
        # Noise: exact-order and NHL division markets must never enter NBA divisions
        {
            "id": 52755848,
            "source": "kalshi",
            "status": "open",
            "sport": "basketball_nba",
            "name": "Atlantic Division: Exact Order",
            "outcomes": [{"name": "Boston / Philadelphia", "probability": 0.31}],
        },
        {
            "id": 59164862,
            "source": "kalshi",
            "status": "open",
            "sport": "icehockey_nhl",
            "name": "NHL Atlantic Division Winner",
            "outcomes": [
                {"name": "Tampa Bay Lightning", "probability": 0.348},
                {"name": "Montreal Canadiens", "probability": 0.211},
            ],
        },
    ]


def test_candidate_is_gated_outside_live_containers_dir_and_validates() -> None:
    assert CANDIDATE_NBA_DIVISION_RACES_PATH.exists()
    assert not (CONTAINERS_DATA_DIR / CANDIDATE_NBA_DIVISION_RACES_PATH.name).exists()
    assert "roundup-nba-division-races" not in ROUNDUP_PRODUCERS
    defn = load_candidate_definition()
    assert defn["rule"]["producer"] == PRODUCER_KIND_LEAGUE_DIVISION_RACES


@pytest.mark.asyncio
async def test_nba_division_races_orders_tightest_first_and_emits_clear_context_line() -> None:
    producer = build_league_division_races_producer()
    result = await produce_league_division_races(_live_nba_division_fixture(), rule=producer.rule)
    assert isinstance(result, RoundupMembers)
    assert len(result.members) == 6
    assert len(result.rows) == 4

    # Southeast (42.1 vs 33.5 = 8.6 pt gap) and Atlantic (47.8 vs 28.4 = 19.4 pt gap)
    # lead ahead of 78.2% Lakers runaway in Pacific.
    divisions_on_card = [r["division"] for r in result.rows]
    assert divisions_on_card == ["Southeast", "Atlantic", "Northwest", "Central"]
    assert result.rows[0]["label"] == "Southeast · Hawks"
    assert result.rows[0]["rendered_percent"] == 42

    feed_item, container = compose_division_races_card_and_container(producer, result)
    ctx = feed_item["context_summary"]
    assert "4 tightest of 6 NBA division races" in ctx
    assert "Hawks (42% in Southeast)" in ctx
    assert "Celtics (48% in Atlantic)" in ctx
    assert feed_item["data"]["roundup"]["context_line"] == ctx
    assert container["context_line"] == ctx
    assert not FORBIDDEN_COPY_RE.search(ctx)
    assert not FORBIDDEN_COPY_RE.search(feed_item["data"]["roundup"]["footer"])

    grading_item = build_division_races_grading_candidate(producer, result)
    assert grading_item["reader_reachable"] is False
    assert grading_item["licence_status"] == "HELD"
    assert grading_item["proposed_card"]["context_line"] == ctx
    assert grading_item["best_single"]["id"] in {52755689, 52755686, 52755684}


def test_single_source_leader_preserved_across_unequal_source_coverage() -> None:
    """When one source omits the true 50% leader, it must NOT be dropped in a two-source division."""
    markets = [
        # Atlantic: Kalshi quotes Celtics 50%, Knicks 30%, Nets 10%; Polymarket omits Celtics!
        {
            "id": 910001,
            "source": "kalshi",
            "status": "open",
            "sport": "basketball_nba",
            "name": "NBA Atlantic Division Winner",
            "outcomes": [
                {"name": "Boston Celtics", "probability": 0.50},
                {"name": "New York Knicks", "probability": 0.30},
                {"name": "Brooklyn Nets", "probability": 0.10},
            ],
        },
        {
            "id": 920001,
            "source": "polymarket",
            "status": "open",
            "sport": "basketball_nba",
            "name": "Pro Basketball: Atlantic Division Champion",
            "outcomes": [
                {"name": "New York Knicks", "probability": 0.30},
                {"name": "Brooklyn Nets", "probability": 0.10},
            ],
        },
        # Central: Polymarket quotes Pistons 52% while Kalshi omits Pistons (tests primary_market_id link!)
        {
            "id": 910002,
            "source": "kalshi",
            "status": "open",
            "sport": "basketball_nba",
            "name": "NBA Central Division Winner",
            "outcomes": [
                {"name": "Cleveland Cavaliers", "probability": 0.28},
                {"name": "Indiana Pacers", "probability": 0.16},
            ],
        },
        {
            "id": 920002,
            "source": "polymarket",
            "status": "open",
            "sport": "basketball_nba",
            "name": "Pro Basketball: Central Division Champion",
            "outcomes": [
                {"name": "Detroit Pistons", "probability": 0.52},
                {"name": "Cleveland Cavaliers", "probability": 0.28},
                {"name": "Indiana Pacers", "probability": 0.16},
            ],
        },
        # Southeast + Northwest
        _live_nba_division_fixture()[2],
        _live_nba_division_fixture()[3],
    ]
    res = select_league_division_races(markets, sport="basketball_nba", min_divisions=4, max_card_rows=4)
    assert isinstance(res, RoundupMembers)
    by_div = {r["division"]: r for r in res.rows}
    assert by_div["Atlantic"]["label"] == "Atlantic · Celtics"
    assert by_div["Atlantic"]["rendered_percent"] == 50
    assert by_div["Atlantic"]["gap_points"] == pytest.approx(20.0, abs=1e-4)
    assert by_div["Atlantic"]["market_id"] == 910001

    assert by_div["Central"]["label"] == "Central · Pistons"
    assert by_div["Central"]["rendered_percent"] == 52
    assert by_div["Central"]["gap_points"] == pytest.approx(24.0, abs=1e-4)
    # Linked to Polymarket market 920002 because 910002 does not list Pistons
    assert by_div["Central"]["market_id"] == 920002
    assert set(res.revision_ids) >= {910001, 920001, 910002, 920002}


def test_cross_source_blend_uses_blend_with_verdict_and_refuses_40pt_divergence() -> None:
    markets = [
        # AFC East twin within threshold: 88% and 90% -> 89% midpoint
        {
            "id": 53671,
            "source": "kalshi",
            "status": "open",
            "sport": "americanfootball_nfl",
            "name": "NFL AFC East Division Winner",
            "outcomes": [{"name": "Buffalo", "probability": 0.88}, {"name": "Miami", "probability": 0.10}],
        },
        {
            "id": 2248388,
            "source": "polymarket",
            "status": "open",
            "sport": "americanfootball_nfl",
            "name": "Pro Football: AFC East Champion",
            "outcomes": [
                {"name": "Buffalo Bills", "probability": 0.90},
                {"name": "Miami Dolphins", "probability": 0.09},
                {"name": "Other", "probability": 0.01},
            ],
        },
        # AFC North, AFC South, AFC West valid single-source
        {
            "id": 53672,
            "source": "kalshi",
            "status": "open",
            "sport": "americanfootball_nfl",
            "name": "NFL AFC North Division Winner",
            "outcomes": [{"name": "Baltimore", "probability": 0.56}, {"name": "Pittsburgh", "probability": 0.36}],
        },
        {
            "id": 53673,
            "source": "kalshi",
            "status": "open",
            "sport": "americanfootball_nfl",
            "name": "NFL AFC South Division Winner",
            "outcomes": [{"name": "Houston", "probability": 0.52}, {"name": "Indianapolis", "probability": 0.31}],
        },
        {
            "id": 53674,
            "source": "kalshi",
            "status": "open",
            "sport": "americanfootball_nfl",
            "name": "NFL AFC West Division Winner",
            "outcomes": [{"name": "Kansas City", "probability": 0.61}, {"name": "Denver", "probability": 0.25}],
        },
        # NFC East divergent twin (80% vs 25% = 55 pt gap -> refused by blend_with_verdict!)
        {
            "id": 53675,
            "source": "kalshi",
            "status": "open",
            "sport": "americanfootball_nfl",
            "name": "NFL NFC East Division Winner",
            "outcomes": [{"name": "Philadelphia", "probability": 0.80}, {"name": "Dallas", "probability": 0.15}],
        },
        {
            "id": 2248392,
            "source": "polymarket",
            "status": "open",
            "sport": "americanfootball_nfl",
            "name": "Pro Football: NFC East Champion",
            "outcomes": [{"name": "Philadelphia Eagles", "probability": 0.25}, {"name": "Dallas Cowboys", "probability": 0.70}],
        },
    ]
    res = select_league_division_races(markets, sport="americanfootball_nfl", min_divisions=4, max_card_rows=4)
    assert isinstance(res, RoundupMembers)
    # 4 verified divisions serve cleanly even though NFC East was refused and NFC N/S/W are absent!
    divs = {r["division"]: r for r in res.rows}
    assert set(divs.keys()) == {"AFC East", "AFC North", "AFC South", "AFC West"}
    assert divs["AFC East"]["probability"] == pytest.approx(0.89, abs=1e-4)
    assert set(res.revision_ids) >= {53671, 2248388}

    # When divergence drops total valid divisions below min_divisions, refusal carries division_divergence_gate!
    refusal = select_league_division_races(markets[3:], sport="americanfootball_nfl", min_divisions=4)
    assert isinstance(refusal, RoundupRefusal)
    reason_codes = [r[0] for r in refusal.reasons]
    assert "insufficient_divisions" in reason_codes
    assert "division_divergence_gate" in reason_codes


@pytest.mark.asyncio
async def test_withholds_on_insufficient_divisions_unsupported_sport_and_session() -> None:
    only_two = _live_nba_division_fixture()[:2]
    res = select_league_division_races(only_two, sport="basketball_nba", min_divisions=4)
    assert isinstance(res, RoundupRefusal)
    assert res.reasons[0][0] == "insufficient_divisions"

    bad_sport = select_league_division_races(only_two, sport="baseball_mlb")
    assert isinstance(bad_sport, RoundupRefusal)
    assert list(bad_sport.reasons) == [("unsupported_sport", "baseball_mlb")]

    bad_session = await produce_league_division_races(object())
    assert isinstance(bad_session, RoundupRefusal)
    assert list(bad_session.reasons) == [("unsupported_session", "object")]
