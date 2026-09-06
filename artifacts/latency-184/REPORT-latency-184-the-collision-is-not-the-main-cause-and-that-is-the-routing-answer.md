# latency/184 — the collision is not the main cause of the cold search box, and that is the routing answer

**PILLAR: DISCOVER. SHIP: the search box stops going cold every morning.** Same ship as 178–183.

Written 2026-09-06, session from 11:26Z. Branch
`program/latency-247-the-search-box-stops-going-cold-at-dawn`.

---

## The one-paragraph version

184 was handed a routing task, not a build task: CERT-2061 was the fourth merits BLOCK on `#3480`,
183 had closed every lever for meeting the bus's invariant with a measurement, and the instruction
was *route it, do not repair it*. Routing to Alex was already half-done — 183 put option **D**
("land the collision fix on the narrower promise it actually keeps") in front of him. Before
relaying anything further I checked the premise every queue in this chain has been carrying: **that
the morning compaction collision is what makes the search box cold.** It is not. Over 208.8 minutes
in which **no compaction grinder ran at all**, the head was dead **34.9% of the wall clock**. The
dominant cause is already filed as **#3398** (p1, "entirely cold 43% of the time"), it is a
different defect from #3480, and #3480 is being held behind an invariant only #3398's fix or a dyno
could satisfy. That is the routing answer.

---

## 1. Correcting my own framing before anyone builds on it

My first pass at this wrote the cold-head rate up as a finding. **It is not a discovery — it is a
re-measurement.** `#3398` was filed at 03:54Z *this morning* by latency/179 with the same
phenomenon, the same method (`max(0, period − TTL)` summed over the ring) and a larger number:
**43.2%**. I am recording that plainly because the chain's own failure mode has been carrying
assumptions forward unchecked, and "184 discovered" would have been one more.

What is genuinely new here is narrower, and it is the part that does the routing work:

> **#3398's coldness occurs with no compaction resident.** #3398 does not mention compaction; #3480
> assumes compaction is the cause. Establishing that the two are independent is what separates the
> claims.

## 2. What I did not do, and why

I did not present a fourth repair. CERT-2061's BLOCK requires "real isolation/capacity or another
concrete topology/schedule change that guarantees an eligible warmer starts inside 120s throughout
every compaction window", and 183 closed every non-purchase lever with a measurement.

I also did not build the grader's named regression (the 02:08 compaction plus the 02:10 five-job
arrival set on actual slots, **including lock/min-period self-gating**). One reason, offered as an
argument rather than a refusal:

> **Modelling self-gating cannot rescue the invariant.** `lock` and `min_period` skips reduce how
> many fires are *eligible*; they do not create slots. During a genuinely both-slots-held window
> the eligible-fire count is irrelevant — zero free slots means zero starts, whatever fraction of
> fires was eligible. Self-gating changes the denominator in quiet periods only. Built correctly,
> the named regression produces a fifth BLOCK, not a pass.

The counters are real and I read them: `skips.by_reason` moved `lock` +265 / `min_period` +75 over
the sampled window. They are the right counters for the grader's test. They are not load-bearing on
the question it is meant to settle.

## 3. The measurement

`artifacts/latency-184/cold-head-census.py` over `.lat182-warmer-samples.jsonl` (48 samples,
08:04:47Z → 11:33:32Z — the sampler 183 left running):

```
sampled window   : 08:04:47Z -> 11:33:32Z  (208.8 min)
distinct passes  : 178 in window

inter-pass gap   : p50=41s p95=184s max=750s
  gaps > 65s  (response TTL lapses) : 46 of 177
  gaps > 120s (expiry budget blown) : 26 of 177

Q1 whole-head-cold : expired == head_n on 34 of 178 passes (19.1%)
     COLD WALL TIME : 71.0 min of 203.1 min = 34.9% of the window

Q2 compaction resident?
  turbo_collapse_futures: NO new start — last_started_at 06:32:20Z (unchanged, 48/48 samples)
  turbo_collapse_odds   : NO new start — last_started_at 06:46:42Z (unchanged, 48/48 samples)

Q3 across the #3399 deploy
  pre-#3399  : passes=133 whole-head-cold=24 (18.0%)  gap p50=42s p95=170s
  post-#3399 : passes=77  whole-head-cold=14 (18.2%)  gap p50=40s p95=196s
```

**Q2 is the load-bearing line.** `last_started_at` is a last-write-wins stamp and cannot be
differenced — but it can be compared for *change*, and it did not change across any of the 48
samples. Neither grinder started during the window; today's compaction ran 06:32–07:11Z, entirely
before it. So the whole 34.9% accrued with **no compaction resident**.

