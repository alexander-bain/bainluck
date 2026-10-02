"""Tonight's marquee game leads the Sports tab's Upcoming list (#9489).

`sports_upcoming_imminent_mnf_9489.json` is the pool production served at
2026-09-28 23:10Z, an hour before Monday Night Football: Eagles @ Bears at slot
6, fifth among upcoming games, below four that start the next day. The corpus
arm replays it through the pass and through the whole display chain; the
synthetic arms cover both directions of the done-when and the refusals.
"""

from __future__ import annotations

import ast
import inspect
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from app.routes import feed as feed_module
from app.routes.feed import PersonalizationContext, apply_discover_display_chain
from app.utils.sports_imminent_marquee import (
    IMMINENT_KICKOFF_HOURS,
    UPCOMING_STATUSES,
    lead_upcoming_with_imminent_marquee_games,
)
from app.utils.tonights_games import MARQUEE_PIN_KEY

CORPUS = Path(__file__).parent / "fixtures" / "sports_upcoming_imminent_mnf_9489.json"
NOW = datetime(2026, 9, 28, 23, 10, 0, tzinfo=timezone.utc)
MNF = "Philadelphia Eagles @ Chicago Bears"

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


def _label(it: dict) -> str:
    d = it.get("data") or {}
    return f"{d.get('away_team')} @ {d.get('home_team')}"


def _upcoming(items: list[dict], n: int = 20) -> list[str]:
    """What the client's "Upcoming" section prints, in order — the frontend
    partitions the served page and never re-sorts (`groupFeedIntoSections`)."""
    return [
        _label(it)
        for it in items[:n]
        if it.get("type") == "event"
        and ((it.get("data") or {}).get("status") or "").lower() in UPCOMING_STATUSES
    ]


def _game(
    name, *, hours, tier=1, score=50, status="scheduled", pin=False, importance=None
):
    tags = [f"tier:{tier}"]
    if importance:
        tags.append(f"importance:{importance}")
    item = {
        "type": "event",
        "score": score,
        "data": {
            "id": abs(hash(name)) % 10**7,
            "status": status,
            "away_team": name,
            "home_team": "Home",
            "commence_time": (NOW + timedelta(hours=hours)).isoformat(),
            "event_tags": tags,
        },
    }
    if pin:
        item[MARQUEE_PIN_KEY] = True
    return item


def _futures(score=90):
    return {"type": "futures", "score": score, "data": {"status": "open"}}


def _names(items):
    return [
        (it.get("data") or {}).get("away_team") for it in items if it["type"] == "event"
    ]


class TestTheProductionCorpus:
    def test_RED_ARM_the_served_page_prints_mnf_fifth(self):
        """If this goes green on its own the corpus is stale, not the defect fixed."""
        upcoming = _upcoming(_corpus())
        assert upcoming.index(MNF) == 4, upcoming

    def test_the_pass_puts_mnf_first_in_upcoming(self):
        out, meta = lead_upcoming_with_imminent_marquee_games(_corpus(), now=NOW)
        upcoming = _upcoming(out)
        assert upcoming[0] == MNF, upcoming
        # Everyone else keeps their served order behind it.
        before = [u for u in _upcoming(_corpus()) if u != MNF]
        assert upcoming[1:] == before
        assert meta == {"imminent": 1, "moved": 5, "hours": IMMINENT_KICKOFF_HOURS}

    def test_only_upcoming_slots_change_occupant(self):
        served = _corpus()
        out, _ = lead_upcoming_with_imminent_marquee_games(served, now=NOW)
        assert len(out) == len(served)
        assert sorted(map(id, out)) == sorted(map(id, served))
        for a, b in zip(served, out):
            if a is not b:
                assert _upcoming([a]) and _upcoming([b]), (a.get("type"), b.get("type"))
        # No score is touched.
        assert [it["score"] for it in out if it["type"] != "event"] == [
            it["score"] for it in served if it["type"] != "event"
        ]

    def test_the_whole_sports_chain_leads_upcoming_with_mnf(self):
        """The served-order claim, proven where the reader gets it: the full
        display chain, not the bare pass."""
        out, meta = apply_discover_display_chain(
            _corpus(), limit=20, ctx=PersonalizationContext(), now=NOW, **SPORTS
        )
        assert _upcoming(out)[0] == MNF, _upcoming(out)
        assert meta["imminent_marquee_upcoming"]["imminent"] == 1


