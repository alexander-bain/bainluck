"""The #6073 re-date declines a row that moved under it, against a REAL PostgreSQL.

## the defect this gate exists for

CERT-2834 BLOCKed the first cut of `redate_polymarket_listing_stamped_events()`.
It selected the whole repair band in one statement and then wrote each row with

    UPDATE events SET commence_time = :dt, commence_time_source = :src,
                      status = 'scheduled'
    WHERE id = :id

Between those two statements is an open window, and the realtime pollers write
into exactly this band: `sync_*_win_probability`, `espn_sync` and the StatPal
livescore arm all commit scores, periods and `status = 'live'` onto Polymarket-
minted events every two minutes. A score landing inside the window is read by
nobody — the repair is holding a tuple it selected seconds ago — and the repair
then commits `scheduled` over a game a reader can see has started. The page
shows a live match badged as not yet begun. That is #6073's own defect, inverted
and re-shipped by its fix.

`redate_target()` refuses a row with any evidence of play, and the SELECT's WHERE
refuses it too. Neither helps: both ran BEFORE the score arrived. Selecting a row
into a repair band is not permission to write over it, and the only place the
guard can live is the write's own WHERE.

## why a real server, and not another unit test

`tests/test_polymarket_redate_listing_stamped_6073.py` drives the pass through a
`_RecordingSession` that answers the SELECT with a canned list and records the
UPDATE as a string. It can assert that the clauses are PRESENT — it does, and
those arms are worth having — but it cannot evaluate one. Under a double,

* `IS NOT DISTINCT FROM` and `=` are the same characters in a recorded string,
  and the difference between them is the difference between declining six
  nullable columns correctly and declining every row in the band;
* `CAST(:was_commence AS timestamptz)` either satisfies asyncpg's parameter-type
  inference or raises `could not determine data type of parameter` at runtime —
  the wrapper around this sweep in `_poll_polymarket_markets` swallows that into
  `stats["errors"]`, so an uncast bind is a rail that is dead in production and
  green in CI forever;
* a `timestamptz` read back out of Postgres and bound back in has to compare
  EQUAL to itself through the driver's own round trip, which is a claim about
  asyncpg and the column's microsecond precision, not about our code;
* and "did another session's commit become visible to this UPDATE" is a question
  about READ COMMITTED, which a fake has no notion of.

So each arm below drives the SHIPPED function, with a competing writer committing
on a SEPARATE connection at the exact instant the defect needs, and reads the
result back on a THIRD connection — what another process would see.

## the interleave, and why it is deterministic

No sleeps and no threads. The pass calls `redate_target()` once per selected row,
after the SELECT and before that row's UPDATE, so patching it is a hook on
precisely the window CERT-2834 named. The hook commits the competing change on
its own connection and then delegates to the real function, which is still
answering the question it was asked with the values the SELECT read — exactly
what the real race hands it.

## the corpus

Four events, one Polymarket group each, all four minted from the listing stamp
(`commence_time_source = 'polymarket'`, start already in the past, status
`suspended`) and all four carrying a `venue_game_start` 18 hours ahead. They are
identical on every column the repair reads. What differs is only what happens
inside the window:

* **`raced_score`** — a realtime poll commits a score and `status = 'live'`.
  MUST be declined. This is `test_score_arriving_after_redate_selection_...`.
* **`uncontested`** — nothing happens. MUST move, and MUST come back
  `scheduled` with the venue's instant. The complement CERT-2834 required: a
  guard that declines everything is not a guard, and without this arm the file
  would pass with `WHERE false`.
* **`raced_relink`** — the matcher links a second event into the group inside
  the window. MUST be declined: a group naming two fixtures no longer proves
  whose instant this is (#2693).
* **`raced_second_stamp`** — a second market arrives in the group carrying a
  DIFFERENT `venue_game_start`. MUST be declined: the group no longer agrees
  with itself about when the fixture is.

The last two are the matcher's window rather than the score poll's; they are here
because both `NOT EXISTS` clauses are otherwise asserted only as substrings.
"""

import os
from contextlib import asynccontextmanager
from datetime import datetime, timezone

import pytest
from sqlalchemy import text

DB_URL = os.environ.get("SEARCH_TEST_DATABASE_URL")

