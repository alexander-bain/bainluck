# latency/181 — a third of the queue stops being invisible to the instrument that sizes it

**PILLAR: DISCOVER. SHIP: the search box stops being cold 45% of the time** — the same ship as 178,
179 and 180. This queue built the prerequisite that ITEM 2's topology decision has been blocked on.

Written 2026-09-06 12:42am PT (07:42Z — PT = local `date` minus 3h, notice 24, verified with
`TZ=America/Los_Angeles date`).

---

## What this queue did

Two things, in order of the directive's own priority.

### 1. Unblocked and re-staged 180's ship (was CERTED GREEN, could not merge)

CERT-2032 was GREEN with the token granted on `2a28a13f`, **conditional on exact-SHA CI** — and that
condition was unmeetable. Exact-sha CI was RED on shard 2 for a reason that had nothing to do with
the ship: `test_combat_card_rollover_1712.py` anchored on a UFC card dated the day before, which
took **every branch cut from master red at once**. That is #3456.

**#3456 is now CLOSED**, fixed on master by `18cbc206`. So:

- Rebased `program/latency-245-…` onto current master. Clean; ship diff vs master unchanged at
  13 files / 1,747 insertions.
- Re-ran the ship's focused gates at the rebased head: **89/89**, including the three files that
  drive `typeahead_search` directly.
- Pushed `9dc0fd0e`; PR #3441 is MERGEABLE.
- **Staged CERT-2037** for a fresh grade.

🔴 **A re-stage was required, and the byte-identical-diff shortcut was NOT available.** The
established precedent (`r_rebasing_a_certified_sha_breaks_the_token_grep`) is: prove the rebase
preserved the diff, then write both shas. That argument does not apply here and was not made.
`git diff abd532c0..9dc0fd0e -- backend/` is **+58/−20** across `app/routes/events.py` and the
ship's own test file: the branch moved past the certed sha with **real code** (`d226e9be`, the
CERT-2032 follow-up that took the shed booleans out of the millisecond map). A token covers the
bytes it was granted on, and these are not those bytes.

### 2. THE PREREQUISITE (ITEM 1): the 32 unlabelled beats now have a duration

`#3466`, `LAT-P242`, PR #3468, **CERT-2038 staged**, branch `program/latency-246-the-queue-can-be-sized`
off master.

`_tracked_run` is called BY THE TASK BODY. 32 of the 110 `background` beat entries never call it, so
they carried **no duration under any label**, and every capacity model built on the label-keyed
metrics scored them at ZERO worker-seconds.

The fix is a third counter in the `task_prerun`/`task_postrun` family: wall time **summed per celery
task name**, written with no cooperation from the body, keyed exactly like the `attempts`/`terminals`
pair. Plus, on `GET /api/admin/celery/schedule-adherence`: `wall_ms_24h`, `wall_window_s`,
`worker_seconds_per_hour` and `queues` on **every** entry (graded *and* unmapped — the 32 are
unmapped by definition), and a `queue_demand` block totalling worker-seconds/hour per queue against
`slots × 3600`.

**A SUM, not `rate × mean`.** This is the part that matters and it is why the directive's ITEM 1
should not be executed as originally framed. `demand.py` computes `deliveries/window × 3600 × MEAN`,
and its own docstring names four traps it had to survive — the label join, the denominator, the
straddle, and bimodality. All four are properties of *multiplying two estimates drawn from two
different windows and joined through a lossy map*. A wall-time sum over a window carried in the
same key has **none of them**: it is not joined, not averaged, and not sampled.

**It discloses what it cannot price, in fields rather than comments:** `tasks_unpriced` with their
names; `tasks_split_across_queues`; and the hard-kill, in-flight and non-beat-dispatched residuals
named in the writer's docstring. `utilisation > 1.0` is proof of oversubscription; **below 1.0 is
NOT proof of headroom**, and the payload says so.

Gates: 38 new tests, **12/12 mutants killed**, 573 green across every consumer of the touched
symbols (files chosen by grepping the SYMBOLS touched, not a `-k` name band).

