"""#3026 — a question is not a game, and a name holding a matchup is not a team.

Four shapes reach `_create_event_from_prediction_market` and mint a two-team
game out of a market TITLE. All four were measured on production 2026-09-04, on
top of #2993's fix: `bracket_refusal_reason` refuses **0** of them, so this is
residue that fix does not reach.

THE EMBEDDED MATCHUP (164 events). Kalshi's broadcast props are titled
"Announcers at Duke vs Virginia" and "Announcers at UConn vs St. John's". The
parse splits on " at ", so team_a is the *series* name "Announcers" and team_b
is the *entire game*, "Duke vs Virginia". A real club is never named "<A> vs
<B>", and the two rows this catches that are NOT announcers — "University" vs
"Albany vs. Buffalo" and "University" vs "Albany vs Vermont" — are equally
fictional.

THE QUESTION HEAD (99 events). Kalshi: "What will the announcers say during New
Zealand vs Egypt" → "What will the announcers say during New Zealand" vs
"Egypt". Polymarket: "Who will win Bucks vs. Heat: Game 2?" → "Who will win
Bucks" vs "Heat". The tail of the split is a real team; the head is a question
and never is.

THE WILL-CLAUSE (11 events, 7 of them still NON-TERMINAL on 2026-09-04).
Polymarket: "Will Greg Mueller Finish Top 3 at the 2026 WSOP Main Event" →
"Will Greg Mueller Finish Top 3" vs "the 2026 WSOP Main Event". Event 15301524
is that row, and it rendered as a live page with a 33%/67% head-to-head hero
reading "WGM 3" vs "T2W Event", a drawn win-probability curve, and an unrelated
BLAST Open Porto award list grafted on as the two teams' panels.

WHY THE TOKEN FLOOR ON "WILL". `Will` is also a first name. A bare `^will\\s`
refuses the UFC fighters **Will Fleury**, **Will Davis** and **Will Harrison** —
four real production rows. Requiring four or more whitespace-separated tokens
separates the clause from the person and costs nothing: it still catches all 11
offenders and refuses none of the 4 people. Same discipline as #2993, where the
elegant "refuse any field market with more than two outcomes" rule was measured
against production and rejected for refusing 3,384 legitimate creations.

WHY A SEPARATE PREDICATE. `bracket_refusal_reason` is also the SCOPE of #2993's
cleanup — the repair reads it to decide which production rows it may touch.
Widening it in place would silently widen a repair that has already
pre-registered a 17-row disposition. Both are called at the mint.

WHY AT THE MINT, NOT IN extract_matchup. The parse also feeds linking, blend
gating and dedup. Refusing there would change what LINKS as well as what is
created. What parses today still parses; it just stops stamping an event row.

BLAST RADIUS, measured on production 2026-09-04: the SQL superset of all four
shapes is 278 events. The shipped predicate refuses **274** and admits exactly
**4** — every one of them a real person named Will. Zero collateral, which is
what `TestRealNamesSurvive` keeps true.
"""

from datetime import datetime, timezone

import pytest

from app.utils.prediction_market_matching import (
    bracket_refusal_reason,
    extract_matchup,
    is_question_fragment,
    name_embeds_a_matchup,
    question_refusal_reason,
)


# Real production market names (futures_markets, read 2026-09-04) grouped by the
# shape they mint.
REAL_EMBEDDED_MATCHUP_TITLES = [
    "Announcers at Duke vs Virginia",
    "Announcers at Arizona vs Houston",
    "Announcers at UConn vs St. John's",
]

REAL_QUESTION_HEAD_TITLES = [
    "What will the announcers say during New Zealand vs Egypt",
    "What will the announcers say during Uruguay vs Cape Verde",
    "What will the announcers say during USA vs Bosnia and Herzegovina",
    "Who will win Bucks vs. Heat: Game 2?",
    "Who will win Canadiens v. Golden Knights: Semifinals Game 3?",
    "Who will win Islanders v. Lightning: Semifinals Game 5?",
]

REAL_WILL_CLAUSE_TITLES = [
    "Will Greg Mueller Finish Top 3 at the 2026 WSOP Main Event",
    "Will Lucas Jumalon Finish Top 3 at the 2026 WSOP Main Event",
    "Will LAG Make the Grand Finals at FRAG Midwest: St. Louis 2026?",
    "Will more or less than 221 total points be scored in "
    "Suns v. Clippers: Finals Game 3?",
]

