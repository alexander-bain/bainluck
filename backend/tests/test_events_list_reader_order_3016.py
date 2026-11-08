"""#3016 — `GET /api/events` serves the games on now first, then the games still
to play, then the games behind us.

THE SHIP: `/sports/soccer_other` stops opening on cards that say nothing.
Production, Nov 8 05:07Z, `?sport=soccer_other&limit=50`: the first 13 rows were
`suspended`, 3-5 h past kickoff, with no score. The 12 games actually being
played came after them, and the games still to play after those. The page's own
read (`days=14`, at the 200-row cap) had the same head.

These drive the real route over SQLite, on the rig
`test_events_list_blank_cards_3016.py` built for this issue's first half, and
then the phase rule directly:

  A  red first: with the re-sort lifted, the route serves the suspended rows
     ahead of the live ones, so the corpus reproduces the defect;
  B  the ship: live first, then still to play, then the suspended rows, each
     phase in kickoff order;
  C  nothing is dropped or added. The set is the pre-fix set, and with the cap
     binding the cap still picks the same rows: the re-sort runs after it;
  D  the rule's arms. A paused match with a score is on now. A served
     `started_without_result` is behind us. A venue-graded paused row is behind
     us. An unrecognised status is still to play.

Every kickoff is an offset from the real clock, and none sits near a window
bound: suspended 3-5 h back (inside the finished arm's floor, never less than
24 h back, and inside `FINISHED_MARGIN`, so the blank-card belt cannot touch
them), live 1 h back, scheduled 1-3 h ahead (gotcha #44).
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from app.models.models import Event
from app.utils.event_list_order import (
    BEHIND_US,
    ON_NOW,
    STILL_TO_PLAY,
    in_reader_order,
    reader_phase,
)
from app.utils.lifecycle import served_event_status as _served_event_status
from tests.test_events_list_blank_cards_3016 import S_OTHER, _payload

POLYMARKET = {"polymarket": {"value": 0.9995, "updated_at": "fixture"}}


def _row(event_id, home, away, *, hours, status, scores=(None, None), sources=None):
    when = datetime.now(timezone.utc) + timedelta(hours=hours)
    return Event(
        id=event_id,
        sport_id=S_OTHER,
        home_team_name=home,
        away_team_name=away,
        commence_time=when,
        status=status,
        home_score=scores[0],
        away_score=scores[1],
        win_probability_sources=sources,
    )


def _specimen():
    """The head of the production read, by id, on offsets from now."""
    return [
        _row(15336024, "Real Salt Lake", "Los Angeles Galaxy", hours=-5, status="suspended"),
        _row(15341389, "Louisville City FC", "Miami FC", hours=-4.5, status="suspended",
             sources=POLYMARKET),
        _row(15336539, "LD Alajuelense", "Sporting FC", hours=-3, status="suspended",
             sources=POLYMARKET),
        _row(15341411, "New Mexico United", "Colorado Springs Switchbacks FC", hours=-1.5,
             status="live", sources=POLYMARKET),
        _row(15340272, "Suwon Bluewings", "Yongin FC", hours=-1, status="live",
             sources=POLYMARKET),
        _row(15336300, "Vegalta Sendai", "Ventforet Kofu", hours=1, status="scheduled",
             sources=POLYMARKET),
        _row(15340273, "Paju Frontier FC", "Chungnam Asan FC", hours=3, status="scheduled",
             sources=POLYMARKET),
    ]


SUSPENDED = [15336024, 15341389, 15336539]
LIVE = [15341411, 15340272]
SCHEDULED = [15336300, 15340273]


def _order(payload) -> list:
    return [card["id"] for card in payload["events"]]


def _as_postgres_returns_it(status, commence_time, now):
    """The real served-status rule, handed the kickoff Postgres would hand it.

    SQLite returns `commence_time` naive, and `timestamptz` returns it aware.
    `live_start_satisfied` cannot compare naive with aware, so it answers "not
    started" and every `live` row on this rig serves as `scheduled`. That made
    this file's first draft pass its order test by coincidence. Attach the UTC
    the column stored, then ask the real rule; `TestTheRig` proves it took.
    """
    if commence_time is not None and commence_time.tzinfo is None:
        commence_time = commence_time.replace(tzinfo=timezone.utc)
    return _served_event_status(status, commence_time, now)


def _served(*events, **params):
    """The served `GET /api/events` body, through the real route."""
    with patch("app.routes.events.served_event_status", new=_as_postgres_returns_it):
        return _payload(*events, **params)


def _pre_fix(*events, **params):
    """The same route with the re-sort lifted: the endpoint before this change."""
    with patch("app.routes.events.in_reader_order", new=lambda rows: rows):
        return _served(*events, **params)


class TestTheRig:
    def test_the_live_rows_serve_as_live(self):
        statuses = {card["id"]: card["status"] for card in _served(*_specimen())["events"]}
        assert [statuses[i] for i in LIVE] == ["live", "live"]
        assert [statuses[i] for i in SUSPENDED] == ["suspended"] * 3
        assert [statuses[i] for i in SCHEDULED] == ["scheduled", "scheduled"]


class TestTheDefectReproduces:
    def test_the_pre_fix_route_led_with_the_suspended_rows(self):
        assert _order(_pre_fix(*_specimen())) == SUSPENDED + LIVE + SCHEDULED, (
            "the pre-fix route must serve the specimen in kickoff order, suspended "
            "first, or this suite certifies a corpus the old code already ordered"
        )


class TestThePageOpensOnTheGamesOnNow:
    def test_live_then_still_to_play_then_behind_us(self):
        assert _order(_served(*_specimen())) == LIVE + SCHEDULED + SUSPENDED

    def test_the_first_card_is_a_game_being_played(self):
        first = _served(*_specimen())["events"][0]
        assert first["status"] == "live"

    def test_with_nothing_live_the_first_card_is_still_to_play(self):
        rows = [r for r in _specimen() if r.status != "live"]
        assert _order(_served(*rows)) == SCHEDULED + SUSPENDED

    def test_a_game_being_played_leads_one_whose_kickoff_just_passed(self):
        """The arm kickoff order cannot produce: the `scheduled` row kicked off
        first (30 min ago, inside the grace, so still to play), and the live
        game still leads it."""
        def rows():  # fresh instances per engine: a committed row is not re-inserted
            return [
                _row(1, "Club A", "Club B", hours=-0.5, status="scheduled"),
                _row(2, "Club C", "Club D", hours=-0.25, status="live"),
            ]

        assert _order(_pre_fix(*rows())) == [1, 2]
        assert _order(_served(*rows())) == [2, 1]

    def test_a_paused_match_with_a_score_stays_with_the_live_games(self):
        rows = _specimen() + [
            _row(3, "Club E", "Club F", hours=-4, status="suspended", scores=(3, 2)),
        ]
        assert _order(_served(*rows))[:3] == [3] + LIVE


class TestNothingIsDroppedOrAdded:
    def test_the_served_set_is_the_pre_fix_set(self):
        assert sorted(_order(_served(*_specimen()))) == sorted(_order(_pre_fix(*_specimen())))

    def test_count_is_unchanged(self):
        assert _served(*_specimen())["count"] == _pre_fix(*_specimen())["count"] == 7

    def test_with_the_cap_binding_the_cap_still_picks_by_kickoff(self):
        """The re-sort runs after the `limit`: a capped page holds the rows it
        always held (the four earliest kickoffs), now with the live one first.
        Sorting in SQL would have swapped the suspended rows out for later
        fixtures, hiding them by volume."""
        assert sorted(_order(_pre_fix(*_specimen(), limit=4))) == sorted(SUSPENDED + LIVE[:1])
        assert _order(_served(*_specimen(), limit=4)) == LIVE[:1] + SUSPENDED


class TestThePhaseRule:
    def test_live_is_on_now(self):
        assert reader_phase({"status": "live"}) == ON_NOW

    def test_a_paused_match_with_a_score_is_on_now(self):
        """The rain delay `live/048` made the state for; its card prints the last
        score and it belongs beside the live games."""
        assert reader_phase({"status": "suspended", "home_score": 3, "away_score": 2}) == ON_NOW

    def test_a_paused_match_with_no_score_is_behind_us(self):
        assert reader_phase({"status": "suspended", "home_score": None, "away_score": None}) == BEHIND_US

    def test_one_sides_score_is_not_a_score(self):
        assert reader_phase({"status": "suspended", "home_score": 1, "away_score": None}) == BEHIND_US

    def test_a_venue_graded_paused_match_is_behind_us(self):
        row = {"status": "suspended", "home_score": 3, "away_score": 2, "venue_settled": True}
        assert reader_phase(row) == BEHIND_US

    def test_scheduled_is_still_to_play_until_the_server_says_it_started(self):
        assert reader_phase({"status": "scheduled"}) == STILL_TO_PLAY
        assert reader_phase({"status": "scheduled", "started_without_result": False}) == STILL_TO_PLAY
        assert reader_phase({"status": "scheduled", "started_without_result": True}) == BEHIND_US

    def test_finals_are_behind_us(self):
        assert reader_phase({"status": "completed", "home_score": 2, "away_score": 1}) == BEHIND_US
        assert reader_phase({"status": "closed"}) == BEHIND_US

    def test_an_unrecognised_status_is_still_to_play_as_on_the_page(self):
        for status in ("postponed", "", None):
            assert reader_phase({"status": status}) == STILL_TO_PLAY

    def test_the_sort_is_stable_and_leaves_the_input_alone(self):
        rows = [
            {"id": 1, "status": "completed"},
            {"id": 2, "status": "scheduled"},
            {"id": 3, "status": "suspended"},
            {"id": 4, "status": "live"},
            {"id": 5, "status": "scheduled"},
            {"id": 6, "status": "live"},
        ]
        before = list(rows)
        assert [r["id"] for r in in_reader_order(rows)] == [4, 6, 2, 5, 1, 3]
        assert rows == before
