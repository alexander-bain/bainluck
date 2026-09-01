# CAL-P156 — the state

Pillar **TRUTH**. Issue **#1978**. Two branches:
`program/calibration-119` (the freeze-lift stack) and
`program/calibration-120-orm-is-winner-nullable` (Alex-authorised, off master).

**Ship: a settled market that our own data graded stops being withheld from the
calibration curve because an unrelated market shared its variant.**

## 0. TL;DR — TWO BLOCKS, BOTH RIGHT, AND THE SECOND ONE DELETED MY FIX

* `TOP-PRODUCT-DEFECTS.md` has **no `[calibration]` item**, so the directive was
  the work (rule 1 satisfied, not skipped).
* **`CERT-514` BLOCK** — the D13 arm counted per market but consumed the counts
  in one variant-grained row requiring `ungraded_lone_claims = 0`, so an ungraded
  sibling still suppressed a graded claim. Correct. §2.
* **I fixed it by adding "rung 1b". `CERT-520` BLOCKED THAT TOO, and was right:
  the rung was DEAD CODE.** It keyed "graded" on `is_winner IS NOT NULL`; the
  repository's canonical predicate is `resolution_source IS NOT NULL`, and the
  measurement below shows every row my rung could have caught was **already
  excluded** by truth eligibility. §3 is the measurement and it is the most
  important thing in this document.
* **The whole correct fix is the one-line conjunct removal.** The producer diff
  against CERT-514's head is now exactly that. §4.
* **Directive item 3's PG-gate audit: DONE, answer NEGATIVE** — §6. It unblocked
  Alex's ORM decision, which turned out to be **already approved** in an unread
  directive. §7.
* All four session instruments **EXIT 0**; margins **21/21/0**. §9.

## 1. WHAT I GOT WRONG, STATED FIRST

I was told a settled-but-ungraded lone claim had no rung to catch it. I believed
it, built a rung, and both the fixture I wrote and the guards I wrote agreed with
me — because I had constructed a database state that **does not exist in
production**. The cert found it by asking a question I never asked: *which column
does this repository already use to mean "graded"?*

The lesson is not "measure more". It is that **CAL-P155 and I both inherited a
premise and neither of us checked it**, and a fixture built from that premise
cannot falsify it.

## 2. CERT-514 — the block that was right

> The SQL counts lone claims per market but admits them through one
> variant-level `clean_vms` row with `ungraded_lone_claims = 0`; one ungraded
> sibling therefore still suppresses an independently graded claim.

Admission is variant-grained — `ranked_outcomes` joins ONE `clean_vms` row per
variant — so a conjunct in the arm can only refuse a whole variant. CAL-P155 had
named this residue and deferred it to "its own queue"; the cert ruled **the
deferral was itself the finding**. Not disputed.

## 3. CERT-520 — THE MEASUREMENT THAT SETTLED IT

My repair moved the refusal "down a grain" into a new rung keyed on
`is_winner IS NULL`. The cert's [P2] said that is the wrong authority signal and
that my fixture manufactured the only state exercising it. Measured against
production, over **3,893,126** outcomes:

| `is_winner IS NULL` | `resolution_source IS NULL` | rows |
|---|---|---|
| False | False | 3,112,284 |
| False | **True** | **778,306** ← the real "nobody graded this" |
| **True** | True | 2,536 |
| **True** | **False** | **0** ← the shape my fixture seeded |

Three consequences, none of them arguable:

1. **The real ungraded row is `is_winner = false, resolution_source = NULL`**,
   not `is_winner = NULL`. That is why the canonical predicate is
   `calibration_graded_share.GRADED_PREDICATE = "fo.resolution_source IS NOT
   NULL"` — whose own comment warns that *"two definitions of one quantity is the
   contradiction machine this lane has now found three times."* **Mine would have
   been the fourth**, in the same module family.
2. **Every one of the 2,536 NULL-winner rows also has a NULL source**, and
   `ranked_outcomes` already filters `resolution_source IN <eligible>`
   (`precompute_calibration.py:2952`). So **rung 1b could never fire.** Dead
   code, and its payload census would have published a permanent zero while the
   778,306-row cohort was excluded elsewhere.
3. **My PG fixture seeded a state with ZERO production instances** —
   `is_winner=NULL` *with* `resolution_source='api_settlement'`, a row claiming
   an authority settled the market while withholding the verdict. `_seed_leg`
   hardcoded the source, so the contradiction was invisible.

**And the premise underneath both CAL-P155 and CAL-P156 was false.** "A
single-outcome member nothing ever graded has NO rung" — it has one, and always
did: truth eligibility.

