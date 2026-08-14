"""Main-scan telemetry for ``poll_kalshi_markets`` (#1586 / #1845).

Why this module exists
----------------------
Kalshi capture is frozen on two populations at once: futures markets we DISPLAY
(``KXMLBPLAYOFFS-26`` and its 30 outcomes were last updated 2026-07-24 02:52:27Z
— three weeks stale, rendered as live, ours 56.5% against Kalshi's own 88.5% on
BOS) and the resolved-outcome cohorts marching toward the 86-day retention cliff
(gotcha #35).

Every previous attempt on this named a mechanism and fixed it: the deadline that
could not interrupt a hung page, the GIL-holding JSON decode, the monster
nested-markets parse, the missing resumable cursor. Each was real. The freeze
outlived all of them, and #1586's own text still records the current era
hypothesis as **unconfirmed** — because the one measurement that would settle it
exceeded the ``db-query`` statement timeout on every formulation tried.

So this run does not add a sixth fix. Per the ruling on this queue: **instrument
the main-scan cursor first, so the freeze's mechanism is read off a measurement
rather than inferred from a coverage curve.** Reporting the mechanism is the
deliverable; the fix follows it.

What is recorded, and why each field earns its place
----------------------------------------------------
The scan is a cursor walking a >28K-event listing across beats. To say where it
freezes you need, per run: where it STARTED, where it ENDED, what it SKIPPED,
and WHY it stopped. In particular:

* ``start_cursor_fp`` / ``end_cursor_fp`` — cursor fingerprints (not the opaque
  blobs). Successive runs showing the SAME start fingerprint mean the resume is
  not advancing; a fingerprint that never repeats across a full day means the
  walk never wraps, so the tail is never revisited.
* ``wrapped`` — the listing was exhausted and the cursor cleared. If this is
  never true, no market past the reach of one beat is EVER refreshed, which is
  a freeze even though every individual page succeeded.
* ``stop_reason`` — one of a closed set. "It returned" is not "it worked"
  (gotcha #53 / ``task_verdict``): a scan that stops on ``main_scan_deadline``
  every single beat is a different disease from one that stops on ``exhausted``.
* ``pages_skipped`` + ``skip_reasons`` — a page whose parse timed out is
  silently dropped today. Dropped events are invisible in a coverage curve.
* ``events_unreached`` / ``unreached_existing`` — the upsert loop processes NEW
  event tickers first (#995's creation fix) and breaks on a per-event deadline.
  That fix is correct for creation and, by construction, starves UPDATES: every
  event the deadline cuts off is an EXISTING one, i.e. exactly the displayed
  markets that go stale. This pair is the measurement that confirms or refutes
  that reading, and no existing counter captures it.

Nothing here changes scan behaviour. It is read-only telemetry.
"""

from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# Latest report, plus a short ring so a reader can see whether the cursor
# ADVANCES across beats — a single sample cannot show a stuck walk.
_LAST_KEY = "bainluck:kalshi:scan_report:last"
_RING_KEY = "bainluck:kalshi:scan_report:ring"
_RING_MAX = 48  # ~4 days at the 2h beat
_TTL_S = 86400 * 7


#: Closed set of reasons the main scan stopped. A scan that always stops for the
#: same non-``exhausted`` reason is the freeze, stated in one word.
STOP_REASONS = (
    "exhausted",          # listing walked to the end; cursor cleared, next beat wraps
    "main_scan_deadline",  # capped deadline hit; cursor saved, tail deferred
    "max_pages",          # page ceiling hit; cursor saved, tail deferred
    "page_error",         # a page fetch failed/timed out; scan stopped early
    "not_run",            # fetch never started (quota guard, wall timeout, etc.)
)


def cursor_fingerprint(cursor: Optional[str]) -> Optional[str]:
    """Short stable fingerprint of an opaque cursor.

    The cursor itself is a long opaque blob and is not useful to a human reader;
    what matters is whether it is the SAME one as last beat. 12 hex chars is
    plenty to answer that and keeps the report readable.
    """
    if not cursor:
        return None
    return hashlib.sha256(str(cursor).encode("utf-8")).hexdigest()[:12]


