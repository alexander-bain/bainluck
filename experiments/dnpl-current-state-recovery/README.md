# DNPL current-state recovery: evidence and isolated prototypes

**Draft owner handoff only. Nothing here is imported by the application.** This directory consolidates corrected client lease handling, a numeric-corrected singleton atomic-authority model, and additive producer-chain metadata. They are independently tested pieces, not one wired or production-ready implementation. No deployment, retry-hint change, second stream, production traffic, or rollout gate is proposed.

## Why this exists

The earlier cloud experiments located avoidable waiting when an already valid preview was lost during a stream gap and the client then waited for another publication. Healthy connected delivery was much faster: original synthetic observation to changed DOM was 43.9–65.3 ms (publication to DOM 11–22 ms). The post-cue stable near-opacity proxy was 373.8–405.9 ms. These are historical fixture results, not physical paint, current venue measurements, or production maxima.

The prompt-only paused-flush arm recovered the target in roughly 0.72 seconds from original observation. A separate final explicit-pending arm first changed DOM in roughly 0.739 seconds, then withdrew the number for 23.1 ms at native reopen instead of falsely reverting to the old probability. Its stable uninterrupted recovery still took roughly 4.96 seconds from observation. Native 5-second reconnect remained unchanged in both. The full history retains executor stalls, missing targets, and an over-10-second arm. **There was no universal worst-case win.** See `evidence/history/browser-structural-results.json`; no new browser benchmark was run for this consolidation.

## Selected implementation, deliberately not wired

- `monotonic-candidate/`: corrected GET request-start monotonic lease cap, actual hook/reader, one-shot policy and pending hero. Expired/empty late responses retain the cap; native reopen and repeated same-chain previews cannot freshen it. Older prompt/pending implementations and the old full EventPage are not supplied as implementation choices.
- `atomic-numeric-encoding/`: the only selectable authority Lua and command adapter. Strict decimal parsing and exact serialization avoid Lua 5.1 owner/sequence rounding, preserve revokes/floors, and disable replay after optional retention failures. Tests execute exact Lua with fake Redis commands, not a Redis server.
- `producer-chain-metadata/`: a one-file additive registry patch over b2b92fe. Pending-chain identity/deadline survive changed values, quiet retries, claim filling and sibling settlement. The actual publisher's ordered batch/claim/ambiguous-ACK behavior is unchanged. Command-generation composition is NOT an atomic batch implementation.
- `fixtures/authority_model.py`: process-local server snapshot model used only for protocol tests. It is not Redis-backed route code.
- `review/`: dated independent receipts and reproducible checks. Their original hashes refer to the frozen earlier packets; `PROVENANCE.json` records the selected copies and path-only edits.

## Critical remaining limits

The three pieces are not end-to-end integrated. A real atomic **batch** publication adapter, durable/non-evicted ordering keys, status/SQL coverage and its post-read notification boundary, a fresh no-store current-state endpoint, route subscription/coverage ordering, current page adoption wiring and owner review remain. Producer-to-Redis clock alignment and a coherent non-increasing server remaining budget are still assumptions. Only GET-bound chains remove arbitrary client wall-clock skew; unbound SSE, client monotonic suspension/rate behavior and real Redis OOM behavior are not solved.

The separate `real-redis-unexecuted/` harness now pins and dispatches the corrected Lua/adapter; three import/selection tests pass, but its 23 real-engine cases are unexecuted. The original blocked harness selected an older Lua and is not evidence for the numeric fix.

No real Redis case ran: the permitted Unix-only local server launch failed before tests. Its blocked-runtime receipt is preserved. Optional retention failures are model-tested, not a guarantee that actual Redis admits a script under memory pressure. Independent hash/counter loss remains an explicit prerequisite failure, not covered eviction safety. A disabled epoch intentionally stays replay-disabled until a new claim.

The existing owners retain their work: Live for DNPL delivery, UX recovery for recovery/adoption, and Speed for same-value observations. No observation timestamps are restamped here. Observation-only producer previews do not necessarily create lock-retry debt, so the earlier quiet 2-second locked-row republish fixture must not be generalized to them.

## Validation and publication status

See `RUN.md` for focused reproduction, `INTEGRATION.md` for required aliases and page/wire contracts, and `GATES.md` for current repository gates. A successful full application build validates the unchanged app with evidence-only additions, not a composed implementation. Historical receipts saying build approval was pending are dated history; the user authorized the Sentry-metadata-bearing build on 2026-10-21 at 15:41 UTC. No Sentry credentials or expanded source upload are supplied.
