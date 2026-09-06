"""`_refine_stand_in_event_starts()`'s SQL and commit, against a REAL PostgreSQL.

## why this gate needs a real server

The rules of the repair are pure and are proved without a database in
`tests/test_stand_in_event_start_refinement.py`. Three things in this rail are
NOT pure, and a fake session can only agree with itself about them:

1. **`WHERE e.commence_time_source = ANY(:derived)`** binds a Python
   `list[str]` to a Postgres `text[]`. That is a driver contract, not a Python
   one. `sorted(DERIVED_COMMENCE_SOURCES)` on a frozenset is the sort of
   expression that raises only when a real driver sees it.

2. **`AND fm.status = 'open'`** is the one WHERE clause the pure predicate does
   NOT duplicate — `_stand_in_refinement_target` never sees a status. Delete it
   and finished matches get re-dated, and no unit test in the tree can tell.
   `test_the_unscoped_query_redates_events_for_matches_already_over` executes
   the mutated shape and requires the damage to be visible.

3. **Whether the UPDATE was COMMITTED, and that it wrote BOTH columns.** Every
   assertion below reads back on a *separate connection*, so what is asserted
   is what another process — the API serving `/api/events/{id}` — would see.

There is no local PostgreSQL in the agent sandbox, so CI is where this runs.

## the corpus

Eight events, each paired with the defect it catches:

* **`refines`** — the ship. Stand-in at Sep 7 midnight, open Kalshi
  `KXATPMATCH` market at the venue's `2026-09-07T18:00Z`. Moves, and its
  `commence_time_source` becomes `kalshi_occurrence`.
* **`two_markets`** — one event, TWO open markets disagreeing about the hour.
  Proves the ORDER BY + dedupe: exactly one write, and a deterministic value.
  Under the pre-dedupe loop the survivor depended on server row order.
* **`itf_next_day`** — the measured Asian ITF draw, +33.5h. Moves.
* **`espn_event`** — identical market, but the event's start came from ESPN.
  The non-overwrite control the cert BLOCK named.
* **`no_source_event`** — `commence_time_source IS NULL`, which is most of the
  table. Must be invisible to `= ANY(:derived)`; a NULL never equals anything,
  so this row also proves the clause is not accidentally `IS DISTINCT FROM`.
* **`closed_market`** — identical to `refines` but the market is `closed`. The
  row that makes clause (2) above load-bearing.
* **`backstop_market`** — dated-match ticker whose market is still on the +14d
  settlement close. Selected by the SQL, refused by the window. This is the
  deploy-ordering row: the repair may run before the poll re-times the market.
* **`outright_market`** — `KXWTA-26USO`, +14d close. Selected by the SQL,
  refused by the dated-match gate. Without that gate this event would be
  dragged a fortnight out.
"""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import text

DB_URL = os.environ.get("SEARCH_TEST_DATABASE_URL")

needs_postgres = pytest.mark.skipif(
    not DB_URL,
    reason=(
        "set SEARCH_TEST_DATABASE_URL to run the real-Postgres stand-in event "
        "start gate (CI job `search-recall` provides one)"
    ),
)

UTC = timezone.utc

STAND_IN_SEP07 = datetime(2026, 9, 7, 0, 0, tzinfo=UTC)
STAND_IN_SEP06 = datetime(2026, 9, 6, 0, 0, tzinfo=UTC)
PUBLISHED = datetime(2026, 9, 7, 18, 0, tzinfo=UTC)
PUBLISHED_LATER = datetime(2026, 9, 7, 20, 30, tzinfo=UTC)
ITF_PUBLISHED = datetime(2026, 9, 7, 9, 30, tzinfo=UTC)
BACKSTOP = datetime(2026, 9, 21, 6, 5, tzinfo=UTC)


