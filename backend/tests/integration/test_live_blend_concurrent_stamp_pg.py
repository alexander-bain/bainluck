"""live/305's blend race, against a REAL PostgreSQL. #836/#837/#5661.

## the defect this gate exists for

`worker-ws` runs the Kalshi and Polymarket consumers under one `asyncio.gather`
(`run_kalshi_ws.py`), and each owns its own `LiveBlendRefresher`. Both stamp the
SAME column on the SAME row — `events.win_probability_sources` — and both used to
do it by SELECTing the column, merging in Python, and writing the whole dict
back. Reproduced here on 2026-09-16, two arms reading one snapshot and writing
250 ms apart::

    kalshi arm's private view : {'betting': 0.5, 'kalshi': 0.53}
    pm arm's private view     : {'betting': 0.5, 'polymarket': 0.52}
    WHAT THE DATABASE KEPT    : {'betting': 0.5, 'polymarket': 0.52}

The later writer does not overwrite a stale sibling VALUE. It drops the sibling
KEY, because the dict it merged into never contained one.

That is the reported hero flicker. live/305 captured the same live event
publishing two hero numbers 89 ms apart — `polymarket p=0.51` then
`kalshi p=0.475` — with nothing underneath able to move in 89 ms, and the page
rendering whichever landed last. It also explains the direction, which a plain
staleness story cannot: the Kalshi arm held the HIGHER own price (0.53 vs 0.52)
and published the LOWER aggregate, because its private copy had no Polymarket
reading in it at all.

WHAT THIS IS NOT, because live/305's receipt said otherwise and the claim should
not be inherited: this is not the chart's zigzag. The fast-lane chart point is
written on the same path, but `_maybe_snapshot` writes
`win_prob_snapshots.home_win_probability` from THIS ARM'S OWN oriented reading,
not from the blended JSONB, and `aggregate_line` is re-derived at serve time from
those per-source rows. The race never reached the historical series; only the
pinned right edge comes off the stored blend. The reported chart example
`/events/15305465` carries no Kalshi or Polymarket series at all and is a
separate defect (#6461).

## why a real server, and not another unit test

Every property asserted here belongs to PostgreSQL and the driver, not to our
Python:

* that `a || b` on JSONB is evaluated INSIDE the UPDATE, so that under READ
  COMMITTED a concurrent UPDATE on the same row blocks and then re-evaluates the
  SET expression against the row the winner committed — the same rule that makes
  `SET n = n + 1` safe where read-modify-write is not. A session double has no
  notion of a row lock and would call both shapes correct;
* that `RETURNING` hands back the post-write row INCLUDING the sibling arm's key,
  which is what the published SSE frame's aggregate must be computed from;
* that the nested `||` preserves sibling keys inside one source's entry. Under
  SQLite `win_probability_sources` is shimmed to JSON, `||` is string
  concatenation, and gotcha #4 is precisely that a JSONB write which reads
  correctly can silently fail to persist.

## the strawman control

`test_the_read_modify_write_shape_still_loses_a_key` runs the OLD shape through
the SAME harness and asserts it LOSES the Kalshi key. Without it, every
assertion below would pass just as happily against a serialised test that never
interleaves, and the gate would be green on the unfixed code. It pins the defect
and proves the interleaving is real — it is a control, not a regression test, and
it must keep FAILING to merge (that is, keep demonstrating the loss).

## what is deliberately NOT asserted here

The throttles, the inversion cache, the snapshot clock and the containment rules
are pure Python and stay in `tests/test_live_blend_refresh.py`. Re-asserting them
behind a `skipif` would move real coverage into a job that does not always run.
"""

import asyncio
import json
import os
from contextlib import asynccontextmanager
from types import SimpleNamespace
from datetime import datetime, timezone
from uuid import uuid4

import pytest
from sqlalchemy import select, text, update

from app.tasks.live_blend_refresh import atomic_stamp_expression
from app.utils.aggregation import stamp_source_reading

DB_URL = os.environ.get("SEARCH_TEST_DATABASE_URL")

needs_postgres = pytest.mark.skipif(
    not DB_URL,
    reason=(
        "set SEARCH_TEST_DATABASE_URL to run the real-Postgres live-blend "
        "concurrent stamp gate (CI job `search-recall` provides one)"
    ),
)

