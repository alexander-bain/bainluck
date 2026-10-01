"""#8126 — the capture consumer's licence, identity and poison controls.

Every capture here is PRODUCED, not hand-written: a venue-shaped Kalshi event body
goes through the producer's own ``classify_kalshi`` and ``_capture_row`` (PR #8120)
and is JSON round-tripped the way ``settlement_captures.raw_response`` stores it.
So a change to what the producer banks reddens this file instead of leaving the
consumer reading a shape that no longer exists. Malformed cases mutate a produced
capture; they never start from a blank dict.
"""

from __future__ import annotations

import copy
import json
from datetime import datetime, timedelta, timezone

import pytest

from app.services.settlement_sweep_runner import PROBE_PROTOCOL_VERSION, _capture_row
from app.utils.kalshi_market_status import NON_VERDICT_RESULTS
from app.utils.settlement_capture_consumer import (
    _LEG_KEYS,
    CONSUMED_PROTOCOL_VERSION,
    WRITE_RESOLUTION_SOURCE,
    CaptureRefused,
    CaptureRow,
    OutcomeRow,
    plan_writes,
    validate_capture,
)
from app.utils.settlement_sweep_plan import Candidate
from app.utils.settlement_truth import classify_kalshi

NOW = datetime(2026, 9, 30, 10, 40, tzinfo=timezone.utc)
MID = 60534962
BOARD = "KXNASDAQ100U-26AUG17H1200"
T1 = "KXNASDAQ100U-26AUG17H1200-T27999.99"
T2 = "KXNASDAQ100U-26AUG17H1200-T28249.99"
T3 = "KXNASDAQ100U-26AUG17H1200-T28499.99"


def venue_leg(ticker: str, status: str = "finalized", result: str = "no") -> dict:
    return {"ticker": ticker, "status": status, "result": result, "yes_bid": None}


def produce(
    legs: list[dict],
    *,
    cid: int = 107429,
    market_id: int = MID,
    at: datetime = NOW,
) -> CaptureRow:
    outcome = classify_kalshi(404, None, 200, {"event": {"event_ticker": BOARD}, "markets": legs})
    row = _capture_row(
        Candidate(market_id, "kalshi", BOARD, NOW - timedelta(days=40), "missing_winner"),
        outcome,
        sweep_id="kalshi-2026-09-30",
        now=NOW,
    )
    raw = json.loads(json.dumps(row["raw_response"])) if row["raw_response"] else None
    return CaptureRow(
        id=cid,
        market_id=row["market_id"],
        source=row["source"],
        protocol_version=row["protocol_version"],
        disposition=row["disposition"],
        winning_outcome=row["winning_outcome"],
        derived=(raw or {}).get("_derived"),
        captured_at=at,
    )


def outcome(
    oid: int,
    ext: str,
    *,
    market_id: int = MID,
    is_winner: bool | None = False,
    source: str | None = None,
    market_source: str = "kalshi",
) -> OutcomeRow:
    return OutcomeRow(oid, market_id, ext, is_winner, source, market_source)


BOARD_OUTCOMES = [outcome(1, T1), outcome(2, T2), outcome(3, T3)]


def mutate(capture: CaptureRow, fn) -> CaptureRow:
    derived = copy.deepcopy(capture.derived)
    fields = dict(capture.__dict__)
    fields["derived"] = derived
    fn(fields, derived)
    return CaptureRow(**fields)


class TestTheProducerContract:
    def test_the_producer_still_banks_protocol_2_legs_in_the_shape_read_here(self):
        c = produce([venue_leg(T1, result="yes"), venue_leg(T2)])
        assert PROBE_PROTOCOL_VERSION == CONSUMED_PROTOCOL_VERSION == c.protocol_version
        assert c.disposition == "settled_per_leg"
        assert c.derived["protocol_version"] == CONSUMED_PROTOCOL_VERSION
        assert all(set(leg) == _LEG_KEYS for leg in c.derived["legs"])


