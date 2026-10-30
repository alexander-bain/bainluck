"""#10090 preview receipt — one log line per preview arm per UTC minute.

WHY. The ledger keeps counters (published, revoked, recomposed, superseded,
refusals by status) and the ALARM line names only the first refused event per
key per 10 s; nothing wrote the counters out and nothing timed how long a
committed price took to reach readers as a preview. Speed's 5-minute readout
needs both per minute in production, without a page capture.

WHAT ONE LINE SAYS (``PREVIEW_RECEIPT_FORMAT``):

* counts for the minute: ``published`` blends, ``revoked``, ``recomposed``,
  ``superseded``, ``withdrawn``, ``fenced``, ``authority_refused``,
  ``publish_errors``, ``no_reading`` — deltas of the refresher's cumulative
  counters, read only when the minute closes;
* ``refused=`` the ledger's refusals by status, plus ``local_*`` drops the
  authority adapter made before any Redis call (``-`` when none);
* ``committed`` — committed input revisions handed to this arm (per event,
  the newest a flush carried); ``measured`` — those a published blend carried;
  ``coalesced`` — replaced by a newer revision of the same event before any
  blend published; ``unpreviewed`` — no blend carried them within
  ``PREVIEW_RECEIPT_AWAIT_S`` (the stamp may still have delivered them);
* recv→publish latency over ``measured``: p50/p90/p99/max in ms, nearest rank.
  ``latency_clock=mono``: the socket's receipt instant (``InputMark.recv_mono``)
  and the publish reply instant are the same process's monotonic clock;
* ``worst=`` up to three ``event:ms`` of the slowest;
* preview capacity passes by ``end`` (``capacity_error`` is ``end=error``).

THE SHIP'S SUBSETS (appended after ``capacity_end``; every field above keeps
its meaning so earlier lines stay comparable):

* ``observation_timeouts`` — observation-preview reads that ran past their
  budget (they preview only unchanged repeats); no longer in ``publish_errors``;
* ``read_required=`` the ``read_required`` refusals by ledger phase
  (``propose``, ``retire``, ``retire_idle``, ...; ``-`` when none);
* ``first`` / ``repeat`` — charged blends with no earlier published blend for
  the event this run, or carrying the same value as the last one: excluded
  from ``moved_*``, still in ``measured`` and the unprefixed percentiles;
* ``live_*`` — the charged blends whose frame said ``status=live``;
  ``moved_*`` — those whose blend value moved from the last published blend
  for that event; ``live_moved_*`` — both, the population a live-game reader
  waits on. Each: ``_measured`` and p50/p90/p99/max in ms; ``live_moved_worst``
  up to three ``event:ms``. Pre-game, suspended, first and repeat blends are
  counted above, never dropped;
* ``live_moved_late`` — live, moved blends whose charge was purged as older
  than ``PREVIEW_RECEIPT_AWAIT_S`` (also in ``unpreviewed``; never timed).
  Marks purged at the minute close had no blend and stay unclassified.

ATTRIBUTION. A published blend for an event is charged to the newest committed
revision of that event not yet charged, at most once. A blend composed before
a newer revision was noted is charged to the newer one (understates). A
revision already older than ``PREVIEW_RECEIPT_AWAIT_S`` when a blend would
charge it is purged as ``unpreviewed`` instead, so no charge exceeds it. A
moved value is charged to the newest committed input of the event (any
outcome, repeats included). It understates when an earlier input moved the
value and a newer one replaced it before the blend published; it overstates
only when the move came from an input not yet noted (the other arm). So
``moved_*`` is neither bound on the reader's wait, and it does not identify
the input that moved the blend. A live, moved blend whose charge is purged
counts in ``live_moved_late`` (and ``unpreviewed``), so a wait pushed past
``PREVIEW_RECEIPT_AWAIT_S`` never reads as a lower ``live_moved_max``.
Counters read at the close are those up to the closing flush, at most one
flush past the boundary.

VOLUME. One fixed-size line per arm per minute the refresher flushed in — a
ZERO line when nothing happened, so a missing line means nothing rolled it (no
flush), never "no previews". No per-event lists beyond ``worst``.

Pure bookkeeping: nothing awaited, no Redis or database call, every entry
point swallowed by its caller. It cannot change a frame, a send or its order.
"""

from __future__ import annotations

import logging
import math
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Callable, Optional

logger = logging.getLogger(__name__)

PREVIEW_RECEIPT_WINDOW_S = 60.0
#: A committed revision no blend carried within this long is `unpreviewed`;
#: the preview's own uncommitted lifetime (`DEFAULT_MAX_UNCOMMITTED_S`).
PREVIEW_RECEIPT_AWAIT_S = 60.0
#: Latency samples kept per minute; past it only `max` and the count move.
PREVIEW_RECEIPT_MAX_SAMPLES = 8192
PREVIEW_RECEIPT_WORST = 3
#: Events whose last published blend value is remembered; past it the memory
#: restarts and the next blend of each event counts as ``first``.
PREVIEW_RECEIPT_MAX_EVENTS = 50_000
#: The cumulative counters a minute line reports as deltas, in line order.
PREVIEW_RECEIPT_COUNTS = (
    "published", "revoked", "ledger_recomposed", "ledger_superseded", "withdrawn",
    "fenced", "authority_refused", "publish_errors", "no_reading",
)

