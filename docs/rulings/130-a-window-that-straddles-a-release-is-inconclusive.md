# RULING 130 — A window that straddles a release is INCONCLUSIVE, not a result

date: 2026-08-24
author: Fable (LAT-P086 item 0a, pasted and reviewed by Alex)
issues: #2107
supersedes:

Generalised from the LAT-P085 dated-streak fix, which applied the same
discipline to arm B only.

---

## The clause

**A measurement window that contains a deploy measures two different systems
and reports one number. It is INCONCLUSIVE — a third verdict alongside pass and
fail — and it never counts toward a streak, in either direction.**

Not "fail" and not "pass". A straddling window cannot fail, because a failure
inside it is unattributable: it may belong to the slug that was retired
mid-window, and re-running it on the current slug is the only way to find out.
And it cannot pass, because a clean straddling window is a clean reading of a
system that no longer exists for part of its duration — the very reading
`post_deploy_latency_not_evidence` was written about.

The general form: **a streak counts consecutive observations of ONE system. A
window that spans a change of system is not an observation of either, so it is
not a link in the chain and it does not break the chain.** Discard it and
re-open the window on the far side of the release.

---

## Why both arms, and why this is not just arm B's rule again

LAT-P085 fixed the seven-day counter on arm B: it counted ROWS, then counted
DAYS, and the dated-streak fix made a day with a deploy in it not count. That
was written as a property of the daily banking loop. It is not — it is a
property of *any* interval compared against a target, and arm A (the
window-sampled 500-rate watch) has exactly the same exposure with none of the
same code.

Two failure directions, both real, both silent:

1. **False break.** A release ships a fix; the window that contains the release
   still holds pre-fix errors; arm A records a failed day and resets the
   counter to zero. The system is correct and the instrument says start again.
   Seven days becomes eight, then nine, indefinitely, as long as the deploy
   cadence is faster than the streak length — which it is.
2. **False bank.** A release ships a *regression* late in a window that was
   clean until then; the window's rate stays under threshold on the strength of
   the pre-release majority; the day banks. The streak certifies a slug that
   was live for forty minutes of it.

Direction 2 is the worse one and it is the one a "be conservative, count it as
a failure" shortcut does not fix. INCONCLUSIVE is the only verdict that is
honest in both directions, which is why it is a third value and not a
re-labelling of one of the two.

---

## What it binds

- Arm A and arm B of the #2107 watch both emit `INCONCLUSIVE` and both exclude
  it from the seven.
- An INCONCLUSIVE window is **logged, not dropped** — a run that silently
  discards windows and a run with nothing to report look identical (gotcha
  #53), and a streak that never advances because every window straddles a
  deploy must say so out loud rather than sitting at 3/7 forever.
- The verdict is decided by the release boundary, not by a heuristic about
  whether the release "could have" affected the metric. Any deploy inside the
  window straddles it.

---

## What it does not bind

It does not extend the window, retry it, or interpolate across the boundary.
The window is discarded and the next one starts after the release. A streak
that takes longer to certify because deploys keep landing is reporting a true
fact about the deploy cadence, and the fix for that is a deploy-free date
(which is why #2107's day-1 re-run is scheduled rather than forced), not a
softer verdict.
