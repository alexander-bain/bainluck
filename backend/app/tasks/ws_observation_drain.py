"""Bounded observation work beside price work, within the caller's scope lock."""

import asyncio
import time


class ObservationDrain:
    """One drain at a time; its cadence survives successive price flushes.

    `run_with` owns and joins the pump before returning. The caller holds the
    consumer's scope lock throughout, so this never outlives routing authority.
    The separate wake never consumes a price-loop wake.
    """

    def __init__(self, drain, pending, wake, period, *, clock=time.monotonic):
        self._drain = drain
        self._pending = pending
        self._wake = wake
        self._period = period
        self._clock = clock
        self._next = 0.0
        self._draining = asyncio.Lock()

    async def _attempt(self):
        async with self._draining:
            now = self._clock()
            if now < self._next or not self._pending():
                return
            self._next = now + self._period
            await self._drain()

    async def _pump(self, stop):
        while not stop.is_set():
            if not self._pending():
                self._wake.clear()
                await self._wake.wait()
                continue
            delay = self._next - self._clock()
            if delay > 0:
                try:
                    await asyncio.wait_for(stop.wait(), timeout=delay)
                except TimeoutError:
                    pass
                continue
            await self._attempt()

    async def run_with(self, work):
        stop = asyncio.Event()
        pump = asyncio.create_task(self._pump(stop), name="kalshi-book-observations")
        completed = False
        try:
            result = await work()
            # Let the owned pump attempt due work even if price work never
            # yielded. All drain cleanup stays on that single joined task.
            await asyncio.sleep(0)
            completed = True
            return result
        finally:
            stop.set()
            self._wake.set()
            if not completed:
                pump.cancel()
            joined = asyncio.gather(pump, return_exceptions=True)
            interrupted = False
            while not joined.done():
                try:
                    await asyncio.shield(joined)
                except asyncio.CancelledError:
                    interrupted = True
                    if not pump.cancelling():
                        pump.cancel()
            if interrupted:
                raise asyncio.CancelledError
            if not pump.cancelled():
                error = pump.exception()
                if error is not None:
                    raise error
