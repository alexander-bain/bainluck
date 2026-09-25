"""A Cardinals game gets one row, whatever StatPal's livescores calls the club. #4865.

PILLAR: MATCHING. SHIP: searching "cardinals" stops serving a second copy of a
finished game that reads "No result reported" while ESPN says Final.

THE DEFECT, as it shipped
═════════════════════════
``_sync_statpal_schedules`` creates rows for live fixtures it cannot find, and
claimed them with ``live_fix.fixture_id``. On MLB that is ``livescores.id`` — a
space ``season-schedule`` never publishes (``STATPAL_LIVE_ANCHOR_FIELD``) — so
the minted row held an id no other row would ever hold, and the id-keyed drain
could never pair it. The only check in front of the mint was exact lower-case
name equality, and StatPal sometimes spells the club ``St.Louis Cardinals``.

Production, 2026-09-25: four Cardinals games (9/13, 9/19, 9/20, 9/23) carried a
second, StatPal-only row with a ten-digit livescores id. In all four, the ESPN
row already held the season-schedule id the live row's ``oddsid`` names —
15317596 had ``366716`` since 9/18, the second row was minted 9/23 08:02Z.

THE RULE
════════
The live-create claims with the sport's declared anchor (``_live_anchor_id``),
looks that id up first, and refuses when a declared sport's row lacks it. No
name matching is added or loosened — this is an id lookup (ruling 048).
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.ext.compiler import compiles


@compiles(JSONB, "sqlite")
def _jsonb_on_sqlite(type_, compiler, **kw):  # pragma: no cover - DDL shim
    return "JSON"


@compiles(ARRAY, "sqlite")
def _array_on_sqlite(type_, compiler, **kw):  # pragma: no cover - DDL shim
    return "JSON"


MLB = "baseball_mlb"
SEASON_ID = "366716"  # season-schedule id, stamped on the ESPN row
LIVESCORES_ID = "1329192831"  # livescores `id` — the space never to be written


class _AsyncShim:
    def __init__(self, session):
        self._s = session

    async def execute(self, *a, **kw):
        return self._s.execute(*a, **kw)

    async def flush(self, *a, **kw):
        return self._s.flush(*a, **kw)

    async def commit(self):
        return self._s.commit()

    async def rollback(self):
        return self._s.rollback()

    def add(self, obj):
        return self._s.add(obj)

    def __getattr__(self, name):
        return getattr(self._s, name)


def _wire(monkeypatch, now, *, stamped: bool = True):
    """The 9/23 specimen: the ESPN row, spelled `St. Louis`, holding the season id."""
    from sqlalchemy import create_engine
    from sqlalchemy import event as sa_event
    from sqlalchemy.orm import Session

    import app.tasks.base as task_base
    from app.models.models import Base, Event, Sport, Team, TeamIdentityMapping

    engine = create_engine("sqlite://")
    Base.metadata.create_all(
        engine,
        tables=[
            Event.__table__,
            Sport.__table__,
            Team.__table__,
            TeamIdentityMapping.__table__,
        ],
    )
    session = Session(engine, expire_on_commit=False)
    sport = Sport(key=MLB, name="MLB")
    session.add(sport)
    session.flush()
    espn_row = Event(
        sport_id=sport.id,
        home_team_name="Pittsburgh Pirates",
        away_team_name="St. Louis Cardinals",
        commence_time=now + timedelta(hours=14),
        status="scheduled",
        statpal_fixture_id=SEASON_ID if stamped else None,
        espn_id="401817048",
    )
    session.add(espn_row)
    session.commit()

    @sa_event.listens_for(session, "loaded_as_persistent")
    def _reattach_utc(_sess, instance):  # pragma: no cover - test rail
        for attr, value in list(instance.__dict__.items()):
            if isinstance(value, datetime) and value.tzinfo is None:
                instance.__dict__[attr] = value.replace(tzinfo=timezone.utc)

    class _Ctx:
        async def __aenter__(self_inner):
            return _AsyncShim(session)

        async def __aexit__(self_inner, exc_type, *_):
            if exc_type is not None:
                session.rollback()
                return False
            session.commit()
            return False

    monkeypatch.setattr(task_base, "get_task_session", lambda: _Ctx())
    monkeypatch.setattr(
        "app.tasks.statpal_sync.get_task_session", lambda: _Ctx(), raising=False
    )
    return session, espn_row.id


def _stub_service(monkeypatch, now, *, odds_id):
    """No schedule rows; livescores serves the game the way it did at 08:02Z."""
    import app.services.statpal_api as statpal_api

    live = [
        statpal_api.StatPalFixture(
            fixture_id=LIVESCORES_ID,
            odds_id=odds_id,
            home_team="Pittsburgh Pirates",
            away_team="St.Louis Cardinals",
            start_time=now + timedelta(hours=14),
            status="not_started",
        )
    ]

    class _Service:
        async def get_fixtures(self, sport):
            return []

        async def get_fixtures_result(self, sport):
            return statpal_api.StatPalFixtureFetch([], "ok", sport, "season-schedule")

        async def get_live_scores(self, sport):
            return list(live)

        async def close(self):
            return None

    monkeypatch.setattr(statpal_api, "is_available", lambda: True)
    monkeypatch.setattr(statpal_api, "StatPalAPIService", lambda *a, **kw: _Service())


def _record_creates(monkeypatch):
    """Stand in for the registry: record every claim the live-create hands it."""
    import app.services.event_registry as event_registry

    claims: list[str] = []

    async def _fake_find_or_create(session, identity):
        claims.append(identity.claim.source_id)
        return object(), False

    monkeypatch.setattr(event_registry, "find_or_create_event", _fake_find_or_create)
    return claims


@pytest.mark.asyncio
async def test_the_specimen_is_not_minted_a_second_row(monkeypatch):
    """The ship: the anchor names the ESPN row, so nothing reaches the registry."""
    from app.tasks.statpal_sync import _sync_statpal_schedules

    now = datetime.now(timezone.utc)
    _wire(monkeypatch, now)
    _stub_service(monkeypatch, now, odds_id=SEASON_ID)
    claims = _record_creates(monkeypatch)

    result = await _sync_statpal_schedules(MLB)

    assert claims == [], f"the live-create still asked the registry for {claims}"
    assert result["live_create_skipped_anchor_known"] == 1
    assert result["live_created_refused_no_anchor"] == 0


@pytest.mark.asyncio
async def test_the_rail_sees_the_shipped_defect(monkeypatch):
    """THE CONTROL. With MLB's anchor declaration removed the path falls back to
    `livescores.id` — the shipped behaviour — and the rail must see the mint
    reach the registry with that id. Otherwise the test above proves nothing."""
    import app.tasks.statpal_sync as statpal_sync

    now = datetime.now(timezone.utc)
    _wire(monkeypatch, now)
    _stub_service(monkeypatch, now, odds_id=SEASON_ID)
    claims = _record_creates(monkeypatch)
    monkeypatch.setattr(statpal_sync, "STATPAL_LIVE_ANCHOR_FIELD", {})

    await statpal_sync._sync_statpal_schedules(MLB)

    assert claims == [LIVESCORES_ID]


@pytest.mark.asyncio
async def test_an_unmatched_game_is_claimed_by_its_season_id(monkeypatch):
    """No row holds the anchor yet: the row may still be created (the gap this
    path fills is real), but under the season id, so the drain can pair it."""
    from app.tasks.statpal_sync import _sync_statpal_schedules

    now = datetime.now(timezone.utc)
    _wire(monkeypatch, now, stamped=False)
    _stub_service(monkeypatch, now, odds_id=SEASON_ID)
    claims = _record_creates(monkeypatch)

    result = await _sync_statpal_schedules(MLB)

    assert claims == [SEASON_ID]
    assert result["live_create_skipped_anchor_known"] == 0


@pytest.mark.asyncio
async def test_a_live_row_without_its_anchor_is_refused_and_counted(monkeypatch):
    """No `oddsid`: the livescores id is the only id in hand and must not be
    written. Refused, counted — never minted in the wrong space."""
    from app.tasks.statpal_sync import _sync_statpal_schedules

    now = datetime.now(timezone.utc)
    _wire(monkeypatch, now, stamped=False)
    _stub_service(monkeypatch, now, odds_id=None)
    claims = _record_creates(monkeypatch)

    result = await _sync_statpal_schedules(MLB)

    assert claims == []
    assert result["live_created_refused_no_anchor"] == 1
