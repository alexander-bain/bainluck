# DOCTRINE — the general clauses, separated from the rulings that minted them

**Created 2026-08-18 (queue 367) on Alex's ruling, answering the flag queue 366 raised.**

## What this file is for

A ruling is a decision about a **specific** thing: this population, this constant, this
lane. Some rulings also contain a clause that is true of everything — and that clause
then has nowhere to live. Left in the ruling, it is only found by whoever goes looking
for *that* ruling, which is precisely the person who already knows it. Ruling **081**
named the shape: *a clause that pays out in its own banking window is doctrine* — if a
sentence written to settle one case immediately explains a second, unrelated case, it
was never about the first case.

So: **rulings stay narrow and keep their evidence; the general clause is lifted here.**

- A ruling is still the record. Doctrine never replaces one, and never carries the
  forensics — it carries the sentence and a pointer.
- This file is **not** ordering, priority, or status. Those live in GitHub Issues.
- Entries are short on purpose. A paragraph nobody re-reads is the same failure as a
  held item nobody re-reads.

**How to add one.** When banking a ruling, ask: *does this clause survive deleting the
case?* If yes, add the aphorism here with a one-line gloss and a pointer to the ruling
and the named failure. Do not restate the ruling.

---

## The clauses

### 1. Could-not-check never renders as nothing-to-report.

A check that could not run must not produce the same output as a check that ran and
found nothing. An empty result, a missing field, a skipped job, a `None` — each has to
be distinguishable from the healthy zero, or the reader supplies the reassuring reading
and is never wrong-footed by the evidence.

