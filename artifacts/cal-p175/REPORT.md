# CAL-P175 — REPORT

**Session:** 2026-09-01 00:0x → 00:2x PT (07:0xZ → 07:2xZ)
**Directive:** `runner-inbox/calibration/938-rebase-cert652-kprime-disclosure.md` (INT-191)
**Branch:** `program/calibration-168-rank1-baseball` @ `2f28aa30` — **tip unchanged, deliberately**

**PILLAR: TRUTH · SHIP: the calibration page stops promising that a counted exclusion will empty
itself when only part of it ever will.**

## 0. ONE PARAGRAPH — ANSWER: ALREADY DONE, BY CERT-662

938 asked for two things: **rebase the K-prime disclosure onto current master**, and **re-stage the
rebased head for a fresh exact-head cert**. Both already happened, ~17 minutes before 938 was
written. CAL-P172/P173 rebased this branch onto `8258395c` — CERT-657's token head, now merged into
master at `76b2b454` — and the cert bus graded the rebased head `2f28aa30` **against `c3143bc2`,
current master**, granting **CERT-662 GREEN at 06:48Z (23:48 PT)**. 938 was written at 00:05 PT off
the stale CERT-652 row. **No rebase was performed and no commit was made: the work 938 asks for
exists, and redoing it would orphan a live token for zero byte change.** I verified the claim
independently rather than quoting the cert, and I closed the one real hole CAL-P174 left open.

**CERT-652 disposition: SUPERSEDED BY CERT-662.** Not withdrawn — the disclosure ships, under a
newer token.

## 1. THE PREMISE OF THE BOUNCE IS NO LONGER TRUE

938's reasoning: *"`0d5edbb0` is CERT-647's BLOCKED head, so `591bd844` sits on top of bytes that
were never certified to merge."*

That was exactly right when CERT-652 was graded. It stopped being true at CERT-657.

| 938's premise | measured now | verdict |
|---|---|---|
| disclosure sits on CERT-647's BLOCKED `0d5edbb0` | sits on `8258395c` (CERT-657 GREEN) | **stale** |
| that base is not on master's line | `8258395c` **is an ancestor of** `origin/master` | **stale** |
| `591bd844` not an ancestor of master | true, and irrelevant — it was **replaced** by `9f1aacc8` | **moot** |
| "required rebase … remains" | rebase done by CAL-P172/P173 | **discharged** |
| "fresh exact-head cert remains" | **CERT-662**, `2f28aa30` vs `c3143bc2` | **discharged** |

## 2. THE DISCLOSURE BYTES ARE PROVABLY THE CERTIFIED ONES

938 §2 warns "do not re-submit `591bd844`". Correct — and the reason it is safe not to is that the
rebased commit carries the **same change**, not a similar one:

```
patch-id 591bd844 (CERT-652 subject) = a8b969adf09f31f962ed858202b0a1ac011718ca
patch-id 9f1aacc8 (rebased, on branch) = a8b969adf09f31f962ed858202b0a1ac011718ca
diff <(git show 591bd844 --format='') <(git show 9f1aacc8 --format='')  →  IDENTICAL DIFF
```

Byte-for-byte the same diff, on a certified base. **CERT-652's reviewed logic is what merges.**

## 3. MERGEABILITY — RE-MEASURED, NOT INHERITED

| check | result |
|---|--:|
| `git merge-tree --write-tree origin/master HEAD` | **EXIT 0**, tree **`664ecc36`** |
| tree of a real materialized merge in a scratch worktree | **`664ecc36`** — identical |
| remote head == local head | ✅ both `2f28aa30` |
| `8258395c` ancestor of `origin/master` | ✅ YES |
| master position | `c3143bc2` — unmoved since CERT-662 graded it |

`664ecc36` is the exact tree CERT-662 recorded. Two independent derivations agree.

⚠️ The 51-file two-dot `origin/master..HEAD` diff **looks** like this branch deletes
`horizon_sentinel.py`, `timebomb_census.py`, the cycling tests and more. It does not. Those are
files master **added** after the merge-base; a two-dot diff renders them as deletions. The
materialized merge above is the honest picture — nothing is dropped.

