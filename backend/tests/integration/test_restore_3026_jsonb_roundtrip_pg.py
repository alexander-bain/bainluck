"""#3026 — the D51 undo must actually execute. CERT-932's named repair.

WHY THIS FILE EXISTS. `repair_3026_question_events.py` deletes events. D51
authorises that UNATTENDED only because a one-command restore ships beside it,
so the restore is not a convenience — it is the entire basis on which the delete
is allowed to run without Alex watching. CERT-932 found that the restore could
not run at all.

The defect, in one line: the banked rows are written by `to_jsonb(e)` in SQL and
read back as **decoded Python dicts**, and `restore_3026_question_events.py`
handed those dicts to a `text()` bind with no type. An unannotated bind compiles
as `NullType`, `NullType` has no bind processor, so the dict reached asyncpg
untouched — and SQLAlchemy's asyncpg jsonb codec expects the dialect's own
serializer to have already produced a string, so it called `.encode()` on a dict
and raised `AttributeError: 'dict' object has no attribute 'encode'` on the
first insert of the first row.

WHY NOTHING CAUGHT IT, and why the fix needs a server to prove. Every cheaper
instrument is green over this defect by construction:

  * the statement COMPILES — the type error is in the value, not the SQL;
  * the module IMPORTS, so a startup gate says nothing;
  * the DRY RUN passes and prints a complete, correct plan, because the dry run
    is defined as the path that never executes an insert;
  * sqlite has no jsonb codec to be wrong about, so an ORM-projection proof
    would round-trip the dict happily;
  * a mock session records the call and asserts on the bind dict, which is the
    dict that never worked.

The only reader that can tell is asyncpg talking to a real PostgreSQL. Hence
this gate, and hence `search-recall` (there is no Postgres in the agent
sandbox — `initdb` dies on `shmget`).

WHAT IT COVERS, which is the list CERT-932 named: the event row, its JSONB
columns, `line_movement_analyses`, `win_prob_snapshots`, `event_provider_anchors`
and the `futures_markets` relink — seeded, backed up and deleted by the SHIPPED
repair functions, then restored by the SHIPPED restore functions. Not a
paraphrase of either: `build_plan` classifies the seeded row itself, so a change
to the predicate that stops selecting it fails here too.

THE RED ARM is the point of the third test. A gate that only exercises the fixed
path cannot tell you the fix is what is holding it up: it would stay green if
someone deleted `_populate_insert` and inlined an untyped `text()` again. So the
last test puts the untyped bind back and asserts the restore RAISES. If that
test ever passes-by-not-raising, this file has stopped guarding anything.
"""

from __future__ import annotations

import os
from datetime import datetime, timezone

import pytest

DB_URL = os.environ.get("SEARCH_TEST_DATABASE_URL")

needs_postgres = pytest.mark.skipif(
    not DB_URL,
    reason=(
        "set SEARCH_TEST_DATABASE_URL to run the #3026 restore round-trip gate "
        "(CI job `search-recall` provides one)"
    ),
)

#: The seeded fiction. `question_refusal_reason` refuses this home name, and
#: `reconstruct_matchup` recovers NOTHING from it — so the repair classifies it
#: `delete / no_fixture_named`, the deterministic no-counterpart path the seven
#: live WSOP cards take. Chosen over the `duplicate` path deliberately: that one
#: turns on a counterpart search whose result depends on what else is in the
#: table, and a gate about JSONB binds should not be able to fail for a reason
#: about matching.
FICTION_HOME = "Will Greg Mueller Finish Top 3"
FICTION_AWAY = "Field"

#: The market must be THE FICTION — `market_is_the_fiction()` True — or
#: `build_plan` holds the row as `owns_real_markets` and never reaches a delete.
#: The question mark is load-bearing by its ABSENCE: `extract_matchup` does not
#: split "Top 3? vs Field", so a market named with one parses to None, reads as
#: a real market, and silently converts this gate into a test of the hold path.
FICTION_MARKET = "Will Greg Mueller Finish Top 3 vs Field"

EVENT_ID = 990001
MARKET_ID = 990002
COMMENCE = datetime(2026, 9, 4, 15, 0, tzinfo=timezone.utc)

