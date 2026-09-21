"""#7807's durable tier against a REAL PostgreSQL.

PILLAR: TRUTH. SHIP: a market's recovered venue history is still on the chart for
the reader who arrives after Redis has evicted it.

## why a real server, and not another unit test

The sibling unit file (`tests/test_durable_venue_history_7807.py`) covers every
predicate this ship adds. The three things asserted HERE are claims about
PostgreSQL and asyncpg, not about our code, and a double cannot hold any of them:

* **The GUC does not escape.** `read_snapshot` bounds itself with `SET LOCAL
  statement_timeout = 2000`, and `SET LOCAL` lives until the end of the
  TRANSACTION — so on the request session it would still be in force when
  `get_probability_timeline` runs its 30/90-day auto-extend query afterwards. The
  read therefore runs in a savepoint that is ROLLED BACK. A fake session records
  that we called `rollback()`; only a real server can say whether rolling back a
  savepoint actually restores the outer `statement_timeout`. (It does — and
  `RELEASE`, which `async with db.begin_nested()` does on a clean exit, does
  not.) That asymmetry is the entire reason the code is shaped the way it is, and
  this file is the only place it is checked rather than asserted.

* **The payload survives the round trip.** The bank is nested JSONB — a dict of
  outcome ids, each carrying a list of six-element point rows mixing ISO strings,
  floats and nulls. `canonical_json` → `CAST(... AS jsonb)` → asyncpg decode has
  to return the same structure, or the reader draws a chart from something that
  merely prints the same (#6215's class, one column over).

* **The generation guard is the server's, not ours.** `publish_snapshot`'s
  `WHERE ... generation <= EXCLUDED.generation` is what stops a slow writer
  holding an older build from overwriting a newer bank. Under a double the
  `ON CONFLICT` clause is an unparsed string and both writes "succeed".

A skip here is NOT a pass: the CI step that arms this file refuses one.
"""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import text

from app.tasks import generic_market_history_fill as fill
from app.utils import generic_market_history as gmh

DB_URL = os.environ.get("SEARCH_TEST_DATABASE_URL")

needs_postgres = pytest.mark.skipif(
    not DB_URL,
    reason=(
        "set SEARCH_TEST_DATABASE_URL to run the real-Postgres #7807 durable "
        "venue-history gate (CI job `search-recall` provides one)"
    ),
)

pytestmark = needs_postgres

MARKET_ID = 59165099
OUTCOME_ID = 219751686
NOW = datetime(2026, 9, 21, 12, 0, 0, tzinfo=timezone.utc)

#: The resting bound this database serves requests under. Deliberately NOT 2000,
#: so a leak of `read_snapshot`'s own ceiling is visible as a changed value
#: rather than hidden behind a coincidence.
OUTER_TIMEOUT = "31s"


def _payload(*, built_at=NOW, settled=False):
    """A bank with the shape the fill really writes: nested, mixed-type, nullable."""
    return {
        "schema": gmh.SCHEMA,
        "version": gmh.CACHE_VERSION,
        "scale": gmh.SCALE,
        "market_id": MARKET_ID,
        "market_source": "kalshi",
        "market_external_id": "KXCAPGAINDOWN-26AUG-27JAN01",
        "attempted_at": built_at.isoformat(),
        "built_at": built_at.isoformat(),
        "status": "ok",
        "market_settled": settled,
        "outcomes": {
            str(OUTCOME_ID): {
                "outcome_id": OUTCOME_ID,
                "contract": {"venue": "kalshi", "ticker": "KXCAPGAINDOWN-26AUG-27JAN01"},
                "points": [
                    ["2026-09-16T03:00:00+00:00", 0.085, 0.08, 0.09, None, "kalshi_candle_60m"],
                    ["2026-09-17T08:00:00+00:00", 0.06, 0.03, 0.09, None, "kalshi_candle_60m"],
                    ["2026-09-18T04:00:00+00:00", 0.07, 0.05, 0.09, 0.07, "kalshi_candle_1440m"],
                ],
                "observed_through": "2026-09-18T04:00:00+00:00",
            }
        },
        "stats": {"fetched_points": 3},
    }


