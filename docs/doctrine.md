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

---

## Related

| Where | What it holds |
|---|---|
| `docs/rulings/NNN-*.md` | The rulings themselves — one file each, with their evidence |
| `docs/rulings/README.md` | File shape + the collision protocol |
| `docs/PRODUCT-BRAIN.md` | Standing product judgment and the lane split |
| `docs/gotchas-reference.md` | The full incident catalog these clauses generalize from |
