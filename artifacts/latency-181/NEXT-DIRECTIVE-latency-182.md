# latency/182 — take the reading, then move the grinders

Written by latency/181 at 2026-09-06 12:45am PT (07:45Z — PT = local `date` minus 3h, notice 24,
verified with `TZ=America/Los_Angeles date`). Staged, not consumed.

**PILLAR: DISCOVER.** **SHIP: the search box stops being cold 45% of the time** — the same ship as
178, 179, 180 and 181. 181 built the instrument. This queue is the first one that can act on a
number instead of a ranking.

## Read first

`artifacts/latency-181/REPORT-latency-181-a-third-of-the-queue-stops-being-invisible.md` and
`artifacts/latency-180/REPORT-latency-180-the-instrument-could-not-see-a-third-of-the-queue.md`.
Issues **#3466** (181's ship, the instrument), **#3399** (180's ship), **#3398** (the parent
measurement, CLAIMED by latency), **#3444** (label map), **#3440** (settled concepts), **#3364**
(`warm_search_head` silenced).

**Do not re-derive any of this:**

- Do NOT re-run the concurrency sweep. Do NOT touch `WARM_CONCURRENCY`, `REFRESH_AHEAD_SECONDS` or
  `RESPONSE_CACHE_TTL_S`. 178 settled all three.
- Do NOT implement priority queueing. 179 measured and refuted it.
- Do NOT move anything to `heavy` on the strength of the old figures. 180 measured it at **0.91x**
  against background's 0.84x *floor* — but see ITEM 1: both of those numbers came from the blind
  instrument and **`heavy` must be re-read on `queue_demand` before it is ruled out**.
- Do NOT rebuild the demand model. **`artifacts/latency-180/demand.py` is now superseded** by
  `queue_demand` on the adherence endpoint — one read, no label join, no `rate x mean`. Use the
  endpoint. Keep `demand.py` only as a cross-check if the two disagree, and if they do, read
  rule (vv) before believing either.
- Do NOT trust `pg_stat_statements` totals. Reset 5+ days ago; 135 of its top 200 statements are
  dead.

## State on arrival — CHECK BOTH OF THESE FIRST, they may have moved

🔴 **Two ships were staged for cert and neither had exact-sha CI green when 181 ended.** GitHub
Actions was backlogged; no CI run in the repo completed in a 20-minute span.

| ship | branch | sha | PR | cert |
|---|---|---|---|---|
| #3399 — 180's typeahead shed fix, rebased | `program/latency-245-the-search-box-stops-going-cold` | `9dc0fd0e` | #3441 | **CERT-2037 staged** |
| #3466 — LAT-P242, the instrument | `program/latency-246-the-queue-can-be-sized` | `9d2ffaff` | #3468 | **CERT-2038 staged** |

For each: read the ledger for a graded row, then require `completed/success` on the **exact sha**
(`gh api "repos/alexander-bain/bainluck/actions/runs?head_sha=$SHA"`, full 40 chars — an
abbreviation returns `[]` and reads as a STOP). **Absence of the row is a STOP, not a pass**
(notice 28). Then check no later ledger row names that cert after "supersedes" (notice 18).

⚠️ **#3399's history, so you do not re-litigate it.** CERT-2032 granted a token on `2a28a13f`
conditional on exact-sha CI, and that condition was unmeetable because #3456 had every branch cut
from master red on shard 2. #3456 is CLOSED (`18cbc206`). The branch was rebased, and CERT-2037 is a
**fresh grade, not a sha-swap** — the branch moved past the certed sha with real code
(`git diff abd532c0..9dc0fd0e -- backend/` is +58/−20), so the byte-identical-diff precedent does
**not** apply and was not claimed. Do not try to merge on CERT-2032.

## ITEM 0 — THE READING. This is the whole point of 181 and it is one GET.

**Blocked until #3466 is live**, and the counters need a window: they are 24h-windowed and empty at
deploy, so `wall_window_s` starts at 0 and every `worker_seconds_per_hour` is withheld until each
task has run at least once. **Give it long enough that the slow beats have fired** — the hourly and
6h ones are the multi-minute grinders, so a 20-minute read will systematically under-report exactly
the tasks this is for. Read `wall_window_s` per row and say what it was; do not quote a total whose
rows have windows shorter than the cadence of the tasks in them.

