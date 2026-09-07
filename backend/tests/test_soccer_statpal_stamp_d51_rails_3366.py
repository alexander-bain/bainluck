"""The D51 rails for soccer's first StatPal stamp, tested where they can fail.

`scripts/soccer_statpal_stamp_3366.py` is the backup + one-command restore that
D51 requires before the owning lane may make that first write unattended. Every
test here is a class of defect that would make the undo *look* like it worked:

  * an undo whose selection rule has drifted from the writer's key rule, so it
    matches nothing and reports a clean zero (`_assert_namespace`);
  * an undo that clears a column it did not write, turning the restore into the
    corruption it exists to reverse;
  * an undo that undoes ONE half, which is the orphan state `_write_link` writes
    both halves to avoid;
  * an apply that runs with no backup on file, which is the whole of D51.

CERT-2207 IS WHY OWNERSHIP IS NOT INFERRED
══════════════════════════════════════════
The first version derived "ours" from the pre-image: empty at backup, populated
now. `TestARowBornInTheBackupGap` is the counterexample that BLOCK found — the
apply selects candidates live and the backup stays valid for
`BACKUP_MAX_AGE`, so a row created in between gets stamped, and under the
derived rule its column read `outside_backup` (left populated) while its anchor
read deletable. The undo produced the orphan.

So the writer records what it wrote and the undo replays that. The two cases the
BLOCK required are `TestARowBornInTheBackupGap` (fully undone, both halves) and
`TestAForeignWriterIsNeverTouched` (left alone, both halves); the real-Postgres
end-to-end that executes the actual writes is
`tests/integration/test_soccer_statpal_manifest_restore_pg.py`.

The planner is pure on purpose, so the interesting half needs no database and
can be replayed over `db-query` rows before anybody runs it against production.
"""

import importlib.util
import os
from datetime import datetime, timedelta, timezone

import pytest

_SCRIPT = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "scripts",
    "soccer_statpal_stamp_3366.py",
)


