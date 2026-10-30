"""#10090 — ``POLYMARKET_WS_OPEN_SCOPE=slate``: the open arm keeps only what a
live or near-start market depends on.

The PM venue process is CPU-bound and the open arm streams every open
contract. Under ``slate`` the full catalog is still discovered and paired; the
finished admission is then cut to the dependency closure of its seeds (the
game socket's tokens, and every leg whose own market is on a slate event):
a kept token keeps its owner and mirrors, a kept leg keeps its binary
complement's token, to a fixed point (``scope_open_contract_admission``).

Fixtures (Sol's red-first list for A, numbered as in the brief):

1. a tokenless live board priced by an event-less binary, by condition and by
   shared token in both catalog row orders: the binary, its other leg and the
   board's bridge stay;
2. a game-owned token with open mirrors, `_side1` repaired: mirrors kept, no
   second subscription; eligible props kept, distant ones dropped;
3. the seed read IS the socket slate's event predicate (live clock-free,
   suspended arm) over the open-market clauses;
5. a binary pair the scope keeps still plans whole at the 999/1000 boundary;
4 and 6 drive the real consumer: a scope rollover keeps the dropped legs'
buffered prices, withdrawals, complements and bookkeeping through their drain;
an empty slate scope runs (adopting the previous run's debt) instead of
exiting; a failed seed read keeps the installed catalog.
"""

import asyncio
import json
import sys

import pytest
import websockets
from sqlalchemy.dialects import postgresql
from sqlalchemy.sql.dml import Update

from app.tasks import live_blend_refresh as blend
from app.tasks import polymarket_open_contracts as open_mod
from app.tasks import polymarket_ws as task
from tests._pm_slate_link_read_10663 import answer_slate_link_read
from tests._pm_slate_market_read_10663 import answer_slate_market_read
from tests.test_ws_consumer_session_lifetime_2471 import _Rig, _install
from tests.test_ws_flush_retry_q491 import POLY_SLATE, _Result


def _scope(market_rows, leg_rows, eligible, taken=(), taken_by_contract=None):
    admission = open_mod.open_contract_asset_map(
        market_rows, leg_rows, taken, (), taken_by_contract
    )
    return admission, open_mod.scope_open_contract_admission(admission, eligible, taken)


def _priced(scoped, token, prob):
    """What one tick in ``token`` prices, by the consumer's own two rules."""
    owner = scoped.asset_to_outcome.get(token)
    targets = ([owner] if owner is not None else []) + [
        oid for oid, _mid in scoped.asset_mirrors.get(token, ()) if oid != owner
    ]
    return dict(task.with_complements(targets, prob, scoped.complement_of))


# ── 1. the event-less binary behind a live board ──────────────────────────────

BOARD, BINARY, DISTANT = 600, 700, 800
BOARD_ROW = (BOARD, None, None, None, 15_000, "Cubs vs. Dodgers", "0xb0a")


def test_a_tokenless_live_board_keeps_the_eventless_binary_that_prices_it():
    markets = [
        BOARD_ROW,  # no token key at all: its legs name the contracts
        (BINARY, ["tY", "tN"], None, None, None, None, None),
        (DISTANT, ["dY", "dN"], None, None, None, None, None),
    ]
    legs = [
        (6001, BOARD, "0xc", False),
        (7001, BINARY, "0xc_yes", False),
        (7002, BINARY, "0xc_no", False),
        (8001, DISTANT, "0xd_yes", False),
        (8002, DISTANT, "0xd_no", False),
    ]
    full, scoped = _scope(markets, legs, eligible={BOARD})
    assert full.asset_mirrors["tY"] == [(6001, BOARD)]  # the #9736 repair
    # The binary's YES token (mirrored by the board) and its NO token (the
    # complement) both stay subscribed; the distant binary goes.
    assert scoped.asset_to_outcome == {"tY": 7001, "tN": 7002}
    assert scoped.asset_mirrors == {"tY": [(6001, BOARD)]}
    assert scoped.complement_of == {7001: 7002, 7002: 7001}
    assert scoped.scope == open_mod.OPEN_SCOPE_SLATE
    assert scoped.counts["scope_assets_dropped"] == 2
    # A tick on either binary token still reaches the live board's leg.
    assert _priced(scoped, "tY", 0.62) == {7001: 0.62, 6001: 0.62, 7002: 0.38}
    assert _priced(scoped, "tN", 0.40) == {7002: 0.40, 7001: pytest.approx(0.60)}
    # The live board's game-winner leg is still bridged to its event.
    assert open_mod.open_contract_event_candidates(markets, scoped) == {6001: 15_000}


