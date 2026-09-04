"""#2993 — a tournament bracket is not a game, and a cut name is not a team.

Two shapes reach `_create_event_from_prediction_market` with names that no
two-team game can have. Both were measured on production 2026-09-04, after
#2947's repair applied, so this is the residue that fix does not reach.

THE CUT (15 events). Kalshi spelled a Valorant map market

    "VALORANT Masters - Masters Santiago (Playoffs: Playoffs): All Gamers vs. Paper Rex Map 1"

`_DASH_PROP_RE` (`^(.+?)\\s+[-–—]\\s+(.+?):\\s+(.+)$`) is non-greedy, so it stops
at the FIRST ": " after the dash — which lands INSIDE the parenthetical. team_b
becomes "Masters Santiago (Playoffs", and the half of the title holding the
real teams ("All Gamers vs. Paper Rex") is thrown away as the stat suffix. The
unbalanced paren is the fingerprint of that cut: 0 of 940,044 production market
NAMES are unbalanced, so an unbalanced parsed name is never something a source
sent us — it is always our own regex splitting a title mid-token.

THE STAGE (2 events). Polymarket's "FNCS Major 2: Europe - Grand Finals: Winner"
is a FIELD market with 50 mutually-exclusive competitor outcomes — the whole
Fortnite bracket. It parsed to "FNCS Major 2: Europe" vs "Grand Finals" and
minted a game. Event 15301525 is that row, and on 2026-09-03 it rendered as a
live card reading "Europe vs Finals".

WHY NOT A WIDER RULE. "Refuse to mint from a field market with more than two
competitor outcomes" would have caught the FNCS row on its shape rather than
its spelling, and it was measured before being rejected: field markets with 9
outcomes have minted 3,384 events in production, and 43-46 outcomes another
~100. The threshold has no safe value, so the refusal anchors on the names.

WHY AT THE MINT, NOT IN extract_matchup. The parse also feeds linking, blend
gating and dedup. Refusing there would change what LINKS as well as what is
created — the same reason `_clean_esports_matchup` post-processes the parsed
result instead of cleaning the input string (#2947). What parses today still
parses; it just stops stamping an event row.

BLAST RADIUS, measured on production 2026-09-04: of 231,419 events ever
created, exactly 17 would have been refused — the 15 cut + the 2 stage. Zero
collateral, which is what `TestRealTeamNamesSurvive` keeps true.
"""

from datetime import datetime, timezone

import pytest

from app.utils.prediction_market_matching import (
    bracket_refusal_reason,
    extract_matchup,
    is_tournament_stage_name,
    parens_are_unbalanced,
)


# Real production market names (futures_markets, read 2026-09-04) and the names
# the parser hands to auto-create for each.
REAL_CUT_TITLES = [
    "VALORANT Masters - Masters Santiago (Playoffs: Playoffs): "
    "All Gamers vs. Paper Rex Map 1",
    "VALORANT Masters - Masters Santiago (Playoffs: Playoffs): "
    "Paper Rex vs. NRG Map 3",
    "VALORANT Masters - Masters Santiago (Playoffs: Playoffs): "
    "BBL Esports vs. G2 Esports Map 2",
]

REAL_STAGE_TITLES = [
    "FNCS Major 2: Europe - Grand Finals: Winner",
    "FNCS Major 2: Na Central - Grand Finals: Winner",
]

# Real production team names carrying balanced parentheses (events table, read
# 2026-09-04). Every one of these must stay creatable.
REAL_PARENTHESISED_TEAMS = [
    "Miami (OH)",
    "Miami (FL)",
    "St. Thomas (MN)",
    "Queens (NC)",
    "Los Heretics (OLD)",
    "Lindenwood (Game 2)",
]


class TestTheCutIsDetectable:
    """An unbalanced paren is the proof that the parse lost the title."""

    @pytest.mark.parametrize("title", REAL_CUT_TITLES)
    def test_the_real_title_still_parses_to_the_cut_name(self, title):
        """Documents the defect rather than the fix: the parse is unchanged."""
        result = extract_matchup(title)
        assert result is not None
        assert result.team_b == "Masters Santiago (Playoffs", (
            "the cut moved — the refusal below is anchored to this exact shape"
        )

    @pytest.mark.parametrize("title", REAL_CUT_TITLES)
    def test_the_cut_name_is_refused(self, title):
        result = extract_matchup(title)
        assert bracket_refusal_reason(result.team_a, result.team_b) is not None

    def test_unbalanced_open_paren(self):
        assert parens_are_unbalanced("Masters Santiago (Playoffs") is True

    def test_unbalanced_close_paren(self):
        assert parens_are_unbalanced("Playoffs) Winner") is True

    @pytest.mark.parametrize("name", REAL_PARENTHESISED_TEAMS)
    def test_real_balanced_team_names_are_not_cuts(self, name):
        assert parens_are_unbalanced(name) is False

    def test_a_name_with_no_parens_is_not_a_cut(self):
        assert parens_are_unbalanced("Paper Rex") is False

    def test_empty_is_not_a_cut(self):
        assert parens_are_unbalanced("") is False


