"""#10090 decision J = A, server half — ``confirmed_at`` on the event stream.

WHY. A live page counts "seconds ago" from the last committed or previewed
CHANGE. On a steady price between points the venues keep quoting that same
price, so the number is current while the counter climbs past 25 s and reads
as a delay. ``confirmed_at`` is the newest time a venue input for the event's
headline outcomes was received and AGREED with what the stream has published
for that source. The page can count from it instead.

THE TRUTH GUARD (Alex's rule): it never advances while a newer, different
price is held or unpublished. Per source and event, ``ConfirmedAt`` advances
only when ALL of these hold:

* the source has published a reading this run, and ``pub`` is the outcome
  prices that reading actually blended (the stamp's contributing rows, held
  quote overlays included) — not what the socket last sent, which a lock
  skip, a later writer or a split phase can make different;
* the newest input of EVERY outcome in ``pub`` equals its published price
  (rounded to 6 places, as the observation path compares);
* no refresh batch holding the event is open (a preview or stamp may be
  about to publish), and no preview a failed stamp left on readers can still
  be showing (``frozen_until``, the preview's own uncommitted lifetime);
* the stamp's frame has been ACKNOWLEDGED by the publisher
  (`LiveBlendRefresher._publish_prices` → `published`): a committed stamp
  whose frame is still queued, failed to build, or failed to publish is a
  newer, different price readers do not have yet (lane1 R2 on #11767);
* on Polymarket, no buffered withdrawal's book prices a published leg out.

A held or unknown state freezes ``c`` (the last agreement) and records ``h``,
when the hold began. An unknown state (nothing this run published can be
compared) holds until ``UNKNOWN_HOLD_S`` after the source's LAST input: a
source that never stamps stops capping only once it also stops speaking. Each venue runs in its own worker-ws process, so the
reader combines them: the newest ``c`` across venues and members, but never
past the earliest live ``h`` — a hold on one venue is a newer, different
price on the event.

PRODUCER. Pure bookkeeping on the socket and refresher paths (nothing awaited,
O(outcomes of one event)); a changed state is written by a separate task: an
advance at most once per ``WRITE_INTERVAL_S`` per event per venue, a
transition INTO a hold at once (a reader keeps the newest value it has seen,
so an over-claim it read before the hold landed would stick). One Redis hash
per event, one field per venue, never on a buffer lock and never a DB write.

READER. ``routes/event_stream.py`` reads through one process-wide cache, at
most one Redis read per event per ``READ_TTL_S`` however many streams watch
it, and adds the value to its named heartbeat.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from datetime import datetime, timezone
from typing import Any, Callable, Iterable, Optional

logger = logging.getLogger(__name__)

#: At most one Redis write per event per venue per this long (the contract's
#: throttle). The first write after a change lands within one interval.
WRITE_INTERVAL_S = 1.0
#: A hash outlives the longest stream connection (`MAX_CONNECTION_S`).
KEY_TTL_S = 900
#: A held entry is rewritten this often while it stays held, so a reader can
#: tell a live hold from one whose writer died (`HELD_FRESH_S`).
HELD_REFRESH_S = 20.0
#: A reader ignores ``h`` from an entry not rewritten within this long.
HELD_FRESH_S = 60.0
#: A batch that never resolved stops freezing its events after this long.
BUSY_MAX_S = 60.0
#: An unknown event (this run has nothing published to compare) reports a hold
#: until this long after its LATER of entering that state and its source's
#: last input: it covers a restart's first flush, and a source still quoting
#: something nobody has published keeps capping; one that never stamps and
#: goes quiet cannot cap the other venue for the whole game.
UNKNOWN_HOLD_S = 30.0
#: A committed stamp whose publication was never acknowledged (a lost task)
#: stops holding as "awaiting" after this long and becomes unknown.
AWAITING_MAX_S = 60.0
#: Events kept per venue process; the least recently touched go first.
MAX_EVENTS = 2000
#: Write and read deadlines (seconds).
WRITE_DEADLINE_S = 1.0
READ_DEADLINE_MS = 250
#: The reader's per-event cache lifetime (seconds).
READ_TTL_S = 1.0

#: Dispositions whose reading equals what this source has published: a stamp
#: published it; the others compared equal to the last stamp and published
#: nothing new (`LiveBlendRefresher._refresh_batch`).
AGREEING = frozenset({"stamped", "unchanged", "preview_only", "unobserved"})
#: Dispositions after which this source speaks for nothing on the event.
SILENT_DISPOSITIONS = frozenset({"no_reading", "no_row", "no_market"})
#: Statuses whose streams exist (`event_stream.QUOTE_STATUSES`).
STREAMED_STATUSES = frozenset({"live", "scheduled", "suspended"})

_SILENT = "silent"


def confirmed_key(event_id: int) -> str:
    """The Redis hash holding one event's per-venue confirmation entries."""
    return f"live:confirmed:{int(event_id)}"


