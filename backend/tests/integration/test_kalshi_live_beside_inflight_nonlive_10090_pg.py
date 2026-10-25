"""#10090 — a live quote arriving DURING a slow non-live price transaction.

## the ship

New live probabilities reach the held event headline and chart promptly even
when an unrelated non-live price transaction is slow.

## the mechanism (v5679 aftercheck, 2026-10-12 21:25:44Z)

Production's slowest Kalshi flush that minute was one non-live phase of 200
rows taking 3.50 s inside its transaction (save 1.50 s, rerank 2.01 s) with no
stamp wait. Live preemption (`live_preempts_tail`) is checked only BEFORE a
non-live phase starts, so a live tick that arrives once that transaction is
running waits for whatever is left of it, then for the next flush.

## the rig

The SHIPPED `flush_prices`, `drain_prices`, `handle_ticker` and `_parse_dollar`
closures (AST, compiled against `app.tasks.kalshi_ws`'s own globals), driven by
the SHIPPED `run_flush_cadence` at production's override (0.25 s period, 2 s
failed retry, wake + work count, the refresher's floor at the period), on the
real `get_task_session` over a five-connection pool (the consumer's), the real
price pipeline, price statement and re-rank, a real `LiveBlendRefresher`
(only its blend SQL is recorded) and the real `publish_committed_market_changes`,
whose Redis publication reads the market's rows back on an INDEPENDENT
connection. Live quotes enter through `handle_ticker` as ticker frames.

The non-live transaction is made slow by a ``BEFORE UPDATE`` trigger that calls
``pg_sleep`` when the non-live market's price changes: a server-side delay
INSIDE the real transaction on the real pooled connection, holding its row
locks until it commits. It is the deterministic stand-in for production's
3.5 s phase; it says nothing about why production's phase was slow.

Synthetic rows; order, coherence and progress — not production timing.
"""

from __future__ import annotations

import ast
import asyncio
import contextlib
import json
import logging
import os
import time
from collections import defaultdict
from datetime import datetime, timezone
from functools import partial
from pathlib import Path
from types import SimpleNamespace

import pytest
from sqlalchemy import text

#: Shares the #837/#10661 disposable database: it creates exactly the tables
#: this file touches, and drops them first. No fallback URL.
DB_URL = os.environ.get("BLEND_DEADLOCK_DATABASE_URL")

pytestmark = [
    pytest.mark.asyncio,
    pytest.mark.skipif(
        not DB_URL,
        reason=(
            "set BLEND_DEADLOCK_DATABASE_URL to run the real-Postgres #10090 "
            "live-beside-in-flight gate (CI job `database-integration` provisions one)"
        ),
    ),
]

SOURCE = Path(__file__).resolve().parents[2] / "app/tasks/kalshi_ws.py"
PERIOD = 0.25  # production's KALSHI_WS_PRICE_FLUSH_SECONDS
FAILED_RETRY = 2.0
#: How long the non-live transaction sleeps inside its price UPDATE.
SLOW_S = 4.0
#: The ship's bound, arrival -> committed, published and read back. Asserted
#: together with the ORDER it needs: served while the non-live row is still
#: uncommitted. Measured ages are also printed (`EVIDENCE`).
BOUND_S = 1.0

TABLES = (
    "sports", "teams", "venues", "events", "futures_markets", "futures_outcomes",
    "win_prob_snapshots",
)

BLOCKER_SQL = (
    "CREATE TABLE bl_inflight_blocker (market_id integer PRIMARY KEY, seconds float8 NOT NULL)",
    """
    CREATE FUNCTION bl_inflight_blocker() RETURNS trigger LANGUAGE plpgsql AS $$
    DECLARE s float8;
    BEGIN
      IF NEW.current_probability IS DISTINCT FROM OLD.current_probability THEN
        SELECT seconds INTO s FROM bl_inflight_blocker WHERE market_id = NEW.market_id;
        IF s IS NOT NULL THEN PERFORM pg_sleep(s); END IF;
      END IF;
      RETURN NEW;
    END $$
    """,
    "CREATE TRIGGER bl_inflight_blocker BEFORE UPDATE ON futures_outcomes "
    "FOR EACH ROW EXECUTE FUNCTION bl_inflight_blocker()",
)
UNBLOCK_SQL = (
    "DROP FUNCTION IF EXISTS bl_inflight_blocker() CASCADE",
    "DROP TABLE IF EXISTS bl_inflight_blocker",
)


@pytest.fixture
async def pg():
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    import app.models.models  # noqa: F401 — registers every table on Base
    from app.services.database import Base

    wanted = [Base.metadata.tables[name] for name in TABLES]
    # The consumer's own pool shape (`_get_task_engine(retain_full_pool=True)`).
    engine = create_async_engine(DB_URL, pool_size=5, max_overflow=0)
    side = create_async_engine(DB_URL, pool_size=4)
    async with side.begin() as conn:
        for sql in UNBLOCK_SQL:
            await conn.execute(text(sql))
        await conn.run_sync(Base.metadata.drop_all, tables=wanted, checkfirst=True)
        await conn.run_sync(Base.metadata.create_all, tables=wanted)
        for sql in BLOCKER_SQL:
            await conn.execute(text(sql))
    ids = await _seed(async_sessionmaker(side, expire_on_commit=False))
    await _warm(engine, 5, ids)
    await _warm(side, 4)
    try:
        yield engine, side, ids
    finally:
        while _OWNERS:
            _OWNERS.pop().close()
        await engine.dispose()
        async with side.begin() as conn:
            for sql in UNBLOCK_SQL:
                await conn.execute(text(sql))
        await side.dispose()


