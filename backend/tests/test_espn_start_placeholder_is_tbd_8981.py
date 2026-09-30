"""#8981: ESPN's date-only placeholder is marked, so a reader sees "TBD".

Specimen: Clemson–Miami, row 14870012 / ESPN 401858249. ESPN's scoreboard
(read 2026-09-27 00:00Z) lists it at ``2026-10-03T04:00Z`` with
``competitions[0].timeValid=false`` and status "10/3 - TBD". The row sat on
that instant with no mark, so `/api/events/14870012` served
``start_is_tbd: false`` and the page read "Oct 2, 2026 · 9:00 PM PDT · Starts
in 6d 4h".
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from app.tasks import espn_start_placeholders as task
from app.tasks.espn_start_placeholders import (
    CandidateRow,
    board_day,
    candidate_statement,
    group_by_board,
    plan_row,
)
from app.utils.start_placeholder import (
    ESPN_START_PLACEHOLDER_TAG_PREFIX,
    START_PLACEHOLDER_TAG_PREFIX,
    desired_espn_start_placeholder_tags,
    espn_start_placeholder_tag,
    start_is_tbd,
    start_placeholder_tag,
    start_placeholder_tags,
)

#: 401858249 as ESPN lists it: midnight Eastern (EDT) on the game's date.
CLEMSON_MIAMI = datetime(2026, 10, 3, 4, 0, tzinfo=timezone.utc)
#: 401858296 Miami v Duke: midnight Eastern under EST.
MIAMI_DUKE = datetime(2026, 11, 14, 5, 0, tzinfo=timezone.utc)
TAG = "provenance:start-placeholder:espn:2026-10-03T04:00Z"
#: 401858249 once ESPN announced it (read 2026-09-27 04:47Z): 7:30 PM EDT.
ANNOUNCED = datetime(2026, 10, 3, 23, 30, tzinfo=timezone.utc)


def _ee(espn_id="401858249", date=CLEMSON_MIAMI, *, time_valid, time_announced):
    return SimpleNamespace(
        espn_id=espn_id, date=date, time_valid=time_valid, time_announced=time_announced,
    )


def _tbd_ee(**kw):
    return _ee(time_valid=False, time_announced=False, **kw)


def _announced_ee(**kw):
    return _ee(time_valid=True, time_announced=True, **kw)


def _silent_ee(**kw):
    """The flag absent: `time_valid` defaults True, but nothing was announced."""
    return _ee(time_valid=True, time_announced=False, **kw)


def _row(commence=CLEMSON_MIAMI, tags=None, espn_id="401858249", event_id=14870012):
    return CandidateRow(
        event_id=event_id, sport_key="americanfootball_ncaaf", espn_id=espn_id,
        commence_time=commence, event_tags=tags if tags is not None else [],
    )


# ─────────────────────────────────────────────────────────────────────────────
# 1. What ESPN's reading asks of the row
# ─────────────────────────────────────────────────────────────────────────────

class TestDesiredTags:
    def test_the_specimen_is_marked(self):
        assert desired_espn_start_placeholder_tags(
            time_valid=False, time_announced=False,
            espn_date=CLEMSON_MIAMI, commence_time=CLEMSON_MIAMI,
        ) == [TAG]

    def test_the_tag_names_the_instant_it_vouches_for(self):
        assert espn_start_placeholder_tag(CLEMSON_MIAMI) == TAG
        assert espn_start_placeholder_tag(MIAMI_DUKE).endswith("2026-11-14T05:00Z")

    def test_a_row_another_rail_moved_is_not_marked(self):
        assert desired_espn_start_placeholder_tags(
            time_valid=False, time_announced=False,
            espn_date=CLEMSON_MIAMI, commence_time=CLEMSON_MIAMI + timedelta(hours=15, minutes=30),
        ) == []

    def test_an_announced_start_the_row_does_not_carry_keeps_the_mark(self):
        # Production 2026-09-27: ESPN announced 401858249 for 7:30 PM EDT
        # (23:30Z). The row still sat on 04:00Z, and clearing the mark served
        # "Oct 2 9:00 PM PDT" again. Nothing has written the real time yet, so
        # the row's own stamp is still a stand-in.
        assert desired_espn_start_placeholder_tags(
            time_valid=True, time_announced=True,
            espn_date=ANNOUNCED,
            commence_time=CLEMSON_MIAMI,
        ) == [TAG]

    def test_the_kept_mark_names_the_rows_stamp_not_espns(self):
        kept = desired_espn_start_placeholder_tags(
            time_valid=True, time_announced=True,
            espn_date=ANNOUNCED, commence_time=CLEMSON_MIAMI,
        )
        assert kept == [espn_start_placeholder_tag(CLEMSON_MIAMI)]
        assert kept != [espn_start_placeholder_tag(ANNOUNCED)]

    def test_an_announced_start_on_the_placeholder_minute_clears_it_too(self):
        # A real Hawaii kickoff (7 PM HST in November) IS 05:00Z. ESPN saying
        # timeValid: true at that minute is the only thing that tells it apart.
        assert desired_espn_start_placeholder_tags(
            time_valid=True, time_announced=True,
            espn_date=MIAMI_DUKE, commence_time=MIAMI_DUKE,
        ) == []

    def test_an_absent_flag_changes_nothing(self):
        assert desired_espn_start_placeholder_tags(
            time_valid=True, time_announced=False,
            espn_date=CLEMSON_MIAMI, commence_time=CLEMSON_MIAMI,
        ) is None


# ─────────────────────────────────────────────────────────────────────────────
# 2. What the reader is served
# ─────────────────────────────────────────────────────────────────────────────

class TestStartIsTbd:
    def test_the_specimen_reads_tbd(self):
        assert start_is_tbd(["sport:football", TAG], CLEMSON_MIAMI, "scheduled") is True

    def test_before_the_mark_it_did_not(self):
        assert start_is_tbd(["sport:football"], CLEMSON_MIAMI, "scheduled") is False

    def test_a_real_kickoff_written_by_any_rail_retires_it(self):
        real = CLEMSON_MIAMI + timedelta(hours=19, minutes=30)
        assert start_is_tbd([TAG], real, "scheduled") is False

    @pytest.mark.parametrize("status", ["live", "completed", "suspended", None])
    def test_only_a_scheduled_game_can_be_tbd(self, status):
        assert start_is_tbd([TAG], CLEMSON_MIAMI, status) is False

    def test_a_naive_stamp_reads_as_utc(self):
        assert start_is_tbd([TAG], CLEMSON_MIAMI.replace(tzinfo=None), "scheduled") is True

    def test_statpals_mark_still_counts(self):
        stamp = datetime(2026, 9, 29, 20, 0, tzinfo=timezone.utc)
        assert start_is_tbd([start_placeholder_tag(stamp)], stamp, "scheduled") is True

    def test_the_two_providers_marks_are_disjoint(self):
        # StatPal's schedule pass rewrites every tag `start_placeholder_tags`
        # returns. If that set ever included ESPN's, StatPal would erase it.
        assert not TAG.startswith(START_PLACEHOLDER_TAG_PREFIX)
        assert start_placeholder_tags([TAG]) == []
        assert TAG.startswith(ESPN_START_PLACEHOLDER_TAG_PREFIX)
        # And the carry across the taxonomy task's wholesale replace keys on this.
        assert TAG.startswith("provenance:")


# ─────────────────────────────────────────────────────────────────────────────
# 3. One row against its day's board
# ─────────────────────────────────────────────────────────────────────────────

class TestPlanRow:
    def test_the_specimen_is_marked(self):
        assert plan_row(_row(), {"401858249": _tbd_ee()}) == ("mark", [TAG])

    def test_an_already_marked_row_is_left_alone(self):
        assert plan_row(_row(tags=["x", TAG]), {"401858249": _tbd_ee()}) == ("unchanged", None)

    def test_an_announced_kickoff_clears_a_stale_mark(self):
        assert plan_row(_row(tags=[TAG]), {"401858249": _announced_ee()}) == ("clear", [])

    def test_the_specimen_after_espn_announced_is_marked_again(self):
        # The production state this fix heals: the mark already cleared, the
        # row still on 04:00Z, ESPN now at 23:30Z with timeValid true.
        board = {"401858249": _announced_ee(date=ANNOUNCED)}
        assert plan_row(_row(tags=["sport:football"]), board) == ("mark", [TAG])

    def test_a_marked_row_keeps_its_mark_when_espn_announces_another_time(self):
        board = {"401858249": _announced_ee(date=ANNOUNCED)}
        assert plan_row(_row(tags=[TAG]), board) == ("unchanged", None)

    def test_the_reader_sees_tbd_until_the_announced_time_is_written(self):
        board = {"401858249": _announced_ee(date=ANNOUNCED)}
        _outcome, desired = plan_row(_row(tags=[]), board)
        assert start_is_tbd(desired, CLEMSON_MIAMI, "scheduled") is True
        # The nightly move (#3023) writes 23:30Z; the kept mark goes inert.
        assert start_is_tbd(desired, ANNOUNCED, "scheduled") is False

    def test_an_announced_kickoff_on_an_unmarked_row_writes_nothing(self):
        assert plan_row(_row(commence=MIAMI_DUKE), {"401858249": _announced_ee(date=MIAMI_DUKE)}) == (
            "unchanged", None,
        )

    def test_a_silent_board_writes_nothing(self):
        assert plan_row(_row(tags=[TAG]), {"401858249": _silent_ee()}) == ("silent", None)

    def test_a_game_missing_from_the_board_writes_nothing(self):
        assert plan_row(_row(tags=[TAG]), {"401858999": _tbd_ee(espn_id="401858999")}) == (
            "not_on_board", None,
        )

    def test_the_join_is_the_espn_id_not_the_clock(self):
        # Another TBD game on the same board, same minute, must not mark this row.
        board = {"401858250": _tbd_ee(espn_id="401858250")}
        assert plan_row(_row(), board)[0] == "not_on_board"


class TestBoards:
    def test_a_placeholder_sits_on_its_own_eastern_day(self):
        assert board_day(CLEMSON_MIAMI) == "20261003"
        assert board_day(MIAMI_DUKE) == "20261114"
        assert board_day(CLEMSON_MIAMI.replace(tzinfo=None)) == "20261003"

    def test_rows_are_grouped_one_read_per_sport_and_day(self):
        rows = [
            _row(event_id=1, espn_id="1"),
            _row(event_id=2, espn_id="2"),
            _row(event_id=3, espn_id="3", commence=MIAMI_DUKE),
        ]
        grouped = group_by_board(rows)
        assert sorted(grouped) == [
            ("americanfootball_ncaaf", "20261003"),
            ("americanfootball_ncaaf", "20261114"),
        ]
        assert [r.event_id for r in grouped[("americanfootball_ncaaf", "20261003")]] == [1, 2]

    def test_the_candidate_query_nominates_by_the_utc_clock(self):
        from sqlalchemy.dialects import postgresql

        sql = str(
            candidate_statement(datetime(2026, 9, 27, tzinfo=timezone.utc)).compile(
                dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}
            )
        )
        assert "timezone('UTC', events.commence_time)" in sql
        assert "EXTRACT(hour FROM timezone('UTC', events.commence_time)) IN (4, 5)" in sql
        assert "EXTRACT(minute FROM timezone('UTC', events.commence_time)) = 0" in sql
        assert "events.status = 'scheduled'" in sql
        assert "events.espn_id IS NOT NULL" in sql


# ─────────────────────────────────────────────────────────────────────────────
# 4. The pass
# ─────────────────────────────────────────────────────────────────────────────

class _Result:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return self._rows


class _Session:
    def __init__(self, rows):
        self.rows = rows
        self.commits = 0

    async def execute(self, stmt):
        return _Result(self.rows)

    async def commit(self):
        self.commits += 1


class _Ctx:
    def __init__(self, session):
        self.session = session

    async def __aenter__(self):
        return self.session

    async def __aexit__(self, *exc):
        return False


def _wire(monkeypatch, *, rows, boards):
    import app.services.espn_api as espn_api
    import app.tasks.base as task_base
    import app.utils.start_placeholder_write as writer

    session = _Session(rows)
    reads: list[tuple] = []
    writes: list[tuple] = []

    class _Espn:
        async def get_scoreboard(self, sport_key, date=None, groups=None):
            reads.append((sport_key, date, groups))
            board = boards.get((sport_key, date))
            if isinstance(board, Exception):
                raise board
            return board

        async def close(self):
            pass

    async def _write(sess, event_id, desired):
        writes.append((event_id, list(desired)))

    monkeypatch.setattr(task_base, "get_task_session", lambda: _Ctx(session))
    monkeypatch.setattr(espn_api, "ESPNAPIService", lambda *a, **kw: _Espn())
    monkeypatch.setattr(writer, "write_espn_start_placeholder_tags", _write)
    return session, reads, writes


def _db_row(event_id, espn_id, commence, tags=None, sport="americanfootball_ncaaf"):
    return (event_id, sport, espn_id, commence, tags or [], "espn", None, None)


@pytest.mark.asyncio
async def test_the_pass_marks_the_specimen_and_reads_the_fbs_board(monkeypatch):
    session, reads, writes = _wire(
        monkeypatch,
        rows=[_db_row(14870012, "401858249", CLEMSON_MIAMI)],
        boards={("americanfootball_ncaaf", "20261003"): [_tbd_ee()]},
    )
    stats = await task._run_mark_espn_start_placeholders(apply=True)
    assert reads == [("americanfootball_ncaaf", "20261003", "80")]
    assert writes == [(14870012, [TAG])]
    assert session.commits == 1
    assert stats["mark"] == 1 and stats["marked_ids"] == [14870012]
    assert stats["status"] == "complete"


@pytest.mark.asyncio
async def test_a_dry_run_plans_and_writes_nothing(monkeypatch):
    session, _, writes = _wire(
        monkeypatch,
        rows=[_db_row(14870012, "401858249", CLEMSON_MIAMI)],
        boards={("americanfootball_ncaaf", "20261003"): [_tbd_ee()]},
    )
    stats = await task._run_mark_espn_start_placeholders(apply=False)
    assert writes == [] and session.commits == 0
    assert stats["marked_ids"] == [14870012]


@pytest.mark.asyncio
async def test_a_dark_board_moves_nothing_and_a_failed_read_costs_only_its_day(monkeypatch):
    rows = [
        _db_row(1, "401858249", CLEMSON_MIAMI, tags=[TAG]),
        _db_row(2, "401858296", MIAMI_DUKE),
        _db_row(3, "401858263", datetime(2026, 10, 17, 4, 0, tzinfo=timezone.utc)),
    ]
    _, reads, writes = _wire(
        monkeypatch,
        rows=rows,
        boards={
            ("americanfootball_ncaaf", "20261003"): None,  # ESPN did not answer
            ("americanfootball_ncaaf", "20261114"): RuntimeError("boom"),
            ("americanfootball_ncaaf", "20261017"): [
                _tbd_ee(espn_id="401858263", date=datetime(2026, 10, 17, 4, 0, tzinfo=timezone.utc)),
            ],
        },
    )
    stats = await task._run_mark_espn_start_placeholders(apply=True)
    assert len(reads) == 3
    assert writes == [(3, ["provenance:start-placeholder:espn:2026-10-17T04:00Z"])]
    assert stats["boards_dark"] == 1 and len(stats["errors"]) == 1
    assert stats["status"] == "partial"


@pytest.mark.asyncio
async def test_no_candidates_reads_nothing(monkeypatch):
    _, reads, writes = _wire(monkeypatch, rows=[], boards={})
    stats = await task._run_mark_espn_start_placeholders(apply=True)
    assert reads == [] and writes == []
    assert stats["status"] == "no_candidates"


@pytest.mark.asyncio
async def test_reads_are_capped(monkeypatch):
    monkeypatch.setattr(task, "MAX_BOARDS", 2)
    rows = [
        _db_row(i, str(i), CLEMSON_MIAMI + timedelta(days=i)) for i in range(5)
    ]
    _, reads, _ = _wire(monkeypatch, rows=rows, boards={})
    stats = await task._run_mark_espn_start_placeholders(apply=True)
    assert len(reads) == 2
    assert stats["boards_skipped_cap"] == 3


# ─────────────────────────────────────────────────────────────────────────────
# 5. The rewrite, on real Postgres: each provider touches only its own marks
# ─────────────────────────────────────────────────────────────────────────────

DB_URL = os.environ.get("START_PLACEHOLDER_DATABASE_URL")


@pytest.mark.asyncio
@pytest.mark.skipif(
    not DB_URL,
    reason="set START_PLACEHOLDER_DATABASE_URL (asyncpg URL to a scratch DB) "
    "to run the JSONB rewrite against real Postgres",
)
async def test_espn_and_statpal_rewrites_never_erase_each_other_on_postgres():
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import create_async_engine

    from app.utils.start_placeholder_write import (
        write_espn_start_placeholder_tags,
        write_start_placeholder_tags,
    )

    statpal = start_placeholder_tag(datetime(2026, 9, 29, 20, 0, tzinfo=timezone.utc))
    engine = create_async_engine(DB_URL)
    try:
        async with engine.begin() as conn:
            await conn.execute(text(
                "CREATE TEMP TABLE events (id int PRIMARY KEY, event_tags jsonb)"
            ))
            await conn.execute(
                text("INSERT INTO events VALUES (1, CAST(:a AS jsonb)), (2, CAST(:b AS jsonb)), (3, NULL)"),
                {
                    "a": json.dumps(["sport:football", statpal]),
                    "b": json.dumps(["tier:1", TAG, statpal]),
                },
            )
            await write_espn_start_placeholder_tags(conn, 1, [TAG])
            await write_start_placeholder_tags(conn, 2, [])  # StatPal clears ITS mark
            await write_espn_start_placeholder_tags(conn, 3, [TAG])
            rows = dict((await conn.execute(text("SELECT id, event_tags FROM events"))).all())
            await write_espn_start_placeholder_tags(conn, 2, [])  # ESPN clears ITS mark
            row2 = (await conn.execute(text("SELECT event_tags FROM events WHERE id = 2"))).scalar()
    finally:
        await engine.dispose()

    assert rows[1] == ["sport:football", statpal, TAG]
    assert rows[2] == ["tier:1", TAG]
    assert rows[3] == [TAG]
    assert row2 == ["tier:1"]
