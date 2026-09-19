"""#7147 — repairing `events` does not repair the PAGE, and this is the half that does.

The score repair applied cleanly to both rows in the MLB tail on 2026-09-19 and
changed nothing a reader could see. `events` held ESPN's final (5-6 and 7-3)
while bainluck.com/events/15313231 printed "5 – 5 · FINAL · TIED" and
/events/15313146 printed "7 – 2". Both pages were photographed after the apply.

The cause is a ladder, not a cache. The event page's hero reads

    lastChartPoint?.homeScore ?? event?.home_score          (app/events/[id]/page.tsx)

so the event row is the FALLBACK BENEATH two observation series, and
`computeLastChartPoint` ranks those two by their own clocks. Both games carried
one `score_snapshots` row stamped `2026-09-19 00:15:22.408164+00` — three days
after a 09-16 game — holding the pre-repair score. Newest clock wins, so the
corrected row lost to it and would have kept losing forever.

Those rows are not observations. Nothing watched that game on 09-19; a writer
re-read our own defective `events` row and banked it as a sighting. Hence DELETE
rather than correct: rewriting one to the true final would manufacture a
different lie (somebody saw this score three days late) and would still drag the
Score Differential chart out to a flat line days past the whistle.

Four properties carry this change and each is guarded below:

* **the class survives its sibling's remedy.** A row can hold this defect with a
  perfectly correct score — repairing the event row is what LEAVES it in that
  state. The scan's early exit has to see the class, or the reader-facing half
  is unreachable on exactly the rows the repair just fixed.
* **the time test alone never deletes anything.** The grace bounds eligibility;
  disagreement with a PROVEN ESPN final bounds the remedy. A late-but-correct
  snapshot is untouched however far past full time it lands.
* **a delete with no banked row must not happen** — the same D51(b) gate the
  event-row half runs, on its own counter so a refusal names which bank failed.
* **the undo puts the rows back**, and is a no-op the second time.
"""
import datetime as dt
import importlib.util
import pathlib
import re
from types import SimpleNamespace

import pytest

_SCRIPTS = pathlib.Path(__file__).resolve().parents[1] / "scripts"


