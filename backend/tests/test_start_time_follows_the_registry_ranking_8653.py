"""#8653 — a game's page shows the real first-pitch time, not StatPal's stale one.

WHAT A READER SAW
=================
Production, 2026-09-25 16:50Z, `https://bainluck.com/events/15318545` at 390px:

    Sep 25, 2026 · 3:05 PM PDT          Starts in 5h 33m
    Red Sox  49% – 51%  Cubs

Cubs @ Red Sox doubleheader game 2. MLB (`824706`) had it at 21:35Z, ESPN
(`401817074`) at 21:30Z. Our row said 22:05Z, `commence_time_source='statpal'`
— StatPal's season-schedule (`366748`) still carried the pre-reschedule time.

WHY ESPN'S CORRECT TIME NEVER LANDED
====================================
The registry's one start-time rule ranks `odds_api 1 < statpal 2 < espn 3 <
mlb_schedule_repair 4` (`event_registry.commence_time_write_authorized`, #2018).
Two writers bypassed it: ESPN's correction hard-coded `!= "statpal"` (deferring
to the provider it outranks), and StatPal's schedule pass overwrote any start
more than five minutes off with no check at all. Both now ask
`utils.start_time_authority.provider_may_set_start`, which IS the registry rule.

Measured before building: 7 rows held a `statpal` start AND an `espn_id`
(now-1d .. now+10d); 6 agreed with ESPN to the minute, 1 did not — this one.
"""

from __future__ import annotations

import asyncio
import inspect
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import event as sa_event
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.ext.compiler import compiles

from app.services.event_registry import (
    _SOURCE_PRIORITY,
    commence_time_write_authorized,
)
from app.utils.start_time_authority import provider_may_set_start


@compiles(JSONB, "sqlite")
def _jsonb_on_sqlite(type_, compiler, **kw):  # pragma: no cover - DDL shim
    return "JSON"


@compiles(ARRAY, "sqlite")
def _array_on_sqlite(type_, compiler, **kw):  # pragma: no cover - DDL shim
    return "JSON"


#: The specimen, verbatim from production.
OUR_STALE_START = datetime(2026, 9, 25, 22, 5, tzinfo=timezone.utc)   # StatPal 366748
ESPN_START = datetime(2026, 9, 25, 21, 30, tzinfo=timezone.utc)       # ESPN 401817074
SPECIMEN_ESPN_ID = "401817074"


# ─────────────────────────────────────────────────────────────────────────────
# 1. The predicate IS the registry rule — one implementation, not a second one
# ─────────────────────────────────────────────────────────────────────────────


class TestThePredicateIsTheRegistryRule:
    @pytest.mark.parametrize(
        "current,incoming,expected",
        [
            # The specimen: ESPN outranks StatPal.
            ("statpal", "espn", True),
            # The reverse: StatPal may no longer overwrite ESPN.
            ("espn", "statpal", False),
            # A provider revising its own stamp — what both rails did before.
            ("espn", "espn", True),
            ("statpal", "statpal", True),
            # Unchanged: both outrank the Odds API and an unstamped row.
            ("odds_api", "espn", True),
            ("odds_api", "statpal", True),
            (None, "espn", True),
            (None, "statpal", True),
            # MLB's own published schedule outranks every poller.
            ("mlb_schedule_repair", "espn", False),
            ("mlb_schedule_repair", "statpal", False),
        ],
    )
    def test_the_ranking(self, current, incoming, expected):
        assert provider_may_set_start(current, incoming) is expected

    def test_it_agrees_with_the_registry_on_every_known_pair(self):
        """If the registry's ranking moves, this predicate moves with it."""
        sources = [None, *sorted(_SOURCE_PRIORITY)]
        for current in sources:
            for incoming in sorted(_SOURCE_PRIORITY):
                registry, _ = commence_time_write_authorized(
                    current, incoming,
                    same_record_revision=current == incoming,
                )
                assert provider_may_set_start(current, incoming) is registry, (
                    current, incoming,
                )


# ─────────────────────────────────────────────────────────────────────────────
# 2. ESPN's scheduled pass — the site that corrects a game before first pitch
# ─────────────────────────────────────────────────────────────────────────────


class _Row:
    """A stand-in ORM row: any column not named here reads as NULL."""

    def __init__(self, **fields):
        self.__dict__.update(fields)

    def __getattr__(self, _name):
        return None


