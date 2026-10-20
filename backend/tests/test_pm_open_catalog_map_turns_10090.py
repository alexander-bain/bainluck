"""#10090 — mapping the open catalog gives the PM socket loop a turn.

Measured 2026-10-20 on worker-ws v5827: after the 50 s admission read, mapping
~62,600 open assets held the one loop that receives every Polymarket socket for
1.43 s (heartbeat max_at 21:14:39.899-21:14:41.329Z, gc_overlap 0). Every
game's quotes waited behind it. The mapping now pauses every
``OPEN_MAP_ROWS_PER_TURN`` rows and returns exactly what the plain map returns.
"""

import asyncio
import json
import random
from dataclasses import asdict

import pytest
import websockets

from app.tasks import live_blend_refresh as blend
from app.tasks import polymarket_open_contracts as open_mod
from app.tasks import polymarket_ws as task
from tests.test_pm_open_cycle_lifetime_10090 import CatalogRig, _Result, until
from tests.test_ws_consumer_session_lifetime_2471 import _install
from tests.test_ws_flush_retry_q491 import POLY_SLATE_LIVE


def _catalog(seed, markets=300):
    """Every shape the mapper reads: own tokens, legacy JSON, per-outcome
    tokens, unpaired, tokenless, shared tokens, graded legs, excluded markets,
    bridge columns, and condition ids for the by-contract mirror."""
    rng = random.Random(seed)
    conditions = [f"0x{rng.getrandbits(64):016x}" for _ in range(markets // 3)]
    tokens = [str(rng.getrandbits(60)) for _ in range(markets)]
    market_rows, outcome_rows, oid = [], [], 1000
    for mid in range(1, markets + 1):
        cond = rng.choice(conditions)
        suffixes = rng.choice(
            [("_yes", "_no"), ("_no", "_yes"), ("_yes", "_side1"), ("", "_no"),
             ("_x", "_yes"), ("_yes", "_no", "_x")]
        )
        legs = []
        for suffix in suffixes:
            legs.append(oid)
            outcome_rows.append((oid, mid, cond + suffix, rng.random() < 0.15))
            oid += 1
        own = [rng.choice(tokens) for _ in legs]
        shape = rng.random()
        a = b = by_outcome = None
        if shape < 0.45:
            a = own
        elif shape < 0.55:
            a = json.dumps(own)
        elif shape < 0.65:
            b = own
        elif shape < 0.75:
            by_outcome = {str(o): t for o, t in zip(legs, own) if rng.random() < 0.8}
        elif shape < 0.85:
            a = own[:-1]  # unpaired
        name = rng.choice(["Knicks vs. 76ers", "Will it rain?", "Spurs vs. Thunder"])
        event = rng.choice([None, 15195694, 15195695])
        market_rows.append((mid, a, b, by_outcome, event, name, cond))
    outcome_rows.sort()
    taken = set(rng.sample(tokens, 20))
    excluded = set(rng.sample(range(1, markets + 1), 15))
    by_contract = {f"{c}:0": rng.choice(tokens) for c in rng.sample(conditions, 10)}
    return market_rows, outcome_rows, taken, excluded, by_contract


def _ordered(admission):
    out = asdict(admission)
    return {k: list(v.items()) if isinstance(v, dict) else v for k, v in out.items()}


@pytest.mark.asyncio
@pytest.mark.parametrize("per_turn", [1, 7, None])
@pytest.mark.parametrize("seed", [1, 2, 3])
async def test_the_cooperative_map_returns_the_plain_map(monkeypatch, per_turn, seed):
    if per_turn is not None:
        monkeypatch.setattr(open_mod, "OPEN_MAP_ROWS_PER_TURN", per_turn)
    args = _catalog(seed)
    plain = open_mod.open_contract_asset_map(*args)
    turned = await open_mod.open_contract_asset_map_cooperatively(*args)
    assert plain.asset_to_outcome and plain.asset_mirrors and plain.complement_of
    assert _ordered(turned) == _ordered(plain)
    candidates = open_mod.open_contract_event_candidates(args[0], plain)
    assert candidates
    assert list(
        (await open_mod.open_contract_event_candidates_cooperatively(args[0], plain)).items()
    ) == list(candidates.items())


@pytest.mark.asyncio
async def test_the_loop_gets_a_turn_every_n_rows(monkeypatch):
    monkeypatch.setattr(open_mod, "OPEN_MAP_ROWS_PER_TURN", 7)
    market_rows, outcome_rows, *rest = _catalog(4)
    ticks, done = [0], asyncio.Event()

    async def ticker():
        while not done.is_set():
            ticks[0] += 1
            await asyncio.sleep(0)

    probe = asyncio.create_task(ticker())
    await asyncio.sleep(0)
    start = ticks[0]
    admission = await open_mod.open_contract_asset_map_cooperatively(
        market_rows, outcome_rows, *rest
    )
    mapped = ticks[0] - start
    start = ticks[0]
    await open_mod.open_contract_event_candidates_cooperatively(market_rows, admission)
    candidates = ticks[0] - start
    done.set()
    await probe
    # Pauses come before row 7, 14, ... of each pass, so a pass of n rows
    # pauses (n - 1) // 7 times. The ticker runs once per pause.
    assert mapped >= (len(outcome_rows) - 1) // 7 + (len(market_rows) - 1) // 7
    assert candidates >= (len(market_rows) - 1) // 7


class _BulkRig(CatalogRig):
    """The catalog rig, answering the open read with ``n`` binary markets."""

    def __init__(self, n):
        super().__init__()
        self.markets = [
            (900 + i, [f"tok{i}a", f"tok{i}b"], None, None, None, "Independent", f"0xbulk{i}")
            for i in range(n)
        ]
        self.legs = [
            row
            for i in range(n)
            for row in ((9000 + 2 * i, 900 + i, f"0xbulk{i}_yes", False),
                        (9001 + 2 * i, 900 + i, f"0xbulk{i}_no", False))
        ]

    def get_task_session(self, **kwargs):
        context, rig = super().get_task_session(**kwargs), self

        class Context:
            async def __aenter__(self):
                session = await context.__aenter__()
                route = session.execute

                async def bulk(stmt, params=None):
                    sql = str(stmt)
                    if sql == str(open_mod.open_contract_markets_stmt()):
                        await route(stmt, params)  # keeps the rig's read count
                        return _Result(rig.markets)
                    if sql == str(open_mod.open_contract_outcomes_stmt()):
                        return _Result(rig.legs)
                    return await route(stmt, params)

                session.execute = bulk
                return session

            async def __aexit__(self, *exc):
                return await context.__aexit__(*exc)

        return Context()


@pytest.mark.asyncio
async def test_the_real_consumer_maps_its_open_read_between_socket_turns(monkeypatch):
    """Through `_run_polymarket_ws_consumer`: with one row per turn, a task
    on the same loop runs between successive open markets' pairings. The
    plain map pairs every market inside one turn."""
    n = 40
    rig, stop = _BulkRig(n), asyncio.Event()
    rig.slate = POLY_SLATE_LIVE

    class Socket:
        def __init__(self):
            self.queue = asyncio.Queue()

        async def send(self, payload):
            return None

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

    ticks, seen = [0], []
    pair = task.legs_in_token_order

    def observed(legs):
        if legs and str(legs[0][1]).startswith("0xbulk"):
            seen.append(ticks[0])
        return pair(legs)

    async def ticker():
        while True:
            ticks[0] += 1
            await asyncio.sleep(0)

    _install(monkeypatch, rig)
    monkeypatch.setattr(websockets, "connect", lambda *args, **kwargs: Socket())
    monkeypatch.setattr(blend, "LiveBlendRefresher", Refresher)
    monkeypatch.setattr(task, "legs_in_token_order", observed)
    monkeypatch.setattr(open_mod, "OPEN_MAP_ROWS_PER_TURN", 1)
    monkeypatch.setattr(task, "PRICE_FLUSH_SECONDS", 10)
    monkeypatch.delenv("PM_WS_PRICE_FLUSH_SECONDS", raising=False)
    monkeypatch.setenv("POLYMARKET_WS_OPEN_CONTRACT_PRICES", "1")
    monkeypatch.setenv("WS_OPEN_CONTRACT_PRICES", "1")

    probe = asyncio.create_task(ticker())

    async def stop_after_the_first_open_map():
        await until(lambda: len(seen) >= n)
        stop.set()

    stopper = asyncio.create_task(stop_after_the_first_open_map())
    await asyncio.wait_for(task._run_polymarket_ws_consumer(stop=stop), 5)
    await stopper
    probe.cancel()
    first = seen[:n]
    assert len(set(first)) == n, first
