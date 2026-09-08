"""#2698 — the US Open winner market is served to nobody.

During the 2026 US Open, `/api/leagues/tennis_atp` reported

    section_counts.championship = {"total": 3, "shown": 3}

over a `sections` dict holding only `matches` and `more_markets`. Three markets
counted as shown, zero served — and one of the three was
`US Open Men's Singles Winner`, 48 contenders, leader 55.5%. The single
most-asked question of the fortnight was the one market the tour page could not
show. Same shape on `tennis_wta`, and `/hub/tennis` reads the same payload.

Two defects, and the second is only visible once the first is fixed.

**1. The championship section is skipped on a page that has no grid.** The skip
reasons that "the grid IS the rendering of this family", which is true for the
14 registered leagues that have a `/api/playoffs/{slug}` and false for the 15
that do not. `/api/playoffs/tennis_atp` is a 404. The escape hatch that exists
for exactly this case, `_CATEGORY_WIDE_FUTURES_ONLY`, is a hand-kept set holding
the single string `"esports"`, so it fires for the esports HUB and for nothing
else.

**2. `ILIKE` has no word boundary.** `LEAGUE_NAME_PATTERNS["tennis_atp"]` holds
`%US Open%Men%`, which matches `US Open Wo·men's Singles Winner` — the substring
is spelled inside the very word meant to exclude it. So the men's tour page's
futures pool already carried the WOMEN'S title market, invisibly, because the
section was dropped before rendering. Un-skipping the section without fixing
this ships a new visible bug in the same commit: the men's tour page showing the
women's US Open winner.

Every population figure quoted below was replayed against production rows on
2026-09-08 by compiling the route's own clause with literal binds and running it
through the read-only `db-query` rail — the payload, not a fixture's idea of it.

Both directions throughout (gotcha #43). A section that renders titles by also
rendering 42 per-map matchups is not a fix, and neither is one that empties the
esports hub — the live surface this rule was modelled on.
"""

from __future__ import annotations

import os
import sqlite3
import sys
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from sqlalchemy import select
from sqlalchemy.dialects import sqlite as sqlite_dialect

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.models import FuturesMarket  # noqa: E402
from app.routes import league_futures as lf  # noqa: E402

NOW = datetime(2026, 9, 8, 11, 30, tzinfo=timezone.utc)
SOON = (NOW + timedelta(days=20)).isoformat()


# ---------------------------------------------------------------------------
# Part 1 — the scope clause, as a real statement over a real table
# ---------------------------------------------------------------------------
#
# Compiled with literal binds and executed over sqlite for the same reason
# `test_hub_womens_draw_3447.py` does it: the route's mocked-db harness hands
# back its whole fixture population for any `futures_markets` statement and
# cannot evaluate a WHERE clause, so a scope test built on it would pass just as
# happily with the fix deleted.

#: The four tennis title rows on production 2026-09-08, real ids and tickers.
#: The two Kalshi rows are what the tour pages must sort out between them; the
#: Polymarket pair carry the word order that started the issue.
TITLE_ROWS = [
    (34277822, "KXATP-26USO", "US Open Men's Singles Winner", None),
    (34277839, "KXWTA-26USO", "US Open Women's Singles Winner", None),
    (114159, "139236", "2026 Men’s US Open Winner (Tennis)", None),
    (114160, "139255", "2026 Women’s US Open Winner (Tennis)", None),
    # Selected by `%ATP%` / `%WTA%`. Both are five-week-old corpses on
    # production (`resolution_date IS NULL`), which Part 3 is about; here they
    # only have to prove the tour patterns still select their own tour.
    (57718610, "775293", "ATP 1000 Montreal: Winner", None),
    (58076256, "790601", "WTA 1000 Toronto: Winner", None),
    # A `KXATP…` ticker whose NAME mentions women. The anti-patterns qualify the
    # name arm only, so the venue's own tour id must still carry it.
    (99001, "KXATPMIXED-26USO", "US Open Mixed Doubles: Women's Side", None),
]

_COLUMNS = (
    "id",
    "external_id",
    "name",
    "status",
    "resolution_date",
    "llm_sport_category",
    "llm_league",
    "market_tier",
    "event_id",
)


@pytest.fixture()
def table():
    conn = sqlite3.connect(":memory:")
    conn.execute(
        "CREATE TABLE futures_markets ("
        "id INTEGER PRIMARY KEY, external_id TEXT, name TEXT, status TEXT, "
        "resolution_date TEXT, llm_sport_category TEXT, llm_league TEXT, "
        "market_tier INTEGER, event_id INTEGER)"
    )
    conn.executemany(
        f"INSERT INTO futures_markets ({','.join(_COLUMNS)}) "
        f"VALUES ({','.join('?' * len(_COLUMNS))})",
        [
            (mid, ext, name, "open", SOON, "tennis", league, 1, None)
            for mid, ext, name, league in TITLE_ROWS
        ],
    )
    conn.commit()
    try:
        yield conn
    finally:
        conn.close()


