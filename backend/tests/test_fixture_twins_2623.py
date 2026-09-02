"""#2623 — one fixture, one row, and the two controls that keep it honest.

RED-FIRST: every test in `TestTheSabalenkaPage` fails on master, where nothing
collapses anything. `TestTheControlsThatCaughtMe` is the important half: those
cases were GREEN on master, went RED against the first cut of
`collapse_fixture_twins`, and are green again only because the rule was
tightened. They must stay green on both trees forever.

Every row below is a verbatim production row from `events`, 2026-09-01.
"""

from datetime import datetime, timedelta, timezone
from importlib import import_module

import pytest


def _sym(module_path, name):
    """Fetch a #2623 symbol, or FAIL BY ASSERTION naming what is missing.

    Lazy on purpose: `app.utils.fixture_twins` does not exist on a tree without
    the fix, so a module-scope import would make this file ERROR at collection
    instead of FAILING. A red-first proof that cannot produce a failure count is
    not a proof.
    """
    try:
        module = import_module(module_path)
    except ModuleNotFoundError:  # pragma: no cover - only on the pre-fix tree
        module = None
    assert module is not None, (
        f"{module_path} does not exist on this tree — #2623 is not applied"
    )
    sym = getattr(module, name, None)
    assert sym is not None, (
        f"{module_path}.{name} does not exist on this tree — #2623 is not applied"
    )
    return sym


def collapse_fixture_twins(rows):
    return _sym("app.utils.fixture_twins", "collapse_fixture_twins")(rows)


def same_fixture(a, b):
    return _sym("app.utils.fixture_twins", "same_fixture")(a, b)


def auto_create_is_stale_fixture(commence_time, now):
    return _sym(
        "app.tasks.prediction_market_matching", "auto_create_is_stale_fixture"
    )(commence_time, now)


def T(iso):
    return datetime.fromisoformat(iso).replace(tzinfo=timezone.utc)


def row(id, sport_key, home, away, when, source, hs=None, aws=None):
    return {
        "id": id,
        "sport_key": sport_key,
        "home_team_name": home,
        "away_team_name": away,
        "commence_time": T(when),
        "commence_time_source": source,
        "home_score": hs,
        "away_score": aws,
    }


# The nine Sabalenka fixtures as they actually sat in `events`: sixteen rows.
SABALENKA_PAGE = [
    row(15201774, "tennis_wta", "Sabalenka", "Bejlek", "2026-09-03T00:30", "kalshi"),
    row(15299512, "tennis_wta_us_open", "Aryna Sabalenka", "Polina Iatcenko",
        "2026-09-02T23:00", "odds_api"),
    row(15299435, "tennis_wta", "Sabalenka", "Iatcenko", "2026-09-02T00:00", "kalshi_ticker"),
    row(15293679, "tennis_wta_us_open", "Aryna Sabalenka", "Maria Camila Osorio Serrano",
        "2026-08-30T15:00", "odds_api"),
    row(15300722, "tennis_wta", "Sabalenka", "Bejlek", "2026-08-20T04:14", "kalshi"),
    row(15206893, "tennis_wta_cincinnati_open", "Aryna Sabalenka", "Sara Bejlek",
        "2026-08-20T00:30", "odds_api", 0, 2),
    row(15205016, "tennis_wta", "Sabalenka", "Wang", "2026-08-19T00:10", "kalshi"),
    row(15200246, "tennis_wta_cincinnati_open", "Aryna Sabalenka", "Xinyu Wang",
        "2026-08-18T12:00", "odds_api", 2, 0),
    row(15209624, "tennis_wta", "Sabalenka", "Gibson", "2026-08-16T21:10", "kalshi"),
    row(15199002, "tennis_wta_cincinnati_open", "Aryna Sabalenka", "Talia Gibson",
        "2026-08-16T15:00", "odds_api", 2, 0),
    row(15197940, "tennis_wta", "Sabalenka", "Alexandrova", "2026-08-09T01:44", "kalshi"),
    row(15191375, "tennis_wta_canadian_open", "Aryna Sabalenka", "Ekaterina Alexandrova",
        "2026-08-09T19:00", "odds_api", 1, 2),
    row(15189260, "tennis_wta_canadian_open", "Aryna Sabalenka", "Shuai Zhang",
        "2026-08-07T19:00", "odds_api", 2, 0),
    row(15197994, "tennis_wta", "Sabalenka", "Zhang", "2026-08-07T00:50", "kalshi"),
    row(15187257, "tennis_wta_canadian_open", "Aryna Sabalenka", "Moyuka Uchijima",
        "2026-08-05T19:00", "odds_api", 2, 0),
    row(15197957, "tennis_wta", "Sabalenka", "Uchijima", "2026-08-05T00:40", "kalshi"),
]


