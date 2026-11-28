"""Guard tests for Item 1: My Stuff team-name matching requires same sport family & gender."""

from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
import sqlalchemy as sa
from fastapi import FastAPI
from sqlalchemy.dialects import postgresql

from app.dependencies.auth import get_optional_user
from app.models.models import Event, Sport
from app.routes import feed as feed_mod
from app.routes.feed import (
    _score_events,
    _sport_key_compatible_sql,
    router as feed_router,
)
from app.services import get_db
from app.utils import principal_independent_cache as pic
from app.utils.personalization import PersonalizationContext
from app.utils.sport_keys import same_sport_same_gender


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0)


def _make_ctx(team_ids: dict[int, set[str]] | None = None) -> PersonalizationContext:
    ctx = PersonalizationContext()
    ctx.team_relations = team_ids if team_ids is not None else {42: {"follow"}}
    ctx.sport_affinities = {}
    return ctx


def _make_event(
    event_id: int,
    sport_key: str,
    home_team_name: str,
    away_team_name: str,
    *,
    now: datetime,
    home_team_id: int | None = None,
    away_team_id: int | None = None,
) -> MagicMock:
    sport = MagicMock()
    sport.id = event_id * 10
    sport.key = sport_key
    sport.name = sport_key

    e = MagicMock()
    e.id = event_id
    e.sport_id = sport.id
    e.sport = sport
    e.home_team_id = home_team_id
    e.away_team_id = away_team_id
    e.home_team_name = home_team_name
    e.away_team_name = away_team_name
    e.status = "scheduled"
    e.commence_time = now + timedelta(hours=3)
    e.win_probability_sources = {
        "betting": {"value": 0.62, "away_value": 0.38},
    }
    e.win_probability_sources_rev = 1
    e.opening_home_probability = 0.60
    e.opening_away_probability = 0.40
    e.espn_win_prob_home = None
    e.opening_home_spread = None
    e.opening_over_under = None
    e.opening_favorite = None
    e.llm_importance = "regular"
    e.llm_gender = None
    e.llm_level = None
    e.llm_league = None
    e.statpal_end_time = None
    e.completed_at = None
    e.period = None
    e.raw_ei = 70.0
    e.ei_metadata = None
    e.home_score = None
    e.away_score = None
    e.external_id = f"ext-{event_id}"
    e.espn_id = f"espn-{event_id}"
    e.game_clock = None
    e.broadcast_info = None
    e.event_tags = []
    return e


class _RecordingDb:
    """AsyncSession mock capturing candidate Event Select queries."""

    def __init__(self, events: list[MagicMock]):
        self.events = events
        self.event_stmts: list = []

    @asynccontextmanager
    async def begin_nested(self):
        sp = MagicMock()
        sp.rollback = AsyncMock(return_value=None)
        sp.commit = AsyncMock(return_value=None)
        yield sp

    async def rollback(self):
        return None

    async def execute(self, stmt, params=None, *a, **k):
        r = MagicMock()
        r.all.return_value = []
        r.scalars.return_value.all.return_value = []
        if getattr(stmt, "column_descriptions", None) and any(
            d.get("entity") is Event for d in stmt.column_descriptions
        ):
            self.event_stmts.append(stmt)
            r.scalars.return_value.all.return_value = list(self.events)
        return r


@pytest.fixture(autouse=True)
def _clean_caches(monkeypatch):
    monkeypatch.setenv("FEED_SHARED_BUILD_CROSS_WORKER", "0")
    monkeypatch.setenv("PREMATCH_READING_CACHE", "0")
    pic.clear_shared_builds()
    yield
    pic.clear_shared_builds()


async def _run_score_events(db, events, *, ctx, my_team_names, my_team_sport_keys):
    now = _now()
    unified_stub = SimpleNamespace(
        events=list(events),
        by_id={},
        odds_map={},
        folded_card_map={},
        fold_result=SimpleNamespace(dropped_ids=[], folded_count=0, merged_sources=[]),
    )
    with (
        patch(
            "app.routes.feed._get_championship_probabilities",
            new=AsyncMock(return_value={}),
        ),
        patch(
            "app.utils.unified_game_read.load_unified_game_reads",
            new=AsyncMock(return_value=unified_stub),
        ),
    ):
        return await _score_events(
            db,
            now,
            None,
            ctx,
            my_teams_only=True,
            my_team_names=my_team_names,
            my_team_sport_keys=my_team_sport_keys,
        )


