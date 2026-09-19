"""#7188b — a city-plus-initial fragment resolves to the club it names, or to nothing.

Kalshi abbreviates a club to its city plus one letter: "New York M", "Los Angeles D",
"Chicago C". Two things conspired in ``team_identity`` to bind those fragments to the
wrong club, and both wrote the wrong answer into ``team_identity_mapping``, where
``resolve_team`` step 2 reads it back as an exact match forever after:

1. ``normalize_name`` strips a trailing single letter as a reserve-team suffix, so
   "Los Angeles C" arrived at the scorer as "los angeles" — the letter that decides
   Chargers-or-Rams was gone before any comparison happened.
2. ``_fuzzy_score`` scored both containment directions 60, so "los angeles" (the
   Angels' and the Dodgers' shared ``alternate_names`` entry) tied with
   "los angeles dodgers", and the ``score > best_score`` accumulator kept whichever
   row the query returned first.

The BEFORE column of this file's fixtures, measured on ``origin/master`` with the real
production rows below, is seven fragments out of eleven answering differently under
ascending and descending row order. Those are the cases each test pins.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock

from app.services.team_identity import (
    TeamIdentityService,
    _fuzzy_score,
    _resolve_scored,
    _sole_best_team,
    _sole_literal_match,
    _strict_name,
)


# Real production rows, teams JOIN sports, read 2026-09-19. The bare-city
# alternate_names on both Chicago and both Los Angeles clubs are the whole defect —
# they are why a same-city tie exists at all.
_PRODUCTION_TEAMS = {
    "americanfootball_nfl": [
        (561, "Chicago Bears", ["Bears"]),
        (556, "Los Angeles Chargers", ["Chargers"]),
        (544, "Los Angeles Rams", ["Rams"]),
        (547, "New York Giants", ["Giants"]),
        (550, "New York Jets", ["Jets"]),
    ],
    "baseball_mlb": [
        (10714, "Chicago Cubs", ["Cubs", "Chicago"]),
        (10734, "Chicago White Sox", ["Chicago", "White Sox"]),
        (10712, "Los Angeles Angels", ["Los Angeles", "Angels"]),
        (10707, "Los Angeles Dodgers", ["Dodgers", "Los Angeles"]),
        (10737, "New York Mets", ["New York", "Mets"]),
        (6610, "New York Yankees", ["New York", "Yankees"]),
    ],
}


class _FakeResult:
    def __init__(self, rows):
        self._rows = rows

    def scalars(self):
        return self

    def all(self):
        return self._rows

    def scalar_one_or_none(self):
        return self._rows[0] if self._rows else None


def _team_pool(sport_key, descending=False):
    teams = []
    for team_id, name, alternates in _PRODUCTION_TEAMS[sport_key]:
        team = MagicMock()
        team.id = team_id
        team.name = name
        team.alternate_names = list(alternates)
        teams.append(team)
    return teams[::-1] if descending else teams


def _mapping_pool(rows, descending=False):
    mappings = []
    for team_id, source_name in rows:
        mapping = MagicMock()
        mapping.team_id = team_id
        mapping.source_name = source_name
        mappings.append(mapping)
    return mappings[::-1] if descending else mappings


@pytest.fixture
def service():
    return TeamIdentityService()


# =============================================================================
# _fuzzy_score — the two containment directions are not the same claim
# =============================================================================

class TestStrictName:
    """The strict form keeps the trailing initial and nothing else changes."""

    def test_a_trailing_initial_survives(self):
        assert _strict_name("Los Angeles C") == "los angeles c"
        assert _strict_name("Chicago C") == "chicago c"

    def test_a_missing_space_after_a_period_is_still_repaired(self):
        """"St.Louis Cardinals" and "St. Louis Cardinals" are one club (#7021).
        ``normalize_name`` repairs this and ``normalize_team_name`` does not, so
        without the repair here the strict pass prefers the duplicate row — the one
        regression a full before/after sweep of all 471 known team names caught."""
        assert _strict_name("St.Louis Cardinals") == _strict_name("St. Louis Cardinals")
        assert _strict_name("St.Louis C") == "st louis c"

    def test_diacritics_and_case_still_fold(self):
        assert _strict_name("Montréal Canadiens") == "montreal canadiens"

    def test_empty_is_empty(self):
        assert _strict_name("") == ""


class TestContainmentDirectionScoresApart:
    def test_candidate_inside_target_outranks_target_inside_candidate(self):
        """"los angeles d" ⊂ "los angeles dodgers" explains every character of the
        fragment; "los angeles" ⊂ "los angeles d" abandons the one that matters."""
        explained = _fuzzy_score("los angeles d", "los angeles dodgers")
        residual = _fuzzy_score("los angeles d", "los angeles")
        assert explained > residual
        assert explained == 60
        assert residual == 50

    def test_target_inside_candidate_still_clears_the_floor(self):
        """The weaker direction is demoted, not disqualified: a lone bare-city
        mapping row must still resolve when nothing competes with it."""
        assert _fuzzy_score("los angeles d", "los angeles") >= 40

    def test_exact_still_outranks_both_directions(self):
        assert _fuzzy_score("chicago cubs", "chicago cubs") == 100


# =============================================================================
# _sole_best_team — a tie between DISTINCT teams is a refusal
# =============================================================================

class TestSoleBestTeam:
    def test_unique_best_wins(self):
        assert _sole_best_team([(1, 60), (2, 50), (3, 0)]) == (1, False)

    def test_tie_between_distinct_teams_refuses(self):
        assert _sole_best_team([(1, 60), (2, 60)]) == (None, True)

    def test_tie_refusal_does_not_depend_on_order(self):
        assert _sole_best_team([(1, 60), (2, 60)]) == _sole_best_team([(2, 60), (1, 60)])

    def test_a_weak_tie_refuses_too(self):
        assert _sole_best_team([(1, 50), (2, 50)]) == (None, True)
        assert _sole_best_team([(1, 40), (2, 40)]) == (None, True)

    def test_an_exact_tie_refuses_as_well(self):
        """Two rows carrying literally the same name are sometimes duplicates of one
        club and sometimes two real clubs sharing a city alias — the Cubs and the
        White Sox both answer to "Chicago". This function cannot tell them apart,
        so it declines to guess; folding the duplicates is #2693's job."""
        assert _sole_best_team([(1, 100), (2, 100)]) == (None, True)

    def test_an_exact_tie_does_not_fall_through_to_a_weaker_sole_match(self):
        assert _sole_best_team([(1, 100), (2, 100), (3, 60)]) == (None, True)

    def test_many_rows_for_one_team_is_not_a_tie(self):
        """A club has many mapping rows and many alternate names. Several entries at
        the top score naming the SAME team is agreement, not ambiguity."""
        assert _sole_best_team([(7, 60), (7, 60), (7, 60), (2, 50)]) == (7, False)

    def test_sub_floor_scores_are_not_ambiguity(self):
        """Nothing came close — a distinct state from "several did"."""
        assert _sole_best_team([(1, 20), (2, 10)]) == (None, False)

    def test_a_sub_floor_tie_does_not_suppress_a_real_match(self):
        """Entries below the floor are not candidates, so they cannot tie with
        each other and refuse a match that does clear it."""
        assert _sole_best_team([(1, 20), (2, 20), (3, 40)]) == (3, False)

    def test_the_floor_is_caller_supplied(self):
        assert _sole_best_team([(1, 50)]) == (1, False)
        assert _sole_best_team([(1, 50)], floor=60) == (None, False)

    def test_empty_is_none(self):
        assert _sole_best_team([]) == (None, False)


class TestSoleLiteralMatch:
    """Raw evidence beats normalized evidence, and only where it is unambiguous."""

    def test_the_one_row_carrying_the_name_verbatim_wins(self):
        """"St Louis Blues" and "St. Louis Blues" are two rows that `_strict_name`
        folds to one string, so the tie rule would refuse a club asked for by its
        own exact name. The raw match is what separates them."""
        candidates = [(1, ["St Louis Blues"]), (2, ["St. Louis Blues", "St. Louis"])]
        assert _sole_literal_match("St Louis Blues", candidates) == 1
        assert _sole_literal_match("St. Louis Blues", candidates) == 2

    def test_case_and_outer_space_do_not_matter(self):
        assert _sole_literal_match("  chicago CUBS ", [(1, ["Chicago Cubs"])]) == 1

    def test_two_rows_carrying_it_verbatim_is_not_a_literal_match(self):
        """Both Chicago clubs really do answer to "Chicago". Raw evidence cannot
        break that either, so it declines and leaves it to the tie rule."""
        assert _sole_literal_match("Chicago", [(1, ["Chicago"]), (2, ["Chicago"])]) is None

    def test_a_fragment_nobody_spells_out_is_not_a_literal_match(self):
        assert _sole_literal_match("Chicago C", [(1, ["Chicago Cubs"])]) is None

    def test_empty_matches_nothing(self):
        assert _sole_literal_match("   ", [(1, [""])]) is None


class TestResolveScored:
    """The loose pass answers "nothing matched", never "the strict pass was unsure"."""

    def test_a_sole_strict_winner_is_taken(self):
        assert _resolve_scored([(1, 60), (2, 50)], [(2, 100)]) == 1

    def test_strict_ambiguity_is_terminal(self):
        """The loose form is the one that threw the distinguishing letter away, so
        it must not break a tie the strict form could not."""
        assert _resolve_scored([(1, 100), (2, 100)], [(1, 100)]) is None

    def test_a_strict_match_below_the_floor_also_blocks_the_loose_pass(self):
        """"Los Angeles C" against a lone cached "Los Angeles" scores 50 strictly and
        100 loosely. The 50 says the fragment carries more than the row does — it is
        not licence to answer with the row (CERT-3130)."""
        assert _resolve_scored([(1, 50)], [(1, 100)], floor=60) is None

    def test_the_loose_pass_runs_when_the_strict_pass_scored_nothing(self):
        assert _resolve_scored([(1, 0), (2, 0)], [(2, 60)]) == 2

    def test_a_loose_tie_refuses_too(self):
        assert _resolve_scored([(1, 0), (2, 0)], [(1, 60), (2, 60)]) is None


# =============================================================================
# _fuzzy_match_teams — the fragments that flipped with row order
# =============================================================================

@pytest.mark.parametrize(
    "sport_key,fragment,expected",
    [
        # Bound to the wrong club in production before this fix.
        ("baseball_mlb", "New York M", "New York Mets"),
        ("baseball_mlb", "Los Angeles D", "Los Angeles Dodgers"),
        ("baseball_mlb", "Chicago C", "Chicago Cubs"),
        ("baseball_mlb", "Chicago W", "Chicago White Sox"),
        ("americanfootball_nfl", "Los Angeles C", "Los Angeles Chargers"),
        # Cities with no same-city collision — must not move.
        ("americanfootball_nfl", "New York G", "New York Giants"),
        ("americanfootball_nfl", "New York J", "New York Jets"),
        # Unambiguous full names and mascots — must not move.
        ("baseball_mlb", "Yankees", "New York Yankees"),
        ("americanfootball_nfl", "Rams", "Los Angeles Rams"),
        ("baseball_mlb", "Chicago Cubs", "Chicago Cubs"),
    ],
)
@pytest.mark.asyncio
async def test_fragment_binds_to_the_club_it_names(service, sport_key, fragment, expected):
    for descending in (False, True):
        session = AsyncMock()
        session.execute.return_value = _FakeResult(_team_pool(sport_key, descending))
        team = await service._fuzzy_match_teams(session, fragment, sport_key)
        assert team is not None, f"{fragment!r} resolved to nothing (descending={descending})"
        assert team.name == expected, (
            f"{fragment!r} -> {team.name!r}, expected {expected!r} (descending={descending})"
        )


@pytest.mark.asyncio
async def test_a_reserve_suffix_still_folds_onto_the_senior_side(service):
    """The loose pass is the old behaviour and it stays behind the strict one.

    ``normalize_name`` strips "II" for the soccer reserve sides it was written
    for. The strict pass keeps the suffix and so scores "bayern ii" against
    "bayern munich" at zero; without the fallback this resolves to nothing.
    """
    bayern = MagicMock()
    bayern.id = 900
    bayern.name = "Bayern Munich"
    bayern.alternate_names = []

    session = AsyncMock()
    session.execute.return_value = _FakeResult([bayern])

    assert await service._fuzzy_match_teams(session, "Bayern II", "soccer_germany_bundesliga") is bayern


# The St. Louis Blues exist twice in production, spelled two ways. `_strict_name`
# folds the spellings together on purpose, which makes them an exact tie — so
# without the literal pass the club cannot be found by its own name.
_ST_LOUIS_TWINS = [
    (700, "St Louis Blues", ["Blues", "St Louis"]),
    (701, "St. Louis Blues", ["Blues", "St. Louis"]),
]


def _twin_pool(descending=False):
    teams = []
    for team_id, name, alternates in _ST_LOUIS_TWINS:
        team = MagicMock()
        team.id = team_id
        team.name = name
        team.alternate_names = list(alternates)
        teams.append(team)
    return teams[::-1] if descending else teams


@pytest.mark.parametrize(
    "fragment,expected_id",
    [
        ("St Louis Blues", 700),
        ("St. Louis Blues", 701),
        ("  st. louis BLUES ", 701),   # case and outer space do not matter
        ("St Louis", 700),             # a literal alias decides too
        ("St. Louis", 701),
    ],
)
@pytest.mark.asyncio
async def test_a_club_asked_for_by_its_own_exact_name_is_found(
    service, fragment, expected_id
):
    """Through ``_fuzzy_match_teams``, not by calling the helper. The two rows fold
    to one string strictly, so the tie rule alone refuses — this is the pass that
    separates them, and the sweep found three real links riding on it."""
    for descending in (False, True):
        session = AsyncMock()
        session.execute.return_value = _FakeResult(_twin_pool(descending))
        team = await service._fuzzy_match_teams(session, fragment, "icehockey_nhl")
        assert team is not None, f"{fragment!r} resolved to nothing"
        assert team.id == expected_id


@pytest.mark.asyncio
async def test_an_alternate_name_can_be_what_makes_a_pool_ambiguous(service):
    """The strict pass scores alternate names, not just the primary one, and that is
    load-bearing: the junk "Detroit" row carries the alias "Pistons", which is the
    only reason "Pistons" is ambiguous at all. Scoring primary names alone would
    hand it confidently to the real club — and would do the same for 57 other
    production lookups that are genuinely two-rowed."""
    pistons = MagicMock()
    pistons.id = 41
    pistons.name = "Detroit Pistons"
    pistons.alternate_names = ["Detroit", "Pistons"]
    twin = MagicMock()
    twin.id = 12719
    twin.name = "Detroit"
    twin.alternate_names = ["Pistons"]

    for pool in ([pistons, twin], [twin, pistons]):
        session = AsyncMock()
        session.execute.return_value = _FakeResult(pool)
        assert await service._fuzzy_match_teams(
            session, "Pistons", "basketball_nba"
        ) is None


@pytest.mark.asyncio
async def test_a_fragment_of_the_twins_names_neither_and_refuses(service):
    """"St Louis B" is spelled out by neither row, so nothing rescues the tie. This
    is a real link lost to #7021's duplicate rows, and it is the honest answer until
    they are folded — better than the coin flip it replaces."""
    for descending in (False, True):
        session = AsyncMock()
        session.execute.return_value = _FakeResult(_twin_pool(descending))
        assert await service._fuzzy_match_teams(
            session, "St Louis B", "icehockey_nhl"
        ) is None


@pytest.mark.parametrize("fragment", ["New York", "Los Angeles"])
@pytest.mark.asyncio
async def test_a_bare_city_naming_two_clubs_resolves_to_nothing(service, fragment):
    """A bare city does not name an NFL club. Both clubs score 60 by containment
    and before this fix the answer was whichever the heap offered first — then
    cached, so every later lookup of that city got the same wrong club."""
    for descending in (False, True):
        session = AsyncMock()
        session.execute.return_value = _FakeResult(
            _team_pool("americanfootball_nfl", descending)
        )
        assert await service._fuzzy_match_teams(
            session, fragment, "americanfootball_nfl"
        ) is None


@pytest.mark.parametrize("fragment", ["Chicago", "New York", "Los Angeles"])
@pytest.mark.asyncio
async def test_a_bare_city_that_is_a_literal_alias_refuses_too(service, fragment):
    """Both MLB clubs in each of these cities carry the bare city in
    ``alternate_names``, so the tie is at an exact match. It refuses all the same:
    an exact tie is sometimes two rows for one club and sometimes two real clubs
    sharing a city, and nothing here can tell those apart (CERT-3130)."""
    for descending in (False, True):
        session = AsyncMock()
        session.execute.return_value = _FakeResult(_team_pool("baseball_mlb", descending))
        assert await service._fuzzy_match_teams(session, fragment, "baseball_mlb") is None


# =============================================================================
# _fuzzy_match_mappings — same rule on the cache that feeds step 2
# =============================================================================

async def _resolve_through_mappings(service, rows, fragment, sport_key, descending=False):
    """Drive ``_fuzzy_match_mappings`` and report the team id it looked up.

    The second query is ``select(Team).where(Team.id == <winner>)``, so the id it
    binds IS the answer. Handing back a fixed team object instead would pass for
    every possible winner — the assertion has to read the id off the statement.
    """
    calls = []

    async def execute(statement):
        calls.append(statement)
        if len(calls) == 1:
            return _FakeResult(_mapping_pool(rows, descending))
        team = MagicMock()
        team.id = list(statement.compile().params.values())[0]
        return _FakeResult([team])

    session = AsyncMock()
    session.execute.side_effect = execute
    team = await service._fuzzy_match_mappings(session, fragment, sport_key)
    return None if team is None else team.id


class TestFuzzyMatchMappings:
    @pytest.mark.asyncio
    async def test_fragment_prefers_the_mapping_that_spells_it_out(self, service):
        """A bare-city row for the Angels must not outscore the Dodgers' full name."""
        rows = [(10707, "Los Angeles Dodgers"), (10712, "Los Angeles")]
        for descending in (False, True):
            assert await _resolve_through_mappings(
                service, rows, "Los Angeles D", "baseball_mlb", descending
            ) == 10707

    @pytest.mark.parametrize(
        "fragment,sport_key,city_owner",
        [
            ("Los Angeles D", "baseball_mlb", 10712),       # Angels hold the bare city
            ("Los Angeles C", "americanfootball_nfl", 544),  # Rams hold it
            ("Chicago C", "baseball_mlb", 10734),            # White Sox hold it
        ],
    )
    @pytest.mark.asyncio
    async def test_a_lone_bare_city_row_does_not_preempt_the_teams_table(
        self, service, fragment, sport_key, city_owner
    ):
        """A cached row named "Los Angeles" is a fact about the city, not about
        "Los Angeles D". It scores 50 strictly and 100 loosely, and either way it
        must not answer here — step 4 is where the canonical teams table says
        Dodgers. Letting it answer is how the cache preempts the truth (CERT-3130)."""
        for descending in (False, True):
            assert await _resolve_through_mappings(
                service, [(city_owner, fragment.rsplit(" ", 1)[0])],
                fragment, sport_key, descending,
            ) is None

    @pytest.mark.asyncio
    async def test_a_stripped_initial_is_recovered_by_the_strict_pass(self, service):
        """"Los Angeles C" loses its C to ``normalize_name``'s reserve-suffix rule.
        What is left, "los angeles", matches the Rams' bare-city row exactly — a
        perfect score for the wrong club. Only the strict pass, which keeps the C,
        can answer this one."""
        rows = [(556, "Los Angeles Chargers"), (544, "Los Angeles Rams"), (544, "Los Angeles")]
        for descending in (False, True):
            assert await _resolve_through_mappings(
                service, rows, "Los Angeles C", "americanfootball_nfl", descending
            ) == 556

    @pytest.mark.asyncio
    async def test_two_clubs_partially_matching_resolve_to_nothing(self, service):
        """"New York" is inside both mapping rows at 60 and names neither club."""
        rows = [(547, "New York Giants"), (550, "New York Jets")]
        for descending in (False, True):
            assert await _resolve_through_mappings(
                service, rows, "New York", "americanfootball_nfl", descending
            ) is None

    @pytest.mark.asyncio
    async def test_both_sides_of_the_strict_pass_use_the_strict_form(self, service):
        """A mapping row can itself be a city-plus-initial name — the cache is full
        of them. Normalizing only the incoming fragment strictly would strip the row's
        own initial and hand the exact match to whatever shares the bare city."""
        rows = [(556, "Los Angeles C"), (544, "Los Angeles")]
        for descending in (False, True):
            assert await _resolve_through_mappings(
                service, rows, "Los Angeles C", "americanfootball_nfl", descending
            ) == 556

    @pytest.mark.asyncio
    async def test_the_loose_pass_still_backs_the_mapping_cache(self, service):
        """As in ``_fuzzy_match_teams``: the strict form scores "bayern ii" against
        "bayern munich" at zero, and only the loose pass folds the reserve side on."""
        rows = [(900, "Bayern Munich")]
        assert await _resolve_through_mappings(
            service, rows, "Bayern II", "soccer_germany_bundesliga"
        ) == 900

    @pytest.mark.asyncio
    async def test_a_cached_row_carrying_the_name_verbatim_breaks_a_fold(self, service):
        """Same rule on the cache. "St Louis Blues" and "St. Louis Blues" are one
        string strictly, so the tie rule refuses — the row spelling it exactly is
        what answers."""
        rows = [(700, "St Louis Blues"), (701, "St. Louis Blues")]
        for descending in (False, True):
            assert await _resolve_through_mappings(
                service, rows, "St Louis Blues", "icehockey_nhl", descending
            ) == 700
            assert await _resolve_through_mappings(
                service, rows, "St. Louis Blues", "icehockey_nhl", descending
            ) == 701

    @pytest.mark.asyncio
    async def test_one_club_on_many_rows_still_resolves(self, service):
        rows = [(10714, "Chicago Cubs"), (10714, "Chicago Cubs"), (10714, "Cubs")]
        assert await _resolve_through_mappings(
            service, rows, "Chicago Cubs", "baseball_mlb"
        ) == 10714


# =============================================================================
# The reason a tie must refuse rather than guess: resolve_team caches the answer
# =============================================================================

class TestRefusalIsNotRegistered:
    @pytest.mark.asyncio
    async def test_an_ambiguous_fragment_writes_no_mapping_row(self, service):
        """``resolve_team`` auto-registers whatever the fuzzy steps return, so a
        guess becomes a durable exact-match fact. A refusal must reach step 5."""
        registered = []

        async def record(*args, **kwargs):
            registered.append(kwargs)

        session = AsyncMock()
        session.execute.side_effect = [
            _FakeResult([]),                                        # step 2: no exact row
            _FakeResult([]),                                        # step 3: no mapping rows
            _FakeResult(_team_pool("americanfootball_nfl")),        # step 4: ambiguous pool
        ]
        service.register_team_identity = record

        result = await service.resolve_team(
            session, "kalshi", "americanfootball_nfl", source_name="New York"
        )

        assert result is None
        assert registered == []

    @pytest.mark.parametrize(
        "fragment,sport_key,mapping_rows,expected_id,expected_name",
        [
            # The cache holds a bare-city row for the rival; the teams table wins.
            (
                "Los Angeles C", "americanfootball_nfl",
                [(544, "Los Angeles")],
                556, "Los Angeles Chargers",
            ),
            (
                "Los Angeles D", "baseball_mlb",
                [(10712, "Los Angeles")],
                10707, "Los Angeles Dodgers",
            ),
            (
                "Chicago C", "baseball_mlb",
                [(10734, "Chicago")],
                10714, "Chicago Cubs",
            ),
        ],
    )
    @pytest.mark.asyncio
    async def test_the_whole_cascade_registers_the_club_the_fragment_names(
        self, service, fragment, sport_key, mapping_rows, expected_id, expected_name
    ):
        """End to end through ``resolve_team``, both row orders: the club it answers
        with AND the club it caches must be the one the fragment names. A unit test
        of either fuzzy step alone cannot see the registration, and registration is
        what makes a wrong answer permanent."""
        for descending in (False, True):
            registered = []

            async def record(session, team_id, *args, **kwargs):
                registered.append(team_id)

            calls = []

            async def execute(statement):
                calls.append(statement)
                if len(calls) == 1:                       # step 2: no exact row
                    return _FakeResult([])
                if len(calls) == 2:                       # step 3: the poisoned cache
                    return _FakeResult(_mapping_pool(mapping_rows, descending))
                return _FakeResult(_team_pool(sport_key, descending))   # step 4

            session = AsyncMock()
            session.execute.side_effect = execute
            service.register_team_identity = record

            team = await service.resolve_team(
                session, "kalshi", sport_key, source_name=fragment
            )

            assert team is not None, f"{fragment!r} resolved to nothing"
            assert team.name == expected_name
            assert registered == [expected_id], (
                f"{fragment!r} cached {registered}, expected [{expected_id}]"
            )

    @pytest.mark.asyncio
    async def test_an_exact_cached_row_still_wins_and_that_is_the_data_repair(self, service):
        """The scope line. A mapping row literally named "Los Angeles C" is an exact
        hit and the cache answers with it — that is what a cache is for, and nothing
        in this module second-guesses it. The 13 such rows already written by the
        two #7188 causes are cleaned by that issue's data repair, not here, which is
        why the repair has to run before the poisoned outcomes are re-resolved."""
        calls = []

        async def execute(statement):
            calls.append(statement)
            if len(calls) == 1:
                return _FakeResult([])
            if len(calls) == 2:
                return _FakeResult(_mapping_pool([(544, "Los Angeles C")]))
            rams = MagicMock()
            rams.id = 544
            rams.name = "Los Angeles Rams"
            return _FakeResult([rams])

        session = AsyncMock()
        session.execute.side_effect = execute
        service.register_team_identity = AsyncMock()

        team = await service.resolve_team(
            session, "kalshi", "americanfootball_nfl", source_name="Los Angeles C"
        )
        assert team.name == "Los Angeles Rams"
