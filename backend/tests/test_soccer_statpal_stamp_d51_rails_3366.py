"""The D51 rails for soccer's first StatPal stamp, tested where they can fail.

`scripts/soccer_statpal_stamp_3366.py` is the backup + one-command restore that
D51 requires before the owning lane may make that first write unattended. Every
test here is a class of defect that would make the undo *look* like it worked:

  * an undo whose selection rule has drifted from the writer's key rule, so it
    matches nothing and reports a clean zero (`_assert_namespace`);
  * an undo that clears a column it did not write, turning the restore into the
    corruption it exists to reverse;
  * an undo that clears the column and leaves the anchor, which is the orphan
    state `_write_link` writes both halves to avoid;
  * an apply that runs with no backup on file, which is the whole of D51.

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


class TestThePlannerOnlyUndoesWhatTheApplyCouldHaveWritten:
    def test_a_column_empty_before_and_populated_now_is_ours(self):
        got = rails.plan_restore(_preimage({"11": None}), [(11, "1043639")], [])
        assert got["to_clear"] == [{"event_id": 11, "written": "1043639"}]

    def test_a_column_that_already_held_an_id_is_never_touched(self):
        """`SET_FIXTURE_ID` is guarded by `IS NULL`, so this cannot be ours —
        whatever it holds now, and even if it holds something different."""
        got = rails.plan_restore(_preimage({"11": "999999"}), [(11, "1043639")], [])
        assert got["to_clear"] == []

    def test_a_column_empty_before_and_empty_now_is_a_no_op(self):
        got = rails.plan_restore(_preimage({"11": None}), [(11, None)], [])
        assert got["to_clear"] == []

    def test_a_row_the_backup_never_saw_is_reported_not_cleared(self):
        """It entered the window after the backup. A non-zero count here is the
        signal that the gap between backup and apply was too wide — which is
        exactly what `BACKUP_MAX_AGE` bounds."""
        got = rails.plan_restore(_preimage({"11": None}), [(12, "777")], [])
        assert got["to_clear"] == []
        assert got["outside_backup"] == [{"event_id": 12, "holds": "777"}]

    def test_the_undo_is_idempotent_against_a_restore_that_already_ran(self):
        first = rails.plan_restore(_preimage({"11": None}), [(11, "1043639")], [])
        assert len(first["to_clear"]) == 1
        second = rails.plan_restore(_preimage({"11": None}), [(11, None)], [])
        assert second["to_clear"] == []


class TestBothHalvesOfTheWriteComeBack:
    def test_an_anchor_absent_from_the_preimage_is_deleted(self):
        got = rails.plan_restore(_preimage({}), [], [(11, "soccer:1043639")])
        assert got["to_delete"] == [{"event_id": 11, "source_id": "soccer:1043639"}]

    def test_an_anchor_already_on_file_is_left_alone(self):
        got = rails.plan_restore(
            _preimage({}, ["11|soccer:1043639"]), [], [(11, "soccer:1043639")]
        )
        assert got["to_delete"] == []
        assert got["not_ours"] == ["11|soccer:1043639"]

    def test_one_apply_yields_a_column_clear_AND_an_anchor_delete(self):
        """The orphan this prevents: an anchor naming an event whose column no
        longer claims the fixture is a correspondence no writer can reach and
        every reader believes."""
        got = rails.plan_restore(
            _preimage({"11": None}), [(11, "1043639")], [(11, "soccer:1043639")]
        )
        assert len(got["to_clear"]) == 1
        assert len(got["to_delete"]) == 1


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

        async def _pass(**kwargs):
            ran.append(kwargs)
            return {"stamped": 80}

        banked = {}

        async def _bank(payload, ident, now):
            banked[ident] = payload
            return "ok"

        monkeypatch.setattr(rails, "_bank", _bank)
        code = await _apply_with_stubs(rails, monkeypatch, _fresh, _pass, bank=False)
        assert code == 0
        assert ran == [{"apply": True}], "the pass must run with apply=True"
        receipt = next(iter(banked.values()))
        assert receipt["verdict"] == "APPLIED"
        assert receipt["backup_identity"] == identity
        assert identity in receipt["undo_command"]
        assert "--apply" in receipt["undo_command"]


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
