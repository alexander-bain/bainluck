"""Ruling 190 & Ruling 301: A (#11937, #12538): single game cards leave Discover
except when a team is followed by the reader (or an enabled stated-stake reason).

Specimens are the nine game cards in the first 60 Discover seats at
Sun Nov 15, 23:30 UTC (`fixtures/discover_games_2026_11_15.json`), trimmed to the
fields the rule reads:

* under Ruling 301: A (carrying out 190: C), none of the nine unfollowed games
  keep a Discover seat on public/signed-out Discover — including the four live
  15+ point swings (49ers, Lakers, Gonzaga, UConn) and any finished upset —
  because chance swings alone are never a reason;
* a followed team's game keeps its Discover seat and its normal card copy;
* stated-stake reasons (`stakes`, `team_move`) are guarded behind one switch
  (`DISCOVER_GAME_ALLOWED_REASONS`, default empty) so each can be turned back on
  one at a time after Fable's look.
"""

from __future__ import annotations

import copy
import inspect
import json
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

from app.utils import discover_game_reason as gr
from app.utils.personalization import PersonalizationContext

NOW = datetime(2026, 11, 15, 23, 30, tzinfo=timezone.utc)
CARDS = json.loads((Path(__file__).parent / "fixtures" / "discover_games_2026_11_15.json").read_text())


def _by(away):
    return copy.deepcopy(next(c for c in CARDS if c["data"]["away_team"].startswith(away)))


class TestTodaysNineGames:
    def test_all_nine_unfollowed_games_leave_discover_by_default(self):
        kept = gr.apply_game_reasons(copy.deepcopy(CARDS))
        assert kept == []

    def test_followed_team_keeps_its_game_and_copy(self):
        card = _by("San Francisco")
        followed_id = card["data"]["away_team_data"]["team_id"]
        original_headline = card.setdefault("headline", "San Francisco 49ers at Dallas Cowboys")
        original_reason = card.setdefault("reason", "Pre-game odds")

        kept = gr.apply_game_reasons([card], followed_team_ids={followed_id})
        assert len(kept) == 1
        assert kept[0]["headline"] == original_headline
        assert kept[0]["reason"] == original_reason
        assert kept[0]["data"]["discover_reason"]["kind"] == "followed_team"

    def test_a_live_swing_without_follow_is_dropped_even_with_all_switches(self, monkeypatch):
        monkeypatch.setenv(gr.ALLOWED_REASONS_ENV, "stakes,team_move,swing,fast_swing,upset")
        assert gr.game_reason(_by("San Francisco")) is None
        assert gr.game_reason(_by("Gonzaga")) is None
        assert gr.game_reason(_by("New York Knicks")) is None

    def test_regular_season_starting_soon_is_not_stakes(self, monkeypatch):
        monkeypatch.setenv(gr.ALLOWED_REASONS_ENV, "stakes")
        assert gr.game_reason(_by("Edmonton")) is None
        assert gr.game_reason(_by("Florida")) is None

    def test_a_finished_game_only_enters_via_team_move_when_enabled(self, monkeypatch):
        card = _by("Carolina")
        card[gr.SIGNALS_KEY] = {"team_moves": [{
            "team": "New Orleans Saints", "outcome": "Yes", "market_id": 9, "market": "Saints make the playoffs?",
            "before": 0.21, "now": 0.09,
        }]}
        assert gr.game_reason(copy.deepcopy(card)) is None
        monkeypatch.setenv(gr.ALLOWED_REASONS_ENV, "team_move")
        reason = gr.game_reason(card)
        assert reason["kind"] == "team_move"
        assert reason["line"] == "Saints make the playoffs? — Yes: 21% a day ago, 9% now"
        assert "because" not in reason["line"] and "after the" not in reason["line"]