async def _warm(engine, size, ids=None):
    """Open the pool's connections first, as a running consumer's are, and
    (``ids``) run the flush's own price and re-rank writes once on each,
    rolled back, so each backend's first-use costs are paid as a running
    consumer's are. Timings then measure the flush, not connection setup."""
    from app.utils.futures_rank import rerank_market_fields_stmt
    from app.utils.kalshi_price_statement import (
        KALSHI_PRICE_STATEMENTS, kalshi_price_parameters,
    )

    async with contextlib.AsyncExitStack() as stack:
        for _ in range(size):
            conn = await stack.enter_async_context(engine.connect())
            if ids is None:
                await conn.execute(text("SELECT 1"))
                continue
            async with conn.begin() as tx:
                for leg, book in (("home", False), ("away", True)):
                    await conn.execute(
                        KALSHI_PRICE_STATEMENTS[book],
                        kalshi_price_parameters(
                            ids["legs"][leg], 0.9, *((0.89, 0.91) if book else (None, None)), True,
                        ),
                    )
                await conn.execute(rerank_market_fields_stmt(sorted(ids["markets"].values())))
                await tx.rollback()


async def _seed(maker) -> dict:
    """A live game, a pre-game game and a standalone non-live market, two legs each."""
    from app.models.models import Event, FuturesMarket, FuturesOutcome, Sport

    async with maker() as session:
        sport = Sport(key="baseball_mlb", name="MLB")
        session.add(sport)
        await session.flush()
        events = {}
        for name, status in (("live", "live"), ("pregame", "scheduled")):
            event = Event(
                sport_id=sport.id, home_team_name=f"Home {name}",
                away_team_name=f"Away {name}", commence_time=datetime.now(timezone.utc),
                status=status, win_probability_sources={},
            )
            session.add(event)
            await session.flush()
            events[name] = event.id
        markets = {}
        for name, event_id in (
            ("live", events["live"]), ("pregame", events["pregame"]), ("nonlive", None),
        ):
            market = FuturesMarket(
                sport_id=sport.id, event_id=event_id, source="kalshi",
                external_id=f"KX10090IF-{name}", name=f"market {name}",
            )
            session.add(market)
            await session.flush()
            markets[name] = market.id
        legs = {}
        for leg, market, prob, rank in (
            ("home", "live", 0.40, 2), ("away", "live", 0.60, 1),
            ("p1", "pregame", 0.45, 2), ("p2", "pregame", 0.55, 1),
            ("x1", "nonlive", 0.30, 2), ("x2", "nonlive", 0.70, 1),
        ):
            outcome = FuturesOutcome(
                market_id=markets[market], name=leg,
                external_id=f"KX10090IF-{leg.upper()}", current_probability=prob,
                rank=rank,
            )
            session.add(outcome)
            await session.flush()
            legs[leg] = outcome.id
        await session.commit()
    return {"event": events["live"], "events": events, "markets": markets, "legs": legs}


class _Receipts:
    exact_trace = None

    def note_raw(self, _event_id):
        return None

    def note_input(self, _event_id, outcome_id, _prob, _kind):
        return outcome_id

    def stage(self, _marks):
        return None


class _Pool:
    """A Redis pool whose PUBLISH is a callback (`publish_committed_market_changes`)."""

    def __init__(self, publish):
        self.publish = publish

    async def get_connection(self, *_a):
        return self

    async def release(self, _conn):
        return None

    def pack_commands(self, commands):
        return list(commands)

    async def send_packed_command(self, commands, **_kw):
        for verb, channel, payload in commands:
            assert verb == "PUBLISH"
            await self.publish(channel, payload)

    async def read_response(self, **_kw):
        return 0

    async def disconnect(self):
        return None


#: Every rig's price owner, closed by `pg` before engine disposal (#10693).
_OWNERS: list = []


