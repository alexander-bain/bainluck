"""#9484 — an open Kalshi contract outside the game slate streams its price.

The ship: a standalone future or prop (no ``event_id``), or a game market whose
event is days away, takes its price from the socket instead of waiting for the
2 h REST poll. Three properties carry it, each asserted here against the real
consumer with a recording socket:

1. the open contract rides its OWN connection, ``ticker`` channel only, and
   its tick becomes a stored price;
2. the game connection is unchanged — it still subscribes only the linked
   slate's tickers, and an open contract never joins the lifecycle map (whose
   handler would write the opposite ``is_winner`` onto every other candidate)
   or the #9418 "this event is subscribed" set;
3. the arm fails closed on itself: a failed admission read or
   ``WS_OPEN_CONTRACT_PRICES=0`` leaves the game slate streaming exactly as
   before, and an empty game slate never opens the all-markets socket.
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
from app.tasks import ws_open_contracts as oc


LINKED_EVENT_TICKER = "KXATPMATCH-26SEP28ANGJOH"
LINKED_TICKER = "KXATPMATCH-26SEP28ANGJOH-ANG"
OPEN_TICKER = "KXNBAMVP-27-SGA"          # standalone future, market 50
FAR_TICKER = "KXNFLGAME-26OCT04BUFKC-KC"  # game 6 days out, event 901, market 9


def _sql(stmt) -> str:
    return str(
        stmt.compile(
            dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True},
        )
    )


# ------------------------------------------------------------ the admission ----


class TestTheAdmissionIsUnsettledTruthNotAHorizon:
    def test_no_event_join_and_every_unsettled_clause(self):
        sql = _sql(oc.kalshi_open_contract_stmt())
        assert "events" not in sql, "an event join re-imposes the game window"
        assert "futures_markets.source = 'kalshi'" in sql
        # NULL fails open: a plain != drops a NULL status.
        assert "futures_markets.status IS NULL OR futures_markets.status != 'resolved'" in sql
        assert "futures_markets.settled_at IS NULL" in sql
        assert (
            "futures_markets.expiration_time IS NULL OR "
            "futures_markets.expiration_time > NOW()"
        ) in sql
        assert "futures_outcomes.external_id IS NOT NULL" in sql
        assert "futures_outcomes.is_winner IS NULL" in sql
        assert "commence_time" not in sql

    def test_the_map_drops_what_the_game_slate_carries_and_upper_cases(self):
        rows = [
            (LINKED_TICKER.lower(), 7, 71),
            (OPEN_TICKER.lower(), 50, 501),
            (None, 51, 511),
        ]
        linked = {LINKED_TICKER: (7, 71)}
        assert oc.open_contract_ticker_map(rows, linked) == {OPEN_TICKER: (50, 501)}

    def test_shards_lose_nothing_and_respect_the_size(self):
        tickers = [f"T{i:05d}" for i in range(45_001)]
        shards = oc.shard_tickers(reversed(tickers), per_connection=20_000)
        assert [len(s) for s in shards] == [20_000, 20_000, 5_001]
        assert [t for s in shards for t in s] == tickers
        assert oc.shard_tickers([], per_connection=20_000) == []

    def test_the_shard_sits_under_the_size_one_socket_has_carried(self):
        assert oc.OPEN_CONTRACT_TICKERS_PER_CONNECTION <= 23_456

    @pytest.mark.parametrize("value,enabled", [
        (None, True), ("1", True), ("0", False), (" 0 ", False), ("yes", True),
    ])
    def test_the_undo_switch(self, monkeypatch, value, enabled):
        if value is None:
            monkeypatch.delenv("WS_OPEN_CONTRACT_PRICES", raising=False)
        else:
            monkeypatch.setenv("WS_OPEN_CONTRACT_PRICES", value)
        assert oc.open_contract_prices_enabled() is enabled


# ------------------------------------------------------ the consumer, wired ----


class _Socket:
    """Records what the consumer subscribed; once a connection has subscribed a
    ticker listed in ``frames_for``, it delivers that ticker's frames."""

    def __init__(self, record, frames_for):
        self._record = record
        self._frames_for = frames_for
        self._subs: list[dict] = []
        self._pending: list[str] = []
        record.append(self._subs)

    async def send(self, payload):
        cmd = json.loads(payload)
        params = cmd["params"]
        self._subs.append(params)
        if LINKED_TICKER in (params.get("market_tickers") or []):
            GAME_SUBSCRIBED.set()
        for ticker in params.get("market_tickers") or []:
            self._pending.extend(self._frames_for.pop(ticker, []))

    def __aiter__(self):
        return self

    async def __anext__(self):
        if self._pending:
            return self._pending.pop(0)
        await asyncio.sleep(3600)  # the recycle cancellation lands here
        raise StopAsyncIteration  # pragma: no cover


