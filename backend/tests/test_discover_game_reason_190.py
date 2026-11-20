"""Ruling 190 (#11937): a single game must earn its Discover seat.

Specimens are the nine game cards in the first 60 Discover seats at
Sun Nov 15, 23:30 UTC (`fixtures/discover_games_2026_11_15.json`), trimmed to the
fields the rule reads. Under the old rule all nine held seats. Under 190:

* kept — four live games whose chance moved 15+ points from pregame
  (49ers–Cowboys 64→89, Lakers–Suns 60→91, Gonzaga–Stanford 71→52,
  UConn–Louisville 16→71);
* out — a live game that moved 4 points (Knicks–Raptors), two finished games
  that were not upsets and whose teams' futures did not move, and two
  regular-season NHL games "starting soon".
"""

from __future__ import annotations

import copy
import inspect
import json
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.utils import discover_game_reason as gr

NOW = datetime(2026, 11, 15, 23, 30, tzinfo=timezone.utc)
CARDS = json.loads((Path(__file__).parent / "fixtures" / "discover_games_2026_11_15.json").read_text())


def _by(away):
    return copy.deepcopy(next(c for c in CARDS if c["data"]["away_team"].startswith(away)))


class TestTodaysNineGames:
    def test_four_kept_five_out(self):
        kept = gr.apply_game_reasons(copy.deepcopy(CARDS))
        assert sorted(c["data"]["away_team"] for c in kept) == [
            "Gonzaga Bulldogs", "Los Angeles Lakers", "San Francisco 49ers", "UConn Huskies",
        ]
        assert all(c["data"]["discover_reason"]["kind"] == "swing" for c in kept)

    def test_the_line_states_only_the_two_numbers_we_hold(self):
        card = _by("San Francisco")
        reason = gr.game_reason(card)
        assert reason["team"] == "San Francisco 49ers"
        assert reason["line"] == "San Francisco 49ers: 64% before the game, 89% now"

    def test_a_falling_home_side_names_the_side_that_rose(self):
        reason = gr.game_reason(_by("Gonzaga"))
        assert reason["line"] == "Gonzaga Bulldogs: 29% before the game, 48% now"

    def test_a_small_live_move_is_not_a_reason(self):
        assert gr.game_reason(_by("New York Knicks")) is None

    def test_regular_season_starting_soon_is_not_stakes(self):
        assert gr.game_reason(_by("Edmonton")) is None
        assert gr.game_reason(_by("Florida")) is None

    def test_a_finished_game_that_was_not_an_upset_needs_a_team_move(self):
        card = _by("Carolina")
        assert gr.game_reason(card) is None
        card[gr.SIGNALS_KEY] = {"team_moves": [{
            "team": "New Orleans Saints", "outcome": "Yes", "market_id": 9, "market": "Saints make the playoffs?",
            "before": 0.21, "now": 0.09,
        }]}
        reason = gr.game_reason(card)
        assert reason["kind"] == "team_move"
        assert reason["line"] == "Saints make the playoffs? — Yes: 21% a day ago, 9% now"
        assert "because" not in reason["line"] and "after the" not in reason["line"]


