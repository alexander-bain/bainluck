"""#10090 — a provisional blend published BEFORE its event stamp commits.

OFF BY DEFAULT, AND THEN ONLY FOR NAMED EVENTS FROM ONE NAMED SOURCE. Nothing
here runs unless the process sets BOTH ``LIVE_BLEND_PREVIEW_SOURCE`` (``kalshi``
or ``polymarket``) and ``LIVE_BLEND_PREVIEW_EVENT_IDS`` (comma-separated event
ids). Unset, malformed or empty, the worker publishes exactly the committed
frames it always did and the stream route forwards nothing new. Turning the
switch on is a production activation decision; landing this code is not one.

Why it exists. A held event page only moves when the WS lane's
``UPDATE events SET win_probability_sources = …`` commits. When another
transaction holds that row, every attempt waits out its lock budget, requeues,
and the page shows nothing new until a stamp finally lands. The reading itself
— estimator, orientation, eligibility, weights — was already computed before
the UPDATE. This module lets that reading be shown while persistence keeps
retrying, without pretending it was stored.

The contract (``preview`` frames, never ``probability`` frames):

* A preview frame has NO ``rev``. It is never given a committed revision, so
  it goes out as a plain PUBLISH: never retained, never replayed to a new
  stream, never ordered with committed frames by rev.
* It carries its own identity: ``epoch`` (this process's fence claim, below)
  and ``seq`` (strictly increasing within the epoch).
* ``base_rev`` is the committed ``win_probability_sources_rev`` the preview's
  bag was composed on. A reader shows a preview only while it holds no newer
  committed revision; a newer commit always wins, whoever wrote it.
* ``pending`` names the uncommitted source values folded in. The composed bag
  is the newest committed bag this process knows, with every pending source
  merged by `aggregation.stamp_source_reading` and the aggregate from
  `compute_aggregate_probability`, the same call the committed frame uses.
  That merge is unconditional; the SQL stamp is not (#8910,
  `observation_admits_clause`). So every composition first drops any pending
  source whose reading `reading_regresses_stored_observation` against the
  base it is composed on — the row this arm read, or a sibling's RETURNING —
  so no value the database would refuse as stale is shown while a lock keeps
  the UPDATE from evaluating that clause.
* ``revoke`` frames withdraw a preview: the stamp was refused (a later stored
  observation), the reading disappeared or returned to the stored value, this
  source left the event's group read or was withdrawn, the event left a quote
  status, or the value stayed uncommitted past
  ``LIVE_BLEND_PREVIEW_MAX_UNCOMMITTED_S``. A reader that sees one falls back
  to its committed value.
* The uncommitted limit bounds one value across retries. Expiry leaves a
  per-source marker of the expired value, and the SAME value is not proposed
  again until a commit, a refusal or a different value ends that chain. The
  marker lives in the bounded per-event state (at most one per source), so
  eviction is the only thing that forgets it. It is NOT a cap on how long
  uncommitted values in total may stay on screen during one long hold.

Display authority across processes (the fence). Production runs each venue's
WS arm in its own process (``WS_VENUE_PROCESSES=1``), and a release overlaps
an old worker with its replacement. So exactly ONE source previews, and its
process must own the display before it may publish a blend:

* claim — one atomic script INCRs a global epoch counter and SETs the
  source's owner key to the result (`FENCE_CLAIM_SCRIPT`). A replacement's
  claim therefore supersedes the old worker at Redis, whatever order their
  frames would otherwise arrive in;
* offer — every batch goes through `FENCE_PUBLISH_SCRIPT`, which PUBLISHes a
  blend only while the owner key still holds this process's epoch. A
  superseded process's blends are dropped at Redis and counted as fenced.
  Revokes pass: they only take a provisional value off the page;
* a missing owner key fails closed (no blend is published) — it is never
  re-claimed from inside a running process;
* readers keep a monotonic epoch floor and refuse anything older
  (``frontend/lib/blendPreview.ts``), so an earlier epoch never regains the
  display, not even on a reader that missed the claim.

Cross-writer scope, stated plainly. The other venue's arm and every other
writer (the poll, the matcher, withdrawals) do not preview; their commits
reach the reader as newer committed revisions, which retire any preview
composed on an older base, and the preview arm's next attempt recomposes on
the freshly read row. No pending state is shared between processes.
"""

