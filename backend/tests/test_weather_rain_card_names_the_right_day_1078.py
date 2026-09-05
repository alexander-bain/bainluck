"""ux/1078 (#3219) — the rain card names the day it actually prices.

The defect these pin, seen on production 2026-09-05 at 13:30Z: the NYC rain
card showed `Today / Sep 6 / 8%` on Saturday September 5. Every label was one
day late, because the row took its label from `resolution_date` — the moment
Kalshi SETTLES the question, 08:00Z, which is the morning AFTER the day priced.

    KXRAIN-26SEP05  "Where will it rain on Sep 5, 2026?"  resolves 2026-09-06 08:00Z
    KXRAIN-26SEP06  "Where will it rain on Sep 6, 2026?"  resolves 2026-09-07 08:00Z

So the fix reads the day out of the market's own ticker (gotcha #14) and never
out of the settlement column. The load-bearing assertion in this file is the
one that pins the day AGAINST a resolution_date that disagrees with it — a test
whose fixture has them equal cannot fail on this bug.
"""

from datetime import date, datetime, timedelta, timezone

import pytest

from app.routes.weather import _rain_day, get_rain


class _FakeOutcome:
    def __init__(self, external_id, name, prob):
        self.external_id = external_id
        self.name = name
        self.current_probability = prob
        self.probability_change_24h = None


class _FakeMarket:
    def __init__(self, external_id, name, resolution_date, outcomes):
        self.external_id = external_id
        self.name = name
        self.resolution_date = resolution_date
        self.outcomes = outcomes


def _daily(external_id, name, resolution_date, nyc_prob=0.21, leader_prob=0.81):
    """A live-shape multi-city daily rain event, NYC below the leader."""
    return _FakeMarket(
        external_id,
        name,
        resolution_date,
        [
            _FakeOutcome(f"{external_id}-MIA", "Miami", leader_prob),
            _FakeOutcome(f"{external_id}-NYC", "New York City", nyc_prob),
        ],
    )


class _FakeResult:
    def __init__(self, rows):
        self._rows = rows

    def scalars(self):
        return self

    def all(self):
        return self._rows


class _FakeSession:
    """Answers the daily query with `markets` and the monthly query with []."""

    def __init__(self, markets):
        self._markets = markets
        self._calls = 0

    async def execute(self, _query):
        self._calls += 1
        return _FakeResult(self._markets if self._calls == 1 else [])


# --------------------------------------------------------------------------
# _rain_day — the ticker is the authority
# --------------------------------------------------------------------------


def test_day_comes_from_the_ticker_not_the_settlement_column():
    """The whole bug in one assertion: the two disagree, the ticker wins."""
    m = _daily(
        "KXRAIN-26SEP06",
        "Where will it rain on Sep 6, 2026?",
        datetime(2026, 9, 7, 8, 0, tzinfo=timezone.utc),
    )
    assert _rain_day(m) == date(2026, 9, 6)
    # And explicitly NOT the day the settlement column would have produced.
    assert _rain_day(m) != m.resolution_date.date()


def test_legacy_binary_ticker_also_yields_its_own_day():
    m = _FakeMarket(
        "KXRAINNYC-26SEP06",
        "Will it rain in NYC on Sep 6, 2026?",
        datetime(2026, 9, 7, 8, 0, tzinfo=timezone.utc),
        [_FakeOutcome("KXRAINNYC-26SEP06-YES", "Yes", 0.4)],
    )
    assert _rain_day(m) == date(2026, 9, 6)


def test_falls_back_to_the_name_when_the_ticker_is_renamed():
    """A ticker rename must not silently empty the card."""
    m = _daily(
        "KXRAIN-SOMETHING-NEW",
        "Where will it rain on Sep 6, 2026?",
        datetime(2026, 9, 7, 8, 0, tzinfo=timezone.utc),
    )
    assert _rain_day(m) == date(2026, 9, 6)


def test_unreadable_day_is_none_never_the_settlement_date():
    """None drops the row. A wrong date is worse than a missing one (ux/1075)."""
    m = _daily(
        "KXRAIN-MYSTERY",
        "Where will it rain?",
        datetime(2026, 9, 7, 8, 0, tzinfo=timezone.utc),
    )
    assert _rain_day(m) is None


def test_impossible_ticker_date_does_not_raise():
    m = _daily(
        "KXRAIN-26FEB30",
        "Where will it rain?",
        datetime(2026, 9, 7, 8, 0, tzinfo=timezone.utc),
    )
    assert _rain_day(m) is None


