"""#10090 — a held KALSHI price row no longer holds the blend, on real PostgreSQL.

## the ship

A reader holding a live event page sees a changed Kalshi price in the headline
promptly while a foreign transaction holds that price's `futures_outcomes`
row, and a newer change during the write's retry cooldown too. Root's isolated
real-PG/EventPage lab on 1a02deea55 (attempt21): Kalshi .375 reached headline
and chart 5087.73 ms after send on the parent, 105.22 ms with this change.

## the rig

The SHIPPED `flush_prices` closure (as #10661's real-PG gate execs it), on the
consumer's own pooled engine and price pipeline, with a REAL
`LiveBlendRefresher("kalshi")` — reader, resolver, orientation, conditional
stamp UPDATE, commit — whose frames are captured after commit. Inputs are
accepted exactly as `handle_ticker` accepts them (buffer, receipt mark, frozen
DB-clock bound). The holder is a second connection holding
`SELECT ... FOR UPDATE` on the Kalshi home leg's price row.

## what is asserted

* the received quote is stamped (committed on the events row) BEFORE the
  holder lets go, and a newer one during the cooldown with no second price
  UPDATE, while the price row still holds the old price;
* RESTART: a new consumer run (empty overlay) re-reading the still-held row
  cannot put the older price back — its stamp is refused in the UPDATE;
* after release the ordinary write lands the newest price and the overlay
  releases it; the stamped value never regresses;
* a newest quote that RETURNS to the price the row still stores (.395 → held
  .375 → .395, Root attempt30) still lands and publishes .395;
* a KNOWN newer stored row (attempt24's ambiguity) is not overlaid: nothing
  is stamped from the stale row and the write retries at the next flush start;
* parent (no overlay installed): nothing is stamped while the row is held —
  the strawman that shows the first assertion bites.

Synthetic rows on one machine: ordering and durability, not production timing.
"""

from __future__ import annotations

import ast
import asyncio
import logging
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from functools import partial
from pathlib import Path

import pytest
from sqlalchemy import text

from app.utils.kalshi_primary_quote import PrimaryQuoteCustody
from tests.integration.test_live_blend_grouped_commit_8129_pg import (  # noqa: F401
    DB_URL,
    rig,
)
from tests.test_event_frame_batching_10659 import private_redis_socket  # noqa: F401

pytestmark = [
    pytest.mark.asyncio,
    pytest.mark.skipif(
        not DB_URL, reason="requires disposable SEARCH_TEST_DATABASE_URL"
    ),
]

SOURCE = Path(__file__).resolve().parents[2] / "app/tasks/kalshi_ws.py"
EVENT, MARKET, HOME, AWAY = 1, 1, 1, 2
PERIOD = 0.25


@pytest.fixture(autouse=True)
async def default_preview_transport(monkeypatch, private_redis_socket):
    """Healthy default ledger; never depend on a Redis at localhost:6379.

    A missing ambient server adds connection waits that can expire the real
    250 ms cooldown before the test's second quote. Keep the production timer
    and ledger, and supply the private transport the consumer now requires.
    """
    from redis.asyncio import Redis
    from app.tasks.live_blend_refresh import LiveBlendRefresher

    client = Redis(unix_socket_path=str(private_redis_socket))
    readers = set()

    def connection(reader):
        readers.add(reader)
        return client

    monkeypatch.setattr(LiveBlendRefresher, "_client", connection)
    try:
        yield
    finally:
        for reader in readers:
            await reader.drain_history()
        await client.aclose()


async def seed(rig):
    from app.models.models import Event, FuturesMarket, FuturesOutcome, Sport

    now = datetime.now(timezone.utc)
    async with rig.maker() as session:
        sport = Sport(key="baseball_mlb", name="MLB")
        session.add(sport)
        await session.flush()
        session.add(Event(
            id=EVENT, sport_id=sport.id, home_team_name="Chicago Cubs",
            away_team_name="Miami Marlins", commence_time=now - timedelta(minutes=30),
            status="live", win_probability_sources={}, opening_home_probability=0.5,
        ))
        session.add(FuturesMarket(
            id=MARKET, source="kalshi", external_id="KXMLBGAME-26OCT17MIACHC",
            sport_id=sport.id, event_id=EVENT, name="Miami vs Chicago C Winner?",
            status="open", category="game",
        ))
        await session.flush()
        for oid, name, ticker, prob in (
            (HOME, "Chicago Cubs", "KXMLBGAME-26OCT17MIACHC-CHC", 0.60),
            (AWAY, "Miami Marlins", "KXMLBGAME-26OCT17MIACHC-MIA", 0.40),
        ):
            session.add(FuturesOutcome(
                id=oid, market_id=MARKET, external_id=ticker, name=name,
                current_probability=prob, rank=1 if oid == HOME else 2,
                last_updated=now - timedelta(minutes=1),
            ))
        await session.commit()


