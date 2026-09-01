"""Q489 — a Polymarket CLOB tick must land on the leg whose book it IS.

WHY THIS FILE EXISTS. `clobTokenIds` is `[yesToken, noToken]`: two asset ids,
one `FuturesMarket`, two `FuturesOutcome` legs. `_run_polymarket_ws_consumer`
declared `asset_to_outcome` and never filled it, so both price handlers resolved
every tick to `outcomes[0]` — the Over/Yes leg. The No token's `best_bid_ask` is
the Yes book seen from the other side (`polymarket.py` says so itself, at
`complementary_book`: "The No token's book is the Yes token's book from the other
side"), so its midpoint is P(No). Writing that to the Yes leg inverts it.

Both legs stream continuously, so the rendered number would not settle on a
wrong value — it would oscillate between p and 1-p at tick rate. A stale card is
wrong once; an inverted card is wrong at random, which is worse, and this is the
half of the fast lane that has never run in production and so has never shown it.

Every test drives the REAL consumer over the REAL service. Only the socket and
the slate query are faked, in the shape `test_ws_recycle_cancellation_q460.py`
established.
"""

import asyncio

import pytest
import websockets
from sqlalchemy.dialects import postgresql
from sqlalchemy.sql.dml import Update

import app.tasks.live_blend_refresh as blend_mod
import app.tasks.polymarket_ws as poly_task

YES_TOKEN = "111"
NO_TOKEN = "222"
YES_OUTCOME_ID = 71
NO_OUTCOME_ID = 72
MARKET_ID = 7
CONDITION_ID = "0xabc"
EVENT_ID = 900

#: The consumer issues three queries, in this order:
#:   1. slate rows   (outcome_id, market_id, outcome_ext, market_ext, event_id)
#:   2. market rows  (market_id, market_ext, market_metadata)
#:   3. outcome rows (outcome_id, market_id, outcome_ext) ORDER BY outcome_id
#:
#: Yes is id 71 and No is id 72 because the ingest inserts the Over/Yes leg
#: first — the ordering the positional token pairing relies on.
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


# ---------------------------------------------------------------- fakes ----


class _TickingSocket:
    """Streams a fixed list of CLOB frames, then goes quiet so the recycle
    timer — not an ended stream — is what stops the consumer."""

    def __init__(self, frames):
        self._frames = list(frames)

    async def send(self, _payload):
        return None

    def __aiter__(self):
        return self

    async def __anext__(self):
        if self._frames:
            return self._frames.pop(0)
        await asyncio.sleep(3600)  # the recycle cancellation lands here
        raise StopAsyncIteration  # pragma: no cover


def _install_socket(monkeypatch, frames):
    def _connect(*_a, **_kw):
        class _Ctx:
            async def __aenter__(self_inner):
                return _TickingSocket(frames)

            async def __aexit__(self_inner, *_exc):
                return False

        return _Ctx()

    monkeypatch.setattr(websockets, "connect", _connect)


class _Result:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return list(self._rows)


class _RecordingSession:
    """Replays the slate for SELECTs and records every UPDATE.

    Recording the statement (rather than a handler's arguments) is deliberate:
    the mis-attribution this file guards happens between the handler and the
    write, so the assertion has to read the write.
    """

    def __init__(self, batches, writes):
        self._batches = batches
        self._writes = writes

    async def execute(self, stmt):
        if isinstance(stmt, Update):
            params = stmt.compile(dialect=postgresql.dialect()).params
            table = stmt.table.name
            if table == "futures_outcomes" and "current_probability" in params:
                self._writes.append(
                    (params["id_1"], params["current_probability"])
                )
            return _Result([])
        return _Result(self._batches.pop(0) if self._batches else [])


def _install_slate(monkeypatch, writes):
    import app.tasks.base as task_base

    batches = [list(b) for b in POLY_SLATE]

    class _Ctx:
        async def __aenter__(self):
            return _RecordingSession(batches, writes)

        async def __aexit__(self, *_exc):
            return False

    monkeypatch.setattr(task_base, "get_task_session", lambda *a, **kw: _Ctx())


class _NoopRefresher:
    """The blend re-stamp is Q460's ship and has its own tests; here it would
    only add DB traffic to a test about attribution."""

    def __init__(self, *_a, **_kw):
        self.refreshed = []

    async def refresh(self, event_ids):
        self.refreshed.append(list(event_ids or []))


def _frame(event_type, asset_id, **kw):
    import json

    return json.dumps({"event_type": event_type, "asset_id": asset_id, **kw})


async def _run(monkeypatch, frames):
    """Drive the real consumer to one planned recycle and return its outcome
    writes as ``[(outcome_id, probability), ...]``."""
    writes: list[tuple[int, float]] = []
    monkeypatch.setattr(poly_task, "SUBSCRIPTION_REFRESH_SECONDS", 0.05)
    monkeypatch.setattr(blend_mod, "LiveBlendRefresher", _NoopRefresher)
    _install_socket(monkeypatch, frames)
    _install_slate(monkeypatch, writes)

    stats = await poly_task._run_polymarket_ws_consumer()
    return writes, stats


