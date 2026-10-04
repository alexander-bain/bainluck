"""#4971: the recorded publication is the bag PostgreSQL committed, or nothing.

Every property here belongs to the server: the per-row revision trigger, the
row lock that orders two writers, the savepoint that discards a contribution,
and the rollback that takes the publication row down with the price. A session
double has none of them, so this file runs only against a real PostgreSQL.
"""

import asyncio
import logging
from datetime import datetime, timezone

import pytest
from sqlalchemy import event as sa_event, select, text, update
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.models.models import Event, ProbabilityPublication
from app.services.database import Base
from app.tasks.live_blend_refresh import atomic_stamp_expression
from app.utils.aggregation import compute_aggregate_probability_tiered
from app.utils.nonvenue_live_push import (
    publish_committed_nonvenue_frames,
    write_nonvenue_probability,
)
from app.utils.probability_publication import (
    BLEND_METHOD,
    COVERAGE_COMPLETE,
    COVERAGE_PRIOR_UNESTABLISHED,
    COVERAGE_UNCOVERED,
    RECORDING_FLAG,
)
from tests.integration.test_live_blend_concurrent_stamp_pg import (
    MARKER,
    SEEDED,
    _seed_event,
    _stored,
    needs_postgres,
    pg_engine as _pg_engine,
)

pg_engine = _pg_engine
pytestmark = needs_postgres


@pytest.fixture
async def engine(pg_engine, monkeypatch):
    monkeypatch.setenv(RECORDING_FLAG, "true")
    async with pg_engine.begin() as conn:
        await conn.run_sync(
            Base.metadata.create_all, tables=[ProbabilityPublication.__table__]
        )
    yield pg_engine
    # No foreign key: delete this gate's rows before pg_engine drops its events.
    async with pg_engine.begin() as conn:
        await conn.execute(
            text(
                "DELETE FROM probability_publications WHERE event_id IN"
                " (SELECT e.id FROM events e JOIN sports s ON s.id = e.sport_id"
                " WHERE s.key LIKE :k)"
            ),
            {"k": f"{MARKER}%"},
        )


@pytest.fixture
def sink(monkeypatch):
    class Redis:
        def __init__(self):
            self.frames = []

        async def publish(self, channel, data):
            import json

            self.frames.append(json.loads(data))

        async def aclose(self):
            pass

    redis = Redis()
    monkeypatch.setattr("app.tasks.redis_state.get_async_redis_client", lambda: redis)
    return redis.frames


def _sessions(engine):
    return async_sessionmaker(engine, expire_on_commit=False)


async def _publications(engine, event_id):
    from types import SimpleNamespace

    table = ProbabilityPublication.__table__
    async with engine.connect() as conn:
        rows = (
            await conn.execute(
                select(table).where(table.c.event_id == event_id).order_by(table.c.rev)
            )
        ).mappings()
        return [SimpleNamespace(**row) for row in rows]


async def _row(engine, event_id):
    async with engine.connect() as conn:
        return (
            await conn.execute(
                select(
                    Event.win_probability_sources,
                    Event.win_probability_sources_rev,
                    Event.status,
                ).where(Event.id == event_id)
            )
        ).one()


def _blend(sources, status="live"):
    from types import SimpleNamespace

    return compute_aggregate_probability_tiered(
        SimpleNamespace(
            win_probability_sources=sources,
            espn_win_prob_home=None,
            opening_home_probability=None,
        ),
        status,
    )


def _pub(rows):
    assert len(rows) == 1, rows
    return rows[0]


async def test_flag_off_records_nothing(engine, monkeypatch):
    monkeypatch.setenv(RECORDING_FLAG, "false")
    event_id = await _seed_event(engine)
    async with _sessions(engine)() as session:
        event = await session.get(Event, event_id)
        await write_nonvenue_probability(session, event, "mlb", 0.6)
        await session.commit()
    assert (await _stored(engine, event_id))["mlb"]["value"] == 0.6
    assert await _publications(engine, event_id) == []


