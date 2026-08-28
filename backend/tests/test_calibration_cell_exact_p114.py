"""CAL-P114 — guards for the exact per-cell replica.

The class this suite exists to catch: **an instrument that quietly stops being
the producer.** ``calibration_cell_exact`` earns the word "exact" from one
property only — it does not re-implement the population predicate, it imports
``_calibration_population_ctes`` from ``precompute_calibration`` and appends a
GROUP BY. Every failure mode below is a way that property can be lost while the
script still runs and still prints plausible numbers, which is precisely the
CAL-P108 finding wearing an instrument's coat.

1. **The chain stops being imported.** Someone inlines "just the bit we need"
   and the rail silently becomes a fourth re-implementation — the thing the
   shape census and the replica already are, and the reason neither could
   measure ``kalshi/economics`` (census 69,653 / 4.65 / **+4.27** against the
   payload's 28,613 / 5.29 / **-0.47**: 2.4x the rows and the wrong SIGN).
2. **The comment stripper eats a quoted literal.** The db-query guard rejects
   the producer's SQL outright because prose comments in it contain semicolons,
   so stripping is mandatory — but this chain has outcome names and regexes
   with ``--`` INSIDE quotes, and a naive ``split('--')`` would delete half a
   predicate and leave valid SQL over a different population.
3. **A semicolon survives.** Then every query is refused with
   "Multi-statement queries not allowed" and the sweep reports nothing measured.
4. **The shape join loses its scoping predicate.** ``SHAPE_JOIN`` aggregates
   ``futures_outcomes``; without ``market_id IN (SELECT market_id FROM
   market_info)`` the planner prices a full 3.3M-row scan and the chunk never
   returns — measured, not theorised: it recursively split to the depth limit
   until the run was killed. Same defect class as CAL-P039's ``vm_stats``.
5. **The cell scoping stops being applied**, so ``--category economics`` folds
   the whole curve and every class share is wrong.
"""

from __future__ import annotations

import importlib.util
import re
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


cce = _load("calibration_cell_exact")


class TestTheChainIsTheProducers:
    """The one property the word 'exact' rests on."""

    def test_sql_carries_the_producers_own_cte_names(self):
        sql = cce.cell_sql("kalshi", "economics", 0, 10_000_000, "none")
        # These CTEs exist only in `_calibration_population_ctes`. If the chain
        # were re-implemented locally they could be spelled anything.
        for cte in ("market_info", "market_result_shape", "virtual_market",
                    "nonexclusive_bundle_markets", "mex_field_divisor",
                    "normalized", "mode_prices", "deduped"):
            assert f"{cte} AS (" in sql, f"{cte} missing — chain not imported"

    def test_the_population_function_is_imported_not_copied(self):
        src = (SCRIPTS / "calibration_cell_exact.py").read_text()
        assert "from app.tasks.precompute_calibration import" in src
        assert "_calibration_population_ctes" in src
        # A local re-definition is the exact regression this guards.
        assert "def _calibration_population_ctes" not in src

    def test_the_frozen_file_is_only_read(self):
        """Ruling 009 freezes COMMITS to the producer, not reads.

        The instrument must never write to it, and must never be the reason
        someone edits it. Nothing in this script may name a write.
        """
        src = (SCRIPTS / "calibration_cell_exact.py").read_text()
        for verb in ("UPDATE futures_", "INSERT INTO", "DELETE FROM"):
            assert verb not in src, f"{verb!r} in a read-only instrument"


class TestCellScoping:
    def test_scoping_reaches_market_info(self):
        sql = cce.cell_sql("kalshi", "economics", 100, 200, "none")
        assert "fm.source = 'kalshi'" in sql
        assert "= 'economics'" in sql
        assert "fm.id >= 100" in sql and "fm.id < 200" in sql

    def test_two_cells_do_not_produce_the_same_sql(self):
        a = cce.cell_sql("kalshi", "economics", 0, 10, "none")
        b = cce.cell_sql("kalshi", "tech", 0, 10, "none")
        assert a != b


