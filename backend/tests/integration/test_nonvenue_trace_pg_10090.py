"""#10090: the nonvenue receipt on real PostgreSQL transactions.

PILLARS: TRUTH / FORMATTING. SHIP: the acceptance case can be scored on an
ordinary held page whose headline moved because a sportsbook, ESPN or model
reading changed.

The real `write_nonvenue_probability` UPDATE, the real SQLAlchemy commit,
rollback and savepoint events, and the real publisher run against a disposable
database. These pin:

* a committed write's PUBLICATION carries the same rev and stamp the database
  kept and the frame the reader receives, with ordered worker clocks from
  RETURNING through COMMIT to the Redis reply;
* every traced write that never reaches a reader is named: rolled back (outer,
  savepoint, failed COMMIT), superseded by a later write of the same event in
  the same transaction (naming the rev that carried it), or a removal;
* a failed fanout names what it attempted and what it never handed over;
* disarmed, armed on another event, and armed on this event issue the SAME SQL,
  the same Redis frames and the same application log lines.
"""

import json
import logging
import re

import pytest
from sqlalchemy import event as sa_event
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.models.models import Event
from app.utils import nonvenue_trace as nt
from app.utils.nonvenue_live_push import (
    publish_committed_nonvenue_frames,
    write_nonvenue_probability,
)
from tests.integration.test_live_blend_concurrent_stamp_pg import (
    _seed_event,
    _stored,
    needs_postgres,
    pg_engine as _pg_engine,
)
from tests.integration.test_nonvenue_live_push_pg_8761 import sink as _sink

pg_engine = _pg_engine
sink = _sink
pytestmark = needs_postgres


@pytest.fixture(autouse=True)
def _reset():
    nt.reset_for_tests()
    yield
    nt.reset_for_tests()


def arm(events):
    """Install an armed trace for ``events``; returns its emitted lines."""
    import time

    lines = []
    trace = nt.NonvenueTrace.from_env(
        {"NONVENUE_TRACE_EVENTS": ",".join(str(e) for e in events),
         "NONVENUE_TRACE_EXPIRES_AT": str(time.time() + 300),
         "NONVENUE_TRACE_MAX_LINES": "256"},
        emit=lambda record: lines.append(json.loads(json.dumps(record))), run="t",
    )
    assert trace is not None
    nt.reset_for_tests(trace)
    return lines


def stage(lines, name):
    return [line for line in lines if line["stage"] == name]


def ordered(line, *clocks):
    monos = [line[f"{c}_mono"] for c in clocks]
    walls = [line[f"{c}_wall"] for c in clocks]
    return monos == sorted(monos) and walls == sorted(walls)


async def test_committed_write_publication_carries_the_kept_rev_and_stamp(pg_engine, sink):
    event_id = await _seed_event(pg_engine)
    lines = arm([event_id])
    async with async_sessionmaker(pg_engine, expire_on_commit=False)() as session:
        event = await session.get(Event, event_id)
        sources = await write_nonvenue_probability(
            session, event, "betting", 0.6, metadata={"betting_book_count": 3},
            evidence={"rule": "median", "floor": 2, "decision": "admitted", "median": 0.6,
                      "split_pair": None,
                      "population": [{"book": "a", "home_probability": 0.6}]},
        )
        assert stage(lines, "PUBLICATION") == []
        await session.commit()
        assert stage(lines, "PUBLICATION") == [], "committed is not published"
        await publish_committed_nonvenue_frames(session)
    (pub,) = stage(lines, "PUBLICATION")
    (channel, frame), = sink
    async with pg_engine.connect() as conn:
        from sqlalchemy import select

        rev = (await conn.execute(select(Event.win_probability_sources_rev)
                                  .where(Event.id == event_id))).scalar_one()
    assert (pub["event"], pub["source"], pub["value"], pub["result"]) == (
        event_id, "betting", 0.6, "SENT")
    assert pub["rev"] == rev == frame["rev"][str(event_id)]
    assert pub["stamped_at"] == sources["betting"]["updated_at"] == frame["updated_at"]
    assert pub["p"] == frame["p"] and pub["status"] == "live"
    assert pub["metadata_keys"] == ["betting_book_count"]
    assert pub["evidence"]["decision"] == "admitted"
    assert pub["evidence"]["population"] == [{"book": "a", "home_probability": 0.6}]
    assert ordered(pub, "returned", "commit_start", "commit_end", "publish_start", "publish_end")
    assert [x["stage"] for x in lines] == ["START", "PUBLICATION"]


