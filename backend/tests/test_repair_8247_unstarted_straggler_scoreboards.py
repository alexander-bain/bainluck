"""#8247: the 0-0 retraction writes only rows still in the exact defect shape.

## what is being guarded, and what deliberately is not

The repair's judgment is two pure functions — :func:`row_is_writable` on the way
out and :func:`classify` on the way back — plus a population pinned BY ID that it
re-verifies before it writes a byte. Those are what these tests cover, together
with the refusals that make the pair safe to hand to an operator: the wrong app,
a row that has settled, a row that took a real score, a row with no pre-image.

WHAT THEY DO NOT COVER IS THE SQL, and that is stated here rather than left to be
discovered. There is no fake session in this file at all: the two policy
functions are handed dicts, so these can prove the verdicts and nothing about
whether the UPDATE's WHERE clause selects the rows the docstring claims. That
claim rests on measurement instead — production 2026-09-23, every `scheduled`
row carrying live state grouped by shape, 13 rows at
`(0-0, 'Postponed', '0:00')` — pinned as :data:`EXPECTED` and re-derived by the
script on every run before it writes.

## why the pinned ids ARE the guard

The tempting predicate is `status='scheduled' AND completed_at IS NULL AND
home_score IS NOT NULL`. It selects exactly the right 13 rows today, and it is
the wrong thing to ship: a genuinely LIVE 0-0 game mis-stamped `scheduled` is
#5324's whole class, it recurs, and that predicate would blank its scoreboard
mid-game. So the population is pinned and every row re-checked, and
:func:`test_a_row_outside_the_pinned_population_is_never_written` is the arm that
fails if someone later "simplifies" the script back to the sweep.

## the asymmetry between the two directions

The repair may only ever turn `0-0` into NULL. The restore may only ever turn
that same NULL back into the banked `0-0`. Both refuse anything else, and the
refusal both share is the one that matters most: a postponed game CAN be made up
and played, at which point the row takes a real score — and neither script may
touch it. That is asserted in both directions, because a classifier that
answered "safe to write" for everything it did not recognise would pass a suite
built only from the arms it repairs.
"""

from __future__ import annotations

import importlib.util
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

_SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"


