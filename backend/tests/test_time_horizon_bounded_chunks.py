"""Bounded chunking, mid-horizon WIP resume, and Postgres equivalence tests (#13518).

Verifies that ``compute_time_horizon_calibration``:
1. Cuts the global non-event ``virtual_market`` roster once using
   content-addressed ``vm_id`` hash buckets (never splitting a ``vm_id`` and
   never shifting keys when new markets resolve between beats).
2. Bounds every chunk with ``statement_timeout`` and recursively bisects along
   whole-``vm_id`` boundaries on timeout (deferring cleanly only when a single
   ``vm_id`` cannot be narrowed further).
3. Saves and resumes mid-horizon progress under ``_TIME_HORIZON_WIP_KEY`` when
   stopping at ``_HORIZON_DEADLINE_S``.
4. Produces exact numeric and diagnostic equivalence against the monolithic
   ``_build_time_horizon_sql(days)`` query on real PostgreSQL
   (``CALIBRATION_TEST_DATABASE_URL``).
"""

from __future__ import annotations

import json
import os
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

import app.tasks.precompute_calibration as pc
from app.utils.calibration_staged_futures import RosterRow
from app.utils.task_verdict import COMPLETE, PARTIAL, verdict_for

_MAIN_KEY = "bainluck:calibration:time_horizon"
_RES = datetime(2026, 1, 15, 12, 0, 0, tzinfo=timezone.utc)

DB_URL = os.environ.get("CALIBRATION_TEST_DATABASE_URL")
pg = pytest.mark.skipif(
    not DB_URL,
    reason="set CALIBRATION_TEST_DATABASE_URL to run real-Postgres chunk parity tests",
)


class _FakeRedis:
    def __init__(self, initial=None):
        self.store: dict[str, str] = {}
        if initial is not None:
            self.store[pc._TIME_HORIZON_WIP_KEY] = initial

    def get(self, key):
        return self.store.get(key)

    def set(self, key, value, ex=None):
        self.store[key] = value

    def delete(self, key):
        self.store.pop(key, None)


class _QueryCanceledTimeoutError(Exception):
    """Test error recognized by ``is_statement_timeout`` via message."""

    def __init__(self, msg: str = "canceling statement due to statement timeout"):
        super().__init__(msg)


def _h_diag_row(
    *,
    bucket_idx=None,
    source=None,
    category=None,
    n=0,
    winners=0,
    sum_prob=0.0,
    sum_sq_err=0.0,
    candidate_n=0,
    final_n=0,
    distinct_questions=0,
    excl_illiquid=0,
    excl_poly_placeholder=0,
    excl_malformed_binary=0,
    excl_esports_bundle=0,
    excl_golf_placeholder=0,
    excl_kalshi_prop_threshold=0,
    excl_weather_wide_spread=0,
    excl_field_incomplete=0,
    ladder_questions=0,
    ladder_rungs_suppressed=0,
):
    return SimpleNamespace(
        bucket_idx=bucket_idx,
        source=source,
        category=category,
        n=n,
        winners=winners,
        avg_prob=(sum_prob / n) if n else None,
        sum_prob=sum_prob,
        sum_sq_err=sum_sq_err,
        candidate_n=candidate_n,
        final_n=final_n,
        distinct_questions=distinct_questions,
        excl_illiquid=excl_illiquid,
        excl_poly_placeholder=excl_poly_placeholder,
        excl_malformed_binary=excl_malformed_binary,
        excl_esports_bundle=excl_esports_bundle,
        excl_golf_placeholder=excl_golf_placeholder,
        excl_kalshi_prop_threshold=excl_kalshi_prop_threshold,
        excl_weather_wide_spread=excl_weather_wide_spread,
        excl_field_incomplete=excl_field_incomplete,
        ladder_questions=ladder_questions,
        ladder_rungs_suppressed=ladder_rungs_suppressed,
    )


class _ExecResult:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return self._rows