class TestBothDirections:
    def test_an_imminent_marquee_game_outranks_a_next_day_game(self):
        items = [
            _game("NextDayPlayoff", hours=26, score=87),
            _futures(),
            _game("TonightNFL", hours=1, score=48),
        ]
        out, _ = lead_upcoming_with_imminent_marquee_games(items, now=NOW)
        assert _names(out) == ["TonightNFL", "NextDayPlayoff"]
        assert out[1]["type"] == "futures", "a non-upcoming card keeps its slot"

    def test_a_next_day_playoff_game_still_outranks_an_imminent_minor_game(self):
        items = [
            _game("NextDayPlayoff", hours=26, score=87),
            _game("TonightChallenger", hours=1, tier=3, score=48),
            _game("TonightMLS", hours=1, tier=2, score=46),
        ]
        out, meta = lead_upcoming_with_imminent_marquee_games(items, now=NOW)
        assert out == items
        assert meta["imminent"] == 0


class TestTheRefusals:
    def test_a_game_past_its_start_time_is_not_imminent(self):
        """A still-`scheduled` row whose start is behind us has a lagging status."""
        items = [_game("Later", hours=26), _game("Lagging", hours=-0.2)]
        out, _ = lead_upcoming_with_imminent_marquee_games(items, now=NOW)
        assert out == items

    def test_a_game_beyond_the_window_is_not_imminent(self):
        items = [
            _game("Later", hours=26),
            _game("SevenHours", hours=IMMINENT_KICKOFF_HOURS + 1),
        ]
        out, _ = lead_upcoming_with_imminent_marquee_games(items, now=NOW)
        assert out == items

    def test_the_window_edge_is_inclusive(self):
        items = [_game("Later", hours=26), _game("Edge", hours=IMMINENT_KICKOFF_HOURS)]
        out, _ = lead_upcoming_with_imminent_marquee_games(items, now=NOW)
        assert _names(out) == ["Edge", "Later"]

    def test_live_and_finished_games_are_never_moved(self):
        items = [
            _game("Later", hours=26),
            _game("Live", hours=-1, status="live", score=95),
            _game("Final", hours=-4, status="completed", score=98),
            _game("Tonight", hours=2),
        ]
        out, _ = lead_upcoming_with_imminent_marquee_games(items, now=NOW)
        assert _names(out) == ["Tonight", "Live", "Final", "Later"]

    def test_a_marquee_pin_keeps_its_exact_slot(self):
        items = [
            _game("Pinned", hours=30, pin=True),
            _game("Later", hours=26),
            _game("Tonight", hours=2),
        ]
        out, _ = lead_upcoming_with_imminent_marquee_games(items, now=NOW)
        assert _names(out) == ["Pinned", "Tonight", "Later"]

    def test_several_imminent_games_keep_their_served_order(self):
        items = [
            _game("Later", hours=26, score=90),
            _game("EarlyKick", hours=1, score=40),
            _game("Sunday4pm", hours=4, score=60),
        ]
        out, _ = lead_upcoming_with_imminent_marquee_games(items, now=NOW)
        assert _names(out) == ["EarlyKick", "Sunday4pm", "Later"]

    def test_a_tail_game_trades_places_and_the_game_count_holds(self):
        """An imminent game beyond the first page takes an upcoming slot inside
        it; the later game it displaces takes the slot it vacated."""
        items = (
            [_game("Later", hours=26)]
            + [_futures() for _ in range(19)]
            + [_game("Tonight", hours=1)]
        )
        out, _ = lead_upcoming_with_imminent_marquee_games(items, now=NOW)
        assert _names(out[:20]) == ["Tonight"]
        assert _names(out[20:]) == ["Later"]

    def test_nothing_to_do_reports_zero_not_none(self):
        items = [_game("Later", hours=26)]
        out, meta = lead_upcoming_with_imminent_marquee_games(items, now=NOW)
        assert out is items
        assert meta == {"imminent": 0, "moved": 0, "hours": IMMINENT_KICKOFF_HOURS}

    def test_a_malformed_item_returns_the_page_unchanged(self):
        class Boom(dict):
            def get(self, *a, **k):
                raise RuntimeError("boom")

        items = [_game("Later", hours=26), Boom(type="event")]
        out, meta = lead_upcoming_with_imminent_marquee_games(items, now=NOW)
        assert out is items
        assert meta["moved"] == 0


