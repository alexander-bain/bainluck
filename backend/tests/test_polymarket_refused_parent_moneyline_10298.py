"""#10298 — a game moneyline its own book refutes stops appearing as a trusted current price.

PILLAR: TRUTH. SHIP: a game moneyline refuted by its own book stops appearing as a
trusted current price.

WHAT A READER SAW. ``/futures/61040985`` (Lions–Packers, Oct 25) printed
"Packers 53%" while the card beside it said "Lions 56%". The independent
disposition reproduced the admitted failure shape on synthetic input:
``outcome_prices=[0.53, 0.47]`` over a 0.15/0.52 book. Anyone could buy at 0.52, so
0.53 was not a current price. **Production writer of 0.53: UNKNOWN.** These
controls establish the shape, not the production cause.

THE TWO CLAUSES (Authority contract C1 + Live's C2 decision, 2026-10-03):

* **C2** — in ``_parent_outcome_data``'s non-negRisk (game) branch, a raw
  ``outcome_prices[0]`` that its own same-payload book prices out
  (``book_refutes_price``, epsilon 0.005) is SKIPPED. It is never substituted by the
  last trade, the ask or the midpoint.
* **C1** — ``_refused_leg_books`` names every game leg that branch dropped while the
  venue served a book, so the unchanged ``_withdraw_book_refuted_legs`` withdraws a
  stored number that book refutes. "Refused" is computed from the branch's own
  output, so it means exactly "the branch that writes it dropped it".
"""

from __future__ import annotations

import inspect

import pytest

from app.tasks import polymarket
from app.tasks.polymarket import _parent_outcome_data, _refused_leg_books

ML = "0xlions_packers_ml"
SPREAD = "0xlions_packers_spread_5_5"
SPREAD_1H = "0xlions_packers_1h_spread_6_5"
TOTAL_2H = "0xlions_packers_2h_ou_20_5"


def _market(**kwargs):
    from app.services.polymarket_api import PolymarketMarket

    defaults = {
        "condition_id": "0xtest",
        "question": "Test?",
        "outcomes": ["Yes", "No"],
        "outcome_prices": [],
        "best_bid": None,
        "best_ask": None,
        "last_trade_price": None,
        "volume_24h": 5_000.0,
    }
    defaults.update(kwargs)
    return PolymarketMarket(**defaults)


def _moneyline(prices=(0.53, 0.47), bid=0.15, ask=0.52, last=0.53, **kw):
    """The specimen shape by default: raw 0.53 over a 0.15/0.52 book."""
    return _market(
        condition_id=ML,
        question="Lions vs. Packers",
        outcomes=["Packers", "Lions"],
        outcome_prices=list(prices),
        best_bid=bid,
        best_ask=ask,
        last_trade_price=last,
        **kw,
    )


def _side_legs():
    """The three spread/total legs the 10/3 LOOK saw beside the moneyline."""
    return [
        _market(condition_id=SPREAD, question="Spread: Packers (-5.5)",
                group_item_title="Spread -5.5", outcome_prices=[0.29, 0.71],
                best_bid=0.28, best_ask=0.30, last_trade_price=0.29),
        _market(condition_id=SPREAD_1H, question="1H Spread: Packers (-6.5)",
                group_item_title="1H Spread -6.5", outcome_prices=[0.50, 0.50],
                best_bid=0.49, best_ask=0.51, last_trade_price=0.50),
        _market(condition_id=TOTAL_2H, question="Packers 2H O/U 20.5",
                group_item_title="Packers 2H O/U 20.5", outcome_prices=[0.50, 0.50],
                best_bid=0.49, best_ask=0.51, last_trade_price=0.50),
    ]


def _game(moneyline=None, legs=None, neg_risk=False):
    from app.services.polymarket_api import PolymarketEvent

    markets = [moneyline or _moneyline()] + (_side_legs() if legs is None else legs)
    return PolymarketEvent(
        id="61040985", title="Lions vs. Packers", neg_risk=neg_risk, markets=markets,
    )


def _emitted(event) -> dict:
    return {od["external_id"]: od["prob"] for od in _parent_outcome_data(event)}