from __future__ import annotations

import itertools
import json
import math
import os
import time
from collections import OrderedDict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from types import SimpleNamespace
from typing import Any, Callable, Optional

SOURCE_ENV = "LIVE_BLEND_PREVIEW_SOURCE"
EVENT_IDS_ENV = "LIVE_BLEND_PREVIEW_EVENT_IDS"
MAX_UNCOMMITTED_ENV = "LIVE_BLEND_PREVIEW_MAX_UNCOMMITTED_S"
#: The arms that may preview (`LiveBlendRefresher.source`).
PREVIEW_SOURCES = frozenset({"kalshi", "polymarket"})
#: How long one uncommitted value may stay on a reader's screen. A concrete
#: product decision, not a measurement; the canary keeps the lab's number.
DEFAULT_MAX_UNCOMMITTED_S = 60.0
#: Latest-per-event state is bounded; the oldest event is revoked past this.
DEFAULT_MAX_EVENTS = 512
#: Statuses a quote stream serves (`routes/event_stream.QUOTE_STATUSES`).
PREVIEW_STATUSES = frozenset({"live", "scheduled", "suspended"})

#: The fence (module doc). One counter for every source, so epochs only rise.
FENCE_EPOCH_KEY = "live:blend_preview:epoch"
FENCE_OWNER_KEY_PREFIX = "live:blend_preview:owner:"
FENCE_CLAIM_SCRIPT = (
    "local epoch = redis.call('INCR', KEYS[1]) "
    "redis.call('SET', KEYS[2], epoch) "
    "return epoch"
)
#: ARGV = epoch, then (kind, channel, payload) per frame, in publication order.
#: Returns {published, fenced, owner-or-empty}.
FENCE_PUBLISH_SCRIPT = (
    "local owner = redis.call('GET', KEYS[1]) "
    "local published, fenced = 0, 0 "
    "for i = 2, #ARGV, 3 do "
    "if ARGV[i] == 'revoke' or owner == ARGV[1] then "
    "redis.call('PUBLISH', ARGV[i + 1], ARGV[i + 2]) published = published + 1 "
    "else fenced = fenced + 1 end "
    "end "
    "return {published, fenced, owner or ''}"
)


def fence_owner_key(source: str) -> str:
    return FENCE_OWNER_KEY_PREFIX + source


def preview_source() -> Optional[str]:
    """The one source allowed to preview, or None (the default: off)."""
    value = (os.environ.get(SOURCE_ENV) or "").strip()
    return value if value in PREVIEW_SOURCES else None


def preview_event_ids() -> frozenset:
    """The canary's events. Any malformed entry turns the whole list off."""
    raw = (os.environ.get(EVENT_IDS_ENV) or "").strip()
    if not raw:
        return frozenset()
    ids = set()
    for token in raw.split(","):
        token = token.strip()
        if not token.isdigit() or int(token) <= 0:
            return frozenset()
        ids.add(int(token))
    return frozenset(ids)


def preview_events_for(source: str) -> frozenset:
    """Events ``source``'s arm previews: empty unless it is THE preview source."""
    return preview_event_ids() if preview_source() == source else frozenset()


def preview_route_events() -> frozenset:
    """Events whose stream forwards previews: the canary's, once a source is named."""
    return preview_event_ids() if preview_source() is not None else frozenset()


def _max_uncommitted_s() -> float:
    try:
        value = float(os.environ.get(MAX_UNCOMMITTED_ENV, DEFAULT_MAX_UNCOMMITTED_S))
    except ValueError:
        return DEFAULT_MAX_UNCOMMITTED_S
    return value if value > 0 else DEFAULT_MAX_UNCOMMITTED_S


def _revision(value: Any) -> Optional[int]:
    return value if type(value) is int and value >= 0 else None


