# CAL-P156 — the state

Pillar **TRUTH**. Issue **#1978**. Branch `program/calibration-119`.
Ship: **a settled market that our own data graded stops being withheld from the
calibration curve because an ungraded market happened to share its variant.**

## 0. TL;DR

* `TOP-PRODUCT-DEFECTS.md` has **no `[calibration]` item** — rule 1 gives this
  lane nothing, so the directive queue was the work.
* 🔴 **`CERT-514` CAME BACK BLOCK (01:46Z), AND IT WAS RIGHT.** [P1]: the arm
  counted per market but still consumed the counts in ONE variant-grained
  `clean_vms` row requiring `ungraded_lone_claims = 0`, so one ungraded sibling
  went on suppressing an independently graded claim. **The finding is the work
  (directive item 2) — reworked, not argued.**
* **The repair is a change of GRAIN: new Queue 299 rung 1b.** The
  `ungraded_lone_claims = 0` conjunct is gone from the arm; unknown truth now
  leaves at the market that holds it. §2.
* **Directive item 3's audit half is DONE, answer NEGATIVE** — §1. No PG gate
  anywhere ever proved a nullability behaviour against a NOT NULL column; the
  exposure was one file and CAL-P155 had already closed it.
* **A wrong premise in the shipping module, found by that audit and now fixed**
  — `precompute_calibration.py` asserted `is_winner` is NOT NULL 1,100 lines
  above the arm that depends on it being nullable. §3.
* **My own new guard was vacuous and the battery caught it** — §5. A containment
  check satisfied by a SIBLING call site; deleting the one that gates the
  published curve left it green.
* All four session instruments **EXIT 0**; margins hold **21/21/0**. §7.
* 🔴 **The population change is UNSIZED and that is declared, not hidden.** §6.

## 1. THE PG-GATE NULLABILITY AUDIT — ASKED AND ANSWERED, NEGATIVE

Directive item 3 left open: *"The other PG gates are NOT audited for this — if
any ever 'proved' a nullability behaviour, it proved it against a column that
could not be null."*

**Population.** Gates that (a) build schema with `Base.metadata.create_all` —
which renders `is_winner` **NOT NULL** from the non-Optional `Mapped[bool]` at
`models.py:849` — **and** (b) touch `is_winner`. That intersection is **10
files**, enumerated by command:

```
tests/integration/test_calibration_mode_price_source_scope_peers_pg.py
tests/integration/test_calibration_mode_price_source_scope_pg.py
tests/integration/test_calibration_vm_variant_join_pg.py      <- CAL-P155 fixed this one
tests/integration/test_futures_price_refresh_writes_pg.py
tests/integration/test_kalshi_cliff_bind_contract.py
tests/integration/test_search_recall_contract.py
tests/test_calibration_canonical_pg.py
tests/test_calibration_examples_canonical_262.py
tests/test_calibration_horizon_honest_263.py
tests/test_calibration_horizon_population_262.py
```

**Verdict.**

* **Eight of the ten make no nullability claim at all.** Measured:
  `grep -c "is_winner IS NULL\|is_winner IS NOT NULL\|is_winner.*None\|ungraded"`
  returns **0** for each. They seed explicit `true`/`false` and assert winner
  *counts*, never winner *knownness*.
* **`test_futures_price_refresh_writes_pg.py` DOES make nullability claims — and
  it is CLEAN.** Its lines 339–353 state the disagreement outright and it
  therefore asserts the three-valued semantics **as a SQL truth table** rather
  than by inserting NULL, "because a test that inserted NULL would pass or error
  depending on which schema it met". That is the correct call.
* **`test_calibration_vm_variant_join_pg.py`** already carries CAL-P155's
  `_match_production_is_winner_nullability()`.

**So the exposure was exactly one file and it was already closed.** Corroborating
narrowness: the only tests referencing the D13 columns at all are
`test_calibration_lost_losses_12cal.py`,
`test_calibration_missing_loser_census_p122.py` and the PG gate — there is no
second place `ungraded_lone_claims` could have been faked green.

**The model-widening half remains Alex's call** (`alex-inbox/calibration-920`)
and is untouched. This audit is what lets that decision be made on its merits
instead of under a suspicion of unknown blast radius.

## 2. THE CERT-514 REWORK — RUNG 1b

### What the cert found

> The SQL counts lone claims per market but admits them through one
> variant-level `clean_vms` row with `ungraded_lone_claims = 0`; one ungraded
> sibling therefore still suppresses an independently graded claim.

Correct, and CAL-P155 had documented the residue as a deliberate choice — "closing
it properly needs a per-market rung and its own queue; it is not smuggled in
here." The cert ruled that the ruling does not permit deferring it. **A narrower
version of the coupling option A removes is still that coupling.**