```
source ~/.claude/.env && curl -s -H "Authorization: Bearer $ADMIN_TOKEN" \
  "$BAINLUCK_API/api/admin/celery/schedule-adherence" | python3 -m json.tool
```

Then answer, in this order:

1. **`queue_demand.background.utilisation`.** Above 1.0 is proof of oversubscription and settles the
   question three queues have been arguing about. Below 1.0 is **not** proof of headroom — read
   `tasks_unpriced`, `tasks_split_across_queues` and the residuals before saying anything.
2. **Re-price `heavy` on the same field.** 180 ruled it out at 0.91x on the *blind* instrument. That
   number was computed without the 32 and is not evidence any more, in either direction.
3. **Reconcile `collapse_snapshots`.** 180 found it reading **0.00/hr on the delivery counter while
   being the largest occupant of the queue** (45.5% of `inspect` samples). One of those numbers is
   lying. It now has `deliveries` and `worker_seconds_per_hour` **on the same row**, so this is a
   read, not a measurement. It also has three beat entries — check whether it lands in
   `tasks_split_across_queues`, because if it does, its demand is real and attributed to nothing.
4. **`refresh_hub`.** Not a beat entry at all, and holding a background slot when 180 looked. It
   will not appear in `queue_demand` — that is the non-beat-dispatch residual working as documented,
   not a bug. Find what dispatches it and price it separately.

## ITEM 1 — THE SHIP: act on the total, not on the ranking

The two named candidates are unchanged, but **do not pick from the list before ITEM 0 gives you the
total**. 179's rule (tt) still holds — relieving one contributor in an oversubscribed queue
reallocates the wait — and 180 adds that a ranking from a partially-blind instrument can name the
wrong task entirely. That instrument is fixed; the reading has not been taken.

- **`turbo_collapse_futures`** — mean **942.7s**, in 36.4% of `inspect` samples. A 16-minute task on
  a 2-slot queue.
- **`collapse_snapshots`** — was unlabelled, in **45.5%** of samples. Now visible.

Both are collapse/compaction work with no reader waiting on them, which is the exact profile
`refresh_stale_futures_prices` had when it was pinned to `heavy`.

In order of preference:

1. **Make them cheaper.** Check both for 179's defect class FIRST — an `Index Scan` whose leading
   column is unconstrained is a full scan that reads like a seek, and the tells are `Total Cost` and
   `Shared Read Blocks`, **never `Node Type`**. A 942s task is a strong prior for a per-item loop.
   Costs nothing elsewhere; if it works it is the right answer.
2. **Cadence** — but ask 179's class question first. `tournament_price_refresh` did not need to run
   less often, it needed to stop costing 189s. Compaction genuinely may not need its cadence, and
   unlike a price refresh nothing user-facing reads it.
3. **A fourth queue, or `--concurrency=3` on background.** ⚠️ **SPENDING. OUT OF SCOPE without
   Alex.** `background`'s 2 slots are a MEMORY bound (2 × 200MB + ~100MB ≈ 512MB Standard-1X
   exactly), so this is a dyno purchase, not a config edit. If the measurement says it is the only
   answer, that is a YOUR-TURN entry with the number, in plain English (notice 19: no "cert", no
   jargon), not a change.

## ITEM 2 — the guard debt, oldest first

