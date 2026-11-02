> Security follow-on: read [the journal/output hardening scope and current verification](../SECURITY-UPDATE.md). Historical measurements below are not new-source reruns.

# Real loopback SSE reconnect experiment

> Targeted follow-on: [event-driven renewal confirmation](../RENEWAL-UPDATE.md).
> Historical results below describe the pre-renewal source; new targeted verification is separately pinned.

## What this candidate adds

The frozen authority model is exercised over real loopback HTTP/SSE sockets:
actual socket destruction/reconnect, old-response callbacks, fresh session/challenge
renewal, duplicate and omission handling, and cleanup after an expired initial
handshake. A zero-timer reconnect variant is compared to an explicit 75 ms baseline
retry timer. No production transport is imported.

Read `src/stream-server.mjs`, `src/wire-client.mjs`, the shared scenarios and tests,
then `RESULTS.md`. `src/{broker,client,protocol,journal}.mjs` is a frozen copied
version, intentionally separate from the slow-client follow-on. Journal is used
only by inherited model tests, not the SSE server.

## Run

Node >=22, POSIX Bash/mktemp. No npm dependencies or installation required.

```sh
bash run.sh test
node --test tests/reviewed-pure-adversarial.mjs
node tests/independent-audit.mjs results/wire-receipt.json
```

`run.sh test` runs 36 model checks, four transport checks, 20 actual loopback
stream cases and a receipt audit, then verifies zero remaining labs/sockets.
Generated raw receipts remain local and gitignored. The runner selects fresh model
output; use it rather than invoking inherited-model directly with its legacy /tmp
fallback. Set NODE_BIN if necessary. Processes are bounded to 30 minutes.

For an optional new browser run: `bash run.sh serve`, open 127.0.0.1:4660, click
Run all 20 checks, and stop the server afterward. The runner does not launch a
browser. STREAM_PORT changes the loopback port; STREAM_OUT changes output.
The server validates local Host and same-origin mutation requests. All controls
affect ephemeral synthetic state only.

## Important limits

- res.write(false) is recorded but this baseline does not implement drain-controlled
  backpressure. Its successor slow-client module is separately reviewed; do not
  silently apply that successor's guarantees to this version.
- Initial/reconnect snapshots recover latest state, not missing intermediate history.
  Omitted-intermediate and omitted-final cases remain explicit evidence.
- A simulated matching storage ACK is not proof of a database/disk commit.
- Leases establish contact with the assumed single broker, not source freshness,
  owner liveness, probability quality or distributed singleton enforcement.
- Withheld fences, already-in-flight old bytes and main-thread stalls retain residual
  stale/unavailable intervals. Loopback faults are not arbitrary Internet partitions.
- DOM writes and second-rAF observation are separate; neither certifies physical
  paint. No remaining-unnecessary-delay or universal end-to-end bound is claimed.

## Packaging and source version

Runtime/test source is copied from the final source freeze in the separately supplied
stream-reconnect experiment. SOURCE-HASHES pins the shared authority modules;
the scoped manifests pin the full PR module. No runtime algorithm is changed by
packaging. Historical receipt paths are not required to run the new synthetic suite.

## Isolation and reproduction

This is an opt-in synthetic experiment, not application integration or permission
to merge/deploy. All fixtures are generated in the runner; no production feeds,
credentials, raw recordings, private file links, database files, or installed
packages are included. The repository [MIT license](../../../LICENSE) applies.
`results/original-source-sha256.json` pins the imported experimental source;
`results/source-sha256.json` pins the packaged runnable source. Generated receipts
and temporary state are gitignored. Detailed original evidence remains in the
separately supplied archive, not this repository.
