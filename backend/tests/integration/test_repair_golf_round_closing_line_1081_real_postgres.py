"""CAL-P1081 (#938)'s golf closing-line repair, executed against a REAL PostgreSQL.

## what this guards, and why nothing cheaper would have caught it

The claim is **"a stored price changed value, to the one the venue actually
quoted"**, and the only thing that can observe a stored row changing value is a
server that stored it. Three of this rail's four moving parts are server-side
and invisible to a mock:

* the candidate predicate turns on a correlated ``LEFT JOIN LATERAL`` over
  ``futures_odds_snapshots`` ordered ``captured_at DESC LIMIT 1``,
* the write re-derives that same lateral inside the ``UPDATE`` rather than
  trusting the plan's ids, and
* ``Numeric(7,6)`` equality (``calibration_probability = opening_probability``)
  is a database comparison, not a Python one — a float round-trip would make
  0.99 == 0.99 true in Python and could make it false in the column.

## the corpus, and what each row can fail on

Five outcomes on three markets, each paired with the defect it catches.

* **the subject** (``SUBJECT_OUTCOME``) — a ``KXDPWORLDTOURR1LEAD`` leg stamped
  ``calibration_probability = opening_probability = 0.99`` with two snapshots
  before commence (0.99 at open, **0.07** last). Must read back **0.07**. This
  is the production specimen: twenty-three golfers at 0.99 in one round-leader
  market while the venue's own last pre-round quote said 7 cents.
* **the ruling-103 control** (``LATE_OUTCOME``) — its ONLY two quotes sit
  **exactly at** ``commence_time`` and two hours after it. Must be refused
  ``no_pre_commence_snapshot`` and keep its stamp. A price captured once the
  round is under way is a partly-known result, not a forecast.

  🔴 **CI wrote this arm's final shape, and the first version was the wrong
  test.** As first seeded, the late outcome ALSO carried an early snapshot at
  the stamp value, so the selector found a legitimate pre-commence quote that
  happened to equal the opening and refused the row as
  ``closing_equals_opening``. The rail was right; the assertion was measuring
  the wrong refusal, and it would have gone on passing as a ruling-103 guard
  while proving nothing about the ``<`` bound. The at-commence snapshot is the
  repair: it is the one value that discriminates ``<`` from ``<=``, so relaxing
  that bound now fails HERE and not only in the source scan.
* **the already-priced control** (``PRICED_OUTCOME``) — ``calibration_probability
  <> opening_probability``, i.e. a row Part A2 already repriced. Must not be
  examined at all. This is the guard against the rail widening from "the stamp
  was never replaced" to "I have an opinion about the price".
* **the no-op control** (``SAME_OUTCOME``) — stamp and closing line agree. Must
  be refused ``closing_equals_opening`` rather than written, so ``changed``
  counts rows that MOVED.
* **the tournament control** (``TOURNEY_OUTCOME``) — same shape, same category,
  same venue, on ``KXPGATOURWINNER``. Out of the bound by scope, and it is the
  arm that fails if somebody relaxes the anchored pattern. Tournament-scoped
  golf measures 2.12/2.42 ECE against the round arms' 14.86/8.58; sweeping it in
  would rewrite a well-calibrated cohort to fix a broken one.

## the arm that proves red-first

``test_nulling_the_stamp_cannot_pass_this`` executes the repair a reviewer
reaches for first — ``SET calibration_probability = NULL``, "let the curve fall
back" — and requires the published price to stay at **0.99**. It does, because
the curve price is ``COALESCE(calibration_probability, opening_probability)``: a
coalesce, not an exclusion (gotcha #144 / ruling 103). A green run of this file
therefore means writing the real closing line was proved NECESSARY, not that
nothing objected.
"""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone

import pytest

DB_URL = os.environ.get("SEARCH_TEST_DATABASE_URL")

needs_postgres = pytest.mark.skipif(
    not DB_URL,
    reason=(
        "set SEARCH_TEST_DATABASE_URL to run the real-Postgres CAL-P1081 golf "
        "closing-line repair gate (CI job `search-recall` provides one)"
    ),
)

