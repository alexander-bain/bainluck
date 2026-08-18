# LAT-P067 — grading the #1609 topology fix, post-deploy

**Deploy:** `-59` merged into `origin/master` in the `3ca79ddf` wave (CI 32162869350, green 9/9
including `deploy`). **Production reached `3ca79ddf` at 2026-08-18T17:01:53Z** (`/api/health`
uptime 8 s), after **four** Integrator cycles (INT-082/083/084/085) and three latency windows spent
blocked.
**Graded by:** latency lane cycle 39, `pid:64040`, against
`docs/audits/latency/lat-p065-1609-topology-fix-predictions.md`, with LAT-P066's attribution
correction applied.
**Instrument:** `backend/scripts/lat_p064_s1_observe.py` (the existing one — comparability is the
point) plus `/api/admin/ops-snapshot` and `/api/admin/task-metrics`.

---

## §0 — The attribution correction, applied, and it cuts BOTH ways

LAT-P066 corrected its own registered predictions before the deploy: `warm_typeahead` is **74.2 %**
of background inflow and the four `expires`-bounded beats are **87.0 %** of it. Therefore **T3
("depth < 50") and #1609's own acceptance criterion 1 are HYGIENE metrics** — they can pass with the
starvation completely untouched, so a pass is E1's and not the cure's.

Fable accepted that correction and re-scoped acceptance criterion 1 accordingly. **T1, with E3
holding, is the whole attribution.**

Stated once, because it matters for reading §3 below: the correction protects the cure from a T3
**pass** being miscredited to it, and *equally* protects it from a T3 **failure** being mischarged
to it. T3 is currently not passing. That is a fact about the hygiene commit, and it is reported as
one.

---

## §1 — Item 1: the deploy check, taken FIRST, and its trap explicitly RULED OUT

The queue's warning: **"`heavy` flat at 0 is the silent no-op and it impersonates health."**

**`heavy` was flat at 0 for the entire observation** — 38 samples at 3 s across the :20 beat, plus
30 samples at 30 s from 17:00:20Z. Zero samples above zero.

**That reading is AMBIGUOUS, and resolving it rather than reporting it is the whole of Item 1.**
`ops-snapshot` computes depth as a plain `r.llen(queue)` (`app/routes/admin.py:1862`) — it measures
**BACKLOG**. An empty 2-slot `heavy` lane consumes an arriving message in milliseconds, so depth
stays 0 through an arrival that certainly happened. The two branches render identically:

- **(a)** the routing never took effect — the silent no-op, and
- **(b)** the work arrived and was consumed faster than any feasible sampling interval.

Gotcha #53 requires a second signal before writing either claim. Here it is:

| beat fires at | `prediction_market_match.last_started_at` | latency |
|---|---|---|
| 17:05:00.000Z | 17:05:00.131861Z | **131 ms** |
| 17:20:00.000Z | 17:20:00.099841Z | **99.8 ms** |

**Background depth was 3,092–3,119 across that entire window.** A Redis list is FIFO (`LPUSH` /
`BRPOP`); a message enqueued at the tail of a 3,092-deep `background` queue **cannot be popped and
started in 99.8 ms.** Two consecutive fires, same signature.

**VERDICT: branch (b). The trap is ruled OUT.** The routing took effect; the work arrived; the lane
absorbed it so fast that a backlog gauge could never see it.

The pre-deploy comparator is the starvation itself: `starts_24h` = **32** against **96** expected
fires/day — the task started on roughly one fire in three. Post-deploy it has started on both fires
observed, each within ~100 ms. (Honest bound on this comparator: it contrasts a *start rate* with a
*start latency*, because no pre-deploy latency was captured. n=2 on the latency.)

### The instrument defect this exposes, registered for the next window

**T4's written pass condition is ungradeable as written**, and that is a defect in the prediction,
not in the fix. It says *"heavy observed > 0 at least once (the work arrived)"* — which silently
assumes arrival produces observable backlog. On a 2-slot lane at depth 0 it does not. The
parenthetical names the right fact; the metric cannot see it.

**Recommended replacement for the next registration:** grade arrival by **start latency against
beat time** (`last_started_at` − scheduled fire), not by queue depth. Depth remains the correct
instrument for the *second* half of T4 (draining / not monotonically rising), which passes trivially
here since it never rose at all.

---

## §2 — T1–T5, graded