async def test_one_write_records_the_committed_bag_rev_and_blend(engine, sink):
    event_id = await _seed_event(engine)
    async with _sessions(engine)() as session:
        event = await session.get(Event, event_id)
        await write_nonvenue_probability(session, event, "mlb", 0.6)
        assert await _publications(engine, event_id) == []
        await session.commit()
        await publish_committed_nonvenue_frames(session)
    bag, rev, _ = await _row(engine, event_id)
    pub = _pub(await _publications(engine, event_id))
    assert pub.sources == bag
    assert pub.rev == rev == 1
    assert (pub.blend_probability, pub.blend_tier) == _blend(bag)
    assert pub.blend_method == BLEND_METHOD
    assert pub.coverage == COVERAGE_COMPLETE and pub.uncovered_keys == []
    assert pub.prior_txn_row_write is False and pub.unobserved_bumps == 0
    assert pub.removed_sources == []
    assert pub.source_clocks == {
        "betting": bag["betting"]["updated_at"],
        "mlb": bag["mlb"]["updated_at"],
    }
    assert [o["source"] for o in pub.observations] == ["mlb"]
    assert pub.observations[0]["rev"] == rev
    assert pub.recorded_at >= pub.txn_started_at
    # The frame recorded is the frame fanout sent, and it carries this state.
    assert len(sink) == 1
    assert pub.queued_frame == sink[0]
    assert pub.queued_frame_matches is True
    assert sink[0]["p"] == pub.blend_probability
    assert sink[0]["rev"] == {str(event_id): pub.rev}


async def test_two_writes_one_commit_record_only_the_final_bag(engine, sink):
    event_id = await _seed_event(engine)
    async with _sessions(engine)() as session:
        event = await session.get(Event, event_id)
        first = await write_nonvenue_probability(session, event, "espn", 0.7)
        await write_nonvenue_probability(session, event, "stat_model", 0.6)
        await session.commit()
        await publish_committed_nonvenue_frames(session)
    bag, rev, _ = await _row(engine, event_id)
    pub = _pub(await _publications(engine, event_id))
    assert pub.rev == rev == 2
    assert pub.sources == bag and pub.sources != first
    assert (pub.blend_probability, pub.blend_tier) == _blend(bag)
    # The intermediate ESPN state is an OBSERVATION, never a published vertex.
    assert [(o["source"], o["rev"]) for o in pub.observations] == [
        ("espn", 1),
        ("stat_model", 2),
    ]
    assert pub.coverage == COVERAGE_COMPLETE
    assert len(sink) == 1 and sink[0]["rev"] == {str(event_id): 2}
    assert pub.queued_frame == sink[0] and pub.queued_frame_matches is True


async def _raw_kalshi(session, event_id, value=0.8):
    await session.execute(
        update(Event)
        .where(Event.id == event_id)
        .values(win_probability_sources=atomic_stamp_expression("kalshi", value))
    )


async def test_unqueued_writer_later_in_the_transaction_is_in_the_bag_and_flagged(
    engine, sink
):
    event_id = await _seed_event(engine)
    async with _sessions(engine)() as session:
        event = await session.get(Event, event_id)
        await write_nonvenue_probability(session, event, "mlb", 0.6)
        await _raw_kalshi(session, event_id)
        await session.commit()
        await publish_committed_nonvenue_frames(session)
    bag, rev, _ = await _row(engine, event_id)
    pub = _pub(await _publications(engine, event_id))
    assert pub.rev == rev == 2
    assert pub.sources == bag and "kalshi" in pub.sources
    assert (pub.blend_probability, pub.blend_tier) == _blend(bag)
    assert pub.coverage == COVERAGE_UNCOVERED
    assert pub.uncovered_keys == ["kalshi"] and pub.unobserved_bumps == 1
    # The QUEUED frame describes the mlb write's state, not the committed one.
    assert pub.queued_frame == sink[0]
    assert sink[0]["rev"] == {str(event_id): 1}
    assert pub.queued_frame_matches is False


async def test_unqueued_writer_before_the_first_tracked_write_is_not_complete(engine):
    """Root's discriminator: untracked Kalshi first, then the tracked write."""
    event_id = await _seed_event(engine)
    async with _sessions(engine)() as session:
        event = await session.get(Event, event_id)
        await _raw_kalshi(session, event_id)
        await write_nonvenue_probability(session, event, "espn", 0.6)
        await session.commit()
    bag, rev, _ = await _row(engine, event_id)
    pub = _pub(await _publications(engine, event_id))
    assert pub.sources == bag and "kalshi" in bag and pub.rev == rev == 2
    assert [o["source"] for o in pub.observations] == ["espn"]
    assert pub.prior_txn_row_write is True
    assert pub.coverage == COVERAGE_PRIOR_UNESTABLISHED
    assert pub.uncovered_keys == [] and pub.unobserved_bumps == 0