*Named failures:* gotcha #53 (Kalshi's `200 + trades: []` for a purged market read as
"no trading happened", recorded SUCCESS every 6h for ten weeks); gotcha #54 (`cmd | tail`
reporting tail's exit code, so a gate that never ran logged `0`); `pull_request:
branches: [master]` giving a stacked PR **no checks at all**, which at a glance is a
green PR (queue 366 `ci.yml`, queue 367 `codeql.yml`).

*Consequence in code:* prefer a three-valued verdict over a bool wherever "unknown" is
reachable — see `app/utils/game_pairing.py`'s `Pairing.UNKNOWN`, and
`app/utils/task_verdict.py`, whose whole purpose is that "it returned" is not "it worked".

### 2. A guard derived from the thing it guards inherits the lie.

If the bound, budget, or expectation is computed from the same artifact the check is
meant to police, it moves whenever the artifact is wrong — and agrees with it. The guard
reports green because it has been redefined, not because anything is sound.

*Named failures:* a ceiling derived from the plan is not a ceiling (ruling **075**,
PR #1943); a fixture that agrees with the bug is the bug (ruling **072**); `repair()`
re-deriving a fresh census under `apply=true` and reporting `miswired_after=0` against
a plan it was never bound to (the 341 hold).

### 3. A percentage padded for safety is an absolute threshold in disguise.

"Allow 10% headroom" reads as proportional and behaves as a constant the moment the base
is itself a measurement. The pad silently becomes the thing being tested.

*Named failure:* the Sentry budget margin (queue 351) — 14.7% against 164.47/day was
157.0/day once the negative controls were priced in, and both readings came from the
same padded base.

### 4. Label equality is not identity.

Two rows agreeing on a name, a matchup, a title, or a normalized string agree on a
**label**. Identity requires dereferencing an id to the thing it names. A label is
evidence; it is never proof.

*Named failures:* ruling **042** (dereference the id, never the label); ruling **079** —
five real scheduled MLB games carried another game's `espn_id` and final score, and the
population that "obviously" needed deleting was admitted by attended evidence per member
instead of by widening the constant that refused it; #1947/#1945 — three ingest sites
paired provider rows to ours on a **team pair with no date**, and in a four-game series
the team pair is not a game.

*Corollary (ruling 079):* a refused population is admitted by evidence gathered
**outside the predicate**, never by loosening the predicate that refused it.

### 5. One predicate, one implementation.

When the same question is asked in two places, the two copies drift, and the drift is
invisible because each site looks correct on its own. Consistency is the requirement,
not the constant (ruling **082**) — so the constant lives in one module and every caller
reads it from there.

*Named failure:* ESPN had a premature-live guard from #1207; StatPal, asking the same
question at three sites, had none — which is how live scores landed on games that had
not been played (#1945). The guard is now one function
(`app/utils/game_pairing.live_write_is_premature`), re-exported under its historical
ESPN name so there is no second copy to drift.

### 6. An instrument that re-reads its subject at coordinates captured earlier is reading two versions of it.

Line numbers, offsets, ids and cursors are captured at one instant and dereferenced at
another. If the subject can change between the two, the instrument reports a mismatch
between the *versions*, and names the subject it was pointed at rather than the one it
actually read — so the failure appears somewhere nobody touched.

*Named failure:* gotcha **#138** — nine source-text tests failed in CAL-P070's suite
because a module was edited mid-run; `inspect.getsource` re-read the file at line numbers
collected before the edit and handed each test a neighbouring function's body. All nine
were green on a clean re-run of the identical tree, and none of them was about the change.

### 7. A stale artifact reads as a current one — clause 1's sibling, and the harder half.

Clause 1 says a check that could not run must not look like a check that found nothing.
The sharper case is that it must not look like the check *before* it, either: any output
written to a reused path outlives the run that produced it, so a non-run inherits its
predecessor's verdict — complete, plausible, and corroborated by the reader's own recent
memory. Truncate or uniquify the target, and read the exit code's **value**: `1` is a
result, every other non-zero is a story about the harness.

*Named failures:* gotcha **#139** — three instances, exit **254** (lost cwd), **4**
(pytest usage error on a relative path) and **1** (a `cd`'s exit code, over a stale log of
a failure that had already been fixed); gotcha **#54**, whose prescribed
`cmd > /tmp/gate.txt` fix is what creates the reused path.
### 8. Duration is not occupancy.

**The occupant is whoever holds the slot when you look.** A task's p50 duration answers
"how long does one run take"; a pool's share answers "who is in the way". They are
different questions and the first cannot be substituted for the second, because
occupancy is *duration x frequency* against a fixed number of slots — a long task that
runs four times a day can be a rounding error, and a short one that runs constantly can
own the pool.

Queue depth (`LLEN`) is not occupancy either: it is backlog, and it is blind to an
arrival a free slot consumes in 100 ms. Both are corroborating evidence at best;
**neither may headline a finding about contention.** To measure occupancy, count
slot-observations — sample the worker's `active` set and see who is actually there.

*Named failure:* #224/#1609 spent an entire program cycle chasing `backfill_winners` on
the strength of a p50 of **13.7 minutes**, the largest duration on the board. Direct
measurement of celery's `active` set — 122 slot-observations over 62 minutes — found it
in **zero** of them. It runs 4x/day: **2.45 %** of a 2-slot pool. The actual occupants
were `warm_typeahead` (26.2 %), `match_prediction_markets` (12.3 %) and the two
`turbo_collapse` tasks (11.5 % + 6.6 %) — one of which had **no gauge at all**
(ruling 086). The right statistic was available the whole time; the wrong one was
merely easier to read.

*Corollary:* an instrument that reports the wrong quantity confidently outranks a
missing one in cost, because a missing instrument is owed and a wrong one is believed.

### 9. A bound derived only from successes cannot be corrected by the failures it causes.

When a limit is computed from completed runs, and exceeding the limit produces something
that is *not* a completed run, the failures are invisible to the rule that set the limit.
Every violation then makes the evidence for widening it stronger and the input to the
calculation no larger — a one-way ratchet whose fixed point is the outage. Refusing to
learn from a truncated run is usually **correct** (it is a lower bound, not a cost), so the
defect is not in that refusal; it is in having no other path by which the bound can move.
**Ask of any derived limit: what would raise it, and can the thing it constrains produce
that?** If the answer is "a success it is preventing", the loop is closed and only an
outside decision opens it.

*Named failures:* ruling **089** — the calibration futures phase, budgeted at
`max(completions) × 1.5` from ten pre-bump 47–118 s runs, cancelled its own unit reads at
the derived 159,637 ms cap for **111 consecutive beats** while every one of them recorded
a floor the budget was forbidden to read. Sibling of clause 2 (*a guard derived from the
thing it guards inherits the lie*): clause 2 is a rule corrupted by its subject, this is a
rule **starved** by it.

### 10. An identifier in a directive is a proposal; the ledger allocates.

A number, slot, or name handed down in an instruction is a *request for* an allocation,
never the allocation itself. Authority to ask is not authority to reserve, because the
asker is not looking at the ledger at the moment the work lands — and between the
directive and the commit, a sibling lane can take the number in good faith. The executing
lane resolves the identifier **against the ledger at write time** and reports the
substitution; it does not use the handed-down value on the strength of who handed it down.

*Named failures:* the LAT-P069 directive assigned ruling **087**, which `ux` had already
banked and merged — the lane took the next free number (**088**) and said so
(ruling **088**). The same shape sank Option D for two cycles: a `migration_slot` *ruled*
assigned in a directive was treated, correctly, as not-yet-an-artifact, because a verbal
ruling relayed through a directive is not the file the invariant reads. And
`MINIMUM_BANKED_RULINGS` has now collided three times, resolved every time by **counting
the files in the merged tree** rather than by trusting either side's number (#1910).

*Consequence in practice:* it is what makes the ruling-per-file layout work at all
(ruling **001**). Separate files cannot conflict, so two lanes banking the same day collide
only on the *number* — which is recoverable by renumbering — instead of on a shared append
region, where the only correct resolution is keep-both and the merged commit carries a new
patch-id forever, so `git cherry` reports landed work as new on every later cycle.

*This clause renumbered itself while being written, which is the cheapest possible demonstration
of it.* It was banked as **7** against a `docs/doctrine.md` holding six clauses. Within four hours
calibration-67 merged and took 6 and 7, was reverted, then **re-landed** as CAL-P071 alongside
CAL-P072 — moving "duration is not occupancy" from 6 to 8 and pushing the ledger to nine clauses.
The number was a proposal both times; the ledger allocated **10**.

⚠️ **And note what this file still is: a shared append region.** Doctrine has exactly the collision
shape ruling 001 removed from rulings, and it has now produced three conflicts in two days. The
one-file-per-clause treatment is the obvious fix and is deliberately *not* done here — it is a
layout change that belongs to whoever owns this file, not to a lane passing through.

### 11. A TTL compared against a cadence is a bug in both directions.

Any expiry chosen without reference to the period of the thing it holds will be wrong, and it
will be wrong **differently depending on which side of the period it lands on**. Two failures,
not one:

- **TTL ≈ cadence** → the value races its own expiry every period. Sibling values written a
  fraction of a second apart can resolve that race in *opposite* directions, so a derived
  quantity computed from both is not merely stale — it is **arithmetically impossible**.
- **TTL < k × cadence**, where `k` is the sample size some consumer requires → the value can
  *never* satisfy that consumer. Not "not yet": never, while both constants hold. And it will
  report the shortfall in the language of a transient condition, because the code that wrote
  the message could not see the ceiling either.

*The rule:* an expiry is stated **in units of the period it must span**, and any consumer with a
minimum-sample requirement is checked against the resulting ceiling **at the point the constant
is defined**. A consumer that cannot be satisfied by the ceiling does not get a longer wait; it
gets **a different instrument** — one keyed on a *moment* rather than a *count*, because a
timestamp carries its own age and has no expiry to race.

*Named failures — one constant, `WINDOW_COUNTER_TTL = 86400`, both directions, found six hours
apart:* it equals a daily beat's cadence, so `mlb_schedule_coverage` reported
`hard_kills_24h: 1` and `health: critical` in a payload that carried that same run's
`last_success_at`, `last_duration_ms` and `last_result_summary` — the end handler's own writes
(LAT-P070, `ef782755`). And it is less than **twice** any daily cadence, so
`schedule-adherence`'s rate arm — which needs `MIN_EXPECTED_FIRES = 2.0` — reported
`window_too_short(expected=0.89<2.0)` for **33 of 123 scheduled entries**, permanently, including
**all six sentinels T5 grades** (LAT-P071, `58267ed9`). Sibling: `REFRESH_LOCK_TTL = 120` guards a
single-flight dispatch whose publish→start lag was measured at **123 minutes** the same night, so
the guard is a function of wall time and the thing it guards is a function of queue position.

*Why it keeps happening:* a TTL is written next to the value it protects, and a cadence lives in
the beat schedule. Nothing puts them on the same screen, so the comparison is never made — and
neither failure announces itself, because an expired key and a never-written key are the same
absence (clause 1, and gotcha #53).

### 12. A line in a spec needs a fixture ON the line.

`0.7 - 0.5 !== 0.2`. A threshold assembled from decimal inputs lands a few ULPs either
side of its intended value at random, so whether two identically-specified cases fall the
same way depends on which decimals someone happened to write them with. Every boundary
therefore ships as a NAMED comparison — `travelAtOrAbove()`, `spread_exceeds()` — with a
fixture sitting exactly on it, never a bare inline `>`/`>=`.

The reason this is doctrine and not a style note: the defect is invisible to ordinary
test data. A suite whose fixtures all sit clearly inside or clearly outside the band
passes under either comparison, so the bug survives every assertion and every review, and
only a fixture ON the line can see it (ruling **087**'s shape — an exclusion that gets
quieter as it gets more wrong).

*Named failures, one in each direction:* on the shipped prop rail a `>=` spec was
implemented as `>` and **a prop that moved exactly twenty points read as NOT surprising**,
silently, because no fixture sat on the line (cycle 98). Conversely, sweeping every pair
whose intended spread equals the divergence threshold, a bare `>` **wrongly gates 78 of
601** — the epsilon-tolerant `spread_exceeds` gates 0 (cycle 99, ruling **097**).

### 13. Read-only is a property of the query, not of the intent.

"It only reads" describes what a caller *means to change*, and says nothing about what the call
*costs to serve*. A request that writes nothing can still hold the one resource every other
request needs — an event loop, a connection, a worker slot, a lock — and while it holds it, the
service is down for everyone. Safety and cheapness are separate axes, and the word "read-only" is
routinely used to assert the second by proving the first.

The tell is an endpoint that is exempted from the guards precisely *because* it is read-only: no
destructive-secret check, no rate limit, no single-flight, often an auto-refreshing dashboard tab
pointed straight at it. The exemption is granted on the axis that was never the risk.

*The rule:* price a read by **what it occupies and for how long**, not by whether it mutates.
Anything that blocks — a broadcast, a fan-out, an unbounded scan, a synchronous client inside an
async handler — is bounded, moved off the shared resource, and single-flighted, whatever its verb.
And an instrument that measures contention must be priced hardest of all, because it is used most
exactly when the resource is already scarce.

*Named failure:* `GET /api/admin/celery-debug` calls `celery_app.control.inspect()` **four times,
inline, at `timeout=5`, inside an `async def`**. `inspect` is a broadcast: it publishes to a
control exchange and blocks until every worker replies or the timeout expires, so one request can
hold the single uvicorn event loop for up to twenty seconds. Two read-only samplers polling it at
20 s and 8 s black-holed **the entire production API for ~10 minutes**, `/api/health` included,
with `heroku ps` reporting `web.1: up` throughout. The proof is the recovery: killing the two
pollers by pid returned p50 to 0.227 s within 25 seconds, with nothing restarted — the dyno was
never unhealthy, the loop was never free (#1994, ruling **096**, LAT-P071 §3e). The endpoint was
exempt from the destructive-secret guard *because it does not write*.

*The compounding form:* the program was measuring **why scheduled work cannot get a slot**, using
an endpoint that consumes the web dyno's only loop to ask. The instrument was part of the
phenomenon. Sibling: gotcha #40's `db-query`, and `celery-debug`'s own memoisation, which then had
to be given a `?fresh=1` bypass because a 5-second cache **masked a live broker failure** — buying
availability with a window in which a real error reads as a healthy 200 (clause 1 again).

### 14. Two measurements never computed side by side have not been compared.

When one number grades another — a metric grading a control, an audit grading a
pipeline, a census grading a repair — the two must be produced by one artifact
that prints both. Not reviewed together; **computed** together, so the
difference is a value someone has to read.

The failure this prevents is not carelessness, it is the case where **both
readings are defensible**. Each side tests its own half, each is green, and the
disagreement lives in the only place neither test covers. No amount of care
finds it, because there is nothing to be careless about: the control is right
about its window and the metric is right about its own.

*Named failure:* `enforce_first_page_quality_floor` protects the first twenty
SERVED cards and was doing it perfectly — zero boring futures in the served
top-20. `audit_feed_quality.py` grades it by filtering to `type == "futures"`
first, which is a different twenty, offset by the 4-6 bundle cards the page
interleaves. Every card the metric flagged sat at served position 22-24. The
number reported as the lane's finding, and kept a P2 open for a month, was a
true statement about a window with no screen behind it (ruling **098**).

*Corollary:* the window, unit or population is part of a metric's NAME. A rate
whose denominator is implicit will be read against whichever denominator the
reader has in mind, which is usually the product's, which is usually not the
code's.

---

### 15. An intervention on a period-quantised system is judged against the quantiser, not the average.

Where a control variable is *also* the quantiser of some periodic quantity, the
mean of that quantity is the wrong statistic to reason from. A quantiser coarser
than the distribution it acts on puts **every** sample on the same side of the
threshold, and an average — or a median, or a "typical case" — hides that there
is no branch left under it.

The tell is that the arithmetic on the side you are optimising is *correct*. It
usually is. The error is not a bad calculation; it is a second role the control
variable plays that the calculation never had a term for.

*Named failure:* `warm_typeahead`'s beat interval. The proposal to move it 10s →
60s was reasoned entirely from arrival: 72.0% of everything published to the
`background` queue, ~82% of fires no-ops, a 60% cut. All true, all undisputed.
But the beat also quantises the warmer's pass period —
`P(B) = B * ceil(max(wall, floor) / B)` — and the period is measured against a
hard **45s** cliff, `/typeahead`'s response-cache TTL. At B = 60 the quantiser is
coarser than the whole measured wall distribution (29.4–42.6s), so P = 60s at the
best, median **and** worst wall alike. LAT-P063 had already graded 20 passes for
20: crossing that TTL does not degrade the head gradually, it empties it. The
halt fired on evidence already in the tree, before any deploy (#1609, #1866,
`app/utils/typeahead_beat_budget.py`).

*Corollary, and it is the sharper half:* **a change that arithmetically fits
inside a measured gap is still refused when the gap is narrower than the
sample's own uncertainty.** `B = 22` happens to give P = 44s across the entire
measured range — 1s of headroom, computed against a maximum drawn from 20
passes. A maximum from a finite sample is a lower bound on the true maximum, so
every margin computed against it inherits that. 1.4s of headroom is not a
margin, it is a coincidence, and the corollary was vindicated inside the window
that banked this clause: the wall's p95 was subsequently measured at **44.6s**,
above the 42.6s "maximum" the margin had been computed from.

*Sibling of clause 3* (a percentage padded for safety is an absolute threshold in
disguise) — both are cases where the number being reasoned about and the number
that actually decides are different quantities.

### 16. A verification suite reports the score of its FIRST pass, not of its last.

Where a suite is graded by adversarial trials — mutations, fuzz cases, injected
faults, red-team probes — the number that goes in the report is what the first
honest run produced. Tightening afterwards is not merely allowed, it is the
point; **presenting the tightened number as the original result is what is
forbidden**, and it is forbidden because the tightened number is a tautology. Any
suite reaches "all caught" if you keep patching until it does. The only figure
carrying information is the one measured before the suite knew what was coming.

The tell is a perfect score with no story attached. A first pass that catches
everything either faced trials chosen to be caught, or is genuinely good — and a
reader cannot tell those apart from the score alone, so the score has to arrive
with its history.

*Named failures, both from the lane that banked this:* LAT-P073's **M4** (a
kill-switch mutation survived; both branches published, so nothing failed, and
the only casualty was a reason label an operator would then go hunting a phantom
Redis fault over). LAT-P074's **M10** — an assertion reading `"run_in_threadpool"
in body` survived a mutation that deleted the `await` and left the import line,
so the endpoint was blocking the event loop while the test read green. Both were
reported as first-pass survivals and *then* patched, in that order.

*Sibling of clause 1* and of ruling **074** (a green pass names the work it did):
all three refuse a summary statistic that has been separated from the conditions
that produced it. A suite score with its provenance removed is an empty `200`.

---

## Related

| Where | What it holds |
|---|---|
| `docs/rulings/NNN-*.md` | The rulings themselves — one file each, with their evidence |
| `docs/rulings/README.md` | File shape + the collision protocol |
| `docs/PRODUCT-BRAIN.md` | Standing product judgment and the lane split |
| `docs/gotchas-reference.md` | The full incident catalog these clauses generalize from |

### 17. A green suite over code that has never executed is evidence about the suite, not about the code.

Lifted out of ruling 102, which named the obligation ("every worker, consumer,
task and script ships with at least one IMPURE test that starts it") on one
case. The general sentence survives deleting that case: **a test proves a
DECISION; only an execution proves the code runs.** Wherever a body of tests
exercises pure functions around an entry point without ever entering it, the
pass rate measures the tests' internal consistency and says nothing whatever
about whether the thing works.

The reason this is worth a clause rather than a habit is the asymmetry in how
the two failures present. A wrong decision fails a test. **An unstarted entry
point fails nothing** — it is simply absent from the evidence, and absence reads
as fine (gotcha #53, one layer up). So the suite gets greener as it grows, and
the confidence it produces grows with it, and neither has any contact with the
question being asked.

*Charter case:* `cohort_cell_census` (#1978) merged with **37 tests, all pure**,
passed CI, passed a clean integration, deployed at v3863 — and died in **73 ms
on every invocation**, because `get_task_session` is an `@asynccontextmanager`
the worker hand-drove as a bare async generator. **17,093 green tests over a
worker that had never run once**, with two further defects queued behind it, all
three surfaced within minutes of the first real start.

*And it keeps paying out against the lanes that bank it, which is the argument
for it.* CAL-P077 wrote its reader's impure test first, covered the fold path
and not the two optional side probes, and lost a 49-cell production sweep to a
`statement_timeout` in the uncovered branch after thirty cells. CAL-P078 then
did it again one file over: every test of its new reader stubbed the fold, so
`from app.database import get_task_session` — a module that does not exist —
was never executed, and the script died on its first line of real work the first
time a human ran it. Both were found by running the thing, not by reading it.

The corollary is where the rule earns its keep: **the branch worth starting is
the one you were least likely to write a test for.** Both payouts above were
optional paths, side probes and error handlers — the code that only runs when
something is already wrong, which is exactly when nobody is watching.

### 18. A row-dropping fix is graded on the rows it keeps and on the cells where the mechanism is absent.

Lifted out of ruling 103. Whenever a change improves an aggregate by REMOVING
observations — an exclusion, a filter, a quality gate, a cohort restriction —
the headline delta is the one number that cannot be used as evidence, because
**dropping hard rows lowers an error metric whether or not the reason for
dropping them is sound.** Every such fix improves its own metric. The
improvement is not the finding; it is the thing requiring one.

Two things do carry the argument, and they are the ones to demand:

1. **The control cells — where the mechanism is ABSENT and nothing should
   move.** If the population is dropped for reason R, then cells with little or
   no R must be near-unmoved. A generic row-dropping effect would move them too,
   so they are the falsifier. Attack them first.
2. **The kept sub-population is CORRECT, not merely better.** "Less bad" is
   consistent with having removed the noisiest rows; "exactly right" is not.

*Case:* the hindsight-capture exclusion measured four candidate policies on the
full 49-cell population rather than assuming one. **Policy D — the intuitive
fix, dropping every fallback price — made the pooled curve WORSE (+0.073 pp)
while discarding 69% of it.** The approved policy moved 3.763 → 1.766 pp
dropping 9.3%, its eight low-mechanism control cells all moved by ≤ 0.097 pp,
and the kept sub-population of the worst cell was calibrated to **0.0 pp** — not
less bad, right. A fallback price is not a bad price; a hindsight price is.

*The trap this closes:* a drop predicate can be blameless in DEFINITION and
still not be outcome-blind in EFFECT. The hindsight rows had a different winrate
from the rest (0.296 vs 0.430) — necessarily so, since a post-settlement price
correlates with the outcome, which IS the corruption. So the exclusion changed
the cells' outcome mix as well as their price quality, and only the control
cells distinguish "we removed corruption" from "we removed difficulty".

*Second obligation, from the same case:* a cell that falls below the reporting
minimum after the drop becomes an **ABSENCE WITH A REASON, never a fixed cell**
(ruling 075's second clause, on the scoreboard). A metric that improves because
a cell VANISHED has not improved.

---

### 19. A per-row predicate cannot fix a defect whose unit is a group.

Wherever the thing that is wrong is a property of a **set** — repetition,
over-representation, imbalance, near-duplication — every rule whose subject is a
single member is a treadmill. Each member the rule removes is replaced by the
next member of the same set. Tuning it harder does not converge; it relocates.

**The diagnostic is a sweep that does not move the outcome.** A threshold whose
whole range produces one shape is not mistuned, it is aimed at the wrong unit.
That is cheap to test — sweep it end to end and look at the result, not the
count — and it is worth doing before spending a cycle tuning a constant.

*Charter case (ruling 111, #195).* UX-P107 shipped ruling 105's structural-rung
filter on the pregame prop rail and swept its constant `PROP_STRUCTURAL_CERTAINTY`
from `0.44` to `0.35`. The rail kept **the same shape at every value**. The rung
population is a continuum with no gap (5.0, 6.0, 7.0, 7.2, 8.5, 8.8, 9.0 …) and
conviction ranking selects a ladder's extreme rungs *by construction*, so the
slots freed at each step refilled from one rung up the same ladder. The fix had
to be the first rule on that surface whose subject was a GROUP — one row per
player-ladder family.

*Second specimen, pre-existing and on another surface.* UX-P098's #1958 finding
recorded that Discover's `boring-rate@20` target is an **aggregate** while its
only control is a **per-family cap of 1**, and called the pair "structurally
inconsistent" — the same shape, filed weeks earlier, still open. Neither case was
derived from the other.

*The corollary that keeps this from being read as "always cap".* A group rule is
the answer when the defect's unit is the group; it is not a licence to cap
things. Ruling 112 is the counterweight from the very next cycle: the same
ladder cap that fixed the repetition also made it safe to **readmit** a rung an
unconditional per-row filter had deleted, because a cap bounds a group without
having to be wrong about any individual member of it.

**⚠️ Numbering note (ruling 066's receipt, discharged).** This clause was
claimed as **19** by UX-P108 and its FILE deliberately withheld: the numbering
guard asserts clauses are contiguous from 1, that branch's base carried 16, and
17/18 were calibration's — claimed and unmerged. Writing it then would have
shipped the `[1..16, 19]` gap the guard exists to catch. The recorded exit
condition was *"`program/calibration-75` merges, master's highest clause reads 18,
and the UX lane writes `### 19.` unchanged"*. Both halves are now true
(`origin/master` = `724fd22c`, highest clause **18**), and it is written here
unchanged, at the number it was claimed at, **without a fifth renumber**.

