# CAL-P140 — the re-baseline window is live and, on its own measured miss rate, already lost; and the thing that spends its budget is a diagnostic census that cannot stop the publish it stops

Published number at session start and end: **1.88 pp, FLAT** (`headline_pass: true`,
CI `[0.86, 1.97]`, population `q268`). The payload moved — `04:35:25.200044Z`,
**925,466** outcomes against CAL-P139's 925,446 — and **not one beat in this
window is a datapoint about the calibration.** All six re-serve the census
promoted at `2026-08-29T20:18:32Z`. §2 explains why, and why the discriminator
CAL-P139 and I both reached for first is the wrong one.

The freeze is **NOT lifted** and I took no exception. `precompute_calibration.py`
is untouched — `git diff --stat` for this session is `artifacts/` only.

---

## 0. The board, unchanged from CAL-P139

| | |
|---|---|
| headline MCE (closing line) | **1.88 pp**, target 2.0, `headline_pass: true` |
| NEEDLE | **30/49** cells at bar |
| queued cells | 19 |
| self-check | `ok: true` — 34/34 by_category, 7/7 by_source reproduced exactly |
| `availability` | `stale` |
| `producer_beats_missed` | 0 |
| freeze score | **5/6 clean, 1 miss, WINDOW_NOT_FULL** (18 beats to go) |

---

## 1. THE WINDOW, CLASSIFIED LIVE — AND ONE MISS ALREADY SPENT

Re-baseline `2026-08-29T23:35:53Z`, the first beat that published after Alex's
one-off rewrote `bainluck:bookmaker_calibration`.

```
###B##   <- oldest ... newest
5/6 clean, 1 miss, 1 of 2 budget left, 18 beats to go
```

Beat #4, `2026-08-30T02:38:29.994681Z`, is **class B**, and it is attributed from
the producer's own ledger rather than from its shape:

```
task-metrics(precompute_calibration_main).last_failure_at = 2026-08-30T02:38:30.113985Z
  (0.119 s after the beat's own stamp)
last_failure_type = DBAPIError
last_error        = asyncpg.exceptions.QueryCanceledError: canceling statement
                    due to statement timeout
                    [SQL: SELECT CASE WHEN fo.resolution_source IS NULL THEN 'missing' ...
```

That is `precompute_calibration.py:4025`, run at
`precompute_calibration.py:4047` as stage `read:truth_census` — the same query
CAL-P118-2 named for its class-B beat n=1. **Not the fix's failure mode (D), not
a deploy kill (C), not a gate refusal (A), not the key outage.** `3200b840`'s
class has still fired zero times since CAL-P139 measured it.

### 🔴 The attribution has a one-beat shelf life, and that is now instrumented

B and D are **indistinguishable in the ring.** Both land as
`terminal="failed", gate="not_evaluated"`; the observation carries `gauges` and
`disclosure` and no error at all. The error lives in `task-metrics.last_error`,
which holds exactly one failure and is overwritten by the next.

So the directive's "classify as they happen, not after" is not a preference — it
is the only window in which the question is answerable. `rebaseline.py --watch`
now polls every 7 minutes, classifies each beat **on first sight**, and appends
to an append-only `window-log.jsonl` that later runs never rewrite. A beat
already logged is skipped whole, so a late reader cannot downgrade an
attribution it can no longer make. Where the stamps do not match, the instrument
emits `B_OR_D_UNATTRIBUTED` and says so; it does not shape-match on `elapsed_ms`.

### The ring is not silently improving the score

Checked because the asymmetry is nasty: the freeze score counts clean beats
among the observations that **exist**, so a beat the sampler drops is invisible,
and a dropped MISS *raises* the score. The sampler reports 7 failures in 24 h,
which made this worth measuring rather than assuming.

**50 producer run-ends examined, 0 dropped, 0 ring observations without a
producer run.** The sampler's failures cost nothing. Banked as a negative
result and wired into the instrument so it is re-checked every poll.

---

## 2. 🔴 §6e's DISCRIMINATOR IS `staged_at`, AND IT IS NOT `frozen_over_drift` — I HAD IT WRONG FIRST

