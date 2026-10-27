# Explicit DNPL v3 activation and bounded cleanup

PILLAR: TRUTH / FORMATTING.
SHIP: held eligible event pages can resume fast updates after ordering authority
loss, using a new domain without reviving old previews or losing chart history.

This is the local implementation contract. Exact-source reviews are retained in
the release offer; provider and operational qualification remain separate. This
document does not authorize any production operation.

## Operator boundary

`ActivationController` is not called by startup, producer code, a scheduler or
an automatic retry. Integrator must establish the approved all-writer
stop/drain interlock before preparing an exact fresh authority and retain that
identity. This is a prerequisite, not an existing reusable implementation:
the operation owner confirmed that the prior formation checks alone do not
satisfy it. The [explicit command boundary](dnpl-authority-v3-command.md) now
provides preview and execute-plan. Its cooperative hold and writer checks do not
themselves establish full external writer exclusion or grant an operation.
No controller method allocates a namespace, restarts a provider, changes policy,
starts writers or grants the interlock. The existing ready authority remains the
only producer authority; preparing/disabled continues committed-only delivery.

The explicit sequence is prepare, arm, initialize, verify-and-ready. A predecessor
can be cleaned once the newer fence is armed; cleanup must finish before another
allocation. Producers start only after the separate attended procedure succeeds.

## What survives crashes

The primary control row stores activation_step 0/1/2. An exact transaction burns
step1 before the only arm send and step2 before the only initializer send. A lost
commit reply or cancellation grants no send permission. No automatic resend is
made after a Redis timeout/reply loss. Initialization success with a lost reply
can be resolved by read-only exact initial-state verification followed by ready
CAS; partial/missing state cannot.

One retirement row stores the full prior authority. Allocation and recording the
predecessor commit atomically. An outstanding predecessor blocks the third
allocation. Cleanup deletes only its six derived namespace keys, verifies absence
in the same guarded Lua, then clears the exact retirement record while locking
the current PostgreSQL authority. An uncertain cleanup/ack keeps or reveals that
receipt; it cannot justify forgetting it or guessing a fresh namespace.
`acknowledge_retirement` resolves a lost Redis cleanup reply using read-only
fence/absence verification and the exact PostgreSQL acknowledgement. It sends
no deletion again. Surviving old keys or a lost/newer fence refuse acknowledgement.

## Why a delayed initializer cannot undo cleanup

One Redis admission fence holds incarnation, operation token and armed/used state.
Arm advances only an existing strictly older fence. Initialize consumes armed to
used before writing any namespace key. Readback requires exact used token and the
unchanged initial namespace. Cleanup requires the exact newer fence. A delayed
older initializer therefore fails after cleanup, as does an older arm.

Absence is not permission to recreate the admission fence. PostgreSQL grants
bootstrap only to the seed successor or an allocation with a changed primary
run_id/master_replid. That permission is consumed before a single send. A
same-primary successor cannot bootstrap after eviction, even if its namespace
is empty. To reach a newer fence on the same primary, the first bootstrap must
already have executed; its one send cannot arrive again after cleanup.

**Availability limit:** losing this admission fence, or abandoning its sole
bootstrap before it executes, can stop recovery on that unchanged primary.
Committed-only delivery remains. Recovery then needs a separately reviewed,
explicit primary-identity change; this code does not perform or authorize one.
If a predecessor is still pending when the primary changes, the explicit
`retire_after_primary_change` step breaks the allocation/cleanup dependency:
atomic INFO must prove that the replacement differs from **both** retained
identities. It deletes/verifies only the recorded predecessor, then acknowledges
that exact receipt under the unchanged PostgreSQL current row. Ordinary prepare
can then record that current namespace as the next predecessor and allocate the
replacement. A readback-only form resolves a lost cleanup reply. No third slot,
receipt bypass, identity rewrite or same-primary cleanup exception is introduced.
Do not advertise automatic recovery from arbitrary eviction. Source review and
Integrator must account for this limit in the final procedure/storage policy.

### Bounded physical storage and restored deletions

The two physical slots are `live:blend_preview:v3:slot:0:` and `:slot:1:`,
selected by incarnation parity. Each has six possible keys. The full
incarnation, UUID, primary identity and policy remain in the guard; parity is
only an address and never authority. PostgreSQL retains one current row and
one predecessor. There is one additional three-field admission fence.

This bounds the new layout to twelve namespace keys plus that fence, even when
a changed-identity rollback restores an already-acknowledged deletion. Each
ledger remains subject to its existing event/reservation limits. No historical
namespace list, scan, TTL-based evidence loss or reliance on LRU is introduced.
Every cleanup atomically validates the full recorded occupant token, including
on a replacement primary. A different occupant, or surviving keys with a
missing/malformed guard, refuses deletion. Entirely absent keys can still be
acknowledged through the exact PostgreSQL predecessor protocol. Old commands
cannot act on a newer occupant merely because its address was reused.

**Availability limit:** initialization still requires an entirely empty target
slot. A rollback-restored occupant which PostgreSQL no longer records is not
silently deleted or adopted. Activation refuses and committed updates remain
available. This delta bounds storage; it does not promise automatic recovery
from every restored or partially evicted dataset.

**First-rollout condition:** this bound covers the two-slot layout only.
Integrator must establish that no earlier UUID-addressed v3 namespaces exist
in the selected dataset or can be imported from a pre-cutover snapshot. A new
process or a fork is not proof of empty storage. If an earlier layout was used,
its bounded cutover requires a separate qualified procedure before activation;
this change performs no scan or deletion of legacy data.

### Provider and administrative premise

Pinned Redis/Valkey source supports identity changes on documented startup,
restart, failover and promotion paths. That is conditional source evidence,
not a guarantee about undisclosed provider operations. Actual service binding,
INFO permission inside scripts and stable standby readiness remain part of
Integrator's qualification.

In-place dataset replacement is excluded throughout the lifetime of v3
authority, retained evidence and in-flight commands, including preparing and
disabled states. This covers RESTORE/SWAPDB, FLUSH followed by rewrites,
DEBUG RELOAD/LOADAOF and equivalent restore tooling. Planned replacement must
exclude writers and disable authority before touching data, then use a
qualified identity-changing recovery path. Disabling alone does not qualify
same-identity restoration. Suspected unexpected replacement breaches the
premise: stop v3 delivery via the authority fallback and requalify recovery.
An operating rule does not itself constrain provider-internal behavior.

## Validation boundaries

Use the existing disposable PG/Redis lab. Controls cover repeated recovery with
bounded key count, delayed initializer/arm after cleanup, fence loss, atomic send
permission, partial initialization, wrong primary, lost cleanup replies and
transport failure without command replay. All ordering/expiry reader gates and
installed-iPhone acceptance remain separate. Neither activation success nor these
controls establishes sub-second visible delivery; the existing full-path replay
and post-release held headline/chart acceptance must still establish that.
