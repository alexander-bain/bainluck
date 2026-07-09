"""#999 L2-72: F1 adapter pure helpers (winner-field motorsports)."""

from datetime import datetime, timezone, timedelta

from app.utils.event_f1 import (
    is_gp_winner_market,
    gp_tokens,
    shares_gp,
    f1_status,
)

NOW = datetime(2026, 7, 9, tzinfo=timezone.utc)


class TestGpWinnerClassifier:
    def test_main_race_winner_is_primary(self):
        assert is_gp_winner_market("British Grand Prix Winner") is True
        assert is_gp_winner_market("British Grand Prix: Driver Winner") is True

    def test_submarkets_are_not_the_primary(self):
        for n in [
            "British Grand Prix: Sprint Race Winner",
            "British Grand Prix Qualifying Session (Q3): Pole Position",
            "Austrian Grand Prix Main Race: Podium Finishers",
            "Austrian Grand Prix Main Race: Top Constructor",
            "British Grand Prix Sprint Race: Top 5 Finishers",
        ]:
            assert is_gp_winner_market(n) is False, n


class TestGpTokens:
    def test_distinctive_gp_name(self):
        assert gp_tokens("British Grand Prix Winner") == {"british"}
        assert gp_tokens("Austrian Grand Prix Main Race: Fastest Lap") == {"austrian"}

    def test_shares_gp(self):
        toks = gp_tokens("British Grand Prix Winner")
        assert shares_gp("British Grand Prix: Sprint Race Winner", toks) is True
        assert shares_gp("Austrian Grand Prix Winner", toks) is False
        assert shares_gp("anything", set()) is False


class TestF1Status:
    def test_settled_past_or_resolved(self):
        assert f1_status("resolved", NOW + timedelta(days=2), NOW) == "settled"
        assert f1_status("open", NOW - timedelta(days=1), NOW) == "settled"

    def test_live_on_race_weekend(self):
        assert f1_status("open", NOW + timedelta(days=2), NOW) == "live"

    def test_upcoming_when_far_or_unknown(self):
        assert f1_status("open", NOW + timedelta(days=20), NOW) == "upcoming"
        assert f1_status("open", None, NOW) == "upcoming"
