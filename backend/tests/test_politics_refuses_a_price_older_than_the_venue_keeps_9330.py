"""#9330 — /politics stops printing a March primary as a live card.

THE READER'S VIEW (production, /politics at 390px, 2026-09-28 07:56Z): in the
Congressional section, "Texas Senate primary: which counties will Paxton win?"
with LEADER Harris 6%, Denton 4%, Hays 1%, +5 more. The primary was
2026-03-03, and all eight legs were last written 2026-03-20, 191 days earlier.

WHY NO EXISTING GATE SAW IT: `status` is 'open' (gotcha #33),
`resolution_date` is the one-year backstop (2027-03-03), no leg is graded, and
there is no venue-settled stamp. Kalshi purged the markets before anything
could read a result, so the event answers with `markets: []`.
`market_reads_settled` can never fire on such a row.

These tests drive the ROUTE's builder, `get_politics`, like the #9199 file
does, because a helper that is never called does not raise. It just keeps
serving the card.

WHAT WOULD MAKE THIS FILE VACUOUS: a route that refuses every market with any
old leg, or every market without stamps. The controls pin the three that must
stay: a market with one fresh leg among old ones, a market just inside the
bound, and a market whose legs carry no stamp at all.
"""

import json
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.routes import politics as politics_module
from app.routes.politics import (
    _last_priced_before_the_venue_forgets,
    get_politics,
)
from app.utils.kalshi_retention import PROVABLY_PURGED_AGE_DAYS

_NOW = datetime.now(timezone.utc)
# Offsets from the clock, never calendar dates (gotcha #44). The specimen's
# backstop resolution is months ahead, as 2027-03-03 is today.
_BACKSTOP = _NOW + timedelta(days=156)
_SPECIMEN_PRICED = _NOW - timedelta(days=191)


class _Scalars:
    def __init__(self, items):
        self._items = items

    def all(self):
        return self._items

    def first(self):
        return self._items[0] if self._items else None

    def unique(self):
        return self


class _Result:
    def __init__(self, items):
        self._scalars = _Scalars(items)

    def scalars(self):
        return self._scalars

    def all(self):
        return self._scalars.all()

    def first(self):
        return self._scalars.first()


_next_id = iter(range(9_330_000, 9_330_999))


def _market(name, external_id, legs):
    """``legs`` is ``[(name, probability, last_updated), ...]``. A stamp of
    ``...`` leaves the attribute OFF the leg, the no-evidence shape."""
    mid = next(_next_id)
    outcomes = []
    for i, (n, p, stamp) in enumerate(legs):
        leg = SimpleNamespace(
            id=mid * 10 + i,
            name=n,
            current_probability=p,
            probability_change_24h=0,
            rank=i + 1,
            is_winner=False,
            resolution_source=None,
        )
        if stamp is not ...:
            leg.last_updated = stamp
        outcomes.append(leg)
    return SimpleNamespace(
        id=mid,
        name=name,
        external_id=external_id,
        source="kalshi",
        category="news",
        llm_sport_category="politics",
        group_id=None,
        outcomes=outcomes,
        market_metadata=None,
        resolution_date=_BACKSTOP,
        updated_at=_NOW,
        volume_24h=1000,
        image_url=None,
        hook_description=None,
        status="open",
    )


# The production specimen, legs and prices as stored (925648), stamps offset.
PAXTON = _market(
    "Texas Senate primary: which counties will Paxton win?",
    "KXPAXTONPRIMARYCOUNTIES-26",
    [
        ("Harris", 0.06, _SPECIMEN_PRICED),
        ("Denton", 0.035, _SPECIMEN_PRICED),
        ("Hays", 0.01, _SPECIMEN_PRICED),
        ("Tarrant", 0.01, _SPECIMEN_PRICED),
        ("Travis", 0.01, _SPECIMEN_PRICED),
        ("Hidalgo", 0.01, _SPECIMEN_PRICED),
        ("Dallas", 0.01, _SPECIMEN_PRICED),
        ("Bexar", 0.01, _SPECIMEN_PRICED),
    ],
)

