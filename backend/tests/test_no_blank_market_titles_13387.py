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
from pathlib import Path

from app.utils.discover_bundles import (
    _make_theme_bundle_item,
    _public_member_item,
    assemble_discover_comparison_bundles,
)
from app.utils.market_display_name import (
    clean_market_display_name,
    fill_market_display_name_blank,
    fill_template_blanks,
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


def test_machinery_candidate_definitions_have_no_underscore_or_ellipsis_blanks() -> None:
    for path in discover_machinery_candidate_paths():
        defn = load_machinery_definition(path)
        raw = json.dumps(defn)
        assert "___" not in raw, f"{path.name} contains ___"
        assert "..." not in raw, f"{path.name} contains ..."
        assert "…" not in raw, f"{path.name} contains …"


def test_fill_underscore_blanks_noop_preserves_normal_titles_and_ellipses() -> None:
    normal = "Will SpaceX launch humans to Mars before 2030?"
    assert fill_underscore_blanks(normal) == normal
    assert fill_market_display_name_blank(normal) == normal
    with_ellipsis = "Wait... will this pass?"
    assert fill_underscore_blanks(with_ellipsis) == with_ellipsis
    assert fill_market_display_name_blank(with_ellipsis) == with_ellipsis


def test_ellipsis_templates_including_ceasefire_parenthetical_and_all_live_benchmark_markets() -> None:
    # #13393: "US x Iran Effective Ceasefire begins by...? (2 week pause)"
    raw_ceasefire = "US x Iran Effective Ceasefire begins by...? (2 week pause)"
    # Single shown deadline on a row says the deadline in place:
    assert (
        fill_market_display_name_blank(raw_ceasefire, "December 31", single_row=True)
        == "US x Iran Effective Ceasefire begins by December 31? (2 week pause)"
    )
    # Multi-deadline open form keeps the parenthetical qualifier and drops "..." / "…":
    assert (
        fill_market_display_name_blank(raw_ceasefire, "December 31", outcome_count=3)
        == "US x Iran Effective Ceasefire begins? (2 week pause)"
    )
    assert fill_template_blanks(raw_ceasefire, "By December 31", single_row=True) == (
        "US x Iran Effective Ceasefire begins by December 31? (2 week pause)"
    )

    samples = [
        ("US-Iran Final Nuclear Deal by…?", "June 30", 3, "US-Iran Final Nuclear Deal?"),
        (
            "Israeli airspace closed by...? (Excluding Holiday Closures)",
            "December 31",
            3,
            "Israeli airspace closed? (Excluding Holiday Closures)",
        ),
        (
            "Houthis capture Taiz by...? (castle)",
            "December 31",
            3,
            "Houthis capture Taiz? (castle)",
        ),
        (
            "Where will the next US-Iran senior diplomatic meeting take place...?",
            "Oman",
            4,
            "Where will the next US-Iran senior diplomatic meeting take place?",
        ),
        (
            "Merriam-Webster Word of the Year 2026 contains...?",
            "larping",
            4,
            "What will Merriam-Webster Word of the Year 2026 contain?",
        ),
        (
            "Oxford Word of the Year 2026 contains...?",
            "AI",
            4,
            "What will Oxford Word of the Year 2026 contain?",
        ),
    ]
    for raw, lead, count, expected in samples:
        actual = fill_market_display_name_blank(raw, lead, outcome_count=count)
        assert actual == expected
        assert "..." not in actual and "…" not in actual and "__" not in actual

    # Check the 3,424 live markets in fun-scout-benchmark: zero blanks or ellipsis templates survive.
    bench_path = (
        Path(__file__).resolve().parents[1]
        / "data"
        / "discover"
        / "fun-scout-benchmark-2026-11-19.json"
    )
    bench = json.loads(bench_path.read_text(encoding="utf-8"))
    for entry in bench.get("markets") or ():
        title = str(entry.get("title") or "")
        rendered_open = fill_market_display_name_blank(title, "December 31", outcome_count=3)
        rendered_single = fill_market_display_name_blank(title, "December 31", single_row=True)
        for rendered in (rendered_open, rendered_single):
            assert rendered and "..." not in rendered and "…" not in rendered and "__" not in rendered, (
                title,
                rendered,
            )


@pytest.mark.asyncio
async def test_bundle_member_single_row_puts_level_and_deadline_in_title_while_set_page_keeps_open_form(
    monkeypatch,
) -> None:
    # 1. Comparison / Theme bundle compact row puts the shown level ("$800B") or
    # shown deadline ("December 31") right in the row's title (#13390 follow-up + #13393).
    openai_member = {
        "type": "futures",
        "score": 82.0,
        "_raw_market_name": "OpenAI IPO closing market cap above ___ ?",
        "reason": "OpenAI IPO closing market cap above ___ ?",
        "data": {
            "id": 115379,
            "name": fill_market_display_name_blank(
                "OpenAI IPO closing market cap above ___ ?", "$800B", outcome_count=7
            ),
            "top_outcomes": [
                {"id": 1636888, "name": "$800B", "probability": 0.68},
                {"id": 1636889, "name": "$1T", "probability": 0.595},
            ],
            "discover_card": {
                "suggested_format": "threshold_heatmap",
                "comparison_theme": "ipo_valuation",
                "bundle_candidate": True,
                "threshold_points": [
                    {"value": 800, "label": "$800B", "probability": 0.68},
                    {"value": 1000, "label": "$1T", "probability": 0.42},
                ],
            },
        },
    }
    anthropic_member = {
        "type": "futures",
        "score": 81.0,
        "_raw_market_name": "Anthropic IPO closing market cap above ___ ?",
        "reason": "",
        "data": {
            "id": 115380,
            "name": fill_market_display_name_blank(
                "Anthropic IPO closing market cap above ___ ?", "$500B", outcome_count=5
            ),
            "top_outcomes": [{"id": 2, "name": "$500B", "probability": 0.72}],
            "discover_card": {
                "suggested_format": "threshold_heatmap",
                "comparison_theme": "ipo_valuation",
                "bundle_candidate": True,
                "threshold_points": [
                    {"value": 500, "label": "$500B", "probability": 0.72},
                    {"value": 800, "label": "$800B", "probability": 0.45},
                ],
            },
        },
    }
    comp_bundles = assemble_discover_comparison_bundles([openai_member, anthropic_member])
    assert comp_bundles
    comp_names = [it["data"]["name"] for it in comp_bundles[0]["data"]["items"]]
    assert comp_names == [
        "OpenAI IPO closing market cap above $800B?",
        "Anthropic IPO closing market cap above $500B?",
    ]
    assert comp_bundles[0]["data"]["debug_bundles"]["member_names"] == comp_names
    # Original open-form dict outside the bundle is never mutated.
    assert openai_member["data"]["name"] == "How high will OpenAI IPO closing market cap go?"

    # 2. Middle East theme bundle member fills the ceasefire deadline while multi-row page keeps open form.
    ceasefire_member = {
        "type": "futures",
        "score": 84.0,
        "_raw_market_name": "US x Iran Effective Ceasefire begins by...? (2 week pause)",
        "reason": "",
        "data": {
            "id": 69603905,
            "name": fill_market_display_name_blank(
                "US x Iran Effective Ceasefire begins by...? (2 week pause)",
                "December 31",
                outcome_count=3,
            ),
            "top_outcomes": [
                {"id": 260868679, "name": "December 31", "probability": 0.765},
                {"id": 260851406, "name": "November 30", "probability": 0.44},
            ],
            "_quality_story_key": "story:middle_east_conflict",
        },
    }
    iran_other = {
        "type": "futures",
        "score": 85.0,
        "_raw_market_name": "Will the U.S. invade Iran before 2027?",
        "reason": "",
        "data": {
            "id": 113232,
            "name": "Will the U.S. invade Iran before 2027?",
            "top_outcomes": [{"id": 1628892, "name": "Yes", "probability": 0.075}],
        },
    }
    theme_bundle = _make_theme_bundle_item(
        "story:middle_east_conflict", [iran_other, ceasefire_member]
    )
    assert theme_bundle is not None
    theme_names = [it["data"]["name"] for it in theme_bundle["data"]["items"]]
    assert "US x Iran Effective Ceasefire begins by December 31? (2 week pause)" in theme_names
    ceasefire_pub = next(
        it["data"] for it in theme_bundle["data"]["items"] if it["data"]["id"] == 69603905
    )
    assert ceasefire_pub.get("title_states_single_answer") is True
    other_pub = next(
        it["data"] for it in theme_bundle["data"]["items"] if it["data"]["id"] == 113232
    )
    assert "title_states_single_answer" not in other_pub
    assert "..." not in json.dumps(theme_bundle)
    assert "…" not in json.dumps(theme_bundle)
    assert "___" not in json.dumps(theme_bundle)

    # 3. Threshold heatmap picks the marked rung (date ONLY when ALL rungs are date_bucket = earliest >= 50%,
    #    threshold/mixed = highest >= 50%, nothing >= 50% falls back to top outcome), and dedups comparators.
    assert (
        fill_market_display_name_blank(
            "Bitcoin above ___ on December 31?", "$120,000 or above", single_row=True
        )
        == "Bitcoin above $120,000 on December 31?"
    )
    assert (
        fill_market_display_name_blank(
            "Revenue over ___ in 2026?", "$5B or more", single_row=True
        )
        == "Revenue over $5B in 2026?"
    )
    assert (
        fill_market_display_name_blank(
            "Inflation below ___ in 2026?", "2.5% or below", single_row=True
        )
        == "Inflation below 2.5% in 2026?"
    )
    assert (
        fill_market_display_name_blank(
            "CPI at most ___ this quarter?", "3% or less", single_row=True
        )
        == "CPI at most 3% this quarter?"
    )
    assert (
        fill_market_display_name_blank(
            "Unemployment under ___ in December?", "4% or lower", single_row=True
        )
        == "Unemployment under 4% in December?"
    )

    heatmap_member = {
        "type": "futures",
        "_raw_market_name": "Trump approval rating at least ___ on November 20?",
        "data": {
            "id": 999111,
            "name": "How high will Trump approval rating go on November 20?",
            "top_outcomes": [{"id": 1, "name": "40%+", "probability": 0.90}],
            "discover_card": {
                "suggested_format": "threshold_heatmap",
                "threshold_points": [
                    {"label": "40%+", "value": 40, "probability": 0.90, "source": "outcome"},
                    {"label": "45%+", "value": 45, "probability": 0.62, "source": "outcome"},
                    {"label": "50%+", "value": 50, "probability": 0.25, "source": "outcome"},
                ],
            },
        },
    }
    pub_heatmap = _public_member_item(heatmap_member)
    assert pub_heatmap["data"]["name"] == "Trump approval rating at least 45% on November 20?"
    assert pub_heatmap["data"].get("title_states_single_answer") is True

    # Mixed ladder (not ALL date_bucket): must follow web `ladderKind` (`every`) / iPhone (`allSatisfy`)
    # and pick the highest >= 50% rung (`45%+` -> `45%`), NOT earliest >= 50%.
    mixed_ladder_member = {
        "type": "futures",
        "_raw_market_name": "Trump approval rating at least ___ on November 20?",
        "data": {
            "id": 999112,
            "name": "How high will Trump approval rating go on November 20?",
            "top_outcomes": [{"id": 1, "name": "December 31", "probability": 0.80}],
            "discover_card": {
                "suggested_format": "threshold_heatmap",
                "threshold_points": [
                    {"label": "40%+", "value": 40, "probability": 0.80, "source": "date_bucket"},
                    {"label": "45%+", "value": 45, "probability": 0.62, "source": "outcome"},
                    {"label": "50%+", "value": 50, "probability": 0.25, "source": "outcome"},
                ],
            },
        },
    }
    pub_mixed = _public_member_item(mixed_ladder_member)
    assert pub_mixed["data"]["name"] == "Trump approval rating at least 45% on November 20?"

    # Nothing at 50% or better: falls back to top_outcomes[0].
    below_even_member = {
        "type": "futures",
        "_raw_market_name": "Trump approval rating at least ___ on November 20?",
        "data": {
            "id": 999113,
            "name": "How high will Trump approval rating go on November 20?",
            "top_outcomes": [{"id": 1, "name": "40%+", "probability": 0.38}],
            "discover_card": {
                "suggested_format": "threshold_heatmap",
                "threshold_points": [
                    {"label": "40%+", "value": 40, "probability": 0.38, "source": "outcome"},
                    {"label": "45%+", "value": 45, "probability": 0.22, "source": "outcome"},
                ],
            },
        },
    }
    pub_below = _public_member_item(below_even_member)
    assert pub_below["data"]["name"] == "Trump approval rating at least 40% on November 20?"

    # 4. Full detail page & container set hydration keep open form where every deadline/level is listed.
    async def _no_withheld(_db, _markets):
        return {}

    monkeypatch.setattr("app.routes.futures.withheld_price_outcome_ids_for_markets", _no_withheld)
    ceasefire_orm = _orm_market(
        69603905,
        "US x Iran Effective Ceasefire begins by...? (2 week pause)",
        [(260868679, "December 31", 0.765), (260851406, "November 30", 0.44)],
    )
    cards, _, failed = await _hydrate_market_cards(_FakeSession([ceasefire_orm]), [69603905])
    assert failed == {}
    assert cards[69603905]["name"] == "US x Iran Effective Ceasefire begins? (2 week pause)"
    assert "title_states_single_answer" not in cards[69603905]
    detail = _format_market_detail(ceasefire_orm, None, set())
    assert detail["name"] == "US x Iran Effective Ceasefire begins? (2 week pause)"
    assert "title_states_single_answer" not in detail
