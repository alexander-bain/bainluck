"""The name-forms sweep's exit code means "no NEW collision". #2823.

``scripts/audit_authority_name_forms.py`` sweeps every distinct team name on
production and reports each canonical form reached by two different names. Most
of those are the rule WORKING — ``Chelsea``/``Chelsea FC`` is one club — and 50
of them are pinned in
:data:`~app.utils.authority_name_forms.EXPECTED_COLLISIONS` after being judged
by hand.

**The script used to exit ``1`` whenever any collision existed at all**, pinned
ones included, so a perfectly healthy corpus failed every run and the exit code
told a caller nothing. Its own docstring promised the opposite ("no collision
outside the pinned allowlist"). These tests hold the two apart, and the first
one is the regression: under the old ``return 1 if total_hits else 0`` a corpus
whose only collisions are pinned exits ``1`` and
:func:`test_a_corpus_of_only_pinned_collisions_exits_zero` goes red.

They drive ``main`` rather than a helper, because the exit code is the thing
that was wrong and a helper's return value is not an exit code.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

from app.utils.authority_name_forms import EXPECTED_COLLISIONS

SCRIPT_PATH = (
    Path(__file__).resolve().parents[1] / "scripts" / "audit_authority_name_forms.py"
)
SPEC = importlib.util.spec_from_file_location("audit_authority_name_forms", SCRIPT_PATH)
audit = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules[SPEC.name] = audit
SPEC.loader.exec_module(audit)

SPORT = "soccer_epl"


@pytest.fixture
def run(monkeypatch):
    """Drive ``main`` over a corpus we choose, with no network and no token check.

    ``load_corpus`` is the only thing between ``main`` and production, so
    replacing it exercises every line of the classification and the exit code.
    """

    def _run(names, argv=("audit_authority_name_forms.py",)):
        monkeypatch.setattr(audit, "TOKEN", "test-token")
        monkeypatch.setattr(audit, "load_corpus", lambda sport: {SPORT: set(names)})
        monkeypatch.setattr(sys, "argv", list(argv))
        return audit.main()

    return _run


def test_a_corpus_of_only_pinned_collisions_exits_zero(run, capsys):
    """THE REGRESSION. ``Chelsea``/``Chelsea FC`` is pinned, so this is healthy.

    The old exit code returned 1 here — a collision is a collision — which is
    what made it unreadable.
    """
    assert EXPECTED_COLLISIONS["chelsea"] == {
        "chelsea",
        "chelsea fc",
    }, "this test's fixture is only a pinned collision while the pin says so"
    assert run(["Chelsea", "Chelsea FC"]) == 0
    out = capsys.readouterr().out
    assert "[known  ]" in out
    assert "FAIL" not in out


def test_a_corpus_with_no_collision_at_all_exits_zero(run):
    """The control: zero is not reached only by the pinned path."""
    assert run(["Chelsea", "Arsenal", "Everton"]) == 0


def test_an_unjudged_collision_exits_one(run, capsys):
    """``Rovers``/``Rovers FC`` collide and nobody has judged them."""
    assert "rovers" not in EXPECTED_COLLISIONS, "fixture must be genuinely unpinned"
    assert run(["Rovers", "Rovers FC"]) == 1
    out = capsys.readouterr().out
    assert "[NEW    ]" in out
    assert "nobody has judged" in out


def test_a_pinned_collision_that_grows_exits_one(run, capsys):
    """A judgment covered the names it was made about, not a third one later.

    ``AC Chelsea`` also reduces to ``chelsea``. The pin says that form belongs
    to exactly two spellings, so a third is unjudged even though the form is
    listed — the failure a plain ``form in EXPECTED_COLLISIONS`` check misses.
    """
    assert run(["Chelsea", "Chelsea FC", "AC Chelsea"]) == 1
    out = capsys.readouterr().out
    assert "[WIDENED]" in out
    assert "not when they were judged" in out


def test_the_script_and_the_suite_share_one_pinned_list(run):
    """Not a fork: the script reads the same object the guard test asserts on.

    If the list is ever copied into the script, the two can drift and the
    script will call a collision new that the suite calls known.
    """
    assert audit.EXPECTED_COLLISIONS is EXPECTED_COLLISIONS


def test_a_vanished_pin_is_reported_and_does_not_fail(run, capsys):
    """The corpus is live; a club we no longer hold cannot collide.

    Reported so a pin can be pruned deliberately, never failed — otherwise the
    sweep goes red for a team leaving the league.
    """
    assert run(["Chelsea", "Chelsea FC"]) == 0
    out = capsys.readouterr().out
    assert "no longer present" in out
    assert f"{len(EXPECTED_COLLISIONS) - 1} pinned collision(s)" in out


def test_a_sport_slice_does_not_report_every_other_sport_as_vanished(run, capsys):
    """A scoped run cannot see the other sports' pinned forms.

    Without this the ``--sport`` path prints 49 false "vanished" lines, which
    is the noise that trains a reader to ignore the section.
    """
    code = run(
        ["Chelsea", "Chelsea FC"],
        argv=("audit_authority_name_forms.py", "--sport", SPORT),
    )
    assert code == 0
    assert "no longer present" not in capsys.readouterr().out
