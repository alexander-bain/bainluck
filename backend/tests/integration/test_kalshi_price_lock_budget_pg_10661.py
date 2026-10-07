"""#10661 — a held Kalshi game stops holding the games after it. Real Postgres.

## the ship

A blocked Kalshi game no longer delays independent games whose prices are ready,
and a recycle still drains the final prices safely.

## what these cases prove, against real row locks

The SHIPPED `flush_prices` and `drain_prices` closures (AST, compiled against
`app.tasks.kalshi_ws`'s own globals) run on the real `get_task_session`, the real
price UPDATE, the real #6598 re-rank and the real `LiveBlendRefresher` due/debt
bookkeeping (only its blend SQL and Redis publication are recorded). A second
connection holds a SIBLING row of game A — the re-rank must move it, so game A's
transaction waits on that row lock exactly as a competing price/rank writer makes
it wait in production.

* ``test_a_held_game_lets_the_later_games_commit`` is the ship: game A gives up
  after 500 ms and rolls back with its newer tick still buffered, while game B
  and the unrelated contract commit, publish and refresh — all before the holder
  lets go. The settled leg is still refused, and the pooled connection carries
  no `lock_timeout` afterwards.
* ``test_without_the_budget_the_held_game_stalls_every_later_game`` is the
  control: the same flush with no budget (the final-drain path, and the shape
  before #10661) leaves game B unwritten for as long as A is held.
* ``test_the_final_drain_outlasts_a_hold_longer_than_three_budgets`` is Live's
  required correction: three back-to-back drain attempts at 500 ms would drop A.
  The drain waits instead, commits after release, and drops nothing. Its own
  strawman runs the drain under the periodic budget and must drop A.
* ``test_cancelling_a_waiting_flush_keeps_every_unpaid_price``: cancelled while
  game A waits, nothing is published or lost and the pooled connection resets.

#10693: the price rows now go through the run's price pipeline, installed on
this engine and closed before it is disposed, exactly as the consumer owns it.
Game B's two legs are one consecutive no-book run, so on the supported
SQLAlchemy/asyncpg pair they are ONE pipelined round trip; on any other pair,
one execute per row. The two ``..._inside_a_pipelined_run`` cases hold a row
the PRICE write itself takes, in the middle of game A's two-row run, so the
lock wait (and the 55P03 it ends in) happens inside the pipeline's round trip,
not in the re-rank after it. ``_selected_path`` names which path ran.

Synthetic rows; ordering and safety only, not production timing.
"""

from __future__ import annotations

import ast
import asyncio
import contextlib
import logging
import os
from collections import defaultdict
from datetime import datetime, timezone
from functools import partial
from pathlib import Path

import pytest
from sqlalchemy import text

#: Shares the #837 disposable database: it creates exactly the six tables this
#: file touches, and drops them first. No fallback URL.
DB_URL = os.environ.get("BLEND_DEADLOCK_DATABASE_URL")

pytestmark = [
    pytest.mark.asyncio,
    pytest.mark.skipif(
        not DB_URL,
        reason=(
            "set BLEND_DEADLOCK_DATABASE_URL to run the real-Postgres #10661 price "
            "lock budget gate (CI job `database-integration` provisions one)"
        ),
    ),
]

SOURCE = Path(__file__).resolve().parents[2] / "app/tasks/kalshi_ws.py"

#: How long the drain case holds the sibling row. Three 500 ms budgets are
#: 1.5 s, but each attempt also pays its transaction (measured 0.58-0.76 s per
#: attempt here), so the hold must clear three whole attempts with margin or a
#: drain that kept the periodic budget is still in its third wait at release.
DRAIN_HOLD_S = 3.0


@pytest.fixture
async def pg():
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    import app.models.models  # noqa: F401 — registers every table on Base
    from app.services.database import Base

    wanted = [
        Base.metadata.tables[name]
        for name in ("sports", "teams", "venues", "events", "futures_markets", "futures_outcomes")
    ]
    # ONE pooled connection for the flush, so "the next transaction on this
    # connection has no lock_timeout" is a statement about the same backend.
    engine = create_async_engine(DB_URL, pool_size=1, max_overflow=0)
    side = create_async_engine(DB_URL, pool_size=3)
    async with side.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all, tables=wanted, checkfirst=True)
        await conn.run_sync(Base.metadata.create_all, tables=wanted)
    ids = await _seed(async_sessionmaker(side, expire_on_commit=False))
    yield engine, side, ids
    # #10693: the listener goes before the engine it is installed on.
    while _OWNERS:
        _OWNERS.pop().close()
    await engine.dispose()
    await side.dispose()


