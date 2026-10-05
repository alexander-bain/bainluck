"""Pure single-activity ordering. Callers persist transitions before doing I/O.

A revision orders coherent served readings, including those with unknown producer
clocks. It is supplied by the future serialized adapter, never inferred here.
"""

from dataclasses import dataclass, replace
from datetime import datetime, timedelta, timezone
from typing import Literal

from app.utils.activitykit_payload import (
    ActivityKitPush,
    GameActivitySnapshot,
    build_activitykit_end,
    build_activitykit_update,
)

Kind = Literal["update", "terminal", "stop"]
Failure = Literal["transient", "permanent", "unavailable"]


@dataclass(frozen=True)
class RetryPolicy:
    """Explicit finite delays; the caller owns transport policy, not APNs."""

    delays: tuple[timedelta, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.delays, tuple) or any(
            not isinstance(delay, timedelta) or delay < timedelta(0)
            for delay in self.delays
        ):
            raise ValueError(
                "Retry delays must be a finite tuple of nonnegative timedeltas"
            )


def _utc(value: datetime) -> datetime:
    if not isinstance(value, datetime) or value.utcoffset() is None:
        raise ValueError("A timezone-aware explicit clock is required")
    return value.astimezone(timezone.utc)


def _revision(value: int) -> None:
    if type(value) is not int or value < 0:
        raise ValueError("revision must be a nonnegative integer")


@dataclass(frozen=True)
class DeliveryCommand:
    """An opaque idempotency identity and immutable bytes for one logical send."""

    command_id: str
    kind: Kind
    push: ActivityKitPush


@dataclass(frozen=True)
class Attempt:
    command: DeliveryCommand
    count: int = 1
    in_flight: bool = True
    retry_at: datetime | None = None

    @property
    def attempt_id(self) -> str:
        return f"{self.command.command_id}:attempt:{self.count}"

    @property
    def command_id(self) -> str:
        return self.command.command_id

    @property
    def push(self) -> ActivityKitPush:
        return self.command.push

    @property
    def kind(self) -> Kind:
        return self.command.kind


@dataclass(frozen=True)
class DeliveryState:
    activity_id: str
    event_id: int
    retry_policy: RetryPolicy
    seen_revision: int = -1
    accepted_revision: int = -1
    snapshot: GameActivitySnapshot | None = None
    score_fence: datetime | None = None
    probability_fence: datetime | None = None
    pending: Kind | None = None
    attempt: Attempt | None = None
    last_timestamp: int = -1
    terminal_latched: bool = False
    stopped: bool = False
    ended: bool = False
    halted: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.activity_id, str) or not self.activity_id.strip():
            raise ValueError("activity_id must identify one registered activity")
        if type(self.event_id) is not int or self.event_id <= 0:
            raise ValueError("event_id must identify one canonical event")

    def observe(
        self, snapshot: GameActivitySnapshot, *, revision: int
    ) -> "DeliveryState":
        """Coalesce newer readings; reject stale fields without erasing fences.

        The first terminal reading latches the end and its exact producer dates,
        matching foreground terminal authority over an older score clock.
        """
        _revision(revision)
        if snapshot.event_id != self.event_id:
            raise ValueError("Snapshot belongs to a different canonical event")
        if (
            revision <= self.seen_revision
            or self.terminal_latched
            or self.stopped
            or self.ended
        ):
            return self
        state = replace(self, seen_revision=revision)
        if not snapshot.is_terminal:
            for clock, fence in (
                (snapshot.score_observed_at, self.score_fence),
                (snapshot.probability_observed_at, self.probability_fence),
            ):
                if clock is not None and fence is not None and _utc(clock) < fence:
                    return state

        def advance(fence: datetime | None, clock: datetime | None) -> datetime | None:
            return (
                max(fence, _utc(clock))
                if fence is not None and clock is not None
                else fence or (_utc(clock) if clock is not None else None)
            )

        state = replace(
            state,
            accepted_revision=revision,
            score_fence=advance(self.score_fence, snapshot.score_observed_at),
            probability_fence=advance(
                self.probability_fence, snapshot.probability_observed_at
            ),
        )
        if snapshot == self.snapshot:
            return state
        # A fresh reading supersedes an unsent retry, never an in-flight send.
        attempt = self.attempt if self.attempt and self.attempt.in_flight else None
        return replace(
            state,
            snapshot=snapshot,
            pending="terminal" if snapshot.is_terminal else "update",
            attempt=attempt,
            terminal_latched=snapshot.is_terminal,
        )

    def stop(self) -> "DeliveryState":
        """Explicit stop supersedes queued updates/final and prevents reactivation."""
        if self.stopped or self.ended:
            return self
        if self.snapshot is None:
            raise ValueError("Stop requires the activity's existing reading")
        attempt = self.attempt if self.attempt and self.attempt.in_flight else None
        return replace(self, stopped=True, pending="stop", attempt=attempt)

    def dispatch(self, *, now: datetime) -> tuple["DeliveryState", Attempt | None]:
        """Reserve exactly one attempt; a transport must commit this before sending."""
        now = _utc(now)
        if self.halted or self.ended:
            return self, None
        if self.attempt:
            if self.attempt.in_flight or now < self.attempt.retry_at:
                return self, None
            attempt = replace(
                self.attempt,
                count=self.attempt.count + 1,
                in_flight=True,
                retry_at=None,
            )
            return replace(self, attempt=attempt), attempt
        if self.pending is None:
            return self, None
        timestamp = int(now.timestamp())
        # APNs ordering has second precision. Wait instead of fabricating a future send time.
        if timestamp <= self.last_timestamp:
            return self, None
        sent_at = now
        if self.pending == "update":
            push = build_activitykit_update(self.snapshot, sent_at=sent_at)
        else:
            push = build_activitykit_end(
                self.snapshot,
                sent_at=sent_at,
                reason="stop" if self.pending == "stop" else "terminal",
            )
        command = DeliveryCommand(
            f"{self.activity_id}:{self.accepted_revision}:{timestamp}:{self.pending}",
            self.pending,
            push,
        )
        return (
            replace(
                self, pending=None, last_timestamp=timestamp, attempt=Attempt(command)
            ),
            Attempt(command),
        )

    def complete(
        self, attempt_id: str, *, now: datetime, failure: Failure | None = None
    ) -> "DeliveryState":
        """Duplicate/late acknowledgments are inert; only transient failures retry."""
        now = _utc(now)
        if failure not in {None, "transient", "permanent", "unavailable"}:
            raise ValueError("Unknown transport result")
        if (
            not self.attempt
            or not self.attempt.in_flight
            or self.attempt.attempt_id != attempt_id
        ):
            return self
        attempt = self.attempt
        if failure is None:
            if attempt.command.kind == "terminal" and self.pending == "stop":
                return replace(self, attempt=None)
            if attempt.command.kind in {"terminal", "stop"}:
                return replace(self, attempt=None, pending=None, ended=True)
            return replace(self, attempt=None)
        if failure != "transient":
            return replace(self, attempt=None, halted=failure)
        if self.pending is not None:
            return replace(self, attempt=None)
        if attempt.count > len(self.retry_policy.delays):
            return replace(self, attempt=None, halted="retry_exhausted")
        return replace(
            self,
            attempt=replace(
                attempt,
                in_flight=False,
                retry_at=now + self.retry_policy.delays[attempt.count - 1],
            ),
        )
