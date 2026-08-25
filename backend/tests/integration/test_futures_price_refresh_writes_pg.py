"""#2199 — the futures price refresher WRITES, proved against real Postgres.

## Why this file exists, stated as the defect it catches

`b19708f0` / v3899 shipped the refresher with 19,906 tests green, and its first
live run returned a `failed` terminal having written **zero** snapshots — not
partially, not transiently, but *by construction and permanently*. The writer
resolved its writable outcomes with

    WHERE market_id = :mid AND is_winner IS NULL

against a column declared `Mapped[bool] = mapped_column(Boolean, default=False)`.
No production row is ever NULL; unsettled is stored as `FALSE`. Measured across
every eligible tier-1 open market: **0 NULL, 10,762 FALSE, 42 TRUE**. So
`existing` came back empty for every market, every priced item took the
`outcome_id is None` branch, and the task incremented `unknown_outcomes` and
moved on.

**The only test covering the property asserted the module's source text**
(`assert "is_winner IS NULL" in _MODULE_SRC`). That is a grep of the
implementation: it passes iff the bug is present, and it cannot fail when the
predicate matches no rows. A source assertion can pin an intent. It can never
observe a write.

So the gate here is data-level, and it is deliberately the *cheapest possible*
shape: seed an outcome exactly the way production seeds it — `is_winner=False`,
the model default, never `None` — then run the real `_write_prices` against a
real database and assert a `futures_odds_snapshots` row lands. A fixture that
sets `is_winner=None` reproduces the false green, which is why
`test_a_null_seeded_fixture_is_the_false_green` exists: it demonstrates the trap
rather than describing it.

Real Postgres, not SQLite and not a recording double, for two reasons that both
bite here. `_write_prices` builds its INSERT with the postgresql dialect's
`pg_insert`, which does not compile elsewhere. And a mock session answers
whatever the test told it to — the entire failure above is a *writer/data*
contract split, and every instrument that does not touch real rows agreed the
feature worked.

Opt-in on `SEARCH_TEST_DATABASE_URL`, following
`test_provenance_enum_real_postgres.py`: there is no local Postgres in the agent
sandbox (initdb fails on shmget), so **CI is the environment that runs this**,
in the `search-recall` job, whose skip-detector refuses to let an unrun gate
read as a passing one.
"""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone

import pytest

DB_URL = os.environ.get("SEARCH_TEST_DATABASE_URL")

pytestmark = [
    pytest.mark.asyncio,
    pytest.mark.skipif(
        not DB_URL,
        reason=(
            "set SEARCH_TEST_DATABASE_URL to run the real-Postgres futures "
            "price-writer gate (CI job: search-recall)"
        ),
    ),
]

_BOOKMAKER = "kalshi"


@pytest.fixture
async def db():
    """A real Postgres carrying the real schema."""
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    import app.models.models  # noqa: F401  — registers every table on Base
    from app.services.database import Base

    engine = create_async_engine(DB_URL)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)

    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as session:
        yield session

    await engine.dispose()


async def _seed_market(session, *, is_winner, external_id="ALC"):
    """One tier-1 open market with one outcome, seeded as production seeds.

    `is_winner` is passed explicitly rather than defaulted so the callers read as
    the two halves of the tri-state the predicate has to survive.
    """
    from app.models.models import FuturesMarket, FuturesOutcome

    market = FuturesMarket(
        source=_BOOKMAKER,
        external_id=f"KXTEST-{external_id}",
        name="Test Championship Winner",
        category="futures",
        market_tier=1,
        status="open",
        resolution_date=datetime.now(timezone.utc) + timedelta(days=30),
    )
    session.add(market)
    await session.flush()

    outcome = FuturesOutcome(
        market_id=market.id,
        external_id=external_id,
        name=external_id,
        is_winner=is_winner,
    )
    session.add(outcome)
    await session.flush()
    return market, outcome


async def _snapshot_count(session, outcome_id: int) -> int:
    from sqlalchemy import text

    return (
        await session.execute(
            text(
                "SELECT COUNT(*) FROM futures_odds_snapshots WHERE outcome_id = :oid"
            ),
            {"oid": outcome_id},
        )
    ).scalar()


def _priced(external_id="ALC", probability=0.305):
    return [
        {
            "external_id": external_id,
            "probability": probability,
            "yes_bid": 0.30,
            "yes_ask": 0.31,
            "last_price": 0.305,
        }
    ]


def _stats():
    return {"unknown_outcomes": 0}


