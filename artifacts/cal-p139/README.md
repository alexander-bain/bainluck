# CAL-P139 — the freeze cannot lift because a 24-hour fuse is already lit, and the curve counts 65% of its Polymarket baseball outcomes twice

Published number at session start and end: **1.88 pp, FLAT** (`headline_pass: true`,
CI `[0.86, 1.97]`). The payload DID move — `2026-08-30T00:35:55Z` → `01:35:22Z`,
925,440 → 925,446 outcomes — and this session counted the beats **in the ring**,
which is CAL-P138's lesson 27 and the reason the count is trustworthy this time.

**The gates opened far enough to run, and I ran them.** The freeze score reached
**3/24** at the v3921 baseline and **3/3 WINDOW_NOT_FULL** at the post-repair
baseline, which is the ≥3-post-repair-beats trigger the queue names. The
falsifier re-measure, the amended N-of-M window check and the re-baseline
artifact are all discharged in §1–§3. The freeze itself is **NOT lifted** and I
took no exception.

---

## 0. The board, unchanged

| | |
|---|---|
| headline MCE (closing line) | **1.88 pp**, target 2.0, `headline_pass: true` |
| NEEDLE | **30/49** cells at bar |
| queued cells | 19, **460,827** excess outcomes |
| self-check | `ok: true` — 34/34 by_category, 7/7 by_source reproduced exactly |
| `availability` | `stale` |
| `producer_beats_missed` | 0 |

Seven commits still unmerged at hand-off: `edc1ee74`, `fef05751`, `61620737`,
`3ee41a21`, `bdfce8ac`, `b1f9635c`, `9f6ee178`. Master did **not** move during
this session — `64b7a034` at both ends. Branch is still `held_on_cert` with no
cert staged in `CERT-QUEUE.md`; that is `alex-inbox/integrator-006` and it is
not mine.

---

## 1. 🔴 THE REPAIR WAS ALEX'S ONE-OFF, AND CALIBRATION-907 SAID IT COULD NOT HAVE WORKED

The previous three queues have been passing along "the producer recovered on its
own, and it was **not** `fef05751`". Half right. It was not `fef05751` — that
commit is unmerged, therefore undeployed. It was also not spontaneous.

`bainluck:bookmaker_calibration` is written with a fixed **24-hour TTL** and
nothing else writes it. Read twice, bracketed to the second:

```
2026-08-30T01:50:01Z → 01:50:02Z    TTL 67,058 s
  ⇒ EXPIRES 2026-08-30T20:27:39Z ±1s
  ⇒ WRITTEN 2026-08-29T20:27:39Z ±1s   (= 1:27:39pm PT)
```

Alex started the detached one-off at **~1:10pm PT**. It finished **17m39s
later**. That is the whole explanation of the outage in one number: the Celery
soft limit is **600 s** and the query needs **~1,060 s**, so it can only ever
finish outside Celery. Corroborating, from `task-metrics`:

* the last in-budget run was 08-28 00:56:47→01:05:52, **544.6 s** — and its key
  expired 24 h later at 01:05:52Z on 08-29, which is when the outage starts;
* every run since pins at **600.4 s** — nine consecutive;
* `last_success_at` is still `2026-08-28T01:05:52Z`, `consecutive_failures: 8`,
  `health: critical`. The one-off bypasses `_tracked_run`, so a success through
  it leaves the metrics untouched — which is exactly the state observed;
* no scheduled run was in flight at 20:27:39Z (they run at ~:57, every 6 h);
* the contents are fresh, not the old copy: `odds_api_bookmaker` published
  **96,748** outcomes today against **96,026** in the pre-outage curve.

**Lesson 24 again — read the writer before you trust the column.** 907 reasoned
from the query's shape ("same unbounded query, so it cannot have finished") and
never checked the artifact the run would have left. The TTL is that artifact.

## 2. The falsifier re-measure — do not revert `3200b840`

The ring is the natural experiment and it needs no interpretation:

| | |
|---|---|
| key expired | 2026-08-29T01:05:52Z |
| last clean beat before it | **00:36:48Z** — 29 min earlier |
| first gate refusal | **01:38:36Z** — 33 min later |
| gate refusals in the whole ring | **12, every one inside the outage window** |
| last refusal ever recorded | **20:21:15Z — six minutes before the key was rewritten** |
| key rewritten | 20:27:39Z |
| refusals since | **zero** |
| beats since that reached a terminal decision | **3 of 3 published clean** |

