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


async def _seed_liquidity_outcome(
    session,
    outcome_id,
    *,
    source,
    volume,
    yes_bid=None,
    last_price=None,
    cp=0.60,
    snapshot=True,
):
    """Seed one resolved single-winner market whose ONE outcome carries a
    specific (volume, bid/trade-evidence) combination (Queue #267 / C44 #1).

    Each scenario lives in its own market (market_id == outcome_id) so it is an
    ungrouped single question (is_multi False), the winner survives ``clean_vms``
    (has_winner >= 1), and ``deduped`` keeps exactly that outcome when — and only
    when — the per-source liquidity predicate admits it. ``volume`` is the
    OUTCOME-level ``fo.volume`` the retired #827 gate keyed on; ``yes_bid`` /
    ``last_price`` are the snapshot evidence #940's predicate keys on. Pass
    ``snapshot=False`` for a row that never showed any snapshot at all.
    """
    from sqlalchemy import text

    await session.execute(
        text(
            "INSERT INTO futures_markets (id, source, status, mutually_exclusive, "
            "market_type, llm_sport_category, volume) VALUES "
            "(:id, :src, 'resolved', false, 'binary', 'politics', 100)"
        ),
        {"id": outcome_id, "src": source},
    )
    await session.execute(
        text(
            "INSERT INTO futures_outcomes (id, market_id, name, opening_probability, "
            "calibration_probability, is_winner, resolution_source, volume) VALUES "
            "(:id, :mid, :nm, :op, :cp, true, 'api_settlement', :vol)"
        ),
        {
            "id": outcome_id,
            "mid": outcome_id,
            "nm": f"o-{outcome_id}",
            "op": cp,
            "cp": cp,
            "vol": volume,
        },
    )
    if snapshot:
        await session.execute(
            text(
                "INSERT INTO futures_odds_snapshots (outcome_id, last_price, yes_bid) "
                "VALUES (:oid, :lp, :yb)"
            ),
            {"oid": outcome_id, "lp": last_price or 0, "yb": yes_bid or 0},
        )


@pytest.mark.asyncio
async def test_liquidity_eligibility_matches_evidence_not_volume():
    """Queue #267 (C44 #1): the retired ``volume=0`` gate no longer pre-empts the
    Kalshi bid/trade evidence predicate, and the exclusion counts are taken over a
    population that STILL CONTAINS every candidate.

    Asserts EXACT ``deduped`` outcome IDs and EXACT liquidity counters (not source
    strings) across the full volume x evidence matrix + Polymarket counterparts.
    """
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
            # --- Kalshi: volume is irrelevant; bid/trade EVIDENCE decides. -------
            # K1 zero-volume + real BID  -> liquid (the exact C44 #1 counterexample)
            await _seed_liquidity_outcome(session, 91001, source="kalshi", volume=0, yes_bid=0.3)
            # K2 zero-volume + real TRADE -> liquid
            await _seed_liquidity_outcome(session, 91002, source="kalshi", volume=0, last_price=0.4)
            # K3 zero-volume + snapshot with NO real bid/trade -> illiquid (#827 fake-ask)
            await _seed_liquidity_outcome(session, 91003, source="kalshi", volume=0)
            # K4 NULL-volume + NO snapshot at all -> illiquid
            await _seed_liquidity_outcome(session, 91004, source="kalshi", volume=None, snapshot=False)
            # K5 NONZERO-volume + no evidence -> illiquid (volume can't rescue no-evidence)
            await _seed_liquidity_outcome(session, 91005, source="kalshi", volume=5)
            # K6 nonzero-volume + real trade -> liquid (ordinary traded row)
            await _seed_liquidity_outcome(session, 91006, source="kalshi", volume=5, last_price=0.5)
            # --- Polymarket: declared placeholder-band policy is preserved. -------
            # P1 zero-volume, never-traded, OUTSIDE the [0.45,0.55] band -> INCLUDED
            #    (the volume gate used to wrongly drop this; declared poly policy keeps it)
            await _seed_liquidity_outcome(session, 91007, source="polymarket", volume=0, cp=0.20, snapshot=False)
            # P2 zero-volume, never-traded, INSIDE the band -> placeholder-excluded
            await _seed_liquidity_outcome(session, 91008, source="polymarket", volume=0, cp=0.50, snapshot=False)
            await session.commit()

            ids = list(range(91001, 91009))
            ctes = _calibration_population_ctes()

            # (a) EVERY candidate is present in ``normalized`` (pre-dedup) — the
            #     "counts computed before the row disappears" invariant. If the
            #     old volume gate returned, zero-volume rows would be missing here.
            norm_rows = (await session.execute(text(
                "WITH " + ctes
                + " SELECT outcome_id FROM normalized WHERE outcome_id = ANY(:ids)"
            ), {"ids": ids})).all()
            assert {r.outcome_id for r in norm_rows} == set(ids), (
                "a candidate vanished before the liquidity predicate could count it"
            )

            # (b) EXACT liquidity counters over the candidate population.
            liq = (await session.execute(text(
                "WITH " + ctes + """,
                liq AS (
                    SELECT
                        COUNT(*) FILTER (WHERE source='kalshi' AND is_liquid) AS k_incl,
                        COUNT(*) FILTER (WHERE source='kalshi' AND NOT is_liquid) AS k_excl,
                        COUNT(*) FILTER (WHERE source='polymarket' AND is_poly_placeholder) AS p_ph,
                        COUNT(*) FILTER (WHERE source='polymarket' AND NOT is_poly_placeholder) AS p_incl
                    FROM normalized WHERE outcome_id = ANY(:ids)
                ) SELECT * FROM liq
            """), {"ids": ids})).one()
            assert liq.k_incl == 3, "K1(bid)+K2(trade)+K6(trade) must be included"
            assert liq.k_excl == 3, "K3+K4+K5 (no evidence, any volume) must be excluded"
            assert liq.p_ph == 1, "only P2 (in-band never-traded) is a poly placeholder"
            assert liq.p_incl == 1, "P1 (out-of-band never-traded) stays IN per declared poly policy"

            # (c) EXACT ``deduped`` (published-curve) outcome IDs.
            pub = (await session.execute(text(
                "WITH " + ctes
                + " SELECT outcome_id FROM deduped WHERE outcome_id = ANY(:ids)"
            ), {"ids": ids})).all()
            assert {r.outcome_id for r in pub} == {91001, 91002, 91006, 91007}, (
                "curve must publish exactly the bid/trade-bearing Kalshi rows "
                "(incl. the zero-volume bid row) + the out-of-band poly row"
            )
    finally:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)
        await engine.dispose()


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
