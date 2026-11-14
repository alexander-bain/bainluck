"""Tests for gated ``big_movers_today`` grouped-card candidate (#12288 Wave 2)."""

from __future__ import annotations

import re
from datetime import datetime, timezone

import pytest

from app.utils.big_movers_today import (
    CANDIDATE_BIG_MOVERS_TODAY_PATH,
    CANDIDATE_BIG_MOVERS_TODAY_ROWS_PATH,
    PRODUCER_KIND_BIG_MOVERS_TODAY,
    build_big_movers_today_CandidatePack,
    build_big_movers_today_producer,
    compose_big_movers_card_and_container,
    load_candidate_definition,
    load_candidate_eval_rows,
    produce_big_movers_today,
    select_big_movers_today,
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
    assert CANDIDATE_BIG_MOVERS_TODAY_PATH.exists()
    assert CANDIDATE_BIG_MOVERS_TODAY_ROWS_PATH.exists()
    assert not (CONTAINERS_DATA_DIR / CANDIDATE_BIG_MOVERS_TODAY_PATH.name).exists()
    assert "roundup-big-movers-today" not in ROUNDUP_PRODUCERS
    defn = load_candidate_definition()
    assert defn["rule"]["producer"] == PRODUCER_KIND_BIG_MOVERS_TODAY


@pytest.mark.asyncio
async def test_eval_rows_seat_only_actively_trading_markets_and_drop_quiet_ones() -> None:
    pack = load_candidate_eval_rows()
    now = datetime.fromisoformat(pack["captured_at"])
    producer = build_big_movers_today_producer()
    res = await produce_big_movers_today(pack["input_markets"], rule=producer.rule, now=now)
    assert isinstance(res, RoundupMembers)

    seated_ids = [r["market_id"] for r in res.rows]
    assert seated_ids == pack["expected_member_ids"]
    for excluded_id in pack["excluded_untraded_ids"]:
        assert excluded_id not in seated_ids

    # Family dedup: #69967999 had both Top 3 (+17.5 pts) and Top 5 (+8 pts); only Top 3 seats
    assert res.rows[0]["market_id"] == 69967999
    assert res.rows[0]["outcome"] == "Top 3"
    assert res.rows[0]["delta_points"] == 18
    assert res.rows[0]["delta_label"] == "+18 pts"

    # Binary "No" complement on GOOGL #67647293 is skipped in favor of "Yes"
    googl_row = next(r for r in res.rows if r["market_id"] == 67647293)
    assert googl_row["outcome"] == "Yes"
    assert googl_row["delta_label"] == "+9 pts"

    feed_item, container = compose_big_movers_card_and_container(producer, res)
    ctx = feed_item["context_summary"]
    assert "6+ points" in ctx
    assert "+18 pts to 83%" in ctx
    assert not FORBIDDEN_COPY_RE.search(ctx)
    assert not FORBIDDEN_COPY_RE.search(feed_item["data"]["roundup"]["footer"])
    assert container["context_line"] == ctx

    cand_pack = build_big_movers_today_CandidatePack(producer, res)
    assert cand_pack["reader_reachable"] is False
    assert cand_pack["best_single"]["market_id"] == 69967999


def test_refuses_when_all_movers_are_untraded_or_crypto() -> None:
    now = datetime(2026, 11, 14, 8, 25, tzinfo=timezone.utc)
    dead_or_crypto = [
        {
            "id": 1,
            "status": "open",
            "name": "What price will Bitcoin hit in November?",
            "volume_24h": 50000.0,
            "price_observed_at": "2026-11-14T08:00:00+00:00",
            "outcomes": [{"name": "65,000", "probability": 0.69, "movement": 0.18}],
        },
        {
            "id": 2,
            "status": "open",
            "name": "Oscars 2027: Best Casting",
            "volume_24h": 0.0,
            "last_trade_at": "2026-10-26T00:00:00+00:00",
            "outcomes": [{"name": "The Odyssey", "probability": 0.51, "movement": 0.12}],
        },
    ]
    res = select_big_movers_today(dead_or_crypto, now=now)
    assert isinstance(res, RoundupRefusal)
    assert res.reasons[0][0] == "insufficient_trading_movers"
