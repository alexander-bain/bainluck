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
import json
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
        self.rollbacks = 0

    async def execute(self, statement, params=None):
        self.executed.append((str(statement), params))
        return _Result(self._script.pop(0) if self._script else [])

    async def commit(self):
        self.commits += 1

    async def rollback(self):
        self.rollbacks += 1


def _wire_saves(monkeypatch, save):
    """Patch BOTH persistence seams from one fake, and make them behave.

    Since CERT-851 each row's receipt is staged inside the SAME transaction as
    its unstamp, so the apply no longer reaches the standalone writer per row —
    only for the pre-write record and the final seal. Patching one seam and not
    the other would leave the real co-commit talking to a fake session. The
    adapter mirrors the real helper, rollback included: that rollback is what
    takes the unstamp back out.
    """
    monkeypatch.setattr(rail, "_save_undo", save)

    async def _co_commit(session, identity, payload):
        ok, note = await save(identity, payload)
        if ok:
            await session.commit()
        else:
            await session.rollback()
        return ok, note

    monkeypatch.setattr(rail, "_save_undo_co_commit", _co_commit)


#: Every payload the rail hands its writers carries the owner token, so every
#: guard that calls one directly has to as well — a payload without it is
#: refused before the store is reached, which would make these tests pass for
#: the wrong reason.
OWNED = {"rows": [], rail.UNDO_OWNER_KEY: "inv0"}

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

        _wire_saves(monkeypatch, _fails)
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

        _wire_saves(monkeypatch, _ok)
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

        _wire_saves(monkeypatch, _ok)

        class _OrderingSession(_FakeSession):
            async def execute(self, statement, params=None):
                if "SET espn_id = NULL" in str(statement):
                    order.append("unstamp")
                return await super().execute(statement, params)

        session = _OrderingSession([CENSUS_BEFORE, [(11,)], [(22,)], CENSUS_AFTER])
        asyncio.run(rail.repair(session, apply=True, plan_hash="abc123def456"))

        # The receipt (CERT-846) means the record is now saved repeatedly — once
        # before the loop and once per cleared row — so the assertion is on the
        # PREFIX, which is the property: the record existed before any write.
        # Moving the pre-loop save below the loop makes this start with
        # "unstamp" and reddens.
        assert order[:2] == ["undo-saved", "unstamp"]
        assert order.count("unstamp") == 2

    def test_the_record_carries_every_row_the_apply_will_touch_with_its_prior_id(
        self, monkeypatch
    ):
        """The PLANNED list is complete from the first write.

        A backup missing a row is not a backup. What changed at CERT-846 is
        which key answers which question: `rows_planned` is the full intent and
        is written before the first unstamp, while `rows` is the receipt and
        starts empty because at that instant nothing has been cleared.
        """
        monkeypatch.setattr(rail, "_read_plan", _plan_reader())
        calls: list[dict] = []

        async def _capture(identity, payload):
            calls.append({"identity": identity, "payload": payload})
            return True, "ok"

        _wire_saves(monkeypatch, _capture)
        session = _FakeSession([CENSUS_BEFORE, [(11,)], [(22,)], CENSUS_AFTER])
        asyncio.run(rail.repair(session, apply=True, plan_hash="abc123def456"))

        first = calls[0]["payload"]
        planned = {r["event_id"]: r["prior_espn_id"] for r in first["rows_planned"]}
        assert planned == {11: "401856667", 22: "401856668"}
        assert first["rows"] == [], "the pre-write record claimed rows it had not cleared"
        assert first["receipt_complete"] is False
        assert first["plan_hash"] == "abc123def456"

        # And by the end the receipt has caught up with reality.
        last = calls[-1]["payload"]
        assert {r["event_id"] for r in last["rows"]} == {11, 22}
        assert last["receipt_complete"] is True


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

        async def _fake(envelope, *, owner_key, owner):
            return {"status": status, "identity": envelope.identity}

        monkeypatch.setattr(ds, "publish_owned_snapshot_standalone", _fake)

    def test_superseded_is_reported_as_a_failed_backup(self, monkeypatch):
        self._publish(monkeypatch, "superseded")
        ok, note = asyncio.run(rail._save_undo("repair:x:undo:1", OWNED))
        assert ok is False
        assert "SUPERSEDED" in note

    def test_occupied_is_reported_as_a_failed_backup(self, monkeypatch):
        """CERT-856. The identity holds another invocation's receipt, which the
        store refused to overwrite — so this apply has no record and must not
        proceed. Named apart from `superseded`: that one means a newer copy of
        the same thing, this one means a record about somebody else's run."""
        self._publish(monkeypatch, "occupied")
        ok, note = asyncio.run(rail._save_undo("repair:x:undo:1", OWNED))
        assert ok is False
        assert "OCCUPIED" in note

    def test_a_payload_with_no_owner_is_refused_before_the_store(self, monkeypatch):
        """An unowned record is one the store cannot protect. Writing it anyway
        would restore the CERT-856 defect for that record alone, silently."""
        import app.services.durable_snapshots as ds

        reached: list[object] = []

        async def _fake(envelope, *, owner_key, owner):
            reached.append(envelope)
            return {"status": "ok", "identity": envelope.identity}

        monkeypatch.setattr(ds, "publish_owned_snapshot_standalone", _fake)
        ok, note = asyncio.run(rail._save_undo("repair:x:undo:1", {"rows": []}))

        assert ok is False
        assert rail.UNDO_OWNER_KEY in note
        assert reached == [], "an unowned record reached the durable store"

    def test_CONTROL_ok_is_a_successful_backup(self, monkeypatch):
        self._publish(monkeypatch, "ok")
        ok, note = asyncio.run(rail._save_undo("repair:x:undo:1", OWNED))
        assert ok is True

    def test_the_owner_it_passes_the_store_is_the_records_own_token(
        self, monkeypatch
    ):
        """The store's refusal keys off this argument. A constant here would
        leave every record owned by the same 'writer' and protect nothing."""
        import app.services.durable_snapshots as ds

        seen: list[tuple] = []

        async def _fake(envelope, *, owner_key, owner):
            seen.append((owner_key, owner))
            return {"status": "ok", "identity": envelope.identity}

        monkeypatch.setattr(ds, "publish_owned_snapshot_standalone", _fake)
        asyncio.run(
            rail._save_undo(
                "repair:x:undo:1", {"rows": [], rail.UNDO_OWNER_KEY: "abc123"}
            )
        )

        assert seen == [(rail.UNDO_OWNER_KEY, "abc123")]

    def test_a_raise_is_a_failed_backup_and_is_never_swallowed(self, monkeypatch):
        import app.services.durable_snapshots as ds

        async def _boom(envelope, *, owner_key, owner):
            raise RuntimeError("database is gone")

        monkeypatch.setattr(ds, "publish_owned_snapshot_standalone", _boom)
        ok, note = asyncio.run(rail._save_undo("repair:x:undo:1", OWNED))
        assert ok is False
        assert "RuntimeError" in note

    def test_the_undo_outlives_the_plan_by_design(self):
        """If the undo ever inherits the plan's 24h life, the backup silently
        stops existing on the timescale a repair is actually questioned."""
        assert rail.UNDO_MAX_AGE_S > rail.PLAN_MAX_AGE_S * 30