def _run_scheduled_pass(monkeypatch, *, commence_time_source, our_start=OUR_STALE_START):
    from app.utils import espn_helpers

    class _Team(_Row):
        def __init__(self, name):
            super().__init__(display_name=name, name=name)

    class _Sport:
        id = 53232
        key = "baseball_mlb"

    event = _Row(
        id=15318545,
        espn_id=SPECIMEN_ESPN_ID,
        sport=_Sport(),
        sport_id=_Sport.id,
        home_team_name="Boston Red Sox",
        away_team_name="Chicago Cubs",
        home_team_normalized=None,
        away_team_normalized=None,
        home_team_id=1,
        away_team_id=2,
        commence_time=our_start,
        commence_time_source=commence_time_source,
        broadcast_info=None,
        llm_importance=None,
        status="scheduled",
    )
    ee = _Row(
        espn_id=SPECIMEN_ESPN_ID,
        home_team=_Team("Boston Red Sox"),
        away_team=_Team("Chicago Cubs"),
        date=ESPN_START,
        broadcasts=[],
        season_type=None,
    )

    class _Result:
        def __init__(self, rows):
            self._rows = rows

        def scalars(self):
            return self

        def all(self):
            return self._rows

    calls = {"n": 0}

    class _Session:
        async def execute(self, *_a, **_k):
            calls["n"] += 1
            return _Result([event] if calls["n"] == 1 else [])

    async def _noop(*_a, **_k):
        return None

    monkeypatch.setattr(espn_helpers, "upsert_team", _noop)
    monkeypatch.setattr(espn_helpers, "register_espn_team_identities", _noop)
    stats: dict = {}
    loop = asyncio.new_event_loop()
    try:
        loop.run_until_complete(
            espn_helpers.sync_scheduled_events(
                _Session(), "baseball_mlb", [ee], stats,
            )
        )
    finally:
        loop.close()
    return event


class TestEspnScheduledPass:
    def test_the_specimen_takes_espns_start(self, monkeypatch):
        """THE GUARD. 22:05Z stamped `statpal` becomes ESPN's 21:30Z."""
        event = _run_scheduled_pass(monkeypatch, commence_time_source="statpal")
        assert event.commence_time == ESPN_START, (
            "ESPN outranks StatPal in the registry's start-time ranking; a stale "
            "StatPal start must not lock ESPN's correction out (#8653). "
            f"Got {event.commence_time}."
        )
        assert event.commence_time_source == "espn"

    def test_espn_still_revises_its_own_start(self, monkeypatch):
        event = _run_scheduled_pass(monkeypatch, commence_time_source="espn")
        assert event.commence_time == ESPN_START

    def test_espn_still_corrects_an_odds_start(self, monkeypatch):
        event = _run_scheduled_pass(monkeypatch, commence_time_source="odds_api")
        assert event.commence_time == ESPN_START

    def test_mlbs_own_schedule_is_not_overwritten(self, monkeypatch):
        """The control on the other side of the ranking: a refusal still refuses."""
        event = _run_scheduled_pass(
            monkeypatch, commence_time_source="mlb_schedule_repair",
        )
        assert event.commence_time == OUR_STALE_START
        assert event.commence_time_source == "mlb_schedule_repair"


# ─────────────────────────────────────────────────────────────────────────────
# 3. ESPN's live pass — same rule, driven through the real writer on a real DB
# ─────────────────────────────────────────────────────────────────────────────


class _AsyncShim:
    def __init__(self, inner):
        self._s = inner

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


def _utc_on_load(session):
    @sa_event.listens_for(session, "loaded_as_persistent")
    def _reattach_utc(_sess, instance):  # pragma: no cover - test rail
        for attr, value in list(instance.__dict__.items()):
            if isinstance(value, datetime) and value.tzinfo is None:
                instance.__dict__[attr] = value.replace(tzinfo=timezone.utc)


