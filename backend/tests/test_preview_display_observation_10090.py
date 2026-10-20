"""Disposable chart endpoints carry evidence time, never retry time."""
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from app.utils.blend_preview import PreviewRegistry
from app.utils.aggregation import compute_aggregate_probability, stamp_source_reading

T = datetime(2026, 10, 20, 12, tzinfo=timezone.utc)
EVENT = SimpleNamespace(status="live", espn_win_prob_home=None,
                        opening_home_probability=None)
BASE = {"kalshi": {"value": 0.4, "updated_at": (T - timedelta(seconds=10)).isoformat()}}


def propose(reg, basis, *, at=T, base=BASE, rev=1, value=0.7):
    return reg.propose(1, "polymarket", value=value, event=EVENT,
                       row_sources=base, row_rev=rev, observed_basis=basis,
                       stamped_at=at)[0]


def test_identical_evidence_retry_does_not_move_chart_but_preserves_weighting():
    reg = PreviewRegistry(epoch=1)
    basis = {"1": T.timestamp(), "2": (T + timedelta(seconds=1)).timestamp()}
    first = propose(reg, basis)
    later = T + timedelta(seconds=30)
    retry = propose(reg, basis, at=later)
    assert first["display_observed_at"] == retry["display_observed_at"] == T.isoformat()
    assert first["observed_at"] != retry["observed_at"]  # unchanged legacy clock
    expected_bag = stamp_source_reading(BASE, "polymarket", 0.7, now=later,
                                       observed_basis=basis)
    expected = compute_aggregate_probability(SimpleNamespace(
        win_probability_sources=expected_bag, status="live",
        espn_win_prob_home=None, opening_home_probability=None), "live")
    assert retry["p"] == expected
    assert retry["preview"]["seq"] > first["preview"]["seq"]
    assert BASE["kalshi"]["updated_at"] == (T - timedelta(seconds=10)).isoformat()


def test_new_observation_same_number_advances_only_when_source_minimum_advances():
    reg = PreviewRegistry(epoch=1)
    first = propose(reg, {"1": T.timestamp(), "2": T.timestamp()})
    half = propose(reg, {"1": T.timestamp(), "2": T.timestamp() + 2})
    both = propose(reg, {"1": T.timestamp() + 1, "2": T.timestamp() + 2})
    assert first["p"] == half["p"] == both["p"]
    assert first["display_observed_at"] == half["display_observed_at"]
    assert both["display_observed_at"] == (T + timedelta(seconds=1)).isoformat()


@pytest.mark.parametrize("basis", [None, {}, {"1": T.timestamp(), "2": None},
    {"1": T.timestamp(), "2": float("nan")}, {"1": True}, {"1": "123"},
    {"1": float("inf")}, {"1": 1e100}])
def test_unknown_or_invalid_contributor_never_borrows_attempt_or_sibling_time(basis):
    frame = propose(PreviewRegistry(epoch=1), basis)
    assert frame["display_observed_at"] is None
    assert frame["p"] is not None  # headline still has its own existing admission


def test_sibling_commit_recomposition_uses_exact_base_clock_not_pending_attempt():
    reg = PreviewRegistry(epoch=1)
    propose(reg, {"1": T.timestamp()})
    sibling_at = T + timedelta(seconds=4)
    new_base = {"kalshi": {"value": 0.6, "updated_at": sibling_at.isoformat()}}
    frames = reg.committed(1, "kalshi", seq=None, sources=new_base, rev=2, event=EVENT)
    assert len(frames) == 1
    assert frames[0]["display_observed_at"] == sibling_at.isoformat()
    assert frames[0]["preview"]["base_rev"] == 2
    retry = propose(reg, {"1": T.timestamp()}, at=T+timedelta(seconds=20),
                    base=new_base, rev=2)
    assert retry["display_observed_at"] == sibling_at.isoformat()
    # A withdrawn sibling must not leave a client-side maximum in the new frame.
    withdrawn = reg.committed(1, "kalshi", seq=None, sources={}, rev=3, event=EVENT)
    assert withdrawn[0]["display_observed_at"] == T.isoformat()


def test_admitted_undated_sibling_abstains_but_refused_sibling_does_not_participate():
    reg = PreviewRegistry(epoch=1)
    frame = propose(reg, {"1": T.timestamp()}, base={"kalshi": 0.4})
    assert frame["display_observed_at"] is None
    # No value = not an admitted source, and cannot veto this clock.
    frame = propose(reg, {"1": T.timestamp()}, base={"kalshi": {"value": None}}, rev=2)
    assert frame["display_observed_at"] == T.isoformat()