class TestEachReason:
    def test_stakes_before_the_game(self):
        card = _by("Edmonton")
        card["data"]["event_tags"] = ["importance:playoff"]
        assert gr.game_reason(card) == {"kind": "stakes", "importance": "playoff", "line": "Playoff game"}

    def test_an_upset(self):
        card = _by("Indiana")  # home 71% pregame
        card["data"]["home_score"], card["data"]["away_score"] = 101, 110
        reason = gr.game_reason(card)
        assert reason["kind"] == "upset" and reason["line"] == "Indiana Pacers won as a 29% underdog"

    def test_a_fast_move_counts_when_the_total_is_small(self):
        card = _by("New York Knicks")
        card[gr.SIGNALS_KEY] = {"fast_move": {"source": "espn", "before": 0.30, "after": 0.44, "delta": 0.14}}
        reason = gr.game_reason(card)
        assert reason["kind"] == "fast_swing"
        assert reason["line"] == "Toronto Raptors: 30% to 44% in the last 15 minutes"

    @pytest.mark.parametrize("delta,expected", [(0.149, None), (0.15, "swing")])
    def test_the_swing_bar_is_fifteen_points(self, delta, expected):
        card = _by("New York Knicks")
        card["data"]["hero_probability"] = card["data"]["opening_odds"]["home_probability"] + delta
        reason = gr.game_reason(card)
        assert (reason or {}).get("kind") == expected

    def test_futures_and_grouped_cards_are_untouched(self):
        items = [{"type": "futures", "data": {"id": 1}}, {"type": "bundle", "data": {"id": "b"}}]
        assert gr.apply_game_reasons(copy.deepcopy(items)) == items

    def test_the_signals_never_reach_the_payload(self):
        card = _by("San Francisco")
        card[gr.SIGNALS_KEY] = {"fast_move": {"source": "espn", "before": 0.6, "after": 0.9, "delta": 0.3}}
        (kept,) = gr.apply_game_reasons([card])
        assert gr.SIGNALS_KEY not in kept


class TestSignalsRead:
    async def test_one_read_each_and_moves_land_on_the_right_cards(self):
        live = _by("New York Knicks")
        done = _by("Carolina")
        saints = done["data"]["home_team_data"]["team_id"]
        replies = [
            [(live["data"]["id"], "espn", 0.30)],
            [(saints, "Yes", 0.09, -0.12, 77, "Saints make the playoffs?")],
        ]

        class DB:
            calls = 0

            async def execute(self, stmt):
                rows = replies[DB.calls]
                DB.calls += 1
                return SimpleNamespace(all=lambda: rows)

        live["data"]["win_probability_sources"]["espn"] = {"value": 0.44}
        await gr.annotate_game_signals(DB(), [live, done], NOW)
        assert DB.calls == 2
        assert round(live[gr.SIGNALS_KEY]["fast_move"]["delta"], 2) == 0.14
        (move,) = done[gr.SIGNALS_KEY]["team_moves"]
        assert move["team"] == "New Orleans Saints" and round(move["before"], 2) == 0.21


class TestWiring:
    def test_the_chain_replaces_the_old_admission_and_narrows_the_marquee_sets(self):
        from app.routes import feed

        src = inspect.getsource(feed.apply_discover_display_chain)
        assert "apply_game_reasons(items)" in src
        block = src[src.index("if game_reason_enabled():"):]
        assert block.index("required_marquee_ids &= _surviving") < block.index("else:")
        assert block.index("_filter_discover_event_noise") > block.index("else:")

    def test_get_feed_reads_the_signals_before_the_chain(self):
        from app.routes import feed

        src = inspect.getsource(feed.get_feed)
        assert src.index("annotate_game_signals(db, feed_items, now)") < src.index(
            "apply_discover_display_chain(\n"
        )

    def test_the_switch_restores_the_old_rule(self, monkeypatch):
        monkeypatch.setenv(gr.SWITCH_ENV, "false")
        assert gr.game_reason_enabled() is False
        monkeypatch.setenv(gr.SWITCH_ENV, "true")
        assert gr.game_reason_enabled() is True


def test_the_reason_line_prints_the_cards_own_pregame_number():
    """Monday Nov 16, seat 13: the card printed "Pregame 21%" (prematch_odds) and
    the reason line said "starting at 22%" (opening_odds 0.2174)."""
    item = {"type": "event", "data": {
        "status": "completed", "home_team": "Vegas Golden Knights", "away_team": "Vancouver Canucks",
        "home_score": 3, "away_score": 6,
        "opening_odds": {"home_probability": 0.7826, "away_probability": 0.2174},
        "prematch_odds": {"home_probability": 0.785, "away_probability": 0.215,
                          "home_rendered_percent": 79, "away_rendered_percent": 21},
    }}
    assert gr.game_reason(item)["line"] == "Vancouver Canucks won as a 21% underdog"
