# Explicit DNPL v3 activation and bounded cleanup

PILLAR: TRUTH / FORMATTING.
SHIP: held eligible event pages can resume fast updates after ordering authority
loss, using a new domain without reviving old previews or losing chart history.

This is the local implementation contract, awaiting independent source review
and provider qualification. It does not authorize any production operation.

## Operator boundary

`ActivationController` is not called by startup, producer code, a scheduler or
an automatic retry. Integrator must hold the existing approved all-writer
interlock before preparing an exact fresh authority and retain that identity.
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

Under the separately required no-same-identity-rollback premise, storage is at
most two bounded event namespaces (six keys each) plus one three-field admission
fence; PostgreSQL has one current row and one predecessor. No history list,
namespace scan or evidence eviction is used. This is not a proof that a hosted
provider satisfies that premise. The supported provider/version qualification
remains required; a compatibility Redis test does not supply it.

## Validation boundaries

Use the existing disposable PG/Redis lab. Controls cover repeated recovery with
bounded key count, delayed initializer/arm after cleanup, fence loss, atomic send
permission, partial initialization, wrong primary, lost cleanup replies and
transport failure without command replay. All ordering/expiry reader gates and
installed-iPhone acceptance remain separate. Neither activation success nor these
controls establishes sub-second visible delivery; the existing full-path replay
and post-release held headline/chart acceptance must still establish that.
