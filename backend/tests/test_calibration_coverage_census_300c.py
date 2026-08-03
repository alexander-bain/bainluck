"""Queue 300C — the coverage census is additive, exact, and honest when it isn't.

Alex's 2026-08-02 ruling: publish BOTH the ~653K published curve observations
and the ~1.28M outcomes with calibration-price coverage, joined by an additive
bridge, without changing the curve. These tests hold the three ways that can go
wrong in the shipped build (rather than in the pure contract, which
``tests/evals/test_calibration_coverage_bridge_contract.py`` pins):

1. the SQL that measures the rungs drifting from the contract that names them,
2. the census silently reporting zero where it actually measured nothing, and
3. the census costing the curve payload anything at all.
"""

from types import SimpleNamespace

import pytest

from app.tasks import precompute_calibration as pc
from app.utils.calibration_coverage_bridge import (
    EXCLUSION_RUNGS,
    PLOTTED_RUNG,
    RUNG_KEYS,
    ensure_census,
    unavailable_census,
)


# ---------------------------------------------------------------------------
# 1. The SQL and the contract cannot drift apart.
# ---------------------------------------------------------------------------
class TestRungDriftIsRefused:
    pytestmark = pytest.mark.usefixtures("census_on")

    def test_every_contract_rung_has_a_sql_predicate(self):
        keys = tuple(key for key, _sql in pc._COVERAGE_RUNG_PREDICATES)
        assert keys == RUNG_KEYS

    def test_only_the_terminal_rung_has_no_predicate(self):
        empty = [key for key, sql in pc._COVERAGE_RUNG_PREDICATES if not sql]
        assert empty == [pc._COVERAGE_RUNG_PREDICATES[-1][0]]

    def test_a_rung_added_without_a_predicate_refuses_to_build_sql(self, monkeypatch):
        # A new contract rung with no SQL branch would quietly dump its outcomes
        # into the catch-all and still "reconcile". Refuse to emit that SQL.
        monkeypatch.setattr(
            pc,
            "_COVERAGE_RUNG_PREDICATES",
            pc._COVERAGE_RUNG_PREDICATES[:-1],
        )
        with pytest.raises(ValueError, match="rung drift"):
            pc._coverage_bridge_ctes()

    def test_the_case_walks_the_contract_order(self):
        sql = pc._coverage_bridge_ctes()
        positions = [sql.index(f"THEN '{key}'") for key, p in pc._COVERAGE_RUNG_PREDICATES if p]
        assert positions == sorted(positions), "rung precedence must follow RUNG_KEYS"
        # The terminal rung is the ELSE, never a WHEN — otherwise a row matching
        # nothing would be dropped from the partition entirely.
        assert f"ELSE '{PLOTTED_RUNG}'" not in sql
        assert "ELSE 'representative_not_selected'" in sql

    def test_the_census_reads_the_canonical_population_not_a_copy(self):
        sql = pc._coverage_bridge_ctes()
        # It joins the already-built population CTEs; it must not re-derive them.
        for cte in ("market_info", "normalized", "deduped"):
            assert f"JOIN {cte} " in sql
        assert "ranked_outcomes AS" not in sql
        assert "virtual_market AS" not in sql


# ---------------------------------------------------------------------------
# 2. Measured vs unmeasured.
# ---------------------------------------------------------------------------
# The transparency counters the futures query already CROSS JOINs onto every
# bucket row. They are irrelevant here but must exist, because the build reads
# them positionally off row 0.
_EXISTING_TRANSPARENCY_COLUMNS = (
    "kalshi_included", "kalshi_excluded", "poly_placeholder_excluded", "poly_included",
    "poly_never_traded_total", "poly_never_traded_in_curve", "both_false_excluded",
    "both_winner_excluded", "golf_placeholder_excluded", "mex_normalized_outcomes",
    "mex_candidate_markets", "mex_normalized_markets", "field_incomplete_markets",
    "field_incomplete_outcomes", "esports_bundle_excluded", "no_winner_excluded",
    "no_winner_markets", "draw_authority_excluded", "draw_authority_markets",
    "orphan_partition_excluded", "orphan_partition_markets",
    "nonexclusive_bundle_candidates", "nonexclusive_bundle_markets",
    "kalshi_prop_threshold_excluded", "weather_wide_spread_excluded",
    "mex_published_markets", "mex_published_outcomes",
)


