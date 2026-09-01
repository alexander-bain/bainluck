"""Q491 — a price that loses a database write must not be lost with it.

WHY THIS FILE EXISTS. Both sockets buffer prices and flush on a timer:

    async with buffer_lock:
        batch = dict(price_buffer)
        price_buffer.clear()      # <-- drained BEFORE the write
    try:
        ... write batch ...
    except Exception:
        stats["errors"] += 1
        return                    # <-- and the batch is gone

The drain happens before the write, so a failed write used to DISCARD the whole
batch. Nothing re-reads it: the buffer is only refilled when that market ticks
again, and 86.7% of open Polymarket markets never tick at all (only 13 of 42,945
tick more than once a minute). So one transient error — a statement_timeout, a
connection blip — froze a card on its old number for as long as the market
stayed quiet, which for most markets is forever.

Nor does the 2-minute REST poll cover it. `_poll_live_prediction_market_prices`
takes events that are live or commencing within **3 hours**; both sockets take
live or within **6 hours**. The 3h-6h band of the slate has the socket as its
ONLY price writer, so there is no second channel to heal the drop. And because
the lost write also carried `last_updated`, the frozen row reads as long-dead to
the liveness gates (#2024) rather than announcing itself.

THE SHIP: a live card's price survives a transient database error — it is
retried on the next flush instead of dropped.

THE RULE THE FIX MUST NOT BREAK: re-queuing uses `setdefault`, never `update`.
A fresher tick may have landed for the same outcome while the failed write was
in flight, and that newer price is the truth. Re-queuing must never resurrect a
stale price over it — that would turn a lost-price bug into a wrong-price bug,
which is worse. `test_a_fresher_tick_is_not_clobbered_by_the_requeue` is that
guard, and it is the non-vacuity partner for every test below.

Every test drives the REAL consumer over the REAL service, in the shape
`test_poly_ws_asset_outcome_map_q489.py` and `test_ws_recycle_cancellation_q460.py`
established. Only the socket, the slate query and the write outcome are faked.
"""

import asyncio
import json

import pytest
import websockets
from sqlalchemy.dialects import postgresql
from sqlalchemy.sql.dml import Update

import app.services.kalshi_ws as kalshi_svc
import app.tasks.kalshi_ws as kalshi_task
import app.tasks.live_blend_refresh as blend_mod
import app.tasks.polymarket_ws as poly_task

YES_TOKEN = "111"
NO_TOKEN = "222"
YES_OUTCOME_ID = 71
NO_OUTCOME_ID = 72
MARKET_ID = 7
CONDITION_ID = "0xabc"
EVENT_ID = 900

#: Same three-query slate the Q489 file documents: slate rows, market rows,
#: outcome rows.
POLY_SLATE = [
    [
        (YES_OUTCOME_ID, MARKET_ID, f"{CONDITION_ID}_yes", CONDITION_ID, EVENT_ID),
        (NO_OUTCOME_ID, MARKET_ID, f"{CONDITION_ID}_no", CONDITION_ID, EVENT_ID),
    ],
    [(MARKET_ID, CONDITION_ID, {"clob_token_ids": [YES_TOKEN, NO_TOKEN]})],
    [
        (YES_OUTCOME_ID, MARKET_ID, f"{CONDITION_ID}_yes"),
        (NO_OUTCOME_ID, MARKET_ID, f"{CONDITION_ID}_no"),
    ],
]

KALSHI_TICKER = "KXTEST-Y"
KALSHI_MARKET_EXT = "KXTEST"
KALSHI_OUTCOME_ID = 81

#: Kalshi issues two queries: market rows then outcome rows.
KALSHI_SLATE = [
    [(KALSHI_MARKET_EXT, MARKET_ID, EVENT_ID)],
    [(KALSHI_TICKER, MARKET_ID, KALSHI_OUTCOME_ID)],
]


# ---------------------------------------------------------------- fakes ----