# The parsed names those titles actually produce, read straight off the bogus
# production rows (events table, 2026-09-04).
REAL_REFUSED_PAIRS = [
    ("Announcers", "Duke vs Virginia"),
    ("Announcers", "New York vs Los Angeles L Professional Basketball Game"),
    ("University", "Albany vs. Buffalo"),
    ("What will the announcers say during New Zealand", "Egypt"),
    ("What will the announcers say during Netherlands", "Japan FIFA World Cup Match"),
    ("Who will win Bucks", "Heat"),
    ("Who will score more points in Clippers", "Suns Game 5"),
    ("Will Greg Mueller Finish Top 3", "the 2026 WSOP Main Event"),
    ("Will LAG Make the Grand Finals", "FRAG Midwest"),
    ("Will more or less than 221 total points be scored in Suns", "Clippers"),
]

# The four production rows in the SQL superset that the predicate MUST admit.
# Every one is a real fighter whose first name is Will.
REAL_PEOPLE_NAMED_WILL = [
    ("Joel Kodua", "Will Harrison"),
    ("Kasim Aras", "Will Fleury"),
    ("Will Davis", "Wilson Lopshire"),
    ("Will Fleury", "Makhmud Muradov"),
]

# Real production team names that a careless version of either rule would eat.
REAL_TEAMS_THAT_MUST_SURVIVE = [
    "Whoville Wanderers",      # "Who" is not a whole token
    "Vsevolod Kovalenko",      # "vs" with no whitespace either side
    "Whatcom Community",       # "What" is not a whole token
    "Willem II",               # a Dutch club, two tokens
    "Williams Racing",
    "Paper Rex",
    "Inner Circle Esports",
    "Miami (OH)",
    "Los Heretics (OLD)",
]


class TestAnEmbeddedMatchupIsNotACompetitor:
    @pytest.mark.parametrize(
        "name",
        [
            "Duke vs Virginia",
            "Albany vs. Buffalo",
            "New York vs Los Angeles L Professional Basketball Game",
            "Alabama vs Michigan College Basketball Game",
        ],
    )
    def test_real_embedded_matchups_are_detected(self, name):
        assert name_embeds_a_matchup(name) is True

    @pytest.mark.parametrize("name", REAL_TEAMS_THAT_MUST_SURVIVE)
    def test_real_team_names_are_not(self, name):
        assert name_embeds_a_matchup(name) is False

    def test_vs_needs_whitespace_on_both_sides(self):
        """The rule keys on the SEPARATOR, not the letters.

        Without this, every club with "vs" inside a token — Vsevolod, Vsetin —
        stops being creatable.
        """
        assert name_embeds_a_matchup("Vsevolod Kovalenko") is False
        assert name_embeds_a_matchup("VSK Vsetin") is False
        assert name_embeds_a_matchup("Duke vs Virginia") is True

    def test_empty_and_none_are_not_matchups(self):
        assert name_embeds_a_matchup("") is False
        assert name_embeds_a_matchup(None) is False


class TestAQuestionHeadIsNotACompetitor:
    @pytest.mark.parametrize(
        "name",
        [
            "Who will win Bucks",
            "Who will score more points in Clippers",
            "What will the announcers say during New Zealand",
            "Will Greg Mueller Finish Top 3",
            "Will LAG Make the Grand Finals",
            "Will more or less than 221 total points be scored in Suns",
        ],
    )
    def test_real_question_heads_are_detected(self, name):
        assert is_question_fragment(name) is True

    @pytest.mark.parametrize("name", REAL_TEAMS_THAT_MUST_SURVIVE)
    def test_real_team_names_are_not(self, name):
        assert is_question_fragment(name) is False

    def test_the_opener_must_be_a_whole_token(self):
        assert is_question_fragment("Whoville Wanderers") is False
        assert is_question_fragment("Whatcom Community") is False
        assert is_question_fragment("Who will win Nets") is True

    def test_detection_is_case_insensitive_and_ignores_surrounding_space(self):
        assert is_question_fragment("  WHO WILL WIN NETS  ") is True
        assert is_question_fragment("what will the announcers say during Spain") is True

    def test_empty_and_none_are_not_questions(self):
        assert is_question_fragment("") is False
        assert is_question_fragment(None) is False


class TestTheWillTokenFloorIsLoadBearing:
    """The rule that a bare `^will\\s` would have got wrong.

    These four pairs are real production rows. If the floor is ever dropped,
    four UFC fighters stop being creatable and this class goes red — which is
    the whole reason it exists.
    """

    @pytest.mark.parametrize("home,away", REAL_PEOPLE_NAMED_WILL)
    def test_a_person_named_will_is_still_a_competitor(self, home, away):
        assert question_refusal_reason(home, away) is None

    @pytest.mark.parametrize(
        "name,expected",
        [
            ("Will Fleury", False),          # 2 tokens — a person
            ("Will Harrison", False),
            ("Will Davis Jr", False),        # 3 tokens — still a person
            ("Will Greg Mueller Finish", True),   # 4 tokens — a clause
            ("Will Greg Mueller Finish Top 3", True),
        ],
    )
    def test_four_tokens_is_the_boundary(self, name, expected):
        assert is_question_fragment(name) is expected


