"""#10090: optional log-only receipt for 1-4 events' sportsbook/ESPN/model publications.

Purpose. A held page's headline also moves when a NONVENUE source changes:
the betting consensus, ESPN, stat_model or mlb (`nonvenue_live_push`). The
venue traces (`pm_stage_trace`, `kalshi_exact_trace`) cannot see those writes,
and the #4971 publication journal is dark, records no commit or publish time,
and coalesces no-ops. This receipt follows each traced write (an OBSERVATION)
from the seam to its Redis publication, in the writing process's log, with no
database write and no Redis call. Every observation is kept, no-ops included.

Each observation line carries:
  identity      ``txn`` (this process's id for the OUTER transaction), ``obs``
                (observation ordinal, ordered), event, source, ``rev`` (the
                row's ``win_probability_sources_rev`` from the same UPDATE: the
                counter a PREVIEW's ``base_rev`` and a reader's committed vector
                name)
  the decision  value, ``removed``, ``changed_sources`` / ``removed_sources``,
                ``metadata_keys``, the producer's own eligibility record
                (``evidence``; betting's books/median/split/floor; null for
                ESPN/stat_model/mlb, which gate before writing), the prior entry
                as this session's ORM view held it (``prior_value``,
                ``prior_updated_at``, ``prior_clock: ORM_VIEW_MAY_BE_STALE``),
                ``value_unchanged`` (a no-op by that view) and
                ``prior_txn_row_write`` (#4971's probe: null unless recording)
  the bag       the complete returned bag: per probability source its value,
                stamp, weight (``effective_source_weights``), refusal and
                observed basis; ``bag_other_keys`` (non-probability keys);
                ``bag_hash`` over the whole returned bag; status, ESPN and
                opening fallback inputs; ``tier`` and ``recomputed_p`` from
                `compute_aggregate_probability_tiered`; ``p`` (the frame's) and
                ``p_matches``
  clocks        ``seam_*`` (entering `write_nonvenue_probability`, before its
                awaited probe and UPDATE: the producer's own decision precedes
                it), ``returned_*`` (after RETURNING), ``commit_start_*`` /
                ``commit_end_*`` (the OUTER ``before_commit`` / ``after_commit``),
                ``publish_start_*`` / ``publish_end_*`` around `publish_frame`;
                ``stamped_at`` is the DB's ``clock_timestamp()`` inside the UPDATE
  outcome       ``commit_result`` (COMMITTED, ROLLED_BACK, SAVEPOINT_ROLLED_BACK,
                COMMIT_FAILED_ROLLED_BACK) and, for the frame, ``frame_hash`` at
                commit and ``frame_unchanged`` at publish

Lines:
  PUBLICATION    a committed observation whose frame reached `publish_frame`;
                 ``result`` SENT, NOT_SENT (publish_frame returned False), or the
                 batch's TIMEOUT / ERROR / CANCELLED; a frame an aborted batch
                 never handed over reads ``NOT_ATTEMPTED_AFTER_<reason>``
  WRITE_UNSENT   an observation no reader receives: ROLLED_BACK (``commit_result``
                 says which), SUPERSEDED_IN_TRANSACTION (a later observation of
                 the same event in the same transaction is the kept frame:
                 ``carried_by_obs`` / ``carried_by_rev``), SOURCE_REMOVED_NOT_SENT
                 or STATUS_NOT_LIVE
  START / ARMED / STOP   START: schema, events, expiry, budgets, ``pid``,
                 ``dyno``, ``release``/``slug_commit`` when the dyno exposes
                 them. STOP: reason and counters (``observations``,
                 ``published``, ``unsent``, ``awaiting_commit``,
                 ``awaiting_publication``, ``bytes``)

Every line carries ``line`` (its ordinal in this run, from 1), so a missing or
truncated line is detectable rather than a quiet source.

Upstream clocks (a sportsbook's ``last_update``, ESPN's data time) are not
handed to this seam by any producer; lines say ``upstream_clock:
NOT_SUPPLIED_AT_SEAM`` rather than inventing one. `*_wall` is the dyno clock
(`time.time`), `*_mono` the process's monotonic clock; nothing here converts
between them or to the DB clock.

Enable only with NONVENUE_TRACE_EVENTS (1-4 comma-separated event ids) and an
absolute epoch-second NONVENUE_TRACE_EXPIRES_AT no more than 600 s away.
NONVENUE_TRACE_MAX_LINES defaults to 128 (4..256, including STOP); the emitted
JSON is also capped at MAX_BYTES. Optional NONVENUE_TRACE_ARM_AT (absolute, at
most 1800 s away; EXPIRES_AT then at most 600 s after it) keeps collection off
until that instant, so the window can sit inside a warm worker instead of on the
restart a config change causes; until then nothing is kept or written but
START. A malformed setting disables the trace. Arm and expiry are fixed on the
monotonic clock at build time.

Scope of the bounds. The configuration is read once per PROCESS, at the first
seam call. worker-realtime runs four prefork children, each with its own budget
and ``run`` id (START carries ``pid`` and ``dyno``), so a dyno writes at most
4 x MAX_LINES, plus MAX_LINES for any child recycled inside the window.
Pending state is bounded (64 observations, 64 committed frames, 64 open
transactions); overflow, expiry or a budget emits STOP and discards all state.

Disarmed (no NONVENUE_TRACE_EVENTS): `nonvenue_trace()` returns None after one
environment read per process, and every hook in `nonvenue_live_push` is a
``None`` check: the same SQL, the same Redis calls, the same frames, the same
log lines. Every method catches its own exceptions: evidence must never cost a
price, a commit or a publication. No payloads beyond the probability bag,
SQL parameters or credentials are recorded. Activation is owner-controlled
(Root with the Integrator); this code performs none.
"""

