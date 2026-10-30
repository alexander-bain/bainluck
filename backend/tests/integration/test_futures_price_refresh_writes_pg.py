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
`test_null_is_unreachable_even_when_you_ask_for_it` exists: it demonstrates the
trap rather than describing it.

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
        when this was written the two schemas disagreed about whether that row
        could exist: production is built by Alembic and permits NULL, while this
        test database is built by `Base.metadata.create_all`, which rendered the
        column NOT NULL from a non-Optional `Mapped[bool]`. A test that inserted
        NULL would have passed or errored depending on which schema it met, which
        is not a property worth asserting.

        🔴 **THAT REASON EXPIRED, and the truth table is kept for a different
        one.** CAL-P156/CAL-P157 closed the drift: the model is now
        `Mapped[Optional[bool]]` with `server_default=text("false")`, so a
        metadata-built database has production's exact column and a NULL row IS
        reachable — `tests/integration/test_futures_outcome_grade_schema_parity_pg.py`
        inserts one and reads it back. What survives is that the three-valued
        semantics, not any one fixture, are what the predicate rests on.
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

        The column IS genuinely nullable now (CAL-P156/CAL-P157 aligned the model
        with production), and this still holds — SQLAlchemy's client-side
        `default=False` fires on the ORM path whether or not NULL is legal, which
        is why the widening moved no writer. What would trip this is the default
        going away; then ordinary ingest starts storing unknown truth and the
        writer's predicate needs re-deciding.
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


# --- #3315: the selector reaches the front page ------------------------------
#
# The class below is the named regression for "a served page-one outcome whose
# venue price differs by >=3 points for more than an hour must be caught by the
# job". It is here, against real Postgres, rather than in the source-text suite
# for the reason this whole file exists: the pre-#3315 predicate was *readable*
# and *shipped* and *green*, and the only instrument that could have contradicted
# it is one that runs the real SELECT against real rows.
#
# THE SPECIMEN IS REAL AND IT IS SEEDED FROM ITS PRODUCTION VALUES. Market 112996,
# "Brazil Presidential Election", Polymarket Gamma event 45915, `market_tier = 2`,
# `volume = 114,137,967`, outcomes last written 1,109 hours before 2026-09-05.
# On that day the card rendered Flávio Bolsonaro at 26.2% while Gamma quoted
# 39.9% — 13.7 points, on Discover page one.


_BRAZIL_VOLUME = 114_137_967
_BRAZIL_EVENT_ID = "45915"


async def _seed_brazil(session, *, market_tier=2, volume=_BRAZIL_VOLUME):
    """The Brazil Presidential Election row, at its production shape."""
    from app.models.models import FuturesMarket, FuturesOutcome

    market = FuturesMarket(
        source="polymarket",
        external_id="0xbrazil",
        name="Brazil Presidential Election",
        category="futures",
        market_tier=market_tier,
        volume=volume,
        status="open",
        group_id=f"polymarket:{_BRAZIL_EVENT_ID}",
        market_metadata={"polymarket_event_id": _BRAZIL_EVENT_ID},
        resolution_date=datetime.now(timezone.utc) + timedelta(days=380),
    )
    session.add(market)
    await session.flush()
    # Priced 46 days ago and never since — the row the card renders.
    session.add(
        FuturesOutcome(
            market_id=market.id,
            external_id="0xbolsonaro",
            name="Flávio Bolsonaro",
            is_winner=False,
            current_probability=0.262,
        )
    )
    await session.flush()
    return market


#: The predicate as it stood before #3315, kept verbatim so the regression can
#: prove its own necessity in one run instead of asking a reader to trust that
#: the old code would have failed. Memory of this codebase: a new mechanism that
#: never pins the incumbent's inadequacy cannot be shown to have been needed.
_PRE_3315_VALUE_SQL = "fm.market_tier = 1 AND fm.volume >= :volume_floor"


class TestTheSweepReachesTheFrontPage:
    async def test_the_brazil_card_is_selected_and_the_old_predicate_refused_it(
        self, db
    ):
        """THE #3315 regression. Both halves in one test, on purpose.

        The assertion that matters is the second one: the widened predicate
        selects Brazil. The first is the control — the *same row*, the *same
        database*, the pre-#3315 predicate — because "the new selector works" is
        compatible with "the old one did too", and that reading would make this
        whole change decoration.
        """
        from sqlalchemy import text
        from app.tasks.futures_price_refresh import (
            HIGH_VALUE_SQL,
            HIGH_VALUE_VOLUME_FLOOR,
            _scan_candidates,
            pool_bind_params,
        )

        market = await _seed_brazil(db)
        await db.commit()

        def _count(value_sql):
            return text(
                f"SELECT COUNT(*) FROM futures_markets fm "
                f"WHERE fm.id = :mid AND ({value_sql})"
            )

        # #5781: taken WHOLE, never listed. This site is the one no local test
        # could reach — it is PG-only, so it does not run without a database —
        # and its hand-built params dict went stale the moment a third value arm
        # added a third bind. A missing bind does not degrade here: SQLAlchemy
        # refuses the statement outright. Extra keys are harmless to `text()`.
        params = {"mid": market.id, **pool_bind_params()}
        before = (await db.execute(_count(_PRE_3315_VALUE_SQL), params)).scalar()
        after = (await db.execute(_count(HIGH_VALUE_SQL), params)).scalar()

        assert before == 0, (
            "the pre-#3315 predicate would have selected Brazil, so this "
            "regression proves nothing — check the control, not the fix"
        )
        assert after == 1, "the widened value test still refuses a tier-2 card"

        # ...and end to end, through the selector the beat actually calls.
        selected = await _scan_candidates(
            db, volume_floor=HIGH_VALUE_VOLUME_FLOOR, stale_hours=6
        )
        assert market.id in {m["id"] for m in selected}
        row = next(m for m in selected if m["id"] == market.id)
        assert row["poly_event_id"] == _BRAZIL_EVENT_ID, (
            "selected but not addressable: /events?id=0x… does not resolve a "
            "condition id, so the fetch would 422 and the card would stay wrong"
        )

    async def test_a_fresh_card_is_not_reselected(self, db):
        """The staleness bound still bounds. Widening the value test must not

        turn the sweep into "re-price everything every hour" — that is a cost
        change dressed as a correctness one, and it would put the whole tier-2
        population on an hourly third-party fetch.
        """
        from app.models.models import FuturesOddsSnapshot, FuturesOutcome
        from sqlalchemy import select
        from app.tasks.futures_price_refresh import (
            HIGH_VALUE_VOLUME_FLOOR,
            _scan_candidates,
        )

        market = await _seed_brazil(db)
        outcome = (
            await db.execute(
                select(FuturesOutcome).where(FuturesOutcome.market_id == market.id)
            )
        ).scalars().first()
        db.add(
            FuturesOddsSnapshot(
                outcome_id=outcome.id,
                bookmaker="polymarket",
                probability=0.399,
                captured_at=datetime.now(timezone.utc),
            )
        )
        await db.commit()

        selected = await _scan_candidates(
            db, volume_floor=HIGH_VALUE_VOLUME_FLOOR, stale_hours=6
        )
        assert market.id not in {m["id"] for m in selected}

    async def test_a_page_one_card_with_no_volume_at_all_is_reached_by_the_served_arm(
        self, db
    ):
        """The arm that does not care what the market is worth.

        Seeded at tier 5 with NULL volume — outside every value test there is,
        including the widened one — and selected anyway, because page one is
        rendering it. This is the property the value predicate structurally
        cannot express, and the reason #3315 needed two changes rather than one.
        """
        from app.tasks.futures_price_refresh import (
            HIGH_VALUE_VOLUME_FLOOR,
            _scan_candidates,
            _scan_served_candidates,
        )

        market = await _seed_brazil(db, market_tier=5, volume=None)
        await db.commit()

        by_value = await _scan_candidates(
            db, volume_floor=HIGH_VALUE_VOLUME_FLOOR, stale_hours=6
        )
        assert market.id not in {m["id"] for m in by_value}, (
            "seeded outside every value test, or the control below proves nothing"
        )

        served = await _scan_served_candidates(
            db, market_ids=[market.id], stale_minutes=45
        )
        assert [m["id"] for m in served] == [market.id]
        assert served[0]["priority"] is True and served[0]["served"] is True


# --- #5771 / CERT-2772: withdrawing the LEG is not withdrawing the NUMBER ------
#
# CERT-2772 BLOCKed #5771's first presentation on exactly the split this file
# exists to catch. The task's new refusal and its `futures_outcomes` withdrawal
# both worked and were both green — against a recording session. The page did
# not move: the event hero and the chart read `Event.win_probability_sources`,
# which the 15-minute matcher stamps from those outcome rows and does not
# re-derive when one goes quiet. Graded reproduction on the exact sha:
# `before=0.99:blend after=0.99:blend`.
#
# So the gate is the SERVED number, resolved and formatted the way the route
# resolves and formats it — `compute_aggregate_probability`, then
# `rendered_duel_percents`, which is the pair the event page prints — over rows
# a real Postgres holds after the REAL task has run. A recording double cannot
# fail this test, which is the point of putting it here.
#
# THE SPECIMEN, at its production values (read 2026-09-12/13):
#   event 15298125, `scheduled`, kicks off 2026-09-13 19:00Z
#   win_probability_sources = {'kalshi': {'value': 0.99, 'eligibility':
#       {'market_id': 60482102, 'source_market_id': 'KXLALIGAGAME-26SEP13SEVVCF',
#        ...}}, 'betting_book_count': 2}
#   opening_home_probability = 0.5856
#   one linked Kalshi market, three legs, all three priced (0.99 / 0.01 / 0.01)

_SEVILLA_TICKER = "KXLALIGAGAME-26SEP13SEVVCF"
_SEVILLA_HERO = 0.99
_SEVILLA_OPENING = 0.5856


async def _seed_sport(session):
    from sqlalchemy import select

    from app.models.models import Sport

    existing = (
        await session.execute(select(Sport).where(Sport.key == "soccer_spain_la_liga"))
    ).scalar_one_or_none()
    if existing is not None:
        return existing
    sport = Sport(key="soccer_spain_la_liga", name="La Liga", group="Soccer")
    session.add(sport)
    await session.flush()
    return sport