async def _seed(maker) -> dict:
    """Two live games and one unrelated contract, all on Kalshi.

    Game A has two legs; its buffered tick moves A1 above A2, so the re-rank must
    rewrite A2 — the row the holder keeps locked. Game B has a priced leg and a
    settled leg the #5411 guard must refuse.
    """
    from app.models.models import Event, FuturesMarket, FuturesOutcome, Sport

    async with maker() as session:
        sport = Sport(key="baseball_mlb", name="MLB")
        session.add(sport)
        await session.flush()
        events = {}
        for name in ("a", "b"):
            event = Event(
                sport_id=sport.id, home_team_name=f"Home {name}",
                away_team_name=f"Away {name}", commence_time=datetime.now(timezone.utc),
                status="live", win_probability_sources={},
            )
            session.add(event)
            await session.flush()
            events[name] = event.id
        markets = {}
        for name, event_id in (("a", events["a"]), ("b", events["b"]), ("x", None)):
            market = FuturesMarket(
                sport_id=sport.id, event_id=event_id, source="kalshi",
                external_id=f"KX-10661-{name}", name=f"market {name}",
            )
            session.add(market)
            await session.flush()
            markets[name] = market.id
        legs = {}
        for leg, market, prob, rank, settled in (
            ("a1", "a", 0.3, 2, None), ("a2", "a", 0.5, 1, None),
            ("b1", "b", 0.5, 1, None), ("b_settled", "b", 1.0, 1, "api_settlement"),
            ("x1", "x", 0.5, 1, None),
        ):
            outcome = FuturesOutcome(
                market_id=markets[market], name=leg, external_id=f"KX-10661-{leg}",
                current_probability=prob,
                rank=rank, resolution_source=settled,
            )
            session.add(outcome)
            await session.flush()
            legs[leg] = outcome.id
        await session.commit()
    return {"events": events, "markets": markets, "legs": legs}


class _Receipts:
    def __init__(self, trace):
        self.trace = trace

    def stage(self, marks):
        self.trace.append(("receipt", tuple(sorted(marks))))


#: #10693: every rig's price owner, closed by `pg` before engine disposal.
_OWNERS: list = []