class TestTheCoCommitHelperItself:
    """CERT-851. The apply-level guards patch this seam, so it needs its own.

    A guard that only ever sees a stubbed co-commit proves the RAIL reacts
    correctly to a reported failure — not that the helper reports one, and not
    that it takes the data write back out when it does. Those are the properties
    the atomicity claim actually rests on, so they are pinned here directly
    against the real function.
    """

    def _stage(self, monkeypatch, status):
        import app.services.durable_snapshots as ds

        async def _fake(db, envelope, *, owner_key, owner):
            return {"status": status, "identity": envelope.identity}

        monkeypatch.setattr(ds, "publish_owned_snapshot_in_txn", _fake)

    def test_ok_commits_exactly_once_and_never_rolls_back(self, monkeypatch):
        self._stage(monkeypatch, "ok")
        session = _FakeSession([])
        ok, note = asyncio.run(
            rail._save_undo_co_commit(session, "repair:x:undo:1", OWNED)
        )

        assert (ok, note) == (True, "ok")
        assert (session.commits, session.rollbacks) == (1, 0)

    def test_superseded_rolls_the_write_back_and_does_NOT_commit(self, monkeypatch):
        """A record that is not ours is not a backup — and here it must also
        cost the write it was supposed to be a backup OF."""
        self._stage(monkeypatch, "superseded")
        session = _FakeSession([])
        ok, note = asyncio.run(
            rail._save_undo_co_commit(session, "repair:x:undo:1", OWNED)
        )

        assert ok is False
        assert "SUPERSEDED" in note
        assert session.commits == 0, "an unreceipted write was committed"
        assert session.rollbacks == 1

    def test_occupied_rolls_the_write_back_and_does_NOT_commit(self, monkeypatch):
        """CERT-856. The store declined to overwrite another invocation's
        receipt, so this row has no record of its own — and a row cleared
        without a record is precisely what D51 forbids."""
        self._stage(monkeypatch, "occupied")
        session = _FakeSession([])
        ok, note = asyncio.run(
            rail._save_undo_co_commit(session, "repair:x:undo:1", OWNED)
        )

        assert ok is False
        assert "OCCUPIED" in note
        assert session.commits == 0, "an unreceipted write was committed"
        assert session.rollbacks == 1

    def test_an_unowned_record_is_refused_and_rolls_the_write_back(self, monkeypatch):
        import app.services.durable_snapshots as ds

        reached: list[object] = []

        async def _fake(db, envelope, *, owner_key, owner):
            reached.append(envelope)
            return {"status": "ok", "identity": envelope.identity}

        monkeypatch.setattr(ds, "publish_owned_snapshot_in_txn", _fake)
        session = _FakeSession([])
        ok, note = asyncio.run(
            rail._save_undo_co_commit(session, "repair:x:undo:1", {"rows": []})
        )

        assert ok is False
        assert rail.UNDO_OWNER_KEY in note
        assert reached == [], "an unowned record reached the durable store"
        assert (session.commits, session.rollbacks) == (0, 1)

    def test_an_error_status_rolls_the_write_back_and_does_NOT_commit(
        self, monkeypatch
    ):
        self._stage(monkeypatch, "error")
        session = _FakeSession([])
        ok, note = asyncio.run(
            rail._save_undo_co_commit(session, "repair:x:undo:1", OWNED)
        )

        assert ok is False
        assert session.commits == 0, "an unreceipted write was committed"
        assert session.rollbacks == 1

    def test_a_raise_rolls_back_and_is_never_swallowed(self, monkeypatch):
        import app.services.durable_snapshots as ds

        async def _boom(db, envelope, *, owner_key, owner):
            raise RuntimeError("database is gone")

        monkeypatch.setattr(ds, "publish_owned_snapshot_in_txn", _boom)
        session = _FakeSession([])
        ok, note = asyncio.run(
            rail._save_undo_co_commit(session, "repair:x:undo:1", OWNED)
        )

        assert ok is False
        assert "RuntimeError" in note
        assert session.commits == 0
        assert session.rollbacks == 1

    def test_the_receipt_is_staged_on_the_SAME_session_it_commits(self, monkeypatch):
        """The one fact that makes this atomic rather than merely sequential.

        Staging on any other session would still return ``ok`` and still commit,
        and every assertion above would pass while the two writes sat in
        different transactions — which is the defect, restored.
        """
        import app.services.durable_snapshots as ds

        seen: list[object] = []

        async def _fake(db, envelope, *, owner_key, owner):
            seen.append(db)
            return {"status": "ok", "identity": envelope.identity}

        monkeypatch.setattr(ds, "publish_owned_snapshot_in_txn", _fake)
        session = _FakeSession([])
        asyncio.run(rail._save_undo_co_commit(session, "repair:x:undo:1", OWNED))

        assert seen == [session], "the receipt was staged on a different session"


