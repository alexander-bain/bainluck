"""The play-evidence read gives the same answer through index ranges. #10090, real Postgres.

``LAST_POST_COMMENCE_SNAPSHOT_SQL`` was the largest single cost in the status
pass (production 2026-10-29: 1,643,779 calls, mean 277 ms, max 247 s). Its
``source NOT IN (venues)`` could not be an index condition, so every venue row
of every candidate event was fetched and thrown away — 93% of the table. The
rewrite reaches the rows through the ranges BETWEEN the venue names instead.

Three properties, each one only Postgres can answer:

* ``the_answer_is_unchanged`` — the new SQL, the pre-#10090 SQL (kept verbatim
  below) and a Python oracle agree on every event: rows with no
  ``valid_until``, rows re-observed long after they began, rows whose
  ``valid_until`` is EARLIER than their start, pregame lines renewed past
  kickoff, venue rows fresher than anything else, an event with only venue
  rows, an event not asked about, and hundreds of snapshots per game across
  sources whose names sit just above, just below and between the venue names.
* ``each_source_is_reached_by_exactly_one_arm`` — the arms partition "NULL or
  not a venue" under THIS database's collation: a value in two arms would be
  counted twice by nothing (MAX is idempotent) but a value in none would be
  silently dropped, and that is what this asserts cannot happen.
* ``the_venue_exclusion_is_an_index_condition`` — with production's index
  shape, every scan of ``win_prob_snapshots`` carries ``source`` in its index
  condition. The pre-#10090 SQL is run through the same assertion and must
  FAIL it, so a green here cannot be a check that passes anything.
"""

from __future__ import annotations

import os
import random
from datetime import datetime, timedelta, timezone

import pytest

#: Reuses the #7617 disposable database, which holds nothing but the tables the
#: contracts that share it create and drop (see that file's note on why it is
#: never `bl_searchtest`).
DB_URL = os.environ.get("DELAY_CONTRACT_DATABASE_URL")

pytestmark = [
    pytest.mark.asyncio,
    pytest.mark.skipif(
        not DB_URL,
        reason=(
            "set DELAY_CONTRACT_DATABASE_URL to run the real-Postgres "
            "snapshot-read contract (CI job `search-recall` provisions one)"
        ),
    ),
]

#: The query as it stood before #10090, byte for byte apart from the inlined
#: venue list. The reference the rewrite must agree with.
_PRE_10090_SQL = """
    SELECT x.event_id, MAX(x.last_seen) AS last_snap
    FROM (
        SELECT w.event_id,
               GREATEST(w.captured_at, COALESCE(w.valid_until, w.captured_at))
                   AS last_seen
          FROM win_prob_snapshots w
          JOIN events e ON e.id = w.event_id
         WHERE w.event_id = ANY(:event_ids) AND w.captured_at >= e.commence_time
           AND (w.source IS NULL OR w.source NOT IN ('betting', 'kalshi', 'polymarket'))
    ) x
    GROUP BY x.event_id
"""

#: Play sources on every side of every venue name in any collation's order,
#: including case and whitespace variants that are NOT venues.
_PLAY_SOURCES = (
    "",
    "aaa",
    "backfill",
    "Betting",
    "betting ",
    "bettinga",
    "espn",
    "Kalshi",
    "kalshi2",
    "mlb",
    "polymarke",
    "polymarket_x",
    "stat_model",
    "statpal",
    "zzz",
)
_VENUES = ("betting", "kalshi", "polymarket")


async def _engine_with_tables():
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import create_async_engine

    import app.models.models  # noqa: F401 — registers every table on Base
    from app.services.database import Base

    wanted = [
        Base.metadata.tables[name]
        for name in ("sports", "teams", "venues", "events", "win_prob_snapshots")
    ]
    engine = create_async_engine(DB_URL)
    async with engine.begin() as conn:
        # CASCADE: a contract that ran earlier in this database (#7617's leaves
        # `futures_markets`) can hold foreign keys into `events`. Only those
        # constraints go; every contract sharing the database recreates its own
        # tables before it reads them.
        for table in reversed(wanted):
            await conn.execute(text(f'DROP TABLE IF EXISTS "{table.name}" CASCADE'))
        await conn.run_sync(Base.metadata.create_all, tables=wanted)
    return engine