#: Set when a connection subscribes the game slate's ticker; replaced per run.
GAME_SUBSCRIBED = asyncio.Event()


def _install_socket(monkeypatch, frames_for):
    global GAME_SUBSCRIBED
    GAME_SUBSCRIBED = asyncio.Event()
    record: list[list[dict]] = []

    def _connect(*_a, **_kw):
        class _Ctx:
            async def __aenter__(self):
                return _Socket(record, frames_for)

            async def __aexit__(self, *_exc):
                return False

        return _Ctx()

    monkeypatch.setattr(websockets, "connect", _connect)
    monkeypatch.setattr(kalshi_svc, "_load_rsa_key", lambda: object())
    monkeypatch.setattr(kalshi_svc, "_sign_ws_request", lambda _k, _i: {})
    return record


class _Result:
    def __init__(self, rows, rowcount=1):
        self._rows = rows
        self.rowcount = rowcount

    def all(self):
        return list(self._rows)

    def scalars(self):
        return self


def _install_session(monkeypatch, *, linked, open_rows, reread=lambda: [],
                     events_admitted=()):
    """Answers each query by WHAT it asks, not by position, so the open-contract
    read can never be handed another query's rows."""
    import app.tasks.base as task_base

    state = {"price_writes": [], "market_writes": [], "open_reads": 0,
             "bridge_reads": []}

    class _Session:
        async def execute(self, stmt):
            if isinstance(stmt, Update):
                params = stmt.compile(dialect=postgresql.dialect()).params
                if stmt.table.name == "futures_outcomes" and "current_probability" in params:
                    state["price_writes"].append(
                        (params["id_1"], params["current_probability"])
                    )
                elif stmt.table.name == "futures_markets":
                    state["market_writes"].append(params)
                return _Result([])
            sql = _sql(stmt)
            if "futures_outcomes.is_winner IS NULL" in sql:
                state["open_reads"] += 1
                rows = open_rows() if callable(open_rows) else open_rows
                if asyncio.iscoroutine(rows):
                    rows = await rows
                return _Result(rows)
            if sql.startswith("SELECT events.id \nFROM events"):
                # #9484 event bridge: the candidate events' state read.
                state["bridge_reads"].append(sql)
                admitted = (
                    events_admitted() if callable(events_admitted)
                    else events_admitted
                )
                return _Result(list(admitted))
            if "events.status = 'live'" in sql and "scheduled" not in sql:
                return _Result(reread())
            if "FROM futures_outcomes" in sql:
                return _Result([(LINKED_TICKER, 7, 71)] if linked else [])
            return _Result([(LINKED_EVENT_TICKER, 7, 900)] if linked else [])

    class _Ctx:
        async def __aenter__(self):
            return _Session()

        async def __aexit__(self, *_exc):
            return False

    monkeypatch.setattr(task_base, "get_task_session", lambda *a, **kw: _Ctx())
    return state


class _NoopRefresher:
    stats = {"stamped": 0, "no_reading": 0, "throttled": 0, "errors": 0}

    def __init__(self, *_a, **_kw):
        self.source = _a[0] if _a else "kalshi"

    def pending_event_ids(self):
        return frozenset()

    async def refresh(self, event_ids, **_kw):
        return None

    async def refresh_pending(self, **_kw):
        return None

    async def publish_market_changes(self, _session):
        return 0


