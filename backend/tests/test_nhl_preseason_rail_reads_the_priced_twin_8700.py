"""#8700 — an NHL preseason game on the NHL page carries its sportsbook price.

## What a reader saw

`/sport/hockey/nhl`, 390px, 2026-09-25 ~13:00 PT (authority/1147): every
preseason final in RECENT RESULTS printed no pre-match number, while the NFL
and MLB finals print `68% · Pre-match · sportsbooks`; tonight's cards were a
Kalshi + Polymarket blend with the sportsbook price — the heaviest source —
missing.

## Why

Every NHL preseason game is two rows (production 2026-09-25 20:3xZ, 40 pairs,
1 unpaired variant row)::

    15314368  icehockey_nhl            espn-anchored  Sharks-Ducks  opening NULL
    15318364  icehockey_nhl_preseason  odds_api       Sharks-Ducks  opening .6998

`fold_twin_events` already folds exactly this pair (#2866 league-aware key,
#7915 eight-minute kick-off drift) and unions the price onto the anchored
survivor. But the league rails were scoped `sports.key = 'icehockey_nhl'`, so
the priced half never reached the batch and the fold had nothing to fold.

## What this pins

* the NHL rails read the in-play variant key and the served card is ONE card,
  the anchored row, carrying the variant's opening line and sportsbook price;
* with the scope reverted, the same rows serve the blank card (the test bites);
* a league that did not declare a variant pays no extra round trip and
  compiles the measured `sports.key = :key` statement;
* a variant with no rows in the window widens nothing;
* the results rail gets fold headroom only when a variant is in scope.
"""

from __future__ import annotations

import asyncio
import re
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.dialects import postgresql
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import Session


@compiles(JSONB, "sqlite")
def _jsonb_on_sqlite(type_, compiler, **kw):  # pragma: no cover - DDL shim
    return "JSON"


@compiles(ARRAY, "sqlite")
def _array_on_sqlite(type_, compiler, **kw):  # pragma: no cover - DDL shim
    return "JSON"


from app.models.models import Base, Event, Sport  # noqa: E402
from app.routes import league_futures as route  # noqa: E402
from app.utils.sport_keys import (  # noqa: E402
    SEASON_VARIANT_RAIL_LEAGUES,
    SPORT_HIERARCHY,
    TOUR_LEAGUES_INCLUDING_TOURNAMENTS,
    league_identity,
    season_variant_rail_keys,
)

NHL = "icehockey_nhl"
NHL_PRE = "icehockey_nhl_preseason"
S_NHL = 4
S_NHL_PRE = 402397

#: The production pair (authority/1147's table on #8700), ids verbatim.
PARENT = 15314368  # icehockey_nhl, ESPN-anchored, the row the page served
TWIN = 15318364  # icehockey_nhl_preseason, Odds API, 132 odds snapshots
OPEN_HOME = 0.6998
OPEN_AWAY = 0.3002

#: Tonight's pair: Capitals at Bruins.
TONIGHT_PARENT = 15314743
TONIGHT_TWIN = 15318810


def _fresh(value: float) -> dict:
    # Gotcha #44: offset from the clock, never a literal stamp.
    return {"value": value, "updated_at": datetime.now(timezone.utc).isoformat()}


def _event(event_id, *, sport_id, when, home, away, **kw):
    return Event(
        id=event_id,
        sport_id=sport_id,
        home_team_name=home,
        away_team_name=away,
        commence_time=when,
        event_tags=kw.pop("tags", []),
        **kw,
    )


def _the_production_rows():
    """Both pairs as production holds them. The variant's kick-off sits eight
    minutes after the parent's, as 36 of the 40 measured pairs do."""
    now = datetime.now(timezone.utc)
    played = (now - timedelta(days=2)).replace(second=0, microsecond=0)
    tonight = (now + timedelta(hours=3)).replace(second=0, microsecond=0)
    return [
        _event(
            PARENT,
            sport_id=S_NHL,
            when=played,
            home="Anaheim Ducks",
            away="San Jose Sharks",
            status="completed",
            completed_at=played + timedelta(hours=3),
            home_score=0,
            away_score=10,
            espn_id="401879400",
        ),
        _event(
            TWIN,
            sport_id=S_NHL_PRE,
            when=played + timedelta(minutes=8, seconds=32),
            home="Anaheim Ducks",
            away="San Jose Sharks",
            status="completed",
            completed_at=played + timedelta(hours=3),
            home_score=0,
            away_score=10,
            win_probability_sources={"betting": _fresh(OPEN_HOME)},
            opening_home_probability=OPEN_HOME,
            opening_away_probability=OPEN_AWAY,
        ),
        _event(
            TONIGHT_PARENT,
            sport_id=S_NHL,
            when=tonight,
            home="Boston Bruins",
            away="Washington Capitals",
            status="scheduled",
            espn_id="401879500",
            # Production read .585/.585, where the weighted median lands on
            # the markets either way; the two venues are split here so the
            # sportsbook's vote is visible in the served number.
            win_probability_sources={
                "kalshi": _fresh(0.57),
                "polymarket": _fresh(0.60),
            },
        ),
        _event(
            TONIGHT_TWIN,
            sport_id=S_NHL_PRE,
            when=tonight,
            home="Boston Bruins",
            away="Washington Capitals",
            status="scheduled",
            win_probability_sources={"betting": _fresh(0.594)},
            opening_home_probability=0.594,
            opening_away_probability=0.406,
        ),
    ]


