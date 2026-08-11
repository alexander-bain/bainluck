"""Q332 Item 2 — every auth-removal / auth-weakening mutant must be KILLED.

C271 routed this class here: the Codex lane does not run mutations that remove or
weaken an auth gate (``CODEX-LANE.md``, 2026-08-11 vendor-routing rule).

Read ``scripts/evals/admin_auth_gate_mutations.py`` for what each mutant does and,
importantly, for the two that are equivalent on the authorization axis and are killed
on the diagnostic contract instead.
"""
from __future__ import annotations

import shutil

import pytest

from scripts.evals import admin_auth_gate_mutations as harness
from scripts.evals.admin_destructive_boundary_contract import load_pack


@pytest.fixture(scope="module")
def mutation_run():
    return harness.run_all()


def test_baseline_boundary_is_clean(mutation_run):
    """The control. If the unmutated gate already fails an assertion, every kill
    below is meaningless — a mutant would 'die' of a pre-existing defect."""
    baseline = mutation_run["rows"][0]
    assert baseline["failures"] == [], baseline["failures"]


@pytest.mark.parametrize("mutant", harness.MUTANTS, ids=lambda m: m["id"])
def test_every_auth_weakening_mutant_is_killed(mutant, mutation_run):
    row = next(r for r in mutation_run["rows"] if r["id"] == mutant["id"])
    assert row["killed"], (
        f"MUTANT SURVIVED: {mutant['id']} — {mutant['why']}\n"
        "A survivor is a missing test or a missing gate. Resolve which; do not delete "
        "the mutant."
    )


def test_no_mutant_is_silently_dropped():
    """The mutant list is the claim. If someone deletes a mutant, the count moves and
    this fails — a security suite that can be quietly shrunk proves nothing."""
    assert len(harness.MUTANTS) == 7
    assert harness.EQUIVALENT_ON_AUTHORIZATION <= {m["id"] for m in harness.MUTANTS}


def test_timing_mutant_is_killed_by_source_contract():
    """``compare_digest`` -> ``==`` is behaviourally IDENTICAL; only timing differs.

    A behavioural oracle cannot kill it and a timing measurement would be a flake, so
    it is pinned at the source: the token comparison must go through
    ``hmac.compare_digest``. Stated plainly rather than counted as a behavioural kill.
    """
    source = harness.read_source()
    assert harness.TIMING_MUTANT["needle"] in source, (
        "The constant-time comparison is gone from _tokens_match. If it was "
        "deliberately refactored, re-target TIMING_MUTANT; do not drop the contract."
    )
    # And the mutated form must genuinely be indistinguishable behaviourally —
    # this is the evidence for the claim above, not an assumption about it.
    mutated = harness.load_module(
        harness.apply_mutant(source, harness.TIMING_MUTANT), "admin_utils_timing_mutant"
    )
    assert harness.oracle(mutated) == [], (
        "The timing mutant changed an accept/reject verdict, so it is NOT merely a "
        "timing weakening — reclassify it as a behavioural mutant."
    )


def test_removing_a_strong_gate_from_a_route_is_caught_by_the_census(tmp_path):
    """The route-level mutant: drop ``_check_admin_destructive`` from a wired handler.

    This is the mutation Item 0 warned about — against an UNWIRED route it would prove
    nothing, because removing a gate that was never called changes nothing. All 15 are
    wired now, so it bites. Uses the census's own ``C271_ROUTES_DIR`` seam, so the real
    tree is never mutated.
    """
    import importlib

    routes_src = harness.REPO / "backend/app/routes"
    routes_copy = tmp_path / "routes"
    shutil.copytree(routes_src, routes_copy)

    target = routes_copy / "admin_teams.py"
    source = target.read_text()
    needle = "    _check_admin_destructive(secret, request=request)"
    assert source.count(needle) == 1, "re-target: merge_duplicate_team's gate moved"
    target.write_text(source.replace(needle, "    _check_admin_secret(secret, request=request)"))

    monkey = pytest.MonkeyPatch()
    try:
        monkey.setenv("C271_ROUTES_DIR", str(routes_copy))
        module = importlib.reload(
            importlib.import_module("scripts.evals.admin_destructive_boundary_contract")
        )
        result = module.evaluate_pack(load_pack())
        failed = [row["id"] for row in result["rows"] if not row["passed"]]
        assert failed == ["merge-team"], (
            f"census did not catch the un-wiring; failures={failed}"
        )
    finally:
        monkey.undo()
        importlib.reload(
            importlib.import_module("scripts.evals.admin_destructive_boundary_contract")
        )