from __future__ import annotations

import hashlib
import json
import logging
import math
import os
import re
import time
from types import SimpleNamespace

logger = logging.getLogger(__name__)

SCHEMA = "nonvenue-trace/1"
MAX_PENDING = 64
MAX_EVENTS = 4
MAX_WINDOW_S = 600
MAX_ARM_WAIT_S = 1800
MAX_ITEMS = 16  # list/dict entries kept per field; the rest are counted
MAX_BYTES = 262_144  # emitted JSON per process run, including STOP
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


def _hash(value):
    try:
        return hashlib.sha1(
            json.dumps(value, sort_keys=True, default=str).encode()).hexdigest()[:16]
    except Exception:
        return "UNAVAILABLE"


def _entry_value(entry):
    from app.utils.aggregation import parse_source_entry

    value, updated = parse_source_entry(entry)
    return value, (updated.isoformat() if updated is not None else None)


class BoundedLogTrace:
    """Env-armed, log-only, bounded: the shared START/ARMED/STOP machinery.

    ``PREFIX`` names the settings (``<PREFIX>_EVENTS``, ``_EXPIRES_AT``,
    ``_MAX_LINES``, ``_ARM_AT``); ``LOG`` is the log line's prefix. A subclass
    reports its own counters and discards its own state at STOP.
    """

    PREFIX = "NONVENUE_TRACE"
    LOG = "nonvenue-trace"

    @classmethod
    def from_env(cls, env, *, wall=time.time, mono=time.monotonic, emit=None, run=None):
        try:
            raw = env.get(f"{cls.PREFIX}_EVENTS", "")
            if not raw or len(raw) > 64:
                return None
            parts = [p.strip() for p in raw.split(",")]
            if not 1 <= len(parts) <= MAX_EVENTS or any(
                not re.fullmatch(r"\d{1,12}", p) for p in parts
            ):
                return None
            events = frozenset(int(p) for p in parts)
            expiry = float(env.get(f"{cls.PREFIX}_EXPIRES_AT", "0"))
            limit = int(env.get(f"{cls.PREFIX}_MAX_LINES", "128"))
            raw_arm = env.get(f"{cls.PREFIX}_ARM_AT")
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
                schema=cls.SCHEMA,
                events=sorted(events),
                expires_at=expiry,
                max_lines=limit,
                max_bytes=MAX_BYTES,
                pid=os.getpid(),
                dyno=_text(env.get("DYNO")),
                release=_text(env.get("HEROKU_RELEASE_VERSION")),
                slug_commit=_text(env.get("HEROKU_SLUG_COMMIT")),
                **cls.START_FIELDS,
            )
            if arm_at is not None:
                start.update(arm_at=arm_at, collection="WAITING_FOR_ARM")
                trace.arm_mono = trace.deadline - (expiry - arm_at)
            trace._send(dict(stage="START", **start))
            return trace
        except (ValueError, TypeError, OverflowError):
            return None

    SCHEMA = SCHEMA
    START_FIELDS: dict = {}

    def __init__(self, events, expiry, limit, run, wall, mono, emit):
        self.events, self.expiry, self.limit, self.run = events, expiry, limit, run
        self.wall, self.mono = wall, mono
        self.deadline = mono() + expiry - wall()
        log = self.LOG
        self.emit = emit or (lambda record: logger.info("%s %s", log, record))
        self.lines = 0
        self.bytes = 0
        self.stopped = False
        self.arm_mono = None

    def _counters(self):
        return {}

    def _discard(self):
        pass

    def _send(self, record):
        self.lines += 1
        try:
            wall, mono = self.wall(), self.mono()
            envelope = dict(run=self.run, line=self.lines, emitted_wall=wall,
                            emitted_mono=mono)
            envelope.update(record)
            text = json.dumps(envelope, sort_keys=True, default=str)
            self.bytes += len(text)
            self.emit(text)
        except Exception:
            pass  # evidence must never cost a publication

    def _stop(self, reason):
        self.arm_mono = None
        if not self.stopped:
            self.stopped = True
            counters = self._counters()
            self._discard()
            self._send(dict(stage="STOP", reason=reason, **counters, bytes=self.bytes))

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
        if self.bytes >= MAX_BYTES - 4096:  # room for STOP
            self._stop("BYTE_BUDGET_STOP")
            return False
        return True

    def _record(self, stage, **fields):
        if self.active():
            self._send(dict(stage=stage, **fields))

    def _clock(self, name):
        return {f"{name}_wall": self.wall(), f"{name}_mono": self.mono()}


