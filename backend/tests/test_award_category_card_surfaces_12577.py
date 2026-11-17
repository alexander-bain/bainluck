"""Tests for #12577: Live DB-hydrated Award Category Paired-Metric Card across Discover, Oscars collection, and category pages."""

from __future__ import annotations

import json
from datetime import datetime, timezone

import pytest

from app.services.paired_metric_register import (
    PAIRED_METRIC_REGISTER_PATH,
    find_paired_set_id_for_market,
    hydrate_paired_metric_set_from_markets,
    load_live_paired_metric_sets,
)
from app.utils.roundup_containers import (
    ROUNDUP_PRODUCERS,
    add_roundup_feed_items,
    evaluate_roundup_producer,
    insert_roundup_feed_items,
    register_roundup_definitions_from_dir,
    reset_roundup_cache_for_tests,
)


NOW_NOV_16 = datetime(2026, 11, 16, 20, 30, 0, tzinfo=timezone.utc)
OBS_NOV_16 = "2026-11-16T20:15:00Z"


def _live_best_picture_markets(
    *,
    odyssey_win: float = 0.52,
    odyssey_nom_kalshi: float = 0.96,
    odyssey_nom_poly: float = 0.94,
    nominees_settled: bool = False,
) -> list[dict]:
    nom_status = "resolved" if nominees_settled else "open"
    return [
        {
            "id": 5165726,
            "name": "Oscar nominees: Best Picture",
            "status": nom_status,
            "source": "kalshi",
            "category": "entertainment",
            "mutually_exclusive": False,
            "prices_updated_at": OBS_NOV_16,
            "outcomes": [
                {
                    "id": 516572601,
                    "name": "The Odyssey",
                    "probability": 1.0 if nominees_settled else odyssey_nom_kalshi,
                    "is_winner": True if nominees_settled else None,
                    "observed_at": OBS_NOV_16,
                },
                {
                    "id": 516572602,
                    "name": "You Can See Everything",
                    "probability": 1.0 if nominees_settled else 0.84,
                    "is_winner": True if nominees_settled else None,
                    "observed_at": OBS_NOV_16,
                },
                {
                    "id": 516572603,
                    "name": "The Black Ball",
                    "probability": 1.0 if nominees_settled else 0.78,
                    "is_winner": True if nominees_settled else None,
                    "observed_at": OBS_NOV_16,
                },
                {
                    "id": 516572604,
                    "name": "Dune: Part Three",
                    "probability": 0.0 if nominees_settled else 0.62,
                    "is_winner": False if nominees_settled else None,
                    "observed_at": OBS_NOV_16,
                },
                {
                    "id": 516572605,
                    "name": "Digger",
                    "probability": 1.0 if nominees_settled else 0.58,
                    "is_winner": True if nominees_settled else None,
                    "observed_at": OBS_NOV_16,
                },
            ],
        },
        {
            "id": 27988771,
            "name": "Oscars 2027: Best Picture Nominations",
            "status": nom_status,
            "source": "polymarket",
            "category": "entertainment",
            "mutually_exclusive": False,
            "prices_updated_at": OBS_NOV_16,
            "outcomes": [
                {
                    "id": 2798877101,
                    "name": "The Odyssey",
                    "probability": 1.0 if nominees_settled else odyssey_nom_poly,
                    "is_winner": True if nominees_settled else None,
                    "observed_at": OBS_NOV_16,
                },
                {
                    "id": 2798877102,
                    "name": "You Can See Everything",
                    "probability": 1.0 if nominees_settled else 0.86,
                    "is_winner": True if nominees_settled else None,
                    "observed_at": OBS_NOV_16,
                },
                {
                    "id": 2798877103,
                    "name": "The Black Ball",
                    "probability": 1.0 if nominees_settled else 0.80,
                    "is_winner": True if nominees_settled else None,
                    "observed_at": OBS_NOV_16,
                },
            ],
        },
        {
            "id": 6173044,
            "name": "Oscar Winner: Best Picture",
            "status": "open",
            "source": "kalshi",
            "category": "entertainment",
            "mutually_exclusive": True,
            "prices_updated_at": OBS_NOV_16,
            "outcomes": [
                {"id": 617304401, "name": "The Odyssey", "probability": odyssey_win, "observed_at": OBS_NOV_16},
                {"id": 617304402, "name": "You Can See Everything", "probability": 0.18, "observed_at": OBS_NOV_16},
                {"id": 617304403, "name": "The Black Ball", "probability": 0.14, "observed_at": OBS_NOV_16},
                {"id": 617304404, "name": "Dune: Part Three", "probability": 0.08, "observed_at": OBS_NOV_16},
                {"id": 617304405, "name": "Digger", "probability": 0.05, "observed_at": OBS_NOV_16},
            ],
        },
    ]


