"""CAL-P117 — guards for the four dimensions rank 1's design was measured on.

CAL-P114's suite guards the property that makes the rail *exact* (the chain is
the producer's, imported). This suite guards the property that makes a
DIMENSION honest: **the class it prints is the rule it claims to bench.**

That is a different failure and it is quieter. A dimension whose CASE has
drifted from the predicate it is standing in for still runs, still partitions
the cell, and still produces a policy table — one that describes a rule nobody
is going to ship. `polymarket/baseball`'s design turns on four arms and each is
a re-rendering of a predicate that lives somewhere else:

============  ============================================================
arm           where the real predicate lives
============  ============================================================
R1            ``half_spike_pair_exclusion`` on ``program/calibration-99``
              — ``hs_half_legs = 2``, a half leg being
              ``ROUND(opening_probability, 4) = 0.5000``
R2            ``published_pair_incoherent_market_predicate`` on the same
              branch — coherent at opening, incoherent as published,
              against ``PAIR_SUM_TOLERANCE``
R3            new here; its threshold is **RULE E's** 1.15, which is also
              ``SUMBAND``'s ``a_sum_le_1.15`` band edge
M1            new here; the [0.45, 0.55] band is
              ``POLY_PLACEHOLDER_EXCLUDE``'s band, already live in the
              producer
============  ============================================================

Every test below is a way one of those correspondences can be broken while the
sweep keeps printing numbers. The three that would be SILENT are marked.
"""

from __future__ import annotations

import importlib.util
import re
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"

NEW_DIMENSIONS = ("pair", "pairtype", "pairsum", "policy", "policy2", "cpdrift")


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


cce = _load("calibration_cell_exact")


class TestTheToleranceIsImportedNotCopied:
    """CAL-P115's rule, applied to the second constant that has two homes.

    An equal copy is not the same thing as the imported name: it passes on the
    day it is written and drifts on the next edit to either side. So the test
    is identity against the module the writer gate reads, not equality against
    ``0.02``.
    """

    def test_pair_tolerance_is_the_writer_gates_own_constant(self):
        from app.utils.pair_opening_coherence import PAIR_SUM_TOLERANCE

        assert cce.PAIR_TOLERANCE is PAIR_SUM_TOLERANCE

    def test_the_source_does_not_restate_the_number(self):
        src = (SCRIPTS / "calibration_cell_exact.py").read_text()
        # The literal may appear nowhere except as part of the import comment.
        offenders = [
            ln for ln in src.splitlines()
            if "0.02" in ln and not ln.lstrip().startswith("#")
        ]
        assert not offenders, f"tolerance restated as a literal: {offenders}"

    def test_the_tolerance_reaches_the_rendered_sql(self):
        for dim in ("pair", "pairtype", "pairsum", "policy", "policy2"):
            sql = cce.cell_sql("polymarket", "baseball", 0, 10, dim)
            assert f"- 1) <= {cce.PAIR_TOLERANCE}" in sql, dim
            assert f"- 1) > {cce.PAIR_TOLERANCE}" in sql, dim


class TestTheOverUnderShapeMatchesTheBranchPredicate:
    """R1 and R2 both rest on 'what is an Over/Under pair', and the branch
    hoisted that into ONE function precisely so two rules could not each carry
    their own copy. This rail is a third caller and must agree with it."""

    def test_exactly_two_legs_named_over_and_under(self):
        for frag in ("pr_n = 2", "pr_over = 1", "pr_under = 1"):
            assert frag in cce.PAIR_EXPR, frag

    def test_the_name_test_is_lower_btrim_exact(self):
        """SILENT if broken. ``LIKE 'over%'`` would swallow
        ``Over 2.5 Goals`` and every threshold leg in the cell, and the fold
        would still print a clean-looking partition."""
        assert "lower(btrim(fo5.name)) = 'over'" in cce.PAIR_JOIN
        assert "lower(btrim(fo5.name)) = 'under'" in cce.PAIR_JOIN

    def test_half_spike_is_the_rounded_exact_value_on_the_OPENING_column(self):
        """SILENT if broken. CAL-P094's spike is a property of
        ``opening_probability``; testing the published column instead would
        select a different population and still return rows."""
        assert re.search(
            r"ROUND\(fo5\.opening_probability,\s*4\)\s*=\s*0\.5000",
            cce.PAIR_JOIN), "half-spike leg test drifted off opening_probability"

    def test_both_pair_sums_are_read_only_over_a_COMPLETE_pair(self):
        """``SUM`` skips NULLs, so 0.98 from one priced leg and 0.98 from two
        are indistinguishable without the leg counts — gotcha #53's shape,
        inside an aggregate. The branch predicate carries both counts and so
        must this."""
        for frag in ("pr_open_legs = 2", "pr_pub_legs = 2"):
            assert frag in cce.PAIR_EXPR, frag

    def test_the_published_price_is_the_COALESCE_the_curve_publishes(self):
        assert ("COALESCE(fo5.calibration_probability, fo5.opening_probability)"
                in cce.PAIR_JOIN)


