"""#11218 — give the C heap's free pages back after a catalog refresh.

worker-ws re-reads both catalogs every ~10 minutes (the Polymarket handover,
the Kalshi scope refresh). Each read builds a large working set that is freed
when the refresh ends. On glibc, the part of it bigger than 512 bytes sits in
the C heap, and freed chunks with live allocations between them stay resident
until something hands their pages back; free() itself only returns the top of
the heap. v5785, 10/18: worker-ws memory stepped up 12-38 MB in windows that
held a catalog refresh of either arm, stayed flat between them, and fell only
occasionally (-12 MB once), 811 -> 944.7 MB in 40 minutes against the 950 MB
line. Co-timed, not attributed: the dyno total also holds the open-receiver
child, and the windows also held reconnects.

The local control (real Polymarket consumer, production-sized catalog, live
traffic, 12 handovers) holds Python's live memory and pymalloc arenas flat
apart from ~1 MB a handover. That rules out only the Python retention it
exercised, not allocations inside C libraries (asyncpg, TLS, websockets), GC
timing or the child. What it leaves consistent with the steps is freed memory
the allocator keeps; on glibc CI the real consumer's handovers left 15 MB that
one trim returned. ``malloc_trim(0)`` hands every whole free page back,
including pages in the middle of the heap. No object moves and no map or
subscription changes. The ``released=`` line each refresh logs is the
production test of this account.

glibc only. Anywhere else (macOS, musl) this does nothing. Undo:
``WS_HEAP_TRIM=0``. Read at each refresh, but a config var change releases and
restarts the dyno, so in production it takes effect from that restart.
"""

import ctypes
import logging
import os
import time
from typing import Callable, Optional

logger = logging.getLogger(__name__)

#: Resolved once: the running C library's ``malloc_trim``, or ``False``.
_trim_fn: Optional[object] = None


def heap_trim_enabled() -> bool:
    """False only when ``WS_HEAP_TRIM`` is set to ``0``."""
    return os.getenv("WS_HEAP_TRIM", "1").strip() != "0"


def _malloc_trim() -> Optional[Callable[[int], int]]:
    global _trim_fn
    if _trim_fn is None:
        found: object = False
        try:
            fn = getattr(ctypes.CDLL(None), "malloc_trim", None)
            if fn is not None:
                fn.argtypes = [ctypes.c_size_t]
                fn.restype = ctypes.c_int
                found = fn
        except Exception:
            found = False
        _trim_fn = found
    return _trim_fn or None


def _rss_bytes() -> Optional[int]:
    """Resident bytes from ``/proc/self/statm``, or ``None`` off Linux."""
    try:
        with open("/proc/self/statm", "rb") as statm:
            return int(statm.read().split()[1]) * os.sysconf("SC_PAGE_SIZE")
    except Exception:
        return None


def release_free_heap(arm: str) -> Optional[int]:
    """Trim the C heap once; the bytes resident memory fell by, or ``None``.

    ``None`` means it did not run: turned off, no ``malloc_trim`` in this C
    library, or the call failed. Never raises into a consumer.
    """
    if not heap_trim_enabled():
        return None
    trim = _malloc_trim()
    if trim is None:
        return None
    try:
        before = _rss_bytes()
        started = time.perf_counter()
        trim(0)
        took_ms = (time.perf_counter() - started) * 1000
        after = _rss_bytes()
    except Exception:
        logger.warning("worker-ws heap trim failed (arm=%s)", arm, exc_info=True)
        return None
    if before is None or after is None:
        logger.info("worker-ws heap trim: arm=%s took=%.0fms", arm, took_ms)
        return None
    released = before - after
    logger.info(
        "worker-ws heap trim: arm=%s released=%.1fMB rss=%.1f->%.1fMB took=%.0fms",
        arm, released / 2**20, before / 2**20, after / 2**20, took_ms,
    )
    return released
