"""A held match is held for its whole session gap, and its clock starts there (#9613).

PILLAR: TRUTH.  SHIP: a China Open doubles match held for tomorrow's session
reads "Starts in …" until that session, and at it goes LIVE instead of
"Suspended". The same holds for a later session more than a day after the venue
stamp.

## Two gaps in the #9588 hold's contract

**The band.** The writer (``statpal_names_a_later_session``) held for ANY future
StatPal start. The readers (the serve path and the rails) honoured the stamp
only inside a 24h band. MEASURED, production 2026-09-29 22:05Z, over the 37
rows the #9588 census found: the largest gap between the venue stamp and
StatPal's start is 34.66h, and 9 of the 37 exceed 24h. On those, once the venue
stamp was 24h old, the row was still ``scheduled`` (held) but read "No result
reported" again, and the task had stopped revisiting it, so nothing maintained
the stamp. One constant, ``STATPAL_LATER_SESSION_HORIZON`` (now 48h), now
bounds the writer, the promoter's revisit and both readers.

**The clock.** At StatPal's start the hold ends and the clock promotes the row.
On the same pass the staleness arm measured "hours since start" from the venue
stamp, which is 21h for ``/events/15320754``, against tennis's 6.5h bound, so
the promoted row was suspended before a ball was hit. A held row's clock now
starts at StatPal's start.
"""

from __future__ import annotations

import contextlib
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest

from app.utils.event_completion import (
    STATPAL_LATER_SESSION_HORIZON,
    STATPAL_LATER_SESSION_KEY,
    STATPAL_LATER_SESSION_MARGIN,
    STATPAL_RELEASED_SESSION_KEY,
    started_without_result,
    statpal_later_session_clock,
    statpal_later_session_pending,
    statpal_later_session_value,
    statpal_names_a_later_session,
    statpal_released_session_clock,
    statpal_released_session_value,
)
from app.utils.event_rails import started_without_result_rows
from tests.test_a_held_later_session_is_not_result_less_9613 import _db_row
from tests.test_a_result_less_fixture_does_not_lead_the_search_4876 import _tier_of
from tests.test_a_venue_stamp_does_not_start_a_later_session_9588 import (
    FIXTURE,
    KALSHI_STAMP,
    STATPAL_START,
    _anchor_for,
    _NetSession,
    _Row,
)

UTC = timezone.utc

# The census's widest gap: 15309330, Polymarket 05:20:12Z 9/10 → StatPal 16:00Z 9/11.
WIDE_STAMP = datetime(2026, 9, 10, 5, 20, 12, tzinfo=UTC)
WIDE_START = datetime(2026, 9, 11, 16, 0, tzinfo=UTC)


def _writer(commence, start, now, source="kalshi"):
    return statpal_names_a_later_session(source, FIXTURE, False, commence, start, now)


def _readers(commence, start, now):
    """Both reader halves: (Python pending, Python label, SQL rail)."""
    sources = {STATPAL_LATER_SESSION_KEY: statpal_later_session_value(start)}
    stamp = sources[STATPAL_LATER_SESSION_KEY]
    return (
        statpal_later_session_pending(sources, commence, now),
        started_without_result("scheduled", commence, now, sources),
        bool(_tier_of(started_without_result_rows(now), _db_row(99, "scheduled", commence, stamp))),
    )


