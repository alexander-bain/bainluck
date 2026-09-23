"""#8132's leg guard, EXECUTED by the real score crowner against real PostgreSQL.

## why this file exists

`tests/test_price_crown_protected_8132.py` proves the clause is PRESENT in every
statement that stamps `game_score`. Presence is not refusal. A guard can be in
the SQL and still write the row — `NOT IN` against a NULL column yields NULL, not
TRUE, which is precisely why the shipped clause wraps the column in `COALESCE`,
and no amount of source-text assertion can tell you whether that `COALESCE` is
there. Only a server decides which rows an `UPDATE` matched.

The thing being graded is a NEGATIVE — "this row did not move" — and a negative is
the easiest claim in testing to satisfy by accident. A board the resolver never
selected, a leg whose name the parser could not read, a market filtered out by the
candidate scan: each leaves the protected row untouched and each would read as a
guard holding. So the corpus carries three legs the guard must NOT stop, on the
same board, graded in the same call:

* **`writable`** — no `resolution_source` at all. The ordinary case. If this one
  does not come back stamped `game_score`, the resolver never reached the board
  and every other assertion in this file is vacuous.
* **`soft`** — `clean_resolution`, the tier-1 price fallback these passes exist to
  supersede. It must be overwritten. This is the over-tightening arm: a guard
  written as "refuse anything already graded" passes every negative assertion
  here and silently stops the resolver doing its job.
* **`own`** — a prior `game_score`. A same-source rewrite, which `is_downgrade`
  permits by name; freezing the pass against its own rows would be a capability
  regression wearing a fix's name.

and two it must:

* **`protected`** — `api_settlement`, `is_winner = false`. #8132's repaired shape
  on the arm that regressed. Ten of these were handed back at 09:45:47Z and
  09:46:06Z on 2026-09-23, six hours after the repair applied.
* **`retraction`** — `ungradeable_result`. The #1852 retraction, whose protection
  `TERMINAL_SOURCES` has claimed in prose since CAL-P056 while the HAVING guard
  named as its defence could not see it (it counts only `is_winner` TRUE rows,
  and a retraction is false).

## the strawman

`test_without_the_guard_the_protected_leg_is_overwritten` runs the PRE-FIX
statement — the same UPDATE with the guard clause removed — against the same
seeded row and requires it to move. Without that arm, a corpus the resolver
silently skipped is indistinguishable from a guard that works, and this whole
file would pass against a codebase with no fix in it at all.

## what this gate does NOT claim

It does not grade the spread parser, the candidate scan's cost, or the upstream
event-attachment defect that made the score wrong in the first place (the board
these ten legs sit on is attached to another game entirely — `matching-symptom`,
#2693). It grades one thing: given a leg an authority already graded, does the
shipped score crowner leave it alone.

There is no PostgreSQL in the agent sandbox by default, so CI's `search-recall`
job is where this normally runs; its skip detection is what stops a silently
skipped gate reading as a passing one.
"""

from __future__ import annotations

import os

import pytest
from sqlalchemy import text

DB_URL = os.environ.get("SEARCH_TEST_DATABASE_URL")

pytestmark = [pytest.mark.asyncio]

needs_postgres = pytest.mark.skipif(
    not DB_URL,
    reason=(
        "set SEARCH_TEST_DATABASE_URL to run the real-Postgres #8132 leg-guard "
        "gate (CI job `search-recall` provides one)"
    ),
)

SPORT_ID = 81320900
EVENT_ID = 81320901
MARKET_ID = 81320902

