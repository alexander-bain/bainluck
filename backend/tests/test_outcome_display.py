"""#993: shared outcome-display rules (search + typeahead + futures DETAIL).

Guards the ONE source of truth so the detail page can't drift back to showing
"Other 100%" while search shows the real leader.
"""

import pytest

from app.utils.outcome_display import (
    display_rank_order,
    drop_duplicate_binary_legs,
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


# ===========================================================================
# UX-P126 / F5 — never rank a placeholder (#1696, display half)
# ===========================================================================


class TestF5RolePlaceholders:
    """`Party`, `Manager`, `Driver` and `Coach` were in NO placeholder regex, so 69
    markets ranked an enumerated slot as their answer. Every name below was read off
    production on 2026-08-24."""

    @pytest.mark.parametrize("name", [
        "Party A", "Party C", "Party Z", "Party AA", "Party AF",
        "Manager A", "Manager K", "Manager Z", "Manager AD",
        "Driver A", "Driver J",
        "Coach A", "Coach N", "Coach T",
    ])
    def test_role_slots_are_placeholders(self, name):
        assert is_placeholder_outcome_name(name) is True, name

    @pytest.mark.parametrize("name", ["Party 2", "Party 9", "Party 40"])
    def test_party_also_enumerates_numerically(self, name):
        # One 40-way coalition ladder numbers its slots instead of lettering them.
        assert is_placeholder_outcome_name(name) is True, name

    @pytest.mark.parametrize("name", [
        # Real entities that START with a role word — the OTHER direction.
        "Party of Regions", "Labour Party", "Party for Freedom",
        "Manager United",            # not a letter
        "Coach Prime", "Coach Cal",
        "Driver 44",                 # a NUMBERED driver is a real identity
        "Driver Ricciardo",
        # And the pre-existing survivors must be untouched by the widening.
        "Team GB", "Team USA", "Cleveland Cavaliers", "Donald Trump",
        "Yes", "No", "Democratic", "Republican",
    ])
    def test_real_names_survive_the_widening(self, name):
        assert is_placeholder_outcome_name(name) is False, name

    def test_coach_k_is_a_slot_here_and_that_is_deliberate(self):
        # "Coach K" is a real nickname in college basketball. In THIS corpus it is
        # n=2 sitting inside an unbroken Coach A..T enumeration on anonymized
        # next-head-coach markets, so it is a slot like its 19 siblings. Recorded
        # explicitly so the trade-off is a decision on the record, not an accident:
        # if a market ever ships "Coach K" as a real nominee it will need a name,
        # and the fix is to ingest the name, not to un-suppress the letter.
        assert is_placeholder_outcome_name("Coach K") is True

    def test_the_letter_bound_is_not_truncated_at_L(self):
        # A bound that stops at L leaves "Coach N"/"Party X" ranking — which is the
        # defect, not a narrower version of the fix.
        for letter in "MNOPQRSTUVWXYZ":
            assert is_placeholder_outcome_name(f"Party {letter}") is True, letter


class TestF5DominantField:
    """A field outcome priced ~100% is an untraded midpoint / no-bid ask, never an
    answer. It must not hold a leader OR a top-N slot."""

    def test_other_at_100_leaves_the_top_n(self):
        # /api/futures/16631690 live 2026-08-24: a real leader headlined correctly
        # and "Other" at 100% sat at served position 2 — inside every top-N.
        outs = [
            {"name": "Byrum Brown", "probability": 0.475},
            {"name": "Other", "probability": 1.0},
            {"name": "Duce Robinson", "probability": 0.475},
            {"name": "Brendan Sorsby", "probability": 0.465},
        ]
        ranked = display_rank_order(
            outs, lambda o: o["name"], lambda o: o["probability"]
        )
        assert [o["name"] for o in ranked[:3]] == [
            "Byrum Brown", "Duce Robinson", "Brendan Sorsby",
        ]
        # Demoted, not deleted — the field's share stays visible.
        assert ranked[-1]["name"] == "Other"
        assert len(ranked) == 4

    def test_a_field_that_carries_real_mass_keeps_its_rank(self):
        # THE OTHER DIRECTION. A wide-open race where "Other" genuinely holds most
        # of the mass is INFORMATION. Only the ~100% artifact is suppressed.
        outs = [
            {"name": "Other", "probability": 0.55},
            {"name": "Gavin Newsom", "probability": 0.22},
        ]
        ranked = display_rank_order(
            outs, lambda o: o["name"], lambda o: o["probability"]
        )
        assert [o["name"] for o in ranked] == ["Other", "Gavin Newsom"]

    def test_threshold_boundary(self):
        below = [{"name": "Other", "probability": 0.89}, {"name": "Real", "probability": 0.1}]
        at = [{"name": "Other", "probability": 0.9}, {"name": "Real", "probability": 0.1}]
        key, prob = (lambda o: o["name"]), (lambda o: o["probability"])
        assert display_rank_order(below, key, prob)[0]["name"] == "Other"
        assert display_rank_order(at, key, prob)[0]["name"] == "Real"

    def test_leader_pick_order_still_demotes_a_plurality_field_one_slot(self):
        # The pre-F5 behaviour is preserved for sub-threshold fields.
        outs = [{"name": "Other", "probability": 0.52},
                {"name": "Cleveland Cavaliers", "probability": 0.27}]
        leader_pick_order(outs)
        assert outs[0]["name"] == "Cleveland Cavaliers"
        assert outs[1]["name"] == "Other"

    def test_leader_pick_order_pushes_a_dominant_field_all_the_way_down(self):
        outs = [{"name": "Other", "probability": 1.0},
                {"name": "Democratic", "probability": 0.585},
                {"name": "Republican", "probability": 0.405}]
        leader_pick_order(outs)
        assert [o["name"] for o in outs] == ["Democratic", "Republican", "Other"]


class TestF5NeverEmpties:
    """A sort helper must never turn a card into nothing. Honest-empty is a
    SURFACE decision (ruling 027); a silently zero-outcome card is worse than a
    labelled one."""

    def test_an_all_placeholder_market_is_returned_unchanged(self):
        outs = [{"name": f"Party {c}", "probability": 1.0} for c in "ABC"]
        ranked = display_rank_order(
            outs, lambda o: o["name"], lambda o: o["probability"]
        )
        assert len(ranked) == 3
        assert [o["name"] for o in ranked] == ["Party A", "Party B", "Party C"]

    def test_an_all_field_market_is_returned_unchanged(self):
        outs = [{"name": "Other", "probability": 1.0},
                {"name": "The Field", "probability": 0.95}]
        ranked = display_rank_order(
            outs, lambda o: o["name"], lambda o: o["probability"]
        )
        assert [o["name"] for o in ranked] == ["Other", "The Field"]

    def test_a_real_fifty_fifty_field_renders_untouched(self):
        # The directive's explicit both-directions ask: a real 50/50 still renders.
        outs = [{"name": "Yes", "probability": 0.5}, {"name": "No", "probability": 0.5}]
        ranked = display_rank_order(
            outs, lambda o: o["name"], lambda o: o["probability"]
        )
        assert [o["name"] for o in ranked] == ["Yes", "No"]
        assert [o["probability"] for o in ranked] == [0.5, 0.5]

    def test_missing_probabilities_do_not_crash_or_reorder(self):
        outs = [{"name": "Alice"}, {"name": "Other"}, {"name": "Bob", "probability": None}]
        ranked = display_rank_order(
            outs, lambda o: o.get("name"), lambda o: o.get("probability")
        )
        assert [o["name"] for o in ranked] == ["Alice", "Other", "Bob"]


class TestF5LiveSpecimens:
    """Production shapes read off the API on 2026-08-24, kept as regression anchors
    so a future refactor has to reproduce the actual user-visible fix."""

    def test_party_c_100_percent_becomes_democratic_vs_republican(self):
        # /api/futures/112910 "Which party wins 2028 US Presidential Election?"
        # served 15 rows led by "Party C 100%". The site's biggest political
        # question was unreadable.
        outs = [{"name": f"Party {c}", "probability": 1.0} for c in "CJIKFEDBGHLA"]
        outs += [
            {"name": "Democratic", "probability": 0.585},
            {"name": "Republican", "probability": 0.405},
            {"name": "Other", "probability": 1.0},
        ]
        ranked = display_rank_order(
            outs, lambda o: o["name"], lambda o: o["probability"]
        )
        assert [o["name"] for o in ranked] == ["Democratic", "Republican", "Other"]

    def test_next_magic_head_coach_leads_with_a_person(self):
        # /api/futures/16631686 served "Coach H 100%" over 15 real candidates.
        outs = [{"name": f"Coach {c}", "probability": 1.0} for c in "HJLNACB"]
        outs += [
            {"name": "Other", "probability": 1.0},
            {"name": "Sean Sweeney", "probability": 1.0},
            {"name": "Sam Cassell", "probability": 0.101},
        ]
        ranked = display_rank_order(
            outs, lambda o: o["name"], lambda o: o["probability"]
        )
        assert ranked[0]["name"] == "Sean Sweeney"
        assert ranked[1]["name"] == "Sam Cassell"
        assert ranked[-1]["name"] == "Other"


class TestF5FeedUsesSharedPipeline:
    """#993's lesson was THREE divergent copies. The feed built `top_outcomes` off
    raw `sorted_outcomes` and never went through this module at all — so it was
    copy three, and the leader it named was its own. Source-level assertion,
    mirroring TestDetailUsesSharedPipeline."""

    @pytest.mark.parametrize("fn_name", ["_score_futures", "_score_sports_mode_futures"])
    def test_feed_ranks_through_display_rank_order_before_slicing_top_n(self, fn_name):
        import inspect
        from app.routes import feed

        src = inspect.getsource(getattr(feed, fn_name))
        assert "display_rank_order" in src, fn_name
        # ORDER matters: filtering after the slice would leave the placeholder in
        # the leader slot and merely shorten the list behind it.
        assert src.index("display_rank_order") < src.index("sorted_outcomes[:10]"), (
            f"{fn_name}: display_rank_order must run BEFORE the top-10 slice"
        )


# ===========================================================================
# UX-P188 — a field never answers "who will…" with its own complement
# ===========================================================================

# Real Polymarket condition ids, read off production 2026-08-30. The three rows
# below are ONE proposition ("will Zoë Kravitz be a bridesmaid") ingested three
# times: once under her name, once as its YES leg, once as its NO leg.
_ZOE = "0xeda9eb14a054e234a72ab94dc45a6302ca702a6a8e5e7c270e7c91628ac8e084"
_GIGI = "0xdc736508860c34b8c28140480a0091734469d2587bc20cd5f87893df0509aa22"


def _leg(name, prob, xid):
    from types import SimpleNamespace

    return SimpleNamespace(name=name, probability=prob, external_id=xid)


def _xid(o):
    return o.external_id


class TestDropDuplicateBinaryLegs:
    """The bridesmaids/Big-Brother class: a named field that also carries the
    Yes/No decomposition of ONE of its own candidates, whose NO leg (the
    complement of a long shot) outranks every real candidate."""

    def test_bridesmaids_lead_card_stops_answering_a_who_question_with_no(self):
        # /entertainment .trending[0] as served 2026-08-30: "No 64.5% | Yes 35.5%
        # | Gigi Hadid 0.4%" for "Who will Taylor Swift's bridesmaids be?"
        field = [
            _leg("No", 0.645, f"{_ZOE}_no"),
            _leg("Yes", 0.355, f"{_ZOE}_yes"),
            _leg("Gigi Hadid", 0.0035, _GIGI),
            _leg("Zoë Kravitz", 0.0005, _ZOE),
        ]
        kept = drop_duplicate_binary_legs(field, _xid)
        assert [o.name for o in kept] == ["Gigi Hadid", "Zoë Kravitz"]
        # The point of the ship: the answer to a "who will" question is a person.
        assert kept[0].name not in ("Yes", "No")

    def test_the_no_leg_alone_is_dropped(self):
        # One-directional guards were UX-P187's surviving mutation. Assert each
        # leg independently so removing EITHER branch of the suffix test fires.
        field = [_leg("No", 0.745, f"{_ZOE}_no"), _leg("Zoë Kravitz", 0.255, _ZOE)]
        assert [o.name for o in drop_duplicate_binary_legs(field, _xid)] == [
            "Zoë Kravitz"
        ]

    def test_the_yes_leg_alone_is_dropped(self):
        field = [_leg("Yes", 0.91, f"{_ZOE}_yes"), _leg("Zoë Kravitz", 0.815, _ZOE)]
        assert [o.name for o in drop_duplicate_binary_legs(field, _xid)] == [
            "Zoë Kravitz"
        ]

    def test_a_genuine_binary_market_keeps_both_legs(self):
        # The non-regression that makes the predicate safe: a real Yes/No market
        # carries the legs with NO base sibling, so neither is a duplicate.
        field = [_leg("Yes", 0.6, f"{_ZOE}_yes"), _leg("No", 0.4, f"{_ZOE}_no")]
        assert len(drop_duplicate_binary_legs(field, _xid)) == 2

    def test_a_kalshi_ladder_with_a_real_yes_outcome_is_untouched(self):
        # CONTROL, and the reason the predicate is id-anchored rather than a name
        # test. Market 112782 ("Will Trump end income tax for people earning under
        # $150k?") serves a legitimate `Yes` whose siblings are date rungs; Kalshi
        # tickers delimit with `-`, never `_`, so no correspondence exists.
        field = [
            _leg("Yes", 0.0255, "KXTAXWAIVE-26-27"),
            _leg("Before 2026", 0.010, "KXTAXWAIVE-26"),
            _leg("Before June 2026", 0.001, "KXTAXWAIVE-26-JUNE"),
        ]
        assert drop_duplicate_binary_legs(field, _xid) == field

    def test_a_yes_named_outcome_without_the_suffix_survives(self):
        # Proves the drop keys on the ID, not the word "Yes": same names, no suffix.
        field = [_leg("Yes", 0.6, "aaa"), _leg("No", 0.4, "bbb")]
        assert len(drop_duplicate_binary_legs(field, _xid)) == 2

    def test_a_suffixed_id_whose_base_is_absent_survives(self):
        # The base sibling is what makes a leg a DUPLICATE. Without it there is
        # nothing being printed twice, so the row stays.
        field = [_leg("Yes", 0.6, "ghost_yes"), _leg("Gigi Hadid", 0.4, _GIGI)]
        assert len(drop_duplicate_binary_legs(field, _xid)) == 2

    def test_the_base_sibling_always_survives_so_a_field_cannot_be_emptied(self):
        # This is WHY the helper needs no explicit never-empty guard, and it is
        # the property that guard would have been standing in for: whatever is
        # dropped, the row it duplicated is still there.
        for field in (
            [_leg("No", 0.645, f"{_ZOE}_no"), _leg("Zoë Kravitz", 0.0005, _ZOE)],
            [
                _leg("Yes", 0.355, f"{_ZOE}_yes"),
                _leg("No", 0.645, f"{_ZOE}_no"),
                _leg("Zoë Kravitz", 0.0005, _ZOE),
            ],
        ):
            kept = drop_duplicate_binary_legs(field, _xid)
            assert kept, "a non-empty field must never be emptied"
            assert _ZOE in {o.external_id for o in kept}

    def test_only_the_trailing_suffix_is_stripped(self):
        # The suffix is a SUFFIX, so the base is what remains after removing the
        # LAST `_`-segment. Every id in the live 514 is suffix-free hex, which is
        # why a leading-split reads identically on them — this pins the compound
        # case those fixtures cannot distinguish (a left-split yields "poly" and
        # silently stops dropping).
        field = [
            _leg("Yes", 0.6, "poly_336594_yes"),
            _leg("Gigi Hadid", 0.4, "poly_336594"),
        ]
        assert [o.name for o in drop_duplicate_binary_legs(field, _xid)] == [
            "Gigi Hadid"
        ]

    def test_a_falsy_external_id_is_never_treated_as_a_base(self):
        # Without the truthiness filter on the id set, a row with external_id ""
        # would make a sibling literally named "_yes" look like its duplicate.
        field = [_leg("Blank", 0.5, ""), _leg("_yes", 0.4, "_yes")]
        assert len(drop_duplicate_binary_legs(field, _xid)) == 2


class TestP188SharedFilterRoutesThroughTheHelper:
    """#993's lesson again: politics/economics/entertainment share one
    `clean_outcomes`, and weather keeps a FOURTH copy. Both must call the helper
    rather than reimplementing the suffix test."""

    def test_dashboard_clean_outcomes_drops_the_legs(self):
        from app.utils.cross_source_matching import clean_outcomes

        field = [
            _leg("No", 0.745, f"{_ZOE}_no"),
            _leg("Melody Morris", 0.265, "0xceaa29f296bdc7793226304eae"),
            _leg("Zoë Kravitz", 0.03, _ZOE),
        ]
        assert [o.name for o in clean_outcomes(field)] == [
            "Melody Morris",
            "Zoë Kravitz",
        ]

    def test_weather_clean_outcomes_drops_the_legs(self):
        from app.routes.weather import _clean_outcomes

        field = [
            _leg("No", 0.745, f"{_ZOE}_no"),
            _leg("Denver", 0.265, "0xceaa29f296bdc7793226304eae"),
            _leg("Zoë Kravitz", 0.03, _ZOE),
        ]
        assert [o.name for o in _clean_outcomes(field)] == ["Denver", "Zoë Kravitz"]

    def test_the_garbage_filter_still_runs_alongside_the_drop(self):
        # Both responsibilities, one function — a mutation deleting either fires.
        from app.utils.cross_source_matching import clean_outcomes

        field = [
            _leg("Player A", 0.9, "xid-placeholder"),
            _leg("No", 0.745, f"{_ZOE}_no"),
            _leg("Zoë Kravitz", 0.03, _ZOE),
        ]
        assert [o.name for o in clean_outcomes(field)] == ["Zoë Kravitz"]