class TestTheSabalenkaPage:
    def test_sixteen_rows_become_nine(self):
        # The issue's own count: "16 event rows for 9 distinct matches".
        result = collapse_fixture_twins(SABALENKA_PAGE)
        assert len(result.kept) == 9
        assert result.dropped_count == 7

    def test_the_scoreless_ghost_goes_and_the_scored_row_stays(self):
        result = collapse_fixture_twins(SABALENKA_PAGE)
        kept_ids = {r["id"] for r in result.kept}
        assert 15300722 not in kept_ids      # 'Sabalenka v Bejlek', closed, no score
        assert 15206893 in kept_ids          # 'Aryna Sabalenka v Sara Bejlek', 0-2

    def test_the_upcoming_match_is_offered_once(self):
        # The worst one a reader sees: the SAME first-round match at two times
        # on two days — "Today 5:00 PM, –/–" beside "Tomorrow 4:00 PM, 94%/6%".
        result = collapse_fixture_twins(SABALENKA_PAGE)
        kept_ids = {r["id"] for r in result.kept}
        assert 15299435 not in kept_ids
        assert 15299512 in kept_ids

    def test_a_surname_meets_a_full_name(self):
        assert same_fixture(SABALENKA_PAGE[4], SABALENKA_PAGE[5])

    def test_the_generic_venue_bucket_meets_the_per_tournament_key(self):
        # `tennis_wta` (551 live rows) vs `tennis_wta_cincinnati_open` (132). A
        # same-`sport_key` test would never have found a single pair.
        assert SABALENKA_PAGE[4]["sport_key"] != SABALENKA_PAGE[5]["sport_key"]
        assert same_fixture(SABALENKA_PAGE[4], SABALENKA_PAGE[5])

    def test_every_drop_names_the_row_it_kept(self):
        # Ruling 054 — a removed row leaves with a reason and a number.
        result = collapse_fixture_twins(SABALENKA_PAGE)
        kept_ids = {r["id"] for r in result.kept}
        assert result.dropped
        for ghost, keeper_id in result.dropped:
            assert keeper_id in kept_ids
            assert ghost["commence_time_source"] in _sym("app.utils.fixture_twins", "VENUE_SOURCES")

    def test_the_third_bejlek_ghost_survives_and_that_is_correct(self):
        # 15201774 is a Kalshi row for the Bejlek fixture dated 2026-09-03 — two
        # WEEKS from the match it duplicates, far outside the window. It is a
        # real residual, and hiding it would need evidence this module does not
        # have. Named here so the residual is a recorded fact, not a surprise.
        result = collapse_fixture_twins(SABALENKA_PAGE)
        assert 15201774 in {r["id"] for r in result.kept}