def _tick(ticker, bid="0.40", ask="0.42", price="0.41"):
    return json.dumps({"type": "ticker", "msg": {
        "market_ticker": ticker, "yes_bid_dollars": bid,
        "yes_ask_dollars": ask, "price_dollars": price,
    }})


def _settle(ticker, result="no"):
    return json.dumps({"type": "market_lifecycle_v2", "msg": {
        "market_ticker": ticker, "status": "determined", "result": result,
    }})


async def _run(monkeypatch, *, frames_for, linked=True, open_rows=(),
               reread=lambda: [], refresh=0.4, check=60.0,
               events_admitted=(), refresher=_NoopRefresher):
    monkeypatch.setenv("KALSHI_API_KEY_ID", "test-key")
    monkeypatch.setenv("KALSHI_RSA_PRIVATE_KEY", "test-secret")
    monkeypatch.setattr(kalshi_task, "SUBSCRIPTION_REFRESH_SECONDS", refresh)
    monkeypatch.setattr(kalshi_task, "PRICE_FLUSH_SECONDS", 0.02)
    monkeypatch.setattr(admission, "ADMISSION_CHECK_SECONDS", check)
    monkeypatch.setattr(admission, "ADMISSION_MIN_RECYCLE_SECONDS", 0)
    monkeypatch.setattr(blend_mod, "LiveBlendRefresher", refresher)
    record = _install_socket(monkeypatch, frames_for)
    state = _install_session(
        monkeypatch, linked=linked, open_rows=list(open_rows)
        if not callable(open_rows) else open_rows, reread=reread,
        events_admitted=events_admitted,
    )
    stats = await asyncio.wait_for(kalshi_task._run_kalshi_ws_consumer(), timeout=5)
    return stats, record, state


def _connections(record):
    """Each connection's subscribe params, keyed by the tickers it asked for."""
    return [subs for subs in record if subs]


class TestAnOpenContractStreamsOnItsOwnConnection:
    async def test_its_tick_becomes_a_stored_price(self, monkeypatch):
        stats, record, state = await _run(
            monkeypatch,
            frames_for={OPEN_TICKER: [_tick(OPEN_TICKER)]},
            open_rows=[(OPEN_TICKER, 50, 501)],
        )

        assert (501, pytest.approx(0.41)) in state["price_writes"]
        assert stats["open_contract_prices_written"] >= 1
        assert stats["open_contract_tickers"] == 1
        assert stats["open_contract_connections"] == 1
        assert stats["open_contract_messages"] >= 1

    async def test_that_connection_asks_for_prices_and_its_own_settlement(
        self, monkeypatch,
    ):
        """#10022 amended this: the connection also carries lifecycle, which it
        routes to the PER-LEG grader (`test_ws_open_contract_settlement_10022`),
        never to the two-sided handler."""
        _stats, record, _state = await _run(
            monkeypatch, frames_for={}, open_rows=[(OPEN_TICKER, 50, 501)],
        )

        conns = _connections(record)
        open_conns = [c for c in conns if any(
            OPEN_TICKER in (p.get("market_tickers") or []) for p in c
        )]
        assert len(open_conns) == 1
        assert [p["channels"] for p in open_conns[0]] == [
            ["ticker"], ["market_lifecycle_v2"],
        ]

    async def test_the_settlement_undo_switch_is_prices_only(self, monkeypatch):
        monkeypatch.setenv("WS_OPEN_CONTRACT_SETTLEMENT", "0")
        _stats, record, _state = await _run(
            monkeypatch, frames_for={}, open_rows=[(OPEN_TICKER, 50, 501)],
        )

        open_conns = [c for c in _connections(record) if any(
            OPEN_TICKER in (p.get("market_tickers") or []) for p in c
        )]
        assert [p["channels"] for p in open_conns[0]] == [["ticker"]]

    async def test_the_game_connection_is_unchanged(self, monkeypatch):
        _stats, record, _state = await _run(
            monkeypatch, frames_for={}, open_rows=[(OPEN_TICKER, 50, 501)],
        )

        game = [c for c in _connections(record) if any(
            LINKED_TICKER in (p.get("market_tickers") or []) for p in c
        )]
        assert len(game) == 1
        assert [p["channels"] for p in game[0]] == [["ticker"], ["market_lifecycle_v2"]]
        for params in game[0]:
            assert params["market_tickers"] == [LINKED_TICKER]


