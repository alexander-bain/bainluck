"""#2947 — an esports tournament name is context, not the away team's name.

Polymarket spells an esports fixture

    "Counter-Strike: Fluxo W7M vs Back to Back (BO3) - PGL Masters Bucharest:
     South American Open Qualifier #1 Playoffs"

Three fragments ride into the two team names at once: the GAME TITLE prefix
lands on team_a, and the best-of MARKER plus the TOURNAMENT land on team_b
(`_GAME_PROP_RE` splits on the last colon, so only the stage segment is
dropped). `_create_event_from_prediction_market` then stamps both verbatim, so
production held 366 events whose teams were "Counter-Strike: Fluxo W7M" and
"Back to Back (BO3) - PGL Masters Bucharest" — 23 still non-terminal, including
the eight PGL Masters Bucharest matches that were live on 2026-09-04.

WHY THIS IS NOT #2871's FIX, WIDENED. #2871 refuses to auto-create from a
CLOSED vocabulary of market types ("- Exact Score"). A tournament name is an
OPEN set: it cannot be enumerated, and cutting at the last dash would eat
hyphenated club names and merge "- Game 4"/"- Game 5" of a series. And these
are REAL matches — refusing to create would lose the fixture, the opposite of
what #2871 wanted. So the rule anchors on the one CLOSED token in the string,
the "(BOn)" marker. Measured on production 2026-09-04:

    366 / 366     polluted esports events carry "(BOn)" before the dash
    19,990/19,990 markets carrying "(BOn)" also carry a "<game title>: " prefix
    0 / 1,395     parsing titles carry a market type in the context
    0 / 366       clean counterparts exist, so no rename can mint a lookalike

AND IT DOES NOT WIDEN WHAT PARSES. The clean is applied to the extracted
matchup, not to the input string. 18,595 of the 19,990 markets have no trailing
stage segment and parse to None today; cleaning the string first would make
every one of them parseable and mint an event apiece. That flood is a separate
decision and is not taken here — see test_the_unparsed_shape_still_does_not_parse.
"""

import pytest

from app.utils.prediction_market_matching import (
    extract_matchup,
    is_derivative_market_name,
)


# Real production market names (futures_markets, source=polymarket, read
# 2026-09-04) — one per game title that actually reaches auto-create.
REAL_TITLES = [
    (
        "Counter-Strike: Inner Circle Esports vs Lazer Cats (BO1) - PGL Bucharest: "
        "European Open Qualifier #1 Playoffs",
        "Inner Circle Esports",
        "Lazer Cats",
    ),
    (
        "Rainbow Six Siege: Shaiikademy vs Circular Beers (BO3) - Asia-Pacific League "
        "Challenger Series: Oceania Group Stage",
        "Shaiikademy",
        "Circular Beers",
    ),
    (
        "Rocket League: Inner Sircle vs Karmine Corp (BO7) - RLCS EU Paris Major: "
        "Open 4 Playoffs",
        "Inner Sircle",
        "Karmine Corp",
    ),
    (
        "Valorant: Team RA'AD vs Vibranium Esports (BO3) - VCL MENA: "
        "Resilience Kickoff Group Stage - NA",
        "Team RA'AD",
        "Vibranium Esports",
    ),
]


