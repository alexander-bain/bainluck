"""#13229 / 314-B: retired-team redirects and anti-recreation guards.

Pins the two halves of the prerequisite PR before any duplicate-team fold runs:

1. **Redirects on read/write entry points:**
   - ``GET /api/teams/<old_id>`` and ``GET /api/teams/<old_slug>`` resolve
     transparently through ``retired_team_redirects`` to the surviving canonical
     team (including chained redirects).
   - ``POST /api/me/favorites`` and ``DELETE /api/me/favorites/<old_id>`` (and
     ``POST /api/me/onboarding``) follow ``retired_team_redirects`` to the
     canonical team id instead of 404ing on cached 1.0.8 Follow taps.

2. **Anti-recreation guards on all three ``Team(...)`` creation sites:**
   - ``app.utils.espn_helpers.upsert_team``
   - ``app.tasks.sports._auto_create_missing_teams``
   - ``app.routes.user.search_teams`` (saved names and aliases)
   Pinned on all six real short spellings (``"Tottenham"``, ``"Newcastle"``,
   ``"Nottingham"``, ``"Ottawa"``, ``"Toronto"``, ``"Columbus"``) plus nearest
   wrong neighbours (reserve/women's sides under #13202 / 286: B, ambiguous
   shared cities/mascots, school-modifier traps, cross-league isolation, and
   #6215 wrong event-level ESPN payloads).
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine, select, text
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import Session

from app.models.models import (
    Base,
    Event,
    FuturesMarket,
    FuturesOutcome,
    RetiredTeamRedirect,
    Sport,
    Team,
    TeamIdentityMapping,
    User,
    UserFavorite,
    UserPreference,
)
from app.routes import teams as teams_route
from app.routes import user as user_route
from app.tasks.sports import _auto_create_missing_teams
from app.utils.espn_helpers import upsert_team
from app.utils.team_redirects import (
    distinguishing_tokens_agree,
    find_existing_team_in_sport,
    resolve_retired_team_by_identifier,
    resolve_retired_team_id,
    unambiguous_short_spelling_match,
)


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
        if str(statement) == "SET LOCAL statement_timeout = '2s'":
            return None  # PostgreSQL enforcement is exercised in the route's integration tests.
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
            TeamIdentityMapping.__table__,
            Event.__table__,
            FuturesMarket.__table__,
            FuturesOutcome.__table__,
            User.__table__,
            UserFavorite.__table__,
            UserPreference.__table__,
        ],
    )
    with engine.begin() as conn:
        conn.execute(
            text(
                "CREATE UNIQUE INDEX IF NOT EXISTS uq_tim_source_name "
                "ON team_identity_mapping (source, source_name, sport_key) "
                "WHERE source_name IS NOT NULL"
            )
        )
    sync_session = Session(engine, expire_on_commit=False)
    return sync_session, _SyncBackedAsyncSession(sync_session)


def _seed_six_canonical_clubs(sync: Session) -> dict[str, Team]:
    epl = Sport(id=1, key="soccer_epl", name="Premier League")
    nhl = Sport(id=2, key="icehockey_nhl", name="NHL")
    mls = Sport(id=3, key="soccer_usa_mls", name="MLS")
    ncaab = Sport(id=4, key="basketball_ncaab", name="NCAAB")
    mlb = Sport(id=5, key="baseball_mlb", name="MLB")
    sync.add_all([epl, nhl, mls, ncaab, mlb])

    clubs = {
        "Tottenham": Team(
            id=146,
            sport_id=1,
            name="Tottenham Hotspur",
            slug="tottenham-hotspur-epl",
            espn_id="367",
            abbreviation="TOT",
            primary_color="#132257",
            logo_url_small="https://a.espncdn.com/i/teamlogos/soccer/500/367.png",
        ),
        "Newcastle": Team(
            id=143,
            sport_id=1,
            name="Newcastle United",
            slug="newcastle-united-epl",
            espn_id="361",
            abbreviation="NEW",
            primary_color="#241f20",
            logo_url_small="https://a.espncdn.com/i/teamlogos/soccer/500/361.png",
        ),
        "Nottingham": Team(
            id=2,
            sport_id=1,
            name="Nottingham Forest",
            slug="nottingham-forest-epl",
            espn_id="393",
            abbreviation="NFO",
            primary_color="#dd0000",
            logo_url_small="https://a.espncdn.com/i/teamlogos/soccer/500/393.png",
        ),
        "Ottawa": Team(
            id=56,
            sport_id=2,
            name="Ottawa Senators",
            slug="ottawa-senators-nhl",
            espn_id="14",
            abbreviation="OTT",
            primary_color="#c8102e",
            logo_url_small="https://a.espncdn.com/i/teamlogos/nhl/500/ott.png",
        ),
        "Toronto": Team(
            id=115,
            sport_id=2,
            name="Toronto Maple Leafs",
            slug="toronto-maple-leafs-nhl",
            espn_id="21",
            abbreviation="TOR",
            primary_color="#00205b",
            logo_url_small="https://a.espncdn.com/i/teamlogos/nhl/500/tor.png",
        ),
        "Columbus": Team(
            id=572,
            sport_id=2,
            name="Columbus Blue Jackets",
            slug="columbus-blue-jackets-nhl",
            espn_id="29",
            abbreviation="CBJ",
            primary_color="#002654",
            logo_url_small="https://a.espncdn.com/i/teamlogos/nhl/500/cbj.png",
        ),
    }
    sync.add_all(clubs.values())
    sync.commit()
    return clubs


SIX_SHORT_SPELLINGS = [
    ("Tottenham", 1, 146, "Tottenham Hotspur", "367"),
    ("Newcastle", 1, 143, "Newcastle United", "361"),
    ("Nottingham", 1, 2, "Nottingham Forest", "393"),
    ("Ottawa", 2, 56, "Ottawa Senators", "14"),
    ("Toronto", 2, 115, "Toronto Maple Leafs", "21"),
    ("Columbus", 2, 572, "Columbus Blue Jackets", "29"),
]


class TestRetiredTeamRedirectsRoutes:
    @pytest.mark.asyncio
    async def test_get_team_by_retired_id_and_retired_slug_resolve_to_survivor(self):
        sync, db = _make_session()
        _seed_six_canonical_clubs(sync)
        sync.add(
            RetiredTeamRedirect(
                retired_team_id=14545,
                retired_slug="tottenham",
                retired_name="Tottenham",
                sport_id=1,
                canonical_team_id=146,
                reason="fold_13229",
            )
        )
        sync.commit()

        by_id = await teams_route.get_team("14545", db=db)
        by_slug = await teams_route.get_team("tottenham", db=db)

        assert by_id["team"]["id"] == 146
        assert by_id["team"]["name"] == "Tottenham Hotspur"
        assert by_id["team"]["slug"] == "tottenham-hotspur-epl"
        assert by_slug["team"]["id"] == 146
        assert by_slug["team"]["name"] == "Tottenham Hotspur"

    @pytest.mark.asyncio
    async def test_chained_redirect_follows_to_final_survivor(self):
        sync, db = _make_session()
        _seed_six_canonical_clubs(sync)
        sync.add_all([
            RetiredTeamRedirect(
                retired_team_id=99001,
                retired_slug="spurs-old",
                retired_name="Spurs Old",
                sport_id=1,
                canonical_team_id=14545,
                reason="fold_1",
            ),
            RetiredTeamRedirect(
                retired_team_id=14545,
                retired_slug="tottenham",
                retired_name="Tottenham",
                sport_id=1,
                canonical_team_id=146,
                reason="fold_2",
            ),
        ])
        sync.commit()

        assert await resolve_retired_team_id(db, 99001) == 146
        assert await resolve_retired_team_by_identifier(db, "spurs-old") == 146
        assert await resolve_retired_team_by_identifier(db, "99001") == 146

    @pytest.mark.asyncio
    async def test_favorites_post_and_delete_follow_retired_team_id(self):
        sync, db = _make_session()
        _seed_six_canonical_clubs(sync)
        user = User(id=7, firebase_uid="uid-7", email="reader@example.com")
        sync.add(user)
        sync.add(
            RetiredTeamRedirect(
                retired_team_id=14545,
                retired_slug="tottenham",
                retired_name="Tottenham",
                sport_id=1,
                canonical_team_id=146,
                reason="fold_13229",
            )
        )
        sync.commit()

        # POST with retired id saves favorite under canonical id 146
        resp1 = await user_route.add_favorite(
            user_route.AddFavoriteRequest(team_id=14545, relation_type="follow"),
            user=user,
            db=db,
        )
        assert resp1 == {"status": "added"}
        favs = sync.execute(select(UserFavorite)).scalars().all()
        assert len(favs) == 1
        assert favs[0].team_id == 146

        # Second POST with retired id (or canonical id) deduplicates cleanly
        resp2 = await user_route.add_favorite(
            user_route.AddFavoriteRequest(team_id=14545, relation_type="follow"),
            user=user,
            db=db,
        )
        assert resp2 == {"status": "already_exists"}
        assert len(sync.execute(select(UserFavorite)).scalars().all()) == 1

        # DELETE with retired id removes the canonical favorite
        resp3 = await user_route.remove_favorite(
            14545, relation_type="follow", user=user, db=db
        )
        assert resp3 == {"status": "removed"}
        assert sync.execute(select(UserFavorite)).scalars().all() == []

        # Unknown id with no redirect still 404s cleanly
        with pytest.raises(HTTPException) as exc:
            await user_route.add_favorite(
                user_route.AddFavoriteRequest(team_id=88888, relation_type="follow"),
                user=user,
                db=db,
            )
        assert exc.value.status_code == 404

    @pytest.mark.asyncio
    async def test_onboarding_remaps_and_deduplicates_retired_team_ids(self):
        sync, db = _make_session()
        _seed_six_canonical_clubs(sync)
        user = User(id=8, firebase_uid="uid-8", email="onboard@example.com")
        sync.add(user)
        sync.add(
            RetiredTeamRedirect(
                retired_team_id=14545,
                retired_slug="tottenham",
                retired_name="Tottenham",
                sport_id=1,
                canonical_team_id=146,
                reason="fold_13229",
            )
        )
        sync.commit()

        body = user_route.OnboardingRequest(
            home_location="London",
            follow_teams=[
                user_route.TeamRef(team_id=14545),
                user_route.TeamRef(team_id=146),
            ],
            sport_affinities={"soccer": 1.0},
        )
        await user_route.submit_onboarding(body=body, user=user, db=db)
        favs = sync.execute(select(UserFavorite)).scalars().all()
        assert len(favs) == 1
        assert favs[0].team_id == 146


class TestCreationGuardsSixRealShortSpellings:
    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "short_name,sport_id,expected_id,full_name,espn_id",
        SIX_SHORT_SPELLINGS,
    )
    async def test_site1_espn_upsert_team_does_not_recreate_short_spelling(
        self, short_name, sport_id, expected_id, full_name, espn_id
    ):
        sync, db = _make_session()
        _seed_six_canonical_clubs(sync)
        before_count = len(sync.execute(select(Team)).scalars().all())

        espn_payload = SimpleNamespace(
            espn_id=espn_id,
            name=full_name,
            display_name=full_name,
            short_name=full_name,
            nickname=full_name.split()[-1],
            abbreviation=None,
            primary_color=None,
            secondary_color=None,
            logo_url=None,
            logo_url_dark=None,
            record=None,
            location=full_name,
        )
        # Run with cold cache (DB path)
        resolved = await upsert_team(db, short_name, espn_payload, sport_id)
        assert resolved is not None
        assert resolved.id == expected_id
        assert len(sync.execute(select(Team)).scalars().all()) == before_count

        # Run with warm full-sport cache
        sport_teams = (
            sync.execute(select(Team).where(Team.sport_id == sport_id))
            .scalars()
            .all()
        )
        cache = {(t.name, t.sport_id): t for t in sport_teams}
        resolved_cached = await upsert_team(
            db, short_name, espn_payload, sport_id, team_cache=cache
        )
        assert resolved_cached is not None
        assert resolved_cached.id == expected_id
        assert len(sync.execute(select(Team)).scalars().all()) == before_count

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "short_name,sport_id,expected_id,full_name,espn_id",
        SIX_SHORT_SPELLINGS,
    )
    async def test_site2_sports_auto_create_does_not_recreate_short_spelling(
        self, short_name, sport_id, expected_id, full_name, espn_id
    ):
        sync, db = _make_session()
        _seed_six_canonical_clubs(sync)
        before_count = len(sync.execute(select(Team)).scalars().all())

        sport_key = "soccer_epl" if sport_id == 1 else "icehockey_nhl"
        created = await _auto_create_missing_teams(
            db, sport_id, sport_key, {short_name}
        )
        assert created == 0
        assert len(sync.execute(select(Team)).scalars().all()) == before_count

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "short_name,sport_id,expected_id,full_name,espn_id",
        SIX_SHORT_SPELLINGS,
    )
    async def test_site3_user_search_does_not_recreate_short_spelling(
        self, short_name, sport_id, expected_id, full_name, espn_id, monkeypatch
    ):
        sync, db = _make_session()
        _seed_six_canonical_clubs(sync)
        before_count = len(sync.execute(select(Team)).scalars().all())

        # The game has the incoming spelling and the verified club link.
        sync.add(
            Event(
                id=9000 + expected_id,
                external_id=f"ext-{expected_id}",
                sport_id=sport_id,
                home_team_id=expected_id,
                home_team_name=short_name,
                away_team_name="Opponent FC",
                commence_time=datetime.now(timezone.utc) + timedelta(days=1),
                status="upcoming",
            )
        )
        sync.commit()

        async def membership(candidates):
            return {(sport_id, expected_id)}

        monkeypatch.setattr(user_route, "onboarding_team_members", membership)
        results = await user_route.search_teams(q=short_name, db=db)
        assert any(r.id == expected_id for r in results)
        # No duplicate row for the short spelling was minted
        same_sport = (
            sync.execute(select(Team).where(Team.sport_id == sport_id))
            .scalars()
            .all()
        )
        assert all(t.name != short_name for t in same_sport)
        assert len(sync.execute(select(Team)).scalars().all()) == before_count

    @pytest.mark.asyncio
    async def test_site3_user_search_keeps_the_linked_clubs_retired_name(
        self, monkeypatch,
    ):
        sync, db = _make_session()
        _seed_six_canonical_clubs(sync)
        sync.add(
            RetiredTeamRedirect(
                retired_team_id=14545,
                retired_slug="spurs",
                retired_name="Spurs",
                sport_id=1,
                canonical_team_id=146,
                reason="fold_13229",
            )
        )
        sync.add(
            Event(
                id=9910,
                external_id="ext-spurs",
                sport_id=1,
                home_team_id=146,
                home_team_name="Spurs",
                away_team_name="Opponent FC",
                commence_time=datetime.now(timezone.utc) + timedelta(days=1),
                status="upcoming",
            )
        )
        sync.commit()
        before_count = len(sync.execute(select(Team)).scalars().all())

        async def membership(candidates):
            return {(1, 146)}

        monkeypatch.setattr(user_route, "onboarding_team_members", membership)
        results = await user_route.search_teams(q="Spurs", db=db)
        assert any(r.id == 146 and r.name == "Tottenham Hotspur" for r in results)
        assert len(sync.execute(select(Team)).scalars().all()) == before_count

    @pytest.mark.asyncio
    async def test_guard_resolves_via_retired_name_identity_mapping_and_alternate_names(
        self,
    ):
        sync, db = _make_session()
        _seed_six_canonical_clubs(sync)
        # 1. Retired name with a spelling that is NOT a prefix ("Spurs" -> 146)
        sync.add(
            RetiredTeamRedirect(
                retired_team_id=14545,
                retired_slug="spurs",
                retired_name="Spurs",
                sport_id=1,
                canonical_team_id=146,
                reason="fold_13229",
            )
        )
        # 2. team_identity_mapping alias ("Magpies" -> 143)
        sync.add(
            TeamIdentityMapping(
                team_id=143,
                source="odds_api",
                source_name="Magpies",
                sport_key="soccer_epl",
            )
        )
        # 3. Team.alternate_names alias ("Tricky Trees" -> 2)
        forest = sync.execute(select(Team).where(Team.id == 2)).scalar_one()
        forest.alternate_names = ["Tricky Trees"]
        sync.commit()

        r1 = await find_existing_team_in_sport(db, "Spurs", 1)
        r2 = await find_existing_team_in_sport(db, "Magpies", 1)
        r3 = await find_existing_team_in_sport(db, "Tricky Trees", 1)
        assert r1 is not None and r1.id == 146
        assert r2 is not None and r2.id == 143
        assert r3 is not None and r3.id == 2


class TestNearestWrongNeighboursNeverCollapse:
    @pytest.mark.parametrize(
        "candidate,existing_name",
        [
            ("Columbus Crew 2", "Columbus Crew SC"),
            ("LA Galaxy II", "LA Galaxy"),
            ("Real Sociedad B", "Real Sociedad"),
            ("Chelsea FC Women", "Chelsea"),
            ("Arsenal Reserves", "Arsenal"),
            ("Massachusetts Minutewomen", "Massachusetts Minutemen"),
            ("San Jose Earthquakes II", "San Jose Earthquakes"),
        ],
    )
    def test_reserve_and_womens_sides_never_collapse_into_first_team(
        self, candidate, existing_name
    ):
        assert not distinguishing_tokens_agree(candidate, existing_name)
        existing = SimpleNamespace(
            id=1, name=existing_name, alternate_names=[existing_name]
        )
        assert unambiguous_short_spelling_match(candidate, [existing]) is None

    def test_ambiguous_city_and_mascot_never_collapse(self):
        epl_manchester = [
            SimpleNamespace(id=10, name="Manchester City", alternate_names=["Manchester"]),
            SimpleNamespace(id=11, name="Manchester United", alternate_names=["Manchester"]),
        ]
        assert unambiguous_short_spelling_match("Manchester", epl_manchester) is None

        mlb_ny = [
            SimpleNamespace(id=20, name="New York Yankees", alternate_names=["New York"]),
            SimpleNamespace(id=21, name="New York Mets", alternate_names=["New York"]),
        ]
        assert unambiguous_short_spelling_match("New York", mlb_ny) is None

        ncaab_tigers = [
            SimpleNamespace(id=30, name="LSU Tigers", alternate_names=["Tigers"]),
            SimpleNamespace(id=31, name="Auburn Tigers", alternate_names=["Tigers"]),
        ]
        assert unambiguous_short_spelling_match("Tigers", ncaab_tigers) is None

    def test_school_word_skipped_club_still_counts_for_ambiguity_paris(self):
        # Fable verdict on #13293: "Saint" is on _SCHOOL_MODIFIER_WORDS, so
        # skipping Paris Saint-Germain before counting prefix matches used to
        # leave Paris FC as a false sole match for "Paris".
        ligue1_paris = [
            SimpleNamespace(id=35, name="Paris Saint-Germain", alternate_names=None),
            SimpleNamespace(id=36, name="Paris FC", alternate_names=None),
        ]
        assert unambiguous_short_spelling_match("Paris", ligue1_paris) is None

    @pytest.mark.parametrize(
        "short_school,other_school",
        [
            ("Georgia", "Georgia Tech Yellow Jackets"),
            ("Michigan", "Michigan State Spartans"),
            ("Texas", "Texas A&M Aggies"),
            ("Louisiana", "Louisiana Tech Bulldogs"),
            ("Kansas", "Kansas State Wildcats"),
            # Fable verdict on #13293: school-word test must run at any name length.
            ("North Dakota", "North Dakota State Bison"),
            ("North Carolina", "North Carolina State Wolfpack"),
            ("San Diego", "San Diego State Aztecs"),
        ],
    )
    def test_school_modifier_traps_never_collapse(self, short_school, other_school):
        existing = SimpleNamespace(id=40, name=other_school, alternate_names=None)
        assert unambiguous_short_spelling_match(short_school, [existing]) is None

    @pytest.mark.asyncio
    async def test_site2_still_allows_reserve_side_as_distinct_team_row(self):
        sync, db = _make_session()
        _seed_six_canonical_clubs(sync)
        sync.add(
            Team(
                id=22,
                sport_id=3,
                name="Columbus Crew SC",
                slug="columbus-crew-sc-mls",
                espn_id="183",
            )
        )
        sync.commit()

        created = await _auto_create_missing_teams(
            db, 3, "soccer_usa_mls", {"Columbus Crew 2"}
        )
        assert created == 1
        mls_names = {
            t.name
            for t in sync.execute(select(Team).where(Team.sport_id == 3)).scalars().all()
        }
        assert "Columbus Crew SC" in mls_names
        assert "Columbus Crew 2" in mls_names

    @pytest.mark.asyncio
    async def test_site1_still_refuses_wrong_event_espn_payload_6215(self):
        sync, db = _make_session()
        _seed_six_canonical_clubs(sync)
        sync.add(
            Team(
                id=133,
                sport_id=1,
                name="Arsenal",
                slug="arsenal-epl",
                espn_id="359",
                abbreviation="ARS",
            )
        )
        sync.commit()
        before_count = len(sync.execute(select(Team)).scalars().all())

        arsenal_espn = SimpleNamespace(
            espn_id="359",
            name="Arsenal",
            display_name="Arsenal",
            short_name="Arsenal",
            nickname="Arsenal",
            abbreviation="ARS",
            primary_color="EF0107",
            secondary_color="FFFFFF",
            logo_url=None,
            logo_url_dark=None,
            record="19-7-3",
            location="Arsenal",
        )
        res = await upsert_team(db, "Fluminense", arsenal_espn, 1)
        assert res is None
        assert len(sync.execute(select(Team)).scalars().all()) == before_count

    @pytest.mark.asyncio
    async def test_cross_league_isolation(self):
        sync, db = _make_session()
        _seed_six_canonical_clubs(sync)
        # "Ottawa Senators" lives in sport_id=2 (NHL), not sport_id=1 (EPL)
        assert await find_existing_team_in_sport(db, "Ottawa", sport_id=1) is None
        found = await find_existing_team_in_sport(db, "Ottawa", sport_id=2)
        assert found is not None and found.id == 56
