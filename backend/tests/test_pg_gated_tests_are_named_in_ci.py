"""Every Postgres-gated integration test must be NAMED by a step in ci.yml.

THE INCIDENT (calibration/1111, 2026-09-11). #2637's repair shipped two tests
that lift the resolve `UPDATE` out of the shipped source and run it against real
Postgres. They were presented — in the PR, in the cert body, and in the lane
handoff — as the proof that the fix works "on ROWS", which was the exact gap
CERT-751 had blocked the first attempt for.

They had never executed. Not in CI, not locally, not once:

  * the file is gated on ``SEARCH_TEST_DATABASE_URL`` (the correct convention);
  * that variable is set in exactly ONE place, the ``search-recall`` job's env;
  * and that job runs each PG gate as its OWN explicit
    ``python -m pytest <file>`` step. Nothing named the new file, so nothing
    ever invoked it, and in the main test job it had no database and skipped.

pytest exits 0 when every test skips. So the branch showed CI
``completed/success``, a clean check-run list, and a green local run whose
summary said ``34 skipped`` — which the author read as the documented
sandbox-has-no-Postgres skip rather than as the gate never running anywhere.

This is standing notice 28 one layer down: a green CI run is a claim about the
steps that RAN. It is also the failure mode the search-recall job's own comments
say it exists to end — *"a silently-skipped gate reads exactly like a passing
one"* — which it does, but only for the files someone remembered to name.

So the invariant is mechanised here rather than left to reviewers: adding a
PG-gated file under ``tests/integration/`` without a workflow step is now a
failing test, not a silent no-op that can be quoted as evidence.
"""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
CI_YML = REPO_ROOT / ".github" / "workflows" / "ci.yml"
INTEGRATION_DIR = Path(__file__).resolve().parent / "integration"

#: A file is "PG-gated" if it skips itself on a Postgres URL env var. Those are
#: the only files that can skip WITHOUT any local signal, which is what makes an
#: unnamed one dangerous rather than merely unrun.
#:
#: #9602 follow-up (CERT-3793): the pattern used to be ``[A-Z_]*TEST_DATABASE_URL``,
#: which only sees the ``*_TEST_*`` convention. Thirteen gated files use a name
#: without ``TEST`` (``DELAY_CONTRACT_DATABASE_URL`` ×5, ``WS_SLATE_…``,
#: ``GENERIC_HISTORY_…``, ``BLEND_DEADLOCK_…``, …), so a new file on one of
#: those gates could go unnamed in ci.yml and this guard would never know it
#: existed. Any PREFIXED ``*_DATABASE_URL`` is a gate. The bare ``DATABASE_URL``
#: is not matched: the prefix-and-underscore is required, and the files that read
#: the bare name are either gated on a prefixed one as well or not PG-gated.
PG_GATE_ENV_RE = re.compile(r"[A-Z][A-Z0-9_]*_DATABASE_URL")

#: Pre-existing violations, each of which must name why it is tolerated. This is
#: a debt list, not a discretionary opt-out: an entry is a file whose gate does
#: not run, so nothing about it may be quoted as proof while it sits here.
#:
#: ``test_feed_static_tag_filter_pg.py`` — found unnamed by the same sweep that
#: found the #2637 hole. Wiring it is a feed-lane change (its first CI execution
#: could legitimately go red, and reding master on another lane's behalf is not
#: this guard's job), so it is recorded here and handed over rather than
#: silently fixed or silently ignored.
KNOWN_UNWIRED = {
    "test_feed_static_tag_filter_pg.py",
}


def _pg_gated_files() -> set[str]:
    found = set()
    for path in sorted(INTEGRATION_DIR.glob("test_*.py")):
        if PG_GATE_ENV_RE.search(path.read_text(encoding="utf-8")):
            found.add(path.name)
    return found


def test_ci_names_every_pg_gated_integration_test():
    """A PG-gated file no ci.yml step names is a gate that never runs."""
    ci_text = CI_YML.read_text(encoding="utf-8")
    gated = _pg_gated_files()

    # The sweep itself must not be vacuous: if the glob or the regex stops
    # matching (a rename, a moved directory), an empty set would sail through
    # and this guard would protect nothing while staying green.
    assert len(gated) >= 10, (
        f"only {len(gated)} PG-gated files found under {INTEGRATION_DIR} — the "
        "detector has stopped matching, so this guard is not guarding anything"
    )

    unnamed = {name for name in gated if name not in ci_text}
    assert unnamed <= KNOWN_UNWIRED, (
        "these Postgres-gated tests are not named by any ci.yml step, so they "
        "skip in every environment and pytest still exits 0 — nothing about "
        f"them may be quoted as evidence: {sorted(unnamed - KNOWN_UNWIRED)}"
    )


TESTS_DIR = Path(__file__).resolve().parent

#: #12612: files directly under ``tests/`` were invisible to the sweep above,
#: which reads ``tests/integration/`` only. That is how #12519's nine
#: real-Postgres tests went unrun in CI while being quoted as the proof. A
#: root-level file is PG-gated when it READS a gate variable from the
#: environment and makes a skip CALL: mentioning a gate in prose, or asserting
#: on its name the way the CI meta-tests do, is not a gate.
GATE_READ_RE = re.compile(
    r"""os\.(?:environ\.get|getenv)\(\s*["'][A-Z][A-Z0-9_]*_DATABASE_URL["']"""
    r"""|os\.environ\[\s*["'][A-Z][A-Z0-9_]*_DATABASE_URL["']"""
)
SKIP_CALL_RE = re.compile(r"pytest\.mark\.skipif\(|pytest\.skip\(")