The first draft of this instrument labelled a clean beat a re-publish when
`disclosure.frozen_over_drift` was true. Every beat in the window is
`frozen_over_drift: true`, so it produced the right labels — for a reason that
does not hold, and that would have labelled every beat from here to the end of
time a re-publish.

Read the source. Under a rolling re-stage,
`calibration_staged_disclosure.py:267` takes the serving branch:

```python
if serving:
    frozen_over_drift = not drift_known_zero
```

with a comment saying exactly what it means — *"The builder advances every beat
now, so its progress says NOTHING about whether the census being served has
moved."* It is a statement about whether the served census has **drifted**,
which it has by the second beat, forever. It is what drives
`availability: stale`. It is not a statement about advancement.

### What actually advances the population, and the trap in reading it

`promote_if_complete` (`calibration_staged_futures.py:1736`): the moment the
rebuild covers all 128 planned units it is promoted into the serving slot,
`staged_at` is re-stamped, and a fresh rebuild starts at zero. **A new
`staged_at` is a new census; the same `staged_at` is the same census re-served,
however fresh the payload's `generated_at` looks.**

🔴 **And the gauge beside it reads as the exact opposite of the truth.** In the
ring, `rebuild_units_banked` is *never* observed at 128. It is observed at

```
122, 119, 121, 94, 122, 123, 124, 127   and then, each time, 0
```

because the promotion happens **inside** the beat that completes it. Read as a
counter that resets, that is eight rebuilds dying one to nine units short —
which is what I wrote down before checking, and it would have been a
spectacular finding and false. Read against `staged_at`, which advances at
every single one of those eight transitions while `units_banked` stays 128, it
is **eight successful promotions in seven days.**

**Lesson: a counter returning to zero does not say whether it was discarded or
harvested. The timestamp beside it does.** This is CAL-P139's lesson 24 (read
the writer before you trust the column) arriving one gauge over: I read the
gauge, not the function that resets it.

`input_fingerprint` is not a population marker either — per
`REASON_INPUT_FINGERPRINT` it hashes the build's SQL functions, so it moves on a
**deploy** and not on a census. The first draft used it for
`population_moved_in_window`; that field is gone.

### So what the window actually contains

| | |
|---|---|
| censuses served in the window | **1** (`2026-08-29T20:18:32Z`) |
| promotions inside the window | **0** |
| MEASUREMENT beats | **0** |
| REPUBLISH beats | **4** |
| UNKNOWN (no prior published beat to compare) | **1** |

The rebuild stands at **43/128** after 9 beats (~4.8/beat, and the unit cost is
climbing: `unit_ms_mean` 153k → 216k across this cycle). The next promotion is
~18 beats out, which lands within a beat or two of the window's own end at
~`22:35Z`. **The 24-beat freeze window will contain at most one datapoint about
the calibration, at its very last beat.** That is not an argument against the
window — ruling 009 asks about the producer, and re-publishes answer that
question correctly — but any reading of the *number* over this window is one
reading, not twenty-four.

---

## 3. 🔴 THE WINDOW IS ALREADY LOST ON ITS OWN MEASURED RATE

`window-odds.py` prices the remaining budget. The regime matters and pooling is
the mistake it exists to avoid: pre-v3921 has class D live, `01:38Z-20:27Z` on
08-29 is saturated with A's that CAL-P139 §2 proved were measurements of a
missing Redis key, and only what is left describes now.

| band | beats | miss rate | classes |
|---|---|---|---|
| whole ring (pooled — shown to make the error visible) | 168 | 0.601 | A 35, C 32, B-exhaustion 15, BD-early 18 |
| **post-v3921, key-outage excluded** | 13 | **0.429** | C 3, B-exhaustion 2, BD-early 1 |
| post-rebaseline (the live window) | 6 | 0.167 | B-exhaustion 1 |

Carrying the operative rate forward over 18 remaining beats against a budget of
**one**:

```
at 0.429 (measured)                       expect 7.71 more misses   P(22/24) = 0.0006
at 0.273 (no releases during the window)  expect 4.91 more misses   P(22/24) = 0.0251
at 0.050 (the amendment's own "healthy")  expect 0.90 more misses   P(22/24) = 0.7735
```

