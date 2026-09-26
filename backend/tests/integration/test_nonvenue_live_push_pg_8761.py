"""#8761: real row writes reach SSE only once PostgreSQL keeps their snapshot."""

import asyncio
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
from sqlalchemy import update
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.models.models import Event
from app.tasks.live_blend_refresh import atomic_stamp_expression
from app.utils.aggregation import compute_aggregate_probability
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

pg_engine = _pg_engine
pytestmark = needs_postgres


@pytest.fixture
def sink(monkeypatch):
    class Redis:
        def __init__(self):
            self.frames = []

        async def publish(self, channel, data):
            import json

            self.frames.append((channel, json.loads(data)))

        async def aclose(self):
            pass

    redis = Redis()
    monkeypatch.setattr("app.tasks.redis_state.get_async_redis_client", lambda: redis)
    return redis.frames


@pytest.mark.parametrize("source", ["betting", "stat_model", "mlb", "espn"])
async def test_returned_snapshot_publishes_only_after_commit(pg_engine, sink, source):
    event_id = await _seed_event(
        pg_engine,
        {
            "kalshi": {
                "value": 0.7,
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }
        },
    )
    async with async_sessionmaker(pg_engine, expire_on_commit=False)() as session:
        event = await session.get(Event, event_id)
        sources = await write_nonvenue_probability(session, event, source, 0.6)
        await publish_committed_nonvenue_frames(session)
        assert sink == []
        assert source not in await _stored(pg_engine, event_id)
        expected = compute_aggregate_probability(event, "live")
        await session.commit()
        assert (await _stored(pg_engine, event_id))[source] == sources[source]
        await publish_committed_nonvenue_frames(session)
        assert len(sink) == 1
        channel, frame = sink[0]
        assert channel == f"live:event:{event_id}"
        assert frame["p"] == expected
        assert frame["source_value"] == 0.6
        assert frame["updated_at"] == sources[source]["updated_at"]
        await publish_committed_nonvenue_frames(session)
        assert len(sink) == 1


async def test_rollback_never_leaks_into_next_commit(pg_engine, sink):
    event_id = await _seed_event(pg_engine)
    async with async_sessionmaker(pg_engine, expire_on_commit=False)() as session:
        event = await session.get(Event, event_id)
        await write_nonvenue_probability(session, event, "stat_model", 0.1)
        await session.rollback()
        await session.commit()
        await publish_committed_nonvenue_frames(session)
    assert sink == []
    assert "stat_model" not in await _stored(pg_engine, event_id)


async def test_savepoint_rollback_preserves_outer_frame(pg_engine, sink):
    event_id = await _seed_event(pg_engine)
    async with async_sessionmaker(pg_engine, expire_on_commit=False)() as session:
        event = await session.get(Event, event_id)
        sources = await write_nonvenue_probability(session, event, "mlb", 0.6)
        async with session.begin_nested() as nested:
            await write_nonvenue_probability(session, event, "stat_model", 0.1)
            await nested.rollback()
        assert event.win_probability_sources == sources
        await session.commit()
        await publish_committed_nonvenue_frames(session)
    assert len(sink) == 1
    assert sink[0][1]["source"] == "mlb"
    assert sink[0][1]["updated_at"] == sources["mlb"]["updated_at"]
    assert "stat_model" not in await _stored(pg_engine, event_id)


async def test_savepoint_release_is_not_commit_and_last_snapshot_wins(pg_engine, sink):
    event_id = await _seed_event(pg_engine)
    async with async_sessionmaker(pg_engine, expire_on_commit=False)() as session:
        event = await session.get(Event, event_id)
        await write_nonvenue_probability(session, event, "espn", 0.7)
        async with session.begin_nested():
            sources = await write_nonvenue_probability(
                session, event, "stat_model", 0.6
            )
        await publish_committed_nonvenue_frames(session)
        assert not sink
        await session.commit()
        await publish_committed_nonvenue_frames(session)
    assert len(sink) == 1
    assert sink[0][1]["source"] == "stat_model"
    assert sink[0][1]["updated_at"] == sources["stat_model"]["updated_at"]


async def test_removal_streams_reweighted_blend_and_keeps_sibling(pg_engine, sink):
    event_id = await _seed_event(pg_engine, {"betting": 0.1, "kalshi": 0.8})
    async with async_sessionmaker(pg_engine, expire_on_commit=False)() as session:
        event = await session.get(Event, event_id)
        sources = await write_nonvenue_probability(
            session, event, "betting", None, metadata={"betting_book_count": 1}
        )
        await session.commit()
        await publish_committed_nonvenue_frames(session)
    assert sources == {"kalshi": 0.8, "betting_book_count": 1}
    assert sink[0][1]["p"] == 0.8
    assert sink[0][1]["source_value"] is None