# ---------------------------------------------------------------------------
# 3. One apply, one identity — never the rotating slot the old note named.
# ---------------------------------------------------------------------------


class TestTheUndoIdentityIsDatedAndDistinct:
    def test_two_applies_do_not_share_a_record(self):
        a = rail.undo_identity_for(
            "hash1", at=datetime(2026, 9, 3, 16, 0, 0, tzinfo=timezone.utc),
            invocation="inv",
        )
        b = rail.undo_identity_for(
            "hash2", at=datetime(2026, 9, 3, 16, 30, 0, tzinfo=timezone.utc),
            invocation="inv",
        )
        assert a != b

    def test_THE_REGRESSION_the_same_plan_at_the_same_instant_does_not_share_one(self):
        """CERT-856, at the identity. The clock and the plan hash are exactly
        the two things a concurrent apply holds an identical copy of, so an
        identity made of them alone is ONE identity in both runs — and the run
        that cleared nothing wrote its empty receipt over the run that had.
        """
        at = datetime(2026, 9, 3, 16, 0, 0, 500_000, tzinfo=timezone.utc)

        a = rail.undo_identity_for("h", at=at, invocation=rail.new_undo_invocation())
        b = rail.undo_identity_for("h", at=at, invocation=rail.new_undo_invocation())

        assert a != b, "two concurrent applies would write to one record"

    def test_the_token_is_never_derived_from_the_work(self):
        """A "nonce" computed from the plan is not a nonce. Sixteen draws with
        every input held fixed must be sixteen different tokens."""
        assert len({rail.new_undo_invocation() for _ in range(16)}) == 16

    def test_the_identity_fits_the_column_it_is_stored_in(self):
        """`durable_state_snapshots.identity` is varchar(120), and this rail's
        prefix is the longer of the two. An overflow raises at the INSERT — when
        a repair is trying to back itself up, the worst moment to find out."""
        ident = rail.undo_identity_for(
            "0123456789abcdef" * 4,
            at=datetime.now(timezone.utc),
            invocation=rail.new_undo_invocation(),
        )
        assert len(ident) <= 120, ident

    def test_the_identity_is_never_the_single_rotating_plan_slot(self):
        ident = rail.undo_identity_for(
            "h", at=datetime.now(timezone.utc), invocation="inv"
        )
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

        _wire_saves(monkeypatch, _ok)
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


