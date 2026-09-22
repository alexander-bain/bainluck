"""Guard for #2623 — search must not render a scoreless twin beside the real row.

RED-FIRST. Every test imports `app.utils.search_fixture_dedup` INSIDE the test
body, so on clean master (where the module does not exist) these fail with
ImportError rather than collection-erroring the whole file and taking the
control cases down with them.

The population is the real one, transcribed from production on 2026-09-01:
`tennis_wta` (4,790 events, 0 with a score) shadowing
`tennis_wta_us_open` / `_cincinnati_open` / `_canadian_open`.
"""

from datetime import datetime, timezone

import pytest


class _Sport:
    def __init__(self, key):
        self.key = key


class _FakeEvent:
    """Mirrors the attributes the helper reads off an ORM `Event`."""

    def __init__(
        self,
        id,
        home_team_name,
        away_team_name,
        commence_time,
        sport_key,
        status="scheduled",
        home_score=None,
        away_score=None,
    ):
        self.id = id
        self.home_team_name = home_team_name
        self.away_team_name = away_team_name
        self.commence_time = commence_time
        self.status = status
        self.home_score = home_score
        self.away_score = away_score
        self.sport = _Sport(sport_key)


def _at(iso):
    return datetime.fromisoformat(iso).replace(tzinfo=timezone.utc)


# --- The defect, verbatim from the shopper's table -------------------------

REAL_ROWS = [
    _FakeEvent(15206893, "Aryna Sabalenka", "Sara Bejlek", _at("2026-08-20T00:30:00"),
               "tennis_wta_cincinnati_open", "completed", 0, 2),
    _FakeEvent(15200246, "Aryna Sabalenka", "Xinyu Wang", _at("2026-08-18T12:00:00"),
               "tennis_wta_cincinnati_open", "completed", 2, 0),
    _FakeEvent(15199002, "Aryna Sabalenka", "Talia Gibson", _at("2026-08-16T15:00:00"),
               "tennis_wta_cincinnati_open", "completed", 2, 0),
    _FakeEvent(15191375, "Aryna Sabalenka", "Ekaterina Alexandrova", _at("2026-08-09T19:00:00"),
               "tennis_wta_canadian_open", "completed", 1, 2),
    _FakeEvent(15189260, "Aryna Sabalenka", "Shuai Zhang", _at("2026-08-07T19:00:00"),
               "tennis_wta_canadian_open", "completed", 2, 0),
    _FakeEvent(15187257, "Aryna Sabalenka", "Moyuka Uchijima", _at("2026-08-05T19:00:00"),
               "tennis_wta_canadian_open", "completed", 2, 0),
    _FakeEvent(15299512, "Aryna Sabalenka", "Polina Iatcenko", _at("2026-09-02T23:00:00"),
               "tennis_wta_us_open", "scheduled"),
]

GHOST_ROWS = [
    _FakeEvent(15300722, "Sabalenka", "Bejlek", _at("2026-08-20T04:14:47"),
               "tennis_wta", "closed"),
    _FakeEvent(15205016, "Sabalenka", "Wang", _at("2026-08-19T00:10:09"),
               "tennis_wta", "closed"),
    _FakeEvent(15209624, "Sabalenka", "Gibson", _at("2026-08-16T21:10:07"),
               "tennis_wta", "closed"),
    _FakeEvent(15197940, "Sabalenka", "Alexandrova", _at("2026-08-09T01:44:50"),
               "tennis_wta", "closed"),
    _FakeEvent(15197994, "Sabalenka", "Zhang", _at("2026-08-07T00:50:06"),
               "tennis_wta", "closed"),
    _FakeEvent(15197957, "Sabalenka", "Uchijima", _at("2026-08-05T00:40:33"),
               "tennis_wta", "closed"),
    _FakeEvent(15299435, "Sabalenka", "Iatcenko", _at("2026-09-02T00:00:00"),
               "tennis_wta", "scheduled"),
]