class TestHorizonSqlAndPlanning:
    def test_horizon_generation_sql_matches_horizon_market_info_scope(self):
        gen_sql = pc._horizon_generation_sql()
        h0_sql, p0 = pc._build_time_horizon_sql(0)
        h7_sql, p7 = pc._build_time_horizon_sql(7)

        assert pc._HORIZON_MARKET_INFO_EXTRA in gen_sql
        assert pc._HORIZON_MARKET_INFO_EXTRA in h0_sql
        assert pc._HORIZON_MARKET_INFO_EXTRA in h7_sql
        assert "FROM virtual_market" in gen_sql
        assert "ORDER BY market_id" in gen_sql
        assert p0 == {}
        assert p7 == {"days": 7}

    def test_build_time_horizon_sql_frozen_vm_roster_scoping(self):
        mono_sql, _ = pc._build_time_horizon_sql(7)
        chunk_sql, params = pc._build_time_horizon_sql(7, frozen_vm_roster=True)

        assert "frozen_vm_roster" not in mono_sql
        assert pc.VM_ROSTER_MARKET_IDS_PARAM not in mono_sql

        assert "frozen_vm_roster AS (" in chunk_sql
        assert pc.VM_ROSTER_MARKET_INFO_EXTRA in chunk_sql
        assert f"fo.market_id = ANY(CAST(:{pc.VM_ROSTER_MARKET_IDS_PARAM} AS bigint[]))" in chunk_sql
        assert f":{pc.VM_ROSTER_VM_IDS_PARAM}" in chunk_sql
        assert f":{pc.VM_ROSTER_IS_GROUPED_PARAM}" in chunk_sql
        assert params == {"days": 7}

    def test_plan_and_bisect_keep_vm_ids_whole(self):
        roster = [
            RosterRow(market_id=101, source="polymarket", vm_id="g:big", is_grouped=True),
            RosterRow(market_id=102, source="polymarket", vm_id="g:big", is_grouped=True),
            RosterRow(market_id=103, source="polymarket", vm_id="g:big", is_grouped=True),
            RosterRow(market_id=201, source="kalshi", vm_id="m:201", is_grouped=False),
            RosterRow(market_id=202, source="kalshi", vm_id="m:202", is_grouped=False),
        ]
        units, assignment = pc._plan_horizon_units(roster, buckets=4)

        seen_markets: list[int] = []
        vm_locations: dict[str, set[str]] = {}
        for unit in units:
            seen_markets.extend(unit.market_ids)
            for vm_id in unit.vm_ids:
                vm_locations.setdefault(vm_id, set()).add(unit.key)

        assert sorted(seen_markets) == [101, 102, 103, 201, 202]
        assert all(len(keys) == 1 for keys in vm_locations.values())

        # Single vm_id cannot be split further
        assert pc._bisect_horizon_markets((101, 102, 103), assignment) is None

        # Multi-vm chunk splits cleanly without tearing g:big
        split = pc._bisect_horizon_markets((101, 102, 103, 201, 202), assignment)
        assert split is not None
        left, right = split
        assert left and right
        assert sorted([*left, *right]) == [101, 102, 103, 201, 202]
        left_vms = {assignment[m][0] for m in left}
        right_vms = {assignment[m][0] for m in right}
        assert left_vms.isdisjoint(right_vms)

    def test_deserialize_rejects_corrupt_or_mismatched_in_progress(self):
        valid = pc._serialize_horizon_in_progress(
            "T-30",
            256,
            {"256:0"},
            {(5, "kalshi", "sports"): {"n": 2, "winners": 1, "sum_prob": 1.1, "sum_sq_err": 0.5}},
            pc._empty_horizon_diag(),
            {"256:0": "abc"},
        )
        assert pc._deserialize_horizon_in_progress(valid, label="T-30", buckets=256) is not None
        assert pc._deserialize_horizon_in_progress(valid, label="T-7", buckets=256) is None
        assert pc._deserialize_horizon_in_progress(valid, label="T-30", buckets=128) is None

        bad_diag = {**valid, "diag_acc": {**valid["diag_acc"], "final_n": -1}}
        assert pc._deserialize_horizon_in_progress(bad_diag, label="T-30", buckets=256) is None

        bool_diag = {**valid, "diag_acc": {**valid["diag_acc"], "final_n": True}}
        assert pc._deserialize_horizon_in_progress(bool_diag, label="T-30", buckets=256) is None


