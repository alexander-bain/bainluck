"""#999 slice 2: tennis adapter pure helpers."""

from datetime import datetime, timezone, timedelta

from app.utils.event_tennis import (
    is_winner_market,
    is_matchup_market,
    tournament_tokens,
    shares_tournament,
    tennis_status,
    tennis_gender,
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


class TestGender:
    """L2-65 Item 2: gender inference guards canonical resolution."""

    def test_women_beats_men_substring(self):
        # "women" contains "men" — women must be detected first.
        assert tennis_gender("2026 Women's Wimbledon Winner") == "women"
        assert tennis_gender("wimbledon-women-s-singles-winner") == "women"
        assert tennis_gender("WTA Wimbledon Winner") == "women"

    def test_men(self):
        assert tennis_gender("2026 Men's Wimbledon Winner") == "men"
        assert tennis_gender("wimbledon-men-s-singles-winner") == "men"
        assert tennis_gender("ATP Wimbledon Winner") == "men"

    def test_neutral(self):
        assert tennis_gender("Wimbledon Winner") == ""
        assert tennis_gender("wimbledon") == ""
        assert tennis_gender(None) == ""


class TestStatus:
    def test_settled_when_resolved_or_past(self):
        assert tennis_status("resolved", NOW + timedelta(days=5), NOW) == "settled"
        assert tennis_status("open", NOW - timedelta(days=1), NOW) == "settled"

    def test_a_near_resolution_is_not_live_by_default(self):
        """UX-P208. Alex, 2026-08-30: `/hub/tennis` printed a pulsing LIVE dot
        over four cards dated up to a fortnight ahead. Proximity to a resolution
        date is not evidence a tournament has begun, so silence no longer
        produces the claim — a caller has to ask for the inference by name."""
        for days in (0.5, 4, 13, 21):
            assert (
                tennis_status("open", NOW + timedelta(days=days), NOW) == "upcoming"
            ), f"a tournament resolving in {days}d claimed to be live"

    def test_the_proximity_inference_survives_where_it_is_asked_for(self):
        """`build_event` still opts in, so this is a real switch and not a
        deletion wearing a keyword. Both arms are asserted: without the flag the
        whole window is quiet, with it the old boundary is bit-for-bit intact."""
        assert (
            tennis_status("open", NOW + timedelta(days=4), NOW, proximity_live=True)
            == "live"
        )
        assert (
            tennis_status("open", NOW + timedelta(days=21), NOW, proximity_live=True)
            == "live"
        )
        assert (
            tennis_status("open", NOW + timedelta(days=22), NOW, proximity_live=True)
            == "upcoming"
        )

    def test_opting_in_never_overrides_a_settled_verdict(self):
        """The flag widens ONE branch. A resolved market and a past resolution
        date still settle, or the crown logic downstream would read a decided
        tournament as in-play."""
        assert (
            tennis_status("resolved", NOW + timedelta(days=5), NOW, proximity_live=True)
            == "settled"
        )
        assert (
            tennis_status("open", NOW - timedelta(days=1), NOW, proximity_live=True)
            == "settled"
        )

    def test_upcoming_when_far_or_unknown(self):
        assert tennis_status("open", NOW + timedelta(days=60), NOW) == "upcoming"
        assert tennis_status("open", None, NOW) == "upcoming"