### The repair

The refusal was never wrong — its **grain** was. Admission is variant-grained
(`ranked_outcomes` joins ONE `clean_vms` row per variant), so a conjunct in the
arm can only ever refuse a whole variant.

**Rung 1b, `ungraded_lone_claim_markets`:**

```sql
ungraded_lone_claim_markets AS (
    SELECT mrs.market_id
    FROM market_result_shape mrs
    WHERE mrs.n_outcomes = 1 AND mrs.graded_count = 0
),
```

fed by a new per-market column,
`COUNT(*) FILTER (WHERE fo.is_winner IS NOT NULL) AS graded_count` — an
**affirmative** grade count, deliberately not `n_outcomes - win_count`, which for
a single-outcome market is identically ≥1 and would make the rung dead.

**Why rung 1 could not just be widened:** it requires `n_outcomes >= 2` on
purpose. At one outcome "nobody won" is the *ordinary* result of a claim that
resolved No, so winner cardinality stops discriminating and only an affirmative
grade can. Rung 1b is rung 1's complement, not its extension — pinned by a guard
that fails if rung 1's floor ever drops to `>= 1` (battery M6).

**The arm loses its conjunct:** `OR graded_lone_claims >= 1`, alone.

The two halves are a **pair**, and every guard asserts them together: clause 4b
(the residue is absent) without clause 4c (rung 1b exists, keys on
`graded_count`, and is applied) would be a straight relaxation that publishes
unknown truth as confident losses.

### Wiring (the full list, so nothing is half-applied)