@pytest.mark.parametrize("board_first", [True, False])
def test_a_shared_token_board_keeps_the_binary_in_either_catalog_order(board_first):
    board = (
        BOARD,
        ["cubs", "dodgers", "phils"],
        None,
        None,
        15_000,
        "NLDS winner",
        "0xb0a",
    )
    binary = (BINARY, ["cubs", "cubsNo"], None, None, None, None, None)
    distant = (DISTANT, ["dY", "dN"], None, None, None, None, None)
    markets = [board, binary, distant] if board_first else [binary, board, distant]
    legs = [
        (6001, BOARD, "0xb1", False),
        (6002, BOARD, "0xb2", False),
        (6003, BOARD, "0xb3", False),
        (7001, BINARY, "0xc_yes", False),
        (7002, BINARY, "0xc_no", False),
        (8001, DISTANT, "0xd_yes", False),
        (8002, DISTANT, "0xd_no", False),
    ]
    full, scoped = _scope(markets, legs, eligible={BOARD})
    kept = set(scoped.asset_to_outcome)
    assert kept == {"cubs", "dodgers", "phils", "cubsNo"}
    # Whichever market owns "cubs", the other mirrors it, and nothing moved.
    for token in kept:
        assert scoped.asset_to_outcome[token] == full.asset_to_outcome[token]
    assert scoped.asset_mirrors == full.asset_mirrors
    priced = _priced(scoped, "cubs", 0.55)
    assert priced[6001] == priced[7001] == 0.55
    assert priced[7002] == pytest.approx(0.45)
    assert scoped.counts["scope_assets_dropped"] == 2


def test_the_closure_follows_complements_across_markets_to_a_fixed_point():
    # live board leg -> binary A (yes) -> A's no token is shared with binary B
    # -> B's other leg. Every link is a real dependency; none is distant noise.
    markets = [
        BOARD_ROW,
        (701, ["aY", "aN"], None, None, None, None, None),
        (702, ["bY", "aN"], None, None, None, None, None),
        (DISTANT, ["dY", "dN"], None, None, None, None, None),
    ]
    legs = [
        (6001, BOARD, "0xa", False),
        (7011, 701, "0xa_yes", False),
        (7012, 701, "0xa_no", False),
        (7021, 702, "0xe_yes", False),
        (7022, 702, "0xe_no", False),
        (8001, DISTANT, "0xd_yes", False),
        (8002, DISTANT, "0xd_no", False),
    ]
    _full, scoped = _scope(markets, legs, eligible={BOARD})
    assert set(scoped.asset_to_outcome) == {"aY", "aN", "bY"}
    assert scoped.asset_mirrors["aN"] == [(7022, 702)]
    assert scoped.complement_of == {7011: 7012, 7012: 7011, 7021: 7022, 7022: 7021}


def test_nothing_eligible_and_nothing_taken_keeps_nothing():
    markets = [(BINARY, ["tY", "tN"], None, None, None, None, None)]
    legs = [(7001, BINARY, "0xc_yes", False), (7002, BINARY, "0xc_no", False)]
    full, scoped = _scope(markets, legs, eligible=set())
    assert full.asset_to_outcome and not scoped.asset_to_outcome
    assert scoped.asset_mirrors == {} and scoped.complement_of == {}
    assert scoped.scope == open_mod.OPEN_SCOPE_SLATE
    assert scoped.counts["scope_assets_dropped"] == 2


# ── 2. game-owned tokens: mirrors stay, nothing is subscribed twice ───────────


