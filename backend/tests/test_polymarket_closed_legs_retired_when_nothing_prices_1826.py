"""#1826: legs the venue CLOSED stop printing a price even when no sibling prices.

THE SPECIMEN, production 2026-10-01 ~11:05Z. ``/futures/63490287`` (*MLB Playoffs:
World Series Exact Matchup*, Polymarket event 1110298, negRisk, 37 legs). We
stored 16 of the legs, every one at ``current_probability 0.095`` on
``bid NULL / ask 0.19``. Those 16 are exactly the legs Gamma had closed and
resolved No (``closed: true``, ``outcomePrices ["0","1"]``, closedTime 07:03Z);
our last write was 06:15Z. The other 21 legs are open empty books (0.01 / 0.82)
the resolver refuses, so on the ``:50`` by-id refresh NOTHING in the field
priced, and ``_fetch_polymarket_prices`` dropped the event before #4000's
retirement could see it. The hourly poll would retire the legs, but its
newest-first 2,000-event window had already stopped reaching the event.

The rule: a field that prices nothing still retires the legs the venue itself
marked closed — and only those, because ``closed`` is the venue talking about
that leg in this payload, which a dark venue cannot do.
"""

from __future__ import annotations

import inspect

from app.tasks import futures_price_refresh as fpr

DEAD = ("0xraysCubs", "0xyankeesCubs", "0xredsoxBrewers")
OPEN = ("0xraysBrewers", "0xyankeesDodgers")


def _market(cid, *, closed, **kwargs):
    from app.services.polymarket_api import PolymarketMarket

    fields = {
        "condition_id": cid,
        "question": cid,
        "outcomes": ["Yes", "No"],
        "closed": closed,
    }
    fields.update(kwargs)
    return PolymarketMarket(**fields)


def _dead(cid):
    """A closed, resolved-No leg, verbatim shape from Gamma 2026-10-01."""
    return _market(cid, closed=True, outcome_prices=[0.0, 1.0],
                   best_bid=None, best_ask=0.19, last_trade_price=None,
                   volume_24h=405.0)


def _open_empty(cid):
    """An open leg with an empty book: refused, and quoted (a bid exists)."""
    return _market(cid, closed=False, outcome_prices=[0.415, 0.585],
                   best_bid=0.01, best_ask=0.82, last_trade_price=None)


def _event(markets, neg_risk=True):
    from app.services.polymarket_api import PolymarketEvent

    return PolymarketEvent(id="1110298", title="MLB Playoffs: World Series Exact Matchup",
                           neg_risk=neg_risk, markets=markets)


def _specimen():
    return _event([_dead(c) for c in DEAD] + [_open_empty(c) for c in OPEN])


class _Service:
    def __init__(self, event):
        self.event = event

    async def get_events_by_ids(self, ids):
        return [{"id": "1110298"}]

    def _parse_event(self, raw):
        return self.event


class TestTheFetchNamesTheClosedLegs:
    async def test_the_specimen_prices_nothing_and_hands_back_its_dead_legs(self):
        priced, unpriced = await fpr._fetch_polymarket_prices(
            _Service(_specimen()), ["1110298"], {}
        )
        assert "1110298" not in priced
        assert unpriced == {"1110298": list(DEAD)}

    async def test_an_open_unquoted_leg_is_not_named_when_nothing_prices(self):
        """The #4000 dark-venue gate stands for legs the venue did NOT close."""
        bare = _market("0xbare", closed=False, outcome_prices=[], best_bid=None,
                       best_ask=None, last_trade_price=None)
        _priced, unpriced = await fpr._fetch_polymarket_prices(
            _Service(_event([bare, _open_empty(OPEN[0])])), ["1110298"], {}
        )
        assert unpriced == {}

    async def test_a_closed_leg_with_a_trade_behind_it_is_not_named(self):
        traded = _dead("0xtraded")
        traded.last_trade_price = 0.4
        _priced, unpriced = await fpr._fetch_polymarket_prices(
            _Service(_event([traded, _open_empty(OPEN[0])])), ["1110298"], {}
        )
        assert unpriced == {}

    def test_out_of_scope_shapes_name_nothing(self):
        assert fpr._venue_closed_unpriced_legs(_event([_dead(c) for c in DEAD],
                                                      neg_risk=False)) == []
        assert fpr._venue_closed_unpriced_legs(_event([_dead(DEAD[0])])) == []

    async def test_a_venue_closed_event_still_takes_the_settled_branch(self):
        """All legs closed is VENUE_SETTLED, ahead of this rule — unchanged."""
        priced, unpriced = await fpr._fetch_polymarket_prices(
            _Service(_event([_dead(c) for c in DEAD])), ["1110298"], {}
        )
        assert priced == {"1110298": fpr.VENUE_SETTLED}
        assert unpriced == {}


class TestTheRefreshActsOnThem:
    def test_the_not_found_branch_retires_then_reranks(self):
        src = inspect.getsource(fpr._refresh_stale_futures_prices)
        branch = src.index("if priced is None:")
        end = src.index("written = await _write_prices(", branch)
        body = src[branch:end]
        retire = body.index("_retire_unpriced_legs(")
        rerank = body.index("rerank_market_field_stmt(")
        commit = body.index("await session.commit()")
        assert retire < rerank < commit
        assert "unpriced_by_event.get(event_id)" in body
        assert 'stats["not_found"] += 1' in body

    def test_the_counter_is_reported_unconditionally(self):
        assert '"legs_retired_venue_closed": 0' in inspect.getsource(fpr)