class _Frames:
    """Streams frames, then goes quiet so the recycle timer stops the consumer.

    THE HANDSHAKE, and it is load-bearing. The fresher-tick guard needs the
    newer price to be in the buffer BEFORE the failed flush re-queues the stale
    one — otherwise the re-queue lands first, `handle_price` overwrites it a
    moment later, and the test passes whether the fix uses `setdefault` or a
    plain assignment. That is a vacuous guard, and the first draft of this file
    was one: the `setdefault -> price_buffer[...] = prob` mutation survived it.

    So the ordering is not raced, it is forced, in two steps:
      ``gate``  — set by the failing write; releases the fresher frame.
      ``ack``   — set by the NEXT ``__anext__`` call, which the consumer only
                  makes once it has finished dispatching the previous frame.
                  The failing write awaits it before raising.
    """

    def __init__(self, frames, gate=None, gated=(), ack=None):
        self._frames = list(frames)
        self._gate = gate
        self._gated = list(gated)
        self._ack = ack
        self._released = False

    async def send(self, _payload):
        return None

    def __aiter__(self):
        return self

    async def __anext__(self):
        if self._released and self._ack is not None:
            # The consumer came back for another frame, so `handle_price` has
            # returned and the fresher price is in the buffer.
            self._ack.set()
        if self._frames:
            return self._frames.pop(0)
        if self._gate is not None and self._gated:
            await self._gate.wait()
            self._released = True
            return self._gated.pop(0)
        await asyncio.sleep(3600)  # the recycle cancellation lands here
        raise StopAsyncIteration  # pragma: no cover


def _install_socket(monkeypatch, frames, gate=None, gated=(), ack=None):
    def _connect(*_a, **_kw):
        class _Ctx:
            async def __aenter__(self_inner):
                return _Frames(frames, gate, gated, ack)

            async def __aexit__(self_inner, *_exc):
                return False

        return _Ctx()

    monkeypatch.setattr(websockets, "connect", _connect)


class _Result:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return list(self._rows)


class _FlakySession:
    """Replays the slate for SELECTs; fails the first ``fail_writes`` price
    writes, then records every one that lands.

    Recording the compiled statement rather than a handler argument is
    deliberate, for the reason the Q489 file gives: the loss this file guards
    happens between the buffer and the write, so the assertion must read the
    write.
    """

    def __init__(self, batches, writes, budget, gate, ack=None):
        self._batches = batches
        self._writes = writes
        self._budget = budget
        self._gate = gate
        self._ack = ack

    async def execute(self, stmt):
        if isinstance(stmt, Update):
            params = stmt.compile(dialect=postgresql.dialect()).params
            if (
                stmt.table.name == "futures_outcomes"
                and "current_probability" in params
            ):
                if self._budget["fail_writes"] > 0:
                    self._budget["fail_writes"] -= 1
                    self._budget["failed"] += 1
                    # Release the fresher tick and WAIT for it to be buffered
                    # before failing — see `_Frames`. Without the wait the
                    # re-queue wins the race and the guard goes vacuous.
                    if self._gate is not None:
                        self._gate.set()
                        try:
                            await asyncio.wait_for(self._ack.wait(), timeout=5)
                        except asyncio.TimeoutError:  # pragma: no cover
                            raise AssertionError(
                                "the fresher frame was never dispatched; the "
                                "handshake this guard depends on did not run"
                            )
                    raise RuntimeError("simulated statement_timeout")
                self._writes.append(
                    (params["id_1"], params["current_probability"])
                )
            return _Result([])
        return _Result(self._batches.pop(0) if self._batches else [])


def _install_slate(monkeypatch, slate, writes, budget, gate=None, ack=None):
    import app.tasks.base as task_base

    batches = [list(b) for b in slate]

    class _Ctx:
        async def __aenter__(self):
            return _FlakySession(batches, writes, budget, gate, ack)

        async def __aexit__(self, *_exc):
            return False

    monkeypatch.setattr(task_base, "get_task_session", lambda *a, **kw: _Ctx())


class _NoopRefresher:
    """Q460's blend re-stamp has its own tests; here it would only add traffic
    to a test about whether the price survived."""

    def __init__(self, *_a, **_kw):
        pass

    async def refresh(self, event_ids):
        return None


def _poly_frame(event_type, asset_id, **kw):
    return json.dumps({"event_type": event_type, "asset_id": asset_id, **kw})


