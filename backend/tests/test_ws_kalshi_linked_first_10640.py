"""#10640 — a live game's Kalshi price never waits behind unrelated rows.

The #9484 open-contract shards feed the same buffer as the game socket, and the
flush wrote every buffered row in ONE transaction, then committed, published and
only then re-stamped event blends. So a held futures/prop UPDATE held the game's
commit, its market frame and its blend stamp with it (Root's
`reproduce_head_of_line.py`, re-run on the #2471 head).

Every consumer test here drives the REAL Kalshi consumer over the real service
with a recording socket; only the socket, the session and the refresher are
faked. The session records each transaction (one ``get_task_session()`` block)
as ``commit`` or ``rollback`` with the rows it wrote, so "the game committed"
is a statement about a transaction boundary, never about an UPDATE returning.

THE FAILING-BEFORE CONTROL is `test_the_game_commits_and_restamps_while_the_
unrelated_write_is_held`: on the single-transaction flush it times out waiting
for the game's commit while the open-contract UPDATE is held.
"""

import asyncio
import json

import pytest
import websockets
from sqlalchemy import Update
from sqlalchemy.dialects import postgresql

import app.services.kalshi_ws as kalshi_svc
import app.tasks.kalshi_ws as kalshi_task
import app.tasks.live_blend_refresh as blend_mod
import app.tasks.ws_admission as admission
from app.utils.repair_lock_budget import SET_LOCK_TIMEOUT_SQL
from tests.pm_bulk_test_support import price_writes, statement_params

GAME_EVENT_TICKER = "KXATPMATCH-26SEP28ANGJOH"
GAME_TICKER = "KXATPMATCH-26SEP28ANGJOH-ANG"
GAME_MARKET, GAME_OUTCOME, GAME_EVENT = 7, 71, 900
OPEN_TICKER = "KXNBAMVP-27-SGA"  # standalone future: no event
OPEN_MARKET, OPEN_OUTCOME = 50, 501

STEP = 2.0  # seconds any single wait in this file may take before it fails


def _sql(stmt) -> str:
    return str(
        stmt.compile(
            dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True},
        )
    )


def _tick(ticker, bid, ask):
    mid = f"{(float(bid) + float(ask)) / 2:.3f}"
    return json.dumps({"type": "ticker", "msg": {
        "market_ticker": ticker, "yes_bid_dollars": bid,
        "yes_ask_dollars": ask, "price_dollars": mid,
    }})


# ---------------------------------------------------------------- the rig ----


class _Rig:
    """Shared state: the trace, the per-row write hooks and the handshakes."""

    def __init__(self):
        self.trace: list[tuple] = []
        self.committed: list[tuple[int, float]] = []
        #: outcome id -> async hook(prob, attempt) returning a rowcount.
        self.hooks: dict = {}
        self.attempts: dict[int, int] = {}
        self.dispatched = 0
        self.both_buffered = asyncio.Event()
        #: frames a socket releases only once this event is set
        self.late_gate = asyncio.Event()
        self.late_frames: dict[str, list[str]] = {}
        self.late_dispatched = asyncio.Event()


class _Socket:
    def __init__(self, rig, frames_for):
        self._rig = rig
        self._frames_for = frames_for
        self._pending: list[str] = []
        self._late: list[str] = []
        self._returned = False
        self._late_returned = False

    async def send(self, payload):
        for ticker in json.loads(payload)["params"].get("market_tickers") or []:
            self._pending.extend(self._frames_for.pop(ticker, []))
            self._late.extend(self._rig.late_frames.pop(ticker, []))

    def __aiter__(self):
        return self

    async def __anext__(self):
        # The consumer comes back for a frame only after `handle_ticker`
        # returned, so the previous frame's price is in the buffer by now.
        if self._returned:
            self._returned = False
            self._rig.dispatched += 1
            if self._rig.dispatched >= 2:
                self._rig.both_buffered.set()
        if self._late_returned:
            self._late_returned = False
            self._rig.late_dispatched.set()
        if self._pending:
            self._returned = True
            return self._pending.pop(0)
        if self._late:
            await self._rig.late_gate.wait()
            self._late_returned = True
            return self._late.pop(0)
        await asyncio.sleep(3600)  # the recycle cancellation lands here
        raise StopAsyncIteration  # pragma: no cover


def _install_socket(monkeypatch, rig, frames_for):
    def _connect(*_a, **_kw):
        class _Ctx:
            async def __aenter__(self):
                return _Socket(rig, frames_for)

            async def __aexit__(self, *_exc):
                return False

        return _Ctx()

    monkeypatch.setattr(websockets, "connect", _connect)
    monkeypatch.setattr(kalshi_svc, "_load_rsa_key", lambda: object())
    monkeypatch.setattr(kalshi_svc, "_sign_ws_request", lambda _k, _i: {})


