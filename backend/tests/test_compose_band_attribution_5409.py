"""#5409 — `compose-band.sh` must not call a pre-existing master failure the sha's.

lane1/254 ran the band on `65d7f749` (CERT-2653, GREEN token, every merge-gate
notice passed) on 2026-09-11. After 31m56s — 1 failed, 26,902 passed — it printed
*"the failure(s) reproduce in isolation, so this is the sha's, not the machine's
… DO NOT PUSH IT."* The sha was fine; the desk merged it and master CI is green.

The failing node shells out to `git merge-base --is-ancestor`, and `~/bainluck/.git`
is a SHALLOW clone, so the ancestry walk hits the graft boundary and answers "not
an ancestor" for commits GitHub confirms are ancestors. It fails identically on
master WITHOUT the sha, and CI checks out `fetch-depth: 0` so it passes there.

**The logic gap is general, and it is the reason this file exists.** Isolation
separates FLAKE from REAL. It does not separate "the sha's" from "already red on
master" — and that class is maximally deterministic, so it reproduces in isolation
every single time and the re-run actively CONFIRMS the wrong cause.

Every test drives both directions: for each way the verdict may be `RED`, there is
a sibling asserting the same inputs with one field moved do NOT produce `RED`. A
suite that only pinned the new `PRE_EXISTING` answer would pass against a function
that returned `PRE_EXISTING` for everything, and that is the worse bug — it would
withhold every genuinely broken sha's stop.
"""

import subprocess
from pathlib import Path

import pytest

HELPER = Path(__file__).resolve().parents[2] / "tools" / "compose_band_verdict.sh"
BAND = Path(__file__).resolve().parents[2] / "tools" / "compose-band.sh"


def verdict(iso_exit, base_exit="none", n_base_nodes=0, n_skipped=0):
    """Drive the real shell function — not a Python re-implementation of it.

    A probe that reimplements the thing it grades measures the reimplementation.
    """
    out = subprocess.run(
        ["bash", "-c",
         f'. "{HELPER}"; compose_band_verdict "{iso_exit}" "{base_exit}" '
         f'"{n_base_nodes}" "{n_skipped}"'],
        capture_output=True, text=True, timeout=30,
    )
    assert out.returncode == 0, f"helper exited {out.returncode}: {out.stderr}"
    return out.stdout.strip()


class TestTheCaseThatCostLane1254ThirtyTwoMinutes:
    def test_a_failure_that_also_fails_on_the_base_is_not_the_shas(self):
        """Reproduces alone (iso 1) AND on the base (base 1) ⇒ PRE_EXISTING."""
        assert verdict(1, base_exit=1, n_base_nodes=1) == "PRE_EXISTING"

    def test_the_same_failure_absent_from_the_base_IS_the_shas(self):
        """The other direction, and the one that keeps the tool useful. Same
        inputs, base passes instead ⇒ RED. Without this pair, a function that
        answered PRE_EXISTING unconditionally would pass the test above."""
        assert verdict(1, base_exit=0, n_base_nodes=1) == "RED"

    def test_pre_existing_is_not_a_clearance(self):
        """`PRE_EXISTING` and `FLAKE` are distinct tokens, so the caller cannot
        collapse them into one 'not red, carry on' branch. Both stop the push;
        only their remedies differ."""
        assert verdict(1, base_exit=1, n_base_nodes=1) != verdict(0)


class TestTheIsolationAnswerStillGovernsFirst:
    def test_passing_alone_is_a_flake_whatever_the_base_says(self):
        assert verdict(0) == "FLAKE"
        assert verdict(0, base_exit=1, n_base_nodes=3) == "FLAKE"

    @pytest.mark.parametrize("iso", [2, 4, 5, 127, 137, 143])
    def test_an_isolation_exit_that_is_not_0_or_1_is_never_a_verdict(self, iso):
        """Gotcha #124: 1 is a result, everything else is a story about the
        harness. pytest's 4 and 5 are the dangerous pair — both look 'not
        failed' to a careless eye."""
        assert verdict(iso, base_exit=0, n_base_nodes=1) == "INCONCLUSIVE"


class TestTheBaselineMustActuallyHaveBeenTaken:
    @pytest.mark.parametrize("base", [2, 4, 5, "none", ""])
    def test_a_baseline_that_did_not_answer_yields_inconclusive_not_red(self, base):
        """The load-bearing default. An unattributed failure is not a verdict
        about a sha, and this tool's expensive error is withholding a good ship,
        not delaying a bad one by one re-run."""
        assert verdict(1, base_exit=base, n_base_nodes=1) == "INCONCLUSIVE"

    def test_all_failing_nodes_being_sha_added_is_red_with_no_baseline(self):
        """A node in a file the sha ADDS cannot be run at master. That is not a
        missing answer — it is the answer: nothing on the base could have caused
        it."""
        assert verdict(1, base_exit="none", n_base_nodes=0, n_skipped=2) == "RED_NO_BASELINE"

    def test_zero_nodes_and_zero_skipped_is_inconclusive_not_red(self):
        """The control for the test above. 'No nodes to run' only means 'the sha
        added them all' when some were actually skipped for that reason; with
        neither, the node list is malformed and the honest answer is that nothing
        was measured. Handing a sha-added path to pytest at master is the exit-4
        trap, and 'no tests ran' would otherwise arrive looking like a clean
        baseline — RED for the right answer by the wrong route."""
        assert verdict(1, base_exit="none", n_base_nodes=0, n_skipped=0) == "INCONCLUSIVE"


class TestTheBandScriptItself:
    def test_it_parses(self):
        """`bash -n` on both files. A shell tool with no test at all is how the
        original shipped; the least this suite owes is that a typo in the new
        branch cannot reach an operator inside a push window."""
        for path in (BAND, HELPER):
            out = subprocess.run(["bash", "-n", str(path)], capture_output=True,
                                 text=True, timeout=30)
            assert out.returncode == 0, f"{path.name}: {out.stderr}"

    def test_the_red_verdict_is_reached_only_through_the_shared_function(self):
        """A source scan proves text is PRESENT, not that it runs — so this is
        deliberately narrow: it asserts the band has no `DO NOT PUSH IT` line
        that is not inside a branch keyed on a `compose_band_verdict` token. The
        behavioural half is the parametrized tests above, which drive the real
        function; this only stops a future edit from re-adding a second,
        unattributed path to the same sentence."""
        text = BAND.read_text()
        # Count only lines that PRINT it. The phrase also appears twice in the
        # comment recording lane1/254's case, and a raw `.count` folds prose in
        # with behaviour — the first cut of this test did exactly that and failed
        # at 4, which is why the predicate is narrowed rather than the number
        # raised.
        printed = [
            ln for ln in text.splitlines()
            if "DO NOT PUSH IT" in ln and ln.lstrip().startswith("echo ")
        ]
        assert len(printed) == 2, (
            "expected exactly the two attributed RED branches (RED and "
            f"RED_NO_BASELINE); got {len(printed)} printing lines, so an "
            f"unattributed path was added: {printed}"
        )
        assert "compose_band_verdict 1 " in text, "the band must call the shared function"

    def test_the_shallow_clone_warning_names_the_condition_and_the_contrast(self):
        """A warning that says 'shallow' without saying what it does to a verdict
        is a word, not a warning."""
        text = BAND.read_text()
        assert "SHALLOW CLONE" in text
        assert "fetch-depth: 0" in text, "must name why CI disagrees"
        assert "is-shallow-repository" in text, "must actually test the condition"