def test_a_game_owned_token_keeps_its_mirrors_and_is_never_subscribed_here():
    taken = {"g0", "g1"}
    markets = [
        # Distant two-sided binary naming the game socket's two tokens. Its
        # `_side1` leg holds the LOWER id (#8403): the pairing orders by suffix.
        (BINARY, ["g0", "g1"], None, None, None, None, None),
        # An eligible prop (its own event is on the slate) and a distant one.
        (901, ["pY", "pN"], None, None, 15_000, "Cubs vs. Dodgers: O/U 8.5", "0xp"),
        (902, ["qY", "qN"], None, None, 16_000, "Mets vs. Braves: O/U 7.5", "0xq"),
    ]
    legs = [
        (7001, BINARY, "0xg_side1", False),
        (7002, BINARY, "0xg", False),
        (9011, 901, "0xp_yes", False),
        (9012, 901, "0xp_no", False),
        (9021, 902, "0xq_yes", False),
        (9022, 902, "0xq_no", False),
    ]
    full, scoped = _scope(markets, legs, eligible={901}, taken=taken)
    assert full.asset_mirrors == {"g0": [(7002, BINARY)], "g1": [(7001, BINARY)]}
    assert scoped.asset_mirrors == full.asset_mirrors
    assert not taken & set(scoped.asset_to_outcome)  # no second subscription
    assert scoped.asset_to_outcome == {"pY": 9011, "pN": 9012}  # every eligible prop
    assert scoped.complement_of == {
        7001: 7002,
        7002: 7001,
        9011: 9012,
        9012: 9011,
    }
    # g0 is token 0: the `0xg` leg, never the lower-id `_side1` leg.
    assert _priced(scoped, "g0", 0.7) == {7002: 0.7, 7001: pytest.approx(0.3)}


# ── 3. the seed read is the slate's own event predicate ──────────────────────


def _sql(stmt_or_clause):
    return str(
        stmt_or_clause.compile(
            dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}
        )
    )


def test_the_seed_read_is_the_socket_slates_event_predicate_over_open_markets():
    from sqlalchemy import and_

    stmt = open_mod.open_contract_scope_markets_stmt()
    sql = _sql(stmt)
    assert "JOIN events ON futures_markets.event_id = events.id" in sql
    where = _sql(stmt.whereclause)
    assert where == _sql(
        and_(*open_mod._open_market_clauses(), task._slate_event_window())
    )
    # The live arm is clock-free; the suspended arm is part of the window.
    assert "events.status = 'live' OR" in where
    assert "events.status = 'suspended'" in where


def test_the_seed_read_follows_the_upcoming_window_setting(monkeypatch):
    monkeypatch.setattr(task, "PM_WS_UPCOMING_HOURS", 3)
    where = _sql(open_mod.open_contract_scope_markets_stmt().whereclause)
    assert "NOW() + INTERVAL '3 hours'" in where


@pytest.mark.parametrize(
    "raw, scope",
    [
        (None, "all"),
        ("", "all"),
        ("all", "all"),
        ("slate", "slate"),
        (" SLATE ", "slate"),
        ("live", "all"),
    ],
)
def test_the_flag_defaults_to_all(monkeypatch, raw, scope):
    if raw is None:
        monkeypatch.delenv("POLYMARKET_WS_OPEN_SCOPE", raising=False)
    else:
        monkeypatch.setenv("POLYMARKET_WS_OPEN_SCOPE", raw)
    assert open_mod.open_contract_scope() == scope


# ── 5. a kept binary still plans whole at the chunk boundary ─────────────────


@pytest.mark.parametrize("ahead", [499, 999])
def test_a_kept_pair_straddling_the_chunk_cap_commits_or_defers_whole(ahead):
    markets = [
        BOARD_ROW,
        (BINARY, ["tY", "tN"], None, None, None, None, None),
    ]
    legs = [
        (6001, BOARD, "0xc", False),
        (7001, BINARY, "0xc_yes", False),
        (7002, BINARY, "0xc_no", False),
    ]
    _full, scoped = _scope(markets, legs, eligible={BOARD})
    others = list(range(1, ahead + 1))
    open_ids = set(others) | {7001, 7002}
    chunks = open_mod.plan_flush_chunks(
        others + [7001, 7002],
        open_ids,
        chunk_rows=500,
        open_chunk_limit=2,
        complement_of=scoped.complement_of,
    )
    planned = [oid for chunk in chunks for oid in chunk]
    if 7001 in planned or 7002 in planned:
        (holding,) = [c for c in chunks if 7001 in c or 7002 in c]
        assert {7001, 7002} <= set(holding)
    assert (7001 in planned) == (7002 in planned)


