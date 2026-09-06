"""UX-P182 (#3447): the tennis hub is a SPORT, not the men's tour.

`/hub/tennis` is the site's only tennis surface and it was declared
`sport_key="tennis_atp"`. `build_linked_matches` scopes on one league key, so the
rail's league clause resolved to `KXATP%` + `%ATP%`/`%US Open%Men%`/… and the
women's draw could not enter it. Measured on production 2026-09-06, US Open
finals weekend: 126 match cards, 80 of them men's Challenger matches, zero
`KXWTA*` rows — while the page's own starred MARQUEE card, two screens above,
was "2026 Women's US Open Winner". Sabalenka, Swiatek, Gauff and Osaka rendered
nowhere on the site's tennis hub.

Why the scope filter is proved as REAL STATEMENTS against sqlite rather than
through the hub's fake db: `test_route_hub.py`'s `_sql_dispatching_db` hands back
its whole fixture population for any `futures_markets` statement, because it
dispatches on the SQL text and cannot evaluate a WHERE clause. That is right for
what it tests (composition), and useless for this one — a rail test built on it
would pass just as happily with `also_sport_keys` deleted, since the fake never
applied the league clause that is the entire subject here. So the clause is
compiled with literal binds and executed over a real table.

Both directions throughout: a widened scope that also admits basketball, or a
closed market, or a market whose question already resolved, is not a fix.
"""

import os
import sqlite3
import sys
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select
from sqlalchemy.dialects import sqlite as sqlite_dialect

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.models import FuturesMarket  # noqa: E402
from app.routes.hub import HUB_CONFIGS  # noqa: E402
from app.routes.league_futures import (  # noqa: E402
    LINKED_MATCH_POOL_LIMIT,
    _league_scope_filters,
    _sport_category_for,
)

NOW = datetime(2026, 9, 6, 6, 30, tzinfo=timezone.utc)
SOON = (NOW + timedelta(days=7)).isoformat()
PAST = (NOW - timedelta(days=7)).isoformat()

#: The eight open WTA US Open matches read from Kalshi's own API on 2026-09-06
#: (notice 26: venue-side series discovery, `series_ticker=KXWTAMATCH`). Every
#: one of them carries `llm_league IS NULL`, which is why the `llm_league ILIKE
#: 'wta'` arm of the league clause cannot rescue them and the ticker prefix must.
WTA_TICKERS = [
    ("KXWTAMATCH-26SEP06SABTOW", "Sabalenka vs Townsend"),
    ("KXWTAMATCH-26SEP06SWIZHE", "Swiatek vs Zheng"),
    ("KXWTAMATCH-26SEP06PEGCIR", "Pegula vs Cirstea"),
    ("KXWTAMATCH-26SEP06ANDPOT", "Andreeva vs Potapova"),
    ("KXWTAMATCH-26SEP06KALNAV", "Kalinskaya vs Navarro"),
    ("KXWTAMATCH-26SEP06KOSNOS", "Kostyuk vs Noskova"),
    ("KXWTAMATCH-26SEP07JOVGAU", "Jovic vs Gauff"),
    ("KXWTAMATCH-26SEP07OSARYB", "Osaka vs Rybakina"),
]

#: What the rail already carried and must keep carrying. The Challenger row is
#: the one Alex saw 80 of; it is a legitimate ATP-scope row and this ship does
#: not remove it.
ATP_ROWS = [
    ("KXATPMATCH-26SEP06PAUALC", "Paul vs Alcaraz", "atp"),
    ("KXATPMATCH-26SEP06MEDTIA", "Medvedev vs Tiafoe", "atp"),
    ("KXATPCHALLENGERMATCH-26SEP06KUMBOR", "Kumasaka vs Borisiouk", "atp"),
    ("KXATPDOUBLES-26SEP06KRAPUE", "Krawietz / Puetz vs Rojer / Winegar", "atp"),
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


def _row(
    market_id,
    external_id,
    name,
    *,
    status="open",
    resolution_date=SOON,
    category="tennis",
    league=None,
    tier=5,
    event_id=None,
):
    return (
        market_id,
        external_id,
        name,
        status,
        resolution_date,
        category,
        league,
        tier,
        event_id if event_id is not None else 900 + market_id,
    )


def _population():
    """One table holding every row the clause must decide about."""
    rows = []
    next_id = 1
    for ticker, name in WTA_TICKERS:
        rows.append(_row(next_id, ticker, name))
        next_id += 1
    for ticker, name, league in ATP_ROWS:
        rows.append(_row(next_id, ticker, name, league=league))
        next_id += 1

    # ── The rows a widened scope must STILL refuse ──
    rows.append(
        # Wrong sport entirely. `llm_sport_category` is an equality above the
        # league OR, so this is the guard that the fix widened the league clause
        # and not the category.
        _row(next_id, "KXNBA-26SEP06BOSLAL", "Celtics vs Lakers", category="basketball")
    )
    next_id += 1
    rows.append(
        # Settled at the venue. A hub rail that starts printing yesterday's
        # matches has swapped one defect for another.
        _row(next_id, "KXWTAMATCH-26SEP01OLDWIN", "Yesterday vs Gone", status="closed")
    )
    next_id += 1
    rows.append(
        # Question already past its resolution date.
        _row(next_id, "KXWTAMATCH-26AUG30EXPIRE", "Expired vs Stale", resolution_date=PAST)
    )
    next_id += 1
    rows.append(
        # A market ABOUT a game at another venue — the `% at %` exclusion, which
        # the widened clause must not reach around.
        _row(next_id, "KXWTAMATCH-26SEP06ATROW", "Swiatek at Flushing Meadows")
    )
    return rows


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
        _population(),
    )
    conn.commit()
    try:
        yield conn
    finally:
        conn.close()


