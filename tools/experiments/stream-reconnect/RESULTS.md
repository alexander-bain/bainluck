# Real-stream results and timing scope

> Targeted follow-on: [event-driven renewal confirmation](../RENEWAL-UPDATE.md).
> Historical results below describe the pre-renewal source; new targeted verification is separately pinned.

## Verified original source

The final exact-source Node run passed 20 real-wire scenarios and zero-socket
shutdown. There were 36 inherited model checks, four transport regressions and
16 independent pure checks. The deeper audits passed 3,008 assertions for final
Node20 and 4,738 for Browser20.

The Browser20 run preceded the final expired-initial-handshake cleanup guard.
Do not label its timing measurements a post-guard browser run. Final Node20 covers
the exact frozen source after that guard. The PR packaging rerun is recorded in
`results/verification.json`; it is not a new browser timing experiment.

## What improved, without overstating it

Real socket loss leads to a fresh connection/session/challenge rather than reviving
old callbacks. Delayed old-response callbacks stay bound to their original closed
connection. Removing the baseline's explicit 75 ms retry sleep removes that chosen
harness timer; scheduling and authority-control round trips remain. Three original
zero-timer reconnect-to-DOM samples were 27.3/47.2/73.6 ms, finite lab observations,
not a worst-case unnecessary-delay bound or a randomized causal comparison.

Normal publish timings start **after** ensureAuthority(), excluding five renewal
waits (maximum 103.0 ms to renewal completion; 106.2 ms to the next synthetic publish
request). Matched renewal-trigger to that same publication's DOM reached 205.9 ms.
The full iteration/user-intent-to-DOM interval is unknown because it lacks a start
timestamp. This pre-generation authority check is not evidence that an already
arrived real producer update was held. Do not add unmatched maxima.

## Negative controls stay visible

Observed sequences [1,3] after an omitted intermediate remain incomplete history,
not a recovered sequence 2. A missing final publication recovers only through a
later renewal snapshot. Already-taken old bytes before a fence, withheld fences and
intentional main-thread stalls demonstrate residual stale/unavailable intervals.
Backpressure is not solved in this baseline. No production, live capture,
Internet-partition, source-freshness, full-history or physical-paint guarantee is
established by these checks.
