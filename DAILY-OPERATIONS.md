# Bain Luck — Daily Operations Runbook (Operating Model v4)

Your entire job: fire windows in the morning, answer questions when nudged,
eyeball ship-gates in the evening. Everything else runs itself.

## One-time migration (do once, ~30 min, mostly automated)

1. In any CLI window at ~/bainluck, paste the v4 ratification prompt (Fable
   provided it; codex executes): creates ~/bainluck-dev/ with the three program
   worktrees (ux, latency, calibration), installs the /program and /integrate
   skills, files a parent issue per program on the board, re-parents existing
   open issues under them, and records the model in PRODUCT-BRAIN.
2. Main repo stays at ~/bainluck. The only new thing in your home directory is
   the single ~/bainluck-dev/ folder.

## Morning (about 5 minutes)

1. Read the "needs-you" digest (arrives ~6:45am PT weekdays, push + here).
   Do what it lists: usually a couple of one-word decisions or one command.
2. Open five terminal windows and type one line in each:

   | Window | Type this |
   |---|---|
   | UX | `cd ~/bainluck-dev/ux && claude --add-dir ~/bainluck` then `/program ux` |
   | Latency | `cd ~/bainluck-dev/latency && claude --add-dir ~/bainluck` then `/program latency` |
   | Calibration | `cd ~/bainluck-dev/calibration && claude --add-dir ~/bainluck` then `/program calibration` |
   | Integrator | `cd ~/bainluck && claude --add-dir ~/bainluck-dev` then `/integrate` (it waits for branches, merges as they land) |
   | Codex | `cd ~/bainluck && codex` then `lane4` |

   **Codex commit location (amended 2026-08-11):** launch is unchanged (root ~/bainluck), but codex now COMMITS in `~/bainluck/.claude/worktrees/codex` on branch `codex/main` -- never in the shared tree. Full protocol: `.claude/handoff/CODEX-LANE.md`. The old `~/bainluck-dev/codex` worktree is removed.

   Cross-root writes are load-bearing: program lanes must be able to write handoff files in ~/bainluck, and the Integrator must be able to write in ~/bainluck-dev. **What grants that is a settings file, not a flag.** Each launch root carries a `.claude/settings.json` (or `settings.local.json`) with `permissions.additionalDirectories` naming the other side. In place today: `~/bainluck-dev/ux/.claude/settings.json` → `/Users/bain/bainluck`, and `~/bainluck/.claude/settings.local.json` → `/Users/bain/bainluck-dev`. Nothing to type. **Note it is per-worktree, not per-container** — standing up the latency and calibration worktrees means copying the same one-key file into each (`~/bainluck-dev/latency/.claude/settings.json`, likewise calibration), or they launch write-denied. Verified fresh-session 2026-08-05: a UX-window write to `~/bainluck/.claude/handoff/` succeeded, so a program window now files its own handoff directly.

   Two things that do NOT work, and cost a cycle each when assumed: **`--add-dir` alone grants read but not write** across roots, and **editing a settings file mid-session changes nothing** — settings are read at launch only. The `--add-dir` flags above stay because they scope the session; the settings files are what open writes. If a lane ever finds itself denied anyway (launched without the file in scope), the fallback is unchanged: write the artifact to `~/.handoff-inbox/<program>-<queue-id>.md`, and the Integrator files it as its Phase-0 step and deletes the inbox copy — handoff IN FLIGHT, never a second source of truth; the queue file's status line in ~/bainluck stays the only authoritative state. One write test at session start tells a lane which path it is on.

3. Walk away. Each window owns its program end to end and ends its session
   cleanly if it ever blocks on you (no more 12-hour idles).

## During the day

- Good idea? Say ONE sentence to any window or to Fable: "file this: <idea>".
  It lands on the board under the right program parent within a minute. You
  never have to remember it again.
- Want status? Glance at a window (one program each), or ask Fable for a
  cross-program read.
- A window finishes its queue? It stages its own next queue and continues, or
  ends cleanly and tells you it's done for the day.

## Evening (about 10 minutes)

1. In the Integrator window: confirm the final `/integrate` ran (it merges the
   day's branches, runs the full suites and publish gates, deploys, and prints
   a ship list).
