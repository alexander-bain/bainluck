"""D51 — the drain is reversible in PRACTICE, not just in the docstring.

Alex's D51 lets a lane apply a data repair without him watching *provided* it
backs up first and ships a one-command restore. This rail already said it was
reversible:

    "Reversible: every prior value is in the plan artifact
     repair:authority_id_collisions:apply_plan."

Every word of that was true of a single apply in isolation and false of the
sequence the operator note actually recommends — `PLAN_IDENTITY` is ONE slot,
so planning MLB overwrites the record that could have taken MLS back, and
`PLAN_MAX_AGE_S` retires it after a day anyway. That is the CERT-843 shape
again (a docstring asserting a property the code does not have), so what is
pinned here is the property, not the prose:

  * nothing is unstamped until this apply's OWN dated record is on disk;
  * a record that could not be written REFUSES the apply, rather than being
    noted and stepped over;
  * a `superseded` durable write is a FAILURE for an undo even though it is a
    success for a plan — a record that is not yours is not a backup;
  * the ids actually go back, and the restore declines a row that has been
    re-anchored since.

Every guard here carries BOTH arms. A "nothing was written" assertion alone
passes for a rail that never writes at all.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone

from app.tasks import repair_authority_id_collisions as rail


class _Result:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return list(self._rows)

    def first(self):
        return self._rows[0] if self._rows else None


class _FakeSession:
    """Answers each statement from a scripted queue, and records the writes."""

    def __init__(self, script):
        self._script = list(script)
        self.executed = []
        self.commits = 0

    async def execute(self, statement, params=None):
        self.executed.append((str(statement), params))
        return _Result(self._script.pop(0) if self._script else [])

    async def commit(self):
        self.commits += 1


CENSUS_BEFORE = [(164, 352)]
CENSUS_AFTER = [(163, 350)]

PLAN_ROWS = [
    {
        "event_id": 11,
        "contested_espn_id": "401856667",
        "verdict": "AGREES_TWIN",
        "sport": "americanfootball_ncaaf",
        "matchup": "Texas v Ohio State",
    },
    {
        "event_id": 22,
        "contested_espn_id": "401856668",
        "verdict": "AGREES_TWIN",
        "sport": "americanfootball_ncaaf",
        "matchup": "Towson v Maryland",
    },
]


def _plan_reader(rows=None, plan_hash="abc123def456"):
    async def _read():
        return {
            "plan_hash": plan_hash,
            "sport": "americanfootball_ncaaf",
            "rows": list(PLAN_ROWS if rows is None else rows),
        }, "ok"

    return _read


def _unstamps(session):
    """Only the writes that clear an id — the census SELECTs are not writes."""
    return [
        (sql, params) for sql, params in session.executed if "SET espn_id = NULL" in sql
    ]


def _restamps(session):
    return [
        (sql, params)
        for sql, params in session.executed
        if "SET espn_id = :prior" in sql
    ]


# ---------------------------------------------------------------------------
# 1. The backup is a PRECONDITION of the write, not a side effect of it.
# ---------------------------------------------------------------------------


class TestNothingIsUnstampedWithoutAnUndoRecord:
    def test_an_undo_that_cannot_be_persisted_refuses_the_whole_apply(
        self, monkeypatch
    ):
        """The arm that matters: a failed backup writes NOTHING.

        Not "writes the rows and logs a warning" — an unstamp that cannot be
        taken back is not a repair this rail performs unattended.
        """
        monkeypatch.setattr(rail, "_read_plan", _plan_reader())

        async def _fails(identity, payload):
            return False, "undo persist rejected: error"

        monkeypatch.setattr(rail, "_save_undo", _fails)
        session = _FakeSession([CENSUS_BEFORE])
        out = asyncio.run(rail.repair(session, apply=True, plan_hash="abc123def456"))

        assert out["refused"] is True
        assert out["reason_codes"] == [rail.REASON_UNDO_UNWRITTEN]
        assert out["unstamped"] == 0
        assert _unstamps(session) == [], "an apply wrote with no undo record on disk"
        assert session.commits == 0

    def test_CONTROL_the_same_plan_DOES_unstamp_once_the_undo_persists(
        self, monkeypatch
    ):
        """Without this arm the refusal test above passes for a broken rail.

        A rail whose apply had been accidentally reduced to a no-op would
        satisfy "wrote nothing" perfectly.
        """
        monkeypatch.setattr(rail, "_read_plan", _plan_reader())

        async def _ok(identity, payload):
            return True, "ok"

        monkeypatch.setattr(rail, "_save_undo", _ok)
        session = _FakeSession([CENSUS_BEFORE, [(11,)], [(22,)], CENSUS_AFTER])
        out = asyncio.run(rail.repair(session, apply=True, plan_hash="abc123def456"))

        assert out.get("refused") is not True
        assert out["unstamped"] == 2
        assert len(_unstamps(session)) == 2
        assert session.commits == 2

    def test_the_undo_is_saved_BEFORE_the_first_unstamp(self, monkeypatch):
        """Ordering IS the guarantee. A backup written after the writes is a
        backup that does not exist for exactly the run that died halfway."""
        monkeypatch.setattr(rail, "_read_plan", _plan_reader())
        order: list[str] = []

        async def _ok(identity, payload):
            order.append("undo-saved")
            return True, "ok"

        monkeypatch.setattr(rail, "_save_undo", _ok)

        class _OrderingSession(_FakeSession):
            async def execute(self, statement, params=None):
                if "SET espn_id = NULL" in str(statement):
                    order.append("unstamp")
                return await super().execute(statement, params)

        session = _OrderingSession([CENSUS_BEFORE, [(11,)], [(22,)], CENSUS_AFTER])
        asyncio.run(rail.repair(session, apply=True, plan_hash="abc123def456"))

        assert order == ["undo-saved", "unstamp", "unstamp"]

    def test_the_record_carries_every_row_the_apply_will_touch_with_its_prior_id(
        self, monkeypatch
    ):
        """A backup missing a row is not a backup; it is a partial one nobody
        can tell apart from a complete one at restore time."""
        monkeypatch.setattr(rail, "_read_plan", _plan_reader())
        captured: dict = {}

        async def _capture(identity, payload):
            captured["identity"] = identity
            captured["payload"] = payload
            return True, "ok"

        monkeypatch.setattr(rail, "_save_undo", _capture)
        session = _FakeSession([CENSUS_BEFORE, [(11,)], [(22,)], CENSUS_AFTER])
        asyncio.run(rail.repair(session, apply=True, plan_hash="abc123def456"))

        saved = {r["event_id"]: r["prior_espn_id"] for r in captured["payload"]["rows"]}
        assert saved == {11: "401856667", 22: "401856668"}
        assert captured["payload"]["plan_hash"] == "abc123def456"


# ---------------------------------------------------------------------------
# 2. `superseded` means opposite things for a plan and for an undo.
# ---------------------------------------------------------------------------


class TestSupersededIsNotASuccessfulBackup:
    """`_save_plan` treats `superseded` as success and is right to: a newer
    good plan is on disk, so the durability contract holds. For an undo the
    same status means the row at that identity holds SOMEBODY ELSE'S content —
    accepting it hands an operator a restore command that puts back the wrong
    rows. This is the exact place the two rails must disagree."""

    def _publish(self, monkeypatch, status):
        import app.services.durable_snapshots as ds

        async def _fake(envelope):
            return {"status": status, "identity": envelope.identity}

        monkeypatch.setattr(ds, "publish_snapshot_standalone", _fake)

    def test_superseded_is_reported_as_a_failed_backup(self, monkeypatch):
        self._publish(monkeypatch, "superseded")
        ok, note = asyncio.run(rail._save_undo("repair:x:undo:1", {"rows": []}))
        assert ok is False
        assert "SUPERSEDED" in note

    def test_CONTROL_ok_is_a_successful_backup(self, monkeypatch):
        self._publish(monkeypatch, "ok")
        ok, note = asyncio.run(rail._save_undo("repair:x:undo:1", {"rows": []}))
        assert ok is True

    def test_a_raise_is_a_failed_backup_and_is_never_swallowed(self, monkeypatch):
        import app.services.durable_snapshots as ds

        async def _boom(envelope):
            raise RuntimeError("database is gone")

        monkeypatch.setattr(ds, "publish_snapshot_standalone", _boom)
        ok, note = asyncio.run(rail._save_undo("repair:x:undo:1", {"rows": []}))
        assert ok is False
        assert "RuntimeError" in note

    def test_the_undo_outlives_the_plan_by_design(self):
        """If the undo ever inherits the plan's 24h life, the backup silently
        stops existing on the timescale a repair is actually questioned."""
        assert rail.UNDO_MAX_AGE_S > rail.PLAN_MAX_AGE_S * 30


# ---------------------------------------------------------------------------
# 3. One apply, one identity — never the rotating slot the old note named.
# ---------------------------------------------------------------------------


class TestTheUndoIdentityIsDatedAndDistinct:
    def test_two_applies_do_not_share_a_record(self):
        a = rail.undo_identity_for(
            "hash1", at=datetime(2026, 9, 3, 16, 0, 0, tzinfo=timezone.utc)
        )
        b = rail.undo_identity_for(
            "hash2", at=datetime(2026, 9, 3, 16, 30, 0, tzinfo=timezone.utc)
        )
        assert a != b

    def test_the_identity_is_never_the_single_rotating_plan_slot(self):
        ident = rail.undo_identity_for("h", at=datetime.now(timezone.utc))
        assert ident != rail.PLAN_IDENTITY
        assert ident.startswith(rail.UNDO_IDENTITY_PREFIX)

    def test_the_restore_script_looks_for_the_prefix_the_rail_writes(self):
        """--list greps `durable_state_snapshots` by prefix. A rename on one
        side alone leaves every record on file invisible to the restore tool."""
        import re
        from pathlib import Path

        src = (
            Path(rail.__file__).resolve().parents[2]
            / "scripts"
            / "restore_authority_id_collisions.py"
        )
        text = src.read_text()
        found = re.search(r'^UNDO_IDENTITY_PREFIX = "([^"]+)"', text, re.M)
        assert found, "the restore script no longer declares UNDO_IDENTITY_PREFIX"
        assert found.group(1) == rail.UNDO_IDENTITY_PREFIX


# ---------------------------------------------------------------------------
# 4. The response tells the truth about reversibility, and says how.
# ---------------------------------------------------------------------------


class TestTheApplyNoteNamesTheRealUndo:
    def _run(self, monkeypatch):
        monkeypatch.setattr(rail, "_read_plan", _plan_reader())

        async def _ok(identity, payload):
            return True, "ok"

        monkeypatch.setattr(rail, "_save_undo", _ok)
        session = _FakeSession([CENSUS_BEFORE, [(11,)], [(22,)], CENSUS_AFTER])
        return asyncio.run(rail.repair(session, apply=True, plan_hash="abc123def456"))

    def test_it_no_longer_claims_the_rotating_plan_slot_is_the_backup(
        self, monkeypatch
    ):
        """The regression this whole file exists for."""
        out = self._run(monkeypatch)
        assert rail.PLAN_IDENTITY not in out["note"]

    def test_it_names_this_applys_own_record_and_a_runnable_restore(self, monkeypatch):
        out = self._run(monkeypatch)
        assert out["undo_identity"].startswith(rail.UNDO_IDENTITY_PREFIX)
        assert out["undo_identity"] in out["note"]
        assert out["undo_identity"] in out["undo_command"]
        assert "restore_authority_id_collisions.py" in out["undo_command"]


# ---------------------------------------------------------------------------
# 5. The ids actually go back — and do not trample a fresher truth.
# ---------------------------------------------------------------------------


def _undo_reader(rows, plan_hash="abc123def456"):
    async def _read(identity):
        return {
            "plan_hash": plan_hash,
            "taken_at": "2026-09-03T16:00:00+00:00",
            "rows": list(rows),
        }, "ok"

    return _read


UNDO_ROWS = [
    {"event_id": 11, "prior_espn_id": "401856667", "matchup": "Texas v Ohio State"},
    {"event_id": 22, "prior_espn_id": "401856668", "matchup": "Towson v Maryland"},
]


class TestTheRestorePutsTheExactIdsBack:
    def test_it_restamps_each_row_with_its_recorded_prior_value(self, monkeypatch):
        monkeypatch.setattr(rail, "_read_undo", _undo_reader(UNDO_ROWS))
        session = _FakeSession([CENSUS_AFTER, [(11,)], [(22,)], CENSUS_BEFORE])
        out = asyncio.run(
            rail.repair(session, apply=True, undo_identity="repair:x:undo:1")
        )

        assert out["restamped"] == 2
        written = {p["event_id"]: p["prior"] for _, p in _restamps(session)}
        assert written == {11: "401856667", 22: "401856668"}

    def test_a_row_re_anchored_since_the_apply_is_left_alone_and_NAMED(
        self, monkeypatch
    ):
        """The compare is in the write: only a row this repair left blank may
        be restamped. Putting yesterday's id over a current one would make the
        undo cause the corruption it exists to reverse."""
        monkeypatch.setattr(rail, "_read_undo", _undo_reader(UNDO_ROWS))
        # Row 11 no longer NULL -> the UPDATE matches nothing.
        session = _FakeSession([CENSUS_AFTER, [], [(22,)], CENSUS_BEFORE])
        out = asyncio.run(
            rail.repair(session, apply=True, undo_identity="repair:x:undo:1")
        )

        assert out["restamped"] == 1
        assert [r["event_id"] for r in out["reoccupied"]] == [11]
        assert out["reoccupied"][0]["reason_code"] == "ESPN_ID_REOCCUPIED"

    def test_the_restore_only_touches_rows_that_are_currently_blank(self, monkeypatch):
        monkeypatch.setattr(rail, "_read_undo", _undo_reader(UNDO_ROWS))
        session = _FakeSession([CENSUS_AFTER, [(11,)], [(22,)], CENSUS_BEFORE])
        asyncio.run(rail.repair(session, apply=True, undo_identity="repair:x:undo:1"))
        for sql, _ in _restamps(session):
            assert "espn_id IS NULL" in sql

    def test_an_undo_is_a_DRY_RUN_unless_apply_is_passed(self, monkeypatch):
        monkeypatch.setattr(rail, "_read_undo", _undo_reader(UNDO_ROWS))
        session = _FakeSession([CENSUS_AFTER])
        out = asyncio.run(rail.repair(session, undo_identity="repair:x:undo:1"))

        assert out["apply"] is False
        assert out["rows_in_record"] == 2
        assert _restamps(session) == []
        assert session.commits == 0

    def test_a_missing_record_refuses_rather_than_restoring_nothing_quietly(
        self, monkeypatch
    ):
        """gotcha #53: "it returned" is not "it worked". A restore against an
        identity that names nothing must not read as a clean zero-row undo."""

        async def _missing(identity):
            return None, rail.REASON_UNDO_MISSING

        monkeypatch.setattr(rail, "_read_undo", _missing)
        session = _FakeSession([])
        out = asyncio.run(
            rail.repair(session, apply=True, undo_identity="repair:x:undo:nope")
        )

        assert out["refused"] is True
        assert out["reason_codes"] == [rail.REASON_UNDO_MISSING]
        assert _restamps(session) == []

    def test_undo_takes_precedence_over_a_derive(self, monkeypatch):
        """An undo is never also a derive — a rail that fell through to
        `_derive` would ask ESPN 164 times and write a plan nobody asked for."""
        monkeypatch.setattr(rail, "_read_undo", _undo_reader(UNDO_ROWS))

        async def _must_not_run(*a, **k):
            raise AssertionError("undo fell through to the derive")

        monkeypatch.setattr(rail, "_derive", _must_not_run)
        session = _FakeSession([CENSUS_AFTER])
        out = asyncio.run(
            rail.repair(session, undo_identity="repair:x:undo:1", sport="baseball_mlb")
        )
        assert out["undo"] is True


# ---------------------------------------------------------------------------
# 6. The restore is reachable — a rail nobody can invoke is a plan with steps.
# ---------------------------------------------------------------------------


class TestTheUndoIsReachableFromTheAdminRail:
    def test_the_dispatcher_passes_undo_identity_to_repairs_that_declare_it(self):
        import inspect

        from app.routes import admin_repairs

        src = inspect.getsource(admin_repairs.run_repair)
        assert '("undo_identity", undo_identity)' in src, (
            "the dispatcher builds its kwargs from an explicit tuple list; a "
            "param that is not in it is silently dropped"
        )

    def test_the_repair_declares_undo_identity_so_the_passthrough_reaches_it(self):
        import inspect

        assert "undo_identity" in inspect.signature(rail.repair).parameters
