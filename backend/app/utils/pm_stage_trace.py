"""#10090: optional stage trace for 1-4 live events' selected Polymarket outcomes.

Purpose. The per-minute delivery receipt carries an event's newest and oldest
input marks and its stamp. Those marks are AGGREGATE: they can belong to a
sibling outcome or a repeat, so they cannot time the exact selected input's
write, fence or stamp. This trace follows the exact selected input (same
`input_seq`, outcome, value, kind and venue timestamp) through each stage:

  ACCEPTED         handler callback under the buffer lock (NOT wire ingress)
  CHUNK            the flush that took it: flush start, snapshot, chunk index and
                   size, path (no owner / joined a running stamp / fence check),
                   session open, statement start/end, commit, end, result
  FENCED           the fence decision, with the held attempt's identity
  PRICE_COMMITTED  the committed row for that exact mark (`stored_epoch` is the
                   row's `last_updated`, the transaction's `now()`, NOT commit)
  PRICE_NOT_COMMITTED  a refused/failed write, or no row returned (unchanged)
  ADMISSION        the refresher's admit/defer decision and its reason
  EVENT_COMMITTED  the stamp whose observation basis holds that exact mark
  EVENT_PUBLICATION  the Redis result for that revision (not browser delivery)
  PREVIEW          a provisional frame this process SENT for the event: its
                   (epoch, seq), reply, base_rev and whole composed bag, with
                   each basis key joined to this trace's exact input_seq
                   (`ExactKalshiTrace.preview`). Changed-only: a re-commit of
                   an unchanged value opens no chain, so its observation reads
                   TRACKED_OUTCOME_NO_RETAINED_COMMIT_AT_THIS_OBSERVATION
  SELECTED         the refresher's selection decision for the event, written at
                   it (`ExactKalshiTrace.selection`); its PREVIEW, READSET or
                   SELECTION_UNSENT repeats ``sel``. A changed blend over an
                   unchanged traced input is a new selected state and is written
  ATTEMPT          one stamp attempt: start, session, commit, disposition,
                   revision and the actual `window.release`

All `*_mono` fields are the worker's monotonic clock (`time.monotonic`, the
same clock as `InputMark.recv_mono` and the flush's `flush_started`). `*_wall`
is the dyno clock. `event_updated_at` is the database clock. Nothing here
converts between them.

Enable only with WS_PM_TRACE_EVENT (one event id), 1-4 explicit
WS_PM_TRACE_OUTCOMES of that event, and an absolute epoch-second
WS_PM_TRACE_EXPIRES_AT no more than 600 s away. WS_PM_TRACE_MAX_LINES defaults to
128 (hard cap 256, including STOP). The line, expiry and pending-state bounds are
`ExactKalshiTrace`'s. An outcome not mapped to the event at START is dropped and
named. No mapped outcome, pending overflow, expiry or budget emits STOP and
discards all state. No payloads, SQL parameters or credentials are recorded.

A fold's members (#10090 R1). A display fold of two-rows-for-one-game members
can take its PM origin from either member, so WS_PM_TRACE_EVENT may list 1-4
comma-separated event ids, with 1-8 outcomes mapped to any of them. One setting,
one window, one shared WS_PM_TRACE_MAX_LINES budget: the cap bounds the
worker's log volume, which more events do not make cheaper. Each event keeps its
own attempt, open chains and admission lines, and every per-event line names
its event. START/ARMED carry ``events`` (sorted) and ``outcome_event`` instead
of ``event`` (plus ``events_without_outcome``); a CHUNK whose selected outcomes span two of them reads
``event: "MULTIPLE"`` with ``events``, and a chunk fenced on two reads
``fenced_by`` as ``{event: attempt}``. With ONE event id every line is exactly
the single-event line, and the 4-outcome cap is unchanged.

Warm arming (optional). WS_PM_TRACE_ARM_AT, an absolute epoch second at most
1800 s away, delays collection so the window can sit inside a warm worker rather
than on its restart. EXPIRES_AT must then be after ARM_AT and at most 600 s after
it. START still says the configuration was accepted (`collection` reads
WAITING_FOR_ARM) and is the only line before arming: until then every entry point
returns before touching any state, so nothing observed before arming is kept or
emitted. ARMED is the actual start: written by the first entry point at or after
the arm instant, with how late that was, the window left, and the mapping re-read
then (the run's outcome map can grow). Arm and expiry are both fixed on the
monotonic clock when the trace is built, so a wall-clock change cannot lengthen
the window. A run that begins inside the window arms at its first entry point. A
present but malformed ARM_AT disables the trace. Absent, nothing here changes.

Volume. Only a CHANGED selected value opens a chain. Repeats keep their
identity without spending lines. Flush, admission and attempt lines are written
only while a chain is open, or for an attempt that fenced one.

Identity. `input_seq` is the exact mark whose value the row committed. When a
flush wrote a later repeat of a change, `carries_changed_seq` names that change
(same value, checked). Older changed seqs of the outcome are split:
`superseded_unwritten` were replaced in the buffer before any write took them,
and `committed_unstamped` were written but replaced before a stamp joined them.
Neither list is evidence those values were ever stamped. The written marks'
identities are held on the chunk itself, so a repeat burst during the awaited
write cannot age them out. A written mark with no retained identity reports
`PRICE_COMMITTED_IDENTITY_UNAVAILABLE`, never silence.

Every entry point catches its own exceptions and returns None. A trace or logger
failure must never cost a price, an exception, a cancellation, ordering or a
lifetime. The callers change no prices, scheduling, eligibility or retries.

Activation and removal are owner-controlled (Root with the Integrator). A
Heroku config change restarts the dyno, so it must not overlap a deployment.
This code performs no activation.
"""

