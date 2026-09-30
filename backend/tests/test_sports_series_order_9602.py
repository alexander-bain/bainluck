"""The sooner game of a series takes the earlier Sports slot (#9602).

`sports_series_game_order_9602.json` is the pool production served at
2026-09-29 11:12Z: Phillies @ Braves NLWC Game 2 (tomorrow) at slot 3 and
Game 1 (today, 18:00Z — 6.8h ahead, so outside #9489's imminent window) at slot
15; White Sox @ Astros Game 1 at slot 0 and Game 2 at slot 11. The corpus arm
replays it through the pass and through the whole display chain; the synthetic
arms cover the refusals.
"""

from __future__ import annotations

import ast
import inspect
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from app.routes.feed import PersonalizationContext, apply_discover_display_chain
from app.utils.sports_imminent_marquee import (
    UPCOMING_STATUSES,
    lead_upcoming_with_imminent_marquee_games,
)
from app.utils.sports_series_order import order_series_games_by_kickoff, series_key
from app.utils.tonights_games import MARQUEE_PIN_KEY

CORPUS = Path(__file__).parent / "fixtures" / "sports_series_game_order_9602.json"
NOW = datetime(2026, 9, 29, 11, 12, 8, tzinfo=timezone.utc)
PHI_G1, PHI_G2 = 15320289, 15320701
CHW_G1, CHW_G2 = 15320300, 15320702

SPORTS = {
    "event_pct": 0.6,
    "include_events": True,
    "my_teams_only": False,
    "sports_mode": True,
}
DISCOVER = {
    "event_pct": 0.15,
    "include_events": True,
    "my_teams_only": False,
    "sports_mode": False,
}
MY_STUFF_VIA_SPORTS_MODE = {
    "event_pct": 0.6,
    "include_events": True,
    "my_teams_only": True,
    "sports_mode": True,
}


def _corpus() -> list[dict]:
    return json.loads(CORPUS.read_text())["items"]


def _upcoming_ids(items: list[dict], n: int = 20) -> list[int]:
    """The client's "Upcoming" section, in order — `groupFeedIntoSections`
    partitions the served page and never re-sorts."""
    return [
        it["data"]["id"]
        for it in items[:n]
        if it.get("type") == "event"
        and ((it.get("data") or {}).get("status") or "").lower() in UPCOMING_STATUSES
    ]


def _index(items: list[dict], event_id: int) -> int:
    return next(
        i
        for i, it in enumerate(items)
        if it.get("type") == "event" and it["data"]["id"] == event_id
    )


def _game(
    away,
    home="Home",
    *,
    hours,
    score=50,
    status="scheduled",
    sport="baseball_mlb",
    pin=False,
):
    item = {
        "type": "event",
        "score": score,
        "data": {
            "id": abs(hash((away, home, hours))) % 10**7,
            "status": status,
            "sport": sport,
            "away_team": away,
            "home_team": home,
            "commence_time": (NOW + timedelta(hours=hours)).isoformat(),
            "event_tags": ["tier:1"],
        },
    }
    if pin:
        item[MARQUEE_PIN_KEY] = True
    return item


def _futures(score=90):
    return {"type": "futures", "score": score, "data": {"status": "open"}}


def _labels(items):
    return [
        f"{it['data']['away_team']}@{it['data']['home_team']}+{it['data']['commence_time'][8:13]}"
        for it in items
        if it["type"] == "event"
    ]


