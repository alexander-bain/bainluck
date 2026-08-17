# LAT-P061 — the split-scan is REFUSED on measurement, the DDL already won, and the index contradiction was two reads of different moments (#1866, #1881, #1545)

window: 2026-08-17, cycle 33 · branch `program/latency-56` (stacked on `-55`) · parent #1545

## §0 — Headline

| directive item | outcome |
|---|---|
| (a) warmer post-deploy read | ⛔ **NOT GRADED. `-55` is not deployed** — confirmed empirically, not inferred. Found a defect in the registered prediction instead, and amended it before any post-fix read exists (§4). |
| (b) split-scan | ✅ **Index contradiction RESOLVED — nobody was wrong** (§1). ✅ Step 5.3 **passes on plan shape**. 🔴 **THE FLIP IS REFUSED ON MEASURED RUNTIME** (§2). The DDL alone already captured the win. |
| LAT-P058 §8 prediction | Graded row by row (§3). **One row far exceeded, one FAILED, one not gradeable, one owed.** |
| Item 2 reframe | ✅ Re-measured and **confirmed**, with the 2 linkable rows named (§5). |

The single most important sentence in this document: **step 5.3's gate is a cost comparison, and the
cost model gets this backwards.** The `UNION` plans at 4,361.77 against the `OR`'s 12,243.92 and
*runs 4.8× slower*. Had this window flipped the flag on the gate as written — which is exactly what
the gate as written instructs — it would have shipped a regression with a green certificate.

---

## §1 — The index contradiction: two reads of different moments, not a disagreement

The directive named a contradiction between this lane's `indisvalid=false`/0-byte read of branch B
and the Integrator's all-three-VALID after the 240 s rebuild, and ruled the catalogue the arbiter.

**Arbiter read, taken fresh and timestamped by the database itself:**

```
read_at = 2026-08-17 17:57:59.864216+00   (10:57:59 PDT)

relname                       indisvalid  indisready       bytes        size
ix_fm_golf_identity_category     true        true        1,105,920    1080 kB
ix_fm_golf_identity_extid        true        true           40,960      40 kB
ix_fm_source_created_at          true        true        7,741,440    7560 kB
```

**The Integrator is right, and this lane's read was the stale one.** But "stale" is the whole
finding: neither read was wrong *when taken*.

**When did the index go valid?** No catalogue column records it, so it was measured from the scan
counter, and the method is stated so the estimate can be attacked:

- `ix_fm_golf_identity_category.idx_scan` = **63** @ 18:01:54Z, **86** @ 18:08:18Z (+23 / 384 s).
- Of those 23, **~11 were this window's own `EXPLAIN ANALYZE` runs** (all after 18:01:54Z). Backing
  them out leaves production's own rate at **≈1.88 scans/min**.
- 63 scans ÷ 1.88/min = **33.5 min** before 18:01:54Z ⇒ index live ≈ **17:28Z = 10:28 PDT**.

⚠️ **Assumes a constant scan rate**, which is the weakest link — the callers are a request path and a
15-minute sweep, so the true rate is lumpy. Treat 10:28 as ±10 min, not as a timestamp.

**Chronology that dissolves the contradiction:**

| time (PDT) | event |
|---|---|
| ~10:0x | LAT-P060's Phase 0 reads `indisvalid=false, indisready=false, 0 bytes`. **Correct.** |
| ~10:0x–10:28 | INT-075 fails at 60 s twice, drops the stub, succeeds at 240 s. |
| **~10:28 (±10)** | **index becomes valid and starts serving.** |
| 10:11 | v3826 (`160a7cdb`) deploys — *unrelated to the DDL*; the index is not a deploy artifact. |
| 10:57:59 | this window's arbiter read: **all three VALID.** **Also correct.** |

