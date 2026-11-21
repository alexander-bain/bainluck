"""Guards eliminating underscore template blanks ('__' / '___') on cards, headlines, and set pages (#13387)."""

from __future__ import annotations

import json
from datetime import datetime, timezone

import pytest

from app.models import FuturesMarket, FuturesOutcome
from app.routes.containers import _hydrate_market_cards
from app.routes.feed import _score_market_trace
from app.routes.futures import _format_market_detail
from app.utils.container_machinery import (
    SubjectArtResolver,
    _hydrate_market_visual_item,
    discover_machinery_candidate_paths,
    load_machinery_definition,
)
from app.utils.discover_bundles import assemble_discover_comparison_bundles
from app.utils.market_display_name import (
    clean_market_display_name,
    fill_market_display_name_blank,
    fill_underscore_blanks,
)

NOW = datetime(2026, 11, 21, 22, 0, tzinfo=timezone.utc)


def _orm_market(
    mid: int,
    name: str,
    outcomes: list[tuple[int, str, float]],
    *,
    source: str = "polymarket",
    category: str = "tech",
    market_type: str = "field",
) -> FuturesMarket:
    market = FuturesMarket(
        id=mid,
        name=name,
        source=source,
        external_id=f"pm-{mid}",
        category=category,
        llm_sport_category=category,
        market_tier=2,
        market_type=market_type,
        mutually_exclusive=False,
        status="open",
        resolution_date=datetime(2027, 4, 1, 3, 59, tzinfo=timezone.utc),
        updated_at=NOW,
        volume=1_000_000.0,
        volume_24h=50_000.0,
        group_id=f"polymarket:{mid}",
    )
    market.sport = None
    market.outcomes = [
        FuturesOutcome(
            id=oid,
            market_id=mid,
            name=oname,
            current_probability=prob,
            opening_probability=prob,
            probability_change_24h=0.0,
            last_updated=NOW,
        )
        for oid, oname, prob in outcomes
    ]
    return market


class _FakeResult:
    def __init__(self, rows):
        self._rows = list(rows)

    def scalars(self):
        return self

    def all(self):
        return list(self._rows)


class _FakeSession:
    def __init__(self, markets):
        self._markets = list(markets)

    async def execute(self, *_args, **_kwargs):
        return _FakeResult(self._markets)


def test_single_threshold_fills_blank_with_threshold_label() -> None:
    assert (
        fill_market_display_name_blank(
            "OpenAI IPO closing market cap above ___ ?",
            "$800B",
            outcome_count=1,
        )
        == "OpenAI IPO closing market cap above $800B?"
    )
    assert (
        fill_market_display_name_blank(
            "Amazon 2026 capex above ___?",
            "Above $120B",
            outcome_count=1,
        )
        == "Amazon 2026 capex above $120B?"
    )


def test_multi_rung_templates_never_emit_underscore_blanks() -> None:
    samples = [
        ("OpenAI IPO closing market cap above ___ ?", "$800B", 7, "How high will OpenAI IPO closing market cap go?"),
        ("Anthropic IPO closing market cap above ___ ?", "$500B", 5, "How high will Anthropic IPO closing market cap go?"),
        ("Amazon 2026 capex above ___?", "$120B", 4, "How high will Amazon 2026 capex go?"),
        ("Trump approval rating at least ___ on November 20?", "45%", 5, "How high will Trump approval rating go on November 20?"),
        ("GPU rental prices (B200) hit___ in 2026?", "$4.00", 6, "What will GPU rental prices (B200) hit in 2026?"),
        ("Vance's Republican nomination odds hit __ by December 31?", "40%", 6, "What will Vance's Republican nomination odds hit by December 31?"),
        ("Will Claude go down on __ days in November 2026?", "3", 5, "How many days will Claude go down in November 2026?"),
        ("Will Venezuelan crude oil production reach __ barrels per day in 2026?", "1M", 5, "How many barrels per day will Venezuelan crude oil production reach in 2026?"),
        ("Will __ ships transit the Strait of Hormuz on any day by November 30?", "50", 5, "How many ships will transit the Strait of Hormuz on any day by November 30?"),
        ("Will a Chinese company have a top ___ AI model by December 31?", "Yes", 2, "Will a Chinese company have a top AI model by December 31?"),
    ]
    for raw, lead, count, expected in samples:
        actual = fill_market_display_name_blank(raw, lead, outcome_count=count)
        assert actual == expected
        assert actual and "___" not in actual and "__" not in actual


