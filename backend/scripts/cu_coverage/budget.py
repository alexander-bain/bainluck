"""Durable spend reservations alongside the standard shared LLM budget."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import date
from typing import Any
from uuid import uuid4

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.durable_snapshots import publish_cas_snapshot_in_txn, read_snapshot
from app.utils.durable_state import DurableEnvelope

from .store import JOURNAL_MAX_AGE_SECONDS, RUN_ID, _read_undo

SCHEMA = "cu-coverage-spend-v1"
BUDGET_ID = f"{RUN_ID}:spend"
PRIOR_SPEND_MICROS = 477_413  # Nov 24 pilot plus the three posted replays, rounded up.
RUN_LIMIT_MICROS = 50_000_000 - PRIOR_SPEND_MICROS
DAY_LIMIT_MICROS = 4_000_000
SHARED_RESERVE_MICROS = 6_000_000
ELEVATED_DAY_LIMIT_MICROS = 25_000_000
ELEVATED_SHARED_MICROS = 40_000_000
UNCLEAR_LIMIT_MICROS = 1_000_000
LOCK_TIMEOUT_MARKET = 71935916
LOCK_TIMEOUT_RESERVATION_MICROS = 1_652
MAX_IN_FLIGHT = 4

_LOCK_BUDGET = text(
    "SELECT identity FROM durable_state_snapshots WHERE identity = :identity FOR UPDATE"
)


@dataclass(frozen=True)
class Reservation:
    market_id: int
    utc_day: str
    model: str
    prompt_sha256: str
    reserved_micros: int
    token: str = field(default_factory=lambda: uuid4().hex)


class CoverageBudgetError(RuntimeError):
    pass


class CoverageBudgetStopped(CoverageBudgetError):
    pass


class CoverageJournalWriteError(CoverageBudgetError):
    """The snapshot write failed before we could confirm its outcome."""


def attempt_identity(market_id: int) -> str:
    return f"{RUN_ID}:attempt:{market_id}"


async def _load(db: AsyncSession, identity: str) -> DurableEnvelope | None:
    result = await read_snapshot(
        db, identity, expected_version=SCHEMA, max_age_s=JOURNAL_MAX_AGE_SECONDS
    )
    if result.missing:
        return None
    if not result.ok or result.envelope is None:
        raise CoverageBudgetError(f"spend journal {identity}: {result.status}")
    return result.envelope


async def _stage(
    db: AsyncSession, identity: str, payload: dict[str, Any], generation: int | None
) -> None:
    envelope = DurableEnvelope.build(
        identity=identity,
        schema_version=SCHEMA,
        generation=1 if generation is None else generation + 1,
        payload=payload,
        source=RUN_ID,
    )
    result = await publish_cas_snapshot_in_txn(
        db, envelope, expected_generation=generation
    )
    if result.get("status") == "error":
        raise CoverageJournalWriteError(f"could not write spend journal {identity}")
    if result.get("status") != "ok":
        raise CoverageBudgetError(f"could not stage spend journal {identity}")


async def _locked_budget(
    db: AsyncSession, manifest_sha256: str
) -> DurableEnvelope | None:
    await db.execute(text("SET LOCAL statement_timeout = '5s'"))
    await db.execute(text("SET LOCAL lock_timeout = '250ms'"))
    await db.execute(_LOCK_BUDGET, {"identity": BUDGET_ID})
    record = await _load(db, BUDGET_ID)
    if record is not None and record.payload["manifest_sha256"] != manifest_sha256:
        raise CoverageBudgetError("a different roster already owns this run")
    return record


async def initialize(
    db: AsyncSession,
    *,
    manifest_sha256: str,
    model: str,
    pilot_sha256: str | None = None,
) -> dict[str, Any]:
    """Initialize or resume the same frozen roster and model."""
    async with db.begin():
        record = await _locked_budget(db, manifest_sha256)
        if record is not None:
            totals = record.payload
            if totals["model"] != model:
                raise CoverageBudgetStopped("the pinned model changed")
            if totals.get("pilot_sha256") != pilot_sha256:
                raise CoverageBudgetStopped("the pinned pilot sample changed")
            if totals["in_flight"] or totals["uncertain"]:
                raise CoverageBudgetStopped(
                    "an earlier provider request needs reconciliation"
                )
            return totals
        totals = {
            "manifest_sha256": manifest_sha256,
            "model": model,
            "pilot_sha256": pilot_sha256,
            "held_micros": 0,
            "spent_micros": 0,
            "retained_micros": 0,
            "days": {},
            "in_flight": 0,
            "uncertain": 0,
        }
        await _stage(db, BUDGET_ID, totals, None)
        return totals


async def reserve(
    db: AsyncSession,
    *,
    manifest_sha256: str,
    reservation: Reservation,
    shared_daily_micros: int,
    use_elevated_cap: bool = False,
) -> None:
    """Bank a conservative provider reservation before the request leaves."""
    if (
        date.fromisoformat(reservation.utc_day).isoformat() != reservation.utc_day
        or reservation.reserved_micros <= 0
    ):
        raise CoverageBudgetError("invalid reservation")
    daily_cap = daily_coverage_micros(
        shared_daily_micros, use_elevated_cap=use_elevated_cap
    )
    identity = attempt_identity(reservation.market_id)
    expected = asdict(reservation) | {"status": "in_flight"}
    async with db.begin():
        record = await _locked_budget(db, manifest_sha256)
        if record is None:
            raise CoverageBudgetError("spend journal has not been initialized")
        totals = record.payload
        if totals["model"] != reservation.model:
            raise CoverageBudgetStopped("the pinned model changed")
        old = await _load(db, identity)
        if old is not None and old.payload == expected:
            return
        if totals["uncertain"] or totals["in_flight"] >= MAX_IN_FLIGHT:
            raise CoverageBudgetStopped("there is no reconciled provider slot")
        if old is not None and old.payload["status"] not in {"refused", "abandoned"}:
            raise CoverageBudgetStopped(
                f"market {reservation.market_id} already has an attempt"
            )
        amount = reservation.reserved_micros
        day_amount = totals["days"].get(reservation.utc_day, 0)
        if day_amount + amount > daily_cap:
            raise CoverageBudgetStopped("coverage daily budget exhausted")
        if totals["held_micros"] + amount > RUN_LIMIT_MICROS:
            raise CoverageBudgetStopped("coverage run budget exhausted")

        totals["days"][reservation.utc_day] = day_amount + amount
        totals["held_micros"] += amount
        totals["in_flight"] += 1
        await _stage(
            db,
            identity,
            expected,
            old.generation if old is not None else None,
        )
        await _stage(db, BUDGET_ID, totals, record.generation)


def daily_coverage_micros(shared_daily_micros: int, *, use_elevated_cap: bool) -> int:
    cap = (
        ELEVATED_DAY_LIMIT_MICROS
        if (use_elevated_cap and shared_daily_micros == ELEVATED_SHARED_MICROS)
        else DAY_LIMIT_MICROS
    )
    return min(cap, shared_daily_micros - SHARED_RESERVE_MICROS)


async def settle(
    db: AsyncSession,
    *,
    manifest_sha256: str,
    reservation: Reservation,
    actual_micros: int | None,
    content: str | None = None,
    refused: bool = False,
    provider_response_id: str | None = None,
) -> dict[str, Any]:
    """Account for a paid answer, or retain its full reservation if uncertain."""
    if refused and (actual_micros != 0 or content is not None):
        raise CoverageBudgetError("a refused request must carry no response")
    if actual_micros is not None and actual_micros < 0:
        raise CoverageBudgetError("negative billed cost")
    identity = attempt_identity(reservation.market_id)
    retained = 0
    billed = actual_micros
    if (
        actual_micros is None
        and content is not None
        and (reservation.reserved_micros < UNCLEAR_LIMIT_MICROS)
    ):
        retained = billed = reservation.reserved_micros
    status = "refused" if refused else "charged"
    if billed is None:
        status = "uncertain"
    elif billed > reservation.reserved_micros:
        status = "over_reservation"
    expected = asdict(reservation) | {"status": "in_flight"}
    settled = expected | {
        "status": status,
        "billed_micros": actual_micros,
        "content": content,
        "provider_response_id": provider_response_id,
        "retained_micros": retained,
    }
    async with db.begin():
        record = await _locked_budget(db, manifest_sha256)
        attempt = await _load(db, identity)
        if record is None or attempt is None:
            raise CoverageBudgetError("provider response has no matching reservation")
        totals = record.payload
        if attempt.payload == settled:
            return totals
        if attempt.payload != expected:
            raise CoverageBudgetError("provider response has no matching reservation")
        totals["in_flight"] -= 1
        if status in {"uncertain", "over_reservation"}:
            totals["uncertain"] += 1
        if billed is not None:
            delta = billed - reservation.reserved_micros
            totals["held_micros"] += delta
            totals["days"][reservation.utc_day] += delta
            totals["spent_micros"] += billed
            totals["retained_micros"] = totals.get("retained_micros", 0) + retained
        await _stage(db, identity, settled, attempt.generation)
        await _stage(db, BUDGET_ID, totals, record.generation)
        return totals


async def recover_stopped_attempts(
    db: AsyncSession,
    *,
    manifest_sha256: str,
    market_ids: list[int],
) -> None:
    """Account for unanswered requests after their worker exited."""
    async with db.begin():
        record = await _locked_budget(db, manifest_sha256)
        if record is None:
            raise CoverageBudgetError("the stopped worker's spend journal is missing")
        totals = record.payload
        unresolved = {"in_flight": 0, "uncertain": 0}
        recovered = []
        for market_id in sorted(set(market_ids)):
            attempt = await _load(db, attempt_identity(market_id))
            if attempt is None or attempt.payload["status"] not in unresolved:
                continue
            if await _read_undo(db, market_id) is not None:
                raise CoverageBudgetError(
                    "an unfinished reservation already has a written profile"
                )
            amount = attempt.payload["reserved_micros"]
            if not 0 < amount < UNCLEAR_LIMIT_MICROS:
                raise CoverageBudgetStopped("unreconciled reservation is at least $1")
            audit_identity = f"{attempt.identity}:retained:{attempt.generation}"
            if market_id == LOCK_TIMEOUT_MARKET:
                audit_identity = f"{attempt.identity}:retained:first"
                if amount != LOCK_TIMEOUT_RESERVATION_MICROS or await _load(
                    db, audit_identity
                ):
                    raise CoverageBudgetStopped(
                        "the approved retry for 71935916 has been used"
                    )
            if attempt.payload.get("content"):
                raise CoverageBudgetError("the stopped attempt has a saved answer")
            unresolved[attempt.payload["status"]] += 1
            recovered.append((attempt, audit_identity, amount))
        if any(totals[key] != count for key, count in unresolved.items()):
            raise CoverageBudgetError(
                "the stopped worker's receipt misses an open reservation"
            )
        for attempt, audit_identity, amount in recovered:
            await _stage(db, audit_identity, attempt.payload, None)
            await _stage(
                db,
                attempt.identity,
                attempt.payload | {"status": "abandoned"},
                attempt.generation,
            )
            totals["spent_micros"] += amount
            totals["retained_micros"] = totals.get("retained_micros", 0) + amount
        if recovered:
            totals.update(in_flight=0, uncertain=0)
            await _stage(db, BUDGET_ID, totals, record.generation)


async def read_attempt(db: AsyncSession, market_id: int) -> dict[str, Any] | None:
    record = await _load(db, attempt_identity(market_id))
    return None if record is None else record.payload