def _selected(conn, sport_key: str, **kwargs) -> set[str]:
    """Run the REAL scope clause over the table and return what it selected."""
    statement = select(FuturesMarket.name).where(
        *lf._league_scope_filters(sport_key, NOW, **kwargs)
    )
    sql = str(
        statement.compile(
            dialect=sqlite_dialect.dialect(),
            compile_kwargs={"literal_binds": True},
        )
    )
    return {name for (name,) in conn.execute(sql).fetchall()}


class TestTheMensTourDoesNotSelectTheWomensTitle:
    def test_the_womens_us_open_winner_is_not_an_atp_market(self, table):
        """The word-boundary leak. RED before the fix: `%US Open%Men%` matches
        "US Open Wo·men's Singles Winner"."""
        selected = _selected(table, "tennis_atp")

        assert "US Open Women's Singles Winner" not in selected, (
            "the men's tour page selected the WOMEN'S title market — "
            "`%US Open%Men%` matched the 'men' inside 'women'"
        )
        assert "2026 Women’s US Open Winner (Tennis)" not in selected

    def test_the_mens_title_and_the_tour_are_still_selected(self, table):
        """Over-refusal is the other half of the guard: an exclusion that also
        removes the market the ship is FOR would pass the test above."""
        selected = _selected(table, "tennis_atp")

        assert "US Open Men's Singles Winner" in selected
        assert "ATP 1000 Montreal: Winner" in selected

    def test_an_atp_tickered_market_may_still_mention_women(self, table):
        """NAME ARM ONLY. `KXATP…` is the venue's own tour statement and beats
        a string test (gotcha #32's shape); only the guess is qualified."""
        assert "US Open Mixed Doubles: Women's Side" in _selected(table, "tennis_atp")

    def test_the_womens_tour_selects_its_own_title(self, table):
        selected = _selected(table, "tennis_wta")

        assert "US Open Women's Singles Winner" in selected
        assert "WTA 1000 Toronto: Winner" in selected

    def test_the_two_tour_hub_still_gets_both_draws(self, table):
        """#3447 must survive. The exclusion is scoped PER KEY inside the OR, so
        a hub asking for both tours gets the women's draw back through the
        sibling's branch — a global "not women's" would empty the rail #3447
        built."""
        selected = _selected(table, "tennis_atp", also_sport_keys=("tennis_wta",))

        assert "US Open Men's Singles Winner" in selected
        assert "US Open Women's Singles Winner" in selected


def test_leagues_without_anti_patterns_keep_their_exact_clause(table):
    """27 of the 29 declared leagues add nothing here, and their compiled SQL is
    byte-identical to before the fix — the same promise `_rail_league_scope`
    makes, for the same reason: a statement that changes shape has to be
    re-measured."""

    def _clause(sport_key: str) -> str:
        statement = select(FuturesMarket.name).where(
            *lf._league_scope_filters(sport_key, NOW)
        )
        return str(
            statement.compile(
                dialect=sqlite_dialect.dialect(),
                compile_kwargs={"literal_binds": True},
            )
        )

    before = _clause("baseball_mlb")
    assert "baseball_mlb" not in lf.LEAGUE_NAME_ANTI_PATTERNS

    # The same league re-compiled while the table DOES declare one, so the test
    # proves the branch is reachable rather than that the string happens to be
    # absent (a positive control can pass for the wrong reason).
    lf.LEAGUE_NAME_ANTI_PATTERNS["baseball_mlb"] = ["%Minor%"]
    try:
        after = _clause("baseball_mlb")
    finally:
        del lf.LEAGUE_NAME_ANTI_PATTERNS["baseball_mlb"]

    assert after != before, "the anti-pattern table did not reach the clause at all"
    assert "'%minor%'" in after.lower()
    assert "minor" not in before.lower(), (
        "an anti-pattern clause reached a league that declares none"
    )


# ---------------------------------------------------------------------------
# Part 2 — the section rule, through the real route
# ---------------------------------------------------------------------------


def _outcome(oid: int, name: str, prob: float, rank: int = 1):
    return SimpleNamespace(
        id=oid,
        name=name,
        current_probability=prob,
        opening_probability=None,
        probability_change_24h=0,
        rank=rank,
        team_id=None,
        is_winner=False,
        resolution_source=None,
    )


#: `resolution_date=None` is a VALUE this file tests, not "unset". The first
#: draft defaulted the parameter to `None` and coalesced it to a date, so the two
#: tests about an undated corpse silently built a dated market and one of them
#: passed for the wrong reason.
_UNSET = object()