COMMENCE = datetime(2026, 6, 4, 14, 51, 3, tzinfo=timezone.utc)

ROUND_MARKET = 9108101
TOURNEY_MARKET = 9108102
ROUND_TICKER = "KXDPWORLDTOURR1LEAD-HEIO26"
TOURNEY_TICKER = "KXPGATOURWINNER-26"

SUBJECT_OUTCOME = 9108201
LATE_OUTCOME = 9108202
PRICED_OUTCOME = 9108203
SAME_OUTCOME = 9108204
TOURNEY_OUTCOME = 9108205

#: The production stamp and the production closing line for the specimen leg.
STAMP = 0.99
TRUE_CLOSING = 0.07


def _asyncpg_url(url: str) -> str:
    if url.startswith("postgresql+asyncpg://"):
        return url
    return url.replace("postgres://", "postgresql://", 1).replace(
        "postgresql://", "postgresql+asyncpg://", 1
    )


@pytest.fixture
async def session():
    """Real Postgres with the real schema, dropped and rebuilt."""
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    import app.models.models  # noqa: F401 — registers every table on Base
    from app.services.database import Base

    engine = create_async_engine(_asyncpg_url(DB_URL))
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as s:
        yield s
    await engine.dispose()


async def _seed(session):
    """Insert the corpus through the ORM.

    The ORM and not raw INSERT: both tables carry client-side defaults a raw
    INSERT does not apply, and `test_pg_gate_seed_completeness.py`'s raw-INSERT
    arm keys on the presence of `INSERT INTO`.
    """
    from app.models import FuturesMarket, FuturesOddsSnapshot, FuturesOutcome

    for mid, ticker in ((ROUND_MARKET, ROUND_TICKER), (TOURNEY_MARKET, TOURNEY_TICKER)):
        session.add(
            FuturesMarket(
                id=mid,
                source="kalshi",
                external_id=ticker,
                name=f"seed {ticker}",
                llm_sport_category="golf",
                status="resolved",
                event_id=None,
                commence_time=COMMENCE,
            )
        )

    # (outcome_id, market, calibration, opening)
    outcomes = (
        (SUBJECT_OUTCOME, ROUND_MARKET, STAMP, STAMP),
        (LATE_OUTCOME, ROUND_MARKET, STAMP, STAMP),
        (PRICED_OUTCOME, ROUND_MARKET, 0.35, STAMP),
        (SAME_OUTCOME, ROUND_MARKET, STAMP, STAMP),
        (TOURNEY_OUTCOME, TOURNEY_MARKET, STAMP, STAMP),
    )
    for oid, mid, cal, opening in outcomes:
        session.add(
            FuturesOutcome(
                id=oid,
                market_id=mid,
                external_id=f"seed-{oid}",
                name=f"Golfer {oid}",
                calibration_probability=cal,
                opening_probability=opening,
                is_winner=False,
                resolution_source="api_settlement",
            )
        )

    # (outcome_id, probability, offset from commence)
    snapshots = (
        # The subject: opens at the stamp, last pre-commence quote is the truth.
        (SUBJECT_OUTCOME, STAMP, timedelta(hours=-8)),
        (SUBJECT_OUTCOME, TRUE_CLOSING, timedelta(hours=-2)),
        # Ruling 103: NO quote before the round begins. The first lands exactly
        # AT commence_time — the one value that tells `<` apart from `<=` — and
        # the second two hours into the round.
        (LATE_OUTCOME, TRUE_CLOSING, timedelta(0)),
        (LATE_OUTCOME, TRUE_CLOSING, timedelta(hours=+2)),
        # Already repriced by Part A2 — must never be examined.
        (PRICED_OUTCOME, 0.35, timedelta(hours=-2)),
        # Stamp IS the closing line.
        (SAME_OUTCOME, STAMP, timedelta(hours=-2)),
        # Tournament scope, otherwise identical to the subject.
        (TOURNEY_OUTCOME, STAMP, timedelta(hours=-8)),
        (TOURNEY_OUTCOME, TRUE_CLOSING, timedelta(hours=-2)),
    )
    for oid, prob, delta in snapshots:
        session.add(
            FuturesOddsSnapshot(
                outcome_id=oid,
                bookmaker="kalshi",
                probability=prob,
                captured_at=COMMENCE + delta,
            )
        )
    await session.commit()


