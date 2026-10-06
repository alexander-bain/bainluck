"""Unmounted canonical-reader adapter. No scheduling, credentials or transport.

A dedicated physical connection owns the event serializer BEFORE opening the
repeatable-read snapshot. The first statement in that transaction belongs to the
canonical reader. A committed immutable projection receives a logical sequence;
replay never reads the game again or assigns an old reading a new sequence.
"""

import asyncio
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from sqlalchemy import insert, select, text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession
from app.models.activitykit import ActivityKitRegistration
from app.models.activitykit_observation import ActivityKitObservation
from app.utils.activitykit_payload import GameActivitySnapshot
from app.utils.activitykit_projection import project_activitykit_snapshot

OBS = ActivityKitObservation.__table__
REG = ActivityKitRegistration.__table__
LOCK_NAMESPACE = 10568


def _event_id(event_id):
    if type(event_id) is not int or not 0 < event_id < 2**31:
        raise ValueError("An integer event identity is required")


def encode_snapshot(snapshot: GameActivitySnapshot) -> dict:
    values = asdict(snapshot)
    for name in ("score_observed_at", "probability_observed_at"):
        clock = values[name]
        if clock is not None:
            values[name] = clock.astimezone(timezone.utc).isoformat()
    return {"schema": 1, "snapshot": values}


def decode_snapshot(value: dict) -> GameActivitySnapshot:
    try:
        if value["schema"] != 1:
            raise ValueError()
        values = dict(value["snapshot"])
        for name in ("score_observed_at", "probability_observed_at"):
            if values[name] is not None:
                values[name] = datetime.fromisoformat(values[name])
        return GameActivitySnapshot(**values)
    except (KeyError, TypeError, ValueError):
        raise ValueError("Invalid persisted ActivityKit observation") from None


@dataclass(frozen=True)
class Observation:
    sequence: int
    snapshot: GameActivitySnapshot


@dataclass(frozen=True)
class FanoutPage:
    attempted: int
    accepted: int
    next_cursor: str | None


async def _canonical_reader(db: AsyncSession, event_id: int) -> dict:
    # Route owner supplies this public seam; no private ContextVar manipulation.
    from app.routes.events import build_event_detail_uncoalesced

    return await build_event_detail_uncoalesced(db, event_id)


class ActivityKitObservationAdapter:
    def __init__(self, engine: AsyncEngine, *, reader=None, lock_timeout_ms=5000):
        if type(lock_timeout_ms) is not int or not 1 <= lock_timeout_ms <= 30000:
            raise ValueError("Lock timeout must be between 1 and 30000 milliseconds")
        self.engine = engine
        self.reader = reader or _canonical_reader
        self.lock_timeout_ms = lock_timeout_ms

    async def capture(self, event_id: int) -> Observation:
        _event_id(event_id)
        async with self.engine.connect() as conn:
            try:
                await conn.execution_options(isolation_level="AUTOCOMMIT")
                await conn.execute(
                    text(f"SET lock_timeout = '{self.lock_timeout_ms}ms'")
                )
                await conn.execute(
                    text("SELECT pg_advisory_lock(:namespace, :event)"),
                    {"namespace": LOCK_NAMESPACE, "event": event_id},
                )
                # Clear SQLAlchemy's logical autobegin, not the session lock.
                await conn.rollback()
                await conn.execution_options(isolation_level="REPEATABLE READ")
                async with conn.begin():
                    async with AsyncSession(
                        bind=conn, autoflush=False, expire_on_commit=False
                    ) as db:
                        detail = await self.reader(db, event_id)
                        snapshot = project_activitykit_snapshot(detail)
                        if snapshot.event_id != event_id:
                            raise ValueError(
                                "Canonical event identity changed; binding refused"
                            )
                        previous = (
                            await db.execute(
                                select(OBS.c.sequence)
                                .where(OBS.c.event_id == event_id)
                                .order_by(OBS.c.sequence.desc())
                                .limit(1)
                            )
                        ).scalar_one_or_none()
                        sequence = (previous or 0) + 1
                        await db.execute(
                            insert(OBS).values(
                                event_id=event_id,
                                sequence=sequence,
                                snapshot=encode_snapshot(snapshot),
                            )
                        )
                return Observation(sequence, snapshot)
            finally:
                # Never return a physical connection carrying a session lock to a
                # pool, including timeout, failed read and cancellation paths.
                # Destruction also resets lock_timeout. No external I/O runs here.
                cleanup = asyncio.create_task(conn.invalidate())
                try:
                    await asyncio.shield(cleanup)
                except asyncio.CancelledError:
                    await cleanup
                    raise

    async def replay(self, event_id: int, sequence: int) -> Observation:
        _event_id(event_id)
        if type(sequence) is not int or sequence <= 0:
            raise ValueError("A positive persisted sequence is required")
        async with self.engine.connect() as conn:
            value = (
                await conn.execute(
                    select(OBS.c.snapshot).where(
                        OBS.c.event_id == event_id, OBS.c.sequence == sequence
                    )
                )
            ).scalar_one()
        snapshot = decode_snapshot(value)
        if snapshot.event_id != event_id:
            raise ValueError("Persisted canonical identity mismatch")
        return Observation(sequence, snapshot)

    async def fanout(
        self,
        event_id: int,
        sequence: int,
        worker,
        *,
        now: datetime,
        after: str = "",
        limit: int = 100,
    ) -> FanoutPage:
        if type(limit) is not int or not 1 <= limit <= 100:
            raise ValueError("Fanout limit must be between 1 and 100")
        if (
            not isinstance(after, str)
            or not isinstance(now, datetime)
            or now.utcoffset() is None
        ):
            raise ValueError("Explicit cursor and aware authorization clock required")
        observation = await self.replay(event_id, sequence)
        async with self.engine.connect() as conn:
            ids = (
                (
                    await conn.execute(
                        select(REG.c.activity_id)
                        .where(
                            REG.c.event_id == event_id,
                            REG.c.activity_id > after,
                            REG.c.is_active.is_(True),
                            REG.c.push_token.is_not(None),
                            REG.c.created_at <= now,
                            REG.c.expires_at > now,
                        )
                        .order_by(REG.c.activity_id)
                        .limit(limit + 1)
                    )
                )
                .scalars()
                .all()
            )
        # The serializer and read connection are gone. The worker rechecks its
        # current horizon, binding, stop/final and token generation fences.
        accepted = 0
        for activity_id in ids[:limit]:
            accepted += bool(
                await worker.observe(
                    activity_id, observation.snapshot, revision=observation.sequence
                )
            )
        return FanoutPage(
            min(len(ids), limit), accepted, ids[limit - 1] if len(ids) > limit else None
        )