# ---------------------------------------------------------------------------
# 7. CERT-846 — the record receipts what was CLEARED, not what was PLANNED.
#
# The BLOCK's reproduction, verbatim: a moved row made the apply return
# `unstamped=0`, and that same apply's undo then returned `restamped=1`. The
# undo had put an espn_id back onto a row the apply never touched — so a stale
# or no-op apply could reverse ANOTHER writer's clear and re-create the very
# collision this rail exists to remove.
#
# Both arms on every guard. "The receipt is empty" passes for a rail that
# receipts nothing at all, so each test that pins an exclusion is paired with
# one proving the included row still goes back.
# ---------------------------------------------------------------------------


def _capturing_save(calls):
    async def _save(identity, payload):
        # Copied, not aliased: the rail mutates its receipt list in place
        # between saves, and a shared reference would make every recorded call
        # look like the last one.
        calls.append({
            "identity": identity,
            "rows": [dict(r) for r in payload["rows"]],
            "rows_planned": [dict(r) for r in payload.get("rows_planned", [])],
            "receipt_complete": payload.get("receipt_complete"),
        })
        return True, "ok"

    return _save


class TestAMovedRowIsNeverInTheReceipt:
    def test_THE_REGRESSION_an_apply_that_cleared_nothing_restores_nothing(
        self, monkeypatch
    ):
        """CERT-846's exact reproduction, end to end and in one test.

        Plan one row; its id has moved, so the unstamp matches nothing and the
        apply reports `unstamped=0`. Feed that apply's OWN record straight into
        the undo, with the row now blank (another writer cleared it). Before the
        fix the undo restamped it. It must now restamp nothing.
        """
        monkeypatch.setattr(rail, "_read_plan", _plan_reader(rows=[PLAN_ROWS[0]]))
        calls: list[dict] = []
        _wire_saves(monkeypatch, _capturing_save(calls))

        # `[]` from the unstamp = rowcount 0 = ESPN_ID_MOVED.
        apply_session = _FakeSession([CENSUS_BEFORE, [], CENSUS_BEFORE])
        applied = asyncio.run(
            rail.repair(apply_session, apply=True, plan_hash="abc123def456")
        )
        assert applied["unstamped"] == 0
        assert [m["reason_code"] for m in applied["moved"]] == ["ESPN_ID_MOVED"]
        assert applied["rows_receipted"] == 0

        # The record this apply actually left behind — not a hand-built one.
        record = calls[-1]
        assert record["rows"] == [], "a row the apply never cleared entered the receipt"
        assert len(record["rows_planned"]) == 1, "the intent must still be recorded"

        async def _read(identity):
            return {"plan_hash": "abc123def456", "taken_at": "t", **record}, "ok"

        monkeypatch.setattr(rail, "_read_undo", _read)
        # The row IS blank now, so a restamp WOULD succeed if one were attempted
        # — the only thing that made the old bug bite. The script holds the two
        # censuses and no unstamp answer: an attempted restamp would take a
        # census tuple and fail loudly rather than pass quietly.
        undo_session = _FakeSession([CENSUS_BEFORE, CENSUS_BEFORE])
        out = asyncio.run(
            rail.repair(undo_session, apply=True, undo_identity=record["identity"])
        )

        assert out["restamped"] == 0
        assert _restamps(undo_session) == [], (
            "the undo wrote an espn_id onto a row its apply never unstamped — "
            "CERT-846 exactly"
        )

    def test_CONTROL_the_row_that_WAS_cleared_still_goes_back(self, monkeypatch):
        """Without this arm the regression above passes for a dead undo.

        Same shape, one difference: the unstamp succeeds. The receipt must then
        carry the row and the undo must put its id back.
        """
        monkeypatch.setattr(rail, "_read_plan", _plan_reader(rows=[PLAN_ROWS[0]]))
        calls: list[dict] = []
        _wire_saves(monkeypatch, _capturing_save(calls))

        apply_session = _FakeSession([CENSUS_BEFORE, [(11,)], CENSUS_AFTER])
        applied = asyncio.run(
            rail.repair(apply_session, apply=True, plan_hash="abc123def456")
        )
        assert applied["unstamped"] == 1
        assert applied["rows_receipted"] == 1

        record = calls[-1]
        assert [r["event_id"] for r in record["rows"]] == [11]

        async def _read(identity):
            return {"plan_hash": "abc123def456", "taken_at": "t", **record}, "ok"

        monkeypatch.setattr(rail, "_read_undo", _read)
        undo_session = _FakeSession([CENSUS_AFTER, [(11,)], CENSUS_BEFORE])
        out = asyncio.run(
            rail.repair(undo_session, apply=True, undo_identity=record["identity"])
        )

        assert out["restamped"] == 1
        assert {p["prior"] for _, p in _restamps(undo_session)} == {"401856667"}

    def test_a_partly_moved_plan_receipts_only_the_rows_it_cleared(self, monkeypatch):
        """The mixed case, which is what a real slice looks like."""
        monkeypatch.setattr(rail, "_read_plan", _plan_reader())
        calls: list[dict] = []
        _wire_saves(monkeypatch, _capturing_save(calls))

        # Row 11 moved, row 22 cleared.
        session = _FakeSession([CENSUS_BEFORE, [], [(22,)], CENSUS_AFTER])
        out = asyncio.run(rail.repair(session, apply=True, plan_hash="abc123def456"))

        assert out["unstamped"] == 1
        assert out["rows_receipted"] == 1
        record = calls[-1]
        assert [r["event_id"] for r in record["rows"]] == [22]
        assert {r["event_id"] for r in record["rows_planned"]} == {11, 22}

    def test_the_receipt_is_written_per_row_not_only_at_the_end(self, monkeypatch):
        """A crash mid-loop must not cost the rows already cleared.

        A record written only after the loop is the CERT-843/846 family again:
        the apply is durable, its reversal is not, and the gap is exactly the
        run that died. Pinned by asserting the receipt GREW while the loop ran.
        """
        monkeypatch.setattr(rail, "_read_plan", _plan_reader())
        calls: list[dict] = []
        _wire_saves(monkeypatch, _capturing_save(calls))

        session = _FakeSession([CENSUS_BEFORE, [(11,)], [(22,)], CENSUS_AFTER])
        asyncio.run(rail.repair(session, apply=True, plan_hash="abc123def456"))

        sizes = [len(c["rows"]) for c in calls]
        assert sizes[0] == 0, "the pre-write record must claim nothing"
        assert 1 in sizes, (
            "no save carried exactly one row — the receipt is written only after "
            "the loop, so a crash mid-drain loses the undo for rows already cleared"
        )
        assert sizes[-1] == 2
        assert sizes == sorted(sizes), "a receipt may only grow"

    def test_a_failed_receipt_ROLLS_BACK_its_own_row_and_STOPS_the_apply(
        self, monkeypatch
    ):
        """CERT-851. Clearing a row you cannot name is the thing D51 forbids.

        This guard used to assert ``unstamped == 1`` — the row was cleared, its
        receipt was lost, and the apply stopped. That is precisely the hole the
        block found: a durable unstamp with an empty record, which the restore
        can never put back. The receipt is now staged in the same transaction as
        the UPDATE, so a receipt that cannot be written takes its own row down
        with it and the count is 0.

        The `first` row is used deliberately: it is the case where the receipt
        has nothing else in it, which is where an empty-list bug hides.
        """
        monkeypatch.setattr(rail, "_read_plan", _plan_reader())
        saves = {"n": 0}

        async def _fail_after_first(identity, payload):
            saves["n"] += 1
            # 1 = the pre-write record, 2 = the first row's receipt.
            return (False, "undo persist rejected: error") if saves["n"] == 2 else (True, "ok")

        _wire_saves(monkeypatch, _fail_after_first)
        # One unstamp answer only: the apply must stop before asking for a
        # second, so a rail that carried on would read a census tuple as an
        # unstamp result and blow up rather than quietly pass.
        session = _FakeSession([CENSUS_BEFORE, [(11,)], CENSUS_AFTER])
        out = asyncio.run(rail.repair(session, apply=True, plan_hash="abc123def456"))

        assert len(_unstamps(session)) == 1, "the apply kept clearing after a lost receipt"
        assert session.commits == 0, "a row was committed without its receipt"
        assert session.rollbacks == 1, "the unreceipted unstamp was not rolled back"
        assert out["unstamped"] == 0, (
            "the response claims a cleared row whose receipt was never written — "
            "the restore cannot put that row back"
        )
        assert out["rows_receipted"] == 0
        assert out["reason_codes"] == [rail.REASON_UNDO_RECEIPT_FAILED]
        assert out["receipt_complete"] is False

    def test_a_receipt_that_fails_LATER_keeps_every_earlier_row_restorable(
        self, monkeypatch
    ):
        """The block's own regression: prove a landed write stays restorable.

        Row one's receipt commits; row two's fails. The first row must remain
        cleared AND named in the durable record — losing it would be the
        opposite over-correction, throwing away good work because a later row
        failed — while row two is rolled back and named by nothing.
        """
        monkeypatch.setattr(rail, "_read_plan", _plan_reader())
        calls: list[dict] = []
        saves = {"n": 0}

        async def _fail_on_the_second_row(identity, payload):
            saves["n"] += 1
            # 1 = pre-write, 2 = row one's receipt, 3 = row two's receipt.
            if saves["n"] == 3:
                return False, "undo persist rejected: error"
            calls.append({"rows": [dict(r) for r in payload["rows"]]})
            return True, "ok"

        _wire_saves(monkeypatch, _fail_on_the_second_row)
        session = _FakeSession([CENSUS_BEFORE, [(11,)], [(22,)], CENSUS_AFTER])
        out = asyncio.run(rail.repair(session, apply=True, plan_hash="abc123def456"))

        assert session.commits == 1, "exactly the one receipted row is durable"
        assert session.rollbacks == 1, "the unreceipted row was not rolled back"
        assert out["unstamped"] == 1
        assert out["rows_receipted"] == 1
        # The surviving durable record still names row one, so the restore has
        # everything it needs to reverse what actually landed.
        assert [r["event_id"] for r in calls[-1]["rows"]] == [11]
        assert out["reason_codes"] == [rail.REASON_UNDO_RECEIPT_FAILED]

    def test_the_response_never_reports_more_cleared_than_it_can_restore(
        self, monkeypatch
    ):
        """The invariant behind both guards above, stated once.

        `unstamped` counting above `rows_receipted` is the exact shape of the
        defect: rows cleared that no record can name. Swept across the failure
        point rather than asserted at one, because the interesting value is
        whichever row the receipt dies on.
        """
        for failing_save in (2, 3, 4):
            monkeypatch.setattr(rail, "_read_plan", _plan_reader())
            saves = {"n": 0}

            async def _fail_at(identity, payload, _target=failing_save):
                saves["n"] += 1
                if saves["n"] == _target:
                    return False, "undo persist rejected: error"
                return True, "ok"

            _wire_saves(monkeypatch, _fail_at)
            # The script must run out exactly when the apply does: save #2 is
            # row one's receipt, so the apply stops after ONE unstamp and a
            # third scripted answer would be read as the closing census.
            unstamp_answers = [[(11,)]] if failing_save == 2 else [[(11,)], [(22,)]]
            session = _FakeSession([CENSUS_BEFORE, *unstamp_answers, CENSUS_AFTER])
            out = asyncio.run(
                rail.repair(session, apply=True, plan_hash="abc123def456")
            )

            assert out["unstamped"] == out["rows_receipted"], (
                f"receipt failing at save #{failing_save} left "
                f"{out['unstamped']} row(s) cleared and "
                f"{out['rows_receipted']} receipted"
            )
            assert out["unstamped"] == session.commits, (
                "a row is durable only if its transaction committed"
            )

    def test_CONTROL_receipts_that_all_succeed_run_the_whole_plan(self, monkeypatch):
        monkeypatch.setattr(rail, "_read_plan", _plan_reader())

        async def _ok(identity, payload):
            return True, "ok"

        _wire_saves(monkeypatch, _ok)
        session = _FakeSession([CENSUS_BEFORE, [(11,)], [(22,)], CENSUS_AFTER])
        out = asyncio.run(rail.repair(session, apply=True, plan_hash="abc123def456"))

        assert len(_unstamps(session)) == 2
        assert out["receipt_complete"] is True
        assert "reason_codes" not in out