def test_year_and_month_are_decoded_not_guessed():
    m = _daily(
        "KXRAIN-27JAN03",
        "Where will it rain on Jan 3, 2027?",
        datetime(2027, 1, 4, 8, 0, tzinfo=timezone.utc),
    )
    assert _rain_day(m) == date(2027, 1, 3)


# --------------------------------------------------------------------------
# get_rain — what the card actually receives
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_row_labels_are_the_priced_day_not_the_day_after():
    """The production specimen, exactly as it was stored on 2026-09-05."""
    markets = [
        _daily(
            "KXRAIN-26SEP05",
            "Where will it rain on Sep 5, 2026?",
            datetime(2026, 9, 6, 8, 0, tzinfo=timezone.utc),
            nyc_prob=0.08,
            leader_prob=0.995,
        ),
        _daily(
            "KXRAIN-26SEP06",
            "Where will it rain on Sep 6, 2026?",
            datetime(2026, 9, 7, 8, 0, tzinfo=timezone.utc),
            nyc_prob=0.21,
            leader_prob=0.805,
        ),
    ]
    out = await get_rain(_FakeSession(markets))
    daily = out["daily"]
    assert [d["date"] for d in daily] == ["Sep 5", "Sep 6"]
    assert [d["iso"] for d in daily] == ["2026-09-05", "2026-09-06"]
    # Sep 5 is a Saturday and Sep 6 a Sunday in 2026. Under the defect these
    # read Sun/Mon, because they were the settlement days.
    assert [d["day"] for d in daily] == ["Sat", "Sun"]
    # And the numbers are still NYC's, not the wettest city's (ux/1076).
    assert [d["prob"] for d in daily] == [8, 21]


@pytest.mark.asyncio
async def test_every_row_carries_an_iso_the_client_can_compare():
    """Without `iso` the card cannot tell which tile is today, so it must not
    be optional in practice — only in the type, for pre-ship cached payloads."""
    markets = [
        _daily(
            "KXRAIN-26SEP06",
            "Where will it rain on Sep 6, 2026?",
            datetime(2026, 9, 7, 8, 0, tzinfo=timezone.utc),
        )
    ]
    out = await get_rain(_FakeSession(markets))
    assert out["daily"]
    for row in out["daily"]:
        assert date.fromisoformat(row["iso"])


@pytest.mark.asyncio
async def test_a_market_whose_day_is_unreadable_is_dropped_not_mislabelled():
    markets = [
        _daily(
            "KXRAIN-MYSTERY",
            "Where will it rain?",
            datetime(2026, 9, 7, 8, 0, tzinfo=timezone.utc),
        )
    ]
    out = await get_rain(_FakeSession(markets))
    assert out["daily"] == []


@pytest.mark.asyncio
async def test_dedup_is_by_priced_day_not_by_settlement_day():
    """Two shapes answering the SAME day must still collapse to one row.

    Under the defect the dedup key was the settlement date; both keys move
    together here, so this pins that the new key still collapses the pair.
    """
    markets = [
        _daily(
            "KXRAIN-26SEP06",
            "Where will it rain on Sep 6, 2026?",
            datetime(2026, 9, 7, 8, 0, tzinfo=timezone.utc),
            nyc_prob=0.21,
        ),
        _FakeMarket(
            "KXRAINNYC-26SEP06",
            "Will it rain in NYC on Sep 6, 2026?",
            # Deliberately a DIFFERENT settlement instant for the same day —
            # the legacy series closed at a different hour. Keying on
            # resolution_date would emit two rows for one day.
            datetime(2026, 9, 7, 4, 0, tzinfo=timezone.utc),
            [_FakeOutcome("KXRAINNYC-26SEP06-YES", "Yes", 0.31)],
        ),
    ]
    out = await get_rain(_FakeSession(markets))
    assert len(out["daily"]) == 1
    assert out["daily"][0]["iso"] == "2026-09-06"


@pytest.mark.asyncio
async def test_a_row_is_never_labelled_with_tomorrows_date():
    """Property form, swept across a year — the label is never the settlement
    day, for any day of any month, including month and year boundaries."""
    day = date(2026, 1, 1)
    checked = 0
    while day < date(2027, 1, 1):
        ticker = f"KXRAIN-{day.strftime('%y%b%d').upper()}"
        settle = datetime.combine(
            day + timedelta(days=1), datetime.min.time(), tzinfo=timezone.utc
        ) + timedelta(hours=8)
        m = _daily(ticker, f"Where will it rain on {day}?", settle)
        assert _rain_day(m) == day, ticker
        checked += 1
        day += timedelta(days=1)
    assert checked == 365