def test_every_sabalenka_ghost_twin_is_collapsed():
    """The whole shopper finding: 14 rows for 7 matches must render as 7."""
    from app.utils.search_fixture_dedup import collapse_duplicate_fixtures

    page = REAL_ROWS + GHOST_ROWS
    kept, dropped_count = collapse_duplicate_fixtures(page)

    kept_ids = [e.id for e in kept]
    ghost_ids = {e.id for e in GHOST_ROWS}
    still_showing = sorted(ghost_ids.intersection(kept_ids))
    assert not still_showing, (
        "search still renders scoreless surname-only twins: "
        f"{still_showing} (kept {len(kept)} of {len(page)} rows)"
    )
    assert kept_ids == [e.id for e in REAL_ROWS], (
        "the rich rows must survive in the caller's original order"
    )
    assert dropped_count == len(GHOST_ROWS)


def test_the_upcoming_match_is_not_offered_at_two_different_times():
    """The worst case: one first-round match, two days, two start times."""
    from app.utils.search_fixture_dedup import collapse_duplicate_fixtures

    real = _FakeEvent(15299512, "Aryna Sabalenka", "Polina Iatcenko",
                      _at("2026-09-02T23:00:00"), "tennis_wta_us_open", "scheduled")
    ghost = _FakeEvent(15299435, "Sabalenka", "Iatcenko",
                       _at("2026-09-02T00:00:00"), "tennis_wta", "scheduled")

    kept, _ = collapse_duplicate_fixtures([real, ghost])
    assert [e.id for e in kept] == [15299512]


def test_a_swapped_orientation_twin_still_collapses():
    """The two providers disagree about who is 'home' on a neutral court."""
    from app.utils.search_fixture_dedup import collapse_duplicate_fixtures

    real = _FakeEvent(1, "Aryna Sabalenka", "Sara Bejlek", _at("2026-08-20T00:30:00"),
                      "tennis_wta_cincinnati_open", "completed", 0, 2)
    ghost = _FakeEvent(2, "Bejlek", "Sabalenka", _at("2026-08-20T04:14:00"),
                       "tennis_wta", "closed")

    kept, _ = collapse_duplicate_fixtures([real, ghost])
    assert [e.id for e in kept] == [1]


# --- Controls: these must be green in BOTH arms once the module exists -----
#
# Each one is a shape the naive rule ("same teams, same day, keep one") would
# eat. They are the reason the dominance test is conjunctive.


def test_a_doubleheader_keeps_both_games():
    """Two genuine completed games, same clubs, hours apart. Neither dominates."""
    from app.utils.search_fixture_dedup import collapse_duplicate_fixtures

    game_one = _FakeEvent(11, "New York Yankees", "Boston Red Sox",
                          _at("2026-07-04T17:05:00"), "baseball_mlb", "completed", 3, 1)
    game_two = _FakeEvent(12, "New York Yankees", "Boston Red Sox",
                          _at("2026-07-04T23:05:00"), "baseball_mlb", "completed", 2, 6)

    kept, dropped = collapse_duplicate_fixtures([game_one, game_two])
    assert [e.id for e in kept] == [11, 12]
    assert dropped == 0


def test_a_three_game_mlb_series_keeps_all_three_games():
    """The false positive the first cut of this helper actually produced.

    Angels–Yankees, transcribed from `/api/events/search?q=Yankees` on
    2026-09-01: three real games on consecutive days, identical team names, the
    played ones carrying scores and the un-played one not. A rule that lets
    "has the result the other lacks" collapse a fixture would delete tomorrow's
    game from search. It is why the pass is scoped to individual sports.
    """
    from app.utils.search_fixture_dedup import collapse_duplicate_fixtures

    yesterday = _FakeEvent(15291547, "Los Angeles Angels", "New York Yankees",
                           _at("2026-09-01T01:38:00"), "baseball_mlb", "closed", 4, 1)
    tonight = _FakeEvent(15292632, "Los Angeles Angels", "New York Yankees",
                         _at("2026-09-02T01:38:00"), "baseball_mlb", "live", 3, 4)
    tomorrow = _FakeEvent(15293347, "Los Angeles Angels", "New York Yankees",
                          _at("2026-09-03T01:38:00"), "baseball_mlb", "scheduled")

    kept, dropped = collapse_duplicate_fixtures([yesterday, tonight, tomorrow])
    assert [e.id for e in kept] == [15291547, 15292632, 15293347], (
        "a search for Yankees must still offer tomorrow's game"
    )
    assert dropped == 0


