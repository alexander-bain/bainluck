# Recovery command preparation

PILLAR: TRUTH / FORMATTING.
SHIP: restore correctly ordered fast headline/chart updates after authority loss.

## Implemented boundary

`python -m app.services.dnpl_activation_command preview` is an explicit read-only
snapshot command, run from `backend/`. It requires:

- `--expected-authority`: JSON containing exactly the eight `Authority` fields
  (protocol, incarnation, namespace, operation_id, state, redis_run_id,
  redis_master_replid, policy_fingerprint). Duplicate or extra fields are refused.
- `--expected-primary`: the exact `run_id:master_replid` comparison target.
- `DNPL_COMMAND_DATABASE_URL` and `DNPL_COMMAND_REDIS_URL` explicitly selected in
  the invocation environment. There is no application-credential fallback.

No credentials belong in the command arguments or output. PostgreSQL sessions
are read-only, with statement/lock timeouts. Reads have a one-second aggregate
budget, Redis has 150ms connection/read limits and no command retry. Connection
errors report their class only, avoiding credential-bearing exception strings.

The command compares the authority, reads activation step and predecessor, reads
Redis identity/role using one INFO command, then repeats the PostgreSQL reads.
Observed changes or a mismatched expected identity refuse. Matching observations
produce `SNAPSHOT_MATCH` and exit 0; refusal exits 2. There is no transaction across
PostgreSQL and Redis: a match is **not** a distributed snapshot, activation
readiness, writer-stop receipt, provider qualification or permission to mutate.
The output always includes `mutation_permitted: false` and
`interlock: UNIMPLEMENTED`. A replacement primary may differ from the authority;
that difference is explicitly reported and never authorizes replacement.

## Unimplemented operational boundary

The operation owner confirmed that no reusable all-writer interlock exists.
Two zero-formation snapshots and a convention-based desk lock do not establish
continuous exclusion or drain commands already sent. A self-authored receipt,
file hash, elapsed wait or `--yes` cannot supply those missing properties.

Consequently this command deliberately exposes **only preview**, not prepare,
arm, initialize, ready, cleanup or retirement acknowledgement. The accepted
controller remains unchanged. A future mutation wrapper must establish the
controller's full prerequisite and pass independent review before exposing
those operations. Preview work does not pay that prerequisite or grant a live
operation. Readback-only resolution of uncertain mutations remains part of the
accepted controller contract, not a capability added by this preview command.

## Controls

Unit controls cover exact/duplicate input, changed authority/step/predecessor,
wrong primary/role, one read on lost reply, bounded reads, refused mutation
subcommands and credential-safe error output. Existing disposable PG/Redis
controls compare actual authority rows, send permissions, predecessor and Redis
key bytes before/after previews at every activation stage. The declared CI group
adds those two controls, retaining its prior assertions. Independent preview
source review and operational completion remain separate from these tests.
