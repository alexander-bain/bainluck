"""Tests for gated ``ceremony_award_categories`` grouped-card candidate (#12288 Wave 2)."""

from __future__ import annotations

import re
from datetime import datetime

import pytest

from app.utils.ceremony_award_categories import (
    CANDIDATE_CEREMONY_AWARD_CATEGORIES_PATH,
    CANDIDATE_CEREMONY_AWARD_CATEGORIES_ROWS_PATH,
    PRODUCER_KIND_CEREMONY_AWARD_CATEGORIES,
    build_ceremony_award_categories_CandidatePack,
    build_ceremony_award_categories_producer,
    compose_ceremony_award_card_and_container,
    load_candidate_definition,
    load_candidate_eval_rows,
    produce_ceremony_award_categories,
    select_ceremony_award_categories,
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


def test_candidate_is_switched_off_and_validates() -> None:
    assert CANDIDATE_CEREMONY_AWARD_CATEGORIES_PATH.exists()
    assert CANDIDATE_CEREMONY_AWARD_CATEGORIES_ROWS_PATH.exists()
    assert not (CONTAINERS_DATA_DIR / CANDIDATE_CEREMONY_AWARD_CATEGORIES_PATH.name).exists()
    assert "roundup-ceremony-award-categories" not in ROUNDUP_PRODUCERS
    defn = load_candidate_definition()
    assert defn["rule"]["producer"] == PRODUCER_KIND_CEREMONY_AWARD_CATEGORIES


@pytest.mark.asyncio
async def test_eval_rows_seat_active_grammy_winner_categories_and_exclude_quiet_or_nominations() -> None:
    pack = load_candidate_eval_rows()
    now = datetime.fromisoformat(pack["captured_at"])
    producer = build_ceremony_award_categories_producer()
    res = await produce_ceremony_award_categories(pack["input_markets"], rule=producer.rule, now=now)
    assert isinstance(res, RoundupMembers)

    seated_ids = [r["market_id"] for r in res.rows]
    assert seated_ids == pack["expected_member_ids"]
    for ex in pack["excluded_ids"]:
        assert ex not in seated_ids

    assert res.rows[0]["category_label"] == "Album of the Year"
    assert res.rows[0]["rendered_percent"] == 41
    assert res.rows[1]["category_label"] == "Best Rap Album"
    assert res.rows[1]["rendered_percent"] == 45

    feed_item, container = compose_ceremony_award_card_and_container(producer, res)
    ctx = feed_item["context_summary"]
    assert "2027 Grammy Awards Winner categories" in ctx
    assert "Album of the Year" in ctx
    assert not FORBIDDEN_COPY_RE.search(ctx)
    assert container["context_line"] == ctx

    cand = build_ceremony_award_categories_CandidatePack(producer, res)
    assert cand["reader_reachable"] is False
    # Best Rap Album (44.65%) is closest to 50%
    assert cand["best_single"]["market_id"] == 58492244


def test_40pt_cross_source_divergence_refuses_explicitly() -> None:
    divergent = [
        {
            "id": 101,
            "source": "polymarket",
            "status": "open",
            "name": "Grammys 2027: Album of the Year Winner",
            "volume_24h": 500.0,
            "outcomes": [
                {"name": "Lux - Rosalía", "probability": 0.72},
                {"name": "Olivia Rodrigo", "probability": 0.18},
                {"name": "Olivia Dean", "probability": 0.10},
            ],
        },
        {
            "id": 102,
            "source": "kalshi",
            "status": "open",
            "name": "Grammy winner: Album of the Year",
            "volume_24h": 500.0,
            "outcomes": [
                {"name": "Lux - Rosalía", "probability": 0.22},
                {"name": "Olivia Rodrigo", "probability": 0.58},
                {"name": "Olivia Dean", "probability": 0.20},
            ],
        },
    ]
    res = select_ceremony_award_categories(divergent, ceremony="grammys", min_categories=2)
    assert isinstance(res, RoundupRefusal)
    assert res.reasons[0][0] == "category_divergence_gate"