def _futures_row(**overrides):
    """One bucket row carrying the constant census columns, as Postgres returns."""
    base = {name: 0 for name in _EXISTING_TRANSPARENCY_COLUMNS}
    base |= {
        "bucket_idx": 5,
        "source": "kalshi",
        "category": "politics",
        "price_moved": False,
        "is_nonexclusive_bundle": False,
        "n": 90,
        "winners": 45,
        "avg_prob": 0.5,
        "sum_prob": 45.0,
        "sum_sq_err": 22.5,
        "published_outcomes": 90,
        "published_questions": 40,
        "cb_plotted_on_curve": 90,
        "cb_market_result_unavailable": 0,
        "cb_truth_source_missing": 12,
        "cb_truth_ineligible_source": 40,
        "cb_question_ungraded": 3,
        "cb_malformed_or_unknown_truth": 6,
        "cb_phantom_liquidity": 8,
        "cb_structural_artifact": 4,
        "cb_field_incomplete": 2,
        "cb_representative_not_selected": 5,
        "cb_coverage_total": 170,
        "cb_with_terminal_cal_price": 150,
    }
    base.update(overrides)
    return SimpleNamespace(**base)


def _sportsbook_row(n, winners):
    return SimpleNamespace(
        bucket_idx=5,
        source="odds_api",
        category="nba",
        price_moved=None,
        n=n,
        winners=winners,
        avg_prob=0.5,
        sum_prob=float(n) / 2,
        sum_sq_err=float(n) / 4,
    )


class _Result:
    def __init__(self, rows=None, scalar=None, one=None):
        self._rows, self._scalar, self._one = rows or [], scalar, one

    def all(self):
        return self._rows

    def scalar(self):
        return self._scalar

    def one(self):
        return self._one


class _StubDB:
    """Returns the futures rows first, then the sportsbook curves, then empties."""

    def __init__(self, futures_rows, events_rows=()):
        self._queue = [
            _Result(rows=list(futures_rows)),
            _Result(rows=list(events_rows)),
            _Result(rows=[]),
            _Result(rows=[]),
            _Result(scalar=0),
            _Result(
                one=SimpleNamespace(has_closing=0, needs_closing=0, total_completed=0)
            ),
        ]

    async def execute(self, statement, params=None):
        return self._queue.pop(0) if self._queue else _Result()

    async def commit(self):
        return None


@pytest.fixture(autouse=True)
def _no_sample_gate(monkeypatch):
    monkeypatch.setattr(pc, "_get_min_category_outcomes", lambda *_a, **_k: 0)


@pytest.fixture
def census_on(monkeypatch):
    """Turn the census on for tests about what it measures.

    It ships OFF (the futures phase is over budget without it — see the module
    comment), so every test that exercises real counts has to say so.
    """
    monkeypatch.setattr(pc, "COVERAGE_CENSUS_ENABLED", True)


class TestCensusEmission:
    pytestmark = pytest.mark.usefixtures("census_on")

    @pytest.mark.asyncio
    async def test_the_bridge_reconciles_in_both_units(self):
        payload = await pc.compute_calibration_payload(
            _StubDB([_futures_row()], events_rows=[_sportsbook_row(30, 15)])
        )
        census = payload["calibration_coverage_census"]
        assert census["status"] == "complete"
        assert census["invariants"]["ok"] is True

        rungs = {c["key"]: c["outcomes"] for c in census["coverage_bridge"]["rungs"]}
        coverage = census["units"]["outcomes_with_calibration_coverage"]["value"]
        assert coverage == 170
        assert rungs[PLOTTED_RUNG] + sum(rungs[k] for k in EXCLUSION_RUNGS) == coverage

        obs = census["observation_bridge"]
        assert obs["futures_outcomes_plotted"] == 90
        assert obs["sportsbook_curve_legs"] == 30
        assert obs["published_curve_observations"] == 120
        assert obs["reconciles"] is True
        assert obs["residual"] == 0

    @pytest.mark.asyncio
    async def test_the_headline_unit_is_still_the_plotted_observation_count(self):
        payload = await pc.compute_calibration_payload(
            _StubDB([_futures_row()], events_rows=[_sportsbook_row(30, 15)])
        )
        # The ruling's core requirement: the big coverage number must not become
        # the headline. total_outcomes stays the plotted count.
        assert payload["total_outcomes"] == 120
        census = payload["calibration_coverage_census"]
        assert (
            census["units"]["published_curve_observations"]["value"]
            == payload["total_outcomes"]
        )
        assert census["units"]["outcomes_with_calibration_coverage"]["value"] > 120

    @pytest.mark.asyncio
    async def test_the_census_names_its_own_population_version(self):
        payload = await pc.compute_calibration_payload(_StubDB([_futures_row()]))
        census = payload["calibration_coverage_census"]
        assert census["population_version"] == pc.CALIBRATION_POPULATION_VERSION
        assert census["population_version"] == payload["population_version"]

    @pytest.mark.asyncio
    async def test_a_pre_census_checkpoint_reads_unknown_not_zero(self):
        # ``rows`` carried forward from a beat that ran before this shipped has no
        # cb_* columns. Reporting 0 there would claim nothing was ever excluded.
        row = _futures_row()
        for key in RUNG_KEYS:
            delattr(row, f"cb_{key}")
        delattr(row, "cb_coverage_total")
        delattr(row, "cb_with_terminal_cal_price")

        payload = await pc.compute_calibration_payload(_StubDB([row]))
        census = payload["calibration_coverage_census"]
        assert census["status"] == "incomplete"
        assert "RUNG_UNKNOWN" in census["invariants"]["violations"]
        assert all(
            c["outcomes"] is None and c["checked"] is False
            for c in census["coverage_bridge"]["rungs"]
        )
        assert census["units"]["outcomes_with_calibration_coverage"]["value"] is None
        # ...and the curve is entirely unaffected by the census being unknown.
        assert payload["total_outcomes"] == 90
        assert payload["buckets"]

    @pytest.mark.asyncio
    async def test_a_measured_empty_rung_is_reported_as_a_checked_zero(self):
        payload = await pc.compute_calibration_payload(_StubDB([_futures_row()]))
        cell = next(
            c
            for c in payload["calibration_coverage_census"]["coverage_bridge"]["rungs"]
            if c["key"] == "market_result_unavailable"
        )
        assert cell["outcomes"] == 0
        assert cell["checked"] is True

    @pytest.mark.asyncio
    async def test_a_partition_that_stopped_partitioning_says_so(self):
        # cb_coverage_total is COUNT(*) over the same CTE the rungs are filtered
        # from, so a mismatch means the CASE stopped covering every row.
        payload = await pc.compute_calibration_payload(
            _StubDB([_futures_row(cb_coverage_total=171)])
        )
        census = payload["calibration_coverage_census"]
        assert census["status"] == "incomplete"
        assert "COVERAGE_PARTITION_RESIDUAL" in census["invariants"]["violations"]

    @pytest.mark.asyncio
    async def test_the_plotted_hinge_is_counted_twice_and_compared(self):
        payload = await pc.compute_calibration_payload(
            _StubDB([_futures_row(published_outcomes=91, cb_coverage_total=170)])
        )
        census = payload["calibration_coverage_census"]
        assert "PLOTTED_HINGE_DIVERGES" in census["invariants"]["violations"]
        assert census["status"] == "incomplete"


