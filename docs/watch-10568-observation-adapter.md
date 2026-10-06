# #10568 canonical ActivityKit observation adapter

PILLAR: TRUTH · FORMATTING

SHIP: Background Live Activity scores, probabilities and final readings match the foreground game, preserving each producer's observation clock.

Source-only orchestration, unmounted and unscheduled. The public reader from
#10571/#10572 is composed at exact source 901a5c3cc3a34e425887a9d8a35a03f8ad51932c.
No adapter-owned event formatter or private route flags exist.

`ActivityKitObservationAdapter.capture(event_id)` takes a session advisory lock on
a dedicated connection in AUTOCOMMIT before opening REPEATABLE READ. The canonical
reader's Event SELECT is the first statement in that transaction. The exact
projection and per-event logical sequence commit atomically using Core writes.
The probability-only source revision never orders score/status. Connections are
physically invalidated after capture, including failure/cancellation/timeout, so
session locks never return to a pool. Lock acquisition
has an asyncio timeout that cancels the query before physically discarding the connection. There is no external transport, cache publication or ORM
flush in the adapter's locked section.

`replay(event_id, sequence)` returns that immutable saved reading and sequence;
it never reads a newer game or relabels a delayed read with a new sequence.
`fanout` reads at most 101 authorized registration ids for a page of at most 100,
ordered by activity id and continued with an explicit cursor. It closes its
connection before invoking the durable worker. A failed registration increments the bounded `failed` count without blocking healthy siblings or cursor progress; cancellation propagates. Callers must not treat a nonzero failure count as complete delivery. The worker rechecks current
binding, authorization horizon, stop/final, revision and credential fences.

Canonical identity changes are refusals. The new event child is SUBSTANCE;
merges refuse retained observations before any child write. Neither registration
nor snapshot is silently reparented. Public observations retain no user or token;
they persist for replay until explicitly removed by a future authorized retention
policy. Such retention also intentionally prevents merging their bound event.

The migration `activitykit_observation` follows `activitykit_credential_expiry`.
It is source-only, separately ATTENDED migration-class. No migration application,
production mounting, scheduler, APNs credentials or Apple/device acceptance is
part of this source. Integrator owns composition, merge and deployment decisions.

Gates: 17 real PostgreSQL cases (14 explicitly synthetic-reader protocol cases,
three actual canonical-route cases). Actual route cases include NBA, draw-priced
soccer and completed state, and prove a writer commit made while the serializer
waits becomes visible, with Event SELECT first in the read transaction. Worker,
registration and expiry PostgreSQL gates remain separate (17/5/17).
