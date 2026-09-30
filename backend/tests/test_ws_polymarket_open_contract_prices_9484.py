"""Every open Polymarket contract streams its price, not only the game slate's. #9484.

WHAT THIS SHIPS. The Polymarket socket subscribed only markets linked to an
event that is live, scheduled within 6 h or recently suspended. A standalone
future or prop (no ``event_id``) or a game market days out never reached the
wire, so its stored price moved only on the REST rotation and the #9484 market
invalidation never fired for it. Codex's 05:26Z decision: every open contract
is eligible, over the existing 500-asset sharding.

THE CASES:

    TestTheSelector ............ unsettled truth only; no event join; graded
                                 legs by `is_winner IS TRUE` / a source, never
                                 `is_winner IS NULL` (the column defaults FALSE).
    TestPairing ................ own tokens by CLOB order when counts match;
                                 per-outcome tokens next; a mismatch is counted,
                                 never zipped; one owner per token.
    TestThirtyFiveThousand ..... 35,000 tokens, every one subscribed once, over
                                 frames under the byte ceiling, with at most 4
                                 handshakes/initial dumps in flight.
    TestReconnectSafeguards .... a clean close no longer re-dials instantly;
                                 the backoff resets only after a stable socket.
    TestFlushPlan .............. linked rows first; open rows bounded per flush,
                                 oldest first, none dropped.
    TestTheConsumer ............ the real `_run_polymarket_ws_consumer` over a
                                 real SQLite session: an open contract's tick is
                                 stored and announced on its market channel; its
                                 socket is prices-only; the game subscription is
                                 unchanged; a failed chunk costs only its rows;
                                 a linked quote is written ahead of an open
                                 backlog; an open-only run opens no all-markets
                                 socket; a failed read costs the arm only.
"""

import asyncio
import json

import pytest
import websockets
from sqlalchemy import (
    Column, DateTime, Integer, MetaData, String, Table, create_engine, insert, text,
)
from sqlalchemy.dialects import postgresql
from sqlalchemy.orm import Session
from sqlalchemy.sql.dml import Update
from sqlalchemy.sql.selectable import Select

import app.services.polymarket_ws as poly_svc
import app.tasks.live_blend_refresh as blend_mod
import app.tasks.polymarket_open_contracts as open_mod
import app.tasks.polymarket_ws as poly_task
from app.models.models import FuturesOutcome
from app.utils.market_quote_push import market_channel, parse_market_frame

pytestmark = pytest.mark.asyncio


def _sql(stmt) -> str:
    return str(
        stmt.compile(
            dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}
        )
    )


# ------------------------------------------------------------ selector ----


class TestTheSelector:
    async def test_markets_are_unsettled_polymarket_with_no_event_join(self):
        sql = _sql(open_mod.open_contract_markets_stmt())
        assert "futures_markets.source = 'polymarket'" in sql
        # NULL fails OPEN: production's column is nullable.
        assert (
            "futures_markets.status IS NULL OR futures_markets.status != 'resolved'"
            in sql
        )
        assert "futures_markets.settled_at IS NULL" in sql
        assert "events" not in sql and "event_id" not in sql
        assert "commence_time" not in sql
        # Only the three token keys, never the whole blob.
        for key in ("clob_token_ids", "clobTokenIds", "clob_yes_token_by_outcome"):
            assert f"market_metadata[{key!r}]" in sql
        assert "futures_markets.market_metadata," not in sql

    async def test_legs_carry_their_graded_flag_in_token_order(self):
        stmt = open_mod.open_contract_outcomes_stmt([7, 8])
        sql = _sql(stmt)
        assert "futures_outcomes.is_winner IS true" in sql
        assert "futures_outcomes.resolution_source IS NOT NULL" in sql
        # `is_winner` defaults FALSE server-side: a NULL test would call every
        # raw-inserted ungraded leg graded (or, as a filter, drop it).
        assert "is_winner IS NULL" not in sql
        assert "ORDER BY futures_outcomes.id" in sql
        assert "events" not in sql

    async def test_legs_are_addressed_by_market_id_through_one_array_bind(self):
        # The join form planned a sequential scan of every outcome; one array
        # bind walks the market_id index, whatever the market count (no
        # per-id bind parameters to run into the driver's 32,767 limit).
        stmt = open_mod.open_contract_outcomes_stmt(range(1, 30_001))
        compiled = stmt.compile(dialect=postgresql.dialect())
        assert "futures_outcomes.market_id = ANY (%(market_ids)s::INTEGER[])" in str(compiled)
        assert "JOIN" not in str(compiled)
        assert list(compiled.params) == ["market_ids"]
        assert compiled.params["market_ids"] == list(range(1, 30_001))

    async def test_the_leg_read_is_chunked_by_market(self):
        stmts = open_mod.open_contract_outcome_stmts(range(1, 4_502))
        chunks = [
            s.compile(dialect=postgresql.dialect()).params["market_ids"]
            for s in stmts
        ]
        assert [len(c) for c in chunks] == [2_000, 2_000, 501]
        assert [i for c in chunks for i in c] == list(range(1, 4_502))
        assert open_mod.open_contract_outcome_stmts([]) == []

    async def test_either_undo_flag_turns_the_arm_off(self, monkeypatch):
        assert open_mod.open_contract_prices_enabled()
        monkeypatch.setenv("POLYMARKET_WS_OPEN_CONTRACT_PRICES", "0")
        assert not open_mod.open_contract_prices_enabled()
        monkeypatch.delenv("POLYMARKET_WS_OPEN_CONTRACT_PRICES")
        monkeypatch.setenv("WS_OPEN_CONTRACT_PRICES", "0")
        assert not open_mod.open_contract_prices_enabled()


