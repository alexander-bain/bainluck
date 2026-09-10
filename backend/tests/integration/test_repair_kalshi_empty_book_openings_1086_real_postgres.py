"""#4745 (CAL-P1086)'s empty-book withdrawal, executed against a REAL PostgreSQL.

## what this guards, and why nothing cheaper would have caught it

CERT-2508 BLOCKed ``ece46743`` with a precise complaint: the guard it added only
affects rows where ``opening_probability IS NULL``, so the already-promoted
34,281 legs stay in the published curve. The required repair is named
``4745-PUBLISHED-EMPTY-BOOK-OPENINGS-ACTUALLY-LEAVE-THE-CURVE``, and the phrase
that matters is **LEAVE THE CURVE**. That is a claim about a stored row's effect
on ``COALESCE(calibration_probability, opening_probability)``, and only a server
that stores the row can observe it. Four of this rail's moving parts are
server-side and invisible to a mock:

* the bound turns on TWO correlated laterals over ``futures_odds_snapshots``,
  one taking the earliest snapshot and one taking the earliest snapshot the
  shipped guard accepts;
* the write re-derives that bound inside the ``UPDATE`` rather than trusting the
  plan's ids, and its ``CASE`` reads ``fo.opening_probability``'s PRE-update
  value to decide whether ``calibration_probability`` was a copy of it;
* ``Numeric(7,6)`` equality (``calibration_probability = opening_probability``,
  ``fo.opening_probability = bad.probability``) is a database comparison, not a
  Python one — a float round-trip makes 0.98 == 0.98 true in Python and can make
  it false in the column, and BOTH of this rail's safety clauses are that
  comparison;
* the "no re-promotion" claim is a claim about what ``backfill_winners``
  Phase 0c does to a row this repair just nulled, six hours later.

## the corpus, and what each row can fail on

Nine outcomes on three markets, each paired with the defect it catches.

* **the subject** (``MARNER``) — the production specimen. One snapshot, bid
  0.00 / ask 0.98 / no trade, ``opening_probability`` 0.98, no calibration
  price. Must end with a NULL curve price: it LEAVES the published curve,
  because no price for it ever existed.
* **the repriced leg** (``TRADED``) — same empty book at open, then a real
  two-sided book at 0.22. Must read back 0.22. This is the arm that proves the
  guard skips the ROW and not the OUTCOME.
* **the copy** (``COPY``) — ``calibration_probability`` is a verbatim copy of
  the discredited 0.98. Both columns must go NULL. Nulling only the opening
  would leave the curve reading 0.98 out of the other half of the COALESCE,
  which is the naive repair and is why ``test_nulling_only_the_opening_cannot
  _pass_this`` exists.
* **the independent price** (``INDEPENDENT``) — ``calibration_probability``
  0.34, opening 0.98. Its opening is repaired and its published price does NOT
  move. 52% of the production cohort is this arm, and the directive that staged
  this queue counted all of it as "published at 0.94". Measured, it publishes
  0.392. The ship must not claim it.
* **the lone-bid control** (``LONE_BID``) — bid 0.95, ask 1.00, no trade. Must
  not be examined. A lone bid is a price somebody will pay and grades 93.7% on
  production; refusing it would delete a well-calibrated cohort to fix a broken
  one.
* **the Polymarket control** (``POLYMARKET``) — byte-identical empty book,
  different venue. Must not be examined. This is CERT-2508's second finding
  (``f437204c``): Phase 0c reads every source's snapshots, Kalshi's write guard
  has refused this shape since 2026-07-13 so the Kalshi population is entirely
  historical, and the unscoped predicate was measured matching 0 Kalshi rows
  and 23 Polymarket rows in a 4-hour window — inert on the venue it was written
  for and live on the one it was not.
* **the provenance control** (``NO_PROVENANCE``) — earliest snapshot is a lone
  ask at 0.98, but the stored opening is 0.55, so something else wrote it. Must
  not be examined. Without this clause the rail would overwrite any row that
  merely HAS a bad earliest snapshot.
* **the no-op control** (``SAME_VALUE``) — a later honest book quotes the same
  0.98. Must be refused ``replacement_equals_stored`` and left alone, so
  ``changed`` counts rows that MOVED. 9 of 1,756 sampled production legs are
  this.
* **the unresolved control** (``UNRESOLVED``) — identical shape on an open
  market. Out of the bound: the curve grades resolved questions.

## the arms that prove red-first

``test_nulling_only_the_opening_cannot_pass_this`` executes the repair a
reviewer reaches for first — null ``opening_probability`` and let the curve fall
back — and requires the copy leg's published price to STAY at 0.98. It does,
because the curve price is a COALESCE, not an exclusion (gotcha #144 /
ruling 103). A green run of this file therefore means writing both columns was
proved NECESSARY, not that nothing objected.

``test_phase_0c_does_not_re_promote_a_withdrawn_row`` runs the SHIPPED Phase 0c
statement immediately after the repair, and carries its own positive control:
a separate outcome with a NULL opening and an honest snapshot, which Phase 0c
must promote in the same execution. Without that control a Phase 0c that did
nothing at all — a typo, a rolled-back transaction, a predicate that matched
nothing — would read exactly like a Phase 0c that correctly left the withdrawn
row alone.
"""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone

import pytest

DB_URL = os.environ.get("SEARCH_TEST_DATABASE_URL")

needs_postgres = pytest.mark.skipif(
    not DB_URL,
    reason=(
        "set SEARCH_TEST_DATABASE_URL to run the real-Postgres #4745 empty-book "
        "withdrawal gate (CI job `search-recall` provides one)"
    ),
)

OPEN_TIME = datetime(2026, 4, 2, 17, 0, 0, tzinfo=timezone.utc)

KALSHI_MARKET = 9174501
OPEN_MARKET = 9174502
PM_MARKET = 9174503

MARNER = 9174601
TRADED = 9174602
COPY = 9174603
INDEPENDENT = 9174604
LONE_BID = 9174605
POLYMARKET = 9174606
NO_PROVENANCE = 9174607
SAME_VALUE = 9174608
UNRESOLVED = 9174609
#: Phase 0c's positive control — never in this rail's bound, only in the
#: re-promotion gate, where it proves the phase ran at all.
PHASE_0C_CONTROL = 9174610

#: The production specimen: *Mitch Marner: 3+ points*, bid 0.00 / ask 0.98 /
#: last 0.00, published 0.98.
BAD_ASK = 0.98
#: The real two-sided book that arrives later on the leg that did trade.
HONEST = 0.22
#: An independently-derived calibration price (production arm c mean: 0.392).
INDEPENDENT_PRICE = 0.34


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
        # The backup table is created by the rail, outside Base.metadata, so
        # `drop_all` on the NEXT test's setup would not remove it and its rows
        # would leak into that test's restore.
        from sqlalchemy import text

        from app.tasks.repair_kalshi_empty_book_openings import BAK_TABLE

        await s.execute(text(f"DROP TABLE IF EXISTS {BAK_TABLE}"))
        await s.commit()
    await engine.dispose()


