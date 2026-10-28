"""Namespace-bound producer adapter over the existing reservation ledger.

One instance has one immutable ready authority. No rebinding, seed/reset or
implicit activation. Construct only from a fresh primary sample; pre-sample
observations cannot create preview chains in the recovered domain.
"""

from dataclasses import dataclass
from datetime import datetime
import json
from typing import Any

from app.services.dnpl_authority import Authority
from app.utils.blend_preview import (
    LedgerRegistry,
    LEDGER_TTL_TOKEN,
    _basis_observation_time,
    _ledger_text,
    carry_selection,
    observe_publication,
    recompose_traced,
)
from app.utils.dnpl_authority_transport import encode_preview
from app.utils.dnpl_redis_authority import (
    GUARDED_LEDGER_SCRIPT,
    guard_token,
    namespace_keys,
)


@dataclass(frozen=True)
class AuthorityTicket:
    authority: Authority
    source: str
    owner: int
    barrier: int

    def __str__(self):
        return str(self.barrier)


class AuthorityLedgerRegistry(LedgerRegistry):
    def __init__(
        self,
        *,
        authority: Authority | None = None,
        observed_after: datetime | None = None,
        **kwargs
    ):
        super().__init__(**kwargs)
        self._authority = None
        self._observed_after = None
        self._halted = False
        if authority is not None:
            self._bind(authority, observed_after)
        elif observed_after is not None:
            raise ValueError("observation floor requires authority")

    def _bind(self, authority, observed_after):
        if self._authority is not None:
            raise ValueError("existing registry cannot change authority")
        if (
            authority.state != "ready"
            or not isinstance(observed_after, datetime)
            or observed_after.tzinfo is None
        ):
            raise ValueError(
                "ready primary authority and aware database clock required"
            )
        if authority.policy_fingerprint != self.policy.fingerprint:
            raise ValueError("ready authority reservation policy mismatch")
        self._authority = authority
        self._observed_after = observed_after

    async def bind_primary(self, store):
        # Caller holds the existing shared claim lock. No registry replacement
        # can relabel old operations or pending buffers as a new domain.
        if self._authority is None:
            authority, sampled_at = await store.read_for_producer()
            self._bind(authority, sampled_at)

    @classmethod
    async def from_primary(cls, store, **kwargs):
        authority, sampled_at = await store.read_for_producer()
        return cls(authority=authority, observed_after=sampled_at, **kwargs)

    @property
    def authority(self):
        return self._authority

    def _ticket_matches(self, ticket, source):
        return (
            isinstance(ticket, AuthorityTicket)
            and ticket.authority == self.authority
            and ticket.source == source
            and ticket.owner == self.claims.get(source)
        )

    def _bind_op(self, op):
        if op is None:
            return None
        return {
            **op,
            "_dnpl_authority": self.authority,
            "owner": self.claims.get(op["source"]),
        }

    async def read_ticket(self, call, source, **kwargs):
        ticket, candidates = await super().read_ticket(call, source, **kwargs)
        return (
            None
            if ticket is None
            else AuthorityTicket(self.authority, source, self.claims[source], ticket)
        ), candidates

    async def capacity_ticket(self, call, source, **kwargs):
        ticket, candidates, idle, when = await super().capacity_ticket(
            call, source, **kwargs
        )
        return (
            (
                None
                if ticket is None
                else AuthorityTicket(
                    self.authority, source, self.claims[source], ticket
                )
            ),
            candidates,
            idle,
            when,
        )

    def propose(self, event_id, source, **kwargs):
        if self._halted or source not in self.claims:
            return []
        observed = _basis_observation_time(kwargs.get("observed_basis"))
        if observed is None or observed <= self._observed_after:
            return []
        ticket = getattr(kwargs["event"], "preview_read_ticket", None)
        if not self._ticket_matches(ticket, source):
            return []
        return [self._bind_op(op) for op in super().propose(event_id, source, **kwargs)]

    def _settle_op(self, *args, **kwargs):
        return self._bind_op(super()._settle_op(*args, **kwargs))

    def terminal_read(self, event_id, source, rev, ticket):
        if not self._ticket_matches(ticket, source):
            return None
        return self._bind_op(
            {
                "ledger_op": "terminal",
                "event_id": event_id,
                "source": source,
                "ctx_rev": rev,
                "read_ticket": ticket,
            }
        )

    def retire_read(self, event_id, source, rev, ticket, **kwargs):
        if not self._ticket_matches(ticket, source):
            return None
        return self._bind_op(
            super().retire_read(event_id, source, rev, ticket, **kwargs)
        )

    def retire_missing(self, event_id, source, ticket):
        if not self._ticket_matches(ticket, source):
            return None
        return self._bind_op(super().retire_missing(event_id, source, ticket))

    def retire_idle(self, event_id, source, rev, ticket, deadline_ms):
        if not self._ticket_matches(ticket, source):
            return None
        return self._bind_op(
            super().retire_idle(event_id, source, rev, ticket, deadline_ms)
        )

    def classify(self, event_id, source, event, rev, ticket):
        if not self._ticket_matches(ticket, source):
            return None
        return self._bind_op(super().classify(event_id, source, event, rev, ticket))

    async def _guarded_call(self, call, source, owner, *argv):
        if self._halted:
            return ["authority_stopped"]
        if self.authority is None:
            return ["authority_unavailable"]
        keys = namespace_keys(self.authority)
        reply = await call(
            "EVAL",
            GUARDED_LEDGER_SCRIPT,
            len(keys),
            *keys,
            guard_token(self.authority),
            self.authority.redis_run_id,
            self.authority.redis_master_replid,
            source,
            str(owner),
            self.policy.fingerprint,
            *("" if a is None else str(a) for a in argv)
        )
        result = [_ledger_text(item) for item in reply]
        if result[0] in {
            "identity_changed",
            "guard_refused",
            "guard_lost",
            "dirty_result",
            "lost",
            "lost_admission",
            "policy_mismatch",
        }:
            self._halted = True
        return result

    async def _eval(self, call, *argv: Any):
        op, source = argv[:2]
        if op == "revoke":
            raise ValueError("v3 revoke requires its originating source")
        owner = "0" if op == "claim" else self.claims.get(source, "0")
        values = list(argv)
        if op == "publish":
            values[8] = encode_preview(self.authority, json.loads(values[8]))
        return await self._guarded_call(call, source, owner, *values)

    async def _mutate(self, op, call, stats):
        if (
            not isinstance(op, dict)
            or op.get("_dnpl_authority") != self.authority
            or op.get("owner") != self.claims.get(op.get("source"))
            or self._halted
        ):
            stats["authority_refused"] = stats.get("authority_refused", 0) + 1
            return []
        frames = await super()._mutate(op, call, stats)
        return [
            {
                **frame,
                "_dnpl_authority": self.authority,
                "_dnpl_source": op["source"],
                "_dnpl_owner": op["owner"],
            }
            for frame in frames
        ]

    async def _publish(self, frame, call, channel, stats, retries=2, observe=None):
        source = frame.get("_dnpl_source")
        if (
            frame.get("_dnpl_authority") != self.authority
            or source not in self.claims
            or frame.get("_dnpl_owner") != self.claims[source]
            or self._halted
        ):
            stats["authority_refused"] = stats.get("authority_refused", 0) + 1
            if observe is not None:
                observe_publication(
                    observe,
                    {key: value for key, value in frame.items() if not key.startswith("_")},
                    frame.get("_ledger"), ("local_authority_refused",),
                )
            return
        clean = {
            key: value for key, value in frame.items() if not key.startswith("_dnpl_")
        }
        if clean["preview"]["kind"] == "revoke":
            meta = clean.pop("_ledger")
            result = await self._guarded_call(
                call,
                source,
                self.claims[source],
                "revoke",
                channel(clean["event_id"]),
                encode_preview(self.authority, clean),
            )
            observe_publication(observe, clean, meta, result)
            if result[0] == "published":
                stats["revoked"] = stats.get("revoked", 0) + 1
            else:
                stats["authority_refused"] = stats.get("authority_refused", 0) + 1
            return
        meta = clean.pop("_ledger")
        payload = json.dumps(clean)
        if clean.get("source") != source or payload.count(LEDGER_TTL_TOKEN) != 1:
            stats["authority_refused"] = stats.get("authority_refused", 0) + 1
            observe_publication(observe, clean, meta, ("local_authority_refused",))
            return
        argv = [
            source,
            self.claims[source],
            clean["event_id"],
            " ".join(self.sources),
            meta["gen"],
            meta["seq"],
            channel(clean["event_id"]),
            payload,
        ]
        for name, owner, expires in meta["contributors"]:
            argv.extend((name, owner, expires))
        result = await self._eval(call, "publish", *argv)
        observe_publication(observe, clean, meta, result)
        if result[0] == "published":
            stats["published"] = stats.get("published", 0) + 1
        elif result[0] == "contributor" and retries > 0:
            stats["ledger_recomposed"] = stats.get("ledger_recomposed", 0) + 1
            sync = self._bind_op(recompose_traced(meta,
                {
                    "ledger_op": "settle",
                    "mode": "sync",
                    "event_id": clean["event_id"],
                    "source": source,
                    "through": None,
                    "reason": "expired",
                    "base_rev": None,
                    "base": None,
                }
            ))
            for fresh in carry_selection(meta, await self._mutate(sync, call, stats)):
                await self._publish(fresh, call, channel, stats, retries - 1, observe)
        elif result[0] in ("stale", "terminal"):
            stats["ledger_superseded"] = stats.get("ledger_superseded", 0) + 1
        else:
            self._refusal(stats, result[0], "publish", source, clean["event_id"])

    async def prepare(self, items, call, stats):
        # Refused maintenance builders may return None; they authorize no call.
        return await super().prepare(
            [item for item in items if item is not None], call, stats
        )