# ------------------------------------------------------------- pairing ----


class TestPairing:
    async def test_own_tokens_pair_in_clob_order_not_id_order(self):
        # #8403: the `_side1` leg holds the LOWER id; token 0 is still the
        # bare-condition leg's.
        adm = open_mod.open_contract_asset_map(
            [(7, ["t0", "t1"], None, None)],
            [(70, 7, "0xabc_side1", False), (71, 7, "0xabc", False)],
        )
        assert adm.asset_to_outcome == {"t0": 71, "t1": 70}
        assert adm.asset_to_market == {"t0": 7, "t1": 7}
        assert adm.counts["markets_admitted"] == 1

    async def test_legacy_json_string_and_camel_case_tokens(self):
        adm = open_mod.open_contract_asset_map(
            [(7, '["a", "b"]', None, None), (8, None, ["c", "d"], None)],
            [
                (71, 7, "x_yes", False), (72, 7, "x_no", False),
                (81, 8, "y_yes", False), (82, 8, "y_no", False),
            ],
        )
        assert adm.asset_to_outcome == {"a": 71, "b": 72, "c": 81, "d": 82}

    async def test_a_count_mismatch_is_counted_never_zipped(self):
        # Two tokens, three legs: a positional zip would put one leg's price on
        # another. Counted instead.
        adm = open_mod.open_contract_asset_map(
            [(7, ["t0", "t1"], None, None)],
            [(71, 7, "a", False), (72, 7, "b", False), (73, 7, "c", False)],
        )
        assert adm.asset_to_outcome == {}
        assert adm.counts["markets_unpaired"] == 1

    async def test_a_field_row_uses_its_per_outcome_tokens(self):
        adm = open_mod.open_contract_asset_map(
            [(9, None, None, {"91": "yes91", "92": "yes92"})],
            [(91, 9, "0x1", False), (92, 9, "0x2", False), (93, 9, "0x3", False)],
        )
        assert adm.asset_to_outcome == {"yes91": 91, "yes92": 92}

    async def test_graded_taken_duplicate_excluded_and_tokenless(self):
        adm = open_mod.open_contract_asset_map(
            [
                (7, ["g", "ok"], None, None),       # one graded leg
                (8, ["taken", "fresh"], None, None),  # one on the game socket
                (9, ["ok", "other"], None, None),   # "ok" already owned by 7
                (5, ["slate0", "slate1"], None, None),  # on the game slate
                (6, None, None, None),              # nothing stored
            ],
            [
                (71, 7, "a_yes", True), (72, 7, "a_no", False),
                (81, 8, "b_yes", False), (82, 8, "b_no", False),
                (91, 9, "c_yes", False), (92, 9, "c_no", False),
                (51, 5, "d_yes", False), (52, 5, "d_no", False),
                (61, 6, "e_yes", False),
            ],
            taken_assets={"taken"},
            excluded_market_ids={5},
        )
        assert adm.asset_to_outcome == {"ok": 72, "fresh": 82, "other": 92}
        # #9736: the taken and duplicate legs are not re-owned, but mirrored.
        assert adm.asset_mirrors == {"taken": [(81, 8)], "ok": [(91, 9)]}
        c = adm.counts
        assert c["legs_graded"] == 1
        assert c["assets_already_streaming"] == 1
        assert c["assets_duplicate"] == 1
        assert c["legs_mirrored"] == 2
        assert c["markets_on_game_slate"] == 1
        assert c["markets_without_tokens"] == 1
        assert c["markets"] == 5