needs_postgres = pytest.mark.skipif(
    not DB_URL,
    reason=(
        "set SEARCH_TEST_DATABASE_URL to run the real-Postgres #6073 re-date "
        "atomicity gate (CI job `search-recall` provides one)"
    ),
)

UTC = timezone.utc

#: The listing stamp as production carries it: already in the past, which is why
#: every row minted from one has sailed past its own invented kickoff.
LISTED = datetime(2026, 9, 13, 19, 12, tzinfo=UTC)

#: What the venue actually says, 18 hours later and still ahead of `NOW`.
VENUE = datetime(2026, 9, 14, 13, 0, tzinfo=UTC)

#: The pass's own clock for these arms. Fixed, and AFTER `LISTED` but BEFORE
#: `VENUE`, so the status arm is the one under test rather than an accident of
#: when CI happens to run (gotcha #44: offset first, never branch on the clock).
NOW = datetime(2026, 9, 14, 6, 0, tzinfo=UTC)

#: A second, disagreeing instant for the ambiguous-stamp arm.
OTHER_VENUE = datetime(2026, 9, 15, 9, 30, tzinfo=UTC)

#: (key, event_id, group_id)
_CORPUS = [
    ("raced_score", 71001, "polymarket:71001"),
    ("uncontested", 71002, "polymarket:71002"),
    ("raced_relink", 71003, "polymarket:71003"),
    ("raced_second_stamp", 71004, "polymarket:71004"),
    ("raced_unlink", 71005, "polymarket:71005"),
    ("raced_stamp_withdrawn", 71006, "polymarket:71006"),
]

#: The event the relink arm's matcher pulls into the group. Deliberately NOT in
#: the repair band itself, so it cannot be repaired on its own account and the
#: arm can only pass by the `NOT EXISTS` firing.
INTRUDER_EVENT_ID = 71099


@pytest.fixture
async def pg_engine():
    """Real Postgres with the real schema.

    Function-scoped for the reason `test_tag_counts_real_postgres.py` records:
    `pytest.ini` leaves `asyncio_default_fixture_loop_scope` unset, so a
    module-scoped async fixture would outlive the loop that made its engine.
    """
    from sqlalchemy.ext.asyncio import create_async_engine

    import app.models.models  # noqa: F401 — registers every table on Base
    from app.services.database import Base

    engine = create_async_engine(DB_URL)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)

    yield engine

    await engine.dispose()


async def _seed(conn) -> None:
    """Insert the corpus.

    🔴 EVERY NOT NULL COLUMN IS SPELLED OUT, INCLUDING THE ONES THAT LOOK
    OPTIONAL. `futures_markets.category` / `.mutually_exclusive` / `.status` and
    `events.status` / `sports.active` carry a **client-side `default=`**, applied
    by the ORM and invisible to a raw INSERT — omitting one does not take the
    default, it raises `NotNullViolation`.
    """
    sport_id = (
        await conn.execute(
            text(
                "INSERT INTO sports (key, name, active) "
                "VALUES ('tennis_atp', 'ATP', true) RETURNING id"
            )
        )
    ).scalar_one()

    for key, event_id, group_id in _CORPUS:
        await conn.execute(
            text(
                "INSERT INTO events (id, sport_id, home_team_name, away_team_name, "
                "commence_time, commence_time_source, status) "
                "VALUES (:id, :sid, :home, :away, :ct, 'polymarket', 'suspended')"
            ),
            {
                "id": event_id,
                "sid": sport_id,
                "home": f"{key} home",
                "away": f"{key} away",
                "ct": LISTED,
            },
        )
        await conn.execute(
            text(
                "INSERT INTO futures_markets "
                "(source, external_id, name, category, mutually_exclusive, "
                " status, group_id, event_id, market_metadata) "
                "VALUES ('polymarket', :ext, :name, 'sports', true, 'open', "
                "        :gid, :eid, CAST(:meta AS jsonb))"
            ),
            {
                "ext": f"cond-{event_id}",
                "name": f"{key} moneyline",
                "gid": group_id,
                "eid": event_id,
                "meta": '{"venue_game_start": "%s"}' % VENUE.isoformat(),
            },
        )

    # The relink arm's second event. Its own provenance is `odds_api`, so it is
    # outside the repair band and the sweep can never select it.
    await conn.execute(
        text(
            "INSERT INTO events (id, sport_id, home_team_name, away_team_name, "
            "commence_time, commence_time_source, status) "
            "VALUES (:id, :sid, 'intruder home', 'intruder away', :ct, "
            "        'odds_api', 'scheduled')"
        ),
        {"id": INTRUDER_EVENT_ID, "sid": sport_id, "ct": VENUE},
    )


