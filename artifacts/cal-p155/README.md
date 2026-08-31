# CAL-P155 — two lone claims stopped being one refusal

**Pillar: TRUTH. Ship: a market the venue graded a LOSS stops being deleted from
the accuracy score for having a sibling that also lost.**

This file is the state for THIS session only. `artifacts/cal-p154/README.md` is
the state for the `CERT-457` repair; `cal-p153`'s for the window and the
supervisor finding; `cal-p152`'s **§7** for the twelve code commits beneath them;
`cal-p151`'s for the nine under those; `cal-p150`'s for the five original.

---

## TL;DR

1. **Alex ruled option A and it is built.** D13's admission arm counts PER
   MARKET: `graded_lone_claims >= 1 AND ungraded_lone_claims = 0`. Two
   independently-graded lone claims sharing a virtual variant each publish. §1.
2. 🔴 **A GUARD FAMILY WAS VACUOUS AND THE FIRST TEST RUN FOUND IT** — every
   assertion about the arm was being made against SQL **with its comments still
   in**, and an arm's comment block necessarily quotes the predicate it explains.
   Broken in both directions at once. §3.
3. **Red-first 3F/44P EXIT 1; mutation battery 6/6 caught; full suite 22,179
   passed / 0 failed.** §4.
4. **Cricket's ingestion fix is DESIGNED and the specimen is now READ, not
   inferred** — 129934 is a container with **zero** sub-market rows ever minted.
   §5, and `DESIGN-polymarket-container-outcomes.md`.
5. **The population bound is measured: ≤8,073 markets of 862,435 — at most
   0.94%, both tilings reconciled exactly.** Option A is a small, bounded change.
   The HEADLINE stays a post-deploy reading. §6.
6. 🔴 **CI found two things the local suite structurally could not**, and one is
   a schema drift: the ORM declares `is_winner` NOT NULL and production has it
   nullable, so **no metadata-built test database in this repo can represent
   "nobody graded this"** — the exact distinction 12-CAL rests on. §9.

---

## 1. The ruling, and the arm

`alex-inbox/calibration-919` put one decision to Alex with a stated default. The
default (option B, per-variant) was taken by CAL-P151 when he had not replied.
He replied: **option A, per-MARKET**, "each independently-graded lone claim
publishes on its own even when two land in the same virtual variant", chosen
knowingly over the lane's own recommendation with the population cost declared
UNMEASURED.

The retired arm read `market_count = 1 AND total_outcomes = 1 AND graded >= 1`.
Those are `vm_stats` columns and `vm_stats` groups per VARIANT, so two lone
claims in one variant carried `market_count = 2` and the arm refused both — while
`has_winner = 0` closed the other arm. Each row is individually what D13's own
comment calls *"a complete, scoreable prediction"*. **They were excluded only
because they were counted together.**

`vm_stats` gains two PER-MARKET columns over
`market_result_shape.n_outcomes = 1` — the same as-captured outcome count Queue
299 rung 1 uses, so "lone claim" means one thing in both places — and the arm
reads them.

## 2. The one thing in this change most likely to be wrong

**`ungraded_lone_claims = 0` is a fail-closed residue of the same coupling the
ruling removes, and it is deliberate.**

Admission is variant-grained: `ranked_outcomes` joins ONE `clean_vms` row per
variant, so admitting a variant admits every member's outcomes. In a variant this
arm admits, `has_winner = 0`, so:

* members with `n_outcomes >= 2` all have `win_count = 0` and
  `no_winner_markets` drops them — rung 1, doing exactly its job;
* single-outcome members that were **graded** are the lone claims, and they
  publish — the ruling;
* a single-outcome member nothing ever **graded** has **no rung at all**. Rung 1
  requires `n_outcomes >= 2` on purpose. It would publish as a confident loss off
  `is_winner`'s False default (gotcha #21).

