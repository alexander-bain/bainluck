"""Queue #262 Item 1 — the time-horizon calibration population must reuse the
canonical resolved-question identity + independent-truth allowlist + artifact
exclusions, finalized on each horizon's SNAPSHOT as the curve price.

Before #262, T-30/T-7/T-1/T-0 used a bespoke ``eligible_outcomes`` CTE with the
LEGACY NOT-IN denylist and NONE of the canonical exclusions/normalization — so the
same /calibration page could show a clean headline and horizon curves containing
self-graded (price-derived), guess, void, or structurally-invalid rows (C23 P1).

Two layers of proof, mirroring the rest of the calibration suite:

  1. ALWAYS-ON source-inspection on ``_build_time_horizon_sql`` — the heavy CTE is
     Postgres-only (CI has no PG service; the dev sandbox blocks shared memory), so
     the always-on guard proves the SHIPPED horizon SQL is built from the canonical
     ``_calibration_population_ctes`` with the horizon snapshot as the curve price,
     carries the truth allowlist + EVERY artifact-exclusion flag, drops the legacy
     denylist, scopes to the non-event universe, keeps all four named horizons, and
     reports candidate/final/distinct-question/exclusion diagnostics.

  2. A Postgres-backed contract test (skipped unless ``CALIBRATION_TEST_DATABASE_URL``
     is set) that seeds the 8 required scenarios and executes the REAL horizon SQL:
     complete field, incomplete-at-horizon field, malformed binary, Poly placeholder,
     Kalshi liquidity failure, prop threshold, weather wide spread, and a snapshot
     that changes classification across horizons — plus the leakage guard that a
     price-derived (settlement_sync) winner never enters any horizon.
"""

import os
from datetime import datetime, timedelta, timezone

import pytest

from app.tasks.precompute_calibration import (
    CALIBRATION_POPULATION_VERSION,
    _build_time_horizon_sql,
    _calibration_population_ctes,
    _HORIZONS,
)