def _kalshi_entry(value, market_id):
    """The stored blend entry at its production shape, attribution included.

    `eligibility.market_id` is what makes "is this the speaker we just silenced?"
    a fact on the row rather than an inference, so the fixture carries it rather
    than a bare value.
    """
    return {
        "value": value,
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "eligibility": {
            "v": 1,
            "rule": "live_blend.admissible_as_blend_speaker@5031",
            "scope": "full_event_winner",
            "status": "verified",
            "market_id": market_id,
            "source_market_id": _SEVILLA_TICKER,
        },
    }


async def _seed_pre_kickoff_event(session, *, external_id="sevvcf"):
    from app.models.models import Event

    sport = await _seed_sport(session)
    event = Event(
        sport_id=sport.id,
        external_id=f"test-{external_id}",
        home_team_name="Sevilla",
        away_team_name="Valencia",
        commence_time=datetime.now(timezone.utc) + timedelta(hours=18),
        status="scheduled",
        opening_home_probability=_SEVILLA_OPENING,
    )
    session.add(event)
    await session.flush()
    return event


async def _seed_kalshi_market(session, event, *, ticker, probabilities, tier=1):
    """A linked Kalshi market the sweep's value arm selects, with priced legs."""
    from app.models.models import FuturesMarket, FuturesOutcome

    market = FuturesMarket(
        source="kalshi",
        external_id=ticker,
        name="Sevilla vs Valencia: Winner",
        category="sports",
        market_tier=tier,
        volume=250_000,
        status="open",
        event_id=event.id,
        resolution_date=datetime.now(timezone.utc) + timedelta(days=2),
    )
    session.add(market)
    await session.flush()
    for name, prob in probabilities.items():
        session.add(
            FuturesOutcome(
                market_id=market.id,
                external_id=f"{ticker}-{name}",
                name=name,
                is_winner=False,
                current_probability=prob,
            )
        )
    await session.flush()
    return market


def _served_hero(event):
    """The number the event page prints, through the route's own two steps."""
    from app.utils.aggregation import compute_aggregate_probability
    from app.utils.graded_card import rendered_duel_percents

    prob = compute_aggregate_probability(event, event.status)
    if prob is None:
        return None, None
    # `opening_home_probability` is `Numeric`, so the tier-3 fallback hands back
    # a `Decimal` and `1.0 - Decimal` raises. The route reaches the same value
    # through a float payload; coerce here rather than assert around it.
    prob = float(prob)
    _away_pct, home_pct = rendered_duel_percents(round(1.0 - prob, 6), prob)
    return prob, home_pct


async def _drive_the_real_task(monkeypatch, session, verdicts, *, fetch=None):
    """Run `_refresh_stale_futures_prices` for real against `session`.

    Only the VENUE is faked — `verdicts` maps a ticker to what Kalshi answers —
    so the selector, both withdrawal statements, the transaction boundary and
    the stats all belong to the task. Everything patched below is I/O this test
    has no business reaching (Redis attempt-skips, the served-signal cache, the
    Polymarket client, the tournament register).
    """
    import contextlib

    from app.tasks import futures_price_refresh as fpr
    from app.utils.feed_served_markets import SERVED_UNAVAILABLE, ServedSignal

    @contextlib.asynccontextmanager
    async def _fake_session(**_kw):
        yield session

    class _Svc:
        async def close(self):
            return None

    monkeypatch.setenv("KALSHI_API_KEY", "test-key")
    monkeypatch.setattr("app.tasks.base.get_task_session", _fake_session)
    monkeypatch.setattr(
        "app.utils.tournament_register.registered_market_ids", lambda: set()
    )
    monkeypatch.setattr(
        "app.utils.feed_served_markets.served_signal",
        lambda: ServedSignal(state=SERVED_UNAVAILABLE, ids=[]),
    )
    monkeypatch.setattr(
        "app.utils.feed_served_markets.note_served_signal_healthy", lambda *a, **k: None
    )
    monkeypatch.setattr(fpr, "_load_attempt_skips", lambda ids: set())
    monkeypatch.setattr(fpr, "_mark_attempted", lambda ids, ttl_seconds: None)
    monkeypatch.setattr(fpr, "_load_label_attempt_skips", lambda ids: set())  # #9543
    monkeypatch.setattr(fpr, "_mark_label_attempted", lambda ids: None)
    monkeypatch.setattr(
        "app.services.polymarket_api.PolymarketAPIService", lambda: _Svc()
    )
    monkeypatch.setattr("app.services.kalshi_api.KalshiAPIService", lambda: _Svc())

    async def _fetch(_service, external_id, **_kw):
        return verdicts.get(external_id)

    monkeypatch.setattr(fpr, "_fetch_kalshi_prices", fetch or _fetch)
    return await fpr._refresh_stale_futures_prices()


class TestTheVenueAnsweredAndThePageHasToStopSayingNinetyNine:
    async def test_venue_answered_pre_kickoff_clears_the_served_hero_5771(
        self, db, monkeypatch
    ):
        """CERT-2772's required test. The number a reader sees, before and after.

        The BEFORE assertion is not decoration: it is the whole reason the
        repair exists. If the seeded row does not serve 99% through the real
        resolver, this test cannot observe the defect and its AFTER would pass
        on the broken code.
        """
        from sqlalchemy import select, text

        from app.models.models import Event

        event = await _seed_pre_kickoff_event(db)
        market = await _seed_kalshi_market(
            db,
            event,
            ticker=_SEVILLA_TICKER,
            probabilities={"Sevilla": _SEVILLA_HERO, "Draw": 0.01, "Valencia": 0.01},
        )
        event.win_probability_sources = {
            "kalshi": _kalshi_entry(_SEVILLA_HERO, market.id),
            "betting_book_count": 2,
        }
        await db.commit()

        # Ids are read BEFORE the run: `db.expire_all()` below expires every
        # loaded instance, and touching `event.id` after that fires a SYNC lazy
        # load inside an async session (`MissingGreenlet`) — the attribute read
        # looks free and is a query.
        event_id, market_id = event.id, market.id

        before_prob, before_pct = _served_hero(event)
        assert before_pct == 99, (
            f"the seed does not reproduce the defect (served {before_pct}%), so "
            "the assertion after the run would pass on the broken code"
        )

        from app.tasks import futures_price_refresh as fpr

        stats = await _drive_the_real_task(
            monkeypatch, db, {_SEVILLA_TICKER: fpr.VENUE_SETTLED}
        )

        db.expire_all()
        after = (
            await db.execute(select(Event).where(Event.id == event_id))
        ).scalar_one()
        after_prob, after_pct = _served_hero(after)

        assert "kalshi" not in (after.win_probability_sources or {}), (
            "the settled speaker is still in the blend, so the hero is still "
            "quoting a contest that has not kicked off — CERT-2772 exactly"
        )
        assert after_pct != 99, f"the page still prints {after_pct}%"
        assert after_prob == pytest.approx(_SEVILLA_OPENING, abs=1e-3), (
            "the hero should fall to the sources still speaking — here the "
            f"opening line — and instead reads {after_prob}"
        )
        # The other keys are not collateral. `betting_book_count` is metadata the
        # card prints beside the number and has nothing to do with Kalshi.
        assert (after.win_probability_sources or {}).get("betting_book_count") == 2

        # ...and the first half still holds on the same rows.
        priced = (
            await db.execute(
                text(
                    "SELECT COUNT(*) FROM futures_outcomes "
                    "WHERE market_id = :mid AND current_probability IS NOT NULL"
                ),
                {"mid": market_id},
            )
        ).scalar()
        assert priced == 0
        assert stats["pre_kickoff_quotes_withdrawn"] == 3
        assert stats["pre_kickoff_heroes_cleared"] == 1

    async def test_a_different_valid_kalshi_speaker_is_preserved_5771(
        self, db, monkeypatch
    ):
        """The control the required repair names, and it is the risk here.

        One event, two linked Kalshi markets: the one the venue answered, and a
        second still quoting. The blend entry names the second. Silencing the
        first must not take the second's number off the page — a repair that
        blanks the key whenever any Kalshi market settles would empty the hero
        on every multi-market event.
        """
        from sqlalchemy import select

        from app.models.models import Event
        from app.tasks import futures_price_refresh as fpr

        event = await _seed_pre_kickoff_event(db, external_id="two-speakers")
        settled = await _seed_kalshi_market(
            db,
            event,
            ticker=_SEVILLA_TICKER,
            probabilities={"Sevilla": _SEVILLA_HERO, "Valencia": 0.01},
        )
        live = await _seed_kalshi_market(
            db,
            event,
            ticker=f"{_SEVILLA_TICKER}-ALT",
            probabilities={"Sevilla": 0.44, "Valencia": 0.56},
        )
        event.win_probability_sources = {"kalshi": _kalshi_entry(0.44, live.id)}
        await db.commit()
        event_id, settled_id, live_id = event.id, settled.id, live.id

        stats = await _drive_the_real_task(
            monkeypatch,
            db,
            {
                _SEVILLA_TICKER: fpr.VENUE_SETTLED,
                f"{_SEVILLA_TICKER}-ALT": [
                    {
                        "external_id": f"{_SEVILLA_TICKER}-ALT-Sevilla",
                        "probability": 0.44,
                        "yes_bid": 0.43,
                        "yes_ask": 0.45,
                        "last_price": 0.44,
                    }
                ],
            },
        )

        db.expire_all()
        after = (
            await db.execute(select(Event).where(Event.id == event_id))
        ).scalar_one()
        wps = after.win_probability_sources or {}
        assert "kalshi" in wps, (
            "the live market's own reading was deleted because a DIFFERENT "
            "market on the same event settled"
        )
        assert wps["kalshi"]["value"] == 0.44
        assert stats["pre_kickoff_heroes_cleared"] == 0
        # The settled market's legs are still withdrawn — the control is about
        # the blend key, not about pricing a settled book.
        assert stats["pre_kickoff_quotes_withdrawn"] == 2
        assert settled_id != live_id

    async def test_a_finished_contest_keeps_its_terminal_number_5771(
        self, db, monkeypatch
    ):
        """Settled means settled, and this is the half that could do harm.

        A contest that HAS happened should carry its terminal Kalshi number —
        that is the result the hero and the card are built to show. The scope is
        the event's own clock, so this must be inert on a completed event even
        though the venue says exactly the same thing about the market.
        """
        from sqlalchemy import select

        from app.models.models import Event
        from app.tasks import futures_price_refresh as fpr

        event = await _seed_pre_kickoff_event(db, external_id="already-played")
        market = await _seed_kalshi_market(
            db,
            event,
            ticker=f"{_SEVILLA_TICKER}-DONE",
            probabilities={"Sevilla": _SEVILLA_HERO, "Valencia": 0.01},
        )
        event.status = "completed"
        event.commence_time = datetime.now(timezone.utc) - timedelta(hours=4)
        event.win_probability_sources = {
            "kalshi": _kalshi_entry(_SEVILLA_HERO, market.id)
        }
        await db.commit()
        event_id = event.id

        stats = await _drive_the_real_task(
            monkeypatch, db, {f"{_SEVILLA_TICKER}-DONE": fpr.VENUE_SETTLED}
        )

        db.expire_all()
        after = (
            await db.execute(select(Event).where(Event.id == event_id))
        ).scalar_one()
        assert (after.win_probability_sources or {}).get("kalshi", {}).get(
            "value"
        ) == _SEVILLA_HERO, "a finished game lost the result it is meant to show"
        assert stats["pre_kickoff_heroes_cleared"] == 0
        assert stats["pre_kickoff_quotes_withdrawn"] == 0

    async def test_the_pre_attribution_shape_is_cleared_by_the_survivor_arm_5771(
        self, db, monkeypatch
    ):
        """The entries written before attribution existed have no `market_id`.

        Arm 1 cannot read them, so they reach arm 2 — and arm 2's question is
        the only safe one available: does ANY Kalshi market on this event still
        hold a readable price? Here none does, so the key goes. Without this
        test the survivor arm could be deleted and every legacy entry would stay
        frozen on the page.
        """
        from sqlalchemy import select

        from app.models.models import Event
        from app.tasks import futures_price_refresh as fpr

        event = await _seed_pre_kickoff_event(db, external_id="legacy-entry")
        await _seed_kalshi_market(
            db,
            event,
            ticker=f"{_SEVILLA_TICKER}-LEGACY",
            probabilities={"Sevilla": _SEVILLA_HERO, "Valencia": 0.01},
        )
        # The pre-#5031 shape: a bare value, no eligibility block at all.
        event.win_probability_sources = {
            "kalshi": {
                "value": _SEVILLA_HERO,
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }
        }
        await db.commit()
        event_id = event.id

        stats = await _drive_the_real_task(
            monkeypatch, db, {f"{_SEVILLA_TICKER}-LEGACY": fpr.VENUE_SETTLED}
        )

        db.expire_all()
        after = (
            await db.execute(select(Event).where(Event.id == event_id))
        ).scalar_one()
        assert "kalshi" not in (after.win_probability_sources or {})
        assert stats["pre_kickoff_heroes_cleared"] == 1


