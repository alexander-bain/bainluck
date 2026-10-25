"""#10090: durable, explicit DNPL incarnation allocation, never a Redis reseed.

All calls use the primary session factory supplied by the caller. There is no
runtime INSERT, implicit bootstrap, retry, global engine or startup hook here.
The migration alone seeds disabled incarnation 0, which cannot appear on wire.

prepare commits an allocation before returning. Failed/abandoned allocations
are burned. ready and disable compare the entire exact record. Neither Redis
readback nor a prepared candidate alone gives permission to publish or start.

Cancellation or a commit error may have written: resolve with read() and exact
candidate equality, never replay a mutation automatically. A write helper never
returns success before its transaction context has successfully committed.
"""

from __future__ import annotations

import asyncio
from dataclasses import asdict, dataclass, replace
from datetime import datetime
import re
from typing import Callable
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

MAX_INCARNATION = 9007199254740991
CONTROL_BUDGET_S = 0.150
_REDIS_ID = re.compile(r"[0-9a-f]{40}\Z")
_FIELDS = (
    "protocol",
    "incarnation",
    "namespace",
    "operation_id",
    "state",
    "redis_run_id",
    "redis_master_replid",
    "policy_fingerprint",
)
_COLUMNS = ", ".join(_FIELDS)
_MATCH = " AND ".join(f"{key} = :old_{key}" for key in _FIELDS)
_READ = text(f"SELECT {_COLUMNS} FROM dnpl_authority WHERE id = 1")
_READ_PRODUCER = text(
    f"SELECT {_COLUMNS}, clock_timestamp() AS sampled_at FROM dnpl_authority WHERE id = 1"
)
_RETIREMENT = text(f"SELECT {_COLUMNS} FROM dnpl_namespace_retirement WHERE id = 1")
_RECORD_RETIREMENT = text(
    f"INSERT INTO dnpl_namespace_retirement (id, {_COLUMNS}) VALUES (1, "
    + ", ".join(f":old_{key}" for key in _FIELDS)
    + ")"
)
_CLEAR_RETIREMENT = text(
    f"DELETE FROM dnpl_namespace_retirement WHERE id = 1 AND {_MATCH} RETURNING id"
)
_CAS = text(
    "UPDATE dnpl_authority SET "
    + ", ".join(f"{key} = :new_{key}" for key in _FIELDS)
    + ", activation_step = CASE WHEN :new_incarnation <> :old_incarnation THEN 0 ELSE activation_step END"
    + ", activation_bootstrap = CASE WHEN :new_incarnation <> :old_incarnation THEN "
    + ":allow_bootstrap ELSE activation_bootstrap END"
    + f" WHERE id = 1 AND {_MATCH} RETURNING {_COLUMNS}"
)


class AuthorityLost(RuntimeError):
    """The mandatory durable row is absent; runtime must not bootstrap it."""


class AuthorityConflict(RuntimeError):
    """Exact CAS missed; read current authority without repeating the write."""


class AuthorityWriteUncertain(RuntimeError):
    """A database/commit/timeout error is not evidence that no write occurred."""


@dataclass(frozen=True)
class Authority:
    protocol: int
    incarnation: int
    namespace: UUID
    operation_id: UUID
    state: str
    redis_run_id: str
    redis_master_replid: str
    policy_fingerprint: str

    def __post_init__(self):
        if type(self.protocol) is not int or self.protocol != 3:
            raise ValueError("unsupported authority protocol")
        if (
            type(self.incarnation) is not int
            or not 0 <= self.incarnation <= MAX_INCARNATION
        ):
            raise ValueError("authority incarnation out of range")
        if self.state not in ("preparing", "ready", "disabled"):
            raise ValueError("unknown authority state")
        if not isinstance(self.namespace, UUID) or not isinstance(
            self.operation_id, UUID
        ):
            raise ValueError("authority UUID required")
        if self.incarnation == 0:
            if (
                self.state != "disabled"
                or self.namespace.int
                or self.operation_id.int
                or self.redis_run_id != ""
                or self.redis_master_replid != ""
                or self.policy_fingerprint != ""
            ):
                raise ValueError("invalid migration seed")
        elif (
            not self.namespace.int
            or not self.operation_id.int
            or not isinstance(self.redis_run_id, str)
            or not _REDIS_ID.fullmatch(self.redis_run_id)
            or not isinstance(self.redis_master_replid, str)
            or not _REDIS_ID.fullmatch(self.redis_master_replid)
            or not isinstance(self.policy_fingerprint, str)
            or not 1 <= len(self.policy_fingerprint) <= 128
        ):
            raise ValueError("incomplete authority identity")

    def wire_identity(self) -> dict[str, str]:
        if self.state != "ready" or self.incarnation == 0:
            raise ValueError("only ready authority may open a stream")
        return {"incarnation": str(self.incarnation), "namespace": str(self.namespace)}


