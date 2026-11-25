"""Tests for #13645 follow-up: keep intraday up-or-down price cards off Discover and avoid vacuous even two-way tied copy."""

from __future__ import annotations

from app.routes.feed import (
    _is_even_two_way_board,
    _printed_leader_percent,
    _printed_outcome_name,
    _printed_runner_up_percent,
)
from app.utils import feed_reasons as fr
from app.utils.discover_rank_13645 import rank_13645_downranks
from app.utils.feed_market_quality import (
    apply_quality_score,
    classify_market_quality,
    is_daily_direction_filler,
    is_intraday_asset_direction,
)


class TestIntradayUpOrDownOffDiscover:
    def test_fifteen_minute_and_intraday_up_or_down_cards_suppressed_across_assets(self):
        intraday_titles = [
            "WTI Crude Oil Up or Down - November 25, 1:15AM-1:30AM ET",
            "Bitcoin Up or Down - November 25, 1:00AM-1:15AM ET",
            "Ethereum Up or Down - Nov 25, 2PM-3PM ET",
            "Gold Up or Down - 15m",
            "S&P 500 (SPX) Up or Down - 15 minutes",
            "Natural Gas Up or Down - November 20, 1:00PM-2:00PM ET",
        ]
        for title in intraday_titles:
            assert is_intraday_asset_direction(title) is True, title
            q = classify_market_quality(
                title,
                sport_category="economics",
                outcome_names=["Down", "Up"],
            )
            assert q.quality_class == "suppress", title
            assert "intraday_asset_direction" in q.reasons, title
            assert "asset_price_level" in q.reasons, title
            assert q.story_key == "story:daily_equity_direction", title
            assert apply_quality_score(95, q) == 0, title

        ranked = rank_13645_downranks(
            [
                {
                    "item_key": "futures:999001",
                    "served_position": 20,
                    "card": {
                        "type": "futures",
                        "data": {
                            "id": 999001,
                            "name": "WTI Crude Oil Up or Down - November 25, 1:15AM-1:30AM ET",
                            "llm_sport_category": "economics",
                            "top_outcomes": [
                                {"name": "Down", "probability": 0.5},
                                {"name": "Up", "probability": 0.5},
                            ],
                        },
                    },
                },
                {
                    "item_key": "futures:999002",
                    "served_position": 21,
                    "card": {
                        "type": "futures",
                        "data": {
                            "id": 999002,
                            "name": "Will OPEC cut oil production in 2026?",
                            "llm_sport_category": "economics",
                            "top_outcomes": [
                                {"name": "Yes", "probability": 0.35},
                                {"name": "No", "probability": 0.65},
                            ],
                        },
                    },
                },
            ]
        )
        assert [c["item_key"] for c in ranked] == ["futures:999002", "futures:999001"]

    def test_untickered_dated_asset_up_or_down_classified_as_daily_filler(self):
        for title in (
            "WTI Crude Oil Up or Down on November 25?",
            "Gold Up or Down today",
        ):
            assert is_daily_direction_filler(title) is True, title
            q = classify_market_quality(title, sport_category="economics")
            assert q.quality_class == "low_quality", title
            assert "daily_equity_direction" in q.reasons, title

    def test_non_intraday_and_political_questions_stay_untouched(self):
        # Voter turnout already hits margin_turnout_excluded, never intraday_asset_direction/daily_equity_direction
        turnout = "Berlin State Election: Turnout Up or Down?"
        assert is_intraday_asset_direction(turnout) is False
        assert is_daily_direction_filler(turnout) is False
        q_turnout = classify_market_quality(turnout, sport_category="politics")
        assert "intraday_asset_direction" not in q_turnout.reasons
        assert "daily_equity_direction" not in q_turnout.reasons

        safe_titles = (
            ("Fed decision: rates up or down, Dec 10, 2:00 PM ET", "economics"),
            ("ECB decision: rates up or down, Dec 10, 2:00 PM ET", "economics"),
            ("Canada's population Up or Down this year?", "world"),
            ("Charizard ex Up or Down: July", "culture"),
            ("Will the Fed cut interest rates at its 2:00 PM meeting?", "economics"),
            ("Will OPEC cut oil production in 2026?", "economics"),
        )
        for title, cat in safe_titles:
            assert is_intraday_asset_direction(title) is False, title
            assert is_daily_direction_filler(title) is False, title
            q = classify_market_quality(title, sport_category=cat)
            assert q.quality_class != "suppress", title
            assert "intraday_asset_direction" not in q.reasons, title

        # Non-intraday oil threshold stays asset_price_level, never intraday_asset_direction
        threshold = "Will WTI Crude Oil settle above $75 by December 31?"
        assert is_intraday_asset_direction(threshold) is False
        q_thresh = classify_market_quality(threshold, sport_category="economics")
        assert "asset_price_level" in q_thresh.reasons
        assert "intraday_asset_direction" not in q_thresh.reasons


