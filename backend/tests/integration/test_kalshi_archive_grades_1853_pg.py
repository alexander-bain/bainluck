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


async def _plan_and_backup(session):
    mod = _script()
    legs = mod.load_archive_legs()
    grades, refused = await mod.build_plan(session, legs)
    await session.rollback()
    digest = mod.plan_digest(grades)
    assert await mod.backup(session, grades, digest) == 0, "every planned leg has its undo row"
    await session.commit()
    return mod, legs, grades, refused, digest


async def _apply(session, mod, legs, digest):
    out = await mod.apply(session, legs, digest)
    await session.commit()
    return out


async def _restore(session, mod):
    out = await mod.restore_report(session)
    await session.commit()
    return out


async def test_plan_backup_apply_and_undo_on_the_specimen(session):
    before = await _legs(session)
    mod, legs, grades, refused, digest = await _plan_and_backup(session)
    assert {g.outcome_id for g in grades} == UNGRADED and len(grades) == mod.EXPECTED_PLAN
    assert set(refused["already_graded"]) == CONTROLS

    out = await _apply(session, mod, legs, digest)
    assert sorted(out["written_ids"]) == sorted(UNGRADED)
    after = await _legs(session)
    for oid in UNGRADED:
        assert after[oid] == ("api_settlement", False, 0.0), oid
    assert {k: after[k] for k in CONTROLS} == {k: before[k] for k in CONTROLS}

    undo = await _restore(session, mod)
    assert sorted(undo["restored"]) == sorted(UNGRADED)
    assert undo["preserved_changed_since_apply"] == []
    assert await _legs(session) == before, "the undo puts every row back exactly"


async def test_a_second_apply_of_the_same_plan_writes_nothing(session):
    mod, legs, grades, _, digest = await _plan_and_backup(session)
    first = await _apply(session, mod, legs, digest)
    second = await _apply(session, mod, legs, digest)
    assert len(first["written_ids"]) == 22
    assert second["written_ids"] == [] and second["skipped_changed_since_backup"] == []
    regrades, _ = await mod.build_plan(session, legs)
    await session.rollback()
    assert regrades == [], "once applied, the plan is empty — a re-run cannot re-plan"


async def test_restore_without_an_apply_refuses(session):
    mod = _script()
    with pytest.raises(mod.Refused):
        await mod.restore(session)


# --- the ownership contract: Root's three counterexamples and CERT-4149's ---


async def test_root_apply_stays_within_the_frozen_approved_set(session):
    """A control retracted to NULL after the backup is NOT written: apply reads
    the frozen set, it never re-plans."""
    mod, legs, grades, _, digest = await _plan_and_backup(session)
    raced = min(r["outcome_id"] for r in STORED["stored"]
                if r["resolution_source"] and r["is_winner"] is False)
    await session.execute(
        text("UPDATE futures_outcomes SET resolution_source=NULL, is_winner=NULL, "
             "last_updated=NOW() WHERE id=:id"), {"id": raced})
    await session.commit()
    out = await _apply(session, mod, legs, digest)
    assert set(out["written_ids"]) == UNGRADED and raced not in out["written_ids"]
    assert (await _legs(session))[raced][:2] == (None, None)


async def test_root_restore_preserves_a_later_same_verdict_writer(session):
    mod, legs, grades, _, digest = await _plan_and_backup(session)
    await _apply(session, mod, legs, digest)
    raced = min(UNGRADED)
    await session.execute(
        text("UPDATE futures_outcomes SET resolution_source='api_settlement', is_winner=false, "
             "current_probability=0.0, last_updated=NOW()+interval '1 minute' WHERE id=:id"),
        {"id": raced})
    await session.commit()
    undo = await _restore(session, mod)
    assert raced not in undo["restored"] and undo["preserved_changed_since_apply"] == [raced]
    assert (await _legs(session))[raced] == ("api_settlement", False, 0.0)
    assert len(undo["restored"]) == 21


async def test_root_a_price_moved_after_backup_is_never_written_over(session):
    """0.47 -> 0.61 between backup and apply: the leg is skipped, not written,
    so no undo can ever reinstall the stale 0.47."""
    mod, legs, grades, _, digest = await _plan_and_backup(session)
    moved = min(UNGRADED)
    await session.execute(
        text("UPDATE futures_outcomes SET current_probability=0.61 WHERE id=:id"), {"id": moved})
    await session.commit()
    out = await _apply(session, mod, legs, digest)
    assert out["skipped_changed_since_backup"] == [moved] and len(out["written_ids"]) == 21
    assert (await _legs(session))[moved] == (None, None, 0.61)
    await _restore(session, mod)
    assert (await _legs(session))[moved] == (None, None, 0.61), "the writer's 0.61 stands"