**The lesson, and it is the same one this program keeps buying:** a catalogue read is a *point-in-time
value*, and quoting one without its timestamp turns it into a claim about the present. Both lanes
reported honestly; only the timestamps were missing, so the two facts looked like a conflict. Every
`pg_index`/`pg_stat` read in this program's runbooks should carry `now()` in the projection — which
this window's did, which is why it could be adjudicated in one query instead of a second cycle.

---

## §2 — Step 5.3: PASSES on plan shape. **THE FLIP IS REFUSED.** Branch-B call.

### 5.3 as written — the gate passes

```
UNION plan @ 10:58:57 PDT, EXPLAIN (FORMAT JSON), plan-only

HashAggregate                                      cost 4,361.77
  Append                                           cost 4,327.04
    Index Only Scan  ix_fm_golf_identity_extid     cost    49.81   rows     79
    Index Only Scan  ix_fm_golf_identity_category  cost 4,266.80   rows  6,868
```

Both branches `Index Only Scan`. Zero `Seq Scan`. Total cost **4,361.77**, far under the stated bar
of 128,191.5. **The gate as written says FLIP.**

### And the `OR` — which is what runs today with the flag OFF — is ALSO fully indexed now

```
OR plan @ 10:59:13 PDT

Bitmap Heap Scan                                     cost 12,243.92
  BitmapOr                                           cost    267.67
    Bitmap Index Scan  ix_fm_golf_identity_extid     cost      2.05
    Bitmap Index Scan  ix_fm_golf_identity_category  cost    264.92
```

**128,191.5 → 12,243.92 with no config change at all.** The DDL alone did that. The flip's remaining
claim is only 12,244 → 4,362.

### 🔴 Then the actual runtimes were measured, and they reverse the cost model

Six `OR` and five `UNION` executions, the last eight **alternating in a single loop** so neither
shape gets a systematically warmer pool:

| shape | executions (ms) | warm median | shared **read** blocks | shared **hit** blocks |
|---|---|---|---|---|
| **`OR`** (live today) | 166.5 (first), 38.3, **17.3, 19.9, 16.6, 18.4** | **≈18.4 ms** | 903 cold → **0** warm | **3,762** |
| **`UNION`** (flag ON) | 98.2, **88.2, 84.8, 96.7, 66.7** | **≈88.2 ms** | **0** always | **9,219** |

**The `UNION` is ~4.8× slower and touches 2.45× more buffers.**

The plan says why, and the sub-node timings are unambiguous: the `UNION`'s `Append` costs only
**9.4 ms** — the index-only scans are genuinely fast — and **94.1 ms of its 98.2 ms is the
`HashAggregate`**. `UNION` must de-duplicate (a row can match both branches, so `UNION ALL` is not
correctness-preserving here), and de-duplicating 7,201 rows of width 1,056 builds a ~7.6 MB hash
table on every call. The `OR` never pays that: `BitmapOr` merges the two bitmaps and does one heap
pass.

**Where the `UNION` genuinely wins, stated because it is real:** it reads **0 blocks from storage,
always**, because both scans are index-only and covered. The `OR` pays **903 blocks** on a cold pool.
Since this whole programme exists because physical reads evict the trigram indexes from a 1 GiB
`shared_buffers`, that is not a trivial advantage. But the `OR`'s cold cost is now **903 blocks
(7.4 MB)**, down from **515.2 MB/call** — it has stopped being an eviction source in any meaningful
sense, and 7.4 MB occasionally is not worth 70 ms on every call.

### 🔴 Branch-B call — **DO NOT FLIP `GOLF_IDENTITY_SPLIT_SCAN`**

**No flip request is posted to the Integrator. The opposite is: the pending flip should be
WITHDRAWN**, and the config var left unset permanently unless new evidence arrives.

| | before DDL | after DDL, flag OFF (today) | after flag ON |
|---|---|---|---|
| plan | Seq Scan, 977 MB | `BitmapOr`, both indexes | `Append` of two Index Only Scans |
| planner cost | 128,191.5 | **12,243.92** | 4,361.77 |
| **warm runtime** | ~2,900 ms (mean) | **≈18 ms** | ≈88 ms |
| read blocks/call | **515.2 MB** | 0 warm / 7.4 MB cold | 0 |
| **verdict** | the defect | ✅ **the fix** | ❌ **a 4.8× regression** |