def preparing_candidate(
    expected: Authority,
    *,
    namespace: UUID,
    operation_id: UUID,
    redis_run_id: str,
    redis_master_replid: str,
    policy_fingerprint: str,
) -> Authority:
    """Build the exact operation to retain BEFORE attempting its durable CAS."""
    if expected.incarnation >= MAX_INCARNATION:
        raise ValueError("authority exhausted")
    if namespace == expected.namespace or operation_id == expected.operation_id:
        raise ValueError("activation requires fresh namespace and operation identity")
    return Authority(
        3,
        expected.incarnation + 1,
        namespace,
        operation_id,
        "preparing",
        redis_run_id,
        redis_master_replid,
        policy_fingerprint,
    )


class AuthorityStore:
    """Short independent transactions; no events-row lock or preview payload."""

    def __init__(
        self, primary_sessions: Callable[[], AsyncSession], *, budget_s=CONTROL_BUDGET_S
    ):
        if not 0 < budget_s <= CONTROL_BUDGET_S:
            raise ValueError("authority budget must be positive and at most 150ms")
        self.sessions = primary_sessions
        self.budget_s = budget_s

    async def read(self) -> Authority:
        async with asyncio.timeout(self.budget_s):
            async with self.sessions() as session:
                row = (await session.execute(_READ)).mappings().one_or_none()
                if row is None:
                    raise AuthorityLost("dnpl_authority row missing")
                return Authority(**row)

    async def read_for_producer(self) -> tuple[Authority, datetime]:
        """Fresh primary sample also bounds which observations may open chains.

        Use the database clock shared by observation bounds, never host wall
        time. Caller must require ready and never rebind an existing registry.
        """
        async with asyncio.timeout(self.budget_s):
            async with self.sessions() as session:
                row = (await session.execute(_READ_PRODUCER)).mappings().one_or_none()
                if row is None:
                    raise AuthorityLost("dnpl_authority row missing")
                values = dict(row)
                sampled_at = values.pop("sampled_at")
                return Authority(**values), sampled_at

    async def read_retirement(self) -> Authority | None:
        """Exact predecessor identity survives operator/process failure."""
        async with asyncio.timeout(self.budget_s):
            async with self.sessions() as session:
                row = (await session.execute(_RETIREMENT)).mappings().one_or_none()
                return None if row is None else Authority(**row)

    async def activation_step(self, expected: Authority) -> int:
        params = {f"old_{key}": value for key, value in asdict(expected).items()}
        async with asyncio.timeout(self.budget_s):
            async with self.sessions() as session:
                value = await session.scalar(
                    text(
                        f"SELECT activation_step FROM dnpl_authority WHERE id = 1 AND {_MATCH}"
                    ),
                    params,
                )
                if value is None:
                    raise AuthorityConflict("activation authority changed or missing")
                return value

    async def take_activation_step(self, expected: Authority, step: int) -> bool:
        """Burn the one permitted Redis send BEFORE doing it, including on crash.

        1=arm admission fence; 2=initialize namespace. An uncertain database
        acknowledgement permits only readback, never sending on an assumption.
        A burned send cannot be replayed after a lost Redis reply or key loss.
        Return whether this allocation may create an absent admission fence:
        only the seed's successor or a changed primary identity. On the same
        identity, a missing fence refuses recovery; an old delayed arm must not
        recreate it after namespace cleanup. No automatic primary restart.
        """
        if expected.state != "preparing" or type(step) is not int or step not in (1, 2):
            raise ValueError("preparing activation step 1 or 2 required")
        params = {f"old_{key}": value for key, value in asdict(expected).items()}
        params.update(step=step, prior_step=step - 1)
        try:
            async with asyncio.timeout(self.budget_s):
                async with self.sessions() as session:
                    async with session.begin():
                        await session.execute(text("SET LOCAL lock_timeout = '100ms'"))
                        await session.execute(
                            text("SET LOCAL statement_timeout = '100ms'")
                        )
                        changed = await session.scalar(
                            text(
                                f"UPDATE dnpl_authority SET activation_step = :step WHERE id = 1 AND {_MATCH} "
                                "AND activation_step = :prior_step RETURNING activation_bootstrap"
                            ),
                            params,
                        )
                        if changed is None:
                            raise AuthorityConflict(
                                "activation send already consumed or authority changed"
                            )
            return bool(changed)
        except AuthorityConflict:
            raise
        except Exception as exc:
            raise AuthorityWriteUncertain(
                "activation send not authorized without successful commit acknowledgement"
            ) from exc

    async def complete_retirement(self, current: Authority, retired: Authority) -> None:
        """Acknowledge verified Redis cleanup, never perform or infer it.

        The explicit activation controller must first fence old initialization
        and verify all six retired keys absent. This helper only consumes its
        durable exact-record receipt. Missing/mismatched evidence is refusal;
        uncertain commit needs read_retirement(), not a repeated write.
        """
        if retired.incarnation == 0 or retired.incarnation >= current.incarnation:
            raise ValueError("retirement must precede current authority")
        current_params = {f"old_{k}": v for k, v in asdict(current).items()}
        retired_params = {f"old_{k}": v for k, v in asdict(retired).items()}
        try:
            async with asyncio.timeout(self.budget_s):
                async with self.sessions() as session:
                    async with session.begin():
                        await session.execute(text("SET LOCAL lock_timeout = '100ms'"))
                        await session.execute(
                            text("SET LOCAL statement_timeout = '100ms'")
                        )
                        found = await session.scalar(
                            text(
                                f"SELECT id FROM dnpl_authority WHERE id = 1 AND {_MATCH} FOR UPDATE"
                            ),
                            current_params,
                        )
                        if found is None:
                            raise AuthorityConflict(
                                "cleanup current authority changed or missing"
                            )
                        removed = await session.scalar(
                            _CLEAR_RETIREMENT, retired_params
                        )
                        if removed is None:
                            raise AuthorityConflict(
                                "cleanup predecessor changed or missing"
                            )
        except AuthorityConflict:
            raise
        except Exception as exc:
            raise AuthorityWriteUncertain(
                "resolve cleanup by exact primary readback; do not retry"
            ) from exc

    async def prepare(self, expected: Authority, candidate: Authority) -> Authority:
        # Prevent callers using this as a generic arbitrary-authority setter.
        proposed = preparing_candidate(
            expected,
            namespace=candidate.namespace,
            operation_id=candidate.operation_id,
            redis_run_id=candidate.redis_run_id,
            redis_master_replid=candidate.redis_master_replid,
            policy_fingerprint=candidate.policy_fingerprint,
        )
        if proposed != candidate:
            raise ValueError("candidate must be the next preparing incarnation")
        return await self._compare_exchange(expected, candidate)

    async def ready(self, expected: Authority) -> Authority:
        """Caller must first verify this exact fresh Redis namespace readback."""
        if expected.state != "preparing":
            raise ValueError("only preparing can become ready")
        return await self._compare_exchange(expected, replace(expected, state="ready"))

    async def disable(self, expected: Authority) -> Authority:
        if expected.state not in ("preparing", "ready"):
            raise ValueError("only allocated authority can be disabled")
        return await self._compare_exchange(
            expected, replace(expected, state="disabled")
        )

    async def _compare_exchange(
        self, expected: Authority, candidate: Authority
    ) -> Authority:
        params = {f"old_{key}": value for key, value in asdict(expected).items()}
        params.update({f"new_{key}": value for key, value in asdict(candidate).items()})
        params["allow_bootstrap"] = expected.incarnation == 0 or (
            candidate.redis_run_id,
            candidate.redis_master_replid,
        ) != (expected.redis_run_id, expected.redis_master_replid)
        try:
            async with asyncio.timeout(self.budget_s):
                async with self.sessions() as session:
                    async with session.begin():
                        # Bound server lock/statement work as well as the entire
                        # client operation, including checkout and commit.
                        await session.execute(text("SET LOCAL lock_timeout = '100ms'"))
                        await session.execute(
                            text("SET LOCAL statement_timeout = '100ms'")
                        )
                        row = (
                            (await session.execute(_CAS, params))
                            .mappings()
                            .one_or_none()
                        )
                        if row is None:
                            raise AuthorityConflict("authority changed or missing")
                        result = Authority(**row)
                        if candidate.incarnation != expected.incarnation:
                            # The CAS owns the control-row lock. Allocation and
                            # predecessor retention commit together; another
                            # allocation cannot overtake unacknowledged cleanup.
                            if (await session.execute(_RETIREMENT)).first() is not None:
                                raise AuthorityConflict("namespace cleanup outstanding")
                            if expected.incarnation:
                                await session.execute(_RECORD_RETIREMENT, params)
            return result
        except AuthorityConflict:
            raise
        except Exception as exc:
            raise AuthorityWriteUncertain(
                "resolve by exact primary readback; do not retry"
            ) from exc
        # CancelledError intentionally propagates. Like a lost commit reply it
        # is ambiguous; the caller retains candidate and reads it back later.
