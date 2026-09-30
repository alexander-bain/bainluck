"""A held match serves StatPal's start, not the venue stamp, as its start (#9634).

PILLAR: TRUTH.  SHIP: a China Open doubles match scheduled for tonight shows
"Starts in …" instead of a start time seventeen hours in the past.

## The specimen, production 2026-09-29 17:27Z

``/events/15320754`` Bublik / Shang v Cerundolo / Rinderknech. #9613 made the
row serve ``started_without_result: false`` and ux's PR #9661 turned the hero
into "Pregame". The header still printed **Sep 28, 10:00 PM PDT** beside it,
because ``GET /api/events/15320754`` served ``commence_time: 05:00Z 9/29`` —
Kalshi's expiry stamp (gotcha #14) — while the row carried
``statpal_later_session_start: 2026-09-30T02:00:00+00:00``.

``_format_event`` now serves the held start as ``commence_time`` for exactly
the rows the hold covers (``served_commence_time``), and nothing else moves.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.utils.event_completion import (
    STATPAL_LATER_SESSION_HORIZON,
    STATPAL_LATER_SESSION_KEY,
    served_commence_time,
    started_without_result,
    statpal_later_session_pending,
    statpal_later_session_value,
)
from tests.test_a_venue_stamp_does_not_start_a_later_session_9588 import (
    KALSHI_STAMP,
    STATPAL_START,
)

UTC = timezone.utc
READ = datetime(2026, 9, 29, 17, 27, tzinfo=UTC)       # the directive's production read
HELD = statpal_later_session_value(STATPAL_START)      # "2026-09-30T02:00:00+00:00"


def _held(stamp=HELD):
    return {STATPAL_LATER_SESSION_KEY: stamp}


class TestServedCommenceTime:
    def test_the_specimen_serves_statpals_start(self):
        assert served_commence_time("scheduled", KALSHI_STAMP, _held(), READ) == STATPAL_START

    def test_control_without_the_stamp_serves_the_stored_start(self):
        # Production-served before this change, and still for an unheld row.
        assert served_commence_time("scheduled", KALSHI_STAMP, {}, READ) == KALSHI_STAMP
        assert served_commence_time("scheduled", KALSHI_STAMP, None, READ) == KALSHI_STAMP

    @pytest.mark.parametrize("status", ["live", "completed", "closed", "suspended", None])
    def test_only_a_scheduled_row_moves(self, status):
        # A live or finished row keeps its stored start: no sentinel limb that
        # reads live/settled rows ever sees a moved clock.
        assert served_commence_time(status, KALSHI_STAMP, _held(), READ) == KALSHI_STAMP

    @pytest.mark.parametrize(
        "now",
        [
            STATPAL_START,                              # the session has arrived
            STATPAL_START + timedelta(minutes=1),       # and passed
            KALSHI_STAMP + STATPAL_LATER_SESSION_HORIZON + timedelta(minutes=1),
        ],
        ids=["reached", "passed", "stored_start_beyond_horizon"],
    )
    def test_a_lapsed_hold_serves_the_stored_start(self, now):
        assert served_commence_time("scheduled", KALSHI_STAMP, _held(), now) == KALSHI_STAMP

    @pytest.mark.parametrize("bad", ["not-a-time", 12345, "", None])
    def test_an_unreadable_stamp_serves_the_stored_start(self, bad):
        assert served_commence_time("scheduled", KALSHI_STAMP, _held(bad), READ) == KALSHI_STAMP

    def test_a_naive_stamp_is_utc(self):
        naive = STATPAL_START.replace(tzinfo=None).isoformat()
        assert served_commence_time("scheduled", KALSHI_STAMP, _held(naive), READ) == STATPAL_START

    def test_a_naive_stored_start_fails_closed(self):
        naive = KALSHI_STAMP.replace(tzinfo=None)
        assert served_commence_time("scheduled", naive, _held(), READ) == naive

    @pytest.mark.parametrize(
        "now",
        [READ, STATPAL_START - timedelta(seconds=1), STATPAL_START,
         KALSHI_STAMP + STATPAL_LATER_SESSION_HORIZON + timedelta(minutes=1)],
    )
    def test_the_served_start_moves_exactly_when_the_hold_holds(self, now):
        # One definition: the start a reader sees and the flag that decides
        # "No result reported" cannot disagree about whether the stamp counts.
        moved = served_commence_time("scheduled", KALSHI_STAMP, _held(), now) != KALSHI_STAMP
        assert moved is statpal_later_session_pending(_held(), KALSHI_STAMP, now)
        if moved:
            assert started_without_result("scheduled", KALSHI_STAMP, now, _held()) is False


class TestTheServedEvent:
    """`_format_event`: the start the web header and every card print."""

    def _event(self, sources, status="scheduled", event_tags=None):
        from app.models.models import Event, Sport

        now = datetime.now(UTC)
        return Event(
            id=15320754, sport_id=1, sport=Sport(id=1, key="tennis_atp", name="ATP"),
            home_team_name="Bublik / Shang", away_team_name="Cerundolo / Rinderknech",
            commence_time=now - timedelta(hours=12, minutes=27), status=status,
            home_score=None, away_score=None, win_probability_sources=sources,
            event_tags=event_tags,
        )

    def test_a_held_row_serves_statpals_start(self):
        from app.routes.events import _format_event

        start = (datetime.now(UTC) + timedelta(hours=8, minutes=33)).replace(microsecond=0)
        served = _format_event(self._event({STATPAL_LATER_SESSION_KEY: statpal_later_session_value(start)}))
        assert datetime.fromisoformat(served["commence_time"]) == start
        assert served["status"] == "scheduled"
        assert served["started_without_result"] is False

    def test_control_no_stamp_serves_the_stored_start(self):
        from app.routes.events import _format_event

        event = self._event({})
        served = _format_event(event)
        assert served["commence_time"] == event.commence_time.isoformat()
        assert served["started_without_result"] is True

    def test_a_live_row_with_a_stamp_keeps_its_stored_start(self):
        from app.routes.events import _format_event

        start = datetime.now(UTC) + timedelta(hours=8)
        event = self._event({STATPAL_LATER_SESSION_KEY: statpal_later_session_value(start)}, status="live")
        assert _format_event(event)["commence_time"] == event.commence_time.isoformat()

    def test_a_placeholder_tag_on_the_stored_start_is_not_tbd_on_statpals(self):
        # `start_is_tbd` is asked of the served start: a tag naming the venue's
        # instant says nothing about StatPal's.
        from app.routes.events import _format_event
        from app.utils.start_placeholder import start_placeholder_tag

        start = datetime.now(UTC) + timedelta(hours=8)
        stored = datetime.now(UTC) - timedelta(hours=12, minutes=27)
        event = self._event(
            {STATPAL_LATER_SESSION_KEY: statpal_later_session_value(start)},
            event_tags=[start_placeholder_tag(stored)],
        )
        event.commence_time = stored
        assert _format_event(event)["start_is_tbd"] is False
        # Strawman: the same tag on the same row, unheld, IS a placeholder — so
        # the assertion above is about the served start, not a dead tag.
        event.win_probability_sources = {}
        assert _format_event(event)["start_is_tbd"] is True