def _p6(value) -> Optional[float]:
    try:
        return round(float(value), 6)
    except (TypeError, ValueError):
        return None


def _ms(wall: Optional[float]) -> Optional[int]:
    return None if wall is None else int(wall * 1000)


def _stamp_wall(stamped_at) -> Optional[float]:
    """The stamp's database write clock (the frame's ``updated_at``)."""
    if isinstance(stamped_at, datetime):
        parsed = stamped_at
    else:
        try:
            parsed = datetime.fromisoformat(str(stamped_at))
        except (TypeError, ValueError):
            return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.timestamp()


def iso(epoch_s: Optional[float]) -> Optional[str]:
    if epoch_s is None:
        return None
    return datetime.fromtimestamp(epoch_s, timezone.utc).isoformat(timespec="milliseconds")


class _Event:
    __slots__ = ("pub", "latest", "confirmed", "held_since", "unknown_since",
                 "busy_until", "previewing", "frozen_until", "touched",
                 "written", "written_at", "awaiting", "awaiting_until",
                 "awaiting_wall", "last_input")

    def __init__(self) -> None:
        #: None = this run has not published a reading; `_SILENT` = the last
        #: reading said this source speaks for nothing; else {outcome: p6}.
        self.pub: Any = None
        #: outcome -> (p6, recv wall) of its newest input.
        self.latest: dict[int, tuple[float, float]] = {}
        self.confirmed: Optional[float] = None
        self.held_since: Optional[float] = None
        self.unknown_since: Optional[float] = None
        self.busy_until: Optional[float] = None
        self.previewing = False
        self.frozen_until: Optional[float] = None
        self.touched = 0.0
        self.written: Optional[tuple] = None
        self.written_at: Optional[float] = None
        #: The revision of a committed stamp whose frame the publisher has not
        #: yet acknowledged, and when that wait gives up (mono).
        self.awaiting: Optional[int] = None
        self.awaiting_until: Optional[float] = None
        #: That stamp's write clock: its publication instant once acknowledged.
        self.awaiting_wall: Optional[float] = None
        #: The newest input's receipt (wall), whatever it agreed with.
        self.last_input: Optional[float] = None


