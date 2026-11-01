"""Bounded v3 validation worker for the existing fanout hub (#10090).

Integration adapter: callers stamp at Redis receipt, supply an uncached primary
read and atomic Redis guard check, and dispatch only from ``deliver``. Committed
frames never enter this queue. This module does not activate production v3.
"""

from __future__ import annotations

import asyncio
import logging
from collections import deque
from dataclasses import dataclass
from time import monotonic
from typing import Awaitable, Callable

from app.services.dnpl_authority import Authority, CONTROL_BUDGET_S

MAX_RECORD_BYTES = 16384
MAX_QUEUED = 64
MAX_BATCH = 16
#: #10090 (11/01 19:45Z): a validation that only ran out of time is not evidence
#: the authority changed. It drops its batch (never delivered) and keeps the
#: stream; this many in a row still reconnect. Reconnecting on every one cut
#: each live reader's stream every 12-58 s on a busy Sunday (a ~1.3 s gap, the
#: "Next update" ring flashing, previews reset) while the number sat still.
MAX_CONSECUTIVE_TIMEOUTS = 5
LOG_INTERVAL_S = 30.0

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class PreviewReceipt:
    channel: str
    payload: str | bytes
    authority: Authority
    received_at: float


class AuthorityFanout:
    """One worker, FIFO order, no cached authority or per-frame tasks.

    Both callbacks are synchronous: delivery/reconnection cannot yield between
    checking the invalidation generation and updating subscriber mailboxes.
    ``verify_redis`` must validate the current identity and clean namespace
    atomically, not compare two independent cached INFO responses.
    """

    def __init__(
        self,
        read_primary: Callable[[], Awaitable[Authority]],
        verify_redis: Callable[[Authority], Awaitable[bool]],
        deliver: Callable[[PreviewReceipt], None],
        reconnect: Callable[[frozenset[str]], None],
    ):
        self._read_primary = read_primary
        self._verify_redis = verify_redis
        self._deliver = deliver
        self._reconnect = reconnect
        self._queue: deque[PreviewReceipt] = deque()
        self._inflight: tuple[PreviewReceipt, ...] = ()
        self._wake = asyncio.Event()
        self._generation = 0
        self._closed = False
        self._worker: asyncio.Task | None = None
        self._timeouts_in_row = 0
        self.stats = {"delivered": 0, "timeouts_skipped": 0, "reconnects": 0}
        self._logged_at = monotonic()

    def start(self) -> None:
        if self._closed or self._worker is not None:
            raise RuntimeError("fanout validator cannot be restarted")
        self._worker = asyncio.create_task(self._run(), name="dnpl-authority-fanout")

    def offer(self, receipt: PreviewReceipt) -> bool:
        if self._closed or self._worker is None or self._worker.done():
            self._reconnect(frozenset((receipt.channel,)))
            return False
        size = (
            len(receipt.payload.encode("utf-8"))
            if isinstance(receipt.payload, str)
            else len(receipt.payload)
        )
        if size > MAX_RECORD_BYTES or len(self._queue) >= MAX_QUEUED:
            self._invalidate((receipt,))
            return False
        self._queue.append(receipt)
        self._wake.set()
        return True

    def _invalidate(self, extra: tuple[PreviewReceipt, ...] = ()) -> None:
        channels = frozenset(r.channel for r in (*self._inflight, *self._queue, *extra))
        self._queue.clear()
        self._generation += 1
        if channels:
            self.stats["reconnects"] += 1
            self._reconnect(channels)

    def _skip_timed_out(self) -> None:
        """Drop the in-flight batch and every queued receipt already past its
        budget, undelivered, keeping every stream (``MAX_CONSECUTIVE_TIMEOUTS``)."""
        self.stats["timeouts_skipped"] += 1
        now = monotonic()
        while self._queue and now - self._queue[0].received_at >= CONTROL_BUDGET_S:
            self._queue.popleft()

    def _log_stats(self) -> None:
        if monotonic() - self._logged_at >= LOG_INTERVAL_S:
            self._logged_at = monotonic()
            logger.info("dnpl_authority_fanout: delivered=%d timeouts_skipped=%d reconnects=%d",
                        self.stats["delivered"], self.stats["timeouts_skipped"],
                        self.stats["reconnects"])

    async def _run(self) -> None:
        try:
            while True:
                await self._wake.wait()
                self._wake.clear()
                while self._queue:
                    # Snapshot before the fresh read. Arrivals during it must
                    # wait for the NEXT read, never inherit this validation.
                    self._inflight = tuple(
                        self._queue.popleft()
                        for _ in range(min(MAX_BATCH, len(self._queue)))
                    )
                    generation = self._generation
                    try:
                        # Include queue residence in the 150ms work budget.
                        remaining = CONTROL_BUDGET_S - (
                            monotonic() - min(r.received_at for r in self._inflight)
                        )
                        if remaining <= 0:
                            raise TimeoutError("preview validation budget exhausted")
                        async with asyncio.timeout(remaining):
                            authority = await self._read_primary()
                            if authority.state != "ready" or any(
                                r.authority != authority for r in self._inflight
                            ):
                                raise ValueError("preview authority changed")
                            if not await self._verify_redis(authority):
                                raise ValueError("preview namespace unavailable")
                        if (
                            monotonic() - min(r.received_at for r in self._inflight)
                            >= CONTROL_BUDGET_S
                        ):
                            raise TimeoutError("preview validation budget exhausted")
                        if generation == self._generation:
                            self._timeouts_in_row = 0
                            for receipt in self._inflight:
                                # Receipt is unchanged; route subtracts ALL
                                # validation/mailbox time from original TTL.
                                self._deliver(receipt)
                                self.stats["delivered"] += 1
                    except asyncio.CancelledError:
                        self._invalidate()
                        raise
                    except TimeoutError:
                        if generation == self._generation:
                            self._timeouts_in_row += 1
                            if self._timeouts_in_row >= MAX_CONSECUTIVE_TIMEOUTS:
                                self._timeouts_in_row = 0
                                self._invalidate()
                            else:
                                self._skip_timed_out()
                    except Exception:
                        if generation == self._generation:
                            self._invalidate()
                    finally:
                        self._inflight = ()
                        self._log_stats()
        except asyncio.CancelledError:
            raise
        finally:
            self._closed = True
            self._invalidate()

    async def aclose(self) -> None:
        self._closed = True
        worker = self._worker
        if worker is not None:
            worker.cancel()
            try:
                await worker
            except asyncio.CancelledError:
                pass
        self._invalidate()
