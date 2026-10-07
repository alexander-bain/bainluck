"""#10702: optional evidence on the existing socket; no I/O or price policy.

Enable only with <=4 exact WS_KALSHI_TRACE_TICKERS and an absolute epoch-second
WS_KALSHI_TRACE_EXPIRES_AT no more than 600s away. WS_KALSHI_TRACE_MAX_LINES
defaults to 128 (hard cap 256, including STOP). No payloads, headers, server
error text or credentials are retained. Exhaustion/expiry discard all state.
ACK proves the correlated command/channel response, never ticker membership.

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

    def _clear(self):
        for state in (
            self.commands,
            self.receives,
            self.accepted,
            self.commits,
            self.stamps,
        ):
            state.clear()

    def _send(self, record):
        self.lines += 1
        try:
            self.emit(
                dict(
                    run=self.run,
                    receive_wall=self.wall(),
                    receive_mono=self.mono(),
                    **record
                )
            )
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
        self._put(self.receives, id(msg), identity)
        self._record(
            "RECEIVED",
            **identity,
            supplied_fields=[f for f in FIELDS if f in msg],
            prices={f: number(msg[f]) for f in FIELDS if f in msg},
            vendor_clock={f: number(msg[f]) for f in CLOCK_FIELDS if f in msg}
            or "UNAVAILABLE"
        )

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
        identity = self.receives.pop(
            id(msg), dict(ticker=ticker.upper(), receive_id="UNAVAILABLE")
        )
        fields = dict(
            **identity,
            reason=reason,
            market=market,
            outcome=outcome,
            event=event,
            probability=probability,
            input_seq=mark.seq if mark is not None else "UNAVAILABLE",
            input_recv_wall=mark.recv_wall if mark is not None else "UNAVAILABLE",
            input_recv_mono=mark.recv_mono if mark is not None else "UNAVAILABLE"
        )
        if mark is not None:
            self._put(self.accepted, mark.seq, fields)
        self._record("DECISION", **fields)

    def committed(self, mark, observed_at):
        if not self.active() or mark is None:
            return
        identity = self.accepted.get(mark.seq)
        if identity is None or identity["outcome"] != mark.outcome_id:
            return
        fields = dict(
            identity,
            stored_at=observed_at.isoformat(),
            stored_epoch=observed_at.timestamp(),
        )
        self._put(self.commits, mark.outcome_id, fields)
        self._record("PRICE_COMMITTED", **fields)

    def tracks(self, mark):
        return (
            self.active()
            and mark is not None
            and mark.seq in self.accepted
            and self.accepted[mark.seq]["outcome"] == mark.outcome_id
        )

    def tracks_event(self, event):
        return self.active() and any(v["event"] == event for v in self.commits.values())

    def write_failed(self, marks, reason):
        for mark in marks:
            if self.active() and mark is not None and mark.seq in self.accepted:
                self._record(
                    "PRICE_NOT_COMMITTED",
                    **self.accepted[mark.seq],
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
                self._record(
                    "EVENT_COMMITTED",
                    **identity,
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
                **identity,
                revision=revision,
                publication=status,
                browser_delivery="UNAVAILABLE"
            )
