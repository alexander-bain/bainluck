"""Unmounted durable ActivityKit composition. No schedule or credential lookup.

Reservation commits before I/O. The send transaction reacquires registration then
state locks, fencing replacement/revocation against bounded transport execution.
A crash after APNs acceptance can repeat the identical command: at-least-once,
never a device-receipt or exactly-once guarantee.
"""

import asyncio
from dataclasses import dataclass, replace
from datetime import datetime, timedelta, timezone
from uuid import uuid4
from sqlalchemy import insert, select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.engine import RowMapping
from typing import Callable
from app.models.activitykit import ActivityKitRegistration
from app.models.activitykit_delivery import ActivityKitDelivery
from app.services.activitykit_apns import APNsResult
from app.services.activitykit_state_codec import encode_state, decode_state
from app.services.activitykit_registration_lifecycle import (
    horizon_open,
    erase_authorization,
)
from app.utils.activitykit_delivery_state import (
    Attempt,
    DeliveryState,
    RetryPolicy,
)
from app.utils.activitykit_payload import (
    GameActivitySnapshot,
)

_REG = ActivityKitRegistration.__table__
_DEL = ActivityKitDelivery.__table__


def _clock(value: datetime) -> datetime:
    if not isinstance(value, datetime) or value.utcoffset() is None:
        raise ValueError("An explicit aware clock is required")
    return value.astimezone(timezone.utc)


@dataclass(frozen=True)
class Reservation:
    activity_id: str
    lease_id: str
    registration_version: int
    token_hash: str
    attempt_id: str


def rebind_token(state: DeliveryState, *, token_changed: bool) -> DeliveryState:
    """A true token generation gets a bounded budget and the latest reading.

    Registration-version changes with the same token never replay accepted
    content or reset retry budgets. Config failures remain halted. Stops and
    completed ends cannot be resurrected by credential replacement.
    """
    if not token_changed or state.stopped or state.ended or state.snapshot is None:
        return state
    if state.halted not in {None, "unavailable", "retry_exhausted"}:
        return state
    return replace(
        state,
        attempt=None,
        halted=None,
        pending="terminal" if state.terminal_latched else "update",
    )


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

    async def _authorized(self, db, reg, *, now):
        if horizon_open(reg, now):
            return True
        if reg is not None:
            await erase_authorization(db, reg, now=now)
        return False

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
            now = _clock(self.clock())
            if not await self._authorized(db, reg, now=now):
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
            now = max(now, _clock(self.clock()))
            if not await self._authorized(db, reg, now=now) or row is None:
                return None
            state = self._state(reg, row)
            changed = (row["registration_version"], row["token_hash"]) != (
                reg["version"],
                reg["token_hash"],
            )
            state = rebind_token(
                state, token_changed=row["token_hash"] != reg["token_hash"]
            )
            state, attempt = reserve_state(
                state,
                now=now,
                lease_id=row["lease_id"],
                lease_expires_at=row["lease_expires_at"],
                owner_changed=changed,
            )
            lease = str(uuid4()) if attempt else (None if changed else row["lease_id"])
            expires = (
                min(
                    now + timedelta(seconds=self.lease_seconds),
                    _clock(reg["expires_at"]),
                )
                if attempt
                else (None if changed else row["lease_expires_at"])
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
            now = max(now, _clock(self.clock()))
            if not await self._authorized(db, reg, now=now) or row is None:
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
            dispatch_at = max(now, _clock(self.clock()))
            if not horizon_open(reg, dispatch_at):
                await erase_authorization(db, reg, now=dispatch_at)
                return "fenced"
            try:
                remaining = (_clock(reg["expires_at"]) - dispatch_at).total_seconds()
                async with asyncio.timeout(min(25, remaining)):
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
            if (
                completed_at >= _clock(reg["expires_at"])
                or result.reason == "token_unregistered"
                and result.outcome == "unavailable"
                or result.outcome == "accepted"
                and completed.ended
            ):
                await erase_authorization(db, reg, now=completed_at)
            return result.outcome
