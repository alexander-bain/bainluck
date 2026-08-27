# LAT-P098 — #2107's closure gate, re-specified under pre-registration

**Cycle:** LAT-P098 · **Date:** 2026-08-26/27 · **Identity:** `LAT-P098-20260827`
**Directive:** Alex 2026-08-26, authored in Alex's Fable session and delivered through the lane
runner Alex launched under his standing authorization.
**Ship this serves:** the Discover feed — the default landing page — stops being able to 500 on
every request without anyone being able to say when it stopped. #2107 is the P0 that did that on
2026-08-22; this is the gate that lets it be closed on evidence instead of on vibes.

**Ruling banked:** `docs/rulings/136-the-falsifier-tests-a-code-change-not-a-slug.md`.
**Instrument:** `backend/scripts/watch_2107_feed_500s.py`.
**Guard suite:** `backend/tests/test_watch_2107_blast_window.py` — 82 pass, proven RED at 67/68
against the retired criterion.

---

## 0. The headline

| item | verdict |
|---|---|
| **the old gate could not fire** | ✅ **CONFIRMED**, and quantified: ~868 days expected wait |
| **two further defects underneath it** | ✅ **FOUND** — a 404ing Sentry org, and the only row ever recorded carrying `is_day: false` |
| **the new criterion** | ✅ **FROZEN** before grading resumed, then proven on a live window |
| **BAINLUCK-ZK today** | **silent since 2026-08-24T06:35:26Z** — but zero days are banked, because nothing was gradeable |
| **earliest closure date** | **2026-09-02 (UTC)**, and only if every day from 2026-08-27 banks |

---

## 1. The gate was structurally impossible, and here is the arithmetic

Ruling 130 disqualified any window containing a deploy. Ruling 135 (2026-08-24) amended it: arm A
narrows to the live slug above a **6 h post-release exposure floor**. Both were measured against a
twelve-day sample. Re-measured now, over the **100 most recent production releases**
(`heroku releases -a bainluck -n 100 --json`, 2026-08-14T16:59:38Z → 2026-08-27T00:45:58Z):

| quantity | measured |
|---|---:|
| span / count | 295.8 h / 100 releases = **0.34 releases per hour** |
| median inter-release gap | **0.63 h** |
| p75 / p90 / max | 1.38 h / 11.64 h / 51.19 h |
| gaps ≥ 1 h / ≥ 2 h / ≥ 6 h / ≥ 24 h | 38 / 19 / 11 / 1 of 99 |
| wall-clock with ≥ 6 h since the last release | **52.1 %** |
| wall-clock with ≥ 2 h since the last release | 69.7 % |
| P(random 60-min window contains a release) | **22 %** |

A day banked only by clearing both gates at once: no release inside the probe hour (78 %) **and**
≥ 6 h since the last release at grading time (52 %). Jointly **≈ 41 %**.

And 41 % is the *optimistic* reading. Without `--last-release-at`, the 6 h bound came from
`_narrow_since`, which walks recorded windows backwards and stops at the first row whose SHA
differs. At one window per day against 0.34 releases/hour, consecutive daily windows essentially
never share a SHA, so the observed bound collapsed to the window's own start and arm A graded
**STRADDLED every time**.

An INCONCLUSIVE day is not neutral either. `summarize` requires **calendar-consecutive** clean UTC
dates, so a day that cannot bank is a gap, and a gap resets the streak exactly as a failure does.
At p = 0.41 the expected wait for seven consecutive banked days is

```
E = (1 - p^7) / (p^7 (1 - p)) = (1 - 0.001948) / (0.001948 x 0.59) ~= 868 attempts
```

**~868 days.** The recorded state file confirms the prediction empirically: it holds **one row**,
from 2026-08-24T18:30:25Z, and the streak has been 0/7 ever since.

### 1.1 This is the third one, and the pattern is the finding

