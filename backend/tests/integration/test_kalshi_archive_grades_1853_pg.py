"""#1853 — the attended archive-grade repair, on a real Postgres: plan, backup, apply, undo.

PILLAR: TRUTH. SHIP: a settled Kalshi question gets its venue-backed result
instead of remaining ungraded.

The specimen's 30 stored legs (22 never graded, 8 ``api_settlement``) are seeded
as read on 2026-10-15 and the repair runs against the RETAINED archive bytes.
What only Postgres can say: the backup DDL and its exactness check, the CAS on
"still ungraded", the settled price the write carries, and an undo that puts back
only what the apply wrote — not a leg somebody graded afterwards, and never one of
the 8 controls.

Opt-in on ``SEARCH_TEST_DATABASE_URL`` and NAMED IN ``ci.yml``.
"""

from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path

import pytest
from sqlalchemy import text

DB_URL = os.environ.get("SEARCH_TEST_DATABASE_URL")

pytestmark = [
    pytest.mark.asyncio,
    pytest.mark.skipif(
        not DB_URL,
        reason="set SEARCH_TEST_DATABASE_URL to run the real-Postgres #1853 archive-grade repair",
    ),
]

ROOT = Path(__file__).resolve().parents[2]
STORED = json.loads((ROOT / "tests" / "fixtures" / "kalshi_archive_1853_stored.json").read_text())
MARKET_ID = STORED["market_id"]


def _script():
    spec = importlib.util.spec_from_file_location(
        "repair_1853_archive_grades", ROOT / "scripts" / "repair_1853_archive_grades.py"
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


async def _clear(s):
    mod = _script()
    await s.execute(text(f"DROP TABLE IF EXISTS {mod.BACKUP_TABLE}"))
    await s.execute(text("DELETE FROM futures_outcomes WHERE market_id = :m"), {"m": MARKET_ID})
    await s.execute(text("DELETE FROM futures_markets WHERE id = :m"), {"m": MARKET_ID})


@pytest.fixture
async def session():
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    from app.models.models import Base

    engine = create_async_engine(DB_URL)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    Session = async_sessionmaker(engine, expire_on_commit=False)
    async with Session() as s:
        await _clear(s)
        await s.execute(
            text(
                "INSERT INTO futures_markets (id, external_id, name, source, status, "
                "category, mutually_exclusive, market_type, llm_sport_category, volume) "
                "VALUES (:id, :xid, 'Levadia vs IFK Goteborg - correct score', 'kalshi', "
                "'resolved', 'soccer', true, 'field', 'soccer', 100)"
            ),
            {"id": MARKET_ID, "xid": STORED["event_ticker"]},
        )
        for r in STORED["stored"]:
            await s.execute(
                text(
                    "INSERT INTO futures_outcomes (id, market_id, external_id, name, "
                    "current_probability, is_winner, resolution_source, volume) VALUES "
                    "(:id, :m, :xid, :xid, :cp, :win, :src, 10)"
                ),
                {
                    "id": r["outcome_id"], "m": MARKET_ID, "xid": r["external_id"],
                    "cp": 0.47 if r["resolution_source"] is None else (1.0 if r["is_winner"] else 0.0),
                    "win": r["is_winner"], "src": r["resolution_source"],
                },
            )
        await s.commit()
        yield s
        await s.rollback()
        await _clear(s)
        await s.commit()
    await engine.dispose()


async def _legs(s):
    rows = (await s.execute(
        text("SELECT id, resolution_source, is_winner, current_probability "
             "FROM futures_outcomes WHERE market_id = :m ORDER BY id"),
        {"m": MARKET_ID},
    )).all()
    await s.rollback()
    return {r[0]: (r[1], r[2], None if r[3] is None else float(r[3])) for r in rows}


UNGRADED = {r["outcome_id"] for r in STORED["stored"] if r["resolution_source"] is None}
CONTROLS = {r["outcome_id"] for r in STORED["stored"] if r["resolution_source"]}


async def test_plan_backup_apply_and_undo_on_the_specimen(session):
    mod = _script()
    legs = mod.load_archive_legs()
    before = await _legs(session)
    controls_before = {k: before[k] for k in CONTROLS}

    grades, refused = await mod.build_plan(session, legs)
    await session.rollback()
    assert {g.outcome_id for g in grades} == UNGRADED and len(grades) == mod.EXPECTED_PLAN
    assert set(refused["already_graded"]) == CONTROLS
    digest = mod.plan_digest(grades)

    assert await mod.backup(session, grades, digest) == 0, "every planned leg has its undo row"
    await session.commit()
    stats = await mod.apply(session, legs, digest)
    await session.commit()
    assert sorted(stats["written_ids"]) == sorted(UNGRADED)

    after = await _legs(session)
    for oid in UNGRADED:
        assert after[oid] == ("api_settlement", False, 0.0), oid
    assert {k: after[k] for k in CONTROLS} == controls_before, "the 8 controls never move"

    # Someone grades one leg differently after the apply: the undo must not revert it.
    touched = min(UNGRADED)
    await session.execute(
        text("UPDATE futures_outcomes SET resolution_source = 'game_score', is_winner = true, "
             "current_probability = 1.0 WHERE id = :id"),
        {"id": touched},
    )
    await session.commit()

    restored = await mod.restore(session)
    await session.commit()
    assert sorted(restored) == sorted(UNGRADED - {touched})
    final = await _legs(session)
    for oid in UNGRADED - {touched}:
        assert final[oid] == (None, None, 0.47), oid
    assert final[touched] == ("game_score", True, 1.0)
    assert {k: final[k] for k in CONTROLS} == controls_before


async def test_a_second_apply_of_the_same_plan_writes_nothing(session):
    mod = _script()
    legs = mod.load_archive_legs()
    grades, _ = await mod.build_plan(session, legs)
    await session.rollback()
    digest = mod.plan_digest(grades)
    assert await mod.backup(session, grades, digest) == 0
    await session.commit()
    first = await mod.apply(session, legs, digest)
    await session.commit()
    second = await mod.apply(session, legs, digest)
    await session.commit()
    assert len(first["written_ids"]) == 22
    assert second["written_ids"] == [], "the CAS refuses a leg that is no longer ungraded"
    regrades, _ = await mod.build_plan(session, legs)
    await session.rollback()
    assert regrades == [], "once applied, the plan is empty — a re-run cannot re-plan"


async def test_restore_without_an_apply_refuses(session):
    mod = _script()
    with pytest.raises(mod.Refused):
        await mod.restore(session)


async def test_a_leg_the_live_grader_wrote_first_is_never_undone(session):
    """The live arm grades one planned leg between backup and apply — the SAME
    verdict and source the apply would have written. The apply's CAS skips it,
    so the undo must skip it too: it was never this repair's write."""
    mod = _script()
    legs = mod.load_archive_legs()
    grades, _ = await mod.build_plan(session, legs)
    await session.rollback()
    digest = mod.plan_digest(grades)
    assert await mod.backup(session, grades, digest) == 0
    await session.commit()
    raced = min(UNGRADED)
    await session.execute(
        text("UPDATE futures_outcomes SET resolution_source = 'api_settlement', "
             "is_winner = false, current_probability = 0.0 WHERE id = :id"),
        {"id": raced},
    )
    await session.commit()
    stats = await mod.apply(session, legs, digest)
    await session.commit()
    assert raced not in stats["written_ids"] and len(stats["written_ids"]) == 21
    restored = await mod.restore(session)
    await session.commit()
    assert raced not in restored and len(restored) == 21
    assert (await _legs(session))[raced] == ("api_settlement", False, 0.0)
