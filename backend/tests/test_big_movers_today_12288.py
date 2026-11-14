"""Tests for gated ``big_movers_today`` grouped-card candidate (#12288 Wave 2)."""

from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone

import pytest

from app.utils.big_movers_today import (
    CANDIDATE_BIG_MOVERS_TODAY_PATH,
    CANDIDATE_BIG_MOVERS_TODAY_ROWS_PATH,
    PRODUCER_KIND_BIG_MOVERS_TODAY,
    build_big_movers_today_CandidatePack,
    build_big_movers_today_producer,
    compose_big_movers_card_and_container,
    is_actively_trading_market,
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


@pytest.mark.asyncio
async def test_producer_closure_without_now_enforces_quote_and_trade_freshness() -> None:
    live_now = datetime.now(timezone.utc)
    fresh_iso = (live_now - timedelta(hours=2)).isoformat()
    old_trade_iso = (live_now - timedelta(days=12)).isoformat()
    old_quote_iso = (live_now - timedelta(hours=36)).isoformat()

    markets = [
        {
            "id": 101,
            "status": "open",
            "category": "tech",
            "name": "Old trade mover",
            "volume_24h": 5000.0,
            "last_trade_at": old_trade_iso,
            "price_observed_at": fresh_iso,
            "outcomes": [{"name": "Yes", "probability": 0.62, "movement": 0.15}],
        },
        {
            "id": 102,
            "status": "open",
            "category": "economics",
            "name": "Old quote mover",
            "volume_24h": 5000.0,
            "last_trade_at": fresh_iso,
            "price_observed_at": old_quote_iso,
            "outcomes": [{"name": "Yes", "probability": 0.48, "movement": 0.14}],
        },
        {
            "id": 103,
            "status": "open",
            "category": "tech",
            "name": "Fresh AI benchmark leader",
            "volume_24h": 8400.0,
            "last_trade_at": fresh_iso,
            "price_observed_at": fresh_iso,
            "outcomes": [{"name": "Google", "probability": 0.71, "movement": 0.12}],
        },
        {
            "id": 104,
            "status": "open",
            "category": "entertainment",
            "name": "Fresh box office leader",
            "volume_24h": 6200.0,
            "last_trade_at": fresh_iso,
            "price_observed_at": fresh_iso,
            "outcomes": [{"name": "Ebenezer", "probability": 0.56, "movement": 0.10}],
        },
        {
            "id": 105,
            "status": "open",
            "category": "economics",
            "name": "Fresh rate decision",
            "volume_24h": 19200.0,
            "last_trade_at": fresh_iso,
            "price_observed_at": fresh_iso,
            "outcomes": [{"name": "25 bps cut", "probability": 0.68, "movement": -0.09}],
        },
    ]

    producer = build_big_movers_today_producer()
    # Call producer.produce directly with NO `now` parameter!
    res = await producer.produce(markets)
    assert isinstance(res, RoundupMembers)
    seated_ids = [r["market_id"] for r in res.rows]
    assert 101 not in seated_ids
    assert 102 not in seated_ids
    assert seated_ids == [103, 104, 105]


def test_guard_is_fail_closed_when_volume_24h_or_freshness_timestamp_is_missing() -> None:
    now = datetime(2026, 11, 14, 8, 25, tzinfo=timezone.utc)
    # Missing volume_24h -> refused
    assert not is_actively_trading_market(
        {
            "id": 201,
            "status": "open",
            "last_trade_at": "2026-11-14T08:00:00+00:00",
            "price_observed_at": "2026-11-14T08:00:00+00:00",
        },
        now=now,
    )
    # Missing both last_trade_at and price_observed_at/updated_at -> refused
    assert not is_actively_trading_market(
        {
            "id": 202,
            "status": "open",
            "volume_24h": 4500.0,
        },
        now=now,
    )
    # Malformed timestamp -> refused
    assert not is_actively_trading_market(
        {
            "id": 203,
            "status": "open",
            "volume_24h": 4500.0,
            "price_observed_at": "not-a-timestamp",
        },
        now=now,
    )
    # Out-of-range movement (18.0 raw percentage points instead of 0.18 fraction) -> refused
    res = select_big_movers_today(
        [
            {
                "id": 204,
                "status": "open",
                "name": "Bad unit mover",
                "volume_24h": 4500.0,
                "price_observed_at": "2026-11-14T08:00:00+00:00",
                "outcomes": [{"name": "Yes", "probability": 0.55, "movement": 18.0}],
            }
        ],
        now=now,
    )
    assert isinstance(res, RoundupRefusal)