class TestEvenTwoWayTiesNeverPrintBothSides:
    def test_down_up_50_50_never_prints_down_and_up(self):
        market_name = "WTI Crude Oil Up or Down - November 25, 1:15AM-1:30AM ET"
        top_outcomes_data = [
            {"name": "Down", "probability": 0.50, "rendered_percent": 50},
            {"name": "Up", "probability": 0.50, "rendered_percent": 50},
        ]
        leader = _printed_outcome_name("Down", {}, market_name, top_outcomes_data)
        assert leader == "Down"

        l_pct = _printed_leader_percent(top_outcomes_data)
        r_pct = _printed_runner_up_percent(top_outcomes_data)
        even = _is_even_two_way_board(top_outcomes_data, l_pct, r_pct, True)
        assert even is True

        for reason_code in (
            ["featured_market"],
            ["resolving_soon_1d"],
            ["resolving_soon_7d"],
            ["resolving_soon_30d"],
        ):
            headline = fr.generate_futures_headline(
                highlight_reasons=reason_code,
                leader_name=leader,
                leader_probability=0.50,
                rendered_leader_percent=l_pct,
                rendered_runner_up_percent=r_pct,
                card_field_is_a_race=True,
                market_name=market_name,
                even_two_way_tie=even,
            )
            reason = fr.generate_futures_reason(
                market_name,
                reason_code,
                leader_name=leader,
                leader_probability=0.50,
                rendered_leader_percent=l_pct,
                rendered_runner_up_percent=r_pct,
                card_field_is_a_race=True,
                even_two_way_tie=even,
            )
            context = fr.generate_futures_context_summary(
                headline=headline,
                highlight_reasons=reason_code,
                market_name=market_name,
                leader_name=leader,
                leader_probability=0.50,
                rendered_leader_percent=l_pct,
                rendered_runner_up_percent=r_pct,
                card_field_is_a_race=True,
                even_two_way_tie=even,
            )
            for text in (headline, reason, context):
                assert "Down and Up" not in text
                assert "Up and Down" not in text
                assert "at 50%" not in text
                assert "(50%)" not in text

        # Direct callers passing tied_leader_names=["Down", "Up"] are also guarded
        assert (
            fr.generate_futures_headline(
                highlight_reasons=["featured_market"],
                leader_name="Down",
                leader_probability=0.50,
                rendered_leader_percent=50,
                rendered_runner_up_percent=50,
                tied_leader_names=["Down", "Up"],
                market_name=market_name,
            )
            == ""
        )
        assert (
            fr.generate_futures_headline(
                highlight_reasons=["featured_market"],
                leader_name="Over",
                leader_probability=0.50,
                rendered_leader_percent=50,
                rendered_runner_up_percent=50,
                tied_leader_names=["Over", "Under"],
                market_name="Total points Over or Under 48.5?",
            )
            == ""
        )

    def test_even_two_way_board_predicate_bounds(self):
        # Opposing generic binary label pairs at 50/50 are suppressed
        for pair in (["Down", "Up"], ["Yes", "No"], ["Over", "Under"]):
            assert _is_even_two_way_board(
                [{"name": pair[0]}, {"name": pair[1]}], 50, 50, True
            )

        # Named two-way 50/50 dead heats keep today's tied-leader copy intact
        named = [{"name": "Alice"}, {"name": "Bob"}]
        assert not _is_even_two_way_board(named, 50, 50, True)
        assert not _is_even_two_way_board(
            [{"name": "Team A"}, {"name": "Team B"}], 50, 50, True
        )
        assert not _is_even_two_way_board(
            [{"name": "Alice"}, {"name": "Bob"}], 51, 49, True
        )
        assert not _is_even_two_way_board(
            [{"name": "Team A"}, {"name": "Team B"}, {"name": "Team C"}], 34, 34, True
        )

        # _printed_outcome_name and generate_futures_headline preserve named 50/50 ties
        named_board = [
            {"name": "Alice", "probability": 0.50, "rendered_percent": 50},
            {"name": "Bob", "probability": 0.50, "rendered_percent": 50},
        ]
        assert (
            _printed_outcome_name(
                "Alice", {}, "Next Chair of the Board?", named_board
            )
            == "Alice and Bob"
        )
        named_headline = fr.generate_futures_headline(
            highlight_reasons=["featured_market"],
            leader_name="Alice and Bob",
            leader_probability=0.50,
            rendered_leader_percent=50,
            rendered_runner_up_percent=50,
            tied_leader_names=["Alice", "Bob"],
            card_field_is_a_race=True,
            market_name="Next Chair of the Board?",
            even_two_way_tie=False,
        )
        assert "Alice and Bob" in named_headline
        assert "50%" in named_headline
