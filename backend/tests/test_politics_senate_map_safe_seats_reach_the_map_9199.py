"""#9199 follow-up — the safest 2026 Senate seats reach the map.

THE READER'S VIEW (production, /politics at 390px, 2026-09-27 22:30Z, after
`396dc279` went live): the map was right for every state it painted — Illinois
blue, Mississippi red, no 2028 seats — but Rhode Island, Delaware, New Mexico
and West Virginia, all on the 2026 ballot, were still grey.

THE CAUSE is upstream of `_build_senate_map`, which is why the builder-level
tests in `test_politics_senate_map_reads_the_seat_9199.py` could not see it:

1. `get_politics` runs `should_exclude_from_featured` on every market before
   theming, and its `probability_extreme` arm (leader > 0.98) dropped RI
   (Kalshi 0.991 / Polymarket 0.993), DE (0.988) and WV (0.986).
2. `_classify_theme` files "New Mexico Senate winner?" under `international`
   (it reads "Mexico"), so NM never entered the `congressional` pool the map
   was built from.

So these tests drive the ROUTE's builder, `get_politics`, not the helper.

WHAT WOULD MAKE THIS FILE VACUOUS: a route that paints every state it is fed.
The controls say the map still refuses a SETTLED seat and a STALE seat, and
that the price cap still keeps a 99% seat off the page's cards.
"""

import json
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.routes.politics import get_politics

_NOW = datetime.now(timezone.utc)
# Offset from the clock, never a calendar date (gotcha #44): a fixed Nov-2026
# resolution goes stale a week after election day and fails every arm. Every
# specimen resolves in 30 days, and the Kalshi tickers carry that same cycle's
# year, so `_build_senate_map`'s nearest-cycle cut keeps them all on any clock.
_RESOLVES = _NOW + timedelta(days=30)
_YY = f"{(_RESOLVES.year - _RESOLVES.year % 2) % 100:02d}"


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


_next_id = iter(range(9_199_000, 9_199_999))


def _market(name, outcomes, external_id, source, resolution, *, settled=False):
    mid = next(_next_id)
    return SimpleNamespace(
        id=mid,
        name=name,
        external_id=external_id,
        source=source,
        category="news",
        llm_sport_category="politics",
        group_id=None,
        outcomes=[
            SimpleNamespace(
                id=mid * 10 + i,
                name=n,
                current_probability=p,
                probability_change_24h=0,
                rank=i + 1,
                is_winner=(i == 0) if settled else None,
                resolution_source="api_settlement" if settled else None,
            )
            for i, (n, p) in enumerate(outcomes)
        ],
        market_metadata={"shape": {"expected_winners": 1}} if settled else None,
        resolution_date=resolution,
        updated_at=_NOW,
        volume_24h=1000,
        image_url=None,
        hook_description=None,
        status="open",
    )


# Production rows, 2026-09-27 (names and prices as stored; dates offset).
RI_KALSHI = _market(
    "Rhode Island Senate winner?",
    [("Democratic party", 0.991), ("Republican party", 0.011)],
    f"SENATERI-{_YY}", "kalshi", _RESOLVES,
)
RI_POLY = _market(
    "Rhode Island Senate Election Winner",
    # Polymarket seat books carry more than two legs (placeholders, "Other"),
    # which is what lets a leaked row past `build_section`'s two-way 95% cut.
    [("Jack Reed (D)", 0.993), ("Raymond McKay (R)", 0.009), ("Other", 0.002)],
    "57668", "polymarket", _RESOLVES,
)
DE_KALSHI = _market(
    "Delaware Senate winner?",
    [("Democratic party", 0.988), ("Republican party", 0.012)],
    f"SENATEDE-{_YY}", "kalshi", _RESOLVES,
)
WV_POLY = _market(
    "West Virginia Senate Election Winner",
    [("Shelley Moore Capito (R)", 0.986), ("Rachel Fetty Anderson (D)", 0.011)],
    "57674", "polymarket", _RESOLVES,
)
NM_POLY = _market(
    "New Mexico Senate Election Winner",
    [("Ben Ray Luján (D)", 0.9695), ("Larry Marker (R)", 0.0185)],
    "57663", "polymarket", _RESOLVES,
)
# Painted before this change; must still be painted after it.
TX_POLY = _market(
    "Texas Senate Election Winner",
    [("James Talarico (D)", 0.605), ("Ken Paxton (R)", 0.395)],
    "57690", "polymarket", _RESOLVES,
)

# CONTROLS — the map's other gates still hold.
SETTLED_SEAT = _market(
    "Oregon Senate winner?",
    [("Democratic party", 0.995), ("Republican party", 0.005)],
    f"SENATEOR-{_YY}", "kalshi", _RESOLVES, settled=True,
)
STALE_SEAT = _market(
    "Kansas Senate winner?",
    [("Democratic party", 0.40), ("Republican party", 0.60)],
    f"SENATEKS-{_YY}", "kalshi", _NOW - timedelta(days=30),
)


async def _build(markets):
    db = AsyncMock()
    db.execute.return_value = _Result(markets)
    return await get_politics(db)


ALL = [RI_KALSHI, RI_POLY, DE_KALSHI, WV_POLY, NM_POLY, TX_POLY,
       SETTLED_SEAT, STALE_SEAT]


@pytest.mark.asyncio
class TestTheSafestSeatsReachTheMap:
    async def test_a_seat_above_the_featured_price_cap_is_painted(self):
        senate_map = (await _build(ALL))["themes"]["congressional"]["senate_map"]
        assert senate_map["RI"] == pytest.approx(99.2)
        assert senate_map["DE"] == pytest.approx(98.8)
        assert senate_map["WV"] == pytest.approx(1.1)

    async def test_a_seat_the_theme_calls_international_is_painted(self):
        senate_map = (await _build(ALL))["themes"]["congressional"]["senate_map"]
        assert senate_map["NM"] == pytest.approx(97.0)

    async def test_a_seat_painted_before_is_still_painted(self):
        senate_map = (await _build(ALL))["themes"]["congressional"]["senate_map"]
        assert senate_map["TX"] == pytest.approx(60.5)


@pytest.mark.asyncio
class TestTheMapsOtherGatesStillHold:
    async def test_a_settled_seat_is_not_painted(self):
        senate_map = (await _build(ALL))["themes"]["congressional"]["senate_map"]
        assert "OR" not in senate_map

    async def test_a_stale_seat_is_not_painted(self):
        senate_map = (await _build(ALL))["themes"]["congressional"]["senate_map"]
        assert "KS" not in senate_map

    async def test_the_price_cap_still_keeps_a_99_percent_seat_off_the_cards(self):
        """The exemption is the MAP's. A foregone race is still no card."""
        payload = await _build([RI_KALSHI, RI_POLY, TX_POLY])
        assert "RI" in payload["themes"]["congressional"]["senate_map"]
        served = json.dumps(
            {k: v for k, v in payload.items() if k != "updated_at"}, default=str
        )
        assert "Rhode Island Senate" not in served