# #10222 — the first twenty slots of `GET /api/feed?mode=sports&limit=40`, read
# on production 2026-10-02 22:06Z (2h54m before tip-off), reduced to the fields
# the pass reads. Dallas Wings @ Golden State Valkyries (`15322555`, WNBA
# playoffs, tier:2) sits at slot 16, below tomorrow's MLB/WNBA playoff games and
# a regular-season NHL game (slot 17 Devils @ Islanders is tomorrow too).
WNBA_NOW = datetime(2026, 10, 2, 22, 6, 0, tzinfo=timezone.utc)
WINGS = "Dallas Wings @ Golden State Valkyries"
_WNBA_SERVED = [
    ("event", 15168046, "scheduled", "2026-10-02T22:30:00+00:00", 88, ["importance:regular_season", "tier:1"], "New York Rangers", "Detroit Red Wings"),
    ("event", 15322075, "completed", "2026-10-02T18:01:00+00:00", 93, ["tier:3"], "KK Partizan NIS", "FC Bayern München"),
    ("futures", 86832, "open", None, 95, [], None, None),
    ("event", 15322853, "scheduled", "2026-10-02T23:00:00+00:00", 83, ["importance:regular_season", "tier:1"], "Washington Capitals", "Carolina Hurricanes"),
    ("event", 15176366, "scheduled", "2026-10-03T00:00:00+00:00", 73, ["importance:regular_season", "tier:1"], "Boston Bruins", "Winnipeg Jets"),
    ("tournament", None, None, None, 100, [], None, None),
    ("event", 15168047, "scheduled", "2026-10-03T01:00:00+00:00", 48, ["importance:regular_season", "tier:1"], "St Louis Blues", "Dallas Stars"),
    ("event", 15318028, "scheduled", "2026-10-02T23:00:00+00:00", 98, ["importance:regular_season", "tier:2"], "Pittsburgh Panthers", "Virginia Tech Hokies"),
    ("tournament", None, None, None, 100, [], None, None),
    ("event", 15322539, "scheduled", "2026-10-03T22:30:00+00:00", 89, ["importance:playoff", "tier:1"], "New York Yankees", "Tampa Bay Rays"),
    ("event", 15322462, "scheduled", "2026-10-03T17:00:00+00:00", 72, ["importance:playoff", "tier:1"], "Chicago White Sox", "Cleveland Guardians"),
    ("tournament", None, None, None, 98, [], None, None),
    ("event", 15318029, "scheduled", "2026-10-03T00:00:00+00:00", 68, ["importance:regular_season", "tier:2"], "Penn State Nittany Lions", "Northwestern Wildcats"),
    ("event", 15323167, "live", "2026-10-02T20:00:00+00:00", 63, ["importance:regular_season", "tier:3"], "Harvey Smith", "Joshua John"),
    ("futures", 114167, "open", None, 93, [], None, None),
    ("event", 15322540, "scheduled", "2026-10-04T01:00:00+00:00", 65, ["importance:playoff", "tier:2"], "New York Liberty", "Atlanta Dream"),
    ("event", 15322555, "scheduled", "2026-10-03T01:00:00+00:00", 63, ["importance:playoff", "tier:2"], "Dallas Wings", "Golden State Valkyries"),
    ("event", 15169780, "scheduled", "2026-10-03T23:30:00+00:00", 60, ["tier:1"], "New Jersey Devils", "New York Islanders"),
    ("event", 15319320, "completed", "2026-10-02T18:01:00+00:00", 56, ["tier:3"], "Valencia Basket", "ASVEL Lyon Villeurbanne"),
    ("event", 15169778, "scheduled", "2026-10-03T23:00:00+00:00", 60, ["importance:regular_season", "tier:1"], "Montreal Canadiens", "Pittsburgh Penguins"),
]