class TestTheControlsThatCaughtMe:
    """Green on master, RED against the first cut, green again after tightening."""

    def test_two_schedule_sources_are_never_collapsed(self):
        # The first cut ranked by `_SOURCE_PRIORITY` and hid a `statpal` MLB row
        # behind an `espn` one. statpal is a schedule, not a venue.
        rows = [
            row(15292569, "baseball_mlb", "Boston Red Sox", "Seattle Mariners",
                "2026-09-01T22:45", "statpal", 6, 9),
            row(15299424, "baseball_mlb", "Boston Red Sox", "Seattle Mariners",
                "2026-09-01T22:45", "espn", 6, 9),
        ]
        assert collapse_fixture_twins(rows).dropped_count == 0

    def test_two_legs_of_a_series_are_never_collapsed(self):
        # The one that mattered: 08-29 17:05 and 08-30 17:35 are DIFFERENT GAMES
        # 24.5 hours apart — inside the 30-hour window. The first cut hid one.
        rows = [
            row(14877917, "baseball_mlb", "New York Yankees", "Boston Red Sox",
                "2026-08-29T17:05", "statpal", 0, 0),
            row(15296514, "baseball_mlb", "New York Yankees", "Boston Red Sox",
                "2026-08-30T17:35", "espn", 16, 1),
        ]
        assert collapse_fixture_twins(rows).dropped_count == 0

    def test_a_ghost_matching_two_real_fixtures_hides_nothing(self):
        # Condition 4. It cannot say WHICH one it duplicates, so it says nothing.
        rows = [
            row(1, "baseball_mlb", "Yankees", "Red Sox", "2026-08-29T20:00", "kalshi"),
            row(2, "baseball_mlb", "New York Yankees", "Boston Red Sox",
                "2026-08-29T17:05", "espn", 0, 6),
            row(3, "baseball_mlb", "New York Yankees", "Boston Red Sox",
                "2026-08-29T23:15", "espn", 9, 2),
        ]
        result = collapse_fixture_twins(rows)
        assert result.dropped_count == 0
        assert len(result.kept) == 3

    def test_an_unrecorded_source_is_not_a_venue(self):
        # Most of the table predates the column. Treating NULL as fabrication
        # would hide real events by the thousand.
        rows = [
            row(1, "tennis_wta", "Sabalenka", "Bejlek", "2026-08-20T04:14", None),
            row(2, "tennis_wta_cincinnati_open", "Aryna Sabalenka", "Sara Bejlek",
                "2026-08-20T00:30", "odds_api", 0, 2),
        ]
        assert collapse_fixture_twins(rows).dropped_count == 0

    def test_an_unrecorded_source_is_not_a_schedule_either(self):
        rows = [
            row(1, "tennis_wta", "Sabalenka", "Bejlek", "2026-08-20T04:14", "kalshi"),
            row(2, "tennis_wta_cincinnati_open", "Aryna Sabalenka", "Sara Bejlek",
                "2026-08-20T00:30", None, 0, 2),
        ]
        assert collapse_fixture_twins(rows).dropped_count == 0

    def test_two_venue_rows_are_never_collapsed_into_each_other(self):
        rows = [
            row(1, "tennis_atp", "Lopez Alcaraz", "Patier", "2026-08-05T15:17", "kalshi"),
            row(2, "tennis_atp", "Lopez Alcaraz", "Patier", "2026-08-05T17:00", "polymarket"),
        ]
        assert collapse_fixture_twins(rows).dropped_count == 0

    def test_a_ghost_holding_the_only_score_is_kept(self):
        rows = [
            row(1, "tennis_wta", "Sabalenka", "Bejlek", "2026-08-20T04:14", "kalshi", 0, 2),
            row(2, "tennis_wta_us_open", "Aryna Sabalenka", "Sara Bejlek",
                "2026-08-20T00:30", "odds_api"),
        ]
        assert collapse_fixture_twins(rows).dropped_count == 0

    def test_different_sports_are_never_one_fixture(self):
        rows = [
            row(1, "tennis_wta", "Lakers", "Thunder", "2026-06-11T03:41", "kalshi"),
            row(2, "basketball_nba", "Lakers", "Thunder", "2026-06-11T03:41", "espn", 88, 92),
        ]
        assert collapse_fixture_twins(rows).dropped_count == 0

    def test_outside_the_window_nothing_collapses(self):
        rows = [
            row(1, "tennis_wta", "Sabalenka", "Bejlek",
                "2026-08-20T00:30", "kalshi"),
            row(2, "tennis_wta_us_open", "Aryna Sabalenka", "Sara Bejlek",
                "2026-08-22T12:00", "odds_api", 0, 2),
        ]
        assert (rows[1]["commence_time"] - rows[0]["commence_time"]) > _sym("app.utils.fixture_twins", "TWIN_WINDOW")
        assert collapse_fixture_twins(rows).dropped_count == 0

    def test_orientation_is_not_identity(self):
        rows = [
            row(1, "tennis_atp", "Faria", "Alcaraz", "2026-09-02T00:00", "kalshi_ticker"),
            row(2, "tennis_atp_us_open", "Carlos Alcaraz", "Jaime Faria",
                "2026-09-03T00:10", "odds_api"),
        ]
        assert collapse_fixture_twins(rows).dropped_count == 1

    def test_the_two_source_sets_are_disjoint(self):
        assert not (_sym("app.utils.fixture_twins", "VENUE_SOURCES")
                    & _sym("app.utils.fixture_twins", "SCHEDULE_SOURCES"))

    def test_order_is_preserved(self):
        result = collapse_fixture_twins(SABALENKA_PAGE)
        original = [r["id"] for r in SABALENKA_PAGE]
        assert [r["id"] for r in result.kept] == [
            i for i in original if i in {k["id"] for k in result.kept}
        ]

    def test_an_empty_page_collapses_to_an_empty_page(self):
        result = collapse_fixture_twins([])
        assert result.kept == [] and result.dropped_count == 0


