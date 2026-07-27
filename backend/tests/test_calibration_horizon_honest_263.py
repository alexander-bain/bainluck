"""Queue #263 Item 1 — every horizon must classify on its OWN forecast price.

Queue #262 finalized each horizon's normalization DIVISOR + field completeness on
the horizon snapshot, but two PRICE-STATE decisions still read the TERMINAL
probability regardless of horizon:

  1. the MEX field-sum > threshold qualification (baked into ``mex_field_candidates``
     as ``HAVING SUM(terminal cp) > MEX_NORMALIZE_THRESHOLD``), and
  2. the Kalshi prop-threshold degenerate-band classification (the 0.90 / hockey-0.50
     bands read ``COALESCE(fo.calibration_probability, fo.opening_probability)``).

So a terminal-low/horizon-high field would not qualify, a terminal-high/horizon-low
field would normalize over a tiny horizon divisor, and a prop outcome would be
excluded/kept by its terminal price on EVERY horizon. #263 Item 1 separates roster
identity (structural, terminal) from price qualification (the price expression):

  * the field-sum threshold moved off candidate detection into the ``normalized``
    gate, keyed on ``mnm_cp_sum`` (the divisor sum over ``{curve_price}``), and
  * ``kalshi_prop_threshold_exclude_sql`` takes a ``curve_price`` override wired to
    the horizon snapshot, preserving the hockey vs general band split mechanically.

Headline is preserved EXACTLY: on the headline path ``{curve_price}`` == terminal cp
and present == terminal, so both reduce to the old ``mex_norm_markets`` behavior.

Two layers of proof (mirroring the rest of the calibration suite): always-on
source-inspection on the shipped SQL builders (the heavy CTE is Postgres-only), plus
a Postgres-backed contract (skipped unless ``CALIBRATION_TEST_DATABASE_URL`` is set)
that seeds fields/props whose classification CROSSES between terminal and horizon.
"""

import os
from datetime import datetime, timedelta, timezone

import pytest

from app.tasks.precompute_calibration import (
    KALSHI_HOCKEY_HONEST_BAND_MAX,
    KALSHI_PROP_THRESHOLD_DEGENERATE_BAND,
    MEX_NORMALIZE_THRESHOLD,
    _build_time_horizon_sql,
    _calibration_population_ctes,
    kalshi_prop_threshold_exclude_sql,
)


# ---------------------------------------------------------------------------
# ALWAYS-ON: the shipped SQL classifies price-state on the curve price.
# ---------------------------------------------------------------------------
class TestPropThresholdBandUsesCurvePrice:
    def test_exclude_sql_defaults_to_terminal_coalesce(self):
        # No curve_price → the historical COALESCE(cp, opening) band (headline).
        sql = kalshi_prop_threshold_exclude_sql(
            source="cv.source", name="fo.name", category="cv.category",
            calibration_probability="fo.calibration_probability",
            opening_probability="fo.opening_probability",
        )
        assert "COALESCE(fo.calibration_probability, fo.opening_probability)" in sql
        assert "hp.horizon_prob" not in sql
        assert f">= {KALSHI_HOCKEY_HONEST_BAND_MAX}" in sql
        assert f">= {KALSHI_PROP_THRESHOLD_DEGENERATE_BAND}" in sql

    def test_exclude_sql_curve_price_override_replaces_both_bands(self):
        # A curve_price override replaces the price expression in BOTH the hockey
        # (0.50) and general (0.90) band comparisons — the split is preserved.
        sql = kalshi_prop_threshold_exclude_sql(
            source="cv.source", name="fo.name", category="cv.category",
            calibration_probability="fo.calibration_probability",
            opening_probability="fo.opening_probability",
            curve_price="hp.horizon_prob",
        )
        # terminal price no longer decides the band
        assert "COALESCE(fo.calibration_probability, fo.opening_probability)" not in sql
        # both bands now read the horizon snapshot
        assert sql.count("hp.horizon_prob") == 2
        assert "cv.category = 'hockey'" in sql  # hockey rule preserved mechanically
        assert f">= {KALSHI_HOCKEY_HONEST_BAND_MAX}" in sql
        assert f">= {KALSHI_PROP_THRESHOLD_DEGENERATE_BAND}" in sql

    def test_headline_population_prop_band_reads_terminal(self):
        # The default (headline) population keeps the terminal COALESCE band verbatim.
        pop = _calibration_population_ctes()
        expected = kalshi_prop_threshold_exclude_sql(
            source="cv.source", name="fo.name", category="cv.category",
            calibration_probability="fo.calibration_probability",
            opening_probability="fo.opening_probability",
            curve_price="COALESCE(fo.calibration_probability, fo.opening_probability)",
        )
        assert expected in pop

    def test_horizon_population_prop_band_reads_snapshot(self):
        # The horizon population classifies the prop band on the horizon snapshot.
        sql, _ = _build_time_horizon_sql(7)
        expected = kalshi_prop_threshold_exclude_sql(
            source="cv.source", name="fo.name", category="cv.category",
            calibration_probability="fo.calibration_probability",
            opening_probability="fo.opening_probability",
            curve_price="hp.horizon_prob",
        )
        assert expected in sql


