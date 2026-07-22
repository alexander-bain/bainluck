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
        # A coherent ME field with mild overround (sum 1.4, within _FIELD_SUM_MAX)
        # squeezes to ~100%. (Sums far past that are independent binaries — see
        # test_overrounded_independent_field_keeps_raw.)
        outs = [{"probability": 0.6}, {"probability": 0.5}, {"probability": 0.3}]
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

    def test_make_cut_overround_protected_even_if_misflagged_me(self):
        # #1200: the SAME make-cut field summing >> 100% (0.87+0.885+0.84 = 2.595)
        # is ALSO protected by the raw-sum overround guard even when mis-flagged
        # mutually_exclusive=True — the sum guard catches it before the squeeze.
        # Defense in depth on top of the ME gate (both a mis-flag and a dropped
        # gate now render raw). Previously this collapsed the leader to ~1%.
        make_cut = [{"probability": 0.87}, {"probability": 0.885}, {"probability": 0.84}]
        assert sum(o["probability"] for o in make_cut) > 1.60  # over the ceiling
        normalize_display_probs(make_cut, mutually_exclusive=True)
        assert make_cut[0]["probability"] == 0.87, "overround field kept raw"

    def test_overrounded_independent_field_keeps_raw(self):
        # #1200: a 184-way independent-binary GC field (Kalshi Tour de France) sums
        # ~281% (heavy overround). Even flagged mutually_exclusive=True, it must
        # render RAW per-rider prices — never squeezed to ~100% (which crushed
        # Pogačar's -1718/94.5% into a false 33.6% coin-flip). Regression guard.
        field = [{"name": "Pogacar", "probability": 0.945}]
        # 183 longshots so the field sums ~2.8x (independent binaries)
        field += [{"name": f"r{i}", "probability": 0.01} for i in range(183)]
        raw_sum = sum(o["probability"] for o in field)
        assert raw_sum > 2.5, "sanity: heavy independent-binary overround"
        normalize_display_probs(field, mutually_exclusive=True)
        assert field[0]["probability"] == 0.945, "leader keeps raw 94.5%, not diluted"
        assert sum(o["probability"] for o in field) == raw_sum, "field left raw"

    def test_coherent_field_still_normalized_at_66_way(self):
        # #1200 counterpart: a large but COHERENT field (World Cup 66-team winner,
        # raw sum ~1.15 < ceiling) STILL normalizes — the guard keys on sum, not
        # outcome count, so the WC champion display is unaffected.
        field = [{"name": "Spain", "probability": 0.15}, {"name": "France", "probability": 0.15}]
        field += [{"name": f"t{i}", "probability": 0.017} for i in range(50)]  # ~0.85
        assert sum(o["probability"] for o in field) < 1.60
        normalize_display_probs(field, mutually_exclusive=True)
        # squeezed from ~1.15 down to ~1.0 (per-outcome 4dp rounding across 52 rows)
        assert abs(sum(o["probability"] for o in field) - 1.0) < 0.02, "coherent field squeezed"

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


class TestPlaceholderMidpointStrip:
    """#1201: strip Kalshi untraded-midpoint (exactly-0.5) placeholders from a
    CORRUPTED mutually-exclusive field before the overround guard, so a real
    leader isn't left showing an absurd raw price (Drake Maye 26.5% for SB MVP)."""

    def test_corrupted_mvp_field_normalizes_real_outcomes(self):
        # Mirrors market 479: dozens of untraded candidates parked at EXACTLY 0.5
        # inflate the field sum past the #1200 ceiling, so WITHOUT the strip the
        # whole field renders raw. With the strip, the 12 placeholders are dropped
        # and the coherent real field (leader 0.06 among many small candidates)
        # normalizes to sum ~1.0 with the leader at low single digits.
        placeholders = [{"name": f"Untraded {i}", "probability": 0.5} for i in range(12)]
        real = [{"name": "Drake Maye", "probability": 0.06}]
        real += [{"name": f"Cand {i}", "probability": 0.03} for i in range(38)]
        outs = placeholders + real
        assert sum(o["probability"] for o in outs) > 3.0  # corrupted (1967%-style)
        # After stripping the 12 placeholders the real field sums ~1.20 — over the
        # 105% overround threshold (so it normalizes) yet within the #1200 band.

        normalize_display_probs(outs, mutually_exclusive=True)

        # Placeholders removed; only the real outcomes remain.
        assert len(outs) == 39
        assert all(o["probability"] != 0.5 for o in outs)
        # Real field normalized to ~100%.
        assert abs(sum(o["probability"] for o in outs) - 1.0) < 0.02
        # Leader is now low single digits — NOT the absurd raw 26.5%/6%-raw.
        leader = max(o["probability"] for o in outs)
        assert leader < 0.10, f"leader should be low single digits, got {leader}"

    def test_legit_two_way_coinflip_untouched(self):
        # A genuine 2-way Yes/No at 0.5/0.5 (only 2 halves) must NOT be stripped.
        outs = [{"name": "Yes", "probability": 0.5}, {"name": "No", "probability": 0.5}]
        normalize_display_probs(outs, mutually_exclusive=True)
        assert len(outs) == 2
        assert outs[0]["probability"] == 0.5
        assert outs[1]["probability"] == 0.5

    def test_coherent_field_with_a_single_half_untouched(self):
        # A coherent one-winner field summing ~1.0 with a single legit 0.5 leader
        # must be left as-is (no placeholder run → no strip; sum in band → kept).
        outs = [
            {"name": "Chiefs", "probability": 0.5},
            {"name": "Bills", "probability": 0.3},
            {"name": "Eagles", "probability": 0.2},
        ]
        normalize_display_probs(outs, mutually_exclusive=True)
        assert len(outs) == 3
        assert outs[0]["probability"] == 0.5
        assert abs(sum(o["probability"] for o in outs) - 1.0) < 0.01

    def test_independent_binary_field_without_halves_still_raw(self):
        # #1200 regression: an overrounded independent-binary field with NO 0.5
        # run (varied prices) is untouched by the strip and kept RAW by the guard.
        field = [{"name": "Pogacar", "probability": 0.945}]
        field += [{"name": f"r{i}", "probability": 0.01} for i in range(183)]
        raw_sum = sum(o["probability"] for o in field)
        normalize_display_probs(field, mutually_exclusive=True)
        assert field[0]["probability"] == 0.945
        assert sum(o["probability"] for o in field) == raw_sum


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
