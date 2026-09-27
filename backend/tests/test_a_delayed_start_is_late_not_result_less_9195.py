"""#9195 — a rain-delayed game is LATE, not result-less.

    cd backend && python3 -m pytest tests/test_a_delayed_start_is_late_not_result_less_9195.py

Production, 2026-09-27: BAL @ NYY 15319530, listed 17:05Z, ESPN `STATUS_RAIN_DELAY`
/ `pre` all afternoon. After #5324 (live/675) the row correctly read `scheduled`,
but at listing + 2h (19:05Z) the clock-only `started_without_result` turned true:
the card flag behind "No result reported" was set and search ranked the game 31st
of 31 for 'yankees', below month-old leftovers. At 19:35:30Z the row carried the
authority's own `espn_not_started_at` stamp from 50 seconds earlier.

The fix reads that stamp, which already exists: ESPN's live pass rewrites it every
60 s while ESPN reports the row as not begun, and it expires after
`AUTHORITY_NOT_STARTED_TTL` (15 min). The Python predicate, the no-result rail, the
upcoming rail and search's ordering all spend it, so the four cannot disagree and
the two rails stay jointly exhaustive (#3211).
"""

from datetime import datetime, timedelta, timezone
import json

import pytest

from app.models.models import Event, Sport
from app.utils.event_completion import (
    AUTHORITY_NOT_STARTED_HORIZON,
    AUTHORITY_NOT_STARTED_TTL,
    ESPN_NOT_STARTED_KEY,
    UPCOMING_GRACE,
    started_without_result,
)
from app.utils.event_rails import (
    live_scheduled_settled_order,
    started_without_result_rows,
    unreported_rail_condition,
    upcoming_rail_condition,
)
from tests.test_a_result_less_fixture_does_not_lead_the_search_4876 import (
    _order_under,
    _row,
    _tier_of,
)

UTC = timezone.utc
NOW = datetime(2026, 9, 27, 19, 35, 30, 739814, tzinfo=UTC)          # db now() at the read
LISTED = datetime(2026, 9, 27, 17, 5, tzinfo=UTC)                     # 15319530 commence_time
STAMP = "2026-09-27T19:34:40.865519+00:00"                            # its espn_not_started_at


def _sources(stamp):
    return None if stamp is None else {ESPN_NOT_STARTED_KEY: stamp}


def _db_row(event_id, status, commence, stamp=None, **signals):
    row = _row(event_id, status, commence.strftime("%Y-%m-%d %H:%M:%S"), **signals)
    row["win_probability_sources"] = (
        None if stamp is None else json.dumps({ESPN_NOT_STARTED_KEY: stamp})
    )
    return row


STAMPS = {
    "fresh": STAMP,
    "at_ttl": (NOW - AUTHORITY_NOT_STARTED_TTL).isoformat(),
    "stale": (NOW - AUTHORITY_NOT_STARTED_TTL - timedelta(seconds=1)).isoformat(),
    "future": (NOW + timedelta(minutes=1)).isoformat(),
    "malformed": "not-a-time",
    "absent": None,
}
OFFSETS = {
    "just_listed": timedelta(minutes=-5),
    "the_specimen": LISTED - NOW,
    "past_horizon": -AUTHORITY_NOT_STARTED_HORIZON - timedelta(minutes=1),
}


class TestTheSpecimen:
    def test_the_card_flag_is_false_while_espn_says_not_started(self):
        assert started_without_result("scheduled", LISTED, NOW, _sources(STAMP)) is False

    def test_control_the_clock_alone_still_says_what_it_said(self):
        """No sources ⇒ the answer every caller had before (and production served)."""
        assert started_without_result("scheduled", LISTED, NOW) is True

    def test_a_stamp_espn_stopped_refreshing_hands_the_row_back_to_the_clock(self):
        stale = (NOW - AUTHORITY_NOT_STARTED_TTL - timedelta(seconds=1)).isoformat()
        assert started_without_result("scheduled", LISTED, NOW, _sources(stale)) is True

    def test_a_row_past_the_horizon_is_not_held_by_any_stamp(self):
        old = NOW - AUTHORITY_NOT_STARTED_HORIZON - timedelta(minutes=1)
        assert started_without_result("scheduled", old, NOW, _sources(STAMP)) is True

    @pytest.mark.parametrize("bad", ["not-a-time", 12345, (NOW + timedelta(minutes=1)).isoformat()])
    def test_an_unreadable_stamp_is_no_statement(self, bad):
        assert started_without_result("scheduled", LISTED, NOW, {ESPN_NOT_STARTED_KEY: bad}) is True

    def test_only_scheduled_rows_are_asked(self):
        assert started_without_result("live", LISTED, NOW, _sources(STAMP)) is False


class TestTheSqlAgreesWithThePython:
    """The rail membership and the card label are one claim, in two languages."""

    @pytest.mark.parametrize("stamp_name", list(STAMPS))
    @pytest.mark.parametrize("offset_name", list(OFFSETS))
    def test_started_without_result_rows(self, stamp_name, offset_name):
        commence = NOW + OFFSETS[offset_name]
        stamp = STAMPS[stamp_name]
        sql = bool(_tier_of(started_without_result_rows(NOW),
                            _db_row(99, "scheduled", commence, stamp)))
        assert sql == started_without_result("scheduled", commence, NOW, _sources(stamp))