| # | prediction | verdict | evidence |
|---|---|---|---|
| **T1** | holes → ~0 in a deploy-free hour | 🔴 **REFUTED — 6 clean holes in 62.01 min** | §4 |
| **T2** | mean real-pass period ≤ 45 s | ✅ **PASS — 39.6 s** | §4 |
| **T3** | background depth sustained < 50 | ❌ **FAIL — ~3,100 throughout. E1's row, not the cure's** | §3 |
| **T4** | heavy > 0 and draining | ✅ **arrival CONFIRMED DIRECTLY** / depth instrument ungradeable | §1 |
| **T5** | sentinels LATE, never MISSING | ⏳ owed to the next window (24 h horizon → 2026-08-19T17:01Z) | §5 |
| **E3** | holes UNCHANGED by `expires` alone | ✅ **HOLDS — and now holds for the topology fix too** | §4 |

**THE HEADLINE, stated plainly: the fix is CONFIRMED DEPLOYED and the warmer holes are
UNCHANGED.** Those two facts together are the finding, and they refute the model the fix was
built on — see §4.2.

---

## §3 — T3 / E1: background depth is RISING post-deploy, and the mechanism is worth stating

| time (UTC) | commit | background |
|---|---|---|
| 17:00:20 | `522caea4` (pre) | 3,072 |
| 17:02:34 | `3ca79ddf` | 3,052 |
| 17:06:41 | `3ca79ddf` | 3,052 |
| 17:08:46 | `3ca79ddf` | 3,084 |
| 17:12:50 | `3ca79ddf` | 3,107 |
| 17:14:55 | `3ca79ddf` | 3,119 |

Against the registered baselines of **418** (LAT-P065, 17:40 PDT 08-17) and **1,030** (LAT-P066,
20:43 PDT) — this window's Phase-0 read was **3,014**, and it is still climbing 13 minutes after the
deploy. E1's horizon is 2 h (**19:02Z**); the long watcher covers it.

**A mechanism that must be understood before E1 is graded, because it changes what E1 can possibly
mean.** Celery's `expires` is stamped **by the publisher at enqueue time** and enforced **by the
worker at consumption time** — the worker pops the message, sees it is expired, and discards it
without executing. Redis does not expire individual list elements. Two consequences:

1. **The ~3,050 messages already queued when the deploy landed were published by the OLD beat and
   carry no `expires` at all.** The hygiene commit cannot discard them. They are immortal until
   popped.
2. **`expires` reduces WORK, not DEPTH.** It makes draining cheaper (a discard is far cheaper than a
   run), which shrinks depth only *indirectly*.

So E1 ("depth < 100 within 2 h") is a prediction about **drain rate**, not about discard. Reported
as an early honest read, not a verdict: at +13 min the queue is rising, so inflow still exceeds pop
rate.

**E2 (`starts_24h` falls toward real passes)**: `warm_typeahead` is starting at **1.6/min** against
a 6/min beat (18 starts in 11.5 observed minutes, `starts_24h` 3,137 → 3,155). `hard_kills_24h` = 0.

---

## §4 — T1 and T2: the 62-minute probe-free, deploy-free window

