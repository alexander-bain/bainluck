"""#4253 — a Kalshi leg the venue has DELISTED stops claiming 100%, proved on real Postgres.

## The defect, as a reader meets it

`/api/futures/108555` — *When will Starlink officially announce an IPO?* — served
its first five outcomes, ranked above every real price, as::

    Before Oct 1, 2025  100%     Before Jan 1, 2026  100%
    Before Nov 1, 2025  100%     Before Sep 1, 2025  100%
    Before Dec 1, 2025  100%     ... then 8.5%, 6.5%, 5.5%

Starlink has not IPO'd. Every one of those five is a contract that ended, and
Kalshi purged its market row (gotcha #35), so the leg vanished from the event's
book and no writer has touched our row since March 2026. **Declining to write is
not the same as withdrawing what is written** — the Polymarket half of this
lesson is `_unpriced_leg_external_ids` (#4000); this is the Kalshi half, and it
is a *different venue fact*: not "the venue quotes no price for this leg" but
"the venue no longer serves this leg at all".

## Why the arms below are shaped the way they are

Measured on production 2026-09-09 against the venue's own API, not our mirror
(standing notice 26): 41 legs across 14 reachable markets carry
`current_probability = 1.0` uncrowned. All 41 are absent from their event's
nested book AND answer **404** on `GET /markets/{ticker}`; three controls still
in the book answer 200, including `KXIPOSTARLINK-26SEP01`, which is `finalized`
with `result=no`.

But the same census found the rule's blast radius is ~30x its defect: over a
random 40-market sample, 4.2% of ALL stored legs are absent from the venue, and
those are dominated by a *different* population — `KX10SONG-26` carries twelve
delisted legs at ~0.99 (Taylor, Bad Bunny, Harry Styles) that are **ungraded YES
results** sitting beside five crowned siblings. Retiring those would destroy the
last surviving trace of a settlement, because Kalshi has purged the result too.

So the gate is not "delisted". It is "delisted AND nothing in this market has
ever been graded", and `test_a_market_grading_has_touched_is_refused` is the arm
that carries the whole safety argument: **the 18 legs the rule refuses are the
proof, not a shortfall.**

## Why real Postgres

`_KALSHI_FROZEN_CERTAIN_SQL` turns on a correlated `NOT EXISTS` over the same
table it selects from, `= ANY(:ids)` binding, and a `RETURNING` clause on the
compare-and-set. None of those are observable in a mock session, and the clock
arm cannot be a source scan at all: `FuturesOutcome.last_updated` carries
`onupdate=func.now()`, which fires for Core/ORM `update()` and **not** for
`text()`. "The timestamp survives" therefore rests on an interaction between a
column default and a *statement style*, neither visible in the retirement's
source — a switch to `sqlalchemy.update()` keeps every scan green and bumps the
clock on every row. That is CERT-2382's finding, applied here before it could
happen again: `futures_markets.updated_at` is rendered to readers as the card's
own date, and `futures_outcomes.last_updated` is what freshness consumers read.

Opt-in on `SEARCH_TEST_DATABASE_URL` (no local Postgres in the agent sandbox —
initdb fails on shmget), so **CI is the environment that runs this**, in the
`search-recall` job, whose skip-detector refuses to let an unrun gate read as a
passing one.
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
            "set SEARCH_TEST_DATABASE_URL to run the real-Postgres Kalshi "
            "delisted-leg retirement gate (CI job: search-recall)"
        ),
    ),
]

#: Deliberately far in the past and asserted verbatim later. A row seeded at
#: `now()` makes "unchanged" and "stamped now" indistinguishable, so the clock
#: arm would pass against the very defect it exists to catch.
_SEEDED_AT = datetime(2026, 3, 30, 16, 45, 13, tzinfo=timezone.utc)


@pytest.fixture
async def db():
    """A real Postgres carrying the real schema."""
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    # One import STYLE for this module across the file (`from ... import ...`),
    # because `_seed` below also needs its names: mixing `import x.y` here with
    # `from x.y import Z` there trips CodeQL's `py/import-and-import-from`.
    # Still imported for its side effect — it registers every table on `Base`.
    from app.models import models as _models  # noqa: F401
    from app.services.database import Base

    engine = create_async_engine(DB_URL)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)

    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as session:
        yield session

    await engine.dispose()


class _FakeKalshi:
    """Answers `market_exists` from a ticker -> True/False/None table.

    The tri-state is the point: `False` is an observed 404, `None` is "we could
    not tell", and the production client collapses a timeout into the same
    return as a 404 unless the caller distinguishes them (gotcha #36).
    """

    def __init__(self, table: dict):
        self.table = table
        self.asked: list[str] = []

    async def market_exists(self, ticker: str):
        self.asked.append(ticker)
        return self.table.get(ticker)


async def _seed(session, legs, *, external_id="KXIPOTEST"):
    """One open Kalshi market whose outcomes are `(ticker, probability, is_winner)`."""
    from app.models.models import FuturesMarket, FuturesOutcome

    market = FuturesMarket(
        source="kalshi",
        external_id=external_id,
        name="When will TestCo officially announce an IPO?",
        category="futures",
        market_type="quantity",
        market_tier=2,
        status="open",
        volume=321074,
        resolution_date=datetime.now(timezone.utc) + timedelta(days=300),
    )
    session.add(market)
    await session.flush()

    for ticker, probability, is_winner in legs:
        session.add(
            FuturesOutcome(
                market_id=market.id,
                external_id=ticker,
                name=ticker,
                current_probability=probability,
                current_american_odds=-10000 if probability == 1.0 else 100,
                opening_probability=0.5,
                is_winner=is_winner,
                last_updated=_SEEDED_AT,
            )
        )
    await session.flush()
    await session.commit()
    return market


def _stats():
    from app.tasks.futures_price_refresh import KALSHI_DELISTED_CHECK_BUDGET  # noqa: F401

    return {
        "delisted_checks": 0,
        "delisted_still_listed": 0,
        "delisted_indeterminate": 0,
        "delisted_refused_market_graded": 0,
        "delisted_check_budget_hit": False,
        "errors": [],
    }


async def _run(session, market, venue, stats=None):
    """Scan for candidates, then confirm and retire. Returns (stats, retired)."""
    from app.tasks.futures_price_refresh import (
        _retire_delisted_kalshi_legs,
        _scan_kalshi_frozen_certain,
    )

    stats = stats if stats is not None else _stats()
    candidates = await _scan_kalshi_frozen_certain(session, [market.id])
    retired = 0
    if candidates.get(market.id):
        retired = await _retire_delisted_kalshi_legs(
            session, venue, market.id, candidates[market.id], stats
        )
        await session.commit()
    return stats, retired, candidates


async def _row(session, market_id, ticker):
    from sqlalchemy import text

    return (
        await session.execute(
            text(
                "SELECT current_probability, current_american_odds, "
                "       opening_probability, is_winner, last_updated "
                "  FROM futures_outcomes "
                " WHERE market_id = :m AND external_id = :t"
            ),
            {"m": market_id, "t": ticker},
        )
    ).one()


class TestTheShip:
    async def test_a_delisted_certain_leg_is_withdrawn(self, db):
        """The founding case: "Before Sep 1, 2025" stops reading 100%."""
        market = await _seed(
            db,
            [
                ("KXIPOTEST-25SEP01", 1.0, False),
                ("KXIPOTEST-27JUN01", 0.73, False),
            ],
        )
        venue = _FakeKalshi(
            {"KXIPOTEST-25SEP01": False, "KXIPOTEST-27JUN01": True}
        )

        stats, retired, _ = await _run(db, market, venue)

        assert retired == 1, "the delisted certain leg was not withdrawn"
        gone = await _row(db, market.id, "KXIPOTEST-25SEP01")
        assert gone.current_probability is None
        assert gone.current_american_odds is None

        # The live leg is untouched, and was never even asked about: it is not a
        # candidate, so it costs no venue call.
        live = await _row(db, market.id, "KXIPOTEST-27JUN01")
        assert float(live.current_probability) == pytest.approx(0.73)
        assert venue.asked == ["KXIPOTEST-25SEP01"]
        assert stats["delisted_checks"] == 1

    async def test_the_observation_clock_and_the_opening_survive(self, db):
        """CERT-2382's finding, applied before it could happen again.

        `last_updated` is what freshness consumers read and what the card renders
        as its date; `opening_probability` is calibration truth and a different
        owner's. A withdrawal must move neither. This cannot be a source scan —
        `onupdate=func.now()` fires for `update()` and not for `text()`.
        """
        market = await _seed(db, [("KXIPOTEST-25SEP01", 1.0, False)])
        venue = _FakeKalshi({"KXIPOTEST-25SEP01": False})

        _, retired, _ = await _run(db, market, venue)
        assert retired == 1

        row = await _row(db, market.id, "KXIPOTEST-25SEP01")
        assert row.current_probability is None, "precondition: it was retired"
        assert row.last_updated == _SEEDED_AT, (
            "the withdrawal moved the observation clock — a reader would be told "
            "we observed this market just now, at the moment we stopped having a "
            "number for it"
        )
        assert float(row.opening_probability) == pytest.approx(0.5)


class TestTheRefusalsThatAreTheSafetyArgument:
    async def test_a_market_grading_has_touched_is_refused(self, db):
        """The 18 legs the rule declines on production, and why.

        `KX10SONG-26` / *Who will release a new song this year?* carries delisted
        legs at ~1.0 beside crowned siblings. There a 1.0 uncrowned is most
        likely an ungraded YES, and the venue has purged the result — so the
        price is the last trace of it, and withdrawing it destroys information
        rather than restoring truth. The right fix there is a winner, not an
        absence, and it belongs to grading.
        """
        market = await _seed(
            db,
            [
                ("KX10SONG-26-TAY", 1.0, False),   # ungraded, looks identical
                ("KX10SONG-26-SWA", 0.995, True),  # grading HAS run here
            ],
            external_id="KX10SONG-26",
        )
        venue = _FakeKalshi({"KX10SONG-26-TAY": False})

        stats, retired, candidates = await _run(db, market, venue)

        assert candidates == {}, (
            "a market with a crowned outcome must not yield candidates at all"
        )
        assert retired == 0
        assert venue.asked == [], "the venue must not even be asked"
        kept = await _row(db, market.id, "KX10SONG-26-TAY")
        assert float(kept.current_probability) == pytest.approx(1.0)

    async def test_a_leg_the_venue_still_lists_is_refused(self, db):
        """`KXIPOSTARLINK-26SEP01` is `finalized` and answers 200. Not ours."""
        market = await _seed(db, [("KXIPOTEST-26SEP01", 1.0, False)])
        venue = _FakeKalshi({"KXIPOTEST-26SEP01": True})

        stats, retired, _ = await _run(db, market, venue)

        assert retired == 0
        assert stats["delisted_still_listed"] == 1
        kept = await _row(db, market.id, "KXIPOTEST-26SEP01")
        assert float(kept.current_probability) == pytest.approx(1.0)

    async def test_an_unreachable_venue_is_not_an_absence(self, db):
        """`None` means "we could not tell" and may never be spent as evidence.

        The production client returns the same value for a genuine 404 and for a
        three-times-failed request (gotcha #36); if this arm ever goes green by
        retiring, a network wobble un-prices live markets.
        """
        market = await _seed(db, [("KXIPOTEST-25SEP01", 1.0, False)])
        venue = _FakeKalshi({"KXIPOTEST-25SEP01": None})

        stats, retired, _ = await _run(db, market, venue)

        assert retired == 0
        assert stats["delisted_indeterminate"] == 1
        kept = await _row(db, market.id, "KXIPOTEST-25SEP01")
        assert float(kept.current_probability) == pytest.approx(1.0)

    async def test_a_price_below_certainty_is_not_a_candidate(self, db):
        """0.99 is a PRICE. Only an exact 1.0 uncrowned is a claim of certainty."""
        market = await _seed(db, [("KXIPOTEST-25SEP01", 0.99, False)])
        venue = _FakeKalshi({"KXIPOTEST-25SEP01": False})

        _, retired, candidates = await _run(db, market, venue)

        assert candidates == {}
        assert retired == 0
        kept = await _row(db, market.id, "KXIPOTEST-25SEP01")
        assert float(kept.current_probability) == pytest.approx(0.99)

    async def test_a_crowned_leg_keeps_its_settlement(self, db):
        """A crowned leg's 1.0 is its result, not a quote — even once delisted."""
        market = await _seed(
            db,
            [
                ("KXIPOTEST-25SEP01", 1.0, True),
                ("KXIPOTEST-27JUN01", 0.73, False),
            ],
        )
        venue = _FakeKalshi({"KXIPOTEST-25SEP01": False})

        _, retired, candidates = await _run(db, market, venue)

        assert candidates == {}
        assert retired == 0
        kept = await _row(db, market.id, "KXIPOTEST-25SEP01")
        assert float(kept.current_probability) == pytest.approx(1.0)
        assert kept.is_winner is True


class TestTheRaceBetweenTheScanAndTheWrite:
    """CERT-2394. The scan's verdict is a candidate list, not a permission.

    `_scan_kalshi_frozen_certain` runs ONCE for the whole batch, then each
    candidate costs a venue round trip — up to `KALSHI_DELISTED_CHECK_BUDGET` of
    them, spaced 0.15s — before anything is written. `backfill_winners` runs
    against these same markets every 6h. So the window in which "this market has
    never been graded" can stop being true is real, it is measured in minutes,
    and it is the window the withdrawal decides inside.

    These tests crown a sibling AFTER the scan and BEFORE the write, which is
    exactly the interleaving that the first version's compare-and-set could not
    see: it re-checked the candidate's own `current_probability`/`is_winner`,
    both of which the crowning leaves untouched.
    """

    async def _scan_then_crown_then_retire(self, db, market, venue, crown):
        """Scan · crown `crown` · retire. Returns (stats, retired, candidates)."""
        from sqlalchemy import text

        from app.tasks.futures_price_refresh import (
            _retire_delisted_kalshi_legs,
            _scan_kalshi_frozen_certain,
        )

        stats = _stats()
        candidates = await _scan_kalshi_frozen_certain(db, [market.id])

        # ── the concurrent grader commits here, mid-flight ──────────────────
        await db.execute(
            text(
                "UPDATE futures_outcomes SET is_winner = TRUE "
                " WHERE market_id = :m AND external_id = :t"
            ),
            {"m": market.id, "t": crown},
        )
        await db.commit()

        retired = 0
        if candidates.get(market.id):
            retired = await _retire_delisted_kalshi_legs(
                db, venue, market.id, candidates[market.id], stats
            )
            await db.commit()
        return stats, retired, candidates

    async def test_a_sibling_crowned_after_the_scan_refuses_the_whole_market(self, db):
        """0 retired, 1.0 retained — the cert's named acceptance.

        The scan admits the market (nothing crowned yet), the venue confirms the
        404, and grading lands in between. The leg must survive: in a market
        grading HAS now touched, a delisted 1.0 is the ungraded-YES class the
        rule exists to protect, and withdrawing it destroys the last trace of a
        result the venue has already purged.
        """
        market = await _seed(
            db,
            [
                ("KXIPOTEST-26SEP01", 1.0, False),  # our candidate
                ("KXIPOTEST-26OCT01", 0.42, False),  # crowned mid-flight
            ],
        )
        venue = _FakeKalshi({"KXIPOTEST-26SEP01": False})

        stats, retired, candidates = await self._scan_then_crown_then_retire(
            db, market, venue, crown="KXIPOTEST-26OCT01"
        )

        assert candidates.get(market.id) == ["KXIPOTEST-26SEP01"], (
            "precondition: the scan must admit the market BEFORE the crowning, "
            "or this test is not exercising the race at all"
        )
        assert venue.asked == ["KXIPOTEST-26SEP01"], (
            "precondition: the venue round trip is the race window"
        )
        assert retired == 0, "a market graded mid-flight must retire nothing"

        kept = await _row(db, market.id, "KXIPOTEST-26SEP01")
        assert float(kept.current_probability) == pytest.approx(1.0), (
            "the candidate's price was erased in a market that is now graded — "
            "the exact class the crowned-sibling refusal exists to preserve"
        )
        assert kept.current_american_odds == -10000, (
            "the odds column must not be half-written either"
        )

    async def test_the_refusal_is_counted_so_it_can_be_seen_firing(self, db):
        """A boundary nobody can observe is one nobody can prove still works.

        Zero retired has two causes — "the venue re-listed everything" and "this
        market got graded under us" — and they are different news. The stat is
        the only thing that separates them in a task metrics read.
        """
        market = await _seed(
            db,
            [
                ("KXIPOTEST-26SEP01", 1.0, False),
                ("KXIPOTEST-26OCT01", 0.42, False),
            ],
        )
        venue = _FakeKalshi({"KXIPOTEST-26SEP01": False})

        stats, retired, _ = await self._scan_then_crown_then_retire(
            db, market, venue, crown="KXIPOTEST-26OCT01"
        )

        assert retired == 0
        assert stats["delisted_refused_market_graded"] == 1

    async def test_no_crowning_still_retires_and_does_not_count_a_refusal(self, db):
        """The control: same interleaving, nothing crowned, the ship still works.

        Without this the two tests above pass just as well against a build that
        retires NOTHING, and the repair would have bought its safety by breaking
        the ship.
        """
        market = await _seed(
            db,
            [
                ("KXIPOTEST-26SEP01", 1.0, False),
                ("KXIPOTEST-26OCT01", 0.42, False),
            ],
        )
        venue = _FakeKalshi({"KXIPOTEST-26SEP01": False})

        # Same helper, crowning a ticker that does not exist -> a no-op UPDATE,
        # so the interleaving is identical and only the crowning is removed.
        stats, retired, _ = await self._scan_then_crown_then_retire(
            db, market, venue, crown="KXIPOTEST-NO-SUCH-LEG"
        )

        assert retired == 1, "the ship must still withdraw an ungraded delisted leg"
        assert stats["delisted_refused_market_graded"] == 0
        withdrawn = await _row(db, market.id, "KXIPOTEST-26SEP01")
        assert withdrawn.current_probability is None
        assert withdrawn.current_american_odds is None


class TestTheBudget:
    async def test_the_confirmation_budget_bounds_the_venue_calls(self, db):
        """One pass cannot spend the loop's wall clock confirming 404s."""
        from app.tasks.futures_price_refresh import KALSHI_DELISTED_CHECK_BUDGET

        over = KALSHI_DELISTED_CHECK_BUDGET + 5
        legs = [(f"KXIPOTEST-L{i:03d}", 1.0, False) for i in range(over)]
        market = await _seed(db, legs)
        venue = _FakeKalshi({t: False for t, _, _ in legs})

        stats, retired, _ = await _run(db, market, venue)

        assert len(venue.asked) == KALSHI_DELISTED_CHECK_BUDGET, (
            "the budget did not bound the venue calls"
        )
        assert stats["delisted_check_budget_hit"] is True
        assert retired == KALSHI_DELISTED_CHECK_BUDGET, (
            "every confirmed leg inside the budget should still be withdrawn"
        )
        # The overflow is left for the next pass, not silently dropped.
        leftover = await _row(db, market.id, f"KXIPOTEST-L{over - 1:03d}")
        assert float(leftover.current_probability) == pytest.approx(1.0)