#: `key -> (outcome_id, leg name, prior is_winner, prior resolution_source)`.
#:
#: The board is a Kalshi run-line ladder on a game the stored score says San
#: Diego won 6–2, so every "San Diego wins by over N" leg grades TRUE from the
#: score and every "Atlanta wins by over N" leg grades FALSE. Both verdicts are
#: represented among the legs the guard must not stop, so a guard that only ever
#: blocked one polarity could not hide here.
LEGS: dict[str, tuple[int, str, bool | None, str | None]] = {
    "protected": (81321101, "San Diego wins by over 3.5 runs", False, "api_settlement"),
    "retraction": (
        81321102,
        "San Diego wins by over 2.5 runs",
        False,
        "ungradeable_result",
    ),
    # 🪤 UNGRADED is `resolution_source IS NULL`, NOT `is_winner IS NULL`:
    # `is_winner` carries a column DEFAULT of False, so "we have no verdict"
    # and "we say this lost" are the same two bytes. That is CAL-P003's note
    # in `resolution_authority` ("is_winner is still the column DEFAULT
    # False, i.e. UNKNOWN truth, not a set of losses"), and it is why the
    # guard keys on the source column and nothing else.
    "writable": (81321103, "San Diego wins by over 1.5 runs", False, None),
    "soft": (81321104, "Atlanta wins by over 1.5 runs", False, "clean_resolution"),
    "own": (81321105, "Atlanta wins by over 2.5 runs", False, "game_score"),
}

#: The legs whose stored verdict must survive a full pass, and what it must be.
MUST_NOT_MOVE = {
    "protected": (False, "api_settlement"),
    "retraction": (False, "ungradeable_result"),
}

#: The legs the pass must still grade, and the verdict the score dictates.
MUST_BE_GRADED = {
    "writable": True,   # SD won by 4, over 1.5
    "soft": False,      # Atlanta did not win by over 1.5
    "own": False,       # Atlanta did not win by over 2.5
}


def _asyncpg_url(url: str) -> str:
    if url.startswith("postgresql+asyncpg://"):
        return url
    return url.replace("postgres://", "postgresql://", 1).replace(
        "postgresql://", "postgresql+asyncpg://", 1
    )


async def _clear(conn) -> None:
    """Remove this file's own rows BY ID, never by DROP.

    `search-recall` runs every real-Postgres gate in sequence against ONE
    database, so `drop_all` here is not a local reset: it raises
    `DependentObjectsStillExistError` on a sibling gate's foreign keys, and when
    it does not raise it deletes their rows (#7147, #2772).
    """
    await conn.execute(
        text("DELETE FROM futures_outcomes WHERE market_id = :m"), {"m": MARKET_ID}
    )
    await conn.execute(
        text("DELETE FROM futures_markets WHERE id = :m"), {"m": MARKET_ID}
    )
    await conn.execute(text("DELETE FROM events WHERE id = :e"), {"e": EVENT_ID})
    await conn.execute(text("DELETE FROM sports WHERE id = :s"), {"s": SPORT_ID})


@pytest.fixture
async def pg_engine():
    """Real Postgres holding the real definitions of the tables this gate uses.

    A NAMED SUBSET, not `Base.metadata.create_all`: the full metadata carries a
    `NULLS NOT DISTINCT` index, PostgreSQL 15 syntax, so whole-schema creation
    dies on a Homebrew Postgres 14 and confines the gate to CI. A gate that can
    be run where the code is written is a gate that gets run.

    Function-scoped because `pytest.ini` leaves
    `asyncio_default_fixture_loop_scope` unset, so a module-scoped async fixture
    would outlive the loop that made its engine (#6215).
    """
    from sqlalchemy.ext.asyncio import create_async_engine

    import app.models.models  # noqa: F401 — registers every table on Base
    from app.services.database import Base

    tables = [
        Base.metadata.tables[name]
        for name in (
            "sports",
            "teams",
            "venues",
            "events",
            "futures_markets",
            "futures_outcomes",
        )
    ]
    engine = create_async_engine(_asyncpg_url(DB_URL))
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all, tables=tables, checkfirst=True)
        await _clear(conn)
    try:
        yield engine
    finally:
        async with engine.begin() as conn:
            await _clear(conn)
        await engine.dispose()


@pytest.fixture
async def session(pg_engine):
    from sqlalchemy.ext.asyncio import async_sessionmaker

    maker = async_sessionmaker(pg_engine, expire_on_commit=False)
    async with maker() as s:
        await _seed(s)
        yield s


