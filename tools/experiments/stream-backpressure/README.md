> Security follow-on: read [the journal/output hardening scope and current verification](../SECURITY-UPDATE.md). Historical measurements below are not new-source reruns.

# Bounded SSE backpressure laboratory

> Targeted follow-on: [event-driven renewal confirmation](../RENEWAL-UPDATE.md).
> Historical results below describe the pre-renewal source; new targeted verification is separately pinned.

This is an isolated synthetic follow-on to the real-loopback reconnect experiment. It is not a production integration. Client, protocol, broker, and journal are copied unchanged. No market data, live capture, remote service, database, credentials, or Internet request is used.

## Run

Requirements: Node.js 22+; no npm dependencies or install. Verified here with Node v24.19.0.

```sh
./run.sh test       # all four unit/model families and both real-wire suites
./run.sh pressure   # baseline failure controls, writer units, pressure TCP cases
./run.sh model      # inherited protocol/storage model only
./run.sh serve      # optional local browser laboratory, not used in pressure verification
```

Set `NODE_BIN` if needed. Each wire suite binds an ephemeral 127.0.0.1 port and closes its listener/sockets in `finally`. The pressure runner has a 90-second watchdog, less-than-30-second per-burst assertions, at most three simultaneous SSE clients, at most 5,000 produced frames per case, and a 2 MiB per-client application/Node safety ceiling. Normal candidate configuration is stricter. The optional manual server defaults to port 4660 and auto-stops after 30 minutes. Stop it with SIGINT/SIGTERM or its same-origin shutdown API.

Rerunning tests replaces corresponding files in `results/`. Copy an evidence directory before rerunning if you need to retain this specific receipt. Source hashes in the pressure receipt bind the tested writer, server, runner, and frozen protocol modules. All checks ran against the final code; `run.sh test` aggregates those same commands. No candidate browser execution was claimed.

## Defect demonstrated before the fix

The preserved original server ignored `ServerResponse.write(false)` and continued writing. The unchanged mock baseline made 258 writes with no drain, retaining 168,865 bytes; both stop-after-false and finite-deadline safety assertions failed as expected. The real-TCP baseline used a genuinely paused HTTP reader and instrumented actual writes/drains: 49 further writes occurred without an intervening drain. Its measured peak Node queue was 82,904 bytes. The baseline run stopped safely rather than exhausting memory. These finite failures show missing protection, not an observed unbounded allocation. Baseline and candidate stress workloads differ in SSE padding; their numbers establish safety invariants, not a direct performance ranking.

`baseline/stream-server.mjs` and its imports are preserved copies. `evidence/baseline-failures.json` contains the intentional failing assertions. The baseline case is marked `expectedSafetyFailure`, not a healthy-server pass.

## Candidate design

`src/bounded-sse-writer.mjs` is the small, dependency-free transport addition:

- Write immediately while writable. Once a write returns false, never call write again before drain.
- Bound queued SSE frames (64), queued encoded bytes (128 KiB), each encoded frame (16 KiB), and the aggregate waiting bytes plus Node `writableLength` (256 KiB by default). Admission reserves 32 bytes per queued frame for Node HTTP chunk framing.
- Disconnect, clear the queue, detach callbacks, and cancel the timer on overflow, oversize frame, write exception, response close, or drain deadline. Default deadline is 250 ms. The wire stress fixture uses 400 ms to distinguish no-drain behavior from scheduling noise.
- Validate current epoch/owner/status immediately before response.write and when admitting a frame. If ownership or terminal status invalidates an unsent backlog, disconnect instead of allowing a fence to wait behind stale queued frames.
- Protect against reentrant close/enqueue callbacks and reject invalid limits before a server/lab/session opens.
- Keep the healthy client's path independent; no persistence ACK, artificial batching delay, or retry sleep is added to display.