The two misses in between are `cancelled`, at **16 s** and **17 s** after
releases v3940 and v3941. Deploys killing in-flight builds.

Publish rate among beats that reached a decision post-repair: **3/3 = 1.00**,
against the **0.472** the condition was written to exclude. The failure class
`3200b840` repaired (sports `read:events` cancelled) has fired **once** since it
deployed and **zero times in the 29 hours since**.

**Verdict: the fix is not indicted. Every `NOT_MET` measured between
2026-08-29T01:38Z and 20:21Z is a measurement of a missing Redis key.**

## 3. The amended N-of-M window check — and why it is capped at 21/24

```
--baseline-at 2026-08-28T18:55:19Z (v3921)   3/24 clean   NOT_MET
--baseline-at 2026-08-29T23:35:53Z (repair)  3/3 clean    WINDOW_NOT_FULL  (reachable 24/24)
no-regression half: self_check.ok true, headline_pass true
```

`reachable 24/24` is the script being honest about what it can see, and it is
wrong about the world, because the script does not know about the TTL. The
window is 24 hourly beats from `23:35:53Z` on 08-29, so beat #24 publishes
~`22:35Z` on 08-30. The key dies at `20:27:39Z`.

| beat | publishes | run starts | outcome |
|---|---|---|---|
| #21 | 19:35Z | 19:15Z | can be clean |
| #22 | 20:35Z | 20:15Z | **race** — the key is read in the *diagnostics* phase, which runs last |
| #23 | 21:35Z | 21:15Z | refuses |
| #24 | 22:35Z | 22:15Z | refuses |

Two misses are allowed and #23/#24 spend both. #22 almost certainly loses the
race, so **21/24 — `NOT_MET`, guaranteed**. The optimistic branch is exactly
22/24 with zero margin, requiring every one of beats #4–#22 to be clean on a day
that has already seen nine releases and three deploy-killed beats.

**The lift condition is 24 hours long and 10% of the curve is on a 24-hour fuse
with a dead writer.** Staged as `alex-inbox/calibration-910` with the one command
that resets it and a deadline of **1:27pm PT Sunday**.

---

## 4. 🔴🔴 THE CURVE COUNTS OUTCOMES TWICE, AND IT IS RULING 125 WITH THE SIGN REVERSED

This was found by accident while starting **CAL-P138-1** (which leg did the curve
publish?). That item needs a fold keyed on the OUTCOME rather than the market,
and the first 6,100-id probe of `polymarket/baseball` returned **96 distinct
outcomes as 192 rows — every one of them exactly twice**.

### The mechanism

`vm_stats` groups by **five** columns:

```sql
GROUP BY vm.vm_id, vm.source, vm.category, vm.is_grouped, vm.mutually_exclusive
```

`ranked_outcomes` joins it back on **two**:

```sql
JOIN clean_vms cv ON cv.vm_id = vm.vm_id AND cv.source = vm.source
```

When one virtual market's members disagree on `category`, `is_grouped` or
`mutually_exclusive`, `clean_vms` holds one row per variant and the join emits
**every outcome of that virtual market once per variant**.

**This is ruling 125's clause with the sign reversed.** 125 says a join whose key
is coarser than the identity of the rows it can *eliminate* silently picks a
winner across a dimension nobody declared. Here the key is coarser than the
identity of the rows it can *multiply*, three CTEs earlier in the same chain.

🔴 **And the reason it survived is that the producer's own comment misdescribes
it.** Both at `precompute_calibration.py:2318` and in ruling 125's text,
`vm_stats` is cited as a model citizen — *"every neighbouring aggregate is
source-scoped deliberately — `vm_stats` GROUPs BY `(vm_id, source)`, `clean_vms`
JOINs on both"*. It groups by five. The audit that found the deleting half read
the first two columns of the GROUP BY and stopped. **Lesson: a comment that
certifies a neighbour is not evidence about the neighbour.**

### It is not an edge case — raw-table census, no CTE chain involved