def _basis_observation_time(basis: Any) -> Optional[datetime]:
    """Date a complete contributing reading, never a persistence retry.

    The minimum is the existing oldest_observation_time contract. Reject an
    incomplete vector in full; filtering bad legs would overstate freshness.
    """
    if not isinstance(basis, dict) or not basis:
        return None
    if any(type(value) not in (int, float) or not math.isfinite(value)
           for value in basis.values()):
        return None
    try:
        return datetime.fromtimestamp(min(basis.values()), timezone.utc)
    except (ValueError, OverflowError, OSError):
        return None


@dataclass(frozen=True)
class _ChainLease:
    # TEST-ONLY additive protocol metadata, never a new observation clock.
    identity: int
    original_expires_at_ms: Optional[int]


@dataclass
class _Pending:
    value: float
    eligibility: Any
    observed_basis: Optional[dict]
    stamped_at: datetime
    seq: int
    #: Monotonic start of this source's uncommitted chain (kept across
    #: re-proposals until a commit, refusal or expiry ends the chain).
    since: float
    lease: _ChainLease


@dataclass
class _EventState:
    status: Optional[str] = None
    espn_win_prob_home: Any = None
    opening_home_probability: Any = None
    base_sources: Optional[dict] = None
    base_rev: Optional[int] = None
    pending: dict = field(default_factory=dict)
    #: source -> the value whose uncommitted chain expired. Not proposed again
    #: until a commit, a refusal or a different value ends the chain.
    expired: dict = field(default_factory=dict)
    #: Highest seq this process published for the event (blend or revoke).
    last_seq: int = 0


