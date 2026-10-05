# W3.2: delivery ordering substrate

PILLARS: TRUTH · FORMATTING.
SHIP: The selected game's reading keeps updating while the phone is suspended.

`activitykit_delivery_state.py` supplies immutable, pure transitions for ONE registered
activity and canonical event. It is not mounted delivery. The future adapter must
persist/compare-and-swap each transition before issuing transport work and serialize
observations and completions. It must restore this state after restart. Activity IDs
are opaque; this module holds no token, credentials, database, or APNs client.

A caller-supplied monotonic revision orders coherent served readings, including
undated ones. Revision assignment/persistence is an adapter requirement, not a
producer timestamp. Independently retained score/probability high-water dates reject
older nonterminal readings; unknown dates never erase those fences or borrow clocks.
The first authoritative terminal snapshot latches its exact values even if its real
producer date is older, and suppresses subsequent readings. Correction of an already
latched terminal is outside this first-end contract and needs an explicit later policy.

Only one command may be in flight. Pending updates coalesce to the newest accepted
reading. Terminal/explicit stop supersede waiting update retries; stop prevents any
reactivation and requests immediate dismissal, including after an in-flight final.
An in-flight update is allowed to finish before the queued end. Each dispatch has a distinct attempt identity in addition to its stable logical
command identity; stale/duplicate attempt completions are inert, including while a
retry is in flight. APNs timestamps advance in real Unix seconds: a second command waits for
a later second instead of inventing a future send time.

Retry policy is injected as a finite tuple of nonnegative delays. Tests use 1s/2s as
an example, not an APNs requirement or product default. Only caller-classified
transient failures retry, reusing the exact command identity and bytes. Permanent,
unavailable, or exhausted attempts halt visibly; token replacement/resumption is
owned by the future authenticated adapter. No automatic restart is implied.

Remaining gates: review retry policy and first-terminal behavior with the mounted
adapter; authenticated activity ownership/token lifecycle; serialized durable storage;
APNs transport/configuration; composed Swift decode; actual suspended-device receipt
under #10543. No push-to-start, Apple configuration, deployment, or phone acceptance
is claimed by this source slice.

Stop after an acknowledged end is inert: dismissal of an already-ended retained
ActivityKit card is not a capability of this first-end delivery state. The future
phone/dismissal adapter must own that separately; this module does not claim it.