class TestTaskResumeBisectionAndIsolation:
    async def test_mid_horizon_deadline_resume_survives_cross_beat_roster_growth(self, monkeypatch):
        from app.tasks import base as task_base
        from app.tasks import calibration_main_build as cmb
        from app.tasks import redis_state

        rc = _FakeRedis()
        monkeypatch.setattr(redis_state, "get_redis_client", lambda: rc)
        monkeypatch.setattr(pc, "_HORIZON_UNIT_BUCKETS", 4)
        monkeypatch.setattr(pc, "_HORIZON_WIP_SAVE_EVERY", 1)
        monkeypatch.setattr(pc, "_HORIZON_ROSTER_TIMEOUT_S", 10)
        monkeypatch.setattr(pc, "_HORIZON_STMT_TIMEOUT_S", 10)
        monkeypatch.setattr(pc, "_HORIZON_DEADLINE_S", 50)
        monkeypatch.setattr(pc, "_MIN_OUTCOMES_PER_HORIZON", 1)

        async def _noop_tag(_db, *, task: str):
            return None

        monkeypatch.setattr(cmb, "tag_scheduled_session", _noop_tag)

        # Pick 4 market IDs landing in distinct buckets plus a 5th market landing in the
        # 3rd bucket (unfinished after Beat 1 stops after 2 buckets).
        chosen_roster = []
        slot_keys_order = []
        seen_slots = set()
        for mid in range(1, 200):
            row = RosterRow(market_id=mid, source="kalshi", vm_id=f"m:{mid}", is_grouped=False)
            units_check, _ = pc._plan_horizon_units([row], buckets=4)
            key = units_check[0].key
            if key not in seen_slots:
                seen_slots.add(key)
                slot_keys_order.append(key)
                chosen_roster.append(row)
                if len(seen_slots) == 4:
                    break
        assert len(chosen_roster) == 4
        planned_beat1, _ = pc._plan_horizon_units(chosen_roster, buckets=4)
        target_unfinished_slot = planned_beat1[2].key
        new_mid = None
        for cand in range(900, 1200):
            cand_row = RosterRow(market_id=cand, source="polymarket", vm_id=f"m:{cand}", is_grouped=False)
            units_check, _ = pc._plan_horizon_units([cand_row], buckets=4)
            if units_check[0].key == target_unfinished_slot:
                new_mid = cand_row
                break
        assert new_mid is not None

        roster_beat2 = list(chosen_roster) + [new_mid]
        active_roster = chosen_roster
        chunk_calls: list[tuple[int | None, tuple[int, ...]]] = []

        # Isolate fake clock from stdlib time so pytest/anyio teardown is untouched
        clock = {"t": 0.0}
        step_iter = iter([0.0, 1.0, 2.0, 3.0, 45.0])

        def _beat1_clock():
            val = next(step_iter, None)
            if val is not None:
                clock["t"] = val
            else:
                clock["t"] += 0.1
            return clock["t"]

        monkeypatch.setattr(pc, "time", SimpleNamespace(monotonic=_beat1_clock))

        class _FakeSession:
            async def rollback(self):
                return None

            async def execute(self, stmt, params=None):
                sql = str(stmt)
                if "SET LOCAL statement_timeout" in sql:
                    return _ExecResult([])
                if "SELECT market_id, source, vm_id, is_grouped" in sql:
                    return _ExecResult(active_roster)
                mids = tuple(int(x) for x in params[pc.VM_ROSTER_MARKET_IDS_PARAM])
                days = params.get("days", 0)
                chunk_calls.append((days, mids))
                return _ExecResult([
                    _h_diag_row(
                        bucket_idx=5,
                        source="kalshi",
                        category="politics",
                        n=len(mids),
                        winners=len(mids),
                        sum_prob=0.5 * len(mids),
                        sum_sq_err=0.25 * len(mids),
                        candidate_n=len(mids),
                        final_n=len(mids),
                        distinct_questions=len(mids),
                    )
                ])

        @asynccontextmanager
        async def _fake_session_ctx():
            yield _FakeSession()

        monkeypatch.setattr(task_base, "get_task_session", _fake_session_ctx)

        res1 = await pc._compute_time_horizon_calibration()
        assert res1["status"] == "partial"
        assert res1["horizons_done"] == 0
        assert res1["in_progress_horizon"] == "T-30"
        assert res1["horizon_chunks_done"] == 2
        assert verdict_for("compute_time_horizon_calibration", res1).verdict == PARTIAL
        assert pc._TIME_HORIZON_WIP_KEY in rc.store
        wip1 = json.loads(rc.store[pc._TIME_HORIZON_WIP_KEY])
        assert wip1["in_progress"]["horizon"] == "T-30"
        done_in_beat1 = {m for _days, mids in chunk_calls for m in mids}
        assert len(done_in_beat1) == 2

        # Beat 2: roster grew by market 999, plenty of clock budget.
        active_roster = roster_beat2
        chunk_calls.clear()
        beat2_counter = {"t": 0.0}

        def _beat2_clock():
            beat2_counter["t"] += 0.1
            return beat2_counter["t"]

        monkeypatch.setattr(pc, "time", SimpleNamespace(monotonic=_beat2_clock))

        res2 = await pc._compute_time_horizon_calibration()
        assert res2["status"] == "ok"
        assert res2["horizons_done"] == 4
        assert verdict_for("compute_time_horizon_calibration", res2).verdict == COMPLETE
        assert pc._TIME_HORIZON_WIP_KEY not in rc.store

        # T-30 resumed ONLY unfinished markets (never re-running Beat 1's 2 markets)
        t30_mids_beat2 = {m for days, mids in chunk_calls if days == 30 for m in mids}
        assert t30_mids_beat2.isdisjoint(done_in_beat1)
        assert new_mid.market_id in t30_mids_beat2

        # Note: in Beat 1 T-30 banked 2 markets; Beat 2 finished remaining markets
        published = json.loads(rc.store[_MAIN_KEY])
        assert published["complete"] is True
        assert published["horizons"]["T-30"]["total_outcomes"] == 5
        assert published["horizons"]["T-0"]["total_outcomes"] == 5

    async def test_timeout_bisects_multi_vm_unit_and_isolates_single_vm_failure(self, monkeypatch):
        from app.tasks import base as task_base
        from app.tasks import calibration_main_build as cmb
        from app.tasks import redis_state

        async def _noop_tag(_db, *, task: str):
            return None

        monkeypatch.setattr(cmb, "tag_scheduled_session", _noop_tag)
        monkeypatch.setattr(pc, "_HORIZON_UNIT_BUCKETS", 1)
        monkeypatch.setattr(pc, "_MIN_OUTCOMES_PER_HORIZON", 1)
        monkeypatch.setattr(pc, "_HORIZON_DEADLINE_S", 540)

        roster = [
            RosterRow(market_id=10, source="kalshi", vm_id="m:10", is_grouped=False),
            RosterRow(market_id=20, source="kalshi", vm_id="m:20", is_grouped=False),
        ]

        # Part A: multi-vm timeout on days=30 bisects cleanly and completes all 4
        rc_a = _FakeRedis()
        monkeypatch.setattr(redis_state, "get_redis_client", lambda: rc_a)
        seen_t30_calls: list[tuple[int, ...]] = []

        class _BisectSession:
            async def rollback(self):
                return None

            async def execute(self, stmt, params=None):
                sql = str(stmt)
                if "SET LOCAL statement_timeout" in sql:
                    return _ExecResult([])
                if "SELECT market_id, source, vm_id, is_grouped" in sql:
                    return _ExecResult(roster)
                mids = tuple(int(x) for x in params[pc.VM_ROSTER_MARKET_IDS_PARAM])
                days = params.get("days", 0)
                if days == 30:
                    seen_t30_calls.append(mids)
                    if len(mids) > 1:
                        raise _QueryCanceledTimeoutError()
                return _ExecResult([
                    _h_diag_row(
                        bucket_idx=5,
                        source="kalshi",
                        category="sports",
                        n=len(mids),
                        winners=1 if 10 in mids else 0,
                        sum_prob=0.5 * len(mids),
                        sum_sq_err=0.25 * len(mids),
                        candidate_n=len(mids),
                        final_n=len(mids),
                        distinct_questions=len(mids),
                    )
                ])

        @asynccontextmanager
        async def _bisect_ctx():
            yield _BisectSession()

        monkeypatch.setattr(task_base, "get_task_session", _bisect_ctx)
        res_a = await pc._compute_time_horizon_calibration()
        assert res_a["status"] == "ok"
        assert res_a["horizons_done"] == 4
        assert seen_t30_calls == [(10, 20), (10,), (20,)]
        pub_a = json.loads(rc_a.store[_MAIN_KEY])
        assert pub_a["horizons"]["T-30"]["total_outcomes"] == 2
        assert pub_a["horizons"]["T-30"]["total_winners"] == 1

        # Part B: irreducible single-vm timeout on T-30 defers T-30 only; other 3 finish
        rc_b = _FakeRedis()
        monkeypatch.setattr(redis_state, "get_redis_client", lambda: rc_b)
        single_roster = [RosterRow(market_id=10, source="kalshi", vm_id="m:10", is_grouped=False)]

        class _PoisonT30Session:
            async def rollback(self):
                return None

            async def execute(self, stmt, params=None):
                sql = str(stmt)
                if "SET LOCAL statement_timeout" in sql:
                    return _ExecResult([])
                if "SELECT market_id, source, vm_id, is_grouped" in sql:
                    return _ExecResult(single_roster)
                if params.get("days") == 30:
                    raise _QueryCanceledTimeoutError()
                return _ExecResult([
                    _h_diag_row(
                        bucket_idx=4,
                        source="kalshi",
                        category="sports",
                        n=1,
                        winners=0,
                        sum_prob=0.4,
                        sum_sq_err=0.16,
                        candidate_n=1,
                        final_n=1,
                        distinct_questions=1,
                    )
                ])

        @asynccontextmanager
        async def _poison_ctx():
            yield _PoisonT30Session()

        monkeypatch.setattr(task_base, "get_task_session", _poison_ctx)
        res_b = await pc._compute_time_horizon_calibration()
        assert res_b["status"] == "partial"
        assert res_b["horizons_done"] == 3
        pub_b = json.loads(rc_b.store[_MAIN_KEY])
        assert pub_b["complete"] is False
        assert pub_b["missing"] == ["T-30"]
        assert set(pub_b["horizons"]) == {"T-7", "T-1", "T-0"}

    async def test_empty_roster_completes_all_horizons_and_clears_wip(self, monkeypatch):
        from app.tasks import base as task_base
        from app.tasks import calibration_main_build as cmb
        from app.tasks import redis_state

        rc = _FakeRedis()
        monkeypatch.setattr(redis_state, "get_redis_client", lambda: rc)

        async def _noop_tag(_db, *, task: str):
            return None

        monkeypatch.setattr(cmb, "tag_scheduled_session", _noop_tag)

        class _EmptySession:
            async def rollback(self):
                return None

            async def execute(self, stmt, params=None):
                return _ExecResult([])

        @asynccontextmanager
        async def _empty_ctx():
            yield _EmptySession()

        monkeypatch.setattr(task_base, "get_task_session", _empty_ctx)
        res = await pc._compute_time_horizon_calibration()
        assert res == {"status": "ok", "horizons": 4, "horizons_done": 4, "total": 4}
        assert pc._TIME_HORIZON_WIP_KEY not in rc.store
        pub = json.loads(rc.store[_MAIN_KEY])
        assert pub["complete"] is True
        assert all(pub["horizons"][label]["skipped"] is True for label, _ in pc._HORIZONS)
        assert all(pub["horizons"][label]["total_outcomes"] == 0 for label, _ in pc._HORIZONS)