# CONTROLS — each shares the specimen's shape and differs in ONE stamp fact.
ONE_FRESH_LEG = _market(
    "New York Governor: which counties will Kathy Hochul win?",
    "KXHOCHULCOUNTIES-26",
    [
        ("Albany", 0.40, _NOW - timedelta(days=191)),
        ("Erie", 0.30, _NOW - timedelta(hours=2)),
    ],
)
JUST_INSIDE = _market(
    "Ruben Gallego out as Senator?",
    "KXGALLEGOOUT-26",
    [
        ("Before Nov 3, 2026", 0.05,
         _NOW - timedelta(days=PROVABLY_PURGED_AGE_DAYS - 1)),
    ],
)
NO_STAMPS = _market(
    "How many Senate seats will Independents win in the Midterms?",
    "KXSENATEIND-26",
    [("At least 1", 0.23, ...), ("At least 2", 0.07, ...)],
)
# A naive (tz-less) stamp is read as UTC, not refused and not crashed on.
NAIVE_OLD = _market(
    "Georgia Senate primary: which counties will Collins win?",
    "KXCOLLINSCOUNTIES-26",
    [("Fulton", 0.20, (_NOW - timedelta(days=191)).replace(tzinfo=None))],
)


async def _served(markets):
    db = AsyncMock()
    db.execute.return_value = _Result(markets)
    payload = await get_politics(db)
    return json.dumps(
        {k: v for k, v in payload.items() if k != "updated_at"}, default=str
    )


@pytest.mark.asyncio
class TestTheSpecimenLeavesThePage:
    async def test_the_march_primary_is_not_served(self):
        served = await _served([PAXTON, ONE_FRESH_LEG, JUST_INSIDE, NO_STAMPS])
        assert "Paxton" not in served
        assert "Harris" not in served

    async def test_a_naive_old_stamp_is_refused_too(self):
        served = await _served([NAIVE_OLD, NO_STAMPS])
        assert "Collins" not in served


@pytest.mark.asyncio
class TestTheControlsStay:
    """Gotcha #43: the gate removes the dead card AND leaves live ones."""

    async def test_one_fresh_leg_keeps_the_market(self):
        served = await _served([PAXTON, ONE_FRESH_LEG])
        assert "Kathy Hochul" in served

    async def test_a_market_just_inside_the_bound_stays(self):
        served = await _served([PAXTON, JUST_INSIDE])
        assert "Ruben Gallego" in served

    async def test_legs_without_a_stamp_are_no_evidence(self):
        served = await _served([PAXTON, NO_STAMPS])
        assert "Independents" in served


class TestTheHelper:
    def test_the_specimen_is_past_the_bound(self):
        assert _last_priced_before_the_venue_forgets(PAXTON, _NOW) is True

    def test_the_freshest_leg_decides(self):
        assert _last_priced_before_the_venue_forgets(ONE_FRESH_LEG, _NOW) is False

    def test_the_bound_is_the_provable_purge_age(self):
        edge = _market("x", "KXEDGE-26", [
            ("a", 0.5, _NOW - timedelta(days=PROVABLY_PURGED_AGE_DAYS, seconds=1)),
        ])
        assert _last_priced_before_the_venue_forgets(edge, _NOW) is True
        assert _last_priced_before_the_venue_forgets(JUST_INSIDE, _NOW) is False

    def test_no_outcomes_is_no_evidence(self):
        empty = SimpleNamespace(outcomes=None)
        assert _last_priced_before_the_venue_forgets(empty, _NOW) is False

    def test_the_route_calls_the_gate_before_theming(self):
        """The gate must sit ABOVE the spotlight append and the theme filing
        (see the positional warning in `get_politics`), so a refused market
        cannot headline the page or reach the Senate map."""
        import inspect

        src = inspect.getsource(politics_module.get_politics)
        gate = src.index("_last_priced_before_the_venue_forgets(m, now)")
        assert gate < src.index("spotlight_eligible.append(m)")
        assert gate < src.index("senate_seat_markets.append(m)")