class TestCommentStripping:
    def test_semicolons_do_not_survive(self):
        """A survivor is refused by the guard as a second statement."""
        for dim in sorted(cce.DIMENSIONS):
            sql = cce.cell_sql("kalshi", "economics", 0, 10, dim)
            assert ";" not in sql, f"--by {dim} leaks a semicolon"

    def test_a_quoted_double_dash_is_preserved(self):
        """The failure that would be SILENT: a literal containing ``--``.

        A naive stripper turns ``WHERE name = 'a--b' AND x = 1`` into
        ``WHERE name = 'a`` — which is not even valid SQL here, but the same
        stripper applied one character later produces valid SQL over a
        different population. Both are unacceptable; this pins the literal.
        """
        got = cce._strip_sql_comments("SELECT 1 WHERE name = 'a--b' AND x = 1")
        assert got == "SELECT 1 WHERE name = 'a--b' AND x = 1"

    def test_a_real_comment_is_removed_including_its_semicolon(self):
        got = cce._strip_sql_comments(
            "SELECT 1  -- this comment; has a semicolon\nFROM t")
        assert ";" not in got
        assert "SELECT 1" in got and "FROM t" in got

    def test_the_producers_own_sql_is_stripped_clean(self):
        """Red-first evidence, not a hypothetical: the UNSTRIPPED chain really
        does carry semicolons, so the stripper is load-bearing rather than
        tidy. If the producer's comments ever lose them this assertion fails
        loudly and the guard can be retired deliberately."""
        from app.tasks.precompute_calibration import (
            _calibration_population_ctes,
        )
        raw = _calibration_population_ctes()
        assert ";" in raw, "producer SQL no longer needs stripping — re-check"
        assert ";" not in cce._strip_sql_comments(raw)


class TestPlannerPredicatesAreStructural:
    def test_shape_join_keeps_its_scoping_conjunct(self):
        """CAL-P039's defect, arriving through a different door.

        Without this conjunct the aggregate over ``futures_outcomes`` has no
        predicate and the chunk never returns. It reads as redundant with the
        ON clause, which is exactly why it would be 'tidied' away.
        """
        assert re.search(
            r"market_id\s+IN\s*\(\s*SELECT\s+market_id\s+FROM\s+market_info\s*\)",
            cce.SHAPE_JOIN), "SHAPE_JOIN lost its scoping predicate"
        # and it must survive comment stripping into the emitted SQL
        sql = cce.cell_sql("kalshi", "economics", 0, 10, "shape")
        assert "FROM market_info" in sql


class TestFoldArithmetic:
    def test_perfect_calibration_is_zero(self):
        bins = {0: {"n": 100, "w": 5, "sp": 5.0},
                9: {"n": 100, "w": 95, "sp": 95.0}}
        n, ece, gap = cce.fold(bins)
        assert (n, ece, gap) == (200, 0.0, 0.0)

    def test_ece_is_absolute_and_gap_is_signed(self):
        """The whole reason ``kalshi/economics`` looks fine on the headline:
        opposite-signed bins cancel in the gap and do NOT cancel in the ECE."""
        bins = {2: {"n": 100, "w": 15, "sp": 25.0},   # over-predicts  +10pp
                7: {"n": 100, "w": 85, "sp": 75.0}}   # under-predicts -10pp
        n, ece, gap = cce.fold(bins)
        assert n == 200
        assert ece == 10.0
        assert gap == 0.0

    def test_empty_folds_to_none_not_zero(self):
        """``could not measure`` must never render as ``measured zero``
        (ruling 075, second clause)."""
        assert cce.fold({}) == (0, None, None)

    def test_dimensions_are_three_tuples(self):
        """A 2-tuple entry silently drops its extra CTE and the key expression
        then references a table that is not in the WITH-body."""
        for name, spec in cce.DIMENSIONS.items():
            assert len(spec) == 3, f"{name} is not (expr, join, pre)"