class Consumer:
    """The shipped flush + a real Kalshi refresher on ``rig``'s schema."""

    def __init__(self, rig, *, overlay=True):
        from app.models.models import FuturesOutcome
        from app.tasks import kalshi_ws
        from app.tasks.base import get_task_session
        from app.tasks.live_blend_refresh import (
            HeldRowQuotes, LiveBlendRefresher, TailReceipts, event_ids_for_outcomes,
        )
        from app.utils.futures_rank import rerank_market_fields_stmt
        from app.utils.kalshi_price_statement import (
            KALSHI_PRICE_STATEMENTS, kalshi_price_parameters,
        )
        from app.utils.price_change_stamp import price_changed_at_value, quote_moved_column
        from app.utils.resolution_authority import AUTHORITATIVE_SOURCES
        from sqlalchemy import func, or_, update

        self.sessions = partial(get_task_session, engine=rig.engine)
        self.frames: list[dict] = []
        self.refresher = self.new_refresher(LiveBlendRefresher, TailReceipts)
        if overlay:
            self.refresher.held_quotes = HeldRowQuotes()
        self.receipts = TailReceipts("kalshi")
        self.batch: dict = {}
        self.attempts: list[tuple] = []
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
            price_buffer=self.batch, buffer_lock=asyncio.Lock(),
            market_id_by_outcome={HOME: MARKET, AWAY: MARKET},
            event_id_by_outcome={HOME: EVENT, AWAY: EVENT},
            input_marks={}, tail_receipts=self.receipts,
            # #10090: the worker's primary-quote custody (bundled pair).
            primary_quote_custody=PrimaryQuoteCustody(), ticker_to_ids={},
            observation_continuity={}, game_clients=[],
            open_contract_outcome_ids=set(), blend_refresher=self.refresher,
            non_blend_outcome_ids=set(), get_task_session=self.sessions,
            stats=defaultdict(int), logger=logging.getLogger(__name__),
            prices=kalshi_ws._KalshiPriceOwner(),
            live_event_ids={EVENT}, flush_budget=None, flush_period=PERIOD,
        )
        tree = ast.parse(SOURCE.read_text())
        wanted = {"flush_prices", "steady_book_signature", "observation_signature",
                  "note_observation_continuity"}
        nodes = [n for n in ast.walk(tree)
                 if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name in wanted]
        assert {n.name for n in nodes} == wanted and len(nodes) == len(wanted)
        exec(compile(ast.Module(body=nodes, type_ignores=[]), str(SOURCE), "exec"), ns)
        self.ns, self.prices = ns, ns["prices"]
        phase = self.prices.phase

        def counted(session, group, **kwargs):
            self.attempts.append(tuple(sorted(group)))
            return phase(session, group, **kwargs)

        self.prices.phase = counted

    def new_refresher(self, LiveBlendRefresher, TailReceipts):
        r = LiveBlendRefresher(
            "kalshi", session_factory=self.sessions, min_refresh_interval_s=0,
        )
        r.receipts = TailReceipts("kalshi")

        async def publish(batch):
            self.frames.extend(batch)

        r._publish = publish
        return r

    def accept(self, oid, value):
        """`handle_ticker`'s acceptance: buffer, receipt mark, frozen bound."""
        self.batch[oid] = (value, None, None)
        mark = self.receipts.note_input(EVENT, oid, value, "ticker")
        self.ns["input_marks"][oid] = mark
        held = getattr(self.refresher, "held_quotes", None)
        if held is not None:
            held.note_input(mark)

    async def flush(self):
        from app.tasks.live_blend_refresh import _mono

        result = await asyncio.wait_for(self.ns["flush_prices"](_mono()), 5)
        await asyncio.wait_for(self.prices.join_stamp(self.refresher), 5)
        return result

    def close(self):
        self.prices.close()


