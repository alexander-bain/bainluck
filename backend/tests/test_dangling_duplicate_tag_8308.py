"""#8308 — a merge must not strand a ``duplicate-of`` tag on a row it deletes.

Unit half. What the SQL actually does to a JSONB array is asserted against a real
server in ``tests/integration/test_dangling_duplicate_tag_8308_pg.py``; this file pins
that every merge rail reaches the tag step, what it reports, and the repair script's
decisions and refusals.
"""

import importlib.util
import sys
from pathlib import Path

import pytest

from app.utils.event_child_repoint import (
    TAG_CLEARED_ON_KEEP,
    TAG_RETARGETED,
    repoint_event_children,
)


class _Result:
    def __init__(self, rowcount=0):
        self.rowcount = rowcount

    def all(self):
        return []


class _RecordingSession:
    def __init__(self, rowcount=1):
        self.statements: list[tuple[str, dict]] = []
        self._rowcount = rowcount

    async def execute(self, stmt, params=None):
        self.statements.append((str(stmt), params or {}))
        return _Result(self._rowcount)


def _tag_statements(session):
    return [(s, p) for s, p in session.statements if s.startswith("UPDATE events SET event_tags")]


class TestTheMergeRailMovesTheTag:
    @pytest.mark.asyncio
    async def test_both_arms_are_issued_with_the_orphan_and_keep_tags(self):
        session = _RecordingSession()
        await repoint_event_children(session, keep_id=15317724, orphan_id=15317957)
        stmts = _tag_statements(session)
        assert len(stmts) == 2, "the tag step is not reached from repoint_event_children"

        clear_sql, clear_params = stmts[0]
        assert "WHERE id = :keep" in clear_sql
        assert clear_params["old_tag"] == "provenance:duplicate-of:15317957"
        assert clear_params["keep"] == 15317724

        retarget_sql, retarget_params = stmts[1]
        assert "id <> :keep AND id <> :orphan" in retarget_sql
        assert retarget_params["new_tag"] == "provenance:duplicate-of:15317724"
        assert retarget_params["old_tag"] == "provenance:duplicate-of:15317957"

    @pytest.mark.asyncio
    async def test_the_tag_step_runs_after_every_child_table(self):
        """The caller's DELETE follows this function; the tag step must be inside it,
        not left for a caller to remember."""
        session = _RecordingSession()
        await repoint_event_children(session, keep_id=1, orphan_id=2)
        last_two = [s for s, _ in session.statements[-2:]]
        assert all(s.startswith("UPDATE events SET event_tags") for s in last_two)

    @pytest.mark.asyncio
    async def test_the_moves_are_reported_under_names_no_one_takes_for_a_table(self):
        session = _RecordingSession(rowcount=2)
        out = await repoint_event_children(session, keep_id=1, orphan_id=2)
        assert out["repointed"][TAG_CLEARED_ON_KEEP] == 2
        assert out["repointed"][TAG_RETARGETED] == 2
        assert set(out) == {"repointed", "dropped_as_duplicate", "markets"}

    @pytest.mark.asyncio
    async def test_no_tag_moves_reports_nothing(self):
        session = _RecordingSession(rowcount=0)
        out = await repoint_event_children(session, keep_id=1, orphan_id=2)
        assert TAG_CLEARED_ON_KEEP not in out["repointed"]
        assert TAG_RETARGETED not in out["repointed"]


_SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "repair_8308_dangling_duplicate_tags.py"


def _load():
    spec = importlib.util.spec_from_file_location("repair_8308_unit", _SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["repair_8308_unit"] = mod
    spec.loader.exec_module(mod)
    return mod


m = _load()
GAME2, NYY2 = 15317724, 15316870
DEAD_G2, DEAD_NYY2 = 15317957, 15317440


def _rows():
    return {
        GAME2: ["provenance:source:odds_api", f"provenance:duplicate-of:{DEAD_G2}"],
        NYY2: [f"provenance:duplicate-of:{DEAD_NYY2}", "narrative:rivalry"],
    }


class TestTheRepairDecides:
    def test_the_pins_are_the_two_verified_rows_and_nothing_else(self):
        assert m.PINNED == {GAME2: DEAD_G2, NYY2: DEAD_NYY2}
        # 14788069 carries the wrong score and must stay hidden until it is fixed.
        assert 14788069 not in m.PINNED

    def test_apply_writes_both_dangling_tags(self):
        out = m.plan(_rows(), set(), restore=False)
        assert out["write"] == [
            (GAME2, f"provenance:duplicate-of:{DEAD_G2}"),
            (NYY2, f"provenance:duplicate-of:{DEAD_NYY2}"),
        ]
        assert out["skip"] == []

    def test_a_live_target_refuses_the_whole_run(self):
        with pytest.raises(m.Refused, match=str(DEAD_NYY2)):
            m.plan(_rows(), {DEAD_NYY2}, restore=False)

    def test_already_healed_and_missing_rows_are_skipped_not_written(self):
        rows = {GAME2: ["provenance:source:odds_api"]}
        out = m.plan(rows, set(), restore=False)
        assert out["write"] == []
        assert out["skip"] == [(GAME2, "tag already absent"), (NYY2, "row missing")]

    def test_restore_writes_only_rows_missing_their_tag(self):
        rows = {GAME2: ["provenance:source:odds_api"], NYY2: None}
        out = m.plan(rows, set(), restore=True)
        assert [w[0] for w in out["write"]] == [GAME2, NYY2]
        out = m.plan(_rows(), set(), restore=True)
        assert out["write"] == []

    @pytest.mark.parametrize("app", ["", "bainluck-staging", None])
    def test_off_production_refuses(self, app):
        env = {} if app is None else {"HEROKU_APP_NAME": app}
        with pytest.raises(m.Refused):
            m.refuse_unless_production(env)

    @pytest.mark.parametrize("app", ["bainluck", "bainluck-heavy"])
    def test_production_apps_pass(self, app):
        m.refuse_unless_production({"HEROKU_APP_NAME": app})