async def test_cert4149_apply_undo_later_grader_retry_undo(session):
    """apply 22 -> undo 22 -> a grader writes one leg -> retry writes 21 -> undo.
    The second undo must not touch the grader's leg: the first undo closed its
    marker, and the retry never re-owned it."""
    mod, legs, grades, _, digest = await _plan_and_backup(session)
    before = await _legs(session)
    await _apply(session, mod, legs, digest)
    first_undo = await _restore(session, mod)
    assert len(first_undo["restored"]) == 22
    graded = min(UNGRADED)
    await session.execute(
        text("UPDATE futures_outcomes SET resolution_source='api_settlement', is_winner=false, "
             "current_probability=0.0, last_updated=NOW() WHERE id=:id"), {"id": graded})
    await session.commit()
    retry = await _apply(session, mod, legs, digest)
    assert graded not in retry["written_ids"] and len(retry["written_ids"]) == 21
    second_undo = await _restore(session, mod)
    assert graded not in second_undo["restored"] and len(second_undo["restored"]) == 21
    final = await _legs(session)
    assert final[graded] == ("api_settlement", False, 0.0), "the grader's result stands"
    for oid in UNGRADED - {graded}:
        assert final[oid] == before[oid]


async def test_cert4149_a_later_odds_update_is_not_undone(session):
    """Any column counts, not only grade/source/price: a later odds write makes
    the row no longer this repair's to undo."""
    mod, legs, grades, _, digest = await _plan_and_backup(session)
    await _apply(session, mod, legs, digest)
    touched = min(UNGRADED)
    await session.execute(
        text("UPDATE futures_outcomes SET current_american_odds=-150 WHERE id=:id"), {"id": touched})
    await session.commit()
    undo = await _restore(session, mod)
    assert undo["preserved_changed_since_apply"] == [touched]
    row = (await session.execute(
        text("SELECT current_american_odds, resolution_source FROM futures_outcomes WHERE id=:id"),
        {"id": touched})).one()
    await session.rollback()
    assert tuple(row) == (-150, "api_settlement")
    # And a lost row is closed: a second undo cannot reach it either.
    assert (await _restore(session, mod))["restored"] == []
    assert await mod.restore(session) == [], "the list form agrees"


async def test_apply_writes_only_its_own_digests_frozen_rows(session):
    """A backup row frozen under ANOTHER digest is not this apply's to write,
    even when it is ungraded and its before-image still matches."""
    mod, legs, grades, _, digest = await _plan_and_backup(session)
    stranger = 229599999
    await session.execute(
        text("INSERT INTO futures_outcomes (id, market_id, external_id, name, "
             "current_probability, is_winner, resolution_source, volume) VALUES "
             "(:id, :m, 'KXUECLSCORE-26JUL30LEVIFK-ZZZ', 'zzz', 0.3, NULL, NULL, 10)"),
        {"id": stranger, "m": MARKET_ID},
    )
    await session.commit()
    # Frozen through the script's own backup, under another plan's digest —
    # bound, like every planned leg, to the version it was approved on.
    image = (await session.execute(
        text("SELECT to_jsonb(fo)::text FROM futures_outcomes fo WHERE id=:id"),
        {"id": stranger})).scalar_one()
    await session.rollback()
    other = [mod.ApprovedGrade(stranger, "KXUECLSCORE-26JUL30LEVIFK-ZZZ", False,
                               "finalized", "no", image)]
    assert await mod.backup(session, other, "another-plan") == 0
    await session.commit()
    out = await _apply(session, mod, legs, digest)
    assert stranger not in out["written_ids"] and len(out["written_ids"]) == 22
    assert (await _legs(session))[stranger] == (None, None, 0.3)


# --- Root 004: the PLAN binds each leg's approved version -------------------
#
# c6a447's window: build_plan returned the 22, a price writer moved one leg
# 0.47 -> 0.61 while it stayed NULL/NULL, and backup adopted the 0.61 row as its
# before-image; apply then wrote over a version nobody reviewed.