class TestTheGameSocketNeverWaitsForTheRead:
    async def test_the_read_runs_after_the_game_slate_subscribed(self, monkeypatch):
        """Production's read takes ~2.8 s. This read will not answer until the
        game connection has subscribed, so a consumer that awaited it first
        would never subscribe the game — the read times out and the arm
        reports an admission error."""
        async def _after_the_game():
            await asyncio.wait_for(GAME_SUBSCRIBED.wait(), timeout=2)
            return [(OPEN_TICKER, 50, 501)]

        stats, _record, state = await _run(
            monkeypatch,
            frames_for={OPEN_TICKER: [_tick(OPEN_TICKER)]},
            open_rows=_after_the_game,
            refresh=1.0,
        )

        assert stats["open_contract_admission_error"] is False
        assert (501, pytest.approx(0.41)) in state["price_writes"]


class TestAnOpenContractNeverReachesSettlementOrAdmission:
    async def test_a_lifecycle_frame_for_it_never_reaches_the_two_sided_write(
        self, monkeypatch,
    ):
        """Delivered on the GAME socket, where the two-sided handler listens:
        the open contract's event ticker is not in the lifecycle map, so no
        market-wide write happens there. #10022: the frame is graded per leg
        instead — that one leg, and no sibling."""
        graded = []

        async def _grade(_session, *, market_id, outcome_id, state, result):
            graded.append((market_id, outcome_id, state, result))
            return None, None

        monkeypatch.setattr(oc, "grade_open_contract_leg", _grade)
        _stats, _record, state = await _run(
            monkeypatch,
            frames_for={LINKED_TICKER: [_settle(OPEN_TICKER)]},
            open_rows=[(OPEN_TICKER, 50, 501), ("KXNBAMVP-27-JOK", 50, 502)],
        )

        assert state["market_writes"] == []
        assert graded == [(50, 501, "determined", "no")]

    async def test_a_far_game_turning_live_still_recycles(self, monkeypatch):
        """Market 9 is streaming as an open contract. When its event goes live
        the #9418 watcher must still see it as unsubscribed — only the game
        slate carries the blend map that stamps its card."""
        stats, _record, _state = await _run(
            monkeypatch,
            frames_for={},
            open_rows=[(FAR_TICKER, 9, 91)],
            reread=lambda: [(901, 9, None)],
            refresh=3.0, check=0.01,
        )

        assert stats.get("recycle_reason") == "admission"
        assert stats["admitted_event_ids"] == [901]