# ---------------------------------------------------------------------------
# #6536 — the delta this writer invalidates is cleared in the same UPDATE.
# ---------------------------------------------------------------------------


async def _seed_outcome_with_delta(
    session,
    *,
    external_id,
    current_probability,
    probability_change_24h,
):
    """One open market + one outcome carrying a stored price AND a stored delta.

    Separate from `_seed_market` on purpose: every other case in this file is
    indifferent to `probability_change_24h`, and the whole subject here is the
    relationship between that column and the price written over it.
    """
    from app.models.models import FuturesMarket, FuturesOutcome

    market = FuturesMarket(
        source=_BOOKMAKER,
        external_id=f"KXDELTA-{external_id}",
        name=f"Delta case {external_id}",
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
        is_winner=False,
        current_probability=current_probability,
        probability_change_24h=probability_change_24h,
    )
    session.add(outcome)
    await session.flush()
    return market, outcome


async def _read_delta(session, outcome_id):
    from sqlalchemy import text

    value = (
        await session.execute(
            text(
                "SELECT probability_change_24h FROM futures_outcomes WHERE id = :oid"
            ),
            {"oid": outcome_id},
        )
    ).scalar()
    return None if value is None else float(value)


class TestTheWriterClearsTheDeltaItInvalidates:
    """#6536 — this task writes the price and used to leave the delta standing.

    `probability_change_24h` is `new - previous`, so `current_probability -
    probability_change_24h` is the previous price. When this writer moves the
    price and the delta stays, that subtraction stops naming a price any venue
    quoted, and the reader meets it as a movement chip: measured on production
    2026-09-16, an outcome sitting at 8% on Discover page one wearing a green
    "up 80 points".

    Real Postgres because the guard is a SQL `CASE` evaluated against the row's
    own stored columns. A recording double reports the expression it was handed,
    which is the assertion restated, not the behaviour.
    """

    async def test_the_impossible_pair_is_never_stored(self, db):
        """THE ship. New price 0.08 against a stored +0.80 implies a prior of -0.72.

        This is the production specimen's exact arithmetic (outcome 227786168,
        "Vinted", #1 Free App in the US App Store).
        """
        from app.tasks.futures_price_refresh import _write_prices

        market, outcome = await _seed_outcome_with_delta(
            db,
            external_id="VINTED",
            current_probability=0.88,
            probability_change_24h=0.80,
        )

        written = await _write_prices(
            db,
            market.id,
            _BOOKMAKER,
            _priced(external_id="VINTED", probability=0.08),
            _stats(),
        )
        await db.commit()

        assert written == 1, "the row was not written at all, so nothing is proved"
        assert await _read_delta(db, outcome.id) is None, (
            "the price moved to 0.08 under a +0.80 delta, which implies a "
            "previous price of -0.72 — the pair refutes itself and the delta "
            "must not survive the write"
        )

    async def test_the_price_still_lands_when_the_delta_is_cleared(self, db):
        """The guard clears a delta; it must never cost the price write.

        Without this, a `CASE` that raised or mis-compiled could satisfy the
        test above by failing the whole UPDATE — the delta would read NULL
        because nothing was written, and the ship would be a regression.
        """
        from sqlalchemy import text
        from app.tasks.futures_price_refresh import _write_prices

        market, outcome = await _seed_outcome_with_delta(
            db,
            external_id="PRICELANDS",
            current_probability=0.88,
            probability_change_24h=0.80,
        )

        await _write_prices(
            db,
            market.id,
            _BOOKMAKER,
            _priced(external_id="PRICELANDS", probability=0.08),
            _stats(),
        )
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
        assert float(row[0]) == pytest.approx(0.08, abs=1e-6)
        assert row[1] is not None
        assert await _snapshot_count(db, outcome.id) == 1

    async def test_a_healthy_delta_survives_byte_for_byte(self, db):
        """THE CONTROL, and the one that decides the blast radius.

        0.30 written over a +0.05 delta implies a previous price of 0.25 — an
        ordinary move, and the chip is true. A guard that cleared this would be
        deleting real movement from the strip, which is the failure mode the
        issue explicitly refused ("no blanket removal of all movement").
        """
        from app.tasks.futures_price_refresh import _write_prices

        market, outcome = await _seed_outcome_with_delta(
            db,
            external_id="HEALTHY",
            current_probability=0.25,
            probability_change_24h=0.05,
        )

        await _write_prices(
            db,
            market.id,
            _BOOKMAKER,
            _priced(external_id="HEALTHY", probability=0.30),
            _stats(),
        )
        await db.commit()

        assert await _read_delta(db, outcome.id) == pytest.approx(0.05, abs=1e-9), (
            "a delta whose implied prior is a real probability describes real "
            "movement and must be left exactly as it was"
        )

    async def test_the_boundaries_are_kept_not_cleared(self, db):
        """Exactly 0 and exactly 1 are PRICES, so the invariant is inclusive.

        The predicate is `< 0 or > 1`. Written as `<= 0 or >= 1` it would clear
        a delta describing a move off a 0% or 100% quote — both of which venues
        publish — so the two boundary rows are seeded as the negative control
        that tells those two predicates apart.
        """
        from app.tasks.futures_price_refresh import _write_prices

        # prior exactly 0.0: 0.20 written over a +0.20 delta.
        market_lo, outcome_lo = await _seed_outcome_with_delta(
            db,
            external_id="PRIORZERO",
            current_probability=0.10,
            probability_change_24h=0.20,
        )
        # prior exactly 1.0: 0.40 written over a -0.60 delta.
        market_hi, outcome_hi = await _seed_outcome_with_delta(
            db,
            external_id="PRIORONE",
            current_probability=0.50,
            probability_change_24h=-0.60,
        )

        await _write_prices(
            db,
            market_lo.id,
            _BOOKMAKER,
            _priced(external_id="PRIORZERO", probability=0.20),
            _stats(),
        )
        await _write_prices(
            db,
            market_hi.id,
            _BOOKMAKER,
            _priced(external_id="PRIORONE", probability=0.40),
            _stats(),
        )
        await db.commit()

        assert await _read_delta(db, outcome_lo.id) == pytest.approx(0.20, abs=1e-9), (
            "an implied prior of exactly 0.0 is a price, not an impossibility"
        )
        assert await _read_delta(db, outcome_hi.id) == pytest.approx(-0.60, abs=1e-9), (
            "an implied prior of exactly 1.0 is a price, not an impossibility"
        )

    async def test_a_null_delta_stays_null(self, db):
        """`NULL - x` is NULL, so the CASE must fall through rather than fabricate.

        The `else_` arm re-selects the column, so a row with no delta keeps
        having no delta. An `else_` of `0` would invent a "no movement" claim on
        every row this task touches.
        """
        from app.tasks.futures_price_refresh import _write_prices

        market, outcome = await _seed_outcome_with_delta(
            db,
            external_id="NODELTA",
            current_probability=0.40,
            probability_change_24h=None,
        )

        await _write_prices(
            db,
            market.id,
            _BOOKMAKER,
            _priced(external_id="NODELTA", probability=0.45),
            _stats(),
        )
        await db.commit()

        assert await _read_delta(db, outcome.id) is None


# --- CERT-3515: the in-play arm keeps a market past its stored date ----------