async def test_prior_write_inside_a_released_savepoint_is_still_seen(engine):
    event_id = await _seed_event(engine)
    async with _sessions(engine)() as session:
        event = await session.get(Event, event_id)
        async with session.begin_nested():
            await _raw_kalshi(session, event_id)
        await write_nonvenue_probability(session, event, "espn", 0.6)
        await session.commit()
    pub = _pub(await _publications(engine, event_id))
    assert pub.prior_txn_row_write is True
    assert pub.coverage == COVERAGE_PRIOR_UNESTABLISHED


async def test_prior_write_rolled_back_in_a_savepoint_leaves_the_baseline_clean(engine):
    event_id = await _seed_event(engine)
    async with _sessions(engine)() as session:
        event = await session.get(Event, event_id)
        async with session.begin_nested() as nested:
            await _raw_kalshi(session, event_id)
            await nested.rollback()
        await session.refresh(event)  # gotcha #6: the rollback expired it
        await write_nonvenue_probability(session, event, "espn", 0.6)
        await session.commit()
    pub = _pub(await _publications(engine, event_id))
    assert "kalshi" not in pub.sources
    assert pub.prior_txn_row_write is False and pub.coverage == COVERAGE_COMPLETE


async def test_a_prior_non_bag_row_write_is_conservatively_unestablished(engine):
    # The probe sees the row, not the column: an earlier score write in this
    # transaction cannot be told from a bag write, so completeness is withheld.
    event_id = await _seed_event(engine)
    async with _sessions(engine)() as session:
        event = await session.get(Event, event_id)
        await session.execute(
            update(Event).where(Event.id == event_id).values(home_score=1)
        )
        await write_nonvenue_probability(session, event, "espn", 0.6)
        await session.commit()
    pub = _pub(await _publications(engine, event_id))
    assert pub.prior_txn_row_write is True
    assert pub.coverage == COVERAGE_PRIOR_UNESTABLISHED
    assert pub.unobserved_bumps == 0


async def test_a_failing_probe_is_contained_and_never_claims_completeness(
    engine, monkeypatch
):
    # Stands in for the post-wraparound future-xid error: a REAL server error.
    monkeypatch.setattr(
        "app.utils.nonvenue_live_push._PRIOR_WRITE_PROBE_SQL",
        "SELECT 1 / (id - id) = 1 FROM events WHERE id = :id",
    )
    event_id = await _seed_event(engine)
    async with _sessions(engine)() as session:
        event = await session.get(Event, event_id)
        await write_nonvenue_probability(session, event, "mlb", 0.6)
        await session.commit()
    assert (await _stored(engine, event_id))["mlb"]["value"] == 0.6
    pub = _pub(await _publications(engine, event_id))
    assert pub.prior_txn_row_write is None
    assert pub.coverage == COVERAGE_PRIOR_UNESTABLISHED


async def test_unqueued_writer_between_two_tracked_writes_is_flagged(engine):
    event_id = await _seed_event(engine)
    async with _sessions(engine)() as session:
        event = await session.get(Event, event_id)
        await write_nonvenue_probability(session, event, "mlb", 0.6)
        await _raw_kalshi(session, event_id)
        await write_nonvenue_probability(session, event, "stat_model", 0.5)
        await session.commit()
    bag, rev, _ = await _row(engine, event_id)
    pub = _pub(await _publications(engine, event_id))
    assert pub.sources == bag and pub.rev == rev == 3
    assert pub.coverage == COVERAGE_UNCOVERED
    assert pub.uncovered_keys == ["kalshi"] and pub.unobserved_bumps == 1


async def test_an_unqueued_change_undone_before_commit_is_still_flagged(engine):
    event_id = await _seed_event(engine)
    async with _sessions(engine)() as session:
        event = await session.get(Event, event_id)
        await write_nonvenue_probability(session, event, "mlb", 0.6)
        await _raw_kalshi(session, event_id)
        await session.execute(
            update(Event)
            .where(Event.id == event_id)
            .values(win_probability_sources=Event.win_probability_sources.op("-")("kalshi"))
        )
        await session.commit()
    pub = _pub(await _publications(engine, event_id))
    assert pub.uncovered_keys == [] and pub.unobserved_bumps == 2
    assert pub.coverage == COVERAGE_UNCOVERED