class TestAV1RecordCannotBeReadAsAReceipt:
    def test_the_schema_version_was_bumped_so_v1_rows_cannot_be_replayed(self):
        """The version is the mechanism, not a label.

        A v1 record's `rows` key holds PLANNED rows. Read by v2 code it would be
        replayed as a receipt — the original bug, resurrected from storage. The
        read passes `expected_version`, so bumping the version is what makes an
        old record unreadable rather than silently reinterpreted.
        """
        import inspect

        assert rail.UNDO_SCHEMA.endswith("/v2"), (
            "the record's meaning changed; a reader that accepts the old version "
            "will treat a planned row as a cleared one"
        )
        src = inspect.getsource(rail._read_undo)
        assert "expected_version=UNDO_SCHEMA" in src

    def test_the_undo_reports_planned_and_cleared_as_DIFFERENT_numbers(
        self, monkeypatch
    ):
        """An operator must be able to see the gap, or they will read a short
        receipt as data loss and go looking for a way to force the rest back."""

        async def _read(identity):
            return {
                "plan_hash": "abc123def456",
                "taken_at": "t",
                "rows": [UNDO_ROWS[0]],
                "rows_planned": UNDO_ROWS,
                "receipt_complete": True,
            }, "ok"

        monkeypatch.setattr(rail, "_read_undo", _read)
        session = _FakeSession([CENSUS_AFTER])
        out = asyncio.run(rail.repair(session, undo_identity="repair:x:undo:1"))

        assert out["rows_in_record"] == 1
        assert out["rows_planned_in_record"] == 2
        assert "ESPN_ID_MOVED" in out["note"]