---

## Two bugs this queue wrote and caught, both now guarded

Recording these because both are cheap to write again.

**1. The beat schedule is keyed by ENTRY name, not task name.** The first version of the queue
attribution did `beat_schedule.get(full_name)`. Entries are `{"arbitrary-key": {"task":
"app.tasks.foo", "options": {...}}}`, so that lookup silently found nothing and fell through to the
default queue — **which is `background`, the queue being sized**. The bug would have inflated the
number it was built to measure. It is also worse than a normal off-by-one: the wrong answer and the
plausible answer are the same string, so a test with a default expectation cannot see it. And one
task can have *several* entries (`collapse_snapshots` has three) that need not agree about the
queue, so the return type has to be a list.

**2. Refactoring `_bump_window_counter` to delegate to an INCRBY sibling turned 14 guards red with
counters reading `0`.** The delegation is the more obviously correct design — one function, an
`amount` parameter — and it changes the Redis **verb** under every counter in the module. Seven
test doubles implement `incr` and not `incrby`, and every writer there swallows exceptions by
contract (they run before and after every task in the system), so the result was a `SET NX` that
landed followed by a bump that raised into an `except: pass`. Real redis-py has both verbs, so
**production would have been fine** — which is exactly what makes it the wrong risk to take: the
test doubles were the only observer that could see it. Backed out, with the reason in the docstring.

---

## What the directive asked for that this queue deliberately did NOT do

**ITEM 1's hand-measurements are now reads, not measurements.** The directive asked to reconcile
`collapse_snapshots` reading 0.00/hr on the delivery counter while being the biggest occupant, and
to find what dispatches `refresh_hub`. Both were framed as bespoke measurement. With LAT-P242 live
they are a single read of one endpoint: `collapse_snapshots` will carry its deliveries and its
worker-seconds side by side on the same row, and a task consuming slots without a beat entry is
precisely what `queue_demand`'s non-beat-dispatch residual is there to expose. Building the
instrument was the cheaper answer than running the measurement, and it leaves something behind.

**ITEM 2 was not attempted, and must not be until #3466 is live and read.** The whole lesson of 179
and 180 is that acting on a ranking taken from a partially-blind instrument names the wrong task.
The instrument is no longer blind; the reading has not been taken.

**No production measurement was taken and no number is claimed here.** The counter is empty until
the code is live.

---

## State on exit — both ships graded, and they went opposite ways

| item | state |
|---|---|
| #3456 (the red shard blocking every branch) | CLOSED, fixed on master `18cbc206` |
| **#3399 — 180's ship** | **CERT-2037 GREEN, TOKEN GRANTED** on `9dc0fd0e`; exact-sha CI **`completed/success`** (run `34019461018`, 07:51Z). Notice-13 grep passes, no supersedes row, PR #3441 MERGEABLE, no alembic. **With the integrator, not self-merged** |
| **#3466 — LAT-P242** | 🔴 **CERT-2038 BLOCK, TOKEN WITHHELD.** PARKED |
| #3398 (parent measurement) | open, CLAIMED by latency |

**#3399 was not self-merged, deliberately.** The integrator holds `LANE-integrator.lock` (pid 71476,
alive) on `INTEGRATOR-228: … adjudicate the CERT-2029/2032 dead-token call` — this ship's own
lineage. Merging into that is the CERT-793-class race. A note with every merge gate pre-checked went
to their inbox instead; nothing is owed back to this lane.

### The BLOCK on LAT-P242 is correct, and this queue is not re-arguing it

CERT-2038's finding: the block shipped **an instrument, no number, and no user-visible surface, and
named neither a pillar nor a ship**. That is a violation of the binding progress/queue/rider/lane-role
rules — a *ship* failure, not a guard-only objection.

It is right. The program file and the directive both name the pillar and the ship; **the cert block
did not**, and it opened by conceding "it ships no number" and "no user-visible surface change".
CLAUDE.md's rider rule says architecture rides a named user-visible ship and is never the cargo.
LAT-P242 was presented as cargo.

