"""#8730: clubs that were never MLS or EPL move to `soccer_other`, and only those.

## what is guarded

The repair's judgment is one pure rule, :func:`phantom_refusal`, applied to a
SQL superset on the way out, and :func:`restore_verdict` on the way back. These
tests hand both rules dicts and prove every clause declines on its own — a rule
that answered "move it" for everything it did not recognise would pass a suite
built only from the rows it repairs.

## what is NOT guarded here, said rather than left to be discovered

There is no database in this file, so nothing here proves the candidate SQL
selects what its docstring claims. That rests on measurement: production
2026-09-25, 641 MLS + 160 EPL teams, re-derived by the script's plan-only run
before any write, and the apply path re-judges each banked team on its live row.

## the reader-visible claim, tested through the code that makes it

The ship is "search stops calling Akwa United an MLS club and `fulham` shows
the real Fulham". The second half is not a line in the repair: it follows from
`soccer_other` NOT being a marquee key while the two source leagues ARE. So the
last tests drive search's own sort and same-name collapse over the Fulham rows
as they sit on production, before and after the move.
"""

from __future__ import annotations

import importlib
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

_SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"


def _load(name: str):
    """Import a `scripts/` module the way the restore imports the repair.

    `scripts/` is not a package; with `backend/` on `sys.path` it resolves as a
    namespace package, which is the seam the restore's `from scripts.repair_...`
    goes through. Loading both by that name makes the gate-sharing assertion
    below a statement about ONE function object, not two copies.
    """
    sys.path.insert(0, str(_SCRIPTS.parent))
    return importlib.import_module(f"scripts.{name}")


repair = _load("repair_8730_phantom_clubs_filed_under_mls_epl")
restore = _load("restore_8730_phantom_clubs_filed_under_mls_epl")

MLS, EPL, OTHER, LA_LIGA = 1326, 1298, 37873, 1317
SOURCES = {MLS, EPL}


def _team(**over):
    """Akwa United (team 5057) as it stands on production 2026-09-25."""
    row = {
        "id": 5057, "name": "Akwa United", "sport_id": MLS,
        "espn_id": None, "statpal_team_id": None, "external_id": None,
        "current_record": None, "has_standings": False,
        "n_events": 1, "n_anonymous": 1,
    }
    row.update(over)
    return row


# --- the rule: the specimen moves -------------------------------------------

def test_the_specimen_in_its_measured_shape_moves():
    assert repair.phantom_refusal(_team(), SOURCES) is None


def test_an_epl_filed_club_moves_too():
    assert repair.phantom_refusal(
        _team(id=4207, name="Corinthians", sport_id=EPL, n_events=3, n_anonymous=3),
        SOURCES,
    ) is None


# --- the rule: every clause declines on its own ------------------------------

def test_a_club_in_any_other_league_is_never_moved():
    assert repair.phantom_refusal(_team(sport_id=LA_LIGA), SOURCES) == repair.NOT_A_SOURCE_LEAGUE


def test_a_club_already_in_the_target_league_is_not_a_candidate():
    assert repair.phantom_refusal(_team(sport_id=OTHER), SOURCES) == repair.NOT_A_SOURCE_LEAGUE


@pytest.mark.parametrize("column", ["espn_id", "statpal_team_id", "external_id"])
def test_a_club_carrying_any_provider_id_is_never_moved(column):
    # Minnesota United FC is MLS because ESPN says so; any id is that evidence.
    assert repair.phantom_refusal(_team(**{column: "17362"}), SOURCES) == repair.HAS_PROVIDER_ID


def test_a_club_with_a_record_is_never_moved():
    assert repair.phantom_refusal(_team(current_record="7-8-11"), SOURCES) == repair.MAINTAINED


def test_a_club_with_standings_is_never_moved():
    assert repair.phantom_refusal(_team(has_standings=True), SOURCES) == repair.MAINTAINED


def test_a_club_that_plays_no_event_is_not_this_defect():
    # Its league came from somewhere other than the anonymous fixtures, so the
    # evidence this repair rests on is absent — decline rather than assume.
    assert repair.phantom_refusal(_team(n_events=0, n_anonymous=0), SOURCES) == repair.NO_EVENTS


def test_one_anchored_fixture_among_many_anonymous_ones_keeps_the_club():
    # Measured, not hypothetical: Los Angeles FC (2326) is an MLS row with no
    # provider id of its own, and 29 of its 44 fixtures are id-anchored. This
    # clause is the only one that keeps it in MLS.
    assert repair.phantom_refusal(
        _team(id=2326, name="Los Angeles FC", n_events=44, n_anonymous=15), SOURCES
    ) == repair.PLAYS_AN_ANCHORED_EVENT
    assert repair.phantom_refusal(
        _team(n_events=40, n_anonymous=39), SOURCES
    ) == repair.PLAYS_AN_ANCHORED_EVENT


def test_missing_counts_read_as_no_events_never_as_all_anonymous():
    row = _team()
    del row["n_events"], row["n_anonymous"]
    assert repair.phantom_refusal(row, SOURCES) == repair.NO_EVENTS


