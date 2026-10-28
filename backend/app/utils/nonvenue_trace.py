"""#10090: optional log-only receipt for 1-4 events' sportsbook/ESPN/model publications.

Purpose. A held page's headline also moves when a NONVENUE source changes:
the betting consensus, ESPN, stat_model or mlb (`nonvenue_live_push`). The
venue traces (`pm_stage_trace`, `kalshi_exact_trace`) cannot see those writes,
and the #4971 publication journal is dark, records no commit or publish time,
and coalesces no-ops. This receipt follows each traced write from its UPDATE
RETURNING to its Redis publication, in the writing process's log, with no
database write:

  PUBLICATION    a committed write whose frame was handed to Redis: event, rev
                 (the row's ``win_probability_sources_rev`` from the same UPDATE,
                 the counter a PREVIEW's ``base_rev`` names), source, value, p,
                 status, the source entry's stamp (``stamped_at``: the DB's
                 ``clock_timestamp()`` inside the UPDATE), the producer's own
                 eligibility record (``evidence``) and the entry's observed
                 basis when present; ``returned_*`` (right after RETURNING),
                 ``commit_start_*`` (the outer ``before_commit``) and
                 ``commit_end_*`` (``after_commit``), ``publish_start_*`` /
                 ``publish_end_*`` around `publish_frame`, and its result:
                 SENT, NOT_SENT (publish_frame returned False), or the batch's
                 ERROR / TIMEOUT / CANCELLED (an aborted batch's frames that were
                 never handed over read ``NOT_ATTEMPTED_AFTER_<reason>``)
  WRITE_UNSENT   a traced write no reader will receive, with why: ROLLED_BACK
                 (its transaction or savepoint rolled back; ``commit_start_*``
                 present when a COMMIT was attempted), SUPERSEDED_IN_TRANSACTION
                 (a later write of the same event in the same transaction is the
                 frame that was kept: ``carried_by_source`` / ``carried_by_rev``),
                 SOURCE_REMOVED_NOT_SENT (a removal is a tombstone, never sent)
                 or STATUS_NOT_LIVE
  START / ARMED / STOP   as the venue traces'; STOP names how many traced writes
                 were still awaiting COMMIT/ROLLBACK (``awaiting_commit``) and
                 how many committed frames were not yet drained
                 (``awaiting_publication``)

Upstream clocks (a sportsbook's ``last_update``, ESPN's data time) are not
handed to this seam by any producer; lines say ``upstream_clock:
NOT_SUPPLIED_AT_SEAM`` rather than inventing one. ESPN/stat_model/mlb pass no
eligibility record: their gating happens before the write, so ``evidence`` is
null for them. `*_wall` is the dyno clock (`time.time`), `*_mono` the process's
monotonic clock; nothing here converts between them or to the DB clock.

Enable only with NONVENUE_TRACE_EVENTS (1-4 comma-separated event ids) and an
absolute epoch-second NONVENUE_TRACE_EXPIRES_AT no more than 600 s away.
NONVENUE_TRACE_MAX_LINES defaults to 128 (4..256, including STOP). Optional
NONVENUE_TRACE_ARM_AT (absolute, at most 1800 s away; EXPIRES_AT then at most
600 s after it) keeps collection off until that instant, so the window can sit
inside a warm worker instead of on the restart a config change causes; until
then nothing is kept or written but START. A malformed setting disables the
trace. Arm and expiry are fixed on the monotonic clock at build time.

Scope of the bounds. The configuration is read once per PROCESS, at the first
traced seam call. worker-realtime runs four prefork children, each with its own
budget and ``run`` id (START carries ``pid`` and ``dyno``), so a dyno writes at
most 4 x MAX_LINES, plus MAX_LINES for any child recycled inside the window.
Pending state is bounded (64 writes, 64 committed frames); overflow, expiry or
budget emits STOP and discards all state.

Disarmed (no NONVENUE_TRACE_EVENTS): `nonvenue_trace()` returns None after one
environment read per process, and every hook in `nonvenue_live_push` is a
``None`` check: the same SQL, the same Redis calls, the same frames, the same
log lines. Every method catches its own exceptions: evidence must never cost a
price, a commit or a publication. No payloads, SQL parameters or credentials
are recorded. Activation is owner-controlled (Root with the Integrator); this
code performs none.
"""

