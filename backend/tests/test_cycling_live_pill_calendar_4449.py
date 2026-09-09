"""#4449 — a bike race wears the live pill while it is being ridden, and not otherwise.

`cycling_status` decided "live" by proximity to `resolution_date`, which is the
market CLOSE date (gotcha #14) and not the race. Both arms were wrong, in opposite
directions, and the calendar knows better than either:

  Vuelta 2026   ridden Aug 22 – Sep 13, GC market closes Sep 19
                → the 25-day band opened Aug 25 and ran to Sep 19, so the card read
                  `upcoming` for the first three days of the race and `live` for six
                  days after it finished.
  Tour de France 2026  ridden Jul 4 – Jul 26, GC market closes Aug 9
                → the band opened Jul 15: eleven days of a Grand Tour actually being
                  ridden while the card said `upcoming`.

The trailing arm is the one that reaches the reader hardest: `status == "live"` is
what paints the pulsing red `● LIVE` pill and pays the `+35` live bonus in
`_score_event_concept`, the largest term in that function.

Anchors are absolute datetimes — the arithmetic never branches on the wall clock
(gotcha #44).
"""

from datetime import datetime, timedelta, timezone

import pytest

from app.utils.event_cycling import concept_date_window, cycling_status
from app.utils.majors_calendar import calendar_window_state, marquee_pin_state

VUELTA = "event:cycling:vuelta-2026"
TDF = "event:cycling:tour-de-france-2026"

#: The GC market close dates — the anchor the OLD rule used. Kept in the test so the
#: fixtures stay honest about what the band was actually measuring from.
VUELTA_MARKET_CLOSE = datetime(2026, 9, 19, 15, 19, tzinfo=timezone.utc)
TDF_MARKET_CLOSE = datetime(2026, 8, 9, tzinfo=timezone.utc)


def _utc(y, m, d, h=12, mi=0):
    return datetime(y, m, d, h, mi, tzinfo=timezone.utc)


def _old_band(resolution_date, now):
    """The pre-#4449 rule, verbatim, so the guards can assert what CHANGED."""
    if resolution_date is not None:
        if resolution_date < now:
            return "settled"
        if (resolution_date - now).total_seconds() / 86400 <= 25:
            return "live"
    return "upcoming"


class TestTheRaceIsOver:
    """The headline defect: a finished Grand Tour wearing the live pill."""

    @pytest.mark.parametrize("day", [14, 15, 16, 17, 18])
    def test_vuelta_is_not_live_after_it_finishes(self, day):
        now = _utc(2026, 9, day, 18)
        assert cycling_status("open", VUELTA_MARKET_CLOSE, now, concept_key=VUELTA) != "live"

    def test_and_the_old_band_called_every_one_of_those_days_live(self):
        # Direction 2 of the guard: prove the fixture actually exercises the bug.
        for day in (14, 15, 16, 17, 18):
            assert _old_band(VUELTA_MARKET_CLOSE, _utc(2026, 9, day, 18)) == "live"

    def test_tdf_is_not_live_after_it_finishes(self):
        now = _utc(2026, 8, 2)
        assert cycling_status("open", TDF_MARKET_CLOSE, now, concept_key=TDF) == "settled"
        assert _old_band(TDF_MARKET_CLOSE, now) == "live"


class TestTheRaceIsOn:
    """The other arm — never demote a race that is actually being ridden."""

    def test_vuelta_is_live_mid_race(self):
        now = _utc(2026, 9, 9, 21)  # the day #4449 was built
        assert cycling_status("open", VUELTA_MARKET_CLOSE, now, concept_key=VUELTA) == "live"

    def test_vuelta_is_live_on_its_finish_day(self):
        # The whole end DAY reads live; the finish happens that afternoon.
        now = _utc(2026, 9, 13, 17)
        assert cycling_status("open", VUELTA_MARKET_CLOSE, now, concept_key=VUELTA) == "live"

    @pytest.mark.parametrize("day", [22, 23, 24])
    def test_vuelta_is_live_from_its_opening_days(self, day):
        # The band did not open until Aug 25 — three days of racing read `upcoming`.
        now = _utc(2026, 8, day)
        assert cycling_status("open", VUELTA_MARKET_CLOSE, now, concept_key=VUELTA) == "live"
        assert _old_band(VUELTA_MARKET_CLOSE, now) == "upcoming"

    @pytest.mark.parametrize("day", [4, 6, 10, 14])
    def test_tdf_is_live_during_the_eleven_days_the_band_missed(self, day):
        now = _utc(2026, 7, day)
        assert cycling_status("open", TDF_MARKET_CLOSE, now, concept_key=TDF) == "live"
        assert _old_band(TDF_MARKET_CLOSE, now) == "upcoming"


class TestTheRaceHasNotStarted:
    def test_a_race_that_has_not_started_is_never_live(self):
        for now in (_utc(2026, 8, 1), _utc(2026, 8, 20), _utc(2026, 8, 21, 23, 59)):
            assert cycling_status("open", VUELTA_MARKET_CLOSE, now, concept_key=VUELTA) == "upcoming"


