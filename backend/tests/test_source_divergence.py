"""Ruling (b), cycle 99 — the divergence gate and equal-weight midpoint.

STRUCTURAL, over the LIVE population rather than over invented rows. Both
fixtures were read from production on 2026-08-19 against deployed `962f668a`:

  - `two_source_events_20260819.json` — every live two-source event blend (76).
  - `related_futures_15200831_20260819.json` — the raw pre-merge rows behind
    Astros @ Angels, captured before the merge shipped.

The unit tests below pin the two properties a synthetic case can prove better
than real data can (the boundary, and the anti-#240 primary rule). Everything
else is asserted against the real rows, because the failure mode this lane keeps
meeting is a green test over a population that does not contain the case.

Every population assertion carries a NON-VACUITY floor. A structural test whose
fixture drifts to empty must go red, not green — that is the same defect as
`boring-rate@20: 0/20` over zero cards, which is what cycle 99 found the feed
audit doing.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from app.utils.aggregation import (
    SOURCE_WEIGHTS,
    _weighted_median,
    assess_event_divergence,
    compute_aggregate_probability,
    effective_source_weights,
    parse_source_entry,
)
from app.utils.futures_source_merge import (
    blend_with_verdict,
    merge_relabel_collisions,
)
from app.utils.source_divergence import (
    DIVERGENCE_SPREAD_THRESHOLD,
    assess_divergence,
    spread_exceeds,
)

FIXTURES = Path(__file__).parent / "fixtures"


class _Ev:
    """The duck type `compute_aggregate_probability` actually reads."""

    def __init__(self, wps, status):
        self.win_probability_sources = wps
        self.status = status
        self.espn_win_prob_home = None
        self.opening_home_probability = None


@pytest.fixture(scope="module")
def live_two_source_events():
    data = json.loads(
        (FIXTURES / "two_source_events_20260819.json").read_text()
    )
    events = data["events"]
    assert len(events) >= 20, (
        "NON-VACUITY: the live two-source fixture must hold a real population. "
        f"got {len(events)}"
    )
    return events


@pytest.fixture(scope="module")
def live_merge_rows():
    data = json.loads(
        (FIXTURES / "related_futures_15200831_20260819.json").read_text()
    )
    rows = data["rows"]
    assert len(rows) >= 50, f"NON-VACUITY: merge fixture too small ({len(rows)})"
    # The captured rows are PRE-merge. If a future capture accidentally records
    # post-merge rows the whole file proves nothing, so say so here.
    assert not any(r.get("blend_rule") for r in rows)
    return rows


def _readings(wps, status):
    keys, values, weights = effective_source_weights(_Ev(wps, status), status)
    return keys, values, weights


# ── the boundary, per ruling (c) ─────────────────────────────────────────────

def test_a_pair_exactly_on_the_threshold_is_sane_and_blends():
    """The threshold is the TOP of the sane band. On the line is inside it."""
    assert spread_exceeds(DIVERGENCE_SPREAD_THRESHOLD) is False
    assert (
        assess_divergence(
            {"kalshi": 0.9, "polymarket": 0.5}, {"kalshi": 0.8, "polymarket": 0.8}
        )
        is None
    ), "0.9 vs 0.5 is a spread of exactly 0.40 and must NOT gate"


def test_float_error_cannot_decide_whether_a_boundary_pair_gates():
    """`0.7 - 0.3` is 0.39999999999999997 and `0.9 - 0.5` is 0.4.

    Two pairs specified as the same spread must get the same verdict. With a
    bare `>` they do not: sweeping every pair whose intended spread is exactly
    the threshold, 78 of 601 land a few ULPs high and wrongly gate.
    """
    wrong = []
    for i in range(0, 601):
        lo = i / 1000.0
        hi = lo + DIVERGENCE_SPREAD_THRESHOLD
        if hi > 1.0:
            break
        if spread_exceeds(abs(hi - lo)):
            wrong.append((lo, hi))
    assert wrong == [], f"boundary pairs wrongly gated: {wrong[:5]}"

    # And the mutation this guards: the same sweep under a bare `>`.
    naive = sum(
        1
        for i in range(0, 601)
        if (i / 1000.0) + DIVERGENCE_SPREAD_THRESHOLD <= 1.0
        and abs(((i / 1000.0) + DIVERGENCE_SPREAD_THRESHOLD) - (i / 1000.0))
        > DIVERGENCE_SPREAD_THRESHOLD
    )
    assert naive > 0, (
        "if this is 0 the sweep no longer exercises the float hazard and the "
        "test above has stopped proving anything"
    )


def test_a_pair_just_past_the_threshold_does_gate():
    d = assess_divergence(
        {"kalshi": 0.9, "polymarket": 0.4999}, {"kalshi": 0.8, "polymarket": 0.8}
    )
    assert d is not None
    assert d.primary_value in (0.9, 0.4999)


# ── scope: the gate governs two sources and only two ─────────────────────────

@pytest.mark.parametrize(
    "readings",
    [
        {"betting": 0.9},
        {"betting": 0.95, "kalshi": 0.02, "polymarket": 0.05},
        {},
    ],
)
def test_the_gate_ignores_populations_it_does_not_govern(readings):
    weights = {k: SOURCE_WEIGHTS.get(k, 0.8) for k in readings}
    assert assess_divergence(readings, weights) is None


# ── the anti-#240 property: primary follows EFFECTIVE weight ─────────────────

def test_the_gate_does_not_print_a_stale_pregame_line_over_a_live_one():
    """A base-weight primary would rebuild #240. This pins that it does not.

    Live blowout: the sportsbook is frozen at its pregame 65% and 40 minutes
    stale; the market says 5% and is current. Spread 0.60, so the gate fires.
    It must render the MARKET's number — the sportsbook's authority does not
    survive it having stopped reporting.
    """
    now = datetime.now(timezone.utc)
    wps = {
        "betting": {"value": 0.65, "updated_at": (now - timedelta(minutes=40)).isoformat()},
        "kalshi": {"value": 0.05, "updated_at": now.isoformat()},
    }
    ev = _Ev(wps, "live")

    divergence = assess_event_divergence(ev, "live")
    assert divergence is not None, "a 60-point live gap must be flagged"
    assert divergence.primary_source == "kalshi"
    assert compute_aggregate_probability(ev, "live") == pytest.approx(0.05)

    # The same pair with a FRESH sportsbook resolves the other way — proving the
    # rule above is about staleness, not about disliking `betting`.
    fresh = {
        "betting": {"value": 0.65, "updated_at": now.isoformat()},
        "kalshi": {"value": 0.05, "updated_at": now.isoformat()},
    }
    assert assess_event_divergence(_Ev(fresh, "live"), "live").primary_source == "betting"
    assert compute_aggregate_probability(_Ev(fresh, "live"), "live") == pytest.approx(0.65)


def test_an_equal_weight_tie_resolves_deterministically_by_declared_order():
    readings = {"kalshi": 0.575, "polymarket": 0.06}
    weights = {"kalshi": 0.8, "polymarket": 0.8}
    assert assess_divergence(readings, weights, order=["kalshi", "polymarket"]).primary_source == "kalshi"
    assert assess_divergence(readings, weights, order=["polymarket", "kalshi"]).primary_source == "polymarket"


# ── SURFACE A: the live 76 ───────────────────────────────────────────────────

def test_every_live_hero_renders_a_number_some_source_actually_stated(
    live_two_source_events,
):
    """The no-mixture invariant, over the real population.

    This is what the gate buys on the events hero. It holds today by accident of
    the median; ruling (b) makes a genuine mixture legal one module over, so it
    is worth a test that fails the moment a mixture leaks onto this surface.
    """
    checked = 0
    for row in live_two_source_events:
        ev = _Ev(row["win_probability_sources"], row["status"])
        keys, values, _ = _readings(row["win_probability_sources"], row["status"])
        if len(keys) != 2:
            continue
        blend = compute_aggregate_probability(ev, row["status"])
        assert blend is not None
        assert any(abs(blend - v) < 1e-6 for v in values), (
            f"event {row['event_id']} rendered {blend}, which is neither of its "
            f"own readings {dict(zip(keys, values))}"
        )
        checked += 1
    assert checked >= 20, f"NON-VACUITY: only {checked} two-source events checked"


def test_the_gate_changes_no_displayed_hero_on_the_live_population(
    live_two_source_events,
):
    """The honest headline: on this surface the gate is a flag, not a number.

    Asserted rather than asserted-about, because it is the property that makes
    the gate safe to ship without a staged rollout. Compare the shipped
    aggregate against the ungated weighted median over the SAME effective
    weights; they must agree everywhere, including on the four gated events.
    """
    gated = 0
    for row in live_two_source_events:
        keys, values, weights = _readings(
            row["win_probability_sources"], row["status"]
        )
        if len(keys) != 2:
            continue
        shipped = compute_aggregate_probability(
            _Ev(row["win_probability_sources"], row["status"]), row["status"]
        )
        ungated = round(_weighted_median(values, weights), 6)
        assert shipped == pytest.approx(ungated), (
            f"event {row['event_id']}: gate moved the hero {ungated} -> {shipped}"
        )
        if assess_divergence(dict(zip(keys, values)), dict(zip(keys, weights))):
            gated += 1
    assert gated >= 1, (
        "NON-VACUITY: no event in the fixture trips the gate, so this test "
        "proved nothing about gated events"
    )


def test_exactly_the_wide_pairs_are_flagged_for_matching(live_two_source_events):
    flagged = []
    for row in live_two_source_events:
        keys, values, _ = _readings(row["win_probability_sources"], row["status"])
        if len(keys) != 2:
            continue
        d = assess_event_divergence(
            _Ev(row["win_probability_sources"], row["status"]), row["status"]
        )
        spread = abs(values[0] - values[1])
        assert (d is not None) == spread_exceeds(spread), (
            f"event {row['event_id']} spread {spread} flagged={d is not None}"
        )
        if d is not None:
            flagged.append((row["event_id"], d.as_evidence()))

    assert flagged, "NON-VACUITY: the live population must contain wide pairs"
    for _eid, ev in flagged:
        assert ev["suspected_mislink"] is True
        assert ev["spread"] > ev["threshold"]
        # Evidence has to name BOTH readings or matching cannot act on it.
        assert ev["primary_source"] != ev["other_source"]
        assert ev["primary_value"] != ev["other_value"]


# ── SURFACE B: the live futures merge ────────────────────────────────────────

def test_the_live_merge_exercises_both_arms_of_the_ruling(live_merge_rows):
    """Non-vacuity for surface B: the real payload must hit gate AND midpoint."""
    merged = [r for r in merge_relabel_collisions(live_merge_rows) if r.get("blend_rule")]
    rules = [r["blend_rule"] for r in merged]
    assert rules.count("divergence_gate") >= 1, rules
    assert rules.count("equal_weight_midpoint") >= 1, rules


def test_the_al_west_specimen_prints_a_stated_value_not_a_statistic(live_merge_rows):
    """The row ruling (b) was written about.

    Kalshi 0.575, Polymarket 0.060. The old blend printed 0.06 (the lower entry);
    a mean would print 0.3175. Both are answers to a question neither source was
    asked. Gated, it prints one source's own number and carries the flag.
    """
    merged = merge_relabel_collisions(live_merge_rows)
    al_west = [
        r
        for r in merged
        if r.get("merge_group") == "al_west" and r.get("blend_rule")
    ]
    assert len(al_west) == 1, f"expected one merged al_west row, got {len(al_west)}"
    row = al_west[0]

    assert row["blend_rule"] == "divergence_gate"
    assert row["probability"] == pytest.approx(0.575)
    assert row["probability"] != pytest.approx(0.3175), "a mean is not a rescue"
    assert row["probability"] != pytest.approx(0.06), "nor is the lower entry"
    assert row["divergence"]["suspected_mislink"] is True
    assert row["divergence"]["spread"] == pytest.approx(0.515)


def test_every_midpoint_merge_is_the_midpoint_and_sits_between_its_sources(
    live_merge_rows,
):
    by_group: dict = {}
    for r in live_merge_rows:
        if r.get("merge_group"):
            by_group.setdefault(r["merge_group"], []).append(r)

    checked = 0
    for row in merge_relabel_collisions(live_merge_rows):
        if row.get("blend_rule") != "equal_weight_midpoint":
            continue
        contributors = [
            c
            for c in by_group[row["merge_group"]]
            if c.get("outcome_name") == row.get("outcome_name")
            or c.get("source") in (row.get("all_sources") or [])
        ]
        vals = sorted(
            {
                float(c["probability"])
                for c in contributors
                if c.get("probability") is not None
                and c.get("market_id") is not None
            }
        )
        # The merged pair's own two readings bracket the printed value.
        assert min(vals) <= row["probability"] <= max(vals)
        checked += 1
    assert checked >= 1, "NON-VACUITY: no midpoint merges exercised"


def test_the_midpoint_is_the_mean_of_exactly_two_equal_weight_readings():
    value, divergence, rule = blend_with_verdict(
        [
            {"source": "kalshi", "probability": 0.095},
            {"source": "polymarket", "probability": 0.0265},
        ]
    )
    assert rule == "equal_weight_midpoint"
    assert divergence is None
    assert value == pytest.approx((0.095 + 0.0265) / 2)
    # The defect the ruling names: the old blend returned the LOWER entry, and
    # the bias was exactly half the spread, always downward.
    assert value != pytest.approx(0.0265)


def test_an_unequal_weight_pair_keeps_the_weighted_median(live_merge_rows):
    """Scope guard. The midpoint is for TIES only; the events aggregator's
    heavier-source tiebreak is designed behaviour and ruling (b) preserved it."""
    value, _, rule = blend_with_verdict(
        [
            {"source": "betting", "probability": 0.70},
            {"source": "kalshi", "probability": 0.60},
        ]
    )
    assert rule == "weighted_median"
    assert value == pytest.approx(0.70)


def test_same_source_rows_are_never_treated_as_a_disagreement():
    """Sibling outcomes of one multi-outcome market are not two opinions.

    This is the 30-row `world_series_matchup` class cycle 97 refused to fuse;
    `blend_with_verdict` re-checks it rather than trusting its caller.
    """
    value, divergence, rule = blend_with_verdict(
        [
            {"source": "kalshi", "probability": 0.90},
            {"source": "kalshi", "probability": 0.10},
        ]
    )
    assert divergence is None
    assert rule == "weighted_median"


def test_merging_never_fuses_distinct_questions(live_merge_rows):
    """Row-count arithmetic: each merge removes exactly its extra contributors."""
    out = merge_relabel_collisions(live_merge_rows)
    merged = [r for r in out if r.get("blend_rule")]
    absorbed = sum(r.get("merged_source_count", 1) - 1 for r in merged)
    assert len(out) == len(live_merge_rows) - absorbed
    for r in merged:
        assert r.get("merged_source_count", 0) == 2, (
            "a merge of more than two contributors is outside the ruling's "
            "scope and must not appear silently"
        )
