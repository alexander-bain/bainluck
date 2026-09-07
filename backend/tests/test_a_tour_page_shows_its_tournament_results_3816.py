"""#3816 — a TOUR's league page covers the tournaments the tour is playing.

═══ THE SHIP ═══

Through the whole 2026 US Open, `/leagues/tennis_atp` said "no recent results"
while 117 settled men's singles matches sat one sport key away in
`tennis_atp_us_open`, each carrying a score, a `completed_at` and an `espn_id`.
Measured on production 2026-09-07 over 14 days:

    key                    status      rows   scores
    tennis_atp             suspended    593        0
    tennis_atp             scheduled    266        0
    tennis_atp             completed      0        —     <- the rail reads THIS
    tennis_atp_us_open     completed    101      101
    tennis_atp_us_open     closed        16       16

The rail was correct about its own key and useless to a reader, because a tour
is not a league: the ATP season is a run of tournaments and each tournament gets
its own bucket, leaving the tour's own key holding qualifiers and Challengers.

═══ WHAT THIS FILE GUARDS, AND IN BOTH DIRECTIONS (gotcha #43) ═══

The widening is the easy half. The half that will break is the OTHER one: 15
sport keys have prefix-children and only two of them have children that are the
same competition. A future reader who "simplifies"
:data:`~app.utils.sport_keys.TOUR_PARENT_SPORT_KEYS` into a `LIKE parent || '_%'`
rule gets a green diff and four silent bugs — women's Bundesliga folded into the
men's page among them. So every one of those four is named here as its own
assertion, and they are named because they EXIST, not as hypotheticals.
"""

import asyncio
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy.dialects import postgresql

from app.routes.league_futures import (
    _scope_condition,
    build_league,
    league_scope_sport_keys,
    recent_results_query,
    unreported_games_query,
    upcoming_games_query,
)
from app.utils.sport_keys import TOUR_PARENT_SPORT_KEYS, tour_child_key_prefix

NOW = datetime(2026, 9, 7, 9, 0, tzinfo=timezone.utc)

#: Every sport key that has prefix-children but is NOT a tour, with the child
#: that would be wrongly folded in. Read off `sports` on production
#: 2026-09-07 — these are the real rows, not invented counter-examples.
NOT_TOURS_WITH_CHILDREN = [
    ("soccer_germany_bundesliga", "soccer_germany_bundesliga_women"),
    ("cricket_the_hundred", "cricket_the_hundred_womens"),
    ("americanfootball_nfl", "americanfootball_nfl_preseason"),
    ("basketball_nba", "basketball_nba_all_stars"),
    ("icehockey_nhl", "icehockey_nhl_championship_winner"),
    ("basketball_ncaab", "basketball_ncaab_championship_winner"),
    ("baseball_mlb", "baseball_mlb_preseason"),
    ("soccer_fifa_world_cup", "soccer_fifa_world_cup_qualifiers_europe"),
]


def _sql(query) -> str:
    return str(query.compile(dialect=postgresql.dialect()))


# ─────────────────────── the vocabulary ───────────────────────


@pytest.mark.parametrize("parent", sorted(TOUR_PARENT_SPORT_KEYS))
def test_a_tour_parent_names_its_children(parent: str):
    prefix = tour_child_key_prefix(parent)
    assert prefix is not None
    # The `_` inside the key is escaped, so the pattern cannot match a key that
    # merely resembles it. Unescaped, `tennis_atp_%` matches `tennisXatpY`.
    assert prefix == parent.replace("_", r"\_") + r"\_%"
    assert r"\_%" in prefix


@pytest.mark.parametrize("parent,child", NOT_TOURS_WITH_CHILDREN)
def test_a_league_with_prefix_children_is_not_a_tour(parent: str, child: str):
    """🔴 THE REGRESSION THIS FILE EXISTS FOR.

    Each of these pairs is a real parent/child prefix relationship in `sports`,
    and in each one the child is a DIFFERENT competition — a women's league, a
    preseason, an exhibition, a futures bucket. Folding it into the parent's
    games rails is a bug, and a prefix rule cannot tell it apart from the US
    Open under the ATP tour.
    """
    assert parent not in TOUR_PARENT_SPORT_KEYS
    assert tour_child_key_prefix(parent) is None
    # And the child must never itself be treated as a tour parent.
    assert tour_child_key_prefix(child) is None