async def _seed_in_play(
    session,
    *,
    ticker,
    resolved_hours_ago,
    status="open",
    winner=False,
    venue_settled=False,
):
    """A tier-1 Kalshi outright, stale (no snapshot), resolving relative to NOW.

    Relative seeding IS the frozen clock here: Postgres reads NOW() for real, so
    "Sunday 23:00Z against a stored 14:00Z" is `resolved_hours_ago=9`.
    """
    from app.models.models import FuturesMarket, FuturesOutcome
    from app.utils.futures_liveness import VENUE_SETTLED_KEY

    now = datetime.now(timezone.utc)
    metadata = {}
    if venue_settled:
        # An UNCONFIRMED stamp (1h old, inside the 48h confirm window): the
        # shared contract still calls this row live, the grace must not.
        metadata[VENUE_SETTLED_KEY] = (now - timedelta(hours=1)).strftime(
            "%Y-%m-%dT%H:%M:%S"
        )
    market = FuturesMarket(
        source=_BOOKMAKER,
        external_id=ticker,
        name=f"{ticker} winner",
        category="championship",
        market_tier=1,
        status=status,
        resolution_date=now - timedelta(hours=resolved_hours_ago),
        market_metadata=metadata,
    )
    session.add(market)
    await session.flush()
    for leg, won in (("USA", winner), ("WORLD", False)):
        session.add(
            FuturesOutcome(
                market_id=market.id,
                external_id=f"{ticker}-{leg}",
                name=leg,
                is_winner=won,
            )
        )
    await session.flush()
    return market.id


class TestTheInPlayArmOutlivesAnExpectedExpirationDate:
    """CERT-3515. `KXPRESCUP-26` stores 2026-09-27 14:00Z — Kalshi's EXPECTED
    expiration; `close_time` is 2026-10-11 — and Sunday's singles run past it.
    The arm must still select it after 14:00Z, and must not resurrect a market
    that is settled, closed, or beyond the grace.
    """

    async def test_after_the_stored_date_it_is_still_selected_and_the_controls_are_not(
        self, db
    ):
        from app.tasks import futures_price_refresh as fpr

        ids = {
            "sunday_2300z": await _seed_in_play(
                db, ticker="KXPRESCUP-26", resolved_hours_ago=9
            ),
            "saturday_future": await _seed_in_play(
                db, ticker="KXFUTURE-26", resolved_hours_ago=-20
            ),
            "has_winner": await _seed_in_play(
                db, ticker="KXWON-26", resolved_hours_ago=9, winner=True
            ),
            "venue_settled": await _seed_in_play(
                db, ticker="KXSTAMP-26", resolved_hours_ago=9, venue_settled=True
            ),
            "beyond_grace": await _seed_in_play(
                db,
                ticker="KXOLD-26",
                resolved_hours_ago=fpr.IN_PLAY_GRACE_HOURS + 4,
            ),
            "resolved_status": await _seed_in_play(
                db, ticker="KXDONE-26", resolved_hours_ago=9, status="resolved"
            ),
        }
        await db.commit()

        out = await fpr._scan_in_play_candidates(
            db, stale_minutes=fpr.IN_PLAY_REFRESH_MINUTES
        )
        selected = {m["id"] for m in out}

        assert ids["sunday_2300z"] in selected, (
            "the Presidents Cup falls out of the in-play arm the moment its stored "
            "expected-expiration passes — CERT-3515's block"
        )
        assert ids["saturday_future"] in selected, "the pre-date arm regressed"
        for control in ("has_winner", "venue_settled", "beyond_grace", "resolved_status"):
            assert ids[control] not in selected, f"the grace resurrected {control}"
        assert all(m["arm"] == fpr._ARM_IN_PLAY for m in out)


class TestTheWindowWriteOnPostgres8871:
    """#8871 — `_KALSHI_WINDOW_WRITE_SQL` on real Postgres through asyncpg.

    The SQLite arm in `test_futures_price_refresh_carries_window_8871.py` proves
    the fences on rows; this one proves the statement itself binds here — a
    `timestamptz` bound twice (SET and `IS DISTINCT FROM`) and once inside a
    `COALESCE` — which only the real driver can answer.
    """

    async def test_the_backstop_row_moves_and_nothing_else_does(self, db):
        from sqlalchemy import text

        from app.models.models import FuturesMarket
        from app.tasks import futures_price_refresh as fpr

        backstop = datetime(2027, 11, 3, 15, tzinfo=timezone.utc)
        expected = datetime(2027, 1, 4, 15, tzinfo=timezone.utc)
        real_close = datetime(2027, 2, 1, tzinfo=timezone.utc)

        def _m(ext, status, rd):
            return FuturesMarket(
                source=_BOOKMAKER,
                external_id=ext,
                name=ext,
                category="futures",
                market_tier=1,
                status=status,
                resolution_date=rd,
                expiration_time=backstop,
            )

        specimen = _m("SENATEME-26", "open", backstop)
        closed = _m("KXREALCLOSE-27", "open", real_close)
        resolved = _m("SENATEOLD-26", "resolved", backstop)
        db.add_all([specimen, closed, resolved])
        await db.flush()

        async def _write(mid, exp=backstop):
            return (
                await db.execute(
                    fpr._KALSHI_WINDOW_WRITE_SQL,
                    {"mid": mid, "resolution_date": expected, "expiration_time": exp},
                )
            ).rowcount

        assert await _write(specimen.id) == 1
        assert await _write(specimen.id) == 0  # already there: zero writes
        assert await _write(closed.id) == 0
        assert await _write(resolved.id) == 0
        await db.commit()

        rows = dict(
            (
                await db.execute(
                    text(
                        "SELECT external_id, resolution_date FROM futures_markets"
                    )
                )
            ).fetchall()
        )
        assert rows == {
            "SENATEME-26": expected,
            "KXREALCLOSE-27": real_close,
            "SENATEOLD-26": backstop,
        }

    async def test_a_missing_expiration_keeps_the_backstop(self, db):
        from sqlalchemy import text

        from app.models.models import FuturesMarket
        from app.tasks import futures_price_refresh as fpr

        backstop = datetime(2027, 11, 3, 15, tzinfo=timezone.utc)
        m = FuturesMarket(
            source=_BOOKMAKER,
            external_id="SENATETX-26",
            name="Texas Senate winner?",
            category="futures",
            market_tier=1,
            status="open",
            resolution_date=backstop,
            expiration_time=backstop,
        )
        db.add(m)
        await db.flush()
        n = (
            await db.execute(
                fpr._KALSHI_WINDOW_WRITE_SQL,
                {
                    "mid": m.id,
                    "resolution_date": datetime(2027, 1, 4, 15, tzinfo=timezone.utc),
                    "expiration_time": None,
                },
            )
        ).rowcount
        assert n == 1
        exp = (
            await db.execute(
                text("SELECT expiration_time FROM futures_markets WHERE id = :i"),
                {"i": m.id},
            )
        ).scalar()
        assert exp == backstop


# ── #4983 — A CONDITION PRICED ON ONE ROW IS PRICED ON EVERY ROW THAT CARRIES IT ──
#
# Reader-visible 2026-09-27 03:30Z, `/search?q=dodgers`: one venue question
# printed twice on the same page — the parent ladder's Dodgers leg (bare
# condition `0x298b…`, written by this task's :50 beat) at 71%, the standalone
# sub-market row for the SAME condition (`<cid>_yes` / `<cid>_no`) at 49.5% from
# the day before. `_write_prices` is market-scoped, so the addressed row moved and
# its twin did not. Seeded here exactly as `_process_event_batch` stores a Gamma
# event: one parent keyed on the event id, one sub-market keyed on the condition.

_TWIN_EVENT = "425048"
_CID_DODGERS = "0x" + "298b" * 16
_CID_YANKEES = "0x" + "a1a1" * 16


async def _seed_gamma_event_twins(session, *, twin_status="open", twin_graded=False):
    from app.models.models import FuturesMarket, FuturesOutcome

    future = datetime.now(timezone.utc) + timedelta(days=30)
    stale = datetime.now(timezone.utc) - timedelta(hours=18)
    parent = FuturesMarket(
        source="polymarket",
        external_id=_TWIN_EVENT,
        name="MLB: Team to win 100+ games",
        category="futures",
        status="open",
        resolution_date=future,
        group_id=f"polymarket:{_TWIN_EVENT}",
        market_metadata={"polymarket_event_id": _TWIN_EVENT},
    )
    twin = FuturesMarket(
        source="polymarket",
        external_id=_CID_DODGERS,
        name="Will the Los Angeles Dodgers win 100 or more games?",
        category="futures",
        status=twin_status,
        resolution_date=future,
        group_id=f"polymarket:{_TWIN_EVENT}",
        market_metadata={"polymarket_event_id": _TWIN_EVENT},
    )
    unrelated = FuturesMarket(
        source="polymarket",
        external_id="0x" + "dead" * 16,
        name="Will the Dodgers win the World Series?",
        category="futures",
        status="open",
        resolution_date=future,
    )
    session.add_all([parent, twin, unrelated])
    await session.flush()

    def _leg(market, ext, name, p):
        return FuturesOutcome(
            market_id=market.id,
            external_id=ext,
            name=name,
            is_winner=False,
            current_probability=p,
            last_updated=stale,
        )

    legs = {
        "parent_dodgers": _leg(parent, _CID_DODGERS, "Los Angeles Dodgers", 0.52),
        "parent_yankees": _leg(parent, _CID_YANKEES, "New York Yankees", 0.10),
        "twin_yes": _leg(twin, f"{_CID_DODGERS}_yes", "Yes", 0.495),
        "twin_no": _leg(twin, f"{_CID_DODGERS}_no", "No", 0.505),
        "unrelated_yes": _leg(unrelated, "0x" + "dead" * 16 + "_yes", "Yes", 0.20),
    }
    if twin_graded:
        legs["twin_yes"].resolution_source = "api_settlement"
        legs["twin_no"].resolution_source = "api_settlement"
    session.add_all(legs.values())
    await session.flush()
    return parent, twin, unrelated, legs