class _Result:
    def __init__(self, rows, rowcount=1):
        self._rows = rows
        self.rowcount = rowcount

    def all(self):
        return list(self._rows)

    def scalars(self):
        return self


def _install_session(monkeypatch, rig):
    """One `_Ctx` per transaction; its exit records commit or rollback."""
    import app.tasks.base as task_base

    class _Session:
        def __init__(self, tx):
            self._tx = tx

        async def execute(self, stmt, params=None):
            if stmt is SET_LOCK_TIMEOUT_SQL:  # #10661: the flush's per-phase lock budget
                return _Result([])
            if isinstance(stmt, Update):
                params = statement_params(stmt, params)  # #10689
                written = price_writes(stmt, params)  # #10689: either shape
                if written:
                    (oid, prob), = written
                    attempt = rig.attempts.get(oid, 0) + 1
                    rig.attempts[oid] = attempt
                    rig.trace.append(("write", oid))
                    hook = rig.hooks.get(oid)
                    rowcount = 1 if hook is None else await hook(prob, attempt)
                    if rowcount:
                        self._tx.append((oid, prob))
                    return _Result([], rowcount=rowcount)
                if stmt.table.name == "futures_outcomes":  # the #6598 re-rank
                    rig.trace.append(("rerank", tuple(o for o, _ in self._tx)))
                    return _Result([], rowcount=0)
                return _Result([])
            sql = _sql(stmt)
            if "futures_outcomes.is_winner IS NULL" in sql:
                return _Result([(OPEN_TICKER, OPEN_MARKET, OPEN_OUTCOME)])
            if sql.startswith("SELECT events.id \nFROM events"):
                return _Result([])
            if "events.status = 'live'" in sql and "scheduled" not in sql:
                return _Result([])
            if "FROM futures_outcomes" in sql:
                return _Result([(GAME_TICKER, GAME_MARKET, GAME_OUTCOME)])
            return _Result([(GAME_EVENT_TICKER, GAME_MARKET, GAME_EVENT)])

    class _Ctx:
        async def __aenter__(self):
            self._tx: list[tuple[int, float]] = []
            return _Session(self._tx)

        async def __aexit__(self, exc_type, *_exc):
            if not self._tx:
                return False
            oids = tuple(o for o, _ in self._tx)
            if exc_type is None:
                rig.trace.append(("commit", oids))
                rig.committed.extend(self._tx)
            else:
                rig.trace.append(("rollback", oids))
            return False

    monkeypatch.setattr(task_base, "get_task_session", lambda *a, **kw: _Ctx())


def _refresher(rig):
    class _Recording:
        stats = {"stamped": 0, "no_reading": 0, "throttled": 0, "errors": 0}

        def __init__(self, *_a, **_kw):
            self.source = _a[0] if _a else "kalshi"

        async def refresh(self, event_ids, **_kw):
            rig.trace.append(("refresh", tuple(sorted(event_ids))))

        def pending_event_ids(self):
            return frozenset()

        async def refresh_pending(self, **_kw):
            return None

        async def publish_market_changes(self, _session):
            rig.trace.append(("publish",))
            return 0

    return _Recording


async def _gated_cadence(rig):
    """`run_flush_cadence`, except the first flush waits until BOTH ticks are
    buffered — so the game leg and the open contract share one batch, which
    is the head-of-line shape. Failure keeps the real rule: wait, then retry.
    #10657: it takes and honours the consumer's ``stop`` like the real one."""

    async def cadence(flush, period, stop=None):
        await rig.both_buffered.wait()
        while stop is None or not stop.is_set():
            ok = await flush(blend_mod._mono())
            await asyncio.sleep(0.01 if ok is not False else 0.03)

    return cadence


async def _start(monkeypatch, rig, *, recycle=1.0):
    monkeypatch.setenv("KALSHI_API_KEY_ID", "test-key")
    monkeypatch.setenv("KALSHI_RSA_PRIVATE_KEY", "test-secret")
    monkeypatch.setattr(kalshi_task, "SUBSCRIPTION_REFRESH_SECONDS", recycle)
    monkeypatch.setattr(admission, "ADMISSION_CHECK_SECONDS", 60.0)
    monkeypatch.setattr(admission, "ADMISSION_MIN_RECYCLE_SECONDS", 0)
    monkeypatch.setattr(blend_mod, "LiveBlendRefresher", _refresher(rig))
    monkeypatch.setattr(blend_mod, "run_flush_cadence", await _gated_cadence(rig))
    frames = {
        GAME_TICKER: [_tick(GAME_TICKER, "0.60", "0.62")],
        OPEN_TICKER: [_tick(OPEN_TICKER, "0.20", "0.22")],
    }
    _install_socket(monkeypatch, rig, frames)
    _install_session(monkeypatch, rig)
    return asyncio.create_task(kalshi_task._run_kalshi_ws_consumer())