class ConfirmedAt:
    """One venue process's confirmation state (module doc).

    ``client`` returns the async Redis client to write on (the refresher's
    own, so this is not a new pool). ``refutes(outcome_id, p)`` is the
    venue's pending-change check beyond inputs: Polymarket passes "a buffered
    withdrawal's book prices p out".
    """

    def __init__(self, source: str, *, client: Optional[Callable[[], Any]] = None,
                 refutes: Optional[Callable[[int, float], bool]] = None,
                 mono: Callable[[], float] = time.monotonic,
                 wall: Callable[[], float] = time.time,
                 preview_ttl_s: Optional[float] = None) -> None:
        self.source = source
        self._client = client
        self.refutes = refutes
        self._mono = mono
        self._wall = wall
        if preview_ttl_s is None:
            from app.utils.blend_preview import _max_uncommitted_s

            preview_ttl_s = _max_uncommitted_s()
        self.preview_ttl_s = preview_ttl_s
        self._events: dict[int, _Event] = {}
        #: event -> {outcome: price} staged by `note_basis` for `resolved`.
        self._basis: dict[int, dict] = {}
        #: event -> (revision, acknowledged): a publisher answer that came
        #: BEFORE its batch resolved (the singleton refresh publishes inline,
        #: then `TailReceipts.resolve` runs), kept for that `resolved`.
        self._early: dict[int, tuple[int, bool]] = {}
        self._dirty: set[int] = set()
        #: Events whose entry just went INTO a hold: written at once.
        self._urgent: set[int] = set()
        self._wake: Optional[asyncio.Event] = None
        self._task: Optional[asyncio.Task] = None
        self._closed = False
        self.stats = {"writes": 0, "write_errors": 0, "advanced": 0, "pruned": 0}

    # ── the socket's side (under its buffer lock: no await, no I/O) ─────────

    def note_input(self, event_id: Optional[int], outcome_id: int,
                   probability, recv_wall: float) -> None:
        """One accepted input for a headline outcome of ``event_id``."""
        p = _p6(probability)
        if event_id is None or p is None or self._closed:
            return
        state = self._state(event_id)
        if (state.pub is None and state.unknown_since is not None
                and recv_wall - max(state.unknown_since, state.last_input or 0.0)
                > UNKNOWN_HOLD_S):
            # The unknown hold had lapsed (the source went quiet); speaking
            # again while still unknown starts a new one, here (R5).
            state.unknown_since = recv_wall
        state.latest[outcome_id] = (p, recv_wall)
        if state.last_input is None or recv_wall > state.last_input:
            state.last_input = recv_wall
        agreed = (isinstance(state.pub, dict) and state.pub.get(outcome_id) == p)
        self._settle(event_id, state, recv_wall if agreed else None, recv_wall)

    def note_mark(self, mark) -> None:
        """`note_input` from a `TailReceipts` input mark (its receipt instant)."""
        if mark is None:
            return
        recv = getattr(mark, "recv_wall", None)
        if recv is not None:
            self.note_input(getattr(mark, "event_id", None), getattr(mark, "outcome_id", None),
                            getattr(mark, "probability", None), recv)

    def note_withdrawal(self, event_id: Optional[int], outcome_id: int) -> None:
        """A withdrawal was buffered for a headline outcome (Polymarket)."""
        state = self._events.get(event_id) if event_id is not None else None
        if state is not None and not self._closed:
            self._settle(event_id, state, None, self._wall())

    # ── the refresher's side ─────────────────────────────────────────────────

    def begin(self, event_ids: Iterable[int], previewing: Iterable[int] = ()) -> None:
        """A refresh batch takes these events: until it resolves, a preview or
        stamp it makes may publish, so nothing it holds is confirmed."""
        if self._closed:
            return
        previewing = set(previewing)
        now, wall = self._mono(), self._wall()
        for event_id in event_ids:
            state = self._events.get(event_id)
            if state is None:
                continue
            state.busy_until = now + BUSY_MAX_S
            state.previewing = event_id in previewing
            self._settle(event_id, state, None, wall)

    def note_basis(self, event_id: int, rows: Iterable[Any]) -> None:
        """The rows a reading with an agreeing disposition blended (its
        ``contributing_outcomes``: ``id`` + ``current_probability``, a held
        quote's overlay included). Taken by that batch's `resolved`."""
        if self._closed:
            return
        basis = {}
        for row in rows:
            oid = getattr(row, "id", None)
            if oid is None:
                self._basis.pop(event_id, None)
                return  # a blended row we cannot name cannot be agreed with
            basis[int(oid)] = getattr(row, "current_probability", None)
        if basis:
            self._basis[event_id] = basis
        else:
            self._basis.pop(event_id, None)

    def resolved(self, event_id: int, disposition: tuple) -> None:
        """The batch that took ``event_id`` committed with ``disposition``."""
        basis = self._basis.pop(event_id, None)
        if self._closed:
            return
        kind = disposition[0] if disposition else None
        state = self._events.get(event_id)
        if state is None:
            if kind not in AGREEING or not basis:
                return
            state = self._state(event_id)
        now, wall = self._mono(), self._wall()
        previewing, state.previewing, state.busy_until = state.previewing, False, None
        published = None
        if kind in AGREEING and basis:
            pub = {int(oid): _p6(p) for oid, p in basis.items()}
            if any(p is None for p in pub.values()):
                state.pub = None
            else:
                state.pub = pub
            if kind == "stamped":
                # A stamp supersedes any preview of this source on the event.
                state.frozen_until = None
                published = _stamp_wall(disposition[2]) if len(disposition) > 2 else None
                status = disposition[5] if len(disposition) > 5 else None
                if status is not None and status not in STREAMED_STATUSES:
                    self._drop(event_id)
                    return
                rev = disposition[4] if len(disposition) > 4 else None
                early = self._early.pop(event_id, None) if type(rev) is int else None
                if early is not None and early[0] >= rev:
                    if not early[1]:
                        # Its frame already failed to publish: unknown.
                        state.pub = None
                        published = None
                elif type(rev) is int:
                    # Committed, not yet on readers' screens: held until the
                    # publisher acknowledges this revision (`published`). A
                    # revision-less frame owes no acknowledgement.
                    state.awaiting = rev
                    state.awaiting_until = now + AWAITING_MAX_S
                    state.awaiting_wall = published
                    published = None  # not on readers' screens yet
        elif kind in SILENT_DISPOSITIONS and not previewing:
            state.pub = _SILENT
        else:
            # lock / stale / a reading that vanished after its preview: what
            # readers see is unknown until the next stamp.
            if kind != "lock":
                state.pub = None
            if previewing:
                state.frozen_until = now + self.preview_ttl_s
        candidate = None
        if isinstance(state.pub, dict):
            recvs = [state.latest[oid][1] for oid, p in state.pub.items()
                     if oid in state.latest and state.latest[oid][0] == p]
            candidate = max([*recvs, *([published] if published is not None else [])],
                            default=None)
        self._settle(event_id, state, candidate, wall)

    def unpublishable(self, event_id: int) -> None:
        """This attempt's frame could not be built: whatever it stamps, no
        reader receives it, so its batch resolves as unknown (no basis)."""
        self._basis.pop(event_id, None)

    def published(self, acknowledged: Iterable[tuple[int, int]],
                  unacknowledged: Iterable[tuple[int, int]] = ()) -> None:
        """The publisher's answer for committed stamp frames, as
        ``(event_id, revision)``: an acknowledged revision (or a newer one) is
        on readers' screens; an unacknowledged one is owed to recovery, so
        what readers show is unknown until this source's next stamp."""
        if self._closed:
            return
        wall = self._wall()
        if len(self._early) > 4 * MAX_EVENTS:
            self._early.clear()  # bounded; a lost answer gives up at AWAITING_MAX_S
        for event_id, rev in acknowledged:
            state = self._events.get(event_id)
            if state is None or state.awaiting is None:
                held = self._early.get(event_id)
                if held is None or rev >= held[0]:
                    self._early[event_id] = (rev, True)
                continue
            if rev < state.awaiting:
                continue
            stamp_wall, state.awaiting_wall = state.awaiting_wall, None
            state.awaiting = state.awaiting_until = None
            agreeing = self._agreeing_recv(state)
            candidates = [c for c in (agreeing, stamp_wall) if c is not None]
            self._settle(event_id, state, max(candidates, default=None), wall)
        for event_id, rev in unacknowledged:
            state = self._events.get(event_id)
            if state is None or state.awaiting is None:
                held = self._early.get(event_id)
                if held is None or rev > held[0]:
                    self._early[event_id] = (rev, False)
                continue
            if rev < state.awaiting:
                continue
            state.awaiting = state.awaiting_until = state.awaiting_wall = None
            state.pub = None
            self._settle(event_id, state, None, wall)

    def _agreeing_recv(self, state: _Event) -> Optional[float]:
        if not isinstance(state.pub, dict):
            return None
        return max((state.latest[oid][1] for oid, p in state.pub.items()
                    if oid in state.latest and state.latest[oid][0] == p), default=None)

    def failed(self, event_ids: Iterable[int]) -> None:
        """The batch did not commit: no stamp landed, a preview may have."""
        if self._closed:
            return
        now, wall = self._mono(), self._wall()
        for event_id in event_ids:
            self._basis.pop(event_id, None)
            state = self._events.get(event_id)
            if state is None:
                continue
            state.busy_until = None
            if state.previewing:
                state.frozen_until = now + self.preview_ttl_s
            state.previewing = False
            self._settle(event_id, state, None, wall)

    def close(self) -> None:
        """The consumer is exiting; the next run starts from nothing."""
        self._closed = True
        task, self._task = self._task, None
        if task is not None and not task.done():
            task.cancel()

    # ── state ────────────────────────────────────────────────────────────────

    def _state(self, event_id: int) -> _Event:
        state = self._events.get(event_id)
        if state is None:
            if len(self._events) >= MAX_EVENTS:
                oldest = min(self._events, key=lambda eid: self._events[eid].touched)
                self._drop(oldest)
                self.stats["pruned"] += 1
            state = self._events[event_id] = _Event()
        state.touched = self._mono()
        return state

    def _drop(self, event_id: int) -> None:
        self._events.pop(event_id, None)
        self._basis.pop(event_id, None)
        self._early.pop(event_id, None)
        self._dirty.discard(event_id)

    def agrees(self, state: _Event) -> bool:
        """Every published leg's newest input equals it, and nothing is open."""
        if not isinstance(state.pub, dict) or not state.pub:
            return False
        now = self._mono()
        if state.busy_until is not None:
            if now < state.busy_until:
                return False
            state.busy_until = None
        if state.frozen_until is not None:
            if now < state.frozen_until:
                return False
            state.frozen_until = None
        if state.awaiting is not None:
            if state.awaiting_until is not None and now < state.awaiting_until:
                return False
            # The acknowledgement never came: readers' copy is unknown.
            state.awaiting = state.awaiting_until = state.awaiting_wall = None
            state.pub = None
            return False
        for oid, p in state.pub.items():
            seen = state.latest.get(oid)
            if seen is not None and seen[0] != p:
                return False
            if self.refutes is not None:
                try:
                    if self.refutes(oid, p):
                        return False
                except Exception:
                    return False  # cannot check it, cannot confirm it
        return True

    def _settle(self, event_id: int, state: _Event, candidate: Optional[float],
                at: float) -> None:
        if state.pub == _SILENT:
            state.held_since = state.unknown_since = None
        elif state.pub is None:
            if state.unknown_since is None:
                state.unknown_since = at
        else:
            state.unknown_since = None
            if self.agrees(state):
                state.held_since = None
                if candidate is not None and (state.confirmed is None
                                              or candidate > state.confirmed):
                    state.confirmed = candidate
                    self.stats["advanced"] += 1
            elif state.held_since is None:
                state.held_since = at
        self._mark(event_id, state)

    def report(self, state: _Event, wall: float) -> tuple:
        """(c, h) as written: agreement and hold-start, epoch ms."""
        if state.pub == _SILENT:
            return (None, None)
        if state.pub is None:
            since = state.unknown_since
            spoke = max(since, state.last_input or since) if since is not None else None
            held = since if spoke is not None and wall - spoke <= UNKNOWN_HOLD_S else None
            return (_ms(state.confirmed), _ms(held))
        return (_ms(state.confirmed), _ms(state.held_since))

    def _lasting_hold(self, state: _Event) -> bool:
        """A hold that lasts until something else happens: a different input,
        a refuting book, nothing comparable (unknown), a failed preview still
        on screens. An open batch or an unacknowledged frame ends within the
        batch's own commit and publication, so it keeps the advance throttle
        (a stamp would otherwise cost an extra write every time)."""
        if state.pub is None:
            return True
        if not isinstance(state.pub, dict):
            return False
        if state.frozen_until is not None and self._mono() < state.frozen_until:
            return True
        for oid, p in state.pub.items():
            seen = state.latest.get(oid)
            if seen is not None and seen[0] != p:
                return True
            if self.refutes is not None:
                try:
                    if self.refutes(oid, p):
                        return True
                except Exception:
                    return True
        return False

    def _mark(self, event_id: int, state: _Event) -> None:
        report = self.report(state, self._wall())
        if state.written != report:
            self._dirty.add(event_id)
            if (report[1] is not None and (state.written is None or state.written[1] is None)
                    and self._lasting_hold(state)):
                # Into a hold: written now, not after the advance throttle.
                self._urgent.add(event_id)
                if self._wake is not None:
                    self._wake.set()
            self._kick()

    # ── the writer ───────────────────────────────────────────────────────────

    def take_due(self, only: Optional[set] = None) -> Optional[list[tuple[int, str]]]:
        """Entries to write now: changed ones, and holds due a refresh. None
        when nothing is dirty or held (the writer may stop). ``only``: just
        these events (a transition into a hold, written between ticks)."""
        wall = self._wall()
        due, live = [], False
        if only is not None:
            for event_id in only:
                state = self._events.get(event_id)
                if state is None:
                    continue
                report = self.report(state, wall)
                if report[1] is not None and report != state.written:
                    # Still held when the writer runs; otherwise it waits for
                    # the tick like any advance.
                    state.written, state.written_at = report, wall
                    self._dirty.discard(event_id)
                    due.append((event_id, json.dumps(
                        {"c": report[0], "h": report[1], "w": _ms(wall)},
                        separators=(",", ":"))))
            return due
        for event_id, state in self._events.items():
            report = self.report(state, wall)
            held = report[1] is not None or state.written is not None and state.written[1] is not None
            if held:
                live = True
            if (event_id in self._dirty or report != state.written
                    or held and (state.written_at is None
                                 or wall - state.written_at >= HELD_REFRESH_S)):
                state.written, state.written_at = report, wall
                due.append((event_id, json.dumps(
                    {"c": report[0], "h": report[1], "w": _ms(wall)},
                    separators=(",", ":"))))
        self._dirty.clear()
        if not due and not live:
            return None
        return due

    def _kick(self) -> None:
        if self._task is not None or self._closed or self._client is None:
            return
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return
        self._task = loop.create_task(self._writer(), name=f"confirmed-at-{self.source}")

    async def _writer(self) -> None:
        clock = asyncio.get_running_loop().time
        try:
            tick = clock() + WRITE_INTERVAL_S
            while not self._closed:
                if self._urgent:
                    # A transition into a hold: written now, alone; the advance
                    # throttle's tick keeps its own time.
                    urgent, self._urgent = self._urgent, set()
                    due = self.take_due(urgent)
                    if due:
                        await self._write(due)
                    continue
                wait = tick - clock()
                if wait > 0:
                    self._wake = asyncio.Event()
                    try:
                        await asyncio.wait_for(self._wake.wait(), timeout=wait)
                        continue  # woken by a hold: write it first
                    except asyncio.TimeoutError:
                        pass
                    finally:
                        self._wake = None
                tick = clock() + WRITE_INTERVAL_S
                due = self.take_due()
                if due is None:
                    return
                if due:
                    await self._write(due)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.warning("confirmed_at[%s]: writer stopped", self.source, exc_info=True)
        finally:
            if self._task is asyncio.current_task():
                self._task = None
                if self._dirty and not self._closed:
                    self._kick()

    async def _write(self, due: list[tuple[int, str]]) -> None:
        try:
            client = self._client()
            pipe = client.pipeline(transaction=False)
            for event_id, payload in due:
                key = confirmed_key(event_id)
                pipe.hset(key, self.source, payload)
                pipe.expire(key, KEY_TTL_S)
            await asyncio.wait_for(pipe.execute(), timeout=WRITE_DEADLINE_S)
            self.stats["writes"] += len(due)
        except asyncio.CancelledError:
            raise
        except Exception:
            # Not written: rewrite on the next tick. Evidence only, so loud
            # once and then counted, never raised into a price path.
            self.stats["write_errors"] += 1
            for event_id, _payload in due:
                state = self._events.get(event_id)
                if state is not None:
                    state.written = state.written_at = None
                    self._dirty.add(event_id)
            if self.stats["write_errors"] in (1, 10) or self.stats["write_errors"] % 1000 == 0:
                logger.warning("confirmed_at[%s]: write failed (errors=%d)",
                               self.source, self.stats["write_errors"], exc_info=True)