async def _seed(session):
    """Insert the corpus through the ORM.

    The ORM and not raw INSERT: both tables carry client-side defaults a raw
    INSERT does not apply, and `test_pg_gate_seed_completeness.py`'s raw-INSERT
    arm keys on the presence of `INSERT INTO`.
    """
    from app.models import FuturesMarket, FuturesOddsSnapshot, FuturesOutcome

    for mid, status, source in (
        (KALSHI_MARKET, "resolved", "kalshi"),
        (OPEN_MARKET, "open", "kalshi"),
        (PM_MARKET, "resolved", "polymarket"),
    ):
        session.add(
            FuturesMarket(
                id=mid,
                source=source,
                external_id=f"seed-market-{mid}",
                name=f"seed {mid}",
                llm_sport_category="hockey",
                status=status,
                event_id=None,
                commence_time=OPEN_TIME + timedelta(hours=6),
            )
        )

    # (outcome_id, market, opening, opening_source, calibration)
    outcomes = (
        (MARNER, KALSHI_MARKET, BAD_ASK, "first_snapshot", None),
        (TRADED, KALSHI_MARKET, BAD_ASK, "first_snapshot", None),
        (COPY, KALSHI_MARKET, BAD_ASK, "first_snapshot", BAD_ASK),
        (INDEPENDENT, KALSHI_MARKET, BAD_ASK, "first_snapshot", INDEPENDENT_PRICE),
        (LONE_BID, KALSHI_MARKET, 0.95, "first_snapshot", None),
        (POLYMARKET, PM_MARKET, BAD_ASK, "first_snapshot", None),
        (NO_PROVENANCE, KALSHI_MARKET, 0.55, "first_snapshot", None),
        (SAME_VALUE, KALSHI_MARKET, BAD_ASK, "first_snapshot", None),
        (UNRESOLVED, OPEN_MARKET, BAD_ASK, "first_snapshot", None),
        (PHASE_0C_CONTROL, KALSHI_MARKET, None, None, None),
    )
    for oid, mid, opening, source, cal in outcomes:
        session.add(
            FuturesOutcome(
                id=oid,
                market_id=mid,
                external_id=f"seed-{oid}",
                name=f"Skater {oid}",
                opening_probability=opening,
                opening_source=source,
                calibration_probability=cal,
                is_winner=False,
                resolution_source="api_settlement",
            )
        )

    # (outcome, bookmaker, probability, yes_bid, yes_ask, last_price, offset)
    empty_book = (0.0, BAD_ASK, 0.0)
    real_book = (0.20, 0.24, 0.21)
    snapshots = (
        # The subject: one empty book, and nothing else, ever.
        (MARNER, "kalshi", BAD_ASK, *empty_book, timedelta(0)),
        # Opened empty, then traded. The guard skips the ROW, not the outcome.
        (TRADED, "kalshi", BAD_ASK, *empty_book, timedelta(0)),
        (TRADED, "kalshi", HONEST, *real_book, timedelta(hours=1)),
        (COPY, "kalshi", BAD_ASK, *empty_book, timedelta(0)),
        (INDEPENDENT, "kalshi", BAD_ASK, *empty_book, timedelta(0)),
        # A lone BID is a price: 0.949 mean, 93.7% realised on production.
        (LONE_BID, "kalshi", 0.95, 0.95, 1.00, 0.0, timedelta(0)),
        # Byte-identical empty book, different venue, different policy.
        (POLYMARKET, "polymarket", BAD_ASK, *empty_book, timedelta(0)),
        # Bad earliest snapshot, but the stored opening did not come from it.
        (NO_PROVENANCE, "kalshi", BAD_ASK, *empty_book, timedelta(0)),
        # A real book arrives later quoting the SAME number.
        (SAME_VALUE, "kalshi", BAD_ASK, *empty_book, timedelta(0)),
        (SAME_VALUE, "kalshi", BAD_ASK, 0.97, 0.99, 0.98, timedelta(hours=1)),
        (UNRESOLVED, "kalshi", BAD_ASK, *empty_book, timedelta(0)),
        # Phase 0c's positive control: an honest book on a NULL-opening leg.
        (PHASE_0C_CONTROL, "kalshi", HONEST, *real_book, timedelta(0)),
    )
    for oid, book, prob, bid, ask, last, delta in snapshots:
        session.add(
            FuturesOddsSnapshot(
                outcome_id=oid,
                bookmaker=book,
                probability=prob,
                yes_bid=bid,
                yes_ask=ask,
                last_price=last,
                captured_at=OPEN_TIME + delta,
            )
        )
    await session.commit()


