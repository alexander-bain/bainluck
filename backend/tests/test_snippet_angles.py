"""Tests for snippet angle selection — pure function golden set.

30 cases: 10 good (strong angles expected), 10 boring (no angle),
10 edge (boundary conditions).
"""

import pytest
from datetime import datetime, timezone, timedelta

from app.utils.snippet_angles import MarketContext, select_angle


NOW = datetime(2026, 6, 11, 12, 0, 0, tzinfo=timezone.utc)


# ── GOOD: strong angles expected ──


def test_fresh_move_up():
    ctx = MarketContext(name="Fed rate cut", movement_24h=0.08, outcome_name="Yes", now=NOW)
    r = select_angle(ctx)
    assert r is not None
    assert r.angle_type == "fresh_move"
    assert "8.0 pts" in r.template
    assert "Up" in r.template


def test_fresh_move_down():
    ctx = MarketContext(name="Trump wins", movement_24h=-0.12, outcome_name="Trump", now=NOW)
    r = select_angle(ctx)
    assert r.angle_type == "fresh_move"
    assert "Down" in r.template


def test_big_shift_from_open():
    ctx = MarketContext(
        name="Dune opens above $150M", probability=0.68,
        opening_probability=0.41, outcome_name="Yes", now=NOW,
    )
    r = select_angle(ctx)
    assert r.angle_type == "big_shift"
    assert "27" in r.template
    assert "opening 41%" in r.template


def test_cross_source_disagreement():
    ctx = MarketContext(
        name="Bitcoin above $100K", cross_source_delta=0.09,
        cross_source_names=("Kalshi", "Polymarket"), now=NOW,
    )
    r = select_angle(ctx)
    assert r.angle_type == "cross_source"
    assert "Kalshi" in r.template
    assert "9.0 pts" in r.template


def test_deadline_pressure():
    ctx = MarketContext(
        name="CPI above 3%", probability=0.58,
        resolution_date=NOW + timedelta(hours=48), now=NOW,
    )
    r = select_angle(ctx)
    assert r.angle_type == "deadline"
    assert "58/42" in r.template


def test_volume_surge_large():
    ctx = MarketContext(name="SpaceX launch", volume_24h=1_200_000, now=NOW)
    r = select_angle(ctx)
    assert r.angle_type == "volume_surge"
    assert "$1.2M" in r.template


def test_volume_surge_medium():
    ctx = MarketContext(name="Nvidia earnings", volume_24h=85_000, now=NOW)
    r = select_angle(ctx)
    assert r.angle_type == "volume_surge"
    assert "$85K" in r.template


def test_leader_change():
    ctx = MarketContext(
        name="Premier League winner", rank_change_24h=1,
        outcome_name="Arsenal", now=NOW,
    )
    r = select_angle(ctx)
    assert r.angle_type == "leader_change"
    assert "Arsenal" in r.template


def test_sibling_action():
    ctx = MarketContext(
        name="Rate cut before July", sibling_angle="before June version",
        sibling_movement=0.14, now=NOW,
    )
    r = select_angle(ctx)
    assert r.angle_type == "sibling_action"
    assert "14.0 pts" in r.template


def test_priority_fresh_move_beats_big_shift():
    ctx = MarketContext(
        name="Test", movement_24h=0.06, probability=0.80,
        opening_probability=0.50, outcome_name="Yes", now=NOW,
    )
    r = select_angle(ctx)
    assert r.angle_type == "fresh_move"


# ── BORING: no angle expected ──


def test_no_angle_empty_context():
    ctx = MarketContext(name="Boring market", now=NOW)
    assert select_angle(ctx) is None


def test_no_angle_tiny_movement():
    ctx = MarketContext(name="Stable", movement_24h=0.02, now=NOW)
    assert select_angle(ctx) is None


def test_no_angle_small_shift():
    ctx = MarketContext(name="Mild", probability=0.55, opening_probability=0.50, now=NOW)
    assert select_angle(ctx) is None


