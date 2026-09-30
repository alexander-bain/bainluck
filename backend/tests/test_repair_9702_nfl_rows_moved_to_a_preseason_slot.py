"""#9702 — two NFL regular-season rows moved onto an Aug 15 preseason slot and closed; a third's sportsbook id sits on the preseason game.

Production 2026-09-30: 14781719 (LAC @ KC, real 2026-10-18) and 15184679
(MIN @ NYJ, real 2027-01-03) are dated to the Aug 15 preseason slot the ESPN
scheduled pass paired them with, and closed with no score — neither game has
another row, so neither reaches a reader. 14780590 (the DAL @ SEA preseason
game) holds the Odds API id of the Dec 8 game, whose row 15304746 has none.
These tests pin the writes, their order, the all-or-nothing state machine and
its refusals.
"""

from __future__ import annotations

import os
import sys
from datetime import datetime

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(__file__)), "scripts"))

import repair_9702_nfl_rows_moved_to_a_preseason_slot as repair  # noqa: E402

KC, NYJ, PRE, DEC8 = repair.KC_LAC, repair.NYJ_MIN, repair.SEA_DAL_PRESEASON, repair.SEA_DAL_DEC8
XID = repair.DEC8_ODDS_ID


def _identity(state: dict) -> dict:
    return {
        e: (*repair.PINNED[e][:3], state[e]["external_id"]) for e in repair.PINNED
    }


def _holders(state: dict) -> list[int]:
    return sorted(e for e, cols in state.items() if cols["external_id"] == XID)


def _plan(state: dict, *, restore: bool = False, holders: list[int] | None = None):
    return repair.plan(
        _identity(state), state, _holders(state) if holders is None else holders,
        restore=restore,
    )


def _apply(state: dict, writes) -> dict:
    """Walk the writes one statement at a time: compare-and-swap, and the external_id UNIQUE constraint."""
    state = {e: dict(cols) for e, cols in state.items()}
    for event_id, old, new in writes:
        for c, v in old.items():
            assert state[event_id][c] == v, (event_id, c)
        if new.get("external_id") is not None:
            held = {cols["external_id"] for e, cols in state.items() if e != event_id}
            assert new["external_id"] not in held, (
                f"events.external_id UNIQUE: {new['external_id']} still held when written to {event_id}"
            )
        state[event_id].update(new)
    return state


class TestTheManifest:
    def test_the_two_missing_games_come_back_on_their_espn_dates(self):
        assert repair.AFTER[KC]["commence_time"] == "2026-10-18T20:25:00+00:00"
        assert repair.AFTER[NYJ]["commence_time"] == "2027-01-03T18:00:00+00:00"
        for e in (KC, NYJ):
            assert repair.BEFORE[e]["status"] == "closed"
            assert repair.AFTER[e]["status"] == "scheduled"
            assert repair.AFTER[e]["completed_at"] is None
            assert repair.AFTER[e]["llm_importance"] == "regular_season"

    def test_the_real_dates_are_not_the_preseason_slot(self):
        # Control: the BEFORE kickoff is the slot of a different (preseason)
        # game and precedes the regular season; the AFTER is inside it.
        season_opens = datetime.fromisoformat("2026-09-10T00:00:00+00:00")
        for e in (KC, NYJ):
            assert datetime.fromisoformat(repair.BEFORE[e]["commence_time"]) < season_opens
            assert datetime.fromisoformat(repair.AFTER[e]["commence_time"]) > season_opens

    def test_the_stale_box_score_stamp_is_cleared(self):
        # A non-NULL box_score_data keeps the post-game box-score pass
        # (box_score_data IS NULL) off the real game once it is played.
        for e in (KC, NYJ):
            assert '"error": "not_available"' in repair.BEFORE[e]["box_score_data"]
            assert repair.AFTER[e]["box_score_data"] is None

    def test_the_moved_rows_keep_both_their_real_ids(self):
        for e in (KC, NYJ):
            assert repair.AFTER[e]["external_id"] == repair.BEFORE[e]["external_id"]
            assert repair.PINNED[e][3] == repair.BEFORE[e]["external_id"]
        assert repair.PINNED[KC][2] == "401873006"
        assert repair.PINNED[NYJ][2] == "401873163"

    def test_only_the_odds_id_moves_between_the_two_seahawks_rows(self):
        assert XID == "0db4646c964ecdff19957373fe707546"
        for e in (PRE, DEC8):
            moved = [c for c in repair.BEFORE[e] if repair.BEFORE[e][c] != repair.AFTER[e][c]]
            assert moved == ["external_id"], (e, moved)
        assert (repair.BEFORE[PRE]["external_id"], repair.AFTER[PRE]["external_id"]) == (XID, None)
        assert (repair.BEFORE[DEC8]["external_id"], repair.AFTER[DEC8]["external_id"]) == (None, XID)

    def test_the_preseason_rows_real_box_score_is_not_pinned_or_written(self):
        assert "box_score_data" not in repair.BEFORE[PRE]
        assert "box_score_data" not in repair.AFTER[PRE]

    def test_it_writes_no_other_table(self):
        import inspect

        for fn in (repair.run, repair._read, repair._backup, repair.update_sql):
            src = inspect.getsource(fn)
            assert "odds_snapshots" not in src
            assert "futures_markets" not in src