async def _run_poly(monkeypatch, frames, fail_writes=0, gated=(), flush=0.02,
                    recycle=0.5):
    """Drive the real Polymarket consumer to one planned recycle.

    ``flush`` well under ``recycle`` so the loop gets many attempts: the ship is
    "the price lands on a LATER flush", and the count of later flushes must not
    be what the assertion is balanced on.
    """
    writes: list[tuple[int, float]] = []
    budget = {"fail_writes": fail_writes, "failed": 0}
    gate = asyncio.Event() if gated else None
    ack = asyncio.Event() if gated else None

    monkeypatch.setattr(poly_task, "SUBSCRIPTION_REFRESH_SECONDS", recycle)
    monkeypatch.setattr(poly_task, "PRICE_FLUSH_SECONDS", flush)
    monkeypatch.setattr(blend_mod, "LiveBlendRefresher", _NoopRefresher)
    _install_socket(monkeypatch, frames, gate, gated, ack)
    _install_slate(monkeypatch, POLY_SLATE, writes, budget, gate, ack)

    stats = await poly_task._run_polymarket_ws_consumer()
    return writes, stats, budget


async def _run_kalshi(monkeypatch, frames, fail_writes=0, flush=0.02,
                      recycle=0.5):
    writes: list[tuple[int, float]] = []
    budget = {"fail_writes": fail_writes, "failed": 0}

    monkeypatch.setenv("KALSHI_API_KEY_ID", "test-key")
    monkeypatch.setenv("KALSHI_RSA_PRIVATE_KEY", "test-secret")
    # Same credential stub `test_ws_recycle_cancellation_q460.py` uses — this
    # file is about the flush, not about signing.
    monkeypatch.setattr(kalshi_svc, "_load_rsa_key", lambda: object())
    monkeypatch.setattr(kalshi_svc, "_sign_ws_request", lambda _k, _i: {})
    monkeypatch.setattr(kalshi_task, "SUBSCRIPTION_REFRESH_SECONDS", recycle)
    monkeypatch.setattr(kalshi_task, "PRICE_FLUSH_SECONDS", flush)
    monkeypatch.setattr(blend_mod, "LiveBlendRefresher", _NoopRefresher)
    _install_socket(monkeypatch, frames)
    _install_slate(monkeypatch, KALSHI_SLATE, writes, budget)

    stats = await kalshi_task._run_kalshi_ws_consumer()
    return writes, stats, budget


# ------------------------------------------------------------- the ship ----


class TestAFailedFlushKeepsThePrice:
    async def test_polymarket_price_lands_on_a_later_flush(self, monkeypatch):
        """THE REGRESSION. One tick, first write fails. Pre-fix the batch was
        dropped and `writes` stayed empty forever — the card kept its old
        number with no second channel to heal it."""
        writes, stats, budget = await _run_poly(
            monkeypatch,
            [_poly_frame("best_bid_ask", YES_TOKEN, best_bid="0.68", best_ask="0.72")],
            fail_writes=1,
        )

        assert budget["failed"] == 1, (
            "the test did not actually exercise a write failure; "
            f"budget={budget}"
        )
        assert writes == [(YES_OUTCOME_ID, pytest.approx(0.70))], (
            "a price whose write failed must be retried, not dropped; "
            f"got {writes}"
        )
        assert stats["errors"] == 1, stats
        assert stats["requeued"] == 1, (
            "`requeued` must count what was put back — `errors` alone cannot "
            f"distinguish a retried batch from a lost one; got {stats}"
        )

    async def test_kalshi_price_lands_on_a_later_flush(self, monkeypatch):
        """The same defect in the other socket. Both were written from the same
        template and both dropped the batch."""
        writes, stats, budget = await _run_kalshi(
            monkeypatch,
            [json.dumps({
                "type": "ticker",
                "msg": {
                    "market_ticker": KALSHI_TICKER,
                    "yes_bid_dollars": "0.40",
                    "yes_ask_dollars": "0.44",
                },
            })],
            fail_writes=1,
        )

        assert budget["failed"] == 1, budget
        assert writes == [(KALSHI_OUTCOME_ID, pytest.approx(0.42))], writes
        assert stats["errors"] == 1 and stats["requeued"] == 1, stats

    async def test_both_legs_of_a_failed_batch_come_back(self, monkeypatch):
        """A batch is not one price. Both legs of a binary tick inside one
        flush window; a dropped batch loses BOTH, so the retry must restore
        both — not just whichever the buffer happened to iterate first."""
        writes, stats, _ = await _run_poly(
            monkeypatch,
            [
                _poly_frame("best_bid_ask", YES_TOKEN, best_bid="0.68", best_ask="0.72"),
                _poly_frame("best_bid_ask", NO_TOKEN, best_bid="0.28", best_ask="0.32"),
            ],
            # One failure is enough: the first write raises out of the whole
            # `async with`, so BOTH legs of the batch are lost together. That
            # is precisely why the retry has to restore the batch, not a row.
            fail_writes=1,
        )

        assert dict(writes) == {
            YES_OUTCOME_ID: pytest.approx(0.70),
            NO_OUTCOME_ID: pytest.approx(0.30),
        }, writes
        assert len(writes) == 2, f"a leg was lost with the failed batch: {writes}"
        assert stats["errors"] == 1 and stats["requeued"] == 2, stats


