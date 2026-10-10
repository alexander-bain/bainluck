"""#10803 — the sunk-slot outcome arm returns the same rows, in the same order,
as the candidate-set form it replaced. Proved on real Postgres.

The old statement was `id IN (outcome arm AND open) AND id NOT IN (UNION of
tier<=1 arms AND open)`. On production its NOT IN built the whole `rangers`
name-match set (5,804 markets, mostly settled) to drop name matches from ~39
outcome candidates. The new statement tests the arms on the row:
`outcome arm AND (tier<=1 arms) IS NOT TRUE`, under the window's own open filter.

This file keeps the OLD form as the reference and compares the two over a seed
holding every case the exclusion can meet: a name match, an outcome-only row, a
row only the second tier<=1 arm reaches, a settled outcome match, an expired
one, and a row whose tier<=1 arm is NULL (a nullable column). The NULL row is
the mutant: `NOT (arms)` drops it while NOT IN kept it.
"""

from __future__ import annotations

import os
import time
from datetime import datetime, timedelta, timezone

import pytest

DB_URL = os.environ.get("SEARCH_TEST_DATABASE_URL")

pytestmark = [
    pytest.mark.asyncio,
    pytest.mark.skipif(
        not DB_URL,
        reason=(
            "set SEARCH_TEST_DATABASE_URL to run the real-Postgres sunk-slot "
            "identity contract (CI job `search-recall` provides one)"
        ),
    ),
]

NAME_MATCH = "Texas Rangers vs. Houston Astros - Run Line"
PENNANT = "MLB: 2026 American League Champion"
TICKER_ONLY = "Who wins Game 3?"
SETTLED = "MLB: 2025 American League Champion"
EXPIRED = "AL Wild Card Winner"
NULL_ARM = "AL West Winner"
NAME_ONLY = "Rangers to make the playoffs?"
UNRELATED = "Seattle Mariners vs. Detroit Tigers - Moneyline"


@pytest.fixture
async def maker():
    """A clean schema per test — the `search-recall` database is shared."""
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    import app.models.models  # noqa: F401 — registers every table on Base
    from app.models.models import FuturesMarket, FuturesOutcome
    from app.services.database import Base

    engine = create_async_engine(DB_URL)
    async with engine.begin() as conn:
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS pg_trgm"))
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)

    now = datetime.now(timezone.utc)
    later, earlier = now + timedelta(days=20), now - timedelta(days=2)
    # name, external_id, status, resolution_date, description, outcomes
    rows = [
        (NAME_MATCH, "kxmlbgame-1", "open", later, "rangers game",
         ["Texas Rangers", "Houston Astros"]),
        (PENNANT, "pm-pennant", "open", later, "the pennant",
         ["Texas Rangers", "Seattle Mariners", "New York Yankees"]),
        (TICKER_ONLY, "kxmlbseries-3", "open", later, "a series game",
         ["Texas Rangers", "Seattle Mariners"]),
        (SETTLED, "pm-pennant-2025", "closed", earlier, "last season",
         ["Texas Rangers", "Toronto Blue Jays"]),
        (EXPIRED, "pm-wildcard", "open", earlier, "already resolved",
         ["Texas Rangers", "Detroit Tigers"]),
        (NULL_ARM, "pm-alwest", "open", None, None,
         ["Texas Rangers", "Seattle Mariners"]),
        (NAME_ONLY, "pm-rangers-playoffs", "open", later, "yes or no",
         ["Yes", "No"]),
        (UNRELATED, "pm-sea-det", "open", later, "a game",
         ["Seattle Mariners", "Detroit Tigers"]),
    ]
    session_maker = async_sessionmaker(engine, expire_on_commit=False)
    async with session_maker() as session:
        for name, ext, status, resolves, description, outcomes in rows:
            market = FuturesMarket(
                source="polymarket", external_id=ext, name=name, status=status,
                resolution_date=resolves, description=description,
                llm_sport_category="baseball", category="championship",
            )
            session.add(market)
            await session.flush()
            for i, outcome in enumerate(outcomes):
                session.add(FuturesOutcome(
                    market_id=market.id, external_id=f"{ext}:{i}", name=outcome,
                    current_probability=0.5,
                ))
        await session.commit()

    yield session_maker

    await engine.dispose()


def _shapes():
    """The route's pieces, rebuilt over FuturesMarket alone: the window adds the
    open filter to every row, as `_futures_window_query` does."""
    from sqlalchemy import func, or_, select, union

    from app.models.models import FuturesMarket, FuturesOutcome
    from app.routes import events as E

    open_now = (
        FuturesMarket.status == "open",
        or_(
            FuturesMarket.resolution_date.is_(None),
            FuturesMarket.resolution_date >= datetime.now(timezone.utc),
        ),
    )

    def window_query(candidate_filter):
        return (
            select(FuturesMarket)
            .where(candidate_filter, *open_now)
            .order_by(FuturesMarket.name.asc(), FuturesMarket.id.asc())
            .limit(20)
        )

    def candidates_in(arms):
        """The pre-#10803 `_futures_candidates_in`, verbatim in shape."""
        selects = [select(FuturesMarket.id).where(arm, *open_now) for arm in arms]
        if len(selects) > 1:
            return FuturesMarket.id.in_(select(union(*selects).subquery().c.id))
        return FuturesMarket.id.in_(selects[0])

    tier1_arms = [
        FuturesMarket.name.ilike("%rangers%"),
        func.lower(FuturesMarket.external_id).like("kxmlb%"),
        # A nullable column: NULL for NULL_ARM's description.
        FuturesMarket.description.ilike("%rangers%"),
    ]
    outcome_arm = E._market_has_outcome(FuturesOutcome.name.ilike("%rangers%"))
    return window_query, candidates_in, tier1_arms, outcome_arm


async def _old_rows(session):
    from sqlalchemy import and_

    window_query, candidates_in, tier1_arms, outcome_arm = _shapes()
    result = await session.execute(window_query(and_(
        candidates_in([outcome_arm]), ~candidates_in(tier1_arms),
    )))
    return [m.name for m in result.scalars().all()]


async def _new_rows(session):
    from app.routes import events as E

    window_query, _candidates_in, tier1_arms, outcome_arm = _shapes()
    rows, state = await E._fetch_sunk_slot_outcome_rows(
        session, window_query, tier1_arms, outcome_arm, time.monotonic() + 10,
    )
    assert state == "merged"
    return [m.name for m in rows]


async def test_the_arm_returns_the_old_forms_rows_in_its_order(maker):
    async with maker() as session:
        old = await _old_rows(session)
    async with maker() as session:
        new = await _new_rows(session)
    assert new == old


async def test_the_rows_are_the_outcome_only_open_markets(maker):
    """The seed bites: the reference is not vacuously empty, and each excluded
    row is excluded for its own reason (name, ticker, settled, expired)."""
    async with maker() as session:
        new = await _new_rows(session)
    assert new == [NULL_ARM, PENNANT]


async def test_a_null_tier1_arm_keeps_its_row_as_not_in_did(maker):
    """The mutant: `~or_(*arms)` evaluates NULL for NULL_ARM and drops it."""
    from sqlalchemy import and_, or_

    window_query, candidates_in, tier1_arms, outcome_arm = _shapes()
    async with maker() as session:
        old = await _old_rows(session)
        mutant = [
            m.name for m in (await session.execute(window_query(
                and_(outcome_arm, ~or_(*tier1_arms))
            ))).scalars().all()
        ]
    assert NULL_ARM in old
    assert NULL_ARM not in mutant