def _rig(engine, side, ids, source=None):
    """The shipped closures on this database; returns (ns, record).

    ``source`` replaces the module text (strawman only).
    """
    from sqlalchemy import func, or_, update

    from app.models.models import FuturesOutcome
    from app.tasks import kalshi_ws
    from app.tasks.base import get_task_session
    from app.tasks.kalshi import _kalshi_yes_probability
    from app.tasks.live_blend_refresh import LiveBlendRefresher, event_ids_for_outcomes
    from app.utils.kalshi_primary_quote import PrimaryQuoteCustody
    from app.utils.futures_rank import rerank_market_fields_stmt
    from app.utils.kalshi_price_statement import (
        KALSHI_PRICE_STATEMENTS, kalshi_price_parameters,
    )
    from app.utils.price_change_stamp import price_changed_at_value, quote_moved_column
    from app.utils.resolution_authority import AUTHORITATIVE_SOURCES

    legs, markets = ids["legs"], ids["markets"]
    # ``hold_first_stamp_s``: the first stamp holds its event that long.
    record = SimpleNamespace(publications=[], stamps=[], stamp_started=[],
                             hold_first_stamp_s=0.0)

    async def committed():
        """Every row's committed price, read on an independent connection."""
        async with side.connect() as conn:
            rows = (await conn.execute(text(
                "SELECT id, current_probability FROM futures_outcomes ORDER BY id"
            ))).all()
        return {row.id: float(row.current_probability) for row in rows}

    class RecordingRefresher(LiveBlendRefresher):
        async def _refresh_batch(self, event_ids, now, *, on_committed=None, **_kw):
            for event_id in event_ids:
                self._last_refresh_at[event_id] = now
            record.stamp_started.append((time.monotonic(), tuple(sorted(event_ids))))
            if record.hold_first_stamp_s and len(record.stamp_started) == 1:
                await asyncio.sleep(record.hold_first_stamp_s)
            # What the stamp would read: the committed rows.
            values = await committed()
            record.stamps.append((time.monotonic(), tuple(sorted(event_ids)), values))
            if on_committed is not None:
                on_committed(list(event_ids))

    async def publish(_channel, payload):
        frame = json.loads(payload)
        values = await committed()
        record.publications.append((time.monotonic(), frame["market_id"], values))

    refresher = RecordingRefresher(
        "kalshi", session_factory=partial(get_task_session, engine=engine),
        min_refresh_interval_s=PERIOD,
    )
    refresher._redis = SimpleNamespace(connection_pool=_Pool(publish))
    market_of = {
        legs["home"]: markets["live"], legs["away"]: markets["live"],
        legs["p1"]: markets["pregame"], legs["p2"]: markets["pregame"],
        legs["x1"]: markets["nonlive"], legs["x2"]: markets["nonlive"],
    }
    pregame = ids["events"]["pregame"]
    event_of = {
        legs["home"]: ids["event"], legs["away"]: ids["event"],
        legs["p1"]: pregame, legs["p2"]: pregame,
    }
    prices = kalshi_ws._KalshiPriceOwner()
    prices.timings = kalshi_ws._FlushTimings()
    _OWNERS.append(prices)
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
        _kalshi_yes_probability=_kalshi_yes_probability,
        price_buffer={}, buffer_lock=asyncio.Lock(), input_marks={},
        # #10090: the worker's primary-quote custody (bundled pair).
        primary_quote_custody=PrimaryQuoteCustody(),
        observation_continuity={}, game_clients=[],
        market_id_by_outcome=market_of, event_id_by_outcome=event_of,
        tail_receipts=_Receipts(), open_contract_outcome_ids=set(),
        blend_refresher=refresher, non_blend_outcome_ids=set(),
        get_task_session=partial(get_task_session, engine=engine),
        stats=defaultdict(int), logger=logging.getLogger(__name__), prices=prices,
        live_event_ids={ids["event"]}, flush_budget=None, flush_period=PERIOD,
        # handle_ticker's consumer state
        ticker_owner={}, open_contract_ids={}, winner_quoted_at={},
        ticker_to_ids={
            f"KX10090IF-{leg.upper()}": (market_of[oid], oid)
            for leg, oid in legs.items()
        },
        flush_wake=asyncio.Event(), admission_wake=asyncio.Event(),
    )
    tree = ast.parse(source or SOURCE.read_text())
    wanted = ("flush_prices", "drain_prices", "handle_ticker", "_parse_dollar",
              "steady_book_signature", "observation_signature", "note_observation_continuity")
    nodes = [n for n in ast.walk(tree)
             if isinstance(n, (ast.AsyncFunctionDef, ast.FunctionDef)) and n.name in wanted]
    assert sorted(n.name for n in nodes) == sorted(wanted)
    exec(compile(ast.Module(body=nodes, type_ignores=[]), str(SOURCE), "exec"), ns)
    prices.input_wake = ns["flush_wake"]  # as the consumer points it
    return ns, record


async def _tick(ns, leg, bid, ask):
    await ns["handle_ticker"]({
        "market_ticker": f"KX10090IF-{leg.upper()}",
        "yes_bid_dollars": f"{bid:.2f}", "yes_ask_dollars": f"{ask:.2f}",
    })


async def _wait_until(predicate, timeout, step=0.01):
    async with asyncio.timeout(timeout):
        while not await predicate():
            await asyncio.sleep(step)


async def _sleeping(side):
    async with side.connect() as conn:
        return bool(await conn.scalar(text(
            "SELECT count(*) FROM pg_stat_activity "
            "WHERE datname = current_database() AND wait_event = 'PgSleep'"
        )))


async def _stored(side):
    async with side.connect() as conn:
        rows = (await conn.execute(text(
            "SELECT id, market_id, current_probability, rank, "
            "rank() OVER (PARTITION BY market_id ORDER BY current_probability "
            "DESC NULLS LAST) AS field FROM futures_outcomes ORDER BY id"
        ))).all()
    return {row.id: (float(row.current_probability), row.rank, row.field) for row in rows}


@contextlib.asynccontextmanager
async def _consumer(ns):
    """The consumer's `timed_flush` + `flush_loop` (failed-retry override)."""
    from app.tasks.live_blend_refresh import run_flush_cadence

    gate = asyncio.Lock()
    stop = asyncio.Event()
    prices = ns["prices"]

    async def timed_flush(flush_started):
        async with gate:
            started = time.monotonic()
            try:
                return await ns["flush_prices"](flush_started)
            finally:
                prices.timings.flushed(time.monotonic() - started)

    cadence = asyncio.create_task(run_flush_cadence(
        timed_flush, PERIOD, stop=stop, failed_retry_interval_s=FAILED_RETRY,
        wake=ns["flush_wake"], work_count=lambda: prices.flush_work,
    ))
    try:
        yield
    finally:
        stop.set()
        await asyncio.wait_for(cadence, 15)
        await asyncio.wait_for(ns["drain_prices"](), 15)
        await asyncio.wait_for(prices.join_stamp(ns["blend_refresher"]), 15)


def _first(seq, predicate):
    return next((item for item in seq if predicate(item)), None)




async def _block(side, market_id, seconds):
    async with side.begin() as conn:
        await conn.execute(text(
            "INSERT INTO bl_inflight_blocker VALUES (:m, :s) "
            "ON CONFLICT (market_id) DO UPDATE SET seconds = EXCLUDED.seconds"
        ), {"m": market_id, "s": seconds})


async def _unblock(side):
    async with side.begin() as conn:
        await conn.execute(text("DELETE FROM bl_inflight_blocker"))


async def _sleepers(side):
    async with side.connect() as conn:
        return await conn.scalar(text(
            "SELECT count(*) FROM pg_stat_activity "
            "WHERE datname = current_database() AND wait_event = 'PgSleep'"
        ))


