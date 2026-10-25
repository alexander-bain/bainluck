"""#10090: optional stage trace for ONE live event's selected Polymarket outcomes.

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
            if not raw_event or not raw or len(raw) > 64:
                return None
            if not re.fullmatch(r"\d{1,12}", raw_event.strip()):
                return None
            event = int(raw_event.strip())
            outcomes = _ids(raw, 4)
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
            trace.event = event
            trace.event_of = event_of
            mapping = {}
            for oid in sorted(outcomes):
                mapped = event_of.get(oid)
                mapping[str(oid)] = (
                    "MAPPED" if mapped == event
                    else "UNMAPPED" if mapped is None
                    else "OTHER_EVENT"
                )
            start = dict(
                event=event,
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
        self.event = None
        self.event_of = {}
        self.arm_mono = None  # set only while a warm arm is still waiting
        self.warm = False
        self.untracked_attempt = "QUEUED_NOT_STARTED"
        self.last_value = {}
        self.waiting = {}  # changed seq -> (outcome, value), until a stamp joins it
        self.written = set()  # waiting seqs a PRICE_COMMITTED already carried
        self.joined = {}  # outcome -> seq last carried by an EVENT_COMMITTED
        self.flush = None
        self.flush_seq = self.chunk_seq = self.attempt_seq = 0
        self.chunk = None
        self.attempt = None
        self.fenced_attempts = set()

    def _clear(self):
        super()._clear()
        for state in (self.last_value, self.waiting, self.joined, self.written):
            state.clear()
        self.flush = self.chunk = self.attempt = None
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
        mapping = {}
        for oid in sorted(self.targets):
            mapped = self.event_of.get(oid)
            mapping[str(oid)] = (
                "MAPPED" if mapped == self.event
                else "UNMAPPED" if mapped is None
                else "OTHER_EVENT"
            )
        self.targets = frozenset(int(k) for k, v in mapping.items() if v == "MAPPED")
        # An attempt already running when collection began was never seen.
        self.untracked_attempt = "UNTRACKED_MAY_PREDATE_ARMED"
        self._send(dict(
            stage="ARMED",
            event=self.event,
            mapping=mapping,
            arm_mono=arm_mono,
            armed_mono=now,
            late_by_s=round(now - arm_mono, 6),
            window_left_s=round(self.deadline - now, 6),
            armed_by="FIRST_ENTRY_POINT_AT_OR_AFTER_ARM",
        ))
        if not self.targets:
            self._stop("NO_MAPPED_OUTCOME")

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
            and mark.event_id == self.event
            and mark.outcome_id in self.targets
        )

    # ── the socket's side ────────────────────────────────────────────────────

    @_guarded
    def input_accepted(self, mark):
        if not self.active() or not self._mine(mark):
            return
        oid = mark.outcome_id
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
        self.chunk = dict(
            self.flush,
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
        if self.event not in fenced_events:
            return
        attempt = self.attempt
        ident = attempt["attempt"] if attempt is not None else self.untracked_attempt
        token["fenced_by"] = ident
        if ident in self.fenced_attempts:
            token["fenced_repeat"] = True
            return
        if attempt is not None:
            self.fenced_attempts.add(ident)
            attempt["fenced_ours"] = True
        self._record(
            "FENCED",
            event=self.event,
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
                    event=self.event,
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
                    "PRICE_NOT_COMMITTED", event=self.event, outcome=oid,
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
            event=self.event,
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
        if not self.active() or not self.waiting or self.event not in set(event_ids):
            return
        fields = dict(flush_started=flush_started)
        if due is not None:
            fields.update(
                due=self.event in due,
                excluded=self.event in excluded,
                fresh=self.event in fresh,
            )
            if reason is None:
                reason = (
                    "DUE" if fields["due"]
                    else "DEFERRED_UNFINISHED" if fields["excluded"]
                    else "NOT_DUE_THROTTLED_OR_BUDGET"
                )
        attempt = self.attempt
        self._record(
            "ADMISSION",
            event=self.event,
            path=kind,
            reason=reason,
            open_seqs=sorted(self.waiting)[-MAX_COVERS:],
            current_attempt=attempt["attempt"] if attempt is not None else None,
            admission_mono=self.mono(),
            **fields,
        )

    @_guarded
    def attempt_start(self, event_ids, clock):
        if not self.active() or self.event not in event_ids:
            return
        self.attempt_seq += 1
        self.untracked_attempt = "QUEUED_NOT_STARTED"
        previous = self.attempt
        self.attempt = dict(
            attempt=self.attempt_seq,
            start_mono=self.mono(),
            flush_clock=clock,
            group=len(event_ids),
            open_at_start=sorted(self.waiting)[-MAX_COVERS:],
            overlapped=previous["attempt"] if previous is not None else None,
        )

    @_guarded
    def attempt_session(self, event_ids):
        if self.attempt is not None and self.event in event_ids:
            self.attempt.setdefault("session_mono", self.mono())

    @_guarded
    def attempt_committed(self, event_ids, dispositions):
        if self.attempt is None or self.event not in event_ids:
            return
        disposition = dispositions.get(self.event, ())
        self.attempt["committed_mono"] = self.mono()
        self.attempt["kind"] = disposition[0] if disposition else "UNAVAILABLE"
        if disposition[:1] == ("stamped",) and len(disposition) > 4:
            self.attempt["revision"] = disposition[4]
            self.attempt["event_updated_at"] = disposition[2]

    @_guarded
    def attempt_released(self, event_ids):
        if self.event not in event_ids or not self.active():
            return
        attempt, self.attempt = self.attempt, None
        if attempt is None:
            return
        self.fenced_attempts.discard(attempt["attempt"])
        if not (attempt["open_at_start"] or attempt.get("fenced_ours") or self.waiting
                or attempt.get("joined")):
            return
        attempt.setdefault("kind", "NOT_COMMITTED_OR_UNAVAILABLE")
        self._record(
            "ATTEMPT",
            event=self.event,
            **{k: v for k, v in attempt.items() if k != "fenced_ours"},
            fenced_ours=bool(attempt.get("fenced_ours")),
            released_mono=self.mono(),
        )

    def tracks_event(self, event):
        return self.active() and event == self.event and bool(self.commits)

    @_guarded
    def stamp(self, event, basis, revision, updated_at):
        if not self.active() or event != self.event:
            return
        matched = [
            v for oid, v in self.commits.items()
            if (basis or {}).get(str(oid)) == v["stored_epoch"]
            and self.joined.get(oid, -1) < v["input_seq"]
        ]
        if not matched:
            return
        self._put(self.stamps, (event, revision), matched)
        if self.attempt is not None:
            self.attempt["joined"] = True
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
                attempt=self.attempt["attempt"] if self.attempt is not None else "UNAVAILABLE",
                linkage="EXACT_OUTCOME_OBSERVATION_BASIS",
            )
