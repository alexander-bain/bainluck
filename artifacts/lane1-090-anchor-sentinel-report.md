# lane1/090 — post-deploy check: the nightly anchor sentinel's first real run

Owed by lane1/082's own merge directive; routed by integrator/120. Read-only; nothing built.

**Status: PRE-RUN BASELINE BANKED. The beat has not fired yet.** Written 2026-09-04 03:20Z.
The first scheduled fire is 06:40 UTC Fri 2026-09-04, ~3h20m after this baseline. A watcher is
armed to read the ledger at 06:43Z; the outcome section below is filled in from that read.

---

## 0. It is live, and it is scheduled

| Fact | Evidence |
|---|---|
| `2e284a49` (lane1/082, CERT-845 GREEN) is on `origin/master` | `git merge-base --is-ancestor` → true |
| It is in the **deployed** build | deployed head is `0bbcc735` (`/api/health`); `2e284a49` is its ancestor |
| The beat is registered on the production scheduler | `/api/admin/celery/schedule-adherence` lists `app.tasks.anchor_schedule_sentinel`, `interval_s: 86400` |
| It has **never run** | that same row reads `reason: no_metric_label_recorded`, and `/api/admin/celery/task-metrics/anchor_schedule_sentinel` → `{"status": "no_data"}` |

`no_data` is the clean pre-run baseline: anything in that key after 06:40Z was written by this
beat's first fire, so the post-run reading is a proven delta and not a pre-existing row.

## 1. The channel — and the one that was NOT available

`heroku logs` is EPERM-blocked from this sandbox (`connect EPERM` on every logplex IP), so the
operator line `_summarize()` writes is not readable here, and logplex would evict it anyway.

The durable channel is the ledger. `_tracked_run` passes the task's **entire returned dict** to
`record_task_success`, which stores it as `last_result_summary`
(`backend/app/tasks/redis_state.py:1001`). That dict is the sweep state: `terminal`, `complete`,
`stopped_by`, `resumed_from`, `continuation`, `pages`, `examined`, `eligible`, `by_verdict`,
`moves`, `elapsed_seconds`, `filing`. So one read of
`/api/admin/celery/task-metrics/anchor_schedule_sentinel` answers all three of the directive's
questions except "did it file", which is checked against the board directly.

**Caveat to carry into the reading (gotcha #53 shape).** `anchor_schedule_sentinel` is not in
`task_verdict.ENFORCED_TASKS`, so `_tracked_run` classifies it `unknown` → recorded as a *success*
stamped `unverified`, whatever the sweep's own terminal was. The counter is therefore not the
verdict: an `authority_dark` or `partial` night will still increment `successes_24h`. The verdict
to read is `last_result_summary.terminal`, never the success count.

## 2. What the window holds tonight, measured before the run

```sql
SELECT count(*) FROM events
WHERE espn_id IS NOT NULL AND completed_at IS NULL
  AND status NOT IN ('completed','closed')
  AND commence_time >= now() - interval '1 day'
  AND commence_time <  now() + interval '120 days'
```
→ **673 rows** (38.8 ms). Tennis is excluded by the task on top of this, so the true eligible
count is ≤673. (`events` has no `sport_key` column, so the tennis cut cannot be applied in this
query; it is applied in the rail by sport key at fetch time.)

Against that, the two bounds:

* **page cap** — 12 pages × `DEFAULT_LIMIT` 100 = 1200 rows. **Not binding at 673.**
* **deadline** — 300s at the ~0.2s/row the module documents = ~135s for the whole window, so a
  complete sweep fits with roughly 2× headroom **on a good night**. The deadline is the binding
  bound, and it is the one with the upstream heavy tail behind it (lane1/082 measured the sibling
  endpoint's 3-group call at 19.3s and 2.0s minutes apart).

So the expected first-night terminal is `no_work` or `plan_only` (complete), with `partial` on a
slow-ESPN night as the legitimate second outcome. `authority_dark` on night one is a finding.

## 3. Does 06:40 fit the heavy queue

Nothing else contends. The daily heavy block is 07:05 / 07:10 / 07:25 / 07:32 / 07:36 / 07:40 /
07:45 / 07:50; the only other pre-07:00 heavy beat is Monday-only 06:20, and 2026-09-04 is a
Friday. That leaves **25 minutes clear** ahead of the 07:05 beat against a 300s inner deadline —
5× headroom. A run that overruns into 07:05 means the inner deadline did not hold, which is a
finding about the deadline, not about the slot.

---

## 4. OUTCOME OF THE 06:40Z RUN

*(pending — the beat has not fired at the time of writing)*
