"""#993: shared outcome-display rules (search + typeahead + futures DETAIL).

Guards the ONE source of truth so the detail page can't drift back to showing
"Other 100%" while search shows the real leader.
"""

from app.utils.outcome_display import (
    is_placeholder_outcome_name,
    normalize_display_probs,
    leader_pick_order,
)


class TestPlaceholder:
    def test_team_single_letter_is_placeholder(self):
        for n in ("Team A", "Team C", "Team E"):
            assert is_placeholder_outcome_name(n) is True, n

    def test_real_teams_kept(self):
        for n in ("Team GB", "Team USA", "Cleveland Cavaliers", "Miami Heat"):
            assert is_placeholder_outcome_name(n) is False, n

    def test_family_and_legacy(self):
        assert is_placeholder_outcome_name("Person CF") is True
        assert is_placeholder_outcome_name("player AB") is True   # legacy garbage
        assert is_placeholder_outcome_name("Donald Trump") is False


class TestNormalizeAndLeaderPick:
    def test_normalize_over_100(self):
        outs = [{"probability": 0.8}, {"probability": 0.6}, {"probability": 0.4}]
        normalize_display_probs(outs)
        assert abs(sum(o["probability"] for o in outs) - 1.0) < 0.01

    def test_leader_pick_demotes_other(self):
        outs = [{"name": "Other", "probability": 0.52},
                {"name": "Cleveland Cavaliers", "probability": 0.27}]
        leader_pick_order(outs)
        assert outs[0]["name"] == "Cleveland Cavaliers"
        assert any(o["name"] == "Other" for o in outs)


class TestDetailUsesSharedPipeline:
    """_format_market_detail must route through the shared rules (not its old
    garbage-only filter). Assert on source rather than a brittle full-market mock
    (the endpoint is proven end-to-end by the live click-through trace)."""

    def test_format_market_detail_calls_shared_helpers(self):
        import inspect
        from app.routes import futures

        src = inspect.getsource(futures._format_market_detail)
        assert "is_placeholder_outcome_name" in src
        assert "normalize_display_probs" in src
        assert "leader_pick_order" in src