class TestTheProductionCorpus:
    def test_RED_ARM_the_served_page_prints_game_2_above_game_1(self):
        """If this goes green on its own the corpus is stale, not the defect fixed."""
        served = _corpus()
        assert _index(served, PHI_G2) == 3
        assert _index(served, PHI_G1) == 15
        assert _index(served, CHW_G1) < _index(served, CHW_G2)

    def test_RED_ARM_the_imminent_pass_alone_does_not_fix_it(self):
        """Game 1 is 6.8h out — #9489's window does not reach it yet."""
        out, meta = lead_upcoming_with_imminent_marquee_games(_corpus(), now=NOW)
        assert _index(out, PHI_G2) < _index(out, PHI_G1)

    def test_the_pass_puts_game_1_in_game_2s_slot(self):
        served = _corpus()
        out, meta = order_series_games_by_kickoff(served)
        assert _index(out, PHI_G1) == 3
        assert _index(out, PHI_G2) == 15
        # CHW@HOU was already in order and stays exactly where it was.
        assert _index(out, CHW_G1) == 0
        assert _index(out, CHW_G2) == 11
        assert meta == {"series": 2, "moved": 2}

    def test_only_the_two_series_slots_change_occupant(self):
        served = _corpus()
        out, _ = order_series_games_by_kickoff(served)
        assert len(out) == len(served)
        changed = [i for i, (a, b) in enumerate(zip(served, out)) if a is not b]
        assert changed == [3, 15]
        # The two games traded slots whole — cards, scores and all.
        assert out[3] is served[15] and out[15] is served[3]
        assert (out[3]["score"], out[15]["score"]) == (45, 65)

    def test_the_whole_sports_chain_prints_game_1_first(self):
        """The served-order claim, proven where the reader gets it: the full
        display chain, not the bare pass."""
        out, meta = apply_discover_display_chain(
            _corpus(), limit=20, ctx=PersonalizationContext(), now=NOW, **SPORTS
        )
        upcoming = _upcoming_ids(out, n=len(out))
        assert upcoming.index(PHI_G1) < upcoming.index(PHI_G2), upcoming
        assert upcoming.index(CHW_G1) < upcoming.index(CHW_G2), upcoming
        assert PHI_G1 in _upcoming_ids(out), "Game 1 reaches the first page"
        assert meta["series_kickoff_order"]["series"] == 2


class TestTheRefusals:
    def test_different_opponents_are_not_a_series(self):
        items = [
            _game("Phillies", "Braves", hours=30, score=80),
            _game("Mets", "Braves", hours=6),
        ]
        out, meta = order_series_games_by_kickoff(items)
        assert out is items
        assert meta == {"series": 0, "moved": 0}

    def test_home_and_away_swapped_is_the_same_series(self):
        items = [
            _game("Braves", "Phillies", hours=30),
            _game("Phillies", "Braves", hours=6),
        ]
        out, _ = order_series_games_by_kickoff(items)
        assert _labels(out) == ["Phillies@Braves+29T17", "Braves@Phillies+30T17"]

    def test_the_same_names_in_another_sport_are_not_a_series(self):
        items = [
            _game("Panthers", "Kings", hours=30, sport="icehockey_nhl"),
            _game("Panthers", "Kings", hours=6, sport="americanfootball_nfl"),
        ]
        out, _ = order_series_games_by_kickoff(items)
        assert out is items

    def test_live_and_finished_games_are_never_moved(self):
        items = [
            _game("Phillies", "Braves", hours=30),
            _game("Phillies", "Braves", hours=-1, status="live", score=95),
            _game("Phillies", "Braves", hours=-26, status="completed", score=98),
        ]
        out, meta = order_series_games_by_kickoff(items)
        assert out is items
        assert meta["series"] == 0

    def test_a_marquee_pin_keeps_its_exact_slot(self):
        items = [
            _game("Phillies", "Braves", hours=30, pin=True),
            _game("Phillies", "Braves", hours=6),
        ]
        out, _ = order_series_games_by_kickoff(items)
        assert out is items

    def test_a_three_game_series_is_sorted_across_its_slots_only(self):
        items = [
            _game("Phillies", "Braves", hours=54),
            _futures(),
            _game("Phillies", "Braves", hours=30),
            _game("Mets", "Nationals", hours=40),
            _game("Phillies", "Braves", hours=6),
        ]
        out, meta = order_series_games_by_kickoff(items)
        assert _labels(out) == [
            "Phillies@Braves+29T17",
            "Phillies@Braves+30T17",
            "Mets@Nationals+01T03",
            "Phillies@Braves+01T17",
        ]
        assert out[1]["type"] == "futures"
        assert out[3] is items[3]
        assert meta == {"series": 1, "moved": 2}

    def test_a_kickoff_tie_keeps_its_served_order(self):
        a = _game("Phillies", "Braves", hours=6, score=60)
        b = _game("Phillies", "Braves", hours=6, score=40)
        out, meta = order_series_games_by_kickoff([a, b])
        assert out[0] is a and out[1] is b
        assert meta == {"series": 1, "moved": 0}

    def test_an_unparseable_kickoff_is_left_alone(self):
        bad = _game("Phillies", "Braves", hours=30)
        bad["data"]["commence_time"] = "not a time"
        items = [bad, _game("Phillies", "Braves", hours=6)]
        out, meta = order_series_games_by_kickoff(items)
        assert out is items
        assert meta["series"] == 0

    def test_an_unkeyable_game_has_no_series(self):
        assert (
            series_key(
                {"data": {"sport": "baseball_mlb", "home_team": "X", "away_team": ""}}
            )
            is None
        )
        assert (
            series_key({"data": {"sport": "", "home_team": "X", "away_team": "Y"}})
            is None
        )

    def test_a_malformed_item_returns_the_page_unchanged(self):
        class Boom(dict):
            def get(self, *a, **k):
                raise RuntimeError("boom")

        items = [_game("Phillies", "Braves", hours=30), Boom(type="event")]
        out, meta = order_series_games_by_kickoff(items)
        assert out is items
        assert meta["moved"] == 0


