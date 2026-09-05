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

The reconciliation invariant (queue 355, #1845)
-----------------------------------------------
Beat 1 of the 350-2b gate read ``events_new 5,335 + events_existing 5,075 =
10,410`` against ``events_fetched 5,000``. Both halves were honestly computed
and neither was a partition of the other: ``events_fetched`` was a MID-FUNCTION
snapshot of the main scan, written before the supplementary rescue loop added
more events, while new/existing were derived from the full list the fetch
RETURNS. Three different populations wearing names that implied one.

The lesson is not "that counter was wrong" — it is that a reader had to do the
addition by hand to find out, and the reading that mattered (``verdict:
frozen``) sat one line above numbers that could not both be true. So the
identity is now **checked by the artifact, every beat**:

    events_new + events_existing == events_fetched == main_scan_events
                                                      + supplementary_events

When it fails, :meth:`KalshiScanReport.verdict` returns ``instrument_broken``
and refuses to report a mechanism. An instrument that cannot add up does not
get to name a disease — that is the whole reason the gate asked for three
beats instead of one.
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
    # Queue 355: the fetch was CANCELLED at poll_kalshi's hard wall. Previously
    # this left the default `max_pages` in place — a cancelled fetch reported
    # itself as a page ceiling, i.e. as a scan that ran. It also produced the
    # one legitimate non-reconciling shape (partial telemetry, zero events),
    # which would otherwise be indistinguishable from a broken counter.
    "fetch_wall",
    "not_run",            # fetch never started (quota guard, etc.)
)

