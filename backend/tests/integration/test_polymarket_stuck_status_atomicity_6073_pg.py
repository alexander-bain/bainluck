"""The stuck-status rescue declines a row that moved under it, against real PG.

## the defect this gate exists for

`rescue_stuck_future_status_events()` re-badges a venue-dated fixture standing
`live`/`suspended` over a kickoff that has not happened yet (#6073's last gap —
see `STUCK_FUTURE_STATUS_SQL` for why the class exists and why it is keyed on the
row rather than on either writer).

It therefore inherits CERT-2834's finding whole. It selects a band in one
statement and writes each row in another, and the realtime pollers write into
exactly this band: `sync_*_win_probability`, `espn_sync` and the StatPal
livescore arm commit scores, periods and `status = 'live'` onto Polymarket-minted
events every two minutes. A score landing between the two statements is read by
nobody — the pass is holding a tuple it selected seconds ago — and the pass then
commits `scheduled` over a game a reader can see has started.

That is worse here than in the sibling sweep, because this rail writes ONLY the
status. There is no date change to make the row look repaired; the single column
it touches is the single column that would be wrong.

`stuck_status_target()` refuses any evidence of play, and the band's WHERE
refuses it too. Neither helps: both ran BEFORE the score arrived. The only place
the guard can live is the write's own WHERE.

## why a real server, and not another unit test

`tests/test_polymarket_stuck_status_6073.py` drives the pass through a recording
double. It asserts the clauses are PRESENT — and those arms are worth having, and
a mutation that deletes one of them reddens — but it cannot evaluate one. Under a
double:

* `IS NOT DISTINCT FROM` and `=` are the same characters in a recorded string,
  and the difference between them is the difference between declining six
  nullable columns correctly and declining every row in the band;
* `CAST(:was_commence AS timestamptz)` either satisfies asyncpg's parameter-type
  inference or raises `could not determine data type of parameter` at runtime —
  and the wrapper around this sweep in `_poll_polymarket_markets` swallows that
  into `stats["errors"]`, so an uncast bind is a rail dead in production and
  green in CI forever;
* a `timestamptz` read out of Postgres and bound back in has to compare EQUAL to
  itself through the driver's round trip;
* and "did another session's commit become visible to this UPDATE" is a question
  about READ COMMITTED, which a fake has no notion of.

## the corpus, and why it is seeded from the SERVER's clock

The band's own WHERE says `e.commence_time > now()` — the POSTGRES clock, not a
Python one. So every row is seeded at `now() + interval`, never at a literal
date. A hardcoded 2026 timestamp would sit in the future today, drift into the
past within days, empty the band, and leave every "declined" arm passing because
nothing was ever selected (gotcha #44: offset first, never a literal, and never
branch on the clock). The pass's Python clock is left real for the same reason —
both clocks are then the same machine's, and the arm is true at any hour.

The premise arm runs first and is what makes the rest non-vacuous.

Four rows, identical on every column the pass reads — `polymarket_venue`,
`suspended`, kickoff 9 days out, no score, no period, no clock, no
`completed_at`. What differs is only what happens inside the window:

* **`raced_score`** — a realtime poll commits a score. MUST be declined.
* **`uncontested`** — nothing happens. MUST come back `scheduled`. The
  complement: a guard that declines everything is not a guard, and without this
  arm the file would pass with `WHERE false`.
* **`raced_settled`** — the settlement sweep closes the row. MUST be declined:
  re-opening a settled match to `scheduled` is not this rail's call.
* **`raced_redate`** — another writer moves the kickoff into the past. MUST be
  declined: the premise that made the status refutable is gone.
"""

import os
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import text

DB_URL = os.environ.get("SEARCH_TEST_DATABASE_URL")

needs_postgres = pytest.mark.skipif(
    not DB_URL,
    reason=(
        "set SEARCH_TEST_DATABASE_URL to run the real-Postgres #6073 "
        "stuck-status atomicity gate (CI job `search-recall` provides one)"
    ),
)

UTC = timezone.utc

#: How far ahead of the SERVER's `now()` the corpus starts. Nine days, the shape
#: of the production specimen (`/events/15310205`, "Starts in 9d 22h").
AHEAD = timedelta(days=9, hours=22)

#: (key, event_id)
_CORPUS = [
    ("raced_score", 72001),
    ("uncontested", 72002),
    ("raced_settled", 72003),
    ("raced_redate", 72004),
]

_IDS = {key: event_id for key, event_id in _CORPUS}


