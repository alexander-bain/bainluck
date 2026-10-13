"""#2978 — NLCS Game 2's ESPN id sits on the finished Game 1 row.

Production 2026-10-12: 15326811 (MIL v LAD, Game 1, final 2-1) holds ESPN
401908031, which ESPN's own summary names as NLCS Game 2 (21:00Z that day);
the Game 2 row 15329040 holds nothing and cannot take the id while the unique
index holds it on the Game 1 row. These tests pin the move's order, its
all-or-nothing state machine and its refusals.
"""

from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(__file__)), "scripts"))

import repair_2978_nlcs_game2_espn_id_on_the_game1_row as repair  # noqa: E402

G1, G2 = repair.GAME1_ROW, repair.GAME2_ROW
G2_ID = repair.GAME2_ESPN_ID


def _rows(state: dict) -> dict:
    return {e: (*repair.PINNED[e], state[e]) for e in repair.PINNED}


def _holders(state: dict) -> list[int]:
    return sorted(e for e, eid in state.items() if eid == G2_ID)


def _plan(state: dict, *, restore: bool = False, holders=None, anchored_to=()):
    return repair.plan(
        _rows(state),
        _holders(state) if holders is None else holders,
        list(anchored_to),
        restore=restore,
    )


def _apply(state: dict, writes) -> dict:
    """Walk the writes one statement at a time, enforcing the unique index."""
    state = dict(state)
    for event_id, old, new in writes:
        assert state[event_id] == old
        if new is not None:
            assert new not in {v for k, v in state.items() if k != event_id}, (
                f"uq_events_espn_id: {new} still held when written to {event_id}"
            )
        state[event_id] = new
    return state


class TestTheManifest:
    def test_the_specimen(self):
        assert repair.BEFORE == {15326811: "401908031", 15329040: None}
        assert repair.AFTER == {15326811: None, 15329040: "401908031"}

    def test_the_rows_read_as_the_two_games_espn_names(self):
        assert repair.PINNED[G1][0] == "2026-10-12T00:00:00+00:00"
        assert repair.PINNED[G2][0] == "2026-10-12T21:00:00+00:00"
        for _k, home, away in repair.PINNED.values():
            assert (home, away) == ("Milwaukee Brewers", "Los Angeles Dodgers")

    def test_game1s_real_id_is_never_written(self):
        # 401908030 is on 15326812, the ESPN row for the same game; the
        # unique index allows one holder, and that fold is not this repair.
        written = {new for _e, _old, new in repair.MOVES} | {
            old for _e, old, _new in repair.MOVES
        }
        assert "401908030" not in written
        assert 15326812 not in repair.PINNED


class TestTheMove:
    def test_apply_moves_the_id_in_an_order_the_unique_index_allows(self):
        writes = _plan(repair.BEFORE)
        assert writes == [(G1, G2_ID, None), (G2, None, G2_ID)]
        assert _apply(repair.BEFORE, writes) == repair.AFTER

    def test_the_reverse_order_would_violate_the_unique_index(self):
        # Control: the order is load-bearing, not incidental.
        with pytest.raises(AssertionError, match="uq_events_espn_id"):
            _apply(repair.BEFORE, list(reversed(repair.MOVES)))

    def test_restore_walks_it_back_in_the_opposite_order(self):
        writes = _plan(repair.AFTER, restore=True)
        assert writes == [(G2, G2_ID, None), (G1, None, G2_ID)]
        assert _apply(repair.AFTER, writes) == repair.BEFORE

    def test_a_second_apply_writes_nothing(self):
        assert _plan(repair.AFTER) == []

    def test_restore_before_any_apply_writes_nothing(self):
        assert _plan(repair.BEFORE, restore=True) == []

    def test_an_anchor_already_on_game2_does_not_refuse(self):
        assert _plan(repair.BEFORE, anchored_to=[G2]) == list(repair.MOVES)

    def test_a_game2_kickoff_nudged_inside_three_hours_still_reads_as_game2(self):
        rows = _rows(repair.BEFORE)
        rows[G2] = ("2026-10-12T21:08:00+00:00", *rows[G2][1:])
        assert repair.plan(rows, [G1], [], restore=False) == list(repair.MOVES)


class TestRefusals:
    @pytest.mark.parametrize(
        "state",
        [
            # Something else stamped the Game 2 row: never ours to guess.
            {G1: G2_ID, G2: "401908099"},
            # A twin repair already cleared the Game 1 row.
            {G1: None, G2: None},
            # Game 1 was re-keyed to its own id by hand, Game 2 untouched.
            {G1: "401908030", G2: None},
        ],
    )
    def test_a_half_state_refuses_the_whole_run(self, state):
        with pytest.raises(repair.Refused, match="neither"):
            _plan(state)
        with pytest.raises(repair.Refused, match="neither"):
            _plan(state, restore=True)

    def test_an_unpinned_row_holding_the_game2_id_refuses(self):
        with pytest.raises(repair.Refused, match="unpinned"):
            _plan(repair.BEFORE, holders=[G1, 15399999])

    def test_an_anchor_binding_the_id_elsewhere_refuses(self):
        with pytest.raises(repair.Refused, match="anchor"):
            _plan(repair.BEFORE, anchored_to=[G1])

    def test_game1_kickoff_is_pinned_to_the_minute(self):
        rows = _rows(repair.BEFORE)
        rows[G1] = ("2026-10-12T00:01:00+00:00", *rows[G1][1:])
        with pytest.raises(repair.Refused, match="pinned"):
            repair.plan(rows, [G1], [], restore=False)

    def test_a_game2_kickoff_past_three_hours_refuses(self):
        rows = _rows(repair.BEFORE)
        rows[G2] = ("2026-10-13T00:01:00+00:00", *rows[G2][1:])
        with pytest.raises(repair.Refused, match="pinned"):
            repair.plan(rows, [G1], [], restore=False)

    def test_swapped_orientation_refuses(self):
        rows = _rows(repair.BEFORE)
        rows[G2] = (rows[G2][0], rows[G2][2], rows[G2][1], rows[G2][3])
        with pytest.raises(repair.Refused, match="pinned"):
            repair.plan(rows, [G1], [], restore=False)

    def test_a_missing_row_refuses(self):
        rows = _rows(repair.BEFORE)
        del rows[G2]
        with pytest.raises(repair.Refused, match="missing"):
            repair.plan(rows, [G1], [], restore=False)

    def test_it_refuses_off_production(self):
        with pytest.raises(repair.Refused):
            repair.refuse_unless_production({})
        with pytest.raises(repair.Refused):
            repair.refuse_unless_production({"HEROKU_APP_NAME": "bainluck-staging"})
        repair.refuse_unless_production({"HEROKU_APP_NAME": "bainluck"})
