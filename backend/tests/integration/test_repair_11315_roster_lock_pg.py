"""#11315 — the exact-market grade's roster locks, against REAL Postgres row locks.

CERT-4252 blocked ``e89215945d``: the apply locked only the market ``FOR SHARE`` and
CAS'd only the rows it writes, so a concurrent writer could crown an absent player,
clear an already-graded winner, or insert a crowned outcome, and the repair still
committed (two winners, or none). The fake-session tests show the in-transaction
roster check refuses such a move; a fake cannot show that the LOCKS keep a writer
out, because a fake has no locks. This file runs the script's own ``run()`` on a
real ``AsyncSession`` and has a second connection attempt each write at the worst
instant.

Every case runs two arms:

* ``fixed`` — the source as written (market ``FOR UPDATE``, roster ``FOR SHARE``);
* ``e892`` — the same source with e892's lock clauses put back (market
  ``FOR SHARE``, roster unlocked). This is the strawman: if a case passes on both
  arms it proves nothing about the locks.

The writer uses ``lock_timeout = 300ms``: blocked means it raised 55P03
(``lock_not_available``) while the repair's transaction was open. Data is
CONSTRUCTED (three outcomes, a two-row board) under the pinned ids; it makes no
production claim. Each case owns a random schema on the disposable database.
"""

from __future__ import annotations

import importlib
import importlib.util
import os
import pathlib
from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.models.models import FuturesMarket, FuturesOutcome
from app.services.database import Base

DB_URL = os.environ.get("SEARCH_TEST_DATABASE_URL")
pytestmark = [
    pytest.mark.asyncio,
    pytest.mark.skipif(not DB_URL, reason="requires disposable SEARCH_TEST_DATABASE_URL"),
]

SCRIPT = (
    pathlib.Path(__file__).resolve().parents[2]
    / "scripts"
    / "repair_11315_datagolf_exact_market_grade.py"
)
PLACEMENT = importlib.import_module("app.tasks.backfill_winners")._datagolf_check_placement

MARKET_ID = 64266833
BRENNAN = 241857512  # pinned winner, dg_29197, board position 1
LOSER = 241857511  # on the board at position 2
ABSENT = 241857510  # not on the board: unknown_absent, never written
JOINER = 241857599  # inserted mid-run
STAMP = datetime(2026, 10, 11, 22, 8, 55, tzinfo=timezone.utc)
LOCK_NOT_AVAILABLE = "55P03"


def _load():
    spec = importlib.util.spec_from_file_location("repair_11315_pg", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(params=["fixed", "e892"])
def arm(request):
    repair = _load()
    if request.param == "e892":
        repair._MARKET_LOCK = " FOR SHARE"
        repair._ROSTER_LOCK = ""
    return SimpleNamespace(name=request.param, repair=repair)


@pytest.fixture
async def rig():
    schema = "roster11315_" + uuid4().hex
    admin = create_async_engine(DB_URL)
    async with admin.begin() as conn:
        await conn.execute(text(f'CREATE SCHEMA "{schema}"'))
    engine = create_async_engine(DB_URL, connect_args={"server_settings": {"search_path": schema}})
    maker = async_sessionmaker(engine, expire_on_commit=False)
    wanted = [
        Base.metadata.tables[name]
        for name in ("sports", "teams", "venues", "events", "futures_markets", "futures_outcomes")
    ]
    try:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all, tables=wanted)
        yield SimpleNamespace(engine=engine, maker=maker)
    finally:
        await engine.dispose()
        async with admin.begin() as conn:
            await conn.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        await admin.dispose()