2. It ends with "EYEBALL:" and at most 3 links — the visible-payoff checks
   only you can judge. Click them, reply good/not-good in that window.
3. Close all windows. Nothing is lost: work state lives on the board and in
   branches, never in a terminal.

## Fable (this chat) — the judgment layer, not a window

- Answers ruling batches with you (the MC forms), edits priorities, verifies
  the live site in Chrome, and pressure-tests anything that smells wrong.
- Runs the Monday scoreboard (7am PT): speed, jank, ships, cycles-by-program.
  Read it in 5 minutes; it tells you if the product is actually improving.
- When in doubt about anything, ask here first.

## How you know when YOU are the blocker

Three guarantees, so you never have to wonder:
1. Any session blocked on a human action files a needs-user issue and ENDS —
   it never silently waits.
2. The daily digest (~6:45am PT weekdays) lists everything blocked on you,
   oldest first, with the exact command/click/decision each needs. If nothing
   needs you, it says so in one line.
3. Urgent same-day items get nudged into this chat by Fable, repeatedly,
   until done.

## What you review, and when (nothing else)

- Ship-gate eyeballs: evening, from the integrator's EYEBALL list (≤3 items).
- Ruling batches: whenever nudged; each is a 2-minute tap-through.
- Monday scoreboard: 5 minutes.

## The one meta-rule

No new process element without a NAMED FAILURE it fixes. If a future idea
can't cite its burn, it doesn't get built.

## Backup remote (added 2026-08-11)
Private mirror: github.com/alexander-bain/bainluck-rescue (remote name: rescue).
Whenever a rescue/* or preserve/* branch is created, back it up:
    git -C ~/bainluck push rescue <branch-name>
Integrator windows: include this in the Phase-0 sweep when new rescue branches exist.

## The single-writer invariant is now a CAPABILITY, not a rule (#1940, closed 2026-08-17)

**Banked by INT-084 as the process win of the week.** Read the shape, not just the fix.

**The finding.** The shared tree carried a *pushable* `heroku` git remote. Anything with a shell —
a lane window, a subagent, a crank, a person in a hurry — could `git push heroku HEAD:master` and
put code into production **without master, without CI, and without the Integrator lock**. This was
not hypothetical: **four live deploys went out that way on 2026-08-17** (v3834/v3835 among them,
deploying `82c985a5` and `46df03ce`, commits that were later deliberately excluded when
`lane1/q363` was rebuilt clean).

**Why the obvious fix was the wrong one.** The reflex is to write a rule — "never push to heroku",
another line in another file, enforced by everyone remembering it. Every one of those four deploys
was made in good faith by a lane whose own instructions told it to ship. A rule would have been
the fifth document those lanes were already obeying.

**What was actually done: the capability was removed.** The `heroku` remote is gone from every
worktree. There is nothing to remember, because there is nothing to type.

| | before (2026-08-17 morning) | after (verified 2026-08-17 20:5x PT, INT-084) |
|---|---|---|
| worktrees with a pushable `heroku` remote | **≥1, in the shared tree everything roots from** | **0 of 20** |
| heroku remote entries across all worktrees | ≥1 | **0** (`git remote -v \| grep -c heroku` = 0, every tree) |
| paths to production | master+CI+lock **or** `git push heroku` | **master + CI + Integrator lock, only** |
| what stops a bypass | a rule someone must recall | **the command does not resolve** |
| live bypass deploys | **4 in one day** | 0 since |

Verification, one line, re-runnable:

```bash
git worktree list --porcelain | grep '^worktree ' | sed 's/^worktree //' \
  | while read -r wt; do git -C "$wt" remote -v | grep -ci heroku; done | paste -sd+ - | bc
# must print 0
```

**The transferable rule — apply it to the next invariant, not just this one:**

> When an invariant is being violated in good faith, the fault is that the violation was
> *possible*, not that someone forgot. Delete the capability. A rule is what you write when you
> cannot delete the capability, and it is strictly worse.

Run the one-liner above during the Phase-0 sweep. A non-zero answer means a worktree was created
from a template that still has the remote, and the invariant is open again.
