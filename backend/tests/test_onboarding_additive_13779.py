"""#13779 (427: A): POST /api/me/onboarding is additive for returning users.

Guard 1: A signed-in user with three onboarding teams, hand-set category
levels, and a home location opens the checklist, follows one more team, and
finishes. All three prior teams, hand-set category levels, and the home location
survive alongside the newly followed team (and re-submitting an existing pair
is idempotent).

Guard 2: A first-run sitting (no stored preferences or teams yet) persists the
initial teams, category levels, home location, raw inputs, and
``onboarding_completed=True`` identically to before.
"""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import Session

from app.models.models import (
    Base,
    RetiredTeamRedirect,
    Sport,
    Team,
    User,
    UserFavorite,
    UserPreference,
)
from app.routes.user import OnboardingRequest, TeamRef, get_preferences, submit_onboarding


@compiles(JSONB, "sqlite")
def _jsonb_on_sqlite(type_, compiler, **kw):  # pragma: no cover - DDL shim
    return "JSON"


@compiles(ARRAY, "sqlite")
def _array_on_sqlite(type_, compiler, **kw):  # pragma: no cover - DDL shim
    return "JSON"


class _SyncBackedAsyncSession(AsyncSession):
    """Lightweight AsyncSession subclass backed by in-memory SQLite."""

    def __init__(self, sync_session: Session) -> None:
        self._sync = sync_session
        self.sync_session = sync_session

    def add(self, instance, _warn: bool = True) -> None:
        self._sync.add(instance)

    async def execute(self, statement, *args, **kwargs):
        return self._sync.execute(statement)

    async def flush(self, objects=None) -> None:
        self._sync.flush(objects)

    async def commit(self) -> None:
        self._sync.commit()


def _make_session() -> tuple[Session, _SyncBackedAsyncSession]:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(
        engine,
        tables=[
            Sport.__table__,
            Team.__table__,
            RetiredTeamRedirect.__table__,
            User.__table__,
            UserFavorite.__table__,
            UserPreference.__table__,
        ],
    )
    sync_session = Session(engine, expire_on_commit=False)
    sync_session.add_all(
        [
            Sport(id=1, key="americanfootball_nfl", name="NFL", group="Football"),
            Sport(id=2, key="basketball_nba", name="NBA", group="Basketball"),
            Sport(id=3, key="baseball_mlb", name="MLB", group="Baseball"),
            Sport(id=4, key="icehockey_nhl", name="NHL", group="Hockey"),
            Team(id=101, sport_id=1, name="New England Patriots", slug="patriots"),
            Team(id=102, sport_id=2, name="Boston Celtics", slug="celtics"),
            Team(id=103, sport_id=3, name="Boston Red Sox", slug="red-sox"),
            Team(id=104, sport_id=4, name="Boston Bruins", slug="bruins"),
            User(id=1, firebase_uid="uid-427a"),
        ]
    )
    sync_session.commit()
    return sync_session, _SyncBackedAsyncSession(sync_session)


@pytest.mark.asyncio
async def test_reopening_checklist_preserves_prior_teams_levels_and_location():
    """Guard 1 (427: A): finishing checklist adds without wiping prior state."""
    sync, db = _make_session()
    user = sync.get(User, 1)

    sync.add_all(
        [
            UserFavorite(
                user_id=1,
                team_id=101,
                relation_type="local",
                source="onboarding",
                weight=1.0,
            ),
            UserFavorite(
                user_id=1,
                team_id=102,
                relation_type="follow",
                source="onboarding",
                weight=1.0,
            ),
            UserFavorite(
                user_id=1,
                team_id=103,
                relation_type="alma_mater",
                source="onboarding",
                weight=1.0,
            ),
            UserPreference(
                user_id=1,
                home_location="Boston",
                sport_affinities={
                    "americanfootball_nfl": 0.3,
                    "basketball_nba": 0.1,
                    "baseball_mlb": 0.0,
                    "politics": 1.0,
                },
                onboarding_completed=True,
                onboarding_raw={"initial": ["Patriots", "Celtics", "Red Sox"]},
            ),
        ]
    )
    sync.commit()

    # Checklist sitting: user follows Boston Bruins (hockey) and re-picks
    # Celtics (already followed), sends no home_location, and touches nfl + hockey.
    body = OnboardingRequest(
        home_location=None,
        follow_teams=[TeamRef(team_id=104), TeamRef(team_id=102)],
        sport_affinities={"nfl": 1.0, "hockey": 1.0},
        raw_inputs={"212a_picks": ["Boston Bruins", "Boston Celtics"]},
    )
    ret = await submit_onboarding(body=body, user=user, db=db)
    await db.commit()

    assert ret == {"status": "ok", "onboarding_completed": True}

    fav_rows = sync.execute(
        select(UserFavorite.team_id, UserFavorite.relation_type).where(
            UserFavorite.user_id == 1
        )
    ).all()
    assert set(fav_rows) == {
        (101, "local"),
        (102, "follow"),
        (103, "alma_mater"),
        (104, "follow"),
    }

    prefs = sync.execute(
        select(UserPreference).where(UserPreference.user_id == 1)
    ).scalar_one()
    assert prefs.home_location == "Boston"
    assert prefs.onboarding_completed is True
    assert prefs.sport_affinities == {
        "americanfootball_nfl": 0.3,
        "basketball_nba": 0.1,
        "baseball_mlb": 0.0,
        "politics": 1.0,
        "icehockey_nhl": 1.0,
    }
    assert prefs.onboarding_raw == {
        "initial": ["Patriots", "Celtics", "Red Sox"],
        "212a_picks": ["Boston Bruins", "Boston Celtics"],
    }


@pytest.mark.asyncio
async def test_first_run_sitting_still_saves_initial_teams_levels_and_location():
    """Guard 2 (427: A): blank first-run user saves identically to today."""
    sync, db = _make_session()
    user = sync.get(User, 1)

    body = OnboardingRequest(
        home_location="Boston",
        local_teams=[TeamRef(team_id=101)],
        follow_teams=[TeamRef(team_id=102)],
        sport_affinities={"nfl": 1.0, "nba": 0.3, "politics": 0.1},
        raw_inputs={"212a_picks": ["New England Patriots", "Boston Celtics"]},
    )
    ret = await submit_onboarding(body=body, user=user, db=db)
    await db.commit()

    assert ret == {"status": "ok", "onboarding_completed": True}

    prefs_resp = await get_preferences(user=user, db=db)
    assert prefs_resp.home_location == "Boston"
    assert prefs_resp.onboarding_completed is True
    assert prefs_resp.sport_affinities == {
        "nfl": 1.0,
        "nba": 0.3,
        "politics": 0.1,
    }
    assert {(f.team_id, f.relation_type) for f in prefs_resp.favorites} == {
        (101, "local"),
        (102, "follow"),
    }
