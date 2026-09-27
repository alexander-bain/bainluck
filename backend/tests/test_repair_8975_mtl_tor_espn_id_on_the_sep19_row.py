"""#8975 — Tuesday's Canadiens @ Maple Leafs id sits on the finished Sep 19 row.

Production 2026-09-27: 15168032 (MTL @ TOR, Sep 19, final 1–4) holds ESPN
401891827, which ESPN's own summary names as the Sep 29 game; the served Sep 29
row 15317562 holds nothing and cannot take the id while the unique index holds
it on the Sep 19 row. These tests pin the move's order, its all-or-nothing
state machine and its refusals.
"""

from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(__file__)), "scripts"))

import repair_8975_mtl_tor_espn_id_on_the_sep19_row as repair  # noqa: E402

SEP19, SEP29 = repair.SEP19_ROW, repair.SEP29_ROW


def _rows(state: dict) -> dict:
    return {e: (*repair.PINNED[e], state[e]) for e in repair.PINNED}


def _holders(state: dict) -> dict:
    out: dict = {}
    for e, eid in state.items():
        if eid is not None:
            out.setdefault(eid, []).append(e)
    return out


def _plan(state: dict, *, restore: bool = False, holders: dict | None = None):
    return repair.plan(
        _rows(state), _holders(state) if holders is None else holders, restore=restore
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
        assert repair.BEFORE == {15168032: "401891827", 15317562: None}
        assert repair.AFTER == {15168032: "401881922", 15317562: "401891827"}

    def test_the_rows_read_as_the_two_games_espn_names(self):
        assert repair.PINNED[SEP19][0].startswith("2026-09-19T23:00")
        assert repair.PINNED[SEP29][0].startswith("2026-09-29T23:00")
        for _k, home, away in repair.PINNED.values():
            assert "Toronto" in home and away.startswith("Montr")


class TestTheMove:
    def test_apply_moves_both_ids_in_an_order_the_unique_index_allows(self):
        writes = _plan(repair.BEFORE)
        assert writes == [
            (SEP19, "401891827", "401881922"),
            (SEP29, None, "401891827"),
        ]
        assert _apply(repair.BEFORE, writes) == repair.AFTER

    def test_the_reverse_order_would_violate_the_unique_index(self):
        # Control: the order is load-bearing, not incidental.
        with pytest.raises(AssertionError, match="uq_events_espn_id"):
            _apply(repair.BEFORE, list(reversed(repair.MOVES)))

    def test_restore_walks_it_back_in_the_opposite_order(self):
        writes = _plan(repair.AFTER, restore=True)
        assert writes == [
            (SEP29, "401891827", None),
            (SEP19, "401881922", "401891827"),
        ]
        assert _apply(repair.AFTER, writes) == repair.BEFORE

    def test_a_second_apply_writes_nothing(self):
        assert _plan(repair.AFTER) == []

    def test_restore_before_any_apply_writes_nothing(self):
        assert _plan(repair.BEFORE, restore=True) == []


class TestRefusals:
    @pytest.mark.parametrize(
        "state",
        [
            # The backfill stamped the Sep 29 row from somewhere else: never ours to guess.
            {SEP19: "401891827", SEP29: "401899999"},
            # Someone already moved the Sep 19 row but not the Sep 29 one.
            {SEP19: "401881922", SEP29: None},
            # A twin repair cleared the Sep 19 row.
            {SEP19: None, SEP29: None},
        ],
    )
    def test_a_half_state_refuses_the_whole_run(self, state):
        with pytest.raises(repair.Refused, match="neither"):
            _plan(state)
        with pytest.raises(repair.Refused, match="neither"):
            _plan(state, restore=True)

    def test_an_unpinned_row_holding_the_sep19_id_refuses(self):
        holders = {"401891827": [SEP19], "401881922": [15311331]}
        with pytest.raises(repair.Refused, match="unpinned"):
            _plan(repair.BEFORE, holders=holders)

    def test_a_row_that_no_longer_reads_as_its_game_refuses(self):
        rows = _rows(repair.BEFORE)
        rows[SEP29] = ("2026-09-30T23:00:00+00:00", *rows[SEP29][1:])
        with pytest.raises(repair.Refused, match="pinned"):
            repair.plan(rows, _holders(repair.BEFORE), restore=False)

    def test_a_missing_row_refuses(self):
        rows = _rows(repair.BEFORE)
        del rows[SEP29]
        with pytest.raises(repair.Refused, match="missing"):
            repair.plan(rows, _holders(repair.BEFORE), restore=False)

    def test_it_refuses_off_production(self):
        with pytest.raises(repair.Refused):
            repair.refuse_unless_production({})
        with pytest.raises(repair.Refused):
            repair.refuse_unless_production({"HEROKU_APP_NAME": "bainluck-staging"})
        repair.refuse_unless_production({"HEROKU_APP_NAME": "bainluck"})
