"""#10182 — the repair that reopens Polymarket boards the venue still trades.

Production 2026-10-02: the resolve sync closed boards for which we hold only the
venue-closed slice of a negRisk field (World Series Exact Matchup /futures/63490287:
16 of 37 legs, all eliminated; Korn Ferry Winner: 2 of 113). PR #10183 stops new
cases. These tests pin the per-board planner the repair writes from: the witness
it shares with that guard, the venue verdicts it keeps, the derived stamps it
clears, and every refusal. The SQL's real behaviour (savepoints, CAS, drift,
undo) is in ``tests/integration/test_repair_polymarket_false_parent_settlements_10182_pg.py``.
"""

from __future__ import annotations

import os
import sys
from datetime import datetime, timezone

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(__file__)), "scripts"))

import repair_polymarket_false_parent_settlements_10182 as repair  # noqa: E402

from app.utils import polymarket_settlement_scan  # noqa: E402

WS_ID, WS_EVENT = repair.SPECIMEN
SETTLED_AT = datetime(2026, 10, 1, 11, 30, 36, 73033, tzinfo=timezone.utc)
SYNC_GATE = {
    "at": "2026-10-01T11:30:36.019860+00:00",
    "task": "sync_polymarket_resolved_status",
    "proof_kind": "winner",
}


def _cid(n: int) -> str:
    return "0x" + f"{n:064x}"


def _venue(event_id=WS_EVENT, *, closed=False, legs=()):
    """A Gamma ``/events/{id}`` payload. ``legs``: ``(n, closed, outcomePrices)``."""
    return {
        "id": event_id,
        "closed": closed,
        "markets": [
            {"conditionId": _cid(n), "closed": c, "outcomePrices": prices}
            for n, c, prices in legs
        ],
    }


def _market(**over):
    m = {
        "id": WS_ID,
        "source": "polymarket",
        "external_id": WS_EVENT,
        "name": "MLB Playoffs: World Series Exact Matchup",
        "status": "resolved",
        "settled_at": SETTLED_AT,
        "polymarket_event_id": WS_EVENT,
        "group_id": f"polymarket:{WS_EVENT}",
        "gate": dict(SYNC_GATE),
    }
    m.update(over)
    return m


def _leg(oid, n, *, w=False, src="api_settlement", suffix="", price="default"):
    if price == "default":
        price = None if w is None else (1.0 if w else 0.0)
    return {
        "id": oid,
        "external_id": _cid(n) + suffix,
        "is_winner": w,
        "resolution_source": src,
        "current_probability": price,
    }


#: The specimen's shape: 20 legs closed and resolved No, 17 still trading; we
#: store 16 of the closed ones, each re-stamped ``all_losers`` by Pass 4.
WS_VENUE = _venue(
    legs=[(n, True, '["0", "1"]') for n in range(20)]
    + [(n, False, '["0.02", "0.98"]') for n in range(20, 37)]
)
WS_LEGS = [_leg(1000 + n, n, src="all_losers") for n in range(16)]


def plan(market=None, legs=None, venue=None, candidate=repair.SPECIMEN):
    return repair.plan_market(
        candidate,
        _market() if market is None else market,
        WS_LEGS if legs is None else legs,
        WS_VENUE if venue is None else venue,
    )


