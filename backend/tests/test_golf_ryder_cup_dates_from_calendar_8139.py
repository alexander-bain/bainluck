"""#8139 — /api/golf gives a dateless tournament the horizon calendar's dates.

The producer half of #8123. `/api/golf` served the Ryder Cup with
`start_date: null` and a `commence_time` of 2026-08-28 that was a capture stamp,
not a time of play, so the card could either print a date almost a month in the
PAST for an event that does not happen until 2027 (the original defect) or,
after #8123 taught it to refuse a date it can prove wrong, print no date at all.
`majors_calendar.yaml` has carried the answer the whole time.

The tests that matter here are the ones that pin what the fill must NOT do. A
date source wired into a list of live tournaments has three ways to lie —
overruling a real schedule, reviving a finished row, and crossing a sport — and
each has a test below that fails if its guard is deleted.
"""

from datetime import datetime, timezone

import pytest

from app.routes.golf import (
    _TOURN_TO_COMPETITION_SLUG,
    _fill_dates_from_calendar,
    _filter_stale_tournaments,
)
from app.utils.competition_identity import next_edition

# A fixed instant, never `utcnow()`: every assertion below is a statement about
# the calendar, and an anchor that moves would turn a config regression into a
# flake and a flake into a config regression (gotcha: test anchors must not
# branch on the clock).
NOW = datetime(2026, 9, 22, 12, 0, tzinfo=timezone.utc)


def test_ryder_cup_gets_its_real_2027_window():
    """The ship. RED on base: both dates are None without the fill."""
    rows = [{"key": "ryder_cup", "name": "Ryder Cup"}]
    _fill_dates_from_calendar(rows, NOW)

    assert rows[0]["start_date"] == "2027-09-17T00:00:00+00:00"
    assert rows[0]["end_date"] == "2027-09-19T00:00:00+00:00"


def test_the_attestation_travels_with_the_dates():
    """`approximate` is the calendar's own word for this row and must survive.

    The calendar's far-future editions are the sport's conventional window,
    refined when the real date is announced. A producer that serves the dates
    and drops the confidence has laundered a roadmap estimate into a fact.
    """
    rows = [{"key": "ryder_cup", "name": "Ryder Cup"}]
    _fill_dates_from_calendar(rows, NOW)

    assert rows[0]["date_confidence"] == "approximate"


def test_it_does_not_touch_the_two_fields_that_were_already_wrong():
    """The capture stamp and the market's resolution are left exactly alone.

    #1077 normalizes `resolution_date` onto a DataGolf end_date because a LIVE
    schedule earns that; a roadmap file does not, and the market really does
    resolve on 2027-09-30 — eleven days after the cup ends.
    """
    rows = [
        {
            "key": "ryder_cup",
            "name": "Ryder Cup",
            "commence_time": "2026-08-28T20:16:51+00:00",
            "resolution_date": "2027-09-30T14:00:00+00:00",
        }
    ]
    _fill_dates_from_calendar(rows, NOW)

    assert rows[0]["commence_time"] == "2026-08-28T20:16:51+00:00"
    assert rows[0]["resolution_date"] == "2027-09-30T14:00:00+00:00"


# --------------------------------------------------------------------------
# The three ways this could lie.
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "existing",
    [
        {"start_date": "2026-09-24T00:00:00+00:00", "end_date": "2026-09-27T00:00:00+00:00"},
        {"start_date": "2026-09-24T00:00:00+00:00"},  # start only
        {"end_date": "2026-09-27T00:00:00+00:00"},  # end only
    ],
)
def test_a_live_schedule_is_never_overruled(existing):
    """DataGolf outranks the roadmap. Either date present means hands off.

    The half-populated cases are the ones worth parametrizing: a fill that
    tested only `start_date` would quietly rewrite a row that had an end.
    """
    rows = [dict(key="ryder_cup", name="Ryder Cup", **existing)]
    _fill_dates_from_calendar(rows, NOW)

    for field, value in existing.items():
        assert rows[0][field] == value
    assert rows[0].get("date_confidence") is None


