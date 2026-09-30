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

#9462 review — "subscribed" means a MAPPED LEG, not a selected event. The first
cut compared the reread with the event ids the slate query SELECTED, before the
consumer had looked up a single token. An event whose Polymarket token top-up
failed (or whose Kalshi winner ticker arrived after the slate read) was counted
as subscribed with nothing on the wire, so when it turned live the difference
was empty and it waited out the 600 s timer. A prop streaming beside a missing
moneyline hid the gap the same way. So admission is now decided per event by
`unadmitted_live_events`: the market the stored blend reading names (the leg
the hero actually renders) must be mapped in this run; with no such reading,
any mapped leg will do.

That makes a new never-admittable population possible — a live event whose
winner leg this run looked up and could not map (Gamma has no token for it
yet). Recycling for it every minute would reconnect the whole socket all day
for a lookup that just failed. So the watcher's first successful reread is a
BASELINE: an event the run already tried (it was on the slate) that is live and
unadmitted at the baseline is held to the timer. An event that turns live
LATER, or that the slate never held, is admitted as before.
"""

import asyncio
import logging
import os
import time
from typing import Any, Awaitable, Callable, Iterable, Optional

from app.utils.probability_eligibility import (
    VERIFIED,
    contributing_market_ids,
    from_entry,
)

logger = logging.getLogger(__name__)

#: How often each consumer re-reads the live event ids. One indexed query over
#: the live rows (tens) per consumer per 30 s.
ADMISSION_CHECK_SECONDS = float(os.getenv("WS_ADMISSION_CHECK_SECONDS", "30"))

#: The earliest a run may be ended for admission, measured from its start.
ADMISSION_MIN_RECYCLE_SECONDS = float(
    os.getenv("WS_ADMISSION_MIN_RECYCLE_SECONDS", "60")
)


def feeding_market_ids(source_entry: Any) -> frozenset:
    """The markets behind a stored blend reading, or empty if none is proven.

    ``source_entry`` is this venue's whole `win_probability_sources` entry.
    Only a VERIFIED eligibility record names markets that fed the rendered
    number; an UNVERIFIED or INELIGIBLE one, a missing one, or one that will
    not parse names nothing, and the caller falls back to "any mapped leg".
    """
    try:
        record = from_entry(source_entry)
    except Exception:
        return frozenset()
    if record is None or record.status != VERIFIED:
        return frozenset()
    return frozenset(contributing_market_ids(record))


def unadmitted_live_events(
    rows: Iterable[tuple], legged_market_ids: Iterable[int],
) -> frozenset:
    """Live events whose rendered price has no mapped leg in this run.

    ``rows`` are ``(event_id, market_id, source_entry)`` for every live
    market on the venue's slate (one row per market is enough; duplicates are
    harmless). ``legged_market_ids`` are the markets this run can attribute a
    tick to — a mapped asset or ticker, not merely a selected row.

    An event is admitted when every market its stored reading names that is on
    the slate is legged, or — when the reading names none of them — when any of
    its slate markets is legged. A named market that is off the slate (settled,
    filtered) cannot be subscribed, so it does not hold the event hostage.
    """
    legged = frozenset(legged_market_ids)
    markets: dict[int, set] = {}
    feeding: dict[int, frozenset] = {}
    for event_id, market_id, entry in rows:
        markets.setdefault(event_id, set()).add(market_id)
        if not feeding.get(event_id):
            feeding[event_id] = feeding_market_ids(entry)
    unadmitted = set()
    for event_id, mids in markets.items():
        feeds = feeding.get(event_id, frozenset()) & mids
        if feeds:
            if not feeds <= legged:
                unadmitted.add(event_id)
        elif not mids & legged:
            unadmitted.add(event_id)
    return frozenset(unadmitted)


async def watch_for_unadmitted_live_events(
    load_unadmitted_live_event_ids: Callable[[], Awaitable[Iterable[int]]],
    tried_event_ids: Iterable[int],
    *,
    arm: str,
    started_at: float,
    check_seconds: Optional[float] = None,
    min_recycle_seconds: Optional[float] = None,
    clock: Callable[[], float] = time.monotonic,
) -> frozenset:
    """Return the live events the run cannot price, once it may recycle.

    ``load_unadmitted_live_event_ids`` answers "which live events have no
    mapped leg for their rendered price right now". ``tried_event_ids`` are the
    events this run's slate held, i.e. the ones whose legs it already looked
    up. The first successful answer is read at once and is the baseline: a
    tried event unadmitted there is held to the timer (a recycle would repeat
    the lookup that just failed). Never returns while nothing else is missing,
    while the reread fails, or before `min_recycle_seconds` have passed since
    `started_at`. Both intervals default to the module constants, read at call
    time.
    """
    if check_seconds is None:
        check_seconds = ADMISSION_CHECK_SECONDS
    if min_recycle_seconds is None:
        min_recycle_seconds = ADMISSION_MIN_RECYCLE_SECONDS
    tried = frozenset(tried_event_ids)
    held: Optional[frozenset] = None
    while True:
        if held is not None:
            await asyncio.sleep(check_seconds)
        try:
            unadmitted = frozenset(await load_unadmitted_live_event_ids())
        except Exception:
            logger.warning(
                "%s WS admission: live reread failed, keeping the subscription",
                arm, exc_info=True,
            )
            if held is None:
                await asyncio.sleep(check_seconds)
            continue
        if held is None:
            held = unadmitted & tried
            if held:
                logger.warning(
                    "%s WS admission: %d live event(s) have no mapped leg for "
                    "their rendered price after this run's lookup; held to the "
                    "timer: %s",
                    arm, len(held), sorted(held)[:20],
                )
            continue
        missing = unadmitted - held
        if missing and clock() - started_at >= min_recycle_seconds:
            return missing


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