| predicate | why it could never fire | how long it stood |
|---|---|---|
| `_detect_restart` = `len(processes) > 1` | production runs one web dyno × `WEB_CONCURRENCY=2`, so two ids answer always | 8 days |
| ruling 130, flat 24 h deploy-free lookback | 2 of 12 UTC dates qualified; longest run 2, against a requirement of 7 | ~1 day |
| ruling 135, 6 h post-release exposure floor | ~41 % per attempt, ~868 days to seven consecutive | 3 days |

All three fail in the **same direction**: the gate grades INCONCLUSIVE, which reads to a later
reader as *not yet proven* rather than *broken*. Nobody investigates "not yet closed". A gate that
cannot fire is worse than no gate, because no gate is visibly absent and a dead gate looks like
diligence.

### 1.2 Two more defects, invisible until the release rule stopped shadowing them

Both sat behind the straddle check in the cascade, so no window ever reached them.

1. **`SENTRY_ORG` defaulted to `bain-luck`. The org is `alexander-bain`.** Measured this session:

   ```
   GET /api/0/organizations/bain-luck/issues/?query=issue:BAINLUCK-ZK   -> http 404
   GET /api/0/organizations/alexander-bain/issues/?query=issue:BAINLUCK-ZK -> http 200
   ```

   A 404 surfaces in `sentry_24h_count` as `verdict: UNKNOWN`, which grades the day INCONCLUSIVE.
   Any run that did not happen to inherit the env var from `~/.claude/.env` had a permanently
   unreadable arm A. Fixed, and pinned by a test that asserts the default with `SENTRY_ORG`
   deliberately unset.

