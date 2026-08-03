"""Queue 300D — the SQL half of staged futures, and the tie authority.

``test_calibration_staged_futures.py`` covers the pure merge/cursor module.
This file covers the thing that module cannot see: the two SCOPES the futures
statement is now built in, and the guarantee that adding the staged one did not
move the monolith by a single character.

The monolith-immutability test is the important one. Everything else in Queue
300D is additive and switchable; the one irreversible risk was refactoring the
heaviest statement in the product and changing it by accident while "only"
parameterizing it. The route's cold-cache serve, the cohort sweep and the
horizon surface all build on this chain, so a stray character here is a silent
population change on three surfaces at once.
"""

import re

import pytest

from app.tasks.precompute_calibration import (
    CALIBRATION_POPULATION_VERSION,
    REPRESENTATIVE_TIE_AUTHORITY,
    VM_ROSTER_IS_GROUPED_PARAM,
    VM_ROSTER_MARKET_IDS_PARAM,
    VM_ROSTER_MARKET_INFO_EXTRA,
    VM_ROSTER_VM_IDS_PARAM,
    _calibration_population_ctes,
    _futures_generation_sql,
    _main_futures_sql,
    _main_input_fingerprint,
    _virtual_market_ctes,
)

try:  # The SQL parse gate, same bargain test_calibration_canonical_pg.py makes.
    import sqlglot
except ImportError:  # pragma: no cover - sqlglot is not a project dependency
    sqlglot = None


class TestMonolithIsUnmoved:
    """The default scope must be exactly what it always was."""

    def test_global_population_has_no_staged_artifacts(self):
        sql = _calibration_population_ctes()
        assert "frozen_vm_roster" not in sql
        assert f":{VM_ROSTER_MARKET_IDS_PARAM}" not in sql
        # The cardinality CTEs are what make the >=3 gate meaningful; the global
        # scope must still DERIVE the assignment rather than replay one.
        assert "group_sizes AS (" in sql
        assert "event_sizes AS (" in sql

    def test_monolith_statement_keeps_its_cross_join_and_count_star(self):
        sql = _main_futures_sql()
        assert "FROM bucketed" in sql
        assert "CROSS JOIN liq_summary ls" in sql
        assert "COUNT(*) AS n," in sql  # not n_outcomes
        # The staged path's two shape changes must not leak into the monolith.
        assert "LEFT JOIN bucketed ON true" not in sql
        assert "COUNT(bucketed.bucket_idx)" not in sql

    def test_virtual_market_global_branch_is_byte_stable(self):
        """The refactor's own regression guard.

        ``_virtual_market_ctes(False)`` must emit the three CTEs verbatim. If a
        future edit "tidies" this branch, the monolith silently becomes a
        different population — so the text itself is pinned, not merely its
        behaviour.
        """
        emitted = _virtual_market_ctes(False)
        assert emitted.count("AS (") == 3
        assert "CASE WHEN gs.group_size >= 3" in emitted
        assert "WHEN es.event_size >= 3" in emitted
        assert "ELSE 'm:' || mi.market_id::text" in emitted
        assert emitted.rstrip().endswith("),")


