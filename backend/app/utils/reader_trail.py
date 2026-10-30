"""#10090 — what a live game's readers still lack, judged at each publication (log only).

THE SHIP. Alex sees, every 5 minutes, the total seconds live game pages spent
trailing a newer price our server already held, plus the single worst case.

THE METRIC (speed, 2026-10-30 04:18Z), server half:

* an input is ELIGIBLE when it would change the blended value readers are
  shown;
* the server TRAILS from our socket's receipt of the oldest eligible input
  readers do not have yet, until the first publication that carries it to
  readers: a DNPL preview, a stamp, or any writer's revision that includes it;
* TOTAL is the union of those intervals per event (each second counts once),
  WORST the longest single interval.

WHAT THIS CLASS ANSWERS, per publication: ``first_new_recv``, the receipt
instant of the oldest eligible input THIS publication is the first to carry to
readers, or None when it carries no change readers lacked. The receipt lines
(`TailReceipts`) print it; `app.utils.trailing_readout` folds them.

HOW IT DECIDES, one consumer process, one source, per LIVE event:

* every accepted input whose price differs from the previous input for that
  outcome (or is the first of the run) joins the event's trail — a repeat
  cannot change anything;
* an input is COMMITTED once its price row has committed: the flush's
  RETURNING row carries the input's price (`note_committed_rows`, matched to
  the newest trail input of that outcome at that price, which also covers the
  older ones it superseded), or a stamp's staged mark has reached it
  (`note_flushed`);
* a published PREVIEW blend carries every committed input not yet shown; a
  STAMP carries every input up to its staged mark (or, with no mark, every
  committed one), and retires them;
* a publication's ``first_new_recv`` is the oldest not-yet-shown input it
  carries, but only when its value differs from the last value this process
  PUBLISHED to readers by preview or stamp. So a stamp that follows its own
  preview reads None: the preview already showed those inputs;
* a published REVOKE drops readers back to the committed value: the shown
  value becomes the last stamped one, and inputs only the revoked preview had
  shown rejoin the trail from the revoke instant (readers lack them again from
  then, not from their receipt);
* a preview composed on a revision older than one this process stamped is
  ignored by readers holding that stamp: it carries nothing, and changes no
  state.

LIMITS, stated so a reader of the number can bound it:

* eligibility is judged on the frame's ``p`` (the headline blend), exact to
  ``VALUE_EPSILON``; a move too small to change the rendered digits still
  counts as a change;
* "last published" is this process's own: production runs each venue in its
  own process (``WS_VENUE_PROCESSES=1``), and the sportsbook/model writers in
  the Celery worker. Another process's publication is not seen here, so a
  value it already showed can be claimed again. ``total_s`` is an upper bound
  under this limit. The union removes overlap, not an interval that ran past
  the publication that actually carried the input;
* a headline leg whose own change did not move ``p`` can still be the oldest
  input a later publication carries, if none retired it first (bounded by its
  own queued stamp);
* a preview published after a LATER flush's commit was noted covers that
  flush's inputs too (understates by at most one flush); an input re-sent at
  the same price as the committed row is matched to the commit (understates);
* more than ``TRAIL_MAX_PENDING`` unshown inputs on one event drops the
  oldest, counted (understates);
* the chart's served line has no server-side publication of its own (pages
  read it from stored history on request), so this receipt times the headline
  only and claims nothing about the chart.

Pure bookkeeping: no await, no I/O, no clock of its own (callers pass walls).
"""

from __future__ import annotations

from collections import deque
from typing import Iterable, Optional

#: Unshown trail inputs kept per live event; a publication normally takes them
#: all within a flush. Past it the oldest is dropped and counted.
TRAIL_MAX_PENDING = 512
#: Two frame values closer than this are the same value to a reader.
VALUE_EPSILON = 1e-9
#: A committed row's price and the input that set it are the same float in the
#: Kalshi writer; Polymarket rounds to 6 places on the way.
COMMITTED_PRICE_TOLERANCE = 1e-6


class _Input:
    __slots__ = ("seq", "since", "outcome_id", "probability", "committed", "shown")

    def __init__(self, seq: int, since: float, outcome_id: int, probability: float) -> None:
        self.seq = seq
        #: When readers began lacking it: its receipt, or the revoke that took
        #: the preview carrying it back off the page.
        self.since = since
        self.outcome_id = outcome_id
        self.probability = probability
        self.committed = False
        self.shown = False


class _EventTrail:
    __slots__ = ("inputs", "shown_p", "stamp_p", "stamp_rev", "dropped", "outcomes")

    def __init__(self) -> None:
        self.inputs: deque[_Input] = deque()
        #: The last value this process published to readers (preview or stamp).
        self.shown_p: Optional[float] = None
        #: The last committed value: what readers fall back to on a revoke.
        self.stamp_p: Optional[float] = None
        self.stamp_rev: Optional[int] = None
        self.dropped = 0
        self.outcomes: set[int] = set()


def _int(value) -> Optional[int]:
    return value if type(value) is int else None


def _float(value) -> Optional[float]:
    if isinstance(value, bool) or value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


