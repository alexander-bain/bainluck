"""#2878 — the twin sweep's WRITE and UNDO, against a real PostgreSQL.

The sqlite half of this ship (`tests/test_tennis_twin_sweep_2878.py`) proves the
judgement and proves the rails honour the label. What it cannot prove is that
the label ever gets written, because the writer is PostgreSQL and nothing else:

    UPDATE events
       SET event_tags = COALESCE(event_tags, '[]'::jsonb) || CAST(:t AS jsonb)
     WHERE id = :eid
       AND NOT COALESCE(event_tags, '[]'::jsonb) @> CAST(:t AS jsonb)

`||` and `@>` are jsonb operators, `event_tags` is JSONB shimmed to JSON under
sqlite, and gotcha #4 exists because a JSONB write that looks right can silently
fail to persist. The idempotence claim in particular lives entirely in that
`NOT @>` — it is a property of the DATABASE, not of this process's memory, and a
suite that never executes the statement cannot grade it.

So this file drives the two shipped scripts' own functions:

    repair_2878_tennis_twin_ghosts.write_tags     the append
    restore_2878_tennis_twin_ghosts.remove_tags   the surgical undo

and asserts, on each side, what the tour page would show.

WHY THE UNDO IS `- tag` AND NOT A RESTORE OF THE BANKED ARRAY
─────────────────────────────────────────────────────────────
`event_tags` is shared and multi-valued — enrichment adds `audience:*` and
`narrative:*`, the registry adds `provenance:*`. Writing a banked array back
would delete every tag anybody added in between. `test_the_undo_leaves_a_tag_
another_writer_added` is that argument executed rather than asserted.

CI: this file is named explicitly in the `search-recall` job. An integration file
without its own step is a gate that exists and never runs — the parent suite's
`test_the_behavioural_search_gate_exists_and_is_wired_into_ci` is on record about
exactly that, and `test_this_gate_is_wired_into_ci` below holds the same line for
this one.
"""

import os
import sys
from datetime import datetime, timezone

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

DB_URL = os.environ.get("SEARCH_TEST_DATABASE_URL")

pytestmark = [
    pytest.mark.skipif(
        not DB_URL,
        reason=(
            "set SEARCH_TEST_DATABASE_URL to run the real-Postgres #2878 twin "
            "sweep write/undo contract (CI job `search-recall` provides one)"
        ),
    ),
    pytest.mark.asyncio,
]

GHOST_ID = 15304918
CANON_ID = 15304938
S_ATP = 1
S_ATP_US_OPEN = 2

NOW = datetime(2026, 9, 6, 20, 0, tzinfo=timezone.utc)
GHOST_TIME = datetime(2026, 9, 4, 0, 0, tzinfo=timezone.utc)
CANON_TIME = datetime(2026, 9, 4, 17, 10, tzinfo=timezone.utc)


@pytest.fixture
async def pg_session():
    """Real Postgres, real schema, real asyncpg type coercion.

    Function-scoped: `pytest.ini` leaves `asyncio_default_fixture_loop_scope`
    unset, so a module-scoped async fixture would outlive the event loop that
    created its engine.
    """
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    import app.models.models  # noqa: F401 — registers every table on Base
    from app.services.database import Base

    engine = create_async_engine(DB_URL)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)

    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as session:
        yield session

    await engine.dispose()


async def _seed(session, *, ghost_tags=None):
    """The Etcheverry–Michelsen pair exactly as #3677 published it."""
    from sqlalchemy import text

    await session.execute(
        text(
            "INSERT INTO sports (id, key, name) VALUES "
            "(:a, 'tennis_atp', 'ATP'), (:b, 'tennis_atp_us_open', 'US Open (ATP)')"
        ),
        {"a": S_ATP, "b": S_ATP_US_OPEN},
    )
    await session.execute(
        text(
            "INSERT INTO events (id, sport_id, home_team_name, away_team_name, "
            "                    commence_time, status, home_score, away_score, event_tags) "
            "VALUES (:gid, :gs, 'Michelsen', 'Etcheverry', :gt, 'scheduled', "
            "        NULL, NULL, CAST(:gtags AS jsonb)), "
            "       (:cid, :cs, 'Alex Michelsen', 'Tomas Martin Etcheverry', :ct, "
            "        'completed', 1, 3, NULL)"
        ),
        {
            "gid": GHOST_ID,
            "gs": S_ATP,
            "gt": GHOST_TIME,
            "gtags": ghost_tags or "[]",
            "cid": CANON_ID,
            "cs": S_ATP_US_OPEN,
            "ct": CANON_TIME,
        },
    )
    await session.commit()


async def _tags(session, event_id):
    from sqlalchemy import text

    return (
        await session.execute(
            text("SELECT COALESCE(event_tags, '[]'::jsonb) FROM events WHERE id = :i"),
            {"i": event_id},
        )
    ).scalar()


