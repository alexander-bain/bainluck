"""Q428 — the tournament price refresh must write the BOOK it priced from.

═══ THE DEFECT, MEASURED IN PRODUCTION 2026-08-28 ═══

``_write_refreshed_prices`` is the only rail that keeps the US Open bracket grid
fresh (every 10 minutes, by condition id). It calls
``_resolve_market_probability`` — which reads ``best_bid``/``best_ask`` to decide
whether the number is a price at all — and then writes the number WITHOUT them:

    futures_outcomes   current_probability, current_american_odds, last_updated
    snapshot           probability, american_odds, captured_at

So the price moves every ten minutes while ``current_yes_bid`` /
``current_yes_ask`` stay frozen at whatever the last full poll left there, and
the snapshot — the permanent record — never gets a book at all. Measured:

    polymarket snapshots in a 3-hour window          24,284
      of those with NO book written                   8,080
      of THOSE that are the US Open ladder            8,076  (512 outcomes)
      of those that are anything else                     4

    US Open ladder outcome rows compared to their own stored book        328
      stored probability sits OUTSIDE its own stored [bid, ask]          181  (55%)

A row whose price is outside its own book is not a stale book, it is two
different observations wearing one timestamp. Everything downstream that judges
price quality from the stored book is therefore judging the wrong book on this
surface: ``is_fabricated_midpoint`` (#1578), ``classify_fabricated_book``
(UX-P011), and the wide-spread exclusion in ``precompute_calibration``. It is
also why the site cannot yet mark an illiquid cell as illiquid — Alex's ruling
of 2026-08-28 asks for exactly that, and the signal it needs is the column this
writer drops on the floor.

═══ WHY EXECUTION AND NOT SOURCE-READING ═══

Same reason as ``test_polymarket_under_snapshot_book_p097`` (CERT-403C finding
3): ``assert "current_yes_bid" in source`` passes against a line in a dead
branch, a second copy of the writer, or code after an early ``continue``.
Every assertion here reads bound parameters off a statement the shipping code
actually emitted.

RED-FIRST BY EXECUTION: at 0e2414cd every ``…carries the book`` test below fails
with the columns absent from the emitted statement.
"""

from __future__ import annotations

import contextlib
from datetime import datetime, timezone

import pytest
from sqlalchemy.dialects import postgresql

from app.services.polymarket_api import PolymarketMarket
from app.tasks.tournament_price_refresh import _write_refreshed_prices

YES_ID, NO_ID = 4001, 4002

#: Deliberately asymmetric and non-degenerate, so a mirrored value can never be
#: mistaken for the original: 1-0.62 = 0.38, 1-0.58 = 0.42, 1-0.60 = 0.40, and
#: all six numbers are distinct.
BID, ASK, LAST = 0.58, 0.62, 0.60


class _Result:
    """Permissive stand-in; answers every shape rather than only today's."""

    def __init__(self, rows=()):
        self._rows = list(rows)

    def all(self):
        return self._rows

    def fetchall(self):
        return self._rows

    def scalar_one(self):
        return YES_ID

    def scalar_one_or_none(self):
        return None

    def scalar(self):
        return None

    def first(self):
        return self._rows[0] if self._rows else None

    def scalars(self):
        return self

    @property
    def rowcount(self):
        return len(self._rows)

    def __iter__(self):
        return iter(self._rows)


class RecordingSession:
    """Records every statement handed to ``execute``."""

    def __init__(self, outcome_rows):
        self.statements: list[object] = []
        self._outcome_rows = outcome_rows

    async def execute(self, stmt, *args, **kwargs):
        self.statements.append(stmt)
        # The writer's only SELECT asks for this market's (id, name) rows.
        if getattr(stmt, "is_select", False):
            return _Result(self._outcome_rows)
        return _Result()

    async def commit(self):
        return None

    async def rollback(self):
        return None


def _bound(stmt) -> dict:
    return stmt.compile(dialect=postgresql.dialect()).params


def _arm(monkeypatch, outcome_rows) -> RecordingSession:
    session = RecordingSession(outcome_rows)

    @contextlib.asynccontextmanager
    async def _fake_session():
        yield session

    import app.tasks.base as base

    monkeypatch.setattr(base, "get_task_session", _fake_session)
    return session


def _market(**kw) -> PolymarketMarket:
    defaults = dict(
        condition_id="0xq428",
        question="Will Novak Djokovic advance to the Quarterfinals in "
                 "Men's Singles at the 2026 US Open?",
        outcomes=["Yes", "No"],
        outcome_prices=[0.60, 0.40],
        best_bid=BID,
        best_ask=ASK,
        last_trade_price=LAST,
        volume_24h=321.0,
        active=True,
    )
    defaults.update(kw)
    return PolymarketMarket(**defaults)


async def _run(monkeypatch, market=None, rows=None):
    rows = rows if rows is not None else [(YES_ID, "Yes"), (NO_ID, "No")]
    session = _arm(monkeypatch, rows)
    stats = {"outcomes_updated": 0, "snapshots_written": 0, "unpriced": 0}
    await _write_refreshed_prices(
        [market or _market()], stats, now=datetime(2026, 8, 28, 21, 30, tzinfo=timezone.utc)
    )
    return session, stats


