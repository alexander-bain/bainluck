"""A match StatPal puts in a later session does not read "No result reported" (#9613).

PILLAR: TRUTH.  SHIP: a China Open doubles match scheduled for tomorrow stops
reading "No result reported" today.

## The specimen, production 2026-09-29 11:50Z

``/events/15320754`` Bublik / Shang v Cerundolo / Rinderknech. #9588 fixed the
LIVE badge: ``transition_event_statuses`` holds the row ``scheduled`` because its
own StatPal anchor (``tennis:2638141``) starts the match at 02:00Z 9/30, not at
Kalshi's 05:00Z 9/29 expiry stamp. The hero still read **"No result reported"**:
``GET /api/events/15320754`` served ``started_without_result: true``, because
that predicate answers from the clock (05:00Z + 2h grace) and the StatPal fact
lived only inside the task.

The task now records the hold on the row (``statpal_later_session_start``), and
the predicate and its SQL twin read it. This file guards both halves, the
writer and the readers, plus the rails' joint exhaustiveness (#3211).
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import pytest

from app.utils.event_completion import (
    ESPN_NOT_STARTED_KEY,
    STATPAL_LATER_SESSION_HORIZON,
    STATPAL_LATER_SESSION_KEY,
    started_without_result,
    statpal_later_session_value,
)
from app.utils.event_rails import (
    started_without_result_rows,
    unreported_rail_condition,
    upcoming_rail_condition,
)
from tests.test_a_result_less_fixture_does_not_lead_the_search_4876 import (
    _row,
    _tier_of,
)
from tests.test_a_venue_stamp_does_not_start_a_later_session_9588 import (
    KALSHI_STAMP,
    STATPAL_START,
    _anchor_for,
    _Row,
    _run_net,
)

UTC = timezone.utc
READ = datetime(2026, 9, 29, 11, 50, tzinfo=UTC)       # the issue's production read
HELD = statpal_later_session_value(STATPAL_START)      # "2026-09-30T02:00:00+00:00"


def _sources(stamp):
    return None if stamp is None else {STATPAL_LATER_SESSION_KEY: stamp}


def _db_row(event_id, status, commence, stamp=None):
    row = _row(event_id, status, commence.strftime("%Y-%m-%d %H:%M:%S"))
    row["win_probability_sources"] = (
        None if stamp is None else json.dumps({STATPAL_LATER_SESSION_KEY: stamp})
    )
    return row


STAMPS = {
    "the_specimen": HELD,
    "one_minute_ahead": (READ + timedelta(minutes=1)).isoformat(),
    "reached": READ.isoformat(),
    "passed": (READ - timedelta(minutes=1)).isoformat(),
    "at_horizon": (READ + STATPAL_LATER_SESSION_HORIZON).isoformat(),
    "beyond_horizon": (READ + STATPAL_LATER_SESSION_HORIZON + timedelta(minutes=1)).isoformat(),
    "malformed": "not-a-time",
    "absent": None,
}
OFFSETS = {
    "the_specimen": KALSHI_STAMP - READ,
    "inside_grace": timedelta(minutes=-30),
    "at_horizon": -STATPAL_LATER_SESSION_HORIZON,
    "past_horizon": -STATPAL_LATER_SESSION_HORIZON - timedelta(minutes=1),
}


class TestTheSpecimen:
    def test_the_held_row_is_not_result_less(self):
        assert started_without_result("scheduled", KALSHI_STAMP, READ, _sources(HELD)) is False

    def test_control_without_the_stamp_it_reads_as_production_served(self):
        """The BEFORE: the clock alone says result-less, which is what shipped."""
        assert started_without_result("scheduled", KALSHI_STAMP, READ, {}) is True

    def test_the_hold_ends_at_statpals_start(self):
        at_start = STATPAL_START
        assert started_without_result("scheduled", KALSHI_STAMP, at_start, _sources(HELD)) is True

    def test_a_row_past_the_horizon_is_not_held(self):
        """The writer only revisits a stamped row inside the band, so a stamp
        past it is one nothing maintains."""
        old = READ - STATPAL_LATER_SESSION_HORIZON - timedelta(minutes=1)
        far = statpal_later_session_value(READ + timedelta(hours=3))
        assert started_without_result("scheduled", old, READ, _sources(far)) is True

    @pytest.mark.parametrize("bad", ["not-a-time", 12345, ["2026-09-30"], STAMPS["beyond_horizon"]])
    def test_an_unreadable_or_absurd_stamp_is_no_hold(self, bad):
        assert started_without_result(
            "scheduled", KALSHI_STAMP, READ, {STATPAL_LATER_SESSION_KEY: bad}
        ) is True

    def test_a_naive_stamp_is_utc(self):
        assert started_without_result(
            "scheduled", KALSHI_STAMP, READ, _sources("2026-09-30T02:00:00")
        ) is False

    def test_the_espn_hold_is_untouched(self):
        """#9195's statement still answers on its own, with no StatPal stamp."""
        fresh = (READ - timedelta(seconds=30)).isoformat()
        assert started_without_result(
            "scheduled", KALSHI_STAMP, READ, {ESPN_NOT_STARTED_KEY: fresh}
        ) is False