class TestFieldSumThresholdIsPriceExpression:
    def test_candidate_detection_no_longer_carries_terminal_sum_gate(self):
        # The old terminal-price field-sum gate is GONE from candidate detection.
        for sql in (_calibration_population_ctes(), _build_time_horizon_sql(7)[0]):
            assert (
                "SUM(COALESCE(fo.calibration_probability, fo.opening_probability)) "
                f"> {MEX_NORMALIZE_THRESHOLD}" not in sql
            )
            # candidate detection keeps only the structural roster gate.
            assert "HAVING COUNT(*) >= 3" in sql

    def test_normalized_gate_keys_field_qualification_on_divisor_sum(self):
        # is_mex_normalized / is_field_incomplete / the divisor CASE all gate on
        # mnm_cp_sum (the price-expression sum), so field qualification is horizon-
        # honest. Appears three times (the three predicates).
        pop = _calibration_population_ctes()
        assert pop.count(f"ro.mnm_cp_sum > {MEX_NORMALIZE_THRESHOLD}") == 3

    def test_horizon_divisor_sums_the_snapshot_price(self):
        # On the horizon, mnm_cp_sum is SUM over hp.horizon_prob (present members),
        # so a terminal-high/horizon-low field can fall below the threshold and a
        # terminal-low/horizon-high field can clear it.
        sql, _ = _build_time_horizon_sql(7)
        assert "SUM(hp.horizon_prob) AS cp_sum" in sql
        assert f"ro.mnm_cp_sum > {MEX_NORMALIZE_THRESHOLD}" in sql

    def test_completeness_still_measures_full_terminal_roster(self):
        # Roster identity stays terminal: a member missing at the horizon still drops
        # the whole field (survivor_n < terminal_eligible_n).
        sql, _ = _build_time_horizon_sql(7)
        assert "MAX(mfc.terminal_eligible_n) AS eligible_n" in sql


# ---------------------------------------------------------------------------
# POSTGRES-BACKED CONTRACT (skipped unless CALIBRATION_TEST_DATABASE_URL is set).
# ---------------------------------------------------------------------------
DB_URL = os.environ.get("CALIBRATION_TEST_DATABASE_URL")

pg = pytest.mark.skipif(
    not DB_URL,
    reason="set CALIBRATION_TEST_DATABASE_URL to run the real horizon-CTE contract test",
)

_RES = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)


