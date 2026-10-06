"""#10581: exact-team dropdown keeps the latest final beside its next game.

Runs the production two-query selector against actual SQL on disposable SQLite.
Timezone binds are UTC-normalized to match PostgreSQL instant comparisons. This
is controlled query acceptance, not PostgreSQL race or installed-phone evidence.
"""

from datetime import datetime, timedelta, timezone
import sqlite3
from types import SimpleNamespace

import pytest
from sqlalchemy.dialects import sqlite

from app.models.models import Event
from app.routes import events as ev

NOW = datetime(2026, 10, 6, 3, 5, 17, tzinfo=timezone.utc)
TEAM = "Milwaukee Brewers"
# The retained official final tuple existed at this instant. The actual kickoff
# is unknown; even this latest possible upper bound predates the recent window.
FINAL_UPPER_BOUND = datetime(2026, 10, 5, 1, 59, 40, 593348, tzinfo=timezone.utc)


def _stamp(value):
    return (
        value.astimezone(timezone.utc)
        .replace(tzinfo=None)
        .strftime("%Y-%m-%d %H:%M:%S.%f")
    )


class _Rows:
    def __init__(self, rows):
        self.rows = rows

    def scalars(self):
        return self

    def all(self):
        return self.rows


class _DB:
    def __init__(self, rows):
        self.connection = sqlite3.connect(":memory:")
        self.connection.execute("CREATE TABLE sports (id INTEGER PRIMARY KEY)")
        self.connection.execute("INSERT INTO sports VALUES (1)")
        self.connection.execute(
            "CREATE TABLE events (id INTEGER PRIMARY KEY, sport_id INTEGER, "
            "home_team_id INTEGER, away_team_id INTEGER, home_team_name TEXT, "
            "away_team_name TEXT, status TEXT, commence_time TEXT, event_tags TEXT)"
        )
        self.connection.executemany(
            "INSERT INTO events VALUES (?,1,NULL,NULL,?,?,?,?,?)",
            [
                (
                    r.id,
                    r.home_team_name,
                    r.away_team_name,
                    r.status,
                    _stamp(r.commence_time),
                    r.event_tags,
                )
                for r in rows
            ],
        )
        self.rows = {r.id: r for r in rows}
        self.calls = 0

    async def execute(self, query):
        self.calls += 1
        # Keep the actual helper's joins/where/order/limit; only the projection
        # changes so the tiny SQL fixture needs no unused ORM columns.
        compiled = query.with_only_columns(Event.id).compile(
            dialect=sqlite.dialect(), compile_kwargs={"render_postcompile": True}
        )
        values = [compiled.params[key] for key in compiled.positiontup]
        values = [_stamp(v) if isinstance(v, datetime) else v for v in values]
        ids = [r[0] for r in self.connection.execute(str(compiled), values)]
        return _Rows([self.rows[i] for i in ids])


def _row(identity, when, *, status="completed", home=TEAM, tags=None):
    return SimpleNamespace(
        id=identity,
        home_team_name=home,
        away_team_name="San Diego Padres",
        status=status,
        commence_time=when,
        event_tags=tags,
    )


@pytest.mark.asyncio
async def test_retained_padres_brewers_final_survives_a_real_next_fixture():
    final = _row(15323985, FINAL_UPPER_BOUND)
    next_game = _row(9001, NOW + timedelta(hours=22), status="scheduled")
    db = _DB([final, next_game])
    finals = await ev._lead_team_finals_with_latest_fallback(db, -1, TEAM, NOW)
    assert [r.id for r in finals] == [15323985]
    assert db.calls == 2
    # Production insertion preserves the next game and keeps the final before props.
    placed = ev._place_todays_finals([next_game], finals, lambda r: r.id == 9001)
    assert [r.id for r in placed] == [9001, 15323985]


@pytest.mark.asyncio
async def test_recent_doubleheader_is_unchanged_and_needs_no_fallback_query():
    db = _DB(
        [
            _row(1, NOW - timedelta(hours=2)),
            _row(2, NOW - timedelta(hours=3)),
            _row(3, FINAL_UPPER_BOUND),
        ]
    )
    finals = await ev._lead_team_finals_with_latest_fallback(db, -1, TEAM, NOW)
    assert [r.id for r in finals] == [1, 2]
    assert db.calls == 1


@pytest.mark.asyncio
async def test_fallback_returns_only_the_newest_finished_game():
    db = _DB(
        [
            _row(1, FINAL_UPPER_BOUND, status="closed"),
            _row(2, FINAL_UPPER_BOUND - timedelta(days=1)),
        ]
    )
    finals = await ev._lead_team_finals_with_latest_fallback(db, -1, TEAM, NOW)
    assert [r.id for r in finals] == [1]


@pytest.mark.asyncio
async def test_fallback_preserves_the_existing_last_match_floor():
    floor = NOW - timedelta(days=ev._LAST_MATCH_LOOKBACK_DAYS)
    db = _DB([_row(1, floor), _row(2, floor - timedelta(microseconds=1))])
    finals = await ev._lead_team_finals_with_latest_fallback(db, -1, TEAM, NOW)
    assert [r.id for r in finals] == [1]
    old_only = _DB([_row(2, floor - timedelta(microseconds=1))])
    assert (
        await ev._lead_team_finals_with_latest_fallback(old_only, -1, TEAM, NOW) == []
    )


@pytest.mark.asyncio
async def test_fallback_refuses_future_suspended_duplicates_and_other_teams():
    db = _DB(
        [
            _row(1, NOW + timedelta(minutes=1)),
            _row(2, FINAL_UPPER_BOUND, status="suspended"),
            _row(3, FINAL_UPPER_BOUND, tags='["provenance:duplicate-of:15323985"]'),
            _row(4, FINAL_UPPER_BOUND, home="Houston Astros"),
            _row(15323985, FINAL_UPPER_BOUND),
        ]
    )
    finals = await ev._lead_team_finals_with_latest_fallback(db, -1, TEAM, NOW)
    assert [r.id for r in finals] == [15323985]


@pytest.mark.asyncio
async def test_exact_team_name_does_not_recall_a_namesake_by_substring():
    db = _DB([_row(1, FINAL_UPPER_BOUND, home="Milwaukee Brewers Academy")])
    assert await ev._lead_team_finals_with_latest_fallback(db, -1, TEAM, NOW) == []