**Q3 is a stability check**, not a result: the rate is flat across #3399's shed deploy at 10:05:31Z
(18.0% → 18.2%), which is what it should be, since #3399 fixed the `sta`/`red` *write* path and not
the pass cadence. A rate that ignores an unrelated deploy is a property of the system rather than an
artifact of one release.

**A metric note that matters.** "19.1% of passes" and "34.9% of wall time" measure the same ring and
differ by a factor of nearly two. The pass count is the wrong one to quote: one 750s gap hurts users
far more than four 70s gaps, and the pass-based figure scores them the other way round. The census
script prints both and says which is user-facing; my own first cut quoted only the pass figure and
understated the problem.

## 4. Why this is the routing answer

The two claims tangled together in `85d052bc` were always separable:

| | claim | status |
|---|---|---|
| **A** | the five/six-beat pile-up on two background slots is removed | **true, provable, delivered by the diff** |
| **B** | a `warm-typeahead` fire always starts inside its 120s budget | **arithmetically unreachable on Standard-1X** |

`85d052bc`'s own commit subject is *"the search box stops going cold every morning"* — claim B's
promise. The bus grades the subject line, so it grades B, and correctly finds it false. **The fix is
held behind a promise it never needed to make.** That was 183's diagnosis; I confirm it from the
diff, and Q2 supplies the missing evidence for it:

> #3480 (compaction collision) and #3398 (warmer starvation, 43.2% cold) are **independent
> defects**. The invariant CERT-2038→2061 keeps demanding is #3398's to satisfy, or the dyno's. It
> was never #3480's to satisfy, and no repair to #3480 can satisfy it.

### Consequences

1. **The bus is right to BLOCK the broad ship**, and there is now a direct production measurement of
   why rather than a simulator: the head is going cold when the compaction beats are not running.
2. **D is more right, not less.** Renaming the ship to what the diff delivers — *"the morning
   cleanup stops taking the search box down for an hour"* — is now the only honest description of it.
3. **The case for the dedicated worker is strengthened, and its justification changes.** A dyno that
   isolates the warmer isolates it from *all* background contention, which is where the loss turns
   out to be. But it is justified by #3398's all-day tail, not by #3480's one morning window — and
   the note to Alex currently says the opposite. He should have that before he answers.

> ⚠️ **What this does NOT license.** My window is 08:04–11:33Z = **1:04–4:33am Pacific**, the
> lowest-traffic hours, and contention is traffic-dependent. Do not extrapolate 34.9% to a day-wide
> cold-minutes figure. What is established is narrower and sufficient for the routing call: *in a
> no-compaction window the head is dead about a third of the time.* Sizing it across a full day is a
> separate measurement, parked.

## 5. Second method, and its limit (notice 26 discipline)

`expired` proves the cache entry was gone, not that a user queried during the gap — a strong proxy,
since the head is by definition the most-queried terms, but a proxy. So rather than relay a
one-counter finding I ran an independent user-shaped check: `.lat247-headprobe.sh` issues real
`GET /api/events/typeahead?q=…` requests against production, cycling 24 head terms (excluding
`sta`/`red`, which #3399's shed makes unrepresentative) at ~23s, so each term is revisited every
~9 min — far rarer than the warmer's ~40s pass, so the probe does not warm what it measures.

Output: `artifacts/latency-184/headprobe-output.txt`.

**Its limit, stated because it bounds what the probe can be used for.** A multi-second head response
has *two* filed causes and the probe cannot tell them apart:

- **#3398** — the head is wholly expired, so the term pays a full cold build; and
- **#2304** — the warmer DELETEs each entry before rebuilding it, so a request landing inside that
  window pays its own independent build (measured there at 2,000–3,689 ms, 8.6% of requests).

My probe's p50 sits squarely in #2304's 2–3.7s band. So it corroborates *the user-visible symptom* —
head terms cost seconds, often — and must not be quoted as attribution to either issue. The
attributing instrument is the ring census in §3.

## 6. State at end of session

- Branch pushed; PR #3483 OPEN/MERGEABLE. Nothing staged on the bus — CERT-2061 is banked BLOCK, so
  the next presentation takes a new id. **No fourth repair was presented.**
- Samplers still running: `.lat182-sampler.sh` chained to `.lat247-sampler-continuation.sh` (to
  19:10Z), both appending to `.lat182-warmer-samples.jsonl`. The 18:30Z + 18:45Z production
  compaction window falls inside that. **It will be more BEFORE, not an AFTER** — an AFTER needs
  #3480 merged and deployed, which needs the routing answer first.
- `#3398` commented with today's re-measurement and the no-compaction finding.
- `alex-inbox` updated with Update 3 carrying §4's correction, in plain English.

— latency/184
