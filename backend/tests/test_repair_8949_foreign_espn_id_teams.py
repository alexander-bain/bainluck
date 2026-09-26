"""#8949 — 55 college-baseball team rows wear another school's ESPN identity.

Production 2026-09-26: `/search?q=cowboys` listed "Fresno State · 34-19" under the
Oklahoma State crest, because row 14624 is named Fresno State and holds Oklahoma
State's ESPN id ``110`` with the badge, record, location and aliases that came
with it. The repair clears the ESPN-sourced identity from the pinned rows; these
tests pin the manifest against the writer's own predicate and the plan's CAS.
"""

from __future__ import annotations

import asyncio
import os
import sys
from types import SimpleNamespace

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(__file__)), "scripts"))

import repair_8949_foreign_espn_id_teams as repair  # noqa: E402
from app.tasks.espn_sync import ESPN_SOURCED_IDENTITY_FIELDS  # noqa: E402
from app.utils.espn_helpers import espn_identity_corresponds  # noqa: E402


def _club(display_name: str) -> SimpleNamespace:
    return SimpleNamespace(
        display_name=display_name, name=None, short_name=None, nickname=None, location=None
    )


def _rows(state: str) -> dict:
    """Every pinned row as production held it BEFORE, or as the clear leaves it."""
    return {
        i: (name, espn_id if state == "before" else None)
        for i, (name, espn_id, _club_name) in repair.PINNED.items()
    }


class TestTheManifest:
    def test_the_specimen_is_pinned(self):
        assert repair.PINNED[14624] == ("Fresno State", "110", "Oklahoma State Cowboys")
        assert repair.PINNED[12954] == ("Oklahoma State", "307", "Kennesaw State Owls")

    def test_it_is_the_55_rows_measured(self):
        assert len(repair.PINNED) == 55

    def test_every_pinned_row_names_a_different_club_than_its_espn_id(self):
        # The writer's own predicate, aliases withheld: they came from the same
        # payload and cannot vouch for it.
        vouched = [
            i
            for i, (name, _eid, club) in repair.PINNED.items()
            if espn_identity_corresponds(name, None, _club(club))
        ]
        assert vouched == []

    @pytest.mark.parametrize(
        "name, club",
        [
            ("Fresno State", "Fresno State Bulldogs"),
            ("Oklahoma State", "Oklahoma State Cowboys"),
            ("Wichita State", "Wichita State Shockers"),
            ("Cal Baptist Lancers", "California Baptist Lancers"),
        ],
    )
    def test_control_the_same_predicate_accepts_the_rows_own_school(self, name, club):
        assert espn_identity_corresponds(name, None, _club(club))

    def test_no_row_is_pinned_under_its_own_school(self):
        for name, _eid, club in repair.PINNED.values():
            assert not club.lower().startswith(name.lower() + " "), (name, club)


class TestTheClearedFields:
    def test_the_clear_is_the_id_plus_every_espn_sourced_field(self):
        assert repair.CLEARED_FIELDS == ("espn_id", *ESPN_SOURCED_IDENTITY_FIELDS)

    def test_it_includes_what_search_reads(self):
        for f in ("alternate_names", "logo_url_small", "abbreviation", "current_record"):
            assert f in repair.CLEARED_FIELDS


class TestThePlan:
    def test_apply_clears_every_pinned_row(self):
        got = repair.plan(_rows("before"), restore=False)
        assert sorted(got["write"]) == sorted(repair.PINNED)
        assert got["skip"] == []

    def test_a_second_apply_writes_nothing(self):
        got = repair.plan(_rows("after"), restore=False)
        assert got["write"] == []
        assert {r for _i, r in got["skip"]} == {"already cleared"}

    def test_restore_writes_every_cleared_row(self):
        got = repair.plan(_rows("after"), restore=True)
        assert sorted(got["write"]) == sorted(repair.PINNED)

    def test_restore_before_any_clear_writes_nothing(self):
        got = repair.plan(_rows("before"), restore=True)
        assert got["write"] == []
        assert {r for _i, r in got["skip"]} == {"never cleared"}

    def test_a_row_whose_id_changed_since_the_pin_is_skipped(self):
        rows = _rows("before")
        rows[14624] = ("Fresno State", "137")
        got = repair.plan(rows, restore=False)
        assert 14624 not in got["write"]
        assert (14624, "espn_id changed since the pin (137)") in got["skip"]

    def test_restore_does_not_undo_a_refill(self):
        rows = _rows("after")
        rows[14624] = ("Fresno State", "137")
        got = repair.plan(rows, restore=True)
        assert 14624 not in got["write"]
        assert (14624, "refilled since the clear (espn_id 137)") in got["skip"]

    def test_a_missing_row_is_skipped(self):
        rows = _rows("before")
        del rows[14624]
        got = repair.plan(rows, restore=False)
        assert (14624, "row missing") in got["skip"]

    def test_an_id_that_no_longer_names_its_team_refuses_the_whole_run(self):
        rows = _rows("before")
        rows[14624] = ("Toledo Rockets", "110")
        with pytest.raises(repair.Refused):
            repair.plan(rows, restore=False)

    def test_it_refuses_off_production(self):
        for env in ({}, {"HEROKU_APP_NAME": "bainluck-staging"}):
            with pytest.raises(repair.Refused):
                repair.refuse_unless_production(env)
        repair.refuse_unless_production({"HEROKU_APP_NAME": "bainluck"})
        repair.refuse_unless_production({"HEROKU_APP_NAME": "bainluck-heavy"})


