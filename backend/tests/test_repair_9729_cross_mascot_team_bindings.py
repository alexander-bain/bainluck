"""#9729 — two Sep 5 college games listed under a club that only shares the mascot.

Production 2026-09-30: event 15181893 (UConn v Lafayette) has Washington as its
home club and 15181945 (Navy v Towson) has LSU as its away club, so each shows
on the wrong team page. Two pre-#7188 mapping rows point Kalshi's and
Polymarket's "Lafayette" at Washington. These tests pin the four writes, the
all-or-nothing state machine and its refusals.
"""

from __future__ import annotations

import inspect
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(__file__)), "scripts"))

import repair_9729_cross_mascot_team_bindings as repair  # noqa: E402

UCONN_GAME, NAVY_GAME = ("events", 15181893, "home_team_id"), ("events", 15181945, "away_team_id")
KALSHI_LAF, POLY_LAF = ("team_identity_mapping", 43874196, "team_id"), ("team_identity_mapping", 45278383, "team_id")


def _identity() -> dict:
    return {repair.key(w): w.identity for w in repair.WRITES}


def _state(which: str) -> dict:
    return {repair.key(w): getattr(w, which) for w in repair.WRITES}


def _plan(state: dict, *, restore: bool = False, identity=None, targets=None):
    return repair.plan(
        _identity() if identity is None else identity,
        state,
        dict(repair.TARGETS) if targets is None else targets,
        restore=restore,
    )


def _apply(state: dict, writes) -> dict:
    state = dict(state)
    for w in writes:
        k = repair.key(w)
        assert state[k] == w.before, k  # the compare half of the UPDATE
        state[k] = w.after
    return state


class TestTheManifest:
    def test_washington_leaves_the_uconn_game_for_uconn(self):
        w = {repair.key(w): w for w in repair.WRITES}[UCONN_GAME]
        assert (w.before, w.after) == (repair.WASHINGTON, repair.UCONN)
        assert w.identity[0] == "UConn Huskies"
        assert repair.TARGETS[repair.UCONN] == ("UConn Huskies", repair.NCAAF_SPORT_ID)

    def test_lsu_leaves_the_towson_side_and_it_points_at_no_club(self):
        # No Towson row exists in NCAAF: NULL, never a guess.
        w = {repair.key(w): w for w in repair.WRITES}[NAVY_GAME]
        assert (w.before, w.after) == (repair.LSU, None)
        assert w.identity[1] == "Towson Tigers"

    def test_both_lafayette_mappings_move_to_lafayette(self):
        for k in (KALSHI_LAF, POLY_LAF):
            w = {repair.key(w): w for w in repair.WRITES}[k]
            assert (w.before, w.after) == (repair.WASHINGTON, repair.LAFAYETTE)
            assert w.identity[1:] == ("Lafayette", repair.NCAAF)
        assert repair.TARGETS[repair.LAFAYETTE] == ("Lafayette Leopards", repair.NCAAF_SPORT_ID)

    def test_the_eastern_washington_rows_are_not_written(self):
        ids = {w.row_id for w in repair.WRITES}
        assert 48836904 not in ids and 49820694 not in ids

    def test_it_never_deletes_or_inserts_outside_its_backup(self):
        for fn in (repair.run, repair.update_sql):
            src = inspect.getsource(fn)
            assert "DELETE" not in src and "INSERT" not in src
        assert "DELETE" not in inspect.getsource(repair._backup)


class TestTheWrites:
    def test_apply_reaches_after(self):
        assert _apply(_state("before"), _plan(_state("before"))) == _state("after")

    def test_restore_walks_it_back(self):
        writes = _plan(_state("after"), restore=True)
        assert [repair.key(w) for w in writes] == [POLY_LAF, KALSHI_LAF, NAVY_GAME, UCONN_GAME]
        assert all(w.before == a and w.after == b for w, (a, b) in zip(
            writes, [(repair.LAFAYETTE, repair.WASHINGTON)] * 2
            + [(None, repair.LSU), (repair.UCONN, repair.WASHINGTON)]
        ))
        assert _apply(_state("after"), writes) == _state("before")

    def test_a_second_apply_writes_nothing(self):
        assert _plan(_state("after")) == []

    def test_restore_before_any_apply_writes_nothing(self):
        assert _plan(_state("before"), restore=True) == []


class TestTheSql:
    def test_the_update_is_compare_and_swap_on_its_one_column(self):
        for w in repair.WRITES:
            sql = repair.update_sql(w)
            assert f"SET {w.column} = :after" in sql
            assert f"{w.column} IS NOT DISTINCT FROM :before" in sql
            assert sql.startswith(f"UPDATE {w.table} ")

    def test_a_null_before_still_compares(self):
        # The restore of the Towson side compares against NULL; `=` would never match.
        restore = _plan(_state("after"), restore=True)
        navy = next(w for w in restore if repair.key(w) == NAVY_GAME)
        assert navy.before is None
        assert "IS NOT DISTINCT FROM :before" in repair.update_sql(navy)


class TestRefusals:
    def test_a_half_state_refuses_the_whole_run(self):
        state = _state("before")
        state[UCONN_GAME] = repair.UCONN
        with pytest.raises(repair.Refused, match="neither"):
            _plan(state)
        with pytest.raises(repair.Refused, match="neither"):
            _plan(state, restore=True)

    def test_an_off_plan_value_refuses_and_is_named(self):
        state = _state("before")
        state[KALSHI_LAF] = 12345
        with pytest.raises(repair.Refused, match="12345"):
            _plan(state)

    def test_a_row_that_no_longer_reads_as_itself_refuses(self):
        identity = _identity()
        identity[NAVY_GAME] = ("Navy Midshipmen", "Tulane Green Wave", repair.NCAAF_SPORT_ID)
        with pytest.raises(repair.Refused, match="pinned"):
            _plan(_state("before"), identity=identity)

    def test_a_target_club_renamed_or_moved_sport_refuses(self):
        targets = dict(repair.TARGETS)
        targets[repair.UCONN] = ("UConn Huskies", 999)
        with pytest.raises(repair.Refused, match="team 19768"):
            _plan(_state("before"), targets=targets)
        del targets[repair.UCONN]
        with pytest.raises(repair.Refused, match="team 19768"):
            _plan(_state("before"), targets=targets)

    def test_a_missing_row_refuses(self):
        identity = _identity()
        del identity[POLY_LAF]
        with pytest.raises(repair.Refused, match="missing"):
            _plan(_state("before"), identity=identity)

    def test_it_refuses_off_production(self):
        with pytest.raises(repair.Refused):
            repair.refuse_unless_production({"HEROKU_APP_NAME": "bainluck-staging"})
        with pytest.raises(repair.Refused):
            repair.refuse_unless_production({})
        repair.refuse_unless_production({"HEROKU_APP_NAME": "bainluck"})
