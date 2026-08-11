from __future__ import annotations
import subprocess

import pytest

from scripts.evals.calibration_census_closure_contract import evaluate_pack,load_pack

# The PRE-FIX state these three cases describe. It is a branch SHA, so it exists
# only in a clone that still has `program/calibration-28` — not on master after
# the stack was rebased into it, and not in CI's shallow checkout at all.
#
# It turned master RED on the merge (CI 31460938356): `git show` exited 128 and
# the CalledProcessError surfaced as a test failure, which reads as "the
# calibration contract broke" when the truth is "this machine does not have that
# commit". A known-issue confirmation that cannot find its own subject must say
# so, not fail as though the subject were wrong.
TARGET="5c138743"

def show(path):
    try:
        return subprocess.check_output(
            ["git","show",f"{TARGET}:{path}"], text=True, stderr=subprocess.DEVNULL
        )
    except subprocess.CalledProcessError:
        pytest.skip(
            f"target {TARGET} is not in this clone — these cases document the "
            f"PRE-FIX state and can only run where that history exists "
            f"(rebased away on master; absent in CI's shallow checkout)"
        )
def test_corpus():
 r=evaluate_pack(load_pack()); assert r["total"]==8 and r["passed"]==8,r
def test_sparse_ids_are_not_mistaken_for_a_gap():
 c=next(x for x in load_pack()["cases"] if x["id"]=="complete-sparse-id-walk"); assert evaluate_pack({"cases":[c]})["passed"]==1
def test_target_has_none_of_the_three_mechanical_fields():
 task=show("backend/app/tasks/census_overlap_trading.py"); script=show("backend/scripts/walk_overlap_census.py")
 assert '"cursor_in"' not in task and '"source_watermark"' not in task
 assert "CURSOR_CHAIN_BROKEN" not in script
def test_target_partial_report_still_returns_zero():
 script=show("backend/scripts/walk_overlap_census.py"); assert "if not complete:" in script and script.rindex("return 0")>script.index("if not complete:")
def test_target_exam_still_overclaims_timing():
 doc=show("docs/CALIBRATION-EXIT-EXAM.md"); assert "stamped-settlement rival is REFUTED" in doc