async def test_two_writes_in_one_transaction_name_the_rev_that_carried_the_first(
    pg_engine, sink
):
    event_id = await _seed_event(pg_engine)
    lines = arm([event_id])
    async with async_sessionmaker(pg_engine, expire_on_commit=False)() as session:
        event = await session.get(Event, event_id)
        await write_nonvenue_probability(session, event, "espn", 0.7)
        async with session.begin_nested():  # a released savepoint is not a commit
            later = await write_nonvenue_probability(session, event, "stat_model", 0.65)
        await session.commit()
        await publish_committed_nonvenue_frames(session)
    (unsent,) = stage(lines, "WRITE_UNSENT")
    (pub,) = stage(lines, "PUBLICATION")
    assert (unsent["source"], unsent["reason"]) == ("espn", "SUPERSEDED_IN_TRANSACTION")
    assert unsent["carried_by_source"] == "stat_model"
    assert unsent["carried_by_rev"] == pub["rev"] == sink[0][1]["rev"][str(event_id)]
    assert unsent["rev"] < pub["rev"]
    assert ordered(unsent, "returned", "commit_start", "commit_end")
    assert pub["stamped_at"] == later["stat_model"]["updated_at"]


@pytest.mark.parametrize("how", ["outer", "savepoint", "failed_commit"])
async def test_rolled_back_writes_are_named_never_published(pg_engine, sink, how):
    event_id = await _seed_event(pg_engine)
    lines = arm([event_id])
    async with async_sessionmaker(pg_engine, expire_on_commit=False)() as session:
        event = await session.get(Event, event_id)
        if how == "savepoint":
            await write_nonvenue_probability(session, event, "mlb", 0.6)
            async with session.begin_nested() as nested:
                await write_nonvenue_probability(session, event, "stat_model", 0.1)
                await nested.rollback()
            await session.commit()
        else:
            await write_nonvenue_probability(session, event, "stat_model", 0.1)
            if how == "failed_commit":
                def fail(_):
                    raise RuntimeError("commit failed")

                sa_event.listen(session.sync_session, "before_commit", fail, once=True)
                with pytest.raises(RuntimeError):
                    await session.commit()
            await session.rollback()
        await publish_committed_nonvenue_frames(session)
    (rolled,) = stage(lines, "WRITE_UNSENT")
    assert (rolled["source"], rolled["reason"]) == ("stat_model", "ROLLED_BACK")
    assert ("commit_start_mono" in rolled) == (how == "failed_commit")
    assert "stat_model" not in await _stored(pg_engine, event_id)
    if how == "savepoint":
        (pub,) = stage(lines, "PUBLICATION")
        assert pub["source"] == "mlb" and [f["source"] for _, f in sink] == ["mlb"]
    else:
        assert stage(lines, "PUBLICATION") == [] and sink == []


async def test_a_removal_is_named_as_never_sent(pg_engine, sink):
    event_id = await _seed_event(pg_engine, {"betting": 0.1, "kalshi": 0.8})
    lines = arm([event_id])
    async with async_sessionmaker(pg_engine, expire_on_commit=False)() as session:
        event = await session.get(Event, event_id)
        await write_nonvenue_probability(session, event, "betting", None,
                                         metadata={"betting_book_count": 1})
        await session.commit()
        await publish_committed_nonvenue_frames(session)
    (unsent,) = stage(lines, "WRITE_UNSENT")
    assert (unsent["reason"], unsent["removed"], unsent["value"]) == (
        "SOURCE_REMOVED_NOT_SENT", True, None)
    assert sink == []