def test_only_the_two_tennis_tours_are_tours():
    """An exact set, so ADDING one is a decision somebody makes on purpose."""
    assert TOUR_PARENT_SPORT_KEYS == frozenset({"tennis_atp", "tennis_wta"})


# ─────────────────────── the scope condition ───────────────────────


def test_one_key_still_compiles_to_plain_equality():
    """The 27 non-tour leagues must emit the statement they always emitted.

    Every block count, needle and plan measurement in `league_futures` was taken
    on `sports.key = :key`. If a single-key scope started compiling to `IN`, all
    of them would quietly become claims about a statement nobody measured.
    """
    sql = _sql(recent_results_query("baseball_mlb", NOW))
    assert "sports.key = " in sql
    assert "sports.key IN" not in sql


def test_a_tour_scope_compiles_to_an_in_list():
    sql = _sql(recent_results_query(["tennis_atp", "tennis_atp_us_open"], NOW))
    assert "sports.key IN" in sql


def test_a_one_element_list_is_still_equality():
    """A tour out of season resolves to just itself, and must not pay for an
    `IN` — this is the off-season plan, and it is the common case for 10 months
    of the year."""
    assert "sports.key IN" not in _sql(recent_results_query(["tennis_atp"], NOW))


def test_the_fence_survives_the_widening():
    """`OFFSET 0` is the results rail's optimization fence (LAT-P110, #2260) and
    the widened scope must not be an excuse to lose it."""
    for scope in ("baseball_mlb", ["tennis_atp", "tennis_atp_us_open"]):
        assert "LIMIT ALL OFFSET 0" in _sql(recent_results_query(scope, NOW))
        assert "LIMIT ALL OFFSET 0" in _sql(unreported_games_query(scope, NOW))


def test_all_three_rails_take_the_widened_scope():
    """Both directions. A widening that reached the results rail only would put
    the US Open's Finals on the page while its upcoming matches stayed off it —
    one page describing two different competitions."""
    scope = ["tennis_atp", "tennis_atp_us_open"]
    for builder in (upcoming_games_query, recent_results_query, unreported_games_query):
        assert "sports.key IN" in _sql(builder(scope, NOW)), builder.__name__


# ─────────────────────── resolving the scope ───────────────────────


class _ScopeSession:
    """Answers the one scope query with a fixed set of keys, and counts calls."""

    def __init__(self, keys: list[str]):
        self._keys = keys
        self.statements: list[str] = []

    async def execute(self, statement, *args, **kwargs):
        self.statements.append(_sql(statement))
        keys = self._keys

        class _R:
            def all(self):
                return [(k,) for k in keys]

        return _R()


def test_a_plain_league_resolves_without_asking_the_database():
    """The round trip is spent on tours only. For the other 27 leagues this must
    cost nothing at all — not a cheap query, none."""
    session = _ScopeSession([])
    scope = asyncio.run(league_scope_sport_keys(session, "baseball_mlb", NOW))
    assert scope == ["baseball_mlb"]
    assert session.statements == []


def test_a_tour_resolves_to_itself_plus_its_active_children():
    session = _ScopeSession(["tennis_atp_us_open", "tennis_atp_cincinnati_open"])
    scope = asyncio.run(league_scope_sport_keys(session, "tennis_atp", NOW))

    assert len(session.statements) == 1
    # Parent first, children sorted — a stable order, so the compiled statement
    # is stable and the query plan cache is not churned by set iteration order.
    assert scope == [
        "tennis_atp",
        "tennis_atp_cincinnati_open",
        "tennis_atp_us_open",
    ]


def test_the_scope_query_asks_only_for_children_carrying_recent_rows():
    """The dormant buckets are the whole cost: 18 of `tennis_atp`'s 19 children
    are idle in September and including them measured 4,195 blocks against 547.
    So the statement must carry BOTH the prefix and the existence test."""
    session = _ScopeSession([])
    asyncio.run(league_scope_sport_keys(session, "tennis_atp", NOW))
    sql = session.statements[0]

    assert "sports.key LIKE" in sql
    assert "EXISTS" in sql
    assert "events.commence_time >=" in sql