# ── the reader (web dyno) ────────────────────────────────────────────────────


def combine(entries: Iterable[Any], now_wall: float) -> Optional[float]:
    """The event's ``confirmed_at`` (epoch s) from venue entries, or None.

    The newest agreement any venue reports, never past the earliest hold a
    live writer reports: an agreement after a hold began is not an agreement
    with the event, because the held venue has a newer, different price. A
    venue's agreement from before the hold is unknown once overwritten, so
    only agreements at or before the hold count (it understates, never
    overstates). Clamped to the reader's clock.
    """
    now_ms = int(now_wall * 1000)
    agreed, holds = [], []
    for raw in entries:
        try:
            entry = json.loads(raw) if isinstance(raw, (str, bytes)) else raw
        except (TypeError, ValueError):
            continue
        if not isinstance(entry, dict):
            continue
        c, h, w = entry.get("c"), entry.get("h"), entry.get("w")
        if type(c) is int:
            agreed.append(c)
        if type(h) is int and type(w) is int and now_ms - w <= HELD_FRESH_S * 1000:
            holds.append(h)
    if holds:
        cap = min(holds)
        agreed = [c for c in agreed if c <= cap]
    if not agreed:
        return None
    return min(max(agreed), now_ms) / 1000.0


async def _fetch(event_ids: list[int]) -> Optional[dict[int, list]]:
    from app.utils.request_cache import bounded_redis_call, get_shared_async_redis

    try:
        client = await get_shared_async_redis()

        async def read():
            pipe = client.pipeline(transaction=False)
            for event_id in event_ids:
                pipe.hgetall(confirmed_key(event_id))
            return await pipe.execute()

        result = await bounded_redis_call(read, deadline_ms=READ_DEADLINE_MS)
    except asyncio.CancelledError:
        raise
    except Exception:
        return None
    if not result.is_ok or not isinstance(result.value, (list, tuple)):
        return None
    out = {}
    for event_id, mapping in zip(event_ids, result.value):
        out[event_id] = list((mapping or {}).values()) if isinstance(mapping, dict) else []
    return out


