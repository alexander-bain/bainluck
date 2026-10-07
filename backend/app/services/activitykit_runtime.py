"""Bounded composition for suspended-phone game updates (#10542).

No scheduler, credential discovery or implicit transport activation. The mounted
caller must serialize runs and persist the returned keyset cursor, including on
partial failure, so an unhealthy early registration cannot starve later ones.
The existing worker alone owns retries, leases, authorization and token fencing.
"""

import asyncio
from dataclasses import dataclass
from datetime import datetime, timezone
import math
import re

from sqlalchemy import select

from app.models.activitykit import ActivityKitRegistration
from app.services.activitykit_registration_lifecycle import cleanup_expired

REG = ActivityKitRegistration.__table__


@dataclass(frozen=True)
class RuntimePolicy:
    enabled: bool = False
    batch_size: int = 20
    cleanup_size: int = 100
    item_seconds: float = 30
    run_seconds: float = 120

    def __post_init__(self):
        if type(self.enabled) is not bool:
            raise ValueError("Explicit boolean activation required")
        for value, maximum in ((self.batch_size, 100), (self.cleanup_size, 1000)):
            if type(value) is not int or not 1 <= value <= maximum:
                raise ValueError("Invalid runtime batch bound")
        for value, maximum in ((self.item_seconds, 30), (self.run_seconds, 300)):
            if (
                type(value) not in (int, float)
                or not math.isfinite(value)
                or not 0 < value <= maximum
            ):
                raise ValueError("Invalid runtime time bound")


@dataclass
class RuntimeResult:
    status: str
    next_cursor: str
    scanned: int = 0
    observed: int = 0
    accepted: int = 0
    retry: int = 0
    unavailable: int = 0
    rejected: int = 0
    fenced: int = 0
    failed: int = 0
    cleaned: int = 0


def _now(clock):
    value = clock()
    if not isinstance(value, datetime) or value.utcoffset() is None:
        raise ValueError("Aware operational clock required")
    return value.astimezone(timezone.utc)


def _candidates(after, limit, now):
    # Read only identities, never tokens. The worker rechecks authorization after
    # acquiring its locks; enumeration cannot authorize a later send.
    return (
        select(REG.c.activity_id, REG.c.event_id)
        .where(
            REG.c.activity_id > after,
            REG.c.is_active.is_(True),
            REG.c.push_token.is_not(None),
            REG.c.token_hash.is_not(None),
            REG.c.created_at <= now,
            REG.c.expires_at > now,
        )
        .order_by(REG.c.activity_id)
        .limit(limit + 1)
    )


async def run_activitykit_page(
    sessions,
    adapter,
    worker,
    transport,
    provider_token,
    *,
    policy=RuntimePolicy(),
    after="",
    clock=lambda: datetime.now(timezone.utc),
):
    """Capture canonical readings and dispatch one finite, fair page.

    provider_token is an explicit async supplier of the approved provider JWT.
    Results contain only counts, a registration cursor and fixed classifications;
    credential-bearing transport/database exceptions never enter a result/log.
    An APNs 'accepted' result is not a device receipt. Caller owns transport close.
    """
    if not isinstance(after, str) or (
        after and not re.fullmatch(r"[A-Za-z0-9_-]{1,128}", after)
    ):
        raise ValueError("Invalid registration cursor")
    result = RuntimeResult("disabled", after)
    if not policy.enabled:
        return result
    result.status = "complete"
    rows = None
    phase = "cleanup"
    try:
        async with asyncio.timeout(policy.run_seconds):
            result.cleaned = await cleanup_expired(
                sessions, batch_size=policy.cleanup_size, clock=lambda: _now(clock)
            )
            phase = "configuration"
            token = await provider_token()
            if (
                not isinstance(token, str)
                or not re.fullmatch(
                    r"[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+", token
                )
                or len(token) > 4096
            ):
                raise ValueError("Invalid provider configuration")
            phase = "enumeration"
            async with sessions() as db:
                rows = (
                    (
                        await db.execute(
                            _candidates(after, policy.batch_size, _now(clock))
                        )
                    )
                    .mappings()
                    .all()
                )
            # Enumeration connection is released before capture or dispatch.
            observations = {}
            phase = "delivery"
            for row in rows[: policy.batch_size]:
                identity, event_id = row["activity_id"], row["event_id"]
                result.next_cursor = identity
                result.scanned += 1
                try:
                    async with asyncio.timeout(policy.item_seconds):
                        if event_id not in observations:
                            # Cache failure as well: one bad game cannot consume
                            # the page budget through repeated canonical reads.
                            observations[event_id] = None
                            observations[event_id] = await adapter.capture(event_id)
                        observation = observations[event_id]
                        if observation is None:
                            result.failed += 1
                            continue
                        if not await worker.observe(
                            identity,
                            observation.snapshot,
                            revision=observation.sequence,
                        ):
                            result.fenced += 1
                            continue
                        result.observed += 1
                        reservation = await worker.reserve(identity, now=_now(clock))
                        if reservation is None:
                            continue
                        outcome = await worker.send(
                            reservation,
                            transport,
                            provider_token=token,
                            now=_now(clock),
                        )
                        if outcome not in {
                            "accepted",
                            "retry",
                            "unavailable",
                            "rejected",
                            "fenced",
                        }:
                            raise ValueError("Invalid worker outcome")
                        setattr(result, outcome, getattr(result, outcome) + 1)
                except asyncio.CancelledError:
                    raise
                except Exception:
                    result.failed += 1
            # Empty cursor starts the next fair sweep, only after this page was
            # fully attempted. A partial timed-out page retains its last attempt.
            if len(rows) <= policy.batch_size:
                result.next_cursor = ""
            if result.failed:
                result.status = "partial_failure"
    except asyncio.CancelledError:
        raise
    except TimeoutError:
        result.status = "time_budget_exhausted"
        result.failed += 1
    except Exception:
        result.status = phase + "_failed"
        result.failed += 1
    return result