def _session_cm_for(session):
    """`get_task_session` replacement that hands the pass the test's session."""

    @asynccontextmanager
    async def _cm():
        yield session

    return _cm


async def _read(engine, event_id) -> dict:
    """Read the row back on a connection of its own.

    A third connection, never the pass's: what another process would see is the
    only thing worth asserting about a committed repair.
    """
    async with engine.connect() as conn:
        row = (
            await conn.execute(
                text(
                    "SELECT commence_time, commence_time_source, status, "
                    "       home_score, away_score "
                    "FROM events WHERE id = :id"
                ),
                {"id": event_id},
            )
        ).one()
    return {
        "commence_time": row[0],
        "commence_time_source": row[1],
        "status": row[2],
        "home_score": row[3],
        "away_score": row[4],
    }


async def _run_sweep(engine, monkeypatch, *, interfere=None):
    """Drive the SHIPPED sweep, committing `interfere` inside its own window.

    `interfere` is called ONCE, immediately before the pass issues its first
    `UPDATE events` and therefore strictly after the band SELECT has returned —
    exactly the interval CERT-2834 named. It runs on a connection of its own,
    via `engine.begin()`, so what it writes is COMMITTED by another transaction
    before the repair's write is evaluated; under READ COMMITTED that is what
    makes the change visible to the repair's WHERE, which is the mechanism the
    whole guard turns on.

    Deterministic by construction: no sleeps, no threads, no second event loop.
    One hook, on the one statement boundary that matters.

    It fires before the FIRST row's write rather than before its own row's,
    which is strictly harsher — the interference is committed for every row the
    pass goes on to consider, so an arm can only pass by the guard declining,
    never by the pass reaching its row before the writer did.
    """
    from sqlalchemy.ext.asyncio import async_sessionmaker

    import app.tasks.polymarket as poly

    maker = async_sessionmaker(engine, expire_on_commit=False)
    session = maker()

    real_execute = session.execute
    armed = {"yes": interfere is not None}

    async def _execute(stmt, params=None, *a, **kw):
        if armed["yes"] and "UPDATE events" in str(stmt):
            armed["yes"] = False
            async with engine.begin() as other:
                await interfere(other)
        return await real_execute(stmt, params, *a, **kw)

    monkeypatch.setattr(session, "execute", _execute)
    monkeypatch.setattr(poly, "get_task_session", _session_cm_for(session))

    # A fixed clock, for the reason gotcha #44 gives: an arm that branches on
    # the wall clock is an arm that changes its mind at midnight.
    class _Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return NOW

    monkeypatch.setattr(poly, "datetime", _Clock)

    try:
        return await poly.redate_polymarket_listing_stamped_events()
    finally:
        await session.close()


# --------------------------------------------------------------------------
# premise
# --------------------------------------------------------------------------
# Every arm below is stated in terms of a corpus the SELECT must actually
# return. If the band query stopped reaching these rows, every "declined" arm
# would pass for the wrong reason — nothing was declined, nothing was selected.
# This arm is what stops that, and it is why it runs first.


@needs_postgres
@pytest.mark.asyncio
async def test_the_corpus_is_inside_the_repair_band(pg_engine, monkeypatch):
    async with pg_engine.begin() as conn:
        await _seed(conn)

    stats = await _run_sweep(pg_engine, monkeypatch)

    assert stats["scanned"] == len(_CORPUS), (
        "the band query does not reach the corpus — every declined arm in this "
        "file would then pass vacuously"
    )
    assert stats["skipped_no_change"] == 0
    assert stats["skipped_multi_event_group"] == 0
    assert stats["skipped_ambiguous_stamp"] == 0


# --------------------------------------------------------------------------
# the required arm
# --------------------------------------------------------------------------