class ReaderTrail:
    """Per-event trail of inputs readers lack (module doc). One per source arm."""

    def __init__(self, max_pending: int = TRAIL_MAX_PENDING) -> None:
        self.max_pending = max_pending
        self._events: dict[int, _EventTrail] = {}
        self._outcome_event: dict[int, int] = {}

    def __contains__(self, event_id) -> bool:
        return event_id in self._events

    def dropped(self, event_id: int, *, reset: bool = False) -> int:
        trail = self._events.get(event_id)
        if trail is None:
            return 0
        count = trail.dropped
        if reset:
            trail.dropped = 0
        return count

    def _trail(self, event_id: int) -> _EventTrail:
        trail = self._events.get(event_id)
        if trail is None:
            trail = self._events[event_id] = _EventTrail()
        return trail

    def forget(self, event_id: int) -> None:
        """The event left the live set: nothing more is kept for it."""
        trail = self._events.pop(event_id, None)
        if trail is None:
            return
        for oid in trail.outcomes:
            if self._outcome_event.get(oid) == event_id:
                del self._outcome_event[oid]

    # ── inputs ───────────────────────────────────────────────────────────────

    def note_input(self, mark, changed: bool) -> None:
        """One accepted input of a live event; only a CHANGED price joins."""
        trail = self._trail(mark.event_id)
        if not changed:
            return
        if len(trail.inputs) >= self.max_pending:
            trail.inputs.popleft()
            trail.dropped += 1
        trail.inputs.append(_Input(mark.seq, mark.recv_wall, mark.outcome_id, mark.probability))
        trail.outcomes.add(mark.outcome_id)
        self._outcome_event[mark.outcome_id] = mark.event_id

    def note_committed_rows(self, rows: Iterable) -> None:
        """A price write's committed RETURNING rows (``id``,
        ``current_probability``): per row, the newest trail input of that
        outcome at the stored price, and every older input of the outcome, are
        committed. A row matching no input commits nothing."""
        for row in rows:
            oid = getattr(row, "id", None)
            price = _float(getattr(row, "current_probability", None))
            event_id = self._outcome_event.get(oid)
            trail = self._events.get(event_id) if event_id is not None else None
            if trail is None or price is None:
                continue
            match = None
            for item in reversed(trail.inputs):
                if (item.outcome_id == oid
                        and abs(item.probability - price) <= COMMITTED_PRICE_TOLERANCE):
                    match = item.seq
                    break
            if match is None:
                continue
            for item in trail.inputs:
                if item.outcome_id == oid and item.seq <= match:
                    item.committed = True

    def note_flushed(self, event_id: int, seq: int) -> None:
        """A flush staged its newest committed input of this event at ``seq``."""
        trail = self._events.get(event_id)
        if trail is None:
            return
        for item in trail.inputs:
            if item.seq <= seq:
                item.committed = True

    # ── publications ─────────────────────────────────────────────────────────

    def _carry(self, trail: _EventTrail, p: Optional[float], carried: list) -> Optional[float]:
        moved = p is not None and (
            trail.shown_p is None or abs(p - trail.shown_p) > VALUE_EPSILON
        )
        first = min((item.since for item in carried), default=None) if moved else None
        if p is not None:
            trail.shown_p = p
        return first

    def preview(self, event_id: int, p, base_rev) -> tuple[bool, Optional[float]]:
        """A preview blend readers were sent. Returns ``(seen, first_new_recv)``:
        ``seen`` is False when readers holding this process's newest stamp
        ignore it (composed on an older revision), and then nothing changes."""
        trail = self._events.get(event_id)
        if trail is None:
            return False, None
        base, stamped = _int(base_rev), trail.stamp_rev
        if base is not None and stamped is not None and base < stamped:
            return False, None
        carried = [item for item in trail.inputs if item.committed and not item.shown]
        first = self._carry(trail, _float(p), carried)
        for item in carried:
            item.shown = True
        return True, first

    def revoke(self, event_id: int, wall: float) -> None:
        """A preview withdrawal readers were sent: they fall back to the
        committed value, and lack again what only the preview had shown."""
        trail = self._events.get(event_id)
        if trail is None:
            return
        trail.shown_p = trail.stamp_p
        for item in trail.inputs:
            if item.shown:
                item.shown = False
                item.since = wall

    def stamp(self, event_id: int, p, rev, mark_seq: Optional[int]) -> Optional[float]:
        """A committed stamp's frame: carries every input up to ``mark_seq``
        (its staged mark), or with no mark every committed input, and retires
        them. Returns ``first_new_recv``."""
        trail = self._events.get(event_id)
        if trail is None:
            return None
        rev = _int(rev)
        if rev is not None and (trail.stamp_rev is None or rev > trail.stamp_rev):
            trail.stamp_rev = rev
        if mark_seq is not None:
            covered = [item for item in trail.inputs if item.seq <= mark_seq]
        else:
            covered = [item for item in trail.inputs if item.committed]
        value = _float(p)
        first = self._carry(trail, value, [item for item in covered if not item.shown])
        if value is not None:
            trail.stamp_p = value
        if covered:
            gone = {id(item) for item in covered}
            trail.inputs = deque(item for item in trail.inputs if id(item) not in gone)
        return first

    def revision(self, event_id: int, rev) -> None:
        """Another writer of this process advanced the revision with a frame
        that carries no value (an invalidation: readers refetch). What readers
        now show is unknown here, so the next carrying publication counts as a
        change."""
        trail = self._events.get(event_id)
        if trail is None:
            return
        rev = _int(rev)
        if rev is not None and (trail.stamp_rev is None or rev > trail.stamp_rev):
            trail.stamp_rev = rev
        trail.shown_p = trail.stamp_p = None
