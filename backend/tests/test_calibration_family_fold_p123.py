"""CAL-P123 — guards for the FAMILY and OUTCOME-NAME dimensions.

The suites for CAL-P117/118/121 guard that a dimension's ``CASE`` still says
what the rule it benches says. This one guards two properties those suites have
never had to:

* the new dimensions are **composed onto** ``calibration_cell_exact``'s chain
  rather than beside it, so the composition itself is the thing that can rot —
  a threshold or an arm can move upstream and leave this file folding a
  different subpopulation under the same word; and
* ``OUTCOME_NAME_EXPR`` has **overlapping arms in a deliberate order**. A
  one-outcome market satisfies ``on_d = 1`` as surely as an undifferentiated
  three-legged one does. Swap two lines and 33 rows of ``polymarket/cricket``
  move from ``d_lone_outcome`` into ``a_undifferentiated``, the table stays
  complete and plausible, and the class this lane owes Alex an answer about
  (12-CAL, the lone-claim filter) disappears into a class about something else.

The tests marked **SILENT** are the ones whose breakage still produces a
complete, plausible, well-formed table.
"""

from __future__ import annotations

import importlib.util
import re
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


cff = _load("calibration_family_fold")
cce = cff.cce


def _norm(sql: str) -> str:
    """Whitespace-insensitive, so a reflow is not a failure and a reword is."""
    return re.sub(r"\s+", " ", sql).strip()


class TestTheFamilyIsTheTAILOfTheName:
    """Polymarket nests ``series: fixture - family``. A dimension that takes
    the FIRST separator instead of the last returns the fixture, which is one
    row per class — the exact ``--by series`` failure this file exists to fix.
    """

    #: Real names, copied from the cell. The third is the shape that makes
    #: greediness load-bearing; the fourth and fifth have no separator at all.
    SPECIMENS = [
        ("T20 Series Hong Kong vs Kuwait: Hong Kong, China vs Kuwait - Most Sixes",
         "Most Sixes"),
        ("Test Series Bangladesh vs. Pakistan: Bangladesh vs Pakistan "
         "- Match goes to Day 4?", "Match goes to Day #?"),
        ("ODI Series Australia vs India, Women: Australia vs India - More Markets",
         "More Markets"),
        ("Indian Premier League: Delhi Capitals vs Punjab Kings", None),
        ("T20 1st Innings 6 Overs Line: O/U 53.5", None),
    ]

    def test_the_strip_pattern_is_greedy(self):
        """SILENT. ``'^.*? - '`` would compile, run, and return the fixture."""
        assert "'^.* - '" in cff.FAMILY_EXPR
        assert "'^.*? - '" not in cff.FAMILY_EXPR

    @pytest.mark.parametrize("name,want", SPECIMENS)
    def test_specimens_land_where_the_docstring_says(self, name, want):
        """Python's ``.*`` is greedy exactly as POSIX ``regexp_replace``'s is,
        so this reproduces the SQL's semantics on the two operations the
        expression performs, in the order it performs them."""
        if " - " not in name:
            assert want is None
            return
        got = re.sub(r"[0-9]+", "#", re.sub(r"^.* - ", "", name))
        assert got == want

    def test_digits_collapse_AFTER_the_split_not_before(self):
        """SILENT and directional. Normalising first would rewrite ``T20`` and
        ``Day 4`` alike, which is harmless here, but normalising the SEPARATOR
        search space is how ``O/U 53.5`` and ``O/U 1.5`` become one family in
        a cell where the rung is the whole question."""
        outer = cff.FAMILY_EXPR.index("REGEXP_REPLACE(REGEXP_REPLACE(")
        assert outer >= 0, "the nesting order is the guarantee; keep it nested"
        inner = cff.FAMILY_EXPR.index("'^.* - '")
        digits = cff.FAMILY_EXPR.index("'[0-9]+'")
        assert inner < digits, "the split must be the INNER call"

    def test_the_no_separator_arm_does_not_claim_to_be_the_match_line(self):
        """It mostly is. It is not only that — the innings O/U lines land there
        too — and a class name that asserts more than its predicate tests is
        how a fold starts lying quietly."""
        assert "z_no_dash_suffix" in cff.FAMILY_EXPR
        assert "match_line" not in cff.FAMILY_EXPR


