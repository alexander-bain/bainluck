# RULING 136 — The falsifier tests a CODE CHANGE, not a slug: releases are tolerated, the cutover transient is not

date: 2026-08-26
author: Alex (directive authored in Alex's Fable session, delivered through the lane runner Alex
launched under his standing authorization 2026-08-26)
issues: #2107
supersedes: amends ruling 135's arm A; retires ruling 130's straddle-disqualification for #2107

Ruling 130 disqualified any window containing a deploy. Ruling 135 measured that against
production, found it unschedulable, and narrowed arm A to the live slug above a 6 h exposure
floor. **That was still unrunnable, for a reason ruling 135 did not price**, and the #2107 gate
has banked zero days in the three days since it shipped.

## The arithmetic that says so

Measured 2026-08-27 over the 100 most recent production releases (2026-08-14T16:59:38Z →
2026-08-27T00:45:58Z, 295.8 h, **0.34 releases/hour**):

| quantity | measured |
|---|---|
| median inter-release gap | **0.63 h** |
| p75 / p90 / max gap | 1.38 h / 11.64 h / 51.19 h |
| gaps ≥ 6 h | 11 of 99 |
| wall-clock with ≥ 6 h since the last release | **52.1 %** |
| P(a random 60-min probe window contains a release) | **22 %** |

A day banks under ruling 135 only if it clears *both*: no release inside the probe hour (78 %)
**and** ≥ 6 h since the last release at grading time (52 %) — jointly ≈ **41 %** per attempt, and
that is the optimistic reading, because without `--last-release-at` the 6 h bound comes from
`_narrow_since`, which walks recorded windows back until the SHA changes. At one window per day
against 0.34 releases/hour, consecutive daily windows essentially never share a SHA, so the
observed bound collapses to the window's own start and arm A grades STRADDLED **every time**.

An INCONCLUSIVE day is not neutral either. `summarize` requires calendar-consecutive clean UTC
dates, so a day that cannot bank is a gap, and a gap resets the streak exactly as a failure does.
At p = 0.41 the expected wait for seven consecutive banked days is on the order of **two years**.
Two independent instrument defects sat underneath that and neither could ever have surfaced,
because every window was already INCONCLUSIVE for the release reason before either was reached:

- `SENTRY_ORG` defaulted to `bain-luck`. **The org is `alexander-bain`.** Any run that did not
  happen to inherit the env var got a 404, which arm A reports as `UNKNOWN`, which grades
  INCONCLUSIVE. Arm A was one unset variable from being permanently unreadable.
- The single window ever recorded (2026-08-24T18:30Z) carries `is_day: false`. It could never
  have banked whatever it measured.

This is the third time in one issue that a #2107 predicate has been **unconditionally
disqualifying** and read as "not yet proven": `_detect_restart` (`len(processes) > 1`, true
always, eight days), then ruling 130's flat 24 h, now ruling 135's 6 h floor. The pattern is the
finding. A gate that cannot fire is worse than no gate, because no gate is visibly absent and a
dead gate looks like diligence.

## The mistake underneath all three

**Ruling 130 attributed to the wrong object.** It reasoned that a window spanning a release
measures "two different systems", so its errors are unattributable. That is true of a *slug* and
false of the thing actually under test. #2107's fix is a code change — `b2e3e1a9` (the team cache
holds detached snapshots) plus `42f2356b` (`season_stats` handed out by reference). **Every slug
deployed since it merged contains it.** A slug boundary between two slugs that both carry the fix
is not a change of the system under test; it is a change of nothing the falsifier is measuring.

What a release *does* change is transient: a dyno boots, an old one drains, caches are cold,
connections re-open. Errors in that band may be artifacts of the cutover rather than of the code.
**That band — not the release — is the thing that has to be excluded.**

## The ruling

**A window is CLEAN when the exposure floor is met and it observed zero `/api/feed` 500s.
Releases inside the window are tolerated. Errors landing inside a named blast-window of a deploy
are not attributable and grade INCONCLUSIVE.**

Five clauses, all pre-registered before grading resumes:

1. **Releases are tolerated.** A release inside the probe window or inside arm A's 24 h lookback
   no longer disqualifies anything. `MIN_POST_RELEASE_EXPOSURE_HOURS` is **retired**.
2. **`DEPLOY_BLAST_WINDOW_MINUTES = 10`.** An error whose timestamp lies within 10 minutes after a
   deploy boundary is unattributable: the window cannot be CLEAN (an error was observed) and
   cannot be FAILED (it may be the cutover). It is INCONCLUSIVE, logged with the boundary it was
   measured against.
3. **Errors outside the blast window are FAILED**, release in the window or not. This is the
   sharpening half: ruling 130 converted every such refutation into a shrug.
4. **The exposure floor is counted in requests, not hours.** `MIN_SERVED_REQUESTS = 50` served
   requests in the window, excluding those issued inside a blast window. Exposure is what the
   instrument actually asked of production, not wall-clock it did not observe. A floor stated in
   hours measures the deploy cadence; a floor stated in requests measures the exposure.