class TestTheBand:
    def test_the_widest_census_gap_is_inside_the_band(self):
        """The constant was sized by this row. Shrink the band below 34.66h and
        this fails before any reader does."""
        assert WIDE_START - WIDE_STAMP <= STATPAL_LATER_SESSION_HORIZON

    def test_the_widest_row_is_held_and_honoured_a_day_and_more_in(self):
        """THE SHIP, band half. 30h after its stamp, 4.66h before StatPal's
        start. RED before #9613: pending False, label True (both 24h-bound)."""
        now = WIDE_STAMP + timedelta(hours=30)
        assert _writer(WIDE_STAMP, WIDE_START, now, source="polymarket") is True
        assert _readers(WIDE_STAMP, WIDE_START, now) == (True, False, False)

    @pytest.mark.parametrize(
        "gap",
        [
            STATPAL_LATER_SESSION_MARGIN + timedelta(minutes=1),
            timedelta(hours=21),
            timedelta(hours=26),
            WIDE_START - WIDE_STAMP,
            STATPAL_LATER_SESSION_HORIZON,
        ],
        ids=["margin+1m", "21h-beijing", "26h", "34.66h-widest", "at-band"],
    )
    @pytest.mark.parametrize("elapsed", [0.0, 0.5, 0.999], ids=["at-stamp", "mid", "last-minute"])
    def test_every_stamp_the_writer_writes_is_one_the_readers_honour(self, gap, elapsed):
        """THE CONTRACT. Writer True ⇒ both readers hold, at every instant the
        hold is live. Two bounds in two constants is how this broke."""
        start = KALSHI_STAMP + gap
        now = KALSHI_STAMP + gap * elapsed
        assert _writer(KALSHI_STAMP, start, now) is True
        assert _readers(KALSHI_STAMP, start, now) == (True, False, False)

    def test_beyond_the_band_the_writer_fails_open(self):
        """A StatPal start more than the band after the stamp is not this
        session's later slot. Both sides decline, so they still agree."""
        start = KALSHI_STAMP + STATPAL_LATER_SESSION_HORIZON + timedelta(minutes=1)
        now = KALSHI_STAMP + timedelta(hours=1)
        assert _writer(KALSHI_STAMP, start, now) is False
        assert statpal_later_session_clock("kalshi", FIXTURE, False, KALSHI_STAMP, start) is None

    def test_the_clock_is_statpals_start_before_and_after_it(self):
        """Clock-free: the same answer whether the session is ahead or begun."""
        assert statpal_later_session_clock(
            "kalshi", FIXTURE, False, KALSHI_STAMP, STATPAL_START
        ) == STATPAL_START
        assert _writer(KALSHI_STAMP, STATPAL_START, STATPAL_START) is False

    @pytest.mark.parametrize(
        "args",
        [
            ("odds_api", FIXTURE, False),
            ("kalshi", None, False),
            ("kalshi", FIXTURE, True),
        ],
        ids=["reported-start", "no-fixture", "play-evidence"],
    )
    def test_the_clock_fails_open_where_the_hold_does(self, args):
        assert statpal_later_session_clock(*args, KALSHI_STAMP, STATPAL_START) is None


# ---------------------------------------------------------------------------
# The loop, at an instant this file chooses (the 9588 harness freezes 09:22Z).
# ---------------------------------------------------------------------------


async def _run_at(now, scheduled=(), live=(), anchors=()):
    session = _NetSession(list(scheduled), list(live), list(anchors))

    @contextlib.asynccontextmanager
    async def _fake_session():
        yield session

    import app.tasks.espn_sync as mod

    class _Frozen(datetime):
        @classmethod
        def now(cls, tz=None):
            return now

    with patch("app.tasks.base.get_task_session", _fake_session), patch.object(
        mod, "datetime", _Frozen
    ):
        stats = await mod._transition_event_statuses_impl()
    return stats