async def _late_live_quotes(ns, record, side, ids):
    """The case: a slow non-live phase in flight, then live input.

    Returns the measurements; asserts nothing about the outcome.
    """
    legs, markets = ids["legs"], ids["markets"]
    live, home, x1 = markets["live"], legs["home"], legs["x1"]
    await _block(side, markets["nonlive"], SLOW_S)

    async def x1_committed():
        return (await _stored(side))[x1][0] == 0.80

    async def control_published():
        return any(v.get(home) == 0.74 for _t, m, v in record.publications if m == live)

    async with _consumer(ns):
        await _tick(ns, "x1", 0.79, 0.81)  # the non-live phase: sleeps in its UPDATE
        await _wait_until(lambda: _sleeping(side), 5)
        in_flight = time.monotonic()
        # 1. A changed live quote arrives inside that transaction (both legs).
        t1 = time.monotonic()
        await _tick(ns, "home", 0.64, 0.66)
        await _tick(ns, "away", 0.34, 0.36)
        await asyncio.sleep(0.4)
        # An equal repeat: not new input, and it does not reset anyone's age.
        await _tick(ns, "home", 0.64, 0.66)
        await asyncio.sleep(0.4)
        # 2. A later changed live quote, still inside the same transaction.
        t2 = time.monotonic()
        await _tick(ns, "home", 0.69, 0.71)
        await _tick(ns, "away", 0.29, 0.31)
        await _wait_until(x1_committed, SLOW_S + 5)
        released = time.monotonic()
        # 3. After-release control: the same path with nothing in flight.
        await asyncio.sleep(0.3)
        t3 = time.monotonic()
        await _tick(ns, "home", 0.73, 0.75)
        await _tick(ns, "away", 0.25, 0.27)
        await _wait_until(control_published, 5)

    live_pubs = [(t, v[home]) for t, m, v in record.publications if m == live]

    def served(since, value):
        """Seconds from ``since`` to the first live publication of ``value``."""
        hit = _first(live_pubs, lambda p: p[0] >= since and p[1] == value)
        return None if hit is None else round(hit[0] - since, 3)

    ages = {"first": served(t1, 0.65), "second": served(t2, 0.70),
            "control": served(t3, 0.74)}
    # What the non-live row held, committed, when each live value was served.
    beside_of = {}
    for _t, mk, v in record.publications:
        if mk == live:
            beside_of.setdefault(v[home], v[x1])
    evidence = (
        f"ages {ages}; non-live committed {released - in_flight:.2f}s after it "
        f"started; live publications (s after first arrival, home): "
        f"{[(round(t - t1, 3), v) for t, v in live_pubs]}"
    )
    print("EVIDENCE", evidence)
    return SimpleNamespace(
        ages=ages, evidence=evidence, t1=t1, t2=t2, released=released,
        in_flight=in_flight, nonlive_when_served=beside_of,
    )


async def test_a_live_quote_arriving_inside_a_slow_nonlive_transaction_publishes_promptly(pg):
    engine, side, ids = pg
    legs, markets = ids["legs"], ids["markets"]
    live, nonlive = markets["live"], markets["nonlive"]
    home, away, x1 = legs["home"], legs["away"], legs["x1"]
    ns, record = _rig(engine, side, ids)
    m = await _late_live_quotes(ns, record, side, ids)
    ages, evidence = m.ages, m.evidence

    # Observed from outside (PgSleep seen, commit seen), so it reads short.
    assert m.released - m.in_flight >= SLOW_S / 2, "the non-live transaction was not slow"
    assert ages["control"] is not None and ages["control"] < BOUND_S, evidence
    # Neither changed live quote waits for — or is coalesced behind — the
    # non-live commit: each is published, itself, inside the bound, before it.
    assert ages["first"] is not None and ages["second"] is not None, evidence
    assert ages["first"] < BOUND_S and ages["second"] < BOUND_S, evidence
    # Both were served while the non-live transaction was still uncommitted.
    assert m.nonlive_when_served[0.65] == m.nonlive_when_served[0.70] == 0.30, (
        m.nonlive_when_served, evidence,
    )
    # The headline's stamp read each committed live value, also before it.
    for value in (0.65, 0.70):
        stamp = _first(record.stamps, lambda s, v=value: s[2].get(home) == v)
        assert stamp is not None and stamp[2][x1] == 0.30, (value, record.stamps)
    # Whole-event coherence: every live publication and stamp read both legs
    # of one quote, never half of one.
    for values in [v for _t, mk, v in record.publications if mk == live] + [
        v for _t, _e, v in record.stamps
    ]:
        assert round(values[home] + values[away], 4) == 1.0, values
    # Publish after commit: no live publication preceded its input.
    assert all(p[0] >= m.t1 for p in record.publications if p[1] == live)
    assert ns["stats"]["live_beside"] == 4  # two quotes, two legs each

    # Non-live recovered: written once, at its value, and published.
    stored = await _stored(side)
    assert stored[x1][0] == 0.80 and stored[home][0] == 0.74 and stored[away][0] == 0.26
    assert all(rank == field for _p, rank, field in stored.values()), stored
    assert len([p for p in record.publications if p[1] == nonlive]) == 1
    assert not ns["price_buffer"]
    assert not ns["prices"].lock_retry_until
    assert ns["stats"]["errors"] == 0 and ns["stats"]["final_flush_dropped"] == 0