async def _seed(s) -> None:
    """Insert the corpus through the ORM.

    The ORM and not raw INSERT: `futures_markets` carries client-side defaults a
    raw INSERT would silently omit, and `test_pg_gate_seed_completeness.py`'s
    raw-INSERT arm keys on the presence of `INSERT INTO`.
    """
    from datetime import datetime, timedelta, timezone

    from app.models import Event, FuturesMarket, FuturesOutcome, Sport

    now = datetime.now(timezone.utc)
    s.add(Sport(id=SPORT_ID, key="baseball_mlb", name="MLB", active=True))
    s.add(
        Event(
            id=EVENT_ID,
            sport_id=SPORT_ID,
            external_id="8132-leg-guard-gate",
            home_team_name="Atlanta Braves",
            away_team_name="San Diego Padres",
            home_score=2,
            away_score=6,
            status="completed",
            commence_time=now - timedelta(days=60),
            completed_at=now - timedelta(days=60) + timedelta(hours=3),
        )
    )
    s.add(
        FuturesMarket(
            id=MARKET_ID,
            source="kalshi",
            external_id="KX8132LEGGATE",
            name="San Diego vs Atlanta: Spread",
            category="game",
            market_tier=5,
            status="resolved",
            event_id=EVENT_ID,
        )
    )
    for key, (oid, name, won, source) in LEGS.items():
        s.add(
            FuturesOutcome(
                id=oid,
                market_id=MARKET_ID,
                external_id=f"KX8132LEGGATE-{key.upper()}",
                name=name,
                # The candidate scan requires a non-NULL price on at least one
                # leg; giving every leg one keeps the scan's shape honest.
                current_probability=0.01,
                is_winner=won,
                resolution_source=source,
            )
        )
    await s.commit()


async def _read(s) -> dict[str, tuple[bool | None, str | None]]:
    rows = (
        await s.execute(
            text(
                "SELECT id, is_winner, resolution_source FROM futures_outcomes "
                "WHERE market_id = :m"
            ),
            {"m": MARKET_ID},
        )
    ).all()
    by_id = {r[0]: (r[1], r[2]) for r in rows}
    return {key: by_id[oid] for key, (oid, *_) in LEGS.items()}


async def _run_the_shipped_resolver(session, monkeypatch) -> dict:
    """Execute the real `_resolve_kalshi_spread_total_from_scores`.

    Its session factory is pointed at this database. The SQL is never restated —
    a gate that re-types the UPDATE proves only that the typist agreed with
    themselves. `scan_in` is left None so the resolver runs its OWN candidate
    scan, which is the half that cannot see an `is_winner = false` retraction and
    therefore the half that keeps handing these boards back.
    """
    import contextlib
    import importlib

    # 🪤 `from app.tasks import backfill_winners` binds the CELERY TASK of that
    # name, which `app/tasks/__init__.py` exports and which shadows the module
    # it lives in. It has no `get_task_session` attribute, and a `setattr` onto
    # it patches nothing the resolver reads. `import_module` is the only form
    # that cannot be shadowed — the same trap the unit band's `_SOURCE` records.
    bw = importlib.import_module("app.tasks.backfill_winners")

    @contextlib.asynccontextmanager
    async def _yield():
        yield session

    monkeypatch.setattr(bw, "get_task_session", _yield)
    return await bw._resolve_kalshi_spread_total_from_scores()


@needs_postgres
async def test_the_seeded_corpus_is_the_defect_shape(session):
    """Asserted BEFORE anything is measured, so a later seed edit cannot make
    the rest of this file vacuous."""
    before = await _read(session)
    assert before["protected"] == (False, "api_settlement")
    assert before["retraction"] == (False, "ungradeable_result")
    assert before["writable"] == (False, None)
    assert before["soft"] == (False, "clean_resolution")
    assert before["own"] == (False, "game_score")

    # And the board must be a CANDIDATE — the whole point of #8132 is that a
    # repaired board does not drop out of the scan. If the HAVING excluded it,
    # nothing below would be testing the guard.
    from app.utils.resolution_authority import OVERWRITABLE_WINNER_SOURCES_SQL

    blocking = (
        await session.execute(
            text(
                "SELECT count(*) FROM futures_outcomes WHERE market_id = :m "
                "AND is_winner AND resolution_source NOT IN "
                + OVERWRITABLE_WINNER_SOURCES_SQL
            ),
            {"m": MARKET_ID},
        )
    ).scalar()
    assert blocking == 0, (
        "the seeded board is excluded by the candidate scan, so this gate would "
        "grade a guard that was never asked a question"
    )


