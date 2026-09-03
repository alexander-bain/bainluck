# LIVE-047 — CERT-773: the two Redis writes become one

**PILLAR: TRUTH. SHIP:** a US Open match page whose chart is thin because a venue
refused it gets asked again, instead of the tier declaring itself permanently,
cleanly finished over the top of it — even when two triggers are inside the
drain at once.

**Subject:** `5b68aee99ad87d983c028c2cbeecc9879330b576` on
`live/035-whole-lifetime-charts`. **Repairs:** CERT-773 (the CERT-753 → 764 →
773 chain, whose three-strike stop was LIFTED by Fable-5 at 4:20pm PT 9/2 under
Alex's ruling that certs must not impede progress — standing notice 16).

---

## What CERT-773 found, and why it is the third of one class

> `_record_attempts` deletes the final retry from the Redis hash and only then
> increments the give-up counter. A second trigger can read between those two
> operations, observe `retry={}`, `gave_up=0`, and an end cursor, then persist
> clean `drained` after the first trigger correctly persisted
> `drained_with_failures`.

CERT-753 blocked the drain for reporting `drained` while match pages stayed thin.
CERT-764 found the same shape one layer down: settlement read the give-up count
*entering* the trigger instead of the one leaving it. CERT-773 found it a third
time, this time *between* two triggers. All three are one disease: **a verdict
derived from state read at the wrong moment.**

Alex's instruction was the one this lane had already written down in live-043 —
stop trying to make the two writes agree after the fact and make them one write,
plus a per-tier lock.

## The repair — four changes, deliberately redundant

| # | Change | What it removes |
|---|--------|-----------------|
| 1 | `_read_checkpoint` reads its four keys in ONE `MULTI/EXEC` | Four round trips can straddle a sibling's write. The state a trigger acts on is now one that existed, not one assembled from two. |
| 2 | `_record_attempts` writes the retry-hash delta and the give-up `INCRBY` in ONE `MULTI/EXEC` | The gap CERT-773 read in. `INCRBY` is queued last so its reply is still the persisted post-attempt total (CERT-764's clause is untouched). |
| 3 | `_mark_done` is MONOTONE **by construction** | `drained_with_failures` is a plain `SET` (upgrades always allowed); `drained` is a `SET NX` (it lands only where nothing terminal is). The wrong direction is not expressible. |
| 4 | A per-tier `SET NX EX` lock | The second trigger reports `locked_out` and writes **nothing** — no retry field, no counter, no cursor, no marker. |

Any one of 1–3 alone closes the cert's reproduction. 4 removes the wasted double
fetch that made the overlap reachable in the first place.

**Why 3 is not redundant with 4.** The lock has a TTL (`TIER_LOCK_TTL_SECONDS =
1800`), because a SIGKILLed Celery worker cannot run a `finally` and a tier shut
forever is worse than a tier occasionally double-visited. A pass that overruns
that TTL puts two writers back on one tier. Monotonicity lives in the WRITE, so
it survives that; a read-then-write guarded only by the lock would not.

**Why the lock fails OPEN.** With Redis unreachable there is no checkpoint to
read and no verdict to corrupt — every write is already swallowed. Refusing to
run would turn a Redis blip into a silently disabled drain, which is the worse
failure.

**`locked_out` is not terminal.** The route tells the operator to re-call until
the verdict is terminal, so overlap is the expected traffic pattern, not an
attack. A locked-out tier holds the whole verdict at `in_progress`, which means
"come back" — reading another trigger's in-flight work as finished would be
CERT-773's mistake wearing a different name.

---

## The grader's exact-head reproduction, re-run here

`backend/scripts/repro_cert773_race.py` drives the cert's reproduction and runs
**unchanged on either tree** — it imports nothing the pre-fix tree lacks, so the
two outputs are directly comparable. It touches no network, no database and no
real Redis.

🔴 **Why it is a script and not only a test.** Trigger B is a second Celery
*worker process*. No arrangement of coroutines inside one event loop can land B
between two Redis round trips of A — the loop only yields at an `await`, and
there is none between `hdel` and `incrby`. So B is modelled where the tearing
actually happens: at the Redis boundary. The fake calls B at every moment a
state becomes visible, which is exactly the set of moments another process could
read at, and it is the *complete* set rather than a hand-picked interleaving.

### Blocked subject `7d99b8f8` (rsync copy, `chart_backfill_thirty_day.py` reverted)

```
CERT-773 race reproduction
========================================================================
head under test : 7d99b8f8b24101bf9bf99d44402563375ac48d13  (rsync copy, source reverted)
start state     : retry={7007: 2} gave_up=0 done=None (cursor at tier end)

PHASE 1 — B settles as soon as it reads (A's write still in flight)
A: third failed fetch of event 7007 (retry budget exhausted)
  B reads  retry={}           gave_up=0 done=None                   -> settles 'drained'
A: _record_attempts -> owed={} gave_up_total=1
A: _settle_tier     -> 'drained_with_failures'
B's reads           : 2, of which TORN (retry={} gave_up=0 done=None): 1
B settled           : ['drained']
Redis command log   : hdel get get hgetall get set set incrby get get hgetall get set set
final Redis state   : gave_up=1  done='drained_with_failures'

PHASE 2 — the cert's ordering: B reads mid-write, A persists, B persists LAST
A: settled first    -> done='drained_with_failures'
  B reads  retry={}           gave_up=0 done=None                   -> settles 'drained'
final Redis state   : gave_up=1  done='drained'

VERDICT: REPRODUCED — a clean 'drained' was settled over an abandoned event.
         This is CERT-773's finding. The tier is permanently, cleanly finished
         and event 7007 stays thin behind it.
```

Phase 2 reproduces the cert's literal final state: **`gave_up=1` beside
`done='drained'`**.

### This subject `5b68aee9`

```
CERT-773 race reproduction
========================================================================
head under test : 5b68aee99ad87d983c028c2cbeecc9879330b576
start state     : retry={7007: 2} gave_up=0 done=None (cursor at tier end)

PHASE 1 — B settles as soon as it reads (A's write still in flight)
A: third failed fetch of event 7007 (retry budget exhausted)
  B reads  retry={}           gave_up=1 done=None                   -> settles 'drained_with_failures'
A: _record_attempts -> owed={} gave_up_total=1
A: _settle_tier     -> 'drained_with_failures'
B's reads           : 1, of which TORN (retry={} gave_up=0 done=None): 0
B settled           : ['drained_with_failures']
Redis command log   : hdel incrby get get hgetall get set set set set
final Redis state   : gave_up=1  done='drained_with_failures'

PHASE 2 — the cert's ordering: B reads mid-write, A persists, B persists LAST
A: settled first    -> done='drained_with_failures'
  B reads  retry={}           gave_up=1 done=None                   -> settles 'drained_with_failures'
final Redis state   : gave_up=1  done='drained_with_failures'

VERDICT: NOT REPRODUCED — no reader, at any moment and in either order,
         could settle a clean 'drained'. gave_up=1 stands beside done='drained_with_failures',
         which is the honest ending.
```

---

## Guards

`backend/tests/test_chart_backfill_one_writer_per_tier.py` — 23 tests.
**18 red against `7d99b8f8`, 5 green in both arms as controls.**

The load-bearing ones, and each fails on its own assertion rather than on a
missing symbol:

* `test_no_reader_ever_sees_the_retry_emptied_before_the_give_up_is_counted` —
  the finding stated as an invariant over EVERY state a reader could land on,
  not one interleaving. Control: `assert [Observed(...)] == []`.
* `test_a_sibling_reading_at_any_moment_of_the_write_never_settles_clean` — the
  reproduction, as a test. Control: `assert 'drained' not in ['drained']`.
* `test_the_retry_delete_and_the_give_up_increment_are_one_transaction` — the
  mechanism, because the invariant could also be satisfied by a lucky ordering
  and luck is not a repair. Control: `assert 0 == 1` transactions.
* `test_the_checkpoint_is_read_as_one_snapshot` — the read half, asserting every
  key is inside the block; one left outside re-opens the tear.
* `test_a_clean_finish_cannot_overwrite_a_failure_ending` — control:
  `a clean finish overwrote a failure ending — the abandoned event is lost`.

**Controls green in BOTH arms** (the ones that stop the repair collapsing into a
blanket `drained_with_failures`):

* `test_a_sibling_reading_a_tier_that_owes_nothing_still_settles_it_clean` — the
  rig must be *capable* of writing `drained`, or the reproduction above passes
  for no reason.
* `test_a_single_trigger_that_abandons_nobody_still_reports_drained`
* `test_a_pass_that_abandons_nobody_still_empties_the_hash`
* `test_an_unreadable_checkpoint_is_still_a_fresh_start`
* `test_a_dry_run_marks_nothing`

**Stated honestly:** `test_two_interleaved_triggers_end_with_failures_never_clean_drained`
is the shape the directive named, and it proves the LOCK (the second trigger
writes nothing; `gave_up == 1`, not 2). It does **not** exhibit the torn read and
cannot, for the event-loop reason above — its marker assertion is green against
the blocked subject. Its docstring says so. The torn read is proved by the
sibling test and the script.

**One fake, not three.** The three per-file Redis fakes become
`backend/tests/lib_tier_redis.py`, which models `MULTI/EXEC`, bytes-on-the-wire
hash fields, `SET NX` refusing with `None`, and `INCRBY`'s reply. A per-file fake
that published a transaction's commands one at a time would turn every
interleaving guard in that file green against a tree with no transaction in it —
which is precisely the way this guard class goes vacuous.

## Gates

| Gate | Result |
|------|--------|
| `pytest -k "chart or thirty_day or backfill"` | **645 passed** |
| `pytest -k "redis or admin_data_quality or task_verdict or tasks_wiring"` | **372 passed** |
| `pytest tests/test_startup.py` | **4 passed** |
| the three drain suites together | **75 passed** |
| `ruff check` on all four changed/new files | clean |

Per ruling D40 the full 26k suite is CI's job, not a pre-push local run.

## What is NOT claimed

* No production access, no write, no merge, no push to master.
* The acceptance criterion — Monfils **15293808** listing → final with both
  venues, and the bus's CHARTS needle moving from 116/241 — is **not** verified
  here. It needs the drain actually run against production, which is an
  attended/measurement action this lane does not take. It is the next step once
  the token is granted.
* The known Redis-eviction bound on the retry hash (module docstring) is
  unchanged and still stated rather than hidden: a shared 100MB LRU can drop the
  hash, the owed retries are forgotten, and the events stay thin-and-findable via
  the two steady-state rails and `reset=true`. Change 3 means an eviction can no
  longer *downgrade* an already-recorded failure ending, which is the half of
  that bound that was permanent.