# ---------------------------------------------------------------------------
# REAL POSTGRES EQUIVALENCE TESTS (#13518, wired into ci.yml #12612 cal gate)
# ---------------------------------------------------------------------------

async def _seed_market(
    session,
    mid: int,
    source: str,
    *,
    mex: bool,
    mtype: str,
    category: str,
    group_id: str | None = None,
    volume: int = 100,
):
    from sqlalchemy import text

    params = {
        "id": mid,
        "src": source,
        "ext": f"hb-{mid}",
        "nm": f"Market {mid}?",
        "gid": group_id,
        "mex": mex,
        "mt": mtype,
        "cat": category,
        "vol": volume,
        "rd": _RES,
    }
    if mtype == "field":
        meta_expr = "CAST(:meta AS jsonb)"
        params["meta"] = json.dumps(
            {
                "shape": {
                    "exhaustive": True,
                    "expected_winners": 1,
                    "outcome_relation": "competitors",
                }
            }
        )
    else:
        meta_expr = "NULL"
    await session.execute(
        text(
            "INSERT INTO futures_markets (id, source, external_id, name, group_id, category, "
            "status, mutually_exclusive, market_type, llm_sport_category, volume, "
            f"resolution_date, market_metadata) VALUES (:id, :src, :ext, :nm, :gid, :cat, "
            f"'resolved', :mex, :mt, :cat, :vol, :rd, {meta_expr})"
        ),
        params,
    )


