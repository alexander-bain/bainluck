"""#2772's FETCH, run on real Postgres over rows whose verdict is already known.

The judgment — :func:`settled_tennis_score_is_impossible` — is covered in full by
``tests/test_a_finished_tennis_match_cannot_have_ended_nil_nil_2772.py``, and no
database is needed to test a rule about two integers. This file exists for the
half a unit test cannot reach.

**A recall fails silently and a judgment fails loudly.** A row the SELECT never
returns cannot fail any test about the rule, so a scoped fetch is the place a
withdrawal quietly stops withdrawing — or quietly starts reaching a population
nobody argued about. Three of its four gates are SQL the ORM writes and nothing
in a unit test executes:

    ``Sport.key LIKE 'tennis%'``     a JOIN, and the only thing standing between
                                    this arm and the 200-odd settled ``0-0``
                                    SOCCER rows on production, where nil-all is
                                    an ordinary result.
    ``status IN (...)``             the CERT-752 control: a SUSPENDED tennis row
                                    holding ``1-0`` is holding a true partial
                                    score.
    ``NOT (greatest(h, a) IN (2,3)  Postgres' ``greatest``, not Python's
      AND h <> a)``                 ``max`` — a different function, with its own
                                    NULL semantics, evaluated by a different
                                    engine.

Every row below is seeded from the production census of 2026-09-16 and its
expected verdict is stated beside it, so the assertion is a set comparison
rather than a count: a recall that returned the right NUMBER of the wrong rows
would pass a count and fails this.
"""

import os
from datetime import datetime, timezone

import pytest
from sqlalchemy import text

from app.tasks.espn_sync import illegal_settled_tennis_score_recall

DB_URL = os.environ.get("SEARCH_TEST_DATABASE_URL")

needs_postgres = pytest.mark.skipif(
    not DB_URL,
    reason=(
        "set SEARCH_TEST_DATABASE_URL to run the real-Postgres #2772 "
        "illegal-tennis-score recall gate (CI job `search-recall` provides one)"
    ),
)

KICKOFF = datetime(2026, 8, 20, 23, 0, tzinfo=timezone.utc)

#: (id, sport_key, status, home, away, should_be_recalled) — the population this
#: arm is allowed to act on, and every neighbour it must walk past. The ids are
#: the production rows wherever a production row exists for the shape.
SEED = [
    # ── the four illegal shapes, settled tennis: ACT ──────────────────────
    (15258192, "tennis_wta_cincinnati_open", "completed", 0, 0, True),
    (15198991, "tennis_atp_cincinnati_open", "completed", 1, 0, True),
    (15199438, "tennis_wta_cincinnati_open", "completed", 1, 1, True),
    (15198600, "tennis_wta_cincinnati_open", "completed", 0, 1, True),
    # `closed`, not `completed` — the status the existing repair misses.
    (15293847, "tennis_atp_us_open", "closed", 0, 0, True),
    # ── legal tennis results: WALK PAST ───────────────────────────────────
    (900001, "tennis_wta_cincinnati_open", "completed", 2, 0, False),
    (900002, "tennis_atp_us_open", "completed", 0, 2, False),
    (900003, "tennis_atp_us_open", "completed", 3, 2, False),
    (900004, "tennis_atp_us_open", "closed", 1, 3, False),
    # ── the CERT-752 control: a PAUSED match's partial score is true ──────
    (900010, "tennis_atp_us_open", "suspended", 0, 0, False),
    (900011, "tennis_atp_us_open", "suspended", 1, 0, False),
    (900012, "tennis_atp_us_open", "live", 1, 1, False),
    (900013, "tennis_atp_us_open", "scheduled", 0, 0, False),
    # ── soccer, where nil-all is a RESULT: 200+ such rows on production ───
    (900020, "soccer_epl", "completed", 0, 0, False),
    (900021, "soccer_usa_mls", "completed", 1, 1, False),
    (900022, "soccer_epl", "closed", 1, 0, False),
    # ── the other sports whose settled 0-0 is its own question, not this ──
    (900030, "baseball_mlb", "completed", 0, 0, False),
    (900031, "basketball_wnba", "completed", 0, 0, False),
    (900032, "americanfootball_cfl", "completed", 0, 0, False),
    # ── no score at all: nothing to refute ────────────────────────────────
    (900040, "tennis_atp_us_open", "completed", None, None, False),
    (900041, "tennis_atp_us_open", "completed", 0, None, False),
    (900042, "tennis_atp_us_open", "completed", None, 0, False),
]

EXPECTED = {row[0] for row in SEED if row[5]}


