"""Tests for additive visual form names on older Discover round-ups and themes (353: A)."""

from __future__ import annotations

from copy import deepcopy
from types import SimpleNamespace

from app.routes.feed import _publish_feed_item
from app.utils.bundle_visual_form import (
    FORM_BENCHMARK_STRIP,
    FORM_COMPARISON_COMPACT_ROWS,
    FORM_DEADLINE_LADDER,
    FORM_MATCHUP_STRIP,
    FORM_PAIRED_STAGE_BARS,
    FORM_PARTY_CONTROL_BARS,
    FORM_THEME_COMPACT_ROWS,
    card_visual_form_id,
    stamp_bundle_form_id,
)
from app.utils.discover_bundles import (
    _make_bundle_item,
    _make_deadline_family_bundle_item,
    _make_swings_bundle_item,
    _make_theme_bundle_item,
    assemble_nfl_division_roundup,
)
from app.utils.discover_opening_mix import card_visual_form_id as opening_mix_form_id
from app.utils.roundup_containers import (
    RoundupMembers,
    RoundupProducer,
    compose_roundup_feed_item,
)


def _sample_market_item(mid: int, name: str, prob: float = 0.65) -> dict:
    return {
        "type": "futures",
        "score": 40.0 + mid,
        "_sort_time": 1_700_000_000.0 + mid,
        "data": {
            "id": mid,
            "name": name,
            "status": "open",
            "top_outcomes": [
                {
                    "name": "Yes",
                    "probability": prob,
                    "probability_change_24h": 0.12,
                }
            ],
            "discover_card": {
                "comparison_theme": "rates",
                "threshold_unit": "%",
            },
        },
    }


def _roundup_producer(*, slug: str, presentation: str | None = None) -> RoundupProducer:
    return RoundupProducer(
        slug=slug,
        name="Test Round-up",
        kind="roundup",
        membership="rule",
        relations=("same_sport",),
        level="market",
        rule={},
        category="sports",
        tag="SPORTS",
        kicker="Round-up",
        section_title="Leaders",
        footer="Bain Luck blend",
        presentation=presentation,
        produce=lambda _db: None,
    )


def _roundup_members(*, paired: dict | None = None, machinery_card: dict | None = None) -> RoundupMembers:
    return RoundupMembers(
        members=[
            {
                "id": 101,
                "type": "futures",
                "card": {"id": 101, "name": "Alpha", "status": "open", "top_outcomes": []},
            }
        ],
        rows=[{"market_id": 101, "label": "Alpha", "probability": 0.62}],
        footer="Bain Luck blend",
        paired_metric_set=paired,
        machinery_card=machinery_card,
    )


def test_compose_roundup_stamps_legacy_strip_paired_and_machinery_without_altering_appearance():
    legacy_bars = compose_roundup_feed_item(
        _roundup_producer(slug="roundup-cfp-picture"),
        _roundup_members(),
    )
    assert legacy_bars is not None
    assert legacy_bars["data"]["form_id"] == FORM_BENCHMARK_STRIP
    assert legacy_bars["data"]["roundup"]["form_id"] == FORM_BENCHMARK_STRIP
    assert "machinery_card" not in legacy_bars["data"]["roundup"]
    assert card_visual_form_id(legacy_bars) == FORM_BENCHMARK_STRIP
    assert opening_mix_form_id(legacy_bars) == FORM_BENCHMARK_STRIP

    strip = compose_roundup_feed_item(
        _roundup_producer(slug="roundup-celtics-next-3-games", presentation="strip"),
        _roundup_members(),
    )
    assert strip is not None
    assert strip["data"]["form_id"] == FORM_MATCHUP_STRIP
    assert strip["data"]["roundup"]["form_id"] == FORM_MATCHUP_STRIP
    assert "machinery_card" not in strip["data"]["roundup"]
    assert opening_mix_form_id(strip) == FORM_MATCHUP_STRIP

    paired = compose_roundup_feed_item(
        _roundup_producer(slug="roundup-paired-legacy"),
        _roundup_members(paired={"title": "Best Picture", "entries": [{"name": "A"}]}),
    )
    assert paired is not None
    assert paired["data"]["form_id"] == FORM_PAIRED_STAGE_BARS
    assert paired["data"]["roundup"]["form_id"] == FORM_PAIRED_STAGE_BARS
    assert "machinery_card" not in paired["data"]["roundup"]

    machinery = compose_roundup_feed_item(
        _roundup_producer(slug="machinery-2028-presidential"),
        _roundup_members(machinery_card={"form_id": "contender_spotlight", "rows": []}),
    )
    assert machinery is not None
    assert machinery["data"]["form_id"] == "contender_spotlight"
    assert machinery["data"]["roundup"]["form_id"] == "contender_spotlight"
    assert opening_mix_form_id(machinery) == "contender_spotlight"