def _market(
    *,
    market_id: int,
    name: str,
    category: str = "championship",
    market_tier: int = 1,
    sport_category: str = "tennis",
    resolution_date=_UNSET,
    n_outcomes: int = 4,
):
    """A title-family market row.

    Mid-band probabilities on purpose: `build_league` skips leaders >=97% and
    all-settled ladders, and a specimen that vanished down THOSE paths would
    prove nothing about this one.
    """
    return SimpleNamespace(
        id=market_id,
        name=name,
        source="kalshi",
        external_id=f"EXT-{market_id}",
        category=category,
        llm_sport_category=sport_category,
        llm_league=None,
        market_tier=market_tier,
        status="open",
        event_id=None,
        outcomes=[
            _outcome(market_id * 100 + i, f"Contender {i}", 0.55 - 0.05 * i, rank=i + 1)
            for i in range(n_outcomes)
        ],
        resolution_date=(
            NOW + timedelta(days=20) if resolution_date is _UNSET else resolution_date
        ),
        canonical_market_key="tennis::championship:2026",
        group_id=None,
    )


def _scalars_result(items):
    result = MagicMock()
    scalars = MagicMock()
    scalars.all.return_value = items
    scalars.unique.return_value = scalars
    result.scalars.return_value = scalars
    return result


def _serve_pool(mock_db, items):
    """Answer the futures-pool query with `items`, everything after it empty."""
    pool, empty = _scalars_result(list(items)), _scalars_result([])
    calls = {"n": 0}

    def _execute(*_args, **_kwargs):
        calls["n"] += 1
        return pool if calls["n"] == 1 else empty

    mock_db.execute.side_effect = _execute


def _section_of(body: dict, name: str) -> str | None:
    for section, rows in body.get("sections", {}).items():
        for row in rows:
            if row["name"] == name:
                return section
    return None


#: The row the whole issue is about, as production holds it.
US_OPEN_MENS = _market(
    market_id=34277822, name="US Open Men's Singles Winner", n_outcomes=8
)


class TestTheTitleReachesAGridLessPage:
    async def test_the_us_open_winner_is_served(self, client, mock_db):
        """The ship. RED before the fix — the row went to `championship_census`
        and `sections` never held it."""
        _serve_pool(mock_db, [US_OPEN_MENS])

        body = (await client.get("/api/leagues/tennis_atp")).json()

        assert _section_of(body, "US Open Men's Singles Winner") == "futures", (
            f"the title market was not served; sections="
            f"{ {k: len(v) for k, v in body.get('sections', {}).items()} }"
        )

    async def test_the_envelope_stops_claiming_it_was_shown(self, client, mock_db):
        """`section_counts.championship = {total: 3, shown: 3}` over an empty
        section is the lie the census told for a year (ruling 025 clause 3). A
        row that renders is counted where it renders."""
        _serve_pool(mock_db, [US_OPEN_MENS])

        body = (await client.get("/api/leagues/tennis_atp")).json()
        counts = body.get("section_counts", {})

        assert counts.get("futures", {}).get("shown") == 1
        assert counts.get("championship", {}).get("shown", 0) == 0

    async def test_a_league_with_a_grid_still_censuses_its_champion(
        self, client, mock_db
    ):
        """THE CONTROL, and the reason the rule asks the grid's own registry.
        `/api/playoffs/mlb` exists and renders this family, so MLB must be
        untouched: counted, not rendered, exactly as before."""
        _serve_pool(
            mock_db,
            [
                _market(
                    market_id=5001,
                    name="World Series Winner",
                    sport_category="baseball",
                )
            ],
        )

        body = (await client.get("/api/leagues/baseball_mlb")).json()

        assert _section_of(body, "World Series Winner") is None, (
            "a league WITH a championship grid started double-rendering its "
            "title markets as cards"
        )
        assert body.get("section_counts", {}).get("championship", {}).get("total") == 1