async def _row(session, outcome_id: int):
    """``(curve_price, opening, opening_source, calibration)`` as stored.

    ``curve_price`` is the producer's own expression,
    ``COALESCE(calibration_probability, opening_probability)`` — the thing a
    reader is shown, and the only column-combination this ship's claim is about.
    """
    from sqlalchemy import text

    got = (
        await session.execute(
            text(
                "SELECT COALESCE(calibration_probability, opening_probability), "
                "opening_probability, opening_source, calibration_probability "
                "FROM futures_outcomes WHERE id = :oid"
            ),
            {"oid": outcome_id},
        )
    ).one()
    return (
        None if got[0] is None else float(got[0]),
        None if got[1] is None else float(got[1]),
        got[2],
        None if got[3] is None else float(got[3]),
    )


@needs_postgres
@pytest.mark.asyncio
async def test_a_leg_that_never_had_a_price_leaves_the_published_curve(session):
    """The ship, in the words CERT-2508 used: it LEAVES THE CURVE."""
    from app.tasks.repair_kalshi_empty_book_openings import repair

    await _seed(session)
    assert (await _row(session, MARNER))[0] == BAD_ASK, "seed precondition"

    result = await repair(session, apply=True)

    curve, opening, source, cal = await _row(session, MARNER)
    assert curve is None, (
        "the leg still has a published price — a guard that nulls one half of a "
        "COALESCE has not removed anything"
    )
    assert (opening, source, cal) == (None, None, None)
    assert result["terminal"] == "changed"
    assert result["leaves_the_curve"] >= 1


@needs_postgres
@pytest.mark.asyncio
async def test_a_leg_that_later_traded_keeps_its_first_real_price(session):
    """The guard skips the ROW, not the OUTCOME.

    Moving it out of the lateral's WHERE would drop this whole leg instead of
    one snapshot — a silent over-withdrawal that the census could not show,
    because the leg would simply never appear.
    """
    from app.tasks.repair_kalshi_empty_book_openings import repair

    await _seed(session)
    await repair(session, apply=True)

    curve, opening, source, _ = await _row(session, TRADED)
    assert (curve, opening, source) == (HONEST, HONEST, "first_snapshot")


@needs_postgres
@pytest.mark.asyncio
async def test_a_calibration_price_that_copies_the_bad_opening_goes_too(session):
    from app.tasks.repair_kalshi_empty_book_openings import repair

    await _seed(session)
    await repair(session, apply=True)

    assert await _row(session, COPY) == (None, None, None, None)


@needs_postgres
@pytest.mark.asyncio
async def test_nulling_only_the_opening_cannot_pass_this(session):
    """Red-first: the repair a reviewer reaches for leaves the price on screen.

    ``COALESCE(calibration_probability, opening_probability)`` is a coalesce,
    not an exclusion (gotcha #144 / ruling 103). Nulling the opening on a leg
    whose calibration price is a copy of it changes the stored row and changes
    NOTHING a reader sees. This arm is why the rail writes two columns, and it
    fails the day somebody simplifies it to one.
    """
    from sqlalchemy import text

    await _seed(session)
    await session.execute(
        text(
            "UPDATE futures_outcomes SET opening_probability = NULL, "
            "opening_source = NULL WHERE id = :oid"
        ),
        {"oid": COPY},
    )
    await session.commit()

    curve, _, _, _ = await _row(session, COPY)
    assert curve == BAD_ASK, (
        "the naive repair was supposed to leave 0.98 published — if it does "
        "not, this gate is no longer proving the two-column write necessary"
    )