@pytest.mark.parametrize("failure", ["client_error", "no_client", "hang", "cancelled"])
async def test_a_failed_fanout_names_attempted_and_never_handed_over(
    pg_engine, sink, monkeypatch, failure
):
    import asyncio

    first, second = await _seed_event(pg_engine), await _seed_event(pg_engine)
    lines = arm([first, second])
    entered = asyncio.Event()

    class Client:
        async def execute_command(self, *command):
            if failure == "client_error":
                raise ConnectionError("Redis down")
            entered.set()
            await asyncio.sleep(30)  # a publish that never answers

        async def aclose(self):
            pass

    def build():
        if failure == "no_client":
            raise RuntimeError("no Redis client")
        return Client()

    monkeypatch.setattr("app.tasks.redis_state.get_async_redis_client", build)
    async with async_sessionmaker(pg_engine, expire_on_commit=False)() as session:
        for event_id in (first, second):
            await write_nonvenue_probability(
                session, await session.get(Event, event_id), "mlb", 0.6)
        await session.commit()
        if failure == "hang":
            real = asyncio.timeout
            monkeypatch.setattr(asyncio, "timeout", lambda _s: real(0.05))
            await publish_committed_nonvenue_frames(session)
            monkeypatch.setattr(asyncio, "timeout", real)
        elif failure == "cancelled":
            task = asyncio.create_task(publish_committed_nonvenue_frames(session))
            await asyncio.wait_for(entered.wait(), 5)
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task
        else:
            await publish_committed_nonvenue_frames(session)
    results = [(line["event"], line["result"]) for line in stage(lines, "PUBLICATION")]
    expected = {
        "client_error": [(first, "NOT_SENT"), (second, "NOT_SENT")],
        "no_client": [(first, "NOT_ATTEMPTED_AFTER_ERROR"),
                      (second, "NOT_ATTEMPTED_AFTER_ERROR")],
        "hang": [(first, "TIMEOUT"), (second, "NOT_ATTEMPTED_AFTER_TIMEOUT")],
        "cancelled": [(first, "CANCELLED"), (second, "NOT_ATTEMPTED_AFTER_CANCELLED")],
    }[failure]
    assert results == expected
    handed = stage(lines, "PUBLICATION")[0]
    assert ("publish_start_mono" in handed) == (failure != "no_client")
    assert (await _stored(pg_engine, first))["mlb"]["value"] == 0.6


async def test_disarmed_and_armed_issue_the_same_sql_frames_and_app_logs(
    pg_engine, sink, caplog
):
    """The byte-identity control: only `nonvenue-trace` lines differ."""

    async def scenario(arming=None):
        event_id = await _seed_event(pg_engine)
        traced = None if arming is None else arming(event_id)
        sql = []

        def record(conn, cursor, statement, *args):
            sql.append(statement)

        sa_event.listen(pg_engine.sync_engine, "before_cursor_execute", record)
        start = len(sink)
        caplog.clear()
        try:
            async with async_sessionmaker(pg_engine, expire_on_commit=False)() as session:
                event = await session.get(Event, event_id)
                await write_nonvenue_probability(session, event, "espn", 0.7)
                await write_nonvenue_probability(session, event, "stat_model", 0.65)
                async with session.begin_nested() as nested:
                    await write_nonvenue_probability(session, event, "mlb", 0.1)
                    await nested.rollback()
                await session.commit()
                await publish_committed_nonvenue_frames(session)
                await write_nonvenue_probability(session, event, "betting", None)
                await session.commit()
                await publish_committed_nonvenue_frames(session)
        finally:
            sa_event.remove(pg_engine.sync_engine, "before_cursor_execute", record)
        frames = [
            (re.sub(r"\d+", "N", channel),
             {k: ("CLOCK" if k == "updated_at" else "REV" if k == "rev" else
                  "EVENT" if k == "event_id" else v) for k, v in frame.items()})
            for channel, frame in sink[start:]
        ]
        logs = [(r.name, r.levelno, r.getMessage().replace(str(event_id), "EVENT"))
                for r in caplog.records if r.name != nt.logger.name]
        return traced, sql, frames, logs

    caplog.set_level(logging.DEBUG)
    nt.reset_for_tests()
    _, sql_off, frames_off, logs_off = await scenario()
    assert nt.nonvenue_trace() is None  # disarmed: built from an empty environment
    other, sql_other, frames_other, logs_other = await scenario(lambda _e: arm([10**11]))
    assert [x["stage"] for x in other] == ["START"]
    lines, sql_on, frames_on, logs_on = await scenario(lambda e: arm([e]))
    assert [(x["stage"], x.get("source"), x.get("reason")) for x in lines] == [
        ("START", None, None),
        ("WRITE_UNSENT", "mlb", "ROLLED_BACK"),
        ("WRITE_UNSENT", "espn", "SUPERSEDED_IN_TRANSACTION"),
        ("PUBLICATION", "stat_model", None),
        ("WRITE_UNSENT", "betting", "SOURCE_REMOVED_NOT_SENT"),
    ]

    assert sql_off == sql_other == sql_on
    assert frames_off == frames_other == frames_on and len(frames_off) == 1
    assert logs_off == logs_other == logs_on