def _event_priced():
    """The two items `_fetch_polymarket_prices` builds for the Gamma event."""

    def _item(cid, p, bid, ask):
        return {
            "external_id": cid,
            "probability": p,
            "yes_bid": bid,
            "yes_ask": ask,
            "last_price": p,
            "no": {
                "probability": 1.0 - p,
                "yes_bid": 1.0 - ask,
                "yes_ask": 1.0 - bid,
                "last_price": 1.0 - p,
            },
        }

    return [_item(_CID_DODGERS, 0.71, 0.69, 0.73), _item(_CID_YANKEES, 0.12, 0.11, 0.13)]


async def _prob(session, outcome_id):
    from sqlalchemy import text

    return float(
        (
            await session.execute(
                text("SELECT current_probability FROM futures_outcomes WHERE id = :i"),
                {"i": outcome_id},
            )
        ).scalar()
    )


class TestAConditionTwinIsPricedWithItsSibling:
    async def test_the_addressed_write_alone_leaves_the_twin_stale(self, db):
        """THE STRAWMAN — the defect as production had it. Without this the
        assertions below would also pass on a writer that already reached twins."""
        from app.tasks.futures_price_refresh import _write_prices

        parent, _twin, _u, legs = await _seed_gamma_event_twins(db)
        stats = {"unknown_outcomes": 0}
        await _write_prices(db, parent.id, "polymarket", _event_priced(), stats)
        await db.commit()

        assert await _prob(db, legs["parent_dodgers"].id) == pytest.approx(0.71)
        assert await _prob(db, legs["twin_yes"].id) == pytest.approx(0.495)

    async def test_the_twin_reads_the_same_number_as_its_sibling(self, db):
        from app.tasks.futures_price_refresh import (
            _write_condition_twins,
            _write_prices,
        )

        parent, twin, _u, legs = await _seed_gamma_event_twins(db)
        stats = {"unknown_outcomes": 0, "errors": []}
        priced = _event_priced()
        await _write_prices(db, parent.id, "polymarket", priced, stats)
        await db.commit()
        await _write_condition_twins(db, priced, [parent.id], stats)

        assert stats["errors"] == []
        assert await _prob(db, legs["twin_yes"].id) == pytest.approx(0.71)
        assert await _prob(db, legs["twin_no"].id) == pytest.approx(0.29)
        assert await _snapshot_count(db, legs["twin_yes"].id) == 1
        assert await _snapshot_count(db, legs["twin_no"].id) == 1
        assert stats["twin_markets_priced"] == 1
        assert stats["twin_snapshots_written"] == 2
        # Handed only its own condition: the Yankees item is not billed as an
        # outcome the twin failed to place.
        assert stats["unknown_outcomes"] == 0

    async def test_the_addressed_row_is_not_written_twice(self, db):
        from app.tasks.futures_price_refresh import (
            _write_condition_twins,
            _write_prices,
        )

        parent, _twin, _u, legs = await _seed_gamma_event_twins(db)
        stats = {"unknown_outcomes": 0, "errors": []}
        priced = _event_priced()
        await _write_prices(db, parent.id, "polymarket", priced, stats)
        await db.commit()
        await _write_condition_twins(db, priced, [parent.id], stats)

        assert await _snapshot_count(db, legs["parent_dodgers"].id) == 1
        assert await _snapshot_count(db, legs["parent_yankees"].id) == 1

    async def test_a_row_carrying_no_priced_condition_is_untouched(self, db):
        from app.tasks.futures_price_refresh import _write_condition_twins

        parent, _twin, _u, legs = await _seed_gamma_event_twins(db)
        stats = {"unknown_outcomes": 0, "errors": []}
        await _write_condition_twins(db, _event_priced(), [parent.id], stats)

        assert await _prob(db, legs["unrelated_yes"].id) == pytest.approx(0.20)
        assert await _snapshot_count(db, legs["unrelated_yes"].id) == 0

    async def test_a_settled_twin_market_is_not_repriced(self, db):
        from app.tasks.futures_price_refresh import _write_condition_twins

        parent, _twin, _u, legs = await _seed_gamma_event_twins(db, twin_status="resolved")
        stats = {"unknown_outcomes": 0, "errors": []}
        await _write_condition_twins(db, _event_priced(), [parent.id], stats)

        assert await _prob(db, legs["twin_yes"].id) == pytest.approx(0.495)
        assert stats.get("twin_markets_priced", 0) == 0

    async def test_a_graded_twin_leg_is_not_repriced(self, db):
        from app.tasks.futures_price_refresh import _write_condition_twins

        parent, _twin, _u, legs = await _seed_gamma_event_twins(db, twin_graded=True)
        stats = {"unknown_outcomes": 0, "errors": []}
        await _write_condition_twins(db, _event_priced(), [parent.id], stats)

        assert await _prob(db, legs["twin_yes"].id) == pytest.approx(0.495)
        assert await _snapshot_count(db, legs["twin_yes"].id) == 0

    async def test_the_reach_is_symmetric_a_sub_market_write_reaches_the_ladder(self, db):
        """The same lookup from the other side: when the addressed row is the
        sub-market, the parent ladder's bare leg is the twin."""
        from app.tasks.futures_price_refresh import (
            _write_condition_twins,
            _write_prices,
        )

        _parent, twin, _u, legs = await _seed_gamma_event_twins(db)
        stats = {"unknown_outcomes": 0, "errors": []}
        priced = _event_priced()
        await _write_prices(db, twin.id, "polymarket", priced, stats)
        await db.commit()
        await _write_condition_twins(db, priced, [twin.id], stats)

        assert await _prob(db, legs["parent_dodgers"].id) == pytest.approx(0.71)
        assert await _prob(db, legs["parent_yankees"].id) == pytest.approx(0.12)


# ── #9543 — THE THRESHOLD LABEL, MERGED INTO JSONB ON REAL POSTGRES ──────────


class TestTheThresholdLabelWriteOnPostgres9543:
    """#9543 — `_KALSHI_THRESHOLD_LABEL_WRITE_SQL` on real Postgres via asyncpg.

    The unit file pins the statement's shape; only Postgres can answer the
    JSONB half: `||` keeps every other key, `COALESCE` turns a NULL into the one
    key, the text bind survives twice, and a same-label rerun is zero writes.
    """

    async def test_the_label_merges_and_every_other_key_survives(self, db):
        from sqlalchemy import text

        from app.models.models import FuturesMarket
        from app.tasks import futures_price_refresh as fpr

        def _m(ext, meta, source=_BOOKMAKER):
            return FuturesMarket(
                source=source,
                external_id=ext,
                name=ext,
                category="futures",
                market_tier=2,
                status="open",
                market_metadata=meta,
            )

        poll_meta = {
            "kalshi_event_ticker": "KXCOWAGE-2027",
            "event_title": "Colombia minimum wage growth minus inflation in 2027",
        }
        specimen = _m("KXCOWAGE-2027", dict(poll_meta))
        null_meta = _m("KXPOKEMON-26SEPCELULTPR", None)  # ORM stores JSON null
        stale = _m("KXSTALE-27", {"threshold_label": "Above 3.00 pp", "x": 1})
        other = _m("0xpoly", {"a": 1}, source="polymarket")
        db.add_all([specimen, null_meta, stale, other])
        await db.flush()

        async def _write(mid, label):
            return (
                await db.execute(
                    fpr._KALSHI_THRESHOLD_LABEL_WRITE_SQL,
                    {"mid": mid, "label": label},
                )
            ).rowcount

        assert await _write(specimen.id, "Above 4.00 pp") == 1
        assert await _write(specimen.id, "Above 4.00 pp") == 0  # idempotent
        assert await _write(null_meta.id, "Above $1237.81") == 1
        assert await _write(stale.id, "Above 4.00 pp") == 1  # corrected
        assert await _write(other.id, "Above 4.00 pp") == 0  # Kalshi only
        await db.commit()

        rows = dict(
            (
                await db.execute(
                    text("SELECT external_id, market_metadata FROM futures_markets")
                )
            ).fetchall()
        )
        assert rows["KXCOWAGE-2027"] == {**poll_meta, "threshold_label": "Above 4.00 pp"}
        assert rows["KXPOKEMON-26SEPCELULTPR"] == {"threshold_label": "Above $1237.81"}
        assert rows["KXSTALE-27"] == {"threshold_label": "Above 4.00 pp", "x": 1}
        assert rows["0xpoly"] == {"a": 1}

        # SQL NULL, the other non-object shape, gains the one key too.
        await db.execute(
            text("UPDATE futures_markets SET market_metadata = NULL WHERE id = :i"),
            {"i": null_meta.id},
        )
        assert await _write(null_meta.id, "Above $1237.81") == 1
        got = (
            await db.execute(
                text("SELECT market_metadata FROM futures_markets WHERE id = :i"),
                {"i": null_meta.id},
            )
        ).scalar()
        assert got == {"threshold_label": "Above $1237.81"}


# ── #9543 / CERT-3817 — THE LABEL ARM, SELECTOR TO WRITE, ON REAL POSTGRES ────


async def _seed_one_yes(
    session,
    ticker,
    *,
    tier=2,
    volume=None,
    meta=None,
    status="open",
    source=_BOOKMAKER,
    extra_outcome=None,
):
    """A market stored the way the Kalshi poll stores a one-market event: one
    outcome named ``Yes`` (``_kalshi_outcome_name`` rule 1), no snapshot."""
    from app.models.models import FuturesMarket, FuturesOutcome

    market = FuturesMarket(
        source=source,
        external_id=ticker,
        name=ticker,
        category="futures",
        market_tier=tier,
        volume=volume,
        status=status,
        resolution_date=datetime.now(timezone.utc) + timedelta(days=30),
        market_metadata=meta,
    )
    session.add(market)
    await session.flush()
    for name in ["Yes"] + ([extra_outcome] if extra_outcome else []):
        session.add(
            FuturesOutcome(
                market_id=market.id,
                external_id=f"{ticker}-{name}",
                name=name,
                is_winner=False,
            )
        )
    await session.flush()
    return market.id