class TestTheSqlAgreesWithThePython:
    """The rail and the card label are one claim, in two languages."""

    @pytest.mark.parametrize("stamp_name", list(STAMPS))
    @pytest.mark.parametrize("offset_name", list(OFFSETS))
    def test_started_without_result_rows(self, stamp_name, offset_name):
        commence = READ + OFFSETS[offset_name]
        stamp = STAMPS[stamp_name]
        sql = bool(_tier_of(started_without_result_rows(READ),
                            _db_row(99, "scheduled", commence, stamp)))
        assert sql == started_without_result("scheduled", commence, READ, _sources(stamp)), (
            stamp_name, offset_name,
        )


class TestTheRailsStayJointlyExhaustive:
    """#3211: a row the no-result rail declines must land on the upcoming rail."""

    @pytest.mark.parametrize("stamp_name", list(STAMPS))
    def test_exactly_one_rail_holds_the_specimen(self, stamp_name):
        row = _db_row(99, "scheduled", KALSHI_STAMP, STAMPS[stamp_name])
        upcoming = bool(_tier_of(upcoming_rail_condition(READ), row))
        unreported = bool(_tier_of(
            unreported_rail_condition(READ, lookback=timedelta(days=30)), row
        ))
        assert upcoming != unreported, (stamp_name, upcoming, unreported)
        label = started_without_result(
            "scheduled", KALSHI_STAMP, READ, _sources(STAMPS[stamp_name])
        )
        assert unreported == label, "the rail must agree with the card's label"

    def test_the_specimen_is_upcoming(self):
        assert _tier_of(upcoming_rail_condition(READ), _db_row(99, "scheduled", KALSHI_STAMP, HELD))


class TestTheServedCard:
    """`_format_event`: the key the web and the app read for "No result reported"."""

    def _event(self, sources):
        from app.models.models import Event, Sport

        now = datetime.now(UTC)
        return Event(
            id=15320754, sport_id=1, sport=Sport(id=1, key="tennis_atp", name="ATP"),
            home_team_name="Bublik / Shang", away_team_name="Cerundolo / Rinderknech",
            commence_time=now - timedelta(hours=6, minutes=50), status="scheduled",
            home_score=None, away_score=None, win_probability_sources=sources,
        )

    def test_a_held_row_serves_false(self):
        from app.routes.events import _format_event

        ahead = statpal_later_session_value(datetime.now(UTC) + timedelta(hours=14))
        event = self._event({STATPAL_LATER_SESSION_KEY: ahead})
        assert _format_event(event)["started_without_result"] is False

    def test_control_no_stamp_serves_true(self):
        from app.routes.events import _format_event

        assert _format_event(self._event({}))["started_without_result"] is True


