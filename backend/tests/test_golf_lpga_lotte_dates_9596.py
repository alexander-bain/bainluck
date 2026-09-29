"""#9596: the LOTTE Championship card is dated by ESPN's LPGA calendar.

`/sports` filed "LOTTE Championship presented by Hoakalei" under Live Now with a
LIVE pill on 2026-09-29, two days before round 1 (Oct 1-4), because the card had
no dates of play and the web fell back to price movement. #8591's ESPN LPGA fill
skipped it twice over: its name has no women's word (`is_womens` False, though
the card is `tour: lpga`), and its Kalshi `commence_time` is the market's close
(2026-10-18, gotcha #14), which put the name-match window two weeks after play.

The card below is the production row `/api/golf` served 2026-09-29 10:44Z.
"""

from datetime import datetime, timezone

from app.routes import golf as golf_mod

_CALENDAR = [
    {"name": "Walmart NW Arkansas Championship pres. by P&G",
     "start": "2026-09-25T07:00Z", "end": "2026-09-27T07:00Z"},
    {"name": "LOTTE Championship pres. by Hoakalei",
     "start": "2026-10-01T07:00Z", "end": "2026-10-04T07:00Z"},
    {"name": "Buick LPGA Shanghai", "start": "2026-10-15T07:00Z", "end": "2026-10-18T07:00Z"},
    {"name": "BMW Ladies Championship", "start": "2026-10-22T07:00Z", "end": "2026-10-25T07:00Z"},
]
_NOW = datetime(2026, 9, 29, 10, 44, tzinfo=timezone.utc)


def _lotte(**over):
    card = {
        "key": "lotte_championship_presented_by_hoakalei",
        "is_womens": False,
        "tour": "lpga",
        "commence_time": "2026-10-18T04:00:00+00:00",
        "resolution_date": "2026-10-18T04:00:00+00:00",
        "start_date": None,
        "end_date": None,
    }
    card.update(over)
    return card


def _fill(card, now=_NOW, calendar=_CALENDAR):
    golf_mod._fill_dates_from_espn_lpga_calendar([card], calendar, now)
    return card


def test_the_lotte_card_gets_its_dates_of_play():
    card = _fill(_lotte())
    assert card["start_date"] == "2026-10-01T00:00:00+00:00"
    assert card["end_date"] == "2026-10-04T00:00:00+00:00"


def test_market_fields_are_left_as_they_were():
    card = _fill(_lotte())
    assert card["commence_time"] == "2026-10-18T04:00:00+00:00"
    assert card["resolution_date"] == "2026-10-18T04:00:00+00:00"


def test_arm_tour_alone_without_the_now_cap_the_close_time_window_still_misses():
    # The tour widening by itself is not enough: the window is Oct 15-21.
    card = _lotte()
    golf_mod._fill_dates_from_espn_lpga_calendar([card], _CALENDAR)
    assert card["start_date"] is None


def test_arm_now_cap_alone_an_unflagged_non_lpga_card_is_still_refused():
    card = _fill(_lotte(tour=None))
    assert card["start_date"] is None


def test_a_mens_tour_card_is_never_dated_from_the_lpga_calendar():
    card = _fill(_lotte(tour="pga"))
    assert card["start_date"] is None


def test_a_real_past_commence_is_not_moved_by_the_cap():
    # NW Arkansas (#8591's specimen): commence is the real opening, before now.
    card = _fill({
        "key": "nw_arkansas_championship_womens", "is_womens": True, "tour": "lpga",
        "commence_time": "2026-09-21T15:01:14+00:00",
        "resolution_date": "2026-09-28T03:59:00+00:00",
        "start_date": None, "end_date": None,
    }, now=datetime(2026, 9, 25, 10, 0, tzinfo=timezone.utc))
    assert card["start_date"] == "2026-09-25T00:00:00+00:00"


def test_the_cap_does_not_reach_back_past_the_three_day_slack():
    # Served on Oct 5, the capped floor is Oct 2; LOTTE (Oct 1) is outside it and
    # the card stays dateless rather than taking a date the name alone chose.
    card = _fill(_lotte(), now=datetime(2026, 10, 5, 12, 0, tzinfo=timezone.utc))
    assert card["start_date"] is None


def test_get_golf_passes_now_and_gates_on_the_lpga_tour():
    import inspect

    src = inspect.getsource(golf_mod.get_golf)
    assert "_fill_dates_from_espn_lpga_calendar(tournaments, await _get_espn_lpga_calendar(), now)" in src
    assert 't.get("tour") == "lpga"' in src
