"""#9418 — a match that goes live mid-cycle gets moving prices in ~1.5 min, not up to 10.

Both venue WS consumers build their subscription ONCE per run, from events that
are live or scheduled within 6 h, and hold it for `SUBSCRIPTION_REFRESH_SECONDS`
(600 in production: the env var is unset). An event that turns live after the
slate was read — a suspended match resuming, a start the venue moved earlier, a
row that sat outside the 6 h scheduled arm — is not on the socket until the next
timed rebuild, so its card reads a REST price up to ten minutes old while the
venue moves every few seconds (#9418: Angelini v Johns, 35 min stale).

The repair is admission, not a new writer. Beside the socket, each consumer
re-reads the live event ids its own slate query WOULD select now, every
`ADMISSION_CHECK_SECONDS`. A live event missing from the ids the run subscribed
ends the run early by cancelling `ws.run` — the same cancellation the timer
delivers, so the consumer reports `"resubscribe"` and the runner re-reads the
slate at once, with no restart and no config.

Three properties the tests pin:

- **Thrash floor.** No run ends early before `ADMISSION_MIN_RECYCLE_SECONDS`
  from its start. A missing event that cannot be admitted (the reread and the
  slate disagreeing for any reason) therefore costs one reconnect a minute at
  worst, never a loop.
- **A failed reread never recycles.** The socket is the thing a reader is
  watching; an unreadable database is a reason to keep it, not to drop it.
- **A complete subscription never recycles.** The reread is a subset of the
  slate's own live arm, so a run that already holds every live event is left
  alone however often it is checked.
"""

import asyncio
import logging
import os
import time
from typing import Awaitable, Callable, Iterable, Optional

logger = logging.getLogger(__name__)

#: How often each consumer re-reads the live event ids. One indexed query over
#: the live rows (tens) per consumer per 30 s.
ADMISSION_CHECK_SECONDS = float(os.getenv("WS_ADMISSION_CHECK_SECONDS", "30"))

#: The earliest a run may be ended for admission, measured from its start.
ADMISSION_MIN_RECYCLE_SECONDS = float(
    os.getenv("WS_ADMISSION_MIN_RECYCLE_SECONDS", "60")
)


async def watch_for_unadmitted_live_events(
    load_live_event_ids: Callable[[], Awaitable[Iterable[int]]],
    subscribed_event_ids: Iterable[int],
    *,
    arm: str,
    started_at: float,
    check_seconds: Optional[float] = None,
    min_recycle_seconds: Optional[float] = None,
    clock: Callable[[], float] = time.monotonic,
) -> frozenset:
    """Return the live event ids the run is missing, once it may recycle.

    Never returns while the subscription is complete, while the reread fails,
    or before `min_recycle_seconds` have passed since `started_at`. Both
    intervals default to the module constants, read at call time.
    """
    if check_seconds is None:
        check_seconds = ADMISSION_CHECK_SECONDS
    if min_recycle_seconds is None:
        min_recycle_seconds = ADMISSION_MIN_RECYCLE_SECONDS
    subscribed = frozenset(subscribed_event_ids)
    while True:
        await asyncio.sleep(check_seconds)
        try:
            live = set(await load_live_event_ids())
        except Exception:
            logger.warning(
                "%s WS admission: live reread failed, keeping the subscription",
                arm, exc_info=True,
            )
            continue
        missing = live - subscribed
        if missing and clock() - started_at >= min_recycle_seconds:
            return frozenset(missing)


async def run_until_admission(
    run: Awaitable, watch: Awaitable[frozenset],
) -> Optional[frozenset]:
    """Await the socket `run` until it ends or `watch` names a missing event.

    Returns the missing ids after cancelling the socket (the recycle path), or
    None when the socket returned on its own. A socket error propagates exactly
    as it did when `ws.run` was awaited directly. A watcher that fails for any
    reason is logged and dropped; the socket keeps running to its timer.
    Cancelling this coroutine (the refresh timer, a shutdown) cancels both.
    """
    run_task = asyncio.ensure_future(run)
    watch_task = asyncio.ensure_future(watch)
    try:
        await asyncio.wait(
            {run_task, watch_task}, return_when=asyncio.FIRST_COMPLETED,
        )
        if run_task.done():
            run_task.result()
            return None
        if watch_task.exception() is None:
            return watch_task.result()
        logger.error(
            "WS admission watcher failed; the subscription recycles on its timer",
            exc_info=watch_task.exception(),
        )
        await run_task
        return None
    finally:
        for task in (run_task, watch_task):
            if not task.done():
                task.cancel()
        await asyncio.gather(run_task, watch_task, return_exceptions=True)