class TestWhatTheSectionRefuses:
    """Tier 1 is not a synonym for outright. Measured on production 2026-09-08,
    un-filtering this section would have put 42 of `esports_cs2`'s 44 tier-1
    rows and 12 of `esports_lol`'s 13 under a heading promising tournament
    winners."""

    @pytest.mark.parametrize(
        "name",
        [
            "Counter-Strike: Azuolas vs G2 Ares - Map 1 Winner",
            "LoL: GIANTX vs Natus Vincere - Game 4 Winner",
            "Set 1 Winner: Shelton vs Alcaraz",
            # Stored `category='championship'` AND a matchup — the specimen that
            # proves a category allowlist alone would let one through.
            "LoL: G2 NORD vs BIG (BO5) - Prime League 1st Division Playoffs",
        ],
    )
    def test_matchups_and_within_match_scopes_are_not_outrights(self, name):
        assert lf._is_outright(_market(market_id=1, name=name)) is False

    @pytest.mark.parametrize(
        "name,category",
        [
            ("US Open Men's Singles Winner", "championship"),
            ("WBC Heavyweight Title on January 1, 2027", "championship"),
            ("NASCAR Cup Series Champion", "championship"),
            # `category` IS NOT THE TEST. The esports hub serves 51 rows today
            # that are not `championship`, including these two shapes; a
            # category allowlist would have deleted every one of them.
            ("Will FaZe Clan make playoffs?", "game_prop"),
            ("Which Club will win the EWC Club Championship?", "other"),
        ],
    )
    def test_real_outrights_are_admitted(self, name, category):
        assert (
            lf._is_outright(_market(market_id=1, name=name, category=category)) is True
        )

    async def test_a_matchup_never_reaches_the_section(self, client, mock_db):
        """The predicate proved through the route, not just in isolation — the
        wiring is the half that was broken."""
        matchup = _market(
            market_id=7001,
            name="Set 1 Winner: Shelton vs Alcaraz",
            category="game_prop",
        )
        _serve_pool(mock_db, [US_OPEN_MENS, matchup])

        body = (await client.get("/api/leagues/tennis_atp")).json()

        assert _section_of(body, "US Open Men's Singles Winner") == "futures"
        assert _section_of(body, "Set 1 Winner: Shelton vs Alcaraz") is None


# ---------------------------------------------------------------------------
# Part 3 — the corpse
# ---------------------------------------------------------------------------


class TestADeadTournamentDoesNotOutsortTheLiveOne:
    """The section sorts by outcome count, so on 2026-09-08 the ATP page's new
    section would have led with `ATP 1000 Montreal: Winner` — 69 outcomes,
    `resolution_date IS NULL`, untouched since 2026-07-31, for a tournament that
    ended in August — and put the US Open second. The missing date is the test,
    not the age: 78 of the esports hub's 80 rows are >7 days untouched on a
    surface that serves them correctly today."""

    async def test_a_winner_market_with_no_resolution_date_is_not_served(
        self, client, mock_db
    ):
        montreal = _market(
            market_id=57718610,
            name="ATP 1000 Montreal: Winner",
            resolution_date=None,
            # Richer than the US Open row, which is exactly how it would have
            # taken the top slot.
            n_outcomes=12,
        )
        _serve_pool(mock_db, [US_OPEN_MENS, montreal])

        body = (await client.get("/api/leagues/tennis_atp")).json()
        served = [row["name"] for row in body.get("sections", {}).get("futures", [])]

        assert served == ["US Open Men's Singles Winner"], (
            f"a dead tournament reached the top of the new section: {served}"
        )

    def test_the_category_wide_hub_keeps_its_undated_rows(self):
        """The esports hub is the live surface this rule was modelled on, and 75
        of its 80 rows carry no resolution date. Its branch is untouched, so the
        rule that protects the tour pages cannot empty it."""
        undated = _market(
            market_id=8001,
            name="EWC 2026: Street Fighter Winner",
            sport_category="esports",
            resolution_date=None,
        )

        assert lf._league_futures_admits(undated) is False, (
            "the league-page admission test changed meaning"
        )
        assert "esports" in lf._CATEGORY_WIDE_FUTURES_ONLY, (
            "the esports hub lost the branch that serves it — its 80 rows are "
            "admitted by `_CATEGORY_WIDE_FUTURES_ONLY`, never by "
            "`_league_futures_admits`"
        )


# ---------------------------------------------------------------------------
# Part 4 — the registry, not a hand-kept set
# ---------------------------------------------------------------------------


def test_the_grid_question_is_asked_of_the_grids_own_registry():
    """`_CATEGORY_WIDE_FUTURES_ONLY` held one string for one hub while fourteen
    other grid-less leagues went unnoticed. Pinning the two lists here means the
    sixteenth registered league is answered for without anyone remembering to
    add it."""
    assert lf._league_has_championship_grid("baseball_mlb") is True
    assert lf._league_has_championship_grid("soccer_epl") is True
    assert lf._league_has_championship_grid("golf_pga") is True

    for gridless in (
        "tennis_atp",
        "tennis_wta",
        "boxing_boxing",
        "mma_mixed_martial_arts",
        "motorsport_f1",
        "motorsport_nascar",
        "esports_cs2",
    ):
        assert lf._league_has_championship_grid(gridless) is False, (
            f"{gridless} claims a championship grid; /api/playoffs/ 404s for it"
        )