class TestTheManifest:
    def test_the_specimen_leads_and_the_cohort_is_pinned(self):
        assert repair.SPECIMEN == (63490287, "1110298")
        assert repair.CANDIDATES[0] == repair.SPECIMEN
        assert len(repair.CANDIDATES) == 22
        ids = [m for m, _ in repair.CANDIDATES]
        events = [e for _, e in repair.CANDIDATES]
        assert len(set(ids)) == len(ids) and len(set(events)) == len(events)
        assert all(e.isdigit() for e in events)
        # The Korn Ferry Winner board the after-check photographed.
        assert (63049616, "1098408") in repair.CANDIDATES

    def test_the_nlcs_board_is_pinned(self):
        # Closed 2026-09-12, before the guard; found 2026-10-03 outside the cohort.
        assert (60087227, "956265") in repair.CANDIDATES
        assert repair._selected([60087227]) == [(60087227, "956265")]

    def test_the_nlcs_shape_reopens_with_its_one_eliminated_leg_promoted(self):
        # Gamma 956265, read 2026-10-03: not negRisk (two teams advance), 15 legs,
        # 11 closed at ["0", "1"], 4 trading. We store only the Rockies, which
        # Pass 4 stamped all_losers at 0.0. Promoted, it can no longer feed
        # #6919's stored-legs-only deferred close.
        mid, eid = 60087227, "956265"
        venue = _venue(
            eid,
            legs=[(n, True, '["0", "1"]') for n in range(11)]
            + [(11, False, '["0.695", "0.305"]'), (12, False, '["0.635", "0.365"]'),
               (13, False, '["0.385", "0.615"]'), (14, False, '["0.325", "0.675"]')],
        )
        market = _market(
            id=mid, external_id=eid, name="MLB Playoffs: Team to advance to NLCS",
            polymarket_event_id=eid, group_id=f"polymarket:{eid}",
        )
        p = repair.plan_market((mid, eid), market, [_leg(224051322, 3, src="all_losers")], venue)
        assert p.verdict == repair.REOPEN, p.reason
        assert p.promote_legs == [(224051322, _cid(3), False, "all_losers", 0.0)]
        assert p.clear_legs == [] and p.legs_preserved == 0
        assert p.venue == {"event_closed": False, "open_legs": 4, "closed_legs": 11, "stored_legs": 1}

    def test_the_witness_is_read_by_the_guards_own_helper(self):
        # One reader of venue truth for the guard and its repair, never a second copy.
        assert repair.settled_legs is polymarket_settlement_scan.settled_legs

    def test_only_refuses_an_unpinned_id(self):
        assert repair._selected([WS_ID]) == [repair.SPECIMEN]
        with pytest.raises(repair.Refused):
            repair._selected([12345])

    def test_refuses_outside_production(self):
        with pytest.raises(repair.Refused):
            repair.refuse_unless_production({})
        with pytest.raises(repair.Refused):
            repair.refuse_unless_production({"HEROKU_APP_NAME": "bainluck-staging"})
        repair.refuse_unless_production({"HEROKU_APP_NAME": "bainluck"})


class TestPartialNegRiskField:
    def test_the_specimen_reopens_and_keeps_every_eliminated_matchup(self):
        p = plan()
        assert p.verdict == repair.REOPEN, p.reason
        # all_losers on a venue-CLOSED leg resolved No carries the venue's own
        # answer: its value is kept and only its label is promoted, never cleared.
        assert p.clear_legs == []
        assert p.legs_preserved == 0
        assert p.promote_legs == [
            (1000 + n, _cid(n), False, "all_losers", 0.0) for n in range(16)
        ]
        assert p.venue == {
            "event_closed": False, "open_legs": 17, "closed_legs": 20, "stored_legs": 16,
        }
        d = p.as_dict()
        assert d["before"]["status"] == "resolved"
        assert d["before"][repair.GATE_KEY]["task"] == repair.SYNC_TASK
        assert d["after"] == {"status": "open", "settled_at": None, repair.GATE_KEY: None}

    def test_the_cure_turns_on_the_venues_open_legs_not_on_ours(self):
        # Control: the identical stored board, venue now reporting every leg closed.
        all_closed = _venue(legs=[(n, True, '["0", "1"]') for n in range(37)])
        assert plan(venue=all_closed).verdict == repair.SKIP_NO_WITNESS


class TestStillValidClosedLegs:
    VENUE = _venue(
        legs=[(1, True, '["1", "0"]'), (2, True, '["0", "1"]'), (3, False, '["0.4", "0.6"]')]
    )

    def test_a_venue_winner_and_loser_are_both_kept(self):
        legs = [_leg(1, 1, w=True), _leg(2, 2, w=False)]
        p = plan(legs=legs, venue=self.VENUE)
        assert p.verdict == repair.REOPEN, p.reason
        assert p.legs_preserved == 2 and p.clear_legs == []

    def test_a_no_side_leg_is_graded_against_the_complement(self):
        legs = [_leg(1, 1, w=False, suffix="_no"), _leg(2, 2, w=True, suffix="_no")]
        p = plan(legs=legs, venue=self.VENUE)
        assert p.verdict == repair.REOPEN, p.reason
        assert p.legs_preserved == 2

    def test_an_ungraded_closed_leg_is_left_alone(self):
        p = plan(legs=[_leg(2, 2, w=None, src=None)], venue=self.VENUE)
        assert p.verdict == repair.REOPEN and p.legs_preserved == 1

    def test_a_closed_leg_contradicting_the_venue_refuses_the_board(self):
        p = plan(legs=[_leg(1, 1, w=False)], venue=self.VENUE)
        assert p.verdict == repair.REFUSED and "contradicts the venue" in p.reason

    def test_a_graded_closed_leg_without_a_terminal_price_refuses(self):
        venue = _venue(legs=[(1, True, '["0.5", "0.5"]'), (3, False, '["0.4", "0.6"]')])
        p = plan(legs=[_leg(1, 1, w=False)], venue=venue)
        assert p.verdict == repair.REFUSED and "no terminal price" in p.reason


