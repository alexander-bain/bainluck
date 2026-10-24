"""Q460 — the fast lane's last mile: WebSocket price -> the number on the card.

WHAT WAS BROKEN. `worker-ws` has been streaming Kalshi prices into
`futures_outcomes.current_probability` in production for months, sub-second,
and none of it was visible. Measured 2026-08-30 18:32 UTC: 4 of 10 live Kalshi
outcomes moved inside a 25-second window, while `Event.win_probability_sources`
— the JSONB every hero and every card actually renders — advanced only on the
120-second `poll_live_prediction_markets` pass. Sampled three times across 90s,
the Kalshi blend stamp read 54s / 0s / 24s old: a clean 120s sawtooth. The fast
lane existed, worked, and stopped one table short of the number.

Alex's own specimen (Hawaii @ Stanford, 2026-08-29) is the cost. That event's
blend carried exactly one prediction-market source, and its in-game snapshots
land 240s / 360s / 600s / 1200s apart. A number that moves every four to twenty
minutes during a football game is what "constantly behind the action" means.

WHAT THIS DOES. After the WS flushes prices for a batch of outcomes, it hands
the affected event ids here. For each, this recomputes that source's home
probability from the rows the flush just wrote — via
`app/utils/live_blend.py`, the SAME expression the 120s poll uses, so the two
writers cannot disagree — and stamps `win_probability_sources`. Since Q501 it
also appends the matching `win_prob_snapshots` point, so the CHART moves on the
same beat as the number.

THE CHART POINT (Q501). This module originally declined to write
`win_prob_snapshots` on the grounds that a snapshot per tick would grow that
table ~60x for resolution nobody can see. That reasoning was about *per-tick*
writes, and it is still right — so the write is throttled on its own clock
(`DEFAULT_SNAPSHOT_INTERVAL_S`, 25s) rather than the blend's 2s one, and it goes
through the same `_create_or_update_win_prob_snapshot` helper the 120s poll uses,
which appends a row only when the value actually CHANGES and otherwise just
bumps `reading_count`/`valid_until` on the existing point. Upper bound is
therefore ~4.8x the 120s poll on a continuously-moving market and 0x on a flat
one — not 60x. What it buys is Alex's stated bar: a live match page gains a
chart point within a minute instead of within two.

Committed chart points have one finite FIFO owner for the consumer run.
Each point freezes its original database stamp time; chart transactions share
the existing three-session ceiling with preparation and quote stamps. A single
admitted event keeps its direct read/write path; multiple events prepare each fresh/pending
population, then commit one event per transaction. Fresh worker tails reread
current quotes in their write session. Fresh stamps
do not wait for older debt's preparation reads. Earlier
completed events publish and release their row locks while later events still
do stamp work. A waiting first event still delays later stamps, but cannot hold
an earlier event's committed stamp or publication.

THREE THINGS IT DELIBERATELY DOES NOT DO.

* **It does not go through Celery.** It is called in-process on the `worker-ws`
  dyno. The background queue is a known congestion point (GIN beat starvation),
  and a fast lane queued behind a slow one is not a fast lane.
* **It does not re-derive the inversion verdict per tick.**
  `_check_and_fix_inversion` costs a per-event `odds_snapshots` lookup, which is
  affordable every 120 seconds and not every 2. Orientation is a property of the
  LINKAGE, not of the price, so it is computed once and cached — and the 120s
  poll re-derives it authoritatively regardless, which bounds how long a wrong
  verdict can survive to one poll interval.

SAFETY POSTURE. Every failure here is swallowed and counted. This runs inside
the WS consumer's flush loop, and a blend refresh that raises must never take
down the price streaming that is the dyno's actual job (gotcha #42, one bad item
must not wipe the pass).
"""

from __future__ import annotations

from asyncio import CancelledError
import asyncio
import contextlib
from contextvars import ContextVar
from collections import deque
import logging
import math
import time
from dataclasses import dataclass, replace as _replace
from datetime import datetime, timezone
from typing import Awaitable, Callable, Container, Iterable, Optional

logger = logging.getLogger(__name__)


#: Per-event floor between fast-lane recomputes, equal to the WS's 2s flush:
#: every flush that carries a new price for an event may stamp it. It was 5s
#: (the 2026-08-30 "<=1 change/~5s" live look), which on a liquid market kept
#: real prices off the page — Alex's required benchmark (Angelini v Johns,
#: 2026-09-28) moves Kalshi 77 -> 80 -> 85 -> 84 two seconds apart, and at 5s
#: the 85 was stored and never stamped. The write rate stays bounded by the
#: flush itself, by the unchanged-value arm (45s, below) and by the chart's own
#: 25s clock; what 2s adds is up to one blend UPDATE per moving event per flush.
DEFAULT_MIN_REFRESH_INTERVAL_S = 2.0

#: How long an event whose batch FAILED waits before it is attempted again —
#: the 5s the success floor used to give it for free. A failed transaction is
#: usually a database in trouble, and at the 2s floor every flush would open a
#: fresh session against it for the same owed stamp. Row-lock retries are not
#: failures and stay due at once.
DEFAULT_FAILED_RETRY_INTERVAL_S = 5.0

#: #11317 P2 — the longest a bundled pair the current-book proof refused waits
#: with none of its proof inputs changed before it is read again. One shared
#: sweep for every parked pair, so a quiet refused slate costs one read every
#: sweep instead of one per pair per 2 s floor. A change to any input the proof
#: reads wakes the pair at once (`current_book_signature`); the sweep is the
#: backstop for a row another writer changed (the poll).
BOOK_REFUSED_SWEEP_S = 10.0

#: How long a cached inversion verdict stays good. One poll interval plus slack:
#: the 120s poll re-derives it authoritatively, so this never has to be the
#: durable answer, only a cheap one that cannot be stale for long.
DEFAULT_INVERSION_TTL_S = 150.0

#: When the recomputed value rounds to what is already stored, the write is
#: still worth making occasionally — `updated_at` is what drives the hero's
#: recency decay (#1829), so a source that goes quiet must still look ALIVE
#: rather than progressively losing weight. Just not on every flush.
#:
#: #5661 — and only when the venue WAS re-read. "Quiet" and "dead" recompute
#: the same number from the same rows; see `restamp_records_no_observation`.
UNCHANGED_RESTAMP_INTERVAL_S = 45.0

#: Per-event floor between fast-lane CHART points. Deliberately slower than the
#: blend's 2s throttle: the number wants to be as live as the socket, the line
#: only has to gain a point often enough that a watching user sees it grow.
#: 25s clears Alex's "within a minute" bar with margin while keeping
#: `win_prob_snapshots` growth to a small multiple of the 120s poll's.
DEFAULT_SNAPSHOT_INTERVAL_S = 25.0

#: live/035 — the CADENCE FLOOR, which is a different promise from the throttle
#: above. The throttle is a ceiling on how often a moving market may write; this
#: is a floor under how long a FLAT one may stay silent. Both are needed: without
#: the floor, `_create_or_update_win_prob_snapshot` writes nothing at all while
#: the price holds, so a tense goalless half draws as one straight segment
#: between its endpoints. 60s is Alex's stated bar and bounds the cost at one row
#: per minute per source per live event.
DEFAULT_SNAPSHOT_MAX_GAP_S = 60.0

#: #837 tail — the longest one event's stamp may QUEUE behind another
#: transaction's lock on its `events` row before it gives up and retries on the
#: next flush. Production 2026-09-24 23:16:09–23:16:20Z: the Polymarket arm's
#: stamp of one game waited 10.6s on a row a worker-realtime transaction held,
#: and because a batch is one transaction inside a serial flush loop, every
#: OTHER game's price froze with it — Brewers @ Phillies moved on the venue at
#: 23:16:12.452 and reached the page at 23:16:24.2. In that 32-minute capture the
#: arm waited >1s 34 times (17 of them ≥5s, 240s in all). Under the server's 1s
#: `deadlock_timeout` on purpose: a stamp that has stopped waiting cannot be the
#: party a deadlock is detected on, and cannot be the convoy the sibling arm
#: queues behind.
#:
#: #11138 — and the stamp's UPDATE carries the same number as its
#: `statement_timeout` (`SET_LOCK_AND_STATEMENT_TIMEOUT_SQL`). `lock_timeout` bounds
#: each lock ACQUISITION, and a row wait is several: the tuple-lock queue, then
#: the holder's transaction, then any writer that took the row first. Each
#: stayed under 500 ms while the statement did not — `pg_stat_statements` max
#: 15.97 s for this UPDATE since 2026-09-27, and v5763 10:36:27Z: Kalshi's stamp
#: of PM 15331282 wrote its clock at .419 and committed ~29.2, so the PM stamp
#: queued behind it gave up at 28.625 and published at 29.258 (1.39 s after the
#: quote). Local PG 14, holder then queued writer: 0.876 s under `lock_timeout`
#: alone, cancelled at 0.65 s with the statement bound.
DEFAULT_STAMP_LOCK_TIMEOUT_MS = 500

# Old stamp retries must not occupy an entire periodic flush while fresh quote
# writes wait for the next one. Cooperative: finish each attempted transaction
# and publication; never cancel a stamp merely because this budget elapsed.
PENDING_STAMP_BUDGET_S = 1.0
# #10090 — a flush that carries fresh event IDs attempts at most this many old
# stamps across all of its refresh calls; the rest stay owed in continuation
# order for a quiet flush, which keeps the full time budget above. Without it a
# busy flush's old debt ran serially for up to that second after its fresh work.
FRESH_FLUSH_PENDING_ATTEMPTS = 1

# #10090 — fixed fresh-stamp workers per refresh. Two disjoint stamps waiting
# on rows/publication must not hold a third ready fresh event. Each holds one
# session only inside its stamp; with a consumer's price writer and standalone
# writer that is the lent engine's five connections (pool 3 + overflow 2).
FRESH_STAMP_WORKERS = 3

# #10090 — admitted cohorts are stamped live-first, as a call's own population
# is. Stage trace 02:14Z 2026-10-15: a live game's admitted stamp started
# 6.43 s after admission and then took 95 ms; 134 events were held by the call
# then, which does not say how many were queued ahead of it, their status, or
# what the three workers were waiting on. This orders a known-live event ahead
# of queued non-live ones when a worker comes free; it cannot preempt an
# occupied worker. After this many live stamps in a row, a waiting non-live
# event goes next, so pre-game prices keep progressing while live ones lead.
ADMITTED_LIVE_RUN = 3

# Includes the point currently writing and reservations before quote COMMIT.
# The writer's ordinary backlog. Past it a newly due stamp does not wait
# (#11138) and still owes its point at its own observation time, paid when
# the writer drains without another quote (#11181). No point drops.
HISTORY_POINT_LIMIT = 64
# The memory bound beyond the ordinary backlog. Points are owed at most one per
# event per snapshot interval, so a held writer reaches it only after minutes
# (a 100-event slate owes 4 a second: ~4 minutes). Past it a point is still
# owed and the stamp still never waits: the point lives only in its durable
# `owed_chart_points` row until memory has room to load it (#11181,
# `OwedChartCustody`).
HISTORY_SPILL_LIMIT = 1024

#: #837 receipt — the per-event floor between receipt lines for chains that
#: cannot qualify as a quiet tail (a busy market's routine deferrals, a held
#: price that rounded to the stored value). Those are summarised with a count.
#: A quiet stamp and every abnormal chain are never held back by it.
TAIL_RECEIPT_COALESCE_S = 60.0

#: #10090 delivery receipt — one line per source × LIVE event × UTC minute:
#: what the consumer received for that game (raw / accepted / changed /
#: repeats, per outcome) and which published revisions carried it. Alex,
#: 2026-10-06: incoming rate, browser arrival rate and lag are three separate
#: numbers; the page capture sees only the second, and nothing on the consumer
#: side said how many inputs one game had or which `rev` a given input reached
#: the page as. Bounded to events whose latest stamp was `live`, so a slate of
#: upcoming games and futures writes no lines.
DELIVERY_RECEIPT_WINDOW_S = 60.0
#: Per line. A live game stamps at most once per 2 s flush (~30 a minute), so
#: the cap only bites if the throttle is changed; the overflow is counted.
DELIVERY_RECEIPT_MAX_STAMPS = 40
#: Inputs awaiting their stamp, per event. A stamp normally takes all of them
#: within one flush; the bound only stops a never-stamped event from growing.
DELIVERY_RECEIPT_MAX_PENDING = 512
#: Lines per source per minute. worker-ws logs drain to Better Stack; a full
#: evening slate must not turn the receipt into the dyno's loudest line. The
#: most active games are written; the rest are counted in one overflow line.
DELIVERY_RECEIPT_MAX_EVENTS = 30


#: #10090 — the live games a consumer run's receipt knew, left for the next run
#: of the same source. Process-local, like `_pending_handoff`: without it every
#: recycle would count nothing for a live game until its first stamp of the new
#: run, and that stamp would read covered=0.
_live_handoff: dict[str, frozenset] = {}


def _mono() -> float:
    """The refresher's monotonic clock — one seam, so a rig can drive time
    without patching `time.monotonic` under the event loop."""
    return time.monotonic()


def _wall() -> float:
    """The dyno's wall clock (epoch seconds, UTC) — same seam, same reason."""
    return time.time()


# Call-local timing for the existing optional-read failure receipt. A fetch
# cancellation alone cannot say whether checkout/admission consumed its budget.
# Ordinary stamp reads have no timing state; no payloads or event IDs are kept.
_observation_read_timing: ContextVar[dict | None] = ContextVar(
    "observation_read_timing", default=None,
)


@contextlib.contextmanager
def _observation_read_step(name):
    timing = _observation_read_timing.get()
    if timing is None:
        yield
        return
    started = _mono()
    timing[name + "_start_ms"] = (started - timing["started_s"]) * 1000
    timing[name + "_completed"] = False
    try:
        yield
        timing[name + "_completed"] = True
    finally:
        timing[name + "_ms"] = (_mono() - started) * 1000


def _observation_read_summary(timing):
    if timing is None:
        return None
    return {key: round(value, 3) if type(value) is float else value
            for key, value in timing.items() if key != "started_s"}


def _iso(wall: Optional[float]) -> Optional[str]:
    if wall is None:
        return None
    from datetime import datetime, timezone

    return datetime.fromtimestamp(wall, timezone.utc).isoformat(timespec="milliseconds")


class PreviewSettlementUncertain(RuntimeError):
    """A settlement did not produce a parsed reply; keep its locked proof alive."""


@dataclass(frozen=True)
class InputMark:
    """One accepted venue input, as the socket received it.

    `seq` counts every accepted input of one consumer run, same-price repeats
    included; `event_ordinal` is how many inputs THIS event had received when
    this one arrived. The receipt's "did anything arrive after the held price"
    is the difference between the event's running count and that ordinal —
    which a stored `price_changed_at` cannot answer, because a repeat or a
    move that rounds to the stored value leaves it untouched.
    """

    seq: int
    event_id: int
    outcome_id: int
    probability: float
    kind: str
    recv_wall: float
    recv_mono: float
    venue_ts_ms: Optional[int]
    event_ordinal: int


@dataclass
class _TailChain:
    origin: str  # "throttle" | "lock" | "batch"
    rev: InputMark  # the revision whose committed write was held
    stamp_rev: InputMark  # the newest committed revision before the close
    stored_wall: float
    opened_wall: float
    opened_mono: float
    later_committed: int = 0
    lock_retries: int = 0
    commit_failures: int = 0
    batch_failures: int = 0


class TailReceipts:
    """#837 — one receipt per held price: received, stored, held, stamped.

    WHY. The deferred-tail stamp exists (`_throttle_deferred`, `_lock_retry`),
    but nothing said, for ONE event, which price was held, when it arrived, and
    whether the stamp that finally carried it was the quiet flush or another
    tick. The aggregate `throttled=`/`stamped=` counts cannot. Codex's review of
    the first draft (2026-09-25 16:20Z) also showed why a receipt must not read
    "quiet" off the final flush: refresh 1000 → held 1001 → a second input
    1003 → stamp 1006 printed quiet=True and held 6s, when the input at 1003
    intervened and the price was held 5s. So a chain opens at the hold, counts
    EVERY later input for the event (same-price and not-yet-flushed ones
    included) and every later committed write, and `quiet` is only
    `later_inputs == 0`.

    CLOCK DOMAINS, stated because they must not be mixed: `*_wall` fields are the
    dyno clock. `stamped_at` is the database write clock, byte-for-byte the JSONB
    `updated_at` and the SSE frame's, so the receipt joins to what was served.
    `*_s` durations are monotonic on the same process. `venue_ts_ms` is the
    venue's clock, copied raw. The database clock (`price_changed_at`,
    `captured_at`) is a fourth domain the receipt does not assert against.

    VOLUME. One line per chain, never per flush. A chain closes only at a due
    refresh, so the always-logged class (quiet stamps, lock and failure chains,
    recycle/shutdown resets) is at most one line per event per throttle
    interval; routine chains are coalesced per event (`TAIL_RECEIPT_COALESCE_S`).
    A `tail-receipt summary` line per consumer run says the instrument was on —
    the absence of a receipt proves nothing without it.

    Pure bookkeeping, nothing awaited, and every entry point is wrapped by its
    caller: a receipt that fails must never cost a price (gotcha #42).
    """

    COALESCIBLE = frozenset(
        {"stamped", "unchanged", "preview_only", "unobserved", "no_reading", "no_row", "no_market"}
    )

    def __init__(self, source: str, *, coalesce_s: float = TAIL_RECEIPT_COALESCE_S) -> None:
        import uuid

        self.source = source
        #: Sequences restart with every consumer run; the run id is what stops
        #: a seq from one run being read against another's across a recycle.
        self.run = uuid.uuid4().hex[:8]
        self.coalesce_s = coalesce_s
        self._seq = 0
        self._inputs_by_event: dict[int, int] = {}
        self._last_seq_by_event: dict[int, int] = {}
        self._staged: dict[int, InputMark] = {}
        self._staged_wall: Optional[float] = None
        self._open: dict[int, _TailChain] = {}
        self._last_logged: dict[int, float] = {}
        self._coalesced: dict[int, int] = {}
        self.stats: dict[str, int] = {
            "inputs": 0, "opened": 0, "logged": 0, "coalesced": 0,
            "delivery_lines": 0,
        }
        # #10090 delivery receipt state (see `DELIVERY_RECEIPT_WINDOW_S`).
        self._window_start: Optional[float] = None
        self._window: dict[int, dict] = {}
        #: Per LIVE event only: worker-ws carries ~100k open-contract outcomes
        #: and runs near its memory quota, so nothing here is kept for an event
        #: until a stamp has said it is live, and it is dropped when it is not.
        self._last_p: dict[int, dict[int, float]] = {}
        self._uncovered: dict[int, deque] = {}
        self._committed: dict[int, InputMark] = {}
        self._live_events: set[int] = set(_live_handoff.pop(source, frozenset()))
        #: Coverage starts no earlier than this run did, nor before a game was
        #: first stamped live in it: a minute line must never claim seconds the
        #: consumer was not watching (Root's 57 s repro: 3 inputs in 3 s read
        #: as 3 in 60 s, a 20x understatement).
        self._run_start = _wall()
        self._live_since: dict[int, float] = {}

    # ── the socket's side ────────────────────────────────────────────────────

    def note_raw(self, event_id: Optional[int]) -> None:
        """#10090 — one venue message for a contract of this event, counted
        BEFORE the price policy decides whether it is a price. `raw` minus
        `accepted` is what the policy refused (one-sided books, terminal
        prices); a message that maps to no event is not this game's."""
        if event_id is None:
            return
        self._roll(_wall())
        if event_id in self._live_events:
            self._bucket(event_id)["raw"] += 1

    def note_input(
        self,
        event_id: Optional[int],
        outcome_id: int,
        probability: float,
        kind: str,
        venue_ts=None,
    ) -> Optional[InputMark]:
        """Stamp one accepted input. Called under the socket's buffer lock, so
        `seq` order is buffer order."""
        if event_id is None:
            return None
        self._seq += 1
        self.stats["inputs"] += 1
        ordinal = self._inputs_by_event.get(event_id, 0) + 1
        self._inputs_by_event[event_id] = ordinal
        self._last_seq_by_event[event_id] = self._seq
        try:
            venue_ms = int(venue_ts) if venue_ts is not None else None
        except (TypeError, ValueError):
            venue_ms = None
        mark = InputMark(
            seq=self._seq, event_id=event_id, outcome_id=outcome_id,
            probability=probability, kind=kind, recv_wall=_wall(),
            recv_mono=_mono(), venue_ts_ms=venue_ms, event_ordinal=ordinal,
        )
        try:
            self._count_input(mark)
        except Exception:
            # The delivery count is evidence about evidence; it must never cost
            # the caller the mark (#837's chain needs it).
            logger.warning("tail receipt: delivery count failed", exc_info=True)
        return mark

    # ── #10090 delivery receipt ──────────────────────────────────────────────

    def _bucket(self, event_id: int) -> dict:
        bucket = self._window.get(event_id)
        if bucket is None:
            observed_from = max(
                self._window_start if self._window_start is not None else self._run_start,
                self._run_start,
                self._live_since.get(event_id, self._run_start),
            )
            bucket = self._window[event_id] = {
                "raw": 0, "outcomes": {}, "stamps": [], "stamps_dropped": 0,
                "from": observed_from,
            }
        return bucket

    def _count_input(self, mark: InputMark) -> None:
        """Accepted, and whether it CHANGED this outcome's price: a repeat is a
        venue message at the price we already held — transport, not news. The
        first input of a run for an outcome has no prior and says so."""
        self._roll(mark.recv_wall)
        if mark.event_id not in self._live_events:
            return
        per = self._bucket(mark.event_id)["outcomes"].setdefault(
            mark.outcome_id, [0, 0, 0, 0],  # accepted, changed, repeats, first
        )
        per[0] += 1
        last = self._last_p.setdefault(mark.event_id, {})
        prior = last.get(mark.outcome_id)
        per[1 if prior is not None and prior != mark.probability
            else 2 if prior is not None else 3] += 1
        last[mark.outcome_id] = mark.probability
        self._uncovered.setdefault(
            mark.event_id, deque(maxlen=DELIVERY_RECEIPT_MAX_PENDING)
        ).append((mark.seq, mark.recv_wall))

    def _note_stamp(self, event_id: int, disposition: tuple) -> None:
        """A committed stamp: the published `rev`, its `stamped_at` (the SSE
        frame's `updated_at`, byte for byte), and the inputs it carried — every
        input of this event up to the newest committed one, so a stamp that
        coalesced many inputs says how many (`covered`) and how old the oldest
        was. Inputs that arrived after the committed one wait for the next."""
        rev = disposition[4] if len(disposition) > 4 else None
        status = disposition[5] if len(disposition) > 5 else None
        was_live = event_id in self._live_events
        mark = self._committed.pop(event_id, None)
        if len(disposition) > 6 and disposition[6] is False:
            # A queued fresh stamp reread the board. The staged input is not
            # joined to that reading; only the exact observation trace can
            # make that claim. Record the stamp without input coverage.
            mark = None
        if status == "live":
            if not was_live:
                self._live_since[event_id] = _wall()
            self._live_events.add(event_id)
        elif not was_live:
            return
        covered, oldest = 0, None
        pending = self._uncovered.get(event_id)
        if mark is not None and pending:
            while pending and pending[0][0] <= mark.seq:
                _seq, wall = pending.popleft()
                covered += 1
                if oldest is None:
                    oldest = wall
        if status is not None and status != "live":
            # This stamp is still the game's (its minute was live); after it,
            # nothing more is kept for the event.
            self._live_events.discard(event_id)
            self._uncovered.pop(event_id, None)
            self._last_p.pop(event_id, None)
            self._live_since.pop(event_id, None)
        self._roll(_wall())
        bucket = self._bucket(event_id)
        if len(bucket["stamps"]) >= DELIVERY_RECEIPT_MAX_STAMPS:
            bucket["stamps_dropped"] += 1
            return
        bucket["stamps"].append("@".join((
            "-" if rev is None else str(rev),
            str(disposition[2]),
            _iso(mark.recv_wall) if mark is not None else "-",
            _iso(oldest) or "-",
            str(covered),
        )))

    def _roll(self, wall: float, *, final: bool = False) -> None:
        """Close the UTC minute once the clock has left it (or at exit), one
        line per live event that had a message, an input or a stamp in it."""
        size = DELIVERY_RECEIPT_WINDOW_S
        if self._window_start is None:
            self._window_start = math.floor(wall / size) * size
            return
        if not final and wall < self._window_start + size:
            return
        window_end = wall if final else self._window_start + size
        # Only live games ever get a bucket (`note_raw`, `_count_input`,
        # `_note_stamp` all check); the most active are written.
        ranked = sorted(
            self._window,
            key=lambda eid: (-sum(v[0] for v in self._window[eid]["outcomes"].values()),
                             -len(self._window[eid]["stamps"]), eid),
        )
        kept = ranked[:DELIVERY_RECEIPT_MAX_EVENTS]
        for event_id in sorted(kept):
            self._emit(event_id, self._window[event_id], window_end)
        if len(ranked) > len(kept):
            logger.info(
                "live_blend_refresh[%s]: delivery-receipt-overflow run=%s "
                "window_start=%s events_dropped=%d dropped=%s",
                self.source, self.run, _iso(self._window_start),
                len(ranked) - len(kept), ",".join(map(str, sorted(ranked[len(kept):])[:50])),
            )
        self._window = {}
        self._window_start = math.floor(wall / size) * size

    def _emit(self, event_id: int, bucket: dict, window_end: float) -> None:
        """`window_start`/`window_s` are the seconds this run actually watched
        the game inside the minute — never the minute's floor before it."""
        per = bucket["outcomes"]
        totals = [sum(v[i] for v in per.values()) for i in range(4)]
        self.stats["delivery_lines"] += 1
        logger.info(
            "live_blend_refresh[%s]: delivery-receipt run=%s event=%s "
            "window_start=%s window_s=%.3f raw=%d accepted=%d changed=%d "
            "repeats=%d first=%d outcomes=%s stamps=%s stamps_dropped=%d",
            self.source, self.run, event_id, _iso(bucket["from"]),
            max(0.0, window_end - bucket["from"]),
            bucket["raw"], *totals,
            ",".join(f"{oid}:{v[0]}:{v[1]}:{v[2]}:{v[3]}" for oid, v in sorted(per.items()))
            or "-",
            ";".join(bucket["stamps"]) or "-", bucket["stamps_dropped"],
        )

    def stage(self, marks: Iterable[InputMark]) -> None:
        """The revisions a flush just COMMITTED — called after the commit and
        immediately before `refresh`, which takes them. Per event, the newest
        input the write carried."""
        self._staged, self._staged_wall = self.staged_for(marks)

    @staticmethod
    def staged_for(marks: Iterable[InputMark]) -> tuple[dict[int, InputMark], float]:
        """`stage`'s per-event newest mark, without taking the staging slot —
        for a cohort admitted into a refresh that already took its own."""
        staged: dict[int, InputMark] = {}
        for mark in marks:
            held = staged.get(mark.event_id)
            if held is None or mark.seq > held.seq:
                staged[mark.event_id] = mark
        return staged, _wall()

    def roll(self) -> None:
        """Close the delivery minute if the clock has left it. Every flush
        reaches here (via `take_staged` or `refresh_pending`), so a minute
        closes within a flush of its end even when no input arrives."""
        self._roll(_wall())

    def take_staged(self) -> tuple[dict[int, InputMark], Optional[float]]:
        self._roll(_wall())
        staged, wall = self._staged, self._staged_wall
        self._staged, self._staged_wall = {}, None
        return staged, wall

    # ── the refresher's side ─────────────────────────────────────────────────

    def _open_chain(self, origin, mark, stored_wall, now) -> _TailChain:
        chain = _TailChain(
            origin=origin, rev=mark, stamp_rev=mark,
            stored_wall=stored_wall if stored_wall is not None else _wall(),
            opened_wall=_wall(), opened_mono=now,
        )
        self._open[mark.event_id] = chain
        self.stats["opened"] += 1
        return chain

    def observe(self, staged, stored_wall, due: set, now: float) -> None:
        """Before the batch: a committed revision for an event with an open
        chain is a later write inside the hold; one for an event the throttle
        is holding opens a chain."""
        for event_id, mark in staged.items():
            held = self._committed.get(event_id)
            if event_id in self._live_events and (held is None or mark.seq > held.seq):
                self._committed[event_id] = mark
            chain = self._open.get(event_id)
            if chain is not None:
                chain.later_committed += 1
                chain.stamp_rev = mark
            elif event_id not in due:
                self._open_chain("throttle", mark, stored_wall, now)

    def resolve(self, due, dispositions, staged, stored_wall, now) -> None:
        """After a batch that COMMITTED: close each attempted chain on what the
        batch did with it. A lock skip keeps (or opens) the chain — the retry
        is the path, and it is counted."""
        for event_id in due:
            disposition = dispositions.get(event_id, ("no_market",))
            if disposition[0] == "stamped":
                try:
                    self._note_stamp(event_id, disposition)
                except Exception:
                    # Never at the expense of closing this or any other chain.
                    logger.warning("tail receipt: delivery stamp failed", exc_info=True)
            chain = self._open.get(event_id)
            if disposition[0] == "lock":
                if chain is None:
                    mark = staged.get(event_id)
                    if mark is None:
                        continue
                    chain = self._open_chain("lock", mark, stored_wall, now)
                chain.lock_retries += 1
                continue
            if chain is not None:
                self._close(event_id, disposition[0], now, disposition=disposition)

    def resolve_failed(
        self, due, dispositions, staged, stored_wall, requeued, exc, now,
    ) -> None:
        """After a batch that did NOT commit. A stamp the batch had made rolled
        back with it — `commit_failed`; otherwise the batch died first —
        `batch_failed`. The refresher retains all due events, so their chains
        stay open and count the failure. The defensive dropped result is only
        for a caller that explicitly omits an event from `requeued`."""
        for event_id in due:
            disposition = dispositions.get(event_id, ("",))
            failure = "commit_failed" if disposition[0] == "stamped" else "batch_failed"
            chain = self._open.get(event_id)
            if chain is None:
                mark = staged.get(event_id)
                if mark is None or event_id not in requeued:
                    continue
                origin = "lock" if disposition[0] == "lock" else "batch"
                chain = self._open_chain(origin, mark, stored_wall, now)
                if origin == "lock":
                    chain.lock_retries += 1
            if event_id in requeued:
                if failure == "commit_failed":
                    chain.commit_failures += 1
                else:
                    chain.batch_failures += 1
                continue
            self._close(event_id, f"dropped_{failure}", now, error=type(exc).__name__)

    def close_all(self, reason: str) -> None:
        """The consumer is exiting: every chain still open was never stamped by
        this run, and the next run's fresh refresher cannot inherit it."""
        now = _mono()
        open_at_close = len(self._open)
        for event_id in sorted(self._open):
            self._close(event_id, reason, now)
        # #10090 — the partial minute the run ended in, with its real length,
        # and the live games for the next run of this source.
        self._roll(_wall(), final=True)
        _live_handoff[self.source] = frozenset(self._live_events)
        logger.info(
            "live_blend_refresh[%s]: tail-receipt summary run=%s reason=%s "
            "inputs=%d opened=%d logged=%d coalesced=%d open_at_close=%d "
            "delivery_lines=%d",
            self.source, self.run, reason, self.stats["inputs"],
            self.stats["opened"], self.stats["logged"], self.stats["coalesced"],
            open_at_close, self.stats["delivery_lines"],
        )

    def _close(self, event_id, result, now, *, disposition=(), error=None) -> None:
        chain = self._open.pop(event_id)
        later_inputs = self._inputs_by_event.get(event_id, 0) - chain.rev.event_ordinal
        quiet = later_inputs == 0 and chain.later_committed == 0
        value = previous = stamped_at = None
        if result == "stamped":
            _, value, stamped_at, previous = disposition[:4]
        elif result in ("unchanged", "preview_only", "unobserved", "stale"):
            value = disposition[1]
        moved = result == "stamped" and (previous is None or previous != value)

        coalescible = (
            result in self.COALESCIBLE
            and not (result == "stamped" and quiet)
            and chain.origin != "lock"
            and not chain.lock_retries
            and not chain.commit_failures
            and not chain.batch_failures
        )
        if coalescible:
            last = self._last_logged.get(event_id)
            if last is not None and (now - last) < self.coalesce_s:
                self._coalesced[event_id] = self._coalesced.get(event_id, 0) + 1
                self.stats["coalesced"] += 1
                return
            self._last_logged[event_id] = now

        self.stats["logged"] += 1
        rev, stamp_rev = chain.rev, chain.stamp_rev
        logger.info(
            "live_blend_refresh[%s]: tail-receipt run=%s event=%s result=%s "
            "quiet=%s moved=%s origin=%s rev_seq=%d rev_outcome=%s rev_p=%.6f "
            "rev_kind=%s rev_recv_wall=%s rev_venue_ts_ms=%s stored_wall=%s "
            "held_wall=%s stamp_rev_seq=%s stamped_at=%s value=%s previous=%s "
            "later_inputs=%d later_committed=%d last_input_seq=%s "
            "lock_retries=%d commit_failures=%d batch_failures=%d held_s=%.3f "
            "recv_to_close_s=%.3f coalesced=%d error=%s",
            self.source, self.run, event_id, result, quiet, moved, chain.origin,
            rev.seq, rev.outcome_id, rev.probability, rev.kind,
            _iso(rev.recv_wall), rev.venue_ts_ms, _iso(chain.stored_wall),
            _iso(chain.opened_wall),
            "-" if len(disposition) > 6 and disposition[6] is False else stamp_rev.seq,
            stamped_at, value, previous,
            later_inputs, chain.later_committed,
            self._last_seq_by_event.get(event_id), chain.lock_retries,
            chain.commit_failures, chain.batch_failures,
            now - chain.opened_mono, now - rev.recv_mono,
            self._coalesced.pop(event_id, 0), error,
        )