class TestTheWrites:
    def test_apply_reaches_after_in_an_order_the_unique_constraint_allows(self):
        writes = _plan(repair.BEFORE)
        assert [w[0] for w in writes] == [KC, NYJ, PRE, DEC8]
        assert _apply(repair.BEFORE, writes) == repair.AFTER

    def test_each_write_moves_only_its_changed_columns(self):
        writes = dict((e, (o, n)) for e, o, n in _plan(repair.BEFORE))
        assert set(writes[KC][1]) == {
            "commence_time", "status", "completed_at", "llm_importance", "box_score_data",
        }
        assert set(writes[PRE][1]) == {"external_id"}
        assert set(writes[DEC8][1]) == {"external_id"}

    def test_the_reverse_order_would_violate_the_unique_constraint(self):
        # Control: the order is load-bearing, not incidental.
        writes = _plan(repair.BEFORE)
        with pytest.raises(AssertionError, match="UNIQUE"):
            _apply(repair.BEFORE, list(reversed(writes)))

    def test_restore_walks_it_back_in_the_opposite_order(self):
        writes = _plan(repair.AFTER, restore=True)
        assert [w[0] for w in writes] == [DEC8, PRE, NYJ, KC]
        assert _apply(repair.AFTER, writes) == repair.BEFORE

    def test_a_second_apply_writes_nothing(self):
        assert _plan(repair.AFTER) == []

    def test_restore_before_any_apply_writes_nothing(self):
        assert _plan(repair.BEFORE, restore=True) == []


class TestTheSql:
    def test_every_written_column_is_compare_and_swapped(self):
        _, old, new = _plan(repair.BEFORE)[0]
        sql = repair.update_sql(old, new)
        for c in new:
            assert f":new_{c}" in sql
            assert f":old_{c}" in sql
        assert "box_score_data = CAST(:new_box_score_data AS jsonb)" in sql
        assert "box_score_data::text IS NOT DISTINCT FROM :old_box_score_data" in sql
        assert "completed_at IS NOT DISTINCT FROM :old_completed_at" in sql

    def test_timestamps_bind_as_datetimes(self):
        assert repair._bind("commence_time", "2026-10-18T20:25:00+00:00") == datetime.fromisoformat(
            "2026-10-18T20:25:00+00:00"
        )
        assert repair._bind("completed_at", None) is None
        assert repair._bind("status", "closed") == "closed"


class TestRefusals:
    def test_a_half_state_refuses_the_whole_run(self):
        # One row already repaired by hand, the rest untouched: never ours to finish by guessing.
        state = {e: dict(cols) for e, cols in repair.BEFORE.items()}
        state[KC] = dict(repair.AFTER[KC])
        with pytest.raises(repair.Refused, match="neither"):
            _plan(state)
        with pytest.raises(repair.Refused, match="neither"):
            _plan(state, restore=True)

    def test_an_off_plan_value_refuses_and_is_named(self):
        # A linker pass re-closed the row with a score: off both plans.
        state = {e: dict(cols) for e, cols in repair.BEFORE.items()}
        state[NYJ]["status"] = "completed"
        with pytest.raises(repair.Refused, match="'status': 'completed'"):
            _plan(state)

    def test_an_unpinned_row_holding_the_odds_id_refuses(self):
        with pytest.raises(repair.Refused, match="unpinned"):
            _plan(repair.BEFORE, holders=[PRE, 15999999])

    def test_a_row_that_no_longer_reads_as_its_game_refuses(self):
        identity = _identity(repair.BEFORE)
        identity[KC] = ("Kansas City Chiefs", "Los Angeles Rams", *identity[KC][2:])
        with pytest.raises(repair.Refused, match="pinned"):
            repair.plan(identity, repair.BEFORE, _holders(repair.BEFORE), restore=False)

    def test_a_moved_row_whose_odds_id_changed_refuses(self):
        identity = _identity(repair.BEFORE)
        identity[NYJ] = (*identity[NYJ][:3], "ffffffffffffffffffffffffffffffff")
        with pytest.raises(repair.Refused, match="pinned"):
            repair.plan(identity, repair.BEFORE, _holders(repair.BEFORE), restore=False)

    def test_a_missing_row_refuses(self):
        identity = _identity(repair.BEFORE)
        del identity[DEC8]
        with pytest.raises(repair.Refused, match="missing"):
            repair.plan(identity, repair.BEFORE, _holders(repair.BEFORE), restore=False)

    def test_it_refuses_off_production(self):
        with pytest.raises(repair.Refused):
            repair.refuse_unless_production({})
        with pytest.raises(repair.Refused):
            repair.refuse_unless_production({"HEROKU_APP_NAME": "bainluck-staging"})
        repair.refuse_unless_production({"HEROKU_APP_NAME": "bainluck"})