class TestTheArmFailsClosedOnItself:
    async def test_a_failed_admission_read_keeps_the_game_slate(self, monkeypatch):
        def _boom():
            raise RuntimeError("simulated statement_timeout")

        stats, record, state = await _run(
            monkeypatch,
            frames_for={LINKED_TICKER: [_tick(LINKED_TICKER)]},
            open_rows=_boom,
        )

        assert stats["open_contract_admission_error"] is True
        assert stats["open_contract_connections"] == 0
        assert (71, pytest.approx(0.41)) in state["price_writes"]
        assert len(_connections(record)) == 1

    async def test_the_undo_switch_skips_the_read_and_the_connections(self, monkeypatch):
        monkeypatch.setenv("WS_OPEN_CONTRACT_PRICES", "0")
        stats, record, state = await _run(
            monkeypatch, frames_for={}, open_rows=[(OPEN_TICKER, 50, 501)],
        )

        assert state["open_reads"] == 0
        assert stats["open_contract_tickers"] == 0
        assert len(_connections(record)) == 1

    async def test_an_empty_game_slate_never_opens_the_all_markets_socket(
        self, monkeypatch,
    ):
        """`KalshiWebSocket.run(market_tickers=[])` subscribes EVERY market on
        both channels. With open contracts and no game slate, only the
        open-contract connections open, each filtered to its own tickers on
        every channel it asks for (#10022 added lifecycle to them)."""
        stats, record, state = await _run(
            monkeypatch,
            frames_for={OPEN_TICKER: [_tick(OPEN_TICKER)]},
            linked=False,
            open_rows=[(OPEN_TICKER, 50, 501)],
        )

        conns = _connections(record)
        assert len(conns) == 1
        for params in conns[0]:
            assert params["market_tickers"] == [OPEN_TICKER]
        assert [p["channels"] for p in conns[0]] == [
            ["ticker"], ["market_lifecycle_v2"],
        ]
        assert (501, pytest.approx(0.41)) in state["price_writes"]
        assert stats.get("status") != "no_markets"

    async def test_nothing_at_all_is_still_no_markets(self, monkeypatch):
        stats, record, _state = await _run(
            monkeypatch, frames_for={}, linked=False, open_rows=[],
        )

        assert stats == {"status": "no_markets"}
        assert record == []


# ------------------------------------------- the event bridge (#9484, 10/01) ----
#
# Production 2026-10-01 14:02:14Z: PIT @ CLE (event 14780550, kickoff 10.21 h
# out) — its verified winner contract streamed on this arm, and the event's
# blend did not move with it, because the flush picks the events to re-stamp
# from `event_id_by_outcome` and the arm never added to it. These are that
# contract's real ids.

PIT_CLE_EVENT = 14780550
PIT_CLE_MARKET = 61894632
PIT_CLE_MARKET_TICKER = "KXNFLGAME-26OCT01PITCLE"
CLE_TICKER = "KXNFLGAME-26OCT01PITCLE-CLE"
PIT_TICKER = "KXNFLGAME-26OCT01PITCLE-PIT"
CLE_OUTCOME, PIT_OUTCOME = 233493086, 233493085
SPREAD_TICKER = "KXNFLSPREAD-26OCT01PITCLE-CLE3"

PIT_CLE_ROWS = [
    (CLE_TICKER, PIT_CLE_MARKET, CLE_OUTCOME, PIT_CLE_EVENT, PIT_CLE_MARKET_TICKER),
    (PIT_TICKER, PIT_CLE_MARKET, PIT_OUTCOME, PIT_CLE_EVENT, PIT_CLE_MARKET_TICKER),
]


def _recording_refresher():
    """A refresher that records which events each flush asked it to re-stamp."""
    asked: list[set[int]] = []

    class _Recording(_NoopRefresher):
        async def refresh(self, event_ids, **_kw):
            asked.append(set(event_ids))

    return _Recording, asked


