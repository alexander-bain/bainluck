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

### 11. A line in a spec needs a fixture ON the line.

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