class _Result:
    def __init__(self, rows=(), rowcount=0, scalar=None):
        self._rows, self.rowcount, self._scalar = list(rows), rowcount, scalar

    def __iter__(self):
        return iter(self._rows)

    def scalar_one(self):
        return self._scalar


class _Session:
    """Holds the pinned rows in memory and records every statement."""

    def __init__(self, rows: dict, banked: int | None = None):
        self.rows = dict(rows)
        self.sql: list[str] = []
        self.banked = banked
        self.commits = 0

    async def execute(self, stmt, params=None):
        sql = str(stmt)
        self.sql.append(sql)
        params = params or {}
        if sql.startswith("SELECT id, name, espn_id FROM teams"):
            return _Result(
                SimpleNamespace(id=i, name=n, espn_id=e) for i, (n, e) in self.rows.items()
            )
        if sql.startswith("SELECT count(*)"):
            return _Result(scalar=len(params["ids"]) if self.banked is None else self.banked)
        if sql.startswith("UPDATE teams"):
            i = params["id"]
            name, eid = self.rows[i]
            if "espn_id = :espn_id" in sql and name == params["name"] and eid == params["espn_id"]:
                self.rows[i] = (name, None)
                return _Result(rowcount=1)
            if "espn_id IS NULL" in sql and name == params["name"] and eid is None:
                self.rows[i] = (name, repair.PINNED[i][1])
                return _Result(rowcount=1)
            return _Result(rowcount=0)
        return _Result()

    async def commit(self):
        self.commits += 1


class TestTheRun:
    def test_dry_run_writes_nothing(self):
        s = _Session(_rows("before"))
        out = asyncio.run(repair.run(s, apply=False, restore=False))
        assert out["planned"] == 55 and out["written"] == 0
        assert not any(q.startswith(("UPDATE", "INSERT", "CREATE")) for q in s.sql)
        assert len(out["still_holding_pinned_espn_id"]) == 55

    def test_apply_backs_up_before_it_clears_and_reads_back(self):
        s = _Session(_rows("before"))
        out = asyncio.run(repair.run(s, apply=True, restore=False))
        first_update = next(i for i, q in enumerate(s.sql) if q.startswith("UPDATE"))
        first_insert = next(i for i, q in enumerate(s.sql) if q.startswith("INSERT"))
        assert first_insert < first_update
        assert out["written"] == 55
        assert out["still_holding_pinned_espn_id"] == []

    def test_the_backup_banks_every_cleared_field(self):
        s = _Session(_rows("before"))
        asyncio.run(repair.run(s, apply=True, restore=False))
        insert = next(q for q in s.sql if q.startswith("INSERT"))
        for f in repair.CLEARED_FIELDS:
            assert f"'{f}', {f}" in insert

    def test_a_short_backup_refuses_before_any_clear(self):
        s = _Session(_rows("before"), banked=54)
        with pytest.raises(repair.Refused):
            asyncio.run(repair.run(s, apply=True, restore=False))
        assert not any(q.startswith("UPDATE") for q in s.sql)

    def test_the_clear_is_compare_and_swap_on_name_and_id(self):
        s = _Session(_rows("before"))
        asyncio.run(repair.run(s, apply=True, restore=False))
        update = next(q for q in s.sql if q.startswith("UPDATE"))
        assert "name = :name AND espn_id = :espn_id" in update

    def test_restore_brings_every_row_back_and_keeps_jsonb_null_as_null(self):
        s = _Session(_rows("after"))
        out = asyncio.run(repair.run(s, apply=False, restore=True))
        assert out["written"] == 55
        assert len(out["still_holding_pinned_espn_id"]) == 55
        update = next(q for q in s.sql if q.startswith("UPDATE"))
        assert "teams.espn_id IS NULL" in update
        assert "NULLIF(b.before->'alternate_names', 'null'::jsonb)" in update
