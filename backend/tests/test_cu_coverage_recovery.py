"""#1809 charges for an unfinished retry only and preserves all-in limits."""

import hashlib
import json
from contextlib import asynccontextmanager
from copy import deepcopy
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
from sqlalchemy.exc import DBAPIError

from scripts.cu_coverage import budget, frozen, store, worker


def test_paid_run_limits():
    assert budget.RUN_LIMIT_MICROS + budget.PRIOR_SPEND_MICROS == 50_000_000
    assert budget.daily_coverage_micros(10_000_000, use_elevated_cap=False) == 4_000_000
    assert budget.daily_coverage_micros(10_000_000, use_elevated_cap=True) == 4_000_000
    assert budget.daily_coverage_micros(40_000_000, use_elevated_cap=False) == 4_000_000
    assert budget.daily_coverage_micros(40_000_000, use_elevated_cap=True) == 25_000_000


def test_frozen_roster_checks_later_blocks(monkeypatch):
    ids = list(range(1001, 2001))
    digest = hashlib.sha256("".join(f"{mid}\n" for mid in ids).encode()).hexdigest()
    monkeypatch.setattr(frozen, "BLOCK_SHA256", (frozen.PILOT_SHA256, digest))
    assert frozen.approved_block(1000, 1834, ids)
    assert not frozen.approved_block(1000, 2001, ids)
    assert not frozen.approved_block(1000, 1834, ids[::-1])


@pytest.fixture
def journal(monkeypatch):
    entries = {}
    undo = {}

    class Session:
        @asynccontextmanager
        async def begin(self):
            yield

    async def load(_db, identity):
        return deepcopy(entries.get(identity))

    async def locked(db, manifest_sha256):
        record = await load(db, budget.BUDGET_ID)
        if record is not None:
            assert record.payload["manifest_sha256"] == manifest_sha256
        return record

    async def stage(_db, identity, payload, generation):
        old = entries.get(identity)
        assert (None if old is None else old.generation) == generation
        entries[identity] = SimpleNamespace(
            identity=identity,
            generation=(generation or 0) + 1,
            payload=deepcopy(payload),
        )

    async def read_undo(_db, market_id):
        return undo.get(market_id)

    @asynccontextmanager
    async def session_scope(**kwargs):
        yield Session()

    monkeypatch.setattr(budget, "_locked_budget", locked)
    monkeypatch.setattr(budget, "_load", load)
    monkeypatch.setattr(budget, "_stage", stage)
    monkeypatch.setattr(budget, "_read_undo", read_undo)
    monkeypatch.setattr(worker, "get_task_session", session_scope)
    return SimpleNamespace(entries=entries, undo=undo, session=Session())


def _today():
    return datetime.now(timezone.utc).date().isoformat()