- **`TYPEAHEAD-SHED-RUNTIME-CACHE-CONTRACT` (CERT-2032's remaining follow-up).** The endpoint-level
  regression: a shed answer WRITES and the next request HITS; a full futures-stage timeout writes
  NOTHING. The grader proved both by hand against production; there is no test. **Why it is not done
  yet, so it is not rediscovered:** three test files drive `typeahead_search` directly
  (`test_typeahead_trending_cache_hit_2117`, `test_search_origin_channel_p118`,
  `test_typeahead_eval_calls_do_not_vote`) and **all three rely on a cache HIT returning before the
  first query**, so they pass `db=None`. This contract needs the MISS path — a fake `AsyncSession`
  surviving every stage of a 1,000-line function. `test_search_response_cache.py::_search` is the
  model. ⚠️ Its warning cost that file a red run: the debug flags' declared defaults are `Query(...)`
  marker objects, **TRUTHY outside FastAPI**, so pass every flag explicitly or the assertions are
  made against the uncached path.
- **`LAT-P240-PREDICATE-SEMANTICS-GUARD` is still owed.** 179's guard counts emitted writes against
  a permissive fake, which is not a semantic check. Production answered it empirically
  (outcomes-per-market 1.642 → 1.647 across the deploy) but that is evidence, not a guard.

## ITEM 3 — filed, not ours; coordinate, do not claim

- **#3444** — `label_map` is single-valued, so `poll_all_odds` is graded on a DataGolf sub-poll
  (3.3x over) and `discover_events` on a taxonomy enrichment (4.0x under). **LAT-P242 routes around
  it for capacity** (`queue_demand` is keyed by celery name and never touches the label map), so it
  no longer blocks the demand number — but it still distorts the *adherence verdicts*. The
  three-line `ast.walk` guard belongs in CI regardless. **`poll_all_odds` is the live lane's.**
- **#3364** — `warm_search_head`'s `expires: 20` against a queue whose wait is minutes discards
  **96.7%** of its fires. The constant's comment justifies 20s by comparing against the task's own
  wall (~4–8s) rather than the QUEUE WAIT; the reasoning is correct and its premise is false. The
  generalisation is worth writing into `_EXPIRING_WARMER_BEATS`: *the bound must be compared against
  delivery latency, not the task's own duration.* Filed, not ours.
- **#3440** — settled golf concepts, 426 wsec/hr, byte-identical output over 3–4 rebuilds. Small,
  safe, and now priceable against a real total.
- Seven `external_id ==` sites remain; none moved in the live `pg_stat_statements` delta.
  `admin_matching.py` is **D35/D39 — file, do not fix**, link #2693.
- **CERT-1988 stays PARKED.** Do not merge PR #3377, do not re-stage, do not rewrite its header.
  `PARKED-MEASUREMENTS.md:8917`.

## Explicitly NOT in scope

- **Spending** — no dyno resize, no concurrency purchase, without Alex and a number.
- `WARM_CONCURRENCY`, `REFRESH_AHEAD_SECONDS`, `RESPONSE_CACHE_TTL_S`, priority queueing.
- **The tsvector index** — Tier-1, integrator + Alex.
- **ITEM 4 of 178** (serving `red sox` its headline market) — recall, not latency; needs a stated
  recall argument and must not be bundled.
- Matching symptoms — D35, file under #2693, never fix.

## Rules carried forward

168 (a)–(g), 170 (b)–(e), 171 (b)–(e), 173 (f)–(i), 174 (j)–(m), 175 (n)–(x), 176 (y)–(dd),
177 (ee)–(kk), 178 (ll)–(oo), 179 (pp)–(uu), 180 (vv)–(aaa), **181 (bbb)–(fff)** all hold. The three
most likely to bite this queue:

**(vv)** An occupancy timeline reconstructed from per-task instrumentation reports UNINSTRUMENTED
work as IDLE. Before believing a resource is free, ask what fraction of its consumers the instrument
can see. **The caveat you write in one model does not travel to the next model built from the same
data.** — LAT-P242 removes the largest known blind spot but does not remove the rule: the residuals
are documented in the payload and they are still residuals.

**(ccc)** When the wrong answer and the plausible default are the same value, a test with a default
expectation is vacuous. Pin a NON-default expectation.

**(fff)** Signal-wired observability fails silently in two indistinguishable ways — never connected,
and connected-but-raising. Drive the REAL signal; calling the handler proves neither.

⚠️ Build on a FRESH branch off master. `program/latency-245-…` and `program/latency-246-…` are both
in flight; `program/latency-242-…` still holds the parked commits.

Idle rule: empty inbox → write the next directive from the charter; never stop, never end with a
question.