#: #12612's debt list for ``tests/``: gated files no ci.yml step names, read
#: one by one on Nov 11. Wiring each is its owner's change (a first CI run can
#: go red), so the list can only shrink. The calibration files' gate,
#: ``CALIBRATION_TEST_DATABASE_URL``, is set by no CI job at all (the four
#: start-placeholder files were wired with their own step, #12612). Nothing in
#: these files is evidence while listed.
KNOWN_UNWIRED_ROOT = {
    "test_calibration_canonical_pg.py",
    "test_calibration_examples_canonical_262.py",
    "test_calibration_horizon_honest_263.py",
    "test_calibration_horizon_population_262.py",
    "test_polymarket_container_sibling_5821.py",
    "test_repair_10520_keeper_current_anchor.py",
}


def _root_pg_gated_files() -> set[str]:
    found = set()
    for path in sorted(TESTS_DIR.glob("test_*.py")):
        if path.name == Path(__file__).name:
            continue  # this guard spells gate reads and skip calls in its own checks
        text = path.read_text(encoding="utf-8")
        if GATE_READ_RE.search(text) and SKIP_CALL_RE.search(text):
            found.add(path.name)
    return found


def test_ci_names_every_pg_gated_test_directly_under_tests():
    """#12612: the same invariant for ``tests/`` itself."""
    ci_text = CI_YML.read_text(encoding="utf-8")
    gated = _root_pg_gated_files()
    # Not vacuous: the two wired files and the debt list are all gated.
    assert {"test_team_merge_keeps_distinct_names_12519.py",
            "test_blend_preview_ledger_tsp1_10090.py"} <= gated, (
        "the root-level detector has stopped matching known gated files"
    )
    unnamed = {name for name in gated if name not in ci_text}
    assert unnamed <= KNOWN_UNWIRED_ROOT, (
        "these Postgres-gated tests directly under tests/ are not named by any "
        "ci.yml step, so they skip everywhere and pytest still exits 0: "
        f"{sorted(unnamed - KNOWN_UNWIRED_ROOT)}"
    )


def test_root_debt_list_does_not_outlive_its_entries():
    ci_text = CI_YML.read_text(encoding="utf-8")
    gated = _root_pg_gated_files()
    for name in sorted(KNOWN_UNWIRED_ROOT):
        assert name in gated, f"{name} is on the debt list but no longer gated: drop it"
        assert name not in ci_text, f"{name} is on the debt list but ci.yml names it: drop it"


def test_root_detector_reads_gates_not_prose():
    assert GATE_READ_RE.search('DB_URL = os.environ.get("SEARCH_TEST_DATABASE_URL")')
    assert GATE_READ_RE.search("url = os.getenv('START_PLACEHOLDER_DATABASE_URL')")
    assert not GATE_READ_RE.search("skipif-gated on `SEARCH_TEST_DATABASE_URL`, so it skips")
    assert not GATE_READ_RE.search('os.environ.get("DATABASE_URL")')
    assert SKIP_CALL_RE.search("pytestmark = pytest.mark.skipif(not DB_URL, reason='x')")
    assert not SKIP_CALL_RE.search("a `skipif`-gated class in this file")


def test_detector_sees_gates_not_spelled_test_database_url():
    """#9602 follow-up: a gate named without ``TEST`` is still a gate.

    The #9602 playoff file and the #7617 file it reuses are gated on
    ``DELAY_CONTRACT_DATABASE_URL``. Under the old pattern neither was in the
    gated set, so deleting their ci.yml step would have left this guard green.
    """
    gated = _pg_gated_files()
    for name in (
        "test_certain_postseason_playoff_pg_9602.py",
        "test_a_delay_is_not_silence_pg_7617.py",
        "test_ws_slate_age_floor_pg_837.py",
    ):
        assert name in gated, f"{name} is PG-gated but the detector does not see it"

    assert PG_GATE_ENV_RE.search('os.environ.get("DELAY_CONTRACT_DATABASE_URL")')
    assert PG_GATE_ENV_RE.search('os.environ.get("SEARCH_TEST_DATABASE_URL")')
    # The bare app URL is not a gate name; matching it would sweep in files
    # that read the app's own database setting.
    assert not PG_GATE_ENV_RE.search('os.environ.get("DATABASE_URL")')


def test_known_unwired_list_does_not_outlive_its_entries():
    """The debt list may not name a file that is already wired (or deleted).

    Without this, an entry silently becomes a permanent blanket exemption for a
    filename that a later step DID wire up — and the next unwired file with that
    name would inherit the waiver.
    """
    ci_text = CI_YML.read_text(encoding="utf-8")
    gated = _pg_gated_files()
    for name in sorted(KNOWN_UNWIRED):
        assert name in gated, (
            f"{name} is on the unwired debt list but is no longer a PG-gated "
            "integration test — drop the entry"
        )
        assert name not in ci_text, (
            f"{name} is on the unwired debt list but ci.yml now names it — "
            "drop the entry so the exemption cannot be inherited"
        )
