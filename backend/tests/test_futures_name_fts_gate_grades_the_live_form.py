"""The futures-name FTS gate grades the expression a ROUTE runs — #2394.

WHAT BROKE, AND WHY NO EXISTING TEST CAUGHT IT.

`ix_futures_name_fts_open` landed on production 2026-08-29 and works. Its gate,
`backend/scripts/gate_futures_name_fts_index.py`, then reported **RED on
`winner`** for two cycles — because it compiled its probe from
`_build_futures_name_filter`, the `FTS(name) OR name ILIKE '%q%'` fold, and
**LAT-P140 had already moved `/typeahead` off that fold** to a UNION of the same
two halves. The fold has ZERO callers in `backend/app/`. Measured on production
while diagnosing it, `winner`:

    FTS half alone         36 ms      uses ix_futures_name_fts_open
    ILIKE half alone       91 ms      uses ix_futures_name_trgm
    the OR of them  1,434-2,232 ms    uses NEITHER — falls back to a status scan
    the UNION of them     102 ms      uses BOTH

So the gate was not wrong about the OR; it was wrong about production. Every
assertion it made was honest and none of them was ABOUT anything a user touches.

`test_typeahead_name_arms_union.py` could not catch this and is not at fault:
its subject is the ROUTE, and the route was already correct. Nothing pointed at
the GATE. This file is that thing.

⚠️ THE RULE IS CALLED, NOT RESTATED. Criterion 1 is graded by `_shape_verdict`
and the arms come from the route's own `_futures_name_arms`, so these tests
compare the gate against the live helper rather than against a second copy of
the predicate written here. A test that re-derives the logic it checks only
tests itself.

No database, no network: every assertion is against compiled SQL.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest
from sqlalchemy.dialects import postgresql

from app.models.models import FuturesMarket
from app.routes.events import _build_expanded_ilike, _futures_name_arms

TERM = "winner"

#: The term the gate reported a false RED on, and the two it always passed. If
#: the graded form ever regresses to the fold, it regresses for all of them.
CENSUS_TERMS = ("winner", "werder", "champions")


def _gate():
    """Import the gate module LAZILY.

    Deliberate: a module-scope import turns "the symbol was deleted" into a
    COLLECTION error, which pytest reports with an exit code that is a story
    about the harness rather than a verdict. Inside the test it is an ordinary
    failure on exit 1.
    """
    path = Path(__file__).resolve().parent.parent / "scripts" / "gate_futures_name_fts_index.py"
    spec = importlib.util.spec_from_file_location("gate_futures_name_fts_index", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules["gate_futures_name_fts_index"] = module
    spec.loader.exec_module(module)
    return module


def _sql(clause) -> str:
    return str(
        clause.compile(
            dialect=postgresql.dialect(paramstyle="named"),
            compile_kwargs={"literal_binds": True},
        )
    )


def _route_arms(term: str = TERM) -> list:
    """The halves as the ROUTE builds them — the comparand, not a copy."""
    return _futures_name_arms(_build_expanded_ilike(FuturesMarket.name, term, None), term)


class TestTheGradedProbeIsTheUnion:
    """What the gate MEASURES is the shape `/typeahead` emits."""

    @pytest.mark.parametrize("term", CENSUS_TERMS)
    def test_the_graded_sql_is_a_union(self, term):
        assert " UNION " in _gate()._arm_sql(term), (
            "the graded probe is not a UNION, so it is the OR fold again and "
            "`winner` will report a false RED against a working index (#2394)."
        )

    def test_each_union_branch_carries_exactly_one_predicate_class(self):
        sql = _gate()._arm_sql(TERM)
        branches = sql.split(" UNION ")
        assert len(branches) == 2, (
            f"the graded probe has {len(branches)} UNION branches, not 2. The "
            "futures NAME arm is FTS + ILIKE; a third branch means the gate has "
            "silently widened to arms it is not measuring the index for."
        )
        # `== 1`, never `>= 1`: a detector that passes on the absence it is
        # supposed to catch is not a detector.
        assert sum("to_tsvector" in b for b in branches) == 1
        assert sum("ILIKE" in b.upper() for b in branches) == 1
        for branch in branches:
            assert not ("to_tsvector" in branch and "ILIKE" in branch.upper()), (
                "one branch carries BOTH halves, so that branch IS the old OR "
                "and the planner will cost it on the union's selectivity."
            )

    @pytest.mark.parametrize("term", CENSUS_TERMS)
    def test_the_branches_are_the_routes_own_arms(self, term):
        """Not 'a union' — a union OF THE ROUTE'S ARMS."""
        graded = _gate()._arm_sql(term)
        for arm in _route_arms(term):
            assert _sql(arm) in graded, (
                "a half of `_futures_name_arms` does not appear in the graded "
                "probe. The gate has its own copy of the predicate, which is how "
                "it drifted off the route in the first place."
            )

    def test_the_digest_is_taken_over_the_union(self):
        """Criterion 3 must cover BOTH halves, not whichever one it kept."""
        sql = _gate()._signature_sql(TERM)
        assert " UNION " in sql and "md5(" in sql and "string_agg(" in sql
        assert sql.count("to_tsvector") == 1 and sql.upper().count("ILIKE") == 1


