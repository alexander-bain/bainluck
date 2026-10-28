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
        emit=lambda text: lines.append(json.loads(text)), run="t",
    )
    assert trace is not None
    nt.reset_for_tests(trace)
    return lines


def stage(lines, name):
    return [line for line in lines if line["stage"] == name]


def selected_for(lines, line):
    (sel,) = [x for x in stage(lines, "SELECTED") if x["obs"] == line["obs"]]
    return sel


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
    sel = selected_for(lines, pub)
    assert sel["metadata_keys"] == ["betting_book_count"]
    assert sel["evidence"]["decision"] == "admitted"
    assert sel["evidence"]["population"] == [{"book": "a", "home_probability": 0.6}]
    assert sel["seam_mono"] <= pub["returned_mono"] and sel["txn"] == pub["txn"]
    final = pub["final"]
    assert final["final_state"] == "FINAL_STATE_NOT_ESTABLISHED"
    assert final["blend_probability"] == frame["p"] and final["queued_frame_matches"] is True
    assert final["observations_in_txn"] == 1 and final["uncovered_keys"] == []
    # The complete committed bag, recomputed with the hero's own helpers.
    stored = await _stored(pg_engine, event_id)
    assert pub["bag_hash"] == nt._hash(stored) == nt._hash(sources)
    assert {row["source"] for row in pub["bag"]} == {"betting"}
    assert pub["bag_other_keys"] == ["betting_book_count"]
    assert pub["recomputed_p"] == frame["p"] and pub["p_matches"] is True
    assert (pub["txn"], pub["obs"], pub["commit_result"]) == (1, 1, "COMMITTED")
    assert pub["frame_unchanged"] is True
    assert ordered(pub, "returned", "commit_start", "commit_end", "publish_start",
                   "publish_end")
    assert [x["stage"] for x in lines] == ["START", "SELECTED", "PUBLICATION"]
    assert [x["line"] for x in lines] == [1, 2, 3]


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
    assert unsent["carried_by_obs"] == pub["obs"] == unsent["obs"] + 1
    assert unsent["txn"] == pub["txn"]
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
    assert rolled["commit_result"] == {"outer": "ROLLED_BACK", "savepoint": "SAVEPOINT_ROLLED_BACK",
                                       "failed_commit": "COMMIT_FAILED_ROLLED_BACK"}[how]
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
    assert (unsent["reason"], unsent["value"]) == ("SOURCE_REMOVED_NOT_SENT", None)
    sel = selected_for(lines, unsent)
    assert (sel["removed"], sel["removed_sources"]) == (True, ["betting"])
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
                await asyncio.wait_for(task, 5)
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
        ("SELECTED", "espn", None),
        ("SELECTED", "stat_model", None),
        ("SELECTED", "mlb", None),
        ("WRITE_UNSENT", "mlb", "ROLLED_BACK"),
        ("WRITE_UNSENT", "espn", "SUPERSEDED_IN_TRANSACTION"),
        ("PUBLICATION", "stat_model", None),
        ("SELECTED", "betting", None),
        ("WRITE_UNSENT", "betting", "SOURCE_REMOVED_NOT_SENT"),
    ]

    assert sql_off == sql_other == sql_on
    assert frames_off == frames_other == frames_on and len(frames_off) == 1
    assert logs_off == logs_other == logs_on


async def test_a_no_op_rewrite_is_its_own_observation_never_coalesced(pg_engine, sink):
    event_id = await _seed_event(pg_engine)
    lines = arm([event_id])
    async with async_sessionmaker(pg_engine, expire_on_commit=False)() as session:
        event = await session.get(Event, event_id)
        for _ in range(2):
            await write_nonvenue_probability(session, event, "espn", 0.7)
            await session.commit()
            await publish_committed_nonvenue_frames(session)
    first, second = stage(lines, "PUBLICATION")
    assert (first["obs"], second["obs"]) == (1, 2) and first["txn"] != second["txn"]
    one, two = selected_for(lines, first), selected_for(lines, second)
    assert (one["value_unchanged"], two["value_unchanged"]) == (False, True)
    assert two["prior_value"] == 0.7 and second["rev"] > first["rev"]
    assert len(sink) == 2



async def test_a_selection_whose_update_fails_or_finds_no_row_is_closed(pg_engine, sink):
    from sqlalchemy import delete

    event_id = await _seed_event(pg_engine)
    lines = arm([event_id])
    async with async_sessionmaker(pg_engine, expire_on_commit=False)() as session:
        event = await session.get(Event, event_id)
        async with pg_engine.begin() as conn:  # the row vanishes after it was read
            await conn.execute(delete(Event).where(Event.id == event_id))
        assert await write_nonvenue_probability(session, event, "espn", 0.7) is None
        await session.commit()
    (sel,) = stage(lines, "SELECTED")
    (closed,) = stage(lines, "WRITE_UNSENT")
    assert (closed["obs"], closed["reason"]) == (sel["obs"], "MISSING_ROW")
    event_id = await _seed_event(pg_engine)
    lines = arm([event_id])
    async with async_sessionmaker(pg_engine, expire_on_commit=False)() as session:
        event = await session.get(Event, event_id)
        with pytest.raises(Exception):
            await write_nonvenue_probability(session, event, "espn", 0.7,
                                             values={"home_score": "not a number"})
        await session.rollback()
    (sel,) = stage(lines, "SELECTED")
    (closed,) = stage(lines, "WRITE_UNSENT")
    assert (closed["obs"], closed["reason"]) == (sel["obs"], "UPDATE_ERROR")
    assert sink == []