async def _seed_outcome(
    session,
    mid: int,
    idx: int,
    *,
    op: float,
    cp: float,
    win: bool,
    volume: int = 10,
    yes_bid: float | None = None,
    yes_ask: float | None = None,
    name: str | None = None,
) -> int:
    from sqlalchemy import text

    oid = mid * 100 + idx
    await session.execute(
        text(
            "INSERT INTO futures_outcomes (id, market_id, external_id, name, opening_probability, "
            "calibration_probability, is_winner, resolution_source, volume, "
            "current_yes_bid, current_yes_ask) VALUES "
            "(:id, :mid, :ext, :nm, :op, :cp, :win, 'api_settlement', :vol, :yb, :ya)"
        ),
        {
            "id": oid,
            "mid": mid,
            "ext": f"hb-o-{oid}",
            "nm": name or f"outcome-{idx}",
            "op": op,
            "cp": cp,
            "win": win,
            "vol": volume,
            "yb": yes_bid,
            "ya": yes_ask,
        },
    )
    return oid


async def _seed_snap(session, oid: int, *, days_before: float, probability: float):
    from sqlalchemy import text

    await session.execute(
        text(
            "INSERT INTO futures_odds_snapshots (outcome_id, bookmaker, probability, "
            "reading_count, captured_at) VALUES (:oid, 'test', :p, 1, :ts)"
        ),
        {"oid": oid, "p": probability, "ts": _RES - timedelta(days=days_before)},
    )


