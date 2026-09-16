# native/191 — #2975, and the two holes the battery found in the guard itself

**The ship:** a test that could hang the entire native gate can no longer do it, and if anything
else ever does, the gate says so in five minutes instead of sitting there.

## Why this was picked up

#2975 was filed 2026-09-04 with a correct diagnosis, a correct suggested fix, no assignee, and the
line *"Owner: whoever next touches the native Sports load tests."* It sat twelve days. It fired
again on 2026-09-16 during a routine gate run for #6544: **995 of 2513 tests in, ten minutes of no
progress, no timeout, no failure** — I killed it by hand. That is the second recorded occurrence and
the second lane-hour it has cost. `uptime` on this Mac read **load average 752**.

## The two halves, and why neither is enough alone

**The cause.** `SupersedeClient.fetchSportsFeed()` blocks the first call **to arrive at the client**
(`callCount == 1`), not the load the test means by "A". The test sequenced its two loads with a
single `await Task.yield()`, which does not guarantee the `async let` child ever reached the client.
When it had not, the test's *second* load became call 1, took the gate, and `openGate()` — which runs
only after that load returns — was unreachable. Arrival is now **announced**: `firstCallArrived`
opens the instant a call is numbered 1, and the test awaits that fact.

Both gates are now the `AsyncGate` that was already in this file thirty lines above `SupersedeClient`.
The hand-rolled continuation the class carried was a weaker second copy of it — single-waiter, and
it resumed inside the lock.

**The class.** `native-gates.sh` had **no bound of any kind** on its test phase. #5591 had already
made a killed run unable to print a green pass line; it did not make a hung run *end*. The watchdog
bounds **progress, not wall-clock**: a healthy run here is 35–140 s, but at load 750 a wall-clock cap
generous enough to survive is too generous to catch anything, while a log that stops growing cleanly
separates "slow" from "stuck".

## The mutation battery — and it found more in my own work than in the code

`mutants.sh` → `mutants-out.txt` (run 2, the result) and `mutants-run1-out.txt` (run 1, the run that
found things — kept, because a battery that only ever shows its clean pass is not evidence).

| | run 1 | run 2 |
|---|---|---|
| killed | 3 | **6** |
| survived | 1 (M4) | **0** |
| refused | 2 (M2, M5 — *hung*) | **0** |
| control | SURVIVED | SURVIVED |

Three findings, all of them about the guard I had just written, not about the fix:

* 🔴 **M2 and M5 did not fail — they HUNG, for 420 s, and were only caught by the battery's own
  bound.** The selftest's hang arm read liveness *after* an unconditional `wait`, so a watchdog that
  reported the stall and failed to kill left `wait` blocking for the child's whole `sleep 600`.
  **A guard against hanging that can itself hang is not a guard.** Liveness is now read and the child
  force-killed *before* `wait`; both mutants are clean kills.
* 🔴 **M4 SURVIVED, and it was the dangerous direction.** `elif true` — trip on the first quiet poll,
  ignoring the limit entirely — passed every arm, because the two arms only ever exercised a log that
  grew on *every* poll or on *none*. On a Mac at load 750 a healthy suite goes quiet for seconds
  between classes, so that mutant would have redded every gate on the machine. A third arm now runs a
  child that is quiet for 14 s under a 30 s limit and then resumes; it kills M4.
* ⭐ **M6 killed my own prediction.** I expected reinstating `await Task.yield()` to *survive* — the
  defect had fired twice in twelve days, so the scheduler should almost always win. It failed
  immediately and by assertion, not by hanging: `XCTAssertEqual failed: ("0") is not equal to ("1")`.
  At this load the child does not reach the client **at all**; the race is not rare here, it is nearly
  always lost, and what made it *look* rare is that losing it produced silence instead of a failure.
  The guard runs before the second load is issued, so it converts the deadlock into a red test before
  the deadlock can form. The wrong prediction is left in `mutants.sh` on purpose — the reason it was
  wrong is the ship.

## What is NOT claimed

The watchdog is a bound, not a diagnosis: it reports *which test was last to start*, which is the one
that hung, and says in terms that this is the suite failing to finish and not a verdict on your
change. It cannot tell a deadlocked test from a genuinely enormous one, which is why the limit is an
env var (`NATIVE_GATES_STALL_LIMIT`, default 300 s) and why the negative arms above are the
load-bearing ones.