class TestTheWriterActuallyWrites:
    async def test_an_unsettled_outcome_gets_a_snapshot(self, db):
        """THE founding case. `is_winner=False` is what production stores.

        If this fails, the task is inert in production no matter what its
        terminal, its beat wiring, or its source text say.
        """
        from app.tasks.futures_price_refresh import _write_prices

        market, outcome = await _seed_market(db, is_winner=False)
        stats = _stats()

        written = await _write_prices(db, market.id, _BOOKMAKER, _priced(), stats)
        await db.commit()

        assert written == 1, "the unsettled outcome was not written"
        assert stats["unknown_outcomes"] == 0, (
            "the outcome was seeded and priced, so treating it as unknown means "
            "the resolving predicate missed a row it owns"
        )
        assert await _snapshot_count(db, outcome.id) == 1

    async def test_the_price_columns_move_too(self, db):
        """A snapshot without the current_* update leaves the board reading July.

        #2199's user-visible symptom was `futures_outcomes.current_probability`
        holding a month-old value while the board rendered it as today's, so the
        snapshot alone is not the ship.
        """
        from sqlalchemy import text
        from app.tasks.futures_price_refresh import _write_prices

        market, outcome = await _seed_market(db, is_winner=False)

        await _write_prices(db, market.id, _BOOKMAKER, _priced(probability=0.305), _stats())
        await db.commit()

        row = (
            await db.execute(
                text(
                    "SELECT current_probability, last_updated FROM futures_outcomes "
                    "WHERE id = :oid"
                ),
                {"oid": outcome.id},
            )
        ).first()
        assert float(row[0]) == pytest.approx(0.305, abs=1e-6)
        assert row[1] is not None


class TestTheSettledRefusalStillHolds:
    """Fixing the predicate must not cost the refusal it was protecting.

    Gotcha #21: a settled book stops quoting, and re-pricing it can only corrupt
    resolved state. `IS NOT TRUE` is the narrowest change that keeps this.
    """

    async def test_a_settled_outcome_is_refused(self, db):
        from app.tasks.futures_price_refresh import _write_prices

        market, outcome = await _seed_market(db, is_winner=True)
        stats = _stats()

        written = await _write_prices(db, market.id, _BOOKMAKER, _priced(), stats)
        await db.commit()

        assert written == 0, "a settled outcome must never be re-priced"
        assert await _snapshot_count(db, outcome.id) == 0
        assert stats["unknown_outcomes"] == 1, (
            "the refusal must be COUNTED, not silent — an invisible refusal is "
            "indistinguishable from the inert writer this file exists to catch"
        )

    async def test_settled_and_unsettled_siblings_are_separated(self, db):
        """The real shape: one market, a decided winner, the rest still live.

        A predicate that is merely non-empty could still admit everything. This
        is the case that distinguishes `IS NOT TRUE` from `TRUE OR FALSE`.
        """
        from app.models.models import FuturesOutcome
        from app.tasks.futures_price_refresh import _write_prices

        market, live = await _seed_market(db, is_winner=False, external_id="ALC")
        settled = FuturesOutcome(
            market_id=market.id, external_id="SIN", name="SIN", is_winner=True
        )
        db.add(settled)
        await db.flush()

        written = await _write_prices(
            db,
            market.id,
            _BOOKMAKER,
            _priced("ALC") + _priced("SIN", 0.9),
            _stats(),
        )
        await db.commit()

        assert written == 1
        assert await _snapshot_count(db, live.id) == 1
        assert await _snapshot_count(db, settled.id) == 0


