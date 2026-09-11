"""T2-1 (#5058): WHICH number a team card prints, and when it prints none.

The ship is "type Patriots and the row already says the two season answers".
This file guards the electing rules — every one of them exists because a
plausible alternative would have put a wrong number in front of a reader.

THE LADDER IN THESE TESTS IS REAL. `KXNFLWINS-27NE`, read from production
2026-09-11 ~05:10Z: seventeen rungs from `1+ wins` at 99.5% down to `17 wins` at
1%, with `10+ wins` at 46.5% the nearest to even. That is the sentence the
Patriots' row is supposed to carry, so it is the fixture.
"""

from __future__ import annotations

import pytest

from app.utils.season_answers import (
    MAKE_PLAYOFFS_KEY,
    SEASON_WINS_KEY,
    build_playoff_answer,
    build_wins_answer,
    format_wins_label,
    normalize_team_key,
    order_answers,
    parse_wins_rung,
    parse_wins_subject,
    parse_wins_ticker,
    pick_wins_rung,
    resolve_subject_to_team,
)

# Production, `KXNFLWINS-27NE`, 2026-09-11.
NE_LADDER: list[tuple[int, float]] = [
    (1, 0.995), (2, 0.995), (3, 0.960), (4, 0.940), (5, 0.930), (6, 0.835),
    (7, 0.805), (8, 0.730), (9, 0.665), (10, 0.465), (11, 0.305), (12, 0.220),
    (13, 0.120), (14, 0.065), (15, 0.030), (16, 0.020),
]

# The NFL grid's own team list, 2026-09-11 — the closed candidate set every
# subject is resolved against.
NFL_TEAMS = [
    {"name": n} for n in [
        "Arizona Cardinals", "Atlanta Falcons", "Baltimore Ravens", "Buffalo Bills",
        "Carolina Panthers", "Chicago Bears", "Cincinnati Bengals", "Cleveland Browns",
        "Dallas Cowboys", "Denver Broncos", "Detroit Lions", "Green Bay Packers",
        "Houston Texans", "Indianapolis Colts", "Jacksonville Jaguars",
        "Kansas City Chiefs", "Los Angeles Chargers", "Los Angeles Rams",
        "Las Vegas Raiders", "Miami Dolphins", "Minnesota Vikings",
        "New England Patriots", "New Orleans Saints", "New York Giants",
        "New York Jets", "Philadelphia Eagles", "Pittsburgh Steelers",
        "Seattle Seahawks", "San Francisco 49ers", "Tampa Bay Buccaneers",
        "Tennessee Titans", "Washington Commanders",
    ]
]


class TestTickerAndNameParsing:
    def test_the_ticker_yields_series_season_and_team_code(self):
        assert parse_wins_ticker("KXNFLWINS-27NE") == ("KXNFLWINS", "27", "NE")
        assert parse_wins_ticker("KXNBAWINS-27GSW") == ("KXNBAWINS", "27", "GSW")

    @pytest.mark.parametrize(
        "ticker",
        [
            None,
            "",
            # The PLAYOFF series, whose shape is `-27-NE`. Reading it as a wins
            # ticker would attach a playoff price to the wins sentence.
            "KXNFLPLAYOFF-27-NE",
            # A per-game head-to-head total, not a season ladder.
            "KXNFLH-27SEPNE",
            "KXNFLWINS-27",
            "kxnflwins-27ne",
        ],
    )
    def test_a_ticker_that_is_not_a_season_wins_ticker_is_refused(self, ticker):
        assert parse_wins_ticker(ticker) is None

    def test_the_subject_is_the_market_name_minus_the_venues_own_scaffolding(self):
        assert parse_wins_subject("Pro Football: New England Total Wins") == "New England"
        assert parse_wins_subject("Pro Basketball: Los Angeles C Total Wins") == "Los Angeles C"
        # No competition prefix is still a subject.
        assert parse_wins_subject("Boston Total Wins") == "Boston"

    @pytest.mark.parametrize(
        "name",
        [
            None,
            "",
            "Pro Football Playoff Qualifiers",
            "Pro Football Best Regular Season Record",
            "Kansas City vs New England: Head-to-Head Win Total",
        ],
    )
    def test_a_name_that_is_not_a_season_wins_market_has_no_subject(self, name):
        assert parse_wins_subject(name) is None

    def test_only_the_cumulative_rung_form_is_read_as_a_threshold(self):
        assert parse_wins_rung("10+ wins") == 10
        assert parse_wins_rung("9+ wins") == 9
        # `17 wins` is the top of an NFL ladder and MEANS "17+", but the bare
        # form means "exactly N" on other markets and we have not checked which
        # convention any given venue used. It prices at 1% and can never be the
        # rung nearest 50%, so refusing it costs the reader nothing.
        assert parse_wins_rung("17 wins") is None
        assert parse_wins_rung("Yes") is None
        assert parse_wins_rung(None) is None


