"""#9104: one "or above" leg must not turn a partition into a cumulative ladder.

Read at 390px on production 2026-09-27 ~09:00Z (/economics, Quarterly GDP card):

    US real GDP growth in 2036?
      0.0% or Below   2%   <- drawn as the winning bar
      0.1% to 0.5%    1%
      2.6% to 3.0%    1%
      3.6% to 4.0%    1%
      6.1%            1%

Kalshi `KXGDPYEAR-36` (market 57774191, stored 04:51Z) prices 1.6% to 2.0% at
22% and 2.1% to 2.5% at 17%; neither reached the card. Every section asked
``any("above" in name)``, the top tail reads "6.1% or Above", and the whole
range ladder went through ``_cumulative_to_discrete``, which differences
neighbours as if each row were P(above X).

The inflation card had the same defect on the September CPI combo: twelve
joint legs, six mentioning "or above", rendered as ONE leg at 1% against a
37.5% leader.

The fixtures below are the stored legs, verbatim. The controls are the two
all-threshold shapes that must stay cumulative: Kalshi's prefix ladder
("Above 1.0%", the Q3 GDP card) and the suffix ladder ("4,300 or above", #7827).
"""

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.routes.economics import (
    _cumulative_to_discrete,
    _reads_as_cumulative,
    get_economics,
)

FIXED_NOW = datetime(2026, 9, 27, 9, 0, tzinfo=timezone.utc)

# KXGDPYEAR-36, market 57774191, db-query 2026-09-27 ~09:10Z, id order.
GDP_2036 = [
    ("1.6% to 2.0%", 0.220), ("2.1% to 2.5%", 0.170), ("0.0% or Below", 0.060),
    ("1.1% to 1.5%", 0.035), ("2.6% to 3.0%", 0.045), ("0.6% to 1.0%", 0.030),
    ("3.1% to 3.5%", 0.020), ("0.1% to 0.5%", 0.040), ("3.6% to 4.0%", 0.025),
    ("5.1% to 5.5%", 0.010), ("5.6% to 6.0%", 0.010), ("4.1% to 4.5%", 0.010),
    ("6.1% or Above", 0.025), ("4.6% to 5.0%", 0.025),
]

# KXCPICOMBO-26SEP, market 61484986, same read.
CPI_COMBO = [
    ("Headline: 0.5% or above, Core: 0.3% or above", 0.375),
    ("Headline: 0.5% or above, Core: Exactly 0.2%", 0.370),
    ("Headline: 0.5% or above, Core: 0.1% or below", 0.070),
    ("Headline: Exactly 0.4%, Core: Exactly 0.2%", 0.030),
    ("Headline: Exactly 0.4%, Core: 0.3% or above", 0.020),
    ("Headline: Exactly 0.4%, Core: 0.1% or below", 0.040),
    ("Headline: 0.2% or below, Core: 0.1% or below", 0.010),
    ("Headline: 0.2% or below, Core: Exactly 0.2%", 0.010),
    ("Headline: 0.2% or below, Core: 0.3% or above", 0.010),
    ("Headline: Exactly 0.3%, Core: 0.1% or below", 0.010),
    ("Headline: Exactly 0.3%, Core: Exactly 0.2%", 0.010),
    ("Headline: Exactly 0.3%, Core: 0.3% or above", 0.010),
]

# KXGDP-26OCT30, market 12573791 — the CONTROL: a true cumulative ladder.
GDP_Q3 = [
    ("Above 1.0%", 0.935), ("Above 1.5%", 0.905), ("Above 2.0%", 0.850),
    ("Above 2.5%", 0.715), ("Above 0.0%", 0.995), ("Above 0.5%", 0.975),
    ("Above 3.0%", 0.695), ("Above 3.5%", 0.640), ("Above 4.0%", 0.375),
]

GOLD_SUFFIX = [("4,300 or above", 0.665), ("4,400 or above", 0.585), ("4,500 or above", 0.500)]


def _outcomes(legs):
    return [
        SimpleNamespace(id=i + 1, name=n, current_probability=p, rank=i + 1)
        for i, (n, p) in enumerate(legs)
    ]