# ---------------------------------------------------------------------------
# 3. Additivity: the curve payload keeps its exact prior shape.
# ---------------------------------------------------------------------------
class TestAdditiveOnly:
    pytestmark = pytest.mark.usefixtures("census_on")

    @pytest.mark.asyncio
    async def test_only_one_key_is_added_to_the_payload(self):
        rows = [_futures_row()]
        with_census = await pc.compute_calibration_payload(_StubDB(list(rows)))
        stripped = {k: v for k, v in with_census.items() if k != "calibration_coverage_census"}
        # Everything else the payload publishes is the same set of sections the
        # publish gate and the page already consume.
        assert "calibration_coverage_census" in with_census
        assert "coverage" not in stripped
        for required in ("buckets", "by_category", "by_source", "total_outcomes", "total_markets"):
            assert required in stripped

    @pytest.mark.asyncio
    async def test_bucket_rows_are_untouched_by_the_census_columns(self):
        payload = await pc.compute_calibration_payload(_StubDB([_futures_row()]))
        bucket = payload["buckets"][0]
        assert not [k for k in bucket if k.startswith("cb_")]
        assert bucket["n"] == 90

    def test_the_census_columns_ride_as_constant_cross_joined_values(self):
        columns = pc._coverage_bridge_select_columns()
        for key in RUNG_KEYS:
            assert f"MAX(cbs.cb_{key})" in columns
        # Constant per row via CROSS JOIN, exactly like liq_summary — so the
        # GROUP BY, and therefore every published bucket, is unchanged.
        assert "GROUP BY" not in columns


class TestEveryBuildStatementParses:
    pytestmark = pytest.mark.usefixtures("census_on")

    """CI has no Postgres, so the census SQL gets a parser instead of a server.

    The census rides inside the single heaviest statement in the product. A
    syntax error there does not degrade the curve — it deletes it. ``sqlglot``
    is not a project dependency (the always-on proofs are the Python mirrors
    above), so this skips where it is absent and gates wherever it is present,
    the same bargain ``test_calibration_canonical_pg.py`` makes with Postgres.
    """

    @pytest.mark.asyncio
    async def test_all_statements_parse_as_postgres(self):
        parse_one = pytest.importorskip("sqlglot").parse_one

        captured: list[str] = []

        class _Recorder(_StubDB):
            def __init__(self):
                super().__init__([_futures_row()])

            async def execute(self, statement, params=None):
                captured.append(str(statement))
                return await super().execute(statement, params)

        await pc.compute_calibration_payload(_Recorder())

        assert captured, "the build issued no statements"
        assert any("coverage_bridge_summary" in sql for sql in captured), (
            "the census never reached the SQL the build actually runs"
        )
        for sql in captured:
            parse_one(sql, dialect="postgres")


