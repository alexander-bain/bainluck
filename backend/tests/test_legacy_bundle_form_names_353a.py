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


def test_opening_mix_treats_lookalike_form_groups_as_one_look_and_preserves_wire_form_id():
    from datetime import datetime, timezone

    from app.utils.bundle_visual_form import discover_opening_form_look
    from app.utils.discover_opening_mix import apply_discover_opening_mix

    assert discover_opening_form_look(FORM_THEME_COMPACT_ROWS) == "compact_rows"
    assert discover_opening_form_look(FORM_COMPARISON_COMPACT_ROWS) == "compact_rows"
    assert discover_opening_form_look(FORM_PARTY_CONTROL_BARS) == "compact_rows"
    assert discover_opening_form_look("coin_flip_matchups") == "duel_matchups"
    assert discover_opening_form_look("matchup_slate") == "duel_matchups"
    assert discover_opening_form_look("benchmark_strip") == "benchmark_strip"
    assert discover_opening_form_look("  ") is None
    assert discover_opening_form_look(None) is None

    def _group(
        idx: int,
        slug: str,
        title: str,
        *,
        category: str,
        kind: str,
        form_id: str,
        score: float,
    ) -> dict:
        data: dict = {
            "id": slug,
            "kind": kind,
            "title": title,
            "category": category,
            "llm_sport_category": category,
            "items": [
                {
                    "type": "futures",
                    "score": score,
                    "data": {
                        "id": 90_000 + idx,
                        "name": title,
                        "status": "open",
                        "category": category,
                        "llm_sport_category": category,
                        "top_outcomes": [{"id": 900_000 + idx, "name": "Yes", "probability": 0.52}],
                    },
                }
            ],
        }
        if kind == "roundup":
            data["roundup"] = {
                "tag": "roundup",
                "level": "member",
                "kicker": category,
                "footer": "Test",
                "relations": ["same_subject"],
                "rows": [{"label": "Opt A", "percent": 52, "href": f"/futures/{90_000 + idx}"}],
                "machinery_card": {"form_id": form_id},
            }
        else:
            data["form_id"] = form_id
            data["story_key"] = f"story:{slug}"
        return {
            "type": "bundle",
            "score": score,
            "reason": title,
            "headline": title,
            "data": data,
        }

    def _single(mid: int, name: str, *, category: str, score: float = 80.0) -> dict:
        return {
            "type": "futures",
            "score": score,
            "reason": name,
            "headline": name,
            "data": {
                "id": mid,
                "name": name,
                "status": "open",
                "category": category,
                "llm_sport_category": category,
                "top_outcomes": [{"id": mid * 10, "name": "Yes", "probability": 0.51}],
            },
        }

    now = datetime(2026, 11, 24, 18, 0, tzinfo=timezone.utc)

    # Group 1: theme_compact_rows + comparison_compact_rows + party_control_bars -> "compact_rows" (<= 2)
    compact_deck = [
        _single(1, "Brewers Opening Day", category="Sports", score=88.0),
        _single(2, "SpaceX Starship orbit", category="Tech", score=86.0),
        _single(3, "Fed June rate move", category="Economics", score=85.0),
        _group(10, "g-theme", "Best sci-fi movie", category="Entertainment", kind="theme", form_id=FORM_THEME_COMPACT_ROWS, score=99.0),
        _group(11, "g-comp", "AI benchmarks comparison", category="Tech", kind="comparison", form_id=FORM_COMPARISON_COMPACT_ROWS, score=98.0),
        _group(12, "g-party", "Senate control forecast", category="Politics", kind="theme", form_id=FORM_PARTY_CONTROL_BARS, score=97.0),
        _group(13, "g-chart", "Tech and Space Movers", category="Tech", kind="roundup", form_id="probability_history_chart", score=95.0),
        _group(14, "g-paired", "Oscars Best Picture", category="Entertainment", kind="roundup", form_id=FORM_PAIRED_STAGE_BARS, score=94.0),
        _group(15, "g-grid", "European League Titles", category="Sports", kind="roundup", form_id="sibling_fields_grid", score=93.0),
        _group(16, "g-bench", "Longevity Milestones", category="Culture", kind="roundup", form_id=FORM_BENCHMARK_STRIP, score=92.0),
        _group(17, "g-nba", "NBA Playoff Races", category="Sports", kind="roundup", form_id=FORM_MATCHUP_STRIP, score=91.0),
        _group(18, "g-odd", "Chess Oddities", category="Culture", kind="roundup", form_id="contender_spotlight", score=90.0),
        _group(19, "g-weather", "Record heat 2026", category="Weather", kind="roundup", form_id="calendar_strip", score=89.0),
    ]
    mixed_compact = apply_discover_opening_mix(compact_deck, now=now)
    top10_compact = mixed_compact[:10]
    assert sum(1 for it in top10_compact if discover_opening_form_look(card_visual_form_id(it)) == "compact_rows") <= 2
    by_id = {it["data"]["id"]: it for it in mixed_compact if it.get("type") == "bundle"}
    assert by_id["g-theme"]["data"]["form_id"] == FORM_THEME_COMPACT_ROWS
    assert by_id["g-comp"]["data"]["form_id"] == FORM_COMPARISON_COMPACT_ROWS
    assert by_id["g-party"]["data"]["form_id"] == FORM_PARTY_CONTROL_BARS

    # Group 2: coin_flip_matchups + matchup_slate -> "duel_matchups" (<= 2)
    # Give every topic at least two non-duel groups (including two TOPIC_ODD slugs)
    # so the form cap itself enforces <= 2 combined duel_matchups without thin-supply fallback.
    duel_deck = [
        _single(21, "Oscars Best Director", category="Entertainment", score=88.0),
        _single(22, "GDP growth Q4", category="Economics", score=86.0),
        _single(23, "AI coding benchmark", category="Tech", score=85.0),
        _group(30, "machinery-long-shots", "Long-Shot Milestones", category="Odd", kind="roundup", form_id="coin_flip_matchups", score=99.0),
        _group(31, "machinery-google-year-in-search-2026", "Year in Search Matchups", category="Odd", kind="roundup", form_id="matchup_slate", score=98.0),
        _group(32, "g-coin-c", "Celebrity Duel C", category="Entertainment", kind="roundup", form_id="coin_flip_matchups", score=97.0),
        _group(33, "g-slate-d", "Tech Showdown Slate", category="Tech", kind="roundup", form_id="matchup_slate", score=96.0),
        _group(34, "machinery-elon-musk-side-quests", "Elon Musk Side Quests", category="Odd", kind="roundup", form_id=FORM_BENCHMARK_STRIP, score=95.0),
        _group(35, "roundup-tomorrows-highs", "Tomorrow's Highs", category="Weather", kind="roundup", form_id="calendar_strip", score=94.0),
        _group(36, "machinery-pop-culture-oddities", "Pop Culture Oddities", category="Odd", kind="roundup", form_id="contender_spotlight", score=93.5),
        _group(37, "g-chart2", "AI Model Movers", category="Tech", kind="roundup", form_id="probability_history_chart", score=93.0),
        _group(38, "g-grid2", "Best Actor Field", category="Entertainment", kind="roundup", form_id="sibling_fields_grid", score=92.5),
        _group(39, "g-ent-backup", "Grammy Winners", category="Entertainment", kind="roundup", form_id=FORM_THEME_COMPACT_ROWS, score=92.0),
        _group(40, "g-paired2", "NHL Awards", category="Sports", kind="roundup", form_id=FORM_PAIRED_STAGE_BARS, score=91.0),
        _group(41, "g-nba2", "NBA Playoffs", category="Sports", kind="roundup", form_id=FORM_MATCHUP_STRIP, score=90.0),
        _group(42, "g-tech-backup", "Semiconductor Outlook", category="Tech", kind="roundup", form_id=FORM_COMPARISON_COMPACT_ROWS, score=89.0),
        _group(43, "g-pwm2", "Fed Rate Cuts 2026", category="Politics", kind="theme", form_id="paired_stage_bars", score=88.0),
    ]
    mixed_duel = apply_discover_opening_mix(duel_deck, now=now)
    top10_duel = mixed_duel[:10]
    assert sum(1 for it in top10_duel if discover_opening_form_look(card_visual_form_id(it)) == "duel_matchups") <= 2
    by_id_duel = {it["data"]["id"]: it for it in mixed_duel if it.get("type") == "bundle"}
    assert by_id_duel["machinery-long-shots"]["data"]["roundup"]["machinery_card"]["form_id"] == "coin_flip_matchups"
    assert by_id_duel["machinery-google-year-in-search-2026"]["data"]["roundup"]["machinery_card"]["form_id"] == "matchup_slate"