def test_a_team_sport_abbreviation_twin_is_left_alone():
    """Name dominance is not safe in league sport either — same reason.

    "Yankees" on Aug 15 and "New York Yankees" on Aug 16 are two games of a
    series, not one game named two ways. Only the event-graph drain can tell
    those apart, so search must not guess.
    """
    from app.utils.search_fixture_dedup import collapse_duplicate_fixtures

    short = _FakeEvent(91, "Yankees", "Blue Jays", _at("2026-08-15T19:07:00"),
                       "baseball_mlb", "scheduled")
    full = _FakeEvent(92, "New York Yankees", "Toronto Blue Jays",
                      _at("2026-08-16T17:37:00"), "baseball_mlb", "completed", 3, 4)

    kept, dropped = collapse_duplicate_fixtures([short, full])
    assert [e.id for e in kept] == [91, 92]
    assert dropped == 0


def test_a_naive_timestamp_never_raises_inside_the_request():
    """An accelerator must not be the thing that 500s search."""
    from app.utils.search_fixture_dedup import collapse_duplicate_fixtures

    aware = _FakeEvent(101, "Aryna Sabalenka", "Sara Bejlek",
                       _at("2026-08-20T00:30:00"), "tennis_wta_cincinnati_open",
                       "completed", 0, 2)
    naive = _FakeEvent(102, "Sabalenka", "Bejlek",
                       datetime(2026, 8, 20, 4, 14), "tennis_wta", "closed")

    kept, dropped = collapse_duplicate_fixtures([aware, naive])
    assert [e.id for e in kept] == [101, 102]
    assert dropped == 0


def test_the_individual_sport_list_matches_the_routes_module():
    """A copied constant that can drift is a defect with a delay fuse."""
    from app.routes.events import _INDIVIDUAL_SPORT_PREFIXES
    from app.utils.search_fixture_dedup import INDIVIDUAL_SPORT_PREFIXES

    assert set(INDIVIDUAL_SPORT_PREFIXES) == set(_INDIVIDUAL_SPORT_PREFIXES), (
        "search_fixture_dedup and routes/events disagree about which sports are "
        "1-on-1 — the dedup pass would run on a team sport, or skip a 1v1 one"
    )


def test_a_rematch_outside_the_window_keeps_both():
    """Same two players, same naming, eight days apart — a different match."""
    from app.utils.search_fixture_dedup import collapse_duplicate_fixtures

    first = _FakeEvent(21, "Aryna Sabalenka", "Sara Bejlek", _at("2026-08-20T00:30:00"),
                       "tennis_wta_cincinnati_open", "completed", 0, 2)
    later = _FakeEvent(22, "Sabalenka", "Bejlek", _at("2026-09-03T00:30:00"),
                       "tennis_wta", "scheduled")

    kept, dropped = collapse_duplicate_fixtures([first, later])
    assert [e.id for e in kept] == [21, 22]
    assert dropped == 0


def test_different_sports_never_collapse():
    """Surname collision across sport families must not hide either row."""
    from app.utils.search_fixture_dedup import collapse_duplicate_fixtures

    tennis = _FakeEvent(31, "Alex Smith", "Jordan Lee", _at("2026-08-20T00:30:00"),
                        "tennis_atp_us_open", "completed", 2, 0)
    basketball = _FakeEvent(32, "Smith", "Lee", _at("2026-08-20T02:30:00"),
                            "basketball_nba", "closed")

    kept, dropped = collapse_duplicate_fixtures([tennis, basketball])
    assert [e.id for e in kept] == [31, 32]
    assert dropped == 0


def test_a_surname_prefix_is_not_a_surname_match():
    """'Wang' must not absorb 'Huang' — the suffix test is whole-word."""
    from app.utils.search_fixture_dedup import collapse_duplicate_fixtures

    real = _FakeEvent(41, "Aryna Sabalenka", "Xinyu Wang", _at("2026-08-18T12:00:00"),
                      "tennis_wta_cincinnati_open", "completed", 2, 0)
    other = _FakeEvent(42, "Sabalenka", "Huang", _at("2026-08-18T18:00:00"),
                       "tennis_wta", "closed")

    kept, dropped = collapse_duplicate_fixtures([real, other])
    assert [e.id for e in kept] == [41, 42]
    assert dropped == 0


