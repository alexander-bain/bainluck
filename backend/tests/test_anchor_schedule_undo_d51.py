"""D51 — the schedule repair is reversible in PRACTICE, not in the docstring.

Alex's D51 lets a lane apply a data repair without him watching *provided* it
backs up first and ships a one-command restore. Until 2026-09-03 this rail had
neither, which is the only reason the two known Week-1 NFL moves sat unapplied
while the fixtures they fix were on the site: the drain next door had grown an
undo, and this rail — a different rail, `_apply_move` rather than the unstamp —
had none. What is pinned here is the property, not the prose:

  * nothing is moved until this apply's OWN dated record is on disk;
  * a record that could not be written REFUSES the apply, rather than being
    noted and stepped over;
  * a `superseded` durable write is a FAILURE for an undo even though it is a
    success for a plan — a record that is not yours is not a backup;
  * the record receipts what was MOVED, never what was planned (CERT-846, next
    door: a record built from the plan offers to reverse moves that never
    happened);
  * the clocks actually go back, and the restore declines a row that something
    else has moved since.

**The compare this rail's restore can make is stronger than the drain's, and
several guards below are about exactly that.** The drain writes NULL — a value
every writer produces identically — so its undo can only ask "is this row still
blank?". This rail writes a specific timestamp, so its restore asks "does this
row still wear the clock WE wrote?", and that question has a real answer.

Every guard here carries BOTH arms. A "nothing was written" assertion alone
passes for a rail that never writes at all.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from app.tasks import reconcile_anchor_schedule as rail
from app.utils.anchor_schedule import AnchoredRow
from app.utils.authority_id_collisions import AuthorityRecord

UTC = timezone.utc
#: The real Week-1 defect, measured on production 2026-09-03: our row says the
#: Chargers host the 49ers on Sep 11, ESPN's own record for that anchor says
#: Dec 18. Two such rows are why Week 1 shows 18 NFL fixtures where there are 16.
OURS = datetime(2026, 9, 11, 0, 35, tzinfo=UTC)
THEIRS = datetime(2026, 12, 18, 1, 15, tzinfo=UTC)
EVENT_ID = 14780595
ESPN_ID = "401873124"


def _row(event_id=EVENT_ID, espn_id=ESPN_ID, commence_time=OURS, **overrides):
    base = dict(
        event_id=event_id,
        sport_key="americanfootball_nfl",
        home_team_name="Los Angeles Chargers",
        away_team_name="San Francisco 49ers",
        espn_id=espn_id,
        commence_time=commence_time,
        status="scheduled",
        completed_at=None,
        commence_time_source="espn",
    )
    base.update(overrides)
    return AnchoredRow(**base)


def _record(starts_at=THEIRS, authority_id=ESPN_ID):
    return AuthorityRecord(
        authority_id=authority_id,
        home_names=frozenset({"los angeles chargers"}),
        away_names=frozenset({"san francisco 49ers"}),
        starts_at=starts_at,
        label="Los Angeles Chargers v San Francisco 49ers",
    )


class _Result:
    def __init__(self, rowcount):
        self.rowcount = rowcount


class _Session:
    def __init__(self, rowcount=1):
        self.statements = []
        self.commits = 0
        self._rowcount = rowcount

    async def execute(self, statement):
        self.statements.append(statement)
        return _Result(self._rowcount)

    async def commit(self):
        self.commits += 1


def _writes(session):
    return [str(s) for s in session.statements if "UPDATE events" in str(s)]


@pytest.fixture
def wired(monkeypatch):
    """Stub the two edges — the database read and the authority — and the record."""

    def _wire(rows, records, rowcount=1, save=None):
        async def _load_rows(session, **kwargs):
            return list(rows)

        async def _count_eligible(session, **kwargs):
            return len(rows)

        async def _fetch_record(service, sport_keys, authority_id):
            return records.get(authority_id)

        monkeypatch.setattr(rail, "_load_rows", _load_rows)
        monkeypatch.setattr(rail, "_count_eligible", _count_eligible)
        monkeypatch.setattr(
            "app.tasks.repair_authority_id_collisions._fetch_record", _fetch_record
        )
        monkeypatch.setattr("app.services.espn_api.get_espn_service", lambda: object())
        if save is not None:
            monkeypatch.setattr(rail, "_save_undo", save)
        return _Session(rowcount=rowcount)

    return _wire


def _capturing_save(calls):
    async def _save(identity, payload):
        # Copied, not aliased: the rail passes lists it goes on appending to,
        # and a shared reference would make every recorded call look like the
        # last one.
        calls.append({
            "identity": identity,
            "rows": [dict(r) for r in payload["rows"]],
            "rows_planned": [dict(r) for r in payload.get("rows_planned", [])],
            "receipt_complete": payload.get("receipt_complete"),
        })
        return True, "ok"

    return _save


# ---------------------------------------------------------------------------
# 1. The backup is a PRECONDITION of the write, not a side effect of it.
# ---------------------------------------------------------------------------


class TestNothingIsMovedWithoutARecord:
    async def test_a_record_that_cannot_be_persisted_refuses_the_whole_apply(
        self, wired
    ):
        """The arm that matters: a failed backup writes NOTHING.

        Not "moves the clocks and logs a warning" — a 98-day schedule move that
        cannot be taken back is not a repair this rail performs unattended.
        """

        async def _fails(identity, payload):
            return False, "undo persist rejected: error"

        session = wired([_row()], {ESPN_ID: _record()}, save=_fails)
        result = await rail.reconcile(session, apply=True)

        assert result["terminal"] == "refused"
        assert result["reason_codes"] == [rail.REASON_UNDO_UNWRITTEN]
        assert result["moved"] == 0
        assert _writes(session) == [], "an apply moved a clock with no record on disk"
        assert session.commits == 0

    async def test_CONTROL_the_same_row_IS_moved_once_the_record_persists(self, wired):
        """Without this arm the refusal test above passes for a broken rail.

        A rail whose apply had been reduced to a no-op would satisfy "wrote
        nothing" perfectly.
        """
        calls: list[dict] = []
        session = wired([_row()], {ESPN_ID: _record()}, save=_capturing_save(calls))
        result = await rail.reconcile(session, apply=True)

        assert result["terminal"] == "complete"
        assert result["moved"] == 1
        assert len(_writes(session)) == 1
        assert session.commits == 1

    async def test_the_record_is_saved_BEFORE_the_first_move(self, wired):
        """Ordering IS the guarantee. A backup written after the writes is a
        backup that does not exist for exactly the run that died halfway."""
        order: list[str] = []

        async def _save(identity, payload):
            order.append("record-saved")
            return True, "ok"

        class _OrderingSession(_Session):
            async def execute(self, statement):
                if "UPDATE events" in str(statement):
                    order.append("move")
                return await super().execute(statement)

        wired([_row()], {ESPN_ID: _record()}, save=_save)
        await rail.reconcile(_OrderingSession(), apply=True)

        assert order[:2] == ["record-saved", "move"]

    async def test_a_dry_run_writes_no_record_because_it_writes_nothing(self, wired):
        """A plan that leaves an undo record behind is noise an operator has to
        sift, and a `--list` full of records for runs that never wrote."""
        calls: list[dict] = []
        session = wired([_row()], {ESPN_ID: _record()}, save=_capturing_save(calls))
        result = await rail.reconcile(session, apply=False)

        assert result["terminal"] == "plan_only"
        assert calls == []
        assert "undo_identity" not in result

    async def test_an_apply_with_nothing_to_move_writes_no_record(self, wired):
        """Both arms of the same rule: no write, no record."""
        calls: list[dict] = []
        session = wired(
            [_row()], {ESPN_ID: _record(starts_at=OURS)}, save=_capturing_save(calls)
        )
        result = await rail.reconcile(session, apply=True)

        assert result["terminal"] == "no_work"
        assert calls == []
        assert session.commits == 0


# ---------------------------------------------------------------------------
# 2. The record receipts what MOVED, never what was planned. (CERT-846's rule,
#    learned on the sibling drain and applied here before it could bite.)
# ---------------------------------------------------------------------------


class TestTheRecordReceiptsWhatMoved:
    async def test_the_pre_write_record_claims_nothing_and_names_the_intent(
        self, wired
    ):
        calls: list[dict] = []
        session = wired([_row()], {ESPN_ID: _record()}, save=_capturing_save(calls))
        await rail.reconcile(session, apply=True)

        first = calls[0]
        assert first["rows"] == [], "the pre-write record claimed a move it had not made"
        assert [r["event_id"] for r in first["rows_planned"]] == [EVENT_ID]
        assert first["receipt_complete"] is False

    async def test_a_STALE_row_never_enters_the_receipt(self, wired):
        """The regression, in this rail's own currency.

        `rowcount` 0 means the compare in the write matched nothing: the row's
        anchor or clock changed since the read, so this apply did not move it.
        A record naming it would offer to "restore" a clock this rail never
        wrote.
        """
        calls: list[dict] = []
        session = wired(
            [_row()], {ESPN_ID: _record()}, rowcount=0, save=_capturing_save(calls)
        )
        result = await rail.reconcile(session, apply=True)

        assert result["moved"] == 0 and result["stale"] == 1
        assert result["rows_receipted"] == 0
        assert calls[-1]["rows"] == [], "a row the apply never moved entered the receipt"
        assert len(calls[-1]["rows_planned"]) == 1, "the intent must still be recorded"

    async def test_CONTROL_a_row_that_DID_move_is_in_the_receipt(self, wired):
        """Without this arm the guard above passes for a receipt that is always
        empty."""
        calls: list[dict] = []
        session = wired(
            [_row()], {ESPN_ID: _record()}, rowcount=1, save=_capturing_save(calls)
        )
        result = await rail.reconcile(session, apply=True)

        assert result["moved"] == 1
        assert result["rows_receipted"] == 1
        assert [r["event_id"] for r in calls[-1]["rows"]] == [EVENT_ID]
        assert calls[-1]["receipt_complete"] is True

    async def test_the_record_carries_the_prior_AND_written_value_of_every_column(
        self, wired
    ):
        """`before` is what a restore puts back; `after` is what makes its
        compare exact. A column moved with no `before` is a column with no way
        back, and this rail writes two of them."""
        calls: list[dict] = []
        session = wired([_row()], {ESPN_ID: _record()}, save=_capturing_save(calls))
        await rail.reconcile(session, apply=True)

        row = calls[-1]["rows"][0]
        assert row["before"] == {
            "commence_time": OURS.isoformat(),
            "commence_time_source": "espn",
        }
        assert row["after"] == {
            "commence_time": THEIRS.isoformat(),
            "commence_time_source": "espn",
        }
        assert row["espn_id"] == ESPN_ID

    async def test_every_column_the_write_touches_has_a_before(self, wired):
        """Pinned structurally, not by listing today's two columns.

        A third column added to the decision's `write` must arrive with its own
        prior value, or the restore silently stops being complete.
        """
        calls: list[dict] = []
        session = wired([_row()], {ESPN_ID: _record()}, save=_capturing_save(calls))
        await rail.reconcile(session, apply=True)

        row = calls[-1]["rows"][0]
        assert set(row["before"]) == set(row["after"]), (
            "a column is written with no recorded prior value — it cannot be "
            "restored"
        )

    async def test_the_commit_happens_before_the_receipt_is_sealed(self, wired):
        """The receipt is a statement about DURABLE rows.

        Sealing before the commit would let the record claim moves the database
        could still discard — the same class of lie as receipting the plan, and
        it points the wrong way: over-claiming, not under-claiming.
        """
        order: list[str] = []

        async def _save(identity, payload):
            order.append(f"save:{len(payload['rows'])}")
            return True, "ok"

        class _OrderingSession(_Session):
            async def commit(self):
                order.append("commit")
                return await super().commit()

        wired([_row()], {ESPN_ID: _record()}, save=_save)
        await rail.reconcile(_OrderingSession(), apply=True)

        assert order == ["save:0", "commit", "save:1"]

    async def test_a_mixed_page_receipts_only_the_row_it_moved(self, wired):
        """What a real slice looks like. Two movers, the session reports one
        rowcount for both, so this pins the SHAPE: planned is 2, and whatever
        lands is what the receipt says."""
        calls: list[dict] = []
        rows = [_row(), _row(event_id=99, espn_id="401873004")]
        session = wired(
            rows,
            {ESPN_ID: _record(), "401873004": _record(authority_id="401873004")},
            rowcount=0,
            save=_capturing_save(calls),
        )
        result = await rail.reconcile(session, apply=True)

        assert result["stale"] == 2
        assert {r["event_id"] for r in calls[-1]["rows_planned"]} == {EVENT_ID, 99}
        assert calls[-1]["rows"] == []


# ---------------------------------------------------------------------------
# 3. `superseded` means opposite things for a plan and for an undo.
# ---------------------------------------------------------------------------


class TestSupersededIsNotASuccessfulBackup:
    def _publish(self, monkeypatch, status):
        async def _publish_standalone(envelope):
            return {"status": status}

        monkeypatch.setattr(
            "app.services.durable_snapshots.publish_snapshot_standalone",
            _publish_standalone,
        )

    async def test_superseded_is_reported_as_a_failed_backup(self, monkeypatch):
        self._publish(monkeypatch, "superseded")
        ok, note = await rail._save_undo("repair:anchor_schedule:undo:x", {"rows": []})

        assert ok is False
        assert "SUPERSEDED" in note

    async def test_CONTROL_ok_is_a_successful_backup(self, monkeypatch):
        self._publish(monkeypatch, "ok")
        ok, note = await rail._save_undo("repair:anchor_schedule:undo:x", {"rows": []})

        assert (ok, note) == (True, "ok")

    async def test_a_raise_is_a_failed_backup_and_is_never_swallowed(self, monkeypatch):
        async def _boom(envelope):
            raise RuntimeError("durable store is down")

        monkeypatch.setattr(
            "app.services.durable_snapshots.publish_snapshot_standalone", _boom
        )
        ok, note = await rail._save_undo("repair:anchor_schedule:undo:x", {"rows": []})

        assert ok is False
        assert "RuntimeError" in note

    def test_the_record_outlives_a_days_worth_of_plans(self):
        """An undo going stale is the loss of the only proof a repair can be
        taken back, which is the opposite of a plan going stale."""
        assert rail.UNDO_MAX_AGE_S >= 365 * 86400


# ---------------------------------------------------------------------------
# 4. One apply, one identity.
# ---------------------------------------------------------------------------


class TestTheIdentityIsDatedAndDistinct:
    def test_two_applies_of_different_moves_do_not_share_a_record(self):
        at = datetime(2026, 9, 3, 16, 0, tzinfo=UTC)
        a = rail.undo_identity_for([{"event_id": 1, "after": {"c": "x"}}], at=at)
        b = rail.undo_identity_for([{"event_id": 2, "after": {"c": "x"}}], at=at)

        assert a != b, "two different applies in the same second shared one record"

    def test_the_same_second_and_different_clocks_do_not_share_a_record(self):
        at = datetime(2026, 9, 3, 16, 0, tzinfo=UTC)
        a = rail.undo_identity_for([{"event_id": 1, "after": {"c": "x"}}], at=at)
        b = rail.undo_identity_for([{"event_id": 1, "after": {"c": "y"}}], at=at)

        assert a != b

    def test_the_identity_carries_the_prefix_the_restore_script_looks_for(self):
        import pathlib

        at = datetime(2026, 9, 3, 16, 0, tzinfo=UTC)
        identity = rail.undo_identity_for([{"event_id": 1, "after": {}}], at=at)
        assert identity.startswith(rail.UNDO_IDENTITY_PREFIX)

        # A rename on one side and not the other orphans `--list` silently.
        script = pathlib.Path(__file__).resolve().parents[1] / (
            "scripts/restore_anchor_schedule_moves.py"
        )
        assert (
            f'UNDO_IDENTITY_PREFIX = "{rail.UNDO_IDENTITY_PREFIX}"'
            in script.read_text()
        )

    def test_it_is_not_the_sibling_rails_prefix(self):
        """Two rails sharing an identity prefix would list each other's records
        and offer the wrong restore command for them."""
        from app.tasks import repair_authority_id_collisions as drain

        assert rail.UNDO_IDENTITY_PREFIX != drain.UNDO_IDENTITY_PREFIX


# ---------------------------------------------------------------------------
# 5. The response tells the truth about reversibility, and says how.
# ---------------------------------------------------------------------------


class TestTheResponseNamesARunnableRestore:
    async def test_it_names_this_applys_own_record_and_a_runnable_command(self, wired):
        calls: list[dict] = []
        session = wired([_row()], {ESPN_ID: _record()}, save=_capturing_save(calls))
        result = await rail.reconcile(session, apply=True)

        assert result["undo_identity"].startswith(rail.UNDO_IDENTITY_PREFIX)
        assert result["undo_identity"] in result["undo_command"]
        assert "restore_anchor_schedule_moves.py" in result["undo_command"]
        assert "--apply" in result["undo_command"]

    async def test_the_restore_script_it_names_exists(self):
        import pathlib

        named = "scripts/restore_anchor_schedule_moves.py"
        assert (pathlib.Path(__file__).resolve().parents[1] / named).exists(), (
            "the apply prints a restore command for a script that is not shipped"
        )


# ---------------------------------------------------------------------------
# 6. The clocks actually go back — and do not trample a fresher truth.
# ---------------------------------------------------------------------------


RECORD_ROW = {
    "event_id": EVENT_ID,
    "espn_id": ESPN_ID,
    "sport": "americanfootball_nfl",
    "matchup": "Los Angeles Chargers v San Francisco 49ers",
    "before": {"commence_time": OURS.isoformat(), "commence_time_source": "espn"},
    "after": {"commence_time": THEIRS.isoformat(), "commence_time_source": "espn"},
}


def _reader(rows, planned=None, complete=True):
    async def _read(identity):
        return {
            "taken_at": "2026-09-03T16:00:00+00:00",
            "rows": list(rows),
            "rows_planned": list(rows if planned is None else planned),
            "receipt_complete": complete,
        }, "ok"

    return _read


class TestTheRestorePutsTheClocksBack:
    async def test_it_reverts_the_row_to_its_recorded_prior_value(self, monkeypatch):
        monkeypatch.setattr(rail, "_read_undo", _reader([RECORD_ROW]))
        session = _Session(rowcount=1)
        result = await rail.restore(session, "repair:anchor_schedule:undo:x", apply=True)

        assert result["reverted"] == 1
        assert result["terminal"] == "complete"
        assert len(_writes(session)) == 1
        assert session.commits == 1

    async def test_a_row_moved_since_the_apply_is_left_alone_and_NAMED(
        self, monkeypatch
    ):
        """The compare is in the write, and here it names the value THIS RAIL
        wrote. A row something else has moved since does not match, and dragging
        it back would make the undo cause the corruption it exists to reverse."""
        monkeypatch.setattr(rail, "_read_undo", _reader([RECORD_ROW]))
        session = _Session(rowcount=0)
        result = await rail.restore(session, "repair:anchor_schedule:undo:x", apply=True)

        assert result["reverted"] == 0
        assert result["terminal"] == "partial"
        assert [r["event_id"] for r in result["moved_on"]] == [EVENT_ID]
        assert result["moved_on"][0]["reason_code"] == "CLOCK_MOVED_ON"

    async def test_the_restore_compares_on_the_value_the_apply_WROTE(self, monkeypatch):
        """The property that makes this rail's undo safer than the drain's.

        The WHERE must re-state the written clock, not merely the event id — an
        undo keyed on the id alone would overwrite whatever the row wears now.
        """
        monkeypatch.setattr(rail, "_read_undo", _reader([RECORD_ROW]))
        session = _Session(rowcount=1)
        await rail.restore(session, "repair:anchor_schedule:undo:x", apply=True)

        compiled = str(
            session.statements[0].compile(compile_kwargs={"literal_binds": True})
        )
        # Split the halves. Asserting the written clock appears *somewhere* is
        # vacuous — both timestamps are in 2026, and the prior value is in the
        # SET clause of every restore — so the assertion has to be about WHICH
        # half each one is in. (Found by mutation: deleting the whole `after`
        # compare left a loose "is 2026 in the statement" check green.)
        setter, _, where = compiled.partition(" WHERE ")
        assert "2026-12-18" in where, (
            "the restore's WHERE does not name the clock the apply WROTE, so it "
            "would drag back a row that something else has moved since"
        )
        assert "events.espn_id = '401873124'" in where
        assert "2026-09-11" in setter, "the restore is not putting the prior clock back"
        assert "2026-09-11" not in where, (
            "the WHERE compares on the PRIOR clock, which no row wears after the "
            "apply — this restore would match nothing, ever"
        )

    async def test_the_compare_covers_EVERY_column_the_apply_wrote(self, monkeypatch):
        """Not just the clock. A column restored without being compared is a
        column this rail would overwrite blind."""
        monkeypatch.setattr(rail, "_read_undo", _reader([RECORD_ROW]))
        session = _Session(rowcount=1)
        await rail.restore(session, "repair:anchor_schedule:undo:x", apply=True)

        _, _, where = str(
            session.statements[0].compile(compile_kwargs={"literal_binds": True})
        ).partition(" WHERE ")
        for column in RECORD_ROW["after"]:
            assert f"events.{column} =" in where, (
                f"{column} is written by the restore but not compared, so a row "
                f"whose {column} changed since the apply is overwritten blind"
            )

    async def test_a_restore_is_a_DRY_RUN_unless_apply_is_passed(self, monkeypatch):
        monkeypatch.setattr(rail, "_read_undo", _reader([RECORD_ROW]))
        session = _Session()
        result = await rail.restore(session, "repair:anchor_schedule:undo:x")

        assert result["applied"] is False
        assert result["rows_in_record"] == 1
        assert _writes(session) == [], "a dry run wrote to the database"
        assert session.commits == 0

    async def test_a_missing_record_refuses_rather_than_reverting_nothing_quietly(
        self, monkeypatch
    ):
        """"Restored 0 of 0" and "there is no record" must not read alike."""

        async def _missing(identity):
            return None, rail.REASON_UNDO_MISSING

        monkeypatch.setattr(rail, "_read_undo", _missing)
        session = _Session()
        result = await rail.restore(session, "nope", apply=True)

        assert result["terminal"] == "refused"
        assert result["reason_codes"] == [rail.REASON_UNDO_MISSING]
        assert _writes(session) == []

    async def test_it_replays_the_RECEIPT_and_never_the_plan(self, monkeypatch):
        """CERT-846's rule, guarded on this rail directly.

        The record's plan names two rows; only one was moved. The restore must
        write once.
        """
        other = {**RECORD_ROW, "event_id": 99, "espn_id": "401873004"}
        monkeypatch.setattr(
            rail, "_read_undo", _reader([RECORD_ROW], planned=[RECORD_ROW, other])
        )
        session = _Session(rowcount=1)
        result = await rail.restore(session, "repair:anchor_schedule:undo:x", apply=True)

        assert result["rows_in_record"] == 1
        assert result["rows_planned_in_record"] == 2
        assert len(_writes(session)) == 1, "the restore replayed a move that never landed"

    async def test_the_operator_line_of_a_restore_is_about_the_restore(
        self, monkeypatch
    ):
        """The reconcile wording would print `moved=0 stale=0` over a run that
        had just put a clock back — every number in it false, and `moved=0`
        false in the direction that reads as "nothing happened"."""
        monkeypatch.setattr(rail, "_read_undo", _reader([RECORD_ROW]))
        session = _Session(rowcount=1)
        result = await rail.restore(session, "repair:anchor_schedule:undo:x", apply=True)
        line = rail.summarize_for_operator(result)

        assert "reverted=1/1" in line
        assert "moved=0" not in line


# ---------------------------------------------------------------------------
# 7. The restore is reachable — a rail nobody can invoke is a plan with steps.
# ---------------------------------------------------------------------------


class TestTheRestoreIsReachableFromTheAdminRail:
    def test_the_endpoint_declares_undo_identity_and_routes_it_to_restore(self):
        import inspect

        from app.routes import admin_events

        src = inspect.getsource(admin_events.reconcile_anchor_schedule_endpoint)
        assert "undo_identity" in src
        assert "await restore(db, undo_identity, apply=apply)" in src

    def test_the_restore_is_routed_BEFORE_the_reconcile_arguments(self):
        """An undo is never also a derive. If the reconcile call came first a
        restore would sweep the window and ask ESPN about it."""
        import inspect

        from app.routes import admin_events

        src = inspect.getsource(admin_events.reconcile_anchor_schedule_endpoint)
        assert src.index("await restore(") < src.index("await reconcile(")

    def test_an_applied_restore_is_gated_on_the_destructive_check(self):
        """It writes. The read token alone must not be enough."""
        import inspect

        from app.routes import admin_events

        src = inspect.getsource(admin_events.reconcile_anchor_schedule_endpoint)
        assert "_check_admin_destructive(request=request)" in src
        assert src.index("_check_admin_destructive") < src.index("await restore(")