#: The tables these arms touch, with `events`' own FK targets so the real
#: column types, nullability and defaults are the ones under test.
#:
#: A SUBSET, and deliberately, where the sibling atomicity file builds the whole
#: schema. `container_provider_anchors` carries `NULLS NOT DISTINCT`, which is
#: PostgreSQL 15+, so a whole-schema `create_all` raises `syntax error at or near
#: "NULLS"` on any 14 server and takes all six arms down with it as ERRORS —
#: before a single one has evaluated anything. A gate that can only run on one
#: machine's server version is a gate that gets shipped unexecuted, which is the
#: one thing this lane's rules do not allow. The subset needs nothing above 9.x
#: and exercises exactly the same `events` DDL.
_TABLES = ("sports", "teams", "venues", "events")


@pytest.fixture
async def pg_engine():
    """Real Postgres with the real `events` schema.

    Function-scoped for the reason `test_tag_counts_real_postgres.py` records:
    `pytest.ini` leaves `asyncio_default_fixture_loop_scope` unset, so a
    module-scoped async fixture would outlive the loop that made its engine.
    """
    from sqlalchemy.ext.asyncio import create_async_engine

    import app.models.models  # noqa: F401 — registers every table on Base
    from app.services.database import Base

    tables = [Base.metadata.tables[name] for name in _TABLES]

    engine = create_async_engine(DB_URL)
    async with engine.begin() as conn:
        # CASCADE, and by hand rather than through `drop_all`. The test database
        # is SHARED with every other integration file, and the ones that build
        # the whole schema leave ~30 tables carrying foreign keys into `events`.
        # A subset `drop_all` then raises `DependentObjectsStillExistError:
        # cannot drop table events because other objects depend on it` — in
        # CI, where files run in one database, and not on a clean local one, so
        # this is exactly the failure that gets discovered after the merge.
        # Dropping the dependents too costs nothing: every file here builds the
        # schema it needs in its own function-scoped fixture.
        await conn.execute(
            text(f"DROP TABLE IF EXISTS {', '.join(reversed(_TABLES))} CASCADE")
        )
        await conn.run_sync(Base.metadata.create_all, tables=tables)

    yield engine

    await engine.dispose()


async def _seed(conn) -> None:
    """Insert the corpus, dated from the SERVER's own clock.

    🔴 EVERY NOT NULL COLUMN IS SPELLED OUT, INCLUDING THE ONES THAT LOOK
    OPTIONAL. `events.status` and `sports.active` carry a **client-side
    `default=`**, applied by the ORM and invisible to a raw INSERT — omitting one
    does not take the default, it raises `NotNullViolation`.
    """
    sport_id = (
        await conn.execute(
            text(
                "INSERT INTO sports (key, name, active) "
                "VALUES ('tennis_atp', 'ATP', true) RETURNING id"
            )
        )
    ).scalar_one()

    for key, event_id in _CORPUS:
        await conn.execute(
            text(
                "INSERT INTO events (id, sport_id, home_team_name, away_team_name, "
                "commence_time, commence_time_source, status) "
                "VALUES (:id, :sid, :home, :away, now() + :ahead, "
                "        'polymarket_venue', 'suspended')"
            ),
            {
                "id": event_id,
                "sid": sport_id,
                "home": f"{key} home",
                "away": f"{key} away",
                "ahead": AHEAD,
            },
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
                    "SELECT status, commence_time, commence_time_source, "
                    "       home_score, away_score "
                    "FROM events WHERE id = :id"
                ),
                {"id": event_id},
            )
        ).one()
    return {
        "status": row[0],
        "commence_time": row[1],
        "commence_time_source": row[2],
        "home_score": row[3],
        "away_score": row[4],
    }


