"""#10331 follow-up: a question about ONE named day leaves when the venue's day ends.

On Sat 10/3 at 14:00Z (7am Pacific) /weather still served "What will the
biggest earthquake be on October 2, 2026? 99%". `is_title_implied_stale` read
the date correctly but added a whole grace day on top of 23:59:59 UTC, so the
question stayed until 23:59:59 UTC on Oct 3 — 4:59pm Pacific the day after.

#10137 already narrowed the identical grace on dated ladder rungs to twelve
hours (`RUNG_GRACE_DAYS`): the venues' latest US deadline, Hawaii, closes the
day at 09:59Z, so twelve hours clears every one of them. A title date is the
same deadline with the same reason for a grace, so it now uses the same one.
"Week of" titles keep their seven days.
"""

from datetime import datetime, timezone

import pytest

from app.utils.market_staleness import (
    RUNG_GRACE_DAYS,
    infer_market_real_world_end,
    is_title_implied_stale,
)

SPECIMEN = "What will the biggest earthquake be on October 2, 2026?"
# The clock ux read the specimen at.
OCT_3_1400Z = datetime(2026, 10, 3, 14, 0, tzinfo=timezone.utc)


def test_the_specimen_is_stale_by_7am_pacific_the_next_day():
    assert is_title_implied_stale(SPECIMEN, "weather", OCT_3_1400Z) == (
        "stale_explicit_title_date"
    )


def test_a_title_date_uses_the_rung_grace():
    end, reason, grace = infer_market_real_world_end(SPECIMEN, "weather", OCT_3_1400Z)
    assert end == datetime(2026, 10, 2, 23, 59, 59, tzinfo=timezone.utc)
    assert (reason, grace) == ("explicit_title_date", RUNG_GRACE_DAYS)


@pytest.mark.parametrize(
    "now",
    [
        datetime(2026, 10, 2, 12, 0, tzinfo=timezone.utc),  # the day itself
        datetime(2026, 10, 3, 3, 59, tzinfo=timezone.utc),  # 11:59pm ET deadline
        datetime(2026, 10, 3, 9, 59, tzinfo=timezone.utc),  # Hawaii's day ends
        datetime(2026, 10, 3, 11, 59, tzinfo=timezone.utc),  # last grace minute
    ],
)
def test_the_day_is_not_withdrawn_while_any_us_clock_is_still_on_it(now):
    assert is_title_implied_stale(SPECIMEN, "weather", now) is None


def test_it_is_withdrawn_once_the_grace_has_run():
    now = datetime(2026, 10, 3, 12, 0, 1, tzinfo=timezone.utc)
    assert is_title_implied_stale(SPECIMEN, "weather", now) == (
        "stale_explicit_title_date"
    )


def test_week_of_keeps_its_seven_days():
    title = "#1 on the Billboard Hot 100 for the Week of Sep 26, 2026?"
    end, reason, grace = infer_market_real_world_end(
        title, "entertainment", OCT_3_1400Z
    )
    assert (reason, grace) == ("explicit_title_date", 7)
    assert is_title_implied_stale(title, "entertainment", OCT_3_1400Z) is None


def test_month_titles_are_unchanged():
    # Only the single-day reading moves; month-level titles keep their day.
    _, reason, grace = infer_market_real_world_end(
        "US Tornadoes in September 2026", "weather", OCT_3_1400Z
    )
    assert (reason, grace) == ("explicit_title_month", 1)
