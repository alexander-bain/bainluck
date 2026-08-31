# CAL-P148 — the "may skip" flag is settled, and the burst that nearly settled it wrong

**TL;DR.** Nothing landed; the freeze holds (`git diff backend/` **0 bytes**, `precompute_calibration.py`
untouched, D13/D22 still unanswered, YOUR-TURN.md unmodified since 07:12 PT). All three carried
instruments re-run green. The budget went to the queue's 🔴 item 2, which is now **closed with a
number** instead of being carried forward a fourth session:

1. ✅ **The serve does not skip the way CAL-P147 feared, and the producer was never at fault.**
   Redis held beat 17 (`15:37:21`) at 16:10Z while the public route served beat 16 (`14:38:38`).
   The producer published normally. The gap is entirely the route's **per-worker in-process memo**
   (`routes/calibration.py:34-35`, `CACHE_TTL = 3600`), which tier 1 serves without ever asking
   Redis whether something newer exists (`:1137-1164`).
2. ✅ **Watched a flip happen live: a 34-minute LAG, not a skip.** Beat 17 reached the serve at
   ~16:09Z, and **the unattended banker caught it by itself at 16:10:02Z** — CAL-P147's thesis
   proven end-to-end on the live article, with no session awake for the capture.
3. 🔴 **A skip is still structurally possible, and is now quantified: ~1 beat in 203, ~1 promotion
   bracket in 102.** Staged as `alex-inbox/calibration-917`. Small enough that the recommendation
   is to do nothing and stop re-deriving it.
4. 🔴 **I nearly filed that number 8× too large, and the way it was caught is the lesson.** See §3.

Window still stands at **17 beats, 14 clean, 3 misses (4=B, 7=C, 15=B, all attributed)**, not
re-baselined. Watcher 3016/3019 untouched, zero restarts.

---

## 1. Carried instruments — all re-run

| check | result |
|---|---|
| watcher singleton | pids **3016/3019** unchanged, checked first thing and after every process action |
| banker liveness | pids 75909/75911 alive, heartbeat advancing (`16:03:59 -> 16:10:02 -> 16:13:04`) |
| freeze | `git diff backend/` **0 bytes** at entry and exit |
| D13 / D22 | **both still unanswered**; `land-12cal.sh` not run; nothing applied |
| `cal-p144/window-beat-margins.py` | **exit 0 — 15 gauged, 15 agreements, 0 disagreements** |
| `cal-p146/promotion-datapoint.py` | **exit 0** — no RECOVERABLE measurement beat unread; beat 14 still ⚫ permanent |
| `cal-p145/refusal-register.py` | **exit 0** — no unregistered `RULE-DESIGN-*.md`; this session authored none |
| unattributed misses | **none** |

`window-beat-margins.py` first returned **exit 1 — "source ~/.claude/.env first"**. Per gotcha #124
that is a story about the harness, not a result: re-run with the env sourced it is exit 0, 15/15.
No new beat landed during the session (beat 18 due ~16:35Z).

## 2. What the lag actually is

Three facts, each measured rather than reasoned from:

* **Redis was ahead.** `/api/admin/calibration/mce` is a bare `_rc.get("bainluck:calibration:main")`
  with no memo in front of it. It returned `15:37:21.873623` while the public route returned
  `14:38:38.114919`. **`bust` was never passed** — the task send sits inside `if bust:`
  (`admin_data_quality.py:3807`), verified by reading the handler before firing it, so the probe
  queues nothing and cannot inject a phantom producer run into the window being measured.
* **The memo TTL is fixed, not sliding.** Tier 1 returns at `:1164` without touching
  `_cache["timestamp"]`; only a tier-2 Redis read restamps it. A sliding TTL would have pinned the
  serve forever under continuous traffic — a completely different and much worse bug. It isn't one.
* **Beat gaps are 47.8–76.4 min, mean 60.09, median 58.5**, against a 60-minute sampler. The mean
  sitting *exactly* on the TTL is why a mean-gap model is useless here: it predicts zero skips by
  construction. The variance is the whole phenomenon, so the rate has to come from the empirical
  distribution.

Monte Carlo over the 16 measured gaps, 20,000 trials × 160 beats, phases uniform:

| independent clocks | P(beat never served) | P(promotion bracket broken) |
|---|---|---|
| 1 | 0.0425 — 1 in 24 | 0.083 — 1 in 12 |
| **2 (measured)** | **0.0049 — 1 in 203** | **0.0098 — 1 in 102** |
| 3 | 0.0008 — 1 in 1256 | 0.0016 — 1 in 628 |

## 3. 🔴 The burst measured a coincidence and read as a mechanism