`CERT-520`'s **[P1]** was my own stale oracle: `_reverted` swaps the D5 JOIN and
nothing else, so the ungraded leg is refused by eligibility on *both* sides;
asserting `== set(ASYM_IDS)` demanded a row no arm of that test can produce, and
CI went red 1/7 at the exact head. Now `ASYM_REACHABLE`, named so that "what
eligibility admits" and "what the rungs publish" cannot be conflated again.

## 4. WHAT THE FIX ACTUALLY IS

```
$ git diff 70518c0d HEAD -- backend/app/tasks/precompute_calibration.py \
    | grep -E '^[+-]' | grep -v '^[+-][+-]' | grep -vE '^[+-]\s*(--|#)'
-                        OR (graded_lone_claims >= 1
-                            AND ungraded_lone_claims = 0)
+                        OR graded_lone_claims >= 1
```

One line. Everything else in the producer diff is comments that now tell the
corrected story, including a standing **"do not re-add it"** note on the rung
with the measurement attached.

Reverted from my first attempt: the rung 1b CTE, `graded_count`, the
`is_ungraded_lone_claim` flag, the LEFT JOIN, all three applications, the
counters, the payload key, the rule text, and the pure-function mirror. The
fingerprint totals return **55/51 → 54/50** — recorded in the pin's docstring
rather than erased, because a tripwire that only ever ratchets up teaches the
next reader that coming back down is suspicious.