class TestRealNamesSurvive:
    """The control that makes every refusal above mean something."""

    @pytest.mark.parametrize(
        "home,away",
        [
            ("Paper Rex", "NRG"),
            ("Duke", "Virginia"),
            ("New Zealand", "Egypt"),
            ("Bucks", "Heat"),
            ("Miami (OH)", "St. Thomas (MN)"),
            ("Willem II", "Feyenoord"),
            ("Vsevolod Kovalenko", "Kasim Aras"),
        ],
    )
    def test_real_matchups_are_admitted(self, home, away):
        assert question_refusal_reason(home, away) is None

    @pytest.mark.parametrize("home,away", REAL_REFUSED_PAIRS)
    def test_the_bogus_production_pairs_are_refused(self, home, away):
        assert question_refusal_reason(home, away) is not None

    @pytest.mark.parametrize("home,away", REAL_REFUSED_PAIRS)
    def test_2993s_predicate_reaches_none_of_them(self, home, away):
        """Why this issue needed its own predicate at all.

        If #2993's guard ever grows to cover these, this test goes red and the
        duplicate refusal should be collapsed — deliberately, not by accident.
        """
        assert bracket_refusal_reason(home, away) is None

    def test_the_reason_names_the_slot_and_the_name(self):
        reason = question_refusal_reason("Bucks", "Who will win Heat")
        assert reason is not None
        assert "away" in reason
        assert "Who will win Heat" in reason


class _Matchup:
    def __init__(self, team_a, team_b):
        self.team_a = team_a
        self.team_b = team_b


class _Market:
    """The fields `_create_event_from_prediction_market` reads, and no others."""

    def __init__(self, name, source="kalshi", category="soccer"):
        self.source = source
        self.external_id = None
        self.name = name
        self.llm_sport_category = category
        self.commence_time = datetime(2026, 9, 4, tzinfo=timezone.utc)


class TestAutoCreateRefusesBeforeTheDatabase:
    """BEHAVIOURAL, not source-inspection.

    `session=None` is the assertion: the refusal must land BEFORE anything
    reaches the registry, so a None session can never be dereferenced. A
    refusal that happened after `find_or_create_event` would already have
    written the bogus event.
    """

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "title",
        REAL_EMBEDDED_MATCHUP_TITLES
        + REAL_QUESTION_HEAD_TITLES
        + REAL_WILL_CLAUSE_TITLES,
    )
    async def test_the_real_titles_mint_nothing(self, title):
        from app.tasks.prediction_market_matching import (
            _create_event_from_prediction_market,
        )

        matchup = extract_matchup(title)
        if matchup is None or not matchup.team_a or not matchup.team_b:
            pytest.skip("the parse no longer produces a matchup for this title")

        result = await _create_event_from_prediction_market(
            None, matchup, _Market(title),
            datetime(2026, 9, 4, tzinfo=timezone.utc),
        )
        assert result is None

    @pytest.mark.asyncio
    @pytest.mark.parametrize("home,away", REAL_REFUSED_PAIRS)
    async def test_the_parsed_pairs_mint_nothing(self, home, away):
        """Anchored on the parsed names, so a parser change cannot make this
        test vacuous the way a title-only test can."""
        from app.tasks.prediction_market_matching import (
            _create_event_from_prediction_market,
        )

        result = await _create_event_from_prediction_market(
            None, _Matchup(home, away), _Market(f"{home} at {away}"),
            datetime(2026, 9, 4, tzinfo=timezone.utc),
        )
        assert result is None

    @pytest.mark.asyncio
    @pytest.mark.parametrize("home,away", REAL_PEOPLE_NAMED_WILL)
    async def test_a_fighter_named_will_runs_past_the_refusal(self, home, away):
        """The control. Without it, a function that returned None
        unconditionally would pass every test above — and four real UFC bouts
        would silently stop being created."""
        from app.tasks.prediction_market_matching import (
            _create_event_from_prediction_market,
        )

        with pytest.raises(AttributeError):
            await _create_event_from_prediction_market(
                None,
                _Matchup(home, away),
                _Market(f"{home} vs. {away}", source="polymarket", category="mma"),
                datetime(2026, 9, 4, tzinfo=timezone.utc),
            )

    @pytest.mark.asyncio
    async def test_the_real_soccer_control_runs_past_the_refusal(self):
        from app.tasks.prediction_market_matching import (
            _create_event_from_prediction_market,
        )

        with pytest.raises(AttributeError):
            await _create_event_from_prediction_market(
                None,
                _Matchup("New Zealand", "Egypt"),
                _Market("New Zealand vs Egypt: Correct Score"),
                datetime(2026, 9, 4, tzinfo=timezone.utc),
            )