class TestTheClock:
    @pytest.mark.asyncio
    async def test_a_released_match_is_not_suspended_at_its_session(self):
        """THE SHIP, clock half. 02:01Z 9/30, one minute into the Beijing
        session, 21h past Kalshi's stamp, no score. RED before #9613:
        suspended. The sibling with no StatPal anchor is the control: the
        staleness arm still suspends it (gotcha #42)."""
        released = _Row(15320754, status="live")
        sibling = _Row(15320999, status="live", fixture=None)
        stats = await _run_at(
            STATPAL_START + timedelta(minutes=1),
            live=[released, sibling],
            anchors=[_anchor_for(15320754)],
        )
        assert released.status == "live"
        assert sibling.status == "suspended"
        assert stats["live_to_suspended"] == 1

    @pytest.mark.asyncio
    async def test_the_clock_runs_from_statpals_start(self):
        """The KILL control: a clock that never ran would pass the ship. 7h
        after StatPal's start is past tennis's 6.5h, so the row is suspended."""
        row = _Row(15320754, status="live")
        await _run_at(
            STATPAL_START + timedelta(hours=7),
            live=[row],
            anchors=[_anchor_for(15320754)],
        )
        assert row.status == "suspended"

    @pytest.mark.asyncio
    async def test_an_old_held_row_is_held_and_keeps_its_stamp(self):
        """30h past its stamp, outside the promoter's 24h window, which only
        the stamp brought it back into. Held, and the stamp is unchanged."""
        now = WIDE_STAMP + timedelta(hours=30)
        row = _Row(15309330)
        row.commence_time = WIDE_STAMP
        row.commence_time_source = "polymarket"
        stamp = {STATPAL_LATER_SESSION_KEY: statpal_later_session_value(WIDE_START)}
        row.win_probability_sources = stamp
        stats = await _run_at(
            now,
            scheduled=[row],
            anchors=[_anchor_for(15309330, start=WIDE_START.isoformat())],
        )
        assert row.status == "scheduled"
        assert row.win_probability_sources is stamp
        assert stats["held_statpal_later_session"] == 1

    @pytest.mark.asyncio
    async def test_an_old_row_whose_session_arrives_is_promoted(self):
        now = WIDE_START + timedelta(minutes=1)
        row = _Row(15309330)
        row.commence_time = WIDE_STAMP
        row.commence_time_source = "polymarket"
        row.win_probability_sources = {
            STATPAL_LATER_SESSION_KEY: statpal_later_session_value(WIDE_START)
        }
        stats = await _run_at(
            now,
            scheduled=[row],
            anchors=[_anchor_for(15309330, start=WIDE_START.isoformat())],
        )
        assert row.status == "live"
        assert STATPAL_LATER_SESSION_KEY not in row.win_probability_sources
        assert stats["cleared_statpal_outside_window"] == 0

    @pytest.mark.asyncio
    async def test_an_old_row_that_loses_its_hold_otherwise_is_not_promoted(self):
        """The anchor is gone. Inside 24h that row would promote on the clock.
        Here the clock ran out a day ago, so it only loses the stamp."""
        now = WIDE_STAMP + timedelta(hours=30)
        row = _Row(15309330)
        row.commence_time = WIDE_STAMP
        row.commence_time_source = "polymarket"
        row.win_probability_sources = {
            STATPAL_LATER_SESSION_KEY: statpal_later_session_value(WIDE_START)
        }
        stats = await _run_at(now, scheduled=[row], anchors=[])
        assert row.status == "scheduled"
        assert STATPAL_LATER_SESSION_KEY not in row.win_probability_sources
        assert stats["cleared_statpal_outside_window"] == 1


# ---------------------------------------------------------------------------
# CERT-3811: the clock survives the first score StatPal writes.
# ---------------------------------------------------------------------------

RECEIPT = statpal_released_session_value(STATPAL_START, FIXTURE)


def _playing(row, period="1st Set"):
    """What StatPal livescores write once the session is under way: a period
    (and a score), and no qualifying non-venue win-prob snapshot."""
    row.period = period
    row.home_score, row.away_score = 0, 0
    return row