async def test_strawman_without_the_beside_writer_the_live_quote_waits_for_the_commit(pg):
    """Proves the case can fail: the same source with the writer never started
    (the shape before this change) holds both live quotes behind the commit."""
    engine, side, ids = pg
    text_ = SOURCE.read_text()
    start = "beside_task = asyncio.create_task(serve_live_beside())"
    assert text_.count(start) == 1
    ns, record = _rig(engine, side, ids, source=text_.replace(start, "pass"))
    m = await _late_live_quotes(ns, record, side, ids)
    assert m.ages["control"] is not None and m.ages["control"] < BOUND_S, m.evidence
    # The first quote is never shown (superseded while it waited), and the
    # second is published only after the non-live commit.
    assert m.ages["first"] is None, m.evidence
    assert m.ages["second"] is not None and m.ages["second"] >= BOUND_S, m.evidence
    assert m.nonlive_when_served[0.70] == 0.80, (m.nonlive_when_served, m.evidence)
    assert ns["stats"]["live_beside"] == 0


async def test_continuing_live_input_never_starves_the_nonlive_phase(pg):
    """Live quotes every 0.3 s for the whole slow phase: each is published
    inside the bound, and the non-live phase still commits on its own clock."""
    engine, side, ids = pg
    legs, markets = ids["legs"], ids["markets"]
    live, home, x1 = markets["live"], legs["home"], legs["x1"]
    ns, record = _rig(engine, side, ids)
    await _block(side, markets["nonlive"], SLOW_S)
    sent = []

    async def x1_committed():
        return (await _stored(side))[x1][0] == 0.80

    async with _consumer(ns):
        await _tick(ns, "x1", 0.79, 0.81)
        await _wait_until(lambda: _sleeping(side), 5)
        in_flight = time.monotonic()
        k = 0
        while not await x1_committed():
            k += 1
            value = round(0.50 + 0.01 * k, 2)
            sent.append((time.monotonic(), value))
            await _tick(ns, "home", value - 0.01, value + 0.01)
            await _tick(ns, "away", 0.99 - value, 1.01 - value)
            await asyncio.sleep(0.3)
            assert k < 40, "the non-live phase never committed"
        released = time.monotonic()
        await asyncio.sleep(BOUND_S)

    assert released - in_flight < SLOW_S + 1.0, "live work starved the non-live phase"
    live_pubs = [(t, v[home]) for t, mk, v in record.publications if mk == live]
    # Each quote is served, or superseded by a later one that is served,
    # inside the bound: the age of the oldest still-owed quote. Intermediate
    # quotes may coalesce; the latest owed state may not wait.
    late, ages = [], []
    for k, (t, _value) in enumerate(sent):
        newer = {v for _t, v in sent[k:]}
        hit = _first(live_pubs, lambda p, t=t, newer=newer: p[0] >= t and p[1] in newer)
        ages.append(None if hit is None else round(hit[0] - t, 3))
        if hit is None or hit[0] - t >= BOUND_S or hit[0] >= released:
            late.append((round(t - in_flight, 3), _value, ages[-1]))
    print("EVIDENCE continuing:", len(sent), "quotes; oldest-owed ages", ages, "late", late)
    assert len(sent) >= 6 and not late, (len(sent), late)
    stored = await _stored(side)
    assert stored[home][0] == sent[-1][1] and stored[x1][0] == 0.80
    assert all(rank == field for _p, rank, field in stored.values()), stored
    assert not ns["price_buffer"] and ns["stats"]["errors"] == 0


async def test_an_event_with_rows_in_the_inflight_phase_is_never_written_beside_it(pg):
    """A pre-game game's phase is in flight when the game turns live: its next
    quote is NOT written beside it (same cohort), only after it commits; an
    independent live game's quote is."""
    engine, side, ids = pg
    legs, markets, events = ids["legs"], ids["markets"], ids["events"]
    home, p1, p2 = legs["home"], legs["p1"], legs["p2"]
    ns, record = _rig(engine, side, ids)
    await _block(side, markets["pregame"], SLOW_S)

    async def pregame_committed():
        return (await _stored(side))[p1][0] == 0.60

    async with _consumer(ns):
        await _tick(ns, "p1", 0.59, 0.61)  # pre-game phase: non-live, sleeps
        await _wait_until(lambda: _sleeping(side), 5)
        ns["live_event_ids"].add(events["pregame"])  # admission: now live
        t = time.monotonic()
        await _tick(ns, "p2", 0.34, 0.36)  # same game, other leg
        await _tick(ns, "home", 0.64, 0.66)  # independent live game
        await _tick(ns, "away", 0.34, 0.36)
        await asyncio.sleep(BOUND_S)
        mid = await _stored(side)
        assert mid[home][0] == 0.65, "the independent live game was not written beside"
        assert mid[p2][0] == 0.55 and mid[p1][0] == 0.45, "the in-flight game was split"
        await _wait_until(pregame_committed, SLOW_S + 5)

        async def p2_written():
            return (await _stored(side))[p2][0] == 0.35

        await _wait_until(p2_written, 5)
    assert time.monotonic() - t > SLOW_S - BOUND_S - 0.5
    stored = await _stored(side)
    assert stored[p1][0] == 0.60 and stored[p2][0] == 0.35
    assert all(rank == field for _p, rank, field in stored.values()), stored
    assert not ns["price_buffer"] and ns["stats"]["errors"] == 0
    # The pre-game market's publications read p1 committed before p2.
    pre = [v for _t, mk, v in record.publications if mk == markets["pregame"]]
    assert pre and pre[0][p1] == 0.60