def _load(name: str):
    """Import a `scripts/` module by path.

    `scripts/` is not a package and is not on `sys.path` under pytest, so the
    script's own `sys.path.insert` of its directory is what makes the restore's
    sibling import work. Loading by path here exercises exactly that seam.
    """
    sys.path.insert(0, str(_SCRIPTS))
    spec = importlib.util.spec_from_file_location(name, _SCRIPTS / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


repair = _load("repair_8247_unstarted_straggler_scoreboards")
restore = _load("restore_8247_unstarted_straggler_scoreboards")

#: The specimen: /events/15290171, White Sox @ Blue Jays, postponed 2026-04-02.
SPECIMEN = 15290171


def _row(**kw):
    """A row in the defect shape, with overrides."""
    base = {
        "id": SPECIMEN,
        "status": "scheduled",
        "completed_at": None,
        "home_score": 0,
        "away_score": 0,
    }
    base.update(kw)
    return base


def _banked(**kw):
    """A restore row: the pre-image beside the live columns."""
    base = {
        "id": SPECIMEN,
        "prior_home_score": 0,
        "prior_away_score": 0,
        "status": "scheduled",
        "completed_at": None,
        "home_score": None,
        "away_score": None,
    }
    base.update(kw)
    return base


# ---------------------------------------------------------------------------
# the population is pinned, and that is deliberate
# ---------------------------------------------------------------------------


def test_the_pinned_population_is_the_thirteen_measured_rows():
    """13 ids, every one 0-0. A 14th appearing here needs its own measurement."""
    assert len(repair.EXPECTED) == 13
    assert {(h, a) for _id, h, a in repair.EXPECTED} == {(0, 0)}
    assert SPECIMEN in repair.EXPECTED_BY_ID


def test_a_row_outside_the_pinned_population_is_never_written():
    """The arm that fails if the script is 'simplified' back to a sweep.

    A live 0-0 game mis-stamped `scheduled` (#5324's class) is in the shape the
    obvious predicate selects and must never be blanked. The pinned ids are the
    only thing standing between this repair and that row.
    """
    assert repair.row_is_writable(_row(id=999_999_999)) == (
        "not in the pinned population"
    )


# ---------------------------------------------------------------------------
# row_is_writable — every refusal is a row that might not be the defect
# ---------------------------------------------------------------------------


def test_the_specimen_in_its_measured_shape_is_writable():
    """The positive control. Without it every refusal below is vacuous."""
    assert repair.row_is_writable(_row()) is None


def test_a_row_that_has_since_settled_is_refused():
    """`completed_at` means the score is now a result, not the defect."""
    row = _row(completed_at=datetime(2026, 9, 1, tzinfo=timezone.utc))
    assert "settled" in repair.row_is_writable(row)


def test_a_row_that_left_scheduled_is_refused():
    assert "status moved" in repair.row_is_writable(_row(status="live"))


def test_a_row_carrying_a_real_score_is_refused():
    """A postponed game CAN be made up and played. 7-3 is not the defect."""
    why = repair.row_is_writable(_row(home_score=7, away_score=3))
    assert "drifted" in why and "real result" in why


def test_an_already_repaired_row_is_a_no_op_not_a_write():
    assert repair.row_is_writable(_row(home_score=None, away_score=None)) == (
        "already repaired"
    )


# ---------------------------------------------------------------------------
# the app guard — notice 47(c)'s attended invocation
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("app", [None, "bainluck", "staging", ""])
def test_the_repair_refuses_every_app_but_the_named_one(app, monkeypatch):
    if app is None:
        monkeypatch.delenv("HEROKU_APP_NAME", raising=False)
    else:
        monkeypatch.setenv("HEROKU_APP_NAME", app)
    refusal = repair.wrong_app_refusal()
    assert refusal is not None and repair.PRODUCER_APP in refusal


def test_the_named_app_is_permitted(monkeypatch):
    monkeypatch.setenv("HEROKU_APP_NAME", repair.PRODUCER_APP)
    assert repair.wrong_app_refusal() is None


def test_the_restore_shares_the_repairs_app_guard_by_import():
    """One definition, not two — a divergent copy is how an undo runs somewhere
    the repair refused to."""
    assert restore.wrong_app_refusal is repair.wrong_app_refusal
    assert restore.BACKUP_TABLE == repair.BACKUP_TABLE


# ---------------------------------------------------------------------------
# classify — the undo, and what it must never stomp
# ---------------------------------------------------------------------------


def test_a_repaired_row_is_restorable():
    """The positive control for the undo direction."""
    assert restore.classify(_banked()) == restore.RESTORE


def test_a_row_that_took_a_real_score_after_the_repair_is_diverged():
    """The likeliest later decision is a legitimate one: the game was played.

    Putting a banked 0-0 back over a real 7-3 would be the undo causing the very
    defect the repair exists to remove, on a row that had recovered from it.
    """
    row = _banked(home_score=7, away_score=3)
    assert restore.classify(row) == restore.DIVERGED


def test_a_row_that_settled_after_the_repair_is_diverged():
    row = _banked(completed_at=datetime(2026, 9, 1, tzinfo=timezone.utc))
    assert restore.classify(row) == restore.DIVERGED


def test_a_row_left_scheduled_but_already_holding_the_pre_image_is_a_no_op():
    """Idempotence: a second run must not rewrite what it already wrote."""
    row = _banked(home_score=0, away_score=0)
    assert restore.classify(row) == restore.ALREADY_BACK


def test_a_bank_row_with_no_pre_image_is_never_guessed_at():
    """NULL/NULL in the bank is not an invitation to invent a scoreboard."""
    row = _banked(prior_home_score=None, prior_away_score=None)
    assert restore.classify(row) == restore.ALREADY_BACK