class PreviewRegistry:
    """Bounded latest-per-event pending state for one process (one fence epoch)."""

    def __init__(
        self,
        *,
        max_events: int = DEFAULT_MAX_EVENTS,
        max_uncommitted_s: Optional[float] = None,
        clock: Callable[[], float] = time.monotonic,
        wall_clock: Callable[[], float] = time.time,
        epoch: Optional[int] = None,
    ) -> None:
        #: This process's fence claim; None until `_publish_previews` claims.
        self.epoch = epoch
        self.claim_lock: Any = None
        self.max_events = max_events
        self.max_uncommitted_s = (
            _max_uncommitted_s() if max_uncommitted_s is None else max_uncommitted_s
        )
        self._clock = clock
        self._wall_clock = wall_clock
        self._chain_identity = itertools.count(1)
        self._seq = itertools.count(1)
        self._events: "OrderedDict[int, _EventState]" = OrderedDict()

    def _new_chain_lease(self, since: float) -> _ChainLease:
        identity = next(self._chain_identity)
        try:
            # Anchor once. Sampling monotonic AFTER wall time conservatively
            # charges time spent obtaining the pair. Server clock alignment is
            # still a protocol prerequisite, not established by this adapter.
            wall = self._wall_clock()
            after = self._clock()
            remaining = self.max_uncommitted_s - (after - since)
            expiry = math.floor(wall * 1000 + remaining * 1000) - 1
            if not (0 <= expiry <= 2**53 - 1) or after < since:
                expiry = None
        except Exception:
            expiry = None
        return _ChainLease(identity, expiry)

    def _chain_metadata(self, event_id: int, state: _EventState) -> dict:
        try:
            # Mirrors the producer's oldest-pending-since lease. A changed
            # probability, observation, seq or base is NOT a new chain.
            _, oldest = min(state.pending.items(), key=lambda item: (item[1].since, item[0]))
            expiry = oldest.lease.original_expires_at_ms
            issued = math.floor(self._wall_clock() * 1000)
            if expiry is None or not (0 <= issued <= 2**53 - 1):
                return {}
            return {"lease_id": "pending:" + str(oldest.lease.identity),
                    "original_expires_at_ms": expiry,
                    "lease_issued_at_ms": issued}
        except Exception:
            # Optional metadata must never suppress an independently accepted
            # live preview. Absence means live-only, not reconstructed expiry.
            return {}

    # ── state ────────────────────────────────────────────────────────────
    def _state(self, event_id: int) -> _EventState:
        state = self._events.get(event_id)
        if state is None:
            state = self._events[event_id] = _EventState()
        self._events.move_to_end(event_id)
        return state

    def _context(self, state: _EventState, event: Any) -> None:
        state.status = getattr(event, "status", None)
        state.espn_win_prob_home = getattr(event, "espn_win_prob_home", None)
        state.opening_home_probability = getattr(event, "opening_home_probability", None)

    def _adopt_base(self, state: _EventState, sources: Any, rev: Any) -> None:
        rev = _revision(rev)
        if rev is None or not isinstance(sources, dict):
            return
        if state.base_rev is None or rev > state.base_rev:
            state.base_rev = rev
            state.base_sources = dict(sources)

    def has_pending(self, event_id: int, source: Optional[str] = None) -> bool:
        state = self._events.get(event_id)
        if state is None:
            return False
        return bool(state.pending) if source is None else source in state.pending

    def pending_seq(self, event_id: int, source: str) -> Optional[int]:
        state = self._events.get(event_id)
        entry = state.pending.get(source) if state is not None else None
        return None if entry is None else entry.seq

    # ── composition ──────────────────────────────────────────────────────
    def _drop_regressed(self, state: _EventState) -> list[str]:
        """Drop each pending source the SQL stamp would refuse as stale (#8910).

        The base may be the row this arm read or a sibling's RETURNING; either
        can carry a later observation of the same rows (the poll or the
        matcher committed one), and under a row lock the UPDATE never gets to
        refuse it.
        """
        from app.utils.aggregation import reading_regresses_stored_observation

        stale = [name for name, entry in state.pending.items()
                 if reading_regresses_stored_observation(
                     state.base_sources, name, entry.observed_basis)]
        for name in stale:
            del state.pending[name]
        return stale

    def _compose(self, event_id: int, state: _EventState, source: str) -> Optional[dict]:
        from app.utils.aggregation import compute_aggregate_probability, stamp_source_reading

        # Every composition is guarded here; callers that need to say WHY a
        # preview went away drop first themselves (a second pass finds none).
        self._drop_regressed(state)
        if (state.base_rev is None or state.status not in PREVIEW_STATUSES
                or not state.pending):
            return None
        bag = dict(state.base_sources or {})
        for name, entry in state.pending.items():
            bag = stamp_source_reading(
                bag, name, entry.value, now=entry.stamped_at,
                eligibility=entry.eligibility, observed_basis=entry.observed_basis,
            )
        shim = SimpleNamespace(
            win_probability_sources=bag,
            status=state.status,
            espn_win_prob_home=state.espn_win_prob_home,
            opening_home_probability=state.opening_home_probability,
        )
        probability = compute_aggregate_probability(shim, state.status)
        if probability is None:
            return None
        now = self._clock()
        oldest = min(entry.since for entry in state.pending.values())
        ttl_ms = max(0, int((self.max_uncommitted_s - (now - oldest)) * 1000))
        seq = next(self._seq)
        state.last_seq = seq
        mover = state.pending.get(source) or next(iter(state.pending.values()))
        # A separate clock-only view preserves the probability/weighting bag
        # exactly. Pending stamps above are attempt times, not observations.
        # Committed siblings retain the clocks of this exact base revision.
        from app.utils.aggregation import newest_source_reading_time

        clock_bag = dict(bag)
        for name, entry in state.pending.items():
            observed = _basis_observation_time(entry.observed_basis)
            clock_bag[name] = {
                **bag[name],
                "updated_at": observed.isoformat() if observed is not None else None,
            }
        display_time = newest_source_reading_time(
            SimpleNamespace(win_probability_sources=clock_bag, status=state.status),
            state.status, require_complete=True,
        )
        # Folded readers need the exact policy inputs, not this row's scalar
        # aggregate. Round-trip a strict JSON copy so retained frame metadata
        # cannot alias the registry's committed base. Invalid legacy metadata
        # leaves singleton behavior intact and gives folded readers no claim.
        pending_entries = None
        try:
            pending_entries = json.loads(json.dumps(
                {name: bag[name] for name in sorted(state.pending)},
                allow_nan=False,
            ))
        except (TypeError, ValueError):
            pass
        return {
            "event_id": int(event_id),
            "p": float(probability),
            "status": state.status,
            "source": source,
            "source_value": float(mover.value),
            "observed_at": mover.stamped_at.isoformat(),  # legacy attempt clock
            # Additive contract: readers must not fall back to observed_at.
            "display_observed_at": display_time.isoformat() if display_time else None,
            "provisional": True,
            "preview": {
                "kind": "blend",
                "epoch": self.epoch,
                "seq": seq,
                "base_rev": state.base_rev,
                "ttl_ms": ttl_ms,
                **self._chain_metadata(event_id, state),
                "pending": {name: float(e.value) for name, e in sorted(state.pending.items())},
                "pending_entries_version": 1,
                "pending_entries": pending_entries,
            },
        }

    def _revoke_frame(self, event_id: int, state: _EventState, reason: str) -> Optional[dict]:
        if state.last_seq == 0:
            return None  # nothing was ever published for this event
        through = state.last_seq
        seq = next(self._seq)
        state.last_seq = seq
        return {
            "event_id": int(event_id),
            "p": None,
            "status": state.status,
            "provisional": True,
            "preview": {
                "kind": "revoke",
                "epoch": self.epoch,
                "seq": seq,
                "through_seq": through,
                "reason": reason,
            },
        }

    def _after_drop(self, event_id: int, state: _EventState, reason: str,
                    source: str) -> list[dict]:
        """A pending source left: recompose the rest, or revoke the event."""
        if self._drop_regressed(state) and not state.pending:
            reason = "stale"
        if state.pending:
            frame = self._compose(event_id, state, source)
            if frame is not None:
                return [frame]
            state.pending.clear()
        frame = self._revoke_frame(event_id, state, reason)
        return [] if frame is None else [frame]

    # ── writer API ───────────────────────────────────────────────────────
    def propose(
        self, event_id: int, source: str, *, value: float, event: Any,
        row_sources: Any, row_rev: Any, eligibility: Any = None,
        observed_basis: Optional[dict] = None, stamped_at: Optional[datetime] = None,
        observation_only: bool = False,
    ) -> list[dict]:
        """A reading passed every check and is about to be persisted.

        Returns the frames to publish now: one preview, or a revoke when the
        event left a quote status / cannot be ordered against a revision.
        """
        state = self._state(event_id)
        self._context(state, event)
        self._adopt_base(state, row_sources, row_rev)
        if state.status not in PREVIEW_STATUSES:
            state.pending.clear()
            state.expired.clear()
            frame = self._revoke_frame(event_id, state, "terminal")
            return [] if frame is None else [frame]
        value = float(value)
        if observation_only:
            from app.utils.aggregation import parse_source_entry, stamp_source_reading
            from app.utils.probability_eligibility import is_refused

            observed = _basis_observation_time(observed_basis)
            stored_value, stored_at = parse_source_entry((state.base_sources or {}).get(source))
            entry = stamp_source_reading(
                state.base_sources or {}, source, value, eligibility=eligibility,
                observed_basis=observed_basis,
            )[source]
            if (observed is None or stored_at is None or stored_value is None
                    or round(stored_value, 4) != value or is_refused(entry)):
                return self.refused(event_id, source, "unobserved")
            prior = state.pending.get(source)
            if observed <= stored_at:
                # The periodic row clock can precede a newer accepted quote.
                # It supplies no new observation, not a source withdrawal. In
                # particular, do not clear an expired same-value chain here.
                if prior is None:
                    return []
                previous = prior.observed_basis
                previous_at = _basis_observation_time(previous)
                if (prior.value == value and previous_at is not None
                        and previous_at > stored_at
                        and set(previous) == set(observed_basis)
                        and all(observed_basis[key] <= seen for key, seen in previous.items())):
                    expired = self.expire()
                    if self._drop_regressed(state):
                        expired.extend(self._after_drop(event_id, state, "stale", source))
                    return expired
                return self.refused(event_id, source, "unobserved")
            if prior is not None:
                previous = prior.observed_basis
                previous_at = _basis_observation_time(previous)
                # A duplicate/frozen leg or regressed sibling may not fabricate
                # a newer whole reading. The existing display keeps its original
                # deadline; a fresh proof never reopens an expired value below.
                if (previous_at is None or set(previous) != set(observed_basis)
                        or any(observed_basis[key] < seen for key, seen in previous.items())
                        or observed <= previous_at):
                    if self._drop_regressed(state):
                        return self._after_drop(event_id, state, "stale", source)
                    return []
        if source in state.expired:
            if state.expired[source] == value:
                # The same value outlived the limit and is still uncommitted:
                # a retry may not open it a fresh lifetime.
                return []
            del state.expired[source]  # a different value: a new chain
        prior = state.pending.get(source)
        now = self._clock()
        state.pending[source] = _Pending(
            value=value, eligibility=eligibility,
            observed_basis=dict(observed_basis) if observed_basis else None,
            stamped_at=stamped_at or datetime.now(timezone.utc),
            seq=0, since=prior.since if prior is not None else now,
            lease=prior.lease if prior is not None else self._new_chain_lease(now),
        )
        stale = self._drop_regressed(state)
        frame = self._compose(event_id, state, source)
        if frame is None:
            if stale:
                # Nothing left that the database would keep: whatever this
                # event showed may not stay up on a refused value.
                state.pending.clear()
                revoke = self._revoke_frame(event_id, state, "stale")
                return [] if revoke is None else [revoke]
            state.pending.pop(source, None)
            return []
        entry = state.pending.get(source)
        if entry is not None:
            entry.seq = frame["preview"]["seq"]
        return [frame, *self._evict()]

    def committed(
        self, event_id: int, source: str, *, seq: Optional[int], sources: Any,
        rev: Any, event: Any = None,
    ) -> list[dict]:
        """This source's stamp COMMITTED (``sources``/``rev`` from RETURNING).

        The pending value the attempt previewed is retired; any other source
        still pending is recomposed on the new committed base so the reader's
        newer revision does not drop it.
        """
        state = self._events.get(event_id)
        if state is None:
            return []
        if event is not None:
            self._context(state, event)
        self._adopt_base(state, sources, rev)
        # This source's newest reading is now stored. A pending value from this
        # attempt (or an earlier one) is retired; only a later proposal of the
        # same source — one this commit does not carry — stays pending.
        state.expired.pop(source, None)
        entry = state.pending.get(source)
        if entry is not None and (seq is None or entry.seq <= seq):
            del state.pending[source]
        if not state.pending:
            return []
        # A sibling still pending is recomposed on the RETURNING base, which
        # may hold a later observation of its rows: `_after_drop` refuses it.
        return self._after_drop(event_id, state, "unorderable", source)

    def refused(self, event_id: int, source: str, reason: str) -> list[dict]:
        """This source's pending value no longer stands (see module doc)."""
        state = self._events.get(event_id)
        if state is None:
            return []
        state.expired.pop(source, None)
        if source not in state.pending:
            return []
        del state.pending[source]
        return self._after_drop(event_id, state, reason, source)

    def expire(self) -> list[dict]:
        """Revoke every source whose value stayed uncommitted too long."""
        now = self._clock()
        frames: list[dict] = []
        for event_id, state in list(self._events.items()):
            stale = [name for name, entry in state.pending.items()
                     if now - entry.since >= self.max_uncommitted_s]
            if not stale:
                continue
            for name in stale:
                state.expired[name] = state.pending.pop(name).value
            frames.extend(self._after_drop(event_id, state, "expired", stale[0]))
        return frames

    def _evict(self) -> list[dict]:
        frames: list[dict] = []
        while len(self._events) > self.max_events:
            event_id, state = self._events.popitem(last=False)
            if state.pending:
                state.pending.clear()
                frame = self._revoke_frame(event_id, state, "evicted")
                if frame is not None:
                    frames.append(frame)
        return frames


_REGISTRY: Optional[PreviewRegistry] = None


def registry() -> PreviewRegistry:
    """The process's one registry: both source arms must share it."""
    global _REGISTRY
    if _REGISTRY is None:
        _REGISTRY = PreviewRegistry()
    return _REGISTRY


def reset_registry_for_tests() -> None:
    global _REGISTRY
    _REGISTRY = None


def is_preview_frame(frame: Any) -> bool:
    preview = frame.get("preview") if isinstance(frame, dict) else None
    return (isinstance(preview, dict) and preview.get("kind") in ("blend", "revoke")
            and "rev" not in frame)