@pytest.fixture
async def pg_engine():
    """Real Postgres with the real schema. Function-scoped for the reason
    ``test_backup_round_trip_jsonb_6215_pg`` gives: ``pytest.ini`` leaves
    ``asyncio_default_fixture_loop_scope`` unset, so a module-scoped async
    fixture would outlive the loop that made its engine."""
    from sqlalchemy.ext.asyncio import create_async_engine

    import app.models.models  # noqa: F401 — registers every table on Base
    from app.models import Event
    from app.services.database import Base

    # ═══ CREATE, NEVER DROP — AND ONLY THE FOUR TABLES `events` NEEDS ═══
    #
    # The house pattern is `drop_all()` then `create_all()` over the WHOLE
    # metadata, and it is wrong here in both halves.
    #
    # `create_all()` whole cannot run outside CI: one unrelated index is
    # declared `NULLS NOT DISTINCT`, which is Postgres 15 syntax, so it passes
    # on CI's `postgres:15` and fails on a developer's 14. A gate only CI can
    # run is a gate nobody runs before pushing.
    #
    # `drop_all()` over a SUBSET cannot run inside CI, which is how the first
    # version of this file went red there and green here: every step of the
    # `search-recall` job shares one database, the steps before this one have
    # already built the full schema, and `DROP TABLE events` then raises
    # `DependentObjectsStillExistError` naming twelve foreign keys — the exact
    # failure a fresh local database cannot produce. Dropping with CASCADE
    # would "fix" it by deleting a sibling step's tables.
    #
    # So: create with `checkfirst` (a no-op on the shared CI schema, the real
    # thing on an empty local one) and drop nothing, ever. The rows this file
    # seeds are cleaned by id instead, and every assertion is scoped to the ids
    # in SEED — a shared database can hold a sibling step's tennis rows, and a
    # gate that asserted over the whole table would be asserting about them.
    tables = [
        Base.metadata.tables[name] for name in ("sports", "teams", "venues")
    ] + [Event.__table__]
    engine = create_async_engine(DB_URL)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all, tables=tables, checkfirst=True)
        await _clear(conn)
    yield engine
    async with engine.begin() as conn:
        await _clear(conn)
    await engine.dispose()


async def _clear(conn):
    """Remove only this file's own rows, by id. See the fixture for why."""
    await conn.execute(
        text("DELETE FROM events WHERE id = ANY(:ids)"),
        {"ids": [row[0] for row in SEED]},
    )


async def _seed(conn):
    sport_ids = {}
    for key in sorted({row[1] for row in SEED}):
        # `ON CONFLICT` because the database is shared: a sibling step may have
        # inserted `soccer_epl` or a tennis key already, and a plain INSERT
        # would fail on the unique key rather than reuse the row.
        sport_ids[key] = (
            await conn.execute(
                text(
                    "INSERT INTO sports (key, name, active) "
                    "VALUES (:k, :k, true) "
                    "ON CONFLICT (key) DO UPDATE SET active = true RETURNING id"
                ),
                {"k": key},
            )
        ).scalar_one()
    for event_id, sport_key, status, home, away, _ in SEED:
        await conn.execute(
            text(
                "INSERT INTO events (id, sport_id, home_team_name, "
                "away_team_name, commence_time, status, home_score, away_score)"
                " VALUES (:i, :s, 'Home', 'Away', :c, :st, :h, :a)"
            ),
            {
                "i": event_id,
                "s": sport_ids[sport_key],
                "c": KICKOFF,
                "st": status,
                "h": home,
                "a": away,
            },
        )


SEEDED = {row[0] for row in SEED}


async def _served(conn):
    """The recall's answer, split into this file's rows and everybody else's.

    Scoped to SEED for the reason the fixture gives: the CI database is shared
    across the job's steps and can already hold a sibling's tennis rows, so
    `served == EXPECTED` over the whole table would be an assertion about them.
    The foreign count is returned rather than discarded — it belongs in the
    quoted line, so a step that suddenly sees a hundred of them is legible.
    """
    await _seed(conn)
    served = {
        r.id for r in (await conn.execute(illegal_settled_tennis_score_recall())).all()
    }
    return served & SEEDED, served - SEEDED


@needs_postgres
@pytest.mark.asyncio
async def test_the_recall_returns_exactly_the_illegal_settled_tennis_rows(pg_engine):
    async with pg_engine.begin() as conn:
        mine, foreign = await _served(conn)
    assert mine == EXPECTED, {
        "missed": sorted(EXPECTED - mine),
        "over-reached": sorted(mine - EXPECTED),
    }
    print(
        f"\n#2772 RECALL {len(mine)}/{len(EXPECTED)} of {len(SEED)} seeded"
        f" ({len(foreign)} pre-existing rows in the shared database, not asserted on)"
    )


@needs_postgres
@pytest.mark.asyncio
async def test_a_settled_nil_nil_in_a_sport_that_can_draw_is_untouched(pg_engine):
    """Stated as its own test because it is the one over-reach that would be
    invisible on a tennis-only fixture and catastrophic on production: 200-odd
    settled ``0-0`` soccer rows, every one of them a real result."""
    async with pg_engine.begin() as conn:
        mine, _ = await _served(conn)
    assert not mine & {900020, 900021, 900022}


@needs_postgres
@pytest.mark.asyncio
async def test_a_paused_match_keeps_its_partial_score(pg_engine):
    """CERT-752 by id. ``suspended`` and ``live`` rows hold partial scores that
    are TRUE, and the score rule alone would delete all of them."""
    async with pg_engine.begin() as conn:
        mine, _ = await _served(conn)
    assert not mine & {900010, 900011, 900012, 900013}


@needs_postgres
@pytest.mark.asyncio
async def test_postgres_greatest_and_the_python_judgment_agree_row_by_row(pg_engine):
    """The fetch and the judgment, both run over the same seeded rows, must
    produce the same set — ``greatest`` in Postgres and ``max`` in Python are
    different functions in different engines, and #4114's lesson is that the
    half which drifts is always the one no test executes."""
    from app.utils.espn_tennis_anchor import settled_tennis_score_is_impossible
    from app.tasks.espn_sync import TENNIS_STATUSES_CLAIMING_A_RESULT

    async with pg_engine.begin() as conn:
        mine, _ = await _served(conn)

    judged = {
        event_id
        for event_id, sport_key, status, home, away, _ in SEED
        if sport_key.startswith("tennis")
        and status in TENNIS_STATUSES_CLAIMING_A_RESULT
        and settled_tennis_score_is_impossible(home_score=home, away_score=away)
    }
    assert mine == judged
