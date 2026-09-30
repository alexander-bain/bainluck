"""#9934 — a held Polymarket price its own wide book has priced out is withdrawn.

Not a regression of #9913. #9913 stops a bad trade from ENTERING; this is a
price that STAYS after the book has moved away from it.

WHAT A READER SAW. ``/events/15321782`` (PHI @ ATL, Wild Card G2, Top 10th,
PHI 4–3, 2026-09-30 21:06Z, 390 px): the Polymarket series card (market
63348823) read Braves 93 / Phillies 8 while Kalshi read Atlanta 55.

STORED (db-query 21:07Z / 21:13Z). Braves 238779087 ``current_probability
0.925``, Phillies 238779088 ``0.075``, both written 20:34:20Z by the socket from
a 20:29:54Z Phillies print at 0.07498, made while ATL led 3–1.

VENUE (21:08Z). CLOB ``/book`` for the Braves token: bid 0.28, ask 0.91.
Nothing had printed since. ``handle_price`` refused the 63pp-wide book's
midpoint (#1578) and did nothing else with it, so 0.925 — above an ask anyone
could buy at — stayed on the page.

THE RULE is #9399's (withdraw a stored price the leg's current book prices out,
``book_refutes_price``), ported to the socket that saw the book.
"""

import inspect
import json
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
from sqlalchemy.sql.dml import Update

import app.tasks.polymarket_ws as poly_task
from app.tasks.polymarket_ws import (
    books_with_complements,
    withdraw_book_refuted_prices,
)
from tests.test_poly_ws_min_order_trade_9733 import (
    NO_LEG as PHILLIES_LEG,
    YES_LEG as BRAVES_LEG,
    YES_TOKEN as BRAVES_TOKEN,
    _run,
    _trade,
)
import tests.test_poly_ws_side1_leg_pairing_8403 as rig

SPECIMEN_BRAVES = 238779087
SPECIMEN_PHILLIES = 238779088
SPECIMEN_BOOK = (0.28, 0.91)  # Braves token, CLOB /book 21:08Z


def _book(token, bid, ask):
    return json.dumps(
        {
            "event_type": "best_bid_ask",
            "asset_id": token,
            "best_bid": bid,
            "best_ask": ask,
        }
    )


# ── the decision, against stored rows ─────────────────────────────────────


class _Result:
    def __init__(self, rows=()):
        self._rows = list(rows)

    def all(self):
        return list(self._rows)


class _StoredRowsSession:
    """Answers the SELECT with stored ``(id, price)`` rows; records each UPDATE."""

    def __init__(self, stored: dict):
        self.stored = stored
        self.updates: list[dict] = []

    async def execute(self, statement, params=None):
        sql = str(statement).lstrip().upper()
        if sql.startswith("SELECT"):
            return _Result(self.stored.items())
        if sql.startswith("UPDATE FUTURES_OUTCOMES"):
            compiled = dict(statement.compile().params)
            self.updates.append(compiled)
            return _Result([(compiled["id_1"], 63348823, None)])
        raise AssertionError(f"unexpected statement: {sql[:80]}")


class TestTheSpecimen:
    async def test_both_legs_of_the_series_card_are_withdrawn(self):
        """THE REGRESSION. Braves 0.925 sits above the 0.91 ask; Phillies 0.075
        sits below its complement book's 0.09 bid. Pre-fix both stayed."""
        books = {
            oid: (bid, ask)
            for oid, bid, ask in books_with_complements(
                [SPECIMEN_BRAVES], *SPECIMEN_BOOK, {SPECIMEN_BRAVES: SPECIMEN_PHILLIES}
            )
        }
        assert books == {
            SPECIMEN_BRAVES: (0.28, 0.91),
            SPECIMEN_PHILLIES: (pytest.approx(0.09), pytest.approx(0.72)),
        }
        session = _StoredRowsSession({SPECIMEN_BRAVES: 0.925, SPECIMEN_PHILLIES: 0.075})
        rows = await withdraw_book_refuted_prices(session, books)
        assert sorted(r[0] for r in rows) == [SPECIMEN_BRAVES, SPECIMEN_PHILLIES]
        for params in session.updates:
            assert params["current_probability"] is None
            assert params["current_american_odds"] is None
        # compare-and-set: keyed on the row AND the value it read
        assert {(p["id_1"], p["current_probability_1"]) for p in session.updates} == {
            (SPECIMEN_BRAVES, 0.925),
            (SPECIMEN_PHILLIES, 0.075),
        }


