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

### 6. Duration is not occupancy.

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

---

## Related

| Where | What it holds |
|---|---|
| `docs/rulings/NNN-*.md` | The rulings themselves — one file each, with their evidence |
| `docs/rulings/README.md` | File shape + the collision protocol |
| `docs/PRODUCT-BRAIN.md` | Standing product judgment and the lane split |
| `docs/gotchas-reference.md` | The full incident catalog these clauses generalize from |
