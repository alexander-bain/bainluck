"""CAL-P003 — the NEVER-GRADED Polymarket cohort admitted to the CLOB rail.

Production measurement 2026-08-07 that motivates these tests: 273,438 resolved
Polymarket outcomes (~133,576 markets) carry NO resolution_source at all, so
`is_winner` is still the column DEFAULT False. precompute_calibration reads that
as UNKNOWN truth (`is_no_winner_market`) and holds them off the published curve —
246,489 of them (90.1%) already have a calibration price, i.e. they are priced
forecasts we simply never graded.

The CLOB drain could already grade them (same venue, same mapper), but its
candidate predicate silently excluded the entire class: `bool_or(resolution_source
= ANY('pass2_loser','all_losers'))` over all-NULL sources evaluates to NULL, never
TRUE, so the HAVING drops every row. These tests pin the fix, and pin that the
existing cohort's predicate did not move.
"""

import inspect

from app.tasks.clob_resolve import (
    _COHORT_DROPPED,
    _COHORT_NEVER_GRADED,
    _WRITE_SOURCE_NEVER_GRADED,
    _cohort_having,
    _cohort_params,
    _load_cohort,
    _load_cohort_stratified,
)
from app.utils.resolution_authority import (
    CALIBRATION_TRUTH_ELIGIBLE_SOURCES,
    authority_tier,
    is_calibration_truth_eligible,
)


# ---------------------------------------------------------------------------
# The cohort predicate
# ---------------------------------------------------------------------------


def test_never_graded_predicate_requires_every_outcome_sourceless():
    """bool_and(... IS NULL): a partially-graded market is NOT this cohort.

    bool_or would admit a market where one outcome was already authoritatively
    graded, and the drain would then rewrite alongside a standing authority.
    """
    having = _cohort_having(_COHORT_NEVER_GRADED)
    assert "bool_and(fo.resolution_source IS NULL)" in having
    assert "bool_or(fo.resolution_source" not in having


def test_never_graded_predicate_still_only_looks_at_uncrowned_markets():
    """Shared with the dropped cohort: never touch a market that has a winner."""
    assert "bool_or(fo.is_winner) IS NOT TRUE" in _cohort_having(_COHORT_NEVER_GRADED)


def test_dropped_cohort_predicate_is_unchanged():
    """Regression guard: admitting a new cohort must not move the existing one."""
    having = _cohort_having(_COHORT_DROPPED)
    assert "bool_or(fo.resolution_source = ANY(:srcs))" in having
    assert "bool_and" not in having


def test_unknown_cohort_falls_back_to_dropped_not_to_the_wider_class():
    """Fail CLOSED: a typo must never silently widen the write population."""
    assert _cohort_having("nonsense") == _cohort_having(_COHORT_DROPPED)


def test_srcs_bind_param_present_exactly_when_the_sql_references_it():
    """A `:srcs` in the SQL with no bind (or vice versa) raises at execute time."""
    for cohort in (_COHORT_DROPPED, _COHORT_NEVER_GRADED, "nonsense"):
        sql = _cohort_having(cohort)
        params = _cohort_params(cohort)
        assert (":srcs" in sql) == ("srcs" in params), cohort


def test_never_graded_cohort_takes_no_srcs_param():
    assert _cohort_params(_COHORT_NEVER_GRADED) == {}


# ---------------------------------------------------------------------------
# The cohort is reachable from both loaders (the drain's and Batch-0's)
# ---------------------------------------------------------------------------


def test_both_loaders_accept_a_cohort_and_default_to_dropped():
    """Default-unchanged: every existing caller keeps the old population."""
    for fn in (_load_cohort, _load_cohort_stratified):
        sig = inspect.signature(fn)
        assert sig.parameters["cohort"].default == _COHORT_DROPPED, fn.__name__


def test_loaders_build_their_having_from_the_shared_helper():
    """Producer/Batch-0 drift is the failure mode: one predicate, two callers."""
    for fn in (_load_cohort, _load_cohort_stratified):
        src = inspect.getsource(fn)
        assert "_cohort_having(cohort)" in src, fn.__name__
        assert "_cohort_params(cohort)" in src, fn.__name__


