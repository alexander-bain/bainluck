# Independent review: bounded GET monotonic lease follow-on

Reviewed October 21, 2026. Separate local test evidence only. The delivered structural v2 archive, pinned source and earlier captures were not changed. No browser timing run, production operation, full application build, push or deployment was performed.

## Finding

The request-start lease is conservative under its stated duration contract. If the request starts at real time t0, a fresh coherent server snapshot occurs at t1 >= t0, and its remaining duration R is no greater than E - t1 for fixed original expiry E, the client deadline t0 + R is no later than E. Outbound, server-processing, inbound and callback delay consume the lease instead of renewing it. Client wall-clock offset and jumps are absent from GET-bound admission, render eligibility and expiration.

The implementation captures the monotonic start locally immediately before fetch, validates the budget, and uses a private object binding rather than trusting JSON to supply a local timestamp. Persistent same-chain caps survive visible overlay clearing, native-open recovery and higher live sequence numbers. Revokes, epoch ordering and committed floors remain dominant. The pending/unavailable presentation contract is unchanged.

An independent mounted counterexample found that an expired-before-settlement GET initially discarded its cap: a buffered higher-sequence frame from the same chain could then revive via the old wall-clock path after rollback. The correction records well-formed expired/zero budgets as non-renewal constraints without displaying authority. The final checks cover both frame-bearing and empty-expired responses, plus tightening an already-held equal-sequence lease. Initial failed outputs remain alongside the final passing output.

## Validation

All 17 independently authored mounted React/jsdom checks pass against the final frozen candidate:

- Initial wall offsets of -2e12, 100000 and +2e12 ms; forward/backward jumps during and after the request.
- Delayed body/JSON settlement and exact-deadline rejection.
- Same-chain higher live sequence, equal-sequence native-open rehydration, expiry followed by a same-base update, and no later renewal.
- Revoke and committed floor precedence, actual page-adoption cancellation and hidden late response.
- Refusal of wire-forged local deadlines.
- Expired response and empty-expired snapshot retaining the cap; same-sequence GET tightening held authority.

These tests mount the actual hook and reader with a controlled transport/controller boundary, fake timers and independent wall/monotonic clocks. They are not native-browser, physical-display, server-storage or production-load tests. The implementer's separate 82 JavaScript checks, eight server-budget checks and isolated dependency-closure typecheck are recorded elsewhere; they must not be described as full-application validation.

All 10 entries of `monotonic-review/FROZEN-CANDIDATE.json` matched before and after the final independent run. Exact input and test hashes are in `final-inputs.json`; final output is `mounted-results-final.txt`. Reproduce from the workspace root:

    node --test review/monotonic-get/test_mounted_get_expiry.cjs

## Scope and remaining assumptions

This resolves the client wall-clock dependency only for a request-bound chain. Unbound SSE retains the prior bounded-skew experimental policy. The proof requires a fresh uncached response computed for this request, coherent server remaining duration that cannot increase through a server clock rollback, stable chain identity, and a client monotonic clock whose elapsed duration continues appropriately. Suspension or unbounded rate errors invalidate that duration proof. A stalled render thread cannot promise physical-screen withdrawal at an exact instant. The fixed 60-second maximum is experimental scope, not verification of deployed overrides.

Real atomic retention, complete status/owner-loss authority, endpoint authentication/backpressure/capacity and broader recovery integration remain owner work. This adds no latency measurement or production recommendation and does not claim the earlier interruption has disappeared.

## Separate ACK-test reconciliation

`review/queued-ack-synchronization-repair-receipt.md` documents the original failed setup assertion without relabeling it a pass. A controlled diagnostic demonstrated that its inner MGET barrier could escape through the real 250 ms read timeout. The separate synchronized test holds the completed read outside that timeout and passed three old/fixed pairs. It supports the route-ordering correction but does not identify the unique historical cause of the uninstrumented failure. The original failure log and delivered archive remain unchanged.
