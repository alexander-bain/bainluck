# CAL-P174 — REPORT

**Session:** 2026-09-01 ~06:48Z → ~07:0xZ / 2026-08-31 ~11:48 pm PT
**Directive:** `runner-inbox/calibration/938-burndown-conveyor.md` (self-staged by CAL-P173)
**Branch:** `program/calibration-168-rank1-baseball` @ `2f28aa30` — **tip unchanged, deliberately**

## 0. ONE PARAGRAPH

938's step 1 said *poll CERT-662 first; GREEN → tell INT the stack is mergeable and answer nothing
else until that is said.* **CERT-662 came back GREEN at 06:48Z.** While polling, I found master had
moved 18 commits and — the material discovery — **had already merged this very branch at
`8258395c`**, the CERT-657 subject. So the merge-plan question CAL-P173 escalated to Alex/Fable was
answered by the Integrator, not owed. I re-measured mergeability of the remaining 7-commit delta
against the new master, flipped the READY file to `ready_for_integration`, and handed the delta to
the Integrator. **Nothing was built. No commit was made. The branch tip was not moved.**

## 1. CERT-662 — GREEN

| field | value |
|---|---|
| verdict | 🟢 **GREEN — TOKEN GRANTED**, 2026-09-01 **06:48Z** (claimed 06:43Z) |
| subject | `2f28aa3014f20ec3892062eb2f37b4782e485a42` |
| graded against | **`c3143bc2`** — current master, **not** the `1cf5be34` the queue block named |
| evidence | focused backend **194/194**, frontend **17/17**, merge tree **`664ecc36`** |
| queue block | `status: done` |
| follow-ups | `MOVEMENT-WINDOW-WRITER-PIN-SEMANTICS`, `CALIBRATION-DISCLOSURE-TEST-COMMENT-TRUTH` (both new), `MOVEMENT-WINDOW-STALE-COMMENT` (pre-existing, still open). None blocking. |

🟢 **The staleness trap did not fire, and that is worth recording.** CAL-P173 staged the block
claiming base `1cf5be34` / "0 behind, 21 ahead". By grading time that was false. The cert bus
re-derived the base rather than trusting the block, and computed merge tree `664ecc36` — the same
tree I measured independently. **A re-cert for the base move is not required.**

## 2. THE DISCOVERY — MASTER ALREADY TOOK HALF THIS BRANCH

```
76b2b454  Merge program/calibration-168-rank1-baseball @ 8258395c (CERT-657, supersedes CERT-638) into master
```

`git merge-base --is-ancestor 8258395c origin/master` → **YES**.

Consequences, all measured this session:

* Branch arithmetic is **18 behind / 7 ahead** of `c3143bc2` — was 0/21 vs `1cf5be34`. The 18 are
  other lanes' merges **plus this branch's own merged half**. Not a rebase signal.
* READY §0's "(a) or (b)?" is **decided — (a)**. READY §9's "still open … merge-plan call for
  Fable/INT" and `YOUR-TURN.md` §3b item 3 are **closed**. This was directive 938 Item 5 #7, the
  file's self-described *"only open question in the stack"*. It needed no decision.
* 057 (integrator) listed **CERT-638 / `4d8373c6`** as green-and-unmerged with *"not acceptable is a
  third cycle of silence."* That row is **discharged**.

## 3. MERGEABILITY OF THE REMAINING DELTA — RE-MEASURED, NOT INHERITED

| check | result |
|---|--:|
| `git merge-tree --write-tree origin/master HEAD` | **EXIT 0**, **0 CONFLICT** lines, tree `664ecc36` |
| `git diff --check` | **EXIT 0** |
| remote == local (`git ls-remote`) | ✅ both `2f28aa30` |
| files in `origin/master...HEAD` | **24** — 2 under `backend/app/`, **3 under `frontend/`** |
| calibration-path overlap with master's 18 | **none** |

The seven commits: `2f28aa30`, `0896b246`, `6f29ffcf`, `dd576c03`, `9f1aacc8`, `f4b5526a`,
`f8126c8c` — the rank-1 `polymarket/baseball` exclusion, the CERT-647 disclosure repair, the two
ported writer-side pins, two heartbeat ticks and a suite record.