**The DDL was the entire fix. The `UNION` was a workaround for the absence of the index, and it
outlived its reason.** `golf_identity_select()` can keep the gated shape as dead-but-tested code, or
the next queue can delete branch B and its flag; either is fine, and neither is urgent.

### The gate itself is defective, and this is its second sibling in one window

**5.3 gates on a cost NUMBER.** LAT-P061's own staging file already warned about exactly this for the
evictor's Option A — *"must gate on PLAN SHAPE, not a cost number"* — and the same correction is
owed here, one step further:

> **Plan shape is necessary and not sufficient. A gate that authorises a config change must compare
> MEASURED RUNTIME of both shapes, paired and alternating, before it says flip.**

`EXPLAIN`'s cost is a unitless planner estimate for choosing between plans of the *same* statement.
Comparing costs **across two different statements** — which is precisely what 5.3 does — is not what
the number is for, and here it is wrong by a factor of 24 in the ranking direction. Same family as
gotcha #124's `Total Cost ≠ runtime until act+loops say so`, promoted from a caveat to a gate defect.

---

## §3 — LAT-P058 §8's registered prediction, graded

Registered before the DDL (`lat-p058-golf-index-spec.md` §8). Graded now that the DDL half exists —
and note this table's own preamble scopes it to **step 1 alone**, *"Step 1 alone is not predicted to
fix the tail"*, so it does **not** depend on the flag. The flag half remains unflipped and, per §2,
should stay that way.

| # | surface | prediction | measured | verdict |
|---|---|---|---|---|
| 1 | 46 gold dispositions | 0 of 46 change; 39/44, MRR 0.8913043478260869 | **NOT READ this window** | ⛔ **OWED** (§6) |
| 2 | golf completed-tournament route | p50 **2.74 s → < 500 ms** | warm 2.23 / 2.26 / 2.43 / 2.87 s, **median ≈2.35 s** | ❌ **FAIL — ~14%, not ~82%** |
| 3 | DB physical read rate | **79.1 → ~62 MB/s** (a 21% cut); pool turnover 12.9 → ~16.5 s | statement-level **516.7 → 2.395 MB/call, 427.6 → 3.2 GB/day (99.5% cut)**; whole-DB **not gradeable** | ⚖️ **SPLIT — one half far exceeded, one half unmeasurable** |
| 4 | #1866's typeahead tail | **0–15%**; **> 30% ⇒ HALT**, name which model you now believe | median miss cost **1730.5 → 1012.6 ms = 41.5%**, inside a **±30–42% noise band** | ⚖️ **NOT GRADEABLE — the HALT threshold sits inside the instrument's own noise** |

### Row 2 — FAIL, and the reason is the useful part: the bottleneck MOVED

`GET /api/golf/tournaments/{slug}`, warm passes, four completed majors:

```
the-open-championship  5.71 s -> 2.87 s      pga-championship  4.44 s -> 2.43 s
us-open                3.05 s -> 2.23 s      the-open          2.04 s -> 2.26 s
control /api/golf (the cached prefix every one of these runs first)  0.47 s x3
control /api/health                                                  0.24 s
```

The spec attributed the route's whole cost to `_build_completed_tournament`'s phase 1, because phase 1
was the database's **#1 physical-read consumer**. Phase 1 is now **≈18 ms** — about **0.8%** of the
route. The route is still 2.35 s.

**Phase 2 is what is left, and it was never a physical-read problem.** `The Open` alone matches
**45 markets carrying 4,621 outcomes (102.7 per market)**, which phase 2 hydrates through
`selectinload` and then assembles into a **99–172 KB** JSON body. Those rows are largely
buffer-resident: cheap in blocks, expensive in ORM row construction and serialization.