Window **17:04:29Z → 18:06:30Z**, 62.01 min, entirely on `3ca79ddf`, **no release inside it**.
247 samples ok, **1 bad** (one `TimeoutError`), **zero sampling gaps**, and **zero holes tainted by
a sampling gap** — so every hole below is clean by the instrument's own guard. A failed sample was
never allowed to read as a hole (gotcha #53).

### 4.1 The numbers

| | baseline (LAT-P064, pre-fix) | **post-fix (this window)** |
|---|---|---|
| clean holes > 120 s | 5 in 55.8 min | **6 in 62.01 min** |
| rate | one per **11.2** min | one per **10.3** min |
| longest hole | 286.6 s | **284.7 s** |
| distinct passes | — | 94 |
| mean real-pass period | — | **39.6 s** |

The six clean holes: **259.9 s, 195.0 s, 284.7 s, 256.1 s, 153.1 s, 277.8 s.**

- **T1 REFUTED.** The registered refutation bar was **≥ 3 clean holes**; there are **6**. Not a
  PARTIAL (that was reserved for 1–2), not a pass. The hole rate is *marginally worse* than
  baseline, which on these n is best read as **unchanged**.
- **T2 PASSES.** 94 distinct passes over 62.01 min = **39.6 s** mean period, inside the route's
  45 s response TTL.

### 4.2 What this refutes, which is bigger than the row

The registered attribution was explicit: *"T1 passing while E3 holds is the WHOLE attribution."*
T1 did not pass — and the fix is **confirmed deployed**, directly, on the wire (§1). So the
inference runs in the other direction, and it lands on the model rather than on the code:

> **The three multi-minute residents were NOT what was causing the warmer holes.** Moving
> `match_prediction_markets`, `poll_kalshi` and `precompute_admin_link_rate` off `background`
> changed the hole frequency and duration **not at all**.

The mechanism is visible in the hole records themselves. Every large hole carries
`starts_24h_delta: 1, successes_24h_delta: 0` — during a 4–5 minute silence the warmer records
**one** start and **zero** completions — and each is followed by a burst (`+11`, `+12` starts in
15–20 s). That is not a slow warmer. **That is beat messages not being delivered, then delivered
all at once**: the lapping pattern, still present.

And the occupant is identifiable. A direct `/api/admin/celery-debug` read at **17:53:09Z** — inside
the 17:52:34→17:55:07 hole — shows **both** background slots busy:

```
match_prediction_markets       -> heavy        ← the fix, working
sync_espn_live_events          -> realtime
backfill_settled_gap_creation  -> background   ← slot 1
precompute_admin_link_rate     -> background   ← slot 2
```

`backfill_winners` measures **p50 816,527 ms = 13.6 minutes** (n=32). **That class was deliberately
left on `background`** by #1609, on #224's authority, and it is a larger occupancy than all three
moved tasks combined. The fix moved the 337 s / 320 s / 72 s tasks and left the 816 s one.

**Two honest caveats on that conclusion, neither of which rescues T1:**

1. `precompute_admin_link_rate` appearing on `background` is a **pre-deploy artifact**, not a
   routing defect: Celery stamps the routing key at **publish** time, so a message enqueued before
   17:01:53Z carries the old route regardless of today's config. Its beat entry and `HEAVY_TASKS`
   membership are both correct. It also means that message waited ~50 min on `background`.
2. Because of (1), one of the two observed occupants will not recur once the pre-deploy backlog
   drains. **The next window should re-run this exact S1 observation after the backlog clears** —
   the steady state may be better than this window's. T1 is refuted *for this window*; the
   re-measure is owed before anyone concludes the fix is worthless.

### 4.3 Sequencing, recorded so it is not mistaken for an omission

Item 2's `#1815` artifact ran **after** this window closed (18:07:37Z), not during it. That script
executes six full Discover builds, and LAT-P063's entire lesson was a reading confounded by the
observer's own load — *"the observation may have caused the thing it observed."* The directive
names T1 as the verdict-bearing read, so it got the clean window.

---

## §5 — T5: the registered COST

Horizon is 24 h from deploy (to **2026-08-19T17:01Z**), so it is **owed to the next window**, not
gradeable here. LAT-P066 re-checked the arithmetic against `precompute_calibration_main`'s real
numbers (0/21 successful, max 22 min): worst case **7.13 min late**. **LATE, never MISSING** holds
on arithmetic.

Standing remedy if a sentinel is ever observed MISSING: **heavy concurrency 2 → 3** (it is a
Standard-2X with the RAM headroom) — **not** sending the three tasks back to `background`. Sending
them back would restore a starvation that has been measured, to avoid one that has only been feared.

**Note for the next window's T5 read:** Option D adds two tasks to `heavy` (LAT-P067). Their
combined load is ~2.5 % of one of heavy's two slots plus a daily ~5 s detect-only read at 07:50 UTC,
deliberately outside #233's protected 07:10–07:45 window. This is declared here so a future T5
failure is not attributed to the wrong commit.

---

## §6 — #1609's closure, flagged

**#1609 was closed `COMPLETED` at 2026-08-18T16:55:25Z** — the minute the merge landed, **six
minutes before the deploy** and before any post-deploy read existed. Its own last two comments say
so explicitly: *"Unmerged and undeployed — a program lane does not push, so nothing below is a
production claim."*

The standing rule is that closure requires measured production evidence, not shipped code. This
closure was made on the merge. It may well turn out to be **retroactively correct** — that is
exactly what §4 determines — but it was not correct *when it was made*, and the grading that should
have gated it is happening in this document, after the fact.

**Disposition, now settled by §4: T1 is REFUTED, so #1609 is REOPENED.**

This is exactly the case the standing rule exists for. Had the grading gated the closure, #1609
would never have been closed; instead it was closed on a merge, and the measurement that arrived
six minutes later says the cure did not achieve what the issue was about. The closure was not
merely premature in process — it was **wrong on the merits**.

What is NOT being claimed: the topology change is not being reverted, and should not be. It is
confirmed working, it is a defensible allocation on its own terms (a 337 s admin grinder does not
belong on a 2-slot latency queue), and #1609's acceptance criterion 1 is a hygiene metric that the
`expires` commit may still satisfy. What is refuted is the **causal model** — that those three tasks
were what starved `warm_typeahead`.

**#1922** (`warm_typeahead` stalls for minutes at a time) is `blocked` on #1609. That block is now
**invalid**: #1609 shipped, deployed, and #1922's symptom is unchanged at 6 holes in 62 minutes.
#1922 should be unblocked and re-scoped onto the long-backfill occupancy identified in §4.2.
