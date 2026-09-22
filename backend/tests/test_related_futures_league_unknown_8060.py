"""#8060 — a WNBA game page stops offering its clubs the NBA playoffs.

WHAT A READER SAW, production 2026-09-22 17:36Z, `/events/15310072`
(Connecticut Sun vs Toronto Tempo, WNBA, two days out). The season panel headed
**Tempo** held fourteen rows and thirteen of them were the Toronto **Raptors**:
`NBA Playoff Qualifiers 71%`, `Pro Basketball Atlantic Division Winner 13%`,
`NBA: 2027 Champion`, `Will Toronto Raptors advance to the Eastern Conference
Finals` … The panel beside it, headed **Sun**, offered `NEC Men's Conference
Tournament Champion — Central Connecticut St.`

THE CAUSE IS NOT THE ONE THE SYMPTOM SUGGESTS, and that is why this file
guards the wiring rather than the filter. `_build_related_futures` already has
a symmetric gender filter that would have refused every Raptors row. It never
ran: the event's sport key is `basketball_other`, so `is_womens` and
`is_mens_specific` are both false and the filter is never armed. The clubs are
not confused about their league — `Connecticut Sun` and `Toronto Tempo` are
both `basketball_wnba` in `teams`. Only the event's row is.

WHAT IS PINNED HERE, and what is deliberately NOT:

* the two pure predicates, and that `_is_womens_league_key` cannot drift from
  the `is_womens` line inside the route (read out of the route's own AST, so
  the pin breaks if somebody edits the route and not the helper);
* that `_both_clubs_are_womens_only` says no on each of the three uncertainties
  the production census found, and that its query is really scoped to both
  names and the sport prefix rather than answering from a fake;
* NOT that the served page changes. That is a claim about SQL this file does
  not execute, and it is paid on production in the #8060 after-check — the
  Tempo panel losing its thirteen Raptors rows while `WNBA: 2026 Champion` and
  `Women's Pro Basketball Champion` stay.
"""

from __future__ import annotations

import ast
import inspect
import textwrap

import pytest

from app.routes import events as events_module
from app.routes.events import (
    _WOMENS_LEAGUE_SPORT_KEYS,
    _both_clubs_are_womens_only,
    _is_womens_league_key,
    _sport_key_names_no_league,
)


# --------------------------------------------------------------------------
# The pure predicates
# --------------------------------------------------------------------------

class TestIsWomensLeagueKey:

    @pytest.mark.parametrize("key", [
        "basketball_wnba",
        "basketball_wncaab",
        "soccer_fifa_womens_world_cup",
        "BASKETBALL_WNBA",
    ])
    def test_womens_keys_are_recognised(self, key):
        assert _is_womens_league_key(key) is True

    @pytest.mark.parametrize("key", [
        "basketball_nba",
        "basketball_ncaab",
        "basketball_other",
        "basketball_nba_summer_league",
        "americanfootball_nfl",
        "",
        None,
    ])
    def test_everything_else_is_not(self, key):
        assert _is_womens_league_key(key) is False

    def test_wnba_is_not_reachable_by_the_substring_markers_alone(self):
        """The reason `_WOMENS_LEAGUE_SPORT_KEYS` exists as its own name.

        `basketball_wnba` contains neither `_women` nor `wncaa`, so a predicate
        built only from `_WOMENS_SPORT_KEY_MARKERS` reads the WNBA as a men's
        league — silently, and in the direction that costs a reader the fix.
        """
        markers = events_module._WOMENS_SPORT_KEY_MARKERS
        assert not any(m in "basketball_wnba" for m in markers)
        assert _is_womens_league_key("basketball_wnba") is True


class TestSportKeyNamesNoLeague:

    @pytest.mark.parametrize("key", [
        "basketball_other", "soccer_other", "tennis_other",
        "americanfootball_other", "BASKETBALL_OTHER",
    ])
    def test_catch_all_keys(self, key):
        assert _sport_key_names_no_league(key) is True

    @pytest.mark.parametrize("key", [
        "basketball_wnba", "basketball_nba", "soccer_epl", "", None,
        "otherbasketball",
    ])
    def test_keys_that_name_a_league(self, key):
        assert _sport_key_names_no_league(key) is False