def _load():
    spec = importlib.util.spec_from_file_location("soccer_statpal_stamp_3366", _SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


rails = _load()


def _preimage(columns, anchors=()):
    return {
        "window_start": "2026-09-05T00:00:00+00:00",
        "window_end": "2026-09-14T00:00:00+00:00",
        "sport_key_prefix": "soccer%",
        "columns": columns,
        "anchors": list(anchors),
    }


def _entry(event_id, fixture_id, *, column=True, anchor=True):
    """One manifest row, in the shape `StampRun.committed_writes` appends."""
    return {
        "event_id": event_id,
        "fixture_id": fixture_id,
        "anchor_source_id": f"soccer:{fixture_id}",
        "column_written": column,
        "anchor_written": anchor,
    }


def _now(*entries):
    """The DB state produced by applying `entries` and nothing else."""
    columns = {
        str(e["event_id"]): e["fixture_id"] for e in entries if e["column_written"]
    }
    anchors = {
        f"{e['event_id']}|{e['anchor_source_id']}"
        for e in entries
        if e["anchor_written"]
    }
    return columns, anchors


class TestTheUndoSelectsWhatTheWriterWrites:
    """A prefix that has drifted restores nothing and says so cleanly."""

    def test_the_soccer_anchor_namespace_is_what_the_undo_greps_for(self):
        from app.utils.provider_anchor_keys import SOURCE_STATPAL, statpal_id_space

        assert SOURCE_STATPAL == rails.ANCHOR_SOURCE
        assert f"{statpal_id_space('soccer')}:" == rails.ANCHOR_SOURCE_ID_PREFIX

    def test_a_drifted_namespace_refuses_rather_than_matching_nothing(
        self, monkeypatch
    ):
        monkeypatch.setattr(rails, "ANCHOR_SOURCE_ID_PREFIX", "football:")
        with pytest.raises(SystemExit) as exc:
            rails._assert_namespace()
        assert "REFUSED" in str(exc.value)

    def test_the_key_the_writer_uses_is_in_the_space_the_undo_scans(self):
        """The end-to-end shape, not just the two constants agreeing."""
        from app.utils.provider_anchor_keys import statpal_anchor_key, statpal_id_space

        key = statpal_anchor_key("1043639", statpal_id_space("soccer"))
        assert key is not None
        assert key.source == rails.ANCHOR_SOURCE
        assert key.source_id.startswith(rails.ANCHOR_SOURCE_ID_PREFIX)


class TestBothHalvesOfTheWriteComeBack:
    def test_one_apply_yields_a_column_clear_AND_an_anchor_delete(self):
        """The orphan this prevents: an anchor naming an event whose column no
        longer claims the fixture is a correspondence no writer can reach and
        every reader believes."""
        entry = _entry(11, "1043639")
        got = rails.plan_restore([entry], *_now(entry))
        assert got["to_clear"] == [{"event_id": 11, "written": "1043639"}]
        assert got["to_delete"] == [{"event_id": 11, "source_id": "soccer:1043639"}]

    def test_the_anchor_only_path_deletes_an_anchor_and_clears_no_column(self):
        """`_write_anchor_only` never touched the column, so neither does the
        undo — the column was already correct before this pass ran."""
        entry = _entry(11, "1043639", column=False)
        got = rails.plan_restore([entry], *_now(entry))
        assert got["to_clear"] == []
        assert got["to_delete"] == [{"event_id": 11, "source_id": "soccer:1043639"}]

    def test_a_confirmed_anchor_is_left_while_its_column_is_cleared(self):
        """`record_anchor` returned CONFIRMED: the anchor was already on file, so
        this pass wrote only the column. Deleting the anchor would remove a
        correspondence the apply did not create."""
        entry = _entry(11, "1043639", anchor=False)
        columns, _ = _now(entry)
        got = rails.plan_restore([entry], columns, {"11|soccer:1043639"})
        assert got["to_clear"] == [{"event_id": 11, "written": "1043639"}]
        assert got["to_delete"] == []

    def test_the_undo_is_idempotent_against_a_restore_that_already_ran(self):
        entry = _entry(11, "1043639")
        first = rails.plan_restore([entry], *_now(entry))
        assert len(first["to_clear"]) == 1 and len(first["to_delete"]) == 1
        second = rails.plan_restore([entry], {}, set())
        assert second["to_clear"] == []
        assert second["to_delete"] == []
        assert len(second["column_moved_on"]) == 1
        assert len(second["anchor_already_gone"]) == 1


class TestARowBornInTheBackupGap:
    """CERT-2207. The row the pre-image could not have seen.

    `BACKUP_MAX_AGE` lets an apply run up to 45 minutes after its backup, and
    ingestion creates soccer rows the whole time. The apply picks its candidates
    live, so it stamps this row; the backup never recorded it. Deriving
    ownership from the pre-image classified the column `outside_backup` and left
    it populated, while classifying the anchor — equally unseen — deletable.
    """

    def test_a_row_absent_from_the_backup_is_still_fully_undone(self):
        born_after = _entry(12, "777777")
        got = rails.plan_restore([born_after], *_now(born_after))
        assert got["to_clear"] == [{"event_id": 12, "written": "777777"}], (
            "the column the apply wrote was left populated — this is the "
            "CERT-2207 orphan"
        )
        assert got["to_delete"] == [{"event_id": 12, "source_id": "soccer:777777"}]

    def test_neither_half_survives_the_undo(self):
        """Stated as the invariant rather than as two counts: after the restore
        there is no event carrying a column without its anchor, or the reverse."""
        born_after = _entry(12, "777777")
        columns, anchors = _now(born_after)
        got = rails.plan_restore([born_after], columns, anchors)

        cleared = {str(r["event_id"]) for r in got["to_clear"]}
        deleted = {f"{r['event_id']}|{r['source_id']}" for r in got["to_delete"]}
        assert not (set(columns) - cleared), "a column survived the undo"
        assert not (anchors - deleted), "an anchor survived the undo"

    def test_the_backup_is_not_consulted_at_all(self):
        """The signature is the proof: a planner that cannot see the pre-image
        cannot mis-attribute a row on the strength of it."""
        import inspect

        params = set(inspect.signature(rails.plan_restore).parameters)
        assert params == {"manifest", "columns_now", "anchors_now"}


class TestAForeignWriterIsNeverTouched:
    """The sibling case the BLOCK required: someone else populates a row that
    was empty at backup time. Under the old derived rule that row looked exactly
    like ours. Under the manifest it is simply absent, and absence is the whole
    test."""

    def test_a_foreign_column_on_a_backed_up_empty_row_is_left_alone(self):
        ours = _entry(11, "1043639")
        columns, anchors = _now(ours)
        # Event 99 was in the backup, recorded empty, and another writer has
        # since populated it and written its anchor.
        columns["99"] = "555555"
        anchors.add("99|soccer:555555")

        got = rails.plan_restore([ours], columns, anchors)

        assert [r["event_id"] for r in got["to_clear"]] == [11]
        assert [r["event_id"] for r in got["to_delete"]] == [11]

    def test_a_foreign_anchor_is_not_deleted_merely_for_being_new(self):
        """The old rule deleted every soccer StatPal anchor absent from the
        pre-image. This one deletes only anchors the manifest names."""
        got = rails.plan_restore([], {"99": "555555"}, {"99|soccer:555555"})
        assert got["to_clear"] == []
        assert got["to_delete"] == []


class TestTheUndoRefusesToWriteOverSomebodyElsesEdit:
    def test_a_column_that_moved_on_is_reported_not_dragged_back(self):
        entry = _entry(11, "1043639")
        got = rails.plan_restore([entry], {"11": "999999"}, {"11|soccer:1043639"})
        assert got["to_clear"] == []
        assert got["column_moved_on"] == [
            {"event_id": 11, "written": "1043639", "holds": "999999"}
        ]
        # The anchor is still ours and still goes.
        assert len(got["to_delete"]) == 1

    def test_an_anchor_already_gone_is_reported_not_an_error(self):
        entry = _entry(11, "1043639")
        columns, _ = _now(entry)
        got = rails.plan_restore([entry], columns, set())
        assert len(got["to_clear"]) == 1
        assert got["to_delete"] == []
        assert len(got["anchor_already_gone"]) == 1


class TestAnApplyThatDiedBeforeBankingIsStillUndoable:
    """The manifest lives in two places on purpose. If the receipt never landed,
    every anchor still carries the run id, and both halves are recoverable from
    the anchor alone."""

    def test_an_attributed_anchor_missing_from_the_manifest_is_reconstructed(self):
        merged = rails.merge_manifest([], [(12, "soccer:777777", None)])
        assert merged == [
            {
                "event_id": 12,
                "fixture_id": "777777",
                "anchor_source_id": "soccer:777777",
                "column_written": True,
                "anchor_written": True,
                "unbanked": True,
            }
        ]

    def test_the_reconstructed_row_undoes_both_halves(self):
        merged = rails.merge_manifest([], [(12, "soccer:777777", None)])
        got = rails.plan_restore(merged, {"12": "777777"}, {"12|soccer:777777"})
        assert len(got["to_clear"]) == 1
        assert len(got["to_delete"]) == 1
        assert len(got["unbanked_anchors"]) == 1

    def test_an_anchor_only_write_is_reconstructed_without_a_column_clear(self):
        """`column_was_already_set` is the discriminator the writer left behind."""
        merged = rails.merge_manifest([], [(12, "soccer:777777", "true")])
        assert merged[0]["column_written"] is False
        got = rails.plan_restore(merged, {"12": "777777"}, {"12|soccer:777777"})
        assert got["to_clear"] == [], "cleared a column this pass never wrote"
        assert len(got["to_delete"]) == 1

    def test_a_banked_row_is_not_duplicated_by_its_own_anchor(self):
        entry = _entry(11, "1043639")
        merged = rails.merge_manifest([entry], [(11, "soccer:1043639", None)])
        assert merged == [entry]


class TestTheWriterRecordsWhatItWrote:
    """The other half of the repair, and the half the planner cannot check.

    `plan_restore` is only as good as the manifest handed to it. These drive the
    REAL runner and watch what it produces: the run id has to reach the anchor's
    `claim_context` (the durable attribution), and each manifest entry has to
    record which halves were actually written. A stamper that reported
    `anchor_written` for an anchor `record_anchor` merely CONFIRMED would have
    the undo delete a correspondence it did not create.
    """

    @staticmethod
    async def _drive(monkeypatch, *, outcome, held=None, run_id="run-xyz"):
        from contextlib import asynccontextmanager
        from types import SimpleNamespace

        import app.tasks.stamp_v1_statpal_fixtures as task
        from app.services.statpal_api import StatPalFixture

        start = datetime(2026, 9, 8, 19, 0, tzinfo=timezone.utc)
        fixture = StatPalFixture(
            fixture_id="board-1",
            fallback_id_3="9544921",
            home_team="Wrexham AFC",
            away_team="Cardiff",
            start_time=start,
        )
        rows = [(1, "Wrexham", "Cardiff City", start, held, "scheduled")]
        contexts = []

        class _Result:
            rowcount = 1

            def fetchall(self):
                return list(rows)

        class _Session:
            async def execute(self, statement, params=None):
                return _Result()

            async def commit(self):
                return None

            async def rollback(self):
                return None

        @asynccontextmanager
        async def _session():
            yield _Session()

        import app.tasks.base as task_base

        monkeypatch.setattr(task_base, "get_task_session", _session)

        async def _schedule(sport, day_offset=None):
            return [fixture] if day_offset == 1 else []

        monkeypatch.setattr(
            task,
            "get_statpal_service",
            lambda: SimpleNamespace(
                get_schedule_fixtures=_schedule,
                get_live_fixtures=lambda sport: _empty(),
                close=_empty,
            ),
        )

        async def _record_anchor(_s, *, event_id, key, claim_context=None):
            contexts.append(claim_context)
            return SimpleNamespace(outcome=outcome)

        monkeypatch.setattr(task, "record_anchor", _record_anchor)

        result = await task._run_stamp_soccer_statpal_fixtures(
            apply=True, now=start, apply_run_id=run_id
        )
        return result, contexts

    @pytest.mark.asyncio
    async def test_the_run_id_lands_in_the_anchors_claim_context(self, monkeypatch):
        from app.services.anchor_channel import WROTE

        _, contexts = await self._drive(monkeypatch, outcome=WROTE)
        assert contexts and contexts[0]["apply_run_id"] == "run-xyz", (
            "the anchor carries no run id, so an apply whose receipt is lost "
            "could never be attributed and never undone"
        )

    @pytest.mark.asyncio
    async def test_a_scheduled_pass_writes_no_run_id_at_all(self, monkeypatch):
        """The four beat leagues have no undo, so the key is absent rather than
        null — otherwise `->>'apply_run_id'` has to be null-guarded everywhere."""
        from app.services.anchor_channel import WROTE

        _, contexts = await self._drive(monkeypatch, outcome=WROTE, run_id=None)
        assert contexts and "apply_run_id" not in contexts[0]

    @pytest.mark.asyncio
    async def test_a_stamp_records_both_halves_as_written(self, monkeypatch):
        from app.services.anchor_channel import WROTE

        result, _ = await self._drive(monkeypatch, outcome=WROTE)
        assert result["committed_write_receipts"] == [
            {
                "event_id": 1,
                "fixture_id": "9544921",
                "anchor_source_id": "soccer:9544921",
                "column_written": True,
                "anchor_written": True,
            }
        ]

    @pytest.mark.asyncio
    async def test_a_confirmed_anchor_is_not_recorded_as_written(self, monkeypatch):
        """`record_anchor` found the anchor already there. The column is still
        ours; the anchor is not, and the manifest has to say so or the undo
        deletes somebody else's row."""
        from app.services.anchor_channel import CONFIRMED

        result, _ = await self._drive(monkeypatch, outcome=CONFIRMED)
        entry = result["committed_write_receipts"][0]
        assert entry["column_written"] is True
        assert entry["anchor_written"] is False

    @pytest.mark.asyncio
    async def test_a_plan_pass_names_its_rows_and_commits_nothing(self, monkeypatch):
        """The phantom gate (#3840) needs the ids BEFORE the write, not counts."""
        import app.tasks.stamp_v1_statpal_fixtures as task

        original = task._run_stamp_soccer_statpal_fixtures

        async def _plan(**kwargs):
            return await original(**{**kwargs, "apply": False})

        monkeypatch.setattr(task, "_run_stamp_soccer_statpal_fixtures", _plan)
        result, contexts = await self._drive(
            monkeypatch, outcome="unused", run_id=None
        )
        assert result["planned_write_receipts"] == [
            {
                "event_id": 1,
                "fixture_id": "9544921",
                "anchor_source_id": "soccer:9544921",
            }
        ]
        assert result["committed_write_receipts"] == []
        assert contexts == [], "a plan pass wrote an anchor"


async def _empty(*args, **kwargs):
    return []


class TestTheUndoLineNamesTheApplyNotTheBackup:
    @pytest.mark.asyncio
    async def test_a_backup_identity_is_refused_rather_than_restoring_nothing(self):
        code = await rails.cmd_restore(
            f"{rails.BACKUP_IDENTITY_PREFIX}:20260907T074500Z",
            apply=True,
            now=datetime.now(timezone.utc),
        )
        assert code == 1, (
            "a backup identity attributes no anchors, so this would have "
            "reported a clean restore of 0 rows"
        )


class TestTheBackupGateIsTheWholeOfD51:
    @pytest.mark.asyncio
    async def test_apply_refuses_when_no_backup_has_ever_been_taken(self, monkeypatch):
        async def _none(session, now):
            return None, None, "no backup has ever been taken"

        ran = []

        async def _never(**kwargs):
            ran.append(kwargs)
            return {}

        code = await _apply_with_stubs(rails, monkeypatch, _none, _never)
        assert code == 1
        assert ran == [], "the pass must not run without a backup"

    @pytest.mark.asyncio
    async def test_apply_refuses_a_backup_older_than_the_bound(self, monkeypatch):
        stale = rails.BACKUP_MAX_AGE + timedelta(minutes=1)

        async def _stale(session, now):
            return (
                "authority:soccer_statpal_stamp:backup:x",
                None,
                f"backup is {int(stale.total_seconds())}s old",
            )

        ran = []

        async def _never(**kwargs):
            ran.append(kwargs)
            return {}

        code = await _apply_with_stubs(rails, monkeypatch, _stale, _never)
        assert code == 1
        assert ran == []

    @pytest.mark.asyncio
    async def test_apply_runs_and_names_its_undo_when_a_fresh_backup_is_on_file(
        self, monkeypatch
    ):
        identity = "authority:soccer_statpal_stamp:backup:20260907T074500Z"

        async def _fresh(session, now):
            return identity, {"columns": {}}, None

        ran = []

        manifest = [
            {
                "event_id": 11,
                "fixture_id": "1043639",
                "anchor_source_id": "soccer:1043639",
                "column_written": True,
                "anchor_written": True,
            }
        ]

        async def _pass(**kwargs):
            ran.append(kwargs)
            return {"stamped": 80, "committed_write_receipts": manifest}

        banked = {}

        async def _bank(payload, ident, now):
            banked[ident] = payload
            return "ok"

        monkeypatch.setattr(rails, "_bank", _bank)
        code = await _apply_with_stubs(rails, monkeypatch, _fresh, _pass, bank=False)
        assert code == 0

        # The run id is generated by `cmd_apply` and must reach the writer, or
        # nothing it writes is attributable and the undo has no durable half.
        assert list(ran[0]) == ["apply", "apply_run_id"]
        assert ran[0]["apply"] is True
        run_id = ran[0]["apply_run_id"]
        assert run_id.startswith(rails.APPLY_IDENTITY_PREFIX)

        receipt = next(iter(banked.values()))
        assert receipt["verdict"] == "APPLIED"
        assert receipt["backup_identity"] == identity
        assert receipt["manifest"] == manifest
        assert receipt["manifest_rows"] == 1

        # Banked UNDER the run id, so one string reaches both the receipt and
        # the anchors, and the undo line names that — never the backup.
        assert list(banked) == [run_id]
        assert receipt["apply_run_id"] == run_id
        assert run_id in receipt["undo_command"]
        assert identity not in receipt["undo_command"]
        assert "--apply" in receipt["undo_command"]

    @pytest.mark.asyncio
    async def test_an_apply_whose_receipt_does_not_bank_says_so_and_fails(
        self, monkeypatch, capsys
    ):
        """The writes are already committed per row, so a lost receipt is not a
        lost apply — but an operator who reads exit 0 will never go looking for
        the undo line, and the anchors are the only remaining record of it."""

        async def _fresh(session, now):
            return "authority:soccer_statpal_stamp:backup:20260907T074500Z", {}, None

        async def _pass(**kwargs):
            return {"stamped": 80, "committed_write_receipts": []}

        async def _wont_bank(payload, ident, now):
            return "error"

        monkeypatch.setattr(rails, "_bank", _wont_bank)
        code = await _apply_with_stubs(rails, monkeypatch, _fresh, _pass, bank=False)
        assert code == 1
        out = capsys.readouterr().out
        assert "did NOT bank" in out
        assert "restore --identity" in out


class TestTheWindowIsWiderThanAnythingThePassCanReach:
    def test_the_preimage_covers_every_board_offset_the_spec_reads(self):
        """A pre-image narrower than the write window is a backup with holes in
        it, and the holes are invisible until a restore needs them."""
        from app.tasks.stamp_v1_statpal_fixtures import CANDIDATE_SLACK, SOCCER

        furthest = max(SOCCER.schedule_day_offsets)
        # Each board serves ~25.5h from its offset, and the pass widens the
        # candidate window by CANDIDATE_SLACK on top.
        reach = timedelta(hours=25.5 * (furthest + 1)) + CANDIDATE_SLACK
        assert rails.PREIMAGE_AFTER > reach
        assert rails.PREIMAGE_BEFORE > CANDIDATE_SLACK


async def _apply_with_stubs(mod, monkeypatch, latest_backup, run_pass, bank=True):
    """Drive `cmd_apply` with its two edges replaced and no database.

    `cmd_apply` opens a session only to look the backup up, so stubbing
    `_latest_backup` removes the database entirely — which is the point: the
    refusal must not depend on anything being reachable.
    """
    import contextlib
    import sys
    import types

    monkeypatch.setattr(mod, "_latest_backup", latest_backup)
    if bank:

        async def _noop_bank(payload, ident, now):
            return "ok"

        monkeypatch.setattr(mod, "_bank", _noop_bank)

    @contextlib.asynccontextmanager
    async def _session():
        yield object()

    base = types.ModuleType("app.tasks.base")
    base.get_task_session = _session
    monkeypatch.setitem(sys.modules, "app.tasks.base", base)

    stamper = types.ModuleType("app.tasks.stamp_v1_statpal_fixtures")
    stamper._run_stamp_soccer_statpal_fixtures = run_pass
    monkeypatch.setitem(sys.modules, "app.tasks.stamp_v1_statpal_fixtures", stamper)

    return await mod.cmd_apply(datetime.now(timezone.utc))