@pytest.fixture
async def seeded():
    """Twelve events of mixed history; returns (engine, asked_ids, oracle)."""
    from sqlalchemy.ext.asyncio import async_sessionmaker

    from app.models.models import Event, Sport, WinProbSnapshot

    engine = await _engine_with_tables()
    rng = random.Random(10090)
    now = datetime(2026, 10, 29, 23, 0, tzinfo=timezone.utc)
    oracle: dict[int, datetime] = {}
    asked: list[int] = []

    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as session:
        sport = Sport(key="americanfootball_nfl", name="NFL")
        session.add(sport)
        await session.flush()

        events = []
        for i in range(12):
            ev = Event(
                sport_id=sport.id,
                home_team_name=f"Home {i}",
                away_team_name=f"Away {i}",
                commence_time=now - timedelta(hours=1 + i % 5),
                status="live",
            )
            session.add(ev)
            events.append(ev)
        await session.flush()

        rows = []

        def snap(ev, source, captured_at, valid_until):
            rows.append(
                WinProbSnapshot(
                    event_id=ev.id,
                    source=source,
                    captured_at=captured_at,
                    valid_until=valid_until,
                    home_win_probability=0.5,
                    away_win_probability=0.5,
                )
            )
            counts = source not in _VENUES and captured_at >= ev.commence_time
            if counts and ev.id in asked:
                seen = max(captured_at, valid_until or captured_at)
                oracle[ev.id] = max(oracle.get(ev.id, seen), seen)

        # events[11] is never asked about; every other one is.
        asked.extend(ev.id for ev in events[:11])

        for ev in events[:10]:
            start = ev.commence_time
            # Many snapshots per game, every source, both sides of kickoff.
            for _ in range(300):
                source = rng.choice(_PLAY_SOURCES + _VENUES * 4)
                captured = start + timedelta(minutes=rng.uniform(-90, 300))
                shape = rng.random()
                if shape < 0.3:
                    valid_until = None
                elif shape < 0.9:
                    valid_until = captured + timedelta(minutes=rng.uniform(0, 120))
                else:
                    # Earlier than its own start: GREATEST must keep the start.
                    valid_until = captured - timedelta(minutes=rng.uniform(1, 30))
                snap(ev, source, captured, valid_until)
            # The freshest row of the game is a venue's and must not count.
            snap(ev, "kalshi", start + timedelta(minutes=5), now + timedelta(hours=1))
            # A pregame line renewed past kickoff must not count either.
            snap(ev, "espn", start - timedelta(seconds=1), now + timedelta(minutes=30))

        # A game re-observed long after its single reading began (#7617's shape).
        snap(events[0], "espn", events[0].commence_time + timedelta(minutes=1),
             now + timedelta(minutes=45))
        # Only venue rows: no answer at all.
        for venue in _VENUES:
            snap(events[10], venue, events[10].commence_time + timedelta(minutes=3),
                 now)
        # Not asked about, freshest play row in the table.
        snap(events[11], "espn", events[11].commence_time + timedelta(minutes=3),
             now + timedelta(hours=2))

        session.add_all(rows)
        await session.commit()

    assert events[10].id not in oracle and events[11].id not in oracle
    assert len(oracle) == 10
    yield engine, asked, oracle
    await engine.dispose()


async def _read(engine, sql, ids):
    from sqlalchemy import text

    async with engine.connect() as conn:
        result = await conn.execute(text(sql), {"event_ids": ids})
        return {row.event_id: row.last_snap for row in result}


