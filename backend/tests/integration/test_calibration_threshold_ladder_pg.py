"""#5305 — a cumulative threshold ladder is ONE forecast, proved on ROWS.

Kalshi ``KXA100MON-26APR30`` ("Price of NVIDIA A100 compute by Apr 30, 2026")
carries 40 rungs — "Above $0.77" through "Above $1.15" — whose opening prices run
0.965 down to 0.06 and SUM TO 19.275, with 38 of the 40 resolving true. Those are
40 nested readings of one number. ``deduped`` published essentially all of them,
because ``is_multi`` is ``(is_grouped OR eligible >= 3)`` and a lone 40-outcome
market satisfies the second arm, so one question contributed ~36 correlated rows —
most of them winners priced well under 1.0 — to one cell's ECE.

WHY THIS IS A POSTGRES TEST AND NOT A UNIT TEST
-----------------------------------------------
The defect is in which ROWS the CTE chain selects, not in any Python predicate.
Every existing guard around this file asserts rendered SQL text or a Python
mirror, and all of them were green while the 40 rungs were publishing. That is
the same gap CERT-751 blocked #2637's first attempt for. So this executes the
REAL ``_calibration_population_ctes`` against seeded rows and asserts the
published set both ways.

THE CONTROL CASE IS THE POINT
-----------------------------
``market_type='quantity'`` covers TWO different objects, and only one of them is
the defect:

    cumulative ladder   "Above $0.77" .. "Above $1.15"   nested, many true, sum >>1
    exclusive bins      "peaks at #1" / "#2-5" / "#6-10"  disjoint, one true, sum ~1

A distribution over disjoint bins is legitimately N forecasts. Neither can reach
the partition arm (``exclusivity_proved_sql`` requires ``market_type='field'``),
so collapsing on shape alone would have deleted well-formed data — measured, in
the very cell this ships for: kalshi/entertainment holds 507 co-winner ladders
against 651 single-winner bin markets. Hence the ``win_count > 1`` discriminator,
and hence ``test_exclusive_bins_still_publish_every_member``, which fails if the
arm ever widens back to shape alone.

Opt-in on ``SEARCH_TEST_DATABASE_URL``, and NAMED IN ``ci.yml`` — a PG-gated file
that no workflow step invokes skips silently and pytest still exits 0, which is
how #2637's "proven on rows" claim came to be made about tests that had never
run. ``test_ci_names_every_pg_gated_integration_test`` guards that class.
"""

from __future__ import annotations

import os

import pytest
from sqlalchemy import text

DB_URL = os.environ.get("SEARCH_TEST_DATABASE_URL")

pytestmark = [
    pytest.mark.asyncio,
    pytest.mark.skipif(
        not DB_URL,
        reason="set SEARCH_TEST_DATABASE_URL to run the real-Postgres #5305 ladder contract",
    ),
]

# Market ids well clear of anything the sibling PG gates seed.
LADDER_MID = 952101
BINS_MID = 952102


async def _seed_market(session, market_id, *, market_type, category="tech"):
    await session.execute(
        text(
            "INSERT INTO futures_markets (id, source, status, mutually_exclusive, "
            "market_type, llm_sport_category, volume) VALUES "
            "(:id, 'kalshi', 'resolved', true, :mt, :cat, 100)"
        ),
        {"id": market_id, "mt": market_type, "cat": category},
    )


async def _seed_outcome(session, market_id, idx, name, prob, *, winner):
    """One resolved outcome plus the bid evidence the Kalshi liquidity predicate
    keys on (#940: a real yes_bid, not the volume proxy)."""
    oid = market_id * 100 + idx
    await session.execute(
        text(
            "INSERT INTO futures_outcomes (id, market_id, name, opening_probability, "
            "calibration_probability, is_winner, resolution_source, volume) VALUES "
            "(:id, :mid, :nm, :p, :p, :win, 'api_settlement', 10)"
        ),
        {"id": oid, "mid": market_id, "nm": name, "p": prob, "win": winner},
    )
    await session.execute(
        text(
            "INSERT INTO futures_odds_snapshots (outcome_id, last_price, yes_bid) "
            "VALUES (:oid, :p, :p)"
        ),
        {"oid": oid, "p": prob},
    )
    return oid


async def _seeded_session():
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    from app.models.models import Base

    engine = create_async_engine(DB_URL)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    Session = async_sessionmaker(engine, expire_on_commit=False)
    return engine, Session


async def _populate(session):
    """A cumulative ladder and a disjoint-bin market, side by side.

    Both are ``quantity``, both are lone markets with 5 eligible outcomes, both
    are ``is_multi``. The ONLY thing separating them is winner cardinality.
    """
    # (A) cumulative ladder: nested thresholds, FOUR of five true, prices sum 2.50.
    await _seed_market(session, LADDER_MID, market_type="quantity")
    ladder_ids = {}
    for idx, (name, prob, win) in enumerate(
        [
            ("Above $0.80", 0.90, True),
            ("Above $0.90", 0.70, True),
            ("Above $1.00", 0.50, True),
            ("Above $1.10", 0.30, True),
            ("Above $1.20", 0.10, False),
        ]
    ):
        ladder_ids[name] = await _seed_outcome(
            session, LADDER_MID, idx, name, prob, winner=win
        )

    # (B) exclusive bins: disjoint ranges, EXACTLY ONE true, prices sum 1.00.
    await _seed_market(session, BINS_MID, market_type="quantity")
    bin_ids = {}
    for idx, (name, prob, win) in enumerate(
        [
            ("Peaks at #1", 0.40, False),
            ("Peaks #2-5", 0.25, True),
            ("Peaks #6-10", 0.15, False),
            ("Peaks #11-25", 0.12, False),
            ("Peaks #26+", 0.08, False),
        ]
    ):
        bin_ids[name] = await _seed_outcome(
            session, BINS_MID, idx, name, prob, winner=win
        )

    await session.commit()
    return ladder_ids, bin_ids


