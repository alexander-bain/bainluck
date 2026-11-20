# Provisional publication recovery

## What this candidate adds

Retain unresolved jobs after bounded retries, restore the same owner's provisional
latest value on reconnect, and compare memory-only, post-publication WAL, and
pre-publication fsync recovery. PostgreSQL writes are identity-bound and generation
fenced; replay restores historical custody without promoting an old epoch to current.

Read `src/candidate.mjs` first, then `src/test.mjs`, `src/outage.mjs`, the five
independent checks in `review/test_recovery_adversarial.mjs`, and `RESULTS.md`.
`baseline/client-core.mjs` is a frozen earlier validator, not a production import.

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

`npm test` runs 29 candidate checks (including 26 actual SIGKILL scenarios), five
independent adversarial checks, an immediate-stop/restart of its own PostgreSQL,
and six 120-offer synthetic timing cells. Negative-control PASS means the expected
limitation was reproduced, not that it was repaired.

## Limits that remain

- Memory loses pending publications on owner death. WAL-after narrows but does not
  eliminate that window. WAL-before persists before display, adding deliberate
  local durability work to the display path.
- PostgreSQL generation fencing does not fence every live display. Already-connected
  old clients and a reconnect check/use race are reproduced as negative controls.
- No distributed authority, source freshness, real transport, production rollout,
  browser paint, or end-to-end latency bound is claimed.
- The WAL is local to this host, not replicated and not a replacement for a production
  storage/recovery design. Offer/callback timings are not browser measurements.

## Packaging changes versus the original archive

Taken from `provisional-recovery-20261020.zip`. The new safe local runner removes
machine-specific dependency paths; database construction validates runner ownership.
Crash-child paths use fileURLToPath so checkout spaces are literal. Independent
review's temporary directory gets the same URL correction. Algorithm/fixtures remain
separate from the newer authority and real-stream implementations. The earlier
baseline tests are retained in the sibling display-before-persist module instead
of being copied again here.

## Isolation and reproduction

This is an opt-in synthetic experiment, not application integration or permission
to merge/deploy. All fixtures are generated in the runner; no production feeds,
credentials, raw recordings, private file links, database files, or installed
packages are included. The repository [MIT license](../../../LICENSE) applies.
`results/original-source-sha256.json` pins the imported experimental source;
`results/source-sha256.json` pins the packaged runnable source. Generated receipts
and temporary state are gitignored. Detailed original evidence remains in the
separately supplied archive, not this repository.