def test_no_angle_small_delta():
    ctx = MarketContext(
        name="Close", cross_source_delta=0.03,
        cross_source_names=("A", "B"), now=NOW,
    )
    assert select_angle(ctx) is None


def test_no_angle_far_deadline():
    ctx = MarketContext(
        name="Distant", probability=0.60,
        resolution_date=NOW + timedelta(days=30), now=NOW,
    )
    assert select_angle(ctx) is None


def test_no_angle_low_volume():
    ctx = MarketContext(name="Thin", volume_24h=5_000, now=NOW)
    assert select_angle(ctx) is None


def test_no_angle_no_rank_change():
    ctx = MarketContext(name="Steady", rank_change_24h=0, now=NOW)
    assert select_angle(ctx) is None


def test_no_angle_extreme_probability_deadline():
    """Deadline pressure skipped when probability is extreme (no tension)."""
    ctx = MarketContext(
        name="Certain", probability=0.95,
        resolution_date=NOW + timedelta(hours=24), now=NOW,
    )
    assert select_angle(ctx) is None


def test_no_angle_past_deadline():
    ctx = MarketContext(
        name="Expired", probability=0.50,
        resolution_date=NOW - timedelta(hours=1), now=NOW,
    )
    assert select_angle(ctx) is None


def test_no_angle_null_everything():
    ctx = MarketContext(
        name="Nothing", probability=None, opening_probability=None,
        movement_24h=None, volume_24h=None, now=NOW,
    )
    assert select_angle(ctx) is None


# ── EDGE: boundary conditions ──


def test_edge_movement_exactly_threshold():
    ctx = MarketContext(name="Edge", movement_24h=0.05, outcome_name="Yes", now=NOW)
    r = select_angle(ctx)
    assert r is not None
    assert r.angle_type == "fresh_move"


def test_edge_movement_just_below():
    ctx = MarketContext(name="Edge", movement_24h=0.049, now=NOW)
    assert select_angle(ctx) is None


def test_edge_shift_exactly_10pts():
    ctx = MarketContext(
        name="Edge", probability=0.60, opening_probability=0.50,
        outcome_name="Yes", now=NOW,
    )
    r = select_angle(ctx)
    assert r.angle_type == "big_shift"


def test_edge_deadline_72h_boundary():
    ctx = MarketContext(
        name="Edge", probability=0.50,
        resolution_date=NOW + timedelta(hours=72), now=NOW,
    )
    r = select_angle(ctx)
    assert r.angle_type == "deadline"


def test_edge_deadline_just_over():
    ctx = MarketContext(
        name="Edge", probability=0.50,
        resolution_date=NOW + timedelta(hours=73), now=NOW,
    )
    assert select_angle(ctx) is None


def test_edge_volume_exactly_50k():
    ctx = MarketContext(name="Edge", volume_24h=50_000, now=NOW)
    r = select_angle(ctx)
    assert r.angle_type == "volume_surge"


def test_edge_volume_just_below():
    ctx = MarketContext(name="Edge", volume_24h=49_999, now=NOW)
    assert select_angle(ctx) is None


def test_edge_negative_big_shift():
    ctx = MarketContext(
        name="Crashed", probability=0.20, opening_probability=0.45,
        outcome_name="Yes", now=NOW,
    )
    r = select_angle(ctx)
    assert r.angle_type == "big_shift"
    assert "down" in r.template


def test_edge_cross_source_exactly_5pts():
    ctx = MarketContext(
        name="Edge", cross_source_delta=0.05,
        cross_source_names=("Kalshi", "Polymarket"), now=NOW,
    )
    r = select_angle(ctx)
    assert r.angle_type == "cross_source"


def test_edge_deadline_probability_boundary_low():
    """Probability at 0.15 — just inside the tension window."""
    ctx = MarketContext(
        name="Edge", probability=0.15,
        resolution_date=NOW + timedelta(hours=24), now=NOW,
    )
    r = select_angle(ctx)
    assert r.angle_type == "deadline"