def test_a_scored_row_is_never_collapsed_into_a_scoreless_one():
    """Direction matters: the row carrying the result always survives."""
    from app.utils.search_fixture_dedup import collapse_duplicate_fixtures

    scoreless_but_fuller = _FakeEvent(
        51, "Aryna Sabalenka", "Sara Bejlek", _at("2026-08-20T00:30:00"),
        "tennis_wta", "closed")
    scored_but_shorter = _FakeEvent(
        52, "Sabalenka", "Bejlek", _at("2026-08-20T02:30:00"),
        "tennis_wta_cincinnati_open", "completed", 0, 2)

    kept, _ = collapse_duplicate_fixtures([scoreless_but_fuller, scored_but_shorter])
    assert 52 in [e.id for e in kept], "the row with the result must survive"


def test_a_lone_row_and_an_empty_page_are_untouched():
    from app.utils.search_fixture_dedup import collapse_duplicate_fixtures

    lone = _FakeEvent(61, "Aryna Sabalenka", "Sara Bejlek", _at("2026-08-20T00:30:00"),
                      "tennis_wta_cincinnati_open", "completed", 0, 2)
    assert collapse_duplicate_fixtures([lone]) == ([lone], 0)
    assert collapse_duplicate_fixtures([]) == ([], 0)


def test_rows_missing_a_time_or_a_name_are_never_dropped():
    """Absent data is never grounds for hiding a result from the user."""
    from app.utils.search_fixture_dedup import collapse_duplicate_fixtures

    real = _FakeEvent(71, "Aryna Sabalenka", "Sara Bejlek", _at("2026-08-20T00:30:00"),
                      "tennis_wta_cincinnati_open", "completed", 0, 2)
    no_time = _FakeEvent(72, "Sabalenka", "Bejlek", None, "tennis_wta", "closed")
    no_name = _FakeEvent(73, "", "Bejlek", _at("2026-08-20T01:00:00"),
                         "tennis_wta", "closed")

    kept, dropped = collapse_duplicate_fixtures([real, no_time, no_name])
    assert [e.id for e in kept] == [71, 72, 73]
    assert dropped == 0


def test_the_helper_does_not_lazy_load_the_sport_relationship():
    """A dedup pass that emits IO per row is a latency incident (gotcha: ORM lazy-load).

    An unloaded relationship must read as "no sport key", not as a database
    round trip — so a row whose `sport` was never eagerly loaded is simply
    never grouped, and therefore never dropped.
    """
    from app.utils.search_fixture_dedup import collapse_duplicate_fixtures

    class _ExplodingSport:
        def __get__(self, obj, objtype=None):  # pragma: no cover - must not run
            raise AssertionError("lazy-loaded Event.sport inside the dedup pass")

    class _Unloaded:
        sport = _ExplodingSport()

        def __init__(self, id):
            self.id = id
            self.home_team_name = "Sabalenka"
            self.away_team_name = "Bejlek"
            self.commence_time = _at("2026-08-20T00:30:00")
            self.status = "closed"
            self.home_score = None
            self.away_score = None

    kept, dropped = collapse_duplicate_fixtures([_Unloaded(81), _Unloaded(82)])
    assert [e.id for e in kept] == [81, 82]
    assert dropped == 0


@pytest.mark.parametrize(
    "sport_key,expected_family",
    [
        ("tennis_wta", "tennis"),
        ("tennis_wta_us_open", "tennis"),
        ("baseball_mlb", "baseball"),
        ("", ""),
        (None, ""),
    ],
)
def test_sport_family_groups_the_generic_bucket_with_its_tournaments(
    sport_key, expected_family
):
    from app.utils.search_fixture_dedup import _sport_family

    assert _sport_family(sport_key) == expected_family


# --- The wiring: a helper nothing calls is not a ship ----------------------


