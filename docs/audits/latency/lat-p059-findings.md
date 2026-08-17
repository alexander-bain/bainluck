# LAT-P059 — the read that could not be graded, and the one that could

**Window:** latency lane cycle 31, `pid:42538`, 2026-08-17 ~09:15–1x:xx PDT.
**Branch:** `program/latency-54`, cut fresh from `origin/master` `3fce786718ca5ddc5cb721722c68eeddd8ab8fbe`.
**Deployed commit at read time:** `3fce7867` (`/api/health`), i.e. the branch base IS the deploy.
**Flag:** `GOLF_IDENTITY_SPLIT_SCAN` — **unset**, re-read at Phase 0 and again before writing this.

---

## Item 0 — the ruling-050 prediction is **NOT GRADED**, and here is the missing half

The Fable directive was explicit: *"grade the registered prediction only after BOTH halves exist
(DDL run + flag flipped past pg_stat step 3), or grade nothing and name the missing half."*

**Neither half is complete.** Measured, not assumed:

| half | required | actual, 2026-08-17 | verdict |
|---|---|---|---|
| **DDL** | three VALID indexes | **2 of 3.** `ix_fm_golf_identity_category` is a **0-byte, `indisvalid=false`, `indisready=false` stub** | ⛔ **INCOMPLETE** |
| **flag** | `GOLF_IDENTITY_SPLIT_SCAN` truthy, past §5.3 | **unset** | ⛔ **ABSENT** |

The missing index is not the incidental one. **It is branch B — the branch that carries 7,263 of
the query's 7,343 rows.** Branch A's index (`ix_fm_golf_identity_extid`, 40 kB, valid) serves ~80
estimated rows. So the DDL is "2 of 3" by count and **0 of 1 by effect** on the golf query.

**Therefore every row of the prediction table is ungraded**, and the honest reason is the same for
all four: the change whose effect they predict is not running in production. Restated so it is not
softened in transit, with what IS known beside it:

| surface | prediction | what is actually true today |
|---|---|---|
| 46 gold dispositions | 0 of 46 change; 39/44; MRR 0.8913043478260869 | **not graded as a prediction** — nothing golf-related is live to move them. The armed control is reported separately below. |
| golf completed-tournament route | p50 2.74 s → < 500 ms | **not graded.** The `OR` still runs; see the counters below — it got slightly *worse*, which is drift, not a result. |
| DB physical read rate | 79.1 → ~62 MB/s; turnover 12.9 → ~16.5 s | **not graded.** No reduction was applied, so there is nothing to attribute. |
| **#1866 typeahead tail** | 0–15%, explicitly not fixed; **> 30% HALTS** | **not graded against the golf change** — but the tail WAS measured this window as `-51`'s control, and it did not improve. See Item 1. **No halt.** |

### The `OR` statement drifted the wrong way, which is worth recording

`queryid 184240953744049829`, the same anchor, cumulative:

| | 2026-08-14 (LAT-P058) | 2026-08-17 (this window) |
|---|---|---|
| calls | 5,829 | **9,016** |
| mean | 2,741.3 ms | **2,913.3 ms** |
| MB per call | 492.5 | **516.7** |

It is doing *more* work per call than when the spec was written, not less. That is the expected
behaviour of an unfixed full-heap Seq Scan against a table that keeps growing, and it is the
baseline the eventual fix will be graded against.

---

## The two verification steps in the runbook that are no longer safe

Both are corrected in place in `lat-p058-golf-index-spec.md` §0b. They belong here too, because
they are instrument defects of the class this program exists to find: **a check that cannot fail,
and a check that now passes for the wrong reason.**

### 1. §5.4's index-usage query returns zero rows, always

It filtered `pg_stat_user_indexes` on **`relname`**. In that view `relname` is the **table** name;
the index name is **`indexrelname`**. Measured both ways within one minute:

```
pg_stat_user_indexes WHERE relname      IN ('ix_fm_...')  ->  0 rows
pg_stat_all_indexes  WHERE indexrelname IN ('ix_fm_...')  ->  3 rows, real counters
```