# ---------------------------------------------------------------------------
# Write-source registration (binding spec lines 22/23/25)
# ---------------------------------------------------------------------------


def test_new_write_source_is_tier3_authoritative():
    assert authority_tier(_WRITE_SOURCE_NEVER_GRADED) == 3


def test_new_write_source_may_grade_the_curve():
    """Spec line 23 — the whole point is re-entering the curve. Sources fail
    CLOSED, so an unregistered name would be silently curve-ineligible."""
    assert is_calibration_truth_eligible(_WRITE_SOURCE_NEVER_GRADED)
    assert _WRITE_SOURCE_NEVER_GRADED in CALIBRATION_TRUTH_ELIGIBLE_SOURCES


def test_new_write_source_is_distinct_from_the_existing_clob_sources():
    """Spec line 25 — this cohort must be revertible in ONE predicate without
    also reverting the #989 cohort."""
    assert _WRITE_SOURCE_NEVER_GRADED not in ("clob_authoritative", "clob_ordinal")


# ---------------------------------------------------------------------------
# Batch-0 stays dry-run until the cohort is blessed (Amendment-1 precedent)
# ---------------------------------------------------------------------------


def test_never_graded_cohort_is_reachable_only_by_explicit_argument():
    """CAL-P065 (#1912) — the deliberate, test-visible act this test asked for.

    It used to read:

        drain_src = inspect.getsource(clob_resolve.clob_resolve_drain)
        assert _COHORT_NEVER_GRADED not in drain_src
        assert _WRITE_SOURCE_NEVER_GRADED not in drain_src

    and it said of itself: *"If a later queue wires it up, this test is the
    deliberate, test-visible act that records it."* This is that queue.

    Worth recording HOW it behaved when the wiring actually landed, because it
    is the argument for the whole behavioral-specimen turn. The drain gained a
    ``cohort`` parameter that reaches the never-graded population — the exact
    change the test existed to catch — and the test **passed anyway**. It greps
    for the string VALUES (``"never_graded"``, ``"clob_never_graded"``), which
    a parameter named ``cohort`` never spells. It would equally have failed on
    a comment that merely mentioned the words. A source-string test is blind to
    the change it was written for and loud about changes that do not matter.

    So the property is now stated as behaviour: the default is the dropped
    cohort, the wider cohort requires someone to ASK for it by name, and an
    unrecognised value falls back closed. The write half is guarded by the
    specimen suite (``tests/test_pm_market_ownership.py``), which drives the
    real function and asserts on the UPDATE it issues.
    """
    from app.tasks import clob_resolve

    sig = inspect.signature(clob_resolve.clob_resolve_drain)
    assert sig.parameters["cohort"].default == _COHORT_DROPPED

    # Reachable — but only by naming it.
    assert _cohort_having(_COHORT_NEVER_GRADED) != _cohort_having(_COHORT_DROPPED)
    assert "bool_and(fo.resolution_source IS NULL)" in _cohort_having(
        _COHORT_NEVER_GRADED
    )

    # And the 25,264-market write stays an attended apply: the never-graded
    # write source is not in the drain's default tiers, so no beat can reach it.
    assert _WRITE_SOURCE_NEVER_GRADED not in clob_resolve._DEFAULT_WRITE_TIERS


def test_batch0_writes_nothing():
    from app.tasks import clob_resolve

    src = inspect.getsource(clob_resolve.clob_never_graded_batch0)
    assert "UPDATE" not in src.upper()
    assert "session.commit" not in src


def test_batch0_uses_the_stratified_loader_on_the_new_cohort():
    """Amendment-1 condition 1: the sample must span ingestion vintages, or the
    yield estimate is just a reading of the newest poller version."""
    from app.tasks import clob_resolve

    src = inspect.getsource(clob_resolve.clob_never_graded_batch0)
    assert "_load_cohort_stratified" in src
    assert "cohort=_COHORT_NEVER_GRADED" in src