class TestAStageIsNotACompetitor:
    @pytest.mark.parametrize("title", REAL_STAGE_TITLES)
    def test_the_real_title_still_parses_to_the_stage_name(self, title):
        result = extract_matchup(title)
        assert result is not None
        assert result.team_b == "Grand Finals"

    @pytest.mark.parametrize("title", REAL_STAGE_TITLES)
    def test_the_stage_name_is_refused(self, title):
        result = extract_matchup(title)
        assert bracket_refusal_reason(result.team_a, result.team_b) is not None

    @pytest.mark.parametrize(
        "stage",
        [
            "Grand Finals", "Grand Final", "Finals", "Final",
            "Semifinals", "Semi-Final", "Quarterfinals",
            "Upper Bracket", "Lower Bracket Final",
            "Winners Bracket", "Losers Bracket",
            "Group Stage", "Swiss Stage", "Play-In", "Playoffs",
            "Round of 16", "Qualifier", "Main Event", "the Grand Finals",
        ],
    )
    def test_stage_names_are_recognised(self, stage):
        assert is_tournament_stage_name(stage) is True

    @pytest.mark.parametrize(
        "team",
        [
            # Real esports and sports clubs, read from production.
            "Paper Rex", "All Gamers", "G2 Esports", "Nongshim RedForce",
            "Team Heretics", "FURIA Esports", "BBL Esports",
            # A club whose name CONTAINS a stage word is not a stage.
            "Final Boss Esports", "Qualifier Gaming", "Bracket City FC",
        ],
    )
    def test_real_competitors_are_not_stages(self, team):
        assert is_tournament_stage_name(team) is False, (
            f"{team!r} read as a stage — its games would stop being created"
        )


class TestRealTeamNamesSurvive:
    """The control arm. A refusal this narrow must refuse nothing else."""

    @pytest.mark.parametrize(
        "team_a,team_b",
        [
            ("Paper Rex", "NRG"),
            # #2947's cleaned output: the market NAME ends in "Playoffs", but
            # the parsed teams are clean, so the game must still be created.
            ("Inner Circle Esports", "Lazer Cats"),
            ("Ohio", "Miami (OH)"),
            ("St. Thomas (MN)", "Lindenwood (Game 2)"),
            ("Vancouver FC", "FC Supra Du Quebec"),
        ],
    )
    def test_a_real_matchup_is_not_refused(self, team_a, team_b):
        assert bracket_refusal_reason(team_a, team_b) is None

    def test_the_2947_shape_still_parses_and_is_allowed(self):
        """End to end on a real #2947 title: parse, clean, then not refused."""
        result = extract_matchup(
            "Counter-Strike: Inner Circle Esports vs Lazer Cats (BO1) - "
            "PGL Bucharest: European Open Qualifier #1 Playoffs"
        )
        assert result is not None
        assert (result.team_a, result.team_b) == (
            "Inner Circle Esports", "Lazer Cats",
        )
        assert bracket_refusal_reason(result.team_a, result.team_b) is None


class _Matchup:
    def __init__(self, team_a, team_b):
        self.team_a = team_a
        self.team_b = team_b


class _Market:
    """The fields `_create_event_from_prediction_market` reads, and no others."""

    def __init__(self, name, source="polymarket"):
        self.source = source
        self.external_id = None
        self.name = name
        self.llm_sport_category = "esports"
        self.commence_time = datetime(2026, 9, 3, tzinfo=timezone.utc)


class TestAutoCreateRefusesBeforeTheDatabase:
    """BEHAVIOURAL, not source-inspection.

    `session=None` is the assertion: the refusal must land BEFORE anything
    reaches the registry, so a None session can never be dereferenced. A
    refusal that happened after `find_or_create_event` would already have
    written the bogus event.
    """

    @pytest.mark.asyncio
    @pytest.mark.parametrize("title", REAL_CUT_TITLES + REAL_STAGE_TITLES)
    async def test_the_real_titles_mint_nothing(self, title):
        from app.tasks.prediction_market_matching import (
            _create_event_from_prediction_market,
        )

        matchup = extract_matchup(title)
        assert matchup is not None, "the parse changed — this test is now vacuous"

        result = await _create_event_from_prediction_market(
            None, matchup, _Market(title),
            datetime(2026, 9, 3, tzinfo=timezone.utc),
        )
        assert result is None

    @pytest.mark.asyncio
    async def test_the_real_matchup_control_runs_past_the_refusal(self):
        """The control that makes the test above mean something.

        The SAME call for a real esports fixture must run PAST the refusal and
        only then fail on the None session. Without this, a function that
        returned None unconditionally would pass — and every esports fixture
        The Odds API does not cover would silently stop being created.
        """
        from app.tasks.prediction_market_matching import (
            _create_event_from_prediction_market,
        )

        with pytest.raises(AttributeError):
            await _create_event_from_prediction_market(
                None,
                _Matchup("Inner Circle Esports", "Lazer Cats"),
                _Market("Valorant: Inner Circle Esports vs Lazer Cats (BO1)"),
                datetime(2026, 9, 3, tzinfo=timezone.utc),
            )
