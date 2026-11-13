"""Tests for #12288 Wave 1 (Idea #15): dynamic ``long_shot_movers`` producer."""

from __future__ import annotations

import re
from datetime import datetime, timezone

import pytest

from app.utils.long_shot_movers import (
    CANDIDATE_LONG_SHOT_MOVERS_PATH,
    PRODUCER_KIND_LONG_SHOT_MOVERS,
    build_long_shot_movers_grading_candidate,
    build_long_shot_movers_producer,
    compose_long_shot_movers_card_and_container,
    load_candidate_definition,
    produce_long_shot_movers,
    select_long_shot_movers,
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

NOW_NOV_13 = datetime(2026, 11, 13, 16, 0, 0, tzinfo=timezone.utc)


def _long_shot_fixture() -> list[dict]:
    return [
        # 1. Started at 6% -> now 21% (+15 pts), recent quote, liquid
        {
            "id": 701001,
            "status": "open",
            "source": "polymarket",
            "name": "2027 Big Game Halftime Show: Miley Cyrus",
            "prices_updated_at": "2026-11-13T15:40:00Z",
            "volume": 48000,
            "outcomes": [
                {"name": "Yes", "probability": 0.21, "prior_24h_probability": 0.06},
            ],
        },
        # 2. Multi-outcome market: Portland Trail Blazers 8% -> 19% (+11 pts)
        {
            "id": 52755686,
            "status": "open",
            "source": "kalshi",
            "name": "NBA Northwest Division Winner",
            "prices_updated_at": "2026-11-13T15:30:00Z",
            "volume": 29500,
            "outcomes": [
                {"name": "Thunder", "probability": 0.46, "prior_24h_probability": 0.51},
                {"name": "Trail Blazers", "probability": 0.19, "prior_24h_probability": 0.08},
            ],
        },
        # 3. Started at 11% -> now 18% (+7 pts)
        {
            "id": 701003,
            "status": "open",
            "source": "kalshi",
            "name": "Heisman Trophy Winner",
            "prices_updated_at": "2026-11-13T15:15:00Z",
            "volume": 65000,
            "outcomes": [
                {"name": "CJ Carr", "probability": 0.18, "prior_24h_probability": 0.11},
            ],
        },
        # Excluded: un-traded quote from 19 hours ago (quiet-market guard)
        {
            "id": 701004,
            "status": "open",
            "source": "polymarket",
            "name": "Quiet untraded market",
            "prices_updated_at": "2026-11-12T20:00:00Z",
            "volume": 50000,
            "outcomes": [
                {"name": "Yes", "probability": 0.25, "prior_24h_probability": 0.05},
            ],
        },
        # Excluded: thin illiquid volume (<1000)
        {
            "id": 701005,
            "status": "open",
            "source": "polymarket",
            "name": "Thin market",
            "prices_updated_at": "2026-11-13T15:50:00Z",
            "volume": 120,
            "outcomes": [
                {"name": "Yes", "probability": 0.22, "prior_24h_probability": 0.04},
            ],
        },
        # Excluded: started at 25% (>12% long-shot ceiling)
        {
            "id": 701006,
            "status": "open",
            "source": "kalshi",
            "name": "Mid-tier mover",
            "prices_updated_at": "2026-11-13T15:50:00Z",
            "volume": 20000,
            "outcomes": [
                {"name": "Yes", "probability": 0.40, "prior_24h_probability": 0.25},
            ],
        },
    ]


def test_candidate_is_gated_and_validates() -> None:
    assert CANDIDATE_LONG_SHOT_MOVERS_PATH.exists()
    assert not (CONTAINERS_DATA_DIR / CANDIDATE_LONG_SHOT_MOVERS_PATH.name).exists()
    assert "roundup-long-shot-movers" not in ROUNDUP_PRODUCERS
    defn = load_candidate_definition()
    assert defn["rule"]["producer"] == PRODUCER_KIND_LONG_SHOT_MOVERS


@pytest.mark.asyncio
async def test_long_shot_movers_enforces_freshness_volume_and_points_only() -> None:
    producer = build_long_shot_movers_producer()
    res = await produce_long_shot_movers(
        _long_shot_fixture(), rule=producer.rule, now=NOW_NOV_13
    )
    assert isinstance(res, RoundupMembers)
    assert [r["market_id"] for r in res.rows] == [701001, 52755686, 701003]
    assert res.rows[0]["delta_label"] == "+15 pts from 6%"
    assert res.rows[1]["delta_label"] == "+11 pts from 8%"
    assert res.rows[1]["label"] == "Trail Blazers · NBA Northwest Division Winner"

    feed_item, container = compose_long_shot_movers_card_and_container(producer, res)
    ctx = feed_item["context_summary"]
    assert "12% or lower a day ago" in ctx
    assert "6 points" in ctx
    assert "+15 pts" in ctx
    assert container["context_line"] == ctx
    assert not FORBIDDEN_COPY_RE.search(ctx)
    assert not FORBIDDEN_COPY_RE.search(feed_item["data"]["roundup"]["footer"])

    grading = build_long_shot_movers_grading_candidate(producer, res)
    assert grading["reader_reachable"] is False
    assert grading["best_single"]["id"] == 701001


def test_withholds_below_min_members() -> None:
    res = select_long_shot_movers(_long_shot_fixture()[:2], now=NOW_NOV_13, min_members=3)
    assert isinstance(res, RoundupRefusal)
    assert res.reasons[0][0] == "insufficient_long_shot_movers"