async def _rows(session, cte_name, market_id):
    from app.tasks.precompute_calibration import _calibration_population_ctes

    ctes = _calibration_population_ctes()
    result = await session.execute(
        text(
            "WITH "
            + ctes
            + f" SELECT outcome_id, outcome_name, adj_opening_probability AS p"
            f" FROM {cte_name} WHERE market_id = :mid ORDER BY outcome_id"
        ),
        {"mid": market_id},
    )
    return result.all()


async def test_cumulative_ladder_publishes_exactly_one_representative():
    """The defect, on rows: five nested rungs collapse to ONE published forecast.

    Also asserts the representative is the rung nearest 50% — the SAME authority
    the single-market ELSE arm already uses (Alex's 2026-08-03 tie ruling), so the
    ladder is not given a bespoke selection rule.
    """
    engine, Session = await _seeded_session()
    try:
        async with Session() as session:
            await _populate(session)

            # NON-VACUITY FIRST. Every rung must be a live candidate in
            # ``normalized`` — liquid, truth-eligible, un-excluded. If the fixture
            # were failing the liquidity or truth gates, ``deduped`` would hold one
            # row (or none) for reasons that have nothing to do with this arm and
            # the assertion below would pass while proving nothing.
            candidates = await _rows(session, "normalized", LADDER_MID)
            assert len(candidates) == 5, (
                f"fixture is not exercising the arm: expected 5 ladder candidates in "
                f"normalized, got {len(candidates)}"
            )

            published = await _rows(session, "deduped", LADDER_MID)
            assert len(published) == 1, (
                f"a cumulative ladder published {len(published)} forecasts; "
                f"one question must publish one: {[r.outcome_name for r in published]}"
            )
            assert published[0].outcome_name == "Above $1.00", (
                "the representative must be the rung nearest 50%, not an arbitrary "
                f"tied row; got {published[0].outcome_name}"
            )
        await _cleanup(Session)
    finally:
        await engine.dispose()


async def test_exclusive_bins_still_publish_every_member():
    """The control: a disjoint-bin distribution is N forecasts and STAYS N.

    This is the assertion that fails if the arm is ever widened to
    ``market_type='quantity'`` alone. On the shipped cells that widening would
    have collapsed 651 single-winner Kalshi entertainment markets — real,
    well-formed calibration data — so the co-winner discriminator is load-bearing
    and not a refinement.
    """
    engine, Session = await _seeded_session()
    try:
        async with Session() as session:
            await _populate(session)

            published = await _rows(session, "deduped", BINS_MID)
            assert len(published) == 5, (
                "a single-winner disjoint-bin market is a distribution and every "
                f"member is its own forecast; got {len(published)}: "
                f"{[r.outcome_name for r in published]}"
            )
            total = sum(float(r.p) for r in published)
            assert 0.98 < total < 1.02, (
                f"the bin distribution should still sum to ~1.0; got {total}"
            )
        await _cleanup(Session)
    finally:
        await engine.dispose()


async def test_ladder_receipt_counts_the_rungs_it_suppressed():
    """gotcha #53: a guard that reports nothing is indistinguishable from a dead
    one. ``threshold_ladder.rungs_suppressed`` must count the work actually done —
    four suppressed rungs for the five-rung ladder, and the bin market must
    contribute nothing to it.
    """
    engine, Session = await _seeded_session()
    try:
        async with Session() as session:
            await _populate(session)

            from app.tasks.precompute_calibration import _calibration_population_ctes

            ctes = _calibration_population_ctes()
            row = (
                await session.execute(
                    text(
                        "WITH "
                        + ctes
                        + """
                        SELECT
                          COUNT(DISTINCT vm_id) FILTER (WHERE is_threshold_ladder)
                            AS questions,
                          COUNT(*) FILTER (WHERE is_threshold_ladder AND rn <> 1)
                            AS suppressed,
                          COUNT(*) FILTER (WHERE is_threshold_ladder
                                             AND market_id = :bins) AS bins_flagged
                        FROM ranked_outcomes
                        WHERE market_id IN (:ladder, :bins)
                        """
                    ),
                    {"ladder": LADDER_MID, "bins": BINS_MID},
                )
            ).one()

            assert row.questions == 1, (
                f"exactly one seeded market is a ladder; got {row.questions}"
            )
            assert row.suppressed == 4, (
                f"five rungs minus one representative is four suppressed; got "
                f"{row.suppressed} — a zero here means the arm never matched"
            )
            assert row.bins_flagged == 0, (
                "the single-winner bin market must never be flagged as a ladder"
            )
        await _cleanup(Session)
    finally:
        await engine.dispose()


async def _cleanup(Session):
    async with Session() as session:
        await session.execute(
            text(
                "DELETE FROM futures_odds_snapshots WHERE outcome_id IN "
                "(SELECT id FROM futures_outcomes WHERE market_id = ANY(:ids))"
            ),
            {"ids": [LADDER_MID, BINS_MID]},
        )
        await session.execute(
            text("DELETE FROM futures_outcomes WHERE market_id = ANY(:ids)"),
            {"ids": [LADDER_MID, BINS_MID]},
        )
        await session.execute(
            text("DELETE FROM futures_markets WHERE id = ANY(:ids)"),
            {"ids": [LADDER_MID, BINS_MID]},
        )
        await session.commit()
