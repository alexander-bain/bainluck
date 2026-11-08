"""#12322 — a Polymarket market the venue lists with legs we cannot price keeps its outcome set.

Nov 7 2026: 3,859 open Polymarket rows held no outcomes at all, plus 594 holding one leg of a
field. Read at the venue the same evening, the legs were there and quoting, but with no trade
behind a wide book, so the gated resolver refuses every one ("Senegal vs. Sudan", event 1282307:
Senegal / Draw / Sudan, each 0.20 x 0.91, no trade). No outcome set means no shape, so no
grouping or comparison can place the market.

The fix records each listed leg as a placeholder with NO price (Kalshi's #3518 state):
insert-only, so an existing row's price is never touched.
"""

from __future__ import annotations

import contextlib

import pytest

from app.services.polymarket_api import PolymarketEvent, PolymarketMarket
from app.tasks import polymarket as poly
from tests.test_polymarket_under_snapshot_book_p097 import RecordingSession, _bound_params, _fresh_stats


def _leg(cid, title, *, prices=(0.555, 0.445), bid=0.2, ask=0.91, last=None, active=True, closed=False,
         outcomes=("Yes", "No"), question=None):
    return PolymarketMarket(condition_id=cid, question=question or f"Will {title} win?", group_item_title=title,
                            outcomes=list(outcomes), outcome_prices=list(prices), best_bid=bid, best_ask=ask,
                            last_trade_price=last, active=active, closed=closed, volume=1000.0)


def _senegal(**overrides):
    legs = overrides.pop("legs", None) or [
        _leg("0xsen", "Senegal"), _leg("0xdraw", "Draw (Senegal vs. Sudan)", prices=(0.145, 0.855), bid=0.04, ask=0.25),
        _leg("0xsud", "Sudan", prices=(0.265, 0.735), bid=0.04, ask=0.49),
    ]
    return PolymarketEvent(id="1282307", title="Senegal vs. Sudan", neg_risk=True, markets=legs, **overrides)


class TestWhichLegsArePlaceholders:
    def test_a_field_whose_every_leg_is_refused_records_all_three(self):
        event = _senegal()
        priced = poly._parent_outcome_data(event)
        assert priced == []  # control: the resolver refuses this book, as on the venue
        legs = poly._parent_placeholder_legs(event, priced)
        assert [(l["external_id"], l["name"]) for l in legs] == [
            ("0xsen", "Senegal"), ("0xdraw", "Draw (Senegal vs. Sudan)"), ("0xsud", "Sudan")]

    def test_a_partial_field_is_completed_and_priced_legs_are_not_repeated(self):
        legs = [_leg("0xa", "Alpha", prices=(0.6, 0.4), bid=0.59, ask=0.61, last=0.6), _leg("0xb", "Beta")]
        event = _senegal(legs=legs)
        priced = poly._parent_outcome_data(event)
        assert [od["external_id"] for od in priced] == ["0xa"]
        assert [l["external_id"] for l in poly._parent_placeholder_legs(event, priced)] == ["0xb"]

    def test_closed_or_inactive_children_are_not_listings(self):
        legs = [_leg("0xa", "Alpha", closed=True), _leg("0xb", "Beta", active=False), _leg("0xc", "Gamma")]
        assert [l["external_id"] for l in poly._parent_placeholder_legs(_senegal(legs=legs), [])] == ["0xc"]

    def test_a_single_yes_no_market_records_its_one_leg(self):
        m = _leg("0xnik", "", prices=(0.505, 0.5), bid=0.02, ask=0.98, question="Nikkei 225 (NIK) Up or Down on November 9?")
        event = PolymarketEvent(id="1324983", title="Nikkei 225 (NIK) Up or Down on November 9?", neg_risk=False, markets=[m])
        assert poly._parent_outcome_data(event) == []
        assert [(l["external_id"], l["name"]) for l in poly._parent_placeholder_legs(event, [])] == [("0xnik", "Yes")]

    def test_a_game_with_a_priced_moneyline_keeps_its_parent_exactly_as_today(self):
        ml = _leg("0xml", "", prices=(0.6, 0.4), bid=0.59, ask=0.61, last=0.6, question="A vs. B")
        prop = _leg("0xprop", "", question="Fight won by KO/TKO?")
        event = PolymarketEvent(id="9", title="A vs. B", neg_risk=False, markets=[ml, prop])
        priced = poly._parent_outcome_data(event)
        assert [od["external_id"] for od in priced] == ["0xml"]
        assert poly._parent_placeholder_legs(event, priced) == []


async def _write(monkeypatch, event) -> RecordingSession:
    from app.models.models import FuturesMarket, FuturesOddsSnapshot, FuturesOutcome
    from app.utils.market_label_normalization import compute_market_tier
    from app.utils.odds_math import probability_to_american
    from sqlalchemy.dialects.postgresql import insert as pg_insert

    session = RecordingSession()

    @contextlib.asynccontextmanager
    async def _fake_session():
        yield session

    monkeypatch.setattr(poly, "get_task_session", _fake_session)
    stats = _fresh_stats()
    stats["by_category"] = {}  # read with .get() on the non-sports path
    await poly._process_event_batch([event], stats, FuturesMarket, FuturesOutcome, FuturesOddsSnapshot,
                                    pg_insert, probability_to_american, compute_market_tier)
    assert not stats["errors"], stats["errors"]
    session.stats = stats
    return session


def _outcome_inserts(session):
    return [st for st in session.statements
            if getattr(getattr(st, "table", None), "name", None) == "futures_outcomes" and st.is_insert]


@pytest.mark.asyncio
async def test_the_writer_records_the_legs_with_no_price_insert_only(monkeypatch):
    session = await _write(monkeypatch, _senegal())
    rows = _outcome_inserts(session)
    params = [_bound_params(st) for st in rows]
    assert [p["name"] for p in params] == ["Senegal", "Draw (Senegal vs. Sudan)", "Sudan"]
    assert all(p["current_probability"] is None and p["is_winner"] is None for p in params)
    # insert-only: an existing row's price is the priced upsert's business, never this one's
    assert all(st._post_values_clause is not None and not getattr(st._post_values_clause, "update_values_to_set", None)
               for st in rows)
    assert session.stats["unpriced_legs_recorded"] == 3
    snaps = [st for st in session.statements if getattr(getattr(st, "table", None), "name", None) == "futures_odds_snapshots"]
    assert snaps == []  # no price, so no observation


@pytest.mark.asyncio
async def test_a_priced_field_writes_exactly_what_it_did_before(monkeypatch):
    legs = [_leg("0xa", "Alpha", prices=(0.6, 0.4), bid=0.59, ask=0.61, last=0.6),
            _leg("0xb", "Beta", prices=(0.4, 0.6), bid=0.39, ask=0.41, last=0.4)]
    session = await _write(monkeypatch, _senegal(legs=legs))
    params = [_bound_params(st) for st in _outcome_inserts(session)]
    assert sorted(p["name"] for p in params) == ["Alpha", "Beta"]
    assert all(p["current_probability"] is not None for p in params)
    assert "unpriced_legs_recorded" not in session.stats