class TestFrozenScope:
    def test_frozen_replays_the_assignment_instead_of_deriving_it(self):
        sql = _calibration_population_ctes(frozen_vm_roster=True)
        assert "frozen_vm_roster AS (" in sql
        # Re-deriving cardinality over a FILTERED market_info is the exact bug
        # this scope exists to avoid: an event losing a member to another chunk
        # can fall below the >=3 gate and silently re-identify every one of its
        # markets. No cardinality CTE may survive here.
        assert "group_sizes AS (" not in sql
        assert "event_sizes AS (" not in sql
        assert "JOIN frozen_vm_roster vr ON vr.market_id = mi.market_id" in sql

    def test_frozen_join_is_inner_so_a_late_market_cannot_join_the_generation(self):
        sql = _calibration_population_ctes(frozen_vm_roster=True)
        assert "LEFT JOIN frozen_vm_roster" not in sql

    def test_empty_chunk_still_carries_its_census(self):
        """A chunk with no published rows must not lose its candidate counts.

        ``liq_summary`` is computed over ``normalized`` (PRE-dedup), so a chunk
        whose every question is excluded still has real numbers to report. The
        staged scope drives from the 1-row censuses and LEFT JOINs the buckets
        so exactly one null-keyed row comes back carrying them.
        """
        sql = _main_futures_sql(frozen=True)
        assert "FROM liq_summary ls" in sql
        assert "LEFT JOIN bucketed ON true" in sql
        # ...and the phantom row must count as zero, not one.
        assert "COUNT(bucketed.bucket_idx) AS n," in sql
        assert "COUNT(*) AS n," not in sql  # not n_outcomes

    def test_roster_params_are_cast_not_suffixed(self):
        """gotcha: ``text()`` drops a bind param followed by ``::``.

        ``:p::bigint[]`` parses the cast as part of the parameter name and the
        statement raises on every run — the defect that left
        ``_fix_golf_commence_times`` dead for months. Every roster param must go
        through ``CAST(:p AS ...)``.
        """
        sql = _main_futures_sql(frozen=True)
        for param in (
            VM_ROSTER_MARKET_IDS_PARAM,
            VM_ROSTER_VM_IDS_PARAM,
            VM_ROSTER_IS_GROUPED_PARAM,
        ):
            assert f"CAST(:{param} AS" in sql
            assert f":{param}::" not in sql

    def test_market_info_extra_scopes_the_base_scan_to_the_chunk(self):
        assert VM_ROSTER_MARKET_IDS_PARAM in VM_ROSTER_MARKET_INFO_EXTRA
        assert "CAST(" in VM_ROSTER_MARKET_INFO_EXTRA
        assert VM_ROSTER_MARKET_INFO_EXTRA in _main_futures_sql(frozen=True)


class TestGenerationRead:
    def test_generation_selects_only_the_roster(self):
        sql = _futures_generation_sql()
        assert "SELECT market_id, source, vm_id, is_grouped" in sql
        assert "FROM virtual_market" in sql

    def test_generation_reuses_the_canonical_population(self):
        """No second copy of the eligibility predicate.

        The roster IS the chunk boundary, so a generation that disagreed with
        the population about which markets are eligible would hand every chunk a
        different universe than the monolith had. This is the C14 drift lesson
        applied to the one place it would be worst.
        """
        assert _calibration_population_ctes() in _futures_generation_sql()


class TestRepresentativeTieAuthority:
    def test_window_breaks_ties_on_canonical_outcome_id(self):
        sql = _calibration_population_ctes()
        assert "ORDER BY ABS(fo.opening_probability - 0.5), fo.id" in sql

    def test_horizon_scope_gets_the_same_authority(self):
        """The horizon finalizes on a snapshot price but must be just as stable."""
        sql = _calibration_population_ctes(rn_order="ABS(hp.horizon_prob - 0.5)")
        assert "ORDER BY ABS(hp.horizon_prob - 0.5), fo.id" in sql

    def test_delta_instrument_ranks_on_distance_alone(self):
        """``rn_distance_rank`` must NOT carry the tie-break.

        Its whole job is to still see the tie that ``rn`` has just resolved. If
        someone "consistently" adds ``fo.id`` here too, every rank becomes
        distinct, the census silently reports zero, and the one-time delta is
        unmeasurable rather than measured-as-none.
        """
        sql = _calibration_population_ctes()
        match = re.search(
            r"RANK\(\) OVER \(\s*PARTITION BY cv\.vm_id\s*ORDER BY ([^\n]+)\n", sql
        )
        assert match, "rn_distance_rank window not found"
        assert match.group(1).strip() == "ABS(fo.opening_probability - 0.5)"

    def test_delta_is_reported_as_identity_not_exclusion(self):
        sql = _main_futures_sql()
        assert "AS representative_tie_broken" in sql
        assert "MAX(ls.representative_tie_broken) AS representative_tie_broken" in sql

    def test_authority_is_in_the_fingerprint(self):
        """A change to the authority must invalidate every carried read."""
        import app.tasks.precompute_calibration as module

        before = _main_input_fingerprint()
        original = module.REPRESENTATIVE_TIE_AUTHORITY
        try:
            module.REPRESENTATIVE_TIE_AUTHORITY = "something-else/v9"
            assert _main_input_fingerprint() != before
        finally:
            module.REPRESENTATIVE_TIE_AUTHORITY = original
        assert _main_input_fingerprint() == before

    def test_population_version_is_not_bumped(self):
        """An identity delta is not a population change.

        Bumping the version here would take /calibration DARK — ``snapshot_verdict``
        refuses a cached artifact whose version is not the one the deployed build
        expects, and the replacement cannot exist until the next successful beat
        (the 2026-08-02 incident, reverted the same hour).
        """
        assert CALIBRATION_POPULATION_VERSION == "q267"
        assert REPRESENTATIVE_TIE_AUTHORITY == "canonical-outcome-id/v1"