class TestTheOrFoldIsAContrastAndNotTheVerdict:
    """The control arm of this guard: the fold must still exist, and still be the fold.

    Both of these stay GREEN under the defect AND under the fix — that is what
    makes them a control. They are what proves the tests above are discriminating
    between two live forms rather than just asserting that some SQL exists.
    """

    def test_the_or_fold_probe_is_still_an_or(self):
        sql = _gate()._or_fold_sql(TERM)
        assert " UNION " not in sql, "the contrast is no longer the OR fold"
        assert "to_tsvector" in sql and "ILIKE" in sql.upper(), (
            "the contrast lost a half, so the run can no longer show what the "
            "UNION split bought."
        )

    def test_the_or_fold_is_the_dead_helper_and_the_graded_form_is_not(self):
        gate = _gate()
        assert _sql(gate._or_fold_predicate(TERM)) != gate._arm_sql(TERM)
        # The fold and the union must be built from the SAME two halves — if they
        # ever diverge, the contrast stops being a contrast and becomes noise.
        fold_sql = _sql(gate._or_fold_predicate(TERM))
        for arm in _route_arms():
            assert _sql(arm) in fold_sql


class TestCriterionOneNoLongerRequiresABitmapOr:
    """Under the UNION there is no BitmapOr node, so requiring one fails every
    correct plan. Graded by calling `_shape_verdict`, never by re-stating it."""

    def test_both_indexes_present_is_green(self):
        gate = _gate()
        ok, missing = gate._shape_verdict(set(gate.EXPECTED_INDEXES))
        assert ok and missing == [], (
            "a plan using BOTH GINs is the outcome the DDL was specced for and "
            "it must not need a BitmapOr to be graded green."
        )

    @pytest.mark.parametrize("dropped", ("ix_futures_name_fts_open", "ix_futures_name_trgm"))
    def test_either_index_missing_is_red(self, dropped):
        gate = _gate()
        ok, missing = gate._shape_verdict(set(gate.EXPECTED_INDEXES) - {dropped})
        assert not ok and missing == [dropped], (
            "half the win is not the win: a plan that serves one half by index "
            "and scans the other is the defect, not a partial pass."
        )

    def test_the_status_scan_fallback_is_red(self):
        # The exact plan `winner` produced under the fold: neither GIN.
        gate = _gate()
        ok, _ = gate._shape_verdict({"ix_futures_markets_status"})
        assert not ok

    def test_the_verdict_cannot_be_told_about_a_bitmap_or(self):
        """The only way to reintroduce the retired criterion is to pass it in."""
        gate = _gate()
        with pytest.raises(TypeError):
            gate._shape_verdict(set(gate.EXPECTED_INDEXES), True)


class TestTheGroundTruthSurgeryCannotSilentlyNoOp:
    """`str.replace` that matches nothing returns the string unchanged.

    If the compiled rendering ever drifts, the 'forced scan' would silently BE
    the indexed query, criterion 3 would compare it against itself, and it would
    pass forever. A criterion that cannot fail is worth what one that always
    fails is worth — and this file's subject is a gate that graded the wrong
    thing for two cycles, so that is not a hypothetical failure mode here.
    """

    def test_the_surgery_actually_changes_both_halves(self):
        gate = _gate()
        truth = gate._ground_truth_sql(TERM)
        assert "coalesce(futures_markets.name, '') || ''" in truth
        assert "(futures_markets.name || '') ILIKE" in truth
        assert truth != gate._signature_sql(TERM)

    def test_a_drifted_rendering_exits_loudly(self, monkeypatch):
        gate = _gate()
        monkeypatch.setattr(
            gate, "_signature_sql", lambda term: "SELECT count(*) FROM futures_markets"
        )
        with pytest.raises(SystemExit) as excinfo:
            gate._ground_truth_sql(TERM)
        # 2 = the harness could not run, per this repo's exit-code grammar.
        # Never 0, and never a silent pass.
        assert excinfo.value.code == 2
