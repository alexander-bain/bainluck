"""Queue #262 Item 2 — reader-trust examples + admin diagnostics must describe the
PUBLISHED bucket.

``/calibration/examples`` (public), ``/calibration/bucket-debug`` and
``/calibration/snapshot-health`` (admin) previously re-implemented eligibility with
a stale NOT-IN denylist, admitted NULL/price-derived truth, omitted the canonical
artifact exclusions/normalization, and inferred the result from terminal
``current_probability`` instead of canonical ``is_winner`` — so an operator or a
skeptical reader could inspect rows that are NOT in the point they explain (C23 P1).

Now all three select from the canonical published population (``deduped`` from
``_calibration_population_ctes``), bucket on the SAME ``adj_opening_probability``,
report truth as ``is_winner``, and surface the population fingerprint.

Two layers of proof (the heavy CTE is Postgres-only — CI has no PG service):
  1. ALWAYS-ON source-inspection that each endpoint builds on the canonical
     population, uses is_winner (never current_probability as truth), and names the
     fingerprint.
  2. A Postgres-backed contract test (skipped unless CALIBRATION_TEST_DATABASE_URL
     is set) proving every returned example is in the requested deduped bucket and
     that a price-derived (settlement_sync) winner never appears.
"""

import inspect
import os

import pytest

from app.routes import calibration as cal
from app.tasks.precompute_calibration import CALIBRATION_POPULATION_VERSION


# ---------------------------------------------------------------------------
# ALWAYS-ON: the three endpoints select the canonical published population.
# ---------------------------------------------------------------------------
def _sql_only(src: str) -> str:
    """Strip the triple-quoted docstring + comment lines so prose mentions of a
    column name don't false-positive a "column not referenced" assertion."""
    import re as _re
    # drop the leading function docstring
    src = _re.sub(r'""".*?"""', "", src, count=1, flags=_re.DOTALL)
    # drop python comment lines
    return "\n".join(l for l in src.splitlines() if not l.lstrip().startswith("#"))


class TestEndpointsUseCanonicalPopulation:
    def test_examples_builds_on_deduped(self):
        src = inspect.getsource(cal.calibration_examples)
        assert "_calibration_population_ctes()" in src
        assert "FROM deduped d" in src
        # bucketed on the SAME adjusted probability the curve uses.
        assert "FLOOR(d.adj_opening_probability * 10)" in src
        # truth is canonical is_winner, not terminal current_probability.
        assert "d.is_winner" in src
        # truth must not derive from a terminal current_probability column ref.
        assert ".current_probability" not in _sql_only(src)
        # the legacy denylist / volume re-implementation is gone.
        assert "pass2_guess" not in src
        assert "population_version" in src

    def test_bucket_debug_builds_on_deduped_with_is_winner(self):
        src = inspect.getsource(cal.calibration_bucket_debug)
        assert "_calibration_population_ctes()" in src
        assert "FROM deduped d" in src
        assert "d.is_winner" in src
        # result label derives from is_winner, never a current_probability band.
        assert 'r.is_winner else "loser"' in src
        assert ".current_probability" not in _sql_only(src)
        assert "population_version" in src

    def test_snapshot_health_measures_canonical_population(self):
        src = inspect.getsource(cal.calibration_snapshot_health)
        assert "_calibration_population_ctes()" in src
        assert "FROM deduped d" in src
        # coverage counted over deduped, not a current_probability band proxy.
        assert ".current_probability" not in _sql_only(src)
        assert "population_version" in src

    def test_fingerprint_is_defined(self):
        assert CALIBRATION_POPULATION_VERSION


# ---------------------------------------------------------------------------
# POSTGRES-BACKED CONTRACT (skipped unless CALIBRATION_TEST_DATABASE_URL is set).
# ---------------------------------------------------------------------------
DB_URL = os.environ.get("CALIBRATION_TEST_DATABASE_URL")

pg = pytest.mark.skipif(
    not DB_URL,
    reason="set CALIBRATION_TEST_DATABASE_URL to run the real-CTE examples contract test",
)


async def _seed_binary(session, mid, source, *, op, win, res_src="api_settlement"):
    from sqlalchemy import text

    await session.execute(
        text(
            "INSERT INTO futures_markets (id, source, status, mutually_exclusive, "
            "market_type, llm_sport_category, volume, name) VALUES "
            "(:id, :src, 'resolved', false, 'binary', 'politics', 100, :nm)"
        ),
        {"id": mid, "src": source, "nm": f"Question {mid}?"},
    )
    oid = mid * 1000
    await session.execute(
        text(
            "INSERT INTO futures_outcomes (id, market_id, name, opening_probability, "
            "calibration_probability, is_winner, resolution_source, volume) VALUES "
            "(:id, :mid, 'Yes', :op, :op, :win, :src, 10)"
        ),
        {"id": oid, "mid": mid, "op": op, "win": win, "src": res_src},
    )
    await session.execute(
        text(
            "INSERT INTO futures_odds_snapshots (outcome_id, bookmaker, probability, "
            "yes_bid, last_price) VALUES (:oid, 'test', :p, :p, :p)"
        ),
        {"oid": oid, "p": op},
    )
    return oid


@pg
@pytest.mark.asyncio
async def test_examples_only_returns_in_bucket_canonical_rows():
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    from app.models.models import Base

    engine = create_async_engine(DB_URL)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    Session = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with Session() as s:
            # An in-bucket-6 winner (0.65), an out-of-bucket loser (0.25 -> bucket 2),
            # and a PRICE-DERIVED (settlement_sync) winner at 0.65 that must NOT leak.
            await _seed_binary(s, 93001, "polymarket", op=0.65, win=True)
            await _seed_binary(s, 93002, "polymarket", op=0.25, win=False)
            await _seed_binary(s, 93003, "polymarket", op=0.65, win=True,
                               res_src="settlement_sync")
            await s.commit()

            cal._examples_cache.clear()
            res = await cal.calibration_examples(
                db=s, source="polymarket", bucket=6, well_traded=0, limit=10
            )
            assert res["population_version"] == CALIBRATION_POPULATION_VERSION
            # Every returned example must be in bucket 6 (price in [0.60, 0.70)).
            for ex in res["examples"]:
                assert 0.60 <= ex["price"] < 0.70, ex
            # The price-derived (settlement_sync) row is absent by construction.
            names = {ex["market_name"] for ex in res["examples"]}
            assert "Question 93003?" not in names
            # The legitimate independent-truth winner IS present.
            assert "Question 93001?" in names
    finally:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)
        await engine.dispose()


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