⚠️ **§6's add/add hazard on `backend/tests/test_movement_window.py` is dead** — CAL-P172 took
master's 555-line file whole; CAL-P173 ported the two surviving pins into it.

## 4. 🔴 WHAT I COULD NOT MEASURE, STATED PLAINLY

**No full suite has been run on the merge result `664ecc36`.** The 25,212-passed number was measured
at `2f28aa30` on the OLD base `1cf5be34`. CERT-662's 194/194 was *focused*, by design. Master has
since moved 18 commits, several test-infra: `a41affcb` (five date bombs), `92fd7c56`/`6ea42d6c`
(clock-anchor guards), `c3143bc2` (contract-gate assertion), `768b683f` (obsolete cycling fixture).

I did **not** run it, and that is a deliberate call, not an omission: gating the commit you actually
push is the Integrator's gate under ruling 017, and running a 20-minute suite on a tree the
Integrator will re-create differently would produce a number about the wrong commit. **Flagged in
READY §10.4 and integrator directive 058 §4 so nobody reads §3's green number as covering the
merge.** Master's own `768b683f` and `c3143bc2` are two live instances of this exact class firing.

Also flagged: **`frontend/` IS touched** (3 files). CERT-657's "backend-only, gates cannot move"
exemption **does not carry** to this half.

## 5. THE PUBLISH GATE — RE-MEASURED A THIRD TIME, UNCHANGED

Read with `?full=true` (the default form strips `outcome{}` entirely — 938's instrument trap held).

| | |
|---|---|
| last beat that PUBLISHED | **2026-08-31T04:37:37Z** (`published: true`, `gate: pass`) |
| beats since | **24** — **23 `not_evaluated` + 1 `refuse`** |
| hours | **~26** |
| `measured` / `envelope_status` | `True` / `ok` |

Published curve: `mce_closing_line` **1.86 pp**, `generated_at 2026-08-31T04:37:36Z` — a **ninth**
session unchanged, and explained rather than merely noted. **RULE E still not deployed**, re-verified
directly: the live `GET /api/calibration` payload carries **no `nonexclusive_bundle_filter`,
`temporary_excluded` or `temporary_by_cell` key at all.** Consistent — they are on this unmerged
branch.

**Per 938 step 2, I said so plainly and did not open a build.** Neither `cal-p162`'s nor
`cal-p168`'s prediction can be graded: no beat has published, so there is nothing to grade against.
Diagnosis of *why* the gate is never asked stays parked (`PARKED-MEASUREMENTS.md` item 5) —
measurement lane, ruling 134.

## 6. WHAT I DID NOT DO

* **No fourth ship** (938 Item 4). Ranks 1, 2, 3 and 6 are all built; nothing on the board is both
  ruled and unbuilt, and the next cell needs a design that needs a fold.
* **No commit, and no move of the branch tip.** Two heartbeat JSONs are dirty in the worktree
  (1 line each, auto-generated). Committing them would have moved the tip off `2f28aa30` and
  **orphaned CERT-662's token** — the precise failure that cost this lane CERT-638 and CERT-652.
  Left uncommitted on purpose.
* **No artifacts cleanup.** The ~18.6k-line `cal-p147-renders` chore stays post-merge; inside the
  delta it would destroy the identical-patch-id property that let CERT-662 grade in five minutes.

## 7. WRITTEN THIS SESSION

| file | what |
|---|---|
| `.claude/handoff/READY-calibration-168-rank1-baseball.md` | header → `ready_for_integration`, head/base/cert corrected; **new §10** = the merge signal |
| `.claude/handoff/runner-inbox/integrator/058-CERT-662-GREEN-…md` | the handoff to INT |
| `~/bainluck/YOUR-TURN.md` | §3b item 3 rewritten (merge-plan call **closed**), item 1 → ~26h, §4 lane row |
| `.claude/handoff/runner-inbox/calibration/939-burndown-conveyor.md` | self-restock (938 Item 4) |
| `artifacts/cal-p174/REPORT.md` | this file |