async def hold_row(rig, oid):
    conn = await rig.engine.connect()
    tx = await conn.begin()
    await conn.execute(
        text("SELECT id FROM futures_outcomes WHERE id = :id FOR UPDATE"), {"id": oid}
    )
    return conn, tx


async def stored(rig):
    async with rig.engine.connect() as conn:
        price = await conn.scalar(
            text("SELECT current_probability FROM futures_outcomes WHERE id = :id"),
            {"id": HOME},
        )
        sources = await conn.scalar(
            text("SELECT win_probability_sources FROM events WHERE id = :id"),
            {"id": EVENT},
        )
    return float(price), (sources or {}).get("kalshi", {}).get("value")


async def started(rig, *, overlay=True):
    await seed(rig)
    c = Consumer(rig, overlay=overlay)
    # The consumer's first stamp: the seeded rows, no hold.
    await c.refresher.refresh([EVENT])
    price, v0 = await stored(rig)
    assert price == 0.60 and v0 is not None, "the Kalshi group must speak"
    held = getattr(c.refresher, "held_quotes", None)
    if held is not None:
        # The consumer samples before any input can arrive.
        assert await held.sample_database_clock(c.sessions)
    return c, v0


async def test_a_held_kalshi_row_stamps_the_received_quote_and_a_restart_cannot_undo_it(rig, monkeypatch):
    c, v0 = await started(rig)
    # This case tests a quote DURING the cooldown, not database-machine speed.
    # Control the shared cadence/retry clock; SQL locks, clock samples, commit
    # and timeouts remain real. Advance explicitly for the after-deadline arm.
    from app.tasks import live_blend_refresh
    clock = [live_blend_refresh._mono()]
    monkeypatch.setattr(live_blend_refresh, "_mono", lambda: clock[0])
    held = c.refresher.held_quotes
    conn, tx = await hold_row(rig, HOME)
    try:
        c.accept(HOME, 0.375)
        assert await c.flush() is True
        price, v1 = await stored(rig)
        assert price == 0.60, "the price row is still held"
        assert v1 != v0, "the received quote reached the events row while held"
        assert HOME in held
        assert c.attempts == [(HOME,)]

        # A newer quote inside the write's cooldown: stamped, no second UPDATE.
        c.accept(HOME, 0.395)
        assert await c.flush() is True
        price, v2 = await stored(rig)
        assert price == 0.60 and v2 not in (v0, v1)
        assert c.attempts == [(HOME,)], "no price UPDATE inside the cooldown"

        # RESTART: a new run with an empty overlay re-reads the held row.
        from app.tasks.live_blend_refresh import LiveBlendRefresher, TailReceipts

        restarted = c.new_refresher(LiveBlendRefresher, TailReceipts)
        await restarted.refresh([EVENT])
        assert await stored(rig) == (0.60, v2), (
            "a stamp built from the older row must be refused in the UPDATE"
        )
        # It did attempt that stamp: refused by the clause, not skipped.
        assert restarted.stats["stale_readings_refused"] == 1
    finally:
        await tx.rollback()
        await conn.close()

    # Released: past the cooldown the ordinary write lands the newest price.
    clock[0] = c.prices.lock_retry_until[HOME] + 0.01
    assert await c.flush() is True
    price, final = await stored(rig)
    assert price == 0.395 and final == v2
    assert HOME not in held and not c.batch
    values = [f.get("source_value") for f in c.frames if f.get("event_id") == EVENT]
    assert v1 in values and v2 in values
    assert values.index(v2) > values.index(v1)
    assert v0 not in values[values.index(v1):], "no published value regresses"
    c.close()