class TestSharedTokenFanOut:
    """#9736. The NLDS board 60087232's Cubs leg and the standalone binary
    61380842 name ONE Polymarket condition. One owner per token left the
    board's leg at its pre-game 0.445 while the binary streamed 0.235 — Cubs
    44% and 22% on one search page. Both legs are the same contract."""

    BOARD = (60087232, None, None, {"601": "cubsYes", "602": "sdYes"})
    BINARY = (61380842, ["cubsYes", "cubsNo"], None, None)
    LEGS = [
        (601, 60087232, "0x52f9", False), (602, 60087232, "0x77aa", False),
        (611, 61380842, "0x52f9_yes", False), (612, 61380842, "0x52f9_no", False),
    ]

    @pytest.mark.parametrize("board_first", [True, False])
    async def test_both_legs_take_the_token_whichever_market_comes_first(
        self, board_first
    ):
        rows = [self.BOARD, self.BINARY] if board_first else [self.BINARY, self.BOARD]
        adm = open_mod.open_contract_asset_map(rows, self.LEGS)

        owner = adm.asset_to_outcome["cubsYes"]
        mirrors = [oid for oid, _mid in adm.asset_mirrors["cubsYes"]]
        assert sorted([owner, *mirrors]) == [601, 611]
        # Subscribed once: the owner map still names each token one time.
        assert sorted(adm.asset_to_outcome) == ["cubsNo", "cubsYes", "sdYes"]
        assert adm.mirrored_outcomes() == (
            {611: 61380842} if board_first else {601: 60087232}
        )
        assert adm.counts["legs_mirrored"] == 1

    async def test_a_token_the_game_socket_carries_is_mirrored_not_resubscribed(
        self,
    ):
        adm = open_mod.open_contract_asset_map(
            [self.BOARD], self.LEGS[:2], taken_assets={"cubsYes"},
        )
        assert adm.asset_to_outcome == {"sdYes": 602}
        assert adm.asset_mirrors == {"cubsYes": [(601, 60087232)]}
        assert adm.counts["assets_already_streaming"] == 1

    async def test_two_legs_of_one_market_naming_one_token_are_not_mirrored(self):
        # A pairing defect inside one market, not a shared contract: the second
        # leg is still dropped, never handed the first leg's price.
        adm = open_mod.open_contract_asset_map(
            [(9, None, None, {"91": "same", "92": "same"})],
            [(91, 9, "0x1", False), (92, 9, "0x2", False)],
        )
        assert adm.asset_to_outcome == {"same": 91}
        assert adm.asset_mirrors == {}
        assert adm.counts["assets_duplicate"] == 1
        assert adm.counts["legs_mirrored"] == 0

    async def test_a_graded_mirror_leg_is_never_priced(self):
        legs = [*self.LEGS[:1], (602, 60087232, "0x77aa", False),
                (611, 61380842, "0x52f9_yes", True),
                (612, 61380842, "0x52f9_no", False)]
        adm = open_mod.open_contract_asset_map([self.BOARD, self.BINARY], legs)
        assert adm.asset_to_outcome["cubsYes"] == 601
        assert "cubsYes" not in adm.asset_mirrors


# ---------------------------------------------------- 35,000 tokens ----


def _synthetic(n_markets: int):
    markets, legs = [], []
    for m in range(n_markets):
        cid = f"0x{m:064x}"
        tokens = [f"{10**76 + 2 * m}", f"{10**76 + 2 * m + 1}"]
        markets.append((m + 1, tokens, None, None))
        legs.append((2 * m + 1, m + 1, f"{cid}_yes", False))
        legs.append((2 * m + 2, m + 1, f"{cid}_no", False))
    return markets, legs


class _DumpThenHold:
    """A venue socket: records its subscribe, sends one dump, then holds."""

    def __init__(self, record, dump_after=0.005, send_dump=True):
        self._record = record
        self._dump_after = dump_after
        self._send_dump = send_dump
        self.closed = False
        self.subscribed = None

    async def send(self, payload):
        if payload != "PING":
            self.subscribed = json.loads(payload).get("assets_ids")
            self._record["subscribed"].append(self.subscribed)

    def __aiter__(self):
        async def gen():
            await asyncio.sleep(self._dump_after)
            if self._send_dump:
                self._record["dumped"] += 1
                yield "[]"
            await asyncio.sleep(3600)

        return gen()

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        self.closed = True
        return False


def _gated_connect(monkeypatch, **socket_kw):
    record = {"subscribed": [], "dumped": 0, "connects": 0, "peak": 0}
    sockets = []

    def connect(*_a, **kw):
        record["connects"] += 1
        record.setdefault("max_queue", kw.get("max_queue"))
        sock = _DumpThenHold(record, **socket_kw)
        sockets.append(sock)
        in_flight = record["connects"] - record["dumped"]
        record["peak"] = max(record["peak"], in_flight)
        return sock

    monkeypatch.setattr(websockets, "connect", connect)
    return record, sockets


async def _cancel(task):
    task.cancel()
    await asyncio.gather(task, return_exceptions=True)


