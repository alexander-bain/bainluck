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
controller remains unchanged. The local `dnpl_activation_runner.run_step`
implementation must establish the controller's full prerequisite and pass
independent review before the CLI exposes those operations. Preview work does
not pay that prerequisite or grant a live
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

## Local operation runner (not a production entry point)

The operation owner's v2 interface is implemented in separate local components:

- `dnpl_operation_hold`: captures the actual helper's owner PID, process start,
  identity and claim epoch into an exclusive run record. It holds the helper's
  existing serialization inode throughout the local command interval and
  verifies actual matching-owner output. It never claims or releases a lane.
  An absent `owner_started` field is supported by capturing the live process
  start; changed claim epoch or process start still refuses. This protects
  cooperative helper transitions during that interval, not external controls.
- `dnpl_writer_verifier`: a pinned standalone child reads releases, slug source,
  formation and dynos for both apps. It receives a fresh nonce and exact binding
  from its parent; raw files are evidence, not permission. Its eight logical
  observations include four Heroku CLI invocations: the eventual operation's
  request budget must account for CLI internal requests, not assume eight HTTP
  requests. This code has not been invoked against production.
- `dnpl_writer_observations`: owns child execution and independently parses raw
  reads. It requires converged commits, exact releases/slugs, no writer or
  unknown active process, and unchanged dyno releases. The entire collection
  must fit 120 seconds measured from parent invocation, with wall/monotonic
  disagreement at most one second; future, negative, unordered and non-integer
  timestamps refuse. Neither interval is a drain bound.
- `dnpl_activation_runner`: invokes that verifier directly, checks actual
  authority/primary, consumes a canonical command identity with `O_EXCL` and
  `fsync`, rechecks freshness after filesystem latency, then calls the accepted
  controller exactly once. A fresh nonce cannot authorize repeating the same
  command. A lost reply yields `UNCERTAIN`; failed post-verification yields
  `UNCERTAIN-WRITER`. Cancellation retains the consumed-send record. Results
  never delete that record or replay a command automatically.

These components do not establish P-EXCL, deployed-source/migration completion,
late-command closure acceptance, provider qualification, or the separately
granted stop/start operations. The CLI continues to refuse mutation commands.
Same-UID malicious modification remains outside the trust boundary. Recreating
a receipt is not an authorization mechanism. A process crash loses the local
continuous hold; no saved record is loaded as evidence of continued ownership.

The deciding local PG/Redis control exercises prepare/arm/initialize/ready
through the runner and repeats it with a genuinely executed initializer whose
reply is deliberately lost. The initializer is sent once; specific ready
readback resolves it. Platform observations in that control are explicitly
simulated. Separate local collector/validator tests cover the real command
shape, file/nonce bindings, freshness and post-send writer refusal.