So the arm refuses that whole variant, and a graded claim sitting beside an
ungraded one is still held back. That is the per-variant coupling again, on a
strictly smaller population, in the safe direction: refusing a scoreable row
costs coverage, publishing unknown truth as a loss corrupts the curve. **Closing
it properly needs a per-market rung and its own queue.** It is written into the
SQL, the tests and the cert rather than left to be discovered.

## 3. 🔴 The guards were being made against the documentation

`_cte_body` — the helper the CAL-P122 suite added precisely so a predicate is
pinned to its own clause — returned the RAW slice of the CTE, comments included.
An arm's comment block has to quote the predicate it is explaining, and this one
quotes both the shipped predicate and the retired one. So:

* `assert "ungraded_lone_claims = 0" in gate` was satisfiable by **the paragraph
  arguing for it**, whether or not the SQL carried it — a presence guard that
  could never fail;
* `assert "market_count = 1" not in gate` **FAILED against a correct
  implementation**, because the comment says what the retired arm used to read.

One cause, both directions, and the second one is what surfaced it: the first run
of the new suite came back red on a producer that was already right.

Fixed by stripping comments with the repo's own `app.utils.sql_comment_strip`
(#2076's tool — it knows a `--` inside a string literal is data and that block
comments nest, which a regex does not). Every assertion is now over what
EXECUTES. Same fix applied to the CAL-P122 census guard.

**This is CAL-P154's lesson one session later in a different disguise.** That one
was a containment check satisfied by sibling call sites; this one is a
containment check satisfied by prose. The general form: *a guard that reads
source text is only as good as its answer to "which bytes actually run".*

## 4. Evidence

| gate | result |
|---|---|
| full backend suite @ `c845cb26` | **22,179 passed / 0 failed / 129 skipped / 61 xfailed**, 909.17 s |
| red-first (producer reverted to `f90bb593`) | **3 failed / 44 passed, EXIT CODE 1** |
| mutation battery | **6/6 caught**, each mutation proved applied by hash, source restored by hash |
| focused 3 files @ head | 47 passed / 5 skipped **EXIT CODE 0** |
| `-k "calibration or bookmaker or ladder"` | 3,091 passed / 29 skipped **EXIT CODE 0** |
| `test_startup` | 4 passed **EXIT CODE 0** |
| ruff | clean, exit 0, on all five changed files and both new artifact scripts |
| fingerprint derived map | only `source_sha256` moved — `uncovered_sql_shaping` **22**, `covered_by_value` **4**, `input_count` **54**, every per-input row identical |

⚠️ **The full suite's `$?` was NOT captured** — it was backgrounded so the host's
three concurrent suites did not serialise. Its summary line is complete and reads
0 failed, which entails exit 0 (gotcha #124's failure modes — 2/3/4/5, 127, 137,
143 — all abort *before* a summary line is printed). Stated rather than claimed:
the graded exit codes above are the ones actually captured. Baseline was 22,173
at `7b401286`; **+6** is this session's net new tests.

🔴 **THE PG GATE DID NOT RUN LOCALLY AND CANNOT.** Those are the 5 skipped —
`test_calibration_vm_variant_join_pg.py` skips without
`SEARCH_TEST_DATABASE_URL`, and there is no local Postgres in this sandbox. **The
inverted fixture and its new third variant are proved only by CI.** Branch pushed
`f90bb593..c845cb26`, `origin` verified EQUAL by SHA; `CI`, `CodeQL` and
`gitleaks` all triggered on the exact head via the standing draft PR **#2346**.

**The mutations, and why each is a plausible wrong reading of the ruling:**

| # | mutation | caught |
|---|---|---|
| M1 | drop the fail-closed conjunct | ✅ |
| M2 | revert the arm to per-VARIANT (option B) | ✅ |
| M3 | keep BOTH arms in an OR — the "safe" partial revert | ✅ |
| M4 | count lone claims per VARIANT (`COUNT(*)` for `COUNT(DISTINCT market_id)`) | ✅ |
| M5 | drop the `market_result_shape` join | ✅ |
| M6 | make that join INNER (ruling 125: it could then delete a row) | ✅ |

## 5. Cricket: the specimen is read, and the design is banked