The client and broker protocol do not change. After a bounded disconnect the consumer explicitly opens a fresh session/challenge and accepts a current snapshot. A reconnect/renewal is latest-state recovery, NOT complete historical replay. Intermediate data can be lost at disconnect; this is disclosed and tested, never silently filled in or labeled complete. A reconnect loop/backoff policy is outside this writer.

The inherited held-old-frame fixtures now have stronger expectations: an old frame still waiting in the server application is refused before response.write, and a fresh snapshot restores latest. The original fixtures/auditor are retained under `baseline/`. This does not retract bytes already accepted into Node, the kernel, a proxy, or the peer.

## Verified cases

- 15/15 focused writer tests, including byte/frame limits, repeated false/drain, oversized frame, no-drain timer, abandon cleanup, late drain, stale owner, terminal backlog, write exceptions, invalid configuration, and reentrancy.
- 36/36 inherited protocol/storage model tests and 4/4 transport-unit checks.
- 20/20 real reconnect/regression cases, with 1,134 offline receipt assertions.
- Six pressure wire cases: the failing baseline positive control plus five candidate checks. Those cover a paused reader alongside a healthy reader; abandoning a blocked socket; actual drain/resume; no-drain deadline; and ownership handover with a queued old-owner backlog.
- Independent reviewer: 21/21 additional no-socket tests and all six pressure receipts audited. Review also checks partial-frame EOF recovery, missing-history honesty, final values, no writes between false/drain, no post-close writes, measured limits, and exact source hashes.

See `RESULTS.md` and `evidence/original-summary.json` for observed numbers and source hashes. Full synthetic traces are intentionally excluded from the PR and regenerated by the runner. The small original summaries in evidence/ identify the historical measurements; results/verification.json records the packaged rerun.

## Measurement boundaries and remaining limitations

The 256 KiB bound covers this writer's queued encoded strings plus Node's response `writableLength`, with HTTP framing reserve. It is not a process-RSS, operating-system/kernel, proxy, client, producer-history, broker-journal, or cross-machine memory bound. Only this writer may write the response. Message strings already allocated by a caller are not retroactively bounded. This laboratory's producer constructs small fixed-schema synthetic frames; the stress size is harmless SSE comment padding, not an enlarged protocol payload. The broker retains its own independent frame/history limits. A generic untrusted payload integration would need ingress byte bounds too.

A false write has already accepted those bytes; they cannot be recalled. The client can still receive old bytes that entered the kernel before a later ownership change, especially before it observes a fence. Frozen client epoch/lease validation remains necessary. The timing fixtures use a 30-second client lease to isolate pressure, whereas the normal server keeps the predecessor's 1,500 ms default. Neither is a source-freshness certificate.

Timers are scheduler-dependent, not hard elapsed-time bounds. The 400 ms no-drain timer was observed at 456.9 ms in this run. A blocked event loop, unreachable peer, failed reconnect, missing final update, or unavailable source can still delay useful output indefinitely. This local finite experiment provides no universal Internet/production latency guarantee.

Server envelope `writeReadyMs` is retained for compatibility but denotes bounded-writer enqueue. `wire-write.transport.actualResponseWriteMs` and `readyToResponseWriteMs` denote actual response.write invocation; neither is network delivery or physical display. All timing uses one local monotonic clock per side. No clock alignment or physical-pixel measurement is claimed.

The receipt system itself is a bounded synthetic audit, not a production telemetry implementation. Storage durability is unchanged: `pending` values display immediately, and a simulated ACK does not prove database/disk persistence.

## PR packaging and independent review

All runtime/test code is retained from the frozen module. Original measurements
are in evidence/; reruns write only gitignored results/. No raw trace or private
file URL is needed. The additional independent reviewer scripts are adapted only
for relative source/receipt paths and literal checkout-path decoding. After the
full suite, run `bash review/run-review.sh` for the baseline failure control,
21 candidate checks, and an audit of the newly generated six-case wire receipt.
The repository [MIT license](../../../LICENSE) applies. Source manifests pin both
original and packaged files. This is not application integration or merge approval.