async def _price(session, outcome_id: int):
    from sqlalchemy import select

    from app.models import FuturesOutcome

    value = (
        await session.execute(
            select(FuturesOutcome.calibration_probability).where(
                FuturesOutcome.id == outcome_id
            )
        )
    ).scalar_one()
    return None if value is None else float(value)


async def _curve_price(session, outcome_id: int):
    """What the published curve would read for this leg.

    ``COALESCE(calibration_probability, opening_probability)`` — the producer's
    own expression. The red-first arm needs this rather than the raw column,
    because the naive repair's whole error is that NULLing one of the two
    changes nothing a reader sees.
    """
    from sqlalchemy import text

    value = (
        await session.execute(
            text(
                "SELECT COALESCE(calibration_probability, opening_probability) "
                "FROM futures_outcomes WHERE id = :oid"
            ),
            {"oid": outcome_id},
        )
    ).scalar_one()
    return None if value is None else float(value)


@needs_postgres
@pytest.mark.asyncio
async def test_the_stamp_reads_back_as_the_venues_last_pre_round_quote(session):
    """The ship: 0.99 becomes 0.07, because 0.07 is what Kalshi last quoted."""
    from app.tasks.repair_golf_round_closing_line import repair

    await _seed(session)
    assert await _price(session, SUBJECT_OUTCOME) == STAMP, "seed precondition"

    result = await repair(session, apply=True)

    assert await _price(session, SUBJECT_OUTCOME) == TRUE_CLOSING
    assert await _curve_price(session, SUBJECT_OUTCOME) == TRUE_CLOSING
    assert result["changed"] == 1, (
        "exactly one row moved; the other four are controls"
    )
    assert result["terminal"] == "changed"


@needs_postgres
@pytest.mark.asyncio
async def test_a_dry_run_moves_nothing_and_still_carries_the_restore(session):
    """D51: an operator reads the undo BEFORE deciding to apply."""
    from app.tasks.repair_golf_round_closing_line import repair

    await _seed(session)
    result = await repair(session, apply=False)

    assert await _price(session, SUBJECT_OUTCOME) == STAMP
    assert result["changed"] == 0
    assert result["terminal"] == "dry_run"
    assert result["restore_sql"] == (
        "UPDATE futures_outcomes SET calibration_probability = opening_probability "
        f"WHERE id IN ({SUBJECT_OUTCOME});"
    )
    # The numeric before-value still travels, even though the undo no longer
    # has to read it.
    assert [p["before"] for p in result["planned"]] == [STAMP]


@needs_postgres
@pytest.mark.asyncio
async def test_a_quote_after_the_round_begins_is_refused(session):
    """Ruling 103, with a specimen rather than a source scan.

    The refusal REASON is asserted, not merely the unchanged price: a row can be
    left alone for several reasons and only one of them means the ``<`` bound
    held. That distinction is what CI found wrong here the first time.
    """
    from app.tasks.repair_golf_round_closing_line import repair

    await _seed(session)
    result = await repair(session, apply=True)

    assert await _price(session, LATE_OUTCOME) == STAMP
    refusals = {r["outcome_id"]: r["reason"] for r in result["refused"]}
    assert refusals[LATE_OUTCOME] == "no_pre_commence_snapshot"


@needs_postgres
@pytest.mark.asyncio
async def test_a_quote_exactly_at_commence_cannot_pass_this(session):
    """RED-FIRST for the ``<`` bound: relaxing it to ``<=`` must break something.

    Runs the mutated selector — ``captured_at <= commence_time`` — over the same
    seeded corpus and requires it to find the at-commence quote the shipped
    selector refuses. Without this, ``test_a_quote_after_the_round_begins_is_
    refused`` passes under both versions of the bound (a +2h snapshot is
    excluded either way) and the ruling-103 guard is decoration.
    """
    from sqlalchemy import text

    await _seed(session)
    picked = (
        await session.execute(
            text(
                "SELECT probability FROM futures_odds_snapshots "
                "WHERE outcome_id = :oid AND captured_at <= :commence "
                "  AND probability > 0 AND probability < 1 "
                "ORDER BY captured_at DESC LIMIT 1"
            ),
            {"oid": LATE_OUTCOME, "commence": COMMENCE},
        )
    ).scalar_one_or_none()

    assert picked is not None and float(picked) == TRUE_CLOSING, (
        "premise: the relaxed bound DOES reach a quote here, so the shipped "
        "bound refusing it is a real decision and not a vacuous one"
    )