---

### 20. A hand-written field is unvalidated input, not a measurement.

A perfect test applied to a field nobody validated inherits the field's error.
`ps -p <pid>` answers *"is that pid alive"* flawlessly and says nothing whatever
about whether the file names the **right** pid — yet a rule that reads the field
as though it were an instrument treats the two as one question.

The tell is grammatical: wherever a check consumes a value some earlier human
typed, it is reading a **claim**, and a claim can be false in ways the check is
not built to notice. Validate the field, or pair it with something the writer
could not forge.

*Charter case (ruling **008**, INT-108 amendment, 2026-08-21).* `LANE-lane1.lock`
read `HELD` with `owner_pid: 38410`, a dead pid — while lane1 was alive and
landing two commits. Read literally the rule said *dead pid, therefore free,
therefore take the lane*. The correct answer was to take nothing and go find out
why a live lane's lock named a dead process.

*Corollary — affirmative accounting beats absence,* and it is clause 1 in the
identity direction: **"I found nobody" is an absence; "I found everybody, and
none of them is here" is a measurement.** Ruling 008's third takeover test is
the affirmative form — each live candidate process mapped to *another* lane by
that lane's own lock — and it is the only one of the three that can rule out a
live owner filed under the wrong pid.

*Same family:* ruling **022** (one shared claim primitive) and its live defect —
a partial re-stamp that refreshes `owner_pid` but leaves the previous owner's
`owner_started` **manufactures** this condition rather than merely failing to
catch it.