class TestCleanMirrorsTheUpstreamArmsItNames:
    """``CLEAN_EXPR`` says "field_1win that sums like a partition". Both halves
    of that sentence are defined in ``calibration_cell_exact``. If either moves
    there and not here, this file folds a different population and says the
    same word."""

    def test_the_field_1win_test_is_the_upstream_one(self):
        assert "sh.mn >= 3 AND sh.mw = 1" in _norm(cff.CLEAN_EXPR)
        assert "WHEN sh.mn >= 3 AND sh.mw = 1 THEN 'field_1win'" in _norm(
            cce.SHAPE_EXPR)

    def test_the_partition_threshold_is_the_upstream_one(self):
        """SILENT. 1.15 appearing in two files is the defect; this test is what
        makes the second copy safe."""
        assert "ms.msum <= 1.15" in _norm(cff.CLEAN_EXPR)
        assert "WHEN ms.msum <= 1.15 THEN 'a_sum_le_1.15'" in _norm(
            cce.SUMBAND_ONLY_EXPR)

    def test_a_null_price_sum_is_not_clean(self):
        """``SUMBAND_ONLY_EXPR`` gives a NULL sum its own ``'na'`` arm rather
        than folding it into the partition band. Letting NULL fall through to
        ``clean`` here would quietly widen the control by the rows least shown
        to belong in it."""
        assert "ms.msum IS NOT NULL" in _norm(cff.CLEAN_EXPR)
        assert "WHEN ms.msum IS NULL THEN 'na'" in _norm(cce.SUMBAND_ONLY_EXPR)


class TestTheOutcomeNameArmsAreOrdered:
    """The arms overlap. Order is the whole semantics."""

    def test_lone_outcome_is_tested_before_undifferentiated(self):
        """SILENT, and it moves the 12-CAL class. ``on_n = 1`` implies
        ``on_d = 1``: a one-outcome market is undifferentiated only in the
        vacuous sense, and it is already the subject of its own open question
        to Alex. It must keep its own name."""
        e = _norm(cff.OUTCOME_NAME_EXPR)
        assert e.index("on_n = 1 THEN 'd_lone_outcome'") < e.index(
            "on_d = 1 THEN 'a_undifferentiated'")

    def test_partly_duplicated_is_tested_after_fully(self):
        """``on_d < on_n`` is true of a fully undifferentiated market too."""
        e = _norm(cff.OUTCOME_NAME_EXPR)
        assert e.index("on_d = 1 THEN 'a_undifferentiated'") < e.index(
            "on_d < onm.on_n THEN 'b_partly_duplicated'")

    def test_unknown_is_its_own_arm_and_not_folded_into_distinct(self):
        """A LEFT JOIN that matched nothing is an absence, not a clean market
        (gotcha #53). ``c_distinct`` is the arm every refusal in the CAL-P123
        report leans on; it must not be able to absorb a join miss."""
        assert "onm.on_n IS NULL THEN 'z_unknown'" in _norm(cff.OUTCOME_NAME_EXPR)

    def test_the_predicate_is_distinctness_not_a_truncation_length(self):
        """SILENT. ``futures_outcomes.name`` is truncated relative to
        ``futures_markets.name``, so a prefix/length test measures a truncation
        constant. The property is distinctness; keep testing that."""
        assert "COUNT(DISTINCT fo4.name)" in cff.OUTCOME_NAME_JOIN
        assert "LIKE" not in cff.OUTCOME_NAME_EXPR
        assert "LENGTH" not in cff.OUTCOME_NAME_JOIN


class TestTheJoinKeepsThePlannerHint:
    """CAL-P114 measured this: without the ``IN (SELECT ...)`` conjunct the
    planner aggregates all 3.3M ``futures_outcomes`` rows before the join and
    the chunk never returns. It reads like a redundant predicate. It is not."""

    def test_the_outcome_name_join_scopes_to_market_info(self):
        assert "market_id IN (SELECT market_id FROM market_info)" in _norm(
            cff.OUTCOME_NAME_JOIN)

    def test_the_upstream_shape_join_still_carries_the_same_hint(self):
        """If it is ever "tidied" out of the original, this copy is next."""
        assert "market_id IN (SELECT market_id FROM market_info)" in _norm(
            cce.SHAPE_JOIN)

    def test_the_join_is_a_left_join(self):
        """An inner join would silently DROP rows whose market has no outcome
        rows, changing the denominator of every class in the table."""
        assert _norm(cff.OUTCOME_NAME_JOIN).startswith("LEFT JOIN")


