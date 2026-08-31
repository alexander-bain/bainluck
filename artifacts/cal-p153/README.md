# CAL-P153 — the window closed NOT_MET, and the supervisor had gone blind on the runner's own argv

**Pillar: TRUTH. Ship: the published calibration curve stops being able to go out
~96,026 outcomes short without saying so.**

This file is the state for THIS session only. `artifacts/cal-p152/README.md` remains
the state for the twelve commits (read its **§7** first — §1–§6 are the prior rework
and §3b's argument is withdrawn by §7b). cal-p151's is the state for the nine
beneath it; cal-p150's for the five original commits.

---

## TL;DR

This session authored **no code**. `CERT-504` was already `status: running` when it
opened, so the queue's step 1 was a poll, not a build. Three things happened that
the next session must not re-derive:

1. 🔴 **THE 24-BEAT WINDOW CLOSED AT 22:49:49Z: `20/24 clean`, `VERDICT NOT_MET`** —
   and **not one of the four misses is the producer's.**
2. 🔴 **THE WATCHER IS GONE AND IT DID NOT DIE — IT EXITED, BY DESIGN, ON A FULL
   WINDOW.** The supervisor did not replace it, and the reason is the finding below.
3. 🔴 **THE SUPERVISOR WAS BLIND, AND WHAT BLINDED IT WAS THE RUNNER DIRECTIVE'S OWN
   TEXT.** Retired at 22:56Z. See §2 — this one generalises past this lane.

`CERT-504` was **still `running`** at this session's last poll. It is the whole of
step 1 and it is not discharged here.

---

## 1. The window: NOT_MET, with zero producer-caused misses

The bar is `22 of the last 24` (`rebaseline.py:382`, `required`/`window`). The result:

```
20/24 clean   (4 misses; -2 of 2 budget left)
###?##C#######B####C####   <- oldest ... newest
VERDICT  NOT_MET
```

**Read the misses before reading the verdict:**

| beat | class | what it actually was |
|---|---|---|
| 4 | `B_OR_D_UNATTRIBUTED` | failed before the gate; B and D are indistinguishable in the ring |
| 7 | `C_DEPLOY_KILL` | cancelled after 693,263 ms — **another lane's release** |
| 15 | `B_DIAGNOSTICS_TRUTH_CENSUS` | `QueryCanceledError`, statement timeout |
| 20 | `C_DEPLOY_KILL` | cancelled after 132,524 ms — **another lane's release** |

Two of four are other lanes' deploys, one is the diagnostics census timing out, one
is unattributable because `task-metrics.last_error` is overwritten by the next
failure. **The count that would have been the producer's own is zero.** A verdict of
NOT_MET on this window is a statement about the shared dyno, not about the thing the
window was built to watch. Do not carry "NOT_MET" forward as a producer verdict.

🔴 **AND IT IS THE VERDICT ON THE FIRST FULL WINDOW, NOT A ROLLING ONE.** `watch()`
returns the moment `beats_in_window >= deadline_beats` (`rebaseline.py:571`). The
window is defined as "the last 24", so it *can* recover as misses age out — beats 4
and 7 leaving would put it at 22/24 — but **no instrument is watching for that any
more**, because the watcher exited. Re-baselining is still correctly gated on the
lift deploying; this note only records that the exit was terminal, not that the
condition is permanently failed.

**Beats 23 and 24 both landed CLEAN** (59,592 ms and 74,024 ms of margin). Beat 19
is still the tightest CLEAN margin at 2,691 ms.

---

## 2. 🔴 The supervisor was blind, and the runner directive is what blinded it

`artifacts/cal-p141/watch-supervisor.sh` keeps exactly one watcher alive by testing
`pgrep -f "rebaseline.py --baseline-at"` every 60 s. It has run since
2026-08-29 23:36 and **`artifacts/cal-p141/supervisor.log` was never created** —
it has never once found the watcher absent, including the ten-plus poll cycles
after the watcher exited at 22:49:49Z.

**The pattern matches the runner window itself.** The directive text this lane is
launched with contains, verbatim, the line

```
  pgrep -f "rebaseline.py --baseline-at"   -> the watcher (3016/3019). Never restart.
```

and that whole directive is a single `-p` argv element on the `claude` process.
Measured: `ps -p <runner> -o command= | grep -c 'rebaseline\.py --baseline-at'` → **1**.

🔴 **AND THE TRAP HIDES ITSELF FROM THE LANE THAT WOULD FIND IT.** macOS `pgrep`
excludes *itself and all its ancestors* by default. Run from inside the runner
window, the runner is an ancestor, so it is excluded and `pgrep` correctly reports
`NONE`. Run from the supervisor — whose ancestors are `init` and its own `bash` —
nothing is excluded, so it matches the runner and reports the watcher ALIVE.
**The same command, the same instant, gives opposite answers to the two processes
that need it, and the one that is wrong is the one that acts on it.**

This is a fresh instance of the cal-p149 pgrep trap, and it is worse than that one:
the previous trap made a pattern miss a process, this one makes a *supervisor* see a
process that is not there — and the false witness is **the instruction telling the
lane to check on it**.

**Action taken:** the window is complete, so the supervisor has no job left. Killed
by pid (`kill 32367`, 22:56Z), verified gone. This was not a judgement about the
finding — a supervisor for a closed window is a restart storm waiting for the last
runner window to close, because the moment nothing quotes the pattern it will
respawn a watcher that exits on `window full` within seconds, forever.

**For whoever builds the next window:** the supervisor's pattern must be
**lane-unique and not quotable in a directive** — a token like
`CAL-PNNN-REBASELINE-WATCHER` passed as its own argv flag, the way the banker and
the serve-phase probe already do it. Those two were never at risk, because their
tokens (`CAL-P147-RENDER-BANKER`, `CAL-P148-SERVE-PHASE-PROBE`) appear in the
directive only inside a `pgrep` the *lane* runs, and the lane's own pgrep excludes
its ancestors.

---

## 3. The ring, and what is still alive

Both remaining daemons were advancing at session close, zero restarts:

| process | pid | last cycle | state |
|---|---|---|---|
| render banker | 75909/75911 | 22:56:12Z | `already_banked`, **15 censuses banked** |
| serve-phase probe | 37525/37527 | 22:56:44Z | 26 samples, served == redis |
| ~~re-baseline watcher~~ | — | exited 22:49:49Z | **window full, terminal** |
| ~~watch supervisor~~ | 32367 | — | **retired 22:56Z** (§2) |

**All four per-session instruments exit 0:**

* `artifacts/cal-p150/board-d15.py` — EXIT 0, every cell named by the 2026-08-30
  batch present and placed
* `artifacts/cal-p146/promotion-datapoint.py` — EXIT 0, no *recoverable* measurement
  beat unread (the beat-14 bracket remains the one permanent, acknowledged loss)
* `artifacts/cal-p145/refusal-register.py` — EXIT 0, 13 of 20 live seats on the
  board, 0 of 13 refused cells on it
* `artifacts/cal-p144/window-beat-margins.py` — EXIT 0, **21 gauged / 21 agree /
  0 disagree**, 3 ungauged (beats 7, 14, 20)

Nothing was added to `PERMANENTLY_UNREADABLE`.

---

## 4. What is unchanged and must not be re-derived

* **The branch is `bd76c953`**, twelve commits, base `682c0b37`, pushed and
  confirmed by `git ls-remote`. `1e07a657` is the last CODE commit;
  `git diff 1e07a657 bd76c953 -- backend/ .github/` is **EMPTY** (re-verified this
  session).
* **Nothing is deployed.** `program/calibration-119` is not an ancestor of master.
  The board still reads **1.88 pp on q268**. All twelve commits are ONE deploy.
  🔴 **Do not take a pre-deploy headline.**
* **The P1-a magnitude is still owed** — `PARKED-MEASUREMENTS.md` entry
  `CAL-P151-P1a`. A GREEN on CERT-504 does not discharge it.
* **Cricket is solved and is not this lane's cargo.** The remaining miss is one
  family caused by a Polymarket ingestion defect (gotcha #18, unapplied). It needs
  its own queue with its own ship.

---

## 5. Lessons

* 🔴 **A watchdog's pattern must not be quotable.** If the string that identifies a
  process can appear in a document, a launch command, or a prompt, then anything
  carrying that document *is* the process as far as the watchdog can tell. Identify
  by a token the watched process is the only thing that can legitimately carry.
* 🔴 **`pgrep` answers a question about the ASKER, not just the pattern.** Ancestor
  exclusion means "is it running?" is not a property of the system. Two processes
  can ask identically and both be right. A liveness check that a supervisor acts on
  must be validated from the supervisor's own position in the tree.
* **An instrument that exits on success leaves no corpse and no alarm.** The watcher
  finishing its job and a watcher dying look identical from `pgrep`. Liveness is an
  advancing heartbeat; *completion* needs its own signal, and this one only had a
  line in a log nobody was tailing.
* **A verdict is not a finding until its misses are attributed.** NOT_MET here would
  read as a producer failure, and the producer caused none of it.