class TestSubjectResolution:
    def test_a_place_name_reaches_the_one_club_it_prefixes(self):
        team = resolve_subject_to_team("New England", NFL_TEAMS)
        assert team is not None and team["name"] == "New England Patriots"

    def test_the_venues_one_letter_disambiguator_survives(self):
        """`Los Angeles C` and `Los Angeles R` are two clubs, not one guess."""
        assert resolve_subject_to_team("Los Angeles C", NFL_TEAMS)["name"] == "Los Angeles Chargers"
        assert resolve_subject_to_team("Los Angeles R", NFL_TEAMS)["name"] == "Los Angeles Rams"

    def test_an_ambiguous_prefix_resolves_to_nothing_rather_than_to_a_favourite(self):
        """`Los Angeles` fits two clubs, `New York` fits two, so neither answers.

        This is the whole safety property. A resolver that picked the first
        match would print the Rams' season on the Chargers' card and nobody
        would ever see a stack trace.
        """
        assert resolve_subject_to_team("Los Angeles", NFL_TEAMS) is None
        assert resolve_subject_to_team("New York", NFL_TEAMS) is None

    def test_a_subject_naming_no_club_in_this_league_resolves_to_nothing(self):
        # George Mason's Patriots are a real team and are not in this league.
        assert resolve_subject_to_team("George Mason", NFL_TEAMS) is None
        assert resolve_subject_to_team("", NFL_TEAMS) is None
        assert resolve_subject_to_team(None, NFL_TEAMS) is None

    def test_an_exact_name_wins_before_prefixing_is_tried(self):
        teams = [{"name": "Boston"}, {"name": "Boston Celtics"}]
        assert resolve_subject_to_team("Boston", teams)["name"] == "Boston"

    def test_accents_and_punctuation_fold(self):
        teams = [{"name": "Montreal Canadiens"}]
        assert resolve_subject_to_team("Montréal", teams)["name"] == "Montreal Canadiens"
        assert normalize_team_key("St. Louis  Blues") == "st louis blues"


class TestRungElection:
    def test_the_patriots_ladder_elects_the_rung_nearest_even(self):
        assert pick_wins_rung(NE_LADDER) == (10, 0.465)

    def test_the_order_the_rungs_arrive_in_does_not_change_the_answer(self):
        assert pick_wins_rung(list(reversed(NE_LADDER))) == (10, 0.465)

    def test_a_tie_reads_the_way_round_a_person_reads_it(self):
        """55% for `9+` beats 45% for `10+` when both are five points from even."""
        assert pick_wins_rung([(9, 0.55), (10, 0.45)]) == (9, 0.55)

    def test_a_ladder_that_contradicts_the_elected_rung_elects_nothing(self):
        """"10 or more" cannot be likelier than "9 or more" — for any season.

        Decidable from the rows alone, with no ground truth and no clock. The
        elected rung here is `9+` at 55%, and the very next rung says 62%: the
        sentence the card would print is refuted by the row beneath it.
        """
        broken = [(8, 0.70), (9, 0.55), (10, 0.62), (11, 0.30)]
        assert pick_wins_rung(broken) is None

    def test_a_wobble_in_the_tail_does_not_withhold_the_mid_ladder_answer(self):
        """Real production shape: `KXNFLWINS-27ATL`, 2026-09-11.

        Its only violation is `15+ 3%` -> `16+ 7%`, four points on a rung nobody
        trades. Whole-ladder monotonicity — the first rule written here —
        refused this ladder and twenty-four others, costing the reader 25 of 32
        NFL teams to protect them from a number they were never going to see.
        """
        atlanta = [
            (1, 0.965), (2, 0.94), (3, 0.88), (4, 0.815), (5, 0.71), (6, 0.615),
            (7, 0.495), (8, 0.385), (9, 0.295), (10, 0.235), (11, 0.11),
            (12, 0.075), (13, 0.05), (14, 0.04), (15, 0.03), (16, 0.07),
        ]
        assert pick_wins_rung(atlanta) == (7, 0.495)

    def test_an_inverted_ladder_elects_nothing_even_where_it_looks_local(self):
        """A ladder running the wrong way round is garbage as a whole.

        The local check alone cannot see this — every neighbouring pair of an
        inverted ladder is "coherent" in the mirror — so the direction of the
        whole thing is checked first.
        """
        inverted = [(1, 0.05), (2, 0.2), (3, 0.5), (4, 0.8), (5, 0.95)]
        assert pick_wins_rung(inverted) is None

    def test_equal_neighbouring_rungs_are_coherent(self):
        assert pick_wins_rung([(1, 0.99), (2, 0.99), (3, 0.52)]) == (3, 0.52)

    def test_a_settled_ladder_elects_nothing(self):
        """Every rung at 0/1 is settlement wearing a live price, not an answer."""
        settled = [(1, 1.0), (2, 1.0), (3, 0.99), (4, 0.01), (5, 0.0)]
        assert pick_wins_rung(settled) is None

    def test_an_empty_ladder_elects_nothing(self):
        assert pick_wins_rung([]) is None

    def test_the_label_names_the_regular_season_because_the_market_settles_on_it(self):
        assert format_wins_label(10) == "10+ regular-season wins"
        assert format_wins_label(9) == "9+ regular-season wins"