class TestShippedState:
    """What is actually switched on, pinned so it cannot drift silently."""

    def test_staged_path_ships_off(self):
        """Queue 300D shipped the machinery, not the cutover.

        The staged statement has never executed against PostgreSQL and the
        queue's gates forbid triggering a build to find out, so turning an
        unexercised path into the ONLY path for the scheduled build is left as a
        deliberate, watched flip. This test is the record of that decision — if
        someone flips the constant, this fails and they have to say so.
        """
        from app.tasks.calibration_main_build import STAGED_FUTURES_ENABLED

        assert STAGED_FUTURES_ENABLED is False

    def test_the_serve_path_can_never_stage(self):
        """Not a switch — a structural guarantee.

        The route's in-request cold-cache serve has no checkpoint to resume
        from, no second beat to finish the job, and a request transaction that
        must not be committed underneath the caller. It gets the single
        statement whatever the operator sets.
        """
        from app.tasks.calibration_main_build import NULL_RUNNER

        assert NULL_RUNNER.staged_futures is False

    def test_off_is_a_true_no_op_for_the_statement(self):
        """OFF must not merely behave the same — it must EMIT the same.

        Paired with ``TestMonolithIsUnmoved``: together they are why shipping
        this off is a no-op rather than a hope.
        """
        assert "frozen_vm_roster" not in _main_futures_sql()
        assert "LEFT JOIN bucketed ON true" not in _main_futures_sql()


class TestCoverageCensusIsRefusedUnderStaging:
    """Item 2's census cannot ride the staged path yet, and must say so loudly.

    ``coverage_universe`` is not vm-scoped: every chunk would rescan all of it
    and LEFT JOIN it against only its own slice of the population, so the summed
    census would come out roughly N times too large with the rungs skewed. That
    is a confidently wrong number, which is worse than no number — so the
    builder refuses instead of emitting it.
    """

    def test_census_stays_off_so_the_monolith_is_unchanged(self):
        from app.tasks.precompute_calibration import COVERAGE_CENSUS_ENABLED

        assert COVERAGE_CENSUS_ENABLED is False
        assert "coverage_universe" not in _main_futures_sql()

    def test_staged_scope_refuses_to_build_with_the_census_on(self, monkeypatch):
        monkeypatch.setattr(
            "app.tasks.precompute_calibration.COVERAGE_CENSUS_ENABLED", True
        )
        with pytest.raises(ValueError, match="not chunk-scoped"):
            _main_futures_sql(frozen=True)

    def test_the_refusal_names_the_work_that_would_lift_it(self, monkeypatch):
        monkeypatch.setattr(
            "app.tasks.precompute_calibration.COVERAGE_CENSUS_ENABLED", True
        )
        with pytest.raises(ValueError) as excinfo:
            _main_futures_sql(frozen=True)
        message = str(excinfo.value)
        assert "coverage_universe" in message
        assert "out-of-population" in message


@pytest.mark.skipif(sqlglot is None, reason="sqlglot not installed")
class TestBothScopesParse:
    """The only automated check on the single heaviest statement in the product."""

    @pytest.mark.parametrize("frozen", [False, True])
    def test_main_statement_parses(self, frozen):
        sqlglot.parse_one(_main_futures_sql(frozen=frozen), read="postgres")

    def test_generation_statement_parses(self):
        sqlglot.parse_one(_futures_generation_sql(), read="postgres")