## 4. 🟢 I CLOSED CAL-P174 §4's OPEN HOLE

CAL-P174 flagged, correctly, that **no gate had ever run on the merge result** — CERT-662's evidence
was *focused* by design, and master had since moved 18 commits, several of them test-infra. It also
flagged that **`frontend/` IS touched (3 files)**, so CERT-657's "backend-only" exemption does not
carry.

That was the one real risk, and it was a specific one: master's `92fd7c56`/`6ea42d6c` clock-anchor
guards and `a41affcb` date-bomb sweep **scan test files**, and this delta adds a 614-line test file
those guards have never seen. That is the exact class that turned master red in `768b683f` and
`c3143bc2`. So I materialized `664ecc36` in a scratch worktree and ran the gates against it:

| gate, on merge result `664ecc36` | result |
|---|--:|
| master's clock-anchor guards + applied call site + startup | **47 passed** |
| K-prime + movement-window + route-calibration + all `test_calibration_*` | **2,595 passed / 8 skipped** |
| frontend Jest — disclosure suite | **17/17** |
| `npm run build` (ESLint gate) | **EXIT 0** |
| `npm run typecheck` (TS ratchet) | **EXIT 0 — 70 errors, baseline 70, exact** |

**0 failed anywhere.** The guard-interaction risk did not fire, and that is now measured rather than
assumed.

## 5. 🔴 WHAT I STILL DID NOT MEASURE, STATED PLAINLY

**The full ~25k backend suite has not run on `664ecc36`.** I ran the bands where master's movement
and this delta actually intersect, not the whole suite. Gating the exact commit that gets pushed is
the Integrator's job under ruling 017, and a 20-minute number measured on a tree the Integrator will
re-create is a number about the wrong commit. §4 narrows the risk; it does not replace that gate.

The publish-gate streak and the RULE E deploy status are unchanged from CAL-P174 §5 and remain a
measurement-lane item (ruling 134). Nothing in this session touched them.

## 6. WHY THIS WAS A BUS RACE, NOT A LANE FAILURE

938 is not wrong so much as **superseded in flight**:

```
23:48 PT  CERT-662 GREEN — token granted for 2f28aa30 vs c3143bc2
23:52 PT  CAL-P174 files integrator inbox 058-CERT-662-GREEN-…  ← still UNCONSUMED
00:05 PT  INT-191 writes 938 (this bounce) off the stale CERT-652 row
00:06 PT  INT-191 writes conveyor 059, whose row 105 still names 591bd844
```

CERT-662's own `CODEX-REPORT-2.md` entry already said it: *"Current origin/master already contains
certified base `8258395c`… Integration token: GRANTED for `2f28aa30` against `c3143bc2`."* The
answer was on the bus 17 minutes before the question. **058 was never consumed, so it never reached
the conveyor that INT-192 will read** — which is why this report's real deliverable is inbox `060`,
not prose.

938 said "a bounce is a one-cycle round trip, not a parking space." Agreed — and this one round-trips
inside its own cycle, with no rebase spent.

## 7. WHAT I DID NOT DO

* **No rebase.** The tip stays `2f28aa30`. Moving it orphans CERT-662's token for zero byte change —
  the precise failure that already cost this lane CERT-638 and CERT-652.
* **No commit.** The two heartbeat JSONs remain dirty on purpose (same reason as CAL-P174 §6).
* **No verdict written to `CODEX-CERT-LOG.md`.** Authors do not certify, and a build lane does not
  write cert rows.

## 8. WRITTEN THIS SESSION

| file | what |
|---|---|
| `runner-inbox/integrator/060-CERT-652-IS-CERT-662-MERGE-THE-DELTA.md` | **the deliverable** — supersedes 059 row 105 |
| `.claude/handoff/READY-calibration-168-rank1-baseball.md` | new §11 answering the bounce head-on |
| `.claude/handoff/CODEX-REPORT-2.md` | lane-authored disposition block, as 938 §3 required |
| `runner-inbox/calibration/938-rebase-cert652-…` | marked consumed |
| `artifacts/cal-p175/REPORT.md` | this file |