def _search_route_functions():
    """AST of `routes/events.py`, keyed by top-level function name.

    An AST walk rather than a substring scan, because a substring scan is
    satisfied by ANY call site in an 8,000-line file — including the one in the
    other endpoint — and this guard's whole job is to say WHICH function calls
    the helper. It raises rather than skipping if the file will not parse or a
    named function has gone missing.
    """
    import ast
    import pathlib

    source = pathlib.Path("app/routes/events.py")
    if not source.exists():  # pytest may run from the repo root
        source = pathlib.Path("backend/app/routes/events.py")
    tree = ast.parse(source.read_text())
    return {
        node.name: node
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }


def _calls_named(node, name):
    import ast

    return any(
        isinstance(child, ast.Call)
        and isinstance(child.func, ast.Name)
        and child.func.id == name
        for child in ast.walk(node)
    )


def _reads_name(node, name):
    import ast

    return any(
        isinstance(child, ast.Name) and child.id == name for child in ast.walk(node)
    )


@pytest.mark.parametrize("endpoint", ["search_events", "typeahead_search"])
def test_both_search_surfaces_collapse_duplicate_fixtures(endpoint):
    """#2623 is the results page, #2580 is the dropdown. One helper, two seams."""
    functions = _search_route_functions()
    assert endpoint in functions, (
        f"{endpoint} is gone from routes/events.py — this guard cannot answer "
        "whether the dedup is still wired, so it fails rather than passes"
    )
    assert _calls_named(functions[endpoint], "collapse_duplicate_fixtures"), (
        f"{endpoint} no longer collapses duplicate fixtures — search will show "
        "a scoreless surname-only twin beside every real match again (#2623)"
    )


def test_the_printed_game_count_is_adjusted_for_the_collapse():
    """"· 16 games" beside nine rows is the same lie in a different font."""
    functions = _search_route_functions()
    assert _reads_name(functions["search_events"], "_fixture_duplicates_dropped"), (
        "search_events no longer reconciles total_results with the collapsed "
        "page — the header count would contradict the rows under it (#2623)"
    )


def test_the_dropdown_overfetches_so_the_collapse_cannot_empty_it():
    """Dedup after a tight LIMIT is a bucket collapse (LAT-P038/#1769)."""
    from app.routes import events as events_route

    assert events_route._EVENT_POOL_FETCH_LIMIT > events_route._EVENT_POOL_SIZE, (
        "the typeahead event fetch must be wider than the pool it fills, or a "
        "duplicate twin costs the dropdown a real suggestion"
    )


# --- #7700: the season-variant pair ----------------------------------------
#
# Transcribed from production 2026-09-21. `GET /api/events/search?q=kraken`
# returns nine rows, two of which are the same game: the ESPN-born
# `icehockey_nhl` row (anchor, no markets) and the Odds-API-born
# `icehockey_nhl_preseason` row (3 markets, 177–301 odds snapshots), eight
# minutes apart, both `completed`, both 4-2, adjacent on page one.

PRESEASON_TWINS = [
    # (parent row, variant row) — every NHL preseason game in the 2026-09-20
    # slate, from the table on #7700.
    (
        _FakeEvent(15312065, "New Jersey Devils", "New York Islanders",
                   _at("2026-09-20T17:00:00"), "icehockey_nhl", "completed", 1, 2),
        _FakeEvent(15316211, "New Jersey Devils", "New York Islanders",
                   _at("2026-09-20T17:08:11"), "icehockey_nhl_preseason",
                   "completed", 1, 2),
    ),
    (
        _FakeEvent(15312208, "Anaheim Ducks", "San Jose Sharks",
                   _at("2026-09-20T20:00:00"), "icehockey_nhl", "completed", 2, 6),
        _FakeEvent(15316224, "Anaheim Ducks", "San Jose Sharks",
                   _at("2026-09-20T20:08:32"), "icehockey_nhl_preseason",
                   "completed", 2, 6),
    ),
    (
        _FakeEvent(15312340, "Calgary Flames", "Seattle Kraken",
                   _at("2026-09-21T00:00:00"), "icehockey_nhl", "completed", 2, 4),
        _FakeEvent(15316214, "Calgary Flames", "Seattle Kraken",
                   _at("2026-09-21T00:08:24"), "icehockey_nhl_preseason",
                   "completed", 2, 4),
    ),
]


