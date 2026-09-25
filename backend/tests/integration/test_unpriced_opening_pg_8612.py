"""#8612 — statement A10 lists the openings that were never a price, on real Postgres.

Discover card 40, 2026-09-25: "Kanye West performs in Russia by October 31: 8%
chance, down 86.3 points since Aug 19". The 0.94 opening was stored off a
16c/96c book. `update_max_movement`'s A10 lists such legs under
`market_metadata['unpriced_opening_ids']`, and `_biggest_move_from_opening`
refuses a listed leg as a sentence subject.

What only a real database can show:

  * the lateral that finds the snapshot AT `opening_captured_at` (a one-second
    window, `LIMIT 1`), which no recording double evaluates;
  * `NOT coalesce(priced, false)`: a one-sided book makes `priced` NULL, and
    without the coalesce the FILTER drops it instead of listing it;
  * the `id % :slices = :slice` scope and the `IS DISTINCT FROM` / removal arms,
    which are about which rows a real UPDATE touches.

Opt-in on `SEARCH_TEST_DATABASE_URL`, like `test_movement_window_pg.py`, and
run in CI's `search-recall` job.
"""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone

import pytest

DB_URL = os.environ.get("SEARCH_TEST_DATABASE_URL")

pytestmark = pytest.mark.skipif(
    not DB_URL,
    reason=(
        "set SEARCH_TEST_DATABASE_URL to run the real-Postgres unpriced-opening "
        "gate (CI job: search-recall)"
    ),
)

KEY = "unpriced_opening_ids"


def _engine():
    from sqlalchemy.ext.asyncio import create_async_engine

    import app.models.models  # noqa: F401 — registers every table on Base

    return create_async_engine(DB_URL)


async def _seed(markets):
    """Rebuild the schema and seed `markets`.

    `markets` is `[(label, status, metadata, legs)]`, and each leg is
    `(leg_label, opening, current, book)`, where `book` is one of:
      * `("book", bid, ask)` — a snapshot at `opening_captured_at` with that book;
      * `"nobook"` — a snapshot at `opening_captured_at` with both sides NULL;
      * `"nosnap"` — no snapshot at that instant (one an hour later instead).
    Returns `{label: market_id}` and `{leg_label: outcome_id}`.
    """
    from sqlalchemy.ext.asyncio import async_sessionmaker

    from app.models.models import FuturesMarket, FuturesOddsSnapshot, FuturesOutcome
    from app.services.database import Base

    engine = _engine()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)

    maker = async_sessionmaker(engine, expire_on_commit=False)
    now = datetime.now(timezone.utc)
    opened = now - timedelta(days=30)
    market_ids: dict[str, int] = {}
    outcome_ids: dict[str, int] = {}
    async with maker() as session:
        for label, status, metadata, legs in markets:
            market = FuturesMarket(
                source="polymarket",
                external_id=f"OPEN8612-{label}",
                name=f"Opening case {label}",
                category="futures",
                market_tier=1,
                status=status,
                resolution_date=now + timedelta(days=30),
                market_metadata=metadata,
            )
            session.add(market)
            await session.flush()
            market_ids[label] = market.id
            for leg_label, opening, current, book in legs:
                outcome = FuturesOutcome(
                    market_id=market.id,
                    external_id=f"OUT-{leg_label}",
                    name=leg_label,
                    is_winner=False,
                    current_probability=current,
                    opening_probability=opening,
                    opening_captured_at=opened,
                    last_updated=now,
                )
                session.add(outcome)
                await session.flush()
                outcome_ids[leg_label] = outcome.id
                if book == "nosnap":
                    at, bid, ask = opened + timedelta(hours=1), 0.40, 0.42
                elif book == "nobook":
                    at, bid, ask = opened, None, None
                else:
                    _, bid, ask = book
                    at = opened
                session.add(
                    FuturesOddsSnapshot(
                        outcome_id=outcome.id,
                        bookmaker="polymarket",
                        probability=opening,
                        yes_bid=bid,
                        yes_ask=ask,
                        captured_at=at,
                    )
                )
        await session.commit()
    await engine.dispose()
    return market_ids, outcome_ids


def _run(slices: int = 1, now_epoch: float | None = None):
    """Drive the REAL `update_max_movement`, with A10 judging every market."""
    import app.tasks as tasks_mod
    import app.tasks.base as base_mod
    import app.tasks.futures_movers_warm as warm_mod
    from app.tasks import update_max_movement

    class _Ctx:
        async def __aenter__(self):
            from sqlalchemy.ext.asyncio import async_sessionmaker

            self._engine = _engine()
            self._session = async_sessionmaker(self._engine, expire_on_commit=False)()
            return self._session

        async def __aexit__(self, *exc):
            await self._session.close()
            await self._engine.dispose()
            return False

    async def _no_warm(_session):
        return {"terminal": "skipped", "completed": 0}

    real = (
        base_mod.get_task_session,
        warm_mod.warm_futures_movers,
        tasks_mod.OPENING_BOOK_SLICES,
        tasks_mod._time.time,
    )
    base_mod.get_task_session = lambda: _Ctx()
    warm_mod.warm_futures_movers = _no_warm
    tasks_mod.OPENING_BOOK_SLICES = slices
    if now_epoch is not None:
        tasks_mod._time.time = lambda: now_epoch
    try:
        return update_max_movement.run()
    finally:
        (
            base_mod.get_task_session,
            warm_mod.warm_futures_movers,
            tasks_mod.OPENING_BOOK_SLICES,
            tasks_mod._time.time,
        ) = real


