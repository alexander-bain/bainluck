# The freeze window is LOST — arithmetically, at beat 15, and class B spent the last of it

`calibration-912` DECIDE 1 asked whether the diagnostics census could be stopped from
blocking the publish, and put the window's survival at **P ≈ 0.4%** on the measured miss
rate. The question is now settled by events rather than by probability.

```
CAL-P140 RE-BASELINE MONITOR — 22 of the last 24
  12/15 clean so far (window 24)   (3 misses; -1 of 2 budget left)
  ###?##C#######B   <- oldest ... newest
  baseline 2026-08-29T23:35:53+00:00
  ring     168 observations, 153 excluded as pre-baseline
  VERDICT  WINDOW_NOT_FULL
```

**The arithmetic, which is the whole report.** 24 beats, 22 required. 15 observed, 12
clean. Nine beats remain and every one of them is already spoken for:

```
    12 clean + 9 remaining = 21   <   22 required
```

**21 < 22. The window cannot be reached even if nothing ever fails again.** The shepherd
still prints `WINDOW_NOT_FULL`, which is true and is not the useful sentence: the verdict
string reports whether the window is FULL, not whether it is REACHABLE, and those two
diverged at beat 15. This is the same read CAL-P129 flagged (*"the window is
arithmetically LOST while the verdict string still reads as wait"*) — one window later, on
a fresh baseline, in the same shape.

## What spent it

| beat | at | class | what it was |
|---|---|---|---|
| #4 | `02:38:29Z` | `B_OR_D_UNATTRIBUTED` | failed before the gate; B and D are indistinguishable in the ring once `last_error` is overwritten |
| #7 | `05:26:33Z` | `C_DEPLOY_KILL` | cancelled mid-flight after 693 s — a release, not the producer |
| #15 | `13:42:18Z` | **`B_DIAGNOSTICS_TRUTH_CENSUS`** | `QueryCanceledError: canceling statement due to statement timeout` |

**Beat 15 is unambiguous and it is D22's exact subject.** The truth-evidence census
(`precompute_calibration.py:4025`) is an unbounded scan over every resolved futures row,
sitting in a `required` phase AHEAD of the publish, feeding nothing the publish gate reads
— by its own comment, *"no source-bias interpretation; just the counts"*.

Beat #4 is the honest gap: it may have been the same class. If it was, class B alone spent
**two of the three** misses in this window, and the one exogenous miss (#7, a release) was
survivable. The attribution could not be recovered — `task-metrics.last_error` is
overwritten by the next failure, and a miss not classified within one beat is
unclassifiable. That is a property of the ring, not of this session.

## What this changes about the ask

D22 was *"may I stop a diagnostic from blocking the publish?"* with a recommendation to
bundle it with the freeze lift rather than take an exception. Nothing in that
recommendation changes — **but the cost of waiting is now measured rather than forecast.**
This class has now spent freeze budget in two consecutive windows.

**The next window cannot start clean while the class is live.** Re-baselining today would
start a 24-beat window whose first miss is already scheduled: the futures rebuild is on
beat 10 of a fresh census (`beats_to_publish: 10` at beat 14), and calibration-912 measured
that the census is squeezed under the ~104 s it needs precisely when the rebuild is heavy.
So the useful sequencing is: **answer D22, land it, THEN re-baseline** — a window opened
before the repair measures the defect, not the producer.

And the coupling runs the other way too: landing the 12-CAL repair (D13) invalidates
`input_fingerprint`, discards the banked futures units, and manufactures ~10 heavy rebuild
beats — the exact condition this class fires under. See
`RULE-DESIGN-12CAL-lost-losses.md` §5. **D22 before D13, or both on one deploy.**

## The window is lost; the instrument is not

The shepherd keeps classifying. Every beat still lands in
`artifacts/cal-p140/window-log.jsonl` with its class, its `staged_at` discriminator and its
attribution, so the miss-rate estimate the NEXT window will be judged against keeps
improving while this one runs out. That is the whole reason the watcher was not killed when
the window became unreachable: a lost window is still a measurement of the producer, and
it is the only one that will exist when D22 is answered.

* watcher `pid 3019` (orphaned to init, poll 420 s) — alive and logging throughout this
  session, restarts: 0.
* beats logged at hand-off: see `window-log-snapshot.jsonl` in this directory.

## Re-read at hand-off — beat 16 published, and the arithmetic did not move

```
  13/16 clean so far (window 24)   (3 misses; -1 of 2 budget left)
  ###?##C#######B#   <- oldest ... newest
  VERDICT  WINDOW_NOT_FULL
```

`13 clean + 8 remaining = 21 < 22`. A clean beat cannot un-lose a window that is short on
budget, and this is what that looks like: the strip gets better, the verdict string stays
the same, and the reachable maximum is still 21. Full output in `window-at-handoff.txt`.