#: Stop reasons under which no scan population exists, so the reconciliation
#: invariant has nothing to check and its failure means nothing.
_NO_POPULATION_STOPS = frozenset({"not_run", "fetch_wall"})


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
    #: The WHOLE population the fetch returned — main scan plus supplementary
    #: rescue — and therefore the population new/existing partition. Written
    #: once, at the return, over exactly what it names (queue 355).
    events_fetched: int = 0
    #: Its two disjoint halves, so a reader can see WHERE the events came from
    #: without re-deriving it. main_scan_events + supplementary_events must
    #: equal events_fetched.
    main_scan_events: int = 0
    supplementary_events: int = 0

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

    # --- the empty-event market backfill (#2214) --------------------------
    # `events_unreached` above says the loop never GOT to an event. These say
    # the opposite and worse thing: the loop got there and found nothing to
    # upsert, because the event arrived with zero markets. That is the larger
    # population by an order of magnitude — the 2026-08-26 ring reads
    # `events_fetched 16,340 / events_processed 389` with `loop_deadline_hit`
    # false on every beat — and until now it was computed in `kalshi_api` and
    # then dropped on the floor: the fields existed in the fetch's telemetry
    # dict and no caller ever copied them here. Instrumentation that does not
    # reach the report is not instrumentation, and it is why the mechanism went
    # a week without being read off the artifact that exists to show it.
    #: Fetched events carrying zero markets — every one dropped by the upsert
    #: loop's `if not event.markets: continue`.
    events_without_markets: int = 0
    #: How many of those the backfill was willing to try.
    market_backfill_candidates: int = 0
    #: Of the candidates, how many belong to a series deliberately fetched
    #: WITHOUT nested markets. This is the population the backfill OWES; a beat
    #: that fills only the accidental remainder is not doing its job.
    market_backfill_stripped_candidates: int = 0
    #: True when the step was skipped outright for want of budget. Post-#2214
    #: this should be false: the step holds a reserved floor.
    market_backfill_skipped_past_deadline: bool = False
    #: Events the backfill actually put markets into.
    market_backfill_filled: int = 0
    #: How many candidates the backfill had ATTEMPTED when the deadline cut the
    #: loop off, or ``None`` when it worked the whole list.
    #:
    #: The field above is not this one and cannot stand in for it: it is True
    #: only when the step never STARTED, and the loop's own mid-flight `break`
    #: wrote nothing anywhere. So a backfill terminated by the deadline on every
    #: single beat reported `skipped_past_deadline: False` — which reads as "the
    #: reserved floor is holding", i.e. as headroom — and the report had no way
    #: to say the opposite. Measured on the 24-beat ring 2026-09-05: candidates
    #: grew 6,968 -> 10,901 while `filled` stayed flat at 367-496, a correlation
    #: of **-0.869** — supply falling as demand rises, which is the signature of
    #: a time-bound step, not a demand-driven one. The loop sleeps 0.3s per
    #: candidate before its request, so 10,901 candidates is 3,270s of sleep
    #: alone against beats that finish in 327s: it cannot have reached the end.
    #:
    #: This is the #2214 / #2927 shape a third time — a number the code knew and
    #: no reader could get — and it is the one that decides whether a new series
    #: class can be admitted at all, so it is the one that has to be legible.
    market_backfill_truncated_after: Optional[int] = None
    #: How many series the backfill worked, and how many venue requests that
    #: cost (#3149). Before the batching these were the same as the candidate
    #: count by construction — one request per event, plus 0.3s of mandatory
    #: sleep each, which is 3,270s for a 10,901-long list inside a beat that
    #: finishes in 327s. Keeping the request count is how a future reader can
    #: tell a backfill that is cheap from one that has silently gone back to
    #: paying per event.
    market_backfill_series_worked: int = 0
    market_backfill_requests: int = 0
    #: Candidates whose series answered but whose own event ticker appeared in
    #: none of the markets returned. This is the failure the batching could
    #: introduce and the per-event loop could not: `filled` alone cannot tell a
    #: batch that served 9 of 10 events from one that was only asked about 9.
    market_backfill_unmatched: int = 0

    # --- the discovered half of the rescue list (#2927) -------------------
    #: The series-discovery receipt for this beat, bounded for persistence by
    #: `kalshi_series_selection.summarize_discovery_receipt`.
    #:
    #: This field exists because #2927 repeated, one ship later, the exact
    #: mistake the `market_backfill_*` block above was added to correct. The
    #: receipt was assembled in `kalshi_api` (`_tel["series_discovery"]`),
    #: carried every number a reader needs — `source: live|cache|failed|
    #: not_wired`, `events_added`, why each declined series was declined — and
    #: then no caller copied it here, so it reached no artifact and no reader.
    #:
    #: What that cost: the ship worked (the first post-deploy beat, 18:45Z on
    #: 2026-09-04, created the first 32 `KXATPDOUBLES`, 30 `KXWTADOUBLES` and
    #: `KXHONEYDEUCE-01JAN27` rows we have ever held), and it could only be
    #: proved from `futures_markets.created_at` — i.e. from the effect, after
    #: the fact. The instrument built to say so said nothing. Worse in the
    #: failure direction: a discovery stage that quietly stops yielding
    #: presents as "the doubles draw stopped updating", which is the exact
    #: outage #2927 was built to end and the exact one the receipt was built
    #: to catch first.
    series_discovery: Dict[str, Any] = field(default_factory=dict)

    duration_s: float = 0.0
    notes: List[str] = field(default_factory=list)

    def reconciliation(self) -> Dict[str, Any]:
        """The identity this report must satisfy, stated with its terms.

        Returned whether or not it holds, because the terms are what makes a
        failure diagnosable — ``ok: false`` on its own is just a second thing
        to distrust.
        """
        partition = self.events_new + self.events_existing
        halves = self.main_scan_events + self.supplementary_events
        checked = self.stop_reason not in _NO_POPULATION_STOPS
        return {
            "checked": checked,
            "ok": (not checked)
            or (partition == self.events_fetched and halves == self.events_fetched),
            "events_fetched": self.events_fetched,
            "new_plus_existing": partition,
            "new_plus_existing_delta": partition - self.events_fetched,
            "main_plus_supplementary": halves,
            "main_plus_supplementary_delta": halves - self.events_fetched,
        }

    def reconciles(self) -> bool:
        """True when the counters add up (or when there is no population)."""
        return bool(self.reconciliation()["ok"])

    def verdict(self) -> str:
        """A one-word reading. "It returned" is not "it worked" (gotcha #53).

        * ``not_run`` / ``fetch_wall`` — no scan population exists to read.
        * ``instrument_broken`` — the counters do not add up, so no mechanism
          may be named off them (queue 355). This outranks every reading below
          it deliberately: beat 1 reported ``frozen`` sitting directly above
          ``5,335 + 5,075`` against ``5,000``, and the verdict was believed.
        * ``frozen``   — the scan reached no existing market this beat.
        * ``starved``  — it reached some, but the deadline cut off existing ones.
        * ``partial``  — pages were skipped or the walk did not wrap.
        * ``healthy``  — walked to exhaustion with nothing dropped.
        """
        if self.stop_reason in _NO_POPULATION_STOPS:
            return self.stop_reason
        if not self.reconciles():
            return "instrument_broken"
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
        data["reconciliation"] = self.reconciliation()
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

    # Queue 355 (#1845): the gate reads THIS summary, so the arithmetic verdict
    # has to survive the aggregation — a per-beat `instrument_broken` that gets
    # averaged into a stop-reason histogram is a check nobody performs. Runs
    # written before the fix carry no `reconciliation` block; they are counted
    # as `unknown` rather than silently as passing, because a beat that cannot
    # prove it adds up is not a beat that adds up.
    reconciling = not_reconciling = unknown_reconciliation = 0
    for h in history:
        state = _history_reconciliation_state(h)
        if state is True:
            reconciling += 1
        elif state is False:
            not_reconciling += 1
        else:
            unknown_reconciliation += 1

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
        # The gate's readability precondition, stated rather than assumed.
        "runs_reconciling": reconciling,
        "runs_not_reconciling": not_reconciling,
        "runs_unknown_reconciliation": unknown_reconciliation,
        "readable_beats": reconciling,
        "arithmetic_ok": not_reconciling == 0 and unknown_reconciliation == 0,
    }


def _history_reconciliation_state(h: Dict[str, Any]) -> Optional[bool]:
    """Did this persisted beat's arithmetic close? ``None`` when unknowable.

    ``None`` is the honest answer for a beat written before the invariant
    existed: its ``events_fetched`` counted the main scan only, so re-deriving
    the identity from its stored fields would manufacture a failure that the
    run itself never claimed either way.
    """
    rec = h.get("reconciliation")
    if isinstance(rec, dict) and "ok" in rec:
        if not rec.get("checked", True):
            return True
        return bool(rec.get("ok"))
    return None


def new_report() -> KalshiScanReport:
    return KalshiScanReport(
        started_at=datetime.now(timezone.utc).isoformat(),
    )
