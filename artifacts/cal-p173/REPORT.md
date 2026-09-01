# CAL-P173 — the rebase landed, the second cert was never re-staged, and the rebase dropped two pins

**PILLAR: TRUTH · SHIP:** the `/calibration` page's published curve stops scoring our own writer's
coin flips (rank 1, `polymarket/baseball`) and says which half of its exclusion is temporary — the
work CERT-652 graded GREEN, now on a base that can actually merge.

**Lane:** calibration. **Branch:** `program/calibration-168-rank1-baseball`.
**Directive:** `937-burndown-conveyor.md` (self-staged by CAL-P170), after `936` was consumed.
**Issue:** #1978.

---

## 0. WHAT THIS SESSION FOUND, IN ONE PARAGRAPH

Directive 937 said *"if 936 has not run, run 936."* **936 had run** — CAL-P172 rebased, resolved the
`test_movement_window.py` add/add, and staged **CERT-657** for `8258395c`. But 937's own §8 warning
was half-discharged: **a rebase orphans BOTH tokens, and only CERT-638's was re-staged.** CERT-652
(GREEN for the rank-1 + disclosure work) says in the cert log, verbatim, *"required rebase and fresh
exact-head cert remain"* — and no such cert existed. That was the gap this session closed. While
closing it, the rebase's resolution turned out to have **dropped two guard properties** that 936
step 2 explicitly asked to be ported rather than dropped; those are restored here.

---

## 1. STATE, MEASURED NOT INHERITED

| fact | value | how |
|---|---|---|
| 936 | **consumed** 2026-08-31 22:02:37 | inbox filename suffix |
| rebase | **done** | `git rev-list --left-right --count origin/master...HEAD` → `0 19` |
| base | `origin/master` `1cf5be342da522b446397611a1c528a0e1fcfd54` | after fresh `git fetch` |
| merge | **exit 0, 0 CONFLICT lines**, tree `7259e2b3216c9318521c7007fa23cb6fbab2f24b` | `git merge-tree --write-tree` |
| `git diff --check` | exit 0 | — |
| remote == local | yes, at the pre-port head `6f29ffcf` | `git ls-remote` |

**The rank-1 work is byte-identical across the rebase — proven by patch-id, not asserted:**

| commit (post-rebase) | patch-id | pre-rebase twin | patch-id |
|---|---|---|---|
| `f8126c8c` rank 1 | `b797fab3…` | `600c2fc0` | `b797fab3…` |
| `f4b5526a` suite record | `04a52b91…` | `0d5edbb0` | `04a52b91…` |
| `9f1aacc8` CERT-647 repair | `a8b969ad…` | `591bd844` | `a8b969ad…` |

All three match. The delta above CERT-657's subject is therefore **same bytes, new base**, plus two
artifacts-only heartbeat commits — exactly the scope CERT-652's own block predicted.

---

## 2. 🔴 THE PUBLISH GATE IS STILL NOT BEING ASKED — RE-MEASURED, AND IT GOT WORSE

Read from `observations[]` via `?full=true`. **The bounded (default) form of
`/api/admin/calibration-beat-gauges` strips `outcome{}` entirely** — a reader who uses the default
sees `None` for every field and can conclude nothing. That is a trap worth knowing.

| | CAL-P169/P170 | **this session** |
|---|---|---|
| last beat that PUBLISHED | 2026-08-31T04:37:37Z | **unchanged** |
| beats since | 22 | **24** |
| `outcome.gate` | `not_evaluated` 21/21 | **`not_evaluated` 23, `refuse` 1** |
| elapsed | ~24 h | **~25 h** |

The published payload's `generated_at` is `2026-08-31T04:37:36.703361Z`, which is that same beat.
**The page has not moved.** `nonexclusive_bundle_filter` is still absent from the live payload, so
RULE E and K′ are still undeployed — consistent, since they are on this unmerged branch.