2. **The only window ever recorded carries `is_day: false`.** It could never have banked whatever
   it measured. The script already prints this at start-up (LAT-P085's fix); nobody read the line
   because the verdict was going to be INCONCLUSIVE regardless.

---

## 2. The mistake underneath all three

Ruling 130 reasoned that a window spanning a release "measures two different systems". That is
true of a **slug** and false of the thing this falsifier tests.

#2107's fix is a **code change** — `b2e3e1a9` (the team cache holds detached snapshots) and
`42f2356b` (`season_stats` handed out by reference). Every slug deployed since it merged contains
it, verified rather than asserted:

```
06fdad74 (v3908, live):  b2e3e1a9=YES  42f2356b=YES
baae52c2 (v3907):        b2e3e1a9=YES  42f2356b=YES
f88fd4fc (v3906):        b2e3e1a9=YES  42f2356b=YES
```

A boundary between two fix-carrying slugs is not a change of the system under test. What a release
*does* change is transient — a dyno boots, an old one drains, caches are cold, connections re-open
— and **that band, not the release, is what has to be excluded.**

---

## 3. The frozen criterion (ruling 136)

> A window is **CLEAN** when the exposure floor is met and it observed zero `/api/feed` 500s.
> Releases inside the window are tolerated. Errors landing inside a named blast-window of a deploy
> are not attributable and grade INCONCLUSIVE.

| clause | value | where |
|---|---|---|
| 1 · releases tolerated | `MIN_POST_RELEASE_EXPOSURE_HOURS` **retired** | the straddle branches are gone from the cascade |
| 2 · blast window | `DEPLOY_BLAST_WINDOW_MINUTES = 10` | error inside → INCONCLUSIVE |
| 3 · attributable errors | error outside → **FAILED**, release or no release | the sharpening half |
| 4 · exposure floor | `MIN_SERVED_REQUESTS = 50`, outside any blast band | counted in requests, not hours |
| 5 · fix ancestry | `--fix-commit`, defaulting to both fix SHAs | `git merge-base --is-ancestor` per observed commit |

Plus `DEFAULT_WINDOW_MINUTES = 90`, derived in §3.2.

Clause 5 is the one that makes clause 1 sound rather than merely convenient. Tolerating releases
without it would let a **rollback to a pre-fix slug bank a clean day for a fix that was not
running** — and a clean window on a pre-fix slug is indistinguishable from a clean window that
certifies everything.

### 3.1 Ten minutes is derived, not chosen

All 35 lifetime BAINLUCK-ZK events were pulled with per-event timestamps
(`/api/0/issues/7677420933/events/`) and each measured against the preceding release across the
same 100-release span:

| blast window B | wall-clock covered | ZK events inside | enrichment | detection lost |
|---:|---:|---:|---:|---:|
| 2 min | 1.1 % | 0 / 35 (0.0 %) | 0.00× | 0.0 % |
| **5 min** | 2.7 % | 3 / 35 (8.6 %) | **3.12×** | 8.6 % |
| **10 min** | 5.4 % | 4 / 35 (11.4 %) | **2.12×** | **11.4 %** |
| 15 min | 7.9 % | 5 / 35 (14.3 %) | 1.80× | 14.3 % |
| 20 min | 10.3 % | 5 / 35 (14.3 %) | 1.38× | 14.3 % |
| 30 min | 14.4 % | 8 / 35 (22.9 %) | 1.59× | 22.9 % |
| 60 min | 22.3 % | 11 / 35 (31.4 %) | 1.41× | 31.4 % |

Enrichment peaks at 5 min and is back to background by 20 min — the signature of a real cutover
transient that dies out within minutes. The four near-deploy events sit at **3.1, 3.3, 4.7 and
7.1 minutes**. 10 minutes covers all four with the last point still enriched 2.12×, and costs the
falsifier 11.4 % of its historical detection power. The bug is overwhelmingly **not** a deploy
artifact: its **median event fires 517 minutes after the preceding release**.

**Shorter is fail-closed**, which is why 10 is an upper bound rather than a margin. A short B
grades a transient error FAILED, costing a re-run; a long B grades a real regression INCONCLUSIVE,
costing the falsifier. 30 and 60 are rejected on that ground despite being more tolerant.

### 3.2 Ninety minutes is derived from the floor

A blast band costs the window ~10 samples, so at one sample per minute the window length and the
request floor are coupled. Simulated over the same 100 releases, stepping a candidate window start
every 5 minutes across the whole 295.8 h span and counting the start times that still clear 50
served requests outside every band:

| window | start times clearing the floor | 7 consecutive days |
|---:|---:|---:|
| 60 min | 3,184 / 3,538 = **90.0 %** | 47.8 % |
| 75 min | 3,429 / 3,535 = 97.0 % | 80.7 % |
| **90 min** | **3,524 / 3,532 = 99.8 %** | **98.6 %** |
| 120 min | 3,526 / 3,526 = 100.0 % | 100.0 % |

60 minutes leaves a single mid-window deploy sitting *on* the floor — 60 samples minus ~11 blasted
is 49, one short. That is the ruling-135 mistake in miniature: a criterion that happens to be
clearable is not a criterion that is runnable. **Expected wait to seven consecutive clean days
falls from ~868 days to ~7.1.**

### 3.3 The cap this criterion does have, stated rather than discovered

Four **evenly spaced** deploys in a 90-minute window leaves 46 served requests, four short of the
floor, and grades INCONCLUSIVE. That shape is **0.99 %** of measured windows, and in practice
rarer, because real 4-deploy windows are clustered and their bands overlap rather than costing 10
minutes each — which is why the whole-span simulation reads 99.8 % rather than 99.0 %. Pinned as a
test (`test_the_cap_this_criterion_does_have_is_named_not_hidden`) rather than left to be found: a
criterion with an unstated cap reads as covering what it does not cover.

---

## 4. Pre-registration, and how it was enforced

The directive required the criterion frozen **before** grading resumed. The order of operations was
therefore:

1. measure the deploy cadence and the ZK event distribution — **instrument calibration, no grading**;
2. write ruling 136 and the constants derived from those measurements;
3. implement, and prove the guard suite RED against the retired criterion;
4. **commit — this is the freeze**;
5. only then run a banking window.

Step 3's red-first is the receipt that the suite discriminates rather than merely passing. The
current script was copied aside, `git show HEAD:...` restored the retired one in its place, and the
new suite was run against it:

```
old script in place:  67 failed, 1 passed
new script restored:  82 passed          (shasum 75dd351c7ab7ba3480c2e9b5ed2d0c81c5a91caa,
                                          identical to the pre-swap copy)
```

Nothing was graded between the measurement and the freeze. The freeze is commit `69c4a9a7`.

### 4.1 Two implementation defects found AFTER the freeze, declared

"We fixed it after freezing" is exactly the sentence a pre-registration exists to make checkable,
so both are named rather than quietly patched. Neither changes a clause; both make the code match
clause 2/3 as written, and the pre-fix cascade was already internally inconsistent about it —
it carried a separate transport branch while feeding every failure into the 5xx count.

1. **A transport error was counted as a refutation.** `status: None` means the request got no
   answer at all, which may be the prober's own network. It is not a 500. Attribution now counts
   5xx only, and transport errors keep the INCONCLUSIVE branch they always had.
2. **The 50-row failure cap could soften a FAILED into an INCONCLUSIVE.** `run_probe` records at
   most 50 failures but counts all of them, so a flood whose first 50 landed near a deploy would
   have graded with zero attributable. The remainder is now charged to `attributable`.

Both move verdicts in the **strict** direction only. Fixed in `c246f717`, guards 82 → 84 (2 added,
1 corrected — the old `test_a_transport_error_is_attributed_the_same_way` asserted defect 1 as if
it were the intended behaviour, which is how it survived review).

**The first banking window was killed 17 minutes in and restarted on the corrected build**, by pid
rather than by pattern, rather than letting it record a verdict a single transport blip could have
turned into a false FAILED on day 1. No row was written by the killed run.

---

## 5. The proof — a live window under the frozen criterion

*(appended after the freeze commit; see §7 for the run record)*

---

## 6. The new earliest closure date

Closure is unchanged: **seven consecutive clean UTC dates, both arms.** What changed is that seven
is reachable.

| | |
|---|---|
| banked days as of the freeze | **0 / 7** |
| first date that can bank | **2026-08-27 (UTC)** |
| **earliest closure date** | **2026-09-02 (UTC)** — 2026-09-01 in PT terms for the last window |
| condition | every one of the seven dates banks; one FAILED or one missed date restarts the count |

`--summarize` now prints this line itself, so the date is read off the instrument rather than off
this document.

Arm A is currently silent — BAINLUCK-ZK's last event was **2026-08-24T06:35:26Z**, so the bug has
not fired in over two days. That is encouraging and it is **not** evidence: zero days are banked
because nothing was gradeable, and unbanked silence is exactly the state ruling 136 exists to stop
being mistaken for progress.

---

## 7. Contamination introduced by this cycle, declared

Ruling 127's general form: an instrument that writes to what it reads must say so.

- **`/api/feed`: 3 warm requests** taken as a liveness read before the window, plus the banking
  window's own samples. The probe is the instrument; its requests are the exposure the floor is
  counted over, and they are declared rather than netted out.
- **Sentry: read-only.** Three `GET`s against the organizations and issues endpoints. No issue was
  resolved, ignored, assigned or annotated.
- **Heroku: read-only.** `heroku releases --json` only. No dyno was restarted, scaled or configured.
- **`git merge-base --is-ancestor`: local, read-only.** No refs written.
- **`.claude/handoff/RULING-CLAIMS.md`: one append** claiming ruling 136 (shared mutable state in
  the main worktree; ledger snapshot quoted in the claim line, per ruling 063).
- **The watch state file** `docs/audits/latency/2107-watch.jsonl` gains rows from §5 onward. Rows
  recorded before the freeze carry no `criterion` field; rows after it carry `criterion:
  "ruling-136"`, so a later reader cannot mistake one ruler for the other.

**Provenance:** LAT-P098, 2026-08-27. Related: #2107, rulings 130 / 135 / 136.
Instrument: `backend/scripts/watch_2107_feed_500s.py`.
