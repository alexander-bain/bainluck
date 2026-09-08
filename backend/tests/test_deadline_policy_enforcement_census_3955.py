"""The deadline constants cannot silently change enforcement status (#3955).

``request_cache`` declares two different KINDS of number under one comment block,
and the difference is invisible at the point of use:

* **Enforced bounds** — some code path reads the constant and actually stops work
  when it is exceeded. If one of these goes inert, the serving path quietly loses
  a real availability guard and every existing test still passes.
* **Contract bounds** — thresholds that exist so the C55 evaluator
  (``scripts/evals/cache_failure_resilience.evaluate_scenario``) can judge observed
  behaviour against them. Nothing enforces these, and nothing should: the router
  timeout is Heroku's H12 cutoff, an environmental fact we stay under rather than
  impose.

Twice now a reader has taken the second kind for the first (#3955 is the second
finding; the seam test's own header made the claim). This guard pins which is
which, so the next change to either list has to be deliberate.

It reads the CODE, not the values. A census of "is this bound enforced?" cannot be
a check on the bound's number — any number satisfies a number test, including the
number of an enforcement that has just been deleted. So the census walks the AST of
``app/`` and counts genuine *loads* of each name. Comments and prose mentioning a
constant are not AST nodes and therefore cannot fake enforcement; the declaring
assignments are Store context and are excluded for free.
"""

from __future__ import annotations

import ast
import pathlib

import pytest

APP_ROOT = pathlib.Path(__file__).resolve().parents[1] / "app"

# Bounds some code path actually applies. Losing one of these is a real regression:
# the constant keeps its value, the tests keep passing, and the guard is gone.
ENFORCED = {
    "REDIS_OP_DEADLINE_MS",
    "FEED_TOTAL_BUDGET_MS",
    "CALIBRATION_ROUTE_BUDGET_MS",
}

# Thresholds the contract evaluator judges against, enforced by nothing on purpose.
# Each entry carries the reason it is not wired, because "unwired" reads as "bug"
# to every fresh pair of eyes that finds it.
CONTRACT_ONLY = {
    # Heroku's H12 cutoff. We stay under it; we cannot impose it.
    "ROUTER_TIMEOUT_MS": "environmental — the router's cutoff, not ours to apply",
    # Superseded by the two whole-request budgets above, which are wired. A
    # per-stage compute bound cannot catch back-to-back attempts that are each
    # individually legal; that is the finding Queue 297 acted on.
    "COMPUTE_DEADLINE_MS": "superseded by the per-route whole-request budgets",
    # No pool-checkout hook applies it today.
    "DB_CHECKOUT_DEADLINE_MS": "no checkout hook applies it",
    # Queue 300B Item 0 removed the request path's build authority, and this
    # bounded exactly that build. Calibration's, per D46 — see #3955.
    "CALIBRATION_COMPUTE_DEADLINE_MS": "the build it bounded no longer runs here",
}

ALL_CONSTANTS = set(ENFORCED) | set(CONTRACT_ONLY)


def _load_sites() -> dict[str, list[str]]:
    """Every genuine read of each constant anywhere under ``app/``."""

    sites: dict[str, list[str]] = {name: [] for name in ALL_CONSTANTS}
    for path in sorted(APP_ROOT.rglob("*.py")):
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except (SyntaxError, UnicodeDecodeError):  # pragma: no cover - not our file
            continue
        for node in ast.walk(tree):
            # Bare `COMPUTE_DEADLINE_MS` inside the declaring module...
            if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load):
                name = node.id
            # ...or `_rc.COMPUTE_DEADLINE_MS` from anywhere else.
            elif isinstance(node, ast.Attribute):
                name = node.attr
            else:
                continue
            if name in sites:
                sites[name].append(f"{path.relative_to(APP_ROOT.parent)}:{node.lineno}")
    return sites


@pytest.fixture(scope="module")
def load_sites() -> dict[str, list[str]]:
    return _load_sites()


@pytest.mark.parametrize("name", sorted(ENFORCED))
def test_an_enforced_bound_still_has_a_site_that_applies_it(name, load_sites):
    """An enforced bound that loses its last reader goes inert in total silence."""

    assert load_sites[name], (
        f"{name} is listed as ENFORCED but nothing under app/ reads it any more. "
        "The value is still declared, so every other test still passes while the "
        "bound it names no longer applies. Either restore the enforcement, or move "
        f"{name} to CONTRACT_ONLY with the reason it is no longer wired."
    )


@pytest.mark.parametrize("name", sorted(CONTRACT_ONLY))
def test_a_contract_only_bound_has_not_quietly_become_enforced(name, load_sites):
    """If one of these gets wired, the prose describing it stops being true."""

    assert not load_sites[name], (
        f"{name} is documented as a contract-only threshold "
        f"({CONTRACT_ONLY[name]}), but app/ now reads it at "
        f"{load_sites[name]}. That may well be the right change — if so, move it to "
        "ENFORCED and update the policy comments in app/utils/request_cache.py and "
        "tests/integration/test_cache_failure_seam.py, which both tell the reader "
        "this bound is not applied."
    )


def test_the_census_covers_every_bound_the_policy_block_declares(load_sites):
    """A new constant must be classified, not left to be discovered by a reader."""

    declared = set()
    source = (APP_ROOT / "utils" / "request_cache.py").read_text(encoding="utf-8")
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and (
                    target.id.endswith("_DEADLINE_MS")
                    or target.id.endswith("_BUDGET_MS")
                    or target.id.endswith("_TIMEOUT_MS")
                ):
                    declared.add(target.id)

    unclassified = declared - ALL_CONSTANTS
    assert not unclassified, (
        f"request_cache declares {sorted(unclassified)}, which this census does not "
        "classify. Add each to ENFORCED or to CONTRACT_ONLY with its reason, so the "
        "next reader is told whether the serving path applies it."
    )