@pytest.fixture
async def pg_session():
    """Real Postgres holding the ONE table this tier touches.

    Built from `DurableStateSnapshot.__table__` — the real model, so the column
    types, the unique index on `identity` and the JSONB payload are the
    production ones — rather than from `Base.metadata`. Two reasons, and the
    second is the load-bearing one:

    * this ship reads and writes exactly one table, so the rest of the schema is
      set dressing that only slows the gate down;
    * the FULL schema needs PostgreSQL 15+ (`NULLS NOT DISTINCT` in one of its
      indexes), which would confine this file to CI. A narrow gate runs on a
      developer's Postgres 14 too, and a gate that can be run where the code is
      written is a gate that gets run.

    Function-scoped for the reason the #6215 gate gives: `pytest.ini` leaves
    `asyncio_default_fixture_loop_scope` unset, so a module-scoped async fixture
    would outlive the loop that made its engine.
    """
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    from app.models.models import DurableStateSnapshot

    table = DurableStateSnapshot.__table__
    engine = create_async_engine(DB_URL)
    async with engine.begin() as conn:
        await conn.run_sync(table.drop, checkfirst=True)
        await conn.run_sync(table.create)

    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as session:
        yield session

    async with engine.begin() as conn:
        await conn.run_sync(table.drop, checkfirst=True)
    await engine.dispose()


async def _timeout_now(session) -> str:
    return (await session.execute(text("SELECT current_setting('statement_timeout')"))).scalar_one()


# ── the GUC that must not escape ────────────────────────────────────────────


async def test_the_durable_read_restores_the_outer_statement_timeout_7807(pg_session):
    """🔴 THE ARM THIS FILE EXISTS FOR.

    `get_probability_timeline` reads the venue history and THEN runs its 30/90-day
    auto-extend query on the same session, in the same transaction. If
    `read_snapshot`'s 2 s ceiling were still in force it would be a new, invisible
    failure mode for exactly the sparse markets the extend exists to serve — and
    it would look like a slow query, not like this change.
    """
    await pg_session.execute(text(f"SET LOCAL statement_timeout = '{OUTER_TIMEOUT}'"))
    assert await _timeout_now(pg_session) == OUTER_TIMEOUT

    got = await fill.read_durable_history(pg_session, MARKET_ID, now=NOW)

    assert got is None, "nothing published yet — the point is what the read left behind"
    assert await _timeout_now(pg_session) == OUTER_TIMEOUT, (
        "read_snapshot's `SET LOCAL statement_timeout = 2000` escaped onto the "
        "request transaction; the savepoint must be ROLLED BACK, not released"
    )


async def test_the_session_is_still_usable_after_the_savepoint_is_rolled_back(pg_session):
    """A rollback that took the caller's own work with it would be a far worse
    bug than the leak it prevents."""
    await pg_session.execute(text("SET LOCAL statement_timeout = '31s'"))
    await fill.publish_durable_history(pg_session, MARKET_ID, _payload())
    await pg_session.commit()

    await pg_session.execute(text(f"SET LOCAL statement_timeout = '{OUTER_TIMEOUT}'"))
    got = await fill.read_durable_history(pg_session, MARKET_ID, now=NOW)
    assert got is not None

    # The session keeps working, and the outer bound is still the outer bound.
    assert (await pg_session.execute(text("SELECT 1"))).scalar_one() == 1
    assert await _timeout_now(pg_session) == OUTER_TIMEOUT


async def test_a_release_would_have_leaked_the_bound(pg_session):
    """The control for the arm above: this is what the code must NOT do.

    Without it, `test_..._restores_the_outer_statement_timeout` could pass on a
    server where `SET LOCAL` simply never survives a statement — i.e. it could be
    green for a reason that has nothing to do with the rollback.
    """
    await pg_session.execute(text(f"SET LOCAL statement_timeout = '{OUTER_TIMEOUT}'"))
    await pg_session.execute(text("SAVEPOINT leaky"))
    await pg_session.execute(text("SET LOCAL statement_timeout = 2000"))
    await pg_session.execute(text("RELEASE SAVEPOINT leaky"))

    assert await _timeout_now(pg_session) == "2s", (
        "if RELEASE did not leak here, the rollback in read_durable_history "
        "would be proving nothing"
    )


# ── the payload survives a real round trip ──────────────────────────────────


async def test_the_bank_survives_postgres_and_asyncpg_with_its_structure_intact(pg_session):
    """#6215's class: a value that merely PRINTS the same is not the same value."""
    written = _payload()
    stage = await fill.publish_durable_history(pg_session, MARKET_ID, written)
    assert stage["status"] == "ok"
    await pg_session.commit()

    got = await fill.read_durable_history(pg_session, MARKET_ID, now=NOW)

    assert got == written, "the round trip must be exact, not merely equivalent"
    series = got["outcomes"][str(OUTCOME_ID)]["points"]
    assert isinstance(series, list) and len(series) == 3
    # The mixed types inside one row are the part a text column would flatten.
    assert series[0][1] == 0.085 and isinstance(series[0][1], float)
    assert series[0][4] is None, "a null inside a point row must stay a null"
    assert series[2][4] == 0.07
    assert got["outcomes"][str(OUTCOME_ID)]["outcome_id"] == OUTCOME_ID