@needs_postgres
@pytest.mark.asyncio
async def test_an_independent_calibration_price_does_not_move(session):
    """52% of the production cohort, and the ship does not claim it.

    The opening is repaired because it is just as false; the published price is
    untouched because the curve never read it. A rail that also rewrote this
    leg's calibration price would be inventing an opinion about a number
    somebody else derived.
    """
    from app.tasks.repair_kalshi_empty_book_openings import repair

    await _seed(session)
    await repair(session, apply=True)

    curve, opening, source, cal = await _row(session, INDEPENDENT)
    assert (curve, cal) == (INDEPENDENT_PRICE, INDEPENDENT_PRICE)
    assert (opening, source) == (None, None)


@needs_postgres
@pytest.mark.asyncio
@pytest.mark.parametrize(
    "outcome_id, why",
    [
        (LONE_BID, "a lone bid is a price somebody will pay; 93.7% realised"),
        (POLYMARKET, "a different venue's policy for the same three columns"),
        (NO_PROVENANCE, "the stored opening did not come from that snapshot"),
        (UNRESOLVED, "the curve grades resolved questions"),
    ],
)
async def test_the_controls_are_never_examined(session, outcome_id, why):
    from app.tasks.repair_kalshi_empty_book_openings import repair

    await _seed(session)
    before = await _row(session, outcome_id)

    await repair(session, apply=True)

    assert await _row(session, outcome_id) == before, why


@needs_postgres
@pytest.mark.asyncio
async def test_a_replacement_equal_to_the_stored_value_is_refused_not_counted(
    session,
):
    """`changed` must count rows that MOVED, on real Numeric(7,6) equality."""
    from app.tasks.repair_kalshi_empty_book_openings import (
        REASON_REPLACEMENT_EQUALS_STORED,
        repair,
    )

    await _seed(session)
    before = await _row(session, SAME_VALUE)

    result = await repair(session, apply=True)

    assert await _row(session, SAME_VALUE) == before
    assert any(
        r["outcome_id"] == SAME_VALUE
        and r["reason"] == REASON_REPLACEMENT_EQUALS_STORED
        for r in result["refusals"]
    )


@needs_postgres
@pytest.mark.asyncio
async def test_phase_0c_does_not_re_promote_a_withdrawn_row(session):
    """The repair's result is a FIXED POINT of the live promotion.

    This is the whole reason the fix is a one-off rail and not a re-deriving
    Phase 0c. A withdrawn row IS examined by Phase 0c — its opening is NULL —
    and its guarded lateral finds no honest snapshot, so the ``CROSS JOIN
    LATERAL`` drops the outcome and nothing is written.

    The positive control is load-bearing: a Phase 0c that did nothing at all
    would pass the withdrawn-row assertion perfectly.
    """
    import importlib
    import sys

    from sqlalchemy import text

    from app.tasks.repair_kalshi_empty_book_openings import repair

    importlib.import_module("app.tasks.backfill_winners")
    phase_0c = sys.modules["app.tasks.backfill_winners"].PHASE_0C_REPAIR_SQL

    await _seed(session)
    await repair(session, apply=True)
    assert (await _row(session, MARNER)) == (None, None, None, None)

    await session.execute(text(phase_0c))
    await session.commit()

    assert (await _row(session, PHASE_0C_CONTROL))[1] == HONEST, (
        "Phase 0c promoted nothing at all — the withdrawn-row assertion below "
        "would be vacuous"
    )
    assert (await _row(session, MARNER)) == (None, None, None, None), (
        "Phase 0c re-promoted a withdrawn row: the repair is not a fixed point "
        "and the curve reverts within one 6-hour cycle"
    )


@needs_postgres
@pytest.mark.asyncio
async def test_running_the_repair_twice_changes_nothing_the_second_time(session):
    """Idempotence, from the bound rather than from a flag.

    After the write a repaired row's stored opening is the honest value or NULL,
    so ``fo.opening_probability = bad.probability`` no longer holds and the row
    is not in its own population. Nothing has to remember that it ran.
    """
    from app.tasks.repair_kalshi_empty_book_openings import repair

    await _seed(session)
    first = await repair(session, apply=True)
    snapshot = {oid: await _row(session, oid) for oid in (MARNER, TRADED, COPY)}

    second = await repair(session, apply=True)

    assert first["changed"] > 0
    assert second["changed"] == 0
    assert {oid: await _row(session, oid) for oid in snapshot} == snapshot