@pytest.mark.asyncio
async def test_query_and_per_game_filter_admit_football_and_exclude_basketball():
    now = _now()
    nd_football = _make_event(
        101,
        "americanfootball_ncaaf",
        "Notre Dame Fighting Irish",
        "USC Trojans",
        now=now,
    )
    nd_mens_hoops = _make_event(
        102,
        "basketball_ncaab",
        "Notre Dame Fighting Irish",
        "Duke Blue Devils",
        now=now,
    )
    nd_womens_hoops = _make_event(
        103,
        "basketball_wncaab",
        "UConn Huskies",
        "Notre Dame Fighting Irish",
        now=now,
    )
    unrelated_football = _make_event(
        104,
        "americanfootball_ncaaf",
        "Ohio State Buckeyes",
        "Michigan Wolverines",
        now=now,
    )
    all_events = [nd_football, nd_mens_hoops, nd_womens_hoops, unrelated_football]
    db = _RecordingDb(all_events)

    items = await _run_score_events(
        db,
        all_events,
        ctx=_make_ctx({42: {"follow"}}),
        my_team_names=["Notre Dame Fighting Irish"],
        my_team_sport_keys={"Notre Dame Fighting Irish": {"americanfootball_ncaaf"}},
    )

    served_ids = [item["data"]["id"] for item in items]
    assert served_ids == [101], f"Expected only Notre Dame football (101), got {served_ids}"

    assert len(db.event_stmts) == 1
    compiled = db.event_stmts[0].compile(
        dialect=postgresql.dialect(),
        compile_kwargs={"literal_binds": True},
    )
    sql = str(compiled)
    assert "%notre dame fighting irish%" in sql.lower()
    assert "lower(sports.key) = 'americanfootball'" in sql.lower()
    assert "americanfootball/_%" in sql.lower()
    assert "not (" in sql.lower()


@pytest.mark.asyncio
async def test_nd_football_excludes_womens_hoops_even_when_allowlisted(monkeypatch):
    """Non-vacuous: even if basketball_wncaab enters MY_STUFF_ALLOWED_SPORT_KEYS,
    Notre Dame women's basketball still cannot match a Notre Dame football follow.
    """
    monkeypatch.setattr(
        feed_mod,
        "MY_STUFF_ALLOWED_SPORT_KEYS",
        feed_mod.MY_STUFF_ALLOWED_SPORT_KEYS | {"basketball_wncaab"},
    )
    now = _now()
    nd_football = _make_event(
        111,
        "americanfootball_ncaaf",
        "Notre Dame Fighting Irish",
        "USC Trojans",
        now=now,
    )
    nd_mens_hoops = _make_event(
        112,
        "basketball_ncaab",
        "Notre Dame Fighting Irish",
        "Duke Blue Devils",
        now=now,
    )
    nd_womens_hoops = _make_event(
        113,
        "basketball_wncaab",
        "UConn Huskies",
        "Notre Dame Fighting Irish",
        now=now,
    )
    db = _RecordingDb([nd_football, nd_mens_hoops, nd_womens_hoops])

    items = await _run_score_events(
        db,
        [nd_football, nd_mens_hoops, nd_womens_hoops],
        ctx=_make_ctx({42: {"follow"}}),
        my_team_names=["Notre Dame Fighting Irish"],
        my_team_sport_keys={"Notre Dame Fighting Irish": {"americanfootball_ncaaf"}},
    )
    assert [item["data"]["id"] for item in items] == [111]