def test_the_kraken_final_is_rendered_once_and_it_is_the_priced_row():
    """#7700's repro: search `kraken`, see last night's Final listed twice."""
    from app.utils.search_fixture_dedup import collapse_duplicate_fixtures

    parent, variant = PRESEASON_TWINS[2]
    kept, dropped = collapse_duplicate_fixtures([variant, parent])

    assert dropped == 1
    assert [e.id for e in kept] == [15316214], (
        "the surviving row must be the season-variant one: its label is true "
        "for a September exhibition and it is the copy carrying the prices"
    )


def test_every_preseason_twin_on_the_slate_collapses():
    """Seven pairs on #7700's table; a reader should see seven games."""
    from app.utils.search_fixture_dedup import collapse_duplicate_fixtures

    page = [row for pair in PRESEASON_TWINS for row in pair]
    kept, dropped = collapse_duplicate_fixtures(page)

    assert dropped == len(PRESEASON_TWINS)
    assert [e.id for e in kept] == [15316211, 15316224, 15316214]


def test_two_rows_sharing_a_sport_key_are_still_left_alone():
    """The rejection this pass sits beside, unchanged.

    Two byte-identical league-sport rows at the same minute offer no grounds to
    prefer either. The variant pass must not become a general league-sport
    dominance rule by accident.
    """
    from app.utils.search_fixture_dedup import collapse_duplicate_fixtures

    first = _FakeEvent(201, "New York Yankees", "Los Angeles Angels",
                       _at("2026-09-01T23:05:00"), "baseball_mlb", "live", 1, 4)
    second = _FakeEvent(202, "New York Yankees", "Los Angeles Angels",
                        _at("2026-09-01T23:05:00"), "baseball_mlb", "live", 1, 4)

    kept, dropped = collapse_duplicate_fixtures([first, second])
    assert [e.id for e in kept] == [201, 202]
    assert dropped == 0


def test_two_variant_rows_are_left_alone():
    """Symmetry is the whole gate — two preseason rows have no survivor rule."""
    from app.utils.search_fixture_dedup import collapse_duplicate_fixtures

    first = _FakeEvent(211, "Calgary Flames", "Seattle Kraken",
                       _at("2026-09-21T00:00:00"), "icehockey_nhl_preseason",
                       "completed", 2, 4)
    second = _FakeEvent(212, "Calgary Flames", "Seattle Kraken",
                        _at("2026-09-21T00:08:24"), "icehockey_nhl_preseason",
                        "completed", 2, 4)

    kept, dropped = collapse_duplicate_fixtures([first, second])
    assert [e.id for e in kept] == [211, 212]
    assert dropped == 0


def test_the_same_clubs_the_next_night_keep_both_rows():
    """A preseason series plays the same opponent again — that is a fixture."""
    from app.utils.search_fixture_dedup import collapse_duplicate_fixtures

    tonight = _FakeEvent(221, "Calgary Flames", "Seattle Kraken",
                         _at("2026-09-21T00:00:00"), "icehockey_nhl",
                         "completed", 2, 4)
    tomorrow = _FakeEvent(222, "Calgary Flames", "Seattle Kraken",
                          _at("2026-09-22T02:00:00"), "icehockey_nhl_preseason",
                          "scheduled")

    kept, dropped = collapse_duplicate_fixtures([tonight, tomorrow])
    assert [e.id for e in kept] == [221, 222]
    assert dropped == 0


def test_a_thirty_one_minute_gap_is_two_fixtures():
    """The bound is the rule; one minute past it the pass must not fire."""
    from app.utils.search_fixture_dedup import collapse_duplicate_fixtures

    parent = _FakeEvent(231, "Calgary Flames", "Seattle Kraken",
                        _at("2026-09-21T00:00:00"), "icehockey_nhl",
                        "completed", 2, 4)
    variant = _FakeEvent(232, "Calgary Flames", "Seattle Kraken",
                         _at("2026-09-21T00:31:00"), "icehockey_nhl_preseason",
                         "completed", 2, 4)

    kept, dropped = collapse_duplicate_fixtures([parent, variant])
    assert [e.id for e in kept] == [231, 232]
    assert dropped == 0


