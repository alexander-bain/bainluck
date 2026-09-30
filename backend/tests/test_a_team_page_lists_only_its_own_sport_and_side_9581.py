"""A team page lists only its own sport's and its own side's games (#9581).

## What a reader saw (production, 390px, 2026-09-29 ~08:55Z)

* `/sport/basketball/wncaab/team/alabama-crimson-tide` (WNCAAB, 24-11) listed
  eight college FOOTBALL games as its own: "vs South Carolina Gamecocks W 49–18".
* The Arsenal Women page listed eight men's fixtures (Leeds, Lille, Napoli…).
* The men's Arsenal page listed the women's UWCL matches: "vs HB Køge W 1–0"
  (15316358) and "@ Paris FC 86%" (15319991).

## Why

`get_team`'s name arm was league-guarded for UNBOUND rows only (#5491). A row
bound to any team passed on the name alone, in any sport and either gender.
The bound half of that arm exists for a sibling competition. Arsenal's page row
sits under `soccer_england_efl_cup`, and its EPL match is bound to the EPL
"Arsenal" row. The fix keeps that case and removes the cross-sport and
cross-gender rows.

## Shape

The #5491 harness: real `get_team` against a real SQLite engine, because the
predicate under test is SQL. Clock-relative offsets (gotcha #44).
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import Session


@compiles(JSONB, "sqlite")
def _jsonb_on_sqlite(type_, compiler, **kw):  # pragma: no cover - DDL shim
    return "JSON"


@compiles(ARRAY, "sqlite")
def _array_on_sqlite(type_, compiler, **kw):  # pragma: no cover - DDL shim
    return "JSON"


from app.models.models import Base, Event, Sport, Team  # noqa: E402
from app.routes import teams as route  # noqa: E402
from app.utils.sport_keys import (  # noqa: E402
    competition_gender,
    same_sport_same_gender,
)

S_EFL_CUP, S_EPL, S_UWCL_W, S_SOCCER_OTHER = 1, 2, 3, 4
S_WNCAAB, S_NCAAB, S_NCAAF = 5, 6, 7

SPORTS = [
    (S_EFL_CUP, "soccer_england_efl_cup"),
    (S_EPL, "soccer_epl"),
    (S_UWCL_W, "soccer_uefa_champs_league_women"),
    (S_SOCCER_OTHER, "soccer_other"),
    (S_WNCAAB, "basketball_wncaab"),
    (S_NCAAB, "basketball_ncaab"),
    (S_NCAAF, "americanfootball_ncaaf"),
]

#: Production team rows (`db-query`, 2026-09-29).
ARSENAL_PAGE_ROW = 1826  # soccer_england_efl_cup, slug `arsenal`
ARSENAL_EPL_ROW = 1827  # the EPL row the league match is bound to
ARSENAL_WOMEN = 11857  # soccer_uefa_champs_league_women, slug `arsenal-women`
HB_KOGE = 19040
LEEDS = 1900
BAMA_WNCAAB = 79  # slug `alabama-crimson-tide`
BAMA_NCAAB = 672
BAMA_NCAAF = 15262
GAMECOCKS_NCAAF = 15263
AUBURN_WNCAAB = 80

WOMENS_UWCL_GAME = 15316358  # Arsenal v HB Køge
EPL_GAME = 15311082  # Arsenal v Leeds United
FOOTBALL_GAME = 15313794  # Alabama v South Carolina (NCAAF)
WNCAAB_GAME = 15500001
NCAAB_GAME = 15500002
CATCH_ALL_GAME = 15500003


def _soon(hours):
    return datetime.now(timezone.utc) + timedelta(hours=hours)


def _event(event_id, sport_id, home, away, home_id, away_id, hours=24):
    return Event(
        id=event_id,
        sport_id=sport_id,
        home_team_id=home_id,
        away_team_id=away_id,
        home_team_name=home,
        away_team_name=away,
        commence_time=_soon(hours),
        status="scheduled",
    )


def _engine(*events):
    eng = create_engine("sqlite://")
    Base.metadata.create_all(eng)
    with Session(eng) as s:
        for sport_id, key in SPORTS:
            s.add(Sport(id=sport_id, key=key, name=key))
        for tid, sid, name, slug in [
            (ARSENAL_PAGE_ROW, S_EFL_CUP, "Arsenal", "arsenal"),
            (ARSENAL_EPL_ROW, S_EPL, "Arsenal", "arsenal-epl"),
            (ARSENAL_WOMEN, S_UWCL_W, "Arsenal", "arsenal-women"),
            (HB_KOGE, S_UWCL_W, "HB Køge", "hb-koge"),
            (LEEDS, S_EPL, "Leeds United", "leeds-united"),
            (BAMA_WNCAAB, S_WNCAAB, "Alabama Crimson Tide", "alabama-crimson-tide"),
            (BAMA_NCAAB, S_NCAAB, "Alabama Crimson Tide", "alabama-crimson-tide-ncaab"),
            (BAMA_NCAAF, S_NCAAF, "Alabama Crimson Tide", "alabama-crimson-tide-ncaaf"),
            (GAMECOCKS_NCAAF, S_NCAAF, "South Carolina Gamecocks", "sc-ncaaf"),
            (AUBURN_WNCAAB, S_WNCAAB, "Auburn Tigers", "auburn-tigers"),
        ]:
            s.add(Team(id=tid, sport_id=sid, name=name, slug=slug))
        for e in events:
            s.add(e)
        s.commit()
    return eng


def _page(eng, slug):
    with Session(eng) as s:

        class _Session:
            async def execute(self, statement):
                return s.execute(statement)

        return asyncio.run(route.get_team(slug, db=_Session()))


def _ids(page):
    return [c["id"] for c in page["upcoming_events"] + page["recent_events"]]


def _arsenal_rows():
    return (
        _event(WOMENS_UWCL_GAME, S_UWCL_W, "Arsenal", "HB Køge", ARSENAL_WOMEN, HB_KOGE, 12),
        _event(EPL_GAME, S_EPL, "Arsenal", "Leeds United", ARSENAL_EPL_ROW, LEEDS, 36),
    )


def _alabama_rows():
    return (
        _event(FOOTBALL_GAME, S_NCAAF, "Alabama Crimson Tide", "South Carolina Gamecocks",
               BAMA_NCAAF, GAMECOCKS_NCAAF, 12),
        _event(WNCAAB_GAME, S_WNCAAB, "Alabama Crimson Tide", "Auburn Tigers",
               BAMA_WNCAAB, AUBURN_WNCAAB, 36),
        # Bound to the MEN's basketball row: same sport, other side.
        _event(NCAAB_GAME, S_NCAAB, "Alabama Crimson Tide", "Auburn Tigers",
               BAMA_NCAAB, None, 48),
    )


class TestTheShip:
    def test_the_mens_club_page_drops_the_womens_match(self):
        """🔴 THE SHIP. "vs HB Køge W 1–0" leaves the EPL club's page."""
        ids = _ids(_page(_engine(*_arsenal_rows()), "arsenal"))
        assert WOMENS_UWCL_GAME not in ids, ids

    def test_the_womens_page_drops_the_mens_fixture(self):
        ids = _ids(_page(_engine(*_arsenal_rows()), "arsenal-women"))
        assert EPL_GAME not in ids, ids

    def test_the_womens_basketball_page_drops_the_football_schedule(self):
        """🔴 `/team/alabama-crimson-tide` listed Alabama's football games."""
        ids = _ids(_page(_engine(*_alabama_rows()), "alabama-crimson-tide"))
        assert FOOTBALL_GAME not in ids, ids
        assert NCAAB_GAME not in ids, ids


