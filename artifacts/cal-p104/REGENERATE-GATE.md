# CAL-P104 — the published-pair fold's evidence can now be read back, and its regenerate is gated on a DEPLOY

**Directive:** 2026-08-26 runner directive, item 2 — *"Repair C-PUBLISHED-PAIR-1's evidence tooling:
timeout in the request BODY, per-bin row identity in the artifact; regenerate, re-stage."*

**Cert:** `C-PUBLISHED-PAIR-1` / `CERT-416`. Re-pin to this branch's head. Acceptance UNCHANGED.

---

## 1. The two named repairs were already in the tree, and this confirms them rather than redoing them

| C-PUBLISHED-PAIR-1 P1 | landed at | shape |
|---|---|---|
| the fold advertises a timeout the row rail refuses | `3f281c5a` | both readings on ONE direct `DATABASE_URL` connection in ONE `REPEATABLE READ, READ ONLY` transaction, budget applied as a database `statement_timeout`. Stronger than the cert's minimum: the cert asked for the timeout to reach the server, this removes the HTTP rail entirely, and with it the 1,000-row cap that made row-level evidence impossible. |
| `bins_whose_row_identity_changed` cannot answer criterion 4 | `3f281c5a`, isolation readback `11294448` | exact row-set arithmetic — `added` / `mutated_survivors` (split `same_bin` / `cross_bin`) / `removed` vs the builder's own flagged set — with per-bin `n`, `sum_prob`, `winners`, `row_identity`. The bin list is retained and demoted to context. |

Neither is re-litigated here. What follows is the part that stopped `regenerate`.

## 2. The third defect, in the same family as the two the cert named: the instrument could not DELIVER a reading

`--out` writes to a one-off dyno's **ephemeral** filesystem, and a detached run's stdout is not
available to the bus. So a successful fold and a fold that never started leave the same trace:
nothing.

That is not a hypothetical. The sibling census fold was polled at
`artifacts/cal-p094/eligible_fold.json` at 21:43Z, 21:45Z, 21:56Z and 21:57Z and read as "still in
flight" when it had never started; what actually landed `cohort-cell-census/v2` was a **durable
row**. Two spaced polls, a "wait one cycle" deferral and a dyno-restart hypothesis were all spent on
an absence that the instrument had no way to distinguish from work in progress.

**Fixed:** the artifact is published to `durable_state_snapshots` under identity
`calibration:published_pair_coherence`, schema `published-pair-coherence/v1`, before the file is
written.

* **Bounded, but still identifying.** Id enumerations are re-capped to 500 in the durable copy (the
  file keeps all 20,000), because a row of a few hundred KB cannot carry five 20,000-element
  arrays. Every list carries an exact `count` **and** an `ids_digest` over the whole set — that is
  what makes a capped enumeration evidence instead of a claim, and it is the same lesson as this
  suite's own kill of the id-only bin digest.
* **`complete` tracks MEASURED, not the verdict.** A non-local run (exit 3) is published
  `complete=true` deliberately. A reader is entitled to skip an incomplete row, so filing "the rule
  moved rows it should not have" under the flag that means "this never finished" would rebuild
  gotcha #53 inside the sink added to prevent it.
* **A failed publish is exit 4, and it outranks 1 and 3.** If the row did not land, a detached run
  has produced no readable evidence at all — so there is no verdict for anyone to act on, and
  returning the verdict's exit code would be publishing a conclusion that exists only inside a dead
  dyno.

## 3. A slug without the rule now refuses BY NAME

Left unguarded, running the fold on a slug that does not carry the rule raised `ImportError` and
exited **1** — which in this fold's own published exit table means *"a reading REFUSED"*. A
**deployment** absence would have been reported as a **measurement** failure, and the operator sent
to debug the fold.

Gotcha #54's amendment states the principle: *1 is a result, everything else is a story about the
harness.* This is a story about the harness, so it is exit **2**, carrying the missing name.

