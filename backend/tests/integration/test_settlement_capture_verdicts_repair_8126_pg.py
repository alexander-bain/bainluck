"""#8126 — the capture-verdict apply, backup, re-run, undo and refusals, against a real PostgreSQL.

WIRED. ci.yml runs this file as its own skip-refusing step in the
``database-integration`` job's ``shared`` group (named in
``.github/ci-postgres-groups.json``), and ``test_pg_gate_seed_completeness.py``
lists it in ``COVERED``. It was staged under ``artifacts/`` until the scope
extension that promoted it here was approved.

What only a real server proves:

* ``raw_response->'_derived'`` read back from ``jsonb`` as a dict, captures
  selected by explicit id and by the bounded window;
* the four-array ``unnest`` binds (bigint / boolean with NULLs) in the bank and
  the compare-and-swap UPDATE;
* the pre-image banked from the LOCKED rows, in the same transaction as the write;
* a re-run that writes nothing; an undo that writes the exact pre-image back;
* drift refusing the undo whole, and ``--restore-undrifted`` leaving it standing;
* a leg repointed after the run (its market or its ticker changed, its grade
  untouched or back at the pre-image) counted as drift, never restored onto;
* a row changed between plan and lock refusing the run with nothing written;
* a row locked by another writer refusing on ``lock_timeout`` instead of waiting.

Run (from ``backend/``)::

    psql -d postgres -c "CREATE DATABASE bl_8126_gate"
    SEARCH_TEST_DATABASE_URL="postgresql+asyncpg://$(whoami)@localhost:5432/bl_8126_gate" \\
      python3 -m pytest -c pytest.ini \\
      tests/integration/test_settlement_capture_verdicts_repair_8126_pg.py -v -rs

Every seed INSERT supplies each NOT NULL column
``test_pg_gate_seed_completeness.py`` requires.
"""

from __future__ import annotations

import importlib.util
import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from sqlalchemy import text

DB_URL = os.environ.get("SEARCH_TEST_DATABASE_URL")

pytestmark = [
    pytest.mark.asyncio,
    pytest.mark.skipif(not DB_URL, reason="set SEARCH_TEST_DATABASE_URL (real Postgres)"),
]

# Staged at ``artifacts/<dir>/`` the backend is a sibling two levels up; promoted
# to ``backend/tests/integration/`` it IS two levels up.
_HERE = Path(__file__).resolve()
_BACKEND = _HERE.parents[2] if _HERE.parent.name == "integration" else _HERE.parents[2] / "backend"
sys.path.insert(0, str(_BACKEND))