def _rig(engine, ids, batch):
    """The shipped closures, bound to this database and a recording refresher."""
    from app.models.models import FuturesOutcome
    from app.tasks import kalshi_ws
    from app.tasks.base import get_task_session
    from app.tasks.live_blend_refresh import LiveBlendRefresher, event_ids_for_outcomes
    from app.utils.futures_rank import rerank_market_fields_stmt
    from app.utils.kalshi_price_statement import (  # #10689
        KALSHI_PRICE_STATEMENTS, kalshi_price_parameters,
    )
    from app.utils.price_change_stamp import price_changed_at_value, quote_moved_column
    from app.utils.resolution_authority import AUTHORITATIVE_SOURCES
    from sqlalchemy import func, or_, update

    legs, markets, events = ids["legs"], ids["markets"], ids["events"]
    trace: list = []

    class RecordingRefresher(LiveBlendRefresher):
        async def _refresh_batch(self, event_ids, now):
            trace.append(("refresh", tuple(sorted(event_ids))))
            for event_id in event_ids:
                self._last_refresh_at[event_id] = now

        async def publish_market_changes(self, session):
            trace.append(("publish",))

    market_of = {
        legs["a1"]: markets["a"], legs["a2"]: markets["a"],
        legs["b1"]: markets["b"], legs["b_settled"]: markets["b"],
        legs["x1"]: markets["x"],
    }
    event_of = {
        legs["a1"]: events["a"], legs["a2"]: events["a"],
        legs["b1"]: events["b"], legs["b_settled"]: events["b"],
    }
    stats = defaultdict(int)
    ns = dict(vars(kalshi_ws))
    ns.update(
        update=update, func=func, or_=or_, FuturesOutcome=FuturesOutcome,
        AUTHORITATIVE_SOURCES=AUTHORITATIVE_SOURCES,
        price_changed_at_value=price_changed_at_value,
        quote_moved_column=quote_moved_column,
        KALSHI_PRICE_STATEMENTS=KALSHI_PRICE_STATEMENTS,
        kalshi_price_parameters=kalshi_price_parameters,
        rerank_market_fields_stmt=rerank_market_fields_stmt,
        event_ids_for_outcomes=event_ids_for_outcomes,
        price_buffer=batch, buffer_lock=asyncio.Lock(),
        market_id_by_outcome=market_of, event_id_by_outcome=event_of,
        input_marks={oid: oid for oid in batch}, tail_receipts=_Receipts(trace),
        open_contract_outcome_ids=set(), blend_refresher=RecordingRefresher("kalshi"),
        get_task_session=partial(get_task_session, engine=engine),
        stats=stats, logger=logging.getLogger(__name__),
        prices=kalshi_ws._KalshiPriceOwner(),  # #10693: the run's price pipeline
    )
    _OWNERS.append(ns["prices"])
    tree = ast.parse(SOURCE.read_text())
    nodes = [n for n in ast.walk(tree) if isinstance(n, ast.AsyncFunctionDef)
             and n.name in ("flush_prices", "drain_prices")]
    assert sorted(n.name for n in nodes) == ["drain_prices", "flush_prices"]
    exec(compile(ast.Module(body=nodes, type_ignores=[]), str(SOURCE), "exec"), ns)
    return ns, trace, stats


@contextlib.asynccontextmanager
async def _holding(side, outcome_id):
    """Another writer's open transaction holding one outcome row."""
    conn = await side.connect()
    tx = await conn.begin()
    await conn.execute(
        text("UPDATE futures_outcomes SET name = name WHERE id = :id"), {"id": outcome_id}
    )
    try:
        yield tx
    finally:
        if tx.is_active:
            await tx.rollback()
        await conn.close()


async def _wait_for_a_lock_wait(side):
    async with side.connect() as conn:
        async with asyncio.timeout(5):
            while not await conn.scalar(text(
                "SELECT count(*) FROM pg_stat_activity "
                "WHERE datname = current_database() AND wait_event_type = 'Lock'"
            )):
                await asyncio.sleep(0.01)


async def _prices(side, ids) -> dict:
    async with side.connect() as conn:
        rows = (await conn.execute(text(
            "SELECT id, current_probability, rank FROM futures_outcomes"
        ))).all()
    by_id = {row.id: (float(row.current_probability), row.rank) for row in rows}
    return {leg: by_id[oid] for leg, oid in ids["legs"].items()}


def _batch(ids, a1=0.7):
    legs = ids["legs"]
    return {
        legs["a1"]: (a1, None, None), legs["b1"]: (0.6, None, None),
        legs["b_settled"]: (0.2, None, None), legs["x1"]: (0.4, None, None),
    }


