"""#10090 — keep the Polymarket process's long-lived heap out of every collection.

Production 2026-10-30 12:33-13:17Z, worker-ws heartbeat, Polymarket process:
``gc2=26-35`` full (generation-2) collections per 2-minute line at
``gc_max=282-644ms``, with ``cpu=0.93-0.95`` and loop-lag p95 98-199 ms; the
Kalshi process beside it ran ``gc2=2-5``. A full collection walks every
tracked object, and almost all of this process's are long-lived: the game and
open-contract catalogs (~5k + ~68k legs) and the maps built from them. They are
walked again every few seconds only because the socket's buffered quotes and
marks survive the young generations and keep re-arming the full one.

``gc.freeze()`` moves every object alive now to a permanent generation that no
collection walks; freed objects are still freed (reference counting is
unchanged), so nothing waits on the collector that did not before. A frozen
object that later becomes part of an unreachable *cycle* is not reclaimed while
frozen, so the freeze is renewed at each catalog handover (the moment a new
catalog has just become the long-lived set): unfreeze, one full collection of
everything (what the old freeze held included), then freeze the survivors.
Cyclic garbage is therefore held for at most one handover period, and the
handover pays one full collection where every few seconds paid one before.

Local lab (``tests/_pm_cpu_rig_10090.py``, production message rates, 120 s
after warm-up, one freeze): generation-2 pauses max 58 -> 5 ms, worst late wake
39 -> 8 ms, CPU per 10k messages 0.83 -> 0.75 s, RSS flat.

Undo: ``PM_WS_GC_FREEZE=0`` (read at each handover; an earlier freeze is
released at the next one). Never raises into a consumer.
"""

import gc
import logging
import os
import time
from typing import Optional

logger = logging.getLogger(__name__)

GC_FREEZE_ENV = "PM_WS_GC_FREEZE"


def gc_freeze_enabled() -> bool:
    """False only when ``PM_WS_GC_FREEZE`` is set to ``0``."""
    return os.getenv(GC_FREEZE_ENV, "1").strip() != "0"


def refreeze_long_lived(arm: str) -> Optional[int]:
    """Collect everything once, then freeze what survived; the frozen count.

    ``None`` means no freeze is held afterwards: turned off (a freeze an
    earlier call held is released) or the collector failed.
    """
    try:
        if not gc_freeze_enabled():
            if gc.get_freeze_count():
                gc.unfreeze()
                logger.info("worker-ws gc freeze: arm=%s released (turned off)", arm)
            return None
        started = time.perf_counter()
        gc.unfreeze()
        collected = gc.collect()
        gc.freeze()
        took_ms = (time.perf_counter() - started) * 1000
        frozen = gc.get_freeze_count()
    except Exception:
        logger.warning("worker-ws gc freeze failed (arm=%s)", arm, exc_info=True)
        return None
    logger.info(
        "worker-ws gc freeze: arm=%s frozen=%d collected=%d took=%.0fms",
        arm, frozen, collected, took_ms,
    )
    return frozen