class _Session:
    def __init__(self, session):
        self._s = session

    async def execute(self, statement, *args, **kwargs):
        return self._s.execute(statement)


def _league_payload(rows):
    eng = create_engine("sqlite://")
    Base.metadata.create_all(eng)
    with Session(eng) as s:
        s.add(Sport(id=S_NHL, key=NHL, name="NHL"))
        s.add(Sport(id=S_NHL_PRE, key=NHL_PRE, name="NHL Preseason"))
        for r in rows:
            s.add(r)
        s.commit()
    with Session(eng) as s:
        return asyncio.run(route.build_league(NHL, _Session(s)))


def _ids(cards):
    return [c["id"] for c in cards]


# ---------------------------------------------------------------------------
# the ship, through the real route
# ---------------------------------------------------------------------------


class TestTheNhlPageCarriesThePrice:
    def test_the_final_prints_its_pre_match_number(self):
        payload = _league_payload(_the_production_rows())
        results = payload["recent_results"]
        assert _ids(results) == [PARENT], (
            "the preseason final should be ONE card, the anchored row: "
            f"{_ids(results)}"
        )
        opening = results[0].get("opening_odds")
        assert opening, f"the final still prints no pre-match number: {results[0]}"
        assert opening["home_probability"] == pytest.approx(OPEN_HOME, abs=1e-3)

    def test_tonights_card_is_one_card_with_the_sportsbook_price(self):
        payload = _league_payload(_the_production_rows())
        upcoming = payload["upcoming_games"]
        assert _ids(upcoming) == [TONIGHT_PARENT], _ids(upcoming)
        card = upcoming[0]
        # 0.585 from the two prediction markets alone; with the sportsbook
        # price in the bag the weighted median is the sportsbook's 0.594.
        assert card["home_win_probability"] == pytest.approx(0.594, abs=1e-3), card
        assert card["opening_odds"]["home_probability"] == pytest.approx(0.594, abs=1e-3)

    def test_without_the_variant_scope_the_same_rows_serve_the_blank_card(
        self, monkeypatch
    ):
        """The control: the rows are unchanged, only the scope is reverted, and
        the page is back to what authority photographed."""
        monkeypatch.setattr(route, "season_variant_rail_keys", lambda _k: [])
        payload = _league_payload(_the_production_rows())
        results = payload["recent_results"]
        assert _ids(results) == [PARENT]
        assert not results[0].get("opening_odds")
        assert payload["upcoming_games"][0]["home_win_probability"] == pytest.approx(
            0.585, abs=1e-3
        )

    def test_a_failed_variant_lookup_serves_the_parent_rails(self, monkeypatch):
        """Gotcha #42: the fold improves the rails, it never costs them. The
        lookup times out; the page still serves the parent's own cards."""
        real_execute = _Session.execute
        raised = {"n": 0}

        async def _timeout_on_lookup(self, statement, *args, **kwargs):
            sql = str(statement.compile(dialect=postgresql.dialect()))
            if sql.strip().startswith("SELECT sports.key"):
                raised["n"] += 1
                raise asyncio.TimeoutError()
            return await real_execute(self, statement, *args, **kwargs)

        monkeypatch.setattr(_Session, "execute", _timeout_on_lookup)
        payload = _league_payload(_the_production_rows())
        assert raised["n"] == 1
        assert _ids(payload["recent_results"]) == [PARENT]
        assert _ids(payload["upcoming_games"]) == [TONIGHT_PARENT]


# ---------------------------------------------------------------------------
# the pure rule
# ---------------------------------------------------------------------------