def test_existing_clean_market_display_name_controls_remain_unchanged() -> None:
    assert clean_market_display_name("Amazon 2026 capex above ___?") == "Amazon 2026 capex above ___?"


@pytest.mark.asyncio
async def test_container_set_page_hydration_eliminates_blank_in_openai_ipo(monkeypatch) -> None:
    async def _no_withheld(_db, _markets):
        return {}

    monkeypatch.setattr("app.routes.futures.withheld_price_outcome_ids_for_markets", _no_withheld)

    multi = _orm_market(
        115379,
        "OpenAI IPO closing market cap above ___ ?",
        [
            (1636888, "$800B", 0.68),
            (1636889, "$1T", 0.595),
            (1636890, "$1.2T", 0.395),
        ],
    )
    single = _orm_market(
        115380,
        "Anthropic IPO closing market cap above ___ ?",
        [(1636999, "$500B", 0.72)],
    )
    cards, _, failed = await _hydrate_market_cards(_FakeSession([multi, single]), [115379, 115380])
    assert failed == {}
    assert cards[115379]["name"] == "How high will OpenAI IPO closing market cap go?"
    assert "___" not in cards[115379]["name"] and "__" not in cards[115379]["name"]
    assert cards[115380]["name"] == "Anthropic IPO closing market cap above $500B?"
    assert "___" not in cards[115380]["name"] and "__" not in cards[115380]["name"]

    detail = _format_market_detail(multi, None, set())
    assert detail["name"] == "How high will OpenAI IPO closing market cap go?"
    assert "___" not in detail["name"] and "__" not in detail["name"]


def test_feed_trace_bundle_and_machinery_never_contain_blanks() -> None:
    multi = _orm_market(
        115379,
        "OpenAI IPO closing market cap above ___ ?",
        [
            (1636888, "$800B", 0.68),
            (1636889, "$1T", 0.595),
            (1636890, "$1.2T", 0.395),
        ],
    )
    trace = _score_market_trace(multi, NOW, source_count=1)
    trace_hl = trace["highlight"]
    assert "___" not in json.dumps(trace_hl)
    assert "__" not in json.dumps(trace_hl)

    member_1 = {
        "type": "futures",
        "score": 81.0,
        "headline": None,
        "reason": "79% chance by December 31",
        "data": {
            "id": 71517547,
            "name": fill_market_display_name_blank("Anthropic closes below IPO price ($83)?", "December 31", outcome_count=6),
            "top_outcomes": [{"id": 1, "name": "December 31", "probability": 0.785}],
            "discover_card": {"comparison_theme": "ipo_valuation", "bundle_candidate": True},
        },
    }
    member_2 = {
        "type": "futures",
        "score": 80.0,
        "headline": None,
        "reason": "68% chance above $800B",
        "data": {
            "id": 115379,
            "name": fill_market_display_name_blank("OpenAI IPO closing market cap above ___ ?", "$800B", outcome_count=7),
            "top_outcomes": [{"id": 2, "name": "$800B", "probability": 0.68}],
            "discover_card": {"comparison_theme": "ipo_valuation", "bundle_candidate": True},
        },
    }
    bundled = assemble_discover_comparison_bundles([member_1, member_2])
    payload = json.dumps(bundled)
    assert "___" not in payload
    assert "__" not in payload

    resolver = SubjectArtResolver()
    hydrated = _hydrate_market_visual_item(
        {
            "id": 115379,
            "name": "OpenAI IPO closing market cap above ___ ?",
            "status": "open",
            "source": "polymarket",
            "category": "tech",
            "outcomes": [{"id": 2, "name": "$800B", "probability": 0.68}],
        },
        max_outcomes=1,
        resolver=resolver,
    )
    assert "___" not in hydrated["title"]
    assert "___" not in hydrated["card"]["name"]


def test_machinery_candidate_definitions_have_no_underscore_blanks() -> None:
    for path in discover_machinery_candidate_paths():
        defn = load_machinery_definition(path)
        raw = json.dumps(defn)
        assert "___" not in raw, f"{path.name} contains ___"


def test_fill_underscore_blanks_noop_preserves_normal_titles_and_ellipses() -> None:
    normal = "Will SpaceX launch humans to Mars before 2030?"
    assert fill_underscore_blanks(normal) == normal
    with_ellipsis = "Wait... will this pass?"
    assert fill_underscore_blanks(with_ellipsis) == with_ellipsis