class TestWhatHitSurvives:
    """A settled race must still hold its T+36h WHAT-HIT card, or the fix trades one
    reader defect for another: the champion card would vanish the moment the race
    ended."""

    def test_whathit_window_reads_settled_but_is_still_pinned(self):
        now = _utc(2026, 9, 14, 12)  # settlement = Sep 14 00:00Z, +36h = Sep 15 12:00Z
        assert cycling_status("open", VUELTA_MARKET_CLOSE, now, concept_key=VUELTA) == "settled"
        # `_score_event_concepts` admits a settled concept exactly while this is "whathit".
        assert marquee_pin_state(VUELTA, now) == "whathit"

    def test_the_whathit_card_still_scores_above_zero(self):
        # feed.py drops a concept scoring <= 0, so "settled" must not zero it out.
        from app.routes.feed import _score_event_concept

        now = _utc(2026, 9, 14, 12)
        card = {
            "key": VUELTA,
            "status": "settled",
            "is_major": True,
            "latest_commence": VUELTA_MARKET_CLOSE,
        }
        assert _score_event_concept(card, now) >= 45  # base 30 + major 15

    def test_the_pin_is_gone_once_whathit_expires(self):
        now = _utc(2026, 9, 15, 13)  # past settlement + 36h
        assert cycling_status("open", VUELTA_MARKET_CLOSE, now, concept_key=VUELTA) == "settled"
        assert marquee_pin_state(VUELTA, now) is None  # → feed.py drops it


class TestAuthorityAndFallback:
    def test_a_venue_grade_still_wins(self):
        # Mid-race by the calendar, but the source says resolved.
        now = _utc(2026, 9, 9)
        assert cycling_status("resolved", None, now, concept_key=VUELTA) == "settled"

    def test_a_closed_market_outranks_a_calendar_that_says_live(self):
        """A market cannot close before the thing it prices has happened, so a passed
        `resolution_date` settles the race however stale the yaml is. Without this the
        calendar could resurrect a finished race — which is exactly what
        `test_a_finished_race_is_still_filtered_out` caught while #4449 was built."""
        now = _utc(2026, 9, 9)  # mid-race by the calendar
        assert calendar_window_state({"start": "2026-08-22", "end": "2026-09-13"}, now) == "live"
        closed_30_days_ago = now - timedelta(days=30)
        assert cycling_status("open", closed_30_days_ago, now, concept_key=VUELTA) == "settled"

    def test_a_race_with_no_calendar_entry_keeps_the_old_band(self):
        unknown = "event:cycling:no-such-race-2026"
        near, far = _utc(2026, 7, 21), _utc(2026, 5, 1)
        assert cycling_status("open", TDF_MARKET_CLOSE, near, concept_key=unknown) == "live"
        assert cycling_status("open", TDF_MARKET_CLOSE, far, concept_key=unknown) == "upcoming"

    def test_no_concept_key_keeps_the_old_band(self):
        # The event-page and feed call sites both pass one; nothing else should break.
        assert cycling_status("open", TDF_MARKET_CLOSE, _utc(2026, 7, 21)) == "live"

    def test_no_dates_at_all_is_upcoming(self):
        assert cycling_status("open", None, _utc(2026, 7, 21)) == "upcoming"


class TestStartDateIsTheRaceNotTheMarketClose:
    def test_vuelta_start_date_is_august(self):
        start_iso, end_iso = concept_date_window("vuelta-2026", VUELTA_MARKET_CLOSE)
        assert start_iso.startswith("2026-08-22")
        assert end_iso.startswith("2026-09-13")
        # Direction 2: the market close is what the feed card used to serve.
        assert not start_iso.startswith("2026-09-19")

    def test_unknown_race_falls_back_to_the_resolution_date(self):
        start_iso, end_iso = concept_date_window("no-such-race-2026", VUELTA_MARKET_CLOSE)
        assert start_iso == end_iso == VUELTA_MARKET_CLOSE.isoformat()


class TestCalendarWindowState:
    """The one clock. `marquee_pin_state` collapses "not yet" and "long over" into the
    same None (gotcha #53); this is the read that tells them apart."""

    ENTRY = {"start": "2026-08-22", "end": "2026-09-13"}
    SETTLEMENT = datetime(2026, 9, 14, tzinfo=timezone.utc)

    def test_four_states(self):
        assert calendar_window_state(self.ENTRY, _utc(2026, 8, 1)) == "upcoming"
        assert calendar_window_state(self.ENTRY, _utc(2026, 9, 1)) == "live"
        assert calendar_window_state(self.ENTRY, self.SETTLEMENT + timedelta(hours=12)) == "whathit"
        assert calendar_window_state(self.ENTRY, self.SETTLEMENT + timedelta(hours=48)) == "past"

    def test_boundaries_are_half_open(self):
        assert calendar_window_state(self.ENTRY, self.SETTLEMENT - timedelta(seconds=1)) == "live"
        assert calendar_window_state(self.ENTRY, self.SETTLEMENT) == "whathit"
        assert calendar_window_state(self.ENTRY, self.SETTLEMENT + timedelta(hours=36)) == "past"

    def test_defensive(self):
        assert calendar_window_state(None, _utc(2026, 9, 1)) is None
        assert calendar_window_state({}, _utc(2026, 9, 1)) is None
        assert calendar_window_state({"start": "nonsense", "end": "x"}, _utc(2026, 9, 1)) is None

    def test_naive_now_is_utc(self):
        assert calendar_window_state(self.ENTRY, datetime(2026, 9, 1, 12)) == "live"

    def test_marquee_pin_state_contract_is_unchanged_by_the_delegation(self):
        # upcoming and past both still collapse to None for the PIN caller.
        assert marquee_pin_state(VUELTA, _utc(2026, 8, 1)) is None
        assert marquee_pin_state(VUELTA, _utc(2026, 9, 1)) == "live"
        assert marquee_pin_state(VUELTA, _utc(2026, 9, 20)) is None