class TestTheArmsArePartitions:
    """A policy table is a pooling of classes. If two arms can both claim one
    row the table double-counts an exclusion — CERT-403B's finding, which is
    why these are ORDERED CASEs and not independent flags."""

    def test_every_new_dimension_has_a_total_else_branch(self):
        for name in NEW_DIMENSIONS:
            expr = cce.DIMENSIONS[name][0]
            assert "ELSE" in expr, f"{name} can key NULL"

    def test_policy_and_policy2_agree_on_r1_and_r2(self):
        """The two folds are read against each other in the design document
        (2.79 vs 2.78 on the same conjunction). That comparison is only
        legitimate if the arms are the same text."""
        for frag in ("r1_half_spike", "r2_pub_incoherent"):
            assert frag in cce.POLICY_EXPR and frag in cce.POLICY2_EXPR

    def test_r1_is_tested_before_r2(self):
        """A pair that opens 0.5000/0.5000 opens COHERENT by construction, so
        it can also satisfy R2 if its published sum drifts. Precedence is what
        makes the overlap reportable instead of double-counted; the design
        document states which arm it is charged to and this pins that."""
        assert (cce.POLICY_EXPR.index("r1_half_spike")
                < cce.POLICY_EXPR.index("r2_pub_incoherent"))

    def test_m1_is_tested_before_the_props_flag_is_read(self):
        """The succession question — 'can the column predicate retire the name
        match' — is only an arithmetic one if M1 gets first refusal on the rows
        both could claim. Reverse this and R3's residual silently absorbs M1."""
        assert (cce.POLICY2_EXPR.index("m1_forced_to_half")
                < cce.POLICY2_EXPR.index("player props"))


class TestThresholdsAreBorrowedNotInvented:
    def test_r3_uses_rule_Es_own_constant(self):
        """1.15 is the structural not-a-partition threshold RULE E already
        carries, and it is also SUMBAND's band edge — so the design's
        'props with sum > 1.15' is exactly the union of SUMBAND's b/c/d/e
        bands and the two tables can be read against each other."""
        assert "ms.msum > 1.15" in cce.POLICY2_EXPR
        assert "ms.msum <= 1.15 THEN 'a_sum_le_1.15'" in cce.SUMBAND_ONLY_EXPR

    def test_the_sum_band_is_defined_once_and_composed(self):
        """Two dimensions that band the same quantity must band it identically
        or their tables cannot be read against each other."""
        assert cce.SUMBAND_ONLY_EXPR in cce.SUMBAND_EXPR
        assert cce.SUMBAND_ONLY_EXPR in cce.PAIRSUM_EXPR
        assert cce.SUMBAND_ONLY_EXPR in cce.POLICY_EXPR

    def test_m1_uses_the_live_placeholder_band(self):
        """[0.45, 0.55] is ``POLY_PLACEHOLDER_EXCLUDE``'s band, already in the
        producer. A rule that invents its own near-0.50 window would be
        measuring a population the shipped filter does not know about."""
        from app.tasks.precompute_calibration import POLY_PLACEHOLDER_EXCLUDE

        assert ">= 0.45" in POLY_PLACEHOLDER_EXCLUDE
        assert "<= 0.55" in POLY_PLACEHOLDER_EXCLUDE
        assert "BETWEEN 0.45 AND 0.55" in cce.DRIFT_EXPR
        assert "BETWEEN 0.45 AND 0.55" in cce.POLICY2_EXPR

    def test_the_drift_ladder_keeps_its_control_rung(self):
        """SILENT if broken. Without ``c_moved_elsewhere`` the fold cannot tell
        'the published price moved a long way' from 'the published price was
        replaced by a coin flip', and the rule would delete real line
        movement. The control measured 12.62 with a TWO-SIDED gap against the
        forced class's 44.36 with a one-sided one; drop it and that comparison
        disappears without any test going red."""
        assert "c_moved_elsewhere" in cce.DRIFT_EXPR
        assert "a_forced_to_half" in cce.DRIFT_EXPR
        assert "b_pulled_to_half" in cce.DRIFT_EXPR


class TestEveryJoinAliasTheKeyUsesIsActuallyJoined:
    """A key expression that references an alias the dimension does not join is
    a SQL error at sweep time — 60 chunks in, after several minutes of a run
    that had already cost real production query budget."""

    ALIASES = ("pr", "ms", "sh", "fm4", "fo6", "fo7")

    def test_aliases_resolve(self):
        for name in NEW_DIMENSIONS:
            expr, join, pre = cce.DIMENSIONS[name]
            for alias in self.ALIASES:
                if re.search(rf"\b{alias}\.", expr):
                    assert (re.search(rf"\)\s*{alias}\s+ON\b", join)
                            or re.search(rf"\b\w+\s+{alias}\s+ON\b", join)), (
                        f"--by {name} keys on {alias}. but never joins it")

    def test_the_msums_cte_is_supplied_wherever_ms_is_keyed(self):
        for name in NEW_DIMENSIONS:
            expr, _join, pre = cce.DIMENSIONS[name]
            if "ms.msum" in expr:
                assert "msums AS (" in pre, f"--by {name} keys ms. with no CTE"

    def test_the_shape_scoping_conjunct_survives_into_the_pair_joins(self):
        """CAL-P114's planner finding, inherited: PAIR_JOIN aggregates
        ``futures_outcomes`` the same way SHAPE_JOIN does and needs the same
        predicate or the chunk never returns."""
        assert re.search(
            r"market_id\s+IN\s*\(\s*SELECT\s+market_id\s+FROM\s+market_info\s*\)",
            cce.PAIR_JOIN)


class TestTheNewDimensionsRenderAtAll:
    def test_every_dimension_renders_semicolon_free_for_this_cell(self):
        for name in NEW_DIMENSIONS:
            sql = cce.cell_sql("polymarket", "baseball", 0, 10, name)
            assert ";" not in sql, f"--by {name} leaks a semicolon"
            assert "GROUP BY 1, 2" in sql
            assert "FROM deduped d" in sql

    def test_the_props_name_match_survives_comment_stripping(self):
        """``ILIKE '%player props%'`` is a quoted literal in a chain the
        stripper walks character by character. If the stripper ever mangles it
        the arm silently matches nothing and R3 reads as worthless."""
        sql = cce.cell_sql("polymarket", "baseball", 0, 10, "policy")
        assert "ILIKE '%player props%'" in sql
