# LAT-P068 — the Option D trigram index: a runbook addressed to the INTEGRATOR

**Supersedes the `alex_action_required` block in `READY-latency-LAT-P067.md`.** That block named
Alex. It should have named the Integrator. This document is the corrected route, and the READY has
been re-pointed at it.

**Status:** NOT YET RUN. Blocked on `program/latency-60` merging (the table does not exist until the
migration ships).

---

## 0. Why this was re-pointed — the reasoning that produced "Alex" was sound and incomplete

`MIGRATION-SLOT-OPTION-D.md`'s "fifth thing" argues:

> *"`psql` / TCP 5432 egress is BLOCKED from an agent session. No lane, including this one, can run
> `CREATE INDEX CONCURRENTLY` itself. It is an **ALEX action**."*

Both sentences of the premise are true. The conclusion skips a path.

There are **three** ways to reach the database, not two:

| path | available to a lane? | available to the Integrator? |
|---|---|---|
| `psql` / `heroku pg:psql` over TCP 5432 | ❌ egress blocked | ❌ egress blocked |
| a `!`-prefixed command in an Alex session | ❌ | ❌ |
| **`heroku run:detached` — a one-off dyno inside Heroku's network** | ⚠️ not the lane's to run | ✅ **this is the standing path** |

The third row is not hypothetical. **`INT-071` built three `CREATE INDEX CONCURRENTLY` indexes on
`futures_markets` this way on 2026-08-15**, from the runbook at
`docs/audits/latency/lat-p058-golf-index-spec.md`, which was written at Fable's direction with the
routing stated explicitly:

> *"The integrator runs it as a one-off dyno op — not Alex, not a migration."*

So the standing order is **integrator-first**. `psql` being blocked rules out two paths and says
nothing about the one that has already worked. Alex is the escalation, not the default — and
escalating by default has a real cost: it parks a p1 on a human who has not been shown a blocker.

**Alex is asked only on a MEASURED block** — §5 defines exactly what counts as one.

---

## 1. Preconditions — check all four, abort on any

```bash
source ~/.claude/.env
```

1. **`program/latency-60` is merged and deployed.** `curl -s "$BAINLUCK_API/api/health"` returns a
   `commit` that has `7781ebb3` as an ancestor. Without the migration there is no table to index.
2. **The table exists and is populated.** The index is built AFTER the backfill, not before — a GIN
   built on an empty table then filled row-by-row is both slower to build overall and produces a
   more bloated index than one built once over the full heap.
   ```sql
   SELECT count(*) FROM typeahead_index;
   ```
   Expect **≈240,891**. Do not proceed under ~200k; the fill is incomplete (re-run the fill task).
3. **No INVALID stub from a previous attempt** (see §4 — this is the failure INT-071 hit):
   ```sql
   SELECT indexrelid::regclass AS idx, indisvalid, indisready
   FROM pg_index
   WHERE indrelid = 'typeahead_index'::regclass;
   ```
   Any row with `indisvalid = false` must be dropped (§4) before retrying.
4. **`backfill_winners` is not running.** This is specific to this build and it is the most likely
   cause of a failure here — see §2.

---

## 2. 🔴 The scheduling constraint, and it is this program's own finding

`CREATE INDEX CONCURRENTLY` waits — **twice** — for every transaction that could see the table to
finish. It does not care that `typeahead_index` is brand new and has no other writers: a long
transaction **anywhere in the database** holds the wait open.

**`backfill_winners` runs every 6 hours with a p50 of 13.7 minutes and a p90 of 14.0 minutes**
(LAT-P068 measured, n=32). `precompute_calibration_main` has a p90 of **1,149 s ≈ 19 minutes**.
Either one, if it holds a transaction open across the build, will stall `CONCURRENTLY` for its full
duration.

That interacts directly with the next section, because a wait that outlives `lock_timeout` does not
queue — it **fails**, and it fails expensively.

**So: check what is running first, and start the build in a quiet window.**

```bash
curl -s -H "Authorization: Bearer $ADMIN_TOKEN" "$BAINLUCK_API/api/admin/celery-debug" \
  | python3 -c 'import sys,json;d=json.load(sys.stdin);[print(t["name"],round(__import__("time").time()-t["time_start"]),"s") for v in d["active"].values() for t in v]'
```

Proceed when nothing long-running is active. `backfill_winners`' next fire is predictable from
`last_started_at` on `/api/admin/task-metrics?task=backfill_winners` plus 6 h.

---

## 3. The build

**`lock_timeout` is `60s`, and the 5s that looks more careful is the one that breaks it.**

INT-071 ran the LAT-P058 spec with `SET lock_timeout = '5s'` and left **all three indexes INVALID**.
The diagnosis was unambiguous because the sizes gave it away: every index had already reached its
**full final size**. The builds had *completed* and then died in `CONCURRENTLY`'s second wait phase.
Re-run byte-identically at `'60s'`, the same statements reached `indisvalid = true` in under a
minute. A short `lock_timeout` here does not protect production; it converts a slow success into a
permanent liability (§4).