async def seed(rig, *, brennan_already=False):
    board = [
        {"dg_id": 29197, "position": "1", "thru": "18", "current_round": 4},
        {"dg_id": 111, "position": "2", "thru": "18", "current_round": 4},
    ]
    async with rig.maker() as s:
        s.add(
            FuturesMarket(
                id=MARKET_ID,
                source="datagolf",
                external_id="datagolf:pga:527:win",
                name="Baycurrent Classic winner",
                market_type="win",
                status="resolved",
                resolution_date=datetime(2026, 10, 11, 23, 0, tzinfo=timezone.utc),
                market_metadata={"datagolf_event_id": "527", "tour": "pga", "leaderboard": board},
            )
        )
        await s.flush()
        won = (True, "leaderboard") if brennan_already else (None, None)
        for oid, ext, grade in (
            (BRENNAN, "dg_29197", won),
            (LOSER, "dg_111", (None, None)),
            (ABSENT, "dg_9000001", (None, None)),
        ):
            s.add(
                FuturesOutcome(
                    id=oid,
                    market_id=MARKET_ID,
                    external_id=ext,
                    name=ext,
                    is_winner=grade[0],
                    resolution_source=grade[1],
                    last_updated=STAMP,
                )
            )
        await s.flush()
        # The ORM fills `is_winner`'s default (FALSE) for a None; the retained
        # ungraded rows read (NULL, NULL), so state that explicitly.
        await s.execute(
            text("UPDATE futures_outcomes SET is_winner = NULL WHERE resolution_source IS NULL")
        )
        await s.commit()


async def winners(rig):
    async with rig.engine.connect() as conn:
        rows = await conn.execute(
            text(
                "SELECT id FROM futures_outcomes WHERE market_id = :m AND is_winner IS TRUE "
                "ORDER BY id"
            ),
            {"m": MARKET_ID},
        )
        return [r.id for r in rows]


async def grades(rig):
    async with rig.engine.connect() as conn:
        rows = await conn.execute(
            text("SELECT id, is_winner, resolution_source FROM futures_outcomes ORDER BY id")
        )
        return {r.id: (r.is_winner, r.resolution_source) for r in rows}


def _sqlstate(exc: DBAPIError):
    return getattr(exc.orig, "sqlstate", None) or getattr(exc.orig, "pgcode", None)


CROWN_ABSENT = (
    "UPDATE futures_outcomes SET is_winner = TRUE, resolution_source = 'leaderboard' "
    "WHERE id = :o",
    {"o": ABSENT},
)
CLEAR_BRENNAN = (
    "UPDATE futures_outcomes SET is_winner = NULL, resolution_source = NULL WHERE id = :o",
    {"o": BRENNAN},
)
DELETE_ABSENT = ("DELETE FROM futures_outcomes WHERE id = :o", {"o": ABSENT})
INSERT_CROWNED = (
    "INSERT INTO futures_outcomes (id, market_id, external_id, name, is_winner, "
    "resolution_source) VALUES (:o, :m, 'dg_7777', 'dg_7777', TRUE, 'leaderboard')",
    {"o": JOINER, "m": MARKET_ID},
)


async def attempt(rig, write) -> str:
    """A second connection tries one write and commits it if it can."""
    sql, params = write
    async with rig.engine.connect() as conn:
        await conn.execute(text("SET lock_timeout = '300ms'"))
        try:
            await conn.execute(text(sql), params)
            await conn.commit()
            return "committed"
        except DBAPIError as exc:
            await conn.rollback()
            return _sqlstate(exc)


class Hooked:
    """The real session, with a seam right after the roster read or before COMMIT."""

    def __init__(self, session, *, after_roster_read=None, before_commit=None):
        self.session = session
        self.after_roster_read = after_roster_read
        self.before_commit = before_commit
        self.outcome_reads = 0
        self.seen: list[str] = []

    async def execute(self, stmt, params=None):
        result = await self.session.execute(stmt, params)
        sql = " ".join(str(stmt).split())
        self.seen.append(sql)
        if sql.startswith("SELECT") and "FROM futures_outcomes" in sql:
            self.outcome_reads += 1
            if self.outcome_reads == 1 and self.after_roster_read:
                await self.after_roster_read()
        return result

    async def commit(self):
        if self.before_commit:
            await self.before_commit()
        await self.session.commit()

    async def rollback(self):
        await self.session.rollback()


async def plan_hash(rig, repair):
    async with rig.maker() as s:
        out = await repair.run(s, PLACEMENT, execute=False)
        await s.rollback()
    assert out["admissible"], out["refusal_reasons"]
    assert out["roster_lock_premise"] is True
    return out["plan_hash"]