@needs_postgres
@pytest.mark.asyncio
async def test_score_arriving_after_redate_selection_cannot_be_reset_to_scheduled_6073(
    pg_engine, monkeypatch
):
    """CERT-2834's witness, as a gate.

    A realtime poll commits `4-3` and `status = 'live'` on a SEPARATE connection
    after the repair selected the row and before it writes. The repair must
    decline, count it, and leave every one of the five columns exactly as the
    score poll left them.
    """
    async with pg_engine.begin() as conn:
        await _seed(conn)

    target = 71001

    async def _score_lands(conn):
        await conn.execute(
            text(
                "UPDATE events SET home_score = 4, away_score = 3, "
                "status = 'live', period = 'Set 2' WHERE id = :id"
            ),
            {"id": target},
        )

    stats = await _run_sweep(pg_engine, monkeypatch, interfere=_score_lands)

    after = await _read(pg_engine, target)
    assert after["status"] == "live", (
        "the repair overwrote a started game with `scheduled` — this is "
        "CERT-2834's defect, live"
    )
    assert after["home_score"] == 4 and after["away_score"] == 3
    assert after["commence_time"] == LISTED, (
        "the date moved too: the whole row was written on a stale tuple"
    )
    assert after["commence_time_source"] == "polymarket"
    assert stats["skipped_raced"] >= 1, (
        "declining silently is only half the repair — a rail that writes "
        "nothing must say so"
    )


@needs_postgres
@pytest.mark.asyncio
async def test_an_uncontested_row_still_moves_and_comes_back_scheduled_6073(
    pg_engine, monkeypatch
):
    """The complement, without which `WHERE false` would pass this file.

    Nothing touches this row inside the window, so the ship's actual claim must
    still hold end to end: the venue's instant is written, the provenance says
    where it came from, and a match nobody has played stops reporting itself as
    one that finished with no result.
    """
    async with pg_engine.begin() as conn:
        await _seed(conn)

    stats = await _run_sweep(pg_engine, monkeypatch)

    after = await _read(pg_engine, 71002)
    assert after["commence_time"] == VENUE
    assert after["commence_time_source"] == "polymarket_venue"
    assert after["status"] == "scheduled"
    assert stats["moved"] == len(_CORPUS)
    assert stats["rescheduled"] == len(_CORPUS)
    assert stats["skipped_raced"] == 0


# --------------------------------------------------------------------------
# the matcher's window: both `NOT EXISTS` clauses, evaluated
# --------------------------------------------------------------------------


@needs_postgres
@pytest.mark.asyncio
async def test_a_group_that_gains_a_second_event_inside_the_window_is_declined(
    pg_engine, monkeypatch
):
    async with pg_engine.begin() as conn:
        await _seed(conn)

    async def _matcher_relinks(conn):
        await conn.execute(
            text(
                "INSERT INTO futures_markets "
                "(source, external_id, name, category, mutually_exclusive, "
                " status, group_id, event_id) "
                "VALUES ('polymarket', 'cond-relink', 'relinked leg', 'sports', "
                "        true, 'open', :gid, :eid)"
            ),
            {"gid": "polymarket:71003", "eid": INTRUDER_EVENT_ID},
        )

    stats = await _run_sweep(pg_engine, monkeypatch, interfere=_matcher_relinks)

    after = await _read(pg_engine, 71003)
    assert after["commence_time"] == LISTED, (
        "a group naming two fixtures no longer proves whose instant this is"
    )
    assert after["status"] == "suspended"
    assert stats["skipped_raced"] >= 1


@needs_postgres
@pytest.mark.asyncio
async def test_a_group_that_gains_a_disagreeing_stamp_inside_the_window_is_declined(
    pg_engine, monkeypatch
):
    async with pg_engine.begin() as conn:
        await _seed(conn)

    async def _second_stamp_arrives(conn):
        await conn.execute(
            text(
                "INSERT INTO futures_markets "
                "(source, external_id, name, category, mutually_exclusive, "
                " status, group_id, event_id, market_metadata) "
                "VALUES ('polymarket', 'cond-stamp2', 'second leg', 'sports', "
                "        true, 'open', :gid, :eid, CAST(:meta AS jsonb))"
            ),
            {
                "gid": "polymarket:71004",
                "eid": 71004,
                "meta": '{"venue_game_start": "%s"}' % OTHER_VENUE.isoformat(),
            },
        )

    stats = await _run_sweep(pg_engine, monkeypatch, interfere=_second_stamp_arrives)

    after = await _read(pg_engine, 71004)
    assert after["commence_time"] == LISTED, (
        "a group disagreeing with itself about when the fixture is cannot date it"
    )
    assert after["status"] == "suspended"
    assert stats["skipped_raced"] >= 1