async def test_unflushed_orm_change_is_flushed_before_the_bag_is_read(engine):
    event_id = await _seed_event(engine)
    async with _sessions(engine)() as session:
        event = await session.get(Event, event_id)
        sources = await write_nonvenue_probability(session, event, "mlb", 0.6)
        event.win_probability_sources = {**sources, "kalshi": 0.8}
        await session.commit()
    bag, rev, _ = await _row(engine, event_id)
    assert bag["kalshi"] == 0.8
    pub = _pub(await _publications(engine, event_id))
    assert pub.sources == bag and pub.rev == rev
    assert pub.uncovered_keys == ["kalshi"] and pub.unobserved_bumps == 1


async def test_outer_rollback_records_nothing(engine):
    event_id = await _seed_event(engine)
    async with _sessions(engine)() as session:
        event = await session.get(Event, event_id)
        await write_nonvenue_probability(session, event, "mlb", 0.6)
        await session.rollback()
        await session.commit()
    assert "mlb" not in await _stored(engine, event_id)
    assert await _publications(engine, event_id) == []


async def test_savepoint_rollback_discards_its_write_and_its_observation(engine):
    event_id = await _seed_event(engine)
    async with _sessions(engine)() as session:
        event = await session.get(Event, event_id)
        await write_nonvenue_probability(session, event, "mlb", 0.6)
        async with session.begin_nested() as nested:
            await write_nonvenue_probability(session, event, "stat_model", 0.1)
            await nested.rollback()
        await session.commit()
    bag, rev, _ = await _row(engine, event_id)
    pub = _pub(await _publications(engine, event_id))
    assert "stat_model" not in bag and "stat_model" not in pub.sources
    assert pub.sources == bag and pub.rev == rev
    assert [o["source"] for o in pub.observations] == ["mlb"]


async def test_savepoint_holding_the_only_write_rolls_back_to_no_row(engine):
    event_id = await _seed_event(engine)
    async with _sessions(engine)() as session:
        event = await session.get(Event, event_id)
        async with session.begin_nested() as nested:
            await write_nonvenue_probability(session, event, "mlb", 0.6)
            await nested.rollback()
        await session.commit()
    assert await _publications(engine, event_id) == []


async def test_savepoint_release_is_not_a_publication(engine):
    event_id = await _seed_event(engine)
    async with _sessions(engine)() as session:
        event = await session.get(Event, event_id)
        async with session.begin_nested():
            await write_nonvenue_probability(session, event, "mlb", 0.6)
        assert await _publications(engine, event_id) == []
        await write_nonvenue_probability(session, event, "stat_model", 0.5)
        await session.commit()
    pub = _pub(await _publications(engine, event_id))
    assert [o["source"] for o in pub.observations] == ["mlb", "stat_model"]


async def test_failed_commit_after_recording_leaves_no_row(engine):
    event_id = await _seed_event(engine)
    async with _sessions(engine)() as session:
        event = await session.get(Event, event_id)
        await write_nonvenue_probability(session, event, "mlb", 0.6)

        def fail(_):
            raise RuntimeError("commit failed")

        # Registered after the recorder's hook, so the row IS inserted first.
        sa_event.listen(session.sync_session, "before_commit", fail, once=True)
        with pytest.raises(RuntimeError, match="commit failed"):
            await session.commit()
        await session.rollback()
    assert "mlb" not in await _stored(engine, event_id)
    assert await _publications(engine, event_id) == []


async def test_removal_keeps_the_surviving_blend_and_names_the_gap(engine, sink):
    event_id = await _seed_event(engine, {"betting": 0.1, "kalshi": 0.8})
    async with _sessions(engine)() as session:
        event = await session.get(Event, event_id)
        await write_nonvenue_probability(
            session, event, "betting", None, metadata={"betting_book_count": 1}
        )
        await session.commit()
        await publish_committed_nonvenue_frames(session)
    pub = _pub(await _publications(engine, event_id))
    assert pub.sources == {"kalshi": 0.8, "betting_book_count": 1}
    assert pub.removed_sources == ["betting"]
    assert (pub.blend_probability, pub.blend_tier) == (0.8, "sources")
    # A removal is not a frame: none was queued, and the row does not claim one.
    assert pub.queued_frame is None and pub.queued_frame_matches is None
    assert not sink
    assert pub.observations[0]["removed"] is True
    assert pub.observations[0]["value"] is None


async def test_removing_the_last_source_records_no_overall_probability(engine):
    event_id = await _seed_event(engine, {"betting": 0.1})
    async with _sessions(engine)() as session:
        event = await session.get(Event, event_id)
        await write_nonvenue_probability(session, event, "betting", None)
        await session.commit()
    pub = _pub(await _publications(engine, event_id))
    assert pub.sources == {}
    assert (pub.blend_probability, pub.blend_tier) == (None, None)
    assert pub.removed_sources == ["betting"]