def test_the_scored_row_survives_even_when_it_is_the_parent():
    """The result outranks the label: a scoreless variant never wins."""
    from app.utils.search_fixture_dedup import collapse_duplicate_fixtures

    parent = _FakeEvent(241, "Calgary Flames", "Seattle Kraken",
                        _at("2026-09-21T00:00:00"), "icehockey_nhl",
                        "completed", 2, 4)
    variant = _FakeEvent(242, "Calgary Flames", "Seattle Kraken",
                         _at("2026-09-21T00:08:24"), "icehockey_nhl_preseason",
                         "closed")

    kept, dropped = collapse_duplicate_fixtures([parent, variant])
    assert [e.id for e in kept] == [241], "the row with the result must survive"
    assert dropped == 1


def test_two_clubs_sharing_a_last_word_never_group():
    """Grouping is on both FULL names, and this is why.

    The ghost pass keys on the SURNAME because a tennis ghost carries nothing
    else. In league sport the last word is a nickname two clubs can share:
    `Chicago White Sox` and `Boston Red Sox` both end in "Sox", so a surname key
    reads a Yankees home game against each of them as one fixture written twice
    and deletes a real game.
    """
    from app.utils.search_fixture_dedup import collapse_duplicate_fixtures

    regular = _FakeEvent(251, "New York Yankees", "Chicago White Sox",
                         _at("2026-09-21T00:00:00"), "baseball_mlb",
                         "completed", 4, 2)
    spring = _FakeEvent(252, "New York Yankees", "Boston Red Sox",
                        _at("2026-09-21T00:10:00"), "baseball_mlb_preseason",
                        "scheduled")

    kept, dropped = collapse_duplicate_fixtures([regular, spring])
    assert [e.id for e in kept] == [251, 252]
    assert dropped == 0


def test_a_scoreless_twin_in_the_same_key_is_left_alone():
    """The asymmetry gate, pinned.

    Without it the pass degenerates into "the scored row beats the scoreless one
    within half an hour", which is a general league-sport dominance rule this
    module has already refused: two same-key rows are the event graph's problem,
    not the renderer's. A variant/parent pair is the only asymmetry it may read.
    """
    from app.utils.search_fixture_dedup import collapse_duplicate_fixtures

    scored = _FakeEvent(271, "Calgary Flames", "Seattle Kraken",
                        _at("2026-09-21T00:00:00"), "icehockey_nhl",
                        "completed", 2, 4)
    scoreless = _FakeEvent(272, "Calgary Flames", "Seattle Kraken",
                           _at("2026-09-21T00:08:24"), "icehockey_nhl",
                           "closed")

    kept, dropped = collapse_duplicate_fixtures([scored, scoreless])
    assert [e.id for e in kept] == [271, 272]
    assert dropped == 0


def test_different_leagues_never_pair_on_a_shared_suffix():
    """`_preseason` is not an identity — the league has to match too."""
    from app.utils.search_fixture_dedup import collapse_duplicate_fixtures

    hockey = _FakeEvent(261, "Calgary Flames", "Seattle Kraken",
                        _at("2026-09-21T00:00:00"), "icehockey_nhl",
                        "completed", 2, 4)
    football = _FakeEvent(262, "Calgary Flames", "Seattle Kraken",
                          _at("2026-09-21T00:08:00"),
                          "americanfootball_nfl_preseason", "completed", 2, 4)

    kept, dropped = collapse_duplicate_fixtures([hockey, football])
    assert [e.id for e in kept] == [261, 262]
    assert dropped == 0


def test_two_leagues_in_one_family_never_pair():
    """The group key is the LEAGUE, not the sport family.

    A preseason friendly between an MLS club and a second-division side is one
    match that two providers may file under two different leagues. Grouping on
    the family ("soccer") would let this pass delete one of them on an
    asymmetry it has no authority over: `sport_keys.league_identity` only ever
    rules a SEASON VARIANT to be its parent league, and these are two leagues.
    """
    from app.utils.search_fixture_dedup import collapse_duplicate_fixtures

    friendly = _FakeEvent(281, "Orlando City SC", "Tampa Bay Rowdies",
                          _at("2026-02-14T00:00:00"), "soccer_mls_preseason",
                          "completed", 1, 2)
    second_division = _FakeEvent(282, "Orlando City SC", "Tampa Bay Rowdies",
                                 _at("2026-02-14T00:10:00"),
                                 "soccer_usl_championship", "scheduled")

    kept, dropped = collapse_duplicate_fixtures([friendly, second_division])
    assert [e.id for e in kept] == [281, 282]
    assert dropped == 0