async def _metadata(market_ids):
    from sqlalchemy import text

    engine = _engine()
    out = {}
    async with engine.connect() as conn:
        for label, mid in market_ids.items():
            out[label] = (
                await conn.execute(
                    text("SELECT market_metadata FROM futures_markets WHERE id = :i"),
                    {"i": mid},
                )
            ).scalar()
    await engine.dispose()
    return out


def _go(coro):
    import asyncio

    return asyncio.run(coro)


def test_the_kanye_opening_is_listed_and_a_priced_one_is_not() -> None:
    """The specimen (0.94 on 16c/96c) is listed; the tight control is not."""
    markets, legs = _go(_seed([
        ("kanye", "open", None, [("kanye-yes", 0.94, 0.077, ("book", 0.16, 0.96))]),
        ("tight", "open", None, [("tight-yes", 0.395, 0.065, ("book", 0.39, 0.40))]),
    ]))
    result = _run()
    meta = _go(_metadata(markets))

    assert (meta["kanye"] or {}).get(KEY) == [legs["kanye-yes"]], meta
    assert KEY not in (meta["tight"] or {}), (
        f"a 39c/40c opening is a price and must not be refused: {meta}"
    )
    assert result["unpriced_openings_written"] == 1, result


def test_a_one_sided_book_lists_and_a_no_book_row_does_not() -> None:
    """One side empty is the wide case at its limit; no book at all is a price."""
    markets, legs = _go(_seed([
        ("board", "open", None, [
            ("one-sided", 0.60, 0.20, ("book", None, 0.90)),
            ("no-book", 0.60, 0.20, "nobook"),
            ("no-snapshot", 0.60, 0.20, "nosnap"),
        ]),
    ]))
    _run()
    listed = (_go(_metadata(markets))["board"] or {}).get(KEY)

    assert listed == [legs["one-sided"]], (
        "expected only the one-sided leg. A no-book row is a price, and a leg "
        f"with no snapshot at its opening instant is unjudged: {listed}"
    )


def test_the_rail_is_exclusive_at_twenty_cents() -> None:
    """A spread of exactly 0.20 is refused and 0.19 is a price, as in A8."""
    markets, legs = _go(_seed([
        ("rail", "open", None, [
            ("at-rail", 0.60, 0.20, ("book", 0.50, 0.70)),
            ("under-rail", 0.60, 0.20, ("book", 0.51, 0.70)),
        ]),
    ]))
    _run()
    listed = (_go(_metadata(markets))["rail"] or {}).get(KEY)
    assert listed == [legs["at-rail"]], listed


def test_a_leg_under_the_surprise_rung_is_not_judged() -> None:
    """Scope is the rung a card can score or state, not every leg."""
    markets, _legs = _go(_seed([
        ("quiet", "open", None, [("quiet-yes", 0.50, 0.45, ("book", 0.02, 0.97))]),
    ]))
    _run()
    assert KEY not in (_go(_metadata(markets))["quiet"] or {})


def test_an_empty_verdict_removes_a_stale_list_and_keeps_other_metadata() -> None:
    """A market whose listed leg now judges priced loses the key, nothing else."""
    markets, _legs = _go(_seed([
        ("healed", "open", {KEY: [999999], "polymarket_event_id": "e1"},
         [("healed-yes", 0.60, 0.20, ("book", 0.59, 0.61))]),
        ("never", "open", {"polymarket_event_id": "e2"},
         [("never-yes", 0.60, 0.20, ("book", 0.59, 0.61))]),
    ]))
    result = _run()
    meta = _go(_metadata(markets))

    assert meta["healed"] == {"polymarket_event_id": "e1"}, meta
    assert meta["never"] == {"polymarket_event_id": "e2"}, meta
    assert result["unpriced_openings_written"] == 1, (
        f"only the healed market should be written: {result}"
    )


def test_a_closed_market_is_not_judged() -> None:
    markets, _legs = _go(_seed([
        ("closed", "closed", None, [("closed-yes", 0.94, 0.07, ("book", 0.16, 0.96))]),
    ]))
    _run()
    assert KEY not in (_go(_metadata(markets))["closed"] or {})


def test_a_run_judges_only_its_slice() -> None:
    """`id % slices = slice`: the other markets wait for their own run."""
    markets, _legs = _go(_seed([
        (f"m{i}", "open", None, [(f"m{i}-yes", 0.94, 0.07, ("book", 0.16, 0.96))])
        for i in range(4)
    ]))
    # Epoch 0 → slice 0 of 2: exactly the even market ids.
    _run(slices=2, now_epoch=0.0)
    meta = _go(_metadata(markets))
    listed = {label for label, m in meta.items() if KEY in (m or {})}
    expected = {label for label, mid in markets.items() if mid % 2 == 0}
    assert listed == expected, (listed, expected)

    # The next ten-minute run takes the odd ones.
    _run(slices=2, now_epoch=600.0)
    meta = _go(_metadata(markets))
    assert all(KEY in (m or {}) for m in meta.values()), meta


def test_a_second_run_rewrites_nothing() -> None:
    markets, _legs = _go(_seed([
        ("kanye", "open", None, [("kanye-yes", 0.94, 0.077, ("book", 0.16, 0.96))]),
    ]))
    assert _run()["unpriced_openings_written"] == 1
    assert _run()["unpriced_openings_written"] == 0