class TestItComposesTheRailRatherThanRebuildingIt:
    """The lane's most expensive recurring mistake is a second rail wearing the
    published curve's name (CAL-P112 on ``polymarket/tech``, CAL-P114 on
    ``kalshi/economics`` — 1.9x the rows and the wrong sign on the gap)."""

    SOURCE = (SCRIPTS / "calibration_family_fold.py").read_text()

    def test_all_four_dimensions_are_registered(self):
        for dim in cff.ADDED_DIMENSIONS:
            assert dim in cce.DIMENSIONS, dim

    def test_registration_uses_setdefault_not_subscript_assignment(self):
        """CAL-P121's convention and its mechanical guard. Rebinding would let
        this file silently change what an existing ``--by`` means."""
        import ast

        tree = ast.parse(self.SOURCE)
        for node in ast.walk(tree):
            if not isinstance(node, ast.Assign):
                continue
            for t in node.targets:
                if (isinstance(t, ast.Subscript)
                        and isinstance(t.value, ast.Attribute)
                        and t.value.attr == "DIMENSIONS"):
                    raise AssertionError(
                        f"cce.DIMENSIONS[...] = ... at line {node.lineno} "
                        "— use setdefault")

    def test_no_name_collides_with_a_dimension_already_on_the_rail(self):
        """SILENT, and it is ``setdefault``'s own failure mode. A collision
        makes registration a NO-OP: the run folds somebody else's dimension
        while its command line and its table header say this one's name."""
        assert not (set(cff.ADDED_DIMENSIONS) & cff._PRE_EXISTING)
        for name, spec in cff.ADDED_DIMENSIONS.items():
            assert cce.DIMENSIONS[name] == spec, name

    def test_its_loader_does_not_pollute_sys_modules(self):
        """These modules mutate shared state at import time — this file adds
        four dimensions to ``cce.DIMENSIONS`` — so a sibling left in
        ``sys.modules`` makes those mutations visible to every other test in
        the pytest process. CAL-P121's
        ``test_this_module_adds_exactly_one_dimension_and_no_more`` caught this
        file doing exactly that on its first draft, and was right to.

        Asserted on the loader rather than on the process: whether some OTHER
        module has registered a sibling is not a fact this file controls, and a
        guard that fails on somebody else's import is a guard that gets
        deleted.
        """
        import sys

        before = set(sys.modules)
        cff._load("calibration_cell_exact")
        assert set(sys.modules) - before == set()
        assert "sys.modules[name] = mod" not in self.SOURCE

    def test_the_registered_dimensions_are_reachable_from_the_cli(self):
        """``main()`` builds ``choices`` from the live dict, so registration and
        reachability are the same fact — until someone freezes the choices."""
        choices = sorted(set(cce.DIMENSIONS) | set(cce.PER_CHUNK_DIMENSIONS))
        assert {"family", "familyclean", "outcomenames",
                "familynames"} <= set(choices)

    def test_it_does_not_reimplement_the_population(self):
        """SILENT, and the most expensive one on the list."""
        assert "_calibration_population_ctes" not in self.SOURCE
        assert "WITH deduped" not in self.SOURCE
        assert "ranked_outcomes" not in self.SOURCE

    def test_it_reuses_the_upstream_joins_by_reference(self):
        """A pasted copy of ``SUMBAND_JOIN`` would not track an upstream fix."""
        assert "cce.SERIES_JOIN" in self.SOURCE
        assert "cce.SUMBAND_JOIN" in self.SOURCE
        assert "cce.SUMBAND_PRE" in self.SOURCE

    def test_it_is_read_only(self):
        """Ruling 134: an instrument writes nothing."""
        for verb in ("INSERT ", "UPDATE ", "DELETE ", "CREATE ", "ALTER ",
                     "DROP ", "TRUNCATE "):
            assert verb not in self.SOURCE.upper(), verb

    def test_it_does_not_load_the_frozen_module_itself(self):
        """Ruling 009 freezes commits to ``precompute_calibration.py``. This
        file reaches the producer's chain only THROUGH
        ``calibration_cell_exact``, which already carries the import and its
        own guards. Naming the frozen module in prose is fine and it does;
        loading a second copy of it here is what must stay impossible.
        """
        import ast

        tree = ast.parse(self.SOURCE)
        for node in ast.walk(tree):
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                names = [a.name for a in getattr(node, "names", [])]
                names.append(getattr(node, "module", "") or "")
                assert not any("precompute_calibration" in n for n in names)
            if isinstance(node, ast.Call):
                for arg in node.args:
                    if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                        assert "precompute_calibration" not in arg.value


class TestTheCliDefault:
    def test_it_defaults_to_family_when_no_by_is_given(self, monkeypatch):
        seen = {}
        monkeypatch.setattr(cff.sys, "argv",
                            ["prog", "--source", "polymarket",
                             "--category", "cricket"])
        monkeypatch.setattr(cce, "main", lambda: seen.setdefault(
            "argv", list(cff.sys.argv)) and 0 or 0)
        cff.main()
        assert seen["argv"][-2:] == ["--by", "family"]

    @pytest.mark.parametrize("given", [["--by", "sumband"], ["--by=sumband"]])
    def test_an_explicit_by_is_never_overridden(self, monkeypatch, given):
        """SILENT in the ``--by=x`` spelling: appending a second ``--by`` makes
        argparse take the LAST one, so the run would quietly fold ``family``
        while its command line says ``sumband``."""
        seen = {}
        monkeypatch.setattr(cff.sys, "argv",
                            ["prog", "--source", "polymarket",
                             "--category", "cricket"] + given)
        monkeypatch.setattr(cce, "main", lambda: seen.setdefault(
            "argv", list(cff.sys.argv)) and 0 or 0)
        cff.main()
        assert seen["argv"].count("--by") + sum(
            1 for a in seen["argv"] if a.startswith("--by=")) == 1