def test_the_parent_is_in_scope_even_when_it_carries_nothing():
    """A tour page can never come back emptier than it was before #3816."""
    session = _ScopeSession([])
    assert asyncio.run(league_scope_sport_keys(session, "tennis_wta", NOW)) == [
        "tennis_wta"
    ]


def test_the_parent_is_not_duplicated_when_the_query_returns_it():
    """`LIKE 'tennis\\_atp\\_%'` cannot match `tennis_atp`, but a future edit to
    the pattern could — and a duplicated key in an `IN` list is harmless SQL and
    a confusing scope, so the guard is cheap and states the intent."""
    session = _ScopeSession(["tennis_atp", "tennis_atp_us_open"])
    scope = asyncio.run(league_scope_sport_keys(session, "tennis_atp", NOW))
    assert scope == ["tennis_atp", "tennis_atp_us_open"]
    assert scope.count("tennis_atp") == 1


def test_the_scope_window_is_the_widest_rail_the_page_renders():
    """A child is in scope if it has ANY row from the results rail's lookback
    onward — behind for Finals, unbounded ahead for upcoming matches. A narrower
    floor would drop a tournament whose only rows are still to be played."""
    session = _ScopeSession([])
    asyncio.run(league_scope_sport_keys(session, "tennis_atp", NOW))
    sql = session.statements[0]

    # The floor is bound, not inlined, so assert on the shape and then on the
    # value the route would compute for it.
    assert "commence_time >=" in sql
    assert "commence_time <=" not in sql, (
        "an upper bound would hide a tournament that has not started yet"
    )


def test_the_round_trip_is_charged_to_tours_only():
    """🔴 THE PRICE, ASSERTED IN BOTH DIRECTIONS.

    `test_league_rails_query_plan.test_build_league_issues_exactly_four_statements`
    fixes the page at four statements and says the next rail has to argue for its
    own round trip. This is that argument, and it is bounded: the fifth statement
    is issued for a tour and for nothing else.

    Measured on production 2026-09-07, `EXPLAIN (ANALYZE, BUFFERS)`, blocks:

        this scope query (EXISTS form)              1,521
        the three rails, active children only    3 x 547
        ─────────────────────────────────────────────────
        total with the round trip                   3,162
        total expanding blindly, asking nothing    12,585

    So the question pays for itself four times over. The alternative that does
    NOT ask — `LIKE` straight into each rail — is the expensive one, which is
    why the exact-count guard is kept rather than loosened.
    """

    class _Recording:
        def __init__(self, scope_keys):
            self.statements: list[str] = []
            self._scope_keys = scope_keys

        async def execute(self, statement, *args, **kwargs):
            sql = _sql(statement)
            self.statements.append(sql)
            keys = self._scope_keys

            class _R:
                def all(self):
                    # Only the scope query reads rows this way; the rails go
                    # through `.scalars()`.
                    return [(k,) for k in keys]

                def scalars(self):
                    class _S:
                        def unique(self_inner):
                            return self_inner

                        def all(self_inner):
                            return []

                    return _S()

            return _R()

    plain = _Recording([])
    asyncio.run(build_league("americanfootball_cfl", plain))
    assert len(plain.statements) == 4, plain.statements
    assert not any("EXISTS" in s and "sports.key LIKE" in s for s in plain.statements)

    tour = _Recording(["tennis_atp_us_open"])
    asyncio.run(build_league("tennis_atp", tour))
    assert len(tour.statements) == 5, tour.statements
    scope_queries = [
        s for s in tour.statements if "EXISTS" in s and "sports.key LIKE" in s
    ]
    assert len(scope_queries) == 1, "exactly one scope query, issued once per build"


def test_the_lookback_floor_matches_the_results_rail():
    from app.routes.league_futures import RESULTS_LOOKBACK_DAYS

    captured: dict = {}

    class _Capturing(_ScopeSession):
        async def execute(self, statement, *args, **kwargs):
            captured["params"] = statement.compile(
                dialect=postgresql.dialect()
            ).params
            return await super().execute(statement, *args, **kwargs)

    asyncio.run(league_scope_sport_keys(_Capturing([]), "tennis_atp", NOW))
    floors = [
        v for v in captured["params"].values() if isinstance(v, datetime)
    ]
    assert floors == [NOW - timedelta(days=RESULTS_LOOKBACK_DAYS)]