# ── the real consumer: 4 (rollover) and 6 (empty scope, failed seed read) ────

OPEN_MARKET, OPEN_YES, OPEN_NO = 17, 171, 172
OPEN_ROWS = [(OPEN_MARKET, ["oY", "oN"], None, None, None, None, None)]
OPEN_LEGS = [
    (OPEN_YES, OPEN_MARKET, "0xo_yes", False),
    (OPEN_NO, OPEN_MARKET, "0xo_no", False),
]
EMPTY_SLATE = [[], [], []]


class ScopeRig(_Rig):
    """The PM consumer's reads, with the open catalog and the seed read
    answered per catalog read (``eligible``: a list, one entry per open read;
    an Exception entry fails that seed read)."""

    def __init__(self, slate=POLY_SLATE, eligible=(), open_rows=OPEN_ROWS):
        super().__init__([])
        self.slate = slate
        self.open_rows = open_rows
        self.eligible = list(eligible)
        self.catalog_reads = self.open_reads = self.seed_reads = 0
        self.on_slate_read = None

    def get_task_session(self, **kwargs):
        original, rig = super().get_task_session(**kwargs), self

        class Context:
            async def __aenter__(self):
                session = await original.__aenter__()
                execute = session.execute

                async def route(stmt, params=None):
                    if isinstance(stmt, Update):
                        return await execute(stmt, params)
                    sql = str(stmt)
                    if sql == str(open_mod.open_contract_markets_stmt()):
                        rig.open_reads += 1
                        return _Result(rig.open_rows)
                    if sql == str(open_mod.open_contract_outcomes_stmt()):
                        return _Result(OPEN_LEGS)
                    if sql == str(open_mod.open_contract_scope_markets_stmt()):
                        rig.seed_reads += 1
                        answer = (
                            rig.eligible[min(rig.seed_reads, len(rig.eligible)) - 1]
                            if rig.eligible
                            else []
                        )
                        if isinstance(answer, BaseException):
                            raise answer
                        return _Result([(mid,) for mid in answer])
                    if "linked_event_id" in sql:
                        rig.catalog_reads += 1
                        if rig.on_slate_read is not None:
                            rig.on_slate_read(rig.catalog_reads)
                        return _Result(answer_slate_link_read(stmt, rig.slate[0]))
                    if "futures_markets.market_metadata" in sql:
                        return _Result(answer_slate_market_read(stmt, rig.slate[1]))
                    if sql.startswith(
                        "SELECT futures_outcomes.id, futures_outcomes.market_id, "
                        "futures_outcomes.external_id"
                    ):
                        return _Result(rig.slate[2])
                    return _Result([])

                session.execute = route
                return session

            async def __aexit__(self, *exc):
                return await original.__aexit__(*exc)

        return Context()


class Socket:
    subscribed: list = []

    def __init__(self):
        self.queue = asyncio.Queue()

    async def send(self, payload):
        if payload != "PING":
            Socket.subscribed.append(tuple(json.loads(payload).get("assets_ids", ())))

    def __aiter__(self):
        return self

    async def __anext__(self):
        return await self.queue.get()

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return None


class Refresher(blend.LiveBlendRefresher):
    async def refresh(self, *args, **kwargs):
        return None

    async def refresh_pending(self, **kwargs):
        return None


def _consumer_locals():
    """The consumer's own state, when this slate read runs in its frame (the
    timer refresh does; a startup read in the admission task does not)."""
    f = sys._getframe(1)
    while f is not None and "open_asset_to_outcome" not in f.f_locals:
        f = f.f_back
    return None if f is None else f.f_locals