### 21. An untrusted signal may VETO, never GRANT.

When a signal is too unreliable to decide a question, the choice is not
binary — trust it or delete it. Give it the **asymmetric** half of the
authority: let it refuse, and never let it permit. A signal that can only block
cannot manufacture permission, so its failure modes collapse into the safe
direction by construction rather than by discipline.

The test for which half is safe: ask what each drift direction *does*. If one
direction merely blocks something legitimate and the other admits something
dangerous, the signal keeps the blocking power and loses the admitting power.

*Charter case (ruling **008**).* Heartbeat timestamps were demoted from oracle to
veto. Ahead-drift (a future stamp) had **admitted a second writer to master**;
as a pure veto the same drift can only refuse a takeover. Behind-drift is never
consulted at all, because the pid test has already answered HELD and stopped.
"Both keys turn, or nobody enters."

*The counterweight, so this is not read as "vetoes are free":* a veto is still a
claim, and clause 22 is what stops it becoming permanent.

### 22. A blocking state with no exit is not conservative — it is stuck.

Every refusal needs a stated condition that clears it, and the condition has to
be **reachable**. A guard whose blocking branch can only be satisfied by
something that can never happen is not a cautious guard; it is an outage with
good intentions, and it will be read as caution right up until someone notices
nothing has moved.

