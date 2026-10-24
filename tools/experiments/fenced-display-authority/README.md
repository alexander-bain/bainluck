> Security follow-on: read [the journal/output hardening scope and current verification](../SECURITY-UPDATE.md). Historical measurements below are not new-source reruns.

# Fenced display-authority experiment

## What this candidate adds

A single broker owns publication authority, atomically registers a subscriber with
its snapshot, fences epochs/sessions, and anchors leases to fresh challenge origin
rather than response arrival. It rejects ownerless startup and nonce replay. A
local optional journal persists control/publication custody before publication.

Start with `src/{broker,client,protocol,journal}.mjs`, then the 36 model checks,
`src/schedule-matrix.mjs`, `src/crash-matrix.mjs`, and the independent `review/test_*.mjs`.
The `baseline/` modules deliberately freeze the older recovery candidate for negative
controls and comparisons. They are not a production import or an attempt to silently
upgrade the baseline's semantics.

Requires Node >=22, npm, Bash, and installed PostgreSQL tools. From this module:

```sh
npm ci --ignore-scripts
npm test
```

The runner creates a unique database directory under `runtime/`, binds only
127.0.0.1, verifies its owned process/data-directory/port before connecting, and
stops that cluster on exit. It refuses an occupied port rather than using the
existing server. Set `PG_BIN` if initdb/pg_ctl are not on PATH; relocated installs
can also set `PG_SHARE`. Set `PGPORT` to another unused unprivileged port if needed.
Do not supply production credentials. The stopped cluster remains for inspection.
PG entry points are internal to the runner, not commands for an existing database.

The dependency is pinned `pg` 8.23.1. A clean online dependency installation was
not verified here; local checks used the existing exact-version installation.
The earlier offline install attempt lacked a cached transitive tarball. A passing
local fixture does not replace repository-wide CI or production integration tests.

`npm test` runs model/independent checks, schedule and SIGKILL matrices, a real owned
PostgreSQL outage/restart, and synthetic model timing cells. `npm run test:model`
omits PostgreSQL/outage/benchmark stages, but still needs the installed pg package
because the frozen baseline module imports it. The optional `node browser/server.mjs`
is a separate loopback browser fixture on port 4658, bounded to 30 minutes. It has
not been remeasured in a browser as part of the PR packaging rerun.

## Limits that remain

- A frame taken before handover can arrive before invalidation, within the old lease.
  The experiment reproduces that residual rather than asserting it cannot happen.
- A blocked JavaScript thread cannot execute lease-expiry cleanup on its deadline.
  Eligibility expiry is not a physical-screen clearance bound.
- The broker is assumed authoritative and singular. A local journal does not enforce
  cross-machine singleton ownership, replication or source freshness.
- Snapshot recovery is latest state, not proof of complete intermediate history.
- Final original model-observation timing included a 2.063-second outlier. No
  subsecond maximum or combined raw-input-to-display bound is established.

## Packaging changes

From `fenced-display-authority-20261020.zip`: remove machine-specific fallback paths
and use a safe owned-cluster runner; require owned data/port verification at SQL
construction. Source hash pins distinguish this packaging from original measurements.
Pure broker/client/protocol/journal logic and original assertion bodies are retained.

## Isolation and reproduction

This is an opt-in synthetic experiment, not application integration or permission
to merge/deploy. All fixtures are generated in the runner; no production feeds,
credentials, raw recordings, private file links, database files, or installed
packages are included. The repository [MIT license](../../../LICENSE) applies.
`results/original-source-sha256.json` pins the imported experimental source;
`results/source-sha256.json` pins the packaged runnable source. Generated receipts
and temporary state are gitignored. Detailed original evidence remains in the
separately supplied archive, not this repository.