class TestHelperCannotDriftFromTheRoute:
    """`_is_womens_league_key` and the route's own `is_womens` must agree.

    Read out of `_build_related_futures`'s AST rather than restated here: a
    test that restates the route's literals passes forever no matter what the
    route does, which is the failure mode this pin exists to avoid.
    """

    @staticmethod
    def _route_womens_literals() -> set[str]:
        tree = ast.parse(
            textwrap.dedent(inspect.getsource(events_module._build_related_futures))
        )
        for node in ast.walk(tree):
            if not isinstance(node, ast.Assign):
                continue
            targets = [t.id for t in node.targets if isinstance(t, ast.Name)]
            if "is_womens" not in targets:
                continue
            return {
                n.value for n in ast.walk(node.value)
                if isinstance(n, ast.Constant) and isinstance(n.value, str)
            }
        raise AssertionError(
            "no `is_womens = ...` assignment found in _build_related_futures — "
            "if it was renamed, re-point this pin rather than deleting it"
        )

    def test_the_pin_actually_found_something(self):
        """Guard the guard: an empty set would make the assertion below vacuous."""
        assert self._route_womens_literals()

    def test_every_league_the_route_calls_womens_the_helper_also_does(self):
        for literal in self._route_womens_literals():
            if not literal.startswith("_"):  # `_women` is the substring clause
                assert _is_womens_league_key(literal) is True, (
                    f"the route treats {literal!r} as a women's league and the "
                    f"helper does not — they decide the same question"
                )

    def test_the_explicit_set_covers_the_routes_explicit_set(self):
        explicit = {
            lit for lit in self._route_womens_literals() if not lit.startswith("_")
        }
        assert explicit <= _WOMENS_LEAGUE_SPORT_KEYS


class TestTheWiringItself:
    """The helpers can be perfect and the page still wrong if nothing calls them.

    Every other class here would stay green if the two lines inside
    `_build_related_futures` were reverted, because none of them executes the
    route. Driving the route needs a session that answers a dozen unrelated
    queries, so this pins the wiring out of the AST instead. It is a structural
    pin and says nothing about what the page serves — that is the production
    after-check's job, named in the module docstring.
    """

    @staticmethod
    def _tree():
        return ast.parse(
            textwrap.dedent(inspect.getsource(events_module._build_related_futures))
        )

    def test_the_womens_branch_consults_the_team_derived_flag(self):
        for node in ast.walk(self._tree()):
            if not isinstance(node, ast.If):
                continue
            assigns_women = any(
                isinstance(s, ast.Assign)
                and any(
                    isinstance(t, ast.Name) and t.id == "gender_market_name_filter"
                    for t in s.targets
                )
                and isinstance(s.value, ast.Constant)
                and s.value.value == "women"
                for s in node.body
            )
            if not assigns_women:
                continue
            names = {
                n.id for n in ast.walk(node.test) if isinstance(n, ast.Name)
            }
            assert "womens_by_team" in names, (
                "the `women` filter is armed without consulting the "
                "team-derived flag — #8060's WNBA pages go back to offering "
                "the NBA playoffs"
            )
            assert "is_womens" in names, "the original sport-key arm was dropped"
            return
        raise AssertionError(
            'no `gender_market_name_filter = "women"` branch found in the route'
        )

    def test_the_flag_is_derived_from_the_club_lookup(self):
        calls = {
            n.func.id
            for n in ast.walk(self._tree())
            if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
        }
        assert "_both_clubs_are_womens_only" in calls
        assert "_sport_key_names_no_league" in calls, (
            "the lookup must be gated on the key naming no league, or it runs "
            "on every event page in the site"
        )


# --------------------------------------------------------------------------
# The club lookup
# --------------------------------------------------------------------------

class _FakeResult:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return self._rows


class _FakeDB:
    """Records the statement it was handed, so the scoping can be asserted.

    A fake that only replays rows proves the bookkeeping and nothing about the
    query; `TestTheQueryIsReallyScoped` reads `statements` so that a helper
    which dropped its WHERE clause could not pass this file.
    """

    def __init__(self, rows):
        self.rows = rows
        self.statements: list = []

    async def execute(self, stmt):
        self.statements.append(stmt)
        return _FakeResult(self.rows)


async def _ask(rows, home="Connecticut Sun", away="Toronto Tempo", prefix="basketball"):
    db = _FakeDB(rows)
    verdict = await _both_clubs_are_womens_only(db, home, away, prefix)
    return verdict, db