def atomic_stamp_expression(
    source: str, value: float, stamped_at=None, eligibility=None,
    observed_basis=None,
):
    """The SET expression that stamps ONE source key WITHOUT reading it first.

    live/305's defect, reproduced against real Postgres 2026-09-16: the Kalshi
    and Polymarket consumers run under one `asyncio.gather`
    (`run_kalshi_ws.py`), each owning its own `LiveBlendRefresher`, and each was
    doing SELECT -> merge in Python -> write the whole column back. Two arms
    that read the same snapshot and write 250 ms apart produce this:

        kalshi arm's private view : {'betting': 0.5, 'kalshi': 0.53}
        pm arm's private view     : {'betting': 0.5, 'polymarket': 0.52}
        WHAT THE DATABASE KEPT    : {'betting': 0.5, 'polymarket': 0.52}

    The later writer does not merely overwrite a stale sibling VALUE — it drops
    the sibling key the earlier writer just created, because the dict it merged
    into never contained it. That is the whole of the reported hero flicker: the
    same question published 89 ms apart as 0.51 and 0.475, each arm blending its
    own fresh price against a view of the other that the database no longer
    holds. It also explains the direction, which a simple staleness story cannot
    — the Kalshi arm held the HIGHER own price (0.53 vs 0.52) and published the
    LOWER aggregate, because its private copy had no Polymarket reading in it at
    all.

    So the merge moves to the server. ``a || b`` on JSONB is evaluated inside the
    UPDATE, and under READ COMMITTED a concurrent UPDATE on the same row blocks,
    then re-evaluates this expression against the row the winner committed —
    the same reason ``SET n = n + 1`` is safe where read-modify-write is not.
    Two arms can no longer erase each other no matter how they interleave.

    The semantics are `aggregation.stamp_source_reading`'s, expressed in SQL,
    and they must stay that way: the top-level `||` copies every sibling SOURCE
    through untouched, and the inner `||` copies every sibling KEY inside this
    source's own entry through untouched (`weight`, `home_probability`, and the
    eligibility record a writer that has not adopted it must never strip). A
    `None` eligibility omits the key rather than writing a null, so it cannot
    clear a record another writer left — the same non-destructive rule the
    Python helper documents.

    ``observed_basis`` follows the Python helper's OPPOSITE rule for that key
    (#8910): given, it is written bound to ``value``; omitted, any basis on the
    entry is removed, so a writer that cannot date its reading never leaves the
    previous reading's observation attached to a new value.
    """
    import json

    from sqlalchemy import Text, case, cast, func, literal, type_coerce
    from sqlalchemy.dialects.postgresql import JSONB

    from app.models.models import Event
    from app.utils.aggregation import OBSERVED_BASIS_KEY, OBSERVED_VALUE_KEY
    from app.utils.probability_eligibility import ELIGIBILITY_KEY

    # Production stamps inside the UPDATE, not before waiting for its row lock.
    # READ COMMITTED re-evaluates this expression against a concurrent updater's
    # committed tuple. A pre-lock Python clock can otherwise make the NEWER
    # aggregate look like an older replay to the phone (#837).
    # Explicit clocks remain available for deterministic historical/helper use.
    entry: dict = {"value": value}
    if stamped_at is not None:
        entry["updated_at"] = stamped_at.isoformat()
    if eligibility is not None:
        entry[ELIGIBILITY_KEY] = eligibility.to_entry()
    if observed_basis:
        entry[OBSERVED_BASIS_KEY] = dict(observed_basis)
        entry[OBSERVED_VALUE_KEY] = value

    empty = cast(literal("{}"), JSONB)

    def as_object(expression):
        """`isinstance(x, dict)`, in SQL. COALESCE is NOT enough here.

        The column is nullable with no default, so it can hold SQL NULL *or*
        the JSONB scalar `null` — and `||` does not treat the second as empty,
        it PROMOTES it: `'null'::jsonb || '{"k":"v"}'::jsonb` evaluates to
        `[null, {"k": "v"}]`. A COALESCE-only guard would therefore turn the
        blend column into an ARRAY on the first stamp of such a row, which the
        Python helper's `dict(sources or {})` / `isinstance(existing, dict)`
        never could. Caught by the real-Postgres gate, not by review.
        """
        return case((func.jsonb_typeof(expression) == "object", expression), else_=empty)

    column = Event.win_probability_sources
    entry_expression = cast(literal(json.dumps(entry)), JSONB)
    if stamped_at is None:
        entry_expression = entry_expression.concat(
            func.jsonb_build_object("updated_at", func.clock_timestamp())
        )
    prior_entry = as_object(column[source])
    if not observed_basis:
        for key in (OBSERVED_BASIS_KEY, OBSERVED_VALUE_KEY):
            prior_entry = type_coerce(
                prior_entry.op("-")(cast(literal(key), Text)), JSONB
            )
    merged_entry = prior_entry.concat(entry_expression)
    return as_object(column).concat(
        func.jsonb_build_object(cast(literal(source), Text), merged_entry)
    )


def observation_admits_clause(source: str, observed_basis):
    """WHERE clause: the stored entry saw none of these rows LATER than this reading.

    #8910 (F3 of the other-writers review, plus Codex's re-observation
    variant). This lane reads its rows, orients, then stamps; the two-minute
    poll can re-observe the venue after a goal, compare under its row lock and
    stamp the post-goal price inside that window. The stamp that followed wrote
    the pre-goal price with the NEWEST clock — the worst shape, because every
    clock guard downstream (the poll's, the phone's #920 ordering, the chart's
    strictly-newer rule) then trusts the older price. The unchanged re-stamp arm
    does the same when the lane re-observed the old value before the poll wrote.

    The decision therefore lives IN the stamping UPDATE rather than in a read
    before it: under READ COMMITTED an UPDATE that waited on the poll's lock
    re-evaluates its WHERE against the row the poll committed, so the comparison
    holds at the commit with no lock of this lane's own and no extra round trip.
    It is `aggregation.reading_regresses_stored_observation` in SQL, and must
    stay that: per contributor, the stored basis trusted only while bound to a
    NUMERIC stored value (Codex, on 30162c4dd6: JSON equality alone trusted
    `"0.6" = "0.6"`, `true = true` and `null = null`, which the Python rule
    abstains on — a malformed entry would then refuse the very write that
    repairs it; a jsonb number is always finite, so `number` is the whole of
    `_finite_number`), a non-number clock on either side ignored (never cast — a
    malformed stored string must not abort the batch), and no shared row means
    no opinion.

    ``None`` when this reading has no basis: the stamp then runs unguarded, as
    it always has, and strips the old basis (`atomic_stamp_expression`).
    """
    from sqlalchemy import bindparam, text
    from sqlalchemy.dialects.postgresql import JSONB

    from app.utils.aggregation import OBSERVED_BASIS_KEY, OBSERVED_VALUE_KEY

    if not observed_basis:
        return None
    entry = (
        "(CASE WHEN jsonb_typeof(events.win_probability_sources) = 'object' "
        "AND jsonb_typeof(events.win_probability_sources -> :obs_source) = 'object' "
        "THEN events.win_probability_sources -> :obs_source "
        "ELSE '{}'::jsonb END)"
    )
    stored_basis = (
        f"(CASE WHEN jsonb_typeof({entry} -> '{OBSERVED_BASIS_KEY}') = 'object' "
        f"AND jsonb_typeof({entry} -> 'value') = 'number' "
        f"AND {entry} -> '{OBSERVED_VALUE_KEY}' = {entry} -> 'value' "
        f"THEN {entry} -> '{OBSERVED_BASIS_KEY}' ELSE '{{}}'::jsonb END)"
    )
    return text(
        "NOT EXISTS (SELECT 1 "
        f"FROM jsonb_each({stored_basis}) AS stored_seen(row_key, seen) "
        "JOIN jsonb_each(:obs_basis) AS this_seen(row_key, seen) "
        "ON this_seen.row_key = stored_seen.row_key "
        "WHERE jsonb_typeof(stored_seen.seen) = 'number' "
        "AND jsonb_typeof(this_seen.seen) = 'number' "
        "AND (stored_seen.seen)::numeric > (this_seen.seen)::numeric)"
    ).bindparams(
        bindparam("obs_source", value=source),
        bindparam("obs_basis", value=dict(observed_basis), type_=JSONB),
    )


def restamp_records_no_observation(
    value: float, observed_at, sources, source: str,
) -> bool:
    """True when stamping ``value`` now would re-date a price nobody re-read.

    #5661, production 2026-09-26 14:24Z, Slovenia v Scotland (15290677): the
    moneyline's three Polymarket rows were last written at 13:28Z and Gamma was
    trading Slovenia at 0.225, while the served `polymarket` leg read 0.405
    stamped 14:24:35Z. This lane is handed an event whenever ANY of its
    outcomes flushes — the exact-score and corners books were ticking — so it
    recomputed 0.405 from the frozen moneyline, found it unchanged, and the
    45-second re-stamp above dated it with the database clock. It also drew a
    fresh 0.405 chart point each time, so the source line ran flat to the edge
    and looked current.

    That is #4028's forgery arriving through the one writer its fix never
    reached — the 120s poll and the 15-minute matcher both stamp
    `oldest_observation_time` — and here it does a second kind of damage: the
    poll orders its population stalest-first by exactly this stamp and drops
    the freshest end when its fetch window closes (2,534 Polymarket rows that
    pass). A forged-fresh stamp therefore parks the event behind every other
    game, so the one writer that WOULD re-read Gamma never reaches it. The
    fake heartbeat is what keeps the real refresh away.

    So the rule `source_observation_time` states — a re-stamp is only honest
    when it records a re-observation — applies here too: an UNCHANGED value may
    be re-stamped only if the rows it came from were seen AFTER the stamp the
    row already carries. A socket tick or a poll touch writes `last_updated`,
    so a quiet-but-healthy book still re-stamps; a book no writer has seen does
    not. Nothing is lost on weight: the hero's relative decay has a 10-minute
    grace, and the leg that ages past it is exactly the one that should.

    Deliberately narrow, and it ABSTAINS (returns False, i.e. today's
    behaviour) whenever it cannot know:

    * a MOVED value is never refused — every real move keeps #837's database
      clock, which the clients use to order frames;
    * ``observed_at`` None (a contributor that cannot say when it was seen,
      `oldest_observation_time`'s contract) or no parseable stored entry means
      there is nothing to compare, and "unknown" is not "stale".
    """
    from app.utils.aggregation import parse_source_entry

    if observed_at is None or not isinstance(sources, dict):
        return False
    stored_value, stored_at = parse_source_entry(sources.get(source))
    if stored_value is None or stored_at is None:
        return False
    if round(stored_value, 4) != value:
        return False
    return observed_at <= stored_at


def heartbeat_deadline(max_gap_s: float, sample_interval_s: float) -> float:
    """The age at which an unchanged value must be re-recorded, given sampling.

    A deadline is not the same thing as a sampling period, and setting the two
    equal quietly misses the bar. This path only *checks* every
    ``sample_interval_s``, so a deadline of exactly ``max_gap_s`` is first
    observed to be breached one whole sample LATE — the real worst-case gap
    becomes ``max_gap_s + sample_interval_s``. Subtracting the period means the
    sample that crosses the deadline lands at or before it, so the guarantee the
    caller asked for is the guarantee the table gets.
    """
    return max(1.0, float(max_gap_s) - float(sample_interval_s))


@dataclass(frozen=True)
class _ChartMarket:
    name: Optional[str]
    id: Optional[int]


@dataclass(frozen=True)
class _ChartOutcome:
    name: Optional[str]


@dataclass(frozen=True)
class _ChartReading:
    home_probability: Optional[float]
    away_probability: Optional[float]
    draw_probability: Optional[float]
    yes_probability: Optional[float]
    market: _ChartMarket
    outcome: _ChartOutcome
    snapshot_observed_at: object
    owned_history: bool = True
    #: #11181 — this point's `owed_chart_points` row, settled with the point.
    custody_id: Optional[int] = None


def _chart_reading(reading, observed_at):
    """Freeze only chart scalars before the stamp session closes (#10090)."""
    market = getattr(reading, "market", None)
    outcome = getattr(reading, "outcome", None)
    return _ChartReading(
        home_probability=getattr(reading, "home_probability", None),
        away_probability=getattr(reading, "away_probability", None),
        draw_probability=getattr(reading, "draw_probability", None),
        yes_probability=getattr(reading, "yes_probability", None),
        market=_ChartMarket(
            name=getattr(market, "name", None),
            id=getattr(market, "id", None),
        ),
        outcome=_ChartOutcome(name=getattr(outcome, "name", None)),
        snapshot_observed_at=observed_at,
    )


class OwedChartCustody:
    """#11181 — durable custody of committed chart observations.

    WHY. A committed stamp owes its chart point at its own observation time,
    and the chart writer can be held for seconds by another transaction's lock
    on `win_prob_snapshots` (production v5763 13:01:22Z: Kalshi's writer held
    5.364 s at 64 owed). Memory alone cannot meet an unwaiting headline, every
    observation and a finite bound at once, and it empties on a restart. So
    each owed point is also a row in `owed_chart_points`:

    * `record` INSERTs it inside the stamp's own event scope. The stamp commits
      only with its row and a failed INSERT fails the stamp. The table has no
      foreign key, so the insert takes no lock on the event or on any chart row.
    * `settle` DELETEs it first, in the same savepoint that writes the point.
      A row that is gone was already paid (a commit whose acknowledgement a
      crash lost, or another process's drain), and nothing is written twice.
    * `load` reads this source's rows that memory does not hold, oldest commit
      id first, so the drain recovers what past the memory bound or through a
      restart lives only here, in each event's own order.
    """

    async def record(self, session, source: str, event_id: int, value, reading) -> int:
        from sqlalchemy import insert

        from app.models.models import OwedChartPoint

        return (
            await session.execute(
                insert(OwedChartPoint)
                .values(
                    source=source,
                    event_id=event_id,
                    value=value,
                    reading=_chart_reading_payload(reading),
                )
                .returning(OwedChartPoint.id)
            )
        ).scalar_one()

    async def settle(self, session, custody_id: int) -> bool:
        from sqlalchemy import delete

        from app.models.models import OwedChartPoint

        return (
            await session.execute(
                delete(OwedChartPoint)
                .where(OwedChartPoint.id == custody_id)
                .returning(OwedChartPoint.id)
            )
        ).first() is not None

    async def load(self, session, source: str, held_ids, limit: int) -> list[tuple]:
        from sqlalchemy import select

        from app.models.models import OwedChartPoint

        query = select(
            OwedChartPoint.id, OwedChartPoint.event_id,
            OwedChartPoint.value, OwedChartPoint.reading,
        ).where(OwedChartPoint.source == source)
        if held_ids:
            query = query.where(OwedChartPoint.id.not_in(sorted(held_ids)))
        rows = await session.execute(query.order_by(OwedChartPoint.id).limit(limit))
        return [tuple(row) for row in rows.all()]


def _chart_reading_payload(reading) -> dict:
    """The frozen chart scalars as JSON; the observation time stays verbatim."""
    observed_at = reading.snapshot_observed_at
    if isinstance(observed_at, datetime):
        observed_at = observed_at.isoformat()
    return {
        "home_probability": reading.home_probability,
        "away_probability": reading.away_probability,
        "draw_probability": reading.draw_probability,
        "yes_probability": reading.yes_probability,
        "market_name": reading.market.name,
        "market_id": reading.market.id,
        "outcome_name": reading.outcome.name,
        "observed_at": observed_at,
    }


def _chart_reading_from_payload(custody_id: int, payload: dict) -> _ChartReading:
    return _ChartReading(
        home_probability=payload.get("home_probability"),
        away_probability=payload.get("away_probability"),
        draw_probability=payload.get("draw_probability"),
        yes_probability=payload.get("yes_probability"),
        market=_ChartMarket(name=payload.get("market_name"), id=payload.get("market_id")),
        outcome=_ChartOutcome(name=payload.get("outcome_name")),
        snapshot_observed_at=payload.get("observed_at"),
        custody_id=custody_id,
    )


#: #10090 — float tolerance on the per-event floor when it is read on the
#: flush-start clock. Consecutive starts are `period` apart by construction
#: (`run_flush_cadence`), but `(t + p) - t` can come back short of `p` at
#: dyno-uptime magnitudes when `p` is not a power of two (`WS_PRICE_FLUSH_SECONDS`
#: is an env knob: t = 1,000,000.1, p = 0.1 gives 0.09999999997671694), which
#: would throttle the very flush the floor is meant to admit. A microsecond is
#: far below any real cadence.
FLUSH_CLOCK_SLACK_S = 1e-6


async def run_flush_cadence(
    flush, period: float, stop=None, *, failed_retry_interval_s: Optional[float] = None,
    wake=None, work_count: Optional[Callable[[], int]] = None,
    wake_coalesce_s: Optional[float] = None,
) -> None:
    """#10090 — start a flush every ``period`` seconds, START to START.

    WHY. Both sockets used to `sleep(PRICE_FLUSH_SECONDS)` AFTER each flush
    finished, so the real cycle was the period PLUS the flush's own work, and a
    tick arriving just after a batch was taken waited for both. Production
    2026-10-06 16:01:37→16:02:37Z, the Kalshi stats line: 29→37 flushes in 60 s
    with ~4,600 updates buffered in that minute — one flush per ~7.5 s on a 2 s
    setting, i.e. ~5.5 s of work plus the 2 s sleep on every cycle. The work is
    not removed here; the sleep stops being added on top of it.

    WHAT IS PRESERVED.

    * One flush at a time. The next starts only after the current one returns,
      so a slow flush makes the next start late — never two in flight — and the
      buffer keeps coalescing per outcome meanwhile (backpressure unchanged).
    * The ceiling. Actual work starts at most once per ``period``. Unchanged
      callers count every flush; opt-in callers distinguish empty probes from
      attempted work. A flush taking longer than ``period`` is followed by
      the next at once (rate ``1/work``, not more).
    * The retry interval. A flush that reports failure (returns ``False``) waits
      a full ``period`` from when it FAILED, exactly as before. An opt-in caller
      may pass ``failed_retry_interval_s`` to keep its previous retry delay while
      shortening only its healthy timer (#10662). Unchanged callers retain their
      configured period, including custom periods.
    * Unchanged callers first flush one ``period`` after the loop starts.
      An opt-in wake may start unused budget sooner, including after idle.
    * An opt-in ``wake_coalesce_s`` gives a woken flush ONE fixed pause before
      it starts, so frames already arriving in the same burst (both legs of a
      game sent back to back) enter the buffer before it snapshots. Without it
      the wake ran between two such frames: the event stamped half-updated and
      its second leg waited out the per-event floor (9aab164651). The pause is
      fixed, never extended by later arrivals, never waits for a missing leg,
      and applies only to a wake — timer, retry and back-to-back flushes under
      continuous input never pay it.

    ``flush`` is called with the flush's start on the refresher's clock
    (`_mono`), which the refresher uses for its per-event floor. Actual work
    starts remain at least ``period`` apart; an empty probe stamped nothing,
    so a subsequent input may wake sooner without bypassing that floor.

    #10657 — ``stop`` (an ``asyncio.Event``) ends the loop at its next turn.
    The consumer sets it before it cancels the loop, because a cancellation
    alone is not a stop: one lost inside a flush's dependencies left an
    earlier run's loop calling ``refresh_pending`` on that run's CLOSED
    sessions every 6 s on production (2026-10-07 02:53Z, 33 and 9 events,
    across a recycle). Checked after every sleep and every flush; a stopped
    loop never starts another flush — the consumer's own drain is the last.
    """
    # An opt-in buffered-input event may shorten only an unused timer phase.
    # `work_count` belongs to the caller: it increments inside the actual flush
    # when price/withdrawal/debt work was attempted. Empty timer probes therefore
    # cannot spend the real-work budget. No callback spawns a task per tick.
    # Unchanged callers still count every flush, with their original first wait.
    import asyncio

    def stopped() -> bool:
        return stop is not None and stop.is_set()

    retry_period = period if failed_retry_interval_s is None else failed_retry_interval_s
    due = _mono() + period
    not_before = _mono()  # no actual flush has used the budget yet
    while not stopped():
        wait = due - _mono()
        if wait > 0:
            if wake is None or _mono() < not_before:
                # Budget/retry waits never wake early. Ticks coalesce into the
                # same Event while this sleep retains the full fixed bound.
                await asyncio.sleep(wait)
            else:
                try:
                    async with asyncio.timeout(wait):
                        await wake.wait()
                except TimeoutError:
                    pass  # retain ordinary timer/debt probes during quiet input
                else:
                    wake.clear()
                    if wake_coalesce_s:
                        await asyncio.sleep(wake_coalesce_s)
                        if stopped():
                            return
                    due = _mono()
                    continue
            if stopped():
                return
        started = max(due, _mono())
        before = work_count() if work_count is not None else None
        if wake is not None:
            # Clear BEFORE the flush captures its batch. A tick during its
            # work sets the same bounded event for the next eligible turn.
            wake.clear()
        ok = await flush(started)
        used = work_count is None or work_count() != before
        due = started + period if ok is not False else _mono() + retry_period
        if used or ok is False:
            not_before = due


#: #10657 — how long a consumer waits, after its final drain, for its stopped
#: flush and stats loops to return. A loop mid-flush finishes that flush (its
#: sessions are still open until the consumer returns); one still running
#: after this is reported by name, never waited on forever.
LOOP_REAP_TIMEOUT_S = 15.0

#: #10090 idle bound: closed `HeldRowQuotes` samplers still unwinding their
#: cancellation, by source, until that source's run reaps its loops.
_closing_samplers: dict[Optional[str], set] = {}


def _park_closing_sampler(source: Optional[str], task) -> None:
    if task is not None and not task.done():
        _closing_samplers.setdefault(source, set()).add(task)


async def reap_stopped_loops(source: str, tasks, *, timeout_s: float = LOOP_REAP_TIMEOUT_S) -> int:
    """Wait (bounded) for a consumer run's stopped loops; return how many are
    STILL running. Never raises and never cancels again: the caller already
    set the stop event and cancelled them. A non-zero return is logged as an
    error because that loop outlives its run (#10657)."""
    import asyncio

    deadline = asyncio.get_running_loop().time() + timeout_s
    still: set = set()
    try:
        pending = [t for t in tasks if t is not None and not t.done()]
        if pending:
            try:
                _done, still = await asyncio.wait(pending, timeout=timeout_s)
            except Exception:
                still = {t for t in pending if not t.done()}
        if still:
            logger.error(
                "live_blend_refresh[%s]: %d consumer loop(s) still running %.0fs "
                "after the run stopped them: %s",
                source, len(still), timeout_s,
                sorted(getattr(t, "get_name", lambda: "?")() for t in still),
            )
    finally:
        # The run's closed idle samplers (`hand_off_pending`, replacement) join
        # here even when a cancellation lands on this reap (812/903 review).
        unreaped = await _join_closing_samplers(source, deadline)
    return len(still) + unreaped


