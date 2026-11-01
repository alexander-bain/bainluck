"""#10090 decision D: a live sportsbook/market pair ties, and the tie is not dict order.

Alex 2026-10-31 (decision D): in live play Kalshi and Polymarket carry the
sportsbook's base weight (3.0). A two-source live event whose arms disagree past
the divergence threshold is rendered from its primary source alone (#1829 gate);
with equal weights `assess_divergence` fell back to the reading order, so
``{kalshi 0.9, betting 0.1}`` read 0.9 and the same bag written the other way
round read 0.1. The tie now goes to the higher BASE weight, the pair's primary
before D; equal base weights keep the reading order. Timestamps are literals
(gotcha #44).
"""

import pytest

from app.utils.aggregation import HERO_RELATIVE_GRACE_SECONDS, assess_event_divergence
from tests.test_probability_recency_and_cap import _FakeEvent, _stamped


def _hero(sources):
    from app.utils.aggregation import compute_aggregate_probability

    return compute_aggregate_probability(_FakeEvent(sources, "live"))


@pytest.mark.parametrize("market", ["kalshi", "polymarket"])
def test_a_tied_live_pair_reads_the_sportsbook_in_either_reading_order(market):
    forward = _stamped(**{market: (0.9, 0), "betting": (0.1, 0)})
    backward = _stamped(**{"betting": (0.1, 0), market: (0.9, 0)})

    assert _hero(forward) == pytest.approx(0.1)
    assert _hero(backward) == pytest.approx(0.1)
    verdict = assess_event_divergence(_FakeEvent(forward, "live"), "live")
    assert (verdict.primary_source, verdict.other_source) == ("betting", market)


def test_the_tiebreak_only_breaks_ties_a_decayed_sportsbook_still_loses():
    """Betting 25 minutes behind decays below the fresh market's 3.0, so the
    market is primary on weight alone: the base-weight order never outranks an
    actual weight difference."""
    behind = HERO_RELATIVE_GRACE_SECONDS + 15 * 60
    sources = _stamped(betting=(0.1, behind), kalshi=(0.9, 0))

    assert _hero(sources) == pytest.approx(0.9)


def test_equal_base_weights_keep_the_reading_order():
    """kalshi and polymarket tied before D too (0.8 each); the stable sort leaves
    that tie exactly where it was."""
    assert _hero(_stamped(kalshi=(0.9, 0), polymarket=(0.1, 0))) == pytest.approx(0.9)
    assert _hero(_stamped(polymarket=(0.1, 0), kalshi=(0.9, 0))) == pytest.approx(0.1)


def test_a_close_live_pair_is_still_averaged_at_equal_weight():
    """No divergence, no gate: decision D's average, 3.0 against 3.0."""
    assert _hero(_stamped(kalshi=(0.6, 0), betting=(0.5, 0))) == pytest.approx(0.55)


def test_a_governed_live_espn_kalshi_pair_reads_kalshi():
    """Decision D's direct consequence, written down: live, kalshi's 3.0
    outweighs espn's 1.5, so a broken espn/kalshi pair renders kalshi (it
    rendered espn at kalshi's old 0.8)."""
    sources = _stamped(espn=(0.1, 0), kalshi=(0.9, 0))

    assert _hero(sources) == pytest.approx(0.9)