class TestWhatIsKept:
    async def test_a_held_price_inside_the_wide_book_is_kept(self):
        """A skip is still a skip: 0.60 is inside 0.28 / 0.91."""
        session = _StoredRowsSession({SPECIMEN_BRAVES: 0.60})
        assert (
            await withdraw_book_refuted_prices(
                session, {SPECIMEN_BRAVES: SPECIMEN_BOOK}
            )
            == []
        )
        assert session.updates == []

    async def test_the_half_cent_tolerance_is_the_shipped_one(self):
        """0.915 is the ask plus #5121's epsilon — not beyond it."""
        session = _StoredRowsSession({SPECIMEN_BRAVES: 0.915})
        assert (
            await withdraw_book_refuted_prices(
                session, {SPECIMEN_BRAVES: SPECIMEN_BOOK}
            )
            == []
        )

    async def test_an_empty_ask_side_refutes_nothing_above(self):
        """A blowout with the ask side cleared (ask 1.0) keeps its 0.98."""
        session = _StoredRowsSession({SPECIMEN_BRAVES: 0.98})
        assert (
            await withdraw_book_refuted_prices(session, {SPECIMEN_BRAVES: (0.60, 1.0)})
            == []
        )

    async def test_an_empty_set_issues_no_statement(self):
        session = _StoredRowsSession({SPECIMEN_BRAVES: 0.925})
        assert await withdraw_book_refuted_prices(session, {}) == []
        assert session.updates == []

    def test_the_write_is_narrow(self):
        src = inspect.getsource(withdraw_book_refuted_prices)
        values = src[src.index(".values(") :]
        assert "opening_probability" not in values
        assert "last_updated=" not in values
        assert "is_winner=" not in values
        # crowned / graded rows are excluded in BOTH the read and the write
        assert src.count("is_winner.isnot(True)") == 2
        assert src.count("resolution_source.is_(None)") == 2
        assert "book_refutes_price(bid, ask, float(stored))" in src


@pytest.mark.parametrize(
    "targets, bid, ask, complement_of, expected",
    [
        ([1], 0.28, 0.91, {}, [(1, 0.28, 0.91)]),
        ([1], 0.28, 0.91, {1: 2}, [(1, 0.28, 0.91), (2, 0.09, 0.72)]),
        # no bid → the complement's ask is 1.0, which nothing exceeds
        ([1], 0.0, 0.40, {1: 2}, [(1, 0.0, 0.40), (2, 0.6, 1.0)]),
        # a complement that is itself a target keeps its own book
        ([1, 2], 0.28, 0.91, {1: 2, 2: 1}, [(1, 0.28, 0.91), (2, 0.28, 0.91)]),
        ([], 0.28, 0.91, {1: 2}, []),
    ],
)
def test_books_with_complements(targets, bid, ask, complement_of, expected):
    got = books_with_complements(targets, bid, ask, complement_of)
    assert got == [(o, pytest.approx(b), pytest.approx(a)) for o, b, a in expected]


# ── the real consumer, socket and slate faked ─────────────────────────────


STAMP = datetime(2026, 9, 30, 20, 34, 20, tzinfo=timezone.utc)


async def _run_with_stored(monkeypatch, frames, stored, pushed):
    """The #9733 rig, whose session also answers the withdrawal's SELECT with
    the legs' stored prices (recognised by its columns, not by its turn)."""
    execute = rig._Session.execute

    async def _execute(self, stmt):
        columns = [
            getattr(c, "name", None) for c in getattr(stmt, "selected_columns", [])
        ]
        if columns == ["id", "current_probability"]:
            return rig._Result(list(stored.items()))
        result = await execute(self, stmt)
        params = stmt.compile().params if isinstance(stmt, Update) else {}
        if "current_probability" in params and params["current_probability"] is None:
            # the withdrawal's RETURNING row
            return rig._Result(
                [
                    SimpleNamespace(
                        id=params["id_1"], market_id=rig.MARKET_ID, last_updated=STAMP
                    )
                ]
            )
        return result

    monkeypatch.setattr(rig._Session, "execute", _execute)
    monkeypatch.setattr(
        poly_task, "queue_market_change", lambda _s, **kw: pushed.append(kw)
    )
    return await _run(monkeypatch, frames)