async def test_a_held_game_lets_the_later_games_commit(pg):
    engine, side, ids = pg
    legs, events = ids["legs"], ids["events"]
    batch = _batch(ids)
    ns, trace, stats = _rig(engine, ids, batch)

    # A newer tick for A1 arrives inside A's transaction: after A1's UPDATE has
    # returned and before the re-rank waits on the held sibling.
    queue = ns["queue_market_change"]

    def tick_arrives(session, **kwargs):
        if legs["a1"] in kwargs["outcome_observed_at"]:
            batch[legs["a1"]] = (0.8, None, None)
        return queue(session, **kwargs)

    ns["queue_market_change"] = tick_arrives

    async with _holding(side, legs["a2"]) as held:
        assert await asyncio.wait_for(ns["flush_prices"](), 5) is False
        assert held.is_active  # all of this happened while A was still held

        stored = await _prices(side, ids)
        assert stored["a1"] == (0.3, 2)  # A rolled back, its rank untouched
        assert stored["b1"][0] == 0.6
        assert stored["b_settled"][0] == 1.0  # #5411 refusal survives
        assert stored["x1"][0] == 0.4
        assert batch == {legs["a1"]: (0.8, None, None)}  # only A, newest tick
        assert [t for t in trace if t[0] == "refresh"] == [("refresh", (events["b"],))]
        assert ("receipt", (legs["b1"],)) in trace
        assert not any(t[0] == "receipt" and legs["a1"] in t[1] for t in trace)
        assert stats["errors"] == 1 and stats["requeued"] == 1
        assert stats["settled_declined"] == 1
        assert stats["flushes"] == 1

        # Transaction-local: the pooled connection's next transaction is unbounded.
        async with engine.connect() as conn:
            assert await conn.scalar(text("SHOW lock_timeout")) == "0"

    assert await asyncio.wait_for(ns["flush_prices"](), 5) is True
    stored = await _prices(side, ids)
    assert stored["a1"] == (0.8, 1) and stored["a2"] == (0.5, 2)
    assert not batch
    assert ("refresh", (events["a"],)) in trace


async def test_without_the_budget_the_held_game_stalls_every_later_game(pg):
    engine, side, ids = pg
    legs = ids["legs"]
    batch = _batch(ids)
    ns, trace, _stats = _rig(engine, ids, batch)

    async with _holding(side, legs["a2"]) as held:
        task = asyncio.create_task(ns["flush_prices"](final_drain=True))
        await _wait_for_a_lock_wait(side)
        await asyncio.sleep(0.8)  # well past the 500 ms budget
        assert not task.done()
        assert (await _prices(side, ids))["b1"][0] == 0.5  # B is still waiting
        assert not any(t[0] in ("publish", "refresh") for t in trace)
        await held.rollback()
        assert await asyncio.wait_for(task, 5) is True
    stored = await _prices(side, ids)
    assert stored["a1"] == (0.7, 1) and stored["b1"][0] == 0.6
    assert not batch


async def test_the_final_drain_outlasts_a_hold_longer_than_three_budgets(pg):
    engine, side, ids = pg
    legs = ids["legs"]
    batch = _batch(ids)
    ns, _trace, stats = _rig(engine, ids, batch)

    async with _holding(side, legs["a2"]) as held:
        task = asyncio.create_task(ns["drain_prices"]())
        await _wait_for_a_lock_wait(side)
        await asyncio.sleep(DRAIN_HOLD_S)
        assert not task.done()
        await held.rollback()
        await asyncio.wait_for(task, 5)
    assert stats["final_flush_dropped"] == 0
    assert not batch
    assert (await _prices(side, ids))["a1"] == (0.7, 1)


async def test_strawman_a_drain_under_the_periodic_budget_drops_the_held_game(pg):
    """Proves the drain case can fail: the same drain on the periodic flush
    gives up three times inside the hold and strands game A's price."""
    engine, side, ids = pg
    legs = ids["legs"]
    batch = _batch(ids)
    ns, _trace, stats = _rig(engine, ids, batch)
    tree = ast.parse(SOURCE.read_text())
    (node,) = [n for n in ast.walk(tree) if isinstance(n, ast.AsyncFunctionDef)
               and n.name == "drain_prices"]
    body = ast.unparse(node)
    assert body.count("flush_prices(final_drain=True)") == 1
    exec(body.replace("flush_prices(final_drain=True)", "flush_prices()"), ns)

    async with _holding(side, legs["a2"]) as held:
        await asyncio.wait_for(ns["drain_prices"](), DRAIN_HOLD_S + 3)
        assert held.is_active
    assert stats["final_flush_dropped"] == 1
    assert (await _prices(side, ids))["a1"] == (0.3, 2)


async def test_cancelling_a_waiting_flush_keeps_every_unpaid_price(pg):
    engine, side, ids = pg
    legs = ids["legs"]
    batch = _batch(ids)
    before = dict(batch)
    ns, trace, _stats = _rig(engine, ids, batch)
    # Still the periodic path and its transaction-local SET, with a budget long
    # enough that the cancel always lands inside the wait, not after it.
    ns["PRICE_PHASE_LOCK_TIMEOUT_MS"] = 10_000

    async with _holding(side, legs["a2"]):
        task = asyncio.create_task(ns["flush_prices"]())
        await _wait_for_a_lock_wait(side)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
    assert batch == before
    assert not any(t[0] in ("publish", "refresh", "receipt") for t in trace)
    assert (await _prices(side, ids))["a1"] == (0.3, 2)
    async with engine.connect() as conn:
        assert await conn.scalar(text("SHOW lock_timeout")) == "0"