async def test_the_answer_is_unchanged(seeded):
    from app.utils.event_completion import LAST_POST_COMMENCE_SNAPSHOT_SQL

    engine, asked, oracle = seeded
    new = await _read(engine, LAST_POST_COMMENCE_SNAPSHOT_SQL, asked)
    old = await _read(engine, _PRE_10090_SQL, asked)

    assert old == oracle
    assert new == old
    # The single-event call `odds_polling` makes agrees too.
    for event_id in asked:
        assert await _read(engine, LAST_POST_COMMENCE_SNAPSHOT_SQL, [event_id]) == (
            {event_id: oracle[event_id]} if event_id in oracle else {}
        )


async def test_each_source_is_reached_by_exactly_one_arm_unless_it_is_a_venue():
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import create_async_engine

    from app.utils.event_completion import _NON_VENUE_SOURCE_RANGES

    probes = [None, *_PLAY_SOURCES, *_VENUES]
    hits = " + ".join(
        f"CASE WHEN {arm} THEN 1 ELSE 0 END" for arm in _NON_VENUE_SOURCE_RANGES
    )
    values = ", ".join(
        f"(CAST(:p{i} AS varchar(30)))" for i in range(len(probes))
    )
    sql = (
        f"SELECT source, {hits} AS arms "
        f"FROM (VALUES {values}) AS v(source)"
    )
    engine = create_async_engine(DB_URL)
    try:
        async with engine.connect() as conn:
            rows = (await conn.execute(
                text(sql), {f"p{i}": p for i, p in enumerate(probes)}
            )).all()
    finally:
        await engine.dispose()

    got = {row.source: row.arms for row in rows}
    assert got == {p: (0 if p in _VENUES else 1) for p in probes}


def _scans_of(plan, relation):
    node = plan.get("Plan", plan)
    found = []
    if node.get("Relation Name") == relation or node.get("Index Name", "").startswith(
        "ix_winprob"
    ):
        found.append(node)
    for child in node.get("Plans", []):
        found.extend(_scans_of(child, relation))
    return found


async def test_the_venue_exclusion_is_an_index_condition(seeded):
    from sqlalchemy import text

    from app.utils.event_completion import LAST_POST_COMMENCE_SNAPSHOT_SQL

    engine, asked, _ = seeded
    async with engine.begin() as conn:
        # Production's index shape, read from pg_index on 2026-10-29: the model's
        # own single-column indexes do not exist there.
        idx = (await conn.execute(text(
            "SELECT indexname FROM pg_indexes WHERE tablename = 'win_prob_snapshots' "
            "AND indexname <> 'win_prob_snapshots_pkey'"
        ))).scalars().all()
        for name in idx:
            await conn.execute(text(f'DROP INDEX "{name}"'))
        await conn.execute(text(
            "CREATE INDEX ix_winprob_event_source ON win_prob_snapshots (event_id, source)"
        ))
        await conn.execute(text(
            "CREATE INDEX ix_winprob_captured ON win_prob_snapshots (captured_at)"
        ))
        await conn.execute(text("ANALYZE win_prob_snapshots"))

    async def plan(sql):
        import json

        async with engine.connect() as conn:
            await conn.execute(text("SET enable_seqscan = off"))
            raw = (await conn.execute(
                text("EXPLAIN (FORMAT JSON) " + sql), {"event_ids": asked}
            )).scalar()
        return json.loads(raw)[0] if isinstance(raw, str) else raw[0]

    def every_scan_conditions_on_source(p):
        scans = [
            n for n in _scans_of(p, "win_prob_snapshots")
            if n.get("Node Type") != "Bitmap Heap Scan"
        ]
        assert scans, "no scan of win_prob_snapshots in the plan"
        return all("source" in (n.get("Index Cond") or "") for n in scans)

    assert every_scan_conditions_on_source(await plan(LAST_POST_COMMENCE_SNAPSHOT_SQL))
    # The strawman: the pre-#10090 form fetches every row and filters after.
    assert not every_scan_conditions_on_source(await plan(_PRE_10090_SQL))
