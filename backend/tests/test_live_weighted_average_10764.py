"""#10764: eligible live updates move the hero and post-kickoff blend together."""

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from app.utils.aggregation import (
    TimestampedProb,
    compute_aggregate_probability,
    compute_aggregated_probability,
    effective_source_weights,
)

from app.utils.probability_eligibility import ELIGIBILITY_KEY, ineligible_record

NOW = datetime(2026, 10, 8, 17, 25, tzinfo=timezone.utc)


def event(values, status="live"):
    return SimpleNamespace(
        status=status,
        win_probability_sources={
            key: {"value": value, "updated_at": NOW.isoformat()}
            for key, value in values.items()
        },
        espn_win_prob_home=None,
        opening_home_probability=None,
    )


def history(values, **kwargs):
    return compute_aggregated_probability(
        {key: [TimestampedProb(NOW, value)] for key, value in values.items()},
        bucket_seconds=60,
        **kwargs,
    )[-1].home_probability


@pytest.mark.parametrize(
    "betting,kalshi,expected",
    [(0.255, 0.295, 0.263421), (0.3587, 0.30, 0.346342), (0.3587, 0.37, 0.361079)],
)
def test_live_updates_contribute_to_hero_and_history(betting, kalshi, expected):
    values = {"betting": betting, "kalshi": kalshi}
    assert compute_aggregate_probability(event(values)) == expected
    assert history(values, live_blend=True, pregame_until=NOW) == expected


def test_default_nonlive_and_pregame_keep_median():
    values = {"betting": 0.255, "kalshi": 0.295}
    assert compute_aggregate_probability(event(values, "scheduled")) == 0.255
    assert history(values) == 0.255
    assert (
        history(values, live_blend=True, pregame_until=NOW + timedelta(minutes=1))
        == 0.255
    )


def test_final_result_and_settled_hero_keep_existing_authority():
    values = {"betting": 0.255, "final_result": 1.0}
    assert compute_aggregate_probability(event(values)) == 1.0
    assert history(values, live_blend=True) == 1.0
    assert (
        compute_aggregate_probability(
            event({"betting": 1.0, "kalshi": 0.295}, "completed")
        )
        == 1.0
    )


def test_divergent_pair_keeps_primary_on_both_surfaces():
    values = {"betting": 0.255, "kalshi": 0.90}
    assert compute_aggregate_probability(event(values)) == 0.255
    assert history(values, live_blend=True) == 0.255


def test_refused_and_withdrawn_source_stays_excluded():
    row = event({"betting": 0.255, "kalshi": 0.295})
    row.win_probability_sources["kalshi"][ELIGIBILITY_KEY] = ineligible_record(
        rule="10764:wrong_question"
    ).to_entry()
    assert compute_aggregate_probability(row) == 0.255
    series = {
        "betting": [
            TimestampedProb(NOW, 0.255),
            TimestampedProb(NOW + timedelta(minutes=1), 0.26),
        ],
        "kalshi": [
            TimestampedProb(NOW, 0.295),
            TimestampedProb(NOW + timedelta(minutes=1), None),
        ],
    }
    assert (
        compute_aggregated_probability(series, live_blend=True)[-1].home_probability
        == 0.26
    )


def test_three_source_effective_cap_is_used_by_live_average():
    values = {"betting": 0.255, "kalshi": 0.295, "polymarket": 0.30}
    keys, _, weights = effective_source_weights(event(values))
    capped = dict(zip(keys, weights))
    assert capped["betting"] == pytest.approx(1.6 * 0.35 / 0.65)
    expected = round(0.255 * 0.35 + 0.295 * 0.325 + 0.30 * 0.325, 6)
    assert compute_aggregate_probability(event(values)) == expected
    assert history(values, live_blend=True) == expected


def test_relative_freshness_still_reduces_lagged_source():
    row = event({"betting": 0.255, "kalshi": 0.295})
    row.win_probability_sources["betting"]["updated_at"] = (
        NOW - timedelta(minutes=20)
    ).isoformat()
    keys, values, weights = effective_source_weights(row)
    assert dict(zip(keys, weights))["betting"] < 3.0
    assert compute_aggregate_probability(row) == round(
        sum(v * w for v, w in zip(values, weights)) / sum(weights), 6
    )
