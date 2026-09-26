"""#8935 — one failing event no longer throws away its whole Polymarket write batch (real Postgres).

PILLAR: TRUTH. SHIP: a Polymarket market's price, status and result stop going
stale for an hour, or six, because a different market in the same write batch
hit a database deadlock.

Production, recovery pass 2026-09-26 20:39Z: one ``DeadlockDetectedError`` and
then 18 ``InFailedSQLTransactionError`` on every later event in the batch. The
writer caught each failure and carried on inside the aborted transaction, and
its single closing ``COMMIT`` is turned into a ``ROLLBACK`` by Postgres, so the
events written BEFORE the failure were discarded as well.

Only Postgres can grade this. A session double does not abort a transaction on
a failed statement and does not turn COMMIT into ROLLBACK. The failure here is
a real database-side error (a title longer than ``futures_markets.name``'s
300), which aborts the transaction exactly as the deadlock did.

The payload is Gamma's own bytes (``tests/fixtures/polymarket_leg_dates_8466``),
copied to three events with distinct event and condition ids, and driven
through the REAL parser and the REAL ``_process_event_batch``.
"""

from __future__ import annotations

import copy
import json
import os
from pathlib import Path

import pytest

DB_URL = os.environ.get("SEARCH_TEST_DATABASE_URL")

pytestmark = pytest.mark.skipif(
    not DB_URL,
    reason="set SEARCH_TEST_DATABASE_URL to run the real-Postgres #8935 batch-savepoint gate",
)

FIXTURE = (
    Path(__file__).resolve().parent.parent
    / "fixtures"
    / "polymarket_leg_dates_8466"
    / "gamma-event-1038648.json"
)

FIRST, POISONED, LAST = "8935001", "8935002", "8935003"


def _copy(event_id: str, *, poison: bool = False) -> dict:
    raw = copy.deepcopy(json.loads(FIXTURE.read_text()))
    raw["id"] = event_id
    raw["slug"] = f"{raw['slug']}-{event_id}"
    for m in raw["markets"]:
        m["id"] = f"{m['id']}{event_id}"
        m["conditionId"] = f"{m['conditionId']}{event_id}"
    if poison:
        # futures_markets.name is String(300): Postgres refuses this at the upsert,
        # a database-side failure that aborts the transaction like a deadlock does.
        raw["title"] = "x" * 400
    return raw


@pytest.fixture
async def pg_engine(monkeypatch):
    from sqlalchemy.ext.asyncio import create_async_engine

    import app.models.models  # noqa: F401 — registers every table on Base
    import app.tasks.base as task_base
    from app.services.database import Base

    engine = create_async_engine(DB_URL)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    monkeypatch.setattr(task_base, "DATABASE_URL", DB_URL)
    yield engine
    await engine.dispose()


async def _write_batch(raws: list[dict]) -> dict:
    """The REAL discovery-poll writer, handed one batch."""
    from sqlalchemy.dialects.postgresql import insert as pg_insert

    from app.models import FuturesMarket, FuturesOddsSnapshot, FuturesOutcome
    from app.services.polymarket_api import PolymarketAPIService
    from app.tasks.polymarket import _process_event_batch
    from app.utils.market_label_normalization import compute_market_tier
    from app.utils.odds_math import probability_to_american

    class _Counting(dict):
        def __missing__(self, key):
            return 0

    stats = _Counting({"errors": []})
    service = PolymarketAPIService()
    events = [service._parse_event(r) for r in raws]
    assert all(e is not None and len(e.markets) == 6 for e in events)
    await _process_event_batch(
        events, stats, FuturesMarket, FuturesOutcome, FuturesOddsSnapshot,
        pg_insert, probability_to_american, compute_market_tier,
    )
    return stats


async def _parents(engine) -> set[str]:
    from sqlalchemy import text

    async with engine.connect() as conn:
        rows = (await conn.execute(text(
            "SELECT external_id FROM futures_markets "
            "WHERE source='polymarket' AND external_id NOT LIKE '0x%'"
        ))).fetchall()
    return {r[0] for r in rows}


async def _legs_of(engine, event_id: str) -> int:
    from sqlalchemy import text

    async with engine.connect() as conn:
        return (await conn.execute(text(
            "SELECT count(*) FROM futures_markets "
            "WHERE source='polymarket' AND external_id LIKE :sfx"
        ), {"sfx": f"0x%{event_id}"})).scalar_one()


async def test_a_clean_batch_writes_every_event(pg_engine):
    """Control: without the poison all three land, so the arm below is
    measuring the failure and not the rig."""
    stats = await _write_batch([_copy(FIRST), _copy(POISONED), _copy(LAST)])
    assert not stats["errors"], stats["errors"]
    assert await _parents(pg_engine) == {FIRST, POISONED, LAST}


async def test_one_failing_event_rolls_back_only_itself(pg_engine):
    stats = await _write_batch(
        [_copy(FIRST), _copy(POISONED, poison=True), _copy(LAST)]
    )

    # Exactly one failure, and it is the poisoned event's own: the event after
    # it must not fail with "current transaction is aborted".
    assert [e.split(":")[0] for e in stats["errors"]] == [POISONED], stats["errors"]
    assert not any("InFailedSQLTransaction" in e for e in stats["errors"])

    # The event before the failure survives the closing COMMIT, and so does the
    # event after it, each with its six legs. Only the poisoned one is missing.
    assert await _parents(pg_engine) == {FIRST, LAST}
    assert await _legs_of(pg_engine, FIRST) == 6
    assert await _legs_of(pg_engine, LAST) == 6
    assert await _legs_of(pg_engine, POISONED) == 0