The code is green and reviewable — 38 tests, 12/12 mutants, 573 green, no migration, and the
grader's own row calls the implementation coherent. It is **parked, not abandoned**, at
`PARKED-MEASUREMENTS.md`, on `program/latency-246-the-queue-can-be-sized` @ `9d2ffaff` (PR #3468),
with the BLOCK's restage condition recorded verbatim.

### Complying with the BLOCK turned up the better brief

The BLOCK demanded LAT-P242 be restaged only as a rider to "an already queued user-visible search
change that actually fixes cold typeahead scheduling/expiry". Going to look for that ship found it
in the beat schedule, with no measurement needed (`app/tasks/__init__.py:5131-5155`):

| UTC | entry | limit |
|---|---|---|
| 06:30 | `collapse-odds-snapshots-daily` | 500 |
| 06:30 | `turbo-collapse-futures` (every 6h) | 5000 |
| 06:35 | `collapse-winprob-snapshots-daily` | 500 |
| 06:40 | `collapse-futures-snapshots-daily` | 500 |
| 06:45 | `turbo-collapse-odds` (every 6h) | 5000 |

**Five compaction beats in a fifteen-minute window on a two-slot queue.** All five default to
`background`; both `turbo_collapse_*` carry `soft_time_limit=3600`. The codebase already says the
consequence in its own words at `app/tasks/__init__.py:3690` — they "may hold **half the background
pool for a full hour**, four times a day", and "a long pair can hold BOTH slots simultaneously — a
scheduled, total background outage window with nothing else able to run."

Meanwhile `warm_typeahead` fires every 10s with `expires: 120` and queues 18 deep, so through that
window every fire is discarded before a slot frees and the 65s TTL lapses.

That is a user-visible ship with a pillar and **a time of day**: *DISCOVER — the search box stops
going cold every morning while five compaction passes share two slots.* It is a beat-schedule
change, it costs nothing, and — unlike a topology argument — it does not depend on knowing the
total, because removing a scheduling coincidence is provably good at any utilisation. That is what
LAT-P242 should ride, and it is a sharper brief than the demand total would have produced.

## Rules added by this queue

**(bbb) A refactor that changes the PRIMITIVE under a shared, exception-swallowing writer has a
silent blast radius, and the test doubles are its only observer.** Production having the capability
is not a defence — it is what hides the change. When every caller of a helper swallows exceptions by
contract, do not change its verb for tidiness.

**(ccc) When the wrong answer and the plausible default are the same value, a test with a default
expectation is vacuous.** Pin a NON-default expectation, or the test passes for the wrong reason.

**(ddd) A "the field is present and null" test does not exercise the compute branch.** An
early-returning absent case and a present-but-unmeasurable case produce the same-looking output down
two different code paths. A mutant defaulting a withheld rate to `0.0` survived a full battery
because only the first was tested.

**(eee) A per-key total must be attributable, and unattributable demand is NAMED, not split.** One
task with several beat entries on different queues cannot have a per-task counter apportioned;
dividing it evenly invents a number.

**(fff) Signal-wired observability fails silently in two indistinguishable ways** — never connected,
and connected-but-raising — because the handlers swallow by contract. Drive the REAL signal in the
test; calling the handler directly proves neither.

**(ggg) An instrument is never the cargo, however good it is and however badly the next decision
needs it.** CERT-2038 BLOCKed a green, well-guarded, genuinely useful measurement instrument purely
on queue shape, and it was right to. Name the pillar and the user-visible ship **in the cert block
header**, or the block is refused before its evidence is read. The corollary is the useful half: if
you cannot name the ship, you have not found it yet — and looking for it is what turned "the queue
is oversubscribed, somehow" into "five compaction passes share two slots for fifteen minutes every
morning".

Carried: 168 (a)–(g), 170 (b)–(e), 171 (b)–(e), 173 (f)–(i), 174 (j)–(m), 175 (n)–(x), 176 (y)–(dd),
177 (ee)–(kk), 178 (ll)–(oo), 179 (pp)–(uu), 180 (vv)–(aaa) all hold.
