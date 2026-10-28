"""#10702: optional evidence on the existing socket; no I/O or price policy.

Enable only with <=4 exact WS_KALSHI_TRACE_TICKERS and an absolute epoch-second
WS_KALSHI_TRACE_EXPIRES_AT no more than 600s away. WS_KALSHI_TRACE_MAX_LINES
defaults to 128 (hard cap 256, including STOP). No payloads, headers, server
error text or credentials are retained. Exhaustion/expiry discard all state.
ACK proves the correlated command/channel response, never ticker membership.
Identical repeats retain exact receive/InputMark identities without spending
lines. A commit, failure or event basis materializes its required input chain;
received clocks stay original even when the evidence is emitted later.

Provenance (#10090): RECEIVED.source says what arrived — a TICKER summary
(its own whitelisted prices) or an ORDERBOOK_FRAME (no prices: book levels
are not a quote). DECISION.dispatch says what the handler actually read:
TICKER_AS_RECEIVED, TICKER_BOOK_OVERLAY (a copy carrying the book's BBO) or
ORDERBOOK_DERIVED (the book's changed best quote), with dispatched_prices
from that object. A pending receipt holds its object, so a recycled id can
never hand one frame's receipt to another; no exact link is UNAVAILABLE.

Post-deploy procedure (owner-controlled; this module changes no configuration):
use the existing bounded worker log session and arrange owner-controlled
activation of the two exact outcome tickers and an absolute expiry <=600s away.
Heroku config activation restarts affected dynos: the owner must account for
that restart; this is not hot environment adoption on a normal recycle.
Find START for that run/expiry, then ADMISSION and SENT/ACK/ERROR. Follow the
same run/receive_id/input_seq through PRICE_COMMITTED and the exact observation
basis to EVENT_COMMITTED/revision and EVENT_PUBLICATION. REDIS_ACK says nothing
about browser delivery; use the existing page capture for that final boundary.
Missing START is UNAVAILABLE, not zero traffic. STOP explains lost coverage.
After expiry, remove the temporary trace settings; no new socket, provider poll,
collector, automatic restart or activation is performed by this code.

PREVIEW (#10090) closes the join from those inputs to the provisional state a
reader adopts. At the ledger's send, one line per composed frame of a traced
event: the frame's ``(epoch, seq)`` (the identity a held page adopts), its
``publication`` reply, and for a blend the committed ``base_rev`` and the WHOLE
composed bag, base plus pending, one row per probability source: role, value,
write clock, observation basis, refusal and the weight the hero gives it, with
the tier, ``recomputed_p`` and whether it equals the frame's ``p``. A basis key
equal to a retained commit's ``stored_epoch`` names that ``input_seq``
(EXACT_OUTCOME_OBSERVATION_BASIS, the EVENT_COMMITTED rule); a tracked outcome
at another observation says so; equal values are never a link. Revokes carry
``through_seq`` and ``reason`` (expiry, refusal, removal). ``ttl_ms`` is the
Redis-computed lifetime; a reader's own expiry is receipt-relative. Limits: a
process sees only frames it sends, so the other venue's frames for the same
event appear as ``seq`` gaps here and in its own trace; the line describes the
send, never browser delivery.
"""

import json
import logging
import math
import re
import time

logger = logging.getLogger(__name__)
FIELDS = (
    "price_dollars",
    "yes_bid_dollars",
    "yes_ask_dollars",
    "price",
    "yes_bid",
    "yes_ask",
)
CLOCK_FIELDS = ("ts", "ts_ms", "timestamp")
MAX_PENDING = 64
PREVIEW_SOURCES = 16  # rows per PREVIEW line; the rest are counted
PREVIEW_BASIS = 8  # observation-basis keys per row; the rest are counted


def number(value):
    """Keep numbers only; arbitrary strings may contain credentials."""
    if isinstance(value, bool) or not isinstance(value, (int, float, str)):
        return "INVALID"
    if isinstance(value, str) and (
        len(value) > 32 or not re.fullmatch(r"[-+0-9.eE]+", value)
    ):
        return "INVALID"
    try:
        parsed = float(value)
        return parsed if math.isfinite(parsed) else "INVALID"
    except (ValueError, TypeError, OverflowError):
        return "INVALID"