async def _mk_market(session, mid, source, *, mex, mtype, category, res_date=_RES, volume=100):
    from sqlalchemy import text

    await session.execute(
        text(
            "INSERT INTO futures_markets (id, source, status, mutually_exclusive, "
            "market_type, llm_sport_category, volume, resolution_date) VALUES "
            "(:id, :src, 'resolved', :mex, :mt, :cat, :vol, :rd)"
        ),
        {"id": mid, "src": source, "mex": mex, "mt": mtype, "cat": category,
         "vol": volume, "rd": res_date},
    )


async def _mk_outcome(session, mid, i, *, op, cp, win, src="api_settlement", volume=10,
                      name=None, yes_bid=None, yes_ask=None):
    from sqlalchemy import text

    oid = mid * 1000 + i
    await session.execute(
        text(
            "INSERT INTO futures_outcomes (id, market_id, name, opening_probability, "
            "calibration_probability, is_winner, resolution_source, volume, "
            "current_yes_bid, current_yes_ask) VALUES "
            "(:id, :mid, :nm, :op, :cp, :win, :src, :vol, :yb, :ya)"
        ),
        {"id": oid, "mid": mid, "nm": name or f"cand-{i}", "op": op, "cp": cp,
         "win": win, "src": src, "vol": volume, "yb": yes_bid, "ya": yes_ask},
    )
    return oid


async def _snap(session, oid, *, days_before_res, probability, yes_bid=None, last_price=None):
    from sqlalchemy import text

    await session.execute(
        text(
            "INSERT INTO futures_odds_snapshots (outcome_id, bookmaker, probability, "
            "yes_bid, last_price, captured_at) VALUES "
            "(:oid, 'test', :p, :yb, :lp, :ts)"
        ),
        {"oid": oid, "p": probability, "yb": yes_bid, "lp": last_price,
         "ts": _RES - timedelta(days=days_before_res)},
    )


async def _run_horizon(session, days):
    from sqlalchemy import text

    sql, params = _build_time_horizon_sql(days)
    return (await session.execute(text(sql), params)).all()


def _final_n(rows):
    return int(rows[0].final_n) if rows else 0


def _prop_excluded(rows):
    return int(rows[0].excl_kalshi_prop_threshold) if rows else 0


@pg
@pytest.mark.asyncio
async def test_field_sum_qualification_crosses_between_terminal_and_horizon():
    """A field whose TERMINAL cp-sum is below threshold but whose HORIZON cp-sum is
    above (and vice versa) must classify from the horizon price."""
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    from app.models.models import Base

    engine = create_async_engine(DB_URL)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    Session = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with Session() as s:
            # (A) TERMINAL-LOW / HORIZON-HIGH: terminal cp sums to 0.90 (< 1.15, would
            #     NOT be a field on terminal), but the T-7 snapshots sum to 1.20
            #     (> 1.15) → qualifies as a normalized field AT THE HORIZON.
            await _mk_market(s, 93101, "polymarket", mex=True, mtype="field", category="politics")
            for i, (cp, hp, win) in enumerate([(0.40, 0.60, True), (0.30, 0.40, False), (0.20, 0.20, False)]):
                oid = await _mk_outcome(s, 93101, i, op=cp, cp=cp, win=win)
                await _snap(s, oid, days_before_res=10, probability=hp, last_price=hp)

            # (B) TERMINAL-HIGH / HORIZON-LOW: terminal cp sums to 1.30 (> 1.15, would
            #     be a field on terminal), but the T-7 snapshots sum to 0.90 (< 1.15)
            #     → NOT a normalization field at the horizon; must not normalize over a
            #     tiny divisor. All members present, so it drops to the multi pool.
            await _mk_market(s, 93102, "polymarket", mex=True, mtype="field", category="economics")
            for i, (cp, hp, win) in enumerate([(0.60, 0.50, True), (0.40, 0.25, False), (0.30, 0.15, False)]):
                oid = await _mk_outcome(s, 93102, i, op=cp, cp=cp, win=win)
                await _snap(s, oid, days_before_res=10, probability=hp, last_price=hp)

            await s.commit()

            rows7 = await _run_horizon(s, 7)
            # (A) publishes its 3 normalized members; (B) is not a field so its single
            # representative binary row survives (rn=1) — distinct questions >= 1.
            # Assert (A)'s field is present and normalized: its winner's normalized
            # bucket is 0.60/1.20 = 0.50 → bucket 5.
            buckets = {(r.source, r.category, r.bucket_idx) for r in rows7 if r.bucket_idx is not None}
            assert ("polymarket", "politics", 5) in buckets, (
                "terminal-low/horizon-high field must qualify + normalize at the horizon"
            )
            # (B) must NOT contribute a blown-up (>1.0-divisor) member: no economics
            # bucket at index 9 from a 0.50/0.90 ≈ 0.56 over-normalization.
            econ_top = max(
                (r.bucket_idx for r in rows7
                 if r.bucket_idx is not None and r.category == "economics"),
                default=-1,
            )
            assert econ_top < 9, "terminal-high/horizon-low field must not normalize over a small divisor"
    finally:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)
        await engine.dispose()