async def _seed_parity_corpus(session):
    # 1. Grouped Polymarket vm_id (3 markets sharing grp-alpha -> vm_id = 'g:grp-alpha')
    for idx, (mid, p30, p0, win) in enumerate([
        (95101, 0.30, 0.45, True),
        (95102, 0.42, 0.48, False),
        (95103, 0.18, 0.12, False),
    ]):
        await _seed_market(
            session, mid, "polymarket", mex=True, mtype="binary",
            category="politics", group_id="grp-alpha",
        )
        o_yes = await _seed_outcome(session, mid, 0, op=p0, cp=p0, win=win)
        o_no = await _seed_outcome(session, mid, 1, op=1 - p0, cp=1 - p0, win=not win)
        await _seed_snap(session, o_yes, days_before=35, probability=p30)
        await _seed_snap(session, o_no, days_before=35, probability=1 - p30)
        await _seed_snap(session, o_yes, days_before=1, probability=p0)
        await _seed_snap(session, o_no, days_before=1, probability=1 - p0)

    # 2. Proved-exclusive field (complete at T-0, INCOMPLETE at T-7)
    await _seed_market(
        session, 95201, "polymarket", mex=True, mtype="field", category="economics"
    )
    for i, (hp, win, snap_days) in enumerate([
        (0.75, True, 20),
        (0.65, False, 20),
        (0.25, False, 2),  # missing before T-7 -> remaining sum 1.40 > 1.15 -> excl_field_incomplete at T-7
    ]):
        oid = await _seed_outcome(session, 95201, i, op=hp, cp=hp, win=win)
        await _seed_snap(session, oid, days_before=snap_days, probability=hp)

    # 3. Cumulative threshold ladder (quantity, win_count > 1 -> collapses to 1 rep)
    await _seed_market(
        session, 95301, "kalshi", mex=False, mtype="quantity", category="tech"
    )
    for i, (hp, win) in enumerate([(0.70, True), (0.55, True), (0.20, False)]):
        oid = await _seed_outcome(
            session, 95301, i, op=hp, cp=hp, win=win,
            yes_bid=hp - 0.02, yes_ask=hp + 0.02, name=f"Above {i}",
        )
        await _seed_snap(session, oid, days_before=15, probability=hp)

    # 4. Liquid + illiquid Kalshi binary markets across different vm_ids
    for mid, hp, win, vol, bid in [
        (95401, 0.65, True, 25, 0.64),
        (95402, 0.35, False, 15, 0.34),
        (95403, 0.52, True, 0, None),   # excl_illiquid
        (95404, 0.80, True, 40, 0.79),
    ]:
        await _seed_market(
            session, mid, "kalshi", mex=True, mtype="binary", category="sports"
        )
        oid = await _seed_outcome(
            session, mid, 0, op=hp, cp=hp, win=win, volume=vol, yes_bid=bid
        )
        oid_no = await _seed_outcome(
            session, mid, 1, op=1 - hp, cp=1 - hp, win=not win, volume=vol,
            yes_bid=(1 - bid if bid is not None else None),
        )
        await _seed_snap(session, oid, days_before=12, probability=hp)
        await _seed_snap(session, oid_no, days_before=12, probability=1 - hp)

    await session.commit()