| site | change |
|---|---|
| `market_result_shape` | `+ graded_count` |
| new CTE | `ungraded_lone_claim_markets` |
| `ranked_outcomes` | `+ is_ungraded_lone_claim` flag, `+ LEFT JOIN` |
| `field_completeness` | `AND NOT ro.is_ungraded_lone_claim` ×2 (survivor_n, survivor_win_n) |
| `deduped` | `AND NOT ro.is_ungraded_lone_claim` — **the publish filter** |
| `_COVERAGE_RUNG_PREDICATES` | added to `malformed_or_unknown_truth` |
| counters + payload | `ungraded_lone_claim_filter` (own key, not folded into rung 1's) |
| `clean_vms` | `ungraded_lone_claims = 0` **removed** |
| `scripts/calibration_missing_loser_census.py` | mirror + `kept_lone_sql` moved in lockstep |

The census mirror matters: its own guard says *"if it still reads the retired
per-variant counts the two halves of this census are two different
populations"*. `lone_claim_is_restorable` and `classify_vm` went single-argument
— the boundary genuinely lost a dimension, and making the signature lie about
that would leave every call site silently still passing.

## 3. THE PRODUCER CONTRADICTED ITSELF ABOUT `is_winner` — FIXED

Found by §1's audit, one directory over from where it was told to look.
`precompute_calibration.py` stated **both** facts, 1,169 lines apart:

* **line 1413** (rung 1's explanation): *"``is_winner`` is **NOT NULL** with a
  False default"*
* **line 2582** (the 12-CAL `graded` column): *"``is_winner`` is **nullable**
  with a False default"*

Production is `is_nullable = YES, column_default = false`. Line 1413 was wrong,
and it was the exact inverse of the fact rung 1b and the `graded` column rest on.

**Nothing behaved wrongly** — rung 1 is NULL-safe by construction
(`win_count = COUNT(*) FILTER (WHERE is_winner = true)` does not count NULL) —
but a reader reasoning from line 1413 would conclude `ungraded_lone_claims` is
identically zero and rung 1b is dead code. Corrected in place, with the
correction and its reason stated rather than silently overwritten.

## 4. GATES

| gate | result |
|---|---|
| `tests/test_startup.py` | 4 passed |
| calibration slice (`-k "calibration or ladder or cohort or resolution or bookmaker"`) | **3,476 passed / 31 skipped, EXIT 0** |
| ruff, changed files | clean |
| `git diff --check` | clean |
| full suite | see §8 |
| **real-Postgres vm-variant gate** | 🔴 **cannot run locally** — no local Postgres in the sandbox (`initdb` fails on shmget). Runs in CI's `search-recall` job. §6. |

## 5. RED-FIRST, AND THE GUARD THAT WAS VACUOUS

### The revert proves less than it looks like it does

Producer reverted to `HEAD`, **verified by sha256** (`27865e4d…` requested,
`27865e4d…` applied), tests unchanged: **4 failed / 62 passed, EXIT 1**.

🔴 **But it fails on `RESTORED_ARM_SQL in gate`, the FIRST assertion in
`assert_repaired_population`** — so clauses 4b and 4c are never reached and the
whole-file revert proves **nothing** about the new guards. A red-first that
exits early is evidence about the assertion that fired, not about the ones
behind it. That is why the battery below exists rather than being a formality.
Restored, verified by sha256.

### The battery — one mutation per guard, each proving it applied

| mutation | guard it must kill | result |
|---|---|---|
| M1 restore the residue conjunct | 4b — residue back in the arm | KILLED |
| M2 delete rung 1b's CTE | 4c — rung does not exist | KILLED |
| M3a stop applying it in **`deduped`** | 4c — not applied to the published curve | KILLED *(after fix)* |
| M3b stop applying it in `survivor_n` | 4c — partial field normalizes over survivors | KILLED |
| M4 key rung 1b on `win_count` | 4c — eats every honest lone No | KILLED |
| M5 derive `graded_count` arithmetically | 4c — rung can never fire | KILLED |
| M6 widen rung 1 to `n_outcomes >= 1` | rung-1 floor — swallows the carve-out | KILLED |

**7/7 KILLED**, final restore verified by sha256.

### 🔴 M3a FAILED FIRST, AND THAT IS THE MOST USEFUL THING IN THIS SECTION

My clause 4c was written `assert "NOT ro.is_ungraded_lone_claim" in sql`. The
flag is applied in **three** places. Deleting the ONE that gates the published
curve — `deduped` — left the assertion **GREEN on its two siblings** in
`field_completeness`. Measured: `M3a … 🔴 SURVIVED exit=0 | 46 passed`.

The battery also refused to run M3 at all on the first pass — *"anchor matched 3
times, expected 1 — NOT APPLIED"* — rather than mutating an arbitrary one of
them. A mutation harness that silently picks a site produces a green that means
nothing.

Re-anchored on `_cte_body(sql, "deduped")`, with a separate count-2 assertion for
`field_completeness` so one site is never evidence about the other. **Only
mutation caught this**; the tests were green and the reasoning read fine.

⚠️ **The pre-existing `NOT ro.is_no_winner_market` assertion has the identical
weakness** and is left as found — noted for the grader, not silently widened.

## 6. WHAT IS NOT PROVED HERE — READ THIS BEFORE GRADING

* 🔴 **THE POPULATION CHANGE IS UNSIZED.** Two movements ship together and
  neither is measured: rows ADMITTED (graded lone claims freed from an ungraded
  sibling) and rows REMOVED (every ungraded lone claim, including ones already
  publishing in variants admitted via `has_winner >= 1` — a pre-existing hole
  rung 1b closes as a consequence of applying the refusal at market grain, which
  is what the cert's fix-sketch asked for). **Not measured on purpose**:
  CERT-514's own bounded attempt hit the endpoint's 10-second statement timeout,
  production Postgres is at 103% of plan, and censuses belong to the measurement
  lane under ruling 134. **A GREEN here must not be read as confirming any
  number.** Staged for the measurement lane; see §9.
* 🔴 **THE REAL-POSTGRES GATE HAS NOT RUN.** `initdb` fails in this sandbox, so
  every data-level claim about rung 1b — the SPLIT itself — rests on CI's
  `search-recall` job. The two new tests there are the load-bearing ones.
* **The rung-1b attribution test is deliberately separate.**
  `test_the_mixed_variant_publishes_only_its_graded_member` asserts the ungraded
  row is absent — but *refusing the whole variant* also makes it absent, so that
  test alone cannot distinguish the repair from the thing it replaced.
  `test_rung_1b_is_what_removes_the_ungraded_member_not_the_arm` reads the flag
  directly. Grade them as a pair.
* **`ungraded_lone_claims` (the vm_stats column) now has no consumer in the
  producer.** Kept because the census script still SELECTs and GROUPs it for
  reporting. Judgement call, flagged.

## 7. INSTRUMENTS

Both background processes alive, advancing, zero restarts:

| instrument | pids | last cycle (UTC) | state |
|---|---|---|---|
| `CAL-P147-RENDER-BANKER` | 75909 / 75911 | 01:36:36Z | `already_banked`, 15 censuses |
| `CAL-P148-SERVE-PHASE-PROBE` | 37525 / 37527 | 01:38:51Z | 27 samples |

Session instruments, all **EXIT 0**:

| instrument | result |
|---|---|
| `cal-p150/board-d15.py` | every cell in the 2026-08-30 batch present and placed |
| `cal-p146/promotion-datapoint.py` | headline **HELD** 1.88 / q268; beat 14 permanently unreadable, unchanged |
| `cal-p145/refusal-register.py` | 13 of 20 live seats under a documented refusal |
| `cal-p144/window-beat-margins.py` | **21 gauged / 21 agree / 0 disagree**; tightest CLEAN beat 19 at 2,691 ms |

Nothing added to `PERMANENTLY_UNREADABLE`. **Nothing deployed**, so the headline
is untouched and directive items 4 and 6 stay correctly ungated.

## 8. FULL SUITE — RUN ON THE MERGED TREE, NOT THE BRANCH

Rule 3 asks for a merge onto current master before staging. Rather than run the
branch alone and merge afterwards, the merged tree was materialised first and
**everything below was run on it** — it is what actually ships.

```
merge-tree --write-tree origin/master HEAD  -> 0fcbddc2, EXIT 0, no conflicts
materialised at /tmp/CAL-P156-merged (detached worktree, probe commit deecb126)
```

| gate, ON THE MERGED TREE | result |
|---|---|
| pinned gates (12cal, p122, fingerprint ×2, result-authority-299, route-calibration, **pg-gate-seed-completeness**, startup) | **208 passed, EXIT 0** |
| **full suite** | **24,465 passed · 0 failed · 138 skipped · 61 xfailed**, 1084 s |

`grep -cE "^(FAILED|ERROR)"` over the full log returns **0**.

⚠️ **`$?` was not captured** — the run was backgrounded with `nohup` and the pid
had exited before the exit code could be read. The zero-failure summary line and
the zero FAILED/ERROR grep are the evidence; the exit code itself is not. Same
caveat CAL-P155 carried. *Fix for next time: wrap the backgrounded suite so it
echoes its own `$?` into the log as its last line.*

⚠️ **The first launch never ran at all.** It used
`--CAL-P156-FULL-SUITE-TOKEN` as a lane-unique argv token and pytest **rejected
it** (`error: unrecognized arguments`). The tell was `pgrep` returning 0 — the
log's last lines looked like an ordinary header. `-o cache_dir=…` already carries
a lane-unique token in argv **and is a real flag**; use that, and check `pgrep`
after every background launch rather than the log.

**File intersection with master since merge-base** (both sides touched):
`.github/workflows/ci.yml`, `app/tasks/__init__.py`, `app/tasks/backfill_winners.py`,
`tests/test_pg_gate_seed_completeness.py` — all from earlier commits in the
calibration-119 stack, none from CAL-P156. `test_pg_gate_seed_completeness.py`
is in the pinned set above **because** it intersects, and it passes on the merge.

## 9. FOR THE MEASUREMENT LANE

**Size rung 1b's two movements** (this is the ship's before/after, deferred):

1. `n_outcomes = 1 AND graded_count = 0` markets, resolved and otherwise
   eligible → the rows rung 1b REMOVES.
2. Of those, how many sit in a variant admitted via `has_winner >= 1` → the
   pre-existing hole closed as a side effect, which is the part nobody asked for
   and everybody should see.
3. Graded lone claims sharing a variant with ≥1 ungraded lone claim → the rows
   the repair ADMITS, i.e. the CERT-514 finding's actual size.

Chunk it; the naive form times out at 10 s. `artifacts/cal-p151/cricket-
population-fold.py` has the rail. **`mod(key, N)` sharding is not sargable** —
range-partition on the key's own index (CAL-P155).

## 10. LESSONS

* **(CAL-P156) A red-first that exits early proves nothing about the assertions
  behind it.** Mine died on clause 3 of a nine-clause helper and I nearly banked
  it as evidence for clauses 4b and 4c. Check WHICH assertion fired, and mutate
  per guard when the answer is "the first one".
* **(CAL-P156) A containment check over a whole SQL chain cannot see which call
  site it matched.** Three occurrences, one of them load-bearing; deleting the
  load-bearing one left the guard green. Anchor on the CTE that actually gates
  the output, and assert the others separately with their own message.
* **(CAL-P156) A mutation harness must refuse an ambiguous anchor.** M3 matched 3
  sites and reported `ANCHOR-MISS` instead of picking one. Had it picked, it
  would have mutated a `field_completeness` site, come back KILLED, and I would
  have shipped the vacuous guard with a green battery behind it.
* **(CAL-P156) An audit that comes back empty is still the deliverable** — and
  its real find may be next door. §1 cleared all ten gates; the actual damage
  from that same drift was a wrong premise in the shipping module (§3).
* **(CAL-P156) "It needs its own queue" is not a disposition a cert has to
  accept.** CAL-P155 named the residue, argued it, and deferred it; the cert
  ruled the deferral was itself the finding. Scope a fix by the RULING, not by
  what is comfortable to finish.