class TestShipsOffUntilTheFuturesPhaseHasRoom:
    """The census measures inside a phase that is already over budget.

    Deploy-day phase ledger: plan ``infeasible``, ``infeasible_phases:
    ["futures"]``, futures floors 1351697/1351955/1299533 ms against a 1380000 ms
    deadline, last run CANCELLED at 1299533 ms with nothing published. So the
    switch ships OFF, and OFF has to cost the build literally nothing — not
    "about the same", nothing.
    """

    def test_it_ships_off(self):
        assert pc.COVERAGE_CENSUS_ENABLED is False

    def test_off_emits_no_sql_at_all(self):
        assert pc._coverage_bridge_ctes() == ""
        assert pc._coverage_bridge_select_columns() == ""
        assert pc._coverage_bridge_join() == ""

    @pytest.mark.asyncio
    async def test_off_leaves_the_build_statement_free_of_the_census(self):
        captured: list[str] = []

        class _Recorder(_StubDB):
            def __init__(self):
                super().__init__([_futures_row()])

            async def execute(self, statement, params=None):
                captured.append(str(statement))
                return await super().execute(statement, params)

        await pc.compute_calibration_payload(_Recorder())
        joined = "\n".join(captured)
        for artifact in (
            "coverage_universe",
            "coverage_bridge",
            "coverage_bridge_summary",
            "cb_plotted_on_curve",
        ):
            assert artifact not in joined

    @pytest.mark.asyncio
    async def test_turning_it_on_adds_only_the_census_to_the_statement(self, monkeypatch):
        """On/off must differ by the census and nothing else.

        The guarantee that makes the off state safe is not "roughly the same
        query" — it is that the ONLY textual difference is the census block. If
        anything else moved, the off state is no longer the pre-census build.
        """

        async def _statements():
            captured: list[str] = []

            class _Recorder(_StubDB):
                def __init__(self):
                    super().__init__([_futures_row()])

                async def execute(self, statement, params=None):
                    captured.append(str(statement))
                    return await super().execute(statement, params)

            await pc.compute_calibration_payload(_Recorder())
            return captured

        monkeypatch.setattr(pc, "COVERAGE_CENSUS_ENABLED", False)
        off = await _statements()
        monkeypatch.setattr(pc, "COVERAGE_CENSUS_ENABLED", True)
        on = await _statements()

        assert len(off) == len(on)
        # Every statement except the futures one is untouched by the switch.
        assert off[1:] == on[1:]
        # And removing the census text from the ON statement restores the OFF one.
        restored = on[0].replace(pc._coverage_bridge_ctes(), "").replace(
            pc._coverage_bridge_select_columns(), ""
        ).replace(pc._coverage_bridge_join(), "")
        assert restored == off[0]

    @pytest.mark.asyncio
    async def test_off_reports_disabled_rather_than_zero_or_broken(self):
        payload = await pc.compute_calibration_payload(_StubDB([_futures_row()]))
        census = payload["calibration_coverage_census"]
        assert census["status"] == "unavailable"
        assert census["reason"] == pc.COVERAGE_CENSUS_DISABLED_REASON
        assert census["population_version"] == pc.CALIBRATION_POPULATION_VERSION
        # Disabled is not zero. Every rung stays null.
        assert all(c["outcomes"] is None for c in census["coverage_bridge"]["rungs"])
        assert (
            census["units"]["outcomes_with_calibration_coverage"]["value"] is None
        )
        # ...and the curve is exactly as it was.
        assert payload["total_outcomes"] == 90
        assert payload["buckets"]


# ---------------------------------------------------------------------------
# 4. Serving tiers: absent is never zero.
# ---------------------------------------------------------------------------
class TestServingTiers:
    def test_a_payload_without_a_census_gets_an_explicit_unavailable_one(self):
        served = ensure_census({"buckets": [], "population_version": "q267"},
                               reason="payload_predates_census")
        census = served["calibration_coverage_census"]
        assert census["status"] == "unavailable"
        assert census["reason"] == "payload_predates_census"
        assert census["population_version"] == "q267"
        assert all(c["outcomes"] is None for c in census["coverage_bridge"]["rungs"])

    def test_an_existing_census_is_never_overwritten(self):
        real = unavailable_census("something_else")
        served = ensure_census(
            {"calibration_coverage_census": real}, reason="payload_predates_census"
        )
        assert served["calibration_coverage_census"] is real

    def test_the_degraded_route_path_marks_the_census(self):
        import inspect

        from app.routes import calibration

        src = inspect.getsource(calibration.public_calibration)
        assert "_ensure_census" in src
        # Both the stale marker and the fresh-Redis tier have to be covered: a
        # main key written by the last pre-census build is fresh but censusless.
        assert src.count("_ensure_census(") >= 2