@pg
@pytest.mark.asyncio
async def test_chunked_time_horizon_sql_matches_monolithic_exactly(monkeypatch):
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    from app.models.models import Base

    monkeypatch.setattr(pc, "_MIN_OUTCOMES_PER_HORIZON", 1)

    engine = create_async_engine(DB_URL)
    pg14_safe_tables = [
        t for t in Base.metadata.sorted_tables if t.name != "container_provider_anchors"
    ]
    async with engine.begin() as conn:
        await conn.run_sync(lambda c: Base.metadata.create_all(c, tables=pg14_safe_tables))
    Session = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with Session() as s:
            await _seed_parity_corpus(s)

            roster = await pc._read_horizon_roster(s)
            assert len(roster) >= 7
            units, assignment = pc._plan_horizon_units(roster, buckets=8)
            assert len(units) >= 3  # proves real multi-chunk splitting

            for days in (0, 7):
                mono_sql, mono_params = pc._build_time_horizon_sql(days)
                mono_rows = (await s.execute(text(mono_sql), mono_params)).all()
                mono_buckets: dict = {}
                mono_diag = pc._empty_horizon_diag()
                pc._fold_horizon_chunk_rows(mono_rows, mono_buckets, mono_diag)
                mono_final = pc._finalize_horizon_result(mono_buckets, mono_diag)

                chunk_sql_str, base_params = pc._build_time_horizon_sql(
                    days, frozen_vm_roster=True
                )
                chunk_sql = text(chunk_sql_str)
                chunk_buckets: dict = {}
                chunk_diag = pc._empty_horizon_diag()
                for unit in units:
                    params = {**base_params, **pc._roster_bind_params(unit.market_ids, assignment)}
                    rows = (await s.execute(chunk_sql, params)).all()
                    pc._fold_horizon_chunk_rows(rows, chunk_buckets, chunk_diag)
                chunk_final = pc._finalize_horizon_result(chunk_buckets, chunk_diag)

                assert chunk_diag == mono_diag
                assert chunk_final == mono_final
                assert chunk_final["total_outcomes"] > 0
                if days == 7:
                    assert chunk_final["excluded"]["field_incomplete"] == 2
                else:
                    assert chunk_final["excluded"]["field_incomplete"] == 0
                assert chunk_final["threshold_ladder"]["questions"] == 1
                assert chunk_final["threshold_ladder"]["rungs_suppressed"] == 2
    finally:
        async with engine.begin() as conn:
            await conn.run_sync(lambda c: Base.metadata.drop_all(c, tables=pg14_safe_tables))
        await engine.dispose()