class TestTheRetryNeverResurrectsAStalePrice:
    async def test_a_fresher_tick_is_not_clobbered_by_the_requeue(self, monkeypatch):
        """THE NON-VACUITY PARTNER, and the reason the fix uses `setdefault`.

        0.70 is buffered and its write fails. While that write was in flight a
        fresher 0.90 arrived for the SAME outcome. Re-queuing with `update`
        would overwrite 0.90 with the stale 0.70 and the card would render a
        price the market had already left — a worse bug than the one being
        fixed. The final write must be 0.90.

        The gate makes this deterministic: the fresher frame is not released
        until the failing write has actually failed.
        """
        writes, stats, budget = await _run_poly(
            monkeypatch,
            [_poly_frame("best_bid_ask", YES_TOKEN, best_bid="0.68", best_ask="0.72")],
            fail_writes=1,
            gated=[
                _poly_frame("best_bid_ask", YES_TOKEN, best_bid="0.88", best_ask="0.92")
            ],
        )

        assert budget["failed"] == 1, budget
        assert writes, "the fresher price never landed at all"
        assert writes[-1] == (YES_OUTCOME_ID, pytest.approx(0.90)), (
            "the re-queued stale price overwrote a fresher tick; "
            f"got {writes}"
        )
        assert pytest.approx(0.70) not in [p for _, p in writes], (
            f"the superseded price must never reach the row; got {writes}"
        )

    async def test_a_clean_flush_requeues_nothing(self, monkeypatch):
        """Control. With no failure the counter must stay at zero — otherwise
        `requeued` proves nothing when it is nonzero."""
        writes, stats, _ = await _run_poly(
            monkeypatch,
            [_poly_frame("best_bid_ask", YES_TOKEN, best_bid="0.68", best_ask="0.72")],
            fail_writes=0,
        )

        assert writes == [(YES_OUTCOME_ID, pytest.approx(0.70))], writes
        assert stats["errors"] == 0 and stats["requeued"] == 0, stats


class TestTheBufferCannotGrowWithoutBound:
    async def test_a_long_outage_parks_at_most_one_entry_per_outcome(
        self, monkeypatch
    ):
        """The re-queue must not turn a sustained outage into a memory leak.

        Both legs tick repeatedly while every write fails. The buffer is keyed
        by outcome_id, so the parked set is bounded by the slate (2 legs here)
        however many flush attempts are burned — and `requeued` counts attempts,
        so it must exceed the number of distinct outcomes without the retry
        having accumulated duplicates.
        """
        writes, stats, budget = await _run_poly(
            monkeypatch,
            [
                _poly_frame("best_bid_ask", YES_TOKEN, best_bid="0.68", best_ask="0.72"),
                _poly_frame("best_bid_ask", NO_TOKEN, best_bid="0.28", best_ask="0.32"),
            ],
            fail_writes=10_000,  # never recovers
        )

        assert writes == [], "no write should have landed during a total outage"
        assert stats["errors"] >= 2, (
            f"the flush loop should have retried more than once; got {stats}"
        )
        # Every retry re-queues the same two legs — never three.
        assert stats["requeued"] == 2 * stats["errors"], (
            "the parked set must stay at one entry per outcome; "
            f"got {stats}"
        )
