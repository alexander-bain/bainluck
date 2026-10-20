# Targeted renewal confirmation update

This separate experimental follow-on changes only the two stream-module wire wrappers, focused synthetic tests/runners, and their review evidence. It does not integrate the composed recorded-input harness, change production code, extend TTLs, change source/estimator policy, or authorize merge/deployment.

## Reuse boundary

The same reviewed `src/wire-client.mjs` is copied into `stream-reconnect` and `stream-backpressure` (SHA-256 `bcb35334f4ebdaf23298ee90db638f573ac3faca14b34c61f65e985b2005e25f`). The frozen `Client`, protocol, broker, journal, writer and server are unchanged. Explicit stream forwarding retains the `synthetic-stream` default. Source fixtures in these PR tests are synthetic; they do not reproduce the separate recorded-input measurements.

The previous wrapper could wait for a control HTTP response after a valid matching SSE renewal snapshot had already arrived. A later polling candidate removed that wait but could still lose accepted proof to scheduler/observer delay. The replacement settles its promise in the same task immediately after `Client.accept`, before observer/render work, only for the pending request's accepted nonce/session/stream/boot/epoch/owner proof and its original unexpired request-time-plus-TTL deadline. The SSE receipt timestamp is still captured before JSON parsing.

The returned proof means **valid at `confirmedAtMs`**, not guaranteed current authority when an awaiting consumer resumes. A callback or scheduling pause can outlive that deadline; callers must still consult `Client.tick()`. HTTP success alone is not proof. An HTTP error does not discard an independently arriving valid proof before its deadline. Completion aborts only its matching HTTP work, stale callbacks cannot clear a newer slot, and unresolved controls are capped (default two). If transport ignores abort, occupied slots can refuse further renewals rather than grow without bound.

## Separate integrated evidence, not a clean acceptance result

- Original normal composition retained all 77 outputs in WAL/PG but displayed only 76 unique identities. Live seq41 expired; latest-only renewal restored seq42 without backfilling seq41. The maximum scheduled-input-to-DOM observation was 1,857.2 ms, conditional on those 76 displayed outputs.
- An intermediate polling candidate delivered only 54 of its 63 actual elapsed outputs and had 20 distinct failed renewal requests. It is not the implementation committed here and is not presented as a successful integration.
- One final event-driven normal run produced **75 actual outputs**, all exact through stdout/WAL/broker history/PG and all reaching 75 unique DOM identities (77 assignments include two restorations). The recorded-mode 77 count is not imposed on elapsed mode.
- Of 362 distinct renewal requests, 358 received valid, nonce-specific confirmation before expiry, all while HTTP responses remained pending. No accepted-unexpired proof was lost to polling. Four requests failed and generated 15 repeated caller error reports across startup, replay and completion. Thus this was **not an error-free end-to-end run**.
- Worst actual Node-input-to-DOM observation was about **1.411 s** (about 1.506 s scheduled-to-DOM), not a universal bound. Clock mapping carries uncertainty; observed DOM assignment is not physical paint. One shared-host run does not isolate causal improvement from load variation.
- The later forced-reconnect composition is **incomplete**, with no final browser receipt, and is not counted as a pass. Pure/mock contracts and the existing synthetic loopback suite do not substitute for that missing evidence.

The baseline slow-PG run displayed all 77 unique outputs, with maximum Node-arrival-to-DOM 379.5 ms while PG verification took 1,207.7–2,462.8 ms. Its live-versus-saved late-close error discrepancy remains disclosed; do not label it clean.

## Packaged verification: explicitly partial

The new synthetic renewal contracts passed 28/28, and the adapted reconnect pure contracts passed 16/16 in independent execution. The reconnect model (36) and transport (4) checks also passed. The existing real-loopback reconnect suite finished **18/20**, then exited nonzero: `held-old-before-fence` and `held-old-after-fence` timed out. This is not a clean compatibility result, and no rerun is substituted for it.

In both failed cases, the 1,500 ms lease expired during preceding control-response waits before the decisive held publication/fence arrived. The unchanged model correctly refused expired numerical authority. Neither trace contains a renewal request or reaches renewal-specific proof settlement. However, the changed constructor/API/receive wrapper and its no-pending-proof hook do execute; these receipts do **not** prove zero scheduling impact or universal compatibility. The exact client traces from both synthetic failures are retained in `stream-reconnect/tests/fixtures/held-fence-failures.json`, pinned to the original full receipt digest. A deterministic replay passed 2/2 against both the unchanged Client and the changed wrapper; this does not replace the failed 18/20 wire result. Cleanup evidence is recorded separately. No TTL or source-policy change was made to force a pass.

The pressure module separately passed 15 writer units, all six pressure-wire cases (including the expected failing-baseline control), 21 independent checks and the independent six-case wire audit. Its separate 20-case reconnect suite was not rerun after this update. All executed real-wire servers stopped with zero sockets/labs. The whole combined `./run.sh test` entry points are not claimed green.

## Verification and provenance

Run each stream module's `./run.sh test` with Node >=22. Focused tests use generated synthetic frames and mocked controls; real loopback cases remain distinct. New verification is in each module's `results/renewal-verification.json`, with current hashes in `results/source-sha256.json`. Predecessor receipts and their exact post-run source manifests remain in `results/verification.json` and `results/source-sha256-before-renewal.json` at parent commit `58de889adbf63d5c659f19802602faaf8a07b964`. None is relabeled as a new-code browser rerun.

Latest-only history, authority-versus-source freshness, cooperative expiry/stall deadlines, unresolved original timing outliers, and pressure-buffer scope limitations remain unchanged. This update removes a specific control/proof orchestration wait; it does not establish production readiness or a maximum unnecessary-delay promise.
