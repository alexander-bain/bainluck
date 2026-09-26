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
(`DEFAULT_SNAPSHOT_INTERVAL_S`, 25s) rather than the blend's 5s one, and it goes
through the same `_create_or_update_win_prob_snapshot` helper the 120s poll uses,
which appends a row only when the value actually CHANGES and otherwise just
bumps `reading_count`/`valid_until` on the existing point. Upper bound is
therefore ~4.8x the 120s poll on a continuously-moving market and 0x on a flat
one — not 60x. What it buys is Alex's stated bar: a live match page gains a
chart point within a minute instead of within two.

It shares the transaction with the blend stamp deliberately. The chart point and
the hero number are the same assertion about the same instant; committing them
together means they cannot disagree even if the dyno dies between two writes.

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

import contextlib
import logging
import math
import time
from dataclasses import dataclass
from typing import Iterable, Optional

logger = logging.getLogger(__name__)


#: Per-event floor between fast-lane recomputes. The WS flushes every 2s; an
#: event whose price ticks continuously does not need a JSONB write every tick
#: to feel live, and 5s keeps the write rate bounded on a busy slate.
DEFAULT_MIN_REFRESH_INTERVAL_S = 5.0

#: How long a cached inversion verdict stays good. One poll interval plus slack:
#: the 120s poll re-derives it authoritatively, so this never has to be the
#: durable answer, only a cheap one that cannot be stale for long.
DEFAULT_INVERSION_TTL_S = 150.0

#: When the recomputed value rounds to what is already stored, the write is
#: still worth making occasionally — `updated_at` is what drives the hero's
#: recency decay (#1829), so a source that goes quiet must still look ALIVE
#: rather than progressively losing weight. Just not every five seconds.
#:
#: #5661 — and only when the venue WAS re-read. "Quiet" and "dead" recompute
#: the same number from the same rows; see `restamp_records_no_observation`.
UNCHANGED_RESTAMP_INTERVAL_S = 45.0

#: Per-event floor between fast-lane CHART points. Deliberately slower than the
#: blend's 5s throttle: the number wants to be as live as the socket, the line
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

#: #837 receipt — the per-event floor between receipt lines for chains that
#: cannot qualify as a quiet tail (a busy market's routine deferrals, a held
#: price that rounded to the stored value). Those are summarised with a count.
#: A quiet stamp and every abnormal chain are never held back by it.
TAIL_RECEIPT_COALESCE_S = 60.0


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
        }

    # ── the socket's side ────────────────────────────────────────────────────

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
        return InputMark(
            seq=self._seq, event_id=event_id, outcome_id=outcome_id,
            probability=probability, kind=kind, recv_wall=_wall(),
            recv_mono=_mono(), venue_ts_ms=venue_ms, event_ordinal=ordinal,
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

    def take_staged(self) -> tuple[dict[int, InputMark], Optional[float]]:
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
        logger.info(
            "live_blend_refresh[%s]: tail-receipt summary run=%s reason=%s "
            "inputs=%d opened=%d logged=%d coalesced=%d open_at_close=%d",
            self.source, self.run, reason, self.stats["inputs"],
            self.stats["opened"], self.stats["logged"], self.stats["coalesced"],
            open_at_close,
        )

    def _close(self, event_id, result, now, *, disposition=(), error=None) -> None:
        chain = self._open.pop(event_id)
        later_inputs = self._inputs_by_event.get(event_id, 0) - chain.rev.event_ordinal
        quiet = later_inputs == 0 and chain.later_committed == 0
        value = previous = stamped_at = None
        if result == "stamped":
            _, value, stamped_at, previous = disposition
        elif result in ("unchanged", "unobserved"):
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
            "held_wall=%s stamp_rev_seq=%d stamped_at=%s value=%s previous=%s "
            "later_inputs=%d later_committed=%d last_input_seq=%s "
            "lock_retries=%d commit_failures=%d batch_failures=%d held_s=%.3f "
            "recv_to_close_s=%.3f coalesced=%d error=%s",
            self.source, self.run, event_id, result, quiet, moved, chain.origin,
            rev.seq, rev.outcome_id, rev.probability, rev.kind,
            _iso(rev.recv_wall), rev.venue_ts_ms, _iso(chain.stored_wall),
            _iso(chain.opened_wall), stamp_rev.seq, stamped_at, value, previous,
            later_inputs, chain.later_committed,
            self._last_seq_by_event.get(event_id), chain.lock_retries,
            chain.commit_failures, chain.batch_failures,
            now - chain.opened_mono, now - rev.recv_mono,
            self._coalesced.pop(event_id, 0), error,
        )