Check it the cheap way: name the event that clears the block, then ask who or
what produces that event. If the answer is the thing the block already
established is gone, there is no exit.

*Charter case (ruling **008**, INT-109 amendment, 2026-08-22).* `MALFORMED-
INVESTIGATE` said "take nothing" with no exit — the named pid can never come
back to life to clear the condition, and a timestamp can never get younger. So
the lane was unclaimable **indefinitely**, and the cost landed on the sole writer
of master. The amendment supplied the exit the word INVESTIGATE had always
implied: the freshness must be **EXPLAINED**, and when the explanation is the
named process's own shutdown flush, it is a takeover after all.

*Corollary — one timestamp is a photograph; two are a derivative.* The way out
of that particular block is a **re-measure, spaced**: a live owner writes again,
a corpse does not. Wherever a single reading is being asked to establish
liveness, motion, or progress, take the second one.

*And the standing of a human saying "it's fine":* corroboration, never the
artefact. It may prompt a re-measure; it may not replace one.

### 23. Discipline tightened and then violated in BOTH directions is a mechanism failure, not a discipline failure.

One violation is a mistake. Repeated violations **in opposite directions**,
after the rule has already been sharpened, are diagnostic: they say the
mechanism is asking a human-written artifact to carry a safety property, and no
amount of further care will make it do so. Symmetry is the signal — a
one-directional failure can still be carelessness, but drifting *both* ways
means the requirement is unmeetable, not unmet.

