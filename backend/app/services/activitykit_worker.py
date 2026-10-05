"""Unmounted durable ActivityKit composition. No schedule or credential lookup.

Reservation commits before I/O. The send transaction reacquires registration then
state locks, fencing replacement/revocation against bounded transport execution.
A crash after APNs acceptance can repeat the identical command: at-least-once,
never a device-receipt or exactly-once guarantee.
"""

import asyncio
import base64
from dataclasses import asdict, dataclass, replace
from datetime import datetime, timedelta, timezone
from uuid import uuid4
from sqlalchemy import insert, select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.engine import RowMapping
from typing import Callable
from app.models.activitykit import ActivityKitRegistration
from app.models.activitykit_delivery import ActivityKitDelivery
from app.services.activitykit_apns import APNsResult
from app.utils.activitykit_delivery_state import (
    Attempt,
    DeliveryCommand,
    DeliveryState,
    RetryPolicy,
)
from app.utils.activitykit_payload import (
    ActivityKitPush,
    GameActivitySnapshot,
    MAX_PAYLOAD_BYTES,
)

_REG = ActivityKitRegistration.__table__
_DEL = ActivityKitDelivery.__table__


def _clock(value: datetime) -> datetime:
    if not isinstance(value, datetime) or value.utcoffset() is None:
        raise ValueError("An explicit aware clock is required")
    return value.astimezone(timezone.utc)


def encode_state(state: DeliveryState) -> dict:
    def encode(value):
        if isinstance(value, datetime):
            return _clock(value).isoformat()
        if isinstance(value, timedelta):
            return value.total_seconds()
        if isinstance(value, bytes):
            return base64.b64encode(value).decode("ascii")
        if isinstance(value, dict):
            return {k: encode(v) for k, v in value.items()}
        if isinstance(value, (list, tuple)):
            return [encode(v) for v in value]
        return value

    return {"schema": 1, "state": encode(asdict(state))}


def decode_state(value: dict) -> DeliveryState:
    try:
        if value["schema"] != 1:
            raise ValueError()
        data = dict(value["state"])

        def date(value):
            return _clock(datetime.fromisoformat(value)) if value is not None else None

        data["retry_policy"] = RetryPolicy(
            tuple(timedelta(seconds=v) for v in data["retry_policy"]["delays"])
        )
        for name in ("score_fence", "probability_fence"):
            data[name] = date(data[name])
        if data["snapshot"] is not None:
            snapshot = dict(data["snapshot"])
            for name in ("score_observed_at", "probability_observed_at"):
                snapshot[name] = date(snapshot[name])
            data["snapshot"] = GameActivitySnapshot(**snapshot)
        if data["attempt"] is not None:
            attempt = dict(data["attempt"])
            command = dict(attempt["command"])
            body = base64.b64decode(command["push"]["body"], validate=True)
            if not 0 < len(body) <= MAX_PAYLOAD_BYTES:
                raise ValueError()
            command["push"] = ActivityKitPush(body)
            attempt["command"] = DeliveryCommand(**command)
            attempt["retry_at"] = date(attempt["retry_at"])
            data["attempt"] = Attempt(**attempt)
        return DeliveryState(**data)
    except (KeyError, TypeError, ValueError, OverflowError):
        raise ValueError("Invalid persisted ActivityKit state") from None


@dataclass(frozen=True)
class Reservation:
    activity_id: str
    lease_id: str
    registration_version: int
    token_hash: str
    attempt_id: str


def reserve_state(
    state: DeliveryState,
    *,
    now: datetime,
    lease_id: str | None,
    lease_expires_at: datetime | None,
    owner_changed: bool
) -> tuple[DeliveryState, Attempt | None]:
    """Recover a crashed reservation without fabricating new payload clocks."""
    now = _clock(now)
    if lease_id and not owner_changed and now < _clock(lease_expires_at):
        return state, None
    if state.attempt and state.attempt.in_flight:
        if state.pending is not None:
            state = replace(state, attempt=None)
        else:
            # Recovery consumes the existing finite retry budget.
            if state.attempt.count > len(state.retry_policy.delays):
                return replace(state, attempt=None, halted="retry_exhausted"), None
            state = replace(
                state, attempt=replace(state.attempt, in_flight=False, retry_at=now)
            )
    return state.dispatch(now=now)


