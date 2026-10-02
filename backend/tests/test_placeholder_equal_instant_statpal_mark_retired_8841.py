"""#8841: ESPN announcing the minute StatPal's placeholder sits on retires the mark.

Specimen: Yankees @ Rays ALDS Game 2, read 2026-10-02 04:55Z. Row 15322663 sat
on ``2026-10-06T00:00Z`` carrying
``provenance:start-placeholder:statpal:2026-10-06T00:00Z``; ESPN 401907986 had
``2026-10-06T00:00Z`` with ``timeValid: true`` — 5:00 PM PT Mon Oct 5. #9197's
move fires only on a DIFFERENT minute, and the placeholder pass's equal-instant
arm cleared only ESPN's own mark, so ``start_is_tbd`` stayed true and the
Yankees page printed "Oct 6 · TBD". Same shape, same read: White Sox @
Guardians Game 1 15322556 (401907991, 21:00Z Oct 5) and Guardians @ White Sox
Game 3 15322557 (no ``espn_id``; 401907992, 20:00Z Oct 7).
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from app.tasks import espn_start_placeholders as task
from app.tasks.espn_start_placeholders import CandidateRow, confirms_placeholder, plan_move
from app.utils.start_placeholder import (
    START_PLACEHOLDER_TAG_PREFIX,
    announced_at_statpal_placeholder,
    espn_start_placeholder_tag,
    start_is_tbd,
    start_placeholder_tag,
)

UTC = timezone.utc
G2 = datetime(2026, 10, 6, 0, 0, tzinfo=UTC)        # NYY @ TB, 8 PM ET Oct 5
CWS_G1 = datetime(2026, 10, 5, 21, 0, tzinfo=UTC)   # CWS @ CLE, 5 PM ET Oct 5
CLE_G3 = datetime(2026, 10, 7, 20, 0, tzinfo=UTC)   # CLE @ CWS, 4 PM ET Oct 7
G2_TAG = start_placeholder_tag(G2)
BASE_TAGS = ["provenance:source:statpal", "provenance:unanchored"]


def _team(name):
    return SimpleNamespace(display_name=name, name=name.split()[-1])


def _game(espn_id, date, away, home, *, announced=True, status="scheduled"):
    return SimpleNamespace(
        espn_id=espn_id, date=date, status=status,
        time_valid=announced, time_announced=announced,
        home_team=_team(home), away_team=_team(away),
    )


#: ESPN's MLB boards as read 2026-10-02 05:10Z, ALDS games only.
OCT5_BOARD = [
    _game("401907991", CWS_G1, "Chicago White Sox", "Cleveland Guardians"),
    _game("401907986", G2, "New York Yankees", "Tampa Bay Rays"),
]
OCT7_BOARD = [
    _game("401907992", CLE_G3, "Cleveland Guardians", "Chicago White Sox"),
    _game("401907987", datetime(2026, 10, 8, 0, 0, tzinfo=UTC),
          "Tampa Bay Rays", "New York Yankees"),
]
BOARDS = {("baseball_mlb", "20261005"): OCT5_BOARD, ("baseball_mlb", "20261007"): OCT7_BOARD}


def _rule(**kw):
    args = dict(
        event_tags=[*BASE_TAGS, G2_TAG],
        commence_time=G2,
        status="scheduled",
        time_announced=True,
        espn_status="scheduled",
        espn_date=G2,
    )
    args.update(kw)
    return announced_at_statpal_placeholder(**args)


def _row(event_id=15322663, espn_id="401907986", commence=G2, tags=None,
         source="espn", home="Tampa Bay Rays", away="New York Yankees"):
    return CandidateRow(
        event_id=event_id, sport_key="baseball_mlb", espn_id=espn_id,
        commence_time=commence,
        event_tags=[*BASE_TAGS, G2_TAG] if tags is None else tags,
        commence_time_source=source, home_team_name=home, away_team_name=away,
    )


# ─────────────────────────────────────────────────────────────────────────────
# 1. The rule
# ─────────────────────────────────────────────────────────────────────────────

class TestTheRule:
    def test_the_specimen_is_announced_at_its_placeholder_minute(self):
        assert _rule()

    def test_retiring_the_mark_retires_the_tbd(self):
        tags = [*BASE_TAGS, G2_TAG]
        assert start_is_tbd(tags, G2, "scheduled")
        assert not start_is_tbd(BASE_TAGS, G2, "scheduled")

    def test_another_minute_is_a_move_not_a_confirmation(self):
        assert not _rule(espn_date=datetime(2026, 10, 6, 0, 8, tzinfo=UTC))

    def test_seconds_inside_the_minute_are_the_same_minute(self):
        assert _rule(espn_date=G2.replace(second=30))

    def test_an_absent_flag_is_no_announcement(self):
        assert not _rule(time_announced=False)

    def test_a_game_espn_has_started_confirms_nothing(self):
        assert not _rule(espn_status="in")

    def test_only_a_scheduled_row_is_confirmed(self):
        assert not _rule(status="live")

    def test_an_unmarked_row_has_nothing_to_retire(self):
        assert not _rule(event_tags=list(BASE_TAGS))

    def test_a_mark_for_another_instant_is_not_this_rows_tbd(self):
        assert not _rule(event_tags=[start_placeholder_tag(CWS_G1)])

    def test_espns_own_mark_is_not_this_rules(self):
        # plan_row already clears ESPN's mark at an equal instant (#8981).
        assert not _rule(event_tags=[espn_start_placeholder_tag(G2)])

    def test_a_naive_espn_date_reads_as_utc(self):
        assert _rule(espn_date=G2.replace(tzinfo=None))


class TestThePlan:
    def test_the_specimen_is_not_a_move(self):
        assert plan_move(_row(), OCT5_BOARD[1]) == ("none", None)

    def test_the_specimen_confirms(self):
        assert confirms_placeholder(_row(), OCT5_BOARD[1])

    def test_before_espn_announces_nothing_confirms(self):
        tbd = _game("401907986", G2, "New York Yankees", "Tampa Bay Rays", announced=False)
        assert not confirms_placeholder(_row(), tbd)


# ─────────────────────────────────────────────────────────────────────────────
# 2. The pass
# ─────────────────────────────────────────────────────────────────────────────

class _Result:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return self._rows


class _Session:
    """First execute answers the candidate query, the next the held-id lookup."""

    def __init__(self, rows, held=()):
        self.answers = [rows, [(h,) for h in held]]
        self.held_lookups = 0
        self.commits = 0

    async def execute(self, stmt):
        if not self.answers:
            return _Result([])
        if len(self.answers) == 1:
            self.held_lookups += 1
        return _Result(self.answers.pop(0))

    async def commit(self):
        self.commits += 1


class _Ctx:
    def __init__(self, session):
        self.session = session

    async def __aenter__(self):
        return self.session

    async def __aexit__(self, *exc):
        return False


def _wire(monkeypatch, *, rows, boards=BOARDS, held=(), write_lands=True):
    import app.services.espn_api as espn_api
    import app.tasks.base as task_base
    import app.utils.start_placeholder_write as writer

    session = _Session(rows, held)
    moves, marks, confirms = [], [], []

    class _Espn:
        async def get_scoreboard(self, sport_key, date=None, groups=None):
            return boards.get((sport_key, date))

        async def close(self):
            pass

    async def _move(sess, event_id, placeholder, announced):
        moves.append((event_id, placeholder, announced))
        return True

    async def _mark(sess, event_id, desired):
        marks.append((event_id, list(desired)))

    async def _confirm(sess, event_id, instant, *, take_source):
        confirms.append((event_id, instant, take_source))
        return write_lands

    monkeypatch.setattr(task_base, "get_task_session", lambda: _Ctx(session))
    monkeypatch.setattr(espn_api, "ESPNAPIService", lambda *a, **kw: _Espn())
    monkeypatch.setattr(writer, "write_announced_start", _move)
    monkeypatch.setattr(writer, "write_espn_start_placeholder_tags", _mark)
    monkeypatch.setattr(writer, "confirm_announced_placeholder", _confirm)
    return session, moves, marks, confirms


def _db(event_id, espn_id, commence, home, away, source="espn"):
    return (
        event_id, "baseball_mlb", espn_id, commence,
        [*BASE_TAGS, start_placeholder_tag(commence)], source, home, away,
    )


ALDS_ROWS = [
    _db(15322556, "401907991", CWS_G1, "Cleveland Guardians", "Chicago White Sox"),
    _db(15322663, "401907986", G2, "Tampa Bay Rays", "New York Yankees"),
    _db(15322557, None, CLE_G3, "Chicago White Sox", "Cleveland Guardians", source="statpal"),
]


@pytest.mark.asyncio
async def test_all_three_alds_marks_are_retired(monkeypatch):
    session, moves, marks, confirms = _wire(monkeypatch, rows=ALDS_ROWS)
    stats = await task._run_mark_espn_start_placeholders(apply=True)
    assert confirms == [
        (15322556, CWS_G1, True),
        (15322663, G2, True),
        (15322557, CLE_G3, True),
    ]
    assert moves == [] and marks == []
    assert session.commits == 1
    assert stats["confirm"] == 3
    assert stats["confirmed_ids"] == [15322556, 15322663, 15322557]
    # The id-less row was found by name, so the held-id guard was consulted.
    assert session.held_lookups == 1


@pytest.mark.asyncio
async def test_a_dry_run_plans_the_retirements_and_writes_nothing(monkeypatch):
    session, _, _, confirms = _wire(monkeypatch, rows=ALDS_ROWS)
    stats = await task._run_mark_espn_start_placeholders(apply=False)
    assert confirms == [] and session.commits == 0
    assert stats["confirmed_ids"] == [15322556, 15322663, 15322557]


@pytest.mark.asyncio
async def test_a_game_another_row_carries_is_not_confirmed_by_name(monkeypatch):
    _, _, _, confirms = _wire(monkeypatch, rows=ALDS_ROWS, held=["401907992"])
    stats = await task._run_mark_espn_start_placeholders(apply=True)
    assert [c[0] for c in confirms] == [15322556, 15322663]
    assert stats["confirm_id_held_elsewhere"] == 1


@pytest.mark.asyncio
async def test_a_row_moved_under_the_pass_is_counted_stale(monkeypatch):
    session, _, _, confirms = _wire(monkeypatch, rows=ALDS_ROWS[1:2], write_lands=False)
    stats = await task._run_mark_espn_start_placeholders(apply=True)
    assert len(confirms) == 1
    assert stats["confirm"] == 0 and stats["confirm_stale"] == 1
    assert stats["confirmed_ids"] == []
    assert session.commits == 0


@pytest.mark.asyncio
async def test_a_source_that_outranks_espn_keeps_its_stamp_but_loses_the_mark(monkeypatch):
    rows = [_db(15322663, "401907986", G2, "Tampa Bay Rays", "New York Yankees",
                source="mlb_schedule_repair")]
    _, _, _, confirms = _wire(monkeypatch, rows=rows)
    await task._run_mark_espn_start_placeholders(apply=True)
    assert confirms == [(15322663, G2, False)]


@pytest.mark.asyncio
async def test_before_espn_announces_the_marks_stay(monkeypatch):
    tbd = {
        key: [
            SimpleNamespace(**{**vars(g), "time_valid": False, "time_announced": False})
            for g in board
        ]
        for key, board in BOARDS.items()
    }
    _, _, _, confirms = _wire(monkeypatch, rows=ALDS_ROWS, boards=tbd)
    stats = await task._run_mark_espn_start_placeholders(apply=True)
    assert confirms == [] and stats["confirm"] == 0


@pytest.mark.asyncio
async def test_a_different_minute_is_still_a_move_never_a_confirmation(monkeypatch):
    # Control: the Wild Card shape (#9197) still writes the announced start.
    placeholder = datetime(2026, 10, 5, 20, 0, tzinfo=UTC)
    rows = [_db(15322663, "401907986", placeholder, "Tampa Bay Rays",
                "New York Yankees", source="statpal")]
    _, moves, _, confirms = _wire(monkeypatch, rows=rows)
    stats = await task._run_mark_espn_start_placeholders(apply=True)
    assert moves == [(15322663, placeholder, G2)]
    assert confirms == [] and stats["confirm"] == 0


# ─────────────────────────────────────────────────────────────────────────────
# 3. The write: compare-and-write, StatPal's prefix only
# ─────────────────────────────────────────────────────────────────────────────

class _Capture:
    def __init__(self, rowcount):
        self.rowcount = rowcount
        self.calls = []

    async def execute(self, stmt, params=None):
        self.calls.append((" ".join(str(stmt).split()), params))
        return SimpleNamespace(rowcount=self.rowcount)


@pytest.mark.asyncio
async def test_the_write_lands_only_on_the_instant_it_read():
    from app.utils.start_placeholder_write import confirm_announced_placeholder

    session = _Capture(rowcount=1)
    assert await confirm_announced_placeholder(session, 15322663, G2, take_source=True)
    sql, params = session.calls[0]
    where = sql.split("WHERE id", 1)[1]
    assert sql.startswith("UPDATE events SET event_tags = ")
    assert "commence_time_source = CASE WHEN :take THEN 'espn'" in sql
    assert "commence_time = :instant" in where
    assert "status = 'scheduled'" in where
    assert params == {
        "plen": len(START_PLACEHOLDER_TAG_PREFIX),
        "prefix": START_PLACEHOLDER_TAG_PREFIX,
        "take": True,
        "instant": G2,
        "eid": 15322663,
    }


@pytest.mark.asyncio
async def test_a_row_that_moved_on_reports_not_written():
    from app.utils.start_placeholder_write import confirm_announced_placeholder

    assert not await confirm_announced_placeholder(
        _Capture(rowcount=0), 15322663, G2, take_source=True
    )


DB_URL = os.environ.get("START_PLACEHOLDER_DATABASE_URL")


@pytest.mark.asyncio
@pytest.mark.skipif(
    not DB_URL,
    reason="set START_PLACEHOLDER_DATABASE_URL (asyncpg URL to a scratch DB) "
    "to run the compare-and-write against real Postgres",
)
async def test_the_confirmation_on_postgres():
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import create_async_engine

    from app.utils.start_placeholder_write import confirm_announced_placeholder

    engine = create_async_engine(DB_URL)
    espn_mark = espn_start_placeholder_tag(G2)
    tags = [*BASE_TAGS, G2_TAG, espn_mark, "sport:baseball", 7]
    try:
        async with engine.begin() as conn:
            await conn.execute(text(
                "CREATE TEMP TABLE events (id int PRIMARY KEY, event_tags jsonb, "
                "commence_time timestamptz, status text, commence_time_source text)"
            ))
            for eid, commence, status, source in (
                (1, G2, "scheduled", "statpal"),         # retired, source taken
                (2, G2, "scheduled", "mlb_schedule_repair"),  # retired, source kept
                (3, CWS_G1, "scheduled", "statpal"),     # moved under the pass
                (4, G2, "live", "statpal"),              # started under the pass
            ):
                await conn.execute(
                    text("INSERT INTO events VALUES (:i, CAST(:t AS jsonb), :c, :s, :src)"),
                    {"i": eid, "t": json.dumps(tags), "c": commence, "s": status, "src": source},
                )
            landed = [
                await confirm_announced_placeholder(conn, 1, G2, take_source=True),
                await confirm_announced_placeholder(conn, 2, G2, take_source=False),
                await confirm_announced_placeholder(conn, 3, G2, take_source=True),
                await confirm_announced_placeholder(conn, 4, G2, take_source=True),
            ]
            rows = {
                r[0]: (r[1], r[2])
                for r in (await conn.execute(text(
                    "SELECT id, event_tags, commence_time_source FROM events"
                ))).all()
            }
    finally:
        await engine.dispose()

    assert landed == [True, True, False, False]
    kept = [*BASE_TAGS, espn_mark, "sport:baseball", 7]
    assert rows[1] == (kept, "espn")
    assert rows[2] == (kept, "mlb_schedule_repair")
    assert rows[3] == (tags, "statpal")
    assert rows[4] == (tags, "statpal")