def _by_table(session, name):
    out = []
    for stmt in session.statements:
        table = getattr(stmt, "table", None)
        if table is not None and table.name == name:
            out.append(_bound(stmt))
        else:
            entity = getattr(stmt, "entity_description", None)
            if isinstance(entity, dict) and entity.get("name") == name:
                out.append(_bound(stmt))
    return out


@pytest.mark.asyncio
class TestTheOutcomeRowCarriesTheBook:
    async def test_the_yes_update_writes_the_bid_and_ask_it_priced_from(
        self, monkeypatch
    ):
        session, _ = await _run(monkeypatch)
        updates = _by_table(session, "futures_outcomes")
        assert updates, "the writer emitted no futures_outcomes statement at all"
        yes = updates[0]
        assert yes["current_yes_bid"] == pytest.approx(BID)
        assert yes["current_yes_ask"] == pytest.approx(ASK)

    async def test_the_price_and_the_book_are_one_observation(self, monkeypatch):
        """The whole point. A price outside its own book is two moments."""
        session, _ = await _run(monkeypatch)
        yes = _by_table(session, "futures_outcomes")[0]
        assert (
            yes["current_yes_bid"]
            <= yes["current_probability"]
            <= yes["current_yes_ask"]
        )

    async def test_the_no_row_gets_the_mirrored_book_not_the_yes_one(
        self, monkeypatch
    ):
        """In a binary CLOB the two tokens share one book: a resting bid for No
        at q IS a resting ask for Yes at 1-q. ``complementary_book`` is the one
        implementation of that identity in this codebase and this writer uses
        it rather than restating it — CAL-P095 measured 493,415 Under/No legs
        with no book at all because a writer mentioned the columns on one leg
        and not the other."""
        session, _ = await _run(monkeypatch)
        updates = _by_table(session, "futures_outcomes")
        assert len(updates) == 2
        no = updates[1]
        assert no["current_yes_bid"] == pytest.approx(1 - ASK)
        assert no["current_yes_ask"] == pytest.approx(1 - BID)


@pytest.mark.asyncio
class TestTheSnapshotCarriesTheBook:
    async def test_the_yes_snapshot_records_bid_ask_and_last(self, monkeypatch):
        session, _ = await _run(monkeypatch)
        snaps = _by_table(session, "futures_odds_snapshots")
        assert snaps, "the writer emitted no snapshot at all"
        yes = snaps[0]
        assert yes["yes_bid"] == pytest.approx(BID)
        assert yes["yes_ask"] == pytest.approx(ASK)
        assert yes["last_price"] == pytest.approx(LAST)

    async def test_the_no_snapshot_records_the_mirrored_book(self, monkeypatch):
        session, _ = await _run(monkeypatch)
        no = _by_table(session, "futures_odds_snapshots")[1]
        assert no["yes_bid"] == pytest.approx(1 - ASK)
        assert no["yes_ask"] == pytest.approx(1 - BID)
        assert no["last_price"] == pytest.approx(1 - LAST)

    async def test_the_history_can_be_reconstructed(self, monkeypatch):
        """34,638 ladder snapshots in 12 hours carried a NULL book and that
        record is gone for good. Every snapshot this rail writes from now on
        must be self-describing."""
        session, _ = await _run(monkeypatch)
        for snap in _by_table(session, "futures_odds_snapshots"):
            assert snap["yes_bid"] is not None
            assert snap["yes_ask"] is not None


@pytest.mark.asyncio
class TestNothingIsInvented:
    """NULL-preserving in both directions (``complementary_book``'s contract).

    A fabricated ``0`` would read downstream as a real, empty book — ``bid > 0``
    is a liquidity test in four places — so a market that arrives with no book
    must leave with no book, not with zeros.
    """

    async def test_a_market_with_no_book_writes_no_book(self, monkeypatch):
        session, _ = await _run(
            monkeypatch,
            market=_market(best_bid=None, best_ask=None, last_trade_price=0.12,
                           outcome_prices=[0.12, 0.88]),
        )
        for row in _by_table(session, "futures_outcomes"):
            assert row["current_yes_bid"] is None
            assert row["current_yes_ask"] is None
        for snap in _by_table(session, "futures_odds_snapshots"):
            assert snap["yes_bid"] is None
            assert snap["yes_ask"] is None

    async def test_a_missing_last_trade_stays_missing_on_both_legs(
        self, monkeypatch
    ):
        session, _ = await _run(
            monkeypatch, market=_market(last_trade_price=None)
        )
        for snap in _by_table(session, "futures_odds_snapshots"):
            assert snap["last_price"] is None

    async def test_an_unpriced_market_writes_nothing_at_all(self, monkeypatch):
        """gotcha #21, forward-only: declining to price must SKIP, never NULL a
        stored price. A wide book with no trade in 24h is Q428's declined case."""
        session, stats = await _run(
            monkeypatch,
            market=_market(outcome_prices=[0.50, 0.50], best_bid=0.01,
                           best_ask=0.99, last_trade_price=0.17,
                           volume_24h=None),
        )
        assert stats["unpriced"] == 1
        assert _by_table(session, "futures_outcomes") == []
        assert _by_table(session, "futures_odds_snapshots") == []