def _hold(entered: asyncio.Event, release: asyncio.Event, *, first_only=True):
    async def hook(_prob, attempt):
        if attempt == 1 or not first_only:
            entered.set()
            await release.wait()
        return 1

    return hook


async def _until(predicate, what):
    async def poll():
        while not predicate():
            await asyncio.sleep(0.005)

    try:
        await asyncio.wait_for(poll(), timeout=STEP)
    except asyncio.TimeoutError:  # pragma: no cover - the failure message
        pytest.fail(f"timed out waiting for {what}")


async def _finish(task):
    return await asyncio.wait_for(task, timeout=STEP * 5)


def _index(trace, item):
    return trace.index(item)


# --------------------------------------------------------- the ship ----


class TestTheGameDoesNotWaitForUnrelatedRows:
    async def test_the_game_commits_and_restamps_while_the_unrelated_write_is_held(
        self, monkeypatch,
    ):
        rig = _Rig()
        entered, release = asyncio.Event(), asyncio.Event()
        rig.hooks[OPEN_OUTCOME] = _hold(entered, release)
        # The recycle stays well past the HELD wait, so on the single-transaction
        # flush this test fails THERE, not after a recycle drained the batch.
        task = await _start(monkeypatch, rig, recycle=STEP * 2)

        await asyncio.wait_for(entered.wait(), timeout=STEP)
        # HELD: the open-contract UPDATE has not returned. The game's
        # transaction has committed, published and asked for its blend.
        await _until(
            lambda: ("refresh", (GAME_EVENT,)) in rig.trace,
            "the game's blend refresh while the unrelated write is held",
        )
        held = list(rig.trace)
        assert ("commit", (GAME_OUTCOME,)) in held
        assert held.index(("commit", (GAME_OUTCOME,))) < held.index(("publish",))
        assert held.index(("publish",)) < held.index(("refresh", (GAME_EVENT,)))
        assert (GAME_OUTCOME, pytest.approx(0.61)) in rig.committed
        assert not any(o == OPEN_OUTCOME for o, _ in rig.committed)

        # RELEASED: the unrelated price still commits, in its own transaction.
        release.set()
        await _until(
            lambda: ("commit", (OPEN_OUTCOME,)) in rig.trace,
            "the unrelated row's commit after release",
        )
        stats = await _finish(task)
        assert (OPEN_OUTCOME, pytest.approx(0.21)) in rig.committed
        assert stats["errors"] == 0
        assert stats["flushes"] == 1, "two phases are still one flush on the stats line"
        assert stats["price_updates"] == 2
        assert stats["open_contract_prices_written"] == 1
        assert stats["final_flush_dropped"] == 0
        # The unrelated phase names no event, so it asks for no blend.
        refreshes = [t for t in rig.trace if t[0] == "refresh"]
        assert refreshes == [("refresh", (GAME_EVENT,))]
        # Each market's field is re-ranked inside the transaction that wrote it.
        assert ("rerank", (GAME_OUTCOME,)) in rig.trace
        assert ("rerank", (OPEN_OUTCOME,)) in rig.trace

    async def test_an_unrelated_failure_cannot_undo_the_committed_game(
        self, monkeypatch,
    ):
        rig = _Rig()

        async def fail_once(_prob, attempt):
            if attempt == 1:
                raise RuntimeError("deadlock detected")
            return 1

        rig.hooks[OPEN_OUTCOME] = fail_once
        task = await _start(monkeypatch, rig)
        await _until(
            lambda: any(o == OPEN_OUTCOME for o, _ in rig.committed),
            "the retried unrelated row",
        )
        stats = await _finish(task)

        trace = rig.trace
        game_commit = _index(trace, ("commit", (GAME_OUTCOME,)))
        assert game_commit < trace.index(("write", OPEN_OUTCOME))
        # The failed unrelated transaction wrote nothing that committed, and
        # the game's price committed exactly once — never rolled back.
        assert [t for t in trace if t == ("commit", (GAME_OUTCOME,))] == [
            ("commit", (GAME_OUTCOME,)),
        ]
        assert ("rollback", (GAME_OUTCOME,)) not in trace
        assert stats["errors"] == 1
        assert stats["requeued"] == 1, "only the unpaid unrelated row is retained"
        assert rig.attempts == {GAME_OUTCOME: 1, OPEN_OUTCOME: 2}
        assert stats["final_flush_dropped"] == 0

    async def test_a_settled_unrelated_row_is_refused_and_the_game_still_lands(
        self, monkeypatch,
    ):
        rig = _Rig()

        async def settled(_prob, _attempt):
            return 0  # the #5411 guard matched the id and refused the row

        rig.hooks[OPEN_OUTCOME] = settled
        task = await _start(monkeypatch, rig)
        await _until(
            lambda: rig.attempts.get(OPEN_OUTCOME), "the refused unrelated row",
        )
        stats = await _finish(task)

        assert (GAME_OUTCOME, pytest.approx(0.61)) in rig.committed
        assert not any(o == OPEN_OUTCOME for o, _ in rig.committed)
        assert stats["settled_declined"] == 1
        assert stats["errors"] == 0
        assert rig.attempts[OPEN_OUTCOME] == 1, "a refusal is terminal, not retried"
        # A refused row re-ranks nothing.
        assert ("rerank", (OPEN_OUTCOME,)) not in rig.trace

    async def test_a_fresher_tick_during_the_held_write_survives_it(
        self, monkeypatch,
    ):
        """Q491's newest-tick rule, per phase: the unrelated phase's
        acknowledgement must not delete a price that arrived during its write."""
        rig = _Rig()
        entered, release = asyncio.Event(), asyncio.Event()
        rig.hooks[OPEN_OUTCOME] = _hold(entered, release)
        rig.late_frames[OPEN_TICKER] = [_tick(OPEN_TICKER, "0.30", "0.32")]
        task = await _start(monkeypatch, rig)

        await asyncio.wait_for(entered.wait(), timeout=STEP)
        rig.late_gate.set()
        await asyncio.wait_for(rig.late_dispatched.wait(), timeout=STEP)
        release.set()
        await _until(
            lambda: (OPEN_OUTCOME, pytest.approx(0.31)) in rig.committed,
            "the fresher unrelated price on the next flush",
        )
        stats = await _finish(task)

        prices = [p for o, p in rig.committed if o == OPEN_OUTCOME]
        assert prices == [pytest.approx(0.21), pytest.approx(0.31)]
        assert stats["final_flush_dropped"] == 0

    async def test_a_recycle_during_the_unrelated_write_keeps_the_game_and_retries_the_rest(
        self, monkeypatch,
    ):
        """Cancellation between phases: the game phase is committed and
        acknowledged; the unrelated row was never acknowledged, so the final
        drain retries it (Q491 repair) rather than dropping it."""
        rig = _Rig()
        entered = asyncio.Event()
        never = asyncio.Event()
        rig.hooks[OPEN_OUTCOME] = _hold(entered, never)  # first attempt only
        task = await _start(monkeypatch, rig, recycle=0.4)

        await asyncio.wait_for(entered.wait(), timeout=STEP)
        stats = await _finish(task)  # the recycle cancels the held flush

        assert stats["status"] == "resubscribe"
        assert ("commit", (GAME_OUTCOME,)) in rig.trace
        assert ("rollback", (GAME_OUTCOME,)) not in rig.trace
        assert (OPEN_OUTCOME, pytest.approx(0.21)) in rig.committed
        assert rig.attempts[GAME_OUTCOME] == 1, "an acknowledged game row is not rewritten"
        assert stats["final_flush_dropped"] == 0