import functools
import json
import logging
import re
import time

from app.utils.kalshi_exact_trace import MAX_PENDING, ExactKalshiTrace

logger = logging.getLogger(__name__)
ACCEPT_CLOCK = "HANDLER_CALLBACK_UNDER_BUFFER_LOCK_NOT_WIRE_INGRESS"
MAX_COVERS = 8
MAX_EVENTS = 4  # a fold's members
MAX_ARM_WAIT_S = 1800
MAX_WINDOW_S = 600


def _guarded(fn):
    @functools.wraps(fn)
    def wrapper(self, *args, **kwargs):
        try:
            return fn(self, *args, **kwargs)
        except Exception:
            return None  # evidence must never cost a price

    return wrapper


def _ids(raw, limit):
    parts = [p.strip() for p in raw.split(",")]
    if not 1 <= len(parts) <= limit or any(not re.fullmatch(r"\d{1,12}", p) for p in parts):
        return None
    return frozenset(int(p) for p in parts)


class PMStageTrace(ExactKalshiTrace):
    @classmethod
    def from_env(cls, env, *, run, event_of, wall=time.time, mono=time.monotonic, emit=None):
        try:
            raw_event = env.get("WS_PM_TRACE_EVENT", "")
            raw = env.get("WS_PM_TRACE_OUTCOMES", "")
            if not raw_event or not raw or len(raw_event) > 64:
                return None
            events = _ids(raw_event, MAX_EVENTS)
            if events is None:
                return None
            # One event keeps its four outcomes; a fold may name two per member.
            cap = 4 if len(events) == 1 else 2 * MAX_EVENTS
            if len(raw) > 16 * cap:
                return None
            outcomes = _ids(raw, cap)
            expiry = float(env.get("WS_PM_TRACE_EXPIRES_AT", "0"))
            limit = int(env.get("WS_PM_TRACE_MAX_LINES", "128"))
            raw_arm = env.get("WS_PM_TRACE_ARM_AT")
            now = wall()
            remaining = expiry - now
            if raw_arm is None:
                arm_at = None
                window_ok = 0 < remaining <= MAX_WINDOW_S
            else:
                if len(raw_arm) > 32:
                    return None
                arm_at = float(raw_arm)
                window_ok = (
                    arm_at - now <= MAX_ARM_WAIT_S
                    and 0 < expiry - arm_at <= MAX_WINDOW_S
                    and remaining > 0
                )
            if outcomes is None or not window_ok or not 4 <= limit <= 256:
                return None
            if run is None:
                import uuid

                run = uuid.uuid4().hex[:8]
            trace = cls(outcomes, expiry, limit, run, wall, mono, emit)
            trace.events = events
            trace.event = next(iter(events)) if len(events) == 1 else None
            trace.event_of = event_of
            mapping = trace._map(outcomes)
            start = dict(
                **trace._event_fields(),
                outcomes=sorted(outcomes),
                mapping=mapping,
                expires_at=expiry,
                max_lines=limit,
                accept_clock=ACCEPT_CLOCK,
            )
            if arm_at is not None:
                start.update(arm_at=arm_at, collection="WAITING_FOR_ARM")
            trace._record("START", **start)
            trace.targets = frozenset(int(k) for k, v in mapping.items() if v == "MAPPED")
            if not trace.targets:
                trace._stop("NO_MAPPED_OUTCOME")
            elif arm_at is not None:
                # Same offset as the deadline: the window is expiry - arm_at.
                trace.arm_mono = trace.deadline - (expiry - arm_at)
                trace.warm = True
            return trace
        except (ValueError, TypeError, OverflowError):
            return None

    def __init__(self, targets, expiry, limit, run, wall, mono, emit):
        super().__init__(
            targets, expiry, limit, run, wall, mono,
            emit or (
                lambda record: logger.info(
                    "pm-stage-trace %s", json.dumps(record, sort_keys=True)
                )
            ),
        )
        self.event = None  # the event id when exactly one is traced
        self.events = frozenset()
        self.event_of = {}
        self.outcome_event = {}  # traced outcome -> its event, as last mapped/seen
        self.arm_mono = None  # set only while a warm arm is still waiting
        self.warm = False
        # Per traced event: what an attempt not seen starting is named.
        self.untracked_default = "QUEUED_NOT_STARTED"
        self.untracked = {}
        self.last_value = {}
        self.waiting = {}  # changed seq -> (outcome, value), until a stamp joins it
        self.written = set()  # waiting seqs a PRICE_COMMITTED already carried
        self.joined = {}  # outcome -> seq last carried by an EVENT_COMMITTED
        self.flush = None
        self.flush_seq = self.chunk_seq = self.attempt_seq = 0
        self.chunk = None
        self.attempts = {}  # traced event -> its current attempt
        self.fenced_attempts = set()

    # The single-event view (one traced event), as the earlier trace held it.
    @property
    def attempt(self):
        return self.attempts.get(self.event)

    @property
    def untracked_attempt(self):
        return self._untracked(self.event)

    def _untracked(self, event):
        return self.untracked.get(event, self.untracked_default)

    def _map(self, outcomes):
        mapping = {}
        for oid in sorted(outcomes):
            mapped = self.event_of.get(oid)
            mapping[str(oid)] = (
                "MAPPED" if mapped in self.events
                else "UNMAPPED" if mapped is None
                else "OTHER_EVENT"
            )
            if mapped in self.events:
                self.outcome_event[oid] = mapped
        return mapping

    def _event_fields(self):
        """START/ARMED: ``event`` for one traced event, else the fold's set."""
        if self.event is not None:
            return dict(event=self.event)
        return dict(
            events=sorted(self.events),
            outcome_event={str(o): e for o, e in sorted(self.outcome_event.items())},
            # Event capacity is not outcome coverage: a member with no mapped
            # outcome is named, never read as covered.
            events_without_outcome=sorted(self.events - set(self.outcome_event.values())),
        )

    def _ours(self, event_ids):
        """The traced events among ``event_ids``, in id order."""
        try:
            return sorted(self.events.intersection(event_ids))
        except TypeError:
            return [e for e in sorted(self.events) if e in event_ids]

    def _waiting_of(self, event):
        return sorted(
            s for s, (o, _v) in self.waiting.items() if self.outcome_event.get(o) == event
        )

    def _clear(self):
        super()._clear()
        for state in (self.last_value, self.waiting, self.joined, self.written):
            state.clear()
        self.flush = self.chunk = None
        self.attempts = {}
        self.fenced_attempts = set()

    def _stop(self, reason):
        self.arm_mono = None
        if not self.stopped:
            self.stopped = True
            self._clear()
            self._send(dict(stage="STOP", reason=reason))

    def active(self):
        if self.arm_mono is not None and not self.stopped:
            if self.mono() < self.arm_mono:
                return False  # waiting: no state, no line
            self._arm()
        return super().active()

    def _arm(self):
        arm_mono, self.arm_mono = self.arm_mono, None
        now = self.mono()
        if now >= self.deadline or self.wall() >= self.expiry:
            self._stop("EXPIRED_BEFORE_ARMED")
            return
        self.outcome_event = {}
        mapping = self._map(self.targets)
        self.targets = frozenset(int(k) for k, v in mapping.items() if v == "MAPPED")
        # An attempt already running when collection began was never seen.
        self.untracked_default = "UNTRACKED_MAY_PREDATE_ARMED"
        self.untracked = {}
        self._send(dict(
            stage="ARMED",
            **self._event_fields(),
            mapping=mapping,
            arm_mono=arm_mono,
            armed_mono=now,
            late_by_s=round(now - arm_mono, 6),
            window_left_s=round(self.deadline - now, 6),
            armed_by="FIRST_ENTRY_POINT_AT_OR_AFTER_ARM",
        ))
        if not self.targets:
            self._stop("NO_MAPPED_OUTCOME")
        else:
            self._notify_armed(self.deadline - now)

    def _open(self, outcome=None, seq=None):
        return any(
            (outcome is None or o == outcome) and (seq is None or s <= seq)
            for s, (o, _value) in self.waiting.items()
        )

    def _input_chain(self, entry):
        if not entry["_decision_logged"]:
            self._record(
                "ACCEPTED",
                **self._fields(entry),
                receive_wall=entry["_decision_wall"],
                receive_mono=entry["_decision_mono"],
            )
            entry["_decision_logged"] = True

    def _mine(self, mark):
        return (
            mark is not None
            and mark.event_id in self.events
            and mark.outcome_id in self.targets
        )

    # ── the socket's side ────────────────────────────────────────────────────

    @_guarded
    def input_accepted(self, mark):
        if not self.active() or not self._mine(mark):
            return
        oid = mark.outcome_id
        self.outcome_event[oid] = mark.event_id
        changed = self.last_value.get(oid) != mark.probability
        first = oid not in self.last_value
        self.last_value[oid] = mark.probability
        entry = dict(
            event=mark.event_id,
            outcome=oid,
            probability=mark.probability,
            kind=mark.kind,
            input_seq=mark.seq,
            event_ordinal=mark.event_ordinal,
            venue_ts_ms=mark.venue_ts_ms,
            input_recv_wall=mark.recv_wall,
            input_recv_mono=mark.recv_mono,
            accept_clock=ACCEPT_CLOCK,
            changed=changed and not first,
            _receive=None,
            _receive_logged=True,
            _decision_logged=False,
            _decision_wall=mark.recv_wall,
            _decision_mono=mark.recv_mono,
            _signature=(oid, mark.seq),
        )
        entry["first_since_armed" if self.warm else "first_of_run"] = first
        self._put(self.accepted, mark.seq, entry)
        if changed:
            if mark.seq not in self.waiting and len(self.waiting) >= MAX_PENDING:
                self._stop("PENDING_OVERFLOW")
                return
            self.waiting[mark.seq] = (oid, mark.probability)
            self._input_chain(entry)

    # ── the flush's side ─────────────────────────────────────────────────────

    @_guarded
    def flush_begin(self, flush_started, final, marks, batch=()):
        """The flush's snapshot of the buffered marks (`batch_marks`). A
        selected outcome buffered with NO mark still opens the flush, so its
        write reports an unavailable identity instead of nothing."""
        self.flush = None
        if not self.active() or not self.waiting:
            return
        mine = [m for m in marks.values() if self._mine(m)]
        markless = sorted(
            oid for oid in batch
            if oid in self.targets and marks.get(oid) is None and self._open(oid)
        )
        if not markless and not any(self._open(m.outcome_id, m.seq) for m in mine):
            return
        self.flush_seq += 1
        self.snapshot(mine)
        self.flush = dict(
            flush=self.flush_seq,
            flush_started_mono=flush_started,
            final=bool(final),
            snapshot_mono=self.mono(),
            snapshot=sorted((m.outcome_id, m.seq, m.probability) for m in mine)
            + [(oid, "UNAVAILABLE", None) for oid in markless],
        )

    @_guarded
    def chunk_begin(self, index, chunk_ids):
        if self.chunk is not None:
            self._chunk_line(self.chunk, "UNFINISHED_UNAVAILABLE")
            self.chunk = None
        if self.flush is None or not self.active():
            return None
        selected = sorted(
            oid for oid in chunk_ids if oid in self.targets
        )
        if not selected:
            return None
        self.chunk_seq += 1
        spans = sorted({self.outcome_event.get(oid) for oid in selected} - {None})
        self.chunk = dict(
            self.flush,
            # One event (always, with one traced): the earlier line's field.
            **(dict(event=spans[0]) if len(spans) == 1
               else dict(event="MULTIPLE" if spans else "UNAVAILABLE", events=spans)),
            chunk=self.chunk_seq,
            index=index,
            size=len(chunk_ids),
            selected=selected,
            path="NO_RUNNING_STAMP",
            begin_mono=self.mono(),
        )
        return self.chunk

    @_guarded
    def chunk_note(self, token, path):
        if token is not None and token is self.chunk:
            token["path"] = path

    @_guarded
    def fence(self, token, held, fenced_events):
        if token is None or token is not self.chunk or not self.active():
            return
        token["path"] = "FENCE_CHECK"
        token["held_events"] = len(held) if held is not None else "UNAVAILABLE"
        ours = self._ours(fenced_events)
        by = {}
        for event in ours:
            by[event] = self._fenced(token, event)
        if len(by) == 1:
            token["fenced_by"] = by[ours[0]]
        elif by:
            token["fenced_by"] = {str(e): ident for e, ident in by.items()}

    def _fenced(self, token, event):
        attempt = self.attempts.get(event)
        ident = attempt["attempt"] if attempt is not None else self._untracked(event)
        if ident in self.fenced_attempts:
            token["fenced_repeat"] = True
            return ident
        if attempt is not None:
            self.fenced_attempts.add(ident)
            attempt["fenced_ours"] = True
        self._record(
            "FENCED",
            event=event,
            flush=token["flush"],
            chunk=token["chunk"],
            held_attempt=ident,
            held_attempt_start_mono=(
                attempt["start_mono"] if attempt is not None else "UNAVAILABLE"
            ),
            held_attempt_kind=(
                attempt.get("kind", "UNAVAILABLE") if attempt is not None else "UNAVAILABLE"
            ),
            fence_mono=self.mono(),
        )
        return ident

    @_guarded
    def chunk_write(self, token, chunk, marks):
        """Immediately before `write_chunk`, with the values and marks it writes."""
        if token is None or token is not self.chunk or not self.active():
            return
        mine = {oid: marks.get(oid) for oid in chunk if oid in self.targets}
        if not mine:
            self._chunk_line(token, "FENCED")
            self.chunk = None
            return
        token["write_mono"] = self.mono()
        token["written"] = sorted(
            (oid, m.seq if m is not None else "UNAVAILABLE", chunk[oid])
            for oid, m in mine.items()
        )
        token["_chunk"] = chunk  # pins identity: `write_stage` matches this object
        token["_marks"] = mine
        # The exact identities this write carries, held HERE: socket repeats
        # arriving during the awaited write age the bounded `accepted` map.
        token["_identities"] = {
            oid: self._accepted(m) if m is not None else None for oid, m in mine.items()
        }

    @_guarded
    def write_stage(self, chunk, stage, rows=None, reason=None):
        """Called from inside `write_chunk` for the chunk this flush registered."""
        token = self.chunk
        if token is None or token.get("_chunk") is not chunk or not self.active():
            return
        token[f"{stage.lower()}_mono"] = self.mono()
        marks, identities = token["_marks"], token["_identities"]
        if stage == "COMMITTED":
            returned = {row.id: row for row in rows or ()}
            for oid, mark in sorted(marks.items()):
                row = returned.get(oid)
                if row is None:
                    self._not_committed(
                        mark, oid, identities.get(oid), "NO_ROW_RETURNED_UNCHANGED"
                    )
                else:
                    self._committed(mark, oid, identities.get(oid), row)
        elif stage in ("FAILED", "COOLDOWN_SKIP"):
            token["detail"] = reason or stage
            for oid, mark in sorted(marks.items()):
                self._not_committed(mark, oid, identities.get(oid), reason or stage)

    def _lineage(self, mark):
        """What this write carries of the outcome's open changed seqs (see
        "Identity" above). Never a claim that any value was stamped."""
        older = sorted(
            s for s, (o, _v) in self.waiting.items()
            if o == mark.outcome_id and s <= mark.seq
        )
        latest = older[-1] if older else None
        carries = (
            latest
            if latest is not None and self.waiting[latest][1] == mark.probability
            else None
        )
        earlier = [s for s in older if s != carries]
        return carries, dict(
            carries_changed_seq=carries,
            superseded_unwritten=[s for s in earlier if s not in self.written][-MAX_COVERS:],
            committed_unstamped=[s for s in earlier if s in self.written][-MAX_COVERS:],
        )

    def _committed(self, mark, oid, identity, row):
        observed = row.last_updated
        if identity is None:
            if self._open(oid):
                self._record(
                    "PRICE_COMMITTED_IDENTITY_UNAVAILABLE",
                    event=self.outcome_event.get(oid),
                    outcome=oid,
                    input_seq=mark.seq if mark is not None else "UNAVAILABLE",
                    identity_reason=(
                        "WRITTEN_MARK_NOT_RETAINED" if mark is not None else "NO_MARK"
                    ),
                    stored_at=observed.isoformat(),
                    stored_clock="DB_TRANSACTION_NOW_NOT_COMMIT",
                    commit_mono=self.mono(),
                )
            return
        if not self._open(oid, mark.seq):
            return
        carries, lineage = self._lineage(mark)
        if carries is not None:
            self.written.add(carries)
        fields = dict(
            identity,
            **lineage,
            stored_at=observed.isoformat(),
            stored_epoch=observed.timestamp(),
            stored_clock="DB_TRANSACTION_NOW_NOT_COMMIT",
            commit_mono=self.mono(),
        )
        self._put(self.commits, oid, fields)
        self._input_chain(identity)
        self._record("PRICE_COMMITTED", **self._fields(fields))

    def _not_committed(self, mark, oid, identity, reason):
        if identity is None:
            if self._open(oid):
                self._record(
                    "PRICE_NOT_COMMITTED", event=self.outcome_event.get(oid), outcome=oid,
                    input_seq=mark.seq if mark is not None else "UNAVAILABLE",
                    identity="UNAVAILABLE", write_reason=reason,
                )
            return
        if not self._open(oid, mark.seq):
            return
        self._input_chain(identity)
        self._record(
            "PRICE_NOT_COMMITTED", **self._fields(identity),
            **self._lineage(mark)[1], write_reason=reason,
        )

    def _chunk_line(self, token, result):
        if not self.active():
            return
        clocks = {k: v for k, v in token.items() if k.endswith("_mono")}

        def span(a, b):
            return (
                round(clocks[b] - clocks[a], 6)
                if a in clocks and b in clocks else "UNAVAILABLE"
            )

        self._record(
            "CHUNK",
            **{k: v for k, v in token.items() if not k.startswith("_")},
            result=result,
            end_mono=self.mono(),
            pre_write_s=span("begin_mono", "write_mono"),
            session_wait_s=span("write_mono", "session_mono"),
            statement_s=span("statement_start_mono", "statement_end_mono"),
            to_commit_s=span("statement_end_mono", "committed_mono"),
        )

    @_guarded
    def chunk_end(self, token, wrote):
        if token is None or token is not self.chunk:
            return
        self.chunk = None
        result = (
            "COMMITTED" if wrote
            else "LOCK_DEFERRED" if wrote is None
            else "FAILED"
        )
        self._chunk_line(token, result)

    # ── the refresher's side ─────────────────────────────────────────────────

    @_guarded
    def stage_admission(self, kind, reason, event_ids, *, due=None, excluded=None,
                        fresh=None, flush_started=None):
        if not self.active() or not self.waiting:
            return
        for event in self._ours(set(event_ids)):
            open_seqs = self._waiting_of(event)
            if not open_seqs:
                continue
            fields = dict(flush_started=flush_started)
            why = reason
            if due is not None:
                fields.update(
                    due=event in due,
                    excluded=event in excluded,
                    fresh=event in fresh,
                )
                if why is None:
                    why = (
                        "DUE" if fields["due"]
                        else "DEFERRED_UNFINISHED" if fields["excluded"]
                        else "NOT_DUE_THROTTLED_OR_BUDGET"
                    )
            attempt = self.attempts.get(event)
            self._record(
                "ADMISSION",
                event=event,
                path=kind,
                reason=why,
                open_seqs=open_seqs[-MAX_COVERS:],
                current_attempt=attempt["attempt"] if attempt is not None else None,
                admission_mono=self.mono(),
                **fields,
            )

    @_guarded
    def attempt_start(self, event_ids, clock):
        if not self.active():
            return
        for event in self._ours(event_ids):
            self.attempt_seq += 1
            self.untracked[event] = "QUEUED_NOT_STARTED"
            previous = self.attempts.get(event)
            self.attempts[event] = dict(
                attempt=self.attempt_seq,
                start_mono=self.mono(),
                flush_clock=clock,
                group=len(event_ids),
                open_at_start=self._waiting_of(event)[-MAX_COVERS:],
                overlapped=previous["attempt"] if previous is not None else None,
            )

    @_guarded
    def attempt_session(self, event_ids):
        for event in self._ours(event_ids):
            attempt = self.attempts.get(event)
            if attempt is not None:
                attempt.setdefault("session_mono", self.mono())

    @_guarded
    def attempt_committed(self, event_ids, dispositions):
        for event in self._ours(event_ids):
            attempt = self.attempts.get(event)
            if attempt is None:
                continue
            disposition = dispositions.get(event, ())
            attempt["committed_mono"] = self.mono()
            attempt["kind"] = disposition[0] if disposition else "UNAVAILABLE"
            if disposition[:1] == ("stamped",) and len(disposition) > 4:
                attempt["revision"] = disposition[4]
                attempt["event_updated_at"] = disposition[2]

    @_guarded
    def attempt_released(self, event_ids):
        ours = self._ours(event_ids)
        if not ours or not self.active():
            return
        for event in ours:
            attempt = self.attempts.pop(event, None)
            if attempt is None:
                continue
            self.fenced_attempts.discard(attempt["attempt"])
            if not (attempt["open_at_start"] or attempt.get("fenced_ours")
                    or self._waiting_of(event) or attempt.get("joined")):
                continue
            attempt.setdefault("kind", "NOT_COMMITTED_OR_UNAVAILABLE")
            self._record(
                "ATTEMPT",
                event=event,
                **{k: v for k, v in attempt.items() if k != "fenced_ours"},
                fenced_ours=bool(attempt.get("fenced_ours")),
                released_mono=self.mono(),
            )

    def tracks_event(self, event):
        return self.active() and event in self.events and any(
            v.get("event") == event for v in self.commits.values()
        )

    @_guarded
    def stamp(self, event, basis, revision, updated_at):
        if not self.active() or event not in self.events:
            return
        matched = [
            v for oid, v in self.commits.items()
            if v.get("event") == event
            and (basis or {}).get(str(oid)) == v["stored_epoch"]
            and self.joined.get(oid, -1) < v["input_seq"]
        ]
        if not matched:
            return
        self._put(self.stamps, (event, revision), matched)
        attempt = self.attempts.get(event)
        if attempt is not None:
            attempt["joined"] = True
        for identity in matched:
            oid = identity["outcome"]
            self.joined[oid] = identity["input_seq"]
            for seq in [s for s, (o, _v) in self.waiting.items()
                        if o == oid and s <= identity["input_seq"]]:
                del self.waiting[seq]
                self.written.discard(seq)
            self._record(
                "EVENT_COMMITTED",
                **self._fields(identity),
                revision=revision,
                event_updated_at=updated_at,
                event_clock="DB_CLOCK_TIMESTAMP",
                attempt=attempt["attempt"] if attempt is not None else "UNAVAILABLE",
                linkage="EXACT_OUTCOME_OBSERVATION_BASIS",
            )