def test_discover_bundles_and_nfl_roundup_carry_visual_form_names():
    m1 = _sample_market_item(1, "Market One", 0.65)
    m2 = _sample_market_item(2, "Market Two", 0.45)

    comp = _make_bundle_item("rates", "cut", [m1, m2])
    assert comp["data"]["form_id"] == FORM_COMPARISON_COMPACT_ROWS
    assert "machinery_card" not in comp["data"]

    swings = _make_swings_bundle_item([(0.12, m1), (0.09, m2)])
    assert swings["data"]["form_id"] == FORM_THEME_COMPACT_ROWS

    geopolitics = _make_theme_bundle_item("story:ai", [m1, m2])
    assert geopolitics is not None
    assert geopolitics["data"]["form_id"] == FORM_THEME_COMPACT_ROWS

    senate = _sample_market_item(11, "Which party will win the U.S. Senate?", 0.56)
    senate["data"]["source"] = "kalshi"
    senate["data"]["group_id"] = "kalshi:CONTROLS-2026"
    senate["data"]["group_type"] = "kalshi_event"
    senate["data"]["market_type"] = "duel"
    senate["data"]["outcome_count"] = 2
    senate["data"]["discover_card"]["remaining_outcome_count"] = 0
    senate["data"]["top_outcomes"] = [
        {"name": "Democratic Party", "probability": 0.56},
        {"name": "Republican Party", "probability": 0.44},
    ]
    house = _sample_market_item(12, "Which party will win the U.S. House?", 0.61)
    house["data"]["source"] = "kalshi"
    house["data"]["group_id"] = "kalshi:CONTROLH-2026"
    house["data"]["group_type"] = "kalshi_event"
    house["data"]["market_type"] = "duel"
    house["data"]["outcome_count"] = 2
    house["data"]["discover_card"]["remaining_outcome_count"] = 0
    house["data"]["top_outcomes"] = [
        {"name": "Democratic Party", "probability": 0.61},
        {"name": "Republican Party", "probability": 0.39},
    ]
    congress = _make_theme_bundle_item("story:us_congress_control:2026", [senate, house])
    assert congress is not None
    assert congress["data"]["form_id"] == FORM_PARTY_CONTROL_BARS

    family_payload = {
        "story_key": "story:deadline_family:polymarket:g1",
        "group_id": "g1",
        "title": "AI Release",
        "shared_question": "When will AI ship?",
        "representative_market_id": 1,
        "representative_outcome_id": 10,
        "selection_reason": "biggest_move",
        "members": [{"market_id": 1}, {"market_id": 2}],
    }
    deadline = _make_deadline_family_bundle_item(family_payload, [m1, m2])
    assert deadline["data"]["form_id"] == FORM_DEADLINE_LADDER

    divisions = [
        SimpleNamespace(
            division=d,
            kalshi_market_id=100 + idx,
            polymarket_market_id=200 + idx,
            leader=SimpleNamespace(
                club=f"Club {idx}",
                kalshi_probability=0.55 - idx * 0.02,
                polymarket_probability=0.55 - idx * 0.02,
                probability=0.55 - idx * 0.02,
                rule="mean",
                observed_at=None,
            ),
            leaders=(),
        )
        for idx, d in enumerate(
            (
                "AFC East",
                "AFC North",
                "AFC South",
                "AFC West",
                "NFC East",
                "NFC North",
                "NFC South",
                "NFC West",
            )
        )
    ]
    nfl = assemble_nfl_division_roundup(divisions, [], collection_ref={"slug": "x", "href": "/collections/x", "name": "NFL"})
    assert nfl is not None
    assert nfl["data"]["form_id"] == FORM_BENCHMARK_STRIP
    assert nfl["data"]["roundup"]["form_id"] == FORM_BENCHMARK_STRIP
    assert "machinery_card" not in nfl["data"]["roundup"]


def test_publish_feed_item_stamps_preexisting_unstamped_bundles_without_mutating_render_fields():
    legacy_cached = {
        "type": "bundle",
        "score": 80.0,
        "data": {
            "id": "roundup:closest-games-tonight",
            "title": "The closest games tonight",
            "kind": "roundup",
            "story_key": "roundup:closest-games-tonight",
            "collection_ref": {"slug": "roundup-closest-games-tonight", "href": "/collections/roundup-closest-games-tonight", "name": "The closest games tonight"},
            "items": [],
            "roundup": {
                "kicker": "Tonight",
                "tag": "SPORTS",
                "footer": "Bain Luck blend",
                "rows": [
                    {"event_id": 10, "label": "A at B", "probability": 0.51},
                    {"event_id": 11, "label": "C at D", "probability": 0.52},
                    {"event_id": 12, "label": "E at F", "probability": 0.53},
                ],
            },
        },
    }
    before_roundup = deepcopy(legacy_cached["data"]["roundup"])
    _publish_feed_item(legacy_cached)
    assert legacy_cached["data"]["form_id"] == FORM_BENCHMARK_STRIP
    assert legacy_cached["data"]["roundup"]["form_id"] == FORM_BENCHMARK_STRIP
    assert "machinery_card" not in legacy_cached["data"]["roundup"]
    after_without_form = {k: v for k, v in legacy_cached["data"]["roundup"].items() if k != "form_id"}
    assert after_without_form == before_roundup

    # Non-bundle cards remain untouched
    futures = {"type": "futures", "data": {"id": 999, "name": "Solo"}}
    assert stamp_bundle_form_id(futures) is None
    assert card_visual_form_id(futures) is None
    assert "form_id" not in futures["data"]