@pytest.mark.asyncio
async def test_arsenal_premier_league_follow_keeps_champions_league_and_excludes_womens(
    monkeypatch,
):
    """Club follow in one league keeps other competitions of the same sport & gender.

    Production specimen: Arsenal (id=133, soccer_epl) vs Champions League Arsenal
    (event 15354424, soccer_uefa_champs_league, team id=6314) vs Women's Champions
    League Arsenal (event 15349510, soccer_uefa_champs_league_women).
    """
    # Test both unpatched MY_STUFF_ALLOWED_SPORT_KEYS (Champions League is already in it)
    # and with women's UCL allowlisted so the gender gate itself is proven non-vacuous.
    now = _now()
    arsenal_epl = _make_event(
        15350001,
        "soccer_epl",
        "Arsenal",
        "Chelsea",
        now=now,
        home_team_id=133,
    )
    arsenal_mens_ucl = _make_event(
        15354424,
        "soccer_uefa_champs_league",
        "Arsenal",
        "Real Madrid",
        now=now,
        home_team_id=None,
    )
    arsenal_womens_ucl = _make_event(
        15349510,
        "soccer_uefa_champs_league_women",
        "Arsenal",
        "Lyon",
        now=now,
        home_team_id=None,
    )
    arsenal_unrelated_hoops = _make_event(
        15359999,
        "basketball_nba",
        "Arsenal",
        "Boston Celtics",
        now=now,
    )
    all_events = [
        arsenal_epl,
        arsenal_mens_ucl,
        arsenal_womens_ucl,
        arsenal_unrelated_hoops,
    ]

    db_default = _RecordingDb([arsenal_epl, arsenal_mens_ucl, arsenal_unrelated_hoops])
    items_default = await _run_score_events(
        db_default,
        [arsenal_epl, arsenal_mens_ucl, arsenal_unrelated_hoops],
        ctx=_make_ctx({133: {"follow"}}),
        my_team_names=["Arsenal"],
        my_team_sport_keys={"Arsenal": {"soccer_epl"}},
    )
    assert sorted(item["data"]["id"] for item in items_default) == [
        15350001,
        15354424,
    ]

    monkeypatch.setattr(
        feed_mod,
        "MY_STUFF_ALLOWED_SPORT_KEYS",
        feed_mod.MY_STUFF_ALLOWED_SPORT_KEYS | {"soccer_uefa_champs_league_women"},
    )
    db_women_allowed = _RecordingDb(all_events)
    items_women_allowed = await _run_score_events(
        db_women_allowed,
        all_events,
        ctx=_make_ctx({133: {"follow"}}),
        my_team_names=["Arsenal"],
        my_team_sport_keys={"Arsenal": {"soccer_epl"}},
    )
    assert sorted(item["data"]["id"] for item in items_women_allowed) == [
        15350001,
        15354424,
    ]

    sql = str(
        db_women_allowed.event_stmts[0].compile(
            dialect=postgresql.dialect(),
            compile_kwargs={"literal_binds": True},
        )
    )
    assert "lower(sports.key) = 'soccer'" in sql.lower()
    assert "soccer/_%" in sql.lower()
    assert "/_women%" in sql.lower()
    assert "sports.key in ('soccer_epl')" not in sql.lower()


@pytest.mark.asyncio
async def test_womens_club_follow_keeps_womens_competitions_and_excludes_mens(
    monkeypatch,
):
    """Reverse direction: a women's follow keeps women's soccer and excludes men's."""
    monkeypatch.setattr(
        feed_mod,
        "MY_STUFF_ALLOWED_SPORT_KEYS",
        feed_mod.MY_STUFF_ALLOWED_SPORT_KEYS
        | {"soccer_uefa_champs_league_women", "soccer_england_wsl_women"},
    )
    now = _now()
    arsenal_wsl = _make_event(
        501,
        "soccer_england_wsl_women",
        "Arsenal",
        "Chelsea",
        now=now,
    )
    arsenal_womens_ucl = _make_event(
        502,
        "soccer_uefa_champs_league_women",
        "Arsenal",
        "Lyon",
        now=now,
    )
    arsenal_mens_epl = _make_event(
        503,
        "soccer_epl",
        "Arsenal",
        "Tottenham Hotspur",
        now=now,
    )
    arsenal_mens_ucl = _make_event(
        504,
        "soccer_uefa_champs_league",
        "Arsenal",
        "Real Madrid",
        now=now,
    )
    db = _RecordingDb(
        [arsenal_wsl, arsenal_womens_ucl, arsenal_mens_epl, arsenal_mens_ucl]
    )
    items = await _run_score_events(
        db,
        [arsenal_wsl, arsenal_womens_ucl, arsenal_mens_epl, arsenal_mens_ucl],
        ctx=_make_ctx({700: {"follow"}}),
        my_team_names=["Arsenal"],
        my_team_sport_keys={"Arsenal": {"soccer_england_wsl_women"}},
    )
    assert sorted(item["data"]["id"] for item in items) == [501, 502]


