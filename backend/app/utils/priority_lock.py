"""#10090: an asyncio lock whose URGENT waiters go first.

The preview claim lock (`LedgerRegistry.claim_lock`) serializes every ledger
publication of a venue process: receipt previews, stamp preparations, settles
and plain frames. Production 2026-11-01 21:2xZ (Kalshi): it was held ~17-20 s a
minute, and a receipt preview, the price a reader is waiting for, queued
behind stamp work for up to 259 ms. A receipt publication asks with
``urgent()`` and is handed the lock before any ordinary waiter; it still waits
for the holder in progress, never preempts it. Ordinary waiters keep FIFO
order among themselves, and urgent ones among theirs.

Any order between two waiters was already possible (it was decided by which
asked first), so the ledger's own checks, not the lock order, keep every
publication correct.

``yield_to_urgent()`` (#10090, 11/01 00:20Z: a receipt waited 575 ms behind
one 579 ms settle hold) lets a long holder hand the lock to a queued urgent
waiter between its own units of work and take it back next, ahead of every
ordinary waiter. A holder that never calls it is unchanged.
"""

from __future__ import annotations

import asyncio
import collections
import contextlib


class PriorityLock:
    """`asyncio.Lock` (``async with lock``, ``locked()``) plus ``urgent()``."""

    def __init__(self) -> None:
        self._locked = False
        self._waiters: collections.deque = collections.deque()
        self._urgent: collections.deque = collections.deque()

    def locked(self) -> bool:
        return self._locked

    async def acquire(self, urgent: bool = False) -> bool:
        if not self._locked and not self._waiters and not self._urgent:
            self._locked = True
            return True
        queue = self._urgent if urgent else self._waiters
        waiter = asyncio.get_running_loop().create_future()
        queue.append(waiter)
        try:
            await waiter
        except asyncio.CancelledError:
            if waiter.done() and not waiter.cancelled():
                # Handed the lock as the cancellation arrived: pass it on.
                self.release()
            else:
                with contextlib.suppress(ValueError):
                    queue.remove(waiter)
            raise
        return True

    def release(self) -> None:
        if not self._locked:
            raise RuntimeError("Lock is not acquired.")
        for queue in (self._urgent, self._waiters):
            while queue:
                waiter = queue.popleft()
                if not waiter.done():
                    waiter.set_result(True)  # ownership moves; still locked
                    return
        self._locked = False

    def urgent_waiting(self) -> bool:
        return any(not waiter.done() for waiter in self._urgent)

    async def yield_to_urgent(self) -> bool:
        """Holder only: when an urgent waiter is queued, hand it the lock and
        wait to get it back, first among ordinary waiters. True if it yielded."""
        if not self._locked or not self.urgent_waiting():
            return False
        waiter = asyncio.get_running_loop().create_future()
        self._waiters.appendleft(waiter)
        self.release()
        try:
            # Shielded: a cancellation must not cancel the hand-back itself.
            await asyncio.shield(waiter)
        except asyncio.CancelledError:
            # The caller's `async with` will release the lock as it unwinds, so
            # it must own it again first: wait (the urgent holder's work is
            # short) without letting a second cancellation strand the wait.
            while not waiter.done():
                with contextlib.suppress(asyncio.CancelledError):
                    await asyncio.shield(waiter)
            raise
        return True

    async def __aenter__(self) -> None:
        await self.acquire()

    async def __aexit__(self, *exc) -> None:
        self.release()

    @contextlib.asynccontextmanager
    async def urgent(self):
        await self.acquire(urgent=True)
        try:
            yield
        finally:
            self.release()