# (key, event_source, event_commence, [(external_id, source, status, market_commence), ...])
_EVENTS = [
    ("refines", "kalshi_ticker", STAND_IN_SEP07, [
        ("KXATPMATCH-26SEP07ZVEDAR", "kalshi", "open", PUBLISHED),
    ]),
    ("two_markets", "kalshi_ticker", STAND_IN_SEP07, [
        ("KXATPMATCH-26SEP07AAAZZZ", "kalshi", "open", PUBLISHED),
        ("KXATPMATCH-26SEP07BBBZZZ", "kalshi", "open", PUBLISHED_LATER),
    ]),
    ("itf_next_day", "kalshi_ticker", STAND_IN_SEP06, [
        ("KXITFMATCH-26SEP06STOISH-STO", "kalshi", "open", ITF_PUBLISHED),
    ]),
    ("espn_event", "espn", STAND_IN_SEP07, [
        ("KXATPMATCH-26SEP07ESPESP", "kalshi", "open", PUBLISHED),
    ]),
    ("no_source_event", None, STAND_IN_SEP07, [
        ("KXATPMATCH-26SEP07NULNUL", "kalshi", "open", PUBLISHED),
    ]),
    ("closed_market", "kalshi_ticker", STAND_IN_SEP07, [
        ("KXATPMATCH-26SEP07CLOCLO", "kalshi", "closed", PUBLISHED),
    ]),
    ("backstop_market", "kalshi_ticker", STAND_IN_SEP07, [
        ("KXATPMATCH-26SEP07FARFAR", "kalshi", "open", BACKSTOP),
    ]),
    ("outright_market", "kalshi_ticker", STAND_IN_SEP07, [
        ("KXWTA-26USO", "kalshi", "open", BACKSTOP),
    ]),
]

#: Events whose commence_time the repair must leave exactly where it found it.
_MUST_NOT_MOVE = (
    "espn_event",
    "no_source_event",
    "closed_market",
    "backstop_market",
    "outright_market",
)

#: Events the repair must move, and to what.
_MUST_MOVE = {
    "refines": PUBLISHED,
    "two_markets": PUBLISHED,        # ORDER BY external_id -> AAAZZZ wins
    "itf_next_day": ITF_PUBLISHED,
}


@pytest.fixture
async def pg_engine():
    """Real Postgres with the real schema. Function-scoped for the reason
    `test_tennis_commence_predicate_real_postgres.py` records: `pytest.ini`
    leaves `asyncio_default_fixture_loop_scope` unset, so a module-scoped async
    fixture would outlive the loop that made its engine."""
    from sqlalchemy.ext.asyncio import create_async_engine

    import app.models.models  # noqa: F401 — registers every table on Base
    from app.services.database import Base

    engine = create_async_engine(DB_URL)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)

    yield engine

    await engine.dispose()


async def _seed(conn) -> dict[str, int]:
    """Insert the corpus. Returns `{key: events.id}`.

    🔴 EVERY NOT NULL COLUMN IS SPELLED OUT, INCLUDING THE ONES THAT LOOK
    OPTIONAL. `futures_markets.category` / `.mutually_exclusive` / `.status`
    carry a **client-side `default=`**, applied by the ORM and invisible to a
    raw INSERT — omitting one raises `NotNullViolation` rather than taking the
    default. `tests/test_pg_gate_seed_completeness.py` parses these statements
    against live ORM metadata and this file is registered in its `COVERED`
    tuple, so the check is on the real statement rather than a copied list.
    """
    sport_id = (
        await conn.execute(
            text(
                "INSERT INTO sports (key, name, active) "
                "VALUES ('tennis_atp', 'ATP', true) RETURNING id"
            )
        )
    ).scalar_one()

    ids: dict[str, int] = {}
    for key, event_source, event_commence, markets in _EVENTS:
        event_id = (
            await conn.execute(
                text(
                    "INSERT INTO events "
                    "(sport_id, home_team_name, away_team_name, commence_time, "
                    " commence_time_source, status) "
                    "VALUES (:sid, :home, :away, :ct, :src, 'scheduled') RETURNING id"
                ),
                {
                    "sid": sport_id,
                    "home": f"{key} home",
                    "away": f"{key} away",
                    "ct": event_commence,
                    "src": event_source,
                },
            )
        ).scalar_one()
        ids[key] = event_id

        for ext, source, status, market_commence in markets:
            await conn.execute(
                text(
                    "INSERT INTO futures_markets "
                    "(source, external_id, name, category, mutually_exclusive, "
                    " status, llm_sport_category, commence_time, event_id) "
                    "VALUES (:source, :ext, :name, 'championship', true, "
                    "        :status, 'tennis', :ct, :eid)"
                ),
                {
                    "source": source,
                    "ext": ext,
                    "name": f"{key} market",
                    "status": status,
                    "ct": market_commence,
                    "eid": event_id,
                },
            )

    return ids