def _load(name: str):
    spec = importlib.util.spec_from_file_location(f"{name}_pg", _BACKEND / "scripts" / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod  # a dataclass resolves its module by name
    spec.loader.exec_module(mod)
    return mod


apply_m = _load("apply_settlement_capture_verdicts_8126")
restore_m = _load("restore_settlement_capture_verdicts_8126")

from app.services.settlement_sweep_runner import _capture_row  # noqa: E402
from app.utils.settlement_capture_consumer import REPAIR_BACKUP_TABLE  # noqa: E402
from app.utils.settlement_sweep_plan import Candidate  # noqa: E402
from app.utils.settlement_truth import classify_kalshi  # noqa: E402

SCHEMA = "capture_verdicts_gate_8126"
NOW = datetime(2026, 9, 30, 10, 40, tzinfo=timezone.utc)

MID = 60534962  # the board
NEIGHBOUR_MID = 60534963  # another Kalshi board carrying the SAME ticker
POLY_MID = 60534964
BOARD = "KXNASDAQ100U-26AUG17H1200"
T1, T2, T3, T4 = (f"{BOARD}-T{n}.99" for n in (27999, 28249, 28499, 28749))

# outcome ids
O1, O2, O3, O4 = 238900001, 238900002, 238900003, 238900004
O_NEIGHBOUR = 238900010
O_GRADED = 238900011  # market MID, ticker T5, already graded the other way
T5 = f"{BOARD}-T28999.99"

CAP_BOARD = 107429
CAP_V1_SCALAR = 59742938
SWEEP_ID = "kalshi-2026-09-30"


@pytest.fixture
async def engines():
    from sqlalchemy.ext.asyncio import create_async_engine
    from sqlalchemy.pool import NullPool

    admin = create_async_engine(DB_URL, poolclass=NullPool)
    async with admin.begin() as c:
        await c.execute(text(f"DROP SCHEMA IF EXISTS {SCHEMA} CASCADE"))
        await c.execute(text(f"CREATE SCHEMA {SCHEMA}"))
        for ddl in (
            "CREATE TABLE futures_markets (id int PRIMARY KEY, source varchar(50) NOT NULL, "
            "external_id varchar(200) NOT NULL, name varchar(300) NOT NULL, "
            "category varchar(50) NOT NULL, mutually_exclusive boolean NOT NULL, "
            "status varchar(20) NOT NULL)",
            "CREATE TABLE futures_outcomes (id int PRIMARY KEY, "
            "market_id int NOT NULL REFERENCES futures_markets(id), "
            "external_id varchar(200) NOT NULL, name varchar(300) NOT NULL, "
            "is_winner boolean DEFAULT false, resolution_source varchar(30), "
            "current_probability numeric(7,6))",
            "CREATE TABLE settlement_captures (id int PRIMARY KEY, "
            "market_id int NOT NULL REFERENCES futures_markets(id), "
            "source varchar(40) NOT NULL, external_id varchar(255) NOT NULL, "
            "disposition varchar(40) NOT NULL, winning_outcome text, raw_response jsonb, "
            "candidate_reason varchar(40) NOT NULL, sweep_id varchar(64) NOT NULL, "
            "protocol_version int NOT NULL DEFAULT 1, captured_at timestamptz NOT NULL, "
            "CONSTRAINT ck_settlement_capture_winner_requires_settled "
            "CHECK ((disposition = 'settled') = (winning_outcome IS NOT NULL)))",
        ):
            await c.execute(text(f"SET LOCAL search_path TO {SCHEMA}"))
            await c.execute(text(ddl))
    engine = create_async_engine(
        DB_URL, poolclass=NullPool, connect_args={"server_settings": {"search_path": SCHEMA}}
    )
    yield engine
    await engine.dispose()
    async with admin.begin() as c:
        await c.execute(text(f"DROP SCHEMA IF EXISTS {SCHEMA} CASCADE"))
    await admin.dispose()


def _produced_raw(legs: list[dict]) -> tuple[str, dict]:
    out = classify_kalshi(404, None, 200, {"event": {"event_ticker": BOARD}, "markets": legs})
    row = _capture_row(
        Candidate(MID, "kalshi", BOARD, NOW - timedelta(days=40), "missing_winner"),
        out,
        sweep_id=SWEEP_ID,
        now=NOW,
    )
    return row["disposition"], row["raw_response"]


def _leg(t, result="no", status="finalized"):
    return {"ticker": t, "status": status, "result": result}


async def _seed(engine):
    from sqlalchemy.ext.asyncio import async_sessionmaker

    disp, raw = _produced_raw(
        [_leg(T1, "yes"), _leg(T2), _leg(T3, "scalar"), _leg(T4), _leg(T5, "yes")]
    )
    assert disp == "settled_per_leg"
    async with async_sessionmaker(engine)() as s:
        await s.execute(
            text(
                "INSERT INTO futures_markets (id, source, external_id, name, category, "
                "mutually_exclusive, status) VALUES "
                f"({MID}, 'kalshi', '{BOARD}', 'Nasdaq-100 on Aug 17', 'economics', false, 'open'), "
                f"({NEIGHBOUR_MID}, 'kalshi', '{BOARD}', 'Nasdaq-100 twin board', 'economics', "
                "false, 'open'), "
                f"({POLY_MID}, 'polymarket', 'poly-nasdaq-aug17', 'Nasdaq-100 on Aug 17', "
                "'economics', false, 'open')"
            )
        )
        await s.execute(
            text(
                "INSERT INTO futures_outcomes (id, market_id, external_id, name, is_winner, "
                "resolution_source, current_probability) VALUES "
                f"({O1}, {MID}, '{T1}', '28,000 or above', false, NULL, 0.990000), "
                f"({O2}, {MID}, '{T2}', '28,250 or above', NULL, NULL, 0.010000), "
                f"({O3}, {MID}, '{T3}', '28,500 or above', false, NULL, 0.090000), "
                # T4's stored ticker differs by case: never matched.
                f"({O4}, {MID}, '{T4.lower()}', '28,750 or above', false, NULL, 0.010000), "
                f"({O_NEIGHBOUR}, {NEIGHBOUR_MID}, '{T1}', 'twin board leg', false, NULL, 0.5), "
                f"({O_GRADED}, {MID}, '{T5}', '29,000 or above', false, 'api_settlement', 0.0)"
            )
        )
        await s.execute(
            text(
                "INSERT INTO settlement_captures (id, market_id, source, external_id, "
                "disposition, winning_outcome, raw_response, candidate_reason, sweep_id, "
                "protocol_version, captured_at) "
                "VALUES (:id, :mid, 'kalshi', :ext, :disp, NULL, CAST(:raw AS jsonb), "
                "'missing_winner', :sweep, 2, :at)"
            ),
            {
                "id": CAP_BOARD,
                "mid": MID,
                "ext": BOARD,
                "disp": disp,
                "raw": json.dumps(raw),
                "sweep": SWEEP_ID,
                "at": NOW,
            },
        )
        await s.execute(
            text(
                "INSERT INTO settlement_captures (id, market_id, source, external_id, "
                "disposition, winning_outcome, raw_response, candidate_reason, sweep_id, "
                "protocol_version, captured_at) "
                "VALUES (:id, :mid, 'kalshi', :ext, 'settled', 'scalar', NULL, "
                "'missing_winner', :sweep, 1, :at)"
            ),
            {
                "id": CAP_V1_SCALAR,
                "mid": NEIGHBOUR_MID,
                "ext": BOARD,
                "sweep": "kalshi-2026-09-21",
                "at": NOW - timedelta(days=9),
            },
        )
        await s.commit()


async def _state(engine) -> dict[int, tuple]:
    async with engine.connect() as c:
        rows = await c.execute(
            text(
                "SELECT id, is_winner, resolution_source, current_probability "
                "FROM futures_outcomes ORDER BY id"
            )
        )
        return {int(r.id): (r.is_winner, r.resolution_source, r.current_probability) for r in rows}


async def _session(engine):
    from sqlalchemy.ext.asyncio import async_sessionmaker

    return async_sessionmaker(engine, expire_on_commit=False)()


async def _apply(engine, **kw):
    async with await _session(engine) as s:
        try:
            return await apply_m.run(s, now=NOW, **kw)
        except Exception:
            await s.rollback()
            raise


async def _restore(engine, **kw):
    async with await _session(engine) as s:
        try:
            return await restore_m.run(s, **kw)
        except Exception:
            await s.rollback()
            raise


async def _backup_exists(engine) -> bool:
    async with engine.connect() as c:
        return bool((await c.execute(text("SELECT to_regclass(:t) IS NOT NULL"), {"t": REPAIR_BACKUP_TABLE})).scalar())


async def _assert_row_is_held(engine, oid: int) -> None:
    """Another writer touching ``oid`` now must hit the lock, not land."""
    from sqlalchemy.exc import DBAPIError

    async with engine.connect() as other:
        await other.begin()
        await other.execute(text("SET LOCAL lock_timeout = '200ms'"))
        with pytest.raises(DBAPIError, match="lock"):
            await other.execute(
                text("UPDATE futures_outcomes SET resolution_source = 'box_score' WHERE id = :id"),
                {"id": oid},
            )
        await other.rollback()


class TestApplyOnARealServer:
    async def test_dry_run_plans_and_writes_nothing(self, engines):
        await _seed(engines)
        before = await _state(engines)
        out = await _apply(engines, capture_ids=[CAP_BOARD])
        assert out["mode"] == "dry-run" and out["written"] == 0
        assert out["tallies"]["writes"] == 2
        assert await _state(engines) == before
        assert not await _backup_exists(engines)

    async def test_apply_writes_the_two_licensed_legs_banks_first_and_reruns_as_a_no_op(
        self, engines
    ):
        await _seed(engines)
        before = await _state(engines)
        out = await _apply(engines, capture_ids=[CAP_BOARD], apply=True, run_id="8126-gate-a")
        assert out["written"] == 2 and out["read_back_matches"] == 2
        assert out["tallies"]["skipped_legs"] == {
            "conflicts_existing_grade": 1,
            "no_verdict": 1,
            "unmatched": 1,
        }
        after = await _state(engines)
        assert after[O1][:2] == (True, "api_settlement")
        assert after[O2][:2] == (False, "api_settlement")
        # scalar leg, case-different ticker, the twin board and the graded leg: untouched.
        for oid in (O3, O4, O_NEIGHBOUR, O_GRADED):
            assert after[oid] == before[oid], oid
        # prices never move
        assert all(after[o][2] == before[o][2] for o in before)

        async with engines.connect() as c:
            banked = (
                await c.execute(
                    text(
                        f"SELECT outcome_id, market_id, capture_id, external_id, pre_is_winner, "
                        f"pre_resolution_source, post_is_winner, post_resolution_source, restored_at "
                        f"FROM {REPAIR_BACKUP_TABLE} WHERE run_id = '8126-gate-a' ORDER BY outcome_id"
                    )
                )
            ).all()
        assert [tuple(r) for r in banked] == [
            (O1, MID, CAP_BOARD, T1, False, None, True, "api_settlement", None),
            (O2, MID, CAP_BOARD, T2, None, None, False, "api_settlement", None),
        ]

        again = await _apply(engines, capture_ids=[CAP_BOARD], apply=True, run_id="8126-gate-b")
        assert again["written"] == 0
        assert again["tallies"]["skipped_legs"]["already_graded_agrees"] == 2
        assert await _state(engines) == after

    async def test_the_window_selects_the_derived_capture_and_never_the_v1_scalar(self, engines):
        await _seed(engines)
        out = await _apply(engines, since=NOW - timedelta(days=30), limit=50)
        assert out["selected_captures"] == 1
        assert out["tallies"]["writes"] == 2

    async def test_a_plan_over_max_writes_refuses_before_any_write(self, engines):
        await _seed(engines)
        before = await _state(engines)
        with pytest.raises(apply_m.Refused, match="max-writes"):
            await _apply(engines, capture_ids=[CAP_BOARD], apply=True, max_writes=1)
        assert await _state(engines) == before
        assert not await _backup_exists(engines)

    async def test_an_explicit_v1_scalar_capture_is_refused_and_writes_nothing(self, engines):
        await _seed(engines)
        before = await _state(engines)
        out = await _apply(engines, capture_ids=[CAP_V1_SCALAR, 999], apply=True)
        assert out["written"] == 0
        assert out["refused"] == {
            str(CAP_V1_SCALAR): "non_verdict_winning_outcome: "
            "winning_outcome='scalar' is a settlement type, never a verdict"
        }
        assert out["missing_capture_ids"] == [999]
        assert await _state(engines) == before

    async def test_a_row_changed_between_plan_and_lock_refuses_the_run(self, engines, monkeypatch):
        await _seed(engines)
        real = apply_m.load_outcomes

        async def racing(session, market_ids):
            got = await real(session, market_ids)
            async with engines.begin() as other:  # another writer commits after our read
                await other.execute(
                    text(
                        "UPDATE futures_outcomes SET is_winner = true, "
                        "resolution_source = 'box_score' WHERE id = :id"
                    ),
                    {"id": O2},
                )
            return got

        monkeypatch.setattr(apply_m, "load_outcomes", racing)
        before = await _state(engines)
        with pytest.raises(apply_m.Refused, match="under lock"):
            await _apply(engines, capture_ids=[CAP_BOARD], apply=True, run_id="8126-gate-race")
        after = await _state(engines)
        assert after[O1] == before[O1], "a sibling was written in a refused run"
        assert after[O2][:2] == (True, "box_score"), "the incumbent writer was overwritten"
        assert not await _backup_exists(engines)

    async def test_the_planned_rows_are_held_from_verify_to_commit(self, engines, monkeypatch):
        await _seed(engines)
        real = apply_m._bank

        async def bank_while_probing(session, run_id, writes):
            await _assert_row_is_held(engines, O1)
            await real(session, run_id, writes)

        monkeypatch.setattr(apply_m, "_bank", bank_while_probing)
        out = await _apply(engines, capture_ids=[CAP_BOARD], apply=True, run_id="8126-gate-held")
        assert out["written"] == 2

    async def test_a_row_locked_by_another_writer_refuses_on_lock_timeout(self, engines, monkeypatch):
        from sqlalchemy.exc import DBAPIError

        await _seed(engines)
        monkeypatch.setattr(apply_m, "LOCK_TIMEOUT", "300ms")
        before = await _state(engines)
        async with engines.connect() as holder:
            await holder.begin()
            await holder.execute(text(f"SELECT 1 FROM futures_outcomes WHERE id = {O1} FOR UPDATE"))
            with pytest.raises(DBAPIError, match="lock"):
                await _apply(engines, capture_ids=[CAP_BOARD], apply=True, run_id="8126-gate-lock")
            await holder.rollback()
        assert await _state(engines) == before
        assert not await _backup_exists(engines)


class TestRestoreOnARealServer:
    async def test_restore_writes_the_exact_pre_image_back_and_closes_the_run(self, engines):
        await _seed(engines)
        before = await _state(engines)
        await _apply(engines, capture_ids=[CAP_BOARD], apply=True, run_id="8126-gate-r")
        dry = await _restore(engines, run_id="8126-gate-r")
        assert dry["restorable"] == 2 and dry["restored"] == 0 and dry["drifted"] == []
        out = await _restore(engines, run_id="8126-gate-r", apply=True)
        assert out["restored"] == 2
        assert await _state(engines) == before  # O2's NULL is_winner comes back NULL
        again = await _restore(engines, run_id="8126-gate-r", apply=True)
        assert again["restored"] == 0 and again["note"] == "run already fully restored"

    async def test_drift_refuses_the_whole_restore_then_undrifted_leaves_it_standing(self, engines):
        await _seed(engines)
        before = await _state(engines)
        await _apply(engines, capture_ids=[CAP_BOARD], apply=True, run_id="8126-gate-d")
        async with engines.begin() as other:  # an incumbent writer regrades O1 after the run
            await other.execute(
                text("UPDATE futures_outcomes SET resolution_source = 'settlement_sync' WHERE id = :id"),
                {"id": O1},
            )
        drifted = await _state(engines)
        with pytest.raises(restore_m.Refused, match="drifted"):
            await _restore(engines, run_id="8126-gate-d", apply=True)
        assert await _state(engines) == drifted, "a refused restore wrote"

        out = await _restore(engines, run_id="8126-gate-d", apply=True, restore_undrifted=True)
        assert out["restored"] == 1
        now = await _state(engines)
        assert now[O1][:2] == (True, "settlement_sync"), "the incumbent change was destroyed"
        assert now[O2] == before[O2]
        async with engines.connect() as c:
            open_rows = (
                await c.execute(
                    text(
                        f"SELECT outcome_id FROM {REPAIR_BACKUP_TABLE} "
                        "WHERE run_id = '8126-gate-d' AND restored_at IS NULL"
                    )
                )
            ).scalars().all()
        assert open_rows == [O1]

    # #8126 review P2: apply banks the leg's market_id and external_id; a row
    # repointed after the run is a different leg, and the old leg's pre-image
    # must never be written onto it — nor its backup closed as already_pre.
    @pytest.mark.parametrize(
        "field,value",
        [("market_id", NEIGHBOUR_MID), ("external_id", "KXOTHER-LEG")],
        ids=["market_id", "external_id"],
    )
    @pytest.mark.parametrize(
        "grade", [None, (False, None)], ids=["grade_at_post", "grade_back_at_pre"]
    )
    async def test_a_repointed_leg_is_drift_refused_whole_then_left_open(
        self, engines, field, value, grade
    ):
        await _seed(engines)
        before = await _state(engines)
        await _apply(engines, capture_ids=[CAP_BOARD], apply=True, run_id="8126-gate-id")
        sets = f"{field} = :value"
        if grade is not None:
            sets += ", is_winner = :w, resolution_source = :src"
        async with engines.begin() as other:
            await other.execute(
                text(f"UPDATE futures_outcomes SET {sets} WHERE id = :id"),
                {"value": value, "id": O1, **({"w": grade[0], "src": grade[1]} if grade else {})},
            )

        async def o1() -> tuple:
            async with engines.connect() as c:
                row = (
                    await c.execute(
                        text(
                            "SELECT market_id, external_id, is_winner, resolution_source "
                            "FROM futures_outcomes WHERE id = :id"
                        ),
                        {"id": O1},
                    )
                ).one()
            return tuple(row)

        repointed = await o1()
        assert repointed[{"market_id": 0, "external_id": 1}[field]] == value

        dry = await _restore(engines, run_id="8126-gate-id")
        assert (dry["restorable"], dry["already_pre"]) == (1, 0)
        assert dry["drifted"] == [
            {
                "outcome_id": O1,
                "post": [MID, T1, True, "api_settlement"],
                "now": list(repointed),
            }
        ]

        with pytest.raises(restore_m.Refused, match="drifted"):
            await _restore(engines, run_id="8126-gate-id", apply=True)
        assert await o1() == repointed, "a refused restore wrote onto the repointed leg"

        out = await _restore(engines, run_id="8126-gate-id", apply=True, restore_undrifted=True)
        assert out["restored"] == 1 and out["already_pre"] == 0
        assert await o1() == repointed, "the old leg's pre-image landed on a different leg"
        assert (await _state(engines))[O2] == before[O2]
        async with engines.connect() as c:
            open_rows = (
                await c.execute(
                    text(
                        f"SELECT outcome_id FROM {REPAIR_BACKUP_TABLE} "
                        "WHERE run_id = '8126-gate-id' AND restored_at IS NULL"
                    )
                )
            ).scalars().all()
        assert open_rows == [O1], "the repointed leg's backup was closed"

    @pytest.mark.parametrize(
        "field,value",
        [
            ("market_id", NEIGHBOUR_MID),
            ("external_id", "KXOTHER-LEG"),
            ("resolution_source", "settlement_sync"),
        ],
    )
    async def test_the_compare_and_swap_refuses_on_its_own_when_classify_is_wrong(
        self, engines, monkeypatch, field, value
    ):
        # Under the lock classify() is the gate the CAS backs up, so only a
        # classifier that waves a moved row through can reach the CAS. Force one.
        await _seed(engines)
        await _apply(engines, capture_ids=[CAP_BOARD], apply=True, run_id="8126-gate-cas")
        async with engines.begin() as other:
            await other.execute(
                text(f"UPDATE futures_outcomes SET {field} = :value WHERE id = :id"),
                {"value": value, "id": O1},
            )
        moved = await _state(engines)
        monkeypatch.setattr(restore_m, "classify", lambda banked, current: (list(banked), [], []))
        with pytest.raises(restore_m.Refused, match="compare-and-swap"):
            await _restore(engines, run_id="8126-gate-cas", apply=True)
        assert await _state(engines) == moved, "the CAS let a moved row be written"

    async def test_the_restored_rows_are_held_from_classify_to_commit(self, engines, monkeypatch):
        await _seed(engines)
        await _apply(engines, capture_ids=[CAP_BOARD], apply=True, run_id="8126-gate-rh")
        real = restore_m.classify
        probed = []

        def classify_after_probe(banked, current):
            probed.append(True)
            return real(banked, current)

        async def probe_between_read_and_write(*_):
            # classify() runs after the outcome read and before the UPDATE; the
            # probe runs at the same point, from another connection.
            await _assert_row_is_held(engines, O1)

        monkeypatch.setattr(restore_m, "classify", classify_after_probe)
        async with await _session(engines) as s:
            orig = s.execute

            async def execute(stmt, *a, **k):
                result = await orig(stmt, *a, **k)
                if "FROM futures_outcomes" in str(stmt) and "UPDATE" not in str(stmt):
                    await probe_between_read_and_write()
                return result

            s.execute = execute  # type: ignore[method-assign]
            out = await restore_m.run(s, run_id="8126-gate-rh", apply=True)
        assert out["restored"] == 2 and probed

    async def test_an_unknown_run_refuses(self, engines):
        await _seed(engines)
        await _apply(engines, capture_ids=[CAP_BOARD], apply=True, run_id="8126-gate-k")
        with pytest.raises(restore_m.Refused, match="no backup rows"):
            await _restore(engines, run_id="8126-nope", apply=True)
