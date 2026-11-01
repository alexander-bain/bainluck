# Display before persistence: isolated review candidate

**Draft experiment, not production integration or merge/deploy approval.**

The user-visible goal is to stop a validated probability waiting for a PostgreSQL
commit before it can be displayed, while being honest that an uncommitted value
is provisional. This first handoff isolates that mechanism for acceptance,
rejection, or adaptation by the main implementation thread.

## Review order / index

1. `src/pipeline.mjs`: display-first versus commit-first, bounded asynchronous
   persistence, idempotent retry, explicit failure/unknown states.
2. `src/postgres.mjs`: exact-identity/hash reconciliation and monotone latest row.
3. `src/client.mjs`: run/epoch/sequence fencing; persistence ACKs are status-only.
4. `checks/unit.mjs`, `checks/postgres.mjs`: synthetic invariants, real PostgreSQL
   failures, out-of-order commits, lost commit ACKs, and an actual SIGKILL.
5. `RESULTS.md`, `results/verification.json`: what was actually run and its limits.
6. `PROVENANCE.md`: code hashes, source attribution and separate experiment inventory.

All additions are confined here. Nothing imports the application, changes an
estimator, starts automatically, enters production test discovery, edits a root
manifest, or alters CI/deployment configuration. Tests are explicit `.mjs` entry
points rather than automatically discovered `test*.py` or `*.test.*` files.

## Run the small synthetic fixture

Prerequisites: Node 22+, npm, and an existing local PostgreSQL installation
(tested with Node 24.19.0 and PostgreSQL 17.11). Do not install or run this at the
repository root. Do not supply a production database URL or credentials.

```sh
cd tools/experiments/display-before-persist
npm ci --ignore-scripts
npm run test:unit
npm test
```

`npm test` creates a new, disposable loopback-only database cluster under
`.runtime/`, runs the 19 explicit checks, and stops that cluster on exit. It does
not connect to an existing PostgreSQL server. If PostgreSQL's tools are not on
PATH, set `PG_BIN` to the installed bin directory. A relocated installation may
also require `PG_SHARE` pointing to its shared-data directory. `PGPORT` defaults
to 55491; choose another unused unprivileged port if necessary. Startup fails
rather than connecting to another server if the port is already occupied.

Both `.runtime/` and `local-results/` are ignored. The stopped test cluster remains
for inspection; delete that experiment-owned directory when no longer needed.
The PG checks verify the runner-owned data directory and port before connecting;
do not invoke them directly. Only this directory's pinned `pg` dependency is required. There are no install or
postinstall hooks. `npm run test:unit` itself needs no PostgreSQL or `pg` import.

The fixtures create small synthetic probabilities in memory. They test ordering
and failure semantics, **not** the previously recorded market's latency numbers.
The historical full-recording results below require the separately supplied
source/evidence ZIP; this small rerun cannot reproduce them. No raw recording,
private download URL, copied full repository, database, credentials, or installed
dependency tree is committed here.

## Boundary of the candidate

- SQL identity is `(run, arm, epoch, event, seq)` plus a payload SHA-256. Payloads are
  copied at admission. Each client model must receive only one arm, and epochs
  must differ between arms: the baseline client does not validate `arm`. This is
  a trusted in-process/wire harness, not an
  authenticated or canonicalized network protocol: the client does not recompute
  the payload hash, and a malicious publish callback is out of scope.
- Capacity includes queued and in-flight jobs (default 64/4). Admission refusal
  produces `not-queued` in display-first, not a false persistence promise.
- Three attempts maximum. A proven commit or exact-key/hash reconciliation is
  `durable`; a commit with unresolved outcome is `outcome-unknown`.
- A memory queue is **not** a durable outbox. A killed owner can lose already
  displayed provisional entries. A fresh epoch clears state; it does not recover
  lost entries. There is no journal, leader election, distributed display lease,
  reconnect protocol, live source freshness guarantee, or production rollout.
- The identity cache is deliberately limited to 256 offers per pipeline. This
  finite-run model is not suitable for an unbounded production stream.
- A second requestAnimationFrame observation is not a certified physical paint.
  Synthetic callback/SQL tests establish no browser or production latency bound.

## Repository checks

The current repository CI treats this path as full scope. Its production tests
are not replaced by these checks, and the root CI is not modified to run this
experiment. Existing required checks must be assessed separately for the exact
PR head. The repository's `tools/` path is excluded by its current Heroku release
classifier, but **this is not permission to merge**. No merge, deployment, or
production setting change is part of this handoff.