# ------------------------------------------------------------- the ship ----


class TestATickLandsOnItsOwnLeg:
    async def test_the_NO_token_writes_the_NO_outcome(self, monkeypatch):
        """THE REGRESSION. Pre-fix this wrote 0.30 onto outcome 71 (Yes) —
        P(No) rendered as P(Yes)."""
        writes, _ = await _run(
            monkeypatch,
            [_frame("best_bid_ask", NO_TOKEN, best_bid="0.28", best_ask="0.32")],
        )

        assert writes == [(NO_OUTCOME_ID, pytest.approx(0.30))], (
            f"a No-token book must grade the No leg; got {writes}"
        )

    async def test_the_YES_token_still_writes_the_YES_outcome(self, monkeypatch):
        """Non-vacuity partner: the fix must not simply move every tick one leg
        along. Same market, same frame shape, the other token."""
        writes, _ = await _run(
            monkeypatch,
            [_frame("best_bid_ask", YES_TOKEN, best_bid="0.68", best_ask="0.72")],
        )

        assert writes == [(YES_OUTCOME_ID, pytest.approx(0.70))], writes

    async def test_both_legs_of_one_binary_are_written_separately(self, monkeypatch):
        """The oscillation proof. Both tokens tick inside one flush window; the
        buffer is keyed by outcome, so two distinct legs must survive it. Pre-fix
        both frames collapsed onto outcome 71 and the second overwrote the first,
        which is exactly the p / 1-p flapping."""
        writes, _ = await _run(
            monkeypatch,
            [
                _frame("best_bid_ask", YES_TOKEN, best_bid="0.68", best_ask="0.72"),
                _frame("best_bid_ask", NO_TOKEN, best_bid="0.28", best_ask="0.32"),
            ],
        )

        assert dict(writes) == {
            YES_OUTCOME_ID: pytest.approx(0.70),
            NO_OUTCOME_ID: pytest.approx(0.30),
        }, writes
        assert len(writes) == 2, f"one leg was overwritten by the other: {writes}"

    async def test_a_trade_on_the_NO_token_grades_the_NO_leg(self, monkeypatch):
        """`last_trade_price` took the same `outcomes[0]` shortcut and needs its
        own guard — it is the path that moves an illiquid market's price."""
        writes, stats = await _run(
            monkeypatch,
            [_frame("last_trade_price", NO_TOKEN, price="0.41")],
        )

        assert writes == [(NO_OUTCOME_ID, pytest.approx(0.41))], writes
        assert stats["trade_updates"] == 1, stats


class TestUnmappableAssetsAreDroppedNotGuessed:
    async def test_a_token_with_no_matching_outcome_writes_nothing(self, monkeypatch):
        """A market carrying more tokens than legs must drop the surplus rather
        than attribute it. `zip` gives this for free; the test pins it, because
        the tempting "fall back to outcomes[0]" is the original bug."""
        writes: list[tuple[int, float]] = []
        monkeypatch.setattr(poly_task, "SUBSCRIPTION_REFRESH_SECONDS", 0.05)
        monkeypatch.setattr(blend_mod, "LiveBlendRefresher", _NoopRefresher)
        _install_socket(
            monkeypatch,
            [_frame("best_bid_ask", "999", best_bid="0.10", best_ask="0.12")],
        )

        import app.tasks.base as task_base

        batches = [
            list(POLY_SLATE[0]),
            [(MARKET_ID, CONDITION_ID, {"clob_token_ids": [YES_TOKEN, NO_TOKEN, "999"]})],
            list(POLY_SLATE[2]),
        ]

        class _Ctx:
            async def __aenter__(self):
                return _RecordingSession(batches, writes)

            async def __aexit__(self, *_exc):
                return False

        monkeypatch.setattr(task_base, "get_task_session", lambda *a, **kw: _Ctx())

        stats = await poly_task._run_polymarket_ws_consumer()

        assert writes == [], f"an unmappable asset was attributed anyway: {writes}"
        assert stats["assets_subscribed"] == 3, stats
        assert stats["assets_mapped"] == 2, stats
        assert stats["assets_unmapped"] == 1, stats


class TestTheMapIsActuallyBuilt:
    async def test_every_subscribed_asset_on_a_two_leg_binary_is_mapped(
        self, monkeypatch
    ):
        """Counts the consumer reports about itself. If `asset_to_outcome` were
        left empty again, `assets_mapped` would be 0 while `assets_subscribed`
        stayed 2 — the exact signature of the defect, now visible in stats."""
        _, stats = await _run(monkeypatch, [])

        assert stats["assets_subscribed"] == 2, stats
        assert stats["assets_mapped"] == 2, stats
        assert stats["assets_unmapped"] == 0, stats