class Phases:
    """Slate reads in the consumer's frame once its first open catalog is
    installed: read 0 starts the first timer refresh, read k follows the
    k-th refresh's boundary."""

    def __init__(self):
        self.reads = -1

    def __call__(self):
        local = _consumer_locals()
        if local is None:
            return None, None
        if self.reads < 0 and not local["open_asset_to_outcome"]:
            return None, None
        self.reads += 1
        return self.reads, local


def _arm(monkeypatch, rig, scope):
    Socket.subscribed = []
    _install(monkeypatch, rig)
    monkeypatch.setattr(websockets, "connect", lambda *a, **k: Socket())
    monkeypatch.setattr(blend, "LiveBlendRefresher", Refresher)
    monkeypatch.setattr(task, "SUBSCRIPTION_REFRESH_SECONDS", 0.02)
    monkeypatch.setattr(task, "PRICE_FLUSH_SECONDS", 10)
    monkeypatch.delenv("PM_WS_PRICE_FLUSH_SECONDS", raising=False)
    monkeypatch.delenv("PM_WS_GAME_FLUSH_SECONDS", raising=False)
    monkeypatch.setenv("POLYMARKET_WS_OPEN_CONTRACT_PRICES", "1")
    monkeypatch.setenv("WS_OPEN_CONTRACT_PRICES", "1")
    monkeypatch.setenv("POLYMARKET_WS_OPEN_RECEIVER_PROCESS", "0")
    if scope is None:
        monkeypatch.delenv("POLYMARKET_WS_OPEN_SCOPE", raising=False)
    else:
        monkeypatch.setenv("POLYMARKET_WS_OPEN_SCOPE", scope)


@pytest.mark.asyncio
async def test_a_scope_rollover_keeps_dropped_legs_debt_through_its_drain(monkeypatch):
    """4. ``all`` -> ``slate`` mid-run drops the open binary from routing, but
    its buffered price, its withdrawal, the pair's complement and the
    per-outcome bookkeeping stay until the drain writes them."""
    rig, stop, seen = ScopeRig(eligible=[[]]), asyncio.Event(), {}
    phases = Phases()

    def on_slate_read(_n):
        n, local = phases()
        if n == 0:  # the first timer refresh starts: still the `all` catalog
            seen["before"] = dict(local["open_asset_to_outcome"])
            local["price_buffer"][OPEN_YES] = 0.61  # a failed write kept it
            local["withdraw_buffer"][OPEN_NO] = (0.05, 0.95)
            local["input_marks"][OPEN_YES] = "mark"
            local["successful_price_write_at"][OPEN_NO] = 1.0
            monkeypatch.setenv("POLYMARKET_WS_OPEN_SCOPE", "slate")
        if n == 1:  # that refresh's boundary has run, under `slate`
            seen["after"] = dict(local["open_asset_to_outcome"])
            seen["routes"] = {
                name: dict(local[name])
                for name in ("market_by_outcome", "open_complement_of")
            }
            seen["open_ids"] = set(local["open_outcome_ids"])
            seen["buffer"] = dict(local["price_buffer"])
            seen["withdraw"] = dict(local["withdraw_buffer"])
            seen["marks"] = set(local["input_marks"])
            seen["written_at"] = set(local["successful_price_write_at"])
            seen["installed"] = local["open_scope_installed"]
            stop.set()

    rig.on_slate_read = on_slate_read
    _arm(monkeypatch, rig, None)
    stats = await asyncio.wait_for(task._run_polymarket_ws_consumer(stop=stop), 30)

    assert seen["before"] == {"oY": OPEN_YES, "oN": OPEN_NO}
    assert seen["after"] == {}  # descoped: no route for a NEW input
    assert seen["installed"] is True
    assert {OPEN_YES, OPEN_NO} <= seen["open_ids"]
    assert seen["routes"]["market_by_outcome"][OPEN_YES] == OPEN_MARKET
    assert seen["routes"]["market_by_outcome"][OPEN_NO] == OPEN_MARKET
    assert seen["routes"]["open_complement_of"] == {
        OPEN_YES: OPEN_NO,
        OPEN_NO: OPEN_YES,
    }
    assert seen["buffer"][OPEN_YES] == 0.61
    assert seen["withdraw"][OPEN_NO] == (0.05, 0.95)
    assert OPEN_YES in seen["marks"] and OPEN_NO in seen["written_at"]
    assert stats["catalog_refreshes"] >= 1 and stats.get("status") != "resubscribe"
    assert stats["open_contract_scope_assets_dropped"] == 2
    # The drain wrote the descoped leg's buffered price.
    assert dict(rig.writes)[OPEN_YES] == pytest.approx(0.61)