async def apply(rig, repair, h, **hooks):
    """The apply in its own transaction; returns (outcome, what the writer got)."""
    got: dict[str, str] = {}

    def writer(write):
        async def go():
            got["writer"] = await attempt(rig, write)

        return go

    hooks = {k: writer(v) for k, v in hooks.items()}
    async with rig.maker() as s:
        await s.execute(text("SET LOCAL lock_timeout = '2s'"))
        hooked = Hooked(s, **hooks)
        try:
            out = await repair.run(hooked, PLACEMENT, execute=True, expect_plan_hash=h)
        except repair.Refused as exc:
            await s.rollback()
            return ("refused", str(exc)), got.get("writer")
    return ("committed", out), got.get("writer")


# ── the positive control: nobody moves ───────────────────────────────────────


async def test_an_unchanged_roster_commits_one_winner_under_its_locks(rig, arm):
    await seed(rig)
    h = await plan_hash(rig, arm.repair)
    (result, out), _ = await apply(rig, arm.repair, h)
    assert result == "committed" and out["written"] == 2
    assert await winners(rig) == [BRENNAN]
    assert (await grades(rig))[ABSENT] == (None, None)


async def test_the_fixed_arm_locks_the_market_for_update_and_the_roster_for_share(rig):
    """The locks really are held: what pg_locks would say, read by trying them."""
    repair = _load()
    await seed(rig)
    h = await plan_hash(rig, repair)
    probes = {}

    async def probe():
        for name, sql in (
            ("market_key_share", "SELECT id FROM futures_markets WHERE id = :o FOR KEY SHARE NOWAIT"),
            ("absent_no_key_update", "SELECT id FROM futures_outcomes WHERE id = :o FOR NO KEY UPDATE NOWAIT"),
            ("absent_share", "SELECT id FROM futures_outcomes WHERE id = :o FOR SHARE NOWAIT"),
        ):
            oid = MARKET_ID if name.startswith("market") else ABSENT
            async with rig.engine.connect() as conn:
                try:
                    await conn.execute(text(sql), {"o": oid})
                    probes[name] = "granted"
                except DBAPIError as exc:
                    probes[name] = _sqlstate(exc)
                await conn.rollback()

    async with rig.maker() as s:
        hooked = Hooked(s, before_commit=probe)
        out = await repair.run(hooked, PLACEMENT, execute=True, expect_plan_hash=h)
    assert out["written"] == 2
    # FOR UPDATE on the market refuses the FK check's FOR KEY SHARE; FOR SHARE on an
    # unwritten roster row refuses an UPDATE's lock but still shares with readers.
    assert probes == {
        "market_key_share": LOCK_NOT_AVAILABLE,
        "absent_no_key_update": LOCK_NOT_AVAILABLE,
        "absent_share": "granted",
    }


# ── the instant before COMMIT: only a lock can stop this writer ──────────────


@pytest.mark.parametrize(
    "write, brennan_already, e892_winners",
    [
        (CROWN_ABSENT, False, [ABSENT, BRENNAN]),
        (CLEAR_BRENNAN, True, []),
        (INSERT_CROWNED, False, [BRENNAN, JOINER]),
        (DELETE_ABSENT, False, [BRENNAN]),
    ],
    ids=[
        "absent-row-crowned",
        "already-winner-cleared",
        "crowned-outcome-inserted",
        "absent-row-deleted",
    ],
)
async def test_a_writer_at_the_last_instant_is_held_out_until_commit(
    rig, arm, write, brennan_already, e892_winners
):
    await seed(rig, brennan_already=brennan_already)
    h = await plan_hash(rig, arm.repair)
    (result, out), writer = await apply(rig, arm.repair, h, before_commit=write)
    assert result == "committed"
    if arm.name == "fixed":
        assert writer == LOCK_NOT_AVAILABLE
        assert await winners(rig) == [BRENNAN]
    else:
        # e892's locks let the writer commit inside the repair's transaction, after
        # every check the repair can make: the CERT-4252 outcome, on real rows.
        assert writer == "committed"
        assert await winners(rig) == e892_winners


