# RULING 127 — The latency program reports two user-facing numbers, and instrument work must name the decision it unblocks

date: 2026-08-23
author: Fable (PROGRAM CHARTER AMENDMENT, Alex ruled; pasted and reviewed by Alex)
issue: 1545

**Issued:** Fable, 2026-08-23, PROGRAM CHARTER AMENDMENT (Alex ruled; pasted and reviewed by Alex).
**Binds:** the `latency` program lane, every cycle, starting LAT-P083.
**Named failure this fixes:** *"dozens of cycles, `MEASURED_WALL_MAX_S` never lowered, and three
cycles spent proving another program's 7.74× step wasn't ours."*

---

## The clause

**A performance program is graded on what users feel, not on what its instruments can prove.**
Instruments are how a claim survives contact with an adversary; they are not the deliverable. A
lane that can only report on the health of its own measuring equipment has stopped being a
performance program and become an instrumentation program — and the transition is invisible from
inside, because instrument work is always *correct*, always *necessary-looking*, and always
produces a green result to report.

`NOT_REFUTED` is not a win. Only the deltas are.

---

## 1. HEADLINE METRIC — every report opens with two numbers and their deltas

Every latency report from LAT-P083 onward **opens** with `feed p50` and `typeahead p50`,
user-facing, with the delta against the previous cycle. **A cycle that does not move them says why
in ONE line.**

### The measurement, defined once, here

Both numbers are pinned to a named instrument and a named input. Changing either resets the series
and must be declared in the headline line, with both old-instrument and new-instrument numbers
published for one overlapping cycle. A delta between two different measurements is a delta of
instruments.

**`feed p50` — ORGANIC, a census, not a probe.**
`GET /api/admin/latency-stats` → the `/api/feed` row → `p50_ms`, over its 1-hour window.
`/api/feed` is in `always_sampled_endpoints`, so this is a census of real user requests rather than
a 1/10 sample. Reported **always** with three companions, none of them optional:

* `n` — the window's sample count. `latency-stats` returns `null` for a percentile it lacks
  samples for, and its own `note` warns that a null is not a fast endpoint. A p50 with no `n`
  beside it is unreadable.
* the **`by_cache_status` split**. `/api/feed` is bimodal with nothing in between — measured this
  cycle at `hit` 12.8 ms / `stale_hit` 15.3 ms / `miss` 5,497.6 ms. **A p50 over mixed cache states
  is a statement about the HIT RATE, not about latency**, and it will move by three orders of
  magnitude on a change that touched no code path a user waits on.
* `newest_sample_age_s`, because a warm number from an hour ago is a claim about an hour ago.

🔴 **TAKE THE FEED READ FIRST, BEFORE ANY PROBING — the lane's own traffic enters the census.**
`/api/feed` is `always_sampled`, so **every** request this lane makes to it lands in the window it
then reports as organic. Measured this cycle: a read at 15:09 PDT returned `n=13`; a read at
15:34 PDT, after a 4½-minute `#2107` watch run, returned `n=24` — **7 of the 24 were mine**, and
they were disproportionately cache hits, which moves the very `by_cache_status` split the headline
is reported on.

This is the *third* instance of one shape in one cycle: probe terms voting in the trending counter
they measure; probe traffic populating the typeahead latency row; watch probes populating the feed
latency row. The general form is already banked below for writes; the reads need it too —
**a census that samples every request counts the observer.**

**Protocol, therefore:** take the `feed p50` reading as the **first** production read of the cycle,
before any probe, watch or smoke run touches `/api/feed`; and if that is impossible, subtract the
lane's own request count and say so. Never report a contaminated `n` as organic.

**`typeahead p50` — PROBE, because organic volume cannot carry it.**
`backend/scripts/probe_typeahead_userfelt.py --terms-from file --terms-file
docs/audits/latency/headline-probe-terms.txt`, reported as **p50 AND cold-share together**.

Why a probe and not the organic rail: measured this cycle, `latency-stats` tracked two endpoints
and `/typeahead` had **no samples in the window at all** (`no_samples_in_window: 1`). At a 1/10
sample rate on organic traffic this thin, the organic typeahead p50 is not a number that exists
most hours. A headline that is `null` half the time is not a headline.

Why *this* probe: it already refuses the two defects that cost LAT-P076 its headline — it records
`http_code` and `bytes` alongside the time, so an HTTP 500 in 4 ms can never be classified as
*warm*; and it takes the term set as an argument, so the set travels with the measurement.

**Cold-share is not optional.** A warm p50 on this endpoint is ~13 ms and will not move whatever
happens; the user-felt quantity is *how often a real query is cold*, and the pair is the metric.

### 🔴 The warm/cold threshold is CALIBRATED per run, never a constant — measured the hard way

The probe's `DEFAULT_WARM_THRESHOLD_S` was **0.150 s**, an absolute wall time, and an absolute wall
silently encodes *where the prober stands*. Measured 2026-08-23 from the agent sandbox — ten
requests to `/api/events/search/trending`, one Redis read behind a public GET — the transport floor
is **p50 0.226 s (min 0.216, max 0.235)**, with `time_connect` ≈ 0.0002 s, so all of it is
time-to-first-byte through the egress proxy and none of it is the server.