def test_the_nhl_declares_its_variant_keys():
    assert season_variant_rail_keys(NHL) == [
        "icehockey_nhl_preseason",
        "icehockey_nhl_summer_league",
    ]


def test_an_undeclared_league_reads_no_variant():
    for key in ("americanfootball_cfl", "basketball_nba", "tennis_atp", NHL_PRE):
        assert season_variant_rail_keys(key) == []


def test_every_declared_league_is_on_a_page_and_is_not_a_tour():
    declared = {
        key
        for hierarchy in SPORT_HIERARCHY.values()
        for league in hierarchy.get("leagues", [])
        for key in league.get("sport_keys", [])
    }
    assert SEASON_VARIANT_RAIL_LEAGUES <= declared
    assert not (SEASON_VARIANT_RAIL_LEAGUES & TOUR_LEAGUES_INCLUDING_TOURNAMENTS)


def test_every_variant_key_is_the_same_league_as_its_parent():
    """The fold's element 0 is `league_identity`; a variant that did not
    collapse onto its parent would be read and never folded — two cards."""
    for parent in SEASON_VARIANT_RAIL_LEAGUES:
        for variant in season_variant_rail_keys(parent):
            assert league_identity(variant) == league_identity(parent)


# ---------------------------------------------------------------------------
# the SQL: what a declared league pays, and what everyone else does not
# ---------------------------------------------------------------------------


def _sql(query, literal=False) -> str:
    kw = {"compile_kwargs": {"literal_binds": True}} if literal else {}
    return str(query.compile(dialect=postgresql.dialect(), **kw))


class _Scalars:
    def __init__(self, rows):
        self._rows = rows

    def unique(self):
        return self

    def all(self):
        return list(self._rows)


class _Result:
    def __init__(self, rows):
        self._rows = rows

    def scalars(self):
        return _Scalars(self._rows)


class _Recording:
    def __init__(self, variants_in_play):
        self.variants_in_play = variants_in_play
        self.statements: list = []

    async def execute(self, statement, *args, **kwargs):
        self.statements.append(statement)
        sql = _sql(statement)
        if sql.strip().startswith("SELECT sports.key \nFROM sports"):
            return _Result(self.variants_in_play)
        return _Result([])


def _build(sport_key, variants_in_play=()):
    session = _Recording(list(variants_in_play))
    asyncio.run(route.build_league(sport_key, session))
    return session


def _rails(session):
    """The games rails' statements — everything that scopes `events` by league,
    minus the variant lookup itself (whose own `IN` is the candidate list)."""
    return [
        s
        for s in session.statements
        if "sports.key" in _sql(s)
        and not _sql(s).strip().startswith("SELECT sports.key")
    ]


def test_the_nhl_rails_widen_to_the_variant_in_play():
    session = _build(NHL, [NHL_PRE])
    lookups = [
        s for s in session.statements if _sql(s).strip().startswith("SELECT sports.key")
    ]
    assert len(lookups) == 1
    assert "EXISTS" in _sql(lookups[0]) and "events.commence_time >" in _sql(lookups[0])
    widened = [s for s in _rails(session) if "sports.key IN" in _sql(s)]
    assert len(widened) == 3, f"expected all three rails widened, got {len(widened)}"
    for s in widened:
        literal = _sql(s, literal=True)
        assert f"'{NHL_PRE}'" in literal and f"'{NHL}'" in literal


def test_the_results_rail_gets_headroom_only_with_a_variant():
    def _results_limit(session):
        for s in session.statements:
            literal = _sql(s, literal=True)
            if "LIMIT ALL OFFSET 0" in literal and "completed" in literal:
                return int(re.findall(r"LIMIT (\d+)\s*$", literal.strip())[0])
        raise AssertionError("no results rail statement")

    assert _results_limit(_build(NHL, [NHL_PRE])) == 2 * route.RESULTS_LIMIT + 1
    assert _results_limit(_build(NHL, [])) == route.RESULTS_LIMIT + 1


def test_a_variant_out_of_season_leaves_the_measured_statement():
    session = _build(NHL, [])
    rails = _rails(session)
    assert len(rails) == 3
    assert not any("sports.key IN" in _sql(s) for s in rails)


def test_an_undeclared_league_pays_no_extra_round_trip():
    """`test_build_league_issues_exactly_four_statements` pins the CFL at four."""
    session = _build("americanfootball_cfl")
    assert len(session.statements) == 4
    assert not any("sports.key IN" in _sql(s) for s in session.statements)
