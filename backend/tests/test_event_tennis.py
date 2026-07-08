"""#999 slice 2: tennis adapter pure helpers."""

from datetime import datetime, timezone, timedelta

from app.utils.event_tennis import (
    is_winner_market,
    is_matchup_market,
    tournament_tokens,
    shares_tournament,
    tennis_status,
)

NOW = datetime(2026, 7, 8, tzinfo=timezone.utc)


class TestClassifiers:
    def test_winner_market(self):
        assert is_winner_market("2026 Women's Wimbledon Winner") is True
        assert is_winner_market("Wimbledon Men's Champion 2026") is True
        assert is_winner_market("Gauff vs Sabalenka") is False
        # a "to win the match" phrasing that is actually a matchup is not a field
        assert is_winner_market("Alcaraz vs Sinner") is False

    def test_matchup_market(self):
        for n in ["Gauff vs Sabalenka", "Alcaraz v Sinner", "Djokovic def. Nadal"]:
            assert is_matchup_market(n) is True
        assert is_matchup_market("2026 Wimbledon Winner") is False

    def test_tournament_tokens(self):
        assert tournament_tokens("2026 Women's Wimbledon Winner") == {"wimbledon"}
        # year / gender / "winner" / "tennis" stripped
        assert "2026" not in tournament_tokens("2026 US Open Winner (Tennis)")

    def test_shares_tournament(self):
        toks = tournament_tokens("2026 Women's Wimbledon Winner")
        assert shares_tournament("Gauff vs Muchova — Wimbledon R2", toks) is True
        assert shares_tournament("2026 US Open Winner", toks) is False
        assert shares_tournament("anything", set()) is False


class TestStatus:
    def test_settled_when_resolved_or_past(self):
        assert tennis_status("resolved", NOW + timedelta(days=5), NOW) == "settled"
        assert tennis_status("open", NOW - timedelta(days=1), NOW) == "settled"

    def test_live_when_resolution_near(self):
        assert tennis_status("open", NOW + timedelta(days=4), NOW) == "live"

    def test_upcoming_when_far_or_unknown(self):
        assert tennis_status("open", NOW + timedelta(days=60), NOW) == "upcoming"
        assert tennis_status("open", None, NOW) == "upcoming"
