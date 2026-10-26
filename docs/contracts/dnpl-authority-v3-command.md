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

## Operational boundary

The operation owner confirmed that no reusable all-writer interlock exists.
Two zero-formation snapshots and a convention-based desk lock do not establish
continuous exclusion or drain commands already sent. A self-authored receipt,
file hash, elapsed wait or `--yes` cannot supply those missing properties.

Consequently the preview command deliberately exposes **only preview**, not
prepare, arm, initialize, ready, cleanup or retirement acknowledgement. The
separate operator entry point below invokes the reviewed local runner; it does
not turn snapshot output into qualification or grant a live operation.
Readback-only resolution of uncertain mutations retains the accepted
controller's specific paths.

## Controls

Unit controls cover exact/duplicate input, changed authority/step/predecessor,
wrong primary/role, one read on lost reply, bounded reads, refused mutation
subcommands and credential-safe error output. Existing disposable PG/Redis
controls compare actual authority rows, send permissions, predecessor and Redis
key bytes before/after previews at every activation stage. The declared CI group
adds those two controls, retaining its prior assertions. Independent preview
source review and operational completion remain separate from these tests.

## Local operation runner

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
granted stop/start operations. The preview CLI continues to refuse mutation commands.
Same-UID malicious modification remains outside the trust boundary. Recreating
a receipt is not an authorization mechanism. A process crash loses the local
continuous hold; no saved record is loaded as evidence of continued ownership.

The deciding local PG/Redis control exercises prepare/arm/initialize/ready
through the runner and repeats it with a genuinely executed initializer whose
reply is deliberately lost. The initializer is sent once; specific ready
readback resolves it. Platform observations in that control are explicitly
simulated. Separate local collector/validator tests cover the real command
shape, file/nonce bindings, freshness and post-send writer refusal.

## Explicit operator invocation

From the exact reviewed checkout's `backend/` directory:

```sh
python -m app.services.dnpl_activation_operator execute-plan \
  --plan /absolute/private/plan.json \
  --lock /absolute/existing/LANE-integrator.lock \
  --owner integrator-v3-OPERATION \
  --run-dir /absolute/private/new-run-directory
```

This is an interface specification, not a production command grant. Integrator
must first qualify the complete operation interval, actual deployed source and
migrations, provider behavior/ACL/standby readiness, and the two-slot legacy
cutover. Stop and start remain separately controlled operations outside this
program. The command neither claims nor releases a lane lock, invokes a worker
manager, changes configuration, scans Redis, nor creates authority implicitly.

The plan file must be a private regular file owned by the invoking user, at most
64 KiB, with no duplicate JSON object keys. Its exact fields are:

- `run_id`: canonical nonzero UUID for this attempt.
- `primary`: the actual expected `run_id:master_replid` string.
- `apps`: exactly `bainluck` and `bainluck-heavy`, each containing positive
  integer `release`, canonical UUID `slug`, and exact 40-character `commit`.
  Commits must match. These are comparison targets, never receipts or permission.
- `steps`: one to eight objects, each with exactly `step`, `expected`, and
  `candidate`. `expected` uses the existing eight-field authority schema.
  `candidate` is null except for `prepare`, which requires the exact next
  allocation bound to `primary`. Only the existing runner's lifecycle and
  retirement-readback steps are accepted. The expected authority of each next
  step must match the preceding step's declared transition. Duplicate operations
  are refused before execution.

Plan-local lifecycle facts are retained during validation: preparing an
allocation establishes step zero; arm precedes initialize, which precedes ready.
The plan cannot abandon its own unready allocation or allocate again while its
known predecessor remains unacknowledged. Activation requires preparing state
and the authority's primary; retirement selects the matching normal or
replacement route. Partial/readback plans beginning against an existing
authority retain unknown starting step/predecessor state for runtime checks;
they do not erase facts established by earlier steps in the same plan.

All input is validated before clients are configured. The same explicit
`DNPL_COMMAND_DATABASE_URL` and `DNPL_COMMAND_REDIS_URL` variables select targets;
application defaults are never used. Unlike preview, operator PG connections
permit the selected writes, retaining 150ms statement/lock timeouts, independent
short controller budgets, NullPool and bounded Redis connections with no retry.
Both clients are closed even on failure.

The existing private run directory receives an exclusive, fsynced `plan.json`
before any command. It cannot be reused to replay or resume a plan. One actual
`DeskHold.capture` remains held across every step, all pre/post verifier calls
and final ready readback. Each step still goes through the accepted runner's
canonical single-send record and PostgreSQL/Lua fences. There is no alternative
direct controller dispatch or caller-supplied observation path.

`PLAN_DONE` (exit 0) means all requested steps and final hold check succeeded;
when the plan ends in `ready`, the durable ready row is also read back under the
hold. It does not start producers or establish reader/provider acceptance.
`UNCERTAIN` or `UNCERTAIN-WRITER` stops immediately, preserves evidence and exits
3; later steps are not attempted. A top-level exception after execution begins
reports `STOPPED`, `may_have_sent: true`, and only the exception class. Invalid
input reports `REFUSED`, exit 2, before client setup. Cancellation propagates,
releases the local hold and retains all written consumption records. Nothing
automatically retries a plan, allocates a successor or deletes a send record.
Specific readback requires a separately prepared explicit plan and renewed
operation qualification; a new directory is not proof of safety or continuity.

The maximum plan has sixteen verifier invocations (pre/post for eight steps).
The operation owner must budget the verifier's actual CLI/API requests, including
CLI internal calls, rather than call this an eight-request operation. Each
collection keeps the existing timeout/freshness checks; elapsed time is not a
late-command drain proof. Invocation wiring requires its own focused review and
release gates before any attended use.


## Explicit operator network budgets

The preview and execute-plan commands accept `--io-budget-ms` (default 150,
integer 1–5000) and `--preview-budget-ms` (default 1000, at least the I/O
allowance and at most 30000). The I/O setting applies separately to one
operator PostgreSQL read/transaction and one Redis checkout/connect/send/reply.
The preview setting bounds the entire six-read/INFO consistency sample, including
inside the operation runner. For example, 1000/5000 accommodates the controlled
200ms local connection-delay test; these are not measured production settings
or a guarantee that every remote request completes. Integrator selects settings
as part of its qualified operation, without spending an attempt to discover a
predictable client-side refusal.

Effective settings are retained in the exclusive `transport-budgets.json` before
any mutation and included in results. They do not change the canonical consumed
send identity. A timeout, cancellation or lost reply still ends the attempt;
selecting a larger budget is not permission to replay. The PostgreSQL step latch,
Redis admission fence, raw single-send path and zero command retries are unchanged.
Disconnect retains its separate 150ms cleanup allowance; pool release and OS
scheduling remain outside a claim of hard end-to-end real-time completion.

Only the explicit operator/preview factories select OperatorAuthorityStore.
Normal AuthorityStore still refuses budgets above 150ms; producer sampling even
on the operator subclass delegates to a normal 150ms store. Existing SQL
statement/lock limits (100ms in control transactions, 150ms connection defaults),
live preview TTLs, fanout deadlines, writer-observation freshness (120s) and clock
skew checks are unchanged. A longer preview may consume the observation freshness
budget: the runner still refuses before send if it is stale. There is no refresh
retry or extended writer-exclusion claim.

The total operation can contain multiple bounded calls and up to eight steps;
it is not bounded by one I/O or preview allowance. P-EXCL must cover the complete
qualified interval. These options change how long an attended caller waits for
the same operation, not server lock occupancy or any probability-delivery target.
The separately accepted 6468 release remains independent of this successor.