> **A statement can be #1 in physical reads and a minority of wall time at the same time.** The spec
> ranked by one dimension and predicted the other. This is the third instance of that error in this
> window (§2's cost-vs-runtime, §4's duration-vs-work, and this one), and they are the same mistake.

Row 2 is a real miss, not a technicality: the *user-visible* promise of the golf work — the majors
load fast — is **not delivered**. The next lever is phase 2's hydration + payload, not the index.

### Row 3 — SPLIT. The statement-level half is the clean one.

**Statement-level, `queryid 184240953744049829`, delta over a fixed 764 s interval** (the method
`lat-p059-pgstat-delta.json` prescribes, because the counter is cumulative and never resets):

```
T0 18:00:14Z   calls 9,092   shared_blks_read 599,529,561
T1 18:12:58Z   calls 9,104   shared_blks_read 599,533,240
delta:  12 calls,  3,679 blocks (28.7 MB)

MB per call:  516.7  ->  2.395     (99.54% reduction, ~216x)
GB per day :  427.6  ->    3.2
```

✅ **Far beyond the predicted 21%.** The prediction was not merely conservative, it was built on the
wrong denominator: it reasoned from the entry's *lifetime cumulative* blocks rather than from a rate
over a window, which is the exact error `lat-p058-golf-index-spec.md` §5.4 warns about three
paragraphs above the prediction it then made.

⛔ **Whole-DB half — NOT GRADEABLE, because the instrument is bursty by an order of magnitude:**

| window | length | measured whole-DB read rate |
|---|---|---|
| 18:13:18Z → 18:14:03Z | 45 s | **4.74 MB/s** |
| 18:14:17Z → 18:17:08Z | 171 s | **40.97 MB/s** |

**An 8.6× disagreement between adjacent windows.** Against that, "79.1 → ~62 MB/s" is a distinction
this instrument cannot draw, and the 79.1 baseline itself was taken over an unstated window. Reporting
either number as the grade would be picking a window to get an answer. *(For the record: 40.97 MB/s
is a 48% cut and 4.74 MB/s is a 94% cut — both "beat" the prediction, which is why neither is
evidence.)*

### Row 4 — the HALT threshold is inside the noise. Answering the question anyway.

Five probe runs, `probe_typeahead_segments.py --rounds 3`, same script, same production, same
un-deployed pre-fix warmer in all five:

| run | at (PDT) | pre-warmed | miss cost, server p50 |
|---|---|---|---|
| P060 r1 | 10:30:38 | 14/24 | 1497.1 ms |
| P060 r2 | 10:34:25 | 8/24 | 1963.9 ms |
| **P061 r1** | 11:06:31 | 13/24 | **1012.6 ms** |
| **P061 r2** | 11:12:17 | 8/24 | **845.7 ms** |
| **P061 r3** | 11:17:05 | 4/24 | **1197.3 ms** |

Median 1730.5 → 1012.6 ms = **41.5%**, which nominally trips the `> 30%` HALT.

**It does not count, and here is why.** Within the pre pair the spread is **31%** (1497→1964) with
nothing changed between them; within the post triple it is **42%** (846→1197), likewise. **The
threshold the HALT is drawn at is smaller than the instrument's own run-to-run variation.** A rule
that fires inside its own noise cannot discriminate — the same defect as a bar above a ceiling
(ruling 074 clause 2), relocated from the target to the tolerance.

⚠️ **Second confound, and it is fatal to using P060's runs as a baseline at all:** the index went live
at **~10:28 ± 10 min** (§1). P060's runs are 10:30 and 10:34. **They are almost certainly already
post-index**, taken while the new index's own pages were cold. So the pre/post framing may be
measuring index-page warm-up rather than the index.

**What can honestly be said:** all three post runs sit below both earlier runs. Under a null of no
effect, P(all 3 below all 2) = 1/C(5,3) = **1/10, p = 0.10**. Directionally consistent with the
mechanism, nowhere near established.