class TestTheReceipt:
    @pytest.mark.asyncio
    async def test_held_released_then_played_stays_live_then_suspends_on_statpals_clock(self):
        """THE SHIP, CERT-3811's two passes and on. Held the evening before,
        promoted at StatPal's start, then StatPal writes '1st Set'. RED at
        f6d229bc23: the play pass returned suspended, live_to_suspended=1,
        because play ended the hold's predicate and the clock fell back to
        Kalshi's stamp 21h earlier."""
        row = _Row(15320754)
        anchors = [_anchor_for(15320754)]

        stats = await _run_at(STATPAL_START - timedelta(hours=1), scheduled=[row], anchors=anchors)
        assert row.status == "scheduled"
        assert stats["held_statpal_later_session"] == 1
        assert STATPAL_RELEASED_SESSION_KEY not in row.win_probability_sources

        stats = await _run_at(STATPAL_START + timedelta(minutes=1), scheduled=[row], anchors=anchors)
        assert row.status == "live"
        assert row.win_probability_sources[STATPAL_RELEASED_SESSION_KEY] == RECEIPT
        assert STATPAL_LATER_SESSION_KEY not in row.win_probability_sources
        assert stats["statpal_released_session_stamped"] == 1

        _playing(row)
        stats = await _run_at(STATPAL_START + timedelta(hours=1), live=[row], anchors=anchors)
        assert row.status == "live"
        assert stats["live_to_suspended"] == 0

        stats = await _run_at(STATPAL_START + timedelta(hours=6), live=[row], anchors=anchors)
        assert row.status == "live"
        assert stats["live_to_suspended"] == 0

        # The KILL control: the receipt is a clock, not a pardon. Past tennis's
        # bound measured from StatPal's start, with nothing reporting, it goes.
        stats = await _run_at(STATPAL_START + timedelta(hours=7), live=[row], anchors=anchors)
        assert row.status == "suspended"
        assert stats["live_to_suspended"] == 1

    @pytest.mark.asyncio
    async def test_without_the_receipt_the_played_row_is_suspended(self):
        """The CONTROL, and CERT-3811's reproduction verbatim: the same played
        row with no receipt. It is suspended, so the receipt is what holds the
        ship above, not some other path."""
        row = _playing(_Row(15320754, status="live"))
        stats = await _run_at(
            STATPAL_START + timedelta(hours=1), live=[row], anchors=[_anchor_for(15320754)]
        )
        assert row.status == "suspended"
        assert stats["live_to_suspended"] == 1

    @pytest.mark.asyncio
    async def test_a_row_the_clock_promoted_earlier_gets_its_receipt_on_the_live_arm(self):
        """A row already live before StatPal's start (promoted before the hold
        existed, or before its link landed, then left live) is released by the
        live arm's pre-play pass. That pass writes the receipt too."""
        row = _Row(15320754, status="live")
        anchors = [_anchor_for(15320754)]
        await _run_at(STATPAL_START + timedelta(minutes=5), live=[row], anchors=anchors)
        assert row.status == "live"
        assert row.win_probability_sources[STATPAL_RELEASED_SESSION_KEY] == RECEIPT

        _playing(row)
        stats = await _run_at(STATPAL_START + timedelta(hours=2), live=[row], anchors=anchors)
        assert row.status == "live"
        assert stats["live_to_suspended"] == 0

    @pytest.mark.asyncio
    async def test_a_receipt_costs_one_write(self):
        row = _Row(15320754, status="live")
        anchors = [_anchor_for(15320754)]
        await _run_at(STATPAL_START + timedelta(minutes=5), live=[row], anchors=anchors)
        written = row.win_probability_sources
        stats = await _run_at(STATPAL_START + timedelta(minutes=20), live=[row], anchors=anchors)
        assert row.win_probability_sources is written
        assert stats["statpal_released_session_stamped"] == 0

    @pytest.mark.asyncio
    async def test_a_sibling_with_play_and_no_statpal_link_is_still_suspended(self):
        """gotcha #42: the receipt path must not stop the arm for everyone."""
        released = _Row(15320754, status="live")
        released.win_probability_sources = {STATPAL_RELEASED_SESSION_KEY: RECEIPT}
        _playing(released)
        sibling = _playing(_Row(15320999, status="live", fixture=None))
        sibling.win_probability_sources = {STATPAL_RELEASED_SESSION_KEY: RECEIPT}
        stats = await _run_at(
            STATPAL_START + timedelta(hours=1),
            live=[released, sibling],
            anchors=[_anchor_for(15320754)],
        )
        assert released.status == "live"
        assert sibling.status == "suspended"
        assert stats["live_to_suspended"] == 1


class TestTheReceiptIsTrustedOnlyWhereTheClockIs:
    def _clock(self, receipt=RECEIPT, source="kalshi", fixture=FIXTURE,
               commence=KALSHI_STAMP, now=STATPAL_START + timedelta(hours=1)):
        return statpal_released_session_clock(
            {STATPAL_RELEASED_SESSION_KEY: receipt}, source, fixture, commence, now
        )

    def test_the_receipt_is_statpals_start(self):
        assert self._clock() == STATPAL_START

    def test_the_receipt_is_a_string_like_the_hold_stamp(self):
        """Several readers walk every key of win_probability_sources and treat
        a dict as a source entry; a string is the shape they already skip."""
        assert isinstance(RECEIPT, str)

    @pytest.mark.parametrize(
        "kwargs",
        [
            {"source": "espn"},
            {"source": "odds_api"},
            {"fixture": None},
            {"fixture": "9999999"},
            {"now": STATPAL_START - timedelta(minutes=1)},
            {"commence": STATPAL_START - STATPAL_LATER_SESSION_MARGIN},
            {"commence": STATPAL_START - STATPAL_LATER_SESSION_HORIZON - timedelta(minutes=1)},
            {"commence": None},
            {"now": None},
            {"receipt": "not-a-date|" + FIXTURE},
            {"receipt": statpal_later_session_value(STATPAL_START)},
            {"receipt": statpal_later_session_value(STATPAL_START) + "|"},
            {"receipt": {"start": statpal_later_session_value(STATPAL_START)}},
            {"receipt": None},
        ],
        ids=[
            "espn-rewrote-start", "reported-start", "no-fixture", "other-fixture",
            "not-yet-reached", "inside-margin", "beyond-band", "no-commence",
            "no-now", "malformed-date", "no-fixture-part", "empty-fixture-part",
            "dict-shaped", "absent",
        ],
    )
    def test_every_way_the_clock_ends_ends_the_receipt_except_play(self, kwargs):
        assert self._clock(**kwargs) is None