PRICE_RACE = min(UNGRADED)


async def _move_price(session, oid, price=0.61):
    await session.execute(
        text("UPDATE futures_outcomes SET current_probability=:p WHERE id=:id"),
        {"p": price, "id": oid})
    await session.commit()


async def _backup_rows(session, mod, digest):
    if not (await session.execute(text(mod.SQL["bak_exists"]))).scalar_one():
        await session.rollback()
        return []
    ids = (await session.execute(
        text(f"SELECT outcome_id FROM {mod.BACKUP_TABLE} WHERE plan_digest=:d ORDER BY 1"),
        {"d": digest})).scalars().all()
    await session.rollback()
    return list(ids)


async def test_a_price_writer_between_plan_and_backup_is_refused_never_adopted(session):
    """Plan 22; an independent writer moves one leg's price 0.47 -> 0.61 while
    it is still NULL/NULL; then backup under the reviewed digest. The leg is no
    longer the version the plan was approved on: backup names it and freezes
    nothing, and the writer's 0.61 stands ungraded."""
    mod = _script()
    legs = mod.load_archive_legs()
    grades, _ = await mod.build_plan(session, legs)
    await session.rollback()
    digest = mod.plan_digest(grades)
    assert len(grades) == 22 and PRICE_RACE in {g.outcome_id for g in grades}
    await _move_price(session, PRICE_RACE)
    with pytest.raises(mod.Refused, match=str(PRICE_RACE)):
        await mod.backup(session, grades, digest)
    await session.rollback()
    assert await _backup_rows(session, mod, digest) == [], "nothing frozen under the old digest"
    assert (await _legs(session))[PRICE_RACE] == (None, None, 0.61)
    # And the reviewed --digest is not this row's: a re-plan names another one.
    regrades, _ = await mod.build_plan(session, legs)
    await session.rollback()
    assert mod.plan_digest(regrades) != digest


async def test_replanning_a_moved_row_changes_the_approval_digest(session):
    """Same ids, same verdicts, one price moved: a different approval digest.
    Re-reviewed at the new digest, the leg is written and its undo puts back
    the 0.61 it was approved on."""
    mod = _script()
    legs = mod.load_archive_legs()
    grades, _ = await mod.build_plan(session, legs)
    await session.rollback()
    digest = mod.plan_digest(grades)
    await _move_price(session, PRICE_RACE)
    regrades, _ = await mod.build_plan(session, legs)
    await session.rollback()
    redigest = mod.plan_digest(regrades)
    assert redigest != digest
    assert [(g.outcome_id, g.is_winner) for g in regrades] == [(g.outcome_id, g.is_winner) for g in grades]
    assert await mod.backup(session, regrades, redigest) == 0
    await session.commit()
    out = await _apply(session, mod, legs, redigest)
    assert sorted(out["written_ids"]) == sorted(UNGRADED)
    await _restore(session, mod)
    assert (await _legs(session))[PRICE_RACE] == (None, None, 0.61)


async def test_a_retry_backup_rechecks_the_row_even_when_its_frozen_row_exists(session):
    """apply -> undo -> re-plan (same digest) -> price writer -> backup. The
    frozen row already exists under this digest, so presence proves nothing:
    backup compares the CURRENT row to the approved version and refuses."""
    mod, legs, grades, _, digest = await _plan_and_backup(session)
    await _apply(session, mod, legs, digest)
    assert len((await _restore(session, mod))["restored"]) == 22
    retry, _ = await mod.build_plan(session, legs)
    await session.rollback()
    assert mod.plan_digest(retry) == digest
    await _move_price(session, PRICE_RACE)
    with pytest.raises(mod.Refused, match=str(PRICE_RACE)):
        await mod.backup(session, retry, digest)
    await session.rollback()
    assert (await _legs(session))[PRICE_RACE] == (None, None, 0.61)


