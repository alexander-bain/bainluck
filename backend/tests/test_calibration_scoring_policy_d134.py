"""D134 — a published calibration number names the METHOD that produced it.

Alex, 2026-09-11: "every grading/blending/calibration calculation carries a
versioned METHOD id; a METHODOLOGY LEDGER ... is kept forever and published with
the accuracy page ... As long as we can inform a skeptical auditor of what
changes we've made to our calculations, we can't be accused of anything nefarious
if we are only trying to make the calculations better over time."

WHAT THESE TESTS ARE FOR, AND WHY THERE ARE SIX OF THEM

The load-bearing test is :func:`test_the_pinned_pair_still_holds` — the pin that
turns a hand-set version string into a mechanism. But a pin is only worth what
its input covers, so the other five exist to stop this suite passing vacuously:

* if the fingerprint did not actually depend on a constant, the pin would hold
  while that constant moved — so every named constant is mutated and asserted to
  move it (:func:`test_every_named_constant_moves_the_fingerprint`);
* if a NEW deciding constant were added to the material without a mutation case,
  it would be covered by the pin but never proven to move it — so the two sets
  are asserted equal in both directions;
* if the fingerprint were process-dependent, two dynos would disagree about the
  method that scored the same board — so it is recomputed in a subprocess under a
  different hash seed;
* if the block were computed but never published, the wire would carry no method
  id at all;
* and a block that graded nothing must not claim a method.
"""

from __future__ import annotations

import json
import os
import pathlib
import subprocess
import sys

import pytest

from app.utils import calibration_scoring as scoring
from app.utils import calibration_sigma as sigma_ledger

# ---------------------------------------------------------------------------
# THE PIN
# ---------------------------------------------------------------------------
# These two literals are the whole guard. They are written here, in the test,
# and NOT beside the constants they describe — a pin that lives next to its
# subject gets updated in the same careless edit that moved the subject, which
# is the failure it exists to prevent.

EXPECTED_POLICY_VERSION = "m1"
EXPECTED_POLICY_FINGERPRINT = "d8c2f32561ea"

_BUMP_INSTRUCTIONS = """
A DECIDING CONSTANT MOVED. That is allowed — it is how the calculations get
better over time — but under D134 it is never silent. Three things happen in ONE
commit, or none of them do:

  1. bump `SCORING_POLICY_VERSION` in app/utils/calibration_scoring.py
     (m1 -> m2 -> ...; never edit an id in place, an old id must keep meaning
     what it meant),
  2. add a dated entry to docs/calibration/METHODOLOGY-LEDGER.md saying in plain
     English what changed, why, and what it affected in counts,
  3. update EXPECTED_POLICY_VERSION and EXPECTED_POLICY_FINGERPRINT here.

If you are here because you only meant to refactor, you did not only refactor.
"""


def test_the_pinned_pair_still_holds():
    """The method id and the constants it names cannot drift apart."""
    assert scoring.SCORING_POLICY_VERSION == EXPECTED_POLICY_VERSION, _BUMP_INSTRUCTIONS
    assert scoring.scoring_policy_fingerprint() == EXPECTED_POLICY_FINGERPRINT, (
        _BUMP_INSTRUCTIONS
        + f"\nmaterial now: {json.dumps(scoring.scoring_policy_material(), sort_keys=True)}"
    )


# ---------------------------------------------------------------------------
# THE ANTI-VACUITY TEST
# ---------------------------------------------------------------------------
# Each case is (module-under-monkeypatch, attribute, a value that is DIFFERENT
# and structurally valid). A pin over a fingerprint that ignores one of its
# inputs is a green test guarding nothing, and the only way to know is to move
# each input and watch the hash move.

_MUTATIONS = [
    pytest.param(scoring, "BAR_PP", 3.5, id="reader-bar"),
    pytest.param(
        scoring,
        "CLASS_BARS_PP",
        {
            "A_multibook_consensus": 2.0,
            "B_exchange_contest": 3.0,
            "C_exchange_standalone": 3.0,
        },
        id="class-bars",
    ),
    pytest.param(
        scoring,
        "GAME_CATEGORIES",
        frozenset({"baseball", "basketball"}),
        id="game-categories",
    ),
    pytest.param(scoring, "MIN_CELL_N", 500, id="min-cell-n"),
    pytest.param(scoring, "SIGMA_GATE", 1.96, id="sigma-gate"),
    pytest.param(scoring, "HEADLINE_TARGET_PP", 1.5, id="headline-target"),
    pytest.param(scoring, "SE_CONVENTION_PP", 25.0, id="se-convention"),
    pytest.param(sigma_ledger, "CELL_DRIFT_BAND", (0.80, 1.20), id="cell-drift-band"),
    pytest.param(sigma_ledger, "COVERAGE_BAND", (0.80, 1.20), id="coverage-band"),
]