async def test_a_failing_witness_keeps_its_receipt_through_commit_and_publication(
    pg_engine, sink
):
    """lane1b P1: a raising witness must not orphan a write that committed and
    was published (STOP once read ``awaiting_write 1`` for it)."""
    event_id = await _seed_event(pg_engine)
    lines = arm([event_id])
    async with async_sessionmaker(pg_engine, expire_on_commit=False)() as session:
        await write_nonvenue_probability(
            session, await session.get(Event, event_id), "espn", 0.7,
            trace_inputs=lambda: 1 / 0)
        await session.commit()
        await publish_committed_nonvenue_frames(session)
    nt.nonvenue_trace()._stop("EXPIRED")
    assert (await _stored(pg_engine, event_id))["espn"]["value"] == 0.7
    assert [frame["event_id"] for _channel, frame in sink] == [event_id]
    (sel,) = stage(lines, "SELECTED")
    (pub,) = stage(lines, "PUBLICATION")
    assert sel["inputs"] == "WITNESS_ERROR" and pub["obs"] == sel["obs"]
    assert pub["result"] == "SENT"
    (stop,) = stage(lines, "STOP")
    assert (stop["observations"], stop["published"], stop["awaiting_write"],
            stop["awaiting_publication"], stop["hook_errors"]) == (1, 1, 0, 0, 1)


async def test_the_real_betting_ingest_receipts_per_book_versions(pg_engine, sink):
    """Real `OddsSnapshot` rows through the real producer: an unchanged book
    names its stored row and ``captured_at`` (a datetime, printed as ISO text,
    never "NESTED"); a NEW book's ``snapshot_id`` is null (unflushed at
    selection)."""
    from datetime import datetime, timezone

    from sqlalchemy import delete, select

    from app.models.models import OddsSnapshot
    from app.tasks.odds_polling import _ingest_event_odds

    async with pg_engine.begin() as conn:
        await conn.run_sync(lambda c: OddsSnapshot.__table__.create(c, checkfirst=True))

    def book(key, home, away, minute):
        return {"key": key, "last_update": f"2026-10-28T18:0{minute}:00Z", "markets": [
            {"key": "h2h", "outcomes": [{"name": "Twins", "price": home},
                                        {"name": "Yankees", "price": away}]}]}

    def odds(changed_price, minute):
        return {"home_team": "Twins", "away_team": "Yankees", "bookmakers": [
            book("b0", -150, 130, minute), book("b1", changed_price, 135, minute),
            book("b2", -145, 125, minute)]}

    event_id = await _seed_event(pg_engine)
    try:
        session_maker = async_sessionmaker(pg_engine, expire_on_commit=False)
        async with session_maker() as session:  # untraced first pass: the stored rows
            await _ingest_event_odds(session, await session.get(Event, event_id),
                                     odds(-160, 0), datetime.now(timezone.utc), {},
                                     update_opening=False)
            await session.commit()
        async with pg_engine.connect() as conn:
            stored = {row.bookmaker: row for row in (await conn.execute(
                select(OddsSnapshot.id, OddsSnapshot.bookmaker, OddsSnapshot.captured_at)
                .where(OddsSnapshot.event_id == event_id))).all()}
        lines = arm([event_id])
        async with session_maker() as session:  # b1 reprices; b0 and b2 do not
            await _ingest_event_odds(session, await session.get(Event, event_id),
                                     odds(-170, 1), datetime.now(timezone.utc), {},
                                     update_opening=False)
            await session.commit()
            await publish_committed_nonvenue_frames(session)
    finally:
        async with pg_engine.begin() as conn:
            await conn.execute(delete(OddsSnapshot).where(OddsSnapshot.event_id == event_id))
    (sel,) = stage(lines, "SELECTED")
    inputs = sel["inputs"]
    assert inputs["upstream_clock_domain"] == "ODDS_API_BOOKMAKER_LAST_UPDATE"
    books = {b["book"]: b for b in inputs["books"]}
    assert list(books) == ["b0", "b1", "b2"]
    for key in ("b0", "b2"):  # unchanged: the stored row and how old its price is
        assert books[key]["new_snapshot"] is False
        assert books[key]["snapshot_id"] == stored[key].id
        assert books[key]["captured_at"] == stored[key].captured_at.isoformat()
    assert books["b1"]["new_snapshot"] is True and books["b1"]["snapshot_id"] is None
    repriced = datetime.fromisoformat(books["b1"]["captured_at"])
    assert repriced > stored["b1"].captured_at
    assert books["b1"]["bookmaker_last_update"] == "2026-10-28T18:01:00Z"
    assert inputs["select_start"]["mono"] <= inputs["select_end"]["mono"] <= sel["seam_mono"]
    (pub,) = stage(lines, "PUBLICATION")
    assert pub["obs"] == sel["obs"] and pub["final"]["queued_frame_matches"] is True