class TestTheCreateThatMintsThem:
    """`auto_create_is_stale_fixture` — the producer half."""

    NOW = T("2026-09-01T22:05")

    def test_the_specimen_is_refused(self):
        # Event 15300722: created 2026-09-01 22:05 for a fixture that started
        # 2026-08-20 04:14. Twelve days.
        assert auto_create_is_stale_fixture(T("2026-08-20T04:14"), self.NOW) is True

    def test_a_match_that_may_still_be_running_is_allowed(self):
        assert auto_create_is_stale_fixture(self.NOW - timedelta(hours=1), self.NOW) is False
        assert auto_create_is_stale_fixture(self.NOW - timedelta(hours=11), self.NOW) is False

    def test_a_midnight_ticker_stand_in_still_clears_the_bound(self):
        # A ticker DATE resolves to midnight UTC; a match played at 23:00 local
        # on that day sits ~30h after its own stand-in. Refusing it would delete
        # a fixture that really happened.
        assert auto_create_is_stale_fixture(self.NOW - timedelta(hours=30), self.NOW) is False

    def test_a_future_fixture_is_never_stale(self):
        assert auto_create_is_stale_fixture(self.NOW + timedelta(days=3), self.NOW) is False

    def test_absence_is_not_age(self):
        # gotcha #53. A missing time is not an old one.
        assert auto_create_is_stale_fixture(None, self.NOW) is False
        assert auto_create_is_stale_fixture(self.NOW, None) is False

    @pytest.mark.parametrize("hours,expected", [(35, False), (37, True)])
    def test_the_bound_is_where_it_says_it_is(self, hours, expected):
        assert _sym("app.tasks.prediction_market_matching", "AUTO_CREATE_MAX_PAST_AGE") == timedelta(hours=36)
        assert auto_create_is_stale_fixture(
            self.NOW - timedelta(hours=hours), self.NOW
        ) is expected


class TestItIsActuallyWiredIn:
    """A pure function nobody calls is a pure function nobody calls.

    `collapse_fixture_twins` is correct in isolation and worth nothing until
    `/api/events/search` runs it — which is the surface the shopper photographed.
    Scanned as an AST so a mention in a comment cannot satisfy it.
    """

    def _search_route_calls(self):
        import ast
        import inspect

        import app.routes.events as events_module

        tree = ast.parse(inspect.getsource(events_module))
        for node in ast.walk(tree):
            if isinstance(node, ast.AsyncFunctionDef) and node.name == "search_events":
                return {
                    call.func.id
                    for call in ast.walk(node)
                    if isinstance(call, ast.Call) and isinstance(call.func, ast.Name)
                }
        raise AssertionError("search_events not found in app/routes/events.py")

    def test_search_collapses_before_it_formats(self):
        calls = self._search_route_calls()
        assert "collapse_fixture_twins" in calls, (
            "/api/events/search does not collapse fixture twins — #2623's fix is "
            "not reachable from the surface it was filed against"
        )
        assert "event_rows_for_collapse" in calls, (
            "the collapse is reading ORM rows directly, which lazy-loads "
            "`Event.sport` once per row inside a supposedly pure pass"
        )

    def test_the_hidden_count_is_reported_and_the_total_is_reduced(self):
        import inspect

        import app.routes.events as events_module

        source = inspect.getsource(events_module.search_events)
        assert "duplicate_fixtures_hidden" in source
        assert "total_count - duplicate_fixtures_hidden" in source, (
            "the results line would promise rows the page deliberately hid"
        )

    def test_the_stale_create_guard_is_reachable_from_the_auto_create(self):
        import ast
        import inspect

        import app.tasks.prediction_market_matching as pmm

        tree = ast.parse(inspect.getsource(pmm))
        called = {
            node.func.id
            for node in ast.walk(tree)
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
        }
        assert "auto_create_is_stale_fixture" in called, (
            "the born-finished refusal is defined and never consulted"
        )