def _assert_refused_is_exactly_dropped(event, refused_fn):
    """Authority C1.3: a leg is refused exactly when the writing branch dropped it
    while the venue served a book."""
    written = set(_emitted(event))
    quoted = {
        m.condition_id for m in event.markets
        if m.condition_id and (m.best_bid is not None or m.best_ask is not None)
    }
    assert set(refused_fn(event)) == quoted - written


def _resolver_strawman(event) -> dict:
    """The predicate the contract forbids: ask the resolver which legs were refused."""
    return {
        m.condition_id: (m.best_bid, m.best_ask)
        for m in event.markets
        if m.condition_id
        and not (polymarket._resolve_market_probability(m) or 0) > 0
        and (m.best_bid is not None or m.best_ask is not None)
    }


class TestTheSpecimen:
    def test_raw_053_over_a_052_ask_is_not_emitted(self):
        """(f1) The moneyline is absent; the three side legs are not."""
        assert ML not in _emitted(_game())

    def test_and_it_is_named_refused_with_its_fresh_book(self):
        assert _refused_leg_books(_game()) == {ML: (0.15, 0.52)}

    def test_the_three_spread_total_legs_are_emitted_byte_identically(self):
        legs = _side_legs()
        out = _emitted(_game(legs=legs))
        for leg in legs:
            assert out[leg.condition_id] is leg.outcome_prices[0]

    def test_the_resolver_would_still_have_priced_it(self):
        """Why the refused set cannot ask the resolver: it admits the raw 0.53
        (the parked sibling, not in this ship)."""
        assert polymarket._resolve_market_probability_with_source(_moneyline()) == (
            pytest.approx(0.53), "outcome_prices",
        )


class TestSkipNeverSubstitute:
    def test_a_refuted_raw_price_does_not_fall_to_a_surviving_last_trade(self):
        """(f2) Raw 0.53 refuted, last 0.40 inside 0.15/0.52: still absent."""
        event = _game(_moneyline(last=0.40))
        assert polymarket._last_trade_survives_own_book(event.markets[0]) == 0.40
        assert ML not in _emitted(event)
        assert set(_refused_leg_books(event)) == {ML}

    def test_the_substitution_strawman_fails_this_guard(self):
        """A branch that routes the C2 refusal to the last trade would emit 0.40."""
        m = _moneyline(last=0.40)

        def substituting(market):
            prob = market.outcome_prices[0]
            if polymarket.book_refutes_price(market.best_bid, market.best_ask, prob):
                prob = polymarket._last_trade_survives_own_book(market)
            return prob

        assert substituting(m) == 0.40  # the strawman would print a number
        assert ML not in _emitted(_game(m))  # the branch does not

    def test_neither_the_ask_nor_the_midpoint_stands_in(self):
        out = _parent_outcome_data(_game(_moneyline(last=None)))
        assert all(od["external_id"] != ML for od in out)
        assert not any(od["prob"] in (0.52, 0.335) for od in out)


class TestWhatSurvives:
    def test_a_raw_price_inside_its_book_is_emitted_byte_identically(self):
        """(f3) 0.40 on 0.38/0.42."""
        m = _moneyline(prices=(0.40, 0.60), bid=0.38, ask=0.42, last=0.40)
        out = _emitted(_game(m))
        assert out[ML] is m.outcome_prices[0]
        assert ML not in _refused_leg_books(_game(m))

    @pytest.mark.parametrize("raw, emitted", [(0.525, True), (0.5251, False)])
    def test_the_ask_boundary_is_half_a_cent(self, raw, emitted):
        """(f4) 0.525 kept over a 0.52 ask; 0.5251 skipped."""
        m = _moneyline(prices=(raw, 1 - raw), bid=0.15, ask=0.52, last=None)
        assert (ML in _emitted(_game(m))) is emitted
        assert (ML in _refused_leg_books(_game(m))) is (not emitted)

    @pytest.mark.parametrize("raw, emitted", [(0.475, True), (0.4749, False)])
    def test_the_bid_mirror_is_half_a_cent(self, raw, emitted):
        """(f4) The bid arm: you could sell into a 0.48 bid."""
        m = _moneyline(prices=(raw, 1 - raw), bid=0.48, ask=0.90, last=None)
        assert (ML in _emitted(_game(m))) is emitted
        assert (ML in _refused_leg_books(_game(m))) is (not emitted)

    @pytest.mark.parametrize("bid, ask", [(0.96, None), (0.96, 1.0), (0, 1)])
    def test_a_book_that_bounds_nothing_refutes_nothing(self, bid, ask):
        """(f5) Gotcha #19: ask None or 1.0 cannot be exceeded; 0/1 is inert."""
        m = _moneyline(prices=(0.97, 0.03), bid=bid, ask=ask, last=0.97)
        assert _emitted(_game(m))[ML] == 0.97
        assert ML not in _refused_leg_books(_game(m))

    def test_a_blowout_wide_spread_still_prices_through_the_last_trade(self):
        """(f5) Gotcha #19: a stale midpoint over a wide book gives way to the trade."""
        m = _moneyline(prices=(0.50, 0.50), bid=0.02, ask=0.98, last=0.97)
        assert _emitted(_game(m))[ML] == 0.97

    def test_the_liquid_packers_062_control_is_emitted_and_not_refused(self):
        """Authority (c): the named-side liquid moneyline."""
        m = _moneyline(prices=(0.62, 0.38), bid=0.61, ask=0.63, last=0.62)
        rows = {od["external_id"]: od for od in _parent_outcome_data(_game(m))}
        assert rows[ML]["prob"] == 0.62
        assert _refused_leg_books(_game(m)) == {}


