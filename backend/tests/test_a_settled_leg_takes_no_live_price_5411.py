"""#5411 — a settled contract has no live price, and the socket must say so.

WHY THIS FILE EXISTS. #5246 taught every reachable Kalshi *settlement* writer to
carry a terminal price: a contract the venue has resolved is worth exactly 1 or
0, so a beaten player stops showing a live number. Its production drain cleared
6,895 rows at 21:58Z on 2026-09-11.

**189 of them were re-priced within 55 minutes.** One contiguous burst,
22:48:36Z → 22:52:43Z, average 0.0904, all Kalshi. The cause was not a
settlement writer at all — it was this socket's price flush, which issued

    UPDATE futures_outcomes SET current_probability = :p WHERE id = :id

with no test of any kind. #5246 enforced the invariant **on entry and not on
update**, so the one writer that had never heard of settlement quietly undid it,
and the card went back to giving eliminated players a 1% chance.

THE SHIP: an eliminated player's price stays at 0 between polls instead of
drifting back to a residual bid.

── THE DISTINCTION THIS FILE EXISTS TO PIN ─────────────────────────────────

The refusal is keyed on the **tier-3 AUTHORITATIVE set**, never on
`resolution_source IS NOT NULL`, and that is the whole correctness of the fix
rather than a detail of it.

At the moment this was written, both live US Open women's finalists carried
`resolution_source = 'ungradeable_result'` — tier 1, a RETRACTION meaning the
venue never declared a side, explicitly reversible by evidence. Sabalenka 0.575
and Rybakina 0.425 summed to exactly 1.000: a perfect live pair. A guard that
refused every row with a non-NULL source would have **frozen the two rows on
that card that most needed to move**, and it would have passed any test that
only asked "does a settled row decline?".

So every test below runs in BOTH directions. A guard that refuses everything is
as wrong as no guard at all, and only the pair can tell them apart.

── WHY A REAL ENGINE ───────────────────────────────────────────────────────

There is no local Postgres in this sandbox (`pg_ctl` cannot create its lock
file), and asserting on a compiled statement's *text* would only prove the
clause is present, not that it selects the right rows — a grep in a costume.

So these tests capture the **real `Update` construct the real consumer emits**
(the same drive-the-real-consumer shape `test_ws_flush_retry_q491.py`
establishes) and then EXECUTE it against a real SQLite engine holding a real
row. SQLite implements `IS NOT DISTINCT FROM`, `NOT IN` and the nullable-column
semantics this guard turns on, so the operator survives verbatim and deleting
the clause changes what the engine does — which is the difference between this
file and a source scan.
"""

import json

import pytest
from sqlalchemy import create_engine, insert, select
from sqlalchemy.sql.dml import Update

import app.services.kalshi_ws as kalshi_svc
import app.tasks.kalshi_ws as kalshi_task
import app.tasks.live_blend_refresh as blend_mod
from app.models.models import FuturesOutcome
from app.utils.resolution_authority import (
    AUTHORITATIVE_SOURCES,
    GUESS_FAMILY_SOURCES,
    TERMINAL_SOURCES,
)

MARKET_ID = 7
EVENT_ID = 900
TICKER = "KXTEST-Y"
MARKET_EXT = "KXTEST"
OUTCOME_ID = 81

#: The price the socket streams: yes_bid 0.40 / yes_ask 0.44 → midpoint 0.42.
STREAMED = 0.42

#: What #5246 leaves on a settled loser. The value the leak overwrote.
SETTLED_PRICE = 0.0

SLATE = [
    [(MARKET_EXT, MARKET_ID, EVENT_ID)],
    [(TICKER, MARKET_ID, OUTCOME_ID)],
]

TICK = json.dumps({
    "type": "ticker",
    "msg": {
        "market_ticker": TICKER,
        "yes_bid_dollars": "0.40",
        "yes_ask_dollars": "0.44",
    },
})


# ---------------------------------------------------------------- fakes ----


class _Frames:
    def __init__(self, frames):
        self._frames = list(frames)

    async def send(self, _payload):
        return None

    def __aiter__(self):
        return self

    async def __anext__(self):
        if self._frames:
            return self._frames.pop(0)
        import asyncio

        await asyncio.sleep(3600)  # the recycle cancellation lands here
        raise StopAsyncIteration  # pragma: no cover


