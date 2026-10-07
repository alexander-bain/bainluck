"""Only a successful outer commit may invalidate a reader's market payload."""

import asyncio
import json
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from redis.exceptions import ResponseError, ConnectionError
from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import Session

from app.utils import market_quote_push as push

STAMP = datetime(2026, 9, 29, tzinfo=timezone.utc)


class FakeRedis:
    """Ordered protocol replies; the baseline single-command API also works."""

    def __init__(self, replies=None):
        self.commands = []
        self.replies = iter(replies) if replies is not None else None
        self.read_counts = []
        self.connection = SimpleNamespace(
            pack_commands=Mock(side_effect=list),
            send_packed_command=AsyncMock(side_effect=self.send),
            read_response=AsyncMock(side_effect=self.read),
            disconnect=AsyncMock(),
        )
        self.connection_pool = SimpleNamespace(
            get_connection=AsyncMock(return_value=self.connection), release=AsyncMock()
        )
        self.publish = AsyncMock(side_effect=self.legacy_publish)

    async def legacy_publish(self, channel, raw):
        self.commands.append(("PUBLISH", channel, raw))
        return await self.read()

    async def send(self, commands):
        self.read_counts.append(self.connection.read_response.await_count)
        self.commands.extend(commands)

    async def read(self):
        response = next(self.replies) if self.replies is not None else 0
        if isinstance(response, BaseException):
            raise response
        return response


@pytest.fixture
def session():
    engine = create_engine("sqlite://")
    with Session(engine) as sync:
        yield SimpleNamespace(sync_session=sync, info=sync.info)
    engine.dispose()


def queue(session, mid=1, oid=11, stamp=STAMP, **kwargs):
    push.queue_market_change(
        session,
        market_id=mid,
        source="kalshi",
        outcome_observed_at={oid: stamp},
        **kwargs,
    )


async def test_commit_coalesces_exact_returned_rows_and_never_sends_prices(session):
    redis = FakeRedis()
    with session.sync_session.begin():
        queue(session)
        queue(session, oid=12, stamp=STAMP + timedelta(seconds=1))
        queue(session, mid=2, oid=21)
        assert await push.publish_committed_market_changes(session, redis) == 0
    assert await push.publish_committed_market_changes(session, redis) == 2
    _, channel, raw = redis.commands[0]
    frame = json.loads(raw)
    assert channel == "live:market:1"
    assert frame["outcome_ids"] == [11, 12]
    assert frame["outcome_observed_at"] == {
        "11": STAMP.isoformat(),
        "12": (STAMP + timedelta(seconds=1)).isoformat(),
    }
    assert frame["updated_at"] == (STAMP + timedelta(seconds=1)).isoformat()
    assert frame["terminal"] is False
    assert not {"p", "probability", "status", "rev"} & frame.keys()
    assert push.parse_market_frame(raw) == frame
    assert await push.publish_committed_market_changes(session, redis) == 0


async def test_rollback_and_failed_commit_publish_nothing(session):
    redis = FakeRedis()
    session.sync_session.begin()
    queue(session)
    session.sync_session.rollback()
    assert await push.publish_committed_market_changes(session, redis) == 0

    def fail(_session):
        raise RuntimeError("commit failed")

    event.listen(session.sync_session, "before_commit", fail)
    session.sync_session.begin()
    queue(session)
    with pytest.raises(RuntimeError, match="commit failed"):
        session.sync_session.commit()
    session.sync_session.rollback()
    assert await push.publish_committed_market_changes(session, redis) == 0
    redis.publish.assert_not_awaited()


async def test_savepoint_release_waits_for_outer_commit_and_rollback_discards_only_its_rows(
    session,
):
    redis = FakeRedis()
    with session.sync_session.begin():
        queue(session, oid=11)
        with session.sync_session.begin_nested():
            queue(session, oid=12)
        assert await push.publish_committed_market_changes(session, redis) == 0
        with pytest.raises(RuntimeError):
            with session.sync_session.begin_nested():
                queue(session, oid=13)
                with session.sync_session.begin_nested():
                    queue(session, oid=14)
                raise RuntimeError("rollback this savepoint")
    assert await push.publish_committed_market_changes(session, redis) == 1
    assert json.loads(redis.commands[0][2])["outcome_ids"] == [11, 12]


async def test_outer_rollback_also_discards_released_savepoint(session):
    redis = FakeRedis()
    with pytest.raises(RuntimeError):
        with session.sync_session.begin():
            with session.sync_session.begin_nested():
                queue(session)
            raise RuntimeError("outer write failed")
    assert await push.publish_committed_market_changes(session, redis) == 0


