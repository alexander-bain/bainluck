"""The linescore reaches a reader, and the cache does not hold it back.

live/058, #2746. Two halves of one number. The poller writes `events.linescore`
every 20 s; a reader sees it only if the payload carries it AND the detail
cache lets go of the old one — live/057's measurement is taken through
`GET /api/events/{id}`, so a 30 s cache in front of a 20 s write is two thirds
of the latency the queue is trying to remove (LAT-P187: an endpoint is not a
surface).
"""

from datetime import datetime, timezone

from app.models import Event, Sport
from app.routes.events import (
    _EVENT_DETAIL_DEFAULT_TTL,
    _EVENT_DETAIL_LIVE_TTL,
    _event_detail_caches_forever,
    _event_detail_live_ttl,
    _format_event,
)

LINE = {
    "source": "espn",
    "unit": "games",
    "state": "in_progress",
    "line": "6-2, 6-7(4), 6-5",
    "current_set": 3,
    "sets": [
        {"home": 6, "away": 2, "home_tiebreak": None, "away_tiebreak": None,
         "won_by": "home"},
        {"home": 6, "away": 7, "home_tiebreak": 4, "away_tiebreak": 7,
         "won_by": "away"},
        {"home": 6, "away": 5, "home_tiebreak": None, "away_tiebreak": None,
         "won_by": None},
    ],
    "sets_won": {"home": 1, "away": 1},
    "games": {"home": 18, "away": 14},
}


def _event(**kwargs):
    sport = Sport(id=1, key=kwargs.pop("sport_key", "tennis_atp_us_open"), name="ATP")
    return Event(
        id=15300836,
        sport_id=1,
        sport=sport,
        home_team_name="Alexei Popyrin",
        away_team_name="Alejandro Tabilo",
        commence_time=datetime(2026, 9, 3, 18, 45, tzinfo=timezone.utc),
        status="live",
        home_score=1,
        away_score=1,
        **kwargs,
    )


class TestThePayload:
    def test_a_live_tennis_event_carries_its_linescore(self):
        """THE SHIP, at the edge a client reads: `1-1` gains `6-2, 6-7(4), 6-5`."""
        data = _format_event(_event(linescore=LINE))

        assert data["linescore"]["line"] == "6-2, 6-7(4), 6-5"
        assert data["linescore"]["current_set"] == 3
        # The set count is still there and still agrees — one row, two grains.
        assert (data["home_score"], data["away_score"]) == (1, 1)

    def test_an_event_with_no_linescore_carries_no_key_at_all(self):
        """Not `"linescore": null`. This formatter runs over every row of every
        list surface, and ~99% of them will never have one."""
        data = _format_event(_event(linescore=None))

        assert "linescore" not in data

    def test_a_linescore_with_no_sets_is_not_emitted(self):
        """A refusal that somehow reached the column must not render as an
        empty score strip — the walkover shape (gotcha #53)."""
        data = _format_event(_event(linescore={"source": "espn", "sets": []}))

        assert "linescore" not in data


class TestTheCacheTtl:
    def test_a_live_tennis_event_is_held_for_ten_seconds(self):
        """Half the latency budget. 20 s write grid + 10 s cache = a 15 s
        median, against 25 s if the cache kept the default."""
        assert _event_detail_live_ttl("tennis_atp_us_open") == 10
        assert _event_detail_live_ttl("tennis_wta") == 10

    def test_every_other_live_sport_keeps_the_default(self):
        """THE CONTROL. A shorter TTL is paid for on the busiest surface in the
        app; it is worth paying only where something upstream writes faster."""
        for key in ("baseball_mlb", "americanfootball_nfl", "soccer_epl", None):
            assert _event_detail_live_ttl(key) == _EVENT_DETAIL_LIVE_TTL

    def test_a_finished_event_is_not_reached_by_the_live_ttl_at_all(self):
        """The live TTL applies to `status == "live"` only — a settled row keeps
        the 5-minute default and a completed one is cached indefinitely."""
        assert _EVENT_DETAIL_DEFAULT_TTL > _event_detail_live_ttl("tennis_atp")


class TestTheSettledCacheFinalizes:
    """CERT-854 repair: a `completed` response cached before the last game was
    served forever, so the poller's two-hour settled grace wrote the right
    scoreline into a database nobody could read it from.

    Status and linescore are written by DIFFERENT jobs on DIFFERENT cadences —
    `transition_event_statuses` at 60 s, `poll_live_tennis_scores` at 20 s — so
    the window where one has flipped and the other has not is ordinary, not
    exotic.
    """

    def test_a_settled_tennis_response_whose_line_is_not_decided_expires(self):
        """THE RACE. `Final` over `6-4, 6-7(2), 5-4`, permanently, is the defect."""
        mid_match = {**LINE, "state": "in_progress", "line": "6-4, 6-7(2), 5-4"}
        response = {"sport": "tennis_atp_us_open", "linescore": mid_match}

        assert _event_detail_caches_forever("completed", response) is False
        assert _event_detail_caches_forever("closed", response) is False

    def test_a_settled_tennis_response_with_a_decided_line_caches_forever(self):
        """THE CONTROL, and it is the whole point of the guard above.

        A rule that simply stopped caching settled tennis would pass the test
        above and put every finished US Open match back on a 5-minute TTL for
        the rest of its life. Terminal means terminal.
        """
        final = {**LINE, "state": "decided", "completion": "final",
                 "line": "6-4, 6-7(2), 7-5", "current_set": None}
        response = {"sport": "tennis_atp_us_open", "linescore": final}

        assert _event_detail_caches_forever("completed", response) is True

    def test_a_settled_tennis_response_with_no_line_at_all_expires(self):
        """Absent is not decided (gotcha #53). A walkover, or a row the poller
        has not reached yet — both self-correct on a bounded TTL and neither
        does on an unbounded one."""
        assert _event_detail_caches_forever(
            "completed", {"sport": "tennis_wta_us_open"}
        ) is False

    def test_every_other_sport_keeps_caching_its_finals_forever(self):
        """THE SECOND CONTROL. No finer grain exists for these, so the settled
        score IS the whole score — paying a TTL there is paying for a race the
        sport cannot have."""
        for key in ("baseball_mlb", "americanfootball_nfl", "soccer_epl", None):
            assert _event_detail_caches_forever(
                "completed", {"sport": key}
            ) is True

    def test_a_live_response_is_never_in_the_forever_branch(self):
        """The forever branch is for settled rows only; a live row takes the
        TTL path above whatever its linescore says."""
        final = {**LINE, "state": "decided"}
        assert _event_detail_caches_forever(
            "live", {"sport": "tennis_atp_us_open", "linescore": final}
        ) is False
        assert _event_detail_caches_forever("scheduled", {"sport": "baseball_mlb"}) is False