The third line is the one that reframes it. Even a producer performing exactly
as well as ruling 009's amendment imagines — its own `P_AT_HEALTHY_RATE`
constant — clears this window only ~77% of the time **once one of two misses is
already spent, on beat four**. The gap between 0.77 and 0.0006 is not the
window being unlucky. It is the rate being wrong.

Class C is counted, deliberately. A deploy-killed beat is exogenous and it
spends budget exactly like any other; the amendment is explicit that *"No beat
is excused; that is the point of a budget."* Suppressing releases for 24 hours
is the only lever anyone actually holds, and it is priced separately — it buys
a factor of 40 and still lands at 2.5%.

**Caveat, stated rather than buried: the operative band is 13 beats.** Three
misses in thirteen is a thin base and the true rate could be materially lower.
It cannot plausibly be 0.05.

### The mechanism behind class B, and why it is not random

`plan.deadline_ms` is 1,380,000. Splitting the `failed/not_evaluated` bucket on
it:

| | over deadline | under | total |
|---|---|---|---|
| CLEAN | 2 | 65 | 67 |
| A gate refusal | 2 | 33 | 35 |
| C deploy kill | 0 | 32 | 32 |
| **B/D** | **15** | 18 | 33 |

45% of the ambiguous class ran past its deadline against 3% of clean beats. **An
association with a mechanism, not a partition** — 18 B/D beats did not overrun,
and the one known class-D beat (`08-28T21:33:47Z`) is among them — which is why
the instrument reports the two halves separately instead of renaming the class.

The mechanism is legible in the ledger. Phase budgets are elastic and derived
from the window that is left. At beat #4 the futures rebuild took 6 units and
`staged:window_left_ms` finished at **29,367**; diagnostics got what was left,
its statement timeout collapsed below the ~104 s the truth census needs
(`read:truth_census = 104,144 ms` on the very next clean beat), and the
statement was cancelled. At the clean beat either side — 4 and 5 units,
`window_left_ms` 395,754 and 282,198 — diagnostics fit in 121,980 ms.

**So the futures rebuild and the diagnostics census are competing for one
window, and the rebuild wins.** The rebuild will keep running for the whole
remaining window (43/128, ~18 beats), which is precisely the period the freeze
condition has to survive.

### The shape of it: a census that cannot publish is sequenced ahead of the publish

The five phases run `futures → sports → diagnostics → aggregate →
serialize_gate_publish`, and all five are `required: true`. The truth census at
`:4025` is, by its own comment, a diagnostic — *"No source-bias interpretation;
just the counts + the two RED invariants"* — an unbounded scan of
`futures_outcomes ⋈ futures_markets` over every resolved row. It contributes
nothing the gate reads.

A read that only describes the data is therefore able to stop the data being
published. I am **not proposing the fix**: the phase order, the query and its
budget are all inside `precompute_calibration.py`, which ruling 009 freezes, and
re-ordering a required phase is exactly what the ruling exists to gate. Staged
for Alex as `alex-inbox/calibration-912`.

---

---

## 4. THE HOLD LEDGER — one question is worth 3.8× the next, and it is the one nobody is pointing at

The directive's item 3 names *"the instruments successor queue you wrote
(blocked-refusal instruments)"*. **No queue by that name exists** — the phrase
appears nowhere in the repo or the handoff tree outside the directive itself. The
reading I took, and acted on: `alex-inbox/calibration-908`'s **option 1**, which
proposes re-pointing the conveyor at *"the highest-excess cell whose INSTRUMENT
cannot yet score it"*. Under that reading the highest-value instrument is the one
that makes the blocked state legible, so that is what I built.

`hold-ledger.py` joins a cited disposition map to the **live** scorecard ranking
and groups the excess outcomes by the question each cell waits on.

```
13-CAL      143,495 total   18,763 cell blocked outright
                          + 59,902 banked design cannot LAND: polymarket/esports
                          + 64,830 banked design cannot LAND: kalshi/economics
                            ⛔ cannot be answered before 12-CAL
12-CAL      143,495 total   all of it transitive, via 13-CAL
19-CAL       37,730 · 17-CAL 16,976 · 14-CAL 16,498 · 20-CAL 16,395 · 21-CAL 9,945
```