class TestThirtyFiveThousand:
    async def test_every_token_is_subscribed_once_under_the_ceiling(self, monkeypatch):
        markets, legs = _synthetic(17_500)
        adm = open_mod.open_contract_asset_map(markets, legs)
        assert len(adm.asset_to_outcome) == 35_000

        record, sockets = _gated_connect(monkeypatch)
        ws = poly_svc.PolymarketWebSocket(max_concurrent_handshakes=4, max_queue=4)
        task = asyncio.create_task(ws.run(asset_ids=sorted(adm.asset_to_outcome)))
        expected = len(poly_svc._shard_asset_ids(sorted(adm.asset_to_outcome)))
        for _ in range(400):
            if record["dumped"] >= expected:
                break
            await asyncio.sleep(0.01)
        try:
            assert expected >= 70
            assert len(record["subscribed"]) == expected
            flat = [a for s in record["subscribed"] for a in s]
            assert len(flat) == 35_000 and set(flat) == set(adm.asset_to_outcome)
            for ids in record["subscribed"]:
                frame = poly_svc._subscribe_frame(ids)
                assert len(frame.encode("utf-8")) <= poly_svc.MAX_SUBSCRIBE_BYTES
            # THE BOUND: never more than 4 dialled-but-undumped at once.
            assert record["peak"] <= 4, record["peak"]
            assert record["max_queue"] == 4
            # Permits are per handshake, not per subscription: all stay up.
            assert ws.stats["shards_connected"] == expected
        finally:
            await _cancel(task)
        assert all(s.closed for s in sockets)
        assert ws.is_connected is False

    async def test_without_the_gate_every_shard_dials_at_once(self, monkeypatch):
        # The control: the same population with no gate peaks at the shard
        # count, so the bound above is the gate's doing.
        markets, legs = _synthetic(2_000)
        assets = sorted(open_mod.open_contract_asset_map(markets, legs).asset_to_outcome)
        record, _ = _gated_connect(monkeypatch, dump_after=0.05)
        ws = poly_svc.PolymarketWebSocket()
        task = asyncio.create_task(ws.run(asset_ids=assets))
        await asyncio.sleep(0.02)
        try:
            assert record["peak"] == len(poly_svc._shard_asset_ids(assets)) > 4
            assert record["max_queue"] == poly_svc.DEFAULT_MAX_QUEUE_MESSAGES
        finally:
            await _cancel(task)

    async def test_a_silent_shard_frees_its_permit_on_the_hold_timeout(
        self, monkeypatch
    ):
        monkeypatch.setattr(poly_svc, "HANDSHAKE_PERMIT_HOLD_SECONDS", 0.02)
        record, sockets = _gated_connect(monkeypatch, send_dump=False)
        ws = poly_svc.PolymarketWebSocket(max_concurrent_handshakes=1)
        markets, legs = _synthetic(750)  # 1,500 assets -> 3 shards
        assets = sorted(open_mod.open_contract_asset_map(markets, legs).asset_to_outcome)
        task = asyncio.create_task(ws.run(asset_ids=assets))
        await asyncio.sleep(0.3)
        try:
            assert record["connects"] == 3
            assert ws.stats["shards_connected"] == 3
        finally:
            await _cancel(task)
        assert all(s.closed for s in sockets)

    async def test_cancelled_while_waiting_on_the_gate_leaks_nothing(
        self, monkeypatch
    ):
        record, sockets = _gated_connect(monkeypatch, send_dump=False)
        ws = poly_svc.PolymarketWebSocket(max_concurrent_handshakes=1)
        markets, legs = _synthetic(750)
        assets = sorted(open_mod.open_contract_asset_map(markets, legs).asset_to_outcome)
        before = asyncio.all_tasks()
        task = asyncio.create_task(ws.run(asset_ids=assets))
        await asyncio.sleep(0.02)
        assert record["connects"] == 1  # two shards still queued on the gate
        await _cancel(task)
        await asyncio.sleep(0.01)
        assert asyncio.all_tasks() - before - {asyncio.current_task()} == set()
        assert all(s.closed for s in sockets)


# ---------------------------------------------- reconnect safeguards ----


class _Stop(BaseException):
    """Not an Exception, so `_run_one`'s reconnect loop cannot swallow it."""


class _AsyncioShim:
    def __init__(self):
        self.sleeps: list[float] = []

    def __getattr__(self, name):
        return getattr(asyncio, name)

    async def sleep(self, delay, *a, **kw):
        if delay != 8:  # the heartbeat (so attempts stay below an 8 s backoff)
            self.sleeps.append(delay)
        return await asyncio.sleep(0)


class _ClosesCleanly:
    closed = False

    async def send(self, _payload):
        return None

    def __aiter__(self):
        async def gen():
            return
            yield  # pragma: no cover

        return gen()

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False


def _reconnects(monkeypatch, behaviour, attempts=3):
    calls = {"n": 0}

    def connect(*_a, **_kw):
        calls["n"] += 1
        if calls["n"] > attempts:
            raise _Stop
        return behaviour()

    monkeypatch.setattr(websockets, "connect", connect)
    monkeypatch.setattr(poly_svc.random, "random", lambda: 1.0)  # no jitter
    shim = _AsyncioShim()
    monkeypatch.setattr(poly_svc, "asyncio", shim)
    return shim


