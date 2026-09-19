"""#7147 — the CAL-P002 apply pass gets the backup D51(b) asks for.

The repair itself has been correct and unrunnable since August: its apply was
approved under ATTENDED capped-batch discipline, it banked nothing, and D51(b)'s
"a repair that backs up first may be applied by the owning lane" door was
therefore shut to it. Nobody walked ~170 (sport, date) groups by hand, so
production served `St. Louis Cardinals 5 — 5 San Francisco Giants, FINAL` for
three days on a game ESPN finalled 5-6. An MLB game cannot end level.

Two properties carry this change and both are guarded here:

* **a write with no banked row must not happen.** Not "should" — the bank and
  the reconciliation are inside the group transaction precisely so the commit
  that lands a repair lands its undo. The gate is tested by making the bank
  fail and asserting the score UPDATE never runs.
* **the undo compare-and-swaps on what the repair WROTE, not on difference.**
  This cohort is rows ESPN adjudicates, so ESPN correcting its own final again
  is the outcome the repair exists to permit. An undo keyed on "differs from the
  backup" would revert exactly those corrections (CERT-2439's lesson, inherited
  rather than re-learned).
"""
import datetime as dt
import importlib.util
import pathlib
import re

import pytest

_SCRIPTS = pathlib.Path(__file__).resolve().parents[1] / "scripts"