async def test_a_held_quote_that_returns_to_the_stored_price_still_lands_and_publishes(rig):
    """Root attempt30 on the exact PR #11190 tree: stored .395, held .375 is
    stamped, then .395 arrives after the retry deadline. The landing write met
    the repeat predicate (same price, fresh `last_updated`) and returned no row,
    so the page kept .375 while the row said .395."""
    c, v0 = await started(rig)
    held = c.refresher.held_quotes
    # Prime: the consumer's own committed write stores .395 NOW, so the
    # predicate's 30 s liveness arm and first-observation force cannot rescue
    # the return below.
    c.accept(HOME, 0.395)
    assert await c.flush() is True
    price, primed = await stored(rig)
    assert price == 0.395 and primed not in (None, v0)
    assert HOME in c.prices.committed_outcome_ids

    conn, tx = await hold_row(rig, HOME)
    try:
        c.accept(HOME, 0.375)
        assert await c.flush() is True
        price, v1 = await stored(rig)
        assert price == 0.395 and v1 != primed, "the held .375 is stamped"
        assert HOME in held
    finally:
        await tx.rollback()
        await conn.close()

    # Past the deadline the newest input is the price the row already stores.
    c.prices.lock_retry_until.clear()
    c.accept(HOME, 0.395)
    attempts = len(c.attempts)
    assert await c.flush() is True
    assert len(c.attempts) == attempts + 1, "the ordinary write ran"
    price, final = await stored(rig)
    assert price == 0.395
    assert final == primed, "the source returns to .395, not the held .375"
    assert HOME not in held and not c.batch
    values = [f.get("source_value") for f in c.frames if f.get("event_id") == EVENT]
    assert values[-1] == primed and values.index(v1) < len(values) - 1
    c.close()


async def test_a_known_newer_stored_row_is_not_overlaid_and_retries_at_the_next_flush_start(rig):
    c, v0 = await started(rig)
    held = c.refresher.held_quotes
    c.accept(HOME, 0.375)  # its bound is the sample taken in `started`
    # Another writer stores a NEWER observation of the row after that bound.
    async with rig.engine.begin() as conn:
        await conn.execute(text(
            "UPDATE futures_outcomes SET current_probability = 0.62, "
            "last_updated = clock_timestamp() WHERE id = :id"
        ), {"id": HOME})
    conn, tx = await hold_row(rig, HOME)
    try:
        from app.tasks.live_blend_refresh import _mono

        before = _mono()
        assert await c.flush() is True
        assert HOME not in held, "the overlay cannot carry a known newer row"
        assert (await stored(rig))[1] == v0, "nothing stamped from the stale row"
        until = c.prices.lock_retry_until[HOME]
        assert before < until <= _mono() + PERIOD, "retry at the next flush start"
        assert c.prices.ambiguous_retry_since
    finally:
        await tx.rollback()
        await conn.close()
    c.prices.lock_retry_until.clear()
    assert await c.flush() is True
    price, value = await stored(rig)
    assert price == 0.375 and value != v0
    assert not c.prices.ambiguous_retry_since
    c.close()


async def test_parent_stamps_nothing_while_the_kalshi_row_is_held(rig):
    c, v0 = await started(rig, overlay=False)
    conn, tx = await hold_row(rig, HOME)
    try:
        c.accept(HOME, 0.375)
        assert await c.flush() is True
        assert await stored(rig) == (0.60, v0)
    finally:
        await tx.rollback()
        await conn.close()
    c.prices.lock_retry_until.clear()
    assert await c.flush() is True
    assert (await stored(rig))[0] == 0.375
    c.close()


async def test_successful_price_returning_supplies_bound_without_another_clock_read(rig):
    c, v0 = await started(rig)
    held = c.refresher.held_quotes
    old_bound = held._database_bound

    async def redundant_read(_sessions):
        pytest.fail("committed RETURNING clock must replace the separate clock read")

    held.sample_database_clock = redundant_read
    try:
        c.accept(HOME, 0.395)
        accepted = c.ns["input_marks"][HOME]
        assert await c.flush() is True
        async with rig.engine.connect() as conn:
            updated = await conn.scalar(text(
                "SELECT last_updated FROM futures_outcomes WHERE id = :id"
            ), {"id": HOME})
        assert held._database_bound > updated.timestamp()
        assert held.bound_for(accepted) == old_bound
        c.accept(HOME, 0.375)
        assert held.bound_for(c.ns["input_marks"][HOME]) == held._database_bound
    finally:
        c.close()