@needs_postgres
async def test_the_resolver_still_grades_the_legs_it_should(session, monkeypatch):
    """The non-vacuity arm AND the over-tightening arm, in one pass.

    If `writable` stays ungraded the resolver never reached the board. If `soft`
    keeps its `clean_resolution` the guard has frozen the pass against exactly
    the tier-1 rows it exists to supersede — a capability regression, not a fix.
    """
    await _run_the_shipped_resolver(session, monkeypatch)
    after = await _read(session)
    for key, expected_winner in MUST_BE_GRADED.items():
        assert after[key] == (expected_winner, "game_score"), (
            f"{key}: expected the score crowner to grade this leg, got {after[key]}"
        )


@needs_postgres
async def test_a_venue_graded_leg_survives_a_full_pass(session, monkeypatch):
    """#8132's ship. The two stamps the repair writes are still there afterwards."""
    await _run_the_shipped_resolver(session, monkeypatch)
    after = await _read(session)
    for key, expected in MUST_NOT_MOVE.items():
        assert after[key] == expected, (
            f"{key}: a score-derived verdict overwrote a leg it may not "
            f"supersede — expected {expected}, got {after[key]}"
        )


@needs_postgres
async def test_the_refusals_are_counted(session, monkeypatch):
    """A refusal nobody counts is a refusal nobody finds.

    This cohort never leaves the candidate set, so the number is expected to be
    steady and non-zero for ever rather than to drain — it is the guard working.
    """
    stats = await _run_the_shipped_resolver(session, monkeypatch)
    assert stats["protected_legs_refused"] >= len(MUST_NOT_MOVE), (
        f"expected at least {len(MUST_NOT_MOVE)} counted refusals, got "
        f"{stats['protected_legs_refused']}"
    )


@needs_postgres
async def test_without_the_guard_the_protected_leg_is_overwritten(session):
    """THE STRAWMAN. The corpus must be capable of showing the damage.

    This is deliberately the PRE-FIX statement, written out rather than imported:
    the point is to run the UPDATE as it stood on master and watch it stamp
    tier 2 over tier 3. If this arm does not move the row, the seeded leg is not
    a specimen and every negative assertion above is satisfied by accident.
    """
    moved = await session.execute(
        text(
            "UPDATE futures_outcomes SET is_winner = :won, "
            "resolution_source = 'game_score', last_updated = NOW() "
            "WHERE id = :oid"
        ),
        {"won": True, "oid": LEGS["protected"][0]},
    )
    await session.commit()
    assert moved.rowcount == 1
    after = await _read(session)
    assert after["protected"] == (True, "game_score"), (
        "the unguarded statement did not reproduce the defect — this corpus "
        "cannot grade the guard"
    )


@needs_postgres
async def test_the_guard_clause_alone_refuses_the_row(session):
    """The clause, isolated, on the two stamps and on a NULL source.

    `NOT IN` against a NULL yields NULL, not TRUE, so an un-COALESCE'd guard
    would refuse every ungraded leg in the system and read here as "very safe".
    The `writable` arm is what catches it.
    """
    from app.tasks.backfill_winners import _GAME_SCORE_LEG_GUARD_SQL

    sql = text(
        "SELECT id FROM futures_outcomes WHERE id = :oid "
        "AND COALESCE(resolution_source, '') NOT IN " + _GAME_SCORE_LEG_GUARD_SQL
    )
    for key in ("protected", "retraction"):
        assert (
            await session.execute(sql, {"oid": LEGS[key][0]})
        ).scalar() is None, f"{key}: the guard clause admits a protected leg"
    for key in ("writable", "soft", "own"):
        assert (
            await session.execute(sql, {"oid": LEGS[key][0]})
        ).scalar() == LEGS[key][0], f"{key}: the guard clause refuses a writable leg"
