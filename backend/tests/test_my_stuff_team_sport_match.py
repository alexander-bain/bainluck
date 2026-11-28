"""Guard tests for Item 1: My Stuff team-name matching requires the followed team's own sport."""

from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from fastapi import FastAPI
from sqlalchemy.dialects import postgresql

from app.dependencies.auth import get_optional_user
from app.models.models import Event
from app.routes.feed import _score_events, router as feed_router
from app.services import get_db
from app.utils import principal_independent_cache as pic
from app.utils.personalization import PersonalizationContext


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
    assert sql.count("sports.key IN ('americanfootball_ncaaf')") >= 2
    assert ") AND sports.key IN ('americanfootball_ncaaf')" in sql


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
