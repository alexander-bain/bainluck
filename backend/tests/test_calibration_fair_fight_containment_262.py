"""Queue #262 Item 3 — the fair-fight surface must NOT declare a source winner
until the comparison is one-question-to-one-question with the headline metric.

Before #262 the futures fair-fight (a) used a stale NOT-IN truth denylist, (b)
grouped GENERIC canonical-key buckets (``basketball::championship:2026`` covers
~47K markets) and called ``min(row counts)`` ``shared_markets``, and (c) emitted a
``winner`` + ``advantage_pp`` from an equal-per-bucket MCE that differs from the
outcome-weighted headline ECE — so the declared winner reflected population +
weighting, not source skill (C23 P1). The sports path IS per-event matched but
still used the non-headline metric.

Containment (this queue, no source-matching redesign, no weighting choice):
  * futures fair-fight uses the independent-truth ALLOWLIST, not the denylist;
  * NEITHER path emits ``winner``/``advantage_pp`` or presents ``min(row counts)``
    as ``shared_markets`` — they degrade to an explicit unavailable response with a
    reason and diagnostic-only per-source MCEs.
"""

import inspect

from app.tasks import precompute_calibration as pc


class TestFairFightTruthAllowlist:
    def test_futures_fair_fight_uses_allowlist_not_denylist(self):
        src = inspect.getsource(pc._query_futures_fair_fight_impl)
        assert "CALIBRATION_TRUTH_ELIGIBLE_SOURCES_SQL" in src
        # the legacy NOT-IN denylist tokens are gone.
        for token in ("pass2_guess", "pass2_loser", "all_losers", "no_pregame_trading"):
            assert token not in src, f"legacy denylist token still in fair-fight: {token}"


class TestNoWinnerEmitted:
    def test_futures_pair_has_no_winner_or_advantage(self):
        src = inspect.getsource(pc._query_futures_fair_fight_impl)
        assert '"winner"' not in src
        assert "advantage_pp" not in src
        # min(row counts) is not presented as matched markets.
        assert '"shared_markets"' not in src
        # explicit unavailable response with a reason + honest per-source counts.
        assert '"comparison_available": False' in src
        assert '"reason"' in src
        assert '"kalshi_rows"' in src and '"polymarket_rows"' in src

    def test_sports_pair_has_no_winner_or_advantage(self):
        src = inspect.getsource(pc._query_sports_fair_fight_impl)
        assert '"winner"' not in src
        assert "advantage_pp" not in src
        assert '"shared_markets"' not in src
        assert '"comparison_available": False' in src
        # per-event matched count is honestly named (these ARE the same game).
        assert '"matched_questions"' in src

    def test_payload_marks_surface_unavailable(self):
        src = inspect.getsource(pc._compute_fair_fight_comparison)
        assert '"comparison_available": False' in src
        assert "unavailable_reason" in src
        # methodology no longer claims a difficulty-controlled winner.
        assert "Diagnostic per-source MCE only" in src


if __name__ == "__main__":
    import pytest

    raise SystemExit(pytest.main([__file__, "-v"]))