async def _tour_page_ids(session):
    """Every card the widened tour page would show, through the real rails."""
    from app.routes.league_futures import (
        recent_results_query,
        unreported_games_query,
        upcoming_games_query,
    )

    ids = []
    for key in ("tennis_atp", "tennis_atp_us_open"):
        for build in (upcoming_games_query, recent_results_query, unreported_games_query):
            rows = (await session.execute(build(key, NOW))).scalars().all()
            ids += [e.id for e in rows]
    return sorted(ids)


async def _plan(session):
    from scripts.repair_2878_tennis_twin_ghosts import build_plan, load_rows

    return build_plan(await load_rows(session, lookback=3650, lookahead=3650))


class TestTheWriteActuallyLands:
    async def test_the_page_shows_two_cards_before_the_sweep(self, pg_session):
        await _seed(pg_session)
        assert await _tour_page_ids(pg_session) == sorted([GHOST_ID, CANON_ID])

    async def test_the_jsonb_append_persists_and_the_ghost_stops_printing(
        self, pg_session
    ):
        """THE SHIP, against the database that will actually run it."""
        from app.services.anchor_channel import duplicate_tag
        from scripts.repair_2878_tennis_twin_ghosts import write_tags

        await _seed(pg_session)
        plan = await _plan(pg_session)
        assert [(t.ghost_id, t.canonical_id) for t in plan.tags] == [
            (GHOST_ID, CANON_ID)
        ]

        written, failed = await write_tags(pg_session, plan.tags)
        assert (written, failed) == (1, [])
        assert await _tags(pg_session, GHOST_ID) == [duplicate_tag(CANON_ID)]
        assert await _tour_page_ids(pg_session) == [CANON_ID]

    async def test_a_second_run_writes_nothing(self, pg_session):
        """Idempotence lives in the `NOT @>`, which is a property of the
        database. Re-running must not append the tag a second time."""
        from scripts.repair_2878_tennis_twin_ghosts import write_tags

        await _seed(pg_session)
        plan = await _plan(pg_session)
        await write_tags(pg_session, plan.tags)
        written, failed = await write_tags(pg_session, plan.tags)
        assert (written, failed) == (0, [])
        assert len(await _tags(pg_session, GHOST_ID)) == 1

    async def test_the_append_preserves_tags_the_row_already_had(self, pg_session):
        """`||` appends; it must not replace. A ghost arrives carrying its own
        provenance and keeps it."""
        from app.services.anchor_channel import duplicate_tag
        from scripts.repair_2878_tennis_twin_ghosts import write_tags

        await _seed(
            pg_session,
            ghost_tags='["provenance:source:kalshi", "provenance:unanchored"]',
        )
        plan = await _plan(pg_session)
        await write_tags(pg_session, plan.tags)
        assert await _tags(pg_session, GHOST_ID) == [
            "provenance:source:kalshi",
            "provenance:unanchored",
            duplicate_tag(CANON_ID),
        ]


class TestTheUndo:
    async def test_the_undo_puts_the_card_back(self, pg_session):
        from scripts.repair_2878_tennis_twin_ghosts import ensure_backup, write_tags
        from scripts.restore_2878_tennis_twin_ghosts import remove_tags

        await _seed(pg_session)
        plan = await _plan(pg_session)
        await ensure_backup(pg_session, plan.tags, {GHOST_ID: "[]"})
        await write_tags(pg_session, plan.tags)
        assert await _tour_page_ids(pg_session) == [CANON_ID]

        class _R:
            event_id, canonical_id = GHOST_ID, CANON_ID

        written, failed = await remove_tags(pg_session, [_R()])
        assert (written, failed) == (1, [])
        assert await _tour_page_ids(pg_session) == sorted([GHOST_ID, CANON_ID])

    async def test_the_undo_leaves_a_tag_another_writer_added(self, pg_session):
        """The argument for `- tag` over restoring the banked array, executed.

        Between the repair and the undo, enrichment adds `narrative:upset_alert`.
        A restore that wrote the banked array back would delete it silently — an
        undo causing the damage it exists to reverse.
        """
        from sqlalchemy import text

        from scripts.repair_2878_tennis_twin_ghosts import ensure_backup, write_tags
        from scripts.restore_2878_tennis_twin_ghosts import remove_tags

        await _seed(pg_session, ghost_tags='["provenance:source:kalshi"]')
        plan = await _plan(pg_session)
        await ensure_backup(
            pg_session, plan.tags, {GHOST_ID: '["provenance:source:kalshi"]'}
        )
        await write_tags(pg_session, plan.tags)

        await pg_session.execute(
            text(
                "UPDATE events SET event_tags = event_tags || "
                "CAST('[\"narrative:upset_alert\"]' AS jsonb) WHERE id = :i"
            ),
            {"i": GHOST_ID},
        )
        await pg_session.commit()

        class _R:
            event_id, canonical_id = GHOST_ID, CANON_ID

        await remove_tags(pg_session, [_R()])
        assert await _tags(pg_session, GHOST_ID) == [
            "provenance:source:kalshi",
            "narrative:upset_alert",
        ]
