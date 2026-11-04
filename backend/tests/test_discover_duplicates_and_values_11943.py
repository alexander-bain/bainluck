"""#11943 — Duplicate cards and impossible values on the Discover feed.

Covers:
1. WTA Chennai twice: Polymarket ``WTA Tennis: Chennai, India, Winner`` (68662981)
   and Kalshi ``WTA Chennai Winner`` (68660446) fold via pairwise tennis tour-stop
   normalization in ``discover_bundles._comparison_title``.
2. Two UFC concepts at one start: ``event:ufc:26nov06`` and
   ``event:ufc:26nov07ufcfightnight`` sharing ``(domain="ufc", start_date="2026-11-07T22:00:00+00:00")``
   dedupe in ``_drop_duplicate_bout_concepts``.
3. TOTO Japan Classic Winner (68977820) with three players at 50.0% each (sum 150%)
   is refused by ``is_placeholder_flat_field`` while genuine co-favorite fields
   like WTA Chennai (9.5% / 9.5% / 9.5% = 28.5%) survive.
4. Golf tournament ``commence_time`` is truncated to whole minutes (``:00+00:00``)
   in ``routes/golf.py::_build_tournament_entry`` and ``routes/feed.py``.
5. ``TIME Person of the Year`` and ``2028 "announce a run"`` sibling families
   normalize resolution dates and ``Presidential run`` -> ``presidential run``
   in ``normalize_registered_family_market`` and ``submarket_resolution_date``.
"""

from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from app.routes.feed import _drop_duplicate_bout_concepts
from app.routes.golf import _build_tournament_entry
from app.tasks.polymarket import submarket_resolution_date
from app.utils.discover_bundles import (
    _comparison_title,
    _dedupe_same_question_members,
    fold_same_question_cards,
)
from app.utils.feed_market_quality import is_placeholder_flat_field
from app.utils.sibling_family import (
    normalize_registered_family_market,
    select_sibling_family,
)


def test_wta_chennai_polymarket_and_kalshi_twins_fold():
    poly = {
        "id": 68662981,
        "name": "WTA Tennis: Chennai, India, Winner",
        "source": "polymarket",
        "resolution_date": "2026-11-08T12:00:00+00:00",
        "top_outcomes": [
            {"name": "Zeynep Sonmez", "probability": 0.145},
            {"name": "Tatjana Maria", "probability": 0.095},
        ],
    }
    kalshi = {
        "id": 68660446,
        "name": "WTA Chennai Winner",
        "source": "kalshi",
        "resolution_date": "2026-11-08T05:00:00+00:00",
        "top_outcomes": [
            {"name": "Zeynep Sonmez", "probability": 0.095},
            {"name": "Tatjana Maria", "probability": 0.095},
        ],
    }
    assert _comparison_title(poly, kalshi) == "WTA Chennai Winner"
    items = [
        {"type": "futures", "score": 76.0, "data": poly},
        {"type": "futures", "score": 72.0, "data": kalshi},
    ]
    kept, folded = _dedupe_same_question_members(items)
    assert len(kept) == 1
    assert len(folded) == 1
    assert kept[0]["data"]["id"] == 68662981

    standalone_kept = fold_same_question_cards(items)
    assert len(standalone_kept) == 1
    assert standalone_kept[0]["data"]["id"] == 68662981


def test_wta_different_tour_stops_do_not_fold():
    chennai = {
        "id": 68662981,
        "name": "WTA Tennis: Chennai, India, Winner",
        "source": "polymarket",
        "resolution_date": "2026-11-08T12:00:00+00:00",
    }
    austin = {
        "id": 68660999,
        "name": "WTA Austin Winner",
        "source": "kalshi",
        "resolution_date": "2026-11-08T05:00:00+00:00",
    }
    assert _comparison_title(chennai, austin) == "WTA Tennis: Chennai, India, Winner"


def test_ufc_concepts_sharing_same_domain_and_start_date_dedupe():
    ufc_nov06 = {
        "type": "concept",
        "score": 48.0,
        "data": {
            "key": "event:ufc:26nov06",
            "name": "Fight Night: Waldo Cortes-Acosta vs Johnny Walker",
            "domain": "ufc",
            "start_date": "2026-11-07T22:00:00+00:00",
            "headline_bout": {
                "fighter_a": "Waldo Cortes-Acosta",
                "fighter_b": "Johnny Walker",
            },
        },
    }
    ufc_nov07 = {
        "type": "concept",
        "score": 53.0,
        "data": {
            "key": "event:ufc:26nov07ufcfightnight",
            "name": "UFC Fight Night",
            "domain": "ufc",
            "start_date": "2026-11-07T22:00:00+00:00",
            "headline_bout": {
                "fighter_a": "Gabriel Bonfim",
                "fighter_b": "Randy Brown",
            },
        },
    }
    ufc_later = {
        "type": "concept",
        "score": 40.0,
        "data": {
            "key": "event:ufc:26nov07",
            "name": "Fight Night: Seok Hyun Ko vs Wellington Turman",
            "domain": "ufc",
            "start_date": "2026-11-08T01:00:00+00:00",
            "headline_bout": {
                "fighter_a": "Seok Hyun Ko",
                "fighter_b": "Wellington Turman",
            },
        },
    }
    deduped = _drop_duplicate_bout_concepts([ufc_nov06, ufc_nov07, ufc_later])
    assert [it["data"]["key"] for it in deduped] == [
        "event:ufc:26nov07ufcfightnight",
        "event:ufc:26nov07",
    ]