async def _join_closing_samplers(source: Optional[str], deadline: float) -> int:
    """Join `source`'s closed idle samplers by `deadline`; return how many still run.

    A cancellation landing here is held until they finish or the budget ends,
    then re-raised. A sampler still running stays registered (its next reap
    owns it) and is logged; nothing is cancelled again.
    """
    loop = asyncio.get_running_loop()
    interrupted: Optional[BaseException] = None
    while True:
        pending = {t for t in _closing_samplers.get(source, ()) if not t.done()}
        if pending:
            _closing_samplers[source] = pending
        else:
            _closing_samplers.pop(source, None)
        remaining = deadline - loop.time()
        if not pending or remaining <= 0:
            break
        try:
            await asyncio.wait(pending, timeout=remaining)
        except asyncio.CancelledError as exc:
            interrupted = exc
    if pending:
        logger.error(
            "live_blend_refresh[%s]: %d idle bound sampler(s) still unwinding at the reap deadline",
            source, len(pending),
        )
    if interrupted is not None:
        raise interrupted
    return len(pending)


# Event context needed by the prepared resolver/stamp, including aggregate
# fallbacks. Unrelated score/metadata JSON must not ride every linked prop row.
PREPARED_EVENT_FIELDS = (
    "id",
    "home_team_name",
    "away_team_name",
    "status",
    "completed_at",
    "commence_time",
    "win_probability_sources",
    "espn_win_prob_home",
    "opening_home_probability",
)

# Resolver identity, semantic/settlement admission and exact observation clocks.
# Descriptions, images, calibration, volume and other presentation columns do
# not participate in the live reading and must not hydrate/copy on every quote.
PREPARED_MARKET_FIELDS = (
    "id", "source", "external_id", "event_id", "name", "status", "market_metadata",
)
PREPARED_OUTCOME_FIELDS = (
    "id", "market_id", "name", "rank", "current_probability", "last_updated", "is_winner",
    "external_id", "resolution_source",
)


class HeldRowQuotes:
    """#11138 — a received quote whose price-row write a lock holds.

    The stamp derives a source's value from `futures_outcomes`, so a foreign
    transaction holding one price row (catalog, rerank, resolution) held the
    blend with it: local real-PG lab on cdd20661, PM .82 reached the folded
    hero after 3.69 s while Kalshi, arriving 350 ms later, took 64 ms.

    ORDERED BY A DATABASE-CLOCK LOWER BOUND, NEVER BY WORKER WALL TIME. A
    `clock_timestamp()` sample that COMPLETED before an input was accepted is a
    lower bound for that input in the same clock domain as
    `futures_outcomes.last_updated` (written by `now()` on the same primary).
    The bound is frozen when the input is accepted (`note_input`) and carried
    with the flush's own chunk snapshot (`bound_for`), so a retry, a later
    sample or a newer tick on the same leg can never re-date it. A stored row
    at or after its bound is ambiguous: the stored row is kept and the ordinary
    price writer resolves the debt. No clock-offset estimate, no future stamp.

    WHOLE EVENT OR NOTHING (lane1 review B1/B2, 2026-10-17). Admission takes
    one event's legs from ONE chunk snapshot, and the overlay applies to every
    held leg of an event or to none (`overlay_event`), so a stamp never mixes
    two venue snapshots: on a three-way market that would print a field no
    venue ever quoted.

    Nothing uncommitted is published: the stamp that carries a held quote
    commits on the events row as before, with `observed_value` and a per-row
    `observed_basis` naming the bound. That committed stamp is the durability
    point; the price row is a projection the existing buffer keeps retrying.
    A later stamp built from the still-held row has an earlier basis and
    `observation_admits_clause` refuses it in the UPDATE, after a restart too,
    when this object is empty.

    Bounded: one input record per accepted outcome and one quote per held
    outcome, released when its write lands or its book is withdrawn.
    """

    #: One optional DB round trip per nonempty game chunk. A sample that times
    #: out backs later samples off. Preview owners get one early recovery
    #: opportunity; sustained failure then costs at most one timeout per long
    #: window however many chunks a flush plans.
    SAMPLE_TIMEOUT_S = 0.15
    SAMPLE_BACKOFF_S = 5.0
    #: One early recovery probe per preview-clock failure episode, then the
    #: existing long backoff. A brief DB timeout must not freeze observations
    #: for five seconds after reads recover. No accepted input is re-dated.
    SAMPLE_RECOVERY_S = 0.25
    #: #10090 — `stored_at_or_after` waits at most this for a relation lock.
    AMBIGUITY_READ_LOCK_TIMEOUT_MS = 10
    #: #10090 IDLE BOUND (Root page max, run 20261021T111728). Samples run only
    #: after a phase commits, so after a quiet spell the newest completed one is
    #: as old as the source's previous phase, and the first input after it
    #: previews THAT time (PM venue 11:18:01.262 printed 11:17:59.866). While
    #: an input for one of the owner's preview events arrived within
    #: IDLE_ACTIVE_S, ONE task per instance re-reads the same sample about
    #: every IDLE_SAMPLE_S (plus read time; grace and backoff stretch it — a
    #: period, not a latency guarantee), with the same timeout and backoff, on
    #: the same pool. It never starts a read while one is in flight; a phase
    #: may still start beside an idle read, and the ordinal keeps the newer.
    #: The semantics are unchanged: a sample that completed before
    #: acceptance, frozen at `note_input`. Lifecycle: `close()` latches; the
    #: owner's teardown (`hand_off_pending`) or replacement (the refresher's
    #: `held_quotes` setter) closes it and `reap_stopped_loops` joins it.
    IDLE_SAMPLE_S = 0.25
    IDLE_ACTIVE_S = 30.0
    #: An input noted after the last sample STARTED is owed its phase's own
    #: post-commit sample; the idle task leaves that phase this long first.
    IDLE_PHASE_GRACE_S = 1.0

    def __init__(self) -> None:
        self._quotes: dict[int, tuple[float, float]] = {}
        self._input_bounds: dict[int, tuple[int, float, float | None]] = {}
        self._database_bound: float | None = None
        self._sample_backoff_until = 0.0
        self._sample_failure_episode = False
        self._sample_failure_ordinal = 0
        self.sample_failures = 0
        # Idle bound (class doc). The owning refresher installs its CURRENT
        # preview events; empty means no idle sampling at all.
        self.preview_events: Callable[[], Container[int]] = frozenset
        self._sessions = None
        self._idle_task: Optional[asyncio.Task] = None
        self._closed = False
        self._sample_started = 0  # ordinal of the newest sample started
        self._sample_published = 0  # ordinal of the sample `_database_bound` holds
        self._graph_sample_ordinal = 0
        self._graph_idle_recovery_used = False
        self._sampling = 0
        self._last_sample_started = -math.inf
        self._last_sample_done = -math.inf
        self._last_input_at = -math.inf
        self._last_preview_input_at = -math.inf
        self.idle_samples = 0
        self.idle_skips = 0

    @staticmethod
    def _now() -> float:
        return time.monotonic()

    @staticmethod
    async def _sleep(seconds: float) -> None:
        await asyncio.sleep(seconds)

    async def sample_database_clock(self, sessions) -> bool:
        """Bounded read; only inputs accepted AFTER it completes may use it."""
        from sqlalchemy import func, select

        if self._now() < self._sample_backoff_until:
            return False
        if self._sample_failure_episode:
            if self._sampling:
                return False
            # Consume the recovery opportunity BEFORE the first await. A
            # concurrent caller or cancellation cannot multiply early probes.
            self._sample_backoff_until = self._now() + self.SAMPLE_BACKOFF_S
        self._sessions = sessions
        self._sample_started += 1
        ordinal = self._sample_started
        self._sampling += 1
        self._last_sample_started = self._now()
        try:
            async with asyncio.timeout(self.SAMPLE_TIMEOUT_S):
                async with sessions() as session:
                    value = (await session.execute(select(func.clock_timestamp()))).scalar_one()
                # Publish the sample only after the session has fully exited,
                # and never over one that STARTED later: an idle read that
                # overlapped a phase's post-commit read must not replace it.
                if ordinal > self._sample_published:
                    self._sample_published = ordinal
                    self._database_bound = value.timestamp()
                # A later graph may own the published timestamp, but a genuine
                # standalone success still proves this failure episode ended.
                if ordinal > self._sample_failure_ordinal:
                    self._sample_failure_episode = False
                    self._sample_backoff_until = 0.0
                    self._graph_idle_recovery_used = False
                self._last_sample_done = self._now()
                return True
        except Exception:
            # The ordinary price writer stays available when the optional fast
            # path cannot establish an order. Cancellation still propagates.
            self.sample_failures += 1
            if ordinal > self._sample_published:
                delay = (
                    self.SAMPLE_RECOVERY_S
                    if not self._sample_failure_episode and self.preview_events()
                    else self.SAMPLE_BACKOFF_S
                )
                self._sample_failure_episode = True
                self._sample_failure_ordinal = max(self._sample_failure_ordinal, ordinal)
                self._sample_backoff_until = max(
                    self._sample_backoff_until, self._now() + delay
                )
            return False
        finally:
            self._sampling -= 1

    def note_input(self, mark) -> None:
        """Freeze the newest completed sample as this input's lower bound."""
        self._input_bounds[mark.outcome_id] = (
            mark.seq, round(float(mark.probability), 6), self._database_bound,
        )
        now = self._now()
        self._last_input_at = now
        if getattr(mark, "event_id", None) in self.preview_events():
            self._last_preview_input_at = now
            self._start_idle_sampler()

    def _start_idle_sampler(self) -> None:
        if self._closed or self._sessions is None or (
                self._idle_task is not None and not self._idle_task.done()):
            return
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return
        self._idle_task = loop.create_task(self._idle_sampler(), name="held-quotes-idle-bound")

    async def _idle_sampler(self) -> None:
        """Keep the bound fresh while preview inputs arrive; exits by itself."""
        try:
            while not self._closed:
                now = self._now()
                graph_recovery_deadline = None
                if (now - self._last_preview_input_at >= self.IDLE_ACTIVE_S
                        or not self.preview_events()):
                    return
                due = self._last_sample_done + self.IDLE_SAMPLE_S
                if self._last_input_at > self._last_sample_started:
                    due = max(due, self._last_input_at + self.IDLE_PHASE_GRACE_S)
                if (self._sample_failure_episode and not self._sampling
                        and not self._graph_idle_recovery_used
                        and self._graph_sample_ordinal > self._sample_failure_ordinal
                        and now >= due
                        and now < self._sample_backoff_until
                        and now - self._last_preview_input_at >= self.IDLE_PHASE_GRACE_S):
                    # A successful graph is evidence for ONE recovery probe
                    # after traffic quiets, not a reset on every busy read.
                    # Consume before awaiting, including cancellation/failure.
                    self._graph_idle_recovery_used = True
                    graph_recovery_deadline = self._sample_backoff_until
                    self._sample_backoff_until = min(self._sample_backoff_until, now)
                due = max(due, self._sample_backoff_until)
                if now < due:
                    await self._sleep(min(due - now, self.IDLE_SAMPLE_S))
                    continue
                if self._sampling:
                    self.idle_skips += 1  # a phase's read is in flight
                    await self._sleep(self.IDLE_SAMPLE_S)
                    continue
                self.idle_samples += 1
                probe_ordinal = self._sample_started + 1
                try:
                    await self.sample_database_clock(self._sessions)
                finally:
                    if (graph_recovery_deadline is not None
                            and self._sample_failure_episode
                            and self._sample_failure_ordinal <= probe_ordinal):
                        # The extra attempt must not postpone the original
                        # retry, nor shorten a newer caller's failure episode.
                        self._sample_backoff_until = min(
                            self._sample_backoff_until, graph_recovery_deadline,
                        )
        except Exception:
            logger.warning("held quotes: idle bound sampler stopped", exc_info=True)

    def close(self) -> Optional[asyncio.Task]:
        """Latch closed and cancel the idle sampler; it never starts again.

        Returns the still-running task for the owner to join (or None).
        """
        self._closed = True
        task, self._idle_task = self._idle_task, None
        if task is None or task.done():
            return None
        task.cancel()
        return task

    def bound_for(self, mark) -> float | None:
        """This exact input's frozen bound, or None (another input, or none yet).

        Read under the consumer's buffer lock in the same block that snapshots
        the chunk's prices and marks, so the bound travels with the snapshot
        and a newer tick arriving during the write cannot drop one leg.
        """
        if mark is None:
            return None
        entry = self._input_bounds.get(getattr(mark, "outcome_id", None))
        if entry is None or entry[2] is None or entry[0] != getattr(mark, "seq", None):
            return None
        if entry[1] != round(float(mark.probability), 6):
            return None
        return entry[2]

    def hold(self, quotes: dict[int, tuple[float, float]]) -> set[int]:
        """Record ``{outcome_id: (price, frozen_bound)}``; returns ids that changed."""
        changed = set()
        for oid, (price, bound) in quotes.items():
            if bound is None:
                continue  # no completed sample preceded this input: no fast path
            # The price row stores NUMERIC(7, 6): read what it will hold.
            entry = (round(float(price), 6), float(bound))
            if self._quotes.get(oid) != entry:
                self._quotes[oid] = entry
                changed.add(oid)
        return changed

    def _new_bounds(self, quotes) -> dict[int, float]:
        """``{outcome_id: bound}`` for the quotes not already held as given."""
        return {
            oid: float(bound)
            for oid, (price, bound) in quotes.items()
            if bound is not None
            and self._quotes.get(oid) != (round(float(price), 6), float(bound))
        }

    def has_new_quotes(self, quotes) -> bool:
        """Whether admission may read (`stored_at_or_after`) or change a held
        observation. False exactly when that read would be skipped, so the
        Kalshi cadence (Root attempt32) counts only admission that can work."""
        return bool(self._new_bounds(quotes))

    async def stored_at_or_after(self, sessions, quotes) -> set[int] | None:
        """#10090 — the ids among NEW ``{outcome_id: (price, bound)}`` whose
        stored row is already at or after its bound: `_ambiguous`, read before
        the hold instead of inside the stamp.

        Held anyway, such a quote owed its event a stamp the overlay refuses,
        so it republished the stored row while the event fence kept the price
        write that carries the quote out (Root attempt20, real PG: the stored
        .70 stamp ran 171→580 ms, two retries fenced behind it, .82 published
        at 664 ms; attempt19 1000.563 ms). An unchanged quote is not read
        again. A row lock never blocks this read; a relation lock gets
        AMBIGUITY_READ_LOCK_TIMEOUT_MS. None means unknown: the caller holds
        as before. It shares the sample's backoff window both ways.
        """
        from sqlalchemy import select

        from app.models.models import FuturesOutcome
        from app.utils.aggregation import _coerce_timestamp
        from app.utils.repair_lock_budget import SET_LOCK_TIMEOUT_SQL, lock_timeout_value

        new = self._new_bounds(quotes)
        if not new:
            return set()
        if self._now() < self._sample_backoff_until:
            return None
        try:
            async with asyncio.timeout(self.SAMPLE_TIMEOUT_S):
                async with sessions() as session:
                    await session.execute(
                        SET_LOCK_TIMEOUT_SQL,
                        {"ms": lock_timeout_value(self.AMBIGUITY_READ_LOCK_TIMEOUT_MS)},
                    )
                    rows = (await session.execute(
                        select(FuturesOutcome.id, FuturesOutcome.last_updated)
                        .where(FuturesOutcome.id.in_(sorted(new)))
                    )).all()
        except Exception:
            # Shares the sample's window: a sick pool still costs one timeout
            # per window, and later sample attempts back off behind this one.
            self.sample_failures += 1
            self._sample_failure_episode = True
            self._sample_failure_ordinal = self._sample_started
            self._sample_backoff_until = self._now() + self.SAMPLE_BACKOFF_S
            return None
        found = set()
        for oid, last_updated in rows:
            stored = _coerce_timestamp(last_updated)
            if stored is not None and stored.timestamp() >= new[oid]:
                found.add(oid)
        return found

    def release(self, outcome_ids: Iterable[int]) -> None:
        for oid in outcome_ids:
            self._quotes.pop(oid, None)

    def __contains__(self, outcome_id) -> bool:
        return outcome_id in self._quotes

    def _ambiguous(self, outcome) -> bool:
        from app.utils.aggregation import _coerce_timestamp

        held = self._quotes.get(getattr(outcome, "id", None))
        if held is None:
            return False
        stored = _coerce_timestamp(getattr(outcome, "last_updated", None))
        return stored is not None and stored.timestamp() >= held[1]

    def overlay_event(self, entries) -> None:
        """Every held leg of one event, or none: one ambiguous leg defers all.

        ``entries`` are one event's `MarketOutcomes`. Each entry's outcome list
        is replaced by its overlaid copy; no outcome object is mutated.
        """
        entries = list(entries)
        if any(self._ambiguous(o) for entry in entries for o in entry.outcomes):
            return
        # #10090 (K1): bundled Challenger children are separate
        # contracts in one market. An unheld sibling committed after a held
        # leg's frozen bound makes that mixed snapshot ambiguous. Scope this
        # new refusal to the bundled branch; other venue/pair rules stay as-is.
        from app.utils.aggregation import _coerce_timestamp

        for entry in entries:
            market = getattr(entry, "market", None)
            ticker = (getattr(market, "external_id", None) or "").upper()
            if not (
                getattr(market, "source", None) == "kalshi"
                and ticker.startswith("KXATPCHALLENGERMATCH-")
                and len(ticker.split("-")) == 2
                and len(entry.outcomes) == 2
            ):
                continue
            bounds = [
                self._quotes[row.id][1] for row in entry.outcomes
                if getattr(row, "id", None) in self._quotes
            ]
            if len(bounds) != 1:
                continue
            for row in entry.outcomes:
                if getattr(row, "id", None) in self._quotes:
                    continue
                stored = _coerce_timestamp(getattr(row, "last_updated", None))
                if stored is not None and stored.timestamp() >= bounds[0]:
                    return
        for entry in entries:
            entry.outcomes[:] = [self.overlaid(o) for o in entry.outcomes]

    def overlaid(self, outcome):
        """This outcome as the stamp should read it: a COPY carrying the held
        quote when the stored row is strictly older than its bound, else the
        outcome itself.

        A copy and not an assignment, deliberately: the namespaces
        `_read_groups` builds are read material for one stamp, and nothing
        here may look like (or become) a write to a `futures_outcomes` row —
        the price row's only writer is the consumer's chunk UPDATE.
        """
        from datetime import datetime, timezone
        from types import SimpleNamespace

        held = self._quotes.get(getattr(outcome, "id", None))
        if held is None or self._ambiguous(outcome):
            return outcome
        price, bound = held
        return SimpleNamespace(**{
            **vars(outcome),
            "current_probability": price,
            "last_updated": datetime.fromtimestamp(bound, timezone.utc),
        })


class _FreshAdmission:
    """#10090 — the door a running `refresh` holds open for committed cohorts.

    One refresh owns the refresher at a time. A whole cohort its caller
    COMMITS after that refresh began joins it here (`admit_fresh`) instead of
    waiting for every earlier stamp to return. Fixed for the call: its flush
    clock, everything it took or admitted (``events``), its same-event fence
    (``holding``: those whose stamp is still queued or running; one that has
    returned may be admitted again, #10090), the FRESH_STAMP_WORKERS session
    slots every one of its stamp
    and preparation sessions holds, and its one frame sender. Each admitted
    event keeps its own staged input mark, retry origin and flush clock: a
    LATER flush's cohort may join while the call's own stamps are unfinished
    (``own_done``), and is stamped on its own flush's clock, never the call's.
    """

    def __init__(self, flush_started, clock, events, *, release_wake=None) -> None:
        import asyncio

        self.flush_started = flush_started
        self.clock = clock
        self.events: set[int] = set(events)
        self.holding: set[int] = set(events)
        #: Admitted events waiting for a stamp worker: live games (their
        #: latest read said live) in ``live_queue``, every other in ``queue``.
        self.queue: deque = deque()
        self.live_queue: deque = deque()
        self.live_run = 0
        self.workers: set = set()
        self.admitted: set[int] = set()
        self.retry: set[int] = set()
        self.completed: set[int] = set()
        self.failed: set[int] = set()
        self.staged: dict[int, InputMark] = {}
        self.stored_wall: dict[int, Optional[float]] = {}
        #: Each admitted event's own flush clock (its cohort's `flush_started`).
        self.clocks: dict[int, float] = {}
        #: Set once the call's own stamps have returned. #10090: it no longer
        #: closes the door — an admitted stamp held past it (a row lock, a slow
        #: frame) shut every later game out until it returned. The door closes
        #: when the admitted workers go idle (`_admission_join`) or when a
        #: lifecycle drain stops admitting (`stop_admitting`); either way the
        #: call then drains only what was queued before the close.
        self.own_done = False
        self.closed = False
        #: #10090 — the one owed (debt) event this call is stamping beside its
        #: admitted cohorts, if any: debt keeps progressing while a call lives
        #: on, but never holds more than one stamp worker.
        self.debt: Optional[int] = None
        self.publish: Optional[Callable[[list[dict]], Awaitable[None]]] = None
        self.publish_inline: Optional[Callable[[list[dict]], Awaitable[None]]] = None
        #: #10090 — per event, how many of its attempts in this call have
        #: returned (or gone back to debt), and a future resolved at the next
        #: one: a lifecycle wait drains a fixed frontier of attempts by these
        #: counts, so a re-admitted event's NEW attempt cannot extend it.
        self.released: dict[int, int] = {}
        self._released_signal = None
        #: #10090 functional release wake (the PM stamp owner's): told of
        #: every actual release so a game flush that fenced a newer quote on
        #: these events runs now, not at the next periodic timer.
        self.release_wake: Optional[Callable[[Iterable[int]], None]] = release_wake
        #: #10090 stage trace only (None unless one is configured): told of
        #: every actual release. Never raises into the fence.
        self.on_release: Optional[Callable[[Iterable[int]], None]] = None

    def next_queued(self) -> int:
        """The admitted event the next free worker stamps: the oldest live
        one, unless ADMITTED_LIVE_RUN live stamps in a row have started while
        a non-live one waited — then that oldest non-live one."""
        if self.live_queue and (not self.queue or self.live_run < ADMITTED_LIVE_RUN):
            if self.queue:
                self.live_run += 1
            return self.live_queue.popleft()
        self.live_run = 0
        return self.queue.popleft()

    def release(self, event_ids) -> None:
        """These events' stamps returned, or went back to debt unstamped."""
        self.holding.difference_update(event_ids)
        if self.debt is not None and self.debt in event_ids:
            self.debt = None
        for event_id in event_ids:
            self.released[event_id] = self.released.get(event_id, 0) + 1
        signal, self._released_signal = self._released_signal, None
        if signal is not None and not signal.done():
            signal.set_result(None)
        if self.release_wake is not None:
            self.release_wake(event_ids)
        if self.on_release is not None:
            with contextlib.suppress(Exception):
                self.on_release(event_ids)

    def released_signal(self):
        """A future resolved at this call's next `release`."""
        import asyncio

        if self._released_signal is None:
            self._released_signal = asyncio.get_running_loop().create_future()
        return self._released_signal


class _HoldingFrontier:
    """#10090 — the attempts one call holds (queued or running) at one instant.

    Drained once each has returned or gone back to debt. Counted per attempt,
    not read from `holding`: an event re-admitted after its frontier attempt
    returned is holding again, and waiting on `holding` would wait for that
    later attempt too — so continuous arrivals could extend the wait forever.
    """

    def __init__(self, window: "_FreshAdmission") -> None:
        self.window = window
        self.counts = {eid: window.released.get(eid, 0) for eid in window.holding}

    def drained(self) -> bool:
        released = self.window.released
        return all(released.get(eid, 0) > n for eid, n in self.counts.items())

    def changed(self):
        """A future resolved when one more attempt of this call returns."""
        return self.window.released_signal()


