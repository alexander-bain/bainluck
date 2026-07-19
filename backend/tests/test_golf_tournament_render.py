"""Golf tournament-page render fixes (Queue #80 — #954 / #955).

#954: Bubble Watch make-cut read a blind cross-source average that blended
DataGolf's differentiated make_cut with one-sided ~0.5 Polymarket/Kalshi
placeholder "To Make the Cut" markets, flattening everyone to ~50%. The fix
prefers DataGolf (_prefer_datagolf_merge).

#955: the Win-chart contenders series plotted "Winner Nationality" (it matches
the "winner" type) instead of golfer winner fields. The fix excludes any name
matching _NON_WINNER_MARKET_RE from the evolution-market selection.
"""

from app.routes.golf import (
    _prefer_datagolf_merge,
    _NON_CONTENDER_WINNER_RE,
    _detect_market_type,
    _tournament_market_type,
    _round_outcome_in_field,
    _completed_round_ceiling,
    _round_scoped_market_complete,
    _match_key,
)


class TestPreferDataGolfMerge:
    def test_first_value_seeds(self):
        assert _prefer_datagolf_merge(None, False, 0.40, True) == (0.40, True)

    def test_datagolf_overrides_placeholder(self):
        # existing placeholder 0.51, DataGolf 0.85 arrives → take DataGolf
        val, is_dg = _prefer_datagolf_merge(0.51, False, 0.85, True)
        assert val == 0.85 and is_dg is True

    def test_datagolf_kept_over_later_placeholder(self):
        # existing DataGolf 0.85, placeholder 0.50 arrives → keep DataGolf
        val, is_dg = _prefer_datagolf_merge(0.85, True, 0.50, False)
        assert val == 0.85 and is_dg is True

    def test_same_class_values_average(self):
        # two non-DataGolf sources still average (prior behavior preserved)
        val, is_dg = _prefer_datagolf_merge(0.30, False, 0.50, False)
        assert val == 0.40 and is_dg is False

    def test_two_datagolf_values_average(self):
        val, is_dg = _prefer_datagolf_merge(0.80, True, 0.90, True)
        assert abs(val - 0.85) < 1e-9 and is_dg is True

    def test_differentiation_survives_real_values(self):
        # Scheffler: DataGolf 0.85 must not be diluted by the 0.51 placeholder
        scheffler, _ = _prefer_datagolf_merge(0.85, True, 0.51, False)
        # Puig: DataGolf 0.40 must not be lifted toward 0.5
        puig, _ = _prefer_datagolf_merge(0.40, True, 0.485, False)
        assert scheffler == 0.85 and puig == 0.40
        assert scheffler - puig > 0.4  # real spread preserved, not flat ~0.5


class TestWinnerChartExclusion:
    def test_nationality_market_excluded(self):
        assert _NON_CONTENDER_WINNER_RE.search("2026 U.S. Open: Winner Nationality")

    def test_country_and_tour_of_winner_excluded(self):
        assert _NON_CONTENDER_WINNER_RE.search("Country of Winner")
        assert _NON_CONTENDER_WINNER_RE.search("Tour of Winner")

    def test_real_winner_markets_not_excluded(self):
        # Critically, "PGA Tour: ... Winner" must survive — the broad
        # _NON_WINNER_MARKET_RE ("tour .* winner") would wrongly drop it.
        for name in (
            "PGA Tour: U.S. Open Winner",
            "U.S. Open - Winner",
            "U.S. Open Winner",
            "U.S. Open: Winner",
        ):
            assert not _NON_CONTENDER_WINNER_RE.search(name), name

    def test_nationality_classifies_as_winner_type(self):
        # This is WHY the name-exclusion is needed: the nationality market is
        # typed "winner" (it contains "Winner"), so the >5-outcome filter alone
        # let its 26 outcomes through into the contenders chart.
        type_key, _ = _detect_market_type("2026 U.S. Open: Winner Nationality")
        assert type_key == "winner"


class TestTournamentMarketType:
    """L2-89: the detail-grouping reclass — non-contender-winner props and
    last-chance qualifier fields move OUT of the winner group into `other`, so
    they surface in Related Futures instead of vanishing."""

    def test_real_winner_field_stays_winner(self):
        for name in (
            "The Open Championship Winner",
            "The Open Winner",
            "U.S. Open Winner",
        ):
            assert _tournament_market_type(name)[0] == "winner", name

    def test_qualifier_winner_downgraded_to_other(self):
        # "The Open: Last-Chance Qualifier Winner" is a separate qualifying field,
        # not the tournament winner — it must not pollute the winner group.
        assert _tournament_market_type("The Open: Last-Chance Qualifier Winner")[0] == "other"
        assert _tournament_market_type("U.S. Open Final Qualifying Winner")[0] == "other"

    def test_nationality_winner_downgraded_to_other(self):
        assert _tournament_market_type("Winner Nationality - Europe")[0] == "other"
        assert _tournament_market_type("2026 U.S. Open: Winner Nationality")[0] == "other"

    def test_placement_families_unaffected(self):
        # The reclass only touches "winner"-typed markets; placement families are
        # detected before it and pass through unchanged.
        assert _tournament_market_type("The Open Championship: Top 5 Finishers")[0] == "top_5"
        # Alex's ruling (The Open 2026): Top 40 is a per-golfer placement column
        # in the ONE golfer grid, not an "other" wall in Related Futures.
        assert _tournament_market_type("The Open Championship: Top 40 Finishers")[0] == "top_40"
        # Round-scoped Top 40 must still classify round_top, never the grid column.
        assert _tournament_market_type("The Open: Round 2 Top 40 Finishers")[0] == "round_top"
        assert _tournament_market_type("The Open Championship: To Make the Cut")[0] == "make_cut"
        assert _tournament_market_type("The Open Championship End of Round 1 Leader")[0] == "round_leader"