async def test_without_drift_the_cycle_round_trips_every_changed_nullable_field(session):
    """The positive control: no writer between plan and backup. Every column
    the apply changes (grade, source, price, odds, price stamp, last_updated)
    is seeded both NULL and non-NULL; plan/backup/apply/undo returns each leg
    to EXACTLY its approved version, and a re-plan names the same digest."""
    ids = sorted(UNGRADED)
    full, empty = ids[0::2], ids[1::2]
    await session.execute(
        text("UPDATE futures_outcomes SET current_probability=0.47, current_american_odds=113, "
             "price_changed_at='2026-07-30T18:04:05.123456+00', "
             "last_updated='2026-07-30T19:00:00.5+00' WHERE id = ANY(CAST(:ids AS bigint[]))"),
        {"ids": full})
    await session.execute(
        text("UPDATE futures_outcomes SET current_probability=NULL, current_american_odds=NULL, "
             "price_changed_at=NULL, last_updated='2026-07-29T00:00:00+00' WHERE id = ANY(CAST(:ids AS bigint[]))"),
        {"ids": empty})
    await session.commit()
    mod = _script()
    legs = mod.load_archive_legs()
    grades, _ = await mod.build_plan(session, legs)
    await session.rollback()
    digest = mod.plan_digest(grades)
    approved = {g.outcome_id: g.approved_before for g in grades}
    assert sorted(approved) == ids
    assert await mod.backup(session, grades, digest) == 0
    await session.commit()
    frozen_as_approved = (await session.execute(
        text(f"SELECT count(*) FROM {mod.BACKUP_TABLE} b JOIN unnest(CAST(:ids AS bigint[]), "
             "CAST(:imgs AS text[])) a(id, img) ON a.id = b.outcome_id "
             "WHERE b.plan_digest = :d AND b.before_row = CAST(a.img AS jsonb)"),
        {"ids": list(approved), "imgs": list(approved.values()), "d": digest})).scalar_one()
    await session.rollback()
    assert frozen_as_approved == 22, "each backup row IS its approved version"
    out = await _apply(session, mod, legs, digest)
    assert sorted(out["written_ids"]) == ids
    changed = await _legs(session)
    assert all(changed[i][:2] == ("api_settlement", False) for i in ids)
    undo = await _restore(session, mod)
    assert sorted(undo["restored"]) == ids
    same = (await session.execute(
        text("SELECT a.id FROM unnest(CAST(:ids AS bigint[]), CAST(:imgs AS text[])) a(id, img) "
             "JOIN futures_outcomes fo ON fo.id = a.id WHERE to_jsonb(fo) = CAST(a.img AS jsonb) "
             "ORDER BY 1"),
        {"ids": list(approved), "imgs": list(approved.values())})).scalars().all()
    await session.rollback()
    assert list(same) == ids, "every changed nullable field is back to its approved value"
    regrades, _ = await mod.build_plan(session, legs)
    await session.rollback()
    assert mod.plan_digest(regrades) == digest


# --- the read-only status packet: how an UNKNOWN receipt is resolved -------
#
# Each phase commits as ONE transaction with its markers, so after a COMMIT
# whose acknowledgement was lost, ``--status`` answers whether it landed. Here
# every COMMIT is acknowledged; the status read after it is what an operator
# would read after the same COMMIT went unacknowledged.


async def _status(session, mod):
    before = await _legs(session)
    out = await mod.status_report(session)
    await session.rollback()
    assert await _legs(session) == before, "status writes nothing"
    return out


async def test_status_before_any_backup_says_no_backup_committed(session):
    mod = _script()
    assert await _status(session, mod) == {"backup_table": "absent", "digests": {}}
    exists = (await session.execute(text(mod.SQL["bak_exists"]))).scalar_one()
    await session.rollback()
    assert not exists, "status creates no table"


async def test_status_resolves_each_phase_of_the_cycle(session):
    mod, legs, grades, _, digest = await _plan_and_backup(session)
    backed = (await _status(session, mod))["digests"][digest]
    assert (backed["frozen"], backed["applied"], backed["holds_before"]) == (22, 0, 22)
    assert backed["holds_after"] == 0 and backed["restored"] == 0
    assert sorted(r["outcome_id"] for r in backed["rows"]) == sorted(UNGRADED)

    await _apply(session, mod, legs, digest)
    applied = (await _status(session, mod))["digests"][digest]
    assert (applied["applied"], applied["holds_after"], applied["holds_before"]) == (22, 22, 0)
    assert all(r["applied_at"] is not None for r in applied["rows"])

    await _restore(session, mod)
    restored = (await _status(session, mod))["digests"][digest]
    assert (restored["applied"], restored["restored"], restored["holds_before"]) == (0, 22, 22)
    assert restored["ownership_lost"] == 0