class _Result:
    def __init__(self, rows, rowcount=1):
        self._rows = rows
        self.rowcount = rowcount

    def all(self):
        return list(self._rows)


class _CapturingSession:
    """Replays the slate for SELECTs and KEEPS the price UPDATE construct.

    The construct, not its parameters: this file's whole question is which rows
    that statement's WHERE clause selects, and only the statement itself can be
    asked that.
    """

    def __init__(self, batches, captured, rowcount):
        self._batches = batches
        self._captured = captured
        self._rowcount = rowcount

    async def execute(self, stmt):
        if isinstance(stmt, Update):
            if stmt.table.name == "futures_outcomes":
                self._captured.append(stmt)
            return _Result([], rowcount=self._rowcount)
        return _Result(self._batches.pop(0) if self._batches else [])


class _NoopRefresher:
    def __init__(self, *_a, **_kw):
        pass

    async def refresh(self, event_ids):
        return None


async def _drive_the_socket(monkeypatch, rowcount=1):
    """Run the REAL consumer over one tick; return (captured stmts, stats)."""
    import websockets

    import app.tasks.base as task_base

    captured: list[Update] = []
    batches = [list(b) for b in SLATE]

    def _connect(*_a, **_kw):
        class _Ctx:
            async def __aenter__(self_inner):
                return _Frames([TICK])

            async def __aexit__(self_inner, *_exc):
                return False

        return _Ctx()

    class _SessionCtx:
        async def __aenter__(self):
            return _CapturingSession(batches, captured, rowcount)

        async def __aexit__(self, *_exc):
            return False

    monkeypatch.setenv("KALSHI_API_KEY_ID", "test-key")
    monkeypatch.setenv("KALSHI_RSA_PRIVATE_KEY", "test-secret")
    monkeypatch.setattr(kalshi_svc, "_load_rsa_key", lambda: object())
    monkeypatch.setattr(kalshi_svc, "_sign_ws_request", lambda _k, _i: {})
    monkeypatch.setattr(kalshi_task, "SUBSCRIPTION_REFRESH_SECONDS", 0.5)
    monkeypatch.setattr(kalshi_task, "PRICE_FLUSH_SECONDS", 0.02)
    monkeypatch.setattr(blend_mod, "LiveBlendRefresher", _NoopRefresher)
    monkeypatch.setattr(websockets, "connect", _connect)
    monkeypatch.setattr(task_base, "get_task_session", lambda *a, **kw: _SessionCtx())

    stats = await kalshi_task._run_kalshi_ws_consumer()
    return captured, stats


def _run_against_a_real_row(stmt, resolution_source, is_winner=False,
                            starting_price=SETTLED_PRICE):
    """Execute the captured statement on SQLite over ONE seeded row.

    Returns ``(rowcount, stored_price)``. The row carries the id the statement
    was built for, so the ONLY thing that can decide the outcome is the guard.
    """
    engine = create_engine("sqlite://")
    table = FuturesOutcome.__table__
    table.create(engine)
    with engine.begin() as conn:
        conn.execute(insert(table).values(
            id=OUTCOME_ID,
            market_id=MARKET_ID,
            external_id=TICKER,
            name="A Beaten Player",
            current_probability=starting_price,
            is_winner=is_winner,
            resolution_source=resolution_source,
        ))
        result = conn.execute(stmt)
        stored = conn.execute(
            select(table.c.current_probability).where(table.c.id == OUTCOME_ID)
        ).scalar_one()
    return result.rowcount, float(stored)


@pytest.fixture
async def price_update(monkeypatch):
    """The one real price UPDATE the real consumer emits for one real tick."""
    captured, _stats = await _drive_the_socket(monkeypatch)
    assert len(captured) == 1, (
        f"expected exactly one price UPDATE, captured {len(captured)} — the "
        "harness is not driving the path this file is about"
    )
    return captured[0]


# ------------------------------------------------------------- the ship ----


