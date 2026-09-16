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
reading in it at all. The fast-lane chart point comes off the same path, so the
zigzag was drawn as well as pushed.

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
from datetime import datetime, timezone

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


@pytest.fixture
async def pg_engine():
    """Real Postgres with the real `events` schema.

    Only the `events` subgraph is created, not `Base.metadata` whole: this gate
    is about one column on one table, and the full metadata carries a
    `NULLS NOT DISTINCT` index that needs PostgreSQL 15+, which would make the
    gate unrunnable on a 14 server for a reason that has nothing to do with it.

    Function-scoped: `pytest.ini` leaves `asyncio_default_fixture_loop_scope`
    unset, so a module-scoped async fixture would outlive the loop that made its
    engine.
    """
    from sqlalchemy.ext.asyncio import create_async_engine

    import app.models.models as models
    from app.services.database import Base

    tables = [
        models.Event.__table__,
        models.Sport.__table__,
        models.Team.__table__,
        models.Venue.__table__,
    ]
    engine = create_async_engine(DB_URL)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all, tables=tables)
        await conn.run_sync(Base.metadata.create_all, tables=tables)

    yield engine

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all, tables=tables)
    await engine.dispose()


async def _seed_event(engine, sources=None) -> int:
    async with engine.begin() as conn:
        sport_id = (
            await conn.execute(
                text(
                    "INSERT INTO sports (key, name, active) "
                    "VALUES ('baseball_mlb', 'MLB', true) RETURNING id"
                )
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
                    win_probability_sources=atomic_stamp_expression(
                        source, value, datetime.now(timezone.utc)
                    )
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