class TestPromotion:
    """A derived stamp on a venue-closed leg becomes the venue's own label."""

    VENUE = _venue(legs=[(1, True, '["1", "0"]'), (2, True, '["0", "1"]'), (3, False, '["0.4", "0.6"]')])

    def test_a_derived_winner_is_promoted_at_its_terminal_price(self):
        p = plan(legs=[_leg(1, 1, w=True, src="clean_resolution")], venue=self.VENUE)
        assert p.verdict == repair.REOPEN, p.reason
        assert p.promote_legs == [(1, _cid(1), True, "clean_resolution", 1.0)]

    def test_a_venue_label_already_in_place_is_not_rewritten(self):
        p = plan(legs=[_leg(2, 2, w=False, src="api_settlement")], venue=self.VENUE)
        assert p.promote_legs == [] and p.legs_preserved == 1

    @pytest.mark.parametrize("price", [None, 0.01, 0.5])
    def test_a_derived_stamp_off_the_terminal_price_refuses(self, price):
        # Promoting it would leave an api_settlement leg carrying a live-looking
        # price — #5246's defect, written by a repair.
        p = plan(legs=[_leg(2, 2, w=False, src="all_losers", price=price)], venue=self.VENUE)
        assert p.verdict == repair.REFUSED and "terminal" in p.reason

    def test_the_promotion_writes_only_the_label_and_cas_on_the_price(self):
        sql = str(repair._PROMOTE_LEG)
        set_clause = sql.split(" SET ", 1)[1].split(" WHERE ", 1)[0]
        assert {c.split("=")[0].strip() for c in set_clause.split(", ")} == {
            "resolution_source", "last_updated",
        }
        assert "resolution_source = 'api_settlement'" in set_clause
        where = sql.split(" WHERE ", 1)[1]
        for g in (
            "id = :oid", "market_id = :mid", "external_id = :ext", "is_winner = :w",
            "resolution_source = :src", "current_probability = CAST(:price AS numeric)",
        ):
            assert g in where, g


class TestStampsOnALegTheVenueStillTrades:
    VENUE = _venue(legs=[(1, True, '["0", "1"]'), (2, False, '["0.3", "0.7"]')])

    @pytest.mark.parametrize("src", sorted(repair.DERIVED_SOURCES))
    def test_a_derived_stamp_is_cleared(self, src):
        legs = [_leg(1, 1), _leg(22, 2, w=False, src=src, price=0.3)]
        p = plan(legs=legs, venue=self.VENUE)
        assert p.verdict == repair.REOPEN, p.reason
        assert p.clear_legs == [(22, _cid(2), False, src)]
        assert p.legs_preserved == 1

    @pytest.mark.parametrize("src", ["api_settlement", "clob_resolve", None])
    def test_any_other_verdict_refuses_the_board(self, src):
        p = plan(legs=[_leg(22, 2, w=False, src=src)], venue=self.VENUE)
        assert p.verdict == repair.REFUSED and "still trades it" in p.reason

    def test_an_ungraded_open_leg_is_fine(self):
        p = plan(legs=[_leg(22, 2, w=None, src=None)], venue=self.VENUE)
        assert p.verdict == repair.REOPEN and p.clear_legs == []


class TestNoWitness:
    def test_every_leg_closed_on_an_open_event_is_no_witness(self):
        venue = _venue(legs=[(n, True, '["0", "1"]') for n in range(16)])
        p = plan(venue=venue)
        assert p.verdict == repair.SKIP_NO_WITNESS and "no open leg" in p.reason

    def test_a_closed_event_with_a_lingering_open_leg_is_no_witness(self):
        # The guard's own rule (#10183): event_closed beats a stray open leg.
        venue = _venue(
            closed=True,
            legs=[(n, True, '["0", "1"]') for n in range(16)] + [(99, False, '["0.5", "0.5"]')],
        )
        p = plan(venue=venue)
        assert p.verdict == repair.SKIP_NO_WITNESS and "event closed" in p.reason

    def test_an_unreadable_venue_refuses(self):
        p = repair.plan_market(repair.SPECIMEN, _market(), WS_LEGS, None)
        assert p.verdict == repair.REFUSED and "venue unreadable" in p.reason

    def test_a_payload_with_no_event_id_refuses(self):
        venue = dict(WS_VENUE)
        venue.pop("id")
        assert plan(venue=venue).verdict == repair.REFUSED


