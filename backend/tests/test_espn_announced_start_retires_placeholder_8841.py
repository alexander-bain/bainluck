"""#8841 equal-instant — ESPN announcing StatPal's placeholder minute retires "TBD".

WHAT IS AT STAKE
================
The Red Sox @ Yankees Wild Card rows (15319235 / 15319236) sit at StatPal's
placeholder 20:00Z with ``provenance:start-placeholder:statpal:<instant>``, so
every reader prints "Sep 29 · TBD". ESPN lists them with ``timeValid=false``.

If ESPN later announces a real start at EXACTLY 20:00Z (4:00 PM ET), none of
ESPN's correction rails fire — they move a row only beyond five minutes — and
the tag still vouches for the unchanged stamp, so a real first pitch would stay
"TBD" forever. And even if ESPN dropped the tag, StatPal's schedule pass writes
it back every run while its ``week[]`` bucket still holds the game on the hour.

The rule: an ESPN reading with an explicit ``timeValid: true`` whose start is
the row's minute drops every start-placeholder tag (other tags untouched) and
takes the stamp as ``espn``; StatPal's pass then withholds the tag from a stamp
an outranking rail vouches for. ``timeValid=false`` and an absent flag vouch
for nothing — the tag stays.
"""

from __future__ import annotations

import asyncio
import json
import os
from datetime import datetime, timedelta, timezone

import pytest

from app.services.espn_api import espn_time_announced, espn_time_valid
from app.utils.espn_start_time import espn_announced_start
from app.utils.start_placeholder import start_is_tbd, start_placeholder_tag

#: The specimen: StatPal's placeholder, and ESPN announcing that same minute.
STAMP = datetime(2026, 9, 29, 20, 0, tzinfo=timezone.utc)
SPECIMEN_ESPN_ID = "401907924"
TAG = start_placeholder_tag(STAMP)
OTHER_TAGS = ["provenance:source:statpal", "provenance:unanchored"]


# ─────────────────────────────────────────────────────────────────────────────
# 1. The parser: only a literal `timeValid: true` is an announcement
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "competition, event_data, announced, valid",
    [
        ({"timeValid": True}, {}, True, True),       # scoreboard shape
        ({}, {"timeValid": True}, True, True),       # summary (header) shape
        ({"timeValid": False}, {}, False, False),    # the specimen today
        ({}, {}, False, True),                       # absent: valid, NOT announced
        ({"timeValid": None}, {}, False, True),
    ],
)
def test_announced_is_explicit_true_only(competition, event_data, announced, valid):
    assert espn_time_announced(competition, event_data) is announced
    assert espn_time_valid(competition, event_data) is valid


class _EE:
    def __init__(self, date, *, time_valid=True, time_announced=False):
        self.date = date
        self.time_valid = time_valid
        self.time_announced = time_announced


def test_announced_start_reader():
    assert espn_announced_start(_EE(STAMP, time_announced=True)) == STAMP
    assert espn_announced_start(_EE(STAMP)) is None                      # absent
    assert espn_announced_start(_EE(STAMP, time_valid=False)) is None    # false
    # a fake with no flag at all (non-ESPNEvent callers) vouches for nothing
    assert espn_announced_start(type("X", (), {"date": STAMP})()) is None


# ─────────────────────────────────────────────────────────────────────────────
# 2. ESPN's live pass — `update_event_fields_from_espn`, on a real (sqlite) row
# ─────────────────────────────────────────────────────────────────────────────


def _live_pass(monkeypatch, *, espn_date, time_valid, time_announced, source="statpal"):
    from sqlalchemy import create_engine, inspect as sa_inspect, select
    from sqlalchemy.orm import Session

    from app.models.models import (
        Base, ESPNSnapshot, Event, ScoreSnapshot, Sport, WinProbSnapshot,
    )
    from app.services.espn_api import ESPNEvent, ESPNTeam
    from app.utils import espn_helpers
    from tests.test_start_time_follows_the_registry_ranking_8653 import (
        _AsyncShim, _utc_on_load,
    )

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
    session.add(Event(
        sport_id=sport.id,
        home_team_name="New York Yankees",
        away_team_name="Boston Red Sox",
        commence_time=STAMP,
        commence_time_source=source,
        status="scheduled",
        espn_id=SPECIMEN_ESPN_ID,
        win_probability_sources={},
        event_tags=[*OTHER_TAGS, TAG],
    ))
    session.commit()
    row = session.execute(select(Event)).scalar_one()

    # The JSONB rewrite is Postgres-only (section 5 runs it for real); here we
    # record that the rail asked for it.
    retired: list[int] = []

    async def _record(_session, event_id):
        retired.append(event_id)

    monkeypatch.setattr(espn_helpers, "retire_start_placeholder_tags", _record)

    def _team(espn_id, display, short, abbr):
        return ESPNTeam(
            espn_id=espn_id, name=short, abbreviation=abbr,
            display_name=display, short_name=short, nickname=short,
            primary_color=None, secondary_color=None, logo_url=None,
            logo_url_dark=None, record=None, location=display.rsplit(" ", 1)[0],
        )

    ee = ESPNEvent(
        espn_id=SPECIMEN_ESPN_ID,
        name="Boston Red Sox at New York Yankees",
        short_name="BOS @ NYY",
        date=espn_date,
        status="scheduled",
        status_detail="Mon, September 29th at 4:00 PM EDT",
        period=None,
        clock=None,
        home_team=_team("10", "New York Yankees", "Yankees", "NYY"),
        away_team=_team("2", "Boston Red Sox", "Red Sox", "BOS"),
        home_score=None,
        away_score=None,
        venue=None,
        broadcasts=[],
        home_win_probability=None,
        season_type=3,
        time_valid=time_valid,
        time_announced=time_announced,
    )
    stats: dict = {}
    asyncio.run(espn_helpers.update_event_fields_from_espn(
        _AsyncShim(session), row, ee, set(), stats
    ))
    in_memory_tags = list(row.event_tags or [])
    dirty_tags = sa_inspect(row).attrs.event_tags.history.has_changes()
    session.commit()
    session.expunge_all()
    stored = session.execute(select(Event)).scalar_one()
    return {
        "row": stored, "retired": retired, "tags": in_memory_tags,
        "dirty_tags": dirty_tags, "stats": stats,
    }