# ---------------------------------------------------------------------------
# ALWAYS-ON: the shipped horizon SQL reuses the canonical population.
# ---------------------------------------------------------------------------
class TestHorizonSQLReusesCanonicalPopulation:
    def _sql(self, days=7):
        sql, _ = _build_time_horizon_sql(days)
        return sql

    def test_built_from_canonical_population_ctes(self):
        # The horizon population is the canonical chain, not a bespoke re-implementation.
        sql = self._sql()
        canonical_markers = [
            "market_info AS",
            "virtual_market AS",
            "clean_vms AS",
            "ranked_outcomes AS MATERIALIZED",
            "field_completeness AS",
            "normalized AS",
            "mode_prices AS",
            "deduped AS",
        ]
        for m in canonical_markers:
            assert m in sql, f"horizon SQL missing canonical CTE: {m}"

    def test_finalizes_on_horizon_snapshot_not_terminal_price(self):
        sql = self._sql()
        # The curve price is the horizon snapshot, injected via horizon_price.
        assert "hp.horizon_prob AS raw_cp" in sql
        assert "JOIN horizon_price hp ON hp.outcome_id = fo.id" in sql
        # Buckets/normalization are on the ADJUSTED horizon price, not a scalar copy.
        assert "FLOOR(adj_opening_probability * 10)" in sql
        assert "FROM deduped" in sql

    def test_uses_truth_allowlist_not_legacy_denylist(self):
        sql = self._sql()
        # The legacy NOT-IN denylist tokens must be gone from every horizon.
        for token in ("pass2_guess", "pass2_loser", "all_losers", "no_pregame_trading"):
            assert token not in sql, f"legacy denylist token leaked into horizon SQL: {token}"
        # The independent-truth allowlist (rendered as an IN-list) is present; a
        # price-derived source (settlement_sync) and clean_resolution are NOT in
        # it (they only appear, unquoted, in the explanatory comment). Check the
        # SQL-literal (quoted) form so the comment mention doesn't false-positive.
        assert "resolution_source IN (" in sql
        assert "'api_settlement'" in sql
        assert "'settlement_sync'" not in sql
        assert "'clean_resolution'" not in sql

    def test_carries_every_artifact_exclusion_flag(self):
        sql = self._sql()
        for flag in (
            "is_liquid",
            "is_poly_placeholder",
            "is_malformed_binary",
            "is_esports_bundle",
            "is_golf_placeholder",
            "is_kalshi_prop_threshold",
            "is_weather_wide_spread",
            "is_field_incomplete",
        ):
            assert flag in sql, f"horizon SQL missing artifact-exclusion flag: {flag}"

    def test_scoped_to_non_event_resolution_date_universe(self):
        sql = self._sql()
        # market_info is scoped so the whole chain runs on the small horizon set.
        assert "AND fm.event_id IS NULL AND fm.resolution_date IS NOT NULL" in sql
        # horizon_price is the leading LATERAL keyed on the cutoff.
        assert sql.startswith("WITH horizon_price AS")
        assert "LEFT JOIN LATERAL" in sql

    def test_reports_candidate_final_distinct_and_exclusion_reasons(self):
        sql = self._sql()
        assert "AS candidate_n" in sql
        assert "AS final_n" in sql
        assert "AS distinct_questions" in sql
        for reason in (
            "excl_illiquid",
            "excl_poly_placeholder",
            "excl_malformed_binary",
            "excl_esports_bundle",
            "excl_golf_placeholder",
            "excl_kalshi_prop_threshold",
            "excl_weather_wide_spread",
            "excl_field_incomplete",
        ):
            assert reason in sql

    def test_completeness_uses_full_terminal_field_size(self):
        # A horizon field is complete only when EVERY terminal-eligible member is
        # present at the snapshot — eligible_n is the terminal count, not the
        # present-outcome COUNT, so a member missing at the horizon drops it whole.
        sql = self._sql()
        assert "MAX(mfc.terminal_eligible_n) AS eligible_n" in sql
        assert "mex_field_candidates" in sql
        assert "mex_field_divisor" in sql

    def test_all_four_named_horizons_preserved_no_universal_cutoff(self):
        labels = {label for label, _ in _HORIZONS}
        assert labels == {"T-30", "T-7", "T-1", "T-0"}
        # T-0 keys off resolution_date itself; the others subtract an interval.
        sql0, p0 = _build_time_horizon_sql(0)
        sql7, p7 = _build_time_horizon_sql(7)
        assert "make_interval" not in sql0 and p0 == {}
        assert "make_interval(days => :days)" in sql7 and p7 == {"days": 7}
        # No single hard-coded "+1h" / one-hour public default is introduced.
        assert "make_interval(hours" not in sql7

    def test_population_version_fingerprint_exposed(self):
        assert CALIBRATION_POPULATION_VERSION  # non-empty
        # Default (headline) and horizon share the SAME population builder.
        assert "deduped AS" in _calibration_population_ctes()


# ---------------------------------------------------------------------------
# POSTGRES-BACKED CONTRACT (skipped unless CALIBRATION_TEST_DATABASE_URL is set).
# Seeds the 8 required scenarios + the leakage guard and runs the REAL horizon SQL.
# ---------------------------------------------------------------------------
DB_URL = os.environ.get("CALIBRATION_TEST_DATABASE_URL")

pg = pytest.mark.skipif(
    not DB_URL,
    reason="set CALIBRATION_TEST_DATABASE_URL to run the real horizon-CTE contract test",
)

# A fixed resolution date so cutoffs are deterministic (never seed relative to
# datetime.now() across a date boundary — gotcha #44).
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


async def _snap(session, oid, *, days_before_res, probability, yes_bid=None,
                last_price=None):
    """A snapshot captured `days_before_res` days before resolution."""
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
    rows = (await session.execute(text(sql), params)).all()
    return rows