class TestBothClubsAreWomensOnly:

    @pytest.mark.asyncio
    async def test_the_specimen_both_sides_wnba(self):
        """The real production rows for `/events/15310072`."""
        verdict, _ = await _ask([
            ("Connecticut Sun", "basketball_wnba"),
            ("Toronto Tempo", "basketball_wnba"),
        ])
        assert verdict is True

    @pytest.mark.asyncio
    async def test_no_rows_at_all(self):
        """4,061 of the 4,374 names on production's `basketball_other` events."""
        verdict, _ = await _ask([])
        assert verdict is False

    @pytest.mark.asyncio
    async def test_one_side_unresolved(self):
        verdict, _ = await _ask([("Connecticut Sun", "basketball_wnba")])
        assert verdict is False

    @pytest.mark.asyncio
    async def test_one_side_is_a_mens_league(self):
        verdict, _ = await _ask([
            ("Connecticut Sun", "basketball_wnba"),
            ("Toronto Tempo", "basketball_nba"),
        ])
        assert verdict is False

    @pytest.mark.asyncio
    async def test_a_name_that_is_not_unanimous_is_refused(self):
        """The 238 MIXED names — one school, two programs, same name.

        `Belmont Bruins` holds rows in `basketball_ncaab` AND
        `basketball_wncaab`; the name does not say which is playing.
        """
        verdict, _ = await _ask(
            [
                ("Belmont Bruins", "basketball_wncaab"),
                ("Belmont Bruins", "basketball_ncaab"),
                ("Lipscomb Bisons", "basketball_wncaab"),
            ],
            home="Belmont Bruins",
            away="Lipscomb Bisons",
        )
        assert verdict is False

    @pytest.mark.asyncio
    async def test_a_lone_national_side_does_not_arm_the_filter(self):
        """`Japan` and `Nigeria` each carry one row and it is `basketball_wnba`.

        Alone, either would arm a women's refusal on a men's international.
        All 34 of their production `basketball_other` fixtures pair them with
        names that resolve to no women's row, which is why demanding BOTH sides
        drops every one of them — measured 0 of the 207 events this fires on.
        """
        verdict, _ = await _ask(
            [("Japan", "basketball_wnba")],
            home="Japan",
            away="Spain",
        )
        assert verdict is False

    @pytest.mark.asyncio
    async def test_both_national_sides_resolving_womens_would_fire(self):
        """Stated so the boundary is a decision on the record, not an accident.

        Two names that BOTH resolve women's-only do arm the filter. Production
        has no such fixture today (0 of 207); if one appears, the women's
        refusal is the right answer for it anyway.
        """
        verdict, _ = await _ask(
            [("Japan", "basketball_wnba"), ("Nigeria", "basketball_wnba")],
            home="Japan",
            away="Nigeria",
        )
        assert verdict is True


class TestTheQueryIsReallyScoped:
    """Anti-vacuity: the fake answers any query, so read the query.

    Without these, a helper that selected every team in the table would pass
    every arm above.
    """

    @pytest.mark.asyncio
    async def test_both_names_and_the_prefix_reach_the_sql(self):
        _, db = await _ask([
            ("Connecticut Sun", "basketball_wnba"),
            ("Toronto Tempo", "basketball_wnba"),
        ])
        assert len(db.statements) == 1
        sql = str(
            db.statements[0].compile(compile_kwargs={"literal_binds": True})
        )
        assert "Connecticut Sun" in sql
        assert "Toronto Tempo" in sql
        assert "basketball%" in sql

    @pytest.mark.asyncio
    async def test_the_prefix_is_the_events_own_sport(self):
        """A `soccer_other` event must not be decided by a basketball club."""
        _, db = await _ask(
            [("Toronto Tempo", "basketball_wnba")],
            prefix="soccer",
        )
        sql = str(
            db.statements[0].compile(compile_kwargs={"literal_binds": True})
        )
        assert "soccer%" in sql
        assert "basketball%" not in sql

    @pytest.mark.asyncio
    async def test_no_query_is_issued_for_an_empty_name(self):
        """The caller guards this, but the helper must not build a bare IN ()."""
        verdict, db = await _ask([], home="", away="")
        assert verdict is False
        assert len(db.statements) == 1