#: The blend as it stands before either socket arm speaks — one sportsbook
#: reading, the weight-3.0 source both arms blend against.
SEEDED = {
    "betting": {"value": 0.5, "updated_at": "2026-09-16T00:00:00+00:00"},
}


#: Marks every `sports` row this gate seeds, so teardown can delete exactly its
#: own rows and nothing else. See `pg_engine` for why it may not simply drop.
MARKER = "blendrace-836"


@pytest.fixture
async def pg_engine():
    """Real Postgres with the real `events` schema — CREATED, never DROPPED.

    THIS FIXTURE MUST NOT DROP ITS TABLES, and the reason is worth stating
    because the obvious drop/create fixture is what every sibling gate in this
    directory uses. CI's `bl_searchtest` is shared by every real-Postgres step
    in the `search-recall` job, and by the time this step runs the full
    `Base.metadata` exists — so `events` has dependent tables
    (`odds_snapshots`, `futures_markets`, `win_prob_snapshots`, …) whose foreign
    keys make dropping it raise `DependentObjectsStillExistError`. Measured on
    this gate's first CI run: green locally against a database that only ever
    held these four tables, red on the runner. A drop that DID succeed would be
    worse — it would silently wreck whichever sibling gate ran next.

    So: create only what is missing, and delete only the rows this gate seeded,
    keyed on `MARKER` in `sports.key`.

    Only the `events` subgraph is named, not `Base.metadata` whole: this gate is
    about one column on one table, and the full metadata carries a
    `NULLS NOT DISTINCT` index that needs PostgreSQL 15+, which would make the
    gate unrunnable on a 14 server for a reason that has nothing to do with it.

    Function-scoped: `pytest.ini` leaves `asyncio_default_fixture_loop_scope`
    unset, so a module-scoped async fixture would outlive the loop that made its
    engine.
    """
    from sqlalchemy.ext.asyncio import create_async_engine

    from app.models.models import Event, FuturesMarket, FuturesOutcome, Sport, Team, Venue
    from app.services.database import Base

    tables = [
        Sport.__table__,
        Venue.__table__,
        Team.__table__,
        Event.__table__,
        FuturesMarket.__table__,
        FuturesOutcome.__table__,
    ]
    engine = create_async_engine(DB_URL)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all, tables=tables)

    yield engine

    async with engine.begin() as conn:
        for table in ("futures_outcomes", "futures_markets"):
            where = (
                "market_id IN (SELECT id FROM futures_markets WHERE sport_id IN"
                " (SELECT id FROM sports WHERE key LIKE :k))"
                if table == "futures_outcomes" else
                "sport_id IN (SELECT id FROM sports WHERE key LIKE :k)"
            )
            await conn.execute(
                text(f"DELETE FROM {table} WHERE {where}"),
                {"k": f"{MARKER}%"},
            )
        await conn.execute(
            text(
                "DELETE FROM events WHERE sport_id IN"
                " (SELECT id FROM sports WHERE key LIKE :k)"
            ),
            {"k": f"{MARKER}%"},
        )
        await conn.execute(
            text("DELETE FROM sports WHERE key LIKE :k"), {"k": f"{MARKER}%"}
        )
    await engine.dispose()


async def _seed_event(engine, sources=None) -> int:
    async with engine.begin() as conn:
        # A unique key per seed: `sports.key` is unique, the database is shared
        # and not reset between tests in this file, and a fixed key would make
        # the second test in the module collide with the first.
        sport_id = (
            await conn.execute(
                text(
                    "INSERT INTO sports (key, name, active) "
                    "VALUES (:k, 'MLB', true) RETURNING id"
                ),
                {"k": f"{MARKER}-{uuid4().hex[:12]}"},
            )
        ).scalar_one()
        return (
            await conn.execute(
                text(
                    "INSERT INTO events (sport_id, home_team_name, away_team_name,"
                    " commence_time, status, created_at, win_probability_sources)"
                    " VALUES (:s, 'Twins', 'Yankees', now(), 'live', now(),"
                    " CAST(:src AS jsonb)) RETURNING id"
                ),
                {"s": sport_id, "src": json.dumps(SEEDED if sources is None else sources)},
            )
        ).scalar_one()


async def _stored(engine, event_id) -> dict:
    from app.models.models import Event

    async with engine.connect() as conn:
        return (
            await conn.execute(
                select(Event.win_probability_sources).where(Event.id == event_id)
            )
        ).scalar_one()


