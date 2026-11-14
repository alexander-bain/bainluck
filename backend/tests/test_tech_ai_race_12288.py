"""Tests for #12288 Wave 1 (Idea #12): dynamic ``tech_ai_race`` producer."""

from __future__ import annotations

import re
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.utils.roundup_containers import (
    CONTAINERS_DATA_DIR,
    ROUNDUP_PRODUCERS,
    RoundupMembers,
    RoundupRefusal,
)
from app.utils.tech_ai_race import (
    CANDIDATE_AI_RACE_PATH,
    PRODUCER_KIND_TECH_AI_RACE,
    build_ai_race_grading_candidate,
    build_tech_ai_race_producer,
    compose_ai_race_card_and_container,
    load_candidate_definition,
    produce_tech_ai_race,
    select_tech_ai_race,
)

FORBIDDEN_COPY_RE = re.compile(
    r"\b(?:questions?|stale|venues?|kalshi|polymarket|opened)\b",
    re.IGNORECASE,
)


def _live_ai_fixture() -> list[dict]:
    """Real Nov 13, 2026 AI leaderboard markets + multi-bucket ladders that must be excluded."""
    return [
        {
            "id": 61329163,
            "source": "polymarket",
            "status": "open",
            "category": "tech",
            "name": "Which company has the best AI model end of November?",
            "outcomes": [
                {"name": "Google", "probability": 0.855},
                {"name": "Anthropic", "probability": 0.123},
                {"name": "OpenAI", "probability": 0.010},
            ],
        },
        {
            "id": 32127334,
            "source": "polymarket",
            "status": "open",
            "category": "tech",
            "name": "Which company has best AI model end of 2026?",
            "outcomes": [
                {"name": "Google", "probability": 0.753},
                {"name": "Anthropic", "probability": 0.194},
                {"name": "OpenAI", "probability": 0.027},
            ],
        },
        {
            "id": 109623,
            "source": "kalshi",
            "status": "open",
            "category": "tech",
            "name": "Which AI company will have the best coding model at the end of 2026?",
            "outcomes": [
                {"name": "Anthropic", "probability": 0.715},
                {"name": "OpenAI", "probability": 0.125},
                {"name": "Google", "probability": 0.115},
            ],
        },
        {
            "id": 68626832,
            "source": "polymarket",
            "status": "open",
            "category": "tech",
            "name": "Which company has the best AI model on LiveBench (Coding) end of December?",
            "outcomes": [
                {"name": "Anthropic", "probability": 0.628},
                {"name": "Google", "probability": 0.109},
                {"name": "OpenAI", "probability": 0.109},
            ],
        },
        # Excluded: score-bucket ladder & non-exclusive "a top-ranked model"
        {
            "id": 8656574,
            "source": "polymarket",
            "status": "open",
            "category": "tech",
            "name": "What Coding Arena Score will any AI model reach by December 31?",
            "outcomes": [{"name": "1560", "probability": 1.0}, {"name": "1580", "probability": 0.58}],
        },
        {
            "id": 109194,
            "source": "kalshi",
            "status": "open",
            "category": "tech",
            "name": "Which companies will have a top-ranked AI model this year?",
            "outcomes": [{"name": "OpenAI", "probability": 0.09}, {"name": "Meta", "probability": 0.055}],
        },
    ]


def test_candidate_is_gated_and_validates() -> None:
    assert CANDIDATE_AI_RACE_PATH.exists()
    assert not (CONTAINERS_DATA_DIR / CANDIDATE_AI_RACE_PATH.name).exists()
    assert "roundup-ai-race" not in ROUNDUP_PRODUCERS
    defn = load_candidate_definition()
    assert defn["rule"]["producer"] == PRODUCER_KIND_TECH_AI_RACE


@pytest.mark.asyncio
async def test_ai_race_keeps_distinct_benchmarks_separate_and_explains_context() -> None:
    producer = build_tech_ai_race_producer()
    res = await produce_tech_ai_race(_live_ai_fixture(), rule=producer.rule)
    assert isinstance(res, RoundupMembers)
    assert len(res.rows) == 4

    # Coding Arena (109623, 72%) and LiveBench Coding (68626832, 63%) are NEVER merged
    # because they settle on different benchmarks.
    ids = [r["market_id"] for r in res.rows]
    assert ids == [61329163, 32127334, 109623, 68626832]
    assert res.rows[0]["label"] == "Overall Arena · End of Nov · Google"
    assert res.rows[2]["label"] == "Coding Arena · Year-end · Anthropic"
    assert res.rows[3]["label"] == "LiveBench Coding · Anthropic"

    feed_item, container = compose_ai_race_card_and_container(producer, res)
    ctx = feed_item["context_summary"]
    assert "Google leads overall evaluations while Anthropic leads coding" in ctx
    assert "each row settles on its named benchmark" in ctx
    assert container["context_line"] == ctx
    assert not FORBIDDEN_COPY_RE.search(ctx)
    assert not FORBIDDEN_COPY_RE.search(feed_item["data"]["roundup"]["footer"])

    grading = build_ai_race_grading_candidate(producer, res)
    assert grading["reader_reachable"] is False
    assert grading["best_single"]["id"] == 68626832


