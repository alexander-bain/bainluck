"""Queue #259 — Postgres-backed contract test for the canonical calibration CTE.

This executes the REAL relational logic (``_calibration_population_ctes`` — the
Postgres-only CTE chain that both ``/api/calibration`` and the cohort sweep build
on) against seeded counter-class rows and proves the sum-to-1 invariant + serve/
sweep row identity end to end.

It is SKIPPED unless a throwaway Postgres is reachable via
``CALIBRATION_TEST_DATABASE_URL`` (an ``postgresql+asyncpg://`` URL to a database
the test may create/drop tables in). CI has no Postgres service and the dev
sandbox blocks shared memory, so this cannot run there — the always-on proof is
the Python mirror in ``test_calibration_field_completeness_259.py``; this test is
the durable gold-standard guard for any environment that DOES have Postgres:

    CALIBRATION_TEST_DATABASE_URL=postgresql+asyncpg://localhost/bl_caltest \\
        python3 -m pytest tests/test_calibration_canonical_pg.py -v
"""

import os

import pytest

DB_URL = os.environ.get("CALIBRATION_TEST_DATABASE_URL")

pytestmark = pytest.mark.skipif(
    not DB_URL, reason="set CALIBRATION_TEST_DATABASE_URL to run the real-CTE contract test"
)


async def _seed_field(session, market_id, source, cps, winner_idx):
    """Seed one resolved field market with ``cps`` outcomes + liquidity snapshots."""
    from sqlalchemy import text

    await session.execute(
        text(
            "INSERT INTO futures_markets (id, source, status, mutually_exclusive, "
            "market_type, llm_sport_category, volume) VALUES "
            "(:id, :src, 'resolved', true, 'field', 'politics', 100)"
        ),
        {"id": market_id, "src": source},
    )
    for i, cp in enumerate(cps):
        oid = market_id * 1000 + i
        await session.execute(
            text(
                "INSERT INTO futures_outcomes (id, market_id, name, opening_probability, "
                "calibration_probability, is_winner, resolution_source, volume) VALUES "
                "(:id, :mid, :nm, :op, :cp, :win, 'api_settlement', 10)"
            ),
            {
                "id": oid,
                "mid": market_id,
                "nm": f"cand-{i}",
                "op": cp,
                "cp": cp,
                "win": (i == winner_idx),
            },
        )
        # A trade so kalshi/poly liquidity predicates pass (last_price > 0).
        await session.execute(
            text(
                "INSERT INTO futures_odds_snapshots (outcome_id, last_price, yes_bid) "
                "VALUES (:oid, :lp, :lp)"
            ),
            {"oid": oid, "lp": max(cp, 0.001)},
        )


@pytest.mark.asyncio
async def test_complete_field_publishes_whole_partition_summing_to_one():
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    from app.models.models import Base
    from app.tasks.precompute_calibration import _calibration_population_ctes

    engine = create_async_engine(DB_URL)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    Session = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with Session() as session:
            # The C14 counterexample: a complete 0.99/0.20/0.001 field (cp_sum 1.191).
            await _seed_field(session, 90001, "polymarket", [0.99, 0.20, 0.001], winner_idx=0)
            await session.commit()

            sql = text(
                "WITH "
                + _calibration_population_ctes()
                + " SELECT market_id, adj_opening_probability AS p, is_mex_normalized, "
                "vm_id AS question_id, outcome_id, is_winner FROM deduped "
                "WHERE market_id = 90001 ORDER BY p DESC"
            )
            rows = (await session.execute(sql)).all()

            # INVARIANT: all three members published, partition sums to ~1.0.
            assert len(rows) == 3, f"expected whole partition, got {len(rows)}"
            assert all(r.is_mex_normalized for r in rows)
            assert abs(sum(float(r.p) for r in rows) - 1.0) < 1e-6
            # exactly one question id (size-gated vm identity), one winner.
            assert len({r.question_id for r in rows}) == 1
            assert sum(1 for r in rows if r.is_winner) == 1

            # ROW IDENTITY: the sweep loader returns the same members/probabilities.
            from scripts.evals.cohort_sweep import load_from_session

            sweep_rows = [r for r in await load_from_session(session) if r["market_id"] == 90001]
            assert len(sweep_rows) == 3
            assert abs(sum(float(r["probability"]) for r in sweep_rows) - 1.0) < 1e-6
            payload_ids = {r.outcome_id for r in rows}
            assert {r["outcome_id"] for r in sweep_rows} == payload_ids
    finally:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)
        await engine.dispose()