class ConfirmedReads:
    """Process-wide read-through cache: streams share one read per event."""

    MAX_EVENTS = 5000

    def __init__(self, fetch=_fetch, *, mono: Callable[[], float] = time.monotonic,
                 wall: Callable[[], float] = time.time) -> None:
        self._fetch = fetch
        self._mono = mono
        self._wall = wall
        self._entries: dict[int, tuple[float, list]] = {}
        self._inflight: dict[int, asyncio.Task] = {}
        self._loop = None

    def _bind_loop(self) -> bool:
        """Reads and their tasks belong to one event loop; a new loop (a
        worker restart, a test) starts from an empty cache."""
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return False
        if loop is not self._loop:
            self._loop, self._entries, self._inflight = loop, {}, {}
        return True

    def _stale(self, event_ids) -> list[int]:
        if not self._bind_loop():
            return []
        now = self._mono()
        return [eid for eid in event_ids
                if eid not in self._inflight
                and (eid not in self._entries or now - self._entries[eid][0] >= READ_TTL_S)]

    def _refresh(self, event_ids: list[int]) -> Optional[asyncio.Task]:
        if not event_ids:
            return None
        task = self._loop.create_task(self._read(event_ids))
        for eid in event_ids:
            self._inflight[eid] = task
        return task

    async def _read(self, event_ids: list[int]) -> None:
        try:
            got = await self._fetch(event_ids)
            now = self._mono()
            if len(self._entries) > self.MAX_EVENTS:
                self._entries = {eid: v for eid, v in self._entries.items()
                                 if now - v[0] < 60.0}
            for eid in event_ids:
                if got is not None:
                    self._entries[eid] = (now, got.get(eid, []))
                else:
                    # A failed read is still an attempt (lane1 S2): what was
                    # known stays, and the next read waits READ_TTL_S, not
                    # the next stream pass, while Redis is down.
                    previous = self._entries.get(eid)
                    self._entries[eid] = (now, previous[1] if previous else [])
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.debug("confirmed_at: read failed", exc_info=True)
        finally:
            for eid in event_ids:
                if self._inflight.get(eid) is asyncio.current_task():
                    del self._inflight[eid]

    def value(self, event_ids) -> Optional[float]:
        entries = []
        for eid in event_ids:
            cached = self._entries.get(eid)
            if cached is not None:
                entries.extend(cached[1])
        return combine(entries, self._wall())

    def peek(self, event_ids) -> Optional[float]:
        """The cached value now; a stale entry starts one shared re-read."""
        self._refresh(self._stale(event_ids))
        return self.value(event_ids)

    async def current(self, event_ids, timeout_s: float) -> Optional[float]:
        """Wait up to ``timeout_s`` for a fresh read (connect only)."""
        self._refresh(self._stale(event_ids))
        tasks = {self._inflight[eid] for eid in event_ids if eid in self._inflight}
        if tasks:
            await asyncio.wait(tasks, timeout=timeout_s)
        return self.value(event_ids)


_READS: Optional[ConfirmedReads] = None


def confirmed_reads() -> ConfirmedReads:
    global _READS
    if _READS is None:
        _READS = ConfirmedReads()
    return _READS


def reset_reads_for_tests() -> None:
    global _READS
    _READS = None
