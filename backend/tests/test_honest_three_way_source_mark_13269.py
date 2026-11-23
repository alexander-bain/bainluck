"""#13269 / 196-A: honest three-way away and draw rows in "Where this number comes from".

Pins all four conditions from Fable's 8:38 PM PT review on #13269:
1. Away and draw values are stored from the same reading and timestamp as home,
   cleared when absent, and refused on read if home value or timestamp moved
   without them (a row never pairs a new home number with an older away number).
2. `allow_unpriced=True` stays off for every caller except three-way away and
   draw rows (`three_way_side_source_mark`).
3. Route test on Fulham at Manchester City (event 15340914): Kalshi 70.5 / 12.5
   / 17.5 and Polymarket 70.5 / 11.5 / 17.5 serve 0.125 and 0.115 on the away
   source sheet (and 0.175 / 0.175 on draw), never a worked-out 0.1283 for both.
4. Pre-write transition window and Fable's worked case (90 / 7 / 3, venues at
   home 86 and 88 without own away prices): Sportsbooks shows 0.03 while venues
   without their own away price are named with `probability: None`.
"""

from __future__ import annotations

import ast
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.routes.events import _format_event_with_aggregated_odds
from app.routes.league_futures import _format_game_brief
from app.tasks.live_blend_refresh import atomic_stamp_expression
from app.utils.aggregation import (
    AWAY_VALUE_KEY,
    DRAW_VALUE_KEY,
    THREE_WAY_AT_KEY,
    THREE_WAY_HOME_VALUE_KEY,
    extract_source_three_way_side,
    stamp_source_reading,
)
from app.utils.source_mark import (
    blended_source_marks,
    quote_source_mark,
    three_way_side_source_mark,
)


class TestCondition1SameReadingAndTimestampBinding:
    def test_away_and_draw_stored_with_same_home_and_timestamp_and_cleared_when_absent(
        self,
    ):
        t1 = datetime.now(timezone.utc) - timedelta(minutes=2)
        t2 = t1 + timedelta(minutes=1)

        bag = stamp_source_reading(
            {},
            "kalshi",
            0.705,
            now=t1,
            away_value=0.125,
            draw_value=0.175,
        )
        entry = bag["kalshi"]
        assert entry["value"] == 0.705
        assert entry[AWAY_VALUE_KEY] == 0.125
        assert entry[DRAW_VALUE_KEY] == 0.175
        assert entry[THREE_WAY_HOME_VALUE_KEY] == 0.705
        assert entry[THREE_WAY_AT_KEY] == entry["updated_at"] == t1.isoformat()
        assert extract_source_three_way_side(bag, "kalshi", 0.705, "away") == 0.125
        assert extract_source_three_way_side(bag, "kalshi", 0.705, "draw") == 0.175

        # Half A: a newer write without away/draw clears all four keys completely.
        bag2 = stamp_source_reading(bag, "kalshi", 0.68, now=t2)
        entry2 = bag2["kalshi"]
        assert entry2["value"] == 0.68
        assert AWAY_VALUE_KEY not in entry2
        assert DRAW_VALUE_KEY not in entry2
        assert THREE_WAY_HOME_VALUE_KEY not in entry2
        assert THREE_WAY_AT_KEY not in entry2
        assert extract_source_three_way_side(bag2, "kalshi", 0.68, "away") is None
        assert extract_source_three_way_side(bag2, "kalshi", 0.68, "draw") is None

    def test_newer_home_value_or_newer_timestamp_never_pairs_with_older_away_number(
        self,
    ):
        t1 = datetime.now(timezone.utc) - timedelta(minutes=5)
        t2 = t1 + timedelta(minutes=4)
        bag = stamp_source_reading(
            {},
            "kalshi",
            0.705,
            now=t1,
            away_value=0.125,
            draw_value=0.175,
        )

        # Half B1: home value moved to 0.74 without refreshing away/draw.
        drifted_value = {"kalshi": {**bag["kalshi"], "value": 0.74}}
        assert extract_source_three_way_side(drifted_value, "kalshi", 0.74, "away") is None
        assert extract_source_three_way_side(drifted_value, "kalshi", 0.74, "draw") is None

        # Half B2: updated_at advanced to t2 while three_way_at is still t1.
        drifted_time = {"kalshi": {**bag["kalshi"], "updated_at": t2.isoformat()}}
        assert extract_source_three_way_side(drifted_time, "kalshi", 0.705, "away") is None
        assert extract_source_three_way_side(drifted_time, "kalshi", 0.705, "draw") is None

        # Half B3: selected home input differs from stored anchor.
        assert extract_source_three_way_side(bag, "kalshi", 0.74, "away") is None

        # Through blended_source_marks, the venue is named with probability=None.
        ev = SimpleNamespace(win_probability_sources=drifted_time)
        _home, away = blended_source_marks(
            ev,
            [("kalshi", 0.705)],
            three_way_probs=(0.705, 0.125, 0.170),
        )
        assert away["state"] == "single"
        assert away["sources"][0]["key"] == "kalshi"
        assert away["sources"][0]["probability"] is None

    def test_atomic_stamp_expression_strips_prior_three_way_keys_and_writes_new_ones(
        self,
    ):
        from sqlalchemy.dialects import postgresql

        t1 = datetime.now(timezone.utc)
        expr_with = atomic_stamp_expression(
            "kalshi", 0.705, stamped_at=t1, away_value=0.125, draw_value=0.175
        )
        sql_with = str(expr_with.compile(dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}))
        for key in (AWAY_VALUE_KEY, DRAW_VALUE_KEY, THREE_WAY_HOME_VALUE_KEY, THREE_WAY_AT_KEY):
            assert key in sql_with

        expr_without = atomic_stamp_expression("kalshi", 0.68, stamped_at=t1)
        sql_without = str(expr_without.compile(dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}))
        # Strips all four keys from prior_entry and does not inject away/draw values.
        assert f"CAST('{AWAY_VALUE_KEY}' AS TEXT)" in sql_without
        assert f"CAST('{DRAW_VALUE_KEY}' AS TEXT)" in sql_without
        assert '"away_value":' not in sql_without
        assert '"draw_value":' not in sql_without