@needs_postgres
@pytest.mark.asyncio
async def test_a_row_part_a2_already_repriced_is_never_examined(session):
    """The rail repairs an unreplaced stamp; it does not second-guess a price."""
    from app.tasks.repair_golf_round_closing_line import repair

    await _seed(session)
    result = await repair(session, apply=True)

    assert await _price(session, PRICED_OUTCOME) == 0.35
    seen = {r["outcome_id"] for r in result["planned"]} | {
        r["outcome_id"] for r in result["refused"]
    }
    assert PRICED_OUTCOME not in seen


@needs_postgres
@pytest.mark.asyncio
async def test_a_stamp_that_equals_its_closing_line_is_refused_not_rewritten(session):
    from app.tasks.repair_golf_round_closing_line import repair

    await _seed(session)
    result = await repair(session, apply=True)

    assert await _price(session, SAME_OUTCOME) == STAMP
    refusals = {r["outcome_id"]: r["reason"] for r in result["refused"]}
    assert refusals[SAME_OUTCOME] == "closing_equals_opening"


@needs_postgres
@pytest.mark.asyncio
async def test_tournament_scope_is_out_of_the_bound(session):
    """The well-calibrated cohort next door must not be touched."""
    from app.tasks.repair_golf_round_closing_line import repair

    await _seed(session)
    result = await repair(session, apply=True)

    assert await _price(session, TOURNEY_OUTCOME) == STAMP
    seen = {r["outcome_id"] for r in result["planned"]} | {
        r["outcome_id"] for r in result["refused"]
    }
    assert TOURNEY_OUTCOME not in seen


@needs_postgres
@pytest.mark.asyncio
async def test_the_repair_is_idempotent(session):
    """A second run finds nothing to do — the plan is self-limiting.

    Part A2's own churn history (#190, #1100) is a null -> opening -> null loop
    that blew the pipeline's soft limit. A repair that re-plans its own output
    would reintroduce exactly that.
    """
    from app.tasks.repair_golf_round_closing_line import repair

    await _seed(session)
    await repair(session, apply=True)
    second = await repair(session, apply=True)

    assert second["changed"] == 0
    assert not second["planned"]


@needs_postgres
@pytest.mark.asyncio
async def test_nulling_the_stamp_cannot_pass_this(session):
    """RED-FIRST. The obvious repair leaves the reader looking at 0.99.

    ``SET calibration_probability = NULL`` is what "just take the bad price out"
    means in this schema, and it is inert: the curve reads
    ``COALESCE(calibration_probability, opening_probability)``, so the leg falls
    straight back onto the same 0.99 stamp it was published with. Nulling is an
    exclusion only if the opening is also fiction and also removed — which
    destroys the captured opening.

    This arm executes that naive statement and requires the published price to
    be UNCHANGED. If it ever starts passing as a fix, the rail's own assertion
    (write the real closing line) has stopped being necessary.
    """
    from sqlalchemy import text

    await _seed(session)
    await session.execute(
        text(
            "UPDATE futures_outcomes SET calibration_probability = NULL "
            "WHERE id = :oid"
        ),
        {"oid": SUBJECT_OUTCOME},
    )
    await session.commit()

    assert await _price(session, SUBJECT_OUTCOME) is None, "the column did clear"
    assert await _curve_price(session, SUBJECT_OUTCOME) == STAMP, (
        "gotcha #144: the curve price is a COALESCE, not an exclusion — nulling "
        "the calibration price republishes the opening stamp unchanged"
    )