@pytest.mark.asyncio
async def test_live_paired_metric_hydration_uses_db_prices_never_stale_snapshot_and_handles_settled_stage1():
    raw_doc = json.loads(PAIRED_METRIC_REGISTER_PATH.read_text(encoding="utf-8"))
    raw_bp = raw_doc["sets"]["oscars-2027-best-picture"]

    # Empty / missing DB rows MUST return None (never static snapshot numbers) on reader surfaces
    assert hydrate_paired_metric_set_from_markets(raw_bp, {}, allow_register_fallback=False) is None

    # Live DB rows override static snapshot numbers and run server-side blend_with_verdict
    loaded = await load_live_paired_metric_sets(
        _live_best_picture_markets(odyssey_win=0.52, odyssey_nom_kalshi=0.96, odyssey_nom_poly=0.94),
        set_ids=["oscars-2027-best-picture"],
    )
    bp = loaded["oscars-2027-best-picture"]
    odyssey = next(e for e in bp["entries"] if e["subject"] == "The Odyssey")
    assert odyssey["stage_2_probability"] == pytest.approx(0.52)
    assert odyssey["stage_1_probability"] == pytest.approx(0.95)
    assert odyssey["stage_1_blend_authority"] == "server:futures_source_merge.blend_with_verdict"
    assert "#" not in bp["subtitle"]
    assert "The Odyssey leads Best Picture" in bp["title"]

    # Post-nominations settled state marks nominated films 'yes' and non-nominees 'no'
    settled_loaded = await load_live_paired_metric_sets(
        _live_best_picture_markets(nominees_settled=True),
        set_ids=["oscars-2027-best-picture"],
    )
    s_bp = settled_loaded["oscars-2027-best-picture"]
    assert s_bp["stage_1_settled"] is True
    by_subj = {e["subject"]: e for e in s_bp["entries"]}
    assert by_subj["The Odyssey"]["stage_1_settled_state"] == "yes"
    assert by_subj["Dune: Part Three"]["stage_1_settled_state"] == "no"


def test_find_paired_set_id_for_market_resolves_stage1_companion_and_stage2():
    assert find_paired_set_id_for_market(6173044) == "oscars-2027-best-picture"
    assert find_paired_set_id_for_market(5165726) == "oscars-2027-best-picture"
    assert find_paired_set_id_for_market(27988771) == "oscars-2027-best-picture"
    assert find_paired_set_id_for_market(5869747) == "oscars-2027-best-director"
    assert find_paired_set_id_for_market(999999999) is None


@pytest.mark.asyncio
async def test_roundup_oscars_best_picture_serves_discover_paired_card_and_folds_constituents():
    reset_roundup_cache_for_tests()
    register_roundup_definitions_from_dir()
    assert "roundup-oscars-best-picture" in ROUNDUP_PRODUCERS
    producer = ROUNDUP_PRODUCERS["roundup-oscars-best-picture"]

    pool = _live_best_picture_markets()
    feed_item, container_payload = await evaluate_roundup_producer(
        producer, pool, now=NOW_NOV_16
    )
    assert feed_item is not None
    assert container_payload is not None
    assert feed_item["data"]["roundup"]["paired_metric_set"]["set_id"] == "oscars-2027-best-picture"
    assert container_payload["paired_metric_set"]["set_id"] == "oscars-2027-best-picture"
    assert container_payload["parent"]["slug"] == "oscars-2027"

    # Contradictory win > nomination (>2pp tolerance) refuses cleanly
    bad_pool = _live_best_picture_markets(odyssey_win=0.80, odyssey_nom_kalshi=0.50, odyssey_nom_poly=0.50)
    reset_roundup_cache_for_tests()
    bad_feed, bad_container = await evaluate_roundup_producer(
        producer, bad_pool, now=NOW_NOV_16
    )
    assert bad_feed is None
    assert bad_container is None

    # Seating the paired Best Picture card prunes duplicate #6173044 out of an existing Oscars theme bundle
    theme_bundle = {
        "type": "bundle",
        "score": 88.0,
        "reason": "Oscars races",
        "headline": "Where do the Oscars races stand?",
        "data": {
            "id": "theme:oscars-2027",
            "kind": "theme",
            "title": "Where do the Oscars races stand?",
            "item_count": 3,
            "member_ids": [6173044, 900001, 900002],
            "items": [
                {"type": "futures", "score": 85.0, "data": {"id": 6173044, "name": "Oscar Winner: Best Picture"}},
                {"type": "futures", "score": 80.0, "data": {"id": 900001, "name": "Oscars 2027: Best Costume Design"}},
                {"type": "futures", "score": 78.0, "data": {"id": 900002, "name": "Oscars 2027: Best Casting"}},
            ],
        },
    }
    filler = [
        {"type": "futures", "score": 90.0 - i, "data": {"id": 800000 + i, "name": f"Market {i}"}}
        for i in range(6)
    ]
    merged = insert_roundup_feed_items(
        filler[:3] + [theme_bundle] + filler[3:],
        [feed_item],
        seat_floor=2,
        page_window=10,
        now=NOW_NOV_16,
    )
    surviving_theme = next(
        it for it in merged if it.get("type") == "bundle" and it["data"].get("id") == "theme:oscars-2027"
    )
    surviving_child_ids = [c["data"]["id"] for c in surviving_theme["data"]["items"]]
    assert 6173044 not in surviving_child_ids
    assert surviving_child_ids == [900001, 900002]
    assert surviving_theme["data"]["item_count"] == 2