def _live_pass(commence_time_source):
    """One ESPN live update on a live row whose start is 35 minutes late."""
    from sqlalchemy import create_engine, select
    from sqlalchemy.orm import Session

    from app.models.models import (
        Base, ESPNSnapshot, Event, ScoreSnapshot, Sport, WinProbSnapshot,
    )
    from app.services.espn_api import ESPNEvent, ESPNTeam
    from app.utils.espn_helpers import update_event_fields_from_espn

    engine = create_engine("sqlite://")
    Base.metadata.create_all(
        engine,
        tables=[
            Event.__table__, Sport.__table__, ScoreSnapshot.__table__,
            ESPNSnapshot.__table__, WinProbSnapshot.__table__,
        ],
    )
    session = Session(engine, expire_on_commit=False)
    _utc_on_load(session)

    sport = Sport(key="baseball_mlb", name="MLB")
    session.add(sport)
    session.flush()
    # Offset first, then truncate (gotcha #44): the anchor never branches on
    # the clock.
    espn_start = (datetime.now(timezone.utc) - timedelta(hours=1)).replace(
        second=0, microsecond=0,
    )
    our_start = espn_start + timedelta(minutes=35)
    row = Event(
        sport_id=sport.id,
        home_team_name="Boston Red Sox",
        away_team_name="Chicago Cubs",
        commence_time=our_start,
        commence_time_source=commence_time_source,
        status="live",
        espn_id=SPECIMEN_ESPN_ID,
        win_probability_sources={},
    )
    session.add(row)
    session.commit()

    def _team(espn_id, display, short, abbr):
        return ESPNTeam(
            espn_id=espn_id, name=short, abbreviation=abbr,
            display_name=display, short_name=short, nickname=short,
            primary_color=None, secondary_color=None, logo_url=None,
            logo_url_dark=None, record=None, location=display.rsplit(" ", 2)[0],
        )

    ee = ESPNEvent(
        espn_id=SPECIMEN_ESPN_ID,
        name="Chicago Cubs at Boston Red Sox",
        short_name="CHC @ BOS",
        date=espn_start,
        status="in",
        status_detail="Top 2nd",
        period=2,
        clock=None,
        home_team=_team("2", "Boston Red Sox", "Red Sox", "BOS"),
        away_team=_team("16", "Chicago Cubs", "Cubs", "CHC"),
        home_score=0,
        away_score=0,
        venue=None,
        broadcasts=[],
        home_win_probability=None,
    )
    loop = asyncio.new_event_loop()
    try:
        loop.run_until_complete(
            update_event_fields_from_espn(_AsyncShim(session), row, ee, set(), {})
        )
    finally:
        loop.close()
    session.commit()
    session.expunge_all()
    got = session.execute(select(Event)).scalar_one()
    return got, espn_start, our_start


class TestEspnLivePass:
    def test_a_statpal_start_takes_espns(self):
        got, espn_start, _ = _live_pass("statpal")
        assert got.commence_time == espn_start
        assert got.commence_time_source == "espn"

    def test_mlbs_own_schedule_is_not_overwritten(self):
        got, _, our_start = _live_pass("mlb_schedule_repair")
        assert got.commence_time == our_start
        assert got.commence_time_source == "mlb_schedule_repair"


# ─────────────────────────────────────────────────────────────────────────────
# 4. StatPal's schedule pass — the writer that stamped `statpal` over everything
# ─────────────────────────────────────────────────────────────────────────────

MLB = "baseball_mlb"
#: One fixture per row, each 35 minutes off the row's start.
FIXTURES = {
    "366748": "espn",               # the specimen's shape: ESPN already right
    "366749": "statpal",            # StatPal revising its own stamp
    "366750": "odds_api",           # StatPal outranks the Odds API
    "366751": None,                 # never stamped: StatPal corrects
    "366752": "mlb_schedule_repair",  # the league's own time: refused
}