def _install_real_session(monkeypatch, engine):
    """Point the production driver at the real server.

    The only seam `_refine_stand_in_event_starts` has is `get_task_session`, so
    the function under test is otherwise untouched — its SQL, its loop, its
    dedupe and its commit are production's.
    """
    from contextlib import asynccontextmanager

    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

    import app.tasks.kalshi as kalshi_task

    maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    @asynccontextmanager
    async def _session():
        async with maker() as session:
            yield session

    monkeypatch.setattr(kalshi_task, "get_task_session", _session)


async def _read_back(engine, ids):
    """Read every event's start on a SEPARATE connection — what another process
    would see, which is the only thing "committed" can mean here."""
    out = {}
    async with engine.connect() as conn:
        for key, event_id in ids.items():
            row = (
                await conn.execute(
                    text(
                        "SELECT commence_time, commence_time_source, status "
                        "FROM events WHERE id = :id"
                    ),
                    {"id": event_id},
                )
            ).one()
            out[key] = row
    return out


# ---------------------------------------------------------------------------
# the driver
# ---------------------------------------------------------------------------

@needs_postgres
async def test_the_repair_moves_only_the_stand_ins_and_commits_the_move(
    pg_engine, monkeypatch
):
    from app.tasks.kalshi import _refine_stand_in_event_starts
    from app.utils.event_completion import KALSHI_OCCURRENCE_COMMENCE_SOURCE

    async with pg_engine.begin() as conn:
        ids = await _seed(conn)

    _install_real_session(monkeypatch, pg_engine)
    moved = await _refine_stand_in_event_starts()

    # Events moved, not rows examined: `two_markets` contributes ONE.
    assert moved == len(_MUST_MOVE), moved

    after = await _read_back(pg_engine, ids)

    for key, expected in _MUST_MOVE.items():
        assert after[key].commence_time == expected, key
        assert after[key].commence_time_source == KALSHI_OCCURRENCE_COMMENCE_SOURCE, key

    for key in _MUST_NOT_MOVE:
        original = next(e[2] for e in _EVENTS if e[0] == key)
        original_source = next(e[1] for e in _EVENTS if e[0] == key)
        assert after[key].commence_time == original, key
        assert after[key].commence_time_source == original_source, key


@needs_postgres
async def test_the_repair_never_writes_status(pg_engine, monkeypatch):
    """Promotion stays the promotion gate's decision, asked of a real time.
    A repair that also flipped `status` would settle unscored rows at the
    sport's maximum duration — the q076 failure this ship exists to end, not
    to relocate."""
    from app.tasks.kalshi import _refine_stand_in_event_starts

    async with pg_engine.begin() as conn:
        ids = await _seed(conn)

    _install_real_session(monkeypatch, pg_engine)
    await _refine_stand_in_event_starts()

    after = await _read_back(pg_engine, ids)
    assert {r.status for r in after.values()} == {"scheduled"}


