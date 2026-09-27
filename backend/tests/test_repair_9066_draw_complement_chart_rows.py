"""#9066 — the repair that takes the away side's price off soccer chart lines.

The repair is a D51(b) production write, so the policy lives in pure per-group
functions and is pinned here: which groups may be deleted, what row shape counts
as an away-leg reading, which app may run it, and that the specimen's HOME rows
are never in the population.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

_SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"


def _load(name: str):
    """Import a `scripts/` module by path (same seam as the #8960 test)."""
    sys.path.insert(0, str(_SCRIPTS))
    spec = importlib.util.spec_from_file_location(name, _SCRIPTS / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


repair = _load("repair_9066_draw_complement_chart_rows")
restore = _load("restore_9066_draw_complement_chart_rows")

#: /events/15316107, Croatia v England, KXUEFANLGAME-26OCT03CROENG.
SPECIMEN_KEY = (15316107, 62398724, "England")
SPECIMEN_EVENT = {
    "id": 15316107,
    "home_team_name": "Croatia",
    "away_team_name": "England",
}
SPECIMEN_OUTCOMES = ["England", "Croatia", "Tie"]


def _row(row_id=13842049, *, home=0.23, yes=0.77):
    return {"id": row_id, "home_win_probability": home, "yes_probability": yes}


def _banked(key):
    return next(c for e, m, leg, c in repair.EXPECTED if (e, m, leg) == key)


def test_the_specimens_away_leg_group_is_pinned_and_deletable():
    rows = [_row(), _row(13842053, home=0.23, yes=0.77)]
    assert (
        repair.group_is_deletable(
            SPECIMEN_KEY, _banked(SPECIMEN_KEY), SPECIMEN_EVENT, SPECIMEN_OUTCOMES, rows
        )
        is None
    )


def test_the_specimens_home_leg_rows_are_never_in_the_population():
    """The 62 Croatia-leg rows are the true series; the repair must leave them."""
    assert (15316107, 62398724, "Croatia") not in repair.EXPECTED_KEYS
    assert (
        repair.group_is_deletable(
            (15316107, 62398724, "Croatia"), 62, SPECIMEN_EVENT, SPECIMEN_OUTCOMES,
            [_row(13919427, home=0.8, yes=0.8)],
        )
        == "not in the pinned population"
    )


def test_both_away_leg_shapes_are_recognised_and_nothing_else_is():
    assert repair.row_shape_is_away_reading(_row(home=0.23, yes=0.77))  # 1 - yes
    assert repair.row_shape_is_away_reading(_row(home=0.70, yes=0.70))  # yes itself
    assert not repair.row_shape_is_away_reading(_row(home=0.25, yes=0.50))
    assert not repair.row_shape_is_away_reading(_row(home=None, yes=0.5))
    assert not repair.row_shape_is_away_reading(_row(home=0.5, yes=None))


def test_a_group_with_an_off_shape_row_is_refused_whole():
    rows = [_row(), _row(99, home=0.25, yes=0.50)]
    why = repair.group_is_deletable(
        SPECIMEN_KEY, _banked(SPECIMEN_KEY), SPECIMEN_EVENT, SPECIMEN_OUTCOMES, rows
    )
    assert why is not None and "not an away-leg reading" in why


def test_more_rows_than_banked_means_a_writer_is_still_running():
    rows = [_row(i) for i in range(_banked(SPECIMEN_KEY) + 1)]
    why = repair.group_is_deletable(
        SPECIMEN_KEY, _banked(SPECIMEN_KEY), SPECIMEN_EVENT, SPECIMEN_OUTCOMES, rows
    )
    assert why is not None and "something wrote more" in why


def test_a_field_that_lost_its_draw_leg_is_no_longer_evidenced():
    """The production predicate is re-asked: no Tie leg, the complement IS home."""
    why = repair.group_is_deletable(
        SPECIMEN_KEY, _banked(SPECIMEN_KEY), SPECIMEN_EVENT, ["England", "Croatia"],
        [_row()],
    )
    assert why is not None and "no longer the away leg" in why


def test_a_leg_that_now_names_the_home_side_is_refused():
    swapped = dict(SPECIMEN_EVENT, home_team_name="England", away_team_name="Croatia")
    why = repair.group_is_deletable(
        SPECIMEN_KEY, _banked(SPECIMEN_KEY), swapped, SPECIMEN_OUTCOMES, [_row()]
    )
    assert why is not None and "no longer the away leg" in why


def test_an_empty_group_is_already_repaired_and_a_missing_event_refuses():
    assert (
        repair.group_is_deletable(
            SPECIMEN_KEY, _banked(SPECIMEN_KEY), SPECIMEN_EVENT, SPECIMEN_OUTCOMES, []
        )
        == "already repaired"
    )
    why = repair.group_is_deletable(
        SPECIMEN_KEY, _banked(SPECIMEN_KEY), None, SPECIMEN_OUTCOMES, [_row()]
    )
    assert why is not None and "no longer exists" in why


def test_the_pin_is_the_measured_census():
    assert len(repair.ROUND_1) == 99
    assert sum(c for *_, c in repair.ROUND_1) == 9414
    assert len(repair.EXPECTED) == 100
    assert len(repair.EXPECTED_KEYS) == 100
    # Round 1's 9,414, less Georgia's 97, plus round 2's 117 + 1,432.
    assert sum(c for *_, c in repair.EXPECTED) == 10866
    assert len({e for e, *_ in repair.EXPECTED}) == 98
    assert _banked(SPECIMEN_KEY) == 185


#: /events/15314006, LA Galaxy v Colorado Rapids, KXMLSGAME-26SEP26LAGCOL (#9130).
GALAXY_KEY = (15314006, 61485166, "Colorado")
GALAXY_EVENT = {
    "id": 15314006,
    "home_team_name": "LA Galaxy",
    "away_team_name": "Colorado Rapids",
}
#: The market's real legs, read from production 2026-09-27.
GALAXY_OUTCOMES = ["Los Angeles G", "Colorado", "Tie"]
GEORGIA_KEY = (15314891, 62398778, "Georgia")


def test_round_two_replaces_round_ones_georgia_count():
    assert (15314891, 62398778, "Georgia", 97) in repair.ROUND_1
    assert _banked(GEORGIA_KEY) == 117
    assert sum(1 for e, m, leg, _ in repair.EXPECTED if (e, m, leg) == GEORGIA_KEY) == 1


def test_the_galaxy_away_leg_group_is_pinned_and_deletable():
    # Last pre-kick-off row as stored: 0.7050 = 1 - P(Colorado) = P(Galaxy) + P(Tie).
    rows = [_row(13971390, home=0.705, yes=0.295), _row(13969977, home=0.51, yes=0.49)]
    assert _banked(GALAXY_KEY) == 1432
    assert (
        repair.group_is_deletable(
            GALAXY_KEY, _banked(GALAXY_KEY), GALAXY_EVENT, GALAXY_OUTCOMES, rows
        )
        is None
    )


def test_the_galaxy_home_leg_is_never_pinned():
    assert not any(
        e == 15314006 and leg != "Colorado" for e, _, leg, _ in repair.EXPECTED
    )


def test_a_galaxy_row_written_after_the_recensus_stops_the_group():
    rows = [_row(i, home=0.705, yes=0.295) for i in range(_banked(GALAXY_KEY) + 1)]
    why = repair.group_is_deletable(
        GALAXY_KEY, _banked(GALAXY_KEY), GALAXY_EVENT, GALAXY_OUTCOMES, rows
    )
    assert why is not None and "since the census" in why


@pytest.mark.parametrize("app", [None, "bainluck", "bainluck-staging"])
def test_only_the_heavy_app_may_apply(monkeypatch, app):
    if app is None:
        monkeypatch.delenv("HEROKU_APP_NAME", raising=False)
    else:
        monkeypatch.setenv("HEROKU_APP_NAME", app)
    assert repair.wrong_app_refusal() is not None


def test_the_heavy_app_is_allowed(monkeypatch):
    monkeypatch.setenv("HEROKU_APP_NAME", "bainluck-heavy")
    assert repair.wrong_app_refusal() is None


def test_restore_reads_the_repairs_own_backup_table():
    assert restore.BACKUP_TABLE == repair.BACKUP_TABLE == (
        "backup_9066_draw_complement_chart_rows"
    )