async def _run_sweep(engine, monkeypatch, *, interfere=None):
    """Drive the SHIPPED sweep, committing `interfere` inside its own window.

    `interfere` is called ONCE, immediately before the pass issues its first
    `UPDATE events` and therefore strictly after the band SELECT has returned —
    exactly the interval CERT-2834 named. It runs on a connection of its own, via
    `engine.begin()`, so what it writes is COMMITTED by another transaction
    before the repair's write is evaluated; under READ COMMITTED that is what
    makes the change visible to the repair's WHERE, which is the mechanism the
    whole guard turns on.

    Deterministic by construction: no sleeps, no threads, no second event loop.

    It fires before the FIRST row's write rather than before its own row's, which
    is strictly harsher — the interference is committed for every row the pass
    goes on to consider, so an arm can only pass by the guard declining, never by
    the pass reaching its row before the writer did.

    The clock is NOT patched. The band compares against the server's `now()`, the
    corpus is seeded from the same server's `now()`, and the pass's own
    `datetime.now` is the same machine — patching one of the three is how the two
    drift apart.
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

    try:
        return await poly.rescue_stuck_future_status_events()
    finally:
        await session.close()


# --------------------------------------------------------------------------
# premise
# --------------------------------------------------------------------------
# Every arm below is stated in terms of a corpus the SELECT must actually
# return. If the band stopped reaching these rows, every "declined" arm would
# pass for the wrong reason — nothing was declined, nothing was selected. This
# arm is what stops that, and it is why it runs first.


@needs_postgres
@pytest.mark.asyncio
async def test_the_corpus_is_inside_the_repair_band(pg_engine, monkeypatch):
    async with pg_engine.begin() as conn:
        await _seed(conn)

    stats = await _run_sweep(pg_engine, monkeypatch)

    assert stats["scanned"] == len(_CORPUS), (
        "the band did not reach the corpus — every declined arm in this file "
        "would pass vacuously"
    )
    assert stats["rescheduled"] == len(_CORPUS)
    assert stats["skipped_not_refuted"] == 0
    assert stats["skipped_raced"] == 0


# --------------------------------------------------------------------------
# the race
# --------------------------------------------------------------------------


@needs_postgres
@pytest.mark.asyncio
async def test_a_score_arriving_after_selection_cannot_be_reset_to_scheduled(
    pg_engine, monkeypatch
):
    """The defect CERT-2834 named, on the rail that writes only the status.

    A realtime poll commits a score inside the window. The pass is still holding
    the score-free tuple its SELECT returned, and `stuck_status_target()` already
    said "scheduled" on it. Only the write's own WHERE can decline this.
    """
    async with pg_engine.begin() as conn:
        await _seed(conn)

    target = _IDS["raced_score"]

    async def _score_lands(conn):
        await conn.execute(
            text(
                "UPDATE events SET home_score = 1, away_score = 0, "
                "period = '1S' WHERE id = :id"
            ),
            {"id": target},
        )

    stats = await _run_sweep(pg_engine, monkeypatch, interfere=_score_lands)

    after = await _read(pg_engine, target)
    assert after["status"] == "suspended", (
        "a game with a score on it was re-badged as not yet begun"
    )
    assert after["home_score"] == 1
    assert stats["skipped_raced"] >= 1

    # And the complement, in the same run: the untouched rows still moved, so
    # this arm cannot be passing because the pass declined everything.
    assert (await _read(pg_engine, _IDS["uncontested"]))["status"] == "scheduled"


@needs_postgres
@pytest.mark.asyncio
async def test_an_uncontested_row_comes_back_scheduled_and_keeps_its_kickoff(
    pg_engine, monkeypatch
):
    """The repair actually happens, and touches ONLY the status.

    Without this arm the whole file would pass with `WHERE false`. The kickoff
    and its provenance are asserted unchanged because the date is correct by the
    band's own premise — writing it would overwrite the venue's own statement.
    """
    async with pg_engine.begin() as conn:
        await _seed(conn)

    before = await _read(pg_engine, _IDS["uncontested"])
    stats = await _run_sweep(pg_engine, monkeypatch)
    after = await _read(pg_engine, _IDS["uncontested"])

    assert stats["rescheduled"] == len(_CORPUS)
    assert after["status"] == "scheduled"
    assert after["commence_time"] == before["commence_time"]
    assert after["commence_time_source"] == "polymarket_venue"
    assert after["home_score"] is None


@needs_postgres
@pytest.mark.asyncio
async def test_a_row_settled_inside_the_window_is_not_reopened(
    pg_engine, monkeypatch
):
    """`status` is in the write's WHERE, so a settled row declines.

    The settlement sweep closing a match inside the window is the realistic
    version of this: re-opening it to `scheduled` would un-settle a result, and
    "settled means settled" is a standing ruling.
    """
    async with pg_engine.begin() as conn:
        await _seed(conn)

    target = _IDS["raced_settled"]

    async def _settles(conn):
        await conn.execute(
            text("UPDATE events SET status = 'closed' WHERE id = :id"),
            {"id": target},
        )

    stats = await _run_sweep(pg_engine, monkeypatch, interfere=_settles)

    assert (await _read(pg_engine, target))["status"] == "closed"
    assert stats["skipped_raced"] >= 1


@needs_postgres
@pytest.mark.asyncio
async def test_a_kickoff_moved_into_the_past_inside_the_window_declines(
    pg_engine, monkeypatch
):
    """The premise itself can be withdrawn, and then the status is honest again.

    `commence_time` is in the write's WHERE even though this statement never
    writes it. If another writer re-times the fixture into the past inside the
    window, `suspended` stops being refuted — and a rail holding the old tuple
    would badge a started match as upcoming.
    """
    async with pg_engine.begin() as conn:
        await _seed(conn)

    target = _IDS["raced_redate"]

    async def _retimes(conn):
        await conn.execute(
            text(
                "UPDATE events SET commence_time = now() - interval '2 hours' "
                "WHERE id = :id"
            ),
            {"id": target},
        )

    stats = await _run_sweep(pg_engine, monkeypatch, interfere=_retimes)

    assert (await _read(pg_engine, target))["status"] == "suspended"
    assert stats["skipped_raced"] >= 1


@needs_postgres
@pytest.mark.asyncio
async def test_a_kickoff_crossed_by_the_clock_mid_pass_declines(pg_engine, monkeypatch):
    """CERT-2858's follow-up: the row is unchanged and the WORLD moved.

    Every other declining arm works by changing a column, which the tuple guard
    catches. This one changes nothing at all — the row is byte-identical to what
    the SELECT read — and the pass must still decline it, because wall time has
    crossed the kickoff while the pass worked. A long lock wait or simply a large
    band is enough, and the result is `scheduled` committed onto a match that has
    started.

    Only `AND e.commence_time > clock_timestamp()` can decline this, and the
    spelling is the whole point. `now()` — the form the review asked for — is
    `transaction_timestamp()`, frozen for the life of the transaction this pass
    runs in, so it would compare the kickoff against the same instant the band
    already compared it against and never fire. This arm is what tells those two
    spellings apart: swap `clock_timestamp()` for `now()` and it reddens.

    🔴 THE ONLY SLEEP IN THIS FILE, and it is load-bearing rather than a
    substitute for thinking about the interleave. The fixture seeds this row two
    seconds ahead, so it is comfortably inside the band when the SELECT runs; the
    hook then holds the pass for three. There is no way to advance a server's
    clock, and no column to change — the absence of a change IS the premise.
    A full second of margin sits on each side of the crossing.

    Vacuity is checked rather than assumed: `scanned` proves the row was really
    selected. Without that, a machine slow enough to miss the band would pass
    this arm by declining nothing.
    """
    async with pg_engine.begin() as conn:
        await _seed(conn)
        # Two seconds out, not nine days: this row must be crossable.
        await conn.execute(
            text(
                "UPDATE events SET commence_time = now() + interval '2 seconds' "
                "WHERE id = :id"
            ),
            {"id": _IDS["raced_score"]},
        )

    async def _time_passes(conn):
        await conn.execute(text("SELECT pg_sleep(3)"))

    stats = await _run_sweep(pg_engine, monkeypatch, interfere=_time_passes)

    assert stats["scanned"] == len(_CORPUS), (
        "the crossable row was not inside the band — this arm would decline "
        "nothing and pass for the wrong reason"
    )
    after = await _read(pg_engine, _IDS["raced_score"])
    assert after["status"] == "suspended", (
        "a match whose kickoff passed while the sweep worked was badged as not "
        "yet begun"
    )
    assert stats["skipped_raced"] >= 1

    # The complement: rows nine days out were untouched by the same clock and
    # still moved, so this is the guard firing and not the pass failing.
    assert (await _read(pg_engine, _IDS["uncontested"]))["status"] == "scheduled"


# --------------------------------------------------------------------------
# the driver
# --------------------------------------------------------------------------


@needs_postgres
@pytest.mark.asyncio
async def test_the_guard_matches_a_row_whose_compared_columns_are_all_null(
    pg_engine, monkeypatch
):
    """`IS NOT DISTINCT FROM`, not `=`, and this is the arm that proves it.

    Six of the eight columns the write re-asserts are nullable and NULL is their
    common value — every row in the corpus is NULL on all six, which is exactly
    production's shape. Under an `=` form `NULL = NULL` is not true, so the WHERE
    would match nothing, the rail would repair zero rows, and it would report
    success while doing so. Mutation-checked: rewriting the guard's eight
    comparisons to `=` reddens four of the six arms in this file.

    🔴 WHAT THIS ARM DOES **NOT** PROVE, stated because the name it was first
    given claimed it did. It was written as "every cast is one Postgres accepts",
    on the sibling guard's rationale that `IS NOT DISTINCT FROM $1` leaves
    asyncpg no parameter type to infer and raises at runtime — which
    `_poll_polymarket_markets` would swallow into `stats["errors"]`, making an
    uncast bind a rail dead in production and green in CI. MEASURED 2026-09-14
    against a real server: removing ALL EIGHT casts from
    `_STUCK_STATUS_UNCHANGED_WHERE` leaves all six arms passing. Every bind in
    this statement sits opposite a typed column, so Postgres infers each one and
    the casts are never reached for. They are kept for symmetry with the sibling
    guard, where the binds are compared against `jsonb->>` expressions, and they
    cost nothing — but the thing holding them in place is the STRUCTURAL arm in
    `tests/test_polymarket_stuck_status_6073.py`, not this one, and an inherited
    rationale nobody re-measured is how a guard ends up asserting a property it
    cannot see.
    """
    async with pg_engine.begin() as conn:
        await _seed(conn)

    stats = await _run_sweep(pg_engine, monkeypatch)

    assert stats["rescheduled"] == len(_CORPUS)
    assert stats["skipped_raced"] == 0