class DurableActivityKitWorker:
    def __init__(
        self,
        sessions: async_sessionmaker[AsyncSession],
        *,
        retry_policy: RetryPolicy,
        lease_seconds: int = 60,
        clock: Callable[[], datetime] = lambda: datetime.now(timezone.utc)
    ):
        if type(lease_seconds) is not int or not 30 <= lease_seconds <= 300:
            raise ValueError("Lease must be between 30 and 300 seconds")
        self.sessions = sessions
        self.retry_policy = retry_policy
        self.lease_seconds = lease_seconds
        self.clock = clock

    async def _locked(self, db: AsyncSession, activity_id: str):
        # Fixed lock order also serializes first-row creation and token mutations.
        reg = (
            (
                await db.execute(
                    select(_REG)
                    .where(_REG.c.activity_id == activity_id)
                    .with_for_update()
                )
            )
            .mappings()
            .one_or_none()
        )
        row = (
            (
                await db.execute(
                    select(_DEL)
                    .where(_DEL.c.activity_id == activity_id)
                    .with_for_update()
                )
            )
            .mappings()
            .one_or_none()
        )
        return reg, row

    @staticmethod
    def _active(reg: RowMapping | None) -> bool:
        return (
            reg is not None
            and reg["is_active"]
            and reg["push_token"]
            and reg["token_hash"]
        )

    @staticmethod
    def _state(reg: RowMapping, row: RowMapping) -> DeliveryState:
        state = decode_state(row["state"])
        if (state.activity_id, state.event_id) != (reg["activity_id"], reg["event_id"]):
            raise ValueError("Persisted activity identity mismatch")
        return state

    async def observe(
        self,
        activity_id,
        snapshot: GameActivitySnapshot,
        *,
        revision: int,
        stop: bool = False
    ):
        async with self.sessions() as db, db.begin():
            reg, row = await self._locked(db, activity_id)
            if not self._active(reg):
                return False
            state = (
                self._state(reg, row)
                if row
                else DeliveryState(activity_id, reg["event_id"], self.retry_policy)
            )
            state = state.observe(snapshot, revision=revision)
            if stop:
                state = state.stop()
            values = {"state": encode_state(state)}
            if row:
                await db.execute(
                    update(_DEL)
                    .where(_DEL.c.activity_id == activity_id)
                    .values(**values)
                )
            else:
                await db.execute(
                    insert(_DEL).values(
                        activity_id=activity_id,
                        registration_version=reg["version"],
                        token_hash=reg["token_hash"],
                        **values
                    )
                )
            return True

    async def reserve(self, activity_id: str, *, now: datetime) -> Reservation | None:
        now = _clock(now)
        async with self.sessions() as db, db.begin():
            reg, row = await self._locked(db, activity_id)
            if not self._active(reg) or row is None:
                return None
            state = self._state(reg, row)
            changed = (row["registration_version"], row["token_hash"]) != (
                reg["version"],
                reg["token_hash"],
            )
            state, attempt = reserve_state(
                state,
                now=now,
                lease_id=row["lease_id"],
                lease_expires_at=row["lease_expires_at"],
                owner_changed=changed,
            )
            lease = str(uuid4()) if attempt else row["lease_id"]
            expires = (
                now + timedelta(seconds=self.lease_seconds)
                if attempt
                else row["lease_expires_at"]
            )
            await db.execute(
                update(_DEL)
                .where(_DEL.c.activity_id == activity_id)
                .values(
                    state=encode_state(state),
                    registration_version=reg["version"],
                    token_hash=reg["token_hash"],
                    lease_id=lease,
                    lease_expires_at=expires,
                )
            )
            if attempt:
                return Reservation(
                    activity_id,
                    lease,
                    reg["version"],
                    reg["token_hash"],
                    attempt.attempt_id,
                )
            return None

    async def send(
        self, reservation: Reservation, transport, *, provider_token: str, now: datetime
    ) -> str:
        """Explicit mocked/approved caller only; no transport or credentials created here."""
        now = _clock(now)
        async with self.sessions() as db, db.begin():
            reg, row = await self._locked(db, reservation.activity_id)
            if not self._active(reg) or row is None:
                return "fenced"
            if (reg["version"], reg["token_hash"], row["lease_id"]) != (
                reservation.registration_version,
                reservation.token_hash,
                reservation.lease_id,
            ):
                return "fenced"
            if now >= _clock(row["lease_expires_at"]):
                return "fenced"
            state = self._state(reg, row)
            if (
                not state.attempt
                or state.attempt.attempt_id != reservation.attempt_id
                or not state.attempt.in_flight
            ):
                return "fenced"
            if state.pending in {"terminal", "stop"} and state.attempt.kind == "update":
                await db.execute(
                    update(_DEL)
                    .where(_DEL.c.activity_id == reservation.activity_id)
                    .values(
                        state=encode_state(replace(state, attempt=None)),
                        lease_id=None,
                        lease_expires_at=None,
                    )
                )
                return "fenced"
            try:
                async with asyncio.timeout(25):
                    result = await transport.send(
                        state.attempt.command,
                        activity_token=reg["push_token"],
                        provider_token=provider_token,
                    )
            except Exception:
                # Transport exceptions can contain credentials; preserve only a
                # fixed classification and the finite retry budget.
                result = APNsResult("retry", "transport_failure")
            if not isinstance(result, APNsResult):
                result = APNsResult("rejected", "invalid_transport_result")
            completed_at = max(now, _clock(self.clock()))
            failure = {
                "accepted": None,
                "retry": "transient",
                "unavailable": "unavailable",
                "rejected": "permanent",
            }[result.outcome]
            completed = state.complete(
                reservation.attempt_id, now=completed_at, failure=failure
            )
            if (
                result.outcome == "retry"
                and completed.attempt
                and not completed.attempt.in_flight
            ):
                retry_at = completed.attempt.retry_at
                if result.retry_at:
                    retry_at = max(retry_at, _clock(result.retry_at))
                if result.retry_after_seconds is not None:
                    retry_at = max(
                        retry_at,
                        completed_at + timedelta(seconds=result.retry_after_seconds),
                    )
                completed = replace(
                    completed, attempt=replace(completed.attempt, retry_at=retry_at)
                )
            await db.execute(
                update(_DEL)
                .where(_DEL.c.activity_id == reservation.activity_id)
                .values(
                    state=encode_state(completed), lease_id=None, lease_expires_at=None
                )
            )
            return result.outcome