class TestCondition2AllowUnpricedStrictlyScoped:
    def test_quote_source_mark_refuses_none_by_default_and_admits_only_when_opted_in(
        self,
    ):
        assert quote_source_mark([{"key": "kalshi", "probability": None}]) == {
            "state": "none",
            "sources": [],
            "reason": "source_evidence_incomplete",
        }
        admitted = quote_source_mark(
            [
                {"key": "betting", "probability": 0.03, "count": 11},
                {"key": "kalshi", "probability": None},
            ],
            method="Bain Luck blend",
            allow_unpriced=True,
        )
        assert admitted["state"] == "blend"
        by_key = {s["key"]: s for s in admitted["sources"]}
        assert by_key["betting"]["probability"] == 0.03
        assert by_key["kalshi"]["probability"] is None
        assert by_key["kalshi"]["name"] == "Kalshi"

        # Invalid non-None values still fail closed even with allow_unpriced=True.
        assert quote_source_mark(
            [{"key": "kalshi", "probability": 1.5}],
            allow_unpriced=True,
        ) == {
            "state": "none",
            "sources": [],
            "reason": "source_evidence_incomplete",
        }

    def test_only_three_way_side_source_mark_sets_allow_unpriced_true(self):
        app_root = Path(__file__).resolve().parents[1] / "app"
        callers: list[tuple[str, str]] = []
        for py_path in sorted(app_root.rglob("*.py")):
            tree = ast.parse(py_path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    for sub in ast.walk(node):
                        if isinstance(sub, ast.Call):
                            for kw in sub.keywords:
                                if kw.arg == "allow_unpriced":
                                    callers.append(
                                        (
                                            str(py_path.relative_to(app_root)),
                                            node.name,
                                        )
                                    )
        assert callers == [("utils/source_mark.py", "three_way_side_source_mark")]


class TestCondition3RealMatchFulhamAtManCity15340914:
    def test_fulham_at_manchester_city_15340914_serves_each_venues_own_away_and_draw(
        self,
    ):
        now = datetime.now(timezone.utc)
        read_at = now - timedelta(seconds=30)

        wps = stamp_source_reading(
            {},
            "betting",
            0.6877,
            now=now,
            price_read_at=read_at,
            away_value=0.1359,
            draw_value=0.1764,
        )
        wps["betting_book_count"] = 11
        wps = stamp_source_reading(
            wps,
            "kalshi",
            0.705,
            now=now,
            price_read_at=read_at,
            away_value=0.125,
            draw_value=0.175,
        )
        wps = stamp_source_reading(
            wps,
            "polymarket",
            0.705,
            now=now,
            price_read_at=read_at,
            away_value=0.115,
            draw_value=0.175,
        )

        event = SimpleNamespace(
            id=15340914,
            external_id="epl-15340914",
            sport=SimpleNamespace(key="soccer_epl", name="Premier League"),
            home_team_name="Manchester City",
            away_team_name="Fulham",
            commence_time=now + timedelta(hours=12),
            completed_at=None,
            status="scheduled",
            home_score=None,
            away_score=None,
            score_source=None,
            win_probability_sources=wps,
            opening_home_probability=0.6877,
            opening_away_probability=0.1359,
            opening_home_spread=None,
            opening_over_under=None,
            opening_favorite=None,
            espn_win_prob_home=None,
            espn_event_id=None,
            game_clock=None,
            period=None,
            period_scores=None,
            broadcast_info=None,
            event_tags=[],
            home_team_id=None,
            away_team_id=None,
            home_team=None,
            away_team=None,
            llm_importance=None,
            llm_gender=None,
            llm_level=None,
            llm_league=None,
            raw_ei=None,
            venue=None,
            metadata_=None,
            box_score_data=None,
        )

        # List/search route formatter
        formatted = _format_event_with_aggregated_odds(
            event,
            odds_data={
                "aggregated": {
                    "home_probability": 0.6877,
                    "away_probability": 0.1359,
                    "home_spread": None,
                    "over_under": None,
                    "home_moneyline": None,
                    "away_moneyline": None,
                    "projected_home_score": None,
                    "projected_away_score": None,
                    "bookmaker_count": 11,
                },
                "bookmakers": [],
            },
            three_way_books=(0.6877, 0.1359),
        )
        away_by_key = {
            s["key"]: s["probability"]
            for s in formatted["away_source_mark"]["sources"]
        }
        assert away_by_key["kalshi"] == 0.125
        assert away_by_key["polymarket"] == 0.115
        assert away_by_key["betting"] == 0.1359
        # Explicitly NOT the old worked-out 0.1283 for both venues.
        assert away_by_key["kalshi"] != away_by_key["polymarket"]

        # League rail formatter agrees identically.
        brief = _format_game_brief(
            event, "soccer_epl", three_way_books=(0.6877, 0.1359)
        )
        brief_away = {
            s["key"]: s["probability"]
            for s in brief["away_source_mark"]["sources"]
        }
        assert brief_away == away_by_key

        # Shared draw-side source mark carries each venue's own draw price.
        draw_mark = three_way_side_source_mark(
            event,
            [("betting", 0.6877), ("kalshi", 0.705), ("polymarket", 0.705)],
            side="draw",
            method="Bain Luck blend",
            books_three_way=(0.6877, 0.1359),
        )
        draw_by_key = {s["key"]: s["probability"] for s in draw_mark["sources"]}
        assert draw_by_key["kalshi"] == 0.175
        assert draw_by_key["polymarket"] == 0.175
        assert draw_by_key["betting"] == 0.1764


class TestCondition4PreWriteWindowAndWorkedCase:
    def test_fables_worked_case_90_7_3_names_unpriced_venues_without_inventing_4_2_or_3_6(
        self,
    ):
        now = datetime.now(timezone.utc)
        read_at = now - timedelta(seconds=15)
        # Transition window: no venue has stamped away_value/draw_value yet.
        wps = stamp_source_reading({}, "betting", 0.90, now=now, price_read_at=read_at)
        wps["betting_book_count"] = 10
        wps = stamp_source_reading(wps, "kalshi", 0.86, now=now, price_read_at=read_at)
        wps = stamp_source_reading(wps, "polymarket", 0.88, now=now, price_read_at=read_at)
        event = SimpleNamespace(win_probability_sources=wps)

        home_mark, away_mark = blended_source_marks(
            event,
            [("betting", 0.90), ("kalshi", 0.86), ("polymarket", 0.88)],
            method="Bain Luck blend",
            three_way_probs=(0.88, 0.04, 0.08),
            books_three_way=(0.90, 0.03),
        )
        home_by_key = {s["key"]: s["probability"] for s in home_mark["sources"]}
        away_by_key = {s["key"]: s["probability"] for s in away_mark["sources"]}

        assert home_by_key == {"betting": 0.90, "kalshi": 0.86, "polymarket": 0.88}
        assert away_mark["state"] == "blend"
        # Sportsbooks shows its own 3%; venues without own away quotes show None
        # (never worked-out 4.2% or 3.6%, and never 14% or 12%).
        assert away_by_key == {"betting": 0.03, "kalshi": None, "polymarket": None}
        assert [s["name"] for s in away_mark["sources"]] == [
            "Kalshi",
            "Polymarket",
            "Sportsbooks",
        ]

    def test_two_way_sport_is_unchanged(self):
        now = datetime.now(timezone.utc)
        wps = stamp_source_reading({}, "kalshi", 0.62, now=now)
        wps = stamp_source_reading(wps, "betting", 0.60, now=now)
        event = SimpleNamespace(win_probability_sources=wps)

        home_mark, away_mark = blended_source_marks(
            event,
            [("betting", 0.60), ("kalshi", 0.62)],
            method="Bain Luck blend",
        )
        assert {s["key"]: s["probability"] for s in home_mark["sources"]} == {
            "betting": 0.60,
            "kalshi": 0.62,
        }
        assert {s["key"]: s["probability"] for s in away_mark["sources"]} == {
            "betting": 0.40,
            "kalshi": 0.38,
        }
