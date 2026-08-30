"""The CERT-430 specimen producer, and the coupling it exists to hold.

CERT-433 withheld this branch's integration token for one reason: the mandated
`tournamentReskin` CERT-430 specimen stayed **green** when the backend
comparison-completeness contributor was deleted, because the frontend fixture
hardcoded the repaired payload.  Behaviour was guarded inside each layer; the
pre-registered **Tier-1 cross-layer kill was unmet**.

`scripts/emit_comparison_specimen.py` closes it by letting the Jest specimen
render a card the production `build_props` actually built.  That only works for
as long as three things stay true, and each one is a test below:

1. **The producer drives production code**, not a copy of it.
2. **Its output is deterministic**, or the consuming suite is flaky rather than
   coupled.
3. **The consumer is still wired to it.**  A producer nobody runs is a script,
   not a guard — the same failure one level up from the one CERT-433 found, and
   the reason `conceptAdmissionParity.test.ts` asserts its own wiring too.

The BEHAVIOUR the specimen encodes is asserted in `test_tournament_slate.py`
(`test_SPECIMEN_one_fresh_leg_cannot_make_a_comparison_live`).  This file is
about the RAIL, and deliberately re-asserts only the two values the cross-layer
kill turns on, so that a change to the rule fails in one obvious place rather
than in a scatter of near-duplicates.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import app.utils.tournament_slate as tournament_slate
from scripts import emit_comparison_specimen as producer

REPO_ROOT = Path(__file__).resolve().parents[2]
PRODUCER_REL = "backend/scripts/emit_comparison_specimen.py"
CONSUMER_REL = "frontend/__tests__/components/tournamentReskin.test.tsx"


def _run_producer() -> tuple[str, int]:
    """Execute the script the way the Jest suite does — bare interpreter."""
    result = subprocess.run(
        [sys.executable, str(REPO_ROOT / PRODUCER_REL)],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        env={"PYTHONPATH": str(REPO_ROOT / "backend"), "PATH": "/usr/bin:/bin"},
    )
    assert result.returncode == 0, (
        f"the producer exited {result.returncode}; the Jest specimen runs this "
        f"exact command and will fail the same way.\n{result.stderr}"
    )
    return result.stdout, result.returncode


def test_the_producer_calls_the_production_rule_not_a_copy():
    """The one property that makes the whole rail worth having.

    A producer that reimplemented `build_props` would emit a correct-looking
    payload forever, including after the production rule was deleted — which is
    precisely the class CERT-433 blocked, moved one file sideways.
    """
    assert producer.build_props is tournament_slate.build_props


def test_the_specimen_is_graded_dark_and_names_the_missing_leg():
    """CERT-430's executed scenario, through the production function.

    These are the two values the cross-layer kill turns on: the grade the
    renderer is asserted to agree with, and the name the page needs in order to
    say WHICH subject is missing.
    """
    card = producer.build_specimen("incomplete")
    assert card["price_state"] == "dark"
    assert card["legs"] == 2
    assert card["unpriced_legs"] == [producer.ALCARAZ_LEG]


def test_the_control_is_graded_live_so_the_kill_is_not_vacuous():
    """The other direction, and it is not optional.

    A rule that darkened every comparison would satisfy the specimen above and
    take the section's best card with it.  The Jest suite asserts this same case
    reads live; if it ever stopped doing so here, the specimen would be proving
    that the producer always says dark.
    """
    card = producer.build_specimen("complete")
    assert card["price_state"] == "live"
    assert card["unpriced_legs"] == []


def test_the_producer_is_deterministic():
    """Same input in, byte-identical JSON out.

    The consuming suite compares the backend's grade against the renderer's on
    every run.  A producer that moved with the wall clock would make that
    comparison flaky, and a flaky cross-layer gate gets deleted rather than
    fixed.  There is no clock read in the script for exactly this reason.
    """
    first, _ = _run_producer()
    second, _ = _run_producer()
    assert first == second
    parsed = json.loads(first)
    assert parsed["produced_by"] == "backend/app/utils/tournament_slate.py:build_props"
    assert set(parsed["cases"]) == {"incomplete", "complete"}


def test_the_producer_runs_without_our_third_party_requirements():
    """It must work on the frontend CI runner, which never runs `pip install`.

    `tournament_slate` and everything it imports are pure logic, so a bare
    interpreter is enough.  If someone adds a SQLAlchemy import anywhere in that
    chain this fails HERE, in the backend suite, rather than as a mystifying red
    in a frontend job that has no Python requirements installed to fix it with.

    Measured under `-S`, which takes `site-packages` off the path entirely, so
    this reproduces the frontend runner's condition rather than approximating
    it.  Counting loaded modules instead would be weaker in both directions: it
    would miss a package the interpreter happened to have, and it would flag
    whatever `sitecustomize` drags in on a developer's machine.

    It fails loudly and specifically, because the alternative is a mystifying
    red in a job with no Python requirements installed to fix it with.  Until
    2026-08-29 this would have failed: `app/utils/__init__.py` imports
    `futures_categorization`, whose module-scope `from app.services import llm`
    put SQLAlchemy, asyncpg, pydantic and httpx behind every `app.utils` import.
    """
    probe = (
        "import scripts.emit_comparison_specimen as p;"
        "print(p.build_specimen('incomplete')['price_state'])"
    )
    result = subprocess.run(
        [sys.executable, "-S", "-c", probe],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        env={"PYTHONPATH": str(REPO_ROOT / "backend"), "PATH": "/usr/bin:/bin"},
    )
    assert result.returncode == 0, (
        "the specimen producer no longer imports without third-party packages, "
        "so it can no longer run in the frontend CI job. Either keep the import "
        "chain pure or add an install step to `frontend-build`.\n"
        f"{result.stderr}"
    )
    assert result.stdout.strip().splitlines()[-1] == "dark"

    # And the ordinary path still produces the same payload.
    stdout, code = _run_producer()
    assert code == 0
    assert json.loads(stdout)["cases"]["incomplete"]["price_state"] == "dark"


def test_the_frontend_specimen_is_still_wired_to_this_producer():
    """A producer nobody runs is a script, not a guard.

    This is the assertion that stops the coupling being severed by someone
    re-typing the fixture — which is the exact edit CERT-433 blocked, and the
    edit a future queue is most likely to make while "simplifying a slow test".
    Narrow on purpose: it asserts the consumer names this producer, not anything
    about how the consumer is written.
    """
    consumer = REPO_ROOT / CONSUMER_REL
    assert consumer.is_file(), f"the CERT-430 consumer is missing: {CONSUMER_REL}"
    text = consumer.read_text(encoding="utf-8")
    assert "emit_comparison_specimen.py" in text, (
        f"{CONSUMER_REL} no longer runs {PRODUCER_REL}. The CERT-430 specimen is "
        "back to asserting against a literal, which is what CERT-433 withheld "
        "the integration token for."
    )
    # NON-VACUITY. The line above would still pass if the consumer merely
    # mentioned the producer in a comment while asserting against a hardcoded
    # grade, so the payload's own field has to appear too: the agreement check
    # cannot be written without reading it.
    assert "price_state" in text