class TestTheLabelArmReachesTheBoardTheValueArmsCannot9543:
    """CERT-3817's required regression. `/futures/60481264` is tier 2 at volume
    5,170 — under the floor, off the register, off page one, not in play, not a
    series family — so before this arm the task never read it and it printed
    "Yes". Seeded as production stores it; only the venue is faked.
    """

    async def _seed(self, db):
        ids = {
            # the two #9543 specimens
            "pokemon": await _seed_one_yes(
                db, "KXPOKEMON-26SEPCELULTPR", volume=5_170, meta=None
            ),
            "cowage": await _seed_one_yes(
                db,
                "KXCOWAGE-2027",
                volume=4_000,
                meta={"kalshi_event_ticker": "KXCOWAGE-2027"},
            ),
            # selected, but the venue refuses: a plain binary and a failed read
            "plain": await _seed_one_yes(db, "KXINDUS-27JAN01", volume=900, meta={}),
            "unreadable": await _seed_one_yes(db, "KXGONE-27", volume=50, meta={}),
            # never selected
            "labelled": await _seed_one_yes(
                db, "KXDONE-27", meta={"threshold_label": "Above 3.00 pp"}
            ),
            "multi": await _seed_one_yes(db, "KXTWO-27", extra_outcome="No"),
            "resolved": await _seed_one_yes(db, "KXOVER-27", status="resolved"),
            "polymarket": await _seed_one_yes(db, "0xpolyyes", source="polymarket"),
        }
        await db.commit()
        return ids

    async def test_the_selector_admits_both_specimens_and_refuses_the_controls(
        self, db
    ):
        from app.tasks import futures_price_refresh as fpr

        ids = await self._seed(db)
        out = await fpr._scan_threshold_label_candidates(db)
        selected = [m["id"] for m in out]

        assert selected == sorted(
            [ids["pokemon"], ids["cowage"], ids["plain"], ids["unreadable"]]
        )
        assert all(m["arm"] == fpr._ARM_THRESHOLD_LABEL and m["priority"] for m in out)

    async def test_the_real_task_writes_both_labels_and_nothing_else(
        self, db, monkeypatch
    ):
        from sqlalchemy import text

        ids = await self._seed(db)
        labels_by_ticker = {
            "KXPOKEMON-26SEPCELULTPR": "Above $1237.81",
            "KXCOWAGE-2027": "Above 4.00 pp",
        }
        fetched: list[str] = []

        async def _venue(_service, external_id, *, windows=None, labels=None, **_kw):
            fetched.append(external_id)
            if external_id == "KXGONE-27":
                return None
            if labels is not None and external_id in labels_by_ticker:
                labels[external_id] = labels_by_ticker[external_id]
            return _priced(external_id=f"{external_id}-Yes", probability=0.41)

        before = dict(
            (
                await db.execute(text("SELECT id, market_metadata FROM futures_markets"))
            ).fetchall()
        )
        stats = await _drive_the_real_task(monkeypatch, db, {}, fetch=_venue)

        assert sorted(fetched) == sorted(
            ["KXPOKEMON-26SEPCELULTPR", "KXCOWAGE-2027", "KXINDUS-27JAN01", "KXGONE-27"]
        )
        assert stats["threshold_label_candidates"] == 4
        assert stats["threshold_labels_written"] == 2

        after = dict(
            (
                await db.execute(text("SELECT id, market_metadata FROM futures_markets"))
            ).fetchall()
        )
        assert after[ids["pokemon"]] == {"threshold_label": "Above $1237.81"}
        assert after[ids["cowage"]] == {
            "kalshi_event_ticker": "KXCOWAGE-2027",
            "threshold_label": "Above 4.00 pp",
        }
        for control in ("plain", "unreadable", "labelled", "multi", "resolved", "polymarket"):
            assert after[ids[control]] == before[ids[control]], control

        # And the next beat has nothing left to label on either specimen.
        from app.tasks import futures_price_refresh as fpr

        again = {m["id"] for m in await fpr._scan_threshold_label_candidates(db)}
        assert ids["pokemon"] not in again and ids["cowage"] not in again


# ══ #10090: the 30-second venue poll's population and write ═══════════════════
#
# Folded here from its own file (lane1 R1 on PR #11789): this file's
# search-recall step already runs under the all-skipped detector, and ci.yml has
# no room for another step. Two contracts no mock can observe:
#
# * WHO is polled — the population SQL renders the sockets' own predicates
#   (`kalshi_ws._kalshi_slate_event_window`, `polymarket_ws._slate_event_window`,
#   `kalshi_open_contract_stmt`) and the hand-off band, so only a real planner
#   running the real text says which rows it admits.
# * WHAT is written — `_write_prices` with a `PollWrite`: a changed leg moves and
#   gains a point, an unchanged one writes nothing, a row a newer writer touched
#   is left alone with no point, a move inside the history interval moves the row
#   and gains its point on a later pass, and a settled leg is never written.


@pytest.fixture
async def poll_db():
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    import app.models.models  # noqa: F401
    from app.services.database import Base

    # Only the tables this gate touches, with their foreign-key closure: the
    # whole schema carries indexes a local PG14 cannot build, and nothing here
    # reads them.
    wanted = {"sports", "events", "futures_markets", "futures_outcomes", "futures_odds_snapshots"}
    tables, frontier = set(), set(wanted)
    while frontier:
        name = frontier.pop()
        tables.add(name)
        for fk in Base.metadata.tables[name].foreign_keys:
            if fk.column.table.name not in tables:
                frontier.add(fk.column.table.name)
    subset = [t for t in Base.metadata.sorted_tables if t.name in tables]

    engine = create_async_engine(DB_URL)
    async with engine.begin() as conn:
        # Drop the WHOLE schema first: the full-schema `db` fixture above leaves
        # tables that reference this subset, and a subset drop would refuse.
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(lambda c: Base.metadata.create_all(c, tables=subset))
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as session:
        yield session
    await engine.dispose()


def _vp_now():
    """Read at each use: a module-level anchor is stale by however long the run
    has taken, and the hand-off band is only 660 s wide (a 12-minute run put
    the 5 h 55 m event outside it)."""
    return datetime.now(timezone.utc)


async def _vp_event(session, *, status="scheduled", starts_in=timedelta(days=2)):
    from sqlalchemy import text

    from app.models.models import Event, Sport

    sport = (
        await session.execute(text("SELECT id FROM sports WHERE key = 'nfl_test'"))
    ).scalar()
    if sport is None:
        row = Sport(key="nfl_test", name="NFL", group="American Football")
        session.add(row)
        await session.flush()
        sport = row.id
    event = Event(
        sport_id=sport,
        home_team_name="Home",
        away_team_name="Away",
        commence_time=_vp_now() + starts_in,
        status=status,
    )
    session.add(event)
    await session.flush()
    return event.id


async def _vp_market(
    session,
    *,
    source,
    ext,
    legs,
    event_id=None,
    tier=1,
    metadata=None,
    status="open",
):
    """``legs``: [(external_id, is_winner, resolution_source)]."""
    from sqlalchemy import text

    from app.models.models import FuturesMarket, FuturesOutcome

    market = FuturesMarket(
        source=source,
        external_id=ext,
        name=f"{ext} market",
        category="futures",
        market_tier=tier,
        status=status,
        event_id=event_id,
        resolution_date=_vp_now() + timedelta(days=30),
        market_metadata=metadata or {},
    )
    session.add(market)
    await session.flush()
    ids = {}
    for leg_ext, is_winner, source_of_grade in legs:
        outcome = FuturesOutcome(
            market_id=market.id,
            external_id=leg_ext,
            name=leg_ext,
            is_winner=is_winner,
            resolution_source=source_of_grade,
            current_probability=0.40,
            current_yes_bid=0.39,
            current_yes_ask=0.41,
        )
        session.add(outcome)
        await session.flush()
        if is_winner is None:
            # The column's server default is FALSE, so the ORM's None does not
            # reach the row; the open arm's NULL leg is written as a raw
            # INSERT writes it.
            await session.execute(
                text("UPDATE futures_outcomes SET is_winner = NULL WHERE id = :o"),
                {"o": outcome.id},
            )
        ids[leg_ext] = outcome.id
    return market.id, ids


async def _vp_population(session, venue, *, open_arm):
    from sqlalchemy import text

    from app.tasks import venue_poll_30s as v

    sql = v.kalshi_population_sql(open_arm) if venue == "kalshi" else v.polymarket_population_sql(open_arm)
    rows = (
        await session.execute(
            text(sql),
            v.population_binds([]),
        )
    ).fetchall()
    return {row[-1] for row in rows}


async def test_kalshi_population_is_shown_minus_both_socket_arms(poll_db):
    db = poll_db
    await _vp_market(
        db, source="kalshi", ext="KXFUT-1",
        legs=[("KXFUT-1-A", False, None), ("KXFUT-1-B", None, None),
              ("KXFUT-1-C", True, "api_settlement"), ("KXFUT-1-D", False, "api_settlement")],
    )
    await _vp_market(db, source="kalshi", ext="KXLOW-1", tier=4, legs=[("KXLOW-1-A", False, None)])
    in_window = await _vp_event(db, starts_in=timedelta(hours=2))
    in_band = await _vp_event(db, starts_in=timedelta(hours=5, minutes=55))
    far = await _vp_event(db, starts_in=timedelta(hours=30))
    live = await _vp_event(db, status="live", starts_in=timedelta(hours=-1))
    for eid, tag in ((in_window, "WIN"), (in_band, "BAND"), (far, "FAR"), (live, "LIVE")):
        await _vp_market(db, source="kalshi", ext=f"KXGAME-{tag}", event_id=eid, tier=5,
                      legs=[(f"KXGAME-{tag}-H", False, None)])
    await db.commit()

    polled = await _vp_population(db, "kalshi", open_arm=True)
    # The open arm streams the NULL leg; settled legs and low-value unlinked
    # markets are not polled; the game socket keeps its window but not the band.
    assert polled == {"KXFUT-1-A", "KXGAME-BAND-H", "KXGAME-FAR-H"}

    polled_arm_off = await _vp_population(db, "kalshi", open_arm=False)
    assert "KXFUT-1-B" in polled_arm_off
    assert "KXGAME-WIN-H" not in polled_arm_off and "KXGAME-LIVE-H" not in polled_arm_off