def test_the_collapse_does_not_depend_on_page_order():
    """A dedup whose answer moves with the caller's sort is a coin flip."""
    from app.utils.search_fixture_dedup import duplicate_fixture_event_ids

    page = [row for pair in PRESEASON_TWINS for row in pair]
    forward = duplicate_fixture_event_ids(page)
    backward = duplicate_fixture_event_ids(list(reversed(page)))

    assert forward == backward == {15312065, 15312208, 15312340}


def test_the_same_fixture_bound_matches_the_registrys():
    """A copied constant that can drift is a defect with a delay fuse."""
    from datetime import timedelta

    from app.services.event_registry import _SAME_FIXTURE_MAX_SEPARATION
    from app.utils.search_fixture_dedup import SAME_FIXTURE_MAX_SEPARATION_MINUTES

    assert _SAME_FIXTURE_MAX_SEPARATION == timedelta(
        minutes=SAME_FIXTURE_MAX_SEPARATION_MINUTES
    ), (
        "the renderer and the event graph disagree about how far apart two rows "
        "can sit and still be one fixture — search would hide a real game, or "
        "keep showing a twin the matcher already calls one"
    )


def test_a_live_twin_is_never_collapsed():
    """Measured casualty, 2026-09-21: the parent is the faster score rail.

    Rangers at Devils, 23:00Z: the ESPN-anchored `icehockey_nhl` row read 1-2
    while its `icehockey_nhl_preseason` twin read 0-1 at the same instant.
    Collapsing onto the variant would have shown a stale score as the only
    score, so a game in progress is out of scope for this pass entirely.
    """
    from app.utils.search_fixture_dedup import collapse_duplicate_fixtures

    espn = _FakeEvent(291, "New Jersey Devils", "New York Rangers",
                      _at("2026-09-21T23:00:00"), "icehockey_nhl", "live", 2, 1)
    odds = _FakeEvent(292, "New Jersey Devils", "New York Rangers",
                      _at("2026-09-21T23:08:14"), "icehockey_nhl_preseason",
                      "live", 1, 0)

    kept, dropped = collapse_duplicate_fixtures([espn, odds])
    assert [e.id for e in kept] == [291, 292]
    assert dropped == 0


def test_an_unknown_status_renders_both_rows():
    """A pass that only ever HIDES fails open on a status it cannot read."""
    from app.utils.search_fixture_dedup import collapse_duplicate_fixtures

    parent = _FakeEvent(301, "Calgary Flames", "Seattle Kraken",
                        _at("2026-09-21T00:00:00"), "icehockey_nhl",
                        "postponed", 2, 4)
    variant = _FakeEvent(302, "Calgary Flames", "Seattle Kraken",
                         _at("2026-09-21T00:08:24"), "icehockey_nhl_preseason",
                         "postponed", 2, 4)

    kept, dropped = collapse_duplicate_fixtures([parent, variant])
    assert [e.id for e in kept] == [301, 302]
    assert dropped == 0


def test_an_upcoming_preseason_twin_collapses_onto_the_priced_row():
    """Pre-game there is no score to go stale, and the prices are the point."""
    from app.utils.search_fixture_dedup import collapse_duplicate_fixtures

    parent = _FakeEvent(311, "Calgary Flames", "Seattle Kraken",
                        _at("2026-09-25T01:40:00"), "icehockey_nhl", "scheduled")
    variant = _FakeEvent(312, "Calgary Flames", "Seattle Kraken",
                         _at("2026-09-25T01:48:00"), "icehockey_nhl_preseason",
                         "scheduled")

    kept, dropped = collapse_duplicate_fixtures([parent, variant])
    assert [e.id for e in kept] == [312]
    assert dropped == 1
