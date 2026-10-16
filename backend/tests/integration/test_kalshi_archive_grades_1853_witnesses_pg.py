"""#1853 — Root's and CERT-4149's executed counterexamples, kept VERBATIM as controls.

Root (2026-10-16, `artifacts/calibration-1853-receipt-20261015/ROOT-CF44-
{SAFETY,PREAPPLY}-WITNESS.py`) and the CERT-4149 reviewer (`test_review_4149_pg.py`)
each executed these against cf44b76e63 and watched them fail: apply re-planned
past its frozen set, restore erased a later writer, the backup was not the
actual before-image, and a stale marker survived undo/retry. The bodies below
are theirs, unedited; only the imports are explicit. The ownership contract in
`scripts/repair_1853_archive_grades.py` is what makes them pass.
"""

from __future__ import annotations

import json

from sqlalchemy import text

import tests.integration.test_kalshi_archive_grades_1853_pg as _rig
from tests.integration.test_kalshi_archive_grades_1853_pg import (  # noqa: F401
    CONTROLS,
    STORED,
    UNGRADED,
    _legs,
    _script,
    pytestmark,
)

#: The rig's real-PG fixture (the specimen's 30 legs, seeded and cleared).
session = _rig.session


# --- Root: ROOT-CF44-SAFETY-WITNESS.py + ROOT-CF44-PREAPPLY-WITNESS.py --------

async def test_root_apply_stays_within_approved_and_backed_up_ids(session):
    mod = _script()
    legs = mod.load_archive_legs()
    grades, _ = await mod.build_plan(session, legs)
    await session.rollback()
    approved = {g.outcome_id for g in grades}
    assert approved == UNGRADED and len(approved) == 22
    digest = mod.plan_digest(grades)
    assert await mod.backup(session, grades, digest) == 0
    await session.commit()
    backed = set((await session.execute(text(f"SELECT outcome_id FROM {mod.BACKUP_TABLE}"))).scalars().all())
    assert backed == approved
    # Another writer retracts a previously authoritative control after the
    # reviewed plan/backup, before the helper run() calls for this exact digest.
    raced = min(r["outcome_id"] for r in STORED["stored"]
                if r["resolution_source"] and r["is_winner"] is False)
    assert raced in CONTROLS and raced not in approved
    await session.execute(text("UPDATE futures_outcomes SET resolution_source=NULL, is_winner=NULL, last_updated=NOW() WHERE id=:id"), {"id": raced})
    await session.commit()
    stats = await mod.apply(session, legs, digest)
    await session.commit()
    written = set(stats["written_ids"])
    print("ROOT_APPLY_RACE", json.dumps({"approved": sorted(approved), "backed": sorted(backed), "written": sorted(written), "new_unbacked": sorted(written-backed), "raced_control": raced}))
    assert written <= approved and written <= backed, "apply wrote outside its approved/backed-up plan"


async def test_root_restore_preserves_a_later_same_verdict_writer(session):
    mod = _script()
    legs = mod.load_archive_legs()
    grades, _ = await mod.build_plan(session, legs)
    await session.rollback()
    digest = mod.plan_digest(grades)
    assert await mod.backup(session, grades, digest) == 0
    await session.commit()
    stats = await mod.apply(session, legs, digest)
    await session.commit()
    assert set(stats["written_ids"]) == UNGRADED
    raced = min(UNGRADED)
    # A live writer confirms the SAME verdict/source/price after this apply.
    # It is a new row version; this repair no longer owns that current grade.
    await session.execute(text("UPDATE futures_outcomes SET resolution_source='api_settlement', is_winner=false, current_probability=0.0, last_updated=NOW()+interval '1 minute' WHERE id=:id"), {"id": raced})
    await session.commit()
    touched = (await session.execute(text("SELECT last_updated FROM futures_outcomes WHERE id=:id"), {"id": raced})).scalar_one()
    await session.rollback()
    restored = await mod.restore(session)
    await session.commit()
    final = (await _legs(session))[raced]
    print("ROOT_RESTORE_RACE", json.dumps({"raced": raced, "later_version": str(touched), "restored_ids": restored, "raced_after_restore": final}))
    assert raced not in restored and final == ("api_settlement", False, 0.0), "restore erased a later writer's confirmed grade"

async def test_root_backup_is_the_actual_beforeimage_of_the_write(session):
    mod = _script()
    legs = mod.load_archive_legs()
    grades, _ = await mod.build_plan(session, legs)
    await session.rollback()
    digest = mod.plan_digest(grades)
    assert await mod.backup(session, grades, digest) == 0
    await session.commit()
    raced = min(UNGRADED)
    # Same approved ID remains ungraded, but a price writer changes its row
    # after the saved backup. A safe apply must refuse this drift or retain
    # the actual before-image; undo must never reinstall an older price.
    await session.execute(text("UPDATE futures_outcomes SET current_probability=0.61, last_updated=NOW()+interval '1 minute' WHERE id=:id"), {"id": raced})
    await session.commit()
    stats = await mod.apply(session, legs, digest)
    await session.commit()
    restored = await mod.restore(session)
    await session.commit()
    final = (await _legs(session))[raced]
    print("ROOT_BEFOREIMAGE_RACE", json.dumps({"raced": raced, "price_before_apply": 0.61, "written": raced in stats["written_ids"], "restored": raced in restored, "final": final}))
    assert final == (None, None, 0.61), "undo restored a stale backup over the actual pre-apply price"


# --- CERT-4149 reviewer: test_review_4149_pg.py -----------------------------

async def test_retry_after_undo_does_not_undo_live_grader(session):
    mod = _script()
    legs = mod.load_archive_legs()
    grades, _ = await mod.build_plan(session, legs)
    await session.rollback()
    digest = mod.plan_digest(grades)
    assert await mod.backup(session, grades, digest) == 0
    await session.commit()
    await mod.apply(session, legs, digest)
    await session.commit()
    assert len(await mod.restore(session)) == 22
    await session.commit()
    # Operator retries the same reviewed repair after its successful undo.
    retry, _ = await mod.build_plan(session, legs)
    await session.rollback()
    assert mod.plan_digest(retry) == digest and len(retry) == 22
    assert await mod.backup(session, retry, digest) == 0
    await session.commit()
    raced = min(UNGRADED)
    await session.execute(text("UPDATE futures_outcomes SET resolution_source='api_settlement', is_winner=false, current_probability=0.0, last_updated=NOW() WHERE id=:id"), {'id':raced})
    await session.commit()
    stats = await mod.apply(session, legs, digest)
    await session.commit()
    assert raced not in stats['written_ids'] and len(stats['written_ids']) == 21
    restored = await mod.restore(session)
    await session.commit()
    assert raced not in restored, f'undo reverted the live grader: {raced}; restored={restored}'

async def test_later_same_venue_grade_version_is_not_undone(session):
    mod = _script()
    legs = mod.load_archive_legs()
    grades, _ = await mod.build_plan(session, legs)
    await session.rollback()
    digest = mod.plan_digest(grades)
    assert await mod.backup(session, grades, digest) == 0
    await session.commit()
    await mod.apply(session, legs, digest)
    await session.commit()
    touched = min(UNGRADED)
    await session.execute(text("UPDATE futures_outcomes SET last_updated=NOW()+interval '1 second', current_american_odds=-123 WHERE id=:id"), {'id':touched})
    await session.commit()
    restored = await mod.restore(session)
    await session.commit()
    assert touched not in restored, 'undo overwrote a later row version'