class TestLivePass:
    def test_announced_equal_instant_retires_the_tag(self, monkeypatch):
        """THE GUARD. ESPN says timeValid:true at StatPal's minute → no TBD."""
        got = _live_pass(
            monkeypatch, espn_date=STAMP, time_valid=True, time_announced=True,
        )
        row = got["row"]
        assert got["retired"] == [row.id]
        assert got["tags"] == OTHER_TAGS, "unrelated provenance tags must survive"
        assert start_is_tbd(got["tags"], row.commence_time, row.status) is False
        assert row.commence_time == STAMP
        assert row.commence_time_source == "espn", (
            "ESPN must take the stamp, or StatPal's pass re-tags it next run"
        )
        assert got["dirty_tags"] is False, "in-memory mirror must not re-send tags via ORM"
        assert got["stats"]["espn_start_placeholder_retired"] == 1

    def test_a_second_of_offset_is_still_the_same_minute(self, monkeypatch):
        got = _live_pass(
            monkeypatch, espn_date=STAMP + timedelta(seconds=30),
            time_valid=True, time_announced=True,
        )
        assert got["retired"] == [got["row"].id]

    def test_timevalid_false_at_equal_instant_keeps_it(self, monkeypatch):
        got = _live_pass(
            monkeypatch, espn_date=STAMP, time_valid=False, time_announced=False,
        )
        row = got["row"]
        assert got["retired"] == []
        assert got["tags"] == [*OTHER_TAGS, TAG]
        assert start_is_tbd(got["tags"], row.commence_time, row.status) is True
        assert row.commence_time_source == "statpal"

    def test_timevalid_absent_at_equal_instant_keeps_it(self, monkeypatch):
        got = _live_pass(
            monkeypatch, espn_date=STAMP, time_valid=True, time_announced=False,
        )
        assert got["retired"] == []
        assert got["tags"] == [*OTHER_TAGS, TAG]
        assert got["row"].commence_time_source == "statpal"

    def test_announced_different_minute_is_not_this_rail(self, monkeypatch):
        """3 minutes off: under the correction threshold, and not the same
        instant — the tag no longer vouches for anything ESPN said."""
        got = _live_pass(
            monkeypatch, espn_date=STAMP + timedelta(minutes=3),
            time_valid=True, time_announced=True,
        )
        assert got["retired"] == []
        assert got["row"].commence_time_source == "statpal"

    def test_an_outranking_stamp_is_kept_but_the_tag_still_goes(self, monkeypatch):
        got = _live_pass(
            monkeypatch, espn_date=STAMP, time_valid=True, time_announced=True,
            source="mlb_schedule_repair",
        )
        assert got["retired"] == [got["row"].id]
        assert got["tags"] == OTHER_TAGS
        assert got["row"].commence_time_source == "mlb_schedule_repair"


# ─────────────────────────────────────────────────────────────────────────────
# 3. ESPN's scheduled pass — `sync_scheduled_events`
# ─────────────────────────────────────────────────────────────────────────────


