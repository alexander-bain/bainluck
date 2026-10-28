"""#10090: the rank-lock holder sampler names the real holder, on real Postgres.

Root attempt58's shape, on the actual `write_chunk` closure the #10664 rig
compiles: a separate transaction holds outcome 3 (absent from the chunk) under a
known `application_name`; the chunk moves outcomes 1/2, so the field re-rank must
rewrite row 3's rank and waits on that lock until its budget cancels it. The
sampler, armed at the rank statement, probes 150 ms in on its own connection and
must name exactly that pid and tag, while the writer's outcome is unchanged:
the chunk rolls back whole, nothing publishes, the cooldown is armed.

Control: the same hold with a chunk that does not change any rank. The
existing no-change guard never touches row 3, the rank finishes inside the
delay, and the sampler spends nothing (no PROBE line).

And `writer_pid` reads the pid of the session it is given, with no round trip.
"""

from __future__ import annotations

import asyncio
import time
from decimal import Decimal
from types import SimpleNamespace

import pytest
from sqlalchemy import insert, text
from sqlalchemy.ext.asyncio import create_async_engine

import app.tasks.base as task_base
from app.models.models import FuturesMarket, FuturesOutcome
from app.utils import pm_lock_holder_trace as mod
from tests.integration.test_pm_bulk_price_write_10664_pg import _prices, _write, rig  # noqa: F401

pytestmark = pytest.mark.asyncio

HOLDER_TAG = "bl-10090-known-rank-holder"


class _RigSampler(mod.RankLockHolderSampler):
    """The rig's session is a proxy with no driver connection; it records the
    writer's pid itself (`r.price_pid`) when the price statement starts."""

    rig = None

    async def writer_pid(self, session):
        return self.rig.price_pid


async def _armed_sampler(r):
    lines = []

    def engine_factory():
        return create_async_engine(
            r.engine.url, pool_size=1, max_overflow=0,
            connect_args={"server_settings": {
                "statement_timeout": str(mod.PROBE_STATEMENT_TIMEOUT_MS),
                "application_name": mod.APPLICATION_NAME,
            }},
        )

    sampler = _RigSampler.from_env(
        {"WS_PM_LOCK_HOLDER_EXPIRES_AT": str(time.time() + 600)},
        run="pg10090", emit=lines.append, engine_factory=engine_factory,
    )
    sampler.rig = r
    assert sampler.ready() is False
    await sampler.warming
    assert sampler.ready() is True, lines
    r.publisher.receipts = SimpleNamespace(exact_trace=None, lock_holder=sampler)
    return sampler, lines


async def _seed_second_market(r):
    async with r.engine.begin() as conn:
        await conn.execute(text("UPDATE futures_outcomes SET rank = 1"))
        await conn.execute(insert(FuturesMarket.__table__), [dict(
            id=2, source="polymarket", external_id="0x2", name="C vs D",
            category="game", mutually_exclusive=True, status="open",
        )])
        await conn.execute(insert(FuturesOutcome.__table__), [
            dict(id=i, market_id=2, external_id=f"leg{i}", name=f"Leg {i}",
                 current_probability=Decimal(p), rank=rank)
            for i, p, rank in [(4, "0.6", 1), (5, "0.4", 2)]
        ])
    r.ns["market_by_outcome"].update({4: 2, 5: 2})
    r.ns["event_id_by_outcome"].update({4: 20, 5: 20})


async def _with_row3_held(r, body):
    async with r.engine.connect() as holder:
        txn = await holder.begin()
        await holder.execute(text(f"SET LOCAL application_name = '{HOLDER_TAG}'"))
        holder_pid = await holder.scalar(text("SELECT pg_backend_pid()"))
        await holder.execute(text("SELECT id FROM futures_outcomes WHERE id = 3 FOR UPDATE"))
        try:
            return holder_pid, await body()
        finally:
            await txn.rollback()


async def test_a_waiting_rank_names_the_transaction_that_holds_its_row(rig, monkeypatch):  # noqa: F811
    # The 100 ms deadline is pinned without a database (the unit file). Here it
    # is widened so a loaded runner cannot turn "which pid" into a timing test.
    monkeypatch.setattr(mod, "PROBE_DEADLINE_S", 2.0)
    r = rig
    await _seed_second_market(r)
    sampler, lines = await _armed_sampler(r)
    before = await _prices(r)

    async def write():
        started = time.monotonic()
        outcome = await _write(r, {1: 0.8, 2: 0.2, 4: 0.65, 5: 0.35})
        return outcome, time.monotonic() - started

    holder_pid, (outcome, elapsed) = await _with_row3_held(r, write)
    if sampler.pending is not None:
        await asyncio.wait_for(sampler.pending.task, 2)

    # The writer's behaviour is the #10664 contract's, unchanged.
    assert outcome is None
    assert not r.price_errors, "the price statement succeeds; only the rank waits"
    assert await _prices(r) == before
    assert r.publisher.frames == []
    assert set(r.ns["lock_retry_until"]) == {1, 2, 4, 5}
    assert elapsed < 2.0, "the writer did not wait on the observer"

    probes = [line for line in lines if line["kind"] == "PROBE"]
    assert len(probes) == 1, lines
    probe = probes[0]
    assert probe["result"] == "HOLDER", probe
    assert probe["writer_pid"] == r.price_pid
    assert probe["markets"] == [1, 2] and probe["outcomes_n"] == 4
    assert probe["writer_wait"].startswith("Lock/")
    assert [(h["pid"], h["application"]) for h in probe["holders"]] == [
        (holder_pid, HOLDER_TAG)
    ]
    assert probe["rank_waited_ms"] >= mod.PROBE_DELAY_S * 1000
    assert [line["reason"] for line in lines if line["kind"] == "STOP"] == ["FIRST_HOLDER"]
    rank_end = next(line for line in lines if line["kind"] == "RANK_END")
    assert rank_end["rank_result"] == "LOCK_TIMEOUT"


async def test_the_control_an_unchanged_rank_spends_no_probe(rig):  # noqa: F811
    r = rig
    await _seed_second_market(r)
    sampler, lines = await _armed_sampler(r)

    async def write():
        return await _write(r, {1: 0.3, 2: 0.3, 4: 0.65, 5: 0.35})

    _holder_pid, outcome = await _with_row3_held(r, write)
    await asyncio.sleep(mod.PROBE_DELAY_S + 0.05)

    assert outcome, "no rank changed, so nothing waited on row 3"
    assert [line["kind"] for line in lines] == ["START", "WARM"]
    assert sampler.probes == 0 and sampler.ready() is True
    await sampler.engine.dispose()


async def test_writer_pid_is_the_sessions_own_backend(rig):  # noqa: F811
    sampler = mod.RankLockHolderSampler(
        time.time() + 600, 1, "pg10090", time.time, time.monotonic,
        lambda record: None, lambda: None,
    )
    async with task_base.get_task_session(engine=rig.engine) as session:
        await session.execute(text("SELECT 1"))
        expected = await session.scalar(text("SELECT pg_backend_pid()"))
        assert await sampler.writer_pid(session) == expected