from __future__ import annotations

import json
import logging
import math
import os
import re
import time

logger = logging.getLogger(__name__)

MAX_PENDING = 64
MAX_EVENTS = 4
MAX_WINDOW_S = 600
MAX_ARM_WAIT_S = 1800
MAX_ITEMS = 16  # list/dict entries kept per evidence field; the rest are counted
UPSTREAM = "NOT_SUPPLIED_AT_SEAM"

_UNSET = object()
_TRACE = _UNSET


def nonvenue_trace():
    """This process's trace, built from the environment on first use, or None."""
    global _TRACE
    if _TRACE is _UNSET:
        try:
            _TRACE = NonvenueTrace.from_env(os.environ)
        except Exception:
            _TRACE = None
    return _TRACE


def reset_for_tests(trace=None):
    global _TRACE
    _TRACE = _UNSET if trace is None else trace


def _number(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return value if math.isfinite(value) else None


def _text(value):
    if isinstance(value, str) and re.fullmatch(r"[A-Za-z0-9_.:@#/+ -]{1,96}", value):
        return value
    return None if value is None else "UNPRINTABLE"


def _clean(value, depth=0):
    """Scalars, short printable strings and small containers only."""
    if value is None or isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return _number(value)
    if isinstance(value, str):
        return _text(value)
    if depth >= 3:
        return "NESTED"
    if isinstance(value, dict):
        keys = sorted(k for k in value if isinstance(k, str))[:MAX_ITEMS]
        out = {_text(k): _clean(value[k], depth + 1) for k in keys}
        if len(value) > len(keys):
            out["omitted"] = len(value) - len(keys)
        return out
    if isinstance(value, (list, tuple)):
        out = [_clean(v, depth + 1) for v in list(value)[:MAX_ITEMS]]
        if len(value) > MAX_ITEMS:
            out.append({"omitted": len(value) - MAX_ITEMS})
        return out
    return type(value).__name__


class NonvenueTrace:
    @classmethod
    def from_env(cls, env, *, wall=time.time, mono=time.monotonic, emit=None, run=None):
        try:
            raw = env.get("NONVENUE_TRACE_EVENTS", "")
            if not raw or len(raw) > 64:
                return None
            parts = [p.strip() for p in raw.split(",")]
            if not 1 <= len(parts) <= MAX_EVENTS or any(
                not re.fullmatch(r"\d{1,12}", p) for p in parts
            ):
                return None
            events = frozenset(int(p) for p in parts)
            expiry = float(env.get("NONVENUE_TRACE_EXPIRES_AT", "0"))
            limit = int(env.get("NONVENUE_TRACE_MAX_LINES", "128"))
            raw_arm = env.get("NONVENUE_TRACE_ARM_AT")
            now = wall()
            if raw_arm is None:
                arm_at = None
                window_ok = 0 < expiry - now <= MAX_WINDOW_S
            else:
                if len(raw_arm) > 32:
                    return None
                arm_at = float(raw_arm)
                window_ok = (
                    arm_at - now <= MAX_ARM_WAIT_S
                    and 0 < expiry - arm_at <= MAX_WINDOW_S
                    and expiry - now > 0
                )
            if not window_ok or not 4 <= limit <= 256:
                return None
            if run is None:
                import uuid

                run = uuid.uuid4().hex[:8]
            trace = cls(events, expiry, limit, run, wall, mono, emit)
            start = dict(
                events=sorted(events),
                expires_at=expiry,
                max_lines=limit,
                pid=os.getpid(),
                dyno=_text(env.get("DYNO")),
                upstream_clock=UPSTREAM,
            )
            if arm_at is not None:
                start.update(arm_at=arm_at, collection="WAITING_FOR_ARM")
                trace.arm_mono = trace.deadline - (expiry - arm_at)
            trace._send(dict(stage="START", **start))
            return trace
        except (ValueError, TypeError, OverflowError):
            return None

    def __init__(self, events, expiry, limit, run, wall, mono, emit):
        self.events, self.expiry, self.limit, self.run = events, expiry, limit, run
        self.wall, self.mono = wall, mono
        self.deadline = mono() + expiry - wall()
        self.emit = emit or (
            lambda record: logger.info("nonvenue-trace %s", json.dumps(record, sort_keys=True))
        )
        self.lines = 0
        self.stopped = False
        self.arm_mono = None
        self.write_seq = 0
        self.pending = {}  # id(frame) -> (frame, record): written, awaiting COMMIT/ROLLBACK
        self.ready = {}  # id(frame) -> (frame, record): committed, awaiting publication

    # ── bounds ────────────────────────────────────────────────────────────────

    def _send(self, record):
        self.lines += 1
        try:
            wall, mono = self.wall(), self.mono()
            envelope = dict(run=self.run, emitted_wall=wall, emitted_mono=mono)
            envelope.update(record)
            self.emit(envelope)
        except Exception:
            pass  # evidence must never cost a publication

    def _stop(self, reason):
        self.arm_mono = None
        if not self.stopped:
            self.stopped = True
            awaiting = (len(self.pending), len(self.ready))
            self.pending.clear()
            self.ready.clear()
            self._send(dict(stage="STOP", reason=reason, awaiting_commit=awaiting[0],
                            awaiting_publication=awaiting[1]))

    def active(self):
        if self.stopped:
            return False
        now = self.mono()
        if self.arm_mono is not None:
            if now < self.arm_mono:
                return False  # waiting: no state, no line
            arm_mono, self.arm_mono = self.arm_mono, None
            if now >= self.deadline or self.wall() >= self.expiry:
                self._stop("EXPIRED_BEFORE_ARMED")
                return False
            self._send(dict(stage="ARMED", events=sorted(self.events), arm_mono=arm_mono,
                            armed_mono=now, late_by_s=round(now - arm_mono, 6),
                            window_left_s=round(self.deadline - now, 6)))
        if self.wall() >= self.expiry or now >= self.deadline:
            self._stop("EXPIRED")
            return False
        if self.lines >= self.limit - 1:
            self._stop("BUDGET_STOP")
            return False
        return True

    def _record(self, stage, **fields):
        if self.active():
            self._send(dict(stage=stage, **fields))

    def _clock(self, name):
        return {f"{name}_wall": self.wall(), f"{name}_mono": self.mono()}

    # ── the write (`write_nonvenue_probability`) ─────────────────────────────

    def written(self, frame, *, value, removed, rev, stamped_at, entry, evidence,
                metadata_keys):
        """Right after the UPDATE RETURNING; the frame is queued, not committed."""
        try:
            event = frame.get("event_id")
            if event not in self.events or not self.active():
                return
            if len(self.pending) >= MAX_PENDING:
                self._stop("PENDING_OVERFLOW")
                return
            from app.utils.aggregation import OBSERVED_BASIS_KEY, OBSERVED_VALUE_KEY
            from app.utils.probability_eligibility import ELIGIBILITY_KEY

            self.write_seq += 1
            entry = entry if isinstance(entry, dict) else {}
            record = dict(
                write=self.write_seq,
                event=event,
                rev=_number(rev),
                source=_text(frame.get("source")),
                value=_number(value),
                removed=bool(removed),
                p=_number(frame.get("p")),
                status=_text(frame.get("status")),
                stamped_at=_text(stamped_at),
                stamped_clock="DB_CLOCK_TIMESTAMP_IN_UPDATE",
                upstream_clock=UPSTREAM,
                evidence=_clean(evidence),
                entry_eligibility=_clean(entry.get(ELIGIBILITY_KEY)),
                observed_basis=_clean(entry.get(OBSERVED_BASIS_KEY)),
                observed_value=_clean(entry.get(OBSERVED_VALUE_KEY)),
                metadata_keys=_clean(list(metadata_keys or ())),
                **self._clock("returned"),
            )
            self.pending[id(frame)] = (frame, record)
        except Exception:
            pass

    # ── the transaction (`before_commit` / `after_commit` / rollback) ────────

    def _traced(self, pending):
        return [(frame, self.pending[id(frame)][1]) for _, frame, *_ in pending
                if id(frame) in self.pending and self.pending[id(frame)][0] is frame]

    def commit_started(self, pending):
        """The outer ``before_commit``: COMMIT is about to be sent."""
        try:
            if not self.pending or not self.active():
                return
            clock = self._clock("commit_start")
            for _frame, record in self._traced(pending):
                record.update(clock)
        except Exception:
            pass

    def committed(self, pending, latest, sent):
        """The outer ``after_commit``. ``latest`` is the kept frame per event and
        ``sent`` whether `nonvenue_live_push` queues it for publication."""
        try:
            if not self.pending or not self.active():
                return
            clock = self._clock("commit_end")
            for frame, record in self._traced(pending):
                del self.pending[id(frame)]
                record.update(clock)
                kept = latest.get(frame["event_id"])
                if kept is not frame:
                    self._unsent(record, "SUPERSEDED_IN_TRANSACTION",
                                 carried_by_source=_text(kept.get("source")),
                                 carried_by_rev=_number(_rev(kept)))
                elif not sent(frame):
                    self._unsent(record, "SOURCE_REMOVED_NOT_SENT"
                                 if frame.get("source_value") is None else "STATUS_NOT_LIVE")
                elif len(self.ready) >= MAX_PENDING:
                    self._stop("PENDING_OVERFLOW")
                    return
                else:
                    self.ready[id(frame)] = (frame, record)
        except Exception:
            pass

    def rolled_back(self, entries):
        """`_after_rollback`'s discarded entries: never committed."""
        try:
            if not self.pending or not self.active():
                return
            for frame, record in self._traced(entries):
                del self.pending[id(frame)]
                self._unsent(record, "ROLLED_BACK", **self._clock("rollback"))
        except Exception:
            pass

    def _unsent(self, record, reason, **fields):
        self._record("WRITE_UNSENT", **record, reason=reason, **fields)

    # ── the publication (`publish_committed_nonvenue_frames`) ────────────────

    def publish_started(self, frame):
        """Returns a token for `published`, or None when the frame is not traced."""
        try:
            held = self.ready.get(id(frame))
            if held is None or held[0] is not frame or not self.active():
                return None
            held[1].update(self._clock("publish_start"))
            return frame
        except Exception:
            return None

    def published(self, token, sent):
        try:
            held = self.ready.pop(id(token), None)
            if held is None:
                return
            self._record("PUBLICATION", **held[1], **self._clock("publish_end"),
                         result="SENT" if sent else "NOT_SENT")
        except Exception:
            pass

    def publish_closed(self, frames, reason):
        """The batch ended without a result for these traced frames."""
        try:
            for frame in frames:
                held = self.ready.get(id(frame))
                if held is None or held[0] is not frame:
                    continue
                del self.ready[id(frame)]
                record = held[1]
                result = (reason if "publish_start_mono" in record
                          else f"NOT_ATTEMPTED_AFTER_{reason}")
                self._record("PUBLICATION", **record, **self._clock("publish_end"),
                             result=result)
        except Exception:
            pass


def _rev(frame):
    rev = frame.get("rev")
    if isinstance(rev, dict):
        return rev.get(str(frame.get("event_id")))
    return rev