class TestMidpointControlsUnchanged:
    """(f6) #1578 / #6676 / #7548 behave as before inside the game branch."""

    def test_a_fabricated_midpoint_gives_way_to_a_trade_inside_its_book(self):
        m = _moneyline(prices=(0.335, 0.665), bid=0.15, ask=0.52, last=0.40)
        assert _emitted(_game(m))[ML] == 0.40

    def test_a_fabricated_midpoint_with_a_refuted_trade_is_dropped_and_refused(self):
        """#7548 then C1: the drop now reaches the refused set."""
        m = _moneyline(prices=(0.335, 0.665), bid=0.15, ask=0.52, last=0.90)
        assert ML not in _emitted(_game(m))
        assert _refused_leg_books(_game(m)) == {ML: (0.15, 0.52)}

    def test_an_empty_book_midpoint_with_no_trade_is_dropped(self):
        m = _moneyline(prices=(0.50, 0.50), bid=0.0, ask=1.0, last=None)
        assert ML not in _emitted(_game(m))
        # bid 0 / ask 1 is a book: the leg is named, and the writer's own
        # predicate refutes nothing against it (the 9399 file pins that arm).
        assert _refused_leg_books(_game(m)) == {ML: (0.0, 1.0)}


class TestOneDefinition:
    @pytest.mark.parametrize("moneyline", [
        _moneyline(),                                                   # C2
        _moneyline(last=0.40),                                          # C2, no substitution
        _moneyline(prices=(0.335, 0.665), last=0.90),                   # #7548
        _moneyline(prices=(0.40, 0.60), bid=0.38, ask=0.42, last=0.40),  # in book
        _moneyline(prices=(0.40, 0.60), bid=0, ask=0.99, last=None),    # resolver refuses
        _moneyline(prices=(), bid=0.30, ask=0.40, last=None),           # no raw price
        _moneyline(prices=(), bid=None, ask=None, last=None),           # no book
    ])
    def test_refused_is_exactly_what_the_branch_dropped(self, moneyline):
        _assert_refused_is_exactly_dropped(_game(moneyline), _refused_leg_books)

    @pytest.mark.parametrize("moneyline", [
        _moneyline(),                                                # resolver writes, branch drops
        _moneyline(prices=(0.40, 0.60), bid=0, ask=0.99, last=None),  # resolver drops, branch writes
    ])
    def test_the_resolver_strawman_fails_the_same_invariant(self, moneyline):
        with pytest.raises(AssertionError):
            _assert_refused_is_exactly_dropped(_game(moneyline), _resolver_strawman)

    def test_the_producer_reads_the_branch_not_the_resolver(self):
        src = inspect.getsource(_refused_leg_books)
        game_arm = src[src.index("elif market.condition_id in emitted"):]
        assert "_parent_outcome_data(event)" in src
        assert "_resolve_market_probability" not in game_arm


