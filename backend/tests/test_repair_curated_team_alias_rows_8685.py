"""#8685 — the eleven curated nicknames reach their teams' rows, with an exact undo.

Unit half: the repair script's decisions, the compare-and-set it issues, its refusals,
that the undo is the inverse of the apply, and that what it writes is the config map's
alias (so the TEAMS card and the games/markets rails answer the same words).
"""

import asyncio
import importlib.util
import sys
from pathlib import Path

import pytest

from app.config.team_aliases import CURATED_TEAM_ALIASES

_SCRIPT = (
    Path(__file__).resolve().parent.parent
    / "scripts"
    / "repair_8685_curated_team_alias_rows.py"
)


def _load():
    spec = importlib.util.spec_from_file_location("repair_8685_unit", _SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["repair_8685_unit"] = mod
    spec.loader.exec_module(mod)
    return mod


m = _load()
HABS = 568  # Montreal Canadiens — the issue's specimen (`habs` served Habay La Neuve)


def _all_at_before():
    return {tid: (sk, name, list(before)) for tid, (sk, name, _a, before) in m.PINNED.items()}


def _all_applied():
    return {
        tid: (sk, name, list(before) + [alias])
        for tid, (sk, name, alias, before) in m.PINNED.items()
    }


class TestThePopulation:
    def test_the_eleven_are_the_config_maps_8685_entries(self):
        for sport_key, name, alias, _before in m.PINNED.values():
            assert alias in CURATED_TEAM_ALIASES[(sport_key, name)]
        assert sorted(a for _s, _n, a, _b in m.PINNED.values()) == sorted(
            ["habs", "pens", "sens", "nucks", "yanks", "nats", "phils", "cubbies",
             "dbacks", "mavs", "jags"]
        )

    def test_the_specimen_is_pinned(self):
        assert m.PINNED[HABS][:3] == ("icehockey_nhl", "Montreal Canadiens", "habs")

    def test_no_before_list_already_held_its_alias(self):
        """The undo removes exactly the alias. That is only the inverse of the apply
        if the row did not already hold it — the proof the docstring leans on."""
        for _s, _n, alias, before in m.PINNED.values():
            assert all(b.strip().lower() != alias for b in before)


class TestApplyPlan:
    def test_every_row_gets_its_alias_appended_and_keeps_the_rest(self):
        out = m.plan(_all_at_before(), restore=False)
        assert out["skip"] == []
        assert sorted(out["write"]) == sorted(
            (tid, list(before), list(before) + [alias])
            for tid, (_s, _n, alias, before) in m.PINNED.items()
        )

    def test_a_name_an_espn_sync_added_since_the_read_survives(self):
        rows = _all_at_before()
        rows[HABS] = ("icehockey_nhl", "Montreal Canadiens", ["Montreal", "Canadiens", "MTL"])
        write = {w[0]: w for w in m.plan(rows, restore=False)["write"]}
        assert write[HABS][2] == ["Montreal", "Canadiens", "MTL", "habs"]

    def test_already_present_in_any_case_is_skipped(self):
        rows = _all_at_before()
        rows[HABS] = ("icehockey_nhl", "Montreal Canadiens", ["Montreal", "Habs"])
        out = m.plan(rows, restore=False)
        assert HABS not in [w[0] for w in out["write"]]
        assert (HABS, "'habs' already present") in out["skip"]

    def test_null_alternate_names_gets_the_alias_alone(self):
        rows = _all_at_before()
        rows[HABS] = ("icehockey_nhl", "Montreal Canadiens", None)
        write = {w[0]: w for w in m.plan(rows, restore=False)["write"]}
        assert write[HABS][1:] == ([], ["habs"])

    def test_a_missing_row_is_skipped(self):
        rows = _all_at_before()
        del rows[HABS]
        out = m.plan(rows, restore=False)
        assert (HABS, "row missing") in out["skip"]
        assert len(out["write"]) == len(m.PINNED) - 1

    def test_an_id_that_names_another_team_refuses_the_run(self):
        rows = _all_at_before()
        rows[HABS] = ("soccer_belgium_first_div", "Habay La Neuve", [])
        with pytest.raises(m.Refused):
            m.plan(rows, restore=False)


class TestRestorePlan:
    def test_restore_is_the_inverse_of_apply(self):
        out = m.plan(_all_applied(), restore=True)
        assert out["skip"] == []
        assert sorted(out["write"]) == sorted(
            (tid, list(before) + [alias], list(before))
            for tid, (_s, _n, alias, before) in m.PINNED.items()
        )

    def test_restore_keeps_a_name_synced_in_after_the_repair(self):
        rows = _all_applied()
        rows[HABS] = ("icehockey_nhl", "Montreal Canadiens", ["Montreal", "Canadiens", "habs", "MTL"])
        write = {w[0]: w for w in m.plan(rows, restore=True)["write"]}
        assert write[HABS][2] == ["Montreal", "Canadiens", "MTL"]

    def test_restore_before_apply_is_a_no_op(self):
        out = m.plan(_all_at_before(), restore=True)
        assert out["write"] == []
        assert (HABS, "'habs' absent, nothing to undo") in out["skip"]


class _Result:
    def __init__(self, rows=(), rowcount=1):
        self._rows = list(rows)
        self.rowcount = rowcount

    def __iter__(self):
        return iter(self._rows)


class _Row:
    def __init__(self, id, sport_key, name, alternate_names):
        self.id = id
        self.sport_key = sport_key
        self.name = name
        self.alternate_names = alternate_names


class _Session:
    def __init__(self, rows, update_rowcount=1):
        self._rows = rows
        self._update_rowcount = update_rowcount
        self.updates: list[tuple[str, dict]] = []
        self.committed = False
        self.rolled_back = False

    async def execute(self, stmt, params=None):
        sql = str(stmt)
        if sql.startswith("SELECT"):
            assert sorted(params["ids"]) == sorted(m.PINNED)
            return _Result(self._rows)
        self.updates.append((sql, params))
        return _Result(rowcount=self._update_rowcount)

    async def commit(self):
        self.committed = True

    async def rollback(self):
        self.rolled_back = True


def _rows_at_before(as_text=False):
    import json

    return [
        _Row(tid, sk, name, json.dumps(before) if as_text else list(before))
        for tid, (sk, name, _a, before) in m.PINNED.items()
    ]


class TestRun:
    def test_dry_run_writes_nothing(self):
        s = _Session(_rows_at_before())
        out = asyncio.run(m.run(s, apply=False, restore=False))
        assert out["mode"] == "dry-run" and len(out["write"]) == 11
        assert s.updates == [] and not s.committed

    @pytest.mark.parametrize("as_text", [False, True])
    def test_apply_issues_one_compare_and_set_per_row(self, as_text):
        import json

        s = _Session(_rows_at_before(as_text=as_text))
        out = asyncio.run(m.run(s, apply=True, restore=False))
        assert out["written"] == 11 and s.committed
        by_id = {p["id"]: p for _sql, p in s.updates}
        assert json.loads(by_id[HABS]["current"]) == ["Montreal", "Canadiens"]
        assert json.loads(by_id[HABS]["new"]) == ["Montreal", "Canadiens", "habs"]
        for sql, _p in s.updates:
            assert "IS NOT DISTINCT FROM CAST(:current AS jsonb)" in sql
            assert sql.startswith("UPDATE teams SET alternate_names")

    def test_a_null_row_compares_against_sql_null(self):
        rows = _rows_at_before()
        rows[0] = _Row(rows[0].id, rows[0].sport_key, rows[0].name, None)
        s = _Session(rows)
        asyncio.run(m.run(s, apply=True, restore=False))
        by_id = {p["id"]: p for _sql, p in s.updates}
        assert by_id[rows[0].id]["current"] is None

    def test_a_write_that_changes_no_row_refuses(self):
        s = _Session(_rows_at_before(), update_rowcount=0)
        with pytest.raises(m.Refused):
            asyncio.run(m.run(s, apply=True, restore=False))
        assert not s.committed


class TestRefusals:
    @pytest.mark.parametrize("app", ["", "bainluck-staging", "local"])
    def test_refuses_off_production(self, app):
        with pytest.raises(m.Refused):
            m.refuse_unless_production({"HEROKU_APP_NAME": app})

    @pytest.mark.parametrize("app", ["bainluck", "bainluck-heavy"])
    def test_runs_on_production(self, app):
        m.refuse_unless_production({"HEROKU_APP_NAME": app})