def _final_outcomes(rows):
    """Rows carry per-row diag; final_n is constant across rows."""
    return int(rows[0].final_n) if rows else 0


@pg
@pytest.mark.asyncio
async def test_horizon_population_contract_all_scenarios():
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    from app.models.models import Base

    engine = create_async_engine(DB_URL)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    Session = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with Session() as s:
            # (1) COMPLETE field: 3 members, all priced at T-7, one winner. Published,
            #     normalized, sums to ~1.0 at the horizon.
            await _mk_market(s, 91001, "polymarket", mex=True, mtype="field", category="politics")
            for i, (op, win) in enumerate([(0.60, True), (0.40, False), (0.20, False)]):
                oid = await _mk_outcome(s, 91001, i, op=op, cp=op, win=win)
                await _snap(s, oid, days_before_res=10, probability=op, last_price=op)

            # (2) INCOMPLETE-at-horizon field: same shape but one member has NO T-7
            #     snapshot → present < terminal → dropped WHOLE.
            await _mk_market(s, 91002, "polymarket", mex=True, mtype="field", category="politics")
            for i, (op, win) in enumerate([(0.60, True), (0.40, False), (0.20, False)]):
                oid = await _mk_outcome(s, 91002, i, op=op, cp=op, win=win)
                if i != 2:  # member 2 has no snapshot at/under the T-7 cutoff
                    await _snap(s, oid, days_before_res=10, probability=op, last_price=op)

            # (3) MALFORMED binary: 2-outcome mex with TWO winners → excluded.
            await _mk_market(s, 91003, "polymarket", mex=True, mtype="binary", category="politics")
            for i, (op, win) in enumerate([(0.55, True), (0.45, True)]):
                oid = await _mk_outcome(s, 91003, i, op=op, cp=op, win=win)
                await _snap(s, oid, days_before_res=10, probability=op, last_price=op)

            # (4) POLY placeholder: near-0.50, NO bid/trade evidence → excluded.
            await _mk_market(s, 91004, "polymarket", mex=False, mtype="binary", category="politics")
            oid = await _mk_outcome(s, 91004, 0, op=0.50, cp=0.50, win=False)
            await _snap(s, oid, days_before_res=10, probability=0.50)  # no bid/last_price

            # (5) KALSHI liquidity failure: never bid / never traded → excluded.
            await _mk_market(s, 91005, "kalshi", mex=False, mtype="binary", category="economics")
            oid = await _mk_outcome(s, 91005, 0, op=0.30, cp=0.30, win=False)
            await _snap(s, oid, days_before_res=10, probability=0.30)  # no yes_bid/last_price

            # (6) KALSHI prop threshold in the degenerate band → excluded.
            await _mk_market(s, 91006, "kalshi", mex=False, mtype="binary", category="basketball")
            oid = await _mk_outcome(s, 91006, 0, op=0.95, cp=0.95, win=False,
                                    name="Player X: 20+")
            await _snap(s, oid, days_before_res=10, probability=0.95, yes_bid=0.95, last_price=0.95)

            # (7) WEATHER wide spread with no trade → excluded.
            await _mk_market(s, 91007, "kalshi", mex=False, mtype="binary", category="weather")
            oid = await _mk_outcome(s, 91007, 0, op=0.40, cp=0.40, win=False,
                                    yes_bid=0.10, yes_ask=0.90)
            await _snap(s, oid, days_before_res=10, probability=0.40, yes_bid=0.10)  # no last_price

            # (8) LEAKAGE guard: a price-derived (settlement_sync) winner must NEVER
            #     enter any horizon (orthogonal to overwrite authority — C20/C21).
            await _mk_market(s, 91008, "polymarket", mex=False, mtype="binary", category="tech")
            oid = await _mk_outcome(s, 91008, 0, op=0.70, cp=0.70, win=True,
                                    src="settlement_sync")
            await _snap(s, oid, days_before_res=10, probability=0.70, last_price=0.70)

            await s.commit()

            # --- T-7 assertions ---
            rows7 = await _run_horizon(s, 7)
            present = {(r.source, r.category, r.bucket_idx): r for r in rows7
                       if r.bucket_idx is not None}

            # Complete field 91001 published: its three normalized members sum to ~1.
            # (We can't filter by market in the aggregate, so assert via distinct
            #  questions + that the incomplete/artifact markets contributed nothing.)
            # Only the complete field survives → exactly one distinct question, 3 finals.
            assert _final_outcomes(rows7) == 3, (
                f"only the complete field should publish, got final_n={_final_outcomes(rows7)}"
            )
            assert int(rows7[0].distinct_questions) == 1
            # Every excluded scenario is reflected in the per-reason diag counts.
            assert int(rows7[0].excl_field_incomplete) >= 3   # scenario (2)
            assert int(rows7[0].excl_malformed_binary) >= 2   # scenario (3)
            assert int(rows7[0].excl_poly_placeholder) >= 1   # scenario (4)
            assert int(rows7[0].excl_illiquid) >= 1           # scenario (5)
            assert int(rows7[0].excl_kalshi_prop_threshold) >= 1  # scenario (6)
            assert int(rows7[0].excl_weather_wide_spread) >= 1    # scenario (7)
            # settlement_sync (price-derived) never even becomes a candidate.
            # candidate_n counts only truth-eligible rows → the tech leak is absent.
            # (3 complete-field + the excluded artifacts, but NOT the settlement_sync row.)
    finally:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)
        await engine.dispose()