class TestAWinnerAndLosersReachTheBoard:
    def test_a_settled_multi_leg_board_writes_each_legs_own_verdict(self):
        c = produce([venue_leg(T1), venue_leg(T2, result="yes"), venue_leg(T3)])
        plan = plan_writes([c], BOARD_OUTCOMES)
        got = {(w.outcome_id, w.new_is_winner) for w in plan.writes}
        assert got == {(1, False), (2, True), (3, False)}
        assert {w.new_resolution_source for w in plan.writes} == {WRITE_RESOLUTION_SOURCE}
        assert {w.capture_id for w in plan.writes} == {107429}
        assert all(w.pre_resolution_source is None for w in plan.writes)
        assert plan.refused == {}

    def test_a_null_is_winner_with_no_source_is_ungraded_and_written(self):
        c = produce([venue_leg(T1, result="yes")])
        plan = plan_writes([c], [outcome(1, T1, is_winner=None)])
        assert [(w.outcome_id, w.pre_is_winner, w.new_is_winner) for w in plan.writes] == [
            (1, None, True)
        ]


class TestExactIdentityInsideTheCapturesOwnMarket:
    @pytest.mark.parametrize(
        "stored",
        [T1.lower(), T1 + " ", " " + T1, T1[:-3], BOARD, T1.replace("-T", "-t")],
    )
    def test_anything_but_the_exact_ticker_is_unmatched(self, stored):
        c = produce([venue_leg(T1, result="yes")])
        plan = plan_writes([c], [outcome(1, stored)])
        assert plan.writes == []
        assert plan.skipped["unmatched"] == [(MID, T1, "")]

    def test_the_same_ticker_on_another_market_is_never_written(self):
        c = produce([venue_leg(T1, result="yes")])
        plan = plan_writes([c], [outcome(9, T1, market_id=MID + 1)])
        assert plan.writes == []
        assert [s[1] for s in plan.skipped["unmatched"]] == [T1]

    def test_a_non_kalshi_market_is_refused(self):
        c = produce([venue_leg(T1, result="yes")])
        plan = plan_writes([c], [outcome(1, T1, market_source="polymarket")])
        assert plan.writes == []
        assert plan.skipped["market_not_kalshi"] == [(MID, T1, "polymarket")]

    def test_two_outcomes_with_one_ticker_are_ambiguous_and_the_siblings_still_write(self):
        c = produce([venue_leg(T1, result="yes"), venue_leg(T2)])
        plan = plan_writes([c], [outcome(1, T1), outcome(11, T1), outcome(2, T2)])
        assert [(w.outcome_id, w.new_is_winner) for w in plan.writes] == [(2, False)]
        assert plan.skipped["ambiguous_identity"] == [(MID, T1, "1,11")]


class TestSettledNoVerdictIsNeverGraded:
    def test_a_scalar_leg_writes_nothing_beside_a_graded_sibling(self):
        c = produce([venue_leg(T1, result="scalar"), venue_leg(T2, result="yes")])
        assert c.disposition == "settled_per_leg"
        plan = plan_writes([c], BOARD_OUTCOMES)
        assert [(w.outcome_id, w.new_is_winner) for w in plan.writes] == [(2, True)]
        assert plan.skipped["no_verdict"] == [(MID, T1, "")]

    def test_an_all_scalar_board_is_settled_and_writes_nothing(self):
        c = produce([venue_leg(T1, result="scalar"), venue_leg(T2, result="scalar")])
        assert c.disposition == "settled_per_leg"
        plan = plan_writes([c], BOARD_OUTCOMES)
        assert plan.writes == []
        assert len(plan.skipped["no_verdict"]) == 2

    def test_an_existing_grade_on_a_scalar_leg_is_surfaced_and_never_cleared(self):
        c = produce([venue_leg(T1, result="scalar")])
        plan = plan_writes([c], [outcome(1, T1, is_winner=False, source="api_settlement")])
        assert plan.writes == []
        assert plan.skipped["no_verdict_but_graded"] == [(MID, T1, "api_settlement")]


class TestTheBoardDispositionLicensesNothing:
    def test_a_partial_board_writes_its_settled_legs_and_not_its_open_ones(self):
        c = produce([venue_leg(T1, result="yes"), venue_leg(T2, status="active", result="")])
        assert c.disposition == "open_no_settlement"
        plan = plan_writes([c], BOARD_OUTCOMES)
        assert [(w.outcome_id, w.new_is_winner) for w in plan.writes] == [(1, True)]
        assert plan.skipped["not_declared"] == [(MID, T2, "")]