async def test_same_identity_same_payload_is_idempotent(engine, caplog):
    event_id = await _seed_event(engine, {"kalshi": 0.8})
    for _ in range(2):
        async with _sessions(engine)() as session:
            event = await session.get(Event, event_id)
            # Removing an absent source moves no revision (the real trigger).
            await write_nonvenue_probability(session, event, "betting", None)
            await session.commit()
    _, rev, _ = await _row(engine, event_id)
    assert rev == 0
    pub = _pub(await _publications(engine, event_id))
    assert pub.rev == 0
    assert "DIVERGENT" not in caplog.text


async def test_same_identity_different_payload_is_loud_and_keeps_the_first(
    engine, caplog
):
    event_id = await _seed_event(engine, {"kalshi": 0.8, "betting": 0.4})
    async with _sessions(engine)() as session:
        event = await session.get(Event, event_id)
        await write_nonvenue_probability(session, event, "stat_model", None)
        await session.commit()
    first = _pub(await _publications(engine, event_id))
    # Status moves without the bag, so the revision does not move either.
    async with engine.begin() as conn:
        await conn.execute(
            update(Event).where(Event.id == event_id).values(status="completed")
        )
    caplog.set_level(logging.ERROR, logger="app.utils.probability_publication")
    async with _sessions(engine)() as session:
        event = await session.get(Event, event_id)
        await write_nonvenue_probability(session, event, "stat_model", None)
        await session.commit()
    kept = _pub(await _publications(engine, event_id))
    assert kept.rev == first.rev == 0
    assert kept.payload_sha256 == first.payload_sha256
    assert kept.event_status == "live"
    assert "DIVERGENT" in caplog.text
    assert first.payload_sha256 in caplog.text


async def test_concurrent_writers_record_consecutive_committed_revisions(engine):
    event_id = await _seed_event(engine)
    sessions = _sessions(engine)
    async with sessions() as one, sessions() as two:
        e1 = await one.get(Event, event_id)
        e2 = await two.get(Event, event_id)
        first = await write_nonvenue_probability(one, e1, "mlb", 0.6)
        blocked = asyncio.create_task(
            write_nonvenue_probability(two, e2, "stat_model", 0.4)
        )
        await asyncio.sleep(0.05)
        assert not blocked.done(), "the second writer must wait on the row lock"
        await one.commit()
        second = await blocked
        await two.commit()
    rows = await _publications(engine, event_id)
    assert [r.rev for r in rows] == [1, 2]
    assert rows[0].sources == first
    assert rows[1].sources == second == (await _row(engine, event_id))[0]
    assert "mlb" in rows[1].sources
    # The waiting writer's probe read the committed row, not its own write.
    assert [r.coverage for r in rows] == [COVERAGE_COMPLETE, COVERAGE_COMPLETE]


async def test_recording_failure_rolls_back_only_its_savepoint(
    engine, monkeypatch, caplog
):
    import app.utils.probability_publication as pp

    real = pp.build_publication

    def too_long(**kwargs):
        row = real(**kwargs)
        row["blend_method"] = "x" * 200  # varchar(80): a REAL server error
        return row

    monkeypatch.setattr(pp, "build_publication", too_long)
    caplog.set_level(logging.ERROR, logger="app.utils.probability_publication")
    event_id = await _seed_event(engine)
    async with _sessions(engine)() as session:
        event = await session.get(Event, event_id)
        await write_nonvenue_probability(session, event, "mlb", 0.6)
        await session.commit()
    assert (await _stored(engine, event_id))["mlb"]["value"] == 0.6
    assert await _publications(engine, event_id) == []
    assert "NOT recorded" in caplog.text