@pytest.mark.asyncio
async def test_basketball_mens_and_womens_gender_keys_stay_separate(monkeypatch):
    """WNCAAB / WNBA keys are female-coded even without ``_women`` in the key string."""
    monkeypatch.setattr(
        feed_mod,
        "MY_STUFF_ALLOWED_SPORT_KEYS",
        feed_mod.MY_STUFF_ALLOWED_SPORT_KEYS | {"basketball_wncaab"},
    )
    now = _now()
    nd_mens = _make_event(
        601,
        "basketball_ncaab",
        "Notre Dame Fighting Irish",
        "Duke Blue Devils",
        now=now,
    )
    nd_womens = _make_event(
        602,
        "basketball_wncaab",
        "Notre Dame Fighting Irish",
        "UConn Huskies",
        now=now,
    )
    nd_football = _make_event(
        603,
        "americanfootball_ncaaf",
        "Notre Dame Fighting Irish",
        "USC Trojans",
        now=now,
    )

    db_men = _RecordingDb([nd_mens, nd_womens, nd_football])
    items_men = await _run_score_events(
        db_men,
        [nd_mens, nd_womens, nd_football],
        ctx=_make_ctx({801: {"follow"}}),
        my_team_names=["Notre Dame Fighting Irish"],
        my_team_sport_keys={"Notre Dame Fighting Irish": {"basketball_ncaab"}},
    )
    assert [item["data"]["id"] for item in items_men] == [601]

    db_women = _RecordingDb([nd_mens, nd_womens, nd_football])
    items_women = await _run_score_events(
        db_women,
        [nd_mens, nd_womens, nd_football],
        ctx=_make_ctx({802: {"follow"}}),
        my_team_names=["Notre Dame Fighting Irish"],
        my_team_sport_keys={"Notre Dame Fighting Irish": {"basketball_wncaab"}},
    )
    assert [item["data"]["id"] for item in items_women] == [602]

    assert same_sport_same_gender("basketball_nba", "basketball_ncaab") is True
    assert same_sport_same_gender("basketball_nba", "basketball_wnba") is False
    assert same_sport_same_gender("basketball_wnba", "basketball_wncaab") is True
    assert same_sport_same_gender("basketball_wnba", "basketball_ncaab") is False


def test_sql_and_python_gender_sport_filters_match_exactly():
    """``_sport_key_compatible_sql`` executes 1:1 with ``same_sport_same_gender``."""
    sport_keys = (
        "americanfootball_ncaaf",
        "americanfootball_nfl",
        "basketball_ncaab",
        "basketball_nba",
        "basketball_wncaab",
        "basketball_wnba",
        "soccer_epl",
        "soccer_usa_mls",
        "soccer_uefa_champs_league",
        "soccer_uefa_champs_league_women",
        "soccer_england_wsl_women",
        "soccer_spain_la_liga",
        "soccer_other",
        "tennis_atp",
        "tennis_wta",
        "golf_pga",
        "rugbyleague_nrl",
        "rugbyleague_nrlw",
        "rugbyunion_six_nations",
        "rugby_other",
        "aussierules_afl",
        "aussierules_aflw",
        "icehockey_nhl",
        "baseball_mlb",
        "mma_mixed_martial_arts",
    )
    engine = sa.create_engine("sqlite://")
    Sport.__table__.create(engine)
    try:
        with engine.begin() as conn:
            for idx, key in enumerate(sport_keys, start=1):
                conn.execute(
                    sa.insert(Sport.__table__).values(id=idx, key=key, name=key)
                )
        with engine.connect() as conn:
            for fk in sport_keys:
                cond = _sport_key_compatible_sql({fk})
                sql_matches = {
                    row[0]
                    for row in conn.execute(sa.select(Sport.key).where(cond))
                }
                py_matches = {
                    ek for ek in sport_keys if same_sport_same_gender(fk, ek)
                }
                assert sql_matches == py_matches, (
                    f"Mismatch for {fk!r}: sql={sorted(sql_matches)} py={sorted(py_matches)}"
                )
    finally:
        engine.dispose()


@pytest.mark.asyncio
async def test_query_and_per_game_filter_are_per_team_not_union_of_followed_sports():
    """Following Notre Dame football + Boston Celtics NBA still excludes Notre Dame basketball."""
    now = _now()
    nd_football = _make_event(
        201,
        "americanfootball_ncaaf",
        "Notre Dame Fighting Irish",
        "Stanford Cardinal",
        now=now,
    )
    nd_mens_hoops = _make_event(
        202,
        "basketball_ncaab",
        "Notre Dame Fighting Irish",
        "North Carolina Tar Heels",
        now=now,
    )
    celtics_nba = _make_event(
        203,
        "basketball_nba",
        "Boston Celtics",
        "Miami Heat",
        now=now,
    )
    all_events = [nd_football, nd_mens_hoops, celtics_nba]
    db = _RecordingDb(all_events)

    items = await _run_score_events(
        db,
        all_events,
        ctx=_make_ctx({42: {"follow"}, 77: {"follow"}}),
        my_team_names=["Notre Dame Fighting Irish", "Boston Celtics"],
        my_team_sport_keys={
            "Notre Dame Fighting Irish": {"americanfootball_ncaaf"},
            "Boston Celtics": {"basketball_nba"},
        },
    )

    served_ids = sorted(item["data"]["id"] for item in items)
    assert served_ids == [201, 203], f"Expected ND football (201) + Celtics NBA (203), got {served_ids}"

    sql = str(
        db.event_stmts[0].compile(
            dialect=postgresql.dialect(),
            compile_kwargs={"literal_binds": True},
        )
    )
    assert "'americanfootball_ncaaf'" in sql
    assert "'basketball_nba'" in sql