class TestTheSocketAsksTheQuestion:
    async def test_a_wide_book_withdraws_the_price_it_rules_out(self, monkeypatch):
        """End to end: the specimen's book arrives, the held 0.925 goes."""
        pushed = []
        writes, stats = await _run_with_stored(
            monkeypatch,
            [_book(BRAVES_TOKEN, "0.28", "0.91")],
            {BRAVES_LEG: 0.925},
            pushed,
        )
        assert writes == [(BRAVES_LEG, None)], writes
        assert stats["held_prices_withdrawn"] == 1, stats
        # the page is told, stamped with the row's own (unmoved) observation
        assert pushed == [
            {
                "market_id": rig.MARKET_ID,
                "source": "polymarket",
                "outcome_observed_at": {BRAVES_LEG: STAMP},
            }
        ], pushed

    async def test_the_wide_book_reaches_the_withdrawal(self, monkeypatch):
        seen = []

        async def _record(_session, books):
            seen.append(dict(books))
            return []

        monkeypatch.setattr(poly_task, "withdraw_book_refuted_prices", _record)
        await _run(monkeypatch, [_book(BRAVES_TOKEN, "0.28", "0.91")])
        assert seen == [{BRAVES_LEG: (0.28, 0.91)}], seen

    async def test_a_book_that_came_back_tight_clears_the_question(self, monkeypatch):
        """Its midpoint replaces the price; the old wide book no longer speaks."""
        seen = []

        async def _record(_session, books):
            seen.append(dict(books))
            return []

        monkeypatch.setattr(poly_task, "withdraw_book_refuted_prices", _record)
        writes, _ = await _run(
            monkeypatch,
            [_book(BRAVES_TOKEN, "0.28", "0.91"), _book(BRAVES_TOKEN, "0.30", "0.34")],
        )
        assert seen == [], seen
        assert writes == [(BRAVES_LEG, pytest.approx(0.32))], writes

    async def test_one_tokens_book_does_not_judge_the_other_leg(self, monkeypatch):
        """The rig proves no complement pair, so the Phillies leg is not asked."""
        seen = []

        async def _record(_session, books):
            seen.append(dict(books))
            return []

        monkeypatch.setattr(poly_task, "withdraw_book_refuted_prices", _record)
        await _run(monkeypatch, [_book(BRAVES_TOKEN, "0.28", "0.91")])
        assert all(PHILLIES_LEG not in books for books in seen), seen

    async def test_a_trade_inside_the_wide_book_is_written_then_kept(self, monkeypatch):
        """The price is written first, then judged as it now stands."""
        order = []

        async def _record(_session, books):
            order.append(("judge", dict(books)))
            return []

        monkeypatch.setattr(poly_task, "withdraw_book_refuted_prices", _record)
        writes, _ = await _run(
            monkeypatch,
            [_book(BRAVES_TOKEN, "0.28", "0.91"), _trade(BRAVES_TOKEN, "0.30", "20")],
        )
        assert writes == [(BRAVES_LEG, pytest.approx(0.30))], writes
        assert order == [("judge", {BRAVES_LEG: (0.28, 0.91)})], order


def test_the_withdrawal_count_reaches_the_minute_line(caplog):
    stats = {
        "price_updates": 0,
        "trade_updates": 0,
        "resolutions": 0,
        "errors": 0,
        "held_prices_withdrawn": 2,
    }
    blend = {"stamped": 0, "no_reading": 0, "throttled": 0, "errors": 0}
    with caplog.at_level("INFO", logger=poly_task.logger.name):
        poly_task._log_stats_line(stats, {}, blend)
    assert "held withdrawn=2" in caplog.text
