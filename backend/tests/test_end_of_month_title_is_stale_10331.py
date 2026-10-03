"""#10331: "by end of <Month>" is a month deadline, and a past one is stale.

On Sat 10/3 /weather Featured led with "Where will a 6.0+ magnitude earthquake
occur by end of September? 100% · Likely" — Polymarket row 59953565, still
open, resolution_date 10-04. `is_title_implied_stale` read "by September 30"
and "in Sep 2026" but returned None for "end of September" (no day, no year),
the commonest Polymarket phrasing. The same helper gates Discover's feed and
the morning digest.
"""

from datetime import datetime, timezone

import pytest

from app.utils.market_staleness import infer_market_real_world_end, is_title_implied_stale

SPECIMEN = "Where will a 6.0+ magnitude earthquake occur by end of September?"
# The clock latency read the specimen at.
OCT_3 = datetime(2026, 10, 3, 12, 40, tzinfo=timezone.utc)


def test_the_specimen_is_stale_on_october_3():
    assert is_title_implied_stale(SPECIMEN, "weather", OCT_3) == (
        "stale_explicit_title_end_of_month"
    )


def test_the_period_ends_the_last_instant_of_the_named_month():
    end, reason, grace = infer_market_real_world_end(SPECIMEN, "weather", OCT_3)
    assert end == datetime(2026, 9, 30, 23, 59, 59, tzinfo=timezone.utc)
    assert (reason, grace) == ("explicit_title_end_of_month", 1)


@pytest.mark.parametrize(
    "now",
    [
        datetime(2026, 9, 15, tzinfo=timezone.utc),  # inside the window
        datetime(2026, 9, 30, 23, 0, tzinfo=timezone.utc),  # last hour
        datetime(2026, 10, 1, 12, 0, tzinfo=timezone.utc),  # inside the grace day
    ],
)
def test_an_open_window_is_not_stale(now):
    assert is_title_implied_stale(SPECIMEN, "weather", now) is None


@pytest.mark.parametrize(
    "title",
    [
        "Will a hurricane make US landfall by the end of September?",
        "Hottest day before end of Sept?",
        "Earthquake by END OF SEP.?",
    ],
)
def test_phrasing_variants_are_read(title):
    assert is_title_implied_stale(title, "weather", OCT_3) == (
        "stale_explicit_title_end_of_month"
    )


def test_a_month_with_a_year_keeps_its_existing_reading():
    # "end of September 2026" was already the month+year branch; unchanged.
    assert is_title_implied_stale(
        "Earthquake by end of September 2026?", "weather", OCT_3
    ) == "stale_explicit_title_month"


def test_a_month_with_a_day_keeps_its_existing_reading():
    assert is_title_implied_stale(
        "Earthquake by end of September 30?", "weather", OCT_3
    ) == "stale_explicit_title_date"


def test_a_yearless_month_long_past_means_the_next_one():
    # On Oct 3, "end of March" ended ~186 days ago — beyond the bare-date
    # look-back, so the title most plausibly means NEXT March: not stale.
    assert is_title_implied_stale("Recession by end of March?", "economics", OCT_3) is None
    # And in January, "end of December" is this coming December.
    january = datetime(2026, 1, 10, tzinfo=timezone.utc)
    assert is_title_implied_stale("Snow in NYC by end of December?", "weather", january) is None


def test_a_year_elsewhere_in_the_title_is_used_without_the_look_back():
    assert is_title_implied_stale(
        "2026 recession by end of March?", "economics", OCT_3
    ) == "stale_explicit_title_end_of_month"
    assert is_title_implied_stale(
        "2027 recession by end of March?", "economics", OCT_3
    ) is None


@pytest.mark.parametrize(
    "title",
    [
        "Box office weekend of September?",  # "weekend", not "end"
        "Will the strike end of its own accord?",
        "Best Picture winner?",
    ],
)
def test_no_month_deadline_is_not_read_as_one(title):
    assert infer_market_real_world_end(title, "entertainment", OCT_3) is None