class TestReconnectSafeguards:
    async def test_a_clean_close_waits_and_backs_off(self, monkeypatch):
        # Before: a clean close fell straight back into connect — no sleep.
        shim = _reconnects(monkeypatch, _ClosesCleanly)
        with pytest.raises(_Stop):
            await poly_svc.PolymarketWebSocket().run(asset_ids=["1"])
        assert shim.sleeps == [1.0, 2.0, 4.0]

    async def test_a_connection_that_held_resets_the_backoff(self, monkeypatch):
        monkeypatch.setattr(poly_svc, "STABLE_CONNECTION_SECONDS", 0.0)
        shim = _reconnects(monkeypatch, _ClosesCleanly)
        with pytest.raises(_Stop):
            await poly_svc.PolymarketWebSocket().run(asset_ids=["1"])
        assert shim.sleeps == [1.0, 1.0, 1.0]

    async def test_a_failed_handshake_never_resets_it(self, monkeypatch):
        monkeypatch.setattr(poly_svc, "STABLE_CONNECTION_SECONDS", 0.0)

        def refuse():
            raise OSError("refused")

        shim = _reconnects(monkeypatch, refuse)
        with pytest.raises(_Stop):
            await poly_svc.PolymarketWebSocket().run(asset_ids=["1"])
        assert shim.sleeps == [1.0, 2.0, 4.0]

    async def test_the_sleep_is_jittered_below_its_base(self, monkeypatch):
        shim = _reconnects(monkeypatch, _ClosesCleanly, attempts=2)
        monkeypatch.setattr(poly_svc.random, "random", lambda: 0.0)
        with pytest.raises(_Stop):
            await poly_svc.PolymarketWebSocket().run(asset_ids=["1"])
        assert shim.sleeps == [0.5, 1.0]


# ----------------------------------------------------------- flush plan ----


class TestFlushPlan:
    async def test_linked_rows_lead_and_open_rows_are_bounded(self):
        buffered = [101, 102, 1, 103, 104, 2, 105]  # oldest first
        opened = {101, 102, 103, 104, 105}
        chunks = open_mod.plan_flush_chunks(buffered, opened, 2, 1)
        assert chunks == [[1, 2], [101, 102]]

    async def test_the_final_drain_takes_everything(self):
        buffered = [101, 102, 1, 103]
        chunks = open_mod.plan_flush_chunks(buffered, {101, 102, 103}, 2, None)
        assert chunks == [[1], [101, 102], [103]]

    async def test_a_standing_backlog_drains_oldest_first_and_loses_none(self):
        # The buffer as `flush_prices` keeps it: written rows leave, the rest
        # keep their place. 5,000 open rows and a linked row every flush.
        opened = set(range(10_000, 15_000))
        buffer = dict.fromkeys(sorted(opened), 0.5)
        written_open = []
        for flush in range(6):
            buffer[flush] = 0.5  # a fresh linked quote
            waiting = len(buffer) - 1
            chunks = open_mod.plan_flush_chunks(buffer, opened, 500, 2)
            assert chunks[0] == [flush], "the linked quote goes first"
            assert sum(len(c) for c in chunks) == 1 + min(1_000, waiting)
            for chunk in chunks:
                for oid in chunk:
                    del buffer[oid]
                    if oid in opened:
                        written_open.append(oid)
        # Oldest first, every one, once.
        assert written_open == sorted(opened)
        assert buffer == {}


# ------------------------------------------------------- the consumer ----


GAME_MARKET, GAME_OUTCOME, GAME_TOKEN, EVENT_ID = 5, 51, "555", 900
#: Standalone open markets: (market_id, outcome_id, token)
OPEN = [(7, 71, "711"), (8, 81, "811"), (9, 91, "911")]


def _database(tmp_path, fail_outcome=None, extra=()):
    engine = create_engine(f"sqlite:///{tmp_path / 'ws.db'}")
    markets = Table(
        "futures_markets", MetaData(),
        Column("id", Integer, primary_key=True),
        Column("source", String), Column("external_id", String),
        Column("name", String), Column("status", String),
        Column("settled_at", DateTime(timezone=True)),
        Column("updated_at", DateTime(timezone=True)),
    )
    markets.create(engine)
    FuturesOutcome.__table__.create(engine)
    with engine.begin() as conn:
        for mid, oid, _tok in [
            (GAME_MARKET, GAME_OUTCOME, GAME_TOKEN), *OPEN, *extra,
        ]:
            conn.execute(insert(markets).values(
                id=mid, source="polymarket", external_id=f"0x{mid}",
                name=f"market {mid}", status="open",
            ))
            conn.execute(insert(FuturesOutcome.__table__).values(
                id=oid, market_id=mid, external_id=f"0x{mid}",
                name="Yes", current_probability=0.30,
            ))
        if fail_outcome is not None:
            conn.execute(text(
                "CREATE TRIGGER boom BEFORE UPDATE ON futures_outcomes "
                f"WHEN NEW.id = {fail_outcome} "
                "BEGIN SELECT RAISE(ABORT, 'boom'); END"
            ))
    return engine