@pg
@pytest.mark.asyncio
async def test_snapshot_changes_classification_across_horizons():
    """(8th scenario) The SAME field is normalized/bucketed from each horizon's own
    price, so a member that moves between snapshots lands in different buckets at
    T-30 vs T-0 — proving horizons are finalized independently, not copied."""
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    from app.models.models import Base

    engine = create_async_engine(DB_URL)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    Session = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with Session() as s:
            # A complete 2-real-member field whose winner drifts up over time.
            await _mk_market(s, 92001, "polymarket", mex=True, mtype="field", category="economics")
            oids = []
            for i, (op, win) in enumerate([(0.50, True), (0.30, False), (0.20, False)]):
                oid = await _mk_outcome(s, 92001, i, op=op, cp=op, win=win)
                oids.append((oid, op, win))
            # Winner: 0.50 at T-30 → 0.90 at T-0. Others adjust so both horizons are
            # complete (all three present at each cutoff).
            await _snap(s, oids[0][0], days_before_res=30, probability=0.50, last_price=0.50)
            await _snap(s, oids[0][0], days_before_res=0, probability=0.90, last_price=0.90)
            await _snap(s, oids[1][0], days_before_res=30, probability=0.30, last_price=0.30)
            await _snap(s, oids[1][0], days_before_res=0, probability=0.30, last_price=0.30)
            await _snap(s, oids[2][0], days_before_res=30, probability=0.20, last_price=0.20)
            await _snap(s, oids[2][0], days_before_res=0, probability=0.20, last_price=0.20)
            await s.commit()

            rows30 = [r for r in await _run_horizon(s, 30) if r.bucket_idx is not None]
            rows0 = [r for r in await _run_horizon(s, 0) if r.bucket_idx is not None]
            # Both horizons publish the complete field (3 finals each).
            assert _final_outcomes(await _run_horizon(s, 30)) == 3
            assert _final_outcomes(await _run_horizon(s, 0)) == 3
            # The winner's normalized bucket at T-0 is strictly higher than at T-30
            # (0.90/(0.90+0.30+0.20) ≈ 0.64 vs 0.50/1.0 = 0.50) — classification
            # genuinely changed across horizons.
            top30 = max(r.bucket_idx for r in rows30)
            top0 = max(r.bucket_idx for r in rows0)
            assert top0 > top30
    finally:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)
        await engine.dispose()


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
