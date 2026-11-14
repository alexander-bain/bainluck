"""Tests for gated ``opening_weekend_slate`` grouped-card candidate (#12288 Wave 2)."""

from __future__ import annotations

import re
from datetime import datetime

import pytest

from app.utils.opening_weekend_slate import (
    CANDIDATE_OPENING_WEEKEND_SLATE_PATH,
    CANDIDATE_OPENING_WEEKEND_SLATE_ROWS_PATH,
    PRODUCER_KIND_OPENING_WEEKEND_SLATE,
    build_opening_weekend_slate_CandidatePack,
    build_opening_weekend_slate_producer,
    compose_opening_weekend_card_and_container,
    format_box_office_bracket,
    load_candidate_definition,
    load_candidate_eval_rows,
    produce_opening_weekend_slate,
    select_opening_weekend_slate,
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
    assert CANDIDATE_OPENING_WEEKEND_SLATE_PATH.exists()
    assert CANDIDATE_OPENING_WEEKEND_SLATE_ROWS_PATH.exists()
    assert not (CONTAINERS_DATA_DIR / CANDIDATE_OPENING_WEEKEND_SLATE_PATH.name).exists()
    assert "roundup-opening-weekend-slate" not in ROUNDUP_PRODUCERS
    defn = load_candidate_definition()
    assert defn["rule"]["producer"] == PRODUCER_KIND_OPENING_WEEKEND_SLATE


def test_bracket_formatting_and_floor_trap_rejection() -> None:
    assert format_box_office_bracket("16m-19m") == "$16M–$19M"
    assert format_box_office_bracket("400m+") == "$400M+"
    assert format_box_office_bracket("<16m") == "Under $16M"
    assert format_box_office_bracket("Above 45") is None


@pytest.mark.asyncio
async def test_eval_rows_seat_active_opening_films_and_drop_holdover_or_untraded_rt() -> None:
    pack = load_candidate_eval_rows()
    now = datetime.fromisoformat(pack["captured_at"])
    producer = build_opening_weekend_slate_producer()
    res = await produce_opening_weekend_slate(pack["input_markets"], rule=producer.rule, now=now)
    assert isinstance(res, RoundupMembers)

    seated_ids = [r["market_id"] for r in res.rows]
    assert seated_ids == pack["expected_member_ids"]
    for ex in pack["excluded_ids"]:
        assert ex not in seated_ids

    assert res.rows[0]["label"] == "Ebenezer — $16M–$19M"
    assert res.rows[0]["rendered_percent"] == 56
    assert res.rows[1]["label"] == "Avengers: Doomsday — $400M+"
    assert res.rows[1]["rendered_percent"] == 57
    assert res.rows[3]["label"] == "Dune: Part Three — $110M–$130M"
    assert res.rows[3]["rendered_percent"] == 39

    feed_item, container = compose_opening_weekend_card_and_container(producer, res)
    ctx = feed_item["context_summary"]
    assert "Ebenezer ($16M–$19M at 56%)" in ctx
    assert not FORBIDDEN_COPY_RE.search(ctx)
    assert container["context_line"] == ctx

    cand = build_opening_weekend_slate_CandidatePack(producer, res)
    assert cand["reader_reachable"] is False
    assert cand["best_single"]["market_id"] == 69847041


def test_cumulative_non_exclusive_floor_ladders_refuse() -> None:
    cumulative = [
        {
            "id": 901,
            "status": "open",
            "name": '"Indie Film" Opening Weekend Box Office',
            "volume_24h": 500.0,
            "outcomes": [
                {"name": "<2.5m", "probability": 0.94},
                {"name": "2.5m-5m", "probability": 0.04},
                {"name": "5m+", "probability": 0.02},
            ],
        }
    ]
    res = select_opening_weekend_slate(cumulative, min_films=2)
    assert isinstance(res, RoundupRefusal)