class TestWrongIdentity:
    @pytest.mark.parametrize(
        "over",
        [
            {"source": "kalshi"},
            {"external_id": "1110299"},
            {"polymarket_event_id": "1110299"},
            {"group_id": "polymarket:1110299"},
        ],
    )
    def test_a_row_that_is_no_longer_the_pinned_board_refuses(self, over):
        p = plan(market=_market(**over))
        assert p.verdict == repair.REFUSED and "identity drift" in p.reason

    def test_absent_event_id_keys_are_not_a_contradiction(self):
        p = plan(market=_market(polymarket_event_id=None, group_id=None))
        assert p.verdict == repair.REOPEN

    def test_the_venue_answering_for_another_event_refuses(self):
        venue = dict(WS_VENUE, id="1110299")
        p = plan(venue=venue)
        assert p.verdict == repair.REFUSED and "venue answered event" in p.reason

    def test_a_stored_leg_that_is_not_on_the_venue_event_refuses(self):
        p = plan(legs=WS_LEGS + [_leg(9999, 4242)])
        assert p.verdict == repair.REFUSED and "not on venue event" in p.reason

    def test_a_missing_row_refuses(self):
        p = repair.plan_market(repair.SPECIMEN, None, [], WS_VENUE)
        assert p.verdict == repair.REFUSED


class TestState:
    def test_an_already_reopened_board_is_a_noop(self):
        p = plan(market=_market(status="open", settled_at=None, gate=None))
        assert p.verdict == repair.NOOP

    def test_open_but_still_carrying_a_gate_refuses(self):
        p = plan(market=_market(status="open", settled_at=None))
        assert p.verdict == repair.REFUSED and "state drift" in p.reason

    def test_another_writers_resolution_is_not_undone(self):
        gate = dict(SYNC_GATE, task="backfill_winners")
        p = plan(market=_market(gate=gate))
        assert p.verdict == repair.REFUSED and "another writer" in p.reason
        assert plan(market=_market(gate=None)).verdict == repair.REFUSED

    def test_resolved_without_settled_at_refuses(self):
        assert plan(market=_market(settled_at=None)).verdict == repair.REFUSED

    def test_an_unexpected_status_refuses(self):
        assert plan(market=_market(status="closed")).verdict == repair.REFUSED


class TestTheStatements:
    def _set_cols(self, stmt):
        sql = str(stmt)
        set_clause = sql.split(" SET ", 1)[1].split(" WHERE ", 1)[0].split(" FROM ", 1)[0]
        return {c.split("=")[0].strip().split(".")[-1] for c in set_clause.split(", ")}

    def test_the_reopen_writes_only_the_parent_state(self):
        assert self._set_cols(repair._REOPEN) == {"status", "settled_at", "market_metadata"}
        assert "market_metadata - 'resolution_gate'" in str(repair._REOPEN)

    def test_the_reopen_compare_and_swaps_on_everything_it_read(self):
        where = str(repair._REOPEN).split(" WHERE ", 1)[1]
        for g in (
            "id = :mid", "source = 'polymarket'", "external_id = :ext",
            "status = 'resolved'", "settled_at = :settled_at",
            "market_metadata->'resolution_gate' = CAST(:gate AS jsonb)",
        ):
            assert g in where, g

    def test_the_leg_clear_writes_only_the_verdict_and_cas_on_it(self):
        assert self._set_cols(repair._CLEAR_LEG) == {
            "is_winner", "resolution_source", "last_updated",
        }
        where = str(repair._CLEAR_LEG).split(" WHERE ", 1)[1]
        for g in (
            "id = :oid", "market_id = :mid", "external_id = :ext",
            "is_winner IS NOT DISTINCT FROM :w", "resolution_source = :src",
        ):
            assert g in where, g
        assert "current_probability" not in str(repair._CLEAR_LEG)

    def test_the_restore_only_lands_on_the_exact_after_state(self):
        where = str(repair._RESTORE_MARKET).split(" WHERE ", 1)[1]
        for g in (
            "fm.status = 'open'", "fm.settled_at IS NULL",
            "fm.market_metadata->'resolution_gate' IS NULL",
        ):
            assert g in where, g
        legs = str(repair._RESTORE_LEGS).split(" WHERE ", 1)[1]
        assert "fo.is_winner IS NULL AND fo.resolution_source IS NULL" in legs