The remedy is to remove the artifact from the decision, not to write a firmer
rule about maintaining it.

*Charter case (ruling **008**).* Every earlier attempt tightened the discipline
around the heartbeat — stamp at each phase boundary, read from `date`, never
future-date — and it was violated anyway, **ahead ×2 and behind ×1**, with
opposite costs (fails-open admits a second writer; fails-closed steals a live
lane's work). The rule silently picked a side depending on which way a human's
clock had slipped. Neither failure is available to a rule that never reads the
clock.

*The trap this closes is recursive, and ruling 008's own history contains it:*
the INT-108 amendment's first instinct was "keep `owner_pid` accurate" — which is
the same discipline fix that had already failed twice in that very file.
**Proposing the failed remedy is easy precisely because it is always locally
reasonable.**

### 24. A translation layer may not speak the source vocabulary in its own voice.

When a product exists to turn one domain's language into another's, the
translated surface is not allowed to carry the source language — least of all in
the sentence that **explains** the translated number. Doing the conversion and
then naming the result in the old vocabulary hands the reader back the thing you
removed, at the last step, after they had already been spared it.

The tell is that the argument for keeping the word is always **consistency**:
several surfaces already use it, and changing one would make them disagree. That
argument is backwards. Consistency is a property worth having *about the right
word*; several surfaces agreeing on the wrong one is not one reason to keep it,
it is several places to fix.

Where our names legitimately survive: enum values, data attributes, column
names, code, comments, reports. The boundary is **rendered text a reader sees** —
which is also what makes the guard cheap, because a sweep over rendered text
with attributes stripped is indifferent to the data contracts by construction
rather than by an exception list.

*Charter case (ruling **138**).* Alex, 2026-08-27: *"'price' as a noun is banned
in user-facing copy — the word is PROBABILITY."* The morning's earlier line had
banned *priced* as a verb and kept *price* as the noun, on exactly the
consistency argument above. The named failure: a platform whose whole premise is
"60% vs 40%, not -150/+130" was printing **"Prices paused"** over the number it
had just finished translating.

*The limit, so this is not read as a ban on a word:* it forbids naming OUR
output in the source vocabulary. It does not forbid the word where the subject
genuinely is the source thing — `/economics` still says "the price at the pump",
because that market is about a price.

### 25. A suppression rule must key on everything that makes two items different questions.

Every surface that shows a list eventually grows a rule for "we already have one
of these" — a template family, a story key, a diversity cap, a near-match
threshold. Each one derives a KEY and drops whatever collides. The clause is
about the key: **it must carry every field that makes two items answer different
questions.** Dropping a field so the rule fires more often does not make it
stricter. It makes it blind to the distinction it was written to protect.

The reason this needs stating is that the failure is **silent by construction**.
A suppression rule reports a count, and a count reads as evidence of curation.
The list looks deliberate; the item that was deleted left no trace on the page;
and the only person who could notice is the one holding both items in their
head, which is nobody after the day it shipped.

The usable test is not similarity. It is: **if a reader saw both, would they
learn something from the second one?** Two items about different subjects almost
always pass it, and the contrast between them is routinely worth more than
either alone — which is the case a shape-based key gets exactly backwards,
because two items are most similar in shape precisely when they are most
comparable in substance.

*Charter case (ruling **139**).* Alex, 2026-08-27: *"alcaraz-second-major and
sinner-second-major are DIFFERENT PLAYERS and must both render. Key the
near-duplicate rule so it never collapses across players."* The family key
dropped the subject token, so two rivals' odds of the same feat were one
"template" and one of them was deleted — at the renderer AND, later, at the
source. Measured the same night: 27c on 42,723 open interest against 1c. Side by
side, the state of the men's draw; separately, trivia.

*The limit:* the rule still exists and still fires. Same subject, same topic
still collapses, and the drop is still counted. What changed is what the key
carries.

# MECHANICAL SPECS — enforced by the Integrator, not judged by it

Everything above this line is a **clause**: a sentence a reader applies with judgement.
Everything below is a **spec**: a rule the Integrator executes without any. They live in
one file because a spec whose reasoning is somewhere else gets edited by someone who
never read the reasoning — but they are numbered separately (specs are named, not
numbered) so a spec can never be mistaken for a doctrine clause, and so adding one
cannot collide with a clause number another lane has claimed.

## MECHANICAL SPEC — `beat_cost`

**Owner:** the `latency` program. **Authority:** ruling 127 item 3 (PROGRAM CHARTER
AMENDMENT, Fable 2026-08-23, Alex ruled).
**Status: SPECIFIED 2026-08-23. ENFORCEMENT BEGINS THE CYCLE AFTER THIS SECTION MERGES
TO MASTER** — a gate that starts refusing merges before its threshold is published
refuses them for a reason nobody can read.

### The named failure it prices

CAL-P078's rolling re-stage (v3874, 2026-08-20 10:45:57 PDT) took
`precompute_calibration_main` from a p50 of **163 s to 1,263 s — 7.74×** — on the one
beat a user-facing page waits on, with no declaration anywhere. That silence cost three
latency cycles establishing the step was not caused by ruling 110's routing change, plus
one falsifier baseline that read ~6× against a perfectly healthy beat until ruling 123
re-pinned it.

**The flag does not forbid the change.** That re-stage was correct and would have been
approved. It makes a regime change arrive **announced**, so the next reader of that
beat's latency knows they are looking at a new regime rather than a regression.

#### 1. The field — mandatory, `none` explicit

Every READY token and every PR description carries a `beat_cost:` line, exactly as they
carry `migration_slot:` and `beat_schedule_change:`. **`beat_cost: none` is a valid and
common value and must be written out.** A missing field is not `none` — it is silence,
and a reader cannot tell silence from a decision (ruling 115's clause, applied to a
third instrument).

**The Integrator's whole job here is presence, not correctness.** It refuses a merge
whose token omits the field. It does not evaluate the number — evaluating it would
require the before/after only the changing lane holds.

#### 2. When the value must be something other than `none`

Declare when a change moves any beat's measured p50 by **both**

* **≥ 1.25×**, **and**
* **≥ 60 s absolute**

— deliberately the same two-gate shape as ruling 126's degradation predicate, and for
the same reason: a pure ratio is sharpest where a beat matters least, so a bare ratio
would demand a declaration for +4 s on a 17 s beat and excuse +297 s on the beat a page
waits on.

**Or when either of these is true after the change, whatever the p50 did**, because both
are failure modes a median cannot see:

* `p95 / soft_time_limit ≥ 0.80` — headroom. A beat at 94 % is one bad day from
  `SoftTimeLimitExceeded`.
* `p50 × runs_24h ≥ 3,600 s/day` — one worker-slot-hour per day. A beat that doubles its
  p50 and halves its frequency costs the same capacity, and a p50 alone cannot say so.

#### 3. The value is MEASURED, never typed

    source ~/.claude/.env
    python3 backend/scripts/measure_beat_cost.py --task <metrics_name>
    python3 backend/scripts/measure_beat_cost.py --all-watched

The script prints the block to paste. This is not convenience: lane1's doctrine clause
**20** — *a hand-written field is unvalidated input, not a measurement* — is the reason.
A field a human types is a claim, and the Integrator cannot tell a careful claim from a
careless one, so the only enforceable version is one whose value came from a command.

Declaration shape:

    beat_cost: <metrics_name> p50 <before>s -> <after>s (<ratio>x, +<abs>s)
               p95/soft <pct> · slot_s/day <n> · measured <ISO8601> via measure_beat_cost.py

`beat_cost: none` needs no numbers.

#### 4. Two traps the measurement itself must not fall into

* **Zero counters over a live ring mean the counters EXPIRED, not that the beat is
  idle.** `successes_24h`/`failures_24h` roll; the duration ring does not. The script's
  own first run reported `runs_24h 0` and therefore `slot_seconds_per_day 0` for
  `precompute_calibration_main` — a beat costing ~1,300 s an hour, rendered as costing
  nothing, in the exact field a reader would use to decide a declaration was unnecessary.
  It now reports **UNKNOWN** with the reason. (#2110 defect (b), one level out.)
* **A beat's `soft_time_limit` is not always its clamp.** Where a task imposes a tighter
  budget on itself (`compute_calibration_prices` stops at its own 540 s, not at the
  configured 600 s), the self-imposed budget is the denominator. See
  `BeatBaseline.effective_clamp_s`.

#### 5. Baseline at specification time — the flag is not theoretical

Measured 2026-08-23 against production, `--all-watched`: **four of the seven watched
beats already sit at or past the 80 % headroom threshold** —
`precompute_backfill_winners_status` **102 %** (its p95 is over its soft limit),
`calibration_prices` 95 %, `precompute_calibration_main` 94 %, `coverage_metrics` 80 %.
Any change touching those beats needs a declaration on the headroom gate alone,
regardless of what it does to their medians.