def test_toto_japan_classic_50_50_50_placeholder_field_refused_while_co_favorites_kept():
    toto_outcomes = [
        (0.50, None, None),
        (0.50, None, None),
        (0.50, None, None),
        (0.01, None, None),
    ]
    assert is_placeholder_flat_field(toto_outcomes, True) is True

    # WTA Chennai co-favorites (9.5% each = 28.5% <= 100%) are NOT refused.
    wta_chennai_outcomes = [
        (0.095, 0.08, 0.11),
        (0.095, 0.08, 0.11),
        (0.095, 0.08, 0.11),
        (0.075, 0.06, 0.09),
    ]
    assert is_placeholder_flat_field(wta_chennai_outcomes, True) is False


def test_golf_tournament_commence_time_truncated_to_whole_minutes():
    market = SimpleNamespace(
        name="World Wide Technology Championship Winner",
        external_id="KXPGAWWT-26",
        source="kalshi",
        market_metadata={"tour": "pga"},
    )
    golfer_data = {
        "ben_griffin": {
            "name": "Ben Griffin",
            "sources": {"kalshi": 0.095},
            "movement_24h": None,
            "movement_is_dated": False,
            "opening_probability": 0.095,
        }
    }
    entry = _build_tournament_entry(
        tourn_key="world_wide_technology_championship",
        tourn_markets=[market],
        golfer_data=golfer_data,
        prop_markets_list=[],
        market_ids=[1],
        market_sources=["kalshi"],
        earliest_commence=datetime(2026, 11, 4, 16, 10, 46, tzinfo=timezone.utc),
        latest_resolution=datetime(2026, 11, 9, 23, 0, 0, tzinfo=timezone.utc),
    )
    assert entry is not None
    assert entry["commence_time"] == "2026-11-04T16:10:00+00:00"


def test_time_person_of_the_year_and_announce_run_normalization():
    event = SimpleNamespace(
        title="TIME Person of the Year 2026",
        end_date=datetime(2026, 12, 31, 0, 0, tzinfo=timezone.utc),
    )
    odd_leg = SimpleNamespace(
        question="Will Jensen Huang be named TIME's Person of the Year for 2026?",
        end_date=datetime(2026, 12, 30, 12, 0, tzinfo=timezone.utc),
    )
    assert submarket_resolution_date(event, odd_leg) == datetime(
        2026, 12, 31, 0, 0, tzinfo=timezone.utc
    )

    newsom_name, newsom_dt = normalize_registered_family_market(
        "Will Gavin Newsom announce a Presidential run before 2027?",
        datetime(2026, 12, 31, 12, 0, tzinfo=timezone.utc),
    )
    assert newsom_name == "Will Gavin Newsom announce a presidential run before 2027?"
    assert newsom_dt == datetime(2026, 12, 31, 23, 59, tzinfo=timezone.utc)

    now = datetime(2026, 11, 4, 12, 0, tzinfo=timezone.utc)
    raw_candidates = [
        (1, "Will Gavin Newsom announce a Presidential run before 2027?", "2026-12-31T12:00:00Z", 0.34),
        (2, "Will JD Vance announce a presidential run before 2027?", "2026-12-31T23:59:00Z", 0.28),
        (3, "Will Josh Shapiro announce a presidential run before 2027?", "2026-12-31T12:00:00Z", 0.19),
    ]
    markets_by_id = {}
    for mid, raw_n, raw_d, p in raw_candidates:
        n_name, n_date = normalize_registered_family_market(raw_n, raw_d)
        markets_by_id[mid] = {
            "id": mid,
            "name": n_name,
            "status": "open",
            "source": "polymarket",
            "group_id": "polymarket:11943",
            "resolution_date": n_date,
            "updated_at": "2026-11-04T10:00:00Z",
            "outcomes": [
                {
                    "id": mid * 10 + 1,
                    "name": "Yes",
                    "probability": p,
                    "observed_at": "2026-11-04T10:00:00Z",
                },
                {
                    "id": mid * 10 + 2,
                    "name": "No",
                    "probability": round(1.0 - p, 4),
                    "observed_at": "2026-11-04T10:00:00Z",
                },
            ],
        }
    plan = select_sibling_family(
        markets_by_id,
        expected_source="polymarket",
        template="Will {subject} announce a presidential run before {deadline}?",
        title_template="Will {subject} announce a presidential run before {deadline}?",
        kicker_prefix="2028 Field",
        subject_unit="candidates",
        footer="Each row is its own market. They don't add up to 100%.",
        section_titles=(),
        now=now,
        withheld_by_market={},
    )
    assert [r["label"] for r in plan.rows] == [
        "Gavin Newsom",
        "JD Vance",
        "Josh Shapiro",
    ]