def _market(mid, name, legs, external_id):
    return SimpleNamespace(
        id=mid, name=name, source="kalshi", external_id=external_id,
        outcomes=_outcomes(legs), status="open", llm_sport_category="economics",
        group_id=None, volume=1_000.0, resolution_date=None,
    )


async def _payload(markets):
    result_obj = MagicMock()
    result_obj.scalars.return_value.unique.return_value.all.return_value = list(markets)
    db = MagicMock()
    db.execute = AsyncMock(return_value=result_obj)
    with patch("app.routes.economics.datetime") as dt:
        dt.now.return_value = FIXED_NOW
        return await get_economics(db)


def _pool():
    return [
        _market(57774191, "US real GDP growth in 2036?", GDP_2036, "KXGDPYEAR-36"),
        _market(12573791, "US real GDP growth in Q3 2026?", GDP_Q3, "KXGDP-26OCT30"),
        _market(61484986, "September 2026 CPI MoM Combo · Headline & Core",
                CPI_COMBO, "KXCPICOMBO-26SEP"),
    ]


def _gdp(payload, mid):
    rows = [g for g in payload["themes"]["recession"]["gdp_quarters"] if g["market_id"] == mid]
    assert len(rows) == 1, f"market {mid} did not reach the GDP card exactly once"
    return rows[0]["dist"]


def _cpi(payload, mid):
    rows = [r for r in payload["themes"]["inflation"]["cpi_releases"] if r["market_id"] == mid]
    assert len(rows) == 1, f"market {mid} did not reach the inflation card exactly once"
    return rows[0]


class TestThePredicate:
    def test_a_range_ladder_with_an_above_tail_is_a_partition(self):
        assert _reads_as_cumulative(_outcomes(GDP_2036)) is False

    def test_the_cpi_combo_is_a_partition(self):
        assert _reads_as_cumulative(_outcomes(CPI_COMBO)) is False

    def test_control_a_prefix_ladder_stays_cumulative(self):
        assert _reads_as_cumulative(_outcomes(GDP_Q3)) is True

    def test_control_a_suffix_ladder_stays_cumulative(self):
        assert _reads_as_cumulative(_outcomes(GOLD_SUFFIX)) is True

    def test_control_a_ladder_without_above_keeps_its_old_path(self):
        """"At least" alone never took the cumulative path; it still does not."""
        legs = [("At least 370", 0.97), ("At least 400", 0.8), ("At least 450", 0.57)]
        assert _reads_as_cumulative(_outcomes(legs)) is False

    def test_the_strawman_is_what_production_ran(self):
        """The old test says True on both specimens — the defect, pinned."""
        for legs in (GDP_2036, CPI_COMBO):
            assert any("above" in n.lower() for n, _ in legs)


@pytest.mark.asyncio
class TestTheCards:
    async def test_the_2036_card_leads_with_kalshis_leader(self):
        dist = _gdp(await _payload(_pool()), 57774191)
        assert dist[0] == [22.0, "1.6% to 2.0%"]
        assert dist[1] == [17.0, "2.1% to 2.5%"]

    async def test_every_2036_number_is_a_stored_price(self):
        dist = _gdp(await _payload(_pool()), 57774191)
        stored = {n: round(p * 100, 1) for n, p in GDP_2036}
        assert len(dist) == len(GDP_2036)
        for prob, label in dist:
            assert stored[label] == prob, (label, prob)

    async def test_the_reported_rendering_does_not_reproduce(self):
        dist = _gdp(await _payload(_pool()), 57774191)
        assert [2.0, "0.0% or Below"] not in dist
        assert max(p for p, _ in dist) == 22.0

    async def test_the_combo_leads_with_its_375_leg(self):
        block = _cpi(await _payload(_pool()), 61484986)
        peak = block["brackets"][block["peakIs"]]
        assert peak == [37.5, "Headline: 0.5% or above, Core: 0.3% or above"]
        assert len(block["brackets"]) == len(CPI_COMBO)

    async def test_control_the_q3_ladder_is_still_differenced(self):
        dist = _gdp(await _payload(_pool()), 12573791)
        assert dist == _cumulative_to_discrete(_outcomes(GDP_Q3), max_buckets=6)