GAME_SLATE = [
    [(GAME_OUTCOME, GAME_MARKET, f"0x{GAME_MARKET}", f"0x{GAME_MARKET}", EVENT_ID)],
    [(GAME_MARKET, f"0x{GAME_MARKET}", {"clob_token_ids": [GAME_TOKEN]})],
    [(GAME_OUTCOME, GAME_MARKET, f"0x{GAME_MARKET}")],
]
OPEN_MARKET_ROWS = [(mid, [tok], None, None) for mid, _oid, tok in OPEN]
OPEN_OUTCOME_ROWS = [(oid, mid, f"0x{mid}", False) for mid, oid, _tok in OPEN]


class _Replayed:
    def __init__(self, rows, rowcount=1):
        self._rows = rows
        self.rowcount = rowcount

    def all(self):
        return list(self._rows)


class _Session:
    """AsyncSession-shaped over a REAL sync Session for the price UPDATE; the
    slate, the open-contract read and the reread are replayed by statement."""

    def __init__(self, real, rig):
        self.sync_session = real
        self._rig = rig

    @property
    def info(self):
        return self.sync_session.info

    async def execute(self, stmt, *_a, **_kw):
        sql = str(stmt)
        if sql == str(open_mod.open_contract_markets_stmt()):
            return self._rig.open_read(0)
        if sql == str(open_mod.open_contract_outcomes_stmt()):
            self._rig.leg_reads.append(
                stmt.compile().params["market_ids"]
            )
            return self._rig.open_read(1)
        if isinstance(stmt, Update):
            if stmt.table.name == "futures_outcomes" and any(
                getattr(c, "key", c) == "current_probability" for c in stmt._values
            ):
                return self.sync_session.execute(stmt)
            self._rig.other_updates.append(stmt)
            return _Replayed([], rowcount=0)
        if isinstance(stmt, Select) and "win_probability_sources" in sql:
            return _Replayed([])
        return _Replayed(self._rig.slate.pop(0) if self._rig.slate else [])


class _FakeRedis:
    def __init__(self):
        self.published = []

    async def publish(self, channel, payload):
        self.published.append((channel, parse_market_frame(payload)))
        return 0


class _Rig:
    def __init__(self, engine, slate, open_rows, frames_for, open_read_fails=False):
        self.engine = engine
        self.slate = [list(b) for b in slate]
        self._open_rows = open_rows
        self.open_read_fails = open_read_fails
        self.frames_for = frames_for
        self.other_updates = []
        self.leg_reads = []
        self.subscribes = []
        self.redis = _FakeRedis()

    def open_read(self, index):
        if self.open_read_fails:
            raise RuntimeError("read failed")
        return _Replayed(self._open_rows[index])


class _VenueSocket:
    def __init__(self, rig):
        self._rig = rig
        self._assets = None
        self._queue: asyncio.Queue = asyncio.Queue()

    async def send(self, payload):
        if payload == "PING":
            return
        self._assets = json.loads(payload).get("assets_ids")
        self._rig.subscribes.append(self._assets)
        for delay, frame in self._rig.frames_for(self._assets):
            asyncio.get_running_loop().call_later(delay, self._queue.put_nowait, frame)

    def __aiter__(self):
        return self

    async def __anext__(self):
        return await self._queue.get()

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False


def _tick(token, bid="0.40", ask="0.44"):
    return json.dumps({
        "event_type": "best_bid_ask", "asset_id": token,
        "best_bid": bid, "best_ask": ask,
    })


async def _drive(monkeypatch, rig, refresh=0.4, flush=0.05):
    import app.tasks.base as task_base
    import app.tasks.redis_state as redis_state

    class _Refresher(blend_mod.LiveBlendRefresher):
        async def refresh(self, _event_ids):
            return None

        async def refresh_pending(self):
            return None

    class _Ctx:
        async def __aenter__(self):
            self.real = Session(rig.engine)
            return _Session(self.real, rig)

        async def __aexit__(self, exc_type, *_exc):
            try:
                if exc_type is None:
                    self.real.commit()
                else:
                    self.real.rollback()
            finally:
                self.real.close()
            return False

    monkeypatch.setattr(poly_task, "SUBSCRIPTION_REFRESH_SECONDS", refresh)
    monkeypatch.setattr(poly_task, "PRICE_FLUSH_SECONDS", flush)
    monkeypatch.setattr(blend_mod, "LiveBlendRefresher", _Refresher)
    monkeypatch.setattr(redis_state, "get_async_redis_client", lambda: rig.redis)
    monkeypatch.setattr(websockets, "connect", lambda *a, **kw: _VenueSocket(rig))
    monkeypatch.setattr(task_base, "get_task_session", lambda *a, **kw: _Ctx())
    return await poly_task._run_polymarket_ws_consumer()


def _stored(engine, outcome_id):
    with engine.connect() as conn:
        return float(conn.execute(
            text("SELECT current_probability FROM futures_outcomes WHERE id = :i"),
            {"i": outcome_id},
        ).scalar_one())


def _frames_by_token(ticks: dict):
    """Each connection is sent the ticks for the tokens IT subscribed:
    ``{token: [(delay_seconds, frame), ...]}``."""
    def frames_for(assets):
        return [
            (delay, frame)
            for token in (assets or [])
            for delay, frame in ticks.get(token, [])
        ]
    return frames_for