async def test_the_row_is_filed_under_the_unversioned_identity(pg_session):
    await fill.publish_durable_history(pg_session, MARKET_ID, _payload())
    await pg_session.commit()

    row = (
        await pg_session.execute(
            text(
                "SELECT identity, schema_version, source, complete "
                "FROM durable_state_snapshots WHERE identity = :i"
            ),
            {"i": gmh.durable_identity(MARKET_ID)},
        )
    ).mappings().one()

    assert row["identity"] == f"generic-history:{MARKET_ID}"
    assert row["schema_version"] == gmh.CACHE_VERSION
    assert row["source"] == fill.DURABLE_SOURCE
    assert row["complete"] is True


async def test_one_market_is_one_row_however_many_times_it_is_filled(pg_session):
    """The bank is replaced, never appended — otherwise the tier grows without
    bound at one row per fill instead of one row per market."""
    for hours in (6, 4, 2):
        await fill.publish_durable_history(
            pg_session, MARKET_ID, _payload(built_at=NOW - timedelta(hours=hours))
        )
        await pg_session.commit()

    count = (
        await pg_session.execute(
            text("SELECT count(*) FROM durable_state_snapshots WHERE identity LIKE 'generic-history:%'")
        )
    ).scalar_one()
    assert count == 1


# ── the generation guard is the server's ────────────────────────────────────


async def test_a_slow_writer_holding_an_older_build_cannot_overwrite_a_newer_bank(pg_session):
    """`WHERE generation <= EXCLUDED.generation` is an unparsed string to a
    double, and both writes would 'succeed'."""
    newer = _payload(built_at=NOW)
    older = _payload(built_at=NOW - timedelta(hours=6))
    older["outcomes"][str(OUTCOME_ID)]["points"] = [
        ["2026-09-15T03:00:00+00:00", 0.5, 0.49, 0.51, None, "kalshi_candle_60m"]
    ]

    assert (await fill.publish_durable_history(pg_session, MARKET_ID, newer))["status"] == "ok"
    await pg_session.commit()

    late = await fill.publish_durable_history(pg_session, MARKET_ID, older)
    await pg_session.commit()
    assert late["status"] == "superseded", "the older build must not land"

    got = await fill.read_durable_history(pg_session, MARKET_ID, now=NOW)
    assert got == newer, "the newer bank survived the late writer"


async def test_a_rebuild_of_the_same_generation_is_idempotent(pg_session):
    """`<=`, not `<`: a retry republishing the identical build must still land."""
    payload = _payload()
    assert (await fill.publish_durable_history(pg_session, MARKET_ID, payload))["status"] == "ok"
    await pg_session.commit()
    assert (await fill.publish_durable_history(pg_session, MARKET_ID, payload))["status"] == "ok"
    await pg_session.commit()


# ── the declared life, against a real stored generated_at ───────────────────


async def test_an_open_markets_bank_is_refused_once_past_its_real_36_hours(pg_session):
    """The age is computed from the `generated_at` PostgreSQL actually stored,
    including its timezone handling — not from a value we kept in Python."""
    await fill.publish_durable_history(
        pg_session, MARKET_ID, _payload(built_at=NOW - timedelta(hours=40))
    )
    await pg_session.commit()

    assert await fill.read_durable_history(pg_session, MARKET_ID, now=NOW) is None
    # …and the row is still there: refusing to SERVE it is not deleting it.
    remaining = (
        await pg_session.execute(
            text("SELECT count(*) FROM durable_state_snapshots WHERE identity = :i"),
            {"i": gmh.durable_identity(MARKET_ID)},
        )
    ).scalar_one()
    assert remaining == 1


async def test_a_settled_bank_keeps_its_seven_days(pg_session):
    await fill.publish_durable_history(
        pg_session, MARKET_ID, _payload(built_at=NOW - timedelta(days=4), settled=True)
    )
    await pg_session.commit()

    got = await fill.read_durable_history(pg_session, MARKET_ID, now=NOW)
    assert got is not None and got["market_settled"] is True
