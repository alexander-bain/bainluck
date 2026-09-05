# Release-Phase Migration Runbook

*What to do when a Heroku release fails on a migration, and how not to write the one that does.*

Written after #2782 (2026-09-02/03), where four releases — v4016, v4017, v4018, v4019 — failed
between 11:46pm and 12:38am with CI green and production sat on stale code for ~50 minutes. It
blocked **every** lane, not just the one that wrote the migration: `integrator/081`'s `d84f0938`
(CERT-797) and `live/048`'s `842e6167` (CERT-799/800) hit the identical failure.

Companion reading: `app/utils/migration_lock_order.py` (the rule), `app/utils/migration_lock_budget.py`
(the wait policy and the retry's safety argument), gotcha #31 (release timeout / index builds),
gotcha #158 (this whole class, in one line), #2724, #2741.

---

## 1. Before you write the migration

**Take the contended tables in the app's order.** The order is declared once, in
`LOCK_ORDER` (`backend/app/utils/migration_lock_order.py`), and enforced by
`backend/tests/test_migration_lock_order.py` over every file in `alembic/versions/`:

```
futures_markets  →  market_match_receipts  →  market_link_changes
```

Two parties taking two locks in two orders is the definition of a deadlock cycle. Live code holds
`futures_markets` and then writes the receipt (`match_receipts.verify_links_are_durable`, plus the
`FOR KEY SHARE` the receipt's own foreign key implies), so a migration must do the same. There is
a second reason the hottest table goes first: a migration's **opening** acquisition is taken while
it holds nothing, so it cannot be anyone's blocker.

If your migration needs two hot tables and cannot order them — a `CREATE TABLE … REFERENCES
futures_markets` locks both inside one statement, and you do not control the order within a
statement — take the parent explicitly first:

```python
op.execute("LOCK TABLE futures_markets IN ACCESS EXCLUSIVE MODE")
```

Or split the two tables into separate revisions, so no single transaction holds one while waiting
for the other.

**Know what is holding the table you are about to lock.** `futures_markets` is the worst case in
this schema: `match_prediction_markets` runs on the **heavy** queue every 15 minutes at 337s p50 /
699s p95, and `poll_kalshi_markets` at 320s p50, and both hold `ACCESS SHARE` on it for their whole
pass. There is no reliable natural gap. A migration that has to *wait* for `futures_markets` is
gambling; a migration that takes it first is not.

**Do not build a big index in the release phase**, and never `CREATE INDEX CONCURRENTLY` inside a
migration (gotcha #31 — Heroku's release timeout is ≈5 min, and `CONCURRENTLY` cannot run in a
transaction). Large indexes go via `psql`, out of band.

---

## 2. What the release phase already does for you

Armed automatically in `backend/alembic/env.py` (#2724, #2782):

| Guard | Value | Effect |
|---|---|---|
| `lock_timeout`, set as a libpq connect option | `ALEMBIC_LOCK_TIMEOUT_MS`, default 5000, clamped 1000–20000 | The `ALTER` aborts (`55P03`) instead of queueing. A pending `ACCESS EXCLUSIVE` blocks every later reader, so an aborted one is strictly better than a waiting one |
| Retry on contention | `ALEMBIC_LOCK_ATTEMPTS` default 4, `ALEMBIC_LOCK_BACKOFF_MS` default 2000 | A lock timeout **or a deadlock** (`40P01`) is retried, but only while `alembic_version` is unchanged and no pending script commits mid-flight |
| Release-phase budget | `RELEASE_PHASE_BUDGET_S = 120` | Attempts are dropped until the worst case fits. A policy that can never land is not a policy |

**The retry is survival, not a cure.** Against a contender that holds the table almost continuously,
four attempts is four coin flips. The log line names which contention it hit — `lock_timeout` means
a straggler and the next attempt may well win; `deadlock` means the migration takes its locks in the
wrong order and the fix is in the diff, not in the retry.

---

## 3. When a release fails anyway

### 3.1 Read the failure, and read it in the right place

```bash
heroku releases -a bainluck | head -10          # which version, and did it say "failed"
heroku releases:output vNNNN -a bainluck        # the release phase's own log
```

The four #2782 failures were **silent** at the `git push` — CI was green, and the release phase is
where it died. `heroku releases` is the only place that says so (see also #2741, where the Procfile
hid the exit code).

Signatures worth recognising:

| In the release output | What it is | What to do |
|---|---|---|
| `psycopg2.errors.LockNotAvailable` (`55P03`) on all attempts | The contender never let go | §3.2 — quiet the contender |
| `psycopg2.errors.DeadlockDetected` (`40P01`), naming two tables | A lock-order inversion — **your migration is wrong** | Fix the order (§1). Quiet the contender to land the pending slug, then ship the ordering fix |
| `Can't locate revision` | A migration file was deleted | Gotcha #8/#49 — restore the file; never delete an applied revision |
| Timeout at ≈5 min with an index build in the diff | Gotcha #31 | Move the index out of band |

### 3.2 The pause / release / scale-back sequence

This is what actually resolved #2782, and it changed **no certified code**. It quiets the contender
rather than trying to win a lock race against it.

```bash
# 1. Stop the heavy contenders. web, realtime, background and worker-ws stay UP —
#    the site keeps serving; only the long futures_markets passes stop.
heroku ps:scale scheduler=0 worker-heavy=0 -a bainluck

# 2. PROVE the table is free before releasing. Do not skip this and do not
#    substitute a sleep: a dyno that is shutting down still holds its locks.
source ~/.claude/.env && curl -s -X POST \
  -H "Authorization: Bearer $ADMIN_TOKEN" -H 'Content-Type: application/json' \
  -d '{"sql":"SELECT count(*) FROM pg_locks l JOIN pg_class c ON c.oid = l.relation WHERE c.relname = '\''futures_markets'\'' AND l.granted","limit":10}' \
  "$BAINLUCK_API/api/admin/db-query"
#    Expect 0. If not, wait and re-check — do not proceed on a non-zero count.

# 3. Release the pending slug (this is the step that was failing).
heroku releases:retry -a bainluck        # or re-push; either re-runs the release phase

# 4. Confirm it landed BEFORE restoring the contenders.
heroku releases -a bainluck | head -3

# 5. Scale back. This is not optional and it is not "later" — a scheduler left at
#    0 stops every polling task in the product.
heroku ps:scale scheduler=1 worker-heavy=1 -a bainluck
```

**Steps 1 and 5 are one action with a gap in the middle.** Write step 5 down before you run step 1.
The failure mode of this runbook is a lane that lands the release, declares victory, and leaves the
heavy queue at zero.

This sequence is **attended** — it takes production dynos down and needs Alex or the integrator. It
is not something a build lane runs on its own initiative.

### 3.3 The trap: a one-off dyno cannot apply a pending migration

`heroku run alembic upgrade heads` boots the **last successful release's** slug. That slug does not
contain the new revision, so it prints "already at head" and changes nothing. Four manual attempts
were spent on this during #2782 before it was spotted. Banked as gotcha #158(b).

The migration can only be applied by the release phase of the slug that carries it.

---

## 4. Considered and not built: quieting the queue automatically

#2782 asked whether the release phase should scale `worker-heavy` to 0 for the duration of the
migration and back afterwards. It is not built, deliberately:

- The release phase would need Platform API credentials with `ps:scale` rights, in an environment
  that currently holds only `DATABASE_URL`. That is a large new blast radius for a rare event.
- A release phase that fails *after* scaling down leaves the product with no heavy queue and no
  operator watching — the failure mode is worse than the one it fixes, and it fires on exactly the
  deploys that are already going badly.
- The ordering guard removes the cycle, and the retry covers the straggler. What remains is the
  narrow case in §3.2, which is rare enough to be worth a human.

Revisit if §3.2 is run more than a couple of times a quarter. Until then the ordering rule is the
cheap fix and this runbook is the expensive one.