class TestWhatMustSurvive:
    def test_the_efl_cup_club_keeps_its_epl_match(self):
        """🔴 THE CONTROL. The EPL match is bound to a DIFFERENT "Arsenal" row
        (the EPL one), so it reaches the EFL-Cup page row only through the name
        arm. Same sport and same side: it must stay. A fix that dropped the name
        arm for bound rows would fail here and pass every ship assertion."""
        ids = _ids(_page(_engine(*_arsenal_rows()), "arsenal"))
        assert EPL_GAME in ids, ids

    def test_each_side_keeps_its_own_game(self):
        ids = _ids(_page(_engine(*_arsenal_rows()), "arsenal-women"))
        assert WOMENS_UWCL_GAME in ids, ids
        ids = _ids(_page(_engine(*_alabama_rows()), "alabama-crimson-tide"))
        assert WNCAAB_GAME in ids, ids

    def test_the_football_page_keeps_football_only(self):
        ids = _ids(_page(_engine(*_alabama_rows()), "alabama-crimson-tide-ncaaf"))
        assert FOOTBALL_GAME in ids, ids
        assert WNCAAB_GAME not in ids and NCAAB_GAME not in ids, ids

    def test_a_bound_catch_all_row_is_not_cut_on_gender(self):
        """`soccer_other` holds both sides, so the gate cannot read a gender off
        it and must not exclude on one (it only ever removes rows)."""
        other = _event(CATCH_ALL_GAME, S_SOCCER_OTHER, "Arsenal", "Leeds United",
                       ARSENAL_EPL_ROW, LEEDS, 60)
        ids = _ids(_page(_engine(other), "arsenal"))
        assert CATCH_ALL_GAME in ids, ids


@pytest.mark.parametrize(
    "key,gender",
    [
        ("soccer_uefa_champs_league_women", "women"),
        ("soccer_germany_bundesliga_women", "women"),
        ("cricket_t20_world_cup_womens", "women"),
        ("basketball_wnba", "women"),
        ("basketball_wncaab", "women"),
        ("aussierules_aflw", "women"),
        ("rugbyleague_nrlw", "women"),
        ("tennis_wta", "women"),
        ("tennis_wta_us_open", "women"),
        ("soccer_epl", "men"),
        ("basketball_ncaab", "men"),
        ("aussierules_afl", "men"),
        ("tennis_atp_us_open", "men"),
        ("soccer_other", None),
        (None, None),
    ],
)
def test_competition_gender(key, gender):
    assert competition_gender(key) == gender


@pytest.mark.parametrize(
    "team_key,event_key,admitted",
    [
        ("soccer_england_efl_cup", "soccer_epl", True),
        ("soccer_england_efl_cup", "soccer_uefa_champs_league_women", False),
        ("soccer_uefa_champs_league_women", "soccer_epl", False),
        ("basketball_wncaab", "americanfootball_ncaaf", False),
        ("basketball_wncaab", "basketball_ncaab", False),
        ("aussierules_aflw", "aussierules_afl", False),
        ("soccer_epl", "soccer_other", True),
        ("rugbyleague_nrl", "rugby_other", True),
        ("tennis_atp", "tennis_atp_us_open", True),
        (None, "soccer_epl", True),
    ],
)
def test_same_sport_same_gender(team_key, event_key, admitted):
    assert same_sport_same_gender(team_key, event_key) is admitted