@pytest.mark.asyncio
async def test_an_empty_slate_scope_runs_and_adopts_the_previous_runs_debt(monkeypatch):
    """6a. No game token and nothing eligible: the run used to EXIT before its
    recovery setup (``no_asset_ids``). An empty slate scope runs it: the
    previous run's owed history is adopted, nothing is subscribed, and the
    run keeps refreshing its catalog instead of recycling."""
    rig, stop = ScopeRig(slate=EMPTY_SLATE, eligible=[[]]), asyncio.Event()
    rig.on_slate_read = lambda n: stop.set() if n >= 3 else None
    _arm(monkeypatch, rig, "slate")
    monkeypatch.setitem(
        blend._history_handoff, "polymarket", ((4242, 0.5, None, None),)
    )
    stats = await asyncio.wait_for(task._run_polymarket_ws_consumer(stop=stop), 30)

    assert stats.get("status") not in ("no_asset_ids", "no_markets", "resubscribe")
    assert stats["history_pending_adopted"] == 1
    assert stats["catalog_refreshes"] >= 1
    assert stats["open_contract_assets"] == 0
    assert not any("oY" in ids or "oN" in ids for ids in Socket.subscribed)


@pytest.mark.asyncio
async def test_an_empty_all_catalog_still_exits_before_recovery(monkeypatch):
    """6a control: with ``all`` an empty catalog keeps today's exit."""
    rig = ScopeRig(slate=EMPTY_SLATE, open_rows=[])
    _arm(monkeypatch, rig, None)
    stats = await asyncio.wait_for(task._run_polymarket_ws_consumer(), 30)
    assert stats == {"status": "no_markets"}
    assert rig.seed_reads == 0


@pytest.mark.asyncio
async def test_a_failed_seed_read_keeps_the_installed_open_catalog(monkeypatch):
    """6b. Read 1 keeps the binary (its market is eligible), read 2's seed read
    fails, read 3 drops it. Between 2 and 3 the installed catalog stands and
    the failure is reported."""
    rig = ScopeRig(
        slate=POLY_SLATE,
        eligible=[
            [OPEN_MARKET],
            RuntimeError("seed read down"),
            [],
        ],
    )
    stop, seen, phases = asyncio.Event(), {}, Phases()

    def on_slate_read(_n):
        n, local = phases()
        if n in (1, 2):  # after refresh 1 (failed seed) / refresh 2 (empty)
            seen[n] = (
                dict(local["open_asset_to_outcome"]),
                local["stats"]["open_contract_admission_error"],
            )
        if n == 2:
            stop.set()

    rig.on_slate_read = on_slate_read
    _arm(monkeypatch, rig, "slate")
    await asyncio.wait_for(task._run_polymarket_ws_consumer(stop=stop), 30)

    assert rig.seed_reads >= 3
    assert seen[1] == ({"oY": OPEN_YES, "oN": OPEN_NO}, True)
    assert seen[2] == ({}, False)


@pytest.mark.asyncio
async def test_all_never_reads_the_seed(monkeypatch):
    """`all` is the arm as it is: no seed read, the full admission installed."""
    rig, stop, seen, phases = ScopeRig(), asyncio.Event(), {}, Phases()

    def on_slate_read(_n):
        n, local = phases()
        if n == 1:
            seen["open"] = dict(local["open_asset_to_outcome"])
            stop.set()

    rig.on_slate_read = on_slate_read
    _arm(monkeypatch, rig, None)
    stats = await asyncio.wait_for(task._run_polymarket_ws_consumer(stop=stop), 30)
    assert rig.seed_reads == 0
    assert seen["open"] == {"oY": OPEN_YES, "oN": OPEN_NO}
    assert not any(key.startswith("open_contract_scope_") for key in stats)