class TestTheConsumer:
    async def test_an_open_contracts_price_is_stored_and_announced(
        self, monkeypatch, tmp_path
    ):
        """THE SHIP. A standalone future's tick lands on its row and one frame
        goes out on its market channel."""
        engine = _database(tmp_path)
        rig = _Rig(
            engine, GAME_SLATE, (OPEN_MARKET_ROWS, OPEN_OUTCOME_ROWS),
            _frames_by_token({"711": [(0.0, _tick("711"))]}),
        )
        stats = await _drive(monkeypatch, rig)

        assert stats["errors"] == 0
        assert rig.leg_reads == [[7, 8, 9]], "legs read for the open markets only"
        assert stats["open_contract_assets"] == 3
        assert stats["open_contract_prices_written"] == 1
        assert _stored(engine, 71) == pytest.approx(0.42)
        assert [c for c, _f in rig.redis.published] == [market_channel(7)]
        assert rig.redis.published[0][1]["outcome_ids"] == [71]
        # The game socket's subscription is exactly its slate; the open one is
        # every open token and nothing the game socket carries.
        assert [GAME_TOKEN] in rig.subscribes
        assert sorted(["711", "811", "911"]) in rig.subscribes
        assert len(rig.subscribes) == 2

    async def test_the_open_socket_is_prices_only(self, monkeypatch, tmp_path):
        """A `market_resolved` for an open contract settles nothing here: the
        settlement maps stay the linked slate's."""
        engine = _database(tmp_path)
        captured = []
        real_cls = poly_svc.PolymarketWebSocket

        class _Recording(real_cls):
            def __init__(self, *a, **kw):
                super().__init__(*a, **kw)
                captured.append(self)

        monkeypatch.setattr(poly_svc, "PolymarketWebSocket", _Recording)
        resolved = json.dumps({
            "event_type": "market_resolved", "market": "0x7",
            "winning_outcome": "Yes",
        })
        rig = _Rig(
            engine, GAME_SLATE, (OPEN_MARKET_ROWS, OPEN_OUTCOME_ROWS),
            _frames_by_token({"711": [(0.0, resolved)]}),
        )
        stats = await _drive(monkeypatch, rig)

        assert stats["resolutions"] == 0
        assert rig.other_updates == []
        game, opened = captured
        assert game.on_resolved is not None
        assert opened.on_resolved is None
        assert opened.on_price is not None and opened.on_trade is not None
        assert opened._max_concurrent_handshakes == (
            open_mod.OPEN_CONTRACT_MAX_CONCURRENT_HANDSHAKES
        )

    async def test_a_failed_chunk_keeps_only_its_own_rows(
        self, monkeypatch, tmp_path
    ):
        engine = _database(tmp_path, fail_outcome=71)
        monkeypatch.setattr(open_mod, "FLUSH_CHUNK_ROWS", 1)
        rig = _Rig(
            engine, GAME_SLATE, (OPEN_MARKET_ROWS, OPEN_OUTCOME_ROWS),
            _frames_by_token({
                "711": [(0.0, _tick("711"))],
                "811": [(0.0, _tick("811", "0.60", "0.62"))],
            }),
        )
        stats = await _drive(monkeypatch, rig)

        assert _stored(engine, 81) == pytest.approx(0.61)
        assert _stored(engine, 71) == pytest.approx(0.30)
        assert [c for c, _f in rig.redis.published] == [market_channel(8)]
        assert stats["errors"] >= 1 and stats["requeued"] >= 1
        # Retried until the last drain, then reported — never silently gone.
        assert stats["final_flush_dropped"] == 1

    async def test_a_linked_quote_is_written_ahead_of_an_open_backlog(
        self, monkeypatch, tmp_path
    ):
        """The open ticks are buffered FIRST; the linked quote still commits
        first, and the open backlog drains over later flushes with none lost."""
        engine = _database(tmp_path)
        monkeypatch.setattr(open_mod, "FLUSH_CHUNK_ROWS", 1)
        monkeypatch.setattr(open_mod, "OPEN_FLUSH_CHUNKS_PER_FLUSH", 1)
        rig = _Rig(
            engine, GAME_SLATE, (OPEN_MARKET_ROWS, OPEN_OUTCOME_ROWS),
            _frames_by_token({
                "711": [(0.0, _tick("711"))],
                "811": [(0.0, _tick("811"))],
                "911": [(0.0, _tick("911"))],
                GAME_TOKEN: [(0.1, _tick(GAME_TOKEN))],
            }),
        )
        stats = await _drive(monkeypatch, rig, refresh=0.6, flush=0.2)

        channels = [c for c, _f in rig.redis.published]
        assert channels[0] == market_channel(GAME_MARKET), channels
        assert sorted(channels) == sorted(
            market_channel(m) for m in (GAME_MARKET, 7, 8, 9)
        )
        assert stats["open_contract_flush_deferred"] >= 2
        assert stats["final_flush_dropped"] == 0

    async def test_an_open_only_run_opens_no_all_markets_socket(
        self, monkeypatch, tmp_path
    ):
        engine = _database(tmp_path)
        rig = _Rig(
            engine, [[]], (OPEN_MARKET_ROWS, OPEN_OUTCOME_ROWS),
            _frames_by_token({"911": [(0.0, _tick("911"))]}),
        )
        stats = await _drive(monkeypatch, rig)

        assert None not in rig.subscribes, "an empty list subscribes to everything"
        assert rig.subscribes == [sorted(["711", "811", "911"])]
        assert _stored(engine, 91) == pytest.approx(0.42)
        assert stats["status"] == "resubscribe"

    async def test_no_slate_and_no_open_contracts_is_still_no_markets(
        self, monkeypatch, tmp_path
    ):
        engine = _database(tmp_path)
        rig = _Rig(engine, [[]], ([], []), _frames_by_token({}))
        assert await _drive(monkeypatch, rig) == {"status": "no_markets"}
        assert rig.subscribes == []
        assert rig.leg_reads == [], "no open market, no leg read"

    async def test_a_failed_read_costs_the_arm_only(self, monkeypatch, tmp_path):
        engine = _database(tmp_path)
        rig = _Rig(
            engine, GAME_SLATE, (OPEN_MARKET_ROWS, OPEN_OUTCOME_ROWS),
            _frames_by_token({GAME_TOKEN: [(0.0, _tick(GAME_TOKEN))]}),
            open_read_fails=True,
        )
        stats = await _drive(monkeypatch, rig)

        assert stats["open_contract_admission_error"] is True
        assert rig.subscribes == [[GAME_TOKEN]]
        assert _stored(engine, GAME_OUTCOME) == pytest.approx(0.42)

    async def test_a_shared_token_prices_every_leg_that_names_it(
        self, monkeypatch, tmp_path
    ):
        """#9736 THE SHIP. A board (market 10) whose leg 101 names the same
        token as standalone market 7: one tick moves BOTH rows, announces BOTH
        markets, and the token is still subscribed once."""
        board = (10, 101, "711")
        engine = _database(tmp_path, extra=[board])
        rig = _Rig(
            engine, GAME_SLATE,
            (
                [*OPEN_MARKET_ROWS, (10, None, None, {"101": "711"})],
                [*OPEN_OUTCOME_ROWS, (101, 10, "0x10", False)],
            ),
            _frames_by_token({"711": [(0.0, _tick("711"))]}),
        )
        stats = await _drive(monkeypatch, rig)

        assert stats["errors"] == 0
        assert _stored(engine, 71) == pytest.approx(0.42)
        assert _stored(engine, 101) == pytest.approx(0.42)
        assert sorted(c for c, _f in rig.redis.published) == sorted(
            [market_channel(7), market_channel(10)]
        )
        assert stats["open_contract_legs_mirrored"] == 1
        assert stats["open_contract_prices_written"] == 2
        assert sorted(["711", "811", "911"]) in rig.subscribes
        assert len(rig.subscribes) == 2

    async def test_a_game_socket_token_also_prices_an_open_leg_naming_it(
        self, monkeypatch, tmp_path
    ):
        """The owner is the game slate's leg; the open board's leg that names
        the same token is not subscribed again, yet moves on the game tick."""
        board = (10, 101, GAME_TOKEN)
        engine = _database(tmp_path, extra=[board])
        rig = _Rig(
            engine, GAME_SLATE,
            (
                [*OPEN_MARKET_ROWS, (10, None, None, {"101": GAME_TOKEN})],
                [*OPEN_OUTCOME_ROWS, (101, 10, "0x10", False)],
            ),
            _frames_by_token({GAME_TOKEN: [(0.1, _tick(GAME_TOKEN))]}),
        )
        stats = await _drive(monkeypatch, rig)

        assert _stored(engine, GAME_OUTCOME) == pytest.approx(0.42)
        assert _stored(engine, 101) == pytest.approx(0.42)
        # Only the game socket's own subscription names the game token.
        assert [a for a in rig.subscribes if GAME_TOKEN in (a or [])] == [
            [GAME_TOKEN]
        ], rig.subscribes
        assert market_channel(10) in [c for c, _f in rig.redis.published]
        assert stats["open_contract_assets_already_streaming"] == 1

    async def test_the_undo_flag_leaves_the_game_socket_alone(
        self, monkeypatch, tmp_path
    ):
        monkeypatch.setenv("POLYMARKET_WS_OPEN_CONTRACT_PRICES", "0")
        engine = _database(tmp_path)
        rig = _Rig(
            engine, GAME_SLATE, (OPEN_MARKET_ROWS, OPEN_OUTCOME_ROWS),
            _frames_by_token({"711": [(0.0, _tick("711"))]}),
        )
        stats = await _drive(monkeypatch, rig)

        assert rig.subscribes == [[GAME_TOKEN]]
        assert stats["open_contract_assets"] == 0
        assert _stored(engine, 71) == pytest.approx(0.30)