def test_a_finished_row_is_gone_before_the_fill_can_reach_it():
    """Property 2, asserted on the COMPOSITION, not on a comment.

    This is the regression that ordering prevents: a tournament the route's own
    staleness signals call finished must not be stamped back to life by a future
    calendar date. `the_open` is mapped, dateless, and long over — exactly the
    shape that would survive if the fill ran first.
    """
    rows = [
        {
            "key": "the_open",
            "name": "The Open",
            "resolution_date": "2026-07-19T00:00:00+00:00",
        }
    ]

    survivors = _filter_stale_tournaments(rows, NOW)
    assert survivors == [], "the filter should have dropped a tournament two months over"

    _fill_dates_from_calendar(survivors, NOW)
    assert survivors == [], "the fill resurrected a row the filter had removed"


def test_the_calendar_alone_cannot_stamp_a_past_edition():
    """Belt to the ordering's braces: the SOURCE also refuses.

    `next_edition` returns the soonest edition that has not finished, so The
    Open's only calendar row (2026-07-16 → 07-19) is unreachable from a 2026-09
    clock. Ordering and source agree rather than one covering for the other — if
    someone later moves the call site, this still holds.
    """
    rows = [{"key": "the_open", "name": "The Open"}]
    _fill_dates_from_calendar(rows, NOW)

    assert rows[0].get("start_date") is None
    assert rows[0].get("end_date") is None


def test_a_golf_card_cannot_borrow_another_sports_competition(monkeypatch):
    """The domain guard, exercised on the branch that must refuse.

    ⚠️ The obvious way to write this test does not test anything. Pointing the
    key at `us-open-tennis` — the live collision the register itself refuses to
    alias, because golf has a US Open too — passes with the domain guard
    DELETED: that competition's only edition ended on 2026-09-13, so
    `next_edition` returns None from this clock and the row keeps its nulls for
    a reason that has nothing to do with sport. Deleting the guard survived that
    version of this test.

    So the target has to be a non-golf competition with a FUTURE edition. The
    Tour de France's 2027 edition (2027-07-03 → 07-25) is one, and the assertion
    below it makes the instrument prove itself: if that edition is ever removed
    from the calendar this test says so instead of quietly going vacuous again.
    """
    monkeypatch.setitem(_TOURN_TO_COMPETITION_SLUG, "ryder_cup", "tour-de-france")

    # The control for the instrument: the refusal must be attributable to the
    # domain, so there has to be something here TO refuse.
    assert next_edition("tour-de-france", NOW) is not None, (
        "this test is vacuous unless the target competition has a future edition"
    )

    rows = [{"key": "ryder_cup", "name": "Ryder Cup"}]
    _fill_dates_from_calendar(rows, NOW)

    assert rows[0].get("start_date") is None, "a cycling date landed on a golf card"
    assert rows[0].get("end_date") is None
    assert rows[0].get("date_confidence") is None


def test_an_unmapped_tournament_is_left_alone():
    """The default. Most rows are ordinary tour events with DataGolf dates."""
    rows = [
        {"key": "nw_arkansas_championship_womens", "name": "Nw Arkansas Championship Womens"},
        {"key": "compliance_solutions_championship", "name": "Compliance Solutions Championship"},
    ]
    _fill_dates_from_calendar(rows, NOW)

    for row in rows:
        assert row.get("start_date") is None
        assert row.get("end_date") is None
        assert row.get("date_confidence") is None


def test_every_mapped_slug_resolves_to_a_golf_competition():
    """The map is ASSIGNED, so a typo in it is silent — this is what catches one.

    A key pointing at a slug the register does not hold fails open (the row
    keeps its null dates and nobody notices). Asserting resolution here turns
    that into a red test at the moment the line is written.
    """
    from app.utils.competition_identity import resolve_competition

    for tourn_key, slug in _TOURN_TO_COMPETITION_SLUG.items():
        row = resolve_competition(slug)
        assert row is not None, f"{tourn_key} -> {slug} is not in the register"
        assert row.get("domain") == "golf", f"{tourn_key} -> {slug} is not a golf competition"