def _select_names(conn, **kwargs):
    """Run the REAL scope clause over the table and return what it selected."""
    statement = select(FuturesMarket.name).where(
        *_league_scope_filters("tennis_atp", NOW, **kwargs)
    )
    sql = str(
        statement.compile(
            dialect=sqlite_dialect.dialect(),
            compile_kwargs={"literal_binds": True},
        )
    )
    return {name for (name,) in conn.execute(sql).fetchall()}


class TestTheWomensDrawReachesTheTennisHub:
    def test_without_the_extra_scope_the_womens_draw_cannot_enter(self, table):
        """The defect, reproduced. This is the CONTROL: it passes before and
        after the fix, and it is what makes the next test's pass mean something.

        A single-league scope is still correct for `/api/leagues/tennis_atp` —
        that page IS the men's tour — so this behaviour is preserved, not fixed.
        """
        selected = _select_names(table)

        assert selected & {name for _, name in WTA_TICKERS} == set(), (
            "the tennis_atp scope admitted a WTA row on its own — then the hub "
            "defect had some other cause and this whole ship is aimed wrong"
        )
        assert "Paul vs Alcaraz" in selected

    def test_the_extra_scope_admits_all_eight_womens_matches(self, table):
        """The ship. Delete `also_sport_keys` from `_league_scope_filters` and
        this is the test that goes red."""
        selected = _select_names(table, also_sport_keys=("tennis_wta",))

        missing = {name for _, name in WTA_TICKERS} - selected
        assert not missing, (
            f"the women's draw is still missing from the hub scope: {sorted(missing)}"
        )

    def test_the_mens_draw_is_not_traded_away_for_the_womens(self, table):
        """Widening must be ADDITIVE. A scope swap that showed the WTA and lost
        the Challenger rail would read as a fix in a WTA-only assertion."""
        narrow = _select_names(table)
        wide = _select_names(table, also_sport_keys=("tennis_wta",))

        assert narrow <= wide, f"widening the scope LOST rows: {sorted(narrow - wide)}"
        assert "Kumasaka vs Borisiouk" in wide
        assert "Krawietz / Puetz vs Rojer / Winegar" in wide

    def test_the_widened_scope_still_refuses_what_it_always_refused(self, table):
        """Every non-league predicate still applies to the rows the extra key
        adds — otherwise this widened one clause and quietly dropped four."""
        wide = _select_names(table, also_sport_keys=("tennis_wta",))

        assert "Celtics vs Lakers" not in wide, "the sport category stopped scoping"
        assert "Yesterday vs Gone" not in wide, "a closed market entered the rail"
        assert "Expired vs Stale" not in wide, "a resolved question entered the rail"
        assert "Swiatek at Flushing Meadows" not in wide, "the '% at %' guard was bypassed"

    def test_no_extra_keys_renders_byte_identical_sql(self):
        """A caller that passes nothing must be affected in no way at all —
        `build_league` and every other league page go through this helper."""
        def rendered(**kwargs):
            statement = select(FuturesMarket.id).where(
                *_league_scope_filters("basketball_nba", NOW, **kwargs)
            )
            return str(statement.compile(compile_kwargs={"literal_binds": True}))

        assert rendered() == rendered(also_sport_keys=())


class TestAMismatchedExtraKeyIsLoud:
    def test_a_different_sport_raises_instead_of_emptying_the_rail(self):
        """`llm_sport_category` is a single-valued equality. Pairing tennis with
        basketball would widen the league OR while the category AND still
        rejected every row it added: a filter that reads wider and returns
        nothing, which is the worst kind of quiet.
        """
        with pytest.raises(ValueError, match="sport category"):
            _league_scope_filters(
                "tennis_atp", NOW, also_sport_keys=("basketball_nba",)
            )

    def test_every_hub_config_pairs_keys_that_can_coexist(self):
        """Fails at test time, not at request time, for any future hub."""
        for slug, cfg in HUB_CONFIGS.items():
            primary = _sport_category_for(cfg.sport_key)
            for extra in cfg.extra_match_sport_keys:
                assert _sport_category_for(extra) == primary, (
                    f"hub {slug!r} pairs {cfg.sport_key!r} with {extra!r}, whose "
                    f"sport categories differ — the rail would silently empty"
                )