class TestTheRailsStayJointlyExhaustive:
    """#3211: a row the no-result rail declines must land on the upcoming rail."""

    @pytest.mark.parametrize("stamp_name", list(STAMPS))
    def test_exactly_one_rail_holds_the_specimen(self, stamp_name):
        row = _db_row(99, "scheduled", LISTED, STAMPS[stamp_name])
        upcoming = bool(_tier_of(upcoming_rail_condition(NOW), row))
        unreported = bool(_tier_of(unreported_rail_condition(NOW, lookback=timedelta(days=30)), row))
        assert upcoming != unreported, (stamp_name, upcoming, unreported)
        held = started_without_result("scheduled", LISTED, NOW, _sources(STAMPS[stamp_name]))
        assert unreported == held, "the rail must agree with the card's label"

    def test_the_specimen_is_upcoming(self):
        assert _tier_of(upcoming_rail_condition(NOW), _db_row(99, "scheduled", LISTED, STAMP))


class TestSearchOrder:
    def test_the_delayed_game_ranks_with_todays_games_not_the_leftovers(self):
        """'yankees' in miniature: today's delayed game, a month-old result-less
        fixture, two Wild Card games still to come, two recent finals."""
        rows = [
            _db_row(1, "scheduled", datetime(2026, 8, 27, 23, 5, tzinfo=UTC)),       # leftover
            _db_row(2, "completed", datetime(2026, 9, 25, 23, 5, tzinfo=UTC)),
            _db_row(3, "completed", datetime(2026, 9, 24, 23, 5, tzinfo=UTC)),
            _db_row(4, "scheduled", datetime(2026, 9, 29, 17, 0, tzinfo=UTC)),       # Wild Card
            _db_row(5, "scheduled", datetime(2026, 9, 30, 17, 0, tzinfo=UTC)),
            _db_row(15319530, "scheduled", LISTED, STAMP),                            # delayed
        ]
        order = _order_under(live_scheduled_settled_order(NOW), rows)
        assert order.index(15319530) < order.index(1), order
        assert order.index(15319530) < order.index(2), order
        assert _tier_of(live_scheduled_settled_order(NOW), rows[-1]) == \
               _tier_of(live_scheduled_settled_order(NOW), rows[3])

    def test_control_without_the_stamp_it_sinks_as_before(self):
        rows = [_db_row(1, "completed", datetime(2026, 9, 25, 23, 5, tzinfo=UTC)),
                _db_row(15319530, "scheduled", LISTED)]
        assert _order_under(live_scheduled_settled_order(NOW), rows)[-1] == 15319530


class TestTheServedCard:
    """`_format_event` — the key the web and the app read for "No result reported"."""

    def _event(self, sources):
        now = datetime.now(UTC)
        return Event(
            id=15319530, sport_id=1, sport=Sport(id=1, key="baseball_mlb", name="MLB"),
            home_team_name="New York Yankees", away_team_name="Baltimore Orioles",
            commence_time=now - UPCOMING_GRACE - timedelta(minutes=30), status="scheduled",
            home_score=None, away_score=None, win_probability_sources=sources,
        )

    def test_a_fresh_stamp_serves_false(self):
        from app.routes.events import _format_event

        fresh = (datetime.now(UTC) - timedelta(seconds=50)).isoformat()
        assert _format_event(self._event({ESPN_NOT_STARTED_KEY: fresh}))["started_without_result"] is False

    def test_control_no_stamp_serves_true(self):
        from app.routes.events import _format_event

        assert _format_event(self._event({}))["started_without_result"] is True


class TestTheVenueSettlementGatesAgree:
    """The two other callers of the predicate ask the venue for a verdict only on
    rows about to print "No result reported". A delayed game is not one of them,
    and both must read the stamp to agree with the card (#6739 / #7092)."""

    @staticmethod
    def _delayed(sources):
        from types import SimpleNamespace

        now = datetime.now(UTC)
        return now, SimpleNamespace(
            id=15319530, home_team_name="New York Yankees", away_team_name="Baltimore Orioles",
            status="scheduled", commence_time=now - UPCOMING_GRACE - timedelta(minutes=30),
            home_score=None, away_score=None, win_probability_sources=sources,
        )

    @pytest.mark.parametrize("stamped", [True, False])
    def test_the_list_rail_reader(self, stamped):
        import asyncio
        from unittest.mock import AsyncMock, MagicMock

        from app.utils.venue_settlement_reader import attach_venue_settlement

        now, event = self._delayed(
            {ESPN_NOT_STARTED_KEY: (datetime.now(UTC) - timedelta(seconds=50)).isoformat()}
            if stamped else {}
        )
        db = MagicMock()
        db.execute = AsyncMock(side_effect=RuntimeError("asked the venue"))
        cards = [{"id": event.id, "status": "scheduled", "home_score": None, "away_score": None}]
        asyncio.run(attach_venue_settlement(db, [event], cards, now))
        assert db.execute.await_count == (0 if stamped else 1)

    @pytest.mark.parametrize("stamped", [True, False])
    def test_the_settled_hero(self, stamped, monkeypatch):
        import asyncio
        from unittest.mock import AsyncMock

        import app.routes.events as events_route

        now, event = self._delayed(
            {ESPN_NOT_STARTED_KEY: (datetime.now(UTC) - timedelta(seconds=50)).isoformat()}
            if stamped else {}
        )
        asked = AsyncMock(return_value=None)
        monkeypatch.setattr(events_route, "_venue_settlement", asked)
        asyncio.run(events_route._settled_hero_result(object(), event, now))
        assert asked.await_count == (0 if stamped else 1)