async def test_cancelled_inside_both_transactions_keeps_every_price_and_drains(pg):
    """Cancelled while the non-live phase AND a live write beside it are inside
    their transactions: nothing commits or publishes, no task or connection
    escapes, every newest price stays buffered, and the final drain writes all."""
    engine, side, ids = pg
    legs, markets = ids["legs"], ids["markets"]
    home, away, x1 = legs["home"], legs["away"], legs["x1"]
    ns, record = _rig(engine, side, ids)
    await _block(side, markets["nonlive"], 10.0)
    await _block(side, markets["live"], 10.0)
    from app.tasks.live_blend_refresh import _mono

    before = await _stored(side)
    await _tick(ns, "x1", 0.79, 0.81)
    flush = asyncio.create_task(ns["flush_prices"](_mono()))
    await _wait_until(lambda: _sleeping(side), 5)
    await _tick(ns, "home", 0.64, 0.66)
    await _tick(ns, "away", 0.34, 0.36)

    async def both_sleeping():
        return await _sleepers(side) == 2

    await _wait_until(both_sleeping, 5)
    buffered = dict(ns["price_buffer"])
    flush.cancel()
    with pytest.raises(asyncio.CancelledError):
        await asyncio.wait_for(flush, 5)
    assert [t for t in asyncio.all_tasks() if t is not asyncio.current_task()
            and not t.done()] == [], "a task escaped the cancelled flush"
    assert ns["price_buffer"] == buffered and set(buffered) == {home, away, x1}
    assert await _stored(side) == before
    assert not record.publications and not record.stamps
    assert ns["prices"].stamping is None

    async def idle():
        return await _sleepers(side) == 0 and engine.pool.checkedout() == 0

    await _wait_until(idle, 15)
    await _unblock(side)
    await asyncio.wait_for(ns["drain_prices"](), 15)
    await asyncio.wait_for(ns["prices"].join_stamp(ns["blend_refresher"]), 15)
    stored = await _stored(side)
    assert (stored[x1][0], stored[home][0], stored[away][0]) == (0.80, 0.65, 0.35)
    assert all(rank == field for _p, rank, field in stored.values()), stored
    assert {mk for _t, mk, _v in record.publications} == {markets["live"], markets["nonlive"]}
    assert ns["stats"]["final_flush_dropped"] == 0 and not ns["price_buffer"]


async def _in_flight(ns, side, ids):
    """The non-live phase sleeping in its UPDATE; returns its x1 probe."""
    x1 = ids["legs"]["x1"]
    await _block(side, ids["markets"]["nonlive"], SLOW_S)
    await _tick(ns, "x1", 0.79, 0.81)
    await _wait_until(lambda: _sleeping(side), 5)

    async def x1_committed():
        return (await _stored(side))[x1][0] == 0.80

    return x1_committed


def _latest_served(record, ids, since, value):
    """(publication age, stamp age, non-live row at each) for ``value``."""
    live, home, x1 = ids["markets"]["live"], ids["legs"]["home"], ids["legs"]["x1"]
    pub = _first(record.publications,
                 lambda p: p[0] >= since and p[1] == live and p[2][home] == value)
    stamp = _first(record.stamps, lambda s: s[0] >= since and s[2][home] == value)
    return (
        None if pub is None else (round(pub[0] - since, 3), pub[2][x1]),
        None if stamp is None else (round(stamp[0] - since, 3), stamp[2][x1]),
    )


def _assert_settled(ns, side_stored, ids, home_value):
    legs = ids["legs"]
    assert side_stored[legs["x1"]][0] == 0.80
    assert side_stored[legs["home"]][0] == home_value
    assert round(side_stored[legs["home"]][0] + side_stored[legs["away"]][0], 4) == 1.0
    assert all(rank == field for _p, rank, field in side_stored.values()), side_stored
    assert not ns["price_buffer"] and not ns["prices"].lock_retry_until
    assert ns["stats"]["errors"] == 0 and ns["stats"]["final_flush_dropped"] == 0


async def test_the_last_quote_inside_the_stamp_floor_is_stamped_before_the_nonlive_commit(pg):
    """Root 2146Z case 1: two quotes closer than the 250 ms stamp floor, then
    silence. The first may coalesce; the LATEST must be published and stamped
    inside the bound, before the non-live commit, with no further message."""
    engine, side, ids = pg
    ns, record = _rig(engine, side, ids)
    async with _consumer(ns):
        x1_committed = await _in_flight(ns, side, ids)
        await _tick(ns, "home", 0.64, 0.66)
        await _tick(ns, "away", 0.34, 0.36)
        await asyncio.sleep(0.05)
        latest = time.monotonic()
        await _tick(ns, "home", 0.69, 0.71)
        await _tick(ns, "away", 0.29, 0.31)
        await _wait_until(x1_committed, SLOW_S + 5)
    pub, stamp = _latest_served(record, ids, latest, 0.70)
    print("EVIDENCE floor: publication", pub, "stamp", stamp)
    assert pub is not None and pub[0] < BOUND_S and pub[1] == 0.30, (pub, record.publications)
    assert stamp is not None and stamp[0] < BOUND_S and stamp[1] == 0.30, (stamp, record.stamps)
    _assert_settled(ns, await _stored(side), ids, 0.70)


async def test_a_quote_fenced_behind_its_own_running_stamp_follows_it_unprompted(pg):
    """Root 2146Z case 2: the event's earlier stamp is held; a newer quote is
    buffered behind that fence, the stamp returns, and no venue message
    follows. The newer quote is written and stamped before the non-live commit."""
    engine, side, ids = pg
    ns, record = _rig(engine, side, ids)
    record.hold_first_stamp_s = 0.5
    async with _consumer(ns):
        x1_committed = await _in_flight(ns, side, ids)
        await _tick(ns, "home", 0.64, 0.66)
        await _tick(ns, "away", 0.34, 0.36)

        async def first_stamp_running():
            return bool(record.stamp_started)

        await _wait_until(first_stamp_running, BOUND_S)
        latest = time.monotonic()
        await _tick(ns, "home", 0.69, 0.71)
        await _tick(ns, "away", 0.29, 0.31)
        await asyncio.sleep(0.1)
        assert ns["stats"]["stamp_fenced"] >= 2, "the newer quote was not fenced"
        await _wait_until(x1_committed, SLOW_S + 5)
    pub, stamp = _latest_served(record, ids, latest, 0.70)
    print("EVIDENCE fenced: publication", pub, "stamp", stamp)
    # After the 0.5 s hold, inside the bound, before the non-live commit.
    assert pub is not None and pub[0] < BOUND_S and pub[1] == 0.30, (pub, record.publications)
    assert stamp is not None and stamp[0] < BOUND_S and stamp[1] == 0.30, (stamp, record.stamps)
    _assert_settled(ns, await _stored(side), ids, 0.70)