# ── right after the roster read ──────────────────────────────────────────────


async def test_a_writer_right_after_the_roster_read_is_held_out_or_refused(rig, arm):
    await seed(rig)
    h = await plan_hash(rig, arm.repair)
    (result, detail), writer = await apply(rig, arm.repair, h, after_roster_read=CROWN_ABSENT)
    if arm.name == "fixed":
        assert writer == LOCK_NOT_AVAILABLE
        assert result == "committed" and await winners(rig) == [BRENNAN]
    else:
        # Unlocked, the writer commits; the in-transaction roster check is what
        # refuses, and the repair writes nothing.
        assert writer == "committed"
        assert result == "refused" and f"outcomes [{ABSENT}] changed" in detail
        assert await winners(rig) == [ABSENT]
        assert (await grades(rig))[LOSER] == (None, None)


# ── a writer already holding its lock when the repair starts ─────────────────


@pytest.mark.parametrize("write", [CROWN_ABSENT, INSERT_CROWNED], ids=["crown-held", "insert-held"])
async def test_an_uncommitted_writer_makes_the_repair_refuse_not_interleave(rig, arm, write):
    await seed(rig)
    h = await plan_hash(rig, arm.repair)
    sql, params = write
    async with rig.engine.connect() as other:
        await other.execute(text(sql), params)  # holds its row / key-share lock
        async with rig.maker() as s:
            await s.execute(text("SET LOCAL lock_timeout = '300ms'"))
            if arm.name == "fixed":
                with pytest.raises(DBAPIError) as caught:
                    await arm.repair.run(s, PLACEMENT, execute=True, expect_plan_hash=h)
                assert _sqlstate(caught.value) == LOCK_NOT_AVAILABLE
                await s.rollback()
            else:
                out = await arm.repair.run(s, PLACEMENT, execute=True, expect_plan_hash=h)
                assert out["written"] == 2
        await other.commit()
    if arm.name == "fixed":
        # The repair wrote nothing; the other writer's own write is all there is.
        assert (await grades(rig))[LOSER] == (None, None)
    else:
        assert len(await winners(rig)) == 2


# ── the premise is read from the real catalog ────────────────────────────────


async def test_without_the_foreign_key_the_apply_refuses(rig):
    repair = _load()
    await seed(rig)
    h = await plan_hash(rig, repair)
    async with rig.engine.begin() as conn:
        names = await conn.execute(
            text(
                "SELECT conname FROM pg_constraint WHERE contype = 'f' "
                "AND conrelid = 'futures_outcomes'::regclass "
                "AND confrelid = 'futures_markets'::regclass"
            )
        )
        for (name,) in list(names):
            await conn.execute(text(f'ALTER TABLE futures_outcomes DROP CONSTRAINT "{name}"'))
    async with rig.maker() as s:
        with pytest.raises(repair.Refused, match="roster_lock_premise"):
            await repair.run(s, PLACEMENT, execute=True, expect_plan_hash=h)
        await s.rollback()
        dry = await repair.run(s, PLACEMENT, execute=False)
        await s.rollback()
    assert dry["roster_lock_premise"] is False
    assert await winners(rig) == []


# ── the undo still runs under the same locks ─────────────────────────────────


async def test_the_restore_returns_the_written_rows_under_the_locks(rig):
    repair = _load()
    await seed(rig)
    h = await plan_hash(rig, repair)
    async with rig.maker() as s:
        out = await repair.run(s, PLACEMENT, execute=True, expect_plan_hash=h)
    written = out["written_versions"]
    assert sorted(written) == [LOSER, BRENNAN]
    async with rig.maker() as s:
        plan = await repair.run(s, PLACEMENT, execute=False, written=written)
        await s.rollback()
    async with rig.maker() as s:
        back = await repair.run(
            s, PLACEMENT, execute=True, expect_plan_hash=plan["plan_hash"], written=written
        )
    assert back["written"] == 2
    assert set((await grades(rig)).values()) == {(None, None)}
