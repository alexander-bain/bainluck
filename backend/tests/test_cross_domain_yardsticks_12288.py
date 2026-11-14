"""Tests for gated ``cross_domain_yardsticks`` ("As likely as") candidate (#12288 Wave 2)."""

from __future__ import annotations

import re
from datetime import datetime

import pytest

from app.utils.cross_domain_yardsticks import (
    CANDIDATE_AS_LIKELY_AS_PATH,
    CANDIDATE_AS_LIKELY_AS_ROWS_PATH,
    PRODUCER_KIND_CROSS_DOMAIN_YARDSTICKS,
    build_cross_domain_yardsticks_CandidatePack,
    build_cross_domain_yardsticks_producer,
    compose_yardsticks_card_and_container,
    load_candidate_definition,
    load_candidate_eval_rows,
    produce_cross_domain_yardsticks,
    select_cross_domain_yardsticks,
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
    assert CANDIDATE_AS_LIKELY_AS_PATH.exists()
    assert CANDIDATE_AS_LIKELY_AS_ROWS_PATH.exists()
    assert not (CONTAINERS_DATA_DIR / CANDIDATE_AS_LIKELY_AS_PATH.name).exists()
    assert "roundup-as-likely-as" not in ROUNDUP_PRODUCERS
    defn = load_candidate_definition()
    assert defn["rule"]["producer"] == PRODUCER_KIND_CROSS_DOMAIN_YARDSTICKS


@pytest.mark.asyncio
async def test_eval_rows_pair_four_domains_near_46_percent_and_preserve_event_destinations() -> None:
    pack = load_candidate_eval_rows()
    now = datetime.fromisoformat(pack["captured_at"])
    producer = build_cross_domain_yardsticks_producer()
    res = await produce_cross_domain_yardsticks(pack["input_items"], rule=producer.rule, now=now)
    assert isinstance(res, RoundupMembers)

    seated_ids = [r["id"] for r in res.rows]
    assert set(seated_ids) == set(pack["expected_member_ids"])
    assert 52755611 not in seated_ids
    assert len({r["domain"] for r in res.rows}) == 4

    # Game member routes to /events/15348566, while market members route to /futures/{id}
    game_row = next(r for r in res.rows if r["id"] == 15348566)
    assert game_row["destination"]["web"] == "/events/15348566"
    econ_row = next(r for r in res.rows if r["id"] == 30691373)
    assert econ_row["destination"]["web"] == "/futures/30691373"

    feed_item, container = compose_yardsticks_card_and_container(producer, res)
    assert res.title == "Around a 46% chance right now"
    ctx = feed_item["context_summary"]
    assert "±1.5 points of 46%" in ctx
    assert not FORBIDDEN_COPY_RE.search(ctx)
    assert container["context_line"] == ctx

    # Verify container section preserves event destination too
    sec_members = container["sections"][0]["members"]
    event_entry = next(m for m in sec_members if m["id"] == 15348566)
    assert event_entry["type"] == "event"
    assert event_entry["destination"]["web"] == "/events/15348566"

    cand = build_cross_domain_yardsticks_CandidatePack(producer, res)
    assert cand["reader_reachable"] is False


def test_refuses_when_single_domain_only() -> None:
    same_domain_only = [
        {
            "id": 1,
            "category": "tech",
            "status": "open",
            "name": "Model A #1",
            "volume_24h": 500.0,
            "outcomes": [{"name": "Yes", "probability": 0.50}],
        },
        {
            "id": 2,
            "category": "tech",
            "status": "open",
            "name": "Model B #1",
            "volume_24h": 500.0,
            "outcomes": [{"name": "Yes", "probability": 0.505}],
        },
    ]
    res = select_cross_domain_yardsticks(same_domain_only)
    assert isinstance(res, RoundupRefusal)