async def test_polymarket_population_drops_tokened_markets_only_while_the_open_arm_is_on(poll_db):
    db = poll_db
    await _vp_market(db, source="polymarket", ext="9001", legs=[("0xaaa", False, None)],
                  metadata={"polymarket_event_id": "9001"})
    await _vp_market(db, source="polymarket", ext="9002", legs=[("0xbbb", False, None)],
                  metadata={"polymarket_event_id": "9002", "clob_token_ids": '["1","2"]'})
    await _vp_market(db, source="polymarket", ext="9003", status="resolved",
                  legs=[("0xccc", False, None)], metadata={"polymarket_event_id": "9003"})
    await db.commit()

    assert await _vp_population(db, "polymarket", open_arm=True) == {"0xaaa"}
    assert await _vp_population(db, "polymarket", open_arm=False) == {"0xaaa", "0xbbb"}


async def _vp_poll(db, outcome_ids, *, fetched_at=None):
    from app.tasks.venue_poll_30s import PollWrite, load_state

    stored = await load_state(db, list(outcome_ids))
    return PollWrite(
        fetched_at=fetched_at or datetime.now(timezone.utc),
        now=datetime.now(timezone.utc),
        stored=stored,
        allowed=frozenset(outcome_ids),
    )


@pytest.fixture
def vp_deferred(monkeypatch):
    """The deferred-point set on an in-memory Redis; ``read`` like each pass does."""
    from app.tasks import venue_poll_30s as v
    from tests.test_venue_poll_30s_10090 import _FakeRedis

    fake = _FakeRedis()
    monkeypatch.setattr(v, "_redis", lambda: fake)
    _VP_PENDING.clear()
    return fake


async def _vp_row(db, outcome_id):
    from sqlalchemy import text

    return (
        await db.execute(
            text("SELECT current_probability, (SELECT count(*) FROM futures_odds_snapshots "
                 "WHERE outcome_id = :o) FROM futures_outcomes WHERE id = :o"),
            {"o": outcome_id},
        )
    ).one()


def _vp_points(ids=None):
    """What a pass reads of the deferred set before it writes, then saves after."""
    from app.tasks.venue_poll_30s import DeferredPoints

    points = DeferredPoints.read(ids or _VP_ALL_IDS)
    _VP_PENDING.append(points)
    return points


#: every outcome id a test may write; the fake set answers only for these
_VP_ALL_IDS = list(range(1, 2000))
_VP_PENDING: list = []


def _vp_save_points():
    while _VP_PENDING:
        _VP_PENDING.pop().save()


def _vp_item(ext, prob, bid, ask):
    return {"external_id": ext, "probability": prob, "yes_bid": bid, "yes_ask": ask,
            "last_price": prob}


async def test_a_changed_leg_moves_and_gains_a_point_an_unchanged_one_writes_nothing(poll_db, vp_deferred):
    db = poll_db
    from app.tasks.venue_poll_30s import write_market

    mid, ids = await _vp_market(db, source="kalshi", ext="KXW",
                             legs=[("KXW-A", False, None), ("KXW-B", False, None)])
    await db.commit()
    stats = {"unknown_outcomes": 0}
    poll = await _vp_poll(db, ids.values(), fetched_at=datetime.now(timezone.utc) + timedelta(seconds=5))
    await write_market(db, venue="kalshi", market_id=mid, poll=poll, stats=stats, deferred=_vp_points(),
                       priced=[_vp_item("KXW-A", 0.55, 0.54, 0.56), _vp_item("KXW-B", 0.40, 0.39, 0.41)])
    assert float((await _vp_row(db, ids["KXW-A"]))[0]) == pytest.approx(0.55)
    assert (await _vp_row(db, ids["KXW-A"]))[1] == 1
    assert (await _vp_row(db, ids["KXW-B"]))[1] == 0
    assert stats["rows_updated"] == 1 and stats["legs_unchanged"] == 1


async def test_a_row_a_newer_writer_touched_is_left_alone_with_no_point(poll_db, vp_deferred):
    db = poll_db
    from app.tasks.venue_poll_30s import write_market

    mid, ids = await _vp_market(db, source="kalshi", ext="KXN", legs=[("KXN-A", False, None)])
    await db.commit()
    stats = {"unknown_outcomes": 0}
    # The venue read was sent an hour ago; the row was written since.
    poll = await _vp_poll(db, ids.values(), fetched_at=datetime.now(timezone.utc) - timedelta(hours=1))
    await write_market(db, venue="kalshi", market_id=mid, poll=poll, stats=stats, deferred=_vp_points(),
                       priced=[_vp_item("KXN-A", 0.70, 0.69, 0.71)])
    prob, points = await _vp_row(db, ids["KXN-A"])
    assert float(prob) == pytest.approx(0.40) and points == 0
    assert stats["legs_newer_writer"] == 1


async def test_a_move_inside_the_interval_moves_the_row_and_gains_its_point_later(poll_db, vp_deferred):
    db = poll_db
    from app.models.models import FuturesOddsSnapshot
    from app.tasks.venue_poll_30s import HISTORY_MIN_INTERVAL_S, write_market

    mid, ids = await _vp_market(db, source="kalshi", ext="KXH", legs=[("KXH-A", False, None)])
    oid = ids["KXH-A"]
    db.add(FuturesOddsSnapshot(
        outcome_id=oid, bookmaker="kalshi", probability=0.40,
        captured_at=datetime.now(timezone.utc) - timedelta(seconds=10),
    ))
    await db.commit()
    future = datetime.now(timezone.utc) + timedelta(seconds=5)
    stats = {"unknown_outcomes": 0}
    poll = await _vp_poll(db, [oid], fetched_at=future)
    await write_market(db, venue="kalshi", market_id=mid, poll=poll, stats=stats, deferred=_vp_points(),
                       priced=[_vp_item("KXH-A", 0.41, 0.40, 0.42)])
    prob, points = await _vp_row(db, oid)
    assert float(prob) == pytest.approx(0.41) and points == 1  # row moved, no new point
    assert stats["history_deferred"] == 1
    _vp_save_points()

    # The next pass after the interval reads the same price: a trailing point.
    later = await _vp_poll(db, [oid], fetched_at=future + timedelta(seconds=5))
    later.now = later.now + timedelta(seconds=HISTORY_MIN_INTERVAL_S + 1)
    await write_market(db, venue="kalshi", market_id=mid, poll=later, stats=stats, deferred=_vp_points(),
                       priced=[_vp_item("KXH-A", 0.41, 0.40, 0.42)])
    assert (await _vp_row(db, oid))[1] == 2
    assert stats["history_trailing_points"] == 1


async def test_a_settled_leg_is_never_written(poll_db, vp_deferred):
    db = poll_db
    from app.tasks.venue_poll_30s import write_market

    mid, ids = await _vp_market(db, source="kalshi", ext="KXS",
                             legs=[("KXS-A", True, "api_settlement"), ("KXS-B", False, "api_settlement")])
    await db.commit()
    stats = {"unknown_outcomes": 0}
    poll = await _vp_poll(db, ids.values(), fetched_at=datetime.now(timezone.utc) + timedelta(seconds=5))
    await write_market(db, venue="kalshi", market_id=mid, poll=poll, stats=stats, deferred=_vp_points(),
                       priced=[_vp_item("KXS-A", 0.55, 0.54, 0.56), _vp_item("KXS-B", 0.55, 0.54, 0.56)])
    for oid in ids.values():
        prob, points = await _vp_row(db, oid)
        assert float(prob) == pytest.approx(0.40) and points == 0
    assert stats["unknown_outcomes"] == 2


# ── #10090 lane1 R1/R2 on #11793: the poll never waits on a held row, and never
#    restores a price a socket withdrew after the poll's read was sent ─────────


async def _vp_hold(engine, outcome_id):
    """An open transaction holding one leg, the way a socket save does."""
    from sqlalchemy import text

    holder = await engine.connect()
    await holder.begin()
    await holder.execute(
        text("UPDATE futures_outcomes SET current_probability = 0.45 WHERE id = :o"),
        {"o": outcome_id},
    )
    return holder


async def _vp_timed(coro):
    import time

    t0 = time.monotonic()
    out = await coro
    return out, time.monotonic() - t0


async def test_the_poll_skips_a_held_leg_and_never_holds_its_siblings_waiting(poll_db, vp_deferred):
    import asyncio

    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import create_async_engine

    from app.tasks.venue_poll_30s import write_market

    db = poll_db
    mid, ids = await _vp_market(db, source="kalshi", ext="KXL",
                                legs=[("KXL-A", False, None), ("KXL-B", False, None)])
    await db.commit()
    engine = create_async_engine(DB_URL)
    holder = await _vp_hold(engine, ids["KXL-B"])
    third = await engine.connect()
    # get_task_session's bound: a poll that waits shows as ~2 s and an error.
    await db.execute(text("SET lock_timeout = '2s'"))
    stats = {"unknown_outcomes": 0}
    poll = await _vp_poll(db, ids.values(), fetched_at=datetime.now(timezone.utc) + timedelta(seconds=5))

    async def third_writer_of_a():
        await asyncio.sleep(0.5)  # after the poll has written A
        await third.begin()
        await third.execute(text("SET LOCAL lock_timeout = '1s'"))
        out, waited = await _vp_timed(third.execute(
            text("UPDATE futures_outcomes SET current_probability = 0.50 WHERE id = :o"),
            {"o": ids["KXL-A"]},
        ))
        await third.rollback()
        return waited

    try:
        (_, poll_s), third_s = await asyncio.gather(
            _vp_timed(write_market(db, venue="kalshi", market_id=mid, poll=poll, stats=stats, deferred=_vp_points(),
                                   priced=[_vp_item("KXL-A", 0.55, 0.54, 0.56),
                                           _vp_item("KXL-B", 0.60, 0.59, 0.61)])),
            third_writer_of_a(),
        )
    finally:
        await holder.rollback()
        await holder.close()
        await third.close()
        await engine.dispose()
    assert poll_s < 1.0 and third_s < 0.5
    assert stats["rows_updated"] == 1 and stats["legs_held"] == 1
    assert "legs_newer_writer" not in stats
    assert float((await _vp_row(db, ids["KXL-A"]))[0]) == pytest.approx(0.55)
    assert float((await _vp_row(db, ids["KXL-B"]))[0]) == pytest.approx(0.40)
    rank = dict((await db.execute(
        text("SELECT id, rank FROM futures_outcomes WHERE market_id = :m"), {"m": mid}
    )).fetchall())
    # A is re-ranked; the held B keeps its rank for the next pass.
    assert rank[ids["KXL-A"]] == 1 and rank[ids["KXL-B"]] is None


