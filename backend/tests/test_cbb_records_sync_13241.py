"""#13241 — college basketball full-slate pregame fetch and standings record sync.

Follow-up 1 from #13241: ~95 college basketball teams (50 women's, 45 men's)
still held prior-season records (e.g. UAB 18-11, Sacramento State 15-17,
Boston College 21-5) and showed blank records once prior-season records were
refused.

Root causes fixed here:
1. ``ESPN_FULL_SLATE_GROUPS`` only included ``americanfootball_ncaaf`` ("80").
   ESPN's undated men's/women's college basketball scoreboards only return ~5-6
   featured games, whereas ``?groups=50`` returns the full D-I slate.
2. No periodic job refreshed ``Team.current_record`` from ESPN's v2 standings
   endpoint (which returns every D-I school's current-season record in one
   request per league and already refuses preseason tables).

Safety invariants pinned below:
- ``_sync_espn_standings_records`` NEVER creates any ``Team`` row; it updates
  ``current_record`` only on existing rows matching ``(sport_id, espn_id)``.
- ESPN dark (``None``) and preseason/empty (``records == {}``) responses leave
  existing rows untouched.
- Both men's and women's college basketball pass ``groups="50"`` on pre-game
  full-slate fetches, while unrelated sports remain unchanged.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import sessionmaker

from app.models.models import Sport, Team


@compiles(JSONB, "sqlite")
def _compile_jsonb_sqlite(_type, _compiler, **_kw):
    return "JSON"


class _AsyncSessionAdapter:
    def __init__(self, sync_session):
        self._s = sync_session

    def add(self, obj):
        return self._s.add(obj)

    def add_all(self, objs):
        return self._s.add_all(objs)

    async def execute(self, stmt, params=None):
        if params is not None:
            return self._s.execute(stmt, params)
        return self._s.execute(stmt)

    async def flush(self):
        return self._s.flush()

    async def commit(self):
        return self._s.commit()

    async def rollback(self):
        return self._s.rollback()

    async def close(self):
        return self._s.close()


def _make_session_factory():
    engine = create_engine("sqlite:///:memory:")
    Sport.__table__.create(engine)
    Team.__table__.create(engine)
    sync_factory = sessionmaker(engine, expire_on_commit=False)

    @asynccontextmanager
    async def _open():
        sess = sync_factory()
        try:
            yield _AsyncSessionAdapter(sess)
        finally:
            sess.close()

    return engine, _open


class TestCollegeBasketballFullSlateGroups:
    def test_both_cbb_leagues_use_division_i_group_50(self):
        from app.services.espn_api import ESPN_FULL_SLATE_GROUPS

        assert ESPN_FULL_SLATE_GROUPS["basketball_ncaab"] == "50"
        assert ESPN_FULL_SLATE_GROUPS["basketball_wncaab"] == "50"
        assert ESPN_FULL_SLATE_GROUPS["americanfootball_ncaaf"] == "80"

    @pytest.mark.asyncio
    async def test_fetch_full_slate_boards_requests_groups_50_for_both_cbb_leagues(self):
        from app.tasks.espn_sync import _fetch_full_slate_boards

        calls: list[tuple[str, str | None]] = []

        class _FakeESPN:
            async def get_scoreboard(self, sport_key, date=None, groups=None):
                calls.append((sport_key, groups))
                return [SimpleNamespace(espn_id=f"{sport_key}-1")]

        stats: dict = {"errors": []}
        boards = await _fetch_full_slate_boards(
            _FakeESPN(),
            ["basketball_ncaab", "basketball_wncaab", "basketball_nba"],
            stats,
        )

        assert calls == [
            ("basketball_ncaab", "50"),
            ("basketball_wncaab", "50"),
        ]
        assert set(boards.keys()) == {"basketball_ncaab", "basketball_wncaab"}
        assert stats["errors"] == []

    @pytest.mark.asyncio
    async def test_get_scoreboard_url_appends_groups_50_for_cbb(self, monkeypatch):
        from app.services import espn_api

        seen: list[str] = []

        async def _fake_get(self, url, *args, **kwargs):
            seen.append(url)
            return {"events": []}

        monkeypatch.setattr(espn_api.ESPNAPIService, "_get", _fake_get)
        svc = espn_api.ESPNAPIService()
        try:
            await svc.get_scoreboard("basketball_ncaab", groups="50")
            await svc.get_scoreboard("basketball_wncaab", groups="50")
        finally:
            await svc.close()

        assert len(seen) == 2
        assert seen[0].endswith("/basketball/mens-college-basketball/scoreboard?groups=50")
        assert seen[1].endswith("/basketball/womens-college-basketball/scoreboard?groups=50")


class TestSyncEspnStandingsRecords:
    @pytest.mark.asyncio
    async def test_updates_existing_cbb_rows_by_espn_id_and_creates_zero_teams(
        self, monkeypatch
    ):
        from app.tasks import espn_sync

        engine, open_session = _make_session_factory()
        try:
            async with open_session() as seed:
                ncaab = Sport(
                    key="basketball_ncaab",
                    name="NCAAB",
                    group="Basketball",
                )
                wncaab = Sport(
                    key="basketball_wncaab",
                    name="WNCAAB",
                    group="Basketball",
                )
                seed.add_all([ncaab, wncaab])
                await seed.flush()

                uab = Team(
                    sport_id=ncaab.id,
                    name="UAB Blazers",
                    slug="uab-blazers",
                    espn_id="5",
                    current_record="18-11",  # stale prior-season record
                )
                sac_state = Team(
                    sport_id=ncaab.id,
                    name="Sacramento State Hornets",
                    slug="sacramento-state-hornets",
                    espn_id="16",
                    current_record="15-17",  # stale prior-season record
                )
                bc_women = Team(
                    sport_id=wncaab.id,
                    name="Boston College Eagles",
                    slug="boston-college-eagles-w",
                    espn_id="103",
                    current_record="21-5",  # stale prior-season record
                )
                already_current = Team(
                    sport_id=wncaab.id,
                    name="UConn Huskies",
                    slug="uconn-huskies-w",
                    espn_id="41",
                    current_record="5-0",
                )
                no_espn_id = Team(
                    sport_id=ncaab.id,
                    name="Unanchored Squad",
                    slug="unanchored-squad",
                    espn_id=None,
                    current_record="12-19",
                )
                seed.add_all([uab, sac_state, bc_women, already_current, no_espn_id])
                await seed.commit()

            class _FakeESPN:
                def __init__(self):
                    self.closed = False

                async def get_standings_reading(self, sport_key: str):
                    if sport_key == "basketball_ncaab":
                        return {
                            "claims": {},
                            "records": {
                                "5": "4-2",
                                "16": "3-3",
                                "99999": "6-0",  # unknown ESPN id: must NOT create a team
                                "bad": "not-a-record",
                            },
                        }
                    if sport_key == "basketball_wncaab":
                        return {
                            "claims": {},
                            "records": {
                                "103": "4-1",
                                "41": "5-0",
                                "88888": "5-1",  # unknown ESPN id: must NOT create a team
                            },
                        }
                    return {"claims": {}, "records": {}}

                async def close(self):
                    self.closed = True

            monkeypatch.setattr("app.services.espn_api.ESPNAPIService", _FakeESPN)
            monkeypatch.setattr(espn_sync, "get_task_session", open_session)

            result = await espn_sync._sync_espn_standings_records()

            assert result["status"] == "ok"
            assert result["sports_checked"] == 2
            assert result["sports_dark"] == []
            assert result["sports_empty"] == []
            assert result["teams_matched"] == 4
            assert result["teams_updated"] == 3
            assert result["teams_unchanged"] == 1
            assert result["errors"] == []

            async with open_session() as verify:
                all_teams = (await verify.execute(select(Team))).scalars().all()
                assert len(all_teams) == 5, "must never create a Team row"
                by_slug = {t.slug: t for t in all_teams}
                assert by_slug["uab-blazers"].current_record == "4-2"
                assert by_slug["sacramento-state-hornets"].current_record == "3-3"
                assert by_slug["boston-college-eagles-w"].current_record == "4-1"
                assert by_slug["uconn-huskies-w"].current_record == "5-0"
                assert by_slug["unanchored-squad"].current_record == "12-19"
        finally:
            engine.dispose()

    @pytest.mark.asyncio
    async def test_dark_and_preseason_standings_leave_rows_untouched(self, monkeypatch):
        from app.tasks import espn_sync

        engine, open_session = _make_session_factory()
        try:
            async with open_session() as seed:
                ncaab = Sport(
                    key="basketball_ncaab",
                    name="NCAAB",
                    group="Basketball",
                )
                wncaab = Sport(
                    key="basketball_wncaab",
                    name="WNCAAB",
                    group="Basketball",
                )
                seed.add_all([ncaab, wncaab])
                await seed.flush()
                seed.add_all(
                    [
                        Team(
                            sport_id=ncaab.id,
                            name="Duke Blue Devils",
                            slug="duke-blue-devils",
                            espn_id="150",
                            current_record="5-0",
                        ),
                        Team(
                            sport_id=wncaab.id,
                            name="South Carolina Gamecocks",
                            slug="south-carolina-w",
                            espn_id="2579",
                            current_record="4-0",
                        ),
                    ]
                )
                await seed.commit()

            class _DarkAndPreseasonESPN:
                async def get_standings_reading(self, sport_key: str):
                    if sport_key == "basketball_ncaab":
                        return None  # ESPN dark
                    return {"claims": {}, "records": {}}  # preseason / empty

                async def close(self):
                    pass

            monkeypatch.setattr(
                "app.services.espn_api.ESPNAPIService", _DarkAndPreseasonESPN
            )
            monkeypatch.setattr(espn_sync, "get_task_session", open_session)

            result = await espn_sync._sync_espn_standings_records()

            assert result["status"] == "ok"
            assert result["sports_dark"] == ["basketball_ncaab"]
            assert result["sports_empty"] == ["basketball_wncaab"]
            assert result["teams_updated"] == 0

            async with open_session() as verify:
                by_slug = {
                    t.slug: t.current_record
                    for t in (await verify.execute(select(Team))).scalars().all()
                }
                assert by_slug == {
                    "duke-blue-devils": "5-0",
                    "south-carolina-w": "4-0",
                }
        finally:
            engine.dispose()

    def test_beat_schedule_entry_is_wired_on_background_outside_sweep_window(self):
        from app.tasks import celery_app

        entry = celery_app.conf.beat_schedule["sync-espn-standings-records"]
        assert entry["task"] == "app.tasks.sync_espn_standings_records"
        assert entry["options"]["queue"] == "background"
        # Minute :23 stays clear of the 10:31-10:44 settlement sweep window.
        assert entry["schedule"].minute == {23}