class TestPlayoffAnswerFromAGridCell:
    # The Patriots' cell, production `/api/playoffs/nfl`, 2026-09-11 04:25Z.
    LIVE_CELL = {
        "merged_probability": 0.4905,
        "sources": [
            {"source": "polymarket", "probability": 0.496, "market_name": "Pro Football: Team to Make Postseason"},
            {"source": "kalshi", "probability": 0.505, "market_name": "Pro Football Playoff Qualifiers"},
        ],
        "trend_24h": 0.48,
        "state": "live",
    }

    def test_a_live_cell_becomes_the_answer_the_grid_page_prints(self):
        answer = build_playoff_answer(self.LIVE_CELL, label="Make Playoffs", season="2026-27")
        assert answer["key"] == MAKE_PLAYOFFS_KEY
        assert answer["label"] == "Make Playoffs"
        # 🔴 The number is the grid's own blend, carried, not recomputed. One
        # question, one number — the dropdown and /playoffs/nfl cannot disagree
        # because there is only one computation.
        assert answer["probability"] == 0.4905
        assert [s["source"] for s in answer["sources"]] == ["polymarket", "kalshi"]

    @pytest.mark.parametrize("state", ["settled", "missing", None])
    def test_a_cell_that_is_not_live_is_an_honest_absence(self, state):
        cell = {**self.LIVE_CELL, "state": state}
        assert build_playoff_answer(cell, label="Make Playoffs", season="2026-27") is None

    def test_a_live_cell_with_no_number_is_an_honest_absence(self):
        cell = {**self.LIVE_CELL, "merged_probability": None}
        assert build_playoff_answer(cell, label="Make Playoffs", season="2026-27") is None

    def test_a_missing_cell_is_an_honest_absence(self):
        assert build_playoff_answer(None, label="Make Playoffs", season="2026-27") is None


class TestReadingOrder:
    def test_the_wins_answer_leads(self):
        wins = build_wins_answer(
            threshold=10, probability=0.465, season="2026-27", market_id=1,
            outcome_id=2, source="kalshi", market_name="Pro Football: New England Total Wins",
            observed_at=None,
        )
        playoffs = build_playoff_answer(
            TestPlayoffAnswerFromAGridCell.LIVE_CELL, label="Make Playoffs", season="2026-27"
        )
        assert [a["key"] for a in order_answers([playoffs, wins])] == [
            SEASON_WINS_KEY, MAKE_PLAYOFFS_KEY,
        ]

    def test_an_unrecognised_answer_is_dropped_not_appended(self):
        """The row has space for two facts that were designed into it.

        A third arriving from a future writer would change what a reader sees
        without anyone deciding it should, so the order is a whitelist.
        """
        wins = {"key": SEASON_WINS_KEY, "label": "10+ regular-season wins", "probability": 0.465}
        surprise = {"key": "division_odds", "label": "Win division", "probability": 0.3}
        assert order_answers([wins, surprise]) == [wins]

    def test_the_wins_answer_carries_its_own_provenance(self):
        answer = build_wins_answer(
            threshold=10, probability=0.465, season="2026-27", market_id=12230814,
            outcome_id=70119106, source="kalshi",
            market_name="Pro Football: New England Total Wins",
            observed_at="2026-09-11T04:00:00+00:00",
        )
        assert answer["market_id"] == 12230814
        assert answer["outcome_id"] == 70119106
        assert answer["season"] == "2026-27"
        # The price's own last movement, never the moment we cached it.
        assert answer["observed_at"] == "2026-09-11T04:00:00+00:00"