class TestScopeLimits:
    def test_a_no_book_game_leg_is_not_named(self):
        """#4000's retirement stays negRisk-only."""
        bare = _moneyline(prices=(), bid=None, ask=None, last=None)
        assert _refused_leg_books(_game(bare)) == {}

    def test_a_truncated_payload_names_nothing_it_did_not_carry(self):
        """The moneyline missing from this pass's payload is never inferred."""
        from app.services.polymarket_api import PolymarketEvent

        truncated = PolymarketEvent(
            id="61040985", title="Lions vs. Packers", neg_risk=False,
            markets=_side_legs(),
        )
        assert _refused_leg_books(truncated) == {}

    def test_a_leg_without_a_condition_id_is_not_named(self):
        m = _moneyline()
        m.condition_id = ""
        assert _refused_leg_books(_game(m)) == {}

    def test_the_key_is_the_legs_own_condition(self):
        refused = _refused_leg_books(_game())
        assert list(refused) == [ML]


class TestOtherShapesUntouched:
    def test_negrisk_still_emits_a_raw_value_its_book_refutes(self):
        """C2 is game-branch only: negRisk prices through the resolver, unchanged."""
        event = _game(neg_risk=True)
        out = _emitted(event)
        assert out[ML] == pytest.approx(0.53)
        assert ML not in _refused_leg_books(event)

    def test_negrisk_refused_set_is_still_the_resolvers(self):
        m = _moneyline(prices=(0.335, 0.665), last=0.90)
        event = _game(m, neg_risk=True)
        assert _refused_leg_books(event) == _resolver_strawman(event) == {ML: (0.15, 0.52)}

    def test_single_market_still_emits_and_refuses_nothing(self):
        from app.services.polymarket_api import PolymarketEvent

        event = PolymarketEvent(
            id="61040985", title="Lions vs. Packers", neg_risk=False,
            markets=[_moneyline()],
        )
        assert [od["prob"] for od in _parent_outcome_data(event)][0] == pytest.approx(0.53)
        assert _refused_leg_books(event) == {}


async def _fetch(event):
    from app.tasks import futures_price_refresh as fpr

    class _Service:
        async def get_events_by_ids(self, ids):
            return [{"id": event.id}]

        def _parse_event(self, raw):
            return event

    refuted: dict = {}
    priced, _unpriced = await fpr._fetch_polymarket_prices(
        _Service(), [event.id], {}, refuted_out=refuted
    )
    items = priced.get(event.id)
    return ({p["external_id"]: p for p in items} if isinstance(items, list) else {}), refuted


class TestTheRefreshFetchTagsTheParentRefusal:
    """The review's correction (2026-10-06): ``futures_price_refresh`` resolves the
    specimen to 0.53 through the unchanged resolver. The fetch keeps that item —
    decomposed ``_yes``/``_no`` rows price on it — and TAGS it, so the writer skips
    only the parent's bare row. The composed write/withdraw is proved against real
    Postgres in ``integration/test_polymarket_refused_leg_withdrawn_9399_real_postgres.py``."""

    async def test_the_specimen_is_kept_tagged_and_its_book_still_reaches_the_withdrawal(self):
        items, refuted = await _fetch(_game())
        assert items[ML]["probability"] == pytest.approx(0.53), "resolver unchanged"
        assert items[ML].get("parent_book_refused") is True
        assert refuted == {"61040985": {ML: (0.15, 0.52)}}

    async def test_the_emitted_legs_are_not_tagged(self):
        items, _ = await _fetch(_game())
        for cid in (SPREAD, SPREAD_1H, TOTAL_2H):
            assert "parent_book_refused" not in items[cid], cid

    async def test_a_moneyline_inside_its_book_is_not_tagged(self):
        items, refuted = await _fetch(_game(_moneyline((0.40, 0.60), 0.38, 0.42, 0.40)))
        assert "parent_book_refused" not in items[ML]
        assert refuted == {"61040985": {}}

    async def test_negrisk_is_never_tagged(self):
        items, _ = await _fetch(_game(neg_risk=True))
        assert not any("parent_book_refused" in i for i in items.values())

    async def test_a_single_market_game_is_never_tagged(self):
        from app.services.polymarket_api import PolymarketEvent

        event = PolymarketEvent(
            id="61040985", title="Lions vs. Packers", neg_risk=False,
            markets=[_moneyline()],
        )
        items, _ = await _fetch(event)
        assert not any("parent_book_refused" in i for i in items.values())