class TestTheWriter:
    """`transition_event_statuses` records the hold it decides, and only that."""

    @pytest.mark.asyncio
    async def test_the_held_row_is_stamped_and_the_sibling_is_not(self):
        """Both arms in one run (gotcha #42)."""
        held = _Row(15320754)
        sibling = _Row(15320999, fixture=None)
        stats, _ = await _run_net(scheduled=[held, sibling], anchors=[_anchor_for(15320754)])
        assert held.status == "scheduled"
        assert held.win_probability_sources == {STATPAL_LATER_SESSION_KEY: HELD}
        assert sibling.status == "live"
        assert STATPAL_LATER_SESSION_KEY not in sibling.win_probability_sources
        assert stats["statpal_later_session_stamped"] == 1
        assert stats["held_statpal_later_session"] == 1

    @pytest.mark.asyncio
    async def test_end_to_end_the_stamped_row_is_not_result_less(self):
        held = _Row(15320754)
        await _run_net(scheduled=[held], anchors=[_anchor_for(15320754)])
        assert started_without_result(
            held.status, held.commence_time, READ, held.win_probability_sources
        ) is False

    @pytest.mark.asyncio
    async def test_other_keys_survive_and_the_dict_is_new(self):
        held = _Row(15320754)
        original = {"kalshi": {"probability": 0.61}}
        held.win_probability_sources = original
        await _run_net(scheduled=[held], anchors=[_anchor_for(15320754)])
        assert held.win_probability_sources is not original, "gotcha #4: a new object"
        assert held.win_probability_sources["kalshi"] == {"probability": 0.61}
        assert original == {"kalshi": {"probability": 0.61}}

    @pytest.mark.asyncio
    async def test_an_unchanged_stamp_is_not_rewritten(self):
        held = _Row(15320754)
        stamped = {STATPAL_LATER_SESSION_KEY: HELD}
        held.win_probability_sources = stamped
        stats, _ = await _run_net(scheduled=[held], anchors=[_anchor_for(15320754)])
        assert held.win_probability_sources is stamped
        assert stats["statpal_later_session_stamped"] == 0

    @pytest.mark.asyncio
    async def test_a_moved_start_is_restamped(self):
        held = _Row(15320754)
        held.win_probability_sources = {STATPAL_LATER_SESSION_KEY: "2026-09-30T04:00:00+00:00"}
        stats, _ = await _run_net(scheduled=[held], anchors=[_anchor_for(15320754)])
        assert held.win_probability_sources[STATPAL_LATER_SESSION_KEY] == HELD
        assert stats["statpal_later_session_stamped"] == 1

    @pytest.mark.asyncio
    async def test_a_session_already_reached_clears_the_stamp(self):
        row = _Row(15320754)
        row.win_probability_sources = {STATPAL_LATER_SESSION_KEY: HELD, "kalshi": 1}
        stats, _ = await _run_net(
            scheduled=[row],
            anchors=[_anchor_for(15320754, start="2026-09-29T09:00:00+00:00")],
        )
        assert row.status == "live"
        assert row.win_probability_sources == {"kalshi": 1}
        assert stats["statpal_later_session_cleared"] == 1

    @pytest.mark.asyncio
    async def test_a_row_that_loses_its_anchor_is_cleared(self):
        row = _Row(15320754, fixture=None)
        row.win_probability_sources = {STATPAL_LATER_SESSION_KEY: HELD}
        stats, _ = await _run_net(scheduled=[row])
        assert row.win_probability_sources == {}
        assert stats["statpal_later_session_cleared"] == 1

    @pytest.mark.asyncio
    async def test_a_demoted_row_carries_the_stamp(self):
        row = _Row(15320754, status="live")
        stats, _ = await _run_net(live=[row], anchors=[_anchor_for(15320754)])
        assert row.status == "scheduled"
        assert stats["demoted_statpal_later_session"] == 1
        assert row.win_probability_sources == {STATPAL_LATER_SESSION_KEY: HELD}