# --------------------------------------------------------------------------
# the matcher's OTHER window: the evidence is withdrawn, not contradicted
# --------------------------------------------------------------------------
# CERT-2837. The two arms above prove the negative clauses fire when the group
# gains something. Neither can fire when the group LOSES everything, because
# `NOT EXISTS` over an empty set is true — so before the two positive `EXISTS`
# these two arms both wrote the venue instant onto an event whose Polymarket
# evidence had just been withdrawn.


@needs_postgres
@pytest.mark.asyncio
async def test_group_unlinked_after_redate_selection_cannot_retime_event_6073(
    pg_engine, monkeypatch
):
    """CERT-2837's witness, as a gate.

    Phase 1.5 detaches a mislinked market by committing `event_id = NULL`. It
    does so on a SEPARATE connection after the repair selected the row and
    before it writes. Both `NOT EXISTS` clauses then pass vacuously — there is
    no second event and no disagreeing stamp, because there is nothing left at
    all — and only a POSITIVE assertion can decline the write.

    The detach is the signal that this group never owned this fixture, so the
    instant it was about to supply is not merely unproven, it is withdrawn. The
    event must keep the row it had.
    """
    async with pg_engine.begin() as conn:
        await _seed(conn)

    async def _phase15_detaches(conn):
        await conn.execute(
            text(
                "UPDATE futures_markets SET event_id = NULL "
                "WHERE group_id = :gid AND source = 'polymarket'"
            ),
            {"gid": "polymarket:71005"},
        )

    stats = await _run_sweep(pg_engine, monkeypatch, interfere=_phase15_detaches)

    after = await _read(pg_engine, 71005)
    assert after["commence_time"] == LISTED, (
        "a group that no longer links this event cannot say when it starts"
    )
    assert after["commence_time_source"] == "polymarket"
    assert after["status"] == "suspended"
    assert stats["skipped_raced"] >= 1


@needs_postgres
@pytest.mark.asyncio
async def test_a_stamp_withdrawn_inside_the_window_cannot_retime_event_6073(
    pg_engine, monkeypatch
):
    """The second positive clause, evaluated.

    A re-ingest rewrites `market_metadata`, and the `venue_game_start` this
    repair was about to trust is no longer there. The group still links the
    event, so the first `EXISTS` is satisfied and only the stamp clause can
    decline it. Writing a remembered instant the venue has stopped publishing is
    the same defect as writing a contradicted one.
    """
    async with pg_engine.begin() as conn:
        await _seed(conn)

    async def _reingest_drops_the_stamp(conn):
        await conn.execute(
            text(
                "UPDATE futures_markets "
                "SET market_metadata = CAST('{}' AS jsonb) "
                "WHERE group_id = :gid AND source = 'polymarket'"
            ),
            {"gid": "polymarket:71006"},
        )

    stats = await _run_sweep(
        pg_engine, monkeypatch, interfere=_reingest_drops_the_stamp
    )

    after = await _read(pg_engine, 71006)
    assert after["commence_time"] == LISTED, (
        "an instant the venue has stopped publishing cannot date the fixture"
    )
    assert after["status"] == "suspended"
    assert stats["skipped_raced"] >= 1


# --------------------------------------------------------------------------
# the binds themselves
# --------------------------------------------------------------------------


@needs_postgres
@pytest.mark.asyncio
async def test_every_cast_in_the_guard_is_one_postgres_accepts(
    pg_engine, monkeypatch
):
    """`IS NOT DISTINCT FROM $1` is un-inferrable, so every bind is CAST.

    A wrong or missing cast raises `could not determine data type of parameter`
    — or, worse, `invalid input syntax`, which is a live row silently skipped.
    The sweep is wrapped in `except Exception` inside `_poll_polymarket_markets`
    precisely so one repair cannot fail a whole poll, which means a raise here
    would be invisible in production forever. This arm executes the shipped
    statement with the shipped binds and asserts it did not raise.
    """
    async with pg_engine.begin() as conn:
        await _seed(conn)

    stats = await _run_sweep(pg_engine, monkeypatch)

    assert stats["moved"] == len(_CORPUS), (
        "a raise inside the sweep is swallowed by the poll's wrapper — this "
        "count is how it becomes visible"
    )
