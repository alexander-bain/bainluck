# #2107 — T0 for the seven-day watch

**LAT-P084 item 3** (Fable directive 2026-08-24, pasted and reviewed by Alex):

> Gated on wave-2 deploy: record T0 (release id + timestamp), start the 7-day
> #2107 watch, and bank day counts only when `counts_toward_seven` is true — your
> INCONCLUSIVE-refuses-to-count behavior is correct and ratified.

**The gate opened mid-window.** It was closed at 17:11Z (master 43 commits ahead
of a deployed v3885) and open by 17:41Z. This file records the moment so the
seven days are counted from a fact rather than from a recollection.

---

## T0

| field | value |
|---|---|
| **release** | **v3886** |
| **commit** | **`b5c2a750c8c20516ce2ba9e100a7164ee2c4ed98`** |
| commit subject | `fix(test): #2107's regression test aged its TTL anchor by uptime, not by age` |
| **deployed at** | **2026-08-24 17:23:50 UTC** = 10:23:50 PDT |
| deployer | alex.bain@gmail.com |
| previous release | v3885 / `81380151`, 2026-08-23 21:48:40 UTC |

**T0 = 2026-08-24T17:23:50Z.** Day 1 of seven cannot close before
2026-08-25T17:23:50Z, and the seven cannot close before **2026-08-31T17:23:50Z**
— and only then if all seven day-windows return `counts_toward_seven: true`.

## Why v3886 is the wave-2 deploy

The #2107 team-cache detachment fix reached `master` inside the INT-112 merge
`4eb54e5f` ("Merge program/latency-75 @ 10209343 (LAT-P082, C-2107-R1 GREEN —
#2107 team-cache detachment P0) into int112/stage"), and

    git merge-base --is-ancestor 4eb54e5f b5c2a750   →   true

so the deployed slug contains it. Before v3886 it did **not**: at 17:11Z
`origin/master` was `fe28d2c3` and the current release was still v3885
(`81380151`), which `4eb54e5f` is *not* an ancestor of. **A merge is not a
deploy** — that distinction is the whole reason this file exists, and it is what
kept item 3 correctly blocked for the first hour of this window.

## What is NOT claimed here

- **No day has been banked.** T0 is a timestamp, not a clean day. The watch
  (`backend/scripts/watch_2107_feed_500s.py`) had **no state file at all** when
  this was written — `docs/audits/latency/2107-watch.jsonl` did not exist — so
  the recorded streak is **0 of 7**.
- **Merging is not closure and neither is deploying.** The cert window that
  diagnosed #2107 found BAINLUCK-ZK firing on 4 of 5 days, so a clean 24 h is
  ~1-in-5 clean by luck. Do not close #2107 on this file.
- A single `GET /api/feed?limit=5` at **17:44:0xZ** returned **200 in 5.72 s**
  (a cache miss, ~3 min after a dyno restart). That is a liveness check, not an
  arm of the watch, and it is recorded here because it is one probe sample this
  lane put into the `always_sampled` census and therefore owes a subtraction
  (ruling 127).

## Ordering note — why the watch did not start the instant the gate opened

The watch's arm B is a **1 req/min `GET /api/feed` probe for 60 minutes**.
`/api/feed` is on `always_sampled_endpoints`, so those 60 requests are 60
entries in the same census LAT-P084 item 1 is measuring, against an organic rate
of ~66 req/h — the probe would roughly **double the population** and swamp the
miss-share signal it would be measured beside. Ruling 127 governs the tie: *take
the feed read first*. The post-v3886 organic accumulation is taken first, and
day 1 of the watch starts after it, on the same day. Both are recorded with
their own start times so neither is mistaken for the other.
