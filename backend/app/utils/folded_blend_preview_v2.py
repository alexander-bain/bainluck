"""Connection-owned composition of independent event-ledger authorities.

No new read, subscription, shared cache or probability policy lives here. There
are at most two elected pending origins, one per supported preview source.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import math
from uuid import uuid4

from app.utils.blend_preview import PREVIEW_SOURCES, PREVIEW_STATUSES
from app.utils.folded_blend_preview import _revision


@dataclass
class _Origin:
    epoch: int
    seq: int
    state: str
    base_rev: int = -1
    deadline: float = 0.0
    entries: dict = field(default_factory=dict)
    observed: dict = field(default_factory=dict)

    @property
    def identity(self):
        return self.epoch, self.seq

    def retire(self, state):
        self.state = state
        self.entries.clear()
        self.observed.clear()


class FoldedPreviewSession:
    """Per-origin fences survive withdrawal; unrelated epochs never compare."""

    def __init__(self, event_id, members, *, session=None):
        self.event_id = event_id
        self.members = frozenset(str(member) for member in members)
        self.session = session or uuid4().hex
        self.sequence = 0
        self.origins = {}
        self.election = None
        self.vector = {}
        self.status = None
        self.disabled = False
        self.reconnect_required = False
        self._last_snapshot = None

    def _retire_all(self):
        for origin in self.origins.values():
            if origin.state == "pending":
                origin.retire("revoked")

    def reset(self):
        """Hub recovery invalidates held prices without resetting their fences."""
        self._retire_all()

    def wait_seconds(self, now, maximum):
        deadlines = [item.deadline for item in self.origins.values()
                     if item.state == "pending"]
        return min(maximum, max(0.001, min(deadlines) - now)) if deadlines else maximum

    def _refresh(self, base, floors, now):
        # A committed floor retires only that origin. Keep the sibling while
        # the ordinary projector obtains a complete newer committed base.
        for key, value in floors.items():
            if key in self.members and _revision(value):
                self.vector[key] = max(value, self.vector.get(key, value))
        for key, item in self.origins.items():
            if item.state != "pending":
                continue
            if floors.get(key, -1) > item.base_rev:
                item.retire("committed")
            elif item.deadline <= now:
                item.retire("expired")
        if base is None:
            # Eviction/recovery is a loss of complete composition authority.
            # Do not resurrect cached tuples when another page warms it later.
            self._retire_all()
            return False
        election = tuple(sorted((name, owner) for name, owner in base.owners.items()
                                if name in PREVIEW_SOURCES))
        if (base.event_id != self.event_id or set(base.revision) != self.members
                or len({owner for _, owner in election}) > 2
                or any(str(owner) not in self.members for _, owner in election)):
            self.disabled = True
        if self.election is None:
            self.election = election
        elif self.election != election:
            # A changed owner set requires a fresh stream; otherwise seen
            # authority could grow unbounded or silently change its meaning.
            # Only a valid, eligible election may request rollover. A bad
            # base remains disabled, rather than making clients reconnect in
            # a loop on the same invalid authority.
            if not self.disabled and base.context["status"] in PREVIEW_STATUSES:
                self.reconnect_required = True
            self.disabled = True
        if self.disabled or base.context["status"] not in PREVIEW_STATUSES:
            self._retire_all()
            return False
        self.status = base.context["status"]
        for key, value in base.revision.items():
            self.vector[key] = max(value, self.vector.get(key, value))
        for key, item in self.origins.items():
            if item.state == "pending" and base.revision[key] > item.base_rev:
                item.retire("committed")
        return base.covers(self.members, self.vector)

    def update(self, base, *, floors, now, frame=None, elapsed_ms=0):
        ready = self._refresh(base, floors, now)
        if frame is not None and self.election is not None and not self.disabled:
            meta = frame.get("preview", {})
            key = str(frame.get("event_id"))
            elected = {str(owner) for _, owner in self.election}
            if (key in elected and isinstance(meta, dict)
                    and _revision(meta.get("epoch")) and _revision(meta.get("seq"))):
                identity = (meta["epoch"], meta["seq"])
                previous = self.origins.get(key)
                newer = previous is None or identity > previous.identity
                # Even an identical packet cannot renew, alter or revive a
                # tuple; the first validated receipt owns its deadline.
                if newer and meta.get("kind") == "revoke" and _revision(meta.get("through_seq")):
                    if meta["through_seq"] < meta["seq"]:
                        self.origins[key] = _Origin(*identity, "revoked")
                elif newer and meta.get("kind") == "blend":
                    validated = None
                    if (base is not None and base.context["status"] in PREVIEW_STATUSES
                            and meta.get("pending_entries_version") == 2
                            and meta.get("pending_entries_authority") == "event-ledger-v1"):
                        # A sibling's commit can delay full-fold publication
                        # without invalidating this origin's own current base.
                        # Retain its newest eligible tuple during that wait.
                        origin_floors = {key: self.vector[key]} if key in self.vector else {}
                        validated = base.pending_entries(
                            frame, members=self.members, floors=origin_floors,
                            elapsed_ms=elapsed_ms, split_origins=True,
                        )
                    if validated is not None:
                        entries, observed, ttl = validated
                        self.origins[key] = _Origin(
                            *identity, "pending", meta["base_rev"],
                            now + ttl / 1000, entries, observed,
                        )
                    elif previous is not None:
                        # A newer ledger tuple supersedes the prior one even
                        # when we cannot project it. Advance only an existing
                        # fence: invalid initial input acquires no authority.
                        self.origins[key] = _Origin(*identity, "revoked")
        return self._snapshot(base if ready else None, now)

    def _snapshot(self, base, now):
        if not self.origins or set(self.vector) != self.members:
            return None
        active = [item for item in self.origins.values() if item.state == "pending"]
        authority = {}
        for key, item in self.origins.items():
            value = {"epoch": item.epoch, "seq": item.seq, "state": item.state}
            if item.state == "pending":
                value["ttl_ms"] = max(0, math.floor((item.deadline - now) * 1000))
            authority[key] = value
        body = None
        if base is not None and active and all(item.base_rev == base.revision[key]
                for key, item in self.origins.items() if item.state == "pending"):
            entries = {name: value for item in active for name, value in item.entries.items()}
            observed = {name: value for item in active for name, value in item.observed.items()}
            body = base.compose(entries, observed)
        kind = "blend" if body is not None else "revoke"
        # Time passing alone does not resend/renew an unchanged snapshot.
        # Deadlines remain part of identity, while serialized TTL counts down.
        signature = (kind, tuple(sorted(self.vector.items())), tuple(
            (key, item.epoch, item.seq, item.state, item.deadline)
            for key, item in sorted(self.origins.items())),
            None if body is None else tuple(sorted(body.items())))
        if signature == self._last_snapshot:
            return None
        self._last_snapshot = signature
        self.sequence += 1
        return {
            **(body or {"event_id": self.event_id, "p": None, "status": self.status}),
            "provisional": True,
            "preview": {
                "kind": kind, "folded_version": 2,
                "fold_session": self.session, "fold_seq": self.sequence,
                "base_fold_revision": dict(self.vector),
                "origin_authority": authority,
                "ttl_ms": (min((a["ttl_ms"] for a in authority.values()
                                if a["state"] == "pending"), default=0)
                           if body is not None else 0),
            },
        }