class NonvenueTrace(BoundedLogTrace):
    START_FIELDS = {"upstream_clock": UPSTREAM}

    def __init__(self, events, expiry, limit, run, wall, mono, emit):
        super().__init__(events, expiry, limit, run, wall, mono, emit)
        self.obs_seq = self.txn_seq = 0
        self.n_published = self.n_unsent = 0
        self.txns = {}  # id(outer transaction) -> (transaction, txn id)
        self.pending = {}  # id(frame) -> (frame, record): awaiting COMMIT/ROLLBACK
        self.ready = {}  # id(frame) -> (frame, record): committed, awaiting publication

    def _counters(self):
        return dict(observations=self.obs_seq, published=self.n_published,
                    unsent=self.n_unsent, awaiting_commit=len(self.pending),
                    awaiting_publication=len(self.ready))

    def _discard(self):
        self.pending.clear()
        self.ready.clear()
        self.txns.clear()

    # ── the seam (`write_nonvenue_probability`) ──────────────────────────────

    def seam_entered(self, event_id):
        """At the seam, before the awaited probe and UPDATE; a token or None."""
        try:
            if event_id in self.events and self.active():
                return self._clock("seam")
        except Exception:
            pass
        return None

    def written(self, token, frame, *, transaction, value, removed, rev, stamped_at, sources,
                status, espn, opening, evidence, metadata_keys, prior, prior_txn_row_write):
        """Right after RETURNING; the frame is queued, not committed."""
        try:
            if token is None or not self.active():
                return
            event = frame.get("event_id")
            if event not in self.events:
                return
            if len(self.pending) >= MAX_PENDING:
                self._stop("PENDING_OVERFLOW")
                return
            txn = self._txn(transaction)
            if txn is None:
                return
            self.obs_seq += 1
            source = frame.get("source")
            prior_value, prior_updated = _entry_value((prior or {}).get(source)
                                                      if isinstance(prior, dict) else None)
            record = dict(
                txn=txn,
                obs=self.obs_seq,
                event=event,
                source=_text(source),
                rev=_number(rev),
                value=_number(value),
                removed=bool(removed),
                changed_sources=[] if removed else [_text(source)],
                removed_sources=[_text(source)] if removed else [],
                metadata_keys=_clean(list(metadata_keys or ())),
                evidence=_clean(evidence),
                prior_value=_number(prior_value),
                prior_updated_at=_text(prior_updated),
                prior_clock="ORM_VIEW_MAY_BE_STALE",
                value_unchanged=(prior_value == value) if prior is not None else None,
                prior_txn_row_write=prior_txn_row_write,
                stamped_at=_text(stamped_at),
                stamped_clock="DB_CLOCK_TIMESTAMP_IN_UPDATE",
                upstream_clock=UPSTREAM,
                p=_number(frame.get("p")),
                **bag_fields(sources, status, espn, opening, frame.get("p")),
                **token,
                **self._clock("returned"),
            )
            self.pending[id(frame)] = (frame, record)
        except Exception:
            pass

    def _txn(self, transaction):
        if transaction is None:
            return None
        held = self.txns.get(id(transaction))
        if held is not None and held[0] is transaction:
            return held[1]
        self._forget_txn()
        if len(self.txns) >= MAX_PENDING:
            self._stop("PENDING_OVERFLOW")
            return None
        self.txn_seq += 1
        self.txns[id(transaction)] = (transaction, self.txn_seq)
        return self.txn_seq

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
            self._forget_txn()
            if not self.pending or not self.active():
                return
            clock = self._clock("commit_end")
            for frame, record in self._traced(pending):
                del self.pending[id(frame)]
                record.update(clock, commit_result="COMMITTED")
                kept = latest.get(frame["event_id"])
                if kept is not frame:
                    carried = self._find(kept)
                    self._unsent(record, "SUPERSEDED_IN_TRANSACTION",
                                 carried_by_obs=None if carried is None else carried["obs"],
                                 carried_by_rev=_number(_rev(kept)))
                elif not sent(frame):
                    self._unsent(record, "SOURCE_REMOVED_NOT_SENT"
                                 if frame.get("source_value") is None else "STATUS_NOT_LIVE")
                elif len(self.ready) >= MAX_PENDING:
                    self._stop("PENDING_OVERFLOW")
                    return
                else:
                    record["frame_hash"] = _hash(frame)
                    self.ready[id(frame)] = (frame, record)
        except Exception:
            pass

    def _find(self, frame):
        held = self.pending.get(id(frame))
        return held[1] if held is not None and held[0] is frame else None

    def rolled_back(self, transaction, entries):
        """`_after_rollback`'s discarded entries: never committed."""
        try:
            self._forget_txn()
            if not self.pending or not self.active():
                return
            nested = bool(getattr(transaction, "nested", False))
            for frame, record in self._traced(entries):
                del self.pending[id(frame)]
                result = ("SAVEPOINT_ROLLED_BACK" if nested
                          else "COMMIT_FAILED_ROLLED_BACK" if "commit_start_mono" in record
                          else "ROLLED_BACK")
                self._unsent(record, "ROLLED_BACK", commit_result=result,
                             **self._clock("rollback"))
        except Exception:
            pass

    def _forget_txn(self):
        """Drop ended outer transactions (a COMMIT or ROLLBACK closed them)."""
        for key, (transaction, _txn) in list(self.txns.items()):
            if not getattr(transaction, "is_active", False):
                del self.txns[key]

    def _unsent(self, record, reason, **fields):
        self.n_unsent += 1
        self._record("WRITE_UNSENT", **record, reason=reason, **fields)

    # ── the publication (`publish_committed_nonvenue_frames`) ────────────────

    def publish_started(self, frame):
        """Returns a token for `published`, or None when the frame is not traced."""
        try:
            held = self.ready.get(id(frame))
            if held is None or held[0] is not frame or not self.active():
                return None
            held[1].update(self._clock("publish_start"),
                           frame_unchanged=_hash(frame) == held[1].get("frame_hash"))
            return frame
        except Exception:
            return None

    def published(self, token, sent):
        try:
            held = self.ready.pop(id(token), None)
            if held is None:
                return
            self.n_published += 1
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
                self.n_published += 1
                self._record("PUBLICATION", **record, **self._clock("publish_end"),
                             result=result)
        except Exception:
            pass