```bash
heroku run:detached --size=standard-2x -a bainluck -- \
  python3 -c "
import os, psycopg2
conn = psycopg2.connect(os.environ['DATABASE_URL'], sslmode='require')
conn.autocommit = True   # CONCURRENTLY cannot run inside a transaction block
cur = conn.cursor()
cur.execute(\"SET lock_timeout = '60s'\")
cur.execute(\"SET statement_timeout = 0\")   # the build is allowed to take as long as it takes
cur.execute('''
  CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_typeahead_index_search_trgm
    ON typeahead_index USING gin (search_text gin_trgm_ops)
''')
print('CREATE returned')
"
```

Notes on each line, because each is a failure someone has already had:

- **`autocommit = True`** — `CREATE INDEX CONCURRENTLY` is rejected inside a transaction block, and
  psycopg2 opens one implicitly. Without this the statement errors immediately.
- **`statement_timeout = 0`** — the DB's default statement timeout would kill a long build. The
  *lock* wait is bounded by `lock_timeout`; the *build* must not be bounded at all.
- **`run:detached`** — a non-detached `heroku run` silently fails to execute in the sandbox
  (gotcha #48). **Never trust its stdout; verify with §4.**
- **`IF NOT EXISTS`** — makes a retry after a §4 cleanup safe.
- **Never in a migration or the release phase** — gotcha #31, the May 22 outage.

---

## 4. Verify — and this is not optional, because the failure is silent

`CREATE returned` on a detached dyno proves nothing (gotcha #53: the run produces the same empty
stdout whether it worked or not). **Ask the database.**

```sql
SELECT i.indexrelid::regclass       AS idx,
       i.indisvalid,
       i.indisready,
       pg_size_pretty(pg_relation_size(i.indexrelid)) AS size
FROM pg_index i
WHERE i.indrelid = 'typeahead_index'::regclass;
```

- **`indisvalid = true`** → done. Proceed to §6.
- **`indisvalid = false`** → the build died in a wait phase. **Do not leave it.** An INVALID index
  is never *read* but IS *maintained on every write*, so it is a permanent write tax that reports
  nothing to anybody. Clear it and retry from §1:
  ```sql
  DROP INDEX CONCURRENTLY ix_typeahead_index_search_trgm;
  ```
  (Also run via a one-off dyno, same `autocommit` requirement.)
- **no row at all** → the statement never executed. Check the dyno actually ran (gotcha #48) before
  concluding anything about the database.

---

## 5. When it becomes Alex's — the definition of a MEASURED block

Escalate to Alex **only** after this is true and written down:

> **Two** §3 attempts, each preceded by the §2 quiet-window check and each using
> `lock_timeout = '60s'`, have left `indisvalid = false`, **and** §4's cleanup has been run between
> them, **and** the `pg_stat_activity` read below has been captured during at least one attempt to
> name what held the wait open.

```sql
SELECT pid, state, wait_event_type, wait_event,
       now() - xact_start AS xact_age, left(query, 120) AS query
FROM pg_stat_activity
WHERE xact_start IS NOT NULL AND now() - xact_start > interval '1 minute'
ORDER BY xact_start;
```

That read is the whole point of the escalation bar: it converts "it didn't work" into "this
transaction blocked it", which is the only form in which the request is worth a human's time. An
escalation without it is a handoff of the diagnosis, not of the work.

**If it does become Alex's, the ask is one line** — everything above is already done:

```
alex_action_required: CREATE INDEX CONCURRENTLY (integrator path exhausted, evidence attached)
ddl: |
  SET lock_timeout = '60s';
  SET statement_timeout = 0;
  CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_typeahead_index_search_trgm
    ON typeahead_index USING gin (search_text gin_trgm_ops);
run_via: `!` prefix in an Alex session, or `heroku pg:psql -a bainluck`
```

---

## 6. The D3 measurement, which the next queue gates on

Take it **after** §4 reports `indisvalid = true`, not before — the sizing model is a claim about the
finished index.

```sql
SELECT pg_size_pretty(pg_relation_size('typeahead_index'))       AS heap,
       pg_size_pretty(pg_indexes_size('typeahead_index'))        AS indexes,
       pg_size_pretty(pg_total_relation_size('typeahead_index')) AS total,
       (SELECT count(*) FROM typeahead_index)                    AS rows;
```

**Registered expectation (ruling 050), carried unchanged from `READY-latency-LAT-P067.md`:**
240,891 rows → **~115 MB total** (~43 MB heap + ~19 MB btrees + ~53 MB GIN) against the 688.6 MB
trigram surface = **6.0×**. **D3 HALT is > 350 MB** — above that the sizing model is wrong and the
read path is not built until it is re-derived.

---

## 7. What this runbook does NOT authorise

The index only. **D1 (the read-path cutover) stays off**, and it is gated on D2's 46 gold probes
showing zero movement in `entity_top_1_rate` (0.9130434782608695) and MRR (0.9347826086956522) —
any movement HALTS, per the slot artifact. D4's staleness sentinel ships with the table.

Ruling 076's dated deletion obligation rides along: whichever arm loses is DELETED in the window the
measurement lands, not parked behind an off flag.