def _wnba_served() -> list[dict]:
    out = []
    for kind, eid, status, commence, score, tags, away, home in _WNBA_SERVED:
        data = {"id": eid, "status": status}
        if kind == "event":
            data.update(
                commence_time=commence, event_tags=tags, away_team=away, home_team=home
            )
        out.append({"type": kind, "score": score, "data": data})
    return out


class TestTonightsTier2PlayoffGame_10222:
    def test_RED_ARM_the_served_page_prints_the_wings_tenth(self):
        """If this goes green on its own the specimen is stale, not the defect fixed."""
        upcoming = _upcoming(_wnba_served())
        assert upcoming.index(WINGS) == 9, upcoming

    def test_the_pass_seats_the_wings_with_tonights_marquee_games(self):
        served = _wnba_served()
        out, meta = lead_upcoming_with_imminent_marquee_games(served, now=WNBA_NOW)
        upcoming = _upcoming(out)
        # Tonight's four tier:1 NHL games keep their lead, in served order; the
        # Wings join them, ahead of every game that starts tomorrow.
        assert upcoming[:5] == [
            "New York Rangers @ Detroit Red Wings",
            "Washington Capitals @ Carolina Hurricanes",
            "Boston Bruins @ Winnipeg Jets",
            "St Louis Blues @ Dallas Stars",
            WINGS,
        ], upcoming
        assert out.index(served[16]) == 7, "the Wings take the first trailing upcoming slot"
        # Everyone else keeps their served order behind them.
        assert upcoming[5:] == [u for u in _upcoming(served) if u not in upcoming[:5]]
        assert meta["imminent"] == 5

    def test_CONTROL_tonights_tier2_regular_season_games_stay_put(self):
        """Pitt @ Virginia Tech and Penn State @ Northwestern start inside the
        window too; they are not playoff games, so they are not promoted."""
        served = _wnba_served()
        out, _ = lead_upcoming_with_imminent_marquee_games(served, now=WNBA_NOW)
        upcoming = _upcoming(out)
        pitt, psu = (
            "Pittsburgh Panthers @ Virginia Tech Hokies",
            "Penn State Nittany Lions @ Northwestern Wildcats",
        )
        assert upcoming.index(pitt) == 5 and upcoming.index(psu) == 8, upcoming
        assert upcoming.index(pitt) > upcoming.index(WINGS)

    def test_CONTROL_tomorrows_tier2_playoff_game_is_not_moved_up(self):
        """Liberty @ Dream is a WNBA playoff game too, but tips off in 27h."""
        served = _wnba_served()
        out, _ = lead_upcoming_with_imminent_marquee_games(served, now=WNBA_NOW)
        assert _upcoming(out).index("New York Liberty @ Atlanta Dream") == 9

    def test_only_upcoming_slots_change_occupant(self):
        served = _wnba_served()
        out, _ = lead_upcoming_with_imminent_marquee_games(served, now=WNBA_NOW)
        assert len(out) == len(served)
        assert sorted(map(id, out)) == sorted(map(id, served))
        for a, b in zip(served, out):
            if a is not b:
                assert _upcoming([a]) and _upcoming([b]), (a.get("type"), b.get("type"))

    def test_a_tier2_championship_game_counts_too(self):
        items = [
            _game("NextDayNFL", hours=26, score=87),
            _game("TonightFinal", hours=2, tier=2, importance="championship"),
        ]
        out, _ = lead_upcoming_with_imminent_marquee_games(items, now=NOW)
        assert _names(out) == ["TonightFinal", "NextDayNFL"]

    def test_CONTROL_a_tier3_or_tier4_playoff_game_is_not_promoted(self):
        """The tagger reads any knockout round as a playoff (an EFL Cup tie,
        #8942); a lower-tier cup tie does not jump a next-day marquee game."""
        items = [
            _game("NextDayPlayoff", hours=26, score=87, importance="playoff"),
            _game("TonightEuroleague", hours=1, tier=3, importance="playoff"),
            _game("TonightCupTie", hours=1, tier=4, importance="playoff"),
        ]
        out, meta = lead_upcoming_with_imminent_marquee_games(items, now=NOW)
        assert out == items
        assert meta["imminent"] == 0

    def test_CONTROL_a_tier2_exhibition_or_regular_season_game_is_not_promoted(self):
        items = [
            _game("NextDayPlayoff", hours=26, score=87),
            _game("TonightNCAAF", hours=1, tier=2, importance="regular_season"),
            _game("TonightPreseason", hours=1, tier=2, importance="exhibition"),
        ]
        out, meta = lead_upcoming_with_imminent_marquee_games(items, now=NOW)
        assert out == items
        assert meta["imminent"] == 0

    def test_the_tier2_playoff_game_keeps_every_existing_refusal(self):
        """Same window, same strictly-ahead start, same status guard."""
        items = [
            _game("Later", hours=26),
            _game("Lagging", hours=-0.2, tier=2, importance="playoff"),
            _game("TooFar", hours=IMMINENT_KICKOFF_HOURS + 1, tier=2, importance="playoff"),
            _game("Live", hours=-1, tier=2, importance="playoff", status="live"),
        ]
        out, meta = lead_upcoming_with_imminent_marquee_games(items, now=NOW)
        assert out == items
        assert meta["imminent"] == 0