async def test_actual_betting_ingest_records_its_book_population(
    engine, sink, monkeypatch
):
    from app.tasks.odds_polling import BETTING_BOOK_FLOOR, _ingest_event_odds
    from tests.test_discovery_advances_betting_consensus_5426 import _FakeSnapshot

    prices = iter([0.58, 0.6, 0.63])

    async def snapshot(*args, **kwargs):
        return _FakeSnapshot(next(prices), None, None), False

    monkeypatch.setattr("app.tasks.odds_polling._create_or_update_snapshot", snapshot)
    event_id = await _seed_event(engine)
    async with _sessions(engine)() as session:
        event = await session.get(Event, event_id)
        await _ingest_event_odds(
            session,
            event,
            {"bookmakers": [{"key": f"book{i}"} for i in range(3)]},
            datetime.now(timezone.utc),
            {},
            update_opening=False,
        )
        await session.commit()
    bag, rev, _ = await _row(engine, event_id)
    pub = _pub(await _publications(engine, event_id))
    assert pub.sources == bag and pub.rev == rev
    assert bag["betting"]["value"] == 0.6 and bag["betting_book_count"] == 3
    assert pub.observations[0]["evidence"] == {
        "rule": "median",
        "floor": BETTING_BOOK_FLOOR,
        "decision": "admitted",
        "median": 0.6,
        "split_pair": None,
        "population": [
            {"book": "book0", "home_probability": 0.58},
            {"book": "book1", "home_probability": 0.6},
            {"book": "book2", "home_probability": 0.63},
        ],
    }


async def _ingest(engine, monkeypatch, prices, **kwargs):
    from app.tasks.odds_polling import _ingest_event_odds
    from tests.test_discovery_advances_betting_consensus_5426 import _FakeSnapshot

    quotes = iter(prices)

    async def snapshot(*args, **_):
        return _FakeSnapshot(next(quotes), None, None), False

    monkeypatch.setattr("app.tasks.odds_polling._create_or_update_snapshot", snapshot)
    event_id = await _seed_event(engine)
    async with _sessions(engine)() as session:
        event = await session.get(Event, event_id)
        await _ingest_event_odds(
            session,
            event,
            {"bookmakers": [{"key": f"book{i}"} for i in range(len(prices))]},
            datetime.now(timezone.utc),
            {},
            update_opening=False,
            **kwargs,
        )
        await session.commit()
    return event_id


@pytest.mark.parametrize(
    "prices, decision, split_pair, median",
    [
        # Ruling 051: two books are below the floor, so betting is removed.
        ([0.5, 0.6], "below_floor", None, 0.55),
        # #7523: the middle pair 0.21/0.8 is a split, so it is removed too.
        ([0.2, 0.21, 0.8, 0.81], "split", [0.21, 0.8], 0.505),
    ],
)
async def test_actual_betting_ingest_tombstone_keeps_its_refusal_evidence(
    engine, monkeypatch, prices, decision, split_pair, median
):
    from app.tasks.odds_polling import BETTING_BOOK_FLOOR

    event_id = await _ingest(engine, monkeypatch, prices)
    bag, rev, _ = await _row(engine, event_id)
    assert "betting" not in bag and bag["betting_book_count"] == len(prices)
    pub = _pub(await _publications(engine, event_id))
    assert pub.sources == bag and pub.rev == rev
    assert pub.removed_sources == ["betting"]
    assert pub.queued_frame is None
    evidence = pub.observations[0]["evidence"]
    assert evidence == {
        "rule": "median",
        "floor": BETTING_BOOK_FLOOR,
        "decision": decision,
        "median": pytest.approx(median),
        "split_pair": split_pair,
        "population": [
            {"book": f"book{i}", "home_probability": p} for i, p in enumerate(prices)
        ],
    }
    assert pub.observations[0]["value"] is None


async def test_a_zero_quote_stays_out_of_the_recorded_population(engine, monkeypatch):
    # The truthiness predicate never admitted a 0.0 home price; the evidence
    # must show the population that was actually used, not the books polled.
    event_id = await _ingest(engine, monkeypatch, [0.0, 0.58, 0.6, 0.63])
    bag, _, _ = await _row(engine, event_id)
    assert bag["betting"]["value"] == 0.6 and bag["betting_book_count"] == 3
    evidence = _pub(await _publications(engine, event_id)).observations[0]["evidence"]
    assert evidence["decision"] == "admitted" and evidence["median"] == 0.6
    assert [b["book"] for b in evidence["population"]] == ["book1", "book2", "book3"]


@pytest.mark.parametrize(
    "prices, kwargs",
    [
        # #5426: a partial caller under the floor leaves betting alone.
        ([0.5, 0.6], {"drop_below_floor": False}),
        # No book quotes a moneyline: no write, so nothing is published.
        ([None, None, None], {}),
    ],
)
async def test_an_ingest_that_writes_nothing_publishes_nothing(
    engine, monkeypatch, prices, kwargs
):
    event_id = await _ingest(engine, monkeypatch, prices, **kwargs)
    bag, rev, _ = await _row(engine, event_id)
    assert bag == SEEDED and rev == 0
    assert await _publications(engine, event_id) == []