class LiveBlendRefresher:
    """Stateful per-source refresher, owned by one WS consumer run.

    State (throttles, inversion verdicts) is per-instance rather than global so
    the Kalshi and Polymarket consumers on the shared dyno cannot evict each
    other's entries, and so a reconnect starts clean.
    """

    @property
    def held_quotes(self) -> Optional[HeldRowQuotes]:
        return self.__dict__.get("_held_quotes")

    @held_quotes.setter
    def held_quotes(self, quotes: Optional[HeldRowQuotes]) -> None:
        previous = self.__dict__.get("_held_quotes")
        self.__dict__["_held_quotes"] = quotes
        if isinstance(previous, HeldRowQuotes) and previous is not quotes:
            # A replaced instance's idle sampler must not outlive it.
            _park_closing_sampler(getattr(self, "source", None), previous.close())
        if isinstance(quotes, HeldRowQuotes):
            # #10090 idle bound: this refresher's CURRENT preview events gate
            # the owner's idle sampler (legacy single-source and ledger alike).
            quotes.preview_events = lambda: getattr(self, "preview_events", frozenset())

    def __init__(
        self,
        source: str,
        *,
        owns_preview_maintenance: bool = True,
        min_refresh_interval_s: float = DEFAULT_MIN_REFRESH_INTERVAL_S,
        failed_retry_interval_s: float = DEFAULT_FAILED_RETRY_INTERVAL_S,
        inversion_ttl_s: float = DEFAULT_INVERSION_TTL_S,
        unchanged_restamp_interval_s: float = UNCHANGED_RESTAMP_INTERVAL_S,
        snapshot_interval_s: float = DEFAULT_SNAPSHOT_INTERVAL_S,
        snapshot_max_gap_s: float = DEFAULT_SNAPSHOT_MAX_GAP_S,
        stamp_lock_timeout_ms: Optional[int] = DEFAULT_STAMP_LOCK_TIMEOUT_MS,
        session_factory=None,
        observation_read_factory=None,
        chart_custody: Optional[OwedChartCustody] = None,
    ) -> None:
        self.source = source
        #: #11181 — durable custody of owed chart points. Both production
        #: consumers pass one (guarded); None keeps every owed point in memory.
        self._chart_custody = chart_custody
        #: Rows may exist that memory does not hold: past its bound, or from a
        #: run or process before this one, so a new refresher starts by reading.
        self._custody_backlog = chart_custody is not None
        #: Points committed to custody alone, or possibly committed (a stamp
        #: whose COMMIT outcome is unknown); a load that overlaps one cannot
        #: conclude the table is drained.
        self._custody_only_committed = 0
        #: Custody-only points committed by this process, by row id: the
        #: publication each still waits on, and (capped at the memory bound)
        #: its snapshot clock, so a load treats it exactly as memory would.
        self._custody_ready: dict[int, asyncio.Event] = {}
        self._custody_clock: dict[int, float] = {}
        #: #11138 — the owning consumer's `HeldRowQuotes`, or None (no overlay).
        self.held_quotes = None
        #: #10090 — the Kalshi WS owner's current-book proof for the bundled
        #: Challenger pair (`compute_source_home_probability`). Off unless the
        #: owner installs all of them before its first refresh can run: the
        #: requirement, the midpoint and primary-price readers, and the landed
        #: primary-quote reader (`current_primary_input(row, held, overlaid=)`).
        self.require_current_book_proof = False
        self.current_book_midpoint = None
        self.current_book_primary_price = None
        self.current_primary_input = None
        #: #11317 P2 — optional: ticker -> a comparable value of every
        #: in-memory input the proof reads for that ticker (book, accepted
        #: primary input, its custody, the held quote). Installed ⇒ a refused
        #: pair is PARKED until one of its values changes (or the shared sweep
        #: runs) instead of being read again every flush. None ⇒ the refusal
        #: re-queues on every flush, as before.
        self.current_book_signature = None
        #: Parked refused pairs: event id -> (tickers, signature at refusal).
        #: Still owed (handed off at a recycle), not yet worth a read.
        self._book_refused: dict[int, tuple] = {}
        self._book_refused_sweep_at: Optional[float] = None
        #: #2471 — the owning consumer's session factory, so the stamp borrows
        #: the consumer's one engine instead of building a pool per batch.
        #: None ⇒ ``app.tasks.base.get_task_session``, looked up per batch.
        self._session_factory = session_factory
        self._observation_read_factory = observation_read_factory
        self.min_refresh_interval_s = min_refresh_interval_s
        self.failed_retry_interval_s = failed_retry_interval_s
        self.inversion_ttl_s = inversion_ttl_s
        self.unchanged_restamp_interval_s = unchanged_restamp_interval_s
        self.snapshot_interval_s = snapshot_interval_s
        self.snapshot_max_gap_s = snapshot_max_gap_s
        #: None or 0 waits as long as Postgres lets it (the pre-#837-tail
        #: behaviour, kept reachable for the deadlock-containment rig).
        self.stamp_lock_timeout_ms = stamp_lock_timeout_ms
        #: Events whose stamp gave up on a lock. Carried into the NEXT refresh
        #: whatever that flush's batch holds: the price that was not stamped is
        #: already in `futures_outcomes`, so waiting for the event to tick again
        #: would strand it on a quiet market.
        self._lock_retry: set[int] = set()
        #: #837 tail — events whose price was written while their throttle was
        #: running. Stamped by the first flush after the throttle expires,
        #: whatever that flush's batch holds. Dropped instead, the stored price
        #: waited for another tick on ANY outcome of the game: production
        #: 2026-09-25 02:47:45–55Z, Padres @ Dodgers' 0.605 was written during
        #: the throttle; the moneyline sent nothing more until 02:47:57.5, so
        #: the stamp at 02:47:52 happened only because another of the game's
        #: markets ticked. On a quiet game the wait is the next tick or the
        #: 120s poll.
        self._throttle_deferred: set[int] = set()
        self._pending_continuation: list[int] = []
        self._pending_flush_started: Optional[float] = None
        self._pending_started_at: Optional[float] = None
        self._pending_attempted = False
        self._pending_attempts = 0
        self._pending_fresh_flush = False
        #: #10090 — the latest flush whose committed cohort a running call of
        #: an EARLIER flush admitted; that flush is fresh-bearing when its own
        #: `refresh` begins.
        self._admitted_fresh_flush: Optional[float] = None
        #: #10090 — the turn order of owed events riding a running call's
        #: door (`window.debt`): a newly owed event joins the back, and the one
        #: taken goes to the back, so a row lock that is due again at once
        #: cannot take every turn from a writable sibling.
        self._debt_rotation: list[int] = []
        self._last_refresh_at: dict[int, float] = {}
        #: Events whose last batch failed -> the monotonic time before which
        #: they are not due, whatever the throttle says.
        self._failed_hold_until: dict[int, float] = {}
        self._last_write_at: dict[int, float] = {}
        self._last_written_value: dict[int, float] = {}
        self._last_snapshot_at: dict[int, float] = {}
        # Local151 durable normal-price intent; no full frames retained in memory.
        self._normal_source = self.source + "_price_publish"
        self._normal_task = None
        self._normal_retry_at = 0.0
        self._normal_closed = False
        self._normal_has_debt = True  # one recovery discovery on startup
        self._normal_epoch = 0
        self._normal_after = 0
        self._normal_horizon = None
        # Positively acknowledged revisions, highest per event, settled by the
        # next recovery opportunity rather than on the publication path.
        self._normal_acked: dict[int, int] = {}
        # Revisions this process committed whose publication has not resolved
        # (held from before COMMIT). Discovery leaves them to that publication.
        self._normal_inflight: set[tuple[int, int]] = set()
        # One owner across refresh calls. A chart session cannot borrow slots
        # from a newer admission window or escape the three-session ceiling.
        self._session_slots = asyncio.Semaphore(FRESH_STAMP_WORKERS)
        self._history: list[tuple] = []
        self._history_task: Optional[asyncio.Task] = None
        self._history_count = 0  # committed debt plus pre-COMMIT reservations
        self._history_limit = HISTORY_POINT_LIMIT
        self._history_spill_limit = HISTORY_SPILL_LIMIT
        self._history_changed = asyncio.Event()
        self._history_reserved: dict[int, float] = {}
        self._history_retry_at: dict[int, float] = {}
        self._inversion: dict[int, tuple[float, bool]] = {}
        self.stats: dict[str, int] = {
            "considered": 0,
            "throttled": 0,
            "no_reading": 0,
            # #11317 — of `no_reading`, readings the bundled pair's current-book
            # proof withheld. `no_reading - bundled_refused` is every other cause.
            "bundled_refused": 0,
            "stamped": 0,
            "unchanged_skipped": 0,
            # #5661 — an unchanged value whose rows no writer has re-read since
            # the stored stamp. Not re-dated; see `restamp_records_no_observation`.
            "unobserved_skipped": 0,
            # #8910 — readings refused because the poll or the matcher had
            # already stored a later observation of the same rows.
            "stale_readings_refused": 0,
            "snapshots_written": 0,
            "snapshots_deduped": 0,
            "errors": 0,
            # live/034 S1 — SSE fanout. Counted so a publisher that is failing
            # every time is visible; a push path that dies quietly looks exactly
            # like a quiet market (gotcha #53).
            "published": 0,
            "publish_errors": 0,
            # #10090 — committed frames sent without `source_snapshot`
            # (no exact singleton revision, or a map that is not strict JSON).
            "source_snapshot_omitted": 0,
            # #837 tail — stamps that stopped waiting on another transaction's
            # row lock and were re-queued. Not an error: the retry is the path.
            "lock_skipped": 0,
            # #11138/#11181 — due chart points owed past the ordinary backlog
            # without waiting; each is still paid at its own time.
            "history_deferred": 0,
            # #11181 — due points carried by their custody row alone (past
            # the memory bound, or behind rows memory does not hold yet) until
            # a load moves them into memory in their event's order.
            "history_custody_only": 0,
            # #11181 — custody rows already settled when their point came up
            # (a commit whose acknowledgement was lost, or another drain).
            "history_already_paid": 0,
            # #10090 — owed points retired because their event row was deleted
            # after the stamp committed (seen on a retry only; ids never reuse).
            "history_event_gone": 0,
            # #9484 — committed market invalidations (`live:market:{id}`) this
            # consumer's writers published through the same client. Counted
            # for the same reason as `published`: a quiet market and a dead
            # market publisher must not look alike.
            "market_published": 0,
            "market_publish_errors": 0,
        }
        #: Lazily-built async Redis client, reused for the life of this
        #: refresher. Built on first publish rather than in __init__ so a
        #: consumer run that never stamps anything never opens a connection.
        self._redis = None
        #: #837 receipt — attached by a consumer that stamps its inputs
        #: (`TailReceipts`); None leaves this refresher exactly as it was.
        self.receipts: Optional[TailReceipts] = None
        #: What the current batch did with each event it attempted, for the
        #: receipt. Filled by `_refresh_batch`, read only after it returns.
        self._dispositions: dict[int, tuple] = {}
        #: #10090 — open only while a `refresh` runs (see `admit_fresh`).
        self._admission: Optional[_FreshAdmission] = None
        #: #10090 — events whose latest stamp read said live: admitted ones
        #: are stamped ahead of the rest (`_FreshAdmission.next_queued`).
        self._live_event_ids: set[int] = set()
        #: #10090 — the running call's same-event fence (`holding_event_ids`).
        #: None from a call's first turn until it opens its door.
        self._holding: Optional[set[int]] = None
        #: #10090 — resolved when the next call opens its door
        #: (`admission_opened`).
        self._admission_signal = None
        #: #10090 — optional callback notified when held events release so a
        #: socket flush loop that fenced a newer quote on those events wakes.
        self.release_wake: Optional[Callable[[Iterable[int]], None]] = None
        #: #10090 — provisional preview (`app.utils.blend_preview`): the
        #: supported sources validate every arriving event. The scope is
        #: stateless: events arriving after startup need no enrollment.
        from app.utils.blend_preview import PreviewEventScope, preview_events_for

        self.preview_events: PreviewEventScope | frozenset = preview_events_for(self.source)
        self.preview = bool(self.preview_events)
        # Short-lived transaction helpers have no task lifecycle to drain.
        # This ownership argument does not change DNPL eligibility or reads.
        self._owns_preview_maintenance = owns_preview_maintenance
        self._preview_maintenance_task = None
        self._preview_maintenance_after = 0.0
        self._preview_maintenance_closed = False
        self.preview_stats: dict[str, int] = {
            "published": 0, "revoked": 0, "fenced": 0, "publish_errors": 0,
        }

    # ── throttling ───────────────────────────────────────────────────────────

    def _due(self, event_id: int, now: float) -> bool:
        hold = self._failed_hold_until.get(event_id)
        if hold is not None:
            if now < hold:
                return False
            del self._failed_hold_until[event_id]
        last = self._last_refresh_at.get(event_id)
        return last is None or (
            (now - last) >= self.min_refresh_interval_s - FLUSH_CLOCK_SLACK_S
        )

    # ── inversion orientation, cached ────────────────────────────────────────

    async def _oriented(
        self, session, event_id: int, home_prob: float, *, reading=None,
        before_fallback: Optional[Callable[[], Awaitable[None]]] = None,
    ) -> float:
        """Apply the inversion verdict, computing it at most once per TTL.

        Returns the home probability the poll would have written. The verdict is
        cached as a BOOLEAN (did this linkage need flipping), not as a value —
        caching the value would pin a price, which is the opposite of the point.
        """
        from app.utils.live_blend import has_proven_home_orientation

        if reading is not None and has_proven_home_orientation(reading):
            # #8814: a stale book can disagree with a correctly named soccer
            # quote. Its cached binary flip would also erase the real draw.
            # Discard that contradicted verdict, including for later ticks
            # whose partial board no longer proves the named home orientation.
            self._inversion.pop(event_id, None)
            return reading.home_probability

        now = time.monotonic()
        cached = self._inversion.get(event_id)
        if cached is not None and now < cached[0]:
            return 1.0 - home_prob if cached[1] else home_prob

        from app.tasks.prediction_market_matching import _check_and_fix_inversion

        if before_fallback is not None:
            # Preserve the existing bound on the cold Event/OddsSnapshot reads.
            await before_fallback()
        corrected = await _check_and_fix_inversion(
            session, event_id, home_prob, self.source,
        )
        flipped = not math.isclose(corrected, home_prob, rel_tol=0.0, abs_tol=1e-9)
        self._inversion[event_id] = (now + self.inversion_ttl_s, flipped)
        return corrected

    # ── the refresh itself ───────────────────────────────────────────────────

    async def refresh(
        self, event_ids: Iterable[int], *, flush_started: Optional[float] = None,
        defer_event_ids: Iterable[int] = (),
    ) -> dict[str, int]:
        """Recompute and stamp the blend for these events. Never raises.

        #10090 — ``flush_started`` is the socket flush's start on `_mono`
        (`run_flush_cadence`). When given, the per-event floor, the failed-retry
        hold and the batch's own interval bookkeeping read THAT clock rather
        than the moment this call happens to run. Flush starts are a period
        apart; refresh calls are not — they trail their flush's write by
        whatever it cost, so a slow write followed by a fast one put two
        refreshes under the floor and the second flush's committed price waited
        a whole extra flush for its stamp. Receipts keep the real clock: they
        time the hold, not the schedule. Omitted, behaviour is unchanged.
        """
        self._start_history()
        self._holding = None
        now = _mono()
        clock = now if flush_started is None else flush_started
        receipts = self.receipts
        staged, stored_wall = (
            self._receipt_call(receipts.take_staged) if receipts is not None else None
        ) or ({}, None)
        self._wake_book_refused(now)
        retry = set(self._lock_retry)
        deferred = set(self._throttle_deferred)
        fresh = set(event_ids)
        wanted = fresh | retry | deferred
        # A caller may still be writing this event's price/withdrawal cohort.
        # Leave its fresh inputs and existing debt owed without reading a
        # partial board; ordinary callers retain the same admission behavior.
        excluded = set(defer_event_ids)
        due = [eid for eid in wanted if eid not in excluded and self._due(eid, clock)]
        self._pending_continuation = [
            eid for eid in self._pending_continuation if eid in wanted
        ]
        if flush_started != self._pending_flush_started:
            self._pending_flush_started = flush_started
            self._pending_started_at = None
            self._pending_attempted = False
            self._pending_attempts = 0
            self._pending_fresh_flush = (
                flush_started is not None
                and flush_started == self._admitted_fresh_flush
            )
        if flush_started is not None and fresh:
            # Sticky for the flush: old attempts made before its first fresh
            # call count against the same allowance, so none is added after.
            self._pending_fresh_flush = True

        def pending_budget_spent():
            if flush_started is None:
                return False
            if (
                self._pending_fresh_flush
                and self._pending_attempts >= FRESH_FLUSH_PENDING_ATTEMPTS
            ):
                return True
            return (
                self._pending_attempted
                and self._pending_started_at is not None
                and _mono() - self._pending_started_at >= PENDING_STAMP_BUDGET_S
            )

        # A flush can call refresh more than once. Once its old-work budget is
        # spent, leave all remaining debt owed without repeating its read. Fresh
        # committed prices are always admitted, even within that same flush.
        if pending_budget_spent():
            due = [eid for eid in due if eid in fresh]
        # A queued retry leaves the set only when a batch actually takes it.
        self._lock_retry = retry.difference(due)
        # A throttled event is owed the price it just had written, so it waits
        # for its throttle rather than for its next tick.
        self._throttle_deferred = wanted.difference(due)
        # A parked pair this batch reads is no longer parked; a refusal in
        # this read parks it again with the inputs it was refused on.
        for event_id in due:
            self._book_refused.pop(event_id, None)
        self.stats["considered"] += len(due)
        # Counted once per throttled price, not once per flush it waits out.
        skipped = len(self._throttle_deferred.difference(deferred))
        if skipped > 0:
            self.stats["throttled"] += skipped
        if receipts is not None:
            self._receipt_call(receipts.observe, staged, stored_wall, set(due), now)
        if self._stage_hook("stage_admission") is not None:
            self._stage_trace(
                "stage_admission", "REFRESH", None, wanted,
                due=due, excluded=excluded, fresh=fresh, flush_started=flush_started,
            )
        if not due:
            if self.release_wake is not None and wanted:
                self.release_wake(wanted)
            return self.stats

        self._dispositions = {}
        completed: set[int] = set()
        failed_groups: set[int] = set()
        budget_deferred: set[int] = set()
        publishing = None
        waiting_frames = []
        reread_events: set[int] = set()
        import asyncio

        publication_lock = asyncio.Lock()

        async def publication_done(*, cancel=False, cancel_on_interrupt=True):
            nonlocal publishing
            if publishing is None:
                return
            import asyncio

            if cancel and not publishing.cancelling():
                publishing.cancel()
            interrupted = None
            while not publishing.done():
                try:
                    await asyncio.wait({publishing})
                except CancelledError as exc:
                    interrupted = exc
                    if cancel_on_interrupt and not publishing.cancelling():
                        publishing.cancel()
            task, publishing = publishing, None
            if interrupted is not None:
                # Retrieve even an unexpected failure before propagating the
                # interruption; no publication task may outlive this refresh.
                if not task.cancelled():
                    task.exception()
                raise interrupted
            if task.cancelled():
                if not cancel:
                    raise CancelledError
            else:
                try:
                    task.result()
                except Exception:
                    self.stats["errors"] += 1
                    logger.exception(
                        "live_blend_refresh[%s]: publication task failed", self.source,
                    )

        async def publish_committed(frames):
            nonlocal publishing

            if not frames:
                return
            # Record definitely-unsent frames before waiting for ownership.
            # Concurrent stamps may commit, but only one sender owns the socket.
            waiting_frames.append(frames)
            async with publication_lock:
                await publication_done()
                waiting_frames.remove(frames)
                # No cancellation point between removing and submitting frames.
                publishing = self._publish_prices_task(frames)

        async def publish_inline(frames):
            # The singleton still sends its own frames before its stamp
            # returns. The lock only orders them with an admitted cohort's.
            async with publication_lock:
                await publication_done()
                await self._publish_prices(frames)

        def committed(group_ids):
            # Called synchronously AFTER COMMIT and cache installation, BEFORE
            # the first publication await. Interrupted delivery does not undo
            # a stored stamp or promise replay; _publish keeps its own contract.
            completed.update(group_ids)
            for event_id in group_ids:
                disposition = self._dispositions.get(event_id, ())
                if event_id in reread_events and disposition[:1] == ("stamped",):
                    self._dispositions[event_id] = disposition[:6] + (False,)
            if receipts is not None:
                self._receipt_call(
                    receipts.resolve,
                    group_ids,
                    self._dispositions,
                    staged,
                    stored_wall,
                    _mono(),
                )

        # #10090 — while this call runs, a cohort its caller commits later
        # joins it on a free stamp worker (`admit_fresh`) rather than waiting
        # for every stamp below to return. Its frames go through this call's
        # one sender; its sessions share this call's FRESH_STAMP_WORKERS slots.
        window = _FreshAdmission(flush_started, clock, due, release_wake=self.release_wake)
        window.publish = publish_committed
        window.publish_inline = publish_inline
        if self._stage_hook("attempt_released") is not None:
            window.on_release = lambda ids: self._stage_trace("attempt_released", ids)
        self._admission = window
        self._holding = window.holding
        not_due = wanted.difference(due)
        if not_due and self.release_wake is not None:
            self.release_wake(not_due)
        signal, self._admission_signal = self._admission_signal, None
        if signal is not None and not signal.done():
            signal.set_result(None)
        interrupted = False
        try:
            # One event already owns its transaction. For multiple admitted events,
            # prepare once and commit each independently so a later row lock cannot
            # hold an earlier stamp or its publication until the batch ends.
            if len(due) == 1:
                pending_only = due[0] not in fresh
                if pending_only and flush_started is not None:
                    if self._pending_started_at is None:
                        self._pending_started_at = _mono()
                    self._pending_attempted = True
                    self._pending_attempts += 1
                self._pending_continuation = [
                    eid for eid in self._pending_continuation if eid not in due
                ]
                try:
                    await self._refresh_batch(due, clock)
                except CancelledError as exc:
                    # #10090 review: a recycle can cancel this stamp after its
                    # prices committed and left the buffer, so no later input
                    # re-asks for it. Keep it owed for the hand-off exactly as the
                    # grouped arm below does, with the retry/deferred work it took.
                    # A cancel that lands after COMMIT (while publishing) costs one
                    # redundant re-stamp, never a lost one.
                    self._refresh_failed(
                        due,
                        retry,
                        clock,
                        receipts,
                        staged,
                        stored_wall,
                        exc,
                        hold=False,
                    )
                    failed_groups.update(due)
                    raise
                except Exception as exc:
                    self.stats["errors"] += 1
                    logger.exception("live_blend_refresh[%s]: batch failed", self.source)
                    self._refresh_failed(
                        due,
                        retry,
                        clock,
                        receipts,
                        staged,
                        stored_wall,
                        exc,
                    )
                    failed_groups.update(due)
                else:
                    completed.update(due)
                    if receipts is not None:
                        self._receipt_call(
                            receipts.resolve,
                            due,
                            self._dispositions,
                            staged,
                            stored_wall,
                            _mono(),
                        )
                finally:
                    window.release(due)

            # Read/stamp fresh prices before reading older debt. Each nonempty
            # population prepares one view for order and the initial worker
            # claims. Queued fresh stamps reread below; old debt and the
            # singleton path above keep their existing read behavior.
            populations = () if len(due) == 1 else (
                fresh.intersection(due), set(due).difference(fresh),
            )
            for population in populations:
                if not population:
                    continue
                pending_only = population.isdisjoint(fresh)
                if pending_only and pending_budget_spent():
                    # A repeated mixed call may have consumed the remaining
                    # budget on its fresh work since the admission check above.
                    # Do not read old debt when no old stamp can be attempted.
                    budget_deferred.update(population)
                    self._lock_retry.update(population.intersection(retry))
                    self._throttle_deferred.update(population.difference(retry))
                    window.release(population)
                    continue
                if pending_only and flush_started is not None:
                    if self._pending_started_at is None:
                        self._pending_started_at = _mono()
                # A fresh-bearing flush with one old attempt left and a due
                # continuation head attempts exactly that head, which the
                # shared read below could not reorder. It reads its own group,
                # as a singleton does, instead of first reading every old
                # event. The rest stay owed in their continuation order; debt
                # without one gets its live-first order from a later read. A
                # single old event without a head has no order to decide
                # either, so it reads its own group the same way.
                carried = [
                    eid for eid in self._pending_continuation if eid in population
                ]
                head = None
                if (
                    pending_only
                    and flush_started is not None
                    and self._pending_fresh_flush
                    and FRESH_FLUSH_PENDING_ATTEMPTS - self._pending_attempts == 1
                ):
                    if carried:
                        head = carried[0]
                    elif len(population) == 1:
                        (head,) = population
                head_only = head is not None
                # A fresh population that fits the fixed workers has no claim
                # order to decide: every event starts at once. Each stamp reads
                # its own group in its own write session, as a singleton does,
                # rather than every stamp first waiting on a separate session's
                # read of all of them. A read failure stays with its own event.
                prepared = None
                try:
                    if not head_only and (
                        pending_only or len(population) > FRESH_STAMP_WORKERS
                    ):
                        prepared = await self._prepare_groups(list(population))
                except Exception as exc:
                    self.stats["errors"] += 1
                    logger.exception(
                        "live_blend_refresh[%s]: preparation failed for %s",
                        self.source, population,
                    )
                    self._refresh_failed(
                        population, retry, clock, receipts, staged, stored_wall, exc,
                    )
                    failed_groups.update(population)
                    window.release(population)
                    continue

                # Preserve live-first order within each population and numeric
                # tie-breaking; missing prepared rows remain due as non-live.
                def stamp_order(event_id: int) -> tuple[bool, int]:
                    if prepared is None:
                        return (False, event_id)
                    context = prepared.get(event_id)
                    return (context is None or context[0].status != "live", event_id)

                ordered = sorted(population, key=stamp_order)
                if pending_only:
                    # Finish last flush's unattempted debt before beginning a
                    # new live-first debt cycle. Fresh remains ahead of both;
                    # repeated locked live IDs cannot starve quieter old debt.
                    queued = set(carried)
                    ordered = carried + [eid for eid in ordered if eid not in queued]

                async def stamp_event(event_id, *, read_current=False):
                    self._pending_continuation = [
                        eid for eid in self._pending_continuation if eid != event_id
                    ]
                    if pending_only and flush_started is not None:
                        self._pending_attempted = True
                        self._pending_attempts += 1
                    group_ids = [event_id]
                    if read_current:
                        reread_events.add(event_id)
                    try:
                        await self._refresh_batch(
                            group_ids,
                            clock,
                            # None (no shared read): this session reads it.
                            prepared=None if read_current else prepared,
                            on_committed=committed,
                            publish_committed=publish_committed,
                        )
                    except Exception as exc:
                        self.stats["errors"] += 1
                        logger.exception(
                            "live_blend_refresh[%s]: group failed for %s",
                            self.source,
                            group_ids,
                        )
                        if not completed.issuperset(group_ids):
                            self._refresh_failed(
                                group_ids,
                                retry,
                                clock,
                                receipts,
                                staged,
                                stored_wall,
                                exc,
                            )
                            failed_groups.update(group_ids)
                    else:
                        # Empty/no-market groups also finished successfully.
                        if not completed.issuperset(group_ids):
                            committed(group_ids)
                    finally:
                        window.release(group_ids)

                if head_only:
                    await stamp_event(head)
                    remaining = population.difference({head})
                    budget_deferred.update(remaining)
                    self._lock_retry.update(remaining.intersection(retry))
                    self._throttle_deferred.update(remaining.difference(retry))
                    window.release(remaining)
                    self._pending_continuation = carried[1:] + [
                        eid for eid in self._pending_continuation
                        if eid not in population
                    ]
                elif not pending_only:
                    # FRESH_STAMP_WORKERS fixed workers claim fresh IDs in
                    # order; waiting stamps cannot hold every fresh sibling
                    # behind their row locks. No population-sized fanout.
                    event_ids = iter(ordered)

                    async def fresh_worker(initial_event_id):
                        await stamp_event(initial_event_id)
                        for event_id in event_ids:
                            # Another stamp/publication may have waited since
                            # preparation. Read current quotes and their actual
                            # observation clocks in this event's write session.
                            # Cost: one joined read per queued fresh event.
                            await stamp_event(event_id, read_current=True)

                    # Claim every initial ID before scheduling any worker:
                    # even a worker completing without yielding cannot consume
                    # a sibling's initial prepared slot. No population fanout.
                    initial_events = [
                        next(event_ids)
                        for _ in range(min(FRESH_STAMP_WORKERS, len(ordered)))
                    ]
                    workers = {
                        asyncio.create_task(fresh_worker(event_id))
                        for event_id in initial_events
                    }
                    try:
                        active = workers.copy()
                        while active:
                            done, active = await asyncio.wait(
                                active, return_when=asyncio.FIRST_COMPLETED,
                            )
                            for task in done:
                                task.result()
                    except BaseException:
                        # Join stamp cleanup before computing cancellation debt.
                        # Repeated consumer cancellation cannot abandon a session
                        # or a worker that owns publication cleanup.
                        for task in workers:
                            if not task.done() and not task.cancelling():
                                task.cancel()
                        active = {task for task in workers if not task.done()}
                        while active:
                            try:
                                _, active = await asyncio.wait(active)
                            except CancelledError:
                                continue
                        for task in workers:
                            if not task.cancelled():
                                task.exception()
                        raise
                else:
                    for index, event_id in enumerate(ordered):
                        if pending_budget_spent():
                            remaining = set(ordered[index:])
                            budget_deferred.update(remaining)
                            self._lock_retry.update(remaining.intersection(retry))
                            self._throttle_deferred.update(remaining.difference(retry))
                            window.release(remaining)
                            self._pending_continuation = ordered[index:] + [
                                eid for eid in self._pending_continuation
                                if eid not in population
                            ]
                            break
                        await stamp_event(event_id)
            # Admitted cohorts finish inside this call; the door closes with
            # no turn between its last worker ending and the close (or when a
            # lifecycle drain stops admitting), so the remaining drain is
            # bounded by what was queued before it.
            window.own_done = True
            await self._admission_join(window)
            await publication_done()
        except CancelledError as exc:
            interrupted = True
            remaining = set(due).difference(completed, failed_groups, budget_deferred)
            if remaining:
                self._refresh_failed(
                    remaining,
                    retry,
                    clock,
                    receipts,
                    staged,
                    stored_wall,
                    exc,
                    hold=False,
                )
            raise
        except Exception as exc:
            # Setup can fail between populations after earlier stamps committed.
            # Only unfinished work remains owed, including immediately due locks.
            self.stats["errors"] += 1
            logger.exception("live_blend_refresh[%s]: preparation failed", self.source)
            self._refresh_failed(
                set(due).difference(completed, failed_groups, budget_deferred),
                retry,
                clock,
                receipts,
                staged,
                stored_wall,
                exc,
            )
        finally:
            # Cancellation or any pre-commit failure must not leave a sender
            # running beside the consumer's final drain or next refresh. An
            # admitted stamp ends first: it may still submit a frame.
            try:
                await self._admission_close(window, cancel=interrupted)
            finally:
                try:
                    await publication_done(cancel=True)
                finally:
                    if waiting_frames:
                        import asyncio

                        # These committed frames were NEVER submitted. Finish one
                        # bounded send before exit; do not retry the predecessor's
                        # uncertain send or interrupt this cleanup on a second
                        # consumer cancellation. _publish retains its 5s bound.
                        frames = [frame for group in waiting_frames for frame in group]
                        waiting_frames.clear()
                        publishing = self._publish_prices_task(frames)
                        await publication_done(cancel_on_interrupt=False)
        return self.stats

    def _refresh_failed(
        self,
        due,
        retry,
        clock,
        receipts,
        staged,
        stored_wall,
        exc,
        *,
        hold=True,
    ) -> None:
        # The outcome prices already committed before this refresh. Keep
        # every owed stamp if its transaction fails, even when no further
        # venue input arrives. Ordinary retries wait out the failed-retry
        # hold; only existing row-lock retries remain due at once.
        failed = set(due).difference(self._lock_retry, retry)
        self._throttle_deferred.update(set(due).difference(self._lock_retry))
        for event_id in failed if hold else ():
            self._failed_hold_until[event_id] = clock + self.failed_retry_interval_s
        for event_id in retry.intersection(due):
            self._lock_retry.add(event_id)
            self._last_refresh_at.pop(event_id, None)
            self._throttle_deferred.discard(event_id)
        if receipts is not None:
            self._receipt_call(
                receipts.resolve_failed,
                due,
                self._dispositions,
                staged,
                stored_wall,
                self._lock_retry | self._throttle_deferred,
                exc,
                _mono(),
            )

    def _stage_hook(self, name):
        """#10090: an optional stage-trace hook, None when no trace has it."""
        return getattr(getattr(self.receipts, "exact_trace", None), name, None)

    def _stage_trace(self, name, *args, **kwargs):
        """#10090: call an optional stage-trace hook. Synchronous, never raises."""
        hook = self._stage_hook(name)
        if hook is not None:
            with contextlib.suppress(Exception):
                hook(*args, **kwargs)

    def _receipt_call(self, fn, *args):
        """Receipts are evidence about the price path, never part of it."""
        try:
            return fn(*args)
        except Exception:
            logger.warning(
                "live_blend_refresh[%s]: tail receipt failed",
                self.source,
                exc_info=True,
            )
            return None

    async def refresh_pending(
        self,
        *,
        flush_started: Optional[float] = None,
        defer_event_ids: Iterable[int] = (),
    ) -> dict[str, int]:
        """#837 tail — stamp only the deferred events. Never raises.

        For the socket's flush when it has no new prices to write: `refresh`
        is otherwise only reached after a price write, and a deferred event on a
        quiet market would wait for a tick that may not come. Deferred means a
        row lock gave up OR the throttle held a written price. Returns at once,
        without opening a session, when nothing is queued or nothing queued is
        due yet.
        """
        self._start_normal_recovery()
        self._start_history()
        if (not self._lock_retry and not self._throttle_deferred
                and not self._book_refused_woken(_mono())):
            if self.receipts is not None:
                # #10090: a quiet flush still closes a finished minute.
                self._receipt_call(self.receipts.roll)
            return self.stats
        return await self.refresh(
            (), flush_started=flush_started, defer_event_ids=defer_event_ids,
        )

    def pending_event_ids(self) -> frozenset:
        """Every event this refresher still owes a stamp (#9462 review).

        #11317 P2: a parked refused pair counts only once it is worth a read
        again (`_book_refused_woken`); until then it spends no flush. It stays
        owed all the same: `hand_off_pending` carries it through a recycle.
        """
        return frozenset(
            self._lock_retry | self._throttle_deferred
            | self._book_refused_woken(_mono())
        )

    # ── #11317 P2: a refused bundled pair waits for a changed input ──────────

    def _book_signature(self, tickers) -> tuple:
        reader = self.current_book_signature
        return tuple(reader(ticker) for ticker in tickers)

    def _park_book_refused(self, event_id: int, group) -> None:
        """The current-book proof refused this event's bundled pair.

        Before: re-queued as throttle-deferred, so every flush read it again
        and was refused again on the same book (v5810: no_reading ≈ 5.7×
        stamped). Now, when the owner installed `current_book_signature`, the
        pair is parked with the value of every in-memory input the proof read;
        it is read again when one of them changes, when a fresh price for the
        event arrives (a batch takes it as usual) or at the shared sweep.
        Synchronous, called from inside the proof: the values recorded are the
        ones the refusal saw, with no await between.
        """
        tickers = ()
        if self.current_book_signature is not None:
            tickers = tuple(sorted({
                row.external_id
                for entry in group
                if getattr(entry.market, "source", None) == "kalshi"
                and (getattr(entry.market, "external_id", None) or "").upper()
                .startswith("KXATPCHALLENGERMATCH-")
                for row in entry.outcomes
                if isinstance(getattr(row, "external_id", None), str)
            }))
        try:
            signature = self._book_signature(tickers) if tickers else None
        except Exception:
            signature = None
        if signature is None:
            self._throttle_deferred.add(event_id)
            return
        if not self._book_refused or self._book_refused_sweep_at is None:
            self._book_refused_sweep_at = _mono() + BOOK_REFUSED_SWEEP_S
        self._book_refused[event_id] = (tickers, signature)

    def _book_refused_woken(self, now: float) -> set[int]:
        """Parked pairs worth a read now. Pure: moves nothing."""
        if not self._book_refused:
            return set()
        sweep = self._book_refused_sweep_at
        if self.current_book_signature is None or (sweep is not None and now >= sweep):
            return set(self._book_refused)
        woken = set()
        for event_id, (tickers, signature) in self._book_refused.items():
            try:
                changed = self._book_signature(tickers) != signature
            except Exception:
                changed = True  # an unreadable input is not proof of no change
            if changed:
                woken.add(event_id)
        return woken

    def _wake_book_refused(self, now: float) -> None:
        """Move the woken parked pairs back into the ordinary deferred debt."""
        woken = self._book_refused_woken(now)
        if not woken:
            return
        for event_id in woken:
            del self._book_refused[event_id]
        self._throttle_deferred.update(woken)
        if not self._book_refused:
            self._book_refused_sweep_at = None

    def holding_event_ids(self) -> Optional[frozenset]:
        """#10090 — the running call's events whose stamp is queued or running.

        A caller may write a newer price for any other event the call took:
        its stamp has returned, so a new stamp is ordered after it (one frame
        sender) and reads the newer board. None before the call's first turn
        has opened its door (`refresh`'s first turn follows its task's
        creation, so a caller that yields once after creating it sees the set).
        """
        return None if self._holding is None else frozenset(self._holding)

    def holding_frontier(self) -> Optional[_HoldingFrontier]:
        """#10090 — the running call's attempts queued or running right now,
        as a frontier a lifecycle wait can drain while the call keeps
        admitting later cohorts (none of which it waits for). None when no
        call is running. Synchronous; never closes the door."""
        window = self._admission
        return None if window is None else _HoldingFrontier(window)

    def admission_opened(self):
        """#10090 — a future resolved when the next call opens its door.

        A call's task created this turn has no window until its first turn
        runs, so `holding_frontier` reads None for a call that is about to
        hold attempts. A lifecycle wait awaits this (beside the task, which
        may end without opening one) rather than polling for the first turn.
        """
        import asyncio

        loop = asyncio.get_running_loop()
        signal = self._admission_signal
        if signal is None or signal.done() or signal.get_loop() is not loop:
            signal = self._admission_signal = loop.create_future()
        return signal

    def adopt_pending(self, event_ids: Iterable[int]) -> None:
        """Take over stamps a previous run of this source still owed.

        Queued as throttle-deferred: this refresher has never stamped them, so
        the first flush (`refresh` or `refresh_pending`) finds them due.
        """
        self._throttle_deferred.update(event_ids)

    def keep_owed(self, event_ids: Iterable[int], *, marks: Iterable[InputMark] = ()) -> None:
        """#10090 — record what `refresh` records for an event it must defer.

        For a caller whose committed events are all still being written by its
        own flush (`defer_event_ids`): joining the running call only to start a
        `refresh` that defers every one of them waits out the WHOLE call, and
        the next flush with it, for no stamp. The debt is the same: queued as
        throttle-deferred, counted once as throttled, and the cohort's newest
        committed input opens its receipt chain as a deferred one does. The
        staging slot is not touched (a running call may own it). Synchronous.
        """
        event_ids = set(event_ids)
        self._stage_trace("stage_admission", "KEEP_OWED", "KEPT_OWED", event_ids)
        throttled = event_ids.difference(self._throttle_deferred)
        self._throttle_deferred.update(event_ids)
        if throttled:
            self.stats["throttled"] += len(throttled)
        receipts = self.receipts
        if receipts is not None:
            staged, wall = self._receipt_call(receipts.staged_for, marks) or ({}, None)
            staged = {eid: m for eid, m in staged.items() if eid in event_ids}
            self._receipt_call(receipts.observe, staged, wall, set(), _mono())

    # ── #10090: admitting a committed cohort into the running refresh ────────

    def admit_fresh(
        self,
        event_ids: Iterable[int],
        *,
        flush_started: Optional[float],
        marks: Iterable[InputMark] = (),
        defer_event_ids: Iterable[int] = (),
    ) -> frozenset:
        """Hand a newly COMMITTED whole cohort to the running `refresh`.

        Returns the events this refresher now owns: each is stamped before the
        running call returns, on a free one of its stamp workers, or is left
        owed exactly as a `refresh` would leave it (throttled). Each is due,
        stamped and held on ITS flush's clock (``flush_started``): a cohort of
        a LATER flush than the running call's joins it for as long as the call
        admits (#10090: until its admitted workers go idle or a lifecycle
        drain calls `stop_admitting`), so a new batch never waits for an
        unrelated older stamp, however long that one is held. Beside it, at
        most one due owed event at a time (`window.debt`) is stamped too, so
        debt progresses while the call lives on; it is not in the returned set.
        Empty means the caller keeps them for its next `refresh`, as before:
        no call is admitting, the clock is earlier, or there is none (the final
        drain keeps its own contract), or the event is fenced — the running call is
        still stamping it (an earlier attempt that has returned does not
        fence a newer price, #10090), or the caller is still writing its cohort
        (``defer_event_ids``) — so no partial board is read and no two stamps
        of one event overlap or reorder. ``marks`` are the cohort's committed
        inputs; they are kept with the admitted events, never staged over
        the running call's own. Synchronous: nothing is awaited here.
        """
        window = self._admission
        if (
            window is None or window.closed or flush_started is None
            or window.flush_started is None
        ):
            if self._stage_hook("stage_admission") is not None:
                self._stage_trace(
                    "stage_admission", "ADMIT", "NO_ADMITTING_CALL", event_ids,
                    flush_started=flush_started,
                )
            return frozenset()
        if flush_started != window.flush_started and flush_started < window.flush_started:
            if self._stage_hook("stage_admission") is not None:
                self._stage_trace(
                    "stage_admission", "ADMIT", "EARLIER_CLOCK", event_ids,
                    flush_started=flush_started,
                )
            return frozenset()
        excluded = set(defer_event_ids)
        if self._stage_hook("stage_admission") is not None:
            event_ids = list(event_ids)  # traced only: read twice below
            for eid in event_ids:
                if eid in excluded or eid in window.holding:
                    self._stage_trace(
                        "stage_admission", "ADMIT",
                        "DEFERRED_UNFINISHED" if eid in excluded else "HELD",
                        (eid,), flush_started=flush_started,
                    )
        taken = {
            eid for eid in event_ids
            if eid not in excluded and eid not in window.holding
        }
        cohort = frozenset(taken)
        if window.debt is None:
            # #10090: a call that keeps admitting may outlive the moment a new
            # `refresh` would have taken the debt, so the oldest due owed event
            # rides along — one at a time, behind the cohort, never fenced.
            self._wake_book_refused(_mono())
            owed = self._lock_retry | self._throttle_deferred
            rotation = [eid for eid in self._debt_rotation if eid in owed]
            rotation += sorted(owed.difference(rotation))
            order = [eid for eid in self._pending_continuation if eid in owed]
            order += [eid for eid in rotation if eid not in order]
            for eid in order:
                if eid in taken or eid in excluded or eid in window.holding:
                    continue
                if self._due(eid, flush_started):
                    taken.add(eid)
                    window.debt = eid
                    rotation.remove(eid)
                    rotation.append(eid)
                    break
            self._debt_rotation = rotation
        if not taken:
            return frozenset()
        # #10090: an event whose earlier stamp in this call has returned is
        # admitted again for its newer committed price. That attempt is retired
        # whole: its admission, outcome, clock, retry origin and input mark are
        # settled, none pays for this one, and a throttled newer price is debt,
        # never an unfinished attempt at close.
        again = taken.intersection(window.events)
        for attempt in (window.admitted, window.completed, window.failed, window.retry):
            attempt.difference_update(again)
        for event_id in again:
            window.clocks.pop(event_id, None)
            window.staged.pop(event_id, None)
            window.stored_wall.pop(event_id, None)
        clock = flush_started
        due = sorted(eid for eid in taken if self._due(eid, clock))
        if self._stage_hook("stage_admission") is not None:
            for eid in taken:
                self._stage_trace(
                    "stage_admission", "ADMIT",
                    ("DEBT_" if eid == window.debt and eid not in cohort else "")
                    + ("ADMITTED" if eid in due else "THROTTLED"),
                    (eid,), flush_started=flush_started,
                )
        throttled = taken.difference(due, self._throttle_deferred)
        self._throttle_deferred.update(taken.difference(due))
        if throttled:
            self.stats["throttled"] += len(throttled)
        retry = self._lock_retry.intersection(due)
        self._lock_retry.difference_update(due)
        self._throttle_deferred.difference_update(due)
        for event_id in due:
            self._book_refused.pop(event_id, None)
        self._pending_continuation = [
            eid for eid in self._pending_continuation if eid not in taken
        ]
        # Sticky for the flush, exactly as a fresh `refresh` call would be. A
        # later flush's allowance is not the running call's to spend: it is
        # marked for that flush's own first `refresh`. Debt alone is not fresh.
        if cohort and flush_started == self._pending_flush_started:
            self._pending_fresh_flush = True
        elif cohort:
            self._admitted_fresh_flush = flush_started
        self.stats["considered"] += len(due)
        window.events.update(taken)
        receipts = self.receipts
        if receipts is not None:
            staged, wall = self._receipt_call(receipts.staged_for, marks) or ({}, None)
            staged = {eid: m for eid, m in staged.items() if eid in taken}
            self._receipt_call(receipts.observe, staged, wall, set(due), _mono())
            for event_id in due:
                if event_id in staged:
                    window.staged[event_id] = staged[event_id]
                    window.stored_wall[event_id] = wall
        if due:
            import asyncio

            window.admitted.update(due)
            window.holding.update(due)
            window.clocks.update(dict.fromkeys(due, clock))
            window.retry.update(retry)
            live = self._live_event_ids
            window.live_queue.extend(eid for eid in due if eid in live)
            window.queue.extend(eid for eid in due if eid not in live)
            # A finished worker consumes nothing more: reap it (its outcome
            # retrieved) so it never holds a worker place while the running
            # call's own stamps keep `_admission_join` from reaching it.
            finished = {task for task in window.workers if task.done()}
            window.workers.difference_update(finished)
            for task in finished:
                if not task.cancelled():
                    task.exception()
            for _ in range(min(FRESH_STAMP_WORKERS - len(window.workers), len(due))):
                window.workers.add(asyncio.create_task(self._admitted_worker(window)))
        return cohort

    def stop_admitting(self) -> None:
        """#10090 — a lifecycle drain (final, cancellation, catalog change, a
        joined fallback) is about to wait for the running call: close its door
        first, so the wait covers what is already queued, never a later
        arrival. Synchronous; the call ends once its queue has drained."""
        window = self._admission
        if window is not None:
            window.closed = True

    def admitting(self) -> bool:
        """#10090 — a running call is still taking later flushes' cohorts."""
        window = self._admission
        return window is not None and not window.closed

    async def _admitted_worker(self, window: _FreshAdmission) -> None:
        while window.live_queue or window.queue:
            await self._stamp_admitted(window, window.next_queued())

    async def _stamp_admitted(self, window: _FreshAdmission, event_id: int) -> None:
        """One admitted event, read in its own session after its cohort
        committed, exactly as a singleton stamp reads, published through the
        running call's one sender. Never raises but for cancellation."""
        receipts = self.receipts
        group_ids = [event_id]
        staged = (
            {event_id: window.staged[event_id]} if event_id in window.staged else {}
        )
        stored_wall = window.stored_wall.get(event_id)
        clock = window.clocks.get(event_id, window.clock)

        def committed(ids):
            window.completed.update(ids)
            if receipts is not None:
                self._receipt_call(
                    receipts.resolve, ids, self._dispositions, staged,
                    stored_wall, _mono(),
                )

        try:
            await self._refresh_batch(
                group_ids, clock,
                on_committed=committed, publish_committed=window.publish,
            )
        except Exception as exc:
            self.stats["errors"] += 1
            logger.exception(
                "live_blend_refresh[%s]: admitted group failed for %s",
                self.source, group_ids,
            )
            if event_id not in window.completed:
                window.failed.add(event_id)
                self._refresh_failed(
                    group_ids, window.retry, clock, receipts, staged,
                    stored_wall, exc,
                )
        else:
            if event_id not in window.completed:
                committed(group_ids)
        finally:
            window.release(group_ids)

    async def _admission_join(self, window: _FreshAdmission) -> None:
        """Wait for every admitted stamp; close the door in the same turn the
        last one is seen finished, so nothing is admitted that no one joins."""
        import asyncio

        while window.workers:
            done, _ = await asyncio.wait(set(window.workers))
            window.workers.difference_update(done)
            for task in done:
                if not task.cancelled():
                    task.exception()
        window.closed = True

    async def _admission_close(self, window: _FreshAdmission, *, cancel: bool) -> None:
        """End admission for this call. On cancellation the admitted stamps are
        cancelled and joined — a repeated cancellation is recorded, never
        obeyed early — and every admitted event that did not commit stays
        owed with no failed-retry hold, including one whose worker never ran
        its first turn."""
        import asyncio

        window.closed = True
        interrupted = None
        while True:
            active = {task for task in window.workers if not task.done()}
            if not active:
                break
            if cancel:
                for task in active:
                    if not task.cancelling():
                        task.cancel()
            try:
                await asyncio.wait(active)
            except CancelledError as exc:
                interrupted = exc
                cancel = True
        for task in window.workers:
            if not task.cancelled():
                task.exception()
        window.workers.clear()
        # Only now: a worker still joining above takes its session slot here.
        if self._admission is window:
            self._admission = None
        unfinished = window.admitted.difference(window.completed, window.failed)
        for event_id in sorted(unfinished):
            self._refresh_failed(
                [event_id], window.retry, window.clocks.get(event_id, window.clock),
                self.receipts,
                {event_id: window.staged[event_id]} if event_id in window.staged else {},
                window.stored_wall.get(event_id),
                interrupted or CancelledError(), hold=False,
            )
        if interrupted is not None:
            raise interrupted

    async def _read_groups(self, session, event_ids: list[int], *, overlay_held=True,
                           clock_sample=None) -> dict[int, tuple]:
        from copy import deepcopy
        from types import SimpleNamespace
        from sqlalchemy import and_, cast, func, literal, null, or_, select
        from app.models.models import Event, FuturesMarket, FuturesOutcome
        from app.utils.live_blend import MarketOutcomes
        from app.utils.content_understanding import CONTENT_UNDERSTANDING_KEY
        from app.utils.prediction_market_matching import (
            COMBAT_FIGHT_WINNER_PREFIXES, TENNIS_MATCH_WINNER_PREFIXES,
        )

        # One fresh statement snapshot of graph, admission and quotes. No ORM
        # hydration and no per-quote Market -> Event -> Outcome round trips.
        # The OUTER JOIN keeps empty/prop markets: group length gates devig.
        outcome_join = FuturesOutcome.market_id == FuturesMarket.id
        if self.source == "kalshi":
            # Exact feeds_win_prob_blend ticker rule, using its shared sets.
            # Missing/empty tickers retain the resolver's name fallback.
            prefix = func.split_part(func.lower(FuturesMarket.external_id), "-", 1)
            outcome_join = and_(
                outcome_join,
                or_(
                    FuturesMarket.external_id.is_(None),
                    FuturesMarket.external_id == "",
                    prefix.endswith("game"),
                    prefix.in_(sorted(
                        COMBAT_FIGHT_WINNER_PREFIXES | TENNIS_MATCH_WINNER_PREFIXES
                    )),
                ),
            )
        elif self.source == "polymarket":
            from app.services.polymarket_api import GAMMA_FULL_CONTEST_WINNER_TYPES
            from app.utils.content_understanding import (
                CONTENT_UNDERSTANDING_KEY,
                CONTENT_UNDERSTANDING_VERSION,
            )

            # A known venue refusal cannot speak in the resolver, including
            # as a devig sibling. Omit only its OUTCOMES, keeping the market
            # shell and group length. Unknown/malformed/future/older records
            # retain their outcomes; no title or inferred class gates this read.
            understanding = FuturesMarket.market_metadata[CONTENT_UNDERSTANDING_KEY]
            version = understanding["v"]
            semantic = understanding["semantic_type"]
            venue = understanding["venue_type"]
            known_refusal = and_(
                func.jsonb_typeof(FuturesMarket.market_metadata) == "object",
                func.jsonb_typeof(understanding) == "object",
                func.jsonb_typeof(version) == "number",
                version.astext == str(CONTENT_UNDERSTANDING_VERSION),
                func.jsonb_typeof(semantic) == "string",
                semantic.astext != "",
                func.jsonb_typeof(venue) == "string",
                venue.astext != "",
                venue.astext.not_in(sorted(GAMMA_FULL_CONTEST_WINNER_TYPES)),
            )
            # Missing JSON paths are SQL NULL: absence is never a refusal.
            outcome_join = and_(outcome_join, ~func.coalesce(known_refusal, False))
        # Only the raw content-understanding record participates in prepared
        # market admission. Keep that entire record, including malformed and
        # older versions, while leaving unrelated catalog JSON in PostgreSQL.
        fields = (
            (FuturesMarket, PREPARED_MARKET_FIELDS),
            (Event, PREPARED_EVENT_FIELDS),
            (FuturesOutcome, PREPARED_OUTCOME_FIELDS),
        )
        # #10090: a preview is composed BEFORE the UPDATE, so it needs the
        # whole committed bag and the revision that dates it. A plain read: it
        # waits on no row lock. Not selected unless this arm previews a
        # canary event in this batch: any other read is the statement it was.
        preview_columns = (
            (Event.win_probability_sources.label("preview_sources"),
             Event.win_probability_sources_rev.label("preview_rev"))
            if not getattr(self, "preview_events", frozenset()).isdisjoint(event_ids)
            else ()
        )
        # Capture BEFORE the statement, not when a prepared plan is later
        # published. Retirement invalidates this proof without renewing it.
        with _observation_read_step("admission"):
            preview_ticket = (
                await self._preview_admission_read() if preview_columns else None
            )
        with _observation_read_step("query"):
            rows = (
                await session.execute(
                    select(*(
                        (cast(null(), Event.win_probability_sources.type)
                         if preview_columns else
                         Event.win_probability_sources.op("->")(literal(self.source))).label(key)
                        if model is Event and key == "win_probability_sources"
                        else func.jsonb_build_object(
                            CONTENT_UNDERSTANDING_KEY,
                            FuturesMarket.market_metadata[CONTENT_UNDERSTANDING_KEY],
                        ).label(key)
                        if model is FuturesMarket and key == "market_metadata"
                        else getattr(model, key)
                        for model, keys in fields for key in keys
                    ), *preview_columns, *(
                        (func.clock_timestamp().label("observation_clock"),)
                        if clock_sample is not None else ()
                    ))
                    .select_from(FuturesMarket)
                    .join(Event, Event.id == FuturesMarket.event_id)
                    .outerjoin(FuturesOutcome, outcome_join)
                    .where(
                        FuturesMarket.source == self.source,
                        FuturesMarket.event_id.in_(event_ids),
                    )
                )
            ).all()
        if clock_sample is not None and rows:
            # Read DB time in the existing statement, without another pool
            # checkout. The caller may adopt it only after its scope succeeds.
            clock_sample["value"] = min(row[-1] for row in rows)
            rows = [row[:-1] for row in rows]
        grouped: dict[int, tuple] = {}
        entries: dict[int, MarketOutcomes] = {}
        held = self.held_quotes if overlay_held else None
        for row in rows:
            market_id = row[0]
            entry = entries.get(market_id)
            if entry is None:
                offset = 0
                market = SimpleNamespace(**dict(zip(
                    PREPARED_MARKET_FIELDS, row[:len(PREPARED_MARKET_FIELDS)]
                )))
                offset += len(PREPARED_MARKET_FIELDS)
                event_values = row[offset:offset + len(PREPARED_EVENT_FIELDS)]
                event_id = event_values[0]
                if event_id not in grouped:
                    context = dict(zip(PREPARED_EVENT_FIELDS, event_values))
                    # Before the UPDATE only this source's restamp guard reads
                    # the JSON. The full aggregate uses UPDATE RETURNING below.
                    source_value = context["win_probability_sources"]
                    if preview_columns:
                        # This same SELECT already returned the full bag. Avoid
                        # transferring/decoding its source again on every row.
                        # Preserve the two independently decoded JSON owners,
                        # copying only once per event, including nested values.
                        full_sources = row[-2]
                        source_value = (deepcopy(full_sources.get(self.source))
                                        if isinstance(full_sources, dict) else None)
                    context["win_probability_sources"] = {self.source: source_value}
                    if preview_columns:
                        # Trailing columns; the outcome slice below zips by
                        # field name, so they never reach an outcome row.
                        context["preview_sources"] = row[-2]
                        context["preview_rev"] = row[-1]
                        context["preview_read_ticket"] = preview_ticket
                    grouped[event_id] = (
                        SimpleNamespace(**context),
                        [],
                    )
                event, group = grouped[event_id]
                entry = MarketOutcomes(
                    market=market,
                    outcomes=[],
                    event_has_result=event.completed_at is not None,
                    event_commence_time=(
                        event.commence_time
                        if event.status == "live" and event.completed_at is None
                        else None
                    ),
                )
                entries[market_id] = entry
                group.append(entry)
            outcome_values = row[len(PREPARED_MARKET_FIELDS) + len(PREPARED_EVENT_FIELDS):]
            if outcome_values[0] is not None:
                outcome = SimpleNamespace(**dict(zip(
                    PREPARED_OUTCOME_FIELDS, outcome_values
                )))
                entry.outcomes.append(outcome)
        # Strong references prevent id reuse while held.overlay_event replaces
        # rows. Membership by id is safe until classification below completes.
        original_rows = {id(row): row for _event, group in grouped.values()
                         for entry in group for row in entry.outcomes}
        if held is not None:
            for _event, group in grouped.values():
                held.overlay_event(group)
        if getattr(self, "current_primary_input", None) is not None:
            for _event, group in grouped.values():
                for entry in group:
                    for row in entry.outcomes:
                        row._primary_quote_overlaid = id(row) not in original_rows
        if preview_ticket is not None:
            await self._retire_terminal_preview_read(grouped, preview_ticket)
        return grouped

    async def _prepare_groups(self, event_ids: list[int]) -> dict[int, tuple]:
        """Read one fresh scalar graph owned only by this refresh call.

        `_read_groups` materializes plain namespaces from scalar query rows,
        including newly decoded JSON. No ORM objects or shared cache escape
        the transaction, so rebuilding and recursively copying that graph
        again only delays the first stamp. Each event's group belongs to one
        worker. Queued fresh events still reread their current quotes; the
        cold orientation fallback still reads in the stamp's own session.
        """
        from app.tasks.base import get_task_session

        factory = self._session_factory or get_task_session
        async with self._session_slot(), factory() as session:
            return await self._read_groups(session, event_ids)

    def _session_slot(self):
        """The run's existing three slots, across quote and history owners."""
        return self._session_slots

    @contextlib.asynccontextmanager
    async def _history_reservations(self, event_ids, now, owed):
        """Reserve debt space before a transaction can owe a point.

        Same-event quotes remain serial under the consumer's existing fence.
        Distinct due observations are never dropped or coalesced. Past the
        ordinary backlog a due stamp still owes its point and does not wait
        (#11138): production v5763 13:01:22Z, Kalshi's writer held 5.364 s at
        64 owed, held 15331223's .375 for 5.8 s behind three due stamps. The
        point keeps its observation time and the writer pays it without
        another quote (#11181). Past the memory bound (`HISTORY_SPILL_LIMIT`),
        or while custody holds rows memory does not, a committed point is
        carried by its custody row alone and loaded in its event's order.
        """
        reserved = set()
        kept = set()
        ready = asyncio.Event()
        try:
            for eid in event_ids:
                last = self._history_reserved.get(eid, self._last_snapshot_at.get(eid))
                if last is not None and now - last < self.snapshot_interval_s:
                    continue
                if self._history_count >= self._history_limit:
                    self._start_history()
                    self.stats["history_deferred"] += 1
                self._history_count += 1
                reserved.add(eid)
            try:
                yield reserved, ready
            except BaseException:
                self._note_normal_debt()
                # A COMMIT whose acknowledgement was lost may still have
                # stored this transaction's custody rows: the next drain reads,
                # and a load already in flight cannot conclude it saw them.
                if reserved and self._chart_custody is not None:
                    self._custody_backlog = True
                    self._custody_only_committed += 1
                raise
            # The nested session has now exited with a successful COMMIT.
            for eid, value, reading in owed:
                self._history_reserved[eid] = now
                custody_id = getattr(reading, "custody_id", None)
                if custody_id is not None and (
                    self._custody_backlog
                    or len(self._history)
                    >= self._history_limit + self._history_spill_limit
                ):
                    self._custody_backlog = True
                    self._custody_only_committed += 1
                    self._custody_ready[custody_id] = ready
                    if len(self._custody_clock) < (
                        self._history_limit + self._history_spill_limit
                    ):
                        self._custody_clock[custody_id] = now
                    self.stats["history_custody_only"] += 1
                    continue
                self._history.append((eid, value, reading, now, ready))
                kept.add(eid)
        finally:
            self._history_count -= len(reserved - kept)
            self._history_changed.set()

    def _start_history(self, *, force=False):
        if self._history_task and not self._history_task.done():
            return
        load = not force and self._custody_backlog
        if not self._history and not load:
            return
        if not force and not load and all(
            _mono() < self._history_retry_at.get(point[0], 0.0)
            for point in self._history
        ):
            return
        self._history_task = asyncio.create_task(self._drain_history(force=force))

    async def _drain_history(self, *, force=False):
        from app.tasks.base import get_task_session

        factory = self._session_factory or get_task_session
        failed = set()
        cursor = 0
        try:
            while True:
                while cursor < len(self._history):
                    point = self._history[cursor]
                    eid, value, reading, observed_clock, ready = point
                    # A failed event keeps its original FIFO, but cannot strand a
                    # healthy sibling's history behind its own retry hold.
                    if eid in failed or (
                        not force and _mono() < self._history_retry_at.get(eid, 0.0)
                    ):
                        cursor += 1
                        continue
                    await ready.wait()  # publication was attempted after COMMIT
                    if not await self._write_owed_snapshots(
                        [(eid, value, reading)],
                        observed_clock,
                        factory,
                        verify_event=eid in self._history_retry_at,
                    ):
                        failed.add(eid)
                        self._history_retry_at[eid] = (
                            _mono() + self.failed_retry_interval_s
                        )
                        cursor += 1
                        self._history_changed.set()
                        continue
                    self._history.pop(cursor)
                    self._history_count -= 1
                    self._history_retry_at.pop(eid, None)
                    # A custody row outside memory may still owe this event a
                    # later point; its reservation clock stays until loaded.
                    if not self._custody_backlog and not any(
                        point[0] == eid for point in self._history
                    ):
                        self._history_reserved.pop(eid, None)
                    self._history_changed.set()
                # The final drain of a run reads no custody: its rows are
                # durable and the next run of the source starts by loading them.
                if force or not await self._load_custody(factory):
                    break
        except Exception:
            self.stats["errors"] += 1
            for eid, *_ in self._history:
                self._history_retry_at[eid] = _mono() + self.failed_retry_interval_s
            logger.exception(
                "live_blend_refresh[%s]: history owner failed; debt retained",
                self.source,
            )
        finally:
            self._history_changed.set()

    async def _load_custody(self, factory) -> int:
        """#11181 — move custody rows memory does not hold into memory.

        Oldest commit id first, at most the room memory has. Same-event points
        commit serially, so ids keep each event's observation order, and while
        any row is outside memory every newly committed point also stays there
        (`_history_reservations`): no later point of an event is ever written
        ahead of an earlier one. A row another drain already paid is found
        gone by `settle`, never written twice. Returns how many rows it moved.
        """
        if not self._custody_backlog or self._chart_custody is None:
            return 0
        room = self._history_limit + self._history_spill_limit - len(self._history)
        if room <= 0:
            return 0
        self._custody_ready = {
            cid: ready for cid, ready in self._custody_ready.items()
            if not ready.is_set()
        }
        committed_before = self._custody_only_committed
        held = {
            reading.custody_id for _, _, reading, _, _ in self._history
            if getattr(reading, "custody_id", None) is not None
        }
        async with self._session_slot(), factory() as session:
            rows = await self._chart_custody.load(session, self.source, held, room)
        done = asyncio.Event()
        done.set()
        for custody_id, eid, value, payload in rows:
            ready = self._custody_ready.pop(custody_id, done)
            # A row from an earlier process carries no clock of this one: the
            # reservation that admitted it already spaced it on the cadence.
            self._history.append((
                eid, value, _chart_reading_from_payload(custody_id, payload),
                self._custody_clock.pop(custody_id, None), ready,
            ))
            self._history_count += 1
        if len(rows) < room and self._custody_only_committed == committed_before:
            # Everything committed before this read was visible to it.
            self._custody_backlog = False
        return len(rows)

    async def drain_history(self):
        """One final attempt, joined through repeated cancellation before close.

        Failed scalar debt stays in the queue for the next run. The owner never
        republishes frames or turns history-only debt into blend debt.
        """
        interrupted = None
        try:
            await self._close_preview_maintenance()
        except asyncio.CancelledError as exc:
            interrupted = exc
        try:
            await self._close_normal_recovery()
        except asyncio.CancelledError as exc:
            interrupted = exc
        self._start_history(force=True)
        task = self._history_task
        while task is not None and not task.done():
            try:
                await asyncio.wait({task})
            except asyncio.CancelledError as exc:
                interrupted = exc
        if task is not None and not task.cancelled():
            task.exception()
        if interrupted is not None:
            raise interrupted

    @contextlib.asynccontextmanager
    async def _event_stamp_scope(self, session, *, single_event: bool):
        """One event already owns the transaction; only siblings need a savepoint."""
        if not single_event:
            async with session.begin_nested():
                yield
            return
        try:
            yield
        except BaseException:
            # A lock timeout aborts PostgreSQL's transaction. Without the
            # redundant event SAVEPOINT, rollback the whole single-event
            # transaction before the caller handles/requeues the failure.
            await session.rollback()
            raise

    async def _refresh_batch(
        self,
        event_ids: list[int],
        now: float,
        *,
        prepared: Optional[dict[int, tuple]] = None,
        on_committed: Optional[Callable[[list[int]], None]] = None,
        publish_committed: Optional[Callable[[list[dict]], Awaitable[None]]] = None,
    ) -> None:
        from types import SimpleNamespace

        from sqlalchemy import update

        from app.models.models import Event
        from app.tasks.base import get_task_session
        from app.utils.aggregation import (
            compute_aggregate_probability,
            observation_basis,
            oldest_observation_time,
        )
        from app.utils.live_blend import compute_source_home_probability
        from app.utils.live_push import build_frame, build_source_snapshot
        from app.utils.repair_lock_budget import (
            SET_LOCK_AND_STATEMENT_TIMEOUT_SQL, SET_LOCK_TIMEOUT_SQL,
            SET_STATEMENT_TIMEOUT_SQL, is_lock_timeout, is_query_canceled,
            lock_timeout_value,
        )

        # live/034 S1 — frames are COLLECTED here and published after the
        # session context exits cleanly, never inside the loop. Publishing
        # mid-transaction would broadcast a number that a later failure in the
        # same batch could roll back, and an un-take-back-able push of a value
        # the database never kept is worse than a push that never happened.
        pending: list[dict] = []
        # #10702: bind exact committed input marks to this reading's actual
        # contributor observations. Nothing is emitted before outer COMMIT.
        exact_trace = getattr(self.receipts, "exact_trace", None)
        trace_bases: dict = {}
        self._stage_trace("attempt_start", event_ids, now)
        # #837 tail (Codex review of #8490) — and for the same reason the
        # write bookkeeping is COLLECTED and applied only after the commit. A
        # released savepoint is not a committed stamp: recorded there, a failed
        # commit left `_should_write` believing the price was stored, so the
        # retry of a lock-deferred event skipped it as unchanged and the price
        # was lost for good.
        written: dict[int, float] = {}
        # #10090 (preview arm only): each canary event's RETURNING bag.
        committed_bags: dict[int, tuple] = {}
        # #10090: the chart points the committed stamps owe, in stamp order.
        owed_snapshots: list[tuple] = []

        # Stamp the throttle for EVERY event we are about to attempt, before any
        # of them can fail to resolve. Stamping per-resolved-event instead would
        # leave an event with no linked markets of this source permanently
        # "due", and every batch opens a session (and, outside a consumer
        # that lends its engine (#2471), a fresh engine and connection pool) —
        # so that event would query Postgres every 2-second flush, forever, to
        # discover the same nothing.
        for event_id in event_ids:
            self._last_refresh_at[event_id] = now

        if self._session_factory is not None:
            get_task_session = self._session_factory  # #2471: the consumer's
        async with (
            self._normal_holds() as held,
            self._history_reservations(event_ids, now, owed_snapshots) as reservation,
            self._session_slot(), get_task_session() as session,
        ):
            reserved, history_ready = reservation
            self._stage_trace("attempt_session", event_ids)
            if prepared is None:
                grouped = await self._read_groups(session, event_ids)
            else:
                grouped = {
                    eid: prepared[eid] for eid in event_ids if eid in prepared
                }
            for eid in event_ids:
                if eid in grouped and getattr(grouped[eid][0], "status", None) == "live":
                    self._live_event_ids.add(eid)
                else:
                    self._live_event_ids.discard(eid)
            if not grouped:
                if self.preview:
                    # #10090: this source spoke for none of these events, so
                    # none of its pending values may keep speaking.
                    await self._publish_previews(self._preview_settlement(
                        event_ids, grouped, {}, set(), {},
                    ))
                return

            # #837 — ONE LOCK ORDER, ONE SAVEPOINT PER EVENT WITH SIBLINGS.
            # A single event owns its whole transaction, so its stamp scope
            # rolls back that transaction on failure instead of paying an
            # extra SAVEPOINT/RELEASE pair on every successful stamp.
            # This batch stamps
            # every event in a single transaction, and the sibling arm (the other
            # venue's consumer, same class, same column) does the same
            # concurrently. Walked in join order, two overlapping batches locked
            # the same `events` rows in opposite orders and Postgres killed one:
            # production 2026-09-24, 5 `deadlock detected` in 13 minutes on a
            # nine-game slate. And the per-event `except` below could not contain
            # it — a deadlock ABORTS the transaction, so every later UPDATE in the
            # batch failed ("current transaction is aborted") and the commit threw
            # away the stamps that had already succeeded: a whole batch of live
            # headlines silently held back until the next price. Ascending id in
            # BOTH arms removes the cycle between them; the savepoint confines any
            # other failure (a third writer, a bad row) to the one event it hit.
            #
            # #837 tail — and no event waits on a lock long enough to hold the
            # rest back (see `DEFAULT_STAMP_LOCK_TIMEOUT_MS`). Transaction-local,
            # set here rather than at session open so the joins above keep their
            # ordinary waits; a timed-out stamp rolls back only its savepoint.
            lock_budget_set = False
            lock_budget_failed = False
            # #11138: armed only at the stamp, so the cold orientation reads
            # keep the lock budget alone. Once armed it stays for the rest of
            # the transaction (one event in every production refresh).
            statement_bound_set = False

            async def ensure_lock_budget(*, whole_statement=False):
                nonlocal lock_budget_set, lock_budget_failed, statement_bound_set
                if not self.stamp_lock_timeout_ms or (
                    lock_budget_set
                    and (statement_bound_set or not whole_statement)
                ):
                    return
                if not whole_statement:
                    budget_sql = SET_LOCK_TIMEOUT_SQL
                elif lock_budget_set:
                    budget_sql = SET_STATEMENT_TIMEOUT_SQL
                else:
                    budget_sql = SET_LOCK_AND_STATEMENT_TIMEOUT_SQL
                try:
                    await session.execute(
                        budget_sql,
                        {"ms": lock_timeout_value(self.stamp_lock_timeout_ms)},
                    )
                except Exception:
                    # Budget setup used to fail outside the event loop. Keep
                    # its whole-batch rollback/requeue, never swallow it as a
                    # single failed event in an unbounded transaction.
                    lock_budget_failed = True
                    raise
                lock_budget_set = True
                statement_bound_set = statement_bound_set or whole_statement

            # #10090 (preview arm only): canary readings awaiting their
            # UPDATE, the preview seq each published, and canary events whose
            # attempt failed.
            preview_plans: dict[int, tuple] = {}
            preview_only: set[int] = set()
            preview_seq: dict[int, int] = {}
            preview_failed: set[int] = set()
            # #10090: compute and publish eligible previews before any event's
            # UPDATE so one row-lock wait cannot hold back a sibling display.
            # Persistence retains the same sorted lock order (#837).
            ordered = sorted(grouped)
            preview_ids = [eid for eid in ordered if eid in self.preview_events]
            if preview_ids:
                work = ([("compute", eid) for eid in preview_ids] + [("preview", None)]
                        + [("stamp" if eid in self.preview_events else "both", eid)
                           for eid in ordered])
            else:
                work = [("both", eid) for eid in ordered]
            for phase, event_id in work:
                if phase == "preview":
                    await self._preview_before_stamp(
                        grouped, preview_plans, preview_seq, observation_only=preview_only,
                    )
                    continue
                if phase == "stamp" and (event_id not in preview_plans or event_id in preview_only):
                    continue
                event, group = grouped[event_id]
                try:
                    if phase == "stamp":
                        refused, proof_kwargs, reading, value, contributing = preview_plans[event_id]
                    else:
                        refused = []
                        proof_kwargs = self._current_reading_proof(event_id, group, refused)
                        reading = compute_source_home_probability(
                            group, event.home_team_name, event.away_team_name,
                            **proof_kwargs,
                        )
                        if reading is None:
                            self.stats["no_reading"] += 1
                            if refused:
                                self.stats["bundled_refused"] += 1
                            self._dispositions[event_id] = ("no_reading",)
                            continue

                        home_prob = await self._oriented(
                            session, event_id, reading.home_probability, reading=reading,
                            before_fallback=ensure_lock_budget,
                        )
                        value = round(home_prob, 4)

                        # #5661 — before the throttle decides WHEN to re-stamp, ask
                        # WHETHER there is anything to re-stamp. The row's own
                        # stored entry is the reference (not this process's memory,
                        # which a dyno restart empties), and the reading's rows are
                        # the ones the number came from, as the 120s poll dates it.
                        contributing = (
                            getattr(reading, "contributing_outcomes", None)
                            or (getattr(reading, "outcome", None),)
                        )
                        if restamp_records_no_observation(
                            value,
                            oldest_observation_time(contributing),
                            getattr(event, "win_probability_sources", None),
                            self.source,
                        ):
                            self.stats["unobserved_skipped"] += 1
                            self._dispositions[event_id] = ("unobserved", value)
                            if phase == "compute":
                                # A periodic durable read can predate an already
                                # accepted observation preview. Let its registry
                                # judge that basis without requesting persistence.
                                preview_plans[event_id] = (
                                    refused, proof_kwargs, reading, value, contributing,
                                )
                                preview_only.add(event_id)
                            continue

                        if not self._should_write(event_id, value, now):
                            self.stats["unchanged_skipped"] += 1
                            self._dispositions[event_id] = ("unchanged", value)
                            # Persistence cadence does not own display admission.
                            # Only a complete contributing observation can try
                            # this route; the registry proves it newer than the
                            # stored reading and its pending observation. There
                            # is no event UPDATE or lock/retry debt for this arm.
                            if phase == "compute" and observation_basis(contributing):
                                preview_plans[event_id] = (
                                    refused, proof_kwargs, reading, value, contributing,
                                )
                                preview_only.add(event_id)
                                self._dispositions[event_id] = ("preview_only", value)
                            continue

                        if phase == "compute":
                            preview_plans[event_id] = (
                                refused, proof_kwargs, reading, value, contributing,
                            )
                            continue

                    # The database assigns the write clock; RETURNING below
                    # supplies that exact clock to the frame and tail receipt.
                    # A Python timestamp taken before the awaited UPDATE could
                    # precede a sibling's stamp despite committing after it.
                    # Core update, never ORM attribute assignment (gotcha #4),
                    # and a server-side merge rather than a read-modify-write:
                    # the sibling arm streaming the OTHER venue writes this same
                    # column concurrently (see `atomic_stamp_expression`).
                    #
                    # RETURNING is load-bearing, not a convenience. The frame
                    # below must carry the aggregate of what the database KEPT,
                    # including whatever the sibling arm committed a moment ago.
                    # Publishing the aggregate of this arm's own private copy is
                    # the second half of live/305's flicker: the row would be
                    # right and the wire still wrong.
                    #
                    # #8910: and the stamp is CONDITIONAL on no other writer
                    # having stored a later observation of these rows — every
                    # stamp, moved or re-stamped. See `observation_admits_clause`
                    # for why the condition lives in this UPDATE.
                    basis = observation_basis(contributing)
                    admits = observation_admits_clause(self.source, basis)
                    # Known-orientation readings that were refused above need
                    # no SET command. Every actual stamp still installs the
                    # same budget before its savepoint and row UPDATE, and
                    # (#11138) bounds that UPDATE as a whole statement.
                    await ensure_lock_budget(whole_statement=True)
                    async with self._event_stamp_scope(
                        session, single_event=len(grouped) == 1,
                    ):
                        if proof_kwargs:
                            checked = compute_source_home_probability(
                                group, event.home_team_name, event.away_team_name, **proof_kwargs,
                            )
                            if (checked is None or checked.home_probability != reading.home_probability
                                    or checked.contributing_outcomes != reading.contributing_outcomes):
                                self.stats["no_reading"] += 1
                                self._dispositions[event_id] = ("no_reading",)
                                continue
                        # `synchronize_session=False`: the ORM cannot evaluate
                        # the guard's SQL in Python, and its "fetch" fallback
                        # rewrites RETURNING to the primary key — the frame
                        # would then be built from an event id, not the blend.
                        stamp = (
                            update(Event)
                            .where(Event.id == event_id)
                            .execution_options(synchronize_session=False)
                        )
                        if admits is not None:
                            stamp = stamp.where(admits)
                        # #9051: the row's revision rides the same RETURNING,
                        # so the frame names exactly the write it reports.
                        stamped_row = (
                            await session.execute(
                                stamp.values(
                                    win_probability_sources=atomic_stamp_expression(
                                        self.source,
                                        value,
                                        eligibility=reading.eligibility,
                                        observed_basis=basis,
                                    )
                                )
                                .returning(
                                    Event.win_probability_sources,
                                    Event.win_probability_sources_rev,
                                )
                            )
                        ).first()
                        new_sources, new_rev = (
                            (None, None) if stamped_row is None else stamped_row
                        )
                        if new_sources is None and admits is not None:
                            # Refused: the poll or the matcher stored a later
                            # observation of these rows since this batch read
                            # them. No chart point, no frame, and NOT recorded
                            # as written, so the next flush reads again rather
                            # than taking this value as already stored. (A row
                            # deleted mid-batch lands here too; skipping it is
                            # right either way.)
                            self.stats["stale_readings_refused"] += 1
                            self._dispositions[event_id] = ("stale", value)
                            continue
                        if new_sources is None:
                            # The UPDATE matched nothing, so there is no stored blend
                            # to publish an aggregate of. Reachable only if the row
                            # went away between the join above and here; `_or_none`
                            # rather than `scalar_one` because that is a benign race
                            # to skip, not a traceback to log on the dyno whose job
                            # is streaming prices.
                            self.stats["no_reading"] += 1
                            self._dispositions[event_id] = ("no_row",)
                            continue

                        stamped_at = new_sources[self.source]["updated_at"]
                        # Intent and source revision COMMIT together. A crash
                        # before publication cannot erase the last recovery duty.
                        # Same revision rule as `build_frame`: a writer with no
                        # integer revision makes no claim, so it owes no intent
                        # and its stamp is not refused for lacking one.
                        if isinstance(new_rev, int) and not isinstance(new_rev, bool):
                            from sqlalchemy import insert
                            from app.models.models import OwedChartPoint
                            await session.execute(insert(OwedChartPoint).values(
                                source=self._normal_source, event_id=event_id,
                                value=value, reading={"rev": new_rev,
                                                      "updated_at": stamped_at},
                            ))
                        # Scalar extraction is still inside the event scope:
                        # if it fails, this stamp cannot commit without its
                        # due chart obligation.
                        chart_reading = (
                            _chart_reading(reading, stamped_at)
                            if event_id in reserved else None
                        )
                        # #11181: the owed point's durable row, in this same
                        # scope. A stamp commits only with it; an INSERT into a
                        # table with no foreign key takes no row lock to wait on.
                        if chart_reading is not None and self._chart_custody is not None:
                            chart_reading = _replace(
                                chart_reading,
                                custody_id=await self._chart_custody.record(
                                    session, self.source, event_id, value,
                                    chart_reading,
                                ),
                            )

                    # Noted only once the stamp scope has succeeded (a stamp
                    # that rolled back must not read as written), and applied only
                    # once the transaction commits — see `written` above.
                    written[event_id] = value
                    if event_id in self.preview_events:
                        committed_bags[event_id] = (new_sources, new_rev, event)

                    # #10090: the chart point is written AFTER this commit and
                    # its publication (`_write_owed_snapshots`), never inside the
                    # stamp's transaction, so chart SQL no longer delays the
                    # stamp's COMMIT or extends its event-row lock. Observed, not
                    # attributed: production 2026-10-11 00:52:30Z (BOS–PHI
                    # 15323924) one frame arrived ~3.0 s after its stamp against
                    # 0.05–0.19 s for its neighbours; no worker/history/lock
                    # receipt ties that interval to a chart write.
                    # Most changed quotes arrive before the chart clock is due;
                    # those owe nothing and open no second session.
                    if chart_reading is not None:
                        owed_snapshots.append((event_id, value, chart_reading))
                    if exact_trace is not None:
                        with contextlib.suppress(Exception):
                            if exact_trace.tracks_event(event_id):
                                trace_bases[event_id] = (basis, new_rev, stamped_at)
                    # #837 receipt — trusted only after the commit;
                    # `previous` says whether it MOVED.
                    self._dispositions[event_id] = (
                        "stamped", value, stamped_at,
                        self._last_written_value.get(event_id),
                        # #10090 delivery receipt: the revision the frame
                        # publishes, and whether the game is live.
                        new_rev, event.status,
                    )

                    # The AGGREGATE, computed off the sources JSONB the server
                    # RETURNED — the number the hero renders, not this one
                    # source's price ("the blend is the product"). The shim
                    # carries that post-write JSONB with the event's own
                    # fallback fields; `compute_aggregate_probability` reads
                    # all of them through `getattr`, so a namespace is a
                    # faithful stand-in for the row without re-reading it.
                    #
                    # `new_sources` is the database's copy, so it already
                    # contains the sibling arm's latest reading. That is what
                    # makes two frames published 89 ms apart agree.
                    #
                    # Attributes are pulled off the ORM object HERE, inside the
                    # session — after it closes they are expired and touching
                    # one would emit a lazy load against a dead session
                    # (gotcha #6).
                    shim = SimpleNamespace(
                        win_probability_sources=new_sources,
                        status=event.status,
                        espn_win_prob_home=getattr(
                            event, "espn_win_prob_home", None
                        ),
                        opening_home_probability=(
                            event.opening_home_probability
                        ),
                    )
                    frame = build_frame(
                        event_id=event_id,
                        probability=compute_aggregate_probability(
                            shim, event.status,
                        ),
                        source=self.source,
                        source_value=value,
                        updated_at=stamped_at,
                        status=event.status,
                        rev=new_rev,
                    )
                    # #10090: the row's complete public sources, from the same
                    # RETURNING bag and revision as `p`. No query. Published
                    # with the frame after COMMIT, or not at all.
                    snapshot = build_source_snapshot(
                        event_id, frame["rev"], new_sources,
                    )
                    if snapshot is None:
                        self.stats["source_snapshot_omitted"] += 1
                    else:
                        frame["source_snapshot"] = snapshot
                    pending.append(frame)
                    # Held before COMMIT: no recovery read can see this
                    # intent before this process has claimed its publication.
                    held |= self._normal_revisions([frame])
                    self._normal_inflight |= held
                except Exception as exc:
                    if lock_budget_failed:
                        raise
                    # #11138: a cancel after the stamp armed its statement
                    # bound is that bound — the row wait ran past its budget.
                    statement_bound = (
                        statement_bound_set and is_query_canceled(exc)
                    )
                    if is_lock_timeout(exc) or statement_bound:
                        # Another transaction holds this row. Its price is
                        # already stored; stamp it on the next flush, due at
                        # once, instead of freezing every other event's stamp
                        # behind a lock this arm does not control.
                        self.stats["lock_skipped"] += 1
                        self._dispositions[event_id] = ("lock",)
                        self._lock_retry.add(event_id)
                        self._last_refresh_at.pop(event_id, None)
                        logger.info(
                            "live_blend_refresh[%s]: event %s row locked >%sms, "
                            "re-queued for the next flush%s",
                            self.source,
                            event_id,
                            self.stamp_lock_timeout_ms,
                            " (statement bound)" if statement_bound else "",
                        )
                        continue
                    self.stats["errors"] += 1
                    if event_id in self.preview_events:
                        preview_failed.add(event_id)
                    # A committed stamp whose frame failed is still stamped.
                    self._dispositions.setdefault(event_id, ("error",))
                    logger.exception(
                        "live_blend_refresh[%s]: event %s failed",
                        self.source, event_id,
                    )

        # Session closed and committed — only now is the pushed number a number
        # the database actually kept, and only now is it "written".
        self._stage_trace("attempt_committed", event_ids, self._dispositions)
        for event_id, value in written.items():
            self._last_write_at[event_id] = now
            self._last_written_value[event_id] = value
        self.stats["stamped"] += len(written)
        if exact_trace is not None:
            for event_id, (basis, revision, stamped_at) in trace_bases.items():
                with contextlib.suppress(Exception):
                    exact_trace.stamp(event_id, basis, revision, stamped_at)
        try:
            if on_committed is not None:
                on_committed(event_ids)
            if publish_committed is None:
                # Ordered with the running quote call's admitted frames.
                window = self._admission
                publish_committed = (
                    self._publish_prices if window is None else window.publish_inline
                )
            settled = []
            # Over every ATTEMPTED canary event, not only those in `grouped`:
            # a canary whose group left beside a non-canary sibling still owes
            # its `no_group` revoke (R3).
            if not self.preview_events.isdisjoint(event_ids):
                # Only canary frames depend on preview recomposition. Release
                # independent committed events through the existing sender
                # before optional ledger/publication I/O can hold them up.
                independent = [
                    frame for frame in pending
                    if frame["event_id"] not in self.preview_events
                ]
                pending = [
                    frame for frame in pending
                    if frame["event_id"] in self.preview_events
                ]
                if independent:
                    await publish_committed(independent)
                # After COMMIT, BEFORE the committed canary frames: a sibling still
                # pending is recomposed on the new base and goes out first, so
                # the committed frame (rev == that base) cannot briefly put the
                # sibling's older stored value back on the page. Revokes go
                # after it, so a retired preview gives way to the commit that
                # carries it, never to the older committed value. A
                # lock-deferred event keeps its preview.
                settled = self._preview_settlement(
                    event_ids, grouped, preview_seq, preview_failed, committed_bags,
                )
                settled = await self._prepare_ledger_previews(settled)
                await self._publish_previews(
                    [f for f in settled if f["preview"]["kind"] == "blend"]
                )
            await publish_committed(pending)
            if settled:
                await self._publish_previews(
                    [f for f in settled if f["preview"]["kind"] != "blend"]
                )
        except BaseException:
            # Frames that never reached `_publish_prices` release here; an
            # early release costs at most one redundant control, a lost one
            # would hide the intent from discovery for this process's life.
            self._release_normal(held)
            raise
        finally:
            # The debt was registered immediately after COMMIT, before the
            # first publication await. Cancellation cannot strand it.
            history_ready.set()
            self._start_history()

    async def _write_owed_snapshots(
        self, owed: list[tuple], now: float, get_task_session,
        *, verify_event: bool = False,
    ) -> bool:
        """#10090 — report whether the owed points' transaction committed.

        Runs after the stamps COMMITTED and their frames were published (inline)
        or submitted to the ordered sender (grouped), in its own short
        transaction, so neither the stamp's COMMIT nor its hold on the event row
        waits on `win_prob_snapshots`. The run's single history owner awaits
        it, independently of the quote owner. A stamp that never commits owes
        no point and takes no slot, so its retry still draws one. Each point keeps its own savepoint, and its ORM writes are flushed
        inside it: one that cannot be written costs only itself, never another
        point and never the number already published.

        The stamp's lock budget is transaction-local and expired at its COMMIT,
        and the consumer sessions carry none of their own, so this transaction
        installs the same budget before any chart SQL. Without it a chart
        UPDATE queued behind another holder of the latest snapshot row waits
        out the resting statement timeout while the history slot stays taken. `stamp_lock_timeout_ms` falsy keeps it off, as
        it does for the stamp.

        `verify_event` (a retry of a point that already failed once): a point
        whose event row is gone is retired with its custody row instead of
        written, so a deleted event does not owe a chart write forever. The
        check runs after the settle, inside the point's savepoint; a lookup
        error or a failed COMMIT keeps the debt, as for any failed point.
        """
        from app.utils.repair_lock_budget import (
            SET_LOCK_TIMEOUT_SQL, lock_timeout_value,
        )

        counts = {
            key: self.stats[key]
            for key in ("snapshots_written", "snapshots_deduped", "history_event_gone")
        }
        try:
            async with (
                self._snapshot_slots_follow_the_commit(
                    [event_id for event_id, _, _ in owed]
                ),
                self._session_slot(),
                get_task_session() as session,
            ):
                if self.stamp_lock_timeout_ms:
                    await session.execute(
                        SET_LOCK_TIMEOUT_SQL,
                        {"ms": lock_timeout_value(self.stamp_lock_timeout_ms)},
                    )
                for event_id, value, reading in owed:
                    async with session.begin_nested():
                        # #11181: settle first, in the point's own savepoint: a
                        # point that fails restores its row, and a row already
                        # gone was paid once and is not written again.
                        custody_id = getattr(reading, "custody_id", None)
                        if custody_id is not None and self._chart_custody is not None:
                            if not await self._chart_custody.settle(session, custody_id):
                                self.stats["history_already_paid"] += 1
                                continue
                        if verify_event:
                            from sqlalchemy import select

                            from app.models.models import Event

                            if (await session.execute(
                                select(Event.id).where(Event.id == event_id)
                            )).first() is None:
                                # The stamp committed against a row that has since
                                # been deleted, and ids are never reused: nothing is
                                # owed. The settle above commits with this savepoint.
                                self.stats["history_event_gone"] += 1
                                logger.warning(
                                    "live_blend_refresh[%s]: owed chart point retired, event %s gone",
                                    self.source, event_id,
                                )
                                continue
                        await self._maybe_snapshot(session, event_id, value, reading, now)
                        await session.flush()
            return True
        except BaseException as exc:
            for key, count in counts.items():
                self.stats[key] = count
            if isinstance(exc, asyncio.CancelledError):
                raise
            self.stats["errors"] += 1
            logger.exception(
                "live_blend_refresh[%s]: committed chart point remains owed",
                self.source,
            )
            return False

    @contextlib.asynccontextmanager
    async def _snapshot_slots_follow_the_commit(self, event_ids: list[int]):
        """Undo these chart points' throttle slots if their transaction does
        not commit.

        `_maybe_snapshot` takes its tentative slot BEFORE writing. An owned
        point that fails retains its separate reservation and retry hold; its
        successful-write slot must roll back with the transaction. Otherwise
        a retry would skip the immutable observation it still owes. Entered before the session
        and exited after it, so a failing or cancelled COMMIT reaches it.
        """
        prior = {eid: self._last_snapshot_at.get(eid) for eid in event_ids}
        try:
            yield
        except BaseException:
            for event_id, at in prior.items():
                if at is None:
                    self._last_snapshot_at.pop(event_id, None)
                else:
                    self._last_snapshot_at[event_id] = at
            raise

    def _client(self):
        """The one async Redis client this refresher publishes on, built lazily.

        Both publishers (event frames and #9484 market invalidations) take it
        from here, so a consumer holds one pool, not one per publisher — the
        #6515 census counts this as one construction site.
        """
        if self._redis is None:
            from app.tasks.redis_state import get_async_redis_client

            self._redis = get_async_redis_client()
        return self._redis

    async def publish_market_changes(self, session) -> int:
        """#9484: drain the market invalidations ``session`` staged and committed.

        Call AFTER the writer's ``get_task_session()`` block has exited, so only
        an outer commit that landed can publish (`market_quote_push` holds the
        rows until its after-commit hook moves them). It shares ``self._redis``
        with the event frames: one client per consumer, never one per flush,
        and it does not wait on ``refresh()`` — a standalone future has no
        event blend to stamp, and its quote is just as real. Never raises.
        """
        from app.utils.market_quote_push import take_committed_market_changes

        try:
            changes = take_committed_market_changes(session)
        except Exception:
            self.stats["market_publish_errors"] += 1
            logger.warning("live_blend_refresh[%s]: market detachment failed", self.source, exc_info=True)
            return 0
        return await self.publish_market_frames(changes)

    async def publish_market_frames(self, changes: list[dict]) -> int:
        """Publish already detached committed market invalidations."""
        from app.utils.market_quote_push import publish_market_changes

        try:
            sent = await publish_market_changes(changes, self._client())
        except Exception:
            self.stats["market_publish_errors"] += 1
            self._redis = None
            logger.warning(
                "live_blend_refresh[%s]: market publication failed",
                self.source, exc_info=True,
            )
            return 0
        self.stats["market_published"] += sent
        return sent

    async def _settle_normal_recovery(self, acknowledged):
        from sqlalchemy import text
        from app.tasks.base import get_task_session
        if not acknowledged:
            return
        if self._session_slots.locked():
            # Never queue behind a stamp for a slot: the next opportunity
            # settles these. Checked with no await before the acquisition.
            self._remember_normal_acks(acknowledged)
            return
        factory = self._session_factory or get_task_session
        # Settling an older ACK cannot erase a newer committed intent.
        async with asyncio.timeout(.25):
            async with self._session_slot(), factory() as session:
                for eid, rev in acknowledged:
                    await session.execute(text(
                        "DELETE FROM owed_chart_points WHERE source=:source "
                        "AND event_id=:eid AND (reading->>'rev')::bigint<=:rev"
                    ), {"source": self._normal_source, "eid": eid, "rev": rev})

    def _note_normal_debt(self):
        self._normal_has_debt = True
        self._normal_epoch += 1

    @staticmethod
    def _normal_revisions(frames):
        # Exactly the revisions `_publish` can acknowledge: an int at the
        # frame's own event key. A revision-less frame owes no intent.
        return {
            (f["event_id"], f["rev"][str(f["event_id"])]) for f in frames
            if isinstance(f.get("rev"), dict)
            and type(f["rev"].get(str(f["event_id"]))) is int
        }

    def _release_normal(self, held):
        self._normal_inflight.difference_update(held)

    @contextlib.asynccontextmanager
    async def _normal_holds(self):
        """The stamp transaction's held intent revisions.

        A failed transaction releases them: its intents never committed, and
        a stale hold would hide an older owed revision of the same game from
        discovery.
        """
        held = set()
        try:
            yield held
        except BaseException:
            self._release_normal(held)
            raise

    def _publish_prices_task(self, frames):
        """`_publish_prices` as its own task. A task cancelled before its
        first step never runs the coroutine's release, so the task's
        completion releases too (a second release is a no-op)."""
        task = asyncio.create_task(self._publish_prices(frames))
        held = self._normal_revisions(frames)
        task.add_done_callback(lambda _task: self._release_normal(held))
        return task

    def _remember_normal_acks(self, acknowledged):
        for eid, rev in acknowledged:
            if rev > self._normal_acked.get(eid, -1):
                self._normal_acked[eid] = rev

    async def _publish_prices(self, frames):
        """Publish committed price frames; remember what Redis acknowledged.

        No database work here. Settling an intent needs a session, and the
        publication lock orders the next cohort's frames behind this call:
        a DELETE awaited here held the next game's price behind the
        database (and one of the three stamp slots) on every publication.
        The next recovery opportunity settles the remembered revisions; a
        lost process leaves only intents whose recovery is price-free.

        Every publication is also a recovery opportunity, started here and
        awaited by nothing. A busy timed flush always has a price batch, so
        it never reaches `refresh_pending`; without this a failed game that
        went quiet waited for a fully empty flush.
        """
        expected = self._normal_revisions(frames)
        try:
            acknowledged = await self._publish(frames) or set()
        except BaseException as exc:
            self._release_normal(expected)
            self._note_normal_debt()
            if not isinstance(exc, Exception):
                raise
            logger.exception("live_blend_refresh[%s]: normal publication retained", self.source)
            self._start_normal_recovery()
            return set()
        if expected - acknowledged:
            self._note_normal_debt()
        # Resolved: acknowledged revisions are now in `_normal_acked`, the rest
        # are owed to the next opportunity.
        self._remember_normal_acks(acknowledged)
        self._release_normal(expected)
        self._start_normal_recovery()
        return acknowledged

    def _start_normal_recovery(self):
        task = self._normal_task
        if task is not None and not task.done():
            return
        if task is not None and not task.cancelled():
            task.exception()
        # Another owner may finish an already-started COMMIT after our empty
        # startup scan. Keep a bounded discovery opportunity on the existing
        # flush loop even when this instance has not recorded a failure.
        if self._normal_closed or _mono() < self._normal_retry_at:
            return
        self._normal_task = asyncio.create_task(self._recover_normal_prices())

    async def _recover_normal_prices(self):
        from sqlalchemy import text
        from app.tasks.base import get_task_session
        factory = self._session_factory or get_task_session
        try:
            # Recovery never queues for a stamp's slot: with all three taken,
            # this opportunity passes and the next one (after the cooldown)
            # tries again. Each of its three acquisitions checks this with no
            # await between the check and the acquisition.
            if self._session_slots.locked():
                return
            acked, self._normal_acked = self._normal_acked, {}
            if acked:
                try:
                    await self._settle_normal_recovery(set(acked.items()))
                except asyncio.CancelledError:
                    raise
                except Exception:
                    # Dropped, not restored: the durable rows remain, so the
                    # discovery below republishes their price-free control
                    # and its acknowledgement settles them.
                    logger.exception(
                        "live_blend_refresh[%s]: normal ACK settlement retained",
                        self.source,
                    )
            if self._session_slots.locked():
                return
            epoch = self._normal_epoch
            # Freeze a finite sweep: new arrivals cannot indefinitely postpone
            # retrying an older failed event. Both reads use (source, id); bound
            # raw rows BEFORE coalescing so duplicate revisions cannot turn a
            # LIMIT32 result into an unbounded DISTINCT/sort over the backlog.
            async with asyncio.timeout(.25):
                async with self._session_slot(), factory() as session:
                    if self._normal_horizon is None:
                        self._normal_horizon = (await session.execute(text(
                            "SELECT id FROM owed_chart_points WHERE source=:source "
                            "ORDER BY id DESC LIMIT 1"
                        ), {"source": self._normal_source})).scalar_one_or_none()
                        if self._normal_horizon is None:
                            if epoch == self._normal_epoch:
                                self._normal_has_debt = False
                            return
                    rows = (await session.execute(text(
                        "SELECT id, event_id, reading FROM owed_chart_points "
                        "WHERE source=:source AND id>:after AND id<=:horizon "
                        "ORDER BY id LIMIT 32"
                    ), {"source": self._normal_source, "after": self._normal_after,
                        "horizon": self._normal_horizon})).all()
            if not rows:
                self._normal_after = 0
                self._normal_horizon = None
                return
            self._normal_after = rows[-1].id
            if len(rows) < 32 or self._normal_after >= self._normal_horizon:
                self._normal_after = 0
                self._normal_horizon = None
            # These are price-free minimum-revision requests, not historical
            # prices. The reader fetches current authoritative state even when
            # a newer revision exists outside this bounded page. Keep the
            # highest revision per event within this page; never drop its debt
            # until publication is positively acknowledged.
            latest = {}
            for row in rows:
                prior = latest.get(row.event_id)
                if prior is None or row.reading["rev"] > prior.reading["rev"]:
                    latest[row.event_id] = row
            # A revision this process still owns belongs to its own publication:
            # in flight, or acknowledged after the swap above and settled by the
            # next opportunity. A control for it would cost every open reader
            # of a busy game a paired read. A lost process owns nothing, so a
            # fresh owner still republishes every intent.
            owned = dict(self._normal_acked)
            for eid, rev in self._normal_inflight:
                if rev > owned.get(eid, -1):
                    owned[eid] = rev
            rows = [
                row for row in latest.values()
                if row.reading["rev"] > owned.get(row.event_id, -1)
            ]
            frames = []
            for _cid, eid, reading in rows:
                rev = {str(eid): reading["rev"]}
                frames.append({
                    "event_id": eid, "p": None, "rev": rev,
                    "updated_at": reading["updated_at"], "reconcile_only": True,
                    "reconcile": {"event_id": eid,
                        "custody_id": f"normal-price:{eid}:{reading['rev']}",
                        "removal_rev": rev},
                })
            # No database session or event lock spans Redis publication.
            async with asyncio.timeout(.25):
                acknowledged = await self._publish(frames) if frames else set()
            await self._settle_normal_recovery(acknowledged)
        except Exception:
            logger.exception("live_blend_refresh[%s]: durable normal recovery retained", self.source)
        finally:
            self._normal_retry_at = _mono() + .5

    async def _close_normal_recovery(self):
        self._normal_closed = True
        task = self._normal_task
        if task is None:
            return
        if not task.done():
            task.cancel()
        interrupted = None
        while not task.done():
            try:
                await asyncio.wait({task})
            except asyncio.CancelledError as exc:
                interrupted = exc
        if not task.cancelled():
            task.exception()
        self._normal_task = None
        if interrupted is not None:
            raise interrupted

    async def _publish(self, frames: list[dict]) -> set[tuple[int, int]]:
        """Fan the committed frames out to any SSE subscribers. Never raises.

        Bounded packed sends avoid one Redis round trip per event (#10659).
        Frame bytes and order stay unchanged; only committed inputs reach this
        method. A PUBLISH with no listeners is successful publication.

        Each command error is consumed and counted without costing siblings.
        An unanswered send may already have run: do not retry inside this attempt.
        Return positively acknowledged revisions to the withdrawal custodian;
        its durable replay may resend the exact committed invalidation later.
        Timeout, cancellation or transport failure disconnects the borrowed
        socket before it returns to the consumer's shared pool.
        """
        acknowledged: set[tuple[int, int]] = set()
        if not frames:
            return acknowledged
        sent = 0
        retention_answered = False
        accounted = 0
        exact_trace = getattr(self.receipts, "exact_trace", None)
        try:
            import asyncio
            from redis.exceptions import ResponseError

            from app.utils.live_push import frame_publish_command
            from app.utils.market_quote_push import _checkout

            async with asyncio.timeout(5):
                client = self._client()
                pool = client.connection_pool
                connection = await _checkout(pool)
                try:
                    for start in range(0, len(frames), 32):
                        commands: list[tuple] = []
                        event_ids: list[int] = []
                        event_revisions: list = []
                        for frame in frames[start : start + 32]:
                            try:
                                commands.append(frame_publish_command(frame, require_replay=True))
                                event_ids.append(frame["event_id"])
                                event_revisions.append(frame.get("rev"))
                            except Exception:
                                accounted += 1
                                self.stats["publish_errors"] += 1
                                logger.warning(
                                    "live_blend_refresh[%s]: frame failed for event %s",
                                    self.source,
                                    frame.get("event_id"),
                                    exc_info=True,
                                )
                        if not commands:
                            continue
                        # Same direct pool protocol as committed MARKET signals.
                        # Pipeline.execute can retry an ambiguous transport write.
                        await connection.send_packed_command(
                            connection.pack_commands(commands)
                        )
                        for event_id, revision in zip(event_ids, event_revisions):
                            try:
                                reply = await connection.read_response()
                            except ResponseError as exc:
                                if str(exc) == "normal price replay retention failed after PUBLISH":
                                    # Lua already published and Redis answered. Keep
                                    # the healthy connection, but do not pay the
                                    # durable intent without replay custody.
                                    retention_answered = True
                                if exact_trace is not None:
                                    with contextlib.suppress(Exception):
                                        exact_trace.publication(event_id, revision, "REDIS_ERROR")
                                accounted += 1
                                self.stats["publish_errors"] += 1
                                logger.warning(
                                    "live_blend_refresh[%s]: publish failed for event %s",
                                    self.source,
                                    event_id,
                                    exc_info=True,
                                )
                                continue
                            if type(reply) is not int or reply < 0:
                                raise ValueError("invalid Redis PUBLISH acknowledgment")
                            accounted += 1
                            sent += 1
                            if isinstance(revision, dict) and type(revision.get(str(event_id))) is int:
                                acknowledged.add((event_id, revision[str(event_id)]))
                            self.stats["published"] += 1
                            if exact_trace is not None:
                                with contextlib.suppress(Exception):
                                    exact_trace.publication(event_id, revision, "REDIS_ACK")
                except BaseException:
                    # Unknown acknowledgment state: unread replies must not be
                    # handed to another consumer, nor commands replayed here.
                    self._redis = None
                    await connection.disconnect()
                    raise
                finally:
                    await pool.release(connection)
                if sent == 0 and not retention_answered:
                    self._redis = None
        except Exception:
            self.stats["publish_errors"] += len(frames) - accounted
            self._redis = None
            logger.warning(
                "live_blend_refresh[%s]: publication incomplete: acknowledged=%s queued=%s",
                self.source,
                sent,
                len(frames),
                exc_info=True,
            )
        return acknowledged

    # ── #10090: provisional preview (off by default; canary events only) ──

    def _current_reading_proof(self, event_id, group, refused, *, park_refused=True):
        """Keep optional observation previews on the ordinary Kalshi proof path."""
        proof_kwargs = {}
        if (getattr(self, "require_current_book_proof", False)
                and any(getattr(entry.market, "source", None) == "kalshi"
                        and (getattr(entry.market, "external_id", None) or "").upper().startswith("KXATPCHALLENGERMATCH-")
                        for entry in group)):
            proof_kwargs = {
                "require_current_book_midpoint": True,
                "current_book_midpoint": getattr(self, "current_book_midpoint", None),
                "current_book_primary_price": getattr(self, "current_book_primary_price", None),
                "current_primary_input": (
                    lambda row: self.current_primary_input(
                        row, self.held_quotes,
                        overlaid=getattr(row, "_primary_quote_overlaid", False),
                    )
                ) if getattr(self, "current_primary_input", None) is not None else None,
                # Bound now: with a canary in the batch this
                # callback is stored in `preview_plans` and
                # called again by the stamp-time recheck.
                "current_book_refused": lambda refused=refused, event_id=event_id, group=group: (
                    refused.append(True)
                    or (self._park_book_refused(event_id, group) if park_refused else None)
                ),
            }
        return proof_kwargs

    async def preview_accepted_observations(self, observations, validate) -> bool | None:
        """Preview acknowledged unchanged venue observations without owning writes.

        The consumer excludes same-event price/stamp ownership and holds its
        scope guard until this work finishes. Graphs/sessions are call-local;
        False asks the caller to retain frozen inputs after capacity/read failure.
        The graph and copied input clocks are disposable. A separately selected
        DB clock may advance held_quotes only for inputs received AFTER this
        read scope completes; the frozen clocks in this batch never change.
        `validate` rechecks immutable input identity and the flush's ownership
        under its buffer lock, including at the final Redis send boundary.
        """
        if self.source not in ("polymarket", "kalshi") or not self.preview:
            return
        from app.tasks.base import get_task_session
        from app.utils.aggregation import _coerce_timestamp
        from app.utils.blend_preview import PREVIEW_STATUSES, registry
        from app.utils.settledness import market_assigned_settled
        from app.utils.live_blend import compute_source_home_probability, has_proven_home_orientation

        read_timing = None
        try:
            event_ids = {eid for eid in observations if eid in self.preview_events}
            event_ids.intersection_update(await validate(event_ids))
            if not event_ids:
                return
            factory = (self._observation_read_factory
                       or self._session_factory or get_task_session)
            # Optional display work must not queue the game loop behind a
            # contended pool/read. The caller may retain the SAME frozen input.
            if self._session_slots.locked():
                return False
            grouped = None
            read_budget = asyncio.timeout(.25)
            read_timing = {"started_s": _mono()}
            clock_owner = self.held_quotes if self._observation_read_factory is not None else None
            clock_sample = None
            if isinstance(clock_owner, HeldRowQuotes) and not clock_owner._closed:
                clock_owner._sample_started += 1
                clock_ordinal = clock_owner._sample_started
                clock_owner._sampling += 1
                clock_owner._last_sample_started = clock_owner._now()
                clock_sample = {}
            try:
                token = _observation_read_timing.set(read_timing)
                try:
                    async with read_budget, self._session_slot(), factory() as session:
                        grouped = await self._read_groups(
                            session, sorted(event_ids), overlay_held=False,
                            **({"clock_sample": clock_sample} if clock_sample is not None else {}),
                        )
                        read_timing["graph_ready_ms"] = (_mono() - read_timing["started_s"]) * 1000
                    # Only normal context completion qualifies, never query or
                    # cleanup timeout/cancellation. A late older read cannot
                    # replace a newer sample or clear its failure episode.
                    if (clock_sample and self.held_quotes is clock_owner
                            and not clock_owner._closed
                            and clock_ordinal > clock_owner._sample_published):
                        clock_owner._database_bound = clock_sample["value"].timestamp()
                        clock_owner._sample_published = clock_ordinal
                        clock_owner._graph_sample_ordinal = clock_ordinal
                        # A graph read has a longer budget than the standalone
                        # clock probe. Its success supplies future input bounds,
                        # but cannot prove that shorter-budget path recovered.
                        # Only a standalone success clears its failure backoff.
                        clock_owner._last_sample_done = clock_owner._now()
                finally:
                    if clock_sample is not None:
                        clock_owner._sampling -= 1
                    read_timing["scope_ms"] = (_mono() - read_timing["started_s"]) * 1000
                    _observation_read_timing.reset(token)
            except TimeoutError:
                # A completed autocommit SELECT needs no commit acknowledgement.
                # Its detached graph remains usable if only connection cleanup
                # exhausts our budget. The existing context still owns cleanup;
                # query failures, writer scopes and external cancellation do not
                # qualify. All input/freshness/send-boundary checks below remain.
                if (self._observation_read_factory is None or grouped is None
                        or not read_budget.expired()):
                    raise
                logger.warning(
                    "live_blend_refresh[%s]: observation read completed; cleanup exceeded budget read_timing=%s",
                    self.source, _observation_read_summary(read_timing),
                )
            plans = {}
            refusals = {}
            for eid, (event, group) in grouped.items():
                if event.status not in PREVIEW_STATUSES or event.completed_at is not None:
                    refusals[eid] = "ineligible"
                    continue
                rows = {row.id: (entry, row) for entry in group for row in entry.outcomes}
                snapshot = observations[eid]
                relevant = [entry for entry in group
                            if any(row.id in snapshot for row in entry.outcomes)]
                if any(entry.market.status != "open"
                       or market_assigned_settled(entry.market, entry.outcomes)
                       or any(row.resolution_source is not None for row in entry.outcomes)
                       for entry in relevant):
                    refusals[eid] = "settled"
                    continue
                proof_kwargs = self._current_reading_proof(eid, group, [], park_refused=False)
                reading = compute_source_home_probability(
                    group, event.home_team_name, event.away_team_name, **proof_kwargs,
                )
                if reading is None or not has_proven_home_orientation(reading):
                    continue  # optional path never invokes repairing inversion fallback
                contributors = getattr(reading, "contributing_outcomes", None) or (reading.outcome,)
                ids = {getattr(row, "id", None) for row in contributors}
                if not ids or not ids.issubset(snapshot):
                    continue
                if any(oid not in rows for oid in snapshot):
                    continue
                valid = True
                read_wall = datetime.now(timezone.utc).timestamp()
                for oid, (value, bound, mark) in snapshot.items():
                    entry, row = rows[oid]
                    stored_at = _coerce_timestamp(row.last_updated)
                    if (mark is None or getattr(mark, "probability", None) != value
                            or type(bound) not in (float, int) or not math.isfinite(bound)
                            or entry.market.status != "open" or row.resolution_source is not None
                            or row.is_winner is True or stored_at is None
                            or stored_at.timestamp() >= bound or bound > read_wall
                            or row.current_probability is None
                            or round(float(row.current_probability), 6) != round(float(value), 6)):
                        valid = False
                        break
                if not valid:
                    continue
                # Keep the immutable DB-clock bounds exactly; the generic
                # observation helper clamps future clocks to app-now. Such
                # clamping would manufacture newer observations on retries.
                basis = {str(row.id): float(snapshot[row.id][1]) for row in contributors}
                if basis:
                    plans[eid] = (event, reading, basis, group, proof_kwargs)
            if not plans and not refusals:
                return

            async def prepare_frames():
                allowed = await validate(set(plans) | set(refusals))
                if not allowed:
                    return []  # rejection/cancellation must not mutate the registry
                preview = registry()
                frames = preview.expire()
                for eid in allowed:
                    if eid in refusals:
                        frames.extend(preview.refused(eid, self.source, refusals[eid]))
                        continue
                    event, reading, basis, group, proof_kwargs = plans[eid]
                    if proof_kwargs:
                        # Current book/custody proof may change during Redis checkout.
                        current = compute_source_home_probability(
                            group, event.home_team_name, event.away_team_name, **proof_kwargs,
                        )
                        if (current is None or not has_proven_home_orientation(current)
                                or round(current.home_probability, 4) != round(reading.home_probability, 4)
                                or {str(row.id) for row in (getattr(current, "contributing_outcomes", None)
                                                            or (current.outcome,))} != set(basis)):
                            continue
                    frames.extend(preview.propose(
                        eid, self.source, value=round(reading.home_probability, 4), event=event,
                        row_sources=event.preview_sources, row_rev=event.preview_rev,
                        eligibility=getattr(reading, "eligibility", None), observed_basis=basis,
                        observation_only=True,
                    ))
                return frames

            await self._publish_previews([], prepare_frames=prepare_frames)
        except Exception:
            self.preview_stats["publish_errors"] += 1
            logger.warning(
                "live_blend_refresh[%s]: optional observation preview unavailable read_timing=%s",
                self.source, _observation_read_summary(read_timing), exc_info=True,
            )
            return False

    async def _preview_before_stamp(self, grouped, plans, published_seq, *, observation_only=()) -> None:
        """Publish every planned reading's preview, then let the UPDATEs run.

        Called once per attempt after all readings were computed and before
        any event's UPDATE, so no event's row-lock wait delays another event's
        preview. A failure here costs only the preview; the stamp proceeds.
        """
        from app.utils.aggregation import observation_basis
        from app.utils.blend_preview import registry

        preview = registry()
        frames = preview.expire()
        for event_id, (_refused, _proof, reading, value, contributing) in plans.items():
            event, _group = grouped[event_id]
            try:
                frames.extend(preview.propose(
                    event_id, self.source, value=value, event=event,
                    row_sources=getattr(event, "preview_sources", None),
                    row_rev=getattr(event, "preview_rev", None),
                    eligibility=getattr(reading, "eligibility", None),
                    observed_basis=observation_basis(contributing),
                    observation_only=event_id in observation_only,
                ))
            except Exception:
                self.preview_stats["publish_errors"] += 1
                logger.warning(
                    "live_blend_refresh[%s]: preview for event %s not composed",
                    self.source, event_id, exc_info=True,
                )
                continue
            seq = preview.pending_seq(event_id, self.source)
            if seq is not None:
                published_seq[event_id] = seq
        await self._publish_previews(frames)

    def _preview_settlement(self, event_ids, grouped, published_seq, failed,
                            committed) -> list[dict]:
        """Settle this attempt's previews against what actually committed.

        Over every ATTEMPTED event, not only those the group read returned: an
        event this source no longer speaks for (unlinked, emptied, omitted by
        a prepared read) must not keep its pending value in the sibling's
        previews. Returns the frames; the caller orders their publication.
        """
        from app.utils.blend_preview import registry

        preview = registry()
        frames: list[dict] = []
        for event_id in dict.fromkeys(event_ids):
            if event_id not in self.preview_events:
                continue  # never proposed: nothing to settle
            try:
                if event_id not in grouped:
                    frames.extend(preview.refused(event_id, self.source, "no_group"))
                    continue
                if event_id in committed:
                    sources, rev, event = committed[event_id]
                    frames.extend(preview.committed(
                        event_id, self.source, seq=published_seq.get(event_id),
                        sources=sources, rev=rev, event=event,
                    ))
                    continue
                if event_id in failed:
                    reason = "error"
                else:
                    reason = (self._dispositions.get(event_id) or ("unknown",))[0]
                    if reason == "lock":
                        continue  # still owed; the retry republishes it
                    if reason in ("preview_only", "unobserved"):
                        # The optional proposal already judged this observation;
                        # absence of a newer durable row is not a withdrawal.
                        # The event restamp was deliberately throttled. Retain
                        # the bounded display chain, including its expiry fence,
                        # without pretending a failed write needs retrying.
                        continue
                # Also ends an expired chain with nothing pending (R4).
                frames.extend(preview.refused(event_id, self.source, reason))
            except Exception:
                self.preview_stats["publish_errors"] += 1
                logger.warning(
                    "live_blend_refresh[%s]: preview for event %s not settled",
                    self.source, event_id, exc_info=True,
                )
        return frames

    async def _claim_preview_epoch(self, connection, preview) -> None:
        """One atomic INCR + SET owner (`FENCE_CLAIM_SCRIPT`); caller holds the claim lock."""
        from app.utils.blend_preview import (
            FENCE_CLAIM_SCRIPT, FENCE_EPOCH_KEY, fence_owner_key,
        )

        if preview.ledger:
            # TSP-1: this source's owner claim in the shared ledger.
            await preview.claim(self._preview_call(connection), self.source)
        else:
            await connection.send_command(
                "EVAL", FENCE_CLAIM_SCRIPT, 2, FENCE_EPOCH_KEY, fence_owner_key(self.source),
            )
            preview.epoch = int(await connection.read_response())
        logger.info(
            "live_blend_refresh[%s]: preview display claimed epoch=%s",
            self.source, preview.claim_of(self.source),
        )

    @staticmethod
    def _preview_call(connection, *, send_before: Optional[float] = None):
        async def call(*args):
            if send_before is not None and asyncio.get_running_loop().time() >= send_before:
                raise TimeoutError("idle retirement pass ended before transmission")
            await connection.send_command(*args)
            return await connection.read_response()
        return call

    async def claim_preview_display(self) -> Optional[int]:
        """Claim this process's display epoch at startup, before any frame.

        Eager, so epoch order is process START order: a replacement started
        during a release overlap outranks the worker it replaces even if that
        worker has not previewed yet, instead of an old process's first frame
        in its final drain fencing the replacement for life. A no-op unless
        this arm previews, and when this process already holds an epoch.
        Never raises: a failed claim is retried by the first publication.
        """
        if not self.preview:
            return None
        try:
            from app.utils.blend_preview import registry
            from app.utils.market_quote_push import _checkout

            preview = registry()
            async with asyncio.timeout(1):
                if preview.claim_lock is None:
                    preview.claim_lock = asyncio.Lock()
                async with preview.claim_lock:
                    if preview.unclaimed(self.source):
                        pool = self._client().connection_pool
                        connection = await _checkout(pool)
                        try:
                            await self._claim_preview_epoch(connection, preview)
                        except BaseException:
                            self._redis = None
                            await connection.disconnect()
                            raise
                        finally:
                            await pool.release(connection)
            return preview.claim_of(self.source)
        except Exception:
            self.preview_stats["publish_errors"] += 1
            logger.warning(
                "live_blend_refresh[%s]: preview display claim failed at startup",
                self.source, exc_info=True,
            )
            return None

    async def _preview_ticket(self, *, include_candidates=False):
        from app.utils.blend_preview import registry
        from app.utils.market_quote_push import _checkout

        preview = registry()
        if preview.claim_lock is None:
            preview.claim_lock = asyncio.Lock()
        pool = self._client().connection_pool
        async with preview.claim_lock:
            connection = await _checkout(pool)
            try:
                if preview.unclaimed(self.source):
                    await self._claim_preview_epoch(connection, preview)
                if include_candidates:
                    return await preview.capacity_ticket(self._preview_call(connection), self.source)
                return await preview.read_ticket(self._preview_call(connection), self.source)
            except BaseException:
                self._redis = None
                await connection.disconnect()
                raise
            finally:
                await pool.release(connection)

    def _start_preview_maintenance(self):
        # One bounded pass per source per 30 seconds, independent of flush
        # cadence. No DB candidate scan or HKEYS on the admission path.
        if (not self._owns_preview_maintenance or self._preview_maintenance_closed or
                time.monotonic() < self._preview_maintenance_after or
                (self._preview_maintenance_task is not None and
                 not self._preview_maintenance_task.done())):
            return
        self._preview_maintenance_after = time.monotonic() + 30.0
        self._preview_maintenance_task = asyncio.create_task(self._maintain_preview_capacity())

    @staticmethod
    def _preview_retirable_row():
        from sqlalchemy import and_, or_, text
        from app.models.models import Event
        from app.tasks.ws_slate import SUSPENDED_SLATE_MAX_AGE_HOURS
        from app.utils.blend_preview import PREVIEW_STATUSES

        return or_(Event.status.not_in(PREVIEW_STATUSES), Event.completed_at.is_not(None),
                   and_(Event.status.in_(("scheduled", "suspended")),
                        Event.commence_time < text(
                            f"NOW() - INTERVAL '{int(SUSPENDED_SLATE_MAX_AGE_HOURS)} hours'")))

    async def _maintain_preview_capacity(self):
        from sqlalchemy import func, select
        from app.models.models import Event
        from app.tasks.base import get_task_session
        from app.utils.blend_preview import registry

        try:
            async with asyncio.timeout(1) as budget:
                ticket, candidates, idle, redis_now = await self._preview_ticket(include_candidates=True)
                # Redis sampled TIME before this local receipt. Flooring the remaining
                # budget makes the remote cutoff conservative absent clock steps/drift.
                when = budget.when()
                deadline_ms = (redis_now + int((when - asyncio.get_running_loop().time()) * 1000)
                               if redis_now is not None else None)
                if ticket is None or not candidates:
                    return
                factory = self._session_factory or get_task_session
                # Fetch existence and retirement eligibility together. This is
                # a fresh statement after the ticket, never cached slate data.
                async with self._session_slot(), factory() as session:
                    rows = (await session.execute(select(
                        Event.id, Event.win_probability_sources_rev,
                        self._preview_retirable_row().label("retirable"),
                        Event.status, Event.commence_time, func.now().label("read_at"),
                    ).where(Event.id.in_(candidates)))).all()
                present = {row[0]: row for row in rows}
                def priority(eid):
                    row = present.get(eid)
                    if row is None or row[2]:
                        return (0, 0, eid)
                    # Only future scheduled rows reach this idle branch.
                    return (1, -row[4].timestamp(), eid)

                def idle_target(row):
                    return (not row[2] and row[3] == "scheduled"
                            and row[4] is not None and row[4] > row[5])

                targets = sorted((eid for eid in candidates
                                  if eid not in present or present[eid][2]
                                  or (eid in idle and idle_target(present[eid]))),
                                 key=priority)[:32]
                # Reclaim a bounded batch rather than allowing just one new
                # event per cadence. Every deletion advances the barrier;
                # each next proof therefore needs a new ticket AND DB read.
                for index, eid in enumerate(targets):
                    row = present.get(eid)
                    if index:
                        ticket, _ = await self._preview_ticket()
                        if ticket is None:
                            return
                        async with self._session_slot(), factory() as session:
                            row = (await session.execute(select(
                                Event.id, Event.win_probability_sources_rev,
                                self._preview_retirable_row().label("retirable"),
                                Event.status, Event.commence_time, func.now().label("read_at"),
                            ).where(Event.id == eid))).first()
                    if row is None:
                        await self._publish_previews([registry().retire_missing(eid, self.source, ticket)])
                    elif row[2]:
                        # The background UPDATE shares the same three DB
                        # slots as quote reads, stamps and chart custody.
                        # Inline terminal callers already own their slot.
                        async with self._session_slot():
                            await self._retire_preview_event(eid, row[1], ticket)
                    elif eid in idle and idle_target(row):
                        if deadline_ms is None or deadline_ms <= redis_now:
                            return
                        await self._retire_idle_preview_event(eid, ticket, deadline_ms, when)
        except Exception:
            self.preview_stats["publish_errors"] += 1
            logger.warning("live_blend_refresh[%s]: preview capacity maintenance incomplete",
                           self.source, exc_info=True)

    async def _retire_idle_preview_event(
        self, event_id: int, ticket: int, deadline_ms: int, when: float,
    ) -> None:
        """Skip busy rows; hold fresh future-scheduled proof through mutation.

        An absent locked result means protected, missing or locked; none authorizes
        missing-row retirement. Publication happens after releasing the row.
        An uncertain outcome keeps the lock until the pass deadline; Redis
        refuses execution at/after its paired cutoff. Redis clock rollback,
        rate drift/failover and involuntary DB lock loss remain residuals:
        this is not distributed atomicity across the two stores.
        """
        from sqlalchemy import func, select
        from app.models.models import Event
        from app.tasks.base import get_task_session
        from app.utils.blend_preview import registry

        factory = self._session_factory or get_task_session
        frames = []
        async with self._session_slot(), factory() as session:
            row = (await session.execute(select(
                Event.status, Event.win_probability_sources_rev,
            ).where(
                Event.id == event_id, Event.status == "scheduled",
                Event.commence_time.is_not(None), Event.commence_time > func.now(),
                Event.completed_at.is_(None),
            ).with_for_update(read=True, skip_locked=True))).first()
            if row is None:
                return
            operation = registry().retire_idle(event_id, self.source, row[1], ticket, deadline_ms)
            operation["send_before"] = when
            try:
                frames = await self._prepare_ledger_previews([operation])
            except BaseException as exc:
                # Before session rollback releases FOR SHARE, including on shutdown,
                # transport errors and repeated cancellation from the outer timeout.
                await self._hold_idle_proof_until(when, exc)
        await self._publish_previews(frames)

    @staticmethod
    async def _hold_idle_proof_until(when: float, error: BaseException) -> None:
        first_cancel = error if isinstance(error, asyncio.CancelledError) else None
        loop = asyncio.get_running_loop()
        while loop.time() < when:
            try:
                await asyncio.sleep(max(0.0, when - loop.time()))
            except asyncio.CancelledError as exc:
                if first_cancel is None:
                    first_cancel = exc
        # Never uncancel: the outer timeout must see a prior shutdown cancellation.
        if first_cancel is not None:
            raise first_cancel
        raise error

    async def _close_preview_maintenance(self):
        self._preview_maintenance_closed = True
        task = self._preview_maintenance_task
        if task is None:
            return
        if not task.done():
            task.cancel()
        interrupted = None
        while not task.done():
            try:
                await asyncio.wait({task})
            except asyncio.CancelledError as exc:
                interrupted = exc
        if not task.cancelled():
            task.exception()
        if interrupted is not None:
            raise interrupted

    async def _preview_admission_read(self) -> Optional[int]:
        """Read-before-admit ticket, without capacity scans on the flush path."""
        from app.utils.blend_preview import registry
        if not registry().ledger:
            return None
        self._start_preview_maintenance()
        try:
            async with asyncio.timeout(.25):
                before, _ = await self._preview_ticket()
                return before
        except Exception:
            self.preview_stats["publish_errors"] += 1
            logger.warning("live_blend_refresh[%s]: preview admission read unavailable", self.source,
                           exc_info=True)
            return None

    async def _retire_terminal_preview_read(self, grouped, ticket: int) -> None:
        from app.utils.blend_preview import PREVIEW_STATUSES, registry

        preview = registry()
        for event_id, (event, _group) in grouped.items():
            if event_id not in self.preview_events:
                continue
            if event.status not in PREVIEW_STATUSES or event.completed_at is not None:
                rev = getattr(event, "preview_rev", None)
                if type(rev) is int and rev >= 0:
                    # One retirement per statement ticket. A racing retirement
                    # refuses this one; it must wait for another real read.
                    await self._retire_preview_event(event_id, rev, ticket)
                    return

    async def _retire_preview_event(self, event_id: int, read_rev: int, ticket: int) -> None:
        """Preserve an ineligible row's floor before forgetting Redis state.

        A fresh read alone is insufficient: source revisions do not change on
        status-only updates. Under the event row lock, this conditional SQL
        increment leaves every future read strictly above the retired floor.
        It changes neither source values nor observation timestamps. A failed
        or timed-out transaction leaves the existing Redis guard in place.
        """
        from sqlalchemy import update
        from app.models.models import Event
        from app.tasks.base import get_task_session
        from app.utils.blend_preview import registry

        preview = registry()
        try:
            async with asyncio.timeout(.25):
                # Close the preview first, including if the durable advance
                # cannot acquire its row. Later duplicate terminal operations
                # carry the old ticket and cannot recreate retired state.
                await self._publish_previews([{
                    "ledger_op": "terminal", "event_id": event_id, "source": self.source,
                    "ctx_rev": read_rev, "read_ticket": ticket,
                }])
                factory = self._session_factory or get_task_session
                async with factory() as session:
                    durable = (await session.execute(update(Event).where(
                        Event.id == event_id,
                        self._preview_retirable_row(),
                        Event.win_probability_sources_rev >= read_rev,
                        Event.win_probability_sources_rev < 9007199254740991,
                    ).values(win_probability_sources_rev=Event.win_probability_sources_rev + 1)
                      .returning(Event.win_probability_sources_rev))).scalar_one_or_none()
                    if durable is None:
                        return
                    await session.commit()
                # Only a successful COMMIT can authorize deletion. Redis
                # still checks ticket, owners, and all event-local floors.
                await self._publish_previews([
                    preview.retire_read(event_id, self.source, durable - 1, ticket,
                                        committed_rev=durable),
                ])
        except Exception:
            self.preview_stats["publish_errors"] += 1
            logger.warning("live_blend_refresh[%s]: preview retirement incomplete", self.source,
                           exc_info=True)

    async def _prepare_ledger_previews(self, items: list) -> list[dict]:
        """TSP-1: run settlement operations now, so their frames can be ordered.

        Single-source registries already return frames: unchanged. A failure
        costs only the preview (the frames are dropped), never the commit.
        """
        if not items or not any("ledger_op" in item for item in items):
            return items
        idle = [item for item in items if item.get("ledger_op") == "retire_idle"]
        send_before = min((item["send_before"] for item in idle), default=None)
        try:
            from app.utils.blend_preview import registry
            from app.utils.market_quote_push import _checkout

            preview = registry()
            async with asyncio.timeout(1):
                if preview.claim_lock is None:
                    preview.claim_lock = asyncio.Lock()
                pool = self._client().connection_pool
                async with preview.claim_lock:
                    connection = await _checkout(pool)
                    first_error = None
                    try:
                        if preview.unclaimed(self.source):
                            await self._claim_preview_epoch(connection, preview)
                        call = (self._preview_call(connection, send_before=send_before)
                                if idle else self._preview_call(connection))
                        return await preview.prepare(items, call, self.preview_stats)
                    except BaseException as exc:
                        first_error = exc
                        self._redis = None
                        try:
                            await connection.disconnect()
                        except BaseException as cleanup_error:
                            # A shutdown may arrive while cleaning up an ordinary
                            # transport failure. Preserve the first cancellation.
                            if (isinstance(cleanup_error, asyncio.CancelledError)
                                    and not isinstance(first_error, asyncio.CancelledError)):
                                first_error = cleanup_error
                        raise first_error
                    finally:
                        try:
                            await pool.release(connection)
                        except BaseException as cleanup_error:
                            if (isinstance(cleanup_error, asyncio.CancelledError)
                                    and not isinstance(first_error, asyncio.CancelledError)):
                                first_error = cleanup_error
                            if first_error is not None:
                                raise first_error
                            raise
        except Exception as exc:
            self.preview_stats["publish_errors"] += 1
            logger.warning(
                "live_blend_refresh[%s]: ledger preview settlement incomplete (%s operations)",
                self.source, len(items), exc_info=True,
            )
            if idle:
                raise PreviewSettlementUncertain("idle retirement reply unavailable") from exc
            return []

    async def _publish_previews(self, frames: list[dict], *, prepare_frames=None) -> None:
        """Fenced PUBLISH of provisional frames. Never raises; never retained.

        Not `_publish`: a preview has no revision, owes no recovery intent and
        must never be counted, acknowledged or replayed as a committed frame.
        Same direct pool protocol, so a borrowed socket left in an unknown
        state is disconnected rather than returned.

        The process normally claimed its epoch at startup
        (`claim_preview_display`); if that claim failed, the first call here
        claims it. Every batch then goes through `FENCE_PUBLISH_SCRIPT`, which
        drops the blends of a process another worker has superseded. No
        epoch, no blend.
        """
        if not frames and prepare_frames is None:
            return
        try:
            import json

            from app.utils.blend_preview import (
                FENCE_PUBLISH_SCRIPT, fence_owner_key, registry,
            )
            from app.utils.live_push import event_channel
            from app.utils.market_quote_push import _checkout

            preview = registry()
            owner_key = fence_owner_key(self.source)
            async with asyncio.timeout(1):
                if preview.claim_lock is None:
                    preview.claim_lock = asyncio.Lock()
                pool = self._client().connection_pool
                async with preview.claim_lock:
                    connection = await _checkout(pool)
                    try:
                        if preview.unclaimed(self.source):
                            await self._claim_preview_epoch(connection, preview)
                        if prepare_frames is not None:
                            frames = await prepare_frames()
                            if not frames:
                                return
                        if preview.ledger:
                            # TSP-1: operations and prepared frames run through
                            # the ledger CAS; nothing is relabeled here.
                            await preview.execute(
                                frames, self._preview_call(connection), event_channel,
                                self.preview_stats,
                            )
                            return
                        # A blend composed before this lock may be older than a
                        # revoke another batch sent while it waited (#10090).
                        kept = [f for f in frames if not preview.withdrawn(f)]
                        if len(kept) < len(frames):
                            self.preview_stats["withdrawn"] = (
                                self.preview_stats.get("withdrawn", 0) + len(frames) - len(kept)
                            )
                            frames = kept
                            if not frames:
                                return
                        argv: list = [preview.epoch]
                        for frame in frames:
                            preview.sending(frame)
                            frame["preview"]["epoch"] = preview.epoch
                            argv.extend((
                                frame["preview"]["kind"],
                                event_channel(frame["event_id"]),
                                json.dumps(frame),
                            ))
                        await connection.send_command(
                            "EVAL", FENCE_PUBLISH_SCRIPT, 1, owner_key, *argv,
                        )
                        published, fenced, owner = await connection.read_response()
                    except BaseException:
                        self._redis = None
                        await connection.disconnect()
                        raise
                    finally:
                        await pool.release(connection)
            revokes = sum(1 for f in frames if f["preview"]["kind"] == "revoke")
            self.preview_stats["revoked"] += revokes
            self.preview_stats["published"] += int(published) - revokes
            if int(fenced):
                self.preview_stats["fenced"] += int(fenced)
                if isinstance(owner, bytes):
                    owner = owner.decode()
                logger.warning(
                    "live_blend_refresh[%s]: %s preview frame(s) fenced: epoch=%s owner=%s",
                    self.source, fenced, preview.epoch, owner or "missing",
                )
        except Exception:
            self.preview_stats["publish_errors"] += 1
            logger.warning(
                "live_blend_refresh[%s]: preview publication incomplete (%s frames)",
                self.source, len(frames), exc_info=True,
            )

    async def _maybe_snapshot(
        self, session, event_id: int, value: float, reading, now: float,
    ) -> None:
        """Append this reading to the chart series, on the snapshot clock.

        Called only after a blend stamp actually happened, which on a FLAT
        market is the `unchanged_restamp_interval_s` beat (45s) rather than the
        2s blend beat. `_create_or_update_win_prob_snapshot` is the same helper
        the 120s poll uses — it appends a row on a value CHANGE and, since
        live/035, also once `max_gap_seconds` of silence have passed, so a
        motionless market still draws a breathing line instead of one straight
        segment between its endpoints.

        Failures are swallowed and counted like everything else in this module:
        the chart is downstream of the number, and a snapshot that cannot be
        written must not cost the blend stamp that already succeeded.
        """
        # #11181: an owned point was spaced by the reservation that admitted
        # it, and its custody row is settled with it, so it is never skipped
        # here. A point loaded from custody has no clock of this process.
        owned = getattr(reading, "owned_history", False)
        if now is not None:
            last = self._last_snapshot_at.get(event_id)
            if not owned and last is not None and (now - last) < self.snapshot_interval_s:
                return
            self._last_snapshot_at[event_id] = now

        try:
            from app.tasks.snapshots import _create_or_update_win_prob_snapshot
            from app.tasks.prediction_market_matching import _second_slot

            # #6277 — THE SAME SECOND SLOT THE 15-MINUTE MATCHER WRITES, from the
            # same helper. This lane recomputes the number every few seconds from
            # the same rows, so a partition published by the matcher and
            # complemented here would be overwritten with the fabricated value
            # within one tick — during the match, which is the window the
            # photographed card was taken in. The two writers disagreeing is the
            # one thing this module exists to prevent, and it applies to the away
            # slot exactly as it applies to the home one.
            away_value, draw_value = _second_slot(reading, value)

            snapshot, is_new = await _create_or_update_win_prob_snapshot(
                session,
                event_id=event_id,
                source=self.source,
                home_win_probability=value,
                away_win_probability=round(away_value, 4),
                draw_probability=None if draw_value is None else round(draw_value, 4),
                game_state={
                    "market_name": getattr(reading.market, "name", None),
                    "market_id": getattr(reading.market, "id", None),
                    "outcome_name": getattr(reading.outcome, "name", None),
                    "yes_probability": reading.yes_probability,
                    # Distinguishable from the poll's "live_fast" in the audit
                    # trail, so "which writer produced this point" stays a
                    # question the data can answer.
                    "poll_type": "ws_fast_lane",
                },
                max_gap_seconds=heartbeat_deadline(
                    self.snapshot_max_gap_s, self.snapshot_interval_s
                ),
                observed_at=getattr(reading, "snapshot_observed_at", None),
            )
            if is_new:
                session.add(snapshot)
                self.stats["snapshots_written"] += 1
            else:
                self.stats["snapshots_deduped"] += 1
        except Exception:
            if getattr(reading, "owned_history", False):
                raise
            self.stats["errors"] += 1
            logger.exception(
                "live_blend_refresh[%s]: snapshot failed for event %s",
                self.source, event_id,
            )

    def _should_write(self, event_id: int, value: float, now: float) -> bool:
        """Write on any real move; on no move, re-stamp only occasionally.

        The re-stamp is not cosmetic. `updated_at` feeds the hero's RELATIVE
        recency decay, so a source that keeps quoting the same price must keep
        saying so or it slowly loses weight against noisier siblings and the
        blend drifts toward whichever source moves most.
        """
        previous = self._last_written_value.get(event_id)
        if previous is None or previous != value:
            return True
        last_write = self._last_write_at.get(event_id, 0.0)
        return (now - last_write) >= self.unchanged_restamp_interval_s