@pytest.mark.parametrize("status", ["scheduled", "completed", "closed"])
async def test_nonlive_writes_do_not_emit_live_frames(pg_engine, sink, status):
    event_id = await _seed_event(pg_engine)
    async with async_sessionmaker(pg_engine, expire_on_commit=False)() as session:
        event = await session.get(Event, event_id)
        event.status = status
        await write_nonvenue_probability(session, event, "mlb", 0.9)
        await session.commit()
        await publish_committed_nonvenue_frames(session)
    assert not sink


async def test_nonvenue_waits_for_venue_and_keeps_its_reading(pg_engine, sink):
    event_id = await _seed_event(pg_engine)
    sessions = async_sessionmaker(pg_engine, expire_on_commit=False)
    async with sessions() as venue, sessions() as nonvenue:
        event = await nonvenue.get(Event, event_id)
        earlier = (
            await venue.execute(
                update(Event)
                .where(Event.id == event_id)
                .values(win_probability_sources=atomic_stamp_expression("kalshi", 0.8))
                .returning(Event.win_probability_sources)
            )
        ).scalar_one()
        pending = asyncio.create_task(
            write_nonvenue_probability(nonvenue, event, "stat_model", 0.65)
        )
        await asyncio.sleep(0.05)
        assert not pending.done(), "must actually block on row lock"
        await venue.commit()
        later = await pending
        await nonvenue.commit()
        await publish_committed_nonvenue_frames(nonvenue)
    assert later["kalshi"] == earlier["kalshi"]
    assert datetime.fromisoformat(
        later["stat_model"]["updated_at"]
    ) > datetime.fromisoformat(earlier["kalshi"]["updated_at"])
    assert sink[0][1]["updated_at"] == later["stat_model"]["updated_at"]
    assert sink[0][1]["p"] == compute_aggregate_probability(
        SimpleNamespace(win_probability_sources=later, status="live"), "live"
    )


async def test_fanout_failure_keeps_committed_source(pg_engine, sink, monkeypatch):
    def broken():
        raise RuntimeError("Redis unavailable")

    monkeypatch.setattr("app.tasks.redis_state.get_async_redis_client", broken)
    event_id = await _seed_event(pg_engine)
    async with async_sessionmaker(pg_engine, expire_on_commit=False)() as session:
        event = await session.get(Event, event_id)
        await write_nonvenue_probability(session, event, "mlb", 0.6)
        await session.commit()
        await publish_committed_nonvenue_frames(session)
    assert (await _stored(pg_engine, event_id))["mlb"]["value"] == 0.6
    assert not sink


async def test_failed_commit_does_not_publish(pg_engine, sink):
    from sqlalchemy import event as sa_event

    event_id = await _seed_event(pg_engine)
    async with async_sessionmaker(pg_engine, expire_on_commit=False)() as session:
        event = await session.get(Event, event_id)
        await write_nonvenue_probability(session, event, "mlb", 0.6)

        def fail(_):
            raise RuntimeError("commit failed")

        sa_event.listen(session.sync_session, "before_commit", fail, once=True)
        with pytest.raises(RuntimeError, match="commit failed"):
            await session.commit()
        await publish_committed_nonvenue_frames(session)
        assert not sink
        await session.rollback()
        await session.commit()
        await publish_committed_nonvenue_frames(session)
    assert not sink
    assert "mlb" not in await _stored(pg_engine, event_id)


async def test_actual_betting_ingest_publishes_its_committed_consensus(
    pg_engine, sink, monkeypatch
):
    from app.tasks.odds_polling import _ingest_event_odds
    from tests.test_discovery_advances_betting_consensus_5426 import _FakeSnapshot

    async def snapshot(*args, **kwargs):
        return _FakeSnapshot(0.6, None, None), False

    monkeypatch.setattr("app.tasks.odds_polling._create_or_update_snapshot", snapshot)
    event_id = await _seed_event(pg_engine)
    async with async_sessionmaker(pg_engine, expire_on_commit=False)() as session:
        event = await session.get(Event, event_id)
        await _ingest_event_odds(
            session,
            event,
            {"bookmakers": [{"key": str(i)} for i in range(3)]},
            datetime.now(timezone.utc),
            {},
            update_opening=False,
        )
        assert not sink
        await session.commit()
        await publish_committed_nonvenue_frames(session)
    assert len(sink) == 1
    assert sink[0][1]["source"] == "betting"
    assert sink[0][1]["p"] == 0.6
    stored = await _stored(pg_engine, event_id)
    assert stored["betting_book_count"] == 3
    assert sink[0][1]["updated_at"] == stored["betting"]["updated_at"]