def _values(sources: dict) -> dict:
    return {key: entry.get("value") for key, entry in sources.items()}


async def _interleaved(engine, event_id, arm):
    """Drive two arms through the exact interleaving the dyno produces.

    Deterministic by construction, with `asyncio.Event` barriers rather than
    sleeps: a sleep-timed race reproduces the loss only sometimes (measured — the
    first run of the scratch reproduction lost the key, the second did not), and
    a guard that fires intermittently is not a guard.

    The ordering is the hazard verbatim: both arms observe the same starting
    snapshot, and only then does either write.
    """
    both_have_read = asyncio.Event()
    first_has_written = asyncio.Event()
    readings = {}

    async def run(source, value, goes_first):
        from sqlalchemy.ext.asyncio import async_sessionmaker

        Session = async_sessionmaker(engine, expire_on_commit=False)
        async with Session() as session:
            observed = await arm.read(session, event_id)
            if goes_first:
                # Wait for the sibling to take its own read of the SAME row, so
                # neither arm can see the other's write before it merges.
                await both_have_read.wait()
            else:
                both_have_read.set()
                await first_has_written.wait()
            readings[source] = await arm.write(
                session, event_id, source, value, observed
            )
            await session.commit()
            if goes_first:
                first_has_written.set()

    await asyncio.gather(
        run("kalshi", 0.53, goes_first=True),
        run("polymarket", 0.52, goes_first=False),
    )
    return readings


class _AtomicArm:
    """Production's shape: merge server-side, read the frame off RETURNING."""

    async def read(self, session, event_id):
        return None  # the fix takes no prior read — that is the point

    async def write(self, session, event_id, source, value, observed):
        from app.models.models import Event

        return (
            await session.execute(
                update(Event)
                .where(Event.id == event_id)
                .values(
                    win_probability_sources=atomic_stamp_expression(source, value)
                )
                .returning(Event.win_probability_sources)
            )
        ).scalar_one()


class _ReadModifyWriteArm:
    """The shape that shipped, kept only to prove the harness sees the loss."""

    async def read(self, session, event_id):
        from app.models.models import Event

        return (
            await session.execute(
                select(Event.win_probability_sources).where(Event.id == event_id)
            )
        ).scalar_one_or_none()

    async def write(self, session, event_id, source, value, observed):
        from app.models.models import Event

        merged = stamp_source_reading(observed, source, value)
        await session.execute(
            update(Event)
            .where(Event.id == event_id)
            .values(win_probability_sources=merged)
        )
        return merged


@needs_postgres
class TestConcurrentArmsDoNotEraseEachOther:
    @pytest.mark.asyncio
    async def test_the_read_modify_write_shape_still_loses_a_key(self, pg_engine):
        """STRAWMAN CONTROL. Not a regression test — a proof the gate is armed.

        If this ever stops losing the Kalshi key, the interleaving in
        `_interleaved` has stopped reproducing the hazard and every assertion in
        this file has quietly become vacuous.
        """
        event_id = await _seed_event(pg_engine)
        await _interleaved(pg_engine, event_id, _ReadModifyWriteArm())

        stored = await _stored(pg_engine, event_id)
        assert "kalshi" not in stored, (
            "the control no longer demonstrates the defect — the interleaving "
            "has stopped reproducing it and this file is now vacuous"
        )
        assert _values(stored) == {"betting": 0.5, "polymarket": 0.52}

    @pytest.mark.asyncio
    async def test_both_arms_survive_the_same_interleaving(self, pg_engine):
        """The ship: one row, two venues, both readings kept."""
        event_id = await _seed_event(pg_engine)
        await _interleaved(pg_engine, event_id, _AtomicArm())

        stored = await _stored(pg_engine, event_id)
        assert _values(stored) == {
            "betting": 0.5,
            "kalshi": 0.53,
            "polymarket": 0.52,
        }

    @pytest.mark.asyncio
    async def test_the_returned_row_carries_the_sibling_arms_reading(self, pg_engine):
        """The published frame's aggregate is computed off this dict.

        The write being correct is only half of it: live/305's two disagreeing
        frames were each built from the writer's own private copy. The arm that
        writes SECOND must see the first arm's key in what RETURNING hands back,
        or the wire stays wrong while the row is right.
        """
        event_id = await _seed_event(pg_engine)
        readings = await _interleaved(pg_engine, event_id, _AtomicArm())

        assert _values(readings["polymarket"]) == {
            "betting": 0.5,
            "kalshi": 0.53,
            "polymarket": 0.52,
        }

    @pytest.mark.asyncio
    async def test_the_second_arm_never_publishes_what_the_row_does_not_hold(
        self, pg_engine
    ):
        """Whatever each arm returned must be a subset of what the row ended on.

        Stated as a property rather than a literal so it keeps its teeth if the
        seeded blend changes: an arm may legitimately return fewer keys than the
        final row (it committed before its sibling), but it may never return a
        VALUE the database does not hold for that key.
        """
        event_id = await _seed_event(pg_engine)
        readings = await _interleaved(pg_engine, event_id, _AtomicArm())
        stored = _values(await _stored(pg_engine, event_id))

        for source, returned in readings.items():
            for key, value in _values(returned).items():
                assert stored[key] == value, (
                    f"the {source} arm published {key}={value} while the row "
                    f"holds {stored[key]}"
                )