5. **Every slug observed must contain the fix** (`--fix-commit`, repeatable). Verified with
   `git merge-base --is-ancestor` against each commit `/api/health` reported. Tolerating releases
   without this is a real hole: a rollback to a pre-fix slug would otherwise bank a clean day for
   a fix that was not running. Unresolvable or non-containing SHAs grade INCONCLUSIVE.

## 10 minutes is DERIVED, not chosen

BAINLUCK-ZK's 35 lifetime events were timestamped and each one measured against the preceding
release across the same 100-release span:

| blast window B | wall-clock covered | ZK events inside | enrichment | detection lost |
|---:|---:|---:|---:|---:|
| 2 min | 1.1 % | 0 / 35 (0.0 %) | 0.00× | 0.0 % |
| **5 min** | 2.7 % | 3 / 35 (8.6 %) | **3.12×** | 8.6 % |
| **10 min** | 5.4 % | 4 / 35 (11.4 %) | **2.12×** | **11.4 %** |
| 15 min | 7.9 % | 5 / 35 (14.3 %) | 1.80× | 14.3 % |
| 20 min | 10.3 % | 5 / 35 (14.3 %) | 1.38× | 14.3 % |
| 30 min | 14.4 % | 8 / 35 (22.9 %) | 1.59× | 22.9 % |
| 60 min | 22.3 % | 11 / 35 (31.4 %) | 1.41× | 31.4 % |

Enrichment peaks at 5 min and decays to background by 20 min — the signature of a real cutover
transient that dies out within minutes. The four near-deploy events sit at **3.1, 3.3, 4.7 and
7.1 minutes**; 10 minutes covers all of them with the last point still at 2.12×, and costs the
falsifier **11.4 %** of its historical detection power. The bug is overwhelmingly *not* a deploy
artifact: the median event fires **517 minutes** after the preceding release.

Direction matters and is stated so a later reader can check the choice rather than inherit it:
**shorter is fail-closed.** A short B grades transient errors as FAILED, which costs a re-run; a
long B grades real regressions as INCONCLUSIVE, which costs the falsifier. 10 is therefore an
**upper bound justified by the enrichment curve**, not a comfort margin, and 30 and 60 are
rejected on that ground even though they would be more tolerant.

## What this does not do

- **It does not weaken arm B into "500s are fine near a deploy".** A blast-window error is
  recorded, printed, and blocks the day from banking. It buys attribution, not silence.
- **It does not retire ruling 130's general form.** A streak still counts consecutive observations
  of one system. Ruling 136's claim is narrower and specific: *for a falsifier whose subject is a
  code change present in every deployed slug, a slug boundary is not a change of system.* Where
  the subject genuinely is a slug — a rollout, a config flip, an infrastructure change — 130
  stands unamended.
- **It does not credit unobserved time.** The exposure floor counts requests the probe made, and
  nothing else.
- **It does not touch the restart arm.** A worker restart still clears the process-globals under
  watch and still grades INCONCLUSIVE, because that *is* a change of the system under test.
- **It does not lower the bar to closure.** Seven consecutive clean UTC dates, both arms, is
  unchanged. What changed is that seven is now reachable.

Implemented in `backend/scripts/watch_2107_feed_500s.py` (`DEPLOY_BLAST_WINDOW_MINUTES`,
`DEFAULT_WINDOW_MINUTES`, `deploy_boundaries`, `attribute_errors`, `check_fix_ancestry`,
`sentry_events_since`, `streak_from_rows`), pinned by
`backend/tests/test_watch_2107_blast_window.py` — 84 pass, proven RED at 67/68 against the retired
criterion.
Pre-registration record: `docs/audits/latency/lat-p098-2107-closure-gate-respec.md`.

**Two implementation defects, found and fixed after the freeze commit and before day 1 banked.**
Recorded here rather than quietly patched, because "we fixed it after freezing" is the sentence a
pre-registration is supposed to make checkable. Neither changes a clause above; both make the code
match clause 2/3 as written, which the cascade was already internally inconsistent about:

- **A transport error was counted as a refutation.** `attribute_errors` split the whole failure
  list, which carries `status: None` for a refused connection. A request that got no answer is not
  evidence of a 500 — it may be the prober's own network — so it keeps the INCONCLUSIVE transport
  branch it always had. Attribution now counts 5xx only.
- **The 50-row failure cap could soften a FAILED into an INCONCLUSIVE.** `run_probe` records at
  most 50 failures but counts all of them, so a flood whose first 50 happened to land near a deploy
  would have graded with zero attributable. An error the cap hid is not thereby inside a blast
  window, so the remainder is charged to `attributable`.

Both move verdicts in the strict direction only. The first banking window was killed 17 minutes in
and restarted on the corrected build rather than allowed to record a verdict a transport blip could
have turned into a false FAILED.