# ------------------------------------------------- #10693 pipelined runs ----


def _selected_path(engine):
    """Record whether a price write ran as one executemany round trip.

    The pipelined path is a driver executemany of the price template; the
    ordinary path is one execute per row. Which one ran is a fact about the
    installed SQLAlchemy/asyncpg pair, so the cases assert it against that.
    """
    from sqlalchemy import event

    seen = []

    def before(_conn, _cursor, statement, _params, _context, executemany):
        if statement.lstrip().upper().startswith("UPDATE FUTURES_OUTCOMES SET CURRENT_PROBABILITY"):
            seen.append(executemany)

    event.listen(engine.sync_engine, "before_cursor_execute", before)
    return seen


def _pipelined_expected():
    from app.utils.kalshi_price_pipeline import _load_compatibility

    return _load_compatibility() is not None


def _pipelined_batch(ids):
    """Game A's two legs buffered together: one consecutive two-row run."""
    legs = ids["legs"]
    return {
        legs["a1"]: (0.7, None, None), legs["a2"]: (0.2, None, None),
        legs["b1"]: (0.6, None, None), legs["b_settled"]: (0.2, None, None),
        legs["x1"]: (0.4, None, None),
    }


async def test_a_held_row_inside_a_pipelined_run_lets_the_later_games_commit(pg):
    engine, side, ids = pg
    legs, events = ids["legs"], ids["events"]
    batch = _pipelined_batch(ids)
    ns, trace, stats = _rig(engine, ids, batch)
    path = _selected_path(engine)

    async with _holding(side, legs["a2"]) as held:
        assert await asyncio.wait_for(ns["flush_prices"](), 5) is False
        assert held.is_active

        stored = await _prices(side, ids)
        assert stored["a1"] == (0.3, 2) and stored["a2"] == (0.5, 1)  # A rolled back whole
        assert stored["b1"][0] == 0.6
        assert stored["b_settled"][0] == 1.0  # #5411 refusal survives the pipeline
        assert stored["x1"][0] == 0.4
        assert batch == {legs["a1"]: (0.7, None, None), legs["a2"]: (0.2, None, None)}
        assert [t for t in trace if t[0] == "refresh"] == [("refresh", (events["b"],))]
        assert not any(t[0] == "receipt" and legs["a1"] in t[1] for t in trace)
        assert stats["errors"] == 1 and stats["requeued"] == 2
        assert stats["settled_declined"] == 1
        async with engine.connect() as conn:
            assert await conn.scalar(text("SHOW lock_timeout")) == "0"

    assert await asyncio.wait_for(ns["flush_prices"](), 5) is True
    stored = await _prices(side, ids)
    assert stored["a1"] == (0.7, 1) and stored["a2"] == (0.2, 2)
    assert not batch
    assert any(path) is _pipelined_expected(), (path, _pipelined_expected())


async def test_the_final_drain_outlasts_a_hold_inside_a_pipelined_run(pg):
    engine, side, ids = pg
    legs = ids["legs"]
    batch = _pipelined_batch(ids)
    ns, _trace, stats = _rig(engine, ids, batch)
    path = _selected_path(engine)

    async with _holding(side, legs["a2"]) as held:
        task = asyncio.create_task(ns["drain_prices"]())
        await _wait_for_a_lock_wait(side)
        await asyncio.sleep(DRAIN_HOLD_S)
        assert not task.done()
        await held.rollback()
        await asyncio.wait_for(task, 5)
    assert stats["final_flush_dropped"] == 0
    assert not batch
    stored = await _prices(side, ids)
    assert stored["a1"] == (0.7, 1) and stored["a2"] == (0.2, 2)
    assert any(path) is _pipelined_expected(), (path, _pipelined_expected())