#: The 5-minute readout's matcher keys on this shape.
PREVIEW_RECEIPT_FORMAT = (
    "blend_preview[%s]: preview-receipt run=%s window_start=%s window_s=%.3f "
    "published=%d revoked=%d recomposed=%d superseded=%d withdrawn=%d fenced=%d "
    "authority_refused=%d publish_errors=%d no_reading=%d refused=%s "
    "committed=%d measured=%d coalesced=%d unpreviewed=%d latency_clock=mono "
    "p50_ms=%s p90_ms=%s p99_ms=%s max_ms=%s latency_dropped=%d worst=%s "
    "capacity_passes=%d capacity_error=%d capacity_end=%s "
    "observation_timeouts=%d read_required=%s first=%d repeat=%d "
    "live_measured=%d live_p50_ms=%s live_p90_ms=%s live_p99_ms=%s live_max_ms=%s "
    "moved_measured=%d moved_p50_ms=%s moved_p90_ms=%s moved_p99_ms=%s moved_max_ms=%s "
    "live_moved_measured=%d live_moved_p50_ms=%s live_moved_p90_ms=%s "
    "live_moved_p99_ms=%s live_moved_max_ms=%s live_moved_worst=%s live_moved_late=%d"
)


def _iso(wall: float) -> str:
    return datetime.fromtimestamp(wall, tz=timezone.utc).isoformat(timespec="milliseconds")


def _pairs(counts: dict) -> str:
    return ",".join(f"{k}:{v}" for k, v in sorted(counts.items()) if v) or "-"


def _rank(ordered: list, p: float) -> str:
    if not ordered:
        return "-"
    return str(int(round(ordered[max(0, math.ceil(p * len(ordered)) - 1)] * 1000)))


def _ms(latency: Optional[float]) -> str:
    return "-" if latency is None else str(int(round(latency * 1000)))


def _worst(samples: list, top: Optional[tuple]) -> str:
    worst = sorted(samples, key=lambda s: (-s[0], s[1]))[:PREVIEW_RECEIPT_WORST]
    if top is not None and top not in worst:
        worst = [top, *worst][:PREVIEW_RECEIPT_WORST]
    return ",".join(f"{eid}:{int(round(lat * 1000))}" for lat, eid in worst) or "-"


class _Subset:
    """One charged population's latencies for the minute (capped like the
    unprefixed samples; ``top`` stays exact past the cap)."""

    def __init__(self) -> None:
        self.count = 0
        self.samples: list[tuple[float, int]] = []
        self.top: Optional[tuple[float, int]] = None

    def add(self, latency: float, event_id: int) -> None:
        self.count += 1
        if self.top is None or latency > self.top[0]:
            self.top = (latency, event_id)
        if len(self.samples) < PREVIEW_RECEIPT_MAX_SAMPLES:
            self.samples.append((latency, event_id))

    def fields(self) -> tuple:
        ordered = sorted(latency for latency, _eid in self.samples)
        return (self.count, _rank(ordered, 0.50), _rank(ordered, 0.90),
                _rank(ordered, 0.99), _ms(None if self.top is None else self.top[0]))


def _value(p: Any) -> Optional[float]:
    """A blend frame's value, rounded past float noise; ``None`` if absent."""
    try:
        return None if p is None else round(float(p), 6)
    except (TypeError, ValueError):
        return None