def _wire_statpal(monkeypatch):
    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session

    import app.services.statpal_api as statpal_api
    import app.tasks.base as task_base
    from app.models.models import Base, Event, Sport, Team, TeamIdentityMapping

    engine = create_engine("sqlite://")
    Base.metadata.create_all(
        engine,
        tables=[
            Event.__table__, Sport.__table__, Team.__table__,
            TeamIdentityMapping.__table__,
        ],
    )
    session = Session(engine, expire_on_commit=False)
    sport = Sport(key=MLB, name="MLB")
    session.add(sport)
    session.flush()

    # Past games, like the #4307 rail: the pass enriches them by fixture id.
    ours = (datetime.now(timezone.utc) - timedelta(hours=3)).replace(
        second=0, microsecond=0,
    )
    statpal_start = ours + timedelta(minutes=35)
    ids = {}
    for i, (fid, stamp) in enumerate(FIXTURES.items()):
        row = Event(
            sport_id=sport.id,
            home_team_name=f"Home {i}",
            away_team_name=f"Away {i}",
            commence_time=ours,
            commence_time_source=stamp,
            status="live",
            statpal_fixture_id=fid,
        )
        session.add(row)
        session.flush()
        ids[fid] = row.id
    session.commit()
    _utc_on_load(session)

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

    fixtures = [
        statpal_api.StatPalFixture(
            fixture_id=fid,
            home_team=f"Home {i}",
            away_team=f"Away {i}",
            start_time=statpal_start,
            status="finished",
        )
        for i, fid in enumerate(FIXTURES)
    ]

    class _Service:
        async def get_fixtures(self, sport):
            return list(fixtures)

        async def get_fixtures_result(self, sport):
            return statpal_api.StatPalFixtureFetch(
                list(fixtures), "ok", sport, "season-schedule"
            )

        async def get_live_scores(self, sport):
            return []

        async def close(self):
            return None

    monkeypatch.setattr(statpal_api, "is_available", lambda: True)
    monkeypatch.setattr(statpal_api, "StatPalAPIService", lambda *a, **kw: _Service())
    return session, ids, ours, statpal_start


@pytest.mark.asyncio
async def test_statpal_writes_only_where_the_ranking_lets_it(monkeypatch):
    """THE GUARD for the writer that caused the lock-out."""
    from app.models.models import Event
    from app.tasks.statpal_sync import _sync_statpal_schedules

    session, ids, ours, statpal_start = _wire_statpal(monkeypatch)
    result = await _sync_statpal_schedules(MLB)
    session.expunge_all()

    def row(fid):
        return session.get(Event, ids[fid])

    # Refused: ESPN's start and the league's own are not StatPal's to replace.
    for fid in ("366748", "366752"):
        got = row(fid)
        assert got.commence_time == ours, (
            f"{FIXTURES[fid]}-stamped start was overwritten by StatPal (#8653)"
        )
        assert got.commence_time_source == FIXTURES[fid]
    # Written: its own stamp, the Odds API's, and an unstamped row.
    for fid in ("366749", "366750", "366751"):
        got = row(fid)
        assert got.commence_time == statpal_start, (FIXTURES[fid], got.commence_time)
        assert got.commence_time_source == "statpal"

    assert result.get("schedule_commence_outranked") == 2, (
        "A refused correction is counted, not silent. Got: "
        f"{result.get('schedule_commence_outranked')!r}"
    )


# ─────────────────────────────────────────────────────────────────────────────
# 5. No writer keeps its own private deference
# ─────────────────────────────────────────────────────────────────────────────


def test_no_espn_start_write_defers_to_statpal_by_name():
    from app.utils import espn_helpers

    src = inspect.getsource(espn_helpers)
    assert "!= \"statpal\"" not in src and "!= 'statpal'" not in src, (
        "ESPN's start correction must ask the registry's ranking "
        "(`provider_may_set_start`), not defer to StatPal by name (#8653)"
    )
    for fn in (
        espn_helpers.update_event_fields_from_espn,
        espn_helpers.sync_scheduled_events,
    ):
        assert 'provider_may_set_start(' in inspect.getsource(fn), fn.__name__


def test_every_espn_start_rail_asks_the_ranking_and_none_names_statpal():
    """The three ESPN start-time rails #8655 did not reach carried the same
    upside-down "StatPal outranks ESPN" refusal, each citing another as its
    source. They now make the same call; none may compare against StatPal by
    name again."""
    from app.tasks import espn_sync
    from app.utils import anchor_schedule, espn_tennis_anchor

    for module in (anchor_schedule, espn_sync, espn_tennis_anchor):
        src = inspect.getsource(module)
        for needle in (
            '== "statpal"', "== 'statpal'", '!= "statpal"', "!= 'statpal'",
            "COMMENCE_SOURCE_STATPAL", "REFUSED_STATPAL",
        ):
            assert needle not in src, (module.__name__, needle)
    for fn in (
        anchor_schedule.schedule_decision,
        espn_sync._recover_unstarted_authority_fixtures,
        espn_tennis_anchor.authority_write,
    ):
        assert "provider_may_set_start(" in inspect.getsource(fn), fn.__name__