class TestWiring:
    def test_the_gate_reads_the_explicit_signal_not_the_discover_negation(self):
        src = inspect.getsource(apply_discover_display_chain)
        call = src.index("order_series_games_by_kickoff(")
        gate = src.rindex("if ", 0, call)
        gate_line = src[gate : src.index("\n", gate)]
        assert "sports_mode" in gate_line, gate_line
        assert "not my_teams_only" in gate_line, gate_line
        assert "discover_mode" not in gate_line, gate_line

    def test_it_runs_after_the_futures_cap_and_before_the_imminent_pass(self):
        tree = ast.parse(inspect.getsource(apply_discover_display_chain))
        watched = (
            "cap_futures_on_games_led_first_page",
            "order_series_games_by_kickoff",
            "lead_upcoming_with_imminent_marquee_games",
            "hoist_live_events_into_first_page",
        )
        calls = [
            n.func.id
            for n in ast.walk(tree)
            if isinstance(n, ast.Call)
            and isinstance(n.func, ast.Name)
            and n.func.id in watched
        ]
        assert calls == list(watched), f"call order changed: {calls}"

    def test_the_pass_is_actually_called_and_its_result_is_kept(self):
        tree = ast.parse(inspect.getsource(apply_discover_display_chain))
        bound = [
            n
            for n in ast.walk(tree)
            if isinstance(n, ast.Assign)
            and isinstance(n.value, ast.Call)
            and isinstance(n.value.func, ast.Name)
            and n.value.func.id == "order_series_games_by_kickoff"
        ]
        assert len(bound) == 1, "expected exactly one call site"
        assert [t.id for t in bound[0].targets[0].elts] == [
            "items",
            "series_order_meta",
        ]


class TestTheOtherSurfacesAreUnchanged:
    @staticmethod
    def _pool():
        return [
            _game("Phillies", "Braves", hours=30, score=80),
            _game("Mets", "Nationals", hours=8, score=70),
            _game("Phillies", "Braves", hours=7, score=40),
        ]

    def test_CONTROL_discover_never_invokes_the_pass(self):
        _out, meta = apply_discover_display_chain(
            self._pool(), limit=20, ctx=PersonalizationContext(), now=NOW, **DISCOVER
        )
        assert meta["series_kickoff_order"] is None

    def test_CONTROL_my_stuff_via_sports_mode_never_invokes_the_pass(self):
        _out, meta = apply_discover_display_chain(
            self._pool(),
            limit=20,
            ctx=PersonalizationContext(),
            now=NOW,
            **MY_STUFF_VIA_SPORTS_MODE,
        )
        assert meta["series_kickoff_order"] is None

    def test_sports_mode_does_invoke_the_pass(self):
        out, meta = apply_discover_display_chain(
            self._pool(), limit=20, ctx=PersonalizationContext(), now=NOW, **SPORTS
        )
        assert meta["series_kickoff_order"] == {"series": 1, "moved": 2}
        assert _labels(out)[0] == "Phillies@Braves+29T18"