def _load(name):
    spec = importlib.util.spec_from_file_location(name, _SCRIPTS / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


repair = _load("repair_event_final_scores")
restore = _load("restore_7147_event_final_scores")


# ---------------------------------------------------------------------------
# the statements
# ---------------------------------------------------------------------------

def test_every_new_statement_parses_as_postgres():
    """A syntax error in a repair is otherwise found by a dyno nobody reads."""
    sqlglot = pytest.importorskip("sqlglot")
    for sql in (
        repair._BAK_CREATE_SQL,
        repair._BAK_COPY_SQL,
        repair._BAK_EXISTS_SQL,
        repair._BAK_MISSING_SQL,
        restore._PLAN_SQL,
        restore._RESTORE_SQL,
    ):
        sqlglot.parse_one(sql, dialect="postgres")


def _set_columns(sql: str) -> set:
    body = re.findall(r"SET\s+(.*?)\s+WHERE", sql, re.S)[0]
    return {part.split("=")[0].strip() for part in body.replace("\n", " ").split(",")}


def test_the_repair_writes_no_column_the_undo_does_not_restore():
    """An undo that restores less than the repair wrote is not an undo.

    The repair writes the score, the completion time and — on a winner flip —
    the blend, across three separate statements. All three columns have to come
    back, or the row lands in a state neither the repair nor production ever
    produced.
    """
    written = (
        _set_columns(repair._FIX_SCORE_SQL)
        | _set_columns(repair._FIX_COMPLETED_AT_SQL)
        | {"win_probability_sources"}  # the blend restamp, via _apply_final_pm_win_prob
    )
    assert written == {
        "home_score", "away_score", "completed_at", "win_probability_sources",
    }
    assert _set_columns(restore._RESTORE_SQL) == written


def test_the_backup_banks_every_column_the_undo_needs():
    """The bank has to happen BEFORE the write, so it cannot read them back."""
    for column in (
        "old_home_score", "old_away_score", "old_completed_at",
        "old_win_probability_sources",
    ):
        assert column in repair._BAK_CREATE_SQL
        assert column in repair._BAK_COPY_SQL
        assert column in restore._PLAN_SQL


def test_the_banked_old_values_are_never_overwritten_by_a_second_run():
    """A row repaired, drifted and repaired again must restore to what
    production held before we EVER touched it — not to our own last write.

    So the conflict clause updates the `new_*` half and leaves the `old_*` half
    alone. Getting this backwards would quietly make the undo a no-op.
    """
    conflict = repair._BAK_COPY_SQL.split("ON CONFLICT", 1)[1]
    assert "new_home_score = EXCLUDED" in conflict
    assert "new_away_score = EXCLUDED" in conflict
    for banked in ("old_home_score", "old_away_score", "old_completed_at",
                   "old_win_probability_sources"):
        assert f"{banked} = EXCLUDED" not in conflict


def test_the_undo_compare_and_swaps_on_what_we_wrote_not_on_difference():
    """CERT-2439. On this cohort ESPN correcting itself again is the EXPECTED
    later state, so "differs from the backup" would revert the correction."""
    sql = " ".join(restore._RESTORE_SQL.split())
    assert "home_score IS NOT DISTINCT FROM :new_home_score" in sql
    assert "away_score IS NOT DISTINCT FROM :new_away_score" in sql


# ---------------------------------------------------------------------------
# the pure gates
# ---------------------------------------------------------------------------

def test_the_apply_gate_rejects_an_empty_reconciliation():
    """`all()` over an empty mapping is True — the emptiness test IS the guard.

    Without it a reconciliation that inspected nothing (no rows, or a backup
    table that does not exist yet) reads as a clean pass and the apply proceeds
    with no undo (gotcha #53).
    """
    assert repair.backup_is_exact({}) is False
    assert repair.backup_is_exact({"events": 0}) is True
    assert repair.backup_is_exact({"events": 1}) is False


@pytest.mark.asyncio
async def test_reconciling_nothing_reports_nothing_rather_than_clean():
    """Pinned because the apply path never reaches it, so no end-to-end test
    can: `reconcile_backup([])` returning `{"events": 0}` would read as a clean
    backup for a set of rows nobody looked at. A mutation to that effect
    survived the whole suite until this test existed.
    """
    assert await repair.reconcile_backup(object(), []) == {}
    assert repair.backup_is_exact(await repair.reconcile_backup(object(), [])) is False


class _PlanRow:
    def __init__(self, *, new=(5, 6), current=(5, 6)):
        self.event_id = 15313231
        self.old_home_score, self.old_away_score = 5, 5
        self.old_completed_at = dt.datetime(2026, 9, 16, 20, 34, tzinfo=dt.timezone.utc)
        self.old_win_probability_sources = {"final_result": {"home_win": 0.5}}
        self.new_home_score, self.new_away_score = new
        self.current_home_score, self.current_away_score = current


def test_a_row_still_holding_our_write_is_restorable():
    assert restore.restorable(_PlanRow(new=(5, 6), current=(5, 6))) is True


def test_a_row_espn_has_corrected_again_is_not_restorable():
    """The live 5-7 is newer information than our 5-6; the undo leaves it."""
    assert restore.restorable(_PlanRow(new=(5, 6), current=(5, 7))) is False


def test_a_row_someone_reverted_by_hand_is_not_restorable():
    """Back at the pre-repair 5-5 — there is nothing to undo, and writing the
    banked value again would be indistinguishable from a repair."""
    assert restore.restorable(_PlanRow(new=(5, 6), current=(5, 5))) is False


# ---------------------------------------------------------------------------
# the apply loop, end to end against a fake session
# ---------------------------------------------------------------------------

_DATE = dt.date(2026, 9, 16)
_COMMENCE = dt.datetime(2026, 9, 16, 17, 15, tzinfo=dt.timezone.utc)


class _Team:
    """ESPN hands back a team OBJECT, not a string — `_espn_team_name` reads
    `display_name` off it. A string stand-in here would make the fixture pass a
    shape production never sees."""

    def __init__(self, display_name):
        self.display_name = display_name
        self.name = display_name
        self.short_name = display_name


class _Game:
    """One ESPN scoreboard entry."""

    def __init__(self):
        self.espn_id = "401816969"
        self.home_team = _Team("St. Louis Cardinals")
        self.away_team = _Team("San Francisco Giants")
        self.home_score, self.away_score = 5, 6
        self.status = "post"
        self.date = _COMMENCE


class _Candidate:
    """One settled row of ours, frozen on a mid-game 5-5."""

    def __init__(self):
        self.event_id = 15313231
        self.espn_id = "401816969"
        self.sport_key = "baseball_mlb"
        self.ev_status = "completed"
        self.home_team_name = "St. Louis Cardinals"
        self.away_team_name = "San Francisco Giants"
        self.home_score, self.away_score = 5, 5
        self.commence_time = _COMMENCE
        self.completed_at = dt.datetime(2026, 9, 16, 20, 34, tzinfo=dt.timezone.utc)
        self.game_date = _DATE


class _Group:
    sport_key, game_date, n = "baseball_mlb", _DATE, 1


class _Result:
    def __init__(self, rows=None, one=None, scalar=None, rowcount=0):
        self._rows, self._one, self._scalar = rows or [], one, scalar
        self.rowcount = rowcount

    def all(self):
        return self._rows

    def one(self):
        return self._one

    def scalar_one(self):
        return self._scalar

    def scalar_one_or_none(self):
        return self._scalar


class _Pop:
    n = 1


class _FakeSession:
    """Answers by statement shape and RECORDS THE ORDER it was asked.

    `bank_succeeds=False` models the one failure the gate exists for: the bank
    INSERT matched no event row, so nothing was banked and the reconciliation
    still finds the row missing.
    """

    def __init__(self, *, bank_succeeds=True):
        self.bank_succeeds = bank_succeeds
        self.calls: list[str] = []
        self.commits = 0

    async def execute(self, stmt, params=None, *_a, **_kw):
        sql = " ".join(str(stmt).split())
        if "CREATE TABLE IF NOT EXISTS" in sql:
            self.calls.append("bak_create")
            return _Result()
        if sql.startswith(f"INSERT INTO {repair.BAK_TABLE}"):
            self.calls.append("bank")
            return _Result(rowcount=1 if self.bank_succeeds else 0)
        if "to_regclass" in sql:
            return _Result(scalar=True)
        if f"NOT EXISTS (SELECT 1 FROM {repair.BAK_TABLE}" in sql:
            self.calls.append("reconcile")
            return _Result(scalar=0 if self.bank_succeeds else 1)
        if "UPDATE events SET home_score" in sql:
            self.calls.append("fix_score")
            return _Result(rowcount=1)
        if "UPDATE events SET completed_at" in sql:
            self.calls.append("fix_completed_at")
            return _Result(rowcount=1)
        if "GROUP BY 1, 2" in sql:
            return _Result(rows=[_Group()])
        if sql.startswith("SELECT e.id AS event_id"):
            return _Result(rows=[_Candidate()])
        if sql.startswith("SELECT COUNT(*) AS n"):
            return _Result(one=_Pop())
        return _Result(rows=[], scalar=None)

    async def commit(self):
        self.commits += 1


class _FakeESPN:
    async def get_scoreboard(self, sport_key, yyyymmdd):
        return [_Game()]


@pytest.fixture
def stub_espn(monkeypatch):
    import app.services.espn_api as espn_api

    # The class IS the factory the repair wants: `get_espn_service()` calls it
    # and gets an instance. A `lambda: _FakeESPN()` wrapper would be the same
    # thing spelled twice (CodeQL py/unnecessary-lambda).
    monkeypatch.setattr(espn_api, "get_espn_service", _FakeESPN)


@pytest.mark.asyncio
async def test_the_bank_lands_before_the_write_it_covers(stub_espn):
    """The ordering IS the guarantee. Both statements are in one transaction, so
    a bank after the write would still commit together — but a bank that is
    never reached at all (an exception, a deadline, a future edit moving the
    write up) would not, and the order is what makes that unrepresentable."""
    s = _FakeSession()
    result = await repair.repair(s, apply=True, sport="baseball_mlb", limit=1)

    assert result["scores_repaired"] == 1
    assert result["backup_refused"] == 0
    assert s.calls.index("bank") < s.calls.index("fix_score")
    assert s.calls.index("reconcile") < s.calls.index("fix_score")


@pytest.mark.asyncio
async def test_a_row_that_could_not_be_banked_is_never_written(stub_espn):
    """The D51(b) gate, doing the only job it has."""
    s = _FakeSession(bank_succeeds=False)
    result = await repair.repair(s, apply=True, sport="baseball_mlb", limit=1)

    assert "fix_score" not in s.calls
    assert "fix_completed_at" not in s.calls
    assert result["scores_repaired"] == 0
    assert result["backup_refused"] == 1
    # The defect is still REPORTED — a refused write must not look like a clean
    # slate, or the next operator reads "nothing to do".
    assert result["score_defects"] == 1


@pytest.mark.asyncio
async def test_a_dry_run_banks_nothing_and_writes_nothing(stub_espn):
    """`apply=false` is the documented first call. It must not create the table
    (runtime DDL on a read-only-intent call) and must not bank a row."""
    s = _FakeSession()
    result = await repair.repair(s, apply=False, sport="baseball_mlb", limit=1)

    assert s.calls == []
    assert result["score_defects"] == 1
    assert result["scores_repaired"] == 0


@pytest.mark.asyncio
async def test_the_undo_command_is_returned_before_anything_is_applied(stub_espn):
    """An operator reads the undo on the dry run, not after the write."""
    s = _FakeSession()
    result = await repair.repair(s, apply=False, sport="baseball_mlb", limit=1)

    assert result["undo"] == repair.UNDO_COMMAND
    assert "restore_7147_event_final_scores.py --apply" in result["undo"]
    # Gotcha #48: a non-detached heroku run returns empty stdout that reads as
    # success, so the command we hand an operator is the detached one.
    assert "run:detached" in result["undo"]