#: Distinct payloads per column, so an assertion cannot pass on the wrong one.
WPS_JSON = {"kalshi": {"probability": 0.41, "book_count": 1}}
TAGS_JSON = ["wsop", "question-shaped"]
ALT_NAMES_JSON = ["Greg Mueller", "G. Mueller"]
MOVEMENT_JSON = {"opened": 0.30, "closed": 0.41, "steps": [0.30, 0.36, 0.41]}
GAME_STATE_JSON = {"period": "final", "clock": None}
CLAIM_CONTEXT_JSON = {"claimed_by": "kalshi", "confidence": "low"}


@pytest.fixture
async def pg_engine():
    """Real Postgres with the real schema.

    Function-scoped: `pytest.ini` leaves `asyncio_default_fixture_loop_scope`
    unset, so a module-scoped async fixture would outlive the loop that made its
    engine. Same shape as `test_link_tennis_already_linked_pg.py`.
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


@pytest.fixture
async def session(pg_engine):
    """A live async session, seeded, with the backup tables guaranteed absent.

    The repair's `ensure_backup` is `CREATE TABLE IF NOT EXISTS` and its inserts
    are `ON CONFLICT DO NOTHING`, so a backup surviving from a previous test
    would make the second run bank nothing and restore stale rows. `drop_all`
    above does not touch them — they are not Alembic-managed and not on
    `Base.metadata` — so they are dropped explicitly.
    """
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import async_sessionmaker

    maker = async_sessionmaker(pg_engine, expire_on_commit=False)
    async with maker() as s:
        for table in ("bak_3026_question_events", "bak_3026_market_links"):
            await s.execute(text(f"DROP TABLE IF EXISTS {table}"))
        await s.commit()
        await _seed(s)
        yield s


async def _seed(s):
    """One fictional event, one fiction market, and one row per child table.

    🔴 EVERY NOT NULL COLUMN WITHOUT A SERVER DEFAULT IS SPELLED OUT.
    `events.sport_id/.home_team_name/.away_team_name/.commence_time/.status`;
    `futures_markets.source/.external_id/.name/.category/.mutually_exclusive/
    .status`; `win_prob_snapshots.event_id/.source/.reading_count`;
    `event_provider_anchors.event_id/.source/.source_id/.id_kind`;
    `line_movement_analyses.analysis_type`. A raw INSERT does not run a
    client-side `default=`, only a `server_default`, and
    `tests/test_pg_gate_seed_completeness.py` parses these statements against
    live ORM metadata — this file is registered in its `COVERED` tuple.
    """
    import json

    from sqlalchemy import text

    await s.execute(
        text(
            "INSERT INTO sports (id, key, name, active) "
            "VALUES (1, 'poker_wsop', 'WSOP', true)"
        )
    )
    await s.execute(
        text(
            "INSERT INTO events (id, sport_id, home_team_name, away_team_name, "
            "commence_time, status, win_probability_sources, event_tags, "
            "home_team_alt_names) "
            "VALUES (:id, 1, :home, :away, :ct, 'scheduled', "
            "CAST(:wps AS jsonb), CAST(:tags AS jsonb), CAST(:alt AS jsonb))"
        ),
        {
            "id": EVENT_ID,
            "home": FICTION_HOME,
            "away": FICTION_AWAY,
            "ct": COMMENCE,
            "wps": json.dumps(WPS_JSON),
            "tags": json.dumps(TAGS_JSON),
            "alt": json.dumps(ALT_NAMES_JSON),
        },
    )
    await s.execute(
        text(
            "INSERT INTO futures_markets (id, event_id, source, external_id, name, "
            "category, mutually_exclusive, status) "
            "VALUES (:id, :eid, 'kalshi', 'KXWSOP-TEST-1', :name, "
            "'player_prop', true, 'open')"
        ),
        {"id": MARKET_ID, "eid": EVENT_ID, "name": FICTION_MARKET},
    )
    await s.execute(
        text(
            "INSERT INTO line_movement_analyses (event_id, analysis_type, movement_data) "
            "VALUES (:eid, 'win_probability', CAST(:md AS jsonb))"
        ),
        {"eid": EVENT_ID, "md": json.dumps(MOVEMENT_JSON)},
    )
    await s.execute(
        text(
            "INSERT INTO win_prob_snapshots (event_id, source, reading_count, game_state) "
            "VALUES (:eid, 'kalshi', 1, CAST(:gs AS jsonb))"
        ),
        {"eid": EVENT_ID, "gs": json.dumps(GAME_STATE_JSON)},
    )
    await s.execute(
        text(
            "INSERT INTO event_provider_anchors (event_id, source, source_id, id_kind, "
            "claim_context) "
            "VALUES (:eid, 'kalshi', 'KXWSOP-TEST-1', 'market_ticker', CAST(:cc AS jsonb))"
        ),
        {"eid": EVENT_ID, "cc": json.dumps(CLAIM_CONTEXT_JSON)},
    )
    await s.commit()


def _load(name, filename):
    """Load a `scripts/` module by path — they are scripts, not a package."""
    import importlib.util
    from pathlib import Path

    path = Path(__file__).resolve().parents[2] / "scripts" / filename
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _repair():
    return _load("r3026", "repair_3026_question_events.py")


def _restore():
    return _load("rst3026", "restore_3026_question_events.py")


async def _delete_the_fiction(s):
    """Drive the SHIPPED repair: classify, bank, delete. Returns the plan."""
    repair = _repair()
    plan = await repair.build_plan(s)

    # Assert the anchor of this whole file FIRST: if the seeded row is not the
    # one row the repair wants to delete, every assertion below is about
    # something else and would pass for the wrong reason.
    assert len(plan) == 1, f"expected exactly the seeded row, got {plan}"
    assert (plan[0]["action"], plan[0]["why"]) == ("delete", "no_fixture_named"), plan[0]
    assert plan[0]["id"] == EVENT_ID
    assert plan[0]["market_ids"] == [MARKET_ID], (
        "the seeded market was not recognised as the fiction, so the repair is "
        "about to hold this row instead of deleting it"
    )

    banked_events, banked_links = await repair.ensure_backup(s, plan)
    assert (banked_events, banked_links) == (1, 1)

    written = await repair.apply_plan(s, plan)
    assert written["deleted"] == 1, written
    assert written["markets_unlinked"] == 1, written
    assert written["lma_deleted"] == 1, written
    return plan


async def _scalar(s, sql, params=None):
    from sqlalchemy import text

    return (await s.execute(text(sql), params or {})).scalar()


@needs_postgres
async def test_backup_delete_restore_round_trips_every_banked_table(session):
    """The whole undo, end to end, on the real codec. CERT-932's named repair.

    This is the test the BLOCK asked for: it fails with
    `AttributeError: 'dict' object has no attribute 'encode'` against the
    untyped bind and passes against the typed one.
    """
    restore = _restore()

    await _delete_the_fiction(session)

    # Gone, and gone properly: the row, its LMA, and the market's link.
    assert await _scalar(session, "SELECT count(*) FROM events WHERE id = :i",
                         {"i": EVENT_ID}) == 0
    assert await _scalar(session, "SELECT count(*) FROM line_movement_analyses "
                                  "WHERE event_id = :i", {"i": EVENT_ID}) == 0
    assert await _scalar(session, "SELECT event_id FROM futures_markets WHERE id = :i",
                         {"i": MARKET_ID}) is None
    # The CASCADE children went with the row — which is what makes banking them
    # by name the difference between an undo and a partial one.
    assert await _scalar(session, "SELECT count(*) FROM win_prob_snapshots "
                                  "WHERE event_id = :i", {"i": EVENT_ID}) == 0
    assert await _scalar(session, "SELECT count(*) FROM event_provider_anchors "
                                  "WHERE event_id = :i", {"i": EVENT_ID}) == 0

    events_report = await restore.restore_events(session, apply=True)
    links_report = await restore.restore_links(session, apply=True)
    await session.commit()

    assert events_report["reinserted"] == 1, events_report
    # 1 LMA + 1 snapshot + 1 anchor. espn_snapshots and game_moments are banked
    # too but were not seeded, so they contribute nothing.
    assert events_report["children_reinserted"] == 3, events_report
    assert links_report["relinked"] == 1, links_report

    # The event is back, by its ORIGINAL id — every child FK points at it.
    from sqlalchemy import text

    row = (
        await session.execute(
            text(
                "SELECT home_team_name, away_team_name, status, sport_id, "
                "       win_probability_sources, event_tags, home_team_alt_names "
                "FROM events WHERE id = :i"
            ),
            {"i": EVENT_ID},
        )
    ).first()
    assert row is not None, "the event did not come back"
    assert row[0] == FICTION_HOME
    assert row[1] == FICTION_AWAY
    assert row[2] == "scheduled"
    assert row[3] == 1
    # The JSONB columns are the ones the defect destroyed. Compare CONTENT, not
    # presence: `jsonb_populate_record` reconstructing an empty object would
    # satisfy a NOT NULL check and lose the whole aggregate.
    assert row[4] == WPS_JSON
    assert row[5] == TAGS_JSON
    assert row[6] == ALT_NAMES_JSON

    lma = (
        await session.execute(
            text("SELECT analysis_type, movement_data FROM line_movement_analyses "
                 "WHERE event_id = :i"),
            {"i": EVENT_ID},
        )
    ).first()
    assert lma is not None, "line_movement_analyses did not come back"
    assert lma[0] == "win_probability"
    assert lma[1] == MOVEMENT_JSON

    snap = (
        await session.execute(
            text("SELECT source, reading_count, game_state FROM win_prob_snapshots "
                 "WHERE event_id = :i"),
            {"i": EVENT_ID},
        )
    ).first()
    assert snap is not None, "win_prob_snapshots did not come back"
    assert (snap[0], snap[1]) == ("kalshi", 1)
    assert snap[2] == GAME_STATE_JSON

    anchor = (
        await session.execute(
            text("SELECT source, source_id, id_kind, claim_context "
                 "FROM event_provider_anchors WHERE event_id = :i"),
            {"i": EVENT_ID},
        )
    ).first()
    assert anchor is not None, "event_provider_anchors did not come back"
    assert (anchor[0], anchor[1], anchor[2]) == ("kalshi", "KXWSOP-TEST-1", "market_ticker")
    assert anchor[3] == CLAIM_CONTEXT_JSON

    assert await _scalar(session, "SELECT event_id FROM futures_markets WHERE id = :i",
                         {"i": MARKET_ID}) == EVENT_ID


@needs_postgres
async def test_restore_is_idempotent_and_does_not_stomp_a_second_run(session):
    """A second `--apply` is a no-op, not a duplicate-key crash.

    D51's undo is a command a person runs when something looks wrong, which is
    exactly the state in which they run it twice.
    """
    restore = _restore()
    await _delete_the_fiction(session)

    first = await restore.restore_events(session, apply=True)
    await restore.restore_links(session, apply=True)
    await session.commit()
    assert first["reinserted"] == 1

    second = await restore.restore_events(session, apply=True)
    second_links = await restore.restore_links(session, apply=True)
    await session.commit()

    assert second["reinserted"] == 0, second
    assert second["already_present"] == 1, second
    assert second_links["relinked"] == 0, second_links
    assert second_links["diverged"] == 0, second_links

    assert await _scalar(session, "SELECT count(*) FROM events WHERE id = :i",
                         {"i": EVENT_ID}) == 1
    assert await _scalar(session, "SELECT count(*) FROM win_prob_snapshots "
                                  "WHERE event_id = :i", {"i": EVENT_ID}) == 1


@needs_postgres
async def test_an_untyped_row_bind_still_fails_so_the_type_is_what_holds_it_up(session):
    """THE RED ARM. Put the defect back and the restore must break.

    Without this, the two tests above would stay green if `_populate_insert`
    were replaced by the untyped `text()` it was written to remove — they
    exercise the fixed path but cannot attribute the pass to the fix. Here the
    typed bind is swapped out for the original statement and the restore is
    required to raise the exact error CERT-932 reproduced.
    """
    from sqlalchemy import text

    restore = _restore()
    await _delete_the_fiction(session)

    # Derived from the shipped statement rather than retyped, so the red arm
    # differs from the real path in EXACTLY one dimension — the bind's type. A
    # hand-copied SQL string would drift, and a red arm testing slightly
    # different SQL proves slightly the wrong thing.
    typed = restore._populate_insert

    def untyped(table, on_conflict_nothing):
        return text(typed(table, on_conflict_nothing).text)

    restore._populate_insert = untyped

    with pytest.raises(Exception) as excinfo:
        await restore.restore_events(session, apply=True)

    assert "encode" in str(excinfo.value), (
        f"expected the asyncpg jsonb codec to reject the raw dict, got "
        f"{type(excinfo.value).__name__}: {excinfo.value}. If this stopped "
        "raising, the codec changed and the two tests above no longer prove "
        "that typing the bind is what makes the restore work."
    )