`futures_markets`, `status='resolved'`, groups with ≥3 markets, hash-chunked on
`md5(group_id)` at 64 chunks, **zero timeouts**:

```
groups 18,378   with mixed identity 18,363   (99.9%)
markets 259,925  in mixed groups   259,859   (100.0%)
   of which mixed on CATEGORY: 1,424 groups; the rest are mixed on mutually_exclusive
```

The driver is the ordinary Polymarket event shape. Specimen, straight off
`futures_markets`:

```
polymarket:745808   field     mutually_exclusive=false    1 market
polymarket:745808   quantity  mutually_exclusive=true    36 markets
```

One `field` market beside 36 `quantity` markets ⇒ two `clean_vms` rows
(`eligible` 29 and 52) ⇒ every outcome in the event published twice.

### What it does to the published cell

`artifacts/cal-p139/outcome-grain-fold.py`, the producer's own chain through
`calibration_cell_exact`, curve `2026-08-30T01:35:22Z`, population `q268`:

RESULTS_TABLE_PLACEHOLDER

⚠️ **These are FLOORS.** `calibration_cell_exact` restricts `market_info` to an id
range, which can drop a group below the `>= 3` threshold and collapse its `vm_id`
to the per-market `m:` arm — and a single-market vm has one identity and
therefore no duplication. A chunked replica loses duplicates it should have; it
cannot invent them.

### Why this matters more than the ECE move

The ECE move is the small half. The large half is **`n`**:

1. **Every σ this lane has computed is inflated.** Lesson 4 already says a σ is a
   claim about independent observations, not about rows — and a row published
   twice is emphatically not two observations. σ scales ~√n, so a 1.65× inflation
   is a **1.28× overstatement of σ** on the affected cells. The five banked rule
   designs are all σ-gated.
2. **The excess-outcomes ranking is inflated**, unevenly — the conveyor picks
   cells "biggest excess first" off numbers that over-count grouped-ladder cells
   ~2× and singleton-market cells not at all.
3. **`total_outcomes` (925,446) is not a count of outcomes.** It is a count of
   join products.
4. The headline is outcome-weighted, so a 2× over-weight on the grouped-ladder
   population is a systematic re-weighting of the published number.

**I am not proposing a fix.** The join is in `precompute_calibration.py`, which
ruling 009 freezes, and one extra conjunct on that join is precisely the kind of
change the ruling exists to gate. Staged for Alex as
`alex-inbox/calibration-911`.

---

## 5. What this queue did NOT do

* **The conveyor's step 1 still has no legal answer — a sixth session.** Every
  top-19 cell is banked, refused, held or off. `alex-inbox/calibration-908` is
  still unanswered. I did not invent a cell to satisfy it.
* **CAL-P138-1 is only half-answered.** The fold now carries `outcome_id`,
  `outcome_name` and `rn_distance_rank`, which is everything the leg question
  needs — but the duplication finding took the session's remaining budget, and
  reading the leg distribution off a population that double-counts 65% of itself
  would have been lesson 14 (check the two halves are about the same population)
  in its purest form. **The leg answer must wait for the dedup.**
* No exclusion rule was designed. §4 is a repair item, not a calibration ship.
* Nothing shipped. `git show --stat <sha> -- backend frontend` is empty for this
  session's commit; artifacts only.

## 6. Gate

`pytest -k "calibration or bookmaker or ladder"` — unchanged from CAL-P136/137/138,
as it must be with zero backend files changed. Recorded in
`artifacts/cal-p139/gate.txt`.

## Evidence

| file | what |
|---|---|
| `payload.json`, `scorecard.txt` | the published curve at `01:35:22Z` and the board |
| `freeze-score-v3921-baseline.json`, `freeze-score-repair-baseline.json` | §3 |
| `ring-post-baseline.json` | all 168 ring observations with outcomes — §2 |
| `redis-census.json`, `redis-census2.json` | the two bracketed TTL reads — §1 |
| `group-identity-census.txt` | the 64-chunk raw-table census — §4 |
| `outcome-grain-fold.py`, `outcomegrain-*.json`, `outcome-grain.json` | §4's folds |
| `outcome-grain-baseball.log`, `outcome-grain-2.log` | sweep transcripts |