**The question the HALT demands — which model do I now believe?** *Neither, and the honest answer is
that this instrument cannot separate them.* The continuous-throughput model (0–15%) and the
periodic-eviction model (larger) make predictions 30 percentage points apart, and the probe's noise
band is 40 points wide. **More runs of this probe will not fix that** — its variance is dominated by
whatever else is sweeping the buffer pool during the run, which is exactly the quantity under test.

**The discriminating instrument is a different one, and it needs no new extension.** Measure the
mechanism directly rather than its downstream consequence: `pg_statio_all_indexes`
`idx_blks_read`/`idx_blks_hit` **as a delta over a fixed interval** on
`ix_futures_outcomes_name_trgm` (406 MB) and `ix_futures_name_trgm` (172 MB). Physical reads against
*those two indexes* is what "the trigram pages are not resident" means, stated as a number, with no
client, no network, and no dependence on which prefixes the probe happened to draw. `pg_buffercache`
would be better still and is **not installed** (extensions present: `pg_stat_statements`, `pg_trgm`,
`plpgsql`). Baseline sample taken this window and recorded in §6 so the next window can take the
delta rather than starting over.

---

## §4 — Item 0: NOT GRADED. `-55` is not deployed — and the prediction had a defect worth more than the read.

**Confirmed empirically rather than inferred from git.** `/api/admin/task-metrics?task=warm_typeahead`:

```
last_result_summary = {terminal: "complete", completed: 40, total: 40,
                       head_source: "redis:search:trending:24h", warmed: 40,
                       timeouts: [], errors: [],
                       seconds_total: 0.294, seconds_max: 0.009}

concurrency  ABSENT      seconds_wall  ABSENT      rebuilt  ABSENT      fresh  ABSENT
```

Pre-fix shape exactly. `/api/health` = `160a7cdb`; `-55` carries 4 unmerged commits. **Nothing
graded**, per the queue's own instruction, which has now held for four consecutive windows without
decaying into a shrug.

Two things worth having anyway:

**1. Hole 2 caught in the act.** That summary *is* a no-op pass: 40 Redis GETs in **294 ms**,
`seconds_max` **9 ms**, reporting `terminal: complete, warmed: 40/40`, having rebuilt nothing. The
defect `-55` fixes, photographed live.

**2. 🔴 The registered prediction's row 4 would have graded PASS on unchanged code.** Full working in
`lat-p060-warmer-arithmetic.md` **§8.1**, written this window and dated before any post-fix read
exists. In short: the no-op band **moved** from 0.6–0.9 s to ~300–400 ms because its duration is
40 sequential Redis GETs — a measurement of Redis, not of the warmer.

| band | LAT-P060 (pre-fix) | LAT-P061 (pre-fix, same code) |
|---|---|---|
| lock skips `<100 ms` | 25 | **12** |
| **no-op `0.6–0.9 s`** | **12** | **0** ← row 4's pass condition, already met |
| **no-op `~300–400 ms`** | — | **13** |
| real passes `>1 s` | 13 | **25** |

Row 4 is re-expressed as `rebuilt == 0 on a pass reporting complete`, a predicate over work
performed. Banked as **ruling 074** clause 1. Row 3 inherits a weaker form of the same defect and is
left standing with an explicit warning to grade it against the concurrent pre-fix read (12), not the
registered 25.

✅ **Row 1's baseline survives and is now stronger.** Pre-fix `excluded_pre_warmed` across six runs
and three windows: 14, 7 (P059) · 14, 8 (P060) · 13, 8, 4 (P061) — **mean ~9.7, stable**. The
`≥ 20 of 24` criterion against a measured ceiling of 24 is measured against a real, repeatedly
confirmed baseline.

---

## §5 — Item 2: the reframe re-measured and CONFIRMED, with the 2 named

The directive accepted LAT-P060's reframe — 22,884 of 22,886 unlinkable-by-design is a **permanent
population, not a backlog** — and asked for the 2 linkable to be routed. Re-measured today against
the **exact predicate from `tasks/polymarket.py:1305`**:

```
subs under LINKED polymarket_event parents : 228,468 rows across 12,916 groups
   ...of which still event_id IS NULL      :         2
```

**Both still unlinked, and both are over 24 hours old:**

| id | name | group_id | created | parent event | parent |
|---|---|---|---|---|---|
| 59080633 | Ann vs. Zhao: Match O/U 23.5 | `polymarket:860454` | 2026-08-16 20:05:11Z | 15199960 | ITF M15 Maanshan 7 Men |
| 59080445 | Kim vs. Muramatsu: Set 2 Games O/U 10.5 | `polymarket:860536` | 2026-08-16 20:05:00Z | 15200024 | ITF W15 Tianjin 3 Women |

**This is not a one-line fix — it is evidence that the later-batch hole already exists in the shipped
code.** `_process_event_batch` propagates `event_id` only inside batches the poll touches; parents are
linked separately by `match_prediction_markets` every 15 min. These two parents linked *after* their
group was last polled, so the propagation has not run for them and will not until a future batch
happens to include that group — **24 hours and counting.**

The consequence for the LAT-P060 recommendation is worth stating plainly, because it cuts against the
option that looked safest: **Option B's "later-batch hole" was treated as a NEW risk B would
introduce. It is not new. The current code has it**, and these two rows are the specimen. B does not
create the hole; it makes the hole cheaper to have. Whatever periodic low-frequency sweep B needs,
**today's code needs it too** — and that reframes the choice from "A is safe, B is risky" to "both
need the sweep; A also pays a permanent full scan."

**Routing:** the 2 rows need a single bounded `UPDATE` restricted to those two `group_id`s — a
**write**, therefore ops/Integrator, not this lane. Yield is 2 rows; the value is entirely in what it
demonstrates, so it should not be run before the finding is read.

### ⚠️ A near-miss this window, recorded because the control is the only reason it was caught

The first census joined `parent.external_id = sub.group_id`. The real statement joins
**`parent.group_id = sub.group_id`**. The wrong query returned **0 rows** — a clean, fast, entirely
plausible "the 2 have already been linked, nothing to do", which is a *better* story than the truth
and would have been reported as a finding.

It was caught by running the **same join with the filter removed as a control**: that also returned 0,
and "no sub-markets exist under any linked parent" is impossible on a database with 228,468 of them.
**The zero was in the join, not in the world.**

> **Proposed gotcha (not self-issued — a lane proposes):** *before believing a census's zero, re-run
> it with the selective filter removed.* If the control is also zero, the join is broken, not the
> population empty. Direct sibling of #53 (an empty 200 is a response shape, not a fact), and the
> same failure mode as a query that returns nothing because a predicate never matches.

---

## §6 — What this window owes, with exit conditions (ruling 066)