@needs_postgres
class TestTheServerSideMergePreservesWhatThePythonHelperDid:
    """`atomic_stamp_expression` is `stamp_source_reading` expressed in SQL.

    The two must not drift: other writers (the 15-minute matcher, the 120s poll)
    still go through the Python helper against the same column.
    """

    @pytest.mark.asyncio
    async def test_sibling_keys_inside_the_entry_are_not_stripped(self, pg_engine):
        """An entry carries keys this writer knows nothing about.

        `_apply_final_pm_win_prob`'s suite pins `weight` as preserved and the
        seeded event fixture carries `home_probability`. A writer whose job is to
        ADD a field must not be a writer that deletes fields it does not
        recognise — the inner `||` is what keeps that true server-side.
        """
        event_id = await _seed_event(
            pg_engine,
            {
                "kalshi": {
                    "value": 0.40,
                    "updated_at": "2026-09-16T00:00:00+00:00",
                    "weight": 0.8,
                    "home_probability": 0.40,
                }
            },
        )
        await _interleaved(pg_engine, event_id, _AtomicArm())

        entry = (await _stored(pg_engine, event_id))["kalshi"]
        assert entry["value"] == 0.53, "the reading itself must advance"
        assert entry["weight"] == 0.8
        assert entry["home_probability"] == 0.40

    @pytest.mark.asyncio
    async def test_a_missing_eligibility_does_not_clear_a_recorded_one(
        self, pg_engine
    ):
        """A `None` record never CLEARS one a previous pass wrote.

        The writers run at different cadences over the same event, so a writer
        that has not adopted the record would otherwise strip the evidence a
        writer that has just finished stamping, and the column would oscillate
        between substantiated and not at whichever cadence is faster.
        """
        from app.utils.probability_eligibility import ELIGIBILITY_KEY

        event_id = await _seed_event(
            pg_engine,
            {
                "kalshi": {
                    "value": 0.40,
                    "updated_at": "2026-09-16T00:00:00+00:00",
                    ELIGIBILITY_KEY: {"rule": "pinned-by-a-previous-pass"},
                }
            },
        )
        await _interleaved(pg_engine, event_id, _AtomicArm())

        entry = (await _stored(pg_engine, event_id))["kalshi"]
        assert entry[ELIGIBILITY_KEY] == {"rule": "pinned-by-a-previous-pass"}

    @pytest.mark.parametrize(
        "blank",
        ["sql-null", "jsonb-null"],
        ids=["sql NULL", "the JSONB scalar null"],
    )
    @pytest.mark.asyncio
    async def test_a_blank_column_is_stamped_rather_than_corrupted(
        self, pg_engine, blank
    ):
        """An event whose blend was never written must still stamp cleanly.

        The column is nullable with no default, so "blank" has TWO spellings and
        they fail differently:

        * `NULL || x` is NULL, so a missing guard silently wipes the stamp;
        * `'null'::jsonb || x` is `[null, x]` — `||` PROMOTES a scalar to an
          ARRAY rather than treating it as empty, so a COALESCE-only guard turns
          the blend column into a list and every reader of it breaks.

        The second is why this expression tests `jsonb_typeof(...) = 'object'`
        rather than coalescing: that is the real translation of the Python
        helper's `isinstance(existing, dict)`. This parametrisation exists
        because the first draft of the fix passed the SQL-NULL case and
        corrupted the other.
        """
        from app.models.models import Event

        event_id = await _seed_event(pg_engine)
        async with pg_engine.begin() as conn:
            await conn.execute(
                text(
                    "UPDATE events SET win_probability_sources = "
                    + ("NULL" if blank == "sql-null" else "'null'::jsonb")
                    + " WHERE id = :id"
                ),
                {"id": event_id},
            )
            assert (
                await conn.execute(
                    select(Event.win_probability_sources).where(Event.id == event_id)
                )
            ).scalar_one() is None, "both spellings read back as None in Python"

        await _interleaved(pg_engine, event_id, _AtomicArm())

        stored = await _stored(pg_engine, event_id)
        assert isinstance(stored, dict), f"the column became a {type(stored).__name__}"
        assert _values(stored) == {"kalshi": 0.53, "polymarket": 0.52}

    @pytest.mark.asyncio
    async def test_it_agrees_with_the_python_helper_on_the_uncontended_path(
        self, pg_engine
    ):
        """Single writer, no race: SQL and Python must produce the same dict.

        This is the anti-drift assertion. The concurrency tests above would all
        still pass if the SQL merge wrote a subtly different SHAPE from the one
        every other writer of this column produces.
        """
        from app.models.models import Event

        stamped_at = datetime(2026, 9, 16, 2, 30, tzinfo=timezone.utc)
        event_id = await _seed_event(pg_engine)

        async with pg_engine.begin() as conn:
            via_sql = (
                await conn.execute(
                    update(Event)
                    .where(Event.id == event_id)
                    .values(
                        win_probability_sources=atomic_stamp_expression(
                            "kalshi", 0.53, stamped_at
                        )
                    )
                    .returning(Event.win_probability_sources)
                )
            ).scalar_one()

        via_python = stamp_source_reading(SEEDED, "kalshi", 0.53, now=stamped_at)
        assert via_sql == via_python


