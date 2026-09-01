# The two unit-cost gauges measure different populations — and the one that reconciles them is never sampled

**CAL-P182, 2026-09-01 ~09:20Z / 02:20 am PT.** Method: the same 168-beat
`/api/admin/calibration-beat-gauges?full=true` history P178–P181 already had, plus the source that
writes it. No new query, no new instrument. Directive `947` ITEM 5 asked *"is this gauge actually
measuring what its name says?"* of every remaining gauge. Asked of the unit-cost pair, the answer
is **no**, and the artifact proves it against itself.

---

## 0. The one-line version

`staged:unit_ms_worst` is **smaller than** `staged:unit_ms_mean` on **25 of 148** beats — which is
arithmetically impossible for a real (mean, max) pair over one population. They are two
populations: **the mean includes cancelled units, the worst does not.** The gauge that would
reconcile them, `staged:unit_ms_mean_completed`, **is computed and then dropped on the floor by the
sampler's allowlist** — 0 appearances in 168 beats.

**Nothing that decides is corrupted** (§4). The damage is confined to the operator-facing artifact,
which happens to be the only instrument this lane is entitled to read.

---

## 1. The observation

Live beat `2026-09-01T08:31:38Z`:

```
"staged:unit_ms_mean":  137476     ← 137.5 s
"staged:unit_ms_worst":  53126     ←  53.1 s     worst < mean
"staged:units_this_beat":     7
"staged:units_completed_this_beat": 5
```

Across the history:

| | beats | `worst >= mean` | `worst < mean` |
|---|--:|--:|--:|
| `units_this_beat == units_completed_this_beat` (no cancellations) | **111** | **111** | **0** |
| `units_this_beat > units_completed_this_beat` (cancellations) | 37 | 14 | **25** |

**A perfect separation.** Not one zero-cancellation beat violates the invariant; every violation has
at least one cancelled unit, and 23 of the 25 are the same `7 timed → 5 completed` shape.

## 2. Why — the two writers, in the source

**`staged:unit_ms_worst`** — `backend/app/tasks/precompute_calibration.py:4741`, folded to the gauge
at `:4457`. The unit loop's cancellation path `continue`s at **`:4719`**, twenty-two lines *before*
`worst_unit_ms = max(worst_unit_ms, unit_ms)` at `:4741`. A cancelled unit therefore never reaches
the max. **Population: completed units only.**