@dataclass
class KalshiScanReport:
    """One ``poll_kalshi_markets`` main-scan run, as a measurement."""

    # --- where it started -------------------------------------------------
    started_at: str = ""
    resumed: bool = False
    start_cursor_fp: Optional[str] = None

    # --- where it ended ---------------------------------------------------
    finished_at: str = ""
    end_cursor_fp: Optional[str] = None
    wrapped: bool = False
    stop_reason: str = "not_run"

    # --- what it covered --------------------------------------------------
    pages_fetched: int = 0
    pages_skipped: int = 0
    skip_reasons: Dict[str, int] = field(default_factory=dict)
    events_fetched: int = 0

    # --- what the upsert loop actually reached ----------------------------
    # The half no existing counter captures. `unreached_existing` is the
    # update-starvation measurement: events fetched, ordered behind the NEW
    # ones, and cut off by the per-event deadline.
    events_new: int = 0
    events_existing: int = 0
    events_processed: int = 0
    events_unreached: int = 0
    unreached_existing: int = 0
    loop_deadline_hit: bool = False

    duration_s: float = 0.0
    notes: List[str] = field(default_factory=list)

    def verdict(self) -> str:
        """A one-word reading. "It returned" is not "it worked" (gotcha #53).

        * ``frozen``   — the scan reached no existing market this beat.
        * ``starved``  — it reached some, but the deadline cut off existing ones.
        * ``partial``  — pages were skipped or the walk did not wrap.
        * ``healthy``  — walked to exhaustion with nothing dropped.
        """
        if self.stop_reason == "not_run":
            return "not_run"
        reached_existing = self.events_processed - self.events_new
        if self.events_existing > 0 and reached_existing <= 0:
            return "frozen"
        if self.unreached_existing > 0:
            return "starved"
        if self.pages_skipped > 0 or not self.wrapped:
            return "partial"
        return "healthy"

    def to_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        data["verdict"] = self.verdict()
        return data


def save_scan_report(report: KalshiScanReport) -> None:
    """Persist the report. Best-effort — telemetry must never break the poll."""
    try:
        from app.tasks.redis_state import get_redis_client

        payload = json.dumps(report.to_dict())
        client = get_redis_client()
        client.setex(_LAST_KEY, _TTL_S, payload)
        # Ring so a reader can see whether the cursor advances across beats.
        client.lpush(_RING_KEY, payload)
        client.ltrim(_RING_KEY, 0, _RING_MAX - 1)
        client.expire(_RING_KEY, _TTL_S)
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning("kalshi scan report: save failed: %s", exc)


def load_scan_report() -> Optional[Dict[str, Any]]:
    """Most recent scan report, or None."""
    try:
        from app.tasks.redis_state import get_redis_client

        raw = get_redis_client().get(_LAST_KEY)
        if not raw:
            return None
        if isinstance(raw, bytes):
            raw = raw.decode("utf-8")
        return json.loads(raw)
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning("kalshi scan report: load failed: %s", exc)
        return None


def load_scan_history(limit: int = _RING_MAX) -> List[Dict[str, Any]]:
    """Recent scan reports, newest first."""
    try:
        from app.tasks.redis_state import get_redis_client

        rows = get_redis_client().lrange(_RING_KEY, 0, max(0, limit - 1))
        out: List[Dict[str, Any]] = []
        for raw in rows or []:
            if isinstance(raw, bytes):
                raw = raw.decode("utf-8")
            try:
                out.append(json.loads(raw))
            except Exception:
                continue
        return out
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning("kalshi scan report: history load failed: %s", exc)
        return []


def summarize_history(history: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Read the mechanism off the ring, rather than off one sample.

    A single beat cannot distinguish "this run was slow" from "the walk never
    advances". Three questions answer that, and they are the whole point of
    keeping a ring:

    * Does the cursor MOVE? (distinct start fingerprints)
    * Does the walk ever WRAP? (if never, the tail is never revisited)
    * Where does it stop, over and over? (stop_reason histogram)
    """
    if not history:
        return {"runs": 0}

    starts = [h.get("start_cursor_fp") for h in history]
    distinct_starts = len({s for s in starts if s})
    stop_hist: Dict[str, int] = {}
    for h in history:
        reason = h.get("stop_reason") or "unknown"
        stop_hist[reason] = stop_hist.get(reason, 0) + 1

    verdict_hist: Dict[str, int] = {}
    for h in history:
        v = h.get("verdict") or "unknown"
        verdict_hist[v] = verdict_hist.get(v, 0) + 1

    wraps = sum(1 for h in history if h.get("wrapped"))
    unreached_existing = sum(int(h.get("unreached_existing") or 0) for h in history)
    processed = sum(int(h.get("events_processed") or 0) for h in history)

    return {
        "runs": len(history),
        "distinct_start_cursors": distinct_starts,
        "cursor_appears_stuck": distinct_starts <= 1 and len(history) > 2,
        "wraps": wraps,
        "never_wrapped": wraps == 0,
        "stop_reasons": stop_hist,
        "verdicts": verdict_hist,
        "total_events_processed": processed,
        "total_unreached_existing": unreached_existing,
    }


def new_report() -> KalshiScanReport:
    return KalshiScanReport(
        started_at=datetime.now(timezone.utc).isoformat(),
    )
