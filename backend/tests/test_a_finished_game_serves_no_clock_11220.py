"""#11220: a completed game serves no game clock.

Production, Nov 10 (Fable): ``GET /api/events/15344868`` (Lakers at Hawks,
completed) served ``espn.game_clock: "12:00"`` beside ``espn.period: "Final"``,
so build 5704 of the iPhone app titled the page "Final 12:00". ESPN resets the
clock to the period length when a game ends; it isn't time left in anything.
#12567 taught the app to blank a run-out clock ("0.0", "0:00"); a reset one
still printed. Fixing it on the server fixes every app version in readers'
hands and the web, with no app build.

What must hold: a finished game (status completed or closed, or a period that
says Final) serves its period and no clock. A live game is untouched.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.utils.game_state import normalize_live_game_state

NBA = "basketball_nba"


class TestTheSharedNormaliser:
    def test_the_production_payload_serves_final_and_no_clock(self):
        assert normalize_live_game_state(NBA, "Final", "12:00", status="completed") == ("Final", None)

    def test_a_final_period_drops_the_clock_even_without_a_status(self):
        assert normalize_live_game_state(NBA, "Final", "12:00") == ("Final", None)

    @pytest.mark.parametrize("period", ["Final/OT", "Final - 2OT", "FT", "Full Time", "final"])
    def test_every_final_spelling_drops_the_clock(self, period):
        assert normalize_live_game_state("soccer_epl", period, "90:00")[1] is None

    @pytest.mark.parametrize("status", ["completed", "closed", "Completed"])
    def test_a_completed_status_drops_the_clock_whatever_the_period_says(self, status):
        assert normalize_live_game_state(NBA, "4th", "12:00", status=status) == ("4th", None)

    def test_a_live_game_keeps_its_clock(self):
        assert normalize_live_game_state(NBA, "3rd", "5:21", status="live") == ("3rd", "5:21")
        assert normalize_live_game_state(NBA, "Halftime", "0:00") == ("Halftime", "0:00")

    def test_a_scheduled_game_is_untouched(self):
        assert normalize_live_game_state(NBA, None, None, status="scheduled") == (None, None)


class TestTheServingSites:
    def test_the_search_and_price_card_state_serves_no_clock_for_a_finished_game(self):
        from app.routes.feed_prices import _live_state

        event = SimpleNamespace(sport=SimpleNamespace(key=NBA), period="Final", game_clock="12:00",
                                status="completed")
        assert _live_state(event) == {"period": "Final", "game_clock": None}

    @pytest.mark.parametrize("path", ["app/routes/events.py", "app/routes/league_futures.py",
                                      "app/routes/feed_prices.py"])
    def test_every_site_passes_the_event_status(self, path):
        import pathlib
        import re

        src = (pathlib.Path(__file__).resolve().parents[1] / path).read_text()
        calls = re.findall(r"normalize_live_game_state\((.*?)\)\n", src, flags=re.S)
        assert calls and all("status=" in c for c in calls), path
