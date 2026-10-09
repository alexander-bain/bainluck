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

Each chart point shares its event's blend transaction. A single admitted event
keeps its direct read/write path; multiple events prepare each fresh/pending
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
import contextlib
from collections import deque
import logging
import math
import time
from dataclasses import dataclass
from typing import Awaitable, Callable, Iterable, Optional

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
DEFAULT_STAMP_LOCK_TIMEOUT_MS = 500

# Old stamp retries must not occupy an entire periodic flush while fresh quote
# writes wait for the next one. Cooperative: finish each attempted transaction
# and publication; never cancel a stamp merely because this budget elapsed.
PENDING_STAMP_BUDGET_S = 1.0

# #10090 — fixed fresh-stamp workers per refresh. Two disjoint stamps waiting
# on rows/publication must not hold a third ready fresh event. Each holds one
# session only inside its stamp; with a consumer's price writer and standalone
# writer that is the lent engine's five connections (pool 3 + overflow 2).
FRESH_STAMP_WORKERS = 3

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


def _iso(wall: Optional[float]) -> Optional[str]:
    if wall is None:
        return None
    from datetime import datetime, timezone

    return datetime.fromtimestamp(wall, timezone.utc).isoformat(timespec="milliseconds")


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
        {"stamped", "unchanged", "unobserved", "no_reading", "no_row", "no_market"}
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
        staged: dict[int, InputMark] = {}
        for mark in marks:
            held = staged.get(mark.event_id)
            if held is None or mark.seq > held.seq:
                staged[mark.event_id] = mark
        self._staged = staged
        self._staged_wall = _wall()

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
        elif result in ("unchanged", "unobserved", "stale"):
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
    * The ceiling. Never more than one flush per ``period``: the configured
      cadence is the bound, as it always was. A flush that takes longer than
      ``period`` is followed by the next at once (rate ``1/work``, not more).
    * The retry interval. A flush that reports failure (returns ``False``) waits
      a full ``period`` from when it FAILED, exactly as before. An opt-in caller
      may pass ``failed_retry_interval_s`` to keep its previous retry delay while
      shortening only its healthy timer (#10662). Unchanged callers retain their
      configured period, including custom periods.
    * The first flush is one ``period`` after the loop starts, as before.

    ``flush`` is called with the flush's start on the refresher's clock
    (`_mono`), which the refresher uses for its per-event floor: starts are at
    least ``period`` apart, so a floor equal to the period admits every flush,
    whatever each flush's write happened to cost before its refresh ran.

    #10657 — ``stop`` (an ``asyncio.Event``) ends the loop at its next turn.
    The consumer sets it before it cancels the loop, because a cancellation
    alone is not a stop: one lost inside a flush's dependencies left an
    earlier run's loop calling ``refresh_pending`` on that run's CLOSED
    sessions every 6 s on production (2026-10-07 02:53Z, 33 and 9 events,
    across a recycle). Checked after every sleep and every flush; a stopped
    loop never starts another flush — the consumer's own drain is the last.
    """
    import asyncio

    def stopped() -> bool:
        return stop is not None and stop.is_set()

    retry_period = period if failed_retry_interval_s is None else failed_retry_interval_s
    due = _mono() + period
    while not stopped():
        wait = due - _mono()
        if wait > 0:
            await asyncio.sleep(wait)
            if stopped():
                return
        started = max(due, _mono())
        ok = await flush(started)
        due = started + period if ok is not False else _mono() + retry_period


#: #10657 — how long a consumer waits, after its final drain, for its stopped
#: flush and stats loops to return. A loop mid-flush finishes that flush (its
#: sessions are still open until the consumer returns); one still running
#: after this is reported by name, never waited on forever.
LOOP_REAP_TIMEOUT_S = 15.0


async def reap_stopped_loops(source: str, tasks, *, timeout_s: float = LOOP_REAP_TIMEOUT_S) -> int:
    """Wait (bounded) for a consumer run's stopped loops; return how many are
    STILL running. Never raises and never cancels again: the caller already
    set the stop event and cancelled them. A non-zero return is logged as an
    error because that loop outlives its run (#10657)."""
    import asyncio

    pending = [t for t in tasks if t is not None and not t.done()]
    if pending:
        try:
            _done, still = await asyncio.wait(pending, timeout=timeout_s)
        except Exception:
            still = {t for t in pending if not t.done()}
    else:
        still = set()
    if still:
        logger.error(
            "live_blend_refresh[%s]: %d consumer loop(s) still running %.0fs "
            "after the run stopped them: %s",
            source, len(still), timeout_s,
            sorted(getattr(t, "get_name", lambda: "?")() for t in still),
        )
    return len(still)


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
)


class LiveBlendRefresher:
    """Stateful per-source refresher, owned by one WS consumer run.

    State (throttles, inversion verdicts) is per-instance rather than global so
    the Kalshi and Polymarket consumers on the shared dyno cannot evict each
    other's entries, and so a reconnect starts clean.
    """

    def __init__(
        self,
        source: str,
        *,
        min_refresh_interval_s: float = DEFAULT_MIN_REFRESH_INTERVAL_S,
        failed_retry_interval_s: float = DEFAULT_FAILED_RETRY_INTERVAL_S,
        inversion_ttl_s: float = DEFAULT_INVERSION_TTL_S,
        unchanged_restamp_interval_s: float = UNCHANGED_RESTAMP_INTERVAL_S,
        snapshot_interval_s: float = DEFAULT_SNAPSHOT_INTERVAL_S,
        snapshot_max_gap_s: float = DEFAULT_SNAPSHOT_MAX_GAP_S,
        stamp_lock_timeout_ms: Optional[int] = DEFAULT_STAMP_LOCK_TIMEOUT_MS,
        session_factory=None,
    ) -> None:
        self.source = source
        #: #2471 — the owning consumer's session factory, so the stamp borrows
        #: the consumer's one engine instead of building a pool per batch.
        #: None ⇒ ``app.tasks.base.get_task_session``, looked up per batch.
        self._session_factory = session_factory
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
        self._last_refresh_at: dict[int, float] = {}
        #: Events whose last batch failed -> the monotonic time before which
        #: they are not due, whatever the throttle says.
        self._failed_hold_until: dict[int, float] = {}
        self._last_write_at: dict[int, float] = {}
        self._last_written_value: dict[int, float] = {}
        self._last_snapshot_at: dict[int, float] = {}
        self._inversion: dict[int, tuple[float, bool]] = {}
        self.stats: dict[str, int] = {
            "considered": 0,
            "throttled": 0,
            "no_reading": 0,
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
            # #837 tail — stamps that stopped waiting on another transaction's
            # row lock and were re-queued. Not an error: the retry is the path.
            "lock_skipped": 0,
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
        now = _mono()
        clock = now if flush_started is None else flush_started
        receipts = self.receipts
        staged, stored_wall = (
            self._receipt_call(receipts.take_staged) if receipts is not None else None
        ) or ({}, None)
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

        def pending_budget_spent():
            return (
                flush_started is not None
                and self._pending_attempted
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
        self.stats["considered"] += len(due)
        # Counted once per throttled price, not once per flush it waits out.
        skipped = len(self._throttle_deferred.difference(deferred))
        if skipped > 0:
            self.stats["throttled"] += skipped
        if receipts is not None:
            self._receipt_call(receipts.observe, staged, stored_wall, set(due), now)
        if not due:
            return self.stats

        self._dispositions = {}
        # One event already owns its transaction. For multiple admitted events,
        # prepare once and commit each independently so a later row lock cannot
        # hold an earlier stamp or its publication until the batch ends.
        if len(due) == 1:
            pending_only = due[0] not in fresh
            if pending_only and flush_started is not None:
                if self._pending_started_at is None:
                    self._pending_started_at = _mono()
                self._pending_attempted = True
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
            else:
                if receipts is not None:
                    self._receipt_call(
                        receipts.resolve,
                        due,
                        self._dispositions,
                        staged,
                        stored_wall,
                        _mono(),
                    )
            return self.stats

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
                publishing = asyncio.create_task(self._publish(frames))

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

        try:
            # Read/stamp fresh prices before reading older debt. Each nonempty
            # population prepares one view for order and the initial worker
            # claims. Queued fresh stamps reread below; old debt and the
            # singleton path above keep their existing read behavior.
            for population in (fresh.intersection(due), set(due).difference(fresh)):
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
                    continue
                if pending_only and flush_started is not None:
                    if self._pending_started_at is None:
                        self._pending_started_at = _mono()
                # A fresh population that fits the fixed workers has no claim
                # order to decide: every event starts at once. Each stamp reads
                # its own group in its own write session, as a singleton does,
                # rather than every stamp first waiting on a separate session's
                # read of all of them. A read failure stays with its own event.
                prepared = None
                try:
                    if pending_only or len(population) > FRESH_STAMP_WORKERS:
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
                    continuation = [
                        eid for eid in self._pending_continuation if eid in population
                    ]
                    carried = set(continuation)
                    ordered = continuation + [eid for eid in ordered if eid not in carried]

                async def stamp_event(event_id, *, read_current=False):
                    self._pending_continuation = [
                        eid for eid in self._pending_continuation if eid != event_id
                    ]
                    if pending_only and flush_started is not None:
                        self._pending_attempted = True
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

                if not pending_only:
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
                            self._pending_continuation = ordered[index:] + [
                                eid for eid in self._pending_continuation
                                if eid not in population
                            ]
                            break
                        await stamp_event(event_id)
            await publication_done()
        except CancelledError as exc:
            remaining = set(due).difference(completed, failed_groups, budget_deferred)
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
            # running beside the consumer's final drain or next refresh.
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
                    publishing = asyncio.create_task(self._publish(frames))
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
        if not self._lock_retry and not self._throttle_deferred:
            if self.receipts is not None:
                # #10090: a quiet flush still closes a finished minute.
                self._receipt_call(self.receipts.roll)
            return self.stats
        return await self.refresh(
            (), flush_started=flush_started, defer_event_ids=defer_event_ids,
        )

    def pending_event_ids(self) -> frozenset:
        """Every event this refresher still owes a stamp (#9462 review)."""
        return frozenset(self._lock_retry | self._throttle_deferred)

    def adopt_pending(self, event_ids: Iterable[int]) -> None:
        """Take over stamps a previous run of this source still owed.

        Queued as throttle-deferred: this refresher has never stamped them, so
        the first flush (`refresh` or `refresh_pending`) finds them due.
        """
        self._throttle_deferred.update(event_ids)

    async def _read_groups(self, session, event_ids: list[int]) -> dict[int, tuple]:
        from types import SimpleNamespace
        from sqlalchemy import and_, func, literal, or_, select
        from app.models.models import Event, FuturesMarket, FuturesOutcome
        from app.utils.live_blend import MarketOutcomes
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
        fields = (
            (FuturesMarket, PREPARED_MARKET_FIELDS),
            (Event, PREPARED_EVENT_FIELDS),
            (FuturesOutcome, PREPARED_OUTCOME_FIELDS),
        )
        rows = (
            await session.execute(
                select(*(
                    Event.win_probability_sources.op("->")(literal(self.source)).label(key)
                    if model is Event and key == "win_probability_sources"
                    else getattr(model, key)
                    for model, keys in fields for key in keys
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
        grouped: dict[int, tuple] = {}
        entries: dict[int, MarketOutcomes] = {}
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
                    context["win_probability_sources"] = {
                        self.source: context["win_probability_sources"],
                    }
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
                entry.outcomes.append(SimpleNamespace(**dict(zip(
                    PREPARED_OUTCOME_FIELDS, outcome_values
                ))))
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
        async with factory() as session:
            return await self._read_groups(session, event_ids)

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
        from app.utils.live_push import build_frame
        from app.utils.repair_lock_budget import (
            SET_LOCK_TIMEOUT_SQL, is_lock_timeout, lock_timeout_value,
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
        # #837 tail (Codex review of #8490) — and for the same reason the
        # write bookkeeping is COLLECTED and applied only after the commit. A
        # released savepoint is not a committed stamp: recorded there, a failed
        # commit left `_should_write` believing the price was stored, so the
        # retry of a lock-deferred event skipped it as unchanged and the price
        # was lost for good.
        written: dict[int, float] = {}

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
            self._snapshot_slots_follow_the_commit(event_ids),
            get_task_session() as session,
        ):
            if prepared is None:
                grouped = await self._read_groups(session, event_ids)
            else:
                grouped = {
                    eid: prepared[eid] for eid in event_ids if eid in prepared
                }
            if not grouped:
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

            async def ensure_lock_budget():
                nonlocal lock_budget_set, lock_budget_failed
                if not self.stamp_lock_timeout_ms or lock_budget_set:
                    return
                try:
                    await session.execute(
                        SET_LOCK_TIMEOUT_SQL,
                        {"ms": lock_timeout_value(self.stamp_lock_timeout_ms)},
                    )
                except Exception:
                    # Budget setup used to fail outside the event loop. Keep
                    # its whole-batch rollback/requeue, never swallow it as a
                    # single failed event in an unbounded transaction.
                    lock_budget_failed = True
                    raise
                lock_budget_set = True

            for event_id in sorted(grouped):
                event, group = grouped[event_id]
                try:
                    reading = compute_source_home_probability(
                        group, event.home_team_name, event.away_team_name,
                    )
                    if reading is None:
                        self.stats["no_reading"] += 1
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
                        continue

                    if not self._should_write(event_id, value, now):
                        self.stats["unchanged_skipped"] += 1
                        self._dispositions[event_id] = ("unchanged", value)
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
                    # same budget before its savepoint and row UPDATE.
                    await ensure_lock_budget()
                    async with self._event_stamp_scope(
                        session, single_event=len(grouped) == 1,
                    ):
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

                        # The chart point retains its own savepoint: a
                        # snapshot that cannot be written must
                        # not cost the stamp (see `_maybe_snapshot`), and the
                        # flush puts its ORM writes INSIDE this event's
                        # savepoint rather than autoflushing into the next
                        # event's UPDATE, where a failure would be charged to
                        # the wrong event.
                        # Most changed quotes arrive before the chart clock is
                        # due. Do not pay SAVEPOINT + RELEASE (or flush) merely
                        # to call a snapshot helper that immediately returns.
                        snapshot_at = self._last_snapshot_at.get(event_id)
                        snapshot_due = snapshot_at is None or (
                            now - snapshot_at >= self.snapshot_interval_s
                        )
                        try:
                            if snapshot_due:
                                async with session.begin_nested():
                                    await self._maybe_snapshot(
                                        session, event_id, value, reading, now,
                                    )
                                    await session.flush()
                        except Exception:
                            self.stats["errors"] += 1
                            logger.exception(
                                "live_blend_refresh[%s]: snapshot failed for event %s",
                                self.source, event_id,
                            )

                    # Noted only once the stamp scope has succeeded (a stamp
                    # that rolled back must not read as written), and applied only
                    # once the transaction commits — see `written` above.
                    written[event_id] = value
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
                    pending.append(
                        build_frame(
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
                    )
                except Exception as exc:
                    if lock_budget_failed:
                        raise
                    if is_lock_timeout(exc):
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
                            "re-queued for the next flush",
                            self.source,
                            event_id,
                            self.stamp_lock_timeout_ms,
                        )
                        continue
                    self.stats["errors"] += 1
                    # A committed stamp whose frame failed is still stamped.
                    self._dispositions.setdefault(event_id, ("error",))
                    logger.exception(
                        "live_blend_refresh[%s]: event %s failed",
                        self.source, event_id,
                    )

        # Session closed and committed — only now is the pushed number a number
        # the database actually kept, and only now is it "written".
        for event_id, value in written.items():
            self._last_write_at[event_id] = now
            self._last_written_value[event_id] = value
        self.stats["stamped"] += len(written)
        if exact_trace is not None:
            for event_id, (basis, revision, stamped_at) in trace_bases.items():
                with contextlib.suppress(Exception):
                    exact_trace.stamp(event_id, basis, revision, stamped_at)
        if on_committed is not None:
            on_committed(event_ids)
        await (self._publish if publish_committed is None else publish_committed)(pending)

    @contextlib.asynccontextmanager
    async def _snapshot_slots_follow_the_commit(self, event_ids: list[int]):
        """Undo this batch's chart-point throttle slots if it does not commit.

        `_maybe_snapshot` takes its slot BEFORE writing, deliberately: a
        snapshot that fails inside its own savepoint must not retry every two
        seconds. But a transaction that never commits wrote no chart point at
        all, and a slot kept for it would hold the line flat for up to
        `snapshot_interval_s` after the retry stamps the number. Entered before
        the session and exited after it, so a failing COMMIT reaches it.
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
        from app.utils.market_quote_push import publish_committed_market_changes

        try:
            sent = await publish_committed_market_changes(session, self._client())
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

    async def _publish(self, frames: list[dict]) -> None:
        """Fan the committed frames out to any SSE subscribers. Never raises.

        Bounded packed sends avoid one Redis round trip per event (#10659).
        Frame bytes and order stay unchanged; only committed inputs reach this
        method. A PUBLISH with no listeners is successful publication.

        Each command error is consumed and counted without costing siblings.
        An unanswered send may already have run: never automatically retry it.
        Timeout, cancellation or transport failure disconnects the borrowed
        socket before it returns to the consumer's shared pool.
        """
        if not frames:
            return
        sent = 0
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
                                commands.append(frame_publish_command(frame))
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
                            except ResponseError:
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
                if sent == 0:
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
        last = self._last_snapshot_at.get(event_id)
        if last is not None and (now - last) < self.snapshot_interval_s:
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
            )
            if is_new:
                session.add(snapshot)
                self.stats["snapshots_written"] += 1
            else:
                self.stats["snapshots_deduped"] += 1
        except Exception:
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


def hand_off_pending(refresher) -> int:
    """Leave `refresher`'s owed stamps for the next run of its source.

    Returns how many events were handed off. Never raises: a refresher that
    cannot say what it owes (a test double) hands off nothing.
    """
    try:
        pending = frozenset(refresher.pending_event_ids())
    except Exception:
        return 0
    if pending:
        _pending_handoff[refresher.source] = (_mono(), pending)
    else:
        _pending_handoff.pop(refresher.source, None)
    return len(pending)


def adopt_handed_off(refresher) -> int:
    """Give `refresher` the stamps the previous run of its source still owed.

    Returns how many events were adopted (0 when none, too old, or the
    refresher cannot adopt). The hand-off is consumed either way.
    """
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