@needs_postgres
async def test_a_second_run_is_a_no_op(pg_engine, monkeypatch):
    """The poll runs this every cycle. Once an event carries
    `kalshi_occurrence` it is no longer in `DERIVED_COMMENCE_SOURCES`, so the
    SQL cannot select it again — the repair converges instead of rewriting the
    same rows forever (which is the #2020 shape from the other end)."""
    from app.tasks.kalshi import _refine_stand_in_event_starts

    async with pg_engine.begin() as conn:
        ids = await _seed(conn)

    _install_real_session(monkeypatch, pg_engine)
    first = await _refine_stand_in_event_starts()
    before = await _read_back(pg_engine, ids)
    second = await _refine_stand_in_event_starts()
    after = await _read_back(pg_engine, ids)

    assert first == len(_MUST_MOVE)
    assert second == 0
    assert {k: v.commence_time for k, v in before.items()} == {
        k: v.commence_time for k, v in after.items()
    }


@needs_postgres
async def test_the_derived_array_binds_through_the_real_driver(pg_engine):
    """`= ANY(:derived)` with a Python list against a `varchar` column, and a
    NULL row that must not match. Executed as its own statement so a bind
    failure is attributed here rather than surfacing as "the repair moved 0"."""
    from app.utils.event_completion import DERIVED_COMMENCE_SOURCES

    async with pg_engine.begin() as conn:
        await _seed(conn)

    async with pg_engine.connect() as conn:
        selected = (
            await conn.execute(
                text(
                    "SELECT count(*) FROM events "
                    "WHERE commence_time_source = ANY(:derived)"
                ),
                {"derived": sorted(DERIVED_COMMENCE_SOURCES)},
            )
        ).scalar_one()

    expected = sum(1 for e in _EVENTS if e[1] in DERIVED_COMMENCE_SOURCES)
    assert selected == expected, (selected, expected)
    # ...and the NULL row is genuinely excluded rather than counted.
    assert any(e[1] is None for e in _EVENTS)


# ---------------------------------------------------------------------------
# two-armed: the mutated shapes must do observable damage
# ---------------------------------------------------------------------------

@needs_postgres
async def test_the_unscoped_query_redates_events_for_matches_already_over(
    pg_engine,
):
    """Drop `AND fm.status = 'open'` and the damage is real and invisible to
    every pure test in the tree, because `_stand_in_refinement_target` never
    sees a status. Without this arm a green run is equally consistent with
    "the corpus has no closed row in it"."""
    async with pg_engine.begin() as conn:
        await _seed(conn)

    async with pg_engine.connect() as conn:
        swept = (
            await conn.execute(
                text("""
                    SELECT fm.external_id
                    FROM events e
                    JOIN futures_markets fm ON fm.event_id = e.id
                    WHERE e.commence_time_source = ANY(:derived)
                      AND fm.source = 'kalshi'
                      AND fm.commence_time IS NOT NULL
                """),
                {"derived": ["kalshi_ticker"]},
            )
        ).scalars().all()

    assert "KXATPMATCH-26SEP07CLOCLO" in swept, (
        "the closed market must be swept up by the unpredicated query, or the "
        "status clause has nothing to be load-bearing about"
    )


@needs_postgres
async def test_without_the_dated_match_gate_an_outright_moves_a_fortnight(
    pg_engine, monkeypatch
):
    """Neutralise gate 2 and the outright's event is dragged from Sep 7 to the
    +14d settlement close. Asserted by driving the REAL rail with the gate
    stubbed to True, so what is proved is that the production call site
    consults it — not that a re-implementation would have."""
    import app.tasks.kalshi as kalshi_task

    async with pg_engine.begin() as conn:
        ids = await _seed(conn)

    _install_real_session(monkeypatch, pg_engine)
    monkeypatch.setattr(kalshi_task, "_is_dated_match_ticker", lambda _t: True)

    # The window still refuses a +336h move, so widen it too: the two bounds
    # are independent and this arm is about gate 2.
    monkeypatch.setattr(
        kalshi_task, "_STAND_IN_REFINEMENT_MAX", timedelta(days=30)
    )
    await kalshi_task._refine_stand_in_event_starts()

    after = await _read_back(pg_engine, ids)
    assert after["outright_market"].commence_time == BACKSTOP, (
        "with the gates neutralised the outright MUST move — otherwise this "
        "arm proves nothing about them"
    )
