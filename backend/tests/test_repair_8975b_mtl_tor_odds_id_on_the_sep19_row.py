"""#8975 (second anchor) — Tuesday's Canadiens @ Maple Leafs sportsbook id sits on the finished Sep 19 row.

Production 2026-09-28: 15168032 (MTL @ TOR, Sep 19, final 1–4) holds Odds API
id 485b2953…, and every sportsbook line for Tuesday's game — priced daily for
nine days after the Sep 19 final — is written there; the served Sep 29 row
15317562 holds no id and blends without sportsbooks. ``external_id`` is
UNIQUE, so the id cannot reach 15317562 while the Sep 19 row holds it. These
tests pin the move's order, its all-or-nothing state machine and its refusals.
"""

from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(__file__)), "scripts"))

import repair_8975b_mtl_tor_odds_id_on_the_sep19_row as repair  # noqa: E402

SEP19, SEP29 = repair.SEP19_ROW, repair.SEP29_ROW
XID = repair.SEP29_ODDS_ID


def _rows(state: dict) -> dict:
    return {e: (*repair.PINNED[e], state[e]) for e in repair.PINNED}


def _holders(state: dict) -> list[int]:
    return sorted(e for e, xid in state.items() if xid == XID)


def _plan(state: dict, *, restore: bool = False, holders: list[int] | None = None):
    return repair.plan(
        _rows(state), _holders(state) if holders is None else holders, restore=restore
    )


def _apply(state: dict, writes) -> dict:
    """Walk the writes one statement at a time, enforcing the unique constraint."""
    state = dict(state)
    for event_id, old, new in writes:
        assert state[event_id] == old
        if new is not None:
            assert new not in {v for k, v in state.items() if k != event_id}, (
                f"events.external_id UNIQUE: {new} still held when written to {event_id}"
            )
        state[event_id] = new
    return state


class TestTheManifest:
    def test_the_specimen(self):
        assert XID == "485b295347cb22f002e014cb87813ed7"
        assert repair.BEFORE == {15168032: XID, 15317562: None}
        assert repair.AFTER == {15168032: None, 15317562: XID}

    def test_the_rows_are_the_same_two_the_espn_repair_pinned(self):
        # The first #8975 repair already vouched for these two rows' identity;
        # this one moves the other anchor between the SAME two rows.
        import repair_8975_mtl_tor_espn_id_on_the_sep19_row as espn_repair

        assert repair.PINNED == espn_repair.PINNED

    def test_it_writes_no_other_column(self):
        # The banked snapshots stay put; only the id moves.
        import inspect

        src = inspect.getsource(repair.run)
        assert "UPDATE events SET external_id = :new " in src
        for fn in (repair.run, repair._read, repair._backup):
            assert "odds_snapshots" not in inspect.getsource(fn)


class TestTheMove:
    def test_apply_moves_the_id_in_an_order_the_unique_constraint_allows(self):
        writes = _plan(repair.BEFORE)
        assert writes == [(SEP19, XID, None), (SEP29, None, XID)]
        assert _apply(repair.BEFORE, writes) == repair.AFTER

    def test_the_reverse_order_would_violate_the_unique_constraint(self):
        # Control: the order is load-bearing, not incidental.
        with pytest.raises(AssertionError, match="UNIQUE"):
            _apply(repair.BEFORE, list(reversed(repair.MOVES)))

    def test_restore_walks_it_back_in_the_opposite_order(self):
        writes = _plan(repair.AFTER, restore=True)
        assert writes == [(SEP29, XID, None), (SEP19, None, XID)]
        assert _apply(repair.AFTER, writes) == repair.BEFORE

    def test_a_second_apply_writes_nothing(self):
        assert _plan(repair.AFTER) == []

    def test_restore_before_any_apply_writes_nothing(self):
        assert _plan(repair.BEFORE, restore=True) == []


class TestRefusals:
    @pytest.mark.parametrize(
        "state",
        [
            # The poll stamped the Sep 29 row with some other listing: never ours to guess.
            {SEP19: XID, SEP29: "ffffffffffffffffffffffffffffffff"},
            # Someone cleared both rows.
            {SEP19: None, SEP29: None},
        ],
    )
    def test_a_half_state_refuses_the_whole_run(self, state):
        with pytest.raises(repair.Refused, match="neither"):
            _plan(state)
        with pytest.raises(repair.Refused, match="neither"):
            _plan(state, restore=True)

    def test_an_unpinned_row_holding_the_id_refuses(self):
        with pytest.raises(repair.Refused, match="unpinned"):
            _plan(repair.BEFORE, holders=[15319504])

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