async def test_actual_espn_stat_model_publishes_after_commit(
    pg_engine, sink, monkeypatch
):
    from app.utils.espn_helpers import compute_and_write_stat_model
    from tests.test_priorless_stat_model_defers_to_market_8522 import (
        _puck_drop_board_row,
    )

    async def snapshot(*args, **kwargs):
        return None, False

    monkeypatch.setattr(
        "app.tasks.snapshots._create_or_update_win_prob_snapshot", snapshot
    )
    monkeypatch.setattr(
        "app.utils.espn_helpers.orient_espn_event_to_row", lambda event, ee: ee
    )
    event_id = await _seed_event(pg_engine, {})
    async with async_sessionmaker(pg_engine, expire_on_commit=False)() as session:
        event = await session.get(Event, event_id)
        assert await compute_and_write_stat_model(
            session, event, _puck_drop_board_row(), "icehockey_nhl", {}
        )
        assert not sink
        await session.commit()
        await publish_committed_nonvenue_frames(session)
    assert len(sink) == 1
    assert sink[0][1]["source"] == "stat_model"
    stored = await _stored(pg_engine, event_id)
    assert sink[0][1]["p"] == stored["stat_model"]["value"]
    assert sink[0][1]["updated_at"] == stored["stat_model"]["updated_at"]


@pytest.mark.parametrize("fail", [False, True])
async def test_task_session_exit_publishes_only_successful_commit(
    pg_engine, sink, monkeypatch, fail
):
    from app.tasks.base import get_task_session

    monkeypatch.setattr("app.tasks.base._get_task_engine", lambda **kwargs: pg_engine)
    event_id = await _seed_event(pg_engine)
    try:
        async with get_task_session() as session:
            event = await session.get(Event, event_id)
            await write_nonvenue_probability(session, event, "mlb", 0.6)
            assert not sink
            if fail:
                raise ValueError("abort task")
    except ValueError:
        assert fail
    assert len(sink) == (0 if fail else 1)


async def test_actual_mlb_task_commits_before_publishing(pg_engine, sink, monkeypatch):
    from contextlib import asynccontextmanager
    from sqlalchemy import select
    from app.tasks.mlb_sync import _sync_mlb_win_probability

    event_id = await _seed_event(pg_engine, {})
    game = SimpleNamespace(
        game_pk=8761,
        home_team="Twins",
        away_team="Yankees",
        game_datetime=None,
        home_win_probability=0.65,
        away_win_probability=0.35,
        home_score=2,
        away_score=1,
        inning=None,
        inning_half=None,
    )

    class Provider:
        async def get_live_games(self):
            return [game]

        async def close(self):
            pass

    async def snapshot(*args, **kwargs):
        return None, False

    @asynccontextmanager
    async def scope():
        async with async_sessionmaker(pg_engine, expire_on_commit=False)() as session:

            class SelectedFixture:
                # The shared fixture uses unique sport keys for safe CI cleanup.
                # Narrow only the task's selection to its one seeded live event;
                # all probability SQL and commits run against PostgreSQL.
                async def execute(self, statement):
                    if statement.is_select:
                        statement = select(Event).where(Event.id == event_id)
                    return await session.execute(statement)

                def __getattr__(self, name):
                    return getattr(session, name)

            yield SelectedFixture()

    monkeypatch.setattr("app.services.mlb_api.MLBAPIService", Provider)
    monkeypatch.setattr("app.tasks.mlb_sync.get_task_session", scope)
    monkeypatch.setattr(
        "app.tasks.mlb_sync._create_or_update_win_prob_snapshot", snapshot
    )
    stats = await _sync_mlb_win_probability()
    assert stats["events_matched"] == 1
    assert stats["errors"] == []
    assert len(sink) == 1
    assert sink[0][1]["source"] == "mlb"
    stored = await _stored(pg_engine, event_id)
    assert sink[0][1]["p"] == stored["mlb"]["value"] == 0.65
    assert sink[0][1]["updated_at"] == stored["mlb"]["updated_at"]


async def test_rolled_back_descendant_savepoint_is_not_published(pg_engine, sink):
    event_id = await _seed_event(pg_engine)
    async with async_sessionmaker(pg_engine, expire_on_commit=False)() as session:
        event = await session.get(Event, event_id)
        async with session.begin_nested() as outer:
            async with session.begin_nested():
                await write_nonvenue_probability(session, event, "mlb", 0.65)
            await outer.rollback()
        await session.commit()
        await publish_committed_nonvenue_frames(session)
    assert not sink
    assert "mlb" not in await _stored(pg_engine, event_id)


@pytest.mark.parametrize("source", ["kalshi", "polymarket", "made_up"])
async def test_nonvenue_writer_refuses_other_source_classes(pg_engine, source):
    event_id = await _seed_event(pg_engine)
    async with async_sessionmaker(pg_engine, expire_on_commit=False)() as session:
        event = await session.get(Event, event_id)
        with pytest.raises(ValueError, match="not a nonvenue probability source"):
            await write_nonvenue_probability(session, event, source, 0.7)
