"""#8774 — D99 = A: the far-horizon hand boosts go to 0, with the pinned values as the undo.

Unit half: the repair script's decisions, the compare-and-set it issues, its refusals,
and that 0 is the value the scorer reads as "no boost" (so the write moves the card).
"""

import importlib.util
import sys
from pathlib import Path

import pytest

from app.utils.futures_highlights import compute_futures_highlight

_SCRIPT = (
    Path(__file__).resolve().parent.parent
    / "scripts"
    / "repair_8774_far_horizon_hand_boosts.py"
)


def _load():
    spec = importlib.util.spec_from_file_location("repair_8774_unit", _SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["repair_8774_unit"] = mod
    spec.loader.exec_module(mod)
    return mod


m = _load()
CANADA_CUP = 171


def _all_open_at_pinned():
    return {mid: ("open", adj) for mid, adj in m.PINNED.items()}


class TestThePopulation:
    def test_the_page_one_specimen_is_pinned_at_its_read_value(self):
        assert m.PINNED[CANADA_CUP] == 60

    def test_every_pinned_value_is_a_boost(self):
        assert m.PINNED and all(adj > 0 for adj in m.PINNED.values())

    def test_events_inside_twelve_months_are_not_pinned(self):
        """Oscars x3 and Coachella 2027 resolve 2027-12-31 but their event is inside the
        year; the odds_api World Series / Super Bowl rows carry no date and are too."""
        for excluded in (5388751, 5165726, 6173044, 108505, 1, 86832):
            assert excluded not in m.PINNED


class TestApplyPlan:
    def test_every_pinned_row_at_its_value_is_written_to_zero(self):
        out = m.plan(_all_open_at_pinned(), restore=False)
        assert out["skip"] == []
        assert sorted(out["write"]) == sorted(
            (mid, adj, 0) for mid, adj in m.PINNED.items()
        )

    def test_a_row_tapped_since_the_read_is_skipped_not_overwritten(self):
        rows = _all_open_at_pinned()
        rows[CANADA_CUP] = ("open", 75)
        out = m.plan(rows, restore=False)
        assert CANADA_CUP not in [w[0] for w in out["write"]]
        assert (CANADA_CUP, "adj 75 is neither 60 nor 0 — tapped since") in out["skip"]

    def test_already_zero_is_reported_as_done(self):
        rows = _all_open_at_pinned()
        rows[CANADA_CUP] = ("open", 0)
        out = m.plan(rows, restore=False)
        assert (CANADA_CUP, "already 0") in out["skip"]

    def test_null_reads_as_zero(self):
        rows = _all_open_at_pinned()
        rows[CANADA_CUP] = ("open", None)
        out = m.plan(rows, restore=False)
        assert (CANADA_CUP, "already 0") in out["skip"]

    def test_missing_and_closed_rows_are_skipped(self):
        rows = _all_open_at_pinned()
        del rows[CANADA_CUP]
        rows[108258] = ("closed", 15)
        out = m.plan(rows, restore=False)
        written = [w[0] for w in out["write"]]
        assert CANADA_CUP not in written and 108258 not in written
        assert (CANADA_CUP, "row missing") in out["skip"]
        assert (108258, "status 'closed', not open") in out["skip"]


class TestRestorePlan:
    def test_restore_writes_each_zeroed_row_back_to_its_pinned_value(self):
        rows = {mid: ("open", 0) for mid in m.PINNED}
        out = m.plan(rows, restore=True)
        assert out["skip"] == []
        assert sorted(out["write"]) == sorted(
            (mid, 0, adj) for mid, adj in m.PINNED.items()
        )

    def test_restore_leaves_a_row_tapped_after_the_repair(self):
        rows = {mid: ("open", 0) for mid in m.PINNED}
        rows[CANADA_CUP] = ("open", 15)
        out = m.plan(rows, restore=True)
        assert (CANADA_CUP, "adj 15 is neither 0 nor 60 — tapped since") in out["skip"]

    def test_restore_after_restore_is_a_no_op(self):
        out = m.plan(_all_open_at_pinned(), restore=True)
        assert out["write"] == []


class _Result:
    def __init__(self, rows=(), rowcount=1):
        self._rows = list(rows)
        self.rowcount = rowcount

    def __iter__(self):
        return iter(self._rows)


class _Row:
    def __init__(self, id, status, curation_score_adj):
        self.id = id
        self.status = status
        self.curation_score_adj = curation_score_adj


class _Session:
    def __init__(self, rows, update_rowcount=1):
        self._rows = rows
        self._update_rowcount = update_rowcount
        self.updates: list[tuple[str, dict]] = []
        self.committed = False

    async def execute(self, stmt, params=None):
        sql = str(stmt)
        if sql.startswith("SELECT"):
            assert sorted(params["ids"]) == sorted(m.PINNED)
            return _Result(self._rows)
        self.updates.append((sql, params))
        return _Result(rowcount=self._update_rowcount)

    async def commit(self):
        self.committed = True


def _rows(value_for):
    return [_Row(mid, "open", value_for(adj)) for mid, adj in m.PINNED.items()]


class TestRun:
    @pytest.mark.asyncio
    async def test_dry_run_writes_nothing(self):
        session = _Session(_rows(lambda adj: adj))
        out = await m.run(session, apply=False, restore=False)
        assert out["mode"] == "dry-run" and out["written"] == 0
        assert session.updates == [] and not session.committed

    @pytest.mark.asyncio
    async def test_apply_is_a_compare_and_set_from_the_pinned_value(self):
        session = _Session(_rows(lambda adj: adj))
        out = await m.run(session, apply=True, restore=False)
        assert out["written"] == len(m.PINNED) and session.committed
        sql, params = next(u for u in session.updates if u[1]["id"] == CANADA_CUP)
        assert "SET curation_score_adj = :target" in sql
        assert "COALESCE(curation_score_adj, 0) = :source" in sql
        assert params == {"id": CANADA_CUP, "source": 60, "target": 0}

    @pytest.mark.asyncio
    async def test_restore_is_the_inverse_compare_and_set(self):
        session = _Session(_rows(lambda adj: 0))
        out = await m.run(session, apply=False, restore=True)
        assert out["mode"] == "restore" and out["written"] == len(m.PINNED)
        _, params = next(u for u in session.updates if u[1]["id"] == CANADA_CUP)
        assert params == {"id": CANADA_CUP, "source": 0, "target": 60}

    @pytest.mark.asyncio
    async def test_a_write_that_changes_no_row_refuses_before_commit(self):
        """A tap landing between read and write makes the CAS miss: stop, don't commit."""
        session = _Session(_rows(lambda adj: adj), update_rowcount=0)
        with pytest.raises(m.Refused, match="expected to change 1 row, changed 0"):
            await m.run(session, apply=True, restore=False)
        assert not session.committed


class TestRefusals:
    @pytest.mark.parametrize("app", ["", "bainluck-staging", "local"])
    def test_off_production_refuses(self, app):
        with pytest.raises(m.Refused):
            m.refuse_unless_production({"HEROKU_APP_NAME": app})

    @pytest.mark.parametrize("app", ["bainluck", "bainluck-heavy"])
    def test_production_apps_pass(self, app):
        m.refuse_unless_production({"HEROKU_APP_NAME": app})


class TestZeroIsNoBoost:
    def test_the_specimens_plus_sixty_is_sixty_ranking_points(self):
        """The write moves the card only if the scorer reads the column; it does, 1:1."""
        kwargs = dict(
            market_name="Canadian Team to Win the Stanley Cup® Before the 2030-31 Season",
            sport_category="hockey",
            market_tier=1,
        )
        boosted = compute_futures_highlight(curation_score_adj=60, **kwargs)
        zeroed = compute_futures_highlight(curation_score_adj=0, **kwargs)
        assert "curation_adj:+60" in boosted.reasons
        assert not any(r.startswith("curation_adj") for r in zeroed.reasons)
        assert boosted.raw_score - zeroed.raw_score == pytest.approx(60)