@pg
@pytest.mark.asyncio
async def test_prop_threshold_band_crosses_0_90_by_horizon():
    """The same Kalshi prop outcome crosses the 0.90 degenerate band between horizons:
    excluded where its snapshot is >= 0.90, kept where its snapshot is below."""
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    from app.models.models import Base

    engine = create_async_engine(DB_URL)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    Session = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with Session() as s:
            # A basketball prop that is BELOW the band at T-30 (0.70) and ABOVE it at
            # T-0 (0.95). Terminal cp is 0.95. Under #263 the T-30 horizon KEEPS it
            # (0.70 < 0.90) and the T-0 horizon EXCLUDES it (0.95 >= 0.90). Add a
            # liquid sibling binary so a bucket survives at both horizons regardless.
            await _mk_market(s, 93201, "kalshi", mex=False, mtype="binary", category="basketball")
            oid = await _mk_outcome(s, 93201, 0, op=0.95, cp=0.95, win=False, name="Player X: 20+")
            await _snap(s, oid, days_before_res=30, probability=0.70, yes_bid=0.70, last_price=0.70)
            await _snap(s, oid, days_before_res=0, probability=0.95, yes_bid=0.95, last_price=0.95)

            await s.commit()

            rows30 = await _run_horizon(s, 30)
            rows0 = await _run_horizon(s, 0)
            # T-30: snapshot 0.70 is below the band → NOT excluded as prop-threshold.
            assert _prop_excluded(rows30) == 0, "below-band horizon snapshot must be kept"
            # T-0: snapshot 0.95 is in the degenerate band → excluded.
            assert _prop_excluded(rows0) >= 1, "in-band horizon snapshot must be excluded"
    finally:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)
        await engine.dispose()


@pg
@pytest.mark.asyncio
async def test_hockey_prop_band_preserved_on_horizon_price():
    """The separate hockey rule (>= 0.50) is preserved mechanically but reads the
    horizon snapshot: an NHL goal-family prop at a horizon snapshot >= 0.50 is
    excluded even though the general band is 0.90."""
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    from app.models.models import Base

    engine = create_async_engine(DB_URL)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    Session = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with Session() as s:
            await _mk_market(s, 93301, "kalshi", mex=False, mtype="binary", category="hockey")
            oid = await _mk_outcome(s, 93301, 0, op=0.30, cp=0.30, win=False, name="Player Y: 1+")
            # Below 0.50 at T-30 (kept), at/above 0.50 at T-0 (excluded by hockey rule).
            await _snap(s, oid, days_before_res=30, probability=0.40, yes_bid=0.40, last_price=0.40)
            await _snap(s, oid, days_before_res=0, probability=0.55, yes_bid=0.55, last_price=0.55)
            await s.commit()

            assert _prop_excluded(await _run_horizon(s, 30)) == 0
            assert _prop_excluded(await _run_horizon(s, 0)) >= 1
    finally:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)
        await engine.dispose()


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
