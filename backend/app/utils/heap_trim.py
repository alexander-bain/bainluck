"""#11218 — give the C heap's free pages back after a catalog refresh.

worker-ws re-reads both catalogs every ~10 minutes (the Polymarket handover,
the Kalshi scope refresh). Each read builds a large working set that is freed
when the refresh ends. On glibc, the part of it bigger than 512 bytes sits in
the C heap. Freed chunks with live allocations between them stay counted in
the process's memory until something hands their pages back, and nothing in
the process ever did. v5785, 10/18: worker-ws stepped up ~16-38 MB at each
catalog refresh of either arm and stayed flat between them, 811 -> 944.7 MB
in 40 minutes against the 950 MB line.

The local control (real Polymarket consumer, production-sized catalog, live
traffic, 12 handovers) holds Python's own live memory and pymalloc arenas flat
apart from ~1 MB a handover, so the step is not retained objects. What is left
is freed memory the allocator keeps. ``malloc_trim(0)`` hands every whole free
page back, including pages in the middle of the heap. No object moves and no
map or subscription changes.

glibc only. Anywhere else (macOS, musl) this does nothing. ``WS_HEAP_TRIM=0``
turns it off at the next refresh, with no deploy. That is the undo line.
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