class TestTheBridgeIsTheGameWinnersOwnEvent:
    def test_candidates_are_admitted_winners_with_an_event(self):
        rows = PIT_CLE_ROWS + [
            (SPREAD_TICKER, 62, 621, PIT_CLE_EVENT, "KXNFLSPREAD-26OCT01PITCLE"),
            (OPEN_TICKER, 50, 501, None, "KXNBAMVP-27"),
            (LINKED_TICKER, 7, 71, 900, LINKED_EVENT_TICKER),
            (None, 51, 511, PIT_CLE_EVENT, PIT_CLE_MARKET_TICKER),
            (FAR_TICKER, 9, 91, 901, None),
        ]
        linked = {LINKED_TICKER: (7, 71)}
        assert oc.open_contract_event_candidates(rows, linked) == {
            CLE_OUTCOME: PIT_CLE_EVENT, PIT_OUTCOME: PIT_CLE_EVENT,
        }

    def test_a_row_without_the_market_columns_is_never_bridged(self):
        assert oc.open_contract_event_candidates(
            [(CLE_TICKER, PIT_CLE_MARKET, CLE_OUTCOME)], {},
        ) == {}

    def test_the_ticker_map_is_unchanged_by_the_new_columns(self):
        """The bridge adds no ticker: the subscription set is read from the
        same rows exactly as before."""
        assert oc.open_contract_ticker_map(PIT_CLE_ROWS, {}) == {
            CLE_TICKER: (PIT_CLE_MARKET, CLE_OUTCOME),
            PIT_TICKER: (PIT_CLE_MARKET, PIT_OUTCOME),
        }

    def test_the_event_read_admits_only_undecided_events_by_id(self):
        sql = _sql(oc.open_contract_bridge_event_stmt([PIT_CLE_EVENT, 7, 7]))
        assert sql.startswith("SELECT events.id \nFROM events")
        assert "events.id IN (7, 14780550)" in sql
        assert "events.completed_at IS NULL" in sql
        assert "events.status IN ('scheduled', 'live')" in sql
        assert "commence_time" not in sql, "a horizon here re-imposes the 6 h slate"
        assert "futures" not in sql

    def test_the_bridge_keeps_only_admitted_events(self):
        cands = {CLE_OUTCOME: PIT_CLE_EVENT, 621: 777}
        assert oc.open_contract_event_bridge(cands, [PIT_CLE_EVENT]) == {
            CLE_OUTCOME: PIT_CLE_EVENT,
        }
        assert oc.open_contract_event_bridge(cands, []) == {}


