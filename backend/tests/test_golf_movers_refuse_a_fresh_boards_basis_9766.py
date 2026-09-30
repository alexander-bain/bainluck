"""#9766 — a winner board whose ~24h-ago column is not a field gives no move.

THE SPECIMEN, production 2026-09-30 08:15Z. /golf's BIGGEST MOVERS (24H) was five
LOTTE Championship golfers, each "▼8–9 pts", none of whom had moved. The basis was
Kalshi market 63115883 ("LOTTE Championship presented by Hoakalei Winner", listed
9/28 22:50Z) as of now−23h = its 05:51Z 9/29 prints, when 105 of 117 legs sat at 9%+
and the column summed 10.573 — the same legs sum 1.387 today. Polymarket's LOTTE
board (63045538) had no write inside the window, so Kalshi's opening print was the
whole of each golfer's dated move.

The five named legs below carry their production values (current / bid / ask, and
the 05:51Z basis). The filler legs stand in for the other 111 at the same shape: a
fresh-board ~9% print over a filled ~1% book.

THE CONTROL is Bank of Utah's Kalshi winner board (63135268), whose basis column read
1.193 over 0.981 at the same instant — a real field. A golfer on it who genuinely
moved must stay a dated mover: a fix that dropped every Kalshi basis, or every basis
over some per-leg size, would take him off too.
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.routes import golf as golf_route
from app.routes.golf import (
    MOVE_BASIS_FIELD_CEILING,
    MOVE_BASIS_RESHAPE_RATIO,
    _basis_column_is_not_a_field,
    get_golf,
)


def _leg(oid, name, cur, bid, ask, change=0.0):
    return SimpleNamespace(
        id=oid,
        name=name,
        current_probability=cur,
        current_yes_bid=bid,
        current_yes_ask=ask,
        opening_probability=None,
        probability_change_24h=change,
    )


def _market(mid, name, source, external_id, outcomes):
    return SimpleNamespace(
        id=mid,
        name=name,
        source=source,
        external_id=external_id,
        outcomes=outcomes,
        commence_time=None,
        resolution_date=None,
        status="open",
        llm_sport_category="golf",
        market_tier=1,
        market_metadata=None,
        mutually_exclusive=True,
    )


# (outcome id, name, current, bid, ask, basis at 09-29 05:51Z) — production rows.
LOTTE_NAMED = [
    (237995975, "Auston Kim", 0.026, 0.0, 0.027, 0.120),
    (237996032, "Grace Kim", 0.008, 0.007, 0.009, 0.091),
    (237996020, "Hannah Green", 0.015, 0.0, 0.014, 0.091),
    (237996005, "In Gee Chun", 0.015, 0.0, 0.013, 0.091),
    (237996019, "Linn Grant", 0.010, 0.0, 0.009, 0.091),
    (237995988, "Jeeno Thitikul", 0.125, 0.12, 0.13, 0.140),
]
LOTTE_FILLER = [
    (238000000 + i, f"Filler Golfer{chr(65 + i // 26)}{chr(65 + i % 26)}", 0.008, 0.007, 0.009, 0.085)
    for i in range(110)
]
LOTTE_KALSHI = _market(
    63115883,
    "LOTTE Championship presented by Hoakalei Winner",
    "kalshi",
    "KXLPGATOUR-LOTCPBH26",
    [_leg(oid, n, c, b, a) for oid, n, c, b, a, _ in LOTTE_NAMED + LOTTE_FILLER],
)
# Polymarket's board: no basis in the window; its stored per-write changes are the
# production ones (0.0 / -0.0025 / -0.001), all under the 0.005 movers floor.
LOTTE_POLY = _market(
    63045538,
    "LPGA: LOTTE Championship Winner",
    "polymarket",
    "1098291",
    [
        _leg(238492704, "Auston Kim", 0.0285, 0.011, 0.046, -0.0025),
        _leg(238492721, "Grace Kim", 0.015, 0.001, 0.029, 0.0),
        _leg(238492713, "Hannah Green", 0.0175, 0.001, 0.034, -0.001),
        _leg(238492718, "Linn Grant", 0.0155, 0.001, 0.030, 0.0),
    ],
)

# CONTROL: a real field. One golfer moved 0.10 → 0.22; the rest held.
UTAH_MOVER = (1, "Ben Griffin", 0.22, 0.21, 0.23, 0.10)
UTAH_REST = [
    (10 + i, f"Utah Golfer{chr(65 + i)}", 0.05, 0.045, 0.055, 0.06) for i in range(15)
]
UTAH_KALSHI = _market(
    63135268,
    "Bank of Utah Championship Winner",
    "kalshi",
    "KXPGATOUR-BAOUC26",
    [_leg(oid, n, c, b, a) for oid, n, c, b, a, _ in [UTAH_MOVER] + UTAH_REST],
)

BASIS = {oid: basis for oid, *_rest, basis in LOTTE_NAMED + LOTTE_FILLER + [UTAH_MOVER] + UTAH_REST}


def _golf_db(markets):
    markets_result = MagicMock()
    markets_result.scalars.return_value.unique.return_value.all.return_value = markets
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
def _no_schedule_and_the_measured_basis(monkeypatch):
    async def _empty():
        return []

    async def _basis(_db, outcome_ids, _now):
        return {oid: BASIS[oid] for oid in outcome_ids if oid in BASIS}

    monkeypatch.setattr(golf_route, "_get_golf_schedule", _empty)
    monkeypatch.setattr(golf_route, "_fetch_24h_snapshots", _basis)


async def _body(markets):
    return await get_golf(db=_golf_db(markets))


def _golfer(body, tourn_needle, golfer):
    t = next(t for t in body["tournaments"] if tourn_needle in t["name"])
    return next(g for g in t.get("_all_golfers", t["golfers"]) if g["name"] == golfer)


def test_the_specimen_column_is_the_one_measured():
    named = [(c, b) for _o, _n, c, _bid, _ask, b in LOTTE_NAMED]
    filler = [(c, b) for _o, _n, c, _bid, _ask, b in LOTTE_FILLER]
    legs = named + filler
    assert sum(b for _, b in legs) > MOVE_BASIS_FIELD_CEILING
    assert sum(b for _, b in legs) > MOVE_BASIS_RESHAPE_RATIO * sum(c for c, _ in legs)
    assert _basis_column_is_not_a_field(legs)


class TestTheFreshBoardGivesNoMove:
    async def test_no_lotte_golfer_is_a_biggest_mover(self):
        body = await _body([LOTTE_KALSHI, LOTTE_POLY, UTAH_KALSHI])
        lotte = [m for m in body["biggest_movers"] if "LOTTE" in m["tournament_name"]]
        assert lotte == []

    @pytest.mark.parametrize("name", ["Auston Kim", "Grace Kim", "Linn Grant", "In Gee Chun", "Hannah Green"])
    async def test_the_named_golfers_carry_no_dated_move(self, name):
        body = await _body([LOTTE_KALSHI, LOTTE_POLY, UTAH_KALSHI])
        g = _golfer(body, "LOTTE", name)
        assert g["movement_is_dated"] is False
        assert g["movement_24h"] is None or abs(g["movement_24h"]) < 0.005

    async def test_the_board_still_prices_the_card(self):
        """The basis is refused, never the price: the card still shows Kalshi."""
        body = await _body([LOTTE_KALSHI, LOTTE_POLY, UTAH_KALSHI])
        g = _golfer(body, "LOTTE", "Jeeno Thitikul")
        assert g["sources"]["kalshi"] == pytest.approx(0.125)


class TestControlARealFieldStillMoves:
    async def test_the_utah_mover_is_a_dated_biggest_mover(self):
        body = await _body([LOTTE_KALSHI, LOTTE_POLY, UTAH_KALSHI])
        g = _golfer(body, "Bank of Utah", "Ben Griffin")
        assert g["movement_is_dated"] is True
        assert g["movement_24h"] == pytest.approx(0.12, abs=1e-3)
        assert body["biggest_movers"][0]["name"] == "Ben Griffin"

    async def test_without_the_guard_lotte_owned_the_movers(self, monkeypatch):
        """The BEFORE: with the column accepted, the five fake drops outrank the real move."""
        monkeypatch.setattr(golf_route, "_basis_column_is_not_a_field", lambda legs: False)
        body = await _body([LOTTE_KALSHI, LOTTE_POLY, UTAH_KALSHI])
        top = [m for m in body["biggest_movers"] if "LOTTE" in m["tournament_name"]]
        assert len(top) >= 4
        assert _golfer(body, "LOTTE", "Auston Kim")["movement_24h"] == pytest.approx(-0.094, abs=1e-3)


class TestTheRuleBothArms:
    def test_a_renormalized_field_on_both_days_is_kept(self):
        # 1.6 then, 1.7 now: over the field ceiling, not reshaped.
        assert not _basis_column_is_not_a_field([(0.85, 0.8), (0.85, 0.8)])

    def test_longshots_drifting_down_are_kept(self):
        # 0.05 → 0.02 per leg is a ratio of 2.5, but three legs cannot oversum a field.
        assert not _basis_column_is_not_a_field([(0.02, 0.05)] * 3)

    def test_the_measured_worst_real_field_is_kept(self):
        # odds_api Masters 2026-09-30: 1.628 over 1.078, the highest aggregated ratio.
        assert not _basis_column_is_not_a_field([(1.078, 1.628)])

    def test_no_basis_is_no_refusal(self):
        assert not _basis_column_is_not_a_field([])
