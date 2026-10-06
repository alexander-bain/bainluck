# #10571 — Canonical game detail on the caller's snapshot

PILLAR: TRUTH · FORMATTING.
SHIP: Background Live Activities can use the same canonical score, probability
and final reading as the foreground game page without receiving another caller's
older in-flight response. This source is the reader substrate for queued #10568.

`build_event_detail_uncoalesced(db, event_id)` runs the existing `get_event`
fresh leader body on the supplied session. Route-owned private ContextVars skip
coalescing and cache publication, and token resets preserve the calling context
on success, exception and cancellation. The function does not modify the shared
fresh-build slots or read/write/evict event-detail cache entries. Canonical
resolution, the folded hero and serve-time corrections use the existing body.
Ordinary fresh calls retain their coalescing and cache publication behavior.

The caller owns serialization and transaction isolation. #10568 must acquire its
serializer on a dedicated connection before opening the REPEATABLE READ read
transaction; the canonical SELECT must be that transaction's first statement.
Taking an advisory transaction lock as its first statement would create a snapshot
before the lock wait and hide the previous holder's commit. The adapter owns the
actual-PostgreSQL ordering proof; this reader neither acquires locks nor starts a
transaction. Sequence-table migrations are in a separate PR.

Local guards exercise the real route with distinct revisioned sessions, a full
cache, occupied slots and a held competing build. Success, failure and cancellation
are each followed by a real fresh-reader herd that must coalesce and publish;
this detects leaked flags by resulting behavior. Full payload equality with the
ordinary leader guards reuse of response semantics.

This source has no mounted caller, scheduler, migration, APNs send, or device or
release acceptance. Integrator owns shared-file composition and merge.