class TestTheTournamentStopsBeingTheAwayTeam:
    """The ship: an esports card prints two team names."""

    @pytest.mark.parametrize("title,team_a,team_b", REAL_TITLES)
    def test_real_polymarket_title_yields_two_clean_team_names(self, title, team_a, team_b):
        m = extract_matchup(title)
        assert m is not None, f"{title!r} no longer parses at all"
        assert m.team_a == team_a, f"game-title prefix rode into team_a: {m.team_a!r}"
        assert m.team_b == team_b, f"marker/tournament rode into team_b: {m.team_b!r}"

    def test_the_live_pgl_match_reads_as_two_teams(self):
        """Event 15304464, live on 2026-09-04. Note the doubled space before "(BO3)"."""
        m = extract_matchup(
            "Counter-Strike: Fluxo W7M vs Back to Back  (BO3) - PGL Masters Bucharest: "
            "South American Open Qualifier #1 Playoffs"
        )
        assert (m.team_a, m.team_b) == ("Fluxo W7M", "Back to Back")

    def test_yes_team_follows_the_name_it_points_at(self):
        """A stale yes_team would orient the price at a team that no longer exists."""
        m = extract_matchup(
            "Counter-Strike: Inner Circle Esports vs Lazer Cats (BO1) - PGL Bucharest: "
            "European Open Qualifier #1 Playoffs"
        )
        assert m.yes_team == m.team_a == "Inner Circle Esports"

    def test_hyphenated_team_name_survives_the_cut(self):
        """"Counter-Strike" is itself hyphenated, and so are real club names.

        The rule must never reach for a dash: it cuts at the marker only.
        """
        m = extract_matchup(
            "Counter-Strike: Virtus.pro vs Lausanne-Sport (BO3) - IEM Beijing: Playoffs"
        )
        assert (m.team_a, m.team_b) == ("Virtus.pro", "Lausanne-Sport")


class TestTheRuleDoesNothingWithoutItsAnchor:
    """The kills. Each is a way this fix could have been too greedy."""

    def test_no_marker_means_no_cut(self):
        """A dash suffix with no "(BOn)" is untouched — the open set stays out."""
        m = extract_matchup("FC Thun vs. Lausanne-Sport")
        assert (m.team_a, m.team_b) == ("FC Thun", "Lausanne-Sport")

    def test_series_game_number_is_still_not_stripped(self):
        """#2871's guard: "- Game 4" is a distinct real game, not context."""
        m = extract_matchup("Mets vs. Dodgers - Game 4")
        assert m.team_b == "Dodgers - Game 4", (
            "stripping the series number would merge Games 1-5 into one event"
        )

    def test_ordinary_category_prefix_is_untouched(self):
        m = extract_matchup("NBA: Warriors vs Celtics")
        assert (m.team_a, m.team_b) == ("Warriors", "Celtics")

    def test_the_unparsed_shape_still_does_not_parse(self):
        """THE FLOOD KILL, and the reason the clean runs on the matchup.

        18,595 markets look like this — no trailing stage segment. They parse to
        None today and must keep doing so: each one that started parsing would
        mint an esports event, and nobody asked for 18,595 new events.
        """
        assert extract_matchup("Counter-Strike: TYLOO vs Rare Atom (BO3) - IEM Beijing") is None

    def test_derivative_suffix_is_still_refused(self):
        """#2871's refusal must be exactly as reachable as it was before."""
        title = "Counter-Strike: TYLOO vs Rare Atom (BO3) - Exact Score"
        assert is_derivative_market_name(title) is True
        assert extract_matchup(title) is None

    def test_a_market_type_in_the_context_is_not_laundered_into_a_clean_game(self):
        """THE FAKE KILL (CERT-880).

        A map prop carrying the marker would otherwise clean to a game-shaped
        "A vs B" and mint a convincing duplicate of the real fixture. Leaving
        the name obviously broken is the better failure. No production row does
        this today (0 of 1,395); the guard is what keeps it that way.
        """
        for title in (
            "Counter-Strike: A vs B (BO3) - Map 2 Winner: Playoffs",
            "Counter-Strike: A vs B (BO3) - IEM Beijing: Map 2 Winner",
        ):
            m = extract_matchup(title)
            assert m is not None and "(BO3)" in m.team_b, (
                f"{title!r} was cleaned into a game-shaped name: "
                f"{None if m is None else (m.team_a, m.team_b)}"
            )

    def test_a_tournament_whose_name_contains_winner_is_still_cleaned(self):
        """The guard matches whole segments, so it does not over-refuse."""
        m = extract_matchup(
            "Counter-Strike: A vs B (BO3) - Winners Bracket Finals: Playoffs"
        )
        assert (m.team_a, m.team_b) == ("A", "B")