class TestTheTennisHubDeclaresTheWomensTour:
    def test_the_config_carries_it(self):
        assert HUB_CONFIGS["tennis"].extra_match_sport_keys == ("tennis_wta",)

    def test_no_other_hub_gained_a_scope_by_accident(self):
        widened = {
            slug for slug, cfg in HUB_CONFIGS.items() if cfg.extra_match_sport_keys
        }
        assert widened == {"tennis"}

    async def test_build_hub_hands_the_extra_keys_to_the_rail(self, monkeypatch):
        """The wiring. The sqlite tests prove the clause; only this proves the
        clause is reached with the config's keys — a `HubConfig` field nobody
        passes on is a field that fixes nothing.
        """
        import app.routes.hub as hub_module

        seen = {}

        # `is_prop` accepted because #3640 made the hub pass its own prop
        # predicate here; this test is about the league scopes and ignores it.
        async def _spy(sport_key, db, *, now=None, also_sport_keys=(), **kwargs):
            seen["sport_key"] = sport_key
            seen["also"] = tuple(also_sport_keys)
            return []

        monkeypatch.setattr(hub_module, "build_linked_matches", _spy)

        async def _empty_league(**kwargs):
            return {"sections": {}}

        monkeypatch.setattr(hub_module, "get_league_futures", _empty_league)

        await hub_module.build_hub(HUB_CONFIGS["tennis"], db=None)

        assert seen["sport_key"] == "tennis_atp"
        assert seen["also"] == ("tennis_wta",), (
            "build_hub dropped the hub's extra league scopes on the floor"
        )


class TestThePoolCapCannotSilentlyEatATour:
    def test_the_cap_has_headroom_over_the_widened_population(self):
        """Sized against the real widened scope, not the old per-league one:
        measured on production 2026-09-06 the tennis pool was 686 ATP-side rows
        + 418 WTA-side = 1,104, against the old cap of 1,500 (74% of it).

        The pool query carries no ORDER BY, so the rows past the cap are
        whichever ones Postgres reached last — a shared cap over two unequal
        populations caps the smaller out, and the smaller one is the women's
        draw. This asserts the number was actually raised; the truncation
        WARNING below is what covers the day this bound is wrong too.
        """
        assert LINKED_MATCH_POOL_LIMIT >= 2 * 1104, (
            "the linked-match pool cap no longer clears the measured tennis "
            "population with room for a season's growth"
        )

    async def test_an_overflowing_pool_says_so(self, caplog):
        """A cap chosen from today's maximum is refuted by next season's. The
        one thing that must not happen quietly is the overflow itself."""
        import logging
        from unittest.mock import AsyncMock, MagicMock

        from app.routes.league_futures import build_linked_matches

        overflow = []
        for i in range(LINKED_MATCH_POOL_LIMIT + 1):
            market = MagicMock()
            market.event_id = None  # nothing survives to the rail; only the cap matters
            market.name = f"Row {i}"
            overflow.append(market)

        scalars = MagicMock()
        scalars.unique.return_value = scalars
        scalars.all.return_value = overflow
        result = MagicMock()
        result.scalars.return_value = scalars

        db = AsyncMock()
        db.execute = AsyncMock(return_value=result)

        with caplog.at_level(logging.WARNING):
            rows = await build_linked_matches(
                "tennis_atp", db, now=NOW, also_sport_keys=("tennis_wta",)
            )

        assert rows == []
        assert any("pool truncated" in r.message for r in caplog.records), (
            "the pool overflowed its cap and the logs said nothing — the next "
            "time a tour vanishes from a hub there will be no way to see why"
        )

    async def test_a_pool_inside_the_cap_is_silent(self, caplog):
        """Both directions: a warning that fires on the normal path is noise,
        and noise is how the real one gets missed."""
        import logging
        from unittest.mock import AsyncMock, MagicMock

        from app.routes.league_futures import build_linked_matches

        scalars = MagicMock()
        scalars.unique.return_value = scalars
        scalars.all.return_value = []
        result = MagicMock()
        result.scalars.return_value = scalars

        db = AsyncMock()
        db.execute = AsyncMock(return_value=result)

        with caplog.at_level(logging.WARNING):
            await build_linked_matches("tennis_atp", db, now=NOW)

        assert not [r for r in caplog.records if "pool truncated" in r.message]