def atomic_stamp_expression(
    source: str, value: float, stamped_at=None, eligibility=None,
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
    """
    import json

    from sqlalchemy import Text, case, cast, func, literal
    from sqlalchemy.dialects.postgresql import JSONB

    from app.models.models import Event
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
    merged_entry = as_object(column[source]).concat(entry_expression)
    return as_object(column).concat(
        func.jsonb_build_object(cast(literal(source), Text), merged_entry)
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
        inversion_ttl_s: float = DEFAULT_INVERSION_TTL_S,
        unchanged_restamp_interval_s: float = UNCHANGED_RESTAMP_INTERVAL_S,
        snapshot_interval_s: float = DEFAULT_SNAPSHOT_INTERVAL_S,
        snapshot_max_gap_s: float = DEFAULT_SNAPSHOT_MAX_GAP_S,
        stamp_lock_timeout_ms: Optional[int] = DEFAULT_STAMP_LOCK_TIMEOUT_MS,
    ) -> None:
        self.source = source
        self.min_refresh_interval_s = min_refresh_interval_s
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
        self._last_refresh_at: dict[int, float] = {}
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
        last = self._last_refresh_at.get(event_id)
        return last is None or (now - last) >= self.min_refresh_interval_s

    # ── inversion orientation, cached ────────────────────────────────────────

    async def _oriented(
        self, session, event_id: int, home_prob: float, *, reading=None,
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

        corrected = await _check_and_fix_inversion(
            session, event_id, home_prob, self.source,
        )
        flipped = not math.isclose(corrected, home_prob, rel_tol=0.0, abs_tol=1e-9)
        self._inversion[event_id] = (now + self.inversion_ttl_s, flipped)
        return corrected

    # ── the refresh itself ───────────────────────────────────────────────────

    async def refresh(self, event_ids: Iterable[int]) -> dict[str, int]:
        """Recompute and stamp the blend for these events. Never raises."""
        now = _mono()
        receipts = self.receipts
        staged, stored_wall = (
            self._receipt_call(receipts.take_staged) if receipts is not None else None
        ) or ({}, None)
        retry = set(self._lock_retry)
        deferred = set(self._throttle_deferred)
        fresh = set(event_ids)
        wanted = fresh | retry | deferred
        due = [eid for eid in wanted if self._due(eid, now)]
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
        try:
            await self._refresh_batch(due, now)
        except Exception as exc:
            self.stats["errors"] += 1
            logger.exception(
                "live_blend_refresh[%s]: batch failed for %d events",
                self.source, len(due),
            )
            # The outcome prices already committed before this refresh. Keep
            # every owed stamp if its transaction fails, even when no further
            # venue input arrives. Ordinary retries retain the attempt's 5s
            # throttle; only existing row-lock retries remain due at once.
            self._throttle_deferred.update(set(due).difference(self._lock_retry))
            for event_id in retry.intersection(due):
                self._lock_retry.add(event_id)
                self._last_refresh_at.pop(event_id, None)
                self._throttle_deferred.discard(event_id)
            if receipts is not None:
                self._receipt_call(
                    receipts.resolve_failed, due, self._dispositions, staged,
                    stored_wall, self._lock_retry | self._throttle_deferred,
                    exc, _mono(),
                )
        else:
            if receipts is not None:
                self._receipt_call(
                    receipts.resolve, due, self._dispositions, staged,
                    stored_wall, _mono(),
                )
        return self.stats

    def _receipt_call(self, fn, *args):
        """Receipts are evidence about the price path, never part of it."""
        try:
            return fn(*args)
        except Exception:
            logger.warning(
                "live_blend_refresh[%s]: tail receipt failed", self.source,
                exc_info=True,
            )
            return None

    async def refresh_pending(self) -> dict[str, int]:
        """#837 tail — stamp only the deferred events. Never raises.

        For the socket's flush when it has no new prices to write: `refresh`
        is otherwise only reached after a price write, and a deferred event on a
        quiet market would wait for a tick that may not come. Deferred means a
        row lock gave up OR the throttle held a written price. Returns at once,
        without opening a session, when nothing is queued or nothing queued is
        due yet.
        """
        if not self._lock_retry and not self._throttle_deferred:
            return self.stats
        return await self.refresh(())

    async def _refresh_batch(self, event_ids: list[int], now: float) -> None:
        from types import SimpleNamespace

        from sqlalchemy import select, update

        from app.models.models import Event, FuturesMarket, FuturesOutcome
        from app.tasks.base import get_task_session
        from app.utils.aggregation import (
            compute_aggregate_probability,
            oldest_observation_time,
        )
        from app.utils.live_blend import (
            MarketOutcomes, compute_source_home_probability,
        )
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
        # "due", and `get_task_session()` builds a fresh engine and connection
        # pool per call — so that event would open a Postgres connection every
        # 2-second flush, forever, to discover the same nothing.
        for event_id in event_ids:
            self._last_refresh_at[event_id] = now

        async with (
            self._snapshot_slots_follow_the_commit(event_ids),
            get_task_session() as session,
        ):
            market_rows = (
                await session.execute(
                    select(FuturesMarket, Event)
                    .join(Event, FuturesMarket.event_id == Event.id)
                    .where(
                        FuturesMarket.source == self.source,
                        FuturesMarket.event_id.in_(event_ids),
                    )
                )
            ).all()
            if not market_rows:
                return

            market_ids = [m.id for m, _ in market_rows]
            outcomes_by_market: dict[int, list] = {}
            for outcome in (
                await session.execute(
                    select(FuturesOutcome).where(
                        FuturesOutcome.market_id.in_(market_ids)
                    )
                )
            ).scalars():
                outcomes_by_market.setdefault(outcome.market_id, []).append(outcome)

            grouped: dict[int, tuple] = {}
            for market, event in market_rows:
                entry = grouped.setdefault(event.id, (event, []))
                entry[1].append(
                    MarketOutcomes(
                        market=market,
                        outcomes=outcomes_by_market.get(market.id, []),
                        # #5820. The 15-minute matcher retires a leg whose only
                        # speaker is a settled market on a game with no result;
                        # this lane recomputes the same number every two
                        # seconds from the same rows, so without the same input
                        # it would re-publish what the matcher just cleared and
                        # the two writers would disagree — the one thing this
                        # module exists to prevent. The Event row is already
                        # joined here, so it costs no query.
                        event_has_result=event.completed_at is not None,
                    )
                )

            # #837 — ONE LOCK ORDER, ONE SAVEPOINT PER EVENT. This batch stamps
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
            if self.stamp_lock_timeout_ms:
                await session.execute(
                    SET_LOCK_TIMEOUT_SQL,
                    {"ms": lock_timeout_value(self.stamp_lock_timeout_ms)},
                )
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
                    )
                    value = round(home_prob, 4)

                    # #5661 — before the throttle decides WHEN to re-stamp, ask
                    # WHETHER there is anything to re-stamp. The row's own
                    # stored entry is the reference (not this process's memory,
                    # which a dyno restart empties), and the reading's rows are
                    # the ones the number came from, as the 120s poll dates it.
                    if restamp_records_no_observation(
                        value,
                        oldest_observation_time(
                            getattr(reading, "contributing_outcomes", None)
                            or (getattr(reading, "outcome", None),)
                        ),
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
                    async with session.begin_nested():
                        new_sources = (
                            await session.execute(
                                update(Event)
                                .where(Event.id == event_id)
                                .values(
                                    win_probability_sources=atomic_stamp_expression(
                                        self.source,
                                        value,
                                        eligibility=reading.eligibility,
                                    )
                                )
                                .returning(Event.win_probability_sources)
                            )
                        ).scalar_one_or_none()
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

                        # The chart point rides a savepoint of its own inside
                        # the stamp's: a snapshot that cannot be written must
                        # not cost the stamp (see `_maybe_snapshot`), and the
                        # flush puts its ORM writes INSIDE this event's
                        # savepoint rather than autoflushing into the next
                        # event's UPDATE, where a failure would be charged to
                        # the wrong event.
                        try:
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

                    # Noted only once the savepoint has released (a stamp that
                    # rolled back must not read as written), and applied only
                    # once the transaction commits — see `written` above.
                    written[event_id] = value
                    # #837 receipt — trusted only once the batch returns, i.e.
                    # after the commit; `previous` says whether it MOVED.
                    self._dispositions[event_id] = (
                        "stamped", value, stamped_at,
                        self._last_written_value.get(event_id),
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
                        )
                    )
                except Exception as exc:
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
                            self.source, event_id, self.stamp_lock_timeout_ms,
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
        await self._publish(pending)

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

    async def _publish(self, frames: list[dict]) -> None:
        """Fan the committed frames out to any SSE subscribers. Never raises.

        Wrapped whole as well as per-frame: `publish_frame` already swallows a
        failed PUBLISH, but building the client can fail too (no `REDIS_URL`, a
        refused TLS handshake), and this runs on the dyno whose actual job is
        streaming prices. Nothing here may interrupt that (gotcha #42).
        """
        if not frames:
            return
        try:
            from app.utils.live_push import publish_frame

            if self._redis is None:
                from app.tasks.redis_state import get_async_redis_client

                self._redis = get_async_redis_client()
            sent = 0
            for frame in frames:
                if await publish_frame(self._redis, frame):
                    sent += 1
                    self.stats["published"] += 1
                else:
                    self.stats["publish_errors"] += 1
            if sent == 0:
                # `publish_frame` swallows its own failure and returns False, so
                # the `except` below never sees a dead connection — without this
                # the poisoned client would be reused for the life of the
                # consumer, publishing nothing and only ticking a counter.
                # A batch where NOTHING went out is enough to suspect the
                # client; rebuild it next time rather than retry it forever.
                self._redis = None
        except Exception:
            self.stats["publish_errors"] += len(frames)
            # Drop the client so the next batch rebuilds it rather than
            # reusing a connection that has already proven bad.
            self._redis = None
            logger.warning(
                "live_blend_refresh[%s]: publish batch failed for %d frames",
                self.source, len(frames), exc_info=True,
            )

    async def _maybe_snapshot(
        self, session, event_id: int, value: float, reading, now: float,
    ) -> None:
        """Append this reading to the chart series, on the snapshot clock.

        Called only after a blend stamp actually happened, which on a FLAT
        market is the `unchanged_restamp_interval_s` beat (45s) rather than the
        5s blend beat. `_create_or_update_win_prob_snapshot` is the same helper
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
