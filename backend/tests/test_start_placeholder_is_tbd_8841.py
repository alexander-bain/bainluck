"""#8841 — an unannounced playoff start prints its date and "TBD", not "1:00 PM".

WHAT A READER SAW
=================
Production 2026-09-26 ~15:20Z, `bainluck.com/search?q=red%20sox` at 390px: the
Red Sox @ Yankees Wild Card card read "Sep 29 1:00 PM". MLB had not set the
time; ESPN's scoreboard carried `timeValid=false` for both games.

Our rows `15319235` / `15319236` were created by the StatPal schedule pass at
20:00Z each. StatPal's `/v1/mlb/season-schedule` (fixture
`statpal_mlb_season_schedule_wildcard_8841.json`, read 2026-09-26 15:33Z) lists
the regular season in `tournament.match[]` with minute-precise times and the
two Wild Card games in `tournament.week[]` ("MLB - Final") at `20:00` — its
placeholder, flattened by the parser into the same list as real starts.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from app.services.statpal_api import StatPalAPIService, StatPalFixture
from app.utils.start_placeholder import (
    START_PLACEHOLDER_TAG_PREFIX,
    desired_start_placeholder_tags,
    needs_start_placeholder_write,
    start_is_tbd,
    start_placeholder_tag,
    statpal_placeholder_fixture_ids,
)

FIXTURES = Path(__file__).parent / "fixtures"
SPECIMEN = FIXTURES / "statpal_mlb_season_schedule_wildcard_8841.json"
GAME_1, GAME_2 = "369024", "369023"
GAME_1_STAMP = datetime(2026, 9, 29, 20, 0, tzinfo=timezone.utc)


def _load(name):
    return json.loads((FIXTURES / name).read_text())


def _parse(data, sport="mlb"):
    return StatPalAPIService(api_key="test")._parse_fixtures(data, sport)


# ─────────────────────────────────────────────────────────────────────────────
# 1. The parser keeps the evidence the flattening used to discard
# ─────────────────────────────────────────────────────────────────────────────


class TestTheParserMarksThePlaceholder:
    def test_the_specimen_games_are_marked_and_nothing_else_is(self):
        fixtures = _parse(json.loads(SPECIMEN.read_text()))
        marked = {f.fixture_id for f in fixtures if f.start_is_placeholder}
        assert marked == {GAME_1, GAME_2}
        by_id = {f.fixture_id: f for f in fixtures}
        assert by_id[GAME_1].start_time == GAME_1_STAMP
        # Every regular-season game in the same payload keeps its real time.
        assert sum(1 for f in fixtures if not f.start_is_placeholder) == 91

    def test_an_on_the_hour_regular_season_game_is_not_a_placeholder(self):
        data = json.loads(SPECIMEN.read_text())
        data["scores"]["tournament"]["match"][-1]["time"] = "20:00"
        data["scores"]["tournament"]["match"][-1]["status"] = "Not Started"
        marked = {f.fixture_id for f in _parse(data) if f.start_is_placeholder}
        assert marked == {GAME_1, GAME_2}, "only the week[] bucket is evidence"

    def test_an_announced_postseason_time_is_not_a_placeholder(self):
        data = json.loads(SPECIMEN.read_text())
        data["scores"]["tournament"]["week"][0]["match"][0]["time"] = "20:08"
        marked = statpal_placeholder_fixture_ids(data, "mlb")
        assert marked == {GAME_2}

    def test_a_started_or_finished_postseason_game_is_not_a_placeholder(self):
        data = json.loads(SPECIMEN.read_text())
        data["scores"]["tournament"]["week"][0]["match"][0]["status"] = "Finished"
        assert statpal_placeholder_fixture_ids(data, "mlb") == {GAME_2}

    def test_a_board_serving_a_local_clock_is_not_this_shape(self):
        data = json.loads(SPECIMEN.read_text())
        game = data["scores"]["tournament"]["week"][0]["match"][0]
        game["timezone"] = "ET"
        game["datetime_utc"] = "2026-09-29T20:00:00Z"
        assert statpal_placeholder_fixture_ids(data, "mlb") == {GAME_2}

    def test_on_the_hour_is_a_real_start_in_nba_and_nhl(self):
        """The same bucket in NBA/NHL would hide real 7:00 PM starts."""
        data = json.loads(SPECIMEN.read_text())
        assert statpal_placeholder_fixture_ids(data, "nba") == frozenset()
        assert statpal_placeholder_fixture_ids(data, "nhl") == frozenset()
        assert not any(f.start_is_placeholder for f in _parse(data, "nba"))

    @pytest.mark.parametrize(
        "name,sport",
        [
            ("statpal_mlb_season_schedule_20260904_fullcensus.json", "mlb"),
            ("statpal_nba_season_schedule_20260904.json", "nba"),
            ("statpal_mlb_livescores_20260904_fullcensus.json", "mlb"),
        ],
    )
    def test_banked_payloads_without_the_shape_mark_nothing(self, name, sport):
        assert not any(f.start_is_placeholder for f in _parse(_load(name), sport))

    def test_a_single_week_game_served_as_a_bare_dict(self):
        data = json.loads(SPECIMEN.read_text())
        week = data["scores"]["tournament"]["week"]
        week[0]["match"] = week[0]["match"][0]
        assert statpal_placeholder_fixture_ids(data, "mlb") == {GAME_1}


# ─────────────────────────────────────────────────────────────────────────────
# 2. The served rule: TBD only while the row still carries the placeholder
# ─────────────────────────────────────────────────────────────────────────────


class TestTheServedRule:
    TAGS = ["provenance:source:statpal", start_placeholder_tag(GAME_1_STAMP)]

    def test_the_specimen_reads_tbd(self):
        assert self.TAGS[1] == START_PLACEHOLDER_TAG_PREFIX + "2026-09-29T20:00Z"
        assert start_is_tbd(self.TAGS, GAME_1_STAMP, "scheduled") is True

    def test_a_real_time_written_by_any_rail_retires_it(self):
        """ESPN with a valid time, MLB, or StatPal itself — none need to know the tag."""
        moved = GAME_1_STAMP + timedelta(minutes=8)
        assert start_is_tbd(self.TAGS, moved, "scheduled") is False

    @pytest.mark.parametrize("status", ["live", "completed", "closed", None])
    def test_only_a_scheduled_game_can_be_tbd(self, status):
        assert start_is_tbd(self.TAGS, GAME_1_STAMP, status) is False

    @pytest.mark.parametrize("tags", [None, [], ["provenance:source:statpal"], "x"])
    def test_an_untagged_row_prints_its_time(self, tags):
        assert start_is_tbd(tags, GAME_1_STAMP, "scheduled") is False

    def test_a_naive_stamp_reads_as_utc(self):
        naive = GAME_1_STAMP.replace(tzinfo=None)
        assert start_is_tbd(self.TAGS, naive, "scheduled") is True


class TestWhatThePassWrites:
    def test_the_placeholder_is_written_for_the_stamp_it_vouches_for(self):
        desired = desired_start_placeholder_tags(
            fixture_is_placeholder=True,
            fixture_start=GAME_1_STAMP,
            commence_time=GAME_1_STAMP,
        )
        assert desired == [start_placeholder_tag(GAME_1_STAMP)]

    def test_a_row_another_rail_moved_gets_no_tag(self):
        assert desired_start_placeholder_tags(
            fixture_is_placeholder=True,
            fixture_start=GAME_1_STAMP,
            commence_time=GAME_1_STAMP - timedelta(hours=16),  # ESPN's T04:00Z
        ) == []

    def test_a_real_start_clears_the_tag(self):
        assert desired_start_placeholder_tags(
            fixture_is_placeholder=False,
            fixture_start=GAME_1_STAMP,
            commence_time=GAME_1_STAMP,
        ) == []

    def test_write_only_when_the_stored_tags_differ(self):
        tag = start_placeholder_tag(GAME_1_STAMP)
        assert needs_start_placeholder_write(["a"], [tag]) is True
        assert needs_start_placeholder_write(["a", tag], [tag]) is False
        assert needs_start_placeholder_write(["a", tag], []) is True
        assert needs_start_placeholder_write(["a"], []) is False
        assert needs_start_placeholder_write(None, []) is False


# ─────────────────────────────────────────────────────────────────────────────
# 3. The payloads carry it
# ─────────────────────────────────────────────────────────────────────────────


def _row(**over):
    from types import SimpleNamespace

    fields = dict(
        id=15319235,
        external_id=None,
        sport=SimpleNamespace(key="baseball_mlb", name="MLB"),
        home_team_name="New York Yankees",
        away_team_name="Boston Red Sox",
        home_team_id=None,
        away_team_id=None,
        home_score=None,
        away_score=None,
        commence_time=GAME_1_STAMP,
        completed_at=None,
        status="scheduled",
        event_tags=["provenance:source:statpal", start_placeholder_tag(GAME_1_STAMP)],
        win_probability_sources=None,
        opening_home_probability=None,
        opening_away_probability=None,
    )
    fields.update(over)
    return SimpleNamespace(**fields)


def test_the_team_page_brief_serves_start_is_tbd():
    from types import SimpleNamespace

    from app.routes.teams import _format_event_brief

    team = SimpleNamespace(id=1, name="Boston Red Sox")
    assert _format_event_brief(_row(), team)["start_is_tbd"] is True
    moved = _row(commence_time=GAME_1_STAMP + timedelta(minutes=8))
    assert _format_event_brief(moved, team)["start_is_tbd"] is False


def _model_row(**over):
    """A real `Event` (every column `_format_event` reads exists on the model)."""
    from app.models import Event, Sport

    fields = dict(
        id=15319235,
        sport_id=1,
        sport=Sport(id=1, key="baseball_mlb", name="MLB"),
        home_team_name="New York Yankees",
        away_team_name="Boston Red Sox",
        home_score=None,
        away_score=None,
        commence_time=GAME_1_STAMP,
        status="scheduled",
        event_tags=["provenance:source:statpal", start_placeholder_tag(GAME_1_STAMP)],
    )
    fields.update(over)
    return Event(**fields)


def test_the_shared_event_formatter_serves_start_is_tbd():
    """`_format_event` feeds search, the event page and every list route.

    Executed, not read as source (CERT-3567 follow-up
    8841-SERVED-PAYLOAD-BEHAVIOR-GUARD): a formatter that printed the key with
    a constant, or read the wrong column, passes a string match and fails here.
    """
    from app.routes.events import _format_event

    assert _format_event(_model_row())["start_is_tbd"] is True


@pytest.mark.parametrize(
    "over",
    [
        # Another rail wrote a real start: the tag no longer vouches for it.
        {"commence_time": GAME_1_STAMP + timedelta(minutes=8)},
        # A game that has started has a start, whatever the stamp says.
        {"status": "live"},
        {"status": "completed"},
        # No tag, or only unrelated tags.
        {"event_tags": None},
        {"event_tags": ["provenance:source:statpal"]},
        # A tag for a different instant than the row carries.
        {"event_tags": [start_placeholder_tag(GAME_1_STAMP + timedelta(days=1))]},
    ],
    ids=["moved", "live", "completed", "no-tags", "unrelated-tag", "other-instant"],
)
def test_the_shared_event_formatter_serves_a_real_start_as_not_tbd(over):
    from app.routes.events import _format_event

    assert _format_event(_model_row(**over))["start_is_tbd"] is False


# ─────────────────────────────────────────────────────────────────────────────
# 4. The schedule pass writes and retires the tag
# ─────────────────────────────────────────────────────────────────────────────


def _wire_pass(monkeypatch, *, fixture: StatPalFixture, row_start, row_tags, source):
    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session

    import app.services.statpal_api as statpal_api
    import app.tasks.base as task_base
    import app.tasks.statpal_sync as statpal_sync
    from tests.test_start_time_follows_the_registry_ranking_8653 import (
        _AsyncShim,
        _utc_on_load,
    )
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
    sport = Sport(key="baseball_mlb", name="MLB")
    session.add(sport)
    session.flush()
    row = Event(
        sport_id=sport.id,
        home_team_name=fixture.home_team,
        away_team_name=fixture.away_team,
        commence_time=row_start,
        commence_time_source=source,
        status="scheduled",
        statpal_fixture_id=fixture.fixture_id,
        event_tags=row_tags,
    )
    session.add(row)
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
    monkeypatch.setattr(statpal_sync, "get_task_session", lambda: _Ctx(), raising=False)

    class _Service:
        async def get_fixtures_result(self, sport):
            return statpal_api.StatPalFixtureFetch([fixture], "ok", sport, "season-schedule")

        async def get_live_scores(self, sport):
            return []

        async def close(self):
            return None

    monkeypatch.setattr(statpal_api, "is_available", lambda: True)
    monkeypatch.setattr(statpal_api, "StatPalAPIService", lambda *a, **kw: _Service())

    # The registry's create path is not what this test is about; the row
    # already exists, so resolve the fixture to it directly.
    async def _find(session_, identity):
        from sqlalchemy import select

        got = (await session_.execute(select(Event).where(Event.id == row.id))).scalar_one()
        return got, False

    monkeypatch.setattr("app.services.event_registry.find_or_create_event", _find)

    writes: list[tuple[int, list[str]]] = []

    async def _record(_session, event_id, desired):
        writes.append((event_id, list(desired)))

    monkeypatch.setattr(statpal_sync, "_write_start_placeholder_tags", _record)
    return row, writes


def _fixture(start, *, placeholder):
    return StatPalFixture(
        fixture_id=GAME_1,
        home_team="New York Yankees",
        away_team="Boston Red Sox",
        start_time=start,
        status="scheduled",
        start_is_placeholder=placeholder,
    )


def _future(hours=48):
    return (datetime.now(timezone.utc) + timedelta(hours=hours)).replace(
        minute=0, second=0, microsecond=0
    )


@pytest.mark.asyncio
async def test_the_pass_tags_a_placeholder_start(monkeypatch):
    from app.tasks.statpal_sync import _sync_statpal_schedules

    start = _future()
    row, writes = _wire_pass(
        monkeypatch, fixture=_fixture(start, placeholder=True),
        row_start=start, row_tags=["provenance:source:statpal"], source="statpal",
    )
    result = await _sync_statpal_schedules("baseball_mlb")
    assert writes == [(row.id, [start_placeholder_tag(start)])]
    assert result["schedule_start_placeholder_written"] == 1


@pytest.mark.asyncio
async def test_the_pass_leaves_an_already_tagged_row_alone(monkeypatch):
    from app.tasks.statpal_sync import _sync_statpal_schedules

    start = _future()
    _row_, writes = _wire_pass(
        monkeypatch, fixture=_fixture(start, placeholder=True),
        row_start=start,
        row_tags=["provenance:source:statpal", start_placeholder_tag(start)],
        source="statpal",
    )
    result = await _sync_statpal_schedules("baseball_mlb")
    assert writes == []
    assert result["schedule_start_placeholder_written"] == 0


@pytest.mark.asyncio
async def test_statpal_announcing_the_time_retires_the_tag(monkeypatch):
    """StatPal moves 20:00 -> 20:08: the start is corrected AND the tag cleared."""
    from app.tasks.statpal_sync import _sync_statpal_schedules

    placeholder = _future()
    real = placeholder + timedelta(minutes=8)
    row, writes = _wire_pass(
        monkeypatch, fixture=_fixture(real, placeholder=False),
        row_start=placeholder,
        row_tags=["provenance:source:statpal", start_placeholder_tag(placeholder)],
        source="statpal",
    )
    await _sync_statpal_schedules("baseball_mlb")
    assert writes == [(row.id, [])]


@pytest.mark.asyncio
async def test_a_row_espn_moved_is_not_retagged(monkeypatch):
    """ESPN outranks StatPal (#8653): its stamp stays and no TBD is claimed for it."""
    from app.tasks.statpal_sync import _sync_statpal_schedules

    placeholder = _future()
    espn = placeholder + timedelta(minutes=8)
    _row_, writes = _wire_pass(
        monkeypatch, fixture=_fixture(placeholder, placeholder=True),
        row_start=espn, row_tags=["provenance:source:espn"], source="espn",
    )
    result = await _sync_statpal_schedules("baseball_mlb")
    assert writes == []
    assert result["schedule_commence_outranked"] == 1


# ─────────────────────────────────────────────────────────────────────────────
# 5. The tag rewrite, on real Postgres
# ─────────────────────────────────────────────────────────────────────────────

DB_URL = os.environ.get("START_PLACEHOLDER_DATABASE_URL")


@pytest.mark.asyncio
@pytest.mark.skipif(
    not DB_URL,
    reason="set START_PLACEHOLDER_DATABASE_URL (asyncpg URL to a scratch DB) "
    "to run the JSONB rewrite against real Postgres",
)
async def test_the_rewrite_touches_only_placeholder_tags_on_postgres():
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import create_async_engine

    from app.tasks.statpal_sync import _write_start_placeholder_tags

    engine = create_async_engine(DB_URL)
    old = start_placeholder_tag(GAME_1_STAMP)
    new = start_placeholder_tag(GAME_1_STAMP + timedelta(days=1))
    try:
        async with engine.begin() as conn:
            await conn.execute(text(
                "CREATE TEMP TABLE events (id int PRIMARY KEY, event_tags jsonb)"
            ))
            await conn.execute(
                text("INSERT INTO events VALUES (1, CAST(:a AS jsonb)), (2, NULL), (3, CAST(:c AS jsonb))"),
                {
                    "a": json.dumps(["provenance:source:statpal", old, "sport:baseball", 7]),
                    "c": json.dumps(["tier:1"]),
                },
            )
            await _write_start_placeholder_tags(conn, 1, [new])
            await _write_start_placeholder_tags(conn, 2, [new])
            await _write_start_placeholder_tags(conn, 3, [])
            rows = dict((await conn.execute(text("SELECT id, event_tags FROM events"))).all())
    finally:
        await engine.dispose()

    assert rows[1] == ["provenance:source:statpal", "sport:baseball", 7, new]
    assert rows[2] == [new]
    assert rows[3] == ["tier:1"]
