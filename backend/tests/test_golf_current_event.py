"""Golf current_event selection — majors must win the marquee slot (#1075).

Regression for Queue #183 Item 1: majors sit in TOURNAMENT_ORDER and are
therefore NOT flagged `is_tour_event`, which excluded them from the
`_find_current_event` candidate pool entirely. A minor qualifier
("The Open Last Chance Qualifier") won the marquee by default while the actual
major (The Open Championship) was buried. The fix widens the pool to
`is_tour_event OR is_major` so schedule-date priority + importance weighting
put an imminent/in-progress major on top.
"""

from datetime import datetime, timezone

from app.routes.golf import _find_current_event


def _golfers():
    return [
        {"name": "A. Golfer", "probability": 0.20, "movement_24h": 0.01, "sources": {"datagolf": 1}},
        {"name": "B. Golfer", "probability": 0.10, "movement_24h": 0.005, "sources": {"datagolf": 1}},
    ]


def _major(commence: str, resolution: str):
    return {
        "key": "the_open",
        "name": "The Open Championship",
        "is_major": True,
        "is_tour_event": False,  # majors live in TOURNAMENT_ORDER
        "commence_time": commence,
        "resolution_date": resolution,
        "golfers": _golfers(),
        "market_ids": [1],
        "market_names": ["The Open Championship: Winner"],
        "market_sources": ["datagolf"],
    }


def _qualifier(commence: str, resolution: str):
    return {
        "key": "the_open_last_chance_qualifier",
        "name": "The Open Last Chance Qualifier",
        "is_major": False,
        "is_tour_event": True,
        "commence_time": commence,
        "resolution_date": resolution,
        "golfers": _golfers(),
        "market_ids": [2],
        "market_names": ["The Open Last Chance Qualifier: Winner"],
        "market_sources": ["kalshi"],
    }


class TestMajorWinsMarquee:
    def test_upcoming_major_beats_qualifier_via_schedule(self):
        """T-3: The Open is upcoming (within 7 days); qualifier already past.

        Schedule-date priority (Phase 1) must surface the major even though only
        the qualifier is flagged is_tour_event.
        """
        now = datetime(2026, 7, 13, tzinfo=timezone.utc)
        tournaments = [
            _qualifier("2026-07-08T12:00:00+00:00", "2026-07-09T00:00:00+00:00"),
            _major("2026-07-16T12:00:00+00:00", "2026-07-19T23:00:00+00:00"),
        ]
        schedule_by_key = {
            "the_open": {"start_date": "2026-07-16", "end_date": "2026-07-19"},
            "the_open_last_chance_qualifier": {"start_date": "2026-07-08", "end_date": "2026-07-08"},
        }
        result = _find_current_event(tournaments, schedule_by_key, now)
        assert result is not None
        assert result["name"] == "The Open Championship"

    def test_in_progress_major_beats_qualifier(self):
        """Thursday tee-off: The Open is in progress → it must become current_event.

        This is THE live-mode-flip gate from #1075 — without majors in the pool
        the live flip can never happen at tee-off.
        """
        now = datetime(2026, 7, 16, 14, 0, tzinfo=timezone.utc)
        tournaments = [
            _qualifier("2026-07-08T12:00:00+00:00", "2026-07-09T00:00:00+00:00"),
            _major("2026-07-16T12:00:00+00:00", "2026-07-19T23:00:00+00:00"),
        ]
        schedule_by_key = {
            "the_open": {"start_date": "2026-07-16", "end_date": "2026-07-19"},
        }
        result = _find_current_event(tournaments, schedule_by_key, now)
        assert result is not None
        assert result["name"] == "The Open Championship"

    def test_major_wins_via_fallback_when_no_schedule(self):
        """No DataGolf schedule → Phase 2 fallback must still prefer the major by
        importance + proximity (the major commences near now)."""
        now = datetime(2026, 7, 16, 14, 0, tzinfo=timezone.utc)
        tournaments = [
            _qualifier("2026-07-15T12:00:00+00:00", "2026-07-16T00:00:00+00:00"),
            _major("2026-07-16T12:00:00+00:00", "2026-07-19T23:00:00+00:00"),
        ]
        result = _find_current_event(tournaments, {}, now)
        assert result is not None
        assert result["name"] == "The Open Championship"

    def test_finished_major_does_not_displace_current_tour_event(self):
        """A major that ended >6 days ago must NOT hijack the marquee from a live
        tour event (guards against resurfacing a past major via far-future Kalshi
        resolution_date)."""
        now = datetime(2026, 7, 16, 14, 0, tzinfo=timezone.utc)
        # US Open in June with a far-future Kalshi resolution_date, plus a current event.
        past_major = {
            "key": "us_open",
            "name": "U.S. Open",
            "is_major": True,
            "is_tour_event": False,
            "commence_time": "2026-06-11T12:00:00+00:00",
            "resolution_date": "2026-08-01T00:00:00+00:00",
            "golfers": _golfers(),
            "market_ids": [3],
            "market_names": ["U.S. Open: Winner"],
            "market_sources": ["kalshi"],
        }
        live_event = _qualifier("2026-07-16T12:00:00+00:00", "2026-07-17T00:00:00+00:00")
        result = _find_current_event([past_major, live_event], {}, now)
        assert result is not None
        assert result["name"] == "The Open Last Chance Qualifier"