async def test_status_names_a_row_a_later_writer_moved(session):
    mod, legs, grades, _, digest = await _plan_and_backup(session)
    await _apply(session, mod, legs, digest)
    moved = sorted(UNGRADED)[0]
    await session.execute(
        text("UPDATE futures_outcomes SET last_updated = NOW() + interval '1 hour' WHERE id = :i"),
        {"i": moved},
    )
    await session.commit()
    d = (await _status(session, mod))["digests"][digest]
    assert (d["applied"], d["holds_after"]) == (22, 21)
    row = next(r for r in d["rows"] if r["outcome_id"] == moved)
    assert row["applied"] and not row["holds_after"] and row["row_exists"]


# --- CERT-4237's follow-up: a lost acknowledgement, landed or not ----------
#
# Each phase runs through the operator's own ``Progress`` phase and COMMIT
# boundary on a real transaction; only the COMMIT's acknowledgement is lost —
# after a real COMMIT (landed) or before one is sent (not landed, the rollback
# discards it). Both print the same UNKNOWN receipt, and the real markers the
# status packet reads tell them apart. Coverage limit: this injects the failure
# around real SQL; it is not an end-to-end network loss through the session
# wrapper (the wrapper's half is pinned in ``tests/test_repair_1853_commit_ack.py``).


class _LostAck:
    def __init__(self, session, landed):
        self.session, self.landed = session, landed

    async def commit(self):
        if self.landed:
            await self.session.commit()
        raise ConnectionError("acknowledgement lost")


@pytest.mark.parametrize("phase", ["backup", "apply", "restore"])
@pytest.mark.parametrize("landed", [False, True], ids=["not-landed", "landed"])
async def test_status_tells_a_landed_unknown_from_one_that_never_landed(
    session, phase, landed, capsys
):
    mod = _script()
    legs = mod.load_archive_legs()
    grades, _ = await mod.build_plan(session, legs)
    await session.rollback()
    digest = mod.plan_digest(grades)
    if phase != "backup":
        assert await mod.backup(session, grades, digest) == 0
        await session.commit()
    if phase == "restore":
        await _apply(session, mod, legs, digest)
    capsys.readouterr()

    progress = mod.Progress()
    progress.mode = phase
    progress.out["plan_digest"] = digest
    with pytest.raises(ConnectionError) as caught:
        with progress.phase(phase):
            if phase == "backup":
                assert await mod.backup(session, grades, digest) == 0
            elif phase == "apply":
                progress.out["applied"] = await mod.apply(session, legs, digest)
            else:
                progress.out.update(await mod.restore_report(session))
            await progress.commit(_LostAck(session, landed), phase)
    await session.rollback()  # what the wrapper's exception exit does
    assert mod._ended_abnormally(progress, caught.value) == 3
    receipt = json.loads(capsys.readouterr().out)
    assert receipt["outcome"] == "UNKNOWN" and receipt["phases"] == {phase: "UNKNOWN"}
    assert "undo" not in receipt and receipt["readback"] == mod.STATUS_COMMAND

    status = await _status(session, mod)
    if phase == "backup" and not landed:
        assert status == {"backup_table": "absent", "digests": {}}
        return
    d = status["digests"][digest]
    assert d["frozen"] == 22
    if phase == "backup":
        assert (d["applied"], d["holds_before"]) == (0, 22)
    elif phase == "apply":
        assert (d["applied"], d["holds_after"]) == ((22, 22) if landed else (0, 0))
    else:
        assert (d["restored"], d["applied"]) == ((22, 0) if landed else (0, 22))


async def test_status_runs_under_a_server_enforced_read_only_transaction(session):
    from sqlalchemy.exc import DBAPIError

    mod, legs, grades, _, digest = await _plan_and_backup(session)
    await session.execute(text("SET TRANSACTION READ ONLY"))
    assert (await session.execute(text("SHOW transaction_read_only"))).scalar_one() == "on"
    d = (await mod.status_report(session))["digests"][digest]
    assert d["frozen"] == 22 and d["holds_before"] == 22
    # The control: the same transaction really refuses a write, so the read
    # above passed because it writes nothing, not because nothing was enforced.
    with pytest.raises(DBAPIError, match="read-only transaction"):
        await session.execute(
            text("UPDATE futures_outcomes SET volume = volume WHERE market_id = :m"),
            {"m": MARKET_ID},
        )
    await session.rollback()