@pg
@pytest.mark.asyncio
async def test_bisected_horizon_chunks_match_unsplit_unit_on_postgres(monkeypatch):
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    from app.models.models import Base

    monkeypatch.setattr(pc, "_MIN_OUTCOMES_PER_HORIZON", 1)

    engine = create_async_engine(DB_URL)
    pg14_safe_tables = [
        t for t in Base.metadata.sorted_tables if t.name != "container_provider_anchors"
    ]
    async with engine.begin() as conn:
        await conn.run_sync(lambda c: Base.metadata.create_all(c, tables=pg14_safe_tables))
    Session = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with Session() as s:
            await _seed_parity_corpus(s)
            roster = await pc._read_horizon_roster(s)
            units, assignment = pc._plan_horizon_units(roster, buckets=1)
            assert len(units) == 1
            whole_unit = units[0]

            split = pc._bisect_horizon_markets(whole_unit.market_ids, assignment)
            assert split is not None
            left_mids, right_mids = split

            sql_str, base_params = pc._build_time_horizon_sql(0, frozen_vm_roster=True)
            stmt = text(sql_str)

            whole_rows = (
                await s.execute(stmt, {**base_params, **pc._roster_bind_params(whole_unit.market_ids, assignment)})
            ).all()
            whole_buckets: dict = {}
            whole_diag = pc._empty_horizon_diag()
            pc._fold_horizon_chunk_rows(whole_rows, whole_buckets, whole_diag)

            split_buckets: dict = {}
            split_diag = pc._empty_horizon_diag()
            for sub in (left_mids, right_mids):
                sub_rows = (
                    await s.execute(stmt, {**base_params, **pc._roster_bind_params(sub, assignment)})
                ).all()
                pc._fold_horizon_chunk_rows(sub_rows, split_buckets, split_diag)

            assert split_diag == whole_diag
            assert pc._finalize_horizon_result(split_buckets, split_diag) == pc._finalize_horizon_result(whole_buckets, whole_diag)
    finally:
        async with engine.begin() as conn:
            await conn.run_sync(lambda c: Base.metadata.drop_all(c, tables=pg14_safe_tables))
        await engine.dispose()


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
