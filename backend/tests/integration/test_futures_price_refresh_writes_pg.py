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
        )

        market = await _seed_brazil(db)
        await db.commit()

        def _count(value_sql):
            return text(
                f"SELECT COUNT(*) FROM futures_markets fm "
                f"WHERE fm.id = :mid AND ({value_sql})"
            )

        params = {"mid": market.id, "volume_floor": HIGH_VALUE_VOLUME_FLOOR}
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


async def _drive_the_real_task(monkeypatch, session, verdicts):
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
    monkeypatch.setattr(
        "app.services.polymarket_api.PolymarketAPIService", lambda: _Svc()
    )
    monkeypatch.setattr("app.services.kalshi_api.KalshiAPIService", lambda: _Svc())

    async def _fetch(_service, external_id):
        return verdicts.get(external_id)

    monkeypatch.setattr(fpr, "_fetch_kalshi_prices", _fetch)
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