# ------------------------------------------------------ the partition ----


class TestThePartition:
    MARKETS = {71: 7, 72: 7, 501: 50, 502: 50, 601: 60}

    def _phases(self, batch, events, markets=None):
        return kalshi_task.linked_first_phases(
            batch, self.MARKETS if markets is None else markets, events,
        )

    def test_a_linked_market_goes_first_whole_and_the_rest_after(self):
        batch = {501: "a", 71: "b", 601: "c", 72: "d", 502: "e"}
        first, rest = self._phases(batch, {71: 900})
        assert first == {71: "b", 72: "d"}, "a sibling travels with its market"
        assert rest == {501: "a", 601: "c", 502: "e"}
        assert set(first) | set(rest) == set(batch)

    def test_a_bridged_open_contract_counts_as_linked(self):
        batch = {501: "a", 601: "c"}
        first, rest = self._phases(batch, {501: 14780550})
        assert set(first) == {501} and set(rest) == {601}

    def test_an_unknown_market_keeps_the_single_transaction(self):
        batch = {71: "b", 999: "x"}
        assert self._phases(batch, {71: 900}) == [batch]

    def test_one_kind_only_keeps_the_single_transaction(self):
        assert self._phases({71: "b", 72: "d"}, {71: 900, 72: 900}) == [
            {71: "b", 72: "d"},
        ]
        assert self._phases({501: "a", 601: "c"}, {}) == [{501: "a", 601: "c"}]
        assert self._phases({}, {}) == [{}]

    def test_an_event_id_of_none_is_not_linked(self):
        batch = {71: "b", 601: "c"}
        assert self._phases(batch, {71: None}) == [batch]

    def test_the_batch_is_not_mutated(self):
        batch = {71: "b", 601: "c"}
        self._phases(batch, {71: 900})
        assert batch == {71: "b", 601: "c"}