**0.150 s is below that floor. From this vantage point the probe could never return `warm`, and
cold-share was pinned at 100 % by construction** — a gate that cannot go green, the same defect
class as LAT-P079's staged `samples == 0 ⇒ INCONCLUSIVE` with the sign flipped. This cycle's first
pass reported **100 % cold, p50 1.537 s**; the same instrument at a floor-derived threshold reports
**6 % cold, p50 0.224 s**. The headline inverted, and nothing on the server changed.

So the threshold is **derived per run**: `measure_transport_floor()` times the calibration endpoint,
and `warm_threshold = floor_p50 + 0.100 s`. If the floor cannot be measured the probe **exits 3 and
refuses to classify** rather than falling back to the constant — an unknown floor is an unknown
threshold, and quietly substituting a constant is exactly how a 0.150 s wall came to be applied
from a 0.226 s vantage point. Every record carries `warm_threshold_s`, `threshold_source` and
`transport_floor_p50_s`, so no reading can be compared against another without its threshold.

This is what *"measured the same way each time"* actually requires here. A **fixed** threshold
would report different cold-shares from CI, a laptop and this sandbox for identical server
behaviour; a **derived** one reports the same. The constant is what varies.

### And the resolution limit, stated so nobody over-reads the number

At a 0.226 s transport floor, a warm read costs ~13 ms of server time — **below this instrument's
resolution**. From this vantage point the probe measures **cold-share reliably and warm p50 not at
all**; the warm wall-clock number is a measurement of the proxy. Cold reads (1.0–1.8 s) sit four to
eight times above the floor and are real.

**So the typeahead headline is led by cold-share, with the warm wall reported beside it and
explicitly labelled floor-bound.** A future cycle that needs a true server-side warm p50 must get
it from `latency-stats` (server-timed) once organic volume supports it, or from a prober inside the
same network — not by tightening this threshold.

### 🔴 The probe set is FROZEN, and every term must already be in the real search head

`docs/audits/latency/headline-probe-terms.txt`, eight terms, committed, with its provenance and its
change protocol inside the file.

The frozen-ness answers *"measured the same way each time"*. The composition answers something
sharper: **`/typeahead` writes to the trending counter the warmer heads from, so probing a term is
a vote for it.** LAT-P082 measured the head with two synthetic strings and thereby put them into an
otherwise-empty zset, where they became 2 of the warmer's 40 slots until their bucket expires — a
measurement that changed the thing it measured, confessed in its own report. A probe set drawn from
terms users already search is a rounding error on that distribution. A probe set of invented
strings **is** the distribution.

*General form, worth carrying: an instrument that writes to the system it reads must be composed of
inputs the system already contains.*

---

## 2. INSTRUMENT TEST — name the decision, or defer the work

**Instrument work is permitted only when it unblocks a NAMED decision, and the report names it.**
An instrument fix that unblocks nothing is deferred, however correct it is.

The test is a sentence of the form *"without this, X cannot be decided"*, where X is a decision
someone is actually waiting on. It is not satisfied by *"the number would be wrong"* — a number
nobody is about to act on can be wrong indefinitely at no cost, and the whole failure mode this
clause names is a lane fixing true things in an order that never reaches a user.

The clause bites hardest where instrument work feels most justified: a defect the lane *found
itself*, in its own instrument, in the middle of a cycle. That is precisely the shape of the three
cycles spent proving another program's 7.74× step was not ours.

---

## 3. LATENCY BUDGET FLAG — `beat_cost`, on the `migration_slot` pattern

Any change, **from any program**, that raises a measured beat cost past the declared threshold must
declare `beat_cost` in its PR and READY token, and **the Integrator refuses the merge without it**
— the same mechanical shape as `migration_slot` and `beat_schedule_change`.

The threshold, the measurement, and the enforceable spec are owned by this lane and specified in
`docs/doctrine.md`, so the Integrator can enforce them without judgement. Calibration's re-stage
class is the first client: CAL-P078's rolling re-stage moved `precompute_calibration_main` from a
p50 of 163 s to 1,263 s — **7.74×** — with no declaration anywhere, and the cost of that silence
was three latency cycles spent establishing that the step was not caused by ruling 110's routing
change, plus one falsifier baseline that read ~6× against a healthy beat until ruling 123 re-pinned
it.

**The point of the flag is not to forbid the change.** CAL-P078's re-stage was correct and would
have been approved. The point is that a 7.74× step on a beat a user-facing page waits on should
arrive **announced**, so that the next reader of that beat's latency knows they are looking at a
regime change rather than a regression.

**Schedule, as ruled:** the spec and its measurement ship this cycle or next; **enforcement begins
the cycle after the spec is in doctrine.** A gate that starts refusing merges before its threshold
is published refuses them for a reason nobody can read.

---

## What this amendment does NOT retire

The falsifier panel, the #2107 watch, and the materiality floors stay — Fable's words: *"they're
what makes item 1 honest."* Two headline numbers with no adversarial machinery behind them are a
dashboard. The amendment does not point the lane away from instruments; it points the instruments
at offence.