def _scheduled_pass(monkeypatch, *, time_valid, time_announced):
    from app.utils import espn_helpers
    from tests.test_start_time_follows_the_registry_ranking_8653 import _Row

    class _Team(_Row):
        def __init__(self, name):
            super().__init__(display_name=name, name=name)

    class _Sport:
        id = 53232
        key = "baseball_mlb"

    event = _Row(
        id=15319235, espn_id=SPECIMEN_ESPN_ID, sport=_Sport(), sport_id=_Sport.id,
        home_team_name="New York Yankees", away_team_name="Boston Red Sox",
        home_team_normalized=None, away_team_normalized=None,
        home_team_id=1, away_team_id=2,
        commence_time=STAMP, commence_time_source="statpal",
        broadcast_info=None, llm_importance=None, status="scheduled",
        event_tags=[*OTHER_TAGS, TAG],
    )
    ee = _Row(
        espn_id=SPECIMEN_ESPN_ID,
        home_team=_Team("New York Yankees"), away_team=_Team("Boston Red Sox"),
        date=STAMP, broadcasts=[], season_type=3,
        time_valid=time_valid, time_announced=time_announced,
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

    retired: list[int] = []

    async def _record(_session, event_id):
        retired.append(event_id)

    monkeypatch.setattr(espn_helpers, "upsert_team", _noop)
    monkeypatch.setattr(espn_helpers, "register_espn_team_identities", _noop)
    monkeypatch.setattr(espn_helpers, "retire_start_placeholder_tags", _record)
    asyncio.run(espn_helpers.sync_scheduled_events(_Session(), "baseball_mlb", [ee], {}))
    return event, retired


class TestScheduledPass:
    def test_announced_equal_instant_retires_the_tag(self, monkeypatch):
        event, retired = _scheduled_pass(monkeypatch, time_valid=True, time_announced=True)
        assert retired == [event.id]
        assert event.event_tags == OTHER_TAGS
        assert start_is_tbd(event.event_tags, event.commence_time, event.status) is False
        assert event.commence_time == STAMP
        assert event.commence_time_source == "espn"

    def test_timevalid_false_keeps_it(self, monkeypatch):
        event, retired = _scheduled_pass(monkeypatch, time_valid=False, time_announced=False)
        assert retired == []
        assert start_is_tbd(event.event_tags, event.commence_time, event.status) is True
        assert event.commence_time_source == "statpal"

    def test_timevalid_absent_keeps_it(self, monkeypatch):
        event, retired = _scheduled_pass(monkeypatch, time_valid=True, time_announced=False)
        assert retired == []
        assert event.event_tags == [*OTHER_TAGS, TAG]


# ─────────────────────────────────────────────────────────────────────────────
# 4. StatPal's schedule pass does not write the tag back
# ─────────────────────────────────────────────────────────────────────────────


def _future():
    return (datetime.now(timezone.utc) + timedelta(hours=48)).replace(
        minute=0, second=0, microsecond=0
    )


@pytest.mark.asyncio
async def test_statpal_does_not_retag_a_stamp_espn_vouched_for(monkeypatch):
    """After the ESPN rail: same instant, source espn, no tag. StatPal still
    calls it a placeholder — and must leave it alone, or TBD flaps back."""
    from app.tasks.statpal_sync import _sync_statpal_schedules
    from tests.test_start_placeholder_is_tbd_8841 import _fixture, _wire_pass

    start = _future()
    _row, writes = _wire_pass(
        monkeypatch, fixture=_fixture(start, placeholder=True),
        row_start=start, row_tags=list(OTHER_TAGS), source="espn",
    )
    result = await _sync_statpal_schedules("baseball_mlb")
    assert writes == []
    assert result["schedule_start_placeholder_written"] == 0


@pytest.mark.asyncio
async def test_control_statpal_still_tags_its_own_stamp(monkeypatch):
    from app.tasks.statpal_sync import _sync_statpal_schedules
    from tests.test_start_placeholder_is_tbd_8841 import _fixture, _wire_pass

    start = _future()
    row, writes = _wire_pass(
        monkeypatch, fixture=_fixture(start, placeholder=True),
        row_start=start, row_tags=list(OTHER_TAGS), source="statpal",
    )
    await _sync_statpal_schedules("baseball_mlb")
    assert writes == [(row.id, [start_placeholder_tag(start)])]


# ─────────────────────────────────────────────────────────────────────────────
# 5. The retire rewrite, on real Postgres
# ─────────────────────────────────────────────────────────────────────────────

DB_URL = os.environ.get("START_PLACEHOLDER_DATABASE_URL")


@pytest.mark.asyncio
@pytest.mark.skipif(
    not DB_URL,
    reason="set START_PLACEHOLDER_DATABASE_URL (asyncpg URL to a scratch DB) "
    "to run the JSONB rewrite against real Postgres",
)
async def test_retire_drops_only_placeholder_tags_on_postgres():
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import create_async_engine

    from app.utils.start_placeholder_write import retire_start_placeholder_tags

    engine = create_async_engine(DB_URL)
    other_instant = start_placeholder_tag(STAMP + timedelta(days=1))
    try:
        async with engine.begin() as conn:
            await conn.execute(text(
                "CREATE TEMP TABLE events (id int PRIMARY KEY, event_tags jsonb)"
            ))
            await conn.execute(
                text("INSERT INTO events VALUES (1, CAST(:a AS jsonb)), (2, NULL)"),
                {"a": json.dumps([*OTHER_TAGS, TAG, "sport:baseball", other_instant, 7])},
            )
            await retire_start_placeholder_tags(conn, 1)
            await retire_start_placeholder_tags(conn, 2)
            rows = dict((await conn.execute(text("SELECT id, event_tags FROM events"))).all())
    finally:
        await engine.dispose()

    assert rows[1] == [*OTHER_TAGS, "sport:baseball", 7]
    assert rows[2] == []