@needs_postgres
@pytest.mark.asyncio
async def test_the_restore_puts_every_row_back_exactly(session):
    """D51: the undo is one call, and it is exact on all three columns."""
    from app.tasks.repair_kalshi_empty_book_openings import repair, restore

    await _seed(session)
    watched = (MARNER, TRADED, COPY, INDEPENDENT, SAME_VALUE)
    before = {oid: await _row(session, oid) for oid in watched}

    await repair(session, apply=True)
    assert {oid: await _row(session, oid) for oid in watched} != before

    result = await restore(session, apply=True)

    assert result["terminal"] == "restored"
    assert {oid: await _row(session, oid) for oid in watched} == before
    # A second restore is a no-op, not a rewrite: `IS DISTINCT FROM` is what
    # makes the reported count mean "rows actually put back".
    assert (await restore(session, apply=True))["restored"] == 0


@needs_postgres
@pytest.mark.asyncio
async def test_the_backup_is_written_in_the_same_transaction_as_the_write(session):
    """A backup on its own connection is a lie waiting for a crash.

    Every row the apply changed must have a backup row after the commit, and the
    gate is a count of uncovered rows rather than a comparison of two totals —
    two totals can agree while naming different rows.
    """
    from sqlalchemy import text

    from app.tasks.repair_kalshi_empty_book_openings import BAK_TABLE, repair

    await _seed(session)
    result = await repair(session, apply=True)

    uncovered = (
        await session.execute(
            text(
                f"SELECT count(*) FROM futures_outcomes fo "
                f"WHERE fo.id IN (:a, :b, :c) "
                f"AND NOT EXISTS (SELECT 1 FROM {BAK_TABLE} b "
                f"WHERE b.outcome_id = fo.id)"
            ),
            {"a": MARNER, "b": TRADED, "c": COPY},
        )
    ).scalar_one()

    assert result["changed"] >= 3
    assert uncovered == 0


@needs_postgres
@pytest.mark.asyncio
async def test_a_dry_run_writes_nothing_and_creates_no_backup_table(session):
    """The default is a plan. A rail that half-applies on a dry run is worse
    than one that refuses, because the operator believes nothing happened."""
    from sqlalchemy import text

    from app.tasks.repair_kalshi_empty_book_openings import BAK_TABLE, repair

    await _seed(session)
    before = {oid: await _row(session, oid) for oid in (MARNER, TRADED, COPY)}

    result = await repair(session)

    assert result["terminal"] == "dry_run"
    assert result["changed"] == 0
    assert result["examined"] >= 5
    assert {oid: await _row(session, oid) for oid in before} == before
    exists = (
        await session.execute(text(f"SELECT to_regclass('{BAK_TABLE}')"))
    ).scalar_one()
    assert exists is None


@needs_postgres
@pytest.mark.asyncio
async def test_paging_walks_the_population_and_reports_its_own_exhaustion(session):
    """A page that repairs its rows removes them from its own bound.

    So `scan_exhausted` — "this page found fewer rows than it asked for" — is
    the only honest end-of-walk signal, and a remaining count would be fiction.
    """
    from app.tasks.repair_kalshi_empty_book_openings import repair

    await _seed(session)

    first = await repair(session, apply=True, limit=1)
    assert first["changed"] == 1
    assert first["scan_exhausted"] is False
    assert first["next_after_id"] is not None

    seen = 1
    after = first["next_after_id"]
    while True:
        page = await repair(session, apply=True, limit=1, after_id=after)
        if page["examined"] == 0:
            break
        seen += page["changed"]
        after = page["next_after_id"]

    # MARNER, TRADED, COPY, INDEPENDENT — SAME_VALUE is refused, not changed.
    assert seen == 4
