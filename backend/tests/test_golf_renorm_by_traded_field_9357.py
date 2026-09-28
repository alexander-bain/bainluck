"""#9357 — a one-winner field is rescaled by the legs it aggregates, not by the offers it withholds.

THE SPECIMEN, production 2026-09-28 10:26Z. Kalshi market 62455818, "Alfred Dunhill
Links Championship Winner": 154 legs, 21 with a bid (summing 0.636) and 133 ask-only
~4.9¢ offers with no bid. The full priced field sums 6.861, so the route's factor was
1/6.861 and the golf hub's blend credited Kalshi with **Tommy Fleetwood 1.8%** while
Kalshi traded him at 12.5% (bid 12 / ask 13) — and the chart beside it drew 12.5%.

The ask-only legs were already withheld per outcome (CERT-450). What was wrong is that
they still sat in the SUM, so every real quote beside them was deflated ~7x.

THE GATE IS UNCHANGED. The full-field sum still decides whether a field is admitted
at all (#926 / #4402): a four-winner season market and an oversumming participation
market must stay refused however thin their traded legs are. The controls pin that,
because a fix that simply summed survivors everywhere would admit both.
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.routes.golf import get_golf


def _quote(oid, name, prob, bid, ask):
    return SimpleNamespace(
        id=oid,
        name=name,
        current_probability=prob,
        current_yes_bid=bid,
        current_yes_ask=ask,
        opening_probability=None,
        probability_change_24h=None,
    )


def _offer(oid, name, ask=0.049):
    """An ask-only leg as Kalshi serves it: nobody bids, the ask is the number."""
    return _quote(oid, name, ask, 0.0, ask)


def _market(mid, name, external_id, outcomes, *, mutually_exclusive):
    return SimpleNamespace(
        id=mid,
        name=name,
        source="kalshi",
        external_id=external_id,
        outcomes=outcomes,
        commence_time=None,
        resolution_date=None,
        status="open",
        llm_sport_category="golf",
        market_tier=1,
        market_metadata=None,
        mutually_exclusive=mutually_exclusive,
    )


#: The four traded legs of 62455818 at their real books, under 40 ask-only offers
#: (production had 133; 40 is enough to take the full sum well past 1.5).
DUNHILL_TRADED = [
    _quote(1, "Tommy Fleetwood", 0.125, 0.12, 0.13),
    _quote(2, "Matt Fitzpatrick", 0.0905, 0.087, 0.094),
    _quote(3, "Robert MacIntyre", 0.0705, 0.054, 0.087),
    _quote(4, "Tyrrell Hatton", 0.0675, 0.041, 0.094),
]
DUNHILL = _market(
    62455818,
    "Alfred Dunhill Links Championship Winner",
    "KXDPWORLDTOUR-ADLC26",
    DUNHILL_TRADED + [_offer(100 + i, f"Offer Golfer {i}") for i in range(40)],
    mutually_exclusive=True,
)

#: CONTROL A — an exclusive field whose TRADED legs alone oversum. It must still be
#: scaled, now by its own traded sum (1.91), not by traded + offers (1.91 + 0.49).
BRITISH_MASTERS = _market(
    59512401,
    "Husqvarna British Masters Winner",
    "KXDPWORLDTOUR-HBM26",
    [
        _quote(11, "Marco Penge", 0.55, 0.54, 0.56),
        _quote(12, "Daniel Hillier", 0.51, 0.50, 0.52),  # not 0.50: that is the untraded-mid placeholder
        _quote(13, "Tom McKibbin", 0.45, 0.44, 0.46),
        _quote(14, "Shaun Norris", 0.40, 0.39, 0.41),
    ]
    + [_offer(200 + i, f"Masters Offer {i}") for i in range(10)],
    mutually_exclusive=True,
)

#: CONTROL B — the #4402 four-winner season market, thinned: its traded legs sum
#: 1.0 (under 1.5) while offers take the full field past it. Refused before; must
#: stay refused — the gate reads the full field, not the survivors.
SEASON_MAJORS = _market(
    56775495,
    "Golfers to win a PGA Tour Major in 2027",
    "KXPGAMAJORWINNER-27",
    [
        _quote(21, "Scottie Scheffler", 0.565, 0.56, 0.57),
        _quote(22, "Rory McIlroy", 0.435, 0.43, 0.44),
    ]
    + [_offer(300 + i, f"Majors Offer {i}") for i in range(30)],
    mutually_exclusive=False,
)


@pytest.fixture
def golf_db():
    markets_result = MagicMock()
    markets_result.scalars.return_value.unique.return_value.all.return_value = [
        DUNHILL,
        BRITISH_MASTERS,
        SEASON_MAJORS,
    ]
    empty = MagicMock()
    empty.__iter__ = lambda self: iter(())

    session = AsyncMock()
    calls = {"n": 0}

    async def _execute(*_args, **_kwargs):
        calls["n"] += 1
        return markets_result if calls["n"] == 1 else empty

    session.execute.side_effect = _execute
    return session


@pytest.fixture(autouse=True)
def _no_schedule(monkeypatch):
    async def _empty():
        return []

    monkeypatch.setattr("app.routes.golf._get_golf_schedule", _empty)


def _tournament(body, needle):
    return next((t for t in body["tournaments"] if needle in t["name"]), None)


def _kalshi(tournament):
    return {g["name"]: g["sources"].get("kalshi") for g in tournament["golfers"]}


class TestTheSpecimen:
    async def test_fleetwood_is_credited_at_his_traded_price(self, golf_db):
        body = await get_golf(golf_db)
        dunhill = _tournament(body, "Dunhill")
        assert dunhill is not None, sorted(t["name"] for t in body["tournaments"])

        kalshi = _kalshi(dunhill)
        # Before #9357: 0.125 / (0.3535 + 40 * 0.049) = 0.054 — the withheld offers
        # deflating the real quote. The traded legs sum 0.3535 (<= 1.5): used as-is.
        assert kalshi["Tommy Fleetwood"] == pytest.approx(0.125, abs=0.001)
        assert kalshi["Matt Fitzpatrick"] == pytest.approx(0.0905, abs=0.001)

    async def test_the_offers_themselves_still_never_print(self, golf_db):
        body = await get_golf(golf_db)
        served = {g["name"] for g in _tournament(body, "Dunhill")["golfers"]}
        assert not any(n.startswith("Offer Golfer") for n in served)
        assert {"Tommy Fleetwood", "Matt Fitzpatrick", "Robert MacIntyre", "Tyrrell Hatton"} <= served


class TestTheGateIsUnchanged:
    async def test_CONTROL_an_oversumming_traded_field_is_still_scaled_down(self, golf_db):
        """The fix changes WHICH sum scales, never whether a >1.5 field is scaled."""
        body = await get_golf(golf_db)
        masters = _tournament(body, "Husqvarna")
        assert masters is not None
        # By the traded sum 1.91, not the old 1.91 + 10 * 0.049 = 2.40.
        assert _kalshi(masters)["Marco Penge"] == pytest.approx(0.55 / 1.91, abs=0.002)

    async def test_CONTROL_the_four_winner_season_market_stays_refused(self, golf_db):
        """Summing survivors in the GATE would admit this (traded sum 1.0) and put
        Scheffler's 56.5% under a tournament-winner heading. The gate reads the full
        field, so it is refused exactly as #4402 left it."""
        body = await get_golf(golf_db)
        assert _tournament(body, "Major") is None
        served = {g["name"] for t in body["tournaments"] for g in t.get("golfers", [])}
        assert "Scottie Scheffler" not in served