def test_rolling_november_and_december_month_end_markets_stay_in_separate_slots() -> None:
    """Open November and December month-end markets must never merge or mislabel percentages."""
    markets = [
        {
            "id": 61329163,
            "source": "polymarket",
            "status": "open",
            "category": "tech",
            "name": "Which company has the best AI model end of November?",
            "outcomes": [
                {"name": "Google", "probability": 0.85},
                {"name": "Anthropic", "probability": 0.12},
            ],
        },
        {
            "id": 770012,
            "source": "kalshi",
            "status": "open",
            "category": "tech",
            "name": "Which AI company has the best AI model at the end of December?",
            "outcomes": [
                {"name": "OpenAI", "probability": 0.55},
                {"name": "Google", "probability": 0.35},
                {"name": "Anthropic", "probability": 0.08},
            ],
        },
        _live_ai_fixture()[2],  # Coding Arena Year-end
    ]
    res = select_tech_ai_race(markets, min_benchmarks=3, max_card_rows=4)
    assert isinstance(res, RoundupMembers)
    by_bench = {r["benchmark"]: r for r in res.rows}
    assert "Overall Arena · End of Nov" in by_bench
    assert "Overall Arena · End of Dec" in by_bench
    assert by_bench["Overall Arena · End of Nov"]["leader"] == "Google"
    assert by_bench["Overall Arena · End of Nov"]["rendered_percent"] == 85
    assert by_bench["Overall Arena · End of Nov"]["market_id"] == 61329163
    assert by_bench["Overall Arena · End of Dec"]["leader"] == "OpenAI"
    assert by_bench["Overall Arena · End of Dec"]["rendered_percent"] == 55
    assert by_bench["Overall Arena · End of Dec"]["market_id"] == 770012


def test_single_source_leader_lab_preserved_when_second_source_omits_it() -> None:
    """When one source omits the 52% leader lab, it must remain the slot leader."""
    markets = [
        {
            "id": 880001,
            "source": "polymarket",
            "status": "open",
            "category": "tech",
            "name": "Which company has best AI model end of 2026?",
            "outcomes": [
                {"name": "OpenAI", "probability": 0.52},
                {"name": "Anthropic", "probability": 0.28},
                {"name": "Google", "probability": 0.15},
            ],
        },
        {
            "id": 880002,
            "source": "kalshi",
            "status": "open",
            "category": "tech",
            "name": "Which company has best AI model end of 2026?",
            "outcomes": [
                {"name": "Anthropic", "probability": 0.30},
                {"name": "Google DeepMind", "probability": 0.17},
            ],
        },
        _live_ai_fixture()[0],
        _live_ai_fixture()[2],
    ]
    res = select_tech_ai_race(markets, min_benchmarks=3)
    assert isinstance(res, RoundupMembers)
    year_end = [r for r in res.rows if r["benchmark"] == "Overall · Year-end"][0]
    assert year_end["leader"] == "OpenAI"
    assert year_end["rendered_percent"] == 52
    # Links to 880001 (the market that actually quotes OpenAI)
    assert year_end["market_id"] == 880001


def test_identical_benchmark_twins_blend_and_divergence_records_reason() -> None:
    fixture = _live_ai_fixture() + [
        {
            "id": 990001,
            "source": "kalshi",
            "status": "open",
            "category": "tech",
            "name": "Which company has best AI model end of 2026?",
            "outcomes": [
                {"name": "Google DeepMind", "probability": 0.727},
                {"name": "Anthropic", "probability": 0.206},
            ],
        }
    ]
    res = select_tech_ai_race(fixture)
    assert isinstance(res, RoundupMembers)
    year_end = [r for r in res.rows if r["benchmark"] == "Overall · Year-end"][0]
    assert year_end["probability"] == pytest.approx(0.74, abs=1e-4)
    assert set(res.revision_ids) >= {32127334, 990001}

    # 40+ pt divergence drops the slot and emits benchmark_divergence_gate on refusal
    divergent = _live_ai_fixture()[:2] + [
        {
            "id": 990099,
            "source": "kalshi",
            "status": "open",
            "category": "tech",
            "name": "Which company has best AI model end of 2026?",
            "outcomes": [
                {"name": "Google DeepMind", "probability": 0.20},
                {"name": "Anthropic", "probability": 0.75},
            ],
        }
    ]
    refusal = select_tech_ai_race(divergent, min_benchmarks=3)
    assert isinstance(refusal, RoundupRefusal)
    reason_codes = [r[0] for r in refusal.reasons]
    assert "insufficient_ai_benchmarks" in reason_codes
    assert "benchmark_divergence_gate" in reason_codes


@pytest.mark.asyncio
async def test_async_session_orm_serialization_and_refusals() -> None:
    orm_rows = [
        SimpleNamespace(
            id=row["id"],
            name=row["name"],
            status=row["status"],
            source=row["source"],
            category=row["category"],
            outcomes=[SimpleNamespace(**o) for o in row["outcomes"]],
        )
        for row in _live_ai_fixture()[:4]
    ]
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = orm_rows
    mock_db = MagicMock(spec=AsyncSession)
    mock_db.execute = AsyncMock(return_value=mock_result)

    res = await produce_tech_ai_race(mock_db, rule={"min_benchmarks": 3})
    assert isinstance(res, RoundupMembers)
    assert len(res.rows) == 4

    bad_session = await produce_tech_ai_race(object())
    assert isinstance(bad_session, RoundupRefusal)
    assert list(bad_session.reasons) == [("unsupported_session", "object")]

    short = select_tech_ai_race(_live_ai_fixture()[:2], min_benchmarks=3)
    assert isinstance(short, RoundupRefusal)
    assert short.reasons[0][0] == "insufficient_ai_benchmarks"
