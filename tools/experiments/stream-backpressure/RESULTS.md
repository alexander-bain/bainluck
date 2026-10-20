# Verified outcome

> Targeted follow-on: [event-driven renewal confirmation](../RENEWAL-UPDATE.md).
> Historical results below describe the pre-renewal source; new targeted verification is separately pinned.

Final pressure run: 2026-10-20 14:41:12–14:41:30 UTC. All its listeners and sockets closed; final labs/sockets were zero. Results are observed synthetic loopback values, not latency promises.

| Check | Observed result |
|---|---|
| Preserved mock baseline | 258 writes despite false, 168,865 queued bytes, no drain deadline; 2 expected failed safety assertions |
| Real baseline | 49 writes after false before any intervening drain; peak Node queue 82,904 bytes |
| Candidate paused reader | Closed at queue limit; peak app+Node bytes 196,298, within 262,144-byte configured cap |
| Concurrent healthy reader | All 491 publications, exact final p=0.91, no duplicate numeric points, all pending without storage ACK |
| Control responsiveness during stress | Maximum sampled local control round trip 19.05 ms |
| Fresh snapshot recovery | 24.82 ms; one recovered point [491], exact p=0.91; renewal added no duplicate |
| Abandon while blocked | Timer, queue, drain listener, and broker session removed; no post-close callback/write |
| Resume actual TCP reading | All 476 points once each; one actual drain; paused-to-latest 363.98 ms; no lost history in this resumed session |
| Drain never arrives | Disconnect observed after 456.94 ms for 400 ms timer; scheduler overshoot disclosed |
| Handover with queued old owner | Two unsent old frames discarded through explicit disconnect; recovery exactly epoch 2 / seq 1 / p=0.2 |
| Writer unit tests | 15/15 |
| Inherited model/transport unit tests | 36/36 and 4/4 |
| Reconnect wire regressions | 20/20, including strengthened unsent-stale-frame expectations |
| Reconnect receipt audit | 1,134 assertions |
| Independent review | 21/21 pure tests, six pressure cases audited, source hashes matched |

The first candidate review exposed reentrant-close timer and reentrant-enqueue/configuration cleanup defects. They were fixed and the final independent suite passed. Baseline and first-review failure receipts remain available rather than being overwritten by a success claim.

This does not establish a finite worst-case user delay. Healthy clients receive no new deliberate wait; a slow client is cut off and must explicitly reconnect/resnapshot. Recovery is latest-only when bytes were abandoned, not an assertion of complete historical observations. The normal default stall timer is 250 ms; stress used 400 ms. Event-loop scheduling can exceed either duration.

## Packaged rerun

The numbers above describe the original 14:41 UTC run, not universal bounds.
The PR rerun is recorded separately in results/verification.json. The original
summary files in evidence/ are preserved; full generated traces remain local and
gitignored. Baseline and candidate padding differ, so compare safety invariants,
not their raw queue/time figures as a performance ranking.