Also corrected (found by §6's audit): `precompute_calibration.py` asserted
`is_winner` is **NOT NULL** 1,169 lines above the arm that depends on it being
nullable. The replacement carries the measurement rather than the opposite
over-correction.

## 5. GATES AND MUTATION

| gate | result |
|---|---|
| calibration slice | **3,476 passed / 31 skipped, EXIT 0** |
| ruff, changed files · `git diff --check` | clean |
| merge-tree vs master `1f0cf419` | **EXIT 0**, no conflicts |
| full suite (merged tree) | §10 |
| **real-Postgres vm-variant gate** | 🔴 cannot run locally (`initdb` fails on shmget) — CI's `search-recall` job is the only place it runs, **and it is what caught [P1]** |

**Mutation battery, re-aimed at the guards that now exist — 5/5 KILLED**, each
proving it applied by sha256 move, final restore verified:

| mutation | guard |
|---|---|
| M1 restore the residue conjunct | 4b — the CERT-514 defect returns |
| M2 re-add a rung on `is_winner IS NULL` | 4c — the CERT-520 dead code returns |
| M3 delete truth eligibility from `ranked_outcomes` | 4c — the filter that *actually* excludes ungraded rows |
| M4 widen rung 1 to `n_outcomes >= 1` | rung-1 floor |
| M5 restore option-B per-variant counts | 4b — Alex's ruling reversed |

M2 and M3 are the pair that encodes §3: the fix is safe **because** the allowlist
is there, and it must not be "helped" by a rung that cannot fire.

**From the first battery, still worth carrying:** my original clause 4c was
`assert "NOT ro.is_ungraded_lone_claim" in sql`, and the flag was applied in
three places — deleting the one that gated the published curve left the guard
**GREEN on its siblings** (`M3a … SURVIVED exit=0 | 46 passed`). The harness also
refused an ambiguous anchor (`matched 3 times, expected 1 — NOT APPLIED`) rather
than mutating an arbitrary site. Had it picked one, a vacuous guard would have
shipped behind a green battery.

## 6. THE PG-GATE NULLABILITY AUDIT — NEGATIVE

Directive item 3. Gates that build schema with `Base.metadata.create_all` **and**
touch `is_winner`: **ten**. Eight make no nullability claim at all (measured,
grep count 0). The ninth,
`tests/integration/test_futures_price_refresh_writes_pg.py`, *does* — and is
clean: it states the model/production disagreement outright at lines 339–353 and
asserts the three-valued semantics as a **SQL truth table** rather than inserting
NULL, "because a test that inserted NULL would pass or error depending on which
schema it met". The tenth is CAL-P155's, already fixed.

**Exposure was one file and it was already closed.** That is what let Alex's ORM
decision be made on measured blast radius instead of suspicion.

## 7. THE ORM QUEUE — AUTHORISED, AND THE DIRECTIVE WAS UNREAD

`runner-inbox/calibration/910-orm-is-winner-nullable.md` was **unconsumed**:
Alex had already approved the widening "in ITS OWN queue". Its number sorts
*below* the working sequence, which is the same reason `950-top-defects-law.md`
sat unread for four sessions. **A directive numbered below the current sequence
is invisible to a lane that takes "the next NNN".**

Done on `program/calibration-120-orm-is-winner-nullable` @ `b3e46d34`, off master,
fast-forward: `is_winner: Mapped[Optional[bool]] = mapped_column(Boolean,
nullable=True, default=False)`. Full suite **24,295 passed / 0 failed**,
**`PYTEST EXIT CODE: 0` captured**. Mutation 3/3 KILLED. Staged as **`CERT-521`**.

🔴 **A SECOND DRIFTED COLUMN, FOUND BY NOT ASSUMING.** I compared the whole table
rather than only the column I was sent for:

```
production NOT NULL : external_id, id, market_id, name
model      NOT NULL : external_id, id, last_updated, market_id, name
```

**`last_updated` has the same drift and is deliberately untouched** — Alex
authorised `is_winner`, nothing depends on `last_updated` being absent, and
widening it retypes every reader of a timestamp for no named ship. Recorded in
the guard's ledger so it cannot read as agreement.

## 8. WHAT IS STILL NOT PROVED

* **The population change is unsized.** Removing the conjunct admits graded lone
  claims that shared a variant with an ungraded one. Unmeasured: CERT-514's own
  bounded attempt hit the 10 s statement timeout, prod Postgres is at 103% of
  plan, and censuses belong to the measurement lane (ruling 134). Parked with
  exact queries in `PARKED-MEASUREMENTS.md`. **No green confirms a number.**
  *(The removal side is now known to be nil — rung 1b is gone, so nothing is
  newly excluded.)*
* **The real-Postgres gate rests on CI.** It is the gate that caught [P1]; treat
  a local green as silence, not evidence.
* **`ungraded_lone_claims` (the vm_stats column) has no producer consumer.** Kept
  because the census script still reports it. CAL-P155 added it; not mine to
  remove, and now demonstrably near-zero within the eligible population.

## 9. INSTRUMENTS

| instrument | pids | last cycle (UTC) | state |
|---|---|---|---|
| `CAL-P147-RENDER-BANKER` | 75909 / 75911 | 01:36:36Z | `already_banked`, 15 censuses |
| `CAL-P148-SERVE-PHASE-PROBE` | 37525 / 37527 | 01:38:51Z | 27 samples |

All four session instruments **EXIT 0**: board-d15 (every 2026-08-30 cell present
and placed) · promotion-datapoint (**HELD** 1.88 / q268) · refusal-register (13 of
20 live seats under a documented refusal) · window-beat-margins (**21 gauged / 21
agree / 0 disagree**, tightest CLEAN beat 2,691 ms). Nothing added to
`PERMANENTLY_UNREADABLE`. **Nothing deployed** — directive items 4 and 6 stay
correctly ungated.

## 10. FULL SUITE

Run on the **merged tree** against master `1f0cf419` (rule 3), not the branch
alone. Result appended on completion.

Earlier runs this session: merged tree @ `9112cbbd` **24,465 passed / 0 failed**;
ORM branch **24,295 passed / 0 failed, EXIT CODE 0 captured**.

⚠️ The first launch of the day never ran: `--CAL-P156-FULL-SUITE-TOKEN` is not a
pytest flag and the process died instantly. **The tell was `pgrep` returning 0,
not the log.** `-o cache_dir=…` already carries a lane-unique token *and* is a
real flag. Later runs were wrapped so the runner echoes its own `$?` as the last
line, which is how the ORM run has a captured exit code and the earlier ones do
not.

## 11. LESSONS

* **(CAL-P156) Ask which column the repository already uses before adding a
  predicate that means the same thing.** `GRADED_PREDICATE` existed, with a
  comment warning that duplicate definitions had already bitten this lane three
  times. I did not look, and built the fourth.
* **(CAL-P156) A fixture you wrote from a premise cannot falsify that premise.**
  Mine seeded a state with zero production instances, so every guard over it
  agreed with me. The fix is not more guards — it is one query against the real
  distribution before designing the predicate.
* **(CAL-P156) "There is no rung for this" is a claim about the whole chain, and
  a WHERE clause is a rung.** Truth eligibility had been excluding the entire
  class the whole time, one CTE upstream of where I was looking.
* **(CAL-P156) A red-first that exits early proves nothing about the assertions
  behind it.** Mine died on clause 3 of a nine-clause helper; clauses 4b/4c were
  never reached. Check WHICH assertion fired.
* **(CAL-P156) A containment check over a whole SQL chain cannot see which call
  site it matched** — three occurrences, deleting the load-bearing one left the
  guard green. Anchor on the CTE that gates the output.
* **(CAL-P156) A mutation harness must refuse an ambiguous anchor**, or it will
  mutate a harmless site, report KILLED, and certify a vacuous guard.
* **(CAL-P156) A directive numbered below the working sequence is invisible.**
  `910` and `950` both sat unread for exactly that reason.
* **(CAL-P156) Compare the whole table, not the column you were sent for.**
  `last_updated` was drifted too, and only a full comparison would ever say so.