def _word(value):
    """Our own short enums only (statuses, reasons, source keys)."""
    if isinstance(value, str) and re.fullmatch(r"[A-Za-z0-9_:-]{1,48}", value):
        return value
    return "INVALID"


def _int(value):
    return value if type(value) is int else "INVALID"


def _scalar(value):
    return None if value is None else number(value)


class ExactKalshiTrace:
    @classmethod
    def from_env(cls, env, *, run, wall=time.time, mono=time.monotonic, emit=None):
        try:
            raw = env.get("WS_KALSHI_TRACE_TICKERS", "")
            if not raw or len(raw) > 516:
                return None
            targets = frozenset(t.strip().upper() for t in raw.split(","))
            expiry = float(env.get("WS_KALSHI_TRACE_EXPIRES_AT", "0"))
            limit = int(env.get("WS_KALSHI_TRACE_MAX_LINES", "128"))
            remaining = expiry - wall()
            if (
                not 1 <= len(targets) <= 4
                or not 0 < remaining <= 600
                or not 4 <= limit <= 256
                or any(not re.fullmatch(r"[A-Z0-9_-]{1,128}", t) for t in targets)
            ):
                return None
            if run is None:
                import uuid

                run = uuid.uuid4().hex[:8]
            trace = cls(targets, expiry, limit, run, wall, mono, emit)
            trace._record(
                "START",
                targets=sorted(targets),
                expires_at=expiry,
                max_lines=limit,
                mapping="UNAVAILABLE_BEFORE_SLATE",
            )
            return trace
        except (ValueError, TypeError, OverflowError):
            return None

    def __init__(self, targets, expiry, limit, run, wall, mono, emit):
        self.targets, self.expiry, self.limit, self.run = targets, expiry, limit, run
        self.wall, self.mono = wall, mono
        self.deadline = mono() + expiry - wall()
        self.emit = emit or (
            lambda record: logger.info(
                "kalshi-exact-trace %s", json.dumps(record, sort_keys=True)
            )
        )
        self.lines = 0
        self.stopped = False
        self.commands, self.receives, self.accepted, self.commits, self.stamps = (
            {},
            {},
            {},
            {},
            {},
        )
        self.receive_seq = 0
        self.pinned = {}
        self.last_quotes, self.last_decisions, self.last_writes = {}, {}, {}

    def _clear(self):
        for state in (
            self.commands,
            self.receives,
            self.accepted,
            self.commits,
            self.stamps,
            self.pinned,
            self.last_quotes,
            self.last_decisions,
            self.last_writes,
        ):
            state.clear()

    def _send(self, record):
        self.lines += 1
        try:
            wall, mono = self.wall(), self.mono()
            envelope = dict(
                run=self.run,
                receive_wall=wall,
                receive_mono=mono,
                emitted_wall=wall,
                emitted_mono=mono,
            )
            envelope.update(record)
            self.emit(envelope)
        except Exception:
            pass  # evidence must never cost a quote

    def active(self):
        if self.stopped:
            return False
        reason = (
            "EXPIRED"
            if self.wall() >= self.expiry or self.mono() >= self.deadline
            else "BUDGET_STOP" if self.lines >= self.limit - 1 else None
        )
        if reason:
            self.stopped = True
            self._clear()
            self._send(dict(stage="STOP", reason=reason))
            return False
        return True

    def _record(self, stage, **fields):
        if self.active():
            self._send(dict(stage=stage, **fields))

    @staticmethod
    def _put(state, key, value):
        if key not in state and len(state) >= MAX_PENDING:
            state.pop(next(iter(state)))
        state[key] = value

    def sent(self, connection, command, channel, tickers, subscribe_all=False):
        if not self.active():
            return
        targets = sorted(
            self.targets
            if subscribe_all or not tickers
            else self.targets.intersection(tickers)
        )
        if not targets:
            return
        self._put(self.commands, (connection, command), (channel, targets))
        self._record(
            "SENT",
            connection=connection,
            command=command,
            channel=channel,
            targets=targets,
            membership="REQUESTED_ONLY",
        )

    def admission(self, linked, opened, event_of, *, phase, open_status):
        """Read the existing maps only. Selection is not a server ACK."""
        for ticker in sorted(self.targets):
            if not self.active():
                return
            ids = linked.get(ticker) or opened.get(ticker)
            self._record(
                "ADMISSION",
                ticker=ticker,
                phase=phase,
                selected_in_linked=ticker in linked,
                selected_in_open=ticker in opened,
                open_status=open_status,
                market=ids[0] if ids else None,
                outcome=ids[1] if ids else None,
                event=event_of.get(ids[1]) if ids else None,
                membership="UNPROVEN_SELECTION_ONLY",
            )

    def response(self, connection, data):
        if not self.active() or not isinstance(data, dict):
            return
        command = data.get("id")
        if type(command) is not int:
            return
        request = self.commands.get((connection, command))
        if request is None or data.get("type") not in ("subscribed", "error"):
            return
        channel, targets = request
        payload = data.get("msg") if isinstance(data.get("msg"), dict) else {}
        if data["type"] == "error":
            self._record(
                "ERROR",
                connection=connection,
                command=command,
                channel=channel,
                targets=targets,
                code=number(payload.get("code")),
                membership="UNPROVEN",
            )
        else:
            # Do not infer membership from a channel ACK or trust free-form text.
            self._record(
                "ACK",
                connection=connection,
                command=command,
                channel=channel,
                channel_matches=payload.get("channel") == channel,
                sid=number(payload.get("sid")),
                targets=targets,
                membership="UNPROVEN_CHANNEL_ACK_ONLY",
            )

    def received(self, connection, msg):
        if not self.active() or not isinstance(msg, dict):
            return
        ticker = msg.get("market_ticker") or msg.get("ticker")
        if not isinstance(ticker, str) or ticker.upper() not in self.targets:
            return
        self.receive_seq += 1
        identity = dict(
            connection=connection, receive_id=self.receive_seq, ticker=ticker.upper()
        )
        record = dict(
            stage="RECEIVED",
            **identity,
            receive_wall=self.wall(),
            receive_mono=self.mono(),
            supplied_fields=[f for f in FIELDS if f in msg],
            prices={f: number(msg[f]) for f in FIELDS if f in msg},
            vendor_clock={f: number(msg[f]) for f in CLOCK_FIELDS if f in msg}
            or "UNAVAILABLE",
            source="TICKER",
        )
        signature = (connection, tuple(record["prices"].items()))
        changed = self.last_quotes.get(identity["ticker"]) != signature
        self._put(self.last_quotes, identity["ticker"], signature)
        self._put(
            self.receives,
            id(msg),
            dict(
                identity=identity,
                record=record,
                logged=changed,
                obj=msg,  # pins id(msg) while pending: never recycled
                dispatch="TICKER_AS_RECEIVED",
            ),
        )
        if changed:
            self._record(**record)

    def book_received(self, connection, frame):
        """An order book frame's own receipt, before the book is applied.
        Logged only when a dispatched quote's decision materializes it."""
        if not self.active() or not isinstance(frame, dict):
            return
        msg = frame.get("msg")
        ticker = msg.get("market_ticker") if isinstance(msg, dict) else None
        if not isinstance(ticker, str) or ticker.upper() not in self.targets:
            return
        self.receive_seq += 1
        identity = dict(
            connection=connection, receive_id=self.receive_seq, ticker=ticker.upper()
        )
        record = dict(
            stage="RECEIVED",
            **identity,
            receive_wall=self.wall(),
            receive_mono=self.mono(),
            source="ORDERBOOK_FRAME",
            book_kind=frame.get("type"),
            sid=number(frame.get("sid")),
            seq=number(frame.get("seq")),
            supplied_fields=[],
            prices={},
            vendor_clock={f: number(msg[f]) for f in CLOCK_FIELDS if f in msg}
            or "UNAVAILABLE",
        )
        self._put(
            self.receives,
            id(frame),
            dict(
                identity=identity,
                record=record,
                logged=False,
                obj=frame,
                dispatch="UNDISPATCHED",
            ),
        )

    def _take(self, obj):
        entry = self.receives.get(id(obj))
        if entry is None or entry["obj"] is not obj:
            return None
        return self.receives.pop(id(obj))

    def derived(self, original, dispatched, dispatch):
        """Move a receipt onto the object the handler will actually read.
        ``dispatched`` None (no quote) drops it; the same object keeps it."""
        if not self.active():
            return
        entry = self._take(original)
        if entry is None or dispatched is None:
            return
        if dispatched is not original:
            entry = dict(entry, obj=dispatched, dispatch=dispatch)
        self._put(self.receives, id(dispatched), entry)

    @staticmethod
    def _fields(entry):
        return {k: v for k, v in entry.items() if not k.startswith("_")}

    def _input_chain(self, entry):
        if not entry["_receive_logged"] and entry["_receive"] is not None:
            self._record(**entry["_receive"])
            entry["_receive_logged"] = True
        if not entry["_decision_logged"]:
            self._record(
                "DECISION",
                **self._fields(entry),
                receive_wall=entry["_decision_wall"],
                receive_mono=entry["_decision_mono"]
            )
            entry["_decision_logged"] = True

    def snapshot(self, marks):
        """Pin the writer's actual snapshot identities across a repeat burst."""
        if not self.active():
            return
        self.pinned.clear()
        for mark in marks:
            entry = self.accepted.get(mark.seq)
            if entry is not None and entry["outcome"] == mark.outcome_id:
                self._put(self.pinned, mark.seq, entry)

    def _accepted(self, mark):
        if mark is None:
            return None
        entry = self.pinned.get(mark.seq) or self.accepted.get(mark.seq)
        return (
            entry if entry is not None and entry["outcome"] == mark.outcome_id else None
        )

    def _price_chain(self, entry):
        self._input_chain(entry)
        if not entry["_price_logged"]:
            self._record(
                "PRICE_COMMITTED",
                **self._fields(entry),
                receive_wall=entry["_price_wall"],
                receive_mono=entry["_price_mono"]
            )
            entry["_price_logged"] = True

    def decided(
        self,
        msg,
        *,
        reason,
        market=None,
        outcome=None,
        event=None,
        probability=None,
        mark=None
    ):
        if not self.active():
            return
        ticker = msg.get("market_ticker") or msg.get("ticker")
        if not isinstance(ticker, str) or ticker.upper() not in self.targets:
            return
        received = self._take(msg)
        identity = (
            received["identity"]
            if received
            else dict(ticker=ticker.upper(), receive_id="UNAVAILABLE")
        )
        dispatched_prices = {f: number(msg[f]) for f in FIELDS if f in msg}
        fields = dict(
            **identity,
            source=received["record"]["source"] if received else "UNAVAILABLE",
            dispatch=received["dispatch"] if received else "UNAVAILABLE",
            dispatched_prices=dispatched_prices,
            reason=reason,
            market=market,
            outcome=outcome,
            event=event,
            probability=probability,
            input_seq=mark.seq if mark is not None else "UNAVAILABLE",
            input_recv_wall=mark.recv_wall if mark is not None else "UNAVAILABLE",
            input_recv_mono=mark.recv_mono if mark is not None else "UNAVAILABLE"
        )
        signature = (
            identity["ticker"],
            identity.get("connection"),
            tuple(received["record"]["prices"].items()) if received else None,
            fields["source"],
            fields["dispatch"],
            tuple(dispatched_prices.items()),
            reason,
            market,
            outcome,
            event,
            probability,
        )
        changed = self.last_decisions.get(ticker.upper()) != signature
        self._put(self.last_decisions, ticker.upper(), signature)
        fields.update(
            _receive=received["record"] if received else None,
            _receive_logged=received["logged"] if received else True,
            _decision_logged=False,
            _decision_wall=self.wall(),
            _decision_mono=self.mono(),
            _signature=signature,
        )
        if mark is not None:
            self._put(self.accepted, mark.seq, fields)
        if changed:
            self._input_chain(fields)

    def committed(self, mark, observed_at):
        if not self.active() or mark is None:
            return
        identity = self._accepted(mark)
        if identity is None:
            return
        fields = dict(
            identity,
            stored_at=observed_at.isoformat(),
            stored_epoch=observed_at.timestamp(),
        )
        fields["_price_logged"] = False
        fields["_price_wall"], fields["_price_mono"] = self.wall(), self.mono()
        status = (fields["_signature"], "COMMITTED")
        changed = self.last_writes.get(mark.outcome_id) != status
        self._put(self.last_writes, mark.outcome_id, status)
        self._put(self.commits, mark.outcome_id, fields)
        if changed:
            self._price_chain(fields)

    def tracks(self, mark):
        return self.active() and self._accepted(mark) is not None

    def tracks_event(self, event):
        return self.active() and any(v["event"] == event for v in self.commits.values())

    def write_failed(self, marks, reason):
        for mark in marks:
            if not self.active():
                return
            entry = self._accepted(mark)
            if entry is not None:
                status = (entry["_signature"], reason)
                changed = self.last_writes.get(mark.outcome_id) != status
                self._put(self.last_writes, mark.outcome_id, status)
                if changed:
                    self._input_chain(entry)
                    self._record(
                        "PRICE_NOT_COMMITTED",
                        **self._fields(entry),
                        write_reason=reason
                    )

    def stamp(self, event, basis, revision, updated_at):
        if not self.active():
            return
        matched = [
            v
            for oid, v in self.commits.items()
            if v["event"] == event and (basis or {}).get(str(oid)) == v["stored_epoch"]
        ]
        if matched:
            self._put(self.stamps, (event, revision), matched)
            for identity in matched:
                self._price_chain(identity)
                self._record(
                    "EVENT_COMMITTED",
                    **self._fields(identity),
                    revision=revision,
                    event_updated_at=updated_at,
                    linkage="EXACT_OUTCOME_OBSERVATION_BASIS"
                )

    def publication(self, event, revision, status):
        if not self.active():
            return
        if isinstance(revision, dict):
            revision = revision.get(str(event))
        if type(revision) is not int:
            return
        for identity in self.stamps.get((event, revision), ()):
            self._record(
                "EVENT_PUBLICATION",
                **self._fields(identity),
                revision=revision,
                publication=status,
                browser_delivery="UNAVAILABLE"
            )

    def preview(self, frame, ledger, reply):
        """One composed ledger preview frame of a traced event, at its send.

        The registry's publication observer (`blend_preview.observe_publication`).
        Reads only; never raises.
        """
        try:
            if not self.active() or not isinstance(frame, dict):
                return
            event = frame.get("event_id")
            if type(event) is not int or not self.tracks_event(event):
                return
            meta = frame.get("preview") if isinstance(frame.get("preview"), dict) else {}
            kind = meta.get("kind")
            fields = dict(
                event=event,
                kind=kind if kind in ("blend", "revoke") else "INVALID",
                epoch=_int(meta.get("epoch")),
                seq=_int(meta.get("seq")),
                publication=_word(reply[0]) if reply else "UNAVAILABLE",
                browser_delivery="UNAVAILABLE",
            )
            if kind == "revoke":
                fields.update(
                    through_seq=_int(meta.get("through_seq")),
                    reason=_word(meta.get("reason")),
                )
            elif kind == "blend":
                try:
                    fields.update(self._preview_state(frame, meta, ledger, reply))
                except Exception:
                    fields["composition"] = "COMPOSITION_ERROR"  # a line, not silence
            self._record("PREVIEW", **fields)
        except Exception:
            pass  # evidence must never cost a quote

    def _preview_state(self, frame, meta, ledger, reply):
        from types import SimpleNamespace

        from app.utils.aggregation import (
            OBSERVED_BASIS_KEY,
            OBSERVED_VALUE_KEY,
            compute_aggregate_probability_tiered,
            effective_source_weights,
            parse_source_entry,
        )
        from app.utils.probability_eligibility import is_refused

        ledger = ledger if isinstance(ledger, dict) else {}
        published = bool(reply) and reply[0] == "published" and len(reply) > 1
        fields = dict(
            base_rev=_int(meta.get("base_rev")),
            p=number(frame.get("p")),
            mover=_word(frame.get("source")),
            ttl_ms=number(reply[1]) if published else "UNAVAILABLE",
            contributors=[
                dict(source=_word(name), owner=_int(owner), deadline_ms=_int(expires))
                for name, owner, expires in list(ledger.get("contributors") or ())[
                    :PREVIEW_SOURCES
                ]
            ],
            deadline_clock="REDIS_TIME_MS",
        )
        base, pending = ledger.get("base"), meta.get("pending_entries")
        if not isinstance(base, dict) or not isinstance(base.get("sources"), dict):
            fields["composition"] = "BASE_UNAVAILABLE"
            return fields
        if not isinstance(pending, dict):
            fields["composition"] = "PENDING_ENTRIES_UNAVAILABLE"
            return fields
        # The exact bag `_composed_frame` aggregated: the committed base with
        # each pending source's stamped entry over it.
        bag = {**base["sources"], **pending}
        status = base.get("status")
        shim = SimpleNamespace(
            win_probability_sources=bag,
            status=status,
            espn_win_prob_home=base.get("espn_win_prob_home"),
            opening_home_probability=base.get("opening_home_probability"),
        )
        probability, tier = compute_aggregate_probability_tiered(shim, status)
        keys, _values, weights = effective_source_weights(shim, status)
        weight_of = dict(zip(keys, weights))
        rows, omitted = [], 0
        for name in sorted(bag):
            entry = bag[name]
            value, updated = parse_source_entry(entry)
            if (value is None or not isinstance(name, str)
                    or not re.fullmatch(r"[a-z0-9_]{1,40}", name)):
                continue  # not a probability source (an injuries list, a flag)
            if len(rows) >= PREVIEW_SOURCES:
                omitted += 1
                continue
            row = dict(
                source=name,
                role="PENDING" if name in pending else "BASE",
                value=number(value),
                updated_epoch=updated.timestamp() if updated is not None else None,
                refused=bool(is_refused(entry)),
                weight=weight_of.get(name, "NOT_WEIGHTED"),
            )
            basis = entry.get(OBSERVED_BASIS_KEY) if isinstance(entry, dict) else None
            if isinstance(basis, dict):
                ids = sorted(k for k in basis if re.fullmatch(r"\d{1,12}", str(k)))
                shown = ids[:PREVIEW_BASIS]
                row.update(
                    observed_basis={k: number(basis[k]) for k in shown},
                    observed_basis_omitted=len(basis) - len(shown),
                    observed_value=_scalar(entry.get(OBSERVED_VALUE_KEY)),
                    inputs=self._preview_inputs(basis, shown),
                )
            rows.append(row)
        fields.update(
            composition="BASE_PLUS_PENDING_ENTRIES",
            status=_word(status) if status is not None else None,
            espn_win_prob_home=_scalar(base.get("espn_win_prob_home")),
            opening_home_probability=_scalar(base.get("opening_home_probability")),
            tier=_word(tier) if tier is not None else None,
            recomputed_p=_scalar(probability),
            recomputed_matches=(
                probability is not None
                and isinstance(frame.get("p"), float)
                and float(probability) == frame["p"]
            ),
            sources=rows,
            sources_omitted=omitted,
        )
        return fields

    def _preview_inputs(self, basis, ids):
        """Exact input identities behind one source's observation basis."""
        inputs = []
        for key in ids:
            oid = int(key)
            identity = self.commits.get(oid)
            if identity is not None and identity.get("stored_epoch") == basis[key]:
                if "_price_logged" in identity:
                    self._price_chain(identity)  # a repeat's chain, as stamp does
                inputs.append(dict(
                    outcome=oid,
                    input_seq=identity.get("input_seq", "UNAVAILABLE"),
                    receive_id=identity.get("receive_id", "UNAVAILABLE"),
                    linkage="EXACT_OUTCOME_OBSERVATION_BASIS",
                ))
            elif identity is not None or oid in self.targets:
                inputs.append(dict(
                    outcome=oid,
                    input_seq="UNAVAILABLE",
                    linkage="TRACKED_OUTCOME_NO_RETAINED_COMMIT_AT_THIS_OBSERVATION",
                ))
        return inputs