async def test_the_rerank_skips_a_held_leg_the_price_write_never_touched(poll_db, vp_deferred):
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import create_async_engine

    from app.tasks.venue_poll_30s import write_market

    db = poll_db
    mid, ids = await _vp_market(db, source="kalshi", ext="KXR",
                                legs=[("KXR-A", False, None), ("KXR-B", False, None)])
    await db.commit()
    engine = create_async_engine(DB_URL)
    # B is held and not in this read: only the rerank would reach it.
    holder = await _vp_hold(engine, ids["KXR-B"])
    await db.execute(text("SET lock_timeout = '2s'"))
    stats = {"unknown_outcomes": 0}
    poll = await _vp_poll(db, [ids["KXR-A"]], fetched_at=datetime.now(timezone.utc) + timedelta(seconds=5))
    try:
        _, poll_s = await _vp_timed(write_market(
            db, venue="kalshi", market_id=mid, poll=poll, stats=stats, deferred=_vp_points(),
            priced=[_vp_item("KXR-A", 0.55, 0.54, 0.56)],
        ))
    finally:
        await holder.rollback()
        await holder.close()
        await engine.dispose()
    assert poll_s < 1.0 and stats["rows_updated"] == 1
    assert float((await _vp_row(db, ids["KXR-A"]))[0]) == pytest.approx(0.55)


async def test_the_poll_never_restores_a_price_the_socket_withdrew_after_its_read(poll_db, vp_deferred):
    import asyncio

    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    from app.tasks.polymarket_ws import withdraw_book_refuted_prices
    from app.tasks.venue_poll_30s import write_market

    db = poll_db
    mid, ids = await _vp_market(db, source="polymarket", ext="9100", legs=[("0xabc", False, None)])
    oid = ids["0xabc"]
    await db.execute(text("UPDATE futures_outcomes SET last_updated = now() - interval '1 hour', "
                          "price_changed_at = now() - interval '1 hour' WHERE id = :o"), {"o": oid})
    await db.commit()
    # The poll's read is sent (a tight book at 0.42) ...
    fetched_at = (await db.execute(text("SELECT clock_timestamp()"))).scalar_one()
    await db.commit()
    await asyncio.sleep(0.05)
    # ... then the socket sees the book go wide and withdraws the held 0.40
    # (#9934: price NULL, `price_changed_at` moves, `last_updated` does not) ...
    engine = create_async_engine(DB_URL)
    async with async_sessionmaker(engine)() as sock:
        withdrawn = await withdraw_book_refuted_prices(sock, {oid: (0.60, 0.99)})
        await sock.commit()
    await engine.dispose()
    assert [r[0] for r in withdrawn] == [oid]
    await db.commit()
    # ... then the poll's write of its earlier read lands, and yields.
    stats = {"unknown_outcomes": 0}
    poll = await _vp_poll(db, [oid], fetched_at=fetched_at)
    await write_market(db, venue="polymarket", market_id=mid, poll=poll, stats=stats, deferred=_vp_points(),
                       priced=[_vp_item("0xabc", 0.42, 0.41, 0.43)])
    prob, points = await _vp_row(db, oid)
    assert prob is None and points == 0
    assert stats["legs_newer_writer"] == 1 and "legs_held" not in stats


# ── #10090 lane1 G1 on #11793: both poll lock sites take FOR NO KEY UPDATE, so a
#    pending snapshot INSERT (its FK check holds FOR KEY SHARE on the leg) is
#    neither skipped as `legs_held` nor waited on. FOR UPDATE would be both ─────


async def _vp_pending_snapshot(engine, outcome_id):
    """An open transaction with a snapshot INSERT pending on one leg; returns it
    and its relation lock modes on futures_outcomes (the FK's KEY SHARE)."""
    from sqlalchemy import func, insert, text

    from app.models.models import FuturesOddsSnapshot

    holder = await engine.connect()
    await holder.begin()
    await holder.execute(insert(FuturesOddsSnapshot).values(
        outcome_id=outcome_id, bookmaker="kalshi", probability=0.4, captured_at=func.now(), reading_count=1,
    ))
    mode = (await holder.execute(text(
        "SELECT string_agg(l.mode, ',') FROM pg_locks l WHERE l.pid = pg_backend_pid() "
        "AND l.locktype = 'relation' AND l.relation = 'futures_outcomes'::regclass"
    ))).scalar_one()
    return holder, mode


async def test_the_poll_writes_a_leg_with_a_pending_snapshot_insert_without_skipping_or_waiting(
    poll_db, vp_deferred
):
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import create_async_engine

    from app.tasks.venue_poll_30s import write_market

    db = poll_db
    mid, ids = await _vp_market(db, source="kalshi", ext="KXK",
                                legs=[("KXK-A", False, None), ("KXK-B", False, None)])
    await db.commit()
    engine = create_async_engine(DB_URL)
    holder, mode = await _vp_pending_snapshot(engine, ids["KXK-B"])
    await db.execute(text("SET lock_timeout = '2s'"))
    stats = {"unknown_outcomes": 0}
    poll = await _vp_poll(db, ids.values(), fetched_at=datetime.now(timezone.utc) + timedelta(seconds=5))
    try:
        _, poll_s = await _vp_timed(write_market(
            db, venue="kalshi", market_id=mid, poll=poll, stats=stats, deferred=_vp_points(),
            priced=[_vp_item("KXK-A", 0.55, 0.54, 0.56), _vp_item("KXK-B", 0.60, 0.59, 0.61)],
        ))
    finally:
        await holder.rollback()
        await holder.close()
        await engine.dispose()
    assert "RowShareLock" in (mode or "")  # the case is real: the FK check holds KEY SHARE
    assert poll_s < 1.0
    assert stats["rows_updated"] == 2
    assert "legs_held" not in stats and "legs_newer_writer" not in stats
    assert float((await _vp_row(db, ids["KXK-B"]))[0]) == pytest.approx(0.60)


async def test_the_rerank_reaches_a_leg_with_a_pending_snapshot_insert_without_skipping_or_waiting(
    poll_db, vp_deferred
):
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import create_async_engine

    from app.tasks.venue_poll_30s import write_market

    db = poll_db
    mid, ids = await _vp_market(db, source="kalshi", ext="KXQ",
                                legs=[("KXQ-A", False, None), ("KXQ-B", False, None)])
    await db.commit()
    engine = create_async_engine(DB_URL)
    # B has a snapshot INSERT pending and is not in this read: only the rerank reaches it.
    holder, mode = await _vp_pending_snapshot(engine, ids["KXQ-B"])
    await db.execute(text("SET lock_timeout = '2s'"))
    stats = {"unknown_outcomes": 0}
    poll = await _vp_poll(db, [ids["KXQ-A"]], fetched_at=datetime.now(timezone.utc) + timedelta(seconds=5))
    try:
        _, poll_s = await _vp_timed(write_market(
            db, venue="kalshi", market_id=mid, poll=poll, stats=stats, deferred=_vp_points(),
            priced=[_vp_item("KXQ-A", 0.55, 0.54, 0.56)],
        ))
    finally:
        await holder.rollback()
        await holder.close()
        await engine.dispose()
    rank = dict((await db.execute(
        text("SELECT id, rank FROM futures_outcomes WHERE market_id = :m"), {"m": mid}
    )).fetchall())
    assert "RowShareLock" in (mode or "")
    assert poll_s < 1.0
    assert rank[ids["KXQ-A"]] == 1 and rank[ids["KXQ-B"]] == 2


async def test_clob_items_write_every_leg_convention_then_skip_unchanged_markets(poll_db, vp_deferred):
    """The CLOB path's items through the first build's writer: a field's bare
    legs, a ``_yes``/``_no`` pair and a bare + ``_side1`` pair each take the
    side ``_write_prices`` gives them; a second identical pass writes nothing and
    skips each market before the writer's own read."""
    db = poll_db
    from app.tasks import venue_poll_pm_clob as clob
    from app.tasks.venue_poll_30s import Unit, _write_group

    field_id, field = await _vp_market(db, source="polymarket", ext="7001",
                                       legs=[("0xa", False, None), ("0xb", False, None)])
    pair_id, pair = await _vp_market(db, source="polymarket", ext="7002",
                                     legs=[("0xd_yes", False, None), ("0xd_no", False, None)])
    side_id, side = await _vp_market(db, source="polymarket", ext="7003",
                                     legs=[("0xe", False, None), ("0xe_side1", False, None)])
    await db.commit()
    units = [Unit("7001", {field_id: [(field["0xa"], "0xa"), (field["0xb"], "0xb")]}),
             Unit("7002", {pair_id: [(pair["0xd_yes"], "0xd_yes"), (pair["0xd_no"], "0xd_no")]}),
             Unit("7003", {side_id: [(side["0xe"], "0xe"), (side["0xe_side1"], "0xe_side1")]})]
    token_of = {"0xa": "ta", "0xb": "tb", "0xd": "td", "0xe": "te"}
    tops = {"ta": (0.42, 0.50), "tb": (None, 0.03), "td": (0.60, 0.62), "te": (0.20, 0.24)}

    async def one_pass():
        stats = {"errors": [], "unknown_outcomes": 0}
        priced: set = set()
        found = clob._price_group(units, token_of, tops, priced, stats)
        await _write_group(db, "polymarket", units, found,
                           datetime.now(timezone.utc) + timedelta(seconds=5), stats)
        return stats

    stats = await one_pass()
    expect = {field["0xa"]: 0.46, field["0xb"]: 0.40,  # 0xb: no bid → untouched
              pair["0xd_yes"]: 0.61, pair["0xd_no"]: 0.39,
              side["0xe"]: 0.22, side["0xe_side1"]: 0.78}
    for oid, prob in expect.items():
        assert float((await _vp_row(db, oid))[0]) == pytest.approx(prob), oid
    assert stats["rows_updated"] == 5 and stats["history_points"] == 5
    assert stats["clob_refused_no_book"] == 1 and stats["errors"] == []

    again = await one_pass()
    assert again.get("rows_updated", 0) == 0 and again["markets_unchanged"] == 3
    for oid in expect:
        assert (await _vp_row(db, oid))[1] == (0 if oid == field["0xb"] else 1)