class TestPoison:
    def test_a_v1_scalar_capture_is_refused_as_a_type_not_a_verdict(self):
        v1 = CaptureRow(
            id=59742938,
            market_id=MID,
            source="kalshi",
            protocol_version=1,
            disposition="settled",
            winning_outcome="scalar",
            derived=None,
        )
        plan = plan_writes([v1], BOARD_OUTCOMES)
        assert plan.writes == []
        assert plan.refused == {59742938: "non_verdict_winning_outcome"}

    @pytest.mark.parametrize("word", sorted(NON_VERDICT_RESULTS) + ["SCALAR", " scalar "])
    def test_every_non_verdict_word_is_refused_whatever_the_protocol(self, word):
        for pv in (1, 2):
            c = CaptureRow(1, MID, "kalshi", pv, "settled", word, None)
            with pytest.raises(CaptureRefused) as exc:
                validate_capture(c)
            assert exc.value.code == "non_verdict_winning_outcome"

    def test_a_v1_board_with_perfect_legs_is_still_refused(self):
        c = produce([venue_leg(T1, result="yes")])
        v1 = mutate(c, lambda f, d: f.update(protocol_version=1))
        plan = plan_writes([v1], BOARD_OUTCOMES)
        assert plan.writes == []
        assert plan.refused == {107429: "not_protocol_2"}


def _set_leg(i, key, value):
    def fn(fields, derived):
        derived["legs"][i][key] = value

    return fn


MALFORMED = {
    "protocol_true": (lambda f, d: f.update(protocol_version=True), "not_protocol_2"),
    "protocol_str": (lambda f, d: f.update(protocol_version="2"), "not_protocol_2"),
    "polymarket": (lambda f, d: f.update(source="polymarket"), "not_kalshi"),
    "purged_board": (lambda f, d: f.update(disposition="purged"), "board_disposition_bears_no_legs"),
    "settled_board": (
        lambda f, d: f.update(disposition="settled"),
        "board_disposition_bears_no_legs",
    ),
    "winning_outcome": (
        lambda f, d: f.update(winning_outcome="yes"),
        "leg_board_carries_winning_outcome",
    ),
    "no_derived": (lambda f, d: f.update(derived=None), "derived_missing"),
    "derived_list": (lambda f, d: f.update(derived=[]), "derived_missing"),
    "derived_v1": (lambda f, d: d.update(protocol_version=1), "derived_not_protocol_2"),
    "legs_empty": (lambda f, d: d.update(legs=[]), "legs_malformed"),
    "legs_dict": (lambda f, d: d.update(legs={}), "legs_malformed"),
    "leg_not_dict": (lambda f, d: d["legs"].append("x"), "leg_malformed"),
    "leg_extra_key": (_set_leg(0, "name", "Yes"), "leg_malformed"),
    "leg_missing_key": (lambda f, d: d["legs"][0].pop("is_winner"), "leg_malformed"),
    "winner_str": (_set_leg(0, "is_winner", "true"), "leg_malformed"),
    "winner_int": (_set_leg(0, "is_winner", 1), "leg_malformed"),
    "settled_none": (_set_leg(0, "is_winner", None), "leg_malformed"),
    "scalar_with_winner": (_set_leg(1, "is_winner", False), "leg_malformed"),
    "unknown_disposition": (_set_leg(0, "disposition", "won"), "leg_malformed"),
    "ticker_padded": (_set_leg(0, "external_id", T1 + " "), "leg_malformed"),
    "ticker_empty": (_set_leg(0, "external_id", ""), "leg_malformed"),
    "ticker_int": (_set_leg(0, "external_id", 7), "leg_malformed"),
    "duplicate_ticker": (_set_leg(2, "external_id", T1), "duplicate_leg_identity"),
    "open_leg_on_settled_board": (
        lambda f, d: d["legs"][1].update(disposition="open_no_settlement", is_winner=None),
        "board_leg_disposition_conflict",
    ),
}


class TestMalformedEvidenceRefusesTheWholeCapture:
    @pytest.mark.parametrize("case", sorted(MALFORMED))
    def test_refused_and_no_sibling_leg_is_written(self, case):
        fn, code = MALFORMED[case]
        good = produce(
            [venue_leg(T1, result="yes"), venue_leg(T2, result="scalar"), venue_leg(T3)]
        )
        assert len(plan_writes([good], BOARD_OUTCOMES).writes) == 2  # the control
        bad = mutate(good, fn)
        plan = plan_writes([bad], BOARD_OUTCOMES)
        assert plan.writes == []
        assert plan.refused == {107429: code}