A 24-request burst at 16:07Z returned **one** distinct `generated_at`, 20/20. I read that as a
phase-locked serve — one effective clock — and had the 1-in-12 row written up and staged. The
supporting story was even plausible: one web dyno, and a deploy (`beat 7 = C_DEPLOY_KILL`) restarts
every worker at the same instant, so of course their TTLs are in lockstep.

It was wrong. The probe's *time series* killed it within four minutes:

```
16:11:37Z  served 15:37:21 (beat 17)
16:14:20Z  served 14:38:38 (beat 16)   <- BACKWARD. One clock cannot do this.
16:16Z     re-burst: 19/5 split across the two censuses
```

`WEB_CONCURRENCY=2` on one web dyno — two uvicorn processes, two `_cache` dicts, two phases. They
boot together but diverge, because each pins its memo whenever *its own* first unmarked Redis read
lands, and post-boot a stale-marked payload is deliberately not served from tier 1 (`:1133-1136`),
so each worker re-reads until its own read is admitted. The 20/20 was both workers briefly holding
the same census. A skip needs **every** clock to miss, so the honest rate is 8× smaller and the
recommendation flips from "worth a look" to "ignore".

**The instrument was rewritten to match**, because the first version's skip test was adjacent-pair
(`prev.served != cur.served`), which under two oscillating clocks reads every backward move as a
transition and is meaningless. It now tests over **sets across time**: a census counts as skipped
only once it has left Redis by more than one full `CACHE_TTL` — so every clock has certainly turned
over — and no worker ever served it. Anything younger is *still in flight*, and calling it a skip
would be CAL-P147's own "unbracketed so far is not permanent" error in a new costume. The report
also prints the backward-move count, which is the one-line proof of how many clocks there are.
Current output: 1 census in Redis, 2 ever served, 2 backward moves, **0 settled → verdict withheld,
exit 0**.

## 4. Two side findings, both from reading rather than assuming

* **Republishes are not content-stable.** `staged_at` moved exactly once in 17 beats (at beat 14,
  the promotion), so it — not `generated_at` — is the content identity. But payloads at *constant*
  `staged_at` still drift: `total_outcomes` 925,446 → 925,466 → 926,007 across beats 3/6/8, and
  `cells_total` 290 → 291. So a promotion bracket genuinely needs **adjacent** beats;
  CAL-P147's adjacency requirement stands and beat 14 stays ⚫ permanent. I checked this
  specifically because if republishes *had* been stable, beat 14 would have been recoverable from
  renders already on disk — worth ruling out before accepting a permanent loss, but it does not hold.
* **The render noise floor is one known field.** Two renders of the *same* census (cal-p140 vs
  cal-p141, both `04:35:25.200044`) differ in exactly one line: `producer_beats_missed` 0 → 2 — a
  scorer-side annotation, not payload. So a bracket diff attributes nothing to the promotion that
  the renderer invented. Nobody had measured this; the guard's whole method rests on it.

## 5. Deliberately not done

* **Landed nothing.** D13, D21, D22 remain Alex's and ungranted; the pre-builds are applied nowhere.
* **Did not re-baseline** — D22 has not landed.
* **Did not build the class-B cure** — still the frozen file, still nobody has asked.
* **Did not extend the missing-loser census** — 45 cells stay PARKED as CAL-P122-1 (ruling 134).
* **Did not fire `bust`** on either route.
* **Did not touch the live window log or the watcher**, and did not restart the banker.
* **Did not propose the cache fix as work.** It is one line, and it is architecture-only against a
  frozen file with no queued ship — the rider rule forbids it. Filed as FYI, not as a queue.
* **Authored no `RULE-DESIGN-*.md`**, so the refusal register's reconciliation is unaffected.

## Evidence

| file | what |
|---|---|
| `serve-phase-probe.py` | §2–3 — the probe; `--report` for transitions + verdict. ruff clean |
| `serve-phase-log.jsonl` | the transition list, including the two backward moves |
| `serve-phase-heartbeat.json` | liveness; a stale stamp with a live pid means wedged |
| `probe-stdout.log` | the running process's own output |
| `../cal-p147-renders/scorecard-20260830T153721-873623.txt` | §1 — the first render banked by the timer, unattended |
| `alex-inbox/calibration-917` | the Alex-facing FYI |

## Running processes at hand-off

```
pgrep -f "rebaseline.py --baseline-at"      -> 3016 3019    watcher — NEVER restart, never duplicate
pgrep -f "CAL-P147-RENDER-BANKER"           -> 75909 75911  render banker
pgrep -f "CAL-P148-SERVE-PHASE-PROBE"       -> 37525 37527  serve-phase probe
```

All three carry lane-unique tokens and can be pkill'd by token without hitting another lane.
