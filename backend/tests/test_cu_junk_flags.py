import pytest

from app.utils.cu_junk_flags import cu_junk_flags


@pytest.mark.parametrize(
    "names",
    [
        ["At least 18.5%", "At least 23.5%", "At least 29%"],
        ["Above 2,200 shipments", "Above 3,500 shipments"],
        ["Category 2 or above", "Category 4 or above"],
        ["↓ €8", "↑ €13", "↑ €20"],
        ["Over $950k", "Over $1.2M", "Over $1.6M"],
        ["≥ −4°C", "≥ 0°C", "≥ 3°C"],
        ["1+ goal", "2+ goals"],
        ["1 vote or more", "11 votes or more"],
    ],
)
def test_repeated_comparisons_on_one_measure_are_ladders(names):
    assert cu_junk_flags(names, []) == ["ladder"]


@pytest.mark.parametrize(
    "names",
    [
        ["April 9th", "July 16"],
        ["Feb. 29, 2028", "2028-03-12"],
    ],
)
def test_distinct_calendar_dates_are_dated_buckets(names):
    assert cu_junk_flags(names, None) == ["dated_bucket"]


@pytest.mark.parametrize(
    "names",
    [
        ["San Francisco 49ers", "Philadelphia 76ers"],
        ["May Allison", "Ben Johnson III"],
        ["2-1", "Liverpool 3 - 0 Brighton", "0:0"],
        ["15", "25", "35"],
        ["10–20 inches", "20–30 inches"],
        ["Yes"],
        ["No"],
        ["Yes", "No"],
        ["Over 27.5", "Under 27.5"],
        ["Below $1m", "Below $1,000,000"],
        ["Over 12 points", "Over 25 yards"],
        ["Homes above 20", "Offices above 30"],
        ["May 7", "June 31"],
        ["May 7", "May 7th"],
        ["July 10", "None of the above"],
        ["Over 7", "Over 8", "Never"],
    ],
)
def test_near_misses_keep_only_model_flags(names):
    assert cu_junk_flags(names, ["duplicate_phrasing"]) == ["duplicate_phrasing"]


def test_model_flags_are_preserved_and_the_same_flag_is_not_added_twice():
    assert cu_junk_flags(["Over 48", "Over 52"], ["social_count", "dated_bucket"]) == [
        "social_count",
        "dated_bucket",
        "ladder",
    ]
    assert cu_junk_flags(["Over 48", "Over 52"], ["ladder", "social_count"]) == [
        "ladder",
        "social_count",
    ]