class TestRoundOutcomeFieldFilter:
    """The Open 2026 p0: Kalshi round-leader markets carry a ~165-name candidate
    roster padded with players NOT in the field (Tiger Woods, Phil Mickelson,
    John Daly, Ernie Els). They must never render as live round-leader outcomes.
    `_round_outcome_in_field` is the guard the round-group builder applies."""

    def _open_field(self):
        # A realistic slice of the actual 2026 Open field (via `_match_key`) —
        # NONE of Tiger Woods / Phil Mickelson / John Daly / Ernie Els are in it.
        return {
            _match_key(n)
            for n in ("Sam Burns", "Jackson Suber", "Lucas Herbert",
                      "Scottie Scheffler", "Rory McIlroy", "Tiger Christensen")
        }

    def test_out_of_field_name_dropped(self):
        # The exact reported bug: Tiger Woods is not in the field and must be
        # dropped even though the Kalshi outcome carries a (phantom) probability.
        field = self._open_field()
        for name in ("Tiger Woods", "Phil Mickelson", "John Daly", "Ernie Els", "Zach Johnson"):
            assert _round_outcome_in_field(name, False, field, True) is False, name

    def test_field_competitor_kept(self):
        field = self._open_field()
        for name in ("Sam Burns", "Jackson Suber", "Lucas Herbert", "Rory McIlroy"):
            assert _round_outcome_in_field(name, False, field, True) is True, name

    def test_tiger_christensen_kept_tiger_woods_dropped(self):
        # A real amateur named "Tiger" IS in the field; the celebrity "Tiger
        # Woods" is not. The guard must distinguish them, not blanket-match "Tiger".
        field = self._open_field()
        assert _round_outcome_in_field("Tiger Christensen", False, field, True) is True
        assert _round_outcome_in_field("Tiger Woods", False, field, True) is False

    def test_graded_winner_never_dropped(self):
        # The authoritative round winner is kept even if its name key somehow
        # misses the roster — a settled result is never filtered away.
        assert _round_outcome_in_field("Some Qualifier", True, self._open_field(), True) is True

    def test_no_authoritative_field_is_a_no_op(self):
        # No DataGolf field → filter OFF → nothing is dropped (we must not risk
        # removing a real entrant we can't verify against an authoritative roster).
        assert _round_outcome_in_field("Tiger Woods", False, set(), False) is True
        assert _round_outcome_in_field("Anyone At All", False, {"scottie scheffler"}, False) is True


class TestCompletedRoundCeiling:
    """The Open 2026 p0: completed rounds are inferred from the round LEADERS
    (graded via is_winner) so Top-N projection markets — which never carry their
    own is_winner — settle by round number instead of showing stale live odds."""

    def test_highest_graded_leader_is_the_ceiling(self):
        # The Open live state: R1/R2/R3 leaders graded, R4 in progress.
        rows = [
            ("leader", 1, True), ("leader", 2, True), ("leader", 3, True),
            ("leader", 4, False),                       # round 4 still live
            ("top", 1, False), ("top", 2, False), ("top", 3, False),
        ]
        assert _completed_round_ceiling(rows) == 3

    def test_no_graded_leader_settles_nothing(self):
        # Nothing graded yet → ceiling 0 → no round settles (all stay live).
        rows = [("leader", 1, False), ("top", 1, False), ("top", 2, False)]
        assert _completed_round_ceiling(rows) == 0

    def test_graded_topn_does_not_count(self):
        # Only a LEADER marks a round done. A graded Top-N must NOT lift the
        # ceiling (guards against a stray is_winner on a projection market).
        rows = [("top", 2, True), ("leader", 1, True)]
        assert _completed_round_ceiling(rows) == 1

    def test_partial_completion(self):
        rows = [("leader", 1, True), ("leader", 2, False)]
        assert _completed_round_ceiling(rows) == 1

    def test_empty_is_zero(self):
        assert _completed_round_ceiling([]) == 0


class TestRoundScopedMarketComplete:
    """The Open 2026 p0 follow-up: round-scoped SCORING props ("Round 1 Scores",
    "Round 2 Lowest Score") settle by the same completed-round ceiling — a
    finished round's score prop must not keep showing live odds. Live/future
    rounds and tournament-wide records survive."""

    def test_past_round_scoring_props_complete(self):
        # Ceiling 3 (R1–R3 done). Every round <= 3 scoring prop is settled.
        for name in (
            "The Open Championship: Round 1 Scores",
            "The Open Championship: Round 1 Lowest Score",
            "The Open Championship: Round 2 Scores",
            "The Open Championship: Round 3 Lowest Score",
        ):
            assert _round_scoped_market_complete(name, 3) is True, name

    def test_live_round_survives(self):
        # Round 4 is in play (> ceiling 3) — its props stay live.
        assert _round_scoped_market_complete("The Open Championship: End of Round 4 Stroke Margin", 3) is False

    def test_tournament_wide_record_survives(self):
        # No round number → tournament-wide, never a completed-round prop.
        assert _round_scoped_market_complete("The Open Championship: Lowest Round Score", 3) is False
        assert _round_scoped_market_complete("The Open Championship: Hole-in-One", 3) is False

    def test_nothing_completed_settles_nothing(self):
        # Ceiling 0 (pre-tournament / no round graded) → nothing settles.
        assert _round_scoped_market_complete("The Open Championship: Round 1 Scores", 0) is False

    def test_empty_name_is_safe(self):
        assert _round_scoped_market_complete("", 3) is False
        assert _round_scoped_market_complete(None, 3) is False