@pytest.mark.asyncio
async def test_multi_sport_follow_for_same_name_admits_both_followed_sports():
    now = _now()
    nd_football = _make_event(
        301,
        "americanfootball_ncaaf",
        "Notre Dame Fighting Irish",
        "Navy Midshipmen",
        now=now,
    )
    nd_mens_hoops = _make_event(
        302,
        "basketball_ncaab",
        "Notre Dame Fighting Irish",
        "Syracuse Orange",
        now=now,
    )
    nd_womens_hoops = _make_event(
        303,
        "basketball_wncaab",
        "Notre Dame Fighting Irish",
        "Louisville Cardinals",
        now=now,
    )
    all_events = [nd_football, nd_mens_hoops, nd_womens_hoops]
    db = _RecordingDb(all_events)

    items = await _run_score_events(
        db,
        all_events,
        ctx=_make_ctx({42: {"follow"}, 43: {"follow"}}),
        my_team_names=["Notre Dame Fighting Irish", "Notre Dame Fighting Irish"],
        my_team_sport_keys={
            "Notre Dame Fighting Irish": {"americanfootball_ncaaf", "basketball_ncaab"}
        },
    )

    assert sorted(item["data"]["id"] for item in items) == [301, 302]


@pytest.mark.asyncio
async def test_team_id_match_still_admits_linked_game_while_rejecting_wrong_sport_unlinked():
    now = _now()
    linked_football = _make_event(
        401,
        "americanfootball_ncaaf",
        "Notre Dame Fighting Irish",
        "Clemson Tigers",
        now=now,
        home_team_id=42,
    )
    unlinked_hoops = _make_event(
        402,
        "basketball_ncaab",
        "Notre Dame Fighting Irish",
        "Virginia Cavaliers",
        now=now,
    )
    db = _RecordingDb([linked_football, unlinked_hoops])

    items = await _run_score_events(
        db,
        [linked_football, unlinked_hoops],
        ctx=_make_ctx({42: {"follow"}}),
        my_team_names=["Notre Dame Fighting Irish"],
        my_team_sport_keys={"Notre Dame Fighting Irish": {"americanfootball_ncaaf"}},
    )

    assert [item["data"]["id"] for item in items] == [401]


@pytest.mark.asyncio
async def test_get_feed_passes_my_team_sport_keys_to_score_events():
    ctx = _make_ctx({42: {"follow"}})
    ctx.is_authenticated = True
    captured: dict = {}

    class _FeedDb:
        async def execute(self, stmt, *a, **k):
            r = MagicMock()
            s = str(stmt).lower()
            if "from teams" in s and "join sports" in s:
                r.all.return_value = [
                    ("Notre Dame Fighting Irish", "americanfootball_ncaaf")
                ]
            else:
                r.all.return_value = []
            r.scalars.return_value.all.return_value = []
            return r

    async def _fake_score_events(*args, **kwargs):
        captured["my_team_names"] = kwargs.get("my_team_names")
        captured["my_team_sport_keys"] = kwargs.get("my_team_sport_keys")
        return []

    test_app = FastAPI()
    test_app.include_router(feed_router, prefix="/api/feed")
    fake_db = _FeedDb()

    async def _override_db():
        yield fake_db

    test_app.dependency_overrides[get_db] = _override_db
    test_app.dependency_overrides[get_optional_user] = lambda: SimpleNamespace(id=7)

    with (
        patch(
            "app.routes.feed._load_personalization_context",
            new=AsyncMock(return_value=ctx),
        ),
        patch("app.routes.feed._score_events", side_effect=_fake_score_events),
    ):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=test_app), base_url="http://test"
        ) as client:
            resp = await client.get(
                "/api/feed?my_teams_only=true&include_events=true&include_futures=false"
            )

    assert resp.status_code == 200
    assert captured["my_team_names"] == ["Notre Dame Fighting Irish"]
    assert captured["my_team_sport_keys"] == {
        "Notre Dame Fighting Irish": {"americanfootball_ncaaf"}
    }