class TestTheFalseGreenIsReproducible:
    async def test_null_is_unreachable_even_when_you_ask_for_it(self, db):
        """You cannot seed the row shape the old predicate looked for. At all.

        This test was originally written the obvious way — seed `is_winner=None`,
        assert the stored value is NULL, and show that `IS NULL` matches it — on
        the assumption that a NULL fixture is the trap a future author would fall
        into. **CI disproved that on the first run** (`assert False is None`), and
        the real answer is stronger than the one being asserted:

        SQLAlchemy's ``default=False`` fires whenever the value is None at INSERT
        time, including when None was passed *explicitly*. So passing
        ``is_winner=None`` does not produce a NULL row — it produces `False`,
        exactly like every production writer. The trap is not that a NULL fixture
        would mislead; it is that **NULL is not reachable through the ORM at
        all**, so no amount of fixture-writing through the normal path could ever
        have exercised the `IS NULL` branch.

        That is why `assert "is_winner IS NULL" in _MODULE_SRC` was the only test
        anyone wrote: it is the only assertion about this predicate that a
        model-shaped test *can* make. The predicate described a population the
        ORM cannot construct, so the only reachable statement about it was a
        statement about the source text.
        """
        from sqlalchemy import text

        _, outcome = await _seed_market(db, is_winner=None)
        await db.commit()

        stored = (
            await db.execute(
                text("SELECT is_winner FROM futures_outcomes WHERE id = :oid"),
                {"oid": outcome.id},
            )
        ).scalar()
        assert stored is False, (
            "explicit None must be coerced to False by the column default — if "
            "this ever returns None the column has become genuinely nullable and "
            "the writer's predicate needs re-deciding"
        )

    async def test_the_old_predicate_matched_nothing_and_the_new_one_matches_the_work(
        self, db
    ):
        """The production census (0 NULL / 10,762 FALSE / 42 TRUE), reproduced in CI.

        This is the assertion that would have caught #2199 before deploy, and it
        is worth stating as a comparison rather than two separate counts: on the
        very same rows, the old predicate selects **nothing** and the new one
        selects **exactly the unsettled work**. No mocking, no source text — two
        queries against real rows written the way production writes them.
        """
        from sqlalchemy import text
        from app.models.models import FuturesOutcome

        market, _ = await _seed_market(db, is_winner=False, external_id="ALC")
        db.add(
            FuturesOutcome(
                market_id=market.id, external_id="SIN", name="SIN", is_winner=True
            )
        )
        await db.commit()

        async def _count(predicate: str) -> int:
            return (
                await db.execute(
                    text(
                        "SELECT COUNT(*) FROM futures_outcomes "
                        f"WHERE market_id = :mid AND {predicate}"
                    ),
                    {"mid": market.id},
                )
            ).scalar()

        assert await _count("is_winner IS NULL") == 0, (
            "the shipped predicate — it matches nothing, which is the defect"
        )
        assert await _count("is_winner IS NOT TRUE") == 1, (
            "the fix — exactly the one unsettled outcome, settled sibling excluded"
        )

    async def test_is_not_true_loses_nothing_the_old_predicate_would_have_found(
        self, db
    ):
        """`IS NOT TRUE` must be a strict superset of `IS NULL`, not a swap.

        Production's `futures_outcomes.is_winner` is `is_nullable = YES` with a
        column default of `false` (checked against the live schema), so a genuine
        NULL is *physically* storable even though no writer produces one. If one
        ever appears — a raw backfill, a migration, a future writer — it means
        "not settled", and the refresher must still price it. A fix that merely
        moved the blind spot from FALSE to NULL would not be a fix.

        Asserted as a truth table rather than by inserting a NULL row, because
        the two schemas disagree about whether that row can exist: production is
        built by Alembic and permits NULL, while this test database is built by
        `Base.metadata.create_all`, where the non-Optional `Mapped[bool]`
        annotation renders the column NOT NULL. A test that inserted NULL would
        pass or error depending on which schema it met, which is not a property
        worth asserting. The three-valued semantics are the same either way and
        are what the predicate actually rests on.
        """
        from sqlalchemy import text

        row = (
            await db.execute(
                text(
                    "SELECT (NULL::boolean IS NOT TRUE),  (NULL::boolean IS NULL), "
                    "       (false IS NOT TRUE),          (false IS NULL), "
                    "       (true IS NOT TRUE),           (true IS NULL)"
                )
            )
        ).first()
        null_not_true, null_is_null, false_not_true, false_is_null, true_not_true, _ = row

        # The superset: everything `IS NULL` admits, `IS NOT TRUE` also admits.
        assert null_is_null is True and null_not_true is True

        # The rows production actually has — admitted by the fix, invisible to the
        # shipped predicate. This single line is the whole of #2199.
        assert false_is_null is False and false_not_true is True

        # And the refusal that must survive the widening (gotcha #21).
        assert true_not_true is False

    async def test_the_model_default_is_false_not_null(self, db):
        """The fact the whole defect rests on, pinned where a schema change trips it.

        If `is_winner` ever becomes genuinely nullable, the writer's predicate
        needs re-deciding and this assertion is where that conversation starts.
        """
        from sqlalchemy import text
        from app.models.models import FuturesMarket, FuturesOutcome

        market = FuturesMarket(
            source=_BOOKMAKER,
            external_id="KXTEST-DEFAULT",
            name="Default Probe",
            category="futures",
            market_tier=1,
            status="open",
        )
        db.add(market)
        await db.flush()
        # No `is_winner` argument at all — the path every ingest writer takes.
        outcome = FuturesOutcome(market_id=market.id, external_id="X", name="X")
        db.add(outcome)
        await db.commit()

        stored = (
            await db.execute(
                text("SELECT is_winner FROM futures_outcomes WHERE id = :oid"),
                {"oid": outcome.id},
            )
        ).scalar()
        assert stored is False, (
            "unsettled is stored as FALSE — a writer predicated on NULL is inert"
        )