**`staged:unit_ms_mean`** — `backend/app/tasks/calibration_main_build.py:1584`, from
`runner.ledger.stage_mean_ms(...)` at `:1559`. This is the writer that actually runs on a
non-publishing beat (`:1534-1541` explains why the frozen module's projection is skipped). Its own
comment at **`:1564-1566`** states the population outright:

> *"``unit_ms_mean`` above averages over every unit the beat **TIMED**, including the one cancelled
> at the deadline, so it is the right number for attributing elapsed time and the **wrong one for
> costing a unit**."*

**Population: timed units, cancelled included.**

So the pair is `max(completed)` against `mean(completed ∪ cancelled)`. Cancelled units are slow *by
definition* — they are cancelled at a time bound — so whenever a beat cancels enough of them, the
mean climbs past the completed-only max. That is the whole mechanism.

### 2b. This defeats the pair's stated purpose

`precompute_calibration.py:4451-4455` says the two are recorded together precisely so the **gap**
can be read as a diagnosis:

> *"a large gap between them is itself the diagnosis — it says the units are unevenly sized, which
> is a plan/partition problem, not a budget one, and no timeout change can fix it."*

That reading requires one population. With two, the gap is contaminated by the cancellation rate and
**cannot be used for what it was built for**. On 25 beats it is not merely contaminated but
inverted.

## 3. The reconciling gauge exists — and is filtered out

`calibration_main_build.py:1577` computes and records the honest number:

```python
runner.ledger.record_gauge("staged:unit_ms_mean_completed", int(completed_mean))
```

`calibration_beat_gauge_sampler.py:167-177` defines `OPERATIONAL_GAUGES`, a **hand-maintained**
allowlist (`:164-166` — *"allowed to be hand-maintained — forgetting one costs a column in a report"*).
It lists `staged:unit_ms_mean` and `staged:unit_ms_worst`. It does **not** list
`staged:unit_ms_mean_completed`.

Confirmed empirically — every gauge key appearing anywhere in 168 beats:

```
168  served_units · units_banked · units_drifted · served_drifted · units_this_beat
     units_drift_checkable · units_drift_uncheckable · served_drift_uncheckable
     units_completed_this_beat
164  unit_ms_mean · beats_to_publish
153  cursor_resume
148  units_done · unit_ms_worst · units_planned
127  served_at
117  window_left_ms
 38  units_cancelled
```

**`unit_ms_mean_completed`: 0 of 168.** Also absent: `staged:beats_basis:completed` /
`staged:beats_basis:mixed`, the flag written at `:1614-1616` that says *which* mean
`beats_to_publish` was derived from. So the artifact publishes the mean that is wrong for costing a
unit, withholds the one that is right, and withholds the flag that would tell you which was used.

## 4. What is NOT broken — stated explicitly, so nobody re-opens it

- 🟢 **The plan is not corrupted.** `beats_to_publish` uses `projection_mean = completed_mean if
  completed_mean else mean_ms` (`:1613`, CAL-P068) and `_unit_costs_from` uses
  `stage_completed_mean_ms` (`:1638`, CAL-P067). Both decision paths already read the completed-only
  cost. This was fixed twice; only the *published* gauge kept the mixed value, deliberately
  (`:1567-1568` — *"the operator-facing gauges above keep the values CAL-P066 published, so nothing
  that reads them moves"*).
- 🟢 **P181's ~17 h is unaffected.** That figure came from bank progression against wall-clock across
  seven completed cycles, never from `unit_ms_mean`. **The ETA and the D-G ask do not move.**
- 🟢 **This is not the publish-gate cause.** That remains `served_at_absent` / fingerprint reset,
  answered and closed. Do not re-open it.

## 5. The operational payload: cancelled units eat the majority of the rebuild

This is the part that is worth carrying forward. On the 25 beats where the artifact proves the
mismatch, you can bound the cancelled units' cost **from the published numbers alone** — no new
query — because `mean × timed` is total timed cost and `worst × completed` is a hard *upper* bound
on the completed share:

| quantity (all **lower** bounds) | min | median | max |
|---|--:|--:|--:|
| published unit cost overstates true completed cost by | 1.04× | **1.57×** | 2.74× |
| share of the beat's unit-time spent on **cancelled** units | 19.9% | **54.4%** | 87.8% |
| cost of one cancelled unit vs the worst **completed** unit | 1.2× | **3.0×** | 6.6× |

The two most recent beats are the worst of the run:

```
09-01T07:31:29   5/7 done   mean 135.4s  worst  52.7s   infl 2.57x   cancelled >=341.9s ea  (72% of unit-time)
09-01T08:31:38   5/7 done   mean 137.5s  worst  53.1s   infl 2.59x   cancelled >=348.4s ea  (72% of unit-time)
```

**Read that plainly: the live rebuild banks 5 units per beat while paying for roughly 13 units'
worth of unit-time.** ~72% of the compute in each of the last two beats went to two units that were
thrown away, each costing ≥6.6× a unit that actually banked.

⚠️ **Hypothesis, NOT a finding, and NOT to be built here:** if the cancellations were eliminated the
beat's banked throughput could rise substantially, shortening the ~17 h rebuild. That is a
**design** question about unit partitioning against #2052's 22.5-minute statement-timeout wall — it
needs a fold, so under ruling 134 it is the measurement lane's, and it is parked, not dropped.

## 6. A fourth defect, found in passing: `staged:units_cancelled` under-reports

Cross-validating the cancelled count against `units_this_beat − units_completed_this_beat`:

- **37** beats agree.
- **15** beats had a timed-but-not-completed unit while `staged:units_cancelled` was **never
  written at all** (e.g. `08-25T16:28` 7→6, `08-28T01:21` 1→0).
- **1** beat wrote `units_cancelled: 1` when two units failed to complete (`08-25T23:33`, 10→8).

`units_cancelled` is written only on the "cancelled at its own bound" path
(`precompute_calibration.py:4706`); the other non-completing exits — the cursor-write failure
`return None` at `:4732`, and the `break` at `:4713` — leave it unwritten. **Use
`units_this_beat − units_completed_this_beat` as the cancelled count.** Every number in §5 does.

## 7. Carry-forward rules for the next session

1. **Never cost a unit from `staged:unit_ms_mean`.** It is the mixed mean; the source says so at
   `calibration_main_build.py:1564-1566`. Until the sampler ships
   `staged:unit_ms_mean_completed`, the only honest published bound on the true unit cost is
   **`staged:unit_ms_worst`**, which is a completed-only *max* and therefore a ceiling.
2. **`worst < mean` is a cancellation signal, not a bug in the reading.** Its size bounds how much
   of the beat was wasted — the §5 arithmetic needs nothing but the artifact.
3. **Cancelled count = `units_this_beat − units_completed_this_beat`**, never
   `staged:units_cancelled` (§6).
4. **Trap 11 stands and now has a sibling.** `staged:beats_to_publish` is not a countdown (P181);
   `staged:unit_ms_mean` is not a unit cost (P182). **Two of the artifact's most quotable numbers do
   not mean what their names say.** Assume the third does not either until it is tested.
5. Both P180's and P181's yields, and this one, came from re-reading a history that four earlier
   sessions had already downloaded. **Three in a row.** The instrument is still not exhausted.

---

### Provenance

Gauge history: `/api/admin/calibration-beat-gauges?full=true`, `artifact_generated_at
2026-09-01T08:45:21.377128+00:00`, 168 observations, last beat `08:31:38.330866Z`, fingerprint
`e2040f90154fae876f0fb65f5abf74c3` (matches the predictor at branch HEAD `2f28aa30` — clock clean,
no reset baked in). Source read at `2f28aa30`. No code changed; nothing pushed.
