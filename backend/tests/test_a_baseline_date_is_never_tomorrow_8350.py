"""#8350 — a "since <date>" sentence never names a day the reader has not reached.

Production, 2026-09-24 05:10Z (10:10pm PDT on Sep 23), `/discover` at 390px:
"Next Claude Opus released? — Down 18 points since Sep 24 — now 32% chance".
The baseline had been taken ~5h earlier, after 00:00Z, and
`format_baseline_date` printed its UTC day, which was still in the future for
every US reader.

"Down N points since D" is true only when the baseline falls on or after D in
the reader's calendar. So the day is read in the westernmost US zone: an Eastern
reader may see a date one day early (weaker, still true), but no reader from
Pacific to UTC+14 sees a date after their own.
"""

from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import pytest

from app.utils.feed_reasons import compose_binary_card_copy, format_baseline_date

UTC = timezone.utc
SPECIMEN_OPENED = datetime(2026, 9, 24, 0, 30, tzinfo=UTC)
SPECIMEN_NOW = datetime(2026, 9, 24, 5, 10, tzinfo=UTC)

READER_ZONES = (
    "America/Los_Angeles",
    "America/Denver",
    "America/Chicago",
    "America/New_York",
    "UTC",
    "Europe/London",
    "Asia/Tokyo",
)

_MONTHS = ("Jan", "Feb", "Mar", "Apr", "May", "Jun",
           "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")


def _parse(label: str, reference_year: int):
    """Turn "Sep 23" / "Dec 31, 2025" back into a date."""
    if ", " in label:
        month_day, year = label.split(", ")
        year = int(year)
    else:
        month_day, year = label, reference_year
    month, day = month_day.split(" ")
    return datetime(year, _MONTHS.index(month) + 1, int(day)).date()


def test_the_served_specimen_reads_the_readers_day_not_tomorrow():
    assert format_baseline_date(SPECIMEN_OPENED, now=SPECIMEN_NOW) == "Sep 23"


def test_the_served_specimen_caption_does_not_cite_sep_24():
    copy = compose_binary_card_copy(
        market_name="Next Claude Opus released?",
        highlight_reasons=["major_surprise"],
        affirmative_probability=0.32,
        rendered_affirmative_percent=32,
        top_surprise_change=-0.18,
        top_surprise_opened_at=SPECIMEN_OPENED,
        now=SPECIMEN_NOW,
    )

    assert copy.headline == "Down 18 points since Sep 23"
    assert copy.context_summary == "Down 18 points since Sep 23 — now 32% chance"
    assert "Sep 24" not in copy.reason


def test_the_year_is_judged_in_the_same_calendar_as_the_day():
    """A New Year's Eve evening baseline: no year while it is still that year, then 2025."""
    opened = datetime(2026, 1, 1, 3, 0, tzinfo=UTC)

    assert format_baseline_date(opened, now=datetime(2026, 1, 1, 6, 0, tzinfo=UTC)) == "Dec 31"
    assert format_baseline_date(opened, now=datetime(2026, 1, 1, 20, 0, tzinfo=UTC)) == "Dec 31, 2025"


def test_a_daytime_baseline_is_unchanged():
    """Control: only the hours where UTC runs ahead of Pacific move."""
    opened = datetime(2026, 9, 10, 18, 0, tzinfo=UTC)
    now = datetime(2026, 9, 24, 18, 0, tzinfo=UTC)

    assert format_baseline_date(opened, now=now) == "Sep 10"


def test_a_naive_baseline_is_still_read_as_utc():
    assert format_baseline_date(datetime(2026, 9, 24, 0, 30), now=SPECIMEN_NOW) == "Sep 23"


@pytest.mark.parametrize("zone", READER_ZONES)
def test_no_reader_from_pacific_eastward_is_shown_a_day_they_have_not_reached(zone):
    """Every half hour of a day, in each reader's calendar: printed day <= their day."""
    tz = ZoneInfo(zone)
    start = datetime(2026, 9, 23, 0, 0, tzinfo=UTC)
    checked = 0
    for step in range(48):
        opened = start + timedelta(minutes=30 * step)
        now = opened + timedelta(hours=1)
        printed = _parse(format_baseline_date(opened, now=now), now.year)
        readers_day = opened.astimezone(tz).date()
        assert printed <= readers_day, (zone, opened.isoformat(), printed)
        checked += 1
    assert checked == 48


def test_the_pacific_reader_sees_exactly_their_own_day():
    """Early is allowed for readers east of Pacific; a Pacific reader gets the exact day."""
    tz = ZoneInfo("America/Los_Angeles")
    start = datetime(2026, 9, 23, 0, 0, tzinfo=UTC)
    for step in range(48):
        opened = start + timedelta(minutes=30 * step)
        printed = _parse(format_baseline_date(opened, now=opened), opened.year)
        assert printed == opened.astimezone(tz).date()