def event_ids_for_outcomes(
    outcome_to_event: dict[int, Optional[int]], outcome_ids: Iterable[int]
) -> set[int]:
    """The distinct linked event ids behind a batch of flushed outcomes."""
    seen: set[int] = set()
    for outcome_id in outcome_ids:
        event_id = outcome_to_event.get(outcome_id)
        if event_id is not None:
            seen.add(event_id)
    return seen


# ── #9462 review: owed stamps survive a recycle ──────────────────────────────
#
# Each consumer run builds a NEW refresher, and the final drain stops as soon as
# the price buffer is empty. A price committed inside the 2 s throttle (or behind
# a row lock) is held in `_throttle_deferred` / `_lock_retry` and stamped by a
# LATER flush — but at a recycle there is no later flush in this run, and the
# next run's refresher started empty. The outcome price stayed in the database;
# the number on the card waited for another venue tick or the 120 s poll. #9418's
# admission recycle made that end-of-run far more frequent.
#
# So the ending run hands its owed events to the next run of the same source,
# which adopts them before its first flush. Process-local on purpose: the two
# consumers of a dyno run in one process, and a restart takes the owed stamps
# with it exactly as it takes the socket. A hand-off older than
# `PENDING_HANDOFF_TTL_S` is dropped — by then the poll has restamped the event.