class TestReProbes:
    def test_two_captures_that_disagree_fail_closed(self):
        a = produce([venue_leg(T1, result="yes")], cid=1, at=NOW - timedelta(days=1))
        b = produce([venue_leg(T1, result="no")], cid=2)
        plan = plan_writes([a, b], BOARD_OUTCOMES)
        assert plan.writes == []
        assert plan.skipped["conflict_across_captures"] == [(MID, T1, "1,2")]

    def test_settled_then_still_trading_fails_closed(self):
        a = produce([venue_leg(T1, result="yes")], cid=1, at=NOW - timedelta(days=1))
        b = produce([venue_leg(T1, status="active", result="")], cid=2)
        assert plan_writes([a, b], BOARD_OUTCOMES).writes == []

    def test_a_verdict_and_a_no_verdict_for_one_leg_fail_closed(self):
        a = produce([venue_leg(T1, result="yes")], cid=1)
        b = produce([venue_leg(T1, result="scalar")], cid=2, at=NOW - timedelta(days=1))
        assert plan_writes([a, b], BOARD_OUTCOMES).writes == []

    def test_trading_then_settled_is_the_normal_progression(self):
        a = produce([venue_leg(T1, status="active", result="")], cid=1, at=NOW - timedelta(days=1))
        b = produce([venue_leg(T1, result="yes")], cid=2)
        plan = plan_writes([b, a], BOARD_OUTCOMES)
        assert [(w.outcome_id, w.new_is_winner, w.capture_id) for w in plan.writes] == [
            (1, True, 2)
        ]

    def test_agreeing_captures_write_once_from_the_newest(self):
        a = produce([venue_leg(T1, result="yes")], cid=1, at=NOW - timedelta(days=1))
        b = produce([venue_leg(T1, result="yes")], cid=2)
        plan = plan_writes([a, b], BOARD_OUTCOMES)
        assert [(w.outcome_id, w.capture_id) for w in plan.writes] == [(1, 2)]

    def test_a_refused_re_probe_is_not_evidence_either_way(self):
        a = produce([venue_leg(T1, result="yes")], cid=1)
        b = mutate(produce([venue_leg(T1, result="no")], cid=2), _set_leg(0, "is_winner", "no"))
        plan = plan_writes([a, b], BOARD_OUTCOMES)
        assert [(w.outcome_id, w.new_is_winner) for w in plan.writes] == [(1, True)]
        assert plan.refused == {2: "leg_malformed"}


class TestIncumbentGrades:
    def test_an_agreeing_grade_is_left_alone(self):
        c = produce([venue_leg(T1, result="yes")])
        plan = plan_writes([c], [outcome(1, T1, is_winner=True, source="box_score")])
        assert plan.writes == []
        assert plan.skipped["already_graded_agrees"] == [(MID, T1, "box_score")]

    @pytest.mark.parametrize("source", ["api_settlement", "box_score", "pass2_guess"])
    def test_a_disagreeing_grade_is_a_conflict_and_never_overwritten(self, source):
        c = produce([venue_leg(T1, result="yes")])
        plan = plan_writes([c], [outcome(1, T1, is_winner=False, source=source)])
        assert plan.writes == []
        assert plan.skipped["conflicts_existing_grade"] == [(MID, T1, f"{source}:False->True")]

    def test_true_with_no_source_is_not_the_default_and_is_not_overwritten_by_a_loss(self):
        c = produce([venue_leg(T1, result="no")])
        plan = plan_writes([c], [outcome(1, T1, is_winner=True, source=None)])
        assert plan.writes == []
        assert plan.skipped["conflicts_existing_grade"] == [(MID, T1, "NULL:True->False")]

    def test_true_with_no_source_and_a_winning_verdict_gains_its_source(self):
        c = produce([venue_leg(T1, result="yes")])
        plan = plan_writes([c], [outcome(1, T1, is_winner=True, source=None)])
        assert [(w.pre_is_winner, w.new_is_winner) for w in plan.writes] == [(True, True)]


def test_tallies_name_every_bucket():
    c = produce([venue_leg(T1, result="yes"), venue_leg(T2, result="scalar"), venue_leg(T3)])
    t = plan_writes([c], BOARD_OUTCOMES).tallies()
    assert t == {
        "writes": 2,
        "writes_winner": 1,
        "writes_loser": 1,
        "refused_captures": {},
        "skipped_legs": {"no_verdict": 1},
    }