**Consequence, stated plainly as 937 item 3 step 2 required:** neither `artifacts/cal-p162/
PREDICTION.md` nor `artifacts/cal-p168/PREDICTION.md` can be graded. No new cell can be shown to
work. **No build was opened on the strength of an ungraded prediction.**

**One correction to the inherited claim, and it is a correction to my own predecessor.** CAL-P170
wrote: *"It completes exactly 5, every time. That is a cap, not a deadline."* The beat at
`2026-09-01T04:19:20Z` completed **4** units at `unit_ms_mean` 43,778 and `elapsed_ms` 260,097 —
one fifth of the longest beat's clock, so it was not clock-bound. **The "exactly 5, every time"
observation has a counterexample.** The cap reading may well still be right; it is no longer
supported by that particular argument. **Not diagnosed here — ruling 134.** Parked.

---

## 3. THE PORT — 936 STEP 2'S "UNLESS" CLAUSE FIRED, AND THE REBASE DID NOT HONOUR IT

936 step 2: *drop yours in favour of master's, **unless** master's 555-line file lost a property
yours pinned — in which case port that one property into master's file.*

CERT-657's block records the resolution as *"master's 555-line file at that path is taken **whole**"*
— i.e. all four of CAL-P159's pins dropped. Master's file is entirely about **the sweep** (the
read-side fix: 21 tests, all on `update_max_movement`'s statements). CAL-P159's pins were about
**the writers**. Those are disjoint. Re-checked by measurement:

| pin | verdict | evidence |
|---|---|---|
| `..._every_writer_computes_a_per_write_delta_not_a_windowed_one` | **PORT** | strings present: `kalshi.py` 1, `polymarket.py` 2, `futures.py` 1 |
| `..._nothing_recomputes_it_over_a_real_24_hour_window` | **PORT, RENAMED** | `interval '24 hours'` absent from all three writers |
| `..._the_upstream_fix_has_not_silently_landed_elsewhere` | **DROP** | `app/tasks/__init__.py` now has `SET probability_change_24h = NULL` **twice** — it pinned the absence of the very sweep master built |
| `..._the_movers_bound_still_documents_why_read_side_is_wrong` | **DROP** | covered by `tests/test_futures_movers_pool_bound.py:72` |

⚠️ `update_max_movement` is a **task function in `app/tasks/__init__.py`**, not a module — there is
no `app/tasks/update_max_movement.py`. A `ls`-based check reads as "the fix is missing".

**The rename matters.** `test_nothing_recomputes_it_over_a_real_24_hour_window` became false the day
lane1/Q482's sweep landed: something *does* now bound the column. It is just not a writer. The
ported pin is `test_no_writer_recomputes_it_over_a_real_24_hour_window` and its docstring says where
the real bound now lives, so the next reader is not told the field is unbounded.

**Ported INTO master's file, not beside it** — restoring a second file at that path is what 936
forbids and what created the collision.

### Negative controls — 2/2 killed, in an rsync copy so the live tree was never mutated

| mutation | pin | result |
|---|---|---|
| remove `- FuturesOutcome.current_probability` from `app/tasks/kalshi.py` | per-write-delta | **FAILS** ✅ |
| inject `interval '24 hours'` into `app/tasks/polymarket.py` | no-writer-recomputes | **FAILS** ✅ |

🔴 **The first attempt at mutation 1 was a false pass, and it is the useful part of this section.**
I replaced the string with `…current_probability_MUTATED`, which still *contains* the asserted
substring, so the pin passed and would have read as "this guard is vacuous". The give-away was
printing the count: `1 -> 1`. The mutation was re-done to actually remove the substring, and only
then was the red believed. Import resolution was confirmed to the copy (`kalshi.__file__` under
`/tmp/cal-p173-mut/`), not the live tree.

---

## 4. GATES — CLAIMS. RE-RUN THEM.

Run in this worktree, `/Users/bain/bainluck-dev/calibration`.

| gate | result |
|---|---|
| smoke `tests/test_startup.py` | **4 passed**, exit 0 |
| full backend suite @ `6f29ffcf` (pre-port) | **25,210 passed / 158 skipped / 61 xfailed / 0 failed**, exit 0, 20:31 |
| full backend suite @ post-port `0896b246` | **25,212 passed / 158 skipped / 61 xfailed / 0 failed**, exit 0, 20:28 |

**+2 and it reconciles exactly** — the two ported pins, and nothing else moved.
| `tests/test_movement_window.py` | **23 passed** (21 master + 2 ported) |
| source-scanning guards¹ | **88 passed** |
| frontend `npm run build` (ESLint gate) | exit 0 |
| frontend `npm run typecheck` (TS gate) | exit 0 — **70 errors, baseline 70**, no new |
| jest `CalibrationNonexclusiveBundleDisclosure` | **17 passed / 17** — matches CERT-652's count |
| `ruff check` on the edited file | clean |

¹ `test_requirements_declares_test_imports_p165`, `test_futures_movers_pool_bound`,
`test_futures_stamp_semantics`, `test_claude_md_size`, `test_movement_window`.

**CAL-P168 recorded `1 failed / 25,057 passed` pre-rebase; the rebased stack is `0 failed`.** The
failure was resolved by master's movement-window fix plus CAL-P172's guard repair.

**`black` was deliberately NOT run.** `backend/tests/test_movement_window.py` is already
black-noncompliant **at HEAD** — those are lane1's bytes. Black's hunk-header list is *byte-identical*
before and after this edit (11 hunks, last one ending ~line 538) while the ported block starts at
line **559**. Reformatting would rewrite 555 of lane1's lines, balloon the cert diff and invite a
semantic conflict, for zero gain. The added block is black-clean on its own.

---

## 5. WHAT WAS NOT DONE, AND WHY

* **No fourth ship.** Directive 937 item 3 step 4 forbids it, and the board has nothing both ruled
  and unbuilt. Ranks 1/2/3/6 are all built; the next top cell needs a fold, which is the measurement
  lane's (ruling 134).
* **No prediction graded** — the curve has not republished (§2).
* **No diagnosis of the 5-unit cap** — ruling 134; parked, with the counterexample above.
* **The ~18.6k-line `artifacts/cal-p147-renders/*.txt` cleanup that 936 flagged as a cheap win was
  not taken.** It is not a blocker, it was explicitly not asked for, and doing it inside a cert
  delta that is otherwise provably "same bytes, new base" would destroy that property — which is the
  single thing making this cert cheap to grade. **It should be a separate commit after the merge.**

---

## 6. THE OPEN MERGE-PLAN QUESTION — STILL FOR FABLE/INT, NOT THIS LANE

`program/calibration-119` @ `8258395c` (CERT-657, `running`) is a **strict ancestor** of
`program/calibration-168-rank1-baseball`. So 168 delivers 119 in full. Whether 119 merges separately
first or is delivered by 168 is a merge-plan call. It is unchanged from READY §8 and is recorded in
`YOUR-TURN.md`.

🟢 **CERT-657 came back GREEN mid-session — token granted 2026-09-01 05:49Z for `8258395c` on
`1cf5be34`.** I had written a dependency warning here (a BLOCK would have re-based these commits and
orphaned this cert too); it is discharged, not merely unlikely. **The base of this delta is now
certified, so this cert grades a delta over graded bytes on both sides.**

🔴 **And the certifier independently named this session's port.** CERT-657's log row closes with
*"Follow-ups remain `MOVEMENT-WINDOW-STALE-COMMENT` and `MOVEMENT-WINDOW-WRITER-PREMISE-PIN`;
neither blocks the ship."* **`MOVEMENT-WINDOW-WRITER-PREMISE-PIN` is exactly the dropped writer-side
premise §3 restores** — found here from 936 step 2 and READY §8 before that row was read, and
confirmed by it afterwards. `MOVEMENT-WINDOW-STALE-COMMENT` is **NOT** addressed here and stays
open.
