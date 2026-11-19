"""Kickoff Live Activity push-to-start dispatcher (#13052 / 254-A / 178-B).

Queries live games pinned by at least one phone carrying `la_start_token`
(`push_devices`), builds APNs `event: "start"` pushes from the canonical event
detail projection, enforces once-per-(device, event) dedup, routes each device
to its `apns_env` (`production` or `sandbox`), and clears dead tokens on APNs 410.

No token or secret is ever logged or included in returned counters.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Awaitable, Callable, Protocol
from uuid import UUID

from sqlalchemy import exists, or_, select
from sqlalchemy.dialects.postgresql import array as pg_array
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.models.activitykit import ActivityKitRegistration
from app.models.models import Event, UserPin
from app.models.push_device import PushDevice
from app.services.activitykit_apns import APNsResult, ActivityKitAPNsTransport
from app.services.push_audience import StartTarget, forget_token, kickoff_plan
from app.utils.activitykit_delivery_state import DeliveryCommand
from app.utils.activitykit_payload import ActivityKitPayloadError
from app.utils.activitykit_projection import project_activitykit_snapshot
from app.utils.activitykit_start_payload import build_activitykit_start

_DEVICES = PushDevice.__table__
_PINS = UserPin.__table__
_REG = ActivityKitRegistration.__table__

#: Only consider live games whose scheduled start is within this window so an
#: old stuck-live row never fires phantom kickoff pushes days later.
KICKOFF_LOOKBACK = timedelta(hours=6)
#: Allow slight early-live transitions where a game goes live a few minutes before scheduled tip.
KICKOFF_LEAD = timedelta(minutes=15)
#: Once-per-(device, event) dedup TTL in Redis.
DEDUP_TTL_SECONDS = 24 * 3600
#: Maximum live candidate events scanned per 30 s beat.
MAX_EVENTS_PER_BEAT = 50


class StartDedupStore(Protocol):
    """Atomic once-per-(device, event) claim; releases only on transient APNs retry."""

    async def claim(self, event_id: int, device_id: UUID, ttl_seconds: int) -> bool: ...
    async def release(self, event_id: int, device_id: UUID) -> None: ...


class RedisStartDedupStore:
    """Bounded Redis NX+EX dedup backed by the shared process pool."""

    def __init__(self, client_factory=None) -> None:
        self._client_factory = client_factory

    def _client(self):
        if self._client_factory is not None:
            return self._client_factory()
        from app.tasks.redis_state import get_redis_client

        return get_redis_client()

    @staticmethod
    def key(event_id: int, device_id: UUID) -> str:
        return f"ak:start:{event_id}:{device_id}"

    async def claim(self, event_id: int, device_id: UUID, ttl_seconds: int) -> bool:
        k = self.key(event_id, device_id)

        def _set():
            return bool(self._client().set(k, "1", nx=True, ex=ttl_seconds))

        return await asyncio.to_thread(_set)

    async def release(self, event_id: int, device_id: UUID) -> None:
        k = self.key(event_id, device_id)

        def _del():
            self._client().delete(k)

        await asyncio.to_thread(_del)


class StartTransportFactory(Protocol):
    def for_env(self, apns_env: str) -> ActivityKitAPNsTransport: ...
    async def aclose(self) -> None: ...


class EnvAPNsTransportPool:
    """Lazily holds up to two HTTP/2 APNs transports: production and sandbox."""

    def __init__(self, bundle_id: str, timeout_seconds: float = 10.0) -> None:
        self._bundle_id = bundle_id
        self._timeout = timeout_seconds
        self._transports: dict[str, ActivityKitAPNsTransport] = {}

    def for_env(self, apns_env: str) -> ActivityKitAPNsTransport:
        env = "sandbox" if apns_env == "sandbox" else "production"
        transport = self._transports.get(env)
        if transport is None:
            transport = ActivityKitAPNsTransport(
                bundle_id=self._bundle_id,
                environment=env,
                timeout_seconds=self._timeout,
            )
            self._transports[env] = transport
        return transport

    async def aclose(self) -> None:
        for transport in self._transports.values():
            await transport.aclose()
        self._transports.clear()


@dataclass(frozen=True)
class StartDispatchSummary:
    events_scanned: int = 0
    attempted: int = 0
    accepted: int = 0
    skipped_dedup: int = 0
    skipped_active: int = 0
    token_forgotten: int = 0
    retryable: int = 0
    rejected: int = 0

    def as_dict(self) -> dict[str, int | str]:
        return {
            "status": "ok",
            "terminal": "ok",
            "events_scanned": self.events_scanned,
            "attempted": self.attempted,
            "accepted": self.accepted,
            "skipped_dedup": self.skipped_dedup,
            "skipped_active": self.skipped_active,
            "token_forgotten": self.token_forgotten,
            "retryable": self.retryable,
            "rejected": self.rejected,
        }


async def _canonical_detail_reader(db: AsyncSession, event_id: int) -> dict:
    from app.routes.events import build_event_detail_uncoalesced

    return await build_event_detail_uncoalesced(db, event_id)


def build_kickoff_event_ids_query(*, now: datetime, limit: int = MAX_EVENTS_PER_BEAT):
    """Build the bounded query for live events pinned by any push-to-start device."""
    window_start = now - KICKOFF_LOOKBACK
    window_end = now + KICKOFF_LEAD

    has_device_start_pin = exists(
        select(1).where(
            _DEVICES.c.la_start_token.is_not(None),
            _DEVICES.c.platform != "appclip",
            or_(
                _DEVICES.c.pinned_event_ids.contains(pg_array([Event.id])),
                exists(
                    select(1).where(
                        _DEVICES.c.user_id.is_not(None),
                        _PINS.c.user_id == _DEVICES.c.user_id,
                        _PINS.c.pin_type == "event",
                        _PINS.c.target_id == Event.id,
                    )
                ),
            ),
        )
    )
    return (
        select(Event.id)
        .where(
            Event.status == "live",
            Event.commence_time.is_not(None),
            Event.commence_time >= window_start,
            Event.commence_time <= window_end,
            has_device_start_pin,
        )
        .order_by(Event.commence_time.asc(), Event.id.asc())
        .limit(limit)
    )


async def find_kickoff_event_ids(
    db: AsyncSession, *, now: datetime, limit: int = MAX_EVENTS_PER_BEAT
) -> list[int]:
    """Return live event IDs within the kickoff window that at least one phone with
    `la_start_token` has pinned (directly on `push_devices` or via signed-in `user_pins`).
    """
    query = build_kickoff_event_ids_query(now=now, limit=limit)
    return list((await db.execute(query)).scalars().all())


async def _active_device_ids_for_event(
    db: AsyncSession, event_id: int, device_ids: list[UUID], *, now: datetime
) -> set[UUID]:
    """Devices that already hold an active Live Activity registration for this event."""
    if not device_ids:
        return set()
    rows = await db.execute(
        select(_REG.c.device_id).where(
            _REG.c.event_id == event_id,
            _REG.c.device_id.in_(device_ids),
            _REG.c.is_active.is_(True),
            _REG.c.expires_at > now,
        )
    )
    return {d for d in rows.scalars().all() if d is not None}


async def dispatch_kickoff_starts(
    sessions: async_sessionmaker[AsyncSession],
    transports: StartTransportFactory,
    provider_token: Callable[[], Awaitable[str]],
    dedup: StartDedupStore,
    *,
    now: datetime | None = None,
    min_app_version: str | None = "1.0.8",
    detail_reader: Callable[[AsyncSession, int], Awaitable[dict]] | None = None,
    candidate_finder: Callable[[AsyncSession, datetime], Awaitable[list[int]]] | None = None,
) -> StartDispatchSummary:
    """One bounded sweep of live pinned games that should auto-start Live Activities."""
    clock = now if now is not None else datetime.now(timezone.utc)
    if clock.utcoffset() is None:
        raise ValueError("An aware clock is required")
    clock = clock.astimezone(timezone.utc)

    reader = detail_reader or _canonical_detail_reader
    finder = candidate_finder or (lambda db, ts: find_kickoff_event_ids(db, now=ts))

    async with sessions() as db:
        event_ids = await finder(db, clock)

    if not event_ids:
        return StartDispatchSummary(events_scanned=0)

    attempted = accepted = skipped_dedup = skipped_active = 0
    token_forgotten = retryable = rejected = 0

    for event_id in event_ids:
        async with sessions() as db:
            # Page through every eligible StartTarget for this event.
            targets: list[StartTarget] = []
            cursor: UUID | None = None
            while True:
                plan = await kickoff_plan(
                    db,
                    event_id,
                    now=clock,
                    min_app_version=min_app_version,
                    after=cursor,
                )
                targets.extend(plan.start)
                if plan.next_after is None:
                    break
                cursor = plan.next_after

            if not targets:
                continue

            active_devices = await _active_device_ids_for_event(
                db, event_id, [t.device_id for t in targets], now=clock
            )
            detail = await reader(db, event_id)
            snapshot = project_activitykit_snapshot(detail)
            if snapshot.lifecycle != "live":
                continue

        # Send APNs start pushes outside the DB read transaction.
        jwt_token = await provider_token()
        for target in targets:
            if target.device_id in active_devices:
                skipped_active += 1
                continue
            claimed = await dedup.claim(event_id, target.device_id, DEDUP_TTL_SECONDS)
            if not claimed:
                skipped_dedup += 1
                continue

            try:
                push = build_activitykit_start(
                    snapshot,
                    sent_at=clock,
                    input_push_token=target.input_push_token,
                    priority="10",
                )
            except ActivityKitPayloadError:
                rejected += 1
                continue

            command = DeliveryCommand(
                command_id=f"start:{event_id}:{target.device_id}",
                # DeliveryCommand.kind only distinguishes non-terminal vs terminal/stop;
                # APNs reads `"event": "start"` from `push.body`.
                kind="update",
                push=push,
            )
            attempted += 1
            try:
                result: APNsResult = await transports.for_env(target.apns_env).send(
                    command,
                    activity_token=target.token,
                    provider_token=jwt_token,
                )
            except Exception:
                # Gotcha #42: isolate per-device transport failures and release the dedup
                # claim so later targets still dispatch and this device retries on next beat.
                retryable += 1
                await dedup.release(event_id, target.device_id)
                continue
            if result.outcome == "accepted":
                accepted += 1
            elif result.outcome == "unavailable":
                # APNs 410: token no longer registered on this phone.
                async with sessions() as db:
                    changed = await forget_token(db, "la_start_token", target.token)
                    await db.commit()
                    if changed:
                        token_forgotten += changed
            elif result.outcome == "retry":
                retryable += 1
                # Release dedup so the next 30 s beat retries this device cleanly.
                await dedup.release(event_id, target.device_id)
            else:
                rejected += 1

    return StartDispatchSummary(
        events_scanned=len(event_ids),
        attempted=attempted,
        accepted=accepted,
        skipped_dedup=skipped_dedup,
        skipped_active=skipped_active,
        token_forgotten=token_forgotten,
        retryable=retryable,
        rejected=rejected,
    )
