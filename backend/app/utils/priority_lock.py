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