def _load(name):
    spec = importlib.util.spec_from_file_location(name, _SCRIPTS / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


repair = _load("repair_event_final_scores")
restore = _load("restore_7147_event_final_scores")


_DATE = dt.date(2026, 9, 16)
_COMMENCE = dt.datetime(2026, 9, 16, 17, 15, tzinfo=dt.timezone.utc)
_FULL_TIME = dt.datetime(2026, 9, 16, 20, 34, tzinfo=dt.timezone.utc)
#: The production specimen's own stamp, three days late.
_POISON_AT = dt.datetime(2026, 9, 19, 0, 15, 22, tzinfo=dt.timezone.utc)


# ---------------------------------------------------------------------------
# the statements
# ---------------------------------------------------------------------------

def test_every_new_statement_parses_as_postgres():
    """A syntax error in a repair is otherwise found by a dyno nobody reads."""
    sqlglot = pytest.importorskip("sqlglot")
    for sql in (
        repair._SNAP_BAK_CREATE_SQL,
        repair._SNAP_BAK_COPY_SQL,
        repair._SNAP_BAK_MISSING_SQL,
        repair._SNAP_DELETE_SQL,
        repair._POST_FINAL_SNAPSHOT_SQL,
        restore._SNAP_PLAN_SQL,
        restore._SNAP_RESTORE_SQL,
    ):
        sqlglot.parse_one(sql, dialect="postgres")


def test_the_delete_is_keyed_on_snapshot_ids_and_nothing_else():
    """The one statement in this change that destroys a row. Its WHERE is an id
    list or it is a table truncation with extra steps — and a second bind would
    mean some OTHER predicate is deciding what disappears."""
    binds = set(re.findall(r":(\w+)", repair._SNAP_DELETE_SQL))
    assert binds == {"snapshot_ids"}
    assert "score_snapshots" in repair._SNAP_DELETE_SQL
    # No date, no score, no event predicate: the loop decides membership and the
    # statement only executes it. A `captured_at >` here would re-derive the
    # grace at write time, where the ESPN comparison that licenses it is absent.
    assert "captured_at" not in repair._SNAP_DELETE_SQL
    assert "home_score" not in repair._SNAP_DELETE_SQL


def test_the_bank_carries_every_column_the_undo_re_inserts():
    """The bank happens before the delete, so it cannot read them back after."""
    for column in ("snapshot_id", "event_id", "captured_at",
                   "home_score", "away_score"):
        assert column in repair._SNAP_BAK_CREATE_SQL
        assert column in repair._SNAP_BAK_COPY_SQL
        assert column in restore._SNAP_PLAN_SQL
        assert column in restore._SNAP_RESTORE_SQL


def test_the_re_insert_keeps_the_original_primary_key():
    """Re-inserting with a fresh id would make a second undo a second copy of
    every snapshot, and would renumber rows the backup still names."""
    assert "b.snapshot_id" in restore._SNAP_RESTORE_SQL
    assert "ON CONFLICT (id) DO NOTHING" in restore._SNAP_RESTORE_SQL


def test_the_re_insert_checks_the_event_still_exists():
    """An event deleted since the repair would abort the INSERT on its foreign
    key, and one unrestorable row must not take the rest of the undo with it."""
    assert "EXISTS (SELECT 1 FROM events e WHERE e.id = b.event_id)" in (
        " ".join(restore._SNAP_RESTORE_SQL.split())
    )


# ---------------------------------------------------------------------------
# the pure gate
# ---------------------------------------------------------------------------

def _snap(home, away, at=_POISON_AT, sid=901):
    return SimpleNamespace(
        id=sid, event_id=15313231, captured_at=at,
        home_score=home, away_score=away,
    )


def test_a_snapshot_contradicting_the_final_is_the_defect():
    assert repair.snapshot_contradicts_final(_snap(5, 5), 5, 6) is True


def test_a_late_snapshot_that_agrees_with_the_final_is_left_alone():
    """The grace decides WHEN a row is eligible; this decides WHETHER it is
    wrong. A duplicate of the truth, however late, is not a defect — and without
    this the remedy would delete the correct final off any game whose last
    snapshot happened to land after the completion stamp."""
    assert repair.snapshot_contradicts_final(_snap(5, 6), 5, 6) is False


def test_an_unknown_espn_final_contradicts_nothing():
    """Mirrors `score_is_stale`'s refusal to grade against an unknown. A `None`
    read as "not equal to 5" would delete a real observation on the strength of
    a number we were never given (gotcha #53)."""
    assert repair.snapshot_contradicts_final(_snap(5, 5), None, 6) is False
    assert repair.snapshot_contradicts_final(_snap(5, 5), 5, None) is False


def test_the_grace_is_measured_in_the_flat_region_of_the_population():
    """Not a round number chosen for comfort. Disagreement runs ~1% for the
    first three hours after full time and 28-92% beyond twelve, so the grace has
    to sit inside the flat region — far enough out to never eat a live game's
    last gasp, far short of the climb this defect lives in."""
    assert 1 <= repair.POST_FINAL_SNAPSHOT_GRACE_MINUTES <= 180


def test_the_candidate_query_applies_the_grace_to_completed_at():
    """The grace is only a floor if it is measured from the completion stamp.
    Measured from `commence_time` it would spare a long game and delete the tail
    of a short one."""
    sql = " ".join(repair._POST_FINAL_SNAPSHOT_SQL.split())
    assert "e.completed_at IS NOT NULL" in sql
    assert "s.captured_at > e.completed_at" in sql
    assert ":grace_minutes" in sql


# ---------------------------------------------------------------------------
# the scan and apply loop, end to end against a fake session
# ---------------------------------------------------------------------------

class _Team:
    def __init__(self, display_name):
        self.display_name = display_name
        self.name = display_name
        self.short_name = display_name


class _Game:
    """ESPN's scoreboard entry: the game ended 5-6."""

    def __init__(self):
        self.espn_id = "401816969"
        self.home_team = _Team("St. Louis Cardinals")
        self.away_team = _Team("San Francisco Giants")
        self.home_score, self.away_score = 5, 6
        self.status = "post"
        self.date = _COMMENCE


class _Candidate:
    """Our row. `home_score` defaults to the ALREADY-REPAIRED 5-6.

    That default is the point of this file: it is the state the score repair
    leaves behind, and the state in which every existing test says there is
    nothing left to do.
    """

    def __init__(self, score=(5, 6)):
        self.event_id = 15313231
        self.espn_id = "401816969"
        self.sport_key = "baseball_mlb"
        self.ev_status = "completed"
        self.home_team_name = "St. Louis Cardinals"
        self.away_team_name = "San Francisco Giants"
        self.home_score, self.away_score = score
        self.commence_time = _COMMENCE
        self.completed_at = _FULL_TIME
        self.game_date = _DATE


class _Group:
    sport_key, game_date, n = "baseball_mlb", _DATE, 1


class _Pop:
    n = 1


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


class _FakeSession:
    """Answers by statement shape and records the order it was asked.

    `snap_bank_succeeds=False` models the one failure the gate exists for: the
    bank INSERT matched nothing, so the reconciliation still finds the rows
    missing and the delete must not run.
    """

    def __init__(self, *, candidate=None, post_final=(), snap_bank_succeeds=True):
        self.candidate = candidate or _Candidate()
        self.post_final = list(post_final)
        self.snap_bank_succeeds = snap_bank_succeeds
        self.calls: list[str] = []
        self.deleted_ids: list = []
        self.commits = 0

    async def execute(self, stmt, params=None, *_a, **_kw):
        sql = " ".join(str(stmt).split())
        # The snapshot statements are matched FIRST: their table name carries
        # the `bak_7147` prefix, so every event-row pattern below also matches
        # them (the trap the sibling suite's session documents).
        if "bak_7147_post_final" in sql:
            if sql.upper().startswith("CREATE TABLE"):
                self.calls.append("snap_bak_create")
                return _Result()
            if sql.upper().startswith("INSERT"):
                self.calls.append("snap_bank")
                return _Result(rowcount=1 if self.snap_bank_succeeds else 0)
            self.calls.append("snap_reconcile")
            return _Result(scalar=0 if self.snap_bank_succeeds else len(self.post_final))
        if sql.startswith("DELETE FROM score_snapshots"):
            self.calls.append("snap_delete")
            self.deleted_ids.extend(params["snapshot_ids"])
            return _Result(rowcount=len(params["snapshot_ids"]))
        if "FROM score_snapshots s" in sql and "JOIN events e" in sql:
            self.calls.append("snap_scan")
            return _Result(rows=list(self.post_final))

        if "CREATE TABLE IF NOT EXISTS" in sql:
            return _Result()
        if sql.startswith(f"ALTER TABLE {repair.BAK_TABLE}"):
            return _Result()
        if sql.startswith(f"UPDATE {repair.BAK_TABLE}"):
            self.calls.append("stamp")
            return _Result(rowcount=1)
        if sql.startswith(f"INSERT INTO {repair.BAK_TABLE}"):
            self.calls.append("bank")
            return _Result(rowcount=1)
        if "to_regclass" in sql:
            return _Result(scalar=True)
        if f"NOT EXISTS (SELECT 1 FROM {repair.BAK_TABLE}" in sql:
            self.calls.append("reconcile")
            return _Result(scalar=0)
        if "UPDATE events SET home_score" in sql:
            self.calls.append("fix_score")
            return _Result(rowcount=1)
        if "UPDATE events SET completed_at" in sql:
            self.calls.append("fix_completed_at")
            return _Result(rowcount=1)
        if "GROUP BY 1, 2" in sql:
            return _Result(rows=[_Group()])
        if sql.startswith("SELECT e.id AS event_id"):
            return _Result(rows=[self.candidate])
        if sql.startswith("SELECT COUNT(*) AS n"):
            return _Result(one=_Pop())
        return _Result(rows=[], scalar=None)

    async def commit(self):
        self.commits += 1
        self.calls.append("commit")


class _FakeESPN:
    async def get_scoreboard(self, sport_key, yyyymmdd):
        return [_Game()]


@pytest.fixture
def stub_espn(monkeypatch):
    import app.services.espn_api as espn_api

    monkeypatch.setattr(espn_api, "get_espn_service", _FakeESPN)


@pytest.mark.asyncio
async def test_a_poisoned_snapshot_is_found_on_a_row_whose_score_is_correct(stub_espn):
    """THE REGRESSION THIS FILE EXISTS FOR.

    The candidate holds 5-6 — exactly what the score repair wrote. Every
    pre-existing test agrees there is nothing to do, and that agreement is what
    let a repaired row keep printing 5-5. The scan has to reach this row anyway.
    """
    s = _FakeSession(post_final=[_snap(5, 5)])
    res = await repair.repair(s, apply=False, sport="baseball_mlb", limit=1)

    assert res["score_defects"] == 0, "the score was already repaired"
    assert res["post_final_snapshot_defects"] == 1
    entry = res["ledger"][0]
    assert entry["action"] == "drop_post_final_snapshots"
    assert entry["snapshot_defect_class"] == repair.POST_FINAL_SNAPSHOT
    assert entry["post_final_snapshots"][0]["score"] == "5-5"
    assert entry["espn_final"] == "5-6"


@pytest.mark.asyncio
async def test_a_dry_run_deletes_nothing_and_banks_nothing(stub_espn):
    """`apply=false` is the documented first call. It must not create the table
    (runtime DDL on a read-only-intent call) and must not touch a snapshot."""
    s = _FakeSession(post_final=[_snap(5, 5)])
    res = await repair.repair(s, apply=False, sport="baseball_mlb", limit=1)

    assert "snap_delete" not in s.calls
    assert "snap_bank" not in s.calls
    assert "snap_bak_create" not in s.calls
    assert res["post_final_snapshot_defects"] == 1
    assert res["post_final_snapshots_dropped"] == 0


@pytest.mark.asyncio
async def test_the_bank_lands_before_the_delete_it_covers(stub_espn):
    """The ordering IS the guarantee — the same argument as the event-row half.
    Both statements are in one transaction, so a bank after the delete would
    still commit together; a bank never reached at all would not."""
    s = _FakeSession(post_final=[_snap(5, 5)])
    res = await repair.repair(s, apply=True, sport="baseball_mlb", limit=1)

    assert res["post_final_snapshots_dropped"] == 1
    assert res["snapshot_backup_refused"] == 0
    assert s.deleted_ids == [901]
    assert s.calls.index("snap_bank") < s.calls.index("snap_delete")
    assert s.calls.index("snap_reconcile") < s.calls.index("snap_delete")
    # And inside the group's transaction, so the commit that removes a snapshot
    # lands its undo with it.
    tape = s.calls[s.calls.index("snap_bank"):]
    assert tape.index("snap_delete") < tape.index("commit")


@pytest.mark.asyncio
async def test_snapshots_that_could_not_be_banked_are_never_deleted(stub_espn):
    """The D51(b) gate, doing the only job it has, on the destructive half."""
    s = _FakeSession(post_final=[_snap(5, 5)], snap_bank_succeeds=False)
    res = await repair.repair(s, apply=True, sport="baseball_mlb", limit=1)

    assert "snap_delete" not in s.calls
    assert s.deleted_ids == []
    assert res["post_final_snapshots_dropped"] == 0
    assert res["snapshot_backup_refused"] == 1
    # Still REPORTED — a refused delete must not read as a clean slate.
    assert res["post_final_snapshot_defects"] == 1
    assert res["ledger"][0]["snapshot_action"] == "skip_backup_not_banked"


@pytest.mark.asyncio
async def test_a_late_snapshot_holding_the_true_final_is_not_touched(stub_espn):
    """Past the grace, so the time test alone would delete it. It carries 5-6 —
    the final itself — and a remedy that removed it would be destroying the
    correct answer for being late."""
    s = _FakeSession(post_final=[_snap(5, 6)])
    res = await repair.repair(s, apply=True, sport="baseball_mlb", limit=1)

    assert res["post_final_snapshot_defects"] == 0
    assert res["post_final_snapshots_dropped"] == 0
    assert "snap_delete" not in s.calls
    # ...and the row raises no ledger entry at all: with a correct score and no
    # snapshot defect there is nothing to report.
    assert res["ledger"] == []


@pytest.mark.asyncio
async def test_a_snapshot_only_row_never_reaches_the_event_row_bank(stub_espn):
    """A bank records "what this row held before we repaired it". On a row this
    pass does not write, that entry licenses an undo of something that never
    happened — and its manifest would be stamped off an untouched row."""
    s = _FakeSession(post_final=[_snap(5, 5)])
    await repair.repair(s, apply=True, sport="baseball_mlb", limit=1)

    assert "snap_delete" in s.calls, "the snapshot half must still have run"
    assert "bank" not in s.calls
    assert "stamp" not in s.calls
    assert "fix_score" not in s.calls


@pytest.mark.asyncio
async def test_both_halves_run_on_a_row_that_carries_both_defects(stub_espn):
    """The ordinary case the day this ships: the score is still 5-5 AND a
    poisoned snapshot sits on top of it. Fixing one and not the other leaves the
    page exactly as wrong as it was."""
    s = _FakeSession(candidate=_Candidate(score=(5, 5)), post_final=[_snap(5, 5)])
    res = await repair.repair(s, apply=True, sport="baseball_mlb", limit=1)

    assert res["scores_repaired"] == 1
    assert res["post_final_snapshots_dropped"] == 1
    assert "fix_score" in s.calls and "snap_delete" in s.calls
    # One ledger entry carrying both, not two rows for one game.
    assert len(res["ledger"]) == 1
    assert res["ledger"][0]["action"] == "fix_score"
    assert res["ledger"][0]["snapshot_defect_class"] == repair.POST_FINAL_SNAPSHOT


@pytest.mark.asyncio
async def test_a_clean_row_is_still_left_entirely_alone(stub_espn):
    """Without this, a mutant that reports every scanned row passes every
    assertion above."""
    s = _FakeSession(post_final=[])
    res = await repair.repair(s, apply=True, sport="baseball_mlb", limit=1)

    assert res["ledger"] == []
    assert res["post_final_snapshot_defects"] == 0
    assert s.deleted_ids == []
    assert "bank" not in s.calls


# ---------------------------------------------------------------------------
# the undo
# ---------------------------------------------------------------------------

def _plan_row(*, already_present=False, event_exists=True, sid=901):
    return SimpleNamespace(
        snapshot_id=sid, event_id=15313231, captured_at=_POISON_AT,
        home_score=5, away_score=5, espn_final="5-6",
        already_present=already_present, event_exists=event_exists,
    )


class _RestoreSession:
    def __init__(self, *, rowcount=1):
        self.rowcount = rowcount
        self.inserted: list = []
        self.commits = 0

    async def execute(self, stmt, params=None, *_a, **_kw):
        self.inserted.append(params["snapshot_id"])
        return _Result(rowcount=self.rowcount)

    async def commit(self):
        self.commits += 1


@pytest.mark.asyncio
async def test_the_undo_re_inserts_a_deleted_snapshot():
    s = _RestoreSession()
    restored, skipped = await restore.restore_snapshots(s, [_plan_row()])

    assert (restored, skipped) == (1, [])
    assert s.inserted == [901]
    # One commit per row: `events` and its children are write-hot, and a batched
    # restore rolls the whole thing back on the first contended row (#3780).
    assert s.commits == 1


@pytest.mark.asyncio
async def test_the_undo_is_a_no_op_the_second_time():
    """A row already back in place is skipped before the statement runs, so a
    twice-run undo cannot double the score series."""
    s = _RestoreSession()
    restored, skipped = await restore.restore_snapshots(
        s, [_plan_row(already_present=True)]
    )

    assert (restored, skipped) == (0, [901])
    assert s.inserted == []


@pytest.mark.asyncio
async def test_the_undo_skips_a_snapshot_whose_event_is_gone():
    """The foreign key would abort the INSERT, and one unrestorable row must not
    take the rest of the restore down with it."""
    s = _RestoreSession()
    restored, skipped = await restore.restore_snapshots(
        s, [_plan_row(event_exists=False)]
    )

    assert (restored, skipped) == (0, [901])
    assert s.inserted == []


@pytest.mark.asyncio
async def test_a_re_insert_that_wrote_nothing_is_reported_as_skipped():
    """The CAS lost to a concurrent insert on the same id between plan and
    write. Not an error — but a restore that silently changed nothing must not
    read as a clean run."""
    s = _RestoreSession(rowcount=0)
    restored, skipped = await restore.restore_snapshots(s, [_plan_row()])

    assert (restored, skipped) == (0, [901])
    assert s.inserted == [901], "it did attempt the write"