### The leverage is not where the disposition view puts it

A disposition-only reading says 13-CAL blocks one cell worth 18,763 — seventh on
the board, below four other holds. That is wrong by 7.6×, because **two banked
designs say in their own shipping clauses that the held rule ships with them**:

* `cal-p112/RULE-DESIGN-polymarket-esports.md:170` — *"E, E2 and E3 ship together
  or the cell is worked twice."*
* `cal-p114/RULE-DESIGN-kalshi-economics.md:381` — *"E, E2, E3 and the
  `(source, category)` keying ship together."*

RULE E2 is what 13-CAL HOLDs. So on the day the freeze lifts, those two designs
cannot land either. **A banked design that cannot land is worth exactly as much
as a held cell**, and nothing on the board was counting it.

The two are reported separately rather than summed into one figure, because
"work not yet done" and "work done and stuck" are different states and a single
number hides which is which.

### Two corrections to calibration-908, in both directions

* 🔴 **908 puts the leverage on 13-CAL; the documents put it on 12-CAL.** The
  scorecard's own text is explicit — *"E2 must not land before 12-CAL is
  decided"*. 12-CAL is the root (`clean_vms`' `has_winner >= 1` drops 432
  authoritative graded losses and keeps 395 winners), and answering 13-CAL first
  is not available. The ledger encodes the dependency and credits 12-CAL
  transitively so it cannot rank last merely because nothing names it.
* **908 says "three of the five banked designs"; it is two.** Grepped every
  banked design: `E2` appears in `polymarket/esports` and `kalshi/economics` and
  in no other banked cell. It also appears in `polymarket/basketball`, which is
  *held*, not banked, and there only as a cross-cell check — so it is
  deliberately excluded from the count.

### The part that outlives this session: it is a sensor, not a report

The ledger exits **3** when a cell appears in the live top 19 with no disposition
on file — which is precisely the condition "step 1 has a legal answer again".
Nothing watched for that before; six sessions in a row discovered the empty set
by reading the board and remembering. It also reports `STALE` for a disposition
naming a cell that has left the board, because a cell that left is either fixed
or the board moved under the ledger and both are worth knowing.

Right now: **19 cells, 0 undisposed, 0 stale, EXIT 0.** Step 1 still selects the
empty set, and that is now a measurement rather than a recollection.

---

## 5. What this queue did NOT do

* **No freeze exception taken, and none requested for D21.** Ungranted is
  ungranted. §3's diagnostics re-order is described, not authorized.
* **No rule design was banked and no cell was worked** — there is still no legal
  cell to work, which is now §4's measured result rather than an assertion.
* **CAL-P138-1 (which leg did the curve publish?) is still half-answered**, and
  CAL-P139's reason still stands: it needs the outcome-grain dedup first.
* **The conveyor's step 1 still has no legal answer — a seventh session.**
  `alex-inbox/calibration-908` remains unanswered. I did not invent a cell.
* Nothing shipped. Artifacts only.

## 6. Gate

`pytest -k "calibration or bookmaker or ladder"` — **2,964 passed, 24 skipped,
19,249 deselected, EXIT CODE 0** in 135.99 s. Unchanged from CAL-P136/137/138/139,
as it must be with zero backend files changed. Recorded in `gate.txt`.

## Evidence

| file | what |
|---|---|
| `rebaseline.py` | the re-baseline monitor: taxonomy classifier, §6e discriminator, sampler-coverage guard, `--watch` |
| `rebaseline.json` | §1/§2 — the banked window at `04:35Z` |
| `window-log.jsonl` | the durable first-sight classifications; the half of §1 that survives the session |
| `watch.txt` | the watcher transcript, snapshotted at commit time — the live `watch.log` it is copied from is gitignored by the repo-wide `*.log` |
| `window-odds.py` / `.json` / `.txt` | §3 — regime-split base rates and the forecast |
| `hold-ledger.py` / `.json` / `.txt` | §4 — the cited disposition map, the landing-block dependency, and the step-1 sensor |
| `scorecard.txt` | §0 — the board at `2026-08-30T04:35:25Z`, and §4's input |
| `gate.txt` | §6 |