async def test_recover_567_and_retry_settlement_without_buying_twice(
    journal, monkeypatch
):
    failed_market = budget.LOCK_TIMEOUT_MARKET
    previous_ids = list(range(1, 568))
    day = _today()
    db = journal.session
    await budget._stage(
        db,
        budget.BUDGET_ID,
        {
            "manifest_sha256": frozen.ROSTER_SHA256,
            "pilot_sha256": frozen.PILOT_SHA256,
            "model": worker.MODEL,
            "held_micros": 267_842,
            "spent_micros": 266_190,
            "days": {day: 267_842},
            "in_flight": 1,
            "uncertain": 0,
        },
        None,
    )
    await budget._stage(
        db,
        budget.attempt_identity(failed_market),
        {
            "market_id": failed_market,
            "utc_day": day,
            "model": worker.MODEL,
            "prompt_sha256": "a" * 64,
            "reserved_micros": 1_652,
            "status": "in_flight",
        },
        None,
    )
    raw_profile = '{"topic":"weather"}'
    for mid in previous_ids:
        journal.undo[mid] = {"written_sha256": store.profile_hash(raw_profile)}

    async def read_market(_engine, mid):
        before_image = journal.undo.get(mid)
        row = {
            "id": mid,
            "name": "Will it rain 10 inches?",
            "source": "kalshi",
            "status": "open",
            "resolution_date": None,
            "category": "weather",
            "outcomes": [],
            "profile_json": raw_profile if before_image else None,
        }
        return row, before_image, await budget.read_attempt(db, mid)

    calls = 0

    def complete(*args, **kwargs):
        nonlocal calls
        assert kwargs["max_retries"] == 0
        calls += 1
        return SimpleNamespace(
            model=worker.MODEL,
            cost_usd=0.0004,
            response=SimpleNamespace(
                id="test-completion",
                choices=[
                    SimpleNamespace(message=SimpleNamespace(content=raw_profile)),
                ],
            ),
        )

    async def build_profile(_engine, row, content, *_args):
        assert row["id"] == failed_market and content == raw_profile
        return json.loads(content)

    async def write_profile(_db, mid, **_kwargs):
        assert mid not in journal.undo
        journal.undo[mid] = {"written_sha256": store.profile_hash(raw_profile)}
        return "written"

    settle = budget.settle
    attempts = 0

    class LockTimeout(Exception):
        sqlstate = "55P03"

    async def settle_with_faults(db, **kwargs):
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise DBAPIError("lock spend row", {}, LockTimeout())
        totals = await settle(db, **kwargs)
        if attempts == 2:
            raise budget.CoverageJournalWriteError(
                "the commit acknowledgement was lost"
            )
        return totals

    monkeypatch.setattr(worker, "read_market", read_market)
    monkeypatch.setattr(worker, "complete_chat_detailed", complete)
    monkeypatch.setattr(worker, "build_profile", build_profile)
    monkeypatch.setattr(worker, "daily_budget_micros", lambda: 10_000_000)
    monkeypatch.setattr(store, "write_profile", write_profile)
    monkeypatch.setattr(budget, "settle", settle_with_faults)
    payload = {
        "manifest_sha256": frozen.ROSTER_SHA256,
        "pilot_sha256": frozen.PILOT_SHA256,
        "model": worker.MODEL,
        "start": 0,
        "end": 568,
        "roster_ids": [*previous_ids[:564], failed_market, *previous_ids[564:]],
        "sample_seed": "fixture",
        "sample_cutoff": None,
        "excluded_sample_ids": [],
        "recover_failed_ids": [failed_market],
    }
    report = await worker.run_chunk(payload, object(), object())
    repeat = await worker.run_chunk(payload, object(), object())
    assert attempts == 3 and calls == 1
    assert report["counts"] == {"already_written": 567, "written": 1}
    assert repeat["counts"] == {"already_written": 568}
    assert report["actual_usd"] == repeat["actual_usd"] == 0.268242
    assert report["retained_usd"] == repeat["retained_usd"] == 0.001652
    assert report["in_flight"] == report["uncertain"] == 0
    assert len(journal.undo) == 568


async def test_unknown_cost_with_saved_answer_retains_reserve(journal):
    db = journal.session
    digest = "b" * 64
    reservation = budget.Reservation(5, _today(), worker.MODEL, digest, 1200)
    await budget.initialize(db, manifest_sha256=digest, model=worker.MODEL)
    await budget.reserve(
        db,
        manifest_sha256=digest,
        reservation=reservation,
        shared_daily_micros=10_000_000,
    )
    result = await budget.settle(
        db,
        manifest_sha256=digest,
        reservation=reservation,
        actual_micros=None,
        content='{"topic":"weather"}',
    )
    assert (
        result["held_micros"]
        == result["spent_micros"]
        == result["retained_micros"]
        == 1200
    )
    assert result["in_flight"] == result["uncertain"] == 0
    assert (await budget.read_attempt(db, 5))["status"] == "charged"


async def test_reservation_cannot_pass_all_in_guardrail(journal):
    db = journal.session
    digest = "b" * 64
    await budget.initialize(db, manifest_sha256=digest, model=worker.MODEL)
    record = journal.entries[budget.BUDGET_ID]
    record.payload["held_micros"] = budget.RUN_LIMIT_MICROS - 100
    reservation = budget.Reservation(5, _today(), worker.MODEL, digest, 101)
    with pytest.raises(
        budget.CoverageBudgetStopped, match="coverage run budget exhausted"
    ):
        await budget.reserve(
            db,
            manifest_sha256=digest,
            reservation=reservation,
            shared_daily_micros=10_000_000,
        )
    assert budget.attempt_identity(5) not in journal.entries