class TestEachReasonAndSwitch:
    def test_stakes_before_the_game_is_gated_behind_allowed_reasons_switch(self, monkeypatch):
        card = _by("Edmonton")
        card["data"]["event_tags"] = ["importance:playoff"]
        assert gr.game_reason(card) is None
        monkeypatch.setenv(gr.ALLOWED_REASONS_ENV, "stakes")
        assert gr.game_reason(card) == {"kind": "stakes", "importance": "playoff", "line": "Playoff game"}

    def test_an_upset_is_never_a_stated_stake_reason(self, monkeypatch):
        card = _by("Indiana")  # home 71% pregame
        card["data"]["home_score"], card["data"]["away_score"] = 101, 110
        assert gr.game_reason(card) is None
        monkeypatch.setenv(gr.ALLOWED_REASONS_ENV, "upset,stakes,team_move")
        assert gr.game_reason(card) is None

    def test_fast_move_is_never_a_stated_stake_reason(self, monkeypatch):
        card = _by("New York Knicks")
        card[gr.SIGNALS_KEY] = {"fast_move": {"source": "espn", "before": 0.30, "after": 0.44, "delta": 0.14}}
        monkeypatch.setenv(gr.ALLOWED_REASONS_ENV, "fast_swing,swing")
        assert gr.game_reason(card) is None

    def test_futures_and_grouped_cards_are_untouched(self):
        items = [{"type": "futures", "data": {"id": 1}}, {"type": "bundle", "data": {"id": "b"}}]
        assert gr.apply_game_reasons(copy.deepcopy(items)) == items

    def test_the_signals_never_reach_the_payload(self):
        card = _by("San Francisco")
        followed_id = card["data"]["away_team_data"]["team_id"]
        card[gr.SIGNALS_KEY] = {"fast_move": {"source": "espn", "before": 0.6, "after": 0.9, "delta": 0.3}}
        (kept,) = gr.apply_game_reasons([card], followed_team_ids={followed_id})
        assert gr.SIGNALS_KEY not in kept

    def test_followed_team_ids_from_ctx_reads_standing_relations_only(self):
        ctx = PersonalizationContext(
            team_relations={
                10: {"follow"},
                20: {"local"},
                30: {"alma_mater"},
                40: {"rival"},
            }
        )
        assert gr.followed_team_ids_from_ctx(ctx) == frozenset({10, 20, 30})
        assert gr.followed_team_ids_from_ctx(PersonalizationContext()) == frozenset()


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

    def test_needs_game_signals_is_off_until_team_move_is_enabled(self, monkeypatch):
        monkeypatch.delenv(gr.ALLOWED_REASONS_ENV, raising=False)
        assert gr.needs_game_signals() is False
        monkeypatch.setenv(gr.ALLOWED_REASONS_ENV, "stakes")
        assert gr.needs_game_signals() is False
        monkeypatch.setenv(gr.ALLOWED_REASONS_ENV, "team_move")
        assert gr.needs_game_signals() is True
        monkeypatch.setenv(gr.SWITCH_ENV, "false")
        assert gr.needs_game_signals() is False


class TestWiring:
    def test_the_chain_replaces_the_old_admission_and_ends_sep10_final_seat(self):
        from app.routes import feed

        src = inspect.getsource(feed.apply_discover_display_chain)
        assert "apply_game_reasons(" in src
        block = src[src.index("if game_reason_enabled():"):]
        assert "followed_team_ids=followed_team_ids_from_ctx(ctx)" in block
        assert "kept_final_ids = set()" in block
        assert block.index("required_marquee_ids &= _surviving") < block.index("else:")
        assert block.index("_filter_discover_event_noise") > block.index("else:")

    def test_get_feed_reads_the_signals_before_the_chain(self):
        from app.routes import feed

        src = inspect.getsource(feed.get_feed)
        assert "needs_game_signals()" in src
        assert src.index("annotate_game_signals(db, feed_items, now)") < src.index(
            "apply_discover_display_chain(\n"
        )

    def test_the_switch_restores_the_old_rule(self, monkeypatch):
        monkeypatch.setenv(gr.SWITCH_ENV, "false")
        assert gr.game_reason_enabled() is False
        monkeypatch.setenv(gr.SWITCH_ENV, "true")
        assert gr.game_reason_enabled() is True


def test_finished_upset_without_follow_is_dropped():
    item = {"type": "event", "data": {
        "status": "completed", "home_team": "Vegas Golden Knights", "away_team": "Vancouver Canucks",
        "home_score": 3, "away_score": 6,
        "opening_odds": {"home_probability": 0.7826, "away_probability": 0.2174},
        "prematch_odds": {"home_probability": 0.785, "away_probability": 0.215,
                          "home_rendered_percent": 79, "away_rendered_percent": 21},
    }}
    assert gr.game_reason(item) is None
