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

    def test_bare_uppercase_codes_are_placeholders(self):
        # #993 L2-43: Ballon d'Or fully-anonymized codes
        for n in ("BF", "BD", "AR", "AY", "W", "Y"):
            assert is_placeholder_outcome_name(n) is True, n

    def test_binary_and_words_not_bare_codes(self):
        # Yes/No/Over/Under/real names must survive (mixed case / len>2)
        for n in ("Yes", "No", "Over", "Under", "Cleveland Cavaliers"):
            assert is_placeholder_outcome_name(n) is False, n


class TestNormalizeAndLeaderPick:
    def test_normalize_over_100(self):
        outs = [{"probability": 0.8}, {"probability": 0.6}, {"probability": 0.4}]
        normalize_display_probs(outs)
        assert abs(sum(o["probability"] for o in outs) - 1.0) < 0.01

    def test_who_wins_overround_still_normalized(self):
        # A mutually-exclusive "who wins" field with Kalshi overround (default
        # mutually_exclusive=True) must STILL be normalized to ~100%.
        outs = [{"probability": 0.55}, {"probability": 0.45}, {"probability": 0.30}]
        normalize_display_probs(outs)  # default mutually_exclusive=True
        assert abs(sum(o["probability"] for o in outs) - 1.0) < 0.01
        # leader preserved
        assert outs[0]["probability"] > outs[1]["probability"]

    def test_make_cut_family_not_squashed(self):
        # #199: golf make-cut is NON-mutually-exclusive (FuturesMarket.mutually_exclusive
        # is False) — half a ~156 field makes the cut, so per-player probs are ~0.5-0.9
        # and the SET sums to many multiples of 100%. Normalizing to sum-1 squashed
        # Scheffler's honest 0.87 to ~0.011 on The Open's detail/ladder rail. With the
        # mutually_exclusive=False gate the display pipeline leaves them UNTOUCHED.
        make_cut = [
            {"name": "Scottie Scheffler", "probability": 0.87},
            {"name": "Rory McIlroy", "probability": 0.885},
            {"name": "Matt Fitzpatrick", "probability": 0.84},
            {"name": "Tommy Fleetwood", "probability": 0.44},
            {"name": "Robert MacIntyre", "probability": 0.79},
            {"name": "Ludvig Aberg", "probability": 0.685},
        ]
        normalize_display_probs(make_cut, mutually_exclusive=False)
        assert make_cut[0]["probability"] == 0.87, "make-cut leader must stay honest"
        assert make_cut[1]["probability"] == 0.885
        assert sum(o["probability"] for o in make_cut) > 4.0, "not squashed to sum-1"

    def test_make_cut_would_be_squashed_if_treated_as_mutually_exclusive(self):
        # Guard the regression itself: the SAME make-cut field, if the ME gate is
        # ever dropped (treated as mutually_exclusive=True), collapses to ~1% — the
        # exact production bug. This documents why the gate must stay.
        make_cut = [{"probability": 0.87}, {"probability": 0.885}, {"probability": 0.84}]
        normalize_display_probs(make_cut, mutually_exclusive=True)
        assert make_cut[0]["probability"] < 0.5, "confirms the un-gated squash"

    def test_top_n_family_not_squashed(self):
        # Top-5 / top-N: N outcomes are simultaneously true (mutually_exclusive=False).
        # Raw per-golfer top-5 probabilities are meaningful; keep them.
        top5 = [
            {"name": "Scottie Scheffler", "probability": 0.335},
            {"name": "Rory McIlroy", "probability": 0.245},
            {"name": "Tommy Fleetwood", "probability": 0.23},
            {"name": "Matt Fitzpatrick", "probability": 0.225},
            {"name": "Jon Rahm", "probability": 0.175},
        ]
        normalize_display_probs(top5, mutually_exclusive=False)
        assert top5[0]["probability"] == 0.335, "top-5 leader must stay honest"
        assert sum(o["probability"] for o in top5) > 1.0, "not squashed to sum-1"

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