# ---------------------------------------------------------------------------
# 8. CERT-856 — two applies in the same instant, and only one receipt survives.
# ---------------------------------------------------------------------------


class _OwnedStore:
    """The durable table's two write predicates, over a dict.

    Emulated rather than stubbed, because the property under test lives in the
    interaction between the rail and the store: a stub that always returns
    ``ok`` proves the rail can write, which is not the question. The predicates
    here are the ones in ``_OWNED_UPSERT_SQL``, and a guard in
    ``test_durable_state_298.py`` pins that SQL against this reading.
    """

    def __init__(self):
        self.rows: dict[str, dict] = {}

    def _write(self, envelope, owner_key, owner):
        if not owner:
            return {"status": "error", "identity": envelope.identity}
        existing = self.rows.get(envelope.identity)
        if existing is not None:
            if existing["payload"].get(owner_key) != owner:
                return {
                    "status": "occupied",
                    "identity": envelope.identity,
                    "owner": existing["payload"].get(owner_key),
                }
            if existing["generation"] > envelope.generation:
                return {"status": "superseded", "identity": envelope.identity}
        self.rows[envelope.identity] = {
            "generation": envelope.generation,
            # Copied: the rail hands over lists it goes on appending to.
            "payload": json.loads(json.dumps(envelope.payload)),
        }
        return {"status": "ok", "identity": envelope.identity}

    def install(self, monkeypatch, module):
        import app.services.durable_snapshots as ds

        async def _standalone(envelope, *, owner_key, owner):
            return self._write(envelope, owner_key, owner)

        async def _in_txn(db, envelope, *, owner_key, owner):
            return self._write(envelope, owner_key, owner)

        monkeypatch.setattr(ds, "publish_owned_snapshot_standalone", _standalone)
        monkeypatch.setattr(ds, "publish_owned_snapshot_in_txn", _in_txn)

        async def _read(identity):
            row = self.rows.get(identity)
            if row is None:
                return None, module.REASON_UNDO_MISSING
            return row["payload"], "ok"

        monkeypatch.setattr(module, "_read_undo", _read)