async def test_a_bridged_live_winner_is_written_beside_without_a_regular_ticker(pg):
    """Root 2146Z case 3: an admitted live winner that streams on an
    open-contract ticker (bridged to its event) sets no flush wake. It is
    still written and stamped beside the slow phase, not after it."""
    engine, side, ids = pg
    legs = ids["legs"]
    ns, record = _rig(engine, side, ids)
    for leg in ("home", "away"):
        ticker = f"KX10090IF-{leg.upper()}"
        ns["open_contract_ids"][ticker] = ns["ticker_to_ids"].pop(ticker)
        ns["open_contract_outcome_ids"].add(legs[leg])
    async with _consumer(ns):
        x1_committed = await _in_flight(ns, side, ids)
        latest = time.monotonic()
        await _tick(ns, "home", 0.64, 0.66)
        await _tick(ns, "away", 0.34, 0.36)
        assert not ns["flush_wake"].is_set(), "a bridged winner now wakes the cadence"
        await _wait_until(x1_committed, SLOW_S + 5)
    pub, stamp = _latest_served(record, ids, latest, 0.65)
    print("EVIDENCE bridged: publication", pub, "stamp", stamp)
    assert pub is not None and pub[0] < BOUND_S and pub[1] == 0.30, (pub, record.publications)
    assert stamp is not None and stamp[0] < BOUND_S and stamp[1] == 0.30, (stamp, record.stamps)
    assert ns["stats"]["open_contract_prices_written"] >= 2
    _assert_settled(ns, await _stored(side), ids, 0.65)


# ── #10090 Root attempt26: the helper also serves beside a LIVE phase ─────────
#
# Two live games. The "pregame" fixture event joins `live_event_ids`, so its
# market's phase is a live phase and its legs are live input. Marks carry the
# consumer's `seq` (buffer order), which the helper's newest-first order reads.


class _SeqReceipts(_Receipts):
    def __init__(self):
        self.seq = 0

    def note_input(self, _event_id, outcome_id, prob, _kind):
        self.seq += 1
        return SimpleNamespace(seq=self.seq, outcome_id=outcome_id, probability=prob)


def _two_live_games(engine, side, ids, source=None):
    ns, record = _rig(engine, side, ids, source=source)
    ns["live_event_ids"].add(ids["events"]["pregame"])
    ns["tail_receipts"] = _SeqReceipts()
    return ns, record


def _served(record, market, leg, since, value):
    """(seconds from ``since``, every committed row) at ``value``'s first publication."""
    hit = _first(record.publications,
                 lambda p: p[0] >= since and p[1] == market and p[2][leg] == value)
    return None if hit is None else (round(hit[0] - since, 3), hit[2])


async def _committed(side, leg, value):
    return (await _stored(side))[leg][0] == value


async def _beside_a_live_phase(ns, record, side, ids):
    """Game P's live phase sleeps in its UPDATE; game L's quote arrives."""
    legs, markets = ids["legs"], ids["markets"]
    await _block(side, markets["pregame"], SLOW_S)
    async with _consumer(ns):
        await _tick(ns, "p1", 0.79, 0.81)
        await _wait_until(lambda: _sleeping(side), 5)
        arrived = time.monotonic()
        await _tick(ns, "home", 0.64, 0.66)
        await _wait_until(lambda: _committed(side, legs["p1"], 0.80), SLOW_S + 5)
        released = time.monotonic()
    served = _served(record, markets["live"], legs["home"], arrived, 0.65)
    print("EVIDENCE beside-live: home", served and served[0],
          f"p1 committed {released - arrived:.2f}s after home arrived")
    return served, released - arrived


async def test_a_live_quote_is_written_beside_another_live_games_slow_transaction(pg):
    """Root attempt26: the helper was started only beside a NON-live phase, so a
    live game's quote waited out another live game's slow transaction."""
    engine, side, ids = pg
    legs = ids["legs"]
    ns, record = _two_live_games(engine, side, ids)
    served, held = await _beside_a_live_phase(ns, record, side, ids)
    assert held >= SLOW_S / 2, "game P's live transaction was not slow"
    assert served is not None and served[0] < BOUND_S, (served, record.publications)
    # Served while game P's row was still uncommitted.
    assert served[1][legs["p1"]] == 0.45, served
    assert ns["stats"]["live_beside"] == 1
    stored = await _stored(side)
    assert stored[legs["p1"]][0] == 0.80 and stored[legs["home"]][0] == 0.65
    assert all(rank == field for _p, rank, field in stored.values()), stored
    assert not ns["price_buffer"] and not ns["prices"].lock_retry_until
    assert ns["stats"]["errors"] == 0 and ns["stats"]["final_flush_dropped"] == 0