class TestWiring:
    def test_the_gate_reads_the_explicit_signal_not_the_discover_negation(self):
        src = inspect.getsource(apply_discover_display_chain)
        call = src.index("lead_upcoming_with_imminent_marquee_games(")
        gate = src.rindex("if ", 0, call)
        gate_line = src[gate : src.index("\n", gate)]
        assert "sports_mode" in gate_line, gate_line
        assert "not my_teams_only" in gate_line, gate_line
        assert "discover_mode" not in gate_line, gate_line

    def test_it_runs_after_the_futures_cap_and_before_the_live_hoist(self):
        tree = ast.parse(inspect.getsource(apply_discover_display_chain))
        watched = (
            "cap_futures_on_games_led_first_page",
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
            and n.value.func.id == "lead_upcoming_with_imminent_marquee_games"
        ]
        assert len(bound) == 1, "expected exactly one call site"
        targets = bound[0].targets[0]
        assert [t.id for t in targets.elts] == ["items", "imminent_marquee_meta"]


class TestTheOtherSurfacesAreUnchanged:
    @staticmethod
    def _pool():
        return [_game(f"Later{i}", hours=26, score=80 - i) for i in range(5)] + [
            _game("Tonight", hours=1, score=40)
        ]

    def test_CONTROL_discover_never_invokes_the_pass(self):
        _out, meta = apply_discover_display_chain(
            self._pool(), limit=20, ctx=PersonalizationContext(), now=NOW, **DISCOVER
        )
        assert meta["imminent_marquee_upcoming"] is None

    def test_CONTROL_my_stuff_via_sports_mode_never_invokes_the_pass(self):
        _out, meta = apply_discover_display_chain(
            self._pool(),
            limit=20,
            ctx=PersonalizationContext(),
            now=NOW,
            **MY_STUFF_VIA_SPORTS_MODE,
        )
        assert meta["imminent_marquee_upcoming"] is None

    def test_sports_mode_does_invoke_the_pass(self):
        out, meta = apply_discover_display_chain(
            self._pool(), limit=20, ctx=PersonalizationContext(), now=NOW, **SPORTS
        )
        assert meta["imminent_marquee_upcoming"]["imminent"] == 1
        assert _names(out)[0] == "Tonight"


class TestTheConstants:
    def test_the_window_is_discovers_imminent_window(self):
        """One definition of "tonight" across Discover (#4898) and Sports."""
        assert IMMINENT_KICKOFF_HOURS == feed_module._DISCOVER_IMMINENT_KICKOFF_HOURS

    def test_the_statuses_are_discovers_imminent_statuses(self):
        assert UPCOMING_STATUSES == feed_module._DISCOVER_IMMINENT_STATUSES