CAL-P151 named the cause (gotcha #18 unapplied) and correctly said it could not
tell which ingestion branch produced it. **That read is now done**, and it
settles the question the design needed:

`futures_markets` 129934 carries `external_id = '208556'` and
`group_id = 'polymarket:208556'` — a PARENT row keyed on the Gamma EVENT id —
with `mutually_exclusive = false` (so a non-negRisk game container),
`market_type = 'field'`, `group_type` **NULL**, no `neg_risk`/`market_count` in
`market_metadata`, and 🔴 **exactly one row under that `group_id`: itself.**

**Zero sub-markets were ever minted.** The three sibling questions exist ONLY as
outcome rows on the container, each settling YES on its own account, because the
winner writer keys on the bare `condition_id` and the container's outcomes are
keyed on exactly that. Three winners on one market, by construction — and
invisible to every rung, because `mutually_exclusive` is false and both
coherence rules and `malformed_binaries` are gated on it.

The full design — mechanism end to end, the three-part fix with F1 as the ship,
the missing guard, the census and its rail traps, and four open questions a
builder must answer rather than assume — is
**`DESIGN-polymarket-container-outcomes.md`**. It is DESIGN ONLY: nothing is
built, `app/tasks/polymarket.py` is untouched, and it is an INGESTION ship that
belongs to an ingestion queue with its own ship line.

**It is OUR bug and the design says so in those words.** No "bad at cricket"
label appears anywhere in it and none may be derived from it.

## 6. The population delta — a bound, and what it cost to get

Alex accepted "unmeasured" going in and is owed the number coming out. Two
different numbers, and only one of them is available before a deploy:

* **The HEADLINE delta is a POST-DEPLOY reading.** This branch's own standing
  rule, unchanged since CAL-P150: nothing is deployed, the board still reads
  **1.88 pp on q268**, and a pre-lift reading published as the headline would be
  the defect wearing the repair's name. It is read the moment the lift deploys,
  by `artifacts/cal-p150/board-d15.py` plus one read of `/api/calibration`.
* **The POPULATION bound is measurable now**, and it is the measurement parked as
  `CAL-P151-P1a`. `lone-claim-candidates.py` is the instrument, and it landed:

| | keys | lone markets |
|---|---:|---:|
| **event keys, >=3 markets, >=1 lone claim** | 6,108 | 7,955 |
| **group keys, >=3 markets, >=1 lone claim** | 115 | 118 |
| **TOTAL — the upper bound** | **6,223** | **8,073** |
| *of which the sub-case the ruling was argued on (>=2 lone in one key)* | *891* | *2,741* |

🟢 **AND THE KEY LIST CROSS-CHECKS THE SWEEP.** The listing pass re-walks the
proven tiling and pulls the qualifying keys themselves: it returned **6,108 event
+ 115 group, zero unlisted ranges** — exactly the counts the aggregate reported,
arrived at by a different statement. Two readings, one answer.

**8,073 markets against a resolved population of 862,435 — at most 0.94%, and
that is a ceiling, not the delta.** Every one of those markets is a candidate;
it only actually moves if its whole variant has no winner at all, and it is a
superset twice over (the `datagolf_recovery_residual` exclusion is not applied,
and a market under a >=3 group that also sits in a >=3 event is counted on both
sides — the producer assigns it to `g:` only). **Both tilings reconciled
exactly** — 435,105 event and 862,408 group markets against counts taken a
different way — so the ceiling is complete rather than merely large.

*The plain statement for Alex: option A is a small, bounded population change.*

**The scope argument makes it a bound by construction, not a sample.** A variant
changes only where the ruled arm fires and the retired one did not, which needs
`market_count >= 2` — with one market it either IS the graded lone claim (both
arms fire) or is not one at all (neither does). And `market_count >= 2` needs a
`g:`/`e:` vm_id, i.e. a key with >=3 resolved markets. So every variant the
ruling can touch lives under a key with **>=3 resolved markets holding >=1
single-outcome market**, and the instrument enumerates exactly those.

🔴 **I GOT THAT SCOPE WRONG FIRST TIME, BY 3x, AND THE MEASUREMENT IS WHAT
CAUGHT IT.** The first cut said ">=2 single-outcome markets" because it reasoned
from the CASE Alex ruled on — two lone claims sharing a variant — instead of from
the predicate that ships. A variant holding ONE lone claim beside one
MULTI-outcome market also carries `market_count = 2`, so the retired arm refused
that lone claim too, and the ruled arm admits it (the multi-outcome neighbour has
`win_count = 0` in a no-winner variant and `no_winner_markets` drops it).
Measured on the first complete run: **890 event keys at `>=2` against 6,108 at
`>=1`.** *Scope a change from the predicate it ships, not from the example that
motivated it.* The instrument now reports both, because the narrower one is the
sub-case the decision was argued on and collapsing them loses that.

🔴 **THE RAIL FOUGHT THIS THE WHOLE WAY AND THE REFUSALS ARE THE TRANSFERABLE
PART.** Every one measured this session, with correlation ids in the run log:

1. The unscoped chain (`SELECT COUNT(*) FROM market_info`) — timeout.
   `SELECT COUNT(*) FROM futures_outcomes` — timeout. The group-key aggregate
   over `status='resolved'` — timeout.
2. 🔴 **`mod(fm.event_id, 16) = k` sharding — timeout, and the reason
   generalizes beyond this file.** A modulus on the grouping key is **not
   sargable**, so every shard still scans the whole table. The hash-modulus
   recipe assumes the scan is the cheap part; on a database at 103% of plan it is
   the only part that costs anything.
3. **Grouping by `fm.id` windows and reassembling per-key totals client-side
   blew the 1,000-row cap on the first window** and halved nine times without
   finishing one range — key density, not data volume.
4. 🔴 **`en_US` collation broke a hand-written text tiling in two independent
   ways at once.** Seeding `[None,'kalshi;')` looks right in ASCII and is empty
   in `en_US`, where punctuation is not compared at the primary level — so
   `'kalshi;'` sorts BEFORE `'kalshi:AUCTIONPRICETREY-26'`. It also timed out
   anyway, because an unbounded `col < 'x'` estimates most of the table and the
   planner takes a sequential scan. The splitter then could find no cut point
   inside an empty range and the run died.
5. **The splitter inherited the failure it existed to fix** — it computed its
   midpoint with `COUNT(*)/2`, an aggregate over the whole partition, which timed
   out. *A split helper must be cheaper than the query it is rescuing.*
6. 🔴 **The first complete run reconciled BOTH tilings exactly — 435,105 event
   and 862,408 group markets, the whole measurement done — and threw it all away
   because one partition in the OPTIONAL key-listing step was refused and the
   exception unwound before anything was banked.** *Bank the answer before the
   convenience.* The instrument now writes the reconciled counts to disk before
   listing, splits a refused listing partition, and returns unreadable ranges BY
   NAME instead of a quietly short list.

What works: **key RANGES on the key's own index**, which are sargable AND make
every key whole inside one partition, so each partition emits one summary row;
text cut points taken from `ORDER BY col OFFSET n LIMIT 1`, which is the
collation's own answer rather than arithmetic; and **coverage proved by
reconciliation** against a count taken a different way (pkey windows), so a hole
in the tiling fails the run instead of shortening the answer.

**STAGE 2 IS NOT BUILT AND IS THE ONLY THING BETWEEN THIS CEILING AND THE EXACT
DELTA.** It folds the candidate keys through the producer's own chain and asks,
per variant, whether `has_winner = 0` — the condition that turns a candidate into
a change. `artifacts/cal-p151/cricket-population-fold.py` already has the rail it
needs (component chunking with a scope proof, so a chunk is a REPLAY of the
global derivation and not a re-derivation over a subset). Re-run stage 1 first if
the key list is needed: `source ~/.claude/.env && python3
artifacts/cal-p155/lone-claim-candidates.py`, and **read `candidate_listing`
before believing the key list** — the counts above come from the reconciled
sweep and are unaffected by a partial listing.

## 9. 🔴 CI caught two things the local suite could not, and they are different kinds

The PG gate skips locally — no Postgres in this sandbox — so the inverted fixture
was unproven until it ran. It came back red twice, and both reds were worth the
round trip.

**(a) THE ORM AND PRODUCTION DISAGREE ABOUT `is_winner`.**
`models.py:849` declares `is_winner: Mapped[bool] = mapped_column(Boolean,
default=False)`. The annotation is not Optional, so SQLAlchemy infers
`nullable=False` and `Base.metadata.create_all` — **how every real-Postgres gate
in this repo builds its schema** — creates it NOT NULL. Production is
`is_nullable = YES, column_default = false` (`information_schema.columns`, read
2026-08-31).

That drift is load-bearing. The whole 12-CAL argument, gotcha #21, D13's retired
`graded >= 1` and this queue's `ungraded_lone_claims = 0` all rest on "not a
winner" spanning a graded loss AND a row nothing ever graded. **In a schema built
from the model that distinction cannot exist** — so a fixture seeded there would
have proved the fail-closed conjunct works by never exercising it. CAL-P152's
lesson in a new place: *a fixture that cannot come from the writer proves nothing
about the reader.*

The gate now relaxes the column to match the schema the producer actually runs
against and **asserts via `information_schema` that the DDL took** rather than
assuming it. The MODEL is deliberately untouched — widening `Mapped[bool]`
reaches every reader of the attribute and does not belong in a freeze-lift batch;
it is reported to Alex. ⚠️ **And if any other PG gate ever "proved" a
nullability behaviour on a metadata-built schema, it proved it against a column
that could not be null. I did not audit the others and am flagging it, not
claiming it.**

**(b) A RED-FIRST ARM ENCODES A POPULATION STATE, AND THE RULING CHANGED IT.**
The reverted two-column join used to MISFILE the loss legs — one admission row to
match, so they published under the sibling's `baseball`. My assertion said "and
this fixture must not also duplicate", which was true then. Option A admits the
cricket variant, so the coarse key now matches BOTH and every outcome is emitted
once per admitted variant: `[(771511,'baseball'), (771511,'cricket'),
(771512,'baseball'), (771512,'cricket')]`. That is D5's own duplication defect,
reproduced on rows the ruling put there.

**CI measured that; I did not predict it.** The arm was re-aimed rather than
relaxed — the accident is now asserted as a subset, duplication as a strict
inequality, and the fixed-join assertions (exactly four rows, each under its own
category, nothing from the unknown-truth variant) are unchanged and still the
load-bearing ones. The general form: *when you change a population, re-read what
your red-first arm is proving — it was written against the old one.*

## 7. What this session did NOT do

* **Deployed nothing, merged nothing, certified nothing.** No headline was taken
  and none was available.
* **Did not re-run the cricket fold** — it is done (CAL-P151) and must not be.
* **Did not build the cricket fix**, and did not touch `app/tasks/polymarket.py`.
* **Did not re-derive E2's scope** — it still needs the deployed repaired
  population, which does not exist.
* **Did not touch the legacy Redis-key detector classification** (D21's 21→22
  `uncovered_sql_shaping`). Untouched and deliberately so, unchanged from
  CAL-P152's reasoning.
* **Did not restart any instrument.** Banker and serve-phase probe both alive
  throughout, zero restarts.
* **Did not rebuild the 24-beat window.** It stays retired until the lift
  deploys; when it is rebuilt the watcher needs a lane-unique argv token
  (CAL-P153).

## 8. Files

| file | what |
|---|---|
| `lone-claim-candidates.py` | the stage-1 bound instrument, with every rail refusal argued in its docstring |
| `lone-claim-candidates.json` / `.txt` | its output and run log — **read `candidate_listing` before believing the key list** |
| `_rail.py` | shared read-rail helpers (query, row-array zip, chain builder) |
| `DESIGN-polymarket-container-outcomes.md` | the cricket ingestion fix design — DESIGN ONLY |