async def _concurrent_refresh_frames(engine, monkeypatch, *, prelock_control):
    """Actual refresh/commit path; only inputs, snapshots and fanout are seams.

    The first arm reaches the pre-SAVEPOINT await first, but the sibling obtains
    the row lock first. Observe an actual PostgreSQL transaction lock wait before
    releasing the sibling. No sleep determines which UPDATE wins.
    """
    from sqlalchemy.ext.asyncio import async_sessionmaker

    from app.models.models import Event, FuturesMarket
    from app.tasks import live_blend_refresh as lbr

    event_id = await _seed_event(engine, sources={})
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as session:
        sport_id = (
            await session.execute(select(Event.sport_id).where(Event.id == event_id))
        ).scalar_one()
        for source in ("kalshi", "polymarket"):
            session.add(
                FuturesMarket(
                    sport_id=sport_id,
                    event_id=event_id,
                    source=source,
                    external_id=f"{MARKER}-{source}-{uuid4().hex}",
                    name="Twins vs Yankees",
                )
            )
        await session.commit()

    first_at_savepoint = asyncio.Event()
    sibling_has_lock = asyncio.Event()
    first_attempting_update = asyncio.Event()
    release_sibling = asyncio.Event()
    sibling_published = asyncio.Event()
    before_lock = {}
    pids = {}
    frames = []
    commits = []
    lock_waits = []

    class OrderedSession:
        def __init__(self, session, source):
            self.session, self.source = session, source
            self.nested_count = 0

        def __getattr__(self, name):
            return getattr(self.session, name)

        @asynccontextmanager
        async def begin_nested(self):
            self.nested_count += 1
            if self.nested_count == 1:
                before_lock[self.source] = datetime.now(timezone.utc)
                if self.source == "polymarket":
                    first_at_savepoint.set()
                    await sibling_has_lock.wait()
                else:
                    await first_at_savepoint.wait()
            async with self.session.begin_nested():
                yield

        async def execute(self, statement, *args, **kwargs):
            is_update = getattr(statement, "is_update", False)
            if is_update and self.source == "polymarket":
                first_attempting_update.set()
            result = await self.session.execute(statement, *args, **kwargs)
            if is_update and self.source == "kalshi":
                sibling_has_lock.set()
            return result

    @asynccontextmanager
    async def session_factory():
        source = asyncio.current_task().get_name()
        async with maker() as session:
            pids[source] = (
                await session.execute(text("SELECT pg_backend_pid()"))
            ).scalar_one()
            yield OrderedSession(session, source)
            await session.commit()
            commits.append(source)

    monkeypatch.setattr("app.tasks.base.get_task_session", session_factory)
    monkeypatch.setattr(
        "app.utils.live_blend.compute_source_home_probability",
        lambda group, *_: SimpleNamespace(
            home_probability=0.55 if group[0].market.source == "kalshi" else 0.65,
            eligibility=None,
        ),
    )
    if prelock_control:
        # The old clock placement, with all production SQL/commit/frame code
        # otherwise unchanged. This must make the newer aggregate look older.
        real_expression = lbr.atomic_stamp_expression

        def old_clock(source, value, stamped_at=None, eligibility=None):
            return real_expression(source, value, before_lock[source], eligibility)

        monkeypatch.setattr(lbr, "atomic_stamp_expression", old_clock)

    arms = {}
    for source in ("kalshi", "polymarket"):
        arm = lbr.LiveBlendRefresher(source)

        async def oriented(session, eid, probability, *, reading=None):
            return probability

        async def snapshot(*args, _source=source):
            if _source == "kalshi":
                await release_sibling.wait()

        async def publish(batch, _source=source):
            if _source == "polymarket":
                await sibling_published.wait()
            frames.extend(batch)
            if _source == "kalshi":
                sibling_published.set()

        arm._oriented, arm._maybe_snapshot, arm._publish = oriented, snapshot, publish
        arms[source] = arm

    async def observe_lock():
        await first_attempting_update.wait()
        async with engine.connect() as conn:
            for _ in range(100):
                row = (
                    await conn.execute(
                        text(
                            "SELECT wait_event_type, wait_event FROM pg_stat_activity WHERE pid=:pid"
                        ),
                        {"pid": pids["polymarket"]},
                    )
                ).first()
                if row and row[0] == "Lock":
                    lock_waits.append(tuple(row))
                    release_sibling.set()
                    return
                await asyncio.sleep(0.001)
        release_sibling.set()
        pytest.fail("the test did not exercise an actual PostgreSQL row-lock wait")

    pm = asyncio.create_task(
        arms["polymarket"]._refresh_batch([event_id], 100), name="polymarket"
    )
    await asyncio.wait_for(first_at_savepoint.wait(), 5)
    kalshi = asyncio.create_task(
        arms["kalshi"]._refresh_batch([event_id], 100), name="kalshi"
    )
    await asyncio.wait_for(asyncio.gather(pm, kalshi, observe_lock()), 5)
    stored = await _stored(engine, event_id)
    assert commits == ["kalshi", "polymarket"]
    assert lock_waits == [("Lock", "transactionid")]
    assert [frame["p"] for frame in frames] == [0.55, 0.60]
    assert _values(stored) == {"kalshi": 0.55, "polymarket": 0.65}
    for frame in frames:
        assert frame["updated_at"] == stored[frame["source"]]["updated_at"]
        assert arms[frame["source"]]._dispositions[event_id][2] == frame["updated_at"]
        assert arms[frame["source"]].stats["errors"] == 0
        assert arms[frame["source"]].stats["lock_skipped"] == 0
    return frames


@needs_postgres
@pytest.mark.asyncio
@pytest.mark.parametrize(
    "prelock_control", [False, True], ids=["database-clock", "old-clock-control"]
)
@pytest.mark.parametrize(
    "late_older_publication", [False, True], ids=["commit-order", "late-old-frame"]
)
async def test_newer_committed_blend_has_newer_frame_clock(
    pg_engine,
    monkeypatch,
    prelock_control,
    late_older_publication,
):
    frames = await _concurrent_refresh_frames(
        pg_engine, monkeypatch, prelock_control=prelock_control
    )
    stamps = [datetime.fromisoformat(frame["updated_at"]) for frame in frames]
    assert (stamps[1] > stamps[0]) is not prelock_control

    # Commit-before-publish does not serialize Redis publication across arms.
    # The clock must identify the newest aggregate even when the older committed
    # frame arrives last. This is the native/chart event-watermark contract.
    delivered = frames[::-1] if late_older_publication else frames
    accepted = None
    for frame in delivered:
        if accepted is None or datetime.fromisoformat(
            frame["updated_at"]
        ) > datetime.fromisoformat(accepted["updated_at"]):
            accepted = frame
    assert accepted["p"] == (0.55 if prelock_control else 0.60)