class PreviewReceipt:
    """The per-minute preview receipt of one refresher arm (module doc).

    ``counters`` returns this arm's CUMULATIVE counts — the
    ``PREVIEW_RECEIPT_COUNTS`` keys plus ``refused:<status>`` and
    ``capacity:<end>`` — and is called only when a minute opens or closes.
    """

    def __init__(self, source: str, counters: Callable[[], dict], *,
                 mono: Callable[[], float] = time.monotonic,
                 wall: Callable[[], float] = time.time) -> None:
        self.source = source
        self.run = uuid.uuid4().hex[:8]
        self._counters = counters
        self._mono = mono
        self._wall = wall
        self._start: Optional[float] = None
        self._from = 0.0
        self._base: dict = {}
        #: event id -> the newest committed input mark no blend carried yet.
        self._awaiting: dict[int, Any] = {}
        #: event id -> the value of the last blend this arm published for it.
        self._last_value: dict[int, Optional[float]] = {}
        self.lines = 0
        self._reset()

    def _reset(self) -> None:
        self._committed = self._measured = self._coalesced = 0
        self._samples: list[tuple[float, int]] = []
        self._dropped = 0
        self._max: Optional[tuple[float, int]] = None
        self._purged = self._first = self._repeat = self._live_moved_late = 0
        self._live, self._moved, self._live_moved = _Subset(), _Subset(), _Subset()

    # ── the refresher's side ─────────────────────────────────────────────────

    def committed(self, staged: dict) -> None:
        """Input marks a flush committed, per event the newest (`TailReceipts.
        observe`'s ``staged``). The same mark twice counts once."""
        self._roll(self._wall())
        for event_id, mark in staged.items():
            held = self._awaiting.get(event_id)
            if held is not None:
                if mark.recv_mono <= held.recv_mono:
                    continue
                self._coalesced += 1
            self._awaiting[event_id] = mark
            self._committed += 1

    def published(self, frame: dict, meta: Any, reply: tuple) -> None:
        """The ledger send's observer (`observe_publication`): called after the
        send it describes; only a blend Redis published is charged."""
        if not reply or reply[0] != "published":
            return
        preview = frame.get("preview") or {}
        if preview.get("kind") != "blend":
            return
        now = self._mono()
        self._roll(self._wall())
        event_id = frame.get("event_id")
        value = _value(frame.get("p"))
        known = event_id in self._last_value
        before = self._last_value.get(event_id)
        if not known and len(self._last_value) >= PREVIEW_RECEIPT_MAX_EVENTS:
            self._last_value.clear()
        self._last_value[event_id] = value
        mark = self._awaiting.pop(event_id, None)
        if mark is None:
            return
        latency = max(0.0, now - mark.recv_mono)
        live = frame.get("status") == "live"
        moved = known and value is not None and before is not None and value != before
        if latency > PREVIEW_RECEIPT_AWAIT_S:
            self._purged += 1  # no blend carried it in time: unpreviewed
            self._live_moved_late += live and moved
            return
        self._measured += 1
        if self._max is None or latency > self._max[0]:
            self._max = (latency, event_id)
        if len(self._samples) < PREVIEW_RECEIPT_MAX_SAMPLES:
            self._samples.append((latency, event_id))
        else:
            self._dropped += 1
        if not known:
            self._first += 1
        elif not moved:
            self._repeat += 1
        if live:
            self._live.add(latency, event_id)
        if moved:
            self._moved.add(latency, event_id)
            if live:
                self._live_moved.add(latency, event_id)

    def roll(self) -> None:
        """Close the minute if the clock has left it; every flush calls this."""
        self._roll(self._wall())

    # ── the minute ───────────────────────────────────────────────────────────

    def _roll(self, wall: float) -> None:
        size = PREVIEW_RECEIPT_WINDOW_S
        if self._start is None:
            self._start = math.floor(wall / size) * size
            self._from = wall  # never claim seconds before the arm watched
            self._base = dict(self._counters())
            return
        if wall < self._start + size:
            return
        self._emit(self._start + size)
        self._start = math.floor(wall / size) * size
        self._from = self._start

    def _emit(self, window_end: float) -> None:
        now = self._mono()
        unpreviewed = [eid for eid, mark in self._awaiting.items()
                       if now - mark.recv_mono > PREVIEW_RECEIPT_AWAIT_S]
        for event_id in unpreviewed:
            del self._awaiting[event_id]
        current = dict(self._counters())
        delta = {}
        for key, value in current.items():
            before = self._base.get(key, 0)
            # A replaced counter (a new registry) restarts from zero.
            delta[key] = value - before if value >= before else value
        self._base = current
        refused = {k.split(":", 1)[1]: v for k, v in delta.items() if k.startswith("refused:")}
        capacity = {k.split(":", 1)[1]: v for k, v in delta.items() if k.startswith("capacity:")}
        read_required = {k.split(":", 1)[1]: v for k, v in delta.items()
                         if k.startswith("read_required:")}
        ordered = sorted(latency for latency, _eid in self._samples)
        worst = sorted(self._samples, key=lambda s: (-s[0], s[1]))[:PREVIEW_RECEIPT_WORST]
        if self._max is not None and self._dropped and self._max not in worst:
            worst = [self._max, *worst][:PREVIEW_RECEIPT_WORST]
        logger.info(
            PREVIEW_RECEIPT_FORMAT, self.source, self.run, _iso(self._from),
            max(0.0, window_end - self._from),
            *(delta.get(key, 0) for key in PREVIEW_RECEIPT_COUNTS), _pairs(refused),
            self._committed, self._measured, self._coalesced, len(unpreviewed) + self._purged,
            _rank(ordered, 0.50), _rank(ordered, 0.90), _rank(ordered, 0.99),
            "-" if self._max is None else str(int(round(self._max[0] * 1000))),
            self._dropped,
            ",".join(f"{eid}:{int(round(lat * 1000))}" for lat, eid in worst) or "-",
            sum(capacity.values()), capacity.get("error", 0), _pairs(capacity),
            delta.get("observation_timeouts", 0), _pairs(read_required),
            self._first, self._repeat,
            *self._live.fields(), *self._moved.fields(), *self._live_moved.fields(),
            _worst(self._live_moved.samples, self._live_moved.top),
            self._live_moved_late,
        )
        self.lines += 1
        self._reset()