@pytest.mark.parametrize("module,attr,replacement", _MUTATIONS)
def test_every_named_constant_moves_the_fingerprint(
    monkeypatch, module, attr, replacement
):
    """Mutate one deciding constant; the fingerprint must not survive it."""
    before = scoring.scoring_policy_fingerprint()
    assert getattr(module, attr) != replacement, (
        f"{attr}'s replacement equals the live value, so this case proves nothing — "
        "pick a different one."
    )
    monkeypatch.setattr(module, attr, replacement)
    assert scoring.scoring_policy_fingerprint() != before, (
        f"{module.__name__}.{attr} changed and the fingerprint did not. It is a "
        "deciding constant that scoring_policy_material() does not cover, so the "
        "pin above cannot defend it."
    )


def test_the_named_omissions_are_still_the_only_omissions():
    """`scoring_policy_material` covers exactly the keys the docstring claims.

    A key added to the material without a mutation case above would be covered by
    the pin but never proven to move it; a key removed would silently narrow what
    the fingerprint defends. Both are caught here rather than by inspection.
    """
    assert set(scoring.scoring_policy_material()) == {
        "bar_pp",
        "class_bars_pp",
        "game_categories",
        "min_cell_n",
        "sigma_gate",
        "headline_target_pp",
        "se_convention_pp",
        "cell_drift_band",
        "coverage_band",
    }
    # Both directions: every material key has a mutation case above, and every
    # case names a real material key. One direction alone lets a new key ship
    # covered-but-unproven, or a case rot into testing nothing.
    mutated_attrs = [param.values[1] for param in _MUTATIONS]
    assert len(set(mutated_attrs)) == len(_MUTATIONS), "two cases target one attribute"
    assert {attr.lower() for attr in mutated_attrs} == set(
        scoring.scoring_policy_material()
    )


def test_the_fingerprint_does_not_depend_on_the_process():
    """Two dynos scoring the same board must name the same method.

    `hash()` is salted per process; a fingerprint built on it would differ
    between workers and read as a methodology change that never happened.
    """
    # Derived from the module's own location, never from the cwd: this test is
    # run from `backend/` by CI and from the repo root by hand, and a `.` on
    # sys.path would make it pass in one place and ImportError in the other.
    backend_root = pathlib.Path(scoring.__file__).resolve().parents[2]
    prog = (
        f"import sys; sys.path.insert(0, {str(backend_root)!r});"
        "from app.utils import calibration_scoring as s;"
        "print(s.scoring_policy_fingerprint())"
    )
    seen = set()
    for seed in ("0", "1", "12345"):
        env = {**os.environ, "PYTHONHASHSEED": seed}
        out = subprocess.run(
            [sys.executable, "-c", prog],
            capture_output=True,
            text=True,
            env=env,
            check=True,
        )
        seen.add(out.stdout.strip())
    assert seen == {EXPECTED_POLICY_FINGERPRINT}, (
        f"fingerprint varies with PYTHONHASHSEED: {seen} — it is reading an "
        "unordered structure somewhere in scoring_policy_material()."
    )


# ---------------------------------------------------------------------------
# THE WIRE
# ---------------------------------------------------------------------------

_PAYLOAD = {
    "generated_at": "2026-09-11T19:16:46.466890+00:00",
    "population_version": "q269",
    "mce_closing_line": 1.1,
    "by_category": [],
    "by_source": [],
}


def test_the_scorecard_publishes_the_policy_beside_the_population():
    """A number that says which rows but not which method is half-provenanced."""
    block = scoring.scorecard(_PAYLOAD, load_ledger=False)
    assert block["population_version"] == "q269"
    policy = block["scoring_policy"]
    assert policy == {
        "version": EXPECTED_POLICY_VERSION,
        "fingerprint": EXPECTED_POLICY_FINGERPRINT,
        "in_force_since": scoring.SCORING_POLICY_IN_FORCE_SINCE,
    }


def test_an_unavailable_scorecard_claims_no_method():
    """Nothing was graded, so no method graded it.

    A `scoring_policy` on a block whose every count is `None` would let a reader
    tie a method id to numbers that do not exist.
    """
    assert "scoring_policy" not in scoring.unavailable("no payload")
