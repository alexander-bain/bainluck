"""#5531 — the hook queue's window holds only markets the evidence gate can pass, on real Postgres.

## The defect, as production measured it

`enrich_market_hooks` wrote **0** hooks from 2026-09-13 to 2026-09-24 (`futures_markets.hook_generated_at`
per day: 400 on 9/11, 200 on 9/12, then nothing). T11-1 (#5461) made the model asked only when a market
has a linked fixture that has not started (`should_generate_hook`). The candidate SELECT kept ordering
null-hook rows first and feed categories (politics, economics, ...) ahead of sports. Those rows have no
fixture, so every one is refused, never stamped, and back at the head of the same `limit * 3` window on
the next run. At the time of measuring, 514 fixture-linked markets with an upcoming kickoff were
waiting behind them, every one with a null hook.

## Why real Postgres

The #5461 unit fake answers "the candidate query" with whatever market it was handed and ignores the
WHERE clause. That is right for what it tests (what the task does with one market) and it cannot tell
whether the window is filled. The window is a SQL property: ORDER BY + LIMIT over a population. Only
a real query shows which rows come back.

Opt-in on `SEARCH_TEST_DATABASE_URL` like its siblings; CI runs it in the `search-recall` job.
"""

from __future__ import annotations

import os
import sys
import types
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone

import pytest

DB_URL = os.environ.get("SEARCH_TEST_DATABASE_URL")

pytestmark = [
    pytest.mark.asyncio,
    pytest.mark.skipif(
        not DB_URL,
        reason=(
            "set SEARCH_TEST_DATABASE_URL to run the real-Postgres hook-queue window gate "
            "(CI job: search-recall)"
        ),
    ),
]


@pytest.fixture
async def engine():
    from sqlalchemy.ext.asyncio import create_async_engine

    import app.models.models  # noqa: F401  — registers every table on Base
    from app.services.database import Base

    eng = create_async_engine(DB_URL)
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    yield eng
    await eng.dispose()


class _CountingClient:
    """Always has an answer, so a market missing from `calls` was NOT ASKED."""

    def __init__(self):
        self.calls: list[str] = []
        self.chat = types.SimpleNamespace(completions=types.SimpleNamespace(create=self._create))

    def _create(self, *, model, messages, max_tokens, temperature):
        self.calls.append(messages[0]["content"])
        msg = types.SimpleNamespace(content="The Giants are set to face the Dodgers this weekend.")
        return types.SimpleNamespace(choices=[types.SimpleNamespace(message=msg)])


async def _noop_sleep(_seconds):
    return None


async def _seed(session, now):
    """Three refused rows that outrank the one askable row on every ORDER BY key, plus a control."""
    from app.models.models import Event, FuturesMarket, FuturesOutcome, Sport

    sport = Sport(key="baseball_mlb", name="MLB", active=True)
    session.add(sport)
    await session.flush()

    upcoming = Event(
        sport_id=sport.id,
        home_team_name="Los Angeles Dodgers",
        away_team_name="San Francisco Giants",
        commence_time=now + timedelta(days=2),
    )
    started = Event(
        sport_id=sport.id,
        home_team_name="New York Yankees",
        away_team_name="Boston Red Sox",
        commence_time=now - timedelta(hours=1),
    )
    session.add_all([upcoming, started])
    await session.flush()

    def market(ext, name, *, category, volume, event_id=None):
        return FuturesMarket(
            source="polymarket",
            external_id=ext,
            name=name,
            status="open",
            llm_sport_category=category,
            volume_24h=volume,
            event_id=event_id,
            resolution_date=now + timedelta(days=30),
        )

    # Null hook, feed category, $1M volume: first on every key the SELECT orders by. No fixture.
    refused = [
        market(f"POL-{i}", f"Will policy {i} pass this year?", category="politics", volume=1_000_000)
        for i in range(3)
    ]
    askable = market(
        "MLB-UPCOMING", "Giants vs. Dodgers", category="mlb", volume=10_000, event_id=upcoming.id
    )
    # Linked, but the fixture has started: the gate refuses it, so the window must not hold it.
    kicked_off = market(
        "MLB-STARTED", "Red Sox vs. Yankees", category="mlb", volume=900_000, event_id=started.id
    )
    session.add_all([*refused, askable, kicked_off])
    await session.flush()
    for m in [*refused, askable, kicked_off]:
        session.add(FuturesOutcome(market_id=m.id, external_id=f"{m.external_id}-Y", name="Yes",
                                   current_probability=0.55, rank=1))
    await session.commit()
    return askable, refused, kicked_off


async def _run(monkeypatch, engine, limit):
    from sqlalchemy.ext.asyncio import async_sessionmaker

    from app.tasks import enrich_markets

    maker = async_sessionmaker(engine, expire_on_commit=False)

    @asynccontextmanager
    async def _session():
        async with maker() as s:
            yield s

    client = _CountingClient()
    monkeypatch.setattr(enrich_markets, "get_task_session", _session)
    monkeypatch.setattr(sys.modules["app.services.llm"], "_get_client", lambda *a, **k: client)
    monkeypatch.setattr(enrich_markets, "asyncio", types.SimpleNamespace(sleep=_noop_sleep))
    stats = await enrich_markets.enrich_market_hooks(limit=limit)
    return stats, client


class TestHookQueueReachesWhatItsGateAllows5531:
    async def test_refused_rows_no_longer_fill_the_window(self, monkeypatch, engine):
        """limit=1 ⇒ a window of 3; three refused rows outrank the askable one on every key.

        Before #5531 the three politics rows filled the window, all were refused, and the run
        wrote nothing (`generated == 0`, `skipped_no_evidence == 3`) — production's 12-day shape.
        """
        from sqlalchemy import text
        from sqlalchemy.ext.asyncio import async_sessionmaker

        now = datetime.now(timezone.utc)
        async with async_sessionmaker(engine, expire_on_commit=False)() as s:
            askable, refused, kicked_off = await _seed(s, now)

        stats, client = await _run(monkeypatch, engine, limit=1)

        assert stats["generated"] == 1, stats
        assert stats["skipped_no_evidence"] == 0, (
            "the window held a row the evidence gate refuses — the head-block #5531 removed", stats
        )
        assert len(client.calls) == 1 and "Giants vs. Dodgers" in client.calls[0]

        async with engine.connect() as conn:
            rows = dict(
                (await conn.execute(
                    text("SELECT external_id, hook_description FROM futures_markets")
                )).all()
            )
        assert rows["MLB-UPCOMING"], "the askable market's hook was not written"
        assert rows["MLB-STARTED"] is None
        assert all(rows[f"POL-{i}"] is None for i in range(3))

    async def test_a_market_whose_fixture_has_started_is_not_a_candidate(self, monkeypatch, engine):
        """The control arm: the filter is the gate's test (kickoff after now), not "has an event_id".

        `MLB-STARTED` is linked and out-volumes the askable row 90×. If the filter were only
        `event_id IS NOT NULL` it would take a window slot and be refused.
        """
        now = datetime.now(timezone.utc)
        from sqlalchemy.ext.asyncio import async_sessionmaker

        async with async_sessionmaker(engine, expire_on_commit=False)() as s:
            await _seed(s, now)

        stats, client = await _run(monkeypatch, engine, limit=5)

        assert stats["skipped_no_evidence"] == 0, stats
        assert [c for c in client.calls if "Red Sox vs. Yankees" in c] == []
        assert stats["generated"] == 1
