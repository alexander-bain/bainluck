"""#9399 — a Polymarket leg whose every price we refuse must not keep a number its book refutes.

PILLAR: TRUTH. SHIP: the Discover card for a live hurricane stops naming a favorite
the venue has abandoned.

WHAT A READER SAW (production 2026-09-28 ~16:10Z). Discover page one, slot 24:
*How strong will Nolo be? — New favorite: Category 5 (92%)*, and
``/api/futures/62233677`` agreed: Category 5 92% · Category 4 72% on a single-winner
field (Gamma event 1075583, ``negRisk: true``).

WHAT THE VENUE SAID (Gamma ``/events/1075583``, same minutes)::

    Category 4   outcomePrices 0.785   bid 0.65 / ask 0.92   last 0.72
    Category 5   outcomePrices 0.205   bid 0.09 / ask 0.32   last 0.92

WHY. Category 5's 0.205 is the midpoint of a 0.23-wide book, so
``is_fabricated_midpoint`` refuses it (#1578); its last trade 0.92 sits above its own
0.32 ask, so ``_last_trade_survives_own_book`` refuses that too (#7548). Both are
right. The resolver then returns ``None`` and both writers SKIP the leg, so the row
kept its 10:50Z 0.92 beside its 10:50Z 0.54/0.92 book — which no serve-time gate
can see through, because the stored book agrees with the stored price.

THE FIX. The writers now take the fresh book of every refused leg and withdraw the
stored price when that book prices it out (``book_refutes_price``, #5121's shipped
predicate). A stored price inside the current book is still left alone.
"""

from __future__ import annotations

import inspect

import pytest

from app.tasks import futures_price_refresh as fpr
from app.tasks import polymarket
from app.tasks.polymarket import _refused_leg_books, _withdraw_book_refuted_legs

CAT4 = "0xcat4"
CAT5 = "0xcat5"
CAT3 = "0xcat3"


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


def _cat5():
    """The specimen leg, verbatim from Gamma 2026-09-28 ~16:0xZ."""
    return _market(
        condition_id=CAT5,
        question="Will Hurricane Nolo reach Category 5?",
        outcome_prices=[0.205, 0.795],
        best_bid=0.09,
        best_ask=0.32,
        last_trade_price=0.92,
    )


def _cat4():
    """The control: a leg the resolver prices (its last trade survives its book)."""
    return _market(
        condition_id=CAT4,
        question="Will Hurricane Nolo reach Category 4?",
        outcome_prices=[0.785, 0.215],
        best_bid=0.65,
        best_ask=0.92,
        last_trade_price=0.72,
    )


def _cat3():
    return _market(
        condition_id=CAT3,
        question="Will Hurricane Nolo reach Category 3?",
        outcome_prices=[0.025, 0.975],
        best_bid=0.02,
        best_ask=0.03,
        last_trade_price=0.025,
    )


def _nolo(markets=None, neg_risk=True):
    from app.services.polymarket_api import PolymarketEvent

    return PolymarketEvent(
        id="1075583",
        title="How strong will Nolo be?",
        neg_risk=neg_risk,
        markets=markets if markets is not None else [_cat4(), _cat5(), _cat3()],
    )


class TestTheSpecimenIsNamed:
    def test_the_resolver_refuses_the_specimen_both_ways(self):
        """The premise, asserted rather than trusted: this is the refusal shape."""
        assert polymarket._resolve_market_probability(_cat5()) is None
        # Cat 4's 0.785 is a fabricated midpoint too (0.65/0.92), but its last
        # trade 0.72 is inside its book — the 0.72 production stores.
        assert polymarket._resolve_market_probability(_cat4()) == pytest.approx(0.72)

    def test_the_refused_leg_comes_back_with_its_fresh_book(self):
        assert _refused_leg_books(_nolo()) == {CAT5: (0.09, 0.32)}

    def test_it_is_exactly_the_leg_the_write_set_dropped(self):
        written = {od["external_id"] for od in polymarket._parent_outcome_data(_nolo())}
        assert written == {CAT4, CAT3}
        assert set(_refused_leg_books(_nolo())) == {CAT5}

    def test_a_leg_with_no_book_at_all_is_not_named(self):
        """Nothing to refute with — #4000's retirement owns that leg."""
        bare = _market(condition_id="0xbare", outcome_prices=[], best_bid=None,
                       best_ask=None, last_trade_price=None)
        assert _refused_leg_books(_nolo([_cat4(), bare])) == {}

    def test_non_negrisk_and_single_market_events_are_out_of_scope(self):
        assert _refused_leg_books(_nolo(neg_risk=False)) == {}
        assert _refused_leg_books(_nolo([_cat5()])) == {}


class _Result:
    def __init__(self, rows=(), rowcount=0):
        self._rows = list(rows)
        self.rowcount = rowcount

    def fetchall(self):
        return self._rows


