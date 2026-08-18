# LAT-P070 — the instrument is live; the sample is not

Cycle 42. Fable's LAT-P069 directive ratified rulings (a)–(d) and left three executable items:
**(1)** the T5 read, tomorrow, read-only; **(2)** build the golf timing split as `latency-63`;
**(3)** take `turbo_collapse`'s p95 at real *n* and resolve P3. Item 4 is integrator-side.

Item 1's artifact is `lat-p070-t5-grading-protocol.md`. This document holds items 2 and 3, and the
finding that item 1 could not have been graded honestly without.

---

## §1 — Item 3: the first real read, and why it is not available in this window

**The instrument IS live.** `program/latency-61` merged as `3383dae2` and reached production in
**v3848 at 2026-08-18T21:59Z**. Verified at the tree, not inferred from the merge:

```
git merge-base --is-ancestor de4bd1d4 origin/master        -> ancestor
git show origin/master:backend/app/tasks/__init__.py       -> _tracked_run("turbo_collapse_futures", ...)
curl $BAINLUCK_API/api/health                              -> {"commit": "43f33396"}   # contains it
```

**And `task-metrics` still says `no_data` — correctly.** Both beats are
`crontab(minute=30|45, hour="*/6")`, so they fire at 00:30/00:45, 06:30/06:45, 12:30/12:45 and
18:30/18:45 UTC. The last fire before the instrument deployed was **18:30/18:45Z — three and a half
hours BEFORE v3848**. Nothing instrumented has run yet. The reading is a correct instrument
reporting an empty window, not a broken one; the distinction is doctrine clause 1 and it is the
difference between "wait" and "debug".

First instrumented fire: **2026-08-19T00:30Z** (futures) / **00:45Z** (odds).

### 🔴 n=1 is not "real n", and the gap is arithmetic

`app/utils/turbo_collapse_budget.py` sets `MIN_SAMPLES = 5`, for the reason its own docstring
gives: at n=1 a nearest-rank p95 *is* `max()`, and "the p95 is 853.8 s" would be a sentence with a
distribution's authority and one observation behind it.

At a 6-hourly cadence, five completions take **24 hours after the first**:

| # | futures fire | odds fire |
|---|---|---|
| 1 | 2026-08-19 00:30Z | 00:45Z |
| 2 | 06:30Z | 06:45Z |
| 3 | 12:30Z | 12:45Z |
| 4 | 18:30Z | 18:45Z |
| 5 | **2026-08-20 00:30Z** | **00:45Z** |

**So P3 cannot resolve to a derived number before 2026-08-20 ~00:45Z**, and only then if all five
runs reach a terminal. Tonight's read moves P3 from `could_not_measure at n=0` to
`could_not_measure at n=1`. That is a real change of state — the gauge exists and is filling — but
it is **not** the headline the directive anticipated, and reporting it as one would be the
"guessed ceiling wearing a derivation" ruling (a) refuses.

**The budget therefore stays at 3600 on both tasks, for the second consecutive window, by design.**

### What was deliberately NOT done to close the gap faster

`turbo_collapse_*` could be triggered by hand to manufacture samples. Refused, for two reasons:
each run holds one of **two** background slots for ~8–14 minutes against a pool measured at 96.7 %
saturation, and the T5 read is fenced for tomorrow — manufacturing occupancy tonight would
contaminate the baseline of a read that has been waited on for two cycles. **The sample is worth
less than the window it would spend.** Recorded rather than silently skipped.

---

## §2 — Item 2: the golf probe's instrument, built

Approved by Fable as a one-queue build on `latency-63`. **It deploys only after the T5 window
closes at 2026-08-19T17:01Z.** The registered prediction and halt (LAT-P069 §4) are unchanged and
were registered *before* this build: DB > 70 %, app 10–25 %, router < 10 %, **HALT at router > 30 %**.

| file | what it adds |
|---|---|
| `app/utils/request_timing.py` | the split as plain data — parse, clamp, reconcile, format |
| `app/middleware/latency.py` | reads `X-Request-Start` **before** `call_next`; emits `X-Timing-Split` |
| `app/main.py` | attaches the per-statement DB timer to the request path's engine |
| `app/utils/latency_stats.py` | the split rides the existing slow-event ring |

### The arithmetic, stated because getting it wrong is how a false attribution is minted