The step's stated reading is *"`idx_scan = 0` an hour after the flip means the planner is not using
them ⇒ report back."* An empty result set is **not** `idx_scan = 0` — it is the absence of an
answer (gotcha #53). As written, the step reports the same thing whether the indexes are unused,
missing, or working perfectly.

### 2. §5.3's numeric cost bar now PASSES while the fix is absent

The gate said: require both branches indexed **and a total cost well under 128,191.5**. Re-measured
against the current, partially-indexed catalogue:

| shape | plan | total cost |
|---|---|---|
| `OR` (today's default) | one Seq Scan | **128,261.89** |
| `UNION` (gated) | Index Only Scan `ix_fm_golf_identity_extid` (45.89) **+ Seq Scan branch B (127,864.28)** + Sort + Unique | **128,033.85** |

**128,033.85 is under 128,191.5.** The numeric half of the gate passes today, with branch B still
sequentially scanning the entire 977 MB heap and reading exactly as many pages as before. The
`UNION` is now **0.998×** the `OR` — so the *old* objection ("a 1.99× regression", "would roughly
double the largest query") is stale, and a reader re-deriving *"is it still 2×?"* now correctly
gets **no** and may conclude the obstacle is gone.

**It is not gone. The verdict is unchanged — DO NOT FLIP — and only the reason changed:** flipping
now buys a Sort + Unique and a 0.2% cost delta in exchange for zero reduction in physical reads.

**A cost ratio cannot express this gate**, because one cheap indexed branch drags the aggregate
under any threshold you pick while the expensive branch is untouched. The gate is **plan shape**:
read both node types.

### What DID land — A2, graded on live traffic over a fixed interval

`ix_fm_source_created_at` — the A2 index, which needed neither the code half nor the flag — is
real, valid (7,520 kB) and in active use: **`idx_scan = 3,360`, `idx_tup_read = 278,374,078`**.

INT-071 graded it with an `EXPLAIN (ANALYZE)` (0.149 ms, 0 shared read blocks). This window grades
it the harder way — **on real production traffic, as a delta over a fixed 22.6-minute interval**,
which is the discipline the queue demanded and which an `EXPLAIN` of one hand-written statement
cannot supply:

| `SELECT MAX(created_at) FROM futures_markets WHERE source = $1` | value |
|---|---|
| calls in the interval | 4 |
| `shared_blks_read` in the interval | **8 blocks — total, across all four calls** |
| ⇒ per call | **~2 blocks ≈ 16 kB** |
| before the index (spec baseline) | **186.6 MB per call** ≈ 23,000 blocks |

**A ~99.99% reduction in physical reads per call, measured on live traffic.** This is the single
unambiguous win of the LAT-P058 program to date, and it is worth being precise that it arrived
**without the code half and without the flag** — statement (3) in the runbook was always
independent of the golf branch, and judging it separately is what let it be banked while the rest
is still blocked.

### The full-interval read-rate table — and it corrects a ranking

All eight top consumers, same 22.6-minute interval (`lat-p059-pgstat-delta.json`):

| queryid | statement | Δcalls | MB/s | **GB/day** |
|---|---|---|---|---|
| `184240953744049829` | **the golf `OR`** | 17 | **5.07** | **427.6** |
| `-5968390436689514332` | `max_movement_24h` UPDATE | 2 | 0.91 | 77.0 |
| `8206311991729879112` | feed category/league scan | 2 | 0.59 | 50.0 |
| `-749027317737976872` | **evictor #2** | **0** | 0.00 | **0.0** |
| `-6729221129999282418` | A2 `MAX(created_at)` | 4 | 0.00 | **0.0** |
| `1186417916192834599` / `5028865687801582843` / `-2626243287596648543` | — | 0 | 0.00 | 0.0 |
| | | | | **554.5 total** |

**The golf `OR` is confirmed as the current number-one consumer by rate — 427.6 GB/day, 77% of the
measured total.** The spec's "19% of every physical read" framing holds on a rate basis. Evictor #2
read **zero** in this interval because it is bursty (it fires inside Polymarket poll batches, not
continuously), which is exactly why cumulative totals and instantaneous rates disagree about it —
see Item 3.

---

## Item 1 — the `-51` warmer read: **taken, twice, and the tail question is answered**

`-51` is merged and deployed (`git cherry` = 0; `/api/health` = `3fce7867`). Owed for three
windows; taken here.

### The warmer is running, and its own summary is clean

`GET /api/admin/task-metrics?task=warm_typeahead`:

```
successes_24h 1438   failures_24h 0   incompletes_24h 0   hard_kills_24h 1
last_result_summary: {"terminal": "complete", "completed": 40, "total": 40,
                      "head_source": "redis:search:trending:24h", "warmed": 40,
                      "timeouts": [], "errors": [], "seconds_total": 32.064}
```

All three of the sanity checks the queue named are **green**: `terminal` is `complete`, not
`skipped` on every beat (no wedged lock); `head_source` is the measured Redis source, not
`static_floor` (both measured sources did not come back empty); `warmed` is 40 of 40. Cadence
confirmed at ~30 s from `successes_window_s / successes_24h` = 43,041 / 1,438 ≈ 29.9 s.

### Primary criterion: **MISSED**, twice — and the second read found the reason

Criterion: `excluded_pre_warmed` **≥ 20 of 24**, up from **0 of 24**. Taken twice (ruling 064):

| run | start | pre-warmed | round 0 | round 1 | round 2 |
|---|---|---|---|---|---|
| head run 1 | 16:26 UTC | **14 of 24** | 0 of 8 | **7 of 8** | **7 of 8** |
| head run 2 | 16:33 UTC | **7 of 24** | 0 of 8 | **0 of 8** | **7 of 8** |
| tail control | 16:28 UTC | **0 of 24** | 0 of 8 | 0 of 8 | 0 of 8 |

**The two runs disagree by 2×, and that disagreement is the finding.** A single run would have been
read as "14 of 24, close-ish, call it a partial pass". Two runs show the head is not steadily warm
— **it oscillates**. Note also that `patriots`, which run 1 suggested was simply absent from the
head, **was pre-warmed in run 2** (229.4 ms). No query is permanently in or out.

### 🔴 Why: the warmer repaints every ~96 s a cache that forgets in 45 s

Measured from `task-metrics`, 50 most recent invocations over a 1,438 s window:

| | measured |
|---|---|
| beats that were **real passes** (> 1 s) | **15** |
| beats that were **lock skips** (< 100 ms) | **30** |
| beats in between (0.1–1 s) | 5 |
| ⇒ **interval between real passes** | **95.9 s** (71.9 s counting the mid band) |
| pass duration | median **33.1 s**, **max 74.2 s**, last `seconds_total` **72.2 s** |
| **route response-cache TTL** | **45 s** |

**`typeahead_warmer.py:59` states the design premise outright: *"30s is inside the route's 45s
TTL"*. In production that premise is false.** The beat is every 30 s, but a pass takes 33–74 s and
the Redis lock serializes them, so 30 of every 50 beats are no-ops and the true repaint period is
**~72–96 s against a 45 s TTL**. Every head query therefore spends roughly **30–50 s of each cycle
cold** — the head is warm about **44% of the time** (21 of 48 pairs across the two runs), not
continuously.

That single number explains all three observations: the run-to-run swing (the probe samples a
different phase of the oscillation), the always-cold round 0, and why **≥ 20 of 24 was not reachable
by any phase of this warmer**. The criterion assumed continuous warmth; the warmer does not provide
it.

**`-51` is therefore delivering roughly half of its intended benefit**, and the shortfall is a
cadence/TTL mismatch, not a defect in the warming itself — every pass that runs reports
`warmed: 40/40, errors: [], timeouts: []`.

⚠️ **Second-order risk, worth flagging now:** the task is `soft_time_limit=100, time_limit=115`, and
a pass has already been measured at **74.2 s**. That is ~26 s of headroom before a soft kill, on a
duration that has grown with the corpus. `hard_kills_24h` is already **1**. Gotcha #131 territory.

**Priced fix, NOT taken this window** (Item 1 is scoped as a read, and the TTL governs the whole
typeahead surface, not just the warmer):
- **Raise the response TTL** above the real pass period (45 s → ≥ 120 s). One constant; but it
  changes staleness for every typeahead consumer, so it needs an explicit staleness answer.
- **Shorten the pass.** `seconds_max` is only **3.09 s** for a single query against a 72.2 s serial
  total — 40 queries run one at a time. Even 4-way concurrency puts a pass near 18 s, comfortably
  inside 45 s, and buys back the soft-limit headroom at the same time.
The second is the better fix and does not touch user-visible staleness. **Both belong in a queue
with the measurement above as the acceptance baseline.**

### Head wall clock: **ungradeable as worded** (the -52 p50 case again)

Criterion: head p50 from **1,627.3 ms** toward **~244 ms**. Measured: **run 1 = 1,627.143 ms**,
**run 2 = 2,331.93 ms**.

Run 1 landing within 0.16 ms of the banked 1,627.3 is a **coincidence, and run 2 is the proof** —
7 minutes later the same statistic read 2,331.93. Had only run 1 been taken, that 0.16 ms would
have been extremely tempting to report as "the head is exactly unchanged", and it would have been
an artefact. It is recorded that way here deliberately.

The criterion is ungradeable for a structural reason, not a noise reason. The probe computes its
summary over `usable` pairs, and `usable = not pre_warmed`
(`probe_typeahead_segments.py:208`). **The p50 is conditioned on the request having been a miss, so
warming cannot move it toward 244 ms by construction** — warming *removes* rows from the population
rather than shifting the ones that remain. Whatever survives into the p50 is, by definition, a
query the warmer failed to warm; its cost is the cold cost.

This is the same class as the `-52` p50 "unchanged" that Fable ruled ungradeable-as-worded. The
number that carries the effect is the *count* of excluded pairs, exactly as the queue said
(*"Do not expect a smaller miss number — expect the miss to stop happening"*). **Recorded so this
criterion is not re-registered in this form a fourth time.**

### Segment pin: **HOLDS**, on all three runs

| segment | head run 1 | head run 2 | tail control | expected |
|---|---|---|---|---|
| `tls` | 144.6 ms | 146.5 ms | 154.9 ms | ~157 ms — **stable across all three** |
| `server` | 1,473.2 ms | 2,185.7 ms | 1,891.3 ms | the only mover |
| `dns` / `connect` / `transfer` | 0.01 / 0.25 / 0.22 | — | 0.01 / 0.28 / 0.25 | floor |

`largest_miss_cost_segment` = `server` with **`share_of_miss_cost` = 1.0** on all three runs. All
movement is in `server` and only in `server`; `tls` varies by 10 ms across three runs spanning the
warm and cold arms. The pin holds.

### Tail control: **the tail did NOT improve — endpoint-level residency stays UNSUPPORTED**

Disjoint never-warmed arm (`borussia`, `sacramento`, `eurovision`, `reykjavik`, `kilkenny`,
`wolverhampton`, `guadalajara`, `trondheim`), same instrument, same hour:

```
excluded_pre_warmed   0 of 24        <- the control is genuinely never-warmed
miss_cost_total  p50  1,703.2 ms     max 3,470.5 ms
miss_total_wall  p50  2,070.4 ms     max 3,711.8 ms
```

Against LAT-P057's cold-tail baseline of **p50 1,661 ms / mean 2,256 ms**: **unchanged, if anything
marginally worse.** The tail is exactly where it was before the warmer deployed.

**This is the decisive form of the question, and it answers it.** The tail control ran at 16:28
UTC — *interleaved between* the two head runs (16:26 and 16:33), on the same endpoint, in the same
minutes, through the same instrument. The head arm reached 7-of-8 pre-warmed in both of those runs
while the tail arm reached **0 of 24 in all three of its rounds**. The warmer's effect is
**strictly local to the queries it warms**; there is no endpoint-level page-residency spillover.

Note this also rules out the alternative reading of the head result. One could object that the head
arm only looks warm because the probe warms itself round-to-round. The tail arm runs the identical
3-round structure with the identical round spacing and reaches 0 of 24 — **so the probe does not
warm itself; the warmer warms the head.**

> **Verdict on the residency claim LAT-P056 withdrew: still unsupported, and now for the third
> time — but for the first time by DIRECT measurement rather than simulation.** LAT-P056's two
> simulations came back flat and inverted; this is a live A/B against a deployed warmer. The claim
> should not be re-opened on the strength of a fourth simulation.

**No halt.** The head arm did go pre-warmed, so the stated HALT condition is not met.

---

## 🔴 The armed null control MOVED — and it moved with **no code change at all**

This is the most consequential result of the window, and it is a finding about the instrument, not
about the product.

The 46-probe gold set was re-read on `3fce7867` (producer blob **`61de6598`** — byte-identical to
the one LAT-P055/P058 used, verified by `git rev-parse HEAD:<path>`; 46/46 fetched, fidelity
`exact`).

| | v3820 / `cabc791a` (LAT-P058) | v `3fce7867` (this window) |
|---|---|---|
| pass | 39 | **41** |
| fail | 5 | **3** |
| xfail | 2 | **1** |
| xpass | 0 | **1** |
| regression | 0 | **0** |
| **MRR** | 0.8913043478260869 | **0.9347826086956522** |
| measured / fidelity | 46/46, `exact` | 46/46, `exact` |

**3 of 46 dispositions changed. Ruling 050 says any movement HALTS, so this is reported as a HALT
condition met** — even though every one of the three moved in the *improving* direction with
`regression = 0`.

### The three, and what actually caused them

| probe | was | now | old top entity | its status **today** |
|---|---|---|---|---|
| `search-gold-fed-001` | xfail (`ENTITY_NOT_TOP`) | **xpass** | `market:58808319` — *"FedEx St. Jude Championship Winner"* | **resolved** |
| `search-gold-hurricane-001` | fail (`ENTITY_NOT_TOP`) | **pass** | `market:338` — *"Stanley Cup® Winner: Vegas Golden Knights vs Carolina **Hurricanes**"* | **resolved** |
| `search-gold-president-001` | fail (`ENTITY_NOT_TOP`) | **pass** | `event:15191951` | **closed**, `completed_at` **2026-08-15 08:12 UTC** |

In all three cases the new top entity is the correct one and is **`open`**: *"Who will be confirmed
as Fed Chair?"*, *"Hurricane Bertha category?"*, *"Presidential Election Winner 2028"*.

**The ranking did not improve. The distractors resolved.** Every one of the three old tops was a
lexical false friend — golf's *"**Fed**Ex"* beating the Fed Chair market, hockey's *"Carolina
**Hurricane**s"* beating the hurricane market — and each has left the eligible pool since the
previous read. `event:15191951` can be dated precisely: it closed on **2026-08-15**, *between* the
two reads.

### Why this matters more than the two probes

**A null control that can move on its own is not a null control.** Had this read been taken without
the corpus check, the honest-looking conclusion available from the numbers alone was *"+2 passes,
MRR +0.0435, zero regressions"* — a clean win to bank, attributable to whatever shipped most
recently. It would have been wrong, and it would have been wrong in the **flattering** direction,
which is the direction nobody re-audits.

This is the *"specimens pinned to live markets expire"* hazard the queue carries — **occurrence
four in this program**, after `tour de france` (LAT-P045), and the first in which the expiry made
the numbers look *better* rather than breaking them.

The consequence is concrete: **the gold set's absolute numbers are not comparable across time
unless the eligible corpus is held fixed.** `39/44` and `41/44` were produced by the same code
against different worlds. Ruling 050's armed control assumes movement implies a change in the
system under test; that assumption is now measurably false in both directions.

> **RULING NEEDED (not self-issued — proposing, per the lane's authority).** Either the gold probes
> must pin to entities that cannot resolve, or every gold read must carry a corpus-delta line
> (*which expected/distractor entities changed eligibility since the comparison read*) before its
> dispositions may be compared. Without one of those, "0 of 46 changed" and "3 of 46 changed" are
> both uninterpretable. Filed to `RULINGS-NEEDED.md`; next free number is **070**, unclaimed by
> this window.

**No halt is called on LAT-P058's account**, because LAT-P058's change is not deployed and cannot
be the cause; the cause is established above and is exogenous. But the movement is real and is
reported as movement.

---

## Item 2 — #1881's unaccent index: **DOES NOT RUN**, and the conditional is why

The queue gated this item explicitly: *"conditional on Item 0's third row. If read volume did NOT
fall, adding 579 MB of index makes the tail worse and the item does not run."*

**Read volume did not fall.** The golf query is unchanged and slightly worse (516.7 MB/call, up
from 492.5); the flag is off; branch B is unindexed. Pool turnover is not improved, so the premise
for affording another **579 MB of trigram index against a 1 GiB `shared_buffers`** is absent.

**The item does not run.** This is the conditional working, not a deferral: the probes shipped in
LAT-P058 (`diacritic_folding`, three canaries, one per direction) are in place and will grade it
whenever the precondition is actually met.

---

## Item 3 — evictor #2's premise-check: the premise **SURVIVES**, and it is bigger than ranked

Two windows running, a banked candidate's mechanism has been wrong on inspection (LAT-P057's
`selectinload`, LAT-P058's "`llm_sport_category` has a btree"). The queue therefore said: assume
this one is wrong too until it survives a plan read.

**It survives.** And the ranking understated it.

### The statement

`backend/app/tasks/polymarket.py:1305`, inside **`_process_event_batch`** — so it fires once per
event *batch*, not once per poll:

```sql
UPDATE futures_markets sub
   SET event_id = parent.event_id
  FROM futures_markets parent
 WHERE sub.group_type = 'polymarket_sub_market'
   AND sub.event_id IS NULL
   AND sub.group_id IS NOT NULL
   AND parent.source = 'polymarket'
   AND parent.group_type = 'polymarket_event'
   AND parent.group_id = sub.group_id
   AND parent.event_id IS NOT NULL
```

### It is the largest cumulative physical-read consumer in the database

`queryid -749027317737976872`:

| | measured |
|---|---|
| calls | **67,537** |
| mean | 1,417.4 ms |
| per call | **241.0 MB** |
| **cumulative `shared_blks_read`** | **15,897.1 GB** |

For scale, the golf `OR` this program has been calling "the database's largest query" sits at
**4,549.0 GB** cumulative — the evictor is **3.5×** it.

> ⚠️ **Cumulative totals are NOT a ranking, and this pair is the proof.** `pg_stat_statements` is at
> its 5,000-entry cap and evicting, so each entry's counters cover a *different, unknown* window.
> `stats_reset` is **63.88 days** ago, but the golf entry holds only 9,016 calls against a
> ~1,110/day rate — i.e. its counters span roughly **8 days**, not 64. Comparing its total to the
> evictor's ~56-day total is comparing two different durations, and it inverts the answer.
>
> **Measured over this window's fixed 22.6-minute interval, the ranking is the other way round:**
>
> | | cumulative total | measured rate, this interval |
> |---|---|---|
> | golf `OR` | 4,549 GB (looks 3.5× *smaller*) | **427.6 GB/day — #1** |
> | evictor #2 | 15,897 GB (looks 3.5× *larger*) | **0.0 GB/day — it did not run** |
>
> The evictor read **zero** in the interval because it is **bursty**: it fires inside Polymarket
> poll batches, not continuously. Its ~1,205 calls/day are concentrated into those windows, so both
> "15.9 TB, the biggest in the database" and "0 GB/day" are true statements about it, and neither is
> usable alone. **LAT-P057 ranked golf first on a rate basis and was right to.** Quote a window with
> every number here, always. Raw delta: `lat-p059-pgstat-delta.json`.

### The plan — the mechanism, confirmed

```
Nested Loop                                        cost=202,003.24  rows=133,008
  -> Seq Scan on futures_markets  (the `sub` side) cost=127,864.28  rows=225,009
       Filter: event_id IS NULL AND group_id IS NOT NULL
               AND group_type = 'polymarket_sub_market'
  -> Memoize
       -> Index Scan using ix_futures_markets_group_id   cost=1.34  rows=1
            Filter: event_id IS NOT NULL AND source = 'polymarket'
                    AND group_type = 'polymarket_event'
```

**The parent side is already solved** — memoized index scan, cost 1.34. The entire defect is the
`sub` side: a **full sequential scan of the same 977 MB heap the golf query scans**, at the very
same cost node (`127,864.28`), executed once per batch, forever.

### The number that makes it a defect rather than a cost

| | measured |
|---|---|
| rows the Seq Scan examines every call | **213,215** |
| linked parents available to match against | 18,540 |
| **rows the statement would actually update** | **0** |

**Zero.** The steady state is that the poll links new sub-markets promptly, so the backlog is
drained; what remains is a permanent population of ~213,215 sub-markets whose parents are not
linked and never will be by this statement. They are re-scanned every batch, at 241 MB, to update
nothing.

Stated carefully, because "zero right now" is one reading and not the general claim:
**the statement's cost is completely decoupled from its yield.** Whether it links 0 rows or 500, it
pays the same full-heap scan of 213,215 candidates. This is gotcha #53's shape — the run that
recovers nothing is indistinguishable from the run with nothing to do — and gotcha #41's shape, a
sweep whose ordering can never reach what it is for.

### Priced, not taken

Per the queue, this item is a **premise-check only**; the fix is not in scope and is not attempted.
Two candidates, for whoever stages it:

- **A — DDL only, zero semantic change.** A partial index on the `sub` side, e.g.
  `(group_id) WHERE group_type='polymarket_sub_market' AND event_id IS NULL AND group_id IS NOT NULL`.
  ~213,215 rows ≈ 8–10 MB. Same Integrator-runbook pattern as LAT-P058, `CONCURRENTLY`, never a
  migration (gotcha #31). ⚠️ Its predicate contains `event_id IS NULL`, a column this very statement
  mutates, so rows churn out of the index as they link — the write cost needs pricing before it is
  recommended, not after.
- **B — bound the statement, a code change.** `_process_event_batch` already knows exactly which
  `group_id`s it just wrote; passing them turns a full-table sweep into a handful of indexed
  lookups. **This changes semantics** — it would stop catching subs whose parent is linked in a
  *later* batch — so it needs its own queue, a test, and a deliberate answer to that case. It is
  not a drive-by.

**Recommendation: stage A and B together as one queue**, because A is the safe immediate relief and
B is the actual fix, and choosing between them requires the write-cost number A does not have yet.

---

## Item 4 — cadence↔TTL hygiene: **NOT TAKEN**

The queue's precondition was *"only if the beat file is already open"*. It was not opened this
window. `beat_schedule_change: false`. Unchanged and still available: `precompute-admin-link-rate`
and `precompute-admin-matured-linkage` at `*/10`, `precompute-admin-audit-all` at `*/15`, all
caching `ex=3600` — six recomputes per cache lifetime, ~20 GB/day (0.7%). **Hygiene, not a fix.**

---

## Gates

| gate | result |
|---|---|
| **Full backend suite** | ✅ **15,282 passed, 62 skipped, 3 xfailed, 0 failed** in 670.80 s. `PYTEST_EXIT_CODE=0`, un-piped, exit code written into `/tmp/lat059_pytest.log` and read from there (gotcha #54). |
| Frontend build / typecheck / jest | **NOT RUN — named explicitly.** No frontend file was touched this window; the diff is `docs/audits/latency/**` only. |
| `xcodebuild` | **NOT RUN — named explicitly.** No native file touched. |
| CI `search-recall` count | **NOT RE-READ this window.** LAT-P058 settled it at **29** on master run `31850374998` / `cabc791a` and cited it on #993; nothing in this window's diff can move it. |

**Ruling 065 SPLIT declarations — partials, each with its addressee:**

1. **Item 0 is a SPLIT.** Graded: nothing. Owed to: **the Integrator**, who holds the DDL half, and
   whose §5.3 gate is corrected in this branch. The prediction remains registered and ungraded.
2. **Item 1's primary criterion is a SPLIT.** The flip was measured (0 → 14 → 7 of 24) but the
   **≥ 20 of 24 threshold is unreachable with this warmer**, for the measured cadence/TTL reason.
   Owed to: **#1866**, as a re-specified criterion plus the cadence fix.
3. **Item 3 is a premise-check only, by queue scope.** The fix is priced, not taken. Owed to:
   **whoever stages the successor queue**; both options are written out above.

## What this window changed on disk

Documentation and captured evidence only. **No production code, no migration, no beat-schedule
entry, no config.**

- `docs/audits/latency/lat-p058-golf-index-spec.md` — §0b added; §5.3 and §5.4 corrected in place.
- `docs/audits/latency/lat-p059-findings.md` — this file.
- `docs/audits/latency/lat-p059-seg-{head,head-run2,tail}.json` — three segment captures.
- `docs/audits/latency/lat-p059-pgstat-{t0,delta}.json` — the fixed-interval read-rate evidence.
- `docs/audits/latency/capture-lat-p059-gold-read-v3fce7867.{results,graded}.json` + producer log.