class _StoredRowsSession:
    """Answers the withdrawal's SELECT with stored rows; records every UPDATE."""

    def __init__(self, rows):
        self.rows = rows
        self.updates: list[dict] = []

    async def execute(self, statement, params=None):
        sql = str(statement).lstrip().upper()
        if sql.startswith("SELECT"):
            return _Result(self.rows)
        if sql.startswith("UPDATE FUTURES_OUTCOMES"):
            self.updates.append(dict(statement.compile().params))
            return _Result(rowcount=1)
        raise AssertionError(f"unexpected statement: {sql[:80]}")


class TestTheWithdrawalDecides:
    async def test_the_specimen_is_withdrawn(self):
        session = _StoredRowsSession([(901, CAT5, 0.92)])
        n = await _withdraw_book_refuted_legs(session, 62233677, {CAT5: (0.09, 0.32)})
        assert n == 1
        (params,) = session.updates
        assert params["current_probability"] is None
        assert params["current_american_odds"] is None
        # compare-and-set: keyed on the row AND the value it read
        assert params["id_1"] == 901
        assert params["current_probability_1"] == pytest.approx(0.92)

    async def test_a_stored_price_inside_the_current_book_is_kept(self):
        """A skip is still a skip: 0.20 is supported by a 0.09/0.32 book."""
        session = _StoredRowsSession([(901, CAT5, 0.20)])
        n = await _withdraw_book_refuted_legs(session, 62233677, {CAT5: (0.09, 0.32)})
        assert n == 0 and session.updates == []

    async def test_a_price_the_bid_prices_out_from_below_is_withdrawn(self):
        """The predicate's mirror arm: you could sell into a 0.50 bid."""
        session = _StoredRowsSession([(901, CAT5, 0.10)])
        n = await _withdraw_book_refuted_legs(session, 62233677, {CAT5: (0.50, 0.80)})
        assert n == 1

    async def test_an_empty_book_refutes_nothing(self):
        """``book_refutes_price``'s carve-out: an ask of 1.0 cannot be exceeded."""
        session = _StoredRowsSession([(901, CAT5, 0.92)])
        n = await _withdraw_book_refuted_legs(session, 62233677, {CAT5: (0, 1)})
        assert n == 0 and session.updates == []

    async def test_an_empty_set_issues_no_statement(self):
        session = _StoredRowsSession([(901, CAT5, 0.92)])
        assert await _withdraw_book_refuted_legs(session, 62233677, {}) == 0
        assert session.updates == []

    def test_the_write_is_narrow(self):
        src = inspect.getsource(_withdraw_book_refuted_legs)
        values = src[src.index(".values(") :]
        assert "opening_probability" not in values
        assert "last_updated" not in values
        assert "is_winner=" not in values
        # graded / crowned rows are excluded in BOTH the read and the write
        assert src.count("is_winner.isnot(True)") == 2
        assert src.count("resolution_source.is_(None)") == 2
        assert "FuturesOutcome.market_id == futures_market_id" in src


class TestBothWritersAskTheQuestion:
    def test_the_hourly_poll_withdraws_after_the_write_and_before_the_rerank(self):
        src = inspect.getsource(polymarket._process_event_batch)
        retire = src.index("_retire_unpriced_legs(")
        withdraw = src.index("_withdraw_book_refuted_legs(")
        rerank = src.index("rerank_market_field_stmt(")
        assert retire < withdraw < rerank
        assert "_refused_leg_books(event)" in src[withdraw : withdraw + 200]

    async def test_the_fetch_hands_back_the_refused_books(self):
        class _Service:
            async def get_events_by_ids(self, ids):
                return [{"id": "1075583"}]

            def _parse_event(self, raw):
                return _nolo()

        refuted: dict = {}
        priced, _unpriced = await fpr._fetch_polymarket_prices(
            _Service(), ["1075583"], {}, refuted_out=refuted
        )
        assert {p["external_id"] for p in priced["1075583"]} == {CAT4, CAT3}
        assert refuted == {"1075583": {CAT5: (0.09, 0.32)}}

    async def test_the_fetch_keeps_its_two_tuple_for_existing_callers(self):
        class _Service:
            async def get_events_by_ids(self, ids):
                return [{"id": "1075583"}]

            def _parse_event(self, raw):
                return _nolo()

        out = await fpr._fetch_polymarket_prices(_Service(), ["1075583"])
        assert isinstance(out, tuple) and len(out) == 2

    def test_the_hourly_refresh_withdraws_after_the_write_and_before_the_rerank(self):
        src = inspect.getsource(fpr._refresh_stale_futures_prices)
        assert "refuted_out=refuted_by_event" in src
        write = src.index('"polymarket", priced, stats')
        withdraw = src.index("_withdraw_book_refuted_legs(")
        rerank = src.index("rerank_market_field_stmt(market[\"id\"])", withdraw)
        assert write < withdraw < rerank
        assert "refuted_by_event.get(event_id)" in src[withdraw : withdraw + 300]

    def test_both_summaries_report_the_counter_unconditionally(self):
        assert '"legs_withdrawn_book_refuted": 0' in inspect.getsource(fpr)
        assert '"legs_withdrawn_book_refuted": 0' in inspect.getsource(polymarket)
