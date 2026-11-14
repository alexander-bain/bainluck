"""Tests for #12288 Wave 1 (Idea #11): dynamic ``headliners_and_hosts`` producer."""

from __future__ import annotations

import re

import pytest

from app.utils.headliners_and_hosts import (
    CANDIDATE_HEADLINERS_AND_HOSTS_PATH,
    PRODUCER_KIND_HEADLINERS_AND_HOSTS,
    build_headliners_and_hosts_grading_candidate,
    build_headliners_and_hosts_producer,
    compose_headliners_card_and_container,
    load_candidate_definition,
    produce_headliners_and_hosts,
    select_headliners_and_hosts,
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


def _live_halftime_fixture() -> list[dict]:
    """Real Nov 13, 2026 Big Game halftime performer markets + song markets that must stay excluded."""
    return [
        {
            "id": 68313448,
            "source": "polymarket",
            "status": "open",
            "mutually_exclusive": False,
            "name": "Who will be in the 2027 Big Game halftime show?",
            "outcomes": [
                {"name": "Jay Z", "probability": 0.972},
                {"name": "Beyonce", "probability": 0.705},
                {"name": "Pharrell", "probability": 0.410},
                {"name": "Miley Cyrus", "probability": 0.190},
                {"name": "Justin Bieber", "probability": 0.095},
            ],
        },
        {
            "id": 56775565,
            "source": "kalshi",
            "status": "open",
            "mutually_exclusive": False,
            "name": "Pro Football Championship Halftime Show: Performers",
            "outcomes": [
                {"name": "JAY-Z", "probability": 0.990},
                {"name": "Beyoncé", "probability": 0.735},
                {"name": "Pharrell Williams", "probability": 0.440},
                {"name": "Miley Cyrus", "probability": 0.210},
                {"name": "Justin Bieber", "probability": 0.105},
            ],
        },
        # Excluded: song markets are not performer contenders
        {
            "id": 69851900,
            "source": "polymarket",
            "status": "open",
            "mutually_exclusive": False,
            "name": "What songs will be played at the 2027 Big Game halftime show?",
            "outcomes": [
                {"name": "99 Problems", "probability": 0.85},
                {"name": "Crazy in Love", "probability": 0.78},
                {"name": "Happy", "probability": 0.62},
                {"name": "Empire State of Mind", "probability": 0.55},
                {"name": "Halo", "probability": 0.48},
                {"name": "Party in the U.S.A.", "probability": 0.35},
            ],
        },
    ]


def test_candidate_is_gated_and_validates() -> None:
    assert CANDIDATE_HEADLINERS_AND_HOSTS_PATH.exists()
    assert not (CONTAINERS_DATA_DIR / CANDIDATE_HEADLINERS_AND_HOSTS_PATH.name).exists()
    assert "roundup-headliners-and-hosts" not in ROUNDUP_PRODUCERS
    defn = load_candidate_definition()
    assert defn["rule"]["producer"] == PRODUCER_KIND_HEADLINERS_AND_HOSTS


@pytest.mark.asyncio
async def test_halftime_performers_preserve_independent_chances_and_explain_non_100_sum() -> None:
    producer = build_headliners_and_hosts_producer()
    res = await produce_headliners_and_hosts(_live_halftime_fixture(), rule=producer.rule)
    assert isinstance(res, RoundupMembers)
    assert len(res.rows) == 5
    # Probabilities sum well above 100% and MUST NOT be normalized!
    total_prob = sum(r["probability"] for r in res.rows)
    assert total_prob > 2.0
    assert res.rows[0]["artist"] == "JAY-Z"
    assert res.rows[0]["probability"] == pytest.approx((0.972 + 0.990) / 2.0, abs=1e-4)
    assert res.rows[1]["artist"] == "Beyoncé"
    assert res.rows[1]["probability"] == pytest.approx((0.705 + 0.735) / 2.0, abs=1e-4)

    feed_item, container = compose_headliners_card_and_container(producer, res)
    ctx = feed_item["context_summary"]
    assert "multiple guests can share the stage" in ctx
    assert "do not add to 100%" in ctx
    assert container["context_line"] == ctx
    assert not FORBIDDEN_COPY_RE.search(ctx)
    assert not FORBIDDEN_COPY_RE.search(feed_item["data"]["roundup"]["footer"])

    grading = build_headliners_and_hosts_grading_candidate(producer, res)
    assert grading["reader_reachable"] is False
    # Pharrell Williams (42.5%) is closest to 50%!
    assert grading["best_single"]["subject"] == "Pharrell Williams"


def test_song_markets_excluded_even_when_larger_than_performer_market_or_alone() -> None:
    """Regression for blocking review: song markets with 'songs' before 'halftime show' must never match."""
    # Case 1: lone Polymarket song market with 3 outcomes -> must refuse!
    lone_song = [
        {
            "id": 69851901,
            "source": "polymarket",
            "status": "open",
            "mutually_exclusive": False,
            "name": "What songs will be played at the 2027 Big Game halftime show?",
            "outcomes": [
                {"name": "99 Problems", "probability": 0.85},
                {"name": "Crazy in Love", "probability": 0.72},
                {"name": "Happy", "probability": 0.61},
            ],
        }
    ]
    res_lone = select_headliners_and_hosts(lone_song, family="big_game_halftime_performers")
    assert isinstance(res_lone, RoundupRefusal)
    assert list(res_lone.reasons) == [("no_matching_stage_family", "big_game_halftime_performers")]

    # Case 2: 3-outcome performer market + 4-outcome song market from same source -> ONLY performers!
    mixed = [
        {
            "id": 68313448,
            "source": "polymarket",
            "status": "open",
            "mutually_exclusive": False,
            "name": "Who will be in the 2027 Big Game halftime show?",
            "outcomes": [
                {"name": "JAY-Z", "probability": 0.97},
                {"name": "Beyoncé", "probability": 0.71},
                {"name": "Pharrell Williams", "probability": 0.42},
            ],
        },
        {
            "id": 69851902,
            "source": "polymarket",
            "status": "open",
            "mutually_exclusive": False,
            "name": "What songs will be played at the 2027 Big Game halftime show?",
            "outcomes": [
                {"name": "99 Problems", "probability": 0.85},
                {"name": "Crazy in Love", "probability": 0.72},
                {"name": "Happy", "probability": 0.61},
                {"name": "Halo", "probability": 0.49},
            ],
        },
    ]
    res_mixed = select_headliners_and_hosts(mixed, family="big_game_halftime_performers", min_contenders=3)
    assert isinstance(res_mixed, RoundupMembers)
    assert [r["artist"] for r in res_mixed.rows] == ["JAY-Z", "Beyoncé", "Pharrell Williams"]


def test_single_host_family_switches_to_single_winner_context_without_false_100_sum_claim() -> None:
    host_markets = [
        {
            "id": 880001,
            "source": "kalshi",
            "status": "open",
            "mutually_exclusive": True,
            "name": "Who will host the 99th Oscars?",
            "outcomes": [
                {"name": "Conan O'Brien", "probability": 0.44},
                {"name": "John Mulaney", "probability": 0.28},
                {"name": "Jimmy Kimmel", "probability": 0.16},
            ],
        }
    ]
    res = select_headliners_and_hosts(host_markets, family="ceremony_host", min_contenders=3)
    assert isinstance(res, RoundupMembers)
    ctx = res.sections[0]["context_line"]
    assert "one choice settles Yes" in ctx
    assert "Conan O'Brien leads at 44%" in ctx
    assert "sum to 100%" not in (res.footer or "")
    assert "mutually exclusive" in (res.footer or "")


@pytest.mark.asyncio
async def test_divergence_gate_forbidden_labels_and_refusal_reasons() -> None:
    # 1. >= 40 pt cross-source disagreement refuses with explicit contender_divergence_gate reason
    divergent = [
        {
            "id": 710001,
            "source": "polymarket",
            "status": "open",
            "mutually_exclusive": False,
            "name": "Who will be in the 2027 Big Game halftime show?",
            "outcomes": [
                {"name": "JAY-Z", "probability": 0.90},
                {"name": "Beyoncé", "probability": 0.70},
                {"name": "Miley Cyrus", "probability": 0.25},
            ],
        },
        {
            "id": 710002,
            "source": "kalshi",
            "status": "open",
            "mutually_exclusive": False,
            "name": "Pro Football Championship Halftime Show: Performers",
            "outcomes": [
                {"name": "JAY-Z", "probability": 0.30},
                {"name": "Beyoncé", "probability": 0.72},
                {"name": "Miley Cyrus", "probability": 0.24},
            ],
        },
    ]
    div_res = select_headliners_and_hosts(divergent)
    assert isinstance(div_res, RoundupRefusal)
    assert list(div_res.reasons) == [("contender_divergence_gate", "big_game_halftime_performers", "JAY-Z")]

    # 2. Forbidden word in upstream contender label ("Stale" / "Opened") is skipped, never raises ValueError
    banned_label = [
        {
            "id": 710003,
            "source": "kalshi",
            "status": "open",
            "mutually_exclusive": False,
            "name": "Pro Football Championship Halftime Show: Performers",
            "outcomes": [
                {"name": "JAY-Z", "probability": 0.92},
                {"name": "Beyoncé", "probability": 0.71},
                {"name": "Pharrell Williams", "probability": 0.40},
                {"name": "Stale Mate", "probability": 0.55},
                {"name": "Opened Eyes", "probability": 0.50},
            ],
        }
    ]
    clean_res = select_headliners_and_hosts(banned_label, min_contenders=3)
    assert isinstance(clean_res, RoundupMembers)
    assert [r["artist"] for r in clean_res.rows] == ["JAY-Z", "Beyoncé", "Pharrell Williams"]

    # 3. no_priced_contenders & insufficient_contenders & unsupported_session
    unpriced = [
        {
            "id": 710004,
            "source": "kalshi",
            "status": "open",
            "name": "Pro Football Championship Halftime Show: Performers",
            "outcomes": [{"name": "JAY-Z", "probability": None}],
        }
    ]
    assert select_headliners_and_hosts(unpriced) == RoundupRefusal(
        [("no_priced_contenders", "big_game_halftime_performers")]
    )

    too_few = [
        {
            "id": 710005,
            "source": "kalshi",
            "status": "open",
            "name": "Pro Football Championship Halftime Show: Performers",
            "outcomes": [
                {"name": "JAY-Z", "probability": 0.90},
                {"name": "Beyoncé", "probability": 0.70},
            ],
        }
    ]
    assert select_headliners_and_hosts(too_few, min_contenders=3) == RoundupRefusal(
        [("insufficient_contenders", 2, 3)]
    )

    bad_session = await produce_headliners_and_hosts(object())
    assert bad_session == RoundupRefusal([("unsupported_session", "object")])