def _freeze(monkeypatch, module, at):
    """Both applies believe they started at the same instant — the condition
    the identity used to be derived from, and nothing else."""

    class _Frozen(datetime):
        @classmethod
        def now(cls, tz=None):
            return at

    monkeypatch.setattr(module, "datetime", _Frozen)


SAME_INSTANT = datetime(2026, 9, 3, 16, 0, 0, 500_000, tzinfo=timezone.utc)


class TestTwoAppliesInOneInstant:
    """CERT-856, reproduced at the rail and caught by both layers.

    Measured on the blocked sha: run one unstamped row 11 and stored receipt
    ``[11]``; a same-instant run that cleared nothing derived the SAME identity
    and replaced that record with ``rows: []``, ``receipt_complete: true``. The
    unstamp was durable and the restore then put nothing back.

    Two arms, because the repair has two layers and either alone would let a
    regression through:

      * the identity is per-INVOCATION, so the collision does not happen; and
      * the store refuses a replacement from another invocation, so if the
        identity ever did collide the first receipt still survives.

    The second arm forces the collision to prove the second layer is load
    bearing rather than dead code behind a good salt.
    """

    def _run(self, monkeypatch, store, rows):
        monkeypatch.setattr(rail, "_read_plan", _plan_reader())
        session = _FakeSession([CENSUS_BEFORE, *rows, CENSUS_AFTER])
        out = asyncio.run(rail.repair(session, apply=True, plan_hash="abc123def456"))
        return out, session

    def test_THE_REGRESSION_the_second_apply_cannot_erase_the_firsts_receipt(
        self, monkeypatch
    ):
        """Identity collision FORCED — same instant, same plan, same token."""
        store = _OwnedStore()
        store.install(monkeypatch, rail)
        _freeze(monkeypatch, rail, SAME_INSTANT)
        # The COLLISION is forced at the identity, not at the token: each run
        # still draws its own owner, exactly as it will in production, and the
        # two are made to land on one slot anyway. Forcing the token instead
        # would give both runs the same OWNER too, and the store would let the
        # second one through — a test that passes for the defect.
        monkeypatch.setattr(
            rail, "undo_identity_for",
            lambda *a, **k: "repair:authority_id_collisions:undo:collide",
        )

        # Run one clears row 11; row 22 had already moved.
        first, _ = self._run(monkeypatch, store, [[(11,)], []])
        assert first["unstamped"] == 1
        assert first["rows_receipted"] == 1
        identity = first["undo_identity"]
        assert store.rows[identity]["payload"]["rows"][0]["event_id"] == 11

        # Run two, in the same instant, finds nothing left to clear.
        second, session = self._run(monkeypatch, store, [[], []])

        assert second["refused"] is True, "the twin apply was allowed to proceed"
        assert second["reason_codes"] == [rail.REASON_UNDO_UNWRITTEN]
        assert "OCCUPIED" in second["undo_note"]
        assert _unstamps(session) == [], "the refused apply still cleared a row"

        receipt = store.rows[identity]["payload"]
        assert [r["event_id"] for r in receipt["rows"]] == [11], (
            "the second apply replaced the first apply's receipt with its own"
        )
        assert receipt["receipt_complete"] is True

    def test_and_the_surviving_receipt_still_RESTORES(self, monkeypatch):
        """A record that survived and cannot be replayed is not a survivor.

        This is the arm that would have failed on the blocked sha: the row was
        durably unstamped and the restore put nothing back.
        """
        store = _OwnedStore()
        store.install(monkeypatch, rail)
        _freeze(monkeypatch, rail, SAME_INSTANT)
        # The COLLISION is forced at the identity, not at the token: each run
        # still draws its own owner, exactly as it will in production, and the
        # two are made to land on one slot anyway. Forcing the token instead
        # would give both runs the same OWNER too, and the store would let the
        # second one through — a test that passes for the defect.
        monkeypatch.setattr(
            rail, "undo_identity_for",
            lambda *a, **k: "repair:authority_id_collisions:undo:collide",
        )

        first, _ = self._run(monkeypatch, store, [[(11,)], []])
        self._run(monkeypatch, store, [[], []])

        restore = _FakeSession([CENSUS_AFTER, [(11,)], CENSUS_BEFORE])
        out = asyncio.run(
            rail.repair(
                restore, apply=True, undo_identity=first["undo_identity"]
            )
        )

        assert out["restamped"] == 1
        written = {p["event_id"]: p["prior"] for _, p in _restamps(restore)}
        assert written == {11: "401856667"}

    def test_CONTROL_with_real_tokens_the_twin_gets_its_OWN_record(
        self, monkeypatch
    ):
        """The first layer, on its own. Nothing is forced here: the same instant
        and the same plan must still yield two identities and two records, so
        the store's refusal is a backstop and not the everyday path — an apply
        blocked by its own twin would be a new outage, not a fix.
        """
        store = _OwnedStore()
        store.install(monkeypatch, rail)
        _freeze(monkeypatch, rail, SAME_INSTANT)

        first, _ = self._run(monkeypatch, store, [[(11,)], []])
        second, _ = self._run(monkeypatch, store, [[], [(22,)]])

        assert first["undo_identity"] != second["undo_identity"]
        assert first["rows_receipted"] == 1 and second["rows_receipted"] == 1
        assert len(store.rows) == 2
        by_identity = {
            k: [r["event_id"] for r in v["payload"]["rows"]]
            for k, v in store.rows.items()
        }
        assert by_identity[first["undo_identity"]] == [11]
        assert by_identity[second["undo_identity"]] == [22]