async def test_strawman_without_a_helper_beside_live_phases_the_quote_waits(pg):
    """The same case on the earlier start condition (non-live phases only)."""
    engine, side, ids = pg
    text_ = SOURCE.read_text()
    start = "beside is None and live_event_ids and not final_drain\n                ):"
    assert text_.count(start) == 1
    old = start.replace("\n                ):", "\n                    and not phase_live\n                ):")
    ns, record = _two_live_games(engine, side, ids, source=text_.replace(start, old))
    served, _held = await _beside_a_live_phase(ns, record, side, ids)
    assert served is not None and served[0] >= BOUND_S, served
    assert served[1][ids["legs"]["p1"]] == 0.80, served
    assert ns["stats"]["live_beside"] == 0


async def _older_slow_newer_fast(ns, record, side, ids):
    """One helper snapshot holds game P's older quote (its UPDATE sleeps) and
    game L's newer quote, both arriving inside a slow non-live transaction."""
    legs, markets = ids["legs"], ids["markets"]
    await _block(side, markets["pregame"], 2.0)
    async with _consumer(ns):
        x1_committed = await _in_flight(ns, side, ids)
        arrived = time.monotonic()
        # No await yields between the two: one buffer, one helper snapshot.
        await _tick(ns, "p1", 0.79, 0.81)
        await _tick(ns, "home", 0.64, 0.66)
        await _wait_until(x1_committed, SLOW_S + 5)
    served = _served(record, markets["live"], legs["home"], arrived, 0.65)
    print("EVIDENCE newest-first: home", served and served[0])
    return served


async def test_the_helper_serves_the_newest_whole_event_first(pg):
    engine, side, ids = pg
    legs = ids["legs"]
    ns, record = _two_live_games(engine, side, ids)
    served = await _older_slow_newer_fast(ns, record, side, ids)
    assert served is not None and served[0] < BOUND_S, (served, record.publications)
    # Before game P's older, slower quote and before the non-live commit.
    assert served[1][legs["p1"]] == 0.45 and served[1][legs["x1"]] == 0.30, served
    assert ns["stats"]["live_beside"] == 2
    stored = await _stored(side)
    assert stored[legs["p1"]][0] == 0.80 and stored[legs["home"]][0] == 0.65
    assert not ns["price_buffer"]
    assert ns["stats"]["errors"] == 0 and ns["stats"]["final_flush_dropped"] == 0


async def test_strawman_in_first_seen_order_the_newer_quote_waits_behind_the_older(pg):
    engine, side, ids = pg
    text_ = SOURCE.read_text()
    order = "        if beside is not None:\n            # The main writer keeps oldest-first"
    assert text_.count(order) == 1
    ns, record = _two_live_games(
        engine, side, ids,
        source=text_.replace(order, "        if False:\n            # The main writer keeps oldest-first"),
    )
    served = await _older_slow_newer_fast(ns, record, side, ids)
    assert served is not None and served[0] >= BOUND_S, served
    assert served[1][ids["legs"]["p1"]] == 0.80, served


async def _owner_joins_mid_helper_phase(ns, record, side, ids):
    """The owner's non-live phase commits while its helper is inside game P's
    slow phase, with game L's quote still untouched in the same snapshot."""
    legs, markets = ids["legs"], ids["markets"]
    await _block(side, markets["nonlive"], 1.0)
    await _block(side, markets["pregame"], 2.5)
    async with _consumer(ns):
        await _tick(ns, "x1", 0.79, 0.81)
        await _wait_until(lambda: _sleeping(side), 5)
        # Older first: newest-first puts game P's slow phase ahead of game L.
        await _tick(ns, "home", 0.64, 0.66)
        await _tick(ns, "p1", 0.79, 0.81)
        await _wait_until(lambda: _committed(side, legs["p1"], 0.80), 10)
        await _wait_until(lambda: _committed(side, legs["home"], 0.65), 5)
    # Anchored on p1's own publication, not on when the poll noticed its
    # commit: the next flush can publish home inside that poll's step.
    p1_pub = _first(record.publications,
                    lambda p: p[1] == markets["pregame"] and p[2][legs["p1"]] == 0.80)
    served = None if p1_pub is None else _served(
        record, markets["live"], legs["home"], p1_pub[0], 0.65)
    print("EVIDENCE cooperative-stop: home after p1", served and served[0],
          "beside", ns["stats"]["live_beside"])
    return served


async def test_a_joining_owner_leaves_the_helpers_untouched_events_to_the_next_flush(pg):
    """Root attempt26 cooperative stop: once the owner joins, the helper ends
    its in-flight whole event and starts no other; the untouched one stays
    buffered and the next flush writes it — nothing is cancelled or lost."""
    engine, side, ids = pg
    legs = ids["legs"]
    ns, record = _two_live_games(engine, side, ids)
    served = await _owner_joins_mid_helper_phase(ns, record, side, ids)
    assert ns["stats"]["live_beside"] == 1  # p1 only: home was the next flush's
    assert served is not None and served[0] < BOUND_S, (served, record.publications)
    stored = await _stored(side)
    assert stored[legs["x1"]][0] == 0.80
    assert stored[legs["p1"]][0] == 0.80 and stored[legs["home"]][0] == 0.65
    assert all(rank == field for _p, rank, field in stored.values()), stored
    assert not ns["price_buffer"] and not ns["prices"].lock_retry_until
    assert ns["stats"]["errors"] == 0 and ns["stats"]["final_flush_dropped"] == 0


async def test_strawman_without_the_stop_the_helper_runs_on_through_its_snapshot(pg):
    engine, side, ids = pg
    text_ = SOURCE.read_text()
    stop = "                if beside_stopping is not None and beside_stopping():\n                    break\n"
    assert text_.count(stop) == 1
    ns, record = _two_live_games(engine, side, ids, source=text_.replace(stop, ""))
    await _owner_joins_mid_helper_phase(ns, record, side, ids)
    assert ns["stats"]["live_beside"] == 2
