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
PG_GATE_ENV_RE = re.compile(r"[A-Z_]*TEST_DATABASE_URL")

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