`wall = app + db`. **`router_queue` is outside `wall`** — the app cannot observe time it did not
yet have the request for. End-to-end is `edge = router_queue + wall`, computed in one place. A
reader who adds all four double-counts, and that is exactly how a "the router is 40 % of this
request" claim gets made out of arithmetic rather than measurement.

Unusable renders `na`, never `0` (gotcha #53). An absent, forged, stale or skewed `X-Request-Start`
is refused rather than scaled. The parser handles seconds / milliseconds / microseconds and the
`t=` and chained-proxy forms, because a unit misread is a 1000× error in the one number the probe
publishes. Small negative deltas clamp to `0.0` (LAT-P068 measured ~5.2 s of clock skew in this
system); large ones are refused.

Two limits recorded rather than papered over: `X-Request-Start` is **client-settable** and this
lane did **not** verify that Heroku's router overwrites a caller-supplied value, so the defence is
the plausibility window rather than trust; and router and dyno clocks are not the same clock.

### Three defects the guards found, none by review

1. `end_db_timing` caught only `ValueError`. CPython raises **`RuntimeError`** on a reused token, so
   a double teardown escaped as a 500 **from inside an observability rail**.
2. The startup-wiring guard was satisfied by the `from … import install_request_db_timer` line
   alone: a mutation replacing the call with `pass` stayed **green**. A guard that agrees with the
   defect (ruling 072). Tightened to the call site and re-mutated red.
3. `record_query` and the engine listener were **two write paths for one write**. The mutation broke
   the helper and left the path production actually uses working — so the instrument reported
   healthy while its real path was untested. Collapsed to one.

### And the module's own explanation was refuted by its own guard

The first draft blamed SQLAlchemy's greenlet: "a `ContextVar.set()` inside `greenlet_spawn` does not
propagate back out". The negative-control test written to prove that **failed** — on the pinned
versions (SQLAlchemy 2.0.50 / greenlet 3.5.1) the greenlet shares the Context outright and a rebind
*does* propagate.

The boundary that actually forces a mutable accumulator is the **asyncio task** inside
`BaseHTTPMiddleware`. Measured directly on starlette 1.1.0: a rebind in the downstream handler is
invisible to the middleware; a mutation of the object the ContextVar already points at is visible.
Both boundaries are now pinned by tests, and the wrong reason is out of the code.

**This is the second time this cycle a registered explanation was replaced by its own
measurement** — the first being LAT-P069's hour-premise correction, which Fable ratified as (c).
The pattern is worth naming: *the guard written to prove a claim is the cheapest place to discover
the claim is false.*

### Adjacent, and honestly bounded: #1606

#1606 says the slow-event ring is structurally unattributable outside `/api/feed` — its first
production read was **100 % `unattributed`**, on `/api/event/{key}` and `/api/playoffs/{league_slug}`.

This build gives every `/api` tail event a **coarse** attribution (`db_ms` / `app_ms` /
`router_queue_ms` / `queries` / `max_query_ms`), which is a different axis from #1606's ask — that
issue wants a per-route *stage* breakdown, and its acceptance criterion 1 names a real `top_stage`.
**#1606 is therefore NOT closed by this work and is not claimed.** What is now true is that the
ring's records carry a why along the axis the golf probe is graded on. Commented on the issue;
the remaining half is per-route stage headers.

---

## §3 — The phantom hard kill, and why item 1 needed it

`mlb_schedule_coverage` has been reported for two windows as "1 attempt / 0 terminals", and it is
one of the seven tasks T5 grades. **It is not stalled. It is a counter artifact, and the surface
was asserting a mechanism its own payload refutes.**

`hard_kills_24h` is derived as `starts − (successes + failures + incompletes)`, and those four
counters **do not share a window** — each is stamped `SET NX EX 86400` at its own first increment.
A comment forty lines below the subtraction already says so. `WINDOW_COUNTER_TTL` is **86400 s**,
which for a *daily* beat is exactly its cadence, so every daily task races its own key expiry once
a day — and the race can resolve differently for `starts` and `successes`, which are written a
fraction of a second apart.

**Measured 2026-08-18T22:45Z. One morning, two of the seven T5 tasks, the same race resolving in
opposite directions:**

| task | `starts_24h` | `successes_24h` | published | what actually happened |
|---|---|---|---|---|
| `mlb_schedule_coverage` | 1 | **0** (`successes_window_s: null`) | `hard_kills_24h: 1`, `health: critical`, *"none reached an end handler — hard-killed"* | started 07:05:00.095Z, **succeeded 07:05:00.851Z**, 734 ms, full result summary |
| `grid_sentinel` | **0** | 1 | clamped to 0 by `max(0, …)` | ran 07:25:06Z, 6.7 s, 0 errors |

The mlb payload carried that run's `last_success_at`, `last_duration_ms` **and**
`last_result_summary` — the end handler's own writes — while declaring the run never reached an end
handler.

**Fixed** (`ef782755`): the derived count is reconciled against the payload's own terminal stamps
before publication, refuting **exactly one** kill — the last run, the only one those stamps speak
for. Earlier kills survive. Both directions are guarded, because the dangerous failure is the
opposite one: a terminal from *before* the start must not refute, or a stale stamp would silence a
genuinely killed task, and turning a real alarm off is far worse than a phantom.

### 🔴 The sibling census has the same defect and is NOT fixed here

`get_hard_kill_census()` — the `ops-snapshot` block, a different code path — computes
`max(0, attempts − terminals)` from a second pair of independently-expiring counters. **A run in
flight at read time is an attempt with no terminal**, indistinguishable from a kill.

Today's census, 13 kills across 121 tasks, five of them this exact shape:

| task | attempts | terminals | cadence |
|---|---|---|---|
| `warm_typeahead` | 5354 | 5353 | every ~10 s |
| `poll_all_odds` | 2631 | 2630 | continuous |
| `heartbeat` | 1311 | 1310 | every minute |
| `sync_statpal_live_plays` | 1311 | 1310 | every minute |
| `sync_espn_live_events` | 1310 | 1309 | every minute |

Five high-frequency tasks, every one **exactly** one short. That is not five coincidental deaths;
that is the read catching one run mid-flight in each.

**Deliberately not fixed in this window.** `hard_kills` was discharged only last cycle after eight
of them, and re-cutting a just-discharged alarm's semantics without a design is how it earns a
ninth. But the finding **supports** the standing recommendation to close it as
*unmeasurable-by-construction*, and now supplies the mechanism: a derived difference between two
independently-windowed counters cannot separate *in flight* from *killed*, and on any task that
runs more often than the census is read it will report a permanent phantom. Commented on #1501.

---

### ⚠️ Two issue references this lane has been carrying are mis-targeted

Checked against the tracker this window, per ruling 077's Phase-0 obligation to read the mechanism
of what you are about to work:

* **#1501 is not the hard-kill census.** It is *"Sentry error quota exhausted — backend errors
  dropped since 07-28"* (`program:plumbing`, `needs-user`). LAT-P069's `da76ded2` and this window's
  `ef782755` both cite it for census work. There is **no** dedicated census issue; the correct home
  is **#1609**, which is where the work has actually been tracked. The commit messages are left as
  written rather than rewritten — the branch history is what the Integrator reads — but the
  reference is wrong and is flagged here so it stops propagating.
* **#1917 is not the golf latency issue.** It is *"Delete `GOLF_IDENTITY_SPLIT_SCAN` and the UNION
  branch — a rewrite measured 4.8x worse must not be left behind an off flag"*. It is *adjacent* to
  `/api/golf/tournaments/{slug}` and is the reference LAT-P069 used for the probe, so this window
  followed the precedent for continuity — but the probe is not that refactor, and the instrument
  built here serves the **#1609/#1606** axis.

Neither is load-bearing for any claim above. Both are the kind of drift that becomes folklore if
nobody writes it down.

---

## §4 — What this window did not touch

* **No occupancy change**, again and deliberately. The 3600 s budgets stand.
* **No `warm_typeahead` W intervention.** Ruling (d) requires any W intervention to predict its
  effect on the **42.2 s mode specifically**, with a halt watching that mode's rate and DB hold %.
  Not started; the prediction has to be built before the change is.
* **Nothing deployed.** `-63` is committed and unpushed; it lands after 17:01Z tomorrow.
* **No `-61`/`-62` rebase.** Integrator-side by rule (ruling 088 / directive item 4); merged floor
  **85** for the stack, resolved by counting files in the merged tree.