class TestABridgedWinnerReStampsItsEvent:
    async def test_pit_cle_tick_requests_its_event_blend(self, monkeypatch):
        refresher, asked = _recording_refresher()
        stats, _record, state = await _run(
            monkeypatch,
            frames_for={CLE_TICKER: [_tick(CLE_TICKER, "0.42", "0.43", "0.43")]},
            open_rows=PIT_CLE_ROWS, events_admitted=[PIT_CLE_EVENT],
            refresher=refresher,
        )

        assert (CLE_OUTCOME, pytest.approx(0.425)) in state["price_writes"]
        assert any(PIT_CLE_EVENT in ids for ids in asked)
        assert stats["open_contract_bridged_outcomes"] == 2
        assert stats["open_contract_bridged_events"] == 1
        assert stats["open_contract_bridge_error"] is False
        assert len(state["bridge_reads"]) == 1

    async def test_the_bridge_adds_no_subscription(self, monkeypatch):
        frames = {CLE_TICKER: [_tick(CLE_TICKER)]}
        _s, bridged, _st = await _run(
            monkeypatch, frames_for=frames, open_rows=PIT_CLE_ROWS,
            events_admitted=[PIT_CLE_EVENT],
        )
        _s, unbridged, _st = await _run(
            monkeypatch, frames_for=frames, open_rows=PIT_CLE_ROWS,
            events_admitted=[],
        )

        assert _connections(bridged) == _connections(unbridged)
        open_conns = [c for c in _connections(bridged) if any(
            CLE_TICKER in (p.get("market_tickers") or []) for p in c
        )]
        assert len(open_conns) == 1
        for params in open_conns[0]:
            assert sorted(params["market_tickers"]) == sorted([CLE_TICKER, PIT_TICKER])

    async def test_a_quiet_contract_requests_nothing(self, monkeypatch):
        """No quote, no stamp: the bridge never re-stamps an event on its own."""
        refresher, asked = _recording_refresher()
        stats, _record, state = await _run(
            monkeypatch, frames_for={}, open_rows=PIT_CLE_ROWS,
            events_admitted=[PIT_CLE_EVENT], refresher=refresher,
        )

        assert stats["open_contract_bridged_events"] == 1
        assert state["price_writes"] == []
        assert not any(PIT_CLE_EVENT in ids for ids in asked)

    async def test_a_decided_event_is_not_bridged(self, monkeypatch):
        """The event read refused it (completed, or not scheduled/live): the
        price still streams, the event is never asked to re-stamp."""
        refresher, asked = _recording_refresher()
        stats, _record, state = await _run(
            monkeypatch,
            frames_for={CLE_TICKER: [_tick(CLE_TICKER)]},
            open_rows=PIT_CLE_ROWS, events_admitted=[], refresher=refresher,
        )

        assert (CLE_OUTCOME, pytest.approx(0.41)) in state["price_writes"]
        assert not any(PIT_CLE_EVENT in ids for ids in asked)
        assert stats["open_contract_bridged_outcomes"] == 0

    async def test_a_prop_on_the_same_event_is_not_bridged(self, monkeypatch):
        refresher, asked = _recording_refresher()
        stats, _record, state = await _run(
            monkeypatch,
            frames_for={SPREAD_TICKER: [_tick(SPREAD_TICKER)]},
            open_rows=[(SPREAD_TICKER, 62, 621, PIT_CLE_EVENT,
                        "KXNFLSPREAD-26OCT01PITCLE")],
            events_admitted=[PIT_CLE_EVENT], refresher=refresher,
        )

        assert (621, pytest.approx(0.41)) in state["price_writes"]
        assert state["bridge_reads"] == []
        assert not any(PIT_CLE_EVENT in ids for ids in asked)

    async def test_a_winner_with_no_event_is_not_bridged(self, monkeypatch):
        """A game winner the matcher has not linked yet streams its price and
        asks for no event read: there is no event to re-stamp."""
        refresher, asked = _recording_refresher()
        _stats, _record, state = await _run(
            monkeypatch,
            frames_for={FAR_TICKER: [_tick(FAR_TICKER)]},
            open_rows=[(FAR_TICKER, 9, 91, None, "KXNFLGAME-26OCT04BUFKC")],
            refresher=refresher,
        )

        assert (91, pytest.approx(0.41)) in state["price_writes"]
        assert state["bridge_reads"] == []
        assert all(ids <= {900} for ids in asked)

    async def test_a_failed_bridge_read_costs_the_stamp_never_the_price(
        self, monkeypatch,
    ):
        def _boom():
            raise RuntimeError("simulated statement_timeout")

        refresher, asked = _recording_refresher()
        stats, record, state = await _run(
            monkeypatch,
            frames_for={CLE_TICKER: [_tick(CLE_TICKER)]},
            open_rows=PIT_CLE_ROWS, events_admitted=_boom, refresher=refresher,
        )

        assert stats["open_contract_bridge_error"] is True
        assert stats["open_contract_admission_error"] is False
        assert stats["open_contract_tickers"] == 2
        assert (CLE_OUTCOME, pytest.approx(0.41)) in state["price_writes"]
        assert not any(PIT_CLE_EVENT in ids for ids in asked)

    async def test_a_slate_leg_keeps_its_own_event(self, monkeypatch):
        """A ticker the slate carries is excluded from the bridge, so the
        slate's outcome → event entry is never overwritten."""
        refresher, asked = _recording_refresher()
        _stats, _record, state = await _run(
            monkeypatch,
            frames_for={LINKED_TICKER: [_tick(LINKED_TICKER)]},
            open_rows=[(LINKED_TICKER, 7, 71, 999, LINKED_EVENT_TICKER)],
            events_admitted=[999], refresher=refresher,
        )

        assert state["bridge_reads"] == []
        assert any(900 in ids for ids in asked)
        assert not any(999 in ids for ids in asked)

    async def test_the_undo_switch_reads_no_bridge(self, monkeypatch):
        monkeypatch.setenv("WS_OPEN_CONTRACT_PRICES", "0")
        stats, _record, state = await _run(
            monkeypatch, frames_for={}, open_rows=PIT_CLE_ROWS,
            events_admitted=[PIT_CLE_EVENT],
        )

        assert state["bridge_reads"] == []
        assert stats["open_contract_bridged_outcomes"] == 0