#: The oldest hand-off a new run adopts. The 120 s poll restamps every live
#: event on its own; carrying a stamp past that would only re-date its work.
PENDING_HANDOFF_TTL_S = 120.0

_pending_handoff: dict[str, tuple[float, frozenset]] = {}
_history_handoff: dict[str, tuple] = {}


def hand_off_pending(refresher) -> int:
    """Leave `refresher`'s owed stamps for the next run of its source.

    Returns how many blend events were handed off. Committed history scalars
    travel separately, without the blend handoff's age cutoff. Its owner must
    already be joined; a legacy/test refresher without that owner is supported.
    Both consumers call this in their teardown `finally`, so it also closes the
    run's idle bound sampler; their `reap_stopped_loops` then joins it.
    """
    held = getattr(refresher, "held_quotes", None)
    if isinstance(held, HeldRowQuotes):
        _park_closing_sampler(getattr(refresher, "source", None), held.close())
    try:
        if refresher._history_task is not None and not refresher._history_task.done():
            raise RuntimeError("history owner must join before handing off its debt")
        debt = tuple((eid, value, reading, at) for eid, value, reading, at, _ in refresher._history)
        if debt:
            _history_handoff[refresher.source] = debt
            refresher._history.clear()
            refresher._history_count = 0
            refresher._history_reserved.clear()
        else:
            _history_handoff.pop(refresher.source, None)
    except AttributeError:
        pass  # legacy/test refresher without a chart owner
    try:
        pending = frozenset(refresher.pending_event_ids())
        # #11317 P2: a parked refused pair is owed too; the next run's book
        # decides it again (`adopt_pending` makes it due once).
        pending |= frozenset(getattr(refresher, "_book_refused", ()))
    except Exception:
        return 0
    if pending:
        _pending_handoff[refresher.source] = (_mono(), pending)
    else:
        _pending_handoff.pop(refresher.source, None)
    return len(pending)


def adopt_handed_off(refresher) -> int:
    """Give `refresher` the stamps the previous run of its source still owed.

    Returns how many blend events were adopted (0 when none, too old, or the
    refresher cannot adopt). History is separate committed observation debt and
    keeps its original times through a recycle, even after a later poll point.
    """
    try:
        debt = _history_handoff.pop(refresher.source, ())
        for eid, value, reading, at in debt:
            ready = asyncio.Event()
            ready.set()
            refresher._history.append((eid, value, reading, at, ready))
            refresher._history_count += 1
            if at is not None:  # a point loaded from custody carries no clock
                refresher._history_reserved[eid] = at
    except AttributeError:
        pass
    try:
        handed = _pending_handoff.pop(refresher.source, None)
    except Exception:
        return 0
    if handed is None:
        return 0
    at, pending = handed
    if _mono() - at > PENDING_HANDOFF_TTL_S:
        return 0
    try:
        refresher.adopt_pending(pending)
    except Exception:
        return 0
    return len(pending)