def test_the_sql_and_the_rule_define_anonymous_the_same_way():
    # The counts the rule reads are computed in SQL. Every id the header names
    # must be tested for NULL in BOTH arms, or one side of a fixture could count
    # as anonymous on evidence the other side's arm would reject.
    sql = repair._CANDIDATE_SQL
    for clause in (
        "e.external_id IS NULL", "e.espn_id IS NULL",
        "e.statpal_fixture_id IS NULL", "e.commence_time_source = 'statpal'",
    ):
        assert sql.count(clause) == 2, clause
    assert "e.home_team_id = b.id" in sql and "e.away_team_id = b.id" in sql


def test_the_survey_superset_already_excludes_every_provider_id():
    for column in ("espn_id", "statpal_team_id", "external_id"):
        assert f"t.{column} IS NULL" in repair._SURVEY_WHERE


def test_the_apply_path_reads_only_the_banked_teams():
    assert repair._BANKED_WHERE == f"t.id IN (SELECT team_id FROM {repair.BACKUP_TABLE})"


def test_the_leagues_are_the_two_the_reader_saw_and_the_catch_all():
    assert repair.SOURCE_LEAGUES == ("soccer_usa_mls", "soccer_epl")
    assert repair.TARGET_LEAGUE == "soccer_other"


# --- the app gate -------------------------------------------------------------

@pytest.mark.parametrize("app", [None, "bainluck-heavy", "bainluck-staging"])
def test_a_write_refuses_every_app_but_the_named_one(app, monkeypatch):
    if app is None:
        monkeypatch.delenv("HEROKU_APP_NAME", raising=False)
    else:
        monkeypatch.setenv("HEROKU_APP_NAME", app)
    for args in (SimpleNamespace(apply=True, backup=False),
                 SimpleNamespace(apply=False, backup=True)):
        assert repair.wrong_app_refusal(args) is not None


def test_the_named_app_is_permitted(monkeypatch):
    monkeypatch.setenv("HEROKU_APP_NAME", "bainluck")
    assert repair.wrong_app_refusal(SimpleNamespace(apply=True, backup=True)) is None


def test_a_plan_only_run_needs_no_app(monkeypatch):
    monkeypatch.delenv("HEROKU_APP_NAME", raising=False)
    assert repair.wrong_app_refusal(SimpleNamespace(apply=False, backup=False)) is None


def test_the_restore_shares_the_repairs_gate_and_bank_by_import():
    assert restore.wrong_app_refusal is repair.wrong_app_refusal
    assert restore.BACKUP_TABLE == repair.BACKUP_TABLE


# --- the undo -----------------------------------------------------------------

_BANKED = {"team_id": 5057, "sport_id_before": MLS, "sport_id_after": OTHER}


def test_a_moved_team_is_restored():
    assert restore.restore_verdict(_BANKED, OTHER) == restore.RESTORE


def test_a_team_already_holding_its_pre_image_is_a_no_op():
    assert restore.restore_verdict(_BANKED, MLS) == restore.NO_OP


def test_a_team_moved_again_since_is_left_alone():
    assert restore.restore_verdict(_BANKED, LA_LIGA) == restore.DIVERGED


def test_a_team_that_no_longer_exists_is_left_alone():
    assert restore.restore_verdict(_BANKED, None) == restore.DIVERGED


def test_the_restore_write_carries_the_restore_verdicts_condition():
    sql = " ".join(restore._RESTORE_SQL.split())
    assert "SET sport_id = b.sport_id_before" in sql
    assert "AND t.sport_id = b.sport_id_after" in sql


# --- the reader-visible claim, through search's own code ---------------------

def _row(team_id, sport_key, rank=0.6):
    return SimpleNamespace(id=team_id, name="Fulham", sport_key=sport_key, team_rank=rank)


def _search_card(rows):
    from app.routes.events import _pick_team_row_per_name, _sort_matched_team_rows

    return _pick_team_row_per_name(_sort_matched_team_rows(rows))


def test_the_move_takes_the_filed_rows_out_of_the_marquee_tiebreak():
    from app.routes.events import _MARQUEE_TEAM_SPORT_KEYS

    assert set(repair.SOURCE_LEAGUES) <= _MARQUEE_TEAM_SPORT_KEYS
    assert repair.TARGET_LEAGUE not in _MARQUEE_TEAM_SPORT_KEYS


def test_before_the_move_the_filed_fulham_can_hold_the_only_card():
    # Production `q=fulham`, 2026-09-25: the MLS row (4757) arrived ahead of the
    # EPL row (135); both marquee, same rank, same name — so arrival order won.
    card = _search_card([
        _row(4757, "soccer_usa_mls"), _row(135, "soccer_epl"),
        _row(1886, "soccer_fa_cup"), _row(17930, "soccer_england_efl_cup"),
    ])
    assert [r.id for r in card] == [4757]


@pytest.mark.parametrize("arrival", ["filed_first", "real_first"])
def test_after_the_move_the_real_fulham_holds_the_card_in_any_arrival_order(arrival):
    rows = [_row(4757, repair.TARGET_LEAGUE), _row(135, "soccer_epl"),
            _row(1886, "soccer_fa_cup"), _row(17930, "soccer_england_efl_cup")]
    if arrival == "real_first":
        rows = [rows[1], rows[0], *rows[2:]]
    assert [(r.id, r.sport_key) for r in _search_card(rows)] == [(135, "soccer_epl")]