async def test_zero_row_update_cannot_create_a_commit_signal(session):
    sync = session.sync_session
    sync.execute(text("CREATE TABLE outcomes (id INTEGER PRIMARY KEY, stamp TEXT)"))
    sync.commit()
    with sync.begin():
        row = sync.execute(
            text("UPDATE outcomes SET stamp=:at WHERE id=11 RETURNING id, stamp"),
            {"at": STAMP.isoformat()},
        ).first()
        if row is not None:
            queue(session, oid=row.id, stamp=row.stamp)
    redis = FakeRedis()
    assert await push.publish_committed_market_changes(session, redis) == 0
    redis.publish.assert_not_awaited()


async def test_assigned_market_only_terminal_keeps_stored_change_time(session):
    with session.sync_session.begin():
        push.queue_market_change(
            session,
            market_id=1,
            source="polymarket",
            outcome_observed_at={},
            terminal=True,
            updated_at=STAMP,
        )
    redis = FakeRedis()
    assert await push.publish_committed_market_changes(session, redis) == 1
    frame = json.loads(redis.commands[0][2])
    assert frame["terminal"] is True
    assert frame["outcome_ids"] == []
    assert frame["updated_at"] == STAMP.isoformat()
    assert push.parse_market_frame(json.dumps(frame)) == frame


async def test_publish_failure_does_not_undo_commit_or_suppress_healthy_sibling(
    session,
):
    with session.sync_session.begin():
        queue(session)
        queue(session, mid=2)
    redis = FakeRedis()
    redis.replies = iter([ResponseError("command denied"), 0])
    assert await push.publish_committed_market_changes(session, redis) == 1
    assert len(redis.commands) == 2
    assert not session.sync_session.in_transaction()
    assert await push.publish_committed_market_changes(session, redis) == 0


def test_queue_requires_a_writing_transaction(session):
    with pytest.raises(RuntimeError, match="writing transaction"):
        queue(session)


@pytest.mark.parametrize(
    "change",
    [
        {"market_id": True},
        {"source": "betting"},
        {"terminal": "yes"},
        {"outcome_ids": [True]},
        {"outcome_ids": [11, 11]},
        {"outcome_observed_at": {}},
        {"updated_at": None},
        {"published_at": "bad"},
        {"invalidation": False},
        {"source": []},
    ],
)
def test_malformed_frames_fail_closed(change):
    frame = push._change(
        market_id=1,
        source="kalshi",
        outcome_observed_at={11: STAMP},
        terminal=False,
        updated_at=None,
    )
    frame["published_at"] = STAMP.isoformat()
    frame.update(change)
    assert push.parse_market_frame(json.dumps(frame)) is None


@pytest.mark.parametrize("raw", [None, {}, "[]", "{}", "not json", b"\xff"])
def test_unparseable_messages_are_ignored(raw):
    assert push.parse_market_frame(raw) is None


async def test_65_notifications_are_sent_in_bounded_batches_before_replies(session):
    with session.sync_session.begin():
        for mid in range(1, 66):
            queue(session, mid=mid)
    redis = FakeRedis()
    assert await push.publish_committed_market_changes(session, redis) == 65
    assert [
        len(call.args[0])
        for call in redis.connection.send_packed_command.await_args_list
    ] == [32, 32, 1]
    assert redis.read_counts == [0, 32, 64]
    assert [args[1] for args in redis.commands] == [
        f"live:market:{n}" for n in range(1, 66)
    ]
    redis.publish.assert_not_awaited()
    redis.connection_pool.release.assert_awaited_once_with(redis.connection)
    redis.connection.disconnect.assert_not_awaited()


@pytest.mark.parametrize(
    "failure", [ConnectionError("reply lost"), asyncio.CancelledError()]
)
async def test_uncertain_batch_is_not_retried_or_reused(session, failure):
    with session.sync_session.begin():
        for mid in range(1, 66):
            queue(session, mid=mid)
    redis = FakeRedis([0, failure])
    if isinstance(failure, asyncio.CancelledError):
        with pytest.raises(asyncio.CancelledError):
            await push.publish_committed_market_changes(session, redis)
    else:
        assert await push.publish_committed_market_changes(session, redis) == 1
    assert len(redis.commands) == 32
    redis.connection.send_packed_command.assert_awaited_once()
    redis.connection.disconnect.assert_awaited_once()
    redis.connection_pool.release.assert_awaited_once_with(redis.connection)
    assert await push.publish_committed_market_changes(session, redis) == 0
    redis.connection_pool.get_connection.assert_awaited_once()


async def test_deadline_disconnects_unread_batch_and_preserves_acknowledged_count(
    session, monkeypatch
):
    with session.sync_session.begin():
        queue(session)
        queue(session, mid=2)
    redis = FakeRedis()
    timeout = asyncio.timeout
    monkeypatch.setattr(push.asyncio, "timeout", lambda seconds: timeout(0.01))

    async def slow_reply():
        await asyncio.sleep(10)

    redis.connection.read_response.side_effect = slow_reply
    assert await push.publish_committed_market_changes(session, redis) == 0
    redis.connection.disconnect.assert_awaited_once()
    redis.connection_pool.release.assert_awaited_once_with(redis.connection)
    assert len(redis.commands) == 2