class TestASettledLegTakesNoLivePrice:
    """The refusal direction: a graded row keeps its terminal price."""

    @pytest.mark.parametrize("source", sorted(AUTHORITATIVE_SOURCES))
    async def test_every_authoritative_source_declines_the_write(
        self, price_update, source
    ):
        """The 189-row leak, one row at a time, across the WHOLE tier.

        Parametrized over the set itself rather than over `api_settlement`
        alone: the leak was measured on `api_settlement`, but a Polymarket CLOB
        settlement is the same class of truth and a guard naming one source
        would let the next one through.
        """
        rowcount, stored = _run_against_a_real_row(price_update, source)

        assert rowcount == 0, (
            f"the socket wrote a live price onto a {source} row — this is the "
            "#5411 leak: it re-priced 189 settled legs in 55 minutes"
        )
        assert stored == pytest.approx(SETTLED_PRICE), (
            f"a {source} leg is worth exactly 1 or 0; it now reads {stored}"
        )

    async def test_the_winner_leg_is_left_at_one(self, price_update):
        """The other direction of settlement, which is easy to forget.

        A settled market has a winner as well as losers, and the winner's
        terminal price is 1. The same live tick would drag it DOWN to 0.42.
        """
        rowcount, stored = _run_against_a_real_row(
            price_update, "api_settlement", is_winner=True, starting_price=1.0
        )

        assert rowcount == 0 and stored == pytest.approx(1.0), (
            f"the winner leg was re-priced to {stored}; a won contract is 1"
        )


class TestALiveLegStillMoves:
    """The permission direction. Without these, a guard that refuses every row
    passes the whole class above while breaking every card on the site."""

    async def test_an_ungraded_row_still_takes_the_price(self, price_update):
        """`resolution_source IS NULL` is the ordinary live row — the bulk of
        the book. If this fails, the socket has stopped working."""
        rowcount, stored = _run_against_a_real_row(
            price_update, None, starting_price=0.30
        )

        assert rowcount == 1 and stored == pytest.approx(STREAMED), (
            "an ungraded row must still take a live price; NOT IN (...) is "
            "NULL rather than TRUE for a NULL source, which would refuse the "
            "entire book"
        )

    @pytest.mark.parametrize("source", sorted(TERMINAL_SOURCES))
    async def test_a_terminal_row_still_takes_the_price(self, price_update, source):
        """THE SPECIMEN THAT MADE THIS THE HARD CASE.

        Both live US Open finalists carried `ungradeable_result` — tier 1, the
        venue has NOT called it. Refusing tier 1 would have frozen the two most
        important rows on the marquee card at a stale number, and the resulting
        page would have looked *more* broken, not less.
        """
        rowcount, stored = _run_against_a_real_row(
            price_update, source, starting_price=0.30
        )

        assert rowcount == 1 and stored == pytest.approx(STREAMED), (
            f"a {source} row is a retraction or a soft close, not a "
            "settlement — it is explicitly reversible by evidence and must "
            "keep taking live prices"
        )

    @pytest.mark.parametrize("source", sorted(GUESS_FAMILY_SOURCES))
    async def test_a_guessed_row_still_takes_the_price(self, price_update, source):
        """Tier 0 is the poison class: a live price is strictly better
        evidence than a heuristic, so it must never be protected."""
        rowcount, stored = _run_against_a_real_row(
            price_update, source, starting_price=0.30
        )

        assert rowcount == 1 and stored == pytest.approx(STREAMED), (
            f"a {source} guess must not shield a row from a real price"
        )


class TestTheRefusalIsCounted:
    """A refusal that cannot be seen is indistinguishable from a socket that
    stopped writing — "it returned" is not "it wrote" (gotcha #53)."""

    async def test_a_declined_write_is_counted_and_not_called_an_update(
        self, monkeypatch
    ):
        _captured, stats = await _drive_the_socket(monkeypatch, rowcount=0)

        assert stats["settled_declined"] == 1, stats
        assert stats["price_updates"] == 0, (
            f"a refused write was counted as a price update: {stats}"
        )

    async def test_a_landed_write_is_not_counted_as_declined(self, monkeypatch):
        """The non-vacuity partner: the counter must distinguish the two, not
        report every flush as a refusal."""
        _captured, stats = await _drive_the_socket(monkeypatch, rowcount=1)

        assert stats["settled_declined"] == 0, stats
        assert stats["price_updates"] == 1, stats