def bag_fields(sources, status, espn, opening, frame_p=None, *, recompute=True):
    """The complete bag; ``recompute`` adds the row aggregate's weights, tier
    and probability (`compute_aggregate_probability_tiered`)."""
    from app.utils.aggregation import (
        OBSERVED_BASIS_KEY,
        SOURCE_WEIGHTS,
        compute_aggregate_probability_tiered,
        effective_source_weights,
    )
    from app.utils.probability_eligibility import is_refused

    bag = sources if isinstance(sources, dict) else {}
    shim = SimpleNamespace(win_probability_sources=bag, status=status,
                           espn_win_prob_home=espn, opening_home_probability=opening)
    fields = dict(bag_hash=_hash(bag), status=_text(status),
                  espn_win_prob_home=_number(_float(espn)),
                  opening_home_probability=_number(_float(opening)))
    keys, weights = [], []
    try:
        if recompute:
            probability, tier = compute_aggregate_probability_tiered(shim, status)
            keys, _values, weights = effective_source_weights(shim, status)
            fields.update(tier=_text(tier), recomputed_p=_number(_float(probability)),
                          p_matches=(probability is not None and frame_p is not None
                                     and float(probability) == frame_p))
    except Exception:
        fields["tier"] = "RECOMPUTE_ERROR"
    weight_of = dict(zip(keys, weights))
    rows, other = [], []
    for name in sorted(k for k in bag if isinstance(k, str)):
        entry = bag[name]
        # The hero reads only SOURCE_WEIGHTS keys; anything else (a book
        # count, an injuries list) is named, never shown as a reading.
        if name not in SOURCE_WEIGHTS:
            other.append(name)
            continue
        value, updated = _entry_value(entry)
        row = dict(source=name, value=_number(value), updated_at=_text(updated),
                   refused=bool(is_refused(entry)))
        if recompute:
            row["weight"] = (_number(weight_of.get(name)) if name in weight_of
                             else "NOT_WEIGHTED")
        basis = entry.get(OBSERVED_BASIS_KEY) if isinstance(entry, dict) else None
        if isinstance(basis, dict):
            row["observed_basis"] = _clean(basis)
        rows.append(row)
    fields.update(bag=rows[:MAX_ITEMS], bag_omitted=max(0, len(rows) - MAX_ITEMS),
                  bag_other_keys=_clean(other))
    return fields


def _float(value):
    try:
        return None if value is None else float(value)
    except (TypeError, ValueError):
        return None


def _rev(frame):
    rev = frame.get("rev") if isinstance(frame, dict) else None
    if isinstance(rev, dict):
        return rev.get(str(frame.get("event_id")))
    return rev