## 4. Why `regenerate` did not happen — two independent blockers, both measured 2026-08-27, both read-only

### Blocker 1 — the subject branch is not deployed

| fact | value | read by |
|---|---|---|
| deployed release | `v3907` | `heroku releases --app bainluck` |
| deployed commit | `baae52c2e970f26d22e35570f7869148f0110cdb` | `heroku releases:info v3907` → `HEROKU_SLUG_COMMIT` |
| `origin/master` | `baae52c2` — the same commit | `git rev-parse origin/master` |
| rule commit `e40d9ca4` an ancestor of master? | **NO** | `git merge-base --is-ancestor e40d9ca4 origin/master` → exit 1 |
| the fold script on master? | **ABSENT** | `git cat-file -e origin/master:backend/scripts/fold_published_pair_coherence.py` |
| `published_pair_coherence_enabled` on master? | **0 occurrences** | `git grep -c … origin/master -- backend/app/tasks/precompute_calibration.py` |
| `PROJECT_PATH` | `backend` | `heroku config:get PROJECT_PATH` |

The `WORKER-FIRE` correction of 2026-08-26 fixed the invocation *path* — `scripts/…`, not
`backend/scripts/…`, because the subdir buildpack promotes `backend/` to the slug root. **The path
is now right and the file still is not there.** The deployment gate was underneath the typo the
whole time, and both produce the same `No such file or directory`.

### Blocker 2 — there is no local rail either

TCP connect to the `DATABASE_URL` host on `5432` from this sandbox returns
`PermissionError: [Errno 1] Operation not permitted`. The fold cannot be run from a workstation with
`DATABASE_URL` set instead of from a dyno.

### The one mechanically-available path is methodologically forbidden

Inlining the chain into a `python3 -c` heredoc — the fallback that rescued the sibling census fold —
is not an option here, and not as a matter of taste. That fold's fallback worked because it needed
only `app`, importable on any slug. This one needs
`_calibration_population_ctes(published_pair_coherence_enabled=…)`, which **is the thing being
measured**. Re-deriving it in a heredoc makes the evidence execute different code from the builder:
CERT-403B's exact defect, and the reason this fold imports the predicate rather than restating it.
It would return a number, and the number would be uncitable.

**The gate, stated so it can go green:** fire the fold when
`heroku releases:info <v> | grep HEROKU_SLUG_COMMIT` names a commit that has `e40d9ca4` as an
ancestor. Nothing else about the invocation changes.

## 5. Gates

| gate | result |
|---|---|
| `tests/test_published_pair_coherence_p100.py` | **63 passed** exit 0 (was 51 — 12 added) |
| red-first, all 12 new tests against the pre-change instrument (`HEAD:…fold_published_pair_coherence.py` restored over the working copy, md5 `0a028ca3…`, then reverted to `d644870f…`) | **12 failed** exit 1 — none of them is green against the instrument as the cert last saw it |
| `ruff check` on both changed files | exit 0 |
| full backend suite | see the commit message — run in this session |

## 6. What this queue could NOT close, stated rather than implied

1. **The delta is still UNMEASURED.** `#2212`'s three unknowns — the ECE delta, the removal count,
   the half-spike overlap — are exactly as unknown as they were. This queue made the instrument
   able to answer them and able to say so when it cannot; it did not answer them.
2. **The durable write itself has never executed against a real database.** It is proved by
   monkeypatched envelope capture (identity, `complete`, payload round-trip) and by the pure
   bounding function. The `publish_snapshot_standalone` path underneath it is shared, long-shipped
   code, but this caller has not run against Postgres.
3. **The sibling fold `fold_cohort_cell_eligible.py` has the same two defects** — no durable sink,
   and a `backend/scripts/…` invocation in its own docstring. Not touched here: it is another
   queue's subject and this lane does not edit files it does not own. Recorded so it is not
   rediscovered a third time.