| owed | to whom | exit condition |
|---|---|---|
| **The warmer post-fix read** (§8 + §8.1 as amended) | next latency window | `/api/health` reports a commit containing `8a352501` **and** `last_result_summary` carries `concurrency`. Grade row 4′, not row 4. |
| **Gold read + corpus-delta** (golf §8 row 1; ruling 073's first paired use) | next latency window | run with `--compare-against` LAT-P059's graded artifact; report the fingerprint verdict whether or not dispositions moved. **Not taken this window** — the window's reads went to the split-scan adjudication the directive ordered first. |
| **The trigram-residency delta** — the instrument that can actually settle row 4 | next latency window | baseline below; take the delta over ≥ 15 min and compare. |
| **The 2-row `UPDATE`** | ops / Integrator | after §5 is read; 2 rows, `group_id IN ('polymarket:860454','polymarket:860536')`. |
| **Withdraw the `GOLF_IDENTITY_SPLIT_SCAN` flip** | Integrator | §2. No action is the correct action — the var stays unset. |

### The trigram-residency instrument, proven out with a first reading

Not just a baseline — it was taken twice this window, and it answers in one query what five probe
runs could not:

```
T0 = 2026-08-17 18:18:00.732825+00     T1 = +171 s

index                            +blks_read   +blks_hit   hit %   physical read rate
ix_futures_name_trgm                  1,036       5,268    83.6%        0.05 MB/s
ix_futures_outcomes_name_trgm        20,833      67,673    76.5%        0.95 MB/s
                                                          COMBINED      1.00 MB/s
```

**Read it as: 170.9 MB of trigram index pages were fetched from storage in 2.8 minutes, against a
combined index footprint of 578 MB.** Roughly 30% of the trigram working set is being re-read from
disk every three minutes, and **~1 in 4 accesses to `ix_futures_outcomes_name_trgm` misses the buffer
pool** — on the index that dominates `/typeahead`'s cost.

That is #1866's thesis stated as a measured rate, with no client, no network, no prefix sampling and
no dependence on which queries the probe happened to draw. **It is the instrument row 4 should have
been written against**, and unlike the probe it is cheap enough to take on every window.

⚠️ One reading is not a number (ruling 064). This is one 171 s window on a workload §3 row 3 has just
shown to be bursty by 8.6×. Take it ≥ 3 times before treating 1.00 MB/s as the baseline.

Cumulative counters for the next window's delta:

```
read_at = 2026-08-17 18:18:00.732825+00

ix_futures_name_trgm            idx_blks_read      90,690,519   idx_blks_hit     299,615,990
ix_futures_outcomes_name_trgm   idx_blks_read     228,100,680   idx_blks_hit     492,189,059
```

```sql
SELECT indexrelname, idx_blks_read, idx_blks_hit, now() AS read_at
  FROM pg_statio_all_indexes
 WHERE indexrelname IN ('ix_futures_outcomes_name_trgm','ix_futures_name_trgm');
```

---

## §7 — LAT-P061 Items 2 and 3, taken after the directive's ordered work

### Item 2 — the head cannot adapt. **Premise-check answered with a number, and the answer is neither branch the queue anticipated.**

The queue asked for a number, not a proposal: *"measure how much the head would actually differ if the warmer's votes were excluded… If the answer is 'barely', say so and close it."*

**Warmer head, live** (`GET /api/events/search/trending`, top 5 with scores, 2026-08-17 ~12:0x PDT):

```
red sox 1768 · celtics 1758 · yankees 1757 · world cup 1752 · patriots 1745
```

Against **1,632 warmer successes/24 h** — the scores are, to within a few percent, the warmer counting
its own passes. LAT-P060's ~89%-self-echo measurement reproduces.

**So what would the head be from the source it is nominally modelled on?** `search_query_logs`, 30 days,
3,598 rows / 212 distinct:

| rank | /search as logged | n |
|---|---|---|
| 1 | stanley cup | 90 |
| 2 | world series | 84 |
| 3 | masters winner | 80 |
| 4 | nba champion | 79 |
| 5 | yankees | 77 |

**Overlap with the warmer head: 1 of 5.** Which looks damning — and then the timestamps were read.

### 🔴 The comparison baseline is polluted too, by a different piece of our own automation

```
minute   rows  distinct_q  days
07:10     783          32     26     <-- one minute a day, 26 of 30 days, 32 queries
07:11      65          12      7
04:24      42          42      2     <-- everything else looks like this
```

**848 of 3,598 rows (23.6%) land in the 07:10–07:11 window**, across 26 days, with 32 distinct queries.
That is the **nightly gold-query sentinel (#1206)**, whose whole design is ~50 family-phrased queries
run on a schedule — and *stanley cup / world series / masters winner / nba champion / ballon d'or /
grammys / oscars* are exactly its phrasings. The top four rows of the "real" distribution are our own
sentinel.

**Re-ranked with the sentinel window excluded:**

| rank | /search, sentinel excluded | n | warmer head rank |
|---|---|---|---|
| 1 | **yankees** | 77 | **3** |
| 2 | **red sox** | 75 | **1** |
| 3 | fed | 66 | — |
| 4 | chiefs | 65 | — |
| 5 | stanley cup | 64 | — |
| 9 | world cup | 46 | **4** |
| 10 | celtics | 44 | **2** |

**The number: 2 of 5 overlap at rank 5.** The warmer's #2 (`celtics`) and #4 (`world cup`) are human
ranks **10** and **9**; `fed` and `chiefs` are human top-4 and are **not warmed at all**.

**Verdict — not "barely", and not a straightforward defect either.** The head is *plausible but stale*:
every member is in the human top ~12, so nothing absurd is being warmed, but the ordering is frozen
and two genuine top-4 queries are missing. The queue's proposed close ("a self-fulfilling head that
happens to be the right head is a documentation problem") **does not apply** — it is not the right head.

**The finding that outranks the original one, and it changes what a fix would even look like:**
**both candidate head sources are contaminated by our own automation** — `search:trending:24h` by the
typeahead warmer (~89%), `search_query_logs` by the gold sentinel (23.6%, concentrated at the top).
There is currently **no clean user-query distribution in the system**. Any head-selection change would
be tuning against a signal we generate, so the prerequisite is a **provenance flag on the logging
path** (mark automation-originated searches at write time), not a smarter ranking. That is a small,
well-scoped piece of work and it is the one that unblocks the rest.

⚠️ Carried forward: LAT-P061's own staging file warns that **any future change letting warm passes hit
the cache would silently stop the voting** (`/typeahead` votes on the miss path only), freezing the head
completely. `-55` deliberately keeps missing, so it does not trip this — but it is now one refactor away.

⚠️ Also noted, not chased: `search:trending:24h` calls `expire(key, 86400)` **on every write**
(`events.py:4791`), so the key resets only after 24 h of total silence — which the warmer's ~96 s
cadence guarantees never happens. The `:24h` in the name is not a window. The observed scores
(~1,768 against ~1,632 passes/day) are consistent with roughly a day's accumulation rather than
unbounded growth, so something is resetting it — Redis eviction or a restart is the likely candidate.
**Unresolved, and flagged rather than asserted**: a key whose retention is set by an unidentified
mechanism is not a measurement instrument.

### Item 3 — cadence↔TTL hygiene: **premise-check answered, change NOT taken**

The queue gates this on *"only if the beat file is already open"*. **It is not** — this window makes no
beat-schedule change, so `beat_schedule_change: false` and `tests/test_tasks_wiring.py` is untouched.
The premise-check it asked for was cheap, so it was taken anyway:

> *"Check whether their caches, like `/typeahead`'s, fail to extend on a hit; if they do, the waste is
> the only effect and the hygiene is free."*

**Answer: they DO extend, and the mechanism is the mirror image of `/typeahead`'s.**
`precompute_admin_health.py` writes with `ex=_ADMIN_HEALTH_CACHE_TTL` (3600) **unconditionally on every
run** — the writer is the scheduled task itself, not a route that returns early on a cache hit. So each
beat genuinely refreshes the TTL.

**Therefore the waste is the only effect, and the hygiene is free.** `precompute-admin-link-rate` and
`precompute-admin-matured-linkage` at `*/10` and `precompute-admin-audit-all` at `*/15` recompute six
and four times per cache lifetime; five of six and three of four buy nothing but a slightly younger
number. Worth ~20 GB/day (**0.7%** — real hygiene, and it must not be reported as a fix).

**Recommendation for whoever next opens the beat file:** `*/10 → */30` and `*/15 → */30` keeps two
refreshes inside every 3600 s TTL, preserving the deliberate slack the module comment describes
(*"generous so a few skipped beats never empty it"*), while cutting the recompute count by ~3×.
Declare `beat_schedule_change: true` and update the `test_tasks_wiring.py` allowlist (gotcha #12).
